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
  let canUndo = false;
  let canRedo = false;
  let canReset = false;
  let showElectrical = false;
  let outlineNodes = [];
  let canvasLocations = [];
  let collapsedOutline = new Set();
  let outlineCollapseReady = false;
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
   * When ``opts.input`` is set, Enter confirms the primary button and the
   * caller should read ``opts.input``'s field via ``promptText``.
   * @param {{
   *   title?: string,
   *   message?: string,
   *   input?: { label?: string, value?: string, placeholder?: string },
   *   buttons?: { id: string, label: string, primary?: boolean, danger?: boolean }[]
   * }} opts
   */
  function appDialog(opts) {
    const modal = document.getElementById("app-modal");
    const titleEl = document.getElementById("app-modal-title");
    const msgEl = document.getElementById("app-modal-message");
    const actions = document.getElementById("app-modal-actions");
    const inputWrap = document.getElementById("app-modal-input-wrap");
    const inputLabel = document.getElementById("app-modal-input-label");
    const inputEl = document.getElementById("app-modal-input");
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
      const wantsInput = Boolean(opts.input);
      if (inputWrap && inputEl) {
        if (wantsInput) {
          inputWrap.classList.remove("hidden");
          if (inputLabel) {
            inputLabel.textContent = opts.input.label || "Path";
          }
          inputEl.value = opts.input.value || "";
          inputEl.placeholder = opts.input.placeholder || "";
        } else {
          inputWrap.classList.add("hidden");
          inputEl.value = "";
        }
      }
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
          if (wantsInput && ev.target === inputEl) {
            ev.preventDefault();
            const primary =
              buttons.find((b) => b.primary) || buttons[buttons.length - 1];
            if (primary) finish(primary.id);
            return;
          }
          if (!wantsInput) {
            const primary =
              buttons.find((b) => b.primary) || buttons[buttons.length - 1];
            if (primary) {
              ev.preventDefault();
              finish(primary.id);
            }
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

      setTimeout(() => {
        if (wantsInput && inputEl) {
          inputEl.focus();
          inputEl.select();
          return;
        }
        const focusBtn =
          actions.querySelector("button.primary") ||
          actions.querySelector("button:last-child");
        if (focusBtn) focusBtn.focus();
      }, 0);
    });
  }

  /**
   * In-app text prompt (no browser dialogs). Returns trimmed string or null.
   * @param {{
   *   title?: string,
   *   message?: string,
   *   label?: string,
   *   value?: string,
   *   placeholder?: string,
   *   okLabel?: string
   * }} opts
   */
  async function promptText(opts) {
    const inputEl = document.getElementById("app-modal-input");
    const choice = await appDialog({
      title: opts.title || "HouseWire",
      message: opts.message || "",
      input: {
        label: opts.label || "Path",
        value: opts.value || "",
        placeholder: opts.placeholder || "",
      },
      buttons: [
        { id: "cancel", label: "Cancel" },
        { id: "ok", label: opts.okLabel || "OK", primary: true },
      ],
    });
    if (choice !== "ok" || !inputEl) return null;
    const value = String(inputEl.value || "").trim();
    return value || null;
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

  function updateHistoryButtons() {
    for (const id of ["btn-undo", "menu-undo"]) {
      const el = document.getElementById(id);
      if (el) el.disabled = !canUndo;
    }
    for (const id of ["btn-redo", "menu-redo"]) {
      const el = document.getElementById(id);
      if (el) el.disabled = !canRedo;
    }
    for (const id of ["btn-layout-reset", "menu-layout-reset"]) {
      const el = document.getElementById(id);
      if (el) el.disabled = !canReset;
    }
  }

  function applyEditFlags(meta) {
    if (!meta) return;
    if (meta.can_undo != null) canUndo = Boolean(meta.can_undo);
    if (meta.can_redo != null) canRedo = Boolean(meta.can_redo);
    if (meta.can_reset != null) canReset = Boolean(meta.can_reset);
    updateHistoryButtons();
    if (typeof meta.dirty === "boolean") {
      dirtyLocal = meta.dirty;
      updateFileMenuState({ dirty: dirtyLocal });
    }
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
      canUndo = false;
      canRedo = false;
      canReset = false;
      activeDocId = null;
      updateHistoryButtons();
    }
    const serverDirty = ((st && st.dirty) || []).length > 0;
    dirtyLocal = hasDocument ? serverDirty : false;
    applyEditFlags(st);
    updateFileMenuState({ dirty: dirtyLocal });
    renderDocTabs(st);
    return st;
  }

  async function applyEditGraph(res, status) {
    if (res && res.graph) {
      graph = res.graph;
      depthLevel = graph.depth || depthLevel;
      maxDepth = graph.max_depth || maxDepth;
      render();
    }
    applyEditFlags(res);
    await syncInspectorFromSelection();
    if (status) setStatus(status);
    scheduleStatusRefresh();
  }

  async function undoEdit() {
    if (!locationId || !canUndo) return;
    const res = await api("/api/edit/undo", {
      method: "POST",
      body: JSON.stringify({ location_id: locationId, depth: depthLevel }),
    });
    if (!res.changed) {
      applyEditFlags(res);
      return;
    }
    await applyEditGraph(res, "undo");
  }

  async function redoEdit() {
    if (!locationId || !canRedo) return;
    const res = await api("/api/edit/redo", {
      method: "POST",
      body: JSON.stringify({ location_id: locationId, depth: depthLevel }),
    });
    if (!res.changed) {
      applyEditFlags(res);
      return;
    }
    await applyEditGraph(res, "redo");
  }

  async function resetEdits() {
    if (!locationId || !canReset) return;
    const res = await api("/api/edit/reset", {
      method: "POST",
      body: JSON.stringify({ location_id: locationId, depth: depthLevel }),
    });
    if (!res.changed) {
      applyEditFlags(res);
      return;
    }
    await applyEditGraph(res, "reset");
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

  /**
   * B/F bocas are never drawn on the geometric center of the place (even a
   * lone B1-1), so the tube/marker stay clear of the middle and of typical
   * side openings. Bias toward local NW (smaller x/y).
   */
  const PLANE_CENTER_BIAS = 18;

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
    let x = planeCellCenter(w, cols, plane.col, PLANE_R);
    let y = planeCellCenter(h, rows, plane.row, PLANE_R);
    const margin = PLANE_R + 5;
    // Always offset a cell that would sit on the place center.
    if (Math.abs(x - w / 2) < 1e-6) {
      x = Math.max(margin, w / 2 - PLANE_CENTER_BIAS);
    }
    if (Math.abs(y - h / 2) < 1e-6) {
      y = Math.max(margin, h / 2 - PLANE_CENTER_BIAS);
    }
    return { x, y };
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

  /**
   * Contour mouth / true boca for a conduit end.
   * Side openings sit on the border. B/F plane cells are the interior boca
   * (tube continues into the place); contour crossing uses
   * ``planeContourEntryAbs`` so the entry can be nudged off N1/S1/….
   */
  function openingMouthAbs(node, openingId, face, byId) {
    return openingAnchorAbs(node, openingId, face, byId);
  }

  function isPlaneOpeningId(openingId) {
    const plane = parsePlaneOpening(openingId);
    return Boolean(plane && (plane.face === "B" || plane.face === "F"));
  }

  /** Absolute positions of side openings on one contour face. */
  function sideOpeningAbsOnFace(node, face, byId) {
    const f = String(face || "").toUpperCase();
    /** @type {{x:number,y:number}[]} */
    const out = [];
    for (const o of node.openings || []) {
      const id = o && (o.id != null ? o.id : o);
      const side = parseSideOpening(id);
      if (!side || side.face !== f) continue;
      out.push(openingAnchorAbs(node, id, f, byId));
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
    const a = absXY(node, byId);
    const w = nodeW(node);
    const h = nodeH(node);
    const alongH = f === "N" || f === "S";
    const clampX = (x) => Math.min(a.x + w - 8, Math.max(a.x + 8, x));
    const clampY = (y) => Math.min(a.y + h - 8, Math.max(a.y + 8, y));
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
    const local = planeAnchorLocal(node, openingId, f);
    const a = absXY(node, byId);
    const w = nodeW(node);
    const h = nodeH(node);
    /** @type {{x:number,y:number}} */
    let mouth;
    if (approach === "N") mouth = { x: a.x + local.x, y: a.y };
    else if (approach === "S") mouth = { x: a.x + local.x, y: a.y + h };
    else if (approach === "W") mouth = { x: a.x, y: a.y + local.y };
    else if (approach === "E") mouth = { x: a.x + w, y: a.y + local.y };
    else mouth = { x: a.x + local.x, y: a.y + local.y };
    return nudgeOffSideOpenings(node, approach, mouth, byId);
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
    /** @type {{x:number,y:number,w:number,h:number}[]} */
    const rects = [];
    for (const n of Object.values(byId || {})) {
      if (!n) continue;
      const a = absXY(n, byId);
      rects.push({ x: a.x, y: a.y, w: nodeW(n), h: nodeH(n) });
    }
    return rects;
  }

  /**
   * Orthogonal route points from p1 to p2. When ``occupied`` is set, prefer
   * candidates that avoid colinear overlap (and lightly avoid crossings).
   * ``obstacles`` are place rects to go around (C / outer rails).
   */
  function orthoRoute(p1, p2, fromFace, toFace, occupied, obstacles, stayBounds, hugRects) {
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
      obstacles,
      [x1, y1],
      [x2, y2],
      stayBounds,
      hugRects
    );
    for (const p of mid) {
      pts.push(p);
    }
    if (bx !== x2 || by !== y2) {
      pts.push([x2, y2]);
    }
    return cleanOrthoPoly(pts);
  }

  function orthoPathD(p1, p2, fromFace, toFace, occupied, obstacles, stayBounds, hugRects) {
    return pointsToPathD(
      orthoRoute(p1, p2, fromFace, toFace, occupied, obstacles, stayBounds, hugRects)
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
  function stripOutAndBack(pts) {
    if (!pts || pts.length < 3) {
      return pts ? pts.map((p) => [p[0], p[1]]) : [];
    }
    /** @type {number[][]} */
    let out = pts.map((p) => [p[0], p[1]]);
    let guard = 0;
    while (guard++ < 64) {
      out = cleanOrthoPoly(out);
      let changed = false;
      for (let i = 2; i < out.length; i++) {
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
    hugRects
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
        // end is already last of midThroughEnd; append opening if distinct
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

    // Tight clearance rails along place walls (same scale as mouth stubs).
    if (hugRects && hugRects.length) {
      const c = WALL_CLEARANCE;
      for (const r of hugRects) {
        push([[r.x - c, ay], [r.x - c, by]]);
        push([[r.x + r.w + c, ay], [r.x + r.w + c, by]]);
        push([[ax, r.y - c], [bx, r.y - c]]);
        push([[ax, r.y + r.h + c], [bx, r.y + r.h + c]]);
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
      // Use stub-scale pad (not a wide detour) so the open side of a C
      // matches the mouth exit jog.
      const obsOffs = needLanes ? [0, lane, -lane, 2 * lane, -2 * lane] : [0];
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
    let bestObstacle = Infinity;
    let bestOutside = Infinity;
    let bestBends = Infinity;
    let bestHug = Infinity;
    let bestEntry = Infinity;
    let bestConflict = Infinity;
    let bestLen = Infinity;
    const eps = overlapEps ?? 6;
    for (const pts of raw) {
      // Include face stubs in bend count: exit-stub + horizontal-first L is
      // down→right→down (2 bends), while vertical-first merges into 1 bend.
      const full = scorePoly(pts);
      const bends = polyBends(full);
      const conflict = pathConflictCost(full, occupied, eps);
      const obstacle = pathObstacleCost(full, obstacles);
      const outside = pathOutsideBoundsCost(full, stayBounds);
      const hug = pathBorderHugCost(full, hugRects);
      const entry = pathEntryExcessCost(full, toFace);
      const len = polyLength(full);
      // Lexicographic: clear boxes, stay in parent, fewest bends first
      // (avoid staircases), then soft wall/entry preference.
      if (
        obstacle < bestObstacle - 1e-9 ||
        (Math.abs(obstacle - bestObstacle) < 1e-9 &&
          outside < bestOutside - 1e-9) ||
        (Math.abs(obstacle - bestObstacle) < 1e-9 &&
          Math.abs(outside - bestOutside) < 1e-9 &&
          bends < bestBends) ||
        (Math.abs(obstacle - bestObstacle) < 1e-9 &&
          Math.abs(outside - bestOutside) < 1e-9 &&
          bends === bestBends &&
          hug < bestHug - 1e-9) ||
        (Math.abs(obstacle - bestObstacle) < 1e-9 &&
          Math.abs(outside - bestOutside) < 1e-9 &&
          bends === bestBends &&
          Math.abs(hug - bestHug) < 1e-9 &&
          entry < bestEntry - 1e-9) ||
        (Math.abs(obstacle - bestObstacle) < 1e-9 &&
          Math.abs(outside - bestOutside) < 1e-9 &&
          bends === bestBends &&
          Math.abs(hug - bestHug) < 1e-9 &&
          Math.abs(entry - bestEntry) < 1e-9 &&
          conflict < bestConflict - 1e-9) ||
        (Math.abs(obstacle - bestObstacle) < 1e-9 &&
          Math.abs(outside - bestOutside) < 1e-9 &&
          bends === bestBends &&
          Math.abs(hug - bestHug) < 1e-9 &&
          Math.abs(entry - bestEntry) < 1e-9 &&
          Math.abs(conflict - bestConflict) < 1e-9 &&
          len < bestLen)
      ) {
        best = pts;
        bestObstacle = obstacle;
        bestOutside = outside;
        bestBends = bends;
        bestHug = hug;
        bestEntry = entry;
        bestConflict = conflict;
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
    const fromPlane = isPlaneOpeningId(edge.from_opening);
    const toPlane = isPlaneOpeningId(edge.to_opening);
    // Side mouths on the border; B/F mouths are the interior plane cell (boca).
    const p1 = openingMouthAbs(a, edge.from_opening, edge.from_opening?.[0], byId);
    const p2 = openingMouthAbs(b, edge.to_opening, edge.to_opening?.[0], byId);
    // Allow the route to enter leaves whose end is a B/F boca.
    /** @type {string[]} */
    const exclude = [];
    if (fromPlane) exclude.push(a.id);
    if (toPlane) exclude.push(b.id);
    const obstacles = placeObstacles(byId, exclude);
    const hugRects = placeBorderRects(byId);
    /** @type {{x:number,y:number,w:number,h:number}|null} */
    let stayBounds = null;
    if (a.parent && a.parent === b.parent) {
      const parent = byId[a.parent];
      if (parent) {
        const pa = absXY(parent, byId);
        stayBounds = {
          x: pa.x + PAD,
          y: pa.y + HEADER,
          w: Math.max(4, nodeW(parent) - 2 * PAD),
          h: Math.max(4, nodeH(parent) - HEADER - PAD),
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
        hugRects
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
        hugRects
      );
      chain = chain
        ? mergeOrthoPolys(chain, part)
        : part.map((p) => [p[0], p[1]]);
    };
    if (fromPlane || toPlane) {
      // Cross the contour at a nudged entry so B-approach does not sit on N1.
      let cur = p1;
      let curFace = fromFace;
      if (fromPlane) {
        const entry = planeContourEntryAbs(
          a,
          edge.from_opening,
          edge.from_opening?.[0],
          byId
        );
        appendInside(p1, entry);
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
        appendInside(entry, p2);
      } else {
        append(cur, p2, curFace, toFace);
      }
    } else {
      append(p1, p2, fromFace, toFace);
    }
    const pts = stripOutAndBack(
      chain || [
        [p1.x, p1.y],
        [p2.x, p2.y],
      ]
    );
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
  const STRAND_WIDTH = 2.5;
  /** Clear gap between strand strokes (equal to stroke → one strand of air). */
  const LANE_GAP = STRAND_WIDTH;
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

  /** Local (element-space) anchor for a terminal cell id. */
  function terminalCellAnchorLocal(elem, cellId) {
    const w = elem.w ?? ELEM_W;
    const h = elem.h ?? ELEM_H;
    const side = parseSideOpening(cellId);
    const face = (side?.face || String(cellId || "?")[0] || "?").toUpperCase();
    const index = side?.index || 1;
    const raw = elem.terminal_grid && elem.terminal_grid[face];
    let n = index;
    if (Array.isArray(raw) && raw.length >= 1) {
      n = Math.max(1, Number(raw[0]) || 1);
      if (raw.length >= 2) {
        n = Math.max(n, (Number(raw[0]) || 1) * (Number(raw[1]) || 1));
      }
    }
    n = Math.max(n, index);
    const t = index / (n + 1);
    if (face === "N") return { x: t * w, y: 0, face };
    if (face === "S") return { x: t * w, y: h, face };
    if (face === "W") return { x: 0, y: t * h, face };
    if (face === "E") return { x: w, y: t * h, face };
    return { x: w / 2, y: h / 2, face: "?" };
  }

  /** Side opening-style cell on an element (``N1``, ``S2``, …). */
  function terminalCellAnchor(elem, cellId, placeById) {
    const p = elementAbsXY(elem, placeById);
    const local = terminalCellAnchorLocal(elem, cellId);
    return { x: p.x + local.x, y: p.y + local.y, face: local.face };
  }

  function pickPinCell(elem, pin, toward, placeById) {
    if (!pin || !elem || !elem.terminal_pins) return null;
    const cells =
      elem.terminal_pins[pin] || elem.terminal_pins[String(pin)] || null;
    if (!cells || !cells.length) return null;
    if (cells.length === 1) return cells[0];
    const face = elementAttachFace(elem, toward, placeById);
    const match = cells.find(
      (c) => String(c || "")[0]?.toUpperCase() === face
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

  /**
   * Attach for a connection pin when ``terminal_grid`` is known; otherwise
   * fall back to fanned mid-face slots. Returns ``{x,y,face}``.
   */
  function resolveElementAttach(
    elem,
    pin,
    toward,
    placeById,
    slot = 0,
    slotCount = 1
  ) {
    const cell = pickPinCell(elem, pin, toward, placeById);
    if (cell) return terminalCellAnchor(elem, cell, placeById);
    const pt = elementAttachPoint(elem, toward, placeById, slot, slotCount);
    const face = elementAttachFace(elem, toward, placeById);
    return { x: pt.x, y: pt.y, face };
  }

  const INBOX_STUB = 14;
  /** Keep offset spine / inbox mids this far outside the element face (px). */
  const ELEMENT_FACE_CLEARANCE = 8;
  /** Extra stroke beyond the tube fill for the high-contrast rim. */
  const OUTLINE_EXTRA = 0.8;

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
      const bends = orthoBendCount([
        [fromPt.x, fromPt.y],
        ...mid,
        [toPt.x, toPt.y],
      ]);
      const score = pref * 10 + bends + faceHug * 80;
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

  /** High-contrast rim for a fill color (light on dark, dark on light). */
  function contrastOutlineCss(fillCss) {
    const h = String(fillCss || "").replace("#", "");
    if (h.length !== 6) return "#ffffff";
    const r = parseInt(h.slice(0, 2), 16) / 255;
    const g = parseInt(h.slice(2, 4), 16) / 255;
    const b = parseInt(h.slice(4, 6), 16) / 255;
    const chan = (c) =>
      c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    const lum = 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b);
    return lum < 0.45 ? "#ffffff" : "#0d1117";
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
   * Global terminal slots (per pin cell, or face when no pin) and lane indices
   * (per route). Fan along a face only when several strands share one terminal.
   */
  function buildCableLayout(cableEdges, elemById, placeById) {
    /** @type {Map<string, {key:string, wi:number, end:string}[]>} */
    const byTerminal = new Map();
    /** @type {Map<string, {key:string, wi:number}[]>} */
    const byRoute = new Map();
    /** @type {Map<string, string[]>} */
    const jacketsByRoute = new Map();

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
          const cell = pickPinCell(elem, pin, toward, placeById);
          // Slot-fan only within the same terminal cell (or mid-face when no pin).
          const tk = cell
            ? `${elem.id}|cell:${cell}`
            : `${elem.id}|face:${elementAttachFace(elem, toward, placeById)}`;
          if (!byTerminal.has(tk)) byTerminal.set(tk, []);
          byTerminal.get(tk).push({ key, wi, end });
        }
        const rk = cableRouteKey(edge, elemById);
        if (!byRoute.has(rk)) byRoute.set(rk, []);
        byRoute.get(rk).push({
          key,
          wi,
          ax: attFrom.x,
          ay: attFrom.y,
          bx: attTo.x,
          by: attTo.y,
        });
      }
      const rk = cableRouteKey(edge, elemById);
      if (!jacketsByRoute.has(rk)) jacketsByRoute.set(rk, []);
      if (!jacketsByRoute.get(rk).includes(key)) {
        jacketsByRoute.get(rk).push(key);
      }
    }

    /** @type {Map<string, {slot:number, count:number}>} */
    const terminalMap = new Map();
    for (const [, list] of byTerminal) {
      list.sort((u, v) =>
        u.key === v.key ? u.wi - v.wi : u.key < v.key ? -1 : 1
      );
      const count = list.length;
      // One strand on this terminal → no Z fan (slotCount 1).
      list.forEach((item, slot) => {
        terminalMap.set(`${item.key}|${item.wi}|${item.end}`, {
          slot: count > 1 ? slot : 0,
          count: count > 1 ? count : 1,
        });
      });
    }

    /** @type {Map<string, {index:number, count:number}>} */
    const laneMap = new Map();
    for (const [, list] of byRoute) {
      // Keep strands of the same cable consecutive, then order cables by
      // pin geometry so jackets wrap a contiguous lane span.
      /** @type {Map<string, typeof list>} */
      const byCable = new Map();
      for (const it of list) {
        if (!byCable.has(it.key)) byCable.set(it.key, []);
        byCable.get(it.key).push(it);
      }
      const cableKeys = [...byCable.keys()];
      const cableScore = (key) => {
        const members = byCable.get(key) || [];
        const xs = members.map((it) => (it.ax + it.bx) / 2);
        const ys = members.map((it) => (it.ay + it.by) / 2);
        return {
          x: xs.reduce((a, b) => a + b, 0) / Math.max(1, xs.length),
          y: ys.reduce((a, b) => a + b, 0) / Math.max(1, ys.length),
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
      for (const key of cableKeys) {
        const members = byCable.get(key) || [];
        members.sort((u, v) => u.wi - v.wi);
        ordered.push(...members);
      }
      const count = ordered.length;
      ordered.forEach((item, index) => {
        laneMap.set(`${item.key}|${item.wi}`, { index, count });
      });
    }

    /** @type {Map<string, {index:number, count:number}>} */
    const jacketMap = new Map();
    for (const [, keys] of jacketsByRoute) {
      keys.sort();
      const count = keys.length;
      keys.forEach((key, index) => {
        jacketMap.set(key, { index, count });
      });
    }

    return {
      terminal(edge, wi, end) {
        return (
          terminalMap.get(`${cableEdgeKey(edge)}|${wi}|${end}`) || {
            slot: 0,
            count: 1,
          }
        );
      },
      lane(edge, wi) {
        return (
          laneMap.get(`${cableEdgeKey(edge)}|${wi}`) || { index: 0, count: 1 }
        );
      },
      jacket(edge) {
        return jacketMap.get(cableEdgeKey(edge)) || { index: 0, count: 1 };
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
    const along =
      (out[0][0] - p.x) * fo.x + (out[0][1] - p.y) * fo.y;
    if (along < want) {
      const need = want - along;
      out[0][0] += fo.x * need;
      out[0][1] += fo.y * need;
    }
    // Lift can make the first segment diagonal — openings/spines stay Manhattan.
    return ensureOrthoPoly(out);
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
  function pinToLanePts(pin, face, lanePt, slot = 0, slotCount = 1) {
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

    if (multiCable && (fo.x || fo.y)) {
      // V leg touches the pin: pin → tip (one short diagonal).
      const nx = -fo.y;
      const ny = fo.x;
      const mid = (nSlots - 1) / 2;
      const fanLat = (s - mid) * Math.max(8, STRAND_WIDTH + LANE_GAP);
      const tip = {
        x: p.x + fo.x * 12 + nx * fanLat,
        y: p.y + fo.y * 12 + ny * fanLat,
      };
      // Stop at the tip — Manhattan bridge to the spine is done by the caller
      // so we never leave a diagonal gap after trimSpineAfterLead.
      return [
        [p.x, p.y],
        [tip.x, tip.y],
      ];
    }

    /** @type {number[][]} */
    const pts = [[p.x, p.y]];
    let from = p;
    if (fo.x || fo.y) {
      const along = (t.x - p.x) * fo.x + (t.y - p.y) * fo.y;
      if (along > 2) {
        const want = Math.min(6, along - 0.5);
        if (want > 1e-6) {
          const stub = stubPoint(p, fo.x, fo.y, want);
          if (Math.hypot(stub.x - p.x, stub.y - p.y) > 1e-6) {
            pts.push([stub.x, stub.y]);
            from = stub;
          }
        }
      }
    }
    if (Math.hypot(from.x - t.x, from.y - t.y) < 1e-6) return pts;
    if (Math.abs(from.x - t.x) < 1e-6 || Math.abs(from.y - t.y) < 1e-6) {
      pts.push([t.x, t.y]);
      return pts;
    }
    return orthoJoinEnd(pts, t, face);
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
    const tip = lead[lead.length - 1];
    let rest = trimSpineAfterLead(spine, tip);
    const bridge = orthoJoinEnd([tip], rest[0], face);
    let chain = mergeOrthoPolys(lead, bridge);
    chain = mergeOrthoPolys(chain, rest);
    return stripOutAndBack(stripShortZJogs(chain || []));
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
  function stripShortZJogs(pts, maxLeg = 28) {
    if (!pts || pts.length < 4) {
      return pts ? pts.map((p) => [p[0], p[1]]) : [];
    }
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
        const abx = b[0] - a[0];
        const aby = b[1] - a[1];
        const bcx = c[0] - b[0];
        const bcy = c[1] - b[1];
        const cdx = d[0] - c[0];
        const cdy = d[1] - c[1];
        if (Math.abs(abx * bcy - aby * bcx) < 1e-6) continue;
        if (Math.abs(bcx * cdy - bcy * cdx) < 1e-6) continue;
        const mid = Math.hypot(bcx, bcy);
        if (mid <= 1e-6 || mid > maxLeg) continue;
        const abH = Math.abs(aby) < 1e-6;
        const cdH = Math.abs(cdy) < 1e-6;
        const bcH = Math.abs(bcy) < 1e-6;
        if (abH !== cdH || abH === bcH) continue;
        // Collapse b-c: connect a→d via one L through a corner that skips the Z.
        const corner = abH ? [d[0], a[1]] : [a[0], d[1]];
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

  /** Exact tube geometry for a hop (same path as the conduit edge). */
  function hopTubePathD(hop) {
    const item = edgePaths.find((e) => e.edge && e.edge.id === hop.conduit);
    if (!item || !item.d) return null;
    const e = item.edge;
    if (e.from === hop.from && e.to === hop.to) return item.d;
    if (e.from === hop.to && e.to === hop.from) return reversePathD(item.d);
    return null;
  }

  /**
   * Base polylines for a cable edge.
   * @param {{fromSlot?:{slot:number,count:number}, toSlot?:{slot:number,count:number}, laneDist?:number, fromPin?:string|null, toPin?:string|null}|undefined} opts
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
    const laneDist = opts?.laneDist || 0;
    const fromPin = opts?.fromPin != null ? opts.fromPin : edge.from_pin;
    const toPin = opts?.toPin != null ? opts.toPin : edge.to_pin;
    /** Full parallel offset of a polyline (stays parallel to conduit walls). */
    const parallel = (pts) => {
      if (!pts || pts.length < 2 || Math.abs(laneDist) < 1e-9) {
        return pts ? pts.map((p) => [p[0], p[1]]) : [];
      }
      return offsetOrthoPts(pts, laneDist);
    };

    // Same box: parallel corridor between stubs; short leads to terminals.
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
      let prefer = { x: (c1.x + c2.x) / 2, y: (c1.y + c2.y) / 2 };
      if (parent) {
        const pa = absXY(parent, placeById);
        prefer = {
          x: pa.x + nodeW(parent) / 2,
          y: pa.y + nodeH(parent) / 2,
        };
      }
      const f1 = p1.face || elementAttachFace(a, c2, placeById);
      const f2 = p2.face || elementAttachFace(b, c1, placeById);
      const o1 = faceOutwardDelta(f1);
      const o2 = faceOutwardDelta(f2);
      const s1 = stubPoint(p1, o1.x, o1.y, INBOX_STUB);
      const s2 = stubPoint(p2, o2.x, o2.y, INBOX_STUB);
      const corridor = orthoPtsPrefer(s1, s2, prefer);
      const corridorOff = parallel(corridor);
      if (!corridorOff.length) return [];
      return [
        rejoinLaneEndsOrtho(
          [p1.x, p1.y],
          f1,
          corridorOff,
          [p2.x, p2.y],
          f2,
          fromSlot.slot,
          fromSlot.count,
          toSlot.slot,
          toSlot.count
        ),
      ];
    }

    const parentExclude = [a.parent, b.parent].filter(Boolean);
    const outsideObstacles = placeObstacles(placeById, parentExclude);
    const leafObstacles = placeObstacles(placeById, [], 2);

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
        const d = orthoPathD(c1, c2, null, null, occupied, outsideObstacles);
        return d
          ? pathDToSubpaths(d).map((sub) => ensureOrthoPoly(parallel(sub)))
          : [];
      }

      /** @type {number[][][]} */
      const exteriors = [];
      for (let i = 0; i < hops.length; i++) {
        const hop = hops[i];
        const pf = placeById[hop.from];
        const pt = placeById[hop.to];
        if (!pf || !pt || !hop.from_opening || !hop.to_opening) {
          const d = orthoPathD(c1, c2, null, null, occupied, outsideObstacles);
          return d
            ? pathDToSubpaths(d).map((sub) => ensureOrthoPoly(parallel(sub)))
            : [];
        }
        const tubeD = hopTubePathD(hop);
        let ext = null;
        if (tubeD) {
          ext = exteriorPathD(tubeD, leafObstacles);
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
          // Centerline exterior only — lane offset applied to the full chain.
          for (const sub of pathDToSubpaths(ext)) {
            if (sub.length >= 2) exteriors.push(sub.map((p) => [p[0], p[1]]));
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

      // Parallel offset on exterior AND on Manhattan inbox spines. Pins rejoin
      // with stub + short diagonal only (no boca→element diagonals).
      /** @type {number[][][]} */
      const exOff = [];
      for (const ext of oriented) {
        const o = parallel(ext);
        if (o && o.length >= 2) exOff.push(o);
      }

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

      /** @type {number[][]|null} */
      let chain = null;
      if (exOff.length) {
        const startJoin = exOff[0][0];
        const endJoin =
          exOff[exOff.length - 1][exOff[exOff.length - 1].length - 1];
        // Centerline inbox to the contour entry, then lane-offset the spine.
        const startTailCtr = hopEndpointTailPts(
          a,
          startPlace,
          first.from_opening,
          placeById,
          fromSlot.slot,
          fromSlot.count,
          fromPin
        );
        if (startTailCtr && startTailCtr.length >= 2) {
          // Tail runs pin→mouth (opposite the exterior's leave direction),
          // so flip the offset sign or lanes cross at the boca.
          let startOff =
            Math.abs(laneDist) < 1e-9
              ? startTailCtr.map((p) => [p[0], p[1]])
              : offsetOrthoPts(startTailCtr, -laneDist);
          if (startOff.length >= 2) {
            startOff = liftOffsetSpineFromPin(
              startOff,
              [startAtt.x, startAtt.y],
              startFace
            );
            // Never snap last→join (that paints a diagonal funnel into the
            // opening). Drop the offset mouth vertex and Manhattan-join.
            const mouthFace = routeFace(
              startPlace,
              first.from_opening,
              first.from_opening?.[0],
              placeById
            );
            if (startOff.length >= 2) startOff = startOff.slice(0, -1);
            startOff = orthoJoinEnd(startOff, startJoin, mouthFace);
            startOff = ensureManhattanNearPoint(startOff, startJoin, 48, [
              startAtt,
            ]);
            const head = pinToLanePts(
              [startAtt.x, startAtt.y],
              startFace,
              startOff[0],
              fromSlot.slot,
              fromSlot.count
            );
            chain = mergeLeadToSpine(head, startOff, startFace);
          }
        }
        if (!chain) {
          const mouthFace = routeFace(
            startPlace,
            first.from_opening,
            first.from_opening?.[0],
            placeById
          );
          chain = orthoJoinEnd(
            [
              [startAtt.x, startAtt.y],
            ],
            startJoin,
            mouthFace
          );
        }
        for (const ext of exOff) {
          chain = mergeOrthoPolys(chain, ext);
        }
        const endTailCtr = hopEndpointTailPts(
          b,
          endPlace,
          last.to_opening,
          placeById,
          toSlot.slot,
          toSlot.count,
          toPin
        );
        if (endTailCtr && endTailCtr.length >= 2) {
          let endOff =
            Math.abs(laneDist) < 1e-9
              ? endTailCtr.map((p) => [p[0], p[1]])
              : offsetOrthoPts(endTailCtr, -laneDist);
          if (endOff.length >= 2) {
            endOff = liftOffsetSpineFromPin(
              endOff,
              [endAtt.x, endAtt.y],
              endFace
            );
            const mouthFace = routeFace(
              endPlace,
              last.to_opening,
              last.to_opening?.[0],
              placeById
            );
            if (endOff.length >= 2) endOff = endOff.slice(0, -1);
            endOff = orthoJoinEnd(endOff, endJoin, mouthFace);
            endOff = ensureManhattanNearPoint(endOff, endJoin, 48, [endAtt]);
            const head = pinToLanePts(
              [endAtt.x, endAtt.y],
              endFace,
              endOff[0],
              toSlot.slot,
              toSlot.count
            );
            const endPart = mergeLeadToSpine(head, endOff, endFace);
            chain = mergeOrthoPolys(chain, endPart.slice().reverse());
          }
        } else {
          const mouthFace = routeFace(
            endPlace,
            last.to_opening,
            last.to_opening?.[0],
            placeById
          );
          const lead = orthoJoinEnd(
            [[endAtt.x, endAtt.y]],
            endJoin,
            mouthFace
          );
          chain = mergeOrthoPolys(chain, lead.slice().reverse());
        }
        if (chain) {
          chain = ensureManhattanNearPoint(chain, startJoin);
          chain = ensureManhattanNearPoint(chain, endJoin);
        }
      } else {
        const startTail = hopEndpointTailPts(
          a,
          startPlace,
          first.from_opening,
          placeById,
          fromSlot.slot,
          fromSlot.count,
          fromPin
        );
        if (startTail) {
          let startOff =
            Math.abs(laneDist) < 1e-9
              ? startTail.map((p) => [p[0], p[1]])
              : offsetOrthoPts(startTail, -laneDist);
          startOff = liftOffsetSpineFromPin(
            startOff,
            [startAtt.x, startAtt.y],
            startFace
          );
          const head = pinToLanePts(
            [startAtt.x, startAtt.y],
            startFace,
            startOff[0] || startTail[0],
            fromSlot.slot,
            fromSlot.count
          );
          chain = mergeLeadToSpine(
            head,
            startOff.length ? startOff : startTail,
            startFace
          );
        }
        const endTail = hopEndpointTailPts(
          b,
          endPlace,
          last.to_opening,
          placeById,
          toSlot.slot,
          toSlot.count,
          toPin
        );
        if (endTail) {
          let endOff =
            Math.abs(laneDist) < 1e-9
              ? endTail.map((p) => [p[0], p[1]])
              : offsetOrthoPts(endTail, -laneDist);
          endOff = liftOffsetSpineFromPin(
            endOff,
            [endAtt.x, endAtt.y],
            endFace
          );
          const head = pinToLanePts(
            [endAtt.x, endAtt.y],
            endFace,
            endOff[0] || endTail[0],
            toSlot.slot,
            toSlot.count
          );
          const endPart = mergeLeadToSpine(
            head,
            endOff.length ? endOff : endTail,
            endFace
          );
          chain = chain
            ? mergeOrthoPolys(chain, endPart)
            : endPart.map((p) => [p[0], p[1]]);
        }
      }
      if (!chain || chain.length < 2) return [];
      let cleaned = stripShortZJogs(stripOutAndBack(chain));
      // Openings must stay Manhattan; never rewrite terminal V diagonals.
      const pins = [startAtt, endAtt];
      cleaned = ensureManhattanNearPoint(cleaned, startOp, 48, pins);
      cleaned = ensureManhattanNearPoint(cleaned, endOp, 48, pins);
      return [cleaned];
    }
    const d = orthoPathD(c1, c2, null, null, occupied, outsideObstacles);
    return d
      ? pathDToSubpaths(d).map((sub) => ensureOrthoPoly(parallel(sub)))
      : [];
  }

  /**
   * Tube geometry: clip through leaf interiors, but keep B/F endpoint places
   * so the tube reaches the plane boca.
   */
  function conduitDisplayD(fullD, byId, edge) {
    if (!fullD) return "";
    /** @type {string[]} */
    const keep = [];
    if (edge && isPlaneOpeningId(edge.from_opening) && edge.from) {
      keep.push(edge.from);
    }
    if (edge && isPlaneOpeningId(edge.to_opening) && edge.to) {
      keep.push(edge.to);
    }
    // inset 0: do not leave a border corridor that paints tube into the leaf
    // toward terminal strips on side-opening ends.
    const leafObs = placeObstacles(byId, keep, 0);
    return exteriorPathD(fullD, leafObs) || "";
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
    return Math.max(strands, contains.length, 1);
  }

  function appendCableVisuals(cablesG, edge, placeById, elemById, occupied, layout) {
    const colors = edge.colors || [];
    const wireIdx = cableWireIndices(edge);
    const edgeName = edge.name || edge.id || edge.via || "";
    /** @type {SVGElement[]} */
    const paths = [];

    /**
     * Paint a sheath jacket around this cable's contiguous lane span (not the
     * conduit centerline — that made every jacket look like a peer strand).
     */
    if (layout && wireIdx.length && edge.jacket_color) {
      const laneInfos = wireIdx.map((wi) => layout.lane(edge, wi));
      const count = laneInfos[0]?.count || wireIdx.length;
      const indices = laneInfos.map((l) => l.index);
      const i0 = Math.min(...indices);
      const i1 = Math.max(...indices);
      const midOff =
        (highwayLaneOffset(i0, count) + highwayLaneOffset(i1, count)) / 2;
      const jw = highwaySpanWidth(i1 - i0 + 1) + 1.2;
      const jacketCss = wireColorCss(edge.jacket_color);
      const paintJacketD = (d) => {
        if (!d) return;
        for (const piece of pathDToSubpaths(d)) {
          if (piece.length < 2) continue;
          const off =
            Math.abs(midOff) < 1e-9
              ? piece.map((p) => [p[0], p[1]])
              : offsetOrthoPts(piece, midOff);
          if (off.length < 2) continue;
          const jacket = el("path", {
            class: "cable-jacket",
            d: pointsToPathD(off),
          });
          jacket.style.stroke = jacketCss;
          jacket.style.strokeWidth = String(Math.max(3, jw));
          jacket.style.strokeOpacity =
            String(edge.jacket_color).toUpperCase() === "WH" ? "0.88" : "0.75";
          jacket.appendChild(
            el(
              "title",
              null,
              `${edgeName}${colors.length ? ` [${colors.join(",")}]` : ""} jacket ${edge.jacket_color}`
            )
          );
          cablesG.appendChild(jacket);
          paths.push(jacket);
        }
      };
      const hops = edge.conduit_hops || [];
      if (hops.length) {
        for (const hop of hops) {
          const tubeD = hopTubePathD(hop);
          if (!tubeD) continue;
          const fakeEdge = {
            from: hop.from,
            to: hop.to,
            from_opening: hop.from_opening,
            to_opening: hop.to_opening,
          };
          paintJacketD(conduitDisplayD(tubeD, placeById, fakeEdge));
        }
      } else if (edge.conduit) {
        const item = edgePaths.find(
          (e) => e.edge && e.edge.id === edge.conduit
        );
        if (item && item.d) {
          paintJacketD(conduitDisplayD(item.d, placeById, item.edge));
        }
      }
    }

    const paintStrand = (d, code, title) => {
      if (!d) return;
      const key = String(code || "").toUpperCase();
      if (key === "GNYE") {
        // Green-yellow PE: green base + yellow dashes (IEC look).
        const gn = el("path", { class: "cable-strand", d });
        gn.setAttribute("stroke", wireColorCss("GN"));
        gn.setAttribute("stroke-width", String(STRAND_WIDTH));
        gn.appendChild(el("title", null, title));
        const ye = el("path", { class: "cable-strand cable-strand-gnye", d });
        ye.setAttribute("stroke", wireColorCss("YE"));
        ye.setAttribute("stroke-width", String(STRAND_WIDTH));
        ye.setAttribute("stroke-dasharray", "5 5");
        ye.style.strokeOpacity = "0.95";
        const hit = el("path", { class: "cable-strand-hit", d });
        cablesG.appendChild(hit);
        cablesG.appendChild(gn);
        cablesG.appendChild(ye);
        paths.push(hit, gn, ye);
        return;
      }
      const strand = el("path", { class: "cable-strand", d });
      strand.setAttribute("stroke", wireColorCss(code));
      strand.setAttribute("stroke-width", String(STRAND_WIDTH));
      strand.appendChild(el("title", null, title));
      const hit = el("path", { class: "cable-strand-hit", d });
      cablesG.appendChild(hit);
      cablesG.appendChild(strand);
      paths.push(hit, strand);
    };

    // Colored strands: true parallel lanes on the highway.
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
        fromPin: cableWirePin(edge, wi, "from"),
        toPin: cableWirePin(edge, wi, "to"),
      });
      for (const sub of strandSubs) {
        paintStrand(
          pointsToPathD(sub),
          code,
          `${edgeName} · ${code}${edge.via ? ` (${edge.via})` : ""}`
        );
      }
    }
    if (!paths.length) return null;
    return { edge, paths, subs: [], wireIdx };
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
        const displayD = conduitDisplayD(routed.d, byId, item.edge);
        for (const path of item.paths) path.setAttribute("d", displayD);
        for (const s of routed.segs) occupied.push(s);
        const n = (item.edge.contains || []).length;
        const lanes = conduitLaneHint(item.edge, graph.cable_edges || []);
        const roadW = conduitRoadWidth(n, lanes);
        const outline = item.paths[0];
        const tube = item.paths[1] || item.paths[0];
        const tubeCss = wireColorCss(item.edge.color || "GY");
        const outlineCss = contrastOutlineCss(tubeCss);
        if (outline && item.paths.length > 1) {
          outline.style.strokeWidth = String(roadW + OUTLINE_EXTRA);
          outline.style.stroke = outlineCss;
        }
        if (tube) {
          tube.style.strokeWidth = String(roadW);
          tube.style.stroke = tubeCss;
          tube.style.strokeOpacity = item.edge.color ? "0.85" : "0.25";
        }
      }
    }
    // Rebuild cable layers (jacket + strands) from scratch.
    const cablesG = worldEl && worldEl.querySelector("g.cables");
    if (cablesG && showElectrical) {
      cablesG.innerHTML = "";
      cablePaths = [];
      const elemById = Object.fromEntries(
        (graph.elements || []).map((e) => [e.id, e])
      );
      const layout = buildCableLayout(graph.cable_edges || [], elemById, byId);
      for (const edge of graph.cable_edges || []) {
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
          (n.type_label || n.type || "") + (n.expandable ? " · +" : ""),
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
      typeText: (node.type_label || node.type || "") + (node.expandable ? " · +" : ""),
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
      (elem.type_label || elem.type
        ? ` · ${elem.type_label || elem.type}`
        : "");
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
      typeText: elem.type_label || elem.type || "",
      x: 4,
      y: 22,
      maxW: w - 8,
      textClass: "element-type",
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
          const local = terminalCellAnchorLocal(elem, cellId);
          const mark = el("circle", {
            class: "element-terminal",
            cx: String(local.x),
            cy: String(local.y),
            r: "2.75",
            "data-terminal": cellId,
          });
          mark.appendChild(el("title", null, cellId));
          g.appendChild(mark);
        }
      }
    }
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
      const n = (edge.contains || []).length;
      const lanes = conduitLaneHint(edge, graph.cable_edges || []);
      const roadW = conduitRoadWidth(n, lanes);
      const displayD = conduitDisplayD(d, byId, edge);
      const tubeCss = wireColorCss(edge.color || "GY");
      const outlineCss = contrastOutlineCss(tubeCss);
      // High-contrast rim around the conduit (esp. black tubes on dark UI).
      const tubeOutline = el("path", {
        class: "edge-tube-outline",
        d: displayD,
      });
      tubeOutline.style.stroke = outlineCss;
      tubeOutline.style.strokeWidth = String(roadW + OUTLINE_EXTRA);
      tubeOutline.style.strokeOpacity = "0.95";
      const tube = el("path", { class: "edge-tube", d: displayD });
      tube.style.stroke = tubeCss;
      tube.style.strokeWidth = String(roadW);
      tube.style.strokeOpacity = edge.color ? "0.85" : "0.25";
      tube.appendChild(el("title", null, title));
      edgesG.appendChild(tubeOutline);
      edgesG.appendChild(tube);
      // Keep full ``d`` for cable hop overlays; display uses clipped geometry.
      edgePaths.push({ edge, paths: [tubeOutline, tube], d });
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

    // Cables: white jacket + colored strands (above tubes + elements).
    if (showElectrical) {
      const elemById = Object.fromEntries(
        (graph.elements || []).map((e) => [e.id, e])
      );
      const layout = buildCableLayout(graph.cable_edges || [], elemById, byId);
      for (const edge of graph.cable_edges || []) {
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
    }
    updateDepthLabel();
  }

  function selectElement(elem) {
    replaceSelection(elem.id);
    highlightOutline(canvasToSiteId(elem.id));
    fillElementInspector(elem);
  }

  function setInspectorMode(mode) {
    const elements = document.getElementById("props-elements-block");
    const conduits = document.getElementById("props-conduits-block");
    const cables = document.getElementById("props-cables-block");
    const placeMode = mode === "place";
    if (elements) elements.classList.toggle("hidden", !placeMode);
    if (conduits) conduits.classList.toggle("hidden", !placeMode);
    if (cables) cables.classList.toggle("hidden", placeMode);
  }

  function ensurePropertiesVisible() {
    const side = document.getElementById("side-panel");
    if (side && side.classList.contains("collapsed")) {
      setSidePanelCollapsed("inspector", false);
    }
  }

  /** @type {{kind:"place"|"element", placeId:string, element?:string}|null} */
  let propsTarget = null;
  let propsSaveTimer = null;

  function appendPropsRow(meta, spec) {
    const dt = document.createElement("dt");
    dt.textContent = spec.key;
    const dd = document.createElement("dd");
    const value = spec.value == null ? "" : String(spec.value);
    if (!spec.editable) {
      const span = document.createElement("span");
      span.className = "props-readonly";
      span.textContent = value || "—";
      dd.appendChild(span);
    } else if (spec.multiline) {
      const ta = document.createElement("textarea");
      ta.dataset.prop = spec.key;
      ta.value = value;
      ta.rows = 3;
      ta.spellcheck = false;
      dd.appendChild(ta);
    } else {
      const input = document.createElement("input");
      input.type = "text";
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
      el.addEventListener("change", () => {
        scheduleSaveProps();
      });
      el.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && el.tagName === "INPUT") {
          ev.preventDefault();
          el.blur();
        }
      });
    });
  }

  function scheduleSaveProps() {
    if (propsSaveTimer) clearTimeout(propsSaveTimer);
    propsSaveTimer = setTimeout(() => {
      propsSaveTimer = null;
      savePropsFromPanel().catch((err) => setStatus(String(err.message || err)));
    }, 350);
  }

  async function savePropsFromPanel() {
    if (!propsTarget || !locationId) return;
    const meta = document.getElementById("props-meta");
    if (!meta) return;
    /** @type {Record<string, string>} */
    const fields = {};
    meta.querySelectorAll("[data-prop]").forEach((el) => {
      const key = el.getAttribute("data-prop");
      if (!key) return;
      fields[key] = el.value;
    });
    if (!Object.keys(fields).length) return;
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
    if (res.graph) {
      graph = res.graph;
      depthLevel = graph.depth || depthLevel;
      maxDepth = graph.max_depth || maxDepth;
      render();
    }
    applyEditFlags(res);
    setStatus(
      res.dirty ? "properties updated · unsaved" : "properties updated"
    );
    scheduleStatusRefresh();
    if (propsTarget.kind === "element" && selectedId) {
      const elem = (graph?.elements || []).find((e) => e.id === selectedId);
      if (elem) fillElementInspector(elem);
    } else if (propsTarget.kind === "place" && selectedId) {
      await fillPlaceInspector(selectedId, res.detail);
    }
  }

  function fillElementInspector(elem) {
    const empty = document.getElementById("panel-empty");
    const panel = document.getElementById("panel-props");
    if (!empty || !panel) {
      setStatus("Properties panel missing — hard-reload the page (Ctrl+Shift+R)");
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
      value: elem.parent || "(canvas root)",
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
      editable: true,
    });
    appendPropsRow(meta, {
      key: "subtype",
      value: elem.subtype || "",
      editable: true,
    });
    appendPropsRow(meta, {
      key: "notes",
      value: elem.notes || "",
      editable: true,
      multiline: true,
    });
    appendPropsRow(meta, {
      key: "terminals",
      value: (elem.terminals || []).join(", "),
      editable: false,
    });
    bindPropsEditors(meta);
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

  async function fillPlaceInspector(id, detailOpt) {
    const empty = document.getElementById("panel-empty");
    const panel = document.getElementById("panel-props");
    if (!empty || !panel) {
      setStatus("Properties panel missing — hard-reload the page (Ctrl+Shift+R)");
      return;
    }
    if (!id || !locationId) {
      propsTarget = null;
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
      appendPropsRow(meta, { key: "id", value: detail.id, editable: false });
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
        editable: true,
      });
      appendPropsRow(meta, {
        key: "subtype",
        value: detail.subtype || "",
        editable: true,
      });
      appendPropsRow(meta, {
        key: "install",
        value: detail.install || "",
        editable: true,
      });
      appendPropsRow(meta, {
        key: "mount",
        value: detail.mount || "",
        editable: true,
      });
      appendPropsRow(meta, {
        key: "openings",
        value: (detail.openings || []).join(", "),
        editable: false,
      });
      appendPropsRow(meta, {
        key: "connects",
        value: (detail.connects || []).join(" ↔ "),
        editable: false,
      });
      appendPropsRow(meta, {
        key: "notes",
        value: detail.notes || "",
        editable: true,
        multiline: true,
      });
      bindPropsEditors(meta);
      const ul = document.getElementById("props-elements");
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
      setStatus(
        lastMeta && lastMeta.dirty
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
    // Server-side write only. Do not call createWritable on a FileSystemFileHandle
    // here — that triggers the browser "allow edit" permission aviso. OS Open /
    // Save As pickers remain available; Save persists via the housewire server.
    const data = await api("/api/save", { method: "POST", body: "{}" });
    setStatus(`saved ${(data.saved || []).length} file(s)`);
    applyEditFlags(data);
    dirtyLocal = false;
    updateSaveButton(false);
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
    applyEditFlags(data);
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
    // OS Save As dialog grants write access as part of the picker — no extra
    // "allow edit" aviso beyond the system file dialog.
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

  async function fileOpen() {
    // Multi-doc: OS file picker, then load content into a workspace tab.
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
    applyEditFlags(data);
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
    applyEditFlags(data);
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
      row.title = [node.type_label || node.type, node.id]
        .filter(Boolean)
        .join(" · ");

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
      // Canvas root: properties for this place (id=. under the canvas location).
      await fillPlaceInspector(".");
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
    } else if (placeId === locationId || placeId === canvasRoot) {
      clearSelectionState();
      setSelectedVisual();
      await fillPlaceInspector(".");
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
    document.getElementById("panel-props").classList.add("hidden");
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
    undoEdit().catch((err) => setStatus(String(err.message || err)));
  });
  document.getElementById("btn-redo")?.addEventListener("click", () => {
    redoEdit().catch((err) => setStatus(String(err.message || err)));
  });
  document.getElementById("btn-layout-reset")?.addEventListener("click", () => {
    resetEdits().catch((err) => setStatus(String(err.message || err)));
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
      undoEdit().catch((err) => setStatus(String(err.message || err)));
    } else if (key === "y" || (key === "z" && ev.shiftKey)) {
      ev.preventDefault();
      redoEdit().catch((err) => setStatus(String(err.message || err)));
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
        undoEdit().catch((err) => setStatus(String(err.message || err)));
      } else if (action === "redo") {
        redoEdit().catch((err) => setStatus(String(err.message || err)));
      } else if (action === "reset") {
        resetEdits().catch((err) => setStatus(String(err.message || err)));
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

  const THEME_KEY = "housewire-theme";

  function currentTheme() {
    const t = document.documentElement.getAttribute("data-theme");
    return t === "light" ? "light" : "dark";
  }

  function syncThemeMenu() {
    const theme = currentTheme();
    const dark = document.getElementById("menu-theme-dark");
    const light = document.getElementById("menu-theme-light");
    if (dark) dark.setAttribute("aria-checked", theme === "dark" ? "true" : "false");
    if (light) light.setAttribute("aria-checked", theme === "light" ? "true" : "false");
  }

  function setTheme(theme) {
    const next = theme === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch (_) {
      /* ignore quota / private mode */
    }
    syncThemeMenu();
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
      if (action === "theme-dark" || action === "theme-light") {
        closeAllMenus();
        setTheme(action === "theme-light" ? "light" : "dark");
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

  syncThemeMenu();

  function closeAboutModal() {
    const modal = document.getElementById("about-modal");
    if (!modal) return;
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
  }

  async function openAboutModal() {
    const modal = document.getElementById("about-modal");
    if (!modal) return;
    try {
      const about = await api("/api/about");
      const titleEl = document.getElementById("about-title");
      const versionEl = document.getElementById("about-version");
      const descEl = document.getElementById("about-description");
      const authorEl = document.getElementById("about-author");
      const repoEl = document.getElementById("about-repository");
      const licenseEl = document.getElementById("about-license");
      const copyrightEl = document.getElementById("about-copyright");
      if (titleEl) titleEl.textContent = about.title || "HouseWire";
      if (versionEl) {
        versionEl.textContent = about.version ? `Version ${about.version}` : "";
      }
      if (descEl) descEl.textContent = about.description || "";
      if (authorEl) authorEl.textContent = about.author || "";
      if (repoEl) {
        const url = about.repository || "";
        repoEl.href = url || "#";
        repoEl.textContent = url;
        if (!url) repoEl.removeAttribute("href");
      }
      if (licenseEl) licenseEl.textContent = about.license || "";
      if (copyrightEl) copyrightEl.textContent = about.copyright || "";
    } catch (err) {
      setStatus(String(err.message || err));
      return;
    }
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    modal.querySelector("[data-about-dismiss].primary, .modal-actions .primary")
      ?.focus?.();
  }

  const menuHelp = document.getElementById("menu-help");
  if (menuHelp) {
    menuHelp.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const item = ev.target.closest("[data-help-action]");
      if (!item || item.disabled) return;
      closeAllMenus();
      const action = item.getAttribute("data-help-action");
      if (action === "about") {
        openAboutModal().catch((err) => setStatus(String(err.message || err)));
      }
    });
  }

  document.querySelectorAll("[data-about-dismiss]").forEach((el) => {
    el.addEventListener("click", () => closeAboutModal());
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    const about = document.getElementById("about-modal");
    if (about && !about.classList.contains("hidden")) {
      closeAboutModal();
      ev.preventDefault();
    }
  });

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
          `/api/place?location=${encodeURIComponent(locationId)}&id=${encodeURIComponent(resolvePlaceApiId(selectedId))}`
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

  loadConductorColors()
    .then(() => loadLocations())
    .catch((err) => setStatus(String(err.message || err)));
})();
