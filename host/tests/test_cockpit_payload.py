"""Tests for the enriched set_cockpit payload: structure, host-rendered strings,
the sanctioned live-tick numeric fields, source caps, unknown-data handling, and
the 16384-byte line-cap under worst-case data."""

from __future__ import annotations

import json
from datetime import timedelta

from claudemon import paddle
from claudemon.models import (
    AccountState,
    AccountUsage,
    CloudflareZoneStats,
    GitHubRepoStats,
    PaddleTotals,
    WindowUsage,
)
from claudemon.render import (
    MAX_COCKPIT_ACCOUNTS,
    MAX_COCKPIT_PRODUCTS,
    MAX_COCKPIT_REPOS,
    MAX_COCKPIT_ZONES,
    to_cockpit_payload,
)
from tests.conftest import NOW

COCKPIT_LINE_CAP = 16384


def _build(accounts, zones, repos, **kw):
    products = paddle.fetch_all(None, ["PixelPeek", "CleanShot Pro", "FocusBar", "SnapVault"])
    totals = paddle.combine_totals(products)
    return to_cockpit_payload(accounts, zones, products, totals, repos, NOW, **kw)


class TestStructure:
    def test_command_name(self, accounts, zones, repos):
        assert _build(accounts, zones, repos)["cmd"] == "set_cockpit"

    def test_top_level_sections(self, accounts, zones, repos):
        p = _build(accounts, zones, repos)["params"]
        assert set(p) >= {
            "updated", "base", "date", "anthropic", "cloudflare",
            "paddle", "github", "alerts",
        }

    def test_account_card_fields(self, accounts, zones, repos):
        p = _build(accounts, zones, repos)["params"]
        card = p["anthropic"]["accounts"][0]
        assert set(card) == {
            "label", "fh_pct", "fh_rst", "fh_sec", "wk_pct", "wk_rnw",
            "plan", "msgs", "act", "st",
        }
        # accounts are sorted by label -> Personal, Studio, Work
        assert [c["label"] for c in p["anthropic"]["accounts"]] == ["PERSONAL", "STUDIO", "WORK"]

    def test_cloudflare_totals_and_down_count(self, accounts, zones, repos):
        cf = _build(accounts, zones, repos)["params"]["cloudflare"]
        assert cf["down"] == 1        # legacy site
        assert cf["degraded"] == 1    # blog site
        assert cf["totals"]["cache"] == 94
        assert cf["totals"]["req"]  # non-empty formatted string

    def test_paddle_totals(self, accounts, zones, repos):
        pd = _build(accounts, zones, repos)["params"]["paddle"]
        assert pd["totals"]["rev_today"] == "$1,248"
        assert pd["totals"]["mom"].startswith("+")
        assert len(pd["products"]) == 4

    def test_github_summary(self, accounts, zones, repos):
        gh = _build(accounts, zones, repos)["params"]["github"]
        assert gh["summary"]["repos"] == 6
        assert gh["summary"]["issues"] == "96"  # 12+28+9+41+4+2
        assert gh["summary"]["prs"] == "18"     # 3+5+1+8+0+1
        assert gh["repos"][0]["lcol"] == "#8FBF7F"  # C++ dot color


class TestHostRenderedContract:
    def test_counts_are_strings(self, accounts, zones, repos):
        p = _build(accounts, zones, repos)["params"]
        site = p["cloudflare"]["sites"][0]
        assert isinstance(site["req"], str)
        assert isinstance(site["bw"], str)
        assert isinstance(p["github"]["repos"][0]["stars"], str)

    def test_percents_and_series_stay_raw_ints(self, accounts, zones, repos):
        p = _build(accounts, zones, repos)["params"]
        card = p["anthropic"]["accounts"][0]
        assert isinstance(card["fh_pct"], int)
        assert all(isinstance(v, int) for v in card["act"])
        assert isinstance(p["cloudflare"]["totals"]["cache"], int)


class TestLiveTickFields:
    def test_base_is_seconds_since_local_midnight(self, accounts, zones, repos):
        p = _build(accounts, zones, repos)["params"]
        local = NOW.astimezone()
        assert p["base"] == local.hour * 3600 + local.minute * 60 + local.second
        assert isinstance(p["base"], int)

    def test_fh_sec_counts_down_to_reset(self, accounts, zones, repos):
        p = _build(accounts, zones, repos)["params"]
        work = next(c for c in p["anthropic"]["accounts"] if c["label"] == "WORK")
        # Work resets in 62 minutes (see conftest).
        assert work["fh_sec"] == 62 * 60

    def test_fh_sec_minus_one_when_unknown(self, zones, repos):
        acct = AccountUsage(label="blank", five_hour=WindowUsage(pct=None, resets_at=None))
        p = _build([acct], zones, repos)["params"]
        assert p["anthropic"]["accounts"][0]["fh_sec"] == -1

    def test_updated_string_still_present(self, accounts, zones, repos):
        # The host-rendered "HH:MM" stays — base is additive, not a replacement.
        p = _build(accounts, zones, repos)["params"]
        assert p["updated"] == NOW.astimezone().strftime("%H:%M")


class TestCaps:
    def test_accounts_capped_at_3(self, zones, repos):
        many = [
            AccountUsage(label=f"acct{i}", five_hour=WindowUsage(pct=10))
            for i in range(6)
        ]
        p = _build(many, zones, repos)["params"]
        assert len(p["anthropic"]["accounts"]) == MAX_COCKPIT_ACCOUNTS

    def test_zones_capped_at_12(self, accounts, repos):
        many = [
            CloudflareZoneStats(name=f"z{i}.com", requests=1000, status={"2xx": 100})
            for i in range(20)
        ]
        p = _build(accounts, many, repos)["params"]
        assert len(p["cloudflare"]["sites"]) == MAX_COCKPIT_ZONES

    def test_products_capped_at_4(self, accounts, zones, repos):
        products = paddle.fetch_all(None, ["PixelPeek"] * 8)
        totals = paddle.combine_totals(products)
        p = to_cockpit_payload(accounts, zones, products, totals, repos, NOW)["params"]
        assert len(p["paddle"]["products"]) == MAX_COCKPIT_PRODUCTS

    def test_repos_capped_at_6(self, accounts, zones):
        many = [GitHubRepoStats(name=f"o/r{i}", stars=1) for i in range(12)]
        p = _build(accounts, zones, many)["params"]
        assert len(p["github"]["repos"]) == MAX_COCKPIT_REPOS


class TestUnknownData:
    def test_empty_sources_produce_empty_sections(self, accounts):
        totals = PaddleTotals()
        # Threshold above every account's 5h usage so no account WARNING fires,
        # isolating the "no CF/Paddle/GitHub data -> empty sections" intent.
        p = to_cockpit_payload(
            accounts, [], [], totals, [], NOW, usage_threshold=101
        )["params"]
        assert p["cloudflare"]["sites"] == []
        assert p["cloudflare"]["totals"]["req"] == ""      # nothing known -> ""
        assert p["cloudflare"]["totals"]["cache"] == -1    # -1 sentinel for the bar
        assert p["paddle"]["products"] == []
        assert p["github"]["repos"] == []
        assert p["alerts"] == []

    def test_unknown_numbers_render_blank(self, zones, repos):
        acct = AccountUsage(
            label="blank",
            five_hour=WindowUsage(pct=None, resets_at=None),
            week=WindowUsage(pct=None, resets_at=None),
            state=AccountState.AUTH,
        )
        card = _build([acct], zones, repos)["params"]["anthropic"]["accounts"][0]
        assert card["fh_pct"] == -1
        assert card["fh_rst"] == ""
        assert card["msgs"] == ""
        assert card["act"] == []
        assert card["plan"] == ""


class TestPayloadSize:
    def test_worst_case_under_16384(self):
        """Realistic worst case: 3 accounts (full 24-bar histograms + long
        labels), 12 sites, 4 products, 6 repos, and a full alerts array.
        Serialized size must sit under the firmware's 16384-byte line cap."""
        hist = [99] * 24  # dense two-digit histogram (worst-case digits)
        accounts = [
            AccountUsage(
                label="LONGACCOUNTNAME",  # gets clipped to 10, but exercise it
                five_hour=WindowUsage(pct=88, resets_at=NOW + timedelta(hours=4)),
                week=WindowUsage(pct=99, resets_at=NOW + timedelta(days=3)),
                plan="Max 20×", messages=123456, activity=hist,
            )
            for _ in range(3)
        ]
        # 12 sites with degraded status so every one emits a WARNING alert, plus
        # long domains and full sparklines.
        bad = {"2xx": 50, "3xx": 5, "4xx": 30, "5xx": 15}
        zones = [
            CloudflareZoneStats(
                name=f"subdomain-{i}.long-domain-name.wizemann.com",
                requests=9_999_999, bytes=9 << 40,
                cached_requests=9_000_000, unique_visitors=999_999,
                threats=99_999, requests_series=[9_999_999] * 7, status=bad,
            )
            for i in range(12)
        ]
        products = paddle.fetch_all(None, ["PixelPeek", "CleanShot Pro", "FocusBar", "SnapVault"])
        totals = paddle.combine_totals(products)
        repos = [
            GitHubRepoStats(
                name=f"awizemann/long-repository-name-{i}",
                stars=999_999, open_issues=9999, open_prs=999,
                language="TypeScript", pushed_at=NOW - timedelta(days=99),
            )
            for i in range(6)
        ]
        payload = to_cockpit_payload(accounts, zones, products, totals, repos, NOW)
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        size = len(line.encode("utf-8"))
        assert size < COCKPIT_LINE_CAP, f"cockpit payload {size} >= cap {COCKPIT_LINE_CAP}"
        # Leave healthy headroom (report the number for the record).
        print(f"\nworst-case cockpit payload: {size} bytes (cap {COCKPIT_LINE_CAP})")
