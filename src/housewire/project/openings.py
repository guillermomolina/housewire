"""JunctionBox / Panel opening ids and opening_grid helpers.

Local box frame (poker): look at the front face ``F`` (lid). Contour faces
are ``N`` ``S`` ``E`` ``W`` in that frame — not geographic north unless
``facing`` / ``mount`` align them. ``B`` is the back (embedded) face.

Side opening ids: ``N1``, ``W2``, … (1-based along the face).
Back/front ids: ``B1-1``, ``F2-3`` — row (N→S) then column (W→E).
"""

from __future__ import annotations

import re
from typing import Any

SIDE_FACES = frozenset({"N", "S", "E", "W"})
PLANE_FACES = frozenset({"F", "B"})
ALL_FACES = SIDE_FACES | PLANE_FACES
# Pair keys follow index order: N→S, W→E.
PAIR_KEYS = {"NS": ("N", "S"), "WE": ("W", "E")}

SIDE_ID_RE = re.compile(r"^([NSEW])(\d+)$")
PLANE_ID_RE = re.compile(r"^([FB])(\d+)-(\d+)$")

# Text in routes / notes: side ids, plane ids, plus legacy tokens.
OPENING_TOKEN_RE = re.compile(
    r"abertura\s+("
    r"[NSEW]\d+"
    r"|[FB]\d+-\d+"
    r"|B\d+"  # legacy opaque B1
    r"|[NSEWUD](?:\.[A-Za-z0-9]+)?"
    r"|(?:back|lid|front|fondo|tapa)(?:\.[A-Za-z0-9]+)?"
    r")",
    re.IGNORECASE,
)


def openings_from_text(*texts: str) -> list[str]:
    """Extract opening id tokens mentioned after ``abertura`` in free text."""
    found: list[str] = []
    for text in texts:
        if not text:
            continue
        for match in OPENING_TOKEN_RE.finditer(str(text)):
            token = match.group(1)
            if token not in found:
                found.append(token)
    return found


def parse_grid_spec(value: Any) -> tuple[int, int]:
    """Return ``(cols, rows)``. A bare int / ``\"3\"`` means ``3x1`` (one row)."""
    if isinstance(value, bool):
        raise ValueError(f"invalid opening_grid: {value!r}")
    if isinstance(value, int):
        if value < 1:
            raise ValueError(f"opening_grid must be >= 1: {value}")
        return value, 1
    if isinstance(value, float) and value == int(value):
        return parse_grid_spec(int(value))
    if isinstance(value, str):
        raw = value.strip().lower().replace(" ", "")
        if "x" in raw:
            left, right = raw.split("x", 1)
            cols, rows = int(left), int(right)
        else:
            cols, rows = int(raw), 1
        if cols < 1 or rows < 1:
            raise ValueError(f"opening_grid must be >= 1: {value!r}")
        return cols, rows
    raise ValueError(f"invalid opening_grid: {value!r}")


def expand_opening_grid(raw: Any) -> dict[str, tuple[int, int]]:
    """Expand ``NS``/``WE`` pairs and per-face keys into ``{face: (cols, rows)}``.

    Explicit ``N``/``S``/… override values from ``NS``/``WE``.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("location.opening_grid must be a map")

    expanded: dict[str, tuple[int, int]] = {}
    overrides: dict[str, tuple[int, int]] = {}

    for key, value in raw.items():
        name = str(key)
        if name == "EW":
            raise ValueError(
                "opening_grid key 'EW' renamed to 'WE' (W→E order, like NS)"
            )
        spec = parse_grid_spec(value)
        if name in PAIR_KEYS:
            for face in PAIR_KEYS[name]:
                expanded[face] = spec
        elif name in ALL_FACES:
            overrides[name] = spec
        else:
            raise ValueError(
                f"unknown opening_grid key: {name!r}. "
                f"Use N,S,E,W,F,B,NS,WE"
            )

    expanded.update(overrides)
    return expanded


def parse_opening_id(opening_id: str) -> tuple[str, int, int | None]:
    """Return ``(face, a, b)`` where ``b`` is set only for ``F``/``B`` plane ids."""
    oid = str(opening_id).strip().upper()
    side = SIDE_ID_RE.fullmatch(oid)
    if side:
        return side.group(1), int(side.group(2)), None
    plane = PLANE_ID_RE.fullmatch(oid)
    if plane:
        return plane.group(1), int(plane.group(2)), int(plane.group(3))
    raise ValueError(
        f"Invalid opening id: {opening_id!r}. "
        f"Use N1, W2, … or B1-1, F2-3, …"
    )


def normalize_opening_id(opening_id: str) -> str:
    face, a, b = parse_opening_id(opening_id)
    if b is None:
        return f"{face}{a}"
    return f"{face}{a}-{b}"


def opening_compass_port(opening_id: str) -> str | None:
    """Graphviz compass port for an opening id (``n``/``s``/``e``/``w``).

    Side faces map directly. Front/back (``F``/``B``) return None (default
    border clip — avoid center port ``_`` which draws into the node).
    Returns None if the id cannot be parsed.
    """
    try:
        face, _a, _b = parse_opening_id(opening_id)
    except ValueError:
        return None
    return {"N": "n", "S": "s", "E": "e", "W": "w"}.get(face)


def opening_fits_grid(opening_id: str, grid: dict[str, tuple[int, int]]) -> bool:
    """True if ``opening_id`` fits ``grid`` (missing face ⇒ no constraint)."""
    face, a, b = parse_opening_id(opening_id)
    if face not in grid:
        return True
    cols, rows = grid[face]
    if face in SIDE_FACES:
        return 1 <= a <= cols * rows
    assert b is not None
    return 1 <= a <= rows and 1 <= b <= cols


def declared_opening_ids(openings: Any) -> set[str] | None:
    """Normalize ``location.openings`` to a set of ids, or ``None`` if absent."""
    if openings is None:
        return None
    if isinstance(openings, list):
        ids: set[str] = set()
        for item in openings:
            if not isinstance(item, str):
                raise ValueError(
                    "location.openings must be a list of ids "
                    "(e.g. [N1, B1-1])"
                )
            ids.add(normalize_opening_id(item))
        return ids
    if isinstance(openings, dict):
        raise ValueError(
            "location.openings is no longer a map {B1: {face:…}}. "
            "Use a list of local ids: openings: [N1, B1-1]"
        )
    raise ValueError("location.openings must be a list of ids")


def validate_location_openings(location: dict[str, Any]) -> None:
    """Validate ``openings`` / ``opening_grid`` on a location block if present."""
    if "opening_grid" in location:
        grid = expand_opening_grid(location.get("opening_grid"))
    else:
        grid = {}

    declared = declared_opening_ids(location.get("openings"))
    if declared is None:
        return

    for oid in declared:
        parse_opening_id(oid)
        if grid and not opening_fits_grid(oid, grid):
            face, _, _ = parse_opening_id(oid)
            cols, rows = grid[face]
            raise ValueError(
                f"Opening {oid} outside opening_grid[{face}]={cols}x{rows}"
            )
