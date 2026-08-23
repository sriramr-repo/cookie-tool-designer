from __future__ import annotations

import json
import shutil
from pathlib import Path

from .models import DesignProject, projects_root


def save_project(project: DesignProject, source: bytes | None = None) -> Path:
    root = projects_root() / project.name.strip().replace("/", "-")
    root.mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text(json.dumps(project.to_dict(), indent=2))
    if source and project.source_filename:
        (root / ("source" + Path(project.source_filename).suffix)).write_bytes(source)
    return root


def list_projects() -> list[Path]:
    root = projects_root()
    return sorted(root.glob("*/settings.json"), key=lambda p: p.stat().st_mtime, reverse=True) if root.exists() else []


def load_project(settings_file: Path) -> DesignProject:
    return DesignProject.from_dict(json.loads(settings_file.read_text()))


def read_project_source(settings_file: Path) -> bytes | None:
    """Read the locally stored source artwork for a saved design."""
    candidates = sorted(settings_file.parent.glob("source.*"))
    return candidates[0].read_bytes() if candidates else None
