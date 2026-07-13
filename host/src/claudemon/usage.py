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


def fetch_org_id(creds: AccountCredentials) -> str | None:
    """The organization this grant belongs to (for duplicate-login detection).
    Best-effort: returns None on any failure."""
    try:
        resp = client.get(USAGE_URL, headers=_headers(creds))
        return resp.headers.get("anthropic-organization-id")
    except httpx.HTTPError:
        return None


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
    can't be found in either the top-level objects or the limits[] array.

    Each window's pct/resets_at come from the top-level object when present
    (falling back to its limits[] entry), and its `severity` comes from the
    matching limits[] entry — the server's own classification, which the device
    prefers over a client-side pct threshold. The scoped weekly limit
    ("weekly_scoped") has no top-level object and is read from limits[] only."""
    by_kind: dict[str, dict] = {}
    for entry in data.get("limits") or []:
        kind = entry.get("kind") if isinstance(entry, dict) else None
        if kind and kind not in by_kind:
            by_kind[kind] = entry

    five_hour = _window(data.get("five_hour"), by_kind.get("session"))
    week = _window(data.get("seven_day"), by_kind.get("weekly_all"))
    week_scoped = _window(None, by_kind.get("weekly_scoped"))

    drift = five_hour is None or week is None
    if drift:
        log.warning(
            "usage schema drift for %s — raw response: %s",
            label,
            json.dumps(data)[:2000],
        )

    enabled, used, limit = _credits(data.get("spend"))
    return AccountUsage(
        label=label,
        five_hour=five_hour or WindowUsage(),
        week=week or WindowUsage(),
        week_scoped=week_scoped or WindowUsage(),
        credits_enabled=enabled,
        credits_used=used,
        credits_limit=limit,
        state=AccountState.DRIFT if drift else AccountState.OK,
        fetched_at=utcnow(),
    )


def _credits(spend) -> tuple[bool, float | None, float | None]:
    """Extra-usage credits from the `spend` object. Returns (enabled, used$,
    limit$) — amounts converted from minor units to whole currency units.
    Disabled/absent spend reads as (False, None, None)."""
    if not isinstance(spend, dict) or not spend.get("enabled"):
        return False, None, None

    def dollars(node) -> float | None:
        if not isinstance(node, dict):
            return None
        amount = node.get("amount_minor")
        if not isinstance(amount, (int, float)):
            return None
        exp = node.get("exponent")
        return amount / (10 ** exp) if isinstance(exp, int) else float(amount)

    return True, dollars(spend.get("used")), dollars(spend.get("limit"))


def _window(node, limit) -> WindowUsage | None:
    """Merge one usage window from its top-level object and its limits[] entry.

    `node` is the top-level `{"utilization", "resets_at"}` object (or None) and
    `limit` is the matching `{"percent", "resets_at", "severity"}` limits[] entry
    (or None). pct/resets_at prefer the object and fall back to the limit;
    severity comes from the limit. Returns None only when nothing at all was
    found (so a missing scoped limit stays empty without tripping drift)."""
    pct: int | None = None
    resets_at = None
    severity: str | None = None

    if isinstance(node, dict):
        utilization = node.get("utilization")
        if isinstance(utilization, (int, float)):
            pct = _normalize_pct(utilization)
        resets_at = _parse_timestamp(node.get("resets_at"))

    active = False
    if isinstance(limit, dict):
        if pct is None and isinstance(limit.get("percent"), (int, float)):
            pct = _normalize_pct(limit["percent"])
        if resets_at is None:
            resets_at = _parse_timestamp(limit.get("resets_at"))
        if isinstance(limit.get("severity"), str):
            severity = limit["severity"]
        active = bool(limit.get("is_active"))

    if pct is None and resets_at is None and severity is None:
        return None
    return WindowUsage(pct=pct, resets_at=resets_at, severity=severity, active=active)


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
