from __future__ import annotations

from pathlib import Path
from typing import Any

from housewire.house import (
    HOUSE_SCHEMA,
    assert_supported_schema,
    load_catalog,
    path_location_parts,
    place_meta_from_mapping,
    validate_house_tree,
)
from housewire.site.openings import validate_location_openings


def validate_house_document(
    doc: dict[str, Any],
    *,
    site_path: Path,
    yaml_path: Path,
) -> None:
    try:
        assert_supported_schema(doc)
    except ValueError:
        raise
    if doc.get("schema") != HOUSE_SCHEMA:
        raise ValueError(f"schema must be {HOUSE_SCHEMA}")
    meta = place_meta_from_mapping(doc)
    if meta is not None:
        validate_location_openings(meta)
    catalog = load_catalog(site_path)
    validate_house_tree(
        doc,
        catalog=catalog,
        file_location_parts=path_location_parts(site_path, yaml_path),
    )
