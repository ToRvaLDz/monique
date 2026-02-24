"""Background daemon that listens for monitor hotplug events and applies profiles."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import threading
import time
from pathlib import Path

from .hyprland import HyprlandIPC
from .niri import NiriIPC
from .sway import SwayIPC
from .models import Profile, apply_clamshell, undo_clamshell
from .profile_manager import ProfileManager
from .utils import load_app_settings

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


def _detect_backend() -> HyprlandIPC | NiriIPC | SwayIPC | None:
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


class MonitorDaemon:
    """Watches compositor events and auto-applies matching profiles."""

    def __init__(self) -> None:
        self._profile_mgr = ProfileManager()
        self._debounce_handle: asyncio.TimerHandle | None = None
        self._last_apply_time: float = 0.0
        self._last_applied_profile: str | None = None
        self._prev_applied_profile: str | None = None
        self._last_applied_fingerprint: set[str] = set()
        self._using_udev: bool = False
        self._ipc: HyprlandIPC | NiriIPC | SwayIPC | None = None
        self._lid_closed: bool | None = None  # None = no lid / not monitored
        self._asyncio_loop: asyncio.AbstractEventLoop | None = None

    async def run(self) -> None:
        log.info("Starting Monique daemon")
        self._asyncio_loop = asyncio.get_event_loop()
        self._start_lid_monitor()

        while True:
            try:
                ipc = _detect_backend()
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
            except Exception as e:
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

    def _schedule_apply(self, ipc: HyprlandIPC | NiriIPC | SwayIPC) -> None:
        """Debounce monitor events before applying."""
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
                    lambda: asyncio.ensure_future(self._apply_best_profile(ipc)),
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
                    lambda: asyncio.ensure_future(self._apply_best_profile(ipc)),
                )
                return
            debounce_ms = NIRI_DEBOUNCE_MS
        else:
            debounce_ms = DEBOUNCE_MS

        self._debounce_handle = loop.call_later(
            debounce_ms / 1000.0,
            lambda: asyncio.ensure_future(self._apply_best_profile(ipc)),
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

                # Detect A→B→A loop (config reload changes fingerprint temporarily)
                if not force and profile.name == self._prev_applied_profile:
                    elapsed = time.monotonic() - self._last_apply_time
                    if elapsed < 30:
                        log.info(
                            "Loop detected (%s → %s → %s), skipping",
                            self._prev_applied_profile,
                            self._last_applied_profile,
                            profile.name,
                        )
                        return

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
                self._last_apply_time = time.monotonic()
                self._prev_applied_profile = self._last_applied_profile
                self._last_applied_profile = profile.name
                self._last_applied_fingerprint = set(fingerprint)

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
        except Exception as e:
            log.error("Failed to apply profile: %s", e)

    # ── Lid monitoring via UPower D-Bus ─────────────────────────────

    def _start_lid_monitor(self) -> None:
        """Start monitoring lid state via UPower D-Bus in a background thread."""
        try:
            import gi
            gi.require_version("Gio", "2.0")
            from gi.repository import Gio, GLib
        except (ImportError, ValueError):
            log.info("GLib not available, lid monitoring disabled")
            return

        def _run() -> None:
            try:
                bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)

                # Check if lid is present
                result = bus.call_sync(
                    "org.freedesktop.UPower",
                    "/org/freedesktop/UPower",
                    "org.freedesktop.DBus.Properties",
                    "Get",
                    GLib.Variant("(ss)", ("org.freedesktop.UPower", "LidIsPresent")),
                    GLib.VariantType("(v)"),
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None,
                )
                lid_present = result.get_child_value(0).get_variant().get_boolean()
                if not lid_present:
                    log.info("No lid detected, lid monitoring disabled")
                    return

                # Get initial lid state
                result = bus.call_sync(
                    "org.freedesktop.UPower",
                    "/org/freedesktop/UPower",
                    "org.freedesktop.DBus.Properties",
                    "Get",
                    GLib.Variant("(ss)", ("org.freedesktop.UPower", "LidIsClosed")),
                    GLib.VariantType("(v)"),
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None,
                )
                self._lid_closed = result.get_child_value(0).get_variant().get_boolean()
                log.info("Initial lid state: %s", "closed" if self._lid_closed else "open")

                # Subscribe to PropertiesChanged
                bus.signal_subscribe(
                    "org.freedesktop.UPower",
                    "org.freedesktop.DBus.Properties",
                    "PropertiesChanged",
                    "/org/freedesktop/UPower",
                    None,
                    Gio.DBusSignalFlags.NONE,
                    _on_signal,
                    None,
                )

                loop = GLib.MainLoop.new(GLib.MainContext.default(), False)
                loop.run()
            except Exception as e:
                log.warning("Lid monitor failed: %s", e)

        def _on_signal(_conn, _sender, _path, _iface, _signal, params, _user_data):
            iface_name = params.get_child_value(0).get_string()
            if iface_name != "org.freedesktop.UPower":
                return
            changed = params.get_child_value(1)
            lid_val = changed.lookup_value("LidIsClosed", GLib.VariantType("b"))
            if lid_val is None:
                return
            closed = lid_val.get_boolean()
            log.info("Lid state changed: %s", "closed" if closed else "open")
            self._lid_closed = closed
            if self._ipc and self._asyncio_loop:
                self._asyncio_loop.call_soon_threadsafe(
                    self._schedule_apply, self._ipc,
                )

        thread = threading.Thread(target=_run, daemon=True, name="lid-monitor")
        thread.start()

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
                except Exception as e:
                    log.warning("Failed to migrate workspace %s: %s", ws_name, e)

        if migrated:
            log.info("Migrated %d workspace(s) to %s", migrated, primary)


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
