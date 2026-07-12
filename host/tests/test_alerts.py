"""Tests for host-side alert derivation: each rule, the toggle gates, the
severity sort ordering + stability, and the threshold boundary."""

from __future__ import annotations

from claudemon.models import AccountState, GitHubRepoStats
from claudemon.render import AlertLevel, derive_alerts
from tests.conftest import _account, _zone


class TestAlertRules:
    def test_down_site_is_critical(self, now):
        z = _zone("legacy.example.com", 0, {}, state=AccountState.ERROR)
        alerts = derive_alerts([z], [], [], now)
        assert len(alerts) == 1
        assert alerts[0]["lvl"] == AlertLevel.CRITICAL
        assert alerts[0]["tag"] == "CRITICAL"
        assert alerts[0]["src"] == "Cloudflare"
        assert "offline" in alerts[0]["msg"]

    def test_degraded_site_is_warning(self, now):
        bad = {"2xx": 60, "3xx": 5, "4xx": 25, "5xx": 10}
        z = _zone("blog.example.com", 300_000, bad)
        alerts = derive_alerts([z], [], [], now)
        assert [a["lvl"] for a in alerts] == [AlertLevel.WARNING]
        assert alerts[0]["src"] == "Cloudflare"

    def test_account_over_threshold_is_warning(self, now):
        acct = _account("Work", 88, 60, 74)
        alerts = derive_alerts([], [acct], [], now, usage_threshold=80)
        assert [a["lvl"] for a in alerts] == [AlertLevel.WARNING]
        assert alerts[0]["src"] == "Anthropic"
        assert "88%" in alerts[0]["msg"]

    def test_watched_repo_issues_is_info(self, now):
        repo = GitHubRepoStats(name="awizemann/cf-worker-kit", open_issues=41)
        alerts = derive_alerts([], [], [repo], now, watched_repos={"awizemann/cf-worker-kit"})
        assert [a["lvl"] for a in alerts] == [AlertLevel.INFO]
        assert alerts[0]["src"] == "GitHub"

    def test_repo_with_zero_issues_no_alert(self, now):
        repo = GitHubRepoStats(name="awizemann/quiet", open_issues=0)
        assert derive_alerts([], [], [repo], now) == []


class TestToggles:
    def test_alert_on_down_off_suppresses_critical(self, now):
        z = _zone("legacy.example.com", 0, {}, state=AccountState.ERROR)
        assert derive_alerts([z], [], [], now, alert_on_down=False) == []

    def test_alert_on_4xx_off_suppresses_degraded(self, now):
        bad = {"2xx": 60, "3xx": 5, "4xx": 25, "5xx": 10}
        z = _zone("blog.example.com", 300_000, bad)
        assert derive_alerts([z], [], [], now, alert_on_4xx=False) == []

    def test_down_still_fires_when_4xx_off(self, now):
        # A down site is CRITICAL via alert_on_down, independent of the 4xx toggle.
        z = _zone("legacy.example.com", 0, {}, state=AccountState.ERROR)
        alerts = derive_alerts([z], [], [], now, alert_on_4xx=False)
        assert [a["lvl"] for a in alerts] == [AlertLevel.CRITICAL]


class TestThresholdBoundary:
    def test_exactly_at_threshold_fires(self, now):
        acct = _account("Edge", 80, 60, 40)
        alerts = derive_alerts([], [acct], [], now, usage_threshold=80)
        assert len(alerts) == 1

    def test_one_below_threshold_silent(self, now):
        acct = _account("Edge", 79, 60, 40)
        assert derive_alerts([], [acct], [], now, usage_threshold=80) == []

    def test_unknown_usage_never_fires(self, now):
        acct = _account("Blank", None, None, None)
        assert derive_alerts([], [acct], [], now, usage_threshold=80) == []


class TestSortAndCap:
    def test_sorted_critical_warning_info(self, now, zones, accounts, repos):
        alerts = derive_alerts(zones, accounts, repos, now, usage_threshold=80)
        levels = [a["lvl"] for a in alerts]
        assert levels == sorted(levels)  # non-decreasing severity
        assert levels[0] == AlertLevel.CRITICAL  # legacy site down

    def test_within_level_keeps_source_order(self, now):
        # Two degraded sites in config order -> WARNING alerts preserve that order.
        bad = {"2xx": 50, "3xx": 5, "4xx": 30, "5xx": 15}
        z1 = _zone("aaa.example.com", 100_000, bad)
        z2 = _zone("bbb.example.com", 100_000, bad)
        alerts = derive_alerts([z1, z2], [], [], now)
        assert [a["msg"].split()[0] for a in alerts] == ["aaa.example.com", "bbb.example.com"]

    def test_capped_at_max(self, now):
        # Exceed the alert cap with a mix that clears the per-source row caps:
        # 12 down sites (CRITICAL) alone is >8, so the payload is capped to 8
        # and keeps the most severe.
        from claudemon.render import MAX_COCKPIT_ALERTS
        many_zones = [
            _zone(f"z{i}.example.com", 0, {}, state=AccountState.ERROR)
            for i in range(12)
        ]
        alerts = derive_alerts(many_zones, [], [], now)
        assert len(alerts) == MAX_COCKPIT_ALERTS
        assert all(a["lvl"] == AlertLevel.CRITICAL for a in alerts)
