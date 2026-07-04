"""Poll/refresh/push loop for `claudemon run`."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from . import keychain, oauth, render, usage
from .models import AccountState, AccountUsage, utcnow
from .serial_link import DeviceLink

log = logging.getLogger(__name__)

POLL_INTERVAL_S = 180       # 60s drew steady HTTP 429s with 3 accounts
MIN_PUSH_GAP_S = 150        # countdown strings tick every minute; don't chase them
HEARTBEAT_PUSH_S = 5 * 60
ERROR_THRESHOLD = 3
BACKOFF_BASE_S = 60
BACKOFF_MAX_S = 300
RATE_LIMIT_BACKOFF_S = 300
RECONNECT_BASE_S = 2
RECONNECT_MAX_S = 30

STATE_FILE = keychain.CONFIG_DIR / "state.json"


class AccountRunner:
    """Per-account poll state: snapshot, failures, backoff, auth health."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.snapshot: AccountUsage = AccountUsage(label=label, state=AccountState.ERROR)
        self.consecutive_failures = 0
        self.next_poll_at = 0.0
        self.auth_failed = False
        self.last_auth_log = 0.0

    def poll(self) -> None:
        now = time.monotonic()
        if now < self.next_poll_at:
            return
        self.next_poll_at = now + POLL_INTERVAL_S

        if self.auth_failed:
            # Log at most hourly; re-login is a manual step.
            if now - self.last_auth_log > 3600:
                log.warning("%s: auth failed — run `claudemon login %s`", self.label, self.label)
                self.last_auth_log = now
            return

        try:
            creds = keychain.load_account(self.label)
        except keychain.KeychainError as e:
            log.error("%s: %s", self.label, e)
            self._mark_auth_failed()
            return

        if creds.expires_within():
            try:
                creds = oauth.refresh(creds)
                keychain.save_account(self.label, creds)  # rotated token — persist NOW
            except oauth.OAuthError as e:
                log.warning("%s: token refresh rejected: %s", self.label, e)
                self._mark_auth_failed()
                return
            except Exception as e:  # network etc. — transient, retry next cycle
                log.warning("%s: token refresh error (transient): %s", self.label, e)
                return

        try:
            snap = usage.fetch_usage(self.label, creds)
        except usage.UsageFetchError as e:
            if e.status_code == 401:
                # Token looked valid but was rejected: one forced refresh, then degrade.
                try:
                    creds = oauth.refresh(creds)
                    keychain.save_account(self.label, creds)
                    snap = usage.fetch_usage(self.label, creds)
                except (oauth.OAuthError, usage.UsageFetchError) as e2:
                    log.warning("%s: unauthorized after forced refresh: %s", self.label, e2)
                    self._mark_auth_failed()
                    return
            elif e.status_code == 429:
                # Throttled, not broken: keep the last snapshot healthy and
                # slow down without escalating toward ERROR.
                self.next_poll_at = now + RATE_LIMIT_BACKOFF_S
                log.info("%s: rate limited; backing off %ds", self.label, RATE_LIMIT_BACKOFF_S)
                return
            else:
                self.consecutive_failures += 1
                backoff = min(BACKOFF_BASE_S * (2 ** (self.consecutive_failures - 1)), BACKOFF_MAX_S)
                self.next_poll_at = now + backoff
                log.warning(
                    "%s: fetch failed (%d consecutive, backoff %ds): %s",
                    self.label, self.consecutive_failures, backoff, e,
                )
                if self.consecutive_failures >= ERROR_THRESHOLD:
                    self.snapshot.state = AccountState.ERROR
                return

        self.consecutive_failures = 0
        self.snapshot = snap

    def _mark_auth_failed(self) -> None:
        self.auth_failed = True
        self.snapshot.state = AccountState.AUTH
        self.last_auth_log = time.monotonic()


def run_loop(foreground: bool = False) -> None:
    labels = keychain.list_accounts()
    if not labels:
        log.error("no accounts configured — run `claudemon login <label>` first")
        raise SystemExit(1)

    log.info("starting poll loop for accounts: %s", ", ".join(labels))
    runners = {label: AccountRunner(label) for label in labels}
    link = DeviceLink()
    last_pushed_payload: str | None = None
    last_push_at = 0.0
    next_reconnect_at = 0.0
    reconnect_backoff = RECONNECT_BASE_S

    while True:
        # Pick up accounts added/removed via `claudemon login/logout` without
        # requiring an agent restart.
        current = keychain.list_accounts()
        for label in current:
            if label not in runners:
                log.info("account added: %s", label)
                runners[label] = AccountRunner(label)
        for label in list(runners):
            if label not in current:
                log.info("account removed: %s", label)
                del runners[label]

        for runner in runners.values():
            runner.poll()

        snapshots = [r.snapshot for r in runners.values()]
        write_state(snapshots)

        payload = render.to_device_payload(snapshots, utcnow())
        # Compare without the volatile "updated" clock so only real changes push
        # early; the heartbeat keeps device staleness detection honest.
        comparable = json.dumps({**payload["params"], "updated": ""}, sort_keys=True)
        now = time.monotonic()
        changed = comparable != last_pushed_payload
        should_push = (changed and (now - last_push_at) >= MIN_PUSH_GAP_S) or (
            now - last_push_at
        ) > HEARTBEAT_PUSH_S

        if should_push:
            if not link.connected and now >= next_reconnect_at:
                if link.connect():
                    reconnect_backoff = RECONNECT_BASE_S
                else:
                    next_reconnect_at = now + reconnect_backoff
                    reconnect_backoff = min(reconnect_backoff * 2, RECONNECT_MAX_S)
                    log.debug("device not found; retrying in %ds", reconnect_backoff)

            if link.connected:
                resp = link.send_command(payload)
                if resp and resp.get("status") == "ok":
                    last_pushed_payload = comparable
                    last_push_at = now
                    log.info("pushed usage to device (%s)", link.port)
                else:
                    log.warning("device push failed; will retry next cycle")

        time.sleep(5 if foreground else 10)


def write_state(snapshots: list[AccountUsage]) -> None:
    """Debug/status cache — labels + numbers only, never tokens."""
    try:
        keychain.CONFIG_DIR.mkdir(mode=0o700, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(
                {
                    "written_at": utcnow().isoformat(),
                    "accounts": [s.to_state_dict() for s in snapshots],
                },
                indent=2,
            )
            + "\n"
        )
    except OSError as e:
        log.warning("could not write state file: %s", e)


def read_state() -> dict | None:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None
