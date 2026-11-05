"""Umbriel IPC communication via one JSON object per line over a Unix socket."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from pathlib import Path
from typing import AsyncIterator

from .config_paths import (
    UMBRIEL,
    compositor_config_paths,
    niri_monitors_path,
    sway_monitors_path,
)
from .hypr_config import write_hyprland_configs
from .kanshi_config import write_kanshi_config
from .models import MonitorConfig, Profile
from .umbriel_config import (
    ensure_umbriel_include,
    monitor_from_umbriel_output,
    umbriel_ids,
    write_umbriel_config,
)
from .utils import (
    backup_file,
    is_greetd_running,
    is_hyprland_installed,
    is_kanshi_config_enabled,
    is_niri_installed,
    is_sddm_running,
    is_sway_installed,
    write_greetd_monitors,
    write_text,
    write_xsetup,
)

log = logging.getLogger(__name__)

_RECV_SIZE = 65536
_REQUEST_TIMEOUT_S = 5.0
# Una snapshot con molti modi supera il limite di default di asyncio (64 KiB)
_STREAM_LIMIT = 1 << 20


def umbriel_socket_path() -> str:
    """Return the IPC socket: ``$UMBRIEL_SOCKET`` or the per-display default."""
    explicit = os.environ.get("UMBRIEL_SOCKET")
    if explicit:
        return explicit
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    display = os.environ.get("WAYLAND_DISPLAY", "")
    return str(Path(runtime) / f"umbriel-{display}.sock")


def env_umbriel_socket() -> str | None:
    """Return ``$UMBRIEL_SOCKET`` when it belongs to the session we run in.

    Umbriel intitola il socket al proprio display Wayland: se
    ``$WAYLAND_DISPLAY`` è un altro, la variabile è ereditata da un Umbriel
    esterno (Niri o Sway annidati dentro Umbriel) e va ignorata.
    """
    sock = os.environ.get("UMBRIEL_SOCKET")
    if not sock:
        return None
    display = os.environ.get("WAYLAND_DISPLAY")
    if display and Path(sock).name != f"umbriel-{display}.sock":
        return None
    return sock


def _accepts_connections(path: Path) -> bool:
    """True if something listens on *path* (a crashed session leaves a stale file)."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(_REQUEST_TIMEOUT_S)
        sock.connect(str(path))
    except OSError:
        return False
    finally:
        sock.close()
    return True


def find_umbriel_socket(runtime_dir: Path) -> Path | None:
    """Scan *runtime_dir* for a live Umbriel socket.

    Prima il nome documentato ``umbriel-$WAYLAND_DISPLAY.sock``, poi gli altri
    ``umbriel-*.sock`` in ordine alfabetico.
    """
    display = os.environ.get("WAYLAND_DISPLAY")
    candidates = sorted(runtime_dir.glob("umbriel-*.sock"))
    if display:
        documented = runtime_dir / f"umbriel-{display}.sock"
        candidates = [documented, *(c for c in candidates if c != documented)]
    return next((c for c in candidates if _accepts_connections(c)), None)


def _reply_value(response: object) -> object:
    """Unwrap ``{"ok": value}``; ``{"err": msg}`` becomes a RuntimeError."""
    if isinstance(response, dict):
        if "err" in response:
            raise RuntimeError(f"Umbriel IPC error: {response['err']}")
        if "ok" in response:
            return response["ok"]
    return response


def _output_identities(outputs: list[dict]) -> frozenset[tuple]:
    """Identify the connected monitors, ignoring layout and focus changes."""
    return frozenset(
        (o.get("name"), o.get("make"), o.get("model"), o.get("serial"))
        for o in outputs
    )


class UmbrielIPC:
    """Communicate with Umbriel via its JSON Unix socket IPC."""

    def __init__(self) -> None:
        self._socket_path = umbriel_socket_path()

    def _request(self, cmd: dict) -> object:
        """Send one request line and return the ``ok`` value of the reply.

        Legge una sola riga terminata da newline senza aspettare l'EOF: il
        server non chiude la connessione subito dopo la risposta.
        """
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(_REQUEST_TIMEOUT_S)
            sock.connect(self._socket_path)
            sock.sendall((json.dumps(cmd) + "\n").encode())

            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(_RECV_SIZE)
                if not chunk:
                    raise ConnectionError("Umbriel closed the connection without a reply")
                buf += chunk
        finally:
            sock.close()

        raw = buf.split(b"\n", 1)[0]
        try:
            reply = json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Umbriel sent an invalid reply: {e}") from e
        return _reply_value(reply)

    def get_outputs(self) -> list[dict]:
        """Query every connected output, disabled ones included."""
        return self._request({"cmd": "outputs"})

    def get_monitors(self) -> list[MonitorConfig]:
        """Query all connected monitors as MonitorConfig list."""
        return [monitor_from_umbriel_output(o) for o in self.get_outputs()]

    def get_workspaces(self) -> list[dict]:
        """Query the workspaces (each entry carries its ``output``)."""
        return self._request({"cmd": "workspaces"})

    def reload(self) -> None:
        """No-op: Umbriel reloads config files live on save."""

    def config_paths(self, *, hypr_config_format: str | None = None) -> list[Path]:
        """Return the config files apply_profile() writes (for backup/revert)."""
        return compositor_config_paths(UMBRIEL, hypr_config_format=hypr_config_format)

    def _read_ids(self) -> dict[str, str] | None:
        """Map description -> ``config_name`` of the live outputs, None on failure."""
        try:
            return umbriel_ids(self.get_outputs())
        except (OSError, RuntimeError, ValueError, AttributeError) as e:
            log.warning("Cannot read Umbriel outputs for identities: %s", e)
            return None

    def apply_profile(
        self, profile: Profile, *, update_sddm: bool = True,
        update_greetd: bool = True, use_description: bool = False,
        hypr_config_format: str | None = None,
    ) -> None:
        """Write the Umbriel monitor config (live reload) and cross-write others."""
        ids = self._read_ids() if use_description else None
        write_umbriel_config(profile, use_description, ids)
        self._cross_write(
            profile, update_sddm=update_sddm, update_greetd=update_greetd,
            use_description=use_description, hypr_config_format=hypr_config_format,
        )
        # Dopo i cross-write: se non si riesce a includere il file l'apply fallisce
        # e il chiamante ripristina i backup
        ensure_umbriel_include()
        self._sync_output_power(profile)

    def _cross_write(
        self, profile: Profile, *, update_sddm: bool, update_greetd: bool,
        use_description: bool, hypr_config_format: str | None,
    ) -> None:
        """Write the configs of the other compositors and the greeters."""
        if is_hyprland_installed():
            write_hyprland_configs(
                profile, fmt=hypr_config_format, use_description=use_description,
            )
        if is_sway_installed():
            sway_conf = sway_monitors_path()
            backup_file(sway_conf)
            write_text(sway_conf, profile.generate_sway_config(use_description=use_description))
        if is_niri_installed():
            niri_conf = niri_monitors_path()
            backup_file(niri_conf)
            write_text(niri_conf, profile.generate_niri_config(use_description=use_description))
        if is_kanshi_config_enabled():
            write_kanshi_config(profile, use_description)
        if update_sddm and is_sddm_running():
            write_xsetup(profile.generate_xsetup_script())
        if update_greetd and is_greetd_running():
            write_greetd_monitors(profile.generate_sway_config(use_description=use_description))

    def _sync_output_power(self, profile: Profile) -> None:
        """Force each connected output on or off as the profile says.

        ``output-enable``/``output-disable`` lasciano un override a runtime
        che sopravvive a un reload identico del file.  Come per Niri, solo gli
        output il cui stato reale non coincide vengono toccati.
        """
        try:
            live = self.get_monitors()
        except (OSError, RuntimeError, ValueError) as e:
            log.warning("Cannot read Umbriel outputs to sync power state: %s", e)
            return

        for mon in profile.monitors:
            cur = _live_match(mon, live)
            if cur is None or cur.enabled == mon.enabled:
                continue
            action = "output-enable" if mon.enabled else "output-disable"
            request = {"cmd": "action", "action": action, "output": cur.name}
            try:
                self._request(request)
            except (OSError, RuntimeError, ValueError) as e:
                log.warning("Cannot run %s on %s: %s", action, cur.name, e)

    async def connect_event_socket(self) -> AsyncIterator[dict]:
        """Subscribe to ``outputs`` and yield when a monitor appears or goes.

        Umbriel invia una snapshot completa a ogni cambiamento (modo, posizione,
        focus, workspace attivo): si produce un evento solo se cambia l'insieme
        ``(name, make, model, serial)``.  La prima snapshot è solo registrata,
        così quelle provocate da un apply non possono innescare un ciclo.
        """
        reader, writer = await asyncio.open_unix_connection(
            self._socket_path, limit=_STREAM_LIMIT,
        )
        try:
            writer.write(b'{"cmd":"subscribe","events":["outputs"]}\n')
            await writer.drain()

            known: frozenset[tuple] | None = None
            while True:
                line = await reader.readline()
                if not line:
                    break
                event = _parse_line(line)
                if event is None:
                    continue
                _reply_value(event)  # un {"err"} interrompe il flusso
                data = event.get("data")
                if event.get("event") != "outputs" or not isinstance(data, list):
                    continue
                current = _output_identities(data)
                changed = known is not None and current != known
                known = current
                if changed:
                    yield event
        finally:
            writer.close()


def _live_match(mon: MonitorConfig, live: list[MonitorConfig]) -> MonitorConfig | None:
    """Find the connected output *mon* stands for, None when ambiguous.

    Con la descrizione un solo output vivo basta; i gemelli senza seriale
    la condividono, quindi si ripiega sul connettore.  Senza corrispondenza
    univoca meglio non toccare nulla che spegnere il gemello sbagliato.
    """
    by_name = [m for m in live if m.name == mon.name]
    if not mon.description:
        return by_name[0] if by_name else None
    twins = [m for m in live if m.description == mon.description]
    if len(twins) <= 1:
        return twins[0] if twins else None
    named = [m for m in twins if m.name == mon.name]
    return named[0] if len(named) == 1 else None


def _parse_line(line: bytes) -> dict | None:
    """Decode one event line; None for blank, invalid or non-object lines."""
    text = line.decode(errors="replace").strip()
    if not text:
        return None
    try:
        event = json.loads(text)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None
