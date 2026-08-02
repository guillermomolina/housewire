#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from housewire.commands import cmd_ls, show_file
from housewire import __title__, __version__
from housewire.site import abm
from housewire.site.paths import split_site_arg
from housewire.site.session import SiteSession
from housewire.shell import run_repl

PACKAGE_ROOT = Path(__file__).resolve().parent
KNOWN_SUBCOMMANDS = frozenset(
    {"shell", "ls", "show", "add", "rm", "version", "serve"}
)


def _catalog_parent() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--catalog",
        default=None,
        help="Type catalog name or path (default: catalogs/default or HOUSEWIRE_CATALOG)",
    )
    return parent


def _apply_catalog_option(catalog: str | None) -> None:
    if catalog:
        os.environ["HOUSEWIRE_CATALOG"] = str(catalog)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="housewire",
        description=f"{__title__}: UI, shell, and ABM for house/v1 installations.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"{__title__} {__version__}",
    )
    sub = parser.add_subparsers(dest="command")


    sh = sub.add_parser(
        "shell",
        parents=[_catalog_parent()],
        help="REPL: cd, ls, use, add, rm, save",
    )
    sh.add_argument("site_path", help="Site YAML file or site directory")

    sub.add_parser("version", help=f"Show {__title__} version")

    serve_p = sub.add_parser(
        "serve",
        parents=[_catalog_parent()],
        help="Interactive physical location UI (requires housewire[ui])",
    )
    serve_p.add_argument("site_path", help="Site YAML file or site directory")
    serve_p.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host (default: 127.0.0.1)",
    )
    serve_p.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Bind port (default: 8765)",
    )

    ls_p = sub.add_parser("ls", help="List locations (cd) and elements")
    ls_p.add_argument("site_path")
    ls_p.add_argument("path", nargs="?", default=".", help="Relative path")

    show_p = sub.add_parser("show", help="Show contents of a house/v1 YAML")
    show_p.add_argument("site_path")
    show_p.add_argument("yaml_path")
    show_p.add_argument("--element")
    show_p.add_argument("--cable")

    add_p = sub.add_parser("add", help="Add artifacts or files")
    add_sub = add_p.add_subparsers(dest="add_kind", required=True)

    add_el = add_sub.add_parser("element")
    add_el.add_argument("site_path")
    add_el.add_argument("yaml_path")
    add_el.add_argument("name")
    add_el.add_argument("--type", required=True)
    add_el.add_argument("--subtype")
    add_el.add_argument("--manufacturer")
    add_el.add_argument("--model")
    add_el.add_argument("--label")
    add_el.add_argument("--notes")
    add_el.add_argument(
        "--set",
        dest="set_specs",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Set element field (repeatable; YAML value)",
    )

    add_cb = add_sub.add_parser("cable")
    add_cb.add_argument("site_path")
    add_cb.add_argument("yaml_path")
    add_cb.add_argument("name")
    add_cb.add_argument("--section", default=None, help="default: catalog / 1.5 mm2")
    add_cb.add_argument("--colors", default=None, help="default: catalog / BN,BU")
    add_cb.add_argument("--subtype", default=None, help="default: power")
    add_cb.add_argument("--kind", default=None, help="legacy alias of --subtype")
    add_cb.add_argument("--label")
    add_cb.add_argument("--notes")

    add_pend = add_sub.add_parser("pend", help="Pending cable + pass-through conduit")
    add_pend.add_argument("site_path")
    add_pend.add_argument("yaml_path")
    add_pend.add_argument("enter", help="Enter opening, e.g. N1")
    add_pend.add_argument("exit", help="Exit opening, e.g. S1")
    add_pend.add_argument("section", nargs="?", default=None, help="e.g. 1.5 or 2.5 mm2")
    add_pend.add_argument("--colors", default=None, help="default: catalog / BN,BU")
    add_pend.add_argument("--subtype", default=None, help="default: power")
    add_pend.add_argument("--kind", default=None, help="legacy alias of --subtype")
    add_pend.add_argument("--label")
    add_pend.add_argument("--notes")

    add_cn = add_sub.add_parser("connection")
    add_cn.add_argument("site_path")
    add_cn.add_argument("yaml_path")
    add_cn.add_argument("--from", dest="from_ref", required=True)
    add_cn.add_argument("--via", dest="via_ref", required=True)
    add_cn.add_argument("--to", dest="to_ref", required=True)

    add_cd = add_sub.add_parser("conduit", help="Tube between openings (physical layer)")
    add_cd.add_argument("site_path")
    add_cd.add_argument("yaml_path")
    add_cd.add_argument("name")
    add_cd.add_argument("--from", dest="from_ref", required=True, help="LocationRef.OpeningId")
    add_cd.add_argument("--to", dest="to_ref", required=True, help="LocationRef.OpeningId")
    add_cd.add_argument(
        "--contains",
        required=True,
        help="Cable ids in this YAML, comma-separated",
    )
    add_cd.add_argument("--subtype", default=None, help="default: tube")
    add_cd.add_argument("--label")
    add_cd.add_argument("--notes")

    add_loc = add_sub.add_parser(
        "location", help="Create nested place under parent elements:"
    )
    add_loc.add_argument("site_path")
    add_loc.add_argument("name", help="New place id (leaf)")
    add_loc.add_argument(
        "--type",
        dest="type_id",
        required=True,
        help="Room, Stair, JunctionBox, DeviceBox, LightPoint, Panel, Floor, House (or Location)",
    )
    add_loc.add_argument("--subtype")
    add_loc.add_argument("--notes")
    add_loc.add_argument(
        "--name",
        dest="working_name",
        help="Short working name for canvas/lists (YAML name:)",
    )
    add_loc.add_argument(
        "--label",
        help="Human-readable label (default: derived if NAME has spaces)",
    )
    add_loc.add_argument(
        "--under",
        default="",
        help="Parent place path inside the site YAML (e.g. Parking)",
    )
    add_loc.add_argument(
        "--set",
        dest="set_specs",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Set place field (repeatable; YAML value)",
    )

    add_d = add_sub.add_parser("dir")
    add_d.add_argument("site_path")
    add_d.add_argument("dir_path")

    rm_p = sub.add_parser("rm", help="Remove artifacts or files")
    rm_sub = rm_p.add_subparsers(dest="rm_kind", required=True)

    rm_el = rm_sub.add_parser("element")
    rm_el.add_argument("site_path")
    rm_el.add_argument("yaml_path")
    rm_el.add_argument("name")

    rm_cb = rm_sub.add_parser("cable")
    rm_cb.add_argument("site_path")
    rm_cb.add_argument("yaml_path")
    rm_cb.add_argument("name")

    rm_cn = rm_sub.add_parser("connection")
    rm_cn.add_argument("site_path")
    rm_cn.add_argument("yaml_path")
    rm_cn.add_argument("index", type=int)

    rm_f = rm_sub.add_parser("file")
    rm_f.add_argument("site_path")
    rm_f.add_argument("file_path")

    rm_d = rm_sub.add_parser("dir")
    rm_d.add_argument("site_path")
    rm_d.add_argument("dir_path")

    return parser


def _colors_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _dispatch_subcommand(args: argparse.Namespace) -> int:
    cmd = args.command
    if cmd == "version":
        print(f"{__title__} {__version__}")
        return 0
    if cmd == "serve":
        from housewire.ui.app import run_serve

        site_path = Path(args.site_path)
        try:
            run_serve(site_path, host=args.host, port=args.port)
        except (RuntimeError, FileNotFoundError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0
    if cmd == "shell":
        return run_repl(Path(args.site_path))
    if cmd == "ls":
        session = SiteSession.open(Path(args.site_path))
        session.cd(args.path)
        return cmd_ls(session)
    if cmd == "show":
        site_root, _site_yaml = split_site_arg(Path(args.site_path))
        return show_file(
            site_root,
            Path(args.yaml_path),
            element=args.element,
            cable=args.cable,
        )
    if cmd == "add":
        session = SiteSession.open(Path(args.site_path))
        site_path = session.root
        if args.add_kind == "location":
            from housewire.house import location_id_from_name
            from housewire.site.io import create_inline_location
            from housewire.site.tree import get_place_node

            raw = Path(args.name)
            if str(raw.parent) not in (".", ""):
                raise ValueError("add location NAME must be a leaf (use --under for parent)")
            leaf_id, auto_label = location_id_from_name(raw.name)
            label = args.label or auto_label
            working_name = getattr(args, "working_name", None)
            yaml_path = session.site_yaml()
            if not yaml_path.is_file():
                raise FileNotFoundError(f"No site YAML at: {yaml_path}")
            doc = abm.load_editable(yaml_path, site_path)
            under = [
                p for p in str(getattr(args, "under", "") or "").replace("\\", "/").split("/") if p
            ]
            parent = get_place_node(doc, under)
            entry = create_inline_location(
                parent,
                leaf_id,
                type_id=args.type_id,
                subtype=args.subtype,
                notes=args.notes,
                label=label,
                working_name=working_name,
            )
            if getattr(args, "set_specs", None):
                abm.apply_set_specs(entry, args.set_specs, target="place")
            abm.persist(doc, yaml_path, site_path)
            where = "/".join([*under, leaf_id])
            print(f"OK {where} in {yaml_path.relative_to(site_path)}")
            return 0
        if args.add_kind == "dir":
            target = (site_path / args.dir_path).resolve()
            target.mkdir(parents=True, exist_ok=True)
            print(f"Created: {target.relative_to(site_path)}")
            return 0
        yaml_path = (site_path / args.yaml_path).resolve()
        doc = abm.load_editable(yaml_path, site_path)
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
            if getattr(args, "set_specs", None):
                abm.apply_set_specs(
                    doc["elements"][args.name], args.set_specs, target="element"
                )
        elif args.add_kind == "cable":
            abm.add_cable(
                doc,
                args.name,
                subtype=args.subtype or args.kind or abm.DEFAULT_CABLE_SUBTYPE,
                section=args.section,
                colors=_colors_list(args.colors) if args.colors else None,
                label=args.label,
                notes=args.notes,
            )
        elif args.add_kind == "pend":
            cable_name, conduit_name = abm.add_pending_cable(
                doc,
                enter=args.enter,
                exit=args.exit,
                section=args.section,
                colors=_colors_list(args.colors) if args.colors else None,
                subtype=args.subtype or args.kind or abm.DEFAULT_CABLE_SUBTYPE,
                label=args.label,
                notes=args.notes,
            )
            abm.persist(doc, yaml_path, site_path)
            print(f"OK {cable_name} + {conduit_name}")
            return 0
        elif args.add_kind == "connection":
            abm.add_connection(
                doc,
                from_ref=args.from_ref,
                via_ref=args.via_ref,
                to_ref=args.to_ref,
            )
        elif args.add_kind == "conduit":
            contains = _colors_list(args.contains)
            if not contains:
                raise ValueError("--contains cannot be empty")
            abm.add_conduit(
                doc,
                args.name,
                contains=contains,
                from_ref=args.from_ref,
                to_ref=args.to_ref,
                subtype=args.subtype or abm.DEFAULT_CONDUIT_SUBTYPE,
                label=args.label,
                notes=args.notes,
            )
        else:
            raise ValueError(f"Unknown add kind: {args.add_kind}")
        abm.persist(doc, yaml_path, site_path)
        print("OK")
        return 0
    if cmd == "rm":
        site_path = SiteSession.open(Path(args.site_path)).root
        if args.rm_kind == "file":
            target = (site_path / args.file_path).resolve()
            target.unlink()
            print(f"Deleted: {target.relative_to(site_path)}")
            return 0
        if args.rm_kind == "dir":
            target = (site_path / args.dir_path).resolve()
            if any(target.iterdir()):
                print("rm dir: directory is not empty", file=sys.stderr)
                return 1
            target.rmdir()
            print(f"Deleted: {target.relative_to(site_path)}")
            return 0
        yaml_path = (site_path / args.yaml_path).resolve()
        doc = abm.load_editable(yaml_path, site_path)
        if args.rm_kind == "element":
            abm.rm_element(doc, args.name)
        elif args.rm_kind == "cable":
            abm.rm_cable(doc, args.name)
        elif args.rm_kind == "connection":
            abm.rm_connection(doc, args.index)
        abm.persist(doc, yaml_path, site_path)
        print("OK")
        return 0
    print("Command not implemented", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        _build_parser().print_help()
        return 0

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    _apply_catalog_option(getattr(args, "catalog", None))
    return _dispatch_subcommand(args)


if __name__ == "__main__":
    raise SystemExit(main())
