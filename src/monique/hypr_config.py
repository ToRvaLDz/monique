"""Scrittura dei file di configurazione monitor di Hyprland.

Hyprland accetta due formati: quello legacy hyprlang (``monitors.conf``) e
quello Lua introdotto con la 0.55 (``monitors.lua``).  Quale dei due viene
generato dipende dall'impostazione ``hypr_config_format``.
"""

from __future__ import annotations

from pathlib import Path

from .models import Profile
from .utils import (
    HYPR_FORMAT_BOTH,
    HYPR_FORMAT_LEGACY,
    HYPR_FORMAT_LUA,
    backup_file,
    get_hypr_config_format,
    hyprland_config_dir,
    normalize_hypr_format,
    write_text,
)


def _resolve_format(fmt: str | None) -> str:
    """Return the effective format, reading the app settings when unset."""
    return get_hypr_config_format() if fmt is None else normalize_hypr_format(fmt)


def hyprland_config_paths(fmt: str | None = None) -> list[Path]:
    """Return the Hyprland monitor config files written for *fmt*."""
    fmt = _resolve_format(fmt)
    conf_dir = hyprland_config_dir()
    paths: list[Path] = []
    if fmt in (HYPR_FORMAT_LEGACY, HYPR_FORMAT_BOTH):
        paths.append(conf_dir / "monitors.conf")
    if fmt in (HYPR_FORMAT_LUA, HYPR_FORMAT_BOTH):
        paths.append(conf_dir / "monitors.lua")
    return paths


def write_hyprland_configs(
    profile: Profile,
    *,
    fmt: str | None = None,
    use_description: bool = False,
    use_v2: bool = False,
    supports_icc: bool = False,
) -> list[Path]:
    """Back up and write the Hyprland monitor configs, returning the paths written."""
    fmt = _resolve_format(fmt)
    conf_dir = hyprland_config_dir()
    written: list[Path] = []

    if fmt in (HYPR_FORMAT_LEGACY, HYPR_FORMAT_BOTH):
        monitors_conf = conf_dir / "monitors.conf"
        backup_file(monitors_conf)
        write_text(monitors_conf, profile.generate_config(
            use_description=use_description,
            use_v2=use_v2,
            supports_icc=supports_icc,
        ))
        written.append(monitors_conf)

    if fmt in (HYPR_FORMAT_LUA, HYPR_FORMAT_BOTH):
        monitors_lua = conf_dir / "monitors.lua"
        backup_file(monitors_lua)
        write_text(monitors_lua, profile.generate_lua_config(
            use_description=use_description,
        ))
        written.append(monitors_lua)

    return written
