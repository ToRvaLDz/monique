"""Generazione e lettura della config monitor di Umbriel (monitors.toml)."""

import copy
import json
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from monique.models import (
    MonitorConfig,
    PositionMode,
    Profile,
    ResolutionMode,
    ScaleMode,
    Transform,
    VRR,
)
from monique.umbriel_config import (
    generate_umbriel_config,
    monitor_from_umbriel_output,
    read_output_settings,
    restore_config_settings,
    umbriel_ids,
    write_umbriel_config,
)

FIXTURE = Path(__file__).parent / "fixtures" / "umbriel_outputs.json"


def _outputs() -> list[dict]:
    """Output reali catturati da un Umbriel headless (`outputs --json`)."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _identified(**changes) -> dict:
    """Il secondo output reale, con l'identita' che il backend headless non ha."""
    out = copy.deepcopy(_outputs()[1])
    out.update(make="AOC", model="2757", serial="1234",
               config_name="PNP(AOC) 2757 1234")
    out.update(changes)
    return out


def _tables(text: str) -> dict:
    return tomllib.loads(text)["output"]


def _mon(**kw) -> MonitorConfig:
    base = dict(name="DP-1", description="AOC 2757 1234", make="AOC",
                model="2757", serial="1234", width=2560, height=1440,
                refresh_rate=144.0, x=0, y=0, scale=1.0,
                position_mode=PositionMode.EXPLICIT)
    base.update(kw)
    return MonitorConfig(**base)


def _gen(*monitors, use_description=False, ids=None) -> str:
    profile = Profile(name="p", monitors=list(monitors))
    return generate_umbriel_config(profile, use_description, ids)


# ── output JSON -> MonitorConfig ─────────────────────────────────────────

def test_real_output_is_read_field_by_field():
    mon = monitor_from_umbriel_output(_outputs()[1])

    assert mon.name == "V2"
    assert (mon.width, mon.height, mon.refresh_rate) == (800, 600, 30.0)
    assert (mon.x, mon.y) == (1280, 0)
    assert mon.scale == 1.0
    assert mon.transform == Transform.NORMAL
    assert mon.enabled is True
    assert mon.position_mode == PositionMode.EXPLICIT
    assert mon.description == ""
    assert mon.available_modes == ["800x600@30.000Hz"]


def test_identity_becomes_the_normalised_description():
    mon = monitor_from_umbriel_output(_identified())

    assert (mon.make, mon.model, mon.serial) == ("AOC", "2757", "1234")
    assert mon.description == "AOC 2757 1234"


def test_pnp_wrapped_make_matches_other_compositors():
    mon = monitor_from_umbriel_output(_identified(make="PNP(AOC)", serial=""))

    assert mon.description == "AOC 2757"


@pytest.mark.parametrize("raw,expected", [
    ("normal", Transform.NORMAL), ("90", Transform.ROTATE_90),
    ("180", Transform.ROTATE_180), ("270", Transform.ROTATE_270),
    ("flipped", Transform.FLIPPED), ("flipped-90", Transform.FLIPPED_90),
    ("flipped-180", Transform.FLIPPED_180),
    ("flipped-270", Transform.FLIPPED_270),
])
def test_every_transform_is_read(raw, expected):
    assert monitor_from_umbriel_output(_identified(transform=raw)).transform == expected


def test_float32_scale_noise_is_rounded_away():
    mon = monitor_from_umbriel_output(_identified(scale=1.2000000476837158))

    assert mon.scale == 1.2


def test_adaptive_sync_maps_to_vrr():
    on = monitor_from_umbriel_output(_identified(adaptive_sync=True))
    null = monitor_from_umbriel_output(_identified(adaptive_sync=None))

    assert on.vrr == VRR.ON
    assert null.vrr == VRR.OFF


def test_disabled_output_keeps_position_and_scale():
    mon = monitor_from_umbriel_output(
        _identified(enabled=False, scale=2.0, position={"x": 10, "y": 20}))

    assert mon.enabled is False
    assert (mon.x, mon.y, mon.scale) == (10, 20, 2.0)
    assert mon.position_mode == PositionMode.AUTO


def test_missing_current_mode_falls_back_to_defaults():
    out = _identified(modes=[])
    mon = monitor_from_umbriel_output(out)

    assert (mon.width, mon.height, mon.refresh_rate) == (1920, 1080, 60.0)


def test_umbriel_ids_maps_description_to_config_name():
    ids = umbriel_ids([_identified(), _outputs()[0]])

    assert ids == {"AOC 2757 1234": "PNP(AOC) 2757 1234"}


# ── generator ────────────────────────────────────────────────────────────

def test_enabled_output_renders_every_managed_key():
    text = _gen(_mon(
        scale=1.5, transform=Transform.ROTATE_90, vrr=VRR.FULLSCREEN,
        bitdepth=10, color_management="hdr", focus_at_startup=True,
        x=100, y=-50, refresh_rate=143.912,
    ))

    assert _tables(text) == {"DP-1": {
        "enabled": True, "mode": "2560x1440@143.912", "position": [100, -50],
        "scale": 1.5, "transform": "90", "vrr": "fullscreen", "hdr": "on",
        "bit_depth": 10, "focus_at_startup": True,
    }}


def test_defaults_are_left_out():
    table = _tables(_gen(_mon()))["DP-1"]

    assert set(table) == {"enabled", "mode", "position", "scale"}


def test_disabled_output_renders_only_enabled_false():
    text = _gen(_mon(enabled=False, scale=2.0, vrr=VRR.ON))

    assert _tables(text) == {"DP-1": {"enabled": False}}


@pytest.mark.parametrize("vrr,policy", [(VRR.ON, "always"), (VRR.FULLSCREEN, "fullscreen")])
def test_vrr_policies(vrr, policy):
    assert _tables(_gen(_mon(vrr=vrr)))["DP-1"]["vrr"] == policy


@pytest.mark.parametrize("cm,hdr", [("hdr", "on"), ("hdredid", "on"),
                                    ("srgb", None), ("", None)])
def test_only_hdr_color_modes_map_to_hdr(cm, hdr):
    assert _tables(_gen(_mon(color_management=cm)))["DP-1"].get("hdr") == hdr


def test_non_explicit_modes_are_omitted():
    table = _tables(_gen(_mon(
        resolution_mode=ResolutionMode.PREFERRED,
        position_mode=PositionMode.AUTO, scale_mode=ScaleMode.AUTO,
    )))["DP-1"]

    assert table == {"enabled": True}


@pytest.mark.parametrize("scale,expected", [(8.0, 4.0), (0.1, 0.25)])
def test_scale_is_clamped_to_umbriel_range(scale, expected):
    assert _tables(_gen(_mon(scale=scale)))["DP-1"]["scale"] == expected


def test_scale_is_always_a_toml_float():
    assert isinstance(_tables(_gen(_mon(scale=1.0)))["DP-1"]["scale"], float)


def test_unknown_refresh_drops_the_rate():
    table = _tables(_gen(_mon(refresh_rate=0.0)))["DP-1"]

    assert table["mode"] == "2560x1440"


def test_hostile_names_round_trip_through_toml():
    nasty = 'Evil "name"\\\nnew\x7fline'
    text = _gen(_mon(name=nasty))

    assert list(_tables(text)) == ['Evil "name"\\ new line']


# ── selector ─────────────────────────────────────────────────────────────

def test_connector_is_used_without_use_description():
    assert list(_tables(_gen(_mon(), use_description=False))) == ["DP-1"]


def test_connected_monitor_uses_the_ipc_config_name():
    ids = {"AOC 2757 1234": "PNP(AOC) 2757 1234"}

    assert list(_tables(_gen(_mon(), use_description=True, ids=ids))) == [
        "PNP(AOC) 2757 1234"]


@pytest.mark.parametrize("ids", [None, {}, {"Other 1 2": "Other 1 2"}])
def test_unknown_to_ipc_is_rebuilt_offline(ids):
    # cross-write (nessun ids), monitor scollegato o IPC fallita
    text = _gen(_mon(), use_description=True, ids=ids)

    assert list(_tables(text)) == ["PNP(AOC) 2757 1234"]


def test_empty_serial_is_rebuilt_as_unknown():
    mon = _mon(description="Dell U2415", make="Dell", model="U2415", serial="")

    assert list(_tables(_gen(mon, use_description=True))) == ["Dell U2415 Unknown"]


def test_no_description_never_rebuilds_an_identity():
    mon = _mon(description="", make="", model="", serial="", name="V2")
    ids = {"AOC 2757 1234": "PNP(AOC) 2757 1234"}

    assert list(_tables(_gen(mon, use_description=True, ids=ids))) == ["V2"]


def test_description_without_make_falls_back_to_connector():
    mon = _mon(make="", model="", serial="")

    assert list(_tables(_gen(mon, use_description=True))) == ["DP-1"]


def test_twins_fall_back_to_connectors():
    a = _mon(name="DP-1")
    b = _mon(name="DP-2")

    assert list(_tables(_gen(a, b, use_description=True))) == ["DP-1", "DP-2"]


def test_unresolvable_duplicates_are_dropped_not_emitted():
    # due tabelle con la stessa chiave romperebbero l'intero file
    text = _gen(_mon(name="DP-1"), _mon(name="dp-1"))

    assert len(_tables(text)) == 1


# ── file e lettura delle impostazioni ────────────────────────────────────

def test_write_creates_file_and_backs_up_previous(isolated_config):
    profile = Profile(name="p", monitors=[_mon()])

    write_umbriel_config(profile, False)
    write_umbriel_config(profile, False)

    out = isolated_config / "umbriel"
    assert (out / "monitors.toml").is_file()
    assert (out / "monitors.toml.bak").is_file()


def test_read_output_settings_round_trips_the_generated_file():
    text = _gen(_mon(vrr=VRR.ON, bitdepth=10, focus_at_startup=True))

    settings = read_output_settings(text)

    assert settings["dp-1"]["vrr"] == "always"
    assert settings["dp-1"]["bit_depth"] == 10


def test_read_output_settings_survives_garbage():
    assert read_output_settings("[output\nnot toml") == {}


# ── integrazione con il vero parser di Umbriel ───────────────────────────

@pytest.mark.skipif(shutil.which("umbriel") is None,
                    reason="umbriel is not on PATH")
def test_generated_file_validates_with_real_umbriel(tmp_path):
    full = _mon(scale=1.25, transform=Transform.FLIPPED_270, vrr=VRR.FULLSCREEN,
                bitdepth=10, color_management="hdr", focus_at_startup=True,
                refresh_rate=143.912)
    off = _mon(name="DP-2", description="Dell U2415", make="Dell",
               model="U2415", serial="", enabled=False)
    text = _gen(full, off, use_description=True)
    path = tmp_path / "monitors.toml"
    path.write_text(text, encoding="utf-8")

    done = subprocess.run(
        ["umbriel", "config", "validate", "--json", "-c", str(path)],
        capture_output=True, text=True, timeout=30,
    )

    report = json.loads(done.stdout)
    assert report["valid"] is True, report["diagnostics"]
    assert done.returncode == 0


# ── impostazioni che l'IPC non riporta ───────────────────────────────────

def _restored(monitors) -> list[MonitorConfig]:
    """Round-trip: generate the file for *monitors*, then refill fresh copies."""
    text = _gen(*monitors, use_description=True)
    fresh = [monitor_from_umbriel_output(_identified(name=m.name)) for m in monitors]
    restore_config_settings(fresh, text)
    return fresh


def test_restore_refills_what_ipc_does_not_report():
    saved = _mon(vrr=VRR.FULLSCREEN, bitdepth=10, color_management="hdr",
                 focus_at_startup=True)

    fresh = _restored([saved])[0]

    assert fresh.vrr == VRR.FULLSCREEN
    assert fresh.bitdepth == 10
    assert fresh.color_management == "hdr"
    assert fresh.focus_at_startup is True


def test_restore_matches_by_identity_then_connector():
    text = (
        '[output."pnp(aoc) 2757 1234"]\nfocus_at_startup = true\n\n'
        '[output."DP-2"]\nbit_depth = 10\n'
    )
    by_identity = monitor_from_umbriel_output(_identified(name="DP-7"))
    by_port = monitor_from_umbriel_output(_outputs()[1])
    by_port.name = "DP-2"

    restore_config_settings([by_identity, by_port], text)

    assert by_identity.focus_at_startup is True
    assert by_port.bitdepth == 10
    assert by_port.focus_at_startup is False


def test_restore_keeps_live_values_the_file_does_not_mention():
    live = monitor_from_umbriel_output(_identified(adaptive_sync=True))

    restore_config_settings([live], '[output."PNP(AOC) 2757 1234"]\nscale = 1.0\n')

    assert live.vrr == VRR.ON
    assert live.bitdepth == 8


def test_restore_ignores_an_unreadable_file():
    live = monitor_from_umbriel_output(_identified())

    restore_config_settings([live], "[output\nbroken")

    assert live.focus_at_startup is False
