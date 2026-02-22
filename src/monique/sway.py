"""Sway IPC communication via binary i3-ipc protocol."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import struct
from typing import AsyncIterator

from .models import MonitorConfig, Profile
from .utils import (
    is_hyprland_installed,
    hyprland_config_dir,
    sway_config_dir,
    is_sddm_running,
    is_greetd_running,
    write_xsetup,
    write_greetd_monitors,
    write_text,
    backup_file,
)

# i3-ipc protocol constants
_MAGIC = b"i3-ipc"
_HEADER_SIZE = 14  # 6 (magic) + 4 (payload_len) + 4 (type)
_HEADER_FMT = f"={len(_MAGIC)}sII"

# Message types
IPC_COMMAND = 0
IPC_GET_WORKSPACES = 1
IPC_SUBSCRIBE = 2
IPC_GET_OUTPUTS = 3

# Event type (high bit set)
EVENT_OUTPUT = 0x80000001


def _recv_exactly(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes from a socket."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed while reading")
        buf.extend(chunk)
    return bytes(buf)


async def _arecv_exactly(reader: asyncio.StreamReader, n: int) -> bytes:
    """Read exactly n bytes from an async StreamReader."""
    data = await reader.readexactly(n)
    return data


class SwayIPC:
    """Communicate with Sway via the i3-ipc binary protocol."""

    def __init__(self) -> None:
        self._socket_path = os.environ.get("SWAYSOCK", "")

    def _send(self, msg_type: int, payload: str = "") -> dict | list:
        """Send a message and return the parsed JSON response."""
        payload_bytes = payload.encode()
        header = struct.pack(_HEADER_FMT, _MAGIC, len(payload_bytes), msg_type)

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self._socket_path)
            sock.sendall(header + payload_bytes)

            # Read response header
            resp_header = _recv_exactly(sock, _HEADER_SIZE)
            _, resp_len, _ = struct.unpack(_HEADER_FMT, resp_header)

            # Read response payload
            resp_payload = _recv_exactly(sock, resp_len)
            return json.loads(resp_payload.decode())
        finally:
            sock.close()

    def get_outputs(self) -> list[dict]:
        """Query all outputs via GET_OUTPUTS."""
        return self._send(IPC_GET_OUTPUTS)

    def get_monitors(self) -> list[MonitorConfig]:
        """Query all connected monitors as MonitorConfig list."""
        outputs = self.get_outputs()
        return [MonitorConfig.from_sway_output(o) for o in outputs]

    def get_workspaces(self) -> list[dict]:
        """Query active workspaces."""
        return self._send(IPC_GET_WORKSPACES)

    def move_workspace_to_monitor(self, workspace: str, monitor: str) -> dict | list:
        """Move a workspace to a different monitor."""
        return self._send(IPC_COMMAND, f"[workspace={workspace}] move workspace to output {monitor}")

    def reload(self) -> dict:
        """Reload Sway configuration."""
        return self._send(IPC_COMMAND, "reload")

    def apply_profile(
        self, profile: Profile, *, update_sddm: bool = True,
        update_greetd: bool = True, use_description: bool = False,
    ) -> None:
        """Write monitor config and reload Sway."""
        conf_dir = sway_config_dir()
        monitors_conf = conf_dir / "monitors.conf"

        # Backup existing
        backup_file(monitors_conf)

        # Write Sway config
        write_text(monitors_conf, profile.generate_sway_config(use_description=use_description))

        # Also write Hyprland config if Hyprland is installed
        if is_hyprland_installed():
            hypr_conf = hyprland_config_dir() / "monitors.conf"
            backup_file(hypr_conf)
            write_text(hypr_conf, profile.generate_config(use_description=use_description))

        # Write SDDM Xsetup script if enabled and SDDM is present
        if update_sddm and is_sddm_running():
            write_xsetup(profile.generate_xsetup_script())

        # Write greetd sway monitors config if enabled and greetd is present
        if update_greetd and is_greetd_running():
            write_greetd_monitors(profile.generate_sway_config(use_description=use_description))

        # Reload
        self.reload()

    async def connect_event_socket(self) -> AsyncIterator[dict]:
        """Subscribe to output events and yield only output event payloads."""
        reader, writer = await asyncio.open_unix_connection(self._socket_path)

        try:
            # Subscribe to output events
            subscribe_payload = json.dumps(["output"]).encode()
            header = struct.pack(
                _HEADER_FMT, _MAGIC, len(subscribe_payload), IPC_SUBSCRIBE,
            )
            writer.write(header + subscribe_payload)
            await writer.drain()

            # Consume the subscribe ACK
            ack_header = await _arecv_exactly(reader, _HEADER_SIZE)
            _, ack_len, _ = struct.unpack(_HEADER_FMT, ack_header)
            await _arecv_exactly(reader, ack_len)

            # Yield only hotplug output events (new/del),
            # skip 'unspecified' to avoid infinite loop when we apply config
            while True:
                evt_header = await _arecv_exactly(reader, _HEADER_SIZE)
                _, evt_len, evt_type = struct.unpack(_HEADER_FMT, evt_header)
                evt_payload = await _arecv_exactly(reader, evt_len)

                if evt_type == EVENT_OUTPUT:
                    event = json.loads(evt_payload.decode())
                    change = event.get("change", "")
                    if change in ("new", "del"):
                        yield event
        finally:
            writer.close()
