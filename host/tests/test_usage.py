"""Tests for usage.parse_usage — the OAuth usage-endpoint parser.

Shapes mirror the live response verified via `claudemon probe` (five_hour /
seven_day top-level objects + a limits[] array carrying kind/percent/severity/
resets_at). Previously parse_usage had no direct coverage, which is how the
server's per-window `severity` and the `weekly_scoped` limit went unused."""

from __future__ import annotations

from claudemon.models import AccountState
from claudemon.usage import parse_usage


def _resp(fh=11.0, wk=6.0, *, fh_sev="normal", wk_sev="normal", scoped_pct=None, scoped_sev=None,
          active="session", spend=None):
    limits = [
        {"kind": "session", "percent": int(fh), "severity": fh_sev,
         "resets_at": "2026-07-13T02:00:00+00:00", "is_active": active == "session"},
        {"kind": "weekly_all", "percent": int(wk), "severity": wk_sev,
         "resets_at": "2026-07-19T05:00:00+00:00", "is_active": active == "weekly_all"},
    ]
    if scoped_pct is not None:
        limits.append({"kind": "weekly_scoped", "percent": scoped_pct, "severity": scoped_sev,
                       "resets_at": "2026-07-19T05:00:00+00:00", "is_active": active == "weekly_scoped"})
    resp = {
        "five_hour": {"utilization": fh, "resets_at": "2026-07-13T02:00:00+00:00"},
        "seven_day": {"utilization": wk, "resets_at": "2026-07-19T05:00:00+00:00"},
        "limits": limits,
    }
    if spend is not None:
        resp["spend"] = spend
    return resp


class TestParseUsage:
    def test_windows_and_state_ok(self):
        u = parse_usage("acct", _resp(fh=11.0, wk=6.0))
        assert u.state is AccountState.OK
        assert u.five_hour.pct == 11
        assert u.week.pct == 6
        assert u.five_hour.resets_at is not None

    def test_severity_lifted_from_limits(self):
        # pct/resets come from the top-level object; severity from the limit entry.
        u = parse_usage("acct", _resp(wk=88.0, wk_sev="warning"))
        assert u.week.pct == 88
        assert u.week.severity == "warning"
        assert u.five_hour.severity == "normal"

    def test_weekly_scoped_parsed_when_present(self):
        u = parse_usage("acct", _resp(scoped_pct=81, scoped_sev="warning"))
        assert u.week_scoped.pct == 81
        assert u.week_scoped.severity == "warning"

    def test_weekly_scoped_absent_is_empty_not_drift(self):
        # Most accounts have no scoped cap; its absence must not trip drift.
        u = parse_usage("acct", _resp())  # no weekly_scoped in limits
        assert u.week_scoped.pct is None
        assert u.week_scoped.severity is None
        assert u.state is AccountState.OK

    def test_falls_back_to_limits_when_top_level_missing(self):
        # No five_hour/seven_day objects — pct must come from limits[].
        data = _resp()
        data.pop("five_hour")
        data.pop("seven_day")
        u = parse_usage("acct", data)
        assert u.five_hour.pct == 11   # from the session limit
        assert u.week.pct == 6         # from the weekly_all limit
        assert u.state is AccountState.OK

    def test_active_window_from_is_active(self):
        u = parse_usage("acct", _resp(active="weekly_all"))
        assert u.week.active is True
        assert u.five_hour.active is False

    def test_credits_enabled_converts_minor_units(self):
        spend = {
            "enabled": True,
            "used": {"amount_minor": 3, "currency": "USD", "exponent": 2},
            "limit": {"amount_minor": 25000, "currency": "USD", "exponent": 2},
        }
        u = parse_usage("acct", _resp(spend=spend))
        assert u.credits_enabled is True
        assert u.credits_used == 0.03
        assert u.credits_limit == 250.0

    def test_credits_disabled_is_empty(self):
        spend = {"enabled": False, "used": {"amount_minor": 0, "exponent": 2}}
        u = parse_usage("acct", _resp(spend=spend))
        assert u.credits_enabled is False
        assert u.credits_used is None

    def test_drift_when_no_window_found(self):
        u = parse_usage("acct", {"unexpected": True})
        assert u.state is AccountState.DRIFT
        assert u.five_hour.pct is None
