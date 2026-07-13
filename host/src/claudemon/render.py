"""Rendering: terminal status table and the set_usage device payload.

The host renders ALL strings (countdowns, updated-at). The device does no
clock math — it only draws labels, bars from integer percents, and these
pre-formatted strings.
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum

from .models import (
    AccountState,
    AccountUsage,
    CloudflareZoneStats,
    GitHubRepoStats,
    PaddleProductStats,
    PaddleTotals,
    WindowUsage,
)

MAX_DEVICE_ACCOUNTS = 4
MAX_LABEL_LEN = 10

# The dense CrowPanel dashboard has room for more than the e-paper's 4 rows.
MAX_DASH_ZONES = 6
MAX_DASH_REPOS = 6

# Cockpit caps (the redesigned 800x480 UI — see docs/protocol.md set_cockpit).
MAX_COCKPIT_ACCOUNTS = 3   # 3 account cards on the Anthropic page
MAX_COCKPIT_ZONES = 12     # firmware paginates 6/page
MAX_COCKPIT_PRODUCTS = 4   # 2x2 product grid
MAX_COCKPIT_REPOS = 6      # repo list rows
MAX_COCKPIT_ALERTS = 8     # alerts panel is scrollable but we cap the payload



def fmt_countdown(resets_at: datetime | None, now: datetime) -> str:
    """"2H05M" under a day, "3D 4H" otherwise, "" when unknown/past."""
    if resets_at is None:
        return ""
    delta = (resets_at - now).total_seconds()
    if delta <= 0:
        return "NOW"
    minutes = int(delta // 60)
    days, rem = divmod(minutes, 24 * 60)
    hours, mins = divmod(rem, 60)
    if days > 0:
        return f"{days}D {hours}H"
    if hours > 0:
        return f"{hours}H{mins:02d}M"
    return f"{mins}M"


def fmt_renewal(resets_at: datetime | None, now: datetime) -> str:
    """Weekly renewal in local time plus time remaining, e.g. "WED 8PM (3D)".

    The suffix counts down to the renewal: hours when under a day away,
    days otherwise. Omitted when the renewal is unknown or already past.
    """
    if resets_at is None:
        return ""
    local = resets_at.astimezone()
    hour = local.strftime("%I").lstrip("0")
    ampm = "AM" if local.hour < 12 else "PM"
    base = f"{local.strftime('%a').upper()} {hour}{ampm}"
    delta = (resets_at - now).total_seconds()
    if delta <= 0:
        return base
    hours = int(delta // 3600)
    if hours < 24:
        return f"{base} ({hours}H)"
    return f"{base} ({hours // 24}D)"


def _pct_or_unknown(w: WindowUsage) -> int:
    return w.pct if w.pct is not None else -1


def fmt_count(n: int | None) -> str:
    """Compact count for a small screen: 942, 1.2K, 12K, 1.3M. "" when unknown."""
    if n is None:
        return ""
    if n < 1000:
        return str(n)
    if n < 10_000:
        return f"{n / 1000:.1f}K".replace(".0K", "K")
    if n < 1_000_000:
        return f"{n // 1000}K"
    if n < 10_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    return f"{n // 1_000_000}M"


def fmt_bytes(n: int | None) -> str:
    """Compact data volume: 4.2GB, 512MB, 88KB. "" when unknown."""
    if n is None:
        return ""
    for unit, size in (("TB", 1 << 40), ("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= size:
            return f"{n / size:.1f}{unit}".replace(".0", "")
    return f"{n}B"


def fmt_relative(when: datetime | None, now: datetime) -> str:
    """Short relative age of a past timestamp: 5m, 3h, 2d, 4w. "" when unknown."""
    if when is None:
        return ""
    secs = (now - when).total_seconds()
    if secs < 90:
        return "now"
    for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            return f"{int(secs // size)}{unit}"
    return "now"


def spark_norm(series: list[int], points: int = 7) -> list[int]:
    """Normalize a request series to 0-100 (share of its own peak) for the device
    sparkline. Returns [] when there's nothing meaningful to draw."""
    tail = series[-points:] if series else []
    if len(tail) < 2:
        return []
    peak = max(tail)
    if peak <= 0:
        return [0] * len(tail)
    return [round(100 * v / peak) for v in tail]


def status_pcts(status: dict[str, int]) -> list[int]:
    """Turn 2xx/3xx/4xx/5xx request counts into whole-percent shares [2xx,3xx,4xx,5xx].
    Returns [] when there's no status data."""
    order = ("2xx", "3xx", "4xx", "5xx")
    total = sum(status.get(k, 0) for k in order)
    if total <= 0:
        return []
    return [round(100 * status.get(k, 0) / total) for k in order]


def fmt_money(n: int | None, symbol: str = "$") -> str:
    """Currency for the sales tiles: $1,248, $98,720, $1.2M. "" when unknown.

    Whole units only (the fetcher already converted from Paddle minor units);
    thousands get commas, millions get a compact 1.2M so the tile never wraps."""
    if n is None:
        return ""
    if abs(n) >= 1_000_000:
        return f"{symbol}{n / 1_000_000:.1f}M".replace(".0M", "M")
    return f"{symbol}{n:,}"


def fmt_signed_pct(n: int | None) -> str:
    """Signed whole percent for the MoM chip: "+12%", "-4%", "0%". "" unknown."""
    if n is None:
        return ""
    return f"{n:+d}%"


def secs_remaining(resets_at: datetime | None, now: datetime) -> int:
    """Integer seconds until a reset, for the device to count down locally.
    -1 when unknown (no reset time); 0 when already elapsed. This is the ONE
    sanctioned numeric-time field — the device can't call the host between
    pushes, so it ticks this down itself (see docs/protocol.md)."""
    if resets_at is None:
        return -1
    delta = (resets_at - now).total_seconds()
    return max(0, int(delta))


def _claude_row(snap: AccountUsage, now: datetime) -> dict:
    return {
        "label": snap.label.upper()[:MAX_LABEL_LEN],
        "fh_pct": _pct_or_unknown(snap.five_hour),
        "fh_rst": fmt_countdown(snap.five_hour.resets_at, now),
        "wk_pct": _pct_or_unknown(snap.week),
        "wk_rnw": fmt_renewal(snap.week.resets_at, now),
        "st": snap.state.value,
    }


def to_device_payload(snapshots: list[AccountUsage], now: datetime) -> dict:
    accounts = [
        _claude_row(snap, now)
        for snap in sorted(snapshots, key=lambda s: s.label)[:MAX_DEVICE_ACCOUNTS]
    ]
    return {
        "cmd": "set_usage",
        "params": {
            "updated": now.astimezone().strftime("%H:%M"),
            "accounts": accounts,
        },
    }


def to_dashboard_payload(
    claude: list[AccountUsage],
    cloudflare: list[CloudflareZoneStats],
    github: list[GitHubRepoStats],
    now: datetime,
) -> dict:
    """The richer set_dashboard payload for the 5" CrowPanel. Every count is a
    pre-formatted short string; `cache` is an int 0-100 (-1 unknown) so the
    device can draw a bar. Numbers the host couldn't fetch are "" (or -1)."""
    cf = [
        {
            "zone": z.name.upper()[:MAX_LABEL_LEN],
            "req": fmt_count(z.requests),
            "bw": fmt_bytes(z.bytes),
            "cache": z.cache_pct if z.cache_pct is not None else -1,
            "vis": fmt_count(z.unique_visitors),
            "thr": fmt_count(z.threats),
            "spark": spark_norm(z.requests_series),
            "codes": status_pcts(z.status),
            "st": z.state.value,
        }
        for z in cloudflare[:MAX_DASH_ZONES]
    ]
    gh = [
        {
            "repo": r.name.upper()[:MAX_LABEL_LEN * 2],
            "stars": fmt_count(r.stars),
            "forks": fmt_count(r.forks),
            "watch": fmt_count(r.watchers),
            "issues": fmt_count(r.open_issues),
            "prs": fmt_count(r.open_prs),
            "rel": (r.latest_release or "")[:12],
            "ci": r.ci_status or "",
            "push": fmt_relative(r.pushed_at, now),
            "lang": (r.language or "")[:12],
            "st": r.state.value,
        }
        for r in github[:MAX_DASH_REPOS]
    ]
    return {
        "cmd": "set_dashboard",
        "params": {
            "updated": now.astimezone().strftime("%H:%M"),
            "claude": [_claude_row(s, now) for s in sorted(claude, key=lambda s: s.label)],
            "cloudflare": cf,
            "github": gh,
        },
    }


# ----------------------------------------------------------------- cockpit
# The redesigned 800x480 UI ("Cockpit"). One enriched payload carries the Home
# grid + all four source pages + the derived alerts panel. Keys are abbreviated
# to keep the line under the 16384-byte cap with worst-case data (see the
# payload-size test). Every string is host-rendered exactly as before; the only
# sanctioned numeric-time additions are `base` (header clock seed) and the
# per-account `fh_sec` (seconds to the 5h reset the device counts down).


class AlertLevel(IntEnum):
    """Alert severity. Lower value = more severe, so a plain sort puts
    CRITICAL first, then WARNING, then INFO (see derive_alerts)."""

    CRITICAL = 0
    WARNING = 1
    INFO = 2

    @property
    def tag(self) -> str:
        return self.name  # "CRITICAL" / "WARNING" / "INFO" — the device tag text


# Thresholds/toggles default to the handoff's shipping values. Phase 3 feeds
# these from admin config; for now callers may override.
DEFAULT_USAGE_THRESHOLD = 80


# Server severity ranking (from the usage endpoint's limits[]). Only warning
# and worse surface as a card badge; "normal"/unknown map to "" (no badge).
_SEVERITY_RANK = {"warning": 1, "critical": 2, "exceeded": 3}


def worst_severity(*windows) -> str:
    """The most severe server-reported severity across the given windows, or ""
    when they're all normal/unknown. Drives the card's alert badge."""
    worst, rank = "", 0
    for w in windows:
        r = _SEVERITY_RANK.get((w.severity or "").lower(), 0)
        if r > rank:
            worst, rank = w.severity.lower(), r
    return worst


def _cockpit_account(snap: AccountUsage, now: datetime) -> dict:
    """One Anthropic account card for the cockpit. Carries the 5h + weekly + the
    scoped-weekly gauges, the numeric seconds-to-5h-reset the device counts down
    locally, the weekly renewal string, and the server's worst-window severity
    (the alert badge). No plan/messages/activity — the usage endpoint has no
    source for those (verified across accounts)."""
    return {
        "label": snap.label.upper()[:MAX_LABEL_LEN],
        "fh_pct": _pct_or_unknown(snap.five_hour),
        "fh_rst": fmt_countdown(snap.five_hour.resets_at, now),
        "fh_sec": secs_remaining(snap.five_hour.resets_at, now),
        "wk_pct": _pct_or_unknown(snap.week),
        "wk_rnw": fmt_renewal(snap.week.resets_at, now),
        "ws_pct": _pct_or_unknown(snap.week_scoped),
        "sev": worst_severity(snap.five_hour, snap.week, snap.week_scoped),
        "st": snap.state.value,
    }


def _cockpit_site(z: CloudflareZoneStats, now: datetime) -> dict:
    """One Cloudflare site row. `site_status` maps zone state -> up/degraded/down
    for the status dot + text; a fetch/auth failure reads as `down`."""
    return {
        "dom": z.name[:24],
        "req": fmt_count(z.requests),
        "bw": fmt_bytes(z.bytes),
        "spark": spark_norm(z.requests_series),
        "st": site_status(z),
    }


def site_status(z: CloudflareZoneStats) -> str:
    """Origin health for a site row: `up` | `degraded` | `down`.

    A hard fetch/auth failure is `down` (we can't confirm it's serving). A zone
    that fetched OK but shows an elevated 4xx/5xx share is `degraded`. Everything
    else is `up`."""
    if z.state != AccountState.OK:
        return "down"
    codes = status_pcts(z.status)
    if codes and (codes[2] + codes[3]) >= 20:  # >=20% non-2xx/3xx
        return "degraded"
    return "up"


def _cockpit_product(p: PaddleProductStats) -> dict:
    return {
        "name": p.name[:20],
        "cat": p.category or "",
        "buys": fmt_count(p.purchases),
        "custs": fmt_count(p.customers),
        "rev": fmt_money(p.revenue_month),
        "spark": spark_norm(p.revenue_series),
        "st": p.state.value,
    }


def _cockpit_repo(r: GitHubRepoStats, now: datetime) -> dict:
    owner, _, short = r.name.partition("/")
    return {
        "name": (short or r.name)[:24],
        "owner": owner[:24],
        "lang": (r.language or "")[:16],
        "lcol": lang_color(r.language),
        "stars": fmt_count(r.stars),
        "issues": fmt_count(r.open_issues),
        "prs": fmt_count(r.open_prs),
        "push": fmt_relative(r.pushed_at, now),
        "st": r.state.value,
    }


# Language dot colors from the handoff (GitHub page). Unknown -> "" (device
# falls back to its muted default).
_LANG_COLOR = {
    "c++": "#8FBF7F",
    "swift": "#E0B25A",
    "typescript": "#6AA0D8",
    "go": "#6AA0D8",
    "rust": "#D08770",
}


def lang_color(language: str | None) -> str:
    if not language:
        return ""
    return _LANG_COLOR.get(language.lower(), "")


def derive_alerts(
    cloudflare: list[CloudflareZoneStats],
    claude: list[AccountUsage],
    github: list[GitHubRepoStats],
    now: datetime,
    *,
    usage_threshold: int = DEFAULT_USAGE_THRESHOLD,
    alert_on_down: bool = True,
    alert_on_4xx: bool = True,
    watched_repos: set[str] | None = None,
) -> list[dict]:
    """Derive the alerts panel from live data + admin toggles, per the handoff:

    - any shown site `down`               -> CRITICAL (gated on `alert_on_down`)
    - any shown site `degraded`           -> WARNING  (gated on `alert_on_4xx`)
    - any account 5h usage >= threshold   -> WARNING
    - a watched repo with open issues     -> INFO

    Returned sorted CRITICAL -> WARNING -> INFO (stable within a level, so ties
    keep source order). Each alert: {lvl, tag, time, msg, src}. `time` is the
    host-rendered relative age; alerts derived from the current snapshot use
    "now" since they reflect this fetch. `watched_repos` is the set of
    owner/repo slugs whose new issues raise an INFO (defaults to all shown)."""
    alerts: list[tuple[AlertLevel, dict]] = []

    for z in cloudflare[:MAX_COCKPIT_ZONES]:
        status = site_status(z)
        if status == "down" and alert_on_down:
            alerts.append((AlertLevel.CRITICAL, _alert(
                AlertLevel.CRITICAL, now, f"{z.name} is offline", "Cloudflare"
            )))
        elif status == "degraded" and alert_on_4xx:
            alerts.append((AlertLevel.WARNING, _alert(
                AlertLevel.WARNING, now, f"{z.name} error rate elevated", "Cloudflare"
            )))

    for snap in claude[:MAX_COCKPIT_ACCOUNTS]:
        pct = snap.five_hour.pct
        if pct is not None and pct >= usage_threshold:
            alerts.append((AlertLevel.WARNING, _alert(
                AlertLevel.WARNING, now,
                f"{snap.label} at {pct}% of 5h window", "Anthropic"
            )))

    watch = watched_repos
    for r in github[:MAX_COCKPIT_REPOS]:
        if watch is not None and r.name not in watch:
            continue
        if r.open_issues:
            alerts.append((AlertLevel.INFO, _alert(
                AlertLevel.INFO, now,
                f"{r.name} has {r.open_issues} open issues", "GitHub"
            )))

    # Stable sort by severity; Python's sort is stable so within-level order is
    # the insertion order above (Cloudflare rows in config order, etc.).
    alerts.sort(key=lambda pair: pair[0])
    return [a for _, a in alerts[:MAX_COCKPIT_ALERTS]]


def _alert(level: AlertLevel, now: datetime, message: str, source: str) -> dict:
    return {
        "lvl": int(level),
        "tag": level.tag,
        "time": "now",
        "msg": message,
        "src": source,
    }


def _cockpit_base(now: datetime) -> int:
    """Seconds-since-local-midnight seed for the device header clock. The device
    increments this each second and formats HH:MM itself — the one sanctioned
    clock relaxation (it can't call the host between pushes)."""
    local = now.astimezone()
    return local.hour * 3600 + local.minute * 60 + local.second


def to_cockpit_payload(
    claude: list[AccountUsage],
    cloudflare: list[CloudflareZoneStats],
    paddle: list[PaddleProductStats],
    paddle_totals: PaddleTotals,
    github: list[GitHubRepoStats],
    now: datetime,
    *,
    usage_threshold: int = DEFAULT_USAGE_THRESHOLD,
    alert_on_down: bool = True,
    alert_on_4xx: bool = True,
    watched_repos: set[str] | None = None,
) -> dict:
    """Build the enriched `set_cockpit` payload for the redesigned 800x480 UI.

    Every count/label is a pre-formatted string exactly as the host-rendering
    contract requires; the only numeric-time deviations are `base` (header clock
    seed) and each account's `fh_sec` (seconds to the 5h reset). Percents and
    normalized series stay raw ints for the device's bars/sparklines/histograms.

    Sources are independently capped (3 accounts / 12 sites / 4 products / 6
    repos); alert toggles + the usage threshold are parameters (Phase 3 wires
    them to admin config)."""
    accounts = [
        _cockpit_account(s, now)
        for s in sorted(claude, key=lambda s: s.label)[:MAX_COCKPIT_ACCOUNTS]
    ]

    cf_shown = cloudflare[:MAX_COCKPIT_ZONES]
    cf_totals = _cloudflare_totals(cf_shown)
    down = sum(1 for z in cf_shown if site_status(z) == "down")
    degraded = sum(1 for z in cf_shown if site_status(z) == "degraded")

    products = [_cockpit_product(p) for p in paddle[:MAX_COCKPIT_PRODUCTS]]
    repos = [_cockpit_repo(r, now) for r in github[:MAX_COCKPIT_REPOS]]

    alerts = derive_alerts(
        cloudflare, claude, github, now,
        usage_threshold=usage_threshold,
        alert_on_down=alert_on_down,
        alert_on_4xx=alert_on_4xx,
        watched_repos=watched_repos,
    )

    return {
        "cmd": "set_cockpit",
        "params": {
            "updated": now.astimezone().strftime("%H:%M"),
            "base": _cockpit_base(now),
            "date": now.astimezone().strftime("%a %-d %b"),
            "anthropic": {"accounts": accounts},
            "cloudflare": {
                "totals": cf_totals,
                "down": down,
                "degraded": degraded,
                "sites": [_cockpit_site(z, now) for z in cf_shown],
            },
            "paddle": {
                "totals": {
                    "rev_today": fmt_money(paddle_totals.revenue_today),
                    "rev_month": fmt_money(paddle_totals.revenue_month),
                    "sales": fmt_count(paddle_totals.sales),
                    "custs": fmt_count(paddle_totals.customers),
                    "mom": fmt_signed_pct(paddle_totals.mom_pct),
                },
                "products": products,
            },
            "github": {
                "summary": {
                    "repos": len(github[:MAX_COCKPIT_REPOS]),
                    "issues": fmt_count(
                        _sum_known(github[:MAX_COCKPIT_REPOS], "open_issues")
                    ),
                    "prs": fmt_count(
                        _sum_known(github[:MAX_COCKPIT_REPOS], "open_prs")
                    ),
                },
                "repos": repos,
            },
            "alerts": alerts,
        },
    }


def _cloudflare_totals(zones: list[CloudflareZoneStats]) -> dict:
    """Combined Cloudflare figures across the shown zones for the totals strip:
    requests today, bandwidth, threats, cache-hit %. Cache-hit is a weighted
    ratio over the summed requests, not a mean of per-zone percents."""
    req = _sum_known(zones, "requests")
    threats = _sum_known(zones, "threats")
    total_bytes = _sum_known(zones, "bytes")
    cached = _sum_known(zones, "cached_requests")
    cache_pct = round(100 * cached / req) if req and cached is not None else -1
    return {
        "req": fmt_count(req),
        "bw": fmt_bytes(total_bytes),
        "threats": fmt_count(threats),
        "cache": cache_pct,
    }


def _sum_known(rows: list, attr: str) -> int | None:
    vals = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
    return sum(vals) if vals else None


_STATE_LABEL = {
    AccountState.OK: "OK",
    AccountState.AUTH: "AUTH FAILED (re-login)",
    AccountState.ERROR: "FETCH ERROR",
    AccountState.DRIFT: "SCHEMA DRIFT",
}


def status_table(snapshots: list[AccountUsage], now: datetime) -> str:
    header = ("ACCOUNT", "5H USED", "5H RESETS", "WEEK USED", "WEEK RESETS", "STATE")
    rows = [header, tuple("-" * len(h) for h in header)]
    for snap in sorted(snapshots, key=lambda s: s.label):
        def pct(w: WindowUsage) -> str:
            return f"{w.pct}%" if w.pct is not None else "--"

        rows.append(
            (
                snap.label,
                pct(snap.five_hour),
                fmt_countdown(snap.five_hour.resets_at, now) or "--",
                pct(snap.week),
                fmt_countdown(snap.week.resets_at, now) or "--",
                _STATE_LABEL.get(snap.state, snap.state.value),
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    return "\n".join(
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in rows
    )
