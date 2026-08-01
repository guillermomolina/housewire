(() => {
  const svg = document.getElementById("canvas");
  const locationSelect = document.getElementById("location-select");
  const representationSelect = document.getElementById("representation");
  const depthLabel = document.getElementById("depth-label");
  const statusEl = document.getElementById("status");
  const viewport = document.getElementById("viewport");

  const LEAF_W = 120;
  const LEAF_H = 56;
  const PAD = 16;
  const HEADER = 28;

  let graph = null;
  let locationId = null;
  let selectedId = null;
  let depthLevel = 1;
  let maxDepth = 1;
  let scale = 1;
  let panX = 40;
  let panY = 40;
  let dirtyLocal = false;
  let drag = null;
  let panDrag = null;
  let saveTimer = null;
  let worldEl = null;
  let nodesById = {};
  let edgePaths = [];
  let lastTap = { id: null, t: 0 };
  const DRAG_THRESHOLD = 4;
  const DBLCLICK_MS = 400;

  const ns = "http://www.w3.org/2000/svg";

  function setStatus(text) {
    statusEl.textContent = text || "";
  }

  function updateDepthLabel() {
    if (depthLabel) {
      depthLabel.textContent = `depth ${depthLevel}/${Math.max(maxDepth, 1)}`;
    }
    const deeper = document.getElementById("btn-depth-in");
    const shallower = document.getElementById("btn-depth-out");
    if (deeper) deeper.disabled = depthLevel >= Math.max(maxDepth, 1);
    if (shallower) shallower.disabled = depthLevel <= 1;
  }

  async function api(path, options) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
      ...options,
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(body || res.statusText);
    }
    return res.json();
  }

  function nodeW(node) {
    return node.w || LEAF_W;
  }

  function nodeH(node) {
    return node.h || LEAF_H;
  }

  function childrenOf(parentId) {
    const key = parentId || null;
    return (graph?.nodes || []).filter((n) => (n.parent || null) === key);
  }

  function measureSizes() {
    if (!graph) return;
    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));

    function measure(node) {
      const kids = childrenOf(node.id);
      if (!kids.length) {
        node.w = LEAF_W;
        node.h = LEAF_H;
        return;
      }
      for (const kid of kids) measure(kid);
      let maxR = 0;
      let maxB = 0;
      for (const kid of kids) {
        maxR = Math.max(maxR, (kid.x ?? 0) + nodeW(kid));
        maxB = Math.max(maxB, (kid.y ?? 0) + nodeH(kid));
      }
      node.w = Math.max(LEAF_W, maxR + PAD);
      node.h = Math.max(LEAF_H, HEADER + maxB + PAD);
    }

    for (const node of childrenOf(null)) measure(node);
    // Keep map warm for abs lookups during measure of orphans
    void byId;
  }

  function absXY(node, byId) {
    const map =
      byId || Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
    if (!node.parent) {
      return { x: node.x ?? 0, y: node.y ?? 0 };
    }
    const parent = map[node.parent];
    if (!parent) {
      return { x: node.x ?? 0, y: node.y ?? 0 };
    }
    const pa = absXY(parent, map);
    return {
      x: pa.x + PAD + (node.x ?? 0),
      y: pa.y + HEADER + (node.y ?? 0),
    };
  }

  function nodeCenterAbs(node, byId) {
    const a = absXY(node, byId);
    return {
      x: a.x + nodeW(node) / 2,
      y: a.y + nodeH(node) / 2,
    };
  }

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
    const declared = (node.openings || [])
      .map((o) => parseSideOpening(o.id))
      .filter((p) => p && p.face === face)
      .map((p) => p.index);
    const maxDeclared = declared.length ? Math.max(...declared) : 0;
    return Math.max(maxDeclared, preferIndex || 1, declared.length, 1);
  }

  function openingAnchorAbs(node, openingId, face, byId) {
    const a = absXY(node, byId);
    const w = nodeW(node);
    const h = nodeH(node);
    const side = parseSideOpening(openingId);
    const plane = parsePlaneOpening(openingId);
    const f = (
      side?.face ||
      plane?.face ||
      face ||
      (openingId || "?")[0] ||
      "?"
    ).toUpperCase();

    if (f === "B" || f === "F") {
      const c = nodeCenterAbs(node, byId);
      if (!plane) return c;
      const cols = Math.max(plane.col, 2);
      const rows = Math.max(plane.row, 2);
      const ox = ((plane.col - 0.5) / cols - 0.5) * (w * 0.35);
      const oy = ((plane.row - 0.5) / rows - 0.5) * (h * 0.35);
      return { x: c.x + ox, y: c.y + oy };
    }

    const index = side?.index || 1;
    const n = sideSlotCount(node, f, index);
    const t = index / (n + 1);

    if (f === "N") return { x: a.x + t * w, y: a.y };
    if (f === "S") return { x: a.x + t * w, y: a.y + h };
    if (f === "W") return { x: a.x, y: a.y + t * h };
    if (f === "E") return { x: a.x + w, y: a.y + t * h };
    return nodeCenterAbs(node, byId);
  }

  /** Local (0,0) anchor for labels drawn inside the node group. */
  function openingAnchorLocal(node, openingId, face) {
    const w = nodeW(node);
    const h = nodeH(node);
    const side = parseSideOpening(openingId);
    const plane = parsePlaneOpening(openingId);
    const f = (
      side?.face ||
      plane?.face ||
      face ||
      (openingId || "?")[0] ||
      "?"
    ).toUpperCase();

    if (f === "B" || f === "F") {
      if (!plane) return { x: w / 2, y: h / 2 };
      const cols = Math.max(plane.col, 2);
      const rows = Math.max(plane.row, 2);
      const ox = ((plane.col - 0.5) / cols - 0.5) * (w * 0.35);
      const oy = ((plane.row - 0.5) / rows - 0.5) * (h * 0.35);
      return { x: w / 2 + ox, y: h / 2 + oy };
    }

    const index = side?.index || 1;
    const n = sideSlotCount(node, f, index);
    const t = index / (n + 1);
    if (f === "N") return { x: t * w, y: 0 };
    if (f === "S") return { x: t * w, y: h };
    if (f === "W") return { x: 0, y: t * h };
    if (f === "E") return { x: w, y: t * h };
    return { x: w / 2, y: h / 2 };
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
          const ox = nested ? 16 : 80;
          const oy = nested ? 36 : 80;
          const gx = nested ? 140 : 180;
          const gy = nested ? 100 : 140;
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
    edgePaths = [];
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

  function applyWorldTransform() {
    if (worldEl) {
      worldEl.setAttribute(
        "transform",
        `translate(${panX},${panY}) scale(${scale})`
      );
    }
  }

  function edgePathD(edge, byId) {
    const a = byId[edge.from];
    const b = byId[edge.to];
    if (!a || !b) return null;
    const p1 = openingAnchorAbs(a, edge.from_opening, edge.from_opening?.[0], byId);
    const p2 = openingAnchorAbs(b, edge.to_opening, edge.to_opening?.[0], byId);
    return `M ${p1.x} ${p1.y} L ${p2.x} ${p2.y}`;
  }

  function refreshEdges() {
    if (!graph) return;
    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    measureSizes();
    for (const item of edgePaths) {
      const d = edgePathD(item.edge, byId);
      if (d) {
        for (const path of item.paths) path.setAttribute("d", d);
      }
    }
  }

  function updateNodeVisual(_node) {
    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    measureSizes();
    for (const n of graph.nodes) {
      const g = nodesById[n.id];
      if (!g) continue;
      const a = absXY(n, byId);
      g.setAttribute("transform", `translate(${a.x},${a.y})`);
      const box = g.querySelector(".node-box");
      if (box) {
        box.setAttribute("width", String(nodeW(n)));
        box.setAttribute("height", String(nodeH(n)));
      }
    }
    refreshEdges();
  }

  function paintNode(node, layerG, byId) {
    const a = absXY(node, byId);
    const w = nodeW(node);
    const h = nodeH(node);
    const hasKids = childrenOf(node.id).length > 0;
    const g = el("g", {
      class: "node" + (hasKids ? " container" : ""),
      "data-id": node.id,
      transform: `translate(${a.x},${a.y})`,
    });
    const box = el("rect", {
      class:
        "node-box" +
        (selectedId === node.id ? " selected" : "") +
        (hasKids ? " container" : "") +
        (node.expandable ? " expandable" : ""),
      width: w,
      height: h,
      rx: 6,
    });
    g.appendChild(box);
    g.appendChild(
      el("text", { class: "node-label", x: 8, y: 18 }, node.label || node.id)
    );
    g.appendChild(
      el(
        "text",
        { class: "node-type", x: 8, y: 34 },
        (node.type || "") + (node.expandable ? " · +" : "")
      )
    );

    if (!hasKids) {
      const backs = (node.openings || []).filter((o) => o.face === "B");
      const sides = (node.openings || []).filter(
        (o) => o.face !== "B" && o.face !== "F"
      );
      for (const op of sides) {
        const anchor = openingAnchorLocal(node, op.id, op.face);
        const labelX =
          op.face === "W" ? 4 : op.face === "E" ? w - 4 : anchor.x;
        const labelY =
          op.face === "N" ? 10 : op.face === "S" ? h - 3 : anchor.y + 3;
        g.appendChild(
          el(
            "text",
            {
              class: "opening-side",
              x: labelX,
              y: labelY,
              "text-anchor":
                op.face === "W" ? "start" : op.face === "E" ? "end" : "middle",
            },
            op.id
          )
        );
      }
      if (backs.length) {
        g.appendChild(
          el("circle", {
            class: "opening-back-mark",
            cx: w / 2,
            cy: h / 2 + 6,
            r: 7,
          })
        );
        g.appendChild(
          el(
            "text",
            {
              class: "opening-back",
              x: w / 2,
              y: h / 2 + 9,
              "text-anchor": "middle",
            },
            backs.map((b) => b.id).join(",")
          )
        );
      }
    }

    box.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      ev.stopPropagation();
      raiseNode(node.id);
      // Defer capture until real drag — early capture kills dblclick.
      drag = {
        id: node.id,
        pointerId: ev.pointerId,
        startClientX: ev.clientX,
        startClientY: ev.clientY,
        origX: node.x,
        origY: node.y,
        moved: false,
        captured: false,
      };
    });

    layerG.appendChild(g);
    nodesById[node.id] = g;
  }

  function raiseNode(id) {
    const gEl = nodesById[id];
    if (gEl && gEl.parentNode) gEl.parentNode.appendChild(gEl);
    for (const kid of childrenOf(id)) raiseNode(kid.id);
  }

  function render() {
    if (!graph) return;
    ensurePositions();
    measureSizes();
    clearSvg();

    worldEl = el("g", { id: "world" });
    applyWorldTransform();
    svg.appendChild(worldEl);

    const page = graph.page || {};
    const representation =
      representationSelect.value || page.representation || "line";
    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));

    // Containers under edges under leaves so nested conduits stay visible.
    const containersG = el("g", { class: "containers" });
    const edgesG = el("g", { class: "edges" });
    const leavesG = el("g", { class: "leaves" });
    worldEl.appendChild(containersG);
    worldEl.appendChild(edgesG);
    worldEl.appendChild(leavesG);

    const byDepth = [...graph.nodes].sort(
      (a, b) => (a.parts?.length || 0) - (b.parts?.length || 0)
    );
    for (const node of byDepth) {
      if (childrenOf(node.id).length) paintNode(node, containersG, byId);
    }

    for (const edge of graph.edges) {
      const d = edgePathD(edge, byId);
      if (!d) continue;
      const contains = (edge.contains || []).join(", ");
      const title = contains
        ? `${edge.id}: ${contains}`
        : String(edge.id || "");
      const paths = [];
      if (representation === "tube") {
        const tube = el("path", { class: "edge-tube", d });
        const core = el("path", { class: "edge-tube-core", d });
        tube.appendChild(el("title", null, title));
        core.appendChild(el("title", null, title));
        edgesG.appendChild(tube);
        edgesG.appendChild(core);
        paths.push(tube, core);
      } else {
        const line = el("path", { class: "edge-line", d });
        line.appendChild(el("title", null, title));
        edgesG.appendChild(line);
        paths.push(line);
      }
      edgePaths.push({ edge, paths });
    }

    for (const node of graph.nodes) {
      if (!childrenOf(node.id).length) paintNode(node, leavesG, byId);
    }
    updateDepthLabel();
  }

  function setSelectedVisual(id) {
    for (const [nid, g] of Object.entries(nodesById)) {
      const box = g.querySelector(".node-box");
      if (!box) continue;
      if (nid === id) box.classList.add("selected");
      else box.classList.remove("selected");
    }
  }

  async function selectNode(id) {
    selectedId = id;
    setSelectedVisual(id);
    const empty = document.getElementById("panel-empty");
    const show = document.getElementById("panel-show");
    if (!id || !locationId) {
      empty.classList.remove("hidden");
      show.classList.add("hidden");
      return;
    }
    try {
      const detail = await api(
        `/api/place?location=${encodeURIComponent(locationId)}&id=${encodeURIComponent(id)}`
      );
      empty.classList.add("hidden");
      show.classList.remove("hidden");
      const meta = document.getElementById("show-meta");
      meta.innerHTML = "";
      const rows = [
        ["id", detail.id],
        ["type", detail.type],
        ["subtype", detail.subtype],
        ["label", detail.label],
        ["install", detail.install],
        ["mount", detail.mount],
        ["openings", (detail.openings || []).join(", ")],
        ["connects", (detail.connects || []).join(" ↔ ")],
        ["notes", detail.notes],
      ];
      for (const [k, v] of rows) {
        if (v == null || v === "") continue;
        const dt = document.createElement("dt");
        dt.textContent = k;
        const dd = document.createElement("dd");
        dd.textContent = String(v);
        meta.appendChild(dt);
        meta.appendChild(dd);
      }
      const ul = document.getElementById("show-elements");
      ul.innerHTML = "";
      for (const elItem of detail.elements || []) {
        const li = document.createElement("li");
        li.textContent = `${elItem.id} (${elItem.type || "?"}${
          elItem.subtype ? " / " + elItem.subtype : ""
        })`;
        ul.appendChild(li);
      }
      prefillRecipesFromSelection(detail);
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }

  function prefillRecipesFromSelection(detail) {
    const openings = detail.openings || [];
    const prefer =
      openings.find((o) => String(o).startsWith("N")) ||
      openings[0] ||
      "N1";
    const fromVal = `${detail.id}.${prefer}`;
    for (const formId of ["form-socket", "form-lamp"]) {
      const form = document.getElementById(formId);
      const from = form.querySelector('[name="from"]');
      if (from && !from.value) from.value = fromVal;
      else if (from) from.value = fromVal;
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
    const opt = [...locationSelect.options].find((o) => o.value === nextId);
    if (opt && !opt.disabled) {
      locationSelect.value = nextId;
      depthLevel = 1;
      await loadLocation();
      setStatus(`Entered ${nextId}`);
      return;
    }
    // Not a canvas root in the selector: deepen the view instead.
    if (node.expandable || childrenOf(node.id).length) {
      await setDepth(depthLevel + 1);
      setStatus(`Depth ${depthLevel}`);
      return;
    }
    setStatus(`No deeper view for ${node.id}`);
  }

  async function endDrag(ev) {
    if (!drag) return;
    if (ev && drag.pointerId != null && ev.pointerId !== drag.pointerId) return;
    const node = graph?.nodes.find((n) => n.id === drag.id);
    svg.classList.remove("dragging");
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
    if (!finished.moved) {
      const now = Date.now();
      const isDbl =
        lastTap.id === finished.id && now - lastTap.t <= DBLCLICK_MS;
      lastTap = isDbl ? { id: null, t: 0 } : { id: finished.id, t: now };
      if (isDbl && node) {
        await enterNode(node);
        return;
      }
      await selectNode(finished.id);
      return;
    }
    lastTap = { id: null, t: 0 };
    if (!node || !locationId) return;
    await selectNode(finished.id);
    try {
      await api(`/api/physical/positions`, {
        method: "PATCH",
        body: JSON.stringify({
          location_id: locationId,
          positions: { [finished.id]: { x: node.x, y: node.y } },
        }),
      });
      setStatus(`Moved ${finished.id} · unsaved`);
      scheduleStatusRefresh();
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }

  svg.addEventListener("pointermove", (ev) => {
    if (drag) {
      const node = graph?.nodes.find((n) => n.id === drag.id);
      if (!node) return;
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
      node.x = Math.round(drag.origX + dx);
      node.y = Math.round(drag.origY + dy);
      dirtyLocal = true;
      updateNodeVisual(node);
      return;
    }
    if (panDrag) {
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
    if (panDrag) {
      panDrag = null;
      viewport.classList.remove("panning");
    }
  });

  svg.addEventListener("pointercancel", (ev) => {
    if (drag) endDrag(ev);
    panDrag = null;
    viewport.classList.remove("panning");
  });

  function scheduleStatusRefresh() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(refreshStatus, 400);
  }

  async function refreshStatus() {
    try {
      const st = await api("/api/status");
      const n = (st.dirty || []).length;
      setStatus(
        n ? `${n} dirty file(s)` : dirtyLocal ? "layout pending" : "saved"
      );
      if (!n) dirtyLocal = false;
    } catch {
      /* ignore */
    }
  }

  async function loadLocations() {
    const data = await api("/api/locations");
    locationSelect.innerHTML = "";
    const rows = data.locations || [];
    for (const loc of rows) {
      const opt = document.createElement("option");
      opt.value = loc.id;
      const pad = "\u00A0\u00A0".repeat(loc.depth || 0);
      const branch = (loc.depth || 0) > 0 ? "└ " : "";
      opt.textContent =
        pad +
        branch +
        (loc.label || loc.id) +
        (loc.type ? ` (${loc.type})` : "");
      if (loc.selectable === false) {
        opt.disabled = true;
      }
      locationSelect.appendChild(opt);
    }
    const first =
      rows.find((r) => r.selectable !== false && r.id === ".") ||
      rows.find((r) => r.selectable !== false);
    if (first) {
      locationId = first.id;
      locationSelect.value = locationId;
      await loadLocation();
    } else {
      setStatus("No locations with children found");
    }
  }

  async function loadLocation() {
    locationId = locationSelect.value;
    selectedId = null;
    document.getElementById("panel-empty").classList.remove("hidden");
    document.getElementById("panel-show").classList.add("hidden");
    graph = await api(
      `/api/physical?location=${encodeURIComponent(locationId)}&depth=${depthLevel}`
    );
    depthLevel = graph.depth || depthLevel;
    maxDepth = graph.max_depth || 1;
    if (depthLevel > maxDepth) depthLevel = Math.max(maxDepth, 1);
    representationSelect.value = graph.page?.representation || "line";
    render();
    await refreshStatus();
  }

  async function setDepth(next) {
    const capped = Math.min(Math.max(1, next), Math.max(maxDepth, 1));
    if (capped === depthLevel && graph) {
      updateDepthLabel();
      return;
    }
    depthLevel = capped;
    await loadLocation();
  }

  locationSelect.addEventListener("change", () => {
    depthLevel = 1;
    loadLocation().catch((err) => setStatus(String(err.message || err)));
  });

  representationSelect.addEventListener("change", async () => {
    const value = representationSelect.value;
    render();
    if (!locationId) return;
    try {
      await api(`/api/physical/page`, {
        method: "PATCH",
        body: JSON.stringify({ location_id: locationId, representation: value }),
      });
      setStatus(`representation=${value} · unsaved`);
      scheduleStatusRefresh();
    } catch (err) {
      setStatus(String(err.message || err));
    }
  });

  document.getElementById("btn-auto").addEventListener("click", async () => {
    try {
      const data = await api(`/api/physical/auto-layout`, {
        method: "POST",
        body: JSON.stringify({
          location_id: locationId,
          force: false,
          depth: depthLevel,
        }),
      });
      graph = data.graph;
      depthLevel = graph.depth || depthLevel;
      maxDepth = graph.max_depth || maxDepth;
      render();
      setStatus(`auto-layout: ${data.updated.length} node(s)`);
      scheduleStatusRefresh();
    } catch (err) {
      setStatus(String(err.message || err));
    }
  });

  document.getElementById("btn-auto-force").addEventListener("click", async () => {
    try {
      const data = await api(`/api/physical/auto-layout`, {
        method: "POST",
        body: JSON.stringify({
          location_id: locationId,
          force: true,
          depth: depthLevel,
        }),
      });
      graph = data.graph;
      depthLevel = graph.depth || depthLevel;
      maxDepth = graph.max_depth || maxDepth;
      render();
      setStatus(`auto-layout force: ${data.updated.length} node(s)`);
      scheduleStatusRefresh();
    } catch (err) {
      setStatus(String(err.message || err));
    }
  });

  document.getElementById("btn-save").addEventListener("click", async () => {
    try {
      const data = await api("/api/save", { method: "POST", body: "{}" });
      setStatus(`saved ${data.saved.length} file(s)`);
      dirtyLocal = false;
    } catch (err) {
      setStatus(String(err.message || err));
    }
  });

  document.getElementById("btn-zoom-in").addEventListener("click", () => {
    scale = Math.min(3, scale * 1.15);
    applyWorldTransform();
  });
  document.getElementById("btn-zoom-out").addEventListener("click", () => {
    scale = Math.max(0.35, scale / 1.15);
    applyWorldTransform();
  });
  document.getElementById("btn-zoom-reset").addEventListener("click", () => {
    scale = 1;
    panX = 40;
    panY = 40;
    applyWorldTransform();
  });

  document.getElementById("btn-depth-in").addEventListener("click", () => {
    setDepth(depthLevel + 1).catch((err) => setStatus(String(err.message || err)));
  });
  document.getElementById("btn-depth-out").addEventListener("click", () => {
    setDepth(depthLevel - 1).catch((err) => setStatus(String(err.message || err)));
  });

  viewport.addEventListener("pointerdown", (ev) => {
    if (drag) return;
    if (ev.target !== svg && ev.target !== viewport) return;
    if (ev.button !== 0) return;
    panDrag = { x: ev.clientX, y: ev.clientY, panX, panY };
    viewport.classList.add("panning");
    svg.setPointerCapture(ev.pointerId);
  });

  viewport.addEventListener(
    "wheel",
    (ev) => {
      ev.preventDefault();
      if (ev.altKey) {
        const delta = ev.deltaY > 0 ? -1 : 1;
        setDepth(depthLevel + delta).catch((err) =>
          setStatus(String(err.message || err))
        );
        return;
      }
      const factor = ev.deltaY > 0 ? 1 / 1.08 : 1.08;
      scale = Math.min(3, Math.max(0.35, scale * factor));
      applyWorldTransform();
    },
    { passive: false }
  );

  document.querySelectorAll(".recipe-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".recipe-tab").forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
      const kind = btn.dataset.recipe;
      for (const id of ["socket", "lamp", "feed"]) {
        document
          .getElementById(`form-${id}`)
          .classList.toggle("hidden", id !== kind);
      }
    });
  });

  function recipeMsg(text) {
    document.getElementById("recipe-msg").textContent = text || "";
  }

  async function submitRecipe(kind, form) {
    if (!locationId) return;
    const data = Object.fromEntries(new FormData(form).entries());
    const body = { location_id: locationId, depth: depthLevel, ...data };
    for (const key of Object.keys(body)) {
      if (body[key] === "") delete body[key];
    }
    recipeMsg("…");
    try {
      const res = await api(`/api/recipes/${kind}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      graph = res.graph;
      depthLevel = graph.depth || depthLevel;
      maxDepth = graph.max_depth || maxDepth;
      render();
      const newId = res.result?.place_id;
      if (newId) await selectNode(newId);
      recipeMsg(
        `${kind}: ${res.result?.cable_name || ""} + ${res.result?.conduit_name || ""}`
      );
      setStatus(`${kind} added · unsaved`);
      scheduleStatusRefresh();
      form.reset();
      if (selectedId) {
        const detail = await api(
          `/api/place?location=${encodeURIComponent(locationId)}&id=${encodeURIComponent(selectedId)}`
        );
        prefillRecipesFromSelection(detail);
      }
    } catch (err) {
      recipeMsg(String(err.message || err));
    }
  }

  document.getElementById("form-socket").addEventListener("submit", (ev) => {
    ev.preventDefault();
    submitRecipe("socket", ev.target);
  });
  document.getElementById("form-lamp").addEventListener("submit", (ev) => {
    ev.preventDefault();
    submitRecipe("lamp", ev.target);
  });
  document.getElementById("form-feed").addEventListener("submit", (ev) => {
    ev.preventDefault();
    submitRecipe("feed", ev.target);
  });

  loadLocations().catch((err) => setStatus(String(err.message || err)));
})();
