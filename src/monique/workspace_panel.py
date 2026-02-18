"""Workspace assignment dialog."""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gdk, Adw, GLib, GObject

from .models import WorkspaceRule


class WorkspacePanel(Adw.Dialog):
    """Dialog for managing workspace-to-monitor assignments."""

    __gtype_name__ = "WorkspacePanel"

    __gsignals__ = {
        "rules-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(
        self,
        monitor_names: list[str] | None = None,
        monitor_descriptions: list[str] | None = None,
        monitor_enabled: list[bool] | None = None,
    ) -> None:
        super().__init__()
        self._rules: list[WorkspaceRule] = []
        self._monitor_names = monitor_names or []
        self._monitor_descriptions = monitor_descriptions or []
        self._drag_index: int = -1
        self._monitor_enabled = monitor_enabled or [True] * len(self._monitor_names)
        self._building = False

        self.set_title("Workspace Rules")
        # Size to ~35% width, ~70% height of primary monitor
        w, h = 500, 600
        display = Gdk.Display.get_default()
        if display:
            mons = display.get_monitors()
            if mons.get_n_items() > 0:
                geom = mons.get_item(0).get_geometry()
                w = int(geom.width * 0.26)
                h = int(geom.height * 0.7)
        self.set_content_width(w)
        self.set_content_height(h)

        self._build_ui()

    # -- Helpers --------------------------------------------------------------

    @staticmethod
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
                # Check if this is a button with a spin icon
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

    # -- UI building ----------------------------------------------------------

    def _build_ui(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header bar
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        header.set_show_start_title_buttons(False)

        btn_add = Gtk.Button()
        btn_add.set_child(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        btn_add.set_tooltip_text("Add rule")
        btn_add.connect("clicked", self._on_add_clicked)
        header.pack_start(btn_add)

        btn_quick = Gtk.Button()
        btn_quick.set_child(Gtk.Image.new_from_icon_name("document-new-symbolic"))
        btn_quick.set_tooltip_text("Quick Setup")
        btn_quick.connect("clicked", self._on_quick_setup_clicked)
        header.pack_start(btn_quick)

        box.append(header)

        # Stack to switch between empty state and rules list
        self._stack = Gtk.Stack()
        self._stack.set_vexpand(True)
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        # Empty status page
        self._status_page = Adw.StatusPage()
        self._status_page.set_icon_name("view-grid-symbolic")
        self._status_page.set_title("No Workspace Rules")
        self._status_page.set_description(
            "Configure workspace assignments to monitors"
        )
        btn_setup = Gtk.Button(label="Quick Setup")
        btn_setup.add_css_class("suggested-action")
        btn_setup.add_css_class("pill")
        btn_setup.set_halign(Gtk.Align.CENTER)
        btn_setup.connect("clicked", self._on_quick_setup_clicked)
        self._status_page.set_child(btn_setup)
        self._stack.add_named(self._status_page, "empty")

        # Scrolled content with rules list
        scroll = Gtk.ScrolledWindow(vexpand=True)
        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list_box.add_css_class("boxed-list")
        self._list_box.set_margin_start(12)
        self._list_box.set_margin_end(12)
        self._list_box.set_margin_top(12)
        self._list_box.set_margin_bottom(12)
        scroll.set_child(self._list_box)
        self._stack.add_named(scroll, "rules")

        box.append(self._stack)
        self.set_child(box)

        self._update_stack_visible()

    def _update_stack_visible(self) -> None:
        if self._rules:
            self._stack.set_visible_child_name("rules")
        else:
            self._stack.set_visible_child_name("empty")

    # -- Rules list -----------------------------------------------------------

    def set_rules(self, rules: list[WorkspaceRule]) -> None:
        """Populate the dialog with existing rules."""
        self._rules = [WorkspaceRule(**r.__dict__) for r in rules]  # copy
        self._rebuild_list()

    def get_rules(self) -> list[WorkspaceRule]:
        """Return current rules."""
        return list(self._rules)

    def _rebuild_list(self) -> None:
        self._building = True
        while True:
            row = self._list_box.get_row_at_index(0)
            if row is None:
                break
            self._list_box.remove(row)

        for i, rule in enumerate(self._rules):
            row = self._create_rule_row(i, rule)
            self._list_box.append(row)

        self._building = False
        self._update_stack_visible()

    # -- Monitor dropdown helpers ---------------------------------------------

    def _monitor_full_options(self) -> list[str]:
        """Full description strings for popup list."""
        options = ["None"]
        for i, name in enumerate(self._monitor_names):
            desc = (
                self._monitor_descriptions[i]
                if i < len(self._monitor_descriptions)
                   and self._monitor_descriptions[i]
                else ""
            )
            options.append(f"{desc} ({name})" if desc else name)
        return options

    def _monitor_compact_options(self) -> list[str]:
        """Compact strings for button display."""
        options = ["None"]
        for i, name in enumerate(self._monitor_names):
            desc = (
                self._monitor_descriptions[i]
                if i < len(self._monitor_descriptions)
                   and self._monitor_descriptions[i]
                else ""
            )
            if desc:
                short = desc[:10].rstrip()
                ellipsis = "\u2026" if len(desc) > 10 else ""
                options.append(f"{short}{ellipsis} ({name})")
            else:
                options.append(name)
        return options

    def _make_monitor_combo(self) -> Gtk.DropDown:
        """Build a DropDown with compact button and full-description popup."""
        full = self._monitor_full_options()
        compact = self._monitor_compact_options()
        model = Gtk.StringList.new(full)

        # Factory for the button area (compact)
        btn_factory = Gtk.SignalListItemFactory()

        def setup_btn(factory, list_item):
            lbl = Gtk.Label(xalign=0, ellipsize=2)  # END
            list_item.set_child(lbl)

        def bind_btn(factory, list_item):
            lbl = list_item.get_child()
            pos = list_item.get_position()
            lbl.set_label(compact[pos] if pos < len(compact) else "")

        btn_factory.connect("setup", setup_btn)
        btn_factory.connect("bind", bind_btn)

        # Factory for the popup list (full description)
        list_factory = Gtk.SignalListItemFactory()

        def setup_list(factory, list_item):
            lbl = Gtk.Label(xalign=0)
            list_item.set_child(lbl)

        def bind_list(factory, list_item):
            lbl = list_item.get_child()
            lbl.set_label(list_item.get_item().get_string())

        list_factory.connect("setup", setup_list)
        list_factory.connect("bind", bind_list)

        combo = Gtk.DropDown(model=model)
        combo.set_factory(btn_factory)
        combo.set_list_factory(list_factory)
        return combo

    # -- Rule row -------------------------------------------------------------

    def _create_rule_row(self, index: int, rule: WorkspaceRule) -> Adw.ExpanderRow:
        expander = Adw.ExpanderRow()

        # Row counter (fixed, 1-based)
        counter_label = Gtk.Label(
            label=str(index + 1),
            width_chars=3,
            xalign=0.5,
            valign=Gtk.Align.CENTER,
        )
        counter_label.add_css_class("dim-label")
        expander.add_prefix(counter_label)

        # Suffixes are rendered right-to-left: first added = rightmost.
        # Visual order: [dropdown] [star] [pin] [delete]

        # Delete button (rightmost)
        btn_del = Gtk.Button()
        btn_del.set_child(Gtk.Image.new_from_icon_name("edit-delete-symbolic"))
        btn_del.set_valign(Gtk.Align.CENTER)
        btn_del.add_css_class("destructive-action")
        btn_del.add_css_class("flat")
        btn_del.connect("clicked", self._on_delete_clicked, index)
        expander.add_suffix(btn_del)

        # Persistent toggle (pin)
        btn_persistent = Gtk.ToggleButton()
        btn_persistent.set_child(Gtk.Image.new_from_icon_name("view-pin-symbolic"))
        btn_persistent.set_active(rule.persistent)
        btn_persistent.set_valign(Gtk.Align.CENTER)
        btn_persistent.add_css_class("flat")
        if rule.persistent:
            btn_persistent.add_css_class("accent")
        btn_persistent.set_tooltip_text("Persistent workspace")
        btn_persistent.connect("toggled", self._on_persistent_toggled, index)
        expander.add_suffix(btn_persistent)

        # Default toggle (star)
        btn_default = Gtk.ToggleButton()
        btn_default.set_child(Gtk.Image.new_from_icon_name("starred-symbolic"))
        btn_default.set_active(rule.default)
        btn_default.set_valign(Gtk.Align.CENTER)
        btn_default.add_css_class("flat")
        if rule.default:
            btn_default.add_css_class("warning")
        btn_default.set_tooltip_text("Default workspace for this monitor")
        btn_default.connect("toggled", self._on_default_toggled, index)
        expander.add_suffix(btn_default)

        # Monitor combo (leftmost suffix)
        monitor_combo = self._make_monitor_combo()
        if rule.monitor in self._monitor_names:
            monitor_combo.set_selected(self._monitor_names.index(rule.monitor) + 1)
        else:
            monitor_combo.set_selected(0)
        monitor_combo.set_valign(Gtk.Align.CENTER)
        monitor_combo.set_size_request(240, -1)
        monitor_combo.connect("notify::selected", self._on_monitor_changed, index)
        expander.add_suffix(monitor_combo)

        # Title: "Workspace N" if numeric, just the name if custom
        expander.set_title(self._ws_title(rule.workspace))

        # -- Rows inside expander --

        # Workspace entry for editing
        entry_ws = Adw.EntryRow(title="Workspace name / number")
        entry_ws.set_text(rule.workspace)
        entry_ws.connect("changed", self._on_ws_changed, index, expander)
        expander.add_row(entry_ws)

        spin_rounding = Adw.SpinRow.new_with_range(-1, 1, 1)
        spin_rounding.set_title("Rounding (-1=unset)")
        spin_rounding.add_prefix(Gtk.Image.new_from_icon_name("draw-circle-symbolic"))
        spin_rounding.set_value(rule.rounding)
        spin_rounding.connect("notify::value", self._on_spin_changed, index, "rounding")
        expander.add_row(spin_rounding)
        self._fix_spin_icons(spin_rounding)

        spin_decorate = Adw.SpinRow.new_with_range(-1, 1, 1)
        spin_decorate.set_title("Decorate (-1=unset)")
        spin_decorate.add_prefix(Gtk.Image.new_from_icon_name("applications-graphics-symbolic"))
        spin_decorate.set_value(rule.decorate)
        spin_decorate.connect("notify::value", self._on_spin_changed, index, "decorate")
        expander.add_row(spin_decorate)
        self._fix_spin_icons(spin_decorate)

        spin_gapsin = Adw.SpinRow.new_with_range(-1, 100, 1)
        spin_gapsin.set_title("Gaps In (-1=unset)")
        spin_gapsin.add_prefix(Gtk.Image.new_from_icon_name("view-dual-symbolic"))
        spin_gapsin.set_value(rule.gapsin)
        spin_gapsin.connect("notify::value", self._on_spin_changed, index, "gapsin")
        expander.add_row(spin_gapsin)
        self._fix_spin_icons(spin_gapsin)

        spin_gapsout = Adw.SpinRow.new_with_range(-1, 100, 1)
        spin_gapsout.set_title("Gaps Out (-1=unset)")
        spin_gapsout.add_prefix(Gtk.Image.new_from_icon_name("view-dual-symbolic"))
        spin_gapsout.set_value(rule.gapsout)
        spin_gapsout.connect("notify::value", self._on_spin_changed, index, "gapsout")
        expander.add_row(spin_gapsout)
        self._fix_spin_icons(spin_gapsout)

        spin_border = Adw.SpinRow.new_with_range(-1, 1, 1)
        spin_border.set_title("Border (-1=unset)")
        spin_border.add_prefix(Gtk.Image.new_from_icon_name("focus-windows-symbolic"))
        spin_border.set_value(rule.border)
        spin_border.connect("notify::value", self._on_spin_changed, index, "border")
        expander.add_row(spin_border)
        self._fix_spin_icons(spin_border)

        spin_bordersize = Adw.SpinRow.new_with_range(-1, 20, 1)
        spin_bordersize.set_title("Border Size (-1=unset)")
        spin_bordersize.add_prefix(Gtk.Image.new_from_icon_name("value-increase-symbolic"))
        spin_bordersize.set_value(rule.bordersize)
        spin_bordersize.connect("notify::value", self._on_spin_changed, index, "bordersize")
        expander.add_row(spin_bordersize)
        self._fix_spin_icons(spin_bordersize)

        entry_oce = Adw.EntryRow(title="On Created Empty")
        entry_oce.add_prefix(Gtk.Image.new_from_icon_name("utilities-terminal-symbolic"))
        entry_oce.set_text(rule.on_created_empty)
        entry_oce.connect("changed", self._on_text_changed, index, "on_created_empty")
        expander.add_row(entry_oce)

        # Drag-and-drop reordering
        drag = Gtk.DragSource()
        drag.set_actions(Gdk.DragAction.MOVE)
        drag.connect("prepare", self._on_drag_prepare, index)
        expander.add_controller(drag)

        drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        drop.connect("drop", self._on_drop, index)
        expander.add_controller(drop)

        return expander

    # -- Quick Setup ----------------------------------------------------------

    def _on_quick_setup_clicked(self, btn: Gtk.Button) -> None:
        if self._rules:
            self._confirm_replace_then_setup()
        else:
            self._show_quick_setup_dialog()

    def _confirm_replace_then_setup(self) -> None:
        dialog = Adw.AlertDialog()
        dialog.set_heading("Replace existing rules?")
        dialog.set_body(
            "Quick Setup will remove all current workspace rules "
            "and generate new ones."
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("replace", "Replace")
        dialog.set_response_appearance(
            "replace", Adw.ResponseAppearance.DESTRUCTIVE
        )
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_confirm_replace_response)
        dialog.present(self)

    def _on_confirm_replace_response(
        self, dialog: Adw.AlertDialog, response: str
    ) -> None:
        if response == "replace":
            self._show_quick_setup_dialog()

    def _show_quick_setup_dialog(self) -> None:
        dialog = Adw.Dialog()
        dialog.set_title("Quick Setup")
        dialog.set_content_width(500)
        dialog.set_content_height(550)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        header.set_show_start_title_buttons(False)

        btn_generate = Gtk.Button(label="Generate")
        btn_generate.add_css_class("suggested-action")
        header.pack_end(btn_generate)
        outer.append(header)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        page = Adw.PreferencesPage()

        # -- Total workspaces group --
        grp_total = Adw.PreferencesGroup(title="Workspaces")
        spin_total = Adw.SpinRow.new_with_range(1, 20, 1)
        spin_total.set_title("Number of workspaces")
        spin_total.set_value(10)
        grp_total.add(spin_total)
        self._fix_spin_icons(spin_total)
        page.add(grp_total)

        # -- Per-monitor distribution --
        # Sort: enabled first, disabled last
        monitor_order: list[int] = sorted(
            range(len(self._monitor_names)),
            key=lambda i: (not self._monitor_enabled[i], i),
        )
        # Parallel lists: spin values preserved across rebuilds
        spin_values: list[int] = [0] * len(self._monitor_names)

        grp_dist = Adw.PreferencesGroup(
            title="Distribution",
            description="Drag to reorder monitor priority",
        )
        monitor_listbox = Gtk.ListBox()
        monitor_listbox.add_css_class("boxed-list")
        monitor_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        grp_dist.add(monitor_listbox)

        summary_label = Gtk.Label(
            label="",
            halign=Gtk.Align.END,
            margin_top=8,
            margin_end=12,
            margin_bottom=4,
        )
        summary_label.add_css_class("dim-label")
        summary_label.add_css_class("caption")
        grp_dist.add(summary_label)

        page.add(grp_dist)

        scroll.set_child(page)
        outer.append(scroll)
        dialog.set_child(outer)

        # -- State helpers ---
        distributing = [False]
        qs_drag = [-1]  # mutable drag source rank
        spin_rows: list[Adw.SpinRow] = []

        def build_monitor_rows() -> None:
            """(Re)build the monitor ListBox from monitor_order."""
            # Save current values
            for i, spin in enumerate(spin_rows):
                spin_values[monitor_order[i]] = int(spin.get_value())

            spin_rows.clear()
            while True:
                row = monitor_listbox.get_row_at_index(0)
                if row is None:
                    break
                monitor_listbox.remove(row)

            for rank, idx in enumerate(monitor_order):
                name = self._monitor_names[idx]
                enabled = self._monitor_enabled[idx]
                spin = Adw.SpinRow.new_with_range(0, 20, 1)
                title = f"Workspaces for {name}"
                if not enabled:
                    title += " (disabled)"
                spin.set_title(title)
                if idx < len(self._monitor_descriptions) and self._monitor_descriptions[idx]:
                    spin.set_subtitle(self._monitor_descriptions[idx])
                    spin.set_subtitle_lines(1)
                    spin.set_title_lines(1)
                spin.set_margin_top(8)
                spin.set_margin_bottom(8)
                if not enabled:
                    spin.set_sensitive(False)
                spin.set_value(spin_values[idx])
                spin.connect("notify::value", on_monitor_spin_changed)

                # DnD
                drag = Gtk.DragSource()
                drag.set_actions(Gdk.DragAction.MOVE)
                drag.connect("prepare", on_qs_drag_prepare, rank)
                spin.add_controller(drag)

                drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
                drop.connect("drop", on_qs_drop, rank)
                spin.add_controller(drop)

                monitor_listbox.append(spin)
                spin_rows.append(spin)
                self._fix_spin_icons(spin)

        def on_qs_drag_prepare(source, x, y, rank):
            qs_drag[0] = rank
            return Gdk.ContentProvider.new_for_value(
                GObject.Value(GObject.TYPE_STRING, str(rank))
            )

        def on_qs_drop(target, value, x, y, dest_rank):
            src = qs_drag[0]
            if src < 0 or src == dest_rank or src >= len(monitor_order):
                return False
            idx = monitor_order.pop(src)
            monitor_order.insert(dest_rank, idx)
            build_monitor_rows()
            update_summary()
            return True

        def distribute(total: int) -> None:
            distributing[0] = True
            enabled = [r for r, i in enumerate(monitor_order) if self._monitor_enabled[i]]
            n = len(enabled)
            if n == 0:
                distributing[0] = False
                return
            base = total // n
            extra = total % n
            for pos, rank in enumerate(enabled):
                spin_rows[rank].set_value(base + (1 if pos < extra else 0))
            distributing[0] = False
            update_summary()

        def update_summary() -> None:
            assigned = sum(int(s.get_value()) for s in spin_rows)
            total = int(spin_total.get_value())
            summary_label.set_label(f"Assigned {assigned} / {total}")
            if assigned != total:
                summary_label.add_css_class("error")
            else:
                summary_label.remove_css_class("error")

        def on_total_changed(row: Adw.SpinRow, pspec) -> None:
            if not distributing[0]:
                distribute(int(row.get_value()))

        def on_monitor_spin_changed(row: Adw.SpinRow, pspec) -> None:
            if not distributing[0]:
                update_summary()

        spin_total.connect("notify::value", on_total_changed)

        # Build initial rows and distribute
        build_monitor_rows()
        distribute(int(spin_total.get_value()))

        def on_generate_clicked(btn: Gtk.Button) -> None:
            total = int(spin_total.get_value())
            # Use monitor_order for workspace assignment order
            distribution = {}
            for rank, idx in enumerate(monitor_order):
                distribution[self._monitor_names[idx]] = int(spin_rows[rank].get_value())
            dialog.force_close()
            self._generate_rules(total, distribution)

        btn_generate.connect("clicked", on_generate_clicked)
        dialog.present(self)

    def _generate_rules(
        self, total: int, distribution: dict[str, int]
    ) -> None:
        rules: list[WorkspaceRule] = []
        ws_num = 1
        for monitor, count in distribution.items():
            for i in range(count):
                rule = WorkspaceRule(
                    workspace=str(ws_num),
                    monitor=monitor,
                    default=(i == 0),
                    persistent=(i == 0),
                )
                rules.append(rule)
                ws_num += 1
        self._rules = rules
        self._rebuild_list()
        self.emit("rules-changed")

    # -- Handlers -------------------------------------------------------------

    def _on_add_clicked(self, btn: Gtk.Button) -> None:
        self._rules.append(WorkspaceRule())
        self._rebuild_list()
        self.emit("rules-changed")

    def _on_drag_prepare(self, source, x, y, index):
        self._drag_index = index
        return Gdk.ContentProvider.new_for_value(
            GObject.Value(GObject.TYPE_STRING, str(index))
        )

    def _on_drop(self, target, value, x, y, dest_index):
        src = self._drag_index
        if src < 0 or src == dest_index or src >= len(self._rules):
            return False
        rule = self._rules.pop(src)
        self._rules.insert(dest_index, rule)
        self._rebuild_list()
        self.emit("rules-changed")
        return True

    def _on_delete_clicked(self, btn: Gtk.Button, index: int) -> None:
        if 0 <= index < len(self._rules):
            self._rules.pop(index)
            self._rebuild_list()
            self.emit("rules-changed")

    @staticmethod
    def _ws_title(ws: str) -> str:
        if not ws:
            return "New Rule"
        if ws.isdigit():
            return f"Workspace {ws}"
        return ws

    def _on_ws_changed(self, entry, index: int, expander=None) -> None:
        if self._building or index >= len(self._rules):
            return
        text = entry.get_text()
        self._rules[index].workspace = text
        if expander:
            expander.set_title(self._ws_title(text))
        self.emit("rules-changed")

    def _on_monitor_changed(self, combo: Gtk.DropDown, pspec, index: int) -> None:
        if self._building or index >= len(self._rules):
            return
        sel = combo.get_selected()
        if sel == 0:
            self._rules[index].monitor = ""
        else:
            options = [""] + self._monitor_names
            if sel < len(options):
                self._rules[index].monitor = options[sel]
        self.emit("rules-changed")

    def _on_persistent_toggled(self, btn: Gtk.ToggleButton, index: int) -> None:
        if self._building or index >= len(self._rules):
            return
        active = btn.get_active()
        self._rules[index].persistent = active
        if active:
            btn.add_css_class("accent")
        else:
            btn.remove_css_class("accent")
        self.emit("rules-changed")

    def _on_default_toggled(self, btn: Gtk.ToggleButton, index: int) -> None:
        if self._building or index >= len(self._rules):
            return
        active = btn.get_active()
        self._rules[index].default = active
        # Ensure only one default per monitor
        if active:
            monitor = self._rules[index].monitor
            if monitor:
                for i, r in enumerate(self._rules):
                    if i != index and r.monitor == monitor and r.default:
                        r.default = False
            self._rebuild_list()
        else:
            btn.remove_css_class("warning")
        self.emit("rules-changed")

    def _on_advanced_changed(self, row: Adw.SwitchRow, pspec, index: int, field: str) -> None:
        if self._building or index >= len(self._rules):
            return
        setattr(self._rules[index], field, row.get_active())
        self.emit("rules-changed")

    def _on_spin_changed(self, row: Adw.SpinRow, pspec, index: int, field: str) -> None:
        if self._building or index >= len(self._rules):
            return
        setattr(self._rules[index], field, int(row.get_value()))
        self.emit("rules-changed")

    def _on_text_changed(self, row: Adw.EntryRow, index: int, field: str) -> None:
        if self._building or index >= len(self._rules):
            return
        setattr(self._rules[index], field, row.get_text())
        self.emit("rules-changed")
