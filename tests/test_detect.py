"""Il profilo "corrente" deve descrivere il layout reale, non l'ultimo applicato."""

from __future__ import annotations

import os
import shutil
import socket
import tempfile
from pathlib import Path

import pytest

from monique.detect import detect_backend, detect_best_profile, detect_current_profile
from monique.models import MonitorConfig, Profile
from monique.niri import NiriIPC
from monique.profile_manager import ProfileManager
from monique.umbriel import UmbrielIPC, find_umbriel_socket


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


# ── Umbriel: variabili d'ambiente e scansione dei socket ─────────────────

_COMPOSITOR_VARS = (
    "HYPRLAND_INSTANCE_SIGNATURE", "NIRI_SOCKET", "SWAYSOCK",
    "UMBRIEL_SOCKET", "WAYLAND_DISPLAY",
)


@pytest.fixture
def runtime(monkeypatch):
    """A short runtime dir (unix socket paths are limited to 107 bytes)."""
    path = Path(tempfile.mkdtemp(prefix="umb"))
    for var in _COMPOSITOR_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(path))
    yield path
    # detect_backend() esporta il socket trovato direttamente in os.environ
    for var in _COMPOSITOR_VARS:
        os.environ.pop(var, None)
    shutil.rmtree(path, ignore_errors=True)


def _listening(path: Path) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX)
    sock.bind(str(path))
    sock.listen(1)
    return sock


def _stale(path: Path) -> None:
    """Leave a socket file nobody listens on, as a crashed session does."""
    sock = socket.socket(socket.AF_UNIX)
    sock.bind(str(path))
    sock.close()


def test_umbriel_socket_env_selects_umbriel(runtime, monkeypatch):
    monkeypatch.setenv("UMBRIEL_SOCKET", str(runtime / "umbriel-wayland-0.sock"))

    assert isinstance(detect_backend(), UmbrielIPC)


def test_umbriel_nested_in_niri_is_umbriel(runtime, monkeypatch):
    # Umbriel dentro Niri: NIRI_SOCKET resta nell'ambiente, il socket combacia
    monkeypatch.setenv("NIRI_SOCKET", str(runtime / "niri.sock"))
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.setenv("UMBRIEL_SOCKET", str(runtime / "umbriel-wayland-1.sock"))

    assert isinstance(detect_backend(), UmbrielIPC)


def test_niri_nested_in_umbriel_is_niri(runtime, monkeypatch):
    # Niri dentro Umbriel: UMBRIEL_SOCKET e' del display esterno, non combacia
    monkeypatch.setenv("NIRI_SOCKET", str(runtime / "niri.sock"))
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.setenv("UMBRIEL_SOCKET", str(runtime / "umbriel-wayland-0.sock"))

    assert isinstance(detect_backend(), NiriIPC)


def test_scan_finds_a_live_umbriel_socket(runtime):
    live = _listening(runtime / "umbriel-wayland-0.sock")
    try:
        assert isinstance(detect_backend(), UmbrielIPC)
    finally:
        live.close()

    assert os.environ["UMBRIEL_SOCKET"] == str(runtime / "umbriel-wayland-0.sock")


def test_scan_skips_stale_sockets(runtime):
    _stale(runtime / "umbriel-wayland-0.sock")
    live = _listening(runtime / "umbriel-wayland-1.sock")
    try:
        assert find_umbriel_socket(runtime) == runtime / "umbriel-wayland-1.sock"
    finally:
        live.close()


def test_scan_prefers_the_documented_name(runtime, monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-7")
    first = _listening(runtime / "umbriel-wayland-0.sock")
    wanted = _listening(runtime / "umbriel-wayland-7.sock")
    try:
        assert find_umbriel_socket(runtime) == runtime / "umbriel-wayland-7.sock"
    finally:
        first.close()
        wanted.close()


def test_scan_without_sockets_finds_nothing(runtime):
    assert find_umbriel_socket(runtime) is None
    assert detect_backend() is None


def test_umbriel_is_scanned_after_the_other_compositors(runtime):
    live = _listening(runtime / "umbriel-wayland-0.sock")
    niri = _listening(runtime / "niri.wayland-1.1.sock")
    try:
        assert isinstance(detect_backend(), NiriIPC)
    finally:
        live.close()
        niri.close()
