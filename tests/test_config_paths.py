"""The config files apply_profile() writes must be exactly the ones it declares.

The GUI backs up config_paths() before applying and restores them on revert.
When the two lists drift apart the revert silently does nothing, which is how
the Sway revert stayed broken: the window assumed the Hyprland paths.
"""

import itertools

import pytest

from monique import utils
from monique.config_paths import (
    HYPRLAND,
    NIRI,
    SWAY,
    UMBRIEL,
    compositor_config_paths,
    niri_monitors_path,
    sway_monitors_path,
    umbriel_monitors_path,
    umbriel_user_config_path,
)
from monique.hyprland import HyprlandIPC
from monique.kanshi_config import kanshi_monitors_path
from monique.niri import NiriIPC
from monique.sway import SwayIPC
from monique.umbriel import UmbrielIPC


IPC_FOR = {HYPRLAND: HyprlandIPC, SWAY: SwayIPC, NIRI: NiriIPC, UMBRIEL: UmbrielIPC}
COMPOSITORS = [HYPRLAND, SWAY, NIRI, UMBRIEL]

# config.kdl and config.toml are the user's own Niri and Umbriel configs,
# patched once with an include. Monique does not generate them.
NOT_GENERATED = {"config.kdl", "config.toml"}


def _set_installed(monkeypatch, primary, *, hyprland, sway, niri, umbriel=False):
    """Fake which compositors are installed, wherever the check is imported."""
    flags = {"hyprland": hyprland, "sway": sway, "niri": niri, "umbriel": umbriel}
    for module in ("monique.config_paths", f"monique.{primary}"):
        for name, value in flags.items():
            target = f"is_{name}_installed"
            mod = __import__(module, fromlist=[target])
            if hasattr(mod, target):
                monkeypatch.setattr(f"{module}.{target}", lambda v=value: v)


def _neutralise_side_effects(monkeypatch, primary):
    """Stub out the socket reload and the privileged pkexec writes."""
    for name in ("is_sddm_running", "is_greetd_running"):
        monkeypatch.setattr(f"monique.{primary}.{name}", lambda: False)
    monkeypatch.setattr(IPC_FOR[primary], "reload", lambda self: None)
    if primary == HYPRLAND:
        monkeypatch.setattr(HyprlandIPC, "get_version", lambda self: (0, 55, 0))


def _files_on_disk(root):
    return {
        p
        for sub in ("hypr", "sway", "niri", "umbriel", "kanshi")
        if (root / sub).is_dir()
        for p in (root / sub).iterdir()
        if p.name not in NOT_GENERATED and p.suffix != ".bak"
    }


def _installation_matrix(primary):
    """Every combination of installed compositors; the active one is present."""
    for hyprland, sway, niri, umbriel in itertools.product([True, False], repeat=4):
        installed = {HYPRLAND: hyprland, SWAY: sway, NIRI: niri, UMBRIEL: umbriel}
        if not installed[primary]:
            continue
        yield hyprland, sway, niri, umbriel


@pytest.mark.parametrize("primary", COMPOSITORS)
@pytest.mark.parametrize("fmt", ["both", "legacy", "lua"])
@pytest.mark.parametrize("kanshi", [True, False])
def test_declared_paths_are_exactly_the_files_written(
    isolated_config, monkeypatch, profile, primary, fmt, kanshi,
):
    utils.save_app_settings({"kanshi_config": kanshi})
    for hyprland, sway, niri, umbriel in _installation_matrix(primary):
        _set_installed(
            monkeypatch, primary,
            hyprland=hyprland, sway=sway, niri=niri, umbriel=umbriel,
        )
        _neutralise_side_effects(monkeypatch, primary)

        for existing in _files_on_disk(isolated_config):
            existing.unlink()
        if primary == UMBRIEL:
            # config.toml e' dell'utente: apply_profile() non lo crea da zero
            umbriel_user_config_path().parent.mkdir(exist_ok=True)
            umbriel_user_config_path().write_text("[general]\n", encoding="utf-8")

        ipc = IPC_FOR[primary]()
        # config.toml e' dichiarato (per il revert) ma e' dell'utente: non generato
        declared = {
            p for p in ipc.config_paths(hypr_config_format=fmt)
            if p.name not in NOT_GENERATED
        }
        ipc.apply_profile(profile, hypr_config_format=fmt, use_description=False)

        assert declared == _files_on_disk(isolated_config), (
            f"{primary} hyprland={hyprland} sway={sway} niri={niri} umbriel={umbriel} "
            f"fmt={fmt} kanshi={kanshi}"
        )


@pytest.mark.parametrize("primary,expected", [
    (SWAY, "monitors.conf"),
    (NIRI, "monitors.kdl"),
    (UMBRIEL, "monitors.toml"),
])
def test_primary_compositor_config_comes_first(monkeypatch, primary, expected):
    _set_installed(monkeypatch, primary, hyprland=True, sway=True, niri=True, umbriel=True)

    assert compositor_config_paths(primary)[0].name == expected


def test_cross_writes_are_included(monkeypatch):
    _set_installed(monkeypatch, SWAY, hyprland=True, sway=True, niri=True, umbriel=True)

    paths = compositor_config_paths(SWAY, hypr_config_format="lua")

    assert sway_monitors_path() in paths
    assert niri_monitors_path() in paths
    assert umbriel_monitors_path() in paths
    assert any(p.name == "monitors.lua" for p in paths)
    assert not any(p.name == "monitors.conf" and "hypr" in p.parts for p in paths)


@pytest.mark.parametrize("primary", COMPOSITORS)
def test_kanshi_file_is_declared_only_when_enabled(monkeypatch, primary):
    _set_installed(monkeypatch, primary, hyprland=True, sway=True, niri=True, umbriel=True)

    assert kanshi_monitors_path() not in compositor_config_paths(primary)

    utils.save_app_settings({"kanshi_config": True})
    paths = compositor_config_paths(primary)

    assert kanshi_monitors_path() in paths
    assert paths[-1] == kanshi_monitors_path()


@pytest.mark.parametrize("primary", COMPOSITORS)
def test_umbriel_config_toml_is_declared_for_umbriel_as_primary_only(
    monkeypatch, primary,
):
    """The include edit in config.toml must be revertable, but only where
    Umbriel's apply_profile() is the one making it."""
    _set_installed(monkeypatch, primary, hyprland=True, sway=True, niri=True, umbriel=True)

    declared = umbriel_user_config_path() in compositor_config_paths(primary)

    assert declared is (primary == UMBRIEL)


def test_absent_compositors_are_not_declared(monkeypatch):
    _set_installed(monkeypatch, SWAY, hyprland=False, sway=True, niri=False)

    assert compositor_config_paths(SWAY) == [sway_monitors_path()]


def test_shared_config_dir_yields_no_duplicates(monkeypatch):
    """--config-dir makes Hyprland and Sway share one monitors.conf."""
    _set_installed(monkeypatch, SWAY, hyprland=True, sway=True, niri=True)
    monkeypatch.setattr(utils, "_runtime_config_dir", "/tmp/monique-shared")

    paths = compositor_config_paths(SWAY, hypr_config_format="legacy")

    assert len(paths) == len(set(paths))


def test_unknown_compositor_is_rejected():
    with pytest.raises(ValueError, match="wayfire"):
        compositor_config_paths("wayfire")
