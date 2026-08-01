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
from housewire.house.conduit_ref import split_conduit_endpoint
from housewire.project import abm, recipes
from housewire.project.io import HOUSEWIRE_YAML, create_inline_location
from housewire.project.session import ProjectSession
from housewire.project.view_layout import get_physical_position, set_physical_position


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


@contextmanager
def at_location(session: ProjectSession, location_id: str | None) -> Iterator[None]:
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
    session: ProjectSession,
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
    raw = Path(name)
    if str(raw.parent) not in (".", ""):
        raise ValueError(
            "recipe NAME must be a leaf (no path); cd to the parent location first"
        )
    leaf_id, auto_label = location_id_from_name(raw.name)
    resolved_label = label or auto_label
    cursor = session.cursor()
    use_inline = want_inline or (not as_dir and cursor.is_inline)
    if as_dir and cursor.is_inline:
        raise ValueError(
            "Cannot create recipe location --dir under an inline place. "
            "cd to the parent outline or use --inline."
        )

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

    if use_inline:
        for child in session.list_location_children():
            if child.name == leaf_id and child.storage == "dir":
                raise ValueError(
                    f"Outline location {leaf_id!r} already exists; "
                    "cannot create the same id inline"
                )
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

    for child in session.list_location_children():
        if child.name == leaf_id and child.storage == "inline":
            raise ValueError(
                f"Inline location {leaf_id!r} already exists; "
                "cannot create the same id as a folder"
            )
    target = session.resolve_under_root(leaf_id)
    index_path = session.stage_outline_location(
        target,
        type_id=type_id,
        subtype=subtype,
        notes=notes,
        label=resolved_label,
        working_name=working_name,
    )
    _path, staged = session.ensure_doc(index_path)
    abm.apply_set_specs(staged, set_specs, target="place")
    session.mark_dirty(index_path)
    return leaf_id, staged


def _position_near_source(
    session: ProjectSession,
    *,
    canvas_location_id: str,
    new_leaf_id: str,
    from_ref: str,
    offset_x: float = 160.0,
    offset_y: float = 0.0,
) -> None:
    """Place new outline node near the source box on the canvas."""
    try:
        box_loc, _op = split_conduit_endpoint(from_ref)
    except ValueError:
        return
    box_rel = str(box_loc).strip()
    if box_rel in (".", "", "self"):
        return
    # Source is usually a sibling under the canvas root.
    leaf = box_rel.split("/")[-1]
    canvas_dir = (
        session.root
        if canvas_location_id in {".", ""}
        else (session.root / canvas_location_id)
    )
    source_yaml = (canvas_dir / leaf / HOUSEWIRE_YAML).resolve()
    new_yaml = (canvas_dir / new_leaf_id / HOUSEWIRE_YAML).resolve()
    try:
        _sp, source_doc = session.ensure_doc(source_yaml)
    except (FileNotFoundError, ValueError, OSError):
        return
    pos = get_physical_position(source_doc)
    if pos is None:
        return
    try:
        _np, new_doc = session.ensure_doc(new_yaml)
    except (FileNotFoundError, ValueError, OSError):
        return
    set_physical_position(new_doc, pos[0] + offset_x, pos[1] + offset_y)
    session.mark_dirty(new_yaml)


def run_socket_recipe(
    session: ProjectSession,
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
            install="surface",
            mount="wall",
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
        if canvas_location_id is not None and not want_inline:
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
    session: ProjectSession,
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
            install="surface",
            mount="ceiling",
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
        if canvas_location_id is not None and not want_inline:
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
    session: ProjectSession,
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


def place_detail(
    session: ProjectSession,
    *,
    canvas_location_id: str,
    place_id: str,
) -> dict[str, Any]:
    """Return show-like detail for an outline child under the canvas root."""
    parts = tuple(p for p in str(place_id).split("/") if p)
    if not parts:
        raise ValueError("place id is required")
    canvas_dir = (
        session.root
        if canvas_location_id in {".", ""}
        else (session.root / canvas_location_id).resolve()
    )
    yaml_path = (canvas_dir.joinpath(*parts) / HOUSEWIRE_YAML).resolve()
    path, doc = session.ensure_doc(yaml_path)
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
                    "type": defn.get("type"),
                    "subtype": defn.get("subtype"),
                    "label": defn.get("label"),
                }
            )
    openings = meta.get("openings") or []
    if not isinstance(openings, list):
        openings = []
    connects = doc.get("connects")
    if not isinstance(connects, list):
        connects = meta.get("connects") if isinstance(meta.get("connects"), list) else []
    return {
        "id": "/".join(parts),
        "path": str(path.relative_to(session.root)),
        "type": meta.get("type"),
        "subtype": meta.get("subtype"),
        "name": meta.get("name"),
        "label": meta.get("label"),
        "display_name": place_name(meta, parts[-1]),
        "display_label": place_label(meta, parts[-1]),
        "notes": meta.get("notes"),
        "install": meta.get("install"),
        "mount": meta.get("mount"),
        "openings": [str(o) for o in openings],
        "connects": [str(c) for c in connects],
        "elements": elements,
    }
