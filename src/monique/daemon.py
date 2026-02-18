"""Background daemon that listens for monitor hotplug events and applies profiles."""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from .hyprland import HyprlandIPC
from .sway import SwayIPC
from .profile_manager import ProfileManager
from .utils import load_app_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [moniqued] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

DEBOUNCE_MS = 500


def _detect_backend() -> HyprlandIPC | SwayIPC | None:
    """Auto-detect the running compositor from environment variables."""
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return HyprlandIPC()
    if os.environ.get("SWAYSOCK"):
        return SwayIPC()
    return None


class MonitorDaemon:
    """Watches compositor events and auto-applies matching profiles."""

    def __init__(self) -> None:
        self._profile_mgr = ProfileManager()
        self._debounce_handle: asyncio.TimerHandle | None = None

    async def run(self) -> None:
        log.info("Starting Monique daemon")

        while True:
            try:
                ipc = _detect_backend()
                if ipc is None:
                    log.warning("No supported compositor detected. Retrying in 5s...")
                    await asyncio.sleep(5)
                    continue

                backend_name = "Hyprland" if isinstance(ipc, HyprlandIPC) else "Sway"
                log.info("Detected %s compositor", backend_name)
                await self._listen(ipc)
            except (ConnectionRefusedError, FileNotFoundError, ConnectionError) as e:
                log.warning("Cannot connect to compositor: %s. Retrying in 5s...", e)
                await asyncio.sleep(5)
            except Exception as e:
                log.error("Unexpected error: %s. Retrying in 5s...", e)
                await asyncio.sleep(5)
            finally:
                if self._debounce_handle:
                    self._debounce_handle.cancel()
                    self._debounce_handle = None

    async def _listen(self, ipc: HyprlandIPC | SwayIPC) -> None:
        log.info("Connected to compositor event socket")
        async for event in ipc.connect_event_socket():
            log.info("Monitor event: %s", event)
            self._schedule_apply(ipc)

    def _schedule_apply(self, ipc: HyprlandIPC | SwayIPC) -> None:
        """Debounce monitor events before applying."""
        loop = asyncio.get_event_loop()
        if self._debounce_handle:
            self._debounce_handle.cancel()
        self._debounce_handle = loop.call_later(
            DEBOUNCE_MS / 1000.0,
            lambda: asyncio.ensure_future(self._apply_best_profile(ipc)),
        )

    async def _apply_best_profile(self, ipc: HyprlandIPC | SwayIPC) -> None:
        """Query current monitors, find best profile, and apply it."""
        try:
            monitors = ipc.get_monitors()
            fingerprint = sorted(m.description for m in monitors if m.description)
            log.info("Current fingerprint: %s", fingerprint)

            profile = self._profile_mgr.find_best_match(fingerprint)
            if profile:
                log.info("Applying profile: %s", profile.name)
                update_sddm = load_app_settings().get("update_sddm", True)
                ipc.apply_profile(profile, update_sddm=update_sddm)
            else:
                log.info("No matching profile found")
        except Exception as e:
            log.error("Failed to apply profile: %s", e)


def main() -> None:
    daemon = MonitorDaemon()
    loop = asyncio.new_event_loop()

    # Handle signals for clean shutdown
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, loop.stop)

    try:
        loop.run_until_complete(daemon.run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
        log.info("Daemon stopped")
