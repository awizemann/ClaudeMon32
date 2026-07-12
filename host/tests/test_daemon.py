"""Tests for the cockpit daemon: settings flowing into the payload (threshold +
toggles actually change the derived alerts), change-detection that ignores the
live-tick fields (base / fh_sec / updated), and the config-driven refresh floor.

No serial device or live tokens — the collector and config are monkeypatched."""

from __future__ import annotations

from datetime import timedelta

import pytest

from claudemon import collect, config as configmod, daemon
from claudemon.models import (
    AccountState,
    AccountUsage,
    CloudflareZoneStats,
    WindowUsage,
)
from tests.conftest import NOW


# --------------------------------------------------------------- refresh floor


class TestRefreshInterval:
    def test_uses_config_refresh(self, monkeypatch):
        monkeypatch.setattr(
            configmod, "load",
            lambda: configmod.Config(settings=configmod.Settings(refresh=90)),
        )
        assert daemon._refresh_interval() == 90.0

    def test_floors_low_refresh(self, monkeypatch):
        monkeypatch.setattr(
            configmod, "load",
            lambda: configmod.Config(settings=configmod.Settings(refresh=1)),
        )
        assert daemon._refresh_interval() == daemon.MIN_REFRESH_S

    def test_bad_config_falls_back_to_default(self, monkeypatch):
        def boom():
            raise ValueError("corrupt config")
        monkeypatch.setattr(configmod, "load", boom)
        assert daemon._refresh_interval() == float(daemon.DEFAULT_REFRESH_S)


# ------------------------------------------------------- settings -> alerts wiring


def _account_at(pct: int) -> AccountUsage:
    return AccountUsage(
        label="acct",
        five_hour=WindowUsage(pct=pct, resets_at=NOW + timedelta(hours=1)),
        week=WindowUsage(pct=10, resets_at=NOW + timedelta(days=3)),
    )


def _down_zone() -> CloudflareZoneStats:
    return CloudflareZoneStats(name="site.com", state=AccountState.ERROR)


def _collector_returning(claude, cf, pd, gh):
    class _Stub:
        def collect(self):
            return claude, cf, pd, gh
    return _Stub()


class TestSettingsIntoPayload:
    def test_usage_threshold_gates_the_warning(self, monkeypatch):
        collector = _collector_returning([_account_at(85)], [], [], [])

        # High threshold: 85% is below it -> no usage alert.
        monkeypatch.setattr(
            configmod, "load",
            lambda: configmod.Config(settings=configmod.Settings(usage_threshold=90)),
        )
        payload, _ = daemon._build_payload(collector, NOW)
        assert not any(a["src"] == "Anthropic" for a in payload["params"]["alerts"])

        # Lower the threshold below 85 -> the usage WARNING now fires.
        monkeypatch.setattr(
            configmod, "load",
            lambda: configmod.Config(settings=configmod.Settings(usage_threshold=80)),
        )
        payload, _ = daemon._build_payload(collector, NOW)
        assert any(a["src"] == "Anthropic" for a in payload["params"]["alerts"])

    def test_alert_down_toggle(self, monkeypatch):
        collector = _collector_returning([], [_down_zone()], [], [])

        monkeypatch.setattr(
            configmod, "load",
            lambda: configmod.Config(settings=configmod.Settings(alert_down=False)),
        )
        payload, _ = daemon._build_payload(collector, NOW)
        assert not any(a["tag"] == "CRITICAL" for a in payload["params"]["alerts"])

        monkeypatch.setattr(
            configmod, "load",
            lambda: configmod.Config(settings=configmod.Settings(alert_down=True)),
        )
        payload, _ = daemon._build_payload(collector, NOW)
        assert any(a["tag"] == "CRITICAL" for a in payload["params"]["alerts"])


# ------------------------------------------------------------- change detection


class TestComparable:
    def _payload(self, base, updated, fh_sec, fh_pct=50):
        return {
            "params": {
                "base": base,
                "updated": updated,
                "anthropic": {
                    "accounts": [{"label": "A", "fh_sec": fh_sec, "fh_pct": fh_pct}]
                },
                "cloudflare": {"sites": []},
            }
        }

    def test_ignores_base_updated_and_fh_sec(self):
        a = self._payload(base=100, updated="14:32", fh_sec=3600)
        b = self._payload(base=200, updated="14:33", fh_sec=3599)
        # Only the live-tick fields differ -> comparable strings match.
        assert daemon._comparable(a) == daemon._comparable(b)

    def test_real_content_change_is_detected(self):
        a = self._payload(base=100, updated="14:32", fh_sec=3600, fh_pct=50)
        b = self._payload(base=100, updated="14:32", fh_sec=3600, fh_pct=51)
        assert daemon._comparable(a) != daemon._comparable(b)

    def test_does_not_mutate_the_push_payload(self):
        p = self._payload(base=100, updated="14:32", fh_sec=3600)
        daemon._comparable(p)
        # base/updated/fh_sec must survive so the real push still carries them.
        assert p["params"]["base"] == 100
        assert p["params"]["updated"] == "14:32"
        assert p["params"]["anthropic"]["accounts"][0]["fh_sec"] == 3600


# --------------------------------------------------------- change-detection + heartbeat loop


class FakeLink:
    """Serial stand-in: always connected, records every pushed payload."""

    def __init__(self):
        self.connected = True
        self.port = "/dev/fake"
        self.sent = []

    def connect(self):
        self.connected = True
        return True

    def send_command(self, payload):
        self.sent.append(payload)
        return {"status": "ok", "cmd": payload.get("cmd")}


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class LoopExit(Exception):
    """Raised from the patched sleep to break out after N cycles."""


def _run_n_cycles(monkeypatch, collector, n, clock):
    """Drive run_loop for `n` cycles, advancing the monotonic clock by one
    heartbeat interval between each so we can observe heartbeat pushes."""
    link = FakeLink()
    monkeypatch.setattr(daemon, "DeviceLink", lambda: link)
    monkeypatch.setattr(daemon.collect, "DashboardCollector", lambda: collector)
    monkeypatch.setattr(daemon.keychain, "list_accounts", lambda: ["acct"])
    monkeypatch.setattr(daemon.time, "monotonic", clock)
    monkeypatch.setattr(daemon, "utcnow", lambda: NOW)
    monkeypatch.setattr(daemon, "write_state", lambda snaps: None)
    monkeypatch.setattr(daemon, "_settings", lambda: configmod.Settings())

    state = {"cycles": 0}

    def fake_sleep(_secs):
        state["cycles"] += 1
        if state["cycles"] >= n:
            raise LoopExit
        clock.t += daemon.HEARTBEAT_PUSH_S + 1  # advance past the heartbeat window

    monkeypatch.setattr(daemon.time, "sleep", fake_sleep)
    with pytest.raises(LoopExit):
        daemon.run_loop()
    return link


class TestRunLoop:
    def test_pushes_once_then_only_on_change(self, monkeypatch):
        # Same data every cycle -> first push (change vs None), then heartbeats.
        collector = _collector_returning([_account_at(50)], [], [], [])
        # Keep the clock still so heartbeat never trips: only the initial change pushes.
        clock = FakeClock()

        link = FakeLink()
        monkeypatch.setattr(daemon, "DeviceLink", lambda: link)
        monkeypatch.setattr(daemon.collect, "DashboardCollector", lambda: collector)
        monkeypatch.setattr(daemon.keychain, "list_accounts", lambda: ["acct"])
        monkeypatch.setattr(daemon.time, "monotonic", clock)
        monkeypatch.setattr(daemon, "utcnow", lambda: NOW)
        monkeypatch.setattr(daemon, "write_state", lambda snaps: None)
        monkeypatch.setattr(daemon, "_settings", lambda: configmod.Settings())

        cycles = {"n": 0}

        def fake_sleep(_s):
            cycles["n"] += 1
            if cycles["n"] >= 3:
                raise LoopExit
            # clock frozen -> no heartbeat

        monkeypatch.setattr(daemon.time, "sleep", fake_sleep)
        with pytest.raises(LoopExit):
            daemon.run_loop()
        assert len(link.sent) == 1  # unchanged content, no heartbeat -> single push

    def test_heartbeat_pushes_even_when_unchanged(self, monkeypatch):
        collector = _collector_returning([_account_at(50)], [], [], [])
        clock = FakeClock()
        link = _run_n_cycles(monkeypatch, collector, n=3, clock=clock)
        # cycle 1: change push; cycles 2 & 3: clock jumped a heartbeat each -> push.
        assert len(link.sent) == 3
        assert all(p["cmd"] == "set_cockpit" for p in link.sent)
