"""FastAPI local management dashboard security, API, job, tunnel, and demo-mode tests."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from colabctl import __version__
from colabctl.web.demo import DemoColabController
from colabctl.web.server import TOKEN_COOKIE, TOKEN_HEADER, create_app
from tests.test_service import _make_controller


def _wait_for_job(client: TestClient, headers: dict[str, str], job_id: str, timeout_s: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = client.get(f"/api/jobs/{job_id}", headers=headers)
        assert r.status_code == 200
        data = r.json()
        if data["status"] != "running":
            return data
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} did not finish within {timeout_s}s")


def test_security_host_and_token_enforcement(tmp_path: Path) -> None:
    ctrl, _, _ = _make_controller(tmp_path)
    app = create_app(ctrl, auth_token="secret-local-token")
    client = TestClient(app)

    # Non-loopback Host header blocked (DNS rebinding guard)
    r_bad_host = client.get("/api/overview", headers={"host": "evil.example.com", TOKEN_HEADER: "secret-local-token"})
    assert r_bad_host.status_code == 403

    # Missing / wrong token rejected on / and /api/*
    assert client.get("/").status_code == 401
    assert client.get("/?token=wrong").status_code == 401
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/overview", headers={TOKEN_HEADER: "wrong"}).status_code == 401

    # Valid ?token=... on / renders HTML with placeholders substituted and sets HttpOnly cookie
    r_index = client.get("/?token=secret-local-token")
    assert r_index.status_code == 200
    assert "secret-local-token" in r_index.text
    assert __version__ in r_index.text
    assert "__COLABCTL_TOKEN__" not in r_index.text
    assert "__COLABCTL_VERSION__" not in r_index.text
    assert r_index.cookies.get(TOKEN_COOKIE) == "secret-local-token"

    # Subsequent API request succeeds via cookie automatically
    r_ov = client.get("/api/overview")
    assert r_ov.status_code == 200
    assert r_ov.json()["overview"]["primary"] == "ultra"


def test_api_session_lifecycle_jobs_and_orphans(tmp_path: Path) -> None:
    ctrl, pool, _ = _make_controller(tmp_path)
    pool.orphans.append({"account": "ultra", "endpoint": "ep-orphan-1", "hardware": "T4"})
    app = create_app(ctrl, auth_token="tok123")
    headers = {TOKEN_HEADER: "tok123"}

    with TestClient(app) as client:
        # Doctor & primary switch
        r_doc = client.get("/api/doctor", headers=headers)
        assert r_doc.status_code == 200
        assert r_doc.json()["accounts_count"] == 2

        r_pri = client.post("/api/accounts/primary", headers=headers, json={"account": "pro1"})
        assert r_pri.status_code == 200
        assert pool.primary == "pro1"

        # Launch session (async job)
        r_up = client.post(
            "/api/sessions",
            headers=headers,
            json={"name": "work", "gpu": "t4", "idle_min": 25, "max_hours": 3.0},
        )
        assert r_up.status_code == 200
        job = _wait_for_job(client, headers, r_up.json()["id"])
        assert job["status"] == "succeeded"
        assert job["result"]["session"]["ssh_alias"] == "colab-work"

        # Probe single session status
        r_st = client.get("/api/sessions/work/status", headers=headers)
        assert r_st.status_code == 200
        assert r_st.json()["watchdog_live"]["running"] is True

        # Extend & guard disable/enable
        r_ext = client.post("/api/sessions/work/extend", headers=headers, json={"hours": 2.0})
        assert r_ext.status_code == 200
        assert r_ext.json()["running"] is True

        r_off = client.post("/api/sessions/work/guard", headers=headers, json={"disable": True})
        assert r_off.status_code == 200
        assert r_off.json()["cancelled"] is True

        # Reset SSH
        r_rst = client.post("/api/sessions/work/reset-ssh", headers=headers)
        assert r_rst.status_code == 200
        assert r_rst.json()["rewarmed"] is True

        # Switch GPU (async job)
        r_sw = client.post(
            "/api/sessions/work/switch",
            headers=headers,
            json={"gpu": "l4", "high_mem": False},
        )
        assert r_sw.status_code == 200
        sw_job = _wait_for_job(client, headers, r_sw.json()["id"])
        assert sw_job["status"] == "succeeded"
        assert sw_job["result"]["session"]["accelerator"] == "L4"

        # Reserved port 8080 rejected by tunnel validation
        r_tun_bad = client.post(
            "/api/tunnels",
            headers=headers,
            json={"session": "work", "remote_port": 8080},
        )
        assert r_tun_bad.status_code == 400
        assert "reserved" in r_tun_bad.json()["detail"].lower()

        # Reap all orphans
        r_reap = client.post("/api/orphans/reap-all", headers=headers)
        assert r_reap.status_code == 200
        reap_job = _wait_for_job(client, headers, r_reap.json()["id"])
        assert reap_job["status"] == "succeeded"
        assert len(reap_job["result"]["reaped"]) == 1
        assert pool.orphans == []

        # Stop session
        r_stop = client.delete("/api/sessions/work", headers=headers)
        assert r_stop.status_code == 200
        stop_job = _wait_for_job(client, headers, r_stop.json()["id"])
        assert stop_job["status"] == "succeeded"
        assert stop_job["result"]["stopped"] is True


def test_demo_mode_end_to_end() -> None:
    ctrl = DemoColabController(simulated_delay_s=0.0)
    app = create_app(ctrl, auth_token="demo-tok", demo_mode=True)
    headers = {TOKEN_HEADER: "demo-tok"}

    with TestClient(app) as client:
        r_ov = client.get("/api/overview", headers=headers)
        assert r_ov.status_code == 200
        data = r_ov.json()
        assert data["demo_mode"] is True
        assert len(data["overview"]["accounts"]) == 3
        assert len(data["overview"]["sessions"]) == 2
        assert len(data["overview"]["orphans"]) == 1
        # Pre-seeded ComfyUI tunnel on dev
        assert len(data["tunnels"]) == 1
        assert data["tunnels"][0]["remote_port"] == 8188

        # Open terminal & VS Code in demo mode do not shell out
        r_term = client.post("/api/sessions/dev/open-terminal", headers=headers)
        assert r_term.status_code == 200
        assert r_term.json()["demo"] is True

        r_vs = client.post("/api/sessions/dev/open-vscode", headers=headers)
        assert r_vs.status_code == 200
        assert r_vs.json()["demo"] is True

        # Start & stop a second demo tunnel
        r_tun = client.post(
            "/api/tunnels",
            headers=headers,
            json={"session": "dev", "remote_port": 6006, "label": "TensorBoard"},
        )
        assert r_tun.status_code == 200
        tid = r_tun.json()["id"]
        r_del = client.delete(f"/api/tunnels/{tid}", headers=headers)
        assert r_del.status_code == 200

        # Stop all clears sessions, orphans, and tunnels
        r_sa = client.post("/api/sessions/stop-all", headers=headers)
        assert r_sa.status_code == 200
        sa_job = _wait_for_job(client, headers, r_sa.json()["id"])
        assert sa_job["status"] == "succeeded"

        r_ov2 = client.get("/api/overview", headers=headers)
        assert r_ov2.json()["overview"]["sessions"] == []
        assert r_ov2.json()["overview"]["orphans"] == []
        assert r_ov2.json()["tunnels"] == []


def test_api_g4_strips_high_mem_and_renders_disconnect_banner(tmp_path: Path) -> None:
    ctrl, pool, _ = _make_controller(tmp_path)
    app = create_app(ctrl, auth_token="tok-g4")
    headers = {TOKEN_HEADER: "tok-g4"}

    with TestClient(app) as client:
        # Index includes disconnect banner, language switcher, and High-RAM hint ids
        r_idx = client.get("/?token=tok-g4")
        assert r_idx.status_code == 200
        assert 'id="disconnect-banner"' in r_idx.text
        assert 'id="btn-lang"' in r_idx.text
        assert 'defaultLang: "auto"' in r_idx.text
        assert "__COLABCTL_LANG__" not in r_idx.text
        assert 'id="launch-high-mem-hint"' in r_idx.text
        assert 'id="switch-gpu-picker"' in r_idx.text

        # Static i18n module is served cleanly
        r_i18n = client.get("/static/i18n.js")
        assert r_i18n.status_code == 200
        assert '"zh-CN"' in r_i18n.text

        # Launching G4 with high_mem=True strips high_mem in title & controller call
        r_up = client.post(
            "/api/sessions",
            headers=headers,
            json={"name": "pro6k", "gpu": "g4", "high_mem": True},
        )
        assert r_up.status_code == 200
        assert "High-RAM" not in r_up.json()["title"]
        assert r_up.json()["meta"] == {"gpu": "G4", "high_mem": False}
        job = _wait_for_job(client, headers, r_up.json()["id"])
        assert job["status"] == "succeeded"
        assert pool.new_calls[-1]["gpu"] == "g4"
        assert pool.new_calls[-1]["high_mem"] is False

        # Switching to G4 with high_mem=True also strips high_mem
        r_sw = client.post(
            "/api/sessions/pro6k/switch",
            headers=headers,
            json={"gpu": "g4", "high_mem": True},
        )
        assert r_sw.status_code == 200
        assert "High-RAM" not in r_sw.json()["title"]
        assert r_sw.json()["meta"] == {"gpu": "G4", "high_mem": False}
        sw_job = _wait_for_job(client, headers, r_sw.json()["id"])
        assert sw_job["status"] == "succeeded"
        assert pool.new_calls[-1]["high_mem"] is False


def test_default_lang_injection(tmp_path: Path) -> None:
    ctrl, _, _ = _make_controller(tmp_path)
    app = create_app(ctrl, auth_token="tok-zh", default_lang="zh-CN")
    client = TestClient(app)
    r = client.get("/?token=tok-zh")
    assert r.status_code == 200
    assert 'defaultLang: "zh-CN"' in r.text


def test_api_account_quota_override_and_demo_mode(tmp_path: Path) -> None:
    # Real controller: overview includes inferred quotas, POST updates & resets
    ctrl, _, _ = _make_controller(tmp_path)
    app = create_app(ctrl, auth_token="tok-q")
    headers = {TOKEN_HEADER: "tok-q"}
    with TestClient(app) as client:
        r_idx = client.get("/?token=tok-q")
        assert 'id="modal-quota"' in r_idx.text

        ov = client.get("/api/overview", headers=headers).json()["overview"]
        accs = {a["name"]: a for a in ov["accounts"]}
        assert accs["ultra"]["quota_cu"] == 2500.0
        assert accs["pro1"]["quota_cu"] == 200.0

        r_set = client.post("/api/accounts/pro1/quota", headers=headers, json={"quota_cu": 500})
        assert r_set.status_code == 200
        assert r_set.json() == {
            "ok": True,
            "account": "pro1",
            "quota_cu": 500.0,
            "quota_source": "custom",
        }
        ov2 = client.get("/api/overview", headers=headers).json()["overview"]
        assert {a["name"]: a for a in ov2["accounts"]}["pro1"]["quota_cu"] == 500.0

        r_reset = client.post("/api/accounts/pro1/quota", headers=headers, json={"quota_cu": None})
        assert r_reset.status_code == 200
        assert r_reset.json()["quota_cu"] == 200.0
        assert r_reset.json()["quota_source"] == "inferred"

    # Demo controller also supports per-account quota inspection & editing
    demo_ctrl = DemoColabController(simulated_delay_s=0.0)
    demo_app = create_app(demo_ctrl, auth_token="tok-dq", demo_mode=True)
    d_headers = {TOKEN_HEADER: "tok-dq"}
    with TestClient(demo_app) as client:
        d_ov = client.get("/api/overview", headers=d_headers).json()["overview"]
        d_accs = {a["name"]: a for a in d_ov["accounts"]}
        assert d_accs["ultra"]["quota_cu"] == 2500.0
        assert d_accs["pro1"]["quota_cu"] == 200.0
        assert d_accs["pro1"]["balance"] == 222.52  # above 200 CU baseline
        assert d_accs["pro2"]["quota_cu"] == 200.0

        r_dset = client.post("/api/accounts/pro1/quota", headers=d_headers, json={"quota_cu": 100})
        assert r_dset.status_code == 200
        assert r_dset.json()["quota_cu"] == 100.0
        assert r_dset.json()["quota_source"] == "custom"
