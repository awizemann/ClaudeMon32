"""Tests for the Paddle fetcher: synthetic data, totals rollup, MoM, unknown
products, and the live-API stub gate."""

from __future__ import annotations

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

    def test_live_token_degrades_to_auth_when_unimplemented(self):
        # A real token routes to _fetch_live, which raises NotImplementedError;
        # fetch_all must degrade to AUTH rows rather than crash the dashboard.
        rows = paddle.fetch_all("live-real-token", ["PixelPeek"])
        assert rows[0].state == AccountState.AUTH
        assert rows[0].purchases is None


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
