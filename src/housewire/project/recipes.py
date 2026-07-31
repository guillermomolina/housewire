"""High-level capture recipes: socket, lamp, feed.

Each recipe creates cable + conduit + connection (and, for socket/lamp, the
caller creates the destination place + element). Defaults match common Spanish
domestic patterns (Schuko from terminal strip; LightPoint + Luminaire).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from housewire.house.conduit_ref import split_conduit_endpoint
from housewire.project import abm

# --- Socket (DeviceBox + Schuko) ------------------------------------------------

SOCKET_DEFAULT_COLORS = ["GY", "GNYE", "BU"]
SOCKET_DEFAULT_SECTION = "2.5 mm2"
SOCKET_DEFAULT_STRIP_PINS = ["3", "2", "1"]  # L, PE, N on typical strip
SOCKET_TERMINALS = ["L", "PE", "N"]
SOCKET_ELEMENT = "Socket"
SOCKET_DEFAULT_TO_OPENING = "N1"
SOCKET_PLACE_TYPE = "DeviceBox"
SOCKET_PLACE_SUBTYPE = "1-gang"
SOCKET_ELEMENT_SUBTYPE = "Schuko"

# --- Lamp (LightPoint + Luminaire) ----------------------------------------------

LAMP_DEFAULT_COLORS_3 = ["BN", "GNYE", "BU"]
LAMP_DEFAULT_COLORS_2 = ["BN", "BU"]
LAMP_DEFAULT_SECTION = "1.5 mm2"
LAMP_DEFAULT_TO_OPENING = "B1-1"
LAMP_ELEMENT = "Luminaire"
LAMP_PLACE_TYPE = "LightPoint"
LAMP_PLACE_SUBTYPE = "ceiling-hole"
LAMP_DEFAULT_TO_PINS_3 = ["1", "2", "3"]
LAMP_DEFAULT_TO_PINS_2 = ["1", "3"]

# --- Feed (box ↔ box) -----------------------------------------------------------

FEED_DEFAULT_COLORS = ["BN", "BU"]
FEED_DEFAULT_SECTION = "1.5 mm2"


@dataclass(frozen=True)
class WiredRunResult:
    cable_name: str
    conduit_name: str
    from_terminals: str
    via_ref: str
    to_terminals: str


def parse_pins(raw: str | Sequence[str] | None) -> list[str]:
    """Parse ``3,2,1`` or ``[3, 2, 1]`` into pin id strings."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(p).strip() for p in raw if str(p).strip()]
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [part.strip() for part in text.split(",") if part.strip()]


def format_terminal_ref(element_path: str, pins: Sequence[str]) -> str:
    """Build ``Box/Regleta.[3, 2, 1]`` or ``Box/Regleta.1``."""
    path = str(element_path).strip().rstrip(".")
    if not path:
        raise ValueError("element path cannot be empty")
    cleaned = [str(p).strip() for p in pins if str(p).strip()]
    if not cleaned:
        raise ValueError("pins cannot be empty")
    if len(cleaned) == 1:
        return f"{path}.{cleaned[0]}"
    return f"{path}.[{', '.join(cleaned)}]"


def format_via_ref(cable_name: str, wire_count: int) -> str:
    if wire_count < 1:
        raise ValueError("wire_count must be >= 1")
    if wire_count == 1:
        return f"{cable_name}.1"
    indices = ", ".join(str(i) for i in range(1, wire_count + 1))
    return f"{cable_name}.[{indices}]"


def qualify_element_path(box_location: str, strip: str) -> str:
    """Join ``Caja_derivacion_2`` + ``Regleta`` → ``Caja_derivacion_2/Regleta``.

    If ``strip`` already contains ``/``, it is returned unchanged.
    Local box (``.``) leaves the strip bare (``Regleta``).
    """
    strip_s = str(strip).strip()
    if not strip_s:
        raise ValueError("strip / element path cannot be empty")
    if "/" in strip_s:
        return strip_s
    box = str(box_location).strip()
    if box in (".", "", "self"):
        return strip_s
    return f"{box}/{strip_s}"


def qualify_pin_ref(box_location: str, pin_spec: str) -> str:
    """Qualify ``Regleta.1`` or ``Regleta.[1, 2]`` under ``box_location``."""
    spec = str(pin_spec).strip()
    if not spec:
        raise ValueError("pin ref cannot be empty")
    if "/" in spec:
        return spec
    box = str(box_location).strip()
    if box in (".", "", "self"):
        return spec
    return f"{box}/{spec}"


def default_cable_name(place_id: str, *, prefix: str = "Linea_a_") -> str:
    return f"{prefix}{place_id}"


def default_conduit_name(place_id: str, *, prefix: str = "Conducto_a_") -> str:
    return f"{prefix}{place_id}"


def add_wired_run(
    doc: dict[str, Any],
    *,
    cable_name: str,
    conduit_name: str,
    from_opening: str,
    to_opening: str,
    from_terminals: str,
    to_terminals: str,
    colors: list[str],
    section: str | None = None,
    notes: str | None = None,
    label: str | None = None,
    subtype: str | None = abm.DEFAULT_CABLE_SUBTYPE,
) -> WiredRunResult:
    """Add cable + conduit + one connection joining terminal arrays."""
    if not colors:
        raise ValueError("colors cannot be empty")
    via_ref = format_via_ref(cable_name, len(colors))
    abm.add_cable(
        doc,
        cable_name,
        section=section,
        colors=list(colors),
        subtype=subtype,
        label=label,
        notes=notes,
    )
    abm.add_conduit(
        doc,
        conduit_name,
        contains=[cable_name],
        from_ref=from_opening,
        to_ref=to_opening,
    )
    abm.add_connection(
        doc,
        from_ref=from_terminals,
        via_ref=via_ref,
        to_ref=to_terminals,
    )
    return WiredRunResult(
        cable_name=cable_name,
        conduit_name=conduit_name,
        from_terminals=from_terminals,
        via_ref=via_ref,
        to_terminals=to_terminals,
    )


def socket_wired_run(
    doc: dict[str, Any],
    *,
    place_id: str,
    from_ref: str,
    strip: str,
    pins: Sequence[str] | None = None,
    to_opening: str = SOCKET_DEFAULT_TO_OPENING,
    colors: list[str] | None = None,
    section: str | None = None,
    notes: str | None = None,
    cable_name: str | None = None,
    conduit_name: str | None = None,
    element_name: str = SOCKET_ELEMENT,
) -> WiredRunResult:
    """Wire parent doc: strip → new socket place (place must already exist)."""
    box_loc, _opening = split_conduit_endpoint(from_ref)
    strip_pins = list(pins) if pins is not None else list(SOCKET_DEFAULT_STRIP_PINS)
    if len(strip_pins) != 3:
        raise ValueError(
            f"socket recipe expects 3 strip pins (L,PE,N order); got {strip_pins!r}"
        )
    resolved_colors = list(colors) if colors is not None else list(SOCKET_DEFAULT_COLORS)
    if len(resolved_colors) != 3:
        raise ValueError(
            f"socket recipe expects 3 colors (phase, PE, N); got {resolved_colors!r}"
        )
    element_path = qualify_element_path(box_loc, strip)
    from_terminals = format_terminal_ref(element_path, strip_pins)
    to_terminals = format_terminal_ref(f"{place_id}/{element_name}", SOCKET_TERMINALS)
    return add_wired_run(
        doc,
        cable_name=cable_name or default_cable_name(place_id),
        conduit_name=conduit_name or default_conduit_name(place_id),
        from_opening=from_ref,
        to_opening=f"{place_id}.{to_opening}",
        from_terminals=from_terminals,
        to_terminals=to_terminals,
        colors=resolved_colors,
        section=section if section is not None else SOCKET_DEFAULT_SECTION,
        notes=notes,
    )


def lamp_wired_run(
    doc: dict[str, Any],
    *,
    place_id: str,
    from_ref: str,
    strip: str,
    pins: Sequence[str],
    to_pins: Sequence[str] | None = None,
    to_opening: str = LAMP_DEFAULT_TO_OPENING,
    colors: list[str] | None = None,
    section: str | None = None,
    notes: str | None = None,
    cable_name: str | None = None,
    conduit_name: str | None = None,
    element_name: str = LAMP_ELEMENT,
) -> WiredRunResult:
    """Wire parent doc: strip → new luminaire place (place must already exist)."""
    strip_pins = [str(p).strip() for p in pins if str(p).strip()]
    if len(strip_pins) not in (2, 3):
        raise ValueError(
            f"lamp recipe expects 2 or 3 strip pins; got {strip_pins!r}"
        )
    if to_pins is None:
        dest_pins = (
            list(LAMP_DEFAULT_TO_PINS_3)
            if len(strip_pins) == 3
            else list(LAMP_DEFAULT_TO_PINS_2)
        )
    else:
        dest_pins = [str(p).strip() for p in to_pins if str(p).strip()]
    if len(dest_pins) != len(strip_pins):
        raise ValueError(
            f"to-pins length ({len(dest_pins)}) must match strip pins ({len(strip_pins)})"
        )
    if colors is not None:
        resolved_colors = list(colors)
    else:
        resolved_colors = (
            list(LAMP_DEFAULT_COLORS_3)
            if len(strip_pins) == 3
            else list(LAMP_DEFAULT_COLORS_2)
        )
    if len(resolved_colors) != len(strip_pins):
        raise ValueError(
            f"colors length ({len(resolved_colors)}) must match strip pins "
            f"({len(strip_pins)})"
        )
    box_loc, _opening = split_conduit_endpoint(from_ref)
    element_path = qualify_element_path(box_loc, strip)
    from_terminals = format_terminal_ref(element_path, strip_pins)
    to_terminals = format_terminal_ref(f"{place_id}/{element_name}", dest_pins)
    return add_wired_run(
        doc,
        cable_name=cable_name or default_cable_name(place_id),
        conduit_name=conduit_name or default_conduit_name(place_id),
        from_opening=from_ref,
        to_opening=f"{place_id}.{to_opening}",
        from_terminals=from_terminals,
        to_terminals=to_terminals,
        colors=resolved_colors,
        section=section if section is not None else LAMP_DEFAULT_SECTION,
        notes=notes,
    )


def feed_wired_run(
    doc: dict[str, Any],
    *,
    name: str,
    from_opening: str,
    to_opening: str,
    from_pin: str,
    to_pin: str,
    colors: list[str] | None = None,
    section: str | None = None,
    notes: str | None = None,
    cable_name: str | None = None,
    conduit_name: str | None = None,
) -> WiredRunResult:
    """Wire a run between two existing places (no new location)."""
    from_box, _ = split_conduit_endpoint(from_opening)
    to_box, _ = split_conduit_endpoint(to_opening)
    from_terminals = qualify_pin_ref(from_box, from_pin)
    to_terminals = qualify_pin_ref(to_box, to_pin)
    # If pin specs are bare ``Regleta.1``, qualify_pin_ref already prefixed.
    # If they look like ``Regleta`` + need array form, caller should pass
    # ``Regleta.[1, 2]`` or ``Regleta.1``.
    resolved_colors = list(colors) if colors is not None else list(FEED_DEFAULT_COLORS)
    return add_wired_run(
        doc,
        cable_name=cable_name or name,
        conduit_name=conduit_name or f"Conducto_{name}",
        from_opening=from_opening,
        to_opening=to_opening,
        from_terminals=from_terminals,
        to_terminals=to_terminals,
        colors=resolved_colors,
        section=section if section is not None else FEED_DEFAULT_SECTION,
        notes=notes,
    )
