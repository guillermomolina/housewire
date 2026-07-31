"""Physical topology diagram from house/v1 (locations + conduits).

Physical layer only: nested location clusters linked by conduits (openings).
Electrical connections (elements + cables) belong to WireViz, not here.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from housewire.house import (
    is_house_document,
    normalize_token,
    path_location_parts,
)
from housewire.house.conduit_ref import (
    conduit_endpoints,
    location_key,
    resolve_location_ref,
    split_conduit_endpoint,
)
from housewire.project.openings import opening_compass_port


@dataclass
class PhysNode:
    node_id: str
    title: str
    type_id: str
    parts: tuple[str, ...]
    display_label: str
    subtitle: str = ""


@dataclass
class PhysEdge:
    src: str
    dst: str
    label: str
    src_port: str | None = None  # Graphviz compass: n/s/e/w/_
    dst_port: str | None = None


@dataclass
class PhysModel:
    nodes: dict[str, PhysNode] = field(default_factory=dict)
    edges: list[PhysEdge] = field(default_factory=list)
    title: str = ""


def _leaf_place_meta(fragment: dict[str, Any], location_parts: list[str]) -> dict[str, Any]:
    """Return place metadata dict for this fragment (directory or inline)."""
    from housewire.house import place_meta_from_mapping

    meta = place_meta_from_mapping(fragment)
    if meta is not None:
        return meta
    leaf = location_parts[-1] if location_parts else None
    for name, definition in (fragment.get("elements") or {}).items():
        if not isinstance(definition, dict):
            continue
        from housewire.house import is_place_type

        if is_place_type(definition.get("type")):
            if leaf is None or str(name) == str(leaf):
                return definition
    return {}


def _safe_id(value: str) -> str:
    return normalize_token(value) or "n"


def _load_house_files(
    project_path: Path, yaml_files: list[Path]
) -> list[tuple[list[str], dict[str, Any]]]:
    """Yield (location_parts, fragment) for each house document piece."""
    from housewire.house import _walk_locations

    pieces: list[tuple[list[str], dict[str, Any]]] = []
    for yaml_file in yaml_files:
        with yaml_file.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not is_house_document(data):
            continue
        base = path_location_parts(project_path, yaml_file)
        try:
            fragments = _walk_locations(data, base)
        except ValueError as exc:
            raise ValueError(f"{yaml_file}: {exc}") from exc
        if not fragments and (
            any(
                key in data
                for key in ("elements", "cables", "connections", "conduits")
            )
            or data.get("type")
            or isinstance(data.get("location"), dict)
        ):
            from housewire.house import place_meta_from_mapping

            frag = {
                key: data[key]
                for key in ("elements", "cables", "connections", "conduits")
                if key in data
            }
            meta = place_meta_from_mapping(data)
            if meta is not None:
                frag.update(meta)
            fragments = [(base, frag)] if frag else []
            if not fragments:
                fragments = _walk_locations(data, base)
        pieces.extend(fragments)
    return pieces


def _ensure_location_node(
    model: PhysModel,
    parts: tuple[str, ...],
    *,
    type_id: str = "Location",
    label: str | None = None,
    subtitle: str = "",
    external: bool = False,
    root_name: str = "site",
) -> str:
    key = location_key(parts)
    if key in model.nodes:
        node = model.nodes[key]
        # Fill in better metadata if we only had a stub before.
        if label and node.display_label in (parts[-1] if parts else root_name, "raiz"):
            node.display_label = label
            node.title = f"{label}\\n{node.type_id}"
        if subtitle and not node.subtitle:
            node.subtitle = subtitle
        if type_id != "Location" and node.type_id in ("Location", "External"):
            node.type_id = type_id
            node.title = f"{node.display_label}\\n{type_id}"
        return key

    if parts:
        leaf = parts[-1]
        display_label = label or leaf
        node_id = _safe_id(key)
    else:
        display_label = label or root_name
        node_id = _safe_id(root_name)
    title = f"{display_label}\\n{type_id}"
    if external:
        title = f"{display_label}\\n(externo)"
        type_id = "External"
    model.nodes[key] = PhysNode(
        node_id=node_id,
        title=title,
        type_id=type_id,
        parts=parts,
        display_label=display_label,
        subtitle=subtitle,
    )
    return key


def _ensure_ancestor_nodes(
    model: PhysModel,
    parts: tuple[str, ...],
    *,
    root_name: str,
) -> None:
    """Ensure every path prefix exists so clusters can nest."""
    for depth in range(len(parts)):
        prefix = parts[: depth + 1]
        _ensure_location_node(model, prefix, root_name=root_name)


def build_physical_model(
    project_path: Path,
    yaml_files: list[Path],
    *,
    title: str = "",
) -> PhysModel:
    """Build location↔conduit graph (physical layer)."""
    from housewire.house import is_place_type

    root_name = project_path.name
    model = PhysModel(title=title or root_name)
    pieces = _load_house_files(project_path, yaml_files)
    known: set[tuple[str, ...]] = {tuple(parts) for parts, _ in pieces}
    fragment_locations = set(known)

    # Pass 1: one node per location (place), not per electrical element.
    for location_parts, fragment in pieces:
        place_meta = _leaf_place_meta(fragment, location_parts)
        leaf_label = str(place_meta["label"]) if place_meta.get("label") else None
        if not location_parts and leaf_label is None:
            leaf_label = root_name
        type_id = str(place_meta.get("type") or "Location")
        subtitle = ""
        if place_meta.get("type"):
            bits = [str(place_meta.get("type"))]
            if place_meta.get("subtype"):
                bits.append(str(place_meta["subtype"]))
            if place_meta.get("notes"):
                bits.append(str(place_meta["notes"]).replace("\n", " "))
            if place_meta.get("install"):
                bits.append(f"install={place_meta['install']}")
            subtitle = " | ".join(bits)
        parts = tuple(location_parts)
        _ensure_ancestor_nodes(model, parts, root_name=root_name)
        _ensure_location_node(
            model,
            parts,
            type_id=type_id if is_place_type(type_id) else "Location",
            label=leaf_label,
            subtitle=subtitle,
            root_name=root_name,
        )

    # Pass 2: conduits → edges between locations.
    for location_parts, fragment in pieces:
        for conduit_name, conduit in (fragment.get("conduits") or {}).items():
            if not isinstance(conduit, dict):
                continue
            try:
                ends = conduit_endpoints(conduit)
            except ValueError:
                continue
            from_ref, to_ref = ends
            try:
                from_loc_ref, from_op = split_conduit_endpoint(from_ref)
                to_loc_ref, to_op = split_conduit_endpoint(to_ref)
            except ValueError:
                continue

            from_parts = resolve_location_ref(
                from_loc_ref, current_parts=location_parts, known=known
            )
            to_parts = resolve_location_ref(
                to_loc_ref, current_parts=location_parts, known=known
            )
            known.add(from_parts)
            known.add(to_parts)

            _ensure_ancestor_nodes(model, from_parts, root_name=root_name)
            _ensure_ancestor_nodes(model, to_parts, root_name=root_name)
            from_key = _ensure_location_node(
                model,
                from_parts,
                external=from_parts not in fragment_locations,
                root_name=root_name,
            )
            to_key = _ensure_location_node(
                model,
                to_parts,
                external=to_parts not in fragment_locations,
                root_name=root_name,
            )

            label = f"{conduit_name}\\n{from_op} ↔ {to_op}"
            model.edges.append(
                PhysEdge(
                    src=from_key,
                    dst=to_key,
                    label=label,
                    src_port=opening_compass_port(from_op),
                    dst_port=opening_compass_port(to_op),
                )
            )

    return model


def _immediate_children(
    parent: tuple[str, ...], all_parts: set[tuple[str, ...]]
) -> list[tuple[str, ...]]:
    depth = len(parent)
    kids = [
        p
        for p in all_parts
        if len(p) == depth + 1 and p[:depth] == parent
    ]
    return sorted(kids)


def _node_label(node: PhysNode) -> str:
    """Single label for a location node (no separate cluster duplicate)."""
    label = node.display_label.replace('"', "'")
    if node.subtitle:
        sub = node.subtitle.replace('"', "'")
        return f"{label}\\n{sub}"
    if node.type_id and node.type_id not in ("Location",):
        return f"{label}\\n{node.type_id}"
    return label


def _emit_node(lines: list[str], node: PhysNode, *, indent: str) -> None:
    title = _node_label(node)
    shape = "oval" if node.type_id == "External" else "box"
    fill = "lightyellow" if node.type_id == "External" else "white"
    lines.append(
        f'{indent}{node.node_id} [label="{title}", shape={shape}, '
        f'style="rounded,filled", fillcolor={fill}];'
    )


def _emit_location(
    lines: list[str],
    model: PhysModel,
    parts: tuple[str, ...],
    all_parts: set[tuple[str, ...]],
    endpoints: set[str],
    *,
    indent: str,
) -> None:
    """Emit nested clusters for containers; a node only once (leaves / edge ends)."""
    key = location_key(parts)
    node = model.nodes[key]
    kids = _immediate_children(parts, all_parts)
    is_endpoint = key in endpoints

    if kids:
        # Container: cluster frame only; node only if conduits attach here.
        cid = node.node_id
        label = node.display_label.replace('"', "'")
        subtitle = node.subtitle.replace('"', "'")
        full_label = f"{label}\\n{subtitle}" if subtitle else label
        lines.append(f"{indent}subgraph cluster_{cid} {{")
        lines.append(f'{indent}  label="{full_label}";')
        lines.append(f"{indent}  style=rounded;")
        lines.append(f"{indent}  color=gray50;")
        if is_endpoint:
            _emit_node(lines, node, indent=indent + "  ")
        for child in kids:
            _emit_location(
                lines, model, child, all_parts, endpoints, indent=indent + "  "
            )
        lines.append(f"{indent}}}")
        return

    # Leaf: one node, no wrapping cluster with the same name.
    _emit_node(lines, node, indent=indent)


def model_to_dot(model: PhysModel) -> str:
    lines: list[str] = [
        "digraph physical {",
        # Free layout. No compass ports: Graphviz clips each edge to the
        # border facing the neighbor (better than forcing YAML opening faces).
        "  rankdir=LR;",
        "  compound=true;",
        "  splines=true;",
        "  nodesep=0.5;",
        "  ranksep=0.6;",
        "  graph [fontname=Arial, fontsize=12, pad=0.3];",
        "  node [fontname=Arial, fontsize=10, shape=box, style=rounded];",
        "  edge [fontname=Arial, fontsize=8, dir=none, headclip=true, tailclip=true];",
    ]
    if model.title:
        lines.append(f'  labelloc="t"; label="{model.title}";')

    all_parts = {node.parts for node in model.nodes.values()}
    endpoints = {edge.src for edge in model.edges} | {edge.dst for edge in model.edges}

    if () in all_parts:
        _emit_location(lines, model, (), all_parts, endpoints, indent="  ")
    else:
        for top in _immediate_children((), all_parts):
            _emit_location(lines, model, top, all_parts, endpoints, indent="  ")

    seen: set[tuple[str, str, str]] = set()
    for edge in model.edges:
        src = model.nodes[edge.src].node_id
        dst = model.nodes[edge.dst].node_id
        key = (src, dst, edge.label)
        if key in seen:
            continue
        seen.add(key)
        label = edge.label.replace('"', "'")
        lines.append(f'  {src} -> {dst} [label="{label}"];')

    lines.append("}")
    return "\n".join(lines) + "\n"


def render_physical_svg(dot_text: str, svg_path: Path, *, also_dot: bool = True) -> None:
    if shutil.which("dot") is None:
        raise RuntimeError("No se encontro 'dot' (Graphviz).")
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    if also_dot:
        svg_path.with_suffix(".dot").write_text(dot_text, encoding="utf-8")
    proc = subprocess.run(
        ["dot", "-Tsvg", "-o", str(svg_path)],
        input=dot_text.encode("utf-8"),
        check=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace"))


def export_physical_zone(
    project_path: Path,
    yaml_files: list[Path],
    output_svg: Path,
    *,
    title: str,
) -> None:
    model = build_physical_model(project_path, yaml_files, title=title)
    if not model.nodes:
        return
    render_physical_svg(model_to_dot(model), output_svg)
