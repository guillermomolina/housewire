"""JSON physical graph for the interactive UI (locations + conduits, no Graphviz)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from housewire.house import (
    catalog_icon,
    is_place_type,
    load_catalog,
    place_label,
    place_meta_from_mapping,
    place_name,
)
from housewire.house import (  # connection endpoint parsing (shared with WireViz)
    _expand_endpoint_token,
    _parse_element_path,
    _split_element_terminal,
)
from housewire.house.conduit_ref import (
    conduit_endpoints,
    resolve_location_ref,
    split_conduit_endpoint,
)
from housewire.project.io import HOUSEWIRE_YAML, load_yaml
from housewire.project.openings import declared_opening_ids, expand_opening_grid
from housewire.project.paths import is_excluded_path
from housewire.project.view_layout import (
    get_electrical_position,
    get_electrical_rotation,
    get_physical_page,
    get_physical_position,
    get_physical_view,
    set_electrical_position,
    set_physical_position,
)

# Window-style nested layout (must match UI constants in static/app.js).
LEAF_W = 120.0
LEAF_H = 56.0
LEAF_W_MAX = 260.0
CONTENT_PAD = 28.0  # margin on each side inside a parent window
CONTENT_HEADER = 36.0
LABEL_CHAR_W = 6.6  # approx. 11px sans glyph width
LABEL_INSET = 16.0
# Electrical element symbols inside a place (match static/app.js).
ELEM_W = 72.0
ELEM_H = 28.0
ELEM_GAP_X = 80.0
ELEM_GAP_Y = 36.0
ELEM_ORIGIN_X = 28.0
ELEM_ORIGIN_Y = 8.0


def _leaf_size(display_name: str) -> tuple[float, float]:
    """Leaf window size wide enough for the canvas name (capped)."""
    text = str(display_name or "").strip() or "?"
    width = LABEL_INSET + len(text) * LABEL_CHAR_W
    return (max(LEAF_W, min(LEAF_W_MAX, width)), LEAF_H)


def _default_local_pos(index: int, *, nested: bool) -> tuple[float, float]:
    cols = 4
    if nested:
        origin_x, origin_y, gap_x, gap_y = 28.0, 40.0, 160.0, 110.0
    else:
        origin_x, origin_y, gap_x, gap_y = 80.0, 80.0, 200.0, 160.0
    return (
        origin_x + (index % cols) * gap_x,
        origin_y + (index // cols) * gap_y,
    )


def _default_element_pos(index: int) -> tuple[float, float]:
    cols = 2
    return (
        ELEM_ORIGIN_X + (index % cols) * ELEM_GAP_X,
        ELEM_ORIGIN_Y + (index // cols) * ELEM_GAP_Y,
    )


def _opening_face(opening_id: str) -> str:
    text = str(opening_id).strip()
    if not text:
        return "?"
    return text[0].upper()


def _content_size(
    parts: tuple[str, ...],
    children_map: dict[tuple[str, ...], list[tuple[str, ...]]],
    pos_map: dict[tuple[str, ...], tuple[float, float]],
    name_map: dict[tuple[str, ...], str],
    cache: dict[tuple[str, ...], tuple[float, float]],
    element_boxes: dict[tuple[str, ...], list[tuple[float, float, float, float]]]
    | None = None,
) -> tuple[float, float]:
    """Bounding window size from nested places and electrical elements."""
    if parts in cache:
        return cache[parts]
    kids = children_map.get(parts, [])
    boxes = (element_boxes or {}).get(parts, [])
    max_r = 0.0
    max_b = 0.0
    has_content = False
    for kid in kids:
        kw, kh = _content_size(
            kid, children_map, pos_map, name_map, cache, element_boxes
        )
        kx, ky = pos_map[kid]
        max_r = max(max_r, kx + kw)
        max_b = max(max_b, ky + kh)
        has_content = True
    for ex, ey, ew, eh in boxes:
        max_r = max(max_r, ex + ew)
        max_b = max(max_b, ey + eh)
        has_content = True
    if not has_content:
        place_id = parts[-1] if parts else "?"
        cache[parts] = _leaf_size(name_map.get(parts, place_id))
        return cache[parts]
    cache[parts] = (
        max(LEAF_W, max_r + 2 * CONTENT_PAD),
        max(LEAF_H, CONTENT_HEADER + max_b + CONTENT_PAD),
    )
    return cache[parts]


def _iter_electrical_elements(
    doc: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Non-place entries under ``elements:`` (Socket, TerminalStrip, …)."""
    raw = doc.get("elements") or {}
    if not isinstance(raw, dict):
        return []
    out: list[tuple[str, dict[str, Any]]] = []
    for name, defn in sorted(raw.items(), key=lambda kv: str(kv[0]).lower()):
        if not isinstance(defn, dict):
            continue
        type_id = defn.get("type")
        if type_id is not None and is_place_type(type_id):
            continue
        out.append((str(name), defn))
    return out


def _element_node_id(place_parts: tuple[str, ...], element_name: str) -> str:
    if place_parts:
        return "/".join((*place_parts, element_name))
    return element_name


def split_element_node_id(node_id: str) -> tuple[tuple[str, ...], str]:
    parts = tuple(p for p in str(node_id).split("/") if p)
    if not parts:
        raise ValueError("empty element id")
    if len(parts) == 1:
        return (), parts[0]
    return parts[:-1], parts[-1]


def _via_cable_name(via_token: str) -> str:
    text = str(via_token).strip()
    if "." in text:
        text = text.split(".", 1)[0]
    return text.strip().rstrip("/")


def _connection_end_element_id(
    endpoint: str,
    *,
    current_parts: tuple[str, ...],
) -> str | None:
    """Resolve ``from``/``to`` to a canvas-relative element node id."""
    try:
        tokens = _expand_endpoint_token(str(endpoint))
        if not tokens:
            return None
        elem_ref, _terminal = _split_element_terminal(tokens[0])
        loc_parts, elem_name = _parse_element_path(
            elem_ref, current_location=list(current_parts)
        )
    except ValueError:
        return None
    return _element_node_id(tuple(loc_parts), elem_name)


def _build_element_nodes(
    *,
    places: list[tuple[tuple[str, ...], dict[str, Any]]],
    loc_doc: dict[str, Any],
) -> list[dict[str, Any]]:
    """Electrical elements for places in the graph (+ canvas root doc)."""
    sources: list[tuple[tuple[str, ...], dict[str, Any]]] = [
        (tuple(), loc_doc),
        *places,
    ]
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for place_parts, doc in sources:
        parent_id = "/".join(place_parts) if place_parts else None
        index = 0
        for name, defn in _iter_electrical_elements(doc):
            eid = _element_node_id(place_parts, name)
            if eid in seen:
                continue
            seen.add(eid)
            stored = get_electrical_position(defn)
            if stored is None:
                ex, ey = _default_element_pos(index)
            else:
                ex, ey = stored
            terminals_raw = defn.get("terminals") or {}
            terminals: list[str] = []
            if isinstance(terminals_raw, dict):
                terminals = [str(k) for k in terminals_raw.keys()]
            raw_name = defn.get("name")
            working_name = (
                str(raw_name).strip()
                if raw_name is not None and str(raw_name).strip()
                else None
            )
            label = defn.get("label")
            label_s = (
                str(label).strip()
                if label is not None and str(label).strip()
                else None
            )
            nodes.append(
                {
                    "id": eid,
                    "leaf_id": name,
                    "name": working_name,
                    "parent": parent_id,
                    "place_parts": list(place_parts),
                    "type": str(defn.get("type") or "Element"),
                    "subtype": defn.get("subtype"),
                    "label": label_s,
                    "display_name": working_name or name,
                    "display_label": label_s or working_name or name,
                    "terminals": terminals,
                    "x": ex,
                    "y": ey,
                    "w": ELEM_W,
                    "h": ELEM_H,
                    "rotation": get_electrical_rotation(defn),
                }
            )
            index += 1
    return nodes


def _build_cable_edges(
    *,
    places: list[tuple[tuple[str, ...], dict[str, Any]]],
    loc_doc: dict[str, Any],
    element_ids: set[str],
    elements: list[dict[str, Any]],
    conduit_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Connection edges whose endpoints are both in ``element_ids``.

    When the via cable appears in a conduit ``contains``, attach that conduit
    so the UI can route the cable along the tube.
    """
    elem_parent = {e["id"]: e.get("parent") for e in elements}
    conduit_by_cable: dict[str, dict[str, Any]] = {}
    for cedge in conduit_edges:
        for cable in cedge.get("contains") or []:
            conduit_by_cable[str(cable)] = cedge

    sources: list[tuple[tuple[str, ...], dict[str, Any]]] = [
        (tuple(), loc_doc),
        *places,
    ]
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for current_parts, doc in sources:
        connections = doc.get("connections") or []
        if not isinstance(connections, list):
            continue
        cables = doc.get("cables") or {}
        if not isinstance(cables, dict):
            cables = {}
        for index, conn in enumerate(connections):
            if not isinstance(conn, dict):
                continue
            from_id = _connection_end_element_id(
                str(conn.get("from") or ""), current_parts=current_parts
            )
            to_id = _connection_end_element_id(
                str(conn.get("to") or ""), current_parts=current_parts
            )
            if not from_id or not to_id:
                continue
            if from_id not in element_ids or to_id not in element_ids:
                continue
            if from_id == to_id:
                continue
            via = str(conn.get("via") or "")
            cable_name = _via_cable_name(via)
            key = (cable_name or f"conn-{index}", from_id, to_id)
            if key in seen:
                continue
            seen.add(key)
            colors: list[str] = []
            cable_name_disp = None
            cable_label = None
            cable = cables.get(cable_name)
            if isinstance(cable, dict):
                raw_colors = cable.get("colors") or []
                if isinstance(raw_colors, list):
                    colors = [str(c) for c in raw_colors]
                raw_n = cable.get("name")
                if raw_n is not None and str(raw_n).strip():
                    cable_name_disp = str(raw_n).strip()
                raw_l = cable.get("label")
                if raw_l is not None and str(raw_l).strip():
                    cable_label = str(raw_l).strip()
            row: dict[str, Any] = {
                "id": cable_name or f"connection_{index}",
                "name": cable_name_disp,
                "label": cable_label,
                "from": from_id,
                "to": to_id,
                "via": via,
                "colors": colors,
            }
            cedge = conduit_by_cable.get(cable_name)
            if cedge is not None:
                from_place = elem_parent.get(from_id)
                to_place = elem_parent.get(to_id)
                c_from = cedge.get("from")
                c_to = cedge.get("to")
                # Align openings with which place hosts each element.
                if from_place == c_from and to_place == c_to:
                    row["conduit"] = cedge.get("id")
                    row["conduit_from"] = c_from
                    row["conduit_to"] = c_to
                    row["from_opening"] = cedge.get("from_opening")
                    row["to_opening"] = cedge.get("to_opening")
                elif from_place == c_to and to_place == c_from:
                    row["conduit"] = cedge.get("id")
                    row["conduit_from"] = c_to
                    row["conduit_to"] = c_from
                    row["from_opening"] = cedge.get("to_opening")
                    row["to_opening"] = cedge.get("from_opening")
            edges.append(row)
    return edges


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
        place_id = root.name if location_id == "." else parent.name
        raw_name = meta.get("name")
        raw_label = meta.get("label")
        places[location_id] = {
            "id": location_id,
            "name": str(raw_name).strip() if raw_name is not None and str(raw_name).strip() else None,
            "label": str(raw_label).strip() if raw_label is not None and str(raw_label).strip() else None,
            "display_name": place_name(meta, place_id),
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
        kids.sort(key=lambda i: places[i]["display_name"].lower())

    rows: list[dict[str, Any]] = []

    def _walk(parent_key: str | None, depth: int) -> None:
        for loc_id in children.get(parent_key, []):
            info = places[loc_id]
            rows.append(
                {
                    "id": info["id"],
                    "name": info["name"],
                    "label": info["label"],
                    "display_name": info["display_name"],
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
                "name": info["name"],
                "label": info["label"],
                "display_name": info["display_name"],
                "type": info["type"],
                "path": info["path"],
                "depth": len(info["parts"]),
                "selectable": loc_id in selectable,
            }
        )
    return rows


def list_site_outline(site_root: Path) -> list[dict[str, Any]]:
    """Full site outline: every place + electrical elements (preorder flat).

    Place ids are site-relative (``.`` for the project root). Element ids are
    ``{place_id}/{element_name}`` (or just the element name under ``.``).
    ``selectable`` means the place can be a canvas root (has child places).
    ``icon`` is resolved from instance → site/package catalog.
    """
    root = site_root.resolve()
    catalog = load_catalog(root)
    places: dict[str, dict[str, Any]] = {}
    elements_by_place: dict[str, list[dict[str, Any]]] = {}

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
        place_id = root.name if location_id == "." else parent.name
        raw_name = meta.get("name")
        raw_label = meta.get("label")
        type_id = str(meta.get("type") or "Location")
        places[location_id] = {
            "id": location_id,
            "name": (
                str(raw_name).strip()
                if raw_name is not None and str(raw_name).strip()
                else None
            ),
            "label": (
                str(raw_label).strip()
                if raw_label is not None and str(raw_label).strip()
                else None
            ),
            "display_name": place_name(meta, place_id),
            "type": type_id,
            "icon": catalog_icon(type_id, catalog=catalog, instance=doc),
            "parts": parts,
        }
        elem_rows: list[dict[str, Any]] = []
        for ename, defn in _iter_electrical_elements(doc):
            eid = (
                ename if location_id == "." else f"{location_id}/{ename}"
            )
            raw_name = defn.get("name")
            working_name = (
                str(raw_name).strip()
                if raw_name is not None and str(raw_name).strip()
                else None
            )
            elabel = defn.get("label")
            label_s = (
                str(elabel).strip()
                if elabel is not None and str(elabel).strip()
                else None
            )
            etype = str(defn.get("type") or "Element")
            elem_rows.append(
                {
                    "kind": "element",
                    "id": eid,
                    "leaf_id": ename,
                    "name": working_name,
                    "parent": location_id,
                    "type": etype,
                    "icon": catalog_icon(etype, catalog=catalog, instance=defn),
                    "subtype": defn.get("subtype"),
                    "label": label_s,
                    "display_name": working_name or ename,
                    "display_label": label_s or working_name or ename,
                }
            )
        elements_by_place[location_id] = elem_rows

    def _is_descendant(ancestor: tuple[str, ...], other: tuple[str, ...]) -> bool:
        return len(other) > len(ancestor) and other[: len(ancestor)] == ancestor

    selectable: set[str] = set()
    for loc_id, info in places.items():
        parts = info["parts"]
        if any(_is_descendant(parts, other["parts"]) for other in places.values()):
            selectable.add(loc_id)

    children: dict[str | None, list[str]] = {}
    for loc_id, info in places.items():
        parts = info["parts"]
        if not parts:
            parent_key: str | None = None
        else:
            parent_key = "." if len(parts) == 1 else "/".join(parts[:-1])
            if parent_key not in places:
                parent_key = None
        children.setdefault(parent_key, []).append(loc_id)

    for kids in children.values():
        kids.sort(key=lambda i: places[i]["display_name"].lower())

    rows: list[dict[str, Any]] = []

    def _walk(parent_key: str | None, depth: int) -> None:
        for loc_id in children.get(parent_key, []):
            info = places[loc_id]
            rows.append(
                {
                    "kind": "place",
                    "id": info["id"],
                    "name": info["name"],
                    "label": info["label"],
                    "display_name": info["display_name"],
                    "type": info["type"],
                    "icon": info.get("icon") or "fa-circle",
                    "depth": depth,
                    "selectable": loc_id in selectable,
                }
            )
            for elem in elements_by_place.get(loc_id, []):
                rows.append({**elem, "depth": depth + 1})
            _walk(loc_id, depth + 1)

    _walk(None, 0)
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

    Each node includes ``w``/``h`` from the full descendant window layout so a
    parent keeps the same footprint whether or not its interior is shown.
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

    all_rows = list(iter_place_yaml_under(ldir, session_docs=session_docs))
    all_under = {parts for parts, _path in all_rows}
    max_depth = max((len(parts) for parts in all_under), default=0)
    depth = min(depth, max(max_depth, 1))

    # Full outline catalog (any depth) for window sizes and conduit resolve.
    all_docs: dict[tuple[str, ...], dict[str, Any]] = {}
    for parts, path in all_rows:
        try:
            doc = _doc_for(path)
        except ValueError:
            continue
        if place_meta_from_mapping(doc) is None:
            continue
        all_docs[parts] = doc

    children_map: dict[tuple[str, ...], list[tuple[str, ...]]] = {}
    for parts in all_docs:
        parent = parts[:-1]
        children_map.setdefault(parent, []).append(parts)
    for kids in children_map.values():
        kids.sort()

    pos_map: dict[tuple[str, ...], tuple[float, float]] = {}
    name_map: dict[tuple[str, ...], str] = {}
    element_boxes: dict[
        tuple[str, ...], list[tuple[float, float, float, float]]
    ] = {}
    for parts, doc in all_docs.items():
        meta = place_meta_from_mapping(doc) or {}
        place_id = parts[-1] if parts else ""
        name_map[parts] = place_name(meta, place_id)
        for index, (_ename, defn) in enumerate(_iter_electrical_elements(doc)):
            stored = get_electrical_position(defn)
            if stored is None:
                ex, ey = _default_element_pos(index)
            else:
                ex, ey = stored
            element_boxes.setdefault(parts, []).append((ex, ey, ELEM_W, ELEM_H))
    for parent, kids in children_map.items():
        nested = len(parent) > 0
        for index, kid in enumerate(kids):
            stored = get_physical_position(all_docs[kid])
            pos_map[kid] = (
                stored
                if stored is not None
                else _default_local_pos(index, nested=nested)
            )

    size_cache: dict[tuple[str, ...], tuple[float, float]] = {}

    places: list[tuple[tuple[str, ...], dict[str, Any]]] = [
        (parts, all_docs[parts])
        for parts in sorted(all_docs)
        if 1 <= len(parts) <= depth
    ]

    known_full = {parts for parts, _ in places}
    known_resolve = set(all_docs) | known_full
    nodes: list[dict[str, Any]] = []

    for parts, doc in places:
        meta = place_meta_from_mapping(doc) or {}
        type_id = str(meta.get("type") or "Location")
        if not is_place_type(type_id):
            type_id = "Location"
        try:
            openings = sorted(declared_opening_ids(meta.get("openings")) or [])
        except ValueError:
            openings = []
        opening_grid: dict[str, list[int]] = {}
        if meta.get("opening_grid") is not None:
            try:
                for face, (cols, rows) in expand_opening_grid(
                    meta.get("opening_grid")
                ).items():
                    opening_grid[face] = [int(cols), int(rows)]
            except ValueError:
                opening_grid = {}
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
        width, height = _content_size(
            parts,
            children_map,
            pos_map,
            name_map,
            size_cache,
            element_boxes,
        )
        px, py = pos_map[parts]
        place_id = parts[-1]
        raw_name = meta.get("name")
        raw_label = meta.get("label")
        nodes.append(
            {
                "id": "/".join(parts),
                "parts": list(parts),
                "parent": parent_id,
                "type": type_id,
                "name": (
                    str(raw_name).strip()
                    if raw_name is not None and str(raw_name).strip()
                    else None
                ),
                "label": (
                    str(raw_label).strip()
                    if raw_label is not None and str(raw_label).strip()
                    else None
                ),
                "display_name": place_name(meta, place_id),
                "display_label": place_label(meta, place_id),
                "openings": [
                    {"id": oid, "face": _opening_face(oid)} for oid in openings
                ],
                "opening_grid": opening_grid or None,
                "x": px,
                "y": py,
                "w": width,
                "h": height,
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
        *[(parts, doc) for parts, doc in places],
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
            cname = conduit.get("name")
            clabel = conduit.get("label")
            edges.append(
                {
                    "id": str(conduit_name),
                    "name": (
                        str(cname).strip()
                        if cname is not None and str(cname).strip()
                        else None
                    ),
                    "label": (
                        str(clabel).strip()
                        if clabel is not None and str(clabel).strip()
                        else None
                    ),
                    "from": from_id,
                    "to": to_id,
                    "from_opening": from_op,
                    "to_opening": to_op,
                    "contains": contains,
                    "subtype": conduit.get("subtype"),
                }
            )

    elements = _build_element_nodes(places=places, loc_doc=loc_doc)
    element_ids = {e["id"] for e in elements}
    cable_edges = _build_cable_edges(
        places=places,
        loc_doc=loc_doc,
        element_ids=element_ids,
        elements=elements,
        conduit_edges=edges,
    )

    return {
        "location": {
            "id": location_id,
            "name": (
                str(loc_meta.get("name")).strip()
                if loc_meta.get("name") is not None
                and str(loc_meta.get("name")).strip()
                else None
            ),
            "label": (
                str(loc_meta.get("label")).strip()
                if loc_meta.get("label") is not None
                and str(loc_meta.get("label")).strip()
                else None
            ),
            "display_name": place_name(loc_meta, ldir.name),
            "display_label": place_label(loc_meta, ldir.name),
            "type": str(loc_meta.get("type") or "Location"),
        },
        "page": page,
        "depth": depth,
        "max_depth": max_depth,
        "nodes": nodes,
        "edges": edges,
        "elements": elements,
        "cable_edges": cable_edges,
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
            parts = tuple(node["parts"])
            yaml_path = (ldir.joinpath(*parts) / HOUSEWIRE_YAML).resolve()
            doc = session_docs.get(yaml_path)
            if doc is None:
                if not yaml_path.is_file():
                    continue
                doc = load_yaml(yaml_path)
                session_docs[yaml_path] = doc
            stored = get_physical_position(doc)
            if not force and stored is not None:
                continue
            col = index % cols
            row = index // cols
            # Nested siblings sit closer; top-level keeps the roomier grid.
            nested = node.get("parent") is not None
            ox = 28.0 if nested else origin_x
            oy = 40.0 if nested else origin_y
            gx = 160.0 if nested else gap_x
            gy = 110.0 if nested else gap_y
            x = ox + col * gx
            y = oy + row * gy
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


def apply_electrical_positions(
    site_root: Path,
    location_id: str,
    positions: dict[str, dict[str, Any]],
    *,
    session_docs: dict[Path, dict[str, Any]],
) -> list[str]:
    """Write ``view.electrical`` for ``{place/element: {x,y}}``. Return ids."""
    ldir = location_dir(site_root, location_id)
    updated: list[str] = []
    for node_id, pos in positions.items():
        place_parts, element_name = split_element_node_id(str(node_id))
        yaml_path = (
            (ldir / HOUSEWIRE_YAML).resolve()
            if not place_parts
            else (ldir.joinpath(*place_parts) / HOUSEWIRE_YAML).resolve()
        )
        doc = session_docs.get(yaml_path)
        if doc is None:
            if not yaml_path.is_file():
                raise FileNotFoundError(f"Unknown element host: {node_id}")
            doc = load_yaml(yaml_path)
            session_docs[yaml_path] = doc
        elements = doc.get("elements")
        if not isinstance(elements, dict) or element_name not in elements:
            raise FileNotFoundError(f"Unknown element: {node_id}")
        elem = elements[element_name]
        if not isinstance(elem, dict):
            raise ValueError(f"Element {node_id} is not a map")
        set_electrical_position(elem, float(pos["x"]), float(pos["y"]))
        updated.append(str(node_id))
    return updated


def apply_electrical_auto_layout(
    site_root: Path,
    location_id: str,
    *,
    session_docs: dict[Path, dict[str, Any]],
    depth: int = 1,
    force: bool = False,
) -> list[str]:
    """Assign grid ``view.electrical`` when missing (or all if force)."""
    graph = build_physical_graph(
        site_root, location_id, depth=depth, session_docs=session_docs
    )
    ldir = location_dir(site_root, location_id)
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for elem in graph.get("elements") or []:
        by_parent.setdefault(elem.get("parent"), []).append(elem)

    updated: list[str] = []
    for siblings in by_parent.values():
        index = 0
        for elem in siblings:
            place_parts = tuple(elem.get("place_parts") or [])
            element_name = str(elem.get("leaf_id") or elem.get("name") or "")
            yaml_path = (
                (ldir / HOUSEWIRE_YAML).resolve()
                if not place_parts
                else (ldir.joinpath(*place_parts) / HOUSEWIRE_YAML).resolve()
            )
            doc = session_docs.get(yaml_path)
            if doc is None:
                if not yaml_path.is_file():
                    continue
                doc = load_yaml(yaml_path)
                session_docs[yaml_path] = doc
            elements = doc.get("elements")
            if not isinstance(elements, dict):
                continue
            defn = elements.get(element_name)
            if not isinstance(defn, dict):
                continue
            stored = get_electrical_position(defn)
            if not force and stored is not None:
                continue
            x, y = _default_element_pos(index)
            set_electrical_position(defn, x, y)
            updated.append(str(elem["id"]))
            index += 1
    return updated
