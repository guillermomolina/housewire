from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from housewire.house import (
    HOUSE_SCHEMA,
    PLACE_TYPES,
    assert_supported_schema,
    is_house_document,
    is_place_type,
    load_catalog,
    _catalog_defaults_for_subtype,
)

HOUSEWIRE_YAML = "housewire.yaml"

EMPTY_HOUSE_TEMPLATE: dict[str, Any] = {
    "schema": HOUSE_SCHEMA,
    "elements": {},
    "cables": {},
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
    hint = f": {path}" if path else ""
    try:
        assert_supported_schema(data)
    except ValueError as exc:
        raise ValueError(f"{exc}{hint}") from exc
    if not is_house_document(data):
        raise ValueError(
            f"Only YAML with schema {HOUSE_SCHEMA} can be edited{hint}."
        )


def create_empty_house_file(path: Path) -> dict[str, Any]:
    if path.exists():
        raise FileExistsError(f"Already exists: {path}")
    doc = {
        "schema": HOUSE_SCHEMA,
        "elements": {},
        "cables": {},
    }
    save_yaml(path, doc, backup=False)
    return doc


def apply_place_catalog_defaults(
    entry: dict[str, Any],
    *,
    type_id: str | None = None,
    subtype: str | None = None,
) -> None:
    """Copy catalog ``defaults`` onto a place map (skip keys already set).

    Merges type-level and subtype-level defaults (e.g. JunctionBox
    ``opening_grid``, IP40 ``install``). Does not overwrite explicit fields.
    """
    tid = str(type_id or entry.get("type") or "").strip()
    if not tid:
        return
    try:
        catalog = load_catalog()
    except FileNotFoundError:
        return
    type_def = catalog.get(tid)
    if not isinstance(type_def, dict):
        return
    eff_subtype = subtype if subtype is not None else entry.get("subtype")
    if eff_subtype is None or str(eff_subtype).strip() == "":
        base = type_def.get("defaults")
        if isinstance(base, dict) and base.get("subtype") is not None:
            eff_subtype = str(base["subtype"]).strip() or None
            if eff_subtype and "subtype" not in entry:
                entry["subtype"] = eff_subtype
    defaults = _catalog_defaults_for_subtype(
        type_def,
        str(eff_subtype).strip() if eff_subtype is not None else None,
    )
    for key, value in defaults.items():
        if key == "subtype":
            continue
        if key in entry:
            continue
        entry[key] = copy.deepcopy(value)


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
    ``name:`` (canvas); ``label`` is human text. Catalog type/subtype defaults
    (e.g. ``opening_grid``, ``install``) are applied when not overridden.
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
    }
    if working_name:
        entry["name"] = working_name
    if label:
        entry["label"] = label
    if subtype:
        entry["subtype"] = subtype
    if notes:
        entry["notes"] = notes
    apply_place_catalog_defaults(entry, type_id=type_id, subtype=subtype)
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
    """Build a place-root house/v2 document (no I/O)."""
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
    return doc


def create_site_document(
    site_root: Path,
    *,
    type_id: str = "House",
    subtype: str | None = None,
    notes: str | None = None,
    label: str | None = None,
    working_name: str | None = None,
    yaml_name: str | None = None,
) -> Path:
    """Create a site YAML (default ``housewire.yaml``) at ``site_root``."""
    site_root.mkdir(parents=True, exist_ok=True)
    name = Path(yaml_name or HOUSEWIRE_YAML).name
    if not name.lower().endswith((".yaml", ".yml")):
        name = f"{name}.yaml"
    yaml_path = site_root / name
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
