"""Poll/refresh/push loop for `claudemon run`.

Drives the CrowPanel Cockpit: every cycle it fetches all four cockpit sections
(Anthropic + discovered Cloudflare/GitHub + Paddle) through the shared
`collect.DashboardCollector`, renders the `set_cockpit` payload, and pushes it
over serial. Two virtues carried over from the classic e-paper loop:

- **change detection** — only push when the rendered content actually changed,
  so the device isn't spammed by identical frames; and
- **a periodic heartbeat** — push at least every few minutes even when nothing
  changed, so the device's 10-minute STALE overlay never trips.

The cockpit payload carries live-tick fields the device counts down locally
(`base`, per-account `fh_sec`) plus the `updated` clock string; all three change
on every fetch, so they're excluded from the change comparison — otherwise the
clock alone would force a push every cycle.
"""

from __future__ import annotations

import json
import logging
import time

from . import collect, config as configmod, keychain, paddle, render
from .models import AccountUsage, utcnow
from .serial_link import DeviceLink

log = logging.getLogger(__name__)

# The poll cadence comes from config.Settings.refresh (seconds); these bound it.
MIN_REFRESH_S = 15          # floor for the dashboard loop. Anthropic usage is
                            # throttled independently (collect.USAGE_TTL_S ~3min),
                            # so a low refresh only speeds the unthrottled
                            # CF/GitHub/Paddle stats — it can't 429 the usage API.
DEFAULT_REFRESH_S = 60
HEARTBEAT_PUSH_S = 5 * 60   # push at least this often so STALE (10min) never trips

STATE_FILE = keychain.CONFIG_DIR / "state.json"


def _refresh_interval() -> float:
    """Poll/push cadence from config, floored so a misconfig can't hammer the
    APIs. A bad/absent config falls back to the default."""
    try:
        refresh = configmod.load().settings.refresh
    except (ValueError, OSError) as e:
        log.warning("config unreadable; using default refresh %ds: %s", DEFAULT_REFRESH_S, e)
        refresh = DEFAULT_REFRESH_S
    return float(max(MIN_REFRESH_S, refresh))


def _comparable(payload: dict) -> str:
    """Serialize the cockpit params for change-detection, excluding the live-tick
    fields the device re-derives locally every second: `base` (header clock
    seed), `updated` (the HH:MM string), and each account's `fh_sec` AND `fh_rst`
    — the seconds-to-5h-reset and its rendered "3H14M" string. The device counts
    down from `fh_sec` at 1 Hz (UI.cpp) and never displays the host's `fh_rst`,
    so both tick every minute without being meaningful content. Leaving `fh_rst`
    in (the original bug) made it differ every cycle, forcing a content push
    ~once a minute and defeating change-detection. With both excluded, only real
    movement — percents, counts, the renewal day, alerts — triggers an early
    push; otherwise the 5-min heartbeat carries the frame."""
    params = json.loads(json.dumps(payload["params"]))  # deep copy; don't mutate the push payload
    params.pop("base", None)
    params.pop("updated", None)
    for card in params.get("anthropic", {}).get("accounts", []):
        card.pop("fh_sec", None)
        card.pop("fh_rst", None)
    return json.dumps(params, sort_keys=True)


def _build_payload(collector: collect.DashboardCollector, now) -> tuple[dict, list[AccountUsage]]:
    """Collect all four sources and render the set_cockpit payload, wiring the
    admin alert config (usage threshold + down/4xx toggles) in. Never raises —
    the collector already classifies each source's failures into row state."""
    claude, cf, pd, gh = collector.collect()
    totals = paddle.combine_totals(pd)
    settings = _settings()
    payload = render.to_cockpit_payload(
        claude, cf, pd, totals, gh, now,
        usage_threshold=settings.usage_threshold,
        alert_on_down=settings.alert_down,
        alert_on_4xx=settings.alert_4xx,
    )
    return payload, claude


def _settings() -> configmod.Settings:
    try:
        return configmod.load().settings
    except (ValueError, OSError) as e:
        log.warning("config unreadable; using default settings: %s", e)
        return configmod.Settings()


def run_loop() -> None:
    if not keychain.list_accounts():
        log.error("no accounts configured — run `claudemon login <label>` first")
        raise SystemExit(1)

    log.info("starting cockpit poll loop")
    collector = collect.DashboardCollector()
    link = DeviceLink()
    last_pushed: str | None = None
    last_state_sig: str | None = None
    last_push_at = float("-inf")  # monotonic() is uptime-based; 0.0 would gate the
    next_reconnect_at = 0.0       # first push on a machine that just booted
    reconnect_backoff = 2.0

    while True:
        now = utcnow()
        try:
            payload, snapshots = _build_payload(collector, now)
        except Exception as e:  # collection is best-effort; never kill the loop
            log.exception("collection cycle failed; retrying next interval: %s", e)
            time.sleep(_refresh_interval())
            continue

        # State file only changes when the underlying account numbers move; skip
        # the write on cycles that didn't shift anything.
        state_sig = json.dumps([s.to_state_dict() for s in snapshots], sort_keys=True)
        if state_sig != last_state_sig:
            last_state_sig = state_sig
            write_state(snapshots)

        clock = time.monotonic()
        comparable = _comparable(payload)
        changed = comparable != last_pushed
        due_for_heartbeat = (clock - last_push_at) > HEARTBEAT_PUSH_S

        if changed or due_for_heartbeat:
            if not link.connected and clock >= next_reconnect_at:
                if link.connect():
                    reconnect_backoff = 2.0
                else:
                    next_reconnect_at = clock + reconnect_backoff
                    reconnect_backoff = min(reconnect_backoff * 2, 30.0)
                    log.debug("device not found; retrying in %ds", reconnect_backoff)

            if link.connected:
                resp = link.send_command(payload)
                if resp and resp.get("status") == "ok":
                    last_pushed = comparable
                    last_push_at = clock
                    log.log(
                        logging.INFO if changed else logging.DEBUG,
                        "pushed cockpit to device (%s)%s",
                        link.port,
                        "" if changed else " [heartbeat]",
                    )
                else:
                    log.warning("device push failed; will retry next cycle")

        # NOTE: the classic e-paper board spoke set_usage; the daemon now targets
        # the cockpit only. An e-paper deployment would need its own render/push
        # path (render.to_device_payload) — out of scope here.

        time.sleep(_refresh_interval())


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
