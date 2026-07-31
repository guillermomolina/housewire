from __future__ import annotations

from pathlib import Path
from typing import Any

from housewire.house import house_document_to_wireviz, is_house_document, load_catalog, path_location_parts, place_meta_from_mapping
from housewire.project.openings import validate_location_openings


def validate_house_document(
    doc: dict[str, Any],
    *,
    project_path: Path,
    yaml_path: Path,
) -> None:
    if not is_house_document(doc):
        raise ValueError("schema must be house/v1")
    meta = place_meta_from_mapping(doc)
    if meta is not None:
        validate_location_openings(meta)
    catalog = load_catalog()
    house_document_to_wireviz(
        doc,
        catalog=catalog,
        file_location_parts=path_location_parts(project_path, yaml_path),
    )
