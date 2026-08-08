"""Unified house/v2 ``cables`` map: Conduit, Cable (cable), Conductor."""
from __future__ import annotations

import copy
from typing import Any, Literal

from housewire.house.conduit_ref import split_conduit_endpoint

ConnectionType = Literal["Conduit", "Cable", "Conductor"]
CONNECTION_TYPES = frozenset({"Conduit", "Cable", "Conductor"})

DEFAULT_CABLE_TYPE = "Cable"
DEFAULT_CONDUIT_TYPE = "Conduit"
DEFAULT_CONDUCTOR_TYPE = "Conductor"

CABLE_CATALOG_KIND = "CableType"
CONDUIT_CATALOG_KIND = "ConduitType"
CONDUCTOR_CATALOG_KIND = "ConductorType"
PLACE_CATALOG_KIND = "PlaceType"
ELEMENT_CATALOG_KIND = "ElementType"

# Same closed set as place ``install`` (UI: Surface | Flush).
INSTALL_VALUES = frozenset({"Surface", "Flush"})
DEFAULT_INSTALL = "Flush"
DEFAULT_MOUNT = "Wall"
MOUNT_VALUES = frozenset({"Wall", "Ceiling", "Floor"})


def normalize_install(raw: Any, *, context: str = "install") -> str | None:
    """Canonicalize ``install`` to ``Surface`` | ``Flush`` (or None if empty)."""
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    if value not in INSTALL_VALUES:
        raise ValueError(
            f"{context}: install must be one of "
            f"{', '.join(sorted(INSTALL_VALUES))} (got {raw!r})"
        )
    return value


def normalize_mount(raw: Any, *, context: str = "mount") -> str | None:
    """Canonicalize ``mount`` to ``Wall`` | ``Ceiling`` | ``Floor``."""
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    if value not in MOUNT_VALUES:
        raise ValueError(
            f"{context}: mount must be one of "
            f"{', '.join(sorted(MOUNT_VALUES))} (got {raw!r})"
        )
    return value


def _normalize_install(raw: Any, *, context: str) -> str | None:
    """Backward-compatible alias."""
    return normalize_install(raw, context=context)
def _catalog_defaults_for_subtype(
    type_def: dict[str, Any] | None, subtype: str | None
) -> dict[str, Any]:
    from housewire.house import resolve_catalog_subtype_key

    defaults: dict[str, Any] = {}
    if not isinstance(type_def, dict):
        return defaults
    base = type_def.get("defaults")
    if isinstance(base, dict):
        defaults.update(copy.deepcopy(base))
    if subtype is None:
        return defaults
    key = resolve_catalog_subtype_key(type_def, subtype)
    subtypes = type_def.get("subtypes")
    if isinstance(subtypes, dict) and key is not None:
        sub = subtypes.get(str(key))
        if isinstance(sub, dict):
            sub_defaults = sub.get("defaults")
            if isinstance(sub_defaults, dict):
                defaults.update(copy.deepcopy(sub_defaults))
    return defaults


def connection_type(entry: dict[str, Any]) -> ConnectionType:
    """Return the fixed PascalCase type of a ``cables:`` entry."""
    value = entry.get("type")
    if value is None:
        raise ValueError("cables entry missing type")
    type_id = str(value)
    if type_id not in CONNECTION_TYPES:
        expected = ", ".join(sorted(CONNECTION_TYPES))
        raise ValueError(f"cables type must be one of {expected}: {type_id}")
    return type_id  # type: ignore[return-value]


def expand_conduit(
    conduit: dict[str, Any], catalog: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Normalize a Conduit entry (in the unified ``cables`` map)."""
    from housewire.house import load_catalog

    cat = catalog if catalog is not None else load_catalog()
    raw = copy.deepcopy(conduit)
    if not isinstance(raw, dict):
        raise ValueError("Invalid conduit (not a map)")

    subtype = raw.get("subtype")
    if connection_type(raw) != DEFAULT_CONDUIT_TYPE:
        raise ValueError(f"type must be {DEFAULT_CONDUIT_TYPE}")
    type_def = cat.get(DEFAULT_CONDUIT_TYPE)
    if type_def is None:
        raise ValueError(f"Unknown conduit type in catalog: {DEFAULT_CONDUIT_TYPE}")

    from housewire.house import resolve_catalog_subtype_key

    subtype = resolve_catalog_subtype_key(
        type_def, str(subtype) if subtype is not None else None
    )
    defaults = _catalog_defaults_for_subtype(type_def, subtype)
    out: dict[str, Any] = {"type": DEFAULT_CONDUIT_TYPE}
    if subtype is not None:
        out["subtype"] = str(subtype)
    for key in ("contains", "from", "to", "name", "label", "notes", "section", "color"):
        if key in raw and raw[key] is not None:
            out[key] = copy.deepcopy(raw[key])
        elif key in defaults:
            out[key] = copy.deepcopy(defaults[key])
    install = _normalize_install(raw.get("install"), context="Conduit")
    if install is None and "install" in defaults:
        install = _normalize_install(defaults.get("install"), context="Conduit")
    if install is not None:
        out["install"] = install
    return out


def expand_cable(
    cable: dict[str, Any], catalog: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Normalize a Cable entry (``contains``, optional jacket ``color``)."""
    from housewire.house import load_catalog

    cat = catalog if catalog is not None else load_catalog()
    raw = copy.deepcopy(cable)
    if not isinstance(raw, dict):
        raise ValueError("Invalid cable (not a map)")

    subtype = raw.get("subtype")
    if connection_type(raw) != DEFAULT_CABLE_TYPE:
        raise ValueError(f"type must be {DEFAULT_CABLE_TYPE}")
    type_def = cat.get(DEFAULT_CABLE_TYPE)
    if type_def is None:
        raise ValueError(f"Unknown cable type in catalog: {DEFAULT_CABLE_TYPE}")

    from housewire.house import resolve_catalog_subtype_key

    subtype = resolve_catalog_subtype_key(
        type_def, str(subtype) if subtype is not None else None
    )
    defaults = _catalog_defaults_for_subtype(type_def, subtype)
    out: dict[str, Any] = {"type": DEFAULT_CABLE_TYPE}
    if subtype is not None:
        out["subtype"] = str(subtype)
    for key in (
        "section",
        "gauge",
        "color",
        "contains",
        "name",
        "label",
        "notes",
        "manufacturer",
        "model",
    ):
        if key in raw and raw[key] is not None:
            out[key] = copy.deepcopy(raw[key])
        elif key in defaults and key not in ("gauge",):
            if key == "section" or key not in out:
                out[key] = copy.deepcopy(defaults[key])
    if "section" not in out and "gauge" not in out and defaults.get("section"):
        out["section"] = copy.deepcopy(defaults["section"])
    install = _normalize_install(raw.get("install"), context="Cable")
    if install is None and "install" in defaults:
        install = _normalize_install(defaults.get("install"), context="Cable")
    if install is not None:
        out["install"] = install
    return out


def expand_conductor(
    conductor: dict[str, Any], catalog: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Normalize a Conductor leaf (``from``/``to`` terminals, ``color``, ``section``)."""
    from housewire.house import load_catalog

    cat = catalog if catalog is not None else load_catalog()
    raw = copy.deepcopy(conductor)
    if not isinstance(raw, dict):
        raise ValueError("Invalid conductor (not a map)")

    subtype = raw.get("subtype")
    if connection_type(raw) != DEFAULT_CONDUCTOR_TYPE:
        raise ValueError(f"type must be {DEFAULT_CONDUCTOR_TYPE}")
    type_def = cat.get(DEFAULT_CONDUCTOR_TYPE)
    if type_def is None:
        raise ValueError(
            f"Unknown conductor type in catalog: {DEFAULT_CONDUCTOR_TYPE}"
        )

    from housewire.house import resolve_catalog_subtype_key

    subtype = resolve_catalog_subtype_key(
        type_def, str(subtype) if subtype is not None else None
    )
    defaults = _catalog_defaults_for_subtype(type_def, subtype)
    out: dict[str, Any] = {"type": DEFAULT_CONDUCTOR_TYPE}
    if subtype is not None:
        out["subtype"] = str(subtype)
    for key in (
        "section",
        "gauge",
        "color",
        "from",
        "to",
        "conduit_path",
        "name",
        "label",
        "notes",
        "manufacturer",
        "model",
    ):
        if key in raw and raw[key] is not None:
            out[key] = copy.deepcopy(raw[key])
        elif key in defaults and key not in ("gauge",):
            if key == "section" or key not in out:
                out[key] = copy.deepcopy(defaults[key])
    if "section" not in out and "gauge" not in out and defaults.get("section"):
        out["section"] = copy.deepcopy(defaults["section"])
    return out


def expand_link(
    entry: dict[str, Any], catalog: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    from housewire.house import load_catalog

    cat = catalog if catalog is not None else load_catalog()
    type_id = connection_type(entry)
    if type_id == "Conduit":
        return expand_conduit(entry, cat)
    if type_id == "Cable":
        return expand_cable(entry, cat)
    return expand_conductor(entry, cat)


def validate_link_entry(
    name: str,
    entry: dict[str, Any],
    *,
    catalog: dict[str, dict[str, Any]],
    cable_ids: set[str],
    current_location: list[str],
    local_prefix: str,
    element_map: dict[str, str],
    normalize_element_ref,
    split_element_terminal,
) -> None:
    """Validate one ``cables:`` entry in place context."""
    type_id = connection_type(entry)
    from housewire.house import validate_catalog_subtype

    validate_catalog_subtype(type_id, entry, catalog, context=f"cables.{name}")
    if type_id == "Conduit":
        expanded = expand_conduit(entry, catalog)
        if not expanded.get("from") or not expanded.get("to"):
            raise ValueError(f"Conduit {name} requires from and to (openings)")
        split_conduit_endpoint(str(expanded["from"]))
        split_conduit_endpoint(str(expanded["to"]))
        for cable_ref in expanded.get("contains") or []:
            ref = str(cable_ref)
            if ref not in cable_ids:
                raise ValueError(
                    f"Conduit {name} references missing cables entry: {ref}"
                )
        return

    if type_id == "Cable":
        expanded = expand_cable(entry, catalog)
        contains = expanded.get("contains") or []
        if not isinstance(contains, list) or not contains:
            raise ValueError(f"Cable {name} requires non-empty contains")
        if expanded.get("from") is not None or expanded.get("to") is not None:
            raise ValueError(
                f"Cable {name} must not set from/to "
                "(only Conductor leaves connect terminals)"
            )
        for cable_ref in contains:
            ref = str(cable_ref)
            if ref not in cable_ids:
                raise ValueError(
                    f"Cable {name} references missing cables entry: {ref}"
                )
        return

    # conductor
    expanded = expand_conductor(entry, catalog)
    if expanded.get("contains"):
        raise ValueError(f"Conductor {name} must not set contains")
    color = expanded.get("color")
    if not color:
        raise ValueError(f"Conductor missing 'color': {name}")
    section = expanded.get("section") or expanded.get("gauge")
    if not section:
        raise ValueError(f"Conductor missing 'section': {name}")
    from_ref = expanded.get("from")
    to_ref = expanded.get("to")
    # Pending/open/unlanded conductors may omit endpoints.
    if from_ref is None and to_ref is None:
        return
    if not from_ref or not to_ref:
        raise ValueError(
            f"Conductor {name} must set both from and to, or omit both "
            "(pending/open run)"
        )
    from_el, _from_pin = split_element_terminal(str(from_ref))
    to_el, _to_pin = split_element_terminal(str(to_ref))
    normalize_element_ref(
        from_el,
        current_location=current_location,
        local_prefix=local_prefix,
        local_map=element_map,
    )
    normalize_element_ref(
        to_el,
        current_location=current_location,
        local_prefix=local_prefix,
        local_map=element_map,
    )


def reject_legacy_keys(fragment: dict[str, Any]) -> None:
    if "connections" in fragment:
        raise ValueError(
            "connections: is not used in house/v2; "
            "use cables entries with type: Conductor (from/to terminals)"
        )
    if "conduits" in fragment:
        raise ValueError(
            "conduits: is not used in house/v2; "
            "use cables entries with type: Conduit"
        )


def contained_ids(
    cables: dict[str, Any], root_id: str, *, transitive: bool = True
) -> set[str]:
    """Ids reachable via ``contains`` from ``root_id`` (not including root)."""
    if root_id not in cables:
        return set()
    out: set[str] = set()
    stack = [root_id]
    seen = {root_id}
    while stack:
        cur = stack.pop()
        entry = cables.get(cur)
        if not isinstance(entry, dict):
            continue
        for ref in entry.get("contains") or []:
            rid = str(ref)
            if rid in out:
                continue
            out.add(rid)
            if transitive and rid not in seen:
                seen.add(rid)
                stack.append(rid)
    return out
