from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TraceSettings:
    threshold: int = 160
    invert: bool = False
    simplify_mm: float = 0.15
    target_width_mm: float = 85.0
    min_feature_mm: float = 0.55


@dataclass
class ToolSettings:
    generator: str = "Cookie cutter"
    blade_height_mm: float = 15.0
    blade_thickness_mm: float = 1.2
    sharp_tip: bool = True
    tip_width_mm: float = 0.5
    chamfer_height_mm: float = 2.5
    support_blade: bool = False
    handle_height_mm: float = 5.0
    handle_width_mm: float = 3.0
    handle_shape: str = "Rounded"
    imprint_depth_mm: float = 2.0
    imprint_thickness_mm: float = 1.0
    relief_height_mm: float = 3.0
    clearance_mm: float = 0.35
    center_bars: str = "Auto"
    center_bar_width_mm: float = 1.5
    bridge_height_mm: float = 1.2
    mirror: bool = False


@dataclass
class PrinterProfile:
    name: str = "Anycubic Kobra S1"
    nozzle_mm: float = 0.4
    build_x_mm: float = 250.0
    build_y_mm: float = 250.0
    build_z_mm: float = 250.0
    material: str = "PLA"


@dataclass
class DesignProject:
    version: int = 1
    name: str = "Untitled"
    source_filename: str | None = None
    trace: TraceSettings = field(default_factory=TraceSettings)
    tool: ToolSettings = field(default_factory=ToolSettings)
    printer: PrinterProfile = field(default_factory=PrinterProfile)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DesignProject":
        return cls(
            version=value.get("version", 1), name=value.get("name", "Untitled"),
            source_filename=value.get("source_filename"),
            trace=TraceSettings(**value.get("trace", {})),
            tool=ToolSettings(**value.get("tool", {})),
            printer=PrinterProfile(**value.get("printer", {})),
        )


def projects_root() -> Path:
    return Path.home() / "CookieDesigner" / "Projects"
