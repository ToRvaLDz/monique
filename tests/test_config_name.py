"""Tests for the configurable monitor config filename (issue #40).

A single ``monitor_config_name`` setting drives the base name of the files
written for every compositor; each backend appends its own extension
(``.kdl`` / ``.conf`` / ``.lua``).  The default reproduces the historical
``monitors.*`` names so existing setups keep working untouched.

These modules import no ``gi``, matching the rest of the suite.
"""

from __future__ import annotations

import pytest

from monique import config_paths, hypr_config, niri
from monique.utils import (
    DEFAULT_MONITOR_CONFIG_NAME,
    get_monitor_config_name,
    hyprland_config_dir,
    niri_config_dir,
    sanitize_monitor_config_name,
    save_app_settings,
)


# ── sanitize_monitor_config_name ─────────────────────────────────────────

@pytest.mark.parametrize("value", ["", "   ", None, 123, "/abs/path", "..", "a/../b"])
def test_sanitize_rejects_invalid(value: object) -> None:
    """Empty, non-string, absolute, and traversal inputs fall back to default."""
    assert sanitize_monitor_config_name(value) == DEFAULT_MONITOR_CONFIG_NAME


def test_sanitize_plain_name() -> None:
    assert sanitize_monitor_config_name("display") == "display"


def test_sanitize_preserves_subdirectory() -> None:
    assert sanitize_monitor_config_name("cfg/display") == "cfg/display"


def test_sanitize_strips_typed_extension() -> None:
    """A known extension typed by mistake must not be doubled on write."""
    assert sanitize_monitor_config_name("display.kdl") == "display"
    assert sanitize_monitor_config_name("cfg/display.CONF") == "cfg/display"
    assert sanitize_monitor_config_name("display.lua") == "display"


def test_sanitize_normalizes_backslashes_and_dot_segments() -> None:
    assert sanitize_monitor_config_name("cfg\\display") == "cfg/display"
    assert sanitize_monitor_config_name("./cfg//display") == "cfg/display"


# ── get_monitor_config_name (reads settings) ─────────────────────────────

def test_get_defaults_when_unset() -> None:
    assert get_monitor_config_name() == DEFAULT_MONITOR_CONFIG_NAME


def test_get_reads_and_sanitizes_setting() -> None:
    save_app_settings({"monitor_config_name": "cfg/display.kdl"})
    assert get_monitor_config_name() == "cfg/display"


# ── propagation into the config path source of truth ─────────────────────

def test_default_paths_match_historical_names() -> None:
    """Back-compat: unset setting reproduces the old filenames exactly."""
    assert config_paths.niri_monitors_path().name == "monitors.kdl"
    assert config_paths.sway_monitors_path().name == "monitors.conf"
    assert [p.name for p in hypr_config.hyprland_config_paths("both")] == [
        "monitors.conf", "monitors.lua",
    ]


def test_custom_name_propagates_to_all_backends() -> None:
    save_app_settings({"monitor_config_name": "display"})

    assert config_paths.niri_monitors_path() == niri_config_dir() / "display.kdl"
    assert config_paths.sway_monitors_path().name == "display.conf"
    assert [p.name for p in hypr_config.hyprland_config_paths("both")] == [
        "display.conf", "display.lua",
    ]


def test_custom_subdirectory_propagates() -> None:
    save_app_settings({"monitor_config_name": "cfg/display"})

    niri_path = config_paths.niri_monitors_path()
    assert niri_path == niri_config_dir() / "cfg" / "display.kdl"
    assert config_paths.sway_monitors_path() == \
        config_paths.sway_config_dir() / "cfg" / "display.conf"
    assert hypr_config.hyprland_config_paths("lua")[0] == \
        hyprland_config_dir() / "cfg" / "display.lua"


# ── Niri include line stays in sync with the configured name ─────────────

def test_niri_include_uses_configured_name() -> None:
    save_app_settings({"monitor_config_name": "cfg/display"})
    conf_dir = niri_config_dir()
    conf_dir.mkdir(parents=True, exist_ok=True)
    (conf_dir / "config.kdl").write_text("// user config\n", encoding="utf-8")

    changed = niri._ensure_niri_config_include()

    assert changed is True
    text = (conf_dir / "config.kdl").read_text(encoding="utf-8")
    assert 'include "cfg/display.kdl"' in text
    assert "monitors.kdl" not in text


def test_niri_include_detected_when_already_present() -> None:
    save_app_settings({"monitor_config_name": "display"})
    conf_dir = niri_config_dir()
    conf_dir.mkdir(parents=True, exist_ok=True)
    # A user-authored include of the current file (no Monique marker).
    (conf_dir / "config.kdl").write_text(
        'include "display.kdl"\n', encoding="utf-8"
    )

    # Already includes the configured file: no rewrite.
    assert niri._ensure_niri_config_include() is False


def test_niri_include_noop_when_marker_already_current() -> None:
    save_app_settings({"monitor_config_name": "display"})
    conf_dir = niri_config_dir()
    conf_dir.mkdir(parents=True, exist_ok=True)
    (conf_dir / "config.kdl").write_text(
        '// Monique monitor configuration\ninclude "display.kdl"\n',
        encoding="utf-8",
    )

    assert niri._ensure_niri_config_include() is False


def test_niri_include_swaps_stale_name_on_rename() -> None:
    """Renaming the config file removes the stale Monique include, not the user's."""
    conf_dir = niri_config_dir()
    conf_dir.mkdir(parents=True, exist_ok=True)
    (conf_dir / "config.kdl").write_text(
        'include "keep-me.kdl"\n'
        '\n// Monique monitor configuration\ninclude "monitors.kdl"\n',
        encoding="utf-8",
    )

    save_app_settings({"monitor_config_name": "cfg/display"})
    changed = niri._ensure_niri_config_include()

    text = (conf_dir / "config.kdl").read_text(encoding="utf-8")
    assert changed is True
    # New name in, stale name out.
    assert 'include "cfg/display.kdl"' in text
    assert "monitors.kdl" not in text
    # User's unrelated include is preserved.
    assert 'include "keep-me.kdl"' in text
    # Exactly one Monique marker remains.
    assert text.count("// Monique monitor configuration") == 1


def test_niri_include_rename_keeps_user_output_blocks() -> None:
    """On a rename (not first run), user-added output blocks must survive."""
    conf_dir = niri_config_dir()
    conf_dir.mkdir(parents=True, exist_ok=True)
    (conf_dir / "config.kdl").write_text(
        'output "DP-1" {\n    scale 2\n}\n'
        '\n// Monique monitor configuration\ninclude "monitors.kdl"\n',
        encoding="utf-8",
    )

    save_app_settings({"monitor_config_name": "display"})
    changed = niri._ensure_niri_config_include()

    text = (conf_dir / "config.kdl").read_text(encoding="utf-8")
    assert changed is True
    assert 'output "DP-1"' in text  # not stripped on rename
    assert 'include "display.kdl"' in text
    assert "monitors.kdl" not in text


def test_niri_include_strips_output_blocks_on_first_run() -> None:
    """True first run (no prior Monique include) still strips output blocks."""
    save_app_settings({"monitor_config_name": "display"})
    conf_dir = niri_config_dir()
    conf_dir.mkdir(parents=True, exist_ok=True)
    (conf_dir / "config.kdl").write_text(
        'output "DP-1" {\n    scale 2\n}\n\ninput {\n    keyboard {}\n}\n',
        encoding="utf-8",
    )

    changed = niri._ensure_niri_config_include()

    text = (conf_dir / "config.kdl").read_text(encoding="utf-8")
    assert changed is True
    assert 'output "DP-1"' not in text  # stripped on first run
    assert "input {" in text  # unrelated block kept
    assert 'include "display.kdl"' in text
