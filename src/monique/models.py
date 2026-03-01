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

    # HDR / EDID Override (Hyprland monitorv2 only)
    hdr: bool = False
    sdr_eotf: int = 0              # 0=global, 1=sRGB, 2=Gamma 2.2
    supports_hdr: int = 0          # 0=auto, 1=force on
    supports_wide_color: int = 0   # 0=auto, 1=force on
    sdr_min_luminance: float = 0.0
    sdr_max_luminance: float = 0.0
    min_luminance: float = 0.0
    max_luminance: float = 0.0
    max_avg_luminance: float = 0.0

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

    # Mapping from Transform enum (CCW, Wayland protocol) to Sway config.
    # Sway rotates CLOCKWISE while the Wayland protocol / Hyprland use CCW,
    # so 90° CCW (enum 1) becomes Sway "270" (270° CW) and vice-versa.
    _SWAY_TRANSFORMS: ClassVar[dict[int, str]] = {
        0: "normal",
        1: "270",
        2: "180",
        3: "90",
        4: "flipped",
        5: "flipped-270",
        6: "flipped-180",
        7: "flipped-90",
    }

    # Inverse mapping: Sway transform string -> Transform enum value
    _SWAY_TRANSFORMS_INV: ClassVar[dict[str, int]] = {
        v: k for k, v in _SWAY_TRANSFORMS.items()
    }

    # Mapping from Transform enum (CCW) to Niri config strings.
    # Niri follows the Wayland protocol CCW convention, so values map 1:1.
    _NIRI_TRANSFORMS: ClassVar[dict[int, str]] = {
        0: "normal",
        1: "90",
        2: "180",
        3: "270",
        4: "flipped",
        5: "flipped-90",
        6: "flipped-180",
        7: "flipped-270",
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
            elif niri_ids is None and self.make:
                # No Niri IPC available (cross-write from another compositor).
                # Reconstruct the Niri-native description from make/model/serial.
                # Match primarily by serial; fall back to model if unavailable.
                make = self.make
                if len(make) == 3 and make.isalpha() and make.isupper():
                    make = f"PNP({make})"
                serial = self.serial if self.serial and self.serial != "Unknown" else ""
                parts = [p for p in (make, self.model, serial) if p]
                identifier = f'"{" ".join(parts)}"'
            else:
                # Mapping available but monitor not in it, or no make info;
                # fall back to connector name
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

        # Transform (Niri uses CCW like Wayland protocol, different from Sway CW)
        transform_str = self._NIRI_TRANSFORMS[self.transform.value]
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

    def to_hyprland_v2_block(
        self,
        use_description: bool = False,
        name_to_id: dict[str, str] | None = None,
    ) -> str:
        """Generate a ``monitorv2 { … }`` config block for Hyprland >= 0.50."""
        lines: list[str] = []

        # Output identifier (must be first attribute)
        if use_description and self.description:
            lines.append(f"  output = desc:{self.description}")
        else:
            lines.append(f"  output = {self.name}")

        # Disabled monitor
        if not self.enabled:
            lines.append("  disabled = 1")
            return "monitorv2 {\n" + "\n".join(lines) + "\n}"

        # Mode (resolution@refresh)
        if self.resolution_mode == ResolutionMode.EXPLICIT:
            refresh = f"{self.refresh_rate:g}"
            lines.append(f"  mode = {self.width}x{self.height}@{refresh}")
        else:
            lines.append(f"  mode = {self.resolution_mode.value}")

        # Position
        if self.position_mode == PositionMode.EXPLICIT:
            lines.append(f"  position = {self.x}x{self.y}")
        else:
            lines.append(f"  position = {self.position_mode.value}")

        # Scale
        if self.scale_mode == ScaleMode.AUTO:
            lines.append("  scale = auto")
        else:
            lines.append(f"  scale = {self.scale:g}")

        # Transform
        if self.transform != Transform.NORMAL:
            lines.append(f"  transform = {self.transform.value}")

        # Mirror
        if self.mirror_of:
            mirror_id = self.mirror_of
            if name_to_id and self.mirror_of in name_to_id:
                mirror_id = name_to_id[self.mirror_of]
            lines.append(f"  mirror = {mirror_id}")

        # Bitdepth
        if self.bitdepth != 8:
            lines.append(f"  bitdepth = {self.bitdepth}")

        # VRR
        if self.vrr != VRR.OFF:
            lines.append(f"  vrr = {self.vrr.value}")

        # Color management (hdr bool falls back to cm = hdr if no explicit cm set)
        cm = self.color_management or ("hdr" if self.hdr else "")
        if cm:
            lines.append(f"  cm = {cm}")

        # SDR brightness / saturation
        if self.sdr_brightness != 1.0:
            lines.append(f"  sdrbrightness = {self.sdr_brightness:g}")
        if self.sdr_saturation != 1.0:
            lines.append(f"  sdrsaturation = {self.sdr_saturation:g}")

        # Reserved area (space-separated in v2)
        if any((self.reserved_top, self.reserved_bottom,
                self.reserved_left, self.reserved_right)):
            lines.append(
                f"  addreserved = {self.reserved_top} {self.reserved_bottom} "
                f"{self.reserved_left} {self.reserved_right}"
            )

        # HDR / EDID Override
        if self.sdr_eotf != 0:
            lines.append(f"  sdr_eotf = {self.sdr_eotf}")
        if self.supports_hdr != 0:
            lines.append(f"  supports_hdr = {self.supports_hdr}")
        if self.supports_wide_color != 0:
            lines.append(f"  supports_wide_color = {self.supports_wide_color}")
        if self.sdr_min_luminance != 0.0:
            lines.append(f"  sdr_min_luminance = {self.sdr_min_luminance:g}")
        if self.sdr_max_luminance != 0.0:
            lines.append(f"  sdr_max_luminance = {self.sdr_max_luminance:g}")
        if self.min_luminance != 0.0:
            lines.append(f"  min_luminance = {self.min_luminance:g}")
        if self.max_luminance != 0.0:
            lines.append(f"  max_luminance = {self.max_luminance:g}")
        if self.max_avg_luminance != 0.0:
            lines.append(f"  max_avg_luminance = {self.max_avg_luminance:g}")

        return "monitorv2 {\n" + "\n".join(lines) + "\n}"

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

_XSETUP_TEMPLATE = '''\
#!/usr/bin/env python3
"""SDDM Xsetup — Generated by Monique.

Matches monitors by EDID description so the script works regardless of
whether the X11 driver uses the same output names as the Wayland compositor
(e.g. NVIDIA uses DFP-* instead of DP-*/HDMI-A-*).
"""
import re, subprocess, sys, time

# (edid_description, wayland_name, xrandr_args_with_wayland_name)
MONITORS = {monitors}
FB_SIZE = "{fb_size}"


def _parse_edid(hex_str):
    """Extract (monitor_name, serial) from raw EDID hex."""
    try:
        data = bytes.fromhex(hex_str)
    except ValueError:
        return "", ""
    name = ""
    serial = ""
    for off in (54, 72, 90, 108):
        if off + 18 > len(data):
            break
        tag = data[off + 3]
        text = data[off + 5 : off + 18].split(b"\\x0a")[0]
        text = text.decode("ascii", errors="ignore").strip()
        if tag == 0xFC and not name:
            name = text
        elif tag == 0xFF and not serial:
            serial = text
    return name, serial


def _get_edid_map():
    """Return {{x11_output: (edid_name, edid_serial)}} for connected outputs."""
    try:
        r = subprocess.run(
            ["xrandr", "--verbose"], capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return {{}}
    result = {{}}
    cur = None
    edid = ""
    in_edid = False
    for line in r.stdout.splitlines():
        m = re.match(r"^(\\S+)\\s+connected", line)
        if m:
            if cur and edid:
                result[cur] = _parse_edid(edid)
            cur = m.group(1)
            edid = ""
            in_edid = False
            continue
        if re.match(r"^\\s+EDID:", line):
            in_edid = True
            continue
        if in_edid:
            s = line.strip()
            if re.match(r"^[0-9a-f]{{2,}}$", s):
                edid += s
            else:
                in_edid = False
    if cur and edid:
        result[cur] = _parse_edid(edid)
    return result


def _resolve(monitors, edid_map):
    """Return list of xrandr arg strings with correct X11 output names."""
    connected = set(edid_map)
    wayland_names = {{name for _, name, _ in monitors}}

    # Fast path: all Wayland names exist in X11 (Intel/AMD)
    if wayland_names <= connected:
        return [args for _, _, args in monitors]

    # EDID matching: map profile description -> X11 output
    avail = dict(edid_map)
    matched = {{}}  # index -> x11_name

    # Pass 1: match by EDID model name (tag FC)
    for i, (desc, _, _) in enumerate(monitors):
        for x11, (ename, _eser) in list(avail.items()):
            if ename and ename in desc:
                matched[i] = x11
                del avail[x11]
                break

    # Pass 2: match by EDID serial (tag FF)
    for i, (desc, _, _) in enumerate(monitors):
        if i in matched:
            continue
        for x11, (_ename, eser) in list(avail.items()):
            if eser and eser in desc:
                matched[i] = x11
                del avail[x11]
                break

    # Pass 3: pair remaining 1:1
    unmatched = [i for i in range(len(monitors)) if i not in matched]
    remaining = list(avail)
    for i, x11 in zip(unmatched, remaining):
        matched[i] = x11

    # Build final args, replacing output names
    result = []
    for i, (_, wl_name, args) in enumerate(monitors):
        x11 = matched.get(i, wl_name)
        result.append(args.replace("--output " + wl_name, "--output " + x11, 1))
    return result


def main():
    lf = open("/tmp/monique-xsetup.log", "w")
    def _log(msg):
        lf.write(msg + "\\n")
        lf.flush()

    _log("Monique Xsetup — " + time.strftime("%Y-%m-%d %H:%M:%S"))

    edid_map = _get_edid_map()
    _log("EDID map: " + repr(edid_map))

    args = _resolve(MONITORS, edid_map)
    _log("Resolved args: " + repr(args))

    # Detect used X11 output names
    used = set()
    for a in args:
        m = re.match(r"--output\\s+(\\S+)", a)
        if m:
            used.add(m.group(1))

    # Disable connected outputs not in our layout
    for x11 in sorted(edid_map):
        if x11 not in used:
            args.append("--output " + x11 + " --off")
            _log("Disabling unused output: " + x11)

    cmd = "xrandr --fb " + FB_SIZE + " " + " ".join(args)
    _log("Command: " + cmd)

    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    _log("Return code: " + str(r.returncode))
    if r.stdout.strip():
        _log("stdout: " + r.stdout.strip())
    if r.stderr.strip():
        _log("stderr: " + r.stderr.strip())
    lf.close()


if __name__ == "__main__":
    main()
'''


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

    def generate_config(self, use_description: bool = False, use_v2: bool = False) -> str:
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
        if use_v2:
            for m in self.monitors:
                lines.append(m.to_hyprland_v2_block(
                    use_description=use_description, name_to_id=name_to_id,
                ))
                lines.append("")
        else:
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
        """Generate an Xsetup Python script with EDID-based output matching.

        Compositor positions are in logical (scaled) coordinates, but xrandr
        uses physical pixel positions.  This method converts the layout by
        sorting monitors on each axis and accumulating physical dimensions.

        The generated script matches monitors by EDID description rather than
        port name, so it works on systems where the X11 driver uses different
        output names than the Wayland compositor (e.g. NVIDIA DFP-* names).
        """
        phys_pos = self._compute_physical_positions()

        monitors_data: list[tuple[str, str, str]] = []
        fb_w = 0
        fb_h = 0
        for m in self.monitors:
            if not m.enabled:
                continue  # skip disabled monitors; xrandr leaves them at X11 default
            px, py = phys_pos.get(m.name, (m.x, m.y))
            args = m.to_xrandr_args(phys_x=px, phys_y=py)
            monitors_data.append((m.description, m.name, args))
            pw, ph = m.physical_size_rotated
            fb_w = max(fb_w, px + pw)
            fb_h = max(fb_h, py + ph)

        return _XSETUP_TEMPLATE.format(
            monitors=repr(monitors_data),
            fb_size=f"{fb_w}x{fb_h}",
        )

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
