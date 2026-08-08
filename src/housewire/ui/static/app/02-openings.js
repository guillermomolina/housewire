  /* === 02-openings.js: Opening marks, mouths, mirrors, edge refresh scheduling ===
   * Fragment of the UI IIFE (bundled into ../app.js).
   * Edit this file, then run: python scripts/bundle_ui_app.py
   */
  function parseSideOpening(openingId) {
    const m = String(openingId || "").match(/^([NSEW])(\d+)$/i);
    if (!m) return null;
    return { face: m[1].toUpperCase(), index: parseInt(m[2], 10) };
  }

  function parsePlaneOpening(openingId) {
    const m = String(openingId || "").match(/^([FB])(\d+)-(\d+)$/i);
    if (!m) return null;
    return {
      face: m[1].toUpperCase(),
      row: parseInt(m[2], 10),
      col: parseInt(m[3], 10),
    };
  }

  function sideSlotCount(node, face, preferIndex) {
    const f = String(face || "").toUpperCase();
    const raw = node.opening_grid && node.opening_grid[f];
    let fromGrid = 0;
    if (Array.isArray(raw) && raw.length >= 1) {
      fromGrid = Math.max(1, Number(raw[0]) || 1);
      if (raw.length >= 2) {
        fromGrid = Math.max(
          fromGrid,
          (Number(raw[0]) || 1) * (Number(raw[1]) || 1)
        );
      }
    } else if (typeof raw === "number") {
      fromGrid = Math.max(1, Number(raw) || 1);
    }
    const declared = (node.openings || [])
      .map((o) => parseSideOpening(o.id || o))
      .filter((p) => p && p.face === f)
      .map((p) => p.index);
    const maxDeclared = declared.length ? Math.max(...declared) : 0;
    // Prefer opening_grid size so N:2 + only N2 sits in the right slot.
    return Math.max(fromGrid, maxDeclared, preferIndex || 1, 1);
  }

  const PLANE_R = 6;
  /**
   * NW isometric depth margin inside the sprite AABB (local ≥ 0).
   * ``view.physical`` w/h is the full painted hull; the front face sits at
   * ``(ISO_DEPTH, ISO_DEPTH)`` with size ``(W - ISO_DEPTH, H - ISO_DEPTH)``.
   */
  const ISO_DEPTH = 20;
  /** @deprecated Kept as aliases for mark math (back = front - depth). */
  const ISO_DX = -ISO_DEPTH;
  const ISO_DY = -ISO_DEPTH;
  const OPENING_MARK_R = 5;
  /** Side marks depth position between front(0) and back(1) projected faces. */
  const ISO_MARK_SIDE_DEPTH_T = 0.5;
  /** Keep marks clear from any projected rectangle border. */
  const ISO_MARK_FACE_MARGIN = OPENING_MARK_R + 6;
  /** F/B marks stay deeper inside their face than side marks (>= 1.5X). */
  const ISO_MARK_FB_INSET_FACTOR = 1.9;

  /** True for faces treated as near/visible under a fixed NW camera. */
  function isoFaceNear(visualFace) {
    const f = String(visualFace || "").toUpperCase();
    return f === "N" || f === "W" || f === "F";
  }

  /** All opening cell ids for a place: opening_grid cells ∪ declared openings. */
  function openingCellsForNode(node) {
    const ids = new Set();
    const expanded = expandFaceGridMap(node.opening_grid);
    for (const face of ["N", "S", "E", "W", "F", "B"]) {
      const spec = expanded[face];
      if (!spec) continue;
      for (const id of listFaceCellIds(face, spec[0], spec[1])) {
        ids.add(id);
      }
    }
    for (const op of node.openings || []) {
      const id = typeof op === "string" ? op : op && op.id;
      if (id) ids.add(String(id));
    }
    return [...ids];
  }

  function nodeHasOpeningMarks(node) {
    if (!node) return false;
    if ((node.openings || []).length) return true;
    const grid = node.opening_grid;
    return Boolean(grid && typeof grid === "object" && Object.keys(grid).length);
  }

  /** Iso NW depth for a place that paints opening marks; else 0. */
  function isoDepth(node) {
    return nodeHasOpeningMarks(node) ? ISO_DEPTH : 0;
  }

  /** Front-face rect in sprite-local coordinates. */
  function frontRectLocal(node) {
    const d = isoDepth(node);
    const W = nodeW(node);
    const H = nodeH(node);
    return {
      x: d,
      y: d,
      w: Math.max(4, W - d),
      h: Math.max(4, H - d),
    };
  }

  /** Content origin (nested places / elements) in sprite-local coordinates. */
  function contentOriginLocal(node) {
    const fr = frontRectLocal(node);
    return { x: fr.x + PAD, y: fr.y + HEADER };
  }

  /** Front-face rect in world coordinates. */
  function frontRectAbs(node, byId) {
    const a = absXY(node, byId);
    const fr = frontRectLocal(node);
    return { x: a.x + fr.x, y: a.y + fr.y, w: fr.w, h: fr.h };
  }

  /** Local mark position for 3D paint and conduit mouth alignment. */
  function openingMarkLocal(node, openingId, byId) {
    const faceHint = String(openingId || "?").match(/^[NSEWFB]/i)?.[0] || "?";
    const anchor = openingAnchorLocal(node, openingId, faceHint, byId);
    const visualFace = anchor.face || faceHint;
    const f = String(visualFace || "?").toUpperCase();
    const margin = ISO_MARK_FACE_MARGIN;
    const fr = frontRectLocal(node);
    const d = isoDepth(node);
    const fw = fr.w;
    const fh = fr.h;
    // Front [fr] and back [0,0]–[fw,fh] overlap inside the sprite.
    const insetX = Math.max(margin, d * ISO_MARK_FB_INSET_FACTOR);
    const insetY = Math.max(margin, d * ISO_MARK_FB_INSET_FACTOR);
    let x = anchor.x;
    let y = anchor.y;
    if (f === "N" || f === "S" || f === "E" || f === "W") {
      // Mid-depth toward the back face (NW), staying inside the sprite.
      const mid = d * ISO_MARK_SIDE_DEPTH_T;
      if (f === "N" || f === "S") {
        x = Math.max(fr.x - mid + margin, Math.min(fr.x + fw - mid - margin, x - mid));
        y = f === "N" ? fr.y - mid : fr.y + fh - mid;
      } else {
        y = Math.max(fr.y - mid + margin, Math.min(fr.y + fh - mid - margin, y - mid));
        x = f === "W" ? fr.x - mid : fr.x + fw - mid;
      }
    } else if (f === "F" || f === "B") {
      // Front-local overlap math (same as legacy), then offset into the sprite.
      const w = fw;
      const h = fh;
      const ix0 = Math.max(0, ISO_DX);
      const iy0 = Math.max(0, ISO_DY);
      const ix1 = Math.min(w, w + ISO_DX);
      const iy1 = Math.min(h, h + ISO_DY);
      const loX = fr.x + ix0 + insetX - ISO_DX;
      const hiX = fr.x + ix1 - insetX;
      const loY = fr.y + iy0 + insetY - ISO_DY;
      const hiY = fr.y + iy1 - insetY;
      x = Math.max(loX, Math.min(hiX, x));
      y = Math.max(loY, Math.min(hiY, y));
      if (f === "B") {
        x += ISO_DX;
        y += ISO_DY;
      }
    }
    return {
      x,
      y,
      face: f,
      near: isoFaceNear(f),
      mouthX: anchor.x,
      mouthY: anchor.y,
    };
  }

  /** Absolute position of the rendered opening mark (same as painted mouth). */
  function openingMarkAbs(node, openingId, face, byId) {
    const a = absXY(node, byId);
    const mark = openingMarkLocal(node, openingId, byId);
    return {
      x: a.x + mark.x,
      y: a.y + mark.y,
      face: mark.face || String(face || "").toUpperCase(),
    };
  }

  /** Top iso face: front top edge → back top edge (sprite-local ≥ 0). */
  function nodeIsoTopPathD(spriteW, _spriteH) {
    const d = ISO_DEPTH;
    const fw = spriteW - d;
    return `M ${d} ${d} L ${d + fw} ${d} L ${fw} 0 L 0 0 Z`;
  }

  /** West iso face: front west edge → back west edge. */
  function nodeIsoWestPathD(_spriteW, spriteH) {
    const d = ISO_DEPTH;
    const fh = spriteH - d;
    return `M ${d} ${d} L 0 0 L 0 ${fh} L ${d} ${d + fh} Z`;
  }

  /** Solid visible edges on the projected back/top-left side. */
  function nodeIsoVisibleWireD(spriteW, spriteH) {
    const d = ISO_DEPTH;
    const fw = spriteW - d;
    const fh = spriteH - d;
    return (
      `M 0 0 H ${fw} ` +
      `M 0 0 V ${fh} ` +
      `M ${d + fw} ${d} L ${fw} 0 ` +
      `M ${d} ${d} L 0 0 ` +
      `M ${d} ${d + fh} L 0 ${fh}`
    );
  }

  /** Dashed hidden edges: right/bottom of back face + right depth ribs. */
  function nodeIsoHiddenWireD(spriteW, spriteH) {
    const d = ISO_DEPTH;
    const fw = spriteW - d;
    const fh = spriteH - d;
    return (
      `M ${fw} 0 V ${fh} H 0 ` +
      `M ${d + fw} ${d + fh} L ${fw} ${fh}`
    );
  }

  function appendNodeIsoBevel(g, w, h) {
    const faces = el("g", {
      class: "node-iso node-iso-faces",
      "aria-hidden": "true",
    });
    faces.appendChild(
      el("path", { class: "node-iso-face node-iso-top", d: nodeIsoTopPathD(w, h) })
    );
    faces.appendChild(
      el("path", {
        class: "node-iso-face node-iso-west",
        d: nodeIsoWestPathD(w, h),
      })
    );
    const wires = el("g", {
      class: "node-iso node-iso-wires",
      "aria-hidden": "true",
    });
    wires.appendChild(
      el("path", {
        class: "node-iso-visible",
        d: nodeIsoVisibleWireD(w, h),
      })
    );
    wires.appendChild(
      el("path", {
        class: "node-iso-hidden",
        d: nodeIsoHiddenWireD(w, h),
      })
    );
    g.appendChild(faces);
    g.appendChild(wires);
    return { faces, wires };
  }

  function syncNodeIsoBevel(g, w, h) {
    const faces = g.querySelector("g.node-iso-faces");
    const wires = g.querySelector("g.node-iso-wires");
    if (!faces || !wires) return;
    const top = faces.querySelector("path.node-iso-top");
    const west = faces.querySelector("path.node-iso-west");
    const visible = wires.querySelector("path.node-iso-visible");
    let hidden = wires.querySelector("path.node-iso-hidden");
    if (!hidden) {
      hidden = wires.querySelector("path.node-iso-far");
      if (hidden) hidden.setAttribute("class", "node-iso-hidden");
    }
    if (top) top.setAttribute("d", nodeIsoTopPathD(w, h));
    if (west) west.setAttribute("d", nodeIsoWestPathD(w, h));
    if (visible) visible.setAttribute("d", nodeIsoVisibleWireD(w, h));
    if (hidden) hidden.setAttribute("d", nodeIsoHiddenWireD(w, h));
  }

  function planeGridDims(node, face, plane) {
    let cols = 1;
    let rows = 1;
    const raw = node.opening_grid && node.opening_grid[face];
    if (Array.isArray(raw) && raw.length >= 2) {
      cols = Math.max(1, Number(raw[0]) || 1);
      rows = Math.max(1, Number(raw[1]) || 1);
    } else if (raw && typeof raw === "object") {
      cols = Math.max(1, Number(raw.cols) || 1);
      rows = Math.max(1, Number(raw.rows) || 1);
    }
    for (const o of node.openings || []) {
      const p = parsePlaneOpening(o.id);
      if (!p || p.face !== face) continue;
      cols = Math.max(cols, p.col);
      rows = Math.max(rows, p.row);
    }
    if (plane) {
      cols = Math.max(cols, plane.col);
      rows = Math.max(rows, plane.row);
    }
    return { cols, rows };
  }

  /** Center of cell index (1-based) along size; outer cells near the border. */
  function planeCellCenter(size, count, index, radius) {
    const margin = radius + 5;
    if (count <= 1) return size / 2;
    const span = Math.max(0, size - 2 * margin);
    return margin + ((index - 1) / (count - 1)) * span;
  }

  /** Local coords for B/F openings on a face grid, almost touching the border. */
  function planeAnchorLocal(node, openingId, face, byId) {
    const fr = frontRectLocal(node);
    const plane = parsePlaneOpening(openingId);
    const f = (plane?.face || face || "?").toUpperCase();
    if (!plane || (f !== "B" && f !== "F")) {
      return { x: fr.x + fr.w / 2, y: fr.y + fr.h / 2 };
    }
    const { cols, rows } = planeGridDims(node, f, plane);
    const flips = effectiveFlips(node, idMap(byId));
    let col = plane.col;
    let row = plane.row;
    if (flips.we) col = cols + 1 - col;
    if (flips.ns) row = rows + 1 - row;
    let x = fr.x + planeCellCenter(fr.w, cols, col, PLANE_R);
    let y = fr.y + planeCellCenter(fr.h, rows, row, PLANE_R);
    return { x, y };
  }

  function openingAnchorAbs(node, openingId, face, byId) {
    const a = absXY(node, byId);
    const local = openingAnchorLocal(node, openingId, face, byId);
    return { x: a.x + local.x, y: a.y + local.y };
  }

  /**
   * Rendered conduit mouth for a conduit end.
   * Keep this aligned with the painted opening mark to avoid visual mismatch.
   */
  function openingMouthAbs(node, openingId, face, byId) {
    return openingMarkAbs(node, openingId, face, byId);
  }

  function isPlaneOpeningId(openingId) {
    const plane = parsePlaneOpening(openingId);
    return Boolean(plane && (plane.face === "B" || plane.face === "F"));
  }

  /** Absolute positions of side openings on one contour face (visual face). */
  function sideOpeningAbsOnFace(node, face, byId) {
    const f = String(face || "").toUpperCase();
    /** @type {{x:number,y:number}[]} */
    const out = [];
    for (const o of node.openings || []) {
      const id = o && (o.id != null ? o.id : o);
      const side = parseSideOpening(id);
      if (!side) continue;
      const local = openingAnchorLocal(node, id, side.face, byId);
      const visual = local.face || side.face;
      if (visual !== f) continue;
      out.push(openingAnchorAbs(node, id, side.face, byId));
    }
    return out;
  }

  /**
   * Nudge a contour point along its face so it does not sit on a side
   * opening (e.g. B-approach vs N1). Prefer left on N/S, down on E/W.
   */
  function nudgeOffSideOpenings(node, face, pt, byId) {
    const f = String(face || "").toUpperCase();
    const others = sideOpeningAbsOnFace(node, f, byId);
    if (!others.length) return { x: pt.x, y: pt.y };
    const CLEAR = 16;
    const NUDGE = 14;
    const fr = frontRectAbs(node, byId);
    const alongH = f === "N" || f === "S";
    const clampX = (x) => Math.min(fr.x + fr.w - 8, Math.max(fr.x + 8, x));
    const clampY = (y) => Math.min(fr.y + fr.h - 8, Math.max(fr.y + 8, y));
    const clearOf = (cx, cy) =>
      others.every((o) => Math.hypot(o.x - cx, o.y - cy) >= CLEAR);
    // Prefer 0, then left/down, then right/up.
    const deltas = [0, -NUDGE, NUDGE, -2 * NUDGE, 2 * NUDGE, -3 * NUDGE, 3 * NUDGE];
    for (const d of deltas) {
      const cx = alongH ? clampX(pt.x + d) : pt.x;
      const cy = alongH ? pt.y : clampY(pt.y + d);
      if (clearOf(cx, cy)) return { x: cx, y: cy };
    }
    if (alongH) return { x: clampX(pt.x - NUDGE), y: pt.y };
    return { x: pt.x, y: clampY(pt.y + NUDGE) };
  }

  /**
   * Where a B/F tube crosses the place contour (nearest side), nudged away
   * from any side opening on that face.
   */
  function planeContourEntryAbs(node, openingId, face, byId) {
    const plane = parsePlaneOpening(openingId);
    const f = (
      plane?.face ||
      face ||
      String(openingId || "?")[0] ||
      "?"
    ).toUpperCase();
    if (!plane || (f !== "B" && f !== "F")) {
      return openingAnchorAbs(node, openingId, face, byId);
    }
    const approach = planeApproachFace(node, openingId, f, byId);
    const local = planeAnchorLocal(node, openingId, f, byId);
    const a = absXY(node, byId);
    const frL = frontRectLocal(node);
    /** @type {{x:number,y:number}} */
    let mouth;
    if (approach === "N") mouth = { x: a.x + local.x, y: a.y + frL.y };
    else if (approach === "S") mouth = { x: a.x + local.x, y: a.y + frL.y + frL.h };
    else if (approach === "W") mouth = { x: a.x + frL.x, y: a.y + local.y };
    else if (approach === "E") mouth = { x: a.x + frL.x + frL.w, y: a.y + local.y };
    else mouth = { x: a.x + local.x, y: a.y + local.y };
    return nudgeOffSideOpenings(node, approach, mouth, byId);
  }

  /** Local (0,0) anchor for labels drawn inside the node group. */
  function openingAnchorLocal(node, openingId, face, byId) {
    const fr = frontRectLocal(node);
    const side = parseSideOpening(openingId);
    const plane = parsePlaneOpening(openingId);
    const rawFace = (
      side?.face ||
      plane?.face ||
      face ||
      (openingId || "?")[0] ||
      "?"
    ).toUpperCase();
    const placeMap = idMap(byId) || Object.fromEntries(
      (graph?.nodes || []).map((n) => [n.id, n])
    );
    const flips = effectiveFlips(node, placeMap);

    if (rawFace === "B" || rawFace === "F") {
      return planeAnchorLocal(node, openingId, rawFace, placeMap);
    }

    const visualFace = flipFace(rawFace, flips);
    const index = side?.index || 1;
    const n = sideSlotCount(node, rawFace, index);
    let t = index / (n + 1);
    // Mirror along-face order so slot indices stay visually consistent.
    if (
      (visualFace === "N" || visualFace === "S") && flips.we
    ) {
      t = 1 - t;
    } else if (
      (visualFace === "E" || visualFace === "W") && flips.ns
    ) {
      t = 1 - t;
    }
    if (visualFace === "N") return { x: fr.x + t * fr.w, y: fr.y, face: visualFace };
    if (visualFace === "S") return { x: fr.x + t * fr.w, y: fr.y + fr.h, face: visualFace };
    if (visualFace === "W") return { x: fr.x, y: fr.y + t * fr.h, face: visualFace };
    if (visualFace === "E") return { x: fr.x + fr.w, y: fr.y + t * fr.h, face: visualFace };
    return { x: fr.x + fr.w / 2, y: fr.y + fr.h / 2, face: visualFace };
  }

  /** Nearest contour face for routing stubs into a B/F opening. */
  function planeApproachFace(node, openingId, face, byId) {
    const p = openingAnchorAbs(node, openingId, face, byId);
    const fr = frontRectAbs(node, byId);
    const dists = [
      ["N", p.y - fr.y],
      ["S", fr.y + fr.h - p.y],
      ["W", p.x - fr.x],
      ["E", fr.x + fr.w - p.x],
    ];
    dists.sort((x, y) => x[1] - y[1]);
    return dists[0][0];
  }

  function routeFace(node, openingId, face, byId) {
    const f = String(
      face || (openingId || "?")[0] || "?"
    ).toUpperCase();
    if (f === "B" || f === "F") {
      return planeApproachFace(node, openingId, f, byId);
    }
    const placeMap = idMap(byId) || Object.fromEntries(
      (graph?.nodes || []).map((n) => [n.id, n])
    );
    return flipFace(f, effectiveFlips(node, placeMap));
  }

  function ensurePositions() {
    if (!graph) return;
    const byParent = {};
    for (const node of graph.nodes) {
      const key = node.parent || "";
      (byParent[key] ||= []).push(node);
    }
    for (const [parentKey, siblings] of Object.entries(byParent)) {
      let i = 0;
      const nested = Boolean(parentKey);
      for (const node of siblings) {
        if (node.x == null || node.y == null) {
          const ox = nested ? 28 : 80;
          const oy = nested ? 40 : 80;
          const gx = nested ? 160 : 200;
          const gy = nested ? 110 : 160;
          node.x = ox + (i % 4) * gx;
          node.y = oy + Math.floor(i / 4) * gy;
          dirtyLocal = true;
        }
        i += 1;
      }
    }
  }

  function clearSvg() {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    worldEl = null;
    nodesById = {};
    elementsById = {};
    edgePaths = [];
    edgePathsByConduitId.clear();
    cablePaths = [];
  }

  /** Cancel in-flight progressive ``render()`` passes. */
  function bumpRenderGen() {
    renderGen += 1;
    if (renderPassRaf) {
      cancelAnimationFrame(renderPassRaf);
      renderPassRaf = 0;
      // Tubes pass may have handed off an open geom cache to a cancelled rAF.
      endRouteGeomCache();
    }
    return renderGen;
  }

  /**
   * Queue the next paint pass after the browser has painted the previous one.
   * Double-rAF so places (or tubes) actually appear before the next heavy pass.
   * @param {number} gen
   * @param {() => void} fn
   */
  function scheduleRenderPass(gen, fn) {
    if (gen !== renderGen) return;
    renderPassRaf = requestAnimationFrame(() => {
      renderPassRaf = 0;
      if (gen !== renderGen) return;
      renderPassRaf = requestAnimationFrame(() => {
        renderPassRaf = 0;
        if (gen !== renderGen) return;
        fn();
      });
    });
  }

  /** Cancel in-flight progressive edge refresh after drag/resize. */
  function bumpEdgeRefreshGen() {
    edgeRefreshGen += 1;
    if (edgeRefreshRaf) {
      cancelAnimationFrame(edgeRefreshRaf);
      edgeRefreshRaf = 0;
    }
    if (edgeRefreshJob) {
      endRouteGeomCache();
      edgeRefreshJob = null;
    }
    return edgeRefreshGen;
  }

  /**
   * Run ``fn`` after the browser has painted (double-rAF).
   * @param {number} gen
   * @param {() => void} fn
   */
  function scheduleEdgeAfterPaint(gen, fn) {
    edgeRefreshRaf = requestAnimationFrame(() => {
      edgeRefreshRaf = 0;
      if (gen !== edgeRefreshGen) return;
      edgeRefreshRaf = requestAnimationFrame(() => {
        edgeRefreshRaf = 0;
        if (gen !== edgeRefreshGen) return;
        fn();
      });
    });
  }

  /**
   * Update one conduit item's SVG from a routed path.
   * @param {(typeof edgePaths)[number]} item
   * @param {{d:string,dCore?:string,segs:any[]}} routed
   * @param {number} roadW
   * @param {Record<string, any>} byId
   */
  function applyRoutedTubeVisual(item, routed, roadW, byId) {
    item.dPaint = routed.d;
    item.d = routed.dCore || routed.d;
    const displayD = conduitDisplayD(routed.d, byId, item.edge);
    for (const path of item.paths) path.setAttribute("d", displayD);
    const outline = item.paths[0];
    const tubeHit = item.paths.find((p) =>
      p.classList?.contains("edge-tube-hit")
    );
    const tube = item.paths.find((p) => p.classList?.contains("edge-tube"));
    const tubeCss = wireColorCss(item.edge.color || "GY");
    if (outline && outline.classList?.contains("edge-tube-outline")) {
      applyTubeOutlineVisibility(outline, tubeCss, roadW);
    }
    if (tubeHit) {
      tubeHit.setAttribute("data-hit-visual", String(roadW));
      tubeHit.style.strokeWidth = String(linkHitStrokeWorld(roadW));
    }
    if (tube) {
      tube.setAttribute("data-core-d", item.d);
      tube.style.strokeWidth = String(roadW);
      tube.style.stroke = tubeCss;
      tube.style.strokeOpacity = item.edge.color ? "0.85" : "0.25";
    }
  }

  /** One time-sliced batch of conduit re-routes for ``edgeRefreshJob``. */
  function refreshTubesChunk(gen) {
    const job = edgeRefreshJob;
    if (
      !job ||
      job.kind !== "tubes" ||
      job.gen !== gen ||
      gen !== edgeRefreshGen ||
      !graph
    ) {
      return;
    }
    const { byId, occupied } = job;
    const t0 = performance.now();
    while (job.index < edgePaths.length) {
      const item = edgePaths[job.index];
      job.index += 1;
      const n = (item.edge.contains || []).length;
      // Skip full cable layout here — hint widths; cables pass rebuilds layout.
      const lanes = tubeLaneCount(item.edge, null);
      const roadW = conduitRoadWidth(n, lanes);
      const half = roadW / 2;
      const routed = edgePathD(item.edge, byId, occupied, half);
      if (routed) {
        applyRoutedTubeVisual(item, routed, roadW, byId);
        for (const s of routed.segs) occupied.push(s);
      }
      if (performance.now() - t0 >= EDGE_REFRESH_BUDGET_MS) break;
    }
    if (job.index < edgePaths.length) {
      edgeRefreshRaf = requestAnimationFrame(() => {
        edgeRefreshRaf = 0;
        if (gen !== edgeRefreshGen) return;
        refreshTubesChunk(gen);
      });
      return;
    }
    indexEdgePaths();
    endRouteGeomCache();
    const onDone = job.onDone;
    edgeRefreshJob = null;
    onDone();
  }

  /**
   * Seed occupied segments from current tube paths (for cable rebuild).
   * @param {ReturnType<typeof buildCableLayout>|null} layout
   */
  function occupiedFromEdgePaths(layout) {
    const occupied = createOccupiedIndex();
    for (const item of edgePaths) {
      if (!item.d) continue;
      const n = (item.edge.contains || []).length;
      const lanes = tubeLaneCount(item.edge, layout);
      const roadW = conduitRoadWidth(n, lanes);
      const half = roadW / 2;
      for (const sub of pathDToSubpaths(item.d)) {
        for (const s of segsFromPoints(sub, half)) occupied.push(s);
      }
    }
    return occupied;
  }

  /** Time-sliced cable SVG rebuild (after tubes are already updated). */
  function refreshCablesChunk(gen) {
    const job = edgeRefreshJob;
    if (
      !job ||
      job.kind !== "cables" ||
      job.gen !== gen ||
      gen !== edgeRefreshGen ||
      !graph
    ) {
      return;
    }
    const { byId, elemById, occupied, layout, cablesG, edges } = job;
    const t0 = performance.now();
    while (job.index < edges.length) {
      const edge = edges[job.index];
      job.index += 1;
      const item = appendCableVisuals(
        cablesG,
        edge,
        byId,
        elemById,
        occupied,
        layout
      );
      if (item) cablePaths.push(item);
      if (performance.now() - t0 >= EDGE_REFRESH_BUDGET_MS) break;
    }
    if (job.index < edges.length) {
      edgeRefreshRaf = requestAnimationFrame(() => {
        edgeRefreshRaf = 0;
        if (gen !== edgeRefreshGen) return;
        refreshCablesChunk(gen);
      });
      return;
    }
    orderCableLayers(cablesG);
    endRouteGeomCache();
    edgeRefreshJob = null;
  }

  /**
   * Rebuild cables after a paint yield; layout runs here (tubes already visible).
   * @param {number} gen
   */
  function startProgressiveCableRebuild(gen) {
    scheduleEdgeAfterPaint(gen, () => {
      if (gen !== edgeRefreshGen || !graph) return;
      if (!showElectrical) return;
      const cablesG = worldEl && worldEl.querySelector("g.cables");
      if (!cablesG) return;
      const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
      const elemById = Object.fromEntries(
        (graph.elements || []).map((e) => [e.id, e])
      );
      beginRouteGeomCache(byId, elemById);
      // Expensive: deferred until tubes are on screen.
      const layout = buildCableLayout(graph.cable_edges || [], elemById, byId);
      const occupied = occupiedFromEdgePaths(layout);
      cablesG.innerHTML = "";
      cablePaths = [];
      edgeRefreshJob = {
        kind: "cables",
        gen,
        byId,
        elemById,
        occupied,
        layout,
        cablesG,
        edges: cablePaintOrder(graph.cable_edges),
        index: 0,
      };
      refreshCablesChunk(gen);
    });
  }

  /**
   * After drag/resize: yield so the moved box paints, re-route tubes in
   * frame-sized chunks, then rebuild cables in later frame slices.
   * @param {{ skipConduits?: boolean }} [opts]
   */
  function scheduleProgressiveEdgeRefresh(opts) {
    const skipConduits = !!(opts && opts.skipConduits);
    // Abort any unfinished full progressive paint; transforms already match.
    bumpRenderGen();
    const gen = bumpEdgeRefreshGen();

    // Drop stale strands immediately so a long refine does not show wrong cables.
    const cablesG = worldEl && worldEl.querySelector("g.cables");
    if (cablesG && showElectrical) {
      cablesG.innerHTML = "";
      cablePaths = [];
    }

    if (skipConduits) {
      startProgressiveCableRebuild(gen);
      return;
    }

    scheduleEdgeAfterPaint(gen, () => {
      if (gen !== edgeRefreshGen || !graph) return;
      const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
      const elemById = Object.fromEntries(
        (graph.elements || []).map((e) => [e.id, e])
      );
      beginRouteGeomCache(byId, elemById);
      edgeRefreshJob = {
        kind: "tubes",
        gen,
        byId,
        occupied: createOccupiedIndex(),
        index: 0,
        onDone: () => {
          if (!showElectrical) return;
          startProgressiveCableRebuild(gen);
        },
      };
      refreshTubesChunk(gen);
    });
  }

  function el(name, attrs, text) {
    const node = document.createElementNS(ns, name);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v != null) node.setAttribute(k, String(v));
      }
    }
    if (text != null) node.textContent = text;
    return node;
  }

  function syncZoomUi() {
    const pct = Math.round(scale * 100);
    const slider = document.getElementById("zoom-slider");
    const label = document.getElementById("zoom-label");
    if (slider && Number(slider.value) !== pct) {
      slider.value = String(Math.min(300, Math.max(5, pct)));
    }
    if (label) label.textContent = `${pct}%`;
  }

  function setScale(next, { anchorClientX, anchorClientY } = {}) {
    const clamped = Math.min(3, Math.max(0.05, next));
    if (clamped === scale) {
      syncZoomUi();
      return;
    }
    if (
      anchorClientX != null &&
      anchorClientY != null &&
      viewport
    ) {
      const rect = viewport.getBoundingClientRect();
      const mx = anchorClientX - rect.left;
      const my = anchorClientY - rect.top;
      const ratio = clamped / scale;
      panX = mx - (mx - panX) * ratio;
      panY = my - (my - panY) * ratio;
    }
    scale = clamped;
    applyWorldTransform();
    rememberCurrentDocView();
  }

  function applyWorldTransform() {
    if (worldEl) {
      worldEl.setAttribute(
        "transform",
        `translate(${panX},${panY}) scale(${scale})`
      );
    }
    syncLinkHitStrokes();
    syncZoomUi();
  }

  function contentBounds() {
    if (!graph?.nodes?.length) return null;
    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const n of graph.nodes) {
      const a = absXY(n, byId);
      const w = nodeW(n);
      const h = nodeH(n);
      minX = Math.min(minX, a.x);
      minY = Math.min(minY, a.y);
      maxX = Math.max(maxX, a.x + w);
      maxY = Math.max(maxY, a.y + h);
    }
    if (!Number.isFinite(minX)) return null;
    return { minX, minY, maxX, maxY, w: maxX - minX, h: maxY - minY };
  }

  function fitView() {
    const bounds = contentBounds();
    const rect = viewport.getBoundingClientRect();
    const viewW = Math.max(rect.width || 800, 100);
    const viewH = Math.max(rect.height || 600, 100);
    const pad = 48;
    if (!bounds || bounds.w < 1 || bounds.h < 1) {
      scale = 1;
      panX = 40;
      panY = 40;
      applyWorldTransform();
      rememberCurrentDocView();
      return;
    }
    const sx = (viewW - pad * 2) / bounds.w;
    const sy = (viewH - pad * 2) / bounds.h;
    scale = Math.min(3, Math.max(0.05, Math.min(sx, sy)));
    panX = pad - bounds.minX * scale + (viewW - pad * 2 - bounds.w * scale) / 2;
    panY = pad - bounds.minY * scale + (viewH - pad * 2 - bounds.h * scale) / 2;
    applyWorldTransform();
    rememberCurrentDocView();
  }

  function pointsToPathD(pts) {
    if (!pts.length) return "";
    let d = `M ${pts[0][0]} ${pts[0][1]}`;
    for (let i = 1; i < pts.length; i++) {
      d += ` L ${pts[i][0]} ${pts[i][1]}`;
    }
    return d;
  }

  function segsFromPoints(pts, half) {
    /** @type {{axis:string,x?:number,y?:number,a:number,b:number,half:number}[]} */
    const segs = [];
    const h = half != null ? Number(half) : 0;
    for (let i = 1; i < pts.length; i++) {
      const x1 = pts[i - 1][0];
      const y1 = pts[i - 1][1];
      const x2 = pts[i][0];
      const y2 = pts[i][1];
      if (Math.abs(x1 - x2) < 1e-6 && Math.abs(y1 - y2) < 1e-6) continue;
      if (Math.abs(y1 - y2) < 1e-6) {
        segs.push({
          axis: "H",
          y: y1,
          a: Math.min(x1, x2),
          b: Math.max(x1, x2),
          half: h,
        });
      } else if (Math.abs(x1 - x2) < 1e-6) {
        segs.push({
          axis: "V",
          x: x1,
          a: Math.min(y1, y2),
          b: Math.max(y1, y2),
          half: h,
        });
      }
    }
    return segs;
  }

  /**
   * Spatial grid over painted conduit/strand segments so stack/cross scoring
   * queries nearby segs instead of the full occupied list.
   * @param {number} [cellSize]
   */
  function createOccupiedIndex(cellSize) {
    const cell = cellSize && cellSize > 0 ? cellSize : 80;
    /** @type {{axis:string,x?:number,y?:number,a:number,b:number,half?:number}[]} */
    const segs = [];
    /** @type {Map<string, typeof segs>} */
    const buckets = new Map();
    const cellKey = (cx, cy) => `${cx},${cy}`;

    function boundsOf(s, pad) {
      const half = (Number(s.half) || 0) + (pad || 0);
      if (s.axis === "H") {
        return {
          x0: s.a - half,
          x1: s.b + half,
          y0: s.y - half,
          y1: s.y + half,
        };
      }
      return {
        x0: s.x - half,
        x1: s.x + half,
        y0: s.a - half,
        y1: s.b + half,
      };
    }

    function forEachCell(b, fn) {
      const c0 = Math.floor(b.x0 / cell);
      const c1 = Math.floor(b.x1 / cell);
      const r0 = Math.floor(b.y0 / cell);
      const r1 = Math.floor(b.y1 / cell);
      for (let cx = c0; cx <= c1; cx++) {
        for (let cy = r0; cy <= r1; cy++) {
          fn(cellKey(cx, cy));
        }
      }
    }

    return {
      push(s) {
        segs.push(s);
        forEachCell(boundsOf(s, 0), (k) => {
          let bucket = buckets.get(k);
          if (!bucket) {
            bucket = [];
            buckets.set(k, bucket);
          }
          bucket.push(s);
        });
      },
      get length() {
        return segs.length;
      },
      [Symbol.iterator]() {
        return segs[Symbol.iterator]();
      },
      /**
       * Segments that may conflict with ``s`` (padded AABB). Always uses the
       * spatial grid (even for the first painted segs) so early routes stay O(near).
       * @param {{axis:string,x?:number,y?:number,a:number,b:number,half?:number}} s
       * @param {number} [pad]
       */
      near(s, pad) {
        if (!segs.length) return segs;
        /** @type {Set<object>} */
        const hit = new Set();
        forEachCell(boundsOf(s, pad || 0), (k) => {
          const bucket = buckets.get(k);
          if (!bucket) return;
          for (const o of bucket) hit.add(o);
        });
        return hit.size ? [...hit] : segs;
      },
    };
  }

  function occupiedNear(occupied, s, pad) {
    if (!occupied) return [];
    if (typeof occupied.near === "function") return occupied.near(s, pad);
    return occupied;
  }

  function rangeOverlapLen(a1, a2, b1, b2) {
    return Math.max(0, Math.min(a2, b2) - Math.max(a1, b1));
  }

  /**
   * Colinear tube stack (rule 15) vs perpendicular crossing.
   * Stacks are expensive and beat bend-count in scoring; crossings are a
   * tiny soft cost so a short X is preferred over a long C-detour.
   * Separation floor is lane pitch (not a hard 6px) so legal parallel lanes
   * at STRAND_WIDTH+LANE_GAP do not force huge detours.
   */
  function segStackConflict(s, o, eps) {
    const clear =
      (Number(s.half) || 0) + (Number(o.half) || 0) + LANE_GAP;
    const need = Math.max(eps || 0, clear > 0 ? clear : LANE_PITCH);
    if (s.axis === "H" && o.axis === "H") {
      if (Math.abs(s.y - o.y) >= need - 1e-6) return 0;
      const ov = rangeOverlapLen(s.a, s.b, o.a, o.b);
      if (ov <= 1) return 0;
      return 200 + ov + (need - Math.abs(s.y - o.y));
    }
    if (s.axis === "V" && o.axis === "V") {
      if (Math.abs(s.x - o.x) >= need - 1e-6) return 0;
      const ov = rangeOverlapLen(s.a, s.b, o.a, o.b);
      if (ov <= 1) return 0;
      return 200 + ov + (need - Math.abs(s.x - o.x));
    }
    return 0;
  }

  function segCrossConflict(s, o) {
    if (s.axis === "H" && o.axis === "V") {
      const y = s.y;
      const x = o.x;
      if (x > s.a + 1 && x < s.b - 1 && y > o.a + 1 && y < o.b - 1) {
        return 1;
      }
    } else if (s.axis === "V" && o.axis === "H") {
      const x = s.x;
      const y = o.y;
      if (y > s.a + 1 && y < s.b - 1 && x > o.a + 1 && x < o.b - 1) {
        return 1;
      }
    }
    return 0;
  }

  function pathStackConflictCost(pts, occupied, eps, half) {
    if (!occupied || !occupied.length) return 0;
    let cost = 0;
    const pad = Math.max(eps || 0, LANE_PITCH);
    for (const s of segsFromPoints(pts, half)) {
      for (const o of occupiedNear(occupied, s, pad)) {
        cost += segStackConflict(s, o, eps);
      }
    }
    return cost;
  }

  function pathCrossConflictCost(pts, occupied, half) {
    if (!occupied || !occupied.length) return 0;
    let cost = 0;
    const pad = Math.max(Number(half) || 0, LANE_GAP);
    for (const s of segsFromPoints(pts, half)) {
      for (const o of occupiedNear(occupied, s, pad)) {
        cost += segCrossConflict(s, o);
      }
    }
    return cost;
  }

  /** @deprecated combined cost — prefer stack/cross split for scoring. */
  function pathConflictCost(pts, occupied, eps, half) {
    return (
      pathStackConflictCost(pts, occupied, eps, half) +
      pathCrossConflictCost(pts, occupied, half) * 25
    );
  }

  /** True when ``pt`` lies strictly inside the front-face rectangle. */
  function pointInPlaceInterior(pt, node, byId, pad) {
    if (!pt || !node) return false;
    const margin = pad == null ? 1 : pad;
    const fr = frontRectAbs(node, byId);
    return (
      pt.x > fr.x + margin &&
      pt.x < fr.x + fr.w - margin &&
      pt.y > fr.y + margin &&
      pt.y < fr.y + fr.h - margin
    );
  }

  /** Shrunk leaf-place rects as routing obstacles (skip rooms/containers). */
  function placeObstacles(byId, excludeIds, inset) {
    // Sprite AABB is already the painted hull (iso depth included in w/h).
    const pad = inset == null ? 2 : inset;
    if (
      routeGeomCache &&
      routeGeomCache.placeById === byId &&
      routeGeomCache.placeLeaves[String(pad)]
    ) {
      return filterCachedIdRects(
        routeGeomCache.placeLeaves[String(pad)],
        excludeIds
      );
    }
    const ex = new Set(excludeIds || []);
    /** @type {{x:number,y:number,w:number,h:number}[]} */
    const rects = [];
    for (const n of Object.values(byId)) {
      if (!n || ex.has(n.id)) continue;
      if (childrenOf(n.id).length) continue;
      const a = absXY(n, byId);
      const w = nodeW(n) - 2 * pad;
      const h = nodeH(n) - 2 * pad;
      if (w < 4 || h < 4) continue;
      rects.push({ x: a.x + pad, y: a.y + pad, w, h });
    }
    return rects;
  }

  /**
   * Element box rects as inbox routing obstacles (rule 17).
   * Include endpoint elements too: corridors must go *around* them and meet
   * the pin only via the outward lead (never pierce the box to the far face).
   */
  function elementObstacles(elemById, placeById, excludeIds, inset) {
    const pad = inset == null ? 2 : inset;
    if (
      routeGeomCache &&
      routeGeomCache.placeById === placeById &&
      routeGeomCache.elemById === elemById &&
      routeGeomCache.elements[String(pad)]
    ) {
      return filterCachedIdRects(
        routeGeomCache.elements[String(pad)],
        excludeIds
      );
    }
    const ex = new Set(excludeIds || []);
    /** @type {{x:number,y:number,w:number,h:number}[]} */
    const rects = [];
    for (const e of Object.values(elemById || {})) {
      if (!e || ex.has(e.id)) continue;
      const a = elementAbsXY(e, placeById);
      const w = (e.w ?? ELEM_W) - 2 * pad;
      const h = (e.h ?? ELEM_H) - 2 * pad;
      if (w < 4 || h < 4) continue;
      rects.push({ x: a.x + pad, y: a.y + pad, w, h });
    }
    return rects;
  }

  function pathObstacleCost(pts, obstacles, endSlack) {
    if (!obstacles || !obstacles.length || !pts || pts.length < 2) return 0;
    // Mouths on iso sprites sit inside the AABB; ignore overlaps near ends so
    // an outward stub can leave the box without a false obstacle hit.
    const slack =
      endSlack == null ? ISO_DEPTH + 24 : Math.max(0, Number(endSlack) || 0);
    const p0 = pts[0];
    const p1 = pts[pts.length - 1];
    const trimNear = (x, y, px, py) => {
      const dy = y - py;
      const dx = x - px;
      // Return 1D interval on the axis-aligned segment that lies inside the
      // slack circle around endpoint (px,py). Caller supplies the free axis.
      return null;
    };
    void trimNear;
    let cost = 0;
    for (const s of segsFromPoints(pts)) {
      for (const r of obstacles) {
        if (s.axis === "H") {
          if (s.y <= r.y || s.y >= r.y + r.h) continue;
          let lo = Math.max(Math.min(s.a, s.b), r.x);
          let hi = Math.min(Math.max(s.a, s.b), r.x + r.w);
          if (hi - lo <= 1) continue;
          if (slack > 0) {
            for (const ep of [p0, p1]) {
              const dy = Math.abs(s.y - ep[1]);
              if (dy >= slack) continue;
              const half = Math.sqrt(Math.max(0, slack * slack - dy * dy));
              const t0 = ep[0] - half;
              const t1 = ep[0] + half;
              // Subtract [t0,t1] from [lo,hi] — keep only the far remainder.
              if (t1 <= lo || t0 >= hi) continue;
              if (t0 <= lo && t1 >= hi) {
                lo = hi;
                break;
              }
              if (t0 <= lo) lo = t1;
              else if (t1 >= hi) hi = t0;
              else {
                // Hole in the middle: charge both sides.
                const left = t0 - lo;
                const right = hi - t1;
                if (left > 1) cost += 180 + left;
                if (right > 1) cost += 180 + right;
                lo = hi;
                break;
              }
            }
          }
          const ov = hi - lo;
          if (ov > 1) cost += 180 + ov;
        } else {
          if (s.x <= r.x || s.x >= r.x + r.w) continue;
          let lo = Math.max(Math.min(s.a, s.b), r.y);
          let hi = Math.min(Math.max(s.a, s.b), r.y + r.h);
          if (hi - lo <= 1) continue;
          if (slack > 0) {
            for (const ep of [p0, p1]) {
              const dx = Math.abs(s.x - ep[0]);
              if (dx >= slack) continue;
              const half = Math.sqrt(Math.max(0, slack * slack - dx * dx));
              const t0 = ep[1] - half;
              const t1 = ep[1] + half;
              if (t1 <= lo || t0 >= hi) continue;
              if (t0 <= lo && t1 >= hi) {
                lo = hi;
                break;
              }
              if (t0 <= lo) lo = t1;
              else if (t1 >= hi) hi = t0;
              else {
                const left = t0 - lo;
                const right = hi - t1;
                if (left > 1) cost += 180 + left;
                if (right > 1) cost += 180 + right;
                lo = hi;
                break;
              }
            }
          }
          const ov = hi - lo;
          if (ov > 1) cost += 180 + ov;
        }
      }
    }
    return cost;
  }

  /**
   * Small rects around opening mouths that are not this edge's endpoints.
   * Keeps mark-to-mark routes from riding through a neighbor boca on the
   * same box (Route_28). Optional ``nodeIds`` limits to those nodes.
   */
  function foreignMouthObstacleRects(byId, excludeKeys, pad, nodeIds) {
    const r = Math.max(4, Number(pad) || OPENING_MARK_R);
    /** @type {{x:number,y:number,w:number,h:number}[]} */
    const rects = [];
    for (const node of Object.values(byId || {})) {
      if (!node || !node.id || !nodeHasOpeningMarks(node)) continue;
      if (nodeIds && !nodeIds.has(node.id)) continue;
      for (const oid of openingCellsForNode(node)) {
        const key = `${node.id}\0${oid}`;
        if (excludeKeys && excludeKeys.has(key)) continue;
        const m = openingMouthAbs(node, oid, oid?.[0], byId);
        if (!m) continue;
        rects.push({
          x: m.x - r,
          y: m.y - r,
          w: 2 * r,
          h: 2 * r,
        });
      }
    }
    return rects;
  }

  /** Soft cost for vertices that leave a parent content rect (same-room tubes). */
  function pathOutsideBoundsCost(pts, bounds) {
    if (!bounds || !pts || !pts.length) return 0;
    let cost = 0;
    const x0 = bounds.x;
    const y0 = bounds.y;
    const x1 = bounds.x + bounds.w;
    const y1 = bounds.y + bounds.h;
    const pad = 2;
    for (const p of pts) {
      if (
        p[0] < x0 - pad ||
        p[0] > x1 + pad ||
        p[1] < y0 - pad ||
        p[1] > y1 + pad
      ) {
        cost += 400;
      }
    }
    return cost;
  }

  /** Preferred gap from a place outer wall (same order as exit stubs). */
  const WALL_CLEARANCE = 24;

  /**
   * Soft cost for segments that run flush along a place outer wall.
   * Pushes the scorer toward a clearance C instead of wall-sliding.
   * Clearance matches the face stub so the open side of a C is not much
   * wider than the exit jog at the mouth.
   */
  function pathBorderHugCost(pts, rects, clearance) {
    if (!pts || pts.length < 2 || !rects || !rects.length) return 0;
    const clear = clearance == null ? WALL_CLEARANCE : clearance;
    let cost = 0;
    for (const s of segsFromPoints(pts)) {
      for (const r of rects) {
        if (s.axis === "V") {
          const nearL = Math.abs(s.x - r.x) < clear;
          const nearR = Math.abs(s.x - (r.x + r.w)) < clear;
          if (!nearL && !nearR) continue;
          const ov = rangeOverlapLen(s.a, s.b, r.y, r.y + r.h);
          if (ov > 8) cost += 80 + ov;
        } else {
          const nearT = Math.abs(s.y - r.y) < clear;
          const nearB = Math.abs(s.y - (r.y + r.h)) < clear;
          if (!nearT && !nearB) continue;
          const ov = rangeOverlapLen(s.a, s.b, r.x, r.x + r.w);
          if (ov > 8) cost += 80 + ov;
        }
      }
    }
    return cost;
  }

  /**
   * Penalize a long final approach into the destination face so the open
   * side of a C stays near WALL_CLEARANCE (like the mouth exit stub).
   */
  function pathEntryExcessCost(pts, toFace) {
    if (!pts || pts.length < 2 || !toFace) return 0;
    const a = pts[pts.length - 2];
    const b = pts[pts.length - 1];
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const f = String(toFace).toUpperCase();
    let span = 0;
    if (f === "W" || f === "E") {
      if (Math.abs(dy) > 1e-6) return 0;
      span = Math.abs(dx);
    } else if (f === "N" || f === "S") {
      if (Math.abs(dx) > 1e-6) return 0;
      span = Math.abs(dy);
    } else {
      return 0;
    }
    return Math.max(0, span - WALL_CLEARANCE) * 3;
  }

  function placeBorderRects(byId) {
    if (routeGeomCache && routeGeomCache.placeById === byId) {
      return routeGeomCache.borderRects;
    }
    /** @type {{x:number,y:number,w:number,h:number}[]} */
    const rects = [];
    for (const n of Object.values(byId || {})) {
      if (!n) continue;
      // Hug rails follow the front face (poker lid), not the iso NW margin.
      rects.push(frontRectAbs(n, byId));
    }
    return rects;
  }

  /**
   * Orthogonal route points from p1 to p2. When ``occupied`` is set, prefer
   * candidates that avoid colinear overlap (and lightly avoid crossings).
   * ``obstacles`` are place rects to go around (C / outer rails).
   */
