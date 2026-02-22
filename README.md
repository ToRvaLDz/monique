<p align="center">
  <img src="https://raw.githubusercontent.com/ToRvaLDz/monique/main/data/com.github.monique.svg" width="96" alt="Monique icon">
</p>

<h1 align="center">Monique</h1>

<p align="center">
  <b>MON</b>itor <b>I</b>ntegrated <b>QU</b>ick <b>E</b>ditor
  <br>
  Graphical monitor configurator for <b>Hyprland</b>, <b>Sway</b> and <b>Niri</b>
</p>

<p align="center">
  <a href="https://github.com/ToRvaLDz/monique/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ToRvaLDz/monique/actions/workflows/ci.yml/badge.svg?v=0.3.1"></a>
  <a href="https://github.com/ToRvaLDz/monique/releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/ToRvaLDz/monique?include_prereleases&label=release&color=orange&v=0.3.1"></a>
  <a href="https://pypi.org/project/monique/"><img alt="PyPI" src="https://img.shields.io/pypi/v/monique?color=blue&label=PyPI&v=0.3.1"></a>
  <a href="https://aur.archlinux.org/packages/monique"><img alt="AUR" src="https://img.shields.io/aur/version/monique?color=1793d1&label=AUR&v=0.3.1"></a>
  <a href="LICENSE"><img alt="License: GPL-3.0" src="https://img.shields.io/badge/license-GPL--3.0-blue"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11+-green">
  <img alt="GTK4 + Adwaita" src="https://img.shields.io/badge/toolkit-GTK4%20%2B%20Adwaita-purple">
  <br>
  <a href="https://github.com/ToRvaLDz/monique/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/ToRvaLDz/monique?style=flat&color=yellow&v=0.3.1"></a>
  <img alt="Last commit" src="https://img.shields.io/github/last-commit/ToRvaLDz/monique?color=teal&v=0.3.1">
  <img alt="Repo size" src="https://img.shields.io/github/repo-size/ToRvaLDz/monique?color=gray&v=0.3.1">
  <br>
  <img alt="Hyprland" src="https://img.shields.io/badge/Hyprland-%2358e1ff?logo=hyprland&logoColor=white">
  <img alt="Sway" src="https://img.shields.io/badge/Sway-%2368751a?logo=sway&logoColor=white">
  <img alt="Niri" src="https://img.shields.io/badge/Niri-%23c77dff">
  <img alt="Wayland" src="https://img.shields.io/badge/Wayland-%23ffbc00?logo=wayland&logoColor=black">
</p>

---

## Screenshots

<table>
  <tr>
    <td align="center">
      <a href="https://raw.githubusercontent.com/ToRvaLDz/monique/main/data/screenshots/1.png"><img src="https://raw.githubusercontent.com/ToRvaLDz/monique/main/data/screenshots/1.png" width="400" alt="Monitor layout editor"></a>
      <br><sub>Layout editor</sub>
    </td>
    <td align="center">
      <a href="https://raw.githubusercontent.com/ToRvaLDz/monique/main/data/screenshots/2.png"><img src="https://raw.githubusercontent.com/ToRvaLDz/monique/main/data/screenshots/2.png" width="400" alt="Workspace rules"></a>
      <br><sub>Workspace rules</sub>
    </td>
  </tr>
  <tr>
    <td align="center">
      <a href="https://raw.githubusercontent.com/ToRvaLDz/monique/main/data/screenshots/3.png"><img src="https://raw.githubusercontent.com/ToRvaLDz/monique/main/data/screenshots/3.png" width="400" alt="Quick setup wizard"></a>
      <br><sub>Quick setup</sub>
    </td>
    <td align="center">
      <a href="https://raw.githubusercontent.com/ToRvaLDz/monique/main/data/screenshots/4.png"><img src="https://raw.githubusercontent.com/ToRvaLDz/monique/main/data/screenshots/4.png" width="400" alt="SDDM preferences"></a>
      <br><sub>SDDM integration</sub>
    </td>
  </tr>
</table>

## Features

- **Drag-and-drop layout** — arrange monitors visually on an interactive canvas
- **Multi-backend** — auto-detects Hyprland, Sway, or Niri from the environment
- **Profile system** — save, load, and switch between monitor configurations
- **Hotplug daemon** (`moniqued`) — automatically applies the best matching profile when monitors are connected or disconnected
- **Display manager integration** — syncs your layout to the login screen for SDDM (xrandr) and greetd (sway), with polkit rule for passwordless writes
- **Workspace rules** — configure workspace-to-monitor assignments (Hyprland/Sway)
- **Live preview** — OSD overlay to identify monitors (double-click)
- **Workspace migration** — automatically moves workspaces to the primary monitor when their monitor is disabled or unplugged (reverted if you click "Revert")
- **Clamshell mode** — disable the internal laptop display when external monitors are connected (manual toggle in the toolbar or automatic via daemon preferences); the daemon also monitors the lid state via UPower D-Bus
- **Confirm-or-revert** — 10-second countdown after applying, auto-reverts if display is unusable

## Installation

### AUR (Arch Linux / CachyOS)

```bash
yay -S monique
```

Or manually:

```bash
git clone https://aur.archlinux.org/monique.git
cd monique
makepkg -si
```

### PyPI

```bash
pip install monique
```

### From source

```bash
git clone https://github.com/ToRvaLDz/monique.git
cd monique
pip install .
```

**Runtime dependencies:** `python`, `python-gobject`, `gtk4`, `libadwaita`
**Optional:** `python-pyudev` (hardware hotplug detection for Niri)

## Usage

### GUI

```bash
monique
```

Open the graphical editor to arrange monitors, set resolutions, scale, rotation, and manage profiles.

### Daemon

```bash
moniqued
```

Or enable the systemd user service:

```bash
systemctl --user enable --now moniqued
```

The daemon auto-detects the active compositor and listens for monitor hotplug events. When a monitor is connected or disconnected, it waits 500ms (debounce) then applies the best matching profile. On Niri, the daemon uses udev DRM events (via `pyudev`) for reliable hardware hotplug detection. Orphaned workspaces are automatically migrated to the primary monitor on Hyprland/Sway (configurable via **Preferences > Migrate workspaces**).

#### Clamshell mode

On laptops, the daemon can automatically disable the internal display when external monitors are connected. Enable it from the GUI: **Menu > Preferences > Clamshell Mode**.

The daemon also monitors the laptop lid state via UPower D-Bus: closing the lid disables the internal display, opening it re-enables it. On desktop PCs (no lid detected), clamshell mode simply disables any internal-type output (`eDP`, `LVDS`) whenever external monitors are present.

> **Note:** if your system suspends on lid close, set `HandleLidSwitch=ignore` in `/etc/systemd/logind.conf` so the daemon can handle it instead.

### Behavior per environment

| Environment | Detection | Events |
|---|---|---|
| Hyprland | `$HYPRLAND_INSTANCE_SIGNATURE` | `monitoradded` / `monitorremoved` via socket2 |
| Sway | `$SWAYSOCK` | `output` events via i3-ipc subscribe |
| Niri | `$NIRI_SOCKET` | udev DRM subsystem (with `pyudev`), IPC fallback |
| Neither | Warning, retry every 5s | — |

## Display manager integration

Monique can sync your monitor layout to the login screen for supported display managers.

| Display Manager | Method | Config path |
|---|---|---|
| SDDM | xrandr via `Xsetup` script | `/usr/share/sddm/scripts/Xsetup` |
| greetd (sway) | sway `output` commands | `/etc/greetd/monique-monitors.conf` |

A polkit rule is included to allow passwordless writes:

```bash
# Installed automatically by the PKGBUILD to:
# /usr/share/polkit-1/rules.d/60-com.github.monique.rules
```

Toggle from the GUI: **Menu > Preferences > Update SDDM Xsetup** or **Update greetd config**.

## Configuration

All configuration is stored in `~/.config/monique/`:

```
~/.config/monique/
├── profiles/
│   ├── Home.json
│   └── Office.json
└── settings.json
```

Monitor config files are written to the compositor's config directory:
- **Hyprland:** `~/.config/hypr/monitors.conf`
- **Sway:** `~/.config/sway/monitors.conf`
- **Niri:** `~/.config/niri/monitors.kdl`

## Project structure

```
src/monique/
├── app.py               # Application entry point
├── window.py            # Main GTK4/Adwaita window
├── canvas.py            # Monitor layout canvas
├── properties_panel.py  # Monitor properties sidebar
├── workspace_panel.py   # Workspace rules dialog
├── models.py            # MonitorConfig, Profile, WorkspaceRule
├── hyprland.py          # Hyprland IPC client
├── sway.py              # Sway IPC client (binary i3-ipc)
├── niri.py              # Niri IPC client (JSON socket)
├── daemon.py            # Hotplug daemon (moniqued)
├── profile_manager.py   # Profile save/load/match
└── utils.py             # Paths, file I/O, helpers
```

## License

[GPL-3.0-or-later](LICENSE)
