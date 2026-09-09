"""Background daemon that listens for monitor hotplug events and applies profiles."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import time

from .hyprland import HyprlandIPC
from .niri import NiriIPC
from .sway import SwayIPC
from .dbus_events import SystemBusWatcher
from .detect import detect_backend
from .models import Profile, apply_clamshell, undo_clamshell
from .profile_manager import ProfileManager
from .utils import load_app_settings, save_active_profile

try:
    import pyudev
    HAS_PYUDEV = True
except ImportError:
    HAS_PYUDEV = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [moniqued] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

DEBOUNCE_MS = 500
UDEV_SETTLE_S = 5  # Ignore udev events shortly after applying (config reload triggers DRM events)
NIRI_DEBOUNCE_MS = 3000  # Niri temporarily drops outputs during rearrangement
NIRI_SETTLE_S_DEFAULT = 15  # Default settle time; overridden by user setting
NIRI_SETTLE_BASE = 10  # Extra base seconds added to settle (matches GUI confirm timeout)
RESUME_POLL_S = 0.5  # Interval between monitor reads while waiting for resume to settle
RESUME_TIMEOUT_S = 10.0  # Give up waiting for a stable read and apply what we have


class MonitorDaemon:
    """Watches compositor events and auto-applies matching profiles."""

    def __init__(self) -> None:
        self._profile_mgr = ProfileManager()
        self._debounce_handle: asyncio.TimerHandle | None = None
        self._last_apply_time: float = 0.0
        self._last_applied_profile: str | None = None
        self._last_applied_fingerprint: set[str] = set()
        self._using_udev: bool = False
        self._ipc: HyprlandIPC | NiriIPC | SwayIPC | None = None
        self._lid_closed: bool | None = None  # None = no lid / not monitored
        self._awaiting_stable: bool = False
        self._asyncio_loop: asyncio.AbstractEventLoop | None = None

    async def run(self) -> None:
        log.info("Starting Monique daemon")
        self._asyncio_loop = asyncio.get_event_loop()
        self._start_system_watcher()

        while True:
            try:
                ipc = detect_backend()
                if ipc is None:
                    log.warning("No supported compositor detected. Retrying in 5s...")
                    await asyncio.sleep(5)
                    continue

                if isinstance(ipc, HyprlandIPC):
                    backend_name = "Hyprland"
                elif isinstance(ipc, NiriIPC):
                    backend_name = "Niri"
                else:
                    backend_name = "Sway"
                log.info("Detected %s compositor", backend_name)
                await self._listen(ipc)
            except (ConnectionRefusedError, FileNotFoundError, ConnectionError) as e:
                log.warning("Cannot connect to compositor: %s. Retrying in 5s...", e)
                await asyncio.sleep(5)
            except Exception as e:  # noqa: BLE001 - top-level backstop: log and keep the daemon alive
                log.error("Unexpected error: %s. Retrying in 5s...", e)
                await asyncio.sleep(5)
            finally:
                if self._debounce_handle:
                    self._debounce_handle.cancel()
                    self._debounce_handle = None

    async def _listen(self, ipc: HyprlandIPC | NiriIPC | SwayIPC) -> None:
        self._ipc = ipc
        if isinstance(ipc, NiriIPC) and HAS_PYUDEV:
            self._using_udev = True
            log.info("Using udev DRM events for Niri hotplug detection")
            await self._listen_udev(ipc)
        else:
            self._using_udev = False
            log.info("Connected to compositor event socket")
            await self._apply_best_profile(ipc, force=True)
            async for event in ipc.connect_event_socket():
                log.info("Monitor event: %s", event)
                self._schedule_apply(ipc)

    async def _listen_udev(self, ipc: NiriIPC) -> None:
        """Listen for udev DRM events instead of compositor IPC."""
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem='drm')
        monitor.start()

        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_readable():
            device = monitor.poll(timeout=0)
            if device and device.action in ('change', 'add', 'remove'):
                queue.put_nowait(device)

        loop.add_reader(monitor.fileno(), on_readable)
        try:
            await self._apply_best_profile(ipc, force=True)
            while True:
                device = await queue.get()
                log.info("udev DRM event: %s %s", device.action, device.device_path)
                self._schedule_apply(ipc)
        finally:
            loop.remove_reader(monitor.fileno())

    def _schedule_apply(self, ipc: HyprlandIPC | NiriIPC | SwayIPC, *, force: bool = False) -> None:
        """Debounce monitor events before applying."""
        if self._awaiting_stable:
            # Resume fires a burst of DRM events; applying on one of them would
            # defeat the wait for a settled monitor list
            log.debug("Monitors still settling, ignoring event")
            return

        loop = asyncio.get_event_loop()
        if self._debounce_handle:
            self._debounce_handle.cancel()

        if self._using_udev:
            # udev mode: short settle to ignore DRM events from config reload
            elapsed = time.monotonic() - self._last_apply_time
            if elapsed < UDEV_SETTLE_S:
                remaining = UDEV_SETTLE_S - elapsed
                log.debug("udev settle: %.1fs remaining, deferring", remaining)
                self._debounce_handle = loop.call_later(
                    remaining,
                    lambda f=force: asyncio.ensure_future(self._apply_best_profile(ipc, force=f)),
                )
                return
            debounce_ms = DEBOUNCE_MS
        elif isinstance(ipc, NiriIPC):
            # Fallback IPC: maintain settle time to avoid config-reload loops
            settings = load_app_settings()
            settle_s = NIRI_SETTLE_BASE + settings.get("niri_settle_time", NIRI_SETTLE_S_DEFAULT)
            elapsed = time.monotonic() - self._last_apply_time
            if elapsed < settle_s:
                remaining = settle_s - elapsed
                self._debounce_handle = loop.call_later(
                    remaining,
                    lambda f=force: asyncio.ensure_future(self._apply_best_profile(ipc, force=f)),
                )
                return
            debounce_ms = NIRI_DEBOUNCE_MS
        else:
            debounce_ms = DEBOUNCE_MS

        self._debounce_handle = loop.call_later(
            debounce_ms / 1000.0,
            lambda f=force: asyncio.ensure_future(self._apply_best_profile(ipc, force=f)),
        )

    async def _apply_best_profile(self, ipc: HyprlandIPC | NiriIPC | SwayIPC, *, force: bool = False) -> None:
        """Query current monitors, find best profile, and apply it."""
        try:
            monitors = ipc.get_monitors()
            fingerprint = sorted(m.description for m in monitors if m.description)
            connected_descs = {m.description for m in monitors if m.description}
            log.info("Current fingerprint: %s", fingerprint)

            settings = load_app_settings()
            clamshell = settings.get("clamshell_mode", False)

            profile = self._profile_mgr.find_best_match(fingerprint, monitors)
            if profile:
                # Skip if we just applied the same profile
                if not force and profile.name == self._last_applied_profile:
                    log.info("Profile %s already applied, skipping", profile.name)
                    return

                # No A→B→A loop guard here on purpose.  Config-reload echoes are
                # already absorbed upstream in ``_schedule_apply`` (UDEV_SETTLE_S
                # in udev mode, the Niri settle window otherwise), so by the time
                # we get here the fingerprint has settled and the live state is
                # authoritative.  A name-history guard cannot tell a reload echo
                # apart from a real drop/recover (DPMS standby produces exactly
                # the same A→B→A sequence) and, being reachable only on the
                # recovery leg, it systematically stranded the daemon on the
                # degraded profile.

                # When clamshell is active, the daemon owns internal display
                # control.  First ensure internal monitors are enabled
                # (handles profiles saved with the old manual toggle), then
                # disable them only if the lid is closed AND external
                # monitors are actually connected right now.
                if clamshell:
                    profile = Profile.from_dict(profile.to_dict())
                    undo_clamshell(profile.monitors)
                    if self._lid_closed is not False:
                        connected_externals = [
                            m for m in profile.monitors
                            if not m.is_internal and m.enabled
                            and m.description in connected_descs
                        ]
                        if connected_externals:
                            apply_clamshell(profile.monitors)
                            log.info("Clamshell: lid closed, disabled internal display(s)")
                        else:
                            log.info(
                                "Clamshell: lid closed but no external monitors "
                                "connected, keeping internal display(s) enabled"
                            )

                # Safety: ensure at least one actually-connected monitor
                # remains enabled.  Prevents black screen in edge cases.
                enabled_connected = [
                    m for m in profile.monitors
                    if m.enabled and m.description in connected_descs
                ]
                if not enabled_connected:
                    log.warning(
                        "Safety: profile %s would disable all connected "
                        "monitors, force-enabling internal display(s)",
                        profile.name,
                    )
                    recovered = False
                    for m in profile.monitors:
                        if m.is_internal and m.description in connected_descs:
                            m.enabled = True
                            recovered = True
                    if not recovered:
                        for m in profile.monitors:
                            if m.description in connected_descs:
                                m.enabled = True
                                recovered = True
                                break
                    if not recovered:
                        log.error(
                            "Safety: cannot find any connected monitor to "
                            "enable, skipping profile apply"
                        )
                        return

                # Snapshot workspaces before applying
                ws_snapshot = ipc.get_workspaces()

                log.info("Applying profile: %s", profile.name)
                update_sddm = settings.get("update_sddm", True)
                update_greetd = settings.get("update_greetd", True)
                use_desc = not settings.get("use_port_names", False)
                ipc.apply_profile(
                    profile, update_sddm=update_sddm,
                    update_greetd=update_greetd, use_description=use_desc,
                )
                profile.last_applied_time = time.time()
                self._profile_mgr.save(profile)
                self._last_apply_time = time.monotonic()
                self._last_applied_profile = profile.name
                self._last_applied_fingerprint = set(fingerprint)
                save_active_profile(profile.name)

                # Migrate orphaned workspaces (Niri handles this natively)
                if not isinstance(ipc, NiriIPC) and settings.get("migrate_workspaces", True):
                    self._migrate_orphaned_workspaces(ipc, profile, ws_snapshot)
            else:
                # No matching profile found.
                # Safety: check if all connected monitors are disabled and
                # try to recover by enabling internal displays.
                all_disabled = monitors and all(not m.enabled for m in monitors)
                has_disabled_internal = any(
                    m.is_internal and not m.enabled for m in monitors
                )

                if clamshell and self._lid_closed is False and has_disabled_internal:
                    # Lid is definitely open → re-enable internal
                    if undo_clamshell(monitors):
                        log.info("Clamshell: lid open, re-enabled internal display(s)")
                        temp = Profile(name="clamshell-undo", monitors=monitors)
                        update_sddm = settings.get("update_sddm", True)
                        use_desc = not settings.get("use_port_names", False)
                        ipc.apply_profile(
                            temp, update_sddm=update_sddm, use_description=use_desc,
                        )
                        self._last_apply_time = time.monotonic()
                elif all_disabled and has_disabled_internal:
                    # Emergency: all monitors off regardless of clamshell/lid
                    # state.  Re-enable internal to avoid black screen.
                    log.warning(
                        "All connected monitors disabled with no matching "
                        "profile, force-enabling internal display(s)"
                    )
                    for m in monitors:
                        if m.is_internal:
                            m.enabled = True
                    temp = Profile(name="emergency-recovery", monitors=monitors)
                    update_sddm = settings.get("update_sddm", True)
                    use_desc = not settings.get("use_port_names", False)
                    ipc.apply_profile(
                        temp, update_sddm=update_sddm, use_description=use_desc,
                    )
                    self._last_apply_time = time.monotonic()
                else:
                    log.info("No matching profile found")
        except (OSError, RuntimeError) as e:
            log.error("Failed to apply profile: %s", e)

    # ── Eventi di sistema (coperchio, risveglio) ────────────────────

    def _start_system_watcher(self) -> None:
        """Watch the system bus for lid and suspend/resume events."""
        SystemBusWatcher(
            on_lid_change=self._on_lid_change,
            on_resume=self._on_resume,
        ).start()

    def _on_lid_change(self, closed: bool, initial: bool) -> None:
        """Lid opened or closed: clamshell decisions depend on this state.

        The state read at startup is only recorded: the first apply is the
        one ``_listen`` performs once connected.
        """
        self._lid_closed = closed
        if not initial:
            self._request_apply()

    def _on_resume(self) -> None:
        """Back from suspend: monitors may have changed while we were asleep.

        No hotplug event is delivered for a monitor plugged or unplugged
        during suspend, so the layout has to be re-checked from scratch.
        """
        if self._ipc is None or self._asyncio_loop is None:
            return
        self._asyncio_loop.call_soon_threadsafe(self._start_resume_apply)

    def _start_resume_apply(self) -> None:
        """Enter the resume path, dropping any apply already in flight."""
        if self._debounce_handle:
            self._debounce_handle.cancel()
            self._debounce_handle = None
        asyncio.ensure_future(self._apply_when_stable(self._ipc))

    async def _apply_when_stable(self, ipc: HyprlandIPC | NiriIPC | SwayIPC) -> None:
        """Wait for the monitor list to settle, then apply the matching profile."""
        if self._awaiting_stable:
            return
        self._awaiting_stable = True
        try:
            await self._wait_for_stable(ipc)
        finally:
            self._awaiting_stable = False
        await self._apply_best_profile(ipc, force=True)

    async def _wait_for_stable(
        self,
        ipc: HyprlandIPC | NiriIPC | SwayIPC,
        *,
        interval: float = RESUME_POLL_S,
        timeout: float = RESUME_TIMEOUT_S,
    ) -> None:
        """Block until two consecutive reads report the same monitors.

        Outputs come back one at a time after a resume, so the first read is
        rarely the whole picture: matching on it would apply a degraded
        profile and migrate workspaces away from monitors that are about to
        reappear.  A monitor that never comes back must not stall the daemon
        either, hence the timeout.
        """
        previous: list[str] | None = None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                fingerprint = sorted(m.description for m in ipc.get_monitors() if m.description)
            except (OSError, RuntimeError) as e:
                # Il compositore può non rispondere subito dopo il risveglio
                log.debug("Monitor read failed while settling: %s", e)
                fingerprint = []
            if fingerprint and fingerprint == previous:
                log.info("Monitors settled: %s", fingerprint)
                return
            previous = fingerprint
            await asyncio.sleep(interval)
        log.warning("Monitors still unsettled after %.0fs, applying anyway", timeout)

    def _request_apply(self) -> None:
        """Schedule an apply from a non-asyncio thread."""
        if self._ipc is None or self._asyncio_loop is None:
            return
        self._asyncio_loop.call_soon_threadsafe(
            lambda: self._schedule_apply(self._ipc, force=True),
        )

    def _migrate_orphaned_workspaces(
        self,
        ipc: HyprlandIPC | SwayIPC,
        profile,
        ws_snapshot: list[dict],
    ) -> None:
        """Move workspaces from disabled/removed monitors to the primary monitor."""
        enabled_names = {m.name for m in profile.monitors if m.enabled}
        if not enabled_names:
            return

        primary = next(m.name for m in profile.monitors if m.enabled)
        migrated = 0

        for ws in ws_snapshot:
            ws_monitor = ws.get("monitor", "")
            ws_name = str(ws.get("name", ws.get("id", "")))
            if ws_monitor and ws_monitor not in enabled_names:
                try:
                    ipc.move_workspace_to_monitor(ws_name, primary)
                    migrated += 1
                except (OSError, RuntimeError) as e:
                    log.warning("Failed to migrate workspace %s: %s", ws_name, e)

        if migrated:
            log.info("Migrated %d workspace(s) to %s", migrated, primary)


async def _amain() -> None:
    daemon = MonitorDaemon()
    task = asyncio.ensure_future(daemon.run())

    # Su SIGTERM/SIGINT cancella il task: il loop di run() è un `while True` che
    # non termina mai, quindi fermare l'event loop a freddo (loop.stop) farebbe
    # sollevare "Event loop stopped before Future completed" e uscire con errore.
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, task.cancel)

    with contextlib.suppress(asyncio.CancelledError):
        await task


def main() -> None:
    try:
        asyncio.run(_amain())
    finally:
        log.info("Daemon stopped")
