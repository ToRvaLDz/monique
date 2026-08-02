"""Regression tests for the hotplug apply loop in ``monique.daemon``.

These exercise ``MonitorDaemon._apply_best_profile`` directly with a fake
IPC backend, so no compositor/GTK is required (matches the rest of the
suite: the tested modules import no ``gi``).
"""

from __future__ import annotations

import asyncio

from monique.daemon import MonitorDaemon
from monique.models import MonitorConfig, Profile
from monique.profile_manager import ProfileManager


class _FakeIPC:
    """Duck-typed compositor IPC stub, just enough for _apply_best_profile."""

    def __init__(self, monitors: list[MonitorConfig]) -> None:
        self.monitors = monitors
        self.applied: list[str] = []

    def get_monitors(self) -> list[MonitorConfig]:
        return self.monitors

    def get_workspaces(self) -> list[dict]:
        return []

    def move_workspace_to_monitor(self, workspace: str, monitor: str) -> None:
        pass

    def apply_profile(self, profile: Profile, **kwargs) -> None:
        self.applied.append(profile.name)


def _mon(name: str, description: str, enabled: bool = True) -> MonitorConfig:
    return MonitorConfig(name=name, description=description, enabled=enabled)


def _save_profiles() -> None:
    """Mirror a real-world profile pair: same 4 monitors, differing enabled."""
    full = Profile(name="Full", monitors=[
        _mon("DP-2", "LG HDR 4K"),
        _mon("DP-3", "AOC 2757"),
        _mon("HDMI-A-1", "Samsung C27JG5x"),
        _mon("eDP-2", "AU Optronics", enabled=False),
    ])
    lg_aoc = Profile(name="LG+AOC", monitors=[
        _mon("DP-2", "LG HDR 4K"),
        _mon("DP-3", "AOC 2757"),
        _mon("HDMI-A-1", "Samsung C27JG5x", enabled=False),
        _mon("eDP-2", "AU Optronics", enabled=False),
    ])
    mgr = ProfileManager()
    mgr.save(full)
    mgr.save(lg_aoc)


_THREE = [
    _mon("DP-2", "LG HDR 4K"),
    _mon("DP-3", "AOC 2757"),
    _mon("eDP-2", "AU Optronics", enabled=False),
]
_FOUR = [
    _mon("DP-2", "LG HDR 4K"),
    _mon("DP-3", "AOC 2757"),
    _mon("HDMI-A-1", "Samsung C27JG5x"),
    _mon("eDP-2", "AU Optronics", enabled=False),
]


def test_drop_and_recover_reapplies_superset_profile() -> None:
    """A monitor that drops out and reconnects (e.g. DPMS standby) must not
    leave the daemon stuck on the degraded profile.

    Regression test for the "standby drops third monitor" bug: an A→B→A
    name-history guard used to refuse the recovery back to Full for up to
    30s.  It was only ever reachable on the recovery leg, never on the
    drop leg, so it systematically biased the daemon towards the smaller
    profile.  The guard is gone; live state decides.
    """
    _save_profiles()

    daemon = MonitorDaemon()
    ipc = _FakeIPC(_FOUR)

    async def scenario() -> None:
        await daemon._apply_best_profile(ipc, force=True)
        assert ipc.applied == ["Full"]

        # Samsung drops out (standby): daemon degrades to LG+AOC.
        ipc.monitors = _THREE
        await daemon._apply_best_profile(ipc)
        assert ipc.applied == ["Full", "LG+AOC"]

        # Samsung reconnects: recovery must go through immediately.
        ipc.monitors = _FOUR
        await daemon._apply_best_profile(ipc)
        assert ipc.applied == ["Full", "LG+AOC", "Full"], (
            "recovery to the 3-monitor profile must not be suppressed"
        )

    asyncio.run(scenario())


def test_repeated_standby_cycles_keep_recovering() -> None:
    """Several standby cycles in a row must each recover.

    The removed guard was time-windowed, so it degraded specifically under
    the repeat case the user actually hit: back-to-back standby cycles.
    """
    _save_profiles()

    daemon = MonitorDaemon()
    ipc = _FakeIPC(_FOUR)

    async def scenario() -> None:
        await daemon._apply_best_profile(ipc, force=True)
        for _ in range(3):
            ipc.monitors = _THREE
            await daemon._apply_best_profile(ipc)
            ipc.monitors = _FOUR
            await daemon._apply_best_profile(ipc)

        assert ipc.applied == [
            "Full", "LG+AOC", "Full", "LG+AOC", "Full", "LG+AOC", "Full",
        ]

    asyncio.run(scenario())


def test_unchanged_fingerprint_does_not_reapply() -> None:
    """The remaining no-op guard still holds.

    Removing the loop guard must not make the daemon re-apply the profile
    it is already on -- that is what suppresses config-reload echoes that
    survive the settle window in ``_schedule_apply``.
    """
    _save_profiles()

    daemon = MonitorDaemon()
    ipc = _FakeIPC(_FOUR)

    async def scenario() -> None:
        await daemon._apply_best_profile(ipc, force=True)
        assert ipc.applied == ["Full"]

        # Spurious re-evaluation with an unchanged fingerprint.
        await daemon._apply_best_profile(ipc)
        await daemon._apply_best_profile(ipc)
        assert ipc.applied == ["Full"], "redundant re-apply must be skipped"

        # ...but an explicit force still re-applies (GUI / startup path).
        await daemon._apply_best_profile(ipc, force=True)
        assert ipc.applied == ["Full", "Full"]

    asyncio.run(scenario())
