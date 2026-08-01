"""house/v1 schema: load catalog, expand locations, export to WireViz dicts."""
from __future__ import annotations

import copy
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

HOUSE_SCHEMA = "house/v1"

# Directory / inline place types (wireviz_skip in catalog).
PLACE_TYPES = frozenset(
    {
        "Room",
        "Stair",
        "JunctionBox",
        "DeviceBox",
        "LightPoint",
        "Panel",
        "Floor",
        "House",
        "Location",
    }
)

# Catalog kinds for cables: / conduits: (not usable as elements).
CABLE_CATALOG_KIND = "cable_type"
CONDUIT_CATALOG_KIND = "conduit_type"
DEFAULT_CABLE_TYPE = "Cable"
DEFAULT_CONDUIT_TYPE = "Conduit"

# Keys that are document/tree structure, not place metadata fields.
PLACE_CHILD_KEYS = frozenset({"elements", "cables", "connections", "conduits", "locations"})
DOCUMENT_ONLY_KEYS = frozenset({"schema", "location", "self"})


def is_place_type(type_id: object) -> bool:
    return str(type_id) in PLACE_TYPES


def place_meta_from_mapping(node: dict[str, Any]) -> dict[str, Any] | None:
    """Extract place metadata from a house node (file root or inline element).

    Canonical form: place fields live on the object itself (``type``, ``name``,
    ``label``, ``openings``, …) beside ``elements`` / ``cables`` / ….

    Legacy: a nested ``location: { type: … }`` map is still accepted.
    """
    if "self" in node and node.get("self") is not None:
        raise ValueError(
            "The 'self:' block is no longer used. Put type/label/openings/… at the root "
            "of the YAML (the file is the place object). "
            "Example:\n  schema: house/v1\n  type: JunctionBox\n  openings: [N1]"
        )
    loc = node.get("location")
    if loc is not None:
        if isinstance(loc, list):
            raise ValueError(
                "location: as a path list is no longer used. "
                "Hierarchy is the directory path or keys under elements."
            )
        if not isinstance(loc, dict):
            raise ValueError(
                "location: legacy must be a map { type: JunctionBox, … }. "
                "Preferred: type/label/… at the document root."
            )
        if node.get("type") is not None and is_place_type(node.get("type")):
            raise ValueError(
                "Do not mix type: at the root with a location: block. "
                "Use only root-level fields."
            )
        type_id = loc.get("type")
        if not type_id or not is_place_type(type_id):
            raise ValueError(
                "location.type must be one of: "
                + ", ".join(sorted(PLACE_TYPES - {"Location"}))
                + " (or Location)"
            )
        return {**copy.deepcopy(loc), "type": str(type_id)}

    type_id = node.get("type")
    if not type_id or not is_place_type(type_id):
        return None
    meta = {
        key: copy.deepcopy(value)
        for key, value in node.items()
        if key not in PLACE_CHILD_KEYS and key not in DOCUMENT_ONLY_KEYS
    }
    meta["type"] = str(type_id)
    return meta

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


def is_technical_id(value: str) -> bool:
    """True if ``value`` is already a safe location/element id (no spaces)."""
    return bool(value) and value == normalize_token(value)


def location_id_from_name(raw_name: str) -> tuple[str, str | None]:
    """Return ``(technical_id, label_or_none)`` for a location leaf name.

    If ``raw_name`` is already a technical id, label is ``None``.
    Otherwise id is ``normalize_token(raw_name)`` and label is the original text
    (human ``label``, not working ``name``).
    """
    name = raw_name.strip()
    if not name:
        raise ValueError("empty location name")
    if is_technical_id(name):
        return name, None
    return normalize_token(name), name


def place_id_from_parts(parts: tuple[str, ...] | list[str]) -> str:
    """Leaf technical id from location parts (last segment, or empty for root)."""
    if not parts:
        return ""
    return str(parts[-1])


def place_name(meta: dict[str, Any] | None, place_id: str) -> str:
    """Working display name: YAML ``name`` → technical ``place_id``."""
    if meta:
        raw = meta.get("name")
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return str(place_id or "")


def place_label(meta: dict[str, Any] | None, place_id: str) -> str:
    """Human label: YAML ``label`` → ``name`` → technical ``place_id``."""
    if meta:
        raw = meta.get("label")
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return place_name(meta, place_id)

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


def _load_catalog_dir(root: Path) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return catalog
    for path in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")):
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Invalid catalog (not a map): {path}")
        type_id = str(data.get("id") or path.stem)
        catalog[type_id] = data
    return catalog


def load_catalog(repo_root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load package catalog, optionally merged with ``$SITE/catalog/*.yaml``.

    Site files overlay package entries by ``id`` (shallow key merge). A site
    file may contain only ``id`` + ``icon`` to customize the UI glyph.
    """
    catalog = _load_catalog_dir(catalog_dir())
    if repo_root is not None:
        site_dir = Path(repo_root).resolve() / "catalog"
        for type_id, data in _load_catalog_dir(site_dir).items():
            base = catalog.get(type_id)
            if base is None:
                catalog[type_id] = dict(data)
            else:
                merged = dict(base)
                merged.update(data)
                catalog[type_id] = merged
    return catalog


def normalize_icon_class(raw: object, *, default: str = "fa-circle") -> str:
    """Return a Font Awesome class token (``fa-plug`` or ``fa-solid fa-plug``)."""
    if raw is None:
        return default
    text = str(raw).strip()
    if not text:
        return default
    return text


def catalog_icon(
    type_id: object,
    *,
    catalog: dict[str, dict[str, Any]] | None = None,
    instance: dict[str, Any] | None = None,
    default: str = "fa-circle",
) -> str:
    """Resolve UI icon: instance ``icon:`` → catalog ``icon:`` → default."""
    if isinstance(instance, dict) and instance.get("icon") is not None:
        return normalize_icon_class(instance.get("icon"), default=default)
    cat = catalog if catalog is not None else load_catalog()
    type_def = cat.get(str(type_id or ""))
    if isinstance(type_def, dict) and type_def.get("icon") is not None:
        return normalize_icon_class(type_def.get("icon"), default=default)
    return default


def _catalog_defaults_for_subtype(
    type_def: dict[str, Any] | None, subtype: str | None
) -> dict[str, Any]:
    """Merge type-level defaults with optional subtype defaults."""
    defaults: dict[str, Any] = {}
    if not isinstance(type_def, dict):
        return defaults
    base = type_def.get("defaults")
    if isinstance(base, dict):
        defaults.update(copy.deepcopy(base))
    if subtype is None:
        return defaults
    subtypes = type_def.get("subtypes")
    if isinstance(subtypes, dict):
        sub = subtypes.get(str(subtype))
        if isinstance(sub, dict):
            sub_defaults = sub.get("defaults")
            if isinstance(sub_defaults, dict):
                defaults.update(copy.deepcopy(sub_defaults))
    return defaults


def expand_cable(
    cable: dict[str, Any], catalog: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Normalize a cables: entry: type/subtype/label + catalog defaults.

    Legacy ``kind: power`` becomes ``subtype: power`` with ``type: Cable``.
    """
    cat = catalog if catalog is not None else load_catalog()
    raw = copy.deepcopy(cable)
    if not isinstance(raw, dict):
        raise ValueError("Invalid cable (not a map)")

    subtype = raw.get("subtype")
    if subtype is None and raw.get("kind") is not None:
        subtype = raw.get("kind")
    type_id = raw.get("type")
    if type_id is None:
        type_id = DEFAULT_CABLE_TYPE
    type_id = str(type_id)
    type_def = cat.get(type_id)
    if type_def is not None and type_def.get("kind") not in (None, CABLE_CATALOG_KIND):
        raise ValueError(
            f"type: {type_id} is not a cable type (catalog kind={type_def.get('kind')!r})"
        )
    if type_def is None and type_id != DEFAULT_CABLE_TYPE:
        raise ValueError(f"Unknown cable type in catalog: {type_id}")

    defaults = _catalog_defaults_for_subtype(type_def, str(subtype) if subtype is not None else None)
    out: dict[str, Any] = {"type": type_id}
    if subtype is not None:
        out["subtype"] = str(subtype)
    for key in ("section", "gauge", "colors", "name", "label", "notes", "manufacturer", "model"):
        if key in raw and raw[key] is not None:
            out[key] = copy.deepcopy(raw[key])
        elif key in defaults and key not in ("gauge",):
            # Prefer section over gauge from catalog defaults.
            if key == "section" or key not in out:
                out[key] = copy.deepcopy(defaults[key])
    if "section" not in out and "gauge" not in out and defaults.get("section"):
        out["section"] = copy.deepcopy(defaults["section"])
    if "colors" not in out and defaults.get("colors"):
        out["colors"] = copy.deepcopy(defaults["colors"])
    return out


def expand_conduit(
    conduit: dict[str, Any], catalog: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Normalize a conduits: entry: type/subtype/label + catalog defaults.

    Legacy forms:
    - ``kind: conduit`` → ``type: Conduit``
    - ``kind: conduit`` + ``type: M20`` → ``type: Conduit``, ``subtype: M20``
    """
    cat = catalog if catalog is not None else load_catalog()
    raw = copy.deepcopy(conduit)
    if not isinstance(raw, dict):
        raise ValueError("Invalid conduit (not a map)")

    type_id = raw.get("type")
    subtype = raw.get("subtype")
    kind = raw.get("kind")

    type_def = cat.get(str(type_id)) if type_id is not None else None
    if type_def is not None and type_def.get("kind") == CONDUIT_CATALOG_KIND:
        resolved_type = str(type_id)
    elif type_id is not None and subtype is None:
        # Legacy: type held the physical size / hose class (M20, hose, …).
        resolved_type = DEFAULT_CONDUIT_TYPE
        subtype = type_id
    elif type_id is None:
        resolved_type = DEFAULT_CONDUIT_TYPE
        if subtype is None and kind is not None and str(kind) != "conduit":
            subtype = kind
    else:
        raise ValueError(
            f"type: {type_id} is not a known conduit type; "
            f"use type: {DEFAULT_CONDUIT_TYPE} and subtype: …"
        )

    type_def = cat.get(resolved_type)
    if type_def is None:
        raise ValueError(f"Unknown conduit type in catalog: {resolved_type}")
    if type_def.get("kind") not in (None, CONDUIT_CATALOG_KIND):
        raise ValueError(
            f"type: {resolved_type} is not a conduit type "
            f"(catalog kind={type_def.get('kind')!r})"
        )

    defaults = _catalog_defaults_for_subtype(
        type_def, str(subtype) if subtype is not None else None
    )
    out: dict[str, Any] = {"type": resolved_type}
    if subtype is not None:
        out["subtype"] = str(subtype)
    for key in ("contains", "from", "to", "name", "label", "notes"):
        if key in raw and raw[key] is not None:
            out[key] = copy.deepcopy(raw[key])
        elif key in defaults:
            out[key] = copy.deepcopy(defaults[key])
    return out


def path_location_parts(project_path: Path, yaml_file: Path) -> list[str]:
    """Location prefix for a YAML file.

    Sites use a single root ``housewire.yaml``; nested places live under
    ``elements:`` and get their path from ``_walk_locations``, so the file
    itself always contributes an empty prefix when it sits at the site root.
    """
    relative = yaml_file.resolve().relative_to(project_path.resolve())
    # Nested files are not supported; ignore parent dirs other than ``.``.
    if relative.name.lower() in {"housewire.yaml", "housewire.yml"} and len(relative.parts) == 1:
        return []
    relative_parent = relative.parent
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
    raise ValueError(f"invalid location: {value!r}")


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
            raise ValueError(f"wireviz_collapse must have 2 pins: {pair}")
        a, b = str(pair[0]), str(pair[1])
        if a not in terminals or b not in terminals:
            raise ValueError(f"wireviz_collapse references missing pins: {pair}")
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
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    type_id = element.get("type")
    if not type_id:
        raise ValueError("Element missing 'type'")
    type_id = str(type_id)
    type_def = catalog.get(type_id)
    if type_def is None:
        raise ValueError(f"Unknown catalog type: {type_id}")
    cat_kind = type_def.get("kind") if isinstance(type_def, dict) else None
    if cat_kind in (CABLE_CATALOG_KIND, CONDUIT_CATALOG_KIND):
        raise ValueError(
            f"type: {type_id} belongs to cables:/conduits:, not to elements:"
        )
    # wireviz_skip: true — no WireViz connector (e.g. place types)
    if isinstance(type_def, dict) and type_def.get("wireviz_skip"):
        return None, None

    subtype = element.get("subtype")
    if subtype is None and isinstance(type_def.get("defaults"), dict):
        subtype = type_def["defaults"].get("subtype")
    type_terminals = type_def.get("terminals") or {}
    type_collapse = type_def.get("wireviz_collapse")
    subtypes = type_def.get("subtypes") if isinstance(type_def, dict) else None
    if isinstance(subtypes, dict) and subtype is not None:
        sub = subtypes.get(str(subtype))
        if isinstance(sub, dict):
            if sub.get("terminals") is not None:
                type_terminals = sub.get("terminals") or {}
            if "wireviz_collapse" in sub:
                type_collapse = sub.get("wireviz_collapse")

    terminals = _merge_terminals(type_terminals, element.get("terminals"))
    if not terminals:
        raise ValueError(f"Type {type_id} does not define terminals")

    pairs_raw = element.get("wireviz_collapse")
    if pairs_raw is None:
        pairs_raw = type_collapse
    # Compat: old name "loops" (easy to confuse with native WireViz loops).
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
    # Do not export pairs to WireViz as loops: they draw odd one-sided arcs.
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


def _cable_to_wireviz(
    cable: dict[str, Any], catalog: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    expanded = expand_cable(cable, catalog)
    colors = expanded.get("colors") or []
    if not isinstance(colors, list) or not colors:
        raise ValueError("Cable missing 'colors'")
    section = expanded.get("section") or expanded.get("gauge")
    if not section:
        raise ValueError("Cable missing 'section'")

    out: dict[str, Any] = {
        "wirecount": len(colors),
        "gauge": section,
        "colors": colors,
    }
    # WireViz cable "type" is the functional class (power/earth/…), i.e. subtype.
    wv_type = expanded.get("subtype") or expanded.get("type")
    if wv_type:
        out["type"] = wv_type
    notes_parts: list[str] = []
    if expanded.get("label"):
        notes_parts.append(f"label: {expanded['label']}")
    if expanded.get("notes"):
        notes_parts.append(str(expanded["notes"]))
    if notes_parts:
        out["notes"] = " — ".join(notes_parts)
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
        raise ValueError(f"Empty list in endpoint: {token}")
    if head.endswith(".") or head.endswith("/"):
        return [f"{head}{item}" for item in items]
    if head:
        return [f"{head}{item}" for item in items]
    return items


def _split_element_terminal(ref: str) -> tuple[str, str]:
    if "." not in ref:
        raise ValueError(f"Invalid terminal reference (missing '.'): {ref}")
    element, terminal = ref.rsplit(".", 1)
    if not element or not terminal:
        raise ValueError(f"Invalid terminal reference: {ref}")
    return element, terminal


def _norm_location_parts(parts: list[str]) -> list[str]:
    return [normalize_token(part) for part in parts]


def _location_contains(base: list[str], target: list[str]) -> bool:
    """True if ``target`` is ``base`` or a descendant (token-normalized)."""
    base_n = _norm_location_parts(base)
    target_n = _norm_location_parts(target)
    return len(target_n) >= len(base_n) and target_n[: len(base_n)] == base_n


def _parse_element_path(
    raw_name: str,
    *,
    current_location: list[str],
) -> tuple[list[str], str]:
    """Return ``(location_parts, element_name)`` for a connection element ref.

    Allowed forms (scoped to the declaring location and its sublocations):
    - local: ``Regleta``
    - child-relative: ``Caja 2/Regleta`` or ``./Caja 2/Regleta``
    - absolute under this tree: ``/Parking/Caja 2/Regleta`` (same subtree only)

    ``../`` (leaving this location upward) is rejected.
    """
    name = raw_name.strip()
    if not name:
        raise ValueError("Empty element reference")
    parts_probe = [part for part in name.replace("\\", "/").split("/") if part]
    if ".." in parts_probe or name.startswith("../") or name == "..":
        raise ValueError(
            f"Reference outside this location (../ not allowed): {raw_name}. "
            "Define the connection in a common ancestor."
        )
    if name.startswith("/"):
        parts = [part for part in name.strip("/").split("/") if part]
        if not parts:
            raise ValueError(f"Invalid absolute reference: {raw_name}")
        return parts[:-1], parts[-1]
    if name.startswith("./"):
        name = name[2:]
    if "/" in name:
        parts = [part for part in name.split("/") if part]
        if len(parts) < 2:
            raise ValueError(f"Invalid relative reference: {raw_name}")
        return list(current_location) + parts[:-1], parts[-1]
    return list(current_location), name


def _assert_ref_in_location_tree(raw_name: str, *, current_location: list[str]) -> None:
    location, _element = _parse_element_path(
        raw_name, current_location=current_location
    )
    if not _location_contains(current_location, location):
        here = "/".join(current_location) if current_location else "/"
        raise ValueError(
            f"Reference outside this location tree: {raw_name}. "
            f"Only this location and sublocations are allowed (current: {here}). "
            "Define the connection higher up."
        )


def _resolve_element_name(
    raw_name: str,
    *,
    current_location: list[str],
    local_prefix: str,
) -> str:
    _assert_ref_in_location_tree(raw_name, current_location=current_location)
    location, element = _parse_element_path(
        raw_name, current_location=current_location
    )
    return prefixed_name(location_prefix(location), element)


def _normalize_local_element_ref(
    raw_name: str,
    *,
    current_location: list[str],
    local_prefix: str,
    local_map: dict[str, str],
) -> str:
    name = raw_name.strip()
    if (
        name.startswith("/")
        or name.startswith("../")
        or name.startswith("./")
        or "/" in name
    ):
        return _resolve_element_name(
            name, current_location=current_location, local_prefix=local_prefix
        )
    # local short name — always in scope
    if name in local_map:
        return local_map[name]
    return prefixed_name(local_prefix, name)


def _parse_via_wires(
    via_token: str,
    cable_local_map: dict[str, str],
    local_prefix: str,
    *,
    current_location: list[str],
) -> tuple[str, list[Any]]:
    expanded = _expand_endpoint_token(via_token)
    cable_names: list[str] = []
    wire_ids: list[Any] = []
    for item in expanded:
        if "." in item:
            cable, wire = item.rsplit(".", 1)
            cable_names.append(cable)
            wire_ids.append(_wireviz_pin(wire) if not isinstance(wire, int) else wire)
        else:
            cable_names.append(item)
            wire_ids.append(None)

    if len(set(cable_names)) != 1:
        raise ValueError(f"via mixes multiple cables: {via_token}")
    cable_raw = cable_names[0]
    if (
        cable_raw.startswith("/")
        or cable_raw.startswith("../")
        or cable_raw.startswith("./")
        or "/" in cable_raw
    ):
        _assert_ref_in_location_tree(cable_raw, current_location=current_location)
        location, element = _parse_element_path(
            cable_raw, current_location=current_location
        )
        if _norm_location_parts(location) != _norm_location_parts(current_location):
            raise ValueError(
                f"via must refer to a cable in this location (not a sublocation): "
                f"{via_token}"
            )
        cable_name = prefixed_name(location_prefix(location), element)
    else:
        cable_name = cable_local_map.get(
            cable_raw, prefixed_name(local_prefix, cable_raw)
        )

    if all(wire is None for wire in wire_ids):
        raise ValueError(f"via missing wire indices: {via_token}")
    if any(wire is None for wire in wire_ids):
        raise ValueError(f"inconsistent via: {via_token}")
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
        raise ValueError("house/v1 connection requires from, via, and to")

    from_tokens = _expand_endpoint_token(str(conn["from"]))
    to_tokens = _expand_endpoint_token(str(conn["to"]))
    via_token = str(conn["via"])

    from_pairs = [_split_element_terminal(token) for token in from_tokens]
    to_pairs = [_split_element_terminal(token) for token in to_tokens]
    cable_name, wire_ids = _parse_via_wires(
        via_token,
        cable_map,
        local_prefix,
        current_location=current_location,
    )

    if not (len(from_pairs) == len(to_pairs) == len(wire_ids)):
        raise ValueError(
            "from/via/to must have the same length after expanding lists: "
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
            raise ValueError(f"from mixes different elements: {conn}")
    for element, _terminal in to_pairs:
        resolved = _normalize_local_element_ref(
            element,
            current_location=current_location,
            local_prefix=local_prefix,
            local_map=element_map,
        )
        if resolved != to_element:
            raise ValueError(f"to mixes different elements: {conn}")

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
    catalog: dict[str, dict[str, Any]] | None = None,
) -> None:
    for conduit_name, conduit in (conduits or {}).items():
        if not isinstance(conduit, dict):
            continue
        expanded = expand_conduit(conduit, catalog)
        contains = expanded.get("contains") or []
        note_bits = [f"conduit:{conduit_name}"]
        if expanded.get("type"):
            note_bits.append(f"type={expanded['type']}")
        if expanded.get("subtype"):
            note_bits.append(f"subtype={expanded['subtype']}")
        if expanded.get("label"):
            note_bits.append(f"label={expanded['label']}")
        if expanded.get("from") is not None and expanded.get("to") is not None:
            note_bits.append(f"from={expanded['from']} to={expanded['to']}")
        if expanded.get("notes"):
            note_bits.append(str(expanded["notes"]))
        annotation = " — ".join(note_bits)
        for cable_ref in contains:
            cable_ref_s = str(cable_ref)
            wv_name = cable_map.get(cable_ref_s, prefixed_name(local_prefix, cable_ref_s))
            if wv_name not in cables_wv:
                raise ValueError(
                    f"Conduit {conduit_name} references missing cable: {cable_ref_s}"
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
            raise ValueError(f"Invalid element: {name}")
        new_name = prefixed_name(prefix, str(name))
        connector, pin_remap = _element_to_connector(definition, catalog)
        if connector is None:
            # wireviz_skip (e.g. type: Location) — registrar en element_map
            # so local references do not fail, but do not emit a connector
            element_map[str(name)] = new_name
            continue
        connectors[new_name] = connector
        element_map[str(name)] = new_name
        pin_remap_by_element[new_name] = pin_remap

    cables: dict[str, Any] = {}
    for name, definition in (fragment.get("cables") or {}).items():
        if not isinstance(definition, dict):
            raise ValueError(f"Invalid cable: {name}")
        new_name = prefixed_name(prefix, str(name))
        cables[new_name] = _cable_to_wireviz(definition, catalog)
        cable_map[str(name)] = new_name

    _annotate_conduits(
        cables, fragment.get("conduits") or {}, cable_map, prefix, catalog
    )

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
            raise ValueError(f"Invalid connection: {conn!r}")

    return {
        "connectors": connectors,
        "cables": cables,
        "connections": connections,
        "pin_remaps": pin_remap_by_element,
    }


def _inject_place_meta(
    node: dict[str, Any],
    flat_elements: dict[str, Any],
    base: list[str],
) -> None:
    """Fold this node's place metadata into elements (synthetic place entry)."""
    meta = place_meta_from_mapping(node)
    if meta is None:
        return
    name = str(base[-1]) if base else str(meta.get("type") or "Place")
    flat_elements[name] = meta


def _walk_locations(
    node: dict[str, Any],
    base: list[str],
) -> list[tuple[list[str], dict[str, Any]]]:
    """Yield (location_parts, fragment) for nested place trees.

    Supports:
    1. Place fields on the node root (``type: JunctionBox``, …).
    2. Legacy ``location: { type: … }`` map (via place_meta_from_mapping).
    3. ``locations: { Name: { … } }`` — explicit location map.
    4. ``elements: { Name: { type: Room|…, elements: … } }`` — nested places.
    """
    fragments: list[tuple[list[str], dict[str, Any]]] = []

    direct_keys = {"elements", "cables", "connections", "conduits"}
    location_child_keys = PLACE_CHILD_KEYS

    raw_elements = dict(node.get("elements") or {})
    location_elements: dict[str, dict[str, Any]] = {}
    plain_elements: dict[str, Any] = {}
    for name, defn in raw_elements.items():
        if (
            isinstance(defn, dict)
            and is_place_type(defn.get("type"))
            and any(k in defn for k in location_child_keys)
        ):
            location_elements[str(name)] = defn
        else:
            plain_elements[str(name)] = defn

    flat_node: dict[str, Any] = {}
    if plain_elements:
        flat_node["elements"] = plain_elements
    for k in ("cables", "connections", "conduits"):
        if k in node:
            flat_node[k] = node[k]

    place_meta = place_meta_from_mapping(node)
    if place_meta is not None:
        for key, value in place_meta.items():
            flat_node[key] = copy.deepcopy(value)

    for name, defn in location_elements.items():
        meta_only = {k: v for k, v in defn.items() if k not in location_child_keys}
        if meta_only or not any(k in defn for k in {"elements", "cables", "connections"}):
            flat_node.setdefault("elements", {})[name] = {
                k: v for k, v in defn.items() if k not in location_child_keys
            } or defn

    _inject_place_meta(node, flat_node.setdefault("elements", {}), base)
    if not flat_node.get("elements"):
        flat_node.pop("elements", None)

    fragment_keys = set(direct_keys)
    if place_meta is not None:
        fragment_keys.update(place_meta.keys())
    if any(key in flat_node for key in fragment_keys):
        fragment = {
            key: copy.deepcopy(flat_node[key])
            for key in fragment_keys
            if key in flat_node
        }
        fragments.append((list(base), fragment))

    for name, defn in location_elements.items():
        if any(k in defn for k in {"elements", "cables", "connections"}):
            child = copy.deepcopy(defn)
            fragments.extend(_walk_locations(child, base + [str(name)]))

    nested = node.get("locations")
    if nested is not None:
        if not isinstance(nested, dict):
            raise ValueError("'locations' must be a map")
        for name, child in nested.items():
            if not isinstance(child, dict):
                raise ValueError(f"locations.{name} must be a map")
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
    Nested place paths come from ``elements:`` under the single site document.
    """
    base_location = list(file_location_parts)

    fragments = _walk_locations(data, base_location)
    if not fragments and (
        any(key in data for key in ("elements", "cables", "connections", "conduits"))
        or place_meta_from_mapping(data) is not None
    ):
        frag: dict[str, Any] = {
            key: copy.deepcopy(data[key])
            for key in ("elements", "cables", "connections", "conduits")
            if key in data
        }
        meta = place_meta_from_mapping(data)
        if meta is not None:
            for key, value in meta.items():
                frag[key] = copy.deepcopy(value)
            elems = dict(frag.get("elements") or {})
            _inject_directory_location(data, elems, base_location)
            if elems:
                frag["elements"] = elems
        if frag:
            fragments = [(base_location, frag)]

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
                raise ValueError(f"house/v1 element collision: {name}")
            merged["connectors"][name] = definition
        for name, definition in converted["cables"].items():
            if name in merged["cables"]:
                raise ValueError(f"house/v1 cable collision: {name}")
            merged["cables"][name] = definition
        merged["connections"].extend(converted["connections"])
        for name, remap in converted.get("pin_remaps", {}).items():
            if name in merged["_pin_remaps"]:
                raise ValueError(f"house/v1 pin_remap collision: {name}")
            merged["_pin_remaps"][name] = remap

    for key in ("options", "metadata"):
        if key in data:
            merged[key] = copy.deepcopy(data[key])

    return merged
