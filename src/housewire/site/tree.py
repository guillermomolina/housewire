"""Single-document place tree helpers (nested ``elements:`` places)."""
from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any, Iterator

from housewire.house import is_place_type
from housewire.site.io import HOUSEWIRE_YAML
from housewire.site.paths import find_site_yaml


def site_yaml_path(site_root: Path, *, name: str | None = None) -> Path:
    """Path of the site document YAML (any ``.yaml`` / ``.yml`` name).

    When the file already exists it is discovered via :func:`find_site_yaml`.
    Otherwise returns ``site_root / name`` or the default site filename.
    """
    found = find_site_yaml(site_root, preferred=name)
    if found is not None:
        return found
    if name:
        return (site_root / name).resolve()
    return (site_root / HOUSEWIRE_YAML).resolve()


def get_place_node(doc: dict[str, Any], parts: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """Return the place mapping at ``parts`` inside ``doc`` (doc root if empty)."""

    def _child(elements: dict[str, Any], part: str) -> Any:
        if part in elements:
            return elements[part]
        want = unicodedata.normalize("NFC", part)
        if want in elements:
            return elements[want]
        for key, value in elements.items():
            if unicodedata.normalize("NFC", str(key)) == want:
                return value
        return None

    node: dict[str, Any] = doc
    walked: list[str] = []
    for part in parts:
        elements = node.get("elements") or {}
        if not isinstance(elements, dict):
            path = "/".join([*walked, part])
            raise ValueError(f"Place does not exist: {path}")
        child = _child(elements, part)
        if child is None:
            path = "/".join([*walked, part])
            raise ValueError(f"Place does not exist: {path}")
        if not isinstance(child, dict) or not is_place_type(child.get("type")):
            raise ValueError(f"Not a location (place type): {part}")
        node = child
        walked.append(part)
    return node


def iter_place_children(node: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Direct child places under ``node['elements']``, sorted by id."""
    elements = node.get("elements") or {}
    if not isinstance(elements, dict):
        return []
    rows: list[tuple[str, dict[str, Any]]] = []
    for name in sorted(elements, key=lambda n: str(n).lower()):
        defn = elements[name]
        if isinstance(defn, dict) and is_place_type(defn.get("type")):
            rows.append((str(name), defn))
    return rows


def iter_places(
    doc: dict[str, Any],
    *,
    under: list[str] | tuple[str, ...] = (),
) -> Iterator[tuple[tuple[str, ...], dict[str, Any]]]:
    """Yield ``(relative_parts, place_node)`` for every nested place under ``under``.

    Does not yield the ``under`` node itself. ``relative_parts`` is relative to
    ``under`` (so a direct child has length 1).
    """
    root = get_place_node(doc, under)

    def _walk(
        node: dict[str, Any], prefix: tuple[str, ...]
    ) -> Iterator[tuple[tuple[str, ...], dict[str, Any]]]:
        for name, child in iter_place_children(node):
            parts = (*prefix, name)
            yield parts, child
            yield from _walk(child, parts)

    yield from _walk(root, ())


def logical_parts_from_id(location_id: str) -> tuple[str, ...]:
    """Parse a canvas/location id (``.`` or ``a/b``) into place parts."""
    text = str(location_id).strip().replace("\\", "/")
    if text in {".", "", "/"}:
        return ()
    return tuple(
        unicodedata.normalize("NFC", p) for p in text.split("/") if p
    )
