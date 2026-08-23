import pytest

shapely = pytest.importorskip("shapely")
trimesh = pytest.importorskip("trimesh")

from shapely.geometry import MultiPolygon, Polygon

from core.mesh import export_bytes, generate
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
