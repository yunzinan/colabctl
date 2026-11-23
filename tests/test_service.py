"""Unit tests for ColabController workflows using a fake PoolAdapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from colabctl.config import AppPaths
from colabctl.models import WatchdogConfig, WatchdogLiveStatus
from colabctl.pool_adapter import CommandOutput, PoolAdapter, PoolAdapterError
from colabctl.service import ColabController, ColabctlError
from colabctl.ssh_manager import SshManager
from colabctl.watchdog_manager import WatchdogManager


class FakePoolAdapter(PoolAdapter):
    def __init__(self) -> None:
        super().__init__(pool_bin="colab-pool", account_bin="colab-account", colab_bin="colab")
        self.sessions: dict[str, dict[str, Any]] = {}
        self.orphans: list[dict[str, Any]] = []
        self.vanished: list[str] = []
        self.reaped: list[tuple[str, str]] = []
        self.fail_next_new_with_orphan: tuple[str, str] | None = None
        self.exec_calls: list[tuple[str, str]] = []
        self.new_calls: list[dict[str, Any]] = []
        self.primary = "ultra"

    def check_binaries(self) -> dict[str, str | None]:
        return {
            "colab": "/bin/colab",
            "colab-pool": "/bin/colab-pool",
            "colab-account": "/bin/colab-account",
            "ssh": "/usr/bin/ssh",
        }

    def list_raw(self, *, live: bool = False) -> dict[str, Any]:
        return {
            "primary": self.primary,
            "active": self.primary,
            "threshold": 5.0,
            "usage_mode": "live" if live else "cached",
            "accounts": [
                {
                    "name": "ultra",
                    "email": "u@example.com",
                    "balance": 2500.0,
                    "hourly_rate": 0.0,
                    "assignments": len(self.sessions) + len(self.orphans),
                    "pool_sessions": len(self.sessions),
                    "primary": self.primary == "ultra",
                    "active": True,
                },
                {
                    "name": "pro1",
                    "email": "p1@example.com",
                    "balance": 200.0,
                    "hourly_rate": 0.0,
                    "assignments": 0,
                    "pool_sessions": 0,
                    "primary": self.primary == "pro1",
                    "active": False,
                },
            ],
            "total": {
                "balance": 2700.0,
                "hourly_rate": 0.0,
                "assignments": len(self.sessions) + len(self.orphans),
                "accounts_with_usage": 2,
                "account_count": 2,
                "complete": True,
            },
            "sessions": list(self.sessions.values()),
            "orphans": list(self.orphans),
            "vanished": list(self.vanished),
            "errors": {},
        }

    def new_session(self, name: str, **kwargs: Any) -> CommandOutput:
        self.new_calls.append({"name": name, **kwargs})
        if self.fail_next_new_with_orphan is not None:
            acc, ep = self.fail_next_new_with_orphan
            self.fail_next_new_with_orphan = None
            self.orphans.append({"account": acc, "endpoint": ep, "hardware": "A100"})
            raise PoolAdapterError("ReadTimeout", returncode=1)
        acc = kwargs.get("account") or self.primary
        gpu = str(kwargs.get("gpu") or "t4").upper()
        self.sessions[name] = {
            "name": name,
            "account": acc,
            "endpoint": f"gpu-{gpu.lower()}-ep1",
            "accelerator": gpu,
        }
        return CommandOutput(0, "Session READY", "")

    def stop_session(self, name: str, *, forget: bool = False) -> CommandOutput:
        if name not in self.sessions:
            raise PoolAdapterError(f"Session '{name}' is not in the pool.")
        del self.sessions[name]
        if name in self.vanished:
            self.vanished.remove(name)
        return CommandOutput(0, "Stopped", "")

    def stop_all(self) -> CommandOutput:
        self.sessions.clear()
        self.orphans.clear()
        self.vanished.clear()
        return CommandOutput(0, "All stopped", "")

    def reap_orphan(self, account: str, endpoint: str) -> CommandOutput:
        self.reaped.append((account, endpoint))
        self.orphans = [
            o
            for o in self.orphans
            if not (o["account"] == account and o["endpoint"] == endpoint)
        ]
        return CommandOutput(0, "Reaped", "")

    def set_primary(self, account: str, *, threshold: float | None = None) -> CommandOutput:
        if account not in ("ultra", "pro1"):
            raise PoolAdapterError(f"Unknown account: {account}")
        self.primary = account
        return CommandOutput(0, f"Primary set to {account}", "")

    def exec_json(
        self, name: str, python_code: str, *, timeout_s: int = 45
    ) -> dict[str, Any]:
        self.exec_calls.append((name, python_code))
        if "nvidia-smi" in python_code and "free" in python_code:
            return {
                "gpu_name": "Tesla T4",
                "gpu_memory_mib": 15360,
                "driver_version": "580.82.07",
                "ram_total": "12Gi",
                "cpu_cores": 2,
                "hostname": "colab-host",
                "tbe_runtime_addr": "172.28.0.1:8011",
            }
        if "sshd:" in python_code:
            return {"killed": [{"pid": 999, "cmd": "sshd: root@pts/0"}]}
        return {}


class FakeWatchdogManager(WatchdogManager):
    def __init__(self, pool: PoolAdapter) -> None:
        super().__init__(pool)
        self.deployed: dict[str, WatchdogConfig] = {}

    def deploy(self, session_name: str, config: WatchdogConfig) -> WatchdogLiveStatus:
        self.deployed[session_name] = config
        return WatchdogLiveStatus(
            running=config.enabled,
            pid=4242,
            deadline_epoch=20000.0,
            remaining_deadline_s=14400.0,
            idle_timeout_s=config.idle_timeout_s,
            remaining_idle_s=float(config.idle_timeout_s or 0),
            gpu_util_percent=0.0,
            last_active_reason="startup",
            cancelled=not config.enabled,
        )

    def get_status(self, session_name: str) -> WatchdogLiveStatus:
        cfg = self.deployed.get(session_name, WatchdogConfig())
        return WatchdogLiveStatus(
            running=cfg.enabled,
            pid=4242,
            deadline_epoch=20000.0,
            remaining_deadline_s=7200.0,
            idle_timeout_s=cfg.idle_timeout_s,
            idle_for_s=60.0,
            remaining_idle_s=1740.0,
            gpu_util_percent=2.0,
            cancelled=not cfg.enabled,
        )

    def update(self, session_name: str, **kwargs: Any) -> WatchdogLiveStatus:
        cfg = self.deployed.setdefault(session_name, WatchdogConfig())
        if kwargs.get("disable"):
            cfg.enabled = False
        if kwargs.get("enable"):
            cfg.enabled = True
        if kwargs.get("idle_minutes") is not None:
            m = kwargs["idle_minutes"]
            cfg.idle_timeout_s = m * 60 if m > 0 else None
        return WatchdogLiveStatus(
            running=cfg.enabled,
            pid=4242,
            deadline_epoch=27200.0,
            remaining_deadline_s=21600.0,
            idle_timeout_s=cfg.idle_timeout_s,
            cancelled=not cfg.enabled,
        )


def _make_controller(tmp_path: Path) -> tuple[ColabController, FakePoolAdapter, FakeWatchdogManager]:
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir(mode=0o700)
    (ssh_dir / "id_ed25519_colab").write_text("dummy-priv")
    (ssh_dir / "id_ed25519_colab.pub").write_text("ssh-ed25519 AAAATEST colab")

    paths = AppPaths(config_dir=tmp_path / "colabctl", ssh_dir=ssh_dir)
    pool = FakePoolAdapter()
    ssh = SshManager(paths, colabctl_bin="/usr/local/bin/colabctl")
    ssh.warmup_mux = lambda alias, ctl, timeout_s=35: (True, None)  # type: ignore[method-assign]
    wd = FakeWatchdogManager(pool)
    ctrl = ColabController(paths=paths, pool=pool, ssh=ssh, watchdog=wd)
    return ctrl, pool, wd


def test_up_status_extend_guard_reset_and_stop_lifecycle(tmp_path: Path) -> None:
    ctrl, pool, wd = _make_controller(tmp_path)

    # 1. Up
    res = ctrl.up("dev", gpu="t4", idle_minutes=20, max_hours=3.0)
    assert res.session.name == "dev"
    assert res.session.account == "ultra"
    assert res.session.ssh_alias == "colab-dev"
    assert res.session.hardware is not None
    assert res.session.hardware.gpu_name == "Tesla T4"
    assert res.watchdog_deployed is True
    assert wd.deployed["dev"].idle_timeout_s == 1200
    assert wd.deployed["dev"].max_duration_s == 10800
    assert ctrl.ssh.is_included_in_user_ssh_config() is True
    assert "Host colab-dev" in ctrl.paths.managed_ssh_config.read_text()

    # 2. Status
    st = ctrl.status("dev")
    assert st.watchdog_live is not None
    assert st.watchdog_live.running is True

    # 3. Extend & disable guard
    ext = ctrl.extend("dev", add_hours=2.0)
    assert ext.running is True
    off = ctrl.configure_guard("dev", disable=True)
    assert off.cancelled is True

    # 4. Reset SSH
    reset = ctrl.reset_ssh("dev")
    assert len(reset["remote_sessions_terminated"]) == 1

    # 5. Stop
    stopped = ctrl.stop("dev")
    assert stopped.stopped is True
    assert "Host colab-dev" not in ctrl.paths.managed_ssh_config.read_text()
    assert ctrl.store.get_session("dev") is None


def test_up_auto_reaps_only_newly_leaked_orphan_on_timeout(tmp_path: Path) -> None:
    ctrl, pool, _ = _make_controller(tmp_path)
    # Pre-existing unrelated browser notebook orphan MUST NOT be touched!
    pool.orphans.append({"account": "ultra", "endpoint": "browser-existing-ep", "hardware": "T4"})
    pool.fail_next_new_with_orphan = ("ultra", "leaked-a100-ep")

    with pytest.raises(ColabctlError) as exc_info:
        ctrl.up("heavy", gpu="a100")

    assert "Auto-reaped 1 newly leaked orphan VM" in str(exc_info.value)
    assert pool.reaped == [("ultra", "leaked-a100-ep")]
    assert len(pool.orphans) == 1
    assert pool.orphans[0]["endpoint"] == "browser-existing-ep"


def test_up_replaces_vanished_session_cleanly(tmp_path: Path) -> None:
    ctrl, pool, _ = _make_controller(tmp_path)
    ctrl.up("dev", gpu="t4")
    # Simulate watchdog killing the VM on Colab backend
    pool.vanished.append("dev")

    res = ctrl.up("dev", gpu="l4")
    assert res.session.accelerator == "L4"
    assert "dev" not in pool.vanished


def test_switch_replaces_gpu_under_same_alias(tmp_path: Path) -> None:
    ctrl, pool, _ = _make_controller(tmp_path)
    ctrl.up("work", gpu="t4")
    switched = ctrl.switch("work", gpu="l4")
    assert switched.session.name == "work"
    assert switched.session.ssh_alias == "colab-work"
    assert switched.session.accelerator == "L4"
    assert pool.sessions["work"]["accelerator"] == "L4"


def test_single_shape_gpus_strip_high_mem(tmp_path: Path) -> None:
    ctrl, pool, _ = _make_controller(tmp_path)
    # G4 (RTX PRO 6000) and L4 only have a single shape; Colab rejects G4 + shape=hm with HTTP 400
    ctrl.up("pro6k", gpu="g4", high_mem=True)
    assert pool.new_calls[-1]["gpu"] == "g4"
    assert pool.new_calls[-1]["high_mem"] is False
    meta = ctrl.store.get_session("pro6k")
    assert meta is not None
    assert meta.high_mem is False

    # A100 still honors high_mem=True
    ctrl.up("a100box", gpu="a100", high_mem=True)
    assert pool.new_calls[-1]["gpu"] == "a100"
    assert pool.new_calls[-1]["high_mem"] is True

    # PoolAdapter.new_session also defensively strips --high-mem for g4/l4
    captured_argv: list[list[str]] = []

    class RecordingPoolAdapter(PoolAdapter):
        def _run(self, argv: list[str], **_kwargs: Any) -> CommandOutput:
            captured_argv.append(argv)
            return CommandOutput(0, "ok", "")

    rec = RecordingPoolAdapter(pool_bin="colab-pool", account_bin="colab-account", colab_bin="colab")
    rec.new_session("s1", gpu="g4", high_mem=True)
    rec.new_session("s2", gpu="l4", high_mem=True)
    rec.new_session("s3", gpu="a100", high_mem=True)
    assert "--high-mem" not in captured_argv[0]
    assert "--high-mem" not in captured_argv[1]
    assert "--high-mem" in captured_argv[2]


def test_account_quota_inference_and_custom_override(tmp_path: Path) -> None:
    from colabctl.models import infer_account_quota

    # Plan alias inference (immune to rollover or burned-down balance)
    assert infer_account_quota("ultra", 2500.0) == 2500.0
    assert infer_account_quota("ultra", 120.0) == 2500.0
    assert infer_account_quota("ai-20x", 400.0) == 2500.0
    assert infer_account_quota("pro1", 222.52) == 200.0
    assert infer_account_quota("pro2", 50.0) == 200.0
    assert infer_account_quota("pro-plus", 480.0) == 500.0
    assert infer_account_quota("proplus", 510.0) == 500.0
    # Words merely starting with "pro" (like "project" / "prod") fall back to balance tiers
    assert infer_account_quota("project", 95.0) == 100.0
    assert infer_account_quota("prod", 2200.0) == 2500.0
    assert infer_account_quota("work", 480.0) == 500.0
    assert infer_account_quota("work", 222.52) == 200.0

    # Controller populates inferred quotas and persists custom overrides
    ctrl, _, _ = _make_controller(tmp_path)
    ov = ctrl.list_overview(live=False)
    by_name = {a.name: a for a in ov.accounts}
    assert by_name["ultra"].quota_cu == 2500.0
    assert by_name["ultra"].quota_source == "inferred"
    assert by_name["pro1"].quota_cu == 200.0
    assert by_name["pro1"].quota_source == "inferred"

    # Override pro1 to 100 CU (e.g. Pro 1x plan) -> persisted in settings.json
    quota, src = ctrl.set_account_quota("pro1", 100.0)
    assert (quota, src) == (100.0, "custom")
    ov2 = ctrl.list_overview(live=False)
    by_name2 = {a.name: a for a in ov2.accounts}
    assert by_name2["pro1"].quota_cu == 100.0
    assert by_name2["pro1"].quota_source == "custom"

    # Reset back to auto-inferred
    quota_auto, src_auto = ctrl.set_account_quota("pro1", None)
    assert (quota_auto, src_auto) == (200.0, "inferred")
    ov3 = ctrl.list_overview(live=False)
    assert {a.name: a for a in ov3.accounts}["pro1"].quota_source == "inferred"
