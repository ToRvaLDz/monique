"""Niri IPC communication via JSON over Unix socket."""

from __future__ import annotations

import asyncio
import json
import os
import socket
from typing import AsyncIterator

from .models import MonitorConfig, Profile
from .utils import (
    niri_config_dir,
    is_hyprland_installed,
    hyprland_config_dir,
    is_sway_installed,
    sway_config_dir,
    is_sddm_running,
    is_greetd_running,
    write_xsetup,
    write_greetd_monitors,
    write_text,
    backup_file,
)


def _ensure_niri_config_include() -> bool:
    """Ensure config.kdl includes monitors.kdl, removing inline output blocks.

    On first run, strips any top-level ``output`` blocks from config.kdl
    (since Monique now manages them via monitors.kdl) and appends the
    ``include`` directive.  Subsequent calls are no-ops.

    Returns True if config.kdl was modified.
    """
    config = niri_config_dir() / "config.kdl"
    if not config.exists():
        return False
    try:
        text = config.read_text(encoding="utf-8")
    except OSError:
        return False

    # Check if include already present
    has_include = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        if "include" in stripped and "monitors.kdl" in stripped:
            has_include = True
            break

    if has_include:
        return False

    # Strip top-level output blocks: ``output "..." { ... }``
    lines = text.splitlines(keepends=True)
    cleaned: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("output ") and "{" in stripped:
            # Skip until closing brace
            depth = stripped.count("{") - stripped.count("}")
            i += 1
            while i < len(lines) and depth > 0:
                depth += lines[i].count("{") - lines[i].count("}")
                i += 1
            # Skip trailing blank line after block
            if i < len(lines) and lines[i].strip() == "":
                i += 1
            continue
        cleaned.append(lines[i])
        i += 1

    result = "".join(cleaned)
    if not result.endswith("\n"):
        result += "\n"
    result += '\n// Monique monitor configuration\ninclude "monitors.kdl"\n'

    backup_file(config)
    write_text(config, result)
    return True


class NiriIPC:
    """Communicate with Niri via its JSON Unix socket IPC."""

    def __init__(self) -> None:
        self._socket_path = os.environ.get("NIRI_SOCKET", "")

    def _request(self, msg: str) -> dict | list:
        """Send a JSON request to the Niri socket, return the Ok result."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self._socket_path)
            sock.sendall((msg + "\n").encode())
            sock.shutdown(socket.SHUT_WR)

            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            sock.close()

        raw = b"".join(chunks).decode(errors="replace")
        response = json.loads(raw)

        if "Ok" in response:
            ok = response["Ok"]
            # The Ok value is a dict with a single key (the response type)
            if isinstance(ok, dict) and len(ok) == 1:
                return next(iter(ok.values()))
            return ok
        if "Err" in response:
            raise RuntimeError(f"Niri IPC error: {response['Err']}")
        return response

    def get_monitors(self) -> list[MonitorConfig]:
        """Query all connected monitors as MonitorConfig list."""
        data = self._request('"Outputs"')
        return [MonitorConfig.from_niri_output(name, out) for name, out in data.items()]

    def get_workspaces(self) -> list[dict]:
        """Query active workspaces."""
        return self._request('"Workspaces"')

    def move_workspace_to_monitor(self, workspace: str, monitor: str) -> None:
        """Move a workspace to a different monitor via Niri Action."""
        action = {"Action": {"MoveWorkspaceToOutput": {"output": monitor}}}
        self._request(json.dumps(action))

    def reload(self) -> None:
        """No-op: Niri auto-reloads config files on change."""
        pass

    def apply_profile(
        self, profile: Profile, *, update_sddm: bool = True,
        update_greetd: bool = True, use_description: bool = False,
    ) -> None:
        """Write monitors.kdl (Niri auto-reloads) and cross-write other compositors."""
        conf_dir = niri_config_dir()
        monitors_conf = conf_dir / "monitors.kdl"

        # Build mapping: normalised description → Niri-native description
        # so that output identifiers in the KDL config match what Niri expects
        # (e.g. "AOC 2757 …" → "PNP(AOC) 2757 …").
        niri_ids: dict[str, str] | None = None
        if use_description:
            try:
                raw_outputs = self._request('"Outputs"')
                niri_ids = {}
                for out in raw_outputs.values():
                    make = out.get("make", "")
                    model = out.get("model", "")
                    serial = out.get("serial") or ""
                    raw_parts = [p for p in (make, model, serial) if p]
                    raw_desc = " ".join(raw_parts)
                    # Build the normalised key (same logic as __post_init__)
                    norm = raw_desc
                    if norm.startswith("PNP("):
                        paren = norm.find(") ")
                        if paren != -1:
                            norm = norm[4:paren] + norm[paren + 1:]
                    if norm.endswith(" Unknown"):
                        norm = norm[:-8]
                    niri_ids[norm] = raw_desc
            except Exception:
                niri_ids = None

        # Backup existing
        backup_file(monitors_conf)

        # Write Niri config
        write_text(monitors_conf, profile.generate_niri_config(
            use_description=use_description, niri_ids=niri_ids,
        ))

        # Cross-write Hyprland config if Hyprland is installed
        if is_hyprland_installed():
            hypr_conf = hyprland_config_dir() / "monitors.conf"
            backup_file(hypr_conf)
            write_text(hypr_conf, profile.generate_config(use_description=use_description))

        # Cross-write Sway config if Sway is installed
        if is_sway_installed():
            sway_conf = sway_config_dir() / "monitors.conf"
            backup_file(sway_conf)
            write_text(sway_conf, profile.generate_sway_config(use_description=use_description))

        # Write SDDM Xsetup script if enabled and SDDM is present
        if update_sddm and is_sddm_running():
            write_xsetup(profile.generate_xsetup_script())

        # Write greetd sway monitors config if enabled and greetd is present
        if update_greetd and is_greetd_running():
            write_greetd_monitors(profile.generate_sway_config(use_description=use_description))

        # Ensure config.kdl includes monitors.kdl (strips inline output blocks on first run)
        _ensure_niri_config_include()

        # No explicit reload needed — Niri watches config files

    async def connect_event_socket(self) -> AsyncIterator[dict]:
        """Connect to EventStream and yield events indicating output changes.

        Niri has no dedicated output event.  We watch ``WorkspacesChanged``
        and yield only when the set of outputs mentioned in the workspace
        list changes (i.e. a monitor was added or removed).
        """
        reader, writer = await asyncio.open_unix_connection(self._socket_path)

        try:
            writer.write(b'"EventStream"\n')
            await writer.drain()

            known_outputs: set[str] | None = None

            while True:
                line = await reader.readline()
                if not line:
                    break
                text = line.decode(errors="replace").strip()
                if not text:
                    continue
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue

                # Extract the set of outputs from WorkspacesChanged
                ws_data = event.get("WorkspacesChanged")
                if ws_data is not None:
                    workspaces = ws_data.get("workspaces", [])
                    outputs = {
                        ws.get("output", "")
                        for ws in workspaces
                        if ws.get("output")
                    }
                    if known_outputs is None:
                        # First event: record initial state, don't yield
                        known_outputs = outputs
                    elif outputs != known_outputs:
                        known_outputs = outputs
                        yield event
        finally:
            writer.close()
