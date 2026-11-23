"""CLI command parsing and JSON output tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from colabctl import __version__, cli
from colabctl.models import DoctorReport
from tests.test_service import _make_controller

runner = CliRunner()


def test_cli_version() -> None:
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0
    assert f"colabctl {__version__}" in result.stdout


def test_cli_ls_and_up_and_stop_json(tmp_path: Path, monkeypatch) -> None:
    ctrl, _, _ = _make_controller(tmp_path)
    monkeypatch.setattr(cli, "_controller", lambda: ctrl)

    # Empty ls --json
    r_ls = runner.invoke(cli.app, ["ls", "--json"])
    assert r_ls.exit_code == 0
    data = json.loads(r_ls.stdout)
    assert data["primary"] == "ultra"
    assert data["sessions"] == []

    # up --json
    r_up = runner.invoke(cli.app, ["up", "demo", "--gpu", "t4", "--idle-min", "25", "--json"])
    assert r_up.exit_code == 0
    up_data = json.loads(r_up.stdout)
    assert up_data["session"]["ssh_alias"] == "colab-demo"
    assert up_data["watchdog_deployed"] is True

    # status --json
    r_st = runner.invoke(cli.app, ["status", "demo", "--json"])
    assert r_st.exit_code == 0
    st_data = json.loads(r_st.stdout)
    assert st_data["watchdog_live"]["running"] is True

    # stop --json
    r_stop = runner.invoke(cli.app, ["stop", "demo", "--json"])
    assert r_stop.exit_code == 0
    assert json.loads(r_stop.stdout)["stopped"] is True


def test_cli_doctor_json(tmp_path: Path, monkeypatch) -> None:
    ctrl, _, _ = _make_controller(tmp_path)
    monkeypatch.setattr(cli, "_controller", lambda: ctrl)

    r_doc = runner.invoke(cli.app, ["doctor", "--json"])
    # ssh_config_included is False before first `up`, so exit 1 with valid JSON report
    report = DoctorReport.model_validate_json(r_doc.stdout)
    assert report.accounts_count == 2
    assert report.primary_account == "ultra"


def test_cli_ssh_passes_remote_command_without_double_dash_leak(
    tmp_path: Path, monkeypatch
) -> None:
    ctrl, _, _ = _make_controller(tmp_path)
    ctrl.up("demo", gpu="t4")
    monkeypatch.setattr(cli, "_controller", lambda: ctrl)

    captured: list[list[str]] = []

    class DummyProc:
        returncode = 0

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda argv: captured.append(list(argv)) or DummyProc(),
    )

    r1 = runner.invoke(cli.app, ["ssh", "demo", "--", "nvidia-smi", "-L"])
    assert r1.exit_code == 0
    assert captured[-1] == ["ssh", "--", "colab-demo", "nvidia-smi -L"]

    r2 = runner.invoke(cli.app, ["ssh", "demo"])
    assert r2.exit_code == 0
    assert captured[-1][:4] == ["ssh", "-t", "--", "colab-demo"]

