from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from housewire.project import abm
from housewire.project.io import HOUSEWIRE_YAML, create_inline_location, create_location_index
from housewire.project.session import ProjectSession

if TYPE_CHECKING:
    pass

HELP_TEXT = """Comandos del shell housewire:
  (Tab completa comandos, subcomandos add/rm y rutas de cd/use/…)
  pwd                          path lógico de location y YAML anfitrión (* = dirty)
  cd [path]                    navegar locations (carpeta outline o place inline)
  ls                           locations hijas (outline+inline) y elements (no-place)
  use housewire.yaml           fijar housewire.yaml activo de la location actual
  show                         place actual (type/label) + elements/cables/…
  show --element NAME | --cable NAME
  pend [<enter> <exit>] [section] [--colors C1,C2] [--notes ...]
                               cable pendiente + conduit (atajo de add pend)
  add location NAME --type T [--subtype ...] [--label ...] [--notes ...]
                               [--inline | --dir]
                               default: outline si estás en outline; inline si estás inline
                               NAME con espacios → id tecnico + label automatico
  add element NAME --type T [--subtype ...] [--label ...] [--manufacturer ...] [--model ...] [--notes ...]
  add cable NAME [--section S] [--colors C1,C2] [--subtype power] [--label ...] [--notes ...]
                               (--kind es alias legacy de --subtype)
                               defaults: section=1.5 mm2, colors=BN,BU
  add pend [<enter> <exit>] [section] [--colors ...] [--notes ...]
  add connection --from F --via V --to T
  add dir <path>                 mkdir -p (sin housewire.yaml; preferible add location)
  rm element|cable NAME
  rm connection <índice>
  rm file housewire.yaml
  rm dir <path>                  solo si está vacío
  save [--force]                 escribir YAML dirty a disco (validate)
  reload                         descartar buffer y releer disco
  generate [-f]                guardar dirty y generar diagramas
  version                      version del programa
  help
  exit | quit                  avisa si hay cambios sin guardar
"""


def _parse_add_args(argv: list[str]) -> tuple[str, list[str]]:
    if not argv:
        raise ValueError(
            "add requiere subcomando: location, element, cable, pend, connection, dir"
        )
    return argv[0], argv[1:]


def _parse_rm_args(argv: list[str]) -> tuple[str, list[str]]:
    if not argv:
        raise ValueError("rm requiere subcomando: element, cable, connection, file, dir")
    return argv[0], argv[1:]


def _colors_list(raw: str) -> list[str]:
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
                f"Cambios sin guardar en {rel}. [g]uardar / [d]escartar / [c]ancelar: ",
                session,
            ).lower()
            if ans in {"g", "guardar", "s", "y", "yes"}:
                session.save(path)
                print(f"Guardado: {rel}")
                break
            if ans in {"d", "descartar", "n", "no"}:
                session.discard(path)
                print(f"Descartado: {rel}")
                break
            if ans in {"c", "cancelar", ""}:
                return False
            print("Responde g, d o c.")
    return True


def cmd_ls(session: ProjectSession) -> int:
    children = session.list_location_children()
    elements = session.list_elements()
    if not children and not elements:
        print("(vacío)")
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
    p.add_argument("--kind", default=None, help="alias legacy de --subtype")
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
            "pend requiere dos aberturas (entrada y salida), p.ej.: pend N1 S1"
        )
    if not enter:
        enter = _prompt("Abertura entrada (p.ej. N1): ", session)
    if not exit_op:
        exit_op = _prompt("Abertura salida (p.ej. S1): ", session)
    if not enter or not exit_op:
        raise ValueError("Aberturas entrada y salida son obligatorias")
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
    print(f"Pendiente {cable_name} + {conduit_name} (entra {enter} → sale {exit_op}).")
    return 0


def cmd_add(session: ProjectSession, argv: list[str]) -> int:
    kind, rest = _parse_add_args(argv)
    if kind == "dir":
        if not rest:
            raise ValueError("add dir requiere ruta")
        target = session.resolve_under_root(rest[0])
        target.mkdir(parents=True, exist_ok=True)
        print(f"Creado: {target.relative_to(session.root)}")
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
        args = p.parse_args(rest)
        raw = _Path(args.name)
        leaf_id, auto_label = location_id_from_name(raw.name)
        label = args.label or auto_label
        cursor = session.cursor()
        want_inline = args.inline or (not args.as_dir and cursor.is_inline)
        if args.as_dir and cursor.is_inline:
            raise ValueError(
                "No se puede crear location --dir bajo un place inline. "
                "cd al outline padre o usa --inline."
            )
        if want_inline:
            if str(raw.parent) not in (".", ""):
                raise ValueError(
                    "add location --inline solo acepta un nombre hoja "
                    "(sin path); cd primero a la location padre"
                )
            path, doc = session.ensure_doc()
            place = session.place_node(doc)
            # Collision with outline sibling
            for child in session.list_location_children():
                if child.name == leaf_id and child.storage == "dir":
                    raise ValueError(
                        f"Ya existe location outline {leaf_id!r}; "
                        "no se puede crear el mismo id inline"
                    )
            create_inline_location(
                place,
                leaf_id,
                type_id=args.type_id,
                subtype=args.subtype,
                notes=args.notes,
                label=label,
            )
            session.mark_dirty(path)
            session.cd(leaf_id)
            print(f"Location inline creada: {'/'.join(session.logical_parts)}")
            return 0

        rel = raw.parent / leaf_id if str(raw.parent) not in (".", "") else _Path(leaf_id)
        # Collision with inline sibling at current place
        for child in session.list_location_children():
            if child.name == leaf_id and child.storage == "inline":
                raise ValueError(
                    f"Ya existe location inline {leaf_id!r}; "
                    "no se puede crear el mismo id como carpeta"
                )
        target = session.resolve_under_root(str(rel))
        index_path = create_location_index(
            target,
            type_id=args.type_id,
            subtype=args.subtype,
            notes=args.notes,
            label=label,
        )
        # Move logical cwd to the new outline location.
        session.logical_parts = list(session.logical_parts) + list(rel.parts)
        session._sync_from_logical()
        session.active_yaml = index_path
        print(f"Location creada: {index_path.relative_to(session.root)}")
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
        session.mark_dirty(path)
        print(f"Elemento {args.name} añadido.")
        return 0
    if kind == "cable":
        p = argparse.ArgumentParser(prog="add cable", add_help=False)
        p.add_argument("name")
        p.add_argument("--section", default=None)
        p.add_argument("--colors", default=None)
        p.add_argument("--subtype", default=None)
        p.add_argument("--kind", default=None, help="alias legacy de --subtype")
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
        print(f"Cable {args.name} añadido.")
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
        print("Conexión añadida.")
        return 0
    raise ValueError(f"add desconocido: {kind}")


def cmd_rm(session: ProjectSession, argv: list[str]) -> int:
    kind, rest = _parse_rm_args(argv)
    if kind == "dir":
        if not rest:
            raise ValueError("rm dir requiere ruta")
        target = session.resolve_under_root(rest[0])
        if not target.is_dir():
            raise NotADirectoryError(f"No es directorio: {rest[0]}")
        if any(target.iterdir()):
            raise ValueError("rm dir: el directorio no está vacío")
        target.rmdir()
        print(f"Borrado: {target.relative_to(session.root)}")
        return 0
    if kind == "file":
        if not rest:
            raise ValueError("rm file requiere nombre")
        target = session.resolve_under_root(rest[0])
        if session.active_yaml and target.resolve() == session.active_yaml.resolve():
            session.active_yaml = None
        target.unlink()
        print(f"Borrado: {target.relative_to(session.root)}")
        return 0
    path, doc = session.ensure_doc()
    place = session.place_node(doc)
    if kind == "element":
        if not rest:
            raise ValueError("rm element requiere NAME")
        abm.rm_element(place, rest[0])
        session.mark_dirty(path)
        print(f"Elemento {rest[0]} borrado.")
        return 0
    if kind == "cable":
        if not rest:
            raise ValueError("rm cable requiere NAME")
        abm.rm_cable(place, rest[0])
        session.mark_dirty(path)
        print(f"Cable {rest[0]} borrado.")
        return 0
    if kind == "connection":
        if not rest:
            raise ValueError("rm connection requiere índice")
        abm.rm_connection(place, int(rest[0]))
        session.mark_dirty(path)
        print(f"Conexión [{rest[0]}] borrada.")
        return 0
    raise ValueError(f"rm desconocido: {kind}")


def cmd_cd(session: ProjectSession, argv: list[str]) -> int:
    raw = argv[0] if argv else None
    current = session.cursor()
    preview = session.preview_cd(raw)
    cur_yaml = current.yaml_path.resolve() if current.yaml_path else None
    new_yaml = preview.yaml_path.resolve() if preview.yaml_path else None
    if cur_yaml is not None and cur_yaml != new_yaml and session.is_dirty(cur_yaml):
        if not _confirm_unsaved(session, [cur_yaml]):
            print("cd cancelado.")
            return 0
    session.cd(raw)
    if session.housewire_yaml_in_cwd() is None and str(session.cwd) != ".":
        print(
            f"Aviso: no hay {HOUSEWIRE_YAML} aquí (no es una location). "
            f"cd a una location o: add location …",
            file=sys.stderr,
        )
    return 0


def cmd_save(session: ProjectSession, argv: list[str]) -> int:
    force = "--force" in argv or "-f" in argv
    dirty = session.dirty_paths()
    if not dirty:
        print("Nada que guardar.")
        return 0
    for path in dirty:
        session.save(path, force=force)
        print(f"Guardado: {path.relative_to(session.root)}")
    return 0


def cmd_reload(session: ProjectSession, argv: list[str]) -> int:
    if session.is_dirty():
        ans = _prompt(
            "Hay cambios sin guardar. ¿Descartar y releer? [s/N]: ", session
        ).lower()
        if ans not in {"s", "y", "yes", "si", "sí"}:
            print("reload cancelado.")
            return 0
    path = session.reload()
    print(f"Recargado: {path.relative_to(session.root)}")
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
                raise ValueError("use requiere <archivo.yaml>")
            session.use_yaml(args[0])
            print(f"Activo: {session.active_yaml.relative_to(session.root)}")
            return 0
        if cmd == "show":
            return cmd_show(session, args)
        if cmd == "pend":
            return cmd_pend(session, args)
        if cmd == "add":
            return cmd_add(session, args)
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
                print(f"Guardando {len(dirty)} YAML dirty antes de generate…")
                session.save_all()
            return generate_fn(session.root, force=force)
        print(f"Comando desconocido: {cmd}. Escribe help.", file=sys.stderr)
        return 1
    except (ValueError, FileNotFoundError, FileExistsError, NotADirectoryError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
