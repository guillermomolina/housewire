"""JSON physical graph for the interactive UI (locations + conduits, no Graphviz)."""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from housewire.house import (
    catalog_icon,
    catalog_type_label,
    is_place_type,
    load_catalog,
    place_label,
    place_meta_from_mapping,
    place_name,
)
from housewire.house import (  # connection endpoint parsing
    _expand_endpoint_token,
    _parse_element_path,
    _split_element_terminal,
)
from housewire.house.conduit_ref import (
    conduit_endpoints,
    resolve_location_ref,
    split_conduit_endpoint,
)
from housewire.house.links import contained_ids, connection_type
from housewire.site.io import load_yaml
from housewire.site.openings import declared_opening_ids, expand_opening_grid
from housewire.site.terminals import element_terminal_layout, grid_to_api
from housewire.site.tree import (
    get_place_node,
    iter_place_children,
    iter_places,
    logical_parts_from_id,
    site_yaml_path,
)
from housewire.site.view_layout import (
    BOUNDS_SPRITE,
    ISO_DEPTH,
    clear_electrical_size,
    clear_physical_size,
    get_electrical_flips,
    get_electrical_position,
    get_electrical_rotation,
    get_electrical_size,
    get_physical_flips,
    get_physical_page,
    get_physical_position,
    get_physical_size,
    get_physical_view,
    grow_view_size_by,
    migrate_site_physical_to_sprite,
    normalize_view_xy_siblings,
    place_paints_iso,
    set_electrical_position,
    set_electrical_size,
    set_physical_bounds,
    set_physical_position,
    set_physical_size,
    shift_place_origin,
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
    from housewire.site.natural_sort import natural_sort_key

    raw = doc.get("elements") or {}
    if not isinstance(raw, dict):
        return []
    out: list[tuple[str, dict[str, Any]]] = []
    for name, defn in sorted(raw.items(), key=lambda kv: natural_sort_key(str(kv[0]))):
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


def _via_wire_indices(via_token: str) -> list[int]:
    """Parse 1-based wire indices from ``Cable.1`` or ``Cable.[1, 2, 3]``."""
    text = str(via_token).strip()
    if "." not in text:
        return []
    _name, _, rest = text.partition(".")
    rest = rest.strip()
    if not rest:
        return []
    if rest.startswith("[") and rest.endswith("]"):
        inner = rest[1:-1]
        out: list[int] = []
        for part in inner.split(","):
            token = part.strip()
            if token.isdigit():
                out.append(int(token))
        return out
    if rest.isdigit():
        return [int(rest)]
    return []


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


def _connection_end_pin(endpoint: str) -> str | None:
    """Return the terminal pin id from a connection endpoint, if any."""
    try:
        tokens = _expand_endpoint_token(str(endpoint))
        if not tokens:
            return None
        _elem_ref, terminal = _split_element_terminal(tokens[0])
        return str(terminal)
    except ValueError:
        return None


def _build_element_nodes(
    *,
    places: list[tuple[tuple[str, ...], dict[str, Any]]],
    loc_doc: dict[str, Any],
    catalog=None,
    locale: str | None = None,
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
            terminals_merged, tgrid, pin_cells = element_terminal_layout(
                defn if isinstance(defn, dict) else {},
                catalog if isinstance(catalog, dict) else None,
            )
            terminals = [str(k) for k in terminals_merged.keys()]
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
            notes = defn.get("notes")
            notes_s = (
                str(notes).strip()
                if notes is not None and str(notes).strip()
                else None
            )
            etype = str(defn.get("type") or "Element")
            max_cols = 1
            for cols, _rows in tgrid.values():
                max_cols = max(max_cols, int(cols))
            auto_w = max(ELEM_W, 28 + max_cols * 14)
            auto_h = ELEM_H
            stored_size = get_electrical_size(defn)
            size_locked = stored_size is not None
            if stored_size is not None:
                ew, eh = stored_size
            else:
                ew, eh = auto_w, auto_h
            nodes.append(
                {
                    "id": eid,
                    "leaf_id": name,
                    "name": working_name,
                    "parent": parent_id,
                    "place_parts": list(place_parts),
                    "type": etype,
                    "subtype": defn.get("subtype"),
                    "icon": catalog_icon(etype, catalog=catalog, instance=defn),
                    "type_label": catalog_type_label(
                        etype,
                        catalog=catalog,
                        subtype=(
                            str(defn.get("subtype"))
                            if defn.get("subtype") is not None
                            else None
                        ),
                        locale=locale,
                    ),
                    "label": label_s,
                    "notes": notes_s,
                    "display_name": working_name or name,
                    "display_label": label_s or working_name or name,
                    "terminals": terminals,
                    "terminal_grid": grid_to_api(tgrid) if tgrid else None,
                    "terminal_pins": pin_cells or None,
                    "x": ex,
                    "y": ey,
                    "w": ew,
                    "h": eh,
                    "size_locked": size_locked,
                    "locked_w": stored_size[0] if stored_size is not None else None,
                    "locked_h": stored_size[1] if stored_size is not None else None,
                    "rotation": get_electrical_rotation(defn),
                    "flip_ns": get_electrical_flips(defn)[0],
                    "flip_we": get_electrical_flips(defn)[1],
                }
            )
            index += 1
    return nodes


def _conduit_carries(cedge: dict[str, Any], cable_name: str) -> bool:
    """True if conduit ``contains`` the id or lists it in ``contains_all``."""
    if cable_name in [str(c) for c in (cedge.get("contains") or [])]:
        return True
    return cable_name in [str(c) for c in (cedge.get("contains_all") or [])]


def _conduit_hops_for_cable(
    cable_name: str,
    from_place: str | None,
    to_place: str | None,
    conduit_edges: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Shortest chain of conduit edges that carry ``cable_name`` between places.

    Returns oriented hops ``{conduit, from, to, from_opening, to_opening}``,
    or ``None`` when there is no path (including same-place / intra-box).
    """
    if not cable_name or not from_place or not to_place:
        return None
    if from_place == to_place:
        return None

    adj: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for cedge in conduit_edges:
        if not _conduit_carries(cedge, cable_name):
            continue
        a = str(cedge.get("from") or "")
        b = str(cedge.get("to") or "")
        if not a or not b or a == b:
            continue
        cid = str(cedge.get("id") or "")
        a_op = cedge.get("from_opening")
        b_op = cedge.get("to_opening")
        if not a_op or not b_op:
            continue
        fwd = {
            "conduit": cid,
            "from": a,
            "to": b,
            "from_opening": a_op,
            "to_opening": b_op,
        }
        rev = {
            "conduit": cid,
            "from": b,
            "to": a,
            "from_opening": b_op,
            "to_opening": a_op,
        }
        adj.setdefault(a, []).append((b, fwd))
        adj.setdefault(b, []).append((a, rev))

    # BFS for fewest hops (then stable by conduit id).
    queue: deque[str] = deque([from_place])
    prev: dict[str, tuple[str, dict[str, Any]] | None] = {from_place: None}
    while queue:
        cur = queue.popleft()
        if cur == to_place:
            break
        neighbors = sorted(adj.get(cur, []), key=lambda t: (t[1]["conduit"], t[0]))
        for nxt, hop in neighbors:
            if nxt in prev:
                continue
            prev[nxt] = (cur, hop)
            queue.append(nxt)

    if to_place not in prev or to_place == from_place:
        return None

    hops: list[dict[str, Any]] = []
    cur = to_place
    while cur != from_place:
        step = prev.get(cur)
        if step is None:
            return None
        parent, hop = step
        hops.append(hop)
        cur = parent
    hops.reverse()
    return hops or None


def _persisted_conduit_hops(
    conduit_path: Any,
    from_place: str | None,
    to_place: str | None,
    conduit_edges: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Resolve a user-selected conduit sequence against visible conduit edges."""
    if not isinstance(conduit_path, list) or not conduit_path:
        return None
    if not from_place or not to_place or from_place == to_place:
        return None
    current = from_place
    hops: list[dict[str, Any]] = []
    for raw_hop in conduit_path:
        if not isinstance(raw_hop, dict):
            return None
        conduit_id = str(raw_hop.get("conduit") or "")
        edge = next(
            (item for item in conduit_edges if str(item.get("id") or "") == conduit_id),
            None,
        )
        if edge is None:
            return None
        direct = {
            "conduit": conduit_id,
            "from": str(edge.get("from") or ""),
            "to": str(edge.get("to") or ""),
            "from_opening": edge.get("from_opening"),
            "to_opening": edge.get("to_opening"),
        }
        reverse = {
            "conduit": conduit_id,
            "from": direct["to"],
            "to": direct["from"],
            "from_opening": direct["to_opening"],
            "to_opening": direct["from_opening"],
        }
        if direct["from"] == current:
            hop = direct
        elif reverse["from"] == current:
            hop = reverse
        else:
            return None
        hops.append(hop)
        current = hop["to"]
    return hops if current == to_place else None


def _build_cable_edges(
    *,
    places: list[tuple[tuple[str, ...], dict[str, Any]]],
    loc_doc: dict[str, Any],
    element_ids: set[str],
    elements: list[dict[str, Any]],
    conduit_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Conductor edges whose endpoints are both in ``element_ids``.

    Group sibling conductors under the same cable that share the same host
    elements into one multi-color ``cable_edge`` for jacket drawing.
    """
    catalog = load_catalog()
    elem_parent = {e["id"]: e.get("parent") for e in elements}

    sources: list[tuple[tuple[str, ...], dict[str, Any]]] = [
        (tuple(), loc_doc),
        *places,
    ]
    # Collect conductors: (cable_or_self, from_id, to_id, from_pin, to_pin, color, name, label)
    raw_rows: list[dict[str, Any]] = []
    for current_parts, doc in sources:
        cables = doc.get("cables") or {}
        if not isinstance(cables, dict):
            continue
        # child -> immediate cable; resolve repeatedly below so cables can be
        # grouped into another cable.
        parent_of: dict[str, str] = {}
        for name, entry in cables.items():
            if not isinstance(entry, dict):
                continue
            try:
                type_id = connection_type(entry)
            except ValueError:
                continue
            if type_id != "Cable":
                continue
            for child in entry.get("contains") or []:
                parent_of[str(child)] = str(name)
        for name, entry in cables.items():
            if not isinstance(entry, dict):
                continue
            try:
                type_id = connection_type(entry)
            except ValueError:
                continue
            if type_id != "Conductor":
                continue
            from_raw = str(entry.get("from") or "")
            to_raw = str(entry.get("to") or "")
            if not from_raw or not to_raw:
                continue
            from_id = _connection_end_element_id(
                from_raw, current_parts=current_parts
            )
            to_id = _connection_end_element_id(
                to_raw, current_parts=current_parts
            )
            if not from_id or not to_id:
                continue
            if from_id not in element_ids or to_id not in element_ids:
                continue
            if from_id == to_id:
                continue
            cable = str(name)
            seen: set[str] = set()
            while cable in parent_of and cable not in seen:
                seen.add(cable)
                cable = parent_of[cable]
            raw_n = entry.get("name")
            raw_l = entry.get("label")
            raw_rows.append(
                {
                    "cable": cable,
                    "conductor": str(name),
                    "from": from_id,
                    "to": to_id,
                    "from_pin": _connection_end_pin(from_raw) or "",
                    "to_pin": _connection_end_pin(to_raw) or "",
                    "color": str(entry.get("color") or "BK"),
                    "name": (
                        str(raw_n).strip()
                        if raw_n is not None and str(raw_n).strip()
                        else None
                    ),
                    "label": (
                        str(raw_l).strip()
                        if raw_l is not None and str(raw_l).strip()
                        else None
                    ),
                    "conduit_path": entry.get("conduit_path"),
                }
            )

    # Group by cable + unordered element pair for multi-strand jacket.
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in raw_rows:
        a, b = row["from"], row["to"]
        if a <= b:
            key = (row["cable"], a, b)
            groups.setdefault(key, []).append(row)
        else:
            # Opposite conductor direction: normalize to lo→hi and swap pins.
            key = (row["cable"], b, a)
            groups.setdefault(key, []).append(
                {
                    **row,
                    "from": b,
                    "to": a,
                    "from_pin": row["to_pin"],
                    "to_pin": row["from_pin"],
                }
            )

    edges: list[dict[str, Any]] = []
    for (cable, from_id, to_id), members in groups.items():
        members_sorted = sorted(members, key=lambda m: m["conductor"])
        colors = [m["color"] for m in members_sorted]
        # Prefer cable display name when grouping multiple strands.
        cable_entry = None
        for _parts, doc in sources:
            cables = doc.get("cables") or {}
            if isinstance(cables, dict) and cable in cables:
                cable_entry = cables[cable]
                break
        name_disp = members_sorted[0]["name"]
        label_disp = members_sorted[0]["label"]
        jacket_color: str | None = None
        if isinstance(cable_entry, dict):
            sn = cable_entry.get("name")
            sl = cable_entry.get("label")
            if sn is not None and str(sn).strip():
                name_disp = str(sn).strip()
            if sl is not None and str(sl).strip():
                label_disp = str(sl).strip()
            # Jacket only for a real Cable (has ``contains``), not a
            # bare conductor that happens to be its own cable key.
            has_children = bool(cable_entry.get("contains"))
            if has_children or len(members_sorted) > 1:
                try:
                    cable_type = connection_type(cable_entry)
                except ValueError:
                    cable_type = "Cable" if has_children else "Conductor"
                if cable_type == "Cable" or has_children:
                    jc = cable_entry.get("color")
                    jacket_color = (
                        str(jc).strip().upper() if jc else None
                    )
        # Multi-color jacket edge: per-strand pins stay aligned with colors/
        # conductors so each wire can land on its own terminal cell.
        from_pins = [m["from_pin"] or None for m in members_sorted]
        to_pins = [m["to_pin"] or None for m in members_sorted]
        row: dict[str, Any] = {
            "id": cable,
            "name": name_disp,
            "label": label_disp,
            "from": from_id,
            "to": to_id,
            "from_pin": from_pins[0],
            "to_pin": to_pins[0],
            "from_pins": from_pins,
            "to_pins": to_pins,
            "via": cable,
            "colors": colors,
            "jacket_color": jacket_color,
            "via_indices": list(range(1, len(colors) + 1)),
            "conductors": [m["conductor"] for m in members_sorted],
        }
        hops = None
        for member in members_sorted:
            hops = _persisted_conduit_hops(
                member.get("conduit_path"),
                elem_parent.get(from_id),
                elem_parent.get(to_id),
                conduit_edges,
            )
            if hops:
                break
        if hops is None:
            hops = _conduit_hops_for_cable(
                cable,
                elem_parent.get(from_id),
                elem_parent.get(to_id),
                conduit_edges,
            )
        if hops is None:
            # Also try matching via each conductor id.
            for m in members_sorted:
                hops = _conduit_hops_for_cable(
                    m["conductor"],
                    elem_parent.get(from_id),
                    elem_parent.get(to_id),
                    conduit_edges,
                )
                if hops:
                    break
        if hops:
            row["conduit_hops"] = hops
            row["conduit"] = hops[0]["conduit"] if len(hops) == 1 else None
            row["conduit_from"] = hops[0]["from"]
            row["conduit_to"] = hops[-1]["to"]
            row["from_opening"] = hops[0]["from_opening"]
            row["to_opening"] = hops[-1]["to_opening"]
        edges.append(row)
    return edges


def location_dir(site_root: Path, location_id: str) -> Path:
    """Return the site root (places are nested in one YAML, not directories)."""
    del location_id  # logical id; filesystem root is always the site
    return site_root.resolve()


def _load_site_doc(
    site_root: Path,
    *,
    session_docs: dict[Path, dict[str, Any]] | None = None,
    site_yaml: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    if site_yaml is not None:
        path = site_yaml.resolve()
    else:
        path = site_yaml_path(site_root)
    if session_docs:
        for key, doc in session_docs.items():
            if key.resolve() == path:
                return path, doc
        # Active buffer may be the only known document when several YAMLs
        # share the site root (find_site_yaml is ambiguous).
        if len(session_docs) == 1:
            key, doc = next(iter(session_docs.items()))
            return key.resolve(), doc
    if not path.is_file():
        raise FileNotFoundError(f"No site .yaml/.yml at site root {site_root}")
    return path, load_yaml(path)


def iter_place_yaml_under(
    location_dir_path: Path,
    *,
    session_docs: dict[Path, dict[str, Any]] | None = None,
) -> list[tuple[tuple[str, ...], Path]]:
    """Compatibility shim: nested places share the site YAML path.

    ``location_dir_path`` must be the site root. Relative parts are logical.
    """
    site_root = location_dir_path.resolve()
    try:
        yaml_path, doc = _load_site_doc(site_root, session_docs=session_docs)
    except FileNotFoundError:
        return []
    return [(parts, yaml_path) for parts, _node in iter_places(doc, under=())]


def list_canvas_locations(
    site_root: Path,
    *,
    site_yaml: Path | None = None,
    session_docs: dict[Path, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Place tree (preorder), only nodes useful as canvas roots.

    Each row includes ``depth`` for UI indentation. A node is included if it
    has child places (selectable) or is an ancestor of such a node. An empty
    site (root with no child places) still lists ``"."`` so the first items
    can be placed.
    Pass ``site_yaml`` when the site root contains several YAML files.
    """
    root = site_root.resolve()
    try:
        _path, site_doc = _load_site_doc(
            root, site_yaml=site_yaml, session_docs=session_docs
        )
    except FileNotFoundError:
        return []

    places: dict[str, dict[str, Any]] = {}
    root_meta = place_meta_from_mapping(site_doc)
    if root_meta is not None:
        places["."] = {
            "id": ".",
            "name": (
                str(root_meta["name"]).strip()
                if root_meta.get("name") is not None and str(root_meta.get("name")).strip()
                else None
            ),
            "label": (
                str(root_meta["label"]).strip()
                if root_meta.get("label") is not None and str(root_meta.get("label")).strip()
                else None
            ),
            "display_name": place_name(root_meta, root.name),
            "type": str(root_meta.get("type") or "Location"),
            "path": ".",
            "parts": (),
        }
    for parts, node in iter_places(site_doc, under=()):
        meta = place_meta_from_mapping(node) or {}
        location_id = "/".join(parts)
        place_id = parts[-1]
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
        if any(_is_descendant(parts, other["parts"]) for other in places.values()):
            selectable.add(loc_id)

    # Empty site (House with no child places): still expose root so the UI can
    # open a canvas and place the first containers/elements.
    if "." in places and not selectable:
        selectable.add(".")

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
            if parent_key not in places:
                parent_key = None
        children.setdefault(parent_key, []).append(loc_id)

    from housewire.site.natural_sort import natural_sort_key

    for kids in children.values():
        kids.sort(key=lambda i: natural_sort_key(places[i]["display_name"]))

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


def list_site_outline(
    site_root: Path,
    *,
    site_yaml: Path | None = None,
    session_docs: dict[Path, dict[str, Any]] | None = None,
    locale: str | None = None,
) -> list[dict[str, Any]]:
    """Full site outline: every place + electrical elements (preorder flat)."""
    root = site_root.resolve()
    catalog = load_catalog(root)
    try:
        _path, site_doc = _load_site_doc(
            root, site_yaml=site_yaml, session_docs=session_docs
        )
    except FileNotFoundError:
        return []

    places: dict[str, dict[str, Any]] = {}
    elements_by_place: dict[str, list[dict[str, Any]]] = {}

    def _register(location_id: str, parts: tuple[str, ...], node: dict[str, Any]) -> None:
        meta = place_meta_from_mapping(node)
        if meta is None:
            return
        place_id = root.name if location_id == "." else parts[-1]
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
            "icon": catalog_icon(type_id, catalog=catalog, instance=node),
            "type_label": catalog_type_label(type_id, catalog=catalog, locale=locale),
            "parts": parts,
        }
        elem_rows: list[dict[str, Any]] = []
        for ename, defn in _iter_electrical_elements(node):
            eid = ename if location_id == "." else f"{location_id}/{ename}"
            raw_n = defn.get("name")
            working_name = (
                str(raw_n).strip() if raw_n is not None and str(raw_n).strip() else None
            )
            elabel = defn.get("label")
            label_s = (
                str(elabel).strip()
                if elabel is not None and str(elabel).strip()
                else None
            )
            notes = defn.get("notes")
            notes_s = (
                str(notes).strip()
                if notes is not None and str(notes).strip()
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
                    "type_label": catalog_type_label(
                        etype,
                        catalog=catalog,
                        subtype=(
                            str(defn.get("subtype"))
                            if defn.get("subtype") is not None
                            else None
                        ),
                        locale=locale,
                    ),
                    "subtype": defn.get("subtype"),
                    "label": label_s,
                    "notes": notes_s,
                    "display_name": working_name or ename,
                    "display_label": label_s or working_name or ename,
                }
            )
        elements_by_place[location_id] = elem_rows

    _register(".", (), site_doc)
    for parts, node in iter_places(site_doc, under=()):
        _register("/".join(parts), parts, node)

    def _is_descendant(ancestor: tuple[str, ...], other: tuple[str, ...]) -> bool:
        return len(other) > len(ancestor) and other[: len(ancestor)] == ancestor

    selectable: set[str] = set()
    for loc_id, info in places.items():
        parts = info["parts"]
        if any(_is_descendant(parts, other["parts"]) for other in places.values()):
            selectable.add(loc_id)

    # Empty site (House with no child places): root is still a canvas location.
    if "." in places and not selectable:
        selectable.add(".")

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

    from housewire.site.natural_sort import natural_sort_key

    for kids in children.values():
        kids.sort(key=lambda i: natural_sort_key(places[i]["display_name"]))

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
                    "icon": info.get("icon") or "circle",
                    "type_label": info.get("type_label")
                    or catalog_type_label(info["type"], catalog=catalog, locale=locale),
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
    locale: str | None = None,
    site_yaml: Path | None = None,
) -> dict[str, Any]:
    """Build UI graph for one location (nested places in the site YAML)."""
    if depth < 1:
        raise ValueError("depth must be >= 1")
    _yaml_path, site_doc = _load_site_doc(
        site_root, session_docs=session_docs, site_yaml=site_yaml
    )
    if migrate_site_physical_to_sprite(site_doc) and session_docs is not None:
        session_docs[_yaml_path] = site_doc
    canvas_parts = logical_parts_from_id(location_id)
    try:
        loc_doc = get_place_node(site_doc, canvas_parts)
    except ValueError as exc:
        raise FileNotFoundError(f"No place for location {location_id!r}") from exc

    loc_meta = place_meta_from_mapping(loc_doc) or {}
    page = get_physical_page(loc_doc)
    catalog = load_catalog(site_root)

    all_docs: dict[tuple[str, ...], dict[str, Any]] = {
        parts: node for parts, node in iter_places(site_doc, under=canvas_parts)
    }
    all_under = set(all_docs)
    max_depth = max((len(parts) for parts in all_under), default=0)
    depth = min(depth, max(max_depth, 1))

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
            stored_sz = get_electrical_size(defn)
            if stored_sz is not None:
                ew, eh = stored_sz
            else:
                ew, eh = ELEM_W, ELEM_H
            element_boxes.setdefault(parts, []).append((ex, ey, ew, eh))
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
        flip_ns, flip_we = get_physical_flips(doc)
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
        if place_paints_iso(doc):
            # Sprite AABB includes NW iso depth beyond the content/front box.
            width += ISO_DEPTH
            height += ISO_DEPTH
        stored_size = get_physical_size(doc)
        size_locked = stored_size is not None
        if stored_size is not None:
            sw, sh = stored_size
            width = max(width, sw)
            height = max(height, sh)
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
                "icon": catalog_icon(type_id, catalog=catalog, instance=doc),
                "type_label": catalog_type_label(type_id, catalog=catalog, locale=locale),
                "openings": [
                    {"id": oid, "face": _opening_face(oid)} for oid in openings
                ],
                "opening_grid": opening_grid or None,
                "x": px,
                "y": py,
                "w": width,
                "h": height,
                "size_locked": size_locked,
                "locked_w": stored_size[0] if stored_size is not None else None,
                "locked_h": stored_size[1] if stored_size is not None else None,
                "rotation": rotation,
                "flip_ns": flip_ns,
                "flip_we": flip_we,
                "expandable": has_deeper,
            }
        )

    def _visible_endpoint(parts: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if parts is None or parts not in known_resolve:
            return None
        if parts in known_full:
            return parts
        for cut in range(min(len(parts), depth), 0, -1):
            anc = parts[:cut]
            if anc in known_full:
                return anc
        return None

    edges: list[dict[str, Any]] = []
    # One drawn tube per opening pair (union contains). Avoids double tubes when
    # a cross-location run was wrongly duplicated at an ancestor.
    edge_by_geom: dict[tuple[tuple[str, str], tuple[str, str]], dict[str, Any]] = {}
    edge_sources: list[tuple[tuple[str, ...], dict[str, Any]]] = [
        (tuple(), loc_doc),
        *[(parts, doc) for parts, doc in places],
    ]
    catalog = load_catalog()
    for current_parts, doc in edge_sources:
        cables = doc.get("cables") or {}
        if not isinstance(cables, dict):
            continue
        for conduit_name, conduit in cables.items():
            if not isinstance(conduit, dict):
                continue
            try:
                if connection_type(conduit) != "Conduit":
                    continue
            except ValueError:
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
            a = (from_id, from_op or "")
            b = (to_id, to_op or "")
            geom_key = (a, b) if a <= b else (b, a)
            contains = [str(c) for c in (conduit.get("contains") or [])]
            all_ids = set(contained_ids(cables, str(conduit_name)))
            cname = conduit.get("name")
            clabel = conduit.get("label")
            raw_color = conduit.get("color")
            tube_color = (
                str(raw_color).strip().upper()
                if raw_color is not None and str(raw_color).strip()
                else None
            )
            raw_install = conduit.get("install")
            tube_install = (
                str(raw_install).strip()
                if raw_install is not None and str(raw_install).strip()
                else None
            )
            existing = edge_by_geom.get(geom_key)
            if existing is None:
                edge_by_geom[geom_key] = {
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
                    "contains": list(contains),
                    "contains_all": sorted(all_ids),
                    "subtype": conduit.get("subtype"),
                    "color": tube_color,
                    "install": tube_install,
                }
            else:
                merged = list(dict.fromkeys([*existing["contains"], *contains]))
                existing["contains"] = merged
                existing["contains_all"] = sorted(
                    set(existing["contains_all"]) | all_ids | set(merged)
                )
                if existing.get("color") is None and tube_color is not None:
                    existing["color"] = tube_color
                if existing.get("install") is None and tube_install is not None:
                    existing["install"] = tube_install
                if existing.get("subtype") is None and conduit.get("subtype") is not None:
                    existing["subtype"] = conduit.get("subtype")
    edges = list(edge_by_geom.values())

    elements = _build_element_nodes(
        places=places, loc_doc=loc_doc, catalog=catalog, locale=locale
    )
    element_ids = {e["id"] for e in elements}
    cable_edges = _build_cable_edges(
        places=places,
        loc_doc=loc_doc,
        element_ids=element_ids,
        elements=elements,
        conduit_edges=edges,
    )

    canvas_leaf = (
        site_root.resolve().name
        if not canvas_parts
        else canvas_parts[-1]
    )
    canvas_flip_ns, canvas_flip_we = get_physical_flips(loc_doc)
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
            "display_name": place_name(loc_meta, canvas_leaf),
            "display_label": place_label(loc_meta, canvas_leaf),
            "type": str(loc_meta.get("type") or "Location"),
            "flip_ns": canvas_flip_ns,
            "flip_we": canvas_flip_we,
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
    site_yaml: Path | None = None,
) -> list[str]:
    """Assign grid positions to nodes missing x/y (or all if force)."""
    graph = build_physical_graph(
        site_root,
        location_id,
        depth=depth,
        session_docs=session_docs,
        site_yaml=site_yaml,
    )
    yaml_path, site_doc = _load_site_doc(
        site_root, session_docs=session_docs, site_yaml=site_yaml
    )
    session_docs[yaml_path] = site_doc
    canvas_parts = logical_parts_from_id(location_id)
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for node in graph["nodes"]:
        parent = node.get("parent")
        by_parent.setdefault(parent, []).append(node)

    updated: list[str] = []
    for siblings in by_parent.values():
        index = 0
        for node in siblings:
            parts = tuple(node["parts"])
            place = get_place_node(site_doc, canvas_parts + parts)
            stored = get_physical_position(place)
            if not force and stored is not None:
                continue
            col = index % cols
            row = index // cols
            nested = node.get("parent") is not None
            ox = 28.0 if nested else origin_x
            oy = 40.0 if nested else origin_y
            gx = 160.0 if nested else gap_x
            gy = 110.0 if nested else gap_y
            x = ox + col * gx
            y = oy + row * gy
            set_physical_position(place, x, y)
            if force:
                clear_physical_size(place)
            updated.append(node["id"])
            index += 1
    return updated


def _absorb_place_children_origin(
    site_doc: dict[str, Any],
    canvas_parts: tuple[str, ...],
    parent_parts: tuple[str, ...],
    updated: list[str],
    *,
    _depth: int = 0,
) -> None:
    """Shift sibling places out of negatives; move parent N/W wall; cascade."""
    if _depth > 32:
        return
    parent = get_place_node(site_doc, parent_parts)
    siblings = [child for _name, child in iter_place_children(parent)]
    dx, dy = normalize_view_xy_siblings(siblings, layer="physical")
    if not dx and not dy:
        return
    rel = parent_parts[len(canvas_parts) :]
    for name, _child in iter_place_children(parent):
        sid = "/".join((*rel, name)) if rel else name
        if sid not in updated:
            updated.append(sid)
    if parent_parts:
        shift_place_origin(parent, dx, dy)
        parent_rel = "/".join(parent_parts[len(canvas_parts) :])
        if parent_rel and parent_rel not in updated:
            updated.append(parent_rel)
        _absorb_place_children_origin(
            site_doc,
            canvas_parts,
            parent_parts[:-1],
            updated,
            _depth=_depth + 1,
        )
    else:
        grow_view_size_by(parent, "physical", dx, dy)


def apply_positions(
    site_root: Path,
    location_id: str,
    positions: dict[str, dict[str, Any]],
    *,
    session_docs: dict[Path, dict[str, Any]],
) -> list[str]:
    """Write positions ``{node_id: {x,y,w?,h?}}``. Return updated ids.

    Transient negatives are accepted then sibling groups are renormalized so
    persisted ``x``/``y`` stay ``>= 0`` (parent-local origin). Parent boxes
    expand toward N/W when content was shifted.
    """
    yaml_path, site_doc = _load_site_doc(site_root, session_docs=session_docs)
    session_docs[yaml_path] = site_doc
    canvas_parts = logical_parts_from_id(location_id)
    updated: list[str] = []
    parents: set[tuple[str, ...]] = set()
    for node_id, pos in positions.items():
        parts = tuple(p for p in str(node_id).split("/") if p)
        if not parts:
            continue
        try:
            place = get_place_node(site_doc, canvas_parts + parts)
        except ValueError as exc:
            raise FileNotFoundError(f"Unknown node: {node_id}") from exc
        set_physical_position(
            place, float(pos["x"]), float(pos["y"]), allow_negative=True
        )
        if "w" in pos and "h" in pos:
            set_physical_size(place, float(pos["w"]), float(pos["h"]))
        if place_paints_iso(place):
            set_physical_bounds(place, BOUNDS_SPRITE)
        updated.append(str(node_id))
        parents.add(tuple(canvas_parts) + parts[:-1])

    for parent_parts in sorted(parents, key=len, reverse=True):
        _absorb_place_children_origin(
            site_doc, canvas_parts, parent_parts, updated
        )
    return updated


def apply_electrical_positions(
    site_root: Path,
    location_id: str,
    positions: dict[str, dict[str, Any]],
    *,
    session_docs: dict[Path, dict[str, Any]],
) -> list[str]:
    """Write ``view.electrical`` for ``{place/element: {x,y,w?,h?}}``. Return ids.

    Transient negatives are renormalized among sibling elements under each host;
    the host box expands toward N/W when needed.
    """
    yaml_path, site_doc = _load_site_doc(site_root, session_docs=session_docs)
    session_docs[yaml_path] = site_doc
    canvas_parts = logical_parts_from_id(location_id)
    updated: list[str] = []
    hosts: set[tuple[str, ...]] = set()
    for node_id, pos in positions.items():
        place_parts, element_name = split_element_node_id(str(node_id))
        host = get_place_node(site_doc, canvas_parts + place_parts)
        elements = host.get("elements")
        if not isinstance(elements, dict) or element_name not in elements:
            raise FileNotFoundError(f"Unknown element: {node_id}")
        elem = elements[element_name]
        if not isinstance(elem, dict):
            raise ValueError(f"Element {node_id} is not a map")
        set_electrical_position(
            elem, float(pos["x"]), float(pos["y"]), allow_negative=True
        )
        if "w" in pos and "h" in pos:
            set_electrical_size(elem, float(pos["w"]), float(pos["h"]))
        updated.append(str(node_id))
        hosts.add(tuple(canvas_parts) + tuple(place_parts))

    for host_parts in hosts:
        host = get_place_node(site_doc, host_parts)
        elements = host.get("elements") or {}
        if not isinstance(elements, dict):
            continue
        siblings: list[dict[str, Any]] = []
        sibling_names: list[str] = []
        for name, entry in elements.items():
            if not isinstance(entry, dict) or is_place_type(entry.get("type")):
                continue
            siblings.append(entry)
            sibling_names.append(str(name))
        dx, dy = normalize_view_xy_siblings(siblings, layer="electrical")
        if dx or dy:
            shift_place_origin(host, dx, dy)
            rel = host_parts[len(canvas_parts) :]
            host_rel = "/".join(rel) if rel else ""
            for name in sibling_names:
                eid = f"{host_rel}/{name}" if host_rel else name
                if eid not in updated:
                    updated.append(eid)
            if host_rel and host_rel not in updated:
                updated.append(host_rel)
            if host_parts:
                _absorb_place_children_origin(
                    site_doc, canvas_parts, host_parts[:-1], updated
                )
    return updated


def apply_electrical_auto_layout(
    site_root: Path,
    location_id: str,
    *,
    session_docs: dict[Path, dict[str, Any]],
    depth: int = 1,
    force: bool = False,
    site_yaml: Path | None = None,
) -> list[str]:
    """Assign grid ``view.electrical`` when missing (or all if force)."""
    graph = build_physical_graph(
        site_root,
        location_id,
        depth=depth,
        session_docs=session_docs,
        site_yaml=site_yaml,
    )
    yaml_path, site_doc = _load_site_doc(
        site_root, session_docs=session_docs, site_yaml=site_yaml
    )
    session_docs[yaml_path] = site_doc
    canvas_parts = logical_parts_from_id(location_id)
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for elem in graph.get("elements") or []:
        by_parent.setdefault(elem.get("parent"), []).append(elem)

    updated: list[str] = []
    for siblings in by_parent.values():
        index = 0
        for elem in siblings:
            place_parts = tuple(elem.get("place_parts") or [])
            element_name = str(elem.get("leaf_id") or elem.get("name") or "")
            host = get_place_node(site_doc, canvas_parts + place_parts)
            elements = host.get("elements")
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
            if force:
                clear_electrical_size(defn)
            updated.append(str(elem["id"]))
            index += 1
    return updated
