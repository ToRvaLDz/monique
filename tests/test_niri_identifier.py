"""Niri output identifiers in the generated KDL config.

A profile that turns a monitor off is applied precisely when that monitor is
gone, so it is absent from the ``niri_ids`` mapping, which is built from the
outputs Niri currently reports.  The block must still carry an identifier Niri
can match: the connector name stored in the profile is the part most likely to
have gone stale, since ports get reassigned across reboots and docking.

The expected strings below are not invented.  They are what `niri msg --json
outputs` reports for a real four-monitor setup, with the make/model/serial
triples taken from the matching saved profile:

    port       make                      model       serial         Niri spells it
    DP-2       LG Electronics            LG HDR 4K   0x00078A89     make model serial
    DP-3       PNP(AOC)                  2757        AXSD79A000536  make model serial
    HDMI-A-1   Samsung Electric Company  C27JG5x     HTOM500271     make model serial
    eDP-2      AU Optronics              0x328E      (none)         make model Unknown
"""

import pytest

from monique.models import MonitorConfig, Profile

# (make, model, serial, identifier Niri expects)
REAL_OUTPUTS = [
    ("LG Electronics", "LG HDR 4K", "0x00078A89",
     "LG Electronics LG HDR 4K 0x00078A89"),
    ("PNP(AOC)", "2757", "AXSD79A000536",
     "PNP(AOC) 2757 AXSD79A000536"),
    ("Samsung Electric Company", "C27JG5x", "HTOM500271",
     "Samsung Electric Company C27JG5x HTOM500271"),
    ("AU Optronics", "0x328E", "",
     "AU Optronics 0x328E Unknown"),
]


@pytest.mark.parametrize("make,model,serial,expected", REAL_OUTPUTS)
def test_rebuilt_identifier_matches_what_niri_reports(make, model, serial, expected):
    monitor = MonitorConfig(name="DP-9", description=f"{make} {model} {serial}".strip(),
                            make=make, model=model, serial=serial)

    assert monitor.niri_native_description() == expected


@pytest.mark.parametrize("make,model,serial,expected", REAL_OUTPUTS)
def test_disconnected_monitor_is_turned_off_by_description(make, model, serial, expected):
    """The mapping holds only connected outputs, so this one is missing."""
    monitor = MonitorConfig(name="DP-9", description=f"{make} {model} {serial}".strip(),
                            make=make, model=model, serial=serial, enabled=False)

    block = monitor.to_niri_block(use_description=True, niri_ids={"someone else": "x"})

    assert block == f'output "{expected}" {{\n    off\n}}'
    assert "DP-9" not in block


def test_bare_pnp_vendor_id_gets_wrapped():
    """Hyprland and Sway report "AOC" where Niri reports "PNP(AOC)"."""
    aoc = MonitorConfig(name="DP-3", description="AOC 2757 AXSD79A000536",
                        make="AOC", model="2757", serial="AXSD79A000536")

    assert aoc.niri_native_description() == "PNP(AOC) 2757 AXSD79A000536"


def test_serial_already_spelled_unknown_is_not_doubled():
    monitor = MonitorConfig(name="eDP-1", description="AU Optronics 0x328E",
                            make="AU Optronics", model="0x328E", serial="Unknown")

    assert monitor.niri_native_description() == "AU Optronics 0x328E Unknown"


def test_connected_monitor_keeps_the_identifier_niri_handed_over():
    """When Niri reports the output, its own string wins over the rebuilt one."""
    monitor = MonitorConfig(name="DP-4", description="AOC 2757 AXSD79A000536",
                            make="AOC", model="2757", serial="AXSD79A000536",
                            enabled=False)

    block = monitor.to_niri_block(
        use_description=True,
        niri_ids={"AOC 2757 AXSD79A000536": "PNP(AOC) 2757 AXSD79A000536"},
    )

    assert 'output "PNP(AOC) 2757 AXSD79A000536"' in block


def test_falls_back_to_the_port_name_without_make():
    """Nothing to rebuild from: the connector name is all that is left."""
    monitor = MonitorConfig(name="DP-4", description="Some Monitor", enabled=False)

    assert 'output "DP-4"' in monitor.to_niri_block(use_description=True, niri_ids={})


def test_no_rebuild_without_make():
    assert MonitorConfig(name="DP-4", model="X").niri_native_description() is None


def test_port_names_stay_untouched_when_descriptions_are_off():
    monitor = MonitorConfig(name="DP-4", description="AOC 2757 AXSD79A000536",
                            make="AOC", model="2757", serial="AXSD79A000536")

    assert 'output "DP-4"' in monitor.to_niri_block(use_description=False)


def test_profile_disables_a_missing_monitor_by_description():
    """End to end: the case that left windows stranded on a switched-away screen.

    LG+AOC is applied the moment the Samsung disappears, and the Samsung is
    stored under DP-4 while it now reports on HDMI-A-1.
    """
    lg = MonitorConfig(
        name="DP-2", description="LG Electronics LG HDR 4K 0x00078A89",
        make="LG Electronics", model="LG HDR 4K", serial="0x00078A89",
        width=3840, height=2160, x=1080, y=0, scale=1.25,
    )
    samsung = MonitorConfig(
        name="DP-4", description="Samsung Electric Company C27JG5x HTOM500271",
        make="Samsung Electric Company", model="C27JG5x", serial="HTOM500271",
        width=2560, height=1440, enabled=False,
    )
    profile = Profile(name="LG+AOC", monitors=[lg, samsung])

    config = profile.generate_niri_config(
        use_description=True, niri_ids={lg.description: lg.description},
    )

    assert 'output "Samsung Electric Company C27JG5x HTOM500271" {\n    off\n}' in config
    assert 'output "DP-4"' not in config
