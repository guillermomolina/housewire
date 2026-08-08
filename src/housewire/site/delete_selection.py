"""Cascade-delete places/elements from a house/v2 document.

Internal links are removed. Links that cross the deletion boundary are severed
into open runs and relocated next to the surviving endpoint. Conduits that lose
an endpoint are deleted (from/to are required).
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
from housewire.house.links import connection_type
from housewire.site.open_runs import format_open_notes, next_open_cable_name
from housewire.site.tree import get_place_node, iter_places, logical_parts_from_id

_EXPAND_LIST_RE = re.compile(
    r"^(?P<head>.*?)\[(?P<body>[^\]]*)\]\s*$",
)


@dataclass
class DeleteResult:
    deleted: list[str] = field(default_factory=list)
    severed: list[str] = field(default_factory=list)
    relocated: list[str] = field(default_factory=list)
    deleted_places: set[tuple[str, ...]] = field(default_factory=set)


def _split_element_terminal(ref: str) -> tuple[str, str]:
    if "." not in ref:
        raise ValueError(f"Invalid terminal reference (missing '.'): {ref}")
    element, terminal = ref.rsplit(".", 1)
    if not element or not terminal:
        raise ValueError(f"Invalid terminal reference: {ref}")
    return element, terminal


def _expand_endpoint_token(token: str) -> list[str]:
    token = token.strip()
    match = _EXPAND_LIST_RE.match(token)
    if not match:
        return [token]
    head = match.group("head")
    body = match.group("body")
    items = [item.strip() for item in body.split(",") if item.strip()]
    if not items:
        raise ValueError(f"Empty list in endpoint: {token}")
    if head.endswith(".") or head.endswith("/"):
        return [f"{head}{item}" for item in items]
    if head:
        return [f"{head}{item}" for item in items]
    return items


def _parse_element_path(
    raw_name: str, *, current_location: list[str]
) -> tuple[list[str], str]:
    name = raw_name.strip()
    if not name:
        raise ValueError("Empty element reference")
    parts_probe = [part for part in name.replace("\\", "/").split("/") if part]
    if ".." in parts_probe or name.startswith("../") or name == "..":
        raise ValueError(f"Reference outside this location: {raw_name}")
    if name.startswith("/"):
        parts = [part for part in name.strip("/").split("/") if part]
        if not parts:
            raise ValueError(f"Invalid absolute reference: {raw_name}")
        return parts[:-1], parts[-1]
    if name.startswith("./"):
        name = name[2:]
    if "/" in name:
        parts = [part for part in name.split("/") if part]
        if len(parts) < 2:
            raise ValueError(f"Invalid relative reference: {raw_name}")
        return list(current_location) + parts[:-1], parts[-1]
    return list(current_location), name


def _resolve_terminal_element(
    endpoint: str | None, *, owner_parts: tuple[str, ...]
) -> tuple[str, ...] | None:
    if endpoint is None or not str(endpoint).strip():
        return None
    try:
        tokens = _expand_endpoint_token(str(endpoint))
        if not tokens:
            return None
        elem_ref, _terminal = _split_element_terminal(tokens[0])
        loc_parts, elem_name = _parse_element_path(
            elem_ref, current_location=list(owner_parts)
        )
    except ValueError:
        return None
    return tuple([*loc_parts, elem_name])


def _known_place_paths(doc: dict[str, Any]) -> set[tuple[str, ...]]:
    known: set[tuple[str, ...]] = {()}
    for parts, _node in iter_places(doc):
        known.add(parts)
    return known


def _id_of(parts: tuple[str, ...]) -> str:
    return "/".join(parts) if parts else "."


def _place_deleted(
    parts: tuple[str, ...], *, deleted_places: set[tuple[str, ...]]
) -> bool:
    for i in range(len(parts) + 1):
        if parts[:i] in deleted_places:
            return True
    return False


def _element_deleted(
    elem_path: tuple[str, ...],
    *,
    deleted_places: set[tuple[str, ...]],
    deleted_elements: set[tuple[str, ...]],
) -> bool:
    if elem_path in deleted_elements:
        return True
    if len(elem_path) < 1:
        return False
    return _place_deleted(elem_path[:-1], deleted_places=deleted_places)


def _expand_deletion_sets(
    doc: dict[str, Any], ids: list[str]
) -> tuple[set[tuple[str, ...]], set[tuple[str, ...]], list[str], list[str]]:
    deleted_places: set[tuple[str, ...]] = set()
    deleted_elements: set[tuple[str, ...]] = set()
    deleted_cables: list[str] = []
    deleted_ids: list[str] = []

    from housewire.site.cable_actions import find_cable_owner

    for raw in ids:
        text = str(raw).strip()
        if not text:
            continue
        parts = logical_parts_from_id(text)
        if not parts:
            raise ValueError("Cannot delete the site root")

        try:
            get_place_node(doc, parts)
            is_place = True
        except ValueError:
            is_place = False

        if is_place:
            if parts in deleted_places:
                continue
            deleted_places.add(parts)
            deleted_ids.append(_id_of(parts))
            for rel, _child in iter_places(doc, under=parts):
                full = tuple([*parts, *rel])
                if full not in deleted_places:
                    deleted_places.add(full)
                    deleted_ids.append(_id_of(full))
            continue

        parent, name = parts[:-1], parts[-1]
        try:
            parent_node = get_place_node(doc, parent)
        except ValueError:
            parent_node = None
        elements = (
            parent_node.get("elements") or {}
            if isinstance(parent_node, dict)
            else {}
        )
        if isinstance(elements, dict) and name in elements and isinstance(
            elements.get(name), dict
        ):
            child = elements[name]
            if is_place_type(child.get("type")):
                deleted_places.add(parts)
                deleted_ids.append(_id_of(parts))
                for rel, _child in iter_places(doc, under=parts):
                    full = tuple([*parts, *rel])
                    deleted_places.add(full)
                    deleted_ids.append(_id_of(full))
            elif parts not in deleted_elements:
                deleted_elements.add(parts)
                deleted_ids.append(_id_of(parts))
            continue

        try:
            find_cable_owner(doc, text)
        except ValueError as exc:
            raise ValueError(f"Unknown id: {text}") from exc
        if text not in deleted_cables:
            deleted_cables.append(text)
            deleted_ids.append(text)

    deleted_elements = {
        e
        for e in deleted_elements
        if not _place_deleted(e[:-1], deleted_places=deleted_places)
    }
    return deleted_places, deleted_elements, deleted_ids, deleted_cables


def _iter_cable_owners(
    doc: dict[str, Any],
) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    rows: list[tuple[tuple[str, ...], dict[str, Any]]] = [((), doc)]
    for parts, node in iter_places(doc):
        rows.append((parts, node))
    return rows


def _node_at(doc: dict[str, Any], parts: tuple[str, ...]) -> dict[str, Any]:
    return get_place_node(doc, parts) if parts else doc


def _ensure_cables_map(node: dict[str, Any]) -> dict[str, Any]:
    cables = node.get("cables")
    if not isinstance(cables, dict):
        cables = {}
        node["cables"] = cables
    return cables


def _unique_name(cables: dict[str, Any], preferred: str) -> str:
    if preferred not in cables:
        return preferred
    open_name = next_open_cable_name({"cables": cables})
    if preferred.startswith("OPEN_"):
        return open_name
    n = 2
    while f"{preferred}_{n}" in cables:
        n += 1
    candidate = f"{preferred}_{n}"
    return candidate if candidate not in cables else open_name


def _mark_conductor_open(entry: dict[str, Any], *, clear_from: bool) -> None:
    if clear_from:
        entry.pop("from", None)
    else:
        entry.pop("to", None)
    extra = str(entry.get("notes") or "").strip()
    entry["notes"] = format_open_notes(status="open", extra=extra or None)


def _find_parent_cable(
    cables: dict[str, Any], child: str, *, catalog: dict[str, Any]
) -> str | None:
    for other, entry in cables.items():
        if not isinstance(entry, dict) or other == child:
            continue
        try:
            if connection_type(entry) != "Cable":
                continue
        except ValueError:
            continue
        if child in [str(c) for c in (entry.get("contains") or [])]:
            return str(other)
    return None


def delete_selection(doc: dict[str, Any], ids: list[str]) -> DeleteResult:
    """Mutate ``doc`` in place. Returns a summary for the UI."""
    if not ids:
        raise ValueError("ids must not be empty")

    catalog = load_catalog()
    deleted_places, deleted_elements, deleted_ids, deleted_cables = (
        _expand_deletion_sets(doc, ids)
    )
    if not deleted_places and not deleted_elements and not deleted_cables:
        raise ValueError("Nothing to delete")

    # Pure cable deletions (no place/element cascade).
    if deleted_cables and not deleted_places and not deleted_elements:
        from housewire.site.cable_actions import delete_cables

        delete_cables(doc, deleted_cables)
        return DeleteResult(deleted=list(deleted_ids), deleted_places=set())

    known = _known_place_paths(doc)
    result = DeleteResult(
        deleted=list(deleted_ids), deleted_places=set(deleted_places)
    )

    if deleted_cables:
        from housewire.site.cable_actions import delete_cables

        delete_cables(doc, deleted_cables)

    delete_keys: set[tuple[tuple[str, ...], str]] = set()
    # (owner, conductor_name, survivor_element_path, clear_from)
    severs: list[tuple[tuple[str, ...], str, tuple[str, ...], bool]] = []

    for owner_parts, node in _iter_cable_owners(doc):
        cables = node.get("cables") or {}
        if not isinstance(cables, dict):
            continue
        for name, entry in list(cables.items()):
            if not isinstance(entry, dict):
                continue
            try:
                type_id = connection_type(entry)
            except ValueError:
                continue
            key = (owner_parts, str(name))

            if type_id == "Conduit":
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
                    delete_keys.add(key)
                    continue
                if _place_deleted(
                    from_parts, deleted_places=deleted_places
                ) or _place_deleted(to_parts, deleted_places=deleted_places):
                    delete_keys.add(key)
                continue

            if type_id != "Conductor":
                continue

            from_el = _resolve_terminal_element(
                entry.get("from"), owner_parts=owner_parts
            )
            to_el = _resolve_terminal_element(
                entry.get("to"), owner_parts=owner_parts
            )
            from_gone = from_el is not None and _element_deleted(
                from_el,
                deleted_places=deleted_places,
                deleted_elements=deleted_elements,
            )
            to_gone = to_el is not None and _element_deleted(
                to_el,
                deleted_places=deleted_places,
                deleted_elements=deleted_elements,
            )
            owner_gone = _place_deleted(owner_parts, deleted_places=deleted_places)

            if from_gone and to_gone:
                delete_keys.add(key)
            elif from_gone and to_el is not None and not to_gone:
                severs.append((owner_parts, str(name), to_el, True))
            elif to_gone and from_el is not None and not from_gone:
                severs.append((owner_parts, str(name), from_el, False))
            elif owner_gone:
                if from_el is not None and not from_gone:
                    severs.append((owner_parts, str(name), from_el, False))
                elif to_el is not None and not to_gone:
                    severs.append((owner_parts, str(name), to_el, True))
                else:
                    delete_keys.add(key)

    # Mark cables that only contain deleted members.
    for owner_parts, node in _iter_cable_owners(doc):
        cables = node.get("cables") or {}
        if not isinstance(cables, dict):
            continue
        sever_names = {n for o, n, *_ in severs if o == owner_parts}
        changed = True
        while changed:
            changed = False
            for name, entry in list(cables.items()):
                if not isinstance(entry, dict):
                    continue
                try:
                    if connection_type(entry) != "Cable":
                        continue
                except ValueError:
                    continue
                key = (owner_parts, str(name))
                if key in delete_keys:
                    continue
                contains = [str(c) for c in (entry.get("contains") or [])]
                if not contains:
                    delete_keys.add(key)
                    changed = True
                    continue
                if all(
                    (owner_parts, c) in delete_keys and c not in sever_names
                    for c in contains
                ):
                    delete_keys.add(key)
                    changed = True

    # Apply severs: relocate (owner→survivor place) when needed, mark open.
    handled: set[tuple[tuple[str, ...], str]] = set()
    for owner_parts, cond_name, survivor_el, clear_from in severs:
        if (owner_parts, cond_name) in handled:
            continue
        src_node = _node_at(doc, owner_parts)
        src_cables = _ensure_cables_map(src_node)
        if cond_name not in src_cables:
            continue

        parent = _find_parent_cable(src_cables, cond_name, catalog=catalog)
        # Move cable + surviving children, or just the conductor.
        if parent and (owner_parts, parent) not in delete_keys:
            group = [parent]
            for child in (src_cables.get(parent) or {}).get("contains") or []:
                child_s = str(child)
                if (owner_parts, child_s) in delete_keys:
                    continue
                group.append(child_s)
        else:
            group = [cond_name]

        dest_place = survivor_el[:-1]
        dest_node = _node_at(doc, dest_place)
        dest_cables = _ensure_cables_map(dest_node)
        same_map = dest_place == owner_parts

        rename: dict[str, str] = {}
        for old in group:
            if old not in src_cables:
                continue
            if same_map:
                rename[old] = old
            else:
                rename[old] = _unique_name(dest_cables, old)

        # Snapshot then write.
        snapshots = {
            old: copy.deepcopy(src_cables[old])
            for old in group
            if old in src_cables
        }

        for old, blob in snapshots.items():
            new = rename[old]
            try:
                type_id = connection_type(blob)
            except ValueError:
                type_id = ""
            if type_id == "Conductor":
                # Apply sever if this conductor is in the sever list for this dest.
                for o, n, surv, cf in severs:
                    if o == owner_parts and n == old and surv == survivor_el:
                        _mark_conductor_open(blob, clear_from=cf)
                        result.severed.append(new)
                        break
                else:
                    # Sibling under same cable may sever to same or other dest;
                    # apply any sever for this conductor name.
                    for o, n, surv, cf in severs:
                        if o == owner_parts and n == old:
                            _mark_conductor_open(blob, clear_from=cf)
                            result.severed.append(new)
                            break
            elif type_id == "Cable":
                blob["contains"] = [
                    rename[str(c)]
                    for c in (blob.get("contains") or [])
                    if str(c) in rename
                ]

            if same_map:
                src_cables[old] = blob
            else:
                dest_cables[new] = blob
                result.relocated.append(new if new == old else f"{old}->{new}")

        if not same_map:
            for old in group:
                if old in src_cables:
                    del src_cables[old]
                handled.add((owner_parts, old))
        else:
            for old in group:
                handled.add((owner_parts, old))

    # Drop marked keys from surviving owners.
    for owner_parts, node in _iter_cable_owners(doc):
        if _place_deleted(owner_parts, deleted_places=deleted_places):
            continue
        cables = node.get("cables")
        if not isinstance(cables, dict):
            continue
        for name in list(cables.keys()):
            if (owner_parts, str(name)) in delete_keys:
                del cables[name]

        again = True
        while again:
            again = False
            for name, entry in list(cables.items()):
                if not isinstance(entry, dict):
                    continue
                try:
                    type_id = connection_type(entry)
                except ValueError:
                    continue
                if type_id not in ("Cable", "Conduit"):
                    continue
                contains = [str(c) for c in (entry.get("contains") or [])]
                filtered = [c for c in contains if c in cables]
                if filtered != contains:
                    entry["contains"] = filtered
                    again = True
                if not filtered:
                    del cables[name]
                    again = True

    # Remove places (deepest first) and leftover elements.
    for place_parts in sorted(deleted_places, key=lambda p: len(p), reverse=True):
        if not place_parts:
            continue
        parent_parts, leaf = place_parts[:-1], place_parts[-1]
        try:
            parent = _node_at(doc, parent_parts)
        except ValueError:
            continue
        elements = parent.get("elements")
        if isinstance(elements, dict) and leaf in elements:
            del elements[leaf]

    for elem_path in list(deleted_elements):
        parent_parts, leaf = elem_path[:-1], elem_path[-1]
        if _place_deleted(parent_parts, deleted_places=deleted_places):
            continue
        try:
            parent = _node_at(doc, parent_parts)
        except ValueError:
            continue
        elements = parent.get("elements")
        if isinstance(elements, dict) and leaf in elements:
            del elements[leaf]

    return result


def suggest_location_after_delete(
    current_location_id: str, *, deleted_places: set[tuple[str, ...]]
) -> str:
    """Climb to the nearest surviving ancestor when the canvas location was removed."""
    cur = logical_parts_from_id(current_location_id)
    if not _place_deleted(cur, deleted_places=deleted_places):
        return current_location_id if str(current_location_id).strip() else "."
    while cur:
        cur = cur[:-1]
        if not _place_deleted(cur, deleted_places=deleted_places):
            return _id_of(cur)
    return "."
