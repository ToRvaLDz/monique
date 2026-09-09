"""Rilevamento del compositore attivo e del profilo che descrive il layout corrente.

Modulo volutamente privo di dipendenze GTK: viene usato sia dalla CLI che dal
daemon, ed è quindi testabile senza un compositore in esecuzione.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .hyprland import HyprlandIPC
from .models import Profile
from .niri import NiriIPC
from .profile_manager import ProfileManager
from .sway import SwayIPC

log = logging.getLogger(__name__)

IPCBackend = HyprlandIPC | NiriIPC | SwayIPC


def detect_backend() -> IPCBackend | None:
    """Auto-detect the running compositor.

    First checks environment variables, then probes XDG_RUNTIME_DIR
    for compositor sockets (handles race condition at login when env vars
    are not yet exported to the systemd user manager).
    """
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return HyprlandIPC()
    if os.environ.get("NIRI_SOCKET"):
        return NiriIPC()
    if os.environ.get("SWAYSOCK"):
        return SwayIPC()

    # Fallback: scan for compositor sockets in XDG_RUNTIME_DIR
    xdg = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    xdg_path = Path(xdg)

    # Hyprland: look for $XDG_RUNTIME_DIR/hypr/<signature>/.socket.sock
    hypr_dir = xdg_path / "hypr"
    if hypr_dir.is_dir():
        for child in hypr_dir.iterdir():
            if child.is_dir() and (child / ".socket.sock").exists():
                os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = child.name
                log.info("Found Hyprland socket: %s", child.name)
                return HyprlandIPC()

    # Niri: look for $XDG_RUNTIME_DIR/niri.*.sock
    for sock in xdg_path.glob("niri.*.sock"):
        if sock.is_socket():
            os.environ["NIRI_SOCKET"] = str(sock)
            log.info("Found Niri socket: %s", sock.name)
            return NiriIPC()

    # Sway: look for $XDG_RUNTIME_DIR/sway-ipc.*.sock
    for sock in xdg_path.glob("sway-ipc.*.sock"):
        if sock.is_socket():
            os.environ["SWAYSOCK"] = str(sock)
            log.info("Found Sway socket: %s", sock.name)
            return SwayIPC()

    return None


def detect_current_profile(
    manager: ProfileManager | None = None,
    ipc: IPCBackend | None = None,
) -> Profile | None:
    """Return the saved profile that matches the live compositor layout.

    Matching is exact (position/scale/transform/resolution of every monitor),
    the same criterion the GUI uses to preselect a profile.  Returns ``None``
    when no compositor is reachable or no saved profile describes the current
    layout.
    """
    ipc = ipc or detect_backend()
    if ipc is None:
        return None

    try:
        monitors = ipc.get_monitors()
    except (OSError, ValueError) as e:
        log.warning("Cannot read monitors from compositor: %s", e)
        return None

    fingerprint = sorted(m.description for m in monitors if m.description)
    if not fingerprint:
        return None

    manager = manager or ProfileManager()
    return manager.find_best_match(fingerprint, monitors, exact_config=True)
