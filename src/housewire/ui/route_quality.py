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


def needs_nested_contrast_rim(
    inner_css: str,
    outer_css: str,
    *,
    inner_code: str | None = None,
    outer_code: str | None = None,
    lum_delta: float = 0.28,
) -> bool:
    """True when nested stroke would vanish into its container without a rim.

    Same IEC color code (e.g. BK jacket in BK conduit) always needs the rim.
    When codes differ, the palette already separates them. Without codes, fall
    back to similar luminance (both dark / both light).
    """
    ic = (inner_code or "").strip().upper()
    oc = (outer_code or "").strip().upper()
    if ic and oc:
        return ic == oc
    if not inner_css or not outer_css:
        return False
    return abs(relative_luminance(inner_css) - relative_luminance(outer_css)) < lum_delta


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
    """Mirror of multi-cable ``pinToLanePts``: diagonal touches the pin + rail."""
    out_dir, lat = _face_axes(face)
    mid = (slot_count - 1) / 2.0
    fan_pitch = max(12.0, FAN_LATERAL_PITCH)
    fan_lat = (slot - mid) * fan_pitch
    tip = (
        pin[0] + out_dir[0] * 14.0 + lat[0] * fan_lat,
        pin[1] + out_dir[1] * 14.0 + lat[1] * fan_lat,
    )
    rail = (
        tip[0] + out_dir[0] * 18.0,
        tip[1] + out_dir[1] * 18.0,
    )
    # pin → tip (V at the terminal), rail stays on tip lateral, then Manhattan.
    return manhattan_join_end([pin, tip, rail], lane_pt, face=face)


def ensure_ortho_poly(pts: Poly) -> list[Point]:
    """Force consecutive vertices onto an orthogonal chain (mirrors app.js).

    Inserts axis-aligned corners between diagonal pairs. Destructive for
    intentional terminal V diagonals — callers must skip those.
    """
    if len(pts) < 2:
        return [(float(p[0]), float(p[1])) for p in pts]
    out: list[Point] = [(float(pts[0][0]), float(pts[0][1]))]
    for p in pts[1:]:
        q = (float(p[0]), float(p[1]))
        last = out[-1]
        if _dist(last, q) < 1e-9:
            continue
        if abs(last[0] - q[0]) < 1e-9 or abs(last[1] - q[1]) < 1e-9:
            out.append(q)
            continue
        # Prefer horizontal-then-vertical (same default as many UI joins).
        out.append((q[0], last[1]))
        out.append(q)
    clean: list[Point] = []
    for p in out:
        if not clean or _dist(clean[-1], p) > 1e-9:
            clean.append(p)
    return clean


def lift_offset_spine_from_pin(
    pts: Poly,
    pin: Point,
    face: str,
    *,
    min_out: float = 10.0,
) -> list[Point]:
    """Mirror of ``liftOffsetSpineFromPin`` — preserves pin→tip V diagonals.

    The 0.34.22 bug always ran ``ensure_ortho_poly`` and collapsed bipolar V
    arms into perpendicular stubs.
    """
    if len(pts) < 1:
        return []
    out: list[Point] = [(float(p[0]), float(p[1])) for p in pts]
    out_dir, _lat = _face_axes(face)
    if out_dir == (0.0, 0.0):
        return out
    if len(out) >= 2 and _dist(out[0], pin) < 1.5:
        if is_diagonal_segment(out[0], out[1]):
            return out
    along = (out[0][0] - pin[0]) * out_dir[0] + (out[0][1] - pin[1]) * out_dir[1]
    if along >= min_out:
        return out
    need = min_out - along
    out[0] = (out[0][0] + out_dir[0] * need, out[0][1] + out_dir[1] * need)
    return ensure_ortho_poly(out)


def strands_merge_before_pin(
    strands: Sequence[Poly],
    pin: Point,
    *,
    min_separation: float = MIN_LANE_SEPARATION,
    meet_radius: float = 4.0,
) -> bool:
    """True when strands run stacked outside ``meet_radius`` of the shared pin.

    Multi-cable terminals may only coincide at the pin itself — any closer
    approach farther out is a premature merge (screenshot Regleta bug).
    """
    if len(strands) < 2:
        return False

    def clipped(poly: Poly) -> list[Point]:
        """Keep vertices / samples farther than ``meet_radius`` from ``pin``."""
        out: list[Point] = []
        for i in range(len(poly) - 1):
            a, b = poly[i], poly[i + 1]
            for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                x = a[0] + t * (b[0] - a[0])
                y = a[1] + t * (b[1] - a[1])
                if _dist((x, y), pin) > meet_radius:
                    out.append((x, y))
        # Dedup consecutive
        clean: list[Point] = []
        for p in out:
            if not clean or _dist(clean[-1], p) > 0.5:
                clean.append(p)
        return clean

    clips = [clipped(s) for s in strands]
    for i in range(len(clips)):
        for j in range(i + 1, len(clips)):
            a, b = clips[i], clips[j]
            if len(a) < 2 or len(b) < 2:
                continue
            if min_polyline_separation(a, b) < min_separation:
                return True
    return False


def shared_terminal_both_arms_diagonal(
    strands: Sequence[Poly], pin: Point
) -> bool:
    """True when every strand touching ``pin`` enters on a diagonal (full V)."""
    if len(strands) < 2:
        return True
    for poly in strands:
        if terminal_entry_is_perpendicular(poly, pin):
            return False
        seg = first_segment_from_pin(poly, pin)
        if seg is None:
            return False
        if not is_diagonal_segment(seg[0], seg[1]):
            return False
    return True


def first_segment_from_pin(pts: Poly, pin: Point, *, tol: float = 1.5) -> tuple[Point, Point] | None:
    """Return (pin, next) for the segment that touches the pin."""
    if len(pts) < 2:
        return None
    if _dist(pts[0], pin) <= tol:
        return (pts[0][0], pts[0][1]), (pts[1][0], pts[1][1])
    if _dist(pts[-1], pin) <= tol:
        return (pts[-1][0], pts[-1][1]), (pts[-2][0], pts[-2][1])
    return None


def terminal_entry_is_perpendicular(pts: Poly, pin: Point) -> bool:
    """True when the segment touching the pin is axis-aligned (no V)."""
    seg = first_segment_from_pin(pts, pin)
    if seg is None:
        return False
    a, b = seg
    return not is_diagonal_segment(a, b)


def count_diagonals_away_from_pin(
    pts: Poly, pin: Point, *, near_radius: float = 36.0
) -> int:
    """Diagonals whose endpoints are both far from the pin (wrong place)."""
    if len(pts) < 2:
        return 0
    n = 0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if not is_diagonal_segment(a, b):
            continue
        if _dist(a, pin) > near_radius and _dist(b, pin) > near_radius:
            n += 1
    return n


def count_out_and_back(pts: Poly, *, max_leg: float = 40.0) -> int:
    """Count collinear reverse runs (ida y vuelta on the same path)."""
    return count_c_jogs(pts, max_leg=max_leg)


def terminal_lead_issues(
    pts: Poly,
    pin: Point,
    *,
    multi_cable: bool,
    radius: float = 36.0,
) -> list[str]:
    """Flag jagged / wrong terminal leads (screenshot Regleta bugs)."""
    issues: list[str] = []
    n_diag = count_diagonals_near_point(pts, pin, radius=radius)
    if multi_cable:
        if n_diag == 0:
            issues.append("shared terminal: missing V diagonal")
        elif n_diag > 1:
            issues.append(
                f"shared terminal: {n_diag} diagonals near pin (want exactly 1)"
            )
        if terminal_entry_is_perpendicular(pts, pin):
            issues.append(
                "shared terminal: perpendicular entry at pin (want V diagonal)"
            )
    elif n_diag:
        issues.append(
            f"single-cable terminal: {n_diag} diagonal(s) near pin "
            "(must be Manhattan)"
        )
    n_far = count_diagonals_away_from_pin(pts, pin, near_radius=radius)
    if n_far:
        issues.append(
            f"diagonal(s) away from pin ({n_far}) — V must sit on the terminal"
        )
    n_back = count_out_and_back(pts)
    if n_back:
        issues.append(f"out-and-back on same path ({n_back})")
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
    strands: Sequence[Poly],
    *,
    min_separation: float = MIN_LANE_SEPARATION,
    ignore_near: Sequence[Point] | None = None,
    ignore_radius: float = 16.0,
) -> bool:
    """True when any two strands run closer than ``min_separation``.

    Short segments near ``ignore_near`` (mouth stubs / pin meets) are skipped
    so legal boca/pin coincidence is not scored as a mid-run overlap.
    """
    anchors = [(float(p[0]), float(p[1])) for p in (ignore_near or [])]

    def skip_seg(a: Point, b: Point) -> bool:
        if not anchors:
            return False
        if any(
            _dist(a, q) <= ignore_radius and _dist(b, q) <= ignore_radius
            for q in anchors
        ):
            return True
        length = _dist(a, b)
        if length <= ignore_radius * 2.0:
            mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
            if any(_dist(mid, q) <= ignore_radius for q in anchors):
                return True
        return False

    def segments(poly: Poly) -> list[tuple[Point, Point]]:
        out: list[tuple[Point, Point]] = []
        for i in range(len(poly) - 1):
            a = (float(poly[i][0]), float(poly[i][1]))
            b = (float(poly[i + 1][0]), float(poly[i + 1][1]))
            if _dist(a, b) < 1e-9 or skip_seg(a, b):
                continue
            out.append((a, b))
        return out

    segs = [segments(s) for s in strands]
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            best = float("inf")
            for a0, a1 in segs[i]:
                for b0, b1 in segs[j]:
                    best = min(best, _seg_seg_distance(a0, a1, b0, b1))
            if best < min_separation:
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
    """Count short orthogonal Z jogs (unnecessary lane hops).

    Diagonal segments (terminal V) are ignored so pin→tip→rail is not a Z.
    """
    if len(pts) < 4:
        return 0
    count = 0
    for i in range(1, len(pts) - 2):
        a = pts[i - 1]
        b = pts[i]
        c = pts[i + 1]
        d = pts[i + 2]
        if (
            is_diagonal_segment(a, b)
            or is_diagonal_segment(b, c)
            or is_diagonal_segment(c, d)
        ):
            continue
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


def strip_short_z_jogs(pts: Poly, *, max_leg: float = MAX_Z_LEG) -> list[Point]:
    """Mirror of ``stripShortZJogs`` in app.js (orthogonal Z only)."""
    if len(pts) < 4:
        return [(p[0], p[1]) for p in pts]
    out: list[Point] = [(p[0], p[1]) for p in pts]
    changed = True
    while changed:
        changed = False
        for i in range(1, len(out) - 2):
            a, b, c, d = out[i - 1], out[i], out[i + 1], out[i + 2]
            if (
                is_diagonal_segment(a, b)
                or is_diagonal_segment(b, c)
                or is_diagonal_segment(c, d)
            ):
                continue
            abx, aby = b[0] - a[0], b[1] - a[1]
            bcx, bcy = c[0] - b[0], c[1] - b[1]
            cdx, cdy = d[0] - c[0], d[1] - c[1]
            if abs(abx * bcy - aby * bcx) < 1e-6:
                continue
            if abs(bcx * cdy - bcy * cdx) < 1e-6:
                continue
            mid = _dist(b, c)
            if mid <= 1e-6 or mid > max_leg:
                continue
            ab_h = abs(aby) < 1e-6
            cd_h = abs(cdy) < 1e-6
            bc_h = abs(bcy) < 1e-6
            if ab_h != cd_h or ab_h == bc_h:
                continue
            corner = (d[0], a[1]) if ab_h else (a[0], d[1])
            out = out[:i] + [corner] + out[i + 2 :]
            changed = True
            break
    return out


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
    place_rects: Sequence[Rect] | None = None,
    shared_terminals: Sequence[
        tuple[Point, str, Sequence[Poly]]
    ]
    | None = None,
    openings: Sequence[Point] | None = None,
    tube_centerline: Poly | None = None,
    tube_half_width: float | None = None,
) -> list[str]:
    """Return human-readable problems for a parallel strand bundle.

    ``allow_z`` / ``allow_c``: set True only when several strands share one
    terminal and an intentional fan is expected.
    ``allow_long_diagonal``: set True only in tests of the detector itself.
    ``allow_terminal_v``: short diagonals OK (multi-cable terminal V only).
    ``allow_crossings``: set True only when intentional crossing is expected.
    ``element_rects``: flag inbox segments that hug element box borders.
    ``place_rects``: flag segments that hug place/box borders.
    ``shared_terminals``: list of (pin, face, strand_polys) that must V-enter.
    ``openings``: mouth points where any diagonal is forbidden; also early-exit.
    ``tube_centerline`` / ``tube_half_width``: flag strands outside the conduit.
    """
    issues: list[str] = []
    overlap_ignore: list[Point] = []
    if openings:
        overlap_ignore.extend(openings)
    if shared_terminals:
        overlap_ignore.extend(t[0] for t in shared_terminals)
    if len(strands) >= 2 and strands_overlap(
        strands,
        min_separation=min_separation,
        ignore_near=overlap_ignore or None,
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
                if (
                    tube_centerline is not None
                    and tube_half_width is not None
                    and strand_exits_before_mouth(
                        poly,
                        mouth,
                        tube_centerline=tube_centerline,
                        tube_half_width=tube_half_width,
                    )
                ):
                    issues.append(
                        f"strand {i}: exits before opening {oi} "
                        "(must leave through the mouth)"
                    )
    if tube_centerline is not None and tube_half_width is not None:
        for i, poly in enumerate(strands):
            # Inbox fans sit outside the tube by design — only score the
            # mouth→mouth run when openings are known.
            check = (
                clip_poly_between_points(poly, openings)
                if openings
                else poly
            )
            if strand_outside_tube(
                check, tube_centerline, half_width=tube_half_width
            ):
                issues.append(
                    f"strand {i}: outside conduit envelope "
                    f"(>{tube_half_width:g}px from centerline)"
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
    if place_rects:
        pins: list[Point] = []
        if shared_terminals:
            pins.extend(t[0] for t in shared_terminals)
        if openings:
            pins.extend(openings)
        for ri, rect in enumerate(place_rects):
            for i, poly in enumerate(strands):
                if polyline_hugs_rect_border(
                    poly, rect, ignore_near=pins
                ):
                    issues.append(
                        f"strand {i}: hugs place rect {ri} border"
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
            if len(polys) >= 2 and not shared_terminal_both_arms_diagonal(
                polys, pin
            ):
                issues.append(
                    f"shared terminal {ti}: asymmetric V "
                    "(every cable must enter on a diagonal)"
                )
            if len(polys) >= 2 and strands_merge_before_pin(polys, pin):
                issues.append(
                    f"shared terminal {ti}: cables merge before the pin"
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


def jacket_mid_offset(lane_i0: int, lane_i1: int, strand_count: int) -> float:
    """Centerline offset for a jacket spanning lanes ``i0..i1`` inclusive."""
    a = highway_lane_offset(lane_i0, strand_count)
    b = highway_lane_offset(lane_i1, strand_count)
    return (a + b) / 2.0


def cable_lanes_are_contiguous(lane_indices: Sequence[int]) -> bool:
    """True when a cable's strand lanes form an unbroken block (for jackets)."""
    if not lane_indices:
        return True
    lo, hi = min(lane_indices), max(lane_indices)
    return set(lane_indices) == set(range(lo, hi + 1))


def parallel_highway_bundle(centerline: Poly, strand_count: int) -> list[list[Point]]:
    """Build ``strand_count`` parallel lanes of a shared orthogonal centerline."""
    return [
        offset_ortho(centerline, highway_lane_offset(i, strand_count))
        for i in range(strand_count)
    ]



def force_through_mouth(pts: Poly, mouth: Point, *, radius: float = 40.0) -> list[Point]:
    """Rewrite ``pts`` so the path passes through ``mouth`` (no early side exit).

    Parallel offset of an L at the opening peels lanes through the tube wall
    before the boca. Drop the peel neighborhood, keep offset until mouth depth,
    take a short lateral into the boca, then leave from the mouth toward the
    far side (Manhattan), stripping out-and-back residue.
    """
    if len(pts) < 2:
        return [(float(p[0]), float(p[1])) for p in pts]
    mx, my = float(mouth[0]), float(mouth[1])
    mouth_p = (mx, my)
    src = [(float(p[0]), float(p[1])) for p in pts]
    best_i = min(range(len(src)), key=lambda i: _dist(src[i], mouth_p))
    lo = best_i
    hi = best_i
    while lo > 0 and _dist(src[lo - 1], mouth_p) <= radius:
        lo -= 1
    while hi < len(src) - 1 and _dist(src[hi + 1], mouth_p) <= radius:
        hi += 1
    before = src[:lo]
    after = src[hi + 1 :]

    def converge_end(side: list[Point]) -> list[Point]:
        if not side:
            return [mouth_p]
        out = list(side)
        while len(out) > 1 and _dist(out[-1], mouth_p) <= radius:
            out.pop()
        last = out[-1]
        if _dist(last, mouth_p) < 1e-6:
            return out
        if abs(last[0] - mx) < 1e-6 or abs(last[1] - my) < 1e-6:
            out.append(mouth_p)
            return out
        if abs(last[1] - my) >= abs(last[0] - mx):
            out.append((last[0], my))
            out.append(mouth_p)
        else:
            out.append((mx, last[1]))
            out.append(mouth_p)
        return out

    left = converge_end(before)
    # Leave from the mouth toward far after-points (skip peel-depth stubs).
    far_after = [p for p in after if _dist(p, mouth_p) > radius]
    if not far_after and after:
        far_after = [after[-1]]
    right: list[Point] = []
    if far_after:
        right = manhattan_join_end([mouth_p], far_after[0])
        for p in far_after[1:]:
            right = manhattan_join_end(right, p)
    if right and _dist(right[0], mouth_p) < 1e-6:
        right = right[1:]
    merged = left + right
    clean: list[Point] = []
    for p in merged:
        if clean and _dist(clean[-1], p) < 1e-6:
            continue
        clean.append(p)
    guard = 0
    while guard < 32 and len(clean) >= 3:
        guard += 1
        changed = False
        for i in range(2, len(clean)):
            # Never collapse a reverse that pivots on the mouth — that is the
            # intentional converge-then-leave (lane offset → boca → exit).
            if _dist(clean[i - 1], mouth_p) < 1.5:
                continue
            ax = clean[i - 1][0] - clean[i - 2][0]
            ay = clean[i - 1][1] - clean[i - 2][1]
            bx = clean[i][0] - clean[i - 1][0]
            by = clean[i][1] - clean[i - 1][1]
            if abs(ax * by - ay * bx) > 1e-6:
                continue
            if ax * bx + ay * by >= -1e-6:
                continue
            len_a = (ax * ax + ay * ay) ** 0.5
            len_b = (bx * bx + by * by) ** 0.5
            if len_b < len_a - 1e-6:
                ux, uy = ax / len_a, ay / len_a
                clean[i - 1] = (
                    clean[i - 2][0] + ux * (len_a - len_b),
                    clean[i - 2][1] + uy * (len_a - len_b),
                )
                clean.pop(i)
            elif len_a < len_b - 1e-6:
                ux, uy = bx / len_b, by / len_b
                keep = len_b - len_a
                clean[i] = (
                    clean[i - 2][0] + ux * keep,
                    clean[i - 2][1] + uy * keep,
                )
                clean.pop(i - 1)
            else:
                del clean[i - 2 : i]
            changed = True
            break
        if not changed:
            break
    return clean


def _point_centerline_dist(p: Point, centerline: Poly) -> float:
    """Min distance from ``p`` to any segment of ``centerline``."""
    if len(centerline) < 2:
        return _dist(p, centerline[0]) if centerline else 0.0

    def point_seg_dist(pt: Point, a: Point, b: Point) -> float:
        abx, aby = b[0] - a[0], b[1] - a[1]
        lab2 = abx * abx + aby * aby
        if lab2 < 1e-12:
            return _dist(pt, a)
        t = max(
            0.0,
            min(1.0, ((pt[0] - a[0]) * abx + (pt[1] - a[1]) * aby) / lab2),
        )
        return _dist(pt, (a[0] + t * abx, a[1] + t * aby))

    return min(
        point_seg_dist(p, centerline[i], centerline[i + 1])
        for i in range(len(centerline) - 1)
    )


def strand_exits_before_mouth(
    pts: Poly,
    mouth: Point,
    *,
    ahead: float = 2.5,
    lateral_min: float = 3.0,
    tube_centerline: Poly | None = None,
    tube_half_width: float | None = None,
) -> bool:
    """True when a path leaves the tube wall before reaching the opening mouth.

    With ``tube_centerline`` / ``tube_half_width``: once the path has been
    inside the tube envelope, any later vertex still short of the mouth that
    sits outside means it pierced the wall (inbox fans never enter the tube
    before the boca, so they are not flagged).

    Without tube geometry (legacy tube-only polylines): flag a lateral peel on
    the approach half from path start to the mouth.
    """
    if len(pts) < 2:
        return False
    mx, my = float(mouth[0]), float(mouth[1])
    mouth_p = (mx, my)
    seq = [(float(p[0]), float(p[1])) for p in pts]
    if min(_dist(p, mouth_p) for p in seq) > ahead + 4.0:
        return True
    best_i = min(range(len(seq)), key=lambda i: _dist(seq[i], mouth_p))

    if tube_centerline is not None and tube_half_width is not None:
        limit = float(tube_half_width) + 1.25

        def left_tube_on_approach(approach: list[Point]) -> bool:
            """``approach`` ordered far → mouth. Flag in-tube then outside."""
            seen_inside = False
            for p in approach:
                if _dist(p, mouth_p) <= ahead:
                    continue
                inside = _point_centerline_dist(p, tube_centerline) <= limit
                if inside:
                    seen_inside = True
                elif seen_inside:
                    return True
            return False

        from_start = seq[: best_i + 1]
        from_end = list(reversed(seq[best_i:]))
        return left_tube_on_approach(from_start) or left_tube_on_approach(
            from_end
        )

    # Legacy: approach half from start (tube-only polylines).
    pre = seq[: min(len(seq), best_i + 1)]
    if len(pre) < 2:
        pre = seq[:2]
    xs = [p[0] for p in pre]
    ys = [p[1] for p in pre]
    vert_tube = (max(xs) - min(xs)) <= (max(ys) - min(ys) + 1e-9)
    from_neg = (sum(ys) / len(ys) < my) if vert_tube else (sum(xs) / len(xs) < mx)

    for i in range(len(pre) - 1):
        a, b = pre[i], pre[i + 1]
        horiz = abs(a[1] - b[1]) < 1e-6 and abs(a[0] - b[0]) >= lateral_min
        vert = abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) >= lateral_min
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        if vert_tube and horiz:
            depth = (my - mid[1]) if from_neg else (mid[1] - my)
            if depth > ahead:
                return True
        if (not vert_tube) and vert:
            depth = (mx - mid[0]) if from_neg else (mid[0] - mx)
            if depth > ahead:
                return True
    return False


def clip_poly_between_points(pts: Poly, anchors: Sequence[Point]) -> list[Point]:
    """Keep the sub-polyline spanning the vertices closest to ``anchors``."""
    if len(pts) < 2 or not anchors:
        return [(float(p[0]), float(p[1])) for p in pts]
    seq = [(float(p[0]), float(p[1])) for p in pts]
    idxs = [
        min(range(len(seq)), key=lambda i: _dist(seq[i], (float(a[0]), float(a[1]))))
        for a in anchors
    ]
    lo, hi = min(idxs), max(idxs)
    return seq[lo : hi + 1]


def strand_outside_tube(
    pts: Poly,
    centerline: Poly,
    *,
    half_width: float,
    slack: float = 1.25,
) -> bool:
    """True when any vertex sits farther than the tube half-width from centerline."""
    if len(pts) < 1 or len(centerline) < 2:
        return False
    limit = half_width + slack
    for p in pts:
        pt = (float(p[0]), float(p[1]))
        if _point_centerline_dist(pt, centerline) > limit:
            return True
    return False


def highway_road_width(strand_count: int) -> float:
    """Match ``highwayRoadWidth`` in app.js."""
    n = max(1, int(strand_count))
    return n * STRAND_WIDTH + (n + 1) * LANE_GAP


def converge_lane_to_mouth(
    pts: Poly, mouth: Point, *, at_start: bool = False
) -> list[Point]:
    """Local converge of an offset lane end onto ``mouth`` (keep mid-run offset)."""
    if at_start:
        return list(
            reversed(converge_lane_to_mouth(list(reversed(pts)), mouth, at_start=False))
        )
    if len(pts) < 1:
        return [(float(mouth[0]), float(mouth[1]))]
    mx, my = float(mouth[0]), float(mouth[1])
    mouth_p = (mx, my)
    out: list[Point] = [(float(p[0]), float(p[1])) for p in pts]
    while len(out) > 1 and _dist(out[-1], mouth_p) < 1.5:
        out.pop()
    last = out[-1]
    if _dist(last, mouth_p) < 1e-6:
        return out
    if abs(last[0] - mx) < 1e-6 or abs(last[1] - my) < 1e-6:
        out.append(mouth_p)
        return out
    if abs(last[1] - my) >= abs(last[0] - mx):
        out.append((last[0], my))
        out.append(mouth_p)
    else:
        out.append((mx, last[1]))
        out.append(mouth_p)
    return out


def mouth_fan_pts(
    mouth: Point,
    inward: Point,
    lane_dist: float,
    *,
    stub: float = 14.0,
) -> list[Point]:
    """mouth → inward stub → lateral+depth fan (inbox separation after boca)."""
    mx, my = float(mouth[0]), float(mouth[1])
    ix, iy = float(inward[0]), float(inward[1])
    stub_pt = (mx + ix * stub, my + iy * stub)
    lx, ly = -iy, ix
    if abs(lane_dist) < 1e-9:
        return [(mx, my), stub_pt]
    # Always deeper into the box than the stub; negative lanes get a half-pitch
    # so tip latitudes stay unique when |lane_dist| matches a positive twin.
    depth_along = abs(lane_dist) + (
        max(6.0, FAN_LATERAL_PITCH * 0.5) if lane_dist < 0 else 0.0
    )
    fan = (
        stub_pt[0] + lx * lane_dist + ix * depth_along,
        stub_pt[1] + ly * lane_dist + iy * depth_along,
    )
    return [(mx, my), stub_pt, fan]


def build_hop_lane(
    pin_start: Point,
    mouth_start: Point,
    exterior: Poly,
    mouth_end: Point,
    pin_end: Point,
    lane_dist: float,
    inward_start: Point,
    inward_end: Point,
) -> list[Point]:
    """Reference hop lane: offset tube only, converge mouths, fan inboxes.

    Does **not** offset a continuous inbox+tube centerline (that peels out of
    the conduit). Matches ``cableBaseSubpaths`` hop assembly in app.js.
    """
    tube = (
        offset_ortho(exterior, lane_dist)
        if abs(lane_dist) > 1e-9
        else [(float(p[0]), float(p[1])) for p in exterior]
    )
    tube = converge_lane_to_mouth(tube, mouth_start, at_start=True)
    tube = converge_lane_to_mouth(tube, mouth_end, at_start=False)

    fan_s = mouth_fan_pts(mouth_start, inward_start, lane_dist)
    to_mouth = list(reversed(fan_s))  # fan → stub → mouth
    head = manhattan_join_end([pin_start], to_mouth[0])
    head = head + to_mouth[1:]

    fan_e = mouth_fan_pts(mouth_end, inward_end, lane_dist)
    tail = manhattan_join_end(fan_e, pin_end)

    chain = list(head[:-1]) + list(tube) + list(tail[1:])
    clean: list[Point] = []
    for p in chain:
        if not clean or _dist(clean[-1], p) > 1e-6:
            clean.append(p)
    return clean


def ensure_vertex_near(
    pts: Poly, target: Point, *, tol: float = 1.5
) -> list[Point]:
    """If ``pts`` misses ``target``, splice a Manhattan detour through it."""
    if len(pts) < 2:
        return [(float(p[0]), float(p[1])) for p in pts]
    tx, ty = float(target[0]), float(target[1])
    src = [(float(p[0]), float(p[1])) for p in pts]
    if min(_dist(p, (tx, ty)) for p in src) <= tol:
        return src
    seg_best = 0
    seg_dist = float("inf")
    for i in range(len(src) - 1):
        a, b = src[i], src[i + 1]
        abx, aby = b[0] - a[0], b[1] - a[1]
        lab2 = abx * abx + aby * aby
        t = 0.0
        if lab2 > 1e-12:
            t = max(
                0.0,
                min(1.0, ((tx - a[0]) * abx + (ty - a[1]) * aby) / lab2),
            )
        px, py = a[0] + t * abx, a[1] + t * aby
        d = _dist((px, py), (tx, ty))
        if d < seg_dist:
            seg_dist = d
            seg_best = i
    a, b = src[seg_best], src[seg_best + 1]
    mid: list[Point] = [(tx, ty)]
    if abs(a[0] - tx) > 1e-6 and abs(a[1] - ty) > 1e-6:
        mid.insert(0, (tx, a[1]))
    if abs(b[0] - tx) > 1e-6 and abs(b[1] - ty) > 1e-6:
        mid.append((tx, b[1]))
    return src[: seg_best + 1] + mid + src[seg_best + 1 :]


def mouth_fan_join_anti_pattern(
    mouth: Point,
    inward: Point,
    lane_dists: Sequence[float],
    pin: Point,
    face: str,
) -> list[list[Point]]:
    """Bug: merge every lead onto the shared stub (collapses inbox lanes)."""
    out: list[list[Point]] = []
    for i, dist in enumerate(lane_dists):
        fan = mouth_fan_pts(mouth, inward, float(dist))
        # Wrong: join to stub (fan[1]) / whole fan path like mergeLeadToSpine
        # exploring stub as a candidate — use stub as spine tip.
        stub = fan[1] if len(fan) > 1 else fan[0]
        lead = terminal_v_lead(pin, face, stub, i, len(lane_dists))
        out.append(manhattan_join_end(lead, stub, face=face) + [mouth])
    return out


def mouth_fan_join_correct(
    mouth: Point,
    inward: Point,
    lane_dists: Sequence[float],
    pin: Point,
    face: str,
) -> list[list[Point]]:
    """Join each lead to its fan tip, then stub → mouth (keeps separation)."""
    out: list[list[Point]] = []
    for i, dist in enumerate(lane_dists):
        fan = mouth_fan_pts(mouth, inward, float(dist))
        tip = fan[-1]
        lead = terminal_v_lead(pin, face, tip, i, len(lane_dists))
        # tip → stub → mouth (fan reversed without duplicating tip)
        to_mouth = list(reversed(fan[:-1])) if len(fan) > 1 else [mouth]
        chain = manhattan_join_end(lead, tip, face=face)
        for p in to_mouth:
            if _dist(chain[-1], p) > 1e-6:
                chain.append(p)
        out.append(chain)
    return out


def join_lead_to_fan_tip(
    lead: Poly, fan_tip: Point, face: str = "N"
) -> list[Point]:
    """Mirror of ``joinLeadToFanTip``: face column/row first, no rail-Y crawl."""
    if not lead:
        return [(float(fan_tip[0]), float(fan_tip[1]))]
    out: list[Point] = [(float(p[0]), float(p[1])) for p in lead]
    fx, fy = float(fan_tip[0]), float(fan_tip[1])
    rail = out[-1]
    if _dist(rail, (fx, fy)) < 1e-6:
        return out
    fo = _face_axes(face)[0]
    ns = abs(fo[1]) >= abs(fo[0])
    if ns:
        if abs(rail[1] - fy) > 1e-6:
            out.append((rail[0], fy))
        if abs(out[-1][0] - fx) > 1e-6 or abs(out[-1][1] - fy) > 1e-6:
            out.append((fx, fy))
    else:
        if abs(rail[0] - fx) > 1e-6:
            out.append((fx, rail[1]))
        if abs(out[-1][0] - fx) > 1e-6 or abs(out[-1][1] - fy) > 1e-6:
            out.append((fx, fy))
    return out


def shared_rail_y_join_anti_pattern(
    leads: Sequence[Poly], fan_tips: Sequence[Point]
) -> list[list[Point]]:
    """Bug: from each rail, go horizontal at rail-Y to stub-x then to fan tip.

    That puts every strand on the same horizontal (Test_01 y=420 trunk).
    """
    out: list[list[Point]] = []
    for lead, tip in zip(leads, fan_tips):
        rail = (float(lead[-1][0]), float(lead[-1][1]))
        fx, fy = float(tip[0]), float(tip[1])
        # Shared horizontal at rail Y toward fan tip x, then vertical.
        chain = [(float(p[0]), float(p[1])) for p in lead]
        if abs(rail[0] - fx) > 1e-6:
            chain.append((fx, rail[1]))
        if abs(rail[1] - fy) > 1e-6:
            chain.append((fx, fy))
        out.append(chain)
    return out


def hop_lanes_through_mouths(
    centerline: Poly,
    mouths: Sequence[Point],
    strand_count: int,
) -> list[list[Point]]:
    """Legacy helper: offset whole centerline then forceThroughMouth (anti-pattern).

    Kept so tests can prove this pattern puts lanes outside the tube.
    Prefer ``build_hop_lane`` for correct geometry.
    """
    lanes = parallel_highway_bundle(centerline, strand_count)
    out: list[list[Point]] = []
    for lane in lanes:
        fixed = [(p[0], p[1]) for p in lane]
        for mouth in mouths:
            fixed = force_through_mouth(fixed, mouth)
        out.append(fixed)
    return out


def compose_hop_centerline(
    start_tail: Poly,
    exterior: Poly,
    end_tail: Poly | None = None,
) -> list[Point]:
    """Build inbox→exterior→inbox centerline (pins dropped).

    ``start_tail`` / ``end_tail`` are pin→mouth polylines (as from hop tails).
    Mirrors the continuous-centerline compose in ``cableBaseSubpaths`` (app.js).
    """
    center: list[Point] = []
    if len(start_tail) >= 2:
        center.extend((float(p[0]), float(p[1])) for p in start_tail[1:])
    if len(exterior) >= 2:
        first = (float(exterior[0][0]), float(exterior[0][1]))
        if center and _dist(center[-1], first) < 1e-6:
            center.extend((float(p[0]), float(p[1])) for p in exterior[1:])
        else:
            center.extend((float(p[0]), float(p[1])) for p in exterior)
    if end_tail is not None and len(end_tail) >= 2:
        end_rev = [
            (float(p[0]), float(p[1])) for p in reversed(list(end_tail)[1:])
        ]
        if center and end_rev and _dist(center[-1], end_rev[0]) < 1e-6:
            center.extend(end_rev[1:])
        else:
            center.extend(end_rev)
    return center


def hop_lanes_continuous(
    start_tail: Poly,
    exterior: Poly,
    end_tail: Poly | None,
    strand_count: int,
) -> list[list[Point]]:
    """Correct hop lanes: one centerline, single-sign parallel offset."""
    center = compose_hop_centerline(start_tail, exterior, end_tail)
    return parallel_highway_bundle(center, strand_count)


def hop_lanes_flipped_inbox(
    start_tail: Poly,
    exterior: Poly,
    end_tail: Poly | None,
    strand_count: int,
) -> list[list[Point]]:
    """Bug pattern: ``+laneDist`` on exterior, ``-laneDist`` on pin→mouth tails.

    That sign flip peels the bundle at elbows and makes strands overlap / cross
    at openings. Kept so tests can prove the failure mode.
    """
    lanes: list[list[Point]] = []
    for i in range(strand_count):
        d = highway_lane_offset(i, strand_count)
        start_off = offset_ortho(start_tail, -d) if len(start_tail) >= 2 else []
        ex_off = offset_ortho(exterior, d) if len(exterior) >= 2 else []
        chain: list[Point] = []
        if start_off:
            chain.extend(start_off[:-1] if ex_off else start_off)
        if ex_off:
            chain.extend(ex_off)
        if end_tail is not None and len(end_tail) >= 2:
            end_off = offset_ortho(end_tail, -d)
            # pin→mouth offset, reverse onto chain (mouth→pin).
            rev = list(reversed(end_off))
            if chain and rev and _dist(chain[-1], rev[0]) < 1e-6:
                chain.extend(rev[1:])
            else:
                chain.extend(rev)
        lanes.append(chain)
    return lanes


def attach_v_leads(
    spine: Poly,
    start_pin: Point,
    start_face: str,
    start_slot: int,
    end_pin: Point,
    end_face: str,
    end_slot: int,
    *,
    slot_count: int,
) -> list[Point]:
    """Attach multi-cable V leads at both ends of an offset spine."""
    if len(spine) < 1:
        return []
    head = terminal_v_lead(
        start_pin, start_face, spine[0], start_slot, slot_count
    )
    # Manhattan-join tip → spine[0] already inside terminal_v_lead.
    mid = list(spine)
    if head and mid and _dist(head[-1], mid[0]) < 1e-6:
        chain = list(head) + mid[1:]
    else:
        chain = list(head) + mid
    rev = list(reversed(chain))
    tail = terminal_v_lead(end_pin, end_face, rev[0], end_slot, slot_count)
    if tail and rev and _dist(tail[-1], rev[0]) < 1e-6:
        merged = list(tail) + rev[1:]
    else:
        merged = list(tail) + rev
    return list(reversed(merged))


def _seg_dist(p: Point, a: Point, b: Point) -> float:
    abx, aby = b[0] - a[0], b[1] - a[1]
    lab2 = abx * abx + aby * aby
    if lab2 < 1e-12:
        return _dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / lab2))
    return _dist(p, (a[0] + t * abx, a[1] + t * aby))


def point_near_polyline(p: Point, poly: Poly, *, tol: float = 3.0) -> bool:
    """True if ``p`` lies within ``tol`` of any vertex or segment of ``poly``."""
    if not poly:
        return False
    pts = [(float(q[0]), float(q[1])) for q in poly]
    if any(_dist(p, q) <= tol for q in pts):
        return True
    for a, b in zip(pts, pts[1:]):
        if _seg_dist(p, a, b) <= tol:
            return True
    return False


def polyline_dist_to_centerline(poly: Poly, centerline: Poly) -> float:
    """Max distance from any vertex of ``poly`` to ``centerline`` segments."""
    if not poly or len(centerline) < 2:
        return 0.0
    cl = [(float(p[0]), float(p[1])) for p in centerline]
    worst = 0.0
    for q in poly:
        d = min(
            _seg_dist((float(q[0]), float(q[1])), cl[i], cl[i + 1])
            for i in range(len(cl) - 1)
        )
        if d > worst:
            worst = d
    return worst


def match_strand_to_tube(
    strand: Poly, tubes: Sequence[Poly]
) -> tuple[int, float]:
    """Return (tube_index, mean_dist) for the tube this strand follows best."""
    if not tubes or not strand:
        return -1, float("inf")
    best_i, best_score = -1, float("inf")
    s = [(float(p[0]), float(p[1])) for p in strand]
    for ti, tube in enumerate(tubes):
        if len(tube) < 2:
            continue
        t = [(float(p[0]), float(p[1])) for p in tube]
        xs = [p[0] for p in t]
        ys = [p[1] for p in t]
        pad = 40.0
        mid = [
            p
            for p in s
            if min(xs) - pad <= p[0] <= max(xs) + pad
            and min(ys) - pad <= p[1] <= max(ys) + pad
        ]
        if len(mid) < 2:
            continue
        near = [
            p
            for p in mid
            if min(_seg_dist(p, t[i], t[i + 1]) for i in range(len(t) - 1)) < 50
        ]
        if len(near) < 2:
            continue
        score = sum(
            min(_seg_dist(p, t[i], t[i + 1]) for i in range(len(t) - 1))
            for p in near
        ) / len(near)
        if score < best_score:
            best_score = score
            best_i = ti
    return best_i, best_score


def shared_horizontal_trunk_length(
    strands: Sequence[Poly],
    *,
    y_min: float,
    y_max: float,
    min_len: float = 40.0,
) -> list[tuple[float, float, int]]:
    """Detect long horizontals at the same Y shared by ≥2 strands (inbox trunk).

    Returns list of (y, length, strand_count) for offending latitudes.
    """
    # y -> list of (x0, x1) intervals per strand
    by_y: dict[int, list[list[tuple[float, float]]]] = {}
    for strand in strands:
        pts = [(float(p[0]), float(p[1])) for p in strand]
        local: dict[int, list[tuple[float, float]]] = {}
        for a, b in zip(pts, pts[1:]):
            if abs(a[1] - b[1]) > 0.75:
                continue
            y = round(a[1])
            if y < y_min or y > y_max:
                continue
            lo, hi = sorted((a[0], b[0]))
            if hi - lo < 1.0:
                continue
            local.setdefault(y, []).append((lo, hi))
        for y, segs in local.items():
            by_y.setdefault(y, []).append(segs)

    bad: list[tuple[float, float, int]] = []
    for y, per_strand in by_y.items():
        if len(per_strand) < 2:
            continue
        # Total covered length union proxy: max pairwise overlap span.
        total = 0.0
        for segs in per_strand:
            total += sum(hi - lo for lo, hi in segs)
        # Overlap: any two strands share an x-range at this y.
        overlap = 0.0
        for i in range(len(per_strand)):
            for j in range(i + 1, len(per_strand)):
                for a0, a1 in per_strand[i]:
                    for b0, b1 in per_strand[j]:
                        lo, hi = max(a0, b0), min(a1, b1)
                        if hi - lo > overlap:
                            overlap = hi - lo
        if overlap >= min_len:
            bad.append((float(y), overlap, len(per_strand)))
    return bad


def assess_live_canvas(
    tubes: Sequence[Poly],
    strands: Sequence[Poly],
    *,
    tube_half_widths: Sequence[float] | None = None,
    mouth_tol: float = 3.0,
    envelope_margin: float = 2.5,
    trunk_y_min: float = 400.0,
    trunk_y_max: float = 440.0,
    bipolar_y_min: float = 430.0,
) -> list[str]:
    """Invariants for a live Test_01-style canvas (tubes + colored strands).

    Used by the Playwright E2E so failures match what the UI actually paints.
    """
    issues: list[str] = []
    if not tubes:
        issues.append("no edge-tube paths on canvas")
    if len(strands) < 1:
        issues.append("no cable strands on canvas")
        return issues

    halves = list(tube_half_widths or [])
    while len(halves) < len(tubes):
        # Match app.js highwayRoadWidth defaults (3-lane ~17.5 → 8.75).
        halves.append(8.75)

    for si, strand in enumerate(strands):
        pts = [(float(p[0]), float(p[1])) for p in strand]
        if len(pts) < 2:
            issues.append(f"strand {si}: too short")
            continue
        ti, _ = match_strand_to_tube(pts, tubes)
        if ti < 0:
            issues.append(f"strand {si}: no matching tube")
            continue
        tube = [(float(p[0]), float(p[1])) for p in tubes[ti]]
        mouth_a, mouth_b = tube[0], tube[-1]
        if not point_near_polyline(mouth_a, pts, tol=mouth_tol):
            issues.append(f"strand {si}: misses tube[{ti}] start mouth")
        if not point_near_polyline(mouth_b, pts, tol=mouth_tol):
            issues.append(f"strand {si}: misses tube[{ti}] end mouth")

        # Envelope: only vertices BETWEEN the two mouth visits on this strand
        # (inbox fans before/after bocas must not inflate max_d).
        def nearest_idx(mouth: Point) -> int:
            best_i, best_d = 0, float("inf")
            for i, p in enumerate(pts):
                d = _dist(p, mouth)
                # Also consider segment distance to catch mouth mid-edge.
                if i + 1 < len(pts):
                    d = min(d, _seg_dist(mouth, p, pts[i + 1]))
                if d < best_d:
                    best_d = d
                    best_i = i
            return best_i

        i0 = nearest_idx(mouth_a)
        i1 = nearest_idx(mouth_b)
        if i1 < i0:
            i0, i1 = i1, i0
        corridor = pts[i0 + 1 : i1]
        if corridor:
            max_d = max(
                min(_seg_dist(p, tube[i], tube[i + 1]) for i in range(len(tube) - 1))
                for p in corridor
            )
            limit = halves[ti] + envelope_margin
            if max_d > limit:
                issues.append(
                    f"strand {si}: outside tube[{ti}] envelope "
                    f"(max_d={max_d:.1f} > {limit:.1f})"
                )

        n_back = count_out_and_back(pts)
        if n_back:
            issues.append(f"strand {si}: out-and-back ({n_back})")

        # Bipolar-ish: path ends near Regleta band → expect a terminal diagonal.
        end_hi = pts[0][1] > bipolar_y_min or pts[-1][1] > bipolar_y_min
        if end_hi:
            d0 = abs(pts[0][0] - pts[1][0]) > 0.5 and abs(pts[0][1] - pts[1][1]) > 0.5
            d1 = (
                abs(pts[-1][0] - pts[-2][0]) > 0.5
                and abs(pts[-1][1] - pts[-2][1]) > 0.5
            )
            if not (d0 or d1):
                issues.append(f"strand {si}: missing terminal V diagonal")

    trunks = shared_horizontal_trunk_length(
        strands, y_min=trunk_y_min, y_max=trunk_y_max, min_len=40.0
    )
    for y, length, n in trunks:
        issues.append(
            f"shared inbox trunk at y≈{y:.0f} overlap={length:.0f}px "
            f"across {n} strands"
        )
    return issues


def assess_live_site(
    tubes: Sequence[Poly],
    strands: Sequence[Poly],
    *,
    tube_half_widths: Sequence[float] | None = None,
    require_tubes: bool = False,
    mouth_tol: float = 3.0,
    envelope_margin: float = 2.5,
    trunk_y_min: float = 400.0,
    trunk_y_max: float = 440.0,
    bipolar_y_min: float = 430.0,
) -> list[str]:
    """Live-canvas checks; sites without conduits skip tube mouth/envelope.

    Same-box routes (no ``edge-tube``) still fail on empty canvas or
    out-and-back. Pass ``require_tubes=True`` when the fixture must draw tubes.
    """
    if not tubes:
        issues: list[str] = []
        if require_tubes:
            issues.append("no edge-tube paths on canvas")
        if len(strands) < 1:
            issues.append("no cable strands on canvas")
            return issues
        for si, strand in enumerate(strands):
            pts = [(float(p[0]), float(p[1])) for p in strand]
            n_back = count_out_and_back(pts)
            if n_back:
                issues.append(f"strand {si}: out-and-back ({n_back})")
        return issues
    return assess_live_canvas(
        tubes,
        strands,
        tube_half_widths=tube_half_widths,
        mouth_tol=mouth_tol,
        envelope_margin=envelope_margin,
        trunk_y_min=trunk_y_min,
        trunk_y_max=trunk_y_max,
        bipolar_y_min=bipolar_y_min,
    )
