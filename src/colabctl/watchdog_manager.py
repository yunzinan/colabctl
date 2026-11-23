"""Deploy, query, extend, and configure the VM-side cost-guard watchdog."""

from __future__ import annotations

import base64
import json

from collections.abc import Callable
from typing import Any

from colabctl.models import WatchdogConfig, WatchdogLiveStatus
from colabctl.pool_adapter import RESULT_MARKER, PoolAdapter
from colabctl.watchdog_script import (
    WATCHDOG_REMOTE_CONFIG,
    WATCHDOG_REMOTE_DIR,
    WATCHDOG_REMOTE_HEARTBEAT,
    WATCHDOG_REMOTE_LOG,
    WATCHDOG_REMOTE_PID,
    WATCHDOG_REMOTE_SCRIPT,
    WATCHDOG_REMOTE_STATUS,
    WATCHDOG_SCRIPT_SOURCE,
)

FastExecFn = Callable[[str, str], dict[str, Any] | None]


class WatchdogManager:
    """Manages the detached VM-side cost-guard process over SSH mux or `colab-pool exec`."""

    def __init__(
        self,
        pool: PoolAdapter,
        *,
        fast_exec: FastExecFn | None = None,
    ) -> None:
        self.pool = pool
        self._fast_exec = fast_exec

    def _run_remote_json(
        self,
        session_name: str,
        code: str,
        *,
        timeout_s: int = 45,
        prefer_ssh: bool = True,
    ) -> dict[str, Any]:
        if prefer_ssh and self._fast_exec is not None:
            fast = self._fast_exec(session_name, code)
            if fast is not None:
                return fast
        return self.pool.exec_json(session_name, code, timeout_s=timeout_s)

    def deploy(
        self,
        session_name: str,
        config: WatchdogConfig,
    ) -> WatchdogLiveStatus:
        script_b64 = base64.b64encode(WATCHDOG_SCRIPT_SOURCE.encode("utf-8")).decode(
            "ascii"
        )
        cfg_payload = {
            "idle_timeout_s": config.idle_timeout_s,
            "max_duration_s": config.max_duration_s,
            "deadline_epoch": config.deadline_epoch,
            "gpu_busy_percent": config.gpu_busy_percent,
            "poll_s": config.poll_s,
            "warn_before_s": config.warn_before_s,
            "cancelled": not config.enabled,
            "heartbeat": WATCHDOG_REMOTE_HEARTBEAT,
            "log": WATCHDOG_REMOTE_LOG,
        }
        code = f"""
import base64, json, os, signal, subprocess, sys, time

MARKER = {RESULT_MARKER!r}
d = {WATCHDOG_REMOTE_DIR!r}
os.makedirs(d, mode=0o700, exist_ok=True)
script_path = {WATCHDOG_REMOTE_SCRIPT!r}
config_path = {WATCHDOG_REMOTE_CONFIG!r}
status_path = {WATCHDOG_REMOTE_STATUS!r}
pid_path = {WATCHDOG_REMOTE_PID!r}

with open(script_path, "wb") as fh:
    fh.write(base64.b64decode({script_b64!r}))
os.chmod(script_path, 0o700)

# Stop any prior watchdog instance cleanly
if os.path.exists(pid_path):
    try:
        old_pid = int(open(pid_path).read().strip())
        os.kill(old_pid, signal.SIGTERM)
        time.sleep(0.3)
    except Exception:
        pass

now = time.time()
cfg = json.loads({json.dumps(cfg_payload)!r})
cfg["started"] = now
cfg["runtime_addr"] = os.environ.get("TBE_RUNTIME_ADDR")
if cfg.get("deadline_epoch") is None and cfg.get("max_duration_s"):
    cfg["deadline_epoch"] = now + float(cfg["max_duration_s"])

tmp_cfg = config_path + ".tmp"
with open(tmp_cfg, "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, indent=2)
os.replace(tmp_cfg, config_path)

if cfg.get("cancelled"):
    print(MARKER + json.dumps({{"running": False, "cancelled": True, "deadline_epoch": cfg.get("deadline_epoch")}}))
else:
    proc = subprocess.Popen(
        [sys.executable, script_path, "--config", config_path, "--status", status_path, "--pid-file", pid_path],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    deadline_wait = time.time() + 5.0
    status = None
    while time.time() < deadline_wait:
        if os.path.exists(status_path):
            try:
                data = json.load(open(status_path, encoding="utf-8"))
                if data.get("pid") == proc.pid:
                    status = data
                    break
            except Exception:
                pass
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    if status is None:
        status = {{
            "running": proc.poll() is None,
            "pid": proc.pid,
            "deadline_epoch": cfg.get("deadline_epoch"),
            "idle_timeout_s": cfg.get("idle_timeout_s"),
            "error": None if proc.poll() is None else f"watchdog exited with code {{proc.returncode}}",
        }}
    print(MARKER + json.dumps(status))
"""
        # Always deploy via kernel exec so TBE_RUNTIME_ADDR is captured directly from os.environ
        data = self._run_remote_json(session_name, code, timeout_s=60, prefer_ssh=False)
        return WatchdogLiveStatus.model_validate(data)

    def get_status(self, session_name: str) -> WatchdogLiveStatus:
        code = f"""
import json, os, time

MARKER = {RESULT_MARKER!r}
status_path = {WATCHDOG_REMOTE_STATUS!r}
pid_path = {WATCHDOG_REMOTE_PID!r}
config_path = {WATCHDOG_REMOTE_CONFIG!r}

pid = None
alive = False
if os.path.exists(pid_path):
    try:
        pid = int(open(pid_path).read().strip())
        os.kill(pid, 0)
        alive = True
    except Exception:
        alive = False

status = {{}}
if os.path.exists(status_path):
    try:
        status = json.load(open(status_path, encoding="utf-8"))
    except Exception as exc:
        status = {{"error": f"status unreadable: {{exc}}"}}

if not status and os.path.exists(config_path):
    try:
        cfg = json.load(open(config_path, encoding="utf-8"))
        status["cancelled"] = bool(cfg.get("cancelled"))
        status["deadline_epoch"] = cfg.get("deadline_epoch")
        status["idle_timeout_s"] = cfg.get("idle_timeout_s")
    except Exception:
        pass

now = time.time()
status["running"] = alive
if pid is not None:
    status["pid"] = pid
if isinstance(status.get("deadline_epoch"), (int, float)):
    status["remaining_deadline_s"] = max(0.0, float(status["deadline_epoch"]) - now)
print(MARKER + json.dumps(status))
"""
        data = self._run_remote_json(session_name, code, timeout_s=45, prefer_ssh=True)
        return WatchdogLiveStatus.model_validate(data)

    def update(
        self,
        session_name: str,
        *,
        add_hours: float | None = None,
        max_hours_from_now: float | None = None,
        idle_minutes: int | None = None,
        disable: bool = False,
        enable: bool = False,
    ) -> WatchdogLiveStatus:
        """Update live watchdog config on the VM (extending deadline or toggling)."""
        params = {
            "add_hours": add_hours,
            "max_hours_from_now": max_hours_from_now,
            "idle_minutes": idle_minutes,
            "disable": disable,
            "enable": enable,
        }
        code = f"""
import json, os, time

MARKER = {RESULT_MARKER!r}
config_path = {WATCHDOG_REMOTE_CONFIG!r}
pid_path = {WATCHDOG_REMOTE_PID!r}
hb_path = {WATCHDOG_REMOTE_HEARTBEAT!r}
params = json.loads({json.dumps(params)!r})

if not os.path.exists(config_path):
    print(MARKER + json.dumps({{"running": False, "error": "watchdog_not_installed"}}))
else:
    cfg = json.load(open(config_path, encoding="utf-8"))
    now = time.time()
    if params["disable"]:
        cfg["cancelled"] = True
    if params["enable"]:
        cfg["cancelled"] = False
    if params["add_hours"] is not None:
        base = cfg.get("deadline_epoch")
        base = max(now, float(base)) if isinstance(base, (int, float)) else now
        cfg["deadline_epoch"] = base + float(params["add_hours"]) * 3600.0
    if params["max_hours_from_now"] is not None:
        hours = float(params["max_hours_from_now"])
        cfg["deadline_epoch"] = (now + hours * 3600.0) if hours > 0 else None
    if params["idle_minutes"] is not None:
        mins = int(params["idle_minutes"])
        cfg["idle_timeout_s"] = (mins * 60) if mins > 0 else None

    # Touch heartbeat so extending also refreshes idle timer
    try:
        open(hb_path, "a").close()
        os.utime(hb_path, None)
    except OSError:
        pass

    tmp = config_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.replace(tmp, config_path)

    pid = None
    alive = False
    if os.path.exists(pid_path):
        try:
            pid = int(open(pid_path).read().strip())
            os.kill(pid, 0)
            alive = True
        except Exception:
            alive = False

    dl = cfg.get("deadline_epoch")
    print(MARKER + json.dumps({{
        "running": alive and not cfg.get("cancelled"),
        "pid": pid,
        "deadline_epoch": dl,
        "remaining_deadline_s": max(0.0, float(dl) - now) if isinstance(dl, (int, float)) else None,
        "idle_timeout_s": cfg.get("idle_timeout_s"),
        "cancelled": bool(cfg.get("cancelled")),
    }}))
"""
        data = self._run_remote_json(session_name, code, timeout_s=45, prefer_ssh=True)
        status = WatchdogLiveStatus.model_validate(data)
        if enable and not status.running:
            # Watchdog process had exited previously; redeploy fresh process.
            redeploy_cfg = WatchdogConfig(
                enabled=True,
                idle_timeout_s=status.idle_timeout_s
                if idle_minutes is None
                else (idle_minutes * 60 if idle_minutes > 0 else None),
                deadline_epoch=status.deadline_epoch,
                max_duration_s=None,
            )
            return self.deploy(session_name, redeploy_cfg)
        return status
