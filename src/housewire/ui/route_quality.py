"""Geometric quality checks for parallel cable routes (canvas invariants).

These detectors exist so routing can be rejected when it either:
- stacks strands on top of each other (overlap), or
- inserts short C/Z jogs that are not needed to fan onto a shared terminal.

Keep thresholds aligned with ``app.js`` (``STRAND_WIDTH``, ``LANE_GAP``).
"""
from __future__ import annotations

from typing import Sequence

Point = tuple[float, float]
Poly = Sequence[Point]

# Must match src/housewire/ui/static/app.js highway constants.
STRAND_WIDTH = 2.5
LANE_GAP = 2.5
# Pitch between neighboring lane centerlines.
LANE_PITCH = STRAND_WIDTH + LANE_GAP
# Allow a little float slack under a full pitch.
MIN_LANE_SEPARATION = LANE_PITCH - 0.75

# Short lateral jog treated as an unnecessary Z (px).
MAX_Z_LEG = 28.0
# Short reverse stub treated as an unnecessary C (px).
MAX_C_LEG = 18.0
# Terminal-only diagonals may be this long; longer = boca→element bug.
# Short diagonals are allowed ONLY on multi-cable terminal V fans.
# Openings (one cable) and single-cable terminals must stay Manhattan.
TERMINAL_DIAG_MAX = 36.0
# Radius around a mouth where any diagonal is forbidden.
OPENING_DIAG_RADIUS = 48.0
# Min run (px) along an element edge before counting as a hug.
ELEMENT_BORDER_MIN_RUN = 12.0
# Clearance (px) from element box edges for inbox corridors.
ELEMENT_BORDER_CLEARANCE = 6.0
# Contrast rim beyond tube stroke (must match app.js OUTLINE_EXTRA).
OUTLINE_EXTRA = 0.8
# Lateral pitch used for shared-terminal V fans.
FAN_LATERAL_PITCH = LANE_PITCH


def _dist(a: Point, b: Point) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _orient(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> int:
    v = (by - ay) * (cx - bx) - (bx - ax) * (cy - by)
    if abs(v) < 1e-9:
        return 0
    return 1 if v > 0 else 2


def _on_segment(
    ax: float, ay: float, bx: float, by: float, cx: float, cy: float
) -> bool:
    return (
        min(ax, bx) - 1e-9 <= cx <= max(ax, bx) + 1e-9
        and min(ay, by) - 1e-9 <= cy <= max(ay, by) + 1e-9
    )


def segments_cross(
    a0: Point, a1: Point, b0: Point, b1: Point, *, endpoint_ok: bool = True
) -> bool:
    """True when open segments properly intersect (optionally ignore shared ends)."""
    o1 = _orient(a0[0], a0[1], a1[0], a1[1], b0[0], b0[1])
    o2 = _orient(a0[0], a0[1], a1[0], a1[1], b1[0], b1[1])
    o3 = _orient(b0[0], b0[1], b1[0], b1[1], a0[0], a0[1])
    o4 = _orient(b0[0], b0[1], b1[0], b1[1], a1[0], a1[1])
    if o1 != o2 and o3 != o4:
        if endpoint_ok:
            for p in (a0, a1):
                for q in (b0, b1):
                    if _dist(p, q) < 1e-6:
                        return False
        return True
    return False


def count_strand_crossings(strands: Sequence[Poly]) -> int:
    """Count proper crossings between strand polylines (inside a shared run)."""
    n = 0
    for i in range(len(strands)):
        for j in range(i + 1, len(strands)):
            a, b = strands[i], strands[j]
            if len(a) < 2 or len(b) < 2:
                continue
            for ia in range(len(a) - 1):
                for ib in range(len(b) - 1):
                    if segments_cross(a[ia], a[ia + 1], b[ib], b[ib + 1]):
                        n += 1
    return n


def relative_luminance(css_hex: str) -> float:
    """sRGB relative luminance for a ``#rrggbb`` color."""
    h = css_hex.strip().lstrip("#")
    if len(h) != 6:
        return 0.5
    r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))

    def chan(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast_outline_css(fill_css: str) -> str:
    """High-contrast rim: light on dark fills, dark on light fills."""
    return "#ffffff" if relative_luminance(fill_css) < 0.45 else "#0d1117"


def jacket_path_is_gapped(pieces: Sequence[Poly], *, max_gap: float = 24.0) -> bool:
    """True when consecutive exterior jacket pieces leave a visible gap."""
    if len(pieces) < 2:
        return False
    for i in range(len(pieces) - 1):
        a = pieces[i]
        b = pieces[i + 1]
        if len(a) < 1 or len(b) < 1:
            continue
        # Gap between end of one piece and start of the next (or reverse).
        d = min(
            _dist(a[-1], b[0]),
            _dist(a[-1], b[-1]),
            _dist(a[0], b[0]),
            _dist(a[0], b[-1]),
        )
        if d > max_gap:
            return True
    return False


def is_diagonal_segment(a: Point, b: Point) -> bool:
    return abs(a[0] - b[0]) > 1e-6 and abs(a[1] - b[1]) > 1e-6


def count_long_diagonals(
    pts: Poly, *, max_ok: float = TERMINAL_DIAG_MAX
) -> int:
    """Count non-axis-aligned segments longer than ``max_ok`` (px)."""
    if len(pts) < 2:
        return 0
    n = 0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if not is_diagonal_segment(a, b):
            continue
        if _dist(a, b) > max_ok:
            n += 1
    return n


def count_diagonals(pts: Poly) -> int:
    """Count every non-axis-aligned segment."""
    if len(pts) < 2:
        return 0
    return sum(
        1
        for i in range(len(pts) - 1)
        if is_diagonal_segment(pts[i], pts[i + 1])
    )


def count_diagonals_near_point(
    pts: Poly, point: Point, *, radius: float = OPENING_DIAG_RADIUS
) -> int:
    """Diagonals with an endpoint within ``radius`` of ``point`` (opening)."""
    if len(pts) < 2:
        return 0
    n = 0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if not is_diagonal_segment(a, b):
            continue
        if _dist(a, point) <= radius or _dist(b, point) <= radius:
            n += 1
    return n


def opening_approach_is_manhattan(
    pts: Poly, mouth: Point, *, radius: float = OPENING_DIAG_RADIUS
) -> bool:
    """True when the approach near an opening has no diagonals."""
    return count_diagonals_near_point(pts, mouth, radius=radius) == 0


def manhattan_join_end(
    pts: Poly, target: Point, face: str = "S"
) -> list[Point]:
    """Append a Manhattan L from ``pts`` end to ``target`` (opening join).

    Mirrors ``orthoJoinEnd`` in ``app.js``. Never introduces a diagonal.
    """
    tx, ty = target
    if not pts:
        return [(tx, ty)]
    out: list[Point] = [(p[0], p[1]) for p in pts]
    lx, ly = out[-1]
    if _dist((lx, ly), (tx, ty)) < 1e-6:
        return out
    if abs(lx - tx) < 1e-6 or abs(ly - ty) < 1e-6:
        out.append((tx, ty))
        return out
    f = (face or "S").upper()
    if f in ("E", "W"):
        out.append((lx, ty))
        out.append((tx, ty))
    else:
        out.append((tx, ly))
        out.append((tx, ty))
    return out


def ensure_manhattan_near_point(
    pts: Poly, point: Point, *, radius: float = OPENING_DIAG_RADIUS
) -> list[Point]:
    """Rewrite diagonals near ``point`` into Manhattan L corners."""
    if len(pts) < 2:
        return [(p[0], p[1]) for p in pts]
    out: list[Point] = [(p[0], p[1]) for p in pts]
    changed = True
    while changed:
        changed = False
        for i in range(len(out) - 1):
            a, b = out[i], out[i + 1]
            if not is_diagonal_segment(a, b):
                continue
            if _dist(a, point) > radius and _dist(b, point) > radius:
                continue
            corner = (b[0], a[1])
            out = out[: i + 1] + [corner] + out[i + 1 :]
            changed = True
            break
    return out


def terminal_v_lead(
    pin: Point,
    face: str,
    lane_pt: Point,
    slot: int,
    slot_count: int,
) -> list[Point]:
    """Mirror of multi-cable ``pinToLanePts``: one V diagonal, then Manhattan."""
    out_dir, lat = _face_axes(face)
    stub = (pin[0] + out_dir[0] * 5.0, pin[1] + out_dir[1] * 5.0)
    mid = (slot_count - 1) / 2.0
    fan_lat = (slot - mid) * FAN_LATERAL_PITCH
    tip = (
        stub[0] + out_dir[0] * 10.0 + lat[0] * fan_lat,
        stub[1] + out_dir[1] * 10.0 + lat[1] * fan_lat,
    )
    return manhattan_join_end([pin, stub, tip], lane_pt, face=face)


def terminal_lead_issues(
    pts: Poly,
    pin: Point,
    *,
    multi_cable: bool,
    radius: float = 36.0,
) -> list[str]:
    """Flag jagged terminal leads (screenshot Regleta peaks / multi-diags)."""
    issues: list[str] = []
    n_diag = count_diagonals_near_point(pts, pin, radius=radius)
    if multi_cable:
        if n_diag == 0:
            issues.append("shared terminal: missing V diagonal")
        elif n_diag > 1:
            issues.append(
                f"shared terminal: {n_diag} diagonals near pin (want exactly 1)"
            )
    elif n_diag:
        issues.append(
            f"single-cable terminal: {n_diag} diagonal(s) near pin "
            "(must be Manhattan)"
        )
    # Spike / reverse near pin: short segment that turns back toward the pin.
    if len(pts) >= 3:
        seq = list(pts)
        if _dist(seq[0], pin) > 1.5 and _dist(seq[-1], pin) <= 1.5:
            seq = list(reversed(seq))
        for i in range(1, min(len(seq) - 1, 6)):
            d_prev = _dist(seq[i - 1], pin)
            d_cur = _dist(seq[i], pin)
            d_next = _dist(seq[i + 1], pin)
            if d_cur > d_prev + 8 and d_next < d_cur - 8:
                issues.append("terminal lead spikes away then back (jagged)")
                break
    return issues


def max_diagonal_length(pts: Poly) -> float:
    """Longest diagonal segment length, or 0 if none."""
    best = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if is_diagonal_segment(a, b):
            best = max(best, _dist(a, b))
    return best


def _seg_seg_distance(
    a0: Point, a1: Point, b0: Point, b1: Point
) -> float:
    """Minimum distance between two finite segments (2D)."""
    # Sample denser on longer segments; exact for ortho pairs is enough here.
    steps = max(4, int(max(_dist(a0, a1), _dist(b0, b1)) // 4) + 1)
    best = float("inf")
    for i in range(steps + 1):
        t = i / steps
        ax = a0[0] + t * (a1[0] - a0[0])
        ay = a0[1] + t * (a1[1] - a0[1])
        for j in range(steps + 1):
            u = j / steps
            bx = b0[0] + u * (b1[0] - b0[0])
            by = b0[1] + u * (b1[1] - b0[1])
            best = min(best, _dist((ax, ay), (bx, by)))
    return best


def min_polyline_separation(a: Poly, b: Poly) -> float:
    """Minimum distance between any pair of segments of two polylines."""
    if len(a) < 2 or len(b) < 2:
        return float("inf")
    best = float("inf")
    for i in range(len(a) - 1):
        for j in range(len(b) - 1):
            best = min(
                best, _seg_seg_distance(a[i], a[i + 1], b[j], b[j + 1])
            )
    return best


def strands_overlap(
    strands: Sequence[Poly], *, min_separation: float = MIN_LANE_SEPARATION
) -> bool:
    """True when any two strands run closer than ``min_separation``."""
    for i in range(len(strands)):
        for j in range(i + 1, len(strands)):
            if min_polyline_separation(strands[i], strands[j]) < min_separation:
                return True
    return False


def _bend_dirs(pts: Poly) -> list[tuple[float, float, float]]:
    """Per vertex (except ends): incoming dx,dy and segment length before bend."""
    out: list[tuple[float, float, float]] = []
    if len(pts) < 3:
        return out
    for i in range(1, len(pts) - 1):
        ax, ay = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
        bx, by = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
        cross = ax * by - ay * bx
        if abs(cross) < 1e-6:
            continue
        out.append((ax, ay, _dist(pts[i - 1], pts[i])))
    return out


def count_z_jogs(pts: Poly, *, max_leg: float = MAX_Z_LEG) -> int:
    """Count short Z (direction reverse after two bends) along a polyline.

    Pattern: travel → turn → short leg → turn back toward the prior axis.
    """
    if len(pts) < 4:
        return 0
    count = 0
    for i in range(1, len(pts) - 2):
        a = pts[i - 1]
        b = pts[i]
        c = pts[i + 1]
        d = pts[i + 2]
        ab = (b[0] - a[0], b[1] - a[1])
        bc = (c[0] - b[0], c[1] - b[1])
        cd = (d[0] - c[0], d[1] - c[1])
        # Need two turns.
        if abs(ab[0] * bc[1] - ab[1] * bc[0]) < 1e-6:
            continue
        if abs(bc[0] * cd[1] - bc[1] * cd[0]) < 1e-6:
            continue
        mid_len = _dist(b, c)
        if mid_len <= 1e-6 or mid_len > max_leg:
            continue
        # Z: first and third segments share an axis and oppose or skip.
        ab_h = abs(ab[1]) < 1e-6
        cd_h = abs(cd[1]) < 1e-6
        if ab_h != cd_h:
            continue
        # Mid leg is perpendicular to ab.
        bc_h = abs(bc[1]) < 1e-6
        if ab_h == bc_h:
            continue
        count += 1
    return count


def count_c_jogs(pts: Poly, *, max_leg: float = MAX_C_LEG) -> int:
    """Count short C hooks: stub out then immediately reverse on the same axis."""
    if len(pts) < 3:
        return 0
    count = 0
    for i in range(len(pts) - 2):
        a, b, c = pts[i], pts[i + 1], pts[i + 2]
        ab = (b[0] - a[0], b[1] - a[1])
        bc = (c[0] - b[0], c[1] - b[1])
        # Colinear opposite directions (180° reverse).
        if abs(ab[0] * bc[1] - ab[1] * bc[0]) > 1e-6:
            continue
        dot = ab[0] * bc[0] + ab[1] * bc[1]
        if dot >= 0:
            continue
        if _dist(a, b) <= max_leg or _dist(b, c) <= max_leg:
            count += 1
    return count


def _face_axes(face: str) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return (outward unit, lateral unit) for a cardinal face."""
    f = (face or "?").upper()
    if f == "N":
        return (0.0, -1.0), (1.0, 0.0)
    if f == "S":
        return (0.0, 1.0), (1.0, 0.0)
    if f == "W":
        return (-1.0, 0.0), (0.0, 1.0)
    if f == "E":
        return (1.0, 0.0), (0.0, 1.0)
    return (0.0, 0.0), (1.0, 0.0)


def approach_point_before_pin(pts: Poly, pin: Point, *, tol: float = 1.5) -> Point | None:
    """Vertex used to judge V-entry (skip pin + short outward stub)."""
    if len(pts) < 2:
        return None
    if _dist(pts[0], pin) <= tol:
        seq = list(pts)
    elif _dist(pts[-1], pin) <= tol:
        seq = list(reversed(pts))
    else:
        return None
    # seq[0] ~= pin. Skip a short stub (≤8px) so V fans use the fan tip.
    if len(seq) >= 3 and _dist(seq[0], seq[1]) <= 8.0:
        return (seq[2][0], seq[2][1])
    return (seq[1][0], seq[1][1])


def shared_terminal_entry_is_v(
    pin: Point,
    face: str,
    approach_pts: Sequence[Point],
    *,
    min_lateral_span: float = FAN_LATERAL_PITCH * 0.6,
) -> bool:
    """True when ≥2 approaches fan laterally (V), not stacked on the normal.

    ``approach_pts`` are the vertices immediately before the pin (or after a
    short stub) for each strand sharing the terminal.
    """
    if len(approach_pts) < 2:
        return True
    _out, lat = _face_axes(face)
    laterals = [
        (p[0] - pin[0]) * lat[0] + (p[1] - pin[1]) * lat[1] for p in approach_pts
    ]
    return (max(laterals) - min(laterals)) >= min_lateral_span


def perpendicular_shared_terminal_entry(
    pin: Point,
    face: str,
    approach_pts: Sequence[Point],
    *,
    lateral_tol: float = 2.0,
) -> bool:
    """True when several strands share a pin but all approach on the face normal.

    This is the live Luminaire/Regleta bug: stub then axis-aligned rejoin with
    no lateral fan (looks like a perpendicular stack, not a V).
    """
    if len(approach_pts) < 2:
        return False
    return not shared_terminal_entry_is_v(
        pin, face, approach_pts, min_lateral_span=lateral_tol + 0.5
    )


Rect = tuple[float, float, float, float]  # x, y, w, h


def polyline_hugs_rect_border(
    pts: Poly,
    rect: Rect,
    *,
    clearance: float = ELEMENT_BORDER_CLEARANCE,
    min_run: float = ELEMENT_BORDER_MIN_RUN,
    ignore_near: Sequence[Point] | None = None,
) -> bool:
    """True when a segment runs along a rect edge within ``clearance``.

    Short terminal stubs ending at ``ignore_near`` pins are skipped so a
    legitimate face landing is not flagged.
    """
    if len(pts) < 2:
        return False
    rx, ry, rw, rh = rect
    left, right = rx, rx + rw
    top, bottom = ry, ry + rh
    ignore = list(ignore_near or [])

    def near_ignored(p: Point) -> bool:
        return any(_dist(p, q) <= clearance + 1.0 for q in ignore)

    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        run = _dist(a, b)
        if run < min_run:
            continue
        # Skip segments that terminate on an ignored pin (final lead).
        if near_ignored(a) or near_ignored(b):
            continue
        ax, ay = a
        bx, by = b
        horiz = abs(ay - by) < 1e-6
        vert = abs(ax - bx) < 1e-6
        if horiz:
            y = ay
            x0, x1 = sorted((ax, bx))
            # Overlap in x with the rect.
            if x1 < left - 1e-6 or x0 > right + 1e-6:
                continue
            if abs(y - top) <= clearance or abs(y - bottom) <= clearance:
                return True
        elif vert:
            x = ax
            y0, y1 = sorted((ay, by))
            if y1 < top - 1e-6 or y0 > bottom + 1e-6:
                continue
            if abs(x - left) <= clearance or abs(x - right) <= clearance:
                return True
    return False


def assess_bundle(
    strands: Sequence[Poly],
    *,
    min_separation: float = MIN_LANE_SEPARATION,
    allow_z: bool = False,
    allow_c: bool = False,
    allow_long_diagonal: bool = False,
    allow_terminal_v: bool = False,
    allow_crossings: bool = False,
    element_rects: Sequence[Rect] | None = None,
    shared_terminals: Sequence[
        tuple[Point, str, Sequence[Poly]]
    ]
    | None = None,
    openings: Sequence[Point] | None = None,
) -> list[str]:
    """Return human-readable problems for a parallel strand bundle.

    ``allow_z`` / ``allow_c``: set True only when several strands share one
    terminal and an intentional fan is expected.
    ``allow_long_diagonal``: set True only in tests of the detector itself.
    ``allow_terminal_v``: short diagonals OK (multi-cable terminal V only).
    ``allow_crossings``: set True only when intentional crossing is expected.
    ``element_rects``: flag inbox segments that hug element box borders.
    ``shared_terminals``: list of (pin, face, strand_polys) that must V-enter.
    ``openings``: mouth points where any diagonal is forbidden.
    """
    issues: list[str] = []
    if len(strands) >= 2 and strands_overlap(
        strands, min_separation=min_separation
    ):
        issues.append("strands overlap (lane separation too small)")
    if not allow_crossings:
        n = count_strand_crossings(strands)
        if n:
            issues.append(f"strands cross inside the run ({n} crossing(s))")
    if not allow_z:
        for i, poly in enumerate(strands):
            n = count_z_jogs(poly)
            if n:
                issues.append(f"strand {i}: {n} unnecessary Z jog(s)")
    if not allow_c:
        for i, poly in enumerate(strands):
            n = count_c_jogs(poly)
            if n:
                issues.append(f"strand {i}: {n} unnecessary C jog(s)")
    # Diagonals: openings + single-cable terminals → Manhattan only.
    # Multi-cable terminal V may use short diagonals when allow_terminal_v
    # or when shared_terminals is provided for this assessment.
    v_ok = allow_terminal_v or bool(shared_terminals)
    if not allow_long_diagonal:
        for i, poly in enumerate(strands):
            n_long = count_long_diagonals(poly)
            if n_long:
                issues.append(
                    f"strand {i}: {n_long} long diagonal(s) "
                    f"(>{TERMINAL_DIAG_MAX:g}px; boca→element)"
                )
            elif not v_ok:
                n_any = count_diagonals(poly)
                if n_any:
                    issues.append(
                        f"strand {i}: {n_any} diagonal(s) "
                        "(only multi-cable terminal V may diagonal)"
                    )
    if openings:
        for oi, mouth in enumerate(openings):
            for i, poly in enumerate(strands):
                n = count_diagonals_near_point(poly, mouth)
                if n:
                    issues.append(
                        f"strand {i}: {n} diagonal(s) near opening {oi} "
                        "(openings are Manhattan-only)"
                    )
    if element_rects:
        pins: list[Point] = []
        if shared_terminals:
            pins.extend(t[0] for t in shared_terminals)
        for ri, rect in enumerate(element_rects):
            for i, poly in enumerate(strands):
                if polyline_hugs_rect_border(
                    poly, rect, ignore_near=pins
                ):
                    issues.append(
                        f"strand {i}: hugs element rect {ri} border"
                    )
    if shared_terminals:
        for ti, (pin, face, polys) in enumerate(shared_terminals):
            approaches: list[Point] = []
            for poly in polys:
                ap = approach_point_before_pin(poly, pin)
                if ap is not None:
                    approaches.append(ap)
            if len(approaches) >= 2 and perpendicular_shared_terminal_entry(
                pin, face, approaches
            ):
                issues.append(
                    f"shared terminal {ti}: perpendicular entry (want V)"
                )
    return issues


def offset_ortho(pts: Poly, dist: float) -> list[Point]:
    """Manhattan parallel offset (same corner join as ``offsetOrthoPts`` in JS)."""
    if len(pts) < 2 or abs(dist) < 1e-9:
        return [(p[0], p[1]) for p in pts]
    src = [(p[0], p[1]) for p in pts]
    segs: list[tuple[float, float, float, float, bool]] = []
    for i in range(len(src) - 1):
        dx = src[i + 1][0] - src[i][0]
        dy = src[i + 1][1] - src[i][1]
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        nx = (-dy / length) * dist
        ny = (dx / length) * dist
        horiz = abs(dy) < 1e-6
        segs.append(
            (
                src[i][0] + nx,
                src[i][1] + ny,
                src[i + 1][0] + nx,
                src[i + 1][1] + ny,
                horiz,
            )
        )
    out: list[Point] = [(segs[0][0], segs[0][1])]
    for i in range(len(segs) - 1):
        s0 = segs[i]
        s1 = segs[i + 1]
        if s0[4] and not s1[4]:
            out.append((s1[0], s0[1]))
        elif not s0[4] and s1[4]:
            out.append((s0[0], s1[1]))
        else:
            out.append((s0[2], s0[3]))
    last = segs[-1]
    out.append((last[2], last[3]))
    return out


def highway_lane_offset(lane_index: int, strand_count: int) -> float:
    """Match ``highwayLaneOffset`` in app.js."""
    n = max(1, int(strand_count))
    i = max(0, min(n - 1, int(lane_index)))
    pitch = STRAND_WIDTH + LANE_GAP
    content = n * STRAND_WIDTH + (n - 1) * LANE_GAP
    first = -content / 2 + STRAND_WIDTH / 2
    return first + i * pitch


def parallel_highway_bundle(centerline: Poly, strand_count: int) -> list[list[Point]]:
    """Build ``strand_count`` parallel lanes of a shared orthogonal centerline."""
    return [
        offset_ortho(centerline, highway_lane_offset(i, strand_count))
        for i in range(strand_count)
    ]
