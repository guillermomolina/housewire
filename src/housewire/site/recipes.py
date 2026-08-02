"""High-level capture recipes: socket, lamp, feed.

Each recipe creates Conductor leaves + optional Cable sheath + Conduit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from housewire.house.conduit_ref import split_conduit_endpoint
from housewire.site import abm

# --- Socket (DeviceBox + Schuko) ------------------------------------------------

SOCKET_DEFAULT_COLORS = ["GY", "GNYE", "BU"]
SOCKET_DEFAULT_SECTION = "2.5 mm2"
# Strip N3=L, N2=PE, N1=N → Socket N1=L, N2=PE, N3=N
SOCKET_DEFAULT_STRIP_PINS = ["N3", "N2", "N1"]
SOCKET_TERMINALS = ["N1", "N2", "N3"]
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
LAMP_DEFAULT_TO_PINS_3 = ["N1", "N2", "N3"]
LAMP_DEFAULT_TO_PINS_2 = ["N1", "N3"]

# --- Feed (box ↔ box) -----------------------------------------------------------

FEED_DEFAULT_COLORS = ["BN", "BU"]
FEED_DEFAULT_SECTION = "1.5 mm2"


@dataclass(frozen=True)
class WiredRunResult:
    cable_name: str
    conduit_name: str
    conductor_names: tuple[str, ...]
    from_terminals: tuple[str, ...]
    to_terminals: tuple[str, ...]


def normalize_pin_id(pin: str) -> str:
    """Bare digits become north face cells (``3`` → ``N3``)."""
    text = str(pin).strip()
    if text.isdigit():
        return f"N{text}"
    return text


def parse_pins(raw: str | Sequence[str] | None) -> list[str]:
    """Parse ``N3,N2,N1`` or ``3,2,1`` into face-cell pin id strings."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [normalize_pin_id(p) for p in raw if str(p).strip()]
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [normalize_pin_id(part) for part in text.split(",") if part.strip()]


def format_terminal_ref(element_path: str, pin: str) -> str:
    """Build ``Box/Regleta.N1`` (bare digit pins become ``N*``)."""
    path = str(element_path).strip().rstrip(".")
    pin_s = normalize_pin_id(pin)
    if not path or not pin_s:
        raise ValueError("element path and pin are required")
    return f"{path}.{pin_s}"


def qualify_element_path(box_location: str, strip: str) -> str:
    """Join ``Caja_derivacion_2`` + ``Regleta`` → ``Caja_derivacion_2/Regleta``."""
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
    """Qualify ``Regleta.1`` under ``box_location``."""
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
    from_pins: Sequence[str],
    to_pins: Sequence[str],
    colors: list[str],
    section: str | None = None,
    notes: str | None = None,
    label: str | None = None,
    subtype: str | None = abm.DEFAULT_CABLE_SUBTYPE,
) -> WiredRunResult:
    """Add conductors + sheath + conduit joining terminal pairs one-to-one."""
    if not colors:
        raise ValueError("colors cannot be empty")
    if not (len(from_pins) == len(to_pins) == len(colors)):
        raise ValueError(
            "from_pins, to_pins, and colors must have the same length"
        )
    conductor_names: list[str] = []
    from_refs: list[str] = []
    to_refs: list[str] = []
    for index, (fp, tp, col) in enumerate(
        zip(from_pins, to_pins, colors, strict=True), start=1
    ):
        cid = f"{cable_name}_{index}"
        abm.add_conductor(
            doc,
            cid,
            section=section,
            color=col,
            from_ref=str(fp),
            to_ref=str(tp),
            subtype=subtype,
            label=label,
            notes=notes,
        )
        conductor_names.append(cid)
        from_refs.append(str(fp))
        to_refs.append(str(tp))
    abm.add_sheath(
        doc,
        cable_name,
        contains=conductor_names,
        subtype=subtype,
        section=section,
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
    return WiredRunResult(
        cable_name=cable_name,
        conduit_name=conduit_name,
        conductor_names=tuple(conductor_names),
        from_terminals=tuple(from_refs),
        to_terminals=tuple(to_refs),
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
    strip_pins = (
        list(pins)
        if pins is not None
        else list(SOCKET_DEFAULT_STRIP_PINS)
    )
    strip_pins = [normalize_pin_id(p) for p in strip_pins]
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
    from_pins = [format_terminal_ref(element_path, p) for p in strip_pins]
    to_pins = [
        format_terminal_ref(f"{place_id}/{element_name}", p) for p in SOCKET_TERMINALS
    ]
    return add_wired_run(
        doc,
        cable_name=cable_name or default_cable_name(place_id),
        conduit_name=conduit_name or default_conduit_name(place_id),
        from_opening=from_ref,
        to_opening=f"{place_id}.{to_opening}",
        from_pins=from_pins,
        to_pins=to_pins,
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
    strip_pins = [normalize_pin_id(p) for p in pins if str(p).strip()]
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
        dest_pins = [normalize_pin_id(p) for p in to_pins if str(p).strip()]
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
    from_pin_refs = [format_terminal_ref(element_path, p) for p in strip_pins]
    to_pin_refs = [
        format_terminal_ref(f"{place_id}/{element_name}", p) for p in dest_pins
    ]
    return add_wired_run(
        doc,
        cable_name=cable_name or default_cable_name(place_id),
        conduit_name=conduit_name or default_conduit_name(place_id),
        from_opening=from_ref,
        to_opening=f"{place_id}.{to_opening}",
        from_pins=from_pin_refs,
        to_pins=to_pin_refs,
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
    resolved_colors = list(colors) if colors is not None else list(FEED_DEFAULT_COLORS)
    # Expand bare Regleta.1 or multi ``Regleta.[1, 2]`` via parse helpers.
    from_specs = _expand_pin_spec(qualify_pin_ref(from_box, from_pin))
    to_specs = _expand_pin_spec(qualify_pin_ref(to_box, to_pin))
    if len(from_specs) == 1 and len(to_specs) == 1 and len(resolved_colors) > 1:
        # Multi-color feed with single pin pair is invalid; require matching lengths.
        raise ValueError(
            "feed with multiple colors needs matching from/to pin lists "
            "(e.g. Regleta.[1, 2])"
        )
    if len(from_specs) != len(to_specs):
        raise ValueError("from_pin and to_pin must expand to the same length")
    if len(from_specs) != len(resolved_colors):
        if len(from_specs) == 1 and len(resolved_colors) == 1:
            pass
        else:
            raise ValueError(
                "colors length must match the number of from/to pins"
            )
    if len(from_specs) == 1 and len(resolved_colors) == 1:
        pass
    return add_wired_run(
        doc,
        cable_name=cable_name or name,
        conduit_name=conduit_name or f"Conducto_{name}",
        from_opening=from_opening,
        to_opening=to_opening,
        from_pins=from_specs,
        to_pins=to_specs,
        colors=resolved_colors
        if len(resolved_colors) == len(from_specs)
        else resolved_colors[: len(from_specs)],
        section=section if section is not None else FEED_DEFAULT_SECTION,
        notes=notes,
    )


def _expand_pin_spec(spec: str) -> list[str]:
    """``Path.N1`` → [Path.N1]; ``Path.[N1, N2]`` / ``Path.[1, 2]`` → list."""
    text = str(spec).strip()
    if ".[" in text and text.endswith("]"):
        head, _, body = text.partition(".[")
        pins = [normalize_pin_id(p) for p in body[:-1].split(",") if p.strip()]
        return [f"{head}.{p}" for p in pins]
    if "." in text:
        head, _, pin = text.rpartition(".")
        return [f"{head}.{normalize_pin_id(pin)}"]
    return [normalize_pin_id(text)]
