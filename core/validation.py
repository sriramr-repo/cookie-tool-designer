from __future__ import annotations

from .mesh import BridgeAnalysis
from .models import PrinterProfile, ToolSettings


def validate(mesh, settings: ToolSettings, printer: PrinterProfile, bridge_analysis: BridgeAnalysis | None = None, export_error: str | None = None) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = []
    min_feature = max(printer.nozzle_mm * 1.2, 0.5)
    if settings.blade_thickness_mm < min_feature:
        messages.append(("error", f"Blade thickness is below the {min_feature:.2f} mm printable minimum for this nozzle."))
    if settings.sharp_tip and settings.tip_width_mm < printer.nozzle_mm:
        messages.append(("warning", "Sharp tip is narrower than the nozzle and may be rounded by the slicer."))
    extents = mesh.extents
    limits = (printer.build_x_mm, printer.build_y_mm, printer.build_z_mm)
    if any(a > b for a, b in zip(extents, limits)):
        messages.append(("error", "Model exceeds the configured build volume."))
    if not mesh.is_watertight:
        messages.append(("error", "Generated mesh is not watertight."))
    if export_error:
        messages.append(("error", f"Export blocked: {export_error}"))
    if bridge_analysis and bridge_analysis.required:
        if bridge_analysis.connected:
            per_island = ", ".join(str(count) for count in bridge_analysis.island_web_counts)
            messages.append((
                "success",
                f"{bridge_analysis.bridge_count} low-profile support web(s) connect all cutter walls "
                f"({per_island} web(s) per floating island).",
            ))
        else:
            messages.append(("warning", "Disconnected cutter walls have no support web and will print as separate pieces."))
    if bridge_analysis and bridge_analysis.enabled and settings.center_bar_width_mm < min_feature:
        messages.append(("warning", f"Bridge width is below the {min_feature:.2f} mm printable minimum for this nozzle."))
    # A combined scene may intentionally contain a cutter and separate stamp.
    # Do not depend on optional graph packages merely to count those pieces.
    if not messages:
        messages.append(("success", "Mesh is watertight and fits the selected printer profile."))
    return messages
