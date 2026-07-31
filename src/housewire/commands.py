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
  pwd                          logical location path and host YAML (* = dirty)
  cd [path]                    navigate locations (outline folder or inline place)
  ls                           child locations (outline+inline) and elements (non-place)
  use housewire.yaml           set active housewire.yaml for the current location
  show                         current place: electrical layer + physical layer
  show --element NAME | --cable NAME
  pend [<enter> <exit>] [section] [--colors C1,C2] [--notes ...]
                               pending cable + conduit from/to (.N1 → .S1)
  set KEY VALUE | set KEY=VALUE
                               property of the current place (YAML; memory → save)
                               nested: opening_grid.N=1
  set --element NAME KEY VALUE property of an element in the place
  unset KEY | unset --element NAME KEY
  add location NAME --type T [--subtype ...] [--label ...] [--notes ...]
                               [--inline | --dir] [--set KEY=VALUE ...]
                               T=Room|JunctionBox|DeviceBox|LightPoint|Panel|Floor|House
                               default: outline if you are in outline; inline if you are inline
                               (memory → save; outline creates folder on save)
                               NAME with spaces → technical id + automatic label
  add element NAME --type T … [--set KEY=VALUE …]  (memory → save)
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
  save [--force]                 write dirty YAML to disk (validate)
  reload                         discard buffer and re-read from disk
  generate [-f]                save dirty and generate the tree for cwd
                               physical=locations↔conduits; WireViz=elements↔cables
  version                      program version
  help
  exit | quit                  warns if there are unsaved changes
  (multi-line)                 end the line with \\ and continue on the next
"""


def _parse_add_args(argv: list[str]) -> tuple[str, list[str]]:
    if not argv:
        raise ValueError(
            "add requires a subcommand: location, element, cable, conduit, pend, connection, dir"
        )
    return argv[0], argv[1:]


def _parse_rm_args(argv: list[str]) -> tuple[str, list[str]]:
    if not argv:
        raise ValueError("rm requires a subcommand: element, cable, connection, file, dir")
    return argv[0], argv[1:]


def _colors_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _csv_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


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
            help="Set place field (repeatable; YAML value)",
        )
        args = p.parse_args(rest)
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
            help="Set element field (repeatable; YAML value)",
        )
        args = p.parse_args(rest)
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
    current = session.cursor()
    preview = session.preview_cd(raw)
    cur_yaml = current.yaml_path.resolve() if current.yaml_path else None
    new_yaml = preview.yaml_path.resolve() if preview.yaml_path else None
    if cur_yaml is not None and cur_yaml != new_yaml and session.is_dirty(cur_yaml):
        if not _confirm_unsaved(session, [cur_yaml]):
            print("cd cancelled.")
            return 0
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
