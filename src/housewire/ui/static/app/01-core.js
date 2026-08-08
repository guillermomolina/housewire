  /* === 01-core.js: State, API, documents, selection, layout helpers ===
   * Fragment of the UI IIFE (bundled into ../app.js).
   * Edit this file, then run: python scripts/bundle_ui_app.py
   */
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
  /** @type {string|null} Selected conduit/cable/conductor id (cables: map). */
  let selectedLinkId = null;
  /** @type {"conduit"|"cable"|"conductor"|null} */
  let selectedLinkType = null;
  /**
   * Active wiring gesture.
   * @type {null|{
   *   kind:"conduit"|"conductor"|"cable", from:string|null, fromX?:number, fromY?:number,
   *   lastX?:number, lastY?:number,
   *   activeContainer?:string|null, enteredOpening?:string|null,
   *   conduitPath?:any[], pathSteps?:any[], history?:any[],
   *   completedSegments?:any[], readyToCommit?:boolean,
   *   cableRoute?:string|null, selectedConductors?:string[], cableHistory?:string[]
   * }}
   */
  let wiringMode = null;
  /** Last snap target under the pointer (sticky for the following click). */
  let wiringHoverSnap = null;
  let depthLevel = DEPTH_DEFAULT;
  let maxDepth = 1;
  let scale = 1;
  let panX = 40;
  let panY = 40;
  let dirtyLocal = false;
  /** Catalog type rows for the left palette (null until /api/catalog). */
  let paletteCatalog = null;
  /** Client mirror of whether the workspace has an open document. */
  let hasDocument = false;
  /** @type {string | null} */
  let activeDocId = null;
  /** Active document YAML filename (e.g. NuevoSitio.yaml) for root Id display. */
  let activeYamlName = null;
  /** Absolute yaml_path from workspace status (real path or server temp). */
  let activeYamlPath = null;
  /**
   * True when the active document was opened from browser content / File → New
   * (temp site on the server). False when opened from a real filesystem path
   * (``housewire serve $SITE`` or Electron Open).
   */
  let activeDocBrowserOrigin = false;
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
  /** Depth before toggling Electrical on (restored when toggling off). */
  let depthBeforeElectrical = null;
  let outlineNodes = [];
  let canvasLocations = [];
  let collapsedOutline = new Set();
  let outlineCollapseReady = false;
  /** Re-render once after growing places around inbox cables. */
  let renderExpandPass = 0;
  /** @type {Record<string, number[][][]>|null} */
  let inboxCablePtsByParent = null;
  /**
   * Progressive paint generation: bump to cancel in-flight rAF passes.
   * Full ``render()`` and progressive edge refresh share this so a new paint
   * aborts an unfinished one.
   */
  let renderGen = 0;
  /** Scheduled progressive-pass rAF handle (0 when idle). */
  let renderPassRaf = 0;
  /** Separate generation for post-drag edge refinement. */
  let edgeRefreshGen = 0;
  let edgeRefreshRaf = 0;
  /** ~one frame budget for conduit re-route slices after drag. */
  const EDGE_REFRESH_BUDGET_MS = 6;
  /**
   * In-flight chunked tube/cable refresh after drag/resize.
   * @type {{
   *   kind: "tubes"|"cables",
   *   gen: number,
   *   byId?: Record<string, any>,
   *   elemById?: Record<string, any>,
   *   occupied: ReturnType<typeof createOccupiedIndex>,
   *   layout?: ReturnType<typeof buildCableLayout>|null,
   *   cablesG?: SVGGElement,
   *   edges?: any[],
   *   index: number,
   *   onDone?: () => void,
   * }|null}
   */
  let edgeRefreshJob = null;
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
  /**
   * Minimum link pick thickness in screen pixels (tubes, strands, jackets).
   * World stroke grows when zoomed out so Route-scale views stay clickable.
   */
  const LINK_HIT_PX = 16;
  /** Extra world padding beyond the painted stroke when zoomed in. */
  const LINK_HIT_PAD = 4;
  /** Must stay in sync with housewire.ui.route_quality highway constants. */
  const STRAND_WIDTH = 2.5;
  // Keep cable strands and adjacent jackets visually distinct and clickable.
  const LANE_GAP = 4;
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
        return isOutlineNodeVisible(c);
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

  /** Lucide icon + primary label on one line (place or element box). */
  function appendIconWithLabel(g, { icon, labelText, x, y, maxW, textClass }) {
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
        fitLabel(labelText, Math.max(8, maxW - (iconSize + gap)))
      )
    );
  }

  const ns = "http://www.w3.org/2000/svg";

  /** Inject Lucide sprite once so <use href="#icon-…"> resolves in-document. */
  function ensureIconSprite() {
    if (document.getElementById("hw-icon-sprite")) return Promise.resolve();
    const scriptSrc =
      document.querySelector('script[src*="app.js"]')?.getAttribute("src") ||
      "";
    const verMatch = scriptSrc.match(/[?&]v=([^&]+)/);
    const ver = verMatch ? `?v=${encodeURIComponent(verMatch[1])}` : "";
    return fetch(`/static/icons.svg${ver}`)
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

  let pendingProblemStatus = null;

  function setStatus(text) {
    if (text && text === pendingProblemStatus) {
      pendingProblemStatus = null;
      return;
    }
    statusEl.textContent = text || "";
  }

  /** Show user-facing information at the appropriate prominence. */
  async function notifyUser(level, message) {
    if (level === "info") {
      setStatus(message);
      return;
    }
    pendingProblemStatus = message;
    await appDialog({
      kind: level,
      title: t(level === "warning" ? "modal.warning" : "modal.error"),
      message,
      buttons: [{ id: "ok", label: t("modal.ok"), primary: true }],
    });
  }

  /**
   * In-app modal. Returns the chosen button id, or null if dismissed.
   * When ``opts.input`` is set, Enter confirms the primary button and the
   * caller should read ``opts.input``'s field via ``promptText``.
   * @param {{
   *   kind?: "warning"|"error",
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
      { id: "cancel", label: t("modal.cancel") },
      { id: "ok", label: t("modal.ok"), primary: true },
    ];
    return new Promise((resolve) => {
      titleEl.textContent = opts.title || "HouseWire";
      msgEl.textContent = opts.message || "";
      modal.dataset.kind = opts.kind || "";
      actions.innerHTML = "";
      const wantsInput = Boolean(opts.input);
      if (inputWrap && inputEl) {
        if (wantsInput) {
          inputWrap.classList.remove("hidden");
          if (inputLabel) {
            inputLabel.textContent = opts.input.label || t("modal.path");
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
        delete modal.dataset.kind;
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
        label: opts.label || t("modal.path"),
        value: opts.value || "",
        placeholder: opts.placeholder || "",
      },
      buttons: [
        { id: "cancel", label: t("modal.cancel") },
        { id: "ok", label: opts.okLabel || t("modal.ok"), primary: true },
      ],
    });
    if (choice !== "ok" || !inputEl) return null;
    const value = String(inputEl.value || "").trim();
    return value || null;
  }

  /** @returns {Promise<"save"|"discard"|null>} */
  async function confirmUnsavedClose(docTitle) {
    const name = docTitle || t("modal.unsavedThisFile");
    const choice = await appDialog({
      title: t("modal.unsavedTitle"),
      message: t("modal.unsavedMessage", { name }),
      buttons: [
        { id: "cancel", label: t("modal.cancel") },
        { id: "discard", label: t("modal.discard"), danger: true },
        { id: "save", label: t("menu.file.save"), primary: true },
      ],
    });
    if (choice === "save" || choice === "discard") return choice;
    return null;
  }

  async function confirmReloadDiscard(docTitle) {
    const name = docTitle || t("modal.unsavedThisFile");
    const choice = await appDialog({
      title: t("modal.reloadTitle"),
      message: t("modal.reloadMessage", { name }),
      buttons: [
        { id: "cancel", label: t("modal.cancel") },
        { id: "reload", label: t("modal.reload"), danger: true, primary: true },
      ],
    });
    return choice === "reload";
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
    const menuReload = document.getElementById("menu-reload");
    if (menuReload) menuReload.disabled = !hasDocument;
    updateDeleteButtons();
    updateDocStatusStrip();
  }

  function updateDocStatusStrip() {
    const el = document.getElementById("status-doc");
    if (!el) return;
    if (!hasDocument || !activeYamlName) {
      el.textContent = "";
      el.title = "";
      updateWindowTitle();
      return;
    }
    const state = dirtyLocal ? t("status.unsaved") : t("status.savedOk");
    el.textContent = `${activeYamlName} · ${state}`;
    const loc =
      locationId && locationId !== "." && locationId !== ""
        ? String(locationId)
        : "";
    el.title = loc
      ? `${activeYamlName} · ${state} · ${loc}`
      : `${activeYamlName} · ${state}`;
    updateWindowTitle();
  }

  /** Browser / OS window title: active file (+ dirty *) — HouseWire. */
  function updateWindowTitle() {
    if (!hasDocument || !activeYamlName) {
      document.title = "HouseWire";
      return;
    }
    const mark = dirtyLocal ? "*" : "";
    document.title = `${mark}${activeYamlName} — HouseWire`;
  }

  function applyWorkspaceStatus(st) {
    const docs = (st && st.documents) || [];
    hasDocument = docs.length > 0 && Boolean(st.document);
    activeDocId = (st && st.active) || (st.document && st.document.id) || null;
    activeYamlName =
      (st && st.document && st.document.yaml) ||
      (st &&
        st.documents &&
        st.documents.find((d) => d.id === activeDocId)?.yaml) ||
      null;
    activeYamlPath =
      (st && st.document && st.document.yaml_path) || null;
    activeDocBrowserOrigin = Boolean(
      st && st.document && st.document.browser_origin
    );
    if (!hasDocument) {
      dirtyLocal = false;
      canUndo = false;
      canRedo = false;
      canReset = false;
      activeDocId = null;
      activeYamlName = null;
      activeYamlPath = null;
      activeDocBrowserOrigin = false;
      updateHistoryButtons();
    }
    const serverDirty = ((st && st.dirty) || []).length > 0;
    dirtyLocal = hasDocument ? serverDirty : false;
    applyEditFlags(st);
    updateFileMenuState({ dirty: dirtyLocal });
    renderDocTabs(st);
    updateDocStatusStrip();
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
    const hasSel = hasDocument && (selectedIds.size >= 1 || Boolean(selectedLinkId));
    for (const id of ["btn-delete", "menu-delete", "btn-cut", "menu-cut", "btn-copy", "menu-copy"]) {
      const el = document.getElementById(id);
      // Cut/copy only for places/elements; delete also for links.
      if (id === "btn-delete" || id === "menu-delete") {
        if (el) el.disabled = !hasSel;
        continue;
      }
      if (el) el.disabled = !(hasDocument && selectedIds.size >= 1);
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
   * - Paste with a different place selected + place clipboard → into that place
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
      const uniq = [...new Set(placeSites)];
      const sources = new Set(clipboardSourceSiteIds(editClipboard));
      // Nest into the selected place when it is not the clipboard source
      // (Cut→select destination, or Copy→select another box).
      if (uniq.length === 1 && !sources.has(uniq[0])) {
        return uniq[0];
      }
      // Sources still selected (typical Copy→Paste): paste as siblings.
      if (uniq.length && uniq.every((id) => sources.has(id))) {
        const parents = [...new Set(uniq.map(parentSiteIdOf))];
        if (parents.length !== 1) return null;
        return parents[0];
      }
      if (uniq.length !== 1) return null;
      return uniq[0];
    }

    if (elemParents.length) {
      // Copy→paste with source element still selected → sibling under same parent.
      const uniq = [...new Set(elemParents)];
      if (uniq.length !== 1) return null;
      return uniq[0];
    }
    return locationId || ".";
  }

  function clipboardSourceSiteIds(payload) {
    const items = (payload && payload.items) || [];
    const ids = [];
    for (const it of items) {
      const path = it.path;
      if (!Array.isArray(path) || !path.length) continue;
      ids.push(path.join("/"));
    }
    return ids;
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
    if (!hasDocument || !locationId) return;
    if (selectedLinkId) {
      const choice = await appDialog({
        title: t("props.link.deleteTitle"),
        message: t("props.link.deleteMessage", { id: selectedLinkId }),
        buttons: [
          { id: "cancel", label: t("modal.cancel") },
          { id: "delete", label: t("menu.edit.delete"), danger: true, primary: true },
        ],
      });
      if (choice !== "delete") return;
      const res = await api("/api/edit/delete", {
        method: "POST",
        body: JSON.stringify({
          location_id: locationId,
          ids: [selectedLinkId],
          depth: depthLevel,
        }),
      });
      clearLinkSelection();
      clearSelectionSilent();
      if (res.graph) {
        graph = res.graph;
        if (res.location) locationId = res.location;
        render();
      }
      applyEditFlags(res);
      await syncInspectorFromSelection();
      setStatus(t("status.linkDeleted"));
      scheduleStatusRefresh();
      return;
    }
    if (selectedIds.size < 1) return;
    const siteIds = [...selectedIds]
      .map((id) => canvasToSiteId(id))
      .filter((id) => id && id !== ".");
    if (!siteIds.length) {
      setStatus(t("status.cannotDeleteRoot"));
      return;
    }
    const n = siteIds.length;
    const choice = await appDialog({
      title: t("modal.deleteTitle"),
      message:
        n === 1
          ? t("modal.deleteOne", { id: siteIds[0] })
          : t("modal.deleteMany", { n }),
      buttons: [
        { id: "cancel", label: t("modal.cancel") },
        { id: "delete", label: t("menu.edit.delete"), danger: true, primary: true },
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
    setStatus(bits.join(" · "));
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
      const message = apiErrorMessage(body, res.statusText);
      await notifyUser(res.status >= 500 ? "error" : "warning", message);
      throw new Error(message);
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
        // Sprite AABB already includes iso depth.
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
      borderRects.push(frontRectAbs(n, placeById));
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
      kind: wiringMode?.kind === "cable" ? "cable" : "selection",
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
    clearLinkSelection();
    updateDeleteButtons();
    syncElectricalUi();
    setSelectedVisual();
    highlightOutlineSelection();
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
    document.querySelectorAll("[data-link-id]").forEach((el) => {
      const on = selectedLinkId && el.getAttribute("data-link-id") === selectedLinkId;
      el.classList.toggle("selected", Boolean(on));
    });
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
    clearLinkSelection();
    selectedIds = normalized;
    if (primaryId != null && normalized.has(primaryId)) {
      selectedId = primaryId;
    } else {
      selectedId = [...normalized].slice(-1)[0] ?? null;
    }
    setSelectedVisual();
    updateDeleteButtons();
    syncElectricalUi();
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

  
  function clearLinkSelection() {
    selectedLinkId = null;
    selectedLinkType = null;
  }

  function clearWiringSnapHighlight() {
    if (!svg) return;
    svg.querySelectorAll(".wiring-snap").forEach((el) => {
      el.classList.remove("wiring-snap");
    });
  }

  function clearWiringPreview() {
    clearWiringSnapHighlight();
    wiringHoverSnap = null;
    document.getElementById("wiring-preview")?.remove();
    document.getElementById("wiring-draft")?.remove();
  }

  function setWiringMode(mode) {
    if (!mode) clearWiringPreview();
    else if (!mode.from) clearWiringPreview();
    wiringHoverSnap = null;
    wiringMode = mode;
    syncWiringCursorUi();
  }

  function syncWiringCursorUi() {
    if (!viewport) return;
    const mode = wiringMode;
    viewport.classList.toggle("wiring-conduit", mode?.kind === "conduit");
    viewport.classList.toggle("wiring-conductor", mode?.kind === "conductor");
    viewport.classList.toggle("wiring-cable", mode?.kind === "cable");
    viewport.classList.toggle(
      "wiring-cable-has-route",
      mode?.kind === "cable" && mode.cableRoute !== null
    );
    viewport.classList.toggle(
      "wiring-conductor-from",
      mode?.kind === "conductor" && !mode?.from
    );
    viewport.classList.toggle(
      "wiring-conductor-to",
      mode?.kind === "conductor" && Boolean(mode?.from)
    );
    viewport.classList.toggle(
      "wiring-conduit-from",
      mode?.kind === "conduit" && !mode?.from
    );
    viewport.classList.toggle(
      "wiring-conduit-to",
      mode?.kind === "conduit" && Boolean(mode?.from)
    );
    if (mode) {
      viewport.classList.remove(
        "resize-ns",
        "resize-ew",
        "resize-nesw",
        "resize-nwse"
      );
      viewport.style.cursor = "";
      if (svg) svg.style.cursor = "";
    }
  }

  function cancelWiringMode() {
    if (!wiringMode) return;
    setWiringMode(null);
    syncCableCandidateVisuals();
    setStatus(t("status.wiringCancelled"));
  }

  /** Ordered conduit ids travelled by a visible conductor or Cable. */
  function cableRouteForMember(memberId) {
    const routes = new Set();
    for (const edge of graph?.cable_edges || []) {
      if (edge.id !== memberId) continue;
      const hops = Array.isArray(edge.conduit_hops)
        ? edge.conduit_hops.map((hop) => String(hop.conduit || ""))
        : edge.conduit
          ? [String(edge.conduit)]
          : [];
      routes.add(JSON.stringify(hops));
    }
    // A cable spanning different routes cannot be added as one member.
    return routes.size === 1 ? [...routes][0] : null;
  }

  function cableSelectionSeed() {
    if (
      selectedIds.size === 0 &&
      (selectedLinkType === "Conductor" || selectedLinkType === "Cable") &&
      selectedLinkId &&
      cableRouteForMember(selectedLinkId) !== null
    ) {
      return selectedLinkId;
    }
    if (selectedIds.size || selectedLinkId) clearSelectionState();
    return null;
  }

  function syncCableCandidateVisuals() {
    const route = wiringMode?.kind === "cable" ? wiringMode.cableRoute : null;
    const selected = new Set(wiringMode?.selectedConductors || []);
    document
      .querySelectorAll("[data-conductor-id], [data-link-type=\"Cable\"]")
      .forEach((path) => {
      const id =
        path.getAttribute("data-cable-id") ||
        path.getAttribute("data-conductor-id") ||
        path.getAttribute("data-link-id");
      const memberRoute = cableRouteForMember(id);
      const eligible = memberRoute !== null;
      const candidate = eligible && route !== null && memberRoute === route;
      path.classList.toggle("cable-eligible", eligible);
      path.classList.toggle("cable-candidate", candidate);
      path.classList.toggle("cable-choice", selected.has(id));
      });
  }

  function pickCableMember(memberId) {
    return pickCableMembers([memberId], false);
  }

  function pickCableMembers(memberIds, additive) {
    if (!wiringMode || wiringMode.kind !== "cable") return false;
    const prior = wiringMode.selectedConductors || [];
    const next = additive ? [...prior] : [];
    for (const id of memberIds) {
      const route = cableRouteForMember(id);
      if (route === null) continue;
      if (additive && next.includes(id)) {
        next.splice(next.indexOf(id), 1);
      } else if (!next.includes(id)) {
        next.push(id);
      }
    }
    const first = next[0];
    const route = first ? cableRouteForMember(first) : null;
    const compatible = route === null
      ? []
      : next.filter((id) => cableRouteForMember(id) === route);
    setWiringMode({
      ...wiringMode,
      cableRoute: route,
      selectedConductors: compatible,
      cableHistory: [],
    });
    syncCableCandidateVisuals();
    if (compatible.length) setStatus(t("status.wiringCableCandidates"));
    return true;
  }

  /** Cable / conductor ids whose rendered paths touch a screen-space box. */
  function cableMembersInClientRect(rect) {
    const ids = new Set();
    document
      .querySelectorAll(
        ".cable-strand-hit.cable-eligible, .cable-jacket-hit.cable-eligible"
      )
      .forEach((path) => {
        const box = path.getBoundingClientRect();
        if (
          box.left <= rect.right &&
          box.right >= rect.left &&
          box.top <= rect.bottom &&
          box.bottom >= rect.top
        ) {
          const id =
            path.getAttribute("data-cable-id") ||
            path.getAttribute("data-conductor-id") ||
            path.getAttribute("data-link-id");
          if (id) ids.add(id);
        }
      });
    return [...ids];
  }

  function wiringSnapRadius() {
    // Generous hit area so first-click snap works off the tiny mark circle.
    return Math.max(28, 36 / Math.max(scale, 0.01));
  }

  /**
   * World position of an SVG circle (cx/cy in its parent user space).
   * Prefer screen CTM so pan/zoom and nested transforms stay consistent.
   */
  function circleCenterWorld(circle) {
    if (!circle || !svg) return null;
    const cx = Number(circle.getAttribute("cx") || 0);
    const cy = Number(circle.getAttribute("cy") || 0);
    try {
      const ctm = circle.getScreenCTM();
      if (ctm && typeof svg.createSVGPoint === "function") {
        const pt = svg.createSVGPoint();
        pt.x = cx;
        pt.y = cy;
        const screen = pt.matrixTransform(ctm);
        return clientToWorld(screen.x, screen.y);
      }
    } catch {
      /* fall through */
    }
    return null;
  }

  /**
   * Visible opening marks / terminals for wiring snap.
   * @param {"conduit"|"conductor"} kind
   * @returns {{ref:string,x:number,y:number,el:Element,pick:()=>void}[]}
   */
  function wiringSnapCandidates(kind) {
    /** @type {{ref:string,x:number,y:number,el:Element,pick:()=>void}[]} */
    const out = [];
    if (!graph || !svg) return out;
    if (kind === "conduit") {
      const byId = Object.fromEntries(
        (graph.nodes || []).map((n) => [n.id, n])
      );
      for (const node of graph.nodes || []) {
        const g = nodesById[node.id];
        if (!g) continue;
        const a = absXY(node, byId);
        for (const circle of g.querySelectorAll(
          "circle.opening-mark[data-opening]"
        )) {
          const oid = circle.getAttribute("data-opening");
          if (!oid) continue;
          const cx = Number(circle.getAttribute("cx") || 0);
          const cy = Number(circle.getAttribute("cy") || 0);
          const world = circleCenterWorld(circle) || {
            x: a.x + cx,
            y: a.y + cy,
          };
          const nodeId = node.id;
          const openingId = oid;
          out.push({
            ref: openingRefForNode(nodeId, openingId),
            x: world.x,
            y: world.y,
            el: circle,
            pick: () => applyWiringOpeningPick(nodeId, openingId, cx, cy),
          });
        }
      }
      return out;
    }
    const placeById = Object.fromEntries(
      (graph.nodes || []).map((n) => [n.id, n])
    );
    if (
      kind === "conductor" &&
      Object.prototype.hasOwnProperty.call(wiringMode || {}, "activeContainer") &&
      wiringMode.activeContainer
    ) {
      const active = wiringMode.activeContainer;
      const entered = wiringMode.enteredOpening;
      for (const node of graph.nodes || []) {
        if (node.id !== active) continue;
        const g = nodesById[node.id];
        if (!g) continue;
        const a = absXY(node, placeById);
        for (const circle of g.querySelectorAll(
          "circle.opening-mark[data-opening]"
        )) {
          const oid = circle.getAttribute("data-opening");
          if (!oid || oid === entered) continue;
          const hop = conductorHopForOpening(active, oid);
          if (!hop) continue;
          const cx = Number(circle.getAttribute("cx") || 0);
          const cy = Number(circle.getAttribute("cy") || 0);
          const world = circleCenterWorld(circle) || {
            x: a.x + cx,
            y: a.y + cy,
          };
          out.push({
            ref: openingRefForNode(node.id, oid),
            x: world.x,
            y: world.y,
            el: circle,
            pick: () =>
              applyWiringConductorOpeningPick(node.id, oid, world.x, world.y),
          });
        }
      }
    }
    for (const elem of graph.elements || []) {
      if (
        kind === "conductor" &&
        Object.prototype.hasOwnProperty.call(wiringMode || {}, "activeContainer") &&
        elem.parent !== wiringMode.activeContainer
      ) {
        continue;
      }
      const g = elementsById[elem.id];
      if (!g) continue;
      const a = elementAbsXY(elem, placeById);
      for (const circle of g.querySelectorAll(
        "circle.element-terminal[data-terminal]"
      )) {
        const tid = circle.getAttribute("data-terminal");
        if (!tid) continue;
        const cx = Number(circle.getAttribute("cx") || 0);
        const cy = Number(circle.getAttribute("cy") || 0);
        const world = circleCenterWorld(circle) || {
          x: a.x + cx,
          y: a.y + cy,
        };
        const elRef = elem;
        const terminalId = tid;
        out.push({
          ref: terminalRefForElem(elRef, terminalId),
          x: world.x,
          y: world.y,
          el: circle,
          pick: () =>
            applyWiringTerminalPick(elRef, terminalId, world.x, world.y),
        });
      }
    }
    return out;
  }

  function nearestWiringSnap(world, kind, excludeRef) {
    if (!world || !kind) return null;
    const maxD = wiringSnapRadius();
    let best = null;
    let bestD = maxD;
    for (const c of wiringSnapCandidates(kind)) {
      if (excludeRef && c.ref === excludeRef) continue;
      const d = Math.hypot(c.x - world.x, c.y - world.y);
      if (d <= bestD) {
        bestD = d;
        best = c;
      }
    }
    return best;
  }

  /**
   * Resolve snap for a click: geometric nearest, else sticky hover target
   * if the pointer is still reasonably close to it.
   */
  function resolveWiringSnap(world) {
    if (!wiringMode) return null;
    const near = nearestWiringSnap(world, wiringMode.kind, wiringMode.from);
    if (near) return near;
    const hover = wiringHoverSnap;
    if (!hover || (wiringMode.from && hover.ref === wiringMode.from)) {
      return null;
    }
    // Hover stickiness: allow a bit more slack than live radius.
    const stick = wiringSnapRadius() * 1.75;
    if (Math.hypot(hover.x - world.x, hover.y - world.y) <= stick) {
      return hover;
    }
    return null;
  }

  function tryWiringSnapAtPointer(clientX, clientY) {
    if (!wiringMode) return false;
    const world = clientToWorld(clientX, clientY);
    const snap = resolveWiringSnap(world);
    if (!snap) return false;
    snap.pick();
    syncWiringPointer(clientX, clientY);
    return true;
  }

  function updateWiringSnapHighlight(cand) {
    clearWiringSnapHighlight();
    if (cand?.el) cand.el.classList.add("wiring-snap");
  }

  function updateWiringPreview(endWorld) {
    if (
      !wiringMode?.from ||
      !endWorld ||
      !worldEl ||
      !Number.isFinite(wiringMode.lastX ?? wiringMode.fromX) ||
      !Number.isFinite(wiringMode.lastY ?? wiringMode.fromY)
    ) {
      document.getElementById("wiring-preview")?.remove();
      return;
    }
    const pts = simpleOrthoPts(
      {
        x: wiringMode.lastX ?? wiringMode.fromX,
        y: wiringMode.lastY ?? wiringMode.fromY,
      },
      endWorld
    );
    if (!pts || pts.length < 2) {
      document.getElementById("wiring-preview")?.remove();
      return;
    }
    const d = pointsToPathD(pts);
    let path = document.getElementById("wiring-preview");
    if (!path) {
      path = el("path", {
        id: "wiring-preview",
        class: `wiring-preview wiring-preview-${wiringMode.kind}`,
      });
      worldEl.appendChild(path);
    } else {
      path.setAttribute(
        "class",
        `wiring-preview wiring-preview-${wiringMode.kind}`
      );
    }
    path.setAttribute("d", d);
  }

  function appendWiringDraftSegment(from, to) {
    if (!worldEl || !from || !to) return;
    const pts = simpleOrthoPts(from, to);
    if (!pts || pts.length < 2) return;
    let draft = document.getElementById("wiring-draft");
    if (!draft) {
      draft = el("g", { id: "wiring-draft" });
      worldEl.appendChild(draft);
    }
    draft.appendChild(
      el("path", {
        class: `wiring-draft wiring-draft-${wiringMode?.kind || "conductor"}`,
        d: pointsToPathD(pts),
      })
    );
  }

  function openingWorldPoint(nodeId, openingId) {
    const g = nodesById[nodeId];
    const circle = g?.querySelector(
      `circle.opening-mark[data-opening="${CSS.escape(String(openingId))}"]`
    );
    const fromCircle = circleCenterWorld(circle);
    if (fromCircle) return fromCircle;
    const node = (graph?.nodes || []).find((n) => n.id === nodeId);
    const byId = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
    if (!node) return null;
    const mouth = openingMouthAbs(node, openingId, openingId?.[0], byId);
    return mouth ? { x: mouth.x, y: mouth.y } : null;
  }

  function syncWiringPointer(clientX, clientY) {
    if (!wiringMode) return;
    const world = clientToWorld(clientX, clientY);
    const snap = nearestWiringSnap(world, wiringMode.kind, wiringMode.from);
    wiringHoverSnap = snap;
    updateWiringSnapHighlight(snap);
    if (wiringMode.from) {
      updateWiringPreview(snap ? { x: snap.x, y: snap.y } : world);
    } else {
      document.getElementById("wiring-preview")?.remove();
    }
  }

  function applyWiringOpeningPick(nodeId, openingId, localX, localY) {
    if (!wiringMode || wiringMode.kind !== "conduit") return false;
    const ref = openingRefForNode(nodeId, openingId);
    const byId = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
    const node = byId[nodeId];
    let x = localX;
    let y = localY;
    if (node && Number.isFinite(localX) && Number.isFinite(localY)) {
      const a = absXY(node, byId);
      x = a.x + localX;
      y = a.y + localY;
    } else if (node) {
      const m = openingMouthAbs(node, openingId, openingId?.[0], byId);
      x = m.x;
      y = m.y;
    }
    if (!wiringMode.from) {
      setWiringMode({
        kind: "conduit",
        from: ref,
        fromX: x,
        fromY: y,
        lastX: x,
        lastY: y,
      });
      setStatus(t("status.wiringConduitTo", { from: ref }));
      return true;
    }
    if (wiringMode.from === ref) {
      setStatus(t("status.wiringSameEnd"));
      return true;
    }
    completeWiringConduit(ref).catch((err) =>
      setStatus(String(err.message || err))
    );
    return true;
  }

  function applyWiringTerminalPick(elem, terminalId, worldX, worldY) {
    if (!wiringMode || wiringMode.kind !== "conductor") return false;
    const ref = terminalRefForElem(elem, terminalId);
    let x = worldX;
    let y = worldY;
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      const placeById = Object.fromEntries(
        (graph?.nodes || []).map((n) => [n.id, n])
      );
      const p = terminalCellAnchor(elem, terminalId, placeById);
      x = p.x;
      y = p.y;
    }
    if (!wiringMode.from) {
      setWiringMode({
        kind: "conductor",
        from: ref,
        fromX: x,
        fromY: y,
        activeContainer: elem.parent || null,
        enteredOpening: null,
        conduitPath: [],
        pathSteps: [],
        history: [],
        completedSegments: [],
        readyToCommit: false,
      });
      setStatus(t("status.wiringConductorNext", { from: ref }));
      return true;
    }
    if (wiringMode.from === ref && !(wiringMode.conduitPath || []).length) {
      setStatus(t("status.wiringSameEnd"));
      return true;
    }
    if (elem.parent !== wiringMode.activeContainer) return false;
    const from = {
      x: wiringMode.lastX ?? wiringMode.fromX,
      y: wiringMode.lastY ?? wiringMode.fromY,
    };
    appendWiringDraftSegment(from, { x, y });
    const segment = {
      from: wiringMode.from,
      to: ref,
      conduitPath: wiringMode.conduitPath || [],
    };
    setWiringMode({
      kind: "conductor",
      from: ref,
      fromX: x,
      fromY: y,
      lastX: x,
      lastY: y,
      activeContainer: elem.parent || null,
      enteredOpening: null,
      conduitPath: [],
      pathSteps: [],
      history: [
        ...(wiringMode.history || []),
        { ...wiringMode, draftSegmentCount: 1 },
      ],
      completedSegments: [...(wiringMode.completedSegments || []), segment],
      readyToCommit: true,
    });
    setStatus(t("status.wiringConductorSegmentReady", { to: ref }));
    return true;
  }

  /**
   * Resolve the conduit selected by an opening click, oriented away from the
   * current container. An opening with more than one conduit is ambiguous.
   */
  function conductorHopForOpening(containerId, openingId) {
    const matches = (graph?.edges || [])
      .filter((edge) => {
        const from = edge.from === containerId && edge.from_opening === openingId;
        const to = edge.to === containerId && edge.to_opening === openingId;
        return (from || to) && edge.from !== edge.to;
      })
      .map((edge) =>
        edge.from === containerId
          ? {
              conduit: edge.id,
              from: edge.from,
              to: edge.to,
              from_opening: edge.from_opening,
              to_opening: edge.to_opening,
            }
          : {
              conduit: edge.id,
              from: edge.to,
              to: edge.from,
              from_opening: edge.to_opening,
              to_opening: edge.from_opening,
            }
      );
    return matches.length === 1 ? matches[0] : null;
  }

  function applyWiringConductorOpeningPick(nodeId, openingId, worldX, worldY) {
    if (!wiringMode || wiringMode.kind !== "conductor" || !wiringMode.from) {
      return false;
    }
    if (nodeId !== wiringMode.activeContainer) return false;
    const hop = conductorHopForOpening(nodeId, openingId);
    if (!hop) {
      setStatus(t("status.wiringConductorOpeningUnavailable"));
      return true;
    }
    const from = {
      x: wiringMode.lastX ?? wiringMode.fromX,
      y: wiringMode.lastY ?? wiringMode.fromY,
    };
    const entered = openingWorldPoint(hop.to, hop.to_opening);
    appendWiringDraftSegment(from, { x: worldX, y: worldY });
    if (entered) appendWiringDraftSegment({ x: worldX, y: worldY }, entered);
    setWiringMode({
      ...wiringMode,
      lastX: entered?.x ?? worldX,
      lastY: entered?.y ?? worldY,
      activeContainer: hop.to,
      enteredOpening: hop.to_opening,
      conduitPath: [...(wiringMode.conduitPath || []), hop],
      pathSteps: [
        ...(wiringMode.pathSteps || []),
        {
          activeContainer: wiringMode.activeContainer,
          enteredOpening: wiringMode.enteredOpening,
          lastX: from.x,
          lastY: from.y,
          draftSegmentCount: entered ? 2 : 1,
        },
      ],
      history: [
        ...(wiringMode.history || []),
        { ...wiringMode, draftSegmentCount: entered ? 2 : 1 },
      ],
      readyToCommit: false,
    });
    setStatus(t("status.wiringConductorEntered", { container: hop.to }));
    return true;
  }

  function undoWiringConductorStep() {
    if (!wiringMode || wiringMode.kind !== "conductor") return false;
    const history = wiringMode.history || [];
    const previous = history.at(-1);
    if (!previous) return false;
    const draft = document.getElementById("wiring-draft");
    for (let i = 0; i < previous.draftSegmentCount; i += 1) {
      draft?.lastElementChild?.remove();
    }
    if (draft && !draft.childElementCount) draft.remove();
    const { draftSegmentCount, ...restored } = previous;
    setWiringMode({ ...restored, history: history.slice(0, -1) });
    setStatus(t("status.wiringConductorUndone"));
    return true;
  }

  async function beginWiringGesture(kind) {
    if (!hasDocument || !locationId) {
      setStatus(t("status.needDocument"));
      return;
    }
    // Neither endpoint-based connection type consumes a prior selection.
    if (selectedIds.size || selectedLinkId) clearSelectionState();
    if (kind === "conductor" && !showElectrical) {
      await setElectrical(true);
    }
    setWiringMode({ kind, from: null });
    setStatus(
      kind === "conduit"
        ? t("status.wiringConduitFrom")
        : t("status.wiringConductorFrom")
    );
  }

  async function beginCableFromSelection() {
    if (!hasDocument || !locationId) {
      setStatus(t("status.needDocument"));
      return;
    }
    const seed = cableSelectionSeed();
    setWiringMode({
      kind: "cable",
      from: null,
      cableRoute: null,
      selectedConductors: [],
      cableHistory: [],
    });
    syncCableCandidateVisuals();
    if (seed) {
      clearSelectionState();
      pickCableMember(seed);
      return;
    }
    setStatus(t("status.wiringCableFrom"));
  }

  async function completeCableCable() {
    const contains = wiringMode?.kind === "cable"
      ? wiringMode.selectedConductors || []
      : [];
    if (!contains.length) return;
    setWiringMode(null);
    syncCableCandidateVisuals();
    const res = await api("/api/connection/cable", {
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
    await selectLink(res.detail.id, "Cable");
    setStatus(t("status.linkGrouped"));
  }

  function openingRefForNode(nodeId, openingId) {
    const sitePlace = canvasToSiteId(nodeId);
    if (!sitePlace || sitePlace === ".") return `.${openingId}`;
    const rel = siteToCanvasRelative(sitePlace) || nodeId;
    return `${rel}.${openingId}`;
  }

  function terminalRefForElem(elem, terminalId) {
    const leaf = elem.leaf_id || String(elem.id).split("/").pop();
    const parent = elem.parent;
    if (parent && parent !== ".") return `${parent}/${leaf}.${terminalId}`;
    return `${leaf}.${terminalId}`;
  }

  async function completeWiringConduit(toRef) {
    const fromRef = wiringMode?.from;
    setWiringMode(null);
    if (!fromRef) return;
    const res = await api("/api/connection/conduit", {
      method: "POST",
      body: JSON.stringify({
        location_id: locationId,
        owner_id: locationId,
        from: fromRef,
        to: toRef,
        depth: depthLevel,
      }),
    });
    if (res.graph) {
      graph = res.graph;
      render();
    }
    applyEditFlags(res);
    await selectLink(res.detail.id, "Conduit");
    setStatus(t("status.conduitCreated"));
  }

  async function completeWiringConductor() {
    const segments = wiringMode?.completedSegments || [];
    setWiringMode(null);
    if (!segments.length) return;
    let lastRes = null;
    for (const segment of segments) {
      const res = await api("/api/connection/conductor", {
        method: "POST",
        body: JSON.stringify({
          location_id: locationId,
          owner_id: locationId,
          from: segment.from,
          to: segment.to,
          conduit_path: segment.conduitPath,
          depth: depthLevel,
        }),
      });
      lastRes = res;
      if (res.graph) graph = res.graph;
      applyEditFlags(res);
    }
    if (graph) render();
    if (lastRes?.detail?.id) await selectLink(lastRes.detail.id, "Conductor");
    setStatus(t("status.conductorCreated"));
  }

  function onWiringOpeningClick(nodeId, openingId, ev) {
    if (!wiringMode) return false;
    ev.stopPropagation();
    ev.preventDefault();
    if (wiringMode.kind === "conductor") {
      const g = nodesById[nodeId];
      const circle = g?.querySelector(
        `circle.opening-mark[data-opening="${CSS.escape(String(openingId))}"]`
      );
      const cx = circle ? Number(circle.getAttribute("cx") || 0) : NaN;
      const cy = circle ? Number(circle.getAttribute("cy") || 0) : NaN;
      const node = (graph?.nodes || []).find((n) => n.id === nodeId);
      const byId = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
      const a = node ? absXY(node, byId) : { x: 0, y: 0 };
      return applyWiringConductorOpeningPick(nodeId, openingId, a.x + cx, a.y + cy);
    }
    if (wiringMode.kind !== "conduit") return false;
    const g = nodesById[nodeId];
    const circle = g?.querySelector(
      `circle.opening-mark[data-opening="${CSS.escape(String(openingId))}"]`
    );
    const cx = circle ? Number(circle.getAttribute("cx") || 0) : NaN;
    const cy = circle ? Number(circle.getAttribute("cy") || 0) : NaN;
    return applyWiringOpeningPick(nodeId, openingId, cx, cy);
  }

  function onWiringTerminalClick(elem, terminalId, ev) {
    if (!wiringMode || wiringMode.kind !== "conductor") return false;
    ev.stopPropagation();
    ev.preventDefault();
    const placeById = Object.fromEntries(
      (graph?.nodes || []).map((n) => [n.id, n])
    );
    const p = terminalCellAnchor(elem, terminalId, placeById);
    return applyWiringTerminalPick(elem, terminalId, p.x, p.y);
  }

  async function selectLink(linkId, typeHint) {
    clearSelectionSilent();
    selectedLinkId = linkId;
    selectedLinkType = typeHint || null;
    setSelectedVisual();
    highlightOutlineSelection();
    await fillLinkInspector(linkId);
  }

  function clearSelectionSilent() {
    selectedIds.clear();
    selectedId = null;
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

  /** World-space stroke width so a painted link stays easy to click at any zoom. */
  function linkHitStrokeWorld(visualW) {
    const visual = Math.max(0, Number(visualW) || 0);
    return Math.max(
      visual + LINK_HIT_PAD,
      LINK_HIT_PX / Math.max(scale, 0.05)
    );
  }

  /**
   * Cable lanes need distinct hit areas: the general 16px link target is
   * wider than their pitch and makes adjacent cables impossible to choose.
   */
  function cableHitStrokeWorld(visualW) {
    const visual = Math.max(0, Number(visualW) || 0);
    return Math.min(
      linkHitStrokeWorld(visual),
      visual + 1
    );
  }

  function syncLinkHitStrokes() {
    document
      .querySelectorAll(".edge-tube-hit, .cable-strand-hit, .cable-jacket-hit")
      .forEach((el) => {
        const visual = Number(el.getAttribute("data-hit-visual") || 0);
        el.style.strokeWidth = String(
          el.classList.contains("edge-tube-hit")
            ? linkHitStrokeWorld(visual)
            : cableHitStrokeWorld(visual)
        );
      });
  }

  function bindLinkHit(el, linkId, type) {
    el.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0 || shouldPanPointer(ev)) return;
      ev.stopPropagation();
      ev.preventDefault();
      if (wiringMode?.kind === "cable") {
        if (type === "Conductor" || type === "Cable") {
          pickCableMembers([linkId], Boolean(ev.ctrlKey || ev.metaKey));
        }
        return;
      }
      selectLink(linkId).catch((err) =>
        setStatus(String(err.message || err))
      );
    });
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
    if (wiringMode?.kind === "conductor" || wiringMode?.kind === "conduit") {
      if (hitEl) hitEl.style.cursor = "";
      return;
    }
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
        const depth = isoDepth(node);
        autoW =
          node.w == null
            ? leafWidthForLabel(node.display_name || node.name || node.id) +
              depth
            : node.w;
        autoH = node.h == null ? LEAF_H + depth : node.h;
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
        const depth = isoDepth(node);
        if (depth) {
          autoW += depth;
          autoH += depth;
        }
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
      const origin = contentOriginLocal(parent);
      const fr = frontRectLocal(parent);
      const ox = pa.x + origin.x;
      const oy = pa.y + origin.y;
      let maxR = Math.max(0, fr.w - 2 * PAD);
      let maxB = Math.max(0, fr.h - HEADER - PAD);
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
      const depth = isoDepth(parent);
      const newW = Math.max(LEAF_W, maxR + 2 * PAD) + depth;
      const newH = Math.max(LEAF_H, HEADER + maxB + PAD) + depth;
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
    const origin = contentOriginLocal(parent);
    return {
      x: pa.x + origin.x + local.x,
      y: pa.y + origin.y + local.y,
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

