"""Orchestrate capture recipes for shell and UI (session + ABM)."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterator

from housewire.house import (
    location_id_from_name,
    place_label,
    place_meta_from_mapping,
    place_name,
)
from housewire.house.conduit_ref import (
    conduit_endpoints,
    resolve_location_ref,
    split_conduit_endpoint,
)
from housewire.site import abm, recipes
from housewire.site.io import create_inline_location
from housewire.site.session import SiteSession
from housewire.site.view_layout import get_physical_position, set_physical_position


def opening_grid_for(opening_id: str) -> dict[str, int]:
    """Derive a minimal opening_grid from an opening id (N1 → {N: 1})."""
    text = str(opening_id).strip()
    if not text:
        return {}
    face = text[0].upper()
    if face.isalpha():
        return {face: 1}
    return {}


def colors_list(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    parts = [part.strip() for part in str(raw).split(",") if part.strip()]
    return parts or None


def _known_location_parts(root: Path) -> set[tuple[str, ...]]:
    from housewire.site.io import load_yaml
    from housewire.site.paths import find_site_yaml
    from housewire.site.tree import iter_places

    known: set[tuple[str, ...]] = {()}
    site = find_site_yaml(root)
    if site is None or not site.is_file():
        return known
    doc = load_yaml(site)
    for parts, _node in iter_places(doc, under=()):
        known.add(parts)
    return known


def _entry_name(defn: dict[str, Any], entry_id: str) -> str | None:
    raw = defn.get("name")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    return None


def _entry_label(defn: dict[str, Any]) -> str | None:
    raw = defn.get("label")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    return None


def _cable_row(name: str, defn: dict[str, Any], *, defined_in: str | None = None) -> dict[str, Any]:
    contains_raw = defn.get("contains") or []
    contains = (
        [str(c) for c in contains_raw] if isinstance(contains_raw, list) else []
    )
    color = defn.get("color")
    colors = [str(color)] if color is not None and str(color).strip() else []
    row: dict[str, Any] = {
        "id": str(name),
        "name": _entry_name(defn, str(name)),
        "label": _entry_label(defn),
        "type": defn.get("type"),
        "subtype": defn.get("subtype"),
        "section": defn.get("section"),
        "color": str(color) if color is not None else None,
        "colors": colors,
        "contains": contains or None,
        "from": defn.get("from"),
        "to": defn.get("to"),
        "notes": defn.get("notes"),
    }
    if defined_in:
        row["defined_in"] = defined_in
    return row


def _conduit_row(
    name: str,
    defn: dict[str, Any],
    *,
    defined_in: str | None = None,
    from_opening: str | None = None,
    to_opening: str | None = None,
) -> dict[str, Any]:
    contains_raw = defn.get("contains") or []
    contains = (
        [str(c) for c in contains_raw] if isinstance(contains_raw, list) else []
    )
    row: dict[str, Any] = {
        "id": str(name),
        "name": _entry_name(defn, str(name)),
        "label": _entry_label(defn),
        "from": defn.get("from"),
        "to": defn.get("to"),
        "subtype": defn.get("subtype"),
        "contains": contains,
        "notes": defn.get("notes"),
    }
    if from_opening is not None:
        row["from_opening"] = from_opening
    if to_opening is not None:
        row["to_opening"] = to_opening
    if defined_in:
        row["defined_in"] = defined_in
    return row


def _place_wiring(
    session: SiteSession,
    *,
    place_parts: tuple[str, ...],
    place_doc: dict[str, Any],
    place_yaml: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Cables/conduits for a place from the unified ``cables`` map."""
    from housewire.house import load_catalog
    from housewire.house.links import resolve_link_kind
    from housewire.site.tree import get_place_node

    catalog = load_catalog()
    root = session.root.resolve()
    place_rel = str(place_yaml.relative_to(root))
    cables_by_id: dict[str, dict[str, Any]] = {}
    conduits_by_id: dict[str, dict[str, Any]] = {}

    def _ingest_cables_map(cables: dict[str, Any], *, defined_in: str) -> None:
        for name, defn in sorted(cables.items(), key=lambda kv: str(kv[0]).lower()):
            if not isinstance(defn, dict):
                continue
            try:
                kind = resolve_link_kind(defn, catalog)
            except ValueError:
                continue
            if kind == "conduit":
                try:
                    from_ref, to_ref = conduit_endpoints(defn)
                    _from_loc, from_op = split_conduit_endpoint(from_ref)
                    _to_loc, to_op = split_conduit_endpoint(to_ref)
                except ValueError:
                    from_op = to_op = None
                conduits_by_id[str(name)] = _conduit_row(
                    str(name),
                    defn,
                    defined_in=defined_in,
                    from_opening=from_op,
                    to_opening=to_op,
                )
            else:
                cables_by_id[str(name)] = _cable_row(
                    str(name), defn, defined_in=defined_in
                )

    local_cables = place_doc.get("cables") or {}
    if isinstance(local_cables, dict):
        _ingest_cables_map(local_cables, defined_in=place_rel)

    known = _known_location_parts(root)
    try:
        _site_path, site_doc = session.ensure_doc(place_yaml.resolve())
    except FileNotFoundError:
        site_doc = None

    def _endpoint_touches_place(endpoint_parts: tuple[str, ...]) -> bool:
        """True if the conduit end is this place or a nested child of it."""
        if endpoint_parts == place_parts:
            return True
        if len(endpoint_parts) <= len(place_parts):
            return False
        return endpoint_parts[: len(place_parts)] == place_parts

    if isinstance(site_doc, dict):
        for cut in range(len(place_parts) - 1, -1, -1):
            ancestor = place_parts[:cut]
            try:
                adoc = get_place_node(site_doc, ancestor)
            except ValueError:
                continue
            cables = adoc.get("cables") or {}
            if not isinstance(cables, dict):
                continue
            for name, defn in cables.items():
                if not isinstance(defn, dict):
                    continue
                try:
                    if resolve_link_kind(defn, catalog) != "conduit":
                        continue
                except ValueError:
                    continue
                cid = str(name)
                if cid in conduits_by_id:
                    continue
                try:
                    from_ref, to_ref = conduit_endpoints(defn)
                    from_loc, from_op = split_conduit_endpoint(from_ref)
                    to_loc, to_op = split_conduit_endpoint(to_ref)
                    from_parts = resolve_location_ref(
                        from_loc, current_parts=list(ancestor), known=known
                    )
                    to_parts = resolve_location_ref(
                        to_loc, current_parts=list(ancestor), known=known
                    )
                except ValueError:
                    continue
                if not (
                    _endpoint_touches_place(tuple(from_parts))
                    or _endpoint_touches_place(tuple(to_parts))
                ):
                    continue
                conduits_by_id[cid] = _conduit_row(
                    cid,
                    defn,
                    defined_in=place_rel,
                    from_opening=from_op,
                    to_opening=to_op,
                )
                for cable_name in conduits_by_id[cid]["contains"]:
                    if cable_name in cables_by_id:
                        continue
                    cdef = cables.get(cable_name)
                    if isinstance(cdef, dict):
                        cables_by_id[cable_name] = _cable_row(
                            cable_name, cdef, defined_in=place_rel
                        )

    cables_out = sorted(cables_by_id.values(), key=lambda r: str(r["id"]).lower())
    conduits_out = sorted(
        conduits_by_id.values(), key=lambda r: str(r["id"]).lower()
    )
    return cables_out, conduits_out


@contextmanager
def at_location(session: SiteSession, location_id: str | None) -> Iterator[None]:
    """Temporarily ``cd`` the session to ``location_id`` (canvas root)."""
    if location_id is None:
        yield
        return
    saved = list(session.logical_parts)
    try:
        if location_id in {".", ""}:
            session.logical_parts = []
            session._sync_from_logical()
        else:
            session.cd(location_id)
        yield
    finally:
        session.logical_parts = saved
        session._sync_from_logical()


def create_recipe_place(
    session: SiteSession,
    name: str,
    *,
    type_id: str,
    subtype: str | None,
    label: str | None,
    notes: str | None,
    openings: list[str],
    opening_grid: dict[str, int] | None,
    install: str | None,
    mount: str | None,
    want_inline: bool = False,
    as_dir: bool = False,
    working_name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Create destination place for socket/lamp recipes; return (leaf_id, place_map)."""
    del want_inline, as_dir  # always nested under current place
    raw = Path(name)
    if str(raw.parent) not in (".", ""):
        raise ValueError(
            "recipe NAME must be a leaf (no path); cd to the parent location first"
        )
    leaf_id, auto_label = location_id_from_name(raw.name)
    resolved_label = label or auto_label

    set_specs = [f"openings=[{', '.join(openings)}]"]
    grid = opening_grid
    if grid is None and openings:
        grid = opening_grid_for(openings[0])
    if grid:
        for face, count in grid.items():
            set_specs.append(f"opening_grid.{face}={count}")
    if install:
        set_specs.append(f"install={install}")
    if mount:
        set_specs.append(f"mount={mount}")

    for child in session.list_location_children():
        if child.name == leaf_id:
            raise ValueError(f"Location already exists: {leaf_id}")
    path, doc = session.ensure_doc()
    parent_place = session.place_node(doc)
    entry = create_inline_location(
        parent_place,
        leaf_id,
        type_id=type_id,
        subtype=subtype,
        notes=notes,
        label=resolved_label,
        working_name=working_name,
    )
    abm.apply_set_specs(entry, set_specs, target="place")
    session.mark_dirty(path)
    return leaf_id, entry


def _position_near_source(
    session: SiteSession,
    *,
    canvas_location_id: str,
    new_leaf_id: str,
    from_ref: str,
    offset_x: float = 160.0,
    offset_y: float = 0.0,
) -> None:
    """Place new nested node near the source box on the canvas."""
    from housewire.site.tree import get_place_node, logical_parts_from_id

    try:
        box_loc, _op = split_conduit_endpoint(from_ref)
    except ValueError:
        return
    box_rel = str(box_loc).strip()
    if box_rel in (".", "", "self"):
        return
    leaf = box_rel.split("/")[-1]
    canvas_parts = logical_parts_from_id(canvas_location_id)
    try:
        path, doc = session.ensure_doc()
    except (FileNotFoundError, ValueError, OSError):
        return
    try:
        source = get_place_node(doc, (*canvas_parts, leaf))
        new_place = get_place_node(doc, (*canvas_parts, new_leaf_id))
    except ValueError:
        return
    pos = get_physical_position(source)
    if pos is None:
        return
    set_physical_position(new_place, pos[0] + offset_x, pos[1] + offset_y)
    session.mark_dirty(path)


def run_socket_recipe(
    session: SiteSession,
    *,
    name: str,
    from_ref: str,
    strip: str,
    pins: str | list[str] | None = None,
    to_opening: str | None = None,
    colors: str | list[str] | None = None,
    section: str | None = None,
    label: str | None = None,
    notes: str | None = None,
    want_inline: bool = False,
    as_dir: bool = False,
    canvas_location_id: str | None = None,
) -> dict[str, Any]:
    """Create DeviceBox+Socket and wire from parent canvas doc."""
    with at_location(session, canvas_location_id):
        parent_path, parent_doc = session.ensure_doc()
        parent_place = session.place_node(parent_doc)
        opening = str(to_opening or recipes.SOCKET_DEFAULT_TO_OPENING).strip()
        leaf_id, place_map = create_recipe_place(
            session,
            name,
            type_id=recipes.SOCKET_PLACE_TYPE,
            subtype=recipes.SOCKET_PLACE_SUBTYPE,
            label=label,
            notes=None,
            openings=[opening],
            opening_grid=None,
            install="Flush",
            mount="Wall",
            want_inline=want_inline,
            as_dir=as_dir,
        )
        abm.add_element(
            place_map,
            recipes.SOCKET_ELEMENT,
            type_id="Socket",
            subtype=recipes.SOCKET_ELEMENT_SUBTYPE,
            label=label,
            notes=notes,
        )
        color_list = (
            list(colors)
            if isinstance(colors, list)
            else colors_list(colors if isinstance(colors, str) else None)
        )
        result = recipes.socket_wired_run(
            parent_place,
            place_id=leaf_id,
            from_ref=from_ref,
            strip=strip,
            pins=recipes.parse_pins(pins) or None,
            to_opening=opening,
            colors=color_list,
            section=section,
            notes=notes,
        )
        session.mark_dirty(parent_path)
        if canvas_location_id is not None:
            _position_near_source(
                session,
                canvas_location_id=canvas_location_id,
                new_leaf_id=leaf_id,
                from_ref=from_ref,
            )
        return {
            "kind": "socket",
            "place_id": leaf_id,
            **asdict(result),
        }


def run_lamp_recipe(
    session: SiteSession,
    *,
    name: str,
    from_ref: str,
    strip: str,
    pins: str | list[str],
    to_pins: str | list[str] | None = None,
    to_opening: str | None = None,
    colors: str | list[str] | None = None,
    section: str | None = None,
    label: str | None = None,
    notes: str | None = None,
    want_inline: bool = False,
    as_dir: bool = False,
    canvas_location_id: str | None = None,
) -> dict[str, Any]:
    """Create LightPoint+Luminaire and wire from parent canvas doc."""
    with at_location(session, canvas_location_id):
        parent_path, parent_doc = session.ensure_doc()
        parent_place = session.place_node(parent_doc)
        opening = str(to_opening or recipes.LAMP_DEFAULT_TO_OPENING).strip()
        leaf_id, place_map = create_recipe_place(
            session,
            name,
            type_id=recipes.LAMP_PLACE_TYPE,
            subtype=recipes.LAMP_PLACE_SUBTYPE,
            label=label,
            notes=None,
            openings=[opening],
            opening_grid=None,
            install="Flush",
            mount="Ceiling",
            want_inline=want_inline,
            as_dir=as_dir,
        )
        abm.add_element(
            place_map,
            recipes.LAMP_ELEMENT,
            type_id="Luminaire",
            label=label,
            notes=notes,
        )
        color_list = (
            list(colors)
            if isinstance(colors, list)
            else colors_list(colors if isinstance(colors, str) else None)
        )
        result = recipes.lamp_wired_run(
            parent_place,
            place_id=leaf_id,
            from_ref=from_ref,
            strip=strip,
            pins=recipes.parse_pins(pins),
            to_pins=recipes.parse_pins(to_pins) or None,
            to_opening=opening,
            colors=color_list,
            section=section,
            notes=notes,
        )
        session.mark_dirty(parent_path)
        if canvas_location_id is not None:
            _position_near_source(
                session,
                canvas_location_id=canvas_location_id,
                new_leaf_id=leaf_id,
                from_ref=from_ref,
                offset_y=-120.0,
            )
        return {
            "kind": "lamp",
            "place_id": leaf_id,
            **asdict(result),
        }


def run_feed_recipe(
    session: SiteSession,
    *,
    name: str,
    from_ref: str,
    to_ref: str,
    from_pin: str,
    to_pin: str,
    colors: str | list[str] | None = None,
    section: str | None = None,
    notes: str | None = None,
    canvas_location_id: str | None = None,
) -> dict[str, Any]:
    """Add feed cable+conduit+connection on the canvas root doc."""
    with at_location(session, canvas_location_id):
        path, doc = session.ensure_doc()
        place = session.place_node(doc)
        color_list = (
            list(colors)
            if isinstance(colors, list)
            else colors_list(colors if isinstance(colors, str) else None)
        )
        result = recipes.feed_wired_run(
            place,
            name=name,
            from_opening=from_ref,
            to_opening=to_ref,
            from_pin=from_pin,
            to_pin=to_pin,
            colors=color_list,
            section=section,
            notes=notes,
        )
        session.mark_dirty(path)
        return {
            "kind": "feed",
            "place_id": None,
            **asdict(result),
        }


def _resolve_place_parts(
    canvas_location_id: str, place_id: str
) -> tuple[str, ...]:
    canvas_parts = (
        tuple()
        if canvas_location_id in {".", ""}
        else tuple(p for p in str(canvas_location_id).split("/") if p)
    )
    # ``.`` / ``@`` = the canvas location itself (site root when canvas is ``.``).
    if str(place_id).strip() in {".", "", "@"}:
        return canvas_parts
    parts = tuple(p for p in str(place_id).split("/") if p)
    if not parts:
        raise ValueError("place id is required")
    return canvas_parts + parts


def _relative_place_id(
    canvas_location_id: str, place_parts: tuple[str, ...]
) -> str:
    canvas_parts = (
        tuple()
        if canvas_location_id in {".", ""}
        else tuple(p for p in str(canvas_location_id).split("/") if p)
    )
    if place_parts == canvas_parts:
        return "."
    if len(place_parts) >= len(canvas_parts) and place_parts[: len(canvas_parts)] == canvas_parts:
        return "/".join(place_parts[len(canvas_parts) :])
    return "/".join(place_parts)


def place_detail(
    session: SiteSession,
    *,
    canvas_location_id: str,
    place_id: str,
) -> dict[str, Any]:
    """Return detail for a nested child under the canvas root (or the canvas itself)."""
    from housewire.site.tree import get_place_node

    place_parts = _resolve_place_parts(canvas_location_id, place_id)
    path, site_doc = session.ensure_doc()
    doc = get_place_node(site_doc, place_parts)
    meta = place_meta_from_mapping(doc) or {}
    elements_raw = doc.get("elements") or {}
    elements: list[dict[str, Any]] = []
    if isinstance(elements_raw, dict):
        for name, defn in sorted(elements_raw.items(), key=lambda kv: str(kv[0]).lower()):
            if not isinstance(defn, dict):
                continue
            elements.append(
                {
                    "id": str(name),
                    "name": (
                        str(defn["name"]).strip()
                        if defn.get("name") is not None
                        and str(defn.get("name")).strip()
                        else None
                    ),
                    "type": defn.get("type"),
                    "subtype": defn.get("subtype"),
                    "label": defn.get("label"),
                }
            )
    openings = meta.get("openings") or []
    if not isinstance(openings, list):
        openings = []
    opening_grid = meta.get("opening_grid")
    if not isinstance(opening_grid, dict):
        opening_grid = None
    cables, conduits = _place_wiring(
        session,
        place_parts=place_parts,
        place_doc=doc,
        place_yaml=path,
    )
    from housewire.site.view_layout import get_physical_flips

    rel_id = _relative_place_id(canvas_location_id, place_parts)
    leaf = place_parts[-1] if place_parts else ""
    flip_ns, flip_we = get_physical_flips(doc)
    return {
        "id": rel_id,
        "path": f"{path.relative_to(session.root)}#{'/'.join(place_parts)}",
        "type": meta.get("type"),
        "subtype": meta.get("subtype"),
        "name": meta.get("name"),
        "label": meta.get("label"),
        "display_name": place_name(meta, leaf),
        "display_label": place_label(meta, leaf),
        "notes": meta.get("notes"),
        "install": meta.get("install"),
        "mount": meta.get("mount"),
        "flip_ns": flip_ns,
        "flip_we": flip_we,
        "openings": [str(o) for o in openings],
        "opening_grid": opening_grid,
        "elements": elements,
        "cables": cables,
        "conduits": conduits,
    }


# Fields the Properties panel may edit (shell ``set`` allows more).
_EDITABLE_PLACE_FIELDS = frozenset(
    {
        "name",
        "label",
        "type",
        "subtype",
        "notes",
        "install",
        "mount",
        "flip_ns",
        "flip_we",
        "opening_grid",
        "openings",
    }
)
_EDITABLE_ELEMENT_FIELDS = frozenset(
    {
        "name",
        "label",
        "type",
        "subtype",
        "notes",
        "flip_ns",
        "flip_we",
        "terminal_grid",
        "terminals",
    }
)
_FLIP_FIELDS = frozenset({"flip_ns", "flip_we"})
# Apply capacity before used lists so validation sees a consistent pair.
_STRUCTURED_FIELD_ORDER = (
    "opening_grid",
    "openings",
    "terminal_grid",
    "terminals",
)


def update_place_properties(
    session: SiteSession,
    *,
    canvas_location_id: str,
    place_id: str,
    fields: dict[str, Any],
    element: str | None = None,
) -> dict[str, Any]:
    """Apply property edits to a place or nested element; return place detail."""
    from housewire.site import abm
    from housewire.site.tree import get_place_node
    from housewire.site.view_layout import (
        parse_flip_field,
        set_electrical_flips,
        set_physical_flips,
    )

    if not isinstance(fields, dict) or not fields:
        raise ValueError("fields must be a non-empty object")

    place_parts = _resolve_place_parts(canvas_location_id, place_id)
    path, site_doc = session.ensure_doc()
    doc = get_place_node(site_doc, place_parts)
    if not isinstance(doc, dict):
        raise ValueError(f"Invalid place: {place_id}")

    if element:
        allowed = _EDITABLE_ELEMENT_FIELDS
        elements = doc.get("elements") or {}
        if not isinstance(elements, dict) or element not in elements:
            raise ValueError(f"Element does not exist: {element}")
        target = elements[element]
        if not isinstance(target, dict):
            raise ValueError(f"Invalid element: {element}")
        target_kind: abm.SetTarget = "element"
    else:
        allowed = _EDITABLE_PLACE_FIELDS
        target = doc
        target_kind = "place"

    unknown = [k for k in fields if k not in allowed]
    if unknown:
        raise ValueError(
            "Unsupported field(s): "
            + ", ".join(sorted(str(k) for k in unknown))
            + f". Editable: {', '.join(sorted(allowed))}"
        )

    flip_updates: dict[str, bool] = {}
    ordered_keys = [k for k in _STRUCTURED_FIELD_ORDER if k in fields]
    ordered_keys.extend(
        k for k in fields if k not in _STRUCTURED_FIELD_ORDER
    )
    for key in ordered_keys:
        raw = fields[key]
        if key in _FLIP_FIELDS:
            flip_updates[key] = parse_flip_field(raw)
            continue
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            if key in target:
                abm.unset_field(target, key)
            continue
        if key in {"opening_grid", "terminal_grid"} and not isinstance(raw, dict):
            raise ValueError(f"{key} must be a map")
        if key == "openings" and not isinstance(raw, list):
            raise ValueError("openings must be a list of ids")
        if key == "terminals" and not isinstance(raw, dict):
            raise ValueError("terminals must be a map of pin id → metadata")
        # Plain text from the Properties panel (notes often contain "a: b").
        # Do not YAML-parse — that raises or turns free text into mappings.
        abm.set_field(target, key, raw, target=target_kind)

    if flip_updates:
        if element:
            set_electrical_flips(
                target,
                flip_ns=flip_updates.get("flip_ns"),
                flip_we=flip_updates.get("flip_we"),
            )
        else:
            set_physical_flips(
                target,
                flip_ns=flip_updates.get("flip_ns"),
                flip_we=flip_updates.get("flip_we"),
            )

    session.mark_dirty(path)
    return place_detail(
        session, canvas_location_id=canvas_location_id, place_id=place_id
    )


def _next_free_child_id(parent_doc: dict[str, Any], base: str) -> str:
    """Return unique child key under ``parent_doc['elements']``."""
    from housewire.site.clipboard import next_available_id

    elements = parent_doc.get("elements") or {}
    if not isinstance(elements, dict):
        raise ValueError("elements must be a map")
    stem = str(base or "").strip() or "NewItem"
    return next_available_id(elements, stem)


def _safe_token(raw: str | None, fallback: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return fallback
    out = "".join(ch if (ch.isalnum() or ch in {"_", "-"}) else "_" for ch in text)
    out = out.strip("_")
    while "__" in out:
        out = out.replace("__", "_")
    return out or fallback


def insert_catalog_item(
    session: SiteSession,
    *,
    canvas_location_id: str,
    place_id: str,
    type_id: str,
    subtype: str | None = None,
    id: str | None = None,
    name: str | None = None,
    label: str | None = None,
    notes: str | None = None,
    x: float | None = None,
    y: float | None = None,
    w: float | None = None,
    h: float | None = None,
) -> dict[str, Any]:
    """Insert place/element by catalog type under a selected place."""
    from housewire.house import is_place_type
    from housewire.site.clipboard import (
        display_name_from_id,
        next_available_display_name,
        next_available_id,
        _sibling_working_fields,
    )
    from housewire.site.io import create_inline_location
    from housewire.site.tree import get_place_node
    from housewire.site.view_layout import (
        set_electrical_position,
        set_physical_position,
        set_physical_size,
    )

    place_parts = _resolve_place_parts(canvas_location_id, place_id)
    path, site_doc = session.ensure_doc()
    parent_doc = get_place_node(site_doc, place_parts)
    if not isinstance(parent_doc, dict):
        raise ValueError(f"Invalid place: {place_id}")

    parent_doc.setdefault("elements", {})
    elements = parent_doc.get("elements") or {}
    if not isinstance(elements, dict):
        raise ValueError("elements must be a map")

    preferred_id = _safe_token(
        id, _safe_token(name, _safe_token(type_id, "NewItem"))
    )
    child_id = next_available_id(elements, preferred_id)
    id_bumped = child_id != preferred_id

    preferred_name = (
        str(name).strip()
        if name is not None and str(name).strip()
        else display_name_from_id(preferred_id)
    )
    preferred_label = (
        str(label).strip()
        if label is not None and str(label).strip()
        else preferred_name
    )
    taken_names, taken_labels = _sibling_working_fields(elements)
    if id_bumped:
        # Mirror paste: when the technical id collides, bump display fields too.
        taken_names.add(preferred_name)
        taken_labels.add(preferred_label)
    working_name = next_available_display_name(taken_names, preferred_name)
    working_label = next_available_display_name(taken_labels, preferred_label)

    notes_text = str(notes).strip() if notes is not None and str(notes).strip() else None
    subtype_text = (
        str(subtype).strip() if subtype is not None and str(subtype).strip() else None
    )
    x0 = float(x) if x is not None else 24.0
    y0 = float(y) if y is not None else 24.0

    rel_parent = _relative_place_id(canvas_location_id, place_parts)
    rel_inserted = child_id if rel_parent in {".", ""} else f"{rel_parent}/{child_id}"
    is_place = is_place_type(type_id)
    if is_place:
        created = create_inline_location(
            parent_doc,
            child_id,
            type_id=type_id,
            subtype=subtype_text,
            notes=notes_text,
            label=working_label,
            working_name=working_name,
        )
        set_physical_position(created, x0, y0)
        if w is not None and h is not None:
            try:
                set_physical_size(created, float(w), float(h))
            except ValueError:
                # Keep default autosize if caller sends invalid dimensions.
                pass
        kind = "place"
    else:
        abm.add_element(
            parent_doc,
            child_id,
            type_id=str(type_id),
            subtype=subtype_text,
            label=working_label,
            notes=notes_text,
        )
        elements = parent_doc.get("elements") or {}
        created = elements.get(child_id)
        if isinstance(created, dict):
            set_electrical_position(created, x0, y0)
            created["name"] = working_name
            created["label"] = working_label
        kind = "element"

    session.mark_dirty(path)
    return {
        "kind": kind,
        "id": rel_inserted,
        "leaf_id": child_id,
        "parent_id": rel_parent,
        "type": str(type_id),
        "subtype": subtype_text,
        "name": working_name,
        "label": working_label,
    }
