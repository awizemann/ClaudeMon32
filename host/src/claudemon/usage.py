"""Fetch and parse the OAuth usage endpoint (5-hour and weekly windows).

This is the endpoint Claude Code's /usage panel reads. Schema verified live
2026-07-04 (see `claudemon probe`):

    {"five_hour": {"utilization": 11.0, "resets_at": "<ISO8601>", ...},
     "seven_day": {"utilization": 63.0, "resets_at": "<ISO8601>", ...},
     "limits": [{"kind": "session"|"weekly_all"|..., "percent": 11,
                 "resets_at": "<ISO8601>", ...}, ...],
     ...}

utilization is a 0-100 float (11.0 == 11%). Parsing is pinned to exactly this
shape plus the verified "limits" array as fallback — deliberately NO guessed
alias keys: an unrecognized response must trip DRIFT (which logs the raw body)
rather than half-match and render wrong numbers as healthy.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx

from .http import client
from .models import AccountCredentials, AccountState, AccountUsage, WindowUsage, utcnow

log = logging.getLogger(__name__)

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
BETA_HEADER = "oauth-2025-04-20"


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
    resp = client.get(USAGE_URL, headers=_headers(creds))
    return resp.status_code, dict(resp.headers), resp.text


def fetch_usage(label: str, creds: AccountCredentials) -> AccountUsage:
    """Fetch usage for one account. Raises UsageFetchError on HTTP/network failure."""
    try:
        resp = client.get(USAGE_URL, headers=_headers(creds))
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
    """Parse the verified schema. Never raises; flags DRIFT when a window
    can't be found in either the top-level objects or the limits[] array."""
    five_hour = _parse_window(data.get("five_hour")) or _find_limit(data, ("session",))
    week = _parse_window(data.get("seven_day")) or _find_limit(data, ("weekly_all",))

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


def _parse_window(node) -> WindowUsage | None:
    """Top-level window object: {"utilization": 0-100, "resets_at": ISO}."""
    if not isinstance(node, dict):
        return None
    utilization = node.get("utilization")
    pct = _normalize_pct(utilization) if isinstance(utilization, (int, float)) else None
    resets_at = _parse_timestamp(node.get("resets_at"))
    if pct is None and resets_at is None:
        return None
    return WindowUsage(pct=pct, resets_at=resets_at)


def _find_limit(data: dict, kinds: tuple[str, ...]) -> WindowUsage | None:
    """Fallback: the "limits" array ({"kind", "percent", "resets_at"} entries)."""
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


def _normalize_pct(value: float) -> int:
    # utilization/percent are 0-100 (11.0 == 11%). Do NOT treat <=1 values as
    # fractions — a real 1% arrives as 1.0.
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
