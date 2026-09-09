"""Segnali D-Bus di sistema che interessano il daemon: coperchio e risveglio.

Il coperchio arriva da UPower (``LidIsClosed``), il risveglio da logind
(``PrepareForSleep``).  Entrambi vivono sul bus di sistema, quindi vengono
seguiti da un unico thread con un solo main loop GLib.

GLib è opzionale: senza, il modulo si carica comunque e il watcher non parte,
così il daemon resta importabile e testabile senza ``gi``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
    HAS_GLIB = True
except (ImportError, ValueError):  # pragma: no cover - dipende dall'ambiente
    HAS_GLIB = False

log = logging.getLogger(__name__)

UPOWER_NAME = "org.freedesktop.UPower"
UPOWER_PATH = "/org/freedesktop/UPower"
LOGIND_NAME = "org.freedesktop.login1"
LOGIND_PATH = "/org/freedesktop/login1"
LOGIND_MANAGER = "org.freedesktop.login1.Manager"


class SystemBusWatcher:
    """Dispatch lid and resume events from the system bus to callbacks.

    ``on_lid_change`` is called as ``(closed, initial)``: the first call
    reports the state found at startup, so the caller can record it without
    mistaking it for a change.

    Callbacks run on the watcher thread, not on the caller's event loop: it is
    up to the caller to hand the work over to its own loop.
    """

    def __init__(
        self,
        on_lid_change: Callable[[bool, bool], None] | None = None,
        on_resume: Callable[[], None] | None = None,
    ) -> None:
        self._on_lid_change = on_lid_change
        self._on_resume = on_resume

    def start(self) -> None:
        """Start watching in a background thread. Returns immediately."""
        if not HAS_GLIB:
            log.info("GLib not available, system bus monitoring disabled")
            return
        thread = threading.Thread(target=self._run, daemon=True, name="system-bus")
        thread.start()

    def _run(self) -> None:
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        except GLib.Error as e:
            log.warning("Cannot connect to the system bus: %s", e)
            return

        watching = False
        if self._on_lid_change is not None:
            watching |= self._watch_lid(bus)
        if self._on_resume is not None:
            watching |= self._watch_sleep(bus)
        if not watching:
            return

        try:
            GLib.MainLoop.new(GLib.MainContext.default(), False).run()
        except GLib.Error as e:  # pragma: no cover - richiede un bus di sistema
            log.warning("System bus monitor stopped: %s", e)

    # ── Coperchio (UPower) ──────────────────────────────────────────

    def _watch_lid(self, bus) -> bool:
        """Subscribe to lid state changes. Returns False when there is no lid."""
        try:
            if not self._upower_property(bus, "LidIsPresent"):
                log.info("No lid detected, lid monitoring disabled")
                return False
            closed = self._upower_property(bus, "LidIsClosed")
        except GLib.Error as e:
            log.warning("Lid monitor failed: %s", e)
            return False

        log.info("Initial lid state: %s", "closed" if closed else "open")
        self._on_lid_change(closed, True)

        bus.signal_subscribe(
            UPOWER_NAME,
            "org.freedesktop.DBus.Properties",
            "PropertiesChanged",
            UPOWER_PATH,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_properties_changed,
            None,
        )
        return True

    @staticmethod
    def _upower_property(bus, name: str) -> bool:
        result = bus.call_sync(
            UPOWER_NAME,
            UPOWER_PATH,
            "org.freedesktop.DBus.Properties",
            "Get",
            GLib.Variant("(ss)", (UPOWER_NAME, name)),
            GLib.VariantType("(v)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        return result.get_child_value(0).get_variant().get_boolean()

    def _on_properties_changed(
        self, _conn, _sender, _path, _iface, _signal, params, _user_data,
    ) -> None:
        if params.get_child_value(0).get_string() != UPOWER_NAME:
            return
        changed = params.get_child_value(1)
        lid = changed.lookup_value("LidIsClosed", GLib.VariantType("b"))
        if lid is None:
            return
        closed = lid.get_boolean()
        log.info("Lid state changed: %s", "closed" if closed else "open")
        self._on_lid_change(closed, False)

    # ── Risveglio (logind) ──────────────────────────────────────────

    def _watch_sleep(self, bus) -> bool:
        """Subscribe to logind's PrepareForSleep."""
        try:
            bus.signal_subscribe(
                LOGIND_NAME,
                LOGIND_MANAGER,
                "PrepareForSleep",
                LOGIND_PATH,
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_prepare_for_sleep,
                None,
            )
        except GLib.Error as e:
            log.warning("Resume monitor failed: %s", e)
            return False

        log.info("Watching logind for suspend/resume")
        return True

    def _on_prepare_for_sleep(
        self, _conn, _sender, _path, _iface, _signal, params, _user_data,
    ) -> None:
        # True: la macchina sta per sospendersi. False: è appena tornata su,
        # ed è l'unico caso in cui rileggere i monitor ha senso
        going_to_sleep = params.get_child_value(0).get_boolean()
        if going_to_sleep:
            log.info("System suspending")
            return
        log.info("System resumed, re-checking monitors")
        self._on_resume()
