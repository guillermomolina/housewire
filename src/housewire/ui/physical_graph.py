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
    get_floor_physical_page,
    get_physical_position,
    get_physical_view,
    set_physical_position,
)


def _opening_face(opening_id: str) -> str:
    text = str(opening_id).strip()
    if not text:
        return "?"
    return text[0].upper()


def list_floors(site_root: Path) -> list[dict[str, Any]]:
    """Return outline places with ``type: Floor`` under the site."""
    rows: list[dict[str, Any]] = []
    root = site_root.resolve()
    seen: set[str] = set()
    for yaml_path in sorted(root.rglob(HOUSEWIRE_YAML)):
        if is_excluded_path(yaml_path):
            continue
        try:
            doc = load_yaml(yaml_path)
        except ValueError:
            continue
        meta = place_meta_from_mapping(doc)
        if meta is None or str(meta.get("type")) != "Floor":
            continue
        rel = yaml_path.parent.relative_to(root)
        floor_id = "." if str(rel) == "." else str(rel).replace("\\", "/")
        if floor_id in seen:
            continue
        seen.add(floor_id)
        rows.append(
            {
                "id": floor_id,
                "label": str(meta.get("label") or yaml_path.parent.name),
                "path": floor_id,
            }
        )
    return rows


def floor_dir(site_root: Path, floor_id: str) -> Path:
    """Resolve floor directory under the site root."""
    root = site_root.resolve()
    if floor_id in {".", "", "/"}:
        return root
    candidate = (site_root / floor_id).resolve()
    candidate.relative_to(root)
    return candidate


def iter_place_yaml_under(floor_dir: Path) -> list[tuple[tuple[str, ...], Path]]:
    """Child outline place yaml paths under the floor (excluding the floor itself)."""
    rows: list[tuple[tuple[str, ...], Path]] = []
    floor_yaml = (floor_dir / HOUSEWIRE_YAML).resolve()
    base = floor_dir.resolve()
    for yaml_path in sorted(floor_dir.rglob(HOUSEWIRE_YAML)):
        resolved = yaml_path.resolve()
        if resolved == floor_yaml:
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
    return rows


def build_physical_graph(
    site_root: Path,
    floor_id: str,
    *,
    session_docs: dict[Path, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build UI graph for one floor: nodes = child places, edges = conduits."""
    fdir = floor_dir(site_root, floor_id)
    floor_yaml = (fdir / HOUSEWIRE_YAML).resolve()

    def _doc_for(path: Path) -> dict[str, Any]:
        resolved = path.resolve()
        if session_docs and resolved in session_docs:
            return session_docs[resolved]
        return load_yaml(resolved)

    if not floor_yaml.is_file() and not (
        session_docs and floor_yaml in {p.resolve() for p in session_docs}
    ):
        raise FileNotFoundError(f"No {HOUSEWIRE_YAML} for floor {floor_id!r}")

    floor_doc = _doc_for(floor_yaml)
    floor_meta = place_meta_from_mapping(floor_doc) or {}
    page = get_floor_physical_page(floor_doc)

    place_paths = iter_place_yaml_under(fdir)
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
        nodes.append(
            {
                "id": "/".join(parts),
                "parts": list(parts),
                "type": type_id,
                "label": str(meta.get("label") or parts[-1]),
                "openings": [
                    {"id": oid, "face": _opening_face(oid)} for oid in openings
                ],
                "x": pos[0] if pos else None,
                "y": pos[1] if pos else None,
                "rotation": rotation,
            }
        )

    edges: list[dict[str, Any]] = []
    edge_sources: list[tuple[tuple[str, ...], dict[str, Any]]] = [
        (tuple(), floor_doc),
        *[(parts, doc) for parts, _, doc in places],
    ]
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
                from_loc, current_parts=list(current_parts), known=known_full
            )
            to_parts = resolve_location_ref(
                to_loc, current_parts=list(current_parts), known=known_full
            )
            if from_parts not in known_full or to_parts not in known_full:
                continue
            contains = [str(c) for c in (conduit.get("contains") or [])]
            edges.append(
                {
                    "id": str(conduit_name),
                    "from": "/".join(from_parts),
                    "to": "/".join(to_parts),
                    "from_opening": from_op,
                    "to_opening": to_op,
                    "contains": contains,
                    "subtype": conduit.get("subtype"),
                }
            )

    return {
        "floor": {
            "id": floor_id,
            "label": str(floor_meta.get("label") or fdir.name),
            "type": str(floor_meta.get("type") or "Floor"),
        },
        "page": page,
        "nodes": nodes,
        "edges": edges,
    }


def apply_auto_layout(
    site_root: Path,
    floor_id: str,
    *,
    session_docs: dict[Path, dict[str, Any]],
    force: bool = False,
    gap_x: float = 180.0,
    gap_y: float = 140.0,
    origin_x: float = 80.0,
    origin_y: float = 80.0,
    cols: int = 4,
) -> list[str]:
    """Assign grid positions to nodes missing x/y (or all if force)."""
    graph = build_physical_graph(
        site_root, floor_id, session_docs=session_docs
    )
    fdir = floor_dir(site_root, floor_id)
    updated: list[str] = []
    for index, node in enumerate(graph["nodes"]):
        if not force and node.get("x") is not None and node.get("y") is not None:
            continue
        col = index % cols
        row = index // cols
        x = origin_x + col * gap_x
        y = origin_y + row * gap_y
        parts = tuple(node["parts"])
        yaml_path = (fdir.joinpath(*parts) / HOUSEWIRE_YAML).resolve()
        doc = session_docs.get(yaml_path)
        if doc is None:
            if not yaml_path.is_file():
                continue
            doc = load_yaml(yaml_path)
            session_docs[yaml_path] = doc
        set_physical_position(doc, x, y)
        updated.append(node["id"])
    return updated


def apply_positions(
    site_root: Path,
    floor_id: str,
    positions: dict[str, dict[str, Any]],
    *,
    session_docs: dict[Path, dict[str, Any]],
) -> list[str]:
    """Write positions ``{node_id: {x,y}}``. Return updated ids."""
    fdir = floor_dir(site_root, floor_id)
    updated: list[str] = []
    for node_id, pos in positions.items():
        parts = tuple(p for p in str(node_id).split("/") if p)
        if not parts:
            continue
        yaml_path = (fdir.joinpath(*parts) / HOUSEWIRE_YAML).resolve()
        doc = session_docs.get(yaml_path)
        if doc is None:
            if not yaml_path.is_file():
                raise FileNotFoundError(f"Unknown node: {node_id}")
            doc = load_yaml(yaml_path)
            session_docs[yaml_path] = doc
        set_physical_position(doc, float(pos["x"]), float(pos["y"]))
        updated.append(str(node_id))
    return updated
