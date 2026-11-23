"""Configuration, filesystem layout, and local metadata storage for colabctl."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from colabctl.models import LocalSessionMeta

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "colabctl"
DEFAULT_SSH_DIR = Path.home() / ".ssh"

PREFERRED_IDENTITY_NAMES: tuple[str, ...] = (
    "id_ed25519_colab",
    "id_ed25519",
    "id_ecdsa",
)


class AppSettings(BaseModel):
    default_gpu: str = "t4"
    default_high_mem: bool = False
    default_idle_min: int = 30
    default_max_hours: float = 4.0
    ssh_alias_prefix: str = "colab-"
    control_persist: str = "5m"
    identity_file: str | None = None
    assign_timeout_s: int = 120
    assign_retries: int = 2
    account_quotas: dict[str, float] = Field(default_factory=dict)


class AppPaths:
    """Resolved filesystem paths for colabctl state and SSH config."""

    def __init__(
        self,
        config_dir: Path | None = None,
        ssh_dir: Path | None = None,
    ) -> None:
        env_dir = os.environ.get("COLABCTL_CONFIG_DIR")
        self.config_dir = (
            config_dir
            if config_dir is not None
            else (Path(env_dir).expanduser() if env_dir else DEFAULT_CONFIG_DIR)
        )
        self.ssh_dir = ssh_dir if ssh_dir is not None else DEFAULT_SSH_DIR

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def sessions_file(self) -> Path:
        return self.config_dir / "sessions.json"

    @property
    def managed_ssh_config(self) -> Path:
        return self.config_dir / "ssh_config"

    @property
    def control_dir(self) -> Path:
        return self.config_dir / "ctl"

    @property
    def user_ssh_config(self) -> Path:
        return self.ssh_dir / "config"

    def ensure_dirs(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.config_dir, 0o700)
        self.control_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.control_dir, 0o700)


def atomic_write_private(path: Path, content: str, mode: int = 0o600) -> None:
    """Write a file atomically with owner-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def resolve_identity_file(
    explicit: str | None = None,
    settings: AppSettings | None = None,
    ssh_dir: Path | None = None,
) -> Path | None:
    """Find an Ed25519/ECDSA private key path accepted by Colab SSH."""
    base_ssh = ssh_dir or DEFAULT_SSH_DIR
    candidates: list[Path] = []
    if explicit:
        p = Path(explicit).expanduser()
        if p.suffix == ".pub":
            p = p.with_suffix("")
        candidates.append(p)
    if settings and settings.identity_file:
        p = Path(settings.identity_file).expanduser()
        if p.suffix == ".pub":
            p = p.with_suffix("")
        candidates.append(p)
    for name in PREFERRED_IDENTITY_NAMES:
        candidates.append(base_ssh / name)

    for path in candidates:
        if path.is_file():
            return path
    return None


class LocalStore:
    """Stores colabctl-specific session metadata (hardware, watchdog, SSH alias)."""

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def load_settings(self) -> AppSettings:
        if not self.paths.settings_file.exists():
            return AppSettings()
        try:
            data = json.loads(self.paths.settings_file.read_text(encoding="utf-8"))
            return AppSettings.model_validate(data)
        except (OSError, ValueError):
            return AppSettings()

    def save_settings(self, settings: AppSettings) -> None:
        self.paths.ensure_dirs()
        atomic_write_private(
            self.paths.settings_file,
            settings.model_dump_json(indent=2) + "\n",
        )

    def load_sessions(self) -> dict[str, LocalSessionMeta]:
        if not self.paths.sessions_file.exists():
            return {}
        try:
            raw: dict[str, Any] = json.loads(
                self.paths.sessions_file.read_text(encoding="utf-8")
            )
            result: dict[str, LocalSessionMeta] = {}
            for name, entry in raw.items():
                try:
                    result[name] = LocalSessionMeta.model_validate(entry)
                except ValueError:
                    continue
            return result
        except (OSError, ValueError):
            return {}

    def save_sessions(self, sessions: dict[str, LocalSessionMeta]) -> None:
        self.paths.ensure_dirs()
        payload = {
            name: meta.model_dump(mode="json") for name, meta in sorted(sessions.items())
        }
        atomic_write_private(
            self.paths.sessions_file,
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        )

    def get_session(self, name: str) -> LocalSessionMeta | None:
        return self.load_sessions().get(name)

    def upsert_session(self, meta: LocalSessionMeta) -> None:
        sessions = self.load_sessions()
        sessions[meta.name] = meta
        self.save_sessions(sessions)

    def delete_session(self, name: str) -> bool:
        sessions = self.load_sessions()
        if name not in sessions:
            return False
        del sessions[name]
        self.save_sessions(sessions)
        return True
