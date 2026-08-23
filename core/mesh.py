from __future__ import annotations

import io
import math
from dataclasses import dataclass, field

import numpy as np
import trimesh
from shapely.geometry import GeometryCollection, LineString, Point, Polygon
from shapely.ops import nearest_points, unary_union

from .models import ToolSettings


@dataclass(frozen=True)
class SupportWeb:
    island_index: int
    source: tuple[float, float]
    target: tuple[float, float]
    reason: str
    manual: bool = False


@dataclass(frozen=True)
class BridgeAnalysis:
    wall_components: int = 1
    bridge_count: int = 0
    island_web_counts: tuple[int, ...] = ()
    minimum_required_webs: int = 2
    webs: tuple[SupportWeb, ...] = ()
    unresolved_reasons: tuple[str, ...] = ()
    connected: bool = True
    enabled: bool = False

    @property
    def required(self) -> bool:
        return self.wall_components > 1

    @property
    def isolated_islands(self) -> int:
        return max(0, self.wall_components - 1)

    @property
    def automatic_web_count(self) -> int:
        return sum(not web.manual for web in self.webs)

    @property
    def manual_web_count(self) -> int:
        return sum(web.manual for web in self.webs)

    @property
    def under_supported_islands(self) -> tuple[int, ...]:
        return tuple(index + 1 for index, count in enumerate(self.island_web_counts) if count < self.minimum_required_webs)

    @property
    def unresolved(self) -> bool:
        return bool(self.unresolved_reasons) or bool(self.under_supported_islands) or not self.connected


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


def _inset_web_path(path: LineString, piece, primary, width: float):
    """Move the two web ends inside their intended walls, or reject the route."""
    coordinates = list(path.coords)
    if len(coordinates) < 2:
        return None
    def unit_vector(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        return (dx / length, dy / length) if length else None
    start_direction = unit_vector(coordinates[0], coordinates[1])
    end_direction = unit_vector(coordinates[-2], coordinates[-1])
    if start_direction is None or end_direction is None:
        return None
    overlap = min(width * 0.45, 0.55)
    start_inside = (coordinates[0][0] - start_direction[0] * overlap, coordinates[0][1] - start_direction[1] * overlap)
    end_inside = (coordinates[-1][0] + end_direction[0] * overlap, coordinates[-1][1] + end_direction[1] * overlap)
    inset_path = LineString([start_inside, *coordinates[1:-1], end_inside])
    inner_floor = max(overlap * 0.3, 0.04)
    if not piece.buffer(-inner_floor).covers(Point(start_inside)):
        return None
    if not primary.buffer(-inner_floor).covers(Point(end_inside)):
        return None
    return inset_path


def _boundary_arc(boundary, point, length: float) -> LineString:
    """Return a short local segment that follows the real cutter-wall contour."""
    total = boundary.length
    if total <= 0:
        return LineString()
    midpoint = boundary.project(point)
    samples = 12
    points = []
    for index in range(samples + 1):
        offset = -length / 2 + length * index / samples
        distance = (midpoint + offset) % total if boundary.is_ring else max(0.0, min(total, midpoint + offset))
        points.append(boundary.interpolate(distance))
    return LineString(points)


def _tapered_ribbon(path: LineString, narrow_width: float, landing_width: float):
    """Create a smooth-width ribbon instead of a rectangular bar."""
    total = path.length
    if total <= 0:
        return None
    fractions = (0.0, 0.18, 0.82, 1.0)
    widths = (landing_width, narrow_width, narrow_width, landing_width)
    left, right = [], []
    for fraction, width in zip(fractions, widths):
        distance = total * fraction
        point = path.interpolate(distance)
        epsilon = min(max(total * 0.002, 0.01), total * 0.08)
        before = path.interpolate(max(0.0, distance - epsilon))
        after = path.interpolate(min(total, distance + epsilon))
        dx, dy = after.x - before.x, after.y - before.y
        magnitude = math.hypot(dx, dy)
        if magnitude == 0:
            return None
        nx, ny = -dy / magnitude, dx / magnitude
        half = width / 2
        left.append((point.x + nx * half, point.y + ny * half))
        right.append((point.x - nx * half, point.y - ny * half))
    return Polygon([*left, *reversed(right)]).buffer(0)


def _contour_gusset(path: LineString, piece, primary, source_boundary, target_boundary, width: float):
    """Build a tapered support gusset with pads clipped to both wall contours."""
    inset_path = _inset_web_path(path, piece, primary, width)
    if inset_path is None:
        return None
    landing_width = width * 1.9
    ribbon = _tapered_ribbon(inset_path, width, landing_width)
    if ribbon is None or ribbon.is_empty:
        return None
    # The central span is never wider than the printable web. The wider ends
    # are permitted only inside their own wall bodies, where they form contour-
    # following landing pads rather than protruding tabs.
    corridor = inset_path.buffer(width / 2, cap_style=2, join_style=2)
    allowed = corridor.union(piece).union(primary)
    tapered = ribbon.intersection(allowed)
    pad_length = max(width * 2.6, 2.4)
    source_pad = _boundary_arc(source_boundary, Point(path.coords[0]), pad_length).buffer(landing_width / 2, cap_style=1, join_style=1).intersection(piece)
    target_pad = _boundary_arc(target_boundary, Point(path.coords[-1]), pad_length).buffer(landing_width / 2, cap_style=1, join_style=1).intersection(primary)
    gusset = unary_union([tapered, source_pad, target_pad]).buffer(0)
    return gusset if not gusset.is_empty else None


def _island_span(piece) -> float:
    minx, miny, maxx, maxy = piece.bounds
    return max(maxx - minx, maxy - miny)


def _web_requirement(piece, primary, settings: ToolSettings) -> int:
    """Determine a conservative web count for one floating cutter-wall island."""
    span = _island_span(piece)
    distance = piece.distance(primary)
    # Two separated attachment points are the safe baseline. Larger islands and
    # islands farther from the primary cutter wall receive more support.
    by_span = math.ceil(span / max(settings.max_unsupported_span_mm, 1.0))
    by_distance = math.ceil(distance / max(settings.max_unsupported_span_mm, 1.0))
    return max(int(settings.min_webs_per_island), 2, by_span, by_distance)


def _boundary_vector_score(boundary, point: Point, path_direction: tuple[float, float]) -> tuple[float, float, float]:
    """Score a contour point by flatness and near-normal gusset alignment."""
    total = boundary.length
    if total <= 0:
        return 0.0, math.pi, 0.0
    distance = boundary.project(point)
    step = min(max(total / 320.0, 0.12), max(total * 0.04, 0.12))
    def sample(offset):
        value = (distance + offset) % total if boundary.is_ring else max(0.0, min(total, distance + offset))
        return boundary.interpolate(value)
    before, current, after = sample(-step), sample(0.0), sample(step)
    first, second = (current.x - before.x, current.y - before.y), (after.x - current.x, after.y - current.y)
    first_length, second_length = math.hypot(*first), math.hypot(*second)
    if first_length == 0 or second_length == 0:
        return 0.0, math.pi, 0.0
    first, second = (first[0] / first_length, first[1] / first_length), (second[0] / second_length, second[1] / second_length)
    curvature = math.acos(max(-1.0, min(1.0, first[0] * second[0] + first[1] * second[1])))
    tangent = (first[0] + second[0], first[1] + second[1])
    tangent_length = math.hypot(*tangent)
    direction_length = math.hypot(*path_direction)
    if tangent_length == 0 or direction_length == 0:
        return 0.0, curvature, 0.0
    tangent = (tangent[0] / tangent_length, tangent[1] / tangent_length)
    direction = (path_direction[0] / direction_length, path_direction[1] / direction_length)
    normal_alignment = 1.0 - abs(tangent[0] * direction[0] + tangent[1] * direction[1])
    flatness = max(0.0, 1.0 - curvature / math.pi)
    return flatness * 0.62 + normal_alignment * 0.38, curvature, normal_alignment


def _path_end_vectors(path: LineString) -> tuple[tuple[float, float], tuple[float, float]]:
    coordinates = list(path.coords)
    return ((coordinates[1][0] - coordinates[0][0], coordinates[1][1] - coordinates[0][1]), (coordinates[-1][0] - coordinates[-2][0], coordinates[-1][1] - coordinates[-2][1]))


def _web_candidates(piece, primary, obstacles, mode: str, width: float):
    """Return safe attachment candidates scored by structural vulnerability.

    A candidate is rejected unless its shallow web overlaps *both* intended
    walls, while avoiding every unrelated cutter wall. This prevents a web from
    spilling through artwork or ending as a free-floating overhang.
    """
    boundaries = [piece.exterior, *piece.interiors]
    sample_count = max(40, min(160, int(piece.boundary.length / max(width * 0.4, 0.15))))
    candidates = []
    seen = set()
    for boundary in boundaries:
        for index in range(sample_count):
            start = boundary.interpolate(index / sample_count, normalized=True)
            _, end = nearest_points(start, primary)
            distance = start.distance(end)
            if distance <= width * 0.25:
                continue
            key = (round(start.x, 3), round(start.y, 3), round(end.x, 3), round(end.y, 3))
            if key in seen:
                continue
            seen.add(key)
            path = _bridge_path(start, end, mode)
            target_boundary = min([primary.exterior, *primary.interiors], key=lambda boundary: boundary.distance(end))
            web = _contour_gusset(path, piece, primary, boundary, target_boundary, width)
            # Strict mode: a requested route is accepted only when both ends can
            # be inset flush. We never substitute a less faithful route.
            if web is None:
                continue
            # Flat end caps sit inside the two intended walls by a controlled
            # overlap, so both attachments are durable and visually flush.
            overlap_floor = max(width * width * 0.12, 0.01)
            if web.intersection(piece).area < overlap_floor or web.intersection(primary).area < overlap_floor:
                continue
            if any(web.intersection(obstacle).area > overlap_floor for obstacle in obstacles):
                continue
            # The core route may touch its two endpoints only; travelling through
            # a wall is overflow, not a support.
            core = path.buffer(width * 0.16, cap_style=2)
            if core.intersection(piece).area > overlap_floor or core.intersection(primary).area > overlap_floor:
                continue
            start_vector, end_vector = _path_end_vectors(path)
            source_strength, _, _ = _boundary_vector_score(boundary, start, start_vector)
            target_strength, _, _ = _boundary_vector_score(target_boundary, end, end_vector)
            # Low-curvature segments with near-normal force transfer are the
            # strongest landing-pad locations; distance is only a tie-breaker.
            structural_score = source_strength * 0.52 + target_strength * 0.48 - distance * 0.003
            candidates.append((structural_score, distance, start, end, path, web))
    return candidates


def _choose_island_webs(piece, primary, obstacles, mode: str, width: float, required: int):
    """Spread web anchors across the island's weakest unsupported regions."""
    candidates = _web_candidates(piece, primary, obstacles, mode, width)
    if len(candidates) < required:
        return candidates
    span = _island_span(piece)
    min_separation = max(width * 2.5, min(span * 0.24, 10.0))
    selected = []
    remaining = list(candidates)
    while remaining and len(selected) < required:
        def score(candidate):
            structural_strength, _, start, _, _, _ = candidate
            if not selected:
                return structural_strength
            spread = min(start.distance(existing[2]) for existing in selected)
            # Secondary gussets retain strong landings while resisting pivoting.
            return structural_strength + spread * 0.045
        candidate = max(remaining, key=score)
        if selected and min(candidate[2].distance(existing[2]) for existing in selected) < min_separation:
            separated = [item for item in remaining if min(item[2].distance(existing[2]) for existing in selected) >= min_separation]
            if separated:
                candidate = max(separated, key=score)
        selected.append(candidate)
        remaining.remove(candidate)
    return selected


def _manual_web_for_region(piece, primary, obstacles, mode: str, width: float, region: str):
    """Choose a safe snapped candidate nearest the requested island region."""
    directions = {"Top": (0.0, 1.0), "Right": (1.0, 0.0), "Bottom": (0.0, -1.0), "Left": (-1.0, 0.0)}
    direction = directions.get(region, directions["Top"])
    centroid = piece.representative_point()
    candidates = _web_candidates(piece, primary, obstacles, mode, width)
    if not candidates:
        raise ValueError("No safe snapped attachment is available for this manual support web.")
    def score(candidate):
        _, distance, start, _, _, _ = candidate
        vector = (start.x - centroid.x, start.y - centroid.y)
        magnitude = math.hypot(*vector) or 1.0
        alignment = (vector[0] * direction[0] + vector[1] * direction[1]) / magnitude
        return alignment * 1000.0 + distance
    return max(candidates, key=score)


def _low_profile_bridges(wall, mode: str, width: float, settings: ToolSettings) -> tuple[object, object, object, BridgeAnalysis]:
    """Build automatic and/or human-selected shallow cutter support webs."""
    pieces = _polygons(wall)
    count = len(pieces)
    if count < 2:
        empty = GeometryCollection()
        return empty, empty, empty, BridgeAnalysis(wall_components=count or 1)
    if mode == "None":
        empty = GeometryCollection()
        return empty, empty, empty, BridgeAnalysis(wall_components=count, connected=False, enabled=False)

    primary_index = max(range(count), key=lambda index: pieces[index].area)
    primary = pieces[primary_index]
    bridge_shapes = []
    automatic_shapes = []
    manual_shapes = []
    island_counts = []
    web_details = []
    unresolved_reasons = []
    bridge_width = max(float(width), 0.01)
    manual_specs = settings.manual_webs if settings.support_web_mode in {"Manual", "Auto + manual"} else []
    for island_number, (index, piece) in enumerate(((i, p) for i, p in enumerate(pieces) if i != primary_index), start=1):
        obstacles = [other for other_index, other in enumerate(pieces) if other_index not in {primary_index, index}]
        selected = []
        if settings.support_web_mode in {"Auto", "Auto + manual"}:
            selected.extend((candidate, False, "") for candidate in _choose_island_webs(
                piece, primary, obstacles, mode, bridge_width, _web_requirement(piece, primary, settings)
            ))
        for spec in manual_specs:
            if int(spec.get("island", 0)) != island_number:
                continue
            region = str(spec.get("region", "Top"))
            candidate = _manual_web_for_region(piece, primary, obstacles, mode, bridge_width, region)
            # A region can only produce one web; duplicate UI submissions do not
            # create stacked geometry.
            if any(candidate[2].distance(existing[0][2]) < bridge_width * 0.5 for existing in selected):
                continue
            selected.append((candidate, True, region))
        island_counts.append(len(selected))
        if len(selected) < settings.min_webs_per_island:
            unresolved_reasons.append(
                f"Island {island_number}: only {len(selected)} of {settings.min_webs_per_island} requested routes can form flush wall-to-wall attachments."
            )
        for rank, (candidate, manual, region) in enumerate(selected, start=1):
            _, _, source, target, _, web = candidate
            bridge_shapes.append(web)
            (manual_shapes if manual else automatic_shapes).append(web)
            if manual:
                reason = f"manual {region.lower()} attachment · curvature-checked"
            elif rank == 1:
                reason = "low-curvature, normal-aligned primary anchor"
            elif rank == 2:
                reason = "separated low-curvature secondary anchor"
            else:
                reason = "stable-contour reinforcement for unsupported span"
            web_details.append(SupportWeb(island_number, (source.x, source.y), (target.x, target.y), reason, manual=manual))

    bridges = unary_union(bridge_shapes).buffer(0) if bridge_shapes else GeometryCollection()
    automatic_bridges = unary_union(automatic_shapes).buffer(0) if automatic_shapes else GeometryCollection()
    manual_bridges = unary_union(manual_shapes).buffer(0) if manual_shapes else GeometryCollection()
    merged = unary_union([wall, bridges]).buffer(0)
    is_connected = len(_polygons(merged)) == 1
    analysis = BridgeAnalysis(
        wall_components=count,
        bridge_count=len(bridge_shapes),
        island_web_counts=tuple(island_counts),
        minimum_required_webs=settings.min_webs_per_island,
        webs=tuple(web_details),
        unresolved_reasons=tuple(unresolved_reasons),
        connected=is_connected,
        enabled=True,
    )
    if not is_connected and bridge_shapes:
        raise ValueError("Support webs could not connect all cutter walls. Adjust the trace, web width, or manual attachments.")
    return bridges, automatic_bridges, manual_bridges, analysis


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
    # Imported SVGs can occasionally contain overlapping paths. Normalize them
    # before topology analysis rather than trying to bridge invalid geometry.
    if not outline.is_valid:
        outline = outline.buffer(0)
    if settings.mirror:
        from shapely import affinity
        outline = affinity.scale(outline, xfact=-1, yfact=1, origin="center")
    g = settings.generator
    wall = _wall(outline, settings.blade_thickness_mm)
    cutter_generators = {"Cookie cutter", "Imprint cutter", "Cutter + stamp", "Sandwich sealer", "Multi-cutter"}
    if g in cutter_generators:
        bridges, automatic_bridges, manual_bridges, bridge_analysis = _low_profile_bridges(
            wall, settings.center_bars, settings.center_bar_width_mm, settings
        )
    else:
        bridges = automatic_bridges = manual_bridges = GeometryCollection()
        bridge_analysis = BridgeAnalysis()
    components: dict[str, trimesh.Trimesh] = {}
    structural_mesh = None
    export_error = None
    if g in cutter_generators:
        components["cutter"] = extrude(wall, settings.blade_height_mm)
        bridge_height = min(settings.bridge_height_mm, settings.blade_height_mm)
        if not automatic_bridges.is_empty:
            components["bridge"] = extrude(automatic_bridges, bridge_height, settings.blade_height_mm - bridge_height)
        if not manual_bridges.is_empty:
            components["manual bridge"] = extrude(manual_bridges, bridge_height, settings.blade_height_mm - bridge_height)
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
        if bridge_analysis.required and bridge_analysis.unresolved:
            details = "; ".join(bridge_analysis.unresolved_reasons)
            islands = ", ".join(str(index) for index in bridge_analysis.under_supported_islands)
            export_error = details or ("Disconnected cutter walls require flush support webs before export." if not bridge_analysis.connected else f"Floating cutter island(s) {islands} need at least {settings.min_webs_per_island} flush support webs before export.")
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
