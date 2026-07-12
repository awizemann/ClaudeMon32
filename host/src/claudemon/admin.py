"""Host-served web admin: a LAN-reachable config console for the cockpit.

Phase 3c. This is the browser counterpart to the CLI's set-token/zones/repos/
products commands: it presents the four sources (Anthropic/Cloudflare/Paddle/
GitHub) as Sources / Displays / Alerts / Device tabs and writes back to the same
stores the daemon reads — the Keychain (tokens) and config.py (selection +
settings). Changes therefore take effect on the daemon's next poll cycle (it
reloads config each cycle).

Design intent (see design_handoff .../README.md, screens 06-09): the page is a
single self-contained HTML/CSS/JS file with no external requests, so it ports
onto the ESP32's own HTTP server in Phase 4 — the firmware serves the same page
and speaks the same tiny JSON API (/api/state, /api/token, /api/config).

Security posture: single-user / local. No auth framework — it binds to the LAN
and is meant for a trusted home network; the bind host is logged plainly so the
operator knows its reach. Tokens are NEVER returned by any GET and NEVER logged;
they only travel inbound on POST /api/token straight into the Keychain.
"""

from __future__ import annotations

import json
import logging
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import collect, config as configmod, keychain, render

log = logging.getLogger(__name__)

DEFAULT_PORT = 8770
DEFAULT_HOST = "0.0.0.0"

# The three global-token services (Anthropic is per-account OAuth, handled apart).
_TOKEN_SERVICES = ("cloudflare", "github", "paddle")

# The page polls /api/state; the collector already caches discovery per token,
# but we add a short state-level TTL so a burst of polls doesn't even walk the
# collector's cache-checks (and so a page left open isn't hammering the box).
_STATE_TTL_S = 5.0

# Settings bounds (mirror the design sliders). Values are clamped, not rejected.
_BRIGHTNESS_MIN, _BRIGHTNESS_MAX = 15, 100
_REFRESH_MIN, _REFRESH_MAX = 15, 300
_THRESHOLD_MIN, _THRESHOLD_MAX = 50, 100

# Reject absurd request bodies outright (the API only ever carries tiny JSON).
_MAX_BODY_BYTES = 256 * 1024

_PAGE_PATH = Path(__file__).with_name("admin.html")


class AdminState:
    """Assembles /api/state and applies /api/config + /api/token writes.

    Holds a long-lived DashboardCollector so discovery (list_zones/list_repos/
    list_products) is cached exactly as it is for the daemon — the page can poll
    state without re-enumerating every zone/repo on the upstream APIs each time.
    A small extra TTL memoises the whole assembled state between rapid polls."""

    def __init__(self, *, clock=time.monotonic) -> None:
        self._clock = clock
        self._collector = collect.DashboardCollector()
        self._cache: tuple[float, dict] | None = None

    # -- reads -------------------------------------------------------------

    def state(self) -> dict:
        cached = self._cache
        now = self._clock()
        if cached is not None and (now - cached[0]) < _STATE_TTL_S:
            return cached[1]
        state = self._build_state()
        self._cache = (now, state)
        return state

    def _invalidate(self) -> None:
        self._cache = None

    def _build_state(self) -> dict:
        cfg = configmod.load()
        cf_token = keychain.load_secret("cloudflare")
        gh_token = keychain.load_secret("github")
        pd_token = keychain.load_secret("paddle")

        # Discovery uses the collector's cache. Without a token there is nothing
        # to enumerate under it (the manual add-* lists aren't offered here — the
        # web admin is the global-token/checklist surface).
        cf_discovered = self._collector._list_zones(cf_token) if cf_token else []
        gh_discovered = self._collector._list_repos(gh_token) if gh_token else []
        pd_discovered = self._collector._list_products(pd_token) if pd_token else []

        return {
            "sources": {
                "cloudflare": {
                    "connected": bool(cf_token),
                    "discovered": cf_discovered,  # [{id, name}]
                    "shown": cfg.cloudflare_shown,
                },
                "github": {
                    "connected": bool(gh_token),
                    "discovered": gh_discovered,  # ["owner/repo"]
                    "shown": cfg.github_shown,
                },
                "paddle": {
                    "connected": bool(pd_token),
                    "discovered": pd_discovered,  # ["Product Name"]
                    "shown": cfg.paddle_shown,
                },
            },
            "anthropic": {"accounts": keychain.list_accounts()},
            "settings": {
                "brightness": cfg.settings.brightness,
                "refresh": cfg.settings.refresh,
                "usage_threshold": cfg.settings.usage_threshold,
                "alert_down": cfg.settings.alert_down,
                "alert_4xx": cfg.settings.alert_4xx,
            },
        }

    # -- writes ------------------------------------------------------------

    def save_token(self, payload: dict) -> dict:
        """POST /api/token — {service, token}. An empty/whitespace token (or an
        explicit delete flag) removes the secret. Never logs the token value."""
        service = payload.get("service")
        if service not in _TOKEN_SERVICES:
            raise _BadRequest(f"unknown service '{service}'")
        token = payload.get("token")
        delete = bool(payload.get("delete")) or not (isinstance(token, str) and token.strip())
        if delete:
            keychain.delete_secret(service)
            log.info("admin: cleared %s token", service)
            self._invalidate()
            return {"service": service, "connected": False}
        keychain.save_secret(service, token.strip())
        log.info("admin: stored %s token", service)  # value intentionally not logged
        self._invalidate()
        return {"service": service, "connected": True}

    def save_config(self, payload: dict) -> dict:
        """POST /api/config. Applies the tri-state selection per service (absent
        key = leave as-is; explicit null = show all; [] = none; list = subset)
        and clamps the settings. Persists via config.save."""
        if not isinstance(payload, dict):
            raise _BadRequest("body must be a JSON object")
        cfg = configmod.load()

        for service in _TOKEN_SERVICES:
            key = f"{service}_shown"
            if key not in payload:
                continue  # leave the current selection untouched
            cfg.set_shown(service, _coerce_shown(payload[key], key))

        settings_in = payload.get("settings")
        if settings_in is not None:
            if not isinstance(settings_in, dict):
                raise _BadRequest("settings must be an object")
            s = cfg.settings
            if "brightness" in settings_in:
                s.brightness = _clamp_int(settings_in["brightness"], _BRIGHTNESS_MIN, _BRIGHTNESS_MAX, "brightness")
            if "refresh" in settings_in:
                s.refresh = _clamp_int(settings_in["refresh"], _REFRESH_MIN, _REFRESH_MAX, "refresh")
            if "usage_threshold" in settings_in:
                s.usage_threshold = _clamp_int(settings_in["usage_threshold"], _THRESHOLD_MIN, _THRESHOLD_MAX, "usage_threshold")
            if "alert_down" in settings_in:
                s.alert_down = _coerce_bool(settings_in["alert_down"], "alert_down")
            if "alert_4xx" in settings_in:
                s.alert_4xx = _coerce_bool(settings_in["alert_4xx"], "alert_4xx")

        configmod.save(cfg)
        self._invalidate()
        return {"ok": True}


class _BadRequest(Exception):
    """A 400 — malformed/invalid request body, distinct from a 500."""


def _coerce_shown(value, key: str) -> list[str] | None:
    """Validate one `<service>_shown` value into the tri-state. null -> show all,
    a list -> that subset (stringified), anything else -> 400."""
    if value is None:
        return None
    if isinstance(value, list):
        return [str(x) for x in value]
    raise _BadRequest(f"{key} must be null or a list")


def _clamp_int(value, lo: int, hi: int, name: str) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise _BadRequest(f"{name} must be an integer") from None
    return max(lo, min(hi, n))


def _coerce_bool(value, name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise _BadRequest(f"{name} must be a boolean")


# ----------------------------------------------------------------- HTTP layer


def make_handler(state: AdminState):
    """Build a request handler class bound to `state`. A closure keeps the
    handler dependency-free (no globals) so tests can drive it with a stub."""

    page_bytes = _PAGE_PATH.read_bytes()

    class AdminHandler(BaseHTTPRequestHandler):
        server_version = "claudemon-admin"

        # Quiet the default per-request stderr line, and — crucially — never let
        # request bodies (which carry tokens on POST /api/token) reach the log.
        def log_message(self, fmt: str, *args) -> None:
            log.debug("%s - %s", self.address_string(), fmt % args)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send_bytes(200, "text/html; charset=utf-8", page_bytes)
            elif path == "/api/state":
                self._send_json(200, state.state())
            else:
                self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            handlers = {
                "/api/token": state.save_token,
                "/api/config": state.save_config,
            }
            fn = handlers.get(path)
            if fn is None:
                self._send_json(404, {"error": "not found"})
                return
            try:
                payload = self._read_json()
                result = fn(payload)
            except _BadRequest as e:
                self._send_json(400, {"error": str(e)})
            except keychain.KeychainError as e:
                # Don't echo Keychain internals verbatim, but surface the failure.
                log.warning("admin: keychain error on %s: %s", path, e)
                self._send_json(500, {"error": "keychain write failed"})
            except Exception as e:  # noqa: BLE001 — last-resort guard for a single-user tool
                log.warning("admin: error on %s: %s", path, e)
                self._send_json(500, {"error": "internal error"})
            else:
                self._send_json(200, result)

        # -- helpers -------------------------------------------------------

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            if length > _MAX_BODY_BYTES:
                raise _BadRequest("request body too large")
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                raise _BadRequest("body is not valid JSON") from None
            if not isinstance(data, dict):
                raise _BadRequest("body must be a JSON object")
            return data

        def _send_json(self, code: int, obj: dict) -> None:
            self._send_bytes(code, "application/json", json.dumps(obj).encode())

        def _send_bytes(self, code: int, content_type: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            # Loopback-only page; no external calls, but be explicit about no caching
            # so a config change is reflected on the next state poll.
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return AdminHandler


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Run the admin server until interrupted. Prints the reachable URL(s)."""
    state = AdminState()
    handler = make_handler(state)
    httpd = ThreadingHTTPServer((host, port), handler)

    shown_host = "localhost" if host in ("0.0.0.0", "") else host
    log.info("admin server bound to %s:%s", host, port)
    print(f"ClaudeMon admin on http://{shown_host}:{port}/")
    if host in ("0.0.0.0", ""):
        lan = _lan_ip()
        if lan:
            print(f"  reachable on the LAN at http://{lan}:{port}/")
        print("  (bound to 0.0.0.0 — reachable by any host on your network)")
    print("Press Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def _lan_ip() -> str | None:
    """Best-effort primary LAN IP (no packets actually sent — a UDP connect just
    picks the outbound interface). Returns None if it can't be determined."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
