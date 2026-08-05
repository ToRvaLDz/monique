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
  <a href="https://github.com/ToRvaLDz/monique/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/ToRvaLDz/monique/actions/workflows/ci.yml/badge.svg?v=0.7.0"></a>
  <a href="https://github.com/ToRvaLDz/monique/releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/ToRvaLDz/monique?include_prereleases&label=release&color=orange&v=0.7.0"></a>
  <a href="https://pypi.org/project/monique/"><img alt="PyPI" src="https://img.shields.io/pypi/v/monique?color=blue&label=PyPI&v=0.7.0"></a>
  <a href="https://aur.archlinux.org/packages/monique"><img alt="AUR" src="https://img.shields.io/aur/version/monique?color=1793d1&label=AUR&v=0.7.0"></a>
  <img alt="NixOS" src="https://img.shields.io/badge/NixOS-flake-5277C3?logo=nixos&logoColor=white">
  <a href="LICENSE"><img alt="License: GPL-3.0" src="https://img.shields.io/badge/license-GPL--3.0-blue"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11+-green">
  <img alt="GTK4 + Adwaita" src="https://img.shields.io/badge/toolkit-GTK4%20%2B%20Adwaita-purple">
  <br>
  <img alt="Last commit" src="https://img.shields.io/github/last-commit/ToRvaLDz/monique?color=teal&v=0.7.0">
  <img alt="Repo size" src="https://img.shields.io/github/repo-size/ToRvaLDz/monique?color=gray&v=0.7.0">
  <br>
  <img alt="Hyprland" src="https://img.shields.io/badge/Hyprland-%2358e1ff?logo=hyprland&logoColor=white">
  <img alt="Sway" src="https://img.shields.io/badge/Sway-%2368751a?logo=sway&logoColor=white">
  <img alt="Niri" src="https://img.shields.io/badge/Niri-%23c77dff">
  <img alt="Wayland" src="https://img.shields.io/badge/Wayland-%23ffbc00?logo=wayland&logoColor=black">
</p>

<p align="center">
  <a href="https://github.com/ToRvaLDz/monique/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/ToRvaLDz/monique?style=social"></a>
</p>

<p align="center">
  <a href="https://buymeacoffee.com/marcomigozzi"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" width="160"></a>
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
- **Cross-write** — save a profile in any compositor and automatically generate config files for the others (e.g. configure in Hyprland → get Sway and Niri configs for free)
- **Profile system** — save, load, and switch between monitor configurations
- **Hotplug daemon** (`moniqued`) — automatically applies the best matching profile when monitors are connected or disconnected
- **Display manager integration** — syncs your layout to the login screen for SDDM (xrandr) and greetd (sway), with polkit rule for passwordless writes
- **Workspace rules** — configure workspace-to-monitor assignments (Hyprland/Sway)
- **HDR & color management** — color management presets, 10-bit output, ICC profiles, SDR brightness/saturation and per-monitor EDID luminance overrides (Hyprland `monitorv2`)
- **Live preview** — OSD overlay to identify monitors (double-click)
- **Workspace migration** — automatically moves workspaces to the primary monitor when their monitor is disabled or unplugged (reverted if you click "Revert")
- **Clamshell mode** — disable the internal laptop display when external monitors are connected (manual toggle in the toolbar or automatic via daemon preferences); the daemon also monitors the lid state via UPower D-Bus
- **Confirm-or-revert** — 10-second countdown after applying, auto-reverts if display is unusable
- **CLI interface** — list, query, and switch profiles from the terminal (`--list-profiles`, `--current-profile`, `--switch-profile`), perfect for hotkey bindings
- **Custom config directory** — write generated monitor config files to a custom path instead of the compositor default (via Preferences or `--config-dir`)
- **Custom config filename** — change the generated file's base name (default `monitors`) from **Preferences → Config Output**; the right extension is added per compositor (`.kdl`/`.conf`/`.lua`) and subdirectories are supported (e.g. `cfg/display`)
- **Active profile tracking** — the last applied profile is persisted across GUI, CLI, and daemon, queryable via `--current-profile`

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

### NixOS / Nix

**With flake** (recommended) -- add it as an input and use the NixOS module:

```nix
# flake.nix
inputs.monique.url = "github:ToRvaLDz/monique";

# configuration.nix (via module)
{ inputs, ... }: {
  imports = [ inputs.monique.nixosModules.default ];
  programs.monique.enable = true;
}
```

**Run without installing:**

```bash
nix run github:ToRvaLDz/monique
```

**Install to user profile:**

```bash
nix profile install github:ToRvaLDz/monique
```

**With overlay:**

```nix
nixpkgs.overlays = [ inputs.monique.overlays.default ];
environment.systemPackages = [ pkgs.monique ];
```

> **Polkit note:** the NixOS module automatically installs the polkit rule for passwordless SDDM/greetd writes. Disable with `programs.monique.enablePolkit = false`.

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

**Runtime dependencies:**

| Distro | Packages |
|--------|----------|
| Arch / CachyOS | `python python-gobject gtk4 libadwaita` |
| Fedora | `python3 python3-gobject gtk4 libadwaita` |
| openSUSE | `python3 python3-gobject gtk4 libadwaita typelib-1_0-Adw-1 typelib-1_0-Gtk-4_0` |
| Ubuntu / Debian | `python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 libadwaita-1-0` |
| NixOS | gestito automaticamente dal flake |

**Optional:** `python-pyudev` (hardware hotplug detection for Niri)

## Usage

### GUI

```bash
monique
```

Open the graphical editor to arrange monitors, set resolutions, scale, rotation, and manage profiles.

### CLI

```bash
# List all saved profiles (JSON array)
monique --list-profiles

# Get the currently active profile
monique --current-profile

# Switch to a profile
monique --switch-profile "Office"

# Switch with a custom config output directory
monique --config-dir ~/my-hypr-config --switch-profile "Office"
```

Bind `monique --switch-profile <name>` to any compositor hotkey for quick profile switching.

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

## HDR and color management

Available on **Hyprland 0.50+**, where Monique writes the `monitorv2 { … }` block syntax
(auto-detected from the running compositor). Sway and Niri expose no equivalent options,
so these controls stay disabled there.

Select a monitor and scroll the properties sidebar. **Advanced** group:

| Control | Hyprland key | Values |
|---|---|---|
| Color Management | `cm` | `auto`, `srgb`, `dcip3`, `dp3`, `adobe`, `wide`, `edid`, `hdr`, `hdredid` |
| Bit Depth | `bitdepth` | `8` or `10` (10 recommended for HDR) |
| ICC Profile | `icc` | absolute path, Hyprland 0.55+ (takes precedence over `cm`) |
| SDR Brightness | `sdrbrightness` | `0.0` to `5.0`, default `1.0` |
| SDR Saturation | `sdrsaturation` | `0.0` to `5.0`, default `1.0` |

**HDR / EDID Override** group, for panels whose EDID reports wrong or missing capabilities:

| Control | Hyprland key | Values |
|---|---|---|
| SDR EOTF | `sdr_eotf` | Global / sRGB / Gamma 2.2 |
| Supports HDR | `supports_hdr` | Auto / Force |
| Supports Wide Color | `supports_wide_color` | Auto / Force |
| SDR Min Luminance | `sdr_min_luminance` | `0.0` to `10.0` |
| SDR Max Luminance | `sdr_max_luminance` | `0.0` to `2000.0` |
| Min Luminance | `min_luminance` | `0.0` to `2000.0` |
| Max Luminance | `max_luminance` | `0.0` to `10000.0` |
| Max Avg Luminance | `max_avg_luminance` | `0.0` to `10000.0` |

Rows marked *inactive* only take effect when Color Management is set to `hdr` or `hdredid`,
or when Hyprland's auto HDR settings drive them. Values left at their default are omitted
from the generated config, so Hyprland keeps its own defaults.

> **Washed-out SDR content on an HDR display** is the usual first problem: raise
> **SDR Brightness** above `1.0` and adjust **SDR Saturation**, and try **SDR EOTF → Gamma 2.2**.
> `hdredid` uses the luminance data from your display's EDID, which helps when that data is
> accurate and hurts when it is not, which is what the manual luminance overrides are for.

> **Note:** Monique only writes the compositor-side configuration. Whether a given
> application or game actually outputs HDR depends on it, and on Proton/gamescope, not on
> the monitor configurator.

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
- **Hyprland:** `~/.config/hypr/monitors.conf` and/or `~/.config/hypr/monitors.lua`
- **Sway:** `~/.config/sway/monitors.conf`
- **Niri:** `~/.config/niri/monitors.kdl`

For Hyprland's legacy hyprlang config, add `source = ~/.config/hypr/monitors.conf` to `hyprland.conf`.
For Hyprland 0.55+ Lua config, add `require("monitors")` to `hyprland.lua`.

By default Monique writes both Hyprland formats so either config style keeps working.
If you only use one, pick it in **Preferences → Hyprland Config Format** (`legacy`, `lua`,
or `both`, stored as `hypr_config_format` in `settings.json`). Switching away from a format
leaves the previously generated file on disk: delete it, or drop its `source`/`require`
line from your Hyprland config, otherwise Hyprland keeps applying the stale layout.

To use a custom output directory, set it in **Preferences → Config Output** or pass `--config-dir` on the command line.

To change the generated file's base name (default `monitors`), set **Monitor config filename** in
**Preferences → Config Output** (stored as `monitor_config_name` in `settings.json`). The value is a
base name without extension, relative to the compositor's config directory, and may include
subdirectories (e.g. `cfg/display` → `cfg/display.kdl` for Niri, `cfg/display.conf` for Sway, and
`cfg/display.conf`/`cfg/display.lua` for Hyprland). Absolute paths and `..` segments are rejected.
For Niri, the `include` line in `config.kdl` is kept in sync with the configured name; if you change
the name later, update your Hyprland `source`/`require` lines to match.

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

## Contributors

Thanks to everyone who has contributed to Monique!

<a href="https://github.com/ToRvaLDz/monique/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=ToRvaLDz/monique" alt="Contributors" />
</a>

## License

[GPL-3.0-or-later](LICENSE)
