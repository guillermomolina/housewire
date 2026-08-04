"""Unified house/v2 ``cables`` map: Conduit, Cable (sheath), Conductor."""
from __future__ import annotations

import copy
from typing import Any, Literal

from housewire.house.conduit_ref import split_conduit_endpoint

LinkKind = Literal["conduit", "cable", "conductor"]

DEFAULT_CABLE_TYPE = "Cable"
DEFAULT_CONDUIT_TYPE = "Conduit"
DEFAULT_CONDUCTOR_TYPE = "Conductor"

CABLE_CATALOG_KIND = "cable_type"
CONDUIT_CATALOG_KIND = "conduit_type"
CONDUCTOR_CATALOG_KIND = "conductor_type"

# Same closed set as place ``install`` (UI: surface | flush).
INSTALL_VALUES = frozenset({"surface", "flush"})
DEFAULT_INSTALL = "flush"
DEFAULT_MOUNT = "wall"
MOUNT_VALUES = frozenset({"wall", "ceiling", "floor"})


def normalize_install(raw: Any, *, context: str = "install") -> str | None:
    """Canonicalize ``install`` to ``surface`` | ``flush`` (or None if empty).

    Legacy ``in_wall`` is accepted and rewritten to ``flush`` (``in_wall``
    collided with ``mount: wall``).
    """
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    if value == "in_wall":
        value = "flush"
    if value not in INSTALL_VALUES:
        raise ValueError(
            f"{context}: install must be one of "
            f"{', '.join(sorted(INSTALL_VALUES))} (got {raw!r})"
        )
    return value


def normalize_mount(raw: Any, *, context: str = "mount") -> str | None:
    """Canonicalize ``mount`` to ``wall`` | ``ceiling`` | ``floor``."""
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


def resolve_link_kind(
    entry: dict[str, Any], catalog: dict[str, dict[str, Any]]
) -> LinkKind:
    """Classify a ``cables:`` entry by catalog kind / type id."""
    type_id = entry.get("type")
    if type_id is None:
        raise ValueError("cables entry missing type")
    type_id = str(type_id)
    type_def = catalog.get(type_id)
    kind = type_def.get("kind") if isinstance(type_def, dict) else None
    if kind == CONDUIT_CATALOG_KIND or type_id == DEFAULT_CONDUIT_TYPE:
        return "conduit"
    if kind == CONDUCTOR_CATALOG_KIND or type_id == DEFAULT_CONDUCTOR_TYPE:
        return "conductor"
    if kind == CABLE_CATALOG_KIND or type_id == DEFAULT_CABLE_TYPE:
        return "cable"
    if type_def is None:
        raise ValueError(f"Unknown cables type in catalog: {type_id}")
    raise ValueError(
        f"type: {type_id} cannot appear under cables: "
        f"(catalog kind={kind!r}; expected conduit/cable/conductor)"
    )


def expand_conduit(
    conduit: dict[str, Any], catalog: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Normalize a Conduit entry (in the unified ``cables`` map)."""
    from housewire.house import load_catalog

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
    """Normalize a Cable sheath entry (``contains``, optional jacket ``color``)."""
    from housewire.house import load_catalog

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
            f"type: {type_id} is not a cable sheath type "
            f"(catalog kind={type_def.get('kind')!r})"
        )
    if type_def is None and type_id != DEFAULT_CABLE_TYPE:
        raise ValueError(f"Unknown cable type in catalog: {type_id}")

    defaults = _catalog_defaults_for_subtype(
        type_def, str(subtype) if subtype is not None else None
    )
    out: dict[str, Any] = {"type": type_id}
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
    type_id = raw.get("type")
    if type_id is None:
        type_id = DEFAULT_CONDUCTOR_TYPE
    type_id = str(type_id)
    type_def = cat.get(type_id)
    if type_def is not None and type_def.get("kind") not in (
        None,
        CONDUCTOR_CATALOG_KIND,
    ):
        raise ValueError(
            f"type: {type_id} is not a conductor type "
            f"(catalog kind={type_def.get('kind')!r})"
        )
    if type_def is None and type_id != DEFAULT_CONDUCTOR_TYPE:
        raise ValueError(f"Unknown conductor type in catalog: {type_id}")

    defaults = _catalog_defaults_for_subtype(
        type_def, str(subtype) if subtype is not None else None
    )
    out: dict[str, Any] = {"type": type_id}
    if subtype is not None:
        out["subtype"] = str(subtype)
    for key in (
        "section",
        "gauge",
        "color",
        "from",
        "to",
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
    kind = resolve_link_kind(entry, cat)
    if kind == "conduit":
        return expand_conduit(entry, cat)
    if kind == "cable":
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
    kind = resolve_link_kind(entry, catalog)
    if kind == "conduit":
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

    if kind == "cable":
        expanded = expand_cable(entry, catalog)
        contains = expanded.get("contains") or []
        if not isinstance(contains, list) or not contains:
            raise ValueError(f"Cable sheath {name} requires non-empty contains")
        if expanded.get("from") is not None or expanded.get("to") is not None:
            raise ValueError(
                f"Cable sheath {name} must not set from/to "
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
