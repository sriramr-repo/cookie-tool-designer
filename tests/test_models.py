from core.models import DesignProject, PrinterProfile, ToolSettings, TraceSettings


def test_project_round_trip():
    project = DesignProject(
        name="Dog cutter",
        trace=TraceSettings(target_width_mm=60),
        tool=ToolSettings(generator="Stamp"),
        printer=PrinterProfile(name="Anycubic Kobra S1"),
    )
    restored = DesignProject.from_dict(project.to_dict())
    assert restored.name == "Dog cutter"
    assert restored.trace.target_width_mm == 60
    assert restored.tool.generator == "Stamp"
    assert restored.printer.name == "Anycubic Kobra S1"


def test_default_printer_profile_is_anycubic_kobra_s1():
    profile = PrinterProfile()

    assert profile.name == "Anycubic Kobra S1"
    assert profile.nozzle_mm == 0.4
    assert (profile.build_x_mm, profile.build_y_mm, profile.build_z_mm) == (250.0, 250.0, 250.0)
