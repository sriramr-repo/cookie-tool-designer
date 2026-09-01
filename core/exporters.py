"""Export helpers shared by the local application workflows."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Protocol

from .image_processor import image_from_bytes, trace_image
from .mesh import export_bytes, generate
from .models import ToolSettings, TraceSettings


class UploadedArtwork(Protocol):
    """The minimal uploaded-file interface needed for batch exports."""

    name: str

    def getvalue(self) -> bytes: ...


def export_filename(filename: str, fmt: str) -> str:
    """Return a safe, deterministic export filename for an uploaded artwork."""
    base = "".join(char if char.isalnum() or char in "-_" else "_" for char in Path(filename).stem) or "design"
    return f"{base}.{fmt}"


def build_batch_zip(
    files: list[UploadedArtwork], trace: TraceSettings, tool: ToolSettings, fmt: str
) -> tuple[bytes, int, list[str]]:
    """Generate one export for each uploaded artwork using shared settings."""
    archive = io.BytesIO()
    errors: list[str] = []
    written = 0
    names_seen: set[str] = set()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for item in files:
            try:
                image = image_from_bytes(item.getvalue(), item.name)
                outline = trace_image(image, trace)
                model = generate(outline, tool)
                base = export_filename(item.name, fmt).removesuffix(f".{fmt}")
                filename = f"{base}.{fmt}"
                suffix = 2
                while filename in names_seen:
                    filename = f"{base}_{suffix}.{fmt}"
                    suffix += 1
                names_seen.add(filename)
                bundle.writestr(filename, export_bytes(model, fmt))
                written += 1
            except Exception as exc:
                errors.append(f"{item.name}: {exc}")
        if errors:
            bundle.writestr("batch-errors.txt", "\n".join(errors))
    return archive.getvalue(), written, errors
