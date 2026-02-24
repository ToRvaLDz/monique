"""Data models: MonitorConfig, WorkspaceRule, Profile."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import ClassVar


# ── Enums ────────────────────────────────────────────────────────────────

class ResolutionMode(Enum):
    EXPLICIT = "explicit"
    PREFERRED = "preferred"
    HIGHRES = "highres"
    HIGHRR = "highrr"


class PositionMode(Enum):
    EXPLICIT = "explicit"
    AUTO = "auto"
    AUTO_RIGHT = "auto-right"
    AUTO_LEFT = "auto-left"
    AUTO_UP = "auto-up"
    AUTO_DOWN = "auto-down"
    AUTO_CENTER_RIGHT = "auto-center-right"
    AUTO_CENTER_LEFT = "auto-center-left"
    AUTO_CENTER_UP = "auto-center-up"
    AUTO_CENTER_DOWN = "auto-center-down"


class ScaleMode(Enum):
    EXPLICIT = "explicit"
    AUTO = "auto"


class VRR(Enum):
    OFF = 0
    ON = 1
    FULLSCREEN = 2


class Transform(Enum):
    NORMAL = 0
    ROTATE_90 = 1
    ROTATE_180 = 2
    ROTATE_270 = 3
    FLIPPED = 4
    FLIPPED_90 = 5
    FLIPPED_180 = 6
    FLIPPED_270 = 7

    @property
    def label(self) -> str:
        labels = {
            0: "Normal",
            1: "90°",
            2: "180°",
            3: "270°",
            4: "Flipped",
            5: "Flipped 90°",
            6: "Flipped 180°",
            7: "Flipped 270°",
        }
        return labels[self.value]

    @property
    def is_rotated(self) -> bool:
        """True if width/height are swapped (90° or 270° variants)."""
        return self.value in (1, 3, 5, 7)


# ── MonitorConfig ────────────────────────────────────────────────────────

@dataclass
class MonitorConfig:
    # Identity (from hyprctl monitors -j)
    name: str = ""              # e.g. "DP-1", "HDMI-A-1"
    description: str = ""       # e.g. "LG Electronics LG ULTRAWIDE 0x00038C43"
    make: str = ""
    model: str = ""
    serial: str = ""

    # Resolution
    width: int = 1920
    height: int = 1080
    refresh_rate: float = 60.0
    resolution_mode: ResolutionMode = ResolutionMode.EXPLICIT

    # Available modes from hardware (list of "WxH@R" strings)
    available_modes: list[str] = field(default_factory=list)

    # Position
    x: int = 0
    y: int = 0
    position_mode: PositionMode = PositionMode.AUTO

    # Scale
    scale: float = 1.0
    scale_mode: ScaleMode = ScaleMode.EXPLICIT

    # Transform
    transform: Transform = Transform.NORMAL

    # Mirror
    mirror_of: str = ""

    # Advanced
    bitdepth: int = 8           # 8 or 10
    vrr: VRR = VRR.OFF
    color_management: str = ""  # "", "srgb", "dcip3", "dp3", "adobe", "wide", "edid", "hdr", "hdredid"
    sdr_brightness: float = 1.0
    sdr_saturation: float = 1.0

    # Reserved area
    reserved_top: int = 0
    reserved_bottom: int = 0
    reserved_left: int = 0
    reserved_right: int = 0

    # Enabled
    enabled: bool = True

    def __post_init__(self) -> None:
        # Normalize description so fingerprints match across compositors.
        # Hyprland appends "Unknown" for missing serials, Sway/Niri omit it.
        if self.description.endswith(" Unknown"):
            self.description = self.description[:-8]
        # Niri wraps some vendor names in PNP(…); strip for cross-compositor matching.
        if self.description.startswith("PNP("):
            paren = self.description.find(") ")
            if paren != -1:
                self.description = self.description[4:paren] + self.description[paren + 1:]

    @property
    def logical_width(self) -> float:
        """Width in logical pixels (accounting for scale and rotation)."""
        w, h = self.width, self.height
        if self.transform.is_rotated:
            w, h = h, w
        return w / self.scale

    @property
    def logical_height(self) -> float:
        """Height in logical pixels (accounting for scale and rotation)."""
        w, h = self.width, self.height
        if self.transform.is_rotated:
            w, h = h, w
        return h / self.scale

    @property
    def physical_size_rotated(self) -> tuple[int, int]:
        """Physical pixel dimensions accounting for rotation (no scale)."""
        w, h = self.width, self.height
        if self.transform.is_rotated:
            w, h = h, w
        return w, h

    @property
    def is_internal(self) -> bool:
        """True if this is a built-in laptop display (eDP or LVDS port)."""
        prefix = self.name.split("-")[0].upper() if self.name else ""
        return prefix in ("EDP", "LVDS", "DSI")

    # Mapping from Transform enum to xrandr --rotate / --reflect values
    # Each entry is (rotate, reflect_or_None)
    _XRANDR_TRANSFORMS: ClassVar[dict[int, tuple[str, str | None]]] = {
        0: ("normal", None),
        1: ("left", None),
        2: ("inverted", None),
        3: ("right", None),
        4: ("normal", "x"),
        5: ("left", "x"),
        6: ("inverted", "x"),
        7: ("right", "x"),
    }

    # Mapping from Transform enum (CCW, Wayland protocol) to Sway config
    # Sway transform strings match WL_OUTPUT_TRANSFORM enum values:
    # both Hyprland and Sway use the same Wayland protocol convention.
    _SWAY_TRANSFORMS: ClassVar[dict[int, str]] = {
        0: "normal",
        1: "90",
        2: "180",
        3: "270",
        4: "flipped",
        5: "flipped-90",
        6: "flipped-180",
        7: "flipped-270",
    }

    # Inverse mapping: Sway transform string -> Transform enum value
    _SWAY_TRANSFORMS_INV: ClassVar[dict[str, int]] = {
        v: k for k, v in _SWAY_TRANSFORMS.items()
    }

    # Mapping from Niri JSON transform string -> Transform enum value
    _NIRI_TRANSFORMS_INV: ClassVar[dict[str, int]] = {
        "Normal": 0, "90": 1, "180": 2, "270": 3,
        "Flipped": 4, "Flipped90": 5, "Flipped180": 6, "Flipped270": 7,
    }

    def to_sway_block(self, use_description: bool = False) -> str:
        """Generate the `output` config block for sway."""
        identifier = (
            f'"{self.description}"'
            if use_description and self.description
            else self.name
        )
        if not self.enabled:
            return f"output {identifier} disable"

        lines: list[str] = []

        # Resolution: only emit mode for explicit resolutions
        if self.resolution_mode == ResolutionMode.EXPLICIT:
            lines.append(f"    mode {self.width}x{self.height}@{self.refresh_rate:.3f}Hz")

        # Position: always emit explicit coordinates
        if self.position_mode == PositionMode.EXPLICIT:
            lines.append(f"    pos {self.x} {self.y}")

        # Scale
        if self.scale_mode == ScaleMode.EXPLICIT:
            lines.append(f"    scale {self.scale:g}")

        # Transform
        lines.append(f"    transform {self._SWAY_TRANSFORMS[self.transform.value]}")

        # VRR → adaptive_sync
        lines.append(f"    adaptive_sync {'on' if self.vrr != VRR.OFF else 'off'}")

        body = "\n".join(lines)
        return f"output {identifier} {{\n{body}\n}}"

    def to_niri_block(
        self, use_description: bool = False,
        niri_ids: dict[str, str] | None = None,
    ) -> str:
        """Generate the ``output`` config block for Niri (KDL format).

        *niri_ids* maps normalised description → Niri-native description
        (e.g. ``"AOC 2757 …"`` → ``"PNP(AOC) 2757 …"``).  When available
        and *use_description* is True, the Niri-native string is used so the
        compositor can match it.  Falls back to connector name.
        """
        if use_description and self.description:
            if niri_ids and self.description in niri_ids:
                identifier = f'"{niri_ids[self.description]}"'
            elif niri_ids is None:
                # No mapping available, best-effort with normalised description
                identifier = f'"{self.description}"'
            else:
                # Mapping available but monitor not in it (e.g. off monitor
                # not currently visible to Niri); fall back to port name
                identifier = f'"{self.name}"'
        else:
            identifier = f'"{self.name}"'
        if not self.enabled:
            return f"output {identifier} {{\n    off\n}}"

        lines: list[str] = []

        # Resolution
        if self.resolution_mode == ResolutionMode.EXPLICIT:
            lines.append(f'    mode "{self.width}x{self.height}@{self.refresh_rate:.3f}"')

        # Scale
        if self.scale_mode == ScaleMode.EXPLICIT:
            lines.append(f"    scale {self.scale:g}")

        # Transform (same values as Sway)
        transform_str = self._SWAY_TRANSFORMS[self.transform.value]
        if transform_str != "normal":
            lines.append(f'    transform "{transform_str}"')

        # Position
        if self.position_mode == PositionMode.EXPLICIT:
            lines.append(f"    position x={self.x} y={self.y}")

        # VRR
        if self.vrr != VRR.OFF:
            lines.append("    variable-refresh-rate")

        body = "\n".join(lines)
        return f"output {identifier} {{\n{body}\n}}"

    def to_xrandr_args(self, phys_x: int | None = None, phys_y: int | None = None) -> str:
        """Generate xrandr arguments for this monitor (without the ``xrandr`` prefix).

        *phys_x*/*phys_y* override the position with physical-pixel values
        (compositor positions are in logical/scaled coordinates which xrandr
        does not understand).
        """
        if not self.enabled:
            return f"--output {self.name} --off"

        parts = [f"--output {self.name}"]

        # Resolution
        if self.resolution_mode == ResolutionMode.EXPLICIT:
            parts.append(f"--mode {self.width}x{self.height}")
            parts.append(f"--rate {self.refresh_rate:.3f}")
        else:
            parts.append("--auto")

        # Position — use physical override when provided
        px = phys_x if phys_x is not None else self.x
        py = phys_y if phys_y is not None else self.y
        parts.append(f"--pos {px}x{py}")

        # Transform (rotate + reflect)
        rotate, reflect = self._XRANDR_TRANSFORMS[self.transform.value]
        parts.append(f"--rotate {rotate}")
        if reflect:
            parts.append(f"--reflect {reflect}")

        return " ".join(parts)

    def to_hyprland_line(
        self,
        use_description: bool = False,
        name_to_id: dict[str, str] | None = None,
    ) -> str:
        """Generate the `monitor=...` config line for hyprland.conf."""
        parts: list[str] = []

        # Name — use desc:DESCRIPTION when use_description is enabled
        if use_description and self.description:
            parts.append(f"desc:{self.description}")
        else:
            parts.append(self.name)

        # Disabled monitor
        if not self.enabled:
            parts.append("disable")
            return "monitor=" + ", ".join(parts)

        # Resolution
        if self.resolution_mode == ResolutionMode.EXPLICIT:
            refresh = f"{self.refresh_rate:g}"
            parts.append(f"{self.width}x{self.height}@{refresh}")
        else:
            parts.append(self.resolution_mode.value)

        # Position
        if self.position_mode == PositionMode.EXPLICIT:
            parts.append(f"{self.x}x{self.y}")
        else:
            parts.append(self.position_mode.value)

        # Scale
        if self.scale_mode == ScaleMode.AUTO:
            parts.append("auto")
        else:
            parts.append(f"{self.scale:g}")

        # Optional extras
        extras: list[str] = []

        if self.transform != Transform.NORMAL:
            extras.append(f"transform, {self.transform.value}")

        if self.mirror_of:
            mirror_id = self.mirror_of
            if name_to_id and self.mirror_of in name_to_id:
                mirror_id = name_to_id[self.mirror_of]
            extras.append(f"mirror, {mirror_id}")

        if self.bitdepth != 8:
            extras.append(f"bitdepth, {self.bitdepth}")

        if self.vrr != VRR.OFF:
            extras.append(f"vrr, {self.vrr.value}")

        if self.color_management:
            extras.append(f"cm, {self.color_management}")

        if self.sdr_brightness != 1.0:
            extras.append(f"sdrbrightness, {self.sdr_brightness:g}")

        if self.sdr_saturation != 1.0:
            extras.append(f"sdrsaturation, {self.sdr_saturation:g}")

        if any((self.reserved_top, self.reserved_bottom, self.reserved_left, self.reserved_right)):
            extras.append(
                f"addreserved, {self.reserved_top}, {self.reserved_bottom}, "
                f"{self.reserved_left}, {self.reserved_right}"
            )

        line = "monitor=" + ", ".join(parts)
        for extra in extras:
            line += f", {extra}"

        return line

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict."""
        d = asdict(self)
        d["resolution_mode"] = self.resolution_mode.value
        d["position_mode"] = self.position_mode.value
        d["scale_mode"] = self.scale_mode.value
        d["transform"] = self.transform.value
        d["vrr"] = self.vrr.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> MonitorConfig:
        """Deserialize from a dict."""
        d = dict(d)  # copy
        d["resolution_mode"] = ResolutionMode(d.get("resolution_mode", "explicit"))
        d["position_mode"] = PositionMode(d.get("position_mode", "auto"))
        d["scale_mode"] = ScaleMode(d.get("scale_mode", "explicit"))
        d["transform"] = Transform(d.get("transform", 0))
        d["vrr"] = VRR(d.get("vrr", 0))
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_hyprctl(cls, data: dict) -> MonitorConfig:
        """Create from hyprctl monitors -j output."""
        modes = list(data.get("availableModes", []))

        # VRR: Hyprland JSON returns bool (false/true), map to 0/1
        vrr_raw = data.get("vrr", False)
        if isinstance(vrr_raw, bool):
            vrr_val = VRR.ON if vrr_raw else VRR.OFF
        elif isinstance(vrr_raw, int):
            vrr_val = VRR(vrr_raw)
        else:
            vrr_val = VRR.OFF

        # Note: reserved area from hyprctl reflects runtime state (bars etc.),
        # not user config. We don't import it to avoid writing addreserved
        # for values set by other programs.

        disabled = data.get("disabled", False)
        raw_x = data.get("x", 0)
        raw_y = data.get("y", 0)

        # Disabled monitors report x=-1, y=-1; use auto positioning
        if disabled and raw_x < 0 and raw_y < 0:
            pos_mode = PositionMode.AUTO
            raw_x = 0
            raw_y = 0
        else:
            pos_mode = PositionMode.EXPLICIT

        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            make=data.get("make", ""),
            model=data.get("model", ""),
            serial=data.get("serial", ""),
            width=data.get("width", 1920),
            height=data.get("height", 1080),
            refresh_rate=round(data.get("refreshRate", 60.0), 3),
            resolution_mode=ResolutionMode.EXPLICIT,
            available_modes=modes,
            x=raw_x,
            y=raw_y,
            position_mode=pos_mode,
            scale=data.get("scale", 1.0),
            scale_mode=ScaleMode.EXPLICIT,
            transform=Transform(data.get("transform", 0)),
            enabled=not disabled,
            vrr=vrr_val,
        )

    @classmethod
    def from_sway_output(cls, data: dict) -> MonitorConfig:
        """Create from swaymsg -t get_outputs JSON output."""
        # Sway doesn't have a 'description' field — reconstruct from components
        make = data.get("make", "")
        model = data.get("model", "")
        serial = data.get("serial", "")
        description = f"{make} {model} {serial}".strip()

        # Current mode
        current_mode = data.get("current_mode", {})
        width = current_mode.get("width", 1920)
        height = current_mode.get("height", 1080)
        # Sway reports refresh in millihertz
        refresh_mhz = current_mode.get("refresh", 60000)
        refresh_rate = round(refresh_mhz / 1000.0, 3)

        # Available modes
        modes: list[str] = []
        for m in data.get("modes", []):
            mw = m.get("width", 0)
            mh = m.get("height", 0)
            mr = round(m.get("refresh", 0) / 1000.0, 3)
            modes.append(f"{mw}x{mh}@{mr:.3f}Hz")

        # Position
        rect = data.get("rect", {})
        raw_x = rect.get("x", 0)
        raw_y = rect.get("y", 0)

        # Scale: -1 means output is disabled in Sway
        raw_scale = data.get("scale", 1.0)
        if raw_scale < 0:
            enabled = False
            scale = 1.0
            pos_mode = PositionMode.AUTO
            raw_x = 0
            raw_y = 0
        else:
            enabled = data.get("active", True)
            scale = raw_scale
            pos_mode = PositionMode.EXPLICIT

        # Transform
        transform_str = data.get("transform", "normal")
        transform_val = cls._SWAY_TRANSFORMS_INV.get(transform_str, 0)

        # Adaptive sync → VRR
        adaptive = data.get("adaptive_sync_status", "disabled")
        vrr_val = VRR.ON if adaptive == "enabled" else VRR.OFF

        return cls(
            name=data.get("name", ""),
            description=description,
            make=make,
            model=model,
            serial=serial,
            width=width,
            height=height,
            refresh_rate=refresh_rate,
            resolution_mode=ResolutionMode.EXPLICIT,
            available_modes=modes,
            x=raw_x,
            y=raw_y,
            position_mode=pos_mode,
            scale=scale,
            scale_mode=ScaleMode.EXPLICIT,
            transform=Transform(transform_val),
            enabled=enabled,
            vrr=vrr_val,
        )

    @classmethod
    def from_niri_output(cls, name: str, data: dict) -> MonitorConfig:
        """Create from Niri IPC Outputs JSON (name is the connector like "DP-2")."""
        make = data.get("make", "")
        model = data.get("model", "")
        serial = data.get("serial") or ""
        parts = [p for p in (make, model, serial) if p]
        description = " ".join(parts)

        # Current mode
        modes_list = data.get("modes", [])
        current_mode_idx = data.get("current_mode")
        if current_mode_idx is not None and 0 <= current_mode_idx < len(modes_list):
            current_mode = modes_list[current_mode_idx]
        else:
            current_mode = {}
        width = current_mode.get("width", 1920)
        height = current_mode.get("height", 1080)
        # Niri reports refresh in millihertz
        refresh_mhz = current_mode.get("refresh_rate", 60000)
        refresh_rate = round(refresh_mhz / 1000.0, 3)

        # Available modes
        available: list[str] = []
        for m in modes_list:
            mw = m.get("width", 0)
            mh = m.get("height", 0)
            mr = round(m.get("refresh_rate", 0) / 1000.0, 3)
            available.append(f"{mw}x{mh}@{mr:.3f}Hz")

        # Logical info (position, scale, transform) — null if disabled
        logical = data.get("logical")
        if logical is not None:
            enabled = True
            raw_x = logical.get("x", 0)
            raw_y = logical.get("y", 0)
            scale = logical.get("scale", 1.0)
            transform_str = logical.get("transform", "Normal")
            transform_val = cls._NIRI_TRANSFORMS_INV.get(transform_str, 0)
            pos_mode = PositionMode.EXPLICIT
        else:
            enabled = False
            raw_x = 0
            raw_y = 0
            scale = 1.0
            transform_val = 0
            pos_mode = PositionMode.AUTO

        # VRR
        vrr_enabled = data.get("vrr_enabled", False)
        vrr_val = VRR.ON if vrr_enabled else VRR.OFF

        return cls(
            name=name,
            description=description,
            make=make,
            model=model,
            serial=serial,
            width=width,
            height=height,
            refresh_rate=refresh_rate,
            resolution_mode=ResolutionMode.EXPLICIT,
            available_modes=available,
            x=raw_x,
            y=raw_y,
            position_mode=pos_mode,
            scale=scale,
            scale_mode=ScaleMode.EXPLICIT,
            transform=Transform(transform_val),
            enabled=enabled,
            vrr=vrr_val,
        )


# ── WorkspaceRule ────────────────────────────────────────────────────────

@dataclass
class WorkspaceRule:
    workspace: str = ""         # workspace number or name
    monitor: str = ""           # monitor name/description
    default: bool = False
    persistent: bool = False
    rounding: int = -1          # -1 = unset
    decorate: int = -1          # -1 = unset
    gapsin: int = -1
    gapsout: int = -1
    border: int = -1            # -1 = unset
    bordersize: int = -1
    on_created_empty: str = ""

    def to_hyprland_line(self, name_to_id: dict[str, str] | None = None) -> str:
        """Generate a workspace rule line for hyprland.conf."""
        parts: list[str] = [self.workspace]

        if self.monitor:
            monitor_id = (
                name_to_id[self.monitor]
                if name_to_id and self.monitor in name_to_id
                else self.monitor
            )
            parts.append(f"monitor:{monitor_id}")
        if self.default:
            parts.append("default:true")
        if self.persistent:
            parts.append("persistent:true")
        if self.rounding >= 0:
            parts.append(f"rounding:{self.rounding}")
        if self.decorate >= 0:
            parts.append(f"decorate:{self.decorate}")
        if self.gapsin >= 0:
            parts.append(f"gapsin:{self.gapsin}")
        if self.gapsout >= 0:
            parts.append(f"gapsout:{self.gapsout}")
        if self.border >= 0:
            parts.append(f"border:{self.border}")
        if self.bordersize >= 0:
            parts.append(f"bordersize:{self.bordersize}")
        if self.on_created_empty:
            parts.append(f"on-created-empty:{self.on_created_empty}")

        return "workspace=" + ", ".join(parts)

    def to_sway_line(self, name_to_id: dict[str, str] | None = None) -> str:
        """Generate a workspace assignment line for sway config.

        Sway only supports ``workspace N output NAME``.
        """
        if self.workspace and self.monitor:
            monitor_id = (
                name_to_id[self.monitor]
                if name_to_id and self.monitor in name_to_id
                else self.monitor
            )
            return f"workspace {self.workspace} output {monitor_id}"
        return ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> WorkspaceRule:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_hyprland_line(cls, line: str) -> WorkspaceRule | None:
        """Parse a ``workspace=...`` line from a Hyprland config file."""
        line = line.strip()
        if not line.startswith("workspace="):
            return None

        content = line[len("workspace="):]
        parts = [p.strip() for p in content.split(",")]
        if not parts:
            return None

        rule = cls(workspace=parts[0])

        _INT_FIELDS = {
            "rounding": "rounding",
            "decorate": "decorate",
            "gapsin": "gapsin",
            "gapsout": "gapsout",
            "border": "border",
            "bordersize": "bordersize",
        }

        for part in parts[1:]:
            if part.startswith("monitor:"):
                rule.monitor = part[8:]
            elif part == "default:true":
                rule.default = True
            elif part == "persistent:true":
                rule.persistent = True
            elif part.startswith("on-created-empty:"):
                rule.on_created_empty = part[17:]
            else:
                for prefix, attr in _INT_FIELDS.items():
                    if part.startswith(f"{prefix}:"):
                        try:
                            setattr(rule, attr, int(part[len(prefix) + 1:]))
                        except ValueError:
                            pass
                        break

        return rule


# ── Profile ──────────────────────────────────────────────────────────────

@dataclass
class Profile:
    name: str = ""
    monitors: list[MonitorConfig] = field(default_factory=list)
    workspace_rules: list[WorkspaceRule] = field(default_factory=list)

    @property
    def fingerprint(self) -> list[str]:
        """Sorted list of monitor descriptions for matching."""
        return sorted(m.description for m in self.monitors if m.description)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "monitors": [m.to_dict() for m in self.monitors],
            "workspace_rules": [w.to_dict() for w in self.workspace_rules],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Profile:
        return cls(
            name=d.get("name", ""),
            monitors=[MonitorConfig.from_dict(m) for m in d.get("monitors", [])],
            workspace_rules=[WorkspaceRule.from_dict(w) for w in d.get("workspace_rules", [])],
        )

    def generate_config(self, use_description: bool = False) -> str:
        """Generate the full monitors.conf content for Hyprland."""
        # Build name→identifier mapping for workspace rules and mirror references
        name_to_id: dict[str, str] = {}
        for m in self.monitors:
            if use_description and m.description:
                name_to_id[m.name] = f"desc:{m.description}"
            else:
                name_to_id[m.name] = m.name

        lines: list[str] = []
        lines.append("# Generated by Monique — https://github.com/ToRvaLDz/monique")
        lines.append("")
        for m in self.monitors:
            lines.append(m.to_hyprland_line(
                use_description=use_description, name_to_id=name_to_id,
            ))
        if self.workspace_rules:
            lines.append("")
            for w in self.workspace_rules:
                lines.append(w.to_hyprland_line(name_to_id=name_to_id))
        lines.append("")
        return "\n".join(lines)

    def generate_sway_config(self, use_description: bool = False) -> str:
        """Generate the full monitors.conf content for Sway."""
        # Build name→identifier mapping for workspace rules
        name_to_id: dict[str, str] = {}
        for m in self.monitors:
            if use_description and m.description:
                name_to_id[m.name] = f'"{m.description}"'
            else:
                name_to_id[m.name] = m.name

        blocks: list[str] = ["# Generated by Monique — https://github.com/ToRvaLDz/monique"]
        for m in self.monitors:
            blocks.append(m.to_sway_block(use_description=use_description))
        ws_lines = [
            w.to_sway_line(name_to_id=name_to_id)
            for w in self.workspace_rules
            if w.to_sway_line(name_to_id=name_to_id)
        ]
        if ws_lines:
            blocks.append("\n".join(ws_lines))
        return "\n\n".join(blocks) + "\n"

    def generate_niri_config(
        self, use_description: bool = False,
        niri_ids: dict[str, str] | None = None,
    ) -> str:
        """Generate the full monitors.kdl content for Niri."""
        blocks: list[str] = ["// Generated by Monique — https://github.com/ToRvaLDz/monique"]
        for m in self.monitors:
            blocks.append(m.to_niri_block(
                use_description=use_description, niri_ids=niri_ids,
            ))
        return "\n\n".join(blocks) + "\n"

    def generate_xsetup_script(self) -> str:
        """Generate an Xsetup shell script with xrandr commands for SDDM.

        Compositor positions are in logical (scaled) coordinates, but xrandr
        uses physical pixel positions.  This method converts the layout by
        sorting monitors on each axis and accumulating physical dimensions.
        All outputs are configured in a single ``xrandr`` invocation so the
        kernel applies the modeset atomically.
        """
        phys_pos = self._compute_physical_positions()

        parts = ["xrandr"]
        for m in self.monitors:
            px, py = phys_pos.get(m.name, (m.x, m.y))
            parts.append("  " + m.to_xrandr_args(phys_x=px, phys_y=py))

        cmd = " \\\n".join(parts)
        lines = [
            "#!/bin/sh",
            "# Generated by Monique — https://github.com/ToRvaLDz/monique",
            cmd,
            "",
        ]
        return "\n".join(lines)

    def _compute_physical_positions(self) -> dict[str, tuple[int, int]]:
        """Convert logical compositor positions to physical xrandr positions.

        Groups monitors into horizontal rows (by logical y) and places them
        left-to-right within each row using their physical dimensions.
        """
        enabled = [m for m in self.monitors if m.enabled]
        if not enabled:
            return {}

        # Group by approximate logical y (within 50px tolerance)
        rows: list[list[MonitorConfig]] = []
        for m in sorted(enabled, key=lambda m: (m.y, m.x)):
            placed = False
            for row in rows:
                if abs(m.y - row[0].y) < 50:
                    row.append(m)
                    placed = True
                    break
            if not placed:
                rows.append([m])

        # Sort rows by y, monitors within row by x
        rows.sort(key=lambda row: row[0].y)
        for row in rows:
            row.sort(key=lambda m: m.x)

        result: dict[str, tuple[int, int]] = {}
        phys_y = 0
        for row in rows:
            phys_x = 0
            row_height = 0
            for m in row:
                result[m.name] = (phys_x, phys_y)
                pw, ph = m.physical_size_rotated
                phys_x += pw
                row_height = max(row_height, ph)
            phys_y += row_height

        return result


# ── Clamshell Mode ────────────────────────────────────────────────────


def apply_clamshell(monitors: list[MonitorConfig]) -> bool:
    """Disable internal displays when external monitors are present and enabled.

    Safety: does nothing if there are no enabled external monitors.
    Returns True if any monitor was changed.
    """
    internals = [m for m in monitors if m.is_internal and m.enabled]
    externals = [m for m in monitors if not m.is_internal and m.enabled]
    if not internals or not externals:
        return False
    for m in internals:
        m.enabled = False
    return True


def undo_clamshell(monitors: list[MonitorConfig]) -> bool:
    """Re-enable internal displays that were disabled.

    Returns True if any monitor was changed.
    """
    changed = False
    for m in monitors:
        if m.is_internal and not m.enabled:
            m.enabled = True
            changed = True
    return changed
