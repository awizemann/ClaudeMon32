"""Tests for the Paddle fetcher: synthetic data, totals rollup, MoM, unknown
products, live-API discovery + transaction aggregation, and resilient states."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from claudemon import paddle
from claudemon.models import AccountState, PaddleProductStats


class TestFetchAll:
    def test_no_products_is_empty(self):
        assert paddle.fetch_all(None, []) == []

    def test_no_token_uses_synthetic(self):
        rows = paddle.fetch_all(None, ["PixelPeek", "FocusBar"])
        assert [r.name for r in rows] == ["PixelPeek", "FocusBar"]
        assert all(r.state == AccountState.OK for r in rows)
        px = rows[0]
        assert px.purchases == 1284
        assert px.customers == 4102
        assert px.revenue_month == 38540
        assert px.revenue_series  # non-empty sparkline

    def test_demo_sentinel_forces_synthetic(self):
        rows = paddle.fetch_all(paddle.DEMO_TOKEN, ["PixelPeek"])
        assert rows[0].purchases == 1284

    def test_unknown_product_is_blank_not_crash(self):
        rows = paddle.fetch_all(None, ["NotARealApp"])
        row = rows[0]
        assert row.name == "NotARealApp"
        assert row.state == AccountState.OK
        assert row.purchases is None
        assert row.revenue_month is None
        assert row.revenue_series == []

    def test_live_token_routes_to_live_fetch(self, monkeypatch):
        # A real token routes to _fetch_live (mocked here); the synthetic path is
        # only for None/"demo".
        sentinel = [PaddleProductStats(name="PixelPeek", purchases=7)]
        monkeypatch.setattr(paddle, "_fetch_live", lambda tok, prods: sentinel)
        rows = paddle.fetch_all("live-real-token", ["PixelPeek"])
        assert rows[0].purchases == 7


class TestCombineTotals:
    def test_sums_across_products(self):
        rows = paddle.fetch_all(None, ["PixelPeek", "CleanShot Pro", "FocusBar", "SnapVault"])
        totals = paddle.combine_totals(rows)
        assert totals.sales == 1284 + 892 + 2410 + 512
        assert totals.customers == 4102 + 2740 + 6980 + 1190
        assert totals.revenue_month == 38540 + 26180 + 19280 + 14720
        assert totals.revenue_today == 512 + 318 + 284 + 134
        assert totals.state == AccountState.OK

    def test_mom_pct_is_signed_whole_percent(self):
        # One product, month 110 vs prev 100 -> +10%.
        row = PaddleProductStats(
            name="X", purchases=1, customers=1,
            revenue_month=110, revenue_month_prev=100,
        )
        assert paddle.combine_totals([row]).mom_pct == 10

    def test_mom_none_without_baseline(self):
        row = PaddleProductStats(name="X", revenue_month=100, revenue_month_prev=None)
        assert paddle.combine_totals([row]).mom_pct is None

    def test_mom_none_when_prev_zero(self):
        row = PaddleProductStats(name="X", revenue_month=100, revenue_month_prev=0)
        assert paddle.combine_totals([row]).mom_pct is None

    def test_all_unknown_products_give_none_totals(self):
        rows = [PaddleProductStats(name="X"), PaddleProductStats(name="Y")]
        totals = paddle.combine_totals(rows)
        assert totals.sales is None
        assert totals.revenue_month is None

    def test_worst_state_surfaces_on_totals(self):
        rows = [
            PaddleProductStats(name="ok", purchases=1, state=AccountState.OK),
            PaddleProductStats(name="bad", state=AccountState.AUTH),
        ]
        totals = paddle.combine_totals(rows)
        assert totals.state == AccountState.AUTH
        # AUTH rows are excluded from the sums (only OK rows counted).
        assert totals.sales == 1


# ------------------------------------------------------------------ live API


class FakeClient:
    """Stand-in for the shared httpx.Client. Serves queued httpx.Response objects
    (or Exceptions to raise) in order; records each GET's url + params."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, params=None):
        self.calls.append({"url": url, "params": params})
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def _resp(body, status=200, url=paddle.PRODUCTS_URL):
    return httpx.Response(status, json=body, request=httpx.Request("GET", url))


def _products_page(products, has_more=False, next_url=None):
    return _resp(
        {
            "data": [{"id": pid, "name": name, "status": "active"} for pid, name in products],
            "meta": {"pagination": {"has_more": has_more, "next": next_url}},
        },
        url=paddle.PRODUCTS_URL,
    )


def _txn(created, grand_total, customer_id, items, status="completed", currency="USD"):
    """Build a Paddle transaction. `items` is [(product_id, line_total_or_None)]."""
    return {
        "id": f"txn_{created}",
        "status": status,
        "created_at": created,
        "customer_id": customer_id,
        "currency_code": currency,
        "details": {"totals": {"grand_total": str(grand_total), "currency_code": currency}},
        "items": [
            {
                "price": {"product_id": pid},
                **({"totals": {"total": str(lt)}} if lt is not None else {}),
            }
            for pid, lt in items
        ],
    }


def _txns_page(txns, has_more=False, next_url=None):
    return _resp(
        {"data": txns, "meta": {"pagination": {"has_more": has_more, "next": next_url}}},
        url=paddle.TRANSACTIONS_URL,
    )


@pytest.fixture
def frozen_now(monkeypatch):
    """Freeze 'now' at 2026-07-12 UTC so month/prev boundaries are deterministic.
    Current month = July 2026 (starts 2026-07-01); prior = June 2026."""
    now = datetime(2026, 7, 12, 15, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(paddle, "utcnow", lambda: now)
    return now


class TestListProducts:
    def test_single_page(self, monkeypatch):
        fake = FakeClient([_products_page([("pro_1", "PixelPeek"), ("pro_2", "FocusBar")])])
        monkeypatch.setattr(paddle, "client", fake)
        assert paddle.list_products("tok") == ["PixelPeek", "FocusBar"]
        assert len(fake.calls) == 1

    def test_paginates_via_cursor(self, monkeypatch):
        next_url = f"{paddle.PRODUCTS_URL}?after=pro_1"
        fake = FakeClient([
            _products_page([("pro_1", "PixelPeek")], has_more=True, next_url=next_url),
            _products_page([("pro_2", "FocusBar")]),
        ])
        monkeypatch.setattr(paddle, "client", fake)
        assert paddle.list_products("tok") == ["PixelPeek", "FocusBar"]
        assert len(fake.calls) == 2
        # First hop carries our params; second reuses the cursor URL, params dropped.
        assert fake.calls[0]["params"]["per_page"] == paddle._PRODUCTS_PER_PAGE
        assert fake.calls[1]["url"] == next_url
        assert fake.calls[1]["params"] is None

    def test_product_without_name_skipped(self, monkeypatch):
        fake = FakeClient([
            _resp({"data": [{"id": "pro_1"}, {"id": "pro_2", "name": "FocusBar"}],
                   "meta": {"pagination": {"has_more": False}}})
        ])
        monkeypatch.setattr(paddle, "client", fake)
        assert paddle.list_products("tok") == ["FocusBar"]

    def test_auth_failure_returns_empty(self, monkeypatch):
        fake = FakeClient([_products_page([], has_more=False)])
        fake._responses = [_resp({}, status=403)]
        monkeypatch.setattr(paddle, "client", fake)
        assert paddle.list_products("tok") == []

    def test_network_error_returns_empty(self, monkeypatch):
        monkeypatch.setattr(paddle, "client", FakeClient([httpx.ConnectError("boom")]))
        assert paddle.list_products("tok") == []

    def test_bad_shape_returns_empty(self, monkeypatch):
        monkeypatch.setattr(paddle, "client", FakeClient([_resp([1, 2, 3])]))
        assert paddle.list_products("tok") == []


class TestFetchLive:
    def _wire(self, monkeypatch, txn_pages, product_pages=None):
        if product_pages is None:
            product_pages = [_products_page([("pro_1", "PixelPeek"), ("pro_2", "FocusBar")])]
        fake = FakeClient(product_pages + txn_pages)
        monkeypatch.setattr(paddle, "client", fake)
        return fake

    def test_revenue_today_month_prev_and_counts(self, monkeypatch, frozen_now):
        # grand_total is minor units (cents). 5000 -> $50 whole.
        txns = [
            # July (current month) — today (2026-07-12)
            _txn("2026-07-12T09:00:00Z", 5000, "cus_A", [("pro_1", None)]),
            # July — earlier this month, different customer
            _txn("2026-07-03T09:00:00Z", 2500, "cus_B", [("pro_1", None)]),
            # July — same customer A again (distinct-customer must stay 2)
            _txn("2026-07-05T09:00:00Z", 1000, "cus_A", [("pro_1", None)]),
            # June (prior calendar month) — counts only toward revenue_month_prev
            _txn("2026-06-20T09:00:00Z", 9000, "cus_C", [("pro_1", None)]),
        ]
        self._wire(monkeypatch, [_txns_page(txns)])
        rows = paddle.fetch_all("tok", ["PixelPeek", "FocusBar"])
        by_name = {r.name: r for r in rows}
        px = by_name["PixelPeek"]
        assert px.state == AccountState.OK
        assert px.purchases == 3                      # 3 July transactions
        assert px.customers == 2                      # cus_A (twice) + cus_B, distinct
        assert px.revenue_today == 50                 # 5000 cents -> $50
        assert px.revenue_month == 50 + 25 + 10       # $85 month-to-date
        assert px.revenue_month_prev == 90            # June's 9000 cents -> $90
        # FocusBar had no transactions -> zeros, still OK.
        fb = by_name["FocusBar"]
        assert fb.state == AccountState.OK
        assert fb.purchases == 0
        assert fb.revenue_month == 0

    def test_minor_unit_conversion_rounds(self, monkeypatch, frozen_now):
        # 1999 cents -> $20 (round-half-to-even of 19.99).
        txns = [_txn("2026-07-10T09:00:00Z", 1999, "cus_A", [("pro_1", None)])]
        self._wire(monkeypatch, [_txns_page(txns)])
        px = {r.name: r for r in paddle.fetch_all("tok", ["PixelPeek"])}["PixelPeek"]
        assert px.revenue_month == 20

    def test_multi_product_transaction_splits_by_line(self, monkeypatch, frozen_now):
        # One transaction spanning two products, each with its own line total.
        txns = [
            _txn("2026-07-08T09:00:00Z", 7000, "cus_A",
                 [("pro_1", 5000), ("pro_2", 2000)]),
        ]
        self._wire(monkeypatch, [_txns_page(txns)])
        by_name = {r.name: r for r in paddle.fetch_all("tok", ["PixelPeek", "FocusBar"])}
        assert by_name["PixelPeek"].revenue_month == 50   # its line only
        assert by_name["FocusBar"].revenue_month == 20
        # Purchase + customer attributed to BOTH products it touched.
        assert by_name["PixelPeek"].purchases == 1
        assert by_name["FocusBar"].purchases == 1
        assert by_name["PixelPeek"].customers == 1
        assert by_name["FocusBar"].customers == 1

    def test_untracked_product_ignored(self, monkeypatch, frozen_now):
        # A transaction for pro_2 (FocusBar) when only PixelPeek is requested.
        txns = [_txn("2026-07-08T09:00:00Z", 5000, "cus_A", [("pro_2", None)])]
        self._wire(monkeypatch, [_txns_page(txns)])
        px = {r.name: r for r in paddle.fetch_all("tok", ["PixelPeek"])}["PixelPeek"]
        assert px.revenue_month == 0
        assert px.purchases == 0

    def test_transactions_paginate_via_cursor(self, monkeypatch, frozen_now):
        next_url = f"{paddle.TRANSACTIONS_URL}?after=txn_1"
        page1 = _txns_page(
            [_txn("2026-07-02T09:00:00Z", 1000, "cus_A", [("pro_1", None)])],
            has_more=True, next_url=next_url,
        )
        page2 = _txns_page(
            [_txn("2026-07-09T09:00:00Z", 2000, "cus_B", [("pro_1", None)])],
        )
        fake = self._wire(monkeypatch, [page1, page2])
        px = {r.name: r for r in paddle.fetch_all("tok", ["PixelPeek"])}["PixelPeek"]
        assert px.revenue_month == 30            # $10 + $20 across both pages
        assert px.purchases == 2
        # 1 products page + 2 transaction pages = 3 GETs.
        assert len(fake.calls) == 3

    def test_created_at_filter_uses_prior_month_start(self, monkeypatch, frozen_now):
        fake = self._wire(monkeypatch, [_txns_page([])])
        paddle.fetch_all("tok", ["PixelPeek"])
        # Transactions request is the 2nd call (after the products page).
        txn_params = fake.calls[1]["params"]
        assert txn_params["status"] == "completed"
        assert txn_params["created_at[GTE]"] == "2026-06-01T00:00:00Z"

    def test_revenue_series_has_one_point_per_day_month_to_date(self, monkeypatch, frozen_now):
        txns = [_txn("2026-07-10T09:00:00Z", 3000, "cus_A", [("pro_1", None)])]
        self._wire(monkeypatch, [_txns_page(txns)])
        px = {r.name: r for r in paddle.fetch_all("tok", ["PixelPeek"])}["PixelPeek"]
        # July 1..12 inclusive = 12 points; the 10th (index 9) carries $30.
        assert len(px.revenue_series) == 12
        assert px.revenue_series[9] == 30
        assert sum(px.revenue_series) == 30

    def test_auth_failure_marks_rows_auth(self, monkeypatch, frozen_now):
        # Products page 403 -> every requested row AUTH, never raises.
        monkeypatch.setattr(paddle, "client", FakeClient([_resp({}, status=403)]))
        rows = paddle.fetch_all("tok", ["PixelPeek", "FocusBar"])
        assert all(r.state == AccountState.AUTH for r in rows)
        assert all(r.purchases is None for r in rows)

    def test_transient_failure_marks_rows_error(self, monkeypatch, frozen_now):
        # Products OK, transactions network error -> ERROR rows.
        products = _products_page([("pro_1", "PixelPeek")])
        monkeypatch.setattr(
            paddle, "client",
            FakeClient([products, httpx.ConnectError("boom")]),
        )
        rows = paddle.fetch_all("tok", ["PixelPeek"])
        assert rows[0].state == AccountState.ERROR

