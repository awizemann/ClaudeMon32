"""Rendering: terminal status table and the set_usage device payload.

The host renders ALL strings (countdowns, updated-at). The device does no
clock math — it only draws labels, bars from integer percents, and these
pre-formatted strings.
"""

from __future__ import annotations

from datetime import datetime

from .models import AccountState, AccountUsage, WindowUsage

MAX_DEVICE_ACCOUNTS = 4
MAX_LABEL_LEN = 10


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


def fmt_renewal(resets_at: datetime | None) -> str:
    """Human-readable weekly renewal in local time, e.g. "WED 8PM"."""
    if resets_at is None:
        return ""
    local = resets_at.astimezone()
    hour = local.strftime("%I").lstrip("0")
    ampm = "AM" if local.hour < 12 else "PM"
    return f"{local.strftime('%a').upper()} {hour}{ampm}"


def _pct_or_unknown(w: WindowUsage) -> int:
    return w.pct if w.pct is not None else -1


def to_device_payload(snapshots: list[AccountUsage], now: datetime) -> dict:
    accounts = []
    for snap in sorted(snapshots, key=lambda s: s.label)[:MAX_DEVICE_ACCOUNTS]:
        accounts.append(
            {
                "label": snap.label.upper()[:MAX_LABEL_LEN],
                "fh_pct": _pct_or_unknown(snap.five_hour),
                "fh_rst": fmt_countdown(snap.five_hour.resets_at, now),
                "wk_pct": _pct_or_unknown(snap.week),
                "wk_rnw": fmt_renewal(snap.week.resets_at),
                "st": snap.state.value,
            }
        )
    return {
        "cmd": "set_usage",
        "params": {
            "updated": now.astimezone().strftime("%H:%M"),
            "accounts": accounts,
        },
    }


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
