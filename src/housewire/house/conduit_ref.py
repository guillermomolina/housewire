"""Conduit endpoints: physical layer links locations via openings.

Canonical form: ``LocationRef.OpeningId`` (e.g. ``Caja_derivacion_4.W2``,
``Parking/Caja_derivacion_4.B2-1``, ``.N1`` for the current place).
"""
from __future__ import annotations

from typing import Any


def split_conduit_endpoint(ref: str) -> tuple[str, str]:
    """Split ``LocationRef.OpeningId`` into ``(location_ref, opening_id)``.

    ``location_ref`` is ``\".\"`` when the ref is ``.N1`` (current place).
    """
    text = str(ref).strip()
    if not text:
        raise ValueError("empty conduit endpoint")
    if "." not in text:
        raise ValueError(
            f"invalid conduit endpoint {text!r}: use LocationRef.OpeningId "
            f"(e.g. Caja_derivacion_4.W2 or .N1)"
        )
    loc, opening = text.rsplit(".", 1)
    opening = opening.strip()
    if not opening:
        raise ValueError(f"conduit endpoint missing opening: {text!r}")
    loc = loc.strip() if loc.strip() else "."
    return loc, opening


def format_conduit_endpoint(location_ref: str, opening: str) -> str:
    loc = str(location_ref).strip() or "."
    return f"{loc}.{str(opening).strip()}"


def conduit_endpoints(conduit: dict[str, Any]) -> tuple[str, str]:
    """Return ``(from_ref, to_ref)``; both fields are required."""
    from_ref = conduit.get("from")
    to_ref = conduit.get("to")
    if from_ref is None or to_ref is None:
        raise ValueError(
            "conduit requires from and to (LocationRef.OpeningId, e.g. Caja.W2)"
        )
    return str(from_ref).strip(), str(to_ref).strip()


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
    suffix_matches = [
        loc for loc in known if len(loc) >= len(parts) and loc[-len(parts) :] == parts
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]

    return under_current if current_parts else parts


def location_key(parts: tuple[str, ...] | list[str]) -> str:
    """Stable node key for a location path (empty = site root)."""
    seq = list(parts)
    if not seq:
        return "raiz"
    from housewire.house import location_prefix

    return location_prefix(seq) or "raiz"
