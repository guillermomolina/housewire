"""house/v1 schema: load catalog, expand locations, validate installations."""
from __future__ import annotations

import copy
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

HOUSE_SCHEMA = "house/v1"

# Directory / inline place types.
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
    """Directory of the installed HouseWire package."""
    return Path(__file__).resolve().parent.parent


def _program_repo_root() -> Path:
    """Checkout root when running from a source tree (…/src/housewire → …)."""
    return package_dir().parent.parent


DEFAULT_CATALOG_NAME = "default"
ENV_CATALOG = "HOUSEWIRE_CATALOG"
ENV_CATALOGS_DIR = "HOUSEWIRE_CATALOGS_DIR"
CATALOG_HINT = (
    "Clone the catalog into catalogs/default, set HOUSEWIRE_CATALOG to a catalog "
    "root (or types/ dir), or set HOUSEWIRE_CATALOGS_DIR. "
    "See https://github.com/guillermomolina/housewire-catalog"
)


def catalogs_search_root() -> Path:
    """Parent directory that contains named catalogs (e.g. ``…/catalogs``)."""
    env = os.environ.get(ENV_CATALOGS_DIR)
    if env:
        return Path(env).expanduser().resolve()
    cwd = (Path.cwd() / "catalogs").resolve()
    if cwd.is_dir():
        return cwd
    return (_program_repo_root() / "catalogs").resolve()


def _types_dir_from_catalog_root(root: Path) -> Path | None:
    """Return a directory that contains type YAML files, or None."""
    if not root.is_dir():
        return None
    nested = root / "types"
    if nested.is_dir() and (
        any(nested.glob("*.yaml")) or any(nested.glob("*.yml"))
    ):
        return nested
    if any(root.glob("*.yaml")) or any(root.glob("*.yml")):
        # Flat catalog root (or types/ itself passed as path).
        return root
    if nested.is_dir():
        return nested
    return None


def _site_catalog_ref(site_root: Path | None) -> str | Path | None:
    """Read optional ``catalog:`` from the site document YAML."""
    if site_root is None:
        return None
    from housewire.site.paths import find_site_yaml

    path = find_site_yaml(Path(site_root))
    if path is None:
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except OSError:
        return None
    if not isinstance(data, dict):
        return None
    ref = data.get("catalog")
    if ref is None:
        return None
    if isinstance(ref, (str, Path)):
        return ref
    if isinstance(ref, dict):
        if ref.get("path"):
            return Path(str(ref["path"]))
        if ref.get("id") or ref.get("name"):
            return str(ref.get("id") or ref.get("name"))
    return None


def resolve_catalog_types_dir(
    catalog: str | Path | None = None,
    *,
    site_root: Path | None = None,
) -> Path:
    """Resolve the directory of type YAML files for the base catalog.

    Order:
    1. Explicit ``catalog`` argument (name or path)
    2. ``HOUSEWIRE_CATALOG`` env
    3. Site ``catalog:`` field (name or path relative to site root)
    4. Named catalog ``default`` under ``HOUSEWIRE_CATALOGS_DIR`` / ``./catalogs``
    """
    candidates: list[Path] = []

    def add_path(raw: str | Path, *, base: Path | None = None) -> None:
        path = Path(raw).expanduser()
        if not path.is_absolute() and base is not None:
            path = (base / path).resolve()
        else:
            path = path.resolve()
        types = _types_dir_from_catalog_root(path)
        if types is not None:
            candidates.append(types)
        # Also try path itself as types/ already.
        elif path.is_dir():
            candidates.append(path)

    def add_named(name: str) -> None:
        add_path(catalogs_search_root() / name)

    if catalog is not None:
        text = str(catalog).strip()
        if text:
            as_path = Path(text).expanduser()
            if as_path.is_absolute() or "/" in text or "\\" in text or text.startswith("."):
                add_path(text, base=Path(site_root).resolve() if site_root else Path.cwd())
            else:
                add_named(text)

    env_catalog = os.environ.get(ENV_CATALOG)
    if env_catalog:
        add_path(env_catalog, base=Path.cwd())

    site_ref = _site_catalog_ref(site_root)
    if site_ref is not None:
        ref_text = str(site_ref).strip()
        if ref_text:
            if isinstance(site_ref, Path) or "/" in ref_text or "\\" in ref_text or ref_text.startswith("."):
                add_path(ref_text, base=Path(site_root).resolve() if site_root else Path.cwd())
            else:
                add_named(ref_text)

    add_named(DEFAULT_CATALOG_NAME)

    for path in candidates:
        if any(path.glob("*.yaml")) or any(path.glob("*.yml")):
            return path

    searched = catalogs_search_root() / DEFAULT_CATALOG_NAME
    raise FileNotFoundError(
        f"No HouseWire type catalog found (looked for {searched}). {CATALOG_HINT}"
    )


def _load_catalog_dir(root: Path) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return catalog
    for path in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")):
        if path.name in {"catalog.yaml", "catalog.yml"}:
            continue
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Invalid catalog (not a map): {path}")
        type_id = str(data.get("id") or path.stem)
        catalog[type_id] = data
    return catalog


def catalog_dir(
    catalog: str | Path | None = None,
    *,
    site_root: Path | None = None,
) -> Path:
    """Return the resolved types directory for the base catalog."""
    return resolve_catalog_types_dir(catalog, site_root=site_root)


def load_catalog(
    site_root: Path | None = None,
    *,
    catalog: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Load external type catalog, optionally merged with ``$SITE/catalog/*.yaml``.

    Base catalog comes from ``HOUSEWIRE_CATALOG``, a named tree under
    ``catalogs/<name>``, or the site document ``catalog:`` field. Site files
    overlay base entries by ``id`` (shallow key merge).
    """
    types_dir = resolve_catalog_types_dir(catalog, site_root=site_root)
    result = _load_catalog_dir(types_dir)
    if not result:
        raise FileNotFoundError(
            f"Catalog types directory is empty: {types_dir}. {CATALOG_HINT}"
        )
    if site_root is not None:
        site_dir = Path(site_root).resolve() / "catalog"
        for type_id, data in _load_catalog_dir(site_dir).items():
            base = result.get(type_id)
            if base is None:
                result[type_id] = dict(data)
            else:
                merged = dict(base)
                merged.update(data)
                result[type_id] = merged
    return result


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


def path_location_parts(site_path: Path, yaml_file: Path) -> list[str]:
    """Location prefix for a YAML file.

    Sites use a single root ``.yaml``/``.yml``; nested places live under
    ``elements:`` and get their path from ``_walk_locations``, so the file
    itself always contributes an empty prefix when it sits at the site root.
    """
    relative = yaml_file.resolve().relative_to(site_path.resolve())
    # Nested files are not supported; ignore parent dirs other than ``.``.
    if len(relative.parts) == 1 and relative.suffix.lower() in {".yaml", ".yml"}:
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



def _pin_id(pin: object) -> object:
    """Normalize pin ids so ``"3"`` and ``3`` compare equal."""
    text = str(pin)
    if text.isdigit():
        return int(text)
    return text


def _validate_terminal_pairs(
    terminals: dict[str, dict[str, Any]],
    pairs: list[Any] | None,
) -> None:
    if not pairs:
        return
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(f"terminal_pairs must have 2 pins: {pair}")
        a, b = str(pair[0]), str(pair[1])
        if a not in terminals or b not in terminals:
            raise ValueError(f"terminal_pairs references missing pins: {pair}")


def _validate_element(
    name: str,
    element: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
) -> None:
    type_id = element.get("type")
    if not type_id:
        raise ValueError(f"Element missing 'type': {name}")
    type_id = str(type_id)
    type_def = catalog.get(type_id)
    if type_def is None:
        raise ValueError(f"Unknown catalog type: {type_id}")
    cat_kind = type_def.get("kind") if isinstance(type_def, dict) else None
    if cat_kind in (CABLE_CATALOG_KIND, CONDUIT_CATALOG_KIND):
        raise ValueError(
            f"type: {type_id} belongs to cables:/conduits:, not to elements:"
        )
    if is_place_type(type_id):
        return

    subtype = element.get("subtype")
    if subtype is None and isinstance(type_def.get("defaults"), dict):
        subtype = type_def["defaults"].get("subtype")
    type_terminals = type_def.get("terminals") or {}
    type_pairs = type_def.get("terminal_pairs")
    subtypes = type_def.get("subtypes") if isinstance(type_def, dict) else None
    if isinstance(subtypes, dict) and subtype is not None:
        sub = subtypes.get(str(subtype))
        if isinstance(sub, dict):
            if sub.get("terminals") is not None:
                type_terminals = sub.get("terminals") or {}
            if "terminal_pairs" in sub:
                type_pairs = sub.get("terminal_pairs")

    terminals = _merge_terminals(type_terminals, element.get("terminals"))
    if not terminals:
        raise ValueError(f"Type {type_id} does not define terminals")

    pairs_raw = element.get("terminal_pairs")
    if pairs_raw is None:
        pairs_raw = type_pairs
    _validate_terminal_pairs(terminals, pairs_raw if isinstance(pairs_raw, list) else None)


def _validate_cable(
    name: str,
    cable: dict[str, Any],
    catalog: dict[str, dict[str, Any]] | None,
) -> None:
    expanded = expand_cable(cable, catalog)
    colors = expanded.get("colors") or []
    if not isinstance(colors, list) or not colors:
        raise ValueError(f"Cable missing 'colors': {name}")
    section = expanded.get("section") or expanded.get("gauge")
    if not section:
        raise ValueError(f"Cable missing 'section': {name}")


def _validate_connection(
    conn: dict[str, Any],
    *,
    current_location: list[str],
    local_prefix: str,
    element_map: dict[str, str],
    cable_map: dict[str, str],
) -> None:
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
    del cable_name  # validated by parse

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


def _validate_flat_fragment(
    fragment: dict[str, Any],
    *,
    catalog: dict[str, dict[str, Any]],
    location_parts: list[str],
    seen_elements: set[str],
    seen_cables: set[str],
) -> None:
    prefix = location_prefix(location_parts)
    element_map: dict[str, str] = {}
    cable_map: dict[str, str] = {}

    for name, definition in (fragment.get("elements") or {}).items():
        if not isinstance(definition, dict):
            raise ValueError(f"Invalid element: {name}")
        new_name = prefixed_name(prefix, str(name))
        if new_name in seen_elements:
            raise ValueError(f"house/v1 element collision: {new_name}")
        seen_elements.add(new_name)
        element_map[str(name)] = new_name
        _validate_element(str(name), definition, catalog)

    for name, definition in (fragment.get("cables") or {}).items():
        if not isinstance(definition, dict):
            raise ValueError(f"Invalid cable: {name}")
        new_name = prefixed_name(prefix, str(name))
        if new_name in seen_cables:
            raise ValueError(f"house/v1 cable collision: {new_name}")
        seen_cables.add(new_name)
        cable_map[str(name)] = new_name
        _validate_cable(str(name), definition, catalog)

    for conduit_name, conduit in (fragment.get("conduits") or {}).items():
        if not isinstance(conduit, dict):
            continue
        expanded = expand_conduit(conduit, catalog)
        for cable_ref in expanded.get("contains") or []:
            cable_ref_s = str(cable_ref)
            qualified = cable_map.get(
                cable_ref_s, prefixed_name(prefix, cable_ref_s)
            )
            if qualified not in seen_cables:
                raise ValueError(
                    f"Conduit {conduit_name} references missing cable: {cable_ref_s}"
                )

    for conn in fragment.get("connections") or []:
        if isinstance(conn, dict):
            _validate_connection(
                conn,
                current_location=location_parts,
                local_prefix=prefix,
                element_map=element_map,
                cable_map=cable_map,
            )
        elif isinstance(conn, list):
            # Legacy triple-list connection form — accept without rewrite.
            continue
        else:
            raise ValueError(f"Invalid connection: {conn!r}")


def validate_house_tree(
    data: dict[str, Any],
    *,
    catalog: dict[str, dict[str, Any]],
    file_location_parts: list[str],
) -> None:
    """Walk a house/v1 document and raise ``ValueError`` on structural errors."""
    base_location = list(file_location_parts)

    # Touch place meta early so legacy ``self:`` / ``location:`` lists fail fast.
    place_meta_from_mapping(data)

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
            _inject_place_meta(data, elems, base_location)
            if elems:
                frag["elements"] = elems
        if frag:
            fragments = [(base_location, frag)]

    seen_elements: set[str] = set()
    seen_cables: set[str] = set()
    for location_parts, fragment in fragments:
        _validate_flat_fragment(
            fragment,
            catalog=catalog,
            location_parts=location_parts,
            seen_elements=seen_elements,
            seen_cables=seen_cables,
        )


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
            wire_ids.append(int(wire) if str(wire).isdigit() else wire)
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





