from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from housewire.project import abm
from housewire.project.io import HOUSEWIRE_YAML, create_inline_location
from housewire.project.session import ProjectSession

if TYPE_CHECKING:
    pass

HELP_TEXT = """housewire shell commands:
  (Tab completes commands, add/rm subcommands, and cd/use/… paths)
  pwd                          logical location path and host YAML (* = any dirty buffer)
  cd [path]                    navigate locations (outline folder or inline place);
                               dirty YAML stay in memory (no save prompt on cd)
  ls                           child locations (outline+inline) and elements (non-place)
  use housewire.yaml           set active housewire.yaml for the current location
  show                         current place: electrical layer + physical layer
  show --element NAME | --cable NAME
  pend [<enter> <exit>] [section] [--colors C1,C2] [--notes ...]
                               pending cable + conduit from/to (.N1 → .S1)
  open [BOX.]Op [section] [--colors C1,C2] [--notes ...]
                               OPEN_* cable leaving an opening (far end unknown)
  claim OPEN_NN --enter [BOX.]Op [--exit Op]
                               attach next conduit hop (from leaves/exits → enter)
  land OPEN_NN --from REF --to REF --as FinalName [--notes ...]
                               electrical connection + rename off OPEN_
  opens                        list open/claimed OPEN_* cables (current + ancestors)
  set KEY VALUE | set KEY=VALUE
                               property of the current place (YAML; memory → save)
                               nested: opening_grid.N=1
  set --element NAME KEY VALUE property of an element in the place
  unset KEY | unset --element NAME KEY
  add location NAME --type T [--subtype ...] [--label ...] [--notes ...]
                               [--inline | --dir] [--set KEY=VALUE | --set KEY VALUE …]
                               T=Room|JunctionBox|DeviceBox|LightPoint|Panel|Floor|House
                               default: outline if you are in outline; inline if you are inline
                               (memory → save; outline creates folder on save)
                               NAME with spaces → technical id + automatic label
  add socket NAME --from BOX.Op --strip ELEMENT [--pins 3,2,1]
                               [--to-opening N1] [--colors GY,GNYE,BU] [--section 2.5]
                               [--inline | --dir] [--label ...] [--notes …]
                               DeviceBox+Socket + cable+conduit+connection (run from parent)
  add lamp NAME --from BOX.Op --strip ELEMENT --pins P1,P2[,P3]
                               [--to-pins 1,2,3] [--to-opening B1-1]
                               [--colors BN,GNYE,BU] [--section 1.5]
                               [--inline | --dir] [--label ...] [--notes …]
                               LightPoint+Luminaire + cable+conduit+connection
  add feed NAME --from BOX.Op --to BOX2.Op --from-pin PATH --to-pin PATH
                               [--colors BN,BU] [--section 1.5] [--notes …]
                               cable+conduit+connection between existing places
  add element NAME --type T … [--set KEY=VALUE | --set KEY VALUE …]  (memory → save)
  add cable NAME …             (memory → save)
  add conduit NAME --from A.Op --to B.Op --contains C1[,C2…]
                               [--subtype tube] [--label ...] [--notes …]
                               (memory → save; physical layer)
  add pend …
  add connection --from F --via V --to T
                               (memory → save; electrical layer)
  add dir <path>                 mkdir -p (no housewire.yaml; prefer add location)
  rm element|cable NAME
  rm connection <index>
  rm file housewire.yaml
  rm dir <path>                  only if empty
  save [--force]                 write all dirty YAML to disk (validate)
  reload                         discard current buffer and re-read from disk
  generate [-f]                save dirty and generate the tree for cwd
                               physical=locations↔conduits; WireViz=elements↔cables
  version                      program version
  help
  exit | quit                  prompts to save/discard each dirty YAML
  (multi-line)                 end the line with \\ and continue on the next
"""


def _parse_add_args(argv: list[str]) -> tuple[str, list[str]]:
    if not argv:
        raise ValueError(
            "add requires a subcommand: location, element, cable, conduit, pend, "
            "connection, socket, lamp, feed, dir"
        )
    return argv[0], argv[1:]


def _opening_grid_for(opening_id: str) -> dict[str, int]:
    """Derive a minimal opening_grid from an opening id (N1 → {N: 1}, B1-1 → {B: 1})."""
    text = str(opening_id).strip()
    if not text:
        return {}
    face = text[0].upper()
    if face.isalpha():
        return {face: 1}
    return {}


def _create_recipe_place(
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
    want_inline: bool,
    as_dir: bool,
) -> tuple[str, dict]:
    """Create destination place for socket/lamp recipes; return (leaf_id, place_map)."""
    from pathlib import Path as _Path

    from housewire.house import location_id_from_name

    raw = _Path(name)
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
        grid = _opening_grid_for(openings[0])
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
    )
    _path, staged = session.ensure_doc(index_path)
    abm.apply_set_specs(staged, set_specs, target="place")
    session.mark_dirty(index_path)
    return leaf_id, staged


def cmd_add_socket(session: ProjectSession, rest: list[str]) -> int:
    from housewire.project import recipes

    p = argparse.ArgumentParser(prog="add socket", add_help=False)
    p.add_argument("name")
    p.add_argument("--from", dest="from_ref", required=True, help="BOX.Opening")
    p.add_argument("--strip", required=True, help="TerminalStrip id in source box")
    p.add_argument("--pins", default=None, help="Strip pins L,PE,N order (default 3,2,1)")
    p.add_argument("--to-opening", default=recipes.SOCKET_DEFAULT_TO_OPENING)
    p.add_argument("--colors", default=None)
    p.add_argument("--section", default=None)
    p.add_argument("--label")
    p.add_argument("--notes")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--inline", action="store_true")
    mode.add_argument("--dir", dest="as_dir", action="store_true")
    args = p.parse_args(rest)

    parent_path, parent_doc = session.ensure_doc()
    parent_place = session.place_node(parent_doc)
    to_opening = str(args.to_opening).strip()
    leaf_id, place_map = _create_recipe_place(
        session,
        args.name,
        type_id=recipes.SOCKET_PLACE_TYPE,
        subtype=recipes.SOCKET_PLACE_SUBTYPE,
        label=args.label,
        notes=None,
        openings=[to_opening],
        opening_grid=None,
        install="surface",
        mount="wall",
        want_inline=args.inline,
        as_dir=args.as_dir,
    )
    abm.add_element(
        place_map,
        recipes.SOCKET_ELEMENT,
        type_id="Socket",
        subtype=recipes.SOCKET_ELEMENT_SUBTYPE,
        label=args.label,
        notes=args.notes,
    )
    # Outline child already marked dirty; inline shares parent_path.
    result = recipes.socket_wired_run(
        parent_place,
        place_id=leaf_id,
        from_ref=args.from_ref,
        strip=args.strip,
        pins=recipes.parse_pins(args.pins) or None,
        to_opening=to_opening,
        colors=_colors_list(args.colors) if args.colors else None,
        section=args.section,
        notes=args.notes,
    )
    session.mark_dirty(parent_path)
    print(
        f"Socket {leaf_id}: {result.cable_name} + {result.conduit_name}; "
        f"{result.from_terminals} → {result.to_terminals}"
    )
    return 0


def cmd_add_lamp(session: ProjectSession, rest: list[str]) -> int:
    from housewire.project import recipes

    p = argparse.ArgumentParser(prog="add lamp", add_help=False)
    p.add_argument("name")
    p.add_argument("--from", dest="from_ref", required=True, help="BOX.Opening")
    p.add_argument("--strip", required=True, help="TerminalStrip id in source box")
    p.add_argument("--pins", required=True, help="Strip pins (2 or 3)")
    p.add_argument("--to-pins", default=None, help="Luminaire pins (default 1,2,3 or 1,3)")
    p.add_argument("--to-opening", default=recipes.LAMP_DEFAULT_TO_OPENING)
    p.add_argument("--colors", default=None)
    p.add_argument("--section", default=None)
    p.add_argument("--label")
    p.add_argument("--notes")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--inline", action="store_true")
    mode.add_argument("--dir", dest="as_dir", action="store_true")
    args = p.parse_args(rest)

    parent_path, parent_doc = session.ensure_doc()
    parent_place = session.place_node(parent_doc)
    to_opening = str(args.to_opening).strip()
    leaf_id, place_map = _create_recipe_place(
        session,
        args.name,
        type_id=recipes.LAMP_PLACE_TYPE,
        subtype=recipes.LAMP_PLACE_SUBTYPE,
        label=args.label,
        notes=None,
        openings=[to_opening],
        opening_grid=None,
        install="surface",
        mount="ceiling",
        want_inline=args.inline,
        as_dir=args.as_dir,
    )
    abm.add_element(
        place_map,
        recipes.LAMP_ELEMENT,
        type_id="Luminaire",
        label=args.label,
        notes=args.notes,
    )
    result = recipes.lamp_wired_run(
        parent_place,
        place_id=leaf_id,
        from_ref=args.from_ref,
        strip=args.strip,
        pins=recipes.parse_pins(args.pins),
        to_pins=recipes.parse_pins(args.to_pins) or None,
        to_opening=to_opening,
        colors=_colors_list(args.colors) if args.colors else None,
        section=args.section,
        notes=args.notes,
    )
    session.mark_dirty(parent_path)
    print(
        f"Lamp {leaf_id}: {result.cable_name} + {result.conduit_name}; "
        f"{result.from_terminals} → {result.to_terminals}"
    )
    return 0


def cmd_add_feed(session: ProjectSession, rest: list[str]) -> int:
    from housewire.project import recipes

    p = argparse.ArgumentParser(prog="add feed", add_help=False)
    p.add_argument("name", help="Cable id (conduit becomes Conducto_<name>)")
    p.add_argument("--from", dest="from_ref", required=True, help="BOX.Opening")
    p.add_argument("--to", dest="to_ref", required=True, help="BOX.Opening")
    p.add_argument(
        "--from-pin",
        required=True,
        help="Electrical start, e.g. Regleta.1 or Box/Regleta.[1, 2]",
    )
    p.add_argument(
        "--to-pin",
        required=True,
        help="Electrical end, e.g. Regleta.1 or Box/Regleta.[1, 2]",
    )
    p.add_argument("--colors", default=None)
    p.add_argument("--section", default=None)
    p.add_argument("--notes")
    args = p.parse_args(rest)

    path, doc = session.ensure_doc()
    place = session.place_node(doc)
    result = recipes.feed_wired_run(
        place,
        name=args.name,
        from_opening=args.from_ref,
        to_opening=args.to_ref,
        from_pin=args.from_pin,
        to_pin=args.to_pin,
        colors=_colors_list(args.colors) if args.colors else None,
        section=args.section,
        notes=args.notes,
    )
    session.mark_dirty(path)
    print(
        f"Feed {result.cable_name} + {result.conduit_name}; "
        f"{result.from_terminals} → {result.to_terminals}"
    )
    return 0



def _parse_rm_args(argv: list[str]) -> tuple[str, list[str]]:
    if not argv:
        raise ValueError("rm requires a subcommand: element, cable, connection, file, dir")
    return argv[0], argv[1:]


def _colors_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _csv_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def normalize_set_argv(argv: list[str]) -> list[str]:
    """Rewrite ``--set KEY VALUE`` into ``--set KEY=VALUE`` (one argparse token).

    ``--set KEY=VALUE`` is left unchanged. Without this, ``--set notes "text"``
    is parsed as ``--set notes`` plus a stray positional.
    """
    out: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--set" and i + 1 < len(argv):
            spec = argv[i + 1]
            if (
                "=" not in spec
                and i + 2 < len(argv)
                and not str(argv[i + 2]).startswith("-")
            ):
                out.append("--set")
                out.append(f"{spec}={argv[i + 2]}")
                i += 3
                continue
            out.append("--set")
            out.append(spec)
            i += 2
            continue
        out.append(tok)
        i += 1
    return out


def _prompt(message: str, session: ProjectSession | None = None) -> str:
    fn = session.input_fn if session is not None else input
    return fn(message).strip()


def _confirm_unsaved(session: ProjectSession, paths: list[Path]) -> bool:
    """Ask what to do with dirty buffers. True = proceed, False = cancel."""
    if not paths:
        return True
    for path in paths:
        rel = path.relative_to(session.root)
        while True:
            ans = _prompt(
                f"Unsaved changes in {rel}. [s]ave / [d]iscard / [c]ancel: ",
                session,
            ).lower()
            if ans in {"s", "save", "g", "guardar", "y", "yes"}:
                session.save(path)
                print(f"Saved: {rel}")
                break
            if ans in {"d", "discard", "descartar", "n", "no"}:
                session.discard(path)
                print(f"Discarded: {rel}")
                break
            if ans in {"c", "cancel", "cancelar", ""}:
                return False
            print("Reply with s, d, or c.")
    return True


def cmd_ls(session: ProjectSession) -> int:
    children = session.list_location_children()
    elements = session.list_elements()
    if not children and not elements:
        print("(empty)")
        return 0
    if children:
        print("locations:")
        for child in children:
            type_bit = child.place_type or "?"
            storage_bit = " · inline" if child.storage == "inline" else ""
            print(f"  {child.name}/  ({type_bit}{storage_bit})")
    if elements:
        print("elements:")
        for name, type_id in elements:
            print(f"  {name}  ({type_id})")
    return 0


def cmd_pwd(session: ProjectSession) -> int:
    logical = "." if not session.logical_parts else "/".join(session.logical_parts)
    print(logical)
    cursor = session.cursor()
    if cursor.yaml_path:
        where = "inline" if cursor.is_inline else "dir"
        print(f"active: {cursor.yaml_path.relative_to(session.root)} ({where})")
    return 0


def cmd_show(session: ProjectSession, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="show", add_help=False)
    parser.add_argument("--element", dest="element")
    parser.add_argument("--cable", dest="cable")
    args, _ = parser.parse_known_args(argv)

    path, doc = session.ensure_doc()
    place = session.place_node(doc)
    print(abm.format_show(place, element=args.element, cable=args.cable))
    return 0


def show_file(project_path: Path, yaml_rel: Path, *, element: str | None, cable: str | None) -> int:
    path = (project_path / yaml_rel).resolve()
    doc = abm.load_editable(path, project_path)
    print(abm.format_show(doc, element=element, cable=cable))
    return 0


def _parse_pend_args(rest: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="pend", add_help=False)
    p.add_argument("positional", nargs="*")
    p.add_argument("--colors")
    p.add_argument("--subtype", default=None)
    p.add_argument("--kind", default=None, help="legacy alias of --subtype")
    p.add_argument("--label")
    p.add_argument("--notes")
    return p.parse_args(rest)


def _resolve_pend_openings(
    positional: list[str], session: ProjectSession | None = None
) -> tuple[str, str, str | None]:
    """Return (enter, exit, section_or_none) from positional args or wizard."""
    enter: str | None = None
    exit_op: str | None = None
    section: str | None = None
    if len(positional) >= 2:
        enter, exit_op = positional[0], positional[1]
        if len(positional) >= 3:
            section = positional[2]
    elif len(positional) == 1:
        raise ValueError(
            "pend requires two openings (enter and exit), e.g.: pend N1 S1"
        )
    if not enter:
        enter = _prompt("Enter opening (e.g. N1): ", session)
    if not exit_op:
        exit_op = _prompt("Exit opening (e.g. S1): ", session)
    if not enter or not exit_op:
        raise ValueError("Enter and exit openings are required")
    return enter, exit_op, section


def cmd_pend(session: ProjectSession, argv: list[str]) -> int:
    args = _parse_pend_args(argv)
    enter, exit_op, section = _resolve_pend_openings(list(args.positional), session)
    colors = _colors_list(args.colors) if args.colors else None
    path, doc = session.ensure_doc()
    cable_name, conduit_name = abm.add_pending_cable(
        session.place_node(doc),
        enter=enter,
        exit=exit_op,
        section=section,
        colors=colors,
        subtype=args.subtype or args.kind or abm.DEFAULT_CABLE_SUBTYPE,
        label=args.label,
        notes=args.notes,
    )
    session.mark_dirty(path)
    print(f"Pending {cable_name} + {conduit_name} (enter {enter} → exit {exit_op}).")
    return 0


def _iter_search_docs(session: ProjectSession) -> list[tuple[Path, dict]]:
    """Current place, ancestors, root, buffers, then all outline housewire.yaml."""
    from housewire.project.io import HOUSEWIRE_YAML
    from housewire.project.paths import is_excluded_path
    from housewire.project.session import place_node_at

    seen: set[Path] = set()
    rows: list[tuple[Path, dict]] = []

    def add(path: Path, doc: dict, inline_parts: list[str] | None = None) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        place = place_node_at(doc, inline_parts or [])
        rows.append((resolved, place))

    try:
        path, doc = session.ensure_doc()
        cursor = session.cursor()
        add(path, doc, cursor.inline_parts)
    except (ValueError, FileNotFoundError):
        pass

    parts = list(session.logical_parts)
    while parts:
        parts.pop()
        try:
            cursor = session._resolve_logical(parts)
        except (ValueError, FileNotFoundError):
            continue
        if cursor.yaml_path is None:
            continue
        path, doc = session.ensure_doc(cursor.yaml_path)
        add(path, doc, [])

    root_yaml = session.root / HOUSEWIRE_YAML
    if root_yaml.is_file() or root_yaml.resolve() in session._buffers:
        path, doc = session.ensure_doc(root_yaml)
        add(path, doc, [])

    for path, buf in session._buffers.items():
        add(path, buf.doc, [])

    # Full outline scan so claim finds OPEN_* opened in a sibling box.
    for yaml_path in session.root.rglob(HOUSEWIRE_YAML):
        if is_excluded_path(yaml_path, session._excluded):
            continue
        try:
            path, doc = session.ensure_doc(yaml_path)
        except (ValueError, OSError):
            continue
        add(path, doc, [])

    return rows


def _find_cable_doc(
    session: ProjectSession, cable_name: str
) -> tuple[Path, dict]:
    from housewire.project import open_runs

    for path, place in _iter_search_docs(session):
        if open_runs.find_cable_in_doc(place, cable_name) is not None:
            return path, place
    raise ValueError(f"Cable not found in current or ancestor YAMLs: {cable_name}")


def cmd_open(session: ProjectSession, argv: list[str]) -> int:
    from housewire.project import open_runs

    p = argparse.ArgumentParser(prog="open", add_help=False)
    p.add_argument("positional", nargs="*")
    p.add_argument("--colors")
    p.add_argument("--subtype", default=None)
    p.add_argument("--label")
    p.add_argument("--notes")
    args = p.parse_args(argv)
    positional = list(args.positional)
    if not positional:
        opening_arg = _prompt("Leave opening (e.g. S2 or Box.S2): ", session)
        section = None
    else:
        opening_arg = positional[0]
        section = positional[1] if len(positional) >= 2 else None
    if not opening_arg:
        raise ValueError("open requires an opening (e.g. S2 or Cuadro_General.S2)")

    leaves = open_runs.resolve_leave_ref(
        opening_arg,
        current_location_ref=open_runs.current_location_ref(session.logical_parts),
    )
    path, doc = session.ensure_doc()
    place = session.place_node(doc)
    cable_name = open_runs.add_open_cable(
        place,
        leaves=leaves,
        section=section,
        colors=_colors_list(args.colors) if args.colors else None,
        subtype=args.subtype or abm.DEFAULT_CABLE_SUBTYPE,
        label=args.label,
        notes=args.notes,
    )
    session.mark_dirty(path)
    print(f"Open {cable_name} leaves {leaves} (far end unknown).")
    return 0


def cmd_claim(session: ProjectSession, argv: list[str]) -> int:
    from housewire.project import open_runs

    p = argparse.ArgumentParser(prog="claim", add_help=False)
    p.add_argument("cable")
    p.add_argument("--enter", required=True, help="Opening where the run arrives")
    p.add_argument("--exit", dest="exit_op", default=None, help="Optional pass-through exit")
    args = p.parse_args(argv)

    path, place = _find_cable_doc(session, args.cable)
    enter_ref = open_runs.opening_ref_at(session.logical_parts, args.enter)
    exit_ref = (
        open_runs.opening_ref_at(session.logical_parts, args.exit_op)
        if args.exit_op
        else None
    )
    # If --enter already has a box prefix, keep it (opening_ref_at preserves it).
    conduit_name, meta = open_runs.claim_open_cable(
        place,
        args.cable,
        enter=enter_ref,
        exit=exit_ref,
    )
    session.mark_dirty(path)
    exit_bit = f", exits {meta.exits}" if meta.exits else ""
    print(
        f"Claimed {args.cable}: {conduit_name} → enters {meta.enters}{exit_bit}."
    )
    return 0


def cmd_land(session: ProjectSession, argv: list[str]) -> int:
    from housewire.project import open_runs

    p = argparse.ArgumentParser(prog="land", add_help=False)
    p.add_argument("cable")
    p.add_argument("--from", dest="from_ref", required=True)
    p.add_argument("--to", dest="to_ref", required=True)
    p.add_argument("--as", dest="as_name", default=None)
    p.add_argument("--notes")
    args = p.parse_args(argv)

    path, place = _find_cable_doc(session, args.cable)
    final = open_runs.land_open_cable(
        place,
        args.cable,
        from_ref=args.from_ref,
        to_ref=args.to_ref,
        as_name=args.as_name,
        notes=args.notes,
    )
    session.mark_dirty(path)
    print(f"Landed {final}: {args.from_ref} → {args.to_ref}.")
    return 0


def cmd_opens(session: ProjectSession, argv: list[str]) -> int:
    from housewire.project import open_runs

    del argv  # no flags yet
    found = False
    seen_names: set[str] = set()
    for path, place in _iter_search_docs(session):
        for name, meta in open_runs.list_open_cables(place):
            if name in seen_names:
                continue
            seen_names.add(name)
            found = True
            rel = path.relative_to(session.root)
            bits = [meta.status]
            if meta.leaves:
                bits.append(f"leaves {meta.leaves}")
            if meta.enters:
                bits.append(f"enters {meta.enters}")
            if meta.exits:
                bits.append(f"exits {meta.exits}")
            print(f"{name}  ({'; '.join(bits)})  [{rel}]")
    if not found:
        print("(no open runs)")
    return 0


def cmd_add(session: ProjectSession, argv: list[str]) -> int:
    kind, rest = _parse_add_args(argv)
    if kind == "dir":
        if not rest:
            raise ValueError("add dir requires a path")
        target = session.resolve_under_root(rest[0])
        target.mkdir(parents=True, exist_ok=True)
        print(f"Created: {target.relative_to(session.root)}")
        return 0
    if kind == "location":
        from pathlib import Path as _Path

        from housewire.house import location_id_from_name

        p = argparse.ArgumentParser(prog="add location", add_help=False)
        p.add_argument("name")
        p.add_argument("--type", dest="type_id", required=True)
        p.add_argument("--subtype")
        p.add_argument("--notes")
        p.add_argument("--label")
        mode = p.add_mutually_exclusive_group()
        mode.add_argument(
            "--inline",
            action="store_true",
            help="Create place under elements: of the current location",
        )
        mode.add_argument(
            "--dir",
            dest="as_dir",
            action="store_true",
            help="Create subdirectory + housewire.yaml (outline)",
        )
        p.add_argument(
            "--set",
            dest="set_specs",
            action="append",
            default=[],
            metavar="KEY=VALUE",
            help="Set place field (repeatable; KEY=VALUE or KEY VALUE)",
        )
        args = p.parse_args(normalize_set_argv(rest))
        raw = _Path(args.name)
        leaf_id, auto_label = location_id_from_name(raw.name)
        label = args.label or auto_label
        cursor = session.cursor()
        want_inline = args.inline or (not args.as_dir and cursor.is_inline)
        if args.as_dir and cursor.is_inline:
            raise ValueError(
                "Cannot create location --dir under an inline place. "
                "cd to the parent outline or use --inline."
            )
        if want_inline:
            if str(raw.parent) not in (".", ""):
                raise ValueError(
                    "add location --inline only accepts a leaf name "
                    "(no path); cd to the parent location first"
                )
            path, doc = session.ensure_doc()
            place = session.place_node(doc)
            # Collision with outline sibling
            for child in session.list_location_children():
                if child.name == leaf_id and child.storage == "dir":
                    raise ValueError(
                        f"Outline location {leaf_id!r} already exists; "
                        "cannot create the same id inline"
                    )
            entry = create_inline_location(
                place,
                leaf_id,
                type_id=args.type_id,
                subtype=args.subtype,
                notes=args.notes,
                label=label,
            )
            if args.set_specs:
                abm.apply_set_specs(entry, args.set_specs, target="place")
            session.mark_dirty(path)
            session.cd(leaf_id)
            print(f"Inline location created: {'/'.join(session.logical_parts)} (in memory → save)")
            return 0

        rel = raw.parent / leaf_id if str(raw.parent) not in (".", "") else _Path(leaf_id)
        # Collision with inline sibling at current place
        for child in session.list_location_children():
            if child.name == leaf_id and child.storage == "inline":
                raise ValueError(
                    f"Inline location {leaf_id!r} already exists; "
                    "cannot create the same id as a folder"
                )
        target = session.resolve_under_root(str(rel))
        index_path = session.stage_outline_location(
            target,
            type_id=args.type_id,
            subtype=args.subtype,
            notes=args.notes,
            label=label,
        )
        if args.set_specs:
            _path, staged = session.ensure_doc(index_path)
            abm.apply_set_specs(staged, args.set_specs, target="place")
            session.mark_dirty(index_path)
        # Move logical cwd to the new outline location.
        session.logical_parts = list(session.logical_parts) + list(rel.parts)
        session._sync_from_logical()
        session.active_yaml = index_path
        print(
            f"Outline location created: {index_path.relative_to(session.root)} "
            f"(in memory → save)"
        )
        return 0
    if kind == "pend":
        return cmd_pend(session, rest)
    if kind == "socket":
        return cmd_add_socket(session, rest)
    if kind == "lamp":
        return cmd_add_lamp(session, rest)
    if kind == "feed":
        return cmd_add_feed(session, rest)
    path, doc = session.ensure_doc()
    place = session.place_node(doc)
    if kind == "element":
        p = argparse.ArgumentParser(prog="add element", add_help=False)
        p.add_argument("name")
        p.add_argument("--type", required=True)
        p.add_argument("--subtype")
        p.add_argument("--manufacturer")
        p.add_argument("--model")
        p.add_argument("--label")
        p.add_argument("--notes")
        p.add_argument(
            "--set",
            dest="set_specs",
            action="append",
            default=[],
            metavar="KEY=VALUE",
            help="Set element field (repeatable; KEY=VALUE or KEY VALUE)",
        )
        args = p.parse_args(normalize_set_argv(rest))
        abm.add_element(
            place,
            args.name,
            type_id=args.type,
            subtype=args.subtype,
            manufacturer=args.manufacturer,
            model=args.model,
            label=args.label,
            notes=args.notes,
        )
        if args.set_specs:
            entry = place["elements"][args.name]
            abm.apply_set_specs(entry, args.set_specs, target="element")
        session.mark_dirty(path)
        print(f"Element {args.name} added.")
        return 0
    if kind == "cable":
        p = argparse.ArgumentParser(prog="add cable", add_help=False)
        p.add_argument("name")
        p.add_argument("--section", default=None)
        p.add_argument("--colors", default=None)
        p.add_argument("--subtype", default=None)
        p.add_argument("--kind", default=None, help="legacy alias of --subtype")
        p.add_argument("--label")
        p.add_argument("--notes")
        args = p.parse_args(rest)
        abm.add_cable(
            place,
            args.name,
            subtype=args.subtype or args.kind or abm.DEFAULT_CABLE_SUBTYPE,
            section=args.section,
            colors=_colors_list(args.colors) if args.colors else None,
            label=args.label,
            notes=args.notes,
        )
        session.mark_dirty(path)
        print(f"Cable {args.name} added.")
        return 0
    if kind == "conduit":
        p = argparse.ArgumentParser(prog="add conduit", add_help=False)
        p.add_argument("name")
        p.add_argument("--from", dest="from_ref", required=True, help="LocationRef.OpeningId")
        p.add_argument("--to", dest="to_ref", required=True, help="LocationRef.OpeningId")
        p.add_argument(
            "--contains",
            required=True,
            help="Cable ids in this YAML, comma-separated",
        )
        p.add_argument("--subtype", default=abm.DEFAULT_CONDUIT_SUBTYPE)
        p.add_argument("--label")
        p.add_argument("--notes")
        args = p.parse_args(rest)
        contains = _csv_list(args.contains)
        if not contains:
            raise ValueError("--contains cannot be empty")
        abm.add_conduit(
            place,
            args.name,
            contains=contains,
            from_ref=args.from_ref,
            to_ref=args.to_ref,
            subtype=args.subtype,
            label=args.label,
            notes=args.notes,
        )
        session.mark_dirty(path)
        print(f"Conduit {args.name} added.")
        return 0
    if kind == "connection":
        p = argparse.ArgumentParser(prog="add connection", add_help=False)
        p.add_argument("--from", dest="from_ref", required=True)
        p.add_argument("--via", dest="via_ref", required=True)
        p.add_argument("--to", dest="to_ref", required=True)
        args = p.parse_args(rest)
        abm.add_connection(
            place, from_ref=args.from_ref, via_ref=args.via_ref, to_ref=args.to_ref
        )
        session.mark_dirty(path)
        print("Connection added.")
        return 0
    raise ValueError(f"Unknown add kind: {kind}")


def cmd_rm(session: ProjectSession, argv: list[str]) -> int:
    kind, rest = _parse_rm_args(argv)
    if kind == "dir":
        if not rest:
            raise ValueError("rm dir requires a path")
        target = session.resolve_under_root(rest[0])
        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {rest[0]}")
        if any(target.iterdir()):
            raise ValueError("rm dir: directory is not empty")
        target.rmdir()
        print(f"Deleted: {target.relative_to(session.root)}")
        return 0
    if kind == "file":
        if not rest:
            raise ValueError("rm file requires a name")
        target = session.resolve_under_root(rest[0])
        if session.active_yaml and target.resolve() == session.active_yaml.resolve():
            session.active_yaml = None
        target.unlink()
        print(f"Deleted: {target.relative_to(session.root)}")
        return 0
    path, doc = session.ensure_doc()
    place = session.place_node(doc)
    if kind == "element":
        if not rest:
            raise ValueError("rm element requires NAME")
        abm.rm_element(place, rest[0])
        session.mark_dirty(path)
        print(f"Element {rest[0]} deleted.")
        return 0
    if kind == "cable":
        if not rest:
            raise ValueError("rm cable requires NAME")
        abm.rm_cable(place, rest[0])
        session.mark_dirty(path)
        print(f"Cable {rest[0]} deleted.")
        return 0
    if kind == "connection":
        if not rest:
            raise ValueError("rm connection requires an index")
        abm.rm_connection(place, int(rest[0]))
        session.mark_dirty(path)
        print(f"Connection [{rest[0]}] deleted.")
        return 0
    raise ValueError(f"Unknown rm kind: {kind}")


def cmd_cd(session: ProjectSession, argv: list[str]) -> int:
    raw = argv[0] if argv else None
    # Dirty buffers stay in memory across YAML boundaries; save/discard on exit
    # or explicit ``save`` / ``reload``.
    session.cd(raw)
    if session.housewire_yaml_in_cwd() is None and str(session.cwd) != ".":
        print(
            f"Warning: no {HOUSEWIRE_YAML} here (not a location). "
            f"cd to a location or: add location …",
            file=sys.stderr,
        )
    return 0


def cmd_set(session: ProjectSession, argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="set", add_help=False)
    p.add_argument("--element", "-e", dest="element")
    p.add_argument("tokens", nargs="+")
    args = p.parse_args(argv)
    tokens = list(args.tokens)
    path, doc = session.ensure_doc()
    place = session.place_node(doc)
    if args.element:
        elements = place.get("elements") or {}
        if not isinstance(elements, dict) or args.element not in elements:
            raise ValueError(f"Element does not exist: {args.element}")
        target_map = elements[args.element]
        if not isinstance(target_map, dict):
            raise ValueError(f"Invalid element: {args.element}")
        target_kind: abm.SetTarget = "element"
        where = f"element {args.element}"
    else:
        target_map = place
        target_kind = "place"
        where = "place"

    # Forms: KEY=VALUE | KEY VALUE… | KEY (unset).
    # Re-join tokens so YAML with spaces works: openings=[W1, S2, E1]
    if "=" in tokens[0]:
        key, value = abm.parse_set_spec(" ".join(tokens))
        if value is None:
            raise ValueError("Use unset KEY or set KEY=VALUE")
        abm.set_field(target_map, key, value, target=target_kind)
        print(f"Set {where}: {key}={value!r}")
    elif len(tokens) == 1:
        abm.unset_field(target_map, tokens[0])
        print(f"Unset {where}: {tokens[0]}")
    else:
        key = tokens[0]
        value = abm.parse_set_value(" ".join(tokens[1:]))
        abm.set_field(target_map, key, value, target=target_kind)
        print(f"Set {where}: {key}={value!r}")
    session.mark_dirty(path)
    return 0


def cmd_unset(session: ProjectSession, argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="unset", add_help=False)
    p.add_argument("--element", "-e", dest="element")
    p.add_argument("key")
    args = p.parse_args(argv)
    path, doc = session.ensure_doc()
    place = session.place_node(doc)
    if args.element:
        elements = place.get("elements") or {}
        if not isinstance(elements, dict) or args.element not in elements:
            raise ValueError(f"Element does not exist: {args.element}")
        target_map = elements[args.element]
        if not isinstance(target_map, dict):
            raise ValueError(f"Invalid element: {args.element}")
        where = f"element {args.element}"
    else:
        target_map = place
        where = "place"
    abm.unset_field(target_map, args.key)
    session.mark_dirty(path)
    print(f"Unset {where}: {args.key}")
    return 0


def cmd_save(session: ProjectSession, argv: list[str]) -> int:
    force = "--force" in argv or "-f" in argv
    dirty = session.dirty_paths()
    if not dirty:
        print("Nothing to save.")
        return 0
    for path in dirty:
        session.save(path, force=force)
        print(f"Saved: {path.relative_to(session.root)}")
    return 0


def cmd_reload(session: ProjectSession, argv: list[str]) -> int:
    if session.is_dirty():
        ans = _prompt(
            "Unsaved changes. Discard and reload? [y/N]: ", session
        ).lower()
        if ans not in {"s", "y", "yes", "si", "sí"}:
            print("reload cancelled.")
            return 0
    path = session.reload()
    print(f"Reloaded: {path.relative_to(session.root)}")
    return 0


def request_leave(session: ProjectSession) -> bool:
    """Return True if the shell may exit (saved/discarded or clean)."""
    return _confirm_unsaved(session, session.dirty_paths())


def run_shell_line(session: ProjectSession, line: str, *, generate_fn) -> int | None:
    line = line.strip()
    if not line:
        return None
    try:
        parts = shlex.split(line)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    cmd = parts[0]
    args = parts[1:]
    try:
        if cmd in {"exit", "quit"}:
            return -1
        if cmd == "help":
            print(HELP_TEXT.rstrip())
            return 0
        if cmd == "version":
            from housewire import __version__

            print(f"housewire {__version__}")
            return 0
        if cmd == "pwd":
            return cmd_pwd(session)
        if cmd == "ls":
            return cmd_ls(session)
        if cmd == "cd":
            return cmd_cd(session, args)
        if cmd == "use":
            if not args:
                raise ValueError("use requires <file.yaml>")
            session.use_yaml(args[0])
            print(f"Active: {session.active_yaml.relative_to(session.root)}")
            return 0
        if cmd == "show":
            return cmd_show(session, args)
        if cmd == "pend":
            return cmd_pend(session, args)
        if cmd == "open":
            return cmd_open(session, args)
        if cmd == "claim":
            return cmd_claim(session, args)
        if cmd == "land":
            return cmd_land(session, args)
        if cmd == "opens":
            return cmd_opens(session, args)
        if cmd == "add":
            return cmd_add(session, args)
        if cmd == "set":
            return cmd_set(session, args)
        if cmd == "unset":
            return cmd_unset(session, args)
        if cmd == "rm":
            return cmd_rm(session, args)
        if cmd == "save":
            return cmd_save(session, args)
        if cmd == "reload":
            return cmd_reload(session, args)
        if cmd == "generate":
            force = "-f" in args or "--force" in args
            dirty = session.dirty_paths()
            if dirty:
                print(f"Saving {len(dirty)} dirty YAML before generate…")
                session.save_all()
            return generate_fn(session.cwd_path(), force=force)
        print(f"Unknown command: {cmd}. Type help.", file=sys.stderr)
        return 1
    except (ValueError, FileNotFoundError, FileExistsError, NotADirectoryError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
