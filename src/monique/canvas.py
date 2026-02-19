"""Monitor arrangement canvas using Gtk.DrawingArea + Cairo."""

from __future__ import annotations

import math

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject

from .models import MonitorConfig, PositionMode


# Snap distance in canvas pixels
SNAP_DISTANCE = 12
# Minimum scale factor for zoom
MIN_ZOOM = 0.05
MAX_ZOOM = 3.0

# Colors
COLOR_BG = (0.12, 0.12, 0.14)
COLOR_GRID = (0.18, 0.18, 0.20)
COLOR_MONITOR = (0.22, 0.24, 0.28)
COLOR_MONITOR_BORDER = (0.4, 0.42, 0.46)
COLOR_SELECTED = (0.26, 0.52, 0.96)
COLOR_SELECTED_FILL = (0.20, 0.35, 0.55)
COLOR_DISABLED = (0.5, 0.2, 0.2)
COLOR_TEXT = (0.9, 0.9, 0.92)
COLOR_TEXT_DIM = (0.6, 0.62, 0.64)


class MonitorCanvas(Gtk.DrawingArea):
    """Canvas widget for arranging monitors with drag-and-drop."""

    __gtype_name__ = "MonitorCanvas"

    __gsignals__ = {
        "monitor-selected": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "monitor-moved": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "monitor-double-clicked": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }

    def __init__(self) -> None:
        super().__init__()
        self._monitors: list[MonitorConfig] = []
        self._selected: int = -1
        self._zoom: float = 0.15
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0

        # Drag state
        self._dragging: bool = False
        self._drag_start_x: float = 0
        self._drag_start_y: float = 0
        self._drag_orig_mx: int = 0
        self._drag_orig_my: int = 0

        # Pan state
        self._panning: bool = False
        self._pan_start_x: float = 0
        self._pan_start_y: float = 0
        self._pan_orig_px: float = 0
        self._pan_orig_py: float = 0

        self.set_draw_func(self._draw)
        self.set_hexpand(True)
        self.set_vexpand(True)

        # Click gesture for selection
        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("pressed", self._on_click_pressed)
        self.add_controller(click)

        # Middle-click for panning
        mid_click = Gtk.GestureClick()
        mid_click.set_button(2)
        mid_click.connect("pressed", self._on_mid_pressed)
        self.add_controller(mid_click)

        # Drag gesture for moving monitors
        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.add_controller(drag)

        # Middle-button drag for panning
        pan_drag = Gtk.GestureDrag()
        pan_drag.set_button(2)
        pan_drag.connect("drag-begin", self._on_pan_begin)
        pan_drag.connect("drag-update", self._on_pan_update)
        self.add_controller(pan_drag)

        # Scroll for zoom
        scroll = Gtk.EventControllerScroll()
        scroll.set_flags(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)

    @property
    def monitors(self) -> list[MonitorConfig]:
        return self._monitors

    @monitors.setter
    def monitors(self, value: list[MonitorConfig]) -> None:
        self._monitors = value
        if self._selected >= len(value):
            self._selected = len(value) - 1 if value else -1
        self._auto_fit()
        self.queue_draw()

    @property
    def selected_index(self) -> int:
        return self._selected

    @selected_index.setter
    def selected_index(self, value: int) -> None:
        if value != self._selected:
            self._selected = value
            self.queue_draw()
            self.emit("monitor-selected", value)

    def _auto_fit(self) -> None:
        """Auto-fit zoom and pan to show all monitors."""
        if not self._monitors:
            return
        min_x = min(m.x for m in self._monitors)
        min_y = min(m.y for m in self._monitors)
        max_x = max(m.x + m.logical_width for m in self._monitors)
        max_y = max(m.y + m.logical_height for m in self._monitors)

        w = self.get_width() or 800
        h = self.get_height() or 600

        span_x = max_x - min_x
        span_y = max_y - min_y
        if span_x <= 0 or span_y <= 0:
            return

        margin = 80
        zoom_x = (w - margin * 2) / span_x
        zoom_y = (h - margin * 2) / span_y
        self._zoom = max(MIN_ZOOM, min(MAX_ZOOM, min(zoom_x, zoom_y)))

        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        self._pan_x = w / 2 - cx * self._zoom
        self._pan_y = h / 2 - cy * self._zoom

    def _screen_to_logical(self, sx: float, sy: float) -> tuple[float, float]:
        """Convert screen coordinates to logical monitor coordinates."""
        lx = (sx - self._pan_x) / self._zoom
        ly = (sy - self._pan_y) / self._zoom
        return lx, ly

    def _logical_to_screen(self, lx: float, ly: float) -> tuple[float, float]:
        """Convert logical coordinates to screen coordinates."""
        sx = lx * self._zoom + self._pan_x
        sy = ly * self._zoom + self._pan_y
        return sx, sy

    def _hit_test(self, sx: float, sy: float) -> int:
        """Return index of monitor at screen position, or -1."""
        lx, ly = self._screen_to_logical(sx, sy)
        # Check in reverse order (topmost first)
        for i in range(len(self._monitors) - 1, -1, -1):
            m = self._monitors[i]
            if (m.x <= lx <= m.x + m.logical_width and
                    m.y <= ly <= m.y + m.logical_height):
                return i
        return -1

    def _snap_position(self, idx: int, new_x: float, new_y: float) -> tuple[int, int]:
        """Snap monitor position to edges of other monitors."""
        m = self._monitors[idx]
        w = m.logical_width
        h = m.logical_height
        threshold = SNAP_DISTANCE / self._zoom

        best_x = new_x
        best_y = new_y
        min_dx = threshold + 1
        min_dy = threshold + 1

        edges_x = [new_x, new_x + w]
        edges_y = [new_y, new_y + h]

        for i, other in enumerate(self._monitors):
            if i == idx:
                continue
            ow = other.logical_width
            oh = other.logical_height

            # Target edges for X snapping
            targets_x = [other.x, other.x + ow]
            for ex in edges_x:
                for tx in targets_x:
                    d = abs(ex - tx)
                    if d < min_dx:
                        min_dx = d
                        best_x = new_x + (tx - ex)

            # Target edges for Y snapping
            targets_y = [other.y, other.y + oh]
            for ey in edges_y:
                for ty in targets_y:
                    d = abs(ey - ty)
                    if d < min_dy:
                        min_dy = d
                        best_y = new_y + (ty - ey)

        snap_x = best_x if min_dx <= threshold else new_x
        snap_y = best_y if min_dy <= threshold else new_y

        return round(snap_x), round(snap_y)

    # ── Event handlers ───────────────────────────────────────────────

    def _on_click_pressed(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        idx = self._hit_test(x, y)
        if idx >= 0:
            self.selected_index = idx
            if n_press == 2:
                # Cancel any active drag and restore original position
                if self._dragging:
                    m = self._monitors[self._selected]
                    m.x = self._drag_orig_mx
                    m.y = self._drag_orig_my
                    self._dragging = False
                    self.queue_draw()
                self.emit("monitor-double-clicked", idx)

    def _on_mid_pressed(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        pass  # handled by pan drag

    def _on_drag_begin(self, gesture: Gtk.GestureDrag, x: float, y: float) -> None:
        idx = self._hit_test(x, y)
        if idx >= 0:
            m = self._monitors[idx]
            self._dragging = True
            self._drag_start_x = x
            self._drag_start_y = y
            self._drag_orig_mx = m.x
            self._drag_orig_my = m.y
        else:
            self._dragging = False

    def _on_drag_update(self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float) -> None:
        if not self._dragging or self._selected < 0:
            return
        # Ignore micro-movements (likely double-click)
        if abs(offset_x) < 3 and abs(offset_y) < 3:
            return
        m = self._monitors[self._selected]
        new_x = self._drag_orig_mx + offset_x / self._zoom
        new_y = self._drag_orig_my + offset_y / self._zoom
        m.x, m.y = self._snap_position(self._selected, new_x, new_y)
        m.position_mode = PositionMode.EXPLICIT
        self.queue_draw()

    def _on_drag_end(self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float) -> None:
        if self._dragging and self._selected >= 0:
            m = self._monitors[self._selected]
            actually_moved = (m.x != self._drag_orig_mx or m.y != self._drag_orig_my)
            self._dragging = False
            if actually_moved:
                self.emit("monitor-moved", self._selected)

    def _on_pan_begin(self, gesture: Gtk.GestureDrag, x: float, y: float) -> None:
        self._panning = True
        self._pan_start_x = x
        self._pan_start_y = y
        self._pan_orig_px = self._pan_x
        self._pan_orig_py = self._pan_y

    def _on_pan_update(self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float) -> None:
        if self._panning:
            self._pan_x = self._pan_orig_px + offset_x
            self._pan_y = self._pan_orig_py + offset_y
            self.queue_draw()

    def _on_scroll(self, controller: Gtk.EventControllerScroll, dx: float, dy: float) -> bool:
        factor = 1.15 if dy < 0 else 1 / 1.15
        new_zoom = self._zoom * factor
        new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, new_zoom))

        # Zoom toward cursor position
        # Get the current cursor position from the allocation center as fallback
        w = self.get_width()
        h = self.get_height()
        cx, cy = w / 2, h / 2

        # Adjust pan to zoom toward center
        self._pan_x = cx - (cx - self._pan_x) * (new_zoom / self._zoom)
        self._pan_y = cy - (cy - self._pan_y) * (new_zoom / self._zoom)
        self._zoom = new_zoom
        self.queue_draw()
        return True

    # ── Drawing ──────────────────────────────────────────────────────

    def _draw(self, area: Gtk.DrawingArea, cr, width: int, height: int) -> None:
        # Background
        cr.set_source_rgb(*COLOR_BG)
        cr.paint()

        # Grid
        self._draw_grid(cr, width, height)

        # Monitors
        for i, m in enumerate(self._monitors):
            self._draw_monitor(cr, m, i == self._selected)

    def _draw_grid(self, cr, width: int, height: int) -> None:
        cr.set_source_rgb(*COLOR_GRID)
        cr.set_line_width(0.5)

        # Determine grid spacing in logical coords
        base_spacing = 500  # logical pixels
        spacing = base_spacing * self._zoom

        # Ensure grid isn't too dense or too sparse
        while spacing < 30:
            spacing *= 2
        while spacing > 200:
            spacing /= 2

        # Draw vertical lines
        start_x = self._pan_x % spacing
        x = start_x
        while x < width:
            cr.move_to(x, 0)
            cr.line_to(x, height)
            x += spacing

        # Draw horizontal lines
        start_y = self._pan_y % spacing
        y = start_y
        while y < height:
            cr.move_to(0, y)
            cr.line_to(width, y)
            y += spacing

        cr.stroke()

    def _draw_monitor(self, cr, m: MonitorConfig, selected: bool) -> None:
        sx, sy = self._logical_to_screen(m.x, m.y)
        sw = m.logical_width * self._zoom
        sh = m.logical_height * self._zoom

        # Fill
        if not m.enabled:
            cr.set_source_rgb(*COLOR_DISABLED)
        elif selected:
            cr.set_source_rgb(*COLOR_SELECTED_FILL)
        else:
            cr.set_source_rgb(*COLOR_MONITOR)

        _rounded_rect(cr, sx, sy, sw, sh, 4)
        cr.fill()

        # Border
        if selected:
            cr.set_source_rgb(*COLOR_SELECTED)
            cr.set_line_width(2.5)
        else:
            cr.set_source_rgb(*COLOR_MONITOR_BORDER)
            cr.set_line_width(1.0)

        _rounded_rect(cr, sx, sy, sw, sh, 4)
        cr.stroke()

        # Text (only if monitor is big enough)
        if sw > 40 and sh > 20:
            self._draw_monitor_text(cr, m, sx, sy, sw, sh)

    def _draw_monitor_text(self, cr, m: MonitorConfig, sx: float, sy: float, sw: float, sh: float) -> None:
        cr.set_source_rgb(*COLOR_TEXT)

        # Name
        name = m.name or "?"
        font_size = min(14, max(8, sw / 10))
        cr.set_font_size(font_size)

        extents = cr.text_extents(name)
        tx = sx + (sw - extents.width) / 2
        ty = sy + sh / 2 - 2
        cr.move_to(tx, ty)
        cr.show_text(name)

        # Resolution
        cr.set_source_rgb(*COLOR_TEXT_DIM)
        res_text = f"{m.width}x{m.height}"
        font_size_small = min(10, max(6, sw / 14))
        cr.set_font_size(font_size_small)
        extents = cr.text_extents(res_text)
        tx = sx + (sw - extents.width) / 2
        ty = sy + sh / 2 + font_size_small + 4
        if ty + 4 < sy + sh:
            cr.move_to(tx, ty)
            cr.show_text(res_text)


def _rounded_rect(cr, x: float, y: float, w: float, h: float, r: float) -> None:
    """Draw a rounded rectangle path."""
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()
