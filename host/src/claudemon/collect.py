"""Shared dashboard-collection orchestration.

`cli.cmd_dashboard` (one-shot) and `daemon.run_loop` (long-running poll) both
need the same "fetch all four cockpit sections" logic. Forking it invites the two
paths to drift, so it lives here once, behind `DashboardCollector`.

The one thing the daemon needs that a one-shot doesn't is a **discovery cache**:
`cloudflare.list_zones` / `github.list_repos` enumerate every zone/repo the token
can see on EVERY call, which for a 60s poll loop is constant enumeration traffic.
The collector caches those LIST results per token with a short TTL and reuses them
between polls; the per-item stats fetch stays live every cycle. A one-shot CLI run
just makes one collector, so its cache is effectively a no-op.

The clock is injectable (`monotonic`) so tests can drive cache hit/miss/expiry
without sleeping.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from . import cloudflare, config as configmod, github, keychain, oauth, paddle, render, sources, usage
from .models import (
    AccountState,
    AccountUsage,
    CloudflareZoneStats,
    GitHubRepoStats,
    PaddleProductStats,
)

log = logging.getLogger(__name__)

# Re-discover the zone/repo lists at most this often. Per-item stats still fetch
# live every cycle; only the enumeration is cached. Ten minutes keeps the poll
# loop from re-listing on every tick while still picking up newly added
# zones/repos within a few minutes.
DISCOVERY_TTL_S = 600.0

# The Anthropic usage endpoint is undocumented and rate-limited — polling it on
# every dashboard tick (the refresh slider goes as low as 15s) draws HTTP 429s
# with multiple accounts. So usage snapshots are throttled INDEPENDENTLY of the
# faster CF/GitHub/Paddle stats: fetched at most this often (matches the endpoint's
# documented ~3-min poll cadence), reused between. See project-status memory note.
USAGE_TTL_S = 180.0


def _collect_snapshots() -> list[AccountUsage]:
    """Fetch a live usage snapshot for each configured Anthropic account.

    Each account is independently resilient: an auth or fetch failure degrades
    only that row's state, never the whole collection."""
    snapshots: list[AccountUsage] = []
    for label in keychain.list_accounts():
        snap = AccountUsage(label=label)
        try:
            creds = oauth.load_fresh(label)
            snap = usage.fetch_usage(label, creds)
        except (keychain.KeychainError, oauth.OAuthError) as e:
            log.warning("%s: %s", label, e)
            snap.state = AccountState.AUTH
        except (oauth.OAuthTransientError, usage.UsageFetchError) as e:
            log.warning("%s: %s", label, e)
            snap.state = AccountState.ERROR
        snapshots.append(snap)
    return snapshots


class DashboardCollector:
    """Fetches all four dashboard sections, caching token-driven discovery.

    Stateless per-fetch except for the discovery cache, so a single instance can
    be reused across an entire poll loop. `clock` defaults to `time.monotonic`
    and is injectable for tests; `ttl` overrides the discovery TTL."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        ttl: float = DISCOVERY_TTL_S,
        usage_ttl: float = USAGE_TTL_S,
    ) -> None:
        self._clock = clock
        self._ttl = ttl
        self._usage_ttl = usage_ttl
        # token -> (fetched_at, discovered). Keyed by token so a rotated token
        # re-discovers instead of serving a stale enumeration.
        self._zone_cache: tuple[str, float, list[dict[str, str]]] | None = None
        self._repo_cache: tuple[str, float, list[str]] | None = None
        self._product_cache: tuple[str, float, list[str]] | None = None
        # (account-set signature, fetched_at, snapshots) — the Anthropic throttle.
        self._snapshot_cache: tuple[str, float, list[AccountUsage]] | None = None

    # -- anthropic usage (throttled independently of the other sources) ----

    def _snapshots(self) -> list[AccountUsage]:
        """Anthropic usage snapshots, polled at most every `usage_ttl` (the
        endpoint is rate-limited — see USAGE_TTL_S). Keyed on the account set so a
        login/logout busts the throttle rather than serving a stale roster."""
        key = "\n".join(keychain.list_accounts())
        cached = self._snapshot_cache
        now = self._clock()
        if cached is not None and cached[0] == key and (now - cached[1]) < self._usage_ttl:
            return cached[2]
        snaps = _collect_snapshots()
        self._snapshot_cache = (key, now, snaps)
        return snaps

    # -- discovery (cached) ------------------------------------------------

    def _list_zones(self, token: str) -> list[dict[str, str]]:
        cached = self._zone_cache
        now = self._clock()
        if cached is not None and cached[0] == token and (now - cached[1]) < self._ttl:
            return cached[2]
        discovered = cloudflare.list_zones(token)
        self._zone_cache = (token, now, discovered)
        return discovered

    def _list_repos(self, token: str) -> list[str]:
        cached = self._repo_cache
        now = self._clock()
        if cached is not None and cached[0] == token and (now - cached[1]) < self._ttl:
            return cached[2]
        discovered = github.list_repos(token)
        self._repo_cache = (token, now, discovered)
        return discovered

    def _list_products(self, token: str) -> list[str]:
        cached = self._product_cache
        now = self._clock()
        if cached is not None and cached[0] == token and (now - cached[1]) < self._ttl:
            return cached[2]
        discovered = paddle.list_products(token)
        self._product_cache = (token, now, discovered)
        return discovered

    # -- source resolution -------------------------------------------------

    def _resolve_zones(
        self, token: str | None, srcs: sources.Sources, cfg: configmod.Config
    ) -> list[sources.CloudflareZone]:
        """Which Cloudflare zones to fetch this cycle. With a token: discover
        (cached) every zone, apply the config `shown` selection, cap to the
        cockpit limit. Without a token: the manual `add-zone` list."""
        if not token:
            return srcs.cloudflare_zones
        discovered = self._list_zones(token)
        names = {z["id"]: z["name"] for z in discovered}
        ids = [z["id"] for z in discovered]
        chosen = configmod.resolve_shown(ids, cfg.cloudflare_shown, render.MAX_COCKPIT_ZONES)
        return [sources.CloudflareZone(id=zid, name=names.get(zid, zid)) for zid in chosen]

    def _resolve_repos(
        self, token: str | None, srcs: sources.Sources, cfg: configmod.Config
    ) -> list[str]:
        """Which GitHub repos to fetch this cycle. With a token: discover
        (cached) + apply the `shown` selection + cap. Without: the manual list."""
        if not token:
            return srcs.github_repos
        discovered = self._list_repos(token)
        return configmod.resolve_shown(discovered, cfg.github_shown, render.MAX_COCKPIT_REPOS)

    def _resolve_products(
        self, token: str | None, srcs: sources.Sources, cfg: configmod.Config
    ) -> list[str]:
        """Which Paddle products to fetch this cycle. With a token: discover
        (cached) every product + apply the `shown` selection + cap. Without a
        token: the manual `add-product` list."""
        if not token:
            return srcs.paddle_products
        discovered = self._list_products(token)
        return configmod.resolve_shown(
            discovered, cfg.paddle_shown, render.MAX_COCKPIT_PRODUCTS
        )

    # -- the collection ----------------------------------------------------

    def collect(
        self,
    ) -> tuple[
        list[AccountUsage],
        list[CloudflareZoneStats],
        list[PaddleProductStats],
        list[GitHubRepoStats],
    ]:
        """Fetch all four dashboard sections (Claude, Cloudflare, Paddle,
        GitHub). Each source is independently resilient — a missing token or
        failed fetch degrades only its own rows.

        When a service token is present the item list is DISCOVERED from the
        token (cached between calls) and narrowed by the config `shown`
        selection; the manual add-zone/add-repo lists remain the fallback when
        no token is set."""
        claude = self._snapshots()
        srcs = sources.load()
        cfg = configmod.load()

        cf: list[CloudflareZoneStats] = []
        cf_token = keychain.load_secret("cloudflare")
        zones = self._resolve_zones(cf_token, srcs, cfg)
        if zones:
            if cf_token:
                cf = cloudflare.fetch_all(cf_token, zones)
            else:
                log.warning(
                    "cloudflare zones configured but no token — run `claudemon set-token cloudflare`"
                )
                cf = [
                    CloudflareZoneStats(name=z.name, state=AccountState.AUTH)
                    for z in zones
                ]

        pd: list[PaddleProductStats] = []
        pd_token = keychain.load_secret("paddle")
        products = self._resolve_products(pd_token, srcs, cfg)
        if products:
            pd = paddle.fetch_all(pd_token, products)

        gh: list[GitHubRepoStats] = []
        gh_token = keychain.load_secret("github")
        repos = self._resolve_repos(gh_token, srcs, cfg)
        if repos:
            gh = github.fetch_all(gh_token, repos)

        return claude, cf, pd, gh
