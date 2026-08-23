import pytest

shapely = pytest.importorskip("shapely")
trimesh = pytest.importorskip("trimesh")

from shapely.geometry import MultiPolygon, Point, Polygon, box

from core.mesh import _boundary_vector_score, _bridge_path, _contour_gusset, _wall, export_bytes, generate
from core.models import PrinterProfile, ToolSettings
from core.validation import validate


def test_cutter_mesh_is_watertight():
    outline = Polygon([(0, 0), (40, 0), (40, 30), (0, 30)])
    model = generate(outline, ToolSettings())
    assert model.mesh.is_watertight
    assert set(model.components) >= {"cutter", "handle"}


def test_stamp_mesh_is_watertight():
    outline = Polygon([(0, 0), (30, 0), (30, 20), (0, 20)])
    model = generate(outline, ToolSettings(generator="Stamp"))
    assert model.mesh.is_watertight
    assert any(level == "success" for level, _ in validate(model.mesh, ToolSettings(generator="Stamp"), __import__("core.models", fromlist=["PrinterProfile"]).PrinterProfile()))


def test_low_profile_bridge_keeps_inner_cutter_loop_attached():
    outline = Polygon(
        [(0, 0), (50, 0), (50, 50), (0, 50)],
        holes=[[(15, 15), (35, 15), (35, 35), (15, 35)]],
    )
    settings = ToolSettings(blade_height_mm=15, bridge_height_mm=1.2)
    model = generate(outline, settings)

    assert "bridge" in model.components
    bridge = model.components["bridge"]
    assert bridge.is_watertight
    assert bridge.bounds[0, 2] == pytest.approx(13.8)
    assert bridge.bounds[1, 2] == pytest.approx(15.0)


def test_connected_single_wall_needs_no_support_web():
    model = generate(Polygon([(0, 0), (40, 0), (40, 30), (0, 30)]), ToolSettings())

    assert "bridge" not in model.components
    assert model.bridge_analysis.wall_components == 1
    assert model.bridge_analysis.bridge_count == 0
    assert model.bridge_analysis.connected


def test_auto_support_webs_connect_every_isolated_wall_with_minimum_count():
    outline = MultiPolygon([
        Polygon([(0, 0), (18, 0), (18, 18), (0, 18)]),
        Polygon([(32, 4), (48, 4), (48, 20), (32, 20)]),
        Polygon([(18, 34), (34, 34), (34, 50), (18, 50)]),
    ])
    model = generate(outline, ToolSettings(center_bars="Auto", bridge_height_mm=1.0))

    assert model.bridge_analysis.required
    assert model.bridge_analysis.connected
    assert model.bridge_analysis.bridge_count >= 2 * (model.bridge_analysis.wall_components - 1)
    assert all(count >= 2 for count in model.bridge_analysis.island_web_counts)
    assert "bridge" in model.components
    assert model.components["bridge"].bounds[0, 2] == pytest.approx(14.0)

def test_large_or_distant_island_receives_more_than_the_two_web_baseline():
    outline = MultiPolygon([
        Polygon([(0, 0), (30, 0), (30, 30), (0, 30)]),
        Polygon([(100, 0), (150, 0), (150, 50), (100, 50)]),
    ])
    settings = ToolSettings(max_unsupported_span_mm=20.0)
    model = generate(outline, settings)

    assert model.bridge_analysis.connected
    assert model.bridge_analysis.island_web_counts[0] > 2
    assert model.bridge_analysis.bridge_count == model.bridge_analysis.island_web_counts[0]


def test_two_webs_are_separated_across_a_floating_inner_loop():
    outline = Polygon(
        [(0, 0), (60, 0), (60, 60), (0, 60)],
        holes=[[(22, 22), (38, 22), (38, 38), (22, 38)]],
    )
    model = generate(outline, ToolSettings())

    assert model.bridge_analysis.island_web_counts == (2,)
    assert model.components["bridge"].bounds[1, 2] == pytest.approx(15.0)
    assert model.export_error is None


def test_disabled_support_web_reports_disconnected_cutter_walls():
    outline = Polygon(
        [(0, 0), (50, 0), (50, 50), (0, 50)],
        holes=[[(15, 15), (35, 15), (35, 35), (15, 35)]],
    )
    settings = ToolSettings(center_bars="None")
    model = generate(outline, settings)
    messages = validate(model.mesh, settings, PrinterProfile(), model.bridge_analysis)

    assert "bridge" not in model.components
    assert model.bridge_analysis.required
    assert not model.bridge_analysis.connected
    assert any(level == "warning" and "separate pieces" in message for level, message in messages)


def test_non_cutter_does_not_add_support_webs():
    outline = MultiPolygon([
        Polygon([(0, 0), (12, 0), (12, 12), (0, 12)]),
        Polygon([(22, 0), (34, 0), (34, 12), (22, 12)]),
    ])
    model = generate(outline, ToolSettings(generator="Stamp"))

    assert "bridge" not in model.components
    assert not model.bridge_analysis.required


def test_narrow_support_web_gets_printer_warning():
    outline = Polygon(
        [(0, 0), (50, 0), (50, 50), (0, 50)],
        holes=[[(15, 15), (35, 15), (35, 35), (15, 35)]],
    )
    settings = ToolSettings(center_bar_width_mm=0.2)
    model = generate(outline, settings)
    messages = validate(model.mesh, settings, PrinterProfile(nozzle_mm=0.4), model.bridge_analysis)

    assert any(level == "warning" and "Bridge width" in message for level, message in messages)


def test_standard_cutter_fuses_handle_and_support_web_into_one_manifold_body():
    outline = Polygon(
        [(0, 0), (50, 0), (50, 50), (0, 50)],
        holes=[[(15, 15), (35, 15), (35, 35), (15, 35)]],
    )
    model = generate(outline, ToolSettings())

    assert model.export_error is None
    assert model.structural_mesh is not None
    assert model.mesh.is_watertight
    assert len(model.mesh.split(only_watertight=False)) == 1
    assert export_bytes(model, "stl")


def test_standard_cutter_export_is_blocked_when_support_webs_are_disabled():
    outline = Polygon(
        [(0, 0), (50, 0), (50, 50), (0, 50)],
        holes=[[(15, 15), (35, 15), (35, 35), (15, 35)]],
    )
    model = generate(outline, ToolSettings(center_bars="None"))

    assert model.export_error
    with pytest.raises(ValueError, match="Disconnected cutter walls"):
        export_bytes(model, "stl")


def test_structural_webs_anchor_to_real_cutter_walls_for_concave_island():
    outline = Polygon(
        [(0, 0), (100, 0), (100, 100), (0, 100)],
        holes=[[(35, 30), (65, 30), (65, 42), (48, 42), (48, 70), (35, 70)]],
    )
    settings = ToolSettings(max_unsupported_span_mm=20.0)
    model = generate(outline, settings)
    wall = _wall(outline, settings.blade_thickness_mm)

    assert model.bridge_analysis.connected
    assert model.bridge_analysis.island_web_counts[0] >= 2
    for web in model.bridge_analysis.webs:
        assert wall.boundary.distance(__import__("shapely", fromlist=["Point"]).Point(web.source)) < 1e-6
        assert wall.boundary.distance(__import__("shapely", fromlist=["Point"]).Point(web.target)) < 1e-6


def test_support_web_routing_handles_multiple_constrained_inner_islands():
    mode = "Auto"
    outline = Polygon(
        [(0, 0), (120, 0), (120, 100), (0, 100)],
        holes=[
            [(15, 20), (35, 20), (35, 45), (15, 45)],
            [(50, 35), (72, 35), (72, 62), (50, 62)],
            [(85, 15), (108, 15), (108, 52), (85, 52)],
        ],
    )
    model = generate(outline, ToolSettings(center_bars=mode, max_unsupported_span_mm=20.0))

    assert model.bridge_analysis.connected
    assert all(count >= 2 for count in model.bridge_analysis.island_web_counts)
    assert model.export_error is None
    assert model.mesh.is_watertight
    assert len(model.mesh.split(only_watertight=False)) == 1


@pytest.mark.parametrize("mode", ["Horizontal", "Vertical"])
def test_forced_route_is_blocked_when_it_cannot_make_flush_attachments(mode):
    outline = Polygon(
        [(0, 0), (120, 0), (120, 100), (0, 100)],
        holes=[[(15, 20), (35, 20), (35, 45), (15, 45)]],
    )
    model = generate(outline, ToolSettings(center_bars=mode))

    assert model.bridge_analysis.unresolved
    assert model.bridge_analysis.unresolved_reasons
    assert model.export_error
    with pytest.raises(ValueError, match="flush wall-to-wall"):
        export_bytes(model, "stl")


def test_invalid_overlapping_vector_geometry_is_normalized_before_generation():
    invalid = MultiPolygon([
        Polygon([(0, 0), (60, 0), (60, 60), (0, 60)]),
        Polygon([(20, 20), (40, 20), (40, 40), (20, 40)]),
    ])
    model = generate(invalid, ToolSettings())

    assert model.mesh.is_watertight


def test_manual_support_web_pair_creates_a_safe_exportable_cutter():
    outline = Polygon(
        [(0, 0), (60, 0), (60, 60), (0, 60)],
        holes=[[(20, 20), (40, 20), (40, 40), (20, 40)]],
    )
    settings = ToolSettings(
        support_web_mode="Manual",
        manual_webs=[{"island": 1, "region": "Top"}, {"island": 1, "region": "Bottom"}],
    )
    model = generate(outline, settings)

    assert model.bridge_analysis.island_web_counts == (2,)
    assert model.bridge_analysis.automatic_web_count == 0
    assert model.bridge_analysis.manual_web_count == 2
    assert "manual bridge" in model.components
    assert model.export_error is None
    assert export_bytes(model, "stl")


def test_manual_mode_blocks_export_when_an_island_has_only_one_web():
    outline = Polygon(
        [(0, 0), (60, 0), (60, 60), (0, 60)],
        holes=[[(20, 20), (40, 20), (40, 40), (20, 40)]],
    )
    settings = ToolSettings(support_web_mode="Manual", manual_webs=[{"island": 1, "region": "Top"}])
    model = generate(outline, settings)

    assert model.bridge_analysis.under_supported_islands == (1,)
    assert model.export_error
    with pytest.raises(ValueError, match="flush wall-to-wall"):
        export_bytes(model, "stl")


def test_auto_plus_manual_retains_both_web_types():
    outline = Polygon(
        [(0, 0), (60, 0), (60, 60), (0, 60)],
        holes=[[(20, 20), (40, 20), (40, 40), (20, 40)]],
    )
    settings = ToolSettings(support_web_mode="Auto + manual", manual_webs=[{"island": 1, "region": "Left"}])
    model = generate(outline, settings)

    assert model.bridge_analysis.automatic_web_count >= 2
    assert model.bridge_analysis.manual_web_count == 1
    assert model.bridge_analysis.under_supported_islands == ()


def test_manual_mode_honors_configured_minimum_web_count():
    outline = Polygon(
        [(0, 0), (60, 0), (60, 60), (0, 60)],
        holes=[[(20, 20), (40, 20), (40, 40), (20, 40)]],
    )
    settings = ToolSettings(
        support_web_mode="Manual", min_webs_per_island=3,
        manual_webs=[{"island": 1, "region": "Top"}, {"island": 1, "region": "Bottom"}],
    )
    model = generate(outline, settings)

    assert model.bridge_analysis.under_supported_islands == (1,)
    assert model.export_error


def test_contour_gusset_has_inset_attachments_and_contour_following_landing_pads():
    island = box(0, 0, 10, 10)
    primary = box(20, 0, 30, 10)
    from shapely.geometry import LineString
    gusset = _contour_gusset(LineString([(10, 5), (20, 5)]), island, primary, island.exterior, primary.exterior, 1.5)

    assert gusset is not None
    island_pad = gusset.intersection(island)
    primary_pad = gusset.intersection(primary)
    assert island_pad.area > 0 and primary_pad.area > 0
    # Both pads extend along their vertical wall contours, rather than ending
    # as the narrow rectangular support strip.
    assert island_pad.bounds[3] - island_pad.bounds[1] > 1.5
    assert primary_pad.bounds[3] - primary_pad.bounds[1] > 1.5


def test_curvature_vector_score_prefers_a_flat_normal_aligned_wall_segment():
    wall = box(0, 0, 10, 10).exterior
    flat_score, flat_curve, flat_alignment = _boundary_vector_score(wall, Point(10, 5), (1, 0))
    corner_score, corner_curve, corner_alignment = _boundary_vector_score(wall, Point(10, 10), (1, 0))

    assert flat_curve < corner_curve
    assert flat_alignment >= corner_alignment
    assert flat_score > corner_score


def test_auto_gussets_report_curvature_aware_structural_reasons():
    outline = Polygon(
        [(0, 0), (100, 0), (100, 100), (0, 100)],
        holes=[[(30, 30), (70, 30), (70, 70), (30, 70)]],
    )
    model = generate(outline, ToolSettings())

    assert model.bridge_analysis.webs
    assert model.bridge_analysis.webs[0].reason == "low-curvature, normal-aligned primary anchor"
    assert model.bridge_analysis.webs[1].reason == "separated low-curvature secondary anchor"
