"""Utility helpers: XDG paths, file I/O, app configuration."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


APP_ID = "com.github.monique"


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


def sway_config_dir() -> Path:
    """Return the Sway config directory."""
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "sway"


def hyprland_config_dir() -> Path:
    """Return the Hyprland config directory."""
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "hypr"


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
