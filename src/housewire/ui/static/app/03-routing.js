  /* === 03-routing.js: Ortho routing, lanes, cable layout, tube/cable paint helpers ===
   * Fragment of the UI IIFE (bundled into ../app.js).
   * Edit this file, then run: python scripts/bundle_ui_app.py
   */
  function orthoRoute(p1, p2, fromFace, toFace, occupied, obstacles, stayBounds, hugRects, halfWidth) {
    const x1 = p1.x;
    const y1 = p1.y;
    const x2 = p2.x;
    const y2 = p2.y;
    if (x1 === x2 && y1 === y2) {
      return [[x1, y1]];
    }

    const STUB = 20;
    // Tighter C rails inside a place; wide exterior detours for conduits.
    const DETOUR = stayBounds ? 28 : 48;
    const half = halfWidth != null ? Number(halfWidth) : 0;
    let maxOccHalf = 0;
    for (const o of occupied || []) {
      maxOccHalf = Math.max(maxOccHalf, Number(o.half) || 0);
    }
    let maxObsClear = 0;
    for (const r of obstacles || []) {
      maxObsClear = Math.max(maxObsClear, Number(r.h) || 0, Number(r.w) || 0);
    }
    // Parallel rails must clear painted tube strokes and foreign boxes.
    const LANE = Math.max(
      LANE_PITCH,
      half + maxOccHalf + LANE_GAP,
      maxObsClear > 0 ? Math.min(40, maxObsClear / 4 + LANE_GAP) : 0
    );
    const OVERLAP_EPS = Math.max(LANE_GAP, half + LANE_GAP);
    const pts = [[x1, y1]];
    let ax = x1;
    let ay = y1;
    let bx = x2;
    let by = y2;

    // Opposing face stubs that would cross in a tight gap (Route_14 Tube2):
    // skip stubs and route mouth-to-mouth instead of an out-and-back C.
    let stubFrom = fromFace;
    let stubTo = toFace;
    if (
      (fromFace === "E" && toFace === "W" && x1 < x2 && x1 + STUB > x2 - STUB) ||
      (fromFace === "W" && toFace === "E" && x1 > x2 && x1 - STUB < x2 + STUB) ||
      (fromFace === "S" && toFace === "N" && y1 < y2 && y1 + STUB > y2 - STUB) ||
      (fromFace === "N" && toFace === "S" && y1 > y2 && y1 - STUB < y2 + STUB)
    ) {
      stubFrom = null;
      stubTo = null;
    }

    if (stubFrom === "E") {
      ax = x1 + STUB;
      pts.push([ax, ay]);
    } else if (stubFrom === "W") {
      ax = x1 - STUB;
      pts.push([ax, ay]);
    } else if (stubFrom === "S") {
      ay = y1 + STUB;
      pts.push([ax, ay]);
    } else if (stubFrom === "N") {
      ay = y1 - STUB;
      pts.push([ax, ay]);
    }
    if (stubTo === "E") bx = x2 + STUB;
    else if (stubTo === "W") bx = x2 - STUB;
    else if (stubTo === "S") by = y2 + STUB;
    else if (stubTo === "N") by = y2 - STUB;

    const mid = minBendOrtho(
      ax,
      ay,
      bx,
      by,
      stubFrom,
      stubTo,
      DETOUR,
      STUB,
      LANE,
      occupied,
      OVERLAP_EPS,
      obstacles,
      [x1, y1],
      [x2, y2],
      stayBounds,
      hugRects,
      half
    );
    for (const p of mid) {
      pts.push(p);
    }
    if (bx !== x2 || by !== y2) {
      pts.push([x2, y2]);
    }
    return cleanOrthoPoly(pts);
  }

  function orthoPathD(p1, p2, fromFace, toFace, occupied, obstacles, stayBounds, hugRects, halfWidth) {
    return pointsToPathD(
      orthoRoute(
        p1,
        p2,
        fromFace,
        toFace,
        occupied,
        obstacles,
        stayBounds,
        hugRects,
        halfWidth
      )
    );
  }

  /** First step from the exit stub must not reverse back into the box. */
  function leavesOutward(fromFace, ax, ay, x, y) {
    const dx = x - ax;
    const dy = y - ay;
    if (Math.abs(dx) < 1e-6 && Math.abs(dy) < 1e-6) return true;
    if (fromFace === "N") return dy <= 1e-6; // north or horizontal
    if (fromFace === "S") return dy >= -1e-6;
    if (fromFace === "E") return dx >= -1e-6;
    if (fromFace === "W") return dx <= 1e-6;
    return true;
  }

  function polyBends(pts) {
    let bends = 0;
    for (let i = 2; i < pts.length; i++) {
      const ax = pts[i - 1][0] - pts[i - 2][0];
      const ay = pts[i - 1][1] - pts[i - 2][1];
      const bx = pts[i][0] - pts[i - 1][0];
      const by = pts[i][1] - pts[i - 1][1];
      if (Math.abs(ax) < 1e-6 && Math.abs(ay) < 1e-6) continue;
      if (Math.abs(bx) < 1e-6 && Math.abs(by) < 1e-6) continue;
      const turn = ax * by - ay * bx;
      if (Math.abs(turn) > 1e-6) bends += 1;
    }
    return bends;
  }

  /** Reject corridors that reverse 180° on the same axis (overlapping stub). */
  function hasUTurn(pts) {
    for (let i = 2; i < pts.length; i++) {
      const ax = pts[i - 1][0] - pts[i - 2][0];
      const ay = pts[i - 1][1] - pts[i - 2][1];
      const bx = pts[i][0] - pts[i - 1][0];
      const by = pts[i][1] - pts[i - 1][1];
      if (Math.abs(ax) < 1e-6 && Math.abs(ay) < 1e-6) continue;
      if (Math.abs(bx) < 1e-6 && Math.abs(by) < 1e-6) continue;
      const turn = ax * by - ay * bx;
      const dot = ax * bx + ay * by;
      if (Math.abs(turn) < 1e-6 && dot < -1e-6) return true;
    }
    return false;
  }

  function polyLength(pts) {
    let len = 0;
    for (let i = 1; i < pts.length; i++) {
      len += Math.abs(pts[i][0] - pts[i - 1][0]) + Math.abs(pts[i][1] - pts[i - 1][1]);
    }
    return len;
  }

  /** True if every consecutive segment is axis-aligned (Manhattan). */
  function isOrthoPoly(pts) {
    for (let i = 1; i < pts.length; i++) {
      const dx = pts[i][0] - pts[i - 1][0];
      const dy = pts[i][1] - pts[i - 1][1];
      if (Math.abs(dx) > 1e-6 && Math.abs(dy) > 1e-6) return false;
    }
    return true;
  }

  /** Drop duplicate points and merge colinear runs. */
  function cleanOrthoPoly(pts) {
    const out = [pts[0]];
    for (let i = 1; i < pts.length; i++) {
      const p = pts[i];
      const q = out[out.length - 1];
      if (Math.abs(p[0] - q[0]) < 1e-6 && Math.abs(p[1] - q[1]) < 1e-6) {
        continue;
      }
      out.push(p);
    }
    let i = 1;
    while (i < out.length - 1) {
      const a = out[i - 1];
      const b = out[i];
      const c = out[i + 1];
      const abx = b[0] - a[0];
      const aby = b[1] - a[1];
      const bcx = c[0] - b[0];
      const bcy = c[1] - b[1];
      const cross = abx * bcy - aby * bcx;
      const sameDir =
        abx * bcx + aby * bcy > 0 ||
        (Math.abs(abx) < 1e-6 && Math.abs(aby) < 1e-6) ||
        (Math.abs(bcx) < 1e-6 && Math.abs(bcy) < 1e-6);
      if (Math.abs(cross) < 1e-6 && sameDir) {
        out.splice(i, 1);
        continue;
      }
      i += 1;
    }
    return out;
  }

  /**
   * Cancel out-and-back runs on the same axis (ida y vuelta) so a reversed
   * exterior + tail does not paint the same segment twice.
   */
  function stripOutAndBack(pts, protectPts) {
    if (!pts || pts.length < 3) {
      return pts ? pts.map((p) => [p[0], p[1]]) : [];
    }
    const protect = (protectPts || [])
      .map((q) =>
        Array.isArray(q) ? { x: q[0], y: q[1] } : { x: q.x, y: q.y }
      )
      .filter((q) => q && Number.isFinite(q.x));
    const isProtected = (p) =>
      protect.some((q) => Math.hypot(p[0] - q.x, p[1] - q.y) < 1.5);
    /** @type {number[][]} */
    let out = pts.map((p) => [p[0], p[1]]);
    let guard = 0;
    while (guard++ < 64) {
      out = cleanOrthoPoly(out);
      let changed = false;
      for (let i = 2; i < out.length; i++) {
        // Keep converge→leave pivots on opening mouths.
        if (isProtected(out[i - 1])) continue;
        const ax = out[i - 1][0] - out[i - 2][0];
        const ay = out[i - 1][1] - out[i - 2][1];
        const bx = out[i][0] - out[i - 1][0];
        const by = out[i][1] - out[i - 1][1];
        if (Math.abs(ax) < 1e-6 && Math.abs(ay) < 1e-6) continue;
        if (Math.abs(bx) < 1e-6 && Math.abs(by) < 1e-6) continue;
        const turn = ax * by - ay * bx;
        const dot = ax * bx + ay * by;
        if (Math.abs(turn) > 1e-6 || dot >= -1e-6) continue;
        const lenA = Math.hypot(ax, ay);
        const lenB = Math.hypot(bx, by);
        if (lenB < lenA - 1e-6) {
          const ux = ax / lenA;
          const uy = ay / lenA;
          out[i - 1][0] = out[i - 2][0] + ux * (lenA - lenB);
          out[i - 1][1] = out[i - 2][1] + uy * (lenA - lenB);
          out.splice(i, 1);
        } else if (lenA < lenB - 1e-6) {
          const ux = bx / lenB;
          const uy = by / lenB;
          const keep = lenB - lenA;
          out[i][0] = out[i - 2][0] + ux * keep;
          out[i][1] = out[i - 2][1] + uy * keep;
          out.splice(i - 1, 1);
        } else {
          out.splice(i - 2, 2);
        }
        changed = true;
        break;
      }
      if (!changed) break;
    }
    return cleanOrthoPoly(out);
  }

  /**
   * Ensure exterior pieces run start-opening → end-opening (not reversed).
   */
  /**
   * Force a lane path through an opening mouth so offset L-corners do not
   * pierce the tube wall before the boca (Foto 1 early exit).
   */
  /**
   * Local converge of an offset lane onto a mouth. Keeps mid-tube parallel
   * offset intact — only rewrites the last few vertices at the boca.
   */
  function convergeLaneToMouth(pts, mouth, atStart) {
    if (!pts || pts.length < 1 || mouth == null) {
      return pts ? pts.map((p) => [p[0], p[1]]) : [];
    }
    if (atStart) {
      return convergeLaneToMouth(pts.slice().reverse(), mouth, false).reverse();
    }
    const mx = Array.isArray(mouth) ? mouth[0] : mouth.x;
    const my = Array.isArray(mouth) ? mouth[1] : mouth.y;
    /** @type {number[][]} */
    const out = pts.map((p) => [p[0], p[1]]);
    // Only drop vertices that already sit on the mouth. A looser pop (e.g. 8)
    // removed the offset lane's arrival at mouth latitude (~laneDist away) and
    // rebuilt from mid-tube — later fan merges then skipped the boca.
    while (
      out.length > 1 &&
      Math.hypot(out[out.length - 1][0] - mx, out[out.length - 1][1] - my) < 1.5
    ) {
      out.pop();
    }
    const last = out[out.length - 1];
    if (Math.hypot(last[0] - mx, last[1] - my) < 1e-6) return cleanOrthoPoly(out);
    if (Math.abs(last[0] - mx) < 1e-6 || Math.abs(last[1] - my) < 1e-6) {
      out.push([mx, my]);
      return cleanOrthoPoly(out);
    }
    if (Math.abs(last[1] - my) >= Math.abs(last[0] - mx)) {
      out.push([last[0], my]);
      out.push([mx, my]);
    } else {
      out.push([mx, last[1]]);
      out.push([mx, my]);
    }
    return cleanOrthoPoly(out);
  }

  /**
   * If ``pts`` never comes within ``tol`` of ``target``, splice a Manhattan
   * detour through ``target`` on the closest segment (keeps hop bocas).
   */
  function ensureVertexNear(pts, target, tol = 1.5) {
    if (!pts || pts.length < 2 || target == null) {
      return pts ? pts.map((p) => [p[0], p[1]]) : [];
    }
    const tx = Array.isArray(target) ? target[0] : target.x;
    const ty = Array.isArray(target) ? target[1] : target.y;
    /** @type {number[][]} */
    const src = pts.map((p) => [p[0], p[1]]);
    let bestD = Infinity;
    for (let i = 0; i < src.length; i++) {
      const d = Math.hypot(src[i][0] - tx, src[i][1] - ty);
      if (d < bestD) bestD = d;
    }
    if (bestD <= tol) return src;
    let segBest = 0;
    let segDist = Infinity;
    for (let i = 0; i < src.length - 1; i++) {
      const a = src[i];
      const b = src[i + 1];
      const abx = b[0] - a[0];
      const aby = b[1] - a[1];
      const lab2 = abx * abx + aby * aby;
      let t = 0;
      if (lab2 > 1e-12) {
        t = Math.max(
          0,
          Math.min(1, ((tx - a[0]) * abx + (ty - a[1]) * aby) / lab2)
        );
      }
      const px = a[0] + t * abx;
      const py = a[1] + t * aby;
      const d = Math.hypot(px - tx, py - ty);
      if (d < segDist) {
        segDist = d;
        segBest = i;
      }
    }
    const a = src[segBest];
    const b = src[segBest + 1];
    /** @type {number[][]} */
    const mid = [[tx, ty]];
    if (Math.abs(a[0] - tx) > 1e-6 && Math.abs(a[1] - ty) > 1e-6) {
      mid.unshift([tx, a[1]]);
    }
    if (Math.abs(b[0] - tx) > 1e-6 && Math.abs(b[1] - ty) > 1e-6) {
      mid.push([tx, b[1]]);
    }
    return cleanOrthoPoly([
      ...src.slice(0, segBest + 1),
      ...mid,
      ...src.slice(segBest + 1),
    ]);
  }

  /**
   * Replace the path between two mouths with the canonical offset tube
   * (already converged onto both bocas). Keeps inbox heads/tails intact.
   */
  function spliceTubeSegment(pts, tube, startOp, endOp) {
    if (!pts || pts.length < 2 || !tube || tube.length < 2) {
      return pts ? pts.map((p) => [p[0], p[1]]) : [];
    }
    const sx = Array.isArray(startOp) ? startOp[0] : startOp.x;
    const sy = Array.isArray(startOp) ? startOp[1] : startOp.y;
    const ex = Array.isArray(endOp) ? endOp[0] : endOp.x;
    const ey = Array.isArray(endOp) ? endOp[1] : endOp.y;
    /** @type {number[][]} */
    const src = pts.map((p) => [p[0], p[1]]);
    // First visit to start mouth, then first visit to end mouth after that.
    let i0 = -1;
    let d0 = Infinity;
    for (let i = 0; i < src.length; i++) {
      const ds = Math.hypot(src[i][0] - sx, src[i][1] - sy);
      if (ds < d0) {
        d0 = ds;
        i0 = i;
      }
    }
    let i1 = -1;
    let d1 = Infinity;
    const from = Math.max(0, i0);
    for (let i = from; i < src.length; i++) {
      const de = Math.hypot(src[i][0] - ex, src[i][1] - ey);
      if (de < d1) {
        d1 = de;
        i1 = i;
      }
    }
    if (i0 < 0 || i1 < 0 || i1 <= i0) {
      return src;
    }
    if (d0 > 24 || d1 > 24) {
      return src;
    }
    const head = src.slice(0, i0 + 1);
    const tail = src.slice(i1);
    let mid = tube.map((p) => [p[0], p[1]]);
    const headEnd = head[head.length - 1];
    const alignFwd =
      Math.hypot(mid[0][0] - headEnd[0], mid[0][1] - headEnd[1]) <=
      Math.hypot(
        mid[mid.length - 1][0] - headEnd[0],
        mid[mid.length - 1][1] - headEnd[1]
      ) +
        1e-6;
    if (!alignFwd) mid = mid.slice().reverse();
    return (
      mergeOrthoPolys(mergeOrthoPolys(head, mid), tail) ||
      cleanOrthoPoly([...head, ...mid, ...tail])
    );
  }

  /**
   * mouth → inward stub → optional lateral+depth fan.
   *
   * Rule 13 (multi-cable openings): pass the lane's mouth *crossing* (already
   * offset) with ``laneDist = 0`` so the fan stubs inward without collapsing
   * onto the center boca. Rule 6 still applies: separate in free space, never
   * by peeling through the tube wall.
   *
   * When ``laneDist ≠ 0`` and ``mouth`` is the center boca (legacy / single
   * call sites), keep the post-mouth lateral fan for inbox tip uniqueness.
   *
   * ``toward`` (optional): pin / attach inside the place. If the nominal
   * opening inward points away from it (common for plane bocas B/F), flip
   * so the fan never goes back into the tube corridor.
   *
   * ``depthBias`` (optional): when ``laneDist≈0`` (crossing already offset),
   * still push a unique tip depth so multi-lane inboxes do not share one
   * stub-Y horizontal (Route_29).
   */
  function mouthFanPts(mouth, face, laneDist, toward, depthBias) {
    const mx = Array.isArray(mouth) ? mouth[0] : mouth.x;
    const my = Array.isArray(mouth) ? mouth[1] : mouth.y;
    let oi = openingInwardDelta(face);
    if (toward != null) {
      const tx = Array.isArray(toward) ? toward[0] : toward.x;
      const ty = Array.isArray(toward) ? toward[1] : toward.y;
      const dx = tx - mx;
      const dy = ty - my;
      if (oi.x * dx + oi.y * dy < -1e-6) {
        oi = { x: -oi.x, y: -oi.y };
      } else if (Math.abs(oi.x) < 1e-9 && Math.abs(oi.y) < 1e-9) {
        // Unknown face: use dominant axis toward the pin.
        if (Math.abs(dx) >= Math.abs(dy)) {
          oi = { x: dx >= 0 ? 1 : -1, y: 0 };
        } else {
          oi = { x: 0, y: dy >= 0 ? 1 : -1 };
        }
      }
    }
    const latDist = Number(laneDist) || 0;
    const bias = Number(depthBias) || 0;
    const latX = -oi.y;
    const latY = oi.x;
    // Multi-lane unique tip: put the stub itself at a lane-unique depth so
    // joinLeadToFanTip H runs sit on distinct latitudes without a tip→stub→mouth
    // Z that stripShortZJogs would collapse (Route_29).
    if (Math.abs(latDist) < 1e-9 && Math.abs(bias) > 1e-9) {
      const stubDepth = INBOX_STUB + Math.max(LANE_PITCH, bias);
      const deep = stubPoint({ x: mx, y: my }, oi.x, oi.y, stubDepth);
      return [
        [mx, my],
        [deep.x, deep.y],
      ];
    }
    const stub = stubPoint({ x: mx, y: my }, oi.x, oi.y, INBOX_STUB);
    /** @type {number[][]} */
    const pts = [
      [mx, my],
      [stub.x, stub.y],
    ];
    if (Math.abs(latDist) < 1e-9) return pts;
    // Always deeper into the box than the stub (never back toward the boca).
    // Negative lanes get an extra half-pitch so tip latitudes stay unique.
    const depthAlong =
      Math.abs(latDist) +
      (latDist < 0 ? Math.max(6, (STRAND_WIDTH + LANE_GAP) * 0.5) : 0);
    pts.push([
      stub.x + latX * latDist + oi.x * depthAlong,
      stub.y + latY * latDist + oi.y * depthAlong,
    ]);
    return pts;
  }

  /** @deprecated destructive full-path rewrite — do not use on hop lanes. */
  function forceThroughMouth(pts, mouth, radius = 40) {
    // Kept only so older experiments remain callable; hop routing uses
    // convergeLaneToMouth on the tube segment instead.
    return convergeLaneToMouth(
      convergeLaneToMouth(pts, mouth, false),
      mouth,
      true
    );
  }

  function orientExteriorSubs(subs, startOp, endOp) {
    if (!subs || !subs.length || !startOp || !endOp) return subs || [];
    const first = subs[0][0];
    const lastSub = subs[subs.length - 1];
    const last = lastSub[lastSub.length - 1];
    const dStartFirst = Math.hypot(first[0] - startOp.x, first[1] - startOp.y);
    const dStartLast = Math.hypot(last[0] - startOp.x, last[1] - startOp.y);
    if (dStartLast + 1 < dStartFirst) {
      return subs
        .map((s) => s.slice().reverse())
        .reverse();
    }
    return subs;
  }

  /**
   * Manhattan connectors from exit stub to entry stub with the fewest bends.
   * Returns intermediate points including the entry stub (bx, by).
   * When ``occupied`` is set, also minimize conflict with prior routes.
   * ``obstacles`` (place rects) push the choice toward outer rails / side C.
   */
  function minBendOrtho(
    ax,
    ay,
    bx,
    by,
    fromFace,
    toFace,
    detour,
    stub,
    lane,
    occupied,
    overlapEps,
    obstacles,
    prePoint,
    postPoint,
    stayBounds,
    hugRects,
    halfWidth
  ) {
    const start = [ax, ay];
    const end = [bx, by];
    const needLanes =
      lane &&
      ((occupied && occupied.length) || (obstacles && obstacles.length));
    const eps = overlapEps ?? 6;
    const half = halfWidth != null ? Number(halfWidth) : 0;
    const occupiedEmpty = !occupied || !occupied.length;
    /** @type {string|null} */
    let memoKey = null;
    if (occupiedEmpty && routeOrthoMemo) {
      const sb = stayBounds
        ? `${stayBounds.x | 0},${stayBounds.y | 0},${stayBounds.w | 0},${stayBounds.h | 0}`
        : "";
      const pre = prePoint ? `${prePoint[0] | 0},${prePoint[1] | 0}` : "";
      const post = postPoint ? `${postPoint[0] | 0},${postPoint[1] | 0}` : "";
      memoKey =
        `${ax | 0},${ay | 0},${bx | 0},${by | 0},` +
        `${fromFace || ""},${toFace || ""},${detour | 0},${lane | 0},${half | 0},` +
        `${obstaclesMemoKey(obstacles)},${sb},${(hugRects && hugRects.length) | 0},` +
        `${pre},${post}`;
      const hit = routeOrthoMemo.get(memoKey);
      if (hit) return hit.map((p) => [p[0], p[1]]);
    }

    /** Score bends on the full opening→stub→…→stub→opening path. */
    const scorePoly = (midThroughEnd) => {
      /** @type {number[][]} */
      const full = [];
      if (prePoint) full.push(prePoint);
      full.push(start);
      for (const p of midThroughEnd) full.push(p);
      if (
        postPoint &&
        (Math.abs(postPoint[0] - end[0]) > 1e-6 ||
          Math.abs(postPoint[1] - end[1]) > 1e-6)
      ) {
        const last = full[full.length - 1];
        if (
          !last ||
          Math.abs(last[0] - postPoint[0]) > 1e-6 ||
          Math.abs(last[1] - postPoint[1]) > 1e-6
        ) {
          full.push(postPoint);
        }
      }
      return cleanOrthoPoly(full);
    };

    /**
     * Emit ortho candidates.
     * @param {number} maxLaneK parallel lane multiples (0..8)
     * @param {number} maxObsK obstacle-rail lane multiples
     * @param {boolean} obstacleCPatterns include 3-bend C around each box
     * @param {boolean} wideDetours also try 2×detour side C loops
     */
    const emitCandidates = (maxLaneK, maxObsK, obstacleCPatterns, wideDetours) => {
      /** @type {number[][][]} */
      const raw = [];
      const push = (pts) => {
        const cleaned = cleanOrthoPoly([start, ...pts, end]);
        if (cleaned.length < 2) return;
        if (!isOrthoPoly(cleaned)) return;
        if (hasUTurn(cleaned)) return;
        const next = cleaned[1];
        if (!leavesOutward(fromFace, ax, ay, next[0], next[1])) return;
        raw.push(cleaned.slice(1));
      };

      if (Math.abs(ax - bx) < 1e-6 || Math.abs(ay - by) < 1e-6) {
        push([]);
      }
      push([[bx, ay]]);
      push([[ax, by]]);

      const mx = (ax + bx) / 2;
      const my = (ay + by) / 2;
      const laneOffs = [0];
      if (needLanes && maxLaneK > 0) {
        for (let k = 1; k <= maxLaneK; k++) {
          laneOffs.push(k * lane, -k * lane);
        }
      }
      for (const off of laneOffs) {
        push([[mx + off, ay], [mx + off, by]]);
        push([[ax, my + off], [bx, my + off]]);
      }

      if (toFace === "S" || fromFace === "S") {
        for (const off of laneOffs) {
          const yOut = Math.max(ay, by) + stub + Math.max(0, off);
          push([[ax, yOut], [bx, yOut]]);
        }
      }
      if (toFace === "N" || fromFace === "N") {
        for (const off of laneOffs) {
          const yOut = Math.min(ay, by) - stub - Math.max(0, off);
          push([[ax, yOut], [bx, yOut]]);
        }
      }
      if (toFace === "E" || fromFace === "E") {
        for (const off of laneOffs) {
          const xOut = Math.max(ax, bx) + stub + Math.max(0, off);
          push([[xOut, ay], [xOut, by]]);
        }
      }
      if (toFace === "W" || fromFace === "W") {
        for (const off of laneOffs) {
          const xOut = Math.min(ax, bx) - stub - Math.max(0, off);
          push([[xOut, ay], [xOut, by]]);
        }
      }

      if (hugRects && hugRects.length) {
        const c = WALL_CLEARANCE;
        for (const r of hugRects) {
          push([[r.x - c, ay], [r.x - c, by]]);
          push([[r.x + r.w + c, ay], [r.x + r.w + c, by]]);
          push([[ax, r.y - c], [bx, r.y - c]]);
          push([[ax, r.y + r.h + c], [bx, r.y + r.h + c]]);
        }
      }

      if (obstacles && obstacles.length) {
        for (const off of laneOffs) {
          const yHi = Math.max(ay, by) + detour + Math.max(0, off);
          const yLo = Math.min(ay, by) - detour - Math.max(0, off);
          const xHi = Math.max(ax, bx) + detour + Math.max(0, off);
          const xLo = Math.min(ax, bx) - detour - Math.max(0, off);
          push([[ax, yHi], [bx, yHi]]);
          push([[ax, yLo], [bx, yLo]]);
          push([[xHi, ay], [xHi, by]]);
          push([[xLo, ay], [xLo, by]]);
        }
        const obsOffs = [0];
        if (needLanes && maxObsK > 0) {
          for (let k = 1; k <= maxObsK; k++) {
            obsOffs.push(k * lane, -k * lane);
          }
        }
        const pad = Math.max(stub, WALL_CLEARANCE);
        for (const r of obstacles) {
          const xR = r.x + r.w + pad;
          const xL = r.x - pad;
          const yB = r.y + r.h + pad;
          const yT = r.y - pad;
          for (const off of obsOffs) {
            const o = Math.abs(off);
            const xRo = xR + (off >= 0 ? o : 0);
            const xLo = xL - (off <= 0 ? o : 0);
            const yBo = yB + (off >= 0 ? o : 0);
            const yTo = yT - (off <= 0 ? o : 0);
            // Always try axis-aligned rails that clear the box.
            push([[xRo, ay], [xRo, by]]);
            push([[xLo, ay], [xLo, by]]);
            push([[ax, yBo], [bx, yBo]]);
            push([[ax, yTo], [bx, yTo]]);
            if (!obstacleCPatterns) continue;
            push([[xRo, ay], [xRo, yBo], [bx, yBo]]);
            push([[xRo, ay], [xRo, yTo], [bx, yTo]]);
            push([[xLo, ay], [xLo, yBo], [bx, yBo]]);
            push([[xLo, ay], [xLo, yTo], [bx, yTo]]);
            push([[ax, yBo], [xRo, yBo], [xRo, by]]);
            push([[ax, yBo], [xLo, yBo], [xLo, by]]);
            push([[ax, yTo], [xRo, yTo], [xRo, by]]);
            push([[ax, yTo], [xLo, yTo], [xLo, by]]);
          }
        }
      }

      const detours =
        wideDetours && obstacles && obstacles.length
          ? [detour, detour * 2]
          : [detour];
      for (const d0 of detours) {
        for (const off of laneOffs) {
          const right = Math.max(ax, bx) + d0 + Math.max(0, off);
          const left = Math.min(ax, bx) - d0 - Math.max(0, off);
          const top = Math.min(ay, by) - d0 - Math.max(0, off);
          const bot = Math.max(ay, by) + d0 + Math.max(0, off);
          push([[right, ay], [right, by]]);
          push([[left, ay], [left, by]]);
          push([[ax, top], [bx, top]]);
          push([[ax, bot], [bx, bot]]);
          push([[right, ay], [right, bot], [bx, bot]]);
          push([[left, ay], [left, top], [bx, top]]);
          push([[ax, bot], [right, bot], [right, by]]);
          push([[ax, top], [left, top], [left, by]]);
        }
      }
      return raw;
    };

    const pickBest = (raw) => {
      let best = raw[0];
      let bestObstacle = Infinity;
      let bestOutside = Infinity;
      let bestStack = Infinity;
      let bestLen = Infinity;
      let bestBends = Infinity;
      let bestHug = Infinity;
      let bestEntry = Infinity;
      let bestCross = Infinity;
      let hasClearInside = false;
      if (stayBounds) {
        for (const pts of raw) {
          const full = scorePoly(pts);
          if (
            pathObstacleCost(full, obstacles) <= 0 &&
            pathOutsideBoundsCost(full, stayBounds) <= 0
          ) {
            hasClearInside = true;
            break;
          }
        }
      }
      for (const pts of raw) {
        const full = scorePoly(pts);
        const bends = polyBends(full);
        const stack = pathStackConflictCost(full, occupied, eps, half);
        const cross = pathCrossConflictCost(full, occupied, half);
        const obstacle = pathObstacleCost(full, obstacles);
        let outside = pathOutsideBoundsCost(full, stayBounds);
        if (hasClearInside && outside > 0) outside += 1e6;
        const hug = pathBorderHugCost(full, hugRects);
        const entry = pathEntryExcessCost(full, toFace);
        const len = polyLength(full);
        if (
          obstacle < bestObstacle - 1e-9 ||
          (Math.abs(obstacle - bestObstacle) < 1e-9 &&
            stack < bestStack - 1e-9) ||
          (Math.abs(obstacle - bestObstacle) < 1e-9 &&
            Math.abs(stack - bestStack) < 1e-9 &&
            outside < bestOutside - 1e-9) ||
          (Math.abs(obstacle - bestObstacle) < 1e-9 &&
            Math.abs(stack - bestStack) < 1e-9 &&
            Math.abs(outside - bestOutside) < 1e-9 &&
            len < bestLen - 1e-6) ||
          (Math.abs(obstacle - bestObstacle) < 1e-9 &&
            Math.abs(stack - bestStack) < 1e-9 &&
            Math.abs(outside - bestOutside) < 1e-9 &&
            Math.abs(len - bestLen) < 1e-6 &&
            bends < bestBends) ||
          (Math.abs(obstacle - bestObstacle) < 1e-9 &&
            Math.abs(stack - bestStack) < 1e-9 &&
            Math.abs(outside - bestOutside) < 1e-9 &&
            Math.abs(len - bestLen) < 1e-6 &&
            bends === bestBends &&
            hug < bestHug - 1e-9) ||
          (Math.abs(obstacle - bestObstacle) < 1e-9 &&
            Math.abs(stack - bestStack) < 1e-9 &&
            Math.abs(outside - bestOutside) < 1e-9 &&
            Math.abs(len - bestLen) < 1e-6 &&
            bends === bestBends &&
            Math.abs(hug - bestHug) < 1e-9 &&
            entry < bestEntry - 1e-9) ||
          (Math.abs(obstacle - bestObstacle) < 1e-9 &&
            Math.abs(stack - bestStack) < 1e-9 &&
            Math.abs(outside - bestOutside) < 1e-9 &&
            Math.abs(len - bestLen) < 1e-6 &&
            bends === bestBends &&
            Math.abs(hug - bestHug) < 1e-9 &&
            Math.abs(entry - bestEntry) < 1e-9 &&
            cross < bestCross - 1e-9)
        ) {
          best = pts;
          bestObstacle = obstacle;
          bestOutside = outside;
          bestStack = stack;
          bestLen = len;
          bestBends = bends;
          bestHug = hug;
          bestEntry = entry;
          bestCross = cross;
        }
      }
      return {
        pts: best,
        obstacle: bestObstacle,
        stack: bestStack,
        outside: bestOutside,
      };
    };

    // Narrow pass: few lanes, rails only around boxes (no per-obstacle C).
    let raw = emitCandidates(needLanes ? 2 : 0, needLanes ? 1 : 0, false, false);
    if (!raw.length) {
      /** @type {number[][]} */
      const fallback = [
        [ax + detour, ay],
        [ax + detour, by],
        [bx, by],
      ];
      if (memoKey && routeOrthoMemo) {
        routeOrthoMemo.set(
          memoKey,
          fallback.map((p) => [p[0], p[1]])
        );
      }
      return fallback;
    }
    let picked = pickBest(raw);
    if (picked.obstacle <= 0 && picked.stack <= 0 && picked.outside <= 0) {
      if (memoKey && routeOrthoMemo) {
        routeOrthoMemo.set(
          memoKey,
          picked.pts.map((p) => [p[0], p[1]])
        );
      }
      return picked.pts;
    }
    // Stack-only: medium pass (more lanes, still no C / 2×detour).
    if (picked.obstacle <= 0 && picked.outside <= 0) {
      raw = emitCandidates(needLanes ? 4 : 0, needLanes ? 1 : 0, false, false);
      if (raw.length) picked = pickBest(raw);
      if (memoKey && routeOrthoMemo) {
        routeOrthoMemo.set(
          memoKey,
          picked.pts.map((p) => [p[0], p[1]])
        );
      }
      return picked.pts;
    }
    // Hard obstacle / out-of-bounds: full wide pass.
    raw = emitCandidates(needLanes ? 8 : 0, needLanes ? 2 : 0, true, true);
    if (!raw.length) {
      if (memoKey && routeOrthoMemo) {
        routeOrthoMemo.set(
          memoKey,
          picked.pts.map((p) => [p[0], p[1]])
        );
      }
      return picked.pts;
    }
    const wide = pickBest(raw).pts;
    if (memoKey && routeOrthoMemo) {
      routeOrthoMemo.set(
        memoKey,
        wide.map((p) => [p[0], p[1]])
      );
    }
    return wide;
  }

  function edgePathD(edge, byId, occupied, halfWidth) {
    const a = byId[edge.from];
    const b = byId[edge.to];
    if (!a || !b) return null;
    const half = halfWidth != null ? Number(halfWidth) : 0;
    const fromFace = routeFace(a, edge.from_opening, edge.from_opening?.[0], byId);
    const toFace = routeFace(b, edge.to_opening, edge.to_opening?.[0], byId);
    const fromPlane = isPlaneOpeningId(edge.from_opening);
    const toPlane = isPlaneOpeningId(edge.to_opening);
    // Rendered mouths may sit inside projected boxes (iso), not strictly on
    // contour anchors.
    const m1 = openingMouthAbs(a, edge.from_opening, edge.from_opening?.[0], byId);
    const m2 = openingMouthAbs(b, edge.to_opening, edge.to_opening?.[0], byId);
    const a1 = openingAnchorAbs(a, edge.from_opening, edge.from_opening?.[0], byId);
    const a2 = openingAnchorAbs(b, edge.to_opening, edge.to_opening?.[0], byId);
    // Iso marks often sit off the contour (mid-depth); that alone must not
    // clear the endpoint as an obstacle — only a mouth *inside* the place
    // needs a corridor to the boca (Route_31 N↔N must skirt the upper box).
    const fromOffContour = Math.hypot(m1.x - a1.x, m1.y - a1.y) > 1e-6;
    const toOffContour = Math.hypot(m2.x - a2.x, m2.y - a2.y) > 1e-6;
    const fromInset = pointInPlaceInterior(m1, a, byId);
    const toInset = pointInPlaceInterior(m2, b, byId);
    // Allow the route to enter leaves whose end is a B/F boca.
    /** @type {string[]} */
    const exclude = [];
    if (fromPlane) exclude.push(a.id);
    if (toPlane) exclude.push(b.id);
    // When the rendered mouth is inside the place (iso inset mark), allow the
    // path to enter that endpoint box so the conduit reaches the visible boca.
    if (fromInset && !exclude.includes(a.id)) exclude.push(a.id);
    if (toInset && !exclude.includes(b.id)) exclude.push(b.id);
    // Foreign bocas on endpoint boxes (mark-to-mark, plane↔plane only):
    // reject L/C that skim a neighbor mouth on the same JB (Route_28 Linea_03
    // vs B2-1). Side↔plane (Route_21 lamp) keeps placeObstacles alone so the
    // preferred L is not flipped onto a strand-hostile corridor.
    const mouthPad = Math.max(OPENING_MARK_R, half || 0) + LANE_GAP;
    const mouthObs =
      fromPlane && toPlane
        ? foreignMouthObstacleRects(
            byId,
            new Set([
              `${a.id}\0${edge.from_opening}`,
              `${b.id}\0${edge.to_opening}`,
            ]),
            mouthPad,
            new Set([a.id, b.id])
          )
        : [];
    const obstacles = placeObstacles(byId, exclude);
    const markObstacles = obstacles.concat(mouthObs);
    const hugRects = placeBorderRects(byId);
    /** @type {{x:number,y:number,w:number,h:number}|null} */
    let stayBounds = null;
    if (a.parent && a.parent === b.parent) {
      const parent = byId[a.parent];
      if (parent) {
        const pa = absXY(parent, byId);
        const origin = contentOriginLocal(parent);
        const fr = frontRectLocal(parent);
        stayBounds = {
          x: pa.x + origin.x,
          y: pa.y + origin.y,
          w: Math.max(4, fr.w - 2 * PAD),
          h: Math.max(4, fr.h - HEADER - PAD),
        };
      }
    }
    /** @type {number[][]|null} */
    let chain = null;
    const append = (fromPt, toPt, ff, tf) => {
      const part = orthoRoute(
        fromPt,
        toPt,
        ff,
        tf,
        occupied,
        obstacles,
        stayBounds,
        hugRects,
        half
      );
      chain = chain
        ? mergeOrthoPolys(chain, part)
        : part.map((p) => [p[0], p[1]]);
    };
    // Interior legs (plane ↔ contour) must NOT use face stubs: orthoRoute
    // stubs go outward and paint a dead-end spur (ghost tube).
    const appendInside = (fromPt, toPt) => {
      const part = orthoRoute(
        fromPt,
        toPt,
        null,
        null,
        occupied,
        obstacles,
        stayBounds,
        hugRects,
        half
      );
      chain = chain
        ? mergeOrthoPolys(chain, part)
        : part.map((p) => [p[0], p[1]]);
    };
    if (fromPlane || toPlane) {
      // Colinear B/F mouths: paint a single H/V segment (no contour stubs).
      if (
        fromPlane &&
        toPlane &&
        (Math.abs(m1.x - m2.x) < 1e-6 || Math.abs(m1.y - m2.y) < 1e-6)
      ) {
        const pts = cleanOrthoPoly([
          [m1.x, m1.y],
          [m2.x, m2.y],
        ]);
        if (
          pts.length >= 2 &&
          pathObstacleCost(pts, markObstacles) <= 0 &&
          pathStackConflictCost(
            pts,
            occupied,
            Math.max(LANE_GAP, half || 0),
            half
          ) <= 0
        ) {
          const d = pointsToPathD(pts);
          return { d, dCore: d, segs: segsFromPoints(pts, half) };
        }
      }
      // Offset B/F mouths: prefer mark-to-mark Manhattan with few bends —
      // L (one corner) first, then C/U (two corners / three segments) via
      // orthoRoute — before contour stubs (Route_28 Linea_03).
      // Also side↔plane (Route_21 Conducto_lampara N→B).
      if (
        (fromPlane || toPlane) &&
        Math.abs(m1.x - m2.x) >= 1e-6 &&
        Math.abs(m1.y - m2.y) >= 1e-6
      ) {
        const stackEps = Math.max(LANE_GAP, half || 0);
        const bothPlane = fromPlane && toPlane;
        const minLeg = bothPlane ? 0 : Math.max(8, LANE_PITCH);
        const pathLen = (pts) => {
          let len = 0;
          for (let i = 1; i < pts.length; i++) {
            len += Math.hypot(
              pts[i][0] - pts[i - 1][0],
              pts[i][1] - pts[i - 1][1]
            );
          }
          return len;
        };
        const acceptMarkPath = (pts) => {
          if (!pts || pts.length < 2) return false;
          if (minLeg > 0) {
            for (let i = 1; i < pts.length; i++) {
              const leg = Math.hypot(
                pts[i][0] - pts[i - 1][0],
                pts[i][1] - pts[i - 1][1]
              );
              if (leg < minLeg - 1e-6) return false;
            }
          }
          if (pathObstacleCost(pts, markObstacles) > 0) return false;
          // A side mouth must leave on its declared face and a plane mouth
          // must be approached through its nearest contour face. Without
          // these strict endpoint directions S→B can take a shorter-but-wrong
          // west exit (Route_32).
          const leavesFace = (face, origin, toward) => {
            const dx = toward[0] - origin.x;
            const dy = toward[1] - origin.y;
            if (face === "N") return Math.abs(dx) < 1e-6 && dy < -1e-6;
            if (face === "S") return Math.abs(dx) < 1e-6 && dy > 1e-6;
            if (face === "E") return Math.abs(dy) < 1e-6 && dx > 1e-6;
            if (face === "W") return Math.abs(dy) < 1e-6 && dx < -1e-6;
            return true;
          };
          if (fromPlane !== toPlane) {
            if (!fromPlane && !leavesFace(fromFace, m1, pts[1])) return false;
            if (!toPlane && !leavesFace(toFace, m2, pts[pts.length - 2])) {
              return false;
            }
            if (toPlane && !leavesFace(toFace, m2, pts[pts.length - 2])) {
              return false;
            }
          }
          if (pathStackConflictCost(pts, occupied, stackEps, half) > 0) {
            return false;
          }
          return true;
        };
        const lCandidates = [
          cleanOrthoPoly([
            [m1.x, m1.y],
            [m2.x, m1.y],
            [m2.x, m2.y],
          ]),
          cleanOrthoPoly([
            [m1.x, m1.y],
            [m1.x, m2.y],
            [m2.x, m2.y],
          ]),
        ];
        /** @type {{pts:number[][], len:number}[]} */
        const scored = [];
        for (const pts of lCandidates) {
          if (pts.length < 3) continue;
          if (!acceptMarkPath(pts)) continue;
          scored.push({ pts, len: pathLen(pts) });
        }
        scored.sort((a, b) => a.len - b.len);
        if (scored.length) {
          const pts = scored[0].pts;
          const d = pointsToPathD(pts);
          return { d, dCore: d, segs: segsFromPoints(pts, half) };
        }
        // B↔B mouths may sit inside their projected endpoint boxes.  A
        // three-segment U through an endpoint box is valid, whereas contour
        // stubs turn the same detour into six painted segments (Route_28).
        if (fromPlane && toPlane) {
          const railGap = Math.max(LANE_PITCH, LANE_GAP + (half || 0));
          const cCandidates = [
            cleanOrthoPoly([
              [m1.x, m1.y],
              [m1.x, m2.y + railGap],
              [m2.x, m2.y + railGap],
              [m2.x, m2.y],
            ]),
            cleanOrthoPoly([
              [m1.x, m1.y],
              [m1.x, m2.y - railGap],
              [m2.x, m2.y - railGap],
              [m2.x, m2.y],
            ]),
          ].filter(acceptMarkPath);
          cCandidates.sort((a, b) => pathLen(a) - pathLen(b));
          if (cCandidates.length) {
            const pts = cCandidates[0];
            const d = pointsToPathD(pts);
            return { d, dCore: d, segs: segsFromPoints(pts, half) };
          }
        }
        // L blocked (stack/obstacle): try ≤3-segment mark-to-mark C/U.
        // Pass faces so N/W mouths stub *out* of the sprite AABB first
        // (Route_21 lamp N→B must clear the from-box iso margin).
        const cPts = cleanOrthoPoly(
          orthoRoute(
            m1,
            m2,
            fromFace,
            toFace,
            occupied,
            markObstacles,
            stayBounds,
            hugRects,
            half
          )
        );
        if (
          cPts.length >= 3 &&
          polyBends(cPts) <= 2 &&
          acceptMarkPath(cPts)
        ) {
          const d = pointsToPathD(cPts);
          return { d, dCore: d, segs: segsFromPoints(cPts, half) };
        }
      }
      // Cross the contour at a nudged entry so B-approach does not sit on N1.
      let cur = a1;
      let curFace = fromFace;
      if (fromPlane) {
        const entry = planeContourEntryAbs(
          a,
          edge.from_opening,
          edge.from_opening?.[0],
          byId
        );
        appendInside(a1, entry);
        cur = entry;
        curFace = fromFace;
      }
      if (toPlane) {
        const entry = planeContourEntryAbs(
          b,
          edge.to_opening,
          edge.to_opening?.[0],
          byId
        );
        append(cur, entry, curFace, toFace);
        appendInside(entry, a2);
      } else {
        append(cur, a2, curFace, toFace);
      }
      let pts = stripOutAndBack(
        chain || [
          [a1.x, a1.y],
          [a2.x, a2.y],
        ]
      );
      if (pts.length) {
        pts[0] = [a1.x, a1.y];
        pts[pts.length - 1] = [a2.x, a2.y];
      }
      const corePts = cleanOrthoPoly(pts.map((p) => [p[0], p[1]]));
      if (corePts.length < 2) return null;
      const dCore = pointsToPathD(corePts);
      if (fromOffContour && pts.length) {
        const head = renderedMarkHeadPts(m1, a1, fromFace, fromPlane);
        if (head.length >= 2) {
          pts = mergeOrthoPolys(head, pts) || pts;
        }
      }
      if (toOffContour && pts.length) {
        const tail = renderedMarkTailPts(a2, m2, toFace, toPlane);
        if (tail.length >= 2) {
          pts = mergeOrthoPolys(pts, tail) || pts;
        }
      }
      pts = stripOutAndBack(pts, [
        [m1.x, m1.y],
        [m2.x, m2.y],
        [a1.x, a1.y],
        [a2.x, a2.y],
      ]);
      if (fromOffContour && pts.length) pts[0] = [m1.x, m1.y];
      if (toOffContour && pts.length) pts[pts.length - 1] = [m2.x, m2.y];
      pts = cleanOrthoPoly(pts);
      if (pts.length < 2) return null;
      return {
        d: pointsToPathD(pts),
        dCore,
        segs: segsFromPoints(pts, half),
      };
    }

    // Side openings: colinear mouths → straight mark-to-mark when clear
    // (face stubs of 20px cross in tight gaps and force a C — Route_14 Tube2).
    if (
      Math.abs(m1.x - m2.x) < 1e-6 ||
      Math.abs(m1.y - m2.y) < 1e-6
    ) {
      const pts = cleanOrthoPoly([
        [m1.x, m1.y],
        [m2.x, m2.y],
      ]);
      const stackEps = Math.max(LANE_GAP, half || 0);
      if (
        pts.length >= 2 &&
        pathObstacleCost(pts, obstacles) <= 0 &&
        pathStackConflictCost(pts, occupied, stackEps, half) <= 0
      ) {
        const d = pointsToPathD(pts);
        return { d, dCore: d, segs: segsFromPoints(pts, half) };
      }
    }
    // Side openings: route between rendered mid-depth mouths so aligned boxes
    // keep straight tubes (no contour→mark L-jogs on the paint path).
    append(m1, m2, fromFace, toFace);
    let pts = stripOutAndBack(
      chain || [
        [m1.x, m1.y],
        [m2.x, m2.y],
      ],
      [
        [m1.x, m1.y],
        [m2.x, m2.y],
      ]
    );
    if (pts.length) {
      pts[0] = [m1.x, m1.y];
      pts[pts.length - 1] = [m2.x, m2.y];
    }
    pts = cleanOrthoPoly(pts);
    if (pts.length < 2) return null;
    const d = pointsToPathD(pts);
    return { d, dCore: d, segs: segsFromPoints(pts, half) };
  }

  function elementAbsXY(elem, placeById) {
    if (!elem.parent) {
      return mirrorTopLevel(
        elem.x ?? 0,
        elem.y ?? 0,
        elem.w ?? ELEM_W,
        elem.h ?? ELEM_H
      );
    }
    const parent = placeById[elem.parent];
    if (!parent) {
      return mirrorTopLevel(
        elem.x ?? 0,
        elem.y ?? 0,
        elem.w ?? ELEM_W,
        elem.h ?? ELEM_H
      );
    }
    const a = absXY(parent, placeById);
    const flips = ownFlips(parent);
    const local = mirrorLocalInParent(
      elem.x ?? 0,
      elem.y ?? 0,
      elem.w ?? ELEM_W,
      elem.h ?? ELEM_H,
      parent,
      flips
    );
    const origin = contentOriginLocal(parent);
    return {
      x: a.x + origin.x + local.x,
      y: a.y + origin.y + local.y,
    };
  }

  function elementCenter(elem, placeById) {
    const p = elementAbsXY(elem, placeById);
    return {
      x: p.x + (elem.w ?? ELEM_W) / 2,
      y: p.y + (elem.h ?? ELEM_H) / 2,
    };
  }

  function simpleOrthoPts(p1, p2) {
    const x1 = p1.x;
    const y1 = p1.y;
    const x2 = p2.x;
    const y2 = p2.y;
    if (Math.abs(x1 - x2) < 1e-6 && Math.abs(y1 - y2) < 1e-6) {
      return [[x1, y1]];
    }
    if (Math.abs(x1 - x2) < 1e-6 || Math.abs(y1 - y2) < 1e-6) {
      return [
        [x1, y1],
        [x2, y2],
      ];
    }
    return [
      [x1, y1],
      [x2, y1],
      [x2, y2],
    ];
  }

  /** Which side of ``elem`` faces ``toward`` (E/W/N/S). */
  function elementAttachFace(elem, toward, placeById) {
    const p = elementAbsXY(elem, placeById);
    const w = elem.w ?? ELEM_W;
    const h = elem.h ?? ELEM_H;
    const cx = p.x + w / 2;
    const cy = p.y + h / 2;
    const dx = toward.x - cx;
    const dy = toward.y - cy;
    if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? "E" : "W";
    return dy >= 0 ? "S" : "N";
  }

  /**
   * Attach point on an element face. ``slot``/``slotCount`` spread terminals
   * along that face so strands do not all land on the midpoint.
   */
  function elementAttachPoint(elem, toward, placeById, slot = 0, slotCount = 1) {
    const p = elementAbsXY(elem, placeById);
    const w = elem.w ?? ELEM_W;
    const h = elem.h ?? ELEM_H;
    const face = elementAttachFace(elem, toward, placeById);
    const n = Math.max(1, slotCount | 0);
    const s = Math.max(0, Math.min(n - 1, slot | 0));
    const t = n <= 1 ? 0.5 : (s + 0.5) / n;
    const inset = 4;
    if (face === "E" || face === "W") {
      const usable = Math.max(2, h - 2 * inset);
      return {
        x: face === "E" ? p.x + w : p.x,
        y: p.y + inset + t * usable,
      };
    }
    const usable = Math.max(2, w - 2 * inset);
    return {
      x: p.x + inset + t * usable,
      y: face === "S" ? p.y + h : p.y,
    };
  }

  /** Stable key for one cable_edge row (id alone can repeat across pairs). */
  function cableEdgeKey(edge) {
    return `${edge.id || ""}|${edge.from || ""}|${edge.to || ""}|${edge.from_pin || ""}|${edge.to_pin || ""}`;
  }

  /**
   * Highway cross-section (px):
   *   [gap][strand][gap][strand]…[gap][strand][gap]
   * gap == strand width so every transparent separator matches a wire.
   */
  // STRAND_WIDTH / LANE_GAP declared near top (routing + highway share them).
  const JACKET_OPACITY_WIDTH_PAD = 1.2;

  /** Conduit road width from strand count (not a fixed stroke). */
  function highwayRoadWidth(strandCount) {
    const n = Math.max(1, strandCount | 0);
    return n * STRAND_WIDTH + (n + 1) * LANE_GAP;
  }

  /** Perpendicular offset of lane ``i`` from the conduit centerline. */
  function highwayLaneOffset(laneIndex, strandCount) {
    const n = Math.max(1, strandCount | 0);
    const i = Math.max(0, Math.min(n - 1, laneIndex | 0));
    const pitch = STRAND_WIDTH + LANE_GAP;
    const content = n * STRAND_WIDTH + (n - 1) * LANE_GAP;
    const first = -content / 2 + STRAND_WIDTH / 2;
    return first + i * pitch;
  }

  /** Span width of consecutive lanes [i0..i1] (for cable jackets). */
  function highwaySpanWidth(laneCountInGroup) {
    const k = Math.max(1, laneCountInGroup | 0);
    return k * STRAND_WIDTH + (k - 1) * LANE_GAP + JACKET_OPACITY_WIDTH_PAD;
  }

  /** @deprecated alias — road width from strand lanes */
  function conduitRoadWidth(_containsCount, laneCount) {
    return highwayRoadWidth(laneCount || _containsCount || 1);
  }

  /** Lane count for tube stroke; ignore cable packing when electrical is off. */
  function tubeLaneCount(edge, layout) {
    if (!showElectrical) return 1;
    if (layout && typeof layout.conduitStrandCount === "function") {
      const packed = layout.conduitStrandCount(edge.id);
      if (packed > 0) return packed;
    }
    return conduitLaneHint(edge, graph?.cable_edges || []);
  }

  /** How many strand lanes ride a conduit edge (for road width). */
  function conduitLaneHint(edge, cableEdges) {
    const cid = edge.id;
    const contains = edge.contains || [];
    let strands = 0;
    for (const ce of cableEdges || []) {
      const hops = ce.conduit_hops || [];
      const on =
        (ce.conduit && ce.conduit === cid) ||
        hops.some((h) => h.conduit === cid) ||
        (ce.id && contains.includes(ce.id));
      if (!on) continue;
      strands += cableWireIndices(ce).length;
    }
    // Do not use contains.length: after loose-conductor modeling it can exceed
    // packed lanes (or include ids not painted), which fattened empty tubes.
    return Math.max(strands, 1);
  }

  /** Local (element-space) anchor for a terminal cell id. */
  function terminalCellAnchorLocal(elem, cellId, placeById) {
    const w = elem.w ?? ELEM_W;
    const h = elem.h ?? ELEM_H;
    const side = parseSideOpening(cellId);
    const rawFace = (side?.face || String(cellId || "?")[0] || "?").toUpperCase();
    const placeMap = placeById || Object.fromEntries(
      (graph?.nodes || []).map((n) => [n.id, n])
    );
    const flips = effectiveFlips(elem, placeMap);
    const face = flipFace(rawFace, flips);
    const index = side?.index || 1;
    const raw = elem.terminal_grid && elem.terminal_grid[rawFace];
    let n = index;
    if (Array.isArray(raw) && raw.length >= 1) {
      n = Math.max(1, Number(raw[0]) || 1);
      if (raw.length >= 2) {
        n = Math.max(n, (Number(raw[0]) || 1) * (Number(raw[1]) || 1));
      }
    }
    n = Math.max(n, index);
    let t = index / (n + 1);
    if ((face === "N" || face === "S") && flips.we) t = 1 - t;
    else if ((face === "E" || face === "W") && flips.ns) t = 1 - t;
    if (face === "N") return { x: t * w, y: 0, face };
    if (face === "S") return { x: t * w, y: h, face };
    if (face === "W") return { x: 0, y: t * h, face };
    if (face === "E") return { x: w, y: t * h, face };
    return { x: w / 2, y: h / 2, face: "?" };
  }

  /** Side opening-style cell on an element (``N1``, ``S2``, …). */
  function terminalCellAnchor(elem, cellId, placeById) {
    const p = elementAbsXY(elem, placeById);
    const local = terminalCellAnchorLocal(elem, cellId, placeById);
    return { x: p.x + local.x, y: p.y + local.y, face: local.face };
  }

  function pickPinCell(elem, pin, toward, placeById) {
    if (!pin || !elem || !elem.terminal_pins) return null;
    const cells =
      elem.terminal_pins[pin] || elem.terminal_pins[String(pin)] || null;
    if (!cells || !cells.length) return null;
    if (cells.length === 1) return cells[0];
    const face = elementAttachFace(elem, toward, placeById);
    const flips = effectiveFlips(elem, placeById);
    const match = cells.find(
      (c) => flipFace(String(c || "")[0], flips) === face
    );
    if (match) return match;
    // Approach face not in pin cells (e.g. W toward NS grid): prefer the
    // cell whose outward stub points into the approach and needs fewer bends.
    let best = cells[0];
    let bestScore = Infinity;
    for (const c of cells) {
      const a = terminalCellAnchor(elem, c, placeById);
      const fo = faceOutwardDelta(a.face);
      const stub = stubPoint(a, fo.x, fo.y, INBOX_STUB);
      const vx = toward.x - a.x;
      const vy = toward.y - a.y;
      const align = fo.x * vx + fo.y * vy;
      const hv = [
        [stub.x, stub.y],
        [toward.x, stub.y],
        [toward.x, toward.y],
      ];
      const vh = [
        [stub.x, stub.y],
        [stub.x, toward.y],
        [toward.x, toward.y],
      ];
      const bendsOf = (poly) => {
        let b = 0;
        for (let i = 2; i < poly.length; i++) {
          const ax = poly[i - 1][0] - poly[i - 2][0];
          const ay = poly[i - 1][1] - poly[i - 2][1];
          const bx = poly[i][0] - poly[i - 1][0];
          const by = poly[i][1] - poly[i - 1][1];
          if (Math.abs(ax * by - ay * bx) > 1e-6) b += 1;
        }
        return b;
      };
      const lenOf = (poly) => {
        let L = 0;
        for (let i = 1; i < poly.length; i++) {
          L += Math.hypot(poly[i][0] - poly[i - 1][0], poly[i][1] - poly[i - 1][1]);
        }
        return L;
      };
      const straight =
        Math.abs(stub.x - toward.x) < 1e-6 ||
        Math.abs(stub.y - toward.y) < 1e-6;
      const bestL = straight
        ? [
            [stub.x, stub.y],
            [toward.x, toward.y],
          ]
        : bendsOf(hv) < bendsOf(vh) ||
            (bendsOf(hv) === bendsOf(vh) && lenOf(hv) <= lenOf(vh))
          ? hv
          : vh;
      const score =
        (align < -1e-6 ? 1e6 : 0) +
        bendsOf(bestL) * 1e3 +
        lenOf(bestL);
      if (score < bestScore) {
        bestScore = score;
        best = c;
      }
    }
    return best;
  }

  /** True when ``cellId`` (e.g. N2) sits on this element's terminal_grid. */
  function cellIdOnElementGrid(elem, cellId) {
    const side = parseSideOpening(cellId);
    if (!side || !elem?.terminal_grid) return false;
    const raw = elem.terminal_grid[side.face];
    if (!Array.isArray(raw) || !raw.length) return false;
    const cols = Math.max(1, Number(raw[0]) || 1);
    const rows = Math.max(1, Number(raw[1]) || 1);
    return side.index >= 1 && side.index <= cols * rows;
  }

  /**
   * Attach for a connection pin when ``terminal_grid`` is known; otherwise
   * fall back to fanned mid-face slots. Returns ``{x,y,face}``.
   *
   * InOut NS/WE pins may attach on either face of the same index; pick the
   * cell that faces ``toward`` (mouth) so inbox stays ≤3 segments instead of
   * wrapping around the strip (Route_30 north box → south terminals).
   */
  function resolveElementAttach(
    elem,
    pin,
    toward,
    placeById,
    slot = 0,
    slotCount = 1
  ) {
    let cell = pickPinCell(elem, pin, toward, placeById);
    if (!cell && pin) {
      const pinS = String(pin);
      /** @type {string[]} */
      const cells = [];
      if (cellIdOnElementGrid(elem, pinS)) cells.push(pinS);
      const opp = oppositeTerminalCellId(pinS);
      if (opp && cellIdOnElementGrid(elem, opp)) cells.push(opp);
      if (cells.length) {
        cell = pickPinCell(
          { ...elem, terminal_pins: { [pinS]: cells } },
          pinS,
          toward,
          placeById
        );
      }
    }
    if (cell) return terminalCellAnchor(elem, cell, placeById);
    const pt = elementAttachPoint(elem, toward, placeById, slot, slotCount);
    const face = elementAttachFace(elem, toward, placeById);
    return { x: pt.x, y: pt.y, face };
  }

  /** ``N2`` → ``S2`` when the pin is a side face cell. */
  function oppositeTerminalCellId(cellId) {
    const side = parseSideOpening(cellId);
    if (!side) return null;
    const opp = { N: "S", S: "N", W: "E", E: "W" }[side.face];
    if (!opp) return null;
    return `${opp}${side.index}`;
  }

  const INBOX_STUB = 14;
  /** Keep offset spine / inbox mids this far outside the element face (px). */
  const ELEMENT_FACE_CLEARANCE = 8;
  /** Extra stroke beyond the tube fill for the high-contrast rim. */
  const OUTLINE_EXTRA = 0.8;

  /** Stub depth past a pin so a multi-cable V fits without climbing back. */
  function inboxStubDepth(slotCount) {
    const n = Math.max(1, slotCount | 0);
    if (n <= 1) return INBOX_STUB;
    return Math.max(
      INBOX_STUB,
      TERMINAL_FAN_TIP + TERMINAL_FAN_RAIL + LANE_GAP * 2
    );
  }

  function faceOutwardDelta(face) {
    const f = String(face || "").toUpperCase();
    if (f === "N") return { x: 0, y: -1 };
    if (f === "S") return { x: 0, y: 1 };
    if (f === "W") return { x: -1, y: 0 };
    if (f === "E") return { x: 1, y: 0 };
    return { x: 0, y: 0 };
  }

  /** Opening face inward (into the place interior). */
  function openingInwardDelta(face) {
    const f = String(face || "").toUpperCase();
    if (f === "N") return { x: 0, y: 1 };
    if (f === "S") return { x: 0, y: -1 };
    if (f === "W") return { x: 1, y: 0 };
    if (f === "E") return { x: -1, y: 0 };
    return { x: 0, y: 0 };
  }

  function stubPoint(pt, dx, dy, dist) {
    return { x: pt.x + dx * dist, y: pt.y + dy * dist };
  }

  /**
   * Outward stub length that does not overshoot ``toward`` along the face
   * normal (avoids down-then-up when the pin sits near the exit opening).
   */
  function stubDistToToward(fromPt, faceDelta, toward, maxDist) {
    const max = maxDist == null ? INBOX_STUB : maxDist;
    const along =
      (toward.x - fromPt.x) * faceDelta.x +
      (toward.y - fromPt.y) * faceDelta.y;
    if (along > 1e-6) return Math.min(max, Math.max(0, along - 0.5));
    return max;
  }

  /** Ortho link from contour anchor to rendered inset mark on a side face. */
  function insetMarkLinkPts(anchor, mark, face) {
    const oi = openingInwardDelta(face);
    const ax = anchor.x;
    const ay = anchor.y;
    const mx = mark.x;
    const my = mark.y;
    if (Math.hypot(mx - ax, my - ay) < 1.5) {
      return [
        [ax, ay],
        [mx, my],
      ];
    }
    if (oi.y !== 0) {
      return [
        [ax, ay],
        [mx, ay],
        [mx, my],
      ];
    }
    return [
      [ax, ay],
      [ax, my],
      [mx, my],
    ];
  }

  function renderedMarkHeadPts(mark, anchor, face, isPlane) {
    if (isPlane) return orthoPtsPrefer(mark, anchor, anchor);
    const link = insetMarkLinkPts(anchor, mark, face);
    return link.slice().reverse();
  }

  function renderedMarkTailPts(anchor, mark, face, isPlane) {
    if (isPlane) return orthoPtsPrefer(anchor, mark, mark);
    return insetMarkLinkPts(anchor, mark, face);
  }

  /**
   * Orthogonal path between two points preferring the bend nearer ``prefer``.
   * Avoids always hugging a wall when a vertical-first L stays interior.
   */
  function orthoPtsPrefer(p1, p2, prefer) {
    if (Math.abs(p1.x - p2.x) < 1e-6 || Math.abs(p1.y - p2.y) < 1e-6) {
      return simpleOrthoPts(p1, p2);
    }
    const hv = [
      [p1.x, p1.y],
      [p2.x, p1.y],
      [p2.x, p2.y],
    ];
    const vh = [
      [p1.x, p1.y],
      [p1.x, p2.y],
      [p2.x, p2.y],
    ];
    if (!prefer) return hv;
    const dHv = Math.hypot(p2.x - prefer.x, p1.y - prefer.y);
    const dVh = Math.hypot(p1.x - prefer.x, p2.y - prefer.y);
    return dVh < dHv ? vh : hv;
  }

  /**
   * In-box route: stub out of each endpoint, then ortho through the place
   * interior (not along the place border).
   * @param {"element"|"opening"} toKind
   */
  function inboxRoutePts(fromPt, fromFace, toPt, toFace, preferCenter, toKind) {
    const fo = faceOutwardDelta(fromFace);
    const aStub = stubPoint(
      fromPt,
      fo.x,
      fo.y,
      stubDistToToward(fromPt, fo, toPt)
    );
    let bStub;
    if (toKind === "opening") {
      const oi = openingInwardDelta(toFace);
      bStub = stubPoint(
        toPt,
        oi.x,
        oi.y,
        stubDistToToward(toPt, oi, fromPt)
      );
    } else {
      const eo = faceOutwardDelta(toFace);
      bStub = stubPoint(
        toPt,
        eo.x,
        eo.y,
        stubDistToToward(toPt, eo, fromPt)
      );
    }
    /** @type {number[][][]} */
    const mids = [];
    if (
      Math.abs(aStub.x - bStub.x) < 1e-6 ||
      Math.abs(aStub.y - bStub.y) < 1e-6
    ) {
      mids.push([
        [aStub.x, aStub.y],
        [bStub.x, bStub.y],
      ]);
    } else {
      mids.push(
        [
          [aStub.x, aStub.y],
          [bStub.x, aStub.y],
          [bStub.x, bStub.y],
        ],
        [
          [aStub.x, aStub.y],
          [aStub.x, bStub.y],
          [bStub.x, bStub.y],
        ]
      );
    }
    let bestMid = mids[0];
    let bestScore = Infinity;
    for (const mid of mids) {
      // Prefer interior (near place center) over wall-sliding L's.
      let pref = 0;
      if (preferCenter) {
        for (const p of mid) {
          pref += Math.hypot(p[0] - preferCenter.x, p[1] - preferCenter.y);
        }
        pref /= mid.length;
      }
      // Strongly penalize mid legs that stay on the element face (regleta border).
      let faceHug = 0;
      if (fo.x || fo.y) {
        for (const q of mid) {
          const along =
            (q[0] - fromPt.x) * fo.x + (q[1] - fromPt.y) * fo.y;
          if (along < ELEMENT_FACE_CLEARANCE) {
            faceHug += ELEMENT_FACE_CLEARANCE - along;
          }
        }
      }
      const fullCand = [
        [fromPt.x, fromPt.y],
        ...mid,
        [toPt.x, toPt.y],
      ];
      const bends = orthoBendCount(fullCand);
      let reverse = 0;
      for (let k = 2; k < fullCand.length; k++) {
        const ax = fullCand[k - 1][0] - fullCand[k - 2][0];
        const ay = fullCand[k - 1][1] - fullCand[k - 2][1];
        const bx = fullCand[k][0] - fullCand[k - 1][0];
        const by = fullCand[k][1] - fullCand[k - 1][1];
        if (Math.abs(ax * by - ay * bx) > 1e-6) continue;
        if (ax * bx + ay * by < -1e-6) reverse += 1;
      }
      const score = pref * 10 + bends + faceHug * 80 + reverse * 500;
      if (score < bestScore) {
        bestScore = score;
        bestMid = mid;
      }
    }
    /** @type {number[][]} */
    const pts = [[fromPt.x, fromPt.y]];
    for (const p of bestMid) {
      const prev = pts[pts.length - 1];
      if (prev && Math.hypot(prev[0] - p[0], prev[1] - p[1]) < 1e-6) continue;
      pts.push(p);
    }
    const last = pts[pts.length - 1];
    if (
      !last ||
      Math.abs(last[0] - toPt.x) > 1e-6 ||
      Math.abs(last[1] - toPt.y) > 1e-6
    ) {
      pts.push([toPt.x, toPt.y]);
    }
    /** @type {number[][]} */
    const clean = [];
    for (const p of pts) {
      const prev = clean[clean.length - 1];
      if (prev && Math.hypot(prev[0] - p[0], prev[1] - p[1]) < 1e-6) continue;
      clean.push(p);
    }
    return clean;
  }

  function pathDToPoints(d) {
    /** @type {number[][]} */
    const pts = [];
    const re = /[ML]\s*([-\d.]+)(?:\s+|,)([-\d.]+)/gi;
    let m;
    while ((m = re.exec(String(d || "")))) {
      pts.push([Number(m[1]), Number(m[2])]);
    }
    return pts;
  }

  function reversePathD(d) {
    const pts = pathDToPoints(d);
    pts.reverse();
    return pointsToPathD(pts);
  }

  /**
   * HouseWire conductor palette (IEC 60757 letter codes → CSS).
   * Canonical source: housewire.house.wire_colors; loaded from /api/wire-colors.
   */
  let CONDUCTOR_COLORS = {
    BN: "#a0522d",
    BK: "#1a1a1a",
    BU: "#1e90ff",
    GNYE: "#adff2f",
    GY: "#9e9e9e",
    RD: "#e53935",
    OG: "#fb8c00",
    YE: "#fdd835",
    GN: "#43a047",
    VT: "#8e24aa",
    WH: "#ffffff",
    PK: "#ec407a",
    TQ: "#26a69a",
    SR: "#b0bec5",
  };
  let UNKNOWN_WIRE_CSS = "#8b949e";

  async function loadConductorColors() {
    try {
      const data = await api("/api/wire-colors");
      const colors = data && data.colors;
      if (!colors || typeof colors !== "object") return;
      const next = {};
      for (const [code, meta] of Object.entries(colors)) {
        if (meta && typeof meta.css === "string") next[code] = meta.css;
      }
      if (Object.keys(next).length) CONDUCTOR_COLORS = next;
      if (typeof data.unknown_css === "string") UNKNOWN_WIRE_CSS = data.unknown_css;
    } catch {
      /* keep embedded fallback */
    }
  }

  function wireColorCss(code) {
    const key = String(code || "").trim().toUpperCase();
    return CONDUCTOR_COLORS[key] || UNKNOWN_WIRE_CSS;
  }

  /** sRGB relative luminance of a ``#rrggbb`` fill. */
  function relativeLuminance(fillCss) {
    const h = String(fillCss || "").replace("#", "");
    if (h.length !== 6) return 0.5;
    const r = parseInt(h.slice(0, 2), 16) / 255;
    const g = parseInt(h.slice(2, 4), 16) / 255;
    const b = parseInt(h.slice(4, 6), 16) / 255;
    const chan = (c) =>
      c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b);
  }

  /** High-contrast rim for a fill color (light on dark, dark on light). */
  function contrastOutlineCss(fillCss) {
    return relativeLuminance(fillCss) < 0.45 ? "#ffffff" : "#0d1117";
  }

  /**
   * Nested content needs the thin high-contrast rim only when it would vanish
   * into its container — e.g. BK jacket inside a BK conduit, or BK strand on a
   * dark canvas when there is no jacket/conduit color. Distinct IEC codes (BK
   * in WH) or a dark tube on a light canvas do not need the rim.
   */
  function needsNestedContrastRim(innerCode, outerCode, innerCss, outerCss) {
    const ic = String(innerCode || "").trim().toUpperCase();
    const oc = String(outerCode || "").trim().toUpperCase();
    if (ic && oc) return ic === oc;
    if (!innerCss || !outerCss) return false;
    return Math.abs(relativeLuminance(innerCss) - relativeLuminance(outerCss)) < 0.28;
  }

  /** Canvas / viewport background (theme ``--bg``) for rim decisions. */
  function canvasBackgroundCss() {
    try {
      const raw = getComputedStyle(document.documentElement)
        .getPropertyValue("--bg")
        .trim();
      if (raw && /^#([0-9a-fA-F]{6})$/.test(raw)) return raw;
    } catch {
      /* ignore */
    }
    const theme = document.documentElement.getAttribute("data-theme");
    return theme === "light" ? "#f6f8fa" : "#1a1d21";
  }

  /**
   * Immediate visual container for a cable stroke: jacket, else conduit color,
   * else the canvas background (loose wire with no cable / uncolored tube).
   */
  function strokeContainerForCableEdge(edge) {
    if (edge && edge.jacket_color) {
      const code = String(edge.jacket_color).trim().toUpperCase();
      return { code, css: wireColorCss(code) };
    }
    const conduitCode = conduitColorForCableEdge(edge);
    if (conduitCode) {
      return { code: conduitCode, css: wireColorCss(conduitCode) };
    }
    return { code: null, css: canvasBackgroundCss() };
  }

  /** Conduit tube rim only when the tube would blend into the canvas. */
  function needsTubeContrastRim(tubeCss) {
    return needsNestedContrastRim(null, null, tubeCss, canvasBackgroundCss());
  }

  /** Conduit color code for a cable edge (first hop / single conduit). */
  function conduitColorForCableEdge(edge) {
    if (!edge || !graph) return null;
    const hops = edge.conduit_hops || [];
    const cid = hops.length ? hops[0].conduit : edge.conduit;
    if (!cid) return null;
    const ce = (graph.edges || []).find((e) => e && e.id === cid);
    const c = ce && ce.color;
    return c != null && String(c).trim() !== "" ? String(c).trim().toUpperCase() : null;
  }

  /** Thin rim under a stroke so same-color nesting stays visible. */
  function appendContrastRim(parent, d, fillCss, width, className) {
    if (!parent || !d || !(width > 0)) return null;
    const rim = el("path", { class: className || "contrast-rim", d });
    rim.style.stroke = contrastOutlineCss(fillCss);
    rim.style.strokeWidth = String(width + OUTLINE_EXTRA);
    rim.style.fill = "none";
    rim.style.strokeOpacity = "0.85";
    rim.style.strokeLinecap = "round";
    rim.style.strokeLinejoin = "round";
    parent.appendChild(rim);
    return rim;
  }

  function applyTubeOutlineVisibility(outlineEl, tubeCss, roadW) {
    if (!outlineEl) return;
    if (needsTubeContrastRim(tubeCss)) {
      outlineEl.style.stroke = contrastOutlineCss(tubeCss);
      outlineEl.style.strokeWidth = String(roadW + OUTLINE_EXTRA);
      outlineEl.style.strokeOpacity = "0.95";
      outlineEl.style.display = "";
    } else {
      outlineEl.style.strokeOpacity = "0";
      outlineEl.style.display = "none";
    }
  }

  function cableWireIndices(edge) {
    const colors = edge.colors || [];
    const raw = edge.via_indices || [];
    /** @type {number[]} */
    let indices = [];
    if (raw.length) {
      for (const v of raw) {
        const i = Number(v) - 1;
        if (Number.isFinite(i) && i >= 0) indices.push(i);
      }
    } else if (colors.length) {
      indices = colors.map((_, i) => i);
    } else {
      indices = [0];
    }
    // Unique, stable order.
    return [...new Set(indices)].sort((a, b) => a - b);
  }

  /** Paint broad cables first so nested / narrower cables remain visible. */
  function cablePaintOrder(edges) {
    return [...(edges || [])].sort((a, b) => {
      const width = cableWireIndices(b).length - cableWireIndices(a).length;
      if (width) return width;
      return String(a.id || "").localeCompare(String(b.id || ""));
    });
  }

  /** Keep all cables below all conductors, independent of cable paint order. */
  function orderCableLayers(cablesG) {
    if (!cablesG) return;
    const children = [...cablesG.children];
    const jackets = children.filter((el) =>
      [...el.classList].some((name) => name.startsWith("cable-jacket"))
    );
    const strands = children.filter((el) => !jackets.includes(el));
    for (const el of [...jackets, ...strands]) cablesG.appendChild(el);
  }

  function laneOffset(laneIndex, laneCount) {
    return highwayLaneOffset(laneIndex, laneCount);
  }

  /** Point as ``{x,y}`` from ``[x,y]``. */
  function xyOf(pt) {
    if (Array.isArray(pt)) return { x: pt[0], y: pt[1] };
    return { x: pt.x, y: pt.y };
  }

  /** Count direction changes in an orthogonal polyline. */
  function orthoBendCount(pts) {
    let b = 0;
    for (let i = 2; i < pts.length; i++) {
      const ax = pts[i - 1][0] - pts[i - 2][0];
      const ay = pts[i - 1][1] - pts[i - 2][1];
      const bx = pts[i][0] - pts[i - 1][0];
      const by = pts[i][1] - pts[i - 1][1];
      if (Math.abs(ax * by - ay * bx) > 1e-6) b += 1;
    }
    return b;
  }

  /** Route from an element attach to a lane-join point (inbox stub + ortho). */
  function routeAttachToJoin(attach, join, preferCenter) {
    const face = attach.face || "N";
    const fo = faceOutwardDelta(face);
    const j = xyOf(join);
    const aStub = stubPoint(
      attach,
      fo.x,
      fo.y,
      stubDistToToward(attach, fo, j)
    );
    // Prefer fewest bends (stub included); break ties with preferCenter.
    const candidates = [];
    if (
      Math.abs(aStub.x - j.x) < 1e-6 ||
      Math.abs(aStub.y - j.y) < 1e-6
    ) {
      candidates.push([
        [aStub.x, aStub.y],
        [j.x, j.y],
      ]);
    } else {
      candidates.push(
        [
          [aStub.x, aStub.y],
          [j.x, aStub.y],
          [j.x, j.y],
        ],
        [
          [aStub.x, aStub.y],
          [aStub.x, j.y],
          [j.x, j.y],
        ]
      );
    }
    let mid = candidates[0];
    let bestBends = Infinity;
    let bestPref = Infinity;
    for (const c of candidates) {
      const full = [[attach.x, attach.y], ...c];
      const bends = orthoBendCount(full);
      let pref = 0;
      if (preferCenter && c.length >= 3) {
        const corner = c[1];
        pref = Math.hypot(corner[0] - preferCenter.x, corner[1] - preferCenter.y);
      }
      if (
        bends < bestBends ||
        (bends === bestBends && pref < bestPref)
      ) {
        bestBends = bends;
        bestPref = pref;
        mid = c;
      }
    }
    /** @type {number[][]} */
    const pts = [[attach.x, attach.y]];
    for (const p of mid) pts.push(p);
    /** @type {number[][]} */
    const clean = [];
    for (const p of pts) {
      const prev = clean[clean.length - 1];
      if (prev && Math.hypot(prev[0] - p[0], prev[1] - p[1]) < 1e-6) continue;
      clean.push(p);
    }
    return clean;
  }

  /** Pin id for strand ``wi`` (falls back to edge.from_pin / to_pin). */
  function cableWirePin(edge, wi, end) {
    const arr = end === "from" ? edge.from_pins : edge.to_pins;
    if (Array.isArray(arr) && arr.length) {
      const p = arr[wi] != null ? arr[wi] : arr[0];
      if (p != null && String(p) !== "") return p;
    }
    return end === "from" ? edge.from_pin : edge.to_pin;
  }

  function cableRouteKey(edge, elemById) {
    const hops = edge.conduit_hops;
    if (hops && hops.length) {
      return hops.map((h) => h.conduit || "").join(">");
    }
    if (edge.conduit) return String(edge.conduit);
    const a = elemById[edge.from];
    const b = elemById[edge.to];
    if (a?.parent && b?.parent && a.parent === b.parent) {
      return `box:${a.parent}`;
    }
    return `cable:${cableEdgeKey(edge)}`;
  }

  /**
   * Global terminal slots (per pin cell) and highway lane indices.
   *
   * Lanes are packed **per conduit** (wires that share that tube). End-to-end
   * route keys left multi-hop cables with different hop sequences each on
   * lane 0 while the tube width still counted every wire — fat empty tubes
   * with strands stacked on the centerline.
   */
  function buildCableLayout(cableEdges, elemById, placeById) {
    /** @type {Map<string, {key:string, wi:number, end:string}[]>} */
    const byTerminal = new Map();
    /** @type {Map<string, {key:string, wi:number, ax:number, ay:number, bx:number, by:number}[]>} */
    const byConduit = new Map();
    /** @type {Map<string, {key:string, wi:number, ax:number, ay:number, bx:number, by:number}[]>} */
    const byRoute = new Map();
    /** @type {Map<string, Map<string, Set<string>>>} */
    const jacketsByConduit = new Map();

    function towardForEnd(edge, end, a, b) {
      const hops = edge.conduit_hops;
      if (hops && hops.length) {
        const hop = end === "from" ? hops[0] : hops[hops.length - 1];
        const place = placeById[end === "from" ? hop.from : hop.to];
        const oid = end === "from" ? hop.from_opening : hop.to_opening;
        if (place && oid) {
          return openingMouthAbs(place, oid, oid?.[0], placeById);
        }
      }
      if (edge.from_opening && edge.to_opening && edge.conduit_from && edge.conduit_to) {
        const place = placeById[end === "from" ? edge.conduit_from : edge.conduit_to];
        const oid = end === "from" ? edge.from_opening : edge.to_opening;
        if (place && oid) {
          return openingMouthAbs(place, oid, oid?.[0], placeById);
        }
      }
      return elementCenter(end === "from" ? b : a, placeById);
    }

    function conduitIdsForEdge(edge) {
      const hops = edge.conduit_hops;
      if (hops && hops.length) {
        return [...new Set(hops.map((h) => h.conduit).filter(Boolean))];
      }
      if (edge.conduit) return [String(edge.conduit)];
      return [];
    }

    /**
     * @param {Map<string, {key:string, wi:number, ax:number, ay:number, bx:number, by:number}[]>} groups
     * @param {(item: {key:string, wi:number}, index:number, count:number, groupKey:string) => void} assign
     */
    function packLaneGroups(groups, assign) {
      for (const [groupKey, list] of groups) {
        /** @type {Map<string, typeof list>} */
        const byCable = new Map();
        for (const it of list) {
          if (!byCable.has(it.key)) byCable.set(it.key, []);
          byCable.get(it.key).push(it);
        }
        const cableKeys = [...byCable.keys()];
        const cableScore = (ck) => {
          const members = byCable.get(ck) || [];
          const xs = members.map((it) => (it.ax + it.bx) / 2);
          const ys = members.map((it) => (it.ay + it.by) / 2);
          return {
            x: xs.reduce((s, v) => s + v, 0) / Math.max(1, xs.length),
            y: ys.reduce((s, v) => s + v, 0) / Math.max(1, ys.length),
          };
        };
        const scores = Object.fromEntries(
          cableKeys.map((k) => [k, cableScore(k)])
        );
        const xs = cableKeys.map((k) => scores[k].x);
        const ys = cableKeys.map((k) => scores[k].y);
        const xSpan = Math.max(...xs) - Math.min(...xs);
        const ySpan = Math.max(...ys) - Math.min(...ys);
        cableKeys.sort((ka, kb) => {
          const a = scores[ka];
          const b = scores[kb];
          if (xSpan >= ySpan) {
            if (Math.abs(a.x - b.x) > 1e-3) return a.x - b.x;
            if (Math.abs(a.y - b.y) > 1e-3) return a.y - b.y;
          } else {
            if (Math.abs(a.y - b.y) > 1e-3) return a.y - b.y;
            if (Math.abs(a.x - b.x) > 1e-3) return a.x - b.x;
          }
          return ka < kb ? -1 : ka > kb ? 1 : 0;
        });
        /** @type {typeof list} */
        const ordered = [];
        for (const ck of cableKeys) {
          const members = byCable.get(ck) || [];
          members.sort((u, v) => u.wi - v.wi);
          ordered.push(...members);
        }
        const count = ordered.length;
        ordered.forEach((item, index) => assign(item, index, count, groupKey));
      }
    }

    for (const edge of cableEdges || []) {
      const a = elemById[edge.from];
      const b = elemById[edge.to];
      if (!a || !b) continue;
      const key = cableEdgeKey(edge);
      const wires = cableWireIndices(edge);
      const towardFrom = towardForEnd(edge, "from", a, b);
      const towardTo = towardForEnd(edge, "to", a, b);
      for (const wi of wires) {
        const fromPin = cableWirePin(edge, wi, "from");
        const toPin = cableWirePin(edge, wi, "to");
        const attFrom = resolveElementAttach(a, fromPin, towardFrom, placeById);
        const attTo = resolveElementAttach(b, toPin, towardTo, placeById);
        for (const end of /** @type {const} */ (["from", "to"])) {
          const elem = end === "from" ? a : b;
          const toward = end === "from" ? towardFrom : towardTo;
          const pin = end === "from" ? fromPin : toPin;
          const cell =
            pickPinCell(elem, pin, toward, placeById) ||
            (pin && cellIdOnElementGrid(elem, pin) ? String(pin) : null);
          const tk = cell
            ? `${elem.id}|cell:${cell}`
            : `${elem.id}|face:${elementAttachFace(elem, toward, placeById)}`;
          if (!byTerminal.has(tk)) byTerminal.set(tk, []);
          byTerminal.get(tk).push({ key, wi, end });
        }
        const entry = {
          key,
          wi,
          ax: attFrom.x,
          ay: attFrom.y,
          bx: attTo.x,
          by: attTo.y,
        };
        for (const cid of conduitIdsForEdge(edge)) {
          if (!byConduit.has(cid)) byConduit.set(cid, []);
          byConduit.get(cid).push({ ...entry });
        }
        const rk = cableRouteKey(edge, elemById);
        if (!byRoute.has(rk)) byRoute.set(rk, []);
        byRoute.get(rk).push(entry);
      }
      for (const cid of conduitIdsForEdge(edge)) {
        // A cable can have conductors terminating on different element
        // pairs. They become separate cable edges to preserve their landing
        // pins, but must share one jacket while they ride this conduit.
        if (!edge.jacket_color) continue;
        if (!jacketsByConduit.has(cid)) jacketsByConduit.set(cid, new Map());
        const byCable = jacketsByConduit.get(cid);
        const cable = String(edge.id || key);
        if (!byCable.has(cable)) byCable.set(cable, new Set());
        byCable.get(cable).add(key);
      }
    }

    /** @type {Map<string, {slot:number, count:number}>} */
    const terminalMap = new Map();
    /** @type {Map<string, number>} */
    const cellCountMap = new Map();
    for (const [tk, list] of byTerminal) {
      list.sort((u, v) =>
        u.key === v.key ? u.wi - v.wi : u.key < v.key ? -1 : 1
      );
      const count = list.length;
      cellCountMap.set(tk, count);
      list.forEach((item, slot) => {
        terminalMap.set(`${item.key}|${item.wi}|${item.end}`, {
          slot: count > 1 ? slot : 0,
          count: count > 1 ? count : 1,
        });
      });
    }

    /** @type {Map<string, {index:number, count:number}>} */
    const conduitLaneMap = new Map();
    /** @type {Map<string, number>} */
    const conduitStrandCounts = new Map();
    packLaneGroups(byConduit, (item, index, count, cid) => {
      conduitLaneMap.set(`${cid}|${item.key}|${item.wi}`, { index, count });
      conduitStrandCounts.set(cid, count);
    });

    /** @type {Map<string, {first:number,last:number,count:number,representative:string}>} */
    const jacketMap = new Map();
    for (const [cid, byCable] of jacketsByConduit) {
      const conduitItems = byConduit.get(cid) || [];
      for (const [cable, keys] of byCable) {
        const lanes = conduitItems
          .filter((item) => keys.has(item.key))
          .map((item) =>
            conduitLaneMap.get(`${cid}|${item.key}|${item.wi}`)
          )
          .filter(Boolean);
        if (!lanes.length) continue;
        const indices = lanes.map((lane) => lane.index);
        jacketMap.set(`${cid}|${cable}`, {
          first: Math.min(...indices),
          last: Math.max(...indices),
          count: lanes[0].count,
          representative: [...keys].sort()[0],
        });
      }
    }

    /** @type {Map<string, {index:number, count:number}>} */
    const routeLaneMap = new Map();
    packLaneGroups(byRoute, (item, index, count) => {
      routeLaneMap.set(`${item.key}|${item.wi}`, { index, count });
    });

    return {
      terminal(edge, wi, end) {
        return (
          terminalMap.get(`${cableEdgeKey(edge)}|${wi}|${end}`) || {
            slot: 0,
            count: 1,
          }
        );
      },
      /** Packed strand count for a conduit highway (0 if nothing rides it). */
      conduitStrandCount(conduitId) {
        if (!conduitId) return 0;
        return conduitStrandCounts.get(String(conduitId)) || 0;
      },
      /** Cables attached to one face-cell (``elemId|cell:N1``) or face bucket. */
      cellCableCount(elemId, cellId) {
        return (
          cellCountMap.get(`${elemId}|cell:${cellId}`) ||
          cellCountMap.get(`${elemId}|face:${String(cellId || "")[0]}`) ||
          0
        );
      },
      /** Same-box / no-conduit fallback (route bucket). */
      lane(edge, wi) {
        return (
          routeLaneMap.get(`${cableEdgeKey(edge)}|${wi}`) || {
            index: 0,
            count: 1,
          }
        );
      },
      /** Highway lane among wires that share ``conduitId``. */
      laneOnConduit(conduitId, edge, wi) {
        if (!conduitId) return this.lane(edge, wi);
        return (
          conduitLaneMap.get(`${conduitId}|${cableEdgeKey(edge)}|${wi}`) || {
            index: 0,
            count: 1,
          }
        );
      },
      jacketOnConduit(conduitId, edge) {
        if (!conduitId) return null;
        return jacketMap.get(`${conduitId}|${edge.id}`) || null;
      },
      isJacketRepresentative(conduitId, edge) {
        const jacket = this.jacketOnConduit(conduitId, edge);
        return !!jacket && jacket.representative === cableEdgeKey(edge);
      },
      jacket(edge) {
        const hops = edge.conduit_hops || [];
        const cid = (hops[0] && hops[0].conduit) || edge.conduit || null;
        return this.jacketOnConduit(cid, edge);
      },
    };
  }

  /**
   * Offset an orthogonal polyline by ``dist`` along the segment normal
   * ``(-dy, dx)``. Corners are re-joined by intersecting offset segment
   * lines so the result stays Manhattan (no diagonal chamfer / fake jog).
   */
  function offsetOrthoPts(pts, dist) {
    if (!pts || pts.length < 2) return pts ? pts.map((p) => [p[0], p[1]]) : [];
    if (Math.abs(dist) < 1e-9) return pts.map((p) => [p[0], p[1]]);
    const src = cleanOrthoPoly(pts.map((p) => [p[0], p[1]]));
    if (src.length < 2) return src;
    /** @type {{ax:number,ay:number,bx:number,by:number,horiz:boolean}[]} */
    const segs = [];
    for (let i = 0; i < src.length - 1; i++) {
      const dx = src[i + 1][0] - src[i][0];
      const dy = src[i + 1][1] - src[i][1];
      const len = Math.hypot(dx, dy) || 1;
      const nx = (-dy / len) * dist;
      const ny = (dx / len) * dist;
      const horiz = Math.abs(dy) < 1e-6;
      segs.push({
        ax: src[i][0] + nx,
        ay: src[i][1] + ny,
        bx: src[i + 1][0] + nx,
        by: src[i + 1][1] + ny,
        horiz,
      });
    }
    /** @type {number[][]} */
    const out = [[segs[0].ax, segs[0].ay]];
    for (let i = 0; i < segs.length - 1; i++) {
      const s0 = segs[i];
      const s1 = segs[i + 1];
      let cx;
      let cy;
      if (s0.horiz && !s1.horiz) {
        cx = s1.ax;
        cy = s0.ay;
      } else if (!s0.horiz && s1.horiz) {
        cx = s0.ax;
        cy = s1.ay;
      } else {
        cx = s0.bx;
        cy = s0.by;
      }
      out.push([cx, cy]);
    }
    const last = segs[segs.length - 1];
    out.push([last.bx, last.by]);
    return cleanOrthoPoly(out);
  }

  /**
   * Parallel offset that must not land inside ``obstacles`` (rule 17).
   * Lane offset of a clear centerline can still shove a strand through an
   * element; if so, re-route between the offset endpoints around the boxes.
   */
  function offsetOrthoPtsClear(pts, dist, obstacles, stayBounds, occupied) {
    if (!pts || pts.length < 2) return pts ? pts.map((p) => [p[0], p[1]]) : [];
    if (Math.abs(dist) < 1e-9) return pts.map((p) => [p[0], p[1]]);
    const off = offsetOrthoPts(pts, dist);
    if (!obstacles || !obstacles.length) return off;
    if (pathObstacleCost(off, obstacles) <= 0) return off;
    const a = off[0];
    const b = off[off.length - 1];
    if (!a || !b) return off;
    const routed = orthoRoute(
      { x: a[0], y: a[1] },
      { x: b[0], y: b[1] },
      null,
      null,
      occupied || null,
      obstacles,
      stayBounds || null,
      null
    );
    // Never return an offset lane that still intersects an element.  The
    // centerline may be clear while the parallel lane cuts through a box.
    return pathObstacleCost(routed, obstacles) <= 0 ? routed : off;
  }

  /** Expand a rect outward by ``pad`` on every side. */
  function inflateObstacleRect(r, pad) {
    const p = Math.max(0, pad || 0);
    return { x: r.x - p, y: r.y - p, w: r.w + 2 * p, h: r.h + 2 * p };
  }

  /** Replace any non-Manhattan segment with an L so paths never paint diagonals. */
  function ensureOrthoPoly(pts) {
    if (!pts || pts.length < 2) return pts ? pts.map((p) => [p[0], p[1]]) : [];
    /** @type {number[][]} */
    const out = [[pts[0][0], pts[0][1]]];
    for (let i = 1; i < pts.length; i++) {
      const prev = out[out.length - 1];
      const p = pts[i];
      if (
        Math.abs(prev[0] - p[0]) < 1e-6 ||
        Math.abs(prev[1] - p[1]) < 1e-6
      ) {
        out.push([p[0], p[1]]);
        continue;
      }
      const mid = simpleOrthoPts(
        { x: prev[0], y: prev[1] },
        { x: p[0], y: p[1] }
      );
      for (let j = 1; j < mid.length; j++) {
        out.push([mid[j][0], mid[j][1]]);
      }
    }
    return cleanOrthoPoly(out);
  }

  /** Max length (px) of a terminal-only diagonal lead into a pin. */
  const TERMINAL_DIAG_MAX = 36;

  /**
   * Push the first offset-spine vertex off the element face.
   * Offsetting a pin-on-face start yields (pin±lane, faceY) — a segment that
   * paints along the regleta border. Lift that point outward first.
   *
   * Multi-cable V (pin→tip diagonal) must not be rewritten to Manhattan —
   * ``ensureOrthoPoly`` would collapse both arms onto the face normal.
   */
  function liftOffsetSpineFromPin(offPts, pin, face, minOut) {
    if (!offPts || offPts.length < 1) {
      return offPts ? offPts.map((p) => [p[0], p[1]]) : [];
    }
    const want = minOut == null ? ELEMENT_FACE_CLEARANCE : minOut;
    const p = {
      x: Array.isArray(pin) ? pin[0] : pin.x,
      y: Array.isArray(pin) ? pin[1] : pin.y,
    };
    const fo = faceOutwardDelta(face);
    /** @type {number[][]} */
    const out = offPts.map((q) => [q[0], q[1]]);
    if (!fo.x && !fo.y) return out;
    // Preserve terminal V: first segment from the pin is already diagonal.
    if (out.length >= 2) {
      const atPin =
        Math.hypot(out[0][0] - p.x, out[0][1] - p.y) < 1.5;
      const diag =
        Math.abs(out[0][0] - out[1][0]) > 1e-6 &&
        Math.abs(out[0][1] - out[1][1]) > 1e-6;
      if (atPin && diag) return out;
    }
    const along =
      (out[0][0] - p.x) * fo.x + (out[0][1] - p.y) * fo.y;
    if (along >= want) return out;
    const need = want - along;
    out[0][0] += fo.x * need;
    out[0][1] += fo.y * need;
    // Lift can make the first segment diagonal — force Manhattan only when
    // we actually moved a non-V spine point (single-cable / offset start).
    return ensureOrthoPoly(out);
  }

  /**
   * Via beside blocking element(s) for a multi-lane inbox skirt (rule 17).
   * Left pins go left of the obstacle, right pins go right; lanes stay pitched.
   */
  function laneSkirtVia(att, tip, crossing, obstacles, laneIndex, laneCount) {
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    let any = false;
    const pad = LANE_PITCH;
    for (const r of obstacles || []) {
      if (!r) continue;
      // Corridor tip→crossing vs rect (axis-aligned bounds test).
      const x0 = Math.min(tip.x, crossing.x) - pad;
      const x1 = Math.max(tip.x, crossing.x) + pad;
      const y0 = Math.min(tip.y, crossing.y) - pad;
      const y1 = Math.max(tip.y, crossing.y) + pad;
      if (r.x + r.w < x0 || r.x > x1 || r.y + r.h < y0 || r.y > y1) continue;
      any = true;
      minX = Math.min(minX, r.x);
      maxX = Math.max(maxX, r.x + r.w);
      minY = Math.min(minY, r.y);
      maxY = Math.max(maxY, r.y + r.h);
    }
    if (!any) {
      return { x: crossing.x, y: crossing.y };
    }
    const cx = (minX + maxX) / 2;
    const n = Math.max(1, laneCount | 0);
    const i = Math.max(0, Math.min(n - 1, laneIndex | 0));
    const margin = LANE_PITCH * 2;
    const goLeft = att.x <= cx;
    const viaX = goLeft
      ? minX - margin - (n - 1 - i) * LANE_PITCH
      : maxX + margin + i * LANE_PITCH;
    let viaY = (minY + maxY) / 2 + (i - (n - 1) / 2) * LANE_PITCH;
    viaY = Math.max(minY - margin, Math.min(maxY + margin, viaY));
    return { x: viaX, y: viaY };
  }

  /**
   * Distinct-pin multi-lane inbox: pin → unique-depth stub toward the mouth,
   * H to the lane column, V to the mouth crossing (≤3 Manhattan segments when
   * clear). When that bus would pierce an element (rule 17), leave the pin
   * outward and skirt beside the obstacle on a lane-unique via.
   */
  function distinctPinLaneBus(
    att,
    face,
    crossing,
    laneDist,
    laneCount,
    laneIndex,
    obstacles
  ) {
    const fo0 = faceOutwardDelta(face);
    let ux = fo0.x;
    let uy = fo0.y;
    const toCx = crossing.x - att.x;
    const toCy = crossing.y - att.y;
    if (ux * toCx + uy * toCy < -1e-6) {
      ux = -ux;
      uy = -uy;
    }
    const n = Math.max(1, laneCount | 0);
    const i = Math.max(
      0,
      Math.min(n - 1, laneIndex != null ? laneIndex | 0 : 0)
    );
    const along = ux * toCx + uy * toCy;
    // Pack unique depths toward the mouth; keep ≥LANE_PITCH clear of the boca
    // so H runs never sit on the mouth latitude.
    let busDepth = TERMINAL_FAN_TIP + (n - 1 - i) * LANE_PITCH;
    if (along > 4) {
      const clear = Math.max(LANE_PITCH * 2, 10);
      const hi = Math.max(6, along - clear);
      const lo = Math.min(
        TERMINAL_FAN_TIP,
        Math.max(6, hi - (n - 1) * LANE_PITCH)
      );
      if (n <= 1) {
        busDepth = Math.min(busDepth, hi);
      } else {
        busDepth = lo + ((n - 1 - i) / (n - 1)) * (hi - lo);
      }
    }
    const rail = stubPoint({ x: att.x, y: att.y }, ux, uy, busDepth);
    /** @type {number[][]} */
    let pts = [
      [att.x, att.y],
      [rail.x, rail.y],
    ];
    const ns = Math.abs(uy) >= Math.abs(ux);
    if (ns) {
      if (Math.abs(rail.x - crossing.x) > 1e-6) {
        pts.push([crossing.x, rail.y]);
      }
      if (Math.abs(rail.y - crossing.y) > 1e-6) {
        pts.push([crossing.x, crossing.y]);
      } else if (pts.length === 2 && Math.abs(rail.x - crossing.x) > 1e-6) {
        pts.push([crossing.x, crossing.y]);
      }
    } else {
      if (Math.abs(rail.y - crossing.y) > 1e-6) {
        pts.push([rail.x, crossing.y]);
      }
      if (Math.abs(rail.x - crossing.x) > 1e-6) {
        pts.push([crossing.x, crossing.y]);
      } else if (pts.length === 2 && Math.abs(rail.y - crossing.y) > 1e-6) {
        pts.push([crossing.x, crossing.y]);
      }
    }
    if (
      Math.hypot(
        pts[pts.length - 1][0] - crossing.x,
        pts[pts.length - 1][1] - crossing.y
      ) > 1e-6
    ) {
      pts.push([crossing.x, crossing.y]);
    }
    pts = cleanOrthoPoly(pts);
    if (!obstacles || !obstacles.length) return pts;
    if (pathObstacleCost(pts, obstacles) <= 0) return pts;

    // Rule 17: leave the pin along the face outward, then skirt the element.
    const foOut = faceOutwardDelta(face);
    let tip = stubPoint(
      { x: att.x, y: att.y },
      foOut.x,
      foOut.y,
      TERMINAL_FAN_TIP
    );
    // If the tip still sits in an obstacle, push further out.
    for (let k = 0; k < 4; k++) {
      let inside = false;
      for (const r of obstacles) {
        if (
          tip.x > r.x &&
          tip.x < r.x + r.w &&
          tip.y > r.y &&
          tip.y < r.y + r.h
        ) {
          inside = true;
          break;
        }
      }
      if (!inside) break;
      tip = stubPoint(tip, foOut.x, foOut.y, LANE_PITCH * 2);
    }
    const via = laneSkirtVia(
      att,
      tip,
      crossing,
      obstacles,
      i,
      n
    );
    const leg1 = orthoRoute(
      tip,
      via,
      null,
      null,
      null,
      obstacles,
      null,
      null
    );
    const leg2 = orthoRoute(
      via,
      { x: crossing.x, y: crossing.y },
      null,
      null,
      null,
      obstacles,
      null,
      null
    );
    /** @type {number[][]} */
    let skirt = [
      [att.x, att.y],
      [tip.x, tip.y],
    ];
    if (leg1 && leg1.length) {
      skirt = mergeOrthoPolys(skirt, leg1) || skirt.concat(leg1);
    } else {
      skirt.push([via.x, via.y]);
    }
    if (leg2 && leg2.length) {
      skirt = mergeOrthoPolys(skirt, leg2) || skirt.concat(leg2);
    } else {
      skirt.push([crossing.x, crossing.y]);
    }
    if (
      Math.hypot(
        skirt[skirt.length - 1][0] - crossing.x,
        skirt[skirt.length - 1][1] - crossing.y
      ) > 1e-6
    ) {
      skirt.push([crossing.x, crossing.y]);
    }
    skirt = cleanOrthoPoly(skirt);
    // A skirt is only a valid repair when it clears every obstacle.  Comparing
    // costs alone accepts a partially improved path that still pierces a box.
    if (
      pathObstacleCost(skirt, obstacles) <= 0 &&
      pathObstacleCost(skirt, obstacles) <= pathObstacleCost(pts, obstacles)
    ) {
      return skirt;
    }
    return pts;
  }

  /**
   * Lead from a terminal pin into a nearby lane point.
   *
   * Rules:
   * - One cable → Manhattan only (optional short stub + L).
   * - Several cables on the same terminal → V: the segment that TOUCHES the
   *   pin is the diagonal (pin→tip). Never stub-then-90° at the pin. After
   *   the tip, Manhattan only (caller bridges tip→spine with orthoJoinEnd).
   */
  function pinToLanePts(pin, face, lanePt, slot = 0, slotCount = 1, sharedPinFan = false) {
    const p = {
      x: Array.isArray(pin) ? pin[0] : pin.x,
      y: Array.isArray(pin) ? pin[1] : pin.y,
    };
    const t = {
      x: Array.isArray(lanePt) ? lanePt[0] : lanePt.x,
      y: Array.isArray(lanePt) ? lanePt[1] : lanePt.y,
    };
    if (Math.hypot(p.x - t.x, p.y - t.y) < 1e-6) return [[p.x, p.y]];
    const fo = faceOutwardDelta(face);
    const nSlots = Math.max(1, slotCount | 0);
    const s = Math.max(0, Math.min(nSlots - 1, slot | 0));
    const multiCable = nSlots > 1;

    if (multiCable && sharedPinFan && (fo.x || fo.y)) {
      // V leg touches the pin: pin → tip (one short diagonal). Opposite slots
      // fan to opposite laterals so both arms of the V are diagonal — never
      // one diagonal and one vertical. A short rail past the tip keeps the
      // strand on its lateral until the spine join (meet only at the pin).
      const nx = -fo.y;
      const ny = fo.x;
      const mid = (nSlots - 1) / 2;
      const fanLat = (s - mid) * TERMINAL_FAN_PITCH;
      const alongToLane =
        (t.x - p.x) * fo.x + (t.y - p.y) * fo.y;
      let tipDepth = TERMINAL_FAN_TIP;
      let railDepth = TERMINAL_FAN_RAIL;
      if (alongToLane > 4) {
        const maxDepth = Math.max(8, alongToLane - 2);
        const want = tipDepth + railDepth;
        if (want > maxDepth) {
          const scale = maxDepth / want;
          tipDepth *= scale;
          railDepth *= scale;
        }
      }
      tipDepth = Math.max(6, tipDepth);
      railDepth = Math.max(4, railDepth);
      const tip = {
        x: p.x + fo.x * tipDepth + nx * fanLat,
        y: p.y + fo.y * tipDepth + ny * fanLat,
      };
      const rail = {
        x: tip.x + fo.x * railDepth,
        y: tip.y + fo.y * railDepth,
      };
      return [
        [p.x, p.y],
        [tip.x, tip.y],
        [rail.x, rail.y],
      ];
    }

    if (multiCable && (fo.x || fo.y)) {
      // Distinct pins + shared tube: unique stub depths, then diagonal to the
      // lane tip (Manhattan H crosses neighbors; same-depth diagonals cross).
      const alongToLane =
        (t.x - p.x) * fo.x + (t.y - p.y) * fo.y;
      let stubDepth =
        Math.max(6, TERMINAL_FAN_TIP * 0.5) + (nSlots - 1 - s) * LANE_PITCH;
      if (alongToLane > 4) {
        stubDepth = Math.min(stubDepth, Math.max(6, alongToLane - 2));
      }
      const rail = stubPoint(p, fo.x, fo.y, stubDepth);
      return [
        [p.x, p.y],
        [rail.x, rail.y],
      ];
    }

    /**
     * Stub only for a single cable. Callers bridge to the lane/fan tip with
     * ``joinLeadToFanTip`` (column-first) or ``joinAvoid`` / ``mergeLeadToSpine``.
     * Completing the join here via ``orthoJoinEnd`` crawls on stub-Y and
     * stacks multi-lane inboxes on one shared horizontal (Route_29).
     */
    /** @type {number[][]} */
    const pts = [[p.x, p.y]];
    if (fo.x || fo.y) {
      const along = (t.x - p.x) * fo.x + (t.y - p.y) * fo.y;
      if (along > 2) {
        const want = Math.min(6, along - 0.5);
        if (want > 1e-6) {
          const stub = stubPoint(p, fo.x, fo.y, want);
          if (Math.hypot(stub.x - p.x, stub.y - p.y) > 1e-6) {
            pts.push([stub.x, stub.y]);
          }
        }
      }
    }
    return pts;
  }

  /**
   * Join a terminal lead (pin→…→rail) to a mouth-fan tip without collapsing
   * onto a shared horizontal at rail-Y (Test_01 y=420 trunk).
   *
   * Default (single cable): column/row-first (N/S → rail.x, E/W → rail.y),
   * then across at the fan-tip latitude.
   *
   * Multi-lane (``hFirst``): H at rail latitude first, then V on the tip
   * column — requires unique rail latitudes (pin V-fan) so H runs do not
   * cross neighbor pin-columns (Route_29).
   * When the simple join would pierce a foreign element (rule 17), detour
   * with ``orthoRoute`` instead.
   */
  function joinLeadToFanTip(lead, fanTip, face, obstacles, hFirst) {
    if (!lead || lead.length < 1) {
      return fanTip ? [[fanTip[0], fanTip[1]]] : [];
    }
    if (!fanTip) return lead.map((p) => [p[0], p[1]]);
    const rail = lead[lead.length - 1];
    if (Math.hypot(rail[0] - fanTip[0], rail[1] - fanTip[1]) < 1e-6) {
      return lead.map((p) => [p[0], p[1]]);
    }
    /** @type {number[][]} */
    const bridge = [[rail[0], rail[1]]];
    const fo = faceOutwardDelta(face || "N");
    const ns = Math.abs(fo.y) >= Math.abs(fo.x);
    if (hFirst) {
      // Diagonal rail → fan tip. Distinct-pin multi-lane cannot Manhattan-H
      // without crossing neighbor pin/lane columns (Route_29).
      bridge.push([fanTip[0], fanTip[1]]);
    } else if (ns) {
      // N/S pin: stay on rail.x down/up to tip.y, then across.
      if (Math.abs(rail[1] - fanTip[1]) > 1e-6) {
        bridge.push([rail[0], fanTip[1]]);
      }
      if (Math.abs(rail[0] - fanTip[0]) > 1e-6) {
        bridge.push([fanTip[0], fanTip[1]]);
      } else if (bridge.length === 1) {
        bridge.push([fanTip[0], fanTip[1]]);
      }
    } else {
      // E/W pin: stay on rail.y across to tip.x, then along.
      if (Math.abs(rail[0] - fanTip[0]) > 1e-6) {
        bridge.push([fanTip[0], rail[1]]);
      }
      if (Math.abs(rail[1] - fanTip[1]) > 1e-6) {
        bridge.push([fanTip[0], fanTip[1]]);
      } else if (bridge.length === 1) {
        bridge.push([fanTip[0], fanTip[1]]);
      }
    }
    const simple = mergeOrthoPolys(lead, bridge) || lead;
    if (obstacles && obstacles.length) {
      const simpleCost = pathObstacleCost(simple, obstacles);
      if (simpleCost > 0) {
        const routed = orthoRoute(
          { x: rail[0], y: rail[1] },
          { x: fanTip[0], y: fanTip[1] },
          null,
          null,
          null,
          obstacles,
          null,
          null
        );
        if (routed && routed.length >= 2) {
          const detour = mergeOrthoPolys(lead, routed) || lead;
          const detourCost = pathObstacleCost(detour, obstacles);
          if (detourCost < simpleCost) {
            return detour;
          }
        }
      }
    }
    return simple;
  }

  /**
   * Join a terminal lead to the offset spine with Manhattan only (no diagonal
   * gap after trimming spine points near the tip).
   */
  function mergeLeadToSpine(lead, spine, face) {
    if (!lead || lead.length < 1) {
      return spine ? spine.map((p) => [p[0], p[1]]) : [];
    }
    if (!spine || spine.length < 1) {
      return lead.map((p) => [p[0], p[1]]);
    }
    const tip = lead[lead.length - 1]; // rail (or tip if no rail)
    const pin = lead[0];
    const vTip = lead.length >= 2 ? lead[1] : tip;
    const fo = faceOutwardDelta(face);
    const latX = -fo.y;
    const latY = fo.x;
    const tipLat =
      (vTip[0] - pin[0]) * latX + (vTip[1] - pin[1]) * latY;
    /** Pick spine join index that avoids ida-y-vuelta / crossing the pin axis. */
    let best = null;
    let bestScore = Infinity;
    const lim = Math.min(spine.length, 12);
    for (let i = 0; i < lim; i++) {
      const join = spine[i];
      const bridge = orthoJoinEnd([tip], join, face);
      /** @type {number[][]} */
      let trial = mergeOrthoPolys(lead, bridge) || [];
      const rest = spine.slice(i);
      trial = mergeOrthoPolys(trial, rest) || trial;
      trial = stripOutAndBack(stripShortZJogs(trial));
      let back = 0;
      for (let k = 2; k < Math.min(trial.length, 10); k++) {
        const ax = trial[k - 1][0] - trial[k - 2][0];
        const ay = trial[k - 1][1] - trial[k - 2][1];
        const bx = trial[k][0] - trial[k - 1][0];
        const by = trial[k][1] - trial[k - 1][1];
        if (Math.abs(ax * by - ay * bx) > 1e-6) continue;
        if (ax * bx + ay * by < -1e-6) back += 1;
      }
      let len = 0;
      for (let k = 1; k < bridge.length; k++) {
        len += Math.hypot(
          bridge[k][0] - bridge[k - 1][0],
          bridge[k][1] - bridge[k - 1][1]
        );
      }
      // Prefer continuing away from the pin after the tip.
      const away =
        (join[0] - tip[0]) * (tip[0] - pin[0]) +
        (join[1] - tip[1]) * (tip[1] - pin[1]);
      // Keep each V arm on its own lateral — do not snap back to pin.x early.
      const joinLat =
        (join[0] - pin[0]) * latX + (join[1] - pin[1]) * latY;
      let latPen = Math.abs(joinLat - tipLat);
      if (Math.abs(tipLat) > 1 && tipLat * joinLat < -1e-6) latPen += 900;
      const score =
        back * 1e5 + len + (away < 0 ? 500 : 0) + latPen * 3 + i * 2;
      if (score < bestScore) {
        bestScore = score;
        best = trial;
      }
    }
    const fallback = stripOutAndBack(
      stripShortZJogs(
        mergeOrthoPolys(
          lead,
          mergeOrthoPolys(orthoJoinEnd([tip], spine[0], face), spine)
        ) || lead
      )
    );
    const picked = best && best.length >= 2 ? best : fallback;
    return preserveTerminalVLead(lead, picked);
  }

  /**
   * If strip/merge collapsed a multi-cable V into a Manhattan stub, put the
   * pin→tip diagonal back so both arms stay diagonal and only meet at the pin.
   */
  function preserveTerminalVLead(lead, chain, protectPts) {
    if (!lead || lead.length < 2 || !chain || chain.length < 2) {
      return chain ? chain.map((p) => [p[0], p[1]]) : [];
    }
    const pin = lead[0];
    const tip = lead[1];
    const leadDiag =
      Math.abs(pin[0] - tip[0]) > 1e-6 && Math.abs(pin[1] - tip[1]) > 1e-6;
    if (!leadDiag) return chain.map((p) => [p[0], p[1]]);
    const c0 = chain[0];
    const c1 = chain[1];
    const chainDiag =
      Math.abs(c0[0] - c1[0]) > 1e-6 && Math.abs(c0[1] - c1[1]) > 1e-6;
    const atPin = Math.hypot(c0[0] - pin[0], c0[1] - pin[1]) < 1.5;
    if (atPin && chainDiag) return chain.map((p) => [p[0], p[1]]);
    // Rebuild: full lead (pin→tip→rail) then Manhattan onto the chain.
    let rest = chain.map((p) => [p[0], p[1]]);
    if (Math.hypot(rest[0][0] - pin[0], rest[0][1] - pin[1]) < 1.5) {
      rest = rest.slice(1);
    }
    const rail = lead[lead.length - 1];
    const bridge = orthoJoinEnd([rail], rest[0] || tip, null);
    // Protect mouths/fans — unprotected stripOutAndBack shortcuts boca converges
    // (Test_01 lamp hop skipped end mouth after V preserve).
    return stripOutAndBack(
      mergeOrthoPolys(lead, mergeOrthoPolys(bridge, rest)) || lead,
      protectPts
    );
  }

  /**
   * Drop spine vertices that sit inside the terminal lead so head+spine
   * do not double-back into a jagged M near the pin.
   */
  function trimSpineAfterLead(spine, leadEnd, minDist = 2) {
    if (!spine || spine.length < 2 || leadEnd == null) {
      return spine ? spine.map((p) => [p[0], p[1]]) : [];
    }
    const ex = Array.isArray(leadEnd) ? leadEnd[0] : leadEnd.x;
    const ey = Array.isArray(leadEnd) ? leadEnd[1] : leadEnd.y;
    /** @type {number[][]} */
    const out = spine.map((p) => [p[0], p[1]]);
    let start = 0;
    while (start < out.length - 1) {
      if (Math.hypot(out[start][0] - ex, out[start][1] - ey) <= minDist) {
        start += 1;
        continue;
      }
      const d0 = Math.hypot(out[start][0] - ex, out[start][1] - ey);
      const d1 = Math.hypot(out[start + 1][0] - ex, out[start + 1][1] - ey);
      if (d0 < 14 && d0 <= d1 + 1e-6) {
        start += 1;
        continue;
      }
      break;
    }
    const trimmed = out.slice(start);
    if (!trimmed.length) return [[ex, ey]];
    return trimmed;
  }

  /**
   * Append a Manhattan path from the polyline end to ``target``.
   * Used at openings (never diagonal). For N/S faces arrive on a vertical;
   * for E/W arrive on a horizontal.
   */
  function orthoJoinEnd(pts, target, face) {
    if (!pts || !pts.length) {
      const t0 = Array.isArray(target) ? target : [target.x, target.y];
      return [[t0[0], t0[1]]];
    }
    /** @type {number[][]} */
    const out = pts.map((p) => [p[0], p[1]]);
    const tx = Array.isArray(target) ? target[0] : target.x;
    const ty = Array.isArray(target) ? target[1] : target.y;
    const last = out[out.length - 1];
    if (Math.hypot(last[0] - tx, last[1] - ty) < 1e-6) {
      return cleanOrthoPoly(out);
    }
    if (Math.abs(last[0] - tx) < 1e-6 || Math.abs(last[1] - ty) < 1e-6) {
      out.push([tx, ty]);
      return cleanOrthoPoly(out);
    }
    const f = String(face || "").toUpperCase();
    if (f === "E" || f === "W") {
      out.push([last[0], ty]);
      out.push([tx, ty]);
    } else {
      // N/S/default: match mouth x first, arrive vertically.
      out.push([tx, last[1]]);
      out.push([tx, ty]);
    }
    return cleanOrthoPoly(out);
  }

  /**
   * Rewrite any diagonal with an endpoint near ``point`` into a Manhattan L.
   * Safety net so openings never keep a funnel snap.
   * ``ignoreNear`` protects terminal V diagonals (do not rewrite near pins).
   */
  function ensureManhattanNearPoint(pts, point, radius = 48, ignoreNear = null) {
    if (!pts || pts.length < 2 || point == null) {
      return pts ? pts.map((p) => [p[0], p[1]]) : [];
    }
    const px = Array.isArray(point) ? point[0] : point.x;
    const py = Array.isArray(point) ? point[1] : point.y;
    const ignore = (ignoreNear || [])
      .map((q) =>
        Array.isArray(q) ? { x: q[0], y: q[1] } : { x: q.x, y: q.y }
      )
      .filter((q) => q && Number.isFinite(q.x));
    const nearIgnore = (a, b) =>
      ignore.some(
        (q) =>
          Math.hypot(a[0] - q.x, a[1] - q.y) <= 36 ||
          Math.hypot(b[0] - q.x, b[1] - q.y) <= 36
      );
    /** @type {number[][]} */
    let out = pts.map((p) => [p[0], p[1]]);
    let changed = true;
    while (changed) {
      changed = false;
      for (let i = 0; i < out.length - 1; i++) {
        const a = out[i];
        const b = out[i + 1];
        const diag =
          Math.abs(a[0] - b[0]) > 1e-6 && Math.abs(a[1] - b[1]) > 1e-6;
        if (!diag) continue;
        const near =
          Math.hypot(a[0] - px, a[1] - py) <= radius ||
          Math.hypot(b[0] - px, b[1] - py) <= radius;
        if (!near) continue;
        if (nearIgnore(a, b)) continue;
        const corner = [b[0], a[1]];
        out = [...out.slice(0, i + 1), corner, ...out.slice(i + 1)];
        changed = true;
        break;
      }
    }
    return cleanOrthoPoly(out);
  }

  /**
   * Mouth → exterior lane join: one cable per opening, Manhattan only.
   */
  function mouthToLanePts(mouth, face, lanePt) {
    const m = {
      x: Array.isArray(mouth) ? mouth[0] : mouth.x,
      y: Array.isArray(mouth) ? mouth[1] : mouth.y,
    };
    const t = {
      x: Array.isArray(lanePt) ? lanePt[0] : lanePt.x,
      y: Array.isArray(lanePt) ? lanePt[1] : lanePt.y,
    };
    if (Math.hypot(m.x - t.x, m.y - t.y) < 1e-6) return [[m.x, m.y]];
    const fo = faceOutwardDelta(face);
    /** @type {number[][]} */
    const pts = [[m.x, m.y]];
    let from = m;
    if (fo.x || fo.y) {
      const along =
        (t.x - m.x) * fo.x + (t.y - m.y) * fo.y;
      if (along > 2) {
        const want = Math.min(INBOX_STUB, along - 0.5);
        if (want > 1e-6) {
          const stub = stubPoint(m, fo.x, fo.y, want);
          pts.push([stub.x, stub.y]);
          from = stub;
        }
      }
    }
    if (Math.hypot(from.x - t.x, from.y - t.y) < 1e-6) return pts;
    if (Math.abs(from.x - t.x) < 1e-6 || Math.abs(from.y - t.y) < 1e-6) {
      pts.push([t.x, t.y]);
      return pts;
    }
    // Never diagonal at openings — pick a single L.
    const hv = [
      [from.x, from.y],
      [t.x, from.y],
      [t.x, t.y],
    ];
    const vh = [
      [from.x, from.y],
      [from.x, t.y],
      [t.x, t.y],
    ];
    const pick =
      Math.hypot(t.x - from.x, 0) <= Math.hypot(0, t.y - from.y) ? hv : vh;
    for (let i = 1; i < pick.length; i++) {
      const q = pick[i];
      const prev = pts[pts.length - 1];
      if (Math.hypot(prev[0] - q[0], prev[1] - q[1]) < 1e-6) continue;
      pts.push([q[0], q[1]]);
    }
    return cleanOrthoPoly(pts);
  }

  /** Remove short Z jogs (two bends with a short middle leg). */
  function stripShortZJogs(pts, maxLeg = 28, protectPts) {
    if (!pts || pts.length < 4) {
      return pts ? pts.map((p) => [p[0], p[1]]) : [];
    }
    const protect = (protectPts || [])
      .map((q) =>
        Array.isArray(q) ? { x: q[0], y: q[1] } : { x: q.x, y: q.y }
      )
      .filter((q) => q && Number.isFinite(q.x));
    const nearProtect = (p) =>
      protect.some((q) => Math.hypot(p[0] - q.x, p[1] - q.y) < 1.5);
    /** @type {number[][]} */
    let out = pts.map((p) => [p[0], p[1]]);
    let changed = true;
    while (changed) {
      changed = false;
      for (let i = 1; i < out.length - 2; i++) {
        const a = out[i - 1];
        const b = out[i];
        const c = out[i + 1];
        const d = out[i + 2];
        if (nearProtect(b) || nearProtect(c) || nearProtect(d)) continue;
        const abx = b[0] - a[0];
        const aby = b[1] - a[1];
        const bcx = c[0] - b[0];
        const bcy = c[1] - b[1];
        const cdx = d[0] - c[0];
        const cdy = d[1] - c[1];
        // Only strip orthogonal Z jogs — never touch terminal V diagonals.
        const abDiag = Math.abs(abx) > 1e-6 && Math.abs(aby) > 1e-6;
        const bcDiag = Math.abs(bcx) > 1e-6 && Math.abs(bcy) > 1e-6;
        const cdDiag = Math.abs(cdx) > 1e-6 && Math.abs(cdy) > 1e-6;
        if (abDiag || bcDiag || cdDiag) continue;
        if (Math.abs(abx * bcy - aby * bcx) < 1e-6) continue;
        if (Math.abs(bcx * cdy - bcy * cdx) < 1e-6) continue;
        const mid = Math.hypot(bcx, bcy);
        if (mid <= 1e-6 || mid > maxLeg) continue;
        const abLen = Math.hypot(abx, aby);
        const cdLen = Math.hypot(cdx, cdy);
        // True Z: short lateral between two longer parallel runs. A long stub
        // then H then short V into the mouth is an L-approach — do not collapse
        // it onto the mouth latitude (Route_30 stacked H at the boca).
        if (abLen <= mid || cdLen <= mid) continue;
        const abH = Math.abs(aby) < 1e-6;
        const cdH = Math.abs(cdy) < 1e-6;
        const bcH = Math.abs(bcy) < 1e-6;
        if (abH !== cdH || abH === bcH) continue;
        // Collapse b-c: connect a→d via one L through a corner that skips the Z.
        const corner = abH ? [d[0], a[1]] : [a[0], d[1]];
        // Do not move a run onto a protected mouth latitude/column.
        if (nearProtect(corner)) continue;
        if (
          protect.some((q) =>
            abH
              ? Math.abs(corner[1] - q.y) < 1e-6
              : Math.abs(corner[0] - q.x) < 1e-6
          )
        ) {
          continue;
        }
        out = [...out.slice(0, i), corner, ...out.slice(i + 2)];
        changed = true;
        break;
      }
    }
    return cleanOrthoPoly(out);
  }

  /**
   * Keep lane-offset highway; join real pins with stub+diagonal only.
   * Trims nothing from the highway — callers must pass offset points that
   * already end at the mouth (not at the pin).
   */
  function rejoinLaneEndsOrtho(pin0, face0, offPts, pin1, face1, slot0, count0, slot1, count1) {
    if (!offPts || offPts.length < 2) {
      return offPts ? offPts.map((p) => [p[0], p[1]]) : [];
    }
    let spine = liftOffsetSpineFromPin(offPts, pin0, face0);
    spine = liftOffsetSpineFromPin(
      spine.slice().reverse(),
      pin1,
      face1
    ).reverse();
    const head = pinToLanePts(
      pin0,
      face0,
      spine[0],
      slot0 || 0,
      count0 || 1
    );
    const tail = pinToLanePts(
      pin1,
      face1,
      spine[spine.length - 1],
      slot1 || 0,
      count1 || 1
    );
    let chain = mergeLeadToSpine(head, spine, face0);
    const tip1 = tail[tail.length - 1];
    while (chain.length >= 2) {
      const b = chain[chain.length - 1];
      if (Math.hypot(b[0] - tip1[0], b[1] - tip1[1]) < 12) {
        chain = chain.slice(0, -1);
        continue;
      }
      break;
    }
    const last = chain[chain.length - 1];
    chain = mergeOrthoPolys(chain, orthoJoinEnd([last], tip1, face1));
    chain = mergeOrthoPolys(chain, tail.slice().reverse());
    return stripShortZJogs(stripOutAndBack(chain || []));
  }

  function pathDToSubpaths(d) {
    /** @type {number[][][]} */
    const subs = [];
    const re = /M\s*([-\d.]+)(?:\s+|,)([-\d.]+)([^M]*)/gi;
    let m;
    while ((m = re.exec(String(d || "")))) {
      /** @type {number[][]} */
      const pts = [[Number(m[1]), Number(m[2])]];
      const rest = m[3] || "";
      const lr = /L\s*([-\d.]+)(?:\s+|,)([-\d.]+)/gi;
      let lm;
      while ((lm = lr.exec(rest))) {
        pts.push([Number(lm[1]), Number(lm[2])]);
      }
      if (pts.length >= 2) subs.push(pts);
    }
    return subs;
  }

  /**
   * In-box hop tail (centerline): element → (B/F plane cell) → mouth.
   * Always Manhattan between mouth/plane and the pin stub — diagonals are
   * applied later only as a short multi-cable V at the terminal (never at
   * openings: one cable per opening → Manhattan only).
   * @returns {number[][]|null}
   */
  function hopEndpointTailPts(
    elem,
    place,
    openingId,
    placeById,
    slot = 0,
    slotCount = 1,
    pin = null,
    mouthOverride = null
  ) {
    if (!elem || !place || !openingId) return null;
    if (elem.parent && place.id && elem.parent !== place.id) return null;
    const plane = parsePlaneOpening(openingId);
    const entry = isPlaneOpeningId(openingId)
      ? planeContourEntryAbs(place, openingId, openingId?.[0], placeById)
      : openingMouthAbs(place, openingId, openingId?.[0], placeById);
    const mouth =
      mouthOverride != null
        ? {
            x: Array.isArray(mouthOverride) ? mouthOverride[0] : mouthOverride.x,
            y: Array.isArray(mouthOverride) ? mouthOverride[1] : mouthOverride.y,
          }
        : entry;
    const planePt = plane
      ? openingAnchorAbs(place, openingId, openingId?.[0], placeById)
      : mouth;
    const opFace = routeFace(place, openingId, openingId?.[0], placeById);
    const attach = resolveElementAttach(
      elem,
      pin,
      planePt,
      placeById,
      slot,
      slotCount
    );
    const placeAbs = absXY(place, placeById);
    const prefer = {
      x: placeAbs.x + nodeW(place) / 2,
      y: placeAbs.y + nodeH(place) / 2,
    };
    const attachFace =
      attach.face || elementAttachFace(elem, planePt, placeById);
    if (plane) {
      const viaPlane = inboxRoutePts(
        attach,
        attachFace,
        planePt,
        opFace,
        prefer,
        "element"
      );
      if (Math.hypot(planePt.x - mouth.x, planePt.y - mouth.y) < 1.5) {
        return viaPlane;
      }
      return mergeOrthoPolys(viaPlane, orthoPtsPrefer(planePt, mouth, prefer));
    }
    return inboxRoutePts(
      attach,
      attachFace,
      mouth,
      opFace,
      prefer,
      "opening"
    );
  }

  /** Merge orthogonal polylines; drop duplicated joint vertex. */
  function mergeOrthoPolys(a, b) {
    if (!a || a.length < 2) return b && b.length >= 2 ? b.map((p) => [p[0], p[1]]) : null;
    if (!b || b.length < 2) return a.map((p) => [p[0], p[1]]);
    /** @type {number[][]} */
    const out = a.map((p) => [p[0], p[1]]);
    for (const p of b) {
      const prev = out[out.length - 1];
      if (prev && Math.hypot(prev[0] - p[0], prev[1] - p[1]) < 1e-6) continue;
      out.push([p[0], p[1]]);
    }
    return out.length >= 2 ? out : null;
  }

  /**
   * Short path from a place opening through the mouth to an exterior lane join.
   * One cable per opening — Manhattan only (no diagonals / V).
   */
  function mouthBridgePts(place, openingId, join, placeById) {
    if (!place || !openingId || join == null) return null;
    const op = openingMouthAbs(place, openingId, openingId?.[0], placeById);
    const j = xyOf(join);
    if (Math.hypot(j.x - op.x, j.y - op.y) < 1.5) {
      return [
        [op.x, op.y],
        [j.x, j.y],
      ];
    }
    const exitFace = routeFace(place, openingId, openingId?.[0], placeById);
    return mouthToLanePts(op, exitFace, j);
  }

  /**
   * Element → opening (interior) → exterior lane join.
   * @returns {number[][]|null}
   */
  function hopTailViaOpening(
    elem,
    place,
    openingId,
    exteriorJoin,
    placeById,
    slot,
    slotCount,
    pin
  ) {
    const inbox = hopEndpointTailPts(
      elem,
      place,
      openingId,
      placeById,
      slot,
      slotCount,
      pin
    );
    const bridge = mouthBridgePts(place, openingId, exteriorJoin, placeById);
    if (inbox && bridge) return mergeOrthoPolys(inbox, bridge);
    if (inbox) return inbox;
    if (bridge) {
      // No in-box element route — at least exit through the mouth.
      const attach = resolveElementAttach(
        elem,
        pin,
        openingAnchorAbs(place, openingId, openingId?.[0], placeById),
        placeById,
        slot,
        slotCount
      );
      return mergeOrthoPolys(
        [
          [attach.x, attach.y],
          [bridge[0][0], bridge[0][1]],
        ],
        bridge
      );
    }
    return null;
  }

  /**
   * Drop polyline runs that cut through leaf places so cable overlays do not
   * paint a green lattice inside junction boxes when a tube route misbehaves.
   */
  function exteriorPathD(d, obstacles) {
    if (!d) return null;
    if (!obstacles || !obstacles.length) return d;
    const pts = pathDToPoints(d);
    if (pts.length < 2) return d;
    let out = "";
    /** @type {number[][]} */
    let run = [];
    const flush = () => {
      if (run.length >= 2) {
        const piece = pointsToPathD(run);
        out = out ? `${out} ${piece}` : piece;
      }
      run = [];
    };
    for (let i = 1; i < pts.length; i++) {
      const a = pts[i - 1];
      const b = pts[i];
      if (pathObstacleCost([a, b], obstacles) > 0) {
        flush();
        continue;
      }
      if (!run.length) run.push(a);
      run.push(b);
    }
    flush();
    return out || null;
  }

  /** Exact tube geometry for a hop (anchor core — parallel lanes, not painted caps).
   *  ``reversed`` is true when the hop runs opposite the conduit edge from→to;
   *  callers must negate laneDist in that case so offsetOrthoPts normals stay
   *  on the same world side of the tube.
   */
  function hopTubePathInfo(hop) {
    const item =
      (hop.conduit && edgePathsByConduitId.get(hop.conduit)) ||
      edgePaths.find((e) => e.edge && e.edge.id === hop.conduit);
    if (!item || !item.d) return null;
    const e = item.edge;
    if (e.from === hop.from && e.to === hop.to) {
      return { d: item.d, reversed: false };
    }
    if (e.from === hop.to && e.to === hop.from) {
      return { d: reversePathD(item.d), reversed: true };
    }
    return null;
  }

  /** @deprecated use hopTubePathInfo */
  function hopTubePathD(hop) {
    const info = hopTubePathInfo(hop);
    return info ? info.d : null;
  }

  /**
   * Base polylines for a cable edge.
   * @param {{fromSlot?:{slot:number,count:number}, toSlot?:{slot:number,count:number}, laneDist?:number, laneIndex?:number, laneCount?:number, laneDistForConduit?:(conduitId:string)=>number, fromPin?:string|null, toPin?:string|null}|undefined} opts
   * @returns {number[][][]}
   */
  function cableBaseSubpaths(edge, placeById, elemById, occupied, opts) {
    const a = elemById[edge.from];
    const b = elemById[edge.to];
    if (!a || !b) return [];
    const c1 = elementCenter(a, placeById);
    const c2 = elementCenter(b, placeById);
    const fromSlot = opts?.fromSlot || { slot: 0, count: 1 };
    const toSlot = opts?.toSlot || { slot: 0, count: 1 };
    const laneDistFallback = opts?.laneDist ?? 0;
    const laneCountHint = Math.max(
      1,
      fromSlot.count | 0,
      toSlot.count | 0,
      opts?.laneCount | 0
    );
    const laneIndexHint = Math.max(
      0,
      Math.min(
        laneCountHint - 1,
        opts?.laneIndex != null ? opts.laneIndex | 0 : fromSlot.slot | 0
      )
    );
    const laneDistForConduit = opts?.laneDistForConduit;
    const fromPin = opts?.fromPin != null ? opts.fromPin : edge.from_pin;
    const toPin = opts?.toPin != null ? opts.toPin : edge.to_pin;
    const laneDistFor = (conduitId) => {
      if (conduitId && typeof laneDistForConduit === "function") {
        const d = laneDistForConduit(conduitId);
        return d == null || Number.isNaN(d) ? 0 : d;
      }
      return laneDistFallback;
    };
    /** Full parallel offset of a polyline (stays parallel to conduit walls). */
    const parallel = (pts, dist = laneDistFallback, obs = null) => {
      if (!pts || pts.length < 2 || Math.abs(dist) < 1e-9) {
        return pts ? pts.map((p) => [p[0], p[1]]) : [];
      }
      if (obs && obs.length) {
        return offsetOrthoPtsClear(pts, dist, obs, null, occupied);
      }
      return offsetOrthoPts(pts, dist);
    };

    // Same box: corridor between stubs, skirting foreign elements (rule 17).
    if (a.parent && b.parent && a.parent === b.parent) {
      const p1 = resolveElementAttach(
        a,
        fromPin,
        c2,
        placeById,
        fromSlot.slot,
        fromSlot.count
      );
      const p2 = resolveElementAttach(
        b,
        toPin,
        c1,
        placeById,
        toSlot.slot,
        toSlot.count
      );
      const parent = placeById[a.parent];
      /** @type {{x:number,y:number,w:number,h:number}|null} */
      let stayBounds = null;
      if (parent) {
        const pa = absXY(parent, placeById);
        const origin = contentOriginLocal(parent);
        const fr = frontRectLocal(parent);
        stayBounds = {
          x: pa.x + origin.x,
          y: pa.y + origin.y,
          w: Math.max(4, fr.w - 2 * PAD),
          h: Math.max(4, fr.h - HEADER - PAD),
        };
      }
      const f1 = p1.face || elementAttachFace(a, c2, placeById);
      const f2 = p2.face || elementAttachFace(b, c1, placeById);
      const o1 = faceOutwardDelta(f1);
      const o2 = faceOutwardDelta(f2);
      // Keep centerline clear enough that ±laneDist parallel cannot shove a
      // strand through the from/to body (common bipolar overlap on IGA/ID).
      const laneClear =
        Math.abs(laneDistFallback) + LANE_GAP + STRAND_WIDTH;
      const stubDepth1 = Math.max(
        inboxStubDepth(fromSlot.count),
        laneClear + 6
      );
      const stubDepth2 = Math.max(
        inboxStubDepth(toSlot.count),
        laneClear + 6
      );
      const s1 = stubPoint(p1, o1.x, o1.y, stubDepth1);
      const s2 = stubPoint(p2, o2.x, o2.y, stubDepth2);
      // Foreign boxes: inflate so lane-parallel offsets stay clear (rule 17).
      // Endpoint boxes: pad by laneClear so parallel of a skimming centerline
      // cannot pierce the body; stubs sit beyond that pad.
      const foreignObs = elementObstacles(elemById, placeById, [a.id, b.id], 2);
      const endObs = [];
      for (const e of [a, b]) {
        if (!e) continue;
        const ea = elementAbsXY(e, placeById);
        const pad = 2;
        const w = (e.w ?? ELEM_W) - 2 * pad;
        const h = (e.h ?? ELEM_H) - 2 * pad;
        if (w < 4 || h < 4) continue;
        endObs.push(
          inflateObstacleRect({ x: ea.x + pad, y: ea.y + pad, w, h }, laneClear)
        );
      }
      const lanePad = LANE_GAP + STRAND_WIDTH;
      const inflatedObs = foreignObs
        .map((r) => ({
          x: r.x - lanePad,
          y: r.y - lanePad,
          w: r.w + 2 * lanePad,
          h: r.h + 2 * lanePad,
        }))
        .concat(endObs);
      // Inbox element clearance (rule 17) outranks prior tube occupation.
      const corridor = orthoRoute(
        s1,
        s2,
        null,
        null,
        occupied,
        inflatedObs,
        stayBounds,
        null
      );
      const corridorOff = offsetOrthoPtsClear(
        corridor.map((p) => [p[0], p[1]]),
        laneDistFallback,
        inflatedObs,
        stayBounds,
        occupied
      );
      if (!corridorOff.length) return [];
      // Do not run stripOutAndBack on obstacle detours — it collapses the
      // C-around-element back into a straight pierce (rule 17).
      const head = pinToLanePts(
        [p1.x, p1.y],
        f1,
        corridorOff[0],
        fromSlot.slot,
        fromSlot.count
      );
      const tail = pinToLanePts(
        [p2.x, p2.y],
        f2,
        corridorOff[corridorOff.length - 1],
        toSlot.slot,
        toSlot.count
      );
      const joinAvoid = (fromPt, toPt) =>
        orthoRoute(
          { x: fromPt[0], y: fromPt[1] },
          { x: toPt[0], y: toPt[1] },
          null,
          null,
          occupied,
          inflatedObs,
          stayBounds,
          null
        );
      let chain = head.map((p) => [p[0], p[1]]);
      const hEnd = chain[chain.length - 1];
      const c0 = corridorOff[0];
      if (
        hEnd &&
        c0 &&
        Math.hypot(hEnd[0] - c0[0], hEnd[1] - c0[1]) > 1e-6
      ) {
        chain = mergeOrthoPolys(chain, joinAvoid(hEnd, c0)) || chain;
      }
      chain = mergeOrthoPolys(chain, corridorOff) || chain;
      const c1pt = corridorOff[corridorOff.length - 1];
      const tip = tail[tail.length - 1];
      if (
        c1pt &&
        tip &&
        Math.hypot(c1pt[0] - tip[0], c1pt[1] - tip[1]) > 1e-6
      ) {
        chain = mergeOrthoPolys(chain, joinAvoid(c1pt, tip)) || chain;
      }
      chain = mergeOrthoPolys(chain, tail.slice().reverse()) || chain;
      return [cleanOrthoPoly(chain || [])];
    }

    const parentExclude = [a.parent, b.parent].filter(Boolean);
    const outsideObstacles = placeObstacles(placeById, parentExclude);
    const leafObstacles = placeObstacles(placeById, [], 2);
    // Free-space legs skirt all elements, including endpoints (rule 17).
    const freeObstacles = outsideObstacles.concat(
      elementObstacles(elemById, placeById, null, 2)
    );

    let hops = edge.conduit_hops;
    if ((!hops || !hops.length) && edge.conduit && edge.conduit_from && edge.conduit_to) {
      hops = [
        {
          conduit: edge.conduit,
          from: edge.conduit_from,
          to: edge.conduit_to,
          from_opening: edge.from_opening,
          to_opening: edge.to_opening,
        },
      ];
    }
    if (hops && hops.length) {
      const first = hops[0];
      const last = hops[hops.length - 1];
      const startPlace = placeById[first.from];
      const endPlace = placeById[last.to];
      if (
        !startPlace ||
        !endPlace ||
        !first.from_opening ||
        !last.to_opening
      ) {
        const d = orthoPathD(c1, c2, null, null, occupied, freeObstacles);
        return d
          ? pathDToSubpaths(d).map((sub) =>
              ensureOrthoPoly(parallel(sub, laneDistFallback, freeObstacles))
            )
          : [];
      }

      /** @type {number[][][]} */
      const exteriors = [];
      for (let i = 0; i < hops.length; i++) {
        const hop = hops[i];
        const pf = placeById[hop.from];
        const pt = placeById[hop.to];
        if (!pf || !pt || !hop.from_opening || !hop.to_opening) {
          const d = orthoPathD(c1, c2, null, null, occupied, freeObstacles);
          return d
            ? pathDToSubpaths(d).map((sub) =>
                ensureOrthoPoly(parallel(sub, laneDistFallback, freeObstacles))
              )
            : [];
        }
        const tubeInfo = hopTubePathInfo(hop);
        let ext = null;
        if (tubeInfo) {
          // Keep the conduit centerline intact. ``exteriorPathD`` drops any
          // segment that skims a place border and was truncating bocas
          // (Test_01 lamp vertical never reached the painted tube end).
          ext = tubeInfo.d;
        } else {
          const opA = isPlaneOpeningId(hop.from_opening)
            ? planeContourEntryAbs(
                pf,
                hop.from_opening,
                hop.from_opening?.[0],
                placeById
              )
            : openingMouthAbs(
                pf,
                hop.from_opening,
                hop.from_opening?.[0],
                placeById
              );
          const opB = isPlaneOpeningId(hop.to_opening)
            ? planeContourEntryAbs(
                pt,
                hop.to_opening,
                hop.to_opening?.[0],
                placeById
              )
            : openingMouthAbs(
                pt,
                hop.to_opening,
                hop.to_opening?.[0],
                placeById
              );
          const fromFace = routeFace(
            pf,
            hop.from_opening,
            hop.from_opening?.[0],
            placeById
          );
          const toFace = routeFace(
            pt,
            hop.to_opening,
            hop.to_opening?.[0],
            placeById
          );
          const routed = orthoRoute(
            opA,
            opB,
            fromFace,
            toFace,
            null,
            placeObstacles(placeById, []),
            null,
            placeBorderRects(placeById)
          );
          ext = exteriorPathD(pointsToPathD(routed), leafObstacles);
        }
        if (ext) {
          // Offset each hop with that conduit's local lane pack (not one
          // end-to-end laneDist for the whole multi-hop chain).
          // Reversed hops flip segment normals in offsetOrthoPts — negate
          // so lanes keep a stable world-side of the tube (avoids stacking
          // some strands and leaving empty slots for others).
          let hopDist = laneDistFor(hop.conduit);
          if (tubeInfo && tubeInfo.reversed) hopDist = -hopDist;
          for (const sub of pathDToSubpaths(ext)) {
            if (sub.length >= 2) {
              exteriors.push(parallel(sub.map((p) => [p[0], p[1]]), hopDist));
            }
          }
        }
      }

      const startOp = isPlaneOpeningId(first.from_opening)
        ? planeContourEntryAbs(
            startPlace,
            first.from_opening,
            first.from_opening?.[0],
            placeById
          )
        : openingMouthAbs(
            startPlace,
            first.from_opening,
            first.from_opening?.[0],
            placeById
          );
      const endOp = isPlaneOpeningId(last.to_opening)
        ? planeContourEntryAbs(
            endPlace,
            last.to_opening,
            last.to_opening?.[0],
            placeById
          )
        : openingMouthAbs(
            endPlace,
            last.to_opening,
            last.to_opening?.[0],
            placeById
          );
      const oriented = orientExteriorSubs(exteriors, startOp, endOp);

      // Tube: +laneDist parallel offset only on the exterior, then local
      // converge onto each mouth. Inbox: mouth fan (separate AFTER the boca).
      // Never offset a continuous inbox+tube centerline then forceThroughMouth
      // — that peels lanes out of the conduit (0.34.20 anti-pattern).
      const startAtt = resolveElementAttach(
        a,
        fromPin,
        startOp,
        placeById,
        fromSlot.slot,
        fromSlot.count
      );
      const endAtt = resolveElementAttach(
        b,
        toPin,
        endOp,
        placeById,
        toSlot.slot,
        toSlot.count
      );
      const startFace =
        startAtt.face || elementAttachFace(a, startOp, placeById);
      const endFace = endAtt.face || elementAttachFace(b, endOp, placeById);
      // Wide multi-lane NS inboxes skirt element bodies (rule 17 / Route_30).
      // Smaller sites keep the mouth fan free — element pierce is gated by
      // dedicated Route_30 E2E, not every fan path.
      const startElemObs =
        laneCountHint >= 8
          ? elementObstacles(elemById, placeById, null, 2)
          : [];
      const endElemObs =
        laneCountHint >= 8
          ? elementObstacles(elemById, placeById, null, 2)
          : [];

      // Tube only gets highway parallel offset. Inbox uses a mouth fan so
      // lanes stay inside the conduit and only separate after the boca.
      /** @type {number[][]|null} */
      let exteriorCtr = null;
      for (const ext of oriented) {
        if (!ext || ext.length < 2) continue;
        exteriorCtr = exteriorCtr
          ? mergeOrthoPolys(exteriorCtr, ext)
          : ext.map((p) => [p[0], p[1]]);
      }
      if (!exteriorCtr || exteriorCtr.length < 2) {
        const d = orthoPathD(c1, c2, null, null, occupied, freeObstacles);
        return d
          ? pathDToSubpaths(d).map((sub) =>
              ensureOrthoPoly(parallel(sub, laneDistFallback, freeObstacles))
            )
          : [];
      }

      // Mouths for hop phases = painted tube ends (not a divergent plane-entry
      // point). Plane bocas (B/F) otherwise pulled strands off the edge-tube.
      const tubeStartOp = {
        x: exteriorCtr[0][0],
        y: exteriorCtr[0][1],
      };
      const tubeEndOp = {
        x: exteriorCtr[exteriorCtr.length - 1][0],
        y: exteriorCtr[exteriorCtr.length - 1][1],
      };

      const startMouthFace = routeFace(
        startPlace,
        first.from_opening,
        first.from_opening?.[0],
        placeById
      );
      const endMouthFace = routeFace(
        endPlace,
        last.to_opening,
        last.to_opening?.[0],
        placeById
      );

      let tube = exteriorCtr.map((p) => [p[0], p[1]]);
      // Per-hop exteriors are already lane-offset. Single-cable (no offset):
      // snap tube ends to the painted boca for clean transit.
      const startLaneDist = laneDistFor(first.conduit);
      const endLaneDist = laneDistFor(last.conduit);
      // Center highway lane has dist≈0 — still multi when siblings share the tube.
      const multiAtOpening =
        laneCountHint > 1 ||
        Math.abs(startLaneDist) >= 1e-9 ||
        Math.abs(endLaneDist) >= 1e-9;
      if (!multiAtOpening) {
        tube = convergeLaneToMouth(tube, tubeStartOp, true);
        tube = convergeLaneToMouth(tube, tubeEndOp, false);
        if (tube.length >= 1) {
          tube[0] = [tubeStartOp.x, tubeStartOp.y];
          tube[tube.length - 1] = [tubeEndOp.x, tubeEndOp.y];
          tube = cleanOrthoPoly(tube);
        }
      }
      // Lane crossing = tube endpoint (center mouth when laneDist≈0).
      const startCrossing = {
        x: tube[0][0],
        y: tube[0][1],
      };
      const endCrossing = {
        x: tube[tube.length - 1][0],
        y: tube[tube.length - 1][1],
      };

      // Fan from the lane crossing. Multi-cable: unique stub depths per lane
      // so pin→tip diagonals stay separated (Route_29).
      const fanDepthBias = (dist) =>
        multiAtOpening ? dist + LANE_PITCH * 3 : 0;
      const startFan = mouthFanPts(
        startCrossing,
        startMouthFace,
        0,
        startAtt,
        fanDepthBias(startLaneDist)
      );
      const endFan = mouthFanPts(
        endCrossing,
        endMouthFace,
        0,
        endAtt,
        fanDepthBias(endLaneDist)
      );
      // Toward mouth: fan → stub → crossing. Multi-lane with distinct pins:
      // unique-depth Manhattan bus (pin column → H → lane column → V). Shared
      // bus depth / diagonals cross when pin order ≠ lane order (Route_29).
      const startFanRev = startFan.slice().reverse();
      const startPinCount = Math.max(fromSlot.count, laneCountHint);
      const startPinSlot =
        fromSlot.count > 1 ? fromSlot.slot : laneIndexHint;
      let head;
      // Distinct-pin bus for wide multi-lane NS inboxes (Route_30). Fewer
      // lanes keep the mouth fan so bocas stay parallel (Route_12 rule 13).
      const useDistinctPinBus =
        multiAtOpening &&
        !(fromSlot.count > 1) &&
        laneCountHint >= 8 &&
        (startFace === "N" || startFace === "S");
      if (useDistinctPinBus) {
        head = distinctPinLaneBus(
          startAtt,
          startFace,
          startCrossing,
          startLaneDist,
          laneCountHint,
          laneIndexHint,
          startElemObs
        );
      } else {
        const startLead = pinToLanePts(
          [startAtt.x, startAtt.y],
          startFace,
          startFanRev[0],
          startPinSlot,
          startPinCount,
          fromSlot.count > 1
        );
        head = joinLeadToFanTip(
          startLead,
          startFanRev[0],
          startFace,
          startElemObs,
          false
        );
        if (startFanRev.length > 1) {
          head = mergeOrthoPolys(head, startFanRev.slice(1)) || head;
        }
      }
      {
        const before = head.map((p) => [p[0], p[1]]);
        const mouthProtect = [startCrossing, startFanRev[0], ...startFan];
        // Distinct-pin bus H depths must not be Z-collapsed onto the boca.
        if (!useDistinctPinBus) {
          head = stripShortZJogs(
            stripOutAndBack(head, mouthProtect),
            28,
            mouthProtect
          );
        } else {
          head = stripOutAndBack(head, mouthProtect);
        }
        // Do not let strip collapse an element-skirting detour (rule 17).
        if (
          startElemObs.length &&
          pathObstacleCost(head, startElemObs) >
            pathObstacleCost(before, startElemObs) + 1
        ) {
          head = before;
        }
      }
      // Phase contract: head ends on the start lane crossing.
      {
        const sx = startCrossing.x;
        const sy = startCrossing.y;
        if (!head.length) {
          head = [[sx, sy]];
        } else if (
          Math.hypot(head[head.length - 1][0] - sx, head[head.length - 1][1] - sy) >
          1e-6
        ) {
          const last = head[head.length - 1];
          if (Math.abs(last[0] - sx) >= 1e-6 && Math.abs(last[1] - sy) >= 1e-6) {
            // Prefer matching crossing latitude on current column (N/S faces).
            head.push([last[0], sy]);
          }
          head.push([sx, sy]);
        } else {
          head[head.length - 1] = [sx, sy];
        }
      }

      const endFanFwd = endFan.map((p) => [p[0], p[1]]);
      const endFanTip = endFanFwd[endFanFwd.length - 1];
      const endPinCount = Math.max(toSlot.count, laneCountHint);
      const endPinSlot = toSlot.count > 1 ? toSlot.slot : laneIndexHint;
      let tailFromPin;
      const useDistinctPinBusEnd =
        multiAtOpening &&
        !(toSlot.count > 1) &&
        laneCountHint >= 8 &&
        (endFace === "N" || endFace === "S");
      if (useDistinctPinBusEnd) {
        tailFromPin = distinctPinLaneBus(
          endAtt,
          endFace,
          endCrossing,
          endLaneDist,
          laneCountHint,
          laneIndexHint,
          endElemObs
        );
      } else {
        const endLead = pinToLanePts(
          [endAtt.x, endAtt.y],
          endFace,
          endFanTip,
          endPinSlot,
          endPinCount,
          toSlot.count > 1
        );
        // pin → … → fan tip → stub → crossing, then reverse to crossing→…→pin.
        tailFromPin = joinLeadToFanTip(
          endLead,
          endFanTip,
          endFace,
          endElemObs,
          false
        );
        const fanToMouth = endFanFwd.slice().reverse(); // fan, stub, crossing
        if (fanToMouth.length > 1) {
          tailFromPin =
            mergeOrthoPolys(tailFromPin, fanToMouth.slice(1)) || tailFromPin;
        }
      }
      {
        const before = tailFromPin.map((p) => [p[0], p[1]]);
        const mouthProtect = [endCrossing, endFanTip, ...endFanFwd];
        if (!useDistinctPinBusEnd) {
          tailFromPin = stripShortZJogs(
            stripOutAndBack(tailFromPin, mouthProtect),
            28,
            mouthProtect
          );
        } else {
          tailFromPin = stripOutAndBack(tailFromPin, mouthProtect);
        }
        if (
          endElemObs.length &&
          pathObstacleCost(tailFromPin, endElemObs) >
            pathObstacleCost(before, endElemObs) + 1
        ) {
          tailFromPin = before;
        }
      }
      // Phase contract: pin-side path ends on the end crossing before reverse.
      // (mergeOrthoPolys ignores 1-point arrays — append explicitly.)
      {
        const ex = endCrossing.x;
        const ey = endCrossing.y;
        if (!tailFromPin.length) {
          tailFromPin = [[ex, ey]];
        } else if (
          Math.hypot(
            tailFromPin[tailFromPin.length - 1][0] - ex,
            tailFromPin[tailFromPin.length - 1][1] - ey
          ) > 1e-6
        ) {
          const last = tailFromPin[tailFromPin.length - 1];
          if (Math.abs(last[0] - ex) >= 1e-6 && Math.abs(last[1] - ey) >= 1e-6) {
            tailFromPin.push([last[0], ey]);
          }
          tailFromPin.push([ex, ey]);
        } else {
          tailFromPin[tailFromPin.length - 1] = [ex, ey];
        }
      }
      const tail = tailFromPin.slice().reverse();

      // Tube stays pristine. Explicit phase concat (no full-chain post-passes).
      /** @type {number[][]} */
      const concatPhases = (headPts, tubePts, tailPts) => {
        /** @type {number[][]} */
        const out = [];
        const append = (seg) => {
          for (const p of seg || []) {
            const prev = out[out.length - 1];
            if (
              prev &&
              Math.hypot(prev[0] - p[0], prev[1] - p[1]) < 1e-6
            ) {
              continue;
            }
            out.push([p[0], p[1]]);
          }
        };
        append(headPts);
        append(tubePts);
        append(tailPts);
        return out.length >= 2 ? out : [];
      };
      let chain = concatPhases(head, tube, tail);
      // Re-assert exterior = canonical tube between lane crossings.
      chain = spliceTubeSegment(chain, tube, startCrossing, endCrossing);
      if (!chain || chain.length < 2) return [];
      return [chain];
    }

    // Free-space (no conduit hops): pin → stub → corridor → stub → pin.
    // Never route element-center to element-center — that misses terminals.
    {
      const p1 = resolveElementAttach(
        a,
        fromPin,
        c2,
        placeById,
        fromSlot.slot,
        fromSlot.count
      );
      const p2 = resolveElementAttach(
        b,
        toPin,
        c1,
        placeById,
        toSlot.slot,
        toSlot.count
      );
      const f1 = p1.face || elementAttachFace(a, c2, placeById);
      const f2 = p2.face || elementAttachFace(b, c1, placeById);
      const o1 = faceOutwardDelta(f1);
      const o2 = faceOutwardDelta(f2);
      const laneClear =
        Math.abs(laneDistFallback) + LANE_GAP + STRAND_WIDTH;
      const s1 = stubPoint(
        p1,
        o1.x,
        o1.y,
        Math.max(inboxStubDepth(fromSlot.count), laneClear + 6)
      );
      const s2 = stubPoint(
        p2,
        o2.x,
        o2.y,
        Math.max(inboxStubDepth(toSlot.count), laneClear + 6)
      );
      const corridor = orthoRoute(
        s1,
        s2,
        null,
        null,
        occupied,
        freeObstacles,
        null,
        null
      );
      const corridorOff = parallel(
        (corridor || []).map((p) =>
          Array.isArray(p) ? [p[0], p[1]] : [p.x, p.y]
        ),
        laneDistFallback,
        freeObstacles
      );
      if (!corridorOff.length) return [];
      const head = pinToLanePts(
        [p1.x, p1.y],
        f1,
        corridorOff[0],
        fromSlot.slot,
        fromSlot.count
      );
      const tail = pinToLanePts(
        [p2.x, p2.y],
        f2,
        corridorOff[corridorOff.length - 1],
        toSlot.slot,
        toSlot.count
      );
      const joinAvoid = (fromPt, toPt) =>
        orthoRoute(
          { x: fromPt[0], y: fromPt[1] },
          { x: toPt[0], y: toPt[1] },
          null,
          null,
          occupied,
          freeObstacles,
          null,
          null
        );
      let chain = head.map((p) => [p[0], p[1]]);
      const hEnd = chain[chain.length - 1];
      const c0 = corridorOff[0];
      if (
        hEnd &&
        c0 &&
        Math.hypot(hEnd[0] - c0[0], hEnd[1] - c0[1]) > 1e-6
      ) {
        chain = mergeOrthoPolys(chain, joinAvoid(hEnd, c0)) || chain;
      }
      chain = mergeOrthoPolys(chain, corridorOff) || chain;
      const c1pt = corridorOff[corridorOff.length - 1];
      const tip = tail[tail.length - 1];
      if (
        c1pt &&
        tip &&
        Math.hypot(c1pt[0] - tip[0], c1pt[1] - tip[1]) > 1e-6
      ) {
        chain = mergeOrthoPolys(chain, joinAvoid(c1pt, tip)) || chain;
      }
      chain = mergeOrthoPolys(chain, tail.slice().reverse()) || chain;
      return [cleanOrthoPoly(chain || [])];
    }
  }

  /**
   * Tube geometry: clip through leaf interiors, but keep both endpoint places
   * (side and B/F bocas) so the tube stays visible into each opening.
   */
  function conduitDisplayD(fullD, byId, edge) {
    if (!fullD) return "";
    /** @type {string[]} */
    const keep = [];
    if (edge?.from) keep.push(edge.from);
    if (edge?.to) keep.push(edge.to);
    // inset 0: do not leave a border corridor that paints tube into the leaf
    // toward terminal strips on side-opening ends.
    const leafObs = placeObstacles(byId, keep, 0);
    const clipped = exteriorPathD(fullD, leafObs);
    if (clipped) return clipped;
    // Mis-routes that pierce unrelated boxes may clip to nothing; still show
    // the routed path rather than a ghost conduit with an empty ``d``.
    return fullD;
  }

  function appendCableVisuals(cablesG, edge, placeById, elemById, occupied, layout) {
    const colors = edge.colors || [];
    const wireIdx = cableWireIndices(edge);
    const edgeName = edge.name || edge.id || edge.via || "";
    /** @type {SVGElement[]} */
    const paths = [];

    /**
     * Paint a cable jacket around this cable's contiguous lane span (not the
     * conduit centerline — that made every jacket look like a peer strand).
     */
    if (layout && wireIdx.length && edge.jacket_color) {
      const jacketCss = wireColorCss(edge.jacket_color);
      const paintJacketD = (d, midOff, jw) => {
        if (!d) return;
        for (const piece of pathDToSubpaths(d)) {
          if (piece.length < 2) continue;
          const off =
            Math.abs(midOff) < 1e-9
              ? piece.map((p) => [p[0], p[1]])
              : offsetOrthoPts(piece, midOff);
          if (off.length < 2) continue;
          const jd = pointsToPathD(off);
          const jwStroke = Math.max(3, jw);
          const container = strokeContainerForCableEdge({
            ...edge,
            jacket_color: null,
          });
          if (
            needsNestedContrastRim(
              edge.jacket_color,
              container.code,
              jacketCss,
              container.css
            )
          ) {
            const rim = appendContrastRim(
              cablesG,
              jd,
              jacketCss,
              jwStroke,
              "cable-jacket-outline"
            );
            if (rim) paths.push(rim);
          }
          const jacketHit = el("path", {
            class: "cable-jacket-hit",
            d: jd,
            "data-link-id": edge.id,
            "data-link-kind": "cable",
            "data-hit-visual": String(jwStroke),
          });
          jacketHit.style.strokeWidth = String(cableHitStrokeWorld(jwStroke));
          bindLinkHit(jacketHit, edge.id, "cable");
          const jacket = el("path", {
            class: "cable-jacket",
            d: jd,
            "data-link-id": edge.id,
            "data-link-kind": "cable",
          });
          jacket.style.stroke = jacketCss;
          jacket.style.strokeWidth = String(jwStroke);
          jacket.style.strokeOpacity =
            String(edge.jacket_color).toUpperCase() === "WH" ? "0.88" : "0.75";
          jacket.appendChild(
            el(
              "title",
              null,
              `${edgeName}${colors.length ? ` [${colors.join(",")}]` : ""} jacket ${edge.jacket_color}`
            )
          );
          cablesG.appendChild(jacketHit);
          cablesG.appendChild(jacket);
          paths.push(jacketHit, jacket);
        }
      };
      const jacketMetrics = (cid) => {
        const jacket = layout.jacketOnConduit(cid, edge);
        if (!jacket) return null;
        return {
          midOff:
            (highwayLaneOffset(jacket.first, jacket.count) +
              highwayLaneOffset(jacket.last, jacket.count)) /
            2,
          jw: highwaySpanWidth(jacket.last - jacket.first + 1) + 1.2,
        };
      };
      const hops = edge.conduit_hops || [];
      if (hops.length) {
        for (const hop of hops) {
          const tubeD = hopTubePathD(hop);
          if (
            !tubeD ||
            !hop.conduit ||
            !layout.isJacketRepresentative(hop.conduit, edge)
          ) continue;
          const fakeEdge = {
            from: hop.from,
            to: hop.to,
            from_opening: hop.from_opening,
            to_opening: hop.to_opening,
          };
          const metrics = jacketMetrics(hop.conduit);
          if (!metrics) continue;
          const { midOff, jw } = metrics;
          paintJacketD(conduitDisplayD(tubeD, placeById, fakeEdge), midOff, jw);
        }
      } else if (edge.conduit) {
        const item =
          edgePathsByConduitId.get(edge.conduit) ||
          edgePaths.find((e) => e.edge && e.edge.id === edge.conduit);
        if (item && item.d && layout.isJacketRepresentative(edge.conduit, edge)) {
          const metrics = jacketMetrics(edge.conduit);
          if (metrics) {
            const { midOff, jw } = metrics;
            paintJacketD(
              conduitDisplayD(item.dPaint || item.d, placeById, item.edge),
              midOff,
              jw
            );
          }
        }
      }
    }

    const paintStrand = (d, code, title, linkId, kind) => {
      if (!d) return;
      const key = String(code || "").toUpperCase();
      const pickId = linkId || edge.id;
      const pickKind = kind || "cable";
      // Immediate container: jacket if present, else conduit, else canvas.
      const container = strokeContainerForCableEdge(edge);
      if (key === "GNYE") {
        // Green-yellow PE: green base + yellow dashes (IEC look).
        const gnCss = wireColorCss("GN");
        if (
          needsNestedContrastRim("GN", container.code, gnCss, container.css)
        ) {
          const rim = appendContrastRim(
            cablesG,
            d,
            gnCss,
            STRAND_WIDTH,
            "cable-strand-outline"
          );
          if (rim) paths.push(rim);
        }
        const gn = el("path", {
          class: "cable-strand",
          d,
          "data-conductor-id": pickId,
          "data-cable-id": edge.id,
        });
        gn.setAttribute("stroke", gnCss);
        gn.setAttribute("stroke-width", String(STRAND_WIDTH));
        gn.appendChild(el("title", null, title));
        const ye = el("path", {
          class: "cable-strand cable-strand-gnye",
          d,
          "data-conductor-id": pickId,
          "data-cable-id": edge.id,
        });
        ye.setAttribute("stroke", wireColorCss("YE"));
        ye.setAttribute("stroke-width", String(STRAND_WIDTH));
        ye.setAttribute("stroke-dasharray", "5 5");
        ye.style.strokeOpacity = "0.95";
        const hit = el("path", {
          class: "cable-strand-hit",
          d,
          "data-link-id": pickId,
          "data-link-kind": pickKind,
          "data-conductor-id": pickId,
          "data-cable-id": edge.id,
          "data-cableed": String(edge.id !== pickId),
          "data-hit-visual": String(STRAND_WIDTH),
        });
        hit.style.strokeWidth = String(cableHitStrokeWorld(STRAND_WIDTH));
        bindLinkHit(hit, pickId, pickKind);
        cablesG.appendChild(hit);
        cablesG.appendChild(gn);
        cablesG.appendChild(ye);
        paths.push(hit, gn, ye);
        return;
      }
      const fillCss = wireColorCss(code);
      if (
        needsNestedContrastRim(key, container.code, fillCss, container.css)
      ) {
        const rim = appendContrastRim(
          cablesG,
          d,
          fillCss,
          STRAND_WIDTH,
          "cable-strand-outline"
        );
        if (rim) paths.push(rim);
      }
      const strand = el("path", {
        class: "cable-strand",
        d,
        "data-conductor-id": pickId,
        "data-cable-id": edge.id,
      });
      strand.setAttribute("stroke", fillCss);
      strand.setAttribute("stroke-width", String(STRAND_WIDTH));
      strand.appendChild(el("title", null, title));
      const hit = el("path", {
        class: "cable-strand-hit",
        d,
        "data-link-id": pickId,
        "data-link-kind": pickKind,
        "data-conductor-id": pickId,
        "data-cable-id": edge.id,
        "data-cableed": String(edge.id !== pickId),
        "data-hit-visual": String(STRAND_WIDTH),
      });
      hit.style.strokeWidth = String(cableHitStrokeWorld(STRAND_WIDTH));
      bindLinkHit(hit, pickId, pickKind);
      cablesG.appendChild(hit);
      cablesG.appendChild(strand);
      paths.push(hit, strand);
    };

    // Colored strands: true parallel lanes on the highway.
    const conductors = edge.conductors || [];
    for (const wi of wireIdx) {
      const code = colors[wi] || colors[0] || "GY";
      const fromT = layout
        ? layout.terminal(edge, wi, "from")
        : { slot: 0, count: 1 };
      const toT = layout
        ? layout.terminal(edge, wi, "to")
        : { slot: 0, count: 1 };
      const lane = layout
        ? layout.lane(edge, wi)
        : { index: wi, count: wireIdx.length };
      const strandSubs = cableBaseSubpaths(edge, placeById, elemById, occupied, {
        fromSlot: fromT,
        toSlot: toT,
        laneDist: highwayLaneOffset(lane.index, lane.count),
        laneIndex: lane.index,
        laneCount: lane.count,
        laneDistForConduit: layout
          ? (cid) => {
              const L = layout.laneOnConduit(cid, edge, wi);
              return highwayLaneOffset(L.index, L.count);
            }
          : undefined,
        fromPin: cableWirePin(edge, wi, "from"),
        toPin: cableWirePin(edge, wi, "to"),
      });
      const conductorId = conductors[wi] || edge.id;
      const strandKind = "conductor";
      for (const sub of strandSubs) {
        paintStrand(
          pointsToPathD(sub),
          code,
          `${edgeName} · ${code}${edge.via ? ` (${edge.via})` : ""}`,
          conductorId,
          strandKind
        );
        // Later same-box / free-space strands avoid stacking on this run.
        for (const s of segsFromPoints(sub, STRAND_WIDTH / 2)) {
          occupied.push(s);
        }
        const fromE = elemById[edge.from];
        const toE = elemById[edge.to];
        if (
          inboxCablePtsByParent &&
          fromE &&
          toE &&
          fromE.parent &&
          fromE.parent === toE.parent &&
          sub &&
          sub.length >= 2
        ) {
          (inboxCablePtsByParent[fromE.parent] ||= []).push(
            sub.map((p) => [p[0], p[1]])
          );
        }
      }
    }
    if (!paths.length) return null;
    return { edge, paths, subs: [], wireIdx };
  }

  /**
   * Re-route conduits and/or rebuild cable SVG.
   * @param {{ skipConduits?: boolean, skipCables?: boolean }} [opts]
   *   skipConduits: reuse tube ``d`` (element-only drag) and only rebuild cables.
   *   skipCables: update tubes only (progressive post-drag first pass).
   */
  function refreshEdges(opts) {
    if (!graph) return;
    const skipConduits = !!(opts && opts.skipConduits);
    const skipCables = !!(opts && opts.skipCables);
    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    const elemById = Object.fromEntries(
      (graph.elements || []).map((e) => [e.id, e])
    );
    beginRouteGeomCache(byId, elemById);
    try {
      /** @type {ReturnType<typeof createOccupiedIndex>} */
      const occupied = createOccupiedIndex();
      // Tubes-only progressive pass skips packing layout (hint widths suffice).
      const layoutForTubes =
        showElectrical && !skipCables
          ? buildCableLayout(graph.cable_edges || [], elemById, byId)
          : null;
      if (!skipConduits) {
        for (const item of edgePaths) {
          const n = (item.edge.contains || []).length;
          const lanes = tubeLaneCount(item.edge, layoutForTubes);
          const roadW = conduitRoadWidth(n, lanes);
          const half = roadW / 2;
          const routed = edgePathD(item.edge, byId, occupied, half);
          if (routed) {
            applyRoutedTubeVisual(item, routed, roadW, byId);
            for (const s of routed.segs) occupied.push(s);
          }
        }
        indexEdgePaths();
      } else {
        for (const item of edgePaths) {
          if (!item.d) continue;
          const n = (item.edge.contains || []).length;
          const lanes = tubeLaneCount(item.edge, layoutForTubes);
          const roadW = conduitRoadWidth(n, lanes);
          const half = roadW / 2;
          for (const sub of pathDToSubpaths(item.d)) {
            for (const s of segsFromPoints(sub, half)) occupied.push(s);
          }
        }
      }
      if (skipCables) return;
      // Rebuild cable layers (jacket + strands) from scratch.
      const cablesG = worldEl && worldEl.querySelector("g.cables");
      if (cablesG && showElectrical) {
        cablesG.innerHTML = "";
        cablePaths = [];
        const layout =
          layoutForTubes ||
          buildCableLayout(graph.cable_edges || [], elemById, byId);
        for (const edge of cablePaintOrder(graph.cable_edges)) {
          const item = appendCableVisuals(
            cablesG,
            edge,
            byId,
            elemById,
            occupied,
            layout
          );
          if (item) cablePaths.push(item);
        }
        orderCableLayers(cablesG);
        syncCableCandidateVisuals();
      }
    } finally {
      endRouteGeomCache();
    }
  }

  function syncOpeningMarks(node) {
    const g = nodesById[node.id];
    if (!g) return;
    const hasKids = childrenOf(node.id).length > 0;
    const showOpenings = !hasKids && nodeHasOpeningMarks(node);
    const w = nodeW(node);
    const h = nodeH(node);
    const box = g.querySelector(".node-box");
    const placeMap = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));

    if (!showOpenings) {
      g.querySelectorAll("g.node-iso").forEach((n) => n.remove());
      g.querySelectorAll("[data-opening]").forEach((n) => n.remove());
      if (box) {
        box.classList.remove("iso-box");
        box.setAttribute("rx", "6");
      }
      return;
    }

    if (box) {
      box.classList.add("iso-box");
      box.setAttribute("rx", "0");
      const fr = frontRectLocal(node);
      box.setAttribute("x", String(fr.x));
      box.setAttribute("y", String(fr.y));
      box.setAttribute("width", String(fr.w));
      box.setAttribute("height", String(fr.h));
    }
    if (!g.querySelector("g.node-iso-faces") || !g.querySelector("g.node-iso-wires")) {
      appendNodeIsoBevel(g, w, h);
    } else {
      syncNodeIsoBevel(g, w, h);
    }
    // Keep projected wireframe above the front face rect.
    const wireLayer = g.querySelector("g.node-iso-wires");
    if (wireLayer) g.appendChild(wireLayer);

    const want = openingCellsForNode(node);
    const wantSet = new Set(want);
    g.querySelectorAll("[data-opening]").forEach((elOp) => {
      const oid = elOp.getAttribute("data-opening");
      if (!oid || !wantSet.has(oid)) elOp.remove();
    });

    const ordered = [...want].sort((a, b) => {
      const ma = openingMarkLocal(node, a, placeMap);
      const mb = openingMarkLocal(node, b, placeMap);
      if (ma.near !== mb.near) return ma.near ? 1 : -1;
      return 0;
    });
    for (const oid of ordered) {
      const mark = openingMarkLocal(node, oid, placeMap);
      const nearFar = mark.near ? "opening-near" : "opening-far";
      const faceClass = `opening-face-${mark.face || "X"}`;
      let circle = g.querySelector(`circle[data-opening="${CSS.escape(String(oid))}"]`);
      if (!circle) {
        circle = el("circle", {
          class: `opening-mark ${nearFar} ${faceClass}`,
          "data-opening": oid,
          cx: mark.x,
          cy: mark.y,
          r: OPENING_MARK_R,
        });
        circle.appendChild(el("title", null, oid));
        circle.addEventListener("pointerdown", (ev) => {
          if (onWiringOpeningClick(node.id, oid, ev)) return;
        });
        g.appendChild(circle);
      } else {
        circle.setAttribute("class", `opening-mark ${nearFar} ${faceClass}`);
        circle.setAttribute("cx", String(mark.x));
        circle.setAttribute("cy", String(mark.y));
      }
      let text = g.querySelector(`text.opening-label[data-opening="${CSS.escape(String(oid))}"]`);
      if (!text) {
        text = el(
          "text",
          {
            class: `opening-label ${nearFar} ${faceClass}`,
            "data-opening": oid,
            x: mark.x,
            y: mark.y + 3,
            "text-anchor": "middle",
          },
          oid
        );
        text.addEventListener("pointerdown", (ev) => {
          if (onWiringOpeningClick(node.id, oid, ev)) return;
        });
        g.appendChild(text);
      } else {
        text.setAttribute("class", `opening-label ${nearFar} ${faceClass}`);
        text.setAttribute("x", String(mark.x));
        text.setAttribute("y", String(mark.y + 3));
        text.textContent = oid;
      }
    }
  }

  function updateElementVisual(elem, placeById) {
    const g = elementsById[elem.id];
    if (!g) return;
    const a = elementAbsXY(elem, placeById);
    const w = elem.w ?? ELEM_W;
    const h = elem.h ?? ELEM_H;
    g.setAttribute("transform", `translate(${a.x},${a.y})`);
    const box = g.querySelector(".element-box");
    if (box) {
      box.setAttribute("width", String(w));
      box.setAttribute("height", String(h));
    }
    const label = g.querySelector("text.element-label");
    if (label) {
      label.textContent = fitLabel(
        elem.display_name || elem.name || elem.leaf_id || elem.id,
        Math.max(8, w - 15)
      );
    }
    for (const mark of g.querySelectorAll("circle.element-terminal")) {
      const cellId = mark.getAttribute("data-terminal");
      if (!cellId) continue;
      const local = terminalCellAnchorLocal(elem, cellId, placeById);
      mark.setAttribute("cx", String(local.x));
      mark.setAttribute("cy", String(local.y));
    }
  }

  /**
   * Update place/element transforms (and optional sizes/labels).
   * @param {unknown} [_node]
   * @param {{ refresh?: boolean, skipConduits?: boolean }} [opts] When refresh
   *   is false, skip conduit/cable re-route (use during pointermove drag; call
   *   again on pointerup). skipConduits reuses tube geometry (element-only drag).
   */
  function updateNodeVisual(_node, opts) {
    const refresh = !opts || opts.refresh !== false;
    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    // Keep live SE growth; NW absorb marks `_auto_absorb` so this does not wipe it.
    measureVisibleSizes();
    for (const n of graph.nodes) {
      const g = nodesById[n.id];
      if (!g) continue;
      const a = absXY(n, byId);
      const w = nodeW(n);
      const h = nodeH(n);
      g.setAttribute("transform", `translate(${a.x},${a.y})`);
      const box = g.querySelector(".node-box");
      if (box) {
        box.setAttribute("width", String(w));
        box.setAttribute("height", String(h));
      }
      const label = g.querySelector("text.node-label");
      if (label) {
        label.textContent = fitLabel(
          (n.display_name || n.name || n.id) + (n.expandable ? " · +" : ""),
          Math.max(8, w - 21)
        );
      }
      syncOpeningMarks(n);
    }
    for (const e of graph.elements || []) {
      updateElementVisual(e, byId);
    }
    if (refresh) {
      const edgeOpts =
        opts && opts.skipConduits ? { skipConduits: true } : undefined;
      if (opts && opts.progressive) {
        scheduleProgressiveEdgeRefresh(edgeOpts);
      } else {
        refreshEdges(edgeOpts);
      }
    }
  }

