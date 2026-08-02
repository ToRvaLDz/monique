"""Percorsi dei file di configurazione monitor scritti da ``apply_profile()``.

Ogni client IPC scrive il config del proprio compositore e, se gli altri
compositori sono installati, ne scrive anche i config (cross-write).  La GUI
ha bisogno di conoscere quei percorsi *prima* di applicare, per poterne fare
il backup e ripristinarli durante il revert: questo modulo è l'unica fonte di
verità, così i due elenchi non possono divergere.
"""

from __future__ import annotations

from pathlib import Path

from .hypr_config import hyprland_config_paths
from .utils import (
    get_monitor_config_name,
    is_hyprland_installed,
    is_niri_installed,
    is_sway_installed,
    niri_config_dir,
    sway_config_dir,
)


HYPRLAND = "hyprland"
SWAY = "sway"
NIRI = "niri"


def sway_monitors_path() -> Path:
    """Return the Sway monitor config file."""
    return sway_config_dir() / f"{get_monitor_config_name()}.conf"


def niri_monitors_path() -> Path:
    """Return the Niri monitor config file."""
    return niri_config_dir() / f"{get_monitor_config_name()}.kdl"


def compositor_config_paths(
    primary: str, *, hypr_config_format: str | None = None,
) -> list[Path]:
    """Return the monitor config files ``apply_profile()`` writes for *primary*.

    The primary compositor's own config comes first, followed by the configs
    cross-written for any other installed compositor.  Privileged files (the
    SDDM Xsetup script and the greetd config) are excluded: they are written
    through ``pkexec`` and are neither backed up nor reverted.

    Paths are de-duplicated because a custom ``--config-dir`` makes every
    compositor share one directory, where Hyprland and Sway both want
    ``monitors.conf``.
    """
    if primary not in (HYPRLAND, SWAY, NIRI):
        raise ValueError(f"Unknown compositor: {primary!r}")

    paths: list[Path] = []

    if primary == HYPRLAND:
        paths.extend(hyprland_config_paths(hypr_config_format))
    elif primary == SWAY:
        paths.append(sway_monitors_path())
    else:
        paths.append(niri_monitors_path())

    # Cross-write targets, mirroring the is_*_installed() checks in apply_profile()
    if primary != HYPRLAND and is_hyprland_installed():
        paths.extend(hyprland_config_paths(hypr_config_format))
    if primary != SWAY and is_sway_installed():
        paths.append(sway_monitors_path())
    if primary != NIRI and is_niri_installed():
        paths.append(niri_monitors_path())

    return list(dict.fromkeys(paths))
