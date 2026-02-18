"""Hyprland IPC communication via Unix sockets."""

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path
from typing import AsyncIterator

from .models import MonitorConfig, Profile, WorkspaceRule
from .utils import (
    hyprland_runtime_dir,
    hyprland_config_dir,
    is_sway_installed,
    sway_config_dir,
    is_sddm_running,
    write_xsetup,
    write_text,
    backup_file,
)


class HyprlandIPC:
    """Communicate with Hyprland via its Unix socket IPC."""

    def __init__(self) -> None:
        self._runtime = hyprland_runtime_dir()

    @property
    def command_socket(self) -> Path:
        return self._runtime / ".socket.sock"

    @property
    def event_socket(self) -> Path:
        return self._runtime / ".socket2.sock"

    def _send(self, payload: bytes) -> bytes:
        """Send a raw command to the Hyprland command socket and return the response."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(self.command_socket))
            sock.sendall(payload)
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            sock.close()

    def command(self, cmd: str) -> str:
        """Send a command and return the text response."""
        return self._send(cmd.encode()).decode(errors="replace")

    def command_json(self, cmd: str) -> list | dict:
        """Send a -j command and return parsed JSON."""
        raw = self._send(f"j/{cmd}".encode()).decode(errors="replace")
        return json.loads(raw)

    def keyword(self, key: str, value: str) -> str:
        """Send a keyword command (runtime config change)."""
        return self.command(f"keyword {key} {value}")

    def batch(self, commands: list[str]) -> str:
        """Send multiple commands as a batch."""
        joined = ";".join(commands)
        return self.command(f"[[BATCH]]{joined}")

    def reload(self) -> str:
        """Reload Hyprland configuration."""
        return self.command("reload")

    def get_monitors(self) -> list[MonitorConfig]:
        """Query all connected monitors (including disabled) as MonitorConfig list."""
        data = self.command_json("monitors all")
        return [MonitorConfig.from_hyprctl(m) for m in data]

    def get_workspaces(self) -> list[dict]:
        """Query active workspaces."""
        return self.command_json("workspaces")

    def get_workspace_rules(self, monitors: list[MonitorConfig] | None = None) -> list[WorkspaceRule]:
        """Query workspace rules and return as WorkspaceRule list.

        Resolves ``desc:...`` monitor references to port names using *monitors*.
        """
        data = self.command_json("workspacerules")
        # Build desc→name mapping
        desc_to_name: dict[str, str] = {}
        if monitors:
            for m in monitors:
                if m.description:
                    desc_to_name[m.description] = m.name

        rules: list[WorkspaceRule] = []
        for entry in data:
            ws = entry.get("workspaceString", "")
            # Skip special workspaces
            if ws.startswith("special:"):
                continue

            monitor_raw = entry.get("monitor", "")
            if monitor_raw.startswith("desc:"):
                desc = monitor_raw[5:]
                monitor = desc_to_name.get(desc, monitor_raw)
            else:
                monitor = monitor_raw

            # gapsOut can be a list [top, right, bottom, left] or absent
            gapsout_raw = entry.get("gapsOut")
            if isinstance(gapsout_raw, list):
                gapsout = gapsout_raw[0] if gapsout_raw else -1
            elif isinstance(gapsout_raw, (int, float)):
                gapsout = int(gapsout_raw)
            else:
                gapsout = -1

            gapsin_raw = entry.get("gapsIn")
            if isinstance(gapsin_raw, list):
                gapsin = gapsin_raw[0] if gapsin_raw else -1
            elif isinstance(gapsin_raw, (int, float)):
                gapsin = int(gapsin_raw)
            else:
                gapsin = -1

            rule = WorkspaceRule(
                workspace=ws,
                monitor=monitor,
                default=entry.get("default", False),
                persistent=entry.get("persistent", False),
                rounding=entry.get("rounding", -1),
                decorate=entry.get("decorate", -1),
                gapsin=gapsin,
                gapsout=gapsout,
                border=entry.get("border", -1),
                bordersize=entry.get("borderSize", -1),
                on_created_empty=entry.get("onCreatedEmpty", ""),
            )
            rules.append(rule)
        return rules

    def apply_profile(self, profile: Profile, *, update_sddm: bool = True) -> None:
        """Write monitor config and reload Hyprland."""
        conf_dir = hyprland_config_dir()
        monitors_conf = conf_dir / "monitors.conf"

        # Backup existing
        backup_file(monitors_conf)

        # Write new config
        write_text(monitors_conf, profile.generate_config())

        # Also write Sway config if Sway is installed
        if is_sway_installed():
            sway_conf = sway_config_dir() / "monitors.conf"
            backup_file(sway_conf)
            write_text(sway_conf, profile.generate_sway_config())

        # Write SDDM Xsetup script if enabled and SDDM is present
        if update_sddm and is_sddm_running():
            write_xsetup(profile.generate_xsetup_script())

        # Reload
        self.reload()

    def apply_profile_keyword(self, profile: Profile) -> None:
        """Apply profile via keyword commands (live, no file write)."""
        cmds: list[str] = []
        for m in profile.monitors:
            line = m.to_hyprland_line()
            # strip "monitor=" prefix for keyword command
            value = line.removeprefix("monitor=")
            cmds.append(f"keyword monitor {value}")
        if cmds:
            self.batch(cmds)

    _MONITOR_EVENTS = (
        "monitoradded>>", "monitorremoved>>",
        "monitoraddedv2>>", "monitorremovedv2>>",
    )

    async def connect_event_socket(self) -> AsyncIterator[str]:
        """Connect to the event socket and yield only monitor hotplug events.

        Filters the raw event stream to yield only monitoradded/monitorremoved
        events, so callers don't need to filter themselves.
        """
        reader, _ = await asyncio.open_unix_connection(str(self.event_socket))
        while True:
            line = await reader.readline()
            if not line:
                break
            event = line.decode(errors="replace").strip()
            if any(event.startswith(e) for e in self._MONITOR_EVENTS):
                yield event
