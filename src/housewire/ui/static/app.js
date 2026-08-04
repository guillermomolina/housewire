(() => {
  const svg = document.getElementById("canvas");
  const depthLabel = document.getElementById("depth-label");
  const statusEl = document.getElementById("status");
  const viewport = document.getElementById("viewport");
  const I18n = window.HouseWireI18n || {
    t: (k) => k,
    getLocale: () => "en",
    setLocale: () => "en",
    applyDomTranslations: () => {},
  };
  const t = (key, vars) => I18n.t(key, vars);

  const LEAF_W = 120;
  const LEAF_H = 56;
  const LEAF_W_MAX = 260;
  const PAD = 28;
  const HEADER = 36;
  const LABEL_CHAR_W = 6.6;
  /** Default depth when opening a document with no saved view. */
  const DEPTH_DEFAULT = 1;
  /** Requested depth when entering a place / deepening without a cap. */
  const DEPTH_MAX_REQUEST = 999;

  let graph = null;
  let locationId = null;
  let selectedId = null;
  let selectedIds = new Set();
  let depthLevel = DEPTH_DEFAULT;
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
  /** sessionStorage key for per-document camera/view (survives F5). */
  const DOC_VIEWS_KEY = "housewire-doc-views-v1";

  function loadPersistedDocViews() {
    try {
      const raw = sessionStorage.getItem(DOC_VIEWS_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed)
        ? parsed
        : {};
    } catch {
      return {};
    }
  }

  function persistDocViews() {
    try {
      sessionStorage.setItem(DOC_VIEWS_KEY, JSON.stringify(docViews));
    } catch {
      /* ignore quota / private mode */
    }
  }

  /** Per-document canvas location/depth/camera (tabs + F5 restore). */
  let docViews = loadPersistedDocViews();
  let drag = null;
  let panDrag = null;
  /** Space held for pan-anywhere (ignored while typing in inputs). */
  let spacePanHeld = false;
  /** Alt held for pan-anywhere (wheel+Alt still changes depth). */
  let altPanHeld = false;
  let marquee = null;
  /** @type {number} */
  let edgeAutoPanRaf = 0;
  /** Last pointer client position while edge auto-pan is active. */
  let edgeAutoPanClient = null;
  let saveTimer = null;
  let worldEl = null;
  let nodesById = {};
  let elementsById = {};
  let edgePaths = [];
  /** @type {Map<string, (typeof edgePaths)[number]>} */
  let edgePathsByConduitId = new Map();
  let cablePaths = [];
  /**
   * Memo for ``minBendOrtho`` within one render/refresh when ``occupied`` is
   * empty (hop fallbacks / interior legs). Cleared with routeGeomCache.
   * @type {Map<string, number[][]>|null}
   */
  let routeOrthoMemo = null;
  let lastTap = { id: null, t: 0 };
  let canUndo = false;
  let canRedo = false;
  let canReset = false;
  /** In-memory Cut/Copy payload from POST /api/edit/copy|cut. */
  let editClipboard = null;
  /** @type {"copy"|"cut"|null} */
  let editClipboardMode = null;
  /** Session default: physical places/conduits only (no elements/cables). */
  let showElectrical = false;
  let outlineNodes = [];
  let canvasLocations = [];
  let collapsedOutline = new Set();
  let outlineCollapseReady = false;
  /** Re-render once after growing places around inbox cables. */
  let renderExpandPass = 0;
  /** @type {Record<string, number[][][]>|null} */
  let inboxCablePtsByParent = null;
  const DRAG_THRESHOLD = 4;
  const DBLCLICK_MS = 400;
  const ELEM_W = 72;
  const ELEM_H = 28;
  /** Default insert size for new place containers (click without drag). */
  const PLACE_INSERT_W = 240;
  const PLACE_INSERT_H = 160;
  /** Edge band (px) that triggers auto-pan while dragging. */
  const EDGE_AUTOPAN_MARGIN = 44;
  /** Max auto-pan speed (px per animation frame) at the viewport edge. */
  const EDGE_AUTOPAN_MAX_PX = 18;
  /** Hit margin for resize edges/corners in screen pixels. */
  const RESIZE_HIT_PX = 7;
  /** Must stay in sync with housewire.ui.route_quality highway constants. */
  const STRAND_WIDTH = 2.5;
  const LANE_GAP = STRAND_WIDTH;
  const LANE_PITCH = STRAND_WIDTH + LANE_GAP;
  /** Shared-terminal V: lateral pitch (keep strands distinct but tight). */
  const TERMINAL_FAN_PITCH = LANE_PITCH;
  /** Outward depth pin→tip and tip→rail for multi-cable terminal V. */
  const TERMINAL_FAN_TIP = 12;
  const TERMINAL_FAN_RAIL = 14;
  /** Min clear between adjacent terminal fan envelopes on one face. */
  const TERMINAL_FAN_CLEAR = STRAND_WIDTH;

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

  function normalizeIconId(raw) {
    let text = String(raw == null ? "" : raw).trim().toLowerCase();
    if (!text) return "circle";
    text = text.replace(/_/g, "-");
    const token = text.split(/\s+/).filter(Boolean)[0] || "";
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(token)) return "circle";
    return token;
  }

  /** HTML for a Lucide icon from the local sprite. */
  function iconHtml(name, extraClass) {
    const id = normalizeIconId(name);
    const cls = extraClass ? `hw-icon ${extraClass}` : "hw-icon";
    return (
      `<svg xmlns="http://www.w3.org/2000/svg" class="${cls}" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false">` +
      `<use href="#icon-${id}" width="24" height="24"></use></svg>`
    );
  }

  function iconElement(name, extraClass) {
    const id = normalizeIconId(name);
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute(
      "class",
      extraClass ? `hw-icon ${extraClass}` : "hw-icon"
    );
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "24");
    svg.setAttribute("height", "24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#icon-${id}`);
    use.setAttribute("width", "24");
    use.setAttribute("height", "24");
    svg.appendChild(use);
    return svg;
  }

  /** Lucide icon + type label on a canvas box (place or element). */
  function appendTypeWithIcon(g, { icon, typeText, x, y, maxW, textClass }) {
    const iconSize = 10;
    const gap = 3;
    const fo = document.createElementNS(ns, "foreignObject");
    fo.setAttribute("class", "type-icon-fo");
    fo.setAttribute("x", String(x));
    fo.setAttribute("y", String(y - iconSize));
    fo.setAttribute("width", String(iconSize + 2));
    fo.setAttribute("height", String(iconSize + 2));
    const svgIcon = iconElement(icon, "type-icon");
    if (svgIcon) fo.appendChild(svgIcon);
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

  /** Inject Lucide sprite once so <use href="#icon-…"> resolves in-document. */
  function ensureIconSprite() {
    if (document.getElementById("hw-icon-sprite")) return Promise.resolve();
    return fetch("/static/icons.svg")
      .then((r) => {
        if (!r.ok) throw new Error(`icons.svg ${r.status}`);
        return r.text();
      })
      .then((text) => {
        const holder = document.createElement("div");
        holder.id = "hw-icon-sprite";
        holder.setAttribute("hidden", "");
        holder.setAttribute("aria-hidden", "true");
        holder.innerHTML = text;
        document.body.prepend(holder);
      })
      .catch((err) => {
        console.warn("HouseWire icon sprite failed to load", err);
      });
  }

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
    updateDeleteButtons();
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

  function pruneCollapsedOutline(deletedSiteIds) {
    if (!deletedSiteIds || !deletedSiteIds.length) return;
    const doomed = new Set(deletedSiteIds);
    let changed = false;
    for (const id of [...collapsedOutline]) {
      if (doomed.has(id)) {
        collapsedOutline.delete(id);
        changed = true;
        continue;
      }
      for (const del of doomed) {
        if (del !== "." && id.startsWith(`${del}/`)) {
          collapsedOutline.delete(id);
          changed = true;
          break;
        }
      }
    }
    if (changed) saveCollapsedOutline();
  }

  function updateDeleteButtons() {
    const hasSel = hasDocument && selectedIds.size >= 1;
    for (const id of ["btn-delete", "menu-delete", "btn-cut", "menu-cut", "btn-copy", "menu-copy"]) {
      const el = document.getElementById(id);
      if (el) el.disabled = !hasSel;
    }
    const canPaste = hasDocument && Boolean(editClipboard);
    for (const id of ["btn-paste", "menu-paste"]) {
      const el = document.getElementById(id);
      if (el) el.disabled = !canPaste;
    }
  }

  function selectedSiteIds() {
    return [...selectedIds]
      .map((id) => canvasToSiteId(id))
      .filter((id) => id && id !== ".");
  }

  /** Parent site id for paste destination, or null if selection is ambiguous. */
  function parentSiteIdOf(siteId) {
    if (!siteId || siteId === ".") return ".";
    if (!siteId.includes("/")) return ".";
    return siteId.slice(0, siteId.lastIndexOf("/"));
  }

  /**
   * Shared parent site id from clipboard item paths (full site paths).
   * Used when pasting elements with an empty selection so they return to their
   * box while the canvas is a selectable ancestor (e.g. floor).
   */
  function clipboardSharedParentSiteId(payload) {
    const items = (payload && payload.items) || [];
    if (!items.length) return null;
    const parents = [];
    for (const it of items) {
      const path = it.path;
      if (!Array.isArray(path) || !path.length) {
        parents.push(".");
        continue;
      }
      parents.push(path.length === 1 ? "." : path.slice(0, -1).join("/"));
    }
    const uniq = [...new Set(parents)];
    return uniq.length === 1 ? uniq[0] : null;
  }

  function siteIdUnderCanvas(siteId, canvasId) {
    if (!siteId) return false;
    if (!canvasId || canvasId === ".") return true;
    return siteId === canvasId || siteId.startsWith(`${canvasId}/`);
  }

  function clipboardHasOnlyElements(payload) {
    const items = (payload && payload.items) || [];
    return items.length > 0 && items.every((it) => it && it.kind === "element");
  }

  /**
   * Paste target place, or null if selection is ambiguous.
   *
   * Intended workflows:
   * - Copy then Paste with the source still selected → sibling (duplicate beside)
   * - Cut then Paste with empty selection → original parent (put back; cables stay
   *   open/disconnected from any far end that was severed)
   * - Paste with a place selected + element clipboard → into that place
   * - Paste with a place selected + place clipboard → siblings of that place
   */
  function resolvePasteParentSiteId() {
    const onlyElems = clipboardHasOnlyElements(editClipboard);

    if (!selectedIds.size) {
      // Cut→paste (and copy→paste after clearing selection): same parent as source
      // when it still sits under the current canvas.
      const fromClip = clipboardSharedParentSiteId(editClipboard);
      if (
        fromClip &&
        siteIdUnderCanvas(fromClip, locationId) &&
        (editClipboardMode === "cut" || onlyElems)
      ) {
        return fromClip;
      }
      return locationId || ".";
    }

    const placeSites = [];
    const elemParents = [];
    const placeById = Object.fromEntries(
      (graph?.nodes || []).map((n) => [n.id, n])
    );
    const elemById = Object.fromEntries(
      (graph?.elements || []).map((e) => [e.id, e])
    );
    for (const id of selectedIds) {
      if (placeById[id]) {
        placeSites.push(canvasToSiteId(id));
        continue;
      }
      const elem = elemById[id];
      if (elem) {
        const parentRel = elem.parent;
        if (parentRel == null || parentRel === "" || parentRel === ".") {
          elemParents.push(locationId || ".");
        } else {
          elemParents.push(canvasToSiteId(parentRel));
        }
      }
    }
    if (placeSites.length && elemParents.length) return null;

    if (placeSites.length) {
      if (onlyElems) {
        // Drop elements into the selected container(s).
        const uniq = [...new Set(placeSites)];
        if (uniq.length !== 1) return null;
        return uniq[0];
      }
      // Places: paste as siblings of the selection.
      const parents = [...new Set(placeSites.map(parentSiteIdOf))];
      if (parents.length !== 1) return null;
      return parents[0];
    }

    if (elemParents.length) {
      // Copy→paste with source element still selected → sibling under same parent.
      const uniq = [...new Set(elemParents)];
      if (uniq.length !== 1) return null;
      return uniq[0];
    }
    return locationId || ".";
  }

  async function copySelection() {
    if (!hasDocument || selectedIds.size < 1) return;
    const siteIds = selectedSiteIds();
    if (!siteIds.length) {
      setStatus(t("status.cannotCopyRoot"));
      return;
    }
    const res = await api("/api/edit/copy", {
      method: "POST",
      body: JSON.stringify({ ids: siteIds }),
    });
    editClipboard = res.payload || null;
    editClipboardMode = editClipboard ? "copy" : null;
    updateDeleteButtons();
    // Keep the source selected so Paste duplicates as a sibling.
    highlightOutlineSelection();
    const n = (editClipboard?.items || []).length;
    setStatus(t("status.copied", { n }));
  }

  async function cutSelection() {
    if (!hasDocument || !locationId || selectedIds.size < 1) return;
    const siteIds = selectedSiteIds();
    if (!siteIds.length) {
      setStatus(t("status.cannotCutRoot"));
      return;
    }
    const res = await api("/api/edit/cut", {
      method: "POST",
      body: JSON.stringify({
        ids: siteIds,
        location_id: locationId,
        depth: depthLevel,
      }),
    });
    editClipboard = res.payload || null;
    editClipboardMode = editClipboard ? "cut" : null;
    updateDeleteButtons();
    pruneCollapsedOutline(res.deleted || siteIds);
    clearSelectionState();
    setSelectedVisual();
    const newLoc = res.location || locationId;
    if (newLoc !== locationId) {
      locationId = newLoc;
      rememberCurrentDocView();
      if (res.graph) {
        graph = res.graph;
        depthLevel = graph.depth || depthLevel;
        maxDepth = graph.max_depth || maxDepth;
        render();
      } else {
        await loadLocation({ fit: false });
      }
    } else if (res.graph) {
      graph = res.graph;
      depthLevel = graph.depth || depthLevel;
      maxDepth = graph.max_depth || maxDepth;
      render();
    }
    applyEditFlags(res);
    await loadOutline();
    await syncInspectorFromSelection();
    const count = (res.deleted || siteIds).length;
    setStatus(t("status.cut", { n: count }));
    scheduleStatusRefresh();
  }

  async function pasteClipboard() {
    if (!hasDocument || !locationId || !editClipboard) return;
    const parentId = resolvePasteParentSiteId();
    if (parentId == null) {
      setStatus(t("status.pasteNeedParent"));
      return;
    }
    const mode = editClipboardMode;
    const res = await api("/api/edit/paste", {
      method: "POST",
      body: JSON.stringify({
        parent_id: parentId,
        payload: editClipboard,
        mode: mode || "copy",
        lang: I18n.getLocale ? I18n.getLocale() : "en",
        location_id: locationId,
        depth: depthLevel,
      }),
    });
    if (res.graph) {
      graph = res.graph;
      depthLevel = graph.depth || depthLevel;
      maxDepth = graph.max_depth || maxDepth;
      render();
    }
    applyEditFlags(res);
    expandOutlineAncestors(parentId);
    await loadOutline();
    const created = res.created || [];
    const relIds = created
      .map((id) => siteToCanvasRelative(id))
      .filter((id) => id);
    // After paste, select only the new items (source stays for another Copy paste).
    if (relIds.length) {
      commitSelection(new Set(relIds), relIds[0]);
      highlightOutlineSelection();
    } else {
      clearSelectionState();
      setSelectedVisual();
    }
    await syncInspectorFromSelection();
    const n = created.length || (editClipboard.items || []).length;
    setStatus(t("status.pasted", { n }));
    scheduleStatusRefresh();
  }

  async function deleteSelection() {
    if (!hasDocument || !locationId || selectedIds.size < 1) return;
    const siteIds = [...selectedIds]
      .map((id) => canvasToSiteId(id))
      .filter((id) => id && id !== ".");
    if (!siteIds.length) {
      setStatus(t("status.cannotDeleteRoot"));
      return;
    }
    const n = siteIds.length;
    const choice = await appDialog({
      title: "Delete",
      message:
        n === 1
          ? `Delete ${siteIds[0]} and its contents? Cross-boundary cables become open runs.`
          : `Delete ${n} selected item(s) and their contents? Cross-boundary cables become open runs.`,
      buttons: [
        { id: "cancel", label: "Cancel" },
        { id: "delete", label: "Delete", danger: true, primary: true },
      ],
    });
    if (choice !== "delete") return;
    const res = await api("/api/edit/delete", {
      method: "POST",
      body: JSON.stringify({
        ids: siteIds,
        location_id: locationId,
        depth: depthLevel,
      }),
    });
    pruneCollapsedOutline(res.deleted || siteIds);
    clearSelectionState();
    setSelectedVisual();
    const newLoc = res.location || locationId;
    if (newLoc !== locationId) {
      locationId = newLoc;
      rememberCurrentDocView();
      if (res.graph) {
        graph = res.graph;
        depthLevel = graph.depth || depthLevel;
        maxDepth = graph.max_depth || maxDepth;
        render();
      } else {
        await loadLocation({ fit: false });
      }
    } else if (res.graph) {
      graph = res.graph;
      depthLevel = graph.depth || depthLevel;
      maxDepth = graph.max_depth || maxDepth;
      render();
    }
    applyEditFlags(res);
    await loadOutline();
    await syncInspectorFromSelection();
    const count = (res.deleted || siteIds).length;
    const bits = [`deleted ${count} item(s)`];
    if ((res.severed || []).length) bits.push(`${res.severed.length} open run(s)`);
    setStatus(`${bits.join(" · ")} · unsaved`);
    scheduleStatusRefresh();
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

  function apiErrorMessage(body, fallback) {
    const raw = (body && String(body).trim()) || fallback || "request failed";
    try {
      const parsed = JSON.parse(raw);
      const detail = parsed && parsed.detail;
      if (typeof detail === "string" && detail.trim()) return detail.trim();
      if (Array.isArray(detail)) {
        const parts = detail
          .map((item) => {
            if (typeof item === "string") return item;
            if (item && typeof item.msg === "string") return item.msg;
            return "";
          })
          .filter(Boolean);
        if (parts.length) return parts.join("; ");
      }
    } catch {
      /* plain text body */
    }
    return raw;
  }

  async function api(path, options) {
    const locale = I18n.getLocale ? I18n.getLocale() : "en";
    const headers = {
      "Content-Type": "application/json",
      "Accept-Language": locale,
      ...(options?.headers || {}),
    };
    let url = path;
    if (url.indexOf("lang=") < 0) {
      url += (url.indexOf("?") >= 0 ? "&" : "?") + "lang=" + encodeURIComponent(locale);
    }
    const res = await fetch(url, {
      ...options,
      headers,
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(apiErrorMessage(body, res.statusText));
    }
    return res.json();
  }

  /** Stable empty list for childrenOf misses (do not mutate). */
  const EMPTY_NODES = Object.freeze([]);

  /** @type {Map<string|null, object[]>|null} */
  let kidsByParent = null;
  /** @type {object|null} */
  let kidsGraphRef = null;

  function ensureKidsIndex() {
    if (kidsByParent && kidsGraphRef === graph) return kidsByParent;
    kidsGraphRef = graph;
    kidsByParent = new Map();
    for (const n of graph?.nodes || []) {
      const key = n.parent || null;
      let arr = kidsByParent.get(key);
      if (!arr) {
        arr = [];
        kidsByParent.set(key, arr);
      }
      arr.push(n);
    }
    return kidsByParent;
  }

  function childrenOf(parentId) {
    const idx = ensureKidsIndex();
    return idx.get(parentId || null) || EMPTY_NODES;
  }

  /**
   * Per-frame routing geometry (obstacles / borders). Built once at the start
   * of render / refreshEdges so each edge does not rebuild the same rects.
   * @type {{
   *   placeById: object,
   *   elemById: object|null,
   *   borderRects: {x:number,y:number,w:number,h:number}[],
   *   placeLeaves: Record<string, {id:string,x:number,y:number,w:number,h:number}[]>,
   *   elements: Record<string, {id:string,x:number,y:number,w:number,h:number}[]>,
   * }|null}
   */
  let routeGeomCache = null;

  function beginRouteGeomCache(placeById, elemById) {
    const placeLeaves = {};
    for (const pad of [0, 2, 8]) {
      /** @type {{id:string,x:number,y:number,w:number,h:number}[]} */
      const rects = [];
      for (const n of Object.values(placeById || {})) {
        if (!n || childrenOf(n.id).length) continue;
        const a = absXY(n, placeById);
        const w = nodeW(n) - 2 * pad;
        const h = nodeH(n) - 2 * pad;
        if (w < 4 || h < 4) continue;
        rects.push({ id: n.id, x: a.x + pad, y: a.y + pad, w, h });
      }
      placeLeaves[String(pad)] = rects;
    }
    /** @type {Record<string, {id:string,x:number,y:number,w:number,h:number}[]>} */
    const elements = {};
    for (const pad of [2]) {
      /** @type {{id:string,x:number,y:number,w:number,h:number}[]} */
      const rects = [];
      for (const e of Object.values(elemById || {})) {
        if (!e) continue;
        const a = elementAbsXY(e, placeById);
        const w = (e.w ?? ELEM_W) - 2 * pad;
        const h = (e.h ?? ELEM_H) - 2 * pad;
        if (w < 4 || h < 4) continue;
        rects.push({ id: e.id, x: a.x + pad, y: a.y + pad, w, h });
      }
      elements[String(pad)] = rects;
    }
    /** @type {{x:number,y:number,w:number,h:number}[]} */
    const borderRects = [];
    for (const n of Object.values(placeById || {})) {
      if (!n) continue;
      const a = absXY(n, placeById);
      borderRects.push({ x: a.x, y: a.y, w: nodeW(n), h: nodeH(n) });
    }
    routeGeomCache = {
      placeById,
      elemById: elemById || null,
      borderRects,
      placeLeaves,
      elements,
    };
    routeOrthoMemo = new Map();
  }

  function endRouteGeomCache() {
    routeGeomCache = null;
    routeOrthoMemo = null;
  }

  function indexEdgePaths() {
    edgePathsByConduitId.clear();
    for (const item of edgePaths) {
      const id = item?.edge?.id;
      if (id) edgePathsByConduitId.set(id, item);
    }
  }

  /** Compact obstacle list for route memo keys (integer px). */
  function obstaclesMemoKey(obstacles) {
    if (!obstacles || !obstacles.length) return "";
    let s = "";
    for (const r of obstacles) {
      s += `${r.x | 0},${r.y | 0},${r.w | 0},${r.h | 0};`;
    }
    return s;
  }

  function filterCachedIdRects(all, excludeIds) {
    const ex = excludeIds && excludeIds.length ? new Set(excludeIds) : null;
    /** @type {{x:number,y:number,w:number,h:number}[]} */
    const out = [];
    for (const r of all || []) {
      if (ex && ex.has(r.id)) continue;
      out.push({ x: r.x, y: r.y, w: r.w, h: r.h });
    }
    return out;
  }

  function isModClick(ev) {
    return !!(ev && (ev.ctrlKey || ev.metaKey));
  }

  function isEditableFocus(target) {
    const el = target || document.activeElement;
    if (!el || el === document.body) return false;
    const tag = String(el.tagName || "").toUpperCase();
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
    if (el.isContentEditable) return true;
    return Boolean(el.closest?.("input, textarea, select, [contenteditable='true']"));
  }

  function isPanModifierHeld() {
    return spacePanHeld || altPanHeld;
  }

  function syncPanReadyClass() {
    if (!viewport) return;
    if (panDrag || marquee) {
      viewport.classList.remove("pan-ready");
      return;
    }
    viewport.classList.toggle("pan-ready", isPanModifierHeld());
  }

  /**
   * Start a canvas pan. ``clearOnClick``: left-drag on empty canvas that never
   * moves clears the selection on pointerup (click vs pan).
   */
  function beginPanDrag(ev, { clearOnClick = false } = {}) {
    if (!ev || drag || marquee || panDrag) return false;
    panDrag = {
      x: ev.clientX,
      y: ev.clientY,
      panX,
      panY,
      pointerId: ev.pointerId,
      clearOnClick: Boolean(clearOnClick),
      moved: false,
    };
    viewport.classList.add("panning");
    viewport.classList.remove("pan-ready");
    try {
      svg.setPointerCapture(ev.pointerId);
    } catch {
      /* ignore */
    }
    return true;
  }

  function endPanDrag() {
    const moved = Boolean(panDrag && panDrag.moved);
    panDrag = null;
    viewport.classList.remove("panning");
    syncPanReadyClass();
    if (moved) rememberCurrentDocView();
  }

  /**
   * Screen-space pan deltas when the pointer sits in the viewport edge band.
   * Positive dx/dy move world content right/down (reveal left/top).
   */
  function edgeAutoPanDelta(clientX, clientY) {
    if (!viewport) return { dx: 0, dy: 0 };
    const rect = viewport.getBoundingClientRect();
    const m = EDGE_AUTOPAN_MARGIN;
    const max = EDGE_AUTOPAN_MAX_PX;
    let dx = 0;
    let dy = 0;
    const left = clientX - rect.left;
    const right = rect.right - clientX;
    const top = clientY - rect.top;
    const bottom = rect.bottom - clientY;
    if (left < m) dx = max * (1 - Math.max(0, left) / m);
    else if (right < m) dx = -max * (1 - Math.max(0, right) / m);
    if (top < m) dy = max * (1 - Math.max(0, top) / m);
    else if (bottom < m) dy = -max * (1 - Math.max(0, bottom) / m);
    return { dx, dy };
  }

  function stopEdgeAutoPan() {
    if (edgeAutoPanRaf) {
      cancelAnimationFrame(edgeAutoPanRaf);
      edgeAutoPanRaf = 0;
    }
    edgeAutoPanClient = null;
  }

  /** One auto-pan + reapply-drag step. Returns true if still near an edge. */
  function applyEdgeAutoPanTick() {
    if (!drag || !drag.moved || !edgeAutoPanClient) {
      stopEdgeAutoPan();
      return false;
    }
    const { x, y } = edgeAutoPanClient;
    const { dx, dy } = edgeAutoPanDelta(x, y);
    if (!dx && !dy) return false;
    panX += dx;
    panY += dy;
    // Keep (client - startClient)/scale tracking the pointer as the camera moves.
    drag.startClientX += dx;
    drag.startClientY += dy;
    applyWorldTransform();
    const fakeEv = { clientX: x, clientY: y, pointerId: drag.pointerId };
    if (drag.kind === "resize") applyResizeDrag(fakeEv);
    else applyMultiDrag(fakeEv);
    return true;
  }

  /** Track pointer and keep panning while it stays in the edge band. */
  function scheduleEdgeAutoPan(ev) {
    if (!drag || !drag.moved || !ev) {
      stopEdgeAutoPan();
      return;
    }
    edgeAutoPanClient = { x: ev.clientX, y: ev.clientY };
    if (edgeAutoPanRaf) return;
    const loop = () => {
      edgeAutoPanRaf = 0;
      if (!applyEdgeAutoPanTick()) return;
      edgeAutoPanRaf = requestAnimationFrame(loop);
    };
    if (applyEdgeAutoPanTick()) {
      edgeAutoPanRaf = requestAnimationFrame(loop);
    }
  }

  /** True when this pointerdown should pan instead of select/move. */
  function shouldPanPointer(ev) {
    if (!ev) return false;
    if (ev.button === 1) return true;
    if (ev.button === 0 && isPanModifierHeld()) return true;
    return false;
  }

  /** Shift+drag selection box (works on empty canvas and inside places).
   *  Ctrl/Cmd+Shift makes the marquee additive. */
  function beginMarquee(ev) {
    if (!ev || ev.button !== 0 || !ev.shiftKey) return false;
    if (drag || marquee || panDrag) return false;
    marquee = {
      pointerId: ev.pointerId,
      startClientX: ev.clientX,
      startClientY: ev.clientY,
      additive: Boolean(ev.ctrlKey || ev.metaKey),
      moved: false,
      captured: true,
    };
    viewport.classList.add("marqueeing");
    try {
      svg.setPointerCapture(ev.pointerId);
    } catch {
      /* ignore */
    }
    return true;
  }

  function clearSelectionState() {
    selectedIds.clear();
    selectedId = null;
    updateDeleteButtons();
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

  /**
   * Drop place/element descendants when an ancestor place is also selected.
   * Never keep both a container and its contents in the selection.
   */
  function normalizeSelectionSet(raw) {
    const byId = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
    const elemById = Object.fromEntries(
      (graph?.elements || []).map((e) => [e.id, e])
    );
    const places = new Set();
    const elems = new Set();
    for (const id of raw || []) {
      if (byId[id]) places.add(id);
      else if (elemById[id]) elems.add(id);
    }
    const keptPlaces = new Set();
    for (const id of places) {
      if (selectionHasAncestorPlace(id, places)) continue;
      keptPlaces.add(id);
    }
    const keptElems = new Set();
    for (const id of elems) {
      const parent = elemById[id]?.parent;
      if (
        parent &&
        (keptPlaces.has(parent) ||
          selectionHasAncestorPlace(parent, keptPlaces))
      ) {
        continue;
      }
      keptElems.add(id);
    }
    return new Set([...keptPlaces, ...keptElems]);
  }

  /** Remove ancestor places of ``id`` so a child can replace its container. */
  function stripAncestorsFromSet(set, id) {
    const byId = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
    const elemById = Object.fromEntries(
      (graph?.elements || []).map((e) => [e.id, e])
    );
    let cur = byId[id] ? byId[id].parent : elemById[id]?.parent;
    while (cur) {
      set.delete(cur);
      cur = byId[cur]?.parent;
    }
  }

  function commitSelection(ids, primaryId, { ensureVisible = true } = {}) {
    const normalized = normalizeSelectionSet(ids);
    selectedIds = normalized;
    if (primaryId != null && normalized.has(primaryId)) {
      selectedId = primaryId;
    } else {
      selectedId = [...normalized].slice(-1)[0] ?? null;
    }
    setSelectedVisual();
    updateDeleteButtons();
    if (ensureVisible && selectedId) {
      ensureIdVisible(selectedId);
      highlightOutlineSelection({ scrollTo: selectedId });
    }
  }

  function toggleSelectionId(id) {
    if (selectedIds.has(id)) {
      const next = new Set(selectedIds);
      next.delete(id);
      commitSelection(next, null, { ensureVisible: false });
      return;
    }
    const next = new Set(selectedIds);
    stripAncestorsFromSet(next, id);
    next.add(id);
    commitSelection(next, id);
  }

  function replaceSelection(id) {
    commitSelection(id == null ? new Set() : new Set([id]), id);
  }

  function worldRectForSelectionId(id) {
    if (!id || !graph) return null;
    const byId = Object.fromEntries((graph.nodes || []).map((n) => [n.id, n]));
    const node = (graph.nodes || []).find((n) => n.id === id);
    if (node) return placeWorldRect(node, byId);
    const elem = (graph.elements || []).find((e) => e.id === id);
    if (elem) return elementWorldRect(elem, byId);
    return null;
  }

  /** Pan the canvas so ``id`` stays inside the viewport (no zoom change). */
  function ensureIdVisible(id, { padding = 48 } = {}) {
    if (!id || !viewport) return;
    const g = nodesById[id] || elementsById[id];
    if (!g) {
      // Fallback before paint: use graph world rects.
      const wr = worldRectForSelectionId(id);
      if (!wr) return;
      const rect = viewport.getBoundingClientRect();
      const viewW = Math.max(rect.width || 0, 1);
      const viewH = Math.max(rect.height || 0, 1);
      const sx1 = wr.x1 * scale + panX;
      const sy1 = wr.y1 * scale + panY;
      const sx2 = wr.x2 * scale + panX;
      const sy2 = wr.y2 * scale + panY;
      let dx = 0;
      let dy = 0;
      if (sx2 - sx1 > viewW - 2 * padding) dx = padding - sx1;
      else if (sx1 < padding) dx = padding - sx1;
      else if (sx2 > viewW - padding) dx = viewW - padding - sx2;
      if (sy2 - sy1 > viewH - 2 * padding) dy = padding - sy1;
      else if (sy1 < padding) dy = padding - sy1;
      else if (sy2 > viewH - padding) dy = viewH - padding - sy2;
      if (!dx && !dy) return;
      panX += dx;
      panY += dy;
      applyWorldTransform();
      rememberCurrentDocView();
      return;
    }
    const box = g.querySelector(".node-box, .element-box") || g;
    const br = box.getBoundingClientRect();
    const vr = viewport.getBoundingClientRect();
    let dx = 0;
    let dy = 0;
    if (br.width > vr.width - 2 * padding) {
      dx = vr.left + padding - br.left;
    } else if (br.left < vr.left + padding) {
      dx = vr.left + padding - br.left;
    } else if (br.right > vr.right - padding) {
      dx = vr.right - padding - br.right;
    }
    if (br.height > vr.height - 2 * padding) {
      dy = vr.top + padding - br.top;
    } else if (br.top < vr.top + padding) {
      dy = vr.top + padding - br.top;
    } else if (br.bottom > vr.bottom - padding) {
      dy = vr.bottom - padding - br.bottom;
    }
    if (!dx && !dy) return;
    panX += dx;
    panY += dy;
    applyWorldTransform();
    rememberCurrentDocView();
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

  /** True when ``outer`` fully contains ``inner``. */
  function rectContains(outer, inner) {
    return (
      outer.x1 <= inner.x1 &&
      outer.y1 <= inner.y1 &&
      outer.x2 >= inner.x2 &&
      outer.y2 >= inner.y2
    );
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

  function resizeHitMargin() {
    return RESIZE_HIT_PX / Math.max(scale, 0.05);
  }

  /**
   * @param {number} lx local x in box
   * @param {number} ly local y in box
   * @param {number} w
   * @param {number} h
   * @returns {string|null} handle id: n|s|e|w|ne|nw|se|sw
   */
  function hitResizeHandle(lx, ly, w, h) {
    const m = resizeHitMargin();
    if (lx < -m || ly < -m || lx > w + m || ly > h + m) return null;
    const nearW = lx <= m;
    const nearE = lx >= w - m;
    const nearN = ly <= m;
    const nearS = ly >= h - m;
    if (nearN && nearW) return "nw";
    if (nearN && nearE) return "ne";
    if (nearS && nearW) return "sw";
    if (nearS && nearE) return "se";
    if (nearN) return "n";
    if (nearS) return "s";
    if (nearW) return "w";
    if (nearE) return "e";
    return null;
  }

  function resizeCursorForHandle(handle) {
    if (handle === "n" || handle === "s") return "ns-resize";
    if (handle === "e" || handle === "w") return "ew-resize";
    if (handle === "ne" || handle === "sw") return "nesw-resize";
    if (handle === "nw" || handle === "se") return "nwse-resize";
    return "";
  }

  function setResizeHoverCursor(handle, hitEl) {
    if (!viewport) return;
    if (panDrag || marquee || (drag && drag.moved)) return;
    // Alt/Space pan takes the cursor; do not paint resize over grab.
    if (isPanModifierHeld()) {
      if (hitEl) hitEl.style.cursor = "";
      viewport.style.cursor = "";
      svg.style.cursor = "";
      viewport.classList.remove(
        "resize-ns",
        "resize-ew",
        "resize-nesw",
        "resize-nwse"
      );
      return;
    }
    const cur = resizeCursorForHandle(handle);
    const classes = [
      "resize-ns",
      "resize-ew",
      "resize-nesw",
      "resize-nwse",
    ];
    for (const c of classes) viewport.classList.remove(c);
    if (cur === "ns-resize") viewport.classList.add("resize-ns");
    else if (cur === "ew-resize") viewport.classList.add("resize-ew");
    else if (cur === "nesw-resize") viewport.classList.add("resize-nesw");
    else if (cur === "nwse-resize") viewport.classList.add("resize-nwse");
    if (hitEl) {
      hitEl.style.cursor = cur || "";
    }
    if (!cur) {
      viewport.style.cursor = "";
      svg.style.cursor = "";
    } else {
      viewport.style.cursor = cur;
      svg.style.cursor = cur;
    }
  }

  function clearResizeHoverCursor(hitEl) {
    if (!viewport) return;
    if (panDrag || marquee || drag) return;
    viewport.classList.remove(
      "resize-ns",
      "resize-ew",
      "resize-nesw",
      "resize-nwse"
    );
    viewport.style.cursor = "";
    svg.style.cursor = "";
    if (hitEl) hitEl.style.cursor = "";
  }

  /**
   * Apply resize from original box + world delta for a handle.
   * N/W keep the opposite edge fixed; x/y may go negative during the gesture
   * (normalized to >= 0 among siblings on drop).
   * @returns {{x:number,y:number,w:number,h:number}}
   */
  function computeResizedBox(orig, handle, dx, dy, minW, minH) {
    let x = orig.x;
    let y = orig.y;
    let w = orig.w;
    let h = orig.h;
    const right = orig.x + orig.w;
    const bottom = orig.y + orig.h;
    if (handle.includes("e")) {
      w = Math.max(minW, orig.w + dx);
    }
    if (handle.includes("s")) {
      h = Math.max(minH, orig.h + dy);
    }
    if (handle.includes("w")) {
      x = Math.min(right - minW, orig.x + dx);
      w = right - x;
    }
    if (handle.includes("n")) {
      y = Math.min(bottom - minH, orig.y + dy);
      h = bottom - y;
    }
    return { x, y, w, h };
  }

  /**
   * Shift sibling places or elements so min(x,y) >= 0. Returns shift applied.
   * @param {string|null} parentId
   * @param {"place"|"element"} kind
   * @returns {{dx:number,dy:number,siblings:object[]}}
   */
  function normalizeContentOrigin(parentId, kind) {
    const parentKey = parentId || null;
    const siblings =
      kind === "place"
        ? (graph?.nodes || []).filter((n) => (n.parent || null) === parentKey)
        : (graph?.elements || []).filter((e) => e.parent === parentId);
    let minX = Infinity;
    let minY = Infinity;
    for (const s of siblings) {
      minX = Math.min(minX, s.x ?? 0);
      minY = Math.min(minY, s.y ?? 0);
    }
    if (!Number.isFinite(minX) || !Number.isFinite(minY)) {
      return { dx: 0, dy: 0, siblings };
    }
    const dx = minX < 0 ? -minX : 0;
    const dy = minY < 0 ? -minY : 0;
    if (dx || dy) {
      for (const s of siblings) {
        s.x = (s.x ?? 0) + dx;
        s.y = (s.y ?? 0) + dy;
      }
    }
    return { dx, dy, siblings };
  }

  /**
   * Move host box west/north and grow w/h so the wall follows content.
   * @param {object} host
   * @param {number} dx
   * @param {number} dy
   */
  function expandHostForOriginShift(host, dx, dy) {
    if (!host || (!dx && !dy)) return;
    host.x = (host.x ?? 0) - dx;
    host.y = (host.y ?? 0) - dy;
    host.w = (Number(host.w) || 0) + dx;
    host.h = (Number(host.h) || 0) + dy;
    host._auto_absorb = true;
  }

  /**
   * Keep drag gesture origins aligned after a live origin absorb.
   * @param {object[]} siblings
   * @param {number} dx
   * @param {number} dy
   * @param {"place"|"element"} kind
   */
  function adjustDragOriginsAfterAbsorb(siblings, dx, dy, kind) {
    if (!drag || (!dx && !dy)) return;
    // Snapshot-based multi-drag recomputes each frame from start origins;
    // mutating origX/origY here freezes NW at 0 and looks like a pointer stop.
    if (drag.kind === "multi" && drag.layoutSnapshot) return;
    const ids = new Set(siblings.map((s) => s.id));
    if (drag.kind === "multi") {
      for (const item of drag.items || []) {
        if (!ids.has(item.id)) continue;
        if (kind === "place" && item.kind === "place") {
          item.origX += dx;
          item.origY += dy;
        } else if (kind === "element" && item.kind === "element") {
          item.origX += dx;
          item.origY += dy;
        }
      }
    } else if (drag.kind === "resize" && ids.has(drag.targetId)) {
      drag.origX += dx;
      drag.origY += dy;
    }
  }

  /**
   * Absorb negatives under parentId; expand host N/W.
   * @param {string|null} parentId
   * @param {"place"|"element"} kind
   * @param {{cascade?: boolean}} [opts] When cascade is false (live drag), only
   *   adjust the immediate host so ancestor normalization cannot nudge the
   *   opposite wall on the first NW pixels.
   * @returns {{shiftedPlaces:Set<string>,shiftedElems:Set<string>,adjustedParents:Set<string>}}
   */
  function absorbNegativeOriginLive(parentId, kind, { cascade = true } = {}) {
    const shiftedPlaces = new Set();
    const shiftedElems = new Set();
    const adjustedParents = new Set();
    let curParent = parentId;
    let curKind = kind;
    for (let guard = 0; guard < 16; guard++) {
      const { dx, dy, siblings } = normalizeContentOrigin(curParent, curKind);
      if (!dx && !dy) break;
      if (curKind === "place") {
        for (const s of siblings) shiftedPlaces.add(s.id);
      } else {
        for (const s of siblings) shiftedElems.add(s.id);
      }
      adjustDragOriginsAfterAbsorb(siblings, dx, dy, curKind);
      if (!curParent) break;
      const host = graph?.nodes.find((n) => n.id === curParent);
      if (!host) break;
      expandHostForOriginShift(host, dx, dy);
      adjustedParents.add(curParent);
      if (!cascade) break;
      // Host may now be negative among its place siblings — cascade.
      curParent = host.parent || null;
      curKind = "place";
    }
    return { shiftedPlaces, shiftedElems, adjustedParents };
  }

  /**
   * After drag/resize, renormalize any parent whose children went negative.
   * @param {{placeParents?:(string|null)[], elementParents?:string[]}} groups
   */
  function normalizeAfterLayoutGesture(groups) {
    const placeParents = new Set(groups.placeParents || []);
    const elementParents = new Set(groups.elementParents || []);
    const shiftedPlaces = new Set();
    const shiftedElems = new Set();
    const adjustedParents = new Set();
    for (const parentId of placeParents) {
      const r = absorbNegativeOriginLive(parentId, "place");
      for (const id of r.shiftedPlaces) shiftedPlaces.add(id);
      for (const id of r.adjustedParents) adjustedParents.add(id);
    }
    for (const parentId of elementParents) {
      if (!parentId) continue;
      const r = absorbNegativeOriginLive(parentId, "element");
      for (const id of r.shiftedElems) shiftedElems.add(id);
      for (const id of r.shiftedPlaces) shiftedPlaces.add(id);
      for (const id of r.adjustedParents) adjustedParents.add(id);
    }
    return { shiftedPlaces, shiftedElems, adjustedParents };
  }

  function captureLayoutSnapshot() {
    return {
      nodes: (graph?.nodes || []).map((n) => ({
        id: n.id,
        x: n.x,
        y: n.y,
        w: n.w,
        h: n.h,
        size_locked: n.size_locked,
        locked_w: n.locked_w,
        locked_h: n.locked_h,
        _originAbsorbX: n._originAbsorbX,
        _originAbsorbY: n._originAbsorbY,
      })),
      elements: (graph?.elements || []).map((e) => ({
        id: e.id,
        x: e.x,
        y: e.y,
        w: e.w,
        h: e.h,
        size_locked: e.size_locked,
        locked_w: e.locked_w,
        locked_h: e.locked_h,
      })),
    };
  }

  function restoreLayoutSnapshot(snapshot) {
    if (!snapshot || !graph) return;
    const nodesById = Object.fromEntries((graph.nodes || []).map((n) => [n.id, n]));
    const elemsById = Object.fromEntries((graph.elements || []).map((e) => [e.id, e]));
    for (const row of snapshot.nodes || []) {
      const n = nodesById[row.id];
      if (!n) continue;
      n.x = row.x;
      n.y = row.y;
      n.w = row.w;
      n.h = row.h;
      n.size_locked = row.size_locked;
      n.locked_w = row.locked_w;
      n.locked_h = row.locked_h;
      n._originAbsorbX = row._originAbsorbX;
      n._originAbsorbY = row._originAbsorbY;
      n._auto_absorb = false;
    }
    for (const row of snapshot.elements || []) {
      const e = elemsById[row.id];
      if (!e) continue;
      e.x = row.x;
      e.y = row.y;
      e.w = row.w;
      e.h = row.h;
      e.size_locked = row.size_locked;
      e.locked_w = row.locked_w;
      e.locked_h = row.locked_h;
    }
  }

  function beginResizeDrag(ev, targetKind, targetId, handle, orig) {
    drag = {
      kind: "resize",
      handle,
      targetKind,
      targetId,
      pointerId: ev.pointerId,
      startClientX: ev.clientX,
      startClientY: ev.clientY,
      origX: orig.x,
      origY: orig.y,
      origW: orig.w,
      origH: orig.h,
      moved: false,
      captured: false,
      modClick: false,
      anchorId: targetId,
      anchorKind: targetKind,
    };
  }

  function applyResizeDrag(ev) {
    if (!drag || drag.kind !== "resize") return;
    const dist = Math.hypot(
      ev.clientX - drag.startClientX,
      ev.clientY - drag.startClientY
    );
    if (!drag.moved && dist < DRAG_THRESHOLD) return;
    if (!drag.moved) {
      drag.moved = true;
      svg.classList.add("dragging", "resizing");
      const cur = resizeCursorForHandle(drag.handle);
      if (cur) {
        viewport.style.cursor = cur;
        svg.style.cursor = cur;
      }
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
    const placeMap = Object.fromEntries(
      (graph?.nodes || []).map((n) => [n.id, n])
    );
    const parent = resizeHostParent(drag.targetKind, drag.targetId, placeMap);
    const flips = parent ? ownFlips(parent) : canvasFlips();
    const d = storedDragDelta(parent, dx, dy);
    const handle = mapResizeHandleThroughFlips(drag.handle, flips);
    const minW = drag.targetKind === "element" ? ELEM_W : LEAF_W;
    const minH = drag.targetKind === "element" ? ELEM_H : LEAF_H;
    const next = computeResizedBox(
      {
        x: drag.origX,
        y: drag.origY,
        w: drag.origW,
        h: drag.origH,
      },
      handle,
      d.dx,
      d.dy,
      minW,
      minH
    );
    if (drag.targetKind === "place") {
      const node = graph?.nodes.find((n) => n.id === drag.targetId);
      if (!node) return;
      node.x = Math.round(next.x);
      node.y = Math.round(next.y);
      node.w = Math.round(next.w);
      node.h = Math.round(next.h);
      node.size_locked = true;
      node.locked_w = node.w;
      node.locked_h = node.h;
    } else {
      const elem = (graph?.elements || []).find((e) => e.id === drag.targetId);
      if (!elem) return;
      elem.x = Math.round(next.x);
      elem.y = Math.round(next.y);
      elem.w = Math.round(next.w);
      elem.h = Math.round(next.h);
      elem.size_locked = true;
      elem.locked_w = elem.w;
      elem.locked_h = elem.h;
    }
    if (drag.targetKind === "place") {
      const node = graph?.nodes.find((n) => n.id === drag.targetId);
      if (node) absorbNegativeOriginLive(node.parent || null, "place", { cascade: false });
    } else {
      const elem = (graph?.elements || []).find((e) => e.id === drag.targetId);
      if (elem?.parent) absorbNegativeOriginLive(elem.parent, "element", { cascade: false });
    }
    updateNodeVisual(null, { refresh: false });
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
    const elemById = Object.fromEntries(
      (graph?.elements || []).map((e) => [e.id, e])
    );
    const hit = additive ? new Set(selectedIds) : new Set();
    /** @type {string[]} */
    const fullContainers = [];
    /** @type {string[]} */
    const fullLeaves = [];
    /** @type {string[]} */
    const partialLeaves = [];
    for (const node of graph?.nodes || []) {
      if (!nodesById[node.id]) continue;
      const rect = placeWorldRect(node, byId);
      if (childrenOf(node.id).length) {
        // Containers: only when the marquee fully encloses the box.
        if (rectContains(worldRect, rect)) fullContainers.push(node.id);
        continue;
      }
      if (rectContains(worldRect, rect)) fullLeaves.push(node.id);
      else if (rectsIntersect(rect, worldRect)) partialLeaves.push(node.id);
    }
    const fullSet = new Set(fullContainers);
    const topContainers = fullContainers.filter(
      (id) => !selectionHasAncestorPlace(id, fullSet)
    );
    const topContainerSet = new Set(topContainers);
    for (const id of topContainers) hit.add(id);

    const fullLeafSet = new Set();
    for (const pid of fullLeaves) {
      if (selectionHasAncestorPlace(pid, topContainerSet)) continue;
      fullLeafSet.add(pid);
      hit.add(pid);
    }

    /** @type {string[]} */
    const elemHits = [];
    if (showElectrical) {
      for (const elem of graph?.elements || []) {
        if (!elementsById[elem.id]) continue;
        if (!rectsIntersect(elementWorldRect(elem, byId), worldRect)) continue;
        const parent = elem.parent;
        // Fully enclosed host (leaf or ancestor container) → host wins.
        if (
          parent &&
          (fullLeafSet.has(parent) ||
            topContainerSet.has(parent) ||
            selectionHasAncestorPlace(parent, topContainerSet) ||
            selectionHasAncestorPlace(parent, fullLeafSet))
        ) {
          continue;
        }
        elemHits.push(elem.id);
      }
    }
    // Partial leaf: if any hosted element is hit, keep elements and drop leaf.
    const hostsWithHitElems = new Set();
    for (const eid of elemHits) {
      const p = elemById[eid]?.parent;
      if (p) hostsWithHitElems.add(p);
      hit.add(eid);
    }
    for (const pid of partialLeaves) {
      if (selectionHasAncestorPlace(pid, topContainerSet)) continue;
      if (hostsWithHitElems.has(pid)) continue;
      hit.add(pid);
    }
    return normalizeSelectionSet(hit);
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
    if (showElectrical) {
      for (const e of graph.elements || []) {
        const key = e.parent || "";
        (elemsByParent[key] ||= []).push(e);
      }
    }
    function measure(node) {
      const kids = childrenOf(node.id);
      const elems = elemsByParent[node.id] || [];
      for (const kid of kids) measure(kid);
      let autoW;
      let autoH;
      if (!kids.length && !elems.length) {
        // Keep server size when no visible interior (depth / empty leaf).
        autoW =
          node.w == null
            ? leafWidthForLabel(node.display_name || node.name || node.id)
            : node.w;
        autoH = node.h == null ? LEAF_H : node.h;
      } else {
        let minL = 0;
        let minT = 0;
        let maxR = 0;
        let maxB = 0;
        for (const kid of kids) {
          const kx = kid.x ?? 0;
          const ky = kid.y ?? 0;
          minL = Math.min(minL, kx);
          minT = Math.min(minT, ky);
          maxR = Math.max(maxR, kx + nodeW(kid));
          maxB = Math.max(maxB, ky + nodeH(kid));
        }
        for (const e of elems) {
          const ex = e.x ?? 0;
          const ey = e.y ?? 0;
          minL = Math.min(minL, ex);
          minT = Math.min(minT, ey);
          maxR = Math.max(maxR, ex + (e.w ?? ELEM_W));
          maxB = Math.max(maxB, ey + (e.h ?? ELEM_H));
        }
        autoW = Math.max(LEAF_W, maxR - minL + 2 * PAD);
        autoH = Math.max(LEAF_H, HEADER + (maxB - minT) + PAD);
      }
      if (node._auto_absorb) {
        // Live NW absorb already grew w/h to keep the opposite wall fixed;
        // do not let locked/auto measure shrink that transient growth away.
        const baseW = node.size_locked
          ? Number(node.locked_w ?? node.w) || 0
          : 0;
        const baseH = node.size_locked
          ? Number(node.locked_h ?? node.h) || 0
          : 0;
        node.w = Math.max(Number(node.w) || 0, baseW, autoW);
        node.h = Math.max(Number(node.h) || 0, baseH, autoH);
        node._auto_absorb = false;
      } else if (node.size_locked) {
        const baseW = Number(node.locked_w ?? node.w) || 0;
        const baseH = Number(node.locked_h ?? node.h) || 0;
        node.w = Math.max(baseW, autoW);
        node.h = Math.max(baseH, autoH);
      } else {
        node.w = autoW;
        node.h = autoH;
      }
    }
    for (const node of childrenOf(null)) measure(node);
  }

  /**
   * Grow leaf places so inbox cable polylines stay inside the content box
   * (absolute world points → parent-local). Returns true if any size changed.
   */
  function expandPlacesForInboxCables(ptsByParent, placeById) {
    if (!ptsByParent || !placeById) return false;
    let changed = false;
    const margin = LANE_PITCH + 4;
    for (const [parentId, polys] of Object.entries(ptsByParent)) {
      if (!polys || !polys.length) continue;
      const parent = placeById[parentId];
      if (!parent) continue;
      const pa = absXY(parent, placeById);
      const ox = pa.x + PAD;
      const oy = pa.y + HEADER;
      let maxR = Math.max(0, nodeW(parent) - 2 * PAD);
      let maxB = Math.max(0, nodeH(parent) - HEADER - PAD);
      for (const pts of polys) {
        if (!pts || pts.length < 1) continue;
        for (const p of pts) {
          if (!p || p.length < 2) continue;
          const lx = p[0] - ox;
          const ly = p[1] - oy;
          // Only expand for content that sits past the current box (or
          // slightly outside — ignore far outliers from free-space hops).
          if (lx < -margin || ly < -margin) continue;
          maxR = Math.max(maxR, lx + margin);
          maxB = Math.max(maxB, ly + margin);
        }
      }
      const newW = Math.max(LEAF_W, maxR + 2 * PAD);
      const newH = Math.max(LEAF_H, HEADER + maxB + PAD);
      if (newW > (parent.w ?? 0) + 0.5 || newH > (parent.h ?? 0) + 0.5) {
        parent.w = newW;
        parent.h = newH;
        changed = true;
      }
    }
    return changed;
  }

  function absXY(node, byId) {
    const map = idMap(byId);
    if (!node.parent) {
      return mirrorTopLevel(
        node.x ?? 0,
        node.y ?? 0,
        nodeW(node),
        nodeH(node)
      );
    }
    const parent = map[node.parent];
    if (!parent) {
      return mirrorTopLevel(
        node.x ?? 0,
        node.y ?? 0,
        nodeW(node),
        nodeH(node)
      );
    }
    const pa = absXY(parent, map);
    const flips = ownFlips(parent);
    const local = mirrorLocalInParent(
      node.x ?? 0,
      node.y ?? 0,
      nodeW(node),
      nodeH(node),
      parent,
      flips
    );
    return {
      x: pa.x + PAD + local.x,
      y: pa.y + HEADER + local.y,
    };
  }

  /** Own flip flags on a graph place/element (no ancestors). */
  function ownFlips(obj) {
    return { ns: Boolean(obj?.flip_ns), we: Boolean(obj?.flip_we) };
  }

  /** Flips of the canvas location (the place currently open). */
  function canvasFlips() {
    const loc = graph?.location || {};
    return { ns: Boolean(loc.flip_ns), we: Boolean(loc.flip_we) };
  }

  /**
   * Effective flips: XOR own flags with ancestor places and the canvas
   * location flips.
   */
  function effectiveFlips(nodeOrElem, placeById) {
    let ns = Boolean(nodeOrElem?.flip_ns);
    let we = Boolean(nodeOrElem?.flip_we);
    let pid = nodeOrElem?.parent || null;
    const map = placeById || {};
    while (pid) {
      const p = map[pid];
      if (!p) break;
      ns = ns !== Boolean(p.flip_ns);
      we = we !== Boolean(p.flip_we);
      pid = p.parent || null;
    }
    const c = canvasFlips();
    ns = ns !== c.ns;
    we = we !== c.we;
    return { ns, we };
  }

  /** Remap N↔S / E↔W for drawing and routing when flipped. */
  function flipFace(face, flips) {
    let f = String(face || "").toUpperCase();
    if (flips?.ns) {
      if (f === "N") f = "S";
      else if (f === "S") f = "N";
    }
    if (flips?.we) {
      if (f === "E") f = "W";
      else if (f === "W") f = "E";
    }
    return f;
  }

  /**
   * In-place mirror frame for top-level canvas items: the AABB of current
   * top-level places/elements (stored coords), so flipping the canvas does
   * not slide the cluster to another page region.
   */
  function canvasMirrorRect() {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    let any = false;
    for (const n of graph?.nodes || []) {
      if (n.parent) continue;
      any = true;
      const x = n.x ?? 0;
      const y = n.y ?? 0;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x + nodeW(n));
      maxY = Math.max(maxY, y + nodeH(n));
    }
    for (const e of graph?.elements || []) {
      if (e.parent) continue;
      any = true;
      const x = e.x ?? 0;
      const y = e.y ?? 0;
      const w = e.w ?? ELEM_W;
      const h = e.h ?? ELEM_H;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x + w);
      maxY = Math.max(maxY, y + h);
    }
    if (!any) {
      const page = graph?.page || {};
      return {
        x: 0,
        y: 0,
        w: Number(page.width) || 2000,
        h: Number(page.height) || 1400,
      };
    }
    return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
  }

  /** Mirror a top-left origin inside an axis-aligned rect (in-place). */
  function mirrorInRect(localX, localY, childW, childH, rect, flips) {
    let x = localX;
    let y = localY;
    if (flips?.we) {
      x = rect.x + (rect.w - ((localX - rect.x) + childW));
    }
    if (flips?.ns) {
      y = rect.y + (rect.h - ((localY - rect.y) + childH));
    }
    return { x, y };
  }

  function mirrorTopLevel(x, y, w, h) {
    const flips = canvasFlips();
    if (!flips.ns && !flips.we) return { x, y };
    return mirrorInRect(x, y, w, h, canvasMirrorRect(), flips);
  }

  /** Mirror child local origin inside parent content box (PAD/HEADER aware). */
  function mirrorLocalInParent(localX, localY, childW, childH, parent, flips) {
    if (!flips?.ns && !flips?.we) return { x: localX, y: localY };
    const cw = Math.max(0, nodeW(parent) - 2 * PAD);
    const ch = Math.max(0, nodeH(parent) - HEADER - PAD);
    return mirrorInRect(localX, localY, childW, childH, { x: 0, y: 0, w: cw, h: ch }, flips);
  }

  /** Screen drag delta → stored local delta under a possibly flipped host. */
  function storedDragDelta(parent, dx, dy) {
    const flips = parent ? ownFlips(parent) : canvasFlips();
    return {
      dx: flips.we ? -dx : dx,
      dy: flips.ns ? -dy : dy,
    };
  }

  /**
   * Visual resize handle → stored-space handle when the host mirrors children.
   * Under WE flip the visual east edge is the stored west edge, etc.
   */
  function mapResizeHandleThroughFlips(handle, flips) {
    let h = String(handle || "");
    if (!flips) return h;
    if (flips.we) {
      h = h.replaceAll("e", "\0").replaceAll("w", "e").replaceAll("\0", "w");
    }
    if (flips.ns) {
      h = h.replaceAll("n", "\0").replaceAll("s", "n").replaceAll("\0", "s");
    }
    return h;
  }

  /** Host place for flip mirroring of a place/element (null = canvas root). */
  function resizeHostParent(targetKind, targetId, placeMap) {
    if (targetKind === "place") {
      const node = graph?.nodes.find((n) => n.id === targetId);
      return node?.parent ? placeMap[node.parent] || null : null;
    }
    const elem = (graph?.elements || []).find((e) => e.id === targetId);
    return elem?.parent ? placeMap[elem.parent] || null : null;
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
  function planeAnchorLocal(node, openingId, face, byId) {
    const w = nodeW(node);
    const h = nodeH(node);
    const plane = parsePlaneOpening(openingId);
    const f = (plane?.face || face || "?").toUpperCase();
    if (!plane || (f !== "B" && f !== "F")) {
      return { x: w / 2, y: h / 2 };
    }
    const { cols, rows } = planeGridDims(node, f, plane);
    const flips = effectiveFlips(node, idMap(byId));
    let col = plane.col;
    let row = plane.row;
    if (flips.we) col = cols + 1 - col;
    if (flips.ns) row = rows + 1 - row;
    let x = planeCellCenter(w, cols, col, PLANE_R);
    let y = planeCellCenter(h, rows, row, PLANE_R);
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
    const local = openingAnchorLocal(node, openingId, face, byId);
    return { x: a.x + local.x, y: a.y + local.y };
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
    const local = planeAnchorLocal(node, openingId, f, byId);
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
  function openingAnchorLocal(node, openingId, face, byId) {
    const w = nodeW(node);
    const h = nodeH(node);
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
    if (visualFace === "N") return { x: t * w, y: 0, face: visualFace };
    if (visualFace === "S") return { x: t * w, y: h, face: visualFace };
    if (visualFace === "W") return { x: 0, y: t * h, face: visualFace };
    if (visualFace === "E") return { x: w, y: t * h, face: visualFace };
    return { x: w / 2, y: h / 2, face: visualFace };
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

  /** Shrunk leaf-place rects as routing obstacles (skip rooms/containers). */
  function placeObstacles(byId, excludeIds, inset) {
    const pad = inset == null ? 8 : inset;
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
    if (routeGeomCache && routeGeomCache.placeById === byId) {
      return routeGeomCache.borderRects;
    }
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
   */
  function mouthFanPts(mouth, face, laneDist, toward) {
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
    const stub = stubPoint({ x: mx, y: my }, oi.x, oi.y, INBOX_STUB);
    /** @type {number[][]} */
    const pts = [
      [mx, my],
      [stub.x, stub.y],
    ];
    if (Math.abs(laneDist) < 1e-9) return pts;
    const latX = -oi.y;
    const latY = oi.x;
    // Always deeper into the box than the stub (never back toward the boca).
    // Negative lanes get an extra half-pitch so tip latitudes stay unique.
    const depthAlong =
      Math.abs(laneDist) +
      (laneDist < 0 ? Math.max(6, (STRAND_WIDTH + LANE_GAP) * 0.5) : 0);
    pts.push([
      stub.x + latX * laneDist + oi.x * depthAlong,
      stub.y + latY * laneDist + oi.y * depthAlong,
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
    return { d: pointsToPathD(pts), segs: segsFromPoints(pts, half) };
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
    // Same content origin as nested locations (PAD / HEADER).
    return {
      x: a.x + PAD + local.x,
      y: a.y + HEADER + local.y,
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
    // Face-cell pin ids (N2, S1, …) attach even if instance terminals omitted
    // them from terminal_pins while the catalog grid still paints the cell.
    if (!cell && pin && cellIdOnElementGrid(elem, pin)) {
      cell = String(pin);
    }
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
   * else the canvas background (loose wire with no sheath / uncolored tube).
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
    /** @type {Map<string, string[]>} */
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
        if (!jacketsByConduit.has(cid)) jacketsByConduit.set(cid, []);
        if (!jacketsByConduit.get(cid).includes(key)) {
          jacketsByConduit.get(cid).push(key);
        }
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

    /** @type {Map<string, {index:number, count:number}>} */
    const routeLaneMap = new Map();
    packLaneGroups(byRoute, (item, index, count) => {
      routeLaneMap.set(`${item.key}|${item.wi}`, { index, count });
    });

    /** @type {Map<string, {index:number, count:number}>} */
    const jacketMap = new Map();
    for (const [cid, keys] of jacketsByConduit) {
      keys.sort();
      const count = keys.length;
      keys.forEach((key, index) => {
        jacketMap.set(`${cid}|${key}`, { index, count });
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
        if (!conduitId) return { index: 0, count: 1 };
        return (
          jacketMap.get(`${conduitId}|${cableEdgeKey(edge)}`) || {
            index: 0,
            count: 1,
          }
        );
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
    return orthoRoute(
      { x: a[0], y: a[1] },
      { x: b[0], y: b[1] },
      null,
      null,
      occupied || null,
      obstacles,
      stayBounds || null,
      null
    );
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
      // V leg touches the pin: pin → tip (one short diagonal). Opposite slots
      // fan to opposite laterals so both arms of the V are diagonal — never
      // one diagonal and one vertical. A short rail past the tip keeps the
      // strand on its lateral until the spine join (meet only at the pin).
      // Never overshoot the lane target along the face normal — that forced
      // an up-then-down join (diamond / out-and-back into the pin).
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
   * Join a terminal lead (pin→…→rail) to a mouth-fan tip without collapsing
   * onto a shared horizontal at rail-Y (Test_01 y=420 trunk).
   * Always travel on the pin-face column/row first (N/S → rail.x, E/W →
   * rail.y), then across at the fan-tip latitude — never pick the axis by
   * which delta is larger (that recreated the shared rail-Y crawl).
   * When the simple join would pierce a foreign element (rule 17), detour
   * with ``orthoRoute`` instead.
   */
  function joinLeadToFanTip(lead, fanTip, face, obstacles) {
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
    if (ns) {
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
        // Only strip orthogonal Z jogs — never touch terminal V diagonals.
        const abDiag = Math.abs(abx) > 1e-6 && Math.abs(aby) > 1e-6;
        const bcDiag = Math.abs(bcx) > 1e-6 && Math.abs(bcy) > 1e-6;
        const cdDiag = Math.abs(cdx) > 1e-6 && Math.abs(cdy) > 1e-6;
        if (abDiag || bcDiag || cdDiag) continue;
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
    const item =
      (hop.conduit && edgePathsByConduitId.get(hop.conduit)) ||
      edgePaths.find((e) => e.edge && e.edge.id === hop.conduit);
    if (!item || !item.d) return null;
    const e = item.edge;
    if (e.from === hop.from && e.to === hop.to) return item.d;
    if (e.from === hop.to && e.to === hop.from) return reversePathD(item.d);
    return null;
  }

  /**
   * Base polylines for a cable edge.
   * @param {{fromSlot?:{slot:number,count:number}, toSlot?:{slot:number,count:number}, laneDist?:number, laneDistForConduit?:(conduitId:string)=>number, fromPin?:string|null, toPin?:string|null}|undefined} opts
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
    const laneDistFallback = opts?.laneDist || 0;
    const laneCountHint = Math.max(
      1,
      fromSlot.count | 0,
      toSlot.count | 0,
      opts?.laneCount | 0
    );
    const laneDistForConduit = opts?.laneDistForConduit;
    const fromPin = opts?.fromPin != null ? opts.fromPin : edge.from_pin;
    const toPin = opts?.toPin != null ? opts.toPin : edge.to_pin;
    const laneDistFor = (conduitId) => {
      if (conduitId && typeof laneDistForConduit === "function") {
        return laneDistForConduit(conduitId) || 0;
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
        stayBounds = {
          x: pa.x + PAD,
          y: pa.y + HEADER,
          w: Math.max(4, nodeW(parent) - 2 * PAD),
          h: Math.max(4, nodeH(parent) - HEADER - PAD),
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
        const tubeD = hopTubePathD(hop);
        let ext = null;
        if (tubeD) {
          // Keep the conduit centerline intact. ``exteriorPathD`` drops any
          // segment that skims a place border and was truncating bocas
          // (Test_01 lamp vertical never reached the painted tube end).
          ext = tubeD;
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
          const hopDist = laneDistFor(hop.conduit);
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
      const startElemObs = elementObstacles(elemById, placeById, null, 2);
      const endElemObs = elementObstacles(elemById, placeById, null, 2);

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
      const multiAtOpening =
        Math.abs(startLaneDist) >= 1e-9 || Math.abs(endLaneDist) >= 1e-9;
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

      // Fan from the lane crossing. Multi-cable already carries lateral in the
      // crossing (laneDist=0 here); single-cable may still use laneDist=0.
      const startFan = mouthFanPts(
        startCrossing,
        startMouthFace,
        0,
        startAtt
      );
      const endFan = mouthFanPts(endCrossing, endMouthFace, 0, endAtt);
      // Toward mouth: fan → stub → crossing. Join lead to fan tip via
      // joinLeadToFanTip (column-first) so lanes do not share rail-Y.
      const startFanRev = startFan.slice().reverse();
      const startLead = pinToLanePts(
        [startAtt.x, startAtt.y],
        startFace,
        startFanRev[0],
        fromSlot.slot,
        fromSlot.count
      );
      let head = joinLeadToFanTip(startLead, startFanRev[0], startFace, startElemObs);
      if (startFanRev.length > 1) {
        head = mergeOrthoPolys(head, startFanRev.slice(1)) || head;
      }
      {
        const before = head.map((p) => [p[0], p[1]]);
        head = stripShortZJogs(
          stripOutAndBack(head, [startCrossing, startFanRev[0], ...startFan])
        );
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
      const endLead = pinToLanePts(
        [endAtt.x, endAtt.y],
        endFace,
        endFanTip,
        toSlot.slot,
        toSlot.count
      );
      // pin → … → fan tip → stub → crossing, then reverse to crossing→…→pin.
      let tailFromPin = joinLeadToFanTip(endLead, endFanTip, endFace, endElemObs);
      const fanToMouth = endFanFwd.slice().reverse(); // fan, stub, crossing
      if (fanToMouth.length > 1) {
        tailFromPin =
          mergeOrthoPolys(tailFromPin, fanToMouth.slice(1)) || tailFromPin;
      }
      {
        const before = tailFromPin.map((p) => [p[0], p[1]]);
        tailFromPin = stripShortZJogs(
          stripOutAndBack(tailFromPin, [endCrossing, endFanTip, ...endFanFwd])
        );
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
          const jacket = el("path", {
            class: "cable-jacket",
            d: jd,
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
          cablesG.appendChild(jacket);
          paths.push(jacket);
        }
      };
      const jacketMetrics = (cid) => {
        const laneInfos = wireIdx.map((wi) =>
          layout.laneOnConduit(cid, edge, wi)
        );
        const count = laneInfos[0]?.count || wireIdx.length;
        const indices = laneInfos.map((l) => l.index);
        const i0 = Math.min(...indices);
        const i1 = Math.max(...indices);
        return {
          midOff:
            (highwayLaneOffset(i0, count) + highwayLaneOffset(i1, count)) / 2,
          jw: highwaySpanWidth(i1 - i0 + 1) + 1.2,
        };
      };
      const hops = edge.conduit_hops || [];
      if (hops.length) {
        for (const hop of hops) {
          const tubeD = hopTubePathD(hop);
          if (!tubeD || !hop.conduit) continue;
          const fakeEdge = {
            from: hop.from,
            to: hop.to,
            from_opening: hop.from_opening,
            to_opening: hop.to_opening,
          };
          const { midOff, jw } = jacketMetrics(hop.conduit);
          paintJacketD(conduitDisplayD(tubeD, placeById, fakeEdge), midOff, jw);
        }
      } else if (edge.conduit) {
        const item =
          edgePathsByConduitId.get(edge.conduit) ||
          edgePaths.find((e) => e.edge && e.edge.id === edge.conduit);
        if (item && item.d) {
          const { midOff, jw } = jacketMetrics(edge.conduit);
          paintJacketD(
            conduitDisplayD(item.d, placeById, item.edge),
            midOff,
            jw
          );
        }
      }
    }

    const paintStrand = (d, code, title) => {
      if (!d) return;
      const key = String(code || "").toUpperCase();
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
        const gn = el("path", { class: "cable-strand", d });
        gn.setAttribute("stroke", gnCss);
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
      const strand = el("path", { class: "cable-strand", d });
      strand.setAttribute("stroke", fillCss);
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
      for (const sub of strandSubs) {
        paintStrand(
          pointsToPathD(sub),
          code,
          `${edgeName} · ${code}${edge.via ? ` (${edge.via})` : ""}`
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
   * @param {{ skipConduits?: boolean }} [opts] When skipConduits, reuse existing
   *   tube ``d`` (element-only drag) and only rebuild cable layers.
   */
  function refreshEdges(opts) {
    if (!graph) return;
    const skipConduits = !!(opts && opts.skipConduits);
    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    const elemById = Object.fromEntries(
      (graph.elements || []).map((e) => [e.id, e])
    );
    beginRouteGeomCache(byId, elemById);
    try {
      /** @type {ReturnType<typeof createOccupiedIndex>} */
      const occupied = createOccupiedIndex();
      const layoutForTubes = showElectrical
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
            item.d = routed.d;
            const displayD = conduitDisplayD(routed.d, byId, item.edge);
            for (const path of item.paths) path.setAttribute("d", displayD);
            for (const s of routed.segs) occupied.push(s);
            const outline = item.paths[0];
            const tube = item.paths[1] || item.paths[0];
            const tubeCss = wireColorCss(item.edge.color || "GY");
            if (outline && item.paths.length > 1) {
              applyTubeOutlineVisibility(outline, tubeCss, roadW);
            }
            if (tube) {
              tube.style.strokeWidth = String(roadW);
              tube.style.stroke = tubeCss;
              tube.style.strokeOpacity = item.edge.color ? "0.85" : "0.25";
            }
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
      // Rebuild cable layers (jacket + strands) from scratch.
      const cablesG = worldEl && worldEl.querySelector("g.cables");
      if (cablesG && showElectrical) {
        cablesG.innerHTML = "";
        cablePaths = [];
        const layout =
          layoutForTubes ||
          buildCableLayout(graph.cable_edges || [], elemById, byId);
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
    } finally {
      endRouteGeomCache();
    }
  }

  function syncOpeningMarks(node) {
    const g = nodesById[node.id];
    if (!g || !node.openings?.length) return;
    const w = nodeW(node);
    const h = nodeH(node);
    const placeMap = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
    for (const op of node.openings) {
      const face = (op.face || op.id?.[0] || "?").toUpperCase();
      const anchor = openingAnchorLocal(node, op.id, face, placeMap);
      const visualFace = anchor.face || flipFace(face, effectiveFlips(node, placeMap));
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
        visualFace === "W" ? 4 : visualFace === "E" ? w - 4 : anchor.x;
      const labelY =
        visualFace === "N" ? 10 : visualFace === "S" ? h - 3 : anchor.y + 3;
      text.setAttribute("x", String(labelX));
      text.setAttribute("y", String(labelY));
      text.setAttribute(
        "text-anchor",
        visualFace === "W" ? "start" : visualFace === "E" ? "end" : "middle"
      );
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
        w - 4
      );
    }
    const typeEl = g.querySelector("text.element-type");
    if (typeEl) {
      typeEl.textContent = fitLabel(
        elem.type_label || elem.type || "",
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
    if (refresh) {
      refreshEdges(
        opts && opts.skipConduits ? { skipConduits: true } : undefined
      );
    }
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
        const anchor = openingAnchorLocal(node, op.id, op.face, byId);
        const visualFace = anchor.face || op.face;
        const labelX =
          visualFace === "W" ? 4 : visualFace === "E" ? w - 4 : anchor.x;
        const labelY =
          visualFace === "N" ? 10 : visualFace === "S" ? h - 3 : anchor.y + 3;
        g.appendChild(
          el(
            "text",
            {
              class: "opening-side",
              "data-opening": op.id,
              x: labelX,
              y: labelY,
              "text-anchor":
                visualFace === "W"
                  ? "start"
                  : visualFace === "E"
                    ? "end"
                    : "middle",
            },
            op.id
          )
        );
      }
      for (const op of planes) {
        const anchor = openingAnchorLocal(node, op.id, op.face, byId);
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
      if (shouldPanPointer(ev)) {
        ev.preventDefault();
        ev.stopPropagation();
        beginPanDrag(ev);
        return;
      }
      if (ev.button !== 0) return;
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
          const local = terminalCellAnchorLocal(elem, cellId, placeById);
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
      if (shouldPanPointer(ev)) {
        ev.preventDefault();
        ev.stopPropagation();
        beginPanDrag(ev);
        return;
      }
      if (ev.button !== 0) return;
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
    ensurePositions();
    measureVisibleSizes();

    const byId = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    const elemById = Object.fromEntries(
      (graph.elements || []).map((e) => [e.id, e])
    );

    /** @type {ReturnType<typeof buildCableLayout>|null} */
    let layout = null;
    if (showElectrical) {
      layout = buildCableLayout(graph.cable_edges || [], elemById, byId);
      if (expandElementsForTerminalFans(layout, elemById)) {
        measureVisibleSizes();
        // Rebuild so attach points use the widened terminal spacing.
        layout = buildCableLayout(graph.cable_edges || [], elemById, byId);
      }
    }

    clearSvg();

    worldEl = el("g", { id: "world" });
    applyWorldTransform();
    svg.appendChild(worldEl);

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

    beginRouteGeomCache(byId, elemById);
    try {
      const byDepth = [...graph.nodes].sort(
        (a, b) => (a.parts?.length || 0) - (b.parts?.length || 0)
      );
      for (const node of byDepth) {
        if (childrenOf(node.id).length) paintNode(node, containersG, byId);
      }

      /** @type {ReturnType<typeof createOccupiedIndex>} */
      const occupied = createOccupiedIndex();
      for (const edge of graph.edges) {
        const n = (edge.contains || []).length;
        const lanes = tubeLaneCount(edge, layout);
        const roadW = conduitRoadWidth(n, lanes);
        const half = roadW / 2;
        const routed = edgePathD(edge, byId, occupied, half);
        if (!routed) continue;
        const d = routed.d;
        for (const s of routed.segs) occupied.push(s);
        const contains = (edge.contains || []).join(", ");
        const edgeName = edge.name || edge.id;
        const title = contains
          ? `${edgeName}: ${contains}`
          : String(edgeName || "");
        const displayD = conduitDisplayD(d, byId, edge);
        const tubeCss = wireColorCss(edge.color || "GY");
        // Rim only when the tube would blend into the canvas background.
        const tubeOutline = el("path", {
          class: "edge-tube-outline",
          d: displayD,
        });
        applyTubeOutlineVisibility(tubeOutline, tubeCss, roadW);
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
      indexEdgePaths();

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
      if (showElectrical && layout) {
        inboxCablePtsByParent = {};
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
        if (
          renderExpandPass < 1 &&
          expandPlacesForInboxCables(inboxCablePtsByParent, byId)
        ) {
          // Grow boxes in-place and re-route tubes/cables only — avoid a second
          // full clearSvg + paint of every node (old recursive render()).
          inboxCablePtsByParent = null;
          renderExpandPass += 1;
          updateNodeVisual(null);
          renderExpandPass = 0;
          updateDepthLabel();
          return;
        }
        inboxCablePtsByParent = null;
      }
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
    if (elements) {
      elements.classList.toggle(
        "hidden",
        !placeMode || !showElectrical || !propsShowElements
      );
    }
    if (conduits) conduits.classList.toggle("hidden", !placeMode);
    if (cables) cables.classList.toggle("hidden", placeMode);
  }

  /**
   * True when this place's electrical elements are painted on the canvas
   * (electrical on + leaf place in the current depth view).
   */
  let propsShowElements = false;

  function placeShowsElementsInView(placeRelId) {
    if (!showElectrical || !graph) return false;
    // Canvas root elements use parent=null and stay visible even with children.
    if (!placeRelId || placeRelId === ".") return true;
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
    /** @type {Record<string, string|boolean>} */
    const fields = {};
    if (!meta) return fields;
    meta.querySelectorAll("[data-prop]").forEach((el) => {
      const key = el.getAttribute("data-prop");
      if (!key) return;
      if (el.type === "checkbox") fields[key] = el.checked;
      else fields[key] = el.value;
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
          optionEl.textContent = propsValueLabel(spec.combo, opt);
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
    setStatus(
      res.dirty ? "flip updated · unsaved" : "flip updated"
    );
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
    setStatus(
      res.dirty ? "properties updated · unsaved" : "properties updated"
    );
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
    appendPropsRow(meta, {
      key: "subtype",
      value: elem.subtype || "",
      editable: false,
    });
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
    appendPropsRow(meta, {
      key: "terminals",
      value: (elem.terminals || []).join(", "),
      editable: false,
    });
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

  async function fillPlaceInspector(id, detailOpt) {
    await flushPendingPropsSave();
    const empty = document.getElementById("panel-empty");
    const panel = document.getElementById("panel-props");
    if (!empty || !panel) {
      setStatus("Properties panel missing — hard-reload the page (Ctrl+Shift+R)");
      return;
    }
    if (!id || !locationId) {
      propsTarget = null;
      propsFieldsBaseline = null;
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
      appendPropsRow(meta, {
        key: "subtype",
        value: detail.subtype || "",
        editable: false,
      });
      appendPropsRow(meta, {
        key: "install",
        value: detail.install || "",
        editable: true,
        combo: "install",
        options: ["surface", "in_wall"],
      });
      appendPropsRow(meta, {
        key: "mount",
        value: detail.mount || "",
        editable: true,
        combo: "mount",
        options: ["wall", "ceiling", "floor"],
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
    setSelectedVisual();
    if (selectedIds.size === 0) {
      highlightOutlineSelection();
      await fillPlaceInspector(null);
      return;
    }
    if (selectedIds.size > 1) {
      setStatus(`${selectedIds.size} selected`);
      highlightOutlineSelection();
      await fillPlaceInspector(null);
      return;
    }
    highlightOutlineSelection();
    const elem = (graph?.elements || []).find((e) => e.id === selectedId);
    if (elem) await fillElementInspector(elem);
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
      depthLevel = DEPTH_MAX_REQUEST;
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
      // Full paint when electrical is on so terminal fans / inbox expansion
      // and cable attach points match the new box size.
      if (showElectrical) render();
      else updateNodeVisual(null);
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
          setStatus(
            lastMeta && lastMeta.dirty
              ? t("status.resizedPlaceUnsaved")
              : t("status.resizedPlace")
          );
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
          setStatus(
            lastMeta && lastMeta.dirty
              ? t("status.resizedElementUnsaved")
              : t("status.resizedElement")
          );
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
    updateNodeVisual(
      null,
      onlyElements && !hostsChanged ? { skipConduits: true } : undefined
    );
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
      setStatus(
        lastMeta && lastMeta.dirty
          ? t("status.movedUnsaved", { n })
          : t("status.moved", { n })
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
        return;
      }
      const n = (st.dirty || []).length;
      const dirty = n > 0 || dirtyLocal;
      setStatus(
        n
          ? t("status.dirty", { n })
          : dirtyLocal
            ? t("status.layoutPending")
            : t("status.savedOk")
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
    setStatus(t("status.saved", { n: (data.saved || []).length }));
    applyEditFlags(data);
    dirtyLocal = false;
    updateSaveButton(false);
    await refreshDocumentLabel();
    return data;
  }

  function rememberCurrentDocView() {
    if (!activeDocId) return;
    docViews[activeDocId] = {
      locationId,
      depthLevel,
      showElectrical: Boolean(showElectrical),
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
  }

  function setElectrical(on) {
    showElectrical = Boolean(on);
    syncElectricalUi();
    if (!showElectrical && selectedId) {
      const isElem = (graph?.elements || []).some((e) => e.id === selectedId);
      if (isElem) clearSelectionState();
    }
    render();
    renderOutline();
    rememberCurrentDocView();
    syncInspectorFromSelection().catch((err) =>
      setStatus(String(err.message || err))
    );
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
      persistDocViews();
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
    if (!hasDocument) {
      try {
        applyWorkspaceStatus(await api("/api/workspace"));
      } catch {
        /* keep current state */
      }
    }
    await refreshDocumentLabel();
    if (!hasDocument) {
      canvasLocations = [];
      svg.innerHTML = "";
      return;
    }
    const data = await api("/api/locations");
    canvasLocations = data.locations || [];
    const saved = activeDocId ? docViews[activeDocId] : null;
    // Restore electrical before outline so element rows match the canvas view.
    if (saved && typeof saved.showElectrical === "boolean") {
      showElectrical = saved.showElectrical;
      syncElectricalUi();
    }
    await loadOutline();
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
      else depthLevel = DEPTH_DEFAULT;
      const hasCamera =
        saved &&
        Number.isFinite(saved.panX) &&
        Number.isFinite(saved.panY) &&
        Number.isFinite(saved.scale);
      await setCanvasLocation(target.id, {
        resetDepth: !saved,
        fit: !hasCamera,
      });
      if (hasCamera) applySavedCamera(saved);
    } else {
      setStatus("No locations with children found");
    }
  }

  async function refreshDocumentLabel() {
    // File identity is shown in view tabs; no separate header label.
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
      label.title = doc.yaml_path || doc.path || doc.title || doc.yaml || "";
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

  async function setCanvasLocation(id, { resetDepth = true, fit = true } = {}) {
    if (!id) return;
    if (resetDepth) depthLevel = DEPTH_DEFAULT;
    locationId = id;
    rememberCurrentDocView();
    await loadLocation({ fit });
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
          ? iconHtml("chevron-down")
          : iconHtml("chevron-right");
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

      const icon = iconElement(node.icon, "outline-icon");
      if (icon) row.appendChild(icon);

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
    applyOutlineSelectionActive();
  }

  /** Site ids for every canvas selection (for outline multi-highlight). */
  function selectionSiteIds() {
    const out = new Set();
    for (const id of selectedIds) {
      out.add(canvasToSiteId(id));
    }
    if (!out.size && locationId) out.add(locationId);
    return out;
  }

  function applyOutlineSelectionActive() {
    const host = document.getElementById("outline-tree");
    if (!host) return;
    const active = selectionSiteIds();
    for (const btn of host.querySelectorAll(".outline-item")) {
      const id = btn.dataset.id;
      btn.classList.toggle("active", active.has(id));
    }
  }

  /** Scroll the outline list so ``siteId`` is in view. */
  function scrollOutlineToSiteId(siteId) {
    if (!siteId) return;
    const host = document.getElementById("outline-tree");
    if (!host) return;
    let row = null;
    for (const btn of host.querySelectorAll(".outline-item")) {
      if (btn.dataset.id === siteId) {
        row = btn;
        break;
      }
    }
    if (!row) return;
    // Expand outline section if it was collapsed in the accordion.
    const outlineSec = document.getElementById("outline-section");
    if (outlineSec?.classList.contains("collapsed")) {
      outlineSec.classList.remove("collapsed");
      try {
        sessionStorage.setItem("housewire-nav-outline-open", "1");
      } catch {
        /* ignore */
      }
      document.getElementById("btn-toggle-outline-section")?.setAttribute(
        "aria-expanded",
        "true"
      );
      const chev = document
        .getElementById("btn-toggle-outline-section")
        ?.querySelector(".nav-section-chevron");
      if (chev) chev.innerHTML = iconHtml("chevron-down");
      const paletteSec = document.getElementById("palette-section");
      const resizer = document.getElementById("resizer-nav-split");
      if (paletteSec && !paletteSec.classList.contains("collapsed")) {
        resizer?.classList.remove("hidden");
        let frac = 0.55;
        try {
          const v = Number(sessionStorage.getItem("housewire-nav-split"));
          if (Number.isFinite(v) && v > 0.1 && v < 0.9) frac = v;
        } catch {
          /* ignore */
        }
        outlineSec.style.flex = `${frac} 1 0`;
        paletteSec.style.flex = `${1 - frac} 1 0`;
      } else {
        outlineSec.style.flex = "1 1 auto";
      }
    }
    row.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  function highlightOutlineSelection(opts) {
    const scrollToId = opts && opts.scrollTo != null ? opts.scrollTo : selectedId;
    let needPaint = false;
    const before = collapsedOutline.size;
    for (const id of selectedIds) {
      const siteId = canvasToSiteId(id);
      if (!siteId) continue;
      expandOutlineAncestors(siteId);
      if (
        outlineNodes.some((n) => n.id === siteId && isOutlineHidden(n))
      ) {
        needPaint = true;
      }
    }
    if (before !== collapsedOutline.size) needPaint = true;
    if (needPaint) renderOutline();
    else applyOutlineSelectionActive();
    const focusSite = scrollToId ? canvasToSiteId(scrollToId) : null;
    if (focusSite) {
      // After expand/re-render, wait a frame so the row exists and layout is ready.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => scrollOutlineToSiteId(focusSite));
      });
    }
  }

  /** @deprecated Prefer highlightOutlineSelection for canvas selection. */
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
    rememberCurrentDocView();
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
  document.getElementById("btn-delete")?.addEventListener("click", () => {
    deleteSelection().catch((err) => setStatus(String(err.message || err)));
  });
  document.getElementById("btn-cut")?.addEventListener("click", () => {
    cutSelection().catch((err) => setStatus(String(err.message || err)));
  });
  document.getElementById("btn-copy")?.addEventListener("click", () => {
    copySelection().catch((err) => setStatus(String(err.message || err)));
  });
  document.getElementById("btn-paste")?.addEventListener("click", () => {
    pasteClipboard().catch((err) => setStatus(String(err.message || err)));
  });

  document.addEventListener("keydown", (ev) => {
    if (isEditableFocus(ev.target)) return;
    const mod = ev.ctrlKey || ev.metaKey;
    if (!mod) {
      if (ev.key === "Delete" || ev.key === "Backspace") {
        const appModal = document.getElementById("app-modal");
        const insertModal = document.getElementById("insert-modal");
        if (appModal && !appModal.classList.contains("hidden")) return;
        if (insertModal && !insertModal.classList.contains("hidden")) return;
        if (selectedIds.size < 1) return;
        ev.preventDefault();
        deleteSelection().catch((err) => setStatus(String(err.message || err)));
      }
      return;
    }
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
    if (key === "x") {
      ev.preventDefault();
      cutSelection().catch((err) => setStatus(String(err.message || err)));
      return;
    }
    if (key === "c") {
      ev.preventDefault();
      copySelection().catch((err) => setStatus(String(err.message || err)));
      return;
    }
    if (key === "v") {
      ev.preventDefault();
      pasteClipboard().catch((err) => setStatus(String(err.message || err)));
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

  const PANEL_MIN_W = 180;
  const PANEL_MAX_FRAC = 0.45;
  const PANEL_DEFAULT_OUTLINE_W = 260;
  const PANEL_DEFAULT_INSPECTOR_W = 320;

  function workspaceBounds() {
    const ws = document.querySelector(".workspace");
    return ws ? ws.getBoundingClientRect() : null;
  }

  function clampPanelWidth(raw) {
    const bounds = workspaceBounds();
    const maxW = bounds ? Math.max(PANEL_MIN_W, bounds.width * PANEL_MAX_FRAC) : 420;
    return Math.min(maxW, Math.max(PANEL_MIN_W, Number(raw) || PANEL_MIN_W));
  }

  function applyPanelWidths() {
    const tree = document.getElementById("nav-tree");
    const side = document.getElementById("side-panel");
    if (!tree || !side) return;
    try {
      const ow = Number(sessionStorage.getItem("housewire-outline-width")) || 0;
      const sw = Number(sessionStorage.getItem("housewire-inspector-width")) || 0;
      tree.style.width = `${clampPanelWidth(ow || PANEL_DEFAULT_OUTLINE_W)}px`;
      side.style.width = `${clampPanelWidth(sw || PANEL_DEFAULT_INSPECTOR_W)}px`;
    } catch {
      tree.style.width = `${PANEL_DEFAULT_OUTLINE_W}px`;
      side.style.width = `${PANEL_DEFAULT_INSPECTOR_W}px`;
    }
  }

  function setPanelWidth(which, widthPx) {
    const tree = document.getElementById("nav-tree");
    const side = document.getElementById("side-panel");
    const w = clampPanelWidth(widthPx);
    if (which === "outline" && tree) {
      tree.style.width = `${w}px`;
      try {
        sessionStorage.setItem("housewire-outline-width", String(Math.round(w)));
      } catch {
        /* ignore */
      }
    }
    if (which === "inspector" && side) {
      side.style.width = `${w}px`;
      try {
        sessionStorage.setItem("housewire-inspector-width", String(Math.round(w)));
      } catch {
        /* ignore */
      }
    }
  }

  function syncPanelResizers() {
    const tree = document.getElementById("nav-tree");
    const side = document.getElementById("side-panel");
    const ro = document.getElementById("resizer-outline");
    const rs = document.getElementById("resizer-inspector");
    if (ro && tree) ro.classList.toggle("hidden", tree.classList.contains("collapsed"));
    if (rs && side) rs.classList.toggle("hidden", side.classList.contains("collapsed"));
  }

  function bindPanelResizeDrag() {
    const ro = document.getElementById("resizer-outline");
    const rs = document.getElementById("resizer-inspector");
    const onStart = (which, ev) => {
      ev.preventDefault();
      const bounds = workspaceBounds();
      if (!bounds) return;
      const move = (mev) => {
        const x = mev.clientX;
        if (which === "outline") setPanelWidth("outline", x - bounds.left);
        else setPanelWidth("inspector", bounds.right - x);
      };
      const up = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        document.body.style.cursor = "";
      };
      document.body.style.cursor = "ew-resize";
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up, { once: true });
    };
    ro?.addEventListener("pointerdown", (ev) => onStart("outline", ev));
    rs?.addEventListener("pointerdown", (ev) => onStart("inspector", ev));
  }

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
    syncPanelResizers();
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
  applyPanelWidths();
  bindPanelResizeDrag();
  syncPanelResizers();
  window.addEventListener("resize", () => {
    applyPanelWidths();
  });

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
        const action = insertItem.getAttribute("data-insert-action");
        if (action === "element" || action === "container") {
          openTypePickerFromInsert(action).catch((err) => insertMsg(String(err.message || err), true));
        } else {
          openInsertModal(action);
        }
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
      } else if (action === "cut") {
        cutSelection().catch((err) => setStatus(String(err.message || err)));
      } else if (action === "copy") {
        copySelection().catch((err) => setStatus(String(err.message || err)));
      } else if (action === "paste") {
        pasteClipboard().catch((err) => setStatus(String(err.message || err)));
      } else if (action === "delete") {
        deleteSelection().catch((err) => setStatus(String(err.message || err)));
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

  function syncLanguageMenu() {
    const loc = I18n.getLocale ? I18n.getLocale() : "en";
    const en = document.getElementById("menu-lang-en");
    const es = document.getElementById("menu-lang-es");
    if (en) en.setAttribute("aria-checked", loc === "en" ? "true" : "false");
    if (es) es.setAttribute("aria-checked", loc === "es" ? "true" : "false");
  }

  async function setUiLocale(next) {
    I18n.setLocale(next);
    syncLanguageMenu();
    relabelPropertyPanel();
    const aboutModal = document.getElementById("about-modal");
    if (aboutModal && !aboutModal.classList.contains("hidden")) {
      openAboutModal().catch((err) => setStatus(String(err.message || err)));
    }
    try {
      await loadPaletteCatalog(true);
      renderPaletteSideList();
      refreshOpenCatalogInsertLabels();
    } catch (err) {
      setStatus(String(err.message || err));
    }
    if (hasDocument && locationId) {
      try {
        await loadGraph();
        await loadOutline();
        await syncInspectorFromSelection();
      } catch (err) {
        setStatus(String(err.message || err));
      }
    }
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
    // Tube/strand contrast rims depend on canvas ``--bg``.
    if (graph) render();
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
      if (action === "lang-en" || action === "lang-es") {
        closeAllMenus();
        setUiLocale(action === "lang-es" ? "es" : "en").catch((err) =>
          setStatus(String(err.message || err))
        );
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

    const languageHost = menuView.querySelector("#menu-language-btn")
      ? menuView.querySelector("#menu-language-btn").closest(".menu-item-submenu")
      : null;
    if (languageHost) {
      languageHost.addEventListener("mouseenter", () => {
        const flyout = languageHost.querySelector(".menu-flyout");
        const trigger = languageHost.querySelector(".menu-submenu-trigger");
        if (!flyout || !trigger) return;
        flyout.classList.remove("hidden");
        languageHost.classList.add("is-open");
        trigger.setAttribute("aria-expanded", "true");
      });
    }
  }

  syncThemeMenu();
  syncLanguageMenu();
  I18n.applyDomTranslations();

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
        versionEl.textContent = about.version
          ? t("about.version", { v: about.version })
          : "";
      }
      if (descEl) descEl.textContent = about.description || "";
      if (authorEl) authorEl.textContent = about.author || "";
      if (repoEl) {
        const url = about.repository || "";
        repoEl.href = url || "#";
        repoEl.textContent = url.replace(/^https?:\/\//, "") || url;
        if (!url) repoEl.removeAttribute("href");
      }
      if (licenseEl) licenseEl.textContent = about.license || "";
      if (copyrightEl) copyrightEl.textContent = about.copyright || "";
      I18n.applyDomTranslations(modal);
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

  viewport.addEventListener(
    "pointerdown",
    (ev) => {
      if (pendingCatalogPlacement && ev.button === 0) {
        ev.preventDefault();
        ev.stopPropagation();
        const startWorld = clientToWorld(ev.clientX, ev.clientY);
        const defs = catalogInsertDefaults(pendingCatalogPlacement.kind);
        const isPlace = pendingCatalogPlacement.kind === "place_type";
        placementDrag = {
          pointerId: ev.pointerId,
          startClientX: ev.clientX,
          startClientY: ev.clientY,
          startWorld,
          parentId: placeParentAtWorld(startWorld.x, startWorld.y),
          sized: false,
          box: { x: startWorld.x, y: startWorld.y, w: defs.w, h: defs.h },
          kind: pendingCatalogPlacement.kind,
        };
        updatePlacementGhost(
          startWorld.x,
          startWorld.y,
          defs.w,
          defs.h,
          pendingCatalogPlacement
        );
        // Elements: click-to-place only (no size drag).
        if (!isPlace) {
          try {
            viewport.setPointerCapture?.(ev.pointerId);
          } catch {
            /* ignore */
          }
        }
        return;
      }
      if (drag || marquee) return;
      if (ev.target !== svg && ev.target !== viewport) return;
      if (beginMarquee(ev)) return;
      if (shouldPanPointer(ev)) {
        ev.preventDefault();
        beginPanDrag(ev);
        return;
      }
      if (ev.button === 0) {
        // Empty canvas: drag pans; click (no move) clears selection.
        ev.preventDefault();
        beginPanDrag(ev, { clearOnClick: true });
      }
    },
    true
  );

  window.addEventListener("pointermove", (ev) => {
    if (pendingCatalogPlacement && !placementDrag) {
      const wpos = clientToWorld(ev.clientX, ev.clientY);
      const defs = catalogInsertDefaults(pendingCatalogPlacement.kind);
      // Hover preview: cursor tip = NW (0,0) of the ghost.
      updatePlacementGhost(
        wpos.x,
        wpos.y,
        defs.w,
        defs.h,
        pendingCatalogPlacement
      );
      return;
    }
    if (!placementDrag || placementDrag.pointerId !== ev.pointerId) return;
    if (!pendingCatalogPlacement) return;
    const end = clientToWorld(ev.clientX, ev.clientY);
    const start = placementDrag.startWorld;
    const defs = catalogInsertDefaults(pendingCatalogPlacement.kind);
    // Elements never size by drag — keep default box at the press point.
    if (pendingCatalogPlacement.kind !== "place_type") {
      placementDrag.sized = false;
      placementDrag.box = { x: start.x, y: start.y, w: defs.w, h: defs.h };
      updatePlacementGhost(start.x, start.y, defs.w, defs.h, pendingCatalogPlacement);
      return;
    }
    const dist = Math.hypot(
      ev.clientX - placementDrag.startClientX,
      ev.clientY - placementDrag.startClientY
    );
    if (dist >= DRAG_THRESHOLD) {
      placementDrag.sized = true;
      // Rubber-band: NW fixed at click (0,0); cursor tip tracks SE.
      const w = Math.max(8, end.x - start.x);
      const h = Math.max(8, end.y - start.y);
      placementDrag.box = { x: start.x, y: start.y, w, h };
      updatePlacementGhost(start.x, start.y, w, h, pendingCatalogPlacement);
    } else {
      placementDrag.sized = false;
      placementDrag.box = { x: start.x, y: start.y, w: defs.w, h: defs.h };
      updatePlacementGhost(
        start.x,
        start.y,
        defs.w,
        defs.h,
        pendingCatalogPlacement
      );
    }
  });

  window.addEventListener("pointerup", (ev) => {
    if (!placementDrag || placementDrag.pointerId !== ev.pointerId) return;
    finalizeCatalogPlacement(ev.clientX, ev.clientY).catch((err) =>
      setStatus(String(err.message || err))
    );
  });

  // Suppress middle-click autoscroll while panning the canvas.
  viewport.addEventListener("auxclick", (ev) => {
    if (ev.button === 1) ev.preventDefault();
  });

  window.addEventListener("keydown", (ev) => {
    if (isEditableFocus(ev.target)) return;
    if (ev.key === "Escape" && (pendingCatalogPlacement || placementDrag)) {
      ev.preventDefault();
      endCatalogPlacementMode();
      setStatus(t("modal.cancel"));
      return;
    }
    if (ev.code === "Space") {
      if (!spacePanHeld) {
        spacePanHeld = true;
        syncPanReadyClass();
      }
      // Keep Space from scrolling the page while using pan-ready.
      if (!ev.repeat) ev.preventDefault();
      return;
    }
    if (ev.key === "Alt") {
      if (!altPanHeld) {
        altPanHeld = true;
        syncPanReadyClass();
      }
    }
  });

  window.addEventListener("keyup", (ev) => {
    if (ev.code === "Space") {
      spacePanHeld = false;
      syncPanReadyClass();
      return;
    }
    if (ev.key === "Alt") {
      altPanHeld = false;
      syncPanReadyClass();
    }
  });

  window.addEventListener("blur", () => {
    spacePanHeld = false;
    altPanHeld = false;
    syncPanReadyClass();
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

  const INSERT_TITLE_KEYS = {
    socket: "menu.insert.socket",
    lamp: "menu.insert.lamp",
    feed: "menu.insert.feed",
    "type-pick": "menu.insert.element",
    "catalog-item": "menu.insert.element",
  };

  let paletteCatalog = null;
  let pendingCatalogInsert = null;
  let pendingCatalogPlacement = null;
  let placementDrag = null;

  function selectedParentPlaceId() {
    const nodes = graph?.nodes || [];
    const places = new Set(nodes.map((n) => n.id));
    if (selectedId) {
      const elem = (graph?.elements || []).find((e) => e.id === selectedId);
      if (elem) return elem.parent || ".";
      if (places.has(selectedId)) return selectedId;
    }
    return ".";
  }

  async function loadPaletteCatalog(force) {
    if (paletteCatalog && !force) return paletteCatalog;
    const data = await api("/api/catalog");
    paletteCatalog = data.types || {};
    return paletteCatalog;
  }

  /** Refresh localized catalog labels after a locale change (open UIs + cache). */
  function refreshOpenCatalogInsertLabels() {
    const modal = document.getElementById("insert-modal");
    const modalOpen = modal && !modal.classList.contains("hidden");
    if (!modalOpen) return;

    const typePick = document.getElementById("form-type-pick");
    if (typePick && !typePick.classList.contains("hidden")) {
      const sel = document.getElementById("insert-type-id");
      const prev = sel ? sel.value : "";
      const row = (paletteCatalog && paletteCatalog[prev]) || null;
      const typeClass = row && row.kind === "place_type" ? "place_type" : "element_type";
      const rows = paletteRows(typeClass, "");
      if (sel) {
        sel.innerHTML = "";
        for (const r of rows) {
          const opt = document.createElement("option");
          opt.value = r.id || "";
          opt.textContent = r.label || r.id || "";
          sel.appendChild(opt);
        }
        if (prev && rows.some((r) => r.id === prev)) sel.value = prev;
      }
      const typeId = sel ? sel.value : prev;
      const subSel = document.getElementById("insert-subtype-id");
      const prevSub = subSel ? subSel.value : "";
      if (typeId) renderSubtypeSelect(typeId, prevSub);
      return;
    }

    const catalogForm = document.getElementById("form-catalog-item");
    if (catalogForm && !catalogForm.classList.contains("hidden") && pendingCatalogInsert) {
      const typeId = pendingCatalogInsert.type_id || "";
      const row = (paletteCatalog && paletteCatalog[typeId]) || null;
      if (!row) return;
      const typeEl = document.getElementById("catalog-type-label");
      const subEl = document.getElementById("catalog-subtype-label");
      const descEl = document.getElementById("catalog-description");
      if (typeEl) typeEl.value = String(row.label || row.id || "").trim();
      if (descEl) descEl.value = row.description || "";
      const subtypeId = pendingCatalogInsert.subtype || "";
      let subtypeLabel = "—";
      if (subtypeId) {
        const hit = subtypeRows(typeId).find((x) => String(x.id) === String(subtypeId));
        subtypeLabel = (hit && (hit.label || hit.id)) || String(subtypeId);
      }
      if (subEl) subEl.value = subtypeLabel;
    }
  }

  function paletteRows(typeClass, q) {
    const rows = Object.values(paletteCatalog || {}).filter((row) => {
      if (!row || typeof row !== "object") return false;
      if (typeClass && row.kind !== typeClass) return false;
      const needle = String(q || "").trim().toLowerCase();
      if (!needle) return true;
      const hay = `${row.id || ""} ${row.label || ""} ${row.description || ""}`.toLowerCase();
      return hay.includes(needle);
    });
    rows.sort((a, b) =>
      String(a.label || a.id || "").localeCompare(String(b.label || b.id || ""))
    );
    return rows;
  }

  function subtypeRows(typeId) {
    const row = (paletteCatalog && paletteCatalog[typeId]) || null;
    const subs = (row && row.subtypes) || [];
    return Array.isArray(subs) ? subs : [];
  }

  function renderSubtypeSelect(typeId, selected) {
    const sel = document.getElementById("insert-subtype-id");
    if (!sel) return;
    const rows = subtypeRows(typeId);
    sel.innerHTML = "";
    if (!rows.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "—";
      sel.appendChild(opt);
      sel.disabled = true;
      return;
    }
    for (const row of rows) {
      const opt = document.createElement("option");
      opt.value = row.id || "";
      opt.textContent = row.label || row.id || "";
      sel.appendChild(opt);
    }
    sel.disabled = false;
    if (selected) sel.value = selected;
  }

  function insertMsg(text, isError) {
    const el = document.getElementById("insert-msg");
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("is-error", Boolean(isError && text));
  }

  function beginCatalogPlacement(draft) {
    pendingCatalogPlacement = draft;
    placementDrag = null;
    clearPlacementGhost();
    insertMsg("");
    closeInsertModal();
    viewport?.classList.add("placing");
    setStatus(t("insert.placeHint"));
  }

  function endCatalogPlacementMode() {
    pendingCatalogPlacement = null;
    placementDrag = null;
    clearPlacementGhost();
    hideMarquee();
    viewport?.classList.remove("placing");
  }

  function catalogInsertDefaults(kind) {
    if (kind === "place_type") {
      return { w: PLACE_INSERT_W, h: PLACE_INSERT_H };
    }
    return { w: ELEM_W, h: ELEM_H };
  }

  /**
   * Deepest place whose world box contains ``(wx, wy)``.
   * Empty canvas / miss → current view (API ``"."``), never the site root
   * above ``locationId``.
   */
  function placeParentAtWorld(wx, wy) {
    const byId = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
    let bestId = ".";
    let bestDepth = -1;
    for (const n of graph?.nodes || []) {
      const r = placeWorldRect(n, byId);
      if (wx < r.x1 || wx > r.x2 || wy < r.y1 || wy > r.y2) continue;
      const depth = Array.isArray(n.parts)
        ? n.parts.length
        : String(n.id || "").split("/").filter(Boolean).length;
      if (depth > bestDepth) {
        bestDepth = depth;
        bestId = n.id;
      }
    }
    return bestId;
  }

  function clearPlacementGhost() {
    document.getElementById("placement-ghost")?.remove();
  }

  function updatePlacementGhost(x, y, w, h, draft) {
    if (!worldEl || !draft) return;
    const isElem = draft.kind === "element_type";
    let g = document.getElementById("placement-ghost");
    if (!g) {
      g = el("g", {
        id: "placement-ghost",
        class: "placement-ghost" + (isElem ? " element-node" : " node"),
      });
      const box = el("rect", {
        class:
          (isElem ? "element-box" : "node-box container") +
          " placement-ghost-box selected",
        x: "0",
        y: "0",
        width: String(w),
        height: String(h),
        rx: isElem ? "3" : "6",
      });
      g.appendChild(box);
      const label = String(
        draft.label || draft.name || draft.type_id || ""
      ).trim();
      if (label) {
        g.appendChild(
          el(
            "text",
            {
              class: isElem ? "element-label" : "node-label",
              x: isElem ? "4" : "8",
              y: isElem ? "12" : "18",
            },
            fitLabel(label, w - (isElem ? 4 : 16))
          )
        );
      }
      worldEl.appendChild(g);
    }
    g.setAttribute("transform", `translate(${x},${y})`);
    const box = g.querySelector("rect.placement-ghost-box");
    if (box) {
      box.setAttribute("width", String(Math.max(1, w)));
      box.setAttribute("height", String(Math.max(1, h)));
    }
    const text = g.querySelector("text");
    if (text) {
      text.textContent = fitLabel(
        String(draft.label || draft.name || draft.type_id || "").trim(),
        w - (isElem ? 4 : 16)
      );
    }
  }

  function worldToParentLocal(x, y, parentId) {
    if (!parentId || parentId === ".") {
      return { x: Math.max(0, Math.round(x)), y: Math.max(0, Math.round(y)) };
    }
    const byId = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
    const parent = byId[parentId];
    if (!parent) {
      // Unknown canvas id: treat as current view content coords.
      return { x: Math.max(0, Math.round(x)), y: Math.max(0, Math.round(y)) };
    }
    const abs = absXY(parent, byId);
    return {
      x: Math.max(0, Math.round(x - abs.x - PAD)),
      y: Math.max(0, Math.round(y - abs.y - HEADER)),
    };
  }

  async function finalizeCatalogPlacement(clientX, clientY) {
    if (!pendingCatalogPlacement || !locationId) return;
    const d = pendingCatalogPlacement;
    const p = placementDrag;
    const end = clientToWorld(clientX, clientY);
    const start = p ? p.startWorld : end;
    const defs = catalogInsertDefaults(d.kind);
    let box = (p && p.box) || { x: start.x, y: start.y, w: defs.w, h: defs.h };
    if (d.kind === "element_type") {
      // Click place: NW at press point, default element size.
      box = { x: start.x, y: start.y, w: defs.w, h: defs.h };
    } else if (p && p.sized) {
      const w = Math.max(LEAF_W, end.x - start.x);
      const h = Math.max(LEAF_H, end.y - start.y);
      box = { x: start.x, y: start.y, w, h };
    }
    // Parent from the placement origin (view floor → current location / ".").
    const parentCanvasId = placeParentAtWorld(box.x + 1, box.y + 1);
    const local = worldToParentLocal(box.x, box.y, parentCanvasId);
    const body = {
      location_id: locationId,
      place_id: resolvePlaceApiId(parentCanvasId),
      depth: depthLevel,
      type_id: d.type_id,
      subtype: d.subtype || undefined,
      id: d.id || undefined,
      name: d.name,
      label: d.label || undefined,
      notes: d.notes || undefined,
      x: local.x,
      y: local.y,
      w: Math.round(box.w),
      h: Math.round(box.h),
    };
    endCatalogPlacementMode();
    setStatus(t("insert.placing"));
    try {
      const res = await api("/api/insert/catalog-item", {
        method: "POST",
        body: JSON.stringify(body),
      });
      graph = res.graph;
      depthLevel = graph.depth || depthLevel;
      maxDepth = graph.max_depth || maxDepth;
      render();
      await loadOutline();
      const newId = res.result?.id;
      if (newId) await selectNode(newId);
      setStatus(t("status.catalogAddedUnsaved"));
      scheduleStatusRefresh();
    } catch (err) {
      const msg = String(err.message || err);
      if (/place does not exist|invalid place/i.test(msg)) {
        setStatus(t("insert.placeNotFound"));
      } else {
        setStatus(msg);
      }
    }
  }

  function resetCatalogInsertForm() {
    const form = document.getElementById("form-catalog-item");
    if (form) form.reset();
    const desc = document.getElementById("catalog-description");
    if (desc) desc.value = "";
    const token = document.getElementById("catalog-id-token");
    if (token) token.value = "";
    const nameEl = document.getElementById("catalog-name");
    if (nameEl) nameEl.value = "";
    const labelEl = document.getElementById("catalog-label");
    if (labelEl) labelEl.value = "";
  }

  /** Technical id from a localized label (keeps letters/digits, spaces → _). */
  function suggestIdFromLabel(label) {
    const raw = String(label || "").trim();
    if (!raw) return "NewItem";
    let out = "";
    for (const ch of raw) {
      if (/[\p{L}\p{N}_-]/u.test(ch)) out += ch;
      else out += "_";
    }
    out = out.replace(/_+/g, "_").replace(/^_|_$/g, "");
    return out || "NewItem";
  }

  function siblingIdsUnder(parentId, kind) {
    const used = new Set();
    const pid = parentId || ".";
    if (kind === "place_type") {
      for (const n of graph?.nodes || []) {
        if ((n.parent || ".") === pid || (n.parent == null && pid === ".")) {
          const leaf = String(n.id || "").split("/").pop();
          if (leaf) used.add(leaf);
        }
      }
    } else {
      for (const e of graph?.elements || []) {
        const ep = e.parent == null || e.parent === "" ? "." : e.parent;
        if (ep === pid) {
          const leaf = e.leaf_id || String(e.id || "").split("/").pop();
          if (leaf) used.add(leaf);
        }
      }
    }
    return used;
  }

  function siblingDisplayFieldsUnder(parentId, kind) {
    const names = new Set();
    const labels = new Set();
    const pid = parentId || ".";
    const consider = (node) => {
      const rawN = node?.name;
      if (rawN != null && String(rawN).trim()) names.add(String(rawN).trim());
      const rawL = node?.label;
      if (rawL != null && String(rawL).trim()) labels.add(String(rawL).trim());
    };
    if (kind === "place_type") {
      for (const n of graph?.nodes || []) {
        if ((n.parent || ".") === pid || (n.parent == null && pid === ".")) {
          consider(n);
        }
      }
    } else {
      for (const e of graph?.elements || []) {
        const ep = e.parent == null || e.parent === "" ? "." : e.parent;
        if (ep === pid) consider(e);
      }
    }
    return { names, labels };
  }

  /** Like paste ``next_available_id``: Foo → Foo_1 → Foo_2. */
  function nextSuggestedIdToken(parentId, base, kind) {
    const stem = suggestIdFromLabel(base);
    const used = siblingIdsUnder(parentId, kind);
    if (!used.has(stem)) return stem;
    let i = 1;
    while (used.has(`${stem}_${i}`)) i += 1;
    return `${stem}_${i}`;
  }

  /** Like paste ``next_available_display_name``: Foo → Foo 1 → Foo 2. */
  function nextSuggestedDisplayName(taken, preferred) {
    const name = String(preferred || "").trim();
    if (!name) return name;
    if (!taken.has(name)) return name;
    const m = /^(.*?)(?:\s+)(\d+)$/.exec(name);
    if (m && m[1].trim()) {
      const stem = m[1].trim();
      let n = Number(m[2]) + 1;
      while (taken.has(`${stem} ${n}`)) n += 1;
      return `${stem} ${n}`;
    }
    let n = 1;
    while (taken.has(`${name} ${n}`)) n += 1;
    return `${name} ${n}`;
  }

  function prefillCatalogInsertFromRow(row, subtypeId) {
    if (!row) return;
    const typeEl = document.getElementById("catalog-type-label");
    const subEl = document.getElementById("catalog-subtype-label");
    const descEl = document.getElementById("catalog-description");
    const tokenEl = document.getElementById("catalog-id-token");
    const nameEl = document.getElementById("catalog-name");
    const labelEl = document.getElementById("catalog-label");
    const localized = String(row.label || row.id || "").trim() || "NewItem";
    if (typeEl) typeEl.value = localized;
    if (descEl) descEl.value = row.description || "";
    let subtypeLabel = "—";
    if (subtypeId) {
      const hit = subtypeRows(row.id || "").find((x) => String(x.id) === String(subtypeId));
      subtypeLabel = (hit && (hit.label || hit.id)) || String(subtypeId);
    }
    if (subEl) subEl.value = subtypeLabel;
    const parentId = selectedParentPlaceId();
    const kind = row.kind || "";
    const idBase = suggestIdFromLabel(localized);
    const idToken = nextSuggestedIdToken(parentId, localized, kind);
    const { names, labels } = siblingDisplayFieldsUnder(parentId, kind);
    const nameTaken = new Set(names);
    const labelTaken = new Set(labels);
    if (idToken !== idBase) {
      nameTaken.add(localized);
      labelTaken.add(localized);
    }
    const displayName = nextSuggestedDisplayName(nameTaken, localized);
    const displayLabel = nextSuggestedDisplayName(labelTaken, localized);
    if (tokenEl) tokenEl.value = idToken;
    if (nameEl) nameEl.value = displayName;
    if (labelEl) labelEl.value = displayLabel;
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
    if (!modal || !INSERT_TITLE_KEYS[kind]) return;
    if (titleEl) titleEl.textContent = t(INSERT_TITLE_KEYS[kind]);
    for (const id of ["socket", "lamp", "feed", "type-pick", "catalog-item"]) {
      const form = document.getElementById(`form-${id}`);
      if (form) form.classList.toggle("hidden", id !== kind);
    }
    insertMsg("");
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    document.addEventListener("keydown", onInsertModalKey);
    const form = document.getElementById(`form-${kind}`);
    const first = form && form.querySelector("input:not([type=hidden]),select,textarea");
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

  async function submitPaletteInsert(form) {
    if (!locationId) return;
    const data = Object.fromEntries(new FormData(form).entries());
    const typeId = String((pendingCatalogInsert && pendingCatalogInsert.type_id) || "").trim();
    if (!typeId) {
      insertMsg(t("insert.selectType"), true);
      return;
    }
    const token = String(data.id_token || "").trim();
    if (!token) {
      insertMsg(t("insert.idRequired"), true);
      return;
    }
    beginCatalogPlacement({
      kind: (pendingCatalogInsert && pendingCatalogInsert.source_kind) || "element_type",
      type_id: typeId,
      subtype: (pendingCatalogInsert && pendingCatalogInsert.subtype) || "",
      id: token,
      name: String(data.name || "").trim() || token,
      label: String(data.label || "").trim() || String(data.name || "").trim() || token,
      notes: data.notes || "",
    });
    form.reset();
    resetCatalogInsertForm();
  }

  function renderPaletteSideList() {
    const qEl = document.getElementById("palette-search-side");
    const q = qEl ? qEl.value : "";
    const containers = paletteRows("place_type", q);
    const elements = paletteRows("element_type", q);
    const render = (hostId, rows) => {
      const host = document.getElementById(hostId);
      if (!host) return;
      host.innerHTML = "";
      for (const row of rows) {
        const btn = document.createElement("button");
        btn.type = "button";
        const isElem = row.kind === "element_type";
        btn.className = "palette-item" + (isElem ? " element" : "");
        const fallback = isElem ? "box" : "folder-open";
        const icon = iconElement(
          row.icon || fallback,
          "palette-item-icon"
        );
        if (icon) btn.appendChild(icon);
        const label = document.createElement("span");
        label.className = "palette-item-label";
        label.textContent = row.label || row.id || "";
        btn.appendChild(label);
        const idEl = document.createElement("span");
        idEl.className = "palette-item-id";
        idEl.textContent = row.id || "";
        btn.appendChild(idEl);
        btn.title = [row.label || row.id, row.id].filter(Boolean).join(" · ");
        btn.addEventListener("click", () => {
          pendingCatalogInsert = {
            type_id: row.id || "",
            subtype: "",
            source_kind: row.kind || "",
          };
          resetCatalogInsertForm();
          prefillCatalogInsertFromRow(row, "");
          openInsertModal("catalog-item");
        });
        host.appendChild(btn);
      }
    };
    render("palette-list-containers", containers);
    render("palette-list-elements", elements);
  }

  function initLeftNavAccordion() {
    const outlineSec = document.getElementById("outline-section");
    const paletteSec = document.getElementById("palette-section");
    const resizer = document.getElementById("resizer-nav-split");
    const btnOutline = document.getElementById("btn-toggle-outline-section");
    const btnPalette = document.getElementById("btn-toggle-palette-section");
    if (!outlineSec || !paletteSec || !resizer || !btnOutline || !btnPalette) {
      return;
    }

    const SPLIT_KEY = "housewire-nav-split";
    const OUTLINE_OPEN_KEY = "housewire-nav-outline-open";
    const PALETTE_OPEN_KEY = "housewire-nav-palette-open";
    const SPLIT_MIN = 0.18;
    const SPLIT_MAX = 0.82;

    function loadSplitFrac() {
      try {
        const v = Number(sessionStorage.getItem(SPLIT_KEY));
        if (Number.isFinite(v) && v >= SPLIT_MIN && v <= SPLIT_MAX) return v;
      } catch {
        /* ignore */
      }
      return 0.55;
    }

    function saveSplitFrac(frac) {
      try {
        sessionStorage.setItem(SPLIT_KEY, String(frac));
      } catch {
        /* ignore */
      }
    }

    function sectionOpen(sec) {
      return !sec.classList.contains("collapsed");
    }

    function setSectionChevron(btn, open) {
      const host = btn.querySelector(".nav-section-chevron");
      if (!host) return;
      host.innerHTML = open ? iconHtml("chevron-down") : iconHtml("chevron-right");
    }

    function applyNavSplit() {
      const outlineOpen = sectionOpen(outlineSec);
      const paletteOpen = sectionOpen(paletteSec);
      resizer.classList.toggle("hidden", !(outlineOpen && paletteOpen));
      btnOutline.setAttribute("aria-expanded", outlineOpen ? "true" : "false");
      btnPalette.setAttribute("aria-expanded", paletteOpen ? "true" : "false");
      setSectionChevron(btnOutline, outlineOpen);
      setSectionChevron(btnPalette, paletteOpen);
      if (outlineOpen && paletteOpen) {
        const frac = loadSplitFrac();
        outlineSec.style.flex = `${frac} 1 0`;
        paletteSec.style.flex = `${1 - frac} 1 0`;
      } else if (outlineOpen) {
        outlineSec.style.flex = "1 1 auto";
        paletteSec.style.flex = "0 0 auto";
      } else if (paletteOpen) {
        outlineSec.style.flex = "0 0 auto";
        paletteSec.style.flex = "1 1 auto";
      } else {
        outlineSec.style.flex = "0 0 auto";
        paletteSec.style.flex = "0 0 auto";
      }
    }

    function setSectionCollapsed(which, collapsed) {
      const sec = which === "outline" ? outlineSec : paletteSec;
      sec.classList.toggle("collapsed", collapsed);
      try {
        sessionStorage.setItem(
          which === "outline" ? OUTLINE_OPEN_KEY : PALETTE_OPEN_KEY,
          collapsed ? "0" : "1"
        );
      } catch {
        /* ignore */
      }
      applyNavSplit();
      if (which === "palette" && !collapsed) {
        loadPaletteCatalog()
          .then(() => renderPaletteSideList())
          .catch((err) => setStatus(String(err.message || err)));
      }
    }

    btnOutline.addEventListener("click", () => {
      setSectionCollapsed("outline", sectionOpen(outlineSec));
    });
    btnPalette.addEventListener("click", () => {
      setSectionCollapsed("palette", sectionOpen(paletteSec));
    });

    resizer.addEventListener("pointerdown", (ev) => {
      if (!sectionOpen(outlineSec) || !sectionOpen(paletteSec)) return;
      ev.preventDefault();
      const split = document.getElementById("nav-split");
      if (!split) return;
      const bounds = split.getBoundingClientRect();
      const move = (mev) => {
        const y = mev.clientY - bounds.top;
        const frac = Math.min(
          SPLIT_MAX,
          Math.max(SPLIT_MIN, y / Math.max(bounds.height, 1))
        );
        saveSplitFrac(frac);
        applyNavSplit();
      };
      const up = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        document.body.style.cursor = "";
      };
      document.body.style.cursor = "ns-resize";
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up, { once: true });
    });

    try {
      if (sessionStorage.getItem(OUTLINE_OPEN_KEY) === "0") {
        outlineSec.classList.add("collapsed");
      }
      if (sessionStorage.getItem(PALETTE_OPEN_KEY) === "0") {
        paletteSec.classList.add("collapsed");
      }
    } catch {
      /* ignore */
    }
    applyNavSplit();
    if (sectionOpen(paletteSec)) {
      loadPaletteCatalog()
        .then(() => renderPaletteSideList())
        .catch((err) => setStatus(String(err.message || err)));
    }
  }

  async function openTypePickerFromInsert(kind) {
    await loadPaletteCatalog();
    const sel = document.getElementById("insert-type-id");
    if (!sel) return;
    const typeClass = kind === "container" ? "place_type" : "element_type";
    const rows = paletteRows(typeClass, "");
    sel.innerHTML = "";
    for (const row of rows) {
      const opt = document.createElement("option");
      opt.value = row.id || "";
      opt.textContent = row.label || row.id || "";
      sel.appendChild(opt);
    }
    const first = rows[0] && rows[0].id;
    if (first) {
      sel.value = first;
      renderSubtypeSelect(first, "");
    }
    openInsertModal("type-pick");
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
  document.getElementById("insert-type-id")?.addEventListener("change", (ev) => {
    renderSubtypeSelect(ev.target.value, "");
  });
  document.getElementById("form-type-pick")?.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const data = Object.fromEntries(new FormData(ev.target).entries());
    const typeId = String(data.type_id || "").trim();
    if (!typeId) {
      insertMsg(t("insert.selectType"), true);
      return;
    }
    const row = (paletteCatalog && paletteCatalog[typeId]) || {};
    pendingCatalogInsert = {
      type_id: typeId,
      subtype: String(data.subtype || "").trim(),
      source_kind: row.kind || "",
    };
    resetCatalogInsertForm();
    prefillCatalogInsertFromRow(row, pendingCatalogInsert.subtype);
    openInsertModal("catalog-item");
  });
  document.getElementById("palette-search-side")?.addEventListener("input", () => {
    renderPaletteSideList();
  });
  document.getElementById("form-catalog-item")?.addEventListener("submit", (ev) => {
    ev.preventDefault();
    submitPaletteInsert(ev.target);
  });

  ensureIconSprite()
    .then(() => {
      initLeftNavAccordion();
      return loadConductorColors();
    })
    .then(() => api("/api/workspace"))
    .then((st) => applyWorkspaceStatus(st))
    .then(() => loadLocations())
    .catch((err) => setStatus(String(err.message || err)));
})();
