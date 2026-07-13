"""Tests for the AutoLink composite transport (WiFi-first, serial fallback).

The interesting behaviour is the selection/fallback logic, exercised here with
fake links (no sockets/serial): prefer the first that connects, fall back to the
next, and re-select from the top after a drop so it returns to WiFi."""

from __future__ import annotations

from claudemon.net_link import AutoLink


class FakeLink:
    """Minimal DeviceLink-shaped stub."""

    def __init__(self, name: str, can_connect: bool = True) -> None:
        self.name = name
        self.port = name
        self._can = can_connect
        self.connected = False
        self.drop_on_send = False
        self.sent: list = []

    def connect(self) -> bool:
        self.connected = self._can
        return self._can

    def close(self) -> None:
        self.connected = False

    def send_command(self, command: dict):
        if self.drop_on_send:
            self.connected = False
            return None
        self.sent.append(command)
        return {"status": "ok", "cmd": command.get("cmd")}


def test_prefers_first_link():
    wifi, serial = FakeLink("wifi"), FakeLink("serial")
    link = AutoLink([wifi, serial])
    assert link.connect() is True
    assert link.connected and link.port == "wifi"
    assert not serial.connected          # serial was never tried


def test_falls_back_when_first_fails():
    wifi = FakeLink("wifi", can_connect=False)
    serial = FakeLink("serial")
    link = AutoLink([wifi, serial])
    assert link.connect() is True
    assert link.port == "serial"


def test_connect_fails_when_all_fail():
    link = AutoLink([FakeLink("wifi", False), FakeLink("serial", False)])
    assert link.connect() is False
    assert not link.connected
    assert link.port == "auto"


def test_reselects_wifi_after_drop():
    wifi, serial = FakeLink("wifi"), FakeLink("serial")
    link = AutoLink([wifi, serial])
    link.connect()                        # picks wifi
    wifi.drop_on_send = True
    assert link.send_command({"cmd": "x"}) is None
    assert not link.connected             # active cleared on the drop
    wifi.drop_on_send = False             # wifi healthy again
    assert link.connect() is True
    assert link.port == "wifi"            # re-preferred, not stuck on serial


def test_send_routes_to_active_link():
    wifi, serial = FakeLink("wifi"), FakeLink("serial")
    link = AutoLink([wifi, serial])
    link.connect()
    link.send_command({"cmd": "ping"})
    assert wifi.sent == [{"cmd": "ping"}]
    assert serial.sent == []
