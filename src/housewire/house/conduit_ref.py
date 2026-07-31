"""Conduit endpoints: physical layer links locations via openings.

Canonical form: ``LocationRef.OpeningId`` (e.g. ``Caja_derivacion_4.W2``,
``Parking/Caja_derivacion_4.B2-1``, ``.N1`` for the current place).

Legacy free-text ``route`` still parses when ``from``/``to`` are absent.
"""
from __future__ import annotations

import re
from typing import Any

# LocationRef.OpeningId — opening is the part after the last '.'
_LEGACY_ROUTE_RE = re.compile(
    r"(?P<a_loc>.+?)\s+abertura\s+(?P<a_op>\S+)"
    r"\s*[↔]+\s*"
    r"(?P<b_loc>.+?)\s+abertura\s+(?P<b_op>\S+)",
    re.IGNORECASE,
)


def split_conduit_endpoint(ref: str) -> tuple[str, str]:
    """Split ``LocationRef.OpeningId`` into ``(location_ref, opening_id)``.

    ``location_ref`` is ``\".\"`` when the ref is ``.N1`` (current place).
    """
    text = str(ref).strip()
    if not text:
        raise ValueError("endpoint de conduit vacio")
    if "." not in text:
        raise ValueError(
            f"endpoint de conduit invalido {text!r}: usa LocationRef.OpeningId "
            f"(p.ej. Caja_derivacion_4.W2 o .N1)"
        )
    loc, opening = text.rsplit(".", 1)
    opening = opening.strip()
    if not opening:
        raise ValueError(f"endpoint de conduit sin abertura: {text!r}")
    loc = loc.strip() if loc.strip() else "."
    return loc, opening


def format_conduit_endpoint(location_ref: str, opening: str) -> str:
    loc = str(location_ref).strip() or "."
    return f"{loc}.{str(opening).strip()}"


def parse_legacy_route(route: str) -> tuple[str, str] | None:
    """Parse ``A abertura X ↔ B abertura Y`` into structured from/to strings.

    Returns ``(from_ref, to_ref)`` as ``LocationRef.OpeningId``, or None.
    """
    text = str(route or "").strip()
    if not text:
        return None
    match = _LEGACY_ROUTE_RE.search(text)
    if not match:
        return None
    a_loc = match.group("a_loc").strip()
    b_loc = match.group("b_loc").strip()
    a_op = match.group("a_op").strip()
    b_op = match.group("b_op").strip()
    return (
        format_conduit_endpoint(a_loc, a_op),
        format_conduit_endpoint(b_loc, b_op),
    )


def conduit_endpoints(conduit: dict[str, Any]) -> tuple[str, str] | None:
    """Return canonical ``(from_ref, to_ref)`` from structured fields or legacy route."""
    from_ref = conduit.get("from")
    to_ref = conduit.get("to")
    if from_ref is not None and to_ref is not None:
        return str(from_ref).strip(), str(to_ref).strip()
    if from_ref is not None or to_ref is not None:
        raise ValueError("conduit requiere from y to juntos (o solo route legacy)")
    return parse_legacy_route(str(conduit.get("route") or ""))


def resolve_location_ref(
    location_ref: str,
    *,
    current_parts: list[str],
    known: set[tuple[str, ...]],
) -> tuple[str, ...]:
    """Resolve a location ref to path parts under the project root."""
    ref = str(location_ref).strip()
    if ref in (".", "", "self"):
        return tuple(current_parts)

    parts = tuple(p for p in ref.split("/") if p)
    if not parts:
        return tuple(current_parts)

    if parts in known:
        return parts

    under_current = tuple(current_parts) + parts
    if under_current in known:
        return under_current

    if current_parts:
        under_parent = tuple(current_parts[:-1]) + parts
        if under_parent in known:
            return under_parent

    leaf = parts[-1]
    matches = [loc for loc in known if loc and loc[-1] == leaf]
    if len(parts) == 1 and len(matches) == 1:
        return matches[0]
    # Suffix match: Planta_baja/Recibidor/Cuadro_General vs Cuadro_General
    suffix_matches = [loc for loc in known if len(loc) >= len(parts) and loc[-len(parts) :] == parts]
    if len(suffix_matches) == 1:
        return suffix_matches[0]

    # Unknown external / not yet in known set: keep as absolute-looking path
    if parts in known or under_current:
        pass
    return under_current if current_parts else parts


def location_key(parts: tuple[str, ...] | list[str]) -> str:
    """Stable node key for a location path (empty = site root)."""
    seq = list(parts)
    if not seq:
        return "raiz"
    from housewire.house import location_prefix

    return location_prefix(seq) or "raiz"
