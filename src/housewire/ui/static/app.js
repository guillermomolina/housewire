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
  let selectedId = null;
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
  const DRAG_THRESHOLD = 4;

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
      const g = el("g", {
        class: "node",
        "data-id": node.id,
        transform: `translate(${node.x},${node.y})`,
      });
      const box = el("rect", {
        class: "node-box" + (selectedId === node.id ? " selected" : ""),
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
        svg.setPointerCapture(ev.pointerId);
        drag = {
          id: node.id,
          pointerId: ev.pointerId,
          startClientX: ev.clientX,
          startClientY: ev.clientY,
          origX: node.x,
          origY: node.y,
          moved: false,
        };
      });

      nodesG.appendChild(g);
      nodesById[node.id] = g;
    }
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

  async function endDrag(ev) {
    if (!drag) return;
    if (ev && drag.pointerId != null && ev.pointerId !== drag.pointerId) return;
    const node = graph?.nodes.find((n) => n.id === drag.id);
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
    if (!finished.moved) {
      await selectNode(finished.id);
      return;
    }
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
    selectedId = null;
    document.getElementById("panel-empty").classList.remove("hidden");
    document.getElementById("panel-show").classList.add("hidden");
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
    const body = { location_id: locationId, ...data };
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
