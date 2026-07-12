"""Tests for the cockpit config store: load/save round-trip, defaults, missing
file, and the shown-selection resolution semantics (absent=all, []=none,
explicit subset), plus the cockpit cap."""

from __future__ import annotations

import json

import pytest

from claudemon import config as configmod


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    """Redirect the config path to a temp file so tests never touch ~/.claudemon."""
    path = tmp_path / "config.json"
    monkeypatch.setattr(configmod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(configmod, "CONFIG_FILE", path)
    return path


class TestLoadSave:
    def test_missing_file_gives_defaults(self, config_file):
        cfg = configmod.load()
        # No selection configured -> None (=> show all) for every service.
        assert cfg.cloudflare_shown is None
        assert cfg.github_shown is None
        assert cfg.paddle_shown is None
        # Settings default to the shipping values.
        assert cfg.settings.brightness == 100
        assert cfg.settings.refresh == 60
        assert cfg.settings.usage_threshold == 80
        assert cfg.settings.alert_down is True
        assert cfg.settings.alert_4xx is True

    def test_round_trip(self, config_file):
        cfg = configmod.Config()
        cfg.cloudflare_shown = ["zone-a", "zone-b"]
        cfg.github_shown = []  # explicit "show none"
        cfg.paddle_shown = None  # never configured
        cfg.settings.brightness = 40
        cfg.settings.usage_threshold = 90
        cfg.settings.alert_4xx = False
        configmod.save(cfg)

        loaded = configmod.load()
        assert loaded.cloudflare_shown == ["zone-a", "zone-b"]
        assert loaded.github_shown == []
        assert loaded.paddle_shown is None
        assert loaded.settings.brightness == 40
        assert loaded.settings.usage_threshold == 90
        assert loaded.settings.alert_4xx is False

    def test_empty_list_survives_round_trip_distinct_from_absent(self, config_file):
        # The tri-state must survive to disk: [] persists a `shown` key, None omits it.
        cfg = configmod.Config(github_shown=[], cloudflare_shown=None)
        configmod.save(cfg)
        raw = json.loads(config_file.read_text())
        assert raw["sources"]["github"] == {"shown": []}
        assert "cloudflare" not in raw["sources"]
        loaded = configmod.load()
        assert loaded.github_shown == []
        assert loaded.cloudflare_shown is None

    def test_no_secrets_in_config(self, config_file):
        cfg = configmod.Config(cloudflare_shown=["z1"])
        configmod.save(cfg)
        text = config_file.read_text().lower()
        assert "token" not in text
        assert "secret" not in text

    def test_corrupt_file_raises(self, config_file):
        config_file.write_text("{not json")
        with pytest.raises(ValueError):
            configmod.load()

    def test_settings_fall_back_on_bad_types(self, config_file):
        config_file.write_text(json.dumps({
            "settings": {"brightness": "loud", "alert_down": "yes"}
        }))
        cfg = configmod.load()
        assert cfg.settings.brightness == 100   # bad int -> default
        assert cfg.settings.alert_down is True  # non-bool -> default

    def test_accessors(self):
        cfg = configmod.Config()
        cfg.set_shown("cloudflare", ["z1"])
        cfg.set_shown("github", [])
        assert cfg.shown_for("cloudflare") == ["z1"]
        assert cfg.shown_for("github") == []
        assert cfg.shown_for("paddle") is None
        with pytest.raises(ValueError):
            cfg.set_shown("bogus", [])


class TestResolveShown:
    DISCOVERED = ["a", "b", "c", "d"]

    def test_absent_shows_all(self):
        assert configmod.resolve_shown(self.DISCOVERED, None, 10) == ["a", "b", "c", "d"]

    def test_empty_shows_none(self):
        assert configmod.resolve_shown(self.DISCOVERED, [], 10) == []

    def test_explicit_subset_in_user_order(self):
        assert configmod.resolve_shown(self.DISCOVERED, ["c", "a"], 10) == ["c", "a"]

    def test_stale_pick_is_dropped(self):
        # "z" was selected but no longer discovered -> silently dropped.
        assert configmod.resolve_shown(self.DISCOVERED, ["b", "z"], 10) == ["b"]

    def test_absent_respects_cap(self):
        assert configmod.resolve_shown(self.DISCOVERED, None, 2) == ["a", "b"]

    def test_explicit_respects_cap(self):
        assert configmod.resolve_shown(self.DISCOVERED, ["d", "c", "b"], 2) == ["d", "c"]

    def test_empty_discovered_is_empty(self):
        assert configmod.resolve_shown([], None, 10) == []
        assert configmod.resolve_shown([], ["a"], 10) == []
