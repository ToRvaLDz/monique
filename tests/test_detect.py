"""Il profilo "corrente" deve descrivere il layout reale, non l'ultimo applicato."""

from __future__ import annotations

import pytest

from monique.detect import detect_best_profile, detect_current_profile
from monique.models import MonitorConfig, Profile
from monique.profile_manager import ProfileManager


class FakeIPC:
    """Compositor stub returning a fixed monitor list."""

    def __init__(self, monitors: list[MonitorConfig], error: Exception | None = None) -> None:
        self._monitors = monitors
        self._error = error

    def get_monitors(self) -> list[MonitorConfig]:
        if self._error:
            raise self._error
        return self._monitors


def _monitor(name: str, desc: str, *, enabled: bool = True, x: int = 0) -> MonitorConfig:
    return MonitorConfig(
        name=name, description=desc, width=1920, height=1080,
        refresh_rate=60.0, x=x, y=0, scale=1.0, enabled=enabled,
    )


@pytest.fixture
def manager(tmp_path):
    directory = tmp_path / "profiles"
    directory.mkdir()
    return ProfileManager(directory)


def test_matches_live_layout_not_last_applied(manager):
    """Two profiles over the same monitors: the live layout picks the right one."""
    two_on = [_monitor("DP-1", "Mon A"), _monitor("DP-2", "Mon B", x=1920)]
    one_on = [_monitor("DP-1", "Mon A"), _monitor("DP-2", "Mon B", enabled=False, x=1920)]

    manager.save(Profile(name="Both", monitors=two_on))
    # L'ultimo applicato è "OnlyA", ma i monitor accesi sono due
    manager.save(Profile(name="OnlyA", monitors=one_on, last_applied_time=9999.0))

    match = detect_current_profile(manager, FakeIPC(two_on))

    assert match is not None
    assert match.name == "Both"


def test_no_match_when_layout_differs(manager):
    """A layout no saved profile describes yields no match (caller falls back)."""
    manager.save(Profile(name="OnlyA", monitors=[
        _monitor("DP-1", "Mon A"), _monitor("DP-2", "Mon B", enabled=False, x=1920),
    ]))

    live = [_monitor("DP-1", "Mon A"), _monitor("DP-2", "Mon B", x=1920)]

    assert detect_current_profile(manager, FakeIPC(live)) is None


def test_unreachable_compositor_returns_none(manager):
    manager.save(Profile(name="OnlyA", monitors=[_monitor("DP-1", "Mon A")]))

    ipc = FakeIPC([], error=OSError("socket gone"))

    assert detect_current_profile(manager, ipc) is None


def test_no_monitors_returns_none(manager):
    manager.save(Profile(name="OnlyA", monitors=[_monitor("DP-1", "Mon A")]))

    assert detect_current_profile(manager, FakeIPC([])) is None


def test_best_profile_ignores_the_layout_in_place(manager):
    """The wrong profile being applied must not stop the right one from matching.

    Scenario from issue #47: a monitor is unplugged while the laptop sleeps,
    so at wake-up the layout still describes a monitor that is now gone.
    """
    both = [_monitor("DP-1", "Mon A"), _monitor("DP-2", "Mon B", x=1920)]
    manager.save(Profile(name="Both", monitors=both))
    manager.save(Profile(name="OnlyA", monitors=[
        _monitor("DP-1", "Mon A"), _monitor("DP-2", "Mon B", enabled=False, x=1920),
    ]))

    # Solo "Mon A" è collegato, ma "Both" è ancora quello applicato
    live = [_monitor("DP-1", "Mon A", x=1920)]

    assert detect_current_profile(manager, FakeIPC(live)) is None
    match = detect_best_profile(manager, FakeIPC(live))
    assert match is not None
    assert match.name == "OnlyA"


def test_best_profile_needs_a_reachable_compositor(manager):
    manager.save(Profile(name="OnlyA", monitors=[_monitor("DP-1", "Mon A")]))

    assert detect_best_profile(manager, FakeIPC([], error=OSError("socket gone"))) is None
