(() => {
  const svg = document.getElementById("canvas");
  const representationSelect = document.getElementById("representation");
  const depthLabel = document.getElementById("depth-label");
  const statusEl = document.getElementById("status");
  const viewport = document.getElementById("viewport");

  const LEAF_W = 120;
  const LEAF_H = 56;
  const LEAF_W_MAX = 260;
  const PAD = 28;
  const HEADER = 36;
  const LABEL_CHAR_W = 6.6;

  let graph = null;
  let locationId = null;
  let selectedId = null;
  let selectedIds = new Set();
  let depthLevel = 1;
  let maxDepth = 1;
  let scale = 1;
  let panX = 40;
  let panY = 40;
  let dirtyLocal = false;
  let drag = null;
  let panDrag = null;
  let marquee = null;
  let spacePan = false;
  let saveTimer = null;
  let worldEl = null;
  let nodesById = {};
  let elementsById = {};
  let edgePaths = [];
  let cablePaths = [];
  let lastTap = { id: null, t: 0 };
  let layoutHistory = [];
  let layoutIndex = -1;
  let layoutBaseline = null;
  let showElements = false;
  let showCables = false;
  let outlineNodes = [];
  let canvasLocations = [];
  let collapsedOutline = new Set();
  let outlineCollapseReady = false;
  const HISTORY_MAX = 50;
  const DRAG_THRESHOLD = 4;
  const DBLCLICK_MS = 400;
  const ELEM_W = 72;
  const ELEM_H = 28;

  function loadCollapsedOutline() {
    try {
      const raw = sessionStorage.getItem("housewire-outline-collapsed-v2");
      if (raw == null) return null; // signal: apply first-level default
      const arr = JSON.parse(raw);
      return new Set(Array.isArray(arr) ? arr : []);
    } catch {
      return null;
    }
  }

  function saveCollapsedOutline() {
    try {
      sessionStorage.setItem(
        "housewire-outline-collapsed-v2",
        JSON.stringify([...collapsedOutline])
      );
    } catch {
      /* ignore */
    }
  }

  function defaultCollapsedOutline(nodes) {
    // Open only the first level: collapse every place deeper than the root.
    const set = new Set();
    const list = nodes || [];
    for (const n of list) {
      if (n.kind !== "place" || (n.depth || 0) < 1) continue;
      const hasKid = list.some((c) => {
        if (outlineParentId(c) !== n.id) return false;
        if (c.kind === "element" && !showElements) return false;
        return true;
      });
      if (hasKid) set.add(n.id);
    }
    return set;
  }

  function ensureOutlineCollapse(nodes) {
    if (outlineCollapseReady) return;
    const stored = loadCollapsedOutline();
    collapsedOutline =
      stored == null ? defaultCollapsedOutline(nodes) : stored;
    outlineCollapseReady = true;
    saveCollapsedOutline();
  }

  function faClass(icon) {
    const raw = String(icon || "fa-circle").trim() || "fa-circle";
    if (raw.includes(" ")) return raw;
    return `fa-solid ${raw}`;
  }

  const ns = "http://www.w3.org/2000/svg";

  function setStatus(text) {
    statusEl.textContent = text || "";
  }

  function snapshotPositions() {
    const places = {};
    for (const n of graph?.nodes || []) {
      places[n.id] = { x: n.x ?? 0, y: n.y ?? 0 };
    }
    const elements = {};
    for (const e of graph?.elements || []) {
      elements[e.id] = { x: e.x ?? 0, y: e.y ?? 0 };
    }
    return { places, elements };
  }

  function cloneSnap(snap) {
    return JSON.parse(JSON.stringify(snap || { places: {}, elements: {} }));
  }

  function xyMapEqual(a, b) {
    const ka = Object.keys(a || {}).sort();
    const kb = Object.keys(b || {}).sort();
    if (ka.length !== kb.length) return false;
    for (let i = 0; i < ka.length; i++) {
      if (ka[i] !== kb[i]) return false;
      const pa = a[ka[i]];
      const pb = b[kb[i]];
      if ((pa?.x ?? 0) !== (pb?.x ?? 0) || (pa?.y ?? 0) !== (pb?.y ?? 0)) {
        return false;
      }
    }
    return true;
  }

  function snapsEqual(a, b) {
    if (!a || !b) return false;
    // Legacy flat snaps (places only) from older sessions — not used after load.
    if (!a.places && !a.elements) {
      return xyMapEqual(a, b.places || b);
    }
    return (
      xyMapEqual(a.places, b.places) && xyMapEqual(a.elements, b.elements)
    );
  }

  function updateHistoryButtons() {
    const undo = document.getElementById("btn-undo");
    const redo = document.getElementById("btn-redo");
    const reset = document.getElementById("btn-layout-reset");
    if (undo) undo.disabled = layoutIndex <= 0;
    if (redo) redo.disabled = layoutIndex < 0 || layoutIndex >= layoutHistory.length - 1;
    if (reset) {
      reset.disabled =
        !layoutBaseline ||
        snapsEqual(snapshotPositions(), layoutBaseline);
    }
  }

  function resetLayoutHistory() {
    layoutBaseline = snapshotPositions();
    layoutHistory = [cloneSnap(layoutBaseline)];
    layoutIndex = 0;
    syncLayoutDirty();
    updateHistoryButtons();
  }

  /** Update Reset target only; leave undo/redo stack intact. */
  function markLayoutBaseline() {
    layoutBaseline = cloneSnap(snapshotPositions());
    syncLayoutDirty();
    updateHistoryButtons();
  }

  function syncLayoutDirty() {
    dirtyLocal = Boolean(
      layoutBaseline && !snapsEqual(snapshotPositions(), layoutBaseline)
    );
  }

  function pushLayoutHistory() {
    const snap = snapshotPositions();
    if (layoutIndex >= 0 && snapsEqual(snap, layoutHistory[layoutIndex])) {
      updateHistoryButtons();
      return;
    }
    layoutHistory = layoutHistory.slice(0, layoutIndex + 1);
    layoutHistory.push(cloneSnap(snap));
    if (layoutHistory.length > HISTORY_MAX) {
      layoutHistory.shift();
    }
    layoutIndex = layoutHistory.length - 1;
    updateHistoryButtons();
  }

  async function persistSnapshot(snap) {
    if (!locationId || !snap) return;
    const places = snap.places || {};
    const elements = snap.elements || {};
    if (Object.keys(places).length) {
      await api(`/api/physical/positions`, {
        method: "PATCH",
        body: JSON.stringify({ location_id: locationId, positions: places }),
      });
    }
    if (Object.keys(elements).length) {
      await api(`/api/electrical/positions`, {
        method: "PATCH",
        body: JSON.stringify({ location_id: locationId, positions: elements }),
      });
    }
    syncLayoutDirty();
    updateSaveButton(dirtyLocal);
    scheduleStatusRefresh();
  }

  async function applyLayoutSnapshot(snap, status) {
    if (!graph || !snap) return;
    const places = snap.places || snap;
    const elements = snap.elements || {};
    for (const n of graph.nodes || []) {
      const p = places[n.id];
      if (!p) continue;
      n.x = p.x;
      n.y = p.y;
    }
    for (const e of graph.elements || []) {
      const p = elements[e.id];
      if (!p) continue;
      e.x = p.x;
      e.y = p.y;
    }
    updateNodeVisual(graph.nodes[0] || null);
    try {
      await persistSnapshot({ places, elements });
      setStatus(
        dirtyLocal ? status || "layout" : status ? `${status} · saved` : "saved"
      );
    } catch (err) {
      setStatus(String(err.message || err));
    }
    updateHistoryButtons();
  }

  async function undoLayout() {
    if (layoutIndex <= 0) return;
    layoutIndex -= 1;
    await applyLayoutSnapshot(layoutHistory[layoutIndex], "undo layout");
  }

  async function redoLayout() {
    if (layoutIndex >= layoutHistory.length - 1) return;
    layoutIndex += 1;
    await applyLayoutSnapshot(layoutHistory[layoutIndex], "redo layout");
  }

  async function resetLayout() {
    if (!layoutBaseline) return;
    layoutHistory = [cloneSnap(layoutBaseline)];
    layoutIndex = 0;
    await applyLayoutSnapshot(layoutBaseline, "reset layout");
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

  function childrenOf(parentId) {
    const key = parentId || null;
    return (graph?.nodes || []).filter((n) => (n.parent || null) === key);
  }

  function isModClick(ev) {
    return !!(ev && (ev.ctrlKey || ev.metaKey));
  }

  function clearSelectionState() {
    selectedIds.clear();
    selectedId = null;
  }

  function setSelectedVisual() {
    for (const [nid, g] of Object.entries(nodesById)) {
      const box = g.querySelector(".node-box");
      if (!box) continue;
      box.classList.toggle("selected", selectedIds.has(nid));
    }
    for (const [eid, g] of Object.entries(elementsById)) {
      const box = g.querySelector(".element-box");
      if (!box) continue;
      box.classList.toggle("selected", selectedIds.has(eid));
    }
  }

  function toggleSelectionId(id) {
    if (selectedIds.has(id)) {
      selectedIds.delete(id);
      if (selectedId === id) {
        selectedId = [...selectedIds].slice(-1)[0] ?? null;
      }
    } else {
      selectedIds.add(id);
      selectedId = id;
    }
    setSelectedVisual();
  }

  function replaceSelection(id) {
    selectedIds = id == null ? new Set() : new Set([id]);
    selectedId = id;
    setSelectedVisual();
  }

  function clientToWorld(clientX, clientY) {
    const rect = viewport.getBoundingClientRect();
    return {
      x: (clientX - rect.left - panX) / scale,
      y: (clientY - rect.top - panY) / scale,
    };
  }

  function rectsIntersect(a, b) {
    return !(a.x2 < b.x1 || a.x1 > b.x2 || a.y2 < b.y1 || a.y1 > b.y2);
  }

  function placeWorldRect(node, byId) {
    const a = absXY(node, byId);
    return {
      x1: a.x,
      y1: a.y,
      x2: a.x + nodeW(node),
      y2: a.y + nodeH(node),
    };
  }

  function elementWorldRect(elem, byId) {
    const a = elementAbsXY(elem, byId);
    const w = elem.w ?? ELEM_W;
    const h = elem.h ?? ELEM_H;
    return { x1: a.x, y1: a.y, x2: a.x + w, y2: a.y + h };
  }

  function selectionHasAncestorPlace(placeId, placeIds) {
    const byId = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
    let cur = byId[placeId];
    while (cur?.parent) {
      if (placeIds.has(cur.parent)) return true;
      cur = byId[cur.parent];
    }
    return false;
  }

  function buildDragItems() {
    const placeIds = new Set();
    const elemIds = new Set();
    for (const id of selectedIds) {
      if ((graph?.nodes || []).some((n) => n.id === id)) placeIds.add(id);
      else if ((graph?.elements || []).some((e) => e.id === id)) elemIds.add(id);
    }
    const items = [];
    for (const id of placeIds) {
      if (selectionHasAncestorPlace(id, placeIds)) continue;
      const node = graph.nodes.find((n) => n.id === id);
      if (!node) continue;
      items.push({
        kind: "place",
        id,
        origX: node.x ?? 0,
        origY: node.y ?? 0,
      });
    }
    for (const id of elemIds) {
      const elem = (graph.elements || []).find((e) => e.id === id);
      if (!elem) continue;
      if (
        elem.parent &&
        (placeIds.has(elem.parent) ||
          selectionHasAncestorPlace(elem.parent, placeIds))
      ) {
        continue;
      }
      items.push({
        kind: "element",
        id,
        origX: elem.x ?? 0,
        origY: elem.y ?? 0,
      });
    }
    return items;
  }

  function marqueeEl() {
    return document.getElementById("marquee");
  }

  function hideMarquee() {
    const box = marqueeEl();
    if (box) box.classList.add("hidden");
    viewport.classList.remove("marqueeing");
  }

  function updateMarqueeDom(x0, y0, x1, y1) {
    const box = marqueeEl();
    if (!box) return;
    const left = Math.min(x0, x1);
    const top = Math.min(y0, y1);
    const w = Math.abs(x1 - x0);
    const h = Math.abs(y1 - y0);
    box.classList.remove("hidden");
    box.style.left = `${left}px`;
    box.style.top = `${top}px`;
    box.style.width = `${w}px`;
    box.style.height = `${h}px`;
  }

  function idsInMarqueeWorld(worldRect, additive) {
    const byId = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
    const hit = additive ? new Set(selectedIds) : new Set();
    for (const node of graph?.nodes || []) {
      if (!nodesById[node.id]) continue;
      if (rectsIntersect(placeWorldRect(node, byId), worldRect)) {
        hit.add(node.id);
      }
    }
    if (showElements) {
      for (const elem of graph?.elements || []) {
        if (!elementsById[elem.id]) continue;
        if (rectsIntersect(elementWorldRect(elem, byId), worldRect)) {
          hit.add(elem.id);
        }
      }
    }
    return hit;
  }

  function idMap(byId) {
    return (
      byId || Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]))
    );
  }

  function nodeW(node) {
    return node.w || LEAF_W;
  }

  function nodeH(node) {
    return node.h || LEAF_H;
  }

  function leafWidthForLabel(label) {
    const text = String(label || "?").trim() || "?";
    return Math.max(LEAF_W, Math.min(LEAF_W_MAX, 16 + text.length * LABEL_CHAR_W));
  }

  function fitLabel(text, boxW) {
    const raw = String(text || "");
    const maxChars = Math.max(4, Math.floor((boxW - 16) / LABEL_CHAR_W));
    if (raw.length <= maxChars) return raw;
    return `${raw.slice(0, Math.max(1, maxChars - 1))}…`;
  }

  /** Recompute window sizes bottom-up from visible children and elements. */
  function measureVisibleSizes() {
    if (!graph) return;
    const elemsByParent = {};
    for (const e of graph.elements || []) {
      const key = e.parent || "";
      (elemsByParent[key] ||= []).push(e);
    }
    function measure(node) {
      const kids = childrenOf(node.id);
      const elems = elemsByParent[node.id] || [];
      for (const kid of kids) measure(kid);
      if (!kids.length && !elems.length) {
        // Keep server size when no visible interior (depth / empty leaf).
        if (node.w == null) {
          node.w = leafWidthForLabel(node.display_name || node.name || node.id);
        }
        if (node.h == null) node.h = LEAF_H;
        return;
      }
      let maxR = 0;
      let maxB = 0;
      for (const kid of kids) {
        maxR = Math.max(maxR, (kid.x ?? 0) + nodeW(kid));
        maxB = Math.max(maxB, (kid.y ?? 0) + nodeH(kid));
      }
      // Elements always contribute (same idea as nested places beyond depth).
      for (const e of elems) {
        maxR = Math.max(maxR, (e.x ?? 0) + (e.w ?? ELEM_W));
        maxB = Math.max(maxB, (e.y ?? 0) + (e.h ?? ELEM_H));
      }
      node.w = Math.max(LEAF_W, maxR + 2 * PAD);
      node.h = Math.max(LEAF_H, HEADER + maxB + PAD);
    }
    for (const node of childrenOf(null)) measure(node);
  }

  function absXY(node, byId) {
    const map = idMap(byId);
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
    cablePaths = [];
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
      return;
    }
    const sx = (viewW - pad * 2) / bounds.w;
    const sy = (viewH - pad * 2) / bounds.h;
    scale = Math.min(3, Math.max(0.05, Math.min(sx, sy)));
    panX = pad - bounds.minX * scale + (viewW - pad * 2 - bounds.w * scale) / 2;
    panY = pad - bounds.minY * scale + (viewH - pad * 2 - bounds.h * scale) / 2;
    applyWorldTransform();
  }

  function orthoPathD(p1, p2, fromFace, toFace) {
    const x1 = p1.x;
    const y1 = p1.y;
    const x2 = p2.x;
    const y2 = p2.y;
    if (x1 === x2 && y1 === y2) {
      return `M ${x1} ${y1}`;
    }
    if (x1 === x2 || y1 === y2) {
      return `M ${x1} ${y1} L ${x2} ${y2}`;
    }
    const STUB = 20;
    const parts = [`M ${x1} ${y1}`];
    let ax = x1;
    let ay = y1;
    let bx = x2;
    let by = y2;
    if (fromFace === "E") {
      ax = x1 + STUB;
      parts.push(`L ${ax} ${ay}`);
    } else if (fromFace === "W") {
      ax = x1 - STUB;
      parts.push(`L ${ax} ${ay}`);
    } else if (fromFace === "S") {
      ay = y1 + STUB;
      parts.push(`L ${ax} ${ay}`);
    } else if (fromFace === "N") {
      ay = y1 - STUB;
      parts.push(`L ${ax} ${ay}`);
    }
    if (toFace === "E") bx = x2 + STUB;
    else if (toFace === "W") bx = x2 - STUB;
    else if (toFace === "S") by = y2 + STUB;
    else if (toFace === "N") by = y2 - STUB;

    // S / Z: two elbows through a mid line (not a single L corner).
    let horizontalBridge;
    if (fromFace === "E" || fromFace === "W") horizontalBridge = true;
    else if (fromFace === "N" || fromFace === "S") horizontalBridge = false;
    else if (toFace === "E" || toFace === "W") horizontalBridge = true;
    else if (toFace === "N" || toFace === "S") horizontalBridge = false;
    else horizontalBridge = Math.abs(bx - ax) >= Math.abs(by - ay);

    if (ax === bx || ay === by) {
      parts.push(`L ${bx} ${by}`);
    } else if (horizontalBridge) {
      const mx = (ax + bx) / 2;
      parts.push(`L ${mx} ${ay}`, `L ${mx} ${by}`, `L ${bx} ${by}`);
    } else {
      const my = (ay + by) / 2;
      parts.push(`L ${ax} ${my}`, `L ${bx} ${my}`, `L ${bx} ${by}`);
    }
    if (bx !== x2 || by !== y2) {
      parts.push(`L ${x2} ${y2}`);
    }
    return parts.join(" ");
  }

  function edgePathD(edge, byId) {
    const a = byId[edge.from];
    const b = byId[edge.to];
    if (!a || !b) return null;
    const fromFace = edge.from_opening?.[0];
    const toFace = edge.to_opening?.[0];
    const p1 = openingAnchorAbs(a, edge.from_opening, fromFace, byId);
    const p2 = openingAnchorAbs(b, edge.to_opening, toFace, byId);
    return orthoPathD(p1, p2, fromFace, toFace);
  }

  function elementAbsXY(elem, placeById) {
    if (!elem.parent) return { x: elem.x ?? 0, y: elem.y ?? 0 };
    const parent = placeById[elem.parent];
    if (!parent) return { x: elem.x ?? 0, y: elem.y ?? 0 };
    const a = absXY(parent, placeById);
    // Same content origin as nested locations (PAD / HEADER).
    return {
      x: a.x + PAD + (elem.x ?? 0),
      y: a.y + HEADER + (elem.y ?? 0),
    };
  }

  function elementCenter(elem, placeById) {
    const p = elementAbsXY(elem, placeById);
    return {
      x: p.x + (elem.w ?? ELEM_W) / 2,
      y: p.y + (elem.h ?? ELEM_H) / 2,
    };
  }

  function appendOrtho(d, p1, p2, fromFace, toFace) {
    const seg = orthoPathD(p1, p2, fromFace, toFace);
    if (!d) return seg;
    // Drop leading M; continue with L segments.
    return d + seg.replace(/^M\s+[-\d.]+(?:\s+|,)[-\d.]+\s*/, " ");
  }

  function cablePathD(edge, placeById, elemById) {
    const a = elemById[edge.from];
    const b = elemById[edge.to];
    if (!a || !b) return null;
    const c1 = elementCenter(a, placeById);
    const c2 = elementCenter(b, placeById);
    const conduitFrom = edge.conduit_from
      ? placeById[edge.conduit_from]
      : null;
    const conduitTo = edge.conduit_to ? placeById[edge.conduit_to] : null;
    if (
      edge.conduit &&
      conduitFrom &&
      conduitTo &&
      edge.from_opening &&
      edge.to_opening
    ) {
      const fromFace = edge.from_opening?.[0];
      const toFace = edge.to_opening?.[0];
      const op1 = openingAnchorAbs(
        conduitFrom,
        edge.from_opening,
        fromFace,
        placeById
      );
      const op2 = openingAnchorAbs(
        conduitTo,
        edge.to_opening,
        toFace,
        placeById
      );
      // Element → opening → along conduit (S) → opening → element.
      let d = appendOrtho("", c1, op1, null, fromFace);
      d = appendOrtho(d, op1, op2, fromFace, toFace);
      d = appendOrtho(d, op2, c2, toFace, null);
      return d;
    }
    return orthoPathD(c1, c2, null, null);
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
    const elemById = Object.fromEntries(
      (graph.elements || []).map((e) => [e.id, e])
    );
    for (const item of cablePaths) {
      const d = cablePathD(item.edge, byId, elemById);
      if (d) {
        for (const path of item.paths) path.setAttribute("d", d);
      }
    }
  }

  function updateElementVisual(elem, placeById) {
    const g = elementsById[elem.id];
    if (!g) return;
    const a = elementAbsXY(elem, placeById);
    g.setAttribute("transform", `translate(${a.x},${a.y})`);
  }

  function updateNodeVisual(_node) {
    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    measureVisibleSizes();
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
    for (const e of graph.elements || []) {
      updateElementVisual(e, byId);
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
        (selectedIds.has(node.id) ? " selected" : "") +
        (hasKids ? " container" : "") +
        (node.expandable ? " expandable" : ""),
      width: w,
      height: h,
      rx: 6,
    });
    g.appendChild(box);
    const fullLabel = node.display_label || node.label || node.display_name || node.name || node.id;
    const canvasName = node.display_name || node.name || node.id;
    const typeText =
      (node.type || "") + (node.expandable ? " · +" : "");
    g.appendChild(el("title", null, fullLabel));
    g.appendChild(
      el(
        "text",
        { class: "node-label", x: 8, y: 18 },
        fitLabel(canvasName, w)
      )
    );
    g.appendChild(
      el(
        "text",
        { class: "node-type", x: 8, y: 34 },
        fitLabel(typeText, w)
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
      if (isModClick(ev)) {
        toggleSelectionId(node.id);
      } else if (!selectedIds.has(node.id)) {
        replaceSelection(node.id);
      }
      if (!selectedIds.has(node.id)) {
        drag = null;
        syncInspectorFromSelection();
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
        moved: false,
        captured: false,
        modClick: isModClick(ev),
      };
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
      (elem.display_label || elem.label || elem.name || elem.id) +
      (elem.type ? ` · ${elem.type}` : "");
    g.appendChild(el("title", null, title));
    g.appendChild(
      el(
        "text",
        { class: "element-label", x: 4, y: 12 },
        fitLabel(elem.name || elem.id, w - 4)
      )
    );
    g.appendChild(
      el(
        "text",
        { class: "element-type", x: 4, y: 22 },
        fitLabel(elem.type || "", w - 4)
      )
    );
    box.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      ev.stopPropagation();
      const gEl = elementsById[elem.id];
      if (gEl && gEl.parentNode) gEl.parentNode.appendChild(gEl);
      if (isModClick(ev)) {
        toggleSelectionId(elem.id);
      } else if (!selectedIds.has(elem.id)) {
        replaceSelection(elem.id);
      }
      if (!selectedIds.has(elem.id)) {
        drag = null;
        syncInspectorFromSelection();
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
        moved: false,
        captured: false,
        modClick: isModClick(ev),
      };
    });
    layerG.appendChild(g);
    elementsById[elem.id] = g;
  }

  function raiseNode(id) {
    const gEl = nodesById[id];
    if (gEl && gEl.parentNode) gEl.parentNode.appendChild(gEl);
    for (const kid of childrenOf(id)) raiseNode(kid.id);
  }

  function render() {
    if (!graph) return;
    ensurePositions();
    measureVisibleSizes();
    clearSvg();

    worldEl = el("g", { id: "world" });
    applyWorldTransform();
    svg.appendChild(worldEl);

    const page = graph.page || {};
    const representation =
      representationSelect.value || page.representation || "line";
    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    const elemById = Object.fromEntries(
      (graph.elements || []).map((e) => [e.id, e])
    );

    // Containers under conduits under leaves; cables then elements on top.
    const containersG = el("g", { class: "containers" });
    const edgesG = el("g", { class: "edges" });
    const leavesG = el("g", { class: "leaves" });
    const cablesG = el("g", { class: "cables" });
    const elementsG = el("g", { class: "elements" });
    worldEl.appendChild(containersG);
    worldEl.appendChild(edgesG);
    worldEl.appendChild(leavesG);
    worldEl.appendChild(cablesG);
    worldEl.appendChild(elementsG);

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

    if (showCables) {
      for (const edge of graph.cable_edges || []) {
        const d = cablePathD(edge, byId, elemById);
        if (!d) continue;
        const colors = (edge.colors || []).join(",");
        const title = colors
          ? `${edge.id} (${colors})`
          : String(edge.id || edge.via || "");
        const line = el("path", { class: "cable-edge", d });
        line.appendChild(el("title", null, title));
        cablesG.appendChild(line);
        cablePaths.push({ edge, paths: [line] });
      }
    }

    if (showElements) {
      for (const elem of graph.elements || []) {
        if (elem.parent && !byId[elem.parent]) continue;
        // Like depth: interior elements only when the place is a leaf in view.
        if (elem.parent && childrenOf(elem.parent).length) continue;
        paintElement(elem, elementsG, byId);
      }
    }
    updateDepthLabel();
  }

  function selectElement(elem) {
    replaceSelection(elem.id);
    highlightOutline(canvasToSiteId(elem.id));
    fillElementInspector(elem);
  }

  function fillElementInspector(elem) {
    const empty = document.getElementById("panel-empty");
    const show = document.getElementById("panel-show");
    empty.classList.add("hidden");
    show.classList.remove("hidden");
    const meta = document.getElementById("show-meta");
    meta.innerHTML = "";
    const rows = [
      ["id", elem.id],
      ["name", elem.name],
      ["type", elem.type],
      ["subtype", elem.subtype],
      ["label", elem.label],
      ["parent", elem.parent || "(canvas root)"],
      ["terminals", (elem.terminals || []).join(", ")],
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
  }

  function canvasToSiteId(relId) {
    if (!relId) return locationId;
    if (!locationId || locationId === "." || locationId === "") return relId;
    return `${locationId}/${relId}`;
  }

  async function fillPlaceInspector(id) {
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
        ["name", detail.name || detail.display_name],
        ["label", detail.label || detail.display_label],
        ["type", detail.type],
        ["subtype", detail.subtype],
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

  async function selectNode(id) {
    const elem = (graph?.elements || []).find((e) => e.id === id);
    if (elem) {
      selectElement(elem);
      return;
    }
    replaceSelection(id);
    highlightOutline(id ? canvasToSiteId(id) : locationId);
    await fillPlaceInspector(id);
  }

  async function syncInspectorFromSelection() {
    setSelectedVisual();
    if (selectedIds.size === 0) {
      highlightOutline(locationId);
      await fillPlaceInspector(null);
      return;
    }
    if (selectedIds.size > 1) {
      setStatus(`${selectedIds.size} selected`);
    }
    highlightOutline(selectedId ? canvasToSiteId(selectedId) : locationId);
    const elem = (graph?.elements || []).find((e) => e.id === selectedId);
    if (elem) fillElementInspector(elem);
    else await fillPlaceInspector(selectedId);
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
    const opt = canvasLocations.find(
      (r) => r.selectable !== false && r.id === nextId
    );
    if (opt) {
      depthLevel = 1;
      await setCanvasLocation(nextId);
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
    await syncInspectorFromSelection();
    try {
      const placePositions = {};
      const elemPositions = {};
      for (const item of finished.items || []) {
        if (item.kind === "place") {
          const node = graph?.nodes.find((n) => n.id === item.id);
          if (node) placePositions[item.id] = { x: node.x, y: node.y };
        } else if (item.kind === "element") {
          const elem = (graph?.elements || []).find((e) => e.id === item.id);
          if (elem) elemPositions[item.id] = { x: elem.x, y: elem.y };
        }
      }
      if (Object.keys(placePositions).length) {
        await api(`/api/physical/positions`, {
          method: "PATCH",
          body: JSON.stringify({
            location_id: locationId,
            positions: placePositions,
          }),
        });
      }
      if (Object.keys(elemPositions).length) {
        await api(`/api/electrical/positions`, {
          method: "PATCH",
          body: JSON.stringify({
            location_id: locationId,
            positions: elemPositions,
          }),
        });
      }
      if (
        !Object.keys(placePositions).length &&
        !Object.keys(elemPositions).length
      ) {
        return;
      }
      pushLayoutHistory();
      syncLayoutDirty();
      updateSaveButton(dirtyLocal);
      const n =
        Object.keys(placePositions).length + Object.keys(elemPositions).length;
      setStatus(
        dirtyLocal
          ? `Moved ${n} · unsaved`
          : `Moved ${n}`
      );
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
    for (const item of drag.items || []) {
      if (item.kind === "place") {
        const node = graph?.nodes.find((n) => n.id === item.id);
        if (!node) continue;
        node.x = Math.max(0, Math.round(item.origX + dx));
        node.y = Math.max(0, Math.round(item.origY + dy));
      } else if (item.kind === "element") {
        const elem = (graph?.elements || []).find((e) => e.id === item.id);
        if (!elem) continue;
        let nx = Math.max(0, Math.round(item.origX + dx));
        let ny = Math.max(0, Math.round(item.origY + dy));
        if (elem.parent) {
          const parent = graph.nodes.find((n) => n.id === elem.parent);
          if (parent) {
            const innerW = Math.max(ELEM_W, nodeW(parent) - 2 * PAD);
            const innerH = Math.max(ELEM_H, nodeH(parent) - HEADER - PAD);
            nx = Math.min(nx, Math.max(0, innerW - (elem.w ?? ELEM_W)));
            ny = Math.min(ny, Math.max(0, innerH - (elem.h ?? ELEM_H)));
          }
        }
        elem.x = nx;
        elem.y = ny;
      }
    }
    updateNodeVisual(null);
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
    const hit = idsInMarqueeWorld(worldRect, finished.additive);
    selectedIds = hit;
    selectedId = [...hit].slice(-1)[0] ?? null;
    await syncInspectorFromSelection();
  }

  svg.addEventListener("pointermove", (ev) => {
    if (drag) {
      applyMultiDrag(ev);
      return;
    }
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
      panDrag = null;
      viewport.classList.remove("panning");
    }
  });

  svg.addEventListener("pointercancel", (ev) => {
    if (drag) endDrag(ev);
    if (marquee) endMarquee(ev);
    panDrag = null;
    viewport.classList.remove("panning");
    hideMarquee();
  });

  function scheduleStatusRefresh() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(refreshStatus, 400);
  }

  async function refreshStatus() {
    try {
      const st = await api("/api/status");
      const n = (st.dirty || []).length;
      syncLayoutDirty();
      const dirty = n > 0 || dirtyLocal;
      setStatus(
        n ? `${n} dirty file(s)` : dirtyLocal ? "layout pending" : "saved"
      );
      updateSaveButton(dirty);
    } catch {
      /* ignore */
    }
  }

  function updateSaveButton(dirty) {
    const btn = document.getElementById("btn-save");
    if (btn) btn.disabled = !dirty;
  }

  async function fillMissingLayout() {
    if (!locationId) return [];
    const data = await api(`/api/physical/auto-layout`, {
      method: "POST",
      body: JSON.stringify({
        location_id: locationId,
        force: false,
        depth: depthLevel,
      }),
    });
    if (data.graph) {
      graph = data.graph;
      depthLevel = graph.depth || depthLevel;
      maxDepth = graph.max_depth || maxDepth;
    }
    return data.updated || [];
  }

  async function fillMissingElectricalLayout() {
    if (!locationId) return [];
    const data = await api(`/api/electrical/auto-layout`, {
      method: "POST",
      body: JSON.stringify({
        location_id: locationId,
        force: false,
        depth: depthLevel,
      }),
    });
    if (data.graph) {
      graph = data.graph;
      depthLevel = graph.depth || depthLevel;
      maxDepth = graph.max_depth || maxDepth;
    }
    return data.updated || [];
  }

  async function loadLocations() {
    const data = await api("/api/locations");
    canvasLocations = data.locations || [];
    await loadOutline();
    const first =
      canvasLocations.find((r) => r.selectable !== false && r.id === ".") ||
      canvasLocations.find((r) => r.selectable !== false);
    if (first) {
      await setCanvasLocation(first.id);
    } else {
      setStatus("No locations with children found");
    }
  }

  async function setCanvasLocation(id, { resetDepth = true } = {}) {
    if (!id) return;
    if (resetDepth) depthLevel = 1;
    locationId = id;
    await loadLocation();
  }

  async function loadOutline() {
    try {
      const data = await api("/api/outline");
      outlineNodes = data.nodes || [];
      ensureOutlineCollapse(outlineNodes);
      renderOutline();
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }

  function outlineParentId(node) {
    if (node.kind === "element") return node.parent || null;
    if (!node.id || node.id === ".") return null;
    if (!node.id.includes("/")) return ".";
    return node.id.slice(0, node.id.lastIndexOf("/"));
  }

  function outlineHasKids(nodeId) {
    return outlineNodes.some((n) => {
      if (outlineParentId(n) !== nodeId) return false;
      if (n.kind === "element" && !showElements) return false;
      return true;
    });
  }

  function isOutlineHidden(node) {
    let parent = outlineParentId(node);
    while (parent) {
      if (collapsedOutline.has(parent)) return true;
      if (parent === ".") break;
      parent = parent.includes("/")
        ? parent.slice(0, parent.lastIndexOf("/"))
        : ".";
    }
    return false;
  }

  function expandOutlineAncestors(siteId) {
    if (!siteId) return;
    let parent =
      siteId === "."
        ? null
        : siteId.includes("/")
          ? siteId.slice(0, siteId.lastIndexOf("/"))
          : ".";
    while (parent) {
      collapsedOutline.delete(parent);
      if (parent === ".") break;
      parent = parent.includes("/")
        ? parent.slice(0, parent.lastIndexOf("/"))
        : ".";
    }
    saveCollapsedOutline();
  }

  function renderOutline() {
    const host = document.getElementById("outline-tree");
    if (!host) return;
    host.innerHTML = "";
    for (const node of outlineNodes) {
      if (node.kind === "element" && !showElements) continue;
      if (isOutlineHidden(node)) continue;
      const row = document.createElement("div");
      row.className =
        "outline-item" + (node.kind === "element" ? " element" : "");
      row.dataset.kind = node.kind || "place";
      row.dataset.id = node.id;
      if (node.parent) row.dataset.parent = node.parent;
      row.style.paddingLeft = `${0.25 + (node.depth || 0) * 0.75}rem`;
      row.title = [node.type, node.id].filter(Boolean).join(" · ");

      const twist = document.createElement("button");
      twist.type = "button";
      twist.className = "outline-twist";
      const hasKids = node.kind === "place" && outlineHasKids(node.id);
      if (hasKids) {
        const open = !collapsedOutline.has(node.id);
        twist.innerHTML = open
          ? '<i class="fa-solid fa-caret-down"></i>'
          : '<i class="fa-solid fa-caret-right"></i>';
        twist.addEventListener("click", (ev) => {
          ev.stopPropagation();
          if (collapsedOutline.has(node.id)) collapsedOutline.delete(node.id);
          else collapsedOutline.add(node.id);
          saveCollapsedOutline();
          renderOutline();
        });
      } else {
        twist.disabled = true;
        twist.innerHTML = "";
      }
      row.appendChild(twist);

      const icon = document.createElement("i");
      icon.className = `${faClass(node.icon)} outline-icon`;
      icon.setAttribute("aria-hidden", "true");
      row.appendChild(icon);

      const label = document.createElement("span");
      label.className = "outline-label";
      label.textContent =
        node.display_name || node.name || node.label || node.id;
      row.appendChild(label);

      row.addEventListener("click", () => {
        onOutlineClick(node).catch((err) =>
          setStatus(String(err.message || err))
        );
      });
      host.appendChild(row);
    }
    applyOutlineActive(selectedId ? canvasToSiteId(selectedId) : locationId);
  }

  function applyOutlineActive(activeId) {
    const host = document.getElementById("outline-tree");
    if (!host) return;
    for (const btn of host.querySelectorAll(".outline-item")) {
      const id = btn.dataset.id;
      btn.classList.toggle(
        "active",
        id === activeId || (activeId == null && id === locationId)
      );
    }
  }

  function highlightOutline(activeId) {
    if (activeId) {
      const before = collapsedOutline.size;
      expandOutlineAncestors(activeId);
      const needPaint =
        before !== collapsedOutline.size ||
        outlineNodes.some((n) => n.id === activeId && isOutlineHidden(n));
      if (needPaint) {
        renderOutline();
        applyOutlineActive(activeId);
        return;
      }
    }
    applyOutlineActive(activeId);
  }

  function siteToCanvasRelative(siteId) {
    if (!siteId || !locationId) return null;
    if (siteId === locationId) return null;
    if (locationId === "." || locationId === "") {
      return siteId === "." ? null : siteId;
    }
    const prefix = `${locationId}/`;
    if (siteId.startsWith(prefix)) return siteId.slice(prefix.length);
    return null;
  }

  function nearestSelectableAncestor(placeId) {
    const places = outlineNodes.filter((n) => n.kind === "place");
    const byId = Object.fromEntries(places.map((p) => [p.id, p]));
    let cur = placeId;
    while (cur) {
      const row = byId[cur];
      if (row?.selectable) return cur;
      if (cur === "." || !cur.includes("/")) {
        const root = byId["."];
        return root?.selectable ? "." : null;
      }
      const parent = cur.includes("/")
        ? cur.slice(0, cur.lastIndexOf("/"))
        : ".";
      cur = parent;
    }
    return null;
  }

  function placeDepthUnderCanvas(placeSiteId, canvasId) {
    if (!placeSiteId || placeSiteId === canvasId) return 1;
    const prefix =
      canvasId === "." || canvasId === "" ? "" : `${canvasId}/`;
    const rel =
      canvasId === "." || canvasId === ""
        ? placeSiteId
        : placeSiteId.startsWith(prefix)
          ? placeSiteId.slice(prefix.length)
          : null;
    if (!rel) return 1;
    return Math.max(1, rel.split("/").filter(Boolean).length);
  }

  async function onOutlineClick(node) {
    if (node.kind === "element") {
      await focusOutlineElement(node);
      return;
    }
    await focusOutlinePlace(node);
  }

  async function focusOutlinePlace(node) {
    const placeId = node.id;
    if (node.selectable) {
      if (locationId !== placeId) {
        await setCanvasLocation(placeId);
      }
      highlightOutline(placeId);
      clearSelectionState();
      setSelectedVisual();
      return;
    }
    const canvasRoot = nearestSelectableAncestor(placeId);
    if (!canvasRoot) {
      setStatus(`No canvas view for ${placeId}`);
      return;
    }
    const needDepth = placeDepthUnderCanvas(placeId, canvasRoot);
    const switched = locationId !== canvasRoot;
    if (switched) {
      depthLevel = needDepth;
      await setCanvasLocation(canvasRoot, { resetDepth: false });
    } else if (needDepth > depthLevel) {
      await setDepth(needDepth);
    }
    const rel = siteToCanvasRelative(placeId);
    if (rel) {
      await selectNode(rel);
    } else {
      highlightOutline(placeId);
    }
  }

  async function focusOutlineElement(node) {
    const parentPlace = node.parent;
    if (!parentPlace) return;
    const canvasRoot = nearestSelectableAncestor(parentPlace);
    if (!canvasRoot) {
      setStatus(`No canvas view for ${parentPlace}`);
      return;
    }
    const needDepth = placeDepthUnderCanvas(parentPlace, canvasRoot);
    const switched = locationId !== canvasRoot;
    if (switched) {
      depthLevel = needDepth;
      await setCanvasLocation(canvasRoot, { resetDepth: false });
    } else if (needDepth > depthLevel) {
      await setDepth(needDepth);
    }
    if (!showElements) {
      showElements = true;
      const toggle = document.getElementById("toggle-elements");
      if (toggle) toggle.checked = true;
      render();
    }
    const rel = siteToCanvasRelative(node.id);
    if (rel) {
      await selectNode(rel);
    } else {
      highlightOutline(node.id);
    }
  }

  async function loadLocation({ fit = true } = {}) {
    clearSelectionState();
    document.getElementById("panel-empty").classList.remove("hidden");
    document.getElementById("panel-show").classList.add("hidden");
    graph = await api(
      `/api/physical?location=${encodeURIComponent(locationId)}&depth=${depthLevel}`
    );
    depthLevel = graph.depth || depthLevel;
    maxDepth = graph.max_depth || 1;
    if (depthLevel > maxDepth) depthLevel = Math.max(maxDepth, 1);
    representationSelect.value = graph.page?.representation || "line";
    let filled = [];
    let filledElem = [];
    try {
      filled = await fillMissingLayout();
      filledElem = await fillMissingElectricalLayout();
    } catch (err) {
      setStatus(String(err.message || err));
    }
    render();
    resetLayoutHistory();
    if (fit) fitView();
    else applyWorldTransform();
    highlightOutline(locationId);
    await refreshStatus();
    const bits = [];
    if (filled.length) {
      bits.push(`${filled.length} place(s)`);
    }
    if (filledElem.length) {
      bits.push(`${filledElem.length} element(s)`);
    }
    if (bits.length) {
      setStatus(`auto-placed ${bits.join(" + ")} missing x/y · unsaved`);
    }
  }

  async function setDepth(next) {
    const capped = Math.min(Math.max(1, next), Math.max(maxDepth, 1));
    if (capped === depthLevel && graph) {
      updateDepthLabel();
      return;
    }
    depthLevel = capped;
    await loadLocation({ fit: false });
  }

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

  const toggleElements = document.getElementById("toggle-elements");
  const toggleCables = document.getElementById("toggle-cables");
  if (toggleElements) {
    toggleElements.addEventListener("change", () => {
      showElements = Boolean(toggleElements.checked);
      render();
      renderOutline();
    });
  }
  if (toggleCables) {
    toggleCables.addEventListener("change", () => {
      showCables = Boolean(toggleCables.checked);
      render();
    });
  }

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
      let elemUpdated = [];
      if (showElements) {
        const elData = await api(`/api/electrical/auto-layout`, {
          method: "POST",
          body: JSON.stringify({
            location_id: locationId,
            force: true,
            depth: depthLevel,
          }),
        });
        if (elData.graph) graph = elData.graph;
        elemUpdated = elData.updated || [];
      }
      render();
      if (data.updated.length || elemUpdated.length) pushLayoutHistory();
      setStatus(
        `auto-layout: ${data.updated.length} place(s)` +
          (elemUpdated.length ? `, ${elemUpdated.length} element(s)` : "")
      );
      scheduleStatusRefresh();
    } catch (err) {
      setStatus(String(err.message || err));
    }
  });

  document.getElementById("btn-undo").addEventListener("click", () => {
    undoLayout().catch((err) => setStatus(String(err.message || err)));
  });
  document.getElementById("btn-redo").addEventListener("click", () => {
    redoLayout().catch((err) => setStatus(String(err.message || err)));
  });
  document.getElementById("btn-layout-reset").addEventListener("click", () => {
    resetLayout().catch((err) => setStatus(String(err.message || err)));
  });

  document.addEventListener("keydown", (ev) => {
    const tag = (ev.target && ev.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    const mod = ev.ctrlKey || ev.metaKey;
    if (!mod) return;
    const key = ev.key.toLowerCase();
    if (key === "z" && !ev.shiftKey) {
      ev.preventDefault();
      undoLayout().catch((err) => setStatus(String(err.message || err)));
    } else if (key === "y" || (key === "z" && ev.shiftKey)) {
      ev.preventDefault();
      redoLayout().catch((err) => setStatus(String(err.message || err)));
    }
  });

  document.getElementById("btn-save").addEventListener("click", async () => {
    try {
      const data = await api("/api/save", { method: "POST", body: "{}" });
      setStatus(`saved ${data.saved.length} file(s)`);
      dirtyLocal = false;
      updateSaveButton(false);
      markLayoutBaseline();
    } catch (err) {
      setStatus(String(err.message || err));
    }
  });

  document.getElementById("btn-zoom-in").addEventListener("click", () => {
    scale = Math.min(3, scale * 1.15);
    applyWorldTransform();
  });
  document.getElementById("btn-zoom-out").addEventListener("click", () => {
    scale = Math.max(0.05, scale / 1.15);
    applyWorldTransform();
  });
  document.getElementById("btn-zoom-reset").addEventListener("click", () => {
    fitView();
  });

  document.getElementById("btn-depth-in").addEventListener("click", () => {
    setDepth(depthLevel + 1).catch((err) => setStatus(String(err.message || err)));
  });
  document.getElementById("btn-depth-out").addEventListener("click", () => {
    setDepth(depthLevel - 1).catch((err) => setStatus(String(err.message || err)));
  });

  viewport.addEventListener("pointerdown", (ev) => {
    if (drag || marquee) return;
    if (ev.target !== svg && ev.target !== viewport) return;
    const panWithLeft = spacePan || ev.altKey;
    if (ev.button === 1 || (ev.button === 0 && panWithLeft)) {
      ev.preventDefault();
      panDrag = { x: ev.clientX, y: ev.clientY, panX, panY };
      viewport.classList.add("panning");
      svg.setPointerCapture(ev.pointerId);
      return;
    }
    if (ev.button !== 0) return;
    marquee = {
      pointerId: ev.pointerId,
      startClientX: ev.clientX,
      startClientY: ev.clientY,
      additive: isModClick(ev),
      moved: false,
      captured: true,
    };
    viewport.classList.add("marqueeing");
    try {
      svg.setPointerCapture(ev.pointerId);
    } catch {
      /* ignore */
    }
  });

  window.addEventListener("keydown", (ev) => {
    if (ev.code === "Space" && !ev.repeat) {
      const tag = (ev.target && ev.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      spacePan = true;
      ev.preventDefault();
    }
  });
  window.addEventListener("keyup", (ev) => {
    if (ev.code === "Space") spacePan = false;
  });
  window.addEventListener("blur", () => {
    spacePan = false;
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
      const next = Math.min(3, Math.max(0.05, scale * factor));
      if (next === scale) return;
      const rect = viewport.getBoundingClientRect();
      const mx = ev.clientX - rect.left;
      const my = ev.clientY - rect.top;
      const ratio = next / scale;
      panX = mx - (mx - panX) * ratio;
      panY = my - (my - panY) * ratio;
      scale = next;
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
      await loadOutline();
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
