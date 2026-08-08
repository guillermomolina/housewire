"""UI/API helpers for unified ``cables:`` links (Conduit / Cable / Conductor)."""

from __future__ import annotations

from typing import Any

from housewire.house import (
    expand_cable,
    expand_conductor,
    expand_conduit,
    load_catalog,
)
from housewire.house.conduit_ref import (
    conduit_endpoints,
    format_conduit_endpoint,
    split_conduit_endpoint,
)
from housewire.house.links import resolve_link_kind
from housewire.site import abm
from housewire.site import open_runs
from housewire.site.session import SiteSession
from housewire.site.tree import get_place_node, iter_places, logical_parts_from_id


_EDITABLE_FIELDS = frozenset(
    {
        "name",
        "label",
        "notes",
        "subtype",
        "section",
        "color",
        "install",
        "from",
        "to",
        "contains",
    }
)


def _iter_owners(doc: dict[str, Any]) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    rows: list[tuple[tuple[str, ...], dict[str, Any]]] = [((), doc)]
    for parts, node in iter_places(doc):
        rows.append((parts, node))
    return rows


def find_cable_owner(
    doc: dict[str, Any], cable_name: str
) -> tuple[tuple[str, ...], dict[str, Any], dict[str, Any]]:
    """Return ``(owner_parts, owner_node, entry)`` for ``cable_name``."""
    key = str(cable_name).strip()
    if not key:
        raise ValueError("Cable id is required")
    for parts, node in _iter_owners(doc):
        cables = node.get("cables")
        if not isinstance(cables, dict):
            continue
        entry = cables.get(key)
        if isinstance(entry, dict):
            return parts, node, entry
    raise ValueError(f"Cable not found: {key}")


def _owner_for_parts(doc: dict[str, Any], parts: tuple[str, ...]) -> dict[str, Any]:
    return get_place_node(doc, parts) if parts else doc


def _ensure_cables(node: dict[str, Any]) -> dict[str, Any]:
    cables = node.get("cables")
    if not isinstance(cables, dict):
        cables = {}
        node["cables"] = cables
    return cables


def _next_unique(cables: dict[str, Any], prefix: str) -> str:
    if prefix not in cables:
        return prefix
    n = 2
    while f"{prefix}_{n}" in cables:
        n += 1
    return f"{prefix}_{n}"


def _validated_conduit_path(
    doc: dict[str, Any], raw_path: list[Any] | None
) -> list[dict[str, str]]:
    """Validate an ordered, oriented route selected in the canvas."""
    if raw_path is None:
        return []
    if not isinstance(raw_path, list):
        raise ValueError("conduit_path must be a list")
    path: list[dict[str, str]] = []
    for raw_hop in raw_path:
        if not isinstance(raw_hop, dict):
            raise ValueError("each conduit_path item must be an object")
        hop = {
            key: str(raw_hop.get(key) or "").strip()
            for key in ("conduit", "from", "to", "from_opening", "to_opening")
        }
        if not all(hop.values()):
            raise ValueError("each conduit_path item needs conduit and endpoints")
        _parts, _owner, conduit = find_cable_owner(doc, hop["conduit"])
        if resolve_link_kind(conduit, load_catalog()) != "conduit":
            raise ValueError(f"{hop['conduit']} is not a Conduit")
        left, right = conduit_endpoints(conduit)
        _left_loc, left_opening = split_conduit_endpoint(left)
        _right_loc, right_opening = split_conduit_endpoint(right)
        if {hop["from_opening"], hop["to_opening"]} != {
            str(left_opening or ""),
            str(right_opening or ""),
        }:
            raise ValueError(
                f"{hop['conduit']} does not match the selected opening endpoints"
            )
        if path and path[-1]["to"] != hop["from"]:
            raise ValueError("conduit_path must be a continuous route")
        path.append(hop)
    return path


def cable_detail(session: SiteSession, *, cable_id: str) -> dict[str, Any]:
    """JSON-friendly detail for the Properties panel."""
    path, doc = session.ensure_doc()
    del path
    owner_parts, _owner, entry = find_cable_owner(doc, cable_id)
    catalog = load_catalog()
    kind = resolve_link_kind(entry, catalog)
    contains = [str(c) for c in (entry.get("contains") or [])]
    row: dict[str, Any] = {
        "id": str(cable_id).strip(),
        "kind": kind,
        "type": entry.get("type"),
        "subtype": entry.get("subtype"),
        "name": entry.get("name"),
        "label": entry.get("label"),
        "notes": entry.get("notes"),
        "section": entry.get("section"),
        "color": entry.get("color"),
        "install": entry.get("install"),
        "from": entry.get("from"),
        "to": entry.get("to"),
        "conduit_path": entry.get("conduit_path"),
        "contains": contains,
        "owner": "/".join(owner_parts) if owner_parts else ".",
    }
    if kind in {"cable", "conductor"}:
        meta = open_runs.parse_open_notes(entry.get("notes"))
        row["open_status"] = meta.status
        row["open_leaves"] = meta.leaves
        row["open_enters"] = meta.enters
        row["open_exits"] = meta.exits
        notes_text = str(entry.get("notes") or "")
        explicit_status = "status:" in notes_text.lower()
        row["is_open_run"] = bool(
            str(cable_id).startswith("OPEN_")
            or (explicit_status and meta.status in {"open", "claimed"})
        )
    return row


def update_cable_properties(
    session: SiteSession,
    *,
    cable_id: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """Patch editable fields on a cables entry."""
    path, doc = session.ensure_doc()
    _parts, owner, entry = find_cable_owner(doc, cable_id)
    catalog = load_catalog()
    kind = resolve_link_kind(entry, catalog)
    unknown = sorted(set(fields) - _EDITABLE_FIELDS)
    if unknown:
        raise ValueError(f"Unsupported cable fields: {', '.join(unknown)}")

    for key, raw in fields.items():
        if key in {"from", "to"} and kind == "cable":
            raise ValueError("Cable sheath has no from/to endpoints")
        if key == "contains":
            if kind == "conductor":
                raise ValueError("Conductor cannot have contains")
            if not isinstance(raw, list):
                raise ValueError("contains must be a list")
            cleaned = [str(x).strip() for x in raw if str(x).strip()]
            cables = _ensure_cables(owner)
            for ref in cleaned:
                if ref not in cables:
                    raise ValueError(f"contains references missing cable: {ref}")
            entry["contains"] = cleaned
            continue
        if key in {"from", "to"}:
            text = None if raw is None else str(raw).strip()
            if not text:
                entry.pop(key, None)
            else:
                if kind == "conduit":
                    split_conduit_endpoint(text)
                entry[key] = text
            continue
        if key == "section" and raw is not None and str(raw).strip():
            entry["section"] = abm.normalize_section(raw)
            continue
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            entry.pop(key, None)
        elif key == "color":
            entry["color"] = str(raw).strip().upper()
        else:
            entry[key] = raw if not isinstance(raw, str) else raw.strip()

    # Re-validate against catalog expanders.
    if kind == "conduit":
        expand_conduit(entry, catalog)
    elif kind == "cable":
        expand_cable(entry, catalog)
    else:
        expand_conductor(entry, catalog)

    session.mark_dirty(path)
    return cable_detail(session, cable_id=cable_id)


def delete_cables(doc: dict[str, Any], names: list[str]) -> list[str]:
    """Delete cables by id; strip from parent ``contains`` first.

    Conduits are removed without deleting their payload. Sheaths remove
    themselves from conduits; child conductors are kept unless also listed.
    """
    deleted: list[str] = []
    catalog = load_catalog()
    pending = [str(n).strip() for n in names if str(n).strip()]
    for name in pending:
        try:
            _parts, owner, entry = find_cable_owner(doc, name)
        except ValueError:
            raise ValueError(f"Unknown id: {name}") from None
        cables = _ensure_cables(owner)
        kind = resolve_link_kind(entry, catalog)
        contains = [str(c) for c in (entry.get("contains") or [])]
        if kind in {"conduit", "cable"} and contains:
            raise ValueError(
                f"No se puede borrar el conector contenedor no vacío: {name}"
            )
        # Drop references from siblings in the same map.
        for other_name, other in list(cables.items()):
            if other_name == name or not isinstance(other, dict):
                continue
            other_contains = [str(c) for c in (other.get("contains") or [])]
            if name in other_contains:
                other["contains"] = [c for c in other_contains if c != name]
                if not other["contains"]:
                    try:
                        other_kind = resolve_link_kind(other, catalog)
                    except ValueError:
                        other_kind = ""
                    if other_kind in {"conduit", "cable"}:
                        del cables[other_name]
                        if other_name not in deleted:
                            deleted.append(other_name)
        del cables[name]
        deleted.append(name)
        del kind  # kind used for clarity / future hooks
    return deleted


def _owner_node_for_insert(
    doc: dict[str, Any], *, owner_id: str | None
) -> tuple[tuple[str, ...], dict[str, Any]]:
    parts = logical_parts_from_id(owner_id or ".")
    node = _owner_for_parts(doc, parts)
    return parts, node


def insert_conduit(
    session: SiteSession,
    *,
    from_ref: str,
    to_ref: str,
    owner_id: str | None = None,
    name: str | None = None,
    subtype: str | None = abm.DEFAULT_CONDUIT_SUBTYPE,
    label: str | None = None,
    notes: str | None = None,
    contains: list[str] | None = None,
    create_open_payload: bool = False,
) -> dict[str, Any]:
    """Create a Conduit between two openings.

    A conduit can be empty. The open→claim workflow is only used when
    ``create_open_payload`` is explicitly requested.
    """
    path, doc = session.ensure_doc()
    _parts, owner = _owner_node_for_insert(doc, owner_id=owner_id)
    # Operate on the owning map (abm helpers expect the map host as ``doc``).
    host = owner
    fr = str(from_ref).strip()
    tr = str(to_ref).strip()
    split_conduit_endpoint(fr)
    split_conduit_endpoint(tr)
    if fr == tr:
        raise ValueError("Conduit ends must be different openings")

    payload = [str(c).strip() for c in (contains or []) if str(c).strip()]
    if not payload and create_open_payload:
        open_name = open_runs.add_open_cable(host, leaves=fr)
        cd_name, _meta = open_runs.claim_open_cable(
            host,
            open_name,
            enter=tr,
            conduit_name=name,
        )
        session.mark_dirty(path)
        detail = cable_detail(session, cable_id=cd_name)
        detail["open_cable"] = open_name
        return detail

    cables = _ensure_cables(host)
    cd_name = name or _next_unique(cables, "Conducto")
    abm.add_conduit(
        host,
        cd_name,
        contains=payload,
        from_ref=fr,
        to_ref=tr,
        subtype=subtype,
        label=label,
        notes=notes,
    )
    session.mark_dirty(path)
    return cable_detail(session, cable_id=cd_name)


def insert_conductor(
    session: SiteSession,
    *,
    from_ref: str,
    to_ref: str,
    owner_id: str | None = None,
    name: str | None = None,
    color: str | None = None,
    section: str | None = None,
    subtype: str | None = abm.DEFAULT_CABLE_SUBTYPE,
    label: str | None = None,
    notes: str | None = None,
    conduit_id: str | None = None,
    conduit_path: list[Any] | None = None,
) -> dict[str, Any]:
    """Create a Conductor between two element terminals."""
    path, doc = session.ensure_doc()
    _parts, owner = _owner_node_for_insert(doc, owner_id=owner_id)
    host = owner
    fr = str(from_ref).strip()
    tr = str(to_ref).strip()
    if not fr or "." not in fr:
        raise ValueError("from must be ElementRef.Terminal (e.g. Socket.N1)")
    if not tr or "." not in tr:
        raise ValueError("to must be ElementRef.Terminal (e.g. Box/Lamp.L1)")
    selected_path = _validated_conduit_path(doc, conduit_path)
    cables = _ensure_cables(host)
    cid = name or _next_unique(cables, "Conductor")
    abm.add_conductor(
        host,
        cid,
        from_ref=fr,
        to_ref=tr,
        color=color,
        section=section,
        subtype=subtype,
        label=label,
        notes=notes,
        conduit_path=selected_path or None,
    )
    conduit_ids = [hop["conduit"] for hop in selected_path]
    if conduit_id and conduit_id not in conduit_ids:
        conduit_ids.append(conduit_id)
    if conduit_ids:
        catalog = load_catalog()
        for selected_conduit_id in dict.fromkeys(conduit_ids):
            _op, _on, conduit = find_cable_owner(doc, selected_conduit_id)
            if resolve_link_kind(conduit, catalog) != "conduit":
                raise ValueError(f"{selected_conduit_id} is not a Conduit")
            contains = [str(c) for c in (conduit.get("contains") or [])]
            if cid not in contains:
                contains.append(cid)
                conduit["contains"] = contains
    session.mark_dirty(path)
    return cable_detail(session, cable_id=cid)


def insert_sheath(
    session: SiteSession,
    *,
    contains: list[str],
    owner_id: str | None = None,
    name: str | None = None,
    color: str | None = None,
    subtype: str | None = abm.DEFAULT_CABLE_SUBTYPE,
    section: str | None = None,
    label: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Group existing conductors/cables into a Cable sheath."""
    path, doc = session.ensure_doc()
    _parts, owner = _owner_node_for_insert(doc, owner_id=owner_id)
    host = owner
    payload = [str(c).strip() for c in contains if str(c).strip()]
    if len(payload) < 1:
        raise ValueError("contains cannot be empty")
    cables = _ensure_cables(host)
    for ref in payload:
        if ref not in cables:
            raise ValueError(f"contains references missing cable: {ref}")
    sheath = name or _next_unique(cables, "Funda")
    abm.add_sheath(
        host,
        sheath,
        contains=payload,
        subtype=subtype,
        color=color,
        section=section,
        label=label,
        notes=notes,
    )
    # Rewrite conduits that listed the members so they list the sheath instead
    # when all members were previously contained (optional tidy).
    catalog = load_catalog()
    for _cname, entry in cables.items():
        if not isinstance(entry, dict):
            continue
        try:
            if resolve_link_kind(entry, catalog) != "conduit":
                continue
        except ValueError:
            continue
        contains_now = [str(c) for c in (entry.get("contains") or [])]
        if not contains_now:
            continue
        if all(m in contains_now for m in payload):
            kept = [c for c in contains_now if c not in payload]
            kept.append(sheath)
            entry["contains"] = kept
    session.mark_dirty(path)
    return cable_detail(session, cable_id=sheath)


def open_run(
    session: SiteSession,
    *,
    leaves: str,
    owner_id: str | None = None,
    colors: list[str] | None = None,
    section: str | None = None,
    subtype: str | None = None,
    label: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    path, doc = session.ensure_doc()
    _parts, owner = _owner_node_for_insert(doc, owner_id=owner_id)
    leave_ref = str(leaves).strip()
    if "." not in leave_ref:
        # Bare opening id → resolve against owner place leaf.
        loc = "/".join(_parts) if _parts else "."
        leave_ref = open_runs.resolve_leave_ref(
            leave_ref, current_location_ref=loc if loc != "." else "."
        )
        if loc != "." and leave_ref.startswith("."):
            leave_ref = format_conduit_endpoint(loc, leave_ref.split(".", 1)[-1])
    name = open_runs.add_open_cable(
        owner,
        leaves=leave_ref,
        colors=colors,
        section=section,
        subtype=subtype,
        label=label,
        notes=notes,
    )
    session.mark_dirty(path)
    return cable_detail(session, cable_id=name)


def claim_run(
    session: SiteSession,
    *,
    cable_id: str,
    enter: str,
    exit: str | None = None,
    conduit_name: str | None = None,
) -> dict[str, Any]:
    path, doc = session.ensure_doc()
    _parts, owner, _entry = find_cable_owner(doc, cable_id)
    cd_name, _meta = open_runs.claim_open_cable(
        owner,
        str(cable_id).strip(),
        enter=str(enter).strip(),
        exit=str(exit).strip() if exit else None,
        conduit_name=conduit_name,
    )
    session.mark_dirty(path)
    detail = cable_detail(session, cable_id=cable_id)
    detail["conduit"] = cd_name
    return detail


def land_run(
    session: SiteSession,
    *,
    cable_id: str,
    from_ref: str,
    to_ref: str,
    as_name: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    path, doc = session.ensure_doc()
    _parts, owner, _entry = find_cable_owner(doc, cable_id)
    final = open_runs.land_open_cable(
        owner,
        str(cable_id).strip(),
        from_ref=str(from_ref).strip(),
        to_ref=str(to_ref).strip(),
        as_name=as_name,
        notes=notes,
    )
    session.mark_dirty(path)
    return cable_detail(session, cable_id=final)


def list_open_runs(session: SiteSession, *, owner_id: str | None = None) -> list[dict[str, Any]]:
    _path, doc = session.ensure_doc()
    if owner_id:
        parts = logical_parts_from_id(owner_id)
        owner = _owner_for_parts(doc, parts)
        rows = open_runs.list_open_cables(owner)
    else:
        rows = []
        for _parts, node in _iter_owners(doc):
            rows.extend(open_runs.list_open_cables(node))
    out: list[dict[str, Any]] = []
    for name, meta in rows:
        out.append(
            {
                "id": name,
                "status": meta.status,
                "leaves": meta.leaves,
                "enters": meta.enters,
                "exits": meta.exits,
            }
        )
    return out
