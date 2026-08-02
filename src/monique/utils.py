"""Utility helpers: XDG paths, file I/O, app configuration."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


APP_ID = "com.github.monique"

# Formati di configurazione monitor supportati da Hyprland.
# "legacy" = hyprlang (monitors.conf), "lua" = Hyprland >= 0.55 (monitors.lua)
HYPR_FORMAT_LEGACY = "legacy"
HYPR_FORMAT_LUA = "lua"
HYPR_FORMAT_BOTH = "both"
HYPR_FORMATS = (HYPR_FORMAT_LEGACY, HYPR_FORMAT_LUA, HYPR_FORMAT_BOTH)
# Default retrocompatibile: scrive entrambi i file, come prima dell'opzione
DEFAULT_HYPR_FORMAT = HYPR_FORMAT_BOTH

# Base name (senza estensione) dei file di config monitor generati.  L'estensione
# la aggiunge ogni compositore: ``.kdl`` (Niri), ``.conf`` (Sway/Hyprland legacy),
# ``.lua`` (Hyprland >= 0.55).  Può includere sottocartelle relative alla config
# dir del compositore (es. ``cfg/display``).  Il default riproduce i nomi storici.
DEFAULT_MONITOR_CONFIG_NAME = "monitors"

# Override runtime impostato via --config-dir (priorità su settings.json)
_runtime_config_dir: str | None = None


def config_dir() -> Path:
    """Return ~/.config/monique, creating it if needed."""
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "monique"
    d.mkdir(parents=True, exist_ok=True)
    return d


def profiles_dir() -> Path:
    """Return the profiles subdirectory."""
    d = config_dir() / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_sway_installed() -> bool:
    """Return True if Sway is available on the system."""
    return shutil.which("sway") is not None


def is_hyprland_installed() -> bool:
    """Return True if Hyprland is available on the system."""
    return shutil.which("Hyprland") is not None


def is_niri_installed() -> bool:
    """Return True if Niri is available on the system."""
    return shutil.which("niri") is not None


def _config_dir_override() -> Path | None:
    """Restituisce il percorso personalizzato per i file monitor, se configurato.

    Priorità: --config-dir (runtime) > settings.json > default del compositor.
    """
    if _runtime_config_dir:
        return Path(_runtime_config_dir).expanduser()
    override = load_app_settings().get("config_dir")
    if override:
        return Path(override).expanduser()
    return None


def sway_config_dir() -> Path:
    """Return the Sway config directory."""
    override = _config_dir_override()
    if override:
        return override
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "sway"


def hyprland_config_dir() -> Path:
    """Return the Hyprland config directory."""
    override = _config_dir_override()
    if override:
        return override
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "hypr"


def niri_config_dir() -> Path:
    """Return the Niri config directory."""
    override = _config_dir_override()
    if override:
        return override
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "niri"


def hyprland_runtime_dir() -> Path:
    """Return the Hyprland runtime directory for IPC sockets."""
    his = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    xdg = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return Path(xdg) / "hypr" / his


def read_json(path: Path) -> dict | list | None:
    """Read and parse a JSON file, returning None on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, data: dict | list) -> None:
    """Write data as formatted JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    """Write text to a file, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def backup_file(path: Path) -> Path | None:
    """Create a .bak copy of a file. Returns backup path or None."""
    if not path.exists():
        return None
    bak = path.with_suffix(path.suffix + ".bak")
    bak.write_bytes(path.read_bytes())
    return bak


def restore_backup(path: Path) -> bool:
    """Restore a file from its .bak copy."""
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        return False
    path.write_bytes(bak.read_bytes())
    bak.unlink()
    return True


def sddm_xsetup_path() -> Path:
    """Return the path to the SDDM Xsetup script."""
    return Path("/usr/share/sddm/scripts/Xsetup")


def is_sddm_running() -> bool:
    """Return True if SDDM is installed (Xsetup script path exists)."""
    return sddm_xsetup_path().exists()


def write_xsetup(content: str) -> None:
    """Write the SDDM Xsetup script using pkexec for root privileges."""
    subprocess.run(
        ["pkexec", "tee", str(sddm_xsetup_path())],
        input=content.encode(),
        stdout=subprocess.DEVNULL,
        check=True,
    )


def greetd_sway_config_path() -> Path:
    """Return the path to the greetd sway config file."""
    return Path("/etc/greetd/sway-config")


def greetd_monitors_path() -> Path:
    """Return the path to the greetd monitors config file."""
    return Path("/etc/greetd/monique-monitors.conf")


def is_greetd_running() -> bool:
    """Return True if greetd is configured with sway (sway-config exists)."""
    return greetd_sway_config_path().exists()


def write_greetd_monitors(content: str) -> None:
    """Write the greetd monitors config using pkexec for root privileges."""
    subprocess.run(
        ["pkexec", "tee", str(greetd_monitors_path())],
        input=content.encode(),
        stdout=subprocess.DEVNULL,
        check=True,
    )


def _settings_path() -> Path:
    """Return the path to the global app settings file."""
    return config_dir() / "settings.json"


def load_app_settings() -> dict:
    """Load global application settings."""
    return read_json(_settings_path()) or {}


def save_app_settings(settings: dict) -> None:
    """Save global application settings."""
    write_json(_settings_path(), settings)


def normalize_hypr_format(value: object) -> str:
    """Return a valid Hyprland config format, falling back to the default."""
    if isinstance(value, str) and value in HYPR_FORMATS:
        return value
    return DEFAULT_HYPR_FORMAT


def get_hypr_config_format() -> str:
    """Return the Hyprland config format selected in the app settings."""
    return normalize_hypr_format(load_app_settings().get("hypr_config_format"))


# Estensioni note che l'utente potrebbe digitare per errore nel base name:
# le rimuoviamo così che ``display.kdl`` non diventi ``display.kdl.conf``.
_MONITOR_CONFIG_EXTS = (".kdl", ".conf", ".lua")


def sanitize_monitor_config_name(value: object) -> str:
    """Return a safe relative stem for the monitor config files.

    Accetta un percorso relativo (eventualmente con sottocartelle) e lo riduce a
    un base name sicuro:

    - i separatori vengono normalizzati a ``/`` (POSIX), come si scrivono nei
      config di Niri/Hyprland;
    - un'estensione nota digitata per errore (``.kdl``/``.conf``/``.lua``) viene
      rimossa: l'estensione la aggiunge il compositore;
    - percorsi assoluti, segmenti ``..``, ``.`` e componenti vuoti vengono
      rifiutati (niente traversal fuori dalla config dir);
    - se il risultato è vuoto o non valido si ricade sul default ``monitors``.
    """
    if not isinstance(value, str):
        return DEFAULT_MONITOR_CONFIG_NAME

    raw = value.strip().replace("\\", "/")
    if not raw or raw.startswith("/"):
        return DEFAULT_MONITOR_CONFIG_NAME

    # Rimuove un'estensione nota digitata per errore (solo sull'ultimo segmento).
    lowered = raw.lower()
    for ext in _MONITOR_CONFIG_EXTS:
        if lowered.endswith(ext):
            raw = raw[: -len(ext)]
            break

    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return DEFAULT_MONITOR_CONFIG_NAME

    return "/".join(parts)


def get_monitor_config_name() -> str:
    """Return the sanitized monitor config base name from the app settings."""
    return sanitize_monitor_config_name(
        load_app_settings().get("monitor_config_name")
    )


def save_active_profile(name: str | None) -> None:
    """Persist the name of the last applied profile."""
    settings = load_app_settings()
    write_json(_settings_path(), {**settings, "active_profile": name})


def get_active_profile() -> str | None:
    """Return the name of the last applied profile, or None."""
    return load_app_settings().get("active_profile")
