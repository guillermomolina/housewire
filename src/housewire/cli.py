#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import shutil
import sys
import unicodedata
from pathlib import Path

import yaml

from housewire.house import (
    house_document_to_wireviz,
    is_house_document,
    load_catalog,
    path_location_parts,
)
from housewire.commands import cmd_ls, show_file
from housewire.house.physical import export_physical_zone
from housewire.project import abm
from housewire.project.paths import (
    YAML_EXTENSIONS,
    collect_yaml_from_directory,
    is_excluded_path,
    is_yaml,
)
from housewire.project.session import ProjectSession
from housewire.shell import run_repl

OUTPUT_SUFFIXES = (".html", ".png", ".svg", ".bom.tsv", ".yaml")
PACKAGE_ROOT = Path(__file__).resolve().parent
EXCLUDED_DIR_NAMES = {".venv", "__pycache__", ".git", "out"}
KNOWN_SUBCOMMANDS = frozenset({"generate", "shell", "ls", "show", "add", "rm"})


def run_wireviz(input_file: Path, output_dir: Path) -> None:
    if shutil.which("dot") is None:
        raise RuntimeError(
            "No se encontro 'dot' (Graphviz). Instala el paquete del sistema 'graphviz'."
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    from housewire.house.wireviz_patch import apply_wireviz_asymmetric_pinlabel_patch
    from wireviz.wireviz import parse as wireviz_parse

    apply_wireviz_asymmetric_pinlabel_patch()
    print()
    print("WireViz (house patch)")
    print("Input file:  ", input_file)
    print(
        "Output file: ",
        f"{output_dir / input_file.stem}.[html|png|svg|tsv]",
    )
    wireviz_parse(
        str(input_file),
        output_formats=("html", "png", "svg", "tsv"),
        output_dir=output_dir,
        output_name=input_file.stem,
        image_paths=[input_file.parent],
    )
    print()


def resolve_inputs(
    project_path: Path, raw_inputs: list[str] | None, output_dir: Path
) -> list[Path]:
    excluded_dirs = {output_dir.resolve()}
    if not raw_inputs:
        return collect_yaml_from_directory(project_path, excluded_dirs)

    resolved_files: list[Path] = []
    for item in raw_inputs:
        candidate = (project_path / item).resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"No existe la ruta de entrada: {candidate}")

        if candidate.is_file():
            if not is_yaml(candidate):
                raise ValueError(f"No es un YAML valido: {candidate}")
            resolved_files.append(candidate)
            continue

        if candidate.is_dir():
            yaml_files = collect_yaml_from_directory(candidate, excluded_dirs)
            if not yaml_files:
                raise FileNotFoundError(
                    f"No se encontraron YAML en el directorio: {candidate}"
                )
            resolved_files.extend(yaml_files)
            continue

        raise ValueError(f"Tipo de entrada no soportado: {candidate}")

    return sorted(set(resolved_files))


def normalize_token(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in ascii_value).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or "sin_nombre"


def build_prefix(project_path: Path, yaml_file: Path) -> str:
    relative_parent = yaml_file.relative_to(project_path).parent
    if str(relative_parent) == ".":
        return ""
    parts = [normalize_token(part) for part in relative_parent.parts]
    return "__".join(part for part in parts if part)


def prefixed_name(prefix: str, name: str) -> str:
    normalized_name = normalize_token(name)
    if not prefix:
        return normalized_name
    return f"{prefix}__{normalized_name}"


def rename_connection_endpoint(endpoint: object, name_map: dict[str, str]) -> object:
    if not isinstance(endpoint, dict):
        return endpoint

    renamed: dict[object, object] = {}
    for key, value in endpoint.items():
        renamed[name_map.get(str(key), key)] = value
    return renamed


def _apply_pin_remaps_to_connections(
    connections: list[object],
    pin_remap_by_element: dict[str, dict[str, object]],
) -> None:
    for connection in connections:
        if not isinstance(connection, list):
            continue
        for endpoint in connection:
            if not isinstance(endpoint, dict):
                continue
            for name, pins in endpoint.items():
                remap = pin_remap_by_element.get(str(name))
                if not remap or not isinstance(pins, list):
                    continue
                endpoint[name] = [remap.get(str(pin), pin) for pin in pins]


def _merge_wireviz_piece(
    *,
    connectors: dict[str, object],
    cables: dict[str, object],
    connections: list[object],
    pin_remaps: dict[str, dict[str, object]],
    merged: dict[str, object],
    options_already_set: bool,
    data: dict,
    prefix: str,
    already_qualified: bool,
) -> bool:
    local_map: dict[str, str] = {}

    local_connectors = data.get("connectors", {}) or {}
    if not isinstance(local_connectors, dict):
        raise ValueError("'connectors' debe ser un mapa")
    for name, definition in local_connectors.items():
        new_name = str(name) if already_qualified else prefixed_name(prefix, str(name))
        if new_name in connectors:
            raise ValueError(f"Colision de nombre en connectors tras prefijo: {new_name}")
        connectors[new_name] = copy.deepcopy(definition)
        local_map[str(name)] = new_name

    local_cables = data.get("cables", {}) or {}
    if not isinstance(local_cables, dict):
        raise ValueError("'cables' debe ser un mapa")
    for name, definition in local_cables.items():
        new_name = str(name) if already_qualified else prefixed_name(prefix, str(name))
        if new_name in cables:
            raise ValueError(f"Colision de nombre en cables tras prefijo: {new_name}")
        cables[new_name] = copy.deepcopy(definition)
        local_map[str(name)] = new_name

    local_connections = data.get("connections", []) or []
    if not isinstance(local_connections, list):
        raise ValueError("'connections' debe ser una lista")
    for connection in local_connections:
        if not isinstance(connection, list):
            raise ValueError("Cada connection debe ser una lista")
        if already_qualified:
            connections.append(copy.deepcopy(connection))
        else:
            renamed = [
                rename_connection_endpoint(endpoint, local_map) for endpoint in connection
            ]
            connections.append(renamed)

    for name, remap in (data.get("_pin_remaps") or {}).items():
        name_s = str(name)
        if name_s in pin_remaps:
            raise ValueError(f"Colision de pin_remap: {name_s}")
        pin_remaps[name_s] = copy.deepcopy(remap)

    if "options" in data and not options_already_set:
        merged["options"] = copy.deepcopy(data["options"])
        options_already_set = True

    for key, value in data.items():
        if key in {
            "options",
            "connectors",
            "cables",
            "connections",
            "schema",
            "_pin_remaps",
        }:
            continue
        if key not in merged:
            merged[key] = copy.deepcopy(value)
            continue
        if isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key].update(copy.deepcopy(value))
        elif isinstance(merged[key], list) and isinstance(value, list):
            merged[key].extend(copy.deepcopy(value))
        else:
            merged[key] = copy.deepcopy(value)

    return options_already_set


def merge_yaml_files(project_path: Path, input_files: list[Path]) -> dict:
    merged: dict[str, object] = {}
    options_already_set = False
    catalog = load_catalog()

    connectors: dict[str, object] = {}
    cables: dict[str, object] = {}
    connections: list[object] = []
    pin_remaps: dict[str, dict[str, object]] = {}

    for yaml_file in input_files:
        with yaml_file.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}

        if not isinstance(data, dict):
            raise ValueError(f"El YAML no contiene un objeto valido: {yaml_file}")

        if is_house_document(data):
            wireviz_data = house_document_to_wireviz(
                data,
                catalog=catalog,
                file_location_parts=path_location_parts(project_path, yaml_file),
            )
            options_already_set = _merge_wireviz_piece(
                connectors=connectors,
                cables=cables,
                connections=connections,
                pin_remaps=pin_remaps,
                merged=merged,
                options_already_set=options_already_set,
                data=wireviz_data,
                prefix="",
                already_qualified=True,
            )
            continue

        prefix = build_prefix(project_path, yaml_file)
        options_already_set = _merge_wireviz_piece(
            connectors=connectors,
            cables=cables,
            connections=connections,
            pin_remaps=pin_remaps,
            merged=merged,
            options_already_set=options_already_set,
            data=data,
            prefix=prefix,
            already_qualified=False,
        )

    _apply_pin_remaps_to_connections(connections, pin_remaps)

    merged["connectors"] = connectors
    merged["cables"] = cables
    merged["connections"] = connections
    return merged


def add_external_stubs(merged: dict[str, object]) -> None:
    """Add simple connectors for names referenced in connections but missing."""
    connectors = merged.get("connectors") or {}
    if not isinstance(connectors, dict):
        return
    connections = merged.get("connections") or []
    used_pins: dict[str, list[object]] = {}

    for connection in connections:
        if not isinstance(connection, list):
            continue
        for endpoint in connection:
            if not isinstance(endpoint, dict):
                continue
            for name, pins in endpoint.items():
                name_s = str(name)
                if name_s in connectors:
                    continue
                # skip cable endpoints (present in cables)
                cables = merged.get("cables") or {}
                if isinstance(cables, dict) and name_s in cables:
                    continue
                if not isinstance(pins, list):
                    continue
                bucket = used_pins.setdefault(name_s, [])
                for pin in pins:
                    if pin not in bucket:
                        bucket.append(pin)

    for name, pins in used_pins.items():
        short = name.split("_")[-1] if "_" in name else name
        connectors[name] = {
            "type": "External",
            "subtype": "fuera de zona",
            "pins": pins or ["x"],
            "pinlabels": [str(p) for p in (pins or ["x"])],
            "notes": f"Stub: {short} referenciado desde esta zona pero definido fuera",
        }


def output_base_name(project_path: Path) -> str:
    return normalize_token(project_path.name)


def expected_output_files(base_name: str, output_dir: Path) -> list[Path]:
    return [
        output_dir / f"{base_name}{suffix}"
        for suffix in (".html", ".png", ".svg", ".bom.tsv")
    ]


def ensure_overwrite_allowed(
    base_name: str, output_dir: Path, *, force: bool = False
) -> None:
    existing_outputs = [
        path for path in expected_output_files(base_name, output_dir) if path.exists()
    ]
    if not existing_outputs:
        return

    if force:
        for file_path in sorted(set(existing_outputs)):
            file_path.unlink()
        return

    output_list = "\n".join(f" - {path}" for path in sorted(set(existing_outputs)))
    answer = input(
        "Se detectaron archivos de salida ya existentes:\n"
        f"{output_list}\n"
        "Quieres sobreescribirlos? [s/N]: "
    ).strip().lower()

    if answer in {"s", "si", "y", "yes"}:
        for file_path in sorted(set(existing_outputs)):
            file_path.unlink()
        return

    raise FileExistsError("Operacion cancelada por el usuario.")


def discover_zones(project_path: Path, all_files: list[Path]) -> dict[str, list[Path]]:
    """Group housewire.yaml files by top-level path under the project root.

    No place type or site layout is assumed: each first-level directory is a
    zone; files directly in the project root form a zone named after the
    project directory. Point ``project_path`` at any subtree to remap scope.
    """
    zones: dict[str, list[Path]] = {}
    for path in all_files:
        rel = path.relative_to(project_path)
        parts = rel.parts
        zone_name = project_path.name if len(parts) == 1 else parts[0]
        zones.setdefault(zone_name, []).append(path)
    return zones


def write_and_render_wireviz(
    project_path: Path,
    input_files: list[Path],
    output_dir: Path,
    base_name: str,
    *,
    with_stubs: bool = False,
) -> None:
    print(f"Fusionando {len(input_files)} YAML → {base_name}...")
    for input_file in input_files:
        print(f" - {input_file}")

    merged_data = merge_yaml_files(project_path, input_files)
    if with_stubs:
        add_external_stubs(merged_data)

    output_dir.mkdir(parents=True, exist_ok=True)
    merged_input = output_dir / f"{base_name}.yaml"
    with merged_input.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(merged_data, handle, sort_keys=False, allow_unicode=True)

    run_wireviz(merged_input, output_dir)


def run_generate_project(
    project_path: Path,
    *,
    inputs: list[str] | None = None,
    force: bool = False,
    do_zones: bool = True,
) -> int:
    output_dir = (project_path / "out").resolve()

    if not project_path.exists():
        print(f"No existe la ruta de proyecto: {project_path}", file=sys.stderr)
        return 1

    if not project_path.is_dir():
        print(f"La ruta de proyecto no es un directorio: {project_path}", file=sys.stderr)
        return 1

    try:
        input_files = resolve_inputs(project_path, inputs, output_dir)
        if not input_files:
            print(f"No se encontraron archivos YAML en: {project_path}", file=sys.stderr)
            return 1

        base_name = output_base_name(project_path)
        ensure_overwrite_allowed(base_name, output_dir, force=force)

        write_and_render_wireviz(
            project_path, input_files, output_dir, base_name, with_stubs=False
        )

        if do_zones:
            zones_dir = output_dir / "zones"
            physical_dir = output_dir / "physical"
            if force:
                if zones_dir.exists():
                    shutil.rmtree(zones_dir)
                if physical_dir.exists():
                    shutil.rmtree(physical_dir)

            zones = discover_zones(project_path, input_files)
            for zone_name, zone_files in zones.items():
                zone_base = normalize_token(zone_name)
                write_and_render_wireviz(
                    project_path,
                    zone_files,
                    zones_dir,
                    zone_base,
                    with_stubs=True,
                )
                phys_svg = physical_dir / f"{zone_base}.svg"
                print(f"Diagrama fisico → {phys_svg}")
                export_physical_zone(
                    project_path,
                    zone_files,
                    phys_svg,
                    title=f"{project_path.name} — {zone_name} (fisico)",
                )

    except Exception as exc:
        if hasattr(exc, "returncode"):
            print(f"Error ejecutando WireViz (codigo {exc.returncode}).", file=sys.stderr)
            return int(exc.returncode)
        if isinstance(exc, RuntimeError):
            print(str(exc), file=sys.stderr)
            return 2
        if isinstance(exc, (FileNotFoundError, ValueError, FileExistsError)):
            print(str(exc), file=sys.stderr)
            return 1
        raise

    print(f"Diagrama fusionado generado en: {output_dir}")
    if do_zones:
        print(f"Zonas WireViz: {output_dir / 'zones'}")
        print(f"Topologia fisica: {output_dir / 'physical'}")
    return 0


def _add_generate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "project_path",
        help="Ruta del proyecto donde estan los YAML y el directorio out",
    )
    parser.add_argument(
        "--input",
        action="append",
        dest="inputs",
        help="Ruta relativa de YAML o carpeta dentro del proyecto",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Sobreescribe la salida existente sin preguntar",
    )
    parser.add_argument(
        "--zones",
        action="store_true",
        default=True,
        help="Genera out/zones/ y out/physical/. Activo por defecto.",
    )
    parser.add_argument(
        "--no-zones",
        action="store_true",
        help="Solo el diagrama fusionado total",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="housewire",
        description="housewire: diagramas, shell y ABM de instalaciones house/v1.",
    )
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="Fusionar YAML y generar diagramas")
    _add_generate_arguments(gen)

    sh = sub.add_parser("shell", help="REPL: cd, ls, use, add, rm, generate")
    sh.add_argument("project_path", help="Ruta del proyecto de obra")

    ls_p = sub.add_parser("ls", help="Listar locations (cd) y elements")
    ls_p.add_argument("project_path")
    ls_p.add_argument("path", nargs="?", default=".", help="Ruta relativa")

    show_p = sub.add_parser("show", help="Ver contenido de un YAML house/v1")
    show_p.add_argument("project_path")
    show_p.add_argument("yaml_path")
    show_p.add_argument("--element")
    show_p.add_argument("--cable")

    add_p = sub.add_parser("add", help="Alta de artefactos o archivos")
    add_sub = add_p.add_subparsers(dest="add_kind", required=True)

    add_el = add_sub.add_parser("element")
    add_el.add_argument("project_path")
    add_el.add_argument("yaml_path")
    add_el.add_argument("name")
    add_el.add_argument("--type", required=True)
    add_el.add_argument("--subtype")
    add_el.add_argument("--manufacturer")
    add_el.add_argument("--model")
    add_el.add_argument("--label")
    add_el.add_argument("--notes")

    add_cb = add_sub.add_parser("cable")
    add_cb.add_argument("project_path")
    add_cb.add_argument("yaml_path")
    add_cb.add_argument("name")
    add_cb.add_argument("--section", default=None, help="default: 1.5 mm2")
    add_cb.add_argument("--colors", default=None, help="default: BN,BU")
    add_cb.add_argument("--kind", default="power")
    add_cb.add_argument("--notes")

    add_pend = add_sub.add_parser("pend", help="Cable pendiente + conduit de paso")
    add_pend.add_argument("project_path")
    add_pend.add_argument("yaml_path")
    add_pend.add_argument("enter", help="Abertura entrada, p.ej. W.N")
    add_pend.add_argument("exit", help="Abertura salida, p.ej. E.S")
    add_pend.add_argument("section", nargs="?", default=None, help="p.ej. 1.5 o 2.5 mm2")
    add_pend.add_argument("--colors", default=None, help="default: BN,BU")
    add_pend.add_argument("--kind", default="power")
    add_pend.add_argument("--notes")

    add_cn = add_sub.add_parser("connection")
    add_cn.add_argument("project_path")
    add_cn.add_argument("yaml_path")
    add_cn.add_argument("--from", dest="from_ref", required=True)
    add_cn.add_argument("--via", dest="via_ref", required=True)
    add_cn.add_argument("--to", dest="to_ref", required=True)

    add_loc = add_sub.add_parser("location", help="Create place directory + housewire.yaml")
    add_loc.add_argument("project_path")
    add_loc.add_argument("name")
    add_loc.add_argument(
        "--type",
        dest="type_id",
        required=True,
        help="Room, JunctionBox, Panel, Zone, House (or Location)",
    )
    add_loc.add_argument("--subtype")
    add_loc.add_argument("--notes")

    add_d = add_sub.add_parser("dir")
    add_d.add_argument("project_path")
    add_d.add_argument("dir_path")

    rm_p = sub.add_parser("rm", help="Baja de artefactos o archivos")
    rm_sub = rm_p.add_subparsers(dest="rm_kind", required=True)

    rm_el = rm_sub.add_parser("element")
    rm_el.add_argument("project_path")
    rm_el.add_argument("yaml_path")
    rm_el.add_argument("name")

    rm_cb = rm_sub.add_parser("cable")
    rm_cb.add_argument("project_path")
    rm_cb.add_argument("yaml_path")
    rm_cb.add_argument("name")

    rm_cn = rm_sub.add_parser("connection")
    rm_cn.add_argument("project_path")
    rm_cn.add_argument("yaml_path")
    rm_cn.add_argument("index", type=int)

    rm_f = rm_sub.add_parser("file")
    rm_f.add_argument("project_path")
    rm_f.add_argument("file_path")

    rm_d = rm_sub.add_parser("dir")
    rm_d.add_argument("project_path")
    rm_d.add_argument("dir_path")

    return parser


def _colors_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _dispatch_subcommand(args: argparse.Namespace) -> int:
    cmd = args.command
    if cmd == "generate":
        project_path = Path(args.project_path).resolve()
        do_zones = args.zones and not args.no_zones
        return run_generate_project(
            project_path,
            inputs=args.inputs,
            force=args.force,
            do_zones=do_zones,
        )
    if cmd == "shell":
        project_path = Path(args.project_path).resolve()
        return run_repl(project_path, generate_fn=_run_generate_from_shell)
    if cmd == "ls":
        session = ProjectSession(Path(args.project_path).resolve())
        session.cd(args.path)
        return cmd_ls(session)
    if cmd == "show":
        return show_file(
            Path(args.project_path).resolve(),
            Path(args.yaml_path),
            element=args.element,
            cable=args.cable,
        )
    if cmd == "add":
        project_path = Path(args.project_path).resolve()
        if args.add_kind == "location":
            from housewire.project.io import create_location_index

            target = (project_path / args.name).resolve()
            index_path = create_location_index(
                target,
                type_id=args.type_id,
                subtype=args.subtype,
                notes=args.notes,
            )
            print(f"OK {index_path.relative_to(project_path)}")
            return 0
        if args.add_kind == "dir":
            target = (project_path / args.dir_path).resolve()
            target.mkdir(parents=True, exist_ok=True)
            print(f"Creado: {target.relative_to(project_path)}")
            return 0
        yaml_path = (project_path / args.yaml_path).resolve()
        doc = abm.load_editable(yaml_path, project_path)
        if args.add_kind == "element":
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
        elif args.add_kind == "cable":
            abm.add_cable(
                doc,
                args.name,
                kind=args.kind,
                section=args.section,
                colors=_colors_list(args.colors) if args.colors else None,
                notes=args.notes,
            )
        elif args.add_kind == "pend":
            cable_name, conduit_name = abm.add_pending_cable(
                doc,
                enter=args.enter,
                exit=args.exit,
                section=args.section,
                colors=_colors_list(args.colors) if args.colors else None,
                kind=args.kind,
                notes=args.notes,
            )
            abm.persist(doc, yaml_path, project_path)
            print(f"OK {cable_name} + {conduit_name}")
            return 0
        elif args.add_kind == "connection":
            abm.add_connection(
                doc,
                from_ref=args.from_ref,
                via_ref=args.via_ref,
                to_ref=args.to_ref,
            )
        abm.persist(doc, yaml_path, project_path)
        print("OK")
        return 0
    if cmd == "rm":
        project_path = Path(args.project_path).resolve()
        if args.rm_kind == "file":
            target = (project_path / args.file_path).resolve()
            target.unlink()
            print(f"Borrado: {target.relative_to(project_path)}")
            return 0
        if args.rm_kind == "dir":
            target = (project_path / args.dir_path).resolve()
            if any(target.iterdir()):
                print("rm dir: el directorio no esta vacio", file=sys.stderr)
                return 1
            target.rmdir()
            print(f"Borrado: {target.relative_to(project_path)}")
            return 0
        yaml_path = (project_path / args.yaml_path).resolve()
        doc = abm.load_editable(yaml_path, project_path)
        if args.rm_kind == "element":
            abm.rm_element(doc, args.name)
        elif args.rm_kind == "cable":
            abm.rm_cable(doc, args.name)
        elif args.rm_kind == "connection":
            abm.rm_connection(doc, args.index)
        abm.persist(doc, yaml_path, project_path)
        print("OK")
        return 0
    print("Comando no implementado", file=sys.stderr)
    return 1


def _run_generate_from_shell(project_path: Path, *, force: bool = False) -> int:
    return run_generate_project(project_path, force=force, do_zones=True)


def _legacy_generate_argv(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    _add_generate_arguments(parser)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        _build_parser().print_help()
        return 0

    first = argv[0]
    if first not in KNOWN_SUBCOMMANDS and not first.startswith("-"):
        candidate = Path(first)
        if candidate.exists():
            args = _legacy_generate_argv(argv)
            do_zones = args.zones and not args.no_zones
            return run_generate_project(
                Path(args.project_path).resolve(),
                inputs=args.inputs,
                force=args.force,
                do_zones=do_zones,
            )

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return _dispatch_subcommand(args)


if __name__ == "__main__":
    raise SystemExit(main())
