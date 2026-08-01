"""JSON physical graph for the interactive UI (locations + conduits, no Graphviz)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from housewire.house import is_place_type, place_meta_from_mapping
from housewire.house.conduit_ref import (
    conduit_endpoints,
    resolve_location_ref,
    split_conduit_endpoint,
)
from housewire.project.io import HOUSEWIRE_YAML, load_yaml
from housewire.project.openings import declared_opening_ids
from housewire.project.paths import is_excluded_path
from housewire.project.view_layout import (
    get_physical_page,
    get_physical_position,
    get_physical_view,
    set_physical_position,
)


def _opening_face(opening_id: str) -> str:
    text = str(opening_id).strip()
    if not text:
        return "?"
    return text[0].upper()


def location_dir(site_root: Path, location_id: str) -> Path:
    """Resolve an outline location directory under the site root."""
    root = site_root.resolve()
    if location_id in {".", "", "/"}:
        return root
    candidate = (site_root / location_id).resolve()
    candidate.relative_to(root)
    return candidate


def iter_place_yaml_under(
    location_dir_path: Path,
    *,
    session_docs: dict[Path, dict[str, Any]] | None = None,
) -> list[tuple[tuple[str, ...], Path]]:
    """Child outline place yaml paths under a location (excluding itself)."""
    rows: list[tuple[tuple[str, ...], Path]] = []
    root_yaml = (location_dir_path / HOUSEWIRE_YAML).resolve()
    base = location_dir_path.resolve()
    seen: set[Path] = set()
    for yaml_path in sorted(location_dir_path.rglob(HOUSEWIRE_YAML)):
        resolved = yaml_path.resolve()
        if resolved == root_yaml:
            continue
        if is_excluded_path(resolved):
            continue
        try:
            rel = resolved.parent.relative_to(base)
        except ValueError:
            continue
        parts = tuple(rel.parts)
        if not parts:
            continue
        rows.append((parts, resolved))
        seen.add(resolved)
    if session_docs:
        for path in session_docs:
            resolved = path.resolve()
            if resolved in seen or resolved == root_yaml:
                continue
            if resolved.name != HOUSEWIRE_YAML:
                continue
            try:
                rel = resolved.parent.relative_to(base)
            except ValueError:
                continue
            parts = tuple(rel.parts)
            if not parts:
                continue
            rows.append((parts, resolved))
            seen.add(resolved)
    return sorted(rows, key=lambda row: row[0])


def list_canvas_locations(site_root: Path) -> list[dict[str, Any]]:
    """Outline location tree (preorder), only nodes useful as canvas roots.

    Each row includes ``depth`` for UI indentation. A node is included if it
    has child outline places (selectable) or is an ancestor of such a node.
    """
    root = site_root.resolve()
    places: dict[str, dict[str, Any]] = {}

    for yaml_path in sorted(root.rglob(HOUSEWIRE_YAML)):
        if is_excluded_path(yaml_path):
            continue
        try:
            doc = load_yaml(yaml_path)
        except ValueError:
            continue
        meta = place_meta_from_mapping(doc)
        if meta is None:
            continue
        parent = yaml_path.parent
        try:
            rel = parent.relative_to(root)
        except ValueError:
            continue
        location_id = "." if str(rel) == "." else str(rel).replace("\\", "/")
        parts = () if location_id == "." else tuple(rel.parts)
        places[location_id] = {
            "id": location_id,
            "label": str(meta.get("label") or (root.name if location_id == "." else parent.name)),
            "type": str(meta.get("type") or "Location"),
            "path": location_id,
            "parts": parts,
        }

    def _is_descendant(ancestor: tuple[str, ...], other: tuple[str, ...]) -> bool:
        return len(other) > len(ancestor) and other[: len(ancestor)] == ancestor

    selectable: set[str] = set()
    for loc_id, info in places.items():
        parts = info["parts"]
        if any(
            _is_descendant(parts, other["parts"]) for other in places.values()
        ):
            selectable.add(loc_id)

    keep: set[str] = set(selectable)
    for loc_id in selectable:
        parts = places[loc_id]["parts"]
        for depth in range(len(parts)):
            anc_parts = parts[:depth]
            anc_id = "." if not anc_parts else "/".join(anc_parts)
            if anc_id in places:
                keep.add(anc_id)

    children: dict[str | None, list[str]] = {}
    for loc_id, info in places.items():
        if loc_id not in keep:
            continue
        parts = info["parts"]
        if not parts:
            parent_key: str | None = None
        else:
            parent_key = "." if len(parts) == 1 else "/".join(parts[:-1])
            if parent_key not in keep:
                parent_key = None
        children.setdefault(parent_key, []).append(loc_id)

    for kids in children.values():
        kids.sort(key=lambda i: places[i]["label"].lower())

    rows: list[dict[str, Any]] = []

    def _walk(parent_key: str | None, depth: int) -> None:
        for loc_id in children.get(parent_key, []):
            info = places[loc_id]
            rows.append(
                {
                    "id": info["id"],
                    "label": info["label"],
                    "type": info["type"],
                    "path": info["path"],
                    "depth": depth,
                    "selectable": loc_id in selectable,
                }
            )
            _walk(loc_id, depth + 1)

    _walk(None, 0)
    # Orphans that lost parent link but are still kept
    emitted = {r["id"] for r in rows}
    for loc_id in sorted(keep - emitted, key=lambda i: places[i]["parts"]):
        info = places[loc_id]
        rows.append(
            {
                "id": info["id"],
                "label": info["label"],
                "type": info["type"],
                "path": info["path"],
                "depth": len(info["parts"]),
                "selectable": loc_id in selectable,
            }
        )
    return rows


def build_physical_graph(
    site_root: Path,
    location_id: str,
    *,
    depth: int = 1,
    session_docs: dict[Path, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build UI graph for one location.

    ``depth`` is how many outline levels under the canvas root are visible
    (1 = direct children only; 2 = children nested inside parents; …).
    """
    if depth < 1:
        raise ValueError("depth must be >= 1")
    ldir = location_dir(site_root, location_id)
    loc_yaml = (ldir / HOUSEWIRE_YAML).resolve()

    def _doc_for(path: Path) -> dict[str, Any]:
        resolved = path.resolve()
        if session_docs and resolved in session_docs:
            return session_docs[resolved]
        return load_yaml(resolved)

    if not loc_yaml.is_file() and not (
        session_docs and loc_yaml in {p.resolve() for p in session_docs}
    ):
        raise FileNotFoundError(
            f"No {HOUSEWIRE_YAML} for location {location_id!r}"
        )

    loc_doc = _doc_for(loc_yaml)
    loc_meta = place_meta_from_mapping(loc_doc) or {}
    page = get_physical_page(loc_doc)

    all_under = {
        parts
        for parts, _path in iter_place_yaml_under(ldir, session_docs=session_docs)
    }
    max_depth = max((len(parts) for parts in all_under), default=0)
    depth = min(depth, max(max_depth, 1))

    place_paths = [
        (parts, path)
        for parts, path in iter_place_yaml_under(ldir, session_docs=session_docs)
        if 1 <= len(parts) <= depth
    ]
    places: list[tuple[tuple[str, ...], Path, dict[str, Any]]] = []
    for parts, path in place_paths:
        try:
            doc = _doc_for(path)
        except ValueError:
            continue
        meta = place_meta_from_mapping(doc)
        if meta is None:
            continue
        places.append((parts, path, doc))

    known_full = {parts for parts, _, _ in places}
    # Resolve conduits against the full outline under this canvas so refs to
    # deeper places still parse; then map endpoints to a visible ancestor.
    known_resolve = all_under | known_full
    nodes: list[dict[str, Any]] = []

    for parts, _path, doc in places:
        meta = place_meta_from_mapping(doc) or {}
        type_id = str(meta.get("type") or "Location")
        if not is_place_type(type_id):
            type_id = "Location"
        try:
            openings = sorted(declared_opening_ids(meta.get("openings")) or [])
        except ValueError:
            openings = []
        pos = get_physical_position(doc)
        phys = get_physical_view(doc) or {}
        rotation = phys.get("rotation", 0)
        if not isinstance(rotation, int):
            try:
                rotation = int(rotation)
            except (TypeError, ValueError):
                rotation = 0
        parent_id = "/".join(parts[:-1]) if len(parts) > 1 else None
        has_deeper = any(
            len(other) > depth and other[: len(parts)] == parts
            for other in all_under
        )
        nodes.append(
            {
                "id": "/".join(parts),
                "parts": list(parts),
                "parent": parent_id,
                "type": type_id,
                "label": str(meta.get("label") or parts[-1]),
                "openings": [
                    {"id": oid, "face": _opening_face(oid)} for oid in openings
                ],
                "x": pos[0] if pos else None,
                "y": pos[1] if pos else None,
                "rotation": rotation,
                "expandable": has_deeper,
            }
        )

    def _visible_endpoint(parts: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if parts is None or parts not in known_resolve:
            return None
        if parts in known_full:
            return parts
        # Collapse to nearest visible ancestor within depth window.
        for cut in range(min(len(parts), depth), 0, -1):
            anc = parts[:cut]
            if anc in known_full:
                return anc
        return None

    edges: list[dict[str, Any]] = []
    edge_sources: list[tuple[tuple[str, ...], dict[str, Any]]] = [
        (tuple(), loc_doc),
        *[(parts, doc) for parts, _, doc in places],
    ]
    seen_edges: set[tuple[str, str, str, str, str]] = set()
    for current_parts, doc in edge_sources:
        conduits = doc.get("conduits") or {}
        if not isinstance(conduits, dict):
            continue
        for conduit_name, conduit in conduits.items():
            if not isinstance(conduit, dict):
                continue
            try:
                from_ref, to_ref = conduit_endpoints(conduit)
                from_loc, from_op = split_conduit_endpoint(from_ref)
                to_loc, to_op = split_conduit_endpoint(to_ref)
            except ValueError:
                continue
            from_parts = resolve_location_ref(
                from_loc, current_parts=list(current_parts), known=known_resolve
            )
            to_parts = resolve_location_ref(
                to_loc, current_parts=list(current_parts), known=known_resolve
            )
            from_vis = _visible_endpoint(from_parts)
            to_vis = _visible_endpoint(to_parts)
            if from_vis is None or to_vis is None or from_vis == to_vis:
                continue
            from_id = "/".join(from_vis)
            to_id = "/".join(to_vis)
            key = (str(conduit_name), from_id, to_id, from_op or "", to_op or "")
            if key in seen_edges:
                continue
            seen_edges.add(key)
            contains = [str(c) for c in (conduit.get("contains") or [])]
            edges.append(
                {
                    "id": str(conduit_name),
                    "from": from_id,
                    "to": to_id,
                    "from_opening": from_op,
                    "to_opening": to_op,
                    "contains": contains,
                    "subtype": conduit.get("subtype"),
                }
            )

    return {
        "location": {
            "id": location_id,
            "label": str(loc_meta.get("label") or ldir.name),
            "type": str(loc_meta.get("type") or "Location"),
        },
        "page": page,
        "depth": depth,
        "max_depth": max_depth,
        "nodes": nodes,
        "edges": edges,
    }


def apply_auto_layout(
    site_root: Path,
    location_id: str,
    *,
    session_docs: dict[Path, dict[str, Any]],
    depth: int = 1,
    force: bool = False,
    gap_x: float = 180.0,
    gap_y: float = 140.0,
    origin_x: float = 80.0,
    origin_y: float = 80.0,
    cols: int = 4,
) -> list[str]:
    """Assign grid positions to nodes missing x/y (or all if force).

    Sibling groups (same parent) are laid out independently so nested depth
    zoom keeps child coords relative to their container.
    """
    graph = build_physical_graph(
        site_root, location_id, depth=depth, session_docs=session_docs
    )
    ldir = location_dir(site_root, location_id)
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for node in graph["nodes"]:
        parent = node.get("parent")
        by_parent.setdefault(parent, []).append(node)

    updated: list[str] = []
    for siblings in by_parent.values():
        index = 0
        for node in siblings:
            if not force and node.get("x") is not None and node.get("y") is not None:
                continue
            col = index % cols
            row = index // cols
            # Nested siblings sit closer; top-level keeps the roomier grid.
            nested = node.get("parent") is not None
            ox = 16.0 if nested else origin_x
            oy = 36.0 if nested else origin_y
            gx = 140.0 if nested else gap_x
            gy = 100.0 if nested else gap_y
            x = ox + col * gx
            y = oy + row * gy
            parts = tuple(node["parts"])
            yaml_path = (ldir.joinpath(*parts) / HOUSEWIRE_YAML).resolve()
            doc = session_docs.get(yaml_path)
            if doc is None:
                if not yaml_path.is_file():
                    continue
                doc = load_yaml(yaml_path)
                session_docs[yaml_path] = doc
            set_physical_position(doc, x, y)
            updated.append(node["id"])
            index += 1
    return updated


def apply_positions(
    site_root: Path,
    location_id: str,
    positions: dict[str, dict[str, Any]],
    *,
    session_docs: dict[Path, dict[str, Any]],
) -> list[str]:
    """Write positions ``{node_id: {x,y}}``. Return updated ids."""
    ldir = location_dir(site_root, location_id)
    updated: list[str] = []
    for node_id, pos in positions.items():
        parts = tuple(p for p in str(node_id).split("/") if p)
        if not parts:
            continue
        yaml_path = (ldir.joinpath(*parts) / HOUSEWIRE_YAML).resolve()
        doc = session_docs.get(yaml_path)
        if doc is None:
            if not yaml_path.is_file():
                raise FileNotFoundError(f"Unknown node: {node_id}")
            doc = load_yaml(yaml_path)
            session_docs[yaml_path] = doc
        set_physical_position(doc, float(pos["x"]), float(pos["y"]))
        updated.append(str(node_id))
    return updated
