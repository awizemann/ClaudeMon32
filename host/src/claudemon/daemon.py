"""Poll/refresh/push loop for `claudemon run`."""

from __future__ import annotations

import json
import logging
import time

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
LOOP_TICK_S = 10

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
        self.credentials_gone = False  # Keychain item vanished; prune this account

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
            creds = oauth.load_fresh(self.label)
        except keychain.KeychainNotFoundError:
            log.warning(
                "%s: credentials no longer in the Keychain; removing account", self.label
            )
            self.credentials_gone = True
            self._mark_auth_failed()
            return
        except (keychain.KeychainError, oauth.OAuthError) as e:
            log.warning("%s: %s", self.label, e)
            self._mark_auth_failed()
            return
        except oauth.OAuthTransientError as e:
            log.warning("%s: token refresh error (transient): %s", self.label, e)
            return

        try:
            snap = usage.fetch_usage(self.label, creds)
        except usage.UsageFetchError as e:
            if e.status_code == 401:
                # Token looked valid but was rejected: one forced refresh, then degrade.
                snap = self._forced_refresh_fetch(creds)
                if snap is None:
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

    def _forced_refresh_fetch(self, creds) -> AccountUsage | None:
        """401 with a fresh-looking token: refresh once, retry the fetch.
        Returns the snapshot, or None after classifying the failure."""
        try:
            creds = oauth.refresh(creds)
            keychain.save_account(self.label, creds)
            return usage.fetch_usage(self.label, creds)
        except (oauth.OAuthError, keychain.KeychainError) as e:
            log.warning("%s: unauthorized after forced refresh: %s", self.label, e)
            self._mark_auth_failed()
            return None
        except (oauth.OAuthTransientError, usage.UsageFetchError) as e:
            log.warning("%s: forced refresh/fetch failed (transient): %s", self.label, e)
            return None

    def _mark_auth_failed(self) -> None:
        self.auth_failed = True
        self.snapshot.state = AccountState.AUTH
        self.last_auth_log = time.monotonic()


def _reconcile_runners(runners: dict[str, AccountRunner]) -> None:
    """Sync runners with the account index; pick up login/logout without a
    restart and prune accounts whose Keychain item vanished."""
    for label, runner in list(runners.items()):
        if runner.credentials_gone:
            keychain.delete_account(label)  # prunes the index; item already gone
            del runners[label]
    try:
        current = keychain.list_accounts()
    except keychain.KeychainError as e:
        log.error("account index unreadable; keeping last-known accounts: %s", e)
        return
    for label in current:
        if label not in runners:
            log.info("account added: %s", label)
            runners[label] = AccountRunner(label)
    for label in list(runners):
        if label not in current:
            log.info("account removed: %s", label)
            del runners[label]


def run_loop() -> None:
    labels = keychain.list_accounts()
    if not labels:
        log.error("no accounts configured — run `claudemon login <label>` first")
        raise SystemExit(1)

    log.info("starting poll loop for accounts: %s", ", ".join(labels))
    runners = {label: AccountRunner(label) for label in labels}
    link = DeviceLink()
    last_pushed_payload: str | None = None
    last_state_sig: str | None = None
    last_push_at = float("-inf")  # monotonic() is uptime-based; 0.0 would gate
    next_reconnect_at = 0.0       # the first push on machines that just booted
    reconnect_backoff = 2.0

    while True:
        _reconcile_runners(runners)
        for runner in runners.values():
            runner.poll()

        snapshots = [r.snapshot for r in runners.values()]

        # State file + device payload only change when a poll landed; skip the
        # serialization work on the ~17 idle ticks between polls.
        state_sig = json.dumps(
            [s.to_state_dict() for s in snapshots], sort_keys=True
        )
        if state_sig != last_state_sig:
            last_state_sig = state_sig
            write_state(snapshots)

        now = time.monotonic()
        due_for_change_push = (now - last_push_at) >= MIN_PUSH_GAP_S
        due_for_heartbeat = (now - last_push_at) > HEARTBEAT_PUSH_S

        if due_for_change_push or due_for_heartbeat:
            payload = render.to_device_payload(snapshots, utcnow())
            # Compare without the volatile "updated" clock so only content
            # changes (percentages, countdown strings) trigger an early push.
            comparable = json.dumps({**payload["params"], "updated": ""}, sort_keys=True)
            changed = comparable != last_pushed_payload

            if changed or due_for_heartbeat:
                if not link.connected and now >= next_reconnect_at:
                    if link.connect():
                        reconnect_backoff = 2.0
                    else:
                        next_reconnect_at = now + reconnect_backoff
                        reconnect_backoff = min(reconnect_backoff * 2, 30.0)
                        log.debug("device not found; retrying in %ds", reconnect_backoff)

                if link.connected:
                    resp = link.send_command(payload)
                    if resp and resp.get("status") == "ok":
                        last_pushed_payload = comparable
                        last_push_at = now
                        log.log(
                            logging.INFO if changed else logging.DEBUG,
                            "pushed usage to device (%s)%s",
                            link.port,
                            "" if changed else " [heartbeat]",
                        )
                    else:
                        log.warning("device push failed; will retry next cycle")

        time.sleep(LOOP_TICK_S)


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
