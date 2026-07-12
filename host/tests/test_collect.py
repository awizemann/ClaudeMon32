"""Tests for the shared DashboardCollector: the collection refactor both the CLI
and the daemon lean on, and its time-based discovery cache (hit/miss/expiry).

No live tokens or devices — `keychain`/`sources`/`config` and the discovery
fetchers are monkeypatched so we exercise the orchestration and cache logic in
isolation."""

from __future__ import annotations

import pytest

from claudemon import collect, config as configmod, sources


@pytest.fixture(autouse=True)
def _no_accounts(monkeypatch):
    """Anthropic collection isn't under test here; stub it to nothing so we can
    focus on discovery + fetch orchestration for the token-driven sources."""
    monkeypatch.setattr(collect, "_collect_snapshots", lambda: [])


@pytest.fixture
def stub_stores(monkeypatch):
    """Empty sources + default config; no manual zones/repos so the token-driven
    discovery path is the one that runs."""
    monkeypatch.setattr(sources, "load", lambda: sources.Sources())
    monkeypatch.setattr(configmod, "load", lambda: configmod.Config())


class Clock:
    """Manually advanced monotonic stand-in for cache-expiry tests."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, secs: float) -> None:
        self.t += secs


# --------------------------------------------------------------- discovery cache


class TestDiscoveryCache:
    def _wire_tokens(self, monkeypatch, cf=None, gh=None):
        """load_secret returns the given token per service (None otherwise)."""
        def load_secret(service):
            return {"cloudflare": cf, "github": gh}.get(service)
        monkeypatch.setattr(collect.keychain, "load_secret", load_secret)

    def test_zone_list_cached_between_collects(self, monkeypatch, stub_stores):
        self._wire_tokens(monkeypatch, cf="cf-tok")
        calls = {"zones": 0}

        def list_zones(token):
            calls["zones"] += 1
            return [{"id": "z1", "name": "a.com"}]

        monkeypatch.setattr(collect.cloudflare, "list_zones", list_zones)
        monkeypatch.setattr(collect.cloudflare, "fetch_all", lambda tok, zones: [])

        clock = Clock()
        c = collect.DashboardCollector(clock=clock, ttl=600.0)
        c.collect()
        c.collect()
        c.collect()
        assert calls["zones"] == 1  # enumerated once, reused twice

    def test_repo_list_cached_between_collects(self, monkeypatch, stub_stores):
        self._wire_tokens(monkeypatch, gh="gh-tok")
        calls = {"repos": 0}

        def list_repos(token):
            calls["repos"] += 1
            return ["o/r1"]

        monkeypatch.setattr(collect.github, "list_repos", list_repos)
        monkeypatch.setattr(collect.github, "fetch_all", lambda tok, repos: [])

        clock = Clock()
        c = collect.DashboardCollector(clock=clock, ttl=600.0)
        c.collect()
        c.collect()
        assert calls["repos"] == 1

    def test_cache_expires_after_ttl(self, monkeypatch, stub_stores):
        self._wire_tokens(monkeypatch, cf="cf-tok")
        calls = {"zones": 0}

        def list_zones(token):
            calls["zones"] += 1
            return [{"id": "z1", "name": "a.com"}]

        monkeypatch.setattr(collect.cloudflare, "list_zones", list_zones)
        monkeypatch.setattr(collect.cloudflare, "fetch_all", lambda tok, zones: [])

        clock = Clock()
        c = collect.DashboardCollector(clock=clock, ttl=600.0)
        c.collect()                 # miss -> 1
        clock.advance(300)
        c.collect()                 # within TTL -> still 1
        assert calls["zones"] == 1
        clock.advance(301)          # now > 600s since first fetch
        c.collect()                 # expired -> re-list
        assert calls["zones"] == 2

    def test_rotated_token_busts_cache(self, monkeypatch, stub_stores):
        token = {"v": "cf-tok-1"}

        def load_secret(service):
            return token["v"] if service == "cloudflare" else None
        monkeypatch.setattr(collect.keychain, "load_secret", load_secret)

        calls = {"zones": 0}

        def list_zones(t):
            calls["zones"] += 1
            return [{"id": "z1", "name": "a.com"}]

        monkeypatch.setattr(collect.cloudflare, "list_zones", list_zones)
        monkeypatch.setattr(collect.cloudflare, "fetch_all", lambda tok, zones: [])

        clock = Clock()
        c = collect.DashboardCollector(clock=clock, ttl=600.0)
        c.collect()
        token["v"] = "cf-tok-2"     # rotated within TTL
        c.collect()
        assert calls["zones"] == 2  # different token -> re-discover

    def test_no_token_skips_discovery(self, monkeypatch, stub_stores):
        self._wire_tokens(monkeypatch)  # both None
        called = {"zones": False, "repos": False}
        monkeypatch.setattr(
            collect.cloudflare, "list_zones",
            lambda t: called.__setitem__("zones", True) or [],
        )
        monkeypatch.setattr(
            collect.github, "list_repos",
            lambda t: called.__setitem__("repos", True) or [],
        )
        c = collect.DashboardCollector()
        claude, cf, pd, gh = c.collect()
        assert not called["zones"] and not called["repos"]
        assert cf == [] and gh == []


# ------------------------------------------------------------ collect orchestration


class TestUsageThrottle:
    """Anthropic usage is polled at most every usage_ttl, independent of the
    (faster) discovery/stats cadence — the endpoint 429s if hammered."""

    def _count_snapshots(self, monkeypatch):
        calls = {"n": 0}
        monkeypatch.setattr(collect, "_collect_snapshots",
                            lambda: calls.__setitem__("n", calls["n"] + 1) or [])
        monkeypatch.setattr(collect.keychain, "list_accounts", lambda: ["work"])
        return calls

    def test_usage_throttled_within_ttl(self, monkeypatch, stub_stores):
        monkeypatch.setattr(collect.keychain, "load_secret", lambda s: None)
        calls = self._count_snapshots(monkeypatch)
        clock = Clock()
        c = collect.DashboardCollector(clock=clock, usage_ttl=180.0)
        c.collect()
        clock.advance(120)
        c.collect()                 # within 180s -> reuse
        assert calls["n"] == 1
        clock.advance(61)           # now > 180s
        c.collect()                 # expired -> re-poll
        assert calls["n"] == 2

    def test_account_change_busts_usage_cache(self, monkeypatch, stub_stores):
        monkeypatch.setattr(collect.keychain, "load_secret", lambda s: None)
        calls = {"n": 0}
        monkeypatch.setattr(collect, "_collect_snapshots",
                            lambda: calls.__setitem__("n", calls["n"] + 1) or [])
        roster = {"v": ["work"]}
        monkeypatch.setattr(collect.keychain, "list_accounts", lambda: roster["v"])
        clock = Clock()
        c = collect.DashboardCollector(clock=clock, usage_ttl=180.0)
        c.collect()
        roster["v"] = ["work", "personal"]  # login within TTL
        c.collect()
        assert calls["n"] == 2      # roster changed -> re-poll despite TTL


class TestCollectOrchestration:
    def test_fetches_all_shown_zones_live_each_cycle(self, monkeypatch, stub_stores):
        """Discovery is cached but per-zone stats still fetch live every cycle."""
        monkeypatch.setattr(
            collect.keychain, "load_secret",
            lambda s: "cf-tok" if s == "cloudflare" else None,
        )
        monkeypatch.setattr(
            collect.cloudflare, "list_zones",
            lambda t: [{"id": "z1", "name": "a.com"}],
        )
        fetch_calls = {"n": 0}

        def fetch_all(tok, zones):
            fetch_calls["n"] += 1
            assert [z.name for z in zones] == ["a.com"]
            return []

        monkeypatch.setattr(collect.cloudflare, "fetch_all", fetch_all)
        c = collect.DashboardCollector()
        c.collect()
        c.collect()
        assert fetch_calls["n"] == 2  # stats fetched every cycle even though list cached

    def test_manual_sources_used_without_token(self, monkeypatch):
        monkeypatch.setattr(
            sources, "load",
            lambda: sources.Sources(github_repos=["manual/repo"]),
        )
        monkeypatch.setattr(configmod, "load", lambda: configmod.Config())
        monkeypatch.setattr(collect.keychain, "load_secret", lambda s: None)
        seen = {}
        monkeypatch.setattr(
            collect.github, "fetch_all",
            lambda tok, repos: seen.setdefault("repos", repos) or [],
        )
        c = collect.DashboardCollector()
        c.collect()
        assert seen["repos"] == ["manual/repo"]
