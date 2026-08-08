from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml

from housewire.house import (
    DEFAULT_CABLE_TYPE,
    DEFAULT_CONDUCTOR_TYPE,
    DEFAULT_CONDUIT_TYPE,
    expand_cable,
    expand_conductor,
    expand_conduit,
    is_place_type,
    load_catalog,
    place_meta_from_mapping,
)
from housewire.house.links import contained_ids, resolve_link_kind
from housewire.site.io import load_yaml, require_house_document, save_yaml
from housewire.site.openings import (
    declared_opening_ids,
    expand_opening_grid,
    normalize_opening_id,
    opening_fits_grid,
    parse_opening_id,
    validate_location_openings,
)
from housewire.site.validate import validate_house_document

_ELEMENT_REF_RE = re.compile(r"(?:^|[./\[])([A-Za-z_][A-Za-z0-9_]*)")
_PEND_CABLE_RE = re.compile(r"^PEND_Linea_(\d+)$")

DEFAULT_CABLE_SECTION = "1.5 mm2"
DEFAULT_CONDUCTOR_COLOR = "BN"
DEFAULT_CABLE_SUBTYPE = "Power"
DEFAULT_CONDUIT_SUBTYPE = "Tube"
DEFAULT_SHEATH_COLOR = "BK"

# Structural keys — use add/rm instead of set.
RESERVED_SET_KEYS = frozenset({"schema", "elements", "cables"})

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
    if root_key in {"terminals", "terminal_grid"}:
        raw_grid = mapping.get("terminal_grid")
        if raw_grid is not None:
            expand_opening_grid(raw_grid)
        terminals = mapping.get("terminals")
        if terminals is not None and not isinstance(terminals, dict):
            raise ValueError("terminals must be a map of pin id → metadata")
        if isinstance(terminals, dict) and raw_grid is not None:
            grid = expand_opening_grid(raw_grid)
            for pin in terminals:
                oid = normalize_opening_id(str(pin))
                if grid and not opening_fits_grid(oid, grid):
                    face, _, _ = parse_opening_id(oid)
                    cols, rows = grid[face]
                    raise ValueError(
                        f"Terminal {oid} outside terminal_grid[{face}]="
                        f"{cols}x{rows}"
                    )


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

    if nested_key is None and root_key == "install":
        from housewire.house.links import normalize_install

        value = normalize_install(value, context="place")
        if value is None:
            raise ValueError("install must be 'Surface' or 'Flush'")
    if nested_key is None and root_key == "mount":
        from housewire.house.links import normalize_mount

        value = normalize_mount(value, context="place")
        if value is None:
            raise ValueError("mount must be 'Wall', 'Ceiling', or 'Floor'")

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


def _conductor_catalog_defaults(
    *,
    type_id: str = DEFAULT_CONDUCTOR_TYPE,
    subtype: str | None = DEFAULT_CABLE_SUBTYPE,
) -> dict[str, Any]:
    """Resolve section/color defaults from catalog for conductors."""
    expanded = expand_conductor(
        {"type": type_id, **({"subtype": subtype} if subtype else {})},
        load_catalog(),
    )
    return {
        "section": expanded.get("section") or DEFAULT_CABLE_SECTION,
        "color": str(expanded.get("color") or DEFAULT_CONDUCTOR_COLOR),
    }


def conductors_referencing_element(doc: dict[str, Any], element_name: str) -> list[str]:
    """Return conductor ids whose from/to mention ``element_name``."""
    hits: list[str] = []
    cables = doc.get("cables") or {}
    if not isinstance(cables, dict):
        return hits
    catalog = load_catalog()
    for name, entry in cables.items():
        if not isinstance(entry, dict):
            continue
        try:
            kind = resolve_link_kind(entry, catalog)
        except ValueError:
            continue
        if kind != "conductor":
            continue
        text = f"{entry.get('from', '')} {entry.get('to', '')}"
        if re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(element_name)}(?=\.|\[|/|$)", text
        ):
            hits.append(str(name))
    return hits


def load_editable(path: Path, site_path: Path) -> dict[str, Any]:
    doc = load_yaml(path)
    require_house_document(doc, path)
    return doc


def persist(doc: dict[str, Any], path: Path, site_path: Path) -> None:
    require_house_document(doc, path)
    validate_house_document(doc, site_path=site_path, yaml_path=path)
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
    refs = conductors_referencing_element(doc, name)
    if refs:
        raise ValueError(
            f"Cannot delete {name}: referenced by conductors {refs}. "
            "Delete those conductors first."
        )
    del elements[name]


def add_cable_group(
    doc: dict[str, Any],
    name: str,
    *,
    contains: list[str],
    type_id: str = DEFAULT_CABLE_TYPE,
    subtype: str | None = DEFAULT_CABLE_SUBTYPE,
    color: str | None = None,
    section: str | None = None,
    label: str | None = None,
    notes: str | None = None,
) -> None:
    """Add a Cable entry that groups conductors and/or other cables."""
    _ensure_maps(doc)
    cables = doc["cables"]
    if not isinstance(cables, dict):
        raise ValueError("cables must be a map")
    if name in cables:
        raise ValueError(f"Cable already exists: {name}")
    if not contains:
        raise ValueError("contains cannot be empty")
    for ref in contains:
        if str(ref) not in cables:
            raise ValueError(f"Cable references missing cables entry: {ref}")
    entry: dict[str, Any] = {
        "type": type_id,
        "contains": [str(c) for c in contains],
        "color": str(color or DEFAULT_SHEATH_COLOR),
    }
    if subtype is not None:
        entry["subtype"] = subtype
    if section is not None:
        entry["section"] = normalize_section(section)
    if label:
        entry["label"] = label
    if notes:
        entry["notes"] = notes
    expand_cable(entry, load_catalog())
    cables[name] = entry


def add_conductor(
    doc: dict[str, Any],
    name: str,
    *,
    color: str | None = None,
    section: str | None = None,
    from_ref: str | None = None,
    to_ref: str | None = None,
    type_id: str = DEFAULT_CONDUCTOR_TYPE,
    subtype: str | None = DEFAULT_CABLE_SUBTYPE,
    label: str | None = None,
    notes: str | None = None,
    conduit_path: list[dict[str, Any]] | None = None,
) -> None:
    """Add a Conductor leaf (optional from/to for pending/open runs)."""
    _ensure_maps(doc)
    cables = doc["cables"]
    if not isinstance(cables, dict):
        raise ValueError("cables must be a map")
    if name in cables:
        raise ValueError(f"Cable already exists: {name}")
    defaults = _conductor_catalog_defaults(type_id=type_id, subtype=subtype)
    entry: dict[str, Any] = {
        "type": type_id,
        "section": normalize_section(section, default=str(defaults["section"])),
        "color": str(color or defaults["color"]),
    }
    if subtype is not None:
        entry["subtype"] = subtype
    if from_ref is not None:
        entry["from"] = str(from_ref).strip()
    if to_ref is not None:
        entry["to"] = str(to_ref).strip()
    if conduit_path:
        entry["conduit_path"] = [dict(hop) for hop in conduit_path]
    if label:
        entry["label"] = label
    if notes:
        entry["notes"] = notes
    expand_conductor(entry, load_catalog())
    cables[name] = entry


def add_cable(
    doc: dict[str, Any],
    name: str,
    *,
    type_id: str = DEFAULT_CONDUCTOR_TYPE,
    subtype: str | None = DEFAULT_CABLE_SUBTYPE,
    kind: str | None = None,
    section: str | None = None,
    color: str | None = None,
    colors: list[str] | None = None,
    from_ref: str | None = None,
    to_ref: str | None = None,
    contains: list[str] | None = None,
    label: str | None = None,
    notes: str | None = None,
) -> None:
    """Add a ``cables`` entry.

    - ``type: Conductor`` (default): leaf wire; optional ``colors[0]`` as color.
    - ``type: Cable``: cable; requires ``contains``.
    - ``type: Conduit``: use :func:`add_conduit`.
    """
    resolved_subtype = subtype if kind is None else kind
    resolved_type = str(type_id)
    if resolved_type == DEFAULT_CONDUIT_TYPE:
        raise ValueError("Use add_conduit for type: Conduit")
    if resolved_type == DEFAULT_CABLE_TYPE or contains is not None:
        if not contains:
            raise ValueError("Cable requires contains")
        add_cable_group(
            doc,
            name,
            contains=contains,
            type_id=DEFAULT_CABLE_TYPE,
            subtype=resolved_subtype,
            color=color or (colors[0] if colors else None),
            section=section,
            label=label,
            notes=notes,
        )
        return
    if colors and len(colors) > 1:
        conductor_ids: list[str] = []
        for index, col in enumerate(colors, start=1):
            cid = f"{name}_{index}"
            add_conductor(
                doc,
                cid,
                type_id=DEFAULT_CONDUCTOR_TYPE,
                subtype=resolved_subtype,
                section=section,
                color=col,
                label=label,
                notes=notes,
            )
            conductor_ids.append(cid)
        add_cable_group(
            doc,
            name,
            contains=conductor_ids,
            subtype=resolved_subtype,
            section=section,
            label=label,
            notes=notes,
        )
        return
    if colors and color is None:
        color = colors[0]
    add_conductor(
        doc,
        name,
        type_id=DEFAULT_CONDUCTOR_TYPE,
        subtype=resolved_subtype,
        section=section,
        color=color,
        from_ref=from_ref,
        to_ref=to_ref,
        label=label,
        notes=notes,
    )


def rm_cable(doc: dict[str, Any], name: str) -> None:
    _ensure_maps(doc)
    cables = doc["cables"]
    if not isinstance(cables, dict) or name not in cables:
        raise ValueError(f"Cable does not exist: {name}")
    for other_name, entry in cables.items():
        if other_name == name or not isinstance(entry, dict):
            continue
        contains = [str(c) for c in (entry.get("contains") or [])]
        if name in contains:
            raise ValueError(
                f"Cannot delete {name}: referenced in contains of {other_name}."
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
    """Add a Conduit entry into the unified ``cables`` map.

    ``contains`` may be empty when the tube is installed before its cables.
    """
    _ensure_maps(doc)
    cables = doc["cables"]
    if not isinstance(cables, dict):
        raise ValueError("cables must be a map")
    if name in cables:
        raise ValueError(f"Cable already exists: {name}")
    for cable_ref in contains:
        if str(cable_ref) not in cables:
            raise ValueError(f"Conduit references missing cables entry: {cable_ref}")
    from housewire.house.conduit_ref import split_conduit_endpoint

    split_conduit_endpoint(from_ref)
    split_conduit_endpoint(to_ref)
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
    expand_conduit(entry, load_catalog())
    cables[name] = entry


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
    """Create PEND_* cable + conductors + pass-through conduit.

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
    note = "; ".join(note_bits)
    resolved_colors = list(colors) if colors else ["BN", "BU"]
    conductor_ids: list[str] = []
    for index, col in enumerate(resolved_colors, start=1):
        cid = f"{cable_name}_{index}"
        add_conductor(
            doc,
            cid,
            subtype=subtype if kind is None else kind,
            section=section,
            color=col,
            notes=note,
            label=label,
        )
        conductor_ids.append(cid)
    add_cable(
        doc,
        cable_name,
        contains=conductor_ids,
        subtype=subtype if kind is None else kind,
        notes=note,
        label=label,
        section=section,
    )
    add_conduit(
        doc,
        conduit_name,
        contains=[cable_name],
        from_ref=f".{enter_s}",
        to_ref=f".{exit_s}",
    )
    return cable_name, conduit_name


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
    catalog = load_catalog()
    lines.append("# elements + unified cables (Conduit / Cable / Conductor)")
    lines.append(f"elements ({len(elements)}):")
    for name in sorted(elements):
        t = elements[name].get("type", "?") if isinstance(elements[name], dict) else "?"
        lines.append(f"  {name} ({t})")
    lines.append(f"cables ({len(cables)}):")
    for name in sorted(cables):
        cb = cables[name] if isinstance(cables[name], dict) else {}
        t = cb.get("type", "?")
        st = cb.get("subtype")
        suffix = f"{t}/{st}" if st else str(t)
        extra = ""
        try:
            kind = resolve_link_kind(cb, catalog) if isinstance(cb, dict) else ""
        except ValueError:
            kind = ""
        if kind == "conductor":
            ends = ""
            if cb.get("from") and cb.get("to"):
                ends = f": {cb['from']} → {cb['to']}"
            col = cb.get("color")
            extra = f" [{col}]{ends}" if col else ends
        elif kind in ("cable", "conduit"):
            contains = cb.get("contains") or []
            contains_s = f" [{', '.join(str(c) for c in contains)}]" if contains else ""
            ends = ""
            if kind == "conduit" and cb.get("from") and cb.get("to"):
                ends = f": {cb['from']} → {cb['to']}"
            extra = f"{ends}{contains_s}"
        lines.append(f"  {name} ({suffix}){extra}")
    return "\n".join(lines)
