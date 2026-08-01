(() => {
  const svg = document.getElementById("canvas");
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
  /** Client mirror of whether the workspace has an open document. */
  let hasDocument = false;
  /** @type {string | null} */
  let activeDocId = null;
  /** @type {Record<string, FileSystemFileHandle>} */
  let fileHandles = {};
  /** Per-document canvas location/depth when switching tabs. */
  let docViews = {};
  let drag = null;
  let panDrag = null;
  let marquee = null;
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
  let showElectrical = false;
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
        if (c.kind === "element" && !showElectrical) return false;
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

  /** Font Awesome icon + type label on a canvas box (place or element). */
  function appendTypeWithIcon(g, { icon, typeText, x, y, maxW, textClass }) {
    const iconSize = 10;
    const gap = 3;
    const fo = document.createElementNS(ns, "foreignObject");
    fo.setAttribute("class", "type-icon-fo");
    fo.setAttribute("x", String(x));
    fo.setAttribute("y", String(y - iconSize));
    fo.setAttribute("width", String(iconSize + 2));
    fo.setAttribute("height", String(iconSize + 2));
    const i = document.createElement("i");
    i.className = `${faClass(icon)} type-icon`;
    i.setAttribute("aria-hidden", "true");
    fo.appendChild(i);
    g.appendChild(fo);
    const textX = x + iconSize + gap;
    g.appendChild(
      el(
        "text",
        { class: textClass, x: textX, y },
        fitLabel(typeText, Math.max(8, maxW - (iconSize + gap)))
      )
    );
  }

  const ns = "http://www.w3.org/2000/svg";

  function setStatus(text) {
    statusEl.textContent = text || "";
  }

  /**
   * In-app modal. Returns the chosen button id, or null if dismissed.
   * @param {{
   *   title?: string,
   *   message?: string,
   *   buttons?: { id: string, label: string, primary?: boolean, danger?: boolean }[]
   * }} opts
   */
  function appDialog(opts) {
    const modal = document.getElementById("app-modal");
    const titleEl = document.getElementById("app-modal-title");
    const msgEl = document.getElementById("app-modal-message");
    const actions = document.getElementById("app-modal-actions");
    if (!modal || !titleEl || !msgEl || !actions) {
      return Promise.resolve(null);
    }
    const buttons = opts.buttons || [
      { id: "cancel", label: "Cancel" },
      { id: "ok", label: "OK", primary: true },
    ];
    return new Promise((resolve) => {
      titleEl.textContent = opts.title || "HouseWire";
      msgEl.textContent = opts.message || "";
      actions.innerHTML = "";
      modal.classList.remove("hidden");
      modal.setAttribute("aria-hidden", "false");

      function finish(result) {
        modal.classList.add("hidden");
        modal.setAttribute("aria-hidden", "true");
        document.removeEventListener("keydown", onKey);
        modal
          .querySelectorAll("[data-modal-dismiss]")
          .forEach((el) => el.removeEventListener("click", onDismiss));
        resolve(result);
      }

      function onDismiss() {
        finish(null);
      }

      function onKey(ev) {
        if (ev.key === "Escape") {
          ev.preventDefault();
          finish(null);
        } else if (ev.key === "Enter") {
          const primary = buttons.find((b) => b.primary) || buttons[buttons.length - 1];
          if (primary) {
            ev.preventDefault();
            finish(primary.id);
          }
        }
      }

      for (const spec of buttons) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = spec.label;
        if (spec.primary) btn.classList.add("primary");
        if (spec.danger) btn.classList.add("danger");
        btn.addEventListener("click", () => finish(spec.id));
        actions.appendChild(btn);
      }

      document.addEventListener("keydown", onKey);
      modal
        .querySelectorAll("[data-modal-dismiss]")
        .forEach((el) => el.addEventListener("click", onDismiss));

      const focusBtn =
        actions.querySelector("button.primary") ||
        actions.querySelector("button:last-child");
      setTimeout(() => focusBtn && focusBtn.focus(), 0);
    });
  }

  /** @returns {Promise<"save"|"discard"|null>} */
  async function confirmUnsavedClose(docTitle) {
    const name = docTitle || "This file";
    const choice = await appDialog({
      title: "Unsaved changes",
      message: `${name} has unsaved changes. Save before closing?`,
      buttons: [
        { id: "cancel", label: "Cancel" },
        { id: "discard", label: "Discard", danger: true },
        { id: "save", label: "Save", primary: true },
      ],
    });
    if (choice === "save" || choice === "discard") return choice;
    return null;
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
    const undoDisabled = layoutIndex <= 0;
    const redoDisabled =
      layoutIndex < 0 || layoutIndex >= layoutHistory.length - 1;
    const resetDisabled =
      !layoutBaseline || snapsEqual(snapshotPositions(), layoutBaseline);
    for (const id of ["btn-undo", "menu-undo"]) {
      const el = document.getElementById(id);
      if (el) el.disabled = undoDisabled;
    }
    for (const id of ["btn-redo", "menu-redo"]) {
      const el = document.getElementById(id);
      if (el) el.disabled = redoDisabled;
    }
    for (const id of ["btn-layout-reset", "menu-layout-reset"]) {
      const el = document.getElementById(id);
      if (el) el.disabled = resetDisabled;
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
    if (!hasDocument || !locationId || !graph || !layoutBaseline) {
      dirtyLocal = false;
      return;
    }
    dirtyLocal = !snapsEqual(snapshotPositions(), layoutBaseline);
  }

  function updateFileMenuState({ dirty } = {}) {
    const menuSave = document.getElementById("menu-save");
    const menuSaveAs = document.getElementById("menu-save-as");
    const menuClose = document.getElementById("menu-close");
    const btnSave = document.getElementById("btn-save");
    const isDirty = dirty == null ? dirtyLocal : Boolean(dirty);
    const saveDisabled = !hasDocument || !isDirty;
    if (menuSave) menuSave.disabled = saveDisabled;
    if (btnSave) btnSave.disabled = saveDisabled;
    if (menuSaveAs) menuSaveAs.disabled = !hasDocument;
    if (menuClose) menuClose.disabled = !hasDocument;
  }

  function applyWorkspaceStatus(st) {
    const docs = (st && st.documents) || [];
    hasDocument = docs.length > 0 && Boolean(st.document);
    activeDocId = (st && st.active) || (st.document && st.document.id) || null;
    if (!hasDocument) {
      dirtyLocal = false;
      layoutBaseline = null;
      layoutHistory = [];
      layoutIndex = -1;
      activeDocId = null;
    }
    const serverDirty = ((st && st.dirty) || []).length > 0;
    if (hasDocument) syncLayoutDirty();
    else dirtyLocal = false;
    updateFileMenuState({ dirty: serverDirty || dirtyLocal });
    renderDocTabs(st);
    return st;
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
      depthLabel.textContent = `${depthLevel}/${Math.max(maxDepth, 1)}`;
    }
    const deeperIds = ["btn-depth-in", "menu-depth-in"];
    const shallowerIds = ["btn-depth-out", "menu-depth-out"];
    const deeperDisabled = depthLevel >= Math.max(maxDepth, 1);
    const shallowerDisabled = depthLevel <= 1;
    for (const id of deeperIds) {
      const el = document.getElementById(id);
      if (el) el.disabled = deeperDisabled;
    }
    for (const id of shallowerIds) {
      const el = document.getElementById(id);
      if (el) el.disabled = shallowerDisabled;
    }
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
    if (showElectrical) {
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

  const PLANE_R = 6;

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
  function planeAnchorLocal(node, openingId, face) {
    const w = nodeW(node);
    const h = nodeH(node);
    const plane = parsePlaneOpening(openingId);
    const f = (plane?.face || face || "?").toUpperCase();
    if (!plane || (f !== "B" && f !== "F")) {
      return { x: w / 2, y: h / 2 };
    }
    const { cols, rows } = planeGridDims(node, f, plane);
    return {
      x: planeCellCenter(w, cols, plane.col, PLANE_R),
      y: planeCellCenter(h, rows, plane.row, PLANE_R),
    };
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
      const local = planeAnchorLocal(node, openingId, f);
      return { x: a.x + local.x, y: a.y + local.y };
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
      return planeAnchorLocal(node, openingId, f);
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

  /** Nearest contour face for routing stubs into a B/F opening. */
  function planeApproachFace(node, openingId, face, byId) {
    const p = openingAnchorAbs(node, openingId, face, byId);
    const a = absXY(node, byId);
    const w = nodeW(node);
    const h = nodeH(node);
    const dists = [
      ["N", p.y - a.y],
      ["S", a.y + h - p.y],
      ["W", p.x - a.x],
      ["E", a.x + w - p.x],
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
    return f;
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
  }

  function applyWorldTransform() {
    if (worldEl) {
      worldEl.setAttribute(
        "transform",
        `translate(${panX},${panY}) scale(${scale})`
      );
    }
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
      return;
    }
    const sx = (viewW - pad * 2) / bounds.w;
    const sy = (viewH - pad * 2) / bounds.h;
    scale = Math.min(3, Math.max(0.05, Math.min(sx, sy)));
    panX = pad - bounds.minX * scale + (viewW - pad * 2 - bounds.w * scale) / 2;
    panY = pad - bounds.minY * scale + (viewH - pad * 2 - bounds.h * scale) / 2;
    applyWorldTransform();
  }

  function pointsToPathD(pts) {
    if (!pts.length) return "";
    let d = `M ${pts[0][0]} ${pts[0][1]}`;
    for (let i = 1; i < pts.length; i++) {
      d += ` L ${pts[i][0]} ${pts[i][1]}`;
    }
    return d;
  }

  function segsFromPoints(pts) {
    /** @type {{axis:string,x?:number,y?:number,a:number,b:number}[]} */
    const segs = [];
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
        });
      } else if (Math.abs(x1 - x2) < 1e-6) {
        segs.push({
          axis: "V",
          x: x1,
          a: Math.min(y1, y2),
          b: Math.max(y1, y2),
        });
      }
    }
    return segs;
  }

  function rangeOverlapLen(a1, a2, b1, b2) {
    return Math.max(0, Math.min(a2, b2) - Math.max(a1, b1));
  }

  /** Colinear stack is expensive; a proper crossing is a smaller penalty. */
  function segConflict(s, o, eps) {
    if (s.axis === "H" && o.axis === "H") {
      if (Math.abs(s.y - o.y) > eps) return 0;
      const ov = rangeOverlapLen(s.a, s.b, o.a, o.b);
      if (ov <= eps) return 0;
      return 200 + ov;
    }
    if (s.axis === "V" && o.axis === "V") {
      if (Math.abs(s.x - o.x) > eps) return 0;
      const ov = rangeOverlapLen(s.a, s.b, o.a, o.b);
      if (ov <= eps) return 0;
      return 200 + ov;
    }
    if (s.axis === "H" && o.axis === "V") {
      const y = s.y;
      const x = o.x;
      if (x > s.a + 1 && x < s.b - 1 && y > o.a + 1 && y < o.b - 1) {
        return 25;
      }
    } else if (s.axis === "V" && o.axis === "H") {
      const x = s.x;
      const y = o.y;
      if (y > s.a + 1 && y < s.b - 1 && x > o.a + 1 && x < o.b - 1) {
        return 25;
      }
    }
    return 0;
  }

  function pathConflictCost(pts, occupied, eps) {
    if (!occupied || !occupied.length) return 0;
    let cost = 0;
    for (const s of segsFromPoints(pts)) {
      for (const o of occupied) {
        cost += segConflict(s, o, eps);
      }
    }
    return cost;
  }

  /** Shrunk leaf-place rects as routing obstacles (skip rooms/containers). */
  function placeObstacles(byId, excludeIds, inset) {
    const ex = new Set(excludeIds || []);
    const pad = inset == null ? 8 : inset;
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

  function pathObstacleCost(pts, obstacles) {
    if (!obstacles || !obstacles.length) return 0;
    let cost = 0;
    for (const s of segsFromPoints(pts)) {
      for (const r of obstacles) {
        if (s.axis === "H") {
          if (s.y <= r.y || s.y >= r.y + r.h) continue;
          const ov = rangeOverlapLen(s.a, s.b, r.x, r.x + r.w);
          if (ov > 1) cost += 180 + ov;
        } else {
          if (s.x <= r.x || s.x >= r.x + r.w) continue;
          const ov = rangeOverlapLen(s.a, s.b, r.y, r.y + r.h);
          if (ov > 1) cost += 180 + ov;
        }
      }
    }
    return cost;
  }

  /**
   * Orthogonal route points from p1 to p2. When ``occupied`` is set, prefer
   * candidates that avoid colinear overlap (and lightly avoid crossings).
   * ``obstacles`` are place rects to go around (C / outer rails).
   */
  function orthoRoute(p1, p2, fromFace, toFace, occupied, obstacles) {
    const x1 = p1.x;
    const y1 = p1.y;
    const x2 = p2.x;
    const y2 = p2.y;
    if (x1 === x2 && y1 === y2) {
      return [[x1, y1]];
    }

    const STUB = 20;
    const DETOUR = 48;
    const LANE = 14;
    const OVERLAP_EPS = 6;
    const pts = [[x1, y1]];
    let ax = x1;
    let ay = y1;
    let bx = x2;
    let by = y2;

    if (fromFace === "E") {
      ax = x1 + STUB;
      pts.push([ax, ay]);
    } else if (fromFace === "W") {
      ax = x1 - STUB;
      pts.push([ax, ay]);
    } else if (fromFace === "S") {
      ay = y1 + STUB;
      pts.push([ax, ay]);
    } else if (fromFace === "N") {
      ay = y1 - STUB;
      pts.push([ax, ay]);
    }
    if (toFace === "E") bx = x2 + STUB;
    else if (toFace === "W") bx = x2 - STUB;
    else if (toFace === "S") by = y2 + STUB;
    else if (toFace === "N") by = y2 - STUB;

    const mid = minBendOrtho(
      ax,
      ay,
      bx,
      by,
      fromFace,
      toFace,
      DETOUR,
      STUB,
      LANE,
      occupied,
      OVERLAP_EPS,
      obstacles
    );
    for (const p of mid) {
      pts.push(p);
    }
    if (bx !== x2 || by !== y2) {
      pts.push([x2, y2]);
    }
    return cleanOrthoPoly(pts);
  }

  function orthoPathD(p1, p2, fromFace, toFace, occupied, obstacles) {
    return pointsToPathD(
      orthoRoute(p1, p2, fromFace, toFace, occupied, obstacles)
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
    obstacles
  ) {
    const start = [ax, ay];
    const end = [bx, by];
    /** @type {number[][][]} */
    const raw = [];
    const needLanes =
      lane &&
      ((occupied && occupied.length) || (obstacles && obstacles.length));

    const push = (pts) => {
      const cleaned = cleanOrthoPoly([start, ...pts, end]);
      if (cleaned.length < 2) return;
      if (!isOrthoPoly(cleaned)) return;
      if (hasUTurn(cleaned)) return;
      const next = cleaned[1];
      if (!leavesOutward(fromFace, ax, ay, next[0], next[1])) return;
      raw.push(cleaned.slice(1)); // intermediates through end
    };

    // 0 bends — only when already aligned (same x or same y)
    if (Math.abs(ax - bx) < 1e-6 || Math.abs(ay - by) < 1e-6) {
      push([]);
    }

    // 1 bend (L)
    push([[bx, ay]]);
    push([[ax, by]]);

    // 2 bends (Z through mid) + parallel lanes to dodge prior routes / boxes
    const mx = (ax + bx) / 2;
    const my = (ay + by) / 2;
    const laneOffs = [0];
    if (needLanes) {
      for (let k = 1; k <= 4; k++) {
        laneOffs.push(k * lane, -k * lane);
      }
    }
    for (const off of laneOffs) {
      push([[mx + off, ay], [mx + off, by]]);
      push([[ax, my + off], [bx, my + off]]);
    }

    // 2 bends: outer rails (approach from beyond the entry stub)
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

    // Always emit outer rails on all four sides when dodging boxes (true C).
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
      // Rails that clear each obstacle rect (endpoint boxes included).
      // Stub-relative detours alone cannot clear a large from/to box.
      const obsOffs = needLanes ? [0, lane, -lane, 2 * lane, -2 * lane] : [0];
      const pad = Math.max(stub, 12);
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
          push([[xRo, ay], [xRo, by]]);
          push([[xLo, ay], [xLo, by]]);
          push([[ax, yBo], [bx, yBo]]);
          push([[ax, yTo], [bx, yTo]]);
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

    // 3 bends: side C loops
    const detours = obstacles && obstacles.length ? [detour, detour * 2] : [detour];
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
        push([
          [right, ay],
          [right, bot],
          [bx, bot],
        ]);
        push([
          [left, ay],
          [left, top],
          [bx, top],
        ]);
        push([
          [ax, bot],
          [right, bot],
          [right, by],
        ]);
        push([
          [ax, top],
          [left, top],
          [left, by],
        ]);
      }
    }

    if (!raw.length) {
      // Fallback: forced side C
      return [
        [ax + detour, ay],
        [ax + detour, by],
        [bx, by],
      ];
    }

    let best = raw[0];
    let bestBendEquiv = Infinity;
    let bestHard = Infinity;
    let bestLen = Infinity;
    const eps = overlapEps ?? 6;
    for (const pts of raw) {
      const full = [[ax, ay], ...pts];
      const bends = polyBends(full);
      const conflict = pathConflictCost(full, occupied, eps);
      const obstacle = pathObstacleCost(full, obstacles);
      const len = polyLength(full);
      // Obstacle hits dominate: ~50 cost ≈ one bend → crossing a box (~180)
      // costs more than a 3-bend C. Conflict ~150 ≈ one bend for stacked tubes.
      const bendEquiv = bends + conflict / 150 + obstacle / 50;
      const hard = obstacle + conflict;
      if (
        bendEquiv < bestBendEquiv - 1e-9 ||
        (Math.abs(bendEquiv - bestBendEquiv) < 1e-9 && hard < bestHard) ||
        (Math.abs(bendEquiv - bestBendEquiv) < 1e-9 &&
          hard === bestHard &&
          len < bestLen)
      ) {
        best = pts;
        bestBendEquiv = bendEquiv;
        bestHard = hard;
        bestLen = len;
      }
    }
    return best;
  }

  function edgePathD(edge, byId, occupied) {
    const a = byId[edge.from];
    const b = byId[edge.to];
    if (!a || !b) return null;
    const fromFace = routeFace(a, edge.from_opening, edge.from_opening?.[0], byId);
    const toFace = routeFace(b, edge.to_opening, edge.to_opening?.[0], byId);
    const p1 = openingAnchorAbs(a, edge.from_opening, edge.from_opening?.[0], byId);
    const p2 = openingAnchorAbs(b, edge.to_opening, edge.to_opening?.[0], byId);
    // Include endpoints: stubs leave the faces, so mid-routes must go around
    // the boxes themselves (otherwise L/Z cuts back through the interior).
    const obstacles = placeObstacles(byId, []);
    const pts = orthoRoute(p1, p2, fromFace, toFace, occupied, obstacles);
    return { d: pointsToPathD(pts), segs: segsFromPoints(pts) };
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

  /** Side midpoint of an element facing ``toward`` (same-box cable endpoints). */
  function elementAttachPoint(elem, toward, placeById) {
    const p = elementAbsXY(elem, placeById);
    const w = elem.w ?? ELEM_W;
    const h = elem.h ?? ELEM_H;
    const cx = p.x + w / 2;
    const cy = p.y + h / 2;
    const dx = toward.x - cx;
    const dy = toward.y - cy;
    if (Math.abs(dx) >= Math.abs(dy)) {
      return { x: dx >= 0 ? p.x + w : p.x, y: cy };
    }
    return { x: cx, y: dy >= 0 ? p.y + h : p.y };
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

  /** Exact tube geometry for a hop (same path as the conduit edge). */
  function hopTubePathD(hop) {
    const item = edgePaths.find((e) => e.edge && e.edge.id === hop.conduit);
    if (!item || !item.d) return null;
    const e = item.edge;
    if (e.from === hop.from && e.to === hop.to) return item.d;
    if (e.from === hop.to && e.to === hop.from) return reversePathD(item.d);
    return null;
  }

  function cablePathD(edge, placeById, elemById, occupied) {
    const a = elemById[edge.from];
    const b = elemById[edge.to];
    if (!a || !b) return null;
    const c1 = elementCenter(a, placeById);
    const c2 = elementCenter(b, placeById);

    // Same box: local bridges only (edge-to-edge L). Hop cables do not paint
    // inside — stubs/tails stacked into a lattice and floating fragments.
    if (a.parent && b.parent && a.parent === b.parent) {
      const p1 = elementAttachPoint(a, c2, placeById);
      const p2 = elementAttachPoint(b, c1, placeById);
      return pointsToPathD(simpleOrthoPts(p1, p2));
    }

    const parentExclude = [a.parent, b.parent].filter(Boolean);
    const outsideObstacles = placeObstacles(placeById, parentExclude);
    const leafObstacles = placeObstacles(placeById, [], 0);

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
      // Exterior tube overlay only (teal tubes already show the run; green
      // rides the conduit outside leaf boxes).
      /** @type {string[]} */
      const parts = [];
      for (let i = 0; i < hops.length; i++) {
        const hop = hops[i];
        const pf = placeById[hop.from];
        const pt = placeById[hop.to];
        if (!pf || !pt || !hop.from_opening || !hop.to_opening) {
          return orthoPathD(c1, c2, null, null, occupied, outsideObstacles);
        }
        const tubeD = hopTubePathD(hop);
        if (tubeD) {
          const ext = exteriorPathD(tubeD, leafObstacles);
          if (ext) parts.push(ext);
          continue;
        }
        const opA = openingAnchorAbs(
          pf,
          hop.from_opening,
          hop.from_opening?.[0],
          placeById
        );
        const opB = openingAnchorAbs(
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
          placeObstacles(placeById, [])
        );
        const ext = exteriorPathD(pointsToPathD(routed), leafObstacles);
        if (ext) parts.push(ext);
      }
      return parts.length ? parts.join(" ") : null;
    }
    return orthoPathD(c1, c2, null, null, occupied, outsideObstacles);
  }

  function refreshEdges() {
    if (!graph) return;
    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    /** @type {{axis:string,x?:number,y?:number,a:number,b:number}[]} */
    const occupied = [];
    for (const item of edgePaths) {
      const routed = edgePathD(item.edge, byId, occupied);
      if (routed) {
        item.d = routed.d;
        for (const path of item.paths) path.setAttribute("d", routed.d);
        for (const s of routed.segs) occupied.push(s);
      }
    }
    const elemById = Object.fromEntries(
      (graph.elements || []).map((e) => [e.id, e])
    );
    for (const item of cablePaths) {
      const d = cablePathD(item.edge, byId, elemById, occupied);
      if (d) {
        for (const path of item.paths) path.setAttribute("d", d);
      }
    }
  }

  function syncOpeningMarks(node) {
    const g = nodesById[node.id];
    if (!g || !node.openings?.length) return;
    const w = nodeW(node);
    const h = nodeH(node);
    for (const op of node.openings) {
      const face = (op.face || op.id?.[0] || "?").toUpperCase();
      const anchor = openingAnchorLocal(node, op.id, face);
      const sel = `[data-opening="${CSS.escape(String(op.id))}"]`;
      if (face === "B" || face === "F") {
        const circle = g.querySelector(`circle${sel}`);
        const text = g.querySelector(`text${sel}`);
        if (circle) {
          circle.setAttribute("cx", String(anchor.x));
          circle.setAttribute("cy", String(anchor.y));
        }
        if (text) {
          text.setAttribute("x", String(anchor.x));
          text.setAttribute("y", String(anchor.y + 3));
        }
        continue;
      }
      const text = g.querySelector(`text.opening-side${sel}`);
      if (!text) continue;
      const labelX =
        face === "W" ? 4 : face === "E" ? w - 4 : anchor.x;
      const labelY =
        face === "N" ? 10 : face === "S" ? h - 3 : anchor.y + 3;
      text.setAttribute("x", String(labelX));
      text.setAttribute("y", String(labelY));
      text.setAttribute(
        "text-anchor",
        face === "W" ? "start" : face === "E" ? "end" : "middle"
      );
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
          n.display_name || n.name || n.id,
          w
        );
      }
      const typeEl = g.querySelector("text.node-type");
      if (typeEl) {
        typeEl.textContent = fitLabel(
          (n.type || "") + (n.expandable ? " · +" : ""),
          Math.max(8, w - 21)
        );
      }
      syncOpeningMarks(n);
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
    g.appendChild(el("title", null, fullLabel));
    g.appendChild(
      el(
        "text",
        { class: "node-label", x: 8, y: 18 },
        fitLabel(canvasName, w)
      )
    );
    appendTypeWithIcon(g, {
      icon: node.icon,
      typeText: (node.type || "") + (node.expandable ? " · +" : ""),
      x: 8,
      y: 34,
      maxW: w - 16,
      textClass: "node-type",
    });

    if (!hasKids) {
      const planes = (node.openings || []).filter(
        (o) => o.face === "B" || o.face === "F"
      );
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
              "data-opening": op.id,
              x: labelX,
              y: labelY,
              "text-anchor":
                op.face === "W" ? "start" : op.face === "E" ? "end" : "middle",
            },
            op.id
          )
        );
      }
      for (const op of planes) {
        const anchor = openingAnchorLocal(node, op.id, op.face);
        const markClass =
          op.face === "F" ? "opening-front-mark" : "opening-back-mark";
        const textClass =
          op.face === "F" ? "opening-front" : "opening-back";
        g.appendChild(
          el("circle", {
            class: markClass,
            "data-opening": op.id,
            cx: anchor.x,
            cy: anchor.y,
            r: PLANE_R,
          })
        );
        g.appendChild(
          el(
            "text",
            {
              class: textClass,
              "data-opening": op.id,
              x: anchor.x,
              y: anchor.y + 3,
              "text-anchor": "middle",
            },
            op.id
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
      (elem.display_label || elem.label || elem.display_name || elem.name || elem.id) +
      (elem.type ? ` · ${elem.type}` : "");
    g.appendChild(el("title", null, title));
    g.appendChild(
      el(
        "text",
        { class: "element-label", x: 4, y: 12 },
        fitLabel(elem.display_name || elem.name || elem.leaf_id || elem.id, w - 4)
      )
    );
    appendTypeWithIcon(g, {
      icon: elem.icon,
      typeText: elem.type || "",
      x: 4,
      y: 22,
      maxW: w - 8,
      textClass: "element-type",
    });
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

    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    const elemById = Object.fromEntries(
      (graph.elements || []).map((e) => [e.id, e])
    );

    // Containers → leaves → conduits → elements → cables (cables on top so
    // in-box tails stay visible over tube caps).
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

    /** @type {{axis:string,x?:number,y?:number,a:number,b:number}[]} */
    const occupied = [];
    for (const edge of graph.edges) {
      const routed = edgePathD(edge, byId, occupied);
      if (!routed) continue;
      const d = routed.d;
      for (const s of routed.segs) occupied.push(s);
      const contains = (edge.contains || []).join(", ");
      const edgeName = edge.name || edge.id;
      const title = contains
        ? `${edgeName}: ${contains}`
        : String(edgeName || "");
      const tube = el("path", { class: "edge-tube", d });
      const core = el("path", { class: "edge-tube-core", d });
      tube.appendChild(el("title", null, title));
      core.appendChild(el("title", null, title));
      edgesG.appendChild(tube);
      edgesG.appendChild(core);
      edgePaths.push({ edge, paths: [tube, core], d });
    }

    for (const node of graph.nodes) {
      if (!childrenOf(node.id).length) paintNode(node, leavesG, byId);
    }

    if (showElectrical) {
      for (const elem of graph.elements || []) {
        if (elem.parent && !byId[elem.parent]) continue;
        // Like depth: interior elements only when the place is a leaf in view.
        if (elem.parent && childrenOf(elem.parent).length) continue;
        paintElement(elem, elementsG, byId);
      }
    }

    // Cables last (above tubes + elements) using the cached tube paths.
    if (showElectrical) {
      for (const edge of graph.cable_edges || []) {
        const d = cablePathD(edge, byId, elemById, occupied);
        if (!d) continue;
        const colors = (edge.colors || []).join(",");
        const edgeName = edge.name || edge.id || edge.via || "";
        const title = colors
          ? `${edgeName} (${colors})`
          : String(edgeName);
        const line = el("path", { class: "cable-edge", d });
        line.appendChild(el("title", null, title));
        cablesG.appendChild(line);
        cablePaths.push({ edge, paths: [line] });
      }
    }
    updateDepthLabel();
  }

  function selectElement(elem) {
    replaceSelection(elem.id);
    highlightOutline(canvasToSiteId(elem.id));
    fillElementInspector(elem);
  }

  function setInspectorMode(mode) {
    const elements = document.getElementById("show-elements-block");
    const conduits = document.getElementById("show-conduits-block");
    const cables = document.getElementById("show-cables-block");
    const placeMode = mode === "place";
    elements.classList.toggle("hidden", !placeMode);
    conduits.classList.toggle("hidden", !placeMode);
    cables.classList.toggle("hidden", placeMode);
  }

  function fillElementInspector(elem) {
    const empty = document.getElementById("panel-empty");
    const show = document.getElementById("panel-show");
    empty.classList.add("hidden");
    show.classList.remove("hidden");
    setInspectorMode("element");
    const meta = document.getElementById("show-meta");
    meta.innerHTML = "";
    const rows = [
      ["id", elem.leaf_id || elem.id],
      ["name", elem.name || elem.display_name],
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
    fillCablesForElement(elem);
  }

  function fillListEmpty(ul, label) {
    ul.innerHTML = "";
    const li = document.createElement("li");
    li.className = "show-empty";
    li.textContent = label;
    ul.appendChild(li);
  }

  function appendSub(li, text) {
    if (!text) return;
    const span = document.createElement("span");
    span.className = "show-sub";
    span.textContent = text;
    li.appendChild(span);
  }

  function fillConduitsList(conduits) {
    const ul = document.getElementById("show-conduits");
    ul.innerHTML = "";
    if (!conduits || !conduits.length) {
      fillListEmpty(ul, "—");
      return;
    }
    for (const c of conduits) {
      const li = document.createElement("li");
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
      ul.appendChild(li);
    }
  }

  function fillCablesForElement(elem) {
    const ul = document.getElementById("show-cables");
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
      const other = e.from === elem.id ? e.to : e.from;
      const title = e.name || e.id || "cable";
      const bits = [title, `↔ ${other}`];
      if ((e.colors || []).length) bits.push((e.colors || []).join(", "));
      if (e.conduit) bits.push(`via ${e.conduit}`);
      li.textContent = bits.join(" · ");
      if (e.name && e.id && e.name !== e.id) {
        appendSub(li, `id: ${e.id}`);
      }
      ul.appendChild(li);
    }
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
      setInspectorMode("place");
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
      if (!(detail.elements || []).length) {
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
      fillConduitsList(detail.conduits || []);
      prefillInsertForms(detail);
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
        // Keep x/y >= 0; parent place grows via measureVisibleSizes.
        elem.x = Math.max(0, Math.round(item.origX + dx));
        elem.y = Math.max(0, Math.round(item.origY + dy));
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
      const st = applyWorkspaceStatus(await api("/api/workspace"));
      if (!hasDocument) {
        return;
      }
      const n = (st.dirty || []).length;
      const dirty = n > 0 || dirtyLocal;
      setStatus(
        n ? `${n} dirty file(s)` : dirtyLocal ? "layout pending" : "saved"
      );
      updateFileMenuState({ dirty });
    } catch {
      /* ignore */
    }
  }

  function updateSaveButton(dirty) {
    updateFileMenuState({ dirty });
  }

  async function saveDocument() {
    const data = await api("/api/save", { method: "POST", body: "{}" });
    const handle = activeDocId ? fileHandles[activeDocId] : null;
    if (handle && data.yaml != null) {
      await writeTextToFileHandle(handle, data.yaml);
    } else if (data.browser_origin && data.yaml != null && !handle) {
      downloadYamlBlob(data.filename || "housewire.yaml", data.yaml);
    }
    setStatus(`saved ${(data.saved || []).length} file(s)`);
    dirtyLocal = false;
    updateSaveButton(false);
    markLayoutBaseline();
    await refreshDocumentLabel();
    return data;
  }

  function rememberCurrentDocView() {
    if (!activeDocId) return;
    docViews[activeDocId] = {
      locationId: locationId,
      depthLevel: depthLevel,
    };
  }

  function resetCanvasState() {
    locationId = null;
    graph = null;
    clearSelectionState();
    dirtyLocal = false;
    layoutHistory = [];
    layoutIndex = -1;
    layoutBaseline = null;
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
  }

  function setElectrical(on) {
    showElectrical = Boolean(on);
    syncElectricalUi();
    render();
    renderOutline();
  }

  function zoomIn() {
    setScale(scale * 1.15);
  }

  function zoomOut() {
    setScale(scale / 1.15);
  }

  async function runAutoLayout() {
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
    if (showElectrical) {
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
  }

  const YAML_PICKER_TYPES = [
    {
      description: "YAML",
      accept: {
        "application/yaml": [".yaml", ".yml"],
        "text/yaml": [".yaml", ".yml"],
        "text/plain": [".yaml", ".yml"],
      },
    },
  ];

  async function writeTextToFileHandle(handle, text) {
    const writable = await handle.createWritable();
    await writable.write(text);
    await writable.close();
  }

  function downloadYamlBlob(filename, content) {
    const blob = new Blob([content], { type: "application/yaml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || "housewire.yaml";
    a.click();
    URL.revokeObjectURL(url);
  }

  function pickOpenYamlViaInput() {
    return new Promise((resolve) => {
      const input = document.getElementById("file-open-input");
      if (!input) {
        resolve(null);
        return;
      }
      input.value = "";
      const onChange = () => {
        input.removeEventListener("change", onChange);
        const file = input.files && input.files[0];
        if (!file) {
          resolve(null);
          return;
        }
        file.text().then((content) => {
          resolve({ handle: null, name: file.name, content });
        }, () => resolve(null));
      };
      input.addEventListener("change", onChange);
      input.click();
    });
  }

  async function pickOpenYamlFile() {
    if (typeof window.showOpenFilePicker === "function") {
      try {
        const [handle] = await window.showOpenFilePicker({
          multiple: false,
          types: YAML_PICKER_TYPES,
          excludeAcceptAllOption: false,
        });
        const file = await handle.getFile();
        return {
          handle,
          name: file.name,
          content: await file.text(),
        };
      } catch (err) {
        if (err && err.name === "AbortError") return null;
      }
    }
    return pickOpenYamlViaInput();
  }

  async function pickSaveYamlFile(suggestedName, content) {
    if (typeof window.showSaveFilePicker === "function") {
      try {
        const handle = await window.showSaveFilePicker({
          suggestedName: suggestedName || "housewire.yaml",
          types: YAML_PICKER_TYPES,
          excludeAcceptAllOption: false,
        });
        await writeTextToFileHandle(handle, content);
        return { handle, name: handle.name || suggestedName };
      } catch (err) {
        if (err && err.name === "AbortError") return null;
      }
    }
    downloadYamlBlob(suggestedName || "housewire.yaml", content);
    return {
      handle: null,
      name: suggestedName || "housewire.yaml",
      downloaded: true,
    };
  }

  async function isDocumentDirty() {
    try {
      const st = applyWorkspaceStatus(await api("/api/workspace"));
      if (!hasDocument) return false;
      const serverDirty = (st.dirty || []).length > 0;
      return serverDirty || dirtyLocal;
    } catch {
      // Do not block Open/Close on a transient API error.
      return false;
    }
  }

  async function fileOpen() {
    // Multi-doc: Open always adds/activates a tab; no discard of other files.
    const picked = await pickOpenYamlFile();
    if (!picked) return;
    rememberCurrentDocView();
    try {
      const st = await api("/api/workspace/open-content", {
        method: "POST",
        body: JSON.stringify({
          filename: picked.name,
          content: picked.content,
        }),
      });
      applyWorkspaceStatus(st);
      if (picked.handle && st.document && st.document.id) {
        fileHandles[st.document.id] = picked.handle;
      }
      await reloadAfterDocumentChange();
      setStatus(`opened ${picked.name}`);
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }

  async function fileSaveAs() {
    let exported;
    try {
      exported = await api("/api/workspace/yaml");
    } catch (err) {
      setStatus(String(err.message || err));
      return;
    }
    const suggested = exported.filename || "housewire.yaml";
    const result = await pickSaveYamlFile(suggested, exported.content);
    if (!result) return;
    rememberCurrentDocView();
    try {
      const st = await api("/api/workspace/open-content", {
        method: "POST",
        body: JSON.stringify({
          filename: result.name,
          content: exported.content,
        }),
      });
      applyWorkspaceStatus(st);
      if (result.handle && st.document && st.document.id) {
        fileHandles[st.document.id] = result.handle;
      }
      dirtyLocal = false;
      updateSaveButton(false);
      await reloadAfterDocumentChange();
      setStatus(
        result.downloaded
          ? `downloaded ${result.name}`
          : `saved as ${result.name}`
      );
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }

  async function closeDocument(docId) {
    if (!docId) return;
    let dirty = false;
    let title = "This file";
    try {
      const st = await api("/api/workspace");
      const row = (st.documents || []).find((d) => d.id === docId);
      dirty = Boolean(row && row.dirty);
      if (row && (row.title || row.yaml)) title = row.title || row.yaml;
      if (docId === activeDocId) {
        syncLayoutDirty();
        dirty = dirty || dirtyLocal || (st.dirty || []).length > 0;
      }
    } catch {
      dirty = docId === activeDocId && dirtyLocal;
    }
    if (dirty) {
      const choice = await confirmUnsavedClose(title);
      if (!choice) return;
      if (choice === "save") {
        const wasActive = docId === activeDocId;
        if (!wasActive) {
          try {
            await api("/api/workspace/activate", {
              method: "POST",
              body: JSON.stringify({ id: docId }),
            });
            applyWorkspaceStatus(await api("/api/workspace"));
          } catch (err) {
            setStatus(String(err.message || err));
            return;
          }
        }
        try {
          await saveDocument();
        } catch (err) {
          setStatus(String(err.message || err));
          return;
        }
      }
    }
    const wasActive = docId === activeDocId;
    rememberCurrentDocView();
    try {
      const st = await api("/api/workspace/close", {
        method: "POST",
        body: JSON.stringify({ force: true, id: docId }),
      });
      delete fileHandles[docId];
      delete docViews[docId];
      applyWorkspaceStatus(st);
      if (!hasDocument) {
        clearDocumentUi();
        await refreshDocumentLabel();
        setStatus("document closed — File → Open…");
        return;
      }
      if (wasActive) {
        resetCanvasState();
        await loadLocations();
      }
      setStatus("document closed");
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }

  async function fileClose() {
    if (!activeDocId) return;
    await closeDocument(activeDocId);
  }

  async function activateDocument(docId) {
    if (!docId || docId === activeDocId) return;
    rememberCurrentDocView();
    try {
      const st = await api("/api/workspace/activate", {
        method: "POST",
        body: JSON.stringify({ id: docId }),
      });
      applyWorkspaceStatus(st);
      resetCanvasState();
      await loadLocations();
      setStatus(`switched to ${(st.document && st.document.title) || docId}`);
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }

  async function handleFileAction(action) {
    closeFileMenu();
    if (action === "open") await fileOpen();
    else if (action === "save") {
      try {
        await saveDocument();
      } catch (err) {
        setStatus(String(err.message || err));
      }
    } else if (action === "save-as") await fileSaveAs();
    else if (action === "close") await fileClose();
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
    await refreshDocumentLabel();
    if (!hasDocument) {
      canvasLocations = [];
      svg.innerHTML = "";
      return;
    }
    const data = await api("/api/locations");
    canvasLocations = data.locations || [];
    await loadOutline();
    const saved = activeDocId ? docViews[activeDocId] : null;
    let target =
      (saved &&
        saved.locationId &&
        canvasLocations.find(
          (r) => r.selectable !== false && r.id === saved.locationId
        )) ||
      canvasLocations.find((r) => r.selectable !== false && r.id === ".") ||
      canvasLocations.find((r) => r.selectable !== false);
    if (target) {
      if (saved && saved.depthLevel) depthLevel = saved.depthLevel;
      else depthLevel = 1;
      await setCanvasLocation(target.id, { resetDepth: !saved });
    } else {
      setStatus("No locations with children found");
    }
  }

  async function refreshDocumentLabel() {
    const el = document.getElementById("doc-label");
    if (!el) return;
    try {
      const st = applyWorkspaceStatus(await api("/api/workspace"));
      const doc = st.document;
      if (!doc) {
        el.textContent = "(no document)";
        el.title = "Active site document";
        return;
      }
      const n = (st.documents || []).length;
      el.textContent =
        n > 1 ? `${doc.title} (${n} open)` : String(doc.title || doc.yaml);
      el.title = doc.yaml_path
        ? String(doc.yaml_path)
        : String(doc.path || "Active site document");
    } catch {
      el.textContent = "";
      hasDocument = false;
      updateFileMenuState({ dirty: false });
    }
  }

  function renderDocTabs(st) {
    const bar = document.getElementById("view-tabs");
    if (!bar) return;
    bar.innerHTML = "";
    const docs = (st && st.documents) || [];
    const active = (st && st.active) || activeDocId;
    for (const doc of docs) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "view-tab" + (doc.id === active ? " active" : "");
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", doc.id === active ? "true" : "false");
      btn.dataset.docId = doc.id;
      const label = document.createElement("span");
      label.textContent = (doc.dirty ? "• " : "") + (doc.title || doc.yaml);
      btn.appendChild(label);
      const close = document.createElement("button");
      close.type = "button";
      close.className = "view-tab-close";
      close.title = "Close file";
      close.setAttribute("aria-label", `Close ${doc.title || doc.yaml}`);
      close.textContent = "×";
      close.addEventListener("click", (ev) => {
        ev.stopPropagation();
        closeDocument(doc.id).catch((err) =>
          setStatus(String(err.message || err))
        );
      });
      btn.appendChild(close);
      btn.addEventListener("click", () => {
        activateDocument(doc.id).catch((err) =>
          setStatus(String(err.message || err))
        );
      });
      bar.appendChild(btn);
    }
  }

  async function setCanvasLocation(id, { resetDepth = true } = {}) {
    if (!id) return;
    if (resetDepth) depthLevel = 1;
    locationId = id;
    if (activeDocId) {
      docViews[activeDocId] = { locationId: id, depthLevel };
    }
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
      if (n.kind === "element" && !showElectrical) return false;
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
      if (node.kind === "element" && !showElectrical) continue;
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
    if (!showElectrical) {
      setElectrical(true);
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
    if (activeDocId) {
      docViews[activeDocId] = { locationId, depthLevel };
    }
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

  syncElectricalUi();

  document.getElementById("btn-electrical")?.addEventListener("click", () => {
    setElectrical(!showElectrical);
  });

  document.getElementById("btn-auto-force")?.addEventListener("click", () => {
    runAutoLayout().catch((err) => setStatus(String(err.message || err)));
  });

  document.getElementById("btn-undo")?.addEventListener("click", () => {
    undoLayout().catch((err) => setStatus(String(err.message || err)));
  });
  document.getElementById("btn-redo")?.addEventListener("click", () => {
    redoLayout().catch((err) => setStatus(String(err.message || err)));
  });
  document.getElementById("btn-layout-reset")?.addEventListener("click", () => {
    resetLayout().catch((err) => setStatus(String(err.message || err)));
  });

  document.addEventListener("keydown", (ev) => {
    const tag = (ev.target && ev.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    const mod = ev.ctrlKey || ev.metaKey;
    if (!mod) return;
    const key = ev.key.toLowerCase();
    if (key === "s") {
      ev.preventDefault();
      saveDocument().catch((err) => setStatus(String(err.message || err)));
      return;
    }
    if (key === "o") {
      ev.preventDefault();
      fileOpen().catch((err) => setStatus(String(err.message || err)));
      return;
    }
    if (key === "z" && !ev.shiftKey) {
      ev.preventDefault();
      undoLayout().catch((err) => setStatus(String(err.message || err)));
    } else if (key === "y" || (key === "z" && ev.shiftKey)) {
      ev.preventDefault();
      redoLayout().catch((err) => setStatus(String(err.message || err)));
    }
  });

  document.getElementById("btn-open")?.addEventListener("click", () => {
    fileOpen().catch((err) => setStatus(String(err.message || err)));
  });

  document.getElementById("btn-save")?.addEventListener("click", async () => {
    try {
      await saveDocument();
    } catch (err) {
      setStatus(String(err.message || err));
    }
  });

  function setSidePanelCollapsed(which, collapsed) {
    const tree = document.getElementById("nav-tree");
    const side = document.getElementById("side-panel");
    const expandOutline = document.getElementById("btn-expand-outline");
    const expandInspector = document.getElementById("btn-expand-inspector");
    const collapseOutline = document.getElementById("btn-collapse-outline");
    const collapseInspector = document.getElementById("btn-collapse-inspector");
    if (which === "outline" && tree) {
      tree.classList.toggle("collapsed", collapsed);
      if (expandOutline) expandOutline.classList.toggle("hidden", !collapsed);
      if (collapseOutline) collapseOutline.setAttribute("aria-expanded", collapsed ? "false" : "true");
      try {
        sessionStorage.setItem("housewire-outline-panel", collapsed ? "0" : "1");
      } catch {
        /* ignore */
      }
    }
    if (which === "inspector" && side) {
      side.classList.toggle("collapsed", collapsed);
      if (expandInspector) expandInspector.classList.toggle("hidden", !collapsed);
      if (collapseInspector) {
        collapseInspector.setAttribute("aria-expanded", collapsed ? "false" : "true");
      }
      try {
        sessionStorage.setItem("housewire-inspector-panel", collapsed ? "0" : "1");
      } catch {
        /* ignore */
      }
    }
  }

  document.getElementById("btn-collapse-outline")?.addEventListener("click", () => {
    setSidePanelCollapsed("outline", true);
  });
  document.getElementById("btn-expand-outline")?.addEventListener("click", () => {
    setSidePanelCollapsed("outline", false);
  });
  document.getElementById("btn-collapse-inspector")?.addEventListener("click", () => {
    setSidePanelCollapsed("inspector", true);
  });
  document.getElementById("btn-expand-inspector")?.addEventListener("click", () => {
    setSidePanelCollapsed("inspector", false);
  });

  try {
    if (sessionStorage.getItem("housewire-outline-panel") === "0") {
      setSidePanelCollapsed("outline", true);
    }
    if (sessionStorage.getItem("housewire-inspector-panel") === "0") {
      setSidePanelCollapsed("inspector", true);
    }
  } catch {
    /* ignore */
  }

  document.querySelectorAll(".menu-btn").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const host = btn.closest(".menu");
      const name = host && host.getAttribute("data-menu");
      if (name) toggleMenu(name);
    });
  });

  // After a click-open, hovering another top-level menu switches to it.
  document.querySelectorAll(".menubar .menu").forEach((host) => {
    host.addEventListener("mouseenter", () => {
      if (!menuBarArmed && !anyMenuOpen()) return;
      const name = host.getAttribute("data-menu");
      if (name && !isMenuOpen(name)) openMenu(name);
    });
  });

  const menuFile = document.getElementById("menu-file");
  if (menuFile) {
    menuFile.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const item = ev.target.closest("[data-file-action]");
      if (!item || item.disabled) return;
      closeAllMenus();
      handleFileAction(item.getAttribute("data-file-action")).catch((err) =>
        setStatus(String(err.message || err))
      );
    });
  }

  const menuEdit = document.getElementById("menu-edit");
  if (menuEdit) {
    menuEdit.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const insertItem = ev.target.closest("[data-insert-action]");
      if (insertItem) {
        if (insertItem.disabled) return;
        closeAllMenus();
        openInsertModal(insertItem.getAttribute("data-insert-action"));
        return;
      }
      const subTrigger = ev.target.closest(".menu-submenu-trigger");
      if (subTrigger) {
        ev.preventDefault();
        const host = subTrigger.closest(".menu-item-submenu");
        const flyout = host && host.querySelector(".menu-flyout");
        if (!flyout) return;
        const open = flyout.classList.contains("hidden");
        document.querySelectorAll(".menu-flyout").forEach((el) => {
          el.classList.add("hidden");
        });
        document.querySelectorAll(".menu-item-submenu").forEach((el) => {
          el.classList.remove("is-open");
        });
        document.querySelectorAll(".menu-submenu-trigger").forEach((btn) => {
          btn.setAttribute("aria-expanded", "false");
        });
        if (open) {
          flyout.classList.remove("hidden");
          host.classList.add("is-open");
          subTrigger.setAttribute("aria-expanded", "true");
        }
        return;
      }
      const item = ev.target.closest("[data-edit-action]");
      if (!item || item.disabled) return;
      const action = item.getAttribute("data-edit-action");
      closeAllMenus();
      if (action === "undo") {
        undoLayout().catch((err) => setStatus(String(err.message || err)));
      } else if (action === "redo") {
        redoLayout().catch((err) => setStatus(String(err.message || err)));
      } else if (action === "reset") {
        resetLayout().catch((err) => setStatus(String(err.message || err)));
      } else if (action === "auto-layout") {
        runAutoLayout().catch((err) => setStatus(String(err.message || err)));
      }
    });

    // Hover opens Insert flyout while Edit menu is open.
    const insertHost = menuEdit.querySelector(".menu-item-submenu");
    if (insertHost) {
      insertHost.addEventListener("mouseenter", () => {
        const flyout = insertHost.querySelector(".menu-flyout");
        const trigger = insertHost.querySelector(".menu-submenu-trigger");
        if (!flyout || !trigger) return;
        flyout.classList.remove("hidden");
        insertHost.classList.add("is-open");
        trigger.setAttribute("aria-expanded", "true");
      });
    }
  }

  const menuView = document.getElementById("menu-view");
  if (menuView) {
    menuView.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const item = ev.target.closest("[data-view-action]");
      if (!item || item.disabled) return;
      const action = item.getAttribute("data-view-action");
      if (action === "electrical") {
        closeAllMenus();
        setElectrical(!showElectrical);
        return;
      }
      closeAllMenus();
      if (action === "zoom-in") zoomIn();
      else if (action === "zoom-out") zoomOut();
      else if (action === "fit") fitView();
      else if (action === "depth-in") {
        setDepth(depthLevel + 1).catch((err) =>
          setStatus(String(err.message || err))
        );
      } else if (action === "depth-out") {
        setDepth(depthLevel - 1).catch((err) =>
          setStatus(String(err.message || err))
        );
      }
    });
  }

  document.addEventListener("click", (ev) => {
    if (ev.target && ev.target.closest && ev.target.closest(".menu")) return;
    closeAllMenus();
  });

  document.getElementById("btn-zoom-in")?.addEventListener("click", () => {
    zoomIn();
  });
  document.getElementById("btn-zoom-out")?.addEventListener("click", () => {
    zoomOut();
  });
  document.getElementById("btn-zoom-reset")?.addEventListener("click", () => {
    fitView();
  });
  document.getElementById("status-zoom-in")?.addEventListener("click", () => {
    zoomIn();
  });
  document.getElementById("status-zoom-out")?.addEventListener("click", () => {
    zoomOut();
  });

  const zoomSlider = document.getElementById("zoom-slider");
  if (zoomSlider) {
    zoomSlider.addEventListener("input", () => {
      const pct = Number(zoomSlider.value);
      if (!Number.isFinite(pct)) return;
      const rect = viewport.getBoundingClientRect();
      setScale(pct / 100, {
        anchorClientX: rect.left + rect.width / 2,
        anchorClientY: rect.top + rect.height / 2,
      });
    });
  }

  document.getElementById("btn-depth-in")?.addEventListener("click", () => {
    setDepth(depthLevel + 1).catch((err) => setStatus(String(err.message || err)));
  });
  document.getElementById("btn-depth-out")?.addEventListener("click", () => {
    setDepth(depthLevel - 1).catch((err) => setStatus(String(err.message || err)));
  });

  viewport.addEventListener("pointerdown", (ev) => {
    if (drag || marquee) return;
    if (ev.target !== svg && ev.target !== viewport) return;
    if (ev.button === 0 && ev.shiftKey) {
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
      return;
    }
    if (ev.button === 1 || ev.button === 0) {
      ev.preventDefault();
      panDrag = { x: ev.clientX, y: ev.clientY, panX, panY };
      viewport.classList.add("panning");
      svg.setPointerCapture(ev.pointerId);
    }
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
      setScale(scale * factor, {
        anchorClientX: ev.clientX,
        anchorClientY: ev.clientY,
      });
    },
    { passive: false }
  );

  const INSERT_TITLES = {
    socket: "Insert socket",
    lamp: "Insert lamp",
    feed: "Insert feed",
  };

  function insertMsg(text, isError) {
    const el = document.getElementById("insert-msg");
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("is-error", Boolean(isError && text));
  }

  function closeInsertModal() {
    const modal = document.getElementById("insert-modal");
    if (!modal) return;
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    document.removeEventListener("keydown", onInsertModalKey);
  }

  function onInsertModalKey(ev) {
    if (ev.key === "Escape") {
      ev.preventDefault();
      closeInsertModal();
    }
  }

  function openInsertModal(kind) {
    const modal = document.getElementById("insert-modal");
    const titleEl = document.getElementById("insert-modal-title");
    if (!modal || !INSERT_TITLES[kind]) return;
    if (titleEl) titleEl.textContent = INSERT_TITLES[kind];
    for (const id of ["socket", "lamp", "feed"]) {
      const form = document.getElementById(`form-${id}`);
      if (form) form.classList.toggle("hidden", id !== kind);
    }
    insertMsg("");
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    document.addEventListener("keydown", onInsertModalKey);
    const form = document.getElementById(`form-${kind}`);
    const first = form && form.querySelector("input:not([type=hidden])");
    setTimeout(() => first && first.focus(), 0);
  }

  document.querySelectorAll("[data-insert-dismiss]").forEach((el) => {
    el.addEventListener("click", () => closeInsertModal());
  });

  async function submitInsert(kind, form) {
    if (!locationId) return;
    const data = Object.fromEntries(new FormData(form).entries());
    const body = { location_id: locationId, depth: depthLevel, ...data };
    for (const key of Object.keys(body)) {
      if (body[key] === "") delete body[key];
    }
    insertMsg("…");
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
      setStatus(`${kind} added · unsaved`);
      scheduleStatusRefresh();
      form.reset();
      if (selectedId) {
        const detail = await api(
          `/api/place?location=${encodeURIComponent(locationId)}&id=${encodeURIComponent(selectedId)}`
        );
        prefillInsertForms(detail);
      }
      closeInsertModal();
    } catch (err) {
      insertMsg(String(err.message || err), true);
    }
  }

  document.getElementById("form-socket")?.addEventListener("submit", (ev) => {
    ev.preventDefault();
    submitInsert("socket", ev.target);
  });
  document.getElementById("form-lamp")?.addEventListener("submit", (ev) => {
    ev.preventDefault();
    submitInsert("lamp", ev.target);
  });
  document.getElementById("form-feed")?.addEventListener("submit", (ev) => {
    ev.preventDefault();
    submitInsert("feed", ev.target);
  });

  loadLocations().catch((err) => setStatus(String(err.message || err)));
})();
