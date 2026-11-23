"""Browser / Chromium App launcher and native macOS Terminal & VS Code openers."""

from __future__ import annotations

import os
import shlex
import shutil
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path

from colabctl.config import AppPaths

MACOS_CHROMIUM_CANDIDATES: tuple[str, ...] = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Arc.app/Contents/MacOS/Arc",
)

LINUX_CHROMIUM_BINS: tuple[str, ...] = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "brave-browser",
    "microsoft-edge",
)


def pick_free_port(preferred: int = 18420) -> int:
    """Return preferred loopback port if free, otherwise ask the OS for an ephemeral port."""
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return int(s.getsockname()[1])
            except OSError:
                continue
    return preferred


def find_chromium_binary() -> str | None:
    if sys.platform == "darwin":
        for path in MACOS_CHROMIUM_CANDIDATES:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    else:
        for name in LINUX_CHROMIUM_BINS:
            found = shutil.which(name)
            if found:
                return found
    # Fallback to Playwright's installed Chromium if available
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            exe = p.chromium.executable_path
            if exe and os.path.isfile(exe):
                return exe
    except Exception:
        pass
    return None


def launch_ui_window(
    url: str,
    *,
    mode: str = "app",
    paths: AppPaths | None = None,
) -> tuple[str, str | None]:
    """Open the dashboard in Chromium --app mode or fallback to system browser.

    Returns (launched_mode, executable_or_note).
    """
    if mode == "none":
        return "none", None

    if mode == "app":
        chrome = find_chromium_binary()
        if chrome:
            app_paths = paths or AppPaths()
            profile_dir = app_paths.config_dir / "chrome-app-profile"
            profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            subprocess.Popen(
                [
                    chrome,
                    f"--app={url}",
                    f"--user-data-dir={profile_dir}",
                    "--window-size=1240,860",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return "chromium-app", chrome

    webbrowser.open(url)
    return "browser", None


def open_native_ssh_terminal(ssh_alias: str, *, colabctl_bin: str, session_name: str) -> str:
    """Open a new local terminal window connected directly to the Colab GPU session."""
    cmd = f"{shlex.quote(colabctl_bin)} ssh {shlex.quote(session_name)}"
    if sys.platform == "darwin":
        # Prefer iTerm2 if running/installed, otherwise Apple Terminal.app
        if Path("/Applications/iTerm.app").exists():
            script = (
                'tell application "iTerm"\n'
                "  activate\n"
                "  create window with default profile\n"
                "  tell current session of current window\n"
                f"    write text {cmd!r}\n"
                "  end tell\n"
                "end tell"
            )
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            if res.returncode == 0:
                return "iTerm"
        escaped = cmd.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            'tell application "Terminal"\n'
            "  activate\n"
            f'  do script "{escaped}"\n'
            "end tell"
        )
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
        return "Terminal.app"

    # Linux fallback
    for term_cmd in (
        ["x-terminal-emulator", "-e", "bash", "-lc", cmd],
        ["gnome-terminal", "--", "bash", "-lc", cmd],
        ["xterm", "-e", cmd],
    ):
        if shutil.which(term_cmd[0]):
            subprocess.Popen(term_cmd, start_new_session=True)
            return term_cmd[0]
    raise RuntimeError(f"No supported terminal emulator found. Run manually: ssh {ssh_alias}")


def open_vscode_remote(ssh_alias: str, remote_dir: str = "/content") -> str:
    """Open VS Code Remote-SSH directly to the Colab VM's /content directory."""
    uri = f"vscode://vscode-remote/ssh-remote+{ssh_alias}{remote_dir}"
    if sys.platform == "darwin":
        subprocess.run(["open", uri], check=True)
        return uri
    if shutil.which("code"):
        subprocess.Popen(["code", "--folder-uri", uri], start_new_session=True)
        return uri
    webbrowser.open(uri)
    return uri
