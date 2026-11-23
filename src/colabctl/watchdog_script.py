"""Self-contained stdlib-only VM-side cost-guard watchdog script.

Runs detached inside the Colab VM. Independently enforces:
1. Hard absolute deadline (`deadline_epoch`)
2. Idle timeout (`idle_timeout_s`): triggers when GPU utilization stays below
   `gpu_busy_percent`, no active `/dev/pts/*` terminal has had recent I/O, and
   the optional heartbeat file has not been touched within `idle_timeout_s`.

When triggered, calls `POST http://$TBE_RUNTIME_ADDR/unassign` (equivalent to
`google.colab.runtime.unassign()`), stopping billing even if the user's laptop
is asleep or offline.
"""

from __future__ import annotations

WATCHDOG_REMOTE_DIR = "/root/.colabctl"
WATCHDOG_REMOTE_SCRIPT = f"{WATCHDOG_REMOTE_DIR}/watchdog.py"
WATCHDOG_REMOTE_CONFIG = f"{WATCHDOG_REMOTE_DIR}/watchdog.json"
WATCHDOG_REMOTE_STATUS = f"{WATCHDOG_REMOTE_DIR}/status.json"
WATCHDOG_REMOTE_PID = f"{WATCHDOG_REMOTE_DIR}/watchdog.pid"
WATCHDOG_REMOTE_LOG = f"{WATCHDOG_REMOTE_DIR}/watchdog.log"
WATCHDOG_REMOTE_HEARTBEAT = f"{WATCHDOG_REMOTE_DIR}/heartbeat"

WATCHDOG_SCRIPT_SOURCE = r'''#!/usr/bin/env python3
"""colabctl VM-side cost-guard watchdog (Python stdlib only)."""

from __future__ import annotations

import argparse
import glob
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

RELEASE_ATTEMPTS = 3


class ColabWatchdog:
    def __init__(
        self,
        config_path: str,
        status_path: str,
        *,
        clock=time.time,
        sleeper=time.sleep,
        gpu_probe=None,
        pty_probe=None,
        unassign_fn=None,
    ) -> None:
        self.config_path = config_path
        self.status_path = status_path
        self.clock = clock
        self.sleeper = sleeper
        self._gpu_probe = gpu_probe
        self._pty_probe = pty_probe
        self._unassign_fn = unassign_fn

        now = float(self.clock())
        self.started = now
        self.last_active = now
        self.last_active_reason = "startup"
        self.last_gpu_util: float | None = None
        self.active_ptys = 0
        self.warned_deadline_for: float | None = None
        self.warned_idle_at: float | None = None
        self.ignored_pty_mtime: float = 0.0
        self.config: dict = {}
        self.log_path = os.path.join(os.path.dirname(os.path.abspath(config_path)), "watchdog.log")

    def log(self, message: str) -> None:
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {message}\n"
        try:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass

    def load_config(self) -> dict:
        try:
            with open(self.config_path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self.config = data
        except (OSError, ValueError) as exc:
            self.log(f"config read failed ({type(exc).__name__}); keeping last config")
        if isinstance(self.config.get("log"), str):
            self.log_path = self.config["log"]
        if isinstance(self.config.get("started"), (int, float)):
            self.started = float(self.config["started"])
            if self.last_active < self.started:
                self.last_active = self.started
        return self.config

    def probe_gpu_util(self) -> float | None:
        if self._gpu_probe is not None:
            return self._gpu_probe()
        try:
            out = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            ).stdout
        except Exception:
            return None
        vals = []
        for line in out.splitlines():
            try:
                vals.append(float(line.strip()))
            except ValueError:
                continue
        return max(vals) if vals else None

    def probe_pty_activity(self) -> tuple[int, float | None]:
        """Return (count of open /dev/pts/N, newest mtime across pts devices)."""
        if self._pty_probe is not None:
            return self._pty_probe()
        ptys = [p for p in glob.glob("/dev/pts/*") if os.path.basename(p).isdigit()]
        latest: float | None = None
        for p in ptys:
            try:
                st = os.stat(p)
                if latest is None or st.st_mtime > latest:
                    latest = st.st_mtime
            except OSError:
                continue
        return len(ptys), latest

    def resolve_runtime_addr(self) -> str | None:
        addr = self.config.get("runtime_addr") or os.environ.get("TBE_RUNTIME_ADDR")
        if addr:
            return str(addr)
        try:
            for pid in os.listdir("/proc"):
                if not pid.isdigit():
                    continue
                try:
                    with open(f"/proc/{pid}/environ", "rb") as fh:
                        for item in fh.read().split(b"\0"):
                            if item.startswith(b"TBE_RUNTIME_ADDR="):
                                return item.split(b"=", 1)[1].decode("utf-8", errors="ignore")
                except OSError:
                    continue
        except OSError:
            pass
        return None

    def broadcast_warning(self, text: str) -> None:
        msg = f"\r\n[colabctl watchdog] {text}\r\n"
        max_mtime = self.ignored_pty_mtime
        for p in glob.glob("/dev/pts/*"):
            if not os.path.basename(p).isdigit():
                continue
            try:
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(msg)
                st = os.stat(p)
                if st.st_mtime > max_mtime:
                    max_mtime = st.st_mtime
            except OSError:
                continue
        # Ignore the mtime bump caused by our own warning write so idle timeout still fires.
        self.ignored_pty_mtime = max_mtime

    def release(self, reason: str) -> bool:
        if self._unassign_fn is not None:
            ok = bool(self._unassign_fn(reason))
            self.log(f"custom unassign ({reason}): {ok}")
            return ok
        addr = self.resolve_runtime_addr()
        if not addr:
            self.log(f"cannot release ({reason}): TBE_RUNTIME_ADDR not found")
            return False
        for attempt in range(1, RELEASE_ATTEMPTS + 1):
            try:
                req = urllib.request.Request(
                    f"http://{addr}/unassign", data=b"", method="POST"
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    if resp.status == 200:
                        self.log(f"released runtime ({reason})")
                        return True
                    self.log(f"unassign HTTP {resp.status} (attempt {attempt})")
            except Exception as exc:
                self.log(f"unassign error ({type(exc).__name__}, attempt {attempt})")
            self.sleeper(5)
        return False

    def write_status(
        self,
        now: float,
        *,
        deadline: float | None,
        idle_timeout: int | None,
        idle_for: float,
        cancelled: bool,
    ) -> None:
        payload = {
            "running": not cancelled,
            "pid": os.getpid(),
            "started_epoch": self.started,
            "updated_epoch": now,
            "deadline_epoch": deadline,
            "remaining_deadline_s": (
                max(0.0, deadline - now) if deadline is not None else None
            ),
            "idle_timeout_s": idle_timeout,
            "idle_for_s": max(0.0, idle_for),
            "remaining_idle_s": (
                max(0.0, idle_timeout - idle_for) if idle_timeout else None
            ),
            "gpu_util_percent": self.last_gpu_util,
            "last_active_reason": self.last_active_reason,
            "active_ptys": self.active_ptys,
            "cancelled": cancelled,
        }
        tmp = f"{self.status_path}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp, self.status_path)
        except OSError:
            pass

    def step(self) -> str:
        """Execute one polling cycle. Returns 'continue', 'cancelled', or 'released'."""
        self.load_config()
        now = float(self.clock())
        if self.config.get("cancelled"):
            self.write_status(
                now,
                deadline=self.config.get("deadline_epoch"),
                idle_timeout=self.config.get("idle_timeout_s"),
                idle_for=max(0.0, now - self.last_active),
                cancelled=True,
            )
            self.log("cancelled; exiting without releasing")
            return "cancelled"

        # 1. Sample activity sources
        gpu_thresh = float(self.config.get("gpu_busy_percent", 5.0))
        util = self.probe_gpu_util()
        self.last_gpu_util = util
        if util is not None and util >= gpu_thresh:
            if now >= self.last_active:
                self.last_active = now
                self.last_active_reason = f"gpu_util={util:.1f}%"

        pty_count, latest_pty_mtime = self.probe_pty_activity()
        self.active_ptys = pty_count
        if (
            latest_pty_mtime is not None
            and latest_pty_mtime > self.ignored_pty_mtime
            and latest_pty_mtime > self.last_active
        ):
            self.last_active = min(now, latest_pty_mtime)
            self.last_active_reason = "ssh_pty_io"

        hb_path = self.config.get("heartbeat")
        if isinstance(hb_path, str):
            try:
                hb_mtime = os.path.getmtime(hb_path)
                if hb_mtime > self.last_active:
                    self.last_active = min(now, hb_mtime)
                    self.last_active_reason = "heartbeat"
            except OSError:
                pass

        idle_for = max(0.0, now - self.last_active)
        deadline = self.config.get("deadline_epoch")
        if not isinstance(deadline, (int, float)):
            deadline = None
        else:
            deadline = float(deadline)

        idle_timeout = self.config.get("idle_timeout_s")
        if not isinstance(idle_timeout, (int, float)) or idle_timeout <= 0:
            idle_timeout = None
        else:
            idle_timeout = int(idle_timeout)

        warn_before = float(self.config.get("warn_before_s", 120))

        self.write_status(
            now,
            deadline=deadline,
            idle_timeout=idle_timeout,
            idle_for=idle_for,
            cancelled=False,
        )

        # 2. Warnings before auto-release
        if deadline is not None:
            rem_dl = deadline - now
            if 0 < rem_dl <= warn_before and self.warned_deadline_for != deadline:
                self.warned_deadline_for = deadline
                self.broadcast_warning(
                    f"Hard limit reached in ~{int(rem_dl)}s. Run 'colabctl extend <name> --hours 2' on your Mac to keep alive."
                )
            elif rem_dl > warn_before:
                self.warned_deadline_for = None

        if idle_timeout is not None:
            rem_idle = idle_timeout - idle_for
            if 0 < rem_idle <= warn_before and (
                self.warned_idle_at is None or self.warned_idle_at < self.last_active
            ):
                self.warned_idle_at = now
                self.broadcast_warning(
                    f"VM idle for {int(idle_for)}s; auto-shutdown in ~{int(rem_idle)}s unless GPU or terminal activity resumes."
                )

        # 3. Enforce deadline
        if deadline is not None and now >= deadline:
            if self.release("hard_deadline"):
                return "released"

        # 4. Enforce idle timeout
        if idle_timeout is not None and idle_for >= idle_timeout:
            if self.release(f"idle_{int(idle_for)}s"):
                return "released"

        return "continue"

    def run(self) -> int:
        self.load_config()
        self.log(f"watchdog started pid={os.getpid()}")
        while True:
            outcome = self.step()
            if outcome in ("cancelled", "released"):
                return 0
            poll = self.config.get("poll_s", 15)
            delay = max(5, min(60, int(poll) if isinstance(poll, (int, float)) else 15))
            self.sleeper(delay)


def main() -> int:
    parser = argparse.ArgumentParser(description="colabctl VM cost-guard watchdog")
    parser.add_argument("--config", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--pid-file", required=True)
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGHUP, signal.SIG_IGN)

    os.makedirs(os.path.dirname(os.path.abspath(args.pid_file)), exist_ok=True)
    with open(args.pid_file, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))

    return ColabWatchdog(args.config, args.status).run()


if __name__ == "__main__":
    sys.exit(main())
'''
