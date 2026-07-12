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
    plan: str | None = None,
    messages: int | None = None,
    activity: list[int] | None = None,
    state: AccountState = AccountState.OK,
) -> AccountUsage:
    fh = WindowUsage(
        pct=fh_pct,
        resets_at=NOW + timedelta(minutes=fh_in_min) if fh_in_min is not None else None,
    )
    wk = WindowUsage(pct=wk_pct, resets_at=NOW + timedelta(days=3) if wk_pct is not None else None)
    return AccountUsage(
        label=label, five_hour=fh, week=wk, state=state,
        plan=plan, messages=messages, activity=activity or [],
    )


@pytest.fixture
def accounts() -> list[AccountUsage]:
    """3 Max accounts matching the handoff example figures."""
    hist = list(range(1, 25))  # ramping 1..24 messages/hour
    return [
        _account("Personal", 46, 133, 61, plan="Max 5×", messages=128, activity=hist),
        _account("Work", 88, 62, 74, plan="Max 20×", messages=412, activity=hist),
        _account("Studio", 22, 228, 39, plan="Max 20×", messages=95, activity=hist),
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
