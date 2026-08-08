  /* === 04-render.js: Node/element paint, progressive render, inspectors, electrical ===
   * Fragment of the UI IIFE (bundled into ../app.js).
   * Edit this file, then run: python scripts/bundle_ui_app.py
   */
  function paintNode(node, layerG, byId) {
    const a = absXY(node, byId);
    const w = nodeW(node);
    const h = nodeH(node);
    const hasKids = childrenOf(node.id).length > 0;
    const showOpenings = !hasKids && nodeHasOpeningMarks(node);
    const fr = frontRectLocal(node);
    const g = el("g", {
      class: "node" + (hasKids ? " container" : ""),
      "data-id": node.id,
      transform: `translate(${a.x},${a.y})`,
    });
    if (showOpenings) {
      appendNodeIsoBevel(g, w, h);
    }
    const box = el("rect", {
      class:
        "node-box" +
        (selectedIds.has(node.id) ? " selected" : "") +
        (hasKids ? " container" : "") +
        (node.expandable ? " expandable" : "") +
        (showOpenings ? " iso-box" : ""),
      x: fr.x,
      y: fr.y,
      width: fr.w,
      height: fr.h,
      rx: showOpenings ? 0 : 6,
    });
    g.appendChild(box);
    const wireLayer = g.querySelector("g.node-iso-wires");
    if (wireLayer) g.appendChild(wireLayer);
    const fullLabel = node.display_label || node.label || node.display_name || node.name || node.id;
    const canvasName =
      (node.display_name || node.name || node.id) +
      (node.expandable ? " · +" : "");
    const typeHint = node.type_label || node.type || "";
    g.appendChild(
      el(
        "title",
        null,
        typeHint ? `${fullLabel} · ${typeHint}` : fullLabel
      )
    );
    appendIconWithLabel(g, {
      icon: node.icon,
      labelText: canvasName,
      x: fr.x + 8,
      y: fr.y + 18,
      maxW: fr.w - 16,
      textClass: "node-label",
    });

    if (showOpenings) {
      const cells = openingCellsForNode(node);
      // Far marks first so near strokes paint on top when they overlap.
      const ordered = [...cells].sort((a, b) => {
        const ma = openingMarkLocal(node, a, byId);
        const mb = openingMarkLocal(node, b, byId);
        if (ma.near !== mb.near) return ma.near ? 1 : -1;
        return 0;
      });
      for (const oid of ordered) {
        const mark = openingMarkLocal(node, oid, byId);
        const nearFar = mark.near ? "opening-near" : "opening-far";
        const faceClass = `opening-face-${mark.face || "X"}`;
        const circle = el("circle", {
          class: `opening-mark ${nearFar} ${faceClass}`,
          "data-opening": oid,
          cx: mark.x,
          cy: mark.y,
          r: OPENING_MARK_R,
        });
        circle.appendChild(el("title", null, oid));
        g.appendChild(circle);
        g.appendChild(
          el(
            "text",
            {
              class: `opening-label ${nearFar} ${faceClass}`,
              "data-opening": oid,
              x: mark.x,
              y: mark.y + 3,
              "text-anchor": "middle",
            },
            oid
          )
        );
      }
      g.querySelectorAll("[data-opening]").forEach((elOp) => {
        elOp.addEventListener("pointerdown", (ev) => {
          const oid = elOp.getAttribute("data-opening");
          if (oid && onWiringOpeningClick(node.id, oid, ev)) return;
        });
      });
    }

    box.addEventListener("pointerdown", (ev) => {
      if (shouldPanPointer(ev)) {
        ev.preventDefault();
        ev.stopPropagation();
        beginPanDrag(ev);
        return;
      }
      if (ev.button !== 0) return;
      // While wiring, snap to openings — never start place drag/select.
      if (
        wiringMode?.kind === "conduit" ||
        wiringMode?.kind === "conductor"
      ) {
        ev.preventDefault();
        ev.stopPropagation();
        tryWiringSnapAtPointer(ev.clientX, ev.clientY);
        return;
      }
      if (wiringMode) {
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
      ev.stopPropagation();
      // Shift+drag marquee must work on place floor (not only empty canvas).
      if (beginMarquee(ev)) return;
      raiseNode(node.id);
      if (isModClick(ev)) {
        toggleSelectionId(node.id);
        syncInspectorFromSelection();
        if (!selectedIds.has(node.id)) {
          drag = null;
          return;
        }
      } else if (!selectedIds.has(node.id)) {
        replaceSelection(node.id);
      }
      if (!selectedIds.has(node.id)) {
        drag = null;
        syncInspectorFromSelection();
        return;
      }
      const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
      const abs = absXY(node, byId);
      const world = clientToWorld(ev.clientX, ev.clientY);
      const handle = hitResizeHandle(
        world.x - abs.x,
        world.y - abs.y,
        nodeW(node),
        nodeH(node)
      );
      if (handle) {
        beginResizeDrag(
          ev,
          "place",
          node.id,
          handle,
          {
            x: node.x ?? 0,
            y: node.y ?? 0,
            w: nodeW(node),
            h: nodeH(node),
          }
        );
        return;
      }
      // Defer capture until real drag — early capture kills dblclick.
      drag = {
        kind: "multi",
        anchorId: node.id,
        anchorKind: "place",
        pointerId: ev.pointerId,
        startClientX: ev.clientX,
        startClientY: ev.clientY,
        items: buildDragItems(),
        layoutSnapshot: captureLayoutSnapshot(),
        moved: false,
        captured: false,
        modClick: isModClick(ev),
      };
    });
    box.addEventListener("pointermove", (ev) => {
      if (drag || panDrag || marquee) return;
      const byId = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
      const abs = absXY(node, byId);
      const world = clientToWorld(ev.clientX, ev.clientY);
      const handle = hitResizeHandle(
        world.x - abs.x,
        world.y - abs.y,
        nodeW(node),
        nodeH(node)
      );
      setResizeHoverCursor(handle, box);
    });
    box.addEventListener("pointerleave", () => {
      clearResizeHoverCursor(box);
    });

    layerG.appendChild(g);
    nodesById[node.id] = g;
  }

  function paintElement(elem, layerG, placeById) {
    const a = elementAbsXY(elem, placeById);
    const w = elem.w ?? ELEM_W;
    const h = elem.h ?? ELEM_H;
    const g = el("g", {
      class: "element-node",
      "data-id": elem.id,
      transform: `translate(${a.x},${a.y})`,
    });
    const box = el("rect", {
      class: "element-box" + (selectedIds.has(elem.id) ? " selected" : ""),
      width: w,
      height: h,
      rx: 3,
    });
    g.appendChild(box);
    const title =
      (elem.display_label || elem.label || elem.display_name || elem.name || elem.id) +
      (elem.type_label || elem.type
        ? ` · ${elem.type_label || elem.type}`
        : "");
    g.appendChild(el("title", null, title));
    appendIconWithLabel(g, {
      icon: elem.icon,
      labelText: elem.display_name || elem.name || elem.leaf_id || elem.id,
      x: 4,
      y: 14,
      maxW: w - 8,
      textClass: "element-label",
    });
    // Terminal cells from terminal_grid (N1, S2, …).
    const grid = elem.terminal_grid;
    if (grid && typeof grid === "object") {
      for (const face of Object.keys(grid)) {
        const raw = grid[face];
        let cols = 1;
        let rows = 1;
        if (Array.isArray(raw)) {
          cols = Math.max(1, Number(raw[0]) || 1);
          rows = Math.max(1, Number(raw[1]) || 1);
        }
        const n = cols * rows;
        for (let i = 1; i <= n; i++) {
          const cellId = `${face}${i}`;
          const local = terminalCellAnchorLocal(elem, cellId, placeById);
          const mark = el("circle", {
            class: "element-terminal",
            cx: String(local.x),
            cy: String(local.y),
            r: "2.75",
            "data-terminal": cellId,
          });
          mark.appendChild(el("title", null, cellId));
          mark.addEventListener("pointerdown", (ev) => {
            if (onWiringTerminalClick(elem, cellId, ev)) return;
          });
          g.appendChild(mark);
        }
      }
    }
    box.addEventListener("pointerdown", (ev) => {
      if (shouldPanPointer(ev)) {
        ev.preventDefault();
        ev.stopPropagation();
        beginPanDrag(ev);
        return;
      }
      if (ev.button !== 0) return;
      // While wiring, snap to terminals — never start element drag/select.
      if (wiringMode?.kind === "conductor") {
        ev.preventDefault();
        ev.stopPropagation();
        tryWiringSnapAtPointer(ev.clientX, ev.clientY);
        return;
      }
      if (wiringMode) {
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
      ev.stopPropagation();
      // Allow Shift+drag marquee to start on an element hit target too.
      if (beginMarquee(ev)) return;
      const gEl = elementsById[elem.id];
      if (gEl && gEl.parentNode) gEl.parentNode.appendChild(gEl);
      if (isModClick(ev)) {
        toggleSelectionId(elem.id);
        syncInspectorFromSelection();
        if (!selectedIds.has(elem.id)) {
          drag = null;
          return;
        }
      } else if (!selectedIds.has(elem.id)) {
        replaceSelection(elem.id);
      }
      if (!selectedIds.has(elem.id)) {
        drag = null;
        syncInspectorFromSelection();
        return;
      }
      const byId = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
      const abs = elementAbsXY(elem, byId);
      const world = clientToWorld(ev.clientX, ev.clientY);
      const w = elem.w ?? ELEM_W;
      const h = elem.h ?? ELEM_H;
      const handle = hitResizeHandle(world.x - abs.x, world.y - abs.y, w, h);
      if (handle) {
        beginResizeDrag(ev, "element", elem.id, handle, {
          x: elem.x ?? 0,
          y: elem.y ?? 0,
          w,
          h,
        });
        return;
      }
      drag = {
        kind: "multi",
        anchorId: elem.id,
        anchorKind: "element",
        pointerId: ev.pointerId,
        startClientX: ev.clientX,
        startClientY: ev.clientY,
        items: buildDragItems(),
        layoutSnapshot: captureLayoutSnapshot(),
        moved: false,
        captured: false,
        modClick: isModClick(ev),
      };
    });
    box.addEventListener("pointermove", (ev) => {
      if (drag || panDrag || marquee || !showElectrical) return;
      const byId = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
      const abs = elementAbsXY(elem, byId);
      const world = clientToWorld(ev.clientX, ev.clientY);
      const handle = hitResizeHandle(
        world.x - abs.x,
        world.y - abs.y,
        elem.w ?? ELEM_W,
        elem.h ?? ELEM_H
      );
      setResizeHoverCursor(handle, box);
    });
    box.addEventListener("pointerleave", () => {
      clearResizeHoverCursor(box);
    });
    layerG.appendChild(g);
    elementsById[elem.id] = g;
  }

  function raiseNode(id) {
    const gEl = nodesById[id];
    if (gEl && gEl.parentNode) gEl.parentNode.appendChild(gEl);
    for (const kid of childrenOf(id)) raiseNode(kid.id);
  }

  function terminalFanHalfWidth(cableCount) {
    const n = Math.max(1, cableCount | 0);
    if (n <= 1) return 0;
    return ((n - 1) / 2) * TERMINAL_FAN_PITCH;
  }

  /**
   * Widen elements so multi-cable terminal V fans on consecutive cells do not
   * overlap (rule 11/15). Growing the element also grows the host place via
   * ``measureVisibleSizes``.
   * @returns {boolean} true if any element size changed
   */
  function expandElementsForTerminalFans(layout, elemById) {
    if (!layout) return false;
    let changed = false;
    for (const elem of Object.values(elemById || {})) {
      const grid = elem.terminal_grid;
      if (!grid || typeof grid !== "object") continue;
      let needW = elem.w ?? ELEM_W;
      let needH = elem.h ?? ELEM_H;
      for (const face of Object.keys(grid)) {
        const raw = grid[face];
        let cols = 1;
        let rows = 1;
        if (Array.isArray(raw)) {
          cols = Math.max(1, Number(raw[0]) || 1);
          rows = Math.max(1, Number(raw[1]) || 1);
        }
        const n = cols * rows;
        if (n < 1) continue;
        /** @type {number[]} */
        const counts = [];
        for (let i = 1; i <= n; i++) {
          counts.push(layout.cellCableCount(elem.id, `${face}${i}`) || 0);
        }
        const edgePad = 4;
        let minAlong = face === "N" || face === "S" ? ELEM_W : ELEM_H;
        // Equal slot layout uses t = i/(n+1); spacing = size/(n+1).
        const edgeHalf = Math.max(
          terminalFanHalfWidth(counts[0]),
          terminalFanHalfWidth(counts[n - 1])
        );
        minAlong = Math.max(minAlong, (edgeHalf + edgePad) * (n + 1));
        for (let i = 0; i < n - 1; i++) {
          const pair =
            terminalFanHalfWidth(counts[i]) +
            terminalFanHalfWidth(counts[i + 1]) +
            TERMINAL_FAN_CLEAR;
          minAlong = Math.max(minAlong, pair * (n + 1));
        }
        if (face === "N" || face === "S") needW = Math.max(needW, minAlong);
        else if (face === "E" || face === "W") needH = Math.max(needH, minAlong);
      }
      const curW = elem.w ?? ELEM_W;
      const curH = elem.h ?? ELEM_H;
      if (needW > curW + 0.5 || needH > curH + 0.5) {
        elem.w = needW;
        elem.h = needH;
        changed = true;
      }
    }
    return changed;
  }

  function render() {
    if (!graph) return;
    // Invalidate unfinished progressive paint and post-drag edge refine.
    bumpEdgeRefreshGen();
    const gen = bumpRenderGen();
    ensurePositions();
    measureVisibleSizes();

    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    const elemById = Object.fromEntries(
      (graph.elements || []).map((e) => [e.id, e])
    );

    // Pass 0 — places only (no cable layout: that blocked first paint).
    clearSvg();

    worldEl = el("g", { id: "world" });
    applyWorldTransform();
    svg.appendChild(worldEl);

    // Layer order: containers → leaves → conduits → elements → cables.
    const containersG = el("g", { class: "containers" });
    const leavesG = el("g", { class: "leaves" });
    const edgesG = el("g", { class: "edges" });
    const cablesG = el("g", { class: "cables" });
    const elementsG = el("g", { class: "elements" });
    worldEl.appendChild(containersG);
    worldEl.appendChild(leavesG);
    worldEl.appendChild(edgesG);
    worldEl.appendChild(elementsG);
    worldEl.appendChild(cablesG);

    const byDepth = [...graph.nodes].sort(
      (a, b) => (a.parts?.length || 0) - (b.parts?.length || 0)
    );
    for (const node of byDepth) {
      if (childrenOf(node.id).length) paintNode(node, containersG, byId);
    }
    for (const node of graph.nodes) {
      if (!childrenOf(node.id).length) paintNode(node, leavesG, byId);
    }
    updateDepthLabel();
    // Force layout so the browser can paint boxes before the tubes pass.
    void svg.getBoundingClientRect();

    scheduleRenderPass(gen, () => {
      renderPassTubes(gen, byId, elemById, edgesG, elementsG, cablesG);
    });
  }

  /**
   * Pass 1 — conduits (after places). Builds cable layout here when Electrical
   * is on so tube widths stay accurate without delaying the places paint.
   * @param {number} gen
   * @param {Record<string, any>} byId
   * @param {Record<string, any>} elemById
   * @param {SVGGElement} edgesG
   * @param {SVGGElement} elementsG
   * @param {SVGGElement} cablesG
   */
  function renderPassTubes(gen, byId, elemById, edgesG, elementsG, cablesG) {
    if (gen !== renderGen || !graph || !worldEl) return;

    /** @type {ReturnType<typeof buildCableLayout>|null} */
    let layout = null;
    if (showElectrical) {
      layout = buildCableLayout(graph.cable_edges || [], elemById, byId);
      if (expandElementsForTerminalFans(layout, elemById)) {
        measureVisibleSizes();
        layout = buildCableLayout(graph.cable_edges || [], elemById, byId);
        // Places already painted; sync box sizes if fans grew elements' hosts.
        updateNodeVisual(null, { refresh: false });
      }
    }

    beginRouteGeomCache(byId, elemById);
    /** @type {ReturnType<typeof createOccupiedIndex>} */
    let occupied = createOccupiedIndex();
    let handOffCache = false;
    try {
      edgePaths = [];
      edgesG.innerHTML = "";
      for (const edge of graph.edges) {
        const n = (edge.contains || []).length;
        const lanes = tubeLaneCount(edge, layout);
        const roadW = conduitRoadWidth(n, lanes);
        const half = roadW / 2;
        const routed = edgePathD(edge, byId, occupied, half);
        if (!routed) continue;
        const dPaint = routed.d;
        const dCore = routed.dCore || dPaint;
        for (const s of routed.segs) occupied.push(s);
        const contains = (edge.contains || []).join(", ");
        const edgeName = edge.name || edge.id;
        const title = contains
          ? `${edgeName}: ${contains}`
          : String(edgeName || "");
        const displayD = conduitDisplayD(dPaint, byId, edge);
        const tubeCss = wireColorCss(edge.color || "GY");
        const tubeOutline = el("path", {
          class: "edge-tube-outline",
          d: displayD,
        });
        applyTubeOutlineVisibility(tubeOutline, tubeCss, roadW);
        const tubeHit = el("path", {
          class: "edge-tube-hit",
          d: displayD,
          "data-link-id": edge.id,
          "data-link-kind": "conduit",
          "data-hit-visual": String(roadW),
        });
        tubeHit.style.strokeWidth = String(linkHitStrokeWorld(roadW));
        bindLinkHit(tubeHit, edge.id, "conduit");
        const tube = el("path", {
          class: "edge-tube",
          d: displayD,
          "data-link-id": edge.id,
          "data-link-kind": "conduit",
          "data-core-d": dCore,
        });
        tube.style.stroke = tubeCss;
        tube.style.strokeWidth = String(roadW);
        tube.style.strokeOpacity = edge.color ? "0.85" : "0.25";
        tube.appendChild(el("title", null, title));
        edgesG.appendChild(tubeOutline);
        edgesG.appendChild(tubeHit);
        edgesG.appendChild(tube);
        edgePaths.push({
          edge,
          paths: [tubeOutline, tubeHit, tube],
          d: dCore,
          dPaint,
        });
      }
      indexEdgePaths();
      void svg.getBoundingClientRect();

      if (!showElectrical) {
        renderExpandPass = 0;
        updateDepthLabel();
        return;
      }

      // Keep geom cache open for the electrical pass (same session as sync paint).
      handOffCache = true;
      scheduleRenderPass(gen, () => {
        renderPassElectrical(
          gen,
          byId,
          elemById,
          layout,
          occupied,
          elementsG,
          cablesG
        );
      });
      if (gen !== renderGen) handOffCache = false;
    } finally {
      if (!handOffCache) endRouteGeomCache();
    }
  }

  /**
   * Pass 2 — elements + cables (Electrical on).
   * @param {number} gen
   * @param {Record<string, any>} byId
   * @param {Record<string, any>} elemById
   * @param {ReturnType<typeof buildCableLayout>|null} layout
   * @param {ReturnType<typeof createOccupiedIndex>} occupied
   * @param {SVGGElement} elementsG
   * @param {SVGGElement} cablesG
   */
  function renderPassElectrical(
    gen,
    byId,
    elemById,
    layout,
    occupied,
    elementsG,
    cablesG
  ) {
    try {
      if (gen !== renderGen || !graph || !worldEl || !showElectrical) return;
      // Cache should still be open from the tubes pass; refresh if cancelled.
      if (!routeGeomCache) beginRouteGeomCache(byId, elemById);
      // Fan expand may have changed element sizes since pass 0; refresh layout.
      let cableLayout =
        layout || buildCableLayout(graph.cable_edges || [], elemById, byId);
      if (expandElementsForTerminalFans(cableLayout, elemById)) {
        measureVisibleSizes();
        for (const e of graph.elements || []) {
          updateElementVisual(e, byId);
        }
        cableLayout = buildCableLayout(graph.cable_edges || [], elemById, byId);
      }

      elementsG.innerHTML = "";
      for (const elem of graph.elements || []) {
        if (elem.parent && !byId[elem.parent]) continue;
        if (elem.parent && childrenOf(elem.parent).length) continue;
        paintElement(elem, elementsG, byId);
      }

      cablesG.innerHTML = "";
      cablePaths = [];
      inboxCablePtsByParent = {};
      for (const edge of graph.cable_edges || []) {
        const item = appendCableVisuals(
          cablesG,
          edge,
          byId,
          elemById,
          occupied,
          cableLayout
        );
        if (item) cablePaths.push(item);
      }
      if (
        renderExpandPass < 1 &&
        expandPlacesForInboxCables(inboxCablePtsByParent, byId)
      ) {
        inboxCablePtsByParent = null;
        renderExpandPass += 1;
        // Grow boxes and progressive re-route — avoid blocking full clearSvg.
        updateNodeVisual(null, { progressive: true });
        renderExpandPass = 0;
        updateDepthLabel();
        return;
      }
      inboxCablePtsByParent = null;
      renderExpandPass = 0;
      updateDepthLabel();
    } finally {
      endRouteGeomCache();
    }
  }

  async function selectElement(elem) {
    replaceSelection(elem.id);
    highlightOutlineSelection();
    await fillElementInspector(elem);
  }

  function setInspectorMode(mode) {
    const elements = document.getElementById("props-elements-block");
    const conduits = document.getElementById("props-conduits-block");
    const cables = document.getElementById("props-cables-block");
    const placeMode = mode === "place";
    const linkMode = mode === "link";
    if (elements) {
      elements.classList.toggle(
        "hidden",
        linkMode || !placeMode || !showElectrical || !propsShowElements
      );
    }
    if (conduits) conduits.classList.toggle("hidden", linkMode || !placeMode);
    if (cables) cables.classList.toggle("hidden", linkMode || placeMode);
  }

  /**
   * True when this place's electrical elements are painted on the canvas
   * (electrical on + leaf place in the current depth view).
   */
  let propsShowElements = false;

  function placeShowsElementsInView(placeRelId) {
    if (!showElectrical || !graph) return false;
    if (!placeRelId || placeRelId === ".") return true;
    if (selectedIds.size === 1 && selectedId === placeRelId) return true;
    return childrenOf(placeRelId).length === 0;
  }

  /** Conduits drawn on the current canvas (same set as graph.edges). */
  function filterConduitsToView(conduits) {
    const visible = new Set((graph?.edges || []).map((e) => String(e.id)));
    return (conduits || []).filter((c) => visible.has(String(c.id)));
  }

  function ensurePropertiesVisible() {
    const side = document.getElementById("side-panel");
    if (side && side.classList.contains("collapsed")) {
      setSidePanelCollapsed("inspector", false);
    }
  }

  /** @type {{kind:"place"|"element", placeId:string, element?:string}|null} */
  let propsTarget = null;
  /** Keep openings/terminals <details> open across inspector rebuilds. */
  let propsFaceEditorOpen = false;
  /** @type {string|null} */
  let propsFaceEditorKey = null;

  function propsFaceEditorStorageKey() {
    if (!propsTarget) return null;
    if (propsTarget.kind === "element") {
      return `e:${propsTarget.placeId || "."}/${propsTarget.element || ""}`;
    }
    if (propsTarget.kind === "place") {
      return `p:${propsTarget.placeId || "."}`;
    }
    return null;
  }

  function syncPropsFaceEditorKey() {
    const key = propsFaceEditorStorageKey();
    if (key !== propsFaceEditorKey) {
      propsFaceEditorKey = key;
      propsFaceEditorOpen = false;
    }
  }
  let propsSaveTimer = null;
  /** JSON snapshot of editable props when the panel was built (skip no-op saves). */
  let propsFieldsBaseline = null;
  /** @type {Promise<void>|null} */
  let propsSavePromise = null;
  function propsLabel(key) {
    return t(`props.key.${key}`);
  }

  function propsValueLabel(group, value) {
    const key = `props.${group}.${value}`;
    const text = t(key);
    return text === key ? String(value) : text;
  }

  /** Catalog type key from ``/api/catalog`` row (``type``; legacy ``id``). */
  function catalogTypeKey(row) {
    return String((row && (row.type || row.id)) || "").trim();
  }

  /** Catalog subtype key from subtype row (``subtype``; legacy ``id``). */
  function catalogSubtypeKey(sub) {
    return String((sub && (sub.subtype || sub.id)) || "").trim();
  }

  /** Closed subtype keys + localized labels from ``/api/catalog``. */
  function catalogSubtypeSelect(typeId) {
    const row = (paletteCatalog && typeId && paletteCatalog[typeId]) || null;
    const subs = (row && row.subtypes) || [];
    if (!Array.isArray(subs) || !subs.length) {
      return { options: null, optionLabels: null };
    }
    /** @type {Record<string, string>} */
    const optionLabels = {};
    const options = [];
    for (const sub of subs) {
      const id = catalogSubtypeKey(sub);
      if (!id) continue;
      options.push(id);
      optionLabels[id] = String((sub && sub.label) || id);
    }
    return { options, optionLabels };
  }

  function orientationNsFromFlip(flag) {
    return flag ? "south_to_north" : "north_to_south";
  }

  function orientationWeFromFlip(flag) {
    return flag ? "east_to_west" : "west_to_east";
  }

  function flipFromOrientationNs(value) {
    return String(value || "").trim() === "south_to_north";
  }

  function flipFromOrientationWe(value) {
    return String(value || "").trim() === "east_to_west";
  }

  function readPropsFieldsFromPanel(meta) {
    /** @type {Record<string, string|boolean|object>} */
    const fields = {};
    if (!meta) return fields;
    meta.querySelectorAll("[data-prop]").forEach((el) => {
      const key = el.getAttribute("data-prop");
      if (!key) return;
      if (el.type === "checkbox") fields[key] = el.checked;
      else fields[key] = el.value;
    });
    meta.querySelectorAll("[data-prop-json]").forEach((el) => {
      const key = el.getAttribute("data-prop-json");
      if (!key) return;
      try {
        fields[key] = JSON.parse(el.value || "null");
      } catch (_err) {
        /* keep previous / skip */
      }
    });
    // Orientation selects map to flip_* boolean fields for the API.
    meta.querySelectorAll("select[data-prop]").forEach((el) => {
      const key = el.getAttribute("data-prop");
      if (key === "orientation_ns") {
        fields.flip_ns = flipFromOrientationNs(el.value);
        delete fields.orientation_ns;
      }
      if (key === "orientation_we") {
        fields.flip_we = flipFromOrientationWe(el.value);
        delete fields.orientation_we;
      }
    });
    return fields;
  }

  function snapshotPropsBaseline(meta) {
    propsFieldsBaseline = JSON.stringify(readPropsFieldsFromPanel(meta));
  }

  function propsPanelDirty(meta) {
    if (!meta || !propsFieldsBaseline) return false;
    return JSON.stringify(readPropsFieldsFromPanel(meta)) !== propsFieldsBaseline;
  }

  async function flushPendingPropsSave() {
    if (propsSaveTimer) {
      clearTimeout(propsSaveTimer);
      propsSaveTimer = null;
    }
    if (propsSavePromise) {
      await propsSavePromise;
    }
    if (!propsTarget || !locationId) return;
    const meta = document.getElementById("props-meta");
    if (!meta || !meta.querySelector("[data-prop]")) return;
    if (!propsPanelDirty(meta)) return;
    propsSavePromise = savePropsFromPanel({ reload: false }).finally(() => {
      propsSavePromise = null;
    });
    await propsSavePromise;
  }

  const OPENING_PLACE_TYPES = new Set([
    "JunctionBox",
    "DeviceBox",
    "LightPoint",
    "Panel",
  ]);
  const FACE_ORDER = ["N", "S", "E", "W", "F", "B"];
  const SIDE_FACES = new Set(["N", "S", "E", "W"]);

  function parseFaceGridSpec(value) {
    if (value == null || value === "") return [0, 0];
    if (Array.isArray(value) && value.length >= 2) {
      return [Math.max(0, Number(value[0]) || 0), Math.max(0, Number(value[1]) || 0)];
    }
    if (typeof value === "number") return [Math.max(0, value), value > 0 ? 1 : 0];
    const text = String(value).trim().toLowerCase().replace(/\s+/g, "");
    if (!text) return [0, 0];
    if (text.includes("x")) {
      const [a, b] = text.split("x");
      return [Math.max(0, parseInt(a, 10) || 0), Math.max(0, parseInt(b, 10) || 0)];
    }
    const n = parseInt(text, 10) || 0;
    return [Math.max(0, n), n > 0 ? 1 : 0];
  }

  /** Normalize API/YAML opening_grid into {face: [cols, rows]}. */
  function expandFaceGridMap(raw) {
    /** @type {Record<string, [number, number]>} */
    const out = {};
    if (!raw || typeof raw !== "object") return out;
    const pairs = { NS: ["N", "S"], WE: ["W", "E"] };
    for (const [key, value] of Object.entries(raw)) {
      const spec = parseFaceGridSpec(value);
      if (spec[0] < 1 || spec[1] < 1) continue;
      if (pairs[key]) {
        for (const face of pairs[key]) out[face] = spec;
      } else if (FACE_ORDER.includes(key)) {
        out[key] = spec;
      }
    }
    return out;
  }

  function listFaceCellIds(face, cols, rows) {
    const f = String(face || "").toUpperCase();
    const c = Math.max(0, Number(cols) || 0);
    const r = Math.max(0, Number(rows) || 0);
    if (c < 1 || r < 1) return [];
    if (SIDE_FACES.has(f)) {
      const n = c * r;
      return Array.from({ length: n }, (_, i) => `${f}${i + 1}`);
    }
    if (f === "F" || f === "B") {
      const ids = [];
      for (let row = 1; row <= r; row += 1) {
        for (let col = 1; col <= c; col += 1) {
          ids.push(`${f}${row}-${col}`);
        }
      }
      return ids;
    }
    return [];
  }

  function compactFaceGridForSave(expanded) {
    /** @type {Record<string, number|string>} */
    const out = {};
    for (const face of FACE_ORDER) {
      const spec = expanded[face];
      if (!spec || spec[0] < 1 || spec[1] < 1) continue;
      const [cols, rows] = spec;
      out[face] = rows === 1 ? cols : `${cols}x${rows}`;
    }
    return out;
  }

  function openingsOccupiedFromDetail(detail) {
    const occ = new Set();
    for (const c of detail?.conduits || []) {
      for (const end of [c.from_opening, c.to_opening, c.from, c.to]) {
        if (end == null) continue;
        const s = String(end).trim();
        const m =
          s.match(/\.([NSEW]\d+|[FB]\d+-\d+)$/i) ||
          s.match(/^([NSEW]\d+|[FB]\d+-\d+)$/i);
        if (m) occ.add(m[1].toUpperCase());
      }
    }
    return occ;
  }

  function terminalsOccupiedFromElement(elem) {
    const occ = new Set();
    const leaf = elem?.leaf_id || String(elem?.id || "").split("/").pop();
    for (const edge of graph?.edges || []) {
      for (const end of [edge.from, edge.to]) {
        if (!end) continue;
        const s = String(end);
        if (leaf && s.startsWith(`${leaf}.`)) {
          occ.add(s.slice(leaf.length + 1).toUpperCase());
        } else if (elem?.id && s.startsWith(`${elem.id}.`)) {
          occ.add(s.slice(String(elem.id).length + 1).toUpperCase());
        }
      }
    }
    for (const cable of graph?.cable_edges || []) {
      for (const end of [cable.from, cable.to]) {
        if (!end) continue;
        const s = String(end);
        if (leaf && s.includes(`${leaf}.`)) {
          const m = s.match(/\.([NSEW]\d+|[FB]\d+-\d+)$/i);
          if (m) occ.add(m[1].toUpperCase());
        }
      }
    }
    return occ;
  }

  function applyFaceCellTitle(btn) {
    const id = btn.dataset.cellId || "";
    const key = btn.dataset.titleKey || "props.face.free";
    btn.title = id ? `${id} — ${t(key)}` : t(key);
  }

  function applyFaceEditorSummary(el) {
    const faces = el.dataset.faces || "";
    if (!faces) {
      el.textContent = t("props.face.summaryEmpty");
      return;
    }
    el.textContent = t("props.face.summary", {
      faces,
      used: el.dataset.used || "0",
      total: el.dataset.total || "0",
    });
  }

  function relabelFaceEditor(meta) {
    const editor = meta.querySelector(".props-face-editor");
    if (!editor) return;
    const summary = editor.querySelector(".props-face-summary");
    if (summary) applyFaceEditorSummary(summary);
    editor.querySelectorAll(".props-face-chip[data-title-key]").forEach((el) => {
      applyFaceCellTitle(el);
    });
  }

  /**
   * Props block: one summary line; expand to edit all faces.
   * Side faces use a 1-row strip; F/B use a row×col matrix (id = Face{row}-{col}).
   * @param {HTMLElement} meta
   * @param {{
   *   mode: "openings"|"terminals",
   *   gridRaw: object|null,
   *   usedList?: string[],
   *   usedMap?: Record<string, object>,
   *   occupied?: Set<string>,
   * }} opts
   */
  function appendFaceCellEditor(meta, opts) {
    const mode = opts.mode;
    const gridKey = mode === "openings" ? "opening_grid" : "terminal_grid";
    const usedKey = mode === "openings" ? "openings" : "terminals";
    const labelKey = mode === "openings" ? "openings" : "terminals";
    /** @type {Record<string, [number, number]>} */
    let expanded = expandFaceGridMap(opts.gridRaw);
    /** @type {Set<string>} */
    let used =
      mode === "openings"
        ? new Set((opts.usedList || []).map((x) => String(x).toUpperCase()))
        : new Set(Object.keys(opts.usedMap || {}).map((x) => String(x).toUpperCase()));
    /** @type {Record<string, object>} */
    const usedMeta = { ...(opts.usedMap || {}) };
    const occupied = opts.occupied || new Set();
    syncPropsFaceEditorKey();
    let editorOpen = propsFaceEditorOpen;

    const dt = document.createElement("dt");
    dt.dataset.labelKey = labelKey;
    dt.textContent = propsLabel(labelKey);

    const details = document.createElement("details");
    details.className = "props-face-editor";
    if (editorOpen) details.open = true;

    const summary = document.createElement("summary");
    summary.className = "props-face-summary";

    const body = document.createElement("div");
    body.className = "props-face-body";

    const gridInput = document.createElement("input");
    gridInput.type = "hidden";
    gridInput.dataset.propJson = gridKey;
    const usedInput = document.createElement("input");
    usedInput.type = "hidden";
    usedInput.dataset.propJson = usedKey;

    function syncHidden() {
      const compact = compactFaceGridForSave(expanded);
      gridInput.value = JSON.stringify(
        Object.keys(compact).length ? compact : null
      );
      if (mode === "openings") {
        usedInput.value = JSON.stringify([...used].sort());
      } else {
        /** @type {Record<string, object>} */
        const map = {};
        for (const id of used) {
          map[id] = usedMeta[id] && typeof usedMeta[id] === "object" ? usedMeta[id] : {};
        }
        usedInput.value = JSON.stringify(map);
      }
    }

    function faceSizeLabel(face, cur) {
      if (!cur || cur[0] < 1 || cur[1] < 1) return "—";
      return face === "F" || face === "B" ? `${cur[0]}×${cur[1]}` : String(cur[0]);
    }

    function faceUsedCount(face, cur) {
      const ids = listFaceCellIds(face, cur?.[0] || 0, cur?.[1] || 0);
      let n = 0;
      for (const id of ids) if (used.has(id)) n += 1;
      return { used: n, total: ids.length };
    }

    function syncSummaryEl() {
      const parts = [];
      let usedTotal = 0;
      let capTotal = 0;
      for (const face of FACE_ORDER) {
        const cur = expanded[face];
        if (!cur || cur[0] < 1 || cur[1] < 1) continue;
        const { used: u, total } = faceUsedCount(face, cur);
        usedTotal += u;
        capTotal += total;
        parts.push(`${face}:${faceSizeLabel(face, cur)}`);
      }
      if (!parts.length) {
        delete summary.dataset.faces;
        delete summary.dataset.used;
        delete summary.dataset.total;
      } else {
        summary.dataset.faces = parts.join(" · ");
        summary.dataset.used = String(usedTotal);
        summary.dataset.total = String(capTotal);
      }
      applyFaceEditorSummary(summary);
    }

    function toggleCell(id) {
      if (used.has(id)) {
        if (occupied.has(id)) {
          if (!window.confirm(t("props.face.confirmRemoveOccupied"))) return;
        }
        used.delete(id);
        delete usedMeta[id];
      } else {
        used.add(id);
        if (mode === "terminals" && !usedMeta[id]) usedMeta[id] = {};
      }
      syncHidden();
      renderFaces();
      scheduleSaveProps();
    }

    function cellTitleKey(id) {
      if (occupied.has(id)) return "props.face.occupied";
      if (used.has(id)) return "props.face.used";
      return "props.face.free";
    }

    function makeCellButton(id, label) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "props-face-chip";
      btn.textContent = label;
      btn.dataset.cellId = id;
      btn.dataset.titleKey = cellTitleKey(id);
      if (used.has(id)) btn.classList.add("is-used");
      if (occupied.has(id)) btn.classList.add("is-occupied");
      applyFaceCellTitle(btn);
      btn.addEventListener("click", () => toggleCell(id));
      return btn;
    }

    const facesHost = document.createElement("div");
    facesHost.className = "props-face-list";

    function renderFaces() {
      syncSummaryEl();
      details.open = editorOpen;
      facesHost.innerHTML = "";
      for (const face of FACE_ORDER) {
        const isPlane = face === "F" || face === "B";
        const cur = expanded[face] || [0, 0];

        const row = document.createElement("div");
        row.className = "props-face-row";

        const name = document.createElement("div");
        name.className = "props-face-name";
        name.textContent = face;
        row.appendChild(name);

        const controls = document.createElement("div");
        controls.className = "props-face-controls";

        const colsInput = document.createElement("input");
        colsInput.type = "number";
        colsInput.min = "0";
        colsInput.max = "24";
        colsInput.value = String(cur[0] || 0);
        const colsKey = isPlane ? "props.face.cols" : "props.face.count";
        colsInput.className = "props-face-num";
        colsInput.setAttribute("data-i18n-title", colsKey);
        colsInput.setAttribute("data-i18n-aria", colsKey);
        colsInput.title = t(colsKey);
        colsInput.setAttribute("aria-label", t(colsKey));

        /** @type {HTMLInputElement|null} */
        let rowsInput = null;
        colsInput.addEventListener("change", () => {
          let cols = Math.max(0, parseInt(colsInput.value, 10) || 0);
          let rows;
          if (isPlane) {
            rows = Math.max(0, parseInt(rowsInput?.value || "0", 10) || 0);
            // F/B need both axes. Spinning one side up from empty left the other
            // at 0 and the change handler cleared the face (looked like a snap
            // back to 0). Bootstrap the unset axis to 1; clearing either axis
            // on an existing grid drops the whole face.
            const had =
              Boolean(expanded[face]) &&
              expanded[face][0] >= 1 &&
              expanded[face][1] >= 1;
            if (cols < 1 || rows < 1) {
              if (!had) {
                if (cols >= 1) rows = 1;
                else if (rows >= 1) cols = 1;
              } else {
                cols = 0;
                rows = 0;
              }
            }
          } else {
            rows = cols > 0 ? 1 : 0;
          }
          if (cols < 1 || rows < 1) delete expanded[face];
          else expanded[face] = [cols, rows];
          const allowed = new Set(
            listFaceCellIds(face, expanded[face]?.[0] || 0, expanded[face]?.[1] || 0)
          );
          for (const id of [...used]) {
            if (id.startsWith(face) && !allowed.has(id) && !occupied.has(id)) {
              used.delete(id);
              delete usedMeta[id];
            }
          }
          syncHidden();
          renderFaces();
          scheduleSaveProps();
        });
        controls.appendChild(colsInput);

        if (isPlane) {
          rowsInput = document.createElement("input");
          rowsInput.type = "number";
          rowsInput.min = "0";
          rowsInput.max = "24";
          rowsInput.value = String(cur[1] || 0);
          rowsInput.className = "props-face-num";
          rowsInput.setAttribute("data-i18n-title", "props.face.rows");
          rowsInput.setAttribute("data-i18n-aria", "props.face.rows");
          rowsInput.title = t("props.face.rows");
          rowsInput.setAttribute("aria-label", t("props.face.rows"));
          rowsInput.addEventListener("change", () => {
            colsInput.dispatchEvent(new Event("change"));
          });
          controls.appendChild(document.createTextNode("×"));
          controls.appendChild(rowsInput);
        }
        row.appendChild(controls);

        const cells = document.createElement("div");
        cells.className = "props-face-cells";
        const cols = cur[0] || 0;
        const rows = cur[1] || 0;
        if (cols < 1 || rows < 1) {
          const empty = document.createElement("span");
          empty.className = "props-face-empty";
          empty.textContent = "—";
          cells.appendChild(empty);
        } else if (isPlane) {
          const matrix = document.createElement("div");
          matrix.className = "props-face-matrix";
          matrix.style.gridTemplateColumns = `repeat(${cols}, minmax(1.55rem, 1.8rem))`;
          matrix.setAttribute("role", "grid");
          matrix.setAttribute("aria-label", `${face} ${cols}×${rows}`);
          for (let rowI = 1; rowI <= rows; rowI += 1) {
            for (let col = 1; col <= cols; col += 1) {
              const id = `${face}${rowI}-${col}`;
              matrix.appendChild(makeCellButton(id, `${rowI}-${col}`));
            }
          }
          cells.appendChild(matrix);
        } else {
          const strip = document.createElement("div");
          strip.className = "props-face-strip";
          const ids = listFaceCellIds(face, cols, rows);
          for (let i = 0; i < ids.length; i += 1) {
            strip.appendChild(makeCellButton(ids[i], String(i + 1)));
          }
          cells.appendChild(strip);
        }
        row.appendChild(cells);
        facesHost.appendChild(row);
      }
    }

    details.addEventListener("toggle", () => {
      editorOpen = details.open;
      propsFaceEditorOpen = details.open;
    });

    syncHidden();
    renderFaces();
    body.appendChild(facesHost);
    details.appendChild(summary);
    details.appendChild(body);
    details.appendChild(gridInput);
    details.appendChild(usedInput);

    const dd = document.createElement("dd");
    dd.appendChild(details);
    meta.appendChild(dt);
    meta.appendChild(dd);
  }

  function appendPropsRow(meta, spec) {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    const value = spec.value == null ? "" : String(spec.value);
    const labelKey = spec.labelKey || spec.key;
    const labelText = spec.label || propsLabel(labelKey);
    dt.dataset.labelKey = labelKey;
    if (!spec.editable) {
      dd.classList.add("props-kind-readonly");
      dt.textContent = labelText;
      const span = document.createElement("span");
      span.className = "props-readonly";
      span.textContent = value || "—";
      dd.appendChild(span);
    } else if (spec.checkbox) {
      const id = `prop-${spec.key}`;
      const label = document.createElement("label");
      label.className = "props-check";
      label.htmlFor = id;
      dt.textContent = "";
      const dtLabel = document.createElement("label");
      dtLabel.className = "props-check-key";
      dtLabel.htmlFor = id;
      dtLabel.textContent = labelText;
      dt.appendChild(dtLabel);
      const input = document.createElement("input");
      input.type = "checkbox";
      input.id = id;
      input.dataset.prop = spec.key;
      input.checked = Boolean(spec.value);
      label.appendChild(input);
      label.appendChild(document.createTextNode(spec.checkLabel || t("props.enabled")));
      dd.appendChild(label);
    } else if (spec.combo) {
      dd.classList.add("props-kind-select");
      dt.textContent = labelText;
      const input = document.createElement("select");
      input.className = "props-select";
      input.dataset.prop = spec.key;
      if (Array.isArray(spec.options) && spec.options.length) {
        let known = false;
        for (const rawOpt of spec.options) {
          const opt = String(rawOpt || "").trim();
          if (!opt) continue;
          const optionEl = document.createElement("option");
          optionEl.value = opt;
          optionEl.textContent =
            (spec.optionLabels && spec.optionLabels[opt]) ||
            propsValueLabel(spec.combo, opt);
          if (opt === value) known = true;
          input.appendChild(optionEl);
        }
        if (value && !known) {
          const optionEl = document.createElement("option");
          optionEl.value = value;
          optionEl.textContent = value;
          input.appendChild(optionEl);
        }
      }
      if (value) {
        input.value = value;
      }
      dd.appendChild(input);
    } else if (spec.multiline) {
      dd.classList.add("props-kind-edit");
      dt.textContent = labelText;
      const ta = document.createElement("textarea");
      ta.dataset.prop = spec.key;
      ta.value = value;
      ta.rows = 3;
      ta.spellcheck = false;
      dd.appendChild(ta);
    } else {
      dd.classList.add("props-kind-edit");
      dt.textContent = labelText;
      const input = document.createElement("input");
      input.type = "text";
      input.className = "props-input";
      input.dataset.prop = spec.key;
      input.value = value;
      input.spellcheck = false;
      dd.appendChild(input);
    }
    meta.appendChild(dt);
    meta.appendChild(dd);
  }

  function bindPropsEditors(meta) {
    meta.querySelectorAll("[data-prop]").forEach((el) => {
      const key = el.getAttribute("data-prop");
      if (key === "orientation_ns" || key === "orientation_we") {
        el.addEventListener("change", () => {
          saveFlipPropsFromPanel().catch((err) =>
            setStatus(String(err.message || err))
          );
        });
        return;
      }
      el.addEventListener("change", () => {
        scheduleSaveProps();
      });
      if (el.type !== "checkbox") {
        el.addEventListener("blur", () => {
          if (propsSaveTimer) {
            clearTimeout(propsSaveTimer);
            propsSaveTimer = null;
          }
          flushPendingPropsSave().catch((err) =>
            setStatus(String(err.message || err))
          );
        });
      }
      el.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && el.tagName === "INPUT" && el.type !== "checkbox") {
          ev.preventDefault();
          el.blur();
        }
      });
    });
  }

  function relabelPropertyPanel() {
    const meta = document.getElementById("props-meta");
    if (!meta) return;
    meta.querySelectorAll("dt[data-label-key]").forEach((el) => {
      const key = el.getAttribute("data-label-key");
      if (!key) return;
      const checkLabel = el.querySelector(".props-check-key");
      if (checkLabel) checkLabel.textContent = propsLabel(key);
      else el.textContent = propsLabel(key);
    });
    meta.querySelectorAll("select[data-prop]").forEach((el) => {
      const key = el.getAttribute("data-prop");
      if (!key) return;
      const group =
        key === "install"
          ? "install"
          : key === "mount"
            ? "mount"
            : key === "orientation_ns"
              ? "orientation"
              : key === "orientation_we"
                ? "orientation"
                : null;
      if (!group) return;
      [...el.options].forEach((opt) => {
        opt.textContent = propsValueLabel(group, opt.value);
      });
    });
    relabelFaceEditor(meta);
  }

  /** Apply flip flags to the in-memory graph for immediate canvas feedback. */
  function applyFlipsLocally(fields) {
    if (!graph || !propsTarget) return;
    const ns = fields.flip_ns;
    const we = fields.flip_we;
    if (propsTarget.kind === "element") {
      const elem = (graph.elements || []).find((e) => e.id === selectedId);
      if (!elem) return;
      if (ns != null) elem.flip_ns = Boolean(ns);
      if (we != null) elem.flip_we = Boolean(we);
      return;
    }
    const node = selectedId
      ? (graph.nodes || []).find((n) => n.id === selectedId)
      : null;
    if (node) {
      if (ns != null) node.flip_ns = Boolean(ns);
      if (we != null) node.flip_we = Boolean(we);
      return;
    }
    // Open canvas location (not a node in the graph).
    const placeKey = resolvePlaceApiId(propsTarget.placeId);
    if (placeKey === "." || placeKey === locationId) {
      if (!graph.location) graph.location = { id: locationId };
      if (ns != null) graph.location.flip_ns = Boolean(ns);
      if (we != null) graph.location.flip_we = Boolean(we);
    }
  }

  /** Read current flip flags for the props target from the in-memory graph. */
  function flipsFromGraph() {
    /** @type {{flip_ns:boolean, flip_we:boolean}} */
    const out = { flip_ns: false, flip_we: false };
    if (!graph || !propsTarget) return out;
    if (propsTarget.kind === "element" && selectedId) {
      const elem = (graph.elements || []).find((e) => e.id === selectedId);
      if (elem) {
        out.flip_ns = Boolean(elem.flip_ns);
        out.flip_we = Boolean(elem.flip_we);
      }
      return out;
    }
    const node = selectedId
      ? (graph.nodes || []).find((n) => n.id === selectedId)
      : null;
    if (node) {
      out.flip_ns = Boolean(node.flip_ns);
      out.flip_we = Boolean(node.flip_we);
      return out;
    }
    const loc = graph.location || {};
    out.flip_ns = Boolean(loc.flip_ns);
    out.flip_we = Boolean(loc.flip_we);
    return out;
  }

  /** Align flip checkboxes with graph (used after a failed PATCH). */
  function syncFlipCheckboxesFromGraph() {
    const meta = document.getElementById("props-meta");
    if (!meta) return;
    const cur = flipsFromGraph();
    meta.querySelectorAll("select[data-prop]").forEach((el) => {
      const key = el.getAttribute("data-prop");
      if (key === "orientation_ns") {
        el.value = orientationNsFromFlip(cur.flip_ns);
      }
      if (key === "orientation_we") {
        el.value = orientationWeFromFlip(cur.flip_we);
      }
    });
  }

  async function saveFlipPropsFromPanel() {
    if (!propsTarget || !locationId) return;
    const meta = document.getElementById("props-meta");
    if (!meta) return;
    /** @type {Record<string, boolean>} */
    const fields = {};
    meta.querySelectorAll("select[data-prop]").forEach((el) => {
      const key = el.getAttribute("data-prop");
      if (key === "orientation_ns") fields.flip_ns = flipFromOrientationNs(el.value);
      if (key === "orientation_we") fields.flip_we = flipFromOrientationWe(el.value);
    });
    if (!Object.keys(fields).length) return;
    // Optimistic paint, but roll back if the server rejects (stale serve,
    // unsupported fields, etc.) so Save/Undo cannot diverge from the buffer.
    const before = flipsFromGraph();
    applyFlipsLocally(fields);
    render();
    const body = {
      location_id: locationId,
      id: resolvePlaceApiId(propsTarget.placeId),
      fields,
      depth: depthLevel,
    };
    if (propsTarget.element) body.element = propsTarget.element;
    let res;
    try {
      res = await api("/api/place/properties", {
        method: "PATCH",
        body: JSON.stringify(body),
      });
    } catch (err) {
      applyFlipsLocally(before);
      syncFlipCheckboxesFromGraph();
      render();
      throw err;
    }
    if (res.graph) {
      graph = res.graph;
      depthLevel = graph.depth || depthLevel;
      maxDepth = graph.max_depth || maxDepth;
      render();
    }
    applyEditFlags(res);
    setStatus(t("status.flipUpdated"));
    scheduleStatusRefresh();
    if (propsTarget.kind === "element" && selectedId) {
      const elem = (graph?.elements || []).find((e) => e.id === selectedId);
      if (elem) await fillElementInspector(elem);
    } else if (propsTarget.kind === "place") {
      const id = selectedId || propsTarget.placeId || ".";
      await fillPlaceInspector(id, res.detail);
    }
  }

  function scheduleSaveProps() {
    if (propsSaveTimer) clearTimeout(propsSaveTimer);
    propsSaveTimer = setTimeout(() => {
      propsSaveTimer = null;
      savePropsFromPanel().catch((err) => setStatus(String(err.message || err)));
    }, 350);
  }

  async function savePropsFromPanel(opts = {}) {
    const reload = opts.reload !== false;
    if (!propsTarget || !locationId) return;
    if (propsTarget.kind === "link") {
      await saveLinkPropsFromPanel();
      return;
    }
    const meta = document.getElementById("props-meta");
    if (!meta) return;
    /** @type {Record<string, string|boolean>} */
    const fields = readPropsFieldsFromPanel(meta);
    if (!Object.keys(fields).length) return;
    if (!propsPanelDirty(meta)) return;
    const body = {
      location_id: locationId,
      id: resolvePlaceApiId(propsTarget.placeId),
      fields,
      depth: depthLevel,
    };
    if (propsTarget.element) body.element = propsTarget.element;
    const res = await api("/api/place/properties", {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    snapshotPropsBaseline(meta);
    if (res.graph) {
      graph = res.graph;
      depthLevel = graph.depth || depthLevel;
      maxDepth = graph.max_depth || maxDepth;
      render();
    }
    applyEditFlags(res);
    setStatus(t("status.propertiesUpdated"));
    scheduleStatusRefresh();
    await loadOutline();
    highlightOutlineSelection();
    if (!reload) return;
    if (propsTarget.kind === "element" && selectedId) {
      const elem = (graph?.elements || []).find((e) => e.id === selectedId);
      if (elem) await fillElementInspector(elem);
    } else if (propsTarget.kind === "place" && selectedId) {
      await fillPlaceInspector(selectedId, res.detail);
    }
  }

  async function fillElementInspector(elem) {
    await flushPendingPropsSave();
    hideLinkActionBar();
    const empty = document.getElementById("panel-empty");
    const panel = document.getElementById("panel-props");
    if (!empty || !panel) {
      setStatus(t("status.propsPanelMissing"));
      return;
    }
    ensurePropertiesVisible();
    empty.classList.add("hidden");
    panel.classList.remove("hidden");
    setInspectorMode("element");
    const leaf = elem.leaf_id || String(elem.id || "").split("/").pop();
    propsTarget = {
      kind: "element",
      placeId: elem.parent || ".",
      element: leaf,
    };
    const meta = document.getElementById("props-meta");
    if (!meta) return;
    meta.innerHTML = "";
    appendPropsRow(meta, {
      key: "id",
      value: leaf,
      editable: false,
    });
    appendPropsRow(meta, {
      key: "parent",
      value: formatCanvasParentLabel(elem.parent),
      editable: false,
    });
    appendPropsRow(meta, {
      key: "name",
      value: elem.name || "",
      editable: true,
    });
    appendPropsRow(meta, {
      key: "label",
      value: elem.label || "",
      editable: true,
    });
    appendPropsRow(meta, {
      key: "type",
      value: elem.type || "",
      editable: false,
    });
    {
      const subSel = catalogSubtypeSelect(elem.type);
      if (subSel.options && subSel.options.length) {
        appendPropsRow(meta, {
          key: "subtype",
          value: elem.subtype || "",
          editable: true,
          combo: "subtype",
          options: subSel.options,
          optionLabels: subSel.optionLabels,
        });
      } else {
        appendPropsRow(meta, {
          key: "subtype",
          value: elem.subtype || "",
          editable: false,
        });
      }
    }
    appendPropsRow(meta, {
      key: "notes",
      value: elem.notes || "",
      editable: true,
      multiline: true,
    });
    appendPropsRow(meta, {
      key: "orientation_ns",
      value: orientationNsFromFlip(Boolean(elem.flip_ns)),
      editable: true,
      combo: "orientation",
      options: ["north_to_south", "south_to_north"],
      labelKey: "orientationNorthSouth",
    });
    appendPropsRow(meta, {
      key: "orientation_we",
      value: orientationWeFromFlip(Boolean(elem.flip_we)),
      editable: true,
      combo: "orientation",
      options: ["west_to_east", "east_to_west"],
      labelKey: "orientationWestEast",
    });
    {
      const hasGrid =
        elem.terminal_grid && Object.keys(elem.terminal_grid).length;
      const termList = Array.isArray(elem.terminals) ? elem.terminals : [];
      const termMap = {};
      for (const pin of termList) {
        if (pin) termMap[String(pin)] = {};
      }
      if (hasGrid || termList.length) {
        appendFaceCellEditor(meta, {
          mode: "terminals",
          gridRaw: elem.terminal_grid || null,
          usedMap: termMap,
          occupied: terminalsOccupiedFromElement(elem),
        });
      }
    }
    bindPropsEditors(meta);
    snapshotPropsBaseline(meta);
    fillCablesForElement(elem);
  }

  function fillListEmpty(ul, label) {
    ul.innerHTML = "";
    const li = document.createElement("li");
    li.className = "props-empty";
    li.textContent = label;
    ul.appendChild(li);
  }

  function appendSub(li, text) {
    if (!text) return;
    const span = document.createElement("span");
    span.className = "props-sub";
    span.textContent = text;
    li.appendChild(span);
  }

  function fillConduitsList(conduits) {
    const ul = document.getElementById("props-conduits");
    ul.innerHTML = "";
    if (!conduits || !conduits.length) {
      fillListEmpty(ul, "—");
      return;
    }
    for (const c of conduits) {
      const li = document.createElement("li");
      li.className = "props-list-clickable";
      const ends = [c.from, c.to].filter(Boolean).join(" → ");
      const title = c.name || c.id;
      const head = [title, c.subtype].filter(Boolean).join(" · ");
      li.textContent = ends ? `${head}: ${ends}` : head;
      if (c.name && c.id && c.name !== c.id) {
        appendSub(li, `id: ${c.id}`);
      }
      const contains = (c.contains || []).join(", ");
      appendSub(li, contains ? `contains: ${contains}` : "");
      appendSub(li, c.label && c.label !== c.name ? String(c.label).trim() : "");
      appendSub(li, c.notes ? String(c.notes).trim() : "");
      li.addEventListener("click", () => {
        selectLink(c.id, "conduit").catch((err) =>
          setStatus(String(err.message || err))
        );
      });
      ul.appendChild(li);
    }
  }

  function fillCablesForElement(elem) {
    const ul = document.getElementById("props-cables");
    const edges = (graph?.cable_edges || []).filter(
      (e) => e.from === elem.id || e.to === elem.id
    );
    if (!edges.length) {
      fillListEmpty(ul, "—");
      return;
    }
    ul.innerHTML = "";
    for (const e of edges) {
      const li = document.createElement("li");
      li.className = "props-list-clickable";
      const other = e.from === elem.id ? e.to : e.from;
      const title = e.name || e.id || "cable";
      const bits = [title, `↔ ${other}`];
      if ((e.colors || []).length) bits.push((e.colors || []).join(", "));
      if (e.conduit) bits.push(`via ${e.conduit}`);
      li.textContent = bits.join(" · ");
      if (e.name && e.id && e.name !== e.id) {
        appendSub(li, `id: ${e.id}`);
      }
      li.addEventListener("click", () => {
        selectLink(e.id, "cable").catch((err) =>
          setStatus(String(err.message || err))
        );
      });
      ul.appendChild(li);
    }
  }

  function canvasToSiteId(relId) {
    if (!relId) return locationId;
    if (!locationId || locationId === "." || locationId === "") return relId;
    return `${locationId}/${relId}`;
  }

  /**
   * Prefer human label/name over technical id for inspector Parent.
   * Order: label → name → display_label → display_name → fallback id.
   */
  function humanPlaceTitle(obj, fallbackId) {
    if (obj && typeof obj === "object") {
      for (const key of ["label", "name", "display_label", "display_name"]) {
        const v = obj[key];
        if (v != null && String(v).trim()) return String(v).trim();
      }
    }
    if (fallbackId && fallbackId !== ".") return String(fallbackId);
    return t("props.siteRoot");
  }

  /** Resolve a site/canvas place id to a display title (outline, then graph). */
  function placeTitleForId(placeId) {
    if (!placeId || placeId === ".") {
      const root = (outlineNodes || []).find(
        (n) => n.kind !== "element" && n.id === "."
      );
      if (root) return humanPlaceTitle(root, ".");
      const loc = graph?.location;
      if (locationId === "." || !locationId) {
        return humanPlaceTitle(loc, ".");
      }
      return humanPlaceTitle(null, ".");
    }
    const outline = (outlineNodes || []).find(
      (n) => n.kind !== "element" && n.id === placeId
    );
    if (outline) return humanPlaceTitle(outline, placeId);
    const node = (graph?.nodes || []).find((n) => n.id === placeId);
    if (node) return humanPlaceTitle(node, placeId);
    // Canvas-relative id under current view → site path for outline lookup.
    if (locationId && locationId !== ".") {
      const siteId = `${locationId}/${placeId}`;
      const nested = (outlineNodes || []).find(
        (n) => n.kind !== "element" && n.id === siteId
      );
      if (nested) return humanPlaceTitle(nested, placeId);
    }
    return humanPlaceTitle(null, placeId);
  }

  /**
   * Human-readable parent for an element/place on the current canvas.
   * ``parentId`` null/""/"." → current view location (canvas floor).
   */
  function formatCanvasParentLabel(parentId) {
    if (parentId && parentId !== ".") {
      return placeTitleForId(parentId);
    }
    return humanPlaceTitle(graph?.location, locationId || ".");
  }

  /**
   * Parent id for a place shown in the inspector (canvas id or ``.``).
   * Inspecting the canvas location itself uses the site-tree parent of
   * ``locationId``.
   */
  function parentIdForPlaceInspector(placeCanvasId) {
    if (!placeCanvasId || placeCanvasId === ".") {
      if (!locationId || locationId === ".") return null;
      if (!locationId.includes("/")) return ".";
      return locationId.slice(0, locationId.lastIndexOf("/"));
    }
    const node = (graph?.nodes || []).find((n) => n.id === placeCanvasId);
    if (!node) return ".";
    return node.parent == null || node.parent === "" ? "." : node.parent;
  }

  function formatPlaceParentLabel(placeCanvasId) {
    const parentId = parentIdForPlaceInspector(placeCanvasId);
    if (parentId == null) return t("props.siteRoot");
    // Canvas location itself → site-tree parent (absolute outline id).
    if (!placeCanvasId || placeCanvasId === ".") {
      return placeTitleForId(parentId);
    }
    // Nested place on this canvas → parent may be canvas-relative.
    return formatCanvasParentLabel(parentId);
  }

  /**
   * Map a place id to the /api/place ``id`` query value.
   * The canvas location itself is ``.`` — ``location=Parking&id=Parking``
   * wrongly means Parking/Parking and 400s.
   */
  function resolvePlaceApiId(id) {
    if (!id || id === ".") return ".";
    if (id === locationId) return ".";
    if (locationId && locationId !== "." && locationId !== "") {
      const onCanvas = (graph?.nodes || []).some((n) => n.id === id);
      if (!onCanvas) {
        const leaf = locationId.includes("/")
          ? locationId.slice(locationId.lastIndexOf("/") + 1)
          : locationId;
        if (id === leaf || locationId.endsWith(`/${id}`)) return ".";
      }
    }
    return id;
  }

  /** Root place path is ``.``; show the site YAML stem (``NuevoSitio``). */
  function formatPlaceIdDisplay(id) {
    if (id && id !== ".") return id;
    const yaml = activeYamlName || "";
    const stem = yaml.replace(/\.(ya?ml)$/i, "");
    return stem || id || "—";
  }

  async function fillPlaceInspector(id, detailOpt) {
    await flushPendingPropsSave();
    hideLinkActionBar();
    const empty = document.getElementById("panel-empty");
    const panel = document.getElementById("panel-props");
    if (!empty || !panel) {
      setStatus(t("status.propsPanelMissing"));
      return;
    }
    if (!id || !locationId) {
      propsTarget = null;
      propsFieldsBaseline = null;
      propsFaceEditorKey = null;
      propsFaceEditorOpen = false;
      empty.classList.remove("hidden");
      panel.classList.add("hidden");
      return;
    }
    const placeKey = resolvePlaceApiId(id);
    try {
      const detail =
        detailOpt ||
        (await api(
          `/api/place?location=${encodeURIComponent(locationId)}&id=${encodeURIComponent(placeKey)}`
        ));
      ensurePropertiesVisible();
      empty.classList.add("hidden");
      panel.classList.remove("hidden");
      setInspectorMode("place");
      propsTarget = { kind: "place", placeId: placeKey };
      const meta = document.getElementById("props-meta");
      if (!meta) return;
      meta.innerHTML = "";
      appendPropsRow(meta, {
        key: "id",
        value: formatPlaceIdDisplay(detail.id),
        editable: false,
      });
      appendPropsRow(meta, {
        key: "parent",
        value: formatPlaceParentLabel(placeKey === "." ? "." : id),
        editable: false,
      });
      appendPropsRow(meta, {
        key: "name",
        value: detail.name || "",
        editable: true,
      });
      appendPropsRow(meta, {
        key: "label",
        value: detail.label || "",
        editable: true,
      });
      appendPropsRow(meta, {
        key: "type",
        value: detail.type || "",
        editable: false,
      });
      {
        const subSel = catalogSubtypeSelect(detail.type);
        if (subSel.options && subSel.options.length) {
          appendPropsRow(meta, {
            key: "subtype",
            value: detail.subtype || "",
            editable: true,
            combo: "subtype",
            options: subSel.options,
            optionLabels: subSel.optionLabels,
          });
        } else {
          appendPropsRow(meta, {
            key: "subtype",
            value: detail.subtype || "",
            editable: false,
          });
        }
      }
      appendPropsRow(meta, {
        key: "install",
        value: detail.install || "",
        editable: true,
        combo: "install",
        options: ["Surface", "Flush"],
      });
      appendPropsRow(meta, {
        key: "mount",
        value: detail.mount || "",
        editable: true,
        combo: "mount",
        options: ["Wall", "Ceiling", "Floor"],
      });
      {
        const typeId = String(detail.type || "");
        const showOpenings =
          OPENING_PLACE_TYPES.has(typeId) ||
          (detail.openings && detail.openings.length) ||
          (detail.opening_grid && Object.keys(detail.opening_grid).length);
        if (showOpenings) {
          const node = (graph?.nodes || []).find(
            (n) => n.id === id || n.id === detail.id
          );
          appendFaceCellEditor(meta, {
            mode: "openings",
            gridRaw: detail.opening_grid || node?.opening_grid || null,
            usedList: detail.openings || [],
            occupied: openingsOccupiedFromDetail(detail),
          });
        }
      }
      appendPropsRow(meta, {
        key: "notes",
        value: detail.notes || "",
        editable: true,
        multiline: true,
      });
      appendPropsRow(meta, {
        key: "orientation_ns",
        value: orientationNsFromFlip(Boolean(detail.flip_ns)),
        editable: true,
        combo: "orientation",
        options: ["north_to_south", "south_to_north"],
        labelKey: "orientationNorthSouth",
      });
      appendPropsRow(meta, {
        key: "orientation_we",
        value: orientationWeFromFlip(Boolean(detail.flip_we)),
        editable: true,
        combo: "orientation",
        options: ["west_to_east", "east_to_west"],
        labelKey: "orientationWestEast",
      });
      bindPropsEditors(meta);
      snapshotPropsBaseline(meta);
      propsShowElements = placeShowsElementsInView(detail.id || placeKey);
      const elementsBlock = document.getElementById("props-elements-block");
      if (elementsBlock) {
        elementsBlock.classList.toggle("hidden", !propsShowElements);
      }
      const ul = document.getElementById("props-elements");
      ul.innerHTML = "";
      if (!propsShowElements) {
        /* Elements section hidden — not in the current view. */
      } else if (!(detail.elements || []).length) {
        fillListEmpty(ul, "—");
      } else {
        for (const elItem of detail.elements || []) {
          const li = document.createElement("li");
          const title = elItem.name || elItem.id;
          li.textContent = `${title} (${elItem.type || "?"}${
            elItem.subtype ? " / " + elItem.subtype : ""
          })`;
          ul.appendChild(li);
        }
      }
      fillConduitsList(filterConduitsToView(detail.conduits || []));
      prefillInsertForms(detail);
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }

  async function selectNode(id) {
    const elem = (graph?.elements || []).find((e) => e.id === id);
    if (elem) {
      await selectElement(elem);
      return;
    }
    replaceSelection(id);
    highlightOutlineSelection();
    await fillPlaceInspector(id);
  }

  async function syncInspectorFromSelection() {
    await flushPendingPropsSave();
    await loadPaletteCatalog().catch(() => null);
    setSelectedVisual();
    if (selectedLinkId) {
      highlightOutlineSelection();
      await fillLinkInspector(selectedLinkId);
      return;
    }
    if (selectedIds.size === 0) {
      highlightOutlineSelection();
      await fillPlaceInspector(null);
      return;
    }
    if (selectedIds.size > 1) {
      setStatus(t("status.nSelected", { n: selectedIds.size }));
      highlightOutlineSelection();
      await fillPlaceInspector(null);
      return;
    }
    highlightOutlineSelection();
    const elem = (graph?.elements || []).find((e) => e.id === selectedId);
    if (elem) await fillElementInspector(elem);
    else await fillPlaceInspector(selectedId);
  }

  function hideLinkActionBar() {
    const bar = document.getElementById("props-link-actions");
    if (bar) {
      bar.classList.add("hidden");
      bar.innerHTML = "";
    }
  }

  function appendLinkAction(bar, label, onClick) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    btn.addEventListener("click", () => {
      onClick().catch((err) => setStatus(String(err.message || err)));
    });
    bar.appendChild(btn);
  }

  async function fillLinkInspector(linkId) {
    const empty = document.getElementById("panel-empty");
    const props = document.getElementById("panel-props");
    const meta = document.getElementById("props-meta");
    if (!empty || !props || !meta) return;
    empty.classList.add("hidden");
    props.classList.remove("hidden");
    setInspectorMode("link");
    hideLinkActionBar();
    meta.innerHTML = "";
    propsTarget = { kind: "link", linkId };
    let detail;
    try {
      detail = await api(`/api/cable?id=${encodeURIComponent(linkId)}`);
    } catch (err) {
      setStatus(String(err.message || err));
      appendPropsRow(meta, {
        key: "id",
        value: linkId,
        editable: false,
      });
      bindPropsEditors(meta);
      snapshotPropsBaseline(meta);
      return;
    }
    selectedLinkKind = detail.kind || selectedLinkKind;
    appendPropsRow(meta, {
      key: "id",
      value: detail.id,
      editable: false,
    });
    appendPropsRow(meta, {
      key: "kind",
      value: detail.kind || "",
      editable: false,
      labelKey: "type",
    });
    appendPropsRow(meta, {
      key: "type",
      value: detail.type || "",
      editable: false,
    });
    appendPropsRow(meta, {
      key: "subtype",
      value: detail.subtype || "",
      editable: true,
    });
    appendPropsRow(meta, {
      key: "name",
      value: detail.name || "",
      editable: true,
    });
    appendPropsRow(meta, {
      key: "label",
      value: detail.label || "",
      editable: true,
    });
    if (detail.kind !== "conduit") {
      appendPropsRow(meta, {
        key: "color",
        value: detail.color || "",
        editable: true,
      });
      appendPropsRow(meta, {
        key: "section",
        value: detail.section || "",
        editable: true,
      });
    }
    if (detail.kind === "conduit" || detail.kind === "cable") {
      appendPropsRow(meta, {
        key: "install",
        value: detail.install || "",
        editable: true,
        combo: "install",
        options: ["Surface", "Flush"],
      });
    }
    appendPropsRow(meta, {
      key: "from",
      value: detail.from || "",
      editable: detail.kind !== "cable",
    });
    appendPropsRow(meta, {
      key: "to",
      value: detail.to || "",
      editable: detail.kind !== "cable",
    });
    appendPropsRow(meta, {
      key: "contains",
      value: (detail.contains || []).join(", "),
      editable: detail.kind !== "conductor",
    });
    appendPropsRow(meta, {
      key: "notes",
      value: detail.notes || "",
      editable: true,
      multiline: true,
    });
    bindPropsEditors(meta);
    snapshotPropsBaseline(meta);
    // Hide place/element lists when inspecting a link.
    document.getElementById("props-elements-block")?.classList.add("hidden");
    document.getElementById("props-conduits-block")?.classList.add("hidden");
    document.getElementById("props-cables-block")?.classList.add("hidden");

    const bar = document.getElementById("props-link-actions");
    if (bar) {
      bar.classList.remove("hidden");
      bar.innerHTML = "";
      if (detail.is_open_run) {
        appendLinkAction(bar, t("props.link.claim"), async () => {
          const enter = window.prompt(t("props.link.claimEnter"));
          if (!enter) return;
          const res = await api("/api/cable/claim", {
            method: "POST",
            body: JSON.stringify({
              location_id: locationId,
              id: detail.id,
              enter: enter.trim(),
              depth: depthLevel,
            }),
          });
          if (res.graph) {
            graph = res.graph;
            render();
          }
          applyEditFlags(res);
          await selectLink(detail.id, detail.kind);
          setStatus(t("status.linkClaimed"));
        });
        appendLinkAction(bar, t("props.link.land"), async () => {
          const fromRef = window.prompt(t("props.link.landFrom"), detail.from || "");
          if (fromRef == null) return;
          const toRef = window.prompt(t("props.link.landTo"), detail.to || "");
          if (toRef == null) return;
          const asName = window.prompt(t("props.link.landAs"), detail.id);
          const res = await api("/api/cable/land", {
            method: "POST",
            body: JSON.stringify({
              location_id: locationId,
              id: detail.id,
              from: fromRef.trim(),
              to: toRef.trim(),
              as_name: asName && asName.trim() ? asName.trim() : null,
              depth: depthLevel,
            }),
          });
          if (res.graph) {
            graph = res.graph;
            render();
          }
          applyEditFlags(res);
          const nextId = res.detail?.id || detail.id;
          await selectLink(nextId, "cable");
          setStatus(t("status.linkLanded"));
        });
      }
      if (detail.kind === "conductor" || detail.kind === "cable") {
        appendLinkAction(bar, t("props.link.groupSheath"), async () => {
          const extra = window.prompt(t("props.link.groupContains"), detail.id);
          if (extra == null) return;
          const contains = [
            detail.id,
            ...String(extra)
              .split(/[,\s]+/)
              .map((s) => s.trim())
              .filter(Boolean),
          ];
          const res = await api("/api/cable/sheath", {
            method: "POST",
            body: JSON.stringify({
              location_id: locationId,
              owner_id: locationId,
              contains,
              depth: depthLevel,
            }),
          });
          if (res.graph) {
            graph = res.graph;
            render();
          }
          applyEditFlags(res);
          await selectLink(res.detail.id, "cable");
          setStatus(t("status.linkGrouped"));
        });
      }
      appendLinkAction(bar, t("menu.edit.delete"), async () => {
        await deleteSelection();
      });
    }
  }

  async function saveLinkPropsFromPanel() {
    if (!propsTarget || propsTarget.kind !== "link" || !locationId) return;
    const meta = document.getElementById("props-meta");
    if (!meta) return;
    /** @type {Record<string, any>} */
    const fields = {};
    meta.querySelectorAll("[data-prop]").forEach((el) => {
      const key = el.getAttribute("data-prop");
      if (!key || key === "id" || key === "kind" || key === "type") return;
      if (el.type === "checkbox") fields[key] = el.checked;
      else fields[key] = el.value;
    });
    if (fields.contains != null && typeof fields.contains === "string") {
      fields.contains = fields.contains
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);
    }
    const res = await api("/api/cable/properties", {
      method: "PATCH",
      body: JSON.stringify({
        location_id: locationId,
        id: propsTarget.linkId,
        fields,
        depth: depthLevel,
      }),
    });
    if (res.graph) {
      graph = res.graph;
      render();
    }
    applyEditFlags(res);
    if (res.detail?.id) selectedLinkId = res.detail.id;
    await fillLinkInspector(selectedLinkId);
    setStatus(t("status.linkSaved"));
  }

  function prefillInsertForms(detail) {
    const openings = detail.openings || [];
    const prefer =
      openings.find((o) => String(o).startsWith("N")) ||
      openings[0] ||
      "N1";
    const fromVal = `${detail.id}.${prefer}`;
    for (const formId of ["form-socket", "form-lamp"]) {
      const form = document.getElementById(formId);
      if (!form) continue;
      const from = form.querySelector('[name="from"]');
      if (from) from.value = fromVal;
    }
    const feedFrom = document.querySelector('#form-feed [name="from"]');
    if (feedFrom) feedFrom.value = fromVal;
  }

  function canvasLocationIdForNode(node) {
    if (!node || !locationId) return null;
    return locationId === "." ? node.id : `${locationId}/${node.id}`;
  }

  async function enterNode(node) {
    if (!node || !locationId) return;
    const nextId = canvasLocationIdForNode(node);
    const opt = canvasLocations.find(
      (r) => r.selectable !== false && r.id === nextId
    );
    if (opt) {
      depthLevel = DEPTH_MAX_REQUEST;
      await setCanvasLocation(nextId);
      setStatus(t("status.entered", { id: nextId }));
      return;
    }
    // Not a canvas root in the selector: deepen the view instead.
    if (node.expandable || childrenOf(node.id).length) {
      await setDepth(depthLevel + 1);
      setStatus(t("status.depth", { n: depthLevel }));
      return;
    }
    setStatus(t("status.noDeeperView", { id: node.id }));
  }

  async function endDrag(ev) {
    if (!drag) return;
    if (ev && drag.pointerId != null && ev.pointerId !== drag.pointerId) return;
    stopEdgeAutoPan();
    svg.classList.remove("dragging", "resizing");
    clearResizeHoverCursor();
    try {
      if (
        drag.captured &&
        drag.pointerId != null &&
        svg.hasPointerCapture?.(drag.pointerId)
      ) {
        svg.releasePointerCapture(drag.pointerId);
      }
    } catch {
      /* ignore */
    }
    const finished = drag;
    drag = null;
    if (finished.moved) rememberCurrentDocView();
    if (finished.kind === "resize") {
      if (!finished.moved || !locationId) {
        await syncInspectorFromSelection();
        return;
      }
      // Normalize parent-local origin if N/W resize went negative, then paint.
      const placeParents = [];
      const elementParents = [];
      if (finished.targetKind === "place") {
        const node = graph?.nodes.find((n) => n.id === finished.targetId);
        if (!node) {
          await syncInspectorFromSelection();
          return;
        }
        placeParents.push(node.parent || null);
      } else {
        const elem = (graph?.elements || []).find(
          (e) => e.id === finished.targetId
        );
        if (!elem) {
          await syncInspectorFromSelection();
          return;
        }
        if (elem.parent) elementParents.push(elem.parent);
      }
      const norm = normalizeAfterLayoutGesture({
        placeParents,
        elementParents,
      });
      // Progressive refine (tubes then cables) — avoid blocking full clearSvg.
      updateNodeVisual(null, { progressive: true });
      await syncInspectorFromSelection();
      try {
        const payload = {};
        if (finished.targetKind === "place") {
          const ids = new Set([finished.targetId, ...norm.shiftedPlaces]);
          for (const id of ids) {
            const node = graph?.nodes.find((n) => n.id === id);
            if (!node) continue;
            payload[id] = { x: node.x, y: node.y };
            if (node.size_locked || id === finished.targetId) {
              payload[id].w = node.w;
              payload[id].h = node.h;
            }
          }
          for (const pid of norm.adjustedParents) {
            const parent = graph?.nodes.find((n) => n.id === pid);
            if (!parent) continue;
            // Auto absorb should persist origin shift, not lock in grown size.
            payload[pid] = { x: parent.x, y: parent.y };
          }
          const lastMeta = await api(`/api/physical/positions`, {
            method: "PATCH",
            body: JSON.stringify({
              location_id: locationId,
              positions: payload,
            }),
          });
          applyEditFlags(lastMeta);
          setStatus(t("status.resizedPlace"));
        } else {
          const ids = new Set([finished.targetId, ...norm.shiftedElems]);
          for (const id of ids) {
            const elem = (graph?.elements || []).find((e) => e.id === id);
            if (!elem) continue;
            payload[id] = { x: elem.x, y: elem.y };
            if (elem.size_locked || id === finished.targetId) {
              payload[id].w = elem.w;
              payload[id].h = elem.h;
            }
          }
          const placePayload = {};
          for (const pid of norm.adjustedParents) {
            const parent = graph?.nodes.find((n) => n.id === pid);
            if (!parent) continue;
            // Auto absorb should persist origin shift, not lock in grown size.
            placePayload[pid] = { x: parent.x, y: parent.y };
          }
          const lastMeta = await api(`/api/electrical/positions`, {
            method: "PATCH",
            body: JSON.stringify({
              location_id: locationId,
              positions: payload,
            }),
          });
          if (Object.keys(placePayload).length) {
            await api(`/api/physical/positions`, {
              method: "PATCH",
              body: JSON.stringify({
                location_id: locationId,
                positions: placePayload,
              }),
            });
          }
          applyEditFlags(lastMeta);
          setStatus(t("status.resizedElement"));
        }
        scheduleStatusRefresh();
      } catch (err) {
        setStatus(String(err.message || err));
      }
      return;
    }
    if (!finished.moved) {
      const now = Date.now();
      const isDbl =
        !finished.modClick &&
        finished.anchorKind === "place" &&
        selectedIds.size === 1 &&
        lastTap.id === finished.anchorId &&
        now - lastTap.t <= DBLCLICK_MS;
      lastTap = isDbl
        ? { id: null, t: 0 }
        : { id: finished.anchorId, t: now };
      if (isDbl) {
        const placeNode = graph?.nodes.find((n) => n.id === finished.anchorId);
        if (placeNode) {
          await enterNode(placeNode);
          return;
        }
      }
      await syncInspectorFromSelection();
      return;
    }
    lastTap = { id: null, t: 0 };
    if (!locationId) return;
    // Re-route tubes/cables once after the drag, not on every pointermove.
    // Element-only moves leave place boxes fixed → reuse conduit geometry.
    const items = finished.items || [];
    if (await tryReparentPlacesAfterDrag(finished, items)) {
      return;
    }
    const placeParents = [];
    const elementParents = [];
    for (const item of items) {
      if (item.kind === "place") {
        const node = graph?.nodes.find((n) => n.id === item.id);
        if (node) placeParents.push(node.parent || null);
      } else if (item.kind === "element") {
        const elem = (graph?.elements || []).find((e) => e.id === item.id);
        if (elem?.parent) elementParents.push(elem.parent);
      }
    }
    const norm = normalizeAfterLayoutGesture({ placeParents, elementParents });
    const onlyElements =
      items.length > 0 && items.every((it) => it.kind === "element");
    // SE growth happens in measureVisibleSizes; run it before deciding whether
    // host geometry changed enough to require conduit re-route.
    measureVisibleSizes();
    let hostsChanged = norm.adjustedParents.size > 0;
    if (!hostsChanged && finished.layoutSnapshot) {
      const beforeById = Object.fromEntries(
        (finished.layoutSnapshot.nodes || []).map((n) => [n.id, n])
      );
      const touchParents = new Set([
        ...elementParents.filter(Boolean),
        ...norm.adjustedParents,
      ]);
      for (const pid of touchParents) {
        const before = beforeById[pid];
        const now = (graph?.nodes || []).find((n) => n.id === pid);
        if (!before || !now) continue;
        if (
          Number(before.x) !== Number(now.x) ||
          Number(before.y) !== Number(now.y) ||
          Number(before.w) !== Number(now.w) ||
          Number(before.h) !== Number(now.h)
        ) {
          hostsChanged = true;
          break;
        }
      }
    }
    updateNodeVisual(null, {
      progressive: true,
      ...(onlyElements && !hostsChanged ? { skipConduits: true } : {}),
    });
    await syncInspectorFromSelection();
    try {
      const placePositions = {};
      const elemPositions = {};
      for (const item of items) {
        if (item.kind === "place") {
          const node = graph?.nodes.find((n) => n.id === item.id);
          if (node) {
            placePositions[item.id] = { x: node.x, y: node.y };
            if (node.size_locked) {
              placePositions[item.id].w = node.w;
              placePositions[item.id].h = node.h;
            }
          }
        } else if (item.kind === "element") {
          const elem = (graph?.elements || []).find((e) => e.id === item.id);
          if (elem) {
            elemPositions[item.id] = { x: elem.x, y: elem.y };
            if (elem.size_locked) {
              elemPositions[item.id].w = elem.w;
              elemPositions[item.id].h = elem.h;
            }
          }
        }
      }
      for (const id of norm.shiftedPlaces) {
        const node = graph?.nodes.find((n) => n.id === id);
        if (!node || placePositions[id]) continue;
        placePositions[id] = { x: node.x, y: node.y };
        if (node.size_locked) {
          placePositions[id].w = node.w;
          placePositions[id].h = node.h;
        }
      }
      for (const id of norm.shiftedElems) {
        const elem = (graph?.elements || []).find((e) => e.id === id);
        if (!elem || elemPositions[id]) continue;
        elemPositions[id] = { x: elem.x, y: elem.y };
        if (elem.size_locked) {
          elemPositions[id].w = elem.w;
          elemPositions[id].h = elem.h;
        }
      }
      for (const pid of norm.adjustedParents) {
        const parent = graph?.nodes.find((n) => n.id === pid);
        if (!parent) continue;
        // Auto absorb should persist origin shift, not lock in grown size.
        placePositions[pid] = { x: parent.x, y: parent.y };
      }
      if (
        !Object.keys(placePositions).length &&
        !Object.keys(elemPositions).length
      ) {
        return;
      }
      let lastMeta = null;
      if (Object.keys(placePositions).length) {
        lastMeta = await api(`/api/physical/positions`, {
          method: "PATCH",
          body: JSON.stringify({
            location_id: locationId,
            positions: placePositions,
          }),
        });
      }
      if (Object.keys(elemPositions).length) {
        lastMeta = await api(`/api/electrical/positions`, {
          method: "PATCH",
          body: JSON.stringify({
            location_id: locationId,
            positions: elemPositions,
          }),
        });
      }
      applyEditFlags(lastMeta);
      const n =
        Object.keys(placePositions).length + Object.keys(elemPositions).length;
      setStatus(t("status.moved", { n }));
      scheduleStatusRefresh();
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }

  function applyMultiDrag(ev) {
    if (!drag || drag.kind !== "multi") return;
    const dist = Math.hypot(
      ev.clientX - drag.startClientX,
      ev.clientY - drag.startClientY
    );
    if (!drag.moved && dist < DRAG_THRESHOLD) return;
    if (!drag.moved) {
      drag.moved = true;
      svg.classList.add("dragging");
      if (!drag.captured && drag.pointerId != null) {
        try {
          svg.setPointerCapture(drag.pointerId);
          drag.captured = true;
        } catch {
          /* ignore */
        }
      }
    }
    const dx = (ev.clientX - drag.startClientX) / scale;
    const dy = (ev.clientY - drag.startClientY) / scale;
    // Recompute from the initial drag snapshot every frame so box growth/shrink
    // is fully reversible when the pointer returns.
    restoreLayoutSnapshot(drag.layoutSnapshot);
    const placeMap = Object.fromEntries(
      (graph?.nodes || []).map((n) => [n.id, n])
    );
    for (const item of drag.items || []) {
      if (item.kind === "place") {
        const node = graph?.nodes.find((n) => n.id === item.id);
        if (!node) continue;
        const parent = node.parent ? placeMap[node.parent] : null;
        const d = storedDragDelta(parent, dx, dy);
        node.x = item.origX + d.dx;
        node.y = item.origY + d.dy;
      } else if (item.kind === "element") {
        const elem = (graph?.elements || []).find((e) => e.id === item.id);
        if (!elem) continue;
        const parent = elem.parent ? placeMap[elem.parent] : null;
        const d = storedDragDelta(parent, dx, dy);
        // x/y may go negative during the gesture; absorb N/W into the host box.
        elem.x = item.origX + d.dx;
        elem.y = item.origY + d.dy;
      }
    }
    const seenElem = new Set();
    const seenPlace = new Set();
    for (const item of drag.items || []) {
      if (item.kind === "element") {
        const elem = (graph?.elements || []).find((e) => e.id === item.id);
        if (elem?.parent && !seenElem.has(elem.parent)) {
          seenElem.add(elem.parent);
          absorbNegativeOriginLive(elem.parent, "element", { cascade: false });
        }
      } else if (item.kind === "place") {
        const node = graph?.nodes.find((n) => n.id === item.id);
        if (!node) continue;
        const key = node.parent || "";
        if (!seenPlace.has(key)) {
          seenPlace.add(key);
          absorbNegativeOriginLive(node.parent || null, "place", {
            cascade: false,
          });
        }
      }
    }
    // Transforms only while dragging; full cable/conduit re-route on drop.
    updateNodeVisual(null, { refresh: false });
  }

  async function endMarquee(ev) {
    if (!marquee) return;
    if (ev && marquee.pointerId != null && ev.pointerId !== marquee.pointerId) {
      return;
    }
    const finished = marquee;
    marquee = null;
    hideMarquee();
    try {
      if (
        finished.captured &&
        finished.pointerId != null &&
        svg.hasPointerCapture?.(finished.pointerId)
      ) {
        svg.releasePointerCapture(finished.pointerId);
      }
    } catch {
      /* ignore */
    }
    if (!finished.moved) {
      if (!finished.additive) {
        clearSelectionState();
        setSelectedVisual();
        await fillPlaceInspector(null);
        highlightOutline(locationId);
      }
      return;
    }
    const w0 = clientToWorld(finished.startClientX, finished.startClientY);
    const w1 = clientToWorld(
      ev?.clientX ?? finished.startClientX,
      ev?.clientY ?? finished.startClientY
    );
    const worldRect = {
      x1: Math.min(w0.x, w1.x),
      y1: Math.min(w0.y, w1.y),
      x2: Math.max(w0.x, w1.x),
      y2: Math.max(w0.y, w1.y),
    };
    const hit = idsInMarqueeWorld(
      worldRect,
      finished.additive || isModClick(ev)
    );
    commitSelection(hit, [...hit].slice(-1)[0] ?? null);
    await syncInspectorFromSelection();
  }

  svg.addEventListener("pointermove", (ev) => {
    if (wiringMode) {
      syncWiringPointer(ev.clientX, ev.clientY);
    }
    if (drag) {
      if (drag.kind === "resize") applyResizeDrag(ev);
      else applyMultiDrag(ev);
      scheduleEdgeAutoPan(ev);
      return;
    }
    stopEdgeAutoPan();
    if (marquee) {
      const dist = Math.hypot(
        ev.clientX - marquee.startClientX,
        ev.clientY - marquee.startClientY
      );
      if (!marquee.moved && dist < DRAG_THRESHOLD) return;
      if (!marquee.moved) {
        marquee.moved = true;
      }
      const rect = viewport.getBoundingClientRect();
      updateMarqueeDom(
        marquee.startClientX - rect.left,
        marquee.startClientY - rect.top,
        ev.clientX - rect.left,
        ev.clientY - rect.top
      );
      return;
    }
    if (panDrag) {
      const dist = Math.hypot(ev.clientX - panDrag.x, ev.clientY - panDrag.y);
      if (!panDrag.moved && dist >= DRAG_THRESHOLD) {
        panDrag.moved = true;
      }
      if (!panDrag.moved) return;
      panX = panDrag.panX + (ev.clientX - panDrag.x);
      panY = panDrag.panY + (ev.clientY - panDrag.y);
      applyWorldTransform();
    }
  });

  svg.addEventListener("pointerup", (ev) => {
    if (drag) {
      endDrag(ev);
      return;
    }
    if (marquee) {
      endMarquee(ev);
      return;
    }
    if (panDrag) {
      const clearSel = panDrag.clearOnClick && !panDrag.moved;
      endPanDrag();
      if (clearSel) {
        clearSelectionState();
        setSelectedVisual();
        fillPlaceInspector(null).catch((err) =>
          setStatus(String(err.message || err))
        );
        highlightOutline(locationId);
      }
    }
  });

  svg.addEventListener("pointercancel", (ev) => {
    stopEdgeAutoPan();
    if (drag) endDrag(ev);
    if (marquee) endMarquee(ev);
    endPanDrag();
    hideMarquee();
  });

  function scheduleStatusRefresh() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(refreshStatus, 400);
  }

  async function refreshStatus() {
    try {
      const st = applyWorkspaceStatus(await api("/api/workspace"));
      if (!hasDocument) {
        updateDocStatusStrip();
        return;
      }
      const n = (st.dirty || []).length;
      const dirty = n > 0 || dirtyLocal;
      updateFileMenuState({ dirty });
    } catch {
      /* ignore */
    }
  }

  function updateSaveButton(dirty) {
    updateFileMenuState({ dirty });
  }

  async function saveDocument() {
    if (!documentHasSaveTarget()) {
      // New / browser-origin docs without a write target → Save As.
      await fileSaveAs();
      return null;
    }
    const handle = activeDocId ? fileHandles[activeDocId] : null;
    if (handle && !isDesktopMode()) {
      // Web File System Access: keep server buffer and write-back to the handle.
      const exported = await api("/api/workspace/yaml");
      await writeTextToFileHandle(handle, exported.content);
    }
    const data = await api("/api/save", { method: "POST", body: "{}" });
    setStatus(t("status.saved", { n: (data.saved || []).length }));
    applyEditFlags(data);
    dirtyLocal = false;
    updateSaveButton(false);
    await refreshDocumentLabel();
    return data;
  }

  function rememberCurrentDocView() {
    if (!activeDocId) return;
    const atMax = depthLevel >= Math.max(maxDepth, 1);
    docViews[activeDocId] = {
      locationId,
      depthLevel,
      // Never persist electrical-on for a shallow depth (invalid on restore).
      showElectrical: Boolean(showElectrical) && atMax,
      panX,
      panY,
      scale,
    };
    persistDocViews();
  }

  function applySavedCamera(saved) {
    if (!saved) return false;
    if (
      !Number.isFinite(saved.panX) ||
      !Number.isFinite(saved.panY) ||
      !Number.isFinite(saved.scale)
    ) {
      return false;
    }
    panX = saved.panX;
    panY = saved.panY;
    scale = Math.min(3, Math.max(0.05, saved.scale));
    applyWorldTransform();
    rememberCurrentDocView();
    return true;
  }

  function resetCanvasState() {
    locationId = null;
    graph = null;
    clearSelectionState();
    dirtyLocal = false;
    canUndo = false;
    canRedo = false;
    canReset = false;
    outlineCollapseReady = false;
    collapsedOutline = new Set();
    svg.innerHTML = "";
  }

  async function reloadAfterDocumentChange() {
    resetCanvasState();
    try {
      applyWorkspaceStatus(await api("/api/workspace"));
    } catch {
      hasDocument = true;
      updateFileMenuState({ dirty: false });
    }
    await loadLocations();
  }

  function clearDocumentUi() {
    clearTimeout(saveTimer);
    saveTimer = null;
    resetCanvasState();
    fileHandles = {};
    docViews = {};
    persistDocViews();
    activeDocId = null;
    hasDocument = false;
    updateFileMenuState({ dirty: false });
    const outline = document.getElementById("outline-tree");
    if (outline) outline.innerHTML = "";
    renderDocTabs({ documents: [], active: null, document: null });
  }

  let menuBarArmed = false;

  function isMenuOpen(name) {
    const menu = document.getElementById(`menu-${name}`);
    return Boolean(menu && !menu.classList.contains("hidden"));
  }

  function anyMenuOpen() {
    return Boolean(document.querySelector(".menu-dropdown:not(.hidden)"));
  }

  function closeAllMenus() {
    document.querySelectorAll(".menu-dropdown, .menu-flyout").forEach((menu) => {
      menu.classList.add("hidden");
    });
    document.querySelectorAll(".menu-btn").forEach((btn) => {
      btn.setAttribute("aria-expanded", "false");
    });
    document.querySelectorAll(".menu-submenu-trigger").forEach((btn) => {
      btn.setAttribute("aria-expanded", "false");
    });
    document.querySelectorAll(".menu-item-submenu").forEach((el) => {
      el.classList.remove("is-open");
    });
    menuBarArmed = false;
  }

  function openMenu(name) {
    const menu = document.getElementById(`menu-${name}`);
    const btn = document.getElementById(`menu-${name}-btn`);
    if (!menu || !btn) return;
    closeAllMenus();
    menu.classList.remove("hidden");
    btn.setAttribute("aria-expanded", "true");
    menuBarArmed = true;
  }

  function toggleMenu(name) {
    if (isMenuOpen(name)) {
      closeAllMenus();
      return;
    }
    openMenu(name);
  }

  function closeFileMenu() {
    closeAllMenus();
  }

  function toggleFileMenu() {
    toggleMenu("file");
  }

  function syncElectricalUi() {
    const btn = document.getElementById("btn-electrical");
    if (btn) btn.setAttribute("aria-pressed", showElectrical ? "true" : "false");
    const mi = document.getElementById("menu-electrical");
    if (mi) mi.setAttribute("aria-checked", showElectrical ? "true" : "false");
    const needHint = t("palette.needsElectrical");
    const insertEnabled = elementsInsertEnabled();
    document.querySelectorAll("[data-needs-electrical]").forEach((el) => {
      el.disabled = !insertEnabled;
      if (insertEnabled) {
        el.removeAttribute("title");
      } else {
        el.title = needHint;
      }
    });
    const elemGroup = document.getElementById("palette-group-elements");
    if (elemGroup) {
      elemGroup.classList.toggle("is-electrical-off", !insertEnabled);
      elemGroup.title = insertEnabled ? "" : needHint;
    }
    renderPaletteSideList();
  }

  /**
   * Electrical is only valid at max depth. Returns true if it was turned off.
   * @param {{ repaint?: boolean }} [opts]
   */
  function enforceElectricalDepthInvariant(opts) {
    const repaint = !opts || opts.repaint !== false;
    if (!showElectrical) return false;
    if (depthLevel >= Math.max(maxDepth, 1)) return false;
    showElectrical = false;
    depthBeforeElectrical = null;
    syncElectricalUi();
    if (repaint && graph) {
      render();
      renderOutline();
    }
    rememberCurrentDocView();
    return true;
  }

  async function setElectrical(on) {
    const want = Boolean(on);
    const turningOn = want && !showElectrical;
    const turningOff = !want && showElectrical;
    showElectrical = want;
    syncElectricalUi();
    if (!showElectrical && selectedId) {
      const isElem = (graph?.elements || []).some((e) => e.id === selectedId);
      if (isElem) clearSelectionState();
    }
    if (!showElectrical) {
      endCatalogPlacementMode();
      if (wiringMode?.kind === "conductor") cancelWiringMode();
    }
    if (turningOn) {
      depthBeforeElectrical = depthLevel;
      const target = Math.max(maxDepth, 1);
      if (depthLevel < target) {
        await setDepth(target);
      } else {
        render();
        renderOutline();
      }
    } else if (turningOff) {
      const restore = depthBeforeElectrical;
      depthBeforeElectrical = null;
      if (restore != null && restore !== depthLevel) {
        const capped = Math.min(
          Math.max(1, restore),
          Math.max(maxDepth, 1)
        );
        await setDepth(capped);
      } else {
        render();
        renderOutline();
      }
    } else {
      render();
      renderOutline();
    }
    rememberCurrentDocView();
    await syncInspectorFromSelection().catch((err) =>
      setStatus(String(err.message || err))
    );
  }

