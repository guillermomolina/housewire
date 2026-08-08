"""Open-ended cable runs: open → claim → land.

``open`` records a cable leaving a known opening toward an unknown far end
(``OPEN_Linea_NN``). ``claim`` attaches the next physical hop (conduit).
``land`` adds the electrical connection and closes the id (rename off ``OPEN_``).

Distinct from ``pend`` (local pass-through ``PEND_*`` inside one box).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from housewire.house.conduit_ref import format_conduit_endpoint, split_conduit_endpoint
from housewire.house.links import connection_type
from housewire.house import load_catalog
from housewire.site import abm
from housewire.site.recipes import _expand_pin_spec

_OPEN_CABLE_RE = re.compile(r"^OPEN_Linea_(\d+)$")
_STATUS_RE = re.compile(r"status:\s*(open|claimed|landed|pending)\b", re.I)
_LEAVES_RE = re.compile(r"leaves\s+([^\s;]+)", re.I)
_ENTERS_RE = re.compile(r"enters\s+([^\s;]+)", re.I)
_EXITS_RE = re.compile(r"exits\s+([^\s;]+)", re.I)

OpenStatus = Literal["open", "claimed", "landed", "pending"]


@dataclass(frozen=True)
class OpenMeta:
    status: OpenStatus
    leaves: str | None = None
    enters: str | None = None
    exits: str | None = None
    extra: str = ""


@dataclass(frozen=True)
class OpenCableHit:
    cable_name: str
    doc: dict[str, Any]
    yaml_path: Any  # Path | None for pure-doc tests
    meta: OpenMeta
    cable: dict[str, Any]


def next_open_cable_name(doc: dict[str, Any]) -> str:
    cables = doc.get("cables") or {}
    max_n = 0
    if isinstance(cables, dict):
        for name in cables:
            match = _OPEN_CABLE_RE.match(str(name))
            if match:
                max_n = max(max_n, int(match.group(1)))
    return f"OPEN_Linea_{max_n + 1:02d}"


def parse_open_notes(notes: str | None) -> OpenMeta:
    text = str(notes or "").strip()
    status_m = _STATUS_RE.search(text)
    status: OpenStatus = "open"
    if status_m:
        status = status_m.group(1).lower()  # type: ignore[assignment]
    leaves_m = _LEAVES_RE.search(text)
    enters_m = _ENTERS_RE.search(text)
    exits_m = _EXITS_RE.search(text)

    def _token(match: re.Match[str] | None) -> str | None:
        if match is None:
            return None
        return match.group(1).rstrip(";,").strip() or None

    # Strip known tokens for leftover human notes
    extra = text
    for pattern in (_STATUS_RE, _LEAVES_RE, _ENTERS_RE, _EXITS_RE):
        extra = pattern.sub("", extra)
    extra = re.sub(r"[;\s]+", " ", extra).strip(" ;")
    return OpenMeta(
        status=status,
        leaves=_token(leaves_m),
        enters=_token(enters_m),
        exits=_token(exits_m),
        extra=extra,
    )


def format_open_notes(
    *,
    status: OpenStatus,
    leaves: str | None = None,
    enters: str | None = None,
    exits: str | None = None,
    extra: str | None = None,
) -> str:
    bits = [f"status: {status}"]
    if leaves:
        bits.append(f"leaves {leaves}")
    if enters:
        bits.append(f"enters {enters}")
    if exits:
        bits.append(f"exits {exits}")
    if extra and str(extra).strip():
        bits.append(str(extra).strip())
    return "; ".join(bits)


def resolve_leave_ref(opening_arg: str, *, current_location_ref: str) -> str:
    """``S2`` → ``CurrentBox.S2``; ``Box.S2`` / ``A/B.S2`` unchanged."""
    text = str(opening_arg).strip()
    if not text:
        raise ValueError("opening is required (e.g. S2 or Cuadro_General.S2)")
    if "." in text:
        split_conduit_endpoint(text)
        return text
    loc = str(current_location_ref).strip()
    if not loc or loc in (".", "self"):
        return format_conduit_endpoint(".", text)
    return format_conduit_endpoint(loc, text)


def add_open_cable(
    doc: dict[str, Any],
    *,
    leaves: str,
    section: str | None = None,
    colors: list[str] | None = None,
    subtype: str | None = abm.DEFAULT_CABLE_SUBTYPE,
    label: str | None = None,
    notes: str | None = None,
    cable_name: str | None = None,
) -> str:
    """Create ``OPEN_*`` cable + conductors (no conduit, no terminal ends yet)."""
    leaves_ref = str(leaves).strip()
    split_conduit_endpoint(leaves_ref)
    loc, opening = split_conduit_endpoint(leaves_ref)
    if loc in (".", "", "self"):
        abm.require_opening_ids(doc, opening)
    name = cable_name or next_open_cable_name(doc)
    if name in (doc.get("cables") or {}):
        raise ValueError(f"Cable already exists: {name}")
    note = format_open_notes(status="open", leaves=leaves_ref, extra=notes)
    resolved_colors = list(colors) if colors else ["BN", "BU"]
    conductor_ids: list[str] = []
    for index, col in enumerate(resolved_colors, start=1):
        cid = f"{name}_{index}"
        abm.add_conductor(
            doc,
            cid,
            section=section,
            color=col,
            subtype=subtype,
            label=label,
            notes=note,
        )
        conductor_ids.append(cid)
    abm.add_cable(
        doc,
        name,
        contains=conductor_ids,
        subtype=subtype,
        section=section,
        label=label,
        notes=note,
    )
    return name


def find_cable_in_doc(doc: dict[str, Any], cable_name: str) -> dict[str, Any] | None:
    cables = doc.get("cables") or {}
    if not isinstance(cables, dict):
        return None
    entry = cables.get(cable_name)
    return entry if isinstance(entry, dict) else None


def conduits_containing(doc: dict[str, Any], cable_name: str) -> list[str]:
    hits: list[str] = []
    cables = doc.get("cables") or {}
    if not isinstance(cables, dict):
        return hits
    catalog = load_catalog()
    for name, entry in cables.items():
        if not isinstance(entry, dict):
            continue
        try:
            if connection_type(entry) != "Conduit":
                continue
        except ValueError:
            continue
        contains = [str(c) for c in (entry.get("contains") or [])]
        if cable_name in contains:
            hits.append(str(name))
    return hits


def rename_cable(doc: dict[str, Any], old_name: str, new_name: str) -> None:
    """Rename a cables entry and rewrite ``contains`` references."""
    cables = doc.setdefault("cables", {})
    if not isinstance(cables, dict) or old_name not in cables:
        raise ValueError(f"Cable does not exist: {old_name}")
    if new_name in cables:
        raise ValueError(f"Cable already exists: {new_name}")
    if old_name == new_name:
        return
    cables[new_name] = cables.pop(old_name)
    # Rename child conductors OPEN_x_1 → Final_1 when renaming cable.
    child_renames: list[tuple[str, str]] = []
    for name in list(cables):
        if name == new_name:
            continue
        if str(name).startswith(old_name + "_"):
            child_renames.append((str(name), new_name + str(name)[len(old_name) :]))
    for old_c, new_c in child_renames:
        if new_c in cables:
            raise ValueError(f"Cable already exists: {new_c}")
        cables[new_c] = cables.pop(old_c)
    for entry in cables.values():
        if not isinstance(entry, dict):
            continue
        contains = entry.get("contains")
        if not isinstance(contains, list):
            continue
        entry["contains"] = [
            (
                new_name
                if str(c) == old_name
                else new_name + str(c)[len(old_name) :]
                if str(c).startswith(old_name + "_")
                else c
            )
            for c in contains
        ]


def claim_open_cable(
    doc: dict[str, Any],
    cable_name: str,
    *,
    enter: str,
    exit: str | None = None,
    conduit_name: str | None = None,
) -> tuple[str, OpenMeta]:
    """Attach a physical hop: conduit from previous end → ``enter``.

    First claim uses ``leaves`` from notes. Later claims use previous ``exits``
    (pass-through at the last box) as the new from-end.
    """
    cable = find_cable_in_doc(doc, cable_name)
    if cable is None:
        raise ValueError(f"Cable does not exist: {cable_name}")
    meta = parse_open_notes(cable.get("notes"))
    if meta.status == "landed":
        raise ValueError(f"{cable_name} is already landed")
    if not _OPEN_CABLE_RE.match(cable_name) and meta.status not in {"open", "claimed"}:
        raise ValueError(
            f"{cable_name} is not an open run (expected OPEN_* or status open/claimed)"
        )

    enter_ref = str(enter).strip()
    split_conduit_endpoint(enter_ref)
    exit_ref = str(exit).strip() if exit else None
    if exit_ref:
        split_conduit_endpoint(exit_ref)

    if meta.status == "open" or not meta.enters:
        from_ref = meta.leaves
        if not from_ref:
            raise ValueError(
                f"{cable_name} has no leaves=… in notes; cannot claim first hop"
            )
    else:
        from_ref = meta.exits
        if not from_ref:
            raise ValueError(
                f"{cable_name} has no exits=… from the previous claim; "
                "pass --exit on the prior claim, or land here"
            )

    hop_n = len(conduits_containing(doc, cable_name)) + 1
    cd_name = conduit_name or f"Conducto_{cable_name}_{hop_n:02d}"
    abm.add_conduit(
        doc,
        cd_name,
        contains=[cable_name],
        from_ref=from_ref,
        to_ref=enter_ref,
    )
    new_meta = OpenMeta(
        status="claimed",
        leaves=meta.leaves,
        enters=enter_ref,
        exits=exit_ref,
        extra=meta.extra,
    )
    cable["notes"] = format_open_notes(
        status=new_meta.status,
        leaves=new_meta.leaves,
        enters=new_meta.enters,
        exits=new_meta.exits,
        extra=new_meta.extra or None,
    )
    return cd_name, new_meta


def land_open_cable(
    doc: dict[str, Any],
    cable_name: str,
    *,
    from_ref: str,
    to_ref: str,
    as_name: str | None = None,
    notes: str | None = None,
) -> str:
    """Set conductor from/to, rename off ``OPEN_``, clear open status."""
    cable = find_cable_in_doc(doc, cable_name)
    if cable is None:
        raise ValueError(f"Cable does not exist: {cable_name}")
    meta = parse_open_notes(cable.get("notes"))
    if meta.status == "landed":
        raise ValueError(f"{cable_name} is already landed")
    if as_name is None:
        if _OPEN_CABLE_RE.match(cable_name):
            raise ValueError(
                f"land {cable_name} requires --as FinalName "
                "(do not keep the OPEN_ prefix)"
            )
        final_name = cable_name
    else:
        final_name = str(as_name).strip()
        if not final_name:
            raise ValueError("--as name cannot be empty")
        if _OPEN_CABLE_RE.match(final_name):
            raise ValueError(f"Final name must not keep OPEN_ prefix: {final_name}")
    if final_name != cable_name:
        rename_cable(doc, cable_name, final_name)
        cable = find_cable_in_doc(doc, final_name)
        assert cable is not None
    contains = [str(c) for c in (cable.get("contains") or [])]
    from_specs = _expand_pin_spec(str(from_ref).strip())
    to_specs = _expand_pin_spec(str(to_ref).strip())
    if len(from_specs) != len(to_specs):
        raise ValueError("from and to must expand to the same number of terminals")
    if len(contains) != len(from_specs):
        raise ValueError(
            f"{final_name} has {len(contains)} conductors but "
            f"from/to expand to {len(from_specs)} terminals"
        )
    for cid, fr, tr in zip(contains, from_specs, to_specs, strict=True):
        child = find_cable_in_doc(doc, cid)
        if child is None:
            raise ValueError(f"Missing conductor {cid} under {final_name}")
        child["from"] = fr
        child["to"] = tr
        child.pop("notes", None)
    extra = notes if notes is not None else meta.extra
    if extra:
        cable["notes"] = str(extra).strip()
    else:
        trail = []
        if meta.leaves:
            trail.append(f"from {meta.leaves}")
        if meta.enters:
            trail.append(f"to {meta.enters}")
        if trail:
            cable["notes"] = "; ".join(trail)
        else:
            cable.pop("notes", None)
    return final_name


def list_open_cables(doc: dict[str, Any]) -> list[tuple[str, OpenMeta]]:
    """Return open/claimed (not landed) cables in ``doc``."""
    rows: list[tuple[str, OpenMeta]] = []
    cables = doc.get("cables") or {}
    if not isinstance(cables, dict):
        return rows
    catalog = load_catalog()
    for name, entry in cables.items():
        if not isinstance(entry, dict):
            continue
        try:
            type_id = connection_type(entry)
        except ValueError:
            continue
        if type_id != "Cable":
            continue
        meta = parse_open_notes(entry.get("notes"))
        is_open_id = bool(_OPEN_CABLE_RE.match(str(name)))
        if is_open_id or meta.status in {"open", "claimed"}:
            if meta.status == "landed":
                continue
            rows.append((str(name), meta))
    return sorted(rows, key=lambda r: r[0])

def current_location_ref(logical_parts: list[str]) -> str:
    """Conduit location ref for the current place (``A/B`` or ``.`` at root)."""
    if not logical_parts:
        return "."
    return "/".join(logical_parts)


def opening_ref_at(logical_parts: list[str], opening: str) -> str:
    """Build ``LocationRef.OpeningId`` for an opening at ``logical_parts``."""
    op = str(opening).strip()
    if "." in op:
        split_conduit_endpoint(op)
        return op
    return format_conduit_endpoint(current_location_ref(logical_parts), op)
