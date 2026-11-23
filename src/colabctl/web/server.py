"""FastAPI local loopback server for the colabctl management dashboard."""

from __future__ import annotations

import atexit
import hmac
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from colabctl import __version__
from colabctl.models import normalize_high_mem
from colabctl.service import ColabController, ColabctlError
from colabctl.ssh_manager import resolve_colabctl_executable
from colabctl.web.jobs import JobManager
from colabctl.web.launcher import open_native_ssh_terminal, open_vscode_remote
from colabctl.web.tunnels import TunnelManager

STATIC_DIR = Path(__file__).resolve().parent / "static"
TOKEN_COOKIE = "colabctl_token"
TOKEN_HEADER = "x-colabctl-token"


class LaunchSessionRequest(BaseModel):
    name: str = Field(default="dev", min_length=1, max_length=48)
    gpu: str = "t4"
    high_mem: bool = False
    account: str | None = None
    idle_min: int = Field(default=30, ge=0, le=1440)
    max_hours: float = Field(default=4.0, ge=0.0, le=48.0)
    enable_guard: bool = True
    timeout: int = Field(default=120, ge=15, le=600)
    retries: int = Field(default=2, ge=0, le=5)


class ExtendSessionRequest(BaseModel):
    hours: float = Field(default=2.0, gt=0.0, le=24.0)
    idle_min: int | None = Field(default=None, ge=0, le=1440)


class GuardConfigRequest(BaseModel):
    idle_min: int | None = Field(default=None, ge=0, le=1440)
    max_hours: float | None = Field(default=None, ge=0.0, le=48.0)
    disable: bool = False
    enable: bool = False


class SwitchGpuRequest(BaseModel):
    gpu: str
    high_mem: bool = False
    account: str | None = None
    idle_min: int | None = Field(default=None, ge=0, le=1440)
    max_hours: float | None = Field(default=None, ge=0.0, le=48.0)
    enable_guard: bool = True


class SetPrimaryRequest(BaseModel):
    account: str
    threshold: float | None = Field(default=None, ge=0.0)


class SetAccountQuotaRequest(BaseModel):
    quota_cu: float | None = Field(default=None, gt=0.0, le=1_000_000.0)


class ReapOrphanRequest(BaseModel):
    account: str
    endpoint: str


class StartTunnelRequest(BaseModel):
    session: str
    remote_port: int = Field(ge=1, le=65535)
    local_port: int | None = Field(default=None, ge=1, le=65535)
    label: str | None = None


def _is_loopback_host(host_header: str) -> bool:
    host = host_header.split(":", 1)[0].strip().lower()
    return host in ("127.0.0.1", "localhost", "[::1]", "testserver")


def create_app(
    controller: ColabController | None = None,
    *,
    auth_token: str | None = None,
    demo_mode: bool = False,
    default_lang: str = "auto",
) -> FastAPI:
    ctrl = controller or ColabController()
    token = auth_token or secrets.token_urlsafe(24)
    jobs = JobManager()
    tunnels = TunnelManager(ctrl, demo_mode=demo_mode)
    if demo_mode:
        try:
            tunnels.start("dev", remote_port=8188, local_port=8188, label="ComfyUI")
        except ColabctlError:
            pass

    def _cleanup_tunnels() -> None:
        tunnels.stop_all()

    atexit.register(_cleanup_tunnels)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        tunnels.stop_all()

    app = FastAPI(
        title="colabctl Dashboard",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.auth_token = token
    app.state.controller = ctrl
    app.state.jobs = jobs
    app.state.tunnels = tunnels
    app.state.demo_mode = demo_mode

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        host = request.headers.get("host", "")
        if host and not _is_loopback_host(host):
            return JSONResponse(
                {"detail": "Forbidden host header (loopback only)."}, status_code=403
            )
        if request.url.path.startswith("/api/"):
            supplied = (
                request.headers.get(TOKEN_HEADER)
                or request.cookies.get(TOKEN_COOKIE)
                or request.query_params.get("token")
                or ""
            )
            if not hmac.compare_digest(supplied, token):
                return JSONResponse(
                    {"detail": "Unauthorized: missing or invalid local session token."},
                    status_code=401,
                )
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, token_q: str | None = Query(default=None, alias="token")):
        cookie_tok = request.cookies.get(TOKEN_COOKIE, "")
        supplied = token_q or cookie_tok
        if not hmac.compare_digest(supplied, token):
            return HTMLResponse(
                "<html><body style='font-family:system-ui;padding:32px;background:#0b0f17;color:#e5e7eb'>"
                "<h2>colabctl — Unauthorized</h2>"
                "<p>Open this dashboard using the authenticated URL printed by <code>colabctl ui</code>.</p>"
                "</body></html>",
                status_code=401,
            )
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        html = (
            html.replace("__COLABCTL_TOKEN__", token)
            .replace("__COLABCTL_VERSION__", __version__)
            .replace("__COLABCTL_DEMO__", "true" if demo_mode else "false")
            .replace("__COLABCTL_LANG__", default_lang)
        )
        response = HTMLResponse(html)
        response.set_cookie(
            TOKEN_COOKIE,
            token,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return response

    # ------------------------------------------------------------------
    # Read & Diagnostics API
    # ------------------------------------------------------------------

    @app.get("/api/health")
    def api_health() -> dict[str, Any]:
        return {"ok": True, "version": __version__, "demo_mode": demo_mode}

    @app.get("/api/overview")
    def api_overview(live: bool = False, probe_guard: bool = False) -> dict[str, Any]:
        try:
            overview = ctrl.list_overview(live=live, probe_guard=probe_guard)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {
            "version": __version__,
            "demo_mode": demo_mode,
            "overview": overview.model_dump(mode="json"),
            "tunnels": [t.model_dump(mode="json") for t in tunnels.list()],
            "jobs": [j.model_dump(mode="json") for j in jobs.list_recent()],
        }

    @app.get("/api/doctor")
    def api_doctor() -> dict[str, Any]:
        return ctrl.doctor().model_dump(mode="json")

    @app.get("/api/jobs")
    def api_jobs() -> list[dict[str, Any]]:
        return [j.model_dump(mode="json") for j in jobs.list_recent()]

    @app.get("/api/jobs/{job_id}")
    def api_job_detail(job_id: str) -> dict[str, Any]:
        rec = jobs.get(job_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        return rec.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    @app.post("/api/accounts/primary")
    def api_set_primary(req: SetPrimaryRequest) -> dict[str, Any]:
        try:
            ctrl.set_primary(req.account, threshold=req.threshold)
        except ColabctlError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "primary": req.account}

    @app.post("/api/accounts/{name}/quota")
    def api_set_account_quota(name: str, req: SetAccountQuotaRequest) -> dict[str, Any]:
        try:
            quota_cu, quota_source = ctrl.set_account_quota(name, req.quota_cu)
        except ColabctlError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True,
            "account": name,
            "quota_cu": quota_cu,
            "quota_source": quota_source,
        }

    # ------------------------------------------------------------------
    # Sessions Lifecycle (async jobs for slow cloud calls)
    # ------------------------------------------------------------------

    @app.post("/api/sessions")
    def api_launch_session(req: LaunchSessionRequest) -> dict[str, Any]:
        eff_high_mem = normalize_high_mem(req.gpu, req.high_mem)

        def _work() -> dict[str, Any]:
            res = ctrl.up(
                req.name,
                gpu=req.gpu,
                high_mem=eff_high_mem,
                account=req.account or None,
                idle_minutes=req.idle_min,
                max_hours=req.max_hours,
                enable_guard=req.enable_guard,
                assign_timeout_s=req.timeout,
                assign_retries=req.retries,
            )
            return res.model_dump(mode="json")

        rec = jobs.submit(
            kind="up",
            target=req.name,
            title=f"Provisioning '{req.name}' ({req.gpu.upper()}{' High-RAM' if eff_high_mem else ''})",
            fn=_work,
            meta={"gpu": req.gpu.upper(), "high_mem": eff_high_mem},
        )
        return rec.model_dump(mode="json")

    @app.get("/api/sessions/{name}/status")
    def api_session_status(name: str) -> dict[str, Any]:
        try:
            view = ctrl.status(name)
        except ColabctlError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return view.model_dump(mode="json")

    @app.post("/api/sessions/{name}/extend")
    def api_extend_session(name: str, req: ExtendSessionRequest) -> dict[str, Any]:
        try:
            wd = ctrl.extend(name, add_hours=req.hours, idle_minutes=req.idle_min)
        except ColabctlError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return wd.model_dump(mode="json")

    @app.post("/api/sessions/{name}/guard")
    def api_configure_guard(name: str, req: GuardConfigRequest) -> dict[str, Any]:
        try:
            wd = ctrl.configure_guard(
                name,
                idle_minutes=req.idle_min,
                max_hours=req.max_hours,
                disable=req.disable,
                enable=req.enable,
            )
        except ColabctlError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return wd.model_dump(mode="json")

    @app.post("/api/sessions/{name}/reset-ssh")
    def api_reset_ssh(name: str) -> dict[str, Any]:
        try:
            res = ctrl.reset_ssh(name)
            # Re-warm mux immediately so next click is instant
            if not demo_mode and hasattr(ctrl, "store") and hasattr(ctrl, "ssh"):
                meta = ctrl.store.get_session(name)
                if meta is not None:
                    res["rewarmed"], res["rewarm_error"] = ctrl.ssh.warmup_mux(
                        meta.ssh_alias, meta.control_path
                    )
        except ColabctlError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return res

    @app.post("/api/sessions/{name}/switch")
    def api_switch_gpu(name: str, req: SwitchGpuRequest) -> dict[str, Any]:
        eff_high_mem = normalize_high_mem(req.gpu, req.high_mem)

        def _work() -> dict[str, Any]:
            tunnels.stop_for_session(name)
            res = ctrl.switch(
                name,
                gpu=req.gpu,
                high_mem=eff_high_mem,
                account=req.account or None,
                idle_minutes=req.idle_min,
                max_hours=req.max_hours,
                enable_guard=req.enable_guard,
            )
            return res.model_dump(mode="json")

        rec = jobs.submit(
            kind="switch",
            target=name,
            title=f"Switching '{name}' to {req.gpu.upper()}{' High-RAM' if eff_high_mem else ''}",
            fn=_work,
            meta={"gpu": req.gpu.upper(), "high_mem": eff_high_mem},
        )
        return rec.model_dump(mode="json")

    @app.delete("/api/sessions/{name}")
    def api_stop_session(name: str, forget: bool = False) -> dict[str, Any]:
        def _work() -> dict[str, Any]:
            tunnels.stop_for_session(name)
            res = ctrl.stop(name, forget=forget)
            return res.model_dump(mode="json")

        rec = jobs.submit(
            kind="stop",
            target=name,
            title=f"Stopping '{name}' and ending billing",
            fn=_work,
        )
        return rec.model_dump(mode="json")

    @app.post("/api/sessions/stop-all")
    def api_stop_all() -> dict[str, Any]:
        def _work() -> dict[str, Any]:
            tunnels.stop_all()
            results = ctrl.stop_all()
            return {"stopped": [r.model_dump(mode="json") for r in results]}

        rec = jobs.submit(
            kind="stop-all",
            target="all",
            title="Stopping ALL VMs across every account",
            fn=_work,
        )
        return rec.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Orphans
    # ------------------------------------------------------------------

    @app.post("/api/orphans/reap")
    def api_reap_orphan(req: ReapOrphanRequest) -> dict[str, Any]:
        def _work() -> dict[str, Any]:
            ctrl.reap_orphan(req.account, req.endpoint)
            return {"account": req.account, "endpoint": req.endpoint}

        rec = jobs.submit(
            kind="reap",
            target=req.endpoint,
            title=f"Reaping orphan {req.endpoint} on {req.account}",
            fn=_work,
            meta={"account": req.account, "endpoint": req.endpoint},
        )
        return rec.model_dump(mode="json")

    @app.post("/api/orphans/reap-all")
    def api_reap_all_orphans() -> dict[str, Any]:
        def _work() -> dict[str, Any]:
            reaped = ctrl.reap_all_orphans()
            return {"reaped": [o.model_dump(mode="json") for o in reaped]}

        rec = jobs.submit(
            kind="reap-all",
            target="orphans",
            title="Reaping all unmanaged orphan VMs",
            fn=_work,
        )
        return rec.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Tunnels & Native Openers
    # ------------------------------------------------------------------

    @app.get("/api/tunnels")
    def api_list_tunnels() -> list[dict[str, Any]]:
        return [t.model_dump(mode="json") for t in tunnels.list()]

    @app.post("/api/tunnels")
    def api_start_tunnel(req: StartTunnelRequest) -> dict[str, Any]:
        try:
            view = tunnels.start(
                req.session,
                remote_port=req.remote_port,
                local_port=req.local_port,
                label=req.label,
            )
        except ColabctlError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return view.model_dump(mode="json")

    @app.delete("/api/tunnels/{tunnel_id}")
    def api_stop_tunnel(tunnel_id: str) -> dict[str, Any]:
        try:
            view = tunnels.stop(tunnel_id)
        except ColabctlError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return view.model_dump(mode="json")

    @app.post("/api/sessions/{name}/open-terminal")
    def api_open_terminal(name: str) -> dict[str, Any]:
        try:
            meta = ctrl.resolve_ssh_target(name)
            if demo_mode:
                return {
                    "ok": True,
                    "demo": True,
                    "opened_in": "Demo Mode (simulated)",
                    "ssh_alias": meta.ssh_alias,
                }
            opened = open_native_ssh_terminal(
                meta.ssh_alias,
                colabctl_bin=resolve_colabctl_executable(),
                session_name=name,
            )
        except (ColabctlError, Exception) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "opened_in": opened, "ssh_alias": meta.ssh_alias}

    @app.post("/api/sessions/{name}/open-vscode")
    def api_open_vscode(name: str) -> dict[str, Any]:
        try:
            meta = ctrl.resolve_ssh_target(name)
            if demo_mode:
                uri = f"vscode://vscode-remote/ssh-remote+{meta.ssh_alias}/content"
                return {
                    "ok": True,
                    "demo": True,
                    "uri": uri,
                    "ssh_alias": meta.ssh_alias,
                }
            uri = open_vscode_remote(meta.ssh_alias)
        except (ColabctlError, Exception) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "uri": uri, "ssh_alias": meta.ssh_alias}

    return app
