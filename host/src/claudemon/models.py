"""Data models shared across ClaudeMon modules."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class AccountState(str, Enum):
    OK = "ok"
    AUTH = "auth"    # refresh/auth failure — needs re-login
    ERROR = "err"    # repeated fetch failures (network/5xx)
    DRIFT = "drift"  # endpoint responded but schema didn't parse cleanly


@dataclass
class AccountCredentials:
    access_token: str
    refresh_token: str
    expires_at: int  # epoch milliseconds
    scopes: list[str] = field(default_factory=list)
    subscription_type: str | None = None
    organization_id: str | None = None  # used to detect duplicate logins

    def expires_within(self, margin_seconds: int = 120) -> bool:
        return (self.expires_at / 1000) - time.time() < margin_seconds

    def to_json(self) -> str:
        return json.dumps(
            {
                "accessToken": self.access_token,
                "refreshToken": self.refresh_token,
                "expiresAt": self.expires_at,
                "scopes": self.scopes,
                "subscriptionType": self.subscription_type,
                "organizationId": self.organization_id,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> "AccountCredentials":
        d = json.loads(raw)
        return cls(
            access_token=d["accessToken"],
            refresh_token=d["refreshToken"],
            expires_at=int(d["expiresAt"]),
            scopes=list(d.get("scopes") or []),
            subscription_type=d.get("subscriptionType"),
            organization_id=d.get("organizationId"),
        )


@dataclass
class WindowUsage:
    pct: int | None = None            # 0-100, None = unknown
    resets_at: datetime | None = None
    # Server-reported severity for this window, from the usage endpoint's
    # limits[] ("normal" / "warning" / ...). None = unknown/absent. This is
    # authoritative — preferred over the client's own pct threshold.
    severity: str | None = None

    @property
    def known(self) -> bool:
        return self.pct is not None


@dataclass
class AccountUsage:
    label: str
    five_hour: WindowUsage = field(default_factory=WindowUsage)   # "session" limit
    week: WindowUsage = field(default_factory=WindowUsage)        # "weekly_all" limit
    # The scoped weekly limit ("weekly_scoped"), distinct from the overall
    # weekly window — the endpoint reports it separately in limits[]. Empty
    # WindowUsage when the account has no scoped cap.
    week_scoped: WindowUsage = field(default_factory=WindowUsage)
    state: AccountState = AccountState.OK
    fetched_at: datetime | None = None

    def to_state_dict(self) -> dict:
        def win(w: WindowUsage) -> dict:
            return {
                "pct": w.pct,
                "resets_at": w.resets_at.isoformat() if w.resets_at else None,
                "severity": w.severity,
            }

        return {
            "label": self.label,
            "five_hour": win(self.five_hour),
            "week": win(self.week),
            "week_scoped": win(self.week_scoped),
            "state": self.state.value,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


# ---------------------------------------------------------------- analytics
# Extra dashboard sources for the 5" CrowPanel target. These reuse AccountState
# (ok / auth / err; drift is Claude-usage-specific and unused here): `auth` means
# the API token is missing or rejected, `err` a transient fetch failure. Numeric
# fields are None when unknown so the device can render "--" rather than a zero.


@dataclass
class CloudflareZoneStats:
    name: str                          # zone display name, e.g. "example.com"
    requests: int | None = None        # total requests over the window (last 7d)
    bytes: int | None = None           # total bytes served
    cached_requests: int | None = None
    unique_visitors: int | None = None
    threats: int | None = None
    requests_series: list[int] = field(default_factory=list)  # per-day requests, oldest first
    status: dict[str, int] = field(default_factory=dict)      # "2xx".."5xx" -> request count
    state: AccountState = AccountState.OK
    fetched_at: datetime | None = None

    @property
    def cache_pct(self) -> int | None:
        if not self.requests or self.cached_requests is None:
            return None
        return max(0, min(100, round(100 * self.cached_requests / self.requests)))

    def to_state_dict(self) -> dict:
        return {
            "name": self.name,
            "requests": self.requests,
            "bytes": self.bytes,
            "cached_requests": self.cached_requests,
            "unique_visitors": self.unique_visitors,
            "threats": self.threats,
            "cache_pct": self.cache_pct,
            "requests_series": self.requests_series,
            "status": self.status,
            "state": self.state.value,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


@dataclass
class GitHubRepoStats:
    name: str                          # "owner/repo"
    stars: int | None = None
    forks: int | None = None
    watchers: int | None = None
    open_issues: int | None = None     # issues only — PRs excluded (see github.py)
    open_prs: int | None = None
    latest_release: str | None = None  # tag name, e.g. "v2.1.0"
    ci_status: str | None = None       # "pass" | "fail" | "run" (default-branch rollup)
    pushed_at: datetime | None = None  # last push to the default branch
    language: str | None = None        # primary language
    state: AccountState = AccountState.OK
    fetched_at: datetime | None = None

    def to_state_dict(self) -> dict:
        return {
            "name": self.name,
            "stars": self.stars,
            "forks": self.forks,
            "watchers": self.watchers,
            "open_issues": self.open_issues,
            "open_prs": self.open_prs,
            "latest_release": self.latest_release,
            "ci_status": self.ci_status,
            "pushed_at": self.pushed_at.isoformat() if self.pushed_at else None,
            "language": self.language,
            "state": self.state.value,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


@dataclass
class PaddleProductStats:
    """One macOS product sold through Paddle. Revenue is in whole currency units
    (dollars), not cents — the fetcher divides Paddle's minor units. Numeric
    fields are None when unknown so the device renders "--" rather than a zero."""

    name: str                          # product display name, e.g. "PixelPeek"
    category: str | None = None        # e.g. "Utilities", "Productivity"
    purchases: int | None = None       # transactions in the month-to-date window
    customers: int | None = None       # distinct paying customers, lifetime
    revenue_today: int | None = None   # revenue today (whole currency units)
    revenue_month: int | None = None   # revenue month-to-date
    revenue_month_prev: int | None = None  # prior calendar month, for MoM
    revenue_series: list[int] = field(default_factory=list)  # per-day revenue, oldest first
    state: AccountState = AccountState.OK
    fetched_at: datetime | None = None

    def to_state_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "purchases": self.purchases,
            "customers": self.customers,
            "revenue_today": self.revenue_today,
            "revenue_month": self.revenue_month,
            "revenue_month_prev": self.revenue_month_prev,
            "revenue_series": self.revenue_series,
            "state": self.state.value,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


@dataclass
class PaddleTotals:
    """Combined Paddle figures across every shown product. Derived host-side from
    the per-product rows (see paddle.combine_totals)."""

    revenue_today: int | None = None
    revenue_month: int | None = None
    revenue_month_prev: int | None = None  # prior month, for the MoM comparison
    sales: int | None = None               # total purchases across products
    customers: int | None = None           # total customers across products
    state: AccountState = AccountState.OK

    @property
    def mom_pct(self) -> int | None:
        """Month-over-month revenue change as a signed whole percent. None when
        the prior month is unknown or zero (no baseline to compare against)."""
        if self.revenue_month is None or not self.revenue_month_prev:
            return None
        delta = self.revenue_month - self.revenue_month_prev
        return round(100 * delta / self.revenue_month_prev)

    def to_state_dict(self) -> dict:
        return {
            "revenue_today": self.revenue_today,
            "revenue_month": self.revenue_month,
            "revenue_month_prev": self.revenue_month_prev,
            "sales": self.sales,
            "customers": self.customers,
            "mom_pct": self.mom_pct,
            "state": self.state.value,
        }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
