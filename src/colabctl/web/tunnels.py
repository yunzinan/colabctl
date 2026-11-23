"""Managed SSH port-forwarding tunnels riding on top of colabctl's ControlMaster."""

from __future__ import annotations

import socket
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel

from colabctl.service import ColabController, ColabctlError

RESERVED_REMOTE_PORTS = frozenset({8080})


class TunnelView(BaseModel):
    id: str
    session: str
    ssh_alias: str
    remote_port: int
    local_port: int
    label: str
    url: str
    status: str  # "running" | "stopped" | "failed"
    pid: int | None = None
    error: str | None = None
    started_at: str


@dataclass
class _ActiveTunnel:
    view: TunnelView
    process: subprocess.Popen[str] | None = None


def _is_local_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


class TunnelManager:
    """Starts and stops `-L` port forwards over colabctl's shared SSH mux socket."""

    def __init__(self, controller: ColabController, *, demo_mode: bool = False) -> None:
        self._ctrl = controller
        self._demo_mode = demo_mode
        self._lock = threading.Lock()
        self._tunnels: dict[str, _ActiveTunnel] = {}

    def start(
        self,
        session_name: str,
        *,
        remote_port: int,
        local_port: int | None = None,
        label: str | None = None,
    ) -> TunnelView:
        if not (1 <= remote_port <= 65535):
            raise ColabctlError(f"Invalid remote port: {remote_port}")
        if remote_port in RESERVED_REMOTE_PORTS:
            raise ColabctlError(
                f"Port {remote_port} is reserved by Colab's internal proxy inside the VM."
            )
        lp = local_port if local_port is not None else remote_port
        if not (1 <= lp <= 65535):
            raise ColabctlError(f"Invalid local port: {lp}")

        meta = self._ctrl.resolve_ssh_target(session_name)

        with self._lock:
            self._prune_exited_locked()
            for active in self._tunnels.values():
                if active.view.status == "running" and active.view.local_port == lp:
                    if (
                        active.view.session == session_name
                        and active.view.remote_port == remote_port
                    ):
                        return active.view.model_copy(deep=True)
                    raise ColabctlError(
                        f"Local port 127.0.0.1:{lp} is already forwarded by tunnel {active.view.id} ({active.view.session}:{active.view.remote_port})."
                    )

        if self._demo_mode:
            tid = uuid.uuid4().hex[:8]
            view = TunnelView(
                id=tid,
                session=session_name,
                ssh_alias=meta.ssh_alias,
                remote_port=remote_port,
                local_port=lp,
                label=(label or f"Port {remote_port}").strip(),
                url=f"http://127.0.0.1:{lp}",
                status="running",
                pid=None,
                started_at=datetime.now(UTC).isoformat(),
            )
            with self._lock:
                self._tunnels[tid] = _ActiveTunnel(view=view, process=None)
            return view.model_copy(deep=True)

        if _is_local_port_in_use(lp):
            raise ColabctlError(
                f"Local port 127.0.0.1:{lp} is already in use by another process. Choose a different local port."
            )

        argv = self._ctrl.ssh.build_tunnel_argv(meta.ssh_alias, remote_port, lp)
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait briefly (up to 4s) for the local listener to bind or fail immediately
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                err = (proc.stderr.read() if proc.stderr else "").strip()
                raise ColabctlError(
                    f"SSH tunnel failed (exit {proc.returncode}): {err or 'check session status'}"
                )
            if _is_local_port_in_use(lp):
                break
            time.sleep(0.15)

        tid = uuid.uuid4().hex[:8]
        view = TunnelView(
            id=tid,
            session=session_name,
            ssh_alias=meta.ssh_alias,
            remote_port=remote_port,
            local_port=lp,
            label=(label or f"Port {remote_port}").strip(),
            url=f"http://127.0.0.1:{lp}",
            status="running",
            pid=proc.pid,
            started_at=datetime.now(UTC).isoformat(),
        )
        with self._lock:
            self._tunnels[tid] = _ActiveTunnel(view=view, process=proc)
        return view.model_copy(deep=True)

    def _prune_exited_locked(self) -> None:
        for active in self._tunnels.values():
            if (
                active.process is not None
                and active.view.status == "running"
                and active.process.poll() is not None
            ):
                active.view.status = (
                    "stopped" if active.process.returncode == 0 else "failed"
                )
                if active.process.returncode != 0 and active.process.stderr:
                    try:
                        active.view.error = active.process.stderr.read().strip()[-300:] or None
                    except OSError:
                        pass

    def list(self) -> list[TunnelView]:
        with self._lock:
            self._prune_exited_locked()
            return [a.view.model_copy(deep=True) for a in self._tunnels.values()]

    def stop(self, tunnel_id: str) -> TunnelView:
        with self._lock:
            active = self._tunnels.pop(tunnel_id, None)
        if active is None:
            raise ColabctlError(f"Tunnel '{tunnel_id}' not found.")
        self._terminate_proc(active.process)
        active.view.status = "stopped"
        return active.view.model_copy(deep=True)

    def stop_for_session(self, session_name: str) -> int:
        with self._lock:
            matched = [
                tid
                for tid, a in self._tunnels.items()
                if a.view.session == session_name
            ]
            popped = [self._tunnels.pop(tid) for tid in matched]
        for active in popped:
            self._terminate_proc(active.process)
        return len(popped)

    def stop_all(self) -> int:
        with self._lock:
            popped = list(self._tunnels.values())
            self._tunnels.clear()
        for active in popped:
            self._terminate_proc(active.process)
        return len(popped)

    @staticmethod
    def _terminate_proc(proc: subprocess.Popen[str] | None) -> None:
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
