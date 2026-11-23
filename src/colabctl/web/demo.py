"""Safe zero-CU in-memory demo controller for `colabctl ui --demo`."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from colabctl.models import (
    AccountInfo,
    DoctorReport,
    HardwareProbe,
    LocalSessionMeta,
    OrphanInstance,
    PoolOverview,
    PoolSessionView,
    StopResult,
    TotalUsage,
    UpResult,
    WatchdogConfig,
    WatchdogLiveStatus,
    normalize_high_mem,
)
from colabctl.service import ColabctlError, validate_gpu, validate_session_name

_GPU_SPECS: dict[str, tuple[str, int, str, int, float]] = {
    # gpu_key -> (gpu_name, vram_mib, ram_normal/high, cores, cu_per_hr)
    "none": ("CPU Only", 0, "12Gi", 2, 0.08),
    "t4": ("Tesla T4", 15360, "12Gi", 2, 1.96),
    "l4": ("NVIDIA L4", 23034, "53Gi", 12, 4.82),
    "g4": ("NVIDIA RTX PRO 6000", 98304, "167Gi", 12, 9.60),
    "a100": ("NVIDIA A100-SXM4-80GB", 81920, "83Gi", 12, 11.77),
    "h100": ("NVIDIA H100 80GB HBM3", 81920, "167Gi", 24, 15.40),
}


@dataclass
class _DemoSession:
    name: str
    account: str
    endpoint: str
    gpu_key: str
    high_mem: bool
    created_at: datetime
    hardware: HardwareProbe
    watchdog: WatchdogConfig
    started_epoch: float
    last_active_epoch: float
    gpu_util_percent: float = 18.0
    last_active_reason: str = "ssh_pty_io"
    ssh_mux_active: bool = True
    pid: int = 4102


@dataclass
class _DemoAccount:
    name: str
    email: str
    balance: float
    disabled: bool = False
    disabled_reason: str | None = None


class DemoColabController:
    """In-memory stand-in for ColabController with realistic ticking watchdogs & 0 CU cost."""

    def __init__(self, *, simulated_delay_s: float = 0.45) -> None:
        self._lock = threading.Lock()
        self._delay = simulated_delay_s
        self._primary = "ultra"
        self._threshold = 5.0
        self._ep_seq = 100
        self._accounts: dict[str, _DemoAccount] = {
            "ultra": _DemoAccount(
                name="ultra",
                email="ultra@example.com",
                balance=2500.00,
            ),
            "pro1": _DemoAccount(
                name="pro1",
                email="pro1@example.com",
                balance=222.52,
            ),
            "pro2": _DemoAccount(
                name="pro2",
                email="pro2@example.com",
                balance=200.00,
            ),
        }
        now = time.time()
        self._sessions: dict[str, _DemoSession] = {
            "dev": _DemoSession(
                name="dev",
                account="ultra",
                endpoint="m-s-demo-t4-01",
                gpu_key="t4",
                high_mem=False,
                created_at=datetime.fromtimestamp(now - 2460, tz=UTC),
                hardware=HardwareProbe(
                    gpu_name="Tesla T4",
                    gpu_memory_mib=15360,
                    driver_version="580.82.07",
                    ram_total="12Gi",
                    cpu_cores=2,
                    hostname="colab-demo-t4",
                    tbe_runtime_addr="172.28.0.1:8011",
                ),
                watchdog=WatchdogConfig(
                    enabled=True,
                    idle_timeout_s=1800,
                    max_duration_s=14400,
                    deadline_epoch=now + 11940,
                ),
                started_epoch=now - 2460,
                last_active_epoch=now - 210,
                gpu_util_percent=36.5,
                last_active_reason="gpu_busy:36.5%",
                ssh_mux_active=True,
                pid=4102,
            ),
            "train-h3": _DemoSession(
                name="train-h3",
                account="pro1",
                endpoint="m-s-demo-a100-02",
                gpu_key="a100",
                high_mem=True,
                created_at=datetime.fromtimestamp(now - 1800, tz=UTC),
                hardware=HardwareProbe(
                    gpu_name="NVIDIA A100-SXM4-80GB",
                    gpu_memory_mib=81920,
                    driver_version="580.82.07",
                    ram_total="167Gi",
                    cpu_cores=12,
                    hostname="colab-demo-a100",
                    tbe_runtime_addr="172.28.0.1:8011",
                ),
                watchdog=WatchdogConfig(
                    enabled=True,
                    idle_timeout_s=1800,
                    max_duration_s=21600,
                    deadline_epoch=now + 19800,
                ),
                started_epoch=now - 1800,
                last_active_epoch=now - 18,
                gpu_util_percent=92.4,
                last_active_reason="gpu_busy:92.4%",
                ssh_mux_active=True,
                pid=5388,
            ),
        }
        self._orphans: list[OrphanInstance] = [
            OrphanInstance(
                account="pro2",
                endpoint="m-s-orphan-t4-9x",
                hardware="Tesla T4",
                name=None,
            )
        ]

    def _sleep(self) -> None:
        if self._delay > 0:
            time.sleep(self._delay)

    def _build_wd_live(self, s: _DemoSession) -> WatchdogLiveStatus:
        now = time.time()
        if not s.watchdog.enabled:
            return WatchdogLiveStatus(
                running=False,
                pid=None,
                started_epoch=s.started_epoch,
                updated_epoch=now,
                deadline_epoch=s.watchdog.deadline_epoch,
                remaining_deadline_s=None,
                idle_timeout_s=s.watchdog.idle_timeout_s,
                idle_for_s=max(0.0, now - s.last_active_epoch),
                remaining_idle_s=None,
                gpu_util_percent=s.gpu_util_percent,
                last_active_reason=s.last_active_reason,
                active_ptys=1 if s.ssh_mux_active else 0,
                cancelled=True,
            )
        idle_for = max(0.0, now - s.last_active_epoch)
        rem_idle = (
            max(0.0, float(s.watchdog.idle_timeout_s) - idle_for)
            if s.watchdog.idle_timeout_s
            else None
        )
        rem_dead = (
            max(0.0, float(s.watchdog.deadline_epoch) - now)
            if s.watchdog.deadline_epoch
            else None
        )
        return WatchdogLiveStatus(
            running=True,
            pid=s.pid,
            started_epoch=s.started_epoch,
            updated_epoch=now,
            deadline_epoch=s.watchdog.deadline_epoch,
            remaining_deadline_s=rem_dead,
            idle_timeout_s=s.watchdog.idle_timeout_s,
            idle_for_s=idle_for,
            remaining_idle_s=rem_idle,
            gpu_util_percent=s.gpu_util_percent,
            last_active_reason=s.last_active_reason,
            active_ptys=1 if s.ssh_mux_active else 0,
            cancelled=False,
        )

    def _session_view(self, s: _DemoSession, *, include_live: bool = True) -> PoolSessionView:
        return PoolSessionView(
            name=s.name,
            account=s.account,
            endpoint=s.endpoint,
            accelerator=s.gpu_key.upper() if s.gpu_key != "none" else "CPU",
            ssh_alias=f"colab-{s.name}",
            created_at=s.created_at.isoformat(),
            hardware=s.hardware.model_copy(deep=True),
            watchdog_config=s.watchdog.model_copy(deep=True),
            watchdog_live=self._build_wd_live(s) if include_live else None,
            ssh_mux_active=s.ssh_mux_active,
            vanished=False,
        )

    def doctor(self) -> DoctorReport:
        with self._lock:
            return DoctorReport(
                ok=True,
                binaries={
                    "colab": "/Users/demo/.local/bin/colab",
                    "colab-pool": "/Users/demo/.local/bin/colab-pool",
                    "colab-account": "/Users/demo/.local/bin/colab-account",
                    "ssh": "/usr/bin/ssh",
                },
                identity_file="/Users/demo/.ssh/id_ed25519_colab",
                ssh_config_included=True,
                managed_ssh_config_path="/Users/demo/.config/colabctl/ssh_config",
                accounts_count=len(self._accounts),
                primary_account=self._primary,
                issues=[],
            )

    def list_overview(
        self,
        *,
        live: bool = False,
        probe_guard: bool = False,
    ) -> PoolOverview:
        if live:
            self._sleep()
        with self._lock:
            accounts: list[AccountInfo] = []
            total_balance = 0.0
            total_rate = 0.0
            total_assignments = 0
            fetched_iso = datetime.now(UTC).isoformat()

            for acc in self._accounts.values():
                acc_sessions = [s for s in self._sessions.values() if s.account == acc.name]
                acc_orphans = [o for o in self._orphans if o.account == acc.name]
                rate = sum(_GPU_SPECS.get(s.gpu_key, _GPU_SPECS["t4"])[4] for s in acc_sessions)
                rate += len(acc_orphans) * 1.96
                assignments = len(acc_sessions) + len(acc_orphans)
                hrs_rem = (acc.balance / rate) if rate > 0 else None
                accounts.append(
                    AccountInfo(
                        name=acc.name,
                        email=acc.email,
                        balance=round(acc.balance, 2),
                        hourly_rate=round(rate, 2),
                        hours_remaining=round(hrs_rem, 1) if hrs_rem is not None else None,
                        assignments=assignments,
                        usage_fetched_at=fetched_iso,
                        pool_sessions=len(acc_sessions),
                        primary=(acc.name == self._primary),
                        active=(acc.name == self._primary),
                        disabled=acc.disabled,
                        disabled_reason=acc.disabled_reason,
                    )
                )
                total_balance += acc.balance
                total_rate += rate
                total_assignments += assignments

            total_hrs = (total_balance / total_rate) if total_rate > 0 else None
            sessions = [
                self._session_view(s, include_live=True)
                for s in self._sessions.values()
            ]
            return PoolOverview(
                primary=self._primary,
                active=self._primary,
                threshold=self._threshold,
                usage_mode="live" if live else "demo",
                accounts=accounts,
                total=TotalUsage(
                    balance=round(total_balance, 2),
                    hourly_rate=round(total_rate, 2),
                    hours_remaining=round(total_hrs, 1) if total_hrs is not None else None,
                    assignments=total_assignments,
                    accounts_with_usage=len(accounts),
                    account_count=len(accounts),
                    complete=True,
                ),
                sessions=sessions,
                orphans=[o.model_copy(deep=True) for o in self._orphans],
                vanished=[],
                errors={},
            )

    def up(
        self,
        name: str,
        *,
        gpu: str | None = None,
        high_mem: bool = False,
        account: str | None = None,
        idle_minutes: int | None = None,
        max_hours: float | None = None,
        enable_guard: bool = True,
        **_kwargs: Any,
    ) -> UpResult:
        validate_session_name(name)
        gpu_norm = validate_gpu(gpu or "t4")
        eff_high_mem = normalize_high_mem(gpu_norm, high_mem)
        self._sleep()
        with self._lock:
            if name in self._sessions:
                raise ColabctlError(
                    f"Session '{name}' already exists. Stop it first or use Switch GPU."
                )
            acc = account or self._primary
            if acc not in self._accounts:
                raise ColabctlError(f"Account '{acc}' not found.")
            self._ep_seq += 1
            gpu_name, vram, ram_base, cores, _rate = _GPU_SPECS[gpu_norm]
            ram = "167Gi" if eff_high_mem and gpu_norm in ("a100", "h100") else (
                "51Gi" if eff_high_mem else ram_base
            )
            now = time.time()
            eff_idle = 30 if idle_minutes is None else idle_minutes
            eff_max = 4.0 if max_hours is None else max_hours
            deadline = (now + eff_max * 3600.0) if (enable_guard and eff_max > 0) else None
            wd_cfg = WatchdogConfig(
                enabled=enable_guard,
                idle_timeout_s=(eff_idle * 60) if eff_idle > 0 else None,
                max_duration_s=int(eff_max * 3600) if eff_max > 0 else None,
                deadline_epoch=deadline,
            )
            sess = _DemoSession(
                name=name,
                account=acc,
                endpoint=f"m-s-demo-{gpu_norm}-{self._ep_seq}",
                gpu_key=gpu_norm,
                high_mem=eff_high_mem,
                created_at=datetime.now(UTC),
                hardware=HardwareProbe(
                    gpu_name=gpu_name if gpu_norm != "none" else None,
                    gpu_memory_mib=vram or None,
                    driver_version="580.82.07" if gpu_norm != "none" else None,
                    ram_total=ram,
                    cpu_cores=cores,
                    hostname=f"colab-demo-{name}",
                    tbe_runtime_addr="172.28.0.1:8011",
                ),
                watchdog=wd_cfg,
                started_epoch=now,
                last_active_epoch=now,
                gpu_util_percent=4.0 if gpu_norm != "none" else 0.0,
                last_active_reason="startup",
                ssh_mux_active=True,
                pid=4000 + self._ep_seq,
            )
            self._sessions[name] = sess
            view = self._session_view(sess, include_live=True)
            return UpResult(
                session=view,
                allocate_seconds=1.2,
                ssh_command=f"ssh colab-{name}",
                ssh_config_path="/Users/demo/.config/colabctl/ssh_config",
                watchdog_deployed=enable_guard,
                watchdog_error=None,
            )

    def status(self, name: str) -> PoolSessionView:
        validate_session_name(name)
        with self._lock:
            sess = self._sessions.get(name)
            if sess is None:
                raise ColabctlError(f"Session '{name}' not found.")
            return self._session_view(sess, include_live=True)

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
        with self._lock:
            sess = self._sessions.get(name)
            if sess is None:
                raise ColabctlError(f"Session '{name}' not found.")
            now = time.time()
            sess.watchdog.enabled = True
            base = max(now, sess.watchdog.deadline_epoch or now)
            sess.watchdog.deadline_epoch = base + add_hours * 3600.0
            if idle_minutes is not None:
                sess.watchdog.idle_timeout_s = idle_minutes * 60 if idle_minutes > 0 else None
            sess.last_active_epoch = now
            sess.last_active_reason = "heartbeat_extend"
            return self._build_wd_live(sess)

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
        with self._lock:
            sess = self._sessions.get(name)
            if sess is None:
                raise ColabctlError(f"Session '{name}' not found.")
            now = time.time()
            if disable:
                sess.watchdog.enabled = False
            if enable:
                sess.watchdog.enabled = True
            if idle_minutes is not None:
                sess.watchdog.idle_timeout_s = idle_minutes * 60 if idle_minutes > 0 else None
            if max_hours is not None:
                sess.watchdog.max_duration_s = int(max_hours * 3600) if max_hours > 0 else None
                sess.watchdog.deadline_epoch = (now + max_hours * 3600.0) if max_hours > 0 else None
            sess.last_active_epoch = now
            sess.last_active_reason = "guard_updated"
            return self._build_wd_live(sess)

    def reset_ssh(self, name: str) -> dict[str, Any]:
        validate_session_name(name)
        self._sleep()
        with self._lock:
            sess = self._sessions.get(name)
            if sess is None:
                raise ColabctlError(f"Session '{name}' not found.")
            sess.ssh_mux_active = True
            return {
                "name": name,
                "local_mux_closed": True,
                "remote_sessions_terminated": [{"pid": 18291, "cmd": "sshd: root@pts/0"}],
                "rewarmed": True,
                "rewarm_error": None,
                "error": None,
            }

    def stop(self, name: str, *, forget: bool = False) -> StopResult:
        validate_session_name(name)
        self._sleep()
        with self._lock:
            existed = self._sessions.pop(name, None) is not None
            return StopResult(
                name=name,
                stopped=existed,
                mux_closed=existed,
                ssh_config_removed=existed,
                message=(
                    f"Session '{name}' stopped (demo)."
                    if existed
                    else f"Session '{name}' was already absent."
                ),
            )

    def stop_all(self) -> list[StopResult]:
        self._sleep()
        with self._lock:
            names = list(self._sessions.keys())
            self._sessions.clear()
            self._orphans.clear()
            return [
                StopResult(
                    name=n,
                    stopped=True,
                    mux_closed=True,
                    ssh_config_removed=True,
                    message=f"Stopped '{n}' (demo).",
                )
                for n in names
            ]

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
    ) -> UpResult:
        self.stop(name)
        return self.up(
            name,
            gpu=gpu,
            high_mem=high_mem,
            account=account,
            idle_minutes=idle_minutes,
            max_hours=max_hours,
            enable_guard=enable_guard,
        )

    def reap_orphan(self, account: str, endpoint: str) -> None:
        self._sleep()
        with self._lock:
            before = len(self._orphans)
            self._orphans = [
                o
                for o in self._orphans
                if not (o.account == account and o.endpoint == endpoint)
            ]
            if len(self._orphans) == before:
                raise ColabctlError(f"Orphan {account}:{endpoint} not found.")

    def reap_all_orphans(self) -> list[OrphanInstance]:
        self._sleep()
        with self._lock:
            reaped = [o.model_copy(deep=True) for o in self._orphans]
            self._orphans.clear()
            return reaped

    def set_primary(self, account: str, *, threshold: float | None = None) -> None:
        with self._lock:
            if account not in self._accounts:
                raise ColabctlError(f"Account '{account}' not found.")
            self._primary = account
            if threshold is not None:
                self._threshold = threshold

    def resolve_ssh_target(self, name: str) -> LocalSessionMeta:
        validate_session_name(name)
        with self._lock:
            sess = self._sessions.get(name)
            if sess is None:
                raise ColabctlError(f"Session '{name}' is not running.")
            return LocalSessionMeta(
                name=sess.name,
                ssh_alias=f"colab-{sess.name}",
                account=sess.account,
                endpoint=sess.endpoint,
                gpu_requested=sess.gpu_key,
                high_mem=sess.high_mem,
                identity_file="/Users/demo/.ssh/id_ed25519_colab",
                control_path=f"/tmp/colabctl-demo-{sess.name}.sock",
                created_at=sess.created_at,
                hardware=sess.hardware.model_copy(deep=True),
                watchdog=sess.watchdog.model_copy(deep=True),
            )
