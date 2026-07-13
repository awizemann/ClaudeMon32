"""Shared fixtures for the cockpit tests.

`NOW` is a fixed timezone-aware instant so countdown/relative strings and the
`base`/`fh_sec` numeric-time fields are deterministic across runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from claudemon.models import (
    AccountState,
    AccountUsage,
    CloudflareZoneStats,
    GitHubRepoStats,
    WindowUsage,
)

NOW = datetime(2026, 7, 12, 14, 32, 5, tzinfo=timezone.utc)


@pytest.fixture
def now() -> datetime:
    return NOW


def _account(
    label: str,
    fh_pct: int | None,
    fh_in_min: int | None,
    wk_pct: int | None,
    *,
    ws_pct: int | None = None,
    fh_sev: str | None = None,
    wk_sev: str | None = None,
    ws_sev: str | None = None,
    active: str | None = None,        # "5h" | "week" | "scoped" — the binding limit
    cred_used: float | None = None,   # dollars; presence enables credits
    cred_limit: float | None = None,
    state: AccountState = AccountState.OK,
) -> AccountUsage:
    fh = WindowUsage(
        pct=fh_pct,
        resets_at=NOW + timedelta(minutes=fh_in_min) if fh_in_min is not None else None,
        severity=fh_sev,
        active=active == "5h",
    )
    wk = WindowUsage(
        pct=wk_pct,
        resets_at=NOW + timedelta(days=3) if wk_pct is not None else None,
        severity=wk_sev,
        active=active == "week",
    )
    ws = WindowUsage(
        pct=ws_pct,
        resets_at=NOW + timedelta(days=3) if ws_pct is not None else None,
        severity=ws_sev,
        active=active == "scoped",
    )
    return AccountUsage(
        label=label, five_hour=fh, week=wk, week_scoped=ws, state=state,
        credits_enabled=cred_used is not None, credits_used=cred_used, credits_limit=cred_limit,
    )


@pytest.fixture
def accounts() -> list[AccountUsage]:
    """3 accounts matching the handoff example figures: a scoped-weekly gauge, a
    server severity on the busiest one (Work at warning), an active-window flag,
    and extra-usage credits enabled on Personal."""
    return [
        _account("Personal", 46, 133, 61, ws_pct=40, active="5h", cred_used=0.03, cred_limit=250.0),
        _account("Work", 88, 62, 74, ws_pct=81, wk_sev="warning", ws_sev="warning", active="week"),
        _account("Studio", 22, 228, 39, ws_pct=15, active="5h"),
    ]


def _zone(name: str, requests: int, status: dict[str, int], state=AccountState.OK) -> CloudflareZoneStats:
    return CloudflareZoneStats(
        name=name,
        requests=requests,
        bytes=requests * 4000,
        cached_requests=int(requests * 0.94),
        unique_visitors=requests // 100,
        threats=requests // 1000,
        requests_series=[requests // 7] * 7,
        status=status,
        state=state,
    )


@pytest.fixture
def zones() -> list[CloudflareZoneStats]:
    """12 sites: one degraded (blog), one down (legacy), rest up."""
    ok = {"2xx": 95, "3xx": 2, "4xx": 2, "5xx": 1}
    bad = {"2xx": 60, "3xx": 5, "4xx": 25, "5xx": 10}  # >=20% non-2xx/3xx -> degraded
    out: list[CloudflareZoneStats] = []
    for i in range(10):
        out.append(_zone(f"site{i}.wizemann.com", 400_000, ok))
    out.append(_zone("blog.wizemann.com", 350_000, bad))                 # degraded
    out.append(_zone("legacy.wizemann.com", 0, {}, state=AccountState.ERROR))  # down
    return out


def _repo(name: str, stars: int, issues: int, prs: int, lang: str, push_h: int) -> GitHubRepoStats:
    return GitHubRepoStats(
        name=name, stars=stars, forks=stars // 10, watchers=stars // 20,
        open_issues=issues, open_prs=prs, language=lang,
        pushed_at=NOW - timedelta(hours=push_h),
    )


@pytest.fixture
def repos() -> list[GitHubRepoStats]:
    return [
        _repo("awizemann/claudemon", 342, 12, 3, "C++", 2),
        _repo("awizemann/pixelpeek", 1200, 28, 5, "Swift", 4),
        _repo("awizemann/focusbar", 864, 9, 1, "Swift", 24),
        _repo("awizemann/cf-worker-kit", 2400, 41, 8, "TypeScript", 6),
        _repo("awizemann/paddle-sync", 156, 4, 0, "Go", 72),
        _repo("awizemann/desk-dash", 78, 2, 1, "Rust", 5),
    ]
