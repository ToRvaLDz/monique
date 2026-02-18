<p align="center">
  <img src="data/com.github.monique.svg" width="96" alt="Monique icon">
</p>

<h1 align="center">Monique</h1>

<p align="center">
  <b>MON</b>itor <b>I</b>ntegrated <b>QU</b>ick <b>E</b>ditor
  <br>
  Graphical monitor configurator for <b>Hyprland</b> and <b>Sway</b>
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: GPL-3.0" src="https://img.shields.io/badge/license-GPL--3.0-blue"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11+-green">
  <img alt="GTK4 + Adwaita" src="https://img.shields.io/badge/toolkit-GTK4%20%2B%20Adwaita-purple">
</p>

---

## Screenshots

<table>
  <tr>
    <td align="center">
      <a href="data/screenshots/1.png"><img src="data/screenshots/1.png" width="400" alt="Monitor layout editor"></a>
      <br><sub>Layout editor</sub>
    </td>
    <td align="center">
      <a href="data/screenshots/2.png"><img src="data/screenshots/2.png" width="400" alt="Workspace rules"></a>
      <br><sub>Workspace rules</sub>
    </td>
  </tr>
  <tr>
    <td align="center">
      <a href="data/screenshots/3.png"><img src="data/screenshots/3.png" width="400" alt="Quick setup wizard"></a>
      <br><sub>Quick setup</sub>
    </td>
    <td align="center">
      <a href="data/screenshots/4.png"><img src="data/screenshots/4.png" width="400" alt="SDDM preferences"></a>
      <br><sub>SDDM integration</sub>
    </td>
  </tr>
</table>

## Features

- **Drag-and-drop layout** — arrange monitors visually on an interactive canvas
- **Multi-backend** — auto-detects Hyprland or Sway from the environment
- **Profile system** — save, load, and switch between monitor configurations
- **Hotplug daemon** (`moniqued`) — automatically applies the best matching profile when monitors are connected or disconnected
- **SDDM integration** — syncs your layout to the login screen via xrandr (with polkit rule for passwordless writes)
- **Workspace rules** — configure workspace-to-monitor assignments
- **Live preview** — OSD overlay to identify monitors (double-click)
- **Confirm-or-revert** — 10-second countdown after applying, auto-reverts if display is unusable

## Installation

### Arch Linux / CachyOS

```bash
git clone https://github.com/ToRvaLDz/monique.git
cd monique
makepkg -si
```

### From source (pip)

```bash
git clone https://github.com/ToRvaLDz/monique.git
cd monique
pip install .
```

**Runtime dependencies:** `python`, `python-gobject`, `gtk4`, `libadwaita`

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

The daemon auto-detects the active compositor and listens for monitor hotplug events. When a monitor is connected or disconnected, it waits 500ms (debounce) then applies the best matching profile.

### Behavior per environment

| Environment | Detection | Events |
|---|---|---|
| Hyprland | `$HYPRLAND_INSTANCE_SIGNATURE` | `monitoradded` / `monitorremoved` via socket2 |
| Sway | `$SWAYSOCK` | `output` events via i3-ipc subscribe |
| Neither | Warning, retry every 5s | — |

## SDDM integration

Monique can sync your monitor layout to the SDDM login screen by writing an `Xsetup` script with xrandr commands.

A polkit rule is included to allow passwordless writes:

```bash
# Installed automatically by the PKGBUILD to:
# /usr/share/polkit-1/rules.d/60-com.github.monique.rules
```

Toggle SDDM sync from the GUI: **Menu > Preferences > Update SDDM Xsetup**.

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
├── daemon.py            # Hotplug daemon (moniqued)
├── profile_manager.py   # Profile save/load/match
└── utils.py             # Paths, file I/O, helpers
```

## License

[GPL-3.0-or-later](LICENSE)
