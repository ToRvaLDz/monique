"""Scrittura dei file di configurazione monitor di Hyprland.

Hyprland accetta due formati: quello legacy hyprlang (``monitors.conf``) e
quello Lua introdotto con la 0.55 (``monitors.lua``).  Quale dei due viene
generato dipende dall'impostazione ``hypr_config_format``.
"""

from __future__ import annotations

from pathlib import Path

from .models import (
    Profile,
    default_monitor_from_hyprland,
    default_monitor_from_hyprland_lua,
    icc_profiles_from_hyprland,
    icc_profiles_from_hyprland_lua,
)
from .utils import (
    HYPR_FORMAT_BOTH,
    HYPR_FORMAT_LEGACY,
    HYPR_FORMAT_LUA,
    backup_file,
    get_hypr_config_format,
    get_monitor_config_name,
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
    name = get_monitor_config_name()
    paths: list[Path] = []
    if fmt in (HYPR_FORMAT_LEGACY, HYPR_FORMAT_BOTH):
        paths.append(conf_dir / f"{name}.conf")
    if fmt in (HYPR_FORMAT_LUA, HYPR_FORMAT_BOTH):
        paths.append(conf_dir / f"{name}.lua")
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
    name = get_monitor_config_name()
    written: list[Path] = []

    if fmt in (HYPR_FORMAT_LEGACY, HYPR_FORMAT_BOTH):
        monitors_conf = conf_dir / f"{name}.conf"
        backup_file(monitors_conf)
        write_text(monitors_conf, profile.generate_config(
            use_description=use_description,
            use_v2=use_v2,
            supports_icc=supports_icc,
        ))
        written.append(monitors_conf)

    if fmt in (HYPR_FORMAT_LUA, HYPR_FORMAT_BOTH):
        monitors_lua = conf_dir / f"{name}.lua"
        backup_file(monitors_lua)
        write_text(monitors_lua, profile.generate_lua_config(
            use_description=use_description,
            supports_icc=supports_icc,
        ))
        written.append(monitors_lua)

    return written


def read_icc_profiles(fmt: str | None = None) -> dict[str, str]:
    """Return the ICC profiles found in the configs we generated.

    ``hyprctl monitors -j`` non riporta il profilo ICC di un monitor, quindi
    questi file sono l'unica fonte da cui recuperarlo quando ricarichiamo lo
    stato dal compositor.  Le chiavi sono gli identificatori di output usati
    nel file: il nome della porta oppure ``desc:DESCRIZIONE``.
    """
    profiles: dict[str, str] = {}

    for conf in hyprland_config_paths(fmt):
        if not conf.exists():
            continue
        parse = (
            icc_profiles_from_hyprland_lua
            if conf.suffix == ".lua"
            else icc_profiles_from_hyprland
        )
        profiles.update(parse(conf.read_text(encoding="utf-8")))

    return profiles


def read_default_monitor(fmt: str | None = None) -> str:
    """Return the identifier of the monitor focused at startup, empty when unset.

    Come per l'ICC, ``hyprctl`` non riporta ``cursor:default_monitor``: il config
    che generiamo è l'unica fonte per ricostruire il flag dopo un reload.
    """
    for conf in hyprland_config_paths(fmt):
        if not conf.exists():
            continue
        parse = (
            default_monitor_from_hyprland_lua
            if conf.suffix == ".lua"
            else default_monitor_from_hyprland
        )
        identifier = parse(conf.read_text(encoding="utf-8"))
        if identifier:
            return identifier

    return ""
