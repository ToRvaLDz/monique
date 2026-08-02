"""Niri IPC communication via JSON over Unix socket."""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
from pathlib import Path
from typing import AsyncIterator

from .config_paths import (
    NIRI,
    compositor_config_paths,
    niri_monitors_path,
    sway_monitors_path,
)
from .hypr_config import write_hyprland_configs
from .models import MonitorConfig, Profile, focus_at_startup_from_niri
from .utils import (
    niri_config_dir,
    get_monitor_config_name,
    is_hyprland_installed,
    is_sway_installed,
    is_sddm_running,
    is_greetd_running,
    write_xsetup,
    write_greetd_monitors,
    write_text,
    backup_file,
)


def read_focus_at_startup() -> list[str]:
    """Return the identifiers marked ``focus-at-startup`` in the config we wrote.

    L'IPC di Niri non riporta il flag (è solo di configurazione), quindi
    ``monitors.kdl`` è l'unica fonte per ricostruirlo dopo un reload.
    """
    conf = niri_monitors_path()
    if not conf.exists():
        return []
    return focus_at_startup_from_niri(conf.read_text(encoding="utf-8"))


# Comment marker written above the Monique-managed ``include`` line in
# config.kdl.  It is how we tell our own include apart from a user's when the
# configured filename changes and the stale line has to be swapped out.
_NIRI_INCLUDE_MARKER = "// Monique monitor configuration"


def _strip_monique_include(lines: list[str]) -> tuple[list[str], str | None]:
    """Drop the Monique-managed marker + ``include`` line.

    Returns the remaining lines and the previous include target (the quoted
    filename), or ``None`` when no Monique-managed include was present.  User
    ``include`` lines (which lack the marker) are left untouched.
    """
    kept: list[str] = []
    old_target: str | None = None
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip() == _NIRI_INCLUDE_MARKER:
            j = i + 1
            while j < n and lines[j].strip() == "":
                j += 1
            if j < n and lines[j].lstrip().startswith("include"):
                m = re.search(r'"([^"]+)"', lines[j])
                if m:
                    old_target = m.group(1)
                j += 1
            i = j
            continue
        kept.append(lines[i])
        i += 1
    return kept, old_target


def _strip_niri_output_blocks(lines: list[str]) -> list[str]:
    """Remove top-level ``output "..." { ... }`` blocks (Monique manages them)."""
    cleaned: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("output ") and "{" in stripped:
            depth = stripped.count("{") - stripped.count("}")
            i += 1
            while i < len(lines) and depth > 0:
                depth += lines[i].count("{") - lines[i].count("}")
                i += 1
            if i < len(lines) and lines[i].strip() == "":
                i += 1
            continue
        cleaned.append(lines[i])
        i += 1
    return cleaned


def _ensure_niri_config_include() -> bool:
    """Ensure config.kdl includes the configured monitor config file.

    On first run, strips any top-level ``output`` blocks from config.kdl (since
    Monique now manages them via the include) and appends the ``include``
    directive.  When the configured filename has changed since a previous run,
    the stale Monique-managed ``include`` is removed and replaced so Niri never
    applies two conflicting layouts.  A user's own ``include`` of the current
    file is respected and never duplicated.

    Returns True if config.kdl was modified.
    """
    config = niri_config_dir() / "config.kdl"
    if not config.exists():
        return False
    try:
        text = config.read_text(encoding="utf-8")
    except OSError:
        return False

    rel_name = f"{get_monitor_config_name()}.kdl"
    lines = text.splitlines(keepends=True)

    kept, old_target = _strip_monique_include(lines)
    first_run = old_target is None

    # A user-authored include of the current file (no Monique marker) counts as
    # already present: don't add a second one.
    user_has_current = any(
        not ln.lstrip().startswith("//") and "include" in ln and rel_name in ln
        for ln in kept
    )

    # Our include already targets the right file, or the user manages it: no-op.
    if old_target == rel_name or (first_run and user_has_current):
        return False

    # Only strip output blocks on a genuine first run; on a rename the user may
    # have legitimately re-added output blocks we must not touch.
    if first_run:
        kept = _strip_niri_output_blocks(kept)

    result = "".join(kept).rstrip("\n")
    if user_has_current:
        result += "\n"
    else:
        result += f'\n\n{_NIRI_INCLUDE_MARKER}\ninclude "{rel_name}"\n'

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

    def config_paths(self, *, hypr_config_format: str | None = None) -> list[Path]:
        """Return the config files apply_profile() writes (for backup/revert)."""
        return compositor_config_paths(NIRI, hypr_config_format=hypr_config_format)

    def apply_profile(
        self, profile: Profile, *, update_sddm: bool = True,
        update_greetd: bool = True, use_description: bool = False,
        hypr_config_format: str | None = None,
    ) -> None:
        """Write the Niri monitor config (auto-reloads) and cross-write others."""
        monitors_conf = niri_monitors_path()

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
                    serial_raw = out.get("serial")
                    serial = serial_raw if serial_raw is not None else "Unknown"
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
            except (OSError, RuntimeError, ValueError, KeyError, AttributeError):
                niri_ids = None

        # Backup existing
        backup_file(monitors_conf)

        # Write Niri config
        write_text(monitors_conf, profile.generate_niri_config(
            use_description=use_description, niri_ids=niri_ids,
        ))

        # Cross-write Hyprland config if Hyprland is installed
        if is_hyprland_installed():
            write_hyprland_configs(
                profile, fmt=hypr_config_format, use_description=use_description,
            )

        # Cross-write Sway config if Sway is installed
        if is_sway_installed():
            sway_conf = sway_monitors_path()
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
