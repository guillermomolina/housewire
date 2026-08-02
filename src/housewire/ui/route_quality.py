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


def _dist(a: Point, b: Point) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


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


def assess_bundle(
    strands: Sequence[Poly],
    *,
    min_separation: float = MIN_LANE_SEPARATION,
    allow_z: bool = False,
    allow_c: bool = False,
) -> list[str]:
    """Return human-readable problems for a parallel strand bundle.

    ``allow_z`` / ``allow_c``: set True only when several strands share one
    terminal and an intentional fan is expected.
    """
    issues: list[str] = []
    if len(strands) >= 2 and strands_overlap(
        strands, min_separation=min_separation
    ):
        issues.append("strands overlap (lane separation too small)")
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
