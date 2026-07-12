"""Fetch per-zone traffic analytics from the Cloudflare GraphQL Analytics API.

One POST to https://api.cloudflare.com/client/v4/graphql with a Bearer token
that has the **Analytics:Read** permission for the zone(s). We read the
`httpRequests1dGroups` dataset (available on the Free plan, daily granularity)
and sum the returned day-groups over a short window:

    sum { requests bytes cachedRequests threats }
    uniq { uniques }

Like the Claude usage fetcher, parsing is resilient: any HTTP/GraphQL failure
classifies the zone's state (auth vs err) instead of crashing the dashboard, so
one bad token never blanks the other sources.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import httpx

from .http import client
from .models import AccountState, CloudflareZoneStats, utcnow

log = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"

_QUERY = """
query ($zoneTag: String!, $since: Date!, $until: Date!) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {
      httpRequests1dGroups(
        limit: 7
        filter: {date_geq: $since, date_leq: $until}
        orderBy: [date_ASC]
      ) {
        dimensions { date }
        sum {
          requests bytes cachedRequests threats
          responseStatusMap { edgeResponseStatus requests }
        }
        uniq { uniques }
      }
    }
  }
}
"""


def _bucket_status(groups: list) -> dict[str, int]:
    """Roll the per-status request counts up into 2xx/3xx/4xx/5xx buckets."""
    buckets = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}
    for g in groups:
        for entry in g["sum"].get("responseStatusMap") or []:
            code = entry.get("edgeResponseStatus", 0)
            key = f"{code // 100}xx"
            if key in buckets:
                buckets[key] += entry.get("requests", 0)
    return {k: v for k, v in buckets.items() if v} or {}


def fetch_zone(token: str, zone_id: str, name: str, window_days: int = 7) -> CloudflareZoneStats:
    """Fetch one zone's rolled-up stats. Never raises — returns a stats object
    whose `state` reflects any failure (AUTH for a bad/absent token, ERR for a
    transient or schema problem)."""
    stats = CloudflareZoneStats(name=name)
    now = utcnow()
    variables = {
        "zoneTag": zone_id,
        "since": (now - timedelta(days=window_days - 1)).date().isoformat(),
        "until": now.date().isoformat(),
    }

    try:
        resp = client.post(
            GRAPHQL_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": _QUERY, "variables": variables},
        )
    except httpx.HTTPError as e:
        log.warning("cloudflare %s: network error: %s", name, e)
        stats.state = AccountState.ERROR
        return stats

    if resp.status_code in (401, 403):
        log.warning("cloudflare %s: token rejected (HTTP %s)", name, resp.status_code)
        stats.state = AccountState.AUTH
        return stats
    if resp.status_code != 200:
        log.warning("cloudflare %s: HTTP %s: %s", name, resp.status_code, resp.text[:200])
        stats.state = AccountState.ERROR
        return stats

    body = resp.json()
    if body.get("errors"):
        messages = "; ".join(e.get("message", "") for e in body["errors"])
        # Authentication/authorization errors come back 200 with an errors array.
        is_auth = "authenticat" in messages.lower() or "not authorized" in messages.lower()
        log.warning("cloudflare %s: GraphQL errors: %s", name, messages[:200])
        stats.state = AccountState.AUTH if is_auth else AccountState.ERROR
        return stats

    zones = (((body.get("data") or {}).get("viewer") or {}).get("zones")) or []
    if not zones:
        log.warning("cloudflare %s: zone tag %s not visible to this token", name, zone_id)
        stats.state = AccountState.ERROR
        return stats

    groups = zones[0].get("httpRequests1dGroups") or []
    stats.requests = sum(g["sum"]["requests"] for g in groups)
    stats.bytes = sum(g["sum"]["bytes"] for g in groups)
    stats.cached_requests = sum(g["sum"]["cachedRequests"] for g in groups)
    stats.threats = sum(g["sum"]["threats"] for g in groups)
    stats.unique_visitors = sum(g["uniq"]["uniques"] for g in groups)
    stats.requests_series = [g["sum"]["requests"] for g in groups]  # per-day, oldest first
    stats.status = _bucket_status(groups)
    stats.fetched_at = now
    return stats


def fetch_all(token: str, zones) -> list[CloudflareZoneStats]:
    """Fetch every configured zone. `zones` is an iterable of CloudflareZone."""
    return [fetch_zone(token, z.id, z.name) for z in zones]
