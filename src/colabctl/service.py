"""Core UI-agnostic controller orchestrating Colab accounts, sessions, SSH, and cost guards."""

from __future__ import annotations

import math
import os
import re
import time
from datetime import UTC, datetime
from typing import Any

from colabctl.config import (
    AppPaths,
    LocalStore,
    resolve_identity_file,
)
from colabctl.models import (
    VALID_GPUS,
    AccountInfo,
    DoctorReport,
    HardwareProbe,
    LocalSessionMeta,
    OrphanInstance,
    PoolOverview,
    PoolSessionView,
    QuotaSource,
    StopResult,
    TotalUsage,
    UpResult,
    WatchdogConfig,
    WatchdogLiveStatus,
    normalize_high_mem,
    resolve_account_quota,
)
from colabctl.pool_adapter import RESULT_MARKER, PoolAdapter, PoolAdapterError
from colabctl.ssh_manager import SshManager, control_socket_path
from colabctl.watchdog_manager import WatchdogManager

SESSION_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,47}$")


class ColabctlError(RuntimeError):
    """User-facing domain error from ColabController."""


def validate_session_name(name: str) -> str:
    if not SESSION_NAME_RE.fullmatch(name):
        raise ColabctlError(
            f"Invalid session name {name!r}. Use 1-48 chars of letters, digits, '.', '_' or '-'."
        )
    return name


def validate_gpu(gpu: str) -> str:
    norm = gpu.strip().lower()
    if norm not in VALID_GPUS:
        raise ColabctlError(
            f"Unsupported GPU {gpu!r}. Supported: {', '.join(VALID_GPUS)}."
        )
    return norm


def _extract_orphan_keys(raw: dict[str, Any]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for item in raw.get("orphans", []):
        acc = item.get("account")
        ep = item.get("endpoint")
        if acc and ep:
            keys.add((str(acc), str(ep)))
    return keys


class ColabController:
    """High-level controller designed to serve CLI, TUI, and Web backends equally."""

    def __init__(
        self,
        *,
        paths: AppPaths | None = None,
        pool: PoolAdapter | None = None,
        ssh: SshManager | None = None,
        watchdog: WatchdogManager | None = None,
    ) -> None:
        self.paths = paths or AppPaths()
        self.store = LocalStore(self.paths)
        self.pool = pool or PoolAdapter()
        self.ssh = ssh or SshManager(self.paths)
        self.watchdog = watchdog or WatchdogManager(
            self.pool, fast_exec=self._fast_ssh_exec_json
        )

    def _fast_ssh_exec_json(
        self, session_name: str, python_code: str
    ) -> dict[str, Any] | None:
        meta = self.store.get_session(session_name)
        if meta is None:
            return None
        return self.ssh.exec_json_if_mux_active(
            meta.ssh_alias,
            meta.control_path,
            python_code,
            marker=RESULT_MARKER,
        )

    # ------------------------------------------------------------------
    # Diagnostics & Overview
    # ------------------------------------------------------------------

    def doctor(self) -> DoctorReport:
        settings = self.store.load_settings()
        bins = self.pool.check_binaries()
        identity = resolve_identity_file(settings=settings, ssh_dir=self.paths.ssh_dir)
        included = self.ssh.is_included_in_user_ssh_config()

        issues: list[str] = []
        for tool, path in bins.items():
            if path is None:
                issues.append(f"Missing required executable: {tool}")
        if identity is None:
            issues.append(
                "No Ed25519/ECDSA SSH key found in ~/.ssh/ (run: ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_colab)."
            )
        if not included:
            issues.append(
                f"{self.paths.user_ssh_config} does not yet Include {self.paths.managed_ssh_config} (will be added automatically on first 'colabctl up')."
            )

        accounts_count = 0
        primary_account: str | None = None
        if bins.get("colab-pool"):
            try:
                raw = self.pool.list_raw(live=False)
                accounts_count = len(raw.get("accounts", []))
                primary_account = raw.get("primary")
                if accounts_count == 0:
                    issues.append(
                        "No Google Colab accounts configured. Run 'colab-account add <alias>'."
                    )
            except PoolAdapterError as exc:
                issues.append(f"Unable to query colab-pool: {exc}")

        return DoctorReport(
            ok=len(issues) == 0,
            binaries=bins,
            identity_file=str(identity) if identity else None,
            ssh_config_included=included,
            managed_ssh_config_path=str(self.paths.managed_ssh_config),
            accounts_count=accounts_count,
            primary_account=primary_account,
            issues=issues,
        )

    def list_overview(
        self,
        *,
        live: bool = False,
        probe_guard: bool = False,
    ) -> PoolOverview:
        raw = self.pool.list_raw(live=live)
        settings = self.store.load_settings()
        local_map = self.store.load_sessions()

        accounts: list[AccountInfo] = []
        for raw_acc in raw.get("accounts", []):
            acc = AccountInfo.model_validate(raw_acc)
            if acc.quota_cu is None:
                acc.quota_cu, acc.quota_source = resolve_account_quota(
                    acc.name, acc.balance, settings.account_quotas
                )
            accounts.append(acc)
        total = TotalUsage.model_validate(raw.get("total", {}))
        vanished_names: list[str] = []
        for v in raw.get("vanished", []):
            if isinstance(v, str):
                vanished_names.append(v)
            elif isinstance(v, dict) and v.get("name"):
                vanished_names.append(str(v["name"]))
        vanished_set = set(vanished_names)

        sessions: list[PoolSessionView] = []
        for entry in raw.get("sessions", []):
            name = str(entry["name"])
            meta = local_map.get(name)
            ssh_alias = meta.ssh_alias if meta else f"{settings.ssh_alias_prefix}{name}"
            ctl_path = meta.control_path if meta else str(control_socket_path(self.paths, name))
            mux_active = self.ssh.is_mux_active(ssh_alias, ctl_path)

            wd_live: WatchdogLiveStatus | None = None
            if probe_guard and name not in vanished_set:
                try:
                    wd_live = self.watchdog.get_status(name)
                except PoolAdapterError as exc:
                    wd_live = WatchdogLiveStatus(running=False, error=str(exc))

            sessions.append(
                PoolSessionView(
                    name=name,
                    account=str(entry.get("account", "")),
                    endpoint=entry.get("endpoint"),
                    accelerator=entry.get("accelerator")
                    or (meta.gpu_requested.upper() if meta else None),
                    ssh_alias=ssh_alias,
                    created_at=entry.get("created_at")
                    or (meta.created_at.isoformat() if meta else None),
                    hardware=meta.hardware if meta else None,
                    watchdog_config=meta.watchdog if meta else None,
                    watchdog_live=wd_live,
                    ssh_mux_active=mux_active,
                    vanished=name in vanished_set,
                )
            )

        orphans = [
            OrphanInstance(
                account=str(o.get("account", "")),
                endpoint=str(o.get("endpoint", "")),
                hardware=o.get("hardware"),
                name=o.get("name"),
            )
            for o in raw.get("orphans", [])
        ]

        return PoolOverview(
            primary=raw.get("primary"),
            active=raw.get("active"),
            threshold=raw.get("threshold"),
            usage_mode=str(raw.get("usage_mode", "cached")),
            accounts=accounts,
            total=total,
            sessions=sessions,
            orphans=orphans,
            vanished=vanished_names,
            errors=raw.get("errors", {}),
        )

    # ------------------------------------------------------------------
    # Provisioning & Hardware Probe
    # ------------------------------------------------------------------

    def probe_hardware(self, session_name: str) -> HardwareProbe:
        code = f"""
import json, os, socket, subprocess

MARKER = {RESULT_MARKER!r}
info = {{
    "gpu_name": None,
    "gpu_memory_mib": None,
    "driver_version": None,
    "ram_total": None,
    "cpu_cores": os.cpu_count(),
    "hostname": socket.gethostname(),
    "tbe_runtime_addr": os.environ.get("TBE_RUNTIME_ADDR"),
}}
try:
    out = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
        text=True, timeout=15
    ).strip()
    if out:
        parts = [p.strip() for p in out.splitlines()[0].split(",")]
        if len(parts) >= 1:
            info["gpu_name"] = parts[0]
        if len(parts) >= 2:
            info["gpu_memory_mib"] = int(float(parts[1]))
        if len(parts) >= 3:
            info["driver_version"] = parts[2]
except Exception:
    pass
try:
    lines = subprocess.check_output(["free", "-h"], text=True, timeout=10).splitlines()
    if len(lines) >= 2:
        cols = lines[1].split()
        if len(cols) >= 2:
            info["ram_total"] = cols[1]
except Exception:
    pass
print(MARKER + json.dumps(info))
"""
        data = self.pool.exec_json(session_name, code, timeout_s=30)
        return HardwareProbe.model_validate(data)

    def up(
        self,
        name: str,
        *,
        gpu: str | None = None,
        high_mem: bool = False,
        account: str | None = None,
        allow_other_account: bool = False,
        idle_minutes: int | None = None,
        max_hours: float | None = None,
        enable_guard: bool = True,
        identity_file: str | None = None,
        assign_timeout_s: int | None = None,
        assign_retries: int | None = None,
        reap_new_orphan_on_failure: bool = True,
        warmup_ssh: bool = True,
    ) -> UpResult:
        validate_session_name(name)
        settings = self.store.load_settings()
        gpu_norm = validate_gpu(gpu if gpu is not None else settings.default_gpu)
        eff_high_mem = normalize_high_mem(gpu_norm, high_mem)
        id_path = resolve_identity_file(
            explicit=identity_file,
            settings=settings,
            ssh_dir=self.paths.ssh_dir,
        )
        if id_path is None:
            raise ColabctlError(
                "No Ed25519/ECDSA SSH key found in ~/.ssh/. Generate one with: ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_colab"
            )

        # Snapshot pre-existing orphans and clean up vanished record if reusing a dead name
        pre_raw = self.pool.list_raw(live=False)
        vanished_names: set[str] = set()
        for v in pre_raw.get("vanished", []):
            if isinstance(v, str):
                vanished_names.add(v)
            elif isinstance(v, dict) and v.get("name"):
                vanished_names.add(str(v["name"]))
        existing_names = {str(s["name"]) for s in pre_raw.get("sessions", [])}
        if name in existing_names:
            if name in vanished_names:
                # Previous VM died (e.g. watchdog auto-stopped it); clean up stale entry.
                try:
                    self.pool.stop_session(name, forget=True)
                except PoolAdapterError:
                    pass
                self.store.delete_session(name)
            else:
                raise ColabctlError(
                    f"Session '{name}' already exists. Connect with 'colabctl ssh {name}', stop it first, or use 'colabctl switch {name} --gpu ...'."
                )
        pre_orphans = _extract_orphan_keys(pre_raw)

        # If caller explicitly names a non-primary account, pass allow_other_account automatically
        primary = pre_raw.get("primary")
        effective_allow_other = allow_other_account or bool(
            account and primary and account != primary
        )

        t0 = time.monotonic()
        try:
            self.pool.new_session(
                name,
                gpu=gpu_norm,
                high_mem=eff_high_mem,
                account=account,
                allow_other_account=effective_allow_other,
                assign_timeout_s=assign_timeout_s or settings.assign_timeout_s,
                assign_retries=assign_retries
                if assign_retries is not None
                else settings.assign_retries,
            )
        except PoolAdapterError as exc:
            reaped_note = ""
            if reap_new_orphan_on_failure:
                reaped = self._reap_newly_created_orphans(pre_orphans)
                if reaped:
                    reaped_note = (
                        f" (Auto-reaped {len(reaped)} newly leaked orphan VM(s): "
                        + ", ".join(f"{acc}:{ep}" for acc, ep in reaped)
                        + ")"
                    )
            raise ColabctlError(f"{exc}{reaped_note}") from exc
        elapsed = round(time.monotonic() - t0, 2)

        # Discover assigned account + endpoint from pool registry
        post_raw = self.pool.list_raw(live=False)
        pool_entry = next(
            (s for s in post_raw.get("sessions", []) if s.get("name") == name),
            None,
        )
        assigned_account = (
            str(pool_entry["account"])
            if pool_entry
            else (account or str(post_raw.get("primary") or ""))
        )
        endpoint = pool_entry.get("endpoint") if pool_entry else None

        # Probe real hardware & TBE_RUNTIME_ADDR
        hardware: HardwareProbe | None = None
        try:
            hardware = self.probe_hardware(name)
        except PoolAdapterError:
            hardware = None

        # Deploy VM-side cost-guard watchdog
        eff_idle_min = (
            settings.default_idle_min if idle_minutes is None else idle_minutes
        )
        eff_max_hours = settings.default_max_hours if max_hours is None else max_hours
        wd_config = WatchdogConfig(
            enabled=enable_guard,
            idle_timeout_s=(eff_idle_min * 60) if eff_idle_min > 0 else None,
            max_duration_s=int(eff_max_hours * 3600) if eff_max_hours > 0 else None,
        )
        wd_live: WatchdogLiveStatus | None = None
        wd_deployed = False
        wd_error: str | None = None
        if enable_guard:
            try:
                wd_live = self.watchdog.deploy(name, wd_config)
                wd_deployed = bool(wd_live.running)
                if wd_live.deadline_epoch is not None:
                    wd_config.deadline_epoch = wd_live.deadline_epoch
                if not wd_deployed:
                    wd_error = wd_live.error or "Watchdog process did not stay running"
            except PoolAdapterError as exc:
                wd_error = str(exc)

        ssh_alias = f"{settings.ssh_alias_prefix}{name}"
        ctl_path = str(control_socket_path(self.paths, name))
        meta = LocalSessionMeta(
            name=name,
            ssh_alias=ssh_alias,
            account=assigned_account,
            endpoint=endpoint,
            gpu_requested=gpu_norm,
            high_mem=eff_high_mem,
            identity_file=str(id_path),
            control_path=ctl_path,
            created_at=datetime.now(UTC),
            hardware=hardware,
            watchdog=wd_config,
        )
        self.store.upsert_session(meta)

        self.ssh.ensure_user_ssh_include()
        cfg_path = self.ssh.sync_ssh_config(self.store.load_sessions(), settings)

        # Warm up the single ControlMaster socket so immediate concurrent SSH/VS Code/tunnel calls never hit 429
        mux_ready = False
        if warmup_ssh:
            mux_ready, _ = self.ssh.warmup_mux(ssh_alias, ctl_path)

        view = PoolSessionView(
            name=name,
            account=assigned_account,
            endpoint=endpoint,
            accelerator=(
                pool_entry.get("accelerator")
                if pool_entry and pool_entry.get("accelerator")
                else gpu_norm.upper()
            ),
            ssh_alias=ssh_alias,
            created_at=meta.created_at.isoformat(),
            hardware=hardware,
            watchdog_config=wd_config,
            watchdog_live=wd_live,
            ssh_mux_active=mux_ready,
        )
        return UpResult(
            session=view,
            allocate_seconds=elapsed,
            ssh_command=f"ssh {ssh_alias}",
            ssh_config_path=str(cfg_path),
            watchdog_deployed=wd_deployed,
            watchdog_error=wd_error,
        )

    def _reap_newly_created_orphans(
        self, pre_orphans: set[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        reaped: list[tuple[str, str]] = []
        try:
            post_raw = self.pool.list_raw(live=False)
        except PoolAdapterError:
            return reaped
        new_orphans = _extract_orphan_keys(post_raw) - pre_orphans
        for acc, ep in sorted(new_orphans):
            try:
                self.pool.reap_orphan(acc, ep)
                reaped.append((acc, ep))
            except PoolAdapterError:
                continue
        return reaped

    # ------------------------------------------------------------------
    # Session Inspection, Guard Management & Recovery
    # ------------------------------------------------------------------

    def status(self, name: str) -> PoolSessionView:
        validate_session_name(name)
        overview = self.list_overview(live=False, probe_guard=False)
        session = next((s for s in overview.sessions if s.name == name), None)
        if session is None:
            raise ColabctlError(
                f"Session '{name}' not found. Run 'colabctl ls' to inspect active sessions."
            )
        if not session.vanished:
            try:
                session.watchdog_live = self.watchdog.get_status(name)
            except PoolAdapterError as exc:
                session.watchdog_live = WatchdogLiveStatus(running=False, error=str(exc))
            if session.hardware is None:
                try:
                    session.hardware = self.probe_hardware(name)
                except PoolAdapterError:
                    pass
        return session

    def extend(
        self,
        name: str,
        *,
        add_hours: float = 2.0,
        idle_minutes: int | None = None,
    ) -> WatchdogLiveStatus:
        validate_session_name(name)
        if add_hours <= 0:
            raise ColabctlError("--hours must be greater than 0.")
        try:
            status = self.watchdog.update(
                name, add_hours=add_hours, idle_minutes=idle_minutes, enable=True
            )
        except PoolAdapterError as exc:
            raise ColabctlError(str(exc)) from exc
        meta = self.store.get_session(name)
        if meta:
            meta.watchdog.enabled = True
            if status.deadline_epoch is not None:
                meta.watchdog.deadline_epoch = status.deadline_epoch
            if idle_minutes is not None:
                meta.watchdog.idle_timeout_s = (
                    idle_minutes * 60 if idle_minutes > 0 else None
                )
            self.store.upsert_session(meta)
        return status

    def configure_guard(
        self,
        name: str,
        *,
        idle_minutes: int | None = None,
        max_hours: float | None = None,
        disable: bool = False,
        enable: bool = False,
    ) -> WatchdogLiveStatus:
        validate_session_name(name)
        if disable and enable:
            raise ColabctlError("Cannot pass both --off and --on.")
        try:
            if not disable and not enable and idle_minutes is None and max_hours is None:
                return self.watchdog.get_status(name)
            status = self.watchdog.update(
                name,
                max_hours_from_now=max_hours,
                idle_minutes=idle_minutes,
                disable=disable,
                enable=enable,
            )
        except PoolAdapterError as exc:
            raise ColabctlError(str(exc)) from exc
        meta = self.store.get_session(name)
        if meta:
            if disable:
                meta.watchdog.enabled = False
            if enable:
                meta.watchdog.enabled = True
            if status.deadline_epoch is not None:
                meta.watchdog.deadline_epoch = status.deadline_epoch
            if idle_minutes is not None:
                meta.watchdog.idle_timeout_s = (
                    idle_minutes * 60 if idle_minutes > 0 else None
                )
            self.store.upsert_session(meta)
        return status

    def reset_ssh(self, name: str) -> dict[str, Any]:
        """Close local ControlMaster socket and clear orphaned remote sshd child sessions."""
        validate_session_name(name)
        settings = self.store.load_settings()
        meta = self.store.get_session(name)
        alias = meta.ssh_alias if meta else f"{settings.ssh_alias_prefix}{name}"
        ctl = meta.control_path if meta else str(control_socket_path(self.paths, name))
        mux_closed = self.ssh.close_mux(alias, ctl)

        # Terminate only child sshd session processes (not the main listening daemon)
        code = f"""
import json, os, signal, subprocess

MARKER = {RESULT_MARKER!r}
killed = []
try:
    out = subprocess.check_output(["ps", "-eo", "pid,ppid,args"], text=True)
    for line in out.splitlines()[1:]:
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        pid, ppid, cmd = int(parts[0]), int(parts[1]), parts[2]
        if cmd.startswith("sshd: root") or ("sshd:" in cmd and "[priv]" in cmd):
            try:
                os.kill(pid, signal.SIGTERM)
                killed.append({{"pid": pid, "cmd": cmd}})
            except OSError:
                pass
except Exception as exc:
    print(MARKER + json.dumps({{"killed": killed, "error": str(exc)}}))
else:
    print(MARKER + json.dumps({{"killed": killed}}))
"""
        try:
            remote = self.pool.exec_json(name, code, timeout_s=45)
        except PoolAdapterError as exc:
            raise ColabctlError(str(exc)) from exc
        return {
            "name": name,
            "local_mux_closed": mux_closed,
            "remote_sessions_terminated": remote.get("killed", []),
            "error": remote.get("error"),
        }

    # ------------------------------------------------------------------
    # Teardown, Switching, Reaping & Proxy
    # ------------------------------------------------------------------

    def stop(self, name: str, *, forget: bool = False) -> StopResult:
        validate_session_name(name)
        settings = self.store.load_settings()
        meta = self.store.get_session(name)
        alias = meta.ssh_alias if meta else f"{settings.ssh_alias_prefix}{name}"
        ctl = meta.control_path if meta else str(control_socket_path(self.paths, name))

        mux_closed = self.ssh.close_mux(alias, ctl)

        stopped = True
        message = f"Session '{name}' stopped."
        try:
            self.pool.stop_session(name, forget=forget)
        except PoolAdapterError as exc:
            if "is not in the pool" in str(exc):
                stopped = False
                message = f"Session '{name}' was already absent from colab-pool; cleaned local metadata."
            else:
                raise ColabctlError(str(exc)) from exc

        removed = self.store.delete_session(name)
        self.ssh.sync_ssh_config(self.store.load_sessions(), settings)
        return StopResult(
            name=name,
            stopped=stopped,
            mux_closed=mux_closed,
            ssh_config_removed=removed,
            message=message,
        )

    def stop_all(self) -> list[StopResult]:
        settings = self.store.load_settings()
        local_map = self.store.load_sessions()
        results: list[StopResult] = []
        for name, meta in list(local_map.items()):
            mux_closed = self.ssh.close_mux(meta.ssh_alias, meta.control_path)
            results.append(
                StopResult(
                    name=name,
                    stopped=True,
                    mux_closed=mux_closed,
                    ssh_config_removed=True,
                    message=f"Closed local mux for '{name}'",
                )
            )
        try:
            self.pool.stop_all()
        except PoolAdapterError as exc:
            raise ColabctlError(str(exc)) from exc

        self.store.save_sessions({})
        self.ssh.sync_ssh_config({}, settings)
        return results

    def switch(
        self,
        name: str,
        *,
        gpu: str,
        high_mem: bool = False,
        account: str | None = None,
        idle_minutes: int | None = None,
        max_hours: float | None = None,
        enable_guard: bool = True,
        identity_file: str | None = None,
    ) -> UpResult:
        """Stop an existing session and re-provision it under the same name & SSH alias."""
        validate_session_name(name)
        validate_gpu(gpu)
        old_meta = self.store.get_session(name)
        if identity_file is None and old_meta is not None:
            identity_file = old_meta.identity_file
        self.stop(name)
        return self.up(
            name,
            gpu=gpu,
            high_mem=high_mem,
            account=account,
            idle_minutes=idle_minutes,
            max_hours=max_hours,
            enable_guard=enable_guard,
            identity_file=identity_file,
        )

    def reap_orphan(self, account: str, endpoint: str) -> None:
        try:
            self.pool.reap_orphan(account, endpoint)
        except PoolAdapterError as exc:
            raise ColabctlError(str(exc)) from exc

    def reap_all_orphans(self) -> list[OrphanInstance]:
        overview = self.list_overview(live=False)
        reaped: list[OrphanInstance] = []
        for orphan in overview.orphans:
            self.reap_orphan(orphan.account, orphan.endpoint)
            reaped.append(orphan)
        return reaped

    def set_primary(self, account: str, *, threshold: float | None = None) -> None:
        try:
            self.pool.set_primary(account, threshold=threshold)
        except PoolAdapterError as exc:
            raise ColabctlError(str(exc)) from exc

    def set_account_quota(
        self, account: str, quota_cu: float | None
    ) -> tuple[float, QuotaSource]:
        """Persist or clear a per-account cycle CU quota override in settings.json."""
        name = account.strip()
        if not name:
            raise ColabctlError("Account name cannot be empty.")
        settings = self.store.load_settings()
        if quota_cu is None:
            settings.account_quotas.pop(name, None)
        else:
            val = float(quota_cu)
            if not math.isfinite(val) or val <= 0:
                raise ColabctlError("Quota must be a positive number of Compute Units.")
            settings.account_quotas[name] = round(val, 2)
        self.store.save_settings(settings)

        balance: float | None = None
        try:
            raw = self.pool.list_raw(live=False)
            for item in raw.get("accounts", []):
                if item.get("name") == name and item.get("balance") is not None:
                    balance = float(item["balance"])
                    break
        except (PoolAdapterError, ValueError, TypeError):
            pass
        return resolve_account_quota(name, balance, settings.account_quotas)

    def resolve_ssh_target(self, name: str) -> LocalSessionMeta:
        validate_session_name(name)
        meta = self.store.get_session(name)
        if meta is not None:
            return meta
        # Check if session exists in colab-pool (created externally); sync SSH config on the fly
        overview = self.list_overview(live=False)
        match = next((s for s in overview.sessions if s.name == name), None)
        if match is None:
            raise ColabctlError(
                f"Session '{name}' is not running. Create one with 'colabctl up {name} --gpu t4'."
            )
        settings = self.store.load_settings()
        id_path = resolve_identity_file(settings=settings, ssh_dir=self.paths.ssh_dir)
        if id_path is None:
            raise ColabctlError("No Ed25519/ECDSA SSH key found in ~/.ssh/.")
        meta = LocalSessionMeta(
            name=name,
            ssh_alias=f"{settings.ssh_alias_prefix}{name}",
            account=match.account,
            endpoint=match.endpoint,
            gpu_requested=(match.accelerator or "none").lower(),
            identity_file=str(id_path),
            control_path=str(control_socket_path(self.paths, name)),
            created_at=datetime.now(UTC),
        )
        self.store.upsert_session(meta)
        self.ssh.ensure_user_ssh_include()
        self.ssh.sync_ssh_config(self.store.load_sessions(), settings)
        return meta

    def exec_proxy(self, name: str) -> None:
        """OpenSSH ProxyCommand entrypoint. Never implicitly provisions a VM."""
        validate_session_name(name)
        settings = self.store.load_settings()
        meta = self.store.get_session(name)
        id_path = resolve_identity_file(
            explicit=meta.identity_file if meta else None,
            settings=settings,
            ssh_dir=self.paths.ssh_dir,
        )
        if id_path is None:
            raise ColabctlError("No Ed25519/ECDSA SSH key found in ~/.ssh/.")
        argv = self.pool.build_proxy_argv(name, str(id_path))
        os.execvp(argv[0], argv)
