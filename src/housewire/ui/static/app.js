(() => {
  const svg = document.getElementById("canvas");
  const floorSelect = document.getElementById("floor-select");
  const representationSelect = document.getElementById("representation");
  const statusEl = document.getElementById("status");
  const viewport = document.getElementById("viewport");

  const NODE_W = 120;
  const NODE_H = 56;

  let graph = null;
  let floorId = null;
  let scale = 1;
  let panX = 40;
  let panY = 40;
  let dirtyLocal = false;
  let drag = null;
  let panDrag = null;
  let saveTimer = null;

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

  function openingAnchor(node, openingId, face) {
    const x = node.x ?? 0;
    const y = node.y ?? 0;
    const f = (face || (openingId || "?")[0] || "?").toUpperCase();
    if (f === "B" || f === "F") {
      return nodeCenter(node);
    }
    if (f === "N") return { x: x + NODE_W / 2, y };
    if (f === "S") return { x: x + NODE_W / 2, y: y + NODE_H };
    if (f === "W") return { x, y: y + NODE_H / 2 };
    if (f === "E") return { x: x + NODE_W, y: y + NODE_H / 2 };
    return nodeCenter(node);
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

  function render() {
    if (!graph) return;
    ensurePositions();
    clearSvg();

    const world = el("g", {
      id: "world",
      transform: `translate(${panX},${panY}) scale(${scale})`,
    });
    svg.appendChild(world);

    const page = graph.page || {};
    const representation = representationSelect.value || page.representation || "line";
    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));

    const edgesG = el("g", { class: "edges" });
    const nodesG = el("g", { class: "nodes" });
    world.appendChild(edgesG);
    world.appendChild(nodesG);

    for (const edge of graph.edges) {
      const a = byId[edge.from];
      const b = byId[edge.to];
      if (!a || !b) continue;
      const p1 = openingAnchor(a, edge.from_opening, edge.from_opening?.[0]);
      const p2 = openingAnchor(b, edge.to_opening, edge.to_opening?.[0]);
      const d = `M ${p1.x} ${p1.y} L ${p2.x} ${p2.y}`;
      if (representation === "tube") {
        edgesG.appendChild(el("path", { class: "edge-tube", d }));
        edgesG.appendChild(el("path", { class: "edge-tube-core", d }));
      } else {
        edgesG.appendChild(el("path", { class: "edge-line", d }));
      }
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
      const sides = (node.openings || []).filter((o) => o.face !== "B" && o.face !== "F");
      for (const op of sides) {
        const anchor = openingAnchor(
          { x: 0, y: 0 },
          op.id,
          op.face
        );
        g.appendChild(
          el(
            "text",
            {
              class: "opening-side",
              x: Math.min(NODE_W - 4, Math.max(4, anchor.x)),
              y: Math.min(NODE_H - 4, Math.max(10, anchor.y + 3)),
              "text-anchor": "middle",
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
        ev.stopPropagation();
        box.setPointerCapture(ev.pointerId);
        drag = {
          id: node.id,
          startClientX: ev.clientX,
          startClientY: ev.clientY,
          origX: node.x,
          origY: node.y,
        };
        box.classList.add("selected");
      });
      box.addEventListener("pointermove", (ev) => {
        if (!drag || drag.id !== node.id) return;
        const dx = (ev.clientX - drag.startClientX) / scale;
        const dy = (ev.clientY - drag.startClientY) / scale;
        node.x = Math.round(drag.origX + dx);
        node.y = Math.round(drag.origY + dy);
        dirtyLocal = true;
        render();
      });
      box.addEventListener("pointerup", async () => {
        if (!drag || drag.id !== node.id) return;
        box.classList.remove("selected");
        const moved = { x: node.x, y: node.y };
        drag = null;
        try {
          await api(`/api/physical/positions`, {
            method: "PATCH",
            body: JSON.stringify({
              floor_id: floorId,
              positions: { [node.id]: moved },
            }),
          });
          setStatus(`Moved ${node.id} · unsaved`);
          scheduleStatusRefresh();
        } catch (err) {
          setStatus(String(err.message || err));
        }
      });

      nodesG.appendChild(g);
    }
  }

  function scheduleStatusRefresh() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(refreshStatus, 400);
  }

  async function refreshStatus() {
    try {
      const st = await api("/api/status");
      const n = (st.dirty || []).length;
      setStatus(n ? `${n} dirty file(s)` : dirtyLocal ? "layout pending" : "saved");
      if (!n) dirtyLocal = false;
    } catch {
      /* ignore */
    }
  }

  async function loadFloors() {
    const data = await api("/api/floors");
    floorSelect.innerHTML = "";
    for (const floor of data.floors || []) {
      const opt = document.createElement("option");
      opt.value = floor.id;
      opt.textContent = floor.label || floor.id;
      floorSelect.appendChild(opt);
    }
    if ((data.floors || []).length) {
      floorId = data.floors[0].id;
      floorSelect.value = floorId;
      await loadFloor();
    } else {
      setStatus("No Floor places found");
    }
  }

  async function loadFloor() {
    floorId = floorSelect.value;
    graph = await api(`/api/physical?floor=${encodeURIComponent(floorId)}`);
    representationSelect.value = graph.page?.representation || "line";
    render();
    await refreshStatus();
  }

  floorSelect.addEventListener("change", () => {
    loadFloor().catch((err) => setStatus(String(err.message || err)));
  });

  representationSelect.addEventListener("change", async () => {
    const value = representationSelect.value;
    render();
    if (!floorId) return;
    try {
      await api(`/api/physical/page`, {
        method: "PATCH",
        body: JSON.stringify({ floor_id: floorId, representation: value }),
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
        body: JSON.stringify({ floor_id: floorId, force: false }),
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
        body: JSON.stringify({ floor_id: floorId, force: true }),
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
    render();
  });
  document.getElementById("btn-zoom-out").addEventListener("click", () => {
    scale = Math.max(0.35, scale / 1.15);
    render();
  });
  document.getElementById("btn-zoom-reset").addEventListener("click", () => {
    scale = 1;
    panX = 40;
    panY = 40;
    render();
  });

  viewport.addEventListener("pointerdown", (ev) => {
    if (ev.target !== svg && ev.target !== viewport) return;
    panDrag = { x: ev.clientX, y: ev.clientY, panX, panY };
    viewport.classList.add("panning");
  });
  viewport.addEventListener("pointermove", (ev) => {
    if (!panDrag) return;
    panX = panDrag.panX + (ev.clientX - panDrag.x);
    panY = panDrag.panY + (ev.clientY - panDrag.y);
    render();
  });
  viewport.addEventListener("pointerup", () => {
    panDrag = null;
    viewport.classList.remove("panning");
  });
  viewport.addEventListener(
    "wheel",
    (ev) => {
      ev.preventDefault();
      const factor = ev.deltaY > 0 ? 1 / 1.08 : 1.08;
      scale = Math.min(3, Math.max(0.35, scale * factor));
      render();
    },
    { passive: false }
  );

  loadFloors().catch((err) => setStatus(String(err.message || err)));
})();
