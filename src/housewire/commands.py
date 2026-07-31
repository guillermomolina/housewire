from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from housewire.project import abm
from housewire.project.io import HOUSEWIRE_YAML, create_location_index
from housewire.project.session import ProjectSession

if TYPE_CHECKING:
    pass

HELP_TEXT = """Comandos del shell housewire:
  (Tab completa comandos, subcomandos add/rm y rutas de cd/use/…)
  pwd                          cwd y YAML activo
  cd [path]                    navegar Locations (directorios); auto-use housewire.yaml
  ls                           locations (cd) y elements de esta location
  use housewire.yaml           fijar housewire.yaml activo
  show                         location: del lugar + contenido de housewire.yaml
  show --element NAME | --cable NAME
  pend [<enter> <exit>] [section] [--colors C1,C2] [--notes ...]
                               cable pendiente + conduit (atajo de add pend)
  add location NAME --type T [--subtype ...] [--notes ...]
                               crear carpeta + housewire.yaml (T=Room|JunctionBox|Panel|Zone|House)
  add element NAME --type T [--subtype ...] [--label ...] [--manufacturer ...] [--model ...] [--notes ...]
  add cable NAME [--section S] [--colors C1,C2] [--kind power] [--notes ...]
                               defaults: section=1.5 mm2, colors=BN,BU
  add pend [<enter> <exit>] [section] [--colors ...] [--notes ...]
  add connection --from F --via V --to T
  add dir <path>                 mkdir -p (sin housewire.yaml; preferible add location)
  rm element|cable NAME
  rm connection <índice>
  rm file housewire.yaml
  rm dir <path>                  solo si está vacío
  generate [-f]                generar diagramas (como housewire generate)
  version                      version del programa
  help
  exit | quit
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


def _prompt(message: str) -> str:
    return input(message).strip()


def cmd_ls(session: ProjectSession) -> int:
    locations = session.list_locations()
    elements = session.list_elements()
    if not locations and not elements:
        print("(vacío)")
        return 0
    if locations:
        print("locations:")
        for name, place_type in locations:
            suffix = f"  ({place_type})" if place_type else ""
            print(f"  {name}/{suffix}")
    if elements:
        print("elements:")
        for name, type_id in elements:
            print(f"  {name}  ({type_id})")
    return 0


def cmd_pwd(session: ProjectSession) -> int:
    print(session.cwd_path().relative_to(session.root) or ".")
    if session.active_yaml:
        print(f"active: {session.active_yaml.relative_to(session.root)}")
    return 0


def cmd_show(session: ProjectSession, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="show", add_help=False)
    parser.add_argument("--element", dest="element")
    parser.add_argument("--cable", dest="cable")
    args, _ = parser.parse_known_args(argv)

    path = session.ensure_active_yaml()
    doc = abm.load_editable(path, session.root)
    print(abm.format_show(doc, element=args.element, cable=args.cable))
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
    p.add_argument("--kind", default="power")
    p.add_argument("--notes")
    return p.parse_args(rest)


def _resolve_pend_openings(positional: list[str]) -> tuple[str, str, str | None]:
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
        enter = _prompt("Abertura entrada (p.ej. N1): ")
    if not exit_op:
        exit_op = _prompt("Abertura salida (p.ej. S1): ")
    if not enter or not exit_op:
        raise ValueError("Aberturas entrada y salida son obligatorias")
    return enter, exit_op, section


def cmd_pend(session: ProjectSession, argv: list[str]) -> int:
    args = _parse_pend_args(argv)
    enter, exit_op, section = _resolve_pend_openings(list(args.positional))
    colors = _colors_list(args.colors) if args.colors else None
    path = session.ensure_active_yaml()
    doc = abm.load_editable(path, session.root)
    cable_name, conduit_name = abm.add_pending_cable(
        doc,
        enter=enter,
        exit=exit_op,
        section=section,
        colors=colors,
        kind=args.kind,
        notes=args.notes,
    )
    abm.persist(doc, path, session.root)
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
        p = argparse.ArgumentParser(prog="add location", add_help=False)
        p.add_argument("name")
        p.add_argument("--type", dest="type_id", required=True)
        p.add_argument("--subtype")
        p.add_argument("--notes")
        args = p.parse_args(rest)
        target = session.resolve_under_root(args.name)
        index_path = create_location_index(
            target, type_id=args.type_id, subtype=args.subtype, notes=args.notes
        )
        session.cwd = target.relative_to(session.root)
        session.active_yaml = index_path
        print(f"Location creada: {index_path.relative_to(session.root)}")
        return 0
    if kind == "pend":
        return cmd_pend(session, rest)
    path = session.ensure_active_yaml()
    doc = abm.load_editable(path, session.root)
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
            doc,
            args.name,
            type_id=args.type,
            subtype=args.subtype,
            manufacturer=args.manufacturer,
            model=args.model,
            label=args.label,
            notes=args.notes,
        )
        abm.persist(doc, path, session.root)
        print(f"Elemento {args.name} añadido.")
        return 0
    if kind == "cable":
        p = argparse.ArgumentParser(prog="add cable", add_help=False)
        p.add_argument("name")
        p.add_argument("--section", default=None)
        p.add_argument("--colors", default=None)
        p.add_argument("--kind", default="power")
        p.add_argument("--notes")
        args = p.parse_args(rest)
        abm.add_cable(
            doc,
            args.name,
            kind=args.kind,
            section=args.section,
            colors=_colors_list(args.colors) if args.colors else None,
            notes=args.notes,
        )
        abm.persist(doc, path, session.root)
        print(f"Cable {args.name} añadido.")
        return 0
    if kind == "connection":
        p = argparse.ArgumentParser(prog="add connection", add_help=False)
        p.add_argument("--from", dest="from_ref", required=True)
        p.add_argument("--via", dest="via_ref", required=True)
        p.add_argument("--to", dest="to_ref", required=True)
        args = p.parse_args(rest)
        abm.add_connection(doc, from_ref=args.from_ref, via_ref=args.via_ref, to_ref=args.to_ref)
        abm.persist(doc, path, session.root)
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
    path = session.ensure_active_yaml()
    doc = abm.load_editable(path, session.root)
    if kind == "element":
        if not rest:
            raise ValueError("rm element requiere NAME")
        abm.rm_element(doc, rest[0])
        abm.persist(doc, path, session.root)
        print(f"Elemento {rest[0]} borrado.")
        return 0
    if kind == "cable":
        if not rest:
            raise ValueError("rm cable requiere NAME")
        abm.rm_cable(doc, rest[0])
        abm.persist(doc, path, session.root)
        print(f"Cable {rest[0]} borrado.")
        return 0
    if kind == "connection":
        if not rest:
            raise ValueError("rm connection requiere índice")
        abm.rm_connection(doc, int(rest[0]))
        abm.persist(doc, path, session.root)
        print(f"Conexión [{rest[0]}] borrada.")
        return 0
    raise ValueError(f"rm desconocido: {kind}")


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
            session.cd(args[0] if args else None)
            if session.housewire_yaml_in_cwd() is None and str(session.cwd) != ".":
                print(
                    f"Aviso: no hay {HOUSEWIRE_YAML} aquí (no es una location). "
                    f"cd a una location o: add location …",
                    file=sys.stderr,
                )
            return 0
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
        if cmd == "generate":
            force = "-f" in args or "--force" in args
            return generate_fn(session.root, force=force)
        print(f"Comando desconocido: {cmd}. Escribe help.", file=sys.stderr)
        return 1
    except (ValueError, FileNotFoundError, FileExistsError, NotADirectoryError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
