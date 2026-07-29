from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from housewire.house import HOUSE_SCHEMA, is_house_document

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
