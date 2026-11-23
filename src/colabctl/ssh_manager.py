"""Managed SSH config, `~/.ssh/config` Include integration, and ControlMaster muxing."""

from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from colabctl.config import AppPaths, AppSettings, atomic_write_private
from colabctl.models import LocalSessionMeta

MANAGED_HEADER = "# Managed automatically by colabctl. Do not edit by hand.\n"


def control_socket_path(paths: AppPaths, session_name: str) -> Path:
    """Short Unix socket path safely under macOS's 104-byte SUN_LEN limit."""
    digest = hashlib.sha256(session_name.encode("utf-8")).hexdigest()[:12]
    return paths.control_dir / f"c-{digest}.sock"


def resolve_colabctl_executable() -> str:
    found = shutil.which("colabctl")
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / "colabctl"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return "colabctl"


class SshManager:
    """Maintains `~/.config/colabctl/ssh_config` and OpenSSH ControlMaster sockets."""

    def __init__(
        self,
        paths: AppPaths,
        *,
        colabctl_bin: str | None = None,
    ) -> None:
        self.paths = paths
        self.colabctl_bin = colabctl_bin or resolve_colabctl_executable()

    def include_directive(self) -> str:
        return f"Include {self.paths.managed_ssh_config}"

    def is_included_in_user_ssh_config(self) -> bool:
        cfg = self.paths.user_ssh_config
        if not cfg.is_file():
            return False
        target = str(self.paths.managed_ssh_config)
        tilde_target = target.replace(str(Path.home()), "~", 1)
        for raw_line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[0].lower() == "include":
                arg = parts[1].strip().strip('"').strip("'")
                if arg in (target, tilde_target):
                    return True
        return False

    def ensure_user_ssh_include(self) -> bool:
        """Idempotently prepend `Include <managed_ssh_config>` to `~/.ssh/config`.

        Returns True if `~/.ssh/config` was modified, False if already present.
        """
        self.paths.ensure_dirs()
        if not self.paths.managed_ssh_config.exists():
            atomic_write_private(self.paths.managed_ssh_config, MANAGED_HEADER)

        if self.is_included_in_user_ssh_config():
            return False

        self.paths.ssh_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        cfg = self.paths.user_ssh_config
        existing = ""
        if cfg.is_file():
            existing = cfg.read_text(encoding="utf-8")
            backup = cfg.with_name("config.bak-colabctl")
            if not backup.exists():
                atomic_write_private(backup, existing)

        directive = self.include_directive()
        new_content = f"{directive}\n\n{existing}" if existing else f"{directive}\n"
        atomic_write_private(cfg, new_content)
        return True

    def render_ssh_config(
        self,
        sessions: dict[str, LocalSessionMeta],
        settings: AppSettings,
    ) -> str:
        lines: list[str] = [MANAGED_HEADER]
        proxy_exe = shlex.quote(self.colabctl_bin)
        for name in sorted(sessions):
            meta = sessions[name]
            proxy_cmd = f"{proxy_exe} _proxy {shlex.quote(meta.name)}"
            block = [
                f"Host {meta.ssh_alias}",
                f"    HostName {meta.ssh_alias}.colabctl.local",
                "    User root",
                f"    IdentityFile {meta.identity_file}",
                "    IdentitiesOnly yes",
                f"    ProxyCommand {proxy_cmd}",
                "    StrictHostKeyChecking no",
                "    UserKnownHostsFile /dev/null",
                "    LogLevel ERROR",
                "    ServerAliveInterval 20",
                "    ServerAliveCountMax 3",
                "    ControlMaster auto",
                f"    ControlPath {meta.control_path}",
                f"    ControlPersist {settings.control_persist}",
                "",
            ]
            lines.extend(block)
        return "\n".join(lines).rstrip() + "\n"

    def sync_ssh_config(
        self,
        sessions: dict[str, LocalSessionMeta],
        settings: AppSettings,
    ) -> Path:
        self.paths.ensure_dirs()
        content = self.render_ssh_config(sessions, settings)
        atomic_write_private(self.paths.managed_ssh_config, content)
        return self.paths.managed_ssh_config

    def is_mux_active(self, alias: str, control_path: str) -> bool:
        sock = Path(control_path)
        if not sock.exists():
            return False
        res = subprocess.run(
            ["ssh", "-S", control_path, "-O", "check", alias],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return res.returncode == 0

    def warmup_mux(self, alias: str, control_path: str, *, timeout_s: int = 35) -> tuple[bool, str | None]:
        """Establish the ControlMaster socket in advance so concurrent SSH calls never race into 429.

        Uses a temp file (never a pipe) for stderr so the backgrounded ControlPersist
        master process cannot keep stdout/stderr pipes open and hang subprocess.run.
        """
        if self.is_mux_active(alias, control_path):
            return True, None
        import tempfile

        self.paths.ensure_dirs()
        with tempfile.TemporaryFile(mode="w+b") as err_file:
            try:
                proc = subprocess.run(
                    [
                        "ssh",
                        "-o",
                        "BatchMode=yes",
                        "-o",
                        f"ConnectTimeout={min(25, timeout_s)}",
                        "--",
                        alias,
                        "true",
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=err_file,
                    timeout=timeout_s,
                )
            except subprocess.TimeoutExpired:
                return False, f"SSH warmup timed out after {timeout_s}s"
            err_file.seek(0)
            err_msg = err_file.read().decode("utf-8", errors="replace").strip() or None
        return proc.returncode == 0, err_msg if proc.returncode != 0 else None

    def close_mux(self, alias: str, control_path: str) -> bool:
        """Close an active ControlMaster socket cleanly and unlink any stale socket."""
        sock = Path(control_path)
        closed = False
        if sock.exists():
            res = subprocess.run(
                ["ssh", "-S", control_path, "-O", "exit", alias],
                capture_output=True,
                text=True,
                timeout=8,
            )
            closed = res.returncode == 0
            if sock.exists():
                sock.unlink(missing_ok=True)
        return closed

    def build_interactive_ssh_argv(
        self,
        alias: str,
        remote_command: list[str] | None = None,
    ) -> list[str]:
        if remote_command:
            # OpenSSH joins extra args with spaces before handing them to the remote
            # shell. Preserve single-arg shell strings (e.g. 'ls | wc -l') verbatim
            # while quoting multi-arg invocations cleanly.
            cmd_str = (
                remote_command[0]
                if len(remote_command) == 1
                else shlex.join(remote_command)
            )
            return ["ssh", "--", alias, cmd_str]
        return [
            "ssh",
            "-t",
            "--",
            alias,
            'cd /content 2>/dev/null; exec "${SHELL:-/bin/bash}" -l',
        ]

    def exec_json_if_mux_active(
        self,
        alias: str,
        control_path: str,
        python_code: str,
        *,
        marker: str,
        timeout_s: int = 15,
    ) -> dict | None:
        """Run a short Python snippet over an already-active ControlMaster socket (no PTY).

        Returns parsed JSON dict on success, or None if mux is inactive or SSH fails
        so callers can seamlessly fall back to `colab-pool exec`.
        """
        import json

        if not self.is_mux_active(alias, control_path):
            return None
        try:
            proc = subprocess.run(
                [
                    "ssh",
                    "-T",
                    "-S",
                    control_path,
                    "-o",
                    "BatchMode=yes",
                    "--",
                    alias,
                    "python3 -",
                ],
                input=python_code,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        for line in reversed(proc.stdout.splitlines()):
            if line.startswith(marker):
                try:
                    data = json.loads(line[len(marker) :].strip())
                    if isinstance(data, dict):
                        return data
                except ValueError:
                    return None
        return None

    def build_tunnel_argv(
        self,
        alias: str,
        remote_port: int,
        local_port: int,
        *,
        bind_host: str = "127.0.0.1",
    ) -> list[str]:
        return [
            "ssh",
            "-N",
            "-o",
            "ExitOnForwardFailure=yes",
            "-L",
            f"{bind_host}:{local_port}:127.0.0.1:{remote_port}",
            alias,
        ]
