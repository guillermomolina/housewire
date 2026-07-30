from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from housewire.house import HOUSE_SCHEMA, PLACE_TYPES, is_house_document, is_place_type

INDEX_YAML = "index.yaml"

EMPTY_HOUSE_TEMPLATE: dict[str, Any] = {
    "schema": HOUSE_SCHEMA,
    "elements": {},
    "cables": {},
    "connections": [],
}


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"El YAML no contiene un objeto valido: {path}")
    return data


def save_yaml(path: Path, data: dict[str, Any], *, backup: bool = True) -> None:
    if backup and path.exists():
        backup_path = path.with_suffix(path.suffix + ".bak")
        backup_path.write_bytes(path.read_bytes())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


def require_house_document(data: dict[str, Any], path: Path | None = None) -> None:
    if not is_house_document(data):
        hint = f": {path}" if path else ""
        raise ValueError(
            f"Solo se puede editar YAML con schema house/v1{hint}. "
            "Usa otro archivo o migra el documento."
        )


def create_empty_house_file(path: Path) -> dict[str, Any]:
    if path.exists():
        raise FileExistsError(f"Ya existe: {path}")
    doc = {
        "schema": HOUSE_SCHEMA,
        "elements": {},
        "cables": {},
        "connections": [],
    }
    save_yaml(path, doc, backup=False)
    return doc


def create_location_index(
    dir_path: Path,
    *,
    type_id: str,
    subtype: str | None = None,
    notes: str | None = None,
) -> Path:
    """Create directory + index.yaml with ``location:`` place metadata."""
    if not is_place_type(type_id):
        raise ValueError(
            "type debe ser uno de: "
            + ", ".join(sorted(PLACE_TYPES - {"Location"}))
            + " (o Location)"
        )
    dir_path.mkdir(parents=True, exist_ok=True)
    index_path = dir_path / INDEX_YAML
    if index_path.exists():
        raise FileExistsError(f"Ya existe: {index_path}")
    location_block: dict[str, Any] = {"type": str(type_id)}
    if subtype:
        location_block["subtype"] = subtype
    if notes:
        location_block["notes"] = notes
    doc: dict[str, Any] = {
        "schema": HOUSE_SCHEMA,
        "location": location_block,
        "elements": {},
        "cables": {},
        "connections": [],
    }
    save_yaml(index_path, doc, backup=False)
    return index_path
