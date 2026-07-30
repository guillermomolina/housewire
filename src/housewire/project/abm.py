from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from housewire.house import load_catalog
from housewire.project.io import load_yaml, require_house_document, save_yaml
from housewire.project.validate import validate_house_document

_ELEMENT_REF_RE = re.compile(r"(?:^|[./\[])([A-Za-z_][A-Za-z0-9_]*)")
_PEND_CABLE_RE = re.compile(r"^PEND_Linea_(\d+)$")

DEFAULT_CABLE_SECTION = "1.5 mm2"
DEFAULT_CABLE_COLORS = ["BN", "BU"]


def _ensure_maps(doc: dict[str, Any]) -> None:
    doc.setdefault("elements", {})
    doc.setdefault("cables", {})
    doc.setdefault("connections", [])
    doc.setdefault("conduits", {})


def normalize_section(raw: str | None) -> str:
    """Acepta '1.5' o '1.5 mm2' → '1.5 mm2'."""
    if raw is None or not str(raw).strip():
        return DEFAULT_CABLE_SECTION
    text = str(raw).strip()
    if "mm" in text.lower():
        return text
    return f"{text} mm2"


def _connection_text(conn: object) -> str:
    if isinstance(conn, dict):
        return " ".join(str(conn.get(k, "")) for k in ("from", "via", "to"))
    if isinstance(conn, list):
        parts: list[str] = []
        for endpoint in conn:
            if isinstance(endpoint, dict):
                parts.extend(str(k) for k in endpoint)
        return " ".join(parts)
    return str(conn)


def connections_referencing_element(doc: dict[str, Any], element_name: str) -> list[int]:
    hits: list[int] = []
    for index, conn in enumerate(doc.get("connections") or []):
        text = _connection_text(conn)
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(element_name)}(?=\.|\[|$)", text):
            hits.append(index)
    return hits


def load_editable(path: Path, project_path: Path) -> dict[str, Any]:
    doc = load_yaml(path)
    require_house_document(doc, path)
    return doc


def persist(doc: dict[str, Any], path: Path, project_path: Path) -> None:
    require_house_document(doc, path)
    validate_house_document(doc, project_path=project_path, yaml_path=path)
    save_yaml(path, doc)


def add_element(
    doc: dict[str, Any],
    name: str,
    *,
    type_id: str,
    subtype: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    label: str | None = None,
    notes: str | None = None,
) -> None:
    _ensure_maps(doc)
    catalog = load_catalog()
    if type_id not in catalog:
        raise ValueError(f"Tipo de catalogo desconocido: {type_id}")
    elements = doc["elements"]
    if not isinstance(elements, dict):
        raise ValueError("elements debe ser un mapa")
    if name in elements:
        raise ValueError(f"Ya existe el elemento: {name}")
    entry: dict[str, Any] = {"type": type_id}
    defaults = (catalog[type_id].get("defaults") or {}) if isinstance(catalog[type_id], dict) else {}
    if subtype is None and defaults.get("subtype") is not None:
        subtype = str(defaults["subtype"])
    if subtype is not None:
        entry["subtype"] = subtype
    if manufacturer:
        entry["manufacturer"] = manufacturer
    if model:
        entry["model"] = model
    if label:
        entry["label"] = label
    if notes:
        entry["notes"] = notes
    elements[name] = entry


def rm_element(doc: dict[str, Any], name: str) -> None:
    _ensure_maps(doc)
    elements = doc["elements"]
    if not isinstance(elements, dict) or name not in elements:
        raise ValueError(f"No existe el elemento: {name}")
    refs = connections_referencing_element(doc, name)
    if refs:
        raise ValueError(
            f"No se puede borrar {name}: referenciado en conexiones {refs}. "
            "Borra esas conexiones primero."
        )
    del elements[name]


def add_cable(
    doc: dict[str, Any],
    name: str,
    *,
    kind: str = "power",
    section: str | None = None,
    colors: list[str] | None = None,
    notes: str | None = None,
) -> None:
    _ensure_maps(doc)
    cables = doc["cables"]
    if not isinstance(cables, dict):
        raise ValueError("cables debe ser un mapa")
    if name in cables:
        raise ValueError(f"Ya existe el cable: {name}")
    resolved_colors = list(colors) if colors is not None else list(DEFAULT_CABLE_COLORS)
    if not resolved_colors:
        raise ValueError("colors no puede estar vacio")
    entry: dict[str, Any] = {
        "kind": kind,
        "section": normalize_section(section),
        "colors": resolved_colors,
    }
    if notes:
        entry["notes"] = notes
    cables[name] = entry


def rm_cable(doc: dict[str, Any], name: str) -> None:
    _ensure_maps(doc)
    cables = doc["cables"]
    if not isinstance(cables, dict) or name not in cables:
        raise ValueError(f"No existe el cable: {name}")
    refs: list[int] = []
    for index, conn in enumerate(doc.get("connections") or []):
        if name in _connection_text(conn):
            refs.append(index)
    if refs:
        raise ValueError(
            f"No se puede borrar cable {name}: referenciado en conexiones {refs}."
        )
    conduits = doc.get("conduits") or {}
    if isinstance(conduits, dict):
        for conduit_name, conduit in conduits.items():
            if not isinstance(conduit, dict):
                continue
            contains = [str(c) for c in (conduit.get("contains") or [])]
            if name in contains:
                raise ValueError(
                    f"No se puede borrar cable {name}: referenciado en conduit {conduit_name}."
                )
    del cables[name]


def next_pend_cable_name(doc: dict[str, Any]) -> str:
    cables = doc.get("cables") or {}
    max_n = 0
    if isinstance(cables, dict):
        for name in cables:
            match = _PEND_CABLE_RE.match(str(name))
            if match:
                max_n = max(max_n, int(match.group(1)))
    return f"PEND_Linea_{max_n + 1:02d}"


def add_conduit(
    doc: dict[str, Any],
    name: str,
    *,
    contains: list[str],
    route: str | None = None,
    type_id: str | None = None,
    notes: str | None = None,
    kind: str = "conduit",
) -> None:
    _ensure_maps(doc)
    conduits = doc["conduits"]
    if not isinstance(conduits, dict):
        raise ValueError("conduits debe ser un mapa")
    if name in conduits:
        raise ValueError(f"Ya existe el conduit: {name}")
    if not contains:
        raise ValueError("contains no puede estar vacio")
    cables = doc.get("cables") or {}
    for cable_ref in contains:
        if str(cable_ref) not in cables:
            raise ValueError(f"Conduit referencia cable inexistente: {cable_ref}")
    entry: dict[str, Any] = {"kind": kind, "contains": [str(c) for c in contains]}
    if type_id:
        entry["type"] = type_id
    if route:
        entry["route"] = route
    if notes:
        entry["notes"] = notes
    conduits[name] = entry


def add_pending_cable(
    doc: dict[str, Any],
    *,
    enter: str,
    exit: str,
    section: str | None = None,
    colors: list[str] | None = None,
    kind: str = "power",
    notes: str | None = None,
) -> tuple[str, str]:
    """Crea cable PEND_* + conduit de paso sin connections.

    Returns (cable_name, conduit_name).
    """
    enter_s = str(enter).strip()
    exit_s = str(exit).strip()
    if not enter_s or not exit_s:
        raise ValueError("enter y exit (aberturas) son obligatorios")
    cable_name = next_pend_cable_name(doc)
    suffix = cable_name.rsplit("_", 1)[-1]
    conduit_name = f"Conducto_paso_{suffix}"
    note_bits = [f"estado: pendiente; entra por {enter_s} y sale por {exit_s}"]
    if notes:
        note_bits.append(str(notes))
    add_cable(
        doc,
        cable_name,
        kind=kind,
        section=section,
        colors=colors,
        notes="; ".join(note_bits),
    )
    add_conduit(
        doc,
        conduit_name,
        contains=[cable_name],
        route=f"abertura {enter_s} ↔ abertura {exit_s} ↔ destino pendiente",
    )
    return cable_name, conduit_name


def add_connection(
    doc: dict[str, Any],
    *,
    from_ref: str,
    via_ref: str,
    to_ref: str,
) -> None:
    _ensure_maps(doc)
    connections = doc["connections"]
    if not isinstance(connections, list):
        raise ValueError("connections debe ser una lista")
    connections.append({"from": from_ref, "via": via_ref, "to": to_ref})


def rm_connection(doc: dict[str, Any], index: int) -> None:
    _ensure_maps(doc)
    connections = doc["connections"]
    if not isinstance(connections, list):
        raise ValueError("connections debe ser una lista")
    if index < 0 or index >= len(connections):
        raise ValueError(f"Indice de conexion invalido: {index}")
    del connections[index]


def format_show(doc: dict[str, Any], *, element: str | None = None, cable: str | None = None) -> str:
    lines: list[str] = []
    if element:
        el = (doc.get("elements") or {}).get(element)
        if el is None:
            raise ValueError(f"No existe el elemento: {element}")
        lines.append(f"element {element}:")
        import yaml as _yaml

        lines.append(_yaml.safe_dump(el, sort_keys=False, allow_unicode=True).rstrip())
        return "\n".join(lines)
    if cable:
        cb = (doc.get("cables") or {}).get(cable)
        if cb is None:
            raise ValueError(f"No existe el cable: {cable}")
        lines.append(f"cable {cable}:")
        import yaml as _yaml

        lines.append(_yaml.safe_dump(cb, sort_keys=False, allow_unicode=True).rstrip())
        return "\n".join(lines)

    location_block = doc.get("location")
    if isinstance(location_block, dict):
        import yaml as _yaml

        type_id = location_block.get("type", "?")
        lines.append(f"location ({type_id}):")
        lines.append(
            _yaml.safe_dump(location_block, sort_keys=False, allow_unicode=True).rstrip()
        )
        lines.append("")

    elements = doc.get("elements") or {}
    cables = doc.get("cables") or {}
    connections = doc.get("connections") or []
    conduits = doc.get("conduits") or {}
    lines.append(f"elements ({len(elements)}):")
    for name in sorted(elements):
        t = elements[name].get("type", "?") if isinstance(elements[name], dict) else "?"
        lines.append(f"  {name} ({t})")
    lines.append(f"cables ({len(cables)}):")
    for name in sorted(cables):
        lines.append(f"  {name}")
    lines.append(f"conduits ({len(conduits)}):")
    for name in sorted(conduits):
        lines.append(f"  {name}")
    lines.append(f"connections ({len(connections)}):")
    for i, conn in enumerate(connections):
        lines.append(f"  [{i}] {conn}")
    return "\n".join(lines)
