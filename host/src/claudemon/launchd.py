"""launchd LaunchAgent install/uninstall for the background poller."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

LABEL = "com.claudemon.agent"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / "Library" / "Logs" / "claudemon"
LOG_FILE = LOG_DIR / "claudemon.log"


def _claudemon_executable() -> str:
    """Absolute path to the claudemon console script in the current venv."""
    candidate = Path(sys.executable).parent / "claudemon"
    if candidate.exists():
        return str(candidate)
    found = shutil.which("claudemon")
    if found:
        return found
    raise RuntimeError("could not locate the claudemon executable for the agent plist")


def install() -> str:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [_claudemon_executable(), "run"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "StandardOutPath": str(LOG_FILE),
        "StandardErrorPath": str(LOG_FILE),
    }
    PLIST_PATH.write_bytes(plistlib.dumps(plist))

    domain = f"gui/{os.getuid()}"
    # Re-bootstrap cleanly if already loaded.
    subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True)
    proc = subprocess.run(
        ["launchctl", "bootstrap", domain, str(PLIST_PATH)], capture_output=True, text=True
    )
    if proc.returncode != 0:
        # Fallback for older macOS
        proc = subprocess.run(
            ["launchctl", "load", str(PLIST_PATH)], capture_output=True, text=True
        )
        if proc.returncode != 0:
            raise RuntimeError(f"launchctl failed: {proc.stderr.strip()}")
    return str(PLIST_PATH)


def uninstall() -> None:
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True)
    PLIST_PATH.unlink(missing_ok=True)


def is_running() -> bool:
    proc = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"], capture_output=True
    )
    return proc.returncode == 0
