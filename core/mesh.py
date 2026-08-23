from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np
import trimesh
from shapely.geometry import GeometryCollection, LineString, Polygon
from shapely.ops import nearest_points, unary_union

from .models import ToolSettings


@dataclass(frozen=True)
class BridgeAnalysis:
    wall_components: int = 1
    bridge_count: int = 0
    connected: bool = True
    enabled: bool = False

    @property
    def required(self) -> bool:
        return self.wall_components > 1


@dataclass
class GeneratedModel:
    components: dict[str, trimesh.Trimesh]
    bridge_analysis: BridgeAnalysis = field(default_factory=BridgeAnalysis)
    structural_mesh: trimesh.Trimesh | None = None
    export_error: str | None = None

    @property
    def mesh(self) -> trimesh.Trimesh:
        return self.structural_mesh or trimesh.util.concatenate(list(self.components.values()))


def _polygons(shape):
    if shape.is_empty:
        return []
    if isinstance(shape, Polygon):
        return [shape]
    return [x for x in getattr(shape, "geoms", []) if isinstance(x, Polygon)]


def extrude(shape, height: float, z: float = 0.0) -> trimesh.Trimesh:
    meshes = [trimesh.creation.extrude_polygon(p, height) for p in _polygons(shape)]
    if not meshes:
        raise ValueError("No printable area was generated.")
    result = trimesh.util.concatenate(meshes)
    result.apply_translation((0, 0, z))
    return result


def _wall(outline, thickness: float):
    return outline.buffer(thickness / 2, join_style=2).difference(outline.buffer(-thickness / 2, join_style=2)).buffer(0)


def _bridge_path(start, end, mode: str) -> LineString:
    """Choose a deterministic bridge path between two wall loops."""
    if mode == "Horizontal":
        return LineString([start, (end.x, start.y), end])
    if mode == "Vertical":
        return LineString([start, (start.x, end.y), end])
    return LineString([start, end])


def _low_profile_bridges(wall, mode: str, width: float) -> tuple[object, BridgeAnalysis]:
    """Connect every cutter-wall island with a minimum spanning support web.

    The web overlaps its adjacent walls, is extruded only near the blade top,
    and is therefore structurally useful without obstructing the cutting edge.
    """
    pieces = _polygons(wall)
    count = len(pieces)
    if count < 2:
        return GeometryCollection(), BridgeAnalysis(wall_components=count or 1)
    if mode == "None":
        return GeometryCollection(), BridgeAnalysis(wall_components=count, connected=False, enabled=False)

    # Prim's algorithm: join all disconnected walls using the shortest total web.
    main = max(range(count), key=lambda index: pieces[index].area)
    connected = {main}
    remaining = set(range(count)) - connected
    bridge_shapes = []
    bridge_width = max(float(width), 0.01)
    while remaining:
        best = None
        for left in connected:
            for right in remaining:
                start, end = nearest_points(pieces[left], pieces[right])
                distance = start.distance(end)
                candidate = (distance, left, right, start, end)
                if best is None or candidate[0] < best[0]:
                    best = candidate
        _, left, right, start, end = best
        path = _bridge_path(start, end, mode)
        # Square caps overlap both cutter walls, producing a printable fused web.
        bridge_shapes.append(path.buffer(bridge_width / 2, cap_style=3, join_style=2))
        connected.add(right)
        remaining.remove(right)

    bridges = unary_union(bridge_shapes).buffer(0)
    merged = unary_union([wall, bridges]).buffer(0)
    is_connected = len(_polygons(merged)) == 1
    analysis = BridgeAnalysis(
        wall_components=count,
        bridge_count=len(bridge_shapes),
        connected=is_connected,
        enabled=True,
    )
    if not is_connected:
        raise ValueError("Automatic support webs could not connect all cutter walls. Adjust the trace or bridge width.")
    return bridges, analysis


def _center_bar(shape, mode: str, width: float):
    if mode == "None" or shape.geom_type != "MultiPolygon":
        return shape
    minx, miny, maxx, maxy = shape.bounds
    from shapely.geometry import box
    horizontal = mode == "Horizontal" or (mode == "Auto" and (maxx - minx) >= (maxy - miny))
    bar = box(minx, (miny + maxy - width) / 2, maxx, (miny + maxy + width) / 2) if horizontal else box((minx + maxx - width) / 2, miny, (minx + maxx + width) / 2, maxy)
    return unary_union([shape, bar]).buffer(0)


def _fuse_one_piece(meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    """Boolean-union structural cutter parts and require one manifold body."""
    fused = trimesh.boolean.union(meshes, engine="manifold", check_volume=False)
    if fused is None or not fused.is_watertight:
        raise ValueError("Structural cutter union is not watertight.")
    if len(fused.split(only_watertight=False)) != 1:
        raise ValueError("Structural cutter union contains disconnected pieces.")
    return fused


def generate(outline, settings: ToolSettings) -> GeneratedModel:
    if settings.mirror:
        from shapely import affinity
        outline = affinity.scale(outline, xfact=-1, yfact=1, origin="center")
    g = settings.generator
    wall = _wall(outline, settings.blade_thickness_mm)
    cutter_generators = {"Cookie cutter", "Imprint cutter", "Cutter + stamp", "Sandwich sealer", "Multi-cutter"}
    if g in cutter_generators:
        bridges, bridge_analysis = _low_profile_bridges(wall, settings.center_bars, settings.center_bar_width_mm)
    else:
        bridges, bridge_analysis = GeometryCollection(), BridgeAnalysis()
    components: dict[str, trimesh.Trimesh] = {}
    structural_mesh = None
    export_error = None
    if g in cutter_generators:
        components["cutter"] = extrude(wall, settings.blade_height_mm)
        if not bridges.is_empty:
            bridge_height = min(settings.bridge_height_mm, settings.blade_height_mm)
            components["bridge"] = extrude(bridges, bridge_height, settings.blade_height_mm - bridge_height)
        if settings.support_blade:
            support = _wall(outline.buffer(settings.handle_width_mm), settings.blade_thickness_mm)
            components["support"] = extrude(support, settings.blade_height_mm - settings.chamfer_height_mm, settings.chamfer_height_mm)
        # This exterior ring overlaps the cutter wall so it can be fused into one body.
        handle = outline.buffer(settings.handle_width_mm).difference(outline)
        components["handle"] = extrude(handle, settings.handle_height_mm, settings.blade_height_mm - settings.handle_height_mm)
        if g == "Imprint cutter":
            details = outline.buffer(-settings.blade_thickness_mm * 1.25)
            components["imprint"] = extrude(details, settings.imprint_depth_mm, settings.blade_height_mm - settings.imprint_depth_mm)
    elif g in {"Stamp", "Embosser", "Debosser", "Cake-pop mold"}:
        base = outline.buffer(settings.handle_width_mm)
        components["base"] = extrude(base, settings.handle_height_mm)
        components["relief"] = extrude(outline, settings.relief_height_mm, settings.handle_height_mm)
    elif g == "Stencil":
        frame = outline.envelope.buffer(settings.handle_width_mm).difference(outline)
        components["stencil"] = extrude(frame, max(1.0, settings.imprint_thickness_mm))
    elif g == "Cake topper":
        stem_w = max(2.0, settings.handle_width_mm)
        minx, miny, maxx, _ = outline.bounds
        from shapely.geometry import box
        components["topper"] = extrude(unary_union([outline, box((minx + maxx - stem_w)/2, miny - 60, (minx + maxx + stem_w)/2, miny)]), settings.imprint_thickness_mm)
    else:
        raise ValueError(f"Unsupported generator: {g}")
    if g == "Cutter + stamp":
        stamp_base = outline.buffer(settings.clearance_mm + settings.handle_width_mm)
        components["stamp"] = extrude(stamp_base, settings.handle_height_mm)

    # These generators promise a single printable cutter body. Other recipes may
    # deliberately contain separate functional pieces (such as a stamp set).
    one_piece_generators = {"Cookie cutter", "Sandwich sealer", "Multi-cutter"}
    if g in one_piece_generators:
        if bridge_analysis.required and not bridge_analysis.connected:
            export_error = "Disconnected cutter walls require low-profile support webs before export."
        else:
            try:
                structural_mesh = _fuse_one_piece(list(components.values()))
            except ValueError as exc:
                export_error = str(exc)
    return GeneratedModel(components, bridge_analysis, structural_mesh, export_error)


def export_bytes(model: GeneratedModel, fmt: str) -> bytes:
    if model.export_error:
        raise ValueError(model.export_error)
    fmt = fmt.lower()
    if fmt == "3mf":
        fmt = "3mf"
    return model.mesh.export(file_type=fmt)


def glb_bytes(model: GeneratedModel) -> bytes:
    scene = trimesh.Scene(model.components)
    return scene.export(file_type="glb")
