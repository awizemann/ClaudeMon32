"""Cockpit config store: the user's source *selection* + device settings.

Non-secret — lives at ~/.claudemon/config.json (mode 0700 dir, reused from the
Keychain module). Tokens NEVER land here; they stay in the Keychain (set via
`claudemon set-token`). This file only records which discovered zones/repos/
products the user chose to show, and the device/alert settings. Shape:

    {
      "sources": {
        "cloudflare": {"shown": ["<zone id>", ...]},
        "github":     {"shown": ["owner/repo", ...]},
        "paddle":     {"shown": ["<product name>", ...]}
      },
      "settings": {
        "brightness": 100, "refresh": 60, "usage_threshold": 80,
        "alert_down": true, "alert_4xx": true
      }
    }

Selection semantics for `shown` (see resolve_shown): an ABSENT `shown` key means
"never configured — show everything discovered" (capped to the cockpit limits);
an explicit empty list `[]` means "show none"; an explicit list is that subset,
in the user's order, filtered to what the token can actually see.

A missing/empty file just means "nothing configured yet": no explicit selection
(so discovery shows all) and the default settings below.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from .keychain import CONFIG_DIR

CONFIG_FILE = CONFIG_DIR / "config.json"

# The three services whose items are discovered under a global token. Anthropic
# stays per-account OAuth and is deliberately NOT part of this selection model.
_SERVICES = ("cloudflare", "github", "paddle")


@dataclass
class Settings:
    """Device + alert settings. Defaults match render.py's shipping values."""

    brightness: int = 100        # 0-100 backlight
    refresh: int = 60            # daemon poll/push interval, seconds
    usage_threshold: int = 80    # 5h-usage % that raises a WARNING alert
    alert_down: bool = True      # raise CRITICAL when a shown site is down
    alert_4xx: bool = True       # raise WARNING when a shown site is degraded


@dataclass
class Config:
    """Parsed config. `shown` is None for a service that was never configured
    (=> show all discovered), or an explicit list (possibly empty => show none).

    Keeping the tri-state as `list | None` is what lets resolve_shown tell
    "never picked" (show all) apart from "picked nothing" ([])."""

    cloudflare_shown: list[str] | None = None
    github_shown: list[str] | None = None
    paddle_shown: list[str] | None = None
    settings: Settings = field(default_factory=Settings)

    def shown_for(self, service: str) -> list[str] | None:
        return {
            "cloudflare": self.cloudflare_shown,
            "github": self.github_shown,
            "paddle": self.paddle_shown,
        }[service]

    def set_shown(self, service: str, shown: list[str] | None) -> None:
        if service == "cloudflare":
            self.cloudflare_shown = shown
        elif service == "github":
            self.github_shown = shown
        elif service == "paddle":
            self.paddle_shown = shown
        else:
            raise ValueError(f"unknown service '{service}'")


def load() -> Config:
    """Load the config, or a default Config when the file is missing. An
    unreadable/corrupt file is an error (silently defaulting would wipe the
    user's selection)."""
    if not CONFIG_FILE.exists():
        return Config()
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"{CONFIG_FILE} is unreadable ({e}); fix or delete it") from e

    sources = data.get("sources") or {}

    def shown(service: str) -> list[str] | None:
        node = sources.get(service)
        if not isinstance(node, dict) or "shown" not in node:
            return None  # never configured -> show all discovered
        raw = node.get("shown")
        if not isinstance(raw, list):
            return None
        return [str(x) for x in raw]

    defaults = Settings()
    s = data.get("settings") or {}
    settings = Settings(
        brightness=_as_int(s.get("brightness"), defaults.brightness),
        refresh=_as_int(s.get("refresh"), defaults.refresh),
        usage_threshold=_as_int(s.get("usage_threshold"), defaults.usage_threshold),
        alert_down=_as_bool(s.get("alert_down"), defaults.alert_down),
        alert_4xx=_as_bool(s.get("alert_4xx"), defaults.alert_4xx),
    )
    return Config(
        cloudflare_shown=shown("cloudflare"),
        github_shown=shown("github"),
        paddle_shown=shown("paddle"),
        settings=settings,
    )


def save(config: Config) -> None:
    """Persist the config as JSON. Only a service with an explicit selection
    writes a `shown` key — a None (never configured) service is omitted so it
    keeps resolving to "show all" on the next load."""
    CONFIG_DIR.mkdir(mode=0o700, exist_ok=True)
    sources: dict[str, dict] = {}
    for service in _SERVICES:
        shown = config.shown_for(service)
        if shown is not None:
            sources[service] = {"shown": list(shown)}
    data = {"sources": sources, "settings": asdict(config.settings)}
    CONFIG_FILE.write_text(json.dumps(data, indent=2) + "\n")


def resolve_shown(
    discovered: list[str], shown: list[str] | None, cap: int
) -> list[str]:
    """Resolve which discovered items to display, applying the selection
    semantics and the cockpit cap.

    - `shown is None` (never configured): show ALL discovered, in discovery
      order, truncated to `cap`.
    - `shown == []`: show NONE.
    - explicit list: keep the user's chosen items in the user's order, filtered
      to those actually discovered (a stale pick that vanished is dropped), then
      truncated to `cap`.
    """
    if shown is None:
        return discovered[:cap]
    seen = set(discovered)
    picked = [item for item in shown if item in seen]
    return picked[:cap]


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_bool(value: object, default: bool) -> bool:
    return value if isinstance(value, bool) else default
