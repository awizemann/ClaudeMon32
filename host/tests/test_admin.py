"""Tests for the web-admin API layer (admin.py). No live tokens, devices, or
sockets: AdminState is driven against monkeypatched keychain/config/discovery,
and the HTTP routing is exercised through a fake request handler that captures
the response instead of writing to a socket.

Focus areas from the Phase 3c spec:
  * /api/state shape omits every secret (only presence booleans)
  * /api/config tri-state round-trips (absent = leave, null = all, [] = none, list)
  * /api/token writes/deletes the Keychain (mocked) and never logs the value
  * settings clamping + validation (400 on bad input)
  * routing (GET /, /api/state; POST /api/token, /api/config; 404s)
"""

from __future__ import annotations

import json

import pytest

from claudemon import admin, config as configmod


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A sandboxed admin environment: config redirected to a temp file, and the
    Keychain + discovery replaced with in-memory fakes. Returns a small handle
    exposing the fakes so tests can assert on writes."""
    # Redirect config storage.
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(configmod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(configmod, "CONFIG_FILE", cfg_path)

    class Fakes:
        secrets: dict[str, str] = {}
        accounts: list[str] = []
        zones: list[dict] = []
        repos: list[str] = []
        products: list[str] = []
        logged: list[str] = []

    f = Fakes()

    # Keychain: back tokens with a dict; record account list.
    monkeypatch.setattr(admin.keychain, "load_secret", lambda name: f.secrets.get(name))
    monkeypatch.setattr(admin.keychain, "save_secret",
                        lambda name, value: f.secrets.__setitem__(name, value))
    monkeypatch.setattr(admin.keychain, "delete_secret",
                        lambda name: f.secrets.pop(name, None))
    monkeypatch.setattr(admin.keychain, "list_accounts", lambda: list(f.accounts))

    # Discovery: bypass the collector's httpx calls entirely.
    monkeypatch.setattr(admin.collect.DashboardCollector, "_list_zones",
                        lambda self, token: list(f.zones))
    monkeypatch.setattr(admin.collect.DashboardCollector, "_list_repos",
                        lambda self, token: list(f.repos))
    monkeypatch.setattr(admin.collect.DashboardCollector, "_list_products",
                        lambda self, token: list(f.products))

    return f


@pytest.fixture
def state(env):
    # Fresh clock so the 5s state cache doesn't bleed between calls we want live.
    ticks = iter(range(0, 100_000, 100))  # 100s apart -> always past the TTL
    return admin.AdminState(clock=lambda: next(ticks))


# ------------------------------------------------------------- /api/state


class TestState:
    def test_shape_and_no_secrets(self, env, state):
        env.secrets = {"cloudflare": "cf-tok", "github": "gh-tok"}
        env.accounts = ["Personal", "Work"]
        env.zones = [{"id": "z1", "name": "a.com"}, {"id": "z2", "name": "b.com"}]
        env.repos = ["o/r1"]
        st = state.state()

        # Structure.
        assert set(st) == {"sources", "anthropic", "settings"}
        assert set(st["sources"]) == {"cloudflare", "github", "paddle"}

        # Connectivity is presence-only; the token value never appears anywhere.
        assert st["sources"]["cloudflare"]["connected"] is True
        assert st["sources"]["paddle"]["connected"] is False
        assert st["anthropic"]["accounts"] == ["Personal", "Work"]
        blob = json.dumps(st)
        assert "cf-tok" not in blob and "gh-tok" not in blob

        # Discovered lists pass through.
        assert st["sources"]["cloudflare"]["discovered"] == env.zones
        assert st["sources"]["github"]["discovered"] == ["o/r1"]
        # shown defaults to None (never configured -> show all).
        assert st["sources"]["cloudflare"]["shown"] is None

    def test_disconnected_service_has_no_discovery(self, env, state):
        env.zones = [{"id": "z1", "name": "a.com"}]  # would discover IF connected
        st = state.state()
        assert st["sources"]["cloudflare"]["connected"] is False
        assert st["sources"]["cloudflare"]["discovered"] == []

    def test_shown_reflects_config(self, env, state):
        env.secrets = {"github": "t"}
        cfg = configmod.Config(github_shown=["o/r1"])
        configmod.save(cfg)
        st = state.state()
        assert st["sources"]["github"]["shown"] == ["o/r1"]

    def test_settings_defaults(self, env, state):
        st = state.state()
        assert st["settings"] == {
            "brightness": 100, "refresh": 60, "usage_threshold": 80,
            "alert_down": True, "alert_4xx": True,
        }

    def test_state_is_cached_within_ttl(self, env):
        # Same clock value both calls -> the second is served from cache, so a
        # keychain change mid-window is not reflected until the TTL lapses.
        st = admin.AdminState(clock=lambda: 1.0)
        first = st.state()
        env.accounts = ["New"]
        second = st.state()
        assert first == second  # cached
        assert second["anthropic"]["accounts"] == []


# ------------------------------------------------------------- /api/token


class TestToken:
    def test_save_writes_keychain(self, env, state):
        res = state.save_token({"service": "cloudflare", "token": "  secret-value  "})
        assert res == {"service": "cloudflare", "connected": True}
        assert env.secrets["cloudflare"] == "secret-value"  # trimmed

    def test_empty_token_deletes(self, env, state):
        env.secrets = {"github": "old"}
        res = state.save_token({"service": "github", "token": "   "})
        assert res == {"service": "github", "connected": False}
        assert "github" not in env.secrets

    def test_delete_flag_deletes(self, env, state):
        env.secrets = {"paddle": "old"}
        state.save_token({"service": "paddle", "token": "x", "delete": True})
        assert "paddle" not in env.secrets

    def test_unknown_service_rejected(self, env, state):
        with pytest.raises(admin._BadRequest):
            state.save_token({"service": "anthropic", "token": "x"})

    def test_token_value_never_logged(self, env, state, caplog):
        import logging
        caplog.set_level(logging.DEBUG, logger="claudemon.admin")
        state.save_token({"service": "cloudflare", "token": "sup3r-secret"})
        assert "sup3r-secret" not in caplog.text


# ------------------------------------------------------------- /api/config


class TestConfig:
    def test_tristate_null_is_show_all(self, env, state):
        # Start from an explicit selection, then null it -> back to show-all (None).
        configmod.save(configmod.Config(cloudflare_shown=["z1"]))
        state.save_config({"cloudflare_shown": None})
        assert configmod.load().cloudflare_shown is None

    def test_tristate_empty_is_none_shown(self, env, state):
        state.save_config({"github_shown": []})
        assert configmod.load().github_shown == []

    def test_tristate_subset_persists_in_order(self, env, state):
        state.save_config({"paddle_shown": ["B", "A"]})
        assert configmod.load().paddle_shown == ["B", "A"]

    def test_absent_key_leaves_selection_untouched(self, env, state):
        configmod.save(configmod.Config(github_shown=["keep"]))
        state.save_config({"cloudflare_shown": ["z1"]})  # github key absent
        loaded = configmod.load()
        assert loaded.github_shown == ["keep"]
        assert loaded.cloudflare_shown == ["z1"]

    def test_settings_clamped(self, env, state):
        state.save_config({"settings": {
            "brightness": 5, "refresh": 9999, "usage_threshold": 200,
        }})
        s = configmod.load().settings
        assert s.brightness == 15     # clamped up to min
        assert s.refresh == 300       # clamped down to max
        assert s.usage_threshold == 100

    def test_settings_partial_update(self, env, state):
        configmod.save(configmod.Config())  # defaults
        state.save_config({"settings": {"alert_down": False}})
        s = configmod.load().settings
        assert s.alert_down is False
        assert s.alert_4xx is True     # untouched default

    def test_bad_shown_type_rejected(self, env, state):
        with pytest.raises(admin._BadRequest):
            state.save_config({"cloudflare_shown": "not-a-list"})

    def test_bad_setting_type_rejected(self, env, state):
        with pytest.raises(admin._BadRequest):
            state.save_config({"settings": {"brightness": "loud"}})
        with pytest.raises(admin._BadRequest):
            state.save_config({"settings": {"alert_down": "yes"}})

    def test_config_round_trips_through_state(self, env, state):
        # A subset saved via /api/config surfaces in /api/state's shown.
        env.secrets = {"cloudflare": "t"}
        env.zones = [{"id": "z1", "name": "a.com"}, {"id": "z2", "name": "b.com"}]
        state.save_config({"cloudflare_shown": ["z2"]})
        st = state.state()
        assert st["sources"]["cloudflare"]["shown"] == ["z2"]


# ------------------------------------------------------------- HTTP routing


class FakeRequest:
    """Drives an AdminHandler without a real socket: feeds a request line +
    headers + optional body, captures the status/headers/body written back."""

    def __init__(self, handler_cls, method, path, body=None):
        import io
        self.handler_cls = handler_cls
        raw = b"" if body is None else json.dumps(body).encode()
        headers = f"{method} {path} HTTP/1.1\r\nContent-Length: {len(raw)}\r\n\r\n"
        self.rfile = io.BytesIO(headers.encode() + raw)
        self.wfile = io.BytesIO()

    def run(self):
        # Construct without invoking BaseHTTPRequestHandler.__init__ (which would
        # try to handle the connection); wire the minimal attributes and dispatch.
        h = self.handler_cls.__new__(self.handler_cls)
        h.rfile = self.rfile
        h.wfile = self.wfile
        h.client_address = ("127.0.0.1", 0)
        h.request_version = "HTTP/1.1"
        h.raw_requestline = self.rfile.readline()
        h.parse_request()
        method = getattr(h, "do_" + h.command)
        method()
        return _parse_response(self.wfile.getvalue())


def _parse_response(raw: bytes):
    head, _, body = raw.partition(b"\r\n\r\n")
    status_line = head.split(b"\r\n", 1)[0]
    code = int(status_line.split()[1])
    return code, body


@pytest.fixture
def handler(env):
    st = admin.AdminState(clock=lambda: 1.0)
    return admin.make_handler(st)


class TestRouting:
    def test_get_root_serves_page(self, handler):
        code, body = FakeRequest(handler, "GET", "/").run()
        assert code == 200
        assert b"ClaudeMon" in body and b"<html" in body.lower()

    def test_get_state_returns_json(self, handler):
        code, body = FakeRequest(handler, "GET", "/api/state").run()
        assert code == 200
        data = json.loads(body)
        assert "sources" in data and "settings" in data

    def test_get_unknown_404(self, handler):
        code, _ = FakeRequest(handler, "GET", "/nope").run()
        assert code == 404

    def test_post_token_ok(self, handler, env):
        code, body = FakeRequest(
            handler, "POST", "/api/token",
            body={"service": "cloudflare", "token": "abc"},
        ).run()
        assert code == 200
        assert env.secrets["cloudflare"] == "abc"

    def test_post_config_ok(self, handler):
        code, _ = FakeRequest(
            handler, "POST", "/api/config",
            body={"settings": {"brightness": 50}},
        ).run()
        assert code == 200
        assert configmod.load().settings.brightness == 50

    def test_post_bad_json_is_400(self, handler):
        code, body = FakeRequest(
            handler, "POST", "/api/config",
            body={"cloudflare_shown": "bad"},
        ).run()
        assert code == 400
        assert b"error" in body

    def test_post_unknown_404(self, handler):
        code, _ = FakeRequest(handler, "POST", "/api/nope", body={}).run()
        assert code == 404
