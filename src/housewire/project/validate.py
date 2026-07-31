from __future__ import annotations

from pathlib import Path
from typing import Any

from housewire.house import house_document_to_wireviz, is_house_document, load_catalog, path_location_parts
from housewire.project.openings import validate_location_openings


def validate_house_document(
    doc: dict[str, Any],
    *,
    project_path: Path,
    yaml_path: Path,
) -> None:
    if not is_house_document(doc):
        raise ValueError("schema debe ser house/v1")
    loc = doc.get("location")
    if isinstance(loc, dict):
        validate_location_openings(loc)
    catalog = load_catalog()
    house_document_to_wireviz(
        doc,
        catalog=catalog,
        file_location_parts=path_location_parts(project_path, yaml_path),
    )
