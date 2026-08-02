"""Element ``terminal_grid`` — same face-grid syntax as location ``opening_grid``.

``terminal_grid: { NS: 2 }`` means 2 cells on N **and** 2 on S (N1,N2,S1,S2).
``N: 2`` means only the north face. Cell ids reuse opening-style tokens
(``N1``, ``S2``, ``W1``, …; plane ``B1-1`` unused for typical DIN devices).
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


def _pin_sort_key(pin: str) -> tuple[int, str]:
    text = str(pin)
    if text.isdigit():
        return (0, f"{int(text):08d}")
    return (1, text)


def _axis_faces(
    grid: dict[str, tuple[int, int]],
) -> tuple[str | None, str | None]:
    """Return ``(entry, exit)`` faces preferring N/S then W/E."""
    if "N" in grid or "S" in grid:
        return ("N" if "N" in grid else None, "S" if "S" in grid else None)
    if "W" in grid or "E" in grid:
        return ("W" if "W" in grid else None, "E" if "E" in grid else None)
    return None, None


def derive_terminal_grid(
    terminals: dict[str, Any],
    collapse: list[Any] | None = None,
) -> dict[str, int]:
    """Guess a compact ``{NS: n}`` when catalog/instance omit ``terminal_grid``."""
    if collapse:
        n = len([p for p in collapse if isinstance(p, (list, tuple)) and len(p) == 2])
        return {"NS": max(1, n)}
    pins = [str(p) for p in (terminals or {})]
    if not pins:
        return {}
    dirs = [
        str((meta or {}).get("direction") or "inout").lower()
        if isinstance(meta, dict)
        else "inout"
        for meta in (terminals or {}).values()
    ]
    n_in = sum(1 for d in dirs if d == "in")
    n_out = sum(1 for d in dirs if d == "out")
    n_io = sum(1 for d in dirs if d not in {"in", "out"})
    return {"NS": max(1, n_in, n_out, n_io)}


def resolve_terminal_grid(
    *,
    instance: dict[str, Any] | None = None,
    type_def: dict[str, Any] | None = None,
    terminals: dict[str, Any] | None = None,
    collapse: list[Any] | None = None,
) -> dict[str, tuple[int, int]]:
    """Expand instance → catalog ``terminal_grid``, or derive from pins."""
    raw = None
    if isinstance(instance, dict) and instance.get("terminal_grid") is not None:
        raw = instance.get("terminal_grid")
    elif isinstance(type_def, dict) and type_def.get("terminal_grid") is not None:
        raw = type_def.get("terminal_grid")
    if raw is not None:
        return expand_terminal_grid(raw)
    derived = derive_terminal_grid(terminals or {}, collapse)
    if not derived:
        return {}
    return expand_terminal_grid(derived)


def pin_to_cells(
    terminals: dict[str, Any],
    grid: dict[str, tuple[int, int]],
    collapse: list[Any] | None = None,
) -> dict[str, list[str]]:
    """Map each pin id to preferred terminal cell ids (e.g. ``1`` → ``[N1]``).

    - ``terminal_pairs`` pairs become columns: first pin → entry face, second → exit.
    - ``inout`` pins without collapse share a column on both axis faces.
    - ``in`` / ``out`` without collapse fill entry / exit columns in pin order.
    """
    if not grid or not terminals:
        return {}
    entry, exit_ = _axis_faces(grid)
    result: dict[str, list[str]] = {}

    def add(pin: str, cells: list[str]) -> None:
        key = str(pin)
        if key not in result:
            result[key] = []
        for cell in cells:
            if cell not in result[key]:
                result[key].append(cell)

    def face_cols(face: str | None) -> int:
        if face is None or face not in grid:
            return 0
        cols, rows = grid[face]
        return max(1, int(cols) * int(rows))

    pairs: list[tuple[str, str]] = []
    if collapse:
        for pair in collapse:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                pairs.append((str(pair[0]), str(pair[1])))

    if pairs:
        for i, (a, b) in enumerate(pairs):
            col = i + 1
            if entry and a in terminals:
                add(a, [f"{entry}{min(col, face_cols(entry) or col)}"])
            if exit_ and b in terminals:
                add(b, [f"{exit_}{min(col, face_cols(exit_) or col)}"])
            # If a pin is missing from the pair face, still record the peer face.
            if a in terminals and a not in result and exit_:
                add(a, [f"{exit_}{min(col, face_cols(exit_) or col)}"])
            if b in terminals and b not in result and entry:
                add(b, [f"{entry}{min(col, face_cols(entry) or col)}"])
        for pin in terminals:
            if str(pin) not in result:
                # Leftover pins: pack onto entry then exit.
                col = len(result) + 1
                cells: list[str] = []
                if entry:
                    cells.append(f"{entry}{min(col, face_cols(entry) or col)}")
                if exit_:
                    cells.append(f"{exit_}{min(col, face_cols(exit_) or col)}")
                if cells:
                    add(str(pin), cells)
        return result

    pins_in = [
        str(p)
        for p, m in terminals.items()
        if isinstance(m, dict) and str(m.get("direction") or "").lower() == "in"
    ]
    pins_out = [
        str(p)
        for p, m in terminals.items()
        if isinstance(m, dict) and str(m.get("direction") or "").lower() == "out"
    ]
    pins_io = [
        str(p)
        for p, m in terminals.items()
        if str(p) not in pins_in and str(p) not in pins_out
    ]
    pins_in.sort(key=_pin_sort_key)
    pins_out.sort(key=_pin_sort_key)
    pins_io.sort(key=_pin_sort_key)

    for i, pin in enumerate(pins_in):
        col = i + 1
        if entry:
            add(pin, [f"{entry}{min(col, face_cols(entry) or col)}"])
        elif exit_:
            add(pin, [f"{exit_}{min(col, face_cols(exit_) or col)}"])

    for i, pin in enumerate(pins_out):
        col = i + 1
        if exit_:
            add(pin, [f"{exit_}{min(col, face_cols(exit_) or col)}"])
        elif entry:
            add(pin, [f"{entry}{min(col, face_cols(entry) or col)}"])

    for i, pin in enumerate(pins_io):
        col = i + 1
        cells = []
        if entry:
            cells.append(f"{entry}{min(col, face_cols(entry) or col)}")
        if exit_:
            cells.append(f"{exit_}{min(col, face_cols(exit_) or col)}")
        # Also support WE-only or single-face grids already handled; if only one
        # side face exists beyond axis, attach there.
        if not cells:
            for face in ("N", "S", "W", "E"):
                if face in grid and face in SIDE_FACES:
                    cells.append(f"{face}{min(col, face_cols(face) or col)}")
                    break
        if cells:
            add(pin, cells)

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
    type_collapse = type_def.get("terminal_pairs")
    type_grid_raw = type_def.get("terminal_grid")
    subtypes = type_def.get("subtypes") if isinstance(type_def, dict) else None
    if isinstance(subtypes, dict) and subtype is not None:
        sub = subtypes.get(str(subtype))
        if isinstance(sub, dict):
            if sub.get("terminals") is not None:
                type_terminals = sub.get("terminals") or {}
            if "terminal_pairs" in sub:
                type_collapse = sub.get("terminal_pairs")
            if sub.get("terminal_grid") is not None:
                type_grid_raw = sub.get("terminal_grid")

    terminals = _merge_terminal_dicts(type_terminals, instance.get("terminals"))
    # If the instance lists terminals, those are the pins that exist on the
    # device (catalog still supplies meta for shared keys). Avoid mapping
    # unused catalog pins onto a smaller terminal_grid.
    inst_terms = instance.get("terminals")
    if isinstance(inst_terms, dict) and inst_terms:
        terminals = {
            str(k): terminals[str(k)]
            for k in inst_terms
            if str(k) in terminals
        }
    collapse = instance.get("terminal_pairs")
    if collapse is None:
        collapse = type_collapse

    effective_type = dict(type_def)
    if type_grid_raw is not None:
        effective_type["terminal_grid"] = type_grid_raw
    grid = resolve_terminal_grid(
        instance=instance,
        type_def=effective_type,
        terminals=terminals,
        collapse=collapse if isinstance(collapse, list) else None,
    )
    cells = pin_to_cells(
        terminals,
        grid,
        collapse if isinstance(collapse, list) else None,
    )
    return terminals, grid, cells
