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


# ── Eventi di sistema: risveglio e coperchio ────────────────────────


def _daemon_with_loop(loop: asyncio.AbstractEventLoop) -> tuple[MonitorDaemon, list[bool]]:
    """A daemon wired to *loop*, recording the ``force`` flag of each apply."""
    daemon = MonitorDaemon()
    daemon._ipc = _FakeIPC([])
    daemon._asyncio_loop = loop
    scheduled: list[bool] = []
    daemon._schedule_apply = lambda ipc, *, force=False: scheduled.append(force)
    return daemon, scheduled


class _SettlingIPC(_FakeIPC):
    """IPC whose monitor list changes read after read, as it does on resume."""

    def __init__(self, reads: list[list[MonitorConfig]]) -> None:
        super().__init__(reads[0])
        self._reads = reads
        self.read_count = 0

    def get_monitors(self) -> list[MonitorConfig]:
        index = min(self.read_count, len(self._reads) - 1)
        self.read_count += 1
        return self._reads[index]


def test_resume_enters_the_settle_path():
    """Resume must not go through the plain debounce."""
    loop = asyncio.new_event_loop()
    try:
        daemon = MonitorDaemon()
        daemon._ipc = _FakeIPC([])
        daemon._asyncio_loop = loop
        entered: list[bool] = []
        daemon._start_resume_apply = lambda: entered.append(True)
        daemon._on_resume()
        loop.run_until_complete(asyncio.sleep(0))
    finally:
        loop.close()

    assert entered == [True]


def test_wait_returns_once_two_reads_agree():
    """One output at a time comes back: the partial reads must not count."""
    partial = [_mon("eDP-2", "AU Optronics")]
    full = [_mon("eDP-2", "AU Optronics"), _mon("DP-2", "LG HDR 4K")]
    ipc = _SettlingIPC([partial, full, full, full])

    loop = asyncio.new_event_loop()
    try:
        daemon = MonitorDaemon()
        loop.run_until_complete(daemon._wait_for_stable(ipc, interval=0.01, timeout=1.0))
    finally:
        loop.close()

    # partial, full, full: si ferma alla prima coppia identica
    assert ipc.read_count == 3


def test_wait_gives_up_when_the_layout_keeps_changing():
    """A monitor that never comes back must not stall the daemon forever."""
    class _NeverSettles(_FakeIPC):
        def __init__(self) -> None:
            super().__init__([])
            self.read_count = 0

        def get_monitors(self) -> list[MonitorConfig]:
            self.read_count += 1
            return [_mon(f"DP-{self.read_count}", f"Mon {self.read_count}")]

    ipc = _NeverSettles()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            MonitorDaemon()._wait_for_stable(ipc, interval=0.01, timeout=0.1),
        )
    finally:
        loop.close()

    assert ipc.read_count > 1


def test_wait_survives_a_compositor_that_is_not_answering_yet():
    """Reads can fail right after resume without aborting the wait."""
    class _SlowToWake(_FakeIPC):
        def __init__(self) -> None:
            super().__init__([])
            self.read_count = 0

        def get_monitors(self) -> list[MonitorConfig]:
            self.read_count += 1
            if self.read_count < 3:
                raise OSError("compositor not ready")
            return [_mon("eDP-2", "AU Optronics")]

    ipc = _SlowToWake()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            MonitorDaemon()._wait_for_stable(ipc, interval=0.01, timeout=1.0),
        )
    finally:
        loop.close()

    assert ipc.read_count == 4


class _FastDaemon(MonitorDaemon):
    """Daemon that polls fast enough for a test to wait on it."""

    async def _wait_for_stable(self, ipc, *, interval: float = 0.01, timeout: float = 1.0):
        await super()._wait_for_stable(ipc, interval=interval, timeout=timeout)


def test_resume_applies_the_settled_layout_not_the_partial_one():
    """The whole point: no degraded profile applied on a half-woken layout.

    Only the LG and the AOC are back on the first read, which on its own
    matches LG+AOC; the Samsung follows a moment later and the right answer
    is Full.
    """
    _save_profiles()
    partial = [_mon("DP-2", "LG HDR 4K"), _mon("DP-3", "AOC 2757")]
    ipc = _SettlingIPC([partial, _FOUR, _FOUR, _FOUR])

    daemon = _FastDaemon()
    daemon._ipc = ipc
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(daemon._apply_when_stable(ipc))
    finally:
        loop.close()

    assert ipc.applied == ["Full"]
    assert daemon._awaiting_stable is False


def test_without_the_wait_the_partial_layout_would_win():
    """Counter-proof: the same first read applied directly gives the degraded profile."""
    _save_profiles()
    ipc = _FakeIPC([_mon("DP-2", "LG HDR 4K"), _mon("DP-3", "AOC 2757")])

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(MonitorDaemon()._apply_best_profile(ipc, force=True))
    finally:
        loop.close()

    assert ipc.applied == ["LG+AOC"]


def test_events_are_dropped_while_waiting_for_the_layout_to_settle():
    loop = asyncio.new_event_loop()
    try:
        daemon, scheduled = _daemon_with_loop(loop)
        daemon._schedule_apply = MonitorDaemon._schedule_apply.__get__(daemon)
        daemon._awaiting_stable = True
        daemon._schedule_apply(daemon._ipc)
    finally:
        loop.close()

    assert daemon._debounce_handle is None


def test_resume_before_the_compositor_is_connected_is_ignored():
    """Waking up before _listen has an IPC must not blow up."""
    daemon = MonitorDaemon()
    daemon._on_resume()  # nessun ipc, nessun loop

    assert daemon._ipc is None


def test_initial_lid_state_is_recorded_without_applying():
    loop = asyncio.new_event_loop()
    try:
        daemon, scheduled = _daemon_with_loop(loop)
        daemon._on_lid_change(True, True)
        loop.run_until_complete(asyncio.sleep(0))
    finally:
        loop.close()

    assert daemon._lid_closed is True
    assert scheduled == []


def test_lid_change_applies():
    loop = asyncio.new_event_loop()
    try:
        daemon, scheduled = _daemon_with_loop(loop)
        daemon._on_lid_change(True, False)
        loop.run_until_complete(asyncio.sleep(0))
    finally:
        loop.close()

    assert daemon._lid_closed is True
    assert scheduled == [True]
