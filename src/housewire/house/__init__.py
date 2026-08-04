"""house/v2 schema: load catalog, expand locations, validate installations."""
from __future__ import annotations

import copy
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from housewire.house.links import (
    CABLE_CATALOG_KIND,
    CONDUCTOR_CATALOG_KIND,
    CONDUIT_CATALOG_KIND,
    DEFAULT_CABLE_TYPE,
    DEFAULT_CONDUCTOR_TYPE,
    DEFAULT_CONDUIT_TYPE,
    expand_cable,
    expand_conductor,
    expand_conduit,
    expand_link,
    reject_legacy_keys,
    resolve_link_kind,
    validate_link_entry,
)

HOUSE_SCHEMA = "house/v2"
LEGACY_HOUSE_SCHEMA = "house/v1"

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

# Keys that are document/tree structure, not place metadata fields.
PLACE_CHILD_KEYS = frozenset({"elements", "cables", "locations"})
DOCUMENT_ONLY_KEYS = frozenset({"schema", "location", "self"})


def assert_supported_schema(data: dict[str, Any]) -> None:
    """Raise if ``schema`` is missing, legacy, or otherwise unsupported."""
    schema = data.get("schema")
    if schema == LEGACY_HOUSE_SCHEMA:
        raise ValueError(
            "Unsupported schema house/v1; this HouseWire build requires house/v2"
        )
    if schema != HOUSE_SCHEMA:
        raise ValueError(
            f"Unsupported schema {schema!r}; this HouseWire build requires {HOUSE_SCHEMA}"
        )


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
            "Example:\n  schema: house/v2\n  type: JunctionBox\n  openings: [N1]"
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
    "Install the default catalog (pip install housewire-catalog / "
    "pip install 'housewire[catalog]'), clone it into catalogs/default, "
    "or set HOUSEWIRE_CATALOG / HOUSEWIRE_CATALOGS_DIR. "
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


def _package_catalog_types_dir() -> Path | None:
    """Types dir from the installed ``housewire-catalog`` package, if present."""
    try:
        from housewire_catalog import types_dir
    except ImportError:
        return None
    try:
        path = types_dir()
    except (FileNotFoundError, OSError, ValueError):
        return None
    if path.is_dir() and (
        any(path.glob("*.yaml")) or any(path.glob("*.yml"))
    ):
        return path.resolve()
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
    5. Installed ``housewire-catalog`` package (``types_dir()``)
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

    packaged = _package_catalog_types_dir()
    if packaged is not None:
        candidates.append(packaged)

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
    ``catalogs/<name>``, the site document ``catalog:`` field, or the installed
    ``housewire-catalog`` package. Site files overlay base entries by ``id``
    (shallow key merge).
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


def normalize_icon_id(raw: object, *, default: str = "circle") -> str:
    """Return a Lucide icon id (``plug``, ``zoom-in``, ``circle``).

    Accepts a single kebab-case token. Empty or invalid values become
    ``default``.
    """
    if raw is None:
        return default
    text = str(raw).strip().lower().replace("_", "-")
    if not text:
        return default
    # One token only (ignore accidental multi-token strings).
    token = text.split()[0]
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", token):
        return default
    return token


def catalog_icon(
    type_id: object,
    *,
    catalog: dict[str, dict[str, Any]] | None = None,
    instance: dict[str, Any] | None = None,
    default: str = "circle",
) -> str:
    """Resolve UI icon: instance ``icon:`` → catalog ``icon:`` → default."""
    if isinstance(instance, dict) and instance.get("icon") is not None:
        return normalize_icon_id(instance.get("icon"), default=default)
    cat = catalog if catalog is not None else load_catalog()
    type_def = cat.get(str(type_id or ""))
    if isinstance(type_def, dict) and type_def.get("icon") is not None:
        return normalize_icon_id(type_def.get("icon"), default=default)
    return default


def catalog_type_label(
    type_id: object,
    *,
    catalog: dict[str, dict[str, Any]] | None = None,
    subtype: str | None = None,
    locale: str | None = None,
) -> str:
    """Human type name for UI: catalog ``label`` / ``name`` (legacy ``title``).

    When ``locale`` is ``es`` and ``label_es`` is set, that wins. Falls back to
    the type id when the catalog has no display string.
    """
    return _catalog_type_localized_text(
        type_id,
        catalog=catalog,
        subtype=subtype,
        locale=locale,
        en_keys=("label", "name", "title"),
        es_key="label_es",
        fallback_to_id=True,
    )


def catalog_type_description(
    type_id: object,
    *,
    catalog: dict[str, dict[str, Any]] | None = None,
    subtype: str | None = None,
    locale: str | None = None,
) -> str:
    """Catalog ``description`` for UI; ``description_es`` when locale is ``es``."""
    return _catalog_type_localized_text(
        type_id,
        catalog=catalog,
        subtype=subtype,
        locale=locale,
        en_keys=("description",),
        es_key="description_es",
        fallback_to_id=False,
    )


def _catalog_type_localized_text(
    type_id: object,
    *,
    catalog: dict[str, dict[str, Any]] | None,
    subtype: str | None,
    locale: str | None,
    en_keys: tuple[str, ...],
    es_key: str,
    fallback_to_id: bool,
) -> str:
    from housewire.i18n import normalize_locale

    tid = str(type_id or "").strip()
    cat = catalog if catalog is not None else load_catalog()
    type_def = cat.get(tid)
    if not isinstance(type_def, dict):
        return (tid or "?") if fallback_to_id else ""
    loc = normalize_locale(locale) if locale is not None else "en"

    def _pick(row: dict[str, Any]) -> str | None:
        if loc == "es":
            raw_es = row.get(es_key)
            if raw_es is not None and str(raw_es).strip():
                return str(raw_es).strip()
        for key in en_keys:
            raw = row.get(key)
            if raw is not None and str(raw).strip():
                return str(raw).strip()
        return None

    if subtype is not None:
        subtypes = type_def.get("subtypes")
        if isinstance(subtypes, dict):
            sub = subtypes.get(str(subtype))
            if isinstance(sub, dict):
                picked = _pick(sub)
                if picked:
                    return picked
    picked = _pick(type_def)
    if picked:
        return picked
    return (tid or "?") if fallback_to_id else ""


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
    if cat_kind in (CABLE_CATALOG_KIND, CONDUIT_CATALOG_KIND, CONDUCTOR_CATALOG_KIND):
        raise ValueError(
            f"type: {type_id} belongs under cables:, not under elements:"
        )
    if is_place_type(type_id):
        return

    if "terminal_pairs" in element:
        raise ValueError(
            f"Element {name}: terminal_pairs is removed; "
            "use face-cell terminal ids (N1, S1, …)"
        )

    subtype = element.get("subtype")
    if subtype is None and isinstance(type_def.get("defaults"), dict):
        subtype = type_def["defaults"].get("subtype")
    type_terminals = type_def.get("terminals") or {}
    subtypes = type_def.get("subtypes") if isinstance(type_def, dict) else None
    if isinstance(subtypes, dict) and subtype is not None:
        sub = subtypes.get(str(subtype))
        if isinstance(sub, dict):
            if sub.get("terminals") is not None:
                type_terminals = sub.get("terminals") or {}

    terminals = _merge_terminals(type_terminals, element.get("terminals"))
    if not terminals:
        raise ValueError(f"Type {type_id} does not define terminals")


def _validate_flat_fragment(
    fragment: dict[str, Any],
    *,
    catalog: dict[str, dict[str, Any]],
    location_parts: list[str],
    seen_elements: set[str],
    seen_cables: set[str],
    ancestor_cable_ids: set[str] | None = None,
) -> set[str]:
    """Validate one place fragment.

    Returns short ``cables:`` ids declared here. Descendant conduits may list
    ancestor cable ids in ``contains`` (cable lifted to LCA; tube stays local).
    """
    reject_legacy_keys(fragment)
    prefix = location_prefix(location_parts)
    element_map: dict[str, str] = {}
    cable_map: dict[str, str] = {}
    local_cable_ids: set[str] = set()

    for name, definition in (fragment.get("elements") or {}).items():
        if not isinstance(definition, dict):
            raise ValueError(f"Invalid element: {name}")
        new_name = prefixed_name(prefix, str(name))
        if new_name in seen_elements:
            raise ValueError(f"house/v2 element collision: {new_name}")
        seen_elements.add(new_name)
        element_map[str(name)] = new_name
        _validate_element(str(name), definition, catalog)

    cables = fragment.get("cables") or {}
    if cables and not isinstance(cables, dict):
        raise ValueError("cables must be a map")
    for name, definition in (cables or {}).items():
        if not isinstance(definition, dict):
            raise ValueError(f"Invalid cables entry: {name}")
        new_name = prefixed_name(prefix, str(name))
        if new_name in seen_cables:
            raise ValueError(f"house/v2 cables collision: {new_name}")
        seen_cables.add(new_name)
        cable_map[str(name)] = new_name
        local_cable_ids.add(str(name))

    cable_ids = set(ancestor_cable_ids or ()) | local_cable_ids

    for name, definition in (cables or {}).items():
        validate_link_entry(
            str(name),
            definition,
            catalog=catalog,
            cable_ids=cable_ids,
            current_location=location_parts,
            local_prefix=prefix,
            element_map=element_map,
            normalize_element_ref=_normalize_local_element_ref,
            split_element_terminal=_split_element_terminal,
        )
    return local_cable_ids


def validate_house_tree(
    data: dict[str, Any],
    *,
    catalog: dict[str, dict[str, Any]],
    file_location_parts: list[str],
) -> None:
    """Walk a house/v2 document and raise ``ValueError`` on structural errors."""
    assert_supported_schema(data)
    base_location = list(file_location_parts)

    # Touch place meta early so legacy ``self:`` / ``location:`` lists fail fast.
    place_meta_from_mapping(data)
    reject_legacy_keys(data)

    fragments = _walk_locations(data, base_location)
    if not fragments and (
        any(key in data for key in ("elements", "cables"))
        or place_meta_from_mapping(data) is not None
    ):
        frag: dict[str, Any] = {
            key: copy.deepcopy(data[key])
            for key in ("elements", "cables")
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
    cable_id_stack: list[tuple[list[str], set[str]]] = []
    for location_parts, fragment in fragments:
        parts_n = _norm_location_parts(location_parts)
        while cable_id_stack:
            top_parts, _ = cable_id_stack[-1]
            if _location_contains(top_parts, parts_n) and top_parts != parts_n:
                break
            cable_id_stack.pop()
        ancestor_ids: set[str] = set()
        for _, ids in cable_id_stack:
            ancestor_ids |= ids
        local_ids = _validate_flat_fragment(
            fragment,
            catalog=catalog,
            location_parts=location_parts,
            seen_elements=seen_elements,
            seen_cables=seen_cables,
            ancestor_cable_ids=ancestor_ids,
        )
        cable_id_stack.append((parts_n, local_ids))


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

    direct_keys = {"elements", "cables"}
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
    if "cables" in node:
        flat_node["cables"] = node["cables"]

    place_meta = place_meta_from_mapping(node)
    if place_meta is not None:
        for key, value in place_meta.items():
            flat_node[key] = copy.deepcopy(value)

    for name, defn in location_elements.items():
        meta_only = {k: v for k, v in defn.items() if k not in location_child_keys}
        if meta_only or not any(k in defn for k in {"elements", "cables"}):
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
        if any(k in defn for k in {"elements", "cables"}):
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





