"""Fetch per-product sales stats (purchases, customers, revenue) from Paddle.

Paddle is the 4th cockpit source: macOS product sales. Like the Cloudflare and
GitHub fetchers, parsing is resilient — any HTTP/network failure classifies the
product's state (auth vs err) instead of crashing the dashboard, so one bad
token never blanks the other sources.

Live API: this targets **Paddle Billing** (the modern platform, base URL
https://api.paddle.com, `Authorization: Bearer <API key>`) — NOT Paddle Classic.

  * Discovery — `GET /products` (id, name, status), paginated via
    `meta.pagination.has_more` + the `meta.pagination.next` cursor URL.
  * Sales — `GET /transactions?status=completed`, filtered server-side to the
    current + prior calendar month with a `created_at[GTE]=<iso8601>` filter so
    we never pull the full history. Each transaction carries
    `details.totals.grand_total` (money in MINOR units, i.e. integer cents) plus
    a `currency_code`, a `customer_id`, `created_at`, and `items[]` whose
    `price.product_id` maps a line to a product. Paginated via the same cursor.

Money: Paddle returns integer minor units in `currency_code`. We divide by 100
to get whole currency units for the device's `fmt_money`. This is correct for
2-decimal currencies (USD/EUR/GBP/...); zero-decimal currencies (e.g. JPY, KRW)
would be over-divided — see `_MINOR_UNIT_DIVISOR` / TODO(zero-decimal).

Timezone: month/today boundaries use **UTC**. Paddle's `created_at` is RFC3339
UTC, and the account's configured reporting timezone isn't exposed by these two
endpoints without an extra settings call. TODO(account-tz): if we later read the
seller's timezone, shift the day/month boundaries to it.

The synthetic path (token absent OR the "demo" sentinel) is preserved for demos
and tests so the whole cockpit renders end-to-end without a live account.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

import httpx

from .http import client
from .models import AccountState, PaddleProductStats, PaddleTotals, utcnow

log = logging.getLogger(__name__)

API_BASE = "https://api.paddle.com"
PRODUCTS_URL = f"{API_BASE}/products"
TRANSACTIONS_URL = f"{API_BASE}/transactions"

# Sentinel token that forces the synthetic path even when a "token" is present,
# for demos and tests without a live Paddle account.
DEMO_TOKEN = "demo"

# Paddle money is integer minor units. 100 minor units == 1 whole unit for the
# common 2-decimal currencies (USD, EUR, GBP, ...). TODO(zero-decimal): JPY/KRW
# and friends are already whole units in Paddle, so this would over-divide them;
# revisit once we track per-currency exponents from `currency_code`.
_MINOR_UNIT_DIVISOR = 100

# Page sizes: Paddle caps per_page at 200 (products) / 100+ (transactions). We
# request the max to minimise round-trips.
_PRODUCTS_PER_PAGE = 200
_TRANSACTIONS_PER_PAGE = 100


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
    return _fetch_live(token, products)


def list_products(token: str) -> list[str]:
    """Discover every product this token can see, as display names in stable
    (API) order. Mirrors `cloudflare.list_zones` / `github.list_repos`.

    Never raises — returns [] on auth/network/shape failure and logs, so a
    discovery hiccup degrades to "nothing found" rather than crashing the fetch.
    """
    names: list[str] = []
    for product in _iter_products(token):
        name = product.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name)
    return names


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


# ------------------------------------------------------------------ live fetch


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class _AuthError(Exception):
    """Token rejected (HTTP 401/403) — maps to AccountState.AUTH."""


class _FetchError(Exception):
    """Transient/shape failure — maps to AccountState.ERROR."""


def _get(url: str, token: str, params: dict | None = None) -> dict:
    """One Paddle GET. Raises _AuthError on 401/403, _FetchError on any other
    non-200, network error, or unparseable body. Paddle wraps every response as
    `{"data": ..., "meta": ...}`."""
    try:
        resp = client.get(url, headers=_headers(token), params=params)
    except httpx.HTTPError as e:
        raise _FetchError(f"network error: {e}") from e

    if resp.status_code in (401, 403):
        raise _AuthError(f"token rejected (HTTP {resp.status_code})")
    if resp.status_code != 200:
        raise _FetchError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        body = resp.json()
    except ValueError as e:
        raise _FetchError(f"unparseable response: {e}") from e
    if not isinstance(body, dict):
        raise _FetchError("unexpected response shape (not an object)")
    return body


def _iter_pages(url: str, token: str, params: dict):
    """Yield each page's `data` list, following Paddle's cursor pagination
    (`meta.pagination.has_more` + `meta.pagination.next`, a full URL). The first
    request carries `params`; subsequent hops use the `next` URL as-is (it already
    embeds the cursor + filters), so we drop our params after the first page.

    Bounded by a page cap so a malformed `has_more`/`next` can never loop forever.
    """
    next_url: str | None = url
    next_params: dict | None = params
    for _ in range(1000):  # hard stop: 1000 pages is far beyond any real account
        if not next_url:
            return
        body = _get(next_url, token, next_params)
        data = body.get("data")
        yield data if isinstance(data, list) else []

        pagination = (body.get("meta") or {}).get("pagination") or {}
        if not pagination.get("has_more"):
            return
        nxt = pagination.get("next")
        if not nxt or not isinstance(nxt, str):
            return
        next_url, next_params = nxt, None
    log.warning("paddle: pagination exceeded 1000 pages; stopping (possible API loop)")


def _iter_products(token: str):
    """Yield every product object, resilient. Logs + returns nothing on failure
    (used by discovery, which must never raise)."""
    try:
        for page in _iter_pages(
            PRODUCTS_URL, token, {"per_page": _PRODUCTS_PER_PAGE}
        ):
            yield from (p for p in page if isinstance(p, dict))
    except _AuthError as e:
        log.warning("paddle list_products: %s", e)
    except _FetchError as e:
        log.warning("paddle list_products: %s", e)


def _parse_dt(value: str | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    """(current-month-start, prior-month-start) in UTC, both tz-aware. Used both
    as the server-side `created_at[GTE]` filter (prior-month-start) and to bucket
    each transaction into this month vs the prior calendar month."""
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 1:
        prev_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prev_start = month_start.replace(month=month_start.month - 1)
    return month_start, prev_start


def _minor_to_whole(minor: int) -> int:
    """Minor units (cents) -> whole currency units, rounded to the nearest whole
    unit (the device shows whole-dollar figures, no cents)."""
    return round(minor / _MINOR_UNIT_DIVISOR)


def _line_amounts(txn: dict) -> dict[str, int]:
    """Split a transaction's revenue (minor units) across the products its line
    items touch, keyed by product_id.

    Preferred: each `item` carries its own `totals.total`, so a multi-product
    transaction attributes each line to its own product. Fallback: a single-item
    transaction (or items without per-line totals) attributes the whole
    `details.totals.grand_total` to the item's product.
    """
    items = txn.get("items") or []
    per_product: dict[str, int] = defaultdict(int)

    # Try per-line totals first.
    line_total_seen = False
    for item in items:
        if not isinstance(item, dict):
            continue
        pid = ((item.get("price") or {}).get("product_id"))
        if not pid:
            continue
        totals = item.get("totals") or {}
        raw = totals.get("total")
        if raw is None:
            continue
        try:
            per_product[pid] += int(raw)
            line_total_seen = True
        except (TypeError, ValueError):
            continue

    if line_total_seen:
        return dict(per_product)

    # Fallback: no per-line totals — attribute the grand_total. Distinct product
    # ids share it evenly so a multi-product transaction still credits each.
    grand = ((txn.get("details") or {}).get("totals") or {}).get("grand_total")
    try:
        grand_val = int(grand)
    except (TypeError, ValueError):
        return {}
    pids = []
    for item in items:
        if not isinstance(item, dict):
            continue
        pid = ((item.get("price") or {}).get("product_id"))
        if pid and pid not in pids:
            pids.append(pid)
    if not pids:
        return {}
    share = grand_val // len(pids)
    return {pid: share for pid in pids}


def _fetch_live(token: str, products: list[str]) -> list[PaddleProductStats]:
    """Live Paddle Billing fetch. Never raises — on any auth/fetch failure every
    requested product row gets the appropriate state (AUTH/ERROR) so the other
    three cockpit sources keep rendering.

    Only products whose display name is in `products` are returned, matched
    case-insensitively to the discovered product catalogue."""
    now = utcnow()
    month_start, prev_start = _month_bounds(now)

    # 1) Product catalogue: name -> id (only the requested products) and the
    #    reverse id -> requested-name for grouping.
    try:
        catalogue = list(_iter_pages(PRODUCTS_URL, token, {"per_page": _PRODUCTS_PER_PAGE}))
    except _AuthError as e:
        log.warning("paddle: %s", e)
        return [PaddleProductStats(name=p, state=AccountState.AUTH) for p in products]
    except _FetchError as e:
        log.warning("paddle: %s", e)
        return [PaddleProductStats(name=p, state=AccountState.ERROR) for p in products]

    wanted = {p.lower(): p for p in products}  # lowercased display name -> as-requested
    id_to_name: dict[str, str] = {}  # product_id -> requested display name
    for page in catalogue:
        for prod in page:
            if not isinstance(prod, dict):
                continue
            pid, name = prod.get("id"), prod.get("name")
            if pid and isinstance(name, str) and name.lower() in wanted:
                id_to_name[pid] = wanted[name.lower()]

    # 2) Completed transactions since the prior-month start (server-side filter).
    try:
        pages = list(
            _iter_pages(
                TRANSACTIONS_URL,
                token,
                {
                    "status": "completed",
                    "per_page": _TRANSACTIONS_PER_PAGE,
                    # Paddle's RFC3339 date-range filter; only pull the current +
                    # prior calendar month rather than all history.
                    "created_at[GTE]": prev_start.isoformat().replace("+00:00", "Z"),
                    "order_by": "created_at[ASC]",
                },
            )
        )
    except _AuthError as e:
        log.warning("paddle: %s", e)
        return [PaddleProductStats(name=p, state=AccountState.AUTH) for p in products]
    except _FetchError as e:
        log.warning("paddle: %s", e)
        return [PaddleProductStats(name=p, state=AccountState.ERROR) for p in products]

    # 3) Aggregate per requested product (keyed by requested display name).
    agg = {p: _Agg() for p in products}
    today = now.date()
    for page in pages:
        for txn in page:
            if not isinstance(txn, dict):
                continue
            created = _parse_dt(txn.get("created_at"))
            if created is None:
                continue
            # Guard the lower bound (server should have filtered, but be safe).
            if created < prev_start:
                continue
            in_month = created >= month_start
            in_prev = prev_start <= created < month_start
            customer = txn.get("customer_id")

            for pid, minor in _line_amounts(txn).items():
                name = id_to_name.get(pid)
                if name is None:
                    continue  # a product we weren't asked to track
                a = agg[name]
                whole = _minor_to_whole(minor)
                if in_prev:
                    a.revenue_prev += whole
                    continue
                if not in_month:
                    continue
                # current month-to-date
                a.purchases += 1
                a.revenue_month += whole
                if customer:
                    a.customers.add(customer)
                if created.date() == today:
                    a.revenue_today += whole
                a.day_revenue[created.date()] += whole

    return [_row_from_agg(name, agg[name], month_start, now) for name in products]


class _Agg:
    def __init__(self) -> None:
        self.purchases = 0
        self.revenue_month = 0
        self.revenue_today = 0
        self.revenue_prev = 0
        self.customers: set = set()
        self.day_revenue: dict = defaultdict(int)


def _row_from_agg(
    name: str, a: _Agg, month_start: datetime, now: datetime
) -> PaddleProductStats:
    # Per-day revenue series for the sparkline: one point per day of the current
    # month so far, oldest first (0 for days with no sales).
    series: list[int] = []
    day = month_start.date()
    end = now.date()
    while day <= end:
        series.append(a.day_revenue.get(day, 0))
        day = day.fromordinal(day.toordinal() + 1)
    return PaddleProductStats(
        name=name,
        purchases=a.purchases,
        customers=len(a.customers),
        revenue_today=a.revenue_today,
        revenue_month=a.revenue_month,
        revenue_month_prev=a.revenue_prev,
        revenue_series=series,
        state=AccountState.OK,
        fetched_at=now,
    )


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
