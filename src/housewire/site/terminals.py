"""Element ``terminal_grid`` — same face-grid syntax as location ``opening_grid``.

Terminal **ids** are face-cell tokens (``N1``, ``S2``, …), identical to opening
ids. Optional ``name`` / ``label`` / ``role`` are display metadata only.

``terminal_grid: { NS: 2 }`` means 2 cells on N **and** 2 on S (N1,N2,S1,S2).
``N: 2`` means only the north face.

For ``direction: InOut`` pins on an NS/WE grid, the opposite-face cell of the
same index is also an attach point (e.g. TerminalStrip ``N1`` → ``[N1, S1]``).
"""

from __future__ import annotations

from typing import Any

from housewire.site.openings import (
    SIDE_FACES,
    expand_opening_grid,
    normalize_opening_id,
    parse_opening_id,
)

# Re-export under terminal names (identical grammar).
expand_terminal_grid = expand_opening_grid
parse_terminal_cell = parse_opening_id
normalize_terminal_cell = normalize_opening_id


def _try_parse_cell(pin: str) -> tuple[str, int, int | None] | None:
    try:
        return parse_opening_id(str(pin))
    except ValueError:
        return None


def _pin_sort_key(pin: str) -> tuple:
    parsed = _try_parse_cell(pin)
    if parsed is not None:
        face, a, b = parsed
        return (0, face, a, b if b is not None else 0)
    text = str(pin)
    if text.isdigit():
        return (1, f"{int(text):08d}")
    return (2, text)


def _axis_faces(
    grid: dict[str, tuple[int, int]],
) -> tuple[str | None, str | None]:
    """Return ``(entry, exit)`` faces preferring N/S then W/E."""
    if "N" in grid or "S" in grid:
        return ("N" if "N" in grid else None, "S" if "S" in grid else None)
    if "W" in grid or "E" in grid:
        return ("W" if "W" in grid else None, "E" if "E" in grid else None)
    return None, None


def _opposite_face(face: str) -> str | None:
    pairs = {"N": "S", "S": "N", "W": "E", "E": "W"}
    return pairs.get(face)


def derive_terminal_grid(terminals: dict[str, Any]) -> dict[str, int]:
    """Guess a compact face grid from face-cell pin ids."""
    counts: dict[str, int] = {}
    for pin in terminals or {}:
        parsed = _try_parse_cell(str(pin))
        if parsed is None:
            continue
        face, a, b = parsed
        if face in SIDE_FACES:
            counts[face] = max(counts.get(face, 0), int(a))
        elif face in {"B", "F"}:
            cols = int(b) if b is not None else int(a)
            rows = int(a)
            counts[face] = max(counts.get(face, 0), cols * rows)
    if not counts:
        n = len(terminals or {})
        return {"NS": max(1, n)} if n else {}
    if "N" in counts and "S" in counts:
        ns = max(counts["N"], counts["S"])
        out: dict[str, int] = {"NS": ns}
        for face, n in counts.items():
            if face not in {"N", "S"}:
                out[face] = n
        return out
    if "W" in counts and "E" in counts:
        we = max(counts["W"], counts["E"])
        out = {"WE": we}
        for face, n in counts.items():
            if face not in {"W", "E"}:
                out[face] = n
        return out
    return dict(counts)


def resolve_terminal_grid(
    *,
    instance: dict[str, Any] | None = None,
    type_def: dict[str, Any] | None = None,
    terminals: dict[str, Any] | None = None,
) -> dict[str, tuple[int, int]]:
    """Expand instance → catalog ``terminal_grid``, or derive from pin ids."""
    raw = None
    if isinstance(instance, dict) and instance.get("terminal_grid") is not None:
        raw = instance.get("terminal_grid")
    elif isinstance(type_def, dict) and type_def.get("terminal_grid") is not None:
        raw = type_def.get("terminal_grid")
    if raw is not None:
        return expand_terminal_grid(raw)
    derived = derive_terminal_grid(terminals or {})
    if not derived:
        return {}
    return expand_terminal_grid(derived)


def pin_to_cells(
    terminals: dict[str, Any],
    grid: dict[str, tuple[int, int]],
) -> dict[str, list[str]]:
    """Map each pin id to attach cell ids.

    Face-cell pin ids map to themselves. ``inout`` pins also attach on the
    opposite axis face at the same index when that face exists in ``grid``
    (TerminalStrip ``N1`` → ``[N1, S1]``).
    """
    if not terminals:
        return {}
    result: dict[str, list[str]] = {}
    entry, exit_ = _axis_faces(grid)

    for pin, meta in terminals.items():
        key = str(pin)
        cells: list[str] = []
        parsed = _try_parse_cell(key)
        if parsed is not None:
            face, a, _b = parsed
            try:
                cell = normalize_opening_id(key)
            except ValueError:
                cell = key
            cells.append(cell)
            direction = (
                str((meta or {}).get("direction") or "InOut")
                if isinstance(meta, dict)
                else "InOut"
            )
            if direction == "InOut" and face in SIDE_FACES:
                opp = _opposite_face(face)
                if opp and opp in grid:
                    cells.append(f"{opp}{a}")
        if cells:
            result[key] = cells

    # Leftover non-cell pins (should be rare after migration).
    leftovers = [str(p) for p in terminals if str(p) not in result]
    leftovers.sort(key=_pin_sort_key)
    for i, pin in enumerate(leftovers, start=1):
        cells = []
        if entry:
            cells.append(f"{entry}{i}")
        if exit_:
            cells.append(f"{exit_}{i}")
        if not cells:
            for face in ("N", "S", "W", "E"):
                if face in grid:
                    cells.append(f"{face}{i}")
                    break
        if cells:
            result[pin] = cells

    return result


def grid_to_api(grid: dict[str, tuple[int, int]]) -> dict[str, list[int]]:
    """JSON-friendly ``{face: [cols, rows]}`` like place ``opening_grid``."""
    return {face: [int(cols), int(rows)] for face, (cols, rows) in grid.items()}


def _merge_terminal_dicts(
    catalog_terminals: dict[str, Any], instance_terminals: dict[str, Any] | None
) -> dict[str, dict[str, Any]]:
    import copy

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


def element_terminal_layout(
    instance: dict[str, Any],
    catalog: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, tuple[int, int]], dict[str, list[str]]]:
    """Return ``(merged_terminals, grid, pin_cells)`` for a canvas element."""
    type_id = str(instance.get("type") or "")
    type_def: dict[str, Any] = {}
    if catalog and type_id in catalog and isinstance(catalog[type_id], dict):
        type_def = catalog[type_id]

    subtype = instance.get("subtype")
    if subtype is None and isinstance(type_def.get("defaults"), dict):
        subtype = type_def["defaults"].get("subtype")
    type_terminals = type_def.get("terminals") or {}
    type_grid_raw = type_def.get("terminal_grid")
    subtypes = type_def.get("subtypes") if isinstance(type_def, dict) else None
    if isinstance(subtypes, dict) and subtype is not None:
        sub = subtypes.get(str(subtype))
        if isinstance(sub, dict):
            if sub.get("terminals") is not None:
                type_terminals = sub.get("terminals") or {}
            if sub.get("terminal_grid") is not None:
                type_grid_raw = sub.get("terminal_grid")

    terminals = _merge_terminal_dicts(type_terminals, instance.get("terminals"))
    effective_type = dict(type_def)
    if type_grid_raw is not None:
        effective_type["terminal_grid"] = type_grid_raw
    grid = resolve_terminal_grid(
        instance=instance,
        type_def=effective_type,
        terminals=terminals,
    )
    # If the instance lists terminals, drop non-listed pins — except catalog
    # face-cell pins that still sit on the painted grid (cables may reference
    # N2 even when the instance only overrode N1/S1 labels).
    inst_terms = instance.get("terminals")
    if isinstance(inst_terms, dict) and inst_terms:
        keep = {str(k) for k in inst_terms if str(k) in terminals}
        for pin in list(terminals):
            if pin in keep:
                continue
            parsed = _try_parse_cell(pin)
            if parsed is None:
                terminals.pop(pin, None)
                continue
            face, idx, _b = parsed
            dims = grid.get(face)
            if not dims:
                terminals.pop(pin, None)
                continue
            cols, rows = int(dims[0]), int(dims[1])
            if idx < 1 or idx > cols * rows:
                terminals.pop(pin, None)
                continue
    cells = pin_to_cells(terminals, grid)
    return terminals, grid, cells
