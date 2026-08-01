(() => {
  const svg = document.getElementById("canvas");
  const locationSelect = document.getElementById("location-select");
  const representationSelect = document.getElementById("representation");
  const statusEl = document.getElementById("status");
  const viewport = document.getElementById("viewport");

  const NODE_W = 120;
  const NODE_H = 56;

  let graph = null;
  let locationId = null;
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

  const ns = "http://www.w3.org/2000/svg";

  function setStatus(text) {
    statusEl.textContent = text || "";
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

  function nodeCenter(node) {
    return {
      x: (node.x ?? 0) + NODE_W / 2,
      y: (node.y ?? 0) + NODE_H / 2,
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

  function openingAnchor(node, openingId, face) {
    const x = node.x ?? 0;
    const y = node.y ?? 0;
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
      const c = nodeCenter(node);
      if (!plane) return c;
      // Slight offset inside the box so several B/F ids are distinguishable.
      const cols = Math.max(plane.col, 2);
      const rows = Math.max(plane.row, 2);
      const ox = ((plane.col - 0.5) / cols - 0.5) * (NODE_W * 0.35);
      const oy = ((plane.row - 0.5) / rows - 0.5) * (NODE_H * 0.35);
      return { x: c.x + ox, y: c.y + oy };
    }

    const index = side?.index || 1;
    const n = sideSlotCount(node, f, index);
    const t = index / (n + 1); // 1-based index → fraction along face

    if (f === "N") return { x: x + t * NODE_W, y };
    if (f === "S") return { x: x + t * NODE_W, y: y + NODE_H };
    if (f === "W") return { x, y: y + t * NODE_H };
    if (f === "E") return { x: x + NODE_W, y: y + t * NODE_H };
    return nodeCenter(node);
  }

  /** Local (0,0) anchor for labels drawn inside the node group. */
  function openingAnchorLocal(node, openingId, face) {
    const abs = openingAnchor({ ...node, x: 0, y: 0 }, openingId, face);
    return abs;
  }

  function ensurePositions() {
    if (!graph) return;
    let i = 0;
    for (const node of graph.nodes) {
      if (node.x == null || node.y == null) {
        node.x = 80 + (i % 4) * 180;
        node.y = 80 + Math.floor(i / 4) * 140;
        dirtyLocal = true;
      }
      i += 1;
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
    const p1 = openingAnchor(a, edge.from_opening, edge.from_opening?.[0]);
    const p2 = openingAnchor(b, edge.to_opening, edge.to_opening?.[0]);
    return `M ${p1.x} ${p1.y} L ${p2.x} ${p2.y}`;
  }

  function refreshEdges() {
    if (!graph) return;
    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    for (const item of edgePaths) {
      const d = edgePathD(item.edge, byId);
      if (d) {
        for (const path of item.paths) path.setAttribute("d", d);
      }
    }
  }

  function updateNodeVisual(node) {
    const g = nodesById[node.id];
    if (g) g.setAttribute("transform", `translate(${node.x},${node.y})`);
    refreshEdges();
  }

  function render() {
    if (!graph) return;
    ensurePositions();
    clearSvg();

    worldEl = el("g", { id: "world" });
    applyWorldTransform();
    svg.appendChild(worldEl);

    const page = graph.page || {};
    const representation =
      representationSelect.value || page.representation || "line";
    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));

    const edgesG = el("g", { class: "edges" });
    const nodesG = el("g", { class: "nodes" });
    worldEl.appendChild(edgesG);
    worldEl.appendChild(nodesG);

    for (const edge of graph.edges) {
      const d = edgePathD(edge, byId);
      if (!d) continue;
      const paths = [];
      if (representation === "tube") {
        const tube = el("path", { class: "edge-tube", d });
        const core = el("path", { class: "edge-tube-core", d });
        edgesG.appendChild(tube);
        edgesG.appendChild(core);
        paths.push(tube, core);
      } else {
        const line = el("path", { class: "edge-line", d });
        edgesG.appendChild(line);
        paths.push(line);
      }
      edgePaths.push({ edge, paths });
    }

    for (const node of graph.nodes) {
      const g = el("g", {
        class: "node",
        "data-id": node.id,
        transform: `translate(${node.x},${node.y})`,
      });
      const box = el("rect", {
        class: "node-box",
        width: NODE_W,
        height: NODE_H,
        rx: 6,
      });
      g.appendChild(box);
      g.appendChild(
        el("text", { class: "node-label", x: 8, y: 18 }, node.label || node.id)
      );
      g.appendChild(
        el("text", { class: "node-type", x: 8, y: 34 }, node.type || "")
      );

      const backs = (node.openings || []).filter((o) => o.face === "B");
      const sides = (node.openings || []).filter(
        (o) => o.face !== "B" && o.face !== "F"
      );
      for (const op of sides) {
        const anchor = openingAnchorLocal(node, op.id, op.face);
        const labelX =
          op.face === "W" ? 4 : op.face === "E" ? NODE_W - 4 : anchor.x;
        const labelY =
          op.face === "N" ? 10 : op.face === "S" ? NODE_H - 3 : anchor.y + 3;
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
            cx: NODE_W / 2,
            cy: NODE_H / 2 + 6,
            r: 7,
          })
        );
        g.appendChild(
          el(
            "text",
            {
              class: "opening-back",
              x: NODE_W / 2,
              y: NODE_H / 2 + 9,
              "text-anchor": "middle",
            },
            backs.map((b) => b.id).join(",")
          )
        );
      }

      box.addEventListener("pointerdown", (ev) => {
        if (ev.button !== 0) return;
        ev.preventDefault();
        ev.stopPropagation();
        const gEl = nodesById[node.id];
        if (gEl && gEl.parentNode) {
          gEl.parentNode.appendChild(gEl);
        }
        box.classList.add("selected");
        svg.classList.add("dragging");
        svg.setPointerCapture(ev.pointerId);
        drag = {
          id: node.id,
          pointerId: ev.pointerId,
          startClientX: ev.clientX,
          startClientY: ev.clientY,
          origX: node.x,
          origY: node.y,
        };
      });

      nodesG.appendChild(g);
      nodesById[node.id] = g;
    }
  }

  async function endDrag(ev) {
    if (!drag) return;
    if (ev && drag.pointerId != null && ev.pointerId !== drag.pointerId) return;
    const node = graph?.nodes.find((n) => n.id === drag.id);
    const g = nodesById[drag.id];
    const box = g?.querySelector(".node-box");
    if (box) box.classList.remove("selected");
    svg.classList.remove("dragging");
    try {
      if (drag.pointerId != null && svg.hasPointerCapture?.(drag.pointerId)) {
        svg.releasePointerCapture(drag.pointerId);
      }
    } catch {
      /* ignore */
    }
    const finished = drag;
    drag = null;
    if (!node || !locationId) return;
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
    for (const loc of data.locations || []) {
      const opt = document.createElement("option");
      opt.value = loc.id;
      opt.textContent =
        (loc.label || loc.id) + (loc.type ? ` (${loc.type})` : "");
      locationSelect.appendChild(opt);
    }
    if ((data.locations || []).length) {
      locationId = data.locations[0].id;
      locationSelect.value = locationId;
      await loadLocation();
    } else {
      setStatus("No locations with children found");
    }
  }

  async function loadLocation() {
    locationId = locationSelect.value;
    graph = await api(
      `/api/physical?location=${encodeURIComponent(locationId)}`
    );
    representationSelect.value = graph.page?.representation || "line";
    render();
    await refreshStatus();
  }

  locationSelect.addEventListener("change", () => {
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
        body: JSON.stringify({ location_id: locationId, force: false }),
      });
      graph = data.graph;
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
        body: JSON.stringify({ location_id: locationId, force: true }),
      });
      graph = data.graph;
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
      const factor = ev.deltaY > 0 ? 1 / 1.08 : 1.08;
      scale = Math.min(3, Math.max(0.35, scale * factor));
      applyWorldTransform();
    },
    { passive: false }
  );

  loadLocations().catch((err) => setStatus(String(err.message || err)));
})();
