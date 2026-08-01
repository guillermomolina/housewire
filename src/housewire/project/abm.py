from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml

from housewire.house import (
    DEFAULT_CABLE_TYPE,
    DEFAULT_CONDUIT_TYPE,
    expand_cable,
    is_place_type,
    load_catalog,
    place_meta_from_mapping,
)
from housewire.project.io import load_yaml, require_house_document, save_yaml
from housewire.project.openings import (
    declared_opening_ids,
    normalize_opening_id,
    validate_location_openings,
)
from housewire.project.validate import validate_house_document

_ELEMENT_REF_RE = re.compile(r"(?:^|[./\[])([A-Za-z_][A-Za-z0-9_]*)")
_PEND_CABLE_RE = re.compile(r"^PEND_Linea_(\d+)$")

DEFAULT_CABLE_SECTION = "1.5 mm2"
DEFAULT_CABLE_COLORS = ["BN", "BU"]
DEFAULT_CABLE_SUBTYPE = "power"
DEFAULT_CONDUIT_SUBTYPE = "tube"

# Structural keys — use add/rm instead of set.
RESERVED_SET_KEYS = frozenset(
    {"schema", "elements", "cables", "connections", "conduits"}
)

SetTarget = Literal["place", "element"]



def declared_openings(doc: dict[str, Any]) -> set[str] | None:
    """Return opening ids if place openings are declared, else ``None``."""
    meta = place_meta_from_mapping(doc)
    if meta is None:
        return None
    return declared_opening_ids(meta.get("openings"))


def require_opening_ids(doc: dict[str, Any], *opening_ids: str) -> None:
    """If openings are declared, each id must exist on this place."""
    meta = place_meta_from_mapping(doc)
    if meta is not None:
        validate_location_openings(meta)
    declared = declared_openings(doc)
    if declared is None:
        return
    normalized = [normalize_opening_id(oid) for oid in opening_ids]
    missing = [oid for oid in normalized if oid not in declared]
    if missing:
        known = ", ".join(sorted(declared)) or "(none)"
        raise ValueError(
            "Opening(s) not declared in openings: "
            + ", ".join(missing)
            + f". Declared: {known}"
        )


def _ensure_maps(doc: dict[str, Any]) -> None:
    doc.setdefault("elements", {})
    doc.setdefault("cables", {})
    doc.setdefault("connections", [])
    doc.setdefault("conduits", {})


def parse_set_value(raw: str) -> Any:
    """Parse a shell/CLI value as YAML (scalar, list, or map).

    On YAML syntax errors, keep the raw string so values like notes with
    ``key: value`` fragments still work.
    """
    text = str(raw)
    stripped = text.strip()
    if stripped == "":
        return ""
    try:
        return yaml.safe_load(stripped)
    except yaml.YAMLError:
        return text


def parse_set_spec(spec: str) -> tuple[str, Any | None]:
    """Parse ``KEY=VALUE`` (set) or ``KEY`` (unset → value None)."""
    text = str(spec).strip()
    if not text:
        raise ValueError("empty set: use KEY=VALUE or KEY")
    if "=" not in text:
        return text, None
    key, _, raw_val = text.partition("=")
    key = key.strip()
    if not key:
        raise ValueError(f"Invalid key in --set: {spec!r}")
    return key, parse_set_value(raw_val)


def _split_field_key(key: str) -> tuple[str, str | None]:
    text = str(key).strip()
    if not text:
        raise ValueError("empty key")
    if "." not in text:
        return text, None
    root, _, nested = text.partition(".")
    root = root.strip()
    nested = nested.strip()
    if not root or not nested:
        raise ValueError(f"Invalid nested key: {key!r}")
    if "." in nested:
        raise ValueError(
            f"Only one nesting level (parent.child): {key!r}"
        )
    return root, nested


def _validate_type_field(value: Any, *, target: SetTarget) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("type must be a non-empty string")
    type_id = value.strip()
    if target == "place":
        if not is_place_type(type_id):
            raise ValueError(
                f"Unknown place type: {type_id!r}. "
                "Use Room|Stair|JunctionBox|DeviceBox|LightPoint|Panel|Floor|House (or Location)."
            )
        return
    catalog = load_catalog()
    if type_id not in catalog:
        raise ValueError(f"Unknown catalog type: {type_id}")


def _maybe_validate_openings(mapping: dict[str, Any], root_key: str) -> None:
    if root_key in {"openings", "opening_grid"}:
        validate_location_openings(mapping)


def set_field(
    mapping: dict[str, Any],
    key: str,
    value: Any,
    *,
    target: SetTarget = "place",
) -> None:
    """Set a property on a place or element mapping (in memory)."""
    if not isinstance(mapping, dict):
        raise ValueError("set target must be a map")
    root_key, nested_key = _split_field_key(key)
    if root_key in RESERVED_SET_KEYS:
        raise ValueError(
            f"Reserved key {root_key!r}: use add/rm (not set)"
        )
    if root_key == "type" and nested_key is None:
        _validate_type_field(value, target=target)

    if nested_key is None:
        mapping[root_key] = value
    else:
        container = mapping.get(root_key)
        if container is None:
            container = {}
            mapping[root_key] = container
        elif not isinstance(container, dict):
            raise ValueError(f"{root_key!r} is not a map; cannot nest")
        container[nested_key] = value

    _maybe_validate_openings(mapping, root_key)


def unset_field(mapping: dict[str, Any], key: str) -> None:
    """Remove a property from a place or element mapping."""
    if not isinstance(mapping, dict):
        raise ValueError("unset target must be a map")
    root_key, nested_key = _split_field_key(key)
    if root_key in RESERVED_SET_KEYS:
        raise ValueError(
            f"Reserved key {root_key!r}: use add/rm (not unset)"
        )
    if nested_key is None:
        if root_key not in mapping:
            raise ValueError(f"Key does not exist: {key}")
        del mapping[root_key]
    else:
        container = mapping.get(root_key)
        if not isinstance(container, dict) or nested_key not in container:
            raise ValueError(f"Key does not exist: {key}")
        del container[nested_key]
        if not container:
            del mapping[root_key]
    _maybe_validate_openings(mapping, root_key)


def apply_set_specs(
    mapping: dict[str, Any],
    specs: list[str],
    *,
    target: SetTarget = "place",
) -> None:
    """Apply ``KEY=VALUE`` / ``KEY`` (unset) specs to ``mapping``."""
    for spec in specs:
        key, value = parse_set_spec(spec)
        if value is None:
            unset_field(mapping, key)
        else:
            set_field(mapping, key, value, target=target)


def normalize_section(raw: str | None, *, default: str | None = None) -> str:
    """Accept '1.5' or '1.5 mm2' → '1.5 mm2'."""
    fallback = default if default is not None else DEFAULT_CABLE_SECTION
    if raw is None or not str(raw).strip():
        return fallback
    text = str(raw).strip()
    if "mm" in text.lower():
        return text
    return f"{text} mm2"


def _cable_catalog_defaults(
    *,
    type_id: str = DEFAULT_CABLE_TYPE,
    subtype: str | None = DEFAULT_CABLE_SUBTYPE,
) -> dict[str, Any]:
    """Resolve section/colors defaults from catalog for ABM writers."""
    expanded = expand_cable(
        {"type": type_id, **({"subtype": subtype} if subtype else {})},
        load_catalog(),
    )
    return {
        "section": expanded.get("section") or DEFAULT_CABLE_SECTION,
        "colors": list(expanded.get("colors") or DEFAULT_CABLE_COLORS),
    }


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
        raise ValueError(f"Unknown catalog type: {type_id}")
    elements = doc["elements"]
    if not isinstance(elements, dict):
        raise ValueError("elements must be a map")
    if name in elements:
        raise ValueError(f"Element already exists: {name}")
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
        raise ValueError(f"Element does not exist: {name}")
    refs = connections_referencing_element(doc, name)
    if refs:
        raise ValueError(
            f"Cannot delete {name}: referenced in connections {refs}. "
            "Delete those connections first."
        )
    del elements[name]


def add_cable(
    doc: dict[str, Any],
    name: str,
    *,
    type_id: str = DEFAULT_CABLE_TYPE,
    subtype: str | None = DEFAULT_CABLE_SUBTYPE,
    kind: str | None = None,
    section: str | None = None,
    colors: list[str] | None = None,
    label: str | None = None,
    notes: str | None = None,
) -> None:
    _ensure_maps(doc)
    cables = doc["cables"]
    if not isinstance(cables, dict):
        raise ValueError("cables must be a map")
    if name in cables:
        raise ValueError(f"Cable already exists: {name}")
    resolved_subtype = subtype if kind is None else kind
    defaults = _cable_catalog_defaults(type_id=type_id, subtype=resolved_subtype)
    resolved_colors = list(colors) if colors is not None else list(defaults["colors"])
    if not resolved_colors:
        raise ValueError("colors cannot be empty")
    entry: dict[str, Any] = {
        "type": type_id,
        "section": normalize_section(section, default=str(defaults["section"])),
        "colors": resolved_colors,
    }
    if resolved_subtype is not None:
        entry["subtype"] = resolved_subtype
    if label:
        entry["label"] = label
    if notes:
        entry["notes"] = notes
    # Validate against catalog (raises on bad type).
    expand_cable(entry, load_catalog())
    cables[name] = entry


def rm_cable(doc: dict[str, Any], name: str) -> None:
    _ensure_maps(doc)
    cables = doc["cables"]
    if not isinstance(cables, dict) or name not in cables:
        raise ValueError(f"Cable does not exist: {name}")
    refs: list[int] = []
    for index, conn in enumerate(doc.get("connections") or []):
        if name in _connection_text(conn):
            refs.append(index)
    if refs:
        raise ValueError(
            f"Cannot delete cable {name}: referenced in connections {refs}."
        )
    conduits = doc.get("conduits") or {}
    if isinstance(conduits, dict):
        for conduit_name, conduit in conduits.items():
            if not isinstance(conduit, dict):
                continue
            contains = [str(c) for c in (conduit.get("contains") or [])]
            if name in contains:
                raise ValueError(
                    f"Cannot delete cable {name}: referenced in conduit {conduit_name}."
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
    from_ref: str,
    to_ref: str,
    type_id: str = DEFAULT_CONDUIT_TYPE,
    subtype: str | None = DEFAULT_CONDUIT_SUBTYPE,
    label: str | None = None,
    notes: str | None = None,
    kind: str | None = None,
) -> None:
    _ensure_maps(doc)
    conduits = doc["conduits"]
    if not isinstance(conduits, dict):
        raise ValueError("conduits must be a map")
    if name in conduits:
        raise ValueError(f"Conduit already exists: {name}")
    if not contains:
        raise ValueError("contains cannot be empty")
    cables = doc.get("cables") or {}
    for cable_ref in contains:
        if str(cable_ref) not in cables:
            raise ValueError(f"Conduit references missing cable: {cable_ref}")
    from housewire.house.conduit_ref import split_conduit_endpoint

    split_conduit_endpoint(from_ref)
    split_conduit_endpoint(to_ref)
    # Legacy: kind was always "conduit"; type_id used to mean physical size.
    resolved_type = type_id
    resolved_subtype = subtype
    if kind is not None and kind != "conduit" and resolved_subtype is None:
        resolved_subtype = kind
    entry: dict[str, Any] = {
        "type": resolved_type,
        "from": str(from_ref).strip(),
        "to": str(to_ref).strip(),
        "contains": [str(c) for c in contains],
    }
    if resolved_subtype is not None:
        entry["subtype"] = resolved_subtype
    if label:
        entry["label"] = label
    if notes:
        entry["notes"] = notes
    from housewire.house import expand_conduit

    expand_conduit(entry, load_catalog())
    conduits[name] = entry


def add_pending_cable(
    doc: dict[str, Any],
    *,
    enter: str,
    exit: str,
    section: str | None = None,
    colors: list[str] | None = None,
    subtype: str | None = DEFAULT_CABLE_SUBTYPE,
    kind: str | None = None,
    label: str | None = None,
    notes: str | None = None,
) -> tuple[str, str]:
    """Create PEND_* cable + pass-through conduit without connections.

    Returns (cable_name, conduit_name).
    """
    enter_s = str(enter).strip()
    exit_s = str(exit).strip()
    if not enter_s or not exit_s:
        raise ValueError("enter and exit (openings) are required")
    require_opening_ids(doc, enter_s, exit_s)
    cable_name = next_pend_cable_name(doc)
    suffix = cable_name.rsplit("_", 1)[-1]
    conduit_name = f"Conducto_paso_{suffix}"
    note_bits = [f"status: pending; enters via {enter_s} and exits via {exit_s}"]
    if notes:
        note_bits.append(str(notes))
    add_cable(
        doc,
        cable_name,
        subtype=subtype,
        kind=kind,
        section=section,
        colors=colors,
        label=label,
        notes="; ".join(note_bits),
    )
    add_conduit(
        doc,
        conduit_name,
        contains=[cable_name],
        from_ref=f".{enter_s}",
        to_ref=f".{exit_s}",
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
        raise ValueError("connections must be a list")
    connections.append({"from": from_ref, "via": via_ref, "to": to_ref})


def rm_connection(doc: dict[str, Any], index: int) -> None:
    _ensure_maps(doc)
    connections = doc["connections"]
    if not isinstance(connections, list):
        raise ValueError("connections must be a list")
    if index < 0 or index >= len(connections):
        raise ValueError(f"Invalid connection index: {index}")
    del connections[index]


def format_show(doc: dict[str, Any], *, element: str | None = None, cable: str | None = None) -> str:
    lines: list[str] = []
    if element:
        el = (doc.get("elements") or {}).get(element)
        if el is None:
            raise ValueError(f"Element does not exist: {element}")
        lines.append(f"element {element}:")
        import yaml as _yaml

        lines.append(_yaml.safe_dump(el, sort_keys=False, allow_unicode=True).rstrip())
        return "\n".join(lines)
    if cable:
        cb = (doc.get("cables") or {}).get(cable)
        if cb is None:
            raise ValueError(f"Cable does not exist: {cable}")
        lines.append(f"cable {cable}:")
        import yaml as _yaml

        lines.append(_yaml.safe_dump(cb, sort_keys=False, allow_unicode=True).rstrip())
        return "\n".join(lines)

    place = place_meta_from_mapping(doc)
    if place is not None:
        import yaml as _yaml

        type_id = place.get("type", "?")
        lines.append(f"place ({type_id}):")
        meta = {k: v for k, v in place.items() if k != "openings"}
        lines.append(_yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).rstrip())
        lines.append("")

        openings = place.get("openings")
        if isinstance(openings, list) and openings:
            lines.append(f"openings ({len(openings)}):")
            for name in openings:
                lines.append(f"  {name}")
            lines.append("")
        elif isinstance(openings, dict) and openings:
            lines.append(f"openings ({len(openings)}):")
            for name in sorted(openings, key=lambda n: str(n)):
                lines.append(f"  {name}  (legacy map — migrate to list)")
            lines.append("")

    elements = doc.get("elements") or {}
    cables = doc.get("cables") or {}
    connections = doc.get("connections") or []
    conduits = doc.get("conduits") or {}
    lines.append("# Electrical layer: elements ↔ cables/connections")
    lines.append(f"elements ({len(elements)}):")
    for name in sorted(elements):
        t = elements[name].get("type", "?") if isinstance(elements[name], dict) else "?"
        lines.append(f"  {name} ({t})")
    lines.append(f"cables ({len(cables)}):")
    for name in sorted(cables):
        cb = cables[name] if isinstance(cables[name], dict) else {}
        t = cb.get("type", "Cable")
        st = cb.get("subtype") or cb.get("kind")
        suffix = f"{t}/{st}" if st else str(t)
        lines.append(f"  {name} ({suffix})")
    lines.append(f"connections ({len(connections)}):")
    for i, conn in enumerate(connections):
        lines.append(f"  [{i}] {conn}")
    lines.append("")
    lines.append("# Physical layer: locations ↔ conduits (openings)")
    lines.append(f"conduits ({len(conduits)}):")
    for name in sorted(conduits):
        cd = conduits[name] if isinstance(conduits[name], dict) else {}
        t = cd.get("type", "Conduit")
        st = cd.get("subtype")
        if st is None and cd.get("kind") and cd.get("kind") != "conduit":
            st = cd.get("kind")
        elif st is None and cd.get("type") and cd.get("type") != "Conduit" and cd.get("kind") == "conduit":
            # legacy type-as-size
            t, st = "Conduit", cd.get("type")
        suffix = f"{t}/{st}" if st else str(t)
        ends = ""
        if cd.get("from") is not None and cd.get("to") is not None:
            ends = f": {cd['from']} → {cd['to']}"
        contains = cd.get("contains") or []
        contains_s = f" [{', '.join(str(c) for c in contains)}]" if contains else ""
        lines.append(f"  {name} ({suffix}){ends}{contains_s}")
    return "\n".join(lines)
