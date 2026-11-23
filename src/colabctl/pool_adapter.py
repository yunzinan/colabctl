"""Typed subprocess adapter around `colab-pool`, `colab-account`, and `colab`."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from colabctl.models import normalize_high_mem

RESULT_MARKER = "__COLABCTL_JSON__:"


class PoolAdapterError(RuntimeError):
    """Raised when an upstream colab-pool or colab-account operation fails."""

    def __init__(
        self,
        message: str,
        *,
        returncode: int = 1,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@dataclass(frozen=True)
class CommandOutput:
    returncode: int
    stdout: str
    stderr: str


def _resolve_executable(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for prefix in (
        os.path.expanduser("~/.local/bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ):
        candidate = os.path.join(prefix, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _extract_json(text: str) -> Any:
    """Parse JSON from stdout, tolerating leading/trailing non-JSON log lines."""
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty JSON output")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(stripped[start : end + 1])
    raise ValueError(f"No valid JSON object found in output: {stripped[:300]!r}")


class PoolAdapter:
    """Wraps `colab-pool` and `colab-account` commands with structured I/O."""

    def __init__(
        self,
        *,
        pool_bin: str | None = None,
        account_bin: str | None = None,
        colab_bin: str | None = None,
    ) -> None:
        self.pool_bin = pool_bin or _resolve_executable("colab-pool") or "colab-pool"
        self.account_bin = (
            account_bin or _resolve_executable("colab-account") or "colab-account"
        )
        self.colab_bin = colab_bin or _resolve_executable("colab") or "colab"

    def check_binaries(self) -> dict[str, str | None]:
        return {
            "colab": _resolve_executable(self.colab_bin),
            "colab-pool": _resolve_executable(self.pool_bin),
            "colab-account": _resolve_executable(self.account_bin),
            "ssh": _resolve_executable("ssh"),
        }

    def _run(
        self,
        argv: list[str],
        *,
        input_text: str | None = None,
        env_overrides: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandOutput:
        env = os.environ.copy()
        if env_overrides:
            env.update(env_overrides)
        try:
            proc = subprocess.run(
                argv,
                input=input_text,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise PoolAdapterError(
                f"Executable not found: {argv[0]}. Install google-colab-cli and colab-account-changer first."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise PoolAdapterError(
                f"Command timed out after {timeout}s: {' '.join(argv)}",
                returncode=124,
                stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
            ) from exc
        return CommandOutput(proc.returncode, proc.stdout, proc.stderr)

    def list_raw(self, *, live: bool = False) -> dict[str, Any]:
        argv = [self.pool_bin, "list", "--json"]
        if not live:
            argv.append("--cached")
        res = self._run(argv, timeout=180)
        # Note: colab-pool list may exit 1 if one account failed inspection while
        # still outputting a valid JSON payload with partial results + errors.
        try:
            return _extract_json(res.stdout)
        except ValueError as exc:
            msg = (res.stderr or res.stdout).strip() or f"exit code {res.returncode}"
            raise PoolAdapterError(
                f"Failed to query colab-pool list: {msg}",
                returncode=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
            ) from exc

    def new_session(
        self,
        name: str,
        *,
        gpu: str = "t4",
        high_mem: bool = False,
        account: str | None = None,
        allow_other_account: bool = False,
        if_missing: bool = False,
        assign_timeout_s: int = 120,
        assign_retries: int = 2,
    ) -> CommandOutput:
        argv = [self.pool_bin, "new", name]
        if account:
            argv.extend(["--account", account])
        if allow_other_account:
            argv.append("--allow-other-account")
        if if_missing:
            argv.append("--if-missing")
        extra: list[str] = []
        if gpu and gpu.lower() != "none":
            extra.extend(["--gpu", gpu.upper()])
        if normalize_high_mem(gpu, high_mem):
            extra.append("--high-mem")
        if extra:
            argv.append("--")
            argv.extend(extra)

        env_overrides = {
            "COLAB_CLI_REQUEST_TIMEOUT": str(assign_timeout_s),
            "COLAB_CLI_ASSIGN_RETRIES": str(assign_retries),
        }
        # Allow enough headroom for retries + backoff
        overall_timeout = max(120, (assign_timeout_s + 30) * (assign_retries + 1) + 60)
        res = self._run(argv, env_overrides=env_overrides, timeout=overall_timeout)
        if res.returncode != 0:
            detail = (res.stderr or res.stdout).strip()
            raise PoolAdapterError(
                f"Failed to allocate session '{name}' (exit {res.returncode}): {detail}",
                returncode=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
            )
        return res

    def stop_session(self, name: str, *, forget: bool = False) -> CommandOutput:
        argv = [self.pool_bin, "stop", name]
        if forget:
            argv.append("--forget")
        res = self._run(argv, timeout=90)
        if res.returncode != 0:
            detail = (res.stderr or res.stdout).strip()
            raise PoolAdapterError(
                f"Failed to stop session '{name}': {detail}",
                returncode=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
            )
        return res

    def stop_all(self) -> CommandOutput:
        res = self._run([self.pool_bin, "stop-all", "--yes"], timeout=180)
        if res.returncode != 0:
            detail = (res.stderr or res.stdout).strip()
            raise PoolAdapterError(
                f"Failed to stop all sessions: {detail}",
                returncode=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
            )
        return res

    def reap_orphan(self, account: str, endpoint: str) -> CommandOutput:
        res = self._run(
            [self.pool_bin, "reap", account, endpoint, "--yes"], timeout=90
        )
        if res.returncode != 0:
            detail = (res.stderr or res.stdout).strip()
            raise PoolAdapterError(
                f"Failed to reap orphan {endpoint} on {account}: {detail}",
                returncode=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
            )
        return res

    def set_primary(
        self, account: str, *, threshold: float | None = None
    ) -> CommandOutput:
        argv = [self.pool_bin, "primary", account]
        if threshold is not None:
            argv.extend(["--threshold", str(threshold)])
        res = self._run(argv, timeout=30)
        if res.returncode != 0:
            detail = (res.stderr or res.stdout).strip()
            raise PoolAdapterError(
                f"Failed to set primary account: {detail}",
                returncode=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
            )
        return res

    def exec_json(
        self, name: str, python_code: str, *, timeout_s: int = 45
    ) -> dict[str, Any]:
        """Run Python on the remote kernel via `colab-pool exec` and parse RESULT_MARKER."""
        argv = [self.pool_bin, "exec", name, "--timeout", str(timeout_s)]
        res = self._run(argv, input_text=python_code, timeout=timeout_s + 30)
        if res.returncode != 0:
            detail = (res.stderr or res.stdout).strip()
            raise PoolAdapterError(
                f"Remote exec failed on '{name}': {detail}",
                returncode=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
            )
        for line in reversed(res.stdout.splitlines()):
            if line.startswith(RESULT_MARKER):
                payload = line[len(RESULT_MARKER) :].strip()
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError as exc:
                    raise PoolAdapterError(
                        f"Malformed JSON from remote exec on '{name}': {payload[:200]}"
                    ) from exc
                if not isinstance(data, dict):
                    raise PoolAdapterError(
                        f"Expected JSON object from remote exec on '{name}'"
                    )
                return data
        err_text = (res.stderr or res.stdout).strip()
        raise PoolAdapterError(
            f"Remote code did not emit a result marker on '{name}': {err_text[-600:]}",
            returncode=1,
            stdout=res.stdout,
            stderr=res.stderr,
        )

    def drivemount(self, name: str, mount_path: str = "/content/drive") -> int:
        """Run interactive `colab-pool drivemount` attached to user stdio."""
        proc = subprocess.run([self.pool_bin, "drivemount", name, mount_path])
        return proc.returncode

    def build_proxy_argv(self, name: str, identity_file: str) -> list[str]:
        return [
            self.pool_bin,
            "ssh",
            name,
            "--proxy-mode",
            "-i",
            identity_file,
        ]
