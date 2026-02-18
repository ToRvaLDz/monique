"""Application entry point."""

from __future__ import annotations

import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio

from .utils import APP_ID


class MonitorApp(Adw.Application):
    """Main application class."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self) -> None:
        win = self.get_active_window()
        if win is None:
            from .window import MainWindow
            win = MainWindow(self)
        win.present()


def main() -> None:
    app = MonitorApp()
    app.run(sys.argv)
