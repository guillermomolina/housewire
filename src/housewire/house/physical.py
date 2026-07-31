"""Physical topology diagram from house/v1 (locations + conduits).

Physical layer only: location nodes linked by conduits (openings).
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


@dataclass
class PhysNode:
    node_id: str
    title: str
    type_id: str
    cluster_id: str
    cluster_label: str
    cluster_subtitle: str = ""


@dataclass
class PhysEdge:
    src: str
    dst: str
    label: str


@dataclass
class PhysModel:
    nodes: dict[str, PhysNode] = field(default_factory=dict)
    edges: list[PhysEdge] = field(default_factory=list)
    title: str = ""


def _cluster_label(parts: list[str], *, leaf_label: str | None = None) -> str:
    if not parts:
        return "raiz"
    display = list(parts)
    if leaf_label:
        display[-1] = leaf_label
    return " / ".join(display)


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
) -> str:
    key = location_key(parts)
    if key in model.nodes:
        return key
    leaf = parts[-1] if parts else "raiz"
    display_label = label or leaf
    title = f"{display_label}\\n{type_id}"
    if external:
        title = f"{display_label}\\n(externo)"
        type_id = "External"
    cluster_label = _cluster_label(list(parts), leaf_label=label)
    model.nodes[key] = PhysNode(
        node_id=_safe_id(key),
        title=title,
        type_id=type_id,
        cluster_id=_safe_id(key),
        cluster_label=cluster_label,
        cluster_subtitle=subtitle,
    )
    return key


def build_physical_model(
    project_path: Path,
    yaml_files: list[Path],
    *,
    title: str = "",
) -> PhysModel:
    """Build location↔conduit graph (physical layer)."""
    from housewire.house import is_place_type

    model = PhysModel(title=title or project_path.name)
    pieces = _load_house_files(project_path, yaml_files)
    known: set[tuple[str, ...]] = {tuple(parts) for parts, _ in pieces}
    fragment_locations = set(known)

    # Pass 1: one node per location (place), not per electrical element.
    for location_parts, fragment in pieces:
        place_meta = _leaf_place_meta(fragment, location_parts)
        leaf_label = str(place_meta["label"]) if place_meta.get("label") else None
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
        _ensure_location_node(
            model,
            tuple(location_parts),
            type_id=type_id if is_place_type(type_id) else "Location",
            label=leaf_label,
            subtitle=subtitle,
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
            if ends is None:
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

            from_key = _ensure_location_node(
                model,
                from_parts,
                external=from_parts not in fragment_locations,
            )
            to_key = _ensure_location_node(
                model,
                to_parts,
                external=to_parts not in fragment_locations,
            )

            contains = [str(c) for c in (conduit.get("contains") or [])]
            short_name = str(conduit_name)
            label_bits = [short_name, f"{from_op} ↔ {to_op}"]
            if contains:
                label_bits.append(", ".join(contains))
            model.edges.append(
                PhysEdge(src=from_key, dst=to_key, label="\\n".join(label_bits))
            )

    return model


def model_to_dot(model: PhysModel) -> str:
    lines: list[str] = [
        "digraph physical {",
        "  rankdir=LR;",
        "  graph [fontname=Arial, fontsize=12, pad=0.3];",
        "  node [fontname=Arial, fontsize=10, shape=box, style=rounded];",
        "  edge [fontname=Arial, fontsize=8];",
    ]
    if model.title:
        lines.append(f'  labelloc="t"; label="{model.title}";')

    clusters: dict[str, list[PhysNode]] = {}
    for node in model.nodes.values():
        clusters.setdefault(node.cluster_id, []).append(node)

    for cluster_id, nodes in sorted(clusters.items(), key=lambda item: item[1][0].cluster_label):
        label = nodes[0].cluster_label.replace('"', "'")
        subtitle = nodes[0].cluster_subtitle.replace('"', "'")
        full_label = f"{label}\n{subtitle}" if subtitle else label
        lines.append(f"  subgraph cluster_{cluster_id} {{")
        lines.append(f'    label="{full_label}";')
        lines.append("    style=rounded;")
        lines.append("    color=gray50;")
        for node in nodes:
            title = node.title.replace('"', "'")
            shape = "oval" if node.type_id == "External" else "box"
            fill = "lightyellow" if node.type_id == "External" else "white"
            lines.append(
                f'    {node.node_id} [label="{title}", shape={shape}, '
                f'style="rounded,filled", fillcolor={fill}];'
            )
        lines.append("  }")

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
