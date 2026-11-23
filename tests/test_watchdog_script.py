"""Unit tests for the embedded VM-side cost-guard watchdog script."""

from __future__ import annotations

import json
from pathlib import Path

from colabctl.watchdog_script import WATCHDOG_SCRIPT_SOURCE


def _load_watchdog_class():
    namespace: dict = {}
    exec(compile(WATCHDOG_SCRIPT_SOURCE, "watchdog.py", "exec"), namespace)
    return namespace["ColabWatchdog"]


def test_watchdog_releases_on_idle_timeout(tmp_path: Path) -> None:
    ColabWatchdog = _load_watchdog_class()
    cfg_path = tmp_path / "watchdog.json"
    status_path = tmp_path / "status.json"
    now = [1000.0]
    released: list[str] = []

    cfg_path.write_text(
        json.dumps(
            {
                "started": 1000.0,
                "idle_timeout_s": 600,
                "deadline_epoch": 10000.0,
                "gpu_busy_percent": 5.0,
                "warn_before_s": 120,
                "cancelled": False,
                "log": str(tmp_path / "watchdog.log"),
            }
        )
    )

    wd = ColabWatchdog(
        str(cfg_path),
        str(status_path),
        clock=lambda: now[0],
        sleeper=lambda _: None,
        gpu_probe=lambda: 0.0,
        pty_probe=lambda: (0, None),
        unassign_fn=lambda reason: released.append(reason) or True,
    )

    # Active window (< 600s)
    now[0] = 1300.0
    assert wd.step() == "continue"
    assert not released

    status = json.loads(status_path.read_text())
    assert status["running"] is True
    assert status["idle_for_s"] == 300.0
    assert status["remaining_idle_s"] == 300.0

    # Past idle timeout (>= 600s)
    now[0] = 1605.0
    assert wd.step() == "released"
    assert len(released) == 1
    assert released[0].startswith("idle_")


def test_watchdog_gpu_and_pty_activity_resets_idle(tmp_path: Path) -> None:
    ColabWatchdog = _load_watchdog_class()
    cfg_path = tmp_path / "watchdog.json"
    status_path = tmp_path / "status.json"
    now = [1000.0]
    gpu_util = [0.0]
    pty_state: list[tuple[int, float | None]] = [(1, 1000.0)]
    released: list[str] = []

    cfg_path.write_text(
        json.dumps(
            {
                "started": 1000.0,
                "idle_timeout_s": 600,
                "deadline_epoch": 10000.0,
                "gpu_busy_percent": 5.0,
                "cancelled": False,
                "log": str(tmp_path / "watchdog.log"),
            }
        )
    )

    wd = ColabWatchdog(
        str(cfg_path),
        str(status_path),
        clock=lambda: now[0],
        sleeper=lambda _: None,
        gpu_probe=lambda: gpu_util[0],
        pty_probe=lambda: pty_state[0],
        unassign_fn=lambda reason: released.append(reason) or True,
    )

    # At t=1500, GPU spikes to 42% -> resets idle
    now[0] = 1500.0
    gpu_util[0] = 42.0
    assert wd.step() == "continue"
    assert json.loads(status_path.read_text())["last_active_reason"] == "gpu_util=42.0%"

    # At t=1900 (400s after GPU spike), GPU drops to 0, still < 600s -> continue
    now[0] = 1900.0
    gpu_util[0] = 0.0
    assert wd.step() == "continue"
    assert not released

    # At t=2050, user types in SSH PTY -> resets idle
    now[0] = 2050.0
    pty_state[0] = (1, 2049.0)
    assert wd.step() == "continue"
    assert json.loads(status_path.read_text())["last_active_reason"] == "ssh_pty_io"

    # At t=2655 (606s after last PTY I/O, GPU 0%) -> releases
    now[0] = 2655.0
    assert wd.step() == "released"
    assert released


def test_watchdog_releases_on_hard_deadline_even_when_gpu_busy(tmp_path: Path) -> None:
    ColabWatchdog = _load_watchdog_class()
    cfg_path = tmp_path / "watchdog.json"
    status_path = tmp_path / "status.json"
    now = [1000.0]
    released: list[str] = []

    cfg_path.write_text(
        json.dumps(
            {
                "started": 1000.0,
                "idle_timeout_s": 1800,
                "deadline_epoch": 2000.0,
                "cancelled": False,
                "log": str(tmp_path / "watchdog.log"),
            }
        )
    )

    wd = ColabWatchdog(
        str(cfg_path),
        str(status_path),
        clock=lambda: now[0],
        sleeper=lambda _: None,
        gpu_probe=lambda: 99.0,
        pty_probe=lambda: (1, now[0]),
        unassign_fn=lambda reason: released.append(reason) or True,
    )

    now[0] = 1999.0
    assert wd.step() == "continue"

    now[0] = 2001.0
    assert wd.step() == "released"
    assert released == ["hard_deadline"]


def test_watchdog_cancelled_exits_without_releasing(tmp_path: Path) -> None:
    ColabWatchdog = _load_watchdog_class()
    cfg_path = tmp_path / "watchdog.json"
    status_path = tmp_path / "status.json"
    released: list[str] = []

    cfg_path.write_text(
        json.dumps(
            {
                "started": 1000.0,
                "idle_timeout_s": 60,
                "deadline_epoch": 1100.0,
                "cancelled": True,
                "log": str(tmp_path / "watchdog.log"),
            }
        )
    )

    wd = ColabWatchdog(
        str(cfg_path),
        str(status_path),
        clock=lambda: 5000.0,
        sleeper=lambda _: None,
        gpu_probe=lambda: 0.0,
        pty_probe=lambda: (0, None),
        unassign_fn=lambda reason: released.append(reason) or True,
    )
    assert wd.step() == "cancelled"
    assert not released
    assert json.loads(status_path.read_text())["cancelled"] is True


def test_watchdog_ignores_own_broadcast_pty_mtime(tmp_path: Path) -> None:
    ColabWatchdog = _load_watchdog_class()
    cfg_path = tmp_path / "watchdog.json"
    status_path = tmp_path / "status.json"
    now = [1000.0]
    pty_mtime = [1000.0]
    released: list[str] = []

    cfg_path.write_text(
        json.dumps(
            {
                "started": 1000.0,
                "idle_timeout_s": 600,
                "deadline_epoch": 10000.0,
                "warn_before_s": 120,
                "cancelled": False,
                "log": str(tmp_path / "watchdog.log"),
            }
        )
    )

    wd = ColabWatchdog(
        str(cfg_path),
        str(status_path),
        clock=lambda: now[0],
        sleeper=lambda _: None,
        gpu_probe=lambda: 0.0,
        pty_probe=lambda: (1, pty_mtime[0]),
        unassign_fn=lambda reason: released.append(reason) or True,
    )

    # Simulate broadcast bumping PTY mtime to 1500.0 and setting ignored_pty_mtime
    now[0] = 1500.0
    wd.ignored_pty_mtime = 1500.0
    pty_mtime[0] = 1500.0
    assert wd.step() == "continue"
    # last_active must still be 1000.0, NOT 1500.0
    assert wd.last_active == 1000.0

    now[0] = 1605.0
    assert wd.step() == "released"
    assert released


def test_watchdog_manager_generated_remote_code_parses_null_booleans(
    tmp_path: Path,
) -> None:
    """Regression test: generated remote snippets must not embed raw JSON null/true/false."""
    import ast
    from colabctl.models import WatchdogConfig
    from colabctl.pool_adapter import PoolAdapter
    from colabctl.watchdog_manager import WatchdogManager

    captured_code: list[str] = []

    class CapturingPool(PoolAdapter):
        def exec_json(self, name: str, python_code: str, *, timeout_s: int = 45):
            captured_code.append(python_code)
            tree = ast.parse(python_code)
            names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
            assert not (names & {"null", "true", "false"}), f"Bare JSON identifier in Python AST: {names}"
            return {"running": True, "pid": 123, "deadline_epoch": 9999.0}

    mgr = WatchdogManager(CapturingPool())
    # Test deploy with None deadline_epoch and False/True booleans
    res = mgr.deploy("demo", WatchdogConfig(enabled=True, deadline_epoch=None, idle_timeout_s=900))
    assert res.running is True
    assert "json.loads(" in captured_code[-1]

    # Test update with None values and booleans
    res2 = mgr.update("demo", add_hours=2.0, max_hours_from_now=None, idle_minutes=None, disable=False, enable=True)
    assert res2.running is True
    assert "json.loads(" in captured_code[-1]

