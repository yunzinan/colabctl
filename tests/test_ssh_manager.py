"""Unit tests for SSH config management, Include idempotency, and ControlMaster paths."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from colabctl.config import AppPaths, AppSettings
from colabctl.models import LocalSessionMeta
from colabctl.ssh_manager import SshManager, control_socket_path


def test_control_socket_path_stays_short(tmp_path: Path) -> None:
    paths = AppPaths(config_dir=tmp_path / "cfg", ssh_dir=tmp_path / "ssh")
    sock = control_socket_path(paths, "a-very-long-session-name-for-testing-sun-len-limits")
    assert sock.parent == paths.control_dir
    assert sock.name.startswith("c-")
    assert sock.name.endswith(".sock")
    assert len(sock.name) == len("c-") + 12 + len(".sock")


def test_ensure_user_ssh_include_is_idempotent_and_preserves_existing(
    tmp_path: Path,
) -> None:
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir(mode=0o700)
    existing_cfg = "Host my-server\n    HostName 10.0.0.1\n    User alice\n"
    (ssh_dir / "config").write_text(existing_cfg, encoding="utf-8")

    paths = AppPaths(config_dir=tmp_path / "colabctl", ssh_dir=ssh_dir)
    mgr = SshManager(paths, colabctl_bin="/usr/local/bin/colabctl")

    assert not mgr.is_included_in_user_ssh_config()
    changed1 = mgr.ensure_user_ssh_include()
    assert changed1 is True
    assert mgr.is_included_in_user_ssh_config()

    # Backup created with exact original contents
    backup = ssh_dir / "config.bak-colabctl"
    assert backup.read_text(encoding="utf-8") == existing_cfg

    # Original host entries preserved after Include
    updated = (ssh_dir / "config").read_text(encoding="utf-8")
    assert updated.startswith(f"Include {paths.managed_ssh_config}\n")
    assert existing_cfg in updated

    # Second call is a no-op
    changed2 = mgr.ensure_user_ssh_include()
    assert changed2 is False
    assert (ssh_dir / "config").read_text(encoding="utf-8") == updated


def test_render_and_sync_ssh_config_has_controlmaster_and_proxy(tmp_path: Path) -> None:
    paths = AppPaths(config_dir=tmp_path / "colabctl", ssh_dir=tmp_path / ".ssh")
    mgr = SshManager(paths, colabctl_bin="/Users/me/.local/bin/colabctl")
    settings = AppSettings(control_persist="5m")

    ctl = str(control_socket_path(paths, "dev"))
    meta = LocalSessionMeta(
        name="dev",
        ssh_alias="colab-dev",
        account="ultra",
        endpoint="gpu-t4-123",
        gpu_requested="t4",
        identity_file="/Users/me/.ssh/id_ed25519_colab",
        control_path=ctl,
        created_at=datetime.now(UTC),
    )

    out_path = mgr.sync_ssh_config({"dev": meta}, settings)
    text = out_path.read_text(encoding="utf-8")
    assert "Host colab-dev" in text
    assert "ProxyCommand /Users/me/.local/bin/colabctl _proxy dev" in text
    assert "ControlMaster auto" in text
    assert f"ControlPath {ctl}" in text
    assert "ControlPersist 5m" in text
    assert "RemoteCommand" not in text  # must stay scp/rsync/VS Code compatible


def test_interactive_ssh_and_tunnel_argv(tmp_path: Path) -> None:
    paths = AppPaths(config_dir=tmp_path / "colabctl", ssh_dir=tmp_path / ".ssh")
    mgr = SshManager(paths, colabctl_bin="/bin/colabctl")

    interactive = mgr.build_interactive_ssh_argv("colab-dev")
    assert interactive[:4] == ["ssh", "-t", "--", "colab-dev"]
    assert "/content" in interactive[4]

    one_shot = mgr.build_interactive_ssh_argv("colab-dev", ["nvidia-smi", "-L"])
    assert one_shot == ["ssh", "--", "colab-dev", "nvidia-smi -L"]

    quoted = mgr.build_interactive_ssh_argv("colab-dev", ["bash", "-lc", "echo hello world"])
    assert quoted == ["ssh", "--", "colab-dev", "bash -lc 'echo hello world'"]

    single_shell = mgr.build_interactive_ssh_argv("colab-dev", ["ls -la | wc -l"])
    assert single_shell == ["ssh", "--", "colab-dev", "ls -la | wc -l"]

    tunnel = mgr.build_tunnel_argv("colab-dev", 8188, 18188)
    assert tunnel == [
        "ssh",
        "-N",
        "-o",
        "ExitOnForwardFailure=yes",
        "-L",
        "127.0.0.1:18188:127.0.0.1:8188",
        "colab-dev",
    ]
