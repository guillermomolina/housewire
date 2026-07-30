"""Physical topology diagram from house/v1 (boxes, elements, conduits).

Not WireViz: no pin tables. Graphviz clusters by location folder.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from housewire.house import (
    is_house_document,
    location_prefix,
    normalize_token,
    path_location_parts,
    prefixed_name,
)

_OPENING_RE = re.compile(
    r"abertura\s+(B\d+|[NSEWUD](?:\.[A-Za-z0-9]+)?|(?:back|lid|fondo|tapa)(?:\.[A-Za-z0-9]+)?)",
    re.IGNORECASE,
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


def _cluster_label(parts: list[str]) -> str:
    return " / ".join(parts) if parts else "(raiz)"


def _safe_id(value: str) -> str:
    return normalize_token(value) or "n"


def _openings_from_text(*texts: str) -> list[str]:
    found: list[str] = []
    for text in texts:
        if not text:
            continue
        for match in _OPENING_RE.finditer(str(text)):
            token = match.group(1)
            if token not in found:
                found.append(token)
    return found


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
        if not fragments and any(
            key in data
            for key in ("elements", "cables", "connections", "conduits", "location")
        ):
            frag = {
                key: data[key]
                for key in ("elements", "cables", "connections", "conduits")
                if key in data
            }
            fragments = [(base, frag)] if frag or isinstance(data.get("location"), dict) else []
            if not fragments and isinstance(data.get("location"), dict):
                fragments = _walk_locations(data, base)
        pieces.extend(fragments)
    return pieces


def build_physical_model(
    project_path: Path,
    yaml_files: list[Path],
    *,
    title: str = "",
) -> PhysModel:
    from housewire.house import (
        _expand_endpoint_token,
        _normalize_local_element_ref,
        _parse_via_wires,
        _split_element_terminal,
        is_place_type,
    )

    model = PhysModel(title=title or project_path.name)
    cable_openings: dict[str, list[str]] = {}

    for location_parts, fragment in _load_house_files(project_path, yaml_files):
        prefix = location_prefix(location_parts)
        cluster_id = _safe_id(prefix or "raiz")
        cluster_label = _cluster_label(location_parts)

        # Collect place metadata (location:) for cluster subtitle
        cluster_subtitle = ""
        for _name, definition in (fragment.get("elements") or {}).items():
            if isinstance(definition, dict) and is_place_type(definition.get("type")):
                parts_sub: list[str] = [str(definition.get("type"))]
                if definition.get("subtype"):
                    parts_sub.append(str(definition["subtype"]))
                if definition.get("notes"):
                    parts_sub.append(str(definition["notes"]).replace("\n", " "))
                cluster_subtitle = " | ".join(parts_sub)
                break

        element_map: dict[str, str] = {}
        for name, definition in (fragment.get("elements") or {}).items():
            if not isinstance(definition, dict):
                continue
            type_id = str(definition.get("type") or "?")
            if is_place_type(type_id):
                continue  # no physical node for place types
            qname = prefixed_name(prefix, str(name))
            element_map[str(name)] = qname
            label = str(definition.get("label") or name)
            extra = f"\\n{label}" if label and label != str(name) else ""
            model.nodes[qname] = PhysNode(
                node_id=_safe_id(qname),
                title=f"{name}\\n{type_id}{extra}",
                type_id=type_id,
                cluster_id=cluster_id,
                cluster_label=cluster_label,
                cluster_subtitle=cluster_subtitle,
            )

        cable_map: dict[str, str] = {}
        for name in fragment.get("cables") or {}:
            cable_map[str(name)] = prefixed_name(prefix, str(name))

        for _conduit_name, conduit in (fragment.get("conduits") or {}).items():
            if not isinstance(conduit, dict):
                continue
            openings = _openings_from_text(
                str(conduit.get("route") or ""),
                str(conduit.get("notes") or ""),
            )
            for cable_ref in conduit.get("contains") or []:
                cref = str(cable_ref)
                qcable = cable_map.get(cref, prefixed_name(prefix, cref))
                cable_openings.setdefault(qcable, [])
                for op in openings:
                    if op not in cable_openings[qcable]:
                        cable_openings[qcable].append(op)

        for conn in fragment.get("connections") or []:
            if not isinstance(conn, dict):
                continue
            if "from" not in conn or "to" not in conn or "via" not in conn:
                continue
            try:
                from_tokens = _expand_endpoint_token(str(conn["from"]))
                to_tokens = _expand_endpoint_token(str(conn["to"]))
                from_pairs = [_split_element_terminal(t) for t in from_tokens]
                to_pairs = [_split_element_terminal(t) for t in to_tokens]
                from_el = _normalize_local_element_ref(
                    from_pairs[0][0],
                    current_location=location_parts,
                    local_prefix=prefix,
                    local_map=element_map,
                )
                to_el = _normalize_local_element_ref(
                    to_pairs[0][0],
                    current_location=location_parts,
                    local_prefix=prefix,
                    local_map=element_map,
                )
                cable_name, _wires = _parse_via_wires(
                    str(conn["via"]),
                    cable_map,
                    prefix,
                    current_location=location_parts,
                )
            except (ValueError, KeyError, IndexError):
                continue

            for el in (from_el, to_el):
                if el in model.nodes:
                    continue
                short = el.rsplit("_", 1)[-1]
                model.nodes[el] = PhysNode(
                    node_id=_safe_id(el),
                    title=f"{short}\\n(externo)",
                    type_id="External",
                    cluster_id="externo",
                    cluster_label="externo",
                )

            parts = cable_name.split("__")
            short_cable = parts[-1] if parts else cable_name
            openings = cable_openings.get(cable_name) or []
            label_bits = [short_cable]
            if openings:
                label_bits.append(" · ".join(openings))
            model.edges.append(
                PhysEdge(src=from_el, dst=to_el, label="\\n".join(label_bits))
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
