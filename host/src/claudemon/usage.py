"""Fetch and parse the OAuth usage endpoint (5-hour and weekly windows).

This is the endpoint Claude Code's /usage panel reads. It is undocumented, so
parsing is deliberately defensive: unknown shapes degrade to None fields and a
DRIFT flag rather than exceptions, and the raw JSON is logged for inspection.
Use `claudemon probe <label>` to see the live response and verify the schema.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx

from .models import AccountCredentials, AccountState, AccountUsage, WindowUsage, utcnow

log = logging.getLogger(__name__)

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
BETA_HEADER = "oauth-2025-04-20"

# Key aliases observed/expected for each window, checked in order.
FIVE_HOUR_KEYS = ("five_hour", "5h", "fiveHour", "session")
WEEK_KEYS = ("seven_day", "week", "sevenDay", "seven_day_overall", "weekly")
# Opus/model-specific weekly buckets some plans report; used as fallback only.
WEEK_FALLBACK_KEYS = ("seven_day_sonnet", "seven_day_opus", "seven_day_oauth_apps")
UTILIZATION_KEYS = ("utilization", "used_pct", "usage", "percent")
RESET_KEYS = ("resets_at", "reset_at", "resetsAt", "reset")


class UsageFetchError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _headers(creds: AccountCredentials) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {creds.access_token}",
        "anthropic-beta": BETA_HEADER,
        "Content-Type": "application/json",
    }


def probe(creds: AccountCredentials) -> tuple[int, dict[str, str], str]:
    """Raw fetch for schema inspection. Returns (status, headers, body-text)."""
    resp = httpx.get(USAGE_URL, headers=_headers(creds), timeout=30)
    return resp.status_code, dict(resp.headers), resp.text


def fetch_usage(label: str, creds: AccountCredentials) -> AccountUsage:
    """Fetch usage for one account. Raises UsageFetchError on HTTP/network failure."""
    try:
        resp = httpx.get(USAGE_URL, headers=_headers(creds), timeout=30)
    except httpx.HTTPError as e:
        raise UsageFetchError(f"network error: {e}") from e

    if resp.status_code == 401:
        raise UsageFetchError("unauthorized", status_code=401)
    if resp.status_code != 200:
        raise UsageFetchError(
            f"HTTP {resp.status_code}: {resp.text[:300]}", status_code=resp.status_code
        )

    try:
        data = resp.json()
    except json.JSONDecodeError as e:
        raise UsageFetchError(f"non-JSON body: {resp.text[:300]}") from e

    return parse_usage(label, data)


def parse_usage(label: str, data: dict) -> AccountUsage:
    """Best-effort parse. Never raises; flags DRIFT when windows can't be found.

    Verified schema (2026-07-04): top-level "five_hour"/"seven_day" objects with
    utilization (0-100 float) + resets_at (ISO). A parallel "limits" array
    (kind: "session"/"weekly_all", percent, resets_at) is used as fallback.
    """
    five_hour = _find_window(data, FIVE_HOUR_KEYS)
    week = _find_window(data, WEEK_KEYS) or _find_window(data, WEEK_FALLBACK_KEYS)

    if five_hour is None:
        five_hour = _find_limit(data, ("session",))
    if week is None:
        week = _find_limit(data, ("weekly_all", "weekly"))

    drift = five_hour is None or week is None
    if drift:
        log.warning(
            "usage schema drift for %s — raw response: %s",
            label,
            json.dumps(data)[:2000],
        )

    return AccountUsage(
        label=label,
        five_hour=five_hour or WindowUsage(),
        week=week or WindowUsage(),
        state=AccountState.DRIFT if drift else AccountState.OK,
        fetched_at=utcnow(),
    )


def _find_limit(data: dict, kinds: tuple[str, ...]) -> WindowUsage | None:
    """Fallback: read the "limits" array (kind/percent/resets_at entries)."""
    limits = data.get("limits")
    if not isinstance(limits, list):
        return None
    for entry in limits:
        if isinstance(entry, dict) and entry.get("kind") in kinds:
            pct = entry.get("percent")
            return WindowUsage(
                pct=_normalize_pct(pct) if isinstance(pct, (int, float)) else None,
                resets_at=_parse_timestamp(entry.get("resets_at")),
            )
    return None


def _find_window(data: dict, keys: tuple[str, ...]) -> WindowUsage | None:
    for key in keys:
        node = data.get(key)
        if isinstance(node, dict):
            win = _parse_window(node)
            if win is not None:
                return win
    return None


def _parse_window(node: dict) -> WindowUsage | None:
    pct = None
    for key in UTILIZATION_KEYS:
        if key in node and isinstance(node[key], (int, float)):
            pct = _normalize_pct(node[key])
            break
    resets_at = None
    for key in RESET_KEYS:
        if key in node and node[key] is not None:
            resets_at = _parse_timestamp(node[key])
            break
    if pct is None and resets_at is None:
        return None
    return WindowUsage(pct=pct, resets_at=resets_at)


def _normalize_pct(value: float) -> int:
    # Schema verified 2026-07-04: utilization is a 0-100 float (11.0 == 11%).
    # Do NOT treat <=1 values as fractions — a real 1% arrives as 1.0.
    return max(0, min(100, round(value)))


def _parse_timestamp(value) -> datetime | None:
    if isinstance(value, (int, float)):
        # epoch seconds or milliseconds
        ts = value / 1000 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None
