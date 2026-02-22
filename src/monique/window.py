"""Main application window."""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gdk, Adw, GLib, Gio

from .canvas import MonitorCanvas
from .properties_panel import PropertiesPanel
from .workspace_panel import WorkspacePanel
from .profile_manager import ProfileManager
from .models import MonitorConfig, Profile, WorkspaceRule
from .hyprland import HyprlandIPC
from .niri import NiriIPC
from .sway import SwayIPC
from .utils import (
    hyprland_config_dir,
    niri_config_dir,
    backup_file,
    restore_backup,
    is_sddm_running,
    is_greetd_running,
    load_app_settings,
    save_app_settings,
)

import os
from pathlib import Path


def _detect_ipc() -> HyprlandIPC | NiriIPC | SwayIPC:
    """Auto-detect the running compositor and return the appropriate IPC client."""
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return HyprlandIPC()
    if os.environ.get("NIRI_SOCKET"):
        return NiriIPC()
    if os.environ.get("SWAYSOCK"):
        return SwayIPC()

    # Fallback: scan for compositor sockets in XDG_RUNTIME_DIR
    xdg = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))

    hypr_dir = xdg / "hypr"
    if hypr_dir.is_dir():
        for child in hypr_dir.iterdir():
            if child.is_dir() and (child / ".socket.sock").exists():
                os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = child.name
                return HyprlandIPC()

    for sock in xdg.glob("niri.*.sock"):
        if sock.is_socket():
            os.environ["NIRI_SOCKET"] = str(sock)
            return NiriIPC()

    for sock in xdg.glob("sway-ipc.*.sock"):
        if sock.is_socket():
            os.environ["SWAYSOCK"] = str(sock)
            return SwayIPC()

    # Default fallback
    return HyprlandIPC()


CONFIRM_TIMEOUT = 10  # seconds
OSD_TIMEOUT_MS = 1500


OSD_WINDOW_TITLE = "monique-osd"


class MonitorOSD(Gtk.Window):
    """Fullscreen transparent overlay showing the monitor name."""

    _css_loaded = False
    _rules_set = False

    def __init__(self, app: Gtk.Application, gdk_monitor: Gdk.Monitor, label: str) -> None:
        super().__init__(application=app)
        self._timer_id: int = 0

        if not MonitorOSD._css_loaded:
            css = Gtk.CssProvider()
            css.load_from_string(
                ".osd-bg { background: rgba(0,0,0,0.35); }"
                ".osd-label { font-size: 72px; font-weight: 800; color: white;"
                " text-shadow: 0 2px 12px rgba(0,0,0,0.7); }"
                ".osd-sub { font-size: 24px; font-weight: 400; color: rgba(255,255,255,0.7);"
                " text-shadow: 0 1px 6px rgba(0,0,0,0.5); }"
            )
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
            MonitorOSD._css_loaded = True

        self.set_title(OSD_WINDOW_TITLE)
        self.set_decorated(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                      valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        box.set_vexpand(True)
        box.set_hexpand(True)
        box.add_css_class("osd-bg")

        name_lbl = Gtk.Label(label=label)
        name_lbl.add_css_class("osd-label")
        box.append(name_lbl)

        geom = gdk_monitor.get_geometry()
        sub = Gtk.Label(label=f"{geom.width}x{geom.height}")
        sub.add_css_class("osd-sub")
        box.append(sub)

        self.set_child(box)
        self.fullscreen_on_monitor(gdk_monitor)

    def show_timed(self, timeout_ms: int = OSD_TIMEOUT_MS) -> None:
        self._ensure_rules()
        self.present()
        self._timer_id = GLib.timeout_add(timeout_ms, self._dismiss)

    def _ensure_rules(self) -> None:
        if MonitorOSD._rules_set:
            return
        try:
            from .hyprland import HyprlandIPC
            t = OSD_WINDOW_TITLE
            HyprlandIPC().batch([
                f"keyword windowrulev2 noanim, title:^{t}$",
                f"keyword windowrulev2 nofocus, title:^{t}$",
                f"keyword windowrulev2 noshadow, title:^{t}$",
                f"keyword windowrulev2 noborder, title:^{t}$",
            ])
            MonitorOSD._rules_set = True
        except Exception:
            pass

    def dismiss(self) -> None:
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = 0
        self.close()

    def _dismiss(self) -> bool:
        self._timer_id = 0
        self.close()
        return False


class MainWindow(Adw.ApplicationWindow):
    """Main window with canvas, properties panel, and toolbar."""

    __gtype_name__ = "MainWindow"

    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app, title="Monique", default_width=1100, default_height=700)
        self._ipc = _detect_ipc()
        self._profile_mgr = ProfileManager()
        self._monitors: list[MonitorConfig] = []
        self._workspace_rules = []
        self._current_profile_name: str = ""
        self._base_profile_name: str = ""  # profile before user edits (for revert)
        self._confirm_timer_id: int = 0
        self._inhibit_profile_switch: bool = False
        self._osd: MonitorOSD | None = None
        self._dirty: bool = False
        self._lid_closed: bool = False
        self._app_settings = load_app_settings()

        self._build_ui()
        self._setup_actions()
        self._load_current_state(select_profile=True)
        self._start_lid_monitor()
        self.connect("close-request", self._on_close_request)

    # ── UI Construction ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Main vertical box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        # Header bar
        header = Adw.HeaderBar()
        main_box.append(header)

        # Profile dropdown
        self._profile_dropdown = Gtk.DropDown()
        self._profile_dropdown.set_tooltip_text("Select profile")
        self._refresh_profile_list()
        self._profile_dropdown.connect("notify::selected", self._on_profile_selected)
        header.pack_start(self._profile_dropdown)

        # Save button
        btn_save = Gtk.Button(icon_name="document-save-symbolic", tooltip_text="Save profile")
        btn_save.connect("clicked", self._on_save_clicked)
        header.pack_start(btn_save)

        # Delete profile button
        btn_del = Gtk.Button(icon_name="edit-delete-symbolic", tooltip_text="Delete profile")
        btn_del.connect("clicked", self._on_delete_profile_clicked)
        header.pack_start(btn_del)

        # Spacer / title
        header.set_title_widget(Adw.WindowTitle(title="Monique", subtitle="Monitor Configuration"))

        # Apply button
        self._btn_apply = Gtk.Button(label="Apply", tooltip_text="Apply configuration")
        self._btn_apply.add_css_class("suggested-action")
        self._btn_apply.connect("clicked", self._on_apply_clicked)
        header.pack_end(self._btn_apply)

        # Workspace button (not applicable for Niri — dynamic per-monitor workspaces)
        if not isinstance(self._ipc, NiriIPC):
            btn_ws = Gtk.Button(icon_name="view-grid-symbolic", tooltip_text="Workspace rules")
            btn_ws.connect("clicked", self._on_workspaces_clicked)
            header.pack_end(btn_ws)

        # Detect monitors button
        btn_detect = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Detect monitors")
        btn_detect.connect("clicked", self._on_detect_clicked)
        header.pack_end(btn_detect)

        # Hamburger menu
        self._build_menu(header)

        # Split view: canvas + properties
        self._split = Adw.OverlaySplitView()
        self._split.set_collapsed(False)
        self._split.set_sidebar_position(Gtk.PackType.END)
        self._split.set_max_sidebar_width(380)
        self._split.set_min_sidebar_width(300)
        main_box.append(self._split)

        # Canvas
        self._canvas = MonitorCanvas()
        self._canvas.set_use_description(not self._app_settings.get("use_port_names", False))
        self._canvas.connect("monitor-selected", self._on_monitor_selected)
        self._canvas.connect("monitor-moved", self._on_monitor_moved)
        self._canvas.connect("monitor-double-clicked", self._on_monitor_double_clicked)
        self._split.set_content(self._canvas)

        # Properties panel in a scrolled window
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._props = PropertiesPanel()
        if isinstance(self._ipc, NiriIPC):
            self._props.set_compositor("niri")
        elif isinstance(self._ipc, SwayIPC):
            self._props.set_compositor("sway")
        else:
            self._props.set_compositor("hyprland")
        self._props.connect("property-changed", self._on_property_changed)
        scroll.set_child(self._props)
        self._split.set_sidebar(scroll)

        # Status bar
        self._status = Gtk.Label(label="Ready", xalign=0)
        self._status.set_margin_start(12)
        self._status.set_margin_end(12)
        self._status.set_margin_top(4)
        self._status.set_margin_bottom(4)
        self._status.add_css_class("dim-label")
        main_box.append(self._status)

        # Toast overlay (wraps the split view)
        self._toast_overlay = Adw.ToastOverlay()
        main_box.remove(self._split)
        self._toast_overlay.set_child(self._split)
        # Re-insert toast overlay where split was
        main_box.remove(self._status)
        main_box.append(self._toast_overlay)
        main_box.append(self._status)

    def _setup_actions(self) -> None:
        """Set up keyboard shortcuts."""
        # Ctrl+S -> save
        action_save = Gio.SimpleAction(name="save")
        action_save.connect("activate", lambda *_: self._on_save_clicked(None))
        self.add_action(action_save)

        # Ctrl+R -> detect
        action_detect = Gio.SimpleAction(name="detect")
        action_detect.connect("activate", lambda *_: self._on_detect_clicked(None))
        self.add_action(action_detect)

        app = self.get_application()
        app.set_accels_for_action("win.save", ["<Control>s"])
        app.set_accels_for_action("win.detect", ["<Control>r"])

    def _build_menu(self, header: Adw.HeaderBar) -> None:
        """Build the hamburger menu with sections."""
        menu = Gio.Menu()

        # ── Settings section ──
        section_settings = Gio.Menu()
        item_prefs = Gio.MenuItem.new("Preferences", "win.preferences")
        item_prefs.set_icon(Gio.ThemedIcon.new("preferences-system-symbolic"))
        section_settings.append_item(item_prefs)
        menu.append_section(None, section_settings)

        if is_sddm_running():
            # SDDM toggle action (used in preferences dialog)
            update_sddm = self._app_settings.get("update_sddm", True)
            action_sddm = Gio.SimpleAction.new_stateful(
                "update-sddm", None, GLib.Variant.new_boolean(update_sddm),
            )
            action_sddm.connect("activate", self._on_sddm_toggled)
            self.add_action(action_sddm)

        # Preferences action
        action_prefs = Gio.SimpleAction(name="preferences")
        action_prefs.connect("activate", self._on_preferences)
        self.add_action(action_prefs)

        # ── About section ──
        section_about = Gio.Menu()
        item_about = Gio.MenuItem.new("About Monique", "win.about")
        item_about.set_icon(Gio.ThemedIcon.new("help-about-symbolic"))
        section_about.append_item(item_about)
        menu.append_section(None, section_about)

        action_about = Gio.SimpleAction(name="about")
        action_about.connect("activate", self._on_about)
        self.add_action(action_about)

        menu_btn = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            menu_model=menu,
            tooltip_text="Menu",
        )
        header.pack_end(menu_btn)

    def _on_preferences(self, action: Gio.SimpleAction, param) -> None:
        """Show the preferences dialog."""
        dialog = Adw.PreferencesDialog(title="Preferences")

        # ── Display Manager group ──
        page = Adw.PreferencesPage(
            title="General",
            icon_name="preferences-system-symbolic",
        )
        dialog.add(page)

        # ── Monitor Identification group ──
        grp_id = Adw.PreferencesGroup(
            title="Monitor Identification",
            description="How monitors are identified in config files",
        )
        page.add(grp_id)

        sw_port = Adw.SwitchRow(
            title="Use port names (e.g. DP-1, HDMI-A-1)",
            subtitle="When disabled, monitors are identified by description (recommended)",
        )
        sw_port.set_active(self._app_settings.get("use_port_names", False))
        sw_port.connect("notify::active", self._on_port_names_switch_changed)
        grp_id.add(sw_port)

        # ── Display Manager group ──
        grp_dm = Adw.PreferencesGroup(
            title="Display Manager",
            description="Configure login screen integration",
        )
        page.add(grp_dm)

        has_dm = False

        if is_sddm_running():
            has_dm = True
            sw_sddm = Adw.SwitchRow(
                title="Update SDDM Xsetup",
                subtitle="Write xrandr layout to the SDDM login screen script",
                icon_name="system-lock-screen-symbolic",
            )
            sw_sddm.set_active(self._app_settings.get("update_sddm", True))
            sw_sddm.connect("notify::active", self._on_sddm_switch_changed)
            grp_dm.add(sw_sddm)

        if is_greetd_running():
            has_dm = True
            sw_greetd = Adw.SwitchRow(
                title="Update greetd sway config",
                subtitle="Add 'include /etc/greetd/monique-monitors.conf' to your sway-config",
                icon_name="system-lock-screen-symbolic",
            )
            sw_greetd.set_active(self._app_settings.get("update_greetd", True))
            sw_greetd.connect("notify::active", self._on_greetd_switch_changed)
            grp_dm.add(sw_greetd)

        if not has_dm:
            row_no_dm = Adw.ActionRow(
                title="No supported display manager detected",
                icon_name="dialog-information-symbolic",
            )
            row_no_dm.add_css_class("dim-label")
            grp_dm.add(row_no_dm)

        # ── Workspaces group (Niri handles migration natively) ──
        if not isinstance(self._ipc, NiriIPC):
            grp_ws = Adw.PreferencesGroup(
                title="Workspaces",
                description="Configure workspace behavior on monitor changes",
            )
            page.add(grp_ws)

            sw_migrate = Adw.SwitchRow(
                title="Migrate workspaces on monitor removal",
                subtitle="Move workspaces to primary monitor when their monitor is disabled",
            )
            sw_migrate.set_active(self._app_settings.get("migrate_workspaces", True))
            sw_migrate.connect("notify::active", self._on_migrate_switch_changed)
            grp_ws.add(sw_migrate)

        # ── Clamshell Mode group ──
        grp_clam = Adw.PreferencesGroup(
            title="Clamshell Mode",
            description="Automatically disable the internal display when external monitors are connected",
        )
        page.add(grp_clam)

        sw_clamshell = Adw.SwitchRow(
            title="Enable clamshell mode",
            subtitle="Disable laptop screen when external monitors are present (daemon)",
            icon_name="computer-symbolic",
        )
        sw_clamshell.set_active(self._app_settings.get("clamshell_mode", False))
        sw_clamshell.connect("notify::active", self._on_clamshell_switch_changed)
        grp_clam.add(sw_clamshell)

        dialog.present(self)

    def _on_sddm_switch_changed(self, row: Adw.SwitchRow, pspec) -> None:
        """Handle the SDDM switch toggle in preferences."""
        new_val = row.get_active()
        self._app_settings["update_sddm"] = new_val
        save_app_settings(self._app_settings)
        # Sync the stateful action if it exists
        action = self.lookup_action("update-sddm")
        if action:
            action.set_state(GLib.Variant.new_boolean(new_val))
        state = "enabled" if new_val else "disabled"
        self._toast(f"SDDM Xsetup update {state}")

    def _on_greetd_switch_changed(self, row: Adw.SwitchRow, pspec) -> None:
        """Handle the greetd switch toggle in preferences."""
        new_val = row.get_active()
        self._app_settings["update_greetd"] = new_val
        save_app_settings(self._app_settings)
        state = "enabled" if new_val else "disabled"
        self._toast(f"greetd monitor config update {state}")

    def _on_migrate_switch_changed(self, row: Adw.SwitchRow, pspec) -> None:
        """Handle the migrate workspaces switch toggle in preferences."""
        new_val = row.get_active()
        self._app_settings["migrate_workspaces"] = new_val
        save_app_settings(self._app_settings)
        state = "enabled" if new_val else "disabled"
        self._toast(f"Workspace migration {state}")

    def _on_port_names_switch_changed(self, row: Adw.SwitchRow, pspec) -> None:
        """Handle the port names switch toggle in preferences."""
        new_val = row.get_active()
        self._app_settings["use_port_names"] = new_val
        save_app_settings(self._app_settings)
        self._canvas.set_use_description(not new_val)
        mode = "port names" if new_val else "descriptions"
        self._toast(f"Monitor identification: {mode}")

    def _on_clamshell_switch_changed(self, row: Adw.SwitchRow, pspec) -> None:
        """Handle the clamshell mode switch toggle in preferences."""
        new_val = row.get_active()
        self._app_settings["clamshell_mode"] = new_val
        save_app_settings(self._app_settings)
        state = "enabled" if new_val else "disabled"
        self._toast(f"Clamshell mode {state}")

    def _on_sddm_toggled(self, action: Gio.SimpleAction, param) -> None:
        """Toggle the 'update SDDM Xsetup' setting (from menu action)."""
        new_val = not action.get_state().get_boolean()
        action.set_state(GLib.Variant.new_boolean(new_val))
        self._app_settings["update_sddm"] = new_val
        save_app_settings(self._app_settings)
        state = "enabled" if new_val else "disabled"
        self._toast(f"SDDM Xsetup update {state}")

    def _on_about(self, action: Gio.SimpleAction, param) -> None:
        """Show the About dialog."""
        about = Adw.AboutDialog(
            application_name="Monique",
            application_icon="com.github.monique",
            version="0.4.0",
            developer_name="Monique contributors",
            comments="MONitor Integrated QUick Editor for Hyprland and Sway",
            license_type=Gtk.License.GPL_3_0,
        )
        about.present(self)

    # ── Lid monitoring ─────────────────────────────────────────────────

    def _start_lid_monitor(self) -> None:
        """Monitor lid state via UPower D-Bus to update clamshell indicators."""
        try:
            self._dbus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
            result = self._dbus.call_sync(
                "org.freedesktop.UPower",
                "/org/freedesktop/UPower",
                "org.freedesktop.DBus.Properties",
                "Get",
                GLib.Variant("(ss)", ("org.freedesktop.UPower", "LidIsPresent")),
                GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE, -1, None,
            )
            if not result.get_child_value(0).get_variant().get_boolean():
                return

            result = self._dbus.call_sync(
                "org.freedesktop.UPower",
                "/org/freedesktop/UPower",
                "org.freedesktop.DBus.Properties",
                "Get",
                GLib.Variant("(ss)", ("org.freedesktop.UPower", "LidIsClosed")),
                GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE, -1, None,
            )
            self._lid_closed = result.get_child_value(0).get_variant().get_boolean()
            self._update_clamshell_indicators()

            def _on_signal(_conn, _sender, _path, _iface, _signal, params, _ud):
                iface_name = params.get_child_value(0).get_string()
                if iface_name != "org.freedesktop.UPower":
                    return
                changed = params.get_child_value(1)
                lid_val = changed.lookup_value("LidIsClosed", GLib.VariantType("b"))
                if lid_val is None:
                    return
                self._lid_closed = lid_val.get_boolean()
                GLib.idle_add(self._on_lid_changed)

            self._dbus.signal_subscribe(
                "org.freedesktop.UPower",
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged",
                "/org/freedesktop/UPower",
                None, Gio.DBusSignalFlags.NONE, _on_signal, None,
            )
        except Exception:
            pass

    def _on_lid_changed(self) -> bool:
        """Called on the main thread when lid state changes."""
        self._update_clamshell_indicators()
        # Reload monitors from compositor to reflect daemon changes
        GLib.timeout_add(1000, self._deferred_reload)
        return False

    def _deferred_reload(self) -> bool:
        """Reload monitor state after daemon has had time to apply."""
        self._load_current_state()
        return False

    def _update_clamshell_indicators(self) -> None:
        """Update canvas to highlight clamshell-managed monitors."""
        clamshell = self._app_settings.get("clamshell_mode", False)
        if clamshell and self._lid_closed:
            indices = {
                i for i, m in enumerate(self._monitors) if m.is_internal
            }
        else:
            indices = set()
        self._canvas.set_clamshell_indices(indices)
        # Update properties panel lock state
        idx = self._canvas.selected_index
        if 0 <= idx < len(self._monitors):
            m = self._monitors[idx]
            self._props.set_enabled_locked(clamshell and m.is_internal)

    # ── Data Loading ─────────────────────────────────────────────────

    def _load_workspace_rules_from_conf(self) -> list[WorkspaceRule]:
        """Read workspace rules from the monitors.conf file we wrote."""
        # Niri doesn't support Hyprland-style workspace rules
        if isinstance(self._ipc, NiriIPC):
            return []
        conf = hyprland_config_dir() / "monitors.conf"
        if not conf.exists():
            return []
        rules: list[WorkspaceRule] = []
        for line in conf.read_text(encoding="utf-8").splitlines():
            rule = WorkspaceRule.from_hyprland_line(line)
            if rule:
                rules.append(rule)
        return rules

    def _load_current_state(self, *, select_profile: bool = False) -> None:
        """Query compositor for current monitor state."""
        try:
            self._monitors = self._ipc.get_monitors()
            self._place_disabled(self._monitors)
            self._workspace_rules = self._load_workspace_rules_from_conf()
            self._canvas.monitors = self._monitors
            if self._monitors:
                self._canvas.selected_index = 0
                self._update_properties_for_selected()
            n_enabled = sum(1 for m in self._monitors if m.enabled)
            n_disabled = sum(1 for m in self._monitors if not m.enabled)
            parts = [f"{n_enabled} active"]
            if n_disabled:
                parts.append(f"{n_disabled} disabled")
            self._set_status(f"{len(self._monitors)} monitor(s) detected ({', '.join(parts)})")
            self._update_clamshell_indicators()
            if select_profile:
                self._select_matching_profile()
        except Exception as e:
            self._set_status(f"Error: {e}")
            self._toast(f"Cannot connect to compositor: {e}")

    @staticmethod
    def _place_disabled(monitors: list[MonitorConfig]) -> None:
        """Position disabled monitors below the active layout so they're visible."""
        enabled = [m for m in monitors if m.enabled]
        disabled = [m for m in monitors if not m.enabled]
        if not disabled:
            return

        if enabled:
            max_y = max(m.y + m.logical_height for m in enabled)
            min_x = min(m.x for m in enabled)
        else:
            max_y = 0
            min_x = 0

        gap = 200  # logical pixels gap between active and disabled section
        x_cursor = min_x
        for m in disabled:
            m.x = round(x_cursor)
            m.y = round(max_y + gap)
            x_cursor += m.logical_width + 100

    def _update_properties_for_selected(self) -> None:
        idx = self._canvas.selected_index
        if 0 <= idx < len(self._monitors):
            m = self._monitors[idx]
            names = [mon.name for mon in self._monitors]
            self._props.set_mirror_monitors(names)
            self._props.update_from_monitor(m)
            # Lock enabled switch for internal monitors when clamshell is active
            clamshell = self._app_settings.get("clamshell_mode", False)
            self._props.set_enabled_locked(clamshell and m.is_internal)
        else:
            self._props.update_from_monitor(None)

    def _select_matching_profile(self) -> None:
        """If the current monitor layout matches a saved profile, select it."""
        current_fp = sorted(m.description for m in self._monitors if m.description)
        match = self._profile_mgr.find_best_match(current_fp, self._monitors, exact_config=True)
        if match is None:
            return
        model = self._profile_dropdown.get_model()
        for i in range(model.get_n_items()):
            if model.get_string(i) == match.name:
                self._inhibit_profile_switch = True
                self._profile_dropdown.set_selected(i)
                self._current_profile_name = match.name
                self._base_profile_name = match.name
                self._workspace_rules = match.workspace_rules
                self._inhibit_profile_switch = False
                break

    def _select_profile_by_name(self, name: str) -> None:
        """Select a profile in the dropdown by name, or (Current) if empty."""
        model = self._profile_dropdown.get_model()
        if not name:
            self._inhibit_profile_switch = True
            self._profile_dropdown.set_selected(0)
            self._inhibit_profile_switch = False
            self._base_profile_name = ""
            return
        for i in range(model.get_n_items()):
            if model.get_string(i) == name:
                self._inhibit_profile_switch = True
                self._profile_dropdown.set_selected(i)
                self._inhibit_profile_switch = False
                self._base_profile_name = name
                return

    # ── Profile Management ───────────────────────────────────────────

    def _refresh_profile_list(self) -> None:
        names = self._profile_mgr.list_profiles()
        options = ["(Current)"] + names
        self._profile_dropdown.set_model(Gtk.StringList.new(options))
        self._profile_dropdown.set_selected(0)

    def _on_profile_selected(self, dropdown: Gtk.DropDown, pspec) -> None:
        if self._inhibit_profile_switch:
            return
        sel = dropdown.get_selected()
        if sel == 0:
            # Current = reload from Hyprland
            self._load_current_state()
            return
        model = dropdown.get_model()
        name = model.get_string(sel)
        profile = self._profile_mgr.load(name)
        if profile:
            self._monitors = profile.monitors
            self._place_disabled(self._monitors)
            self._workspace_rules = profile.workspace_rules
            self._current_profile_name = profile.name
            self._base_profile_name = profile.name
            self._canvas.monitors = self._monitors
            if self._monitors:
                self._canvas.selected_index = 0
                self._update_properties_for_selected()
            self._update_clamshell_indicators()
            self._set_status(f"Loaded profile: {name}")

    def _on_save_clicked(self, btn) -> None:
        dialog = Adw.AlertDialog()
        dialog.set_heading("Save Profile")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")

        # Build content: radio for existing profiles + new name entry
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(24)
        box.set_margin_end(24)

        existing = self._profile_mgr.list_profiles()
        self._save_radios: list[Gtk.CheckButton] = []
        group_leader: Gtk.CheckButton | None = None

        # Existing profiles as radio buttons
        if existing:
            label_existing = Gtk.Label(label="Overwrite existing:", xalign=0)
            label_existing.add_css_class("dim-label")
            box.append(label_existing)

            for name in existing:
                radio = Gtk.CheckButton(label=name)
                if group_leader is None:
                    group_leader = radio
                else:
                    radio.set_group(group_leader)
                self._save_radios.append(radio)
                box.append(radio)

            sep = Gtk.Separator()
            sep.set_margin_top(4)
            sep.set_margin_bottom(4)
            box.append(sep)

        # New profile option
        new_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._save_radio_new = Gtk.CheckButton(label="New:")
        if group_leader is not None:
            self._save_radio_new.set_group(group_leader)
        else:
            group_leader = self._save_radio_new
        new_box.append(self._save_radio_new)

        self._save_entry = Gtk.Entry(hexpand=True)
        self._save_entry.set_placeholder_text("Profile name")
        self._save_entry.set_text(self._generate_profile_name())
        new_box.append(self._save_entry)
        box.append(new_box)

        # Auto-select: if editing a loaded profile, pre-select it; else select "New"
        preselected = False
        if self._current_profile_name and existing:
            for radio in self._save_radios:
                if radio.get_label() == self._current_profile_name:
                    radio.set_active(True)
                    preselected = True
                    break
        if not preselected:
            self._save_radio_new.set_active(True)

        # Focus entry when "New" is selected
        self._save_radio_new.connect("toggled", self._on_save_new_toggled)
        self._save_entry.connect("changed", lambda e: self._save_radio_new.set_active(True))

        dialog.set_extra_child(box)
        dialog.connect("response", self._on_save_response)
        dialog.present(self)

    def _on_save_new_toggled(self, radio: Gtk.CheckButton) -> None:
        if radio.get_active():
            self._save_entry.grab_focus()

    def _on_save_response(self, dialog: Adw.AlertDialog, response: str) -> None:
        if response != "save":
            return

        # Determine selected name
        name = ""
        if self._save_radio_new.get_active():
            name = self._save_entry.get_text().strip()
        else:
            for radio in self._save_radios:
                if radio.get_active():
                    name = radio.get_label()
                    break

        if not name:
            self._toast("No profile name specified")
            return

        profile = Profile(
            name=name,
            monitors=list(self._monitors),
            workspace_rules=list(self._workspace_rules),
        )
        self._profile_mgr.save(profile)
        self._current_profile_name = name
        self._inhibit_profile_switch = True
        self._refresh_profile_list()
        # Select the saved profile in the dropdown
        model = self._profile_dropdown.get_model()
        for i in range(model.get_n_items()):
            if model.get_string(i) == name:
                self._profile_dropdown.set_selected(i)
                break
        self._inhibit_profile_switch = False
        self._dirty = False
        self._toast(f"Profile '{name}' saved")

    def _on_delete_profile_clicked(self, btn) -> None:
        sel = self._profile_dropdown.get_selected()
        if sel == 0:
            self._toast("Cannot delete (Current)")
            return
        model = self._profile_dropdown.get_model()
        name = model.get_string(sel)
        self._profile_mgr.delete(name)
        self._refresh_profile_list()
        self._toast(f"Profile '{name}' deleted")

    def _generate_profile_name(self) -> str:
        """Generate a default profile name from connected monitors."""
        if not self._monitors:
            return "Default"
        names = [m.model or m.name for m in self._monitors]
        return " + ".join(names)

    # ── Dirty tracking ─────────────────────────────────────────────

    def _mark_dirty(self) -> None:
        """Switch dropdown to (Current) when the user modifies anything."""
        self._dirty = True
        if self._inhibit_profile_switch:
            return
        sel = self._profile_dropdown.get_selected()
        if sel != 0:
            self._inhibit_profile_switch = True
            self._profile_dropdown.set_selected(0)
            self._inhibit_profile_switch = False
        self._current_profile_name = ""

    # ── Canvas Events ────────────────────────────────────────────────

    def _on_monitor_selected(self, canvas: MonitorCanvas, index: int) -> None:
        self._update_properties_for_selected()

    def _on_monitor_double_clicked(self, canvas: MonitorCanvas, index: int) -> None:
        self._show_osd(index)

    def _on_monitor_moved(self, canvas: MonitorCanvas, index: int) -> None:
        self._mark_dirty()
        self._update_properties_for_selected()

    def _on_property_changed(self, panel: PropertiesPanel) -> None:
        self._mark_dirty()
        self._canvas.queue_draw()

    # ── Workspace Dialog ─────────────────────────────────────────────

    def _on_workspaces_clicked(self, btn) -> None:
        names = [m.name for m in self._monitors]
        descs = [m.description for m in self._monitors]
        enabled = [m.enabled for m in self._monitors]
        dialog = WorkspacePanel(
            monitor_names=names,
            monitor_descriptions=descs,
            monitor_enabled=enabled,
            application=self.get_application(),
        )
        dialog.set_rules(self._workspace_rules)
        dialog.connect("rules-changed", self._on_workspace_rules_changed)
        dialog.set_transient_for(self)
        dialog.present()

    def _on_workspace_rules_changed(self, panel: WorkspacePanel) -> None:
        self._workspace_rules = panel.get_rules()
        self._mark_dirty()

    # ── Detect ───────────────────────────────────────────────────────

    def _on_detect_clicked(self, btn) -> None:
        self._load_current_state()

    # ── Apply ────────────────────────────────────────────────────────

    def _on_apply_clicked(self, btn) -> None:
        """Apply the current configuration with backup and confirmation."""
        profile = Profile(
            name=self._current_profile_name or "applied",
            monitors=list(self._monitors),
            workspace_rules=list(self._workspace_rules),
        )

        # Determine config path based on compositor
        if isinstance(self._ipc, NiriIPC):
            monitors_conf = niri_config_dir() / "monitors.kdl"
        else:
            monitors_conf = hyprland_config_dir() / "monitors.conf"

        # Snapshot actual compositor state before applying (for revert)
        pre_monitors = self._ipc.get_monitors()
        self._place_disabled(pre_monitors)
        self._pre_apply_monitors = pre_monitors
        self._pre_apply_profile_name = self._base_profile_name
        self._pre_apply_workspace_rules = list(self._workspace_rules)
        self._ws_snapshot = self._ipc.get_workspaces()
        self._migrated_workspaces: list[tuple[str, str]] = []

        # Backup
        backup_file(monitors_conf)

        try:
            update_sddm = self._app_settings.get("update_sddm", True)
            update_greetd = self._app_settings.get("update_greetd", True)
            use_desc = not self._app_settings.get("use_port_names", False)
            self._ipc.apply_profile(
                profile, update_sddm=update_sddm, update_greetd=update_greetd,
                use_description=use_desc,
            )
            self._set_status("Configuration applied")
        except Exception as e:
            self._toast(f"Apply failed: {e}")
            restore_backup(monitors_conf)
            return

        # Migrate orphaned workspaces if setting is on (Niri handles this natively)
        if not isinstance(self._ipc, NiriIPC) and self._app_settings.get("migrate_workspaces", True):
            self._migrate_orphaned_workspaces(profile)

        # Show confirmation dialog with countdown
        self._show_confirm_dialog(monitors_conf)

    def _migrate_orphaned_workspaces(self, profile: Profile) -> None:
        """Move workspaces from disabled/removed monitors to the primary monitor."""
        enabled_names = {m.name for m in profile.monitors if m.enabled}
        if not enabled_names:
            return

        # Primary = first enabled monitor in profile
        primary = next(m.name for m in profile.monitors if m.enabled)

        self._migrated_workspaces = []
        for ws in self._ws_snapshot:
            ws_monitor = ws.get("monitor", "")
            ws_name = str(ws.get("name", ws.get("id", "")))
            if ws_monitor and ws_monitor not in enabled_names:
                try:
                    self._ipc.move_workspace_to_monitor(ws_name, primary)
                    self._migrated_workspaces.append((ws_name, ws_monitor))
                except Exception:
                    pass

    def _show_confirm_dialog(self, conf_path) -> None:
        self._confirm_remaining = CONFIRM_TIMEOUT
        dialog = Adw.AlertDialog()
        dialog.set_heading("Keep Settings?")
        dialog.set_body(f"Reverting in {self._confirm_remaining}s if not confirmed...")
        dialog.add_response("revert", "Revert")
        dialog.set_response_appearance("revert", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.add_response("keep", "Keep Settings")
        dialog.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("keep")
        dialog.set_close_response("revert")

        self._confirm_dialog = dialog
        self._confirm_conf_path = conf_path

        # Start countdown
        self._confirm_timer_id = GLib.timeout_add(1000, self._confirm_tick)
        dialog.connect("response", self._on_confirm_response)
        dialog.present(self)

    def _confirm_tick(self) -> bool:
        self._confirm_remaining -= 1
        if self._confirm_remaining <= 0:
            # Auto-revert
            self._confirm_dialog.force_close()
            self._do_revert()
            return False
        self._confirm_dialog.set_body(f"Reverting in {self._confirm_remaining}s if not confirmed...")
        return True

    def _on_confirm_response(self, dialog: Adw.AlertDialog, response: str) -> None:
        if self._confirm_timer_id:
            GLib.source_remove(self._confirm_timer_id)
            self._confirm_timer_id = 0

        if response == "keep":
            # Remove backup
            bak = self._confirm_conf_path.with_suffix(self._confirm_conf_path.suffix + ".bak")
            if bak.exists():
                bak.unlink()
            self._migrated_workspaces = []
            self._base_profile_name = self._current_profile_name
            self._toast("Settings kept")
        else:
            self._do_revert()

    def _do_revert(self) -> None:
        # Restore migrated workspaces to their original monitors
        for ws_name, original_monitor in self._migrated_workspaces:
            try:
                self._ipc.move_workspace_to_monitor(ws_name, original_monitor)
            except Exception:
                pass
        self._migrated_workspaces = []

        if restore_backup(self._confirm_conf_path):
            try:
                self._ipc.reload()
            except Exception as e:
                self._toast(f"Revert reload failed: {e}")
                return

            # Restore pre-apply GUI state directly (no need to re-query compositor)
            self._monitors = self._pre_apply_monitors
            self._current_profile_name = self._pre_apply_profile_name
            self._workspace_rules = self._pre_apply_workspace_rules
            self._canvas.monitors = self._monitors
            if self._monitors:
                self._canvas.selected_index = 0
                self._update_properties_for_selected()
            self._update_clamshell_indicators()
            # Select the pre-apply profile in dropdown by name
            self._select_profile_by_name(self._pre_apply_profile_name)
            self._toast("Settings reverted")
        else:
            self._toast("No backup to revert")

    # ── OSD ───────────────────────────────────────────────────────────

    def _show_osd(self, index: int) -> None:
        """Show an OSD overlay on the physical monitor corresponding to index."""
        # Dismiss previous
        if self._osd is not None:
            self._osd.dismiss()
            self._osd = None

        if index < 0 or index >= len(self._monitors):
            return

        mon = self._monitors[index]
        gdk_mon = self._find_gdk_monitor(mon.name)
        if gdk_mon is None:
            return

        self._osd = MonitorOSD(self.get_application(), gdk_mon, mon.name)
        self._osd.show_timed()

        # Re-focus the main window so the OSD doesn't steal it
        GLib.idle_add(self.present)

    def _find_gdk_monitor(self, connector: str) -> Gdk.Monitor | None:
        """Find the Gdk.Monitor matching a connector name like 'DP-1'."""
        display = Gdk.Display.get_default()
        if display is None:
            return None
        monitors = display.get_monitors()
        for i in range(monitors.get_n_items()):
            gdk_mon = monitors.get_item(i)
            if gdk_mon.get_connector() == connector:
                return gdk_mon
        return None

    # ── Close ─────────────────────────────────────────────────────────

    def _on_close_request(self, window: Adw.ApplicationWindow) -> bool:
        if not self._dirty:
            return False  # allow close

        dialog = Adw.AlertDialog()
        dialog.set_heading("Unsaved Changes")
        dialog.set_body("Save changes before closing?")
        dialog.add_response("discard", "Discard")
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_close_dialog_response)
        dialog.present(self)
        return True  # block close for now

    def _on_close_dialog_response(self, dialog: Adw.AlertDialog, response: str) -> None:
        if response == "cancel":
            return
        if response == "save":
            self._on_save_clicked(None)
            # Close after save dialog completes (dirty will be False)
            return
        # discard
        self._dirty = False
        self.close()

    # ── Helpers ──────────────────────────────────────────────────────

    def _set_status(self, text: str) -> None:
        self._status.set_text(text)

    def _toast(self, message: str) -> None:
        toast = Adw.Toast(title=message, timeout=3)
        self._toast_overlay.add_toast(toast)
