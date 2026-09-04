from core.exporters import export_filename
from core.models import DesignProject, PrinterProfile, ToolSettings, TraceSettings


def test_project_round_trip():
    project = DesignProject(
        name="Dog cutter",
        trace=TraceSettings(target_width_mm=60),
        tool=ToolSettings(generator="Stamp", min_webs_per_island=3, max_unsupported_span_mm=16.0),
        printer=PrinterProfile(name="Anycubic Kobra S1"),
    )
    restored = DesignProject.from_dict(project.to_dict())
    assert restored.name == "Dog cutter"
    assert restored.trace.target_width_mm == 60
    assert restored.tool.generator == "Stamp"
    assert restored.tool.min_webs_per_island == 3
    assert restored.tool.max_unsupported_span_mm == 16.0
    assert restored.printer.name == "Anycubic Kobra S1"


def test_default_printer_profile_is_anycubic_kobra_s1():
    profile = PrinterProfile()

    assert profile.name == "Anycubic Kobra S1"
    assert profile.nozzle_mm == 0.4
    assert (profile.build_x_mm, profile.build_y_mm, profile.build_z_mm) == (250.0, 250.0, 250.0)


def test_export_filename_is_safe_and_deterministic():
    assert export_filename("my design!.png", "stl") == "my_design_.stl"
    assert export_filename(".svg", "3mf") == "_svg.3mf"
