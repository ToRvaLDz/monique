"""Application entry point."""

from __future__ import annotations

import json
import sys
import time

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio

from .utils import APP_ID, get_active_profile, save_active_profile
from .profile_manager import ProfileManager


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


def _cmd_list_profiles() -> int:
    mgr = ProfileManager()
    print(json.dumps(mgr.list_profiles()))
    return 0


def _cmd_current_profile() -> int:
    name = get_active_profile()
    if name:
        print(name)
        return 0
    print("")
    return 1


def _cmd_switch_profile(name: str) -> int:
    import os
    from .hyprland import HyprlandIPC
    from .niri import NiriIPC
    from .sway import SwayIPC
    from .utils import load_app_settings

    mgr = ProfileManager()
    profile = mgr.load(name)
    if profile is None:
        print(f"error: profile '{name}' not found", file=sys.stderr)
        available = mgr.list_profiles()
        if available:
            print(f"available profiles: {', '.join(available)}", file=sys.stderr)
        return 1

    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        ipc = HyprlandIPC()
    elif os.environ.get("NIRI_SOCKET"):
        ipc = NiriIPC()
    elif os.environ.get("SWAYSOCK"):
        ipc = SwayIPC()
    else:
        print("error: no supported compositor detected", file=sys.stderr)
        return 1

    settings = load_app_settings()
    ipc.apply_profile(
        profile,
        update_sddm=settings.get("update_sddm", True),
        update_greetd=settings.get("update_greetd", True),
        use_description=not settings.get("use_port_names", False),
    )
    save_active_profile(name)
    profile.last_applied_time = time.time()
    mgr.save(profile)

    print(name)
    return 0


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="monique",
        description="MONitor Integrated QUick Editor",
        add_help=True,
    )
    parser.add_argument(
        "--config-dir",
        metavar="PATH",
        help="Override output directory for monitors.conf",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--list-profiles",
        action="store_true",
        help="Print available profile names as JSON array and exit",
    )
    group.add_argument(
        "--current-profile",
        action="store_true",
        help="Print the active profile name and exit (exit code 1 if none)",
    )
    group.add_argument(
        "--switch-profile",
        metavar="NAME",
        help="Apply a profile by name and exit",
    )

    # argparse intercetta --help ma lascia passare gli argomenti GTK
    args, remaining = parser.parse_known_args()

    # Override runtime della directory di output (ha priorità sulle settings)
    if args.config_dir:
        from . import utils
        utils._runtime_config_dir = args.config_dir

    if args.list_profiles:
        sys.exit(_cmd_list_profiles())
    if args.current_profile:
        sys.exit(_cmd_current_profile())
    if args.switch_profile:
        sys.exit(_cmd_switch_profile(args.switch_profile))

    # Nessun flag CLI: avvia la GUI passando gli argomenti residui
    sys.argv = [sys.argv[0]] + remaining
    app = MonitorApp()
    app.run(sys.argv)
