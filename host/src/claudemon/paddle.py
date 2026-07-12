"""Fetch per-product sales stats (purchases, customers, revenue) from Paddle.

Paddle is the 4th cockpit source: macOS product sales. Like the Cloudflare and
GitHub fetchers, parsing is resilient — any HTTP/network failure classifies the
product's state (auth vs err) instead of crashing the dashboard, so one bad
token never blanks the other sources.

TODO(live-api): the Paddle Billing API (https://api.paddle.com) exposes revenue
via `GET /reports` (async report jobs) and raw rows via `GET /transactions` /
`GET /customers`. The exact aggregation (revenue today vs month, per-product
grouping by `product_id`, customer de-duplication) needs a live account to pin
down — Paddle returns money as integer minor units (cents) in a `currency_code`,
and "today"/"month" boundaries must use the account timezone. Until that's wired,
`fetch_all` returns synthetic data (from the design handoff) so the whole
cockpit is testable end-to-end. The synthetic path is gated on the token being
absent OR equal to the sentinel "demo"; a real token flips to `_fetch_live`,
which currently raises NotImplementedError rather than silently faking numbers.
"""

from __future__ import annotations

import logging

from .models import AccountState, PaddleProductStats, PaddleTotals, utcnow

log = logging.getLogger(__name__)

API_BASE = "https://api.paddle.com"

# Sentinel token that forces the synthetic path even when a "token" is present,
# for demos and tests without a live Paddle account.
DEMO_TOKEN = "demo"


def fetch_all(token: str | None, products: list[str]) -> list[PaddleProductStats]:
    """Fetch every configured product. `products` is a list of product display
    names. Never raises — a failure marks the affected rows' state.

    With no token (or the "demo" sentinel) this returns synthetic rows so the
    cockpit renders end-to-end; a real token routes to the live path.
    """
    if not products:
        return []
    if not token or token == DEMO_TOKEN:
        log.info("paddle: no live token — using synthetic sales data")
        return _synthetic(products)
    try:
        return _fetch_live(token, products)
    except NotImplementedError:
        # The live endpoint isn't wired yet (see module TODO). Fail loud in logs
        # but degrade gracefully: the rows report AUTH so the device shows "--".
        log.warning("paddle: live API not implemented; set the token to 'demo' for sample data")
        return [PaddleProductStats(name=p, state=AccountState.AUTH) for p in products]


def combine_totals(products: list[PaddleProductStats]) -> PaddleTotals:
    """Roll per-product rows up into the combined-totals tile. Sums ignore
    unknown (None) fields; the state is the worst state across products so a
    single failed product surfaces on the totals tile."""
    ok = [p for p in products if p.state == AccountState.OK]

    def total(attr: str) -> int | None:
        vals = [getattr(p, attr) for p in ok if getattr(p, attr) is not None]
        return sum(vals) if vals else None

    return PaddleTotals(
        revenue_today=total("revenue_today"),
        revenue_month=total("revenue_month"),
        revenue_month_prev=total("revenue_month_prev"),
        sales=total("purchases"),
        customers=total("customers"),
        state=_worst_state(products),
    )


def _worst_state(products: list[PaddleProductStats]) -> AccountState:
    order = [AccountState.AUTH, AccountState.ERROR, AccountState.DRIFT, AccountState.OK]
    for state in order:
        if any(p.state == state for p in products):
            return state
    return AccountState.OK


def _fetch_live(token: str, products: list[str]) -> list[PaddleProductStats]:
    """Live Paddle Billing API fetch. Not yet implemented — see module TODO."""
    raise NotImplementedError("paddle live API fetch is a Phase-2+ task")


# ---------------------------------------------------------------- synthetic data
# Values mirror the design handoff's Paddle screen so the cockpit renders
# realistically without a live account. Keyed by lowercased product name; an
# unknown product name yields an all-"--" row (state OK, numbers None) rather
# than crashing, so a typo in the sources file is visible on the device.

_SAMPLE = {
    "pixelpeek": dict(category="Utilities", purchases=1284, customers=4102,
                      revenue_today=512, revenue_month=38540, prev_month=34410),
    "cleanshot pro": dict(category="Productivity", purchases=892, customers=2740,
                          revenue_today=318, revenue_month=26180, prev_month=24980),
    "focusbar": dict(category="Productivity", purchases=2410, customers=6980,
                     revenue_today=284, revenue_month=19280, prev_month=16820),
    "snapvault": dict(category="Utilities", purchases=512, customers=1190,
                      revenue_today=134, revenue_month=14720, prev_month=11940),
}


def _synthetic(products: list[str]) -> list[PaddleProductStats]:
    now = utcnow()
    rows: list[PaddleProductStats] = []
    for name in products:
        sample = _SAMPLE.get(name.lower())
        if sample is None:
            rows.append(PaddleProductStats(name=name, fetched_at=now))
            continue
        month = sample["revenue_month"]
        # A 14-point per-day revenue series that averages to month/30, gently
        # ramping so the sparkline has shape. Oldest first.
        series = _ramp(month // 30, points=14)
        rows.append(
            PaddleProductStats(
                name=name,
                category=sample["category"],
                purchases=sample["purchases"],
                customers=sample["customers"],
                revenue_today=sample["revenue_today"],
                revenue_month=month,
                revenue_month_prev=sample["prev_month"],
                revenue_series=series,
                fetched_at=now,
            )
        )
    return rows


def _ramp(mean: int, points: int) -> list[int]:
    """A small deterministic ramp centered on `mean` for demo sparklines."""
    if mean <= 0 or points < 2:
        return []
    half = points // 2
    return [max(0, mean + (i - half) * (mean // points)) for i in range(points)]
