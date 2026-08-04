"""Pack / paste selection for Cut-Copy-Paste (aligned with delete_selection).

Internal links are copied intact. Cross-boundary conductors become open-run
stubs on the selected side. Conduits that lose an endpoint are omitted.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any

from housewire.house import is_place_type, load_catalog
from housewire.house.conduit_ref import (
    conduit_endpoints,
    resolve_location_ref,
    split_conduit_endpoint,
)
from housewire.house.links import resolve_link_kind
from housewire.site.delete_selection import (
    _element_deleted,
    _expand_deletion_sets,
    _iter_cable_owners,
    _known_place_paths,
    _mark_conductor_open,
    _node_at,
    _parse_element_path,
    _place_deleted,
    _resolve_terminal_element,
    _unique_name,
)
from housewire.site.open_runs import format_open_notes
from housewire.site.tree import logical_parts_from_id
from housewire.site.view_layout import (
    get_electrical_position,
    get_electrical_size,
    get_physical_position,
    get_physical_size,
    set_electrical_position,
    set_physical_position,
    set_physical_size,
)

_TRAILING_NUM = re.compile(r"^(.*?)(\d+)$")
# Match nested canvas layout in physical_graph / app.js.
_LEAF_W = 120.0
_LEAF_H = 56.0
_ELEM_W = 72.0
_ELEM_H = 28.0
_GAP = 16.0
_STEP_X = 160.0
_STEP_Y = 110.0
_ELEM_STEP_X = 80.0
_ELEM_STEP_Y = 36.0
_CONTENT_PAD = 28.0
_CONTENT_HEADER = 36.0
_ORIGIN_X = 28.0
_ORIGIN_Y = 40.0
_ELEM_ORIGIN_X = 28.0
_ELEM_ORIGIN_Y = 8.0
CLIPBOARD_VERSION = 1


@dataclass
class PasteResult:
    created: list[str] = field(default_factory=list)
    renamed: dict[str, str] = field(default_factory=dict)


def next_available_id(existing: set[str] | dict[str, Any], preferred: str) -> str:
    """Unique sibling id: Interruptor→Interruptor_1, Interruptor_1→Interruptor_2."""
    taken = (
        {str(k) for k in existing.keys()}
        if isinstance(existing, dict)
        else {str(x) for x in existing}
    )
    name = str(preferred).strip() or "Item"
    if name not in taken:
        return name
    match = _TRAILING_NUM.match(name)
    if match:
        stem = match.group(1)
        n = int(match.group(2)) + 1
        while f"{stem}{n}" in taken:
            n += 1
        return f"{stem}{n}"
    n = 1
    while f"{name}_{n}" in taken:
        n += 1
    return f"{name}_{n}"


def _roots(
    deleted_places: set[tuple[str, ...]], deleted_elements: set[tuple[str, ...]]
) -> tuple[list[tuple[str, ...]], list[tuple[str, ...]]]:
    place_roots = [
        p
        for p in sorted(deleted_places, key=lambda x: (len(x), x))
        if not any(p[:i] in deleted_places for i in range(1, len(p)))
    ]
    elem_roots = [
        e
        for e in sorted(deleted_elements, key=lambda x: (len(x), x))
        if not _place_deleted(e[:-1], deleted_places=deleted_places)
    ]
    return place_roots, elem_roots


def _walk_place_nodes(
    node: dict[str, Any], parts: tuple[str, ...]
) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    rows: list[tuple[tuple[str, ...], dict[str, Any]]] = [(parts, node)]
    elements = node.get("elements") or {}
    if not isinstance(elements, dict):
        return rows
    for name, child in elements.items():
        if isinstance(child, dict) and is_place_type(child.get("type")):
            rows.extend(_walk_place_nodes(child, (*parts, str(name))))
    return rows


def _scrub_cables_in_node(
    node: dict[str, Any],
    *,
    owner_parts: tuple[str, ...],
    selected_places: set[tuple[str, ...]],
    selected_elements: set[tuple[str, ...]],
    catalog: dict[str, Any],
    known: set[tuple[str, ...]],
) -> None:
    cables = node.get("cables")
    if not isinstance(cables, dict):
        return
    drop: set[str] = set()
    for name, entry in list(cables.items()):
        if not isinstance(entry, dict):
            continue
        try:
            kind = resolve_link_kind(entry, catalog)
        except ValueError:
            continue
        if kind == "conduit":
            try:
                from_ref, to_ref = conduit_endpoints(entry)
                from_loc, _a = split_conduit_endpoint(from_ref)
                to_loc, _b = split_conduit_endpoint(to_ref)
                from_parts = resolve_location_ref(
                    from_loc, current_parts=list(owner_parts), known=known
                )
                to_parts = resolve_location_ref(
                    to_loc, current_parts=list(owner_parts), known=known
                )
            except ValueError:
                drop.add(str(name))
                continue
            if _place_deleted(
                from_parts, deleted_places=selected_places
            ) and _place_deleted(to_parts, deleted_places=selected_places):
                continue
            drop.add(str(name))
            continue
        if kind != "conductor":
            continue
        from_el = _resolve_terminal_element(entry.get("from"), owner_parts=owner_parts)
        to_el = _resolve_terminal_element(entry.get("to"), owner_parts=owner_parts)
        from_in = from_el is not None and _element_deleted(
            from_el,
            deleted_places=selected_places,
            deleted_elements=selected_elements,
        )
        to_in = to_el is not None and _element_deleted(
            to_el,
            deleted_places=selected_places,
            deleted_elements=selected_elements,
        )
        if from_in and to_in:
            continue
        if from_in and not to_in:
            _mark_conductor_open(entry, clear_from=False)
        elif to_in and not from_in:
            _mark_conductor_open(entry, clear_from=True)
        else:
            drop.add(str(name))

    for name in drop:
        cables.pop(name, None)

    again = True
    while again:
        again = False
        for name, entry in list(cables.items()):
            if not isinstance(entry, dict):
                continue
            try:
                kind = resolve_link_kind(entry, catalog)
            except ValueError:
                continue
            if kind not in ("cable", "conduit"):
                continue
            contains = [str(c) for c in (entry.get("contains") or [])]
            filtered = [c for c in contains if c in cables]
            if filtered != contains:
                entry["contains"] = filtered
                again = True
            if not filtered:
                del cables[name]
                again = True


def _terminal_suffix(endpoint: str | None) -> str | None:
    if endpoint is None or not str(endpoint).strip() or "." not in str(endpoint):
        return None
    return str(endpoint).rsplit(".", 1)[-1]


def _rel_elem_ref(
    elem_path: tuple[str, ...],
    *,
    place_roots: list[tuple[str, ...]],
    terminal: str,
) -> tuple[tuple[str, ...] | None, str]:
    for root in sorted(place_roots, key=len, reverse=True):
        if len(elem_path) >= len(root) and elem_path[: len(root)] == root:
            rel = elem_path[len(root) :]
            body = "/".join(rel) if rel else elem_path[-1]
            return root, f"{body}.{terminal}"
    return None, f"{elem_path[-1]}.{terminal}"


def _find_place_item(
    items: list[dict[str, Any]], path_prefix: tuple[str, ...]
) -> dict[str, Any] | None:
    for item in items:
        if item.get("kind") == "place" and tuple(item.get("path") or []) == path_prefix:
            return item
    return None


def _ensure_cables(node: dict[str, Any]) -> dict[str, Any]:
    cables = node.get("cables")
    if not isinstance(cables, dict):
        cables = {}
        node["cables"] = cables
    return cables


def _attach_open_stub(
    cables: dict[str, Any],
    *,
    preferred_name: str,
    template: dict[str, Any],
    clear_from: bool,
    local_ref: str,
) -> None:
    name = _unique_name(cables, preferred_name)
    blob = copy.deepcopy(template)
    blob["type"] = blob.get("type") or "Conductor"
    if clear_from:
        blob.pop("from", None)
        blob["to"] = local_ref
    else:
        blob.pop("to", None)
        blob["from"] = local_ref
    extra = str(blob.get("notes") or "").strip()
    blob["notes"] = format_open_notes(status="open", extra=extra or None)
    cables[name] = blob


def _rewrite_endpoint_for_pack(
    endpoint: str,
    *,
    owner_parts: tuple[str, ...],
    place_roots: list[tuple[str, ...]],
    elem_roots: list[tuple[str, ...]],
) -> str:
    if "." not in endpoint or "[" in endpoint:
        return endpoint
    elem_ref, terminal = endpoint.rsplit(".", 1)
    try:
        loc_parts, elem_name = _parse_element_path(
            elem_ref, current_location=list(owner_parts)
        )
    except ValueError:
        return endpoint
    elem_path = tuple([*loc_parts, elem_name])
    for root in sorted(place_roots, key=len, reverse=True):
        if elem_path[: len(root)] == root:
            rel = (root[-1], *elem_path[len(root) :])
            return f"{'/'.join(rel)}.{terminal}"
    if elem_path in elem_roots:
        return f"{elem_path[-1]}.{terminal}"
    return endpoint


def _rewrite_conduit_for_pack(
    ref: str,
    *,
    owner_parts: tuple[str, ...],
    place_roots: list[tuple[str, ...]],
    known: set[tuple[str, ...]],
) -> str | None:
    try:
        loc, opening = split_conduit_endpoint(ref)
        parts = resolve_location_ref(loc, current_parts=list(owner_parts), known=known)
    except ValueError:
        return None
    for root in sorted(place_roots, key=len, reverse=True):
        if parts == root or parts[: len(root)] == root:
            rel = (root[-1], *parts[len(root) :])
            return f"{'/'.join(rel)}.{opening}"
    return None


def pack_selection(doc: dict[str, Any], ids: list[str]) -> dict[str, Any]:
    """Build a JSON-serializable clipboard payload (does not mutate ``doc``)."""
    if not ids:
        raise ValueError("ids must not be empty")
    catalog = load_catalog()
    selected_places, selected_elements, _ = _expand_deletion_sets(doc, ids)
    if not selected_places and not selected_elements:
        raise ValueError("Nothing to copy")
    known = _known_place_paths(doc)
    place_roots, elem_roots = _roots(selected_places, selected_elements)

    items: list[dict[str, Any]] = []
    for root in place_roots:
        node = copy.deepcopy(_node_at(doc, root))
        for parts, sub in _walk_place_nodes(node, root):
            _scrub_cables_in_node(
                sub,
                owner_parts=parts,
                selected_places=selected_places,
                selected_elements=selected_elements,
                catalog=catalog,
                known=known,
            )
        items.append({"kind": "place", "id": root[-1], "node": node, "path": list(root)})

    for root in elem_roots:
        parent = _node_at(doc, root[:-1])
        elements = parent.get("elements") or {}
        blob = elements.get(root[-1])
        if isinstance(blob, dict):
            items.append(
                {
                    "kind": "element",
                    "id": root[-1],
                    "node": copy.deepcopy(blob),
                    "path": list(root),
                }
            )

    parent_cables: dict[str, Any] = {}

    for owner_parts, node in _iter_cable_owners(doc):
        if _place_deleted(owner_parts, deleted_places=selected_places):
            continue
        cables = node.get("cables") or {}
        if not isinstance(cables, dict):
            continue

        include: set[str] = set()
        for name, entry in list(cables.items()):
            if not isinstance(entry, dict):
                continue
            try:
                kind = resolve_link_kind(entry, catalog)
            except ValueError:
                continue
            if kind == "conduit":
                try:
                    from_ref, to_ref = conduit_endpoints(entry)
                    from_loc, _a = split_conduit_endpoint(from_ref)
                    to_loc, _b = split_conduit_endpoint(to_ref)
                    from_p = resolve_location_ref(
                        from_loc, current_parts=list(owner_parts), known=known
                    )
                    to_p = resolve_location_ref(
                        to_loc, current_parts=list(owner_parts), known=known
                    )
                except ValueError:
                    continue
                if _place_deleted(
                    from_p, deleted_places=selected_places
                ) and _place_deleted(to_p, deleted_places=selected_places):
                    include.add(str(name))
                continue
            if kind != "conductor":
                continue
            from_el = _resolve_terminal_element(
                entry.get("from"), owner_parts=owner_parts
            )
            to_el = _resolve_terminal_element(entry.get("to"), owner_parts=owner_parts)
            from_in = from_el is not None and _element_deleted(
                from_el,
                deleted_places=selected_places,
                deleted_elements=selected_elements,
            )
            to_in = to_el is not None and _element_deleted(
                to_el,
                deleted_places=selected_places,
                deleted_elements=selected_elements,
            )
            if from_in and to_in:
                include.add(str(name))
            elif from_in and from_el is not None:
                term = _terminal_suffix(entry.get("from")) or "N1"
                place_root, local_ref = _rel_elem_ref(
                    from_el, place_roots=place_roots, terminal=term
                )
                target = (
                    _find_place_item(items, place_root) if place_root is not None else None
                )
                dest = _ensure_cables(target["node"]) if target else parent_cables
                _attach_open_stub(
                    dest,
                    preferred_name=str(name),
                    template=entry,
                    clear_from=False,
                    local_ref=local_ref,
                )
            elif to_in and to_el is not None:
                term = _terminal_suffix(entry.get("to")) or "N1"
                place_root, local_ref = _rel_elem_ref(
                    to_el, place_roots=place_roots, terminal=term
                )
                target = (
                    _find_place_item(items, place_root) if place_root is not None else None
                )
                dest = _ensure_cables(target["node"]) if target else parent_cables
                _attach_open_stub(
                    dest,
                    preferred_name=str(name),
                    template=entry,
                    clear_from=True,
                    local_ref=local_ref,
                )

        for name, entry in list(cables.items()):
            if not isinstance(entry, dict) or str(name) in include:
                continue
            try:
                if resolve_link_kind(entry, catalog) != "cable":
                    continue
            except ValueError:
                continue
            contains = [str(c) for c in (entry.get("contains") or [])]
            if any(c in include for c in contains):
                include.add(str(name))

        rename: dict[str, str] = {}
        for name in include:
            entry = cables.get(name)
            if not isinstance(entry, dict):
                continue
            new_name = _unique_name(parent_cables, str(name))
            rename[str(name)] = new_name
            parent_cables[new_name] = copy.deepcopy(entry)

        for _old, new_name in rename.items():
            entry = parent_cables.get(new_name)
            if not isinstance(entry, dict):
                continue
            try:
                kind = resolve_link_kind(entry, catalog)
            except ValueError:
                continue
            if kind == "cable":
                entry["contains"] = [
                    rename[str(c)]
                    for c in (entry.get("contains") or [])
                    if str(c) in rename
                ]
            elif kind == "conductor":
                for key in ("from", "to"):
                    raw = entry.get(key)
                    if raw is None or not str(raw).strip():
                        continue
                    entry[key] = _rewrite_endpoint_for_pack(
                        str(raw),
                        owner_parts=owner_parts,
                        place_roots=place_roots,
                        elem_roots=elem_roots,
                    )
            elif kind == "conduit":
                for key in ("from", "to"):
                    raw = entry.get(key)
                    if raw is None:
                        continue
                    rewritten = _rewrite_conduit_for_pack(
                        str(raw),
                        owner_parts=owner_parts,
                        place_roots=place_roots,
                        known=known,
                    )
                    if rewritten is not None:
                        entry[key] = rewritten

    return {
        "version": CLIPBOARD_VERSION,
        "items": items,
        "parent_cables": parent_cables,
    }


def _rewrite_endpoint_on_paste(
    endpoint: str | None,
    *,
    owner_parts: tuple[str, ...],
    root_rename: dict[str, str],
) -> str | None:
    if endpoint is None or not str(endpoint).strip():
        return endpoint
    text = str(endpoint).strip()
    if "." not in text or "[" in text:
        return text
    elem_ref, terminal = text.rsplit(".", 1)
    try:
        loc_parts, elem_name = _parse_element_path(
            elem_ref, current_location=list(owner_parts)
        )
    except ValueError:
        return text
    path = [*loc_parts, elem_name]
    if path and path[0] in root_rename:
        path[0] = root_rename[path[0]]
    if owner_parts and path[: len(owner_parts)] == list(owner_parts):
        body = "/".join(path[len(owner_parts) :])
    else:
        body = "/".join(path)
    return f"{body}.{terminal}"


def _rewrite_conduit_on_paste(
    ref: str | None, *, root_rename: dict[str, str]
) -> str | None:
    if ref is None or not str(ref).strip():
        return ref
    try:
        loc, opening = split_conduit_endpoint(str(ref))
    except ValueError:
        return ref
    if loc in (".", "", "self"):
        return ref
    parts = [p for p in loc.split("/") if p]
    if parts and parts[0] in root_rename:
        parts[0] = root_rename[parts[0]]
    loc_s = "/".join(parts) if parts else "."
    return f"{loc_s}.{opening}" if loc_s != "." else f".{opening}"


def _merge_cables_into(
    dest: dict[str, Any],
    incoming: dict[str, Any],
    *,
    owner_parts: tuple[str, ...],
    root_rename: dict[str, str],
    catalog: dict[str, Any],
) -> None:
    rename: dict[str, str] = {}
    snapshots: dict[str, Any] = {}
    for old, entry in incoming.items():
        if not isinstance(entry, dict):
            continue
        new = _unique_name(dest, str(old))
        # Reserve name so subsequent uniques see it.
        dest[new] = None  # type: ignore[assignment]
        rename[str(old)] = new
        snapshots[new] = copy.deepcopy(entry)

    for new, entry in snapshots.items():
        try:
            kind = resolve_link_kind(entry, catalog)
        except ValueError:
            kind = ""
        if kind == "cable":
            entry["contains"] = [
                rename[str(c)]
                for c in (entry.get("contains") or [])
                if str(c) in rename
            ]
        elif kind == "conductor":
            for key in ("from", "to"):
                entry[key] = _rewrite_endpoint_on_paste(
                    entry.get(key), owner_parts=owner_parts, root_rename=root_rename
                )
        elif kind == "conduit":
            for key in ("from", "to"):
                entry[key] = _rewrite_conduit_on_paste(
                    entry.get(key), root_rename=root_rename
                )
        dest[new] = entry


def _box_size(
    node: dict[str, Any], *, default_w: float, default_h: float, electrical: bool
) -> tuple[float, float]:
    size = get_electrical_size(node) if electrical else get_physical_size(node)
    if size is not None:
        return float(size[0]), float(size[1])
    return default_w, default_h


def _rects_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    *,
    gap: float = _GAP,
) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (
        ax + aw + gap <= bx
        or bx + bw + gap <= ax
        or ay + ah + gap <= by
        or by + bh + gap <= ay
    )


def _candidate_positions(
    preferred: tuple[float, float] | None,
    *,
    step_x: float,
    step_y: float,
    origin_x: float,
    origin_y: float,
) -> list[tuple[float, float]]:
    """Preferred point first, then a compact spiral / grid of alternatives."""
    out: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()

    def _add(x: float, y: float) -> None:
        key = (round(x, 1), round(y, 1))
        if key in seen or x < 0 or y < 0:
            return
        seen.add(key)
        out.append((x, y))

    if preferred is not None:
        _add(preferred[0], preferred[1])
    _add(origin_x, origin_y)
    # Expanding rings around preferred (or origin).
    base_x = preferred[0] if preferred is not None else origin_x
    base_y = preferred[1] if preferred is not None else origin_y
    for ring in range(1, 12):
        for dx in range(-ring, ring + 1):
            for dy in range(-ring, ring + 1):
                if max(abs(dx), abs(dy)) != ring:
                    continue
                _add(base_x + dx * step_x, base_y + dy * step_y)
    # Extra row/column scan from origin for dense parents.
    for row in range(0, 8):
        for col in range(0, 8):
            _add(origin_x + col * step_x, origin_y + row * step_y)
    return out


def _find_free_position(
    w: float,
    h: float,
    *,
    preferred: tuple[float, float] | None,
    obstacles: list[tuple[float, float, float, float]],
    step_x: float,
    step_y: float,
    origin_x: float,
    origin_y: float,
) -> tuple[float, float]:
    for x, y in _candidate_positions(
        preferred,
        step_x=step_x,
        step_y=step_y,
        origin_x=origin_x,
        origin_y=origin_y,
    ):
        rect = (x, y, w, h)
        if any(_rects_overlap(rect, other) for other in obstacles):
            continue
        return x, y
    # Last resort: stack below the lowest obstacle.
    if obstacles:
        bottom = max(oy + oh for _ox, oy, _ow, oh in obstacles)
        return origin_x, bottom + _GAP
    return origin_x, origin_y


def _collect_place_obstacles(parent: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    obstacles: list[tuple[float, float, float, float]] = []
    elements = parent.get("elements") or {}
    if not isinstance(elements, dict):
        return obstacles
    for child in elements.values():
        if not isinstance(child, dict) or not is_place_type(child.get("type")):
            continue
        pos = get_physical_position(child)
        if pos is None:
            continue
        w, h = _box_size(child, default_w=_LEAF_W, default_h=_LEAF_H, electrical=False)
        obstacles.append((float(pos[0]), float(pos[1]), w, h))
    return obstacles


def _collect_element_obstacles(
    parent: dict[str, Any],
) -> list[tuple[float, float, float, float]]:
    obstacles: list[tuple[float, float, float, float]] = []
    elements = parent.get("elements") or {}
    if not isinstance(elements, dict):
        return obstacles
    for child in elements.values():
        if not isinstance(child, dict) or is_place_type(child.get("type")):
            continue
        pos = get_electrical_position(child)
        if pos is None:
            continue
        w, h = _box_size(child, default_w=_ELEM_W, default_h=_ELEM_H, electrical=True)
        obstacles.append((float(pos[0]), float(pos[1]), w, h))
    return obstacles


def _place_without_overlap(
    node: dict[str, Any],
    *,
    obstacles: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    w, h = _box_size(node, default_w=_LEAF_W, default_h=_LEAF_H, electrical=False)
    preferred = get_physical_position(node)
    x, y = _find_free_position(
        w,
        h,
        preferred=preferred,
        obstacles=obstacles,
        step_x=_STEP_X,
        step_y=_STEP_Y,
        origin_x=_ORIGIN_X,
        origin_y=_ORIGIN_Y,
    )
    set_physical_position(node, x, y)
    rect = (x, y, w, h)
    obstacles.append(rect)
    return rect


def _element_without_overlap(
    node: dict[str, Any],
    *,
    obstacles: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    w, h = _box_size(node, default_w=_ELEM_W, default_h=_ELEM_H, electrical=True)
    preferred = get_electrical_position(node)
    x, y = _find_free_position(
        w,
        h,
        preferred=preferred,
        obstacles=obstacles,
        step_x=_ELEM_STEP_X,
        step_y=_ELEM_STEP_Y,
        origin_x=_ELEM_ORIGIN_X,
        origin_y=_ELEM_ORIGIN_Y,
    )
    set_electrical_position(node, x, y)
    rect = (x, y, w, h)
    obstacles.append(rect)
    return rect


def _grow_parent_to_fit(
    parent: dict[str, Any],
    content_rects: list[tuple[float, float, float, float]],
) -> None:
    """If the parent has a locked size, enlarge it so pasted content fits."""
    if not content_rects:
        return
    stored = get_physical_size(parent)
    if stored is None:
        # Unlocked parents auto-size from content on the next graph build.
        return
    max_r = max(x + w for x, _y, w, _h in content_rects)
    max_b = max(y + h for _x, y, _w, h in content_rects)
    need_w = max(_LEAF_W, max_r + 2 * _CONTENT_PAD)
    need_h = max(_LEAF_H, _CONTENT_HEADER + max_b + _CONTENT_PAD)
    sw, sh = float(stored[0]), float(stored[1])
    if need_w > sw or need_h > sh:
        set_physical_size(parent, max(sw, need_w), max(sh, need_h))


def paste_payload(
    doc: dict[str, Any],
    *,
    parent_id: str,
    payload: dict[str, Any],
) -> PasteResult:
    """Insert clipboard payload under ``parent_id``. Mutates ``doc``."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        raise ValueError("clipboard is empty")
    parent_parts = logical_parts_from_id(parent_id)
    parent = _node_at(doc, parent_parts)
    elements = parent.get("elements")
    if not isinstance(elements, dict):
        elements = {}
        parent["elements"] = elements

    catalog = load_catalog()
    result = PasteResult()
    root_rename: dict[str, str] = {}
    place_obstacles = _collect_place_obstacles(parent)
    elem_obstacles = _collect_element_obstacles(parent)
    fitted_rects: list[tuple[float, float, float, float]] = list(place_obstacles)
    fitted_rects.extend(elem_obstacles)

    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        old_id = str(item.get("id") or "").strip()
        node = item.get("node")
        if not old_id or not isinstance(node, dict):
            continue
        new_id = next_available_id(elements, old_id)
        root_rename[old_id] = new_id
        result.renamed[old_id] = new_id
        blob = copy.deepcopy(node)
        if kind == "place":
            rect = _place_without_overlap(blob, obstacles=place_obstacles)
            fitted_rects.append(rect)
            elements[new_id] = blob
            created = "/".join((*parent_parts, new_id)) if parent_parts else new_id
            result.created.append(created)
        elif kind == "element":
            rect = _element_without_overlap(blob, obstacles=elem_obstacles)
            fitted_rects.append(rect)
            elements[new_id] = blob
            created = "/".join((*parent_parts, new_id)) if parent_parts else new_id
            result.created.append(created)
        else:
            raise ValueError(f"Unknown clipboard item kind: {kind}")

    _grow_parent_to_fit(parent, fitted_rects)

    parent_cables = payload.get("parent_cables") or {}
    if isinstance(parent_cables, dict) and parent_cables:
        _merge_cables_into(
            _ensure_cables(parent),
            parent_cables,
            owner_parts=parent_parts,
            root_rename=root_rename,
            catalog=catalog,
        )

    return result
