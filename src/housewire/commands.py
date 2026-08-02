from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from housewire.site import abm
from housewire.site.io import create_inline_location
from housewire.site.session import SiteSession

if TYPE_CHECKING:
    pass

HELP_TEXT = """HouseWire shell commands:
  (Tab completes commands, add/rm subcommands, and cd/use/… paths)
  pwd                          logical location path and host YAML (* = any dirty buffer)
  cd [path]                    navigate nested places under elements:;
                               dirty YAML stay in memory (no save prompt on cd)
  ls                           child places and elements (non-place)
  use <site.yaml>              activate a site YAML at the site root
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
  add location NAME --type T [--subtype ...] [--name ...] [--label ...] [--notes ...]
                               [--set KEY=VALUE | --set KEY VALUE …]
                               T=Room|Stair|JunctionBox|DeviceBox|LightPoint|Panel|Floor|House
                               nests under current place elements: (memory → save)
                               NAME with spaces → technical id + automatic label
                               --name = short working name (canvas); --label = human text
  add socket NAME --from BOX.Op --strip ELEMENT [--pins 3,2,1]
                               [--to-opening N1] [--colors GY,GNYE,BU] [--section 2.5]
                               [--label ...] [--notes …]
                               DeviceBox+Socket + Cable/Conductor+Conduit (run from parent)
  add lamp NAME --from BOX.Op --strip ELEMENT --pins P1,P2[,P3]
                               [--to-pins 1,2,3] [--to-opening B1-1]
                               [--colors BN,GNYE,BU] [--section 1.5]
                               [--label ...] [--notes …]
                               LightPoint+Luminaire + Cable/Conductor+Conduit
  add feed NAME --from BOX.Op --to BOX2.Op --from-pin PATH --to-pin PATH
                               [--colors BN,BU] [--section 1.5] [--notes …]
                               Cable/Conductor+Conduit between existing places
  add element NAME --type T … [--set KEY=VALUE | --set KEY VALUE …]  (memory → save)
  add cable NAME …             sheath or conductor into cables: (memory → save)
  add conductor NAME --from A --to B [--color BN] …
                               leaf Conductor in cables: (memory → save)
  add conduit NAME --from A.Op --to B.Op --contains C1[,C2…]
                               [--subtype tube] [--label ...] [--notes …]
                               Conduit entry in cables: (memory → save)
  add pend …
  add dir <path>                 mkdir -p (prefer add location for places)
  rm element|cable NAME
  rm file <site.yaml>
  rm dir <path>                  only if empty
  save [--force]                 write all dirty YAML to disk (validate)
  reload                         discard current buffer and re-read from disk
  version                      program version
  help
  exit | quit                  prompts to save/discard each dirty YAML
  (multi-line)                 end the line with \\ and continue on the next
"""


def _parse_add_args(argv: list[str]) -> tuple[str, list[str]]:
    if not argv:
        raise ValueError(
            "add requires a subcommand: location, element, cable, conductor, "
            "conduit, pend, socket, lamp, feed, dir"
        )
    return argv[0], argv[1:]


def _opening_grid_for(opening_id: str) -> dict[str, int]:
    from housewire.site.recipe_actions import opening_grid_for

    return opening_grid_for(opening_id)


def _create_recipe_place(
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
) -> tuple[str, dict]:
    from housewire.site.recipe_actions import create_recipe_place

    del want_inline, as_dir
    return create_recipe_place(
        session,
        name,
        type_id=type_id,
        subtype=subtype,
        label=label,
        notes=notes,
        openings=openings,
        opening_grid=opening_grid,
        install=install,
        mount=mount,
    )


def cmd_add_socket(session: SiteSession, rest: list[str]) -> int:
    from housewire.site import recipes
    from housewire.site.recipe_actions import run_socket_recipe

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
    args = p.parse_args(rest)

    result = run_socket_recipe(
        session,
        name=args.name,
        from_ref=args.from_ref,
        strip=args.strip,
        pins=args.pins,
        to_opening=args.to_opening,
        colors=args.colors,
        section=args.section,
        label=args.label,
        notes=args.notes,
    )
    print(
        f"Socket {result['place_id']}: {result['cable_name']} + {result['conduit_name']}; "
        f"{result['from_terminals']} → {result['to_terminals']}"
    )
    return 0


def cmd_add_lamp(session: SiteSession, rest: list[str]) -> int:
    from housewire.site import recipes
    from housewire.site.recipe_actions import run_lamp_recipe

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
    args = p.parse_args(rest)

    result = run_lamp_recipe(
        session,
        name=args.name,
        from_ref=args.from_ref,
        strip=args.strip,
        pins=args.pins,
        to_pins=args.to_pins,
        to_opening=args.to_opening,
        colors=args.colors,
        section=args.section,
        label=args.label,
        notes=args.notes,
    )
    print(
        f"Lamp {result['place_id']}: {result['cable_name']} + {result['conduit_name']}; "
        f"{result['from_terminals']} → {result['to_terminals']}"
    )
    return 0


def cmd_add_feed(session: SiteSession, rest: list[str]) -> int:
    from housewire.site.recipe_actions import run_feed_recipe

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

    result = run_feed_recipe(
        session,
        name=args.name,
        from_ref=args.from_ref,
        to_ref=args.to_ref,
        from_pin=args.from_pin,
        to_pin=args.to_pin,
        colors=args.colors,
        section=args.section,
        notes=args.notes,
    )
    print(
        f"Feed {result['cable_name']} + {result['conduit_name']}; "
        f"{result['from_terminals']} → {result['to_terminals']}"
    )
    return 0



def _parse_rm_args(argv: list[str]) -> tuple[str, list[str]]:
    if not argv:
        raise ValueError("rm requires a subcommand: element, cable, file, dir")
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


def _prompt(message: str, session: SiteSession | None = None) -> str:
    fn = session.input_fn if session is not None else input
    return fn(message).strip()


def _confirm_unsaved(session: SiteSession, paths: list[Path]) -> bool:
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


def cmd_ls(session: SiteSession) -> int:
    children = session.list_location_children()
    elements = session.list_elements()
    if not children and not elements:
        print("(empty)")
        return 0
    if children:
        print("locations:")
        for child in children:
            type_bit = child.place_type or "?"
            print(f"  {child.name}/  ({type_bit})")
    if elements:
        print("elements:")
        for name, type_id in elements:
            print(f"  {name}  ({type_id})")
    return 0


def cmd_pwd(session: SiteSession) -> int:
    logical = "." if not session.logical_parts else "/".join(session.logical_parts)
    print(logical)
    cursor = session.cursor()
    if cursor.yaml_path:
        print(f"active: {cursor.yaml_path.relative_to(session.root)}")
    return 0


def cmd_show(session: SiteSession, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="show", add_help=False)
    parser.add_argument("--element", dest="element")
    parser.add_argument("--cable", dest="cable")
    args, _ = parser.parse_known_args(argv)

    path, doc = session.ensure_doc()
    place = session.place_node(doc)
    print(abm.format_show(place, element=args.element, cable=args.cable))
    return 0


def show_file(site_path: Path, yaml_rel: Path, *, element: str | None, cable: str | None) -> int:
    path = (site_path / yaml_rel).resolve()
    doc = abm.load_editable(path, site_path)
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
    positional: list[str], session: SiteSession | None = None
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


def cmd_pend(session: SiteSession, argv: list[str]) -> int:
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


def _iter_search_docs(session: SiteSession) -> list[tuple[Path, dict]]:
    """Current place and ancestor places inside the single site document."""
    from housewire.site.session import place_node_at

    seen: set[tuple[str, ...]] = set()
    rows: list[tuple[Path, dict]] = []

    try:
        path, doc = session.ensure_doc()
    except (ValueError, FileNotFoundError):
        return rows

    def add(parts: list[str]) -> None:
        key = tuple(parts)
        if key in seen:
            return
        seen.add(key)
        place = place_node_at(doc, parts)
        rows.append((path, place))

    add(list(session.logical_parts))
    parts = list(session.logical_parts)
    while parts:
        parts.pop()
        add(parts)
    return rows


def _find_cable_doc(
    session: SiteSession, cable_name: str
) -> tuple[Path, dict]:
    from housewire.site import open_runs

    for path, place in _iter_search_docs(session):
        if open_runs.find_cable_in_doc(place, cable_name) is not None:
            return path, place
    raise ValueError(f"Cable not found in current or ancestor YAMLs: {cable_name}")


def cmd_open(session: SiteSession, argv: list[str]) -> int:
    from housewire.site import open_runs

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


def cmd_claim(session: SiteSession, argv: list[str]) -> int:
    from housewire.site import open_runs

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


def cmd_land(session: SiteSession, argv: list[str]) -> int:
    from housewire.site import open_runs

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


def cmd_opens(session: SiteSession, argv: list[str]) -> int:
    from housewire.site import open_runs

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


def cmd_add(session: SiteSession, argv: list[str]) -> int:
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
        p.add_argument(
            "--name",
            dest="working_name",
            help="Short working name for canvas/lists (YAML name:)",
        )
        p.add_argument("--label", help="Human-readable label (YAML label:)")
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
        if str(raw.parent) not in (".", ""):
            raise ValueError(
                "add location only accepts a leaf name "
                "(no path); cd to the parent location first"
            )
        leaf_id, auto_label = location_id_from_name(raw.name)
        label = args.label or auto_label
        working_name = args.working_name
        path, doc = session.ensure_doc()
        place = session.place_node(doc)
        for child in session.list_location_children():
            if child.name == leaf_id:
                raise ValueError(f"Location already exists: {leaf_id}")
        entry = create_inline_location(
            place,
            leaf_id,
            type_id=args.type_id,
            subtype=args.subtype,
            notes=args.notes,
            label=label,
            working_name=working_name,
        )
        if args.set_specs:
            abm.apply_set_specs(entry, args.set_specs, target="place")
        session.mark_dirty(path)
        session.cd(leaf_id)
        print(
            f"Location created: {'/'.join(session.logical_parts)} (in memory → save)"
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
        p.add_argument("--colors", default=None, help="One or more colors → sheath+conductors")
        p.add_argument("--color", default=None, help="Single conductor color")
        p.add_argument("--from", dest="from_ref", default=None)
        p.add_argument("--to", dest="to_ref", default=None)
        p.add_argument("--subtype", default=None)
        p.add_argument("--kind", default=None, help="legacy alias of --subtype")
        p.add_argument("--label")
        p.add_argument("--notes")
        args = p.parse_args(rest)
        subtype = args.subtype or args.kind or abm.DEFAULT_CABLE_SUBTYPE
        colors = _colors_list(args.colors) if args.colors else None
        if colors and len(colors) > 1:
            conductor_ids: list[str] = []
            for index, col in enumerate(colors, start=1):
                cid = f"{args.name}_{index}"
                abm.add_conductor(
                    place,
                    cid,
                    subtype=subtype,
                    section=args.section,
                    color=col,
                    label=args.label,
                    notes=args.notes,
                )
                conductor_ids.append(cid)
            abm.add_sheath(
                place,
                args.name,
                contains=conductor_ids,
                subtype=subtype,
                section=args.section,
                label=args.label,
                notes=args.notes,
            )
        else:
            color = args.color or (colors[0] if colors else None)
            abm.add_conductor(
                place,
                args.name,
                subtype=subtype,
                section=args.section,
                color=color,
                from_ref=args.from_ref,
                to_ref=args.to_ref,
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
    if kind == "conductor":
        p = argparse.ArgumentParser(prog="add conductor", add_help=False)
        p.add_argument("name")
        p.add_argument("--from", dest="from_ref", required=True)
        p.add_argument("--to", dest="to_ref", required=True)
        p.add_argument("--color", required=True)
        p.add_argument("--section", default=None)
        p.add_argument("--subtype", default=None)
        p.add_argument("--label")
        p.add_argument("--notes")
        args = p.parse_args(rest)
        abm.add_conductor(
            place,
            args.name,
            from_ref=args.from_ref,
            to_ref=args.to_ref,
            color=args.color,
            section=args.section,
            subtype=args.subtype or abm.DEFAULT_CABLE_SUBTYPE,
            label=args.label,
            notes=args.notes,
        )
        session.mark_dirty(path)
        print(f"Conductor {args.name} added.")
        return 0
    if kind == "connection":
        raise ValueError(
            "add connection is removed in house/v2; "
            "use add conductor --from … --to … --color …"
        )
    raise ValueError(f"Unknown add kind: {kind}")


def cmd_rm(session: SiteSession, argv: list[str]) -> int:
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
        raise ValueError(
            "rm connection is removed in house/v2; "
            "use rm cable <ConductorOrSheathId>"
        )
    raise ValueError(f"Unknown rm kind: {kind}")


def cmd_cd(session: SiteSession, argv: list[str]) -> int:
    raw = argv[0] if argv else None
    # Dirty buffers stay in memory across YAML boundaries; save/discard on exit
    # or explicit ``save`` / ``reload``.
    session.cd(raw)
    return 0


def cmd_set(session: SiteSession, argv: list[str]) -> int:
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


def cmd_unset(session: SiteSession, argv: list[str]) -> int:
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


def cmd_save(session: SiteSession, argv: list[str]) -> int:
    force = "--force" in argv or "-f" in argv
    dirty = session.dirty_paths()
    if not dirty:
        print("Nothing to save.")
        return 0
    for path in dirty:
        session.save(path, force=force)
        print(f"Saved: {path.relative_to(session.root)}")
    return 0


def cmd_reload(session: SiteSession, argv: list[str]) -> int:
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


def request_leave(session: SiteSession) -> bool:
    """Return True if the shell may exit (saved/discarded or clean)."""
    return _confirm_unsaved(session, session.dirty_paths())


def run_shell_line(session: SiteSession, line: str) -> int | None:
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
            from housewire import __title__, __version__

            print(f"{__title__} {__version__}")
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
        print(f"Unknown command: {cmd}. Type help.", file=sys.stderr)
        return 1
    except (ValueError, FileNotFoundError, FileExistsError, NotADirectoryError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
