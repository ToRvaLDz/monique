"""Properties panel for selected monitor using Adw.PreferencesPage."""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, GObject

from .models import (
    MonitorConfig, ResolutionMode, PositionMode, ScaleMode,
    Transform, VRR,
)


def _fix_spin_icons(widget: Gtk.Widget) -> None:
    """Replace SpinRow +/- button icons with text labels after a delay."""
    _LABELS = {
        "list-add-symbolic": "+",
        "list-remove-symbolic": "\u2212",
        "value-increase-symbolic": "+",
        "value-decrease-symbolic": "\u2212",
    }

    def _do_fix():
        _walk(widget)
        return False  # don't repeat

    def _walk(w):
        child = w.get_first_child()
        while child:
            next_s = child.get_next_sibling()
            if isinstance(child, Gtk.Button):
                icon = child.get_icon_name() or ""
                if not icon:
                    bc = child.get_child()
                    if isinstance(bc, Gtk.Image):
                        icon = bc.get_icon_name() or ""
                if icon in _LABELS:
                    child.set_icon_name("")
                    lbl = Gtk.Label(label=_LABELS[icon])
                    lbl.add_css_class("heading")
                    child.set_child(lbl)
            # Always recurse into all children
            _walk(child)
            child = next_s

    GLib.timeout_add(150, _do_fix)


class PropertiesPanel(Adw.PreferencesPage):
    """Side panel showing properties of the selected monitor."""

    __gtype_name__ = "PropertiesPanel"

    __gsignals__ = {
        "property-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self) -> None:
        super().__init__()
        self._monitor: MonitorConfig | None = None
        self._building = False

        self._build_ui()

    def _build_ui(self) -> None:
        # ── Monitor Info ─────────────────────────────────────────────
        grp_info = Adw.PreferencesGroup(title="Monitor")
        self.add(grp_info)

        self._row_name = Adw.ActionRow(title="Name", icon_name="video-display-symbolic")
        self._lbl_name = Gtk.Label(label="—", xalign=1)
        self._lbl_name.add_css_class("dim-label")
        self._row_name.add_suffix(self._lbl_name)
        grp_info.add(self._row_name)

        self._row_desc = Adw.ActionRow(title="Description", icon_name="text-x-generic-symbolic")
        self._lbl_desc = Gtk.Label(label="—", xalign=1, wrap=True, max_width_chars=24)
        self._lbl_desc.add_css_class("dim-label")
        self._row_desc.add_suffix(self._lbl_desc)
        grp_info.add(self._row_desc)

        self._sw_enabled = Adw.SwitchRow(title="Enabled", icon_name="system-shutdown-symbolic")
        self._sw_enabled.connect("notify::active", self._on_changed)
        grp_info.add(self._sw_enabled)
        self._enabled_locked = False

        # ── Resolution ───────────────────────────────────────────────
        grp_res = Adw.PreferencesGroup(title="Resolution")
        self.add(grp_res)

        self._combo_res_mode = Adw.ComboRow(title="Mode", icon_name="preferences-other-symbolic")
        modes = Gtk.StringList.new([m.value for m in ResolutionMode])
        self._combo_res_mode.set_model(modes)
        self._combo_res_mode.connect("notify::selected", self._on_res_mode_changed)
        grp_res.add(self._combo_res_mode)

        self._combo_resolution = Adw.ComboRow(title="Resolution", icon_name="preferences-desktop-display-symbolic")
        self._combo_resolution.connect("notify::selected", self._on_resolution_changed)
        grp_res.add(self._combo_resolution)

        self._spin_width = Adw.SpinRow.new_with_range(320, 15360, 1)
        self._spin_width.set_title("Width")
        self._spin_width.connect("notify::value", self._on_changed)
        grp_res.add(self._spin_width)
        _fix_spin_icons(self._spin_width)

        self._spin_height = Adw.SpinRow.new_with_range(200, 8640, 1)
        self._spin_height.set_title("Height")
        self._spin_height.connect("notify::value", self._on_changed)
        grp_res.add(self._spin_height)
        _fix_spin_icons(self._spin_height)

        self._spin_refresh = Adw.SpinRow.new_with_range(1, 600, 0.01)
        self._spin_refresh.set_title("Refresh Rate")
        self._spin_refresh.set_digits(2)
        self._spin_refresh.connect("notify::value", self._on_changed)
        grp_res.add(self._spin_refresh)
        _fix_spin_icons(self._spin_refresh)

        # ── Position ─────────────────────────────────────────────────
        grp_pos = Adw.PreferencesGroup(title="Position")
        self.add(grp_pos)

        self._combo_pos_mode = Adw.ComboRow(title="Mode", icon_name="preferences-other-symbolic")
        pos_modes = Gtk.StringList.new([m.value for m in PositionMode])
        self._combo_pos_mode.set_model(pos_modes)
        self._combo_pos_mode.connect("notify::selected", self._on_pos_mode_changed)
        grp_pos.add(self._combo_pos_mode)

        self._spin_x = Adw.SpinRow.new_with_range(-32768, 32768, 1)
        self._spin_x.set_title("X")
        self._spin_x.connect("notify::value", self._on_changed)
        grp_pos.add(self._spin_x)
        _fix_spin_icons(self._spin_x)

        self._spin_y = Adw.SpinRow.new_with_range(-32768, 32768, 1)
        self._spin_y.set_title("Y")
        self._spin_y.connect("notify::value", self._on_changed)
        grp_pos.add(self._spin_y)
        _fix_spin_icons(self._spin_y)

        # ── Scale & Transform ────────────────────────────────────────
        grp_scale = Adw.PreferencesGroup(title="Scale &amp; Transform")
        self.add(grp_scale)

        self._combo_scale_mode = Adw.ComboRow(title="Scale Mode")
        scale_modes = Gtk.StringList.new([m.value for m in ScaleMode])
        self._combo_scale_mode.set_model(scale_modes)
        self._combo_scale_mode.connect("notify::selected", self._on_scale_mode_changed)
        grp_scale.add(self._combo_scale_mode)

        self._spin_scale = Adw.SpinRow.new_with_range(0.1, 10.0, 0.05)
        self._spin_scale.set_title("Scale")
        self._spin_scale.set_digits(2)
        self._spin_scale.connect("notify::value", self._on_changed)
        grp_scale.add(self._spin_scale)
        _fix_spin_icons(self._spin_scale)

        self._combo_transform = Adw.ComboRow(title="Transform", icon_name="object-rotate-right-symbolic")
        transforms = Gtk.StringList.new([t.label for t in Transform])
        self._combo_transform.set_model(transforms)
        self._combo_transform.connect("notify::selected", self._on_changed)
        grp_scale.add(self._combo_transform)

        # ── Advanced ─────────────────────────────────────────────────
        grp_adv = Adw.PreferencesGroup(title="Advanced")
        self.add(grp_adv)

        self._combo_mirror = Adw.ComboRow(title="Mirror Of", icon_name="edit-copy-symbolic")
        self._combo_mirror.connect("notify::selected", self._on_changed)
        grp_adv.add(self._combo_mirror)

        self._combo_bitdepth = Adw.ComboRow(title="Bit Depth", icon_name="color-select-symbolic")
        self._combo_bitdepth.set_model(Gtk.StringList.new(["8", "10"]))
        self._combo_bitdepth.connect("notify::selected", self._on_changed)
        grp_adv.add(self._combo_bitdepth)

        self._combo_vrr = Adw.ComboRow(title="VRR", icon_name="display-brightness-symbolic")
        self._combo_vrr.set_model(Gtk.StringList.new(["Off", "On", "Fullscreen only"]))
        self._combo_vrr.connect("notify::selected", self._on_changed)
        grp_adv.add(self._combo_vrr)

        self._combo_cm = Adw.ComboRow(title="Color Management", icon_name="applications-graphics-symbolic")
        cm_options = ["None", "auto", "srgb", "dcip3", "dp3", "adobe", "wide", "edid", "hdr", "hdredid"]
        self._combo_cm.set_model(Gtk.StringList.new(cm_options))
        self._combo_cm.connect("notify::selected", self._on_changed)
        grp_adv.add(self._combo_cm)

        self._spin_sdr_bright = Adw.SpinRow.new_with_range(0.0, 5.0, 0.05)
        self._spin_sdr_bright.set_title("SDR Brightness")
        self._spin_sdr_bright.set_digits(2)
        self._spin_sdr_bright.connect("notify::value", self._on_changed)
        grp_adv.add(self._spin_sdr_bright)
        _fix_spin_icons(self._spin_sdr_bright)

        self._spin_sdr_sat = Adw.SpinRow.new_with_range(0.0, 5.0, 0.05)
        self._spin_sdr_sat.set_title("SDR Saturation")
        self._spin_sdr_sat.set_digits(2)
        self._spin_sdr_sat.connect("notify::value", self._on_changed)
        grp_adv.add(self._spin_sdr_sat)
        _fix_spin_icons(self._spin_sdr_sat)

        # ── Reserved Area ────────────────────────────────────────────
        grp_reserved = Adw.PreferencesGroup(title="Reserved Area")
        self.add(grp_reserved)

        self._spin_res_top = Adw.SpinRow.new_with_range(0, 500, 1)
        self._spin_res_top.set_title("Top")
        self._spin_res_top.connect("notify::value", self._on_changed)
        grp_reserved.add(self._spin_res_top)
        _fix_spin_icons(self._spin_res_top)

        self._spin_res_bottom = Adw.SpinRow.new_with_range(0, 500, 1)
        self._spin_res_bottom.set_title("Bottom")
        self._spin_res_bottom.connect("notify::value", self._on_changed)
        grp_reserved.add(self._spin_res_bottom)
        _fix_spin_icons(self._spin_res_bottom)

        self._spin_res_left = Adw.SpinRow.new_with_range(0, 500, 1)
        self._spin_res_left.set_title("Left")
        self._spin_res_left.connect("notify::value", self._on_changed)
        grp_reserved.add(self._spin_res_left)
        _fix_spin_icons(self._spin_res_left)

        self._spin_res_right = Adw.SpinRow.new_with_range(0, 500, 1)
        self._spin_res_right.set_title("Right")
        self._spin_res_right.connect("notify::value", self._on_changed)
        grp_reserved.add(self._spin_res_right)
        _fix_spin_icons(self._spin_res_right)

    def set_enabled_locked(self, locked: bool) -> None:
        """Lock the Enabled switch (e.g. for clamshell-managed monitors)."""
        self._enabled_locked = locked
        self._sw_enabled.set_sensitive(not locked)
        self._sw_enabled.set_subtitle(
            "Managed by clamshell mode" if locked else "",
        )

    def set_mirror_monitors(self, names: list[str]) -> None:
        """Update the mirror dropdown with available monitor names."""
        self._building = True
        options = ["None"] + [n for n in names if n != (self._monitor.name if self._monitor else "")]
        self._combo_mirror.set_model(Gtk.StringList.new(options))
        self._building = False

    def update_from_monitor(self, monitor: MonitorConfig | None) -> None:
        """Populate all fields from a MonitorConfig."""
        self._building = True
        self._monitor = monitor

        if monitor is None:
            self.set_sensitive(False)
            self._building = False
            return

        self.set_sensitive(True)

        self._lbl_name.set_label(monitor.name or "—")
        self._lbl_desc.set_label(monitor.description or "—")
        self._sw_enabled.set_active(monitor.enabled)
        self._sw_enabled.set_sensitive(not self._enabled_locked)

        # Resolution mode
        res_modes = [m.value for m in ResolutionMode]
        idx = res_modes.index(monitor.resolution_mode.value) if monitor.resolution_mode.value in res_modes else 0
        self._combo_res_mode.set_selected(idx)

        # Available modes dropdown
        if monitor.available_modes:
            self._combo_resolution.set_model(Gtk.StringList.new(monitor.available_modes))
            # Find closest match
            for i, mode in enumerate(monitor.available_modes):
                if mode.startswith(f"{monitor.width}x{monitor.height}"):
                    self._combo_resolution.set_selected(i)
                    break
        else:
            self._combo_resolution.set_model(Gtk.StringList.new([]))

        self._spin_width.set_value(monitor.width)
        self._spin_height.set_value(monitor.height)
        self._spin_refresh.set_value(monitor.refresh_rate)

        # Show/hide manual fields based on mode
        is_explicit = monitor.resolution_mode == ResolutionMode.EXPLICIT
        self._combo_resolution.set_visible(is_explicit)
        self._spin_width.set_visible(is_explicit)
        self._spin_height.set_visible(is_explicit)
        self._spin_refresh.set_visible(is_explicit)

        # Position mode
        pos_modes = [m.value for m in PositionMode]
        idx = pos_modes.index(monitor.position_mode.value) if monitor.position_mode.value in pos_modes else 0
        self._combo_pos_mode.set_selected(idx)

        self._spin_x.set_value(monitor.x)
        self._spin_y.set_value(monitor.y)
        is_explicit_pos = monitor.position_mode == PositionMode.EXPLICIT
        self._spin_x.set_visible(is_explicit_pos)
        self._spin_y.set_visible(is_explicit_pos)

        # Scale
        scale_modes = [m.value for m in ScaleMode]
        idx = scale_modes.index(monitor.scale_mode.value) if monitor.scale_mode.value in scale_modes else 0
        self._combo_scale_mode.set_selected(idx)
        self._spin_scale.set_value(monitor.scale)
        self._spin_scale.set_visible(monitor.scale_mode == ScaleMode.EXPLICIT)

        # Transform
        self._combo_transform.set_selected(monitor.transform.value)

        # Mirror
        model = self._combo_mirror.get_model()
        if model:
            if monitor.mirror_of:
                for i in range(model.get_n_items()):
                    if model.get_string(i) == monitor.mirror_of:
                        self._combo_mirror.set_selected(i)
                        break
            else:
                self._combo_mirror.set_selected(0)

        # Advanced
        self._combo_bitdepth.set_selected(0 if monitor.bitdepth == 8 else 1)
        self._combo_vrr.set_selected(monitor.vrr.value)

        cm_options = ["None", "auto", "srgb", "dcip3", "dp3", "adobe", "wide", "edid", "hdr", "hdredid"]
        cm_val = monitor.color_management or "None"
        idx = cm_options.index(cm_val) if cm_val in cm_options else 0
        self._combo_cm.set_selected(idx)

        self._spin_sdr_bright.set_value(monitor.sdr_brightness)
        self._spin_sdr_sat.set_value(monitor.sdr_saturation)

        # Reserved
        self._spin_res_top.set_value(monitor.reserved_top)
        self._spin_res_bottom.set_value(monitor.reserved_bottom)
        self._spin_res_left.set_value(monitor.reserved_left)
        self._spin_res_right.set_value(monitor.reserved_right)

        self._building = False

    def _apply_to_monitor(self) -> None:
        """Write current UI values back to the MonitorConfig."""
        m = self._monitor
        if m is None:
            return

        m.enabled = self._sw_enabled.get_active()

        # Resolution mode
        res_modes = list(ResolutionMode)
        m.resolution_mode = res_modes[self._combo_res_mode.get_selected()]

        if m.resolution_mode == ResolutionMode.EXPLICIT:
            # Check if a mode was selected from dropdown
            sel = self._combo_resolution.get_selected()
            model = self._combo_resolution.get_model()
            if model and sel < model.get_n_items() and sel != Gtk.INVALID_LIST_POSITION:
                mode_str = model.get_string(sel)
                # Parse "WxH@R" or "WxH@R Hz"
                self._parse_mode_string(m, mode_str)
            else:
                m.width = int(self._spin_width.get_value())
                m.height = int(self._spin_height.get_value())
                m.refresh_rate = round(self._spin_refresh.get_value(), 2)

        # Position
        pos_modes = list(PositionMode)
        m.position_mode = pos_modes[self._combo_pos_mode.get_selected()]
        if m.position_mode == PositionMode.EXPLICIT:
            m.x = int(self._spin_x.get_value())
            m.y = int(self._spin_y.get_value())

        # Scale
        scale_modes = list(ScaleMode)
        m.scale_mode = scale_modes[self._combo_scale_mode.get_selected()]
        if m.scale_mode == ScaleMode.EXPLICIT:
            m.scale = round(self._spin_scale.get_value(), 2)

        # Transform
        m.transform = Transform(self._combo_transform.get_selected())

        # Mirror
        mirror_model = self._combo_mirror.get_model()
        if mirror_model:
            sel = self._combo_mirror.get_selected()
            if sel == 0 or sel == Gtk.INVALID_LIST_POSITION:
                m.mirror_of = ""
            else:
                m.mirror_of = mirror_model.get_string(sel)

        # Advanced
        m.bitdepth = 10 if self._combo_bitdepth.get_selected() == 1 else 8
        m.vrr = VRR(self._combo_vrr.get_selected())

        cm_options = ["", "auto", "srgb", "dcip3", "dp3", "adobe", "wide", "edid", "hdr", "hdredid"]
        m.color_management = cm_options[self._combo_cm.get_selected()]

        m.sdr_brightness = round(self._spin_sdr_bright.get_value(), 2)
        m.sdr_saturation = round(self._spin_sdr_sat.get_value(), 2)

        # Reserved
        m.reserved_top = int(self._spin_res_top.get_value())
        m.reserved_bottom = int(self._spin_res_bottom.get_value())
        m.reserved_left = int(self._spin_res_left.get_value())
        m.reserved_right = int(self._spin_res_right.get_value())

    def _parse_mode_string(self, m: MonitorConfig, mode_str: str) -> None:
        """Parse a mode string like '1920x1080@60.00' into monitor fields."""
        try:
            res_part, rate_part = mode_str.split("@")
            w, h = res_part.split("x")
            m.width = int(w)
            m.height = int(h)
            # Remove trailing " Hz" if present
            rate_part = rate_part.replace("Hz", "").strip()
            m.refresh_rate = round(float(rate_part), 2)
        except (ValueError, IndexError):
            pass

    def _on_changed(self, *args) -> None:
        if self._building or self._monitor is None:
            return
        self._apply_to_monitor()
        self.emit("property-changed")

    def _on_res_mode_changed(self, *args) -> None:
        if self._building:
            return
        res_modes = list(ResolutionMode)
        mode = res_modes[self._combo_res_mode.get_selected()]
        is_explicit = mode == ResolutionMode.EXPLICIT
        self._combo_resolution.set_visible(is_explicit)
        self._spin_width.set_visible(is_explicit)
        self._spin_height.set_visible(is_explicit)
        self._spin_refresh.set_visible(is_explicit)
        self._on_changed()

    def _on_resolution_changed(self, *args) -> None:
        if self._building or self._monitor is None:
            return
        sel = self._combo_resolution.get_selected()
        model = self._combo_resolution.get_model()
        if model and sel < model.get_n_items() and sel != Gtk.INVALID_LIST_POSITION:
            mode_str = model.get_string(sel)
            self._building = True
            self._parse_mode_string(self._monitor, mode_str)
            self._spin_width.set_value(self._monitor.width)
            self._spin_height.set_value(self._monitor.height)
            self._spin_refresh.set_value(self._monitor.refresh_rate)
            self._building = False
            self._on_changed()

    def _on_pos_mode_changed(self, *args) -> None:
        if self._building:
            return
        pos_modes = list(PositionMode)
        mode = pos_modes[self._combo_pos_mode.get_selected()]
        is_explicit = mode == PositionMode.EXPLICIT
        self._spin_x.set_visible(is_explicit)
        self._spin_y.set_visible(is_explicit)
        self._on_changed()

    def _on_scale_mode_changed(self, *args) -> None:
        if self._building:
            return
        scale_modes = list(ScaleMode)
        mode = scale_modes[self._combo_scale_mode.get_selected()]
        self._spin_scale.set_visible(mode == ScaleMode.EXPLICIT)
        self._on_changed()
