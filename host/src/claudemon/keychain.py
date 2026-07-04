"""macOS Keychain storage for per-account OAuth credentials.

Uses /usr/bin/security directly (not the `keyring` package) so the Keychain
item ACL is bound to the stable `security` binary rather than a venv Python
path — a venv rebuild would otherwise trigger authorization prompts, which is
fatal for an unattended launchd agent.

All items live under service "claudemon" (account = user-chosen label).
This module must never touch Claude Code's own "Claude Code-credentials" item.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .models import AccountCredentials

SERVICE = "claudemon"
CONFIG_DIR = Path.home() / ".claudemon"
INDEX_FILE = CONFIG_DIR / "accounts.json"

SECURITY = "/usr/bin/security"


class KeychainError(RuntimeError):
    pass


class KeychainNotFoundError(KeychainError):
    """The item does not exist (vs. locked/denied) — safe to self-heal the index."""


# `security` exit status for errSecItemNotFound
_SEC_ITEM_NOT_FOUND_RC = 44


def _run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run([SECURITY, *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise KeychainError(
            f"security {args[0]} failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )
    return proc


def save_account(label: str, creds: AccountCredentials) -> None:
    _run(
        [
            "add-generic-password",
            "-U",  # update if exists
            "-s", SERVICE,
            "-a", label,
            "-l", f"ClaudeMon ({label})",
            "-w", creds.to_json(),
        ]
    )
    _index_add(label)


def load_account(label: str) -> AccountCredentials:
    proc = _run(["find-generic-password", "-s", SERVICE, "-a", label, "-w"], check=False)
    if proc.returncode == _SEC_ITEM_NOT_FOUND_RC:
        raise KeychainNotFoundError(f"No stored credentials for account '{label}'")
    if proc.returncode != 0:
        raise KeychainError(
            f"Keychain read failed for '{label}' (rc={proc.returncode}): {proc.stderr.strip()}"
        )
    return AccountCredentials.from_json(proc.stdout.strip())


def delete_account(label: str) -> None:
    _run(["delete-generic-password", "-s", SERVICE, "-a", label], check=False)
    _index_remove(label)


def list_accounts() -> list[str]:
    """Read the label index. A missing index means no accounts; an unreadable
    one is an error — silently returning [] would make the daemon stop polling
    every account while valid credentials still sit in the Keychain."""
    if not INDEX_FILE.exists():
        return []
    try:
        data = json.loads(INDEX_FILE.read_text())
        return sorted(data.get("accounts", []))
    except (json.JSONDecodeError, OSError) as e:
        raise KeychainError(
            f"Account index {INDEX_FILE} is unreadable ({e}); "
            f"fix or delete it, then re-run `claudemon login` for each account"
        ) from e


def _write_index(labels: list[str]) -> None:
    CONFIG_DIR.mkdir(mode=0o700, exist_ok=True)
    INDEX_FILE.write_text(json.dumps({"accounts": sorted(set(labels))}, indent=2) + "\n")


def _index_add(label: str) -> None:
    labels = list_accounts()
    if label not in labels:
        labels.append(label)
    _write_index(labels)


def _index_remove(label: str) -> None:
    _write_index([l for l in list_accounts() if l != label])
