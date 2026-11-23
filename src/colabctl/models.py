"""Typed data models shared across the core service, CLI, and future TUI/Web UI."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

GpuType = Literal["none", "t4", "l4", "g4", "a100", "h100"]
VALID_GPUS: tuple[str, ...] = ("none", "t4", "l4", "g4", "a100", "h100")
# Accelerators that only offer a single fixed host shape on Colab; passing
# `--high-mem` (`shape=hm`) is ignored for L4 and rejected with HTTP 400 for G4.
SINGLE_SHAPE_GPUS: tuple[str, ...] = ("l4", "g4")


def normalize_high_mem(gpu: str, high_mem: bool) -> bool:
    """Return effective high_mem flag, stripping it for single-shape GPUs."""
    if not high_mem:
        return False
    return gpu.strip().lower() not in SINGLE_SHAPE_GPUS


class AccountInfo(BaseModel):
    name: str
    email: str | None = None
    balance: float | None = None
    hourly_rate: float | None = None
    hours_remaining: float | None = None
    assignments: int | None = None
    usage_fetched_at: str | None = None
    pool_sessions: int = 0
    primary: bool = False
    active: bool = False
    disabled: bool = False
    disabled_reason: str | None = None


class TotalUsage(BaseModel):
    balance: float | None = None
    hourly_rate: float | None = None
    hours_remaining: float | None = None
    assignments: int | None = None
    accounts_with_usage: int = 0
    account_count: int = 0
    complete: bool = False


class HardwareProbe(BaseModel):
    gpu_name: str | None = None
    gpu_memory_mib: int | None = None
    driver_version: str | None = None
    ram_total: str | None = None
    cpu_cores: int | None = None
    hostname: str | None = None
    tbe_runtime_addr: str | None = None


class WatchdogConfig(BaseModel):
    enabled: bool = True
    idle_timeout_s: int | None = 1800  # 30 minutes
    max_duration_s: int | None = 14400  # 4 hours
    deadline_epoch: float | None = None
    gpu_busy_percent: float = 5.0
    poll_s: int = 15
    warn_before_s: int = 120


class WatchdogLiveStatus(BaseModel):
    running: bool = False
    pid: int | None = None
    started_epoch: float | None = None
    updated_epoch: float | None = None
    deadline_epoch: float | None = None
    remaining_deadline_s: float | None = None
    idle_timeout_s: int | None = None
    idle_for_s: float | None = None
    remaining_idle_s: float | None = None
    gpu_util_percent: float | None = None
    last_active_reason: str | None = None
    active_ptys: int = 0
    cancelled: bool = False
    error: str | None = None


class LocalSessionMeta(BaseModel):
    name: str
    ssh_alias: str
    account: str
    endpoint: str | None = None
    gpu_requested: str = "t4"
    high_mem: bool = False
    identity_file: str
    control_path: str
    created_at: datetime
    hardware: HardwareProbe | None = None
    watchdog: WatchdogConfig = Field(default_factory=WatchdogConfig)


class PoolSessionView(BaseModel):
    name: str
    account: str
    endpoint: str | None = None
    accelerator: str | None = None
    ssh_alias: str
    created_at: str | None = None
    hardware: HardwareProbe | None = None
    watchdog_config: WatchdogConfig | None = None
    watchdog_live: WatchdogLiveStatus | None = None
    ssh_mux_active: bool = False
    vanished: bool = False


class OrphanInstance(BaseModel):
    account: str
    endpoint: str
    hardware: str | None = None
    name: str | None = None


class PoolOverview(BaseModel):
    primary: str | None = None
    active: str | None = None
    threshold: float | None = None
    usage_mode: str = "cached"
    accounts: list[AccountInfo] = Field(default_factory=list)
    total: TotalUsage = Field(default_factory=TotalUsage)
    sessions: list[PoolSessionView] = Field(default_factory=list)
    orphans: list[OrphanInstance] = Field(default_factory=list)
    vanished: list[str] = Field(default_factory=list)
    errors: dict[str, Any] = Field(default_factory=dict)


class UpResult(BaseModel):
    session: PoolSessionView
    allocate_seconds: float
    ssh_command: str
    ssh_config_path: str
    watchdog_deployed: bool
    watchdog_error: str | None = None


class StopResult(BaseModel):
    name: str
    stopped: bool
    mux_closed: bool
    ssh_config_removed: bool
    message: str


class DoctorReport(BaseModel):
    ok: bool
    binaries: dict[str, str | None]
    identity_file: str | None
    ssh_config_included: bool
    managed_ssh_config_path: str
    accounts_count: int
    primary_account: str | None
    issues: list[str] = Field(default_factory=list)
