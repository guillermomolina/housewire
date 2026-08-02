"""Shared helpers to build single-file nested site fixtures."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from housewire.project.io import (
    HOUSEWIRE_YAML,
    create_inline_location,
    create_site_document,
    load_yaml,
    save_yaml,
)
from housewire.project.tree import get_place_node


def init_site(
    root: Path,
    *,
    type_id: str = "House",
    label: str | None = None,
    notes: str | None = None,
    working_name: str | None = None,
) -> dict[str, Any]:
    """Create the default site YAML under ``root`` and return the loaded document."""
    create_site_document(
        root,
        type_id=type_id,
        label=label,
        notes=notes,
        working_name=working_name,
    )
    return load_yaml(root / HOUSEWIRE_YAML)


def add_place(
    doc: dict[str, Any],
    name: str,
    *,
    under: list[str] | tuple[str, ...] = (),
    type_id: str,
    subtype: str | None = None,
    label: str | None = None,
    notes: str | None = None,
    working_name: str | None = None,
) -> dict[str, Any]:
    """Insert a nested place under ``under`` path inside ``doc``."""
    parent = get_place_node(doc, under)
    return create_inline_location(
        parent,
        name,
        type_id=type_id,
        subtype=subtype,
        label=label,
        notes=notes,
        working_name=working_name,
    )


def save_site(root: Path, doc: dict[str, Any]) -> Path:
    path = root / HOUSEWIRE_YAML
    save_yaml(path, doc, backup=False)
    return path
