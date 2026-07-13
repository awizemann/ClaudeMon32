"""Tests for the new cockpit formatters (money, signed pct, seconds-remaining).
The existing fmt_count/fmt_bytes/fmt_relative are reused unchanged and covered
indirectly by the payload tests."""

from __future__ import annotations

from datetime import timedelta

import pytest

from claudemon.render import (
    fmt_money,
    fmt_signed_pct,
    secs_remaining,
)
from tests.conftest import NOW


class TestFmtMoney:
    def test_none_is_empty(self):
        assert fmt_money(None) == ""

    def test_thousands_get_commas(self):
        assert fmt_money(1248) == "$1,248"
        assert fmt_money(98720) == "$98,720"

    def test_small_values(self):
        assert fmt_money(0) == "$0"
        assert fmt_money(42) == "$42"

    def test_millions_compact(self):
        assert fmt_money(1_200_000) == "$1.2M"
        assert fmt_money(2_000_000) == "$2M"  # trailing .0 stripped

    def test_custom_symbol(self):
        assert fmt_money(500, symbol="€") == "€500"


class TestFmtSignedPct:
    def test_none_is_empty(self):
        assert fmt_signed_pct(None) == ""

    def test_positive_has_plus(self):
        assert fmt_signed_pct(12) == "+12%"

    def test_negative(self):
        assert fmt_signed_pct(-4) == "-4%"

    def test_zero_is_signed(self):
        assert fmt_signed_pct(0) == "+0%"


class TestSecsRemaining:
    def test_unknown_is_minus_one(self):
        assert secs_remaining(None, NOW) == -1

    def test_future(self):
        assert secs_remaining(NOW + timedelta(hours=2, minutes=13), NOW) == 2 * 3600 + 13 * 60

    def test_elapsed_clamps_to_zero(self):
        assert secs_remaining(NOW - timedelta(minutes=5), NOW) == 0

    def test_exact_now(self):
        assert secs_remaining(NOW, NOW) == 0
