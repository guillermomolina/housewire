from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from housewire.house import HOUSE_SCHEMA, PLACE_TYPES, is_house_document, is_place_type

HOUSEWIRE_YAML = "housewire.yaml"

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
        raise ValueError(f"YAML does not contain a valid object: {path}")
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
            f"Only YAML with schema house/v1 can be edited{hint}. "
            "Use another file or migrate the document."
        )


def create_empty_house_file(path: Path) -> dict[str, Any]:
    if path.exists():
        raise FileExistsError(f"Already exists: {path}")
    doc = {
        "schema": HOUSE_SCHEMA,
        "elements": {},
        "cables": {},
        "connections": [],
    }
    save_yaml(path, doc, backup=False)
    return doc


def create_inline_location(
    parent_place: dict[str, Any],
    name: str,
    *,
    type_id: str,
    subtype: str | None = None,
    notes: str | None = None,
    label: str | None = None,
    working_name: str | None = None,
) -> dict[str, Any]:
    """Create an inline place under ``parent_place['elements'][name]``.

    ``name`` is the technical id (map key). Optional ``working_name`` is YAML
    ``name:`` (canvas); ``label`` is human text.
    """
    if not is_place_type(type_id):
        raise ValueError(
            "type must be one of: "
            + ", ".join(sorted(PLACE_TYPES - {"Location"}))
            + " (or Location)"
        )
    parent_place.setdefault("elements", {})
    elements = parent_place["elements"]
    if not isinstance(elements, dict):
        raise ValueError("elements must be a map")
    if name in elements:
        raise ValueError(f"Element/location already exists: {name}")
    entry: dict[str, Any] = {
        "type": str(type_id),
        "elements": {},
        "cables": {},
        "connections": [],
    }
    if working_name:
        entry["name"] = working_name
    if label:
        entry["label"] = label
    if subtype:
        entry["subtype"] = subtype
    if notes:
        entry["notes"] = notes
    elements[name] = entry
    return entry


def build_location_document(
    *,
    type_id: str,
    subtype: str | None = None,
    notes: str | None = None,
    label: str | None = None,
    working_name: str | None = None,
) -> dict[str, Any]:
    """Build a place-root house/v1 document (no I/O)."""
    if not is_place_type(type_id):
        raise ValueError(
            "type must be one of: "
            + ", ".join(sorted(PLACE_TYPES - {"Location"}))
            + " (or Location)"
        )
    doc: dict[str, Any] = {
        "schema": HOUSE_SCHEMA,
        "type": str(type_id),
    }
    if working_name:
        doc["name"] = working_name
    if label:
        doc["label"] = label
    if subtype:
        doc["subtype"] = subtype
    if notes:
        doc["notes"] = notes
    doc["elements"] = {}
    doc["cables"] = {}
    doc["connections"] = []
    return doc


def create_site_document(
    site_root: Path,
    *,
    type_id: str = "House",
    subtype: str | None = None,
    notes: str | None = None,
    label: str | None = None,
    working_name: str | None = None,
) -> Path:
    """Create the single site ``housewire.yaml`` at ``site_root`` (no nested dirs)."""
    site_root.mkdir(parents=True, exist_ok=True)
    yaml_path = site_root / HOUSEWIRE_YAML
    if yaml_path.exists():
        raise FileExistsError(f"Already exists: {yaml_path}")
    doc = build_location_document(
        type_id=type_id,
        subtype=subtype,
        notes=notes,
        label=label,
        working_name=working_name,
    )
    save_yaml(yaml_path, doc, backup=False)
    return yaml_path
