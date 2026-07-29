"""house/v1 schema: load catalog, expand locations, export to WireViz dicts."""
from __future__ import annotations

import copy
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

HOUSE_SCHEMA = "house/v1"

_EXPAND_LIST_RE = re.compile(
    r"^(?P<head>.*?)\[(?P<body>[^\]]+)\]$"
)


def normalize_token(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in ascii_value).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or "sin_nombre"


def location_prefix(parts: list[str]) -> str:
    tokens = [normalize_token(part) for part in parts if part]
    return "__".join(token for token in tokens if token)


def prefixed_name(prefix: str, name: str) -> str:
    normalized_name = normalize_token(name)
    if not prefix:
        return normalized_name
    return f"{prefix}__{normalized_name}"


def is_house_document(data: object) -> bool:
    return isinstance(data, dict) and data.get("schema") == HOUSE_SCHEMA


def package_dir() -> Path:
    """Directory of the installed housewire package (contains catalog/)."""
    return Path(__file__).resolve().parent.parent


def catalog_dir() -> Path:
    return package_dir() / "catalog"


def load_catalog(repo_root: Path | None = None) -> dict[str, dict[str, Any]]:
    # repo_root kept for API compat; catalog ships inside the package.
    root = catalog_dir()
    catalog: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return catalog

    for path in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")):
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Catalogo invalido (no es mapa): {path}")
        type_id = str(data.get("id") or path.stem)
        catalog[type_id] = data
    return catalog


def path_location_parts(project_path: Path, yaml_file: Path) -> list[str]:
    relative_parent = yaml_file.relative_to(project_path).parent
    if str(relative_parent) == ".":
        return []
    return list(relative_parent.parts)


def _as_location_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part for part in value.split("/") if part]
    if isinstance(value, list):
        return [str(part) for part in value]
    raise ValueError(f"location invalida: {value!r}")


def _merge_terminals(
    catalog_terminals: dict[str, Any], instance_terminals: dict[str, Any] | None
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for pin, meta in (catalog_terminals or {}).items():
        if isinstance(meta, dict):
            merged[str(pin)] = copy.deepcopy(meta)
        else:
            merged[str(pin)] = {"label": str(meta)}
    for pin, meta in (instance_terminals or {}).items():
        pin_s = str(pin)
        base = merged.get(pin_s, {})
        if isinstance(meta, dict):
            base = {**base, **copy.deepcopy(meta)}
        else:
            base = {**base, "label": str(meta)}
        merged[pin_s] = base
    return merged


def _wireviz_pin(pin: object) -> object:
    """WireViz compara pines con ==; '3' y 3 no coinciden."""
    text = str(pin)
    if text.isdigit():
        return int(text)
    return text


def _terminal_label(meta: dict[str, Any], pin: str) -> str:
    label = meta.get("label", pin)
    if label is None:
        return str(pin)
    if str(label) == "":
        return "·"
    return str(label)


def _collapse_pairs_for_wireviz(
    terminals: dict[str, dict[str, Any]],
    pairs: list[list[Any]] | None,
) -> tuple[list[Any], list[str], dict[str, Any]]:
    """Collapse in/out pairs into one WireViz pin so cables attach left+right.

    Driven by catalog `wireviz_collapse` (not WireViz native `loops`, which
    draw ugly U-turns on one side).
    """
    remap: dict[str, Any] = {}
    if not pairs:
        pins = [_wireviz_pin(pin) for pin in terminals]
        labels = [_terminal_label(terminals[pin], pin) for pin in terminals]
        for pin in terminals:
            remap[str(pin)] = _wireviz_pin(pin)
        return pins, labels, remap

    pins: list[Any] = []
    labels: list[str] = []
    used: set[str] = set()
    for pair in pairs:
        if len(pair) != 2:
            raise ValueError(f"wireviz_collapse debe tener 2 pines: {pair}")
        a, b = str(pair[0]), str(pair[1])
        if a not in terminals or b not in terminals:
            raise ValueError(f"wireviz_collapse referencia pines inexistentes: {pair}")
        used.add(a)
        used.add(b)
        wv_pin = _wireviz_pin(a)
        la = _terminal_label(terminals[a], a)
        lb = _terminal_label(terminals[b], b)
        # left|middle|right — WireViz repeats pin name on both sides; the
        # generate patch rewrites HTML so sides show la / lb.
        from housewire.house.wireviz_patch import format_side_pinlabel

        pin_label = format_side_pinlabel(la, f"{a}→{b}", lb)
        pins.append(wv_pin)
        labels.append(pin_label)
        remap[a] = wv_pin
        remap[b] = wv_pin

    for pin, meta in terminals.items():
        if pin in used:
            continue
        wv_pin = _wireviz_pin(pin)
        pins.append(wv_pin)
        labels.append(_terminal_label(meta, pin))
        remap[str(pin)] = wv_pin

    return pins, labels, remap


def _element_to_connector(
    element: dict[str, Any], catalog: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    type_id = element.get("type")
    if not type_id:
        raise ValueError("Elemento sin 'type'")
    type_id = str(type_id)
    type_def = catalog.get(type_id)
    if type_def is None:
        raise ValueError(f"Tipo de catalogo desconocido: {type_id}")

    terminals = _merge_terminals(
        type_def.get("terminals") or {}, element.get("terminals")
    )
    if not terminals:
        raise ValueError(f"El tipo {type_id} no define terminals")

    pairs_raw = element.get("wireviz_collapse")
    if pairs_raw is None:
        pairs_raw = type_def.get("wireviz_collapse")
    # Compat: antiguo nombre "loops" (confundible con loops nativos de WireViz).
    if pairs_raw is None:
        pairs_raw = element.get("loops")
    if pairs_raw is None:
        pairs_raw = type_def.get("loops")

    pins, pinlabels, pin_remap = _collapse_pairs_for_wireviz(terminals, pairs_raw)

    connector: dict[str, Any] = {
        "type": type_id,
        "pins": pins,
        "pinlabels": pinlabels,
    }
    # No exportar pares a WireViz como loops: generan arcos raros en un solo lado.
    if element.get("subtype") is not None:
        connector["subtype"] = element["subtype"]
    elif type_def.get("defaults", {}).get("subtype") is not None:
        connector["subtype"] = type_def["defaults"]["subtype"]

    if element.get("manufacturer"):
        connector["manufacturer"] = element["manufacturer"]
    if element.get("model"):
        connector["mpn"] = element["model"]
    if element.get("serial"):
        connector["pn"] = element["serial"]

    notes_parts: list[str] = []
    if element.get("label"):
        notes_parts.append(f"label: {element['label']}")
    if type_def.get("description_es"):
        notes_parts.append(str(type_def["description_es"]).strip())
    directions = [
        f"{pin}={terminals[pin]['direction']}"
        for pin in terminals
        if terminals[pin].get("direction")
    ]
    if directions:
        notes_parts.append("direction: " + ", ".join(directions))
    if element.get("notes"):
        notes_parts.append(str(element["notes"]))
    if notes_parts:
        connector["notes"] = " — ".join(notes_parts)

    return connector, pin_remap


def _cable_to_wireviz(cable: dict[str, Any]) -> dict[str, Any]:
    colors = cable.get("colors") or []
    if not isinstance(colors, list) or not colors:
        raise ValueError("Cable sin 'colors'")
    section = cable.get("section") or cable.get("gauge")
    if not section:
        raise ValueError("Cable sin 'section'")

    out: dict[str, Any] = {
        "wirecount": len(colors),
        "gauge": section,
        "colors": colors,
    }
    kind = cable.get("kind") or cable.get("type")
    if kind:
        out["type"] = kind
    if cable.get("notes"):
        out["notes"] = cable["notes"]
    return out


def _expand_endpoint_token(token: str) -> list[str]:
    token = token.strip()
    match = _EXPAND_LIST_RE.match(token)
    if not match:
        return [token]
    head = match.group("head")
    body = match.group("body")
    items = [item.strip() for item in body.split(",") if item.strip()]
    if not items:
        raise ValueError(f"Lista vacia en endpoint: {token}")
    if head.endswith(".") or head.endswith("/"):
        return [f"{head}{item}" for item in items]
    if head:
        return [f"{head}{item}" for item in items]
    return items


def _split_element_terminal(ref: str) -> tuple[str, str]:
    if "." not in ref:
        raise ValueError(f"Referencia de borne invalida (falta '.'): {ref}")
    element, terminal = ref.rsplit(".", 1)
    if not element or not terminal:
        raise ValueError(f"Referencia de borne invalida: {ref}")
    return element, terminal


def _resolve_element_name(
    raw_name: str,
    *,
    current_location: list[str],
    local_prefix: str,
) -> str:
    name = raw_name.strip()
    if name.startswith("/"):
        parts = [part for part in name.strip("/").split("/") if part]
        if len(parts) < 1:
            raise ValueError(f"Referencia absoluta invalida: {raw_name}")
        element = parts[-1]
        location = parts[:-1]
        return prefixed_name(location_prefix(location), element)

    if name.startswith("../") or name.startswith("./"):
        location = list(current_location)
        rest = name
        while rest.startswith("../"):
            if not location:
                raise ValueError(f"Referencia relativa fuera de raiz: {raw_name}")
            location.pop()
            rest = rest[3:]
        if rest.startswith("./"):
            rest = rest[2:]
        parts = [part for part in rest.split("/") if part]
        if not parts:
            raise ValueError(f"Referencia relativa invalida: {raw_name}")
        element = parts[-1]
        location.extend(parts[:-1])
        return prefixed_name(location_prefix(location), element)

    return prefixed_name(local_prefix, name)

def _normalize_local_element_ref(
    raw_name: str,
    *,
    current_location: list[str],
    local_prefix: str,
    local_map: dict[str, str],
) -> str:
    name = raw_name.strip()
    if name.startswith("/") or name.startswith("../") or name.startswith("./"):
        return _resolve_element_name(
            name, current_location=current_location, local_prefix=local_prefix
        )
    # local short name
    if name in local_map:
        return local_map[name]
    return prefixed_name(local_prefix, name)


def _parse_via_wires(via_token: str, cable_local_map: dict[str, str], local_prefix: str) -> tuple[str, list[Any]]:
    expanded = _expand_endpoint_token(via_token)
    cable_names: list[str] = []
    wire_ids: list[Any] = []
    for item in expanded:
        if "." in item:
            cable, wire = item.rsplit(".", 1)
            cable_names.append(cable)
            wire_ids.append(_wireviz_pin(wire) if not isinstance(wire, int) else wire)
        else:
            # bare cable name with implicit wires from sibling expansion already done
            cable_names.append(item)
            wire_ids.append(None)

    if len(set(cable_names)) != 1:
        raise ValueError(f"via mezcla varios cables: {via_token}")
    cable_raw = cable_names[0]
    if cable_raw.startswith("/") or cable_raw.startswith("../") or cable_raw.startswith("./"):
        # unusual but allow absolute cable refs as already-qualified names
        cable_name = _resolve_element_name(
            cable_raw, current_location=[], local_prefix=local_prefix
        )
    else:
        cable_name = cable_local_map.get(cable_raw, prefixed_name(local_prefix, cable_raw))

    if all(wire is None for wire in wire_ids):
        raise ValueError(f"via sin indices de hilo: {via_token}")
    if any(wire is None for wire in wire_ids):
        raise ValueError(f"via inconsistente: {via_token}")
    return cable_name, wire_ids


def _connection_dict_to_wireviz(
    conn: dict[str, Any],
    *,
    current_location: list[str],
    local_prefix: str,
    element_map: dict[str, str],
    cable_map: dict[str, str],
    pin_remap_by_element: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if "from" not in conn or "to" not in conn or "via" not in conn:
        raise ValueError("Connection house/v1 requiere from, via y to")

    from_tokens = _expand_endpoint_token(str(conn["from"]))
    to_tokens = _expand_endpoint_token(str(conn["to"]))
    via_token = str(conn["via"])

    from_pairs = [_split_element_terminal(token) for token in from_tokens]
    to_pairs = [_split_element_terminal(token) for token in to_tokens]
    cable_name, wire_ids = _parse_via_wires(via_token, cable_map, local_prefix)

    if not (len(from_pairs) == len(to_pairs) == len(wire_ids)):
        raise ValueError(
            "from/via/to deben tener la misma longitud tras expandir listas: "
            f"{conn}"
        )

    from_element = _normalize_local_element_ref(
        from_pairs[0][0],
        current_location=current_location,
        local_prefix=local_prefix,
        local_map=element_map,
    )
    to_element = _normalize_local_element_ref(
        to_pairs[0][0],
        current_location=current_location,
        local_prefix=local_prefix,
        local_map=element_map,
    )
    for element, _terminal in from_pairs:
        resolved = _normalize_local_element_ref(
            element,
            current_location=current_location,
            local_prefix=local_prefix,
            local_map=element_map,
        )
        if resolved != from_element:
            raise ValueError(f"from mezcla elementos distintos: {conn}")
    for element, _terminal in to_pairs:
        resolved = _normalize_local_element_ref(
            element,
            current_location=current_location,
            local_prefix=local_prefix,
            local_map=element_map,
        )
        if resolved != to_element:
            raise ValueError(f"to mezcla elementos distintos: {conn}")

    from_remap = pin_remap_by_element.get(from_element, {})
    to_remap = pin_remap_by_element.get(to_element, {})
    from_terminals = [
        _wireviz_pin(from_remap.get(str(terminal), terminal))
        for _element, terminal in from_pairs
    ]
    to_terminals = [
        _wireviz_pin(to_remap.get(str(terminal), terminal))
        for _element, terminal in to_pairs
    ]

    return [
        {from_element: from_terminals},
        {cable_name: wire_ids},
        {to_element: to_terminals},
    ]


def _annotate_conduits(
    cables_wv: dict[str, dict[str, Any]],
    conduits: dict[str, Any],
    cable_map: dict[str, str],
    local_prefix: str,
) -> None:
    for conduit_name, conduit in (conduits or {}).items():
        if not isinstance(conduit, dict):
            continue
        contains = conduit.get("contains") or []
        note_bits = [f"conduit:{conduit_name}"]
        if conduit.get("type"):
            note_bits.append(f"type={conduit['type']}")
        if conduit.get("route"):
            note_bits.append(f"route={conduit['route']}")
        if conduit.get("notes"):
            note_bits.append(str(conduit["notes"]))
        annotation = " — ".join(note_bits)
        for cable_ref in contains:
            cable_ref_s = str(cable_ref)
            wv_name = cable_map.get(cable_ref_s, prefixed_name(local_prefix, cable_ref_s))
            if wv_name not in cables_wv:
                raise ValueError(
                    f"Conduit {conduit_name} referencia cable inexistente: {cable_ref_s}"
                )
            existing = cables_wv[wv_name].get("notes")
            cables_wv[wv_name]["notes"] = (
                f"{existing} — {annotation}" if existing else annotation
            )


def _convert_flat_fragment(
    fragment: dict[str, Any],
    *,
    catalog: dict[str, dict[str, Any]],
    location_parts: list[str],
) -> dict[str, Any]:
    prefix = location_prefix(location_parts)
    element_map: dict[str, str] = {}
    cable_map: dict[str, str] = {}
    pin_remap_by_element: dict[str, dict[str, Any]] = {}

    connectors: dict[str, Any] = {}
    for name, definition in (fragment.get("elements") or {}).items():
        if not isinstance(definition, dict):
            raise ValueError(f"Elemento invalido: {name}")
        new_name = prefixed_name(prefix, str(name))
        connector, pin_remap = _element_to_connector(definition, catalog)
        connectors[new_name] = connector
        element_map[str(name)] = new_name
        pin_remap_by_element[new_name] = pin_remap

    cables: dict[str, Any] = {}
    for name, definition in (fragment.get("cables") or {}).items():
        if not isinstance(definition, dict):
            raise ValueError(f"Cable invalido: {name}")
        new_name = prefixed_name(prefix, str(name))
        cables[new_name] = _cable_to_wireviz(definition)
        cable_map[str(name)] = new_name

    _annotate_conduits(cables, fragment.get("conduits") or {}, cable_map, prefix)

    connections: list[Any] = []
    for conn in fragment.get("connections") or []:
        if isinstance(conn, dict):
            connections.append(
                _connection_dict_to_wireviz(
                    conn,
                    current_location=location_parts,
                    local_prefix=prefix,
                    element_map=element_map,
                    cable_map=cable_map,
                    pin_remap_by_element=pin_remap_by_element,
                )
            )
        elif isinstance(conn, list):
            # already wireviz-style; remap local names
            renamed: list[Any] = []
            for endpoint in conn:
                if not isinstance(endpoint, dict):
                    renamed.append(endpoint)
                    continue
                mapped: dict[Any, Any] = {}
                for key, value in endpoint.items():
                    key_s = str(key)
                    if key_s in element_map:
                        mapped[element_map[key_s]] = value
                    elif key_s in cable_map:
                        mapped[cable_map[key_s]] = value
                    else:
                        mapped[prefixed_name(prefix, key_s)] = value
                renamed.append(mapped)
            connections.append(renamed)
        else:
            raise ValueError(f"Connection invalida: {conn!r}")

    return {
        "connectors": connectors,
        "cables": cables,
        "connections": connections,
        "pin_remaps": pin_remap_by_element,
    }


def _walk_locations(
    node: dict[str, Any],
    base: list[str],
) -> list[tuple[list[str], dict[str, Any]]]:
    """Yield (location_parts, fragment) for nested locations trees."""
    fragments: list[tuple[list[str], dict[str, Any]]] = []

    direct_keys = {"elements", "cables", "connections", "conduits"}
    if any(key in node for key in direct_keys):
        fragment = {key: copy.deepcopy(node[key]) for key in direct_keys if key in node}
        fragments.append((list(base), fragment))

    nested = node.get("locations")
    if nested is None:
        return fragments
    if not isinstance(nested, dict):
        raise ValueError("'locations' debe ser un mapa")

    for name, child in nested.items():
        if not isinstance(child, dict):
            raise ValueError(f"locations.{name} debe ser un mapa")
        fragments.extend(_walk_locations(child, base + [str(name)]))
    return fragments


def house_document_to_wireviz(
    data: dict[str, Any],
    *,
    catalog: dict[str, dict[str, Any]],
    file_location_parts: list[str],
) -> dict[str, Any]:
    """Convert a house/v1 document into a WireViz-compatible dict.

    Names are already location-prefixed; merge step must not prefix again.
    """
    explicit = _as_location_list(data.get("location"))
    # location es relativo al path del fichero: se concatena, no sustituye.
    # Ejemplo: fichero en Parking/ con location: [Caja derivacion 1]
    # → base = [Parking, Caja derivacion 1]
    if explicit:
        # Evitar duplicar partes que ya están en file_location_parts
        # (compatibilidad con location absoluto: si empieza con las mismas partes, no duplicar)
        if explicit[:len(file_location_parts)] == file_location_parts:
            base_location = explicit
        else:
            base_location = list(file_location_parts) + explicit
    else:
        base_location = list(file_location_parts)

    fragments = _walk_locations(data, base_location)
    # also allow top-level elements without nesting already handled by walk
    if not fragments and any(key in data for key in ("elements", "cables", "connections")):
        fragments = [
            (
                base_location,
                {
                    key: copy.deepcopy(data[key])
                    for key in ("elements", "cables", "connections", "conduits")
                    if key in data
                },
            )
        ]

    merged: dict[str, Any] = {
        "connectors": {},
        "cables": {},
        "connections": [],
        "_pin_remaps": {},
    }

    for location_parts, fragment in fragments:
        converted = _convert_flat_fragment(
            fragment, catalog=catalog, location_parts=location_parts
        )
        for name, definition in converted["connectors"].items():
            if name in merged["connectors"]:
                raise ValueError(f"Colision de elemento house/v1: {name}")
            merged["connectors"][name] = definition
        for name, definition in converted["cables"].items():
            if name in merged["cables"]:
                raise ValueError(f"Colision de cable house/v1: {name}")
            merged["cables"][name] = definition
        merged["connections"].extend(converted["connections"])
        for name, remap in converted.get("pin_remaps", {}).items():
            if name in merged["_pin_remaps"]:
                raise ValueError(f"Colision de pin_remap house/v1: {name}")
            merged["_pin_remaps"][name] = remap

    # pass through metadata/options if present
    for key in ("options", "metadata"):
        if key in data:
            merged[key] = copy.deepcopy(data[key])

    return merged
