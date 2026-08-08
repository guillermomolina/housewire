  /* === 05-shell.js: Zoom, docs/tabs, menus, palette, boot ===
   * Fragment of the UI IIFE (bundled into ../app.js).
   * Edit this file, then run: python scripts/bundle_ui_app.py
   */
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

  async function fileOpen() {
    rememberCurrentDocView();
    try {
      if (isDesktopMode()) {
        const path = await desktopBridge().openYaml();
        if (!path) return;
        const st = await api("/api/workspace/open", {
          method: "POST",
          body: JSON.stringify({ path }),
        });
        applyWorkspaceStatus(st);
        await rememberDesktopRecent(path);
        await reloadAfterDocumentChange();
        const name =
          (st.document && (st.document.yaml || st.document.title)) || path;
        setStatus(t("status.opened", { name }));
        return;
      }
      const picked = await pickOpenYamlFileWeb();
      if (!picked) return;
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
      setStatus(t("status.opened", { name: picked.name }));
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }

  async function fileNew() {
    rememberCurrentDocView();
    try {
      const locale = I18n.getLocale ? I18n.getLocale() : "en";
      const st = await api("/api/workspace/new", {
        method: "POST",
        body: JSON.stringify({ locale }),
      });
      applyWorkspaceStatus(st);
      await reloadAfterDocumentChange();
      // New empty site: select the root place and show its properties.
      highlightOutline(".");
      clearSelectionState();
      setSelectedVisual();
      await fillPlaceInspector(".");
      const name =
        (st.document && (st.document.yaml || st.document.title)) ||
        t("file.newSiteTitle");
      setStatus(t("status.newSite", { name }));
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }

  async function fileSaveAs() {
    try {
      if (isDesktopMode()) {
        let suggested = "housewire.yaml";
        try {
          const exported = await api("/api/workspace/yaml");
          suggested = exported.filename || suggested;
        } catch {
          /* keep default */
        }
        const path = await desktopBridge().saveYamlAs(suggested);
        if (!path) return;
        const previousDocId = activeDocId;
        rememberCurrentDocView();
        const st = await api("/api/workspace/save-as-file", {
          method: "POST",
          body: JSON.stringify({ path }),
        });
        applyWorkspaceStatus(st);
        replaceActiveDocumentView(previousDocId);
        await rememberDesktopRecent(path);
        dirtyLocal = false;
        updateSaveButton(false);
        const name =
          (st.document && (st.document.yaml || st.document.title)) || path;
        setStatus(t("status.savedAs", { name }));
        return;
      }

      let exported;
      try {
        exported = await api("/api/workspace/yaml");
      } catch (err) {
        setStatus(String(err.message || err));
        return;
      }
      const suggested = exported.filename || "housewire.yaml";
      const result = await pickSaveYamlFileWeb(suggested, exported.content);
      if (!result) return;
      await replaceBrowserDocument(
        result.name,
        exported.content,
        result.handle || null
      );
      setStatus(
        result.downloaded
          ? `downloaded ${result.name}`
          : t("status.savedAs", { name: result.name })
      );
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }

  async function saveBrowserDocumentInApp() {
    const exported = await api("/api/workspace/yaml");
    const suggested = exported.filename || "housewire.yaml";
    const filename = await promptText({
      title: t("menu.file.save"),
      message: t("modal.saveAsMessage"),
      label: t("modal.filename"),
      value: suggested,
      placeholder: "housewire.yaml",
      okLabel: t("menu.file.save"),
    });
    if (!filename) return null;
    const st = await replaceBrowserDocument(filename, exported.content);
    setStatus(t("status.savedAs", { name: filename }));
    return st;
  }

  async function replaceBrowserDocument(filename, content, handle = null) {
    const previousDocId = activeDocId;
    rememberCurrentDocView();
    const st = await api("/api/workspace/save-as-content", {
      method: "POST",
      body: JSON.stringify({ filename, content }),
    });
    applyWorkspaceStatus(st);
    replaceActiveDocumentView(previousDocId);
    if (handle && activeDocId) fileHandles[activeDocId] = handle;
    dirtyLocal = false;
    updateSaveButton(false);
    return st;
  }

  function replaceActiveDocumentView(previousDocId) {
    if (!previousDocId || previousDocId === activeDocId) return;
    if (docViews[previousDocId]) {
      docViews[activeDocId] = docViews[previousDocId];
    }
    delete docViews[previousDocId];
    delete fileHandles[previousDocId];
    persistDocViews();
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
        setStatus(t("status.documentClosedNeedOpen"));
        return;
      }
      if (wasActive) {
        resetCanvasState();
        await loadLocations();
      }
      setStatus(t("status.documentClosed"));
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
      setStatus(
        t("status.switchedTo", {
          name: (st.document && st.document.title) || docId,
        })
      );
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }

  async function handleFileAction(action) {
    closeFileMenu();
    if (action === "new") await fileNew();
    else if (action === "open") await fileOpen();
    else if (action === "save") {
      try {
        await saveDocument();
      } catch (err) {
        setStatus(String(err.message || err));
      }
    } else if (action === "save-as") await fileSaveAs();
    else if (action === "close") await fileClose();
    else if (action === "reload") await fileReload();
    else if (action === "quit") await desktopQuit();
  }

  async function fileReload() {
    if (!hasDocument) return;
    const title = activeYamlName || t("modal.unsavedThisFile");
    if (dirtyLocal) {
      const ok = await confirmReloadDiscard(title);
      if (!ok) return;
    }
    rememberCurrentDocView();
    try {
      const st = await api("/api/workspace/reload", {
        method: "POST",
        body: "{}",
      });
      applyWorkspaceStatus(st);
      dirtyLocal = false;
      updateSaveButton(false);
      resetCanvasState();
      await loadLocations();
      setStatus(t("status.reloaded", { name: activeYamlName || title }));
    } catch (err) {
      setStatus(String(err.message || err));
    }
  }

  async function rememberDesktopRecent(filePath) {
    if (!isDesktopMode() || !filePath) return;
    const bridge = desktopBridge();
    if (!bridge || typeof bridge.rememberRecent !== "function") return;
    try {
      await bridge.rememberRecent(filePath);
      await refreshRecentMenu();
    } catch {
      /* ignore */
    }
  }

  async function desktopQuit() {
    if (!isDesktopMode()) return;
    const bridge = desktopBridge();
    if (bridge && typeof bridge.quit === "function") {
      await bridge.quit();
    }
  }

  async function desktopToggleFullscreen() {
    if (!isDesktopMode()) return;
    const bridge = desktopBridge();
    if (bridge && typeof bridge.toggleFullscreen === "function") {
      await bridge.toggleFullscreen();
    }
  }

  async function openRecentPath(filePath) {
    if (!filePath) return;
    rememberCurrentDocView();
    try {
      const st = await api("/api/workspace/open", {
        method: "POST",
        body: JSON.stringify({ path: filePath }),
      });
      applyWorkspaceStatus(st);
      await rememberDesktopRecent(filePath);
      await reloadAfterDocumentChange();
      const name =
        (st.document && (st.document.yaml || st.document.title)) || filePath;
      setStatus(t("status.opened", { name }));
    } catch (err) {
      const bridge = desktopBridge();
      if (bridge && typeof bridge.forgetRecent === "function") {
        try {
          await bridge.forgetRecent(filePath);
          await refreshRecentMenu();
        } catch {
          /* ignore */
        }
      }
      setStatus(String(err.message || err));
    }
  }

  function basenamePath(filePath) {
    const s = String(filePath || "");
    const parts = s.split(/[/\\]/);
    return parts[parts.length - 1] || s;
  }

  async function refreshRecentMenu() {
    const flyout = document.getElementById("menu-recent");
    const empty = document.getElementById("menu-recent-empty");
    if (!flyout || !isDesktopMode()) return;
    const bridge = desktopBridge();
    let paths = [];
    try {
      if (bridge && typeof bridge.listRecent === "function") {
        paths = (await bridge.listRecent()) || [];
      }
    } catch {
      paths = [];
    }
    flyout.querySelectorAll("[data-recent-path]").forEach((el) => el.remove());
    if (!paths.length) {
      if (empty) empty.classList.remove("hidden");
      return;
    }
    if (empty) empty.classList.add("hidden");
    for (const filePath of paths) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("role", "menuitem");
      btn.setAttribute("data-recent-path", filePath);
      btn.title = filePath;
      const main = document.createElement("span");
      main.className = "menu-item-main";
      const label = document.createElement("span");
      label.textContent = basenamePath(filePath);
      main.appendChild(label);
      btn.appendChild(main);
      flyout.appendChild(btn);
    }
  }

  function applyDesktopShellChrome() {
    if (!isDesktopMode()) return;
    document.body.classList.add("desktop-shell");
    document.querySelectorAll("[data-desktop-only]").forEach((el) => {
      el.hidden = false;
    });
    refreshRecentMenu().catch(() => {});
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
    // Load physical view first; restore electrical only if depth is max after load.
    const wantElectrical = Boolean(saved && saved.showElectrical);
    showElectrical = false;
    syncElectricalUi();
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
      // Default boot: depth 1. Restore a saved depth only when it is a number.
      if (saved && Number.isFinite(saved.depthLevel) && saved.depthLevel >= 1) {
        depthLevel = Math.floor(saved.depthLevel);
      } else {
        depthLevel = DEPTH_DEFAULT;
      }
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
      // Electrical only at max depth (e.g. 3/3). Never leave it on at 1/x.
      if (
        wantElectrical &&
        depthLevel >= Math.max(maxDepth, 1)
      ) {
        await setElectrical(true);
      } else {
        enforceElectricalDepthInvariant({ repaint: false });
        syncElectricalUi();
      }
    } else {
      setStatus(t("status.noLocations"));
    }
  }

  async function refreshDocumentLabel() {
    // Tabs show file name + dirty bullet; keep them in sync after save/open.
    try {
      applyWorkspaceStatus(await api("/api/workspace"));
    } catch {
      /* ignore */
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
      const dirty =
        Boolean(doc.dirty) ||
        (doc.id === active && dirtyLocal) ||
        ((st.dirty || []).length > 0 && doc.id === active);
      // Prefer real filename (with .yaml) over a title without extension.
      const tabName = doc.yaml || doc.title || "untitled";
      label.textContent = (dirty ? "• " : "") + tabName;
      label.title = doc.yaml_path || doc.path || tabName;
      btn.appendChild(label);
      const close = document.createElement("button");
      close.type = "button";
      close.className = "view-tab-close";
      close.title = "Close file";
      close.setAttribute("aria-label", `Close ${tabName}`);
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

  /** Site ids from root (``.``) down to a canvas location id. */
  function sitePathIds(siteId) {
    const canvas = String(siteId || ".").trim() || ".";
    if (canvas === ".") return ["."];
    const segments = canvas.split("/").filter(Boolean);
    const ids = ["."];
    for (let i = 0; i < segments.length; i++) {
      ids.push(segments.slice(0, i + 1).join("/"));
    }
    return ids;
  }

  /** How many canvas levels up ``toId`` is from ``fromId`` (same branch only). */
  function canvasLevelsUp(fromId, toId) {
    const from = fromId || ".";
    const to = toId || ".";
    if (from === to) return 0;
    if (to !== "." && !from.startsWith(`${to}/`)) return 0;
    const path = sitePathIds(from);
    const fromIdx = path.indexOf(from);
    const toIdx = path.indexOf(to);
    if (fromIdx < 0 || toIdx < 0 || toIdx >= fromIdx) return 0;
    return fromIdx - toIdx;
  }

  async function setCanvasLocation(id, { resetDepth = true, fit = true } = {}) {
    if (!id) return;
    const prev = locationId;
    if (resetDepth) {
      depthLevel = DEPTH_DEFAULT;
    } else {
      const up = canvasLevelsUp(prev, id);
      if (up > 0) depthLevel = depthLevel + up;
    }
    locationId = id;
    expandOutlineAncestors(id);
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

  /** True when ``placeSiteId`` is on or under the current canvas location. */
  function outlinePlaceUnderCanvas(placeSiteId) {
    const canvas = locationId || ".";
    if (canvas === "." || canvas === "") return true;
    if (placeSiteId === canvas) return true;
    return placeSiteId.startsWith(`${canvas}/`);
  }

  /** Site ids from root (``.``) down to the current canvas location. */
  function canvasLocationPathIds() {
    return sitePathIds(locationId);
  }

  function isOnCanvasLocationPath(placeSiteId) {
    if (!placeSiteId) return false;
    return canvasLocationPathIds().includes(placeSiteId);
  }

  function isOutlinePlaceVisibleById(placeSiteId) {
    if (!placeSiteId) return false;
    // Breadcrumb: ancestors on the path to the current canvas (click to go up).
    if (isOnCanvasLocationPath(placeSiteId)) return true;
    if (!outlinePlaceUnderCanvas(placeSiteId)) return false;
    const rel = placeDepthUnderCanvas(placeSiteId, locationId || ".");
    return rel <= depthLevel;
  }

  /** Place has no child place visible at the current depth (canvas leaf). */
  function isOutlinePlaceLeafInView(placeSiteId) {
    return !outlineNodes.some(
      (n) =>
        n.kind === "place" &&
        n.id !== placeSiteId &&
        isOutlinePlaceVisibleById(n.id) &&
        outlineParentId(n) === placeSiteId
    );
  }

  function isOutlinePlaceChainVisible(placeSiteId) {
    if (!isOutlinePlaceVisibleById(placeSiteId)) return false;
    let cur = placeSiteId;
    while (cur && cur !== ".") {
      const parent = cur.includes("/")
        ? cur.slice(0, cur.lastIndexOf("/"))
        : ".";
      if (!isOutlinePlaceVisibleById(parent)) return false;
      if (parent === ".") break;
      cur = parent;
    }
    return true;
  }

  /** Same visibility rules as the physical canvas (depth + electrical + leaves). */
  function isOutlineNodeVisible(node) {
    if (!node) return false;
    if (node.kind === "place") {
      return isOutlinePlaceChainVisible(node.id);
    }
    if (node.kind === "element") {
      if (!showElectrical) return false;
      const parent = node.parent;
      if (!parent || !isOutlinePlaceChainVisible(parent)) return false;
      return isOutlinePlaceLeafInView(parent);
    }
    return true;
  }

  function outlineHasKids(nodeId) {
    return outlineNodes.some((n) => {
      if (outlineParentId(n) !== nodeId) return false;
      return isOutlineNodeVisible(n);
    });
  }

  function isOutlineHidden(node) {
    if (node && isOnCanvasLocationPath(node.id)) return false;
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
      if (!isOutlineNodeVisible(node)) continue;
      if (isOutlineHidden(node)) continue;
      const onPath =
        node.kind === "place" && isOnCanvasLocationPath(node.id);
      const canvasHere = locationId || ".";
      const isCanvasRoot =
        node.id === canvasHere ||
        (node.id === "." && (canvasHere === "." || canvasHere === ""));
      const row = document.createElement("div");
      row.className =
        "outline-item" +
        (node.kind === "element" ? " element" : "") +
        (onPath && !isCanvasRoot ? " outline-crumb" : "");
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

  /** Minimum depth so a site place is visible on the canvas and in the outline. */
  function depthRequiredForSitePlace(sitePlaceId) {
    return placeDepthUnderCanvas(sitePlaceId, locationId || ".");
  }

  function bumpMaxDepthFromGraph(g) {
    if (g && g.max_depth != null) {
      maxDepth = Math.max(maxDepth, g.max_depth);
    }
  }

  /** Deepen the view when a nested place would be hidden at the current depth. */
  async function ensureDepthForSitePlace(sitePlaceId) {
    const required = depthRequiredForSitePlace(sitePlaceId);
    if (required <= depthLevel) {
      updateDepthLabel();
      renderOutline();
      return false;
    }
    await setDepth(required);
    return true;
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
    // Site root is always the canvas for an empty (or root) view — show its
    // properties even if outline selectable flags lag behind locations API.
    if (placeId === ".") {
      if (locationId !== ".") {
        await setCanvasLocation(".", { resetDepth: false });
      }
      highlightOutline(".");
      clearSelectionState();
      setSelectedVisual();
      await fillPlaceInspector(".");
      return;
    }
    if (node.selectable) {
      if (locationId !== placeId) {
        const goingUp = canvasLevelsUp(locationId, placeId) > 0;
        await setCanvasLocation(placeId, { resetDepth: !goingUp });
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
      setStatus(t("status.noCanvasView", { id: placeId }));
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
      setStatus(t("status.noCanvasView", { id: parentPlace }));
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
      await setElectrical(true);
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
      bits.push(t("status.autoPlacedPlaces", { n: filled.length }));
    }
    if (filledElem.length) {
      bits.push(t("status.autoPlacedElements", { n: filledElem.length }));
    }
    if (bits.length) {
      setStatus(t("status.autoPlaced", { bits: bits.join(" + ") }));
    }
    renderOutline();
    updateDocStatusStrip();
  }

  async function setDepth(next) {
    const wanted = Math.max(1, Math.floor(Number(next) || 1));
    if (wanted === depthLevel && graph) {
      updateDepthLabel();
      renderOutline();
      return;
    }
    // Electrical only at max depth: drop it before loading a shallower view.
    if (showElectrical && wanted < Math.max(maxDepth, 1)) {
      showElectrical = false;
      depthBeforeElectrical = null;
      syncElectricalUi();
    }
    depthLevel = wanted;
    await loadLocation({ fit: false });
    enforceElectricalDepthInvariant({ repaint: true });
  }

  syncElectricalUi();

  document.getElementById("btn-electrical")?.addEventListener("click", () => {
    setElectrical(!showElectrical).catch((err) =>
      setStatus(String(err.message || err))
    );
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
    if (ev.key === "F5") {
      ev.preventDefault();
      fileReload().catch((err) => setStatus(String(err.message || err)));
      return;
    }
    if (ev.key === "F11" && isDesktopMode()) {
      ev.preventDefault();
      desktopToggleFullscreen().catch((err) =>
        setStatus(String(err.message || err))
      );
      return;
    }
    const mod = ev.ctrlKey || ev.metaKey;
    if (!mod) {
      if (
        ev.key === "Backspace" &&
        (wiringMode?.kind === "conductor"
          ? undoWiringConductorStep()
          : undoCableConductorPick())
      ) {
        // This listener runs before the window-level wiring shortcut. Stop it
        // here so Backspace cannot fall through to deletion of the selection.
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
      if (ev.key === "Delete" || ev.key === "Backspace") {
        const appModal = document.getElementById("app-modal");
        const insertModal = document.getElementById("insert-modal");
        if (appModal && !appModal.classList.contains("hidden")) return;
        if (insertModal && !insertModal.classList.contains("hidden")) return;
        if (selectedIds.size < 1 && !selectedLinkId) return;
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
    if (key === "q" && isDesktopMode()) {
      ev.preventDefault();
      desktopQuit().catch((err) => setStatus(String(err.message || err)));
      return;
    }
    if (key === "n") {
      ev.preventDefault();
      fileNew().catch((err) => setStatus(String(err.message || err)));
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

  document.getElementById("btn-new")?.addEventListener("click", () => {
    fileNew().catch((err) => setStatus(String(err.message || err)));
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
      const recentItem = ev.target.closest("[data-recent-path]");
      if (recentItem) {
        closeAllMenus();
        openRecentPath(recentItem.getAttribute("data-recent-path")).catch(
          (err) => setStatus(String(err.message || err))
        );
        return;
      }
      const subTrigger = ev.target.closest(".menu-submenu-trigger");
      if (subTrigger && menuFile.contains(subTrigger)) {
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
          refreshRecentMenu().catch(() => {});
          flyout.classList.remove("hidden");
          host.classList.add("is-open");
          subTrigger.setAttribute("aria-expanded", "true");
        }
        return;
      }
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
        const needsElec = insertItem.hasAttribute("data-needs-electrical");
        const runInsert = async () => {
          if (needsElec) {
            if (!elementsInsertEnabled()) {
              setStatus(t("palette.needsElectrical"));
              return;
            }
            if (!showElectrical) await setElectrical(true);
          }
          if (action === "element" || action === "container") {
            await openTypePickerFromInsert(action);
          } else if (action === "conduit") {
            await beginWiringGesture("conduit");
          } else if (action === "conductor") {
            await beginWiringGesture("conductor");
          } else if (action === "cable") {
            await beginSheathFromSelection();
          } else {
            openInsertModal(action);
          }
        };
        runInsert().catch((err) => {
          if (String(err.message || err) !== "electrical required") {
            insertMsg(String(err.message || err), true);
            setStatus(String(err.message || err));
          }
        });
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
        setElectrical(!showElectrical).catch((err) =>
          setStatus(String(err.message || err))
        );
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
      else if (action === "fullscreen") {
        desktopToggleFullscreen().catch((err) =>
          setStatus(String(err.message || err))
        );
      } else if (action === "depth-in") {
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
  applyDesktopShellChrome();
  updateWindowTitle();

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
        const runtime =
          isDesktopMode() ? "desktop" : about.runtime || "server";
        const ver = about.version
          ? t("about.version", { v: about.version })
          : "";
        versionEl.textContent = ver
          ? `${ver} · ${runtime}`
          : String(runtime);
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
        const isPlace = pendingCatalogPlacement.kind === "PlaceType";
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
      if (wiringMode && ev.button === 0 && !shouldPanPointer(ev)) {
        if (tryWiringSnapAtPointer(ev.clientX, ev.clientY)) {
          ev.preventDefault();
          ev.stopPropagation();
          return;
        }
        // Empty click while wiring: keep the gesture (no clear-selection pan).
        if (ev.target === svg || ev.target === viewport) {
          ev.preventDefault();
          return;
        }
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
    if (wiringMode && !pendingCatalogPlacement && !placementDrag) {
      syncWiringPointer(ev.clientX, ev.clientY);
    }
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
    if (pendingCatalogPlacement.kind !== "PlaceType") {
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
    if (ev.key === "Escape" && wiringMode) {
      ev.preventDefault();
      cancelWiringMode();
      return;
    }
    if (
      ev.key === "Backspace" &&
      (wiringMode?.kind === "conductor"
        ? undoWiringConductorStep()
        : undoCableConductorPick())
    ) {
      ev.preventDefault();
      return;
    }
    if (
      ev.key === "Enter" &&
      wiringMode?.kind === "conductor" &&
      wiringMode.readyToCommit
    ) {
      ev.preventDefault();
      completeWiringConductor().catch((err) =>
        setStatus(String(err.message || err))
      );
      return;
    }
    if (
      ev.key === "Enter" &&
      wiringMode?.kind === "cable" &&
      wiringMode.selectedConductors?.length
    ) {
      ev.preventDefault();
      completeCableSheath().catch((err) =>
        setStatus(String(err.message || err))
      );
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

  function isSingleSelectedPlace() {
    if (selectedIds.size !== 1 || !selectedId) return false;
    if ((graph?.elements || []).some((e) => e.id === selectedId)) return false;
    return (graph?.nodes || []).some((n) => n.id === selectedId);
  }

  /** Element insert in palette / Insert menu (electrical on, or one place selected). */
  function elementsInsertEnabled() {
    if (!hasDocument || !locationId) return false;
    if (showElectrical) return true;
    return isSingleSelectedPlace();
  }

  async function ensureElectricalForElementInsert() {
    if (showElectrical) return;
    if (!isSingleSelectedPlace()) {
      setStatus(t("palette.needsElectrical"));
      throw new Error("electrical required");
    }
    await setElectrical(true);
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
      const typeClass = row && row.kind === "PlaceType" ? "PlaceType" : "ElementType";
      const rows = paletteRows(typeClass, "");
      if (sel) {
        sel.innerHTML = "";
        for (const r of rows) {
          const opt = document.createElement("option");
          opt.value = catalogTypeKey(r);
          opt.textContent = r.label || catalogTypeKey(r);
          sel.appendChild(opt);
        }
        if (prev && rows.some((r) => catalogTypeKey(r) === prev)) sel.value = prev;
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
      if (typeEl) typeEl.value = String(row.label || catalogTypeKey(row) || "").trim();
      if (descEl) descEl.value = row.description || "";
      const subtypeId = pendingCatalogInsert.subtype || "";
      let subtypeLabel = "—";
      if (subtypeId) {
        const hit = subtypeRows(typeId).find((x) => catalogSubtypeKey(x) === String(subtypeId));
        subtypeLabel = (hit && (hit.label || catalogSubtypeKey(hit))) || String(subtypeId);
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
      const hay = `${catalogTypeKey(row)} ${row.label || ""} ${row.description || ""}`.toLowerCase();
      return hay.includes(needle);
    });
    rows.sort((a, b) =>
      String(a.label || catalogTypeKey(a) || "").localeCompare(
        String(b.label || catalogTypeKey(b) || ""),
        I18n.getLocale ? I18n.getLocale() : "en",
        { sensitivity: "base" }
      )
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
      opt.value = catalogSubtypeKey(row);
      opt.textContent = row.label || catalogSubtypeKey(row);
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

  /** Merge type + subtype catalog defaults (mirrors server apply). */
  function catalogEffectiveDefaults(typeId, subtype) {
    const row = (paletteCatalog && typeId && paletteCatalog[typeId]) || null;
    if (!row || typeof row !== "object") return {};
    /** @type {Record<string, unknown>} */
    const out = { ...(row.defaults || {}) };
    let sub = String(subtype || "").trim();
    if (!sub && out.subtype != null) sub = String(out.subtype).trim();
    const hit = (row.subtypes || []).find(
      (x) => catalogSubtypeKey(x) === sub
    );
    if (hit && hit.defaults && typeof hit.defaults === "object") {
      Object.assign(out, hit.defaults);
    }
    return out;
  }

  async function beginCatalogPlacement(draft) {
    if (draft && draft.kind === "ElementType") {
      try {
        await ensureElectricalForElementInsert();
      } catch {
        return;
      }
    }
    if (draft && draft.kind === "PlaceType") {
      try {
        await loadPaletteCatalog();
      } catch {
        /* proceed without defaults */
      }
      const defs = catalogEffectiveDefaults(draft.type_id, draft.subtype);
      if (Array.isArray(defs.openings)) draft.openings = defs.openings;
      if (defs.opening_grid && typeof defs.opening_grid === "object") {
        draft.opening_grid = defs.opening_grid;
      }
    }
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
    if (kind === "PlaceType") {
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

  /**
   * Like ``placeParentAtWorld``, but skips dragged places and their descendants
   * so a box can nest into whatever lies under it.
   */
  function nestPlaceCanvasIdAtWorld(wx, wy, excludeCanvasIds) {
    const exclude = excludeCanvasIds || [];
    const byId = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
    let bestId = ".";
    let bestDepth = -1;
    for (const n of graph?.nodes || []) {
      if (
        exclude.some(
          (ex) => n.id === ex || String(n.id).startsWith(`${ex}/`)
        )
      ) {
        continue;
      }
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

  /**
   * If place drag ends over another place, reparent into that place.
   * Returns true when the drop was handled (caller should skip position PATCH).
   */
  async function tryReparentPlacesAfterDrag(finished, items) {
    const placeItems = (items || []).filter((it) => it.kind === "place");
    if (!placeItems.length) return false;
    if ((items || []).some((it) => it.kind === "element")) return false;

    const byId = Object.fromEntries((graph?.nodes || []).map((n) => [n.id, n]));
    const rootItems = placeItems.filter(
      (it) =>
        !placeItems.some(
          (other) =>
            other.id !== it.id && String(it.id).startsWith(`${other.id}/`)
        )
    );
    if (!rootItems.length) return false;

    const exclude = placeItems.map((it) => it.id);
    const anchorId = finished.anchorId || rootItems[0].id;
    const anchor = byId[anchorId] || byId[rootItems[0].id];
    if (!anchor) return false;
    const center = nodeCenterAbs(anchor, byId);
    const nestCanvas = nestPlaceCanvasIdAtWorld(center.x, center.y, exclude);
    const nestSite =
      nestCanvas === "." ? locationId || "." : canvasToSiteId(nestCanvas);

    const rootSiteIds = rootItems.map((it) => canvasToSiteId(it.id));
    if (
      rootSiteIds.some(
        (sid) => nestSite === sid || nestSite.startsWith(`${sid}/`)
      )
    ) {
      return false;
    }
    if (!rootSiteIds.some((sid) => parentSiteIdOf(sid) !== nestSite)) {
      return false;
    }

    const positions = {};
    for (const it of rootItems) {
      const node = byId[it.id];
      if (!node) continue;
      const abs = absXY(node, byId);
      const local = worldToParentLocal(abs.x, abs.y, nestCanvas);
      const siteId = canvasToSiteId(it.id);
      positions[siteId] = { x: local.x, y: local.y };
      if (node.size_locked) {
        positions[siteId].w = node.w;
        positions[siteId].h = node.h;
      }
    }

    try {
      const requestDepth = Math.max(
        depthLevel,
        depthRequiredForSitePlace(nestSite) + 1
      );
      const res = await api("/api/edit/reparent", {
        method: "POST",
        body: JSON.stringify({
          ids: rootSiteIds,
          parent_id: nestSite,
          positions,
          location_id: locationId,
          depth: requestDepth,
        }),
      });
      applyEditFlags(res);
      const moved = res.moved || [];
      let targetDepth = depthLevel;
      for (const siteId of moved) {
        targetDepth = Math.max(targetDepth, depthRequiredForSitePlace(siteId));
      }
      targetDepth = Math.max(targetDepth, depthRequiredForSitePlace(nestSite));
      if (targetDepth > depthLevel) {
        await ensureDepthForSitePlace(
          moved[0] || nestSite
        );
      } else if (res.graph) {
        graph = res.graph;
        depthLevel = graph.depth || depthLevel;
        maxDepth = graph.max_depth || maxDepth;
        render();
        updateDepthLabel();
      } else {
        await loadLocation({ fit: false });
      }
      expandOutlineAncestors(nestSite);
      await loadOutline();
      const relIds = moved
        .map((id) => siteToCanvasRelative(id))
        .filter((id) => id);
      if (relIds.length) {
        commitSelection(new Set(relIds), relIds[0]);
        highlightOutlineSelection();
      } else {
        clearSelectionState();
        setSelectedVisual();
      }
      await syncInspectorFromSelection();
      const n = moved.length || rootSiteIds.length;
      setStatus(
        t("status.moved", { n })
      );
      scheduleStatusRefresh();
      return true;
    } catch (err) {
      setStatus(String(err.message || err));
      try {
        await loadLocation({ fit: false });
      } catch {
        /* ignore reload errors */
      }
      return true;
    }
  }

  function clearPlacementGhost() {
    document.getElementById("placement-ghost")?.remove();
  }

  /** Sync opening marks on the placement ghost (same geometry as paintNode). */
  function syncPlacementGhostOpenings(g, ghostNode) {
    const want = openingCellsForNode(ghostNode);
    const wantSet = new Set(want);
    g.querySelectorAll("[data-opening]").forEach((elOp) => {
      const oid = elOp.getAttribute("data-opening");
      if (!oid || !wantSet.has(oid)) elOp.remove();
    });
    const placeMap = {};
    const ordered = [...want].sort((a, b) => {
      const ma = openingMarkLocal(ghostNode, a, placeMap);
      const mb = openingMarkLocal(ghostNode, b, placeMap);
      if (ma.near !== mb.near) return ma.near ? 1 : -1;
      return 0;
    });
    for (const oid of ordered) {
      const mark = openingMarkLocal(ghostNode, oid, placeMap);
      const nearFar = mark.near ? "opening-near" : "opening-far";
      const faceClass = `opening-face-${mark.face || "X"}`;
      let circle = g.querySelector(
        `circle[data-opening="${CSS.escape(String(oid))}"]`
      );
      if (!circle) {
        circle = el("circle", {
          class: `opening-mark ${nearFar} ${faceClass}`,
          "data-opening": oid,
          cx: mark.x,
          cy: mark.y,
          r: OPENING_MARK_R,
        });
        circle.appendChild(el("title", null, oid));
        g.appendChild(circle);
      } else {
        circle.setAttribute("class", `opening-mark ${nearFar} ${faceClass}`);
        circle.setAttribute("cx", String(mark.x));
        circle.setAttribute("cy", String(mark.y));
      }
      let text = g.querySelector(
        `text.opening-label[data-opening="${CSS.escape(String(oid))}"]`
      );
      if (!text) {
        text = el(
          "text",
          {
            class: `opening-label ${nearFar} ${faceClass}`,
            "data-opening": oid,
            x: mark.x,
            y: mark.y + 3,
            "text-anchor": "middle",
          },
          oid
        );
        g.appendChild(text);
      } else {
        text.setAttribute("class", `opening-label ${nearFar} ${faceClass}`);
        text.setAttribute("x", String(mark.x));
        text.setAttribute("y", String(mark.y + 3));
        text.textContent = oid;
      }
    }
  }

  function updatePlacementGhost(x, y, w, h, draft) {
    if (!worldEl || !draft) return;
    const isElem = draft.kind === "ElementType";
    const bw = Math.max(1, w);
    const bh = Math.max(1, h);
    const ghostNode = {
      w: bw,
      h: bh,
      openings: Array.isArray(draft.openings) ? draft.openings : [],
      opening_grid:
        draft.opening_grid && typeof draft.opening_grid === "object"
          ? draft.opening_grid
          : null,
    };
    const showOpenings = !isElem && nodeHasOpeningMarks(ghostNode);
    const fr = showOpenings
      ? frontRectLocal(ghostNode)
      : { x: 0, y: 0, w: bw, h: bh };
    const wantKey = `${isElem ? "e" : "p"}:${showOpenings ? "o" : "n"}`;
    let g = document.getElementById("placement-ghost");
    if (g && g.getAttribute("data-ghost-key") !== wantKey) {
      g.remove();
      g = null;
    }
    if (!g) {
      g = el("g", {
        id: "placement-ghost",
        class: "placement-ghost" + (isElem ? " element-node" : " node"),
        "data-ghost-key": wantKey,
      });
      if (showOpenings) appendNodeIsoBevel(g, bw, bh);
      const box = el("rect", {
        class:
          (isElem ? "element-box" : "node-box") +
          (showOpenings ? " iso-box" : isElem ? "" : " container") +
          " placement-ghost-box selected",
        x: String(fr.x),
        y: String(fr.y),
        width: String(fr.w),
        height: String(fr.h),
        rx: isElem ? "3" : showOpenings ? "0" : "6",
      });
      g.appendChild(box);
      if (showOpenings) {
        const wireLayer = g.querySelector("g.node-iso-wires");
        if (wireLayer) g.appendChild(wireLayer);
      }
      const label = String(
        draft.label || draft.name || draft.type_id || ""
      ).trim();
      if (label) {
        g.appendChild(
          el(
            "text",
            {
              class:
                (isElem ? "element-label" : "node-label") +
                " placement-ghost-label",
              x: String(isElem ? 4 : fr.x + 8),
              y: String(isElem ? 12 : fr.y + 18),
            },
            fitLabel(label, (isElem ? bw : fr.w) - (isElem ? 4 : 16))
          )
        );
      }
      worldEl.appendChild(g);
    }
    g.setAttribute("transform", `translate(${x},${y})`);
    const box = g.querySelector("rect.placement-ghost-box");
    if (box) {
      box.setAttribute("x", String(fr.x));
      box.setAttribute("y", String(fr.y));
      box.setAttribute("width", String(Math.max(1, fr.w)));
      box.setAttribute("height", String(Math.max(1, fr.h)));
    }
    if (showOpenings) {
      syncNodeIsoBevel(g, bw, bh);
      const wireLayer = g.querySelector("g.node-iso-wires");
      if (wireLayer) g.appendChild(wireLayer);
      syncPlacementGhostOpenings(g, ghostNode);
    }
    const text = g.querySelector("text.placement-ghost-label");
    if (text) {
      text.setAttribute("x", String(isElem ? 4 : fr.x + 8));
      text.setAttribute("y", String(isElem ? 12 : fr.y + 18));
      text.textContent = fitLabel(
        String(draft.label || draft.name || draft.type_id || "").trim(),
        (isElem ? bw : fr.w) - (isElem ? 4 : 16)
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
    if (d.kind === "ElementType") {
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
    // Nested inserts need enough depth to appear on the canvas (and in the
    // returned graph). Depth 1 only shows direct children of the canvas.
    const parentRelDepth =
      !parentCanvasId || parentCanvasId === "."
        ? 0
        : String(parentCanvasId).split("/").filter(Boolean).length;
    const needDepth = Math.max(depthLevel, parentRelDepth + 1);
    const body = {
      location_id: locationId,
      place_id: resolvePlaceApiId(parentCanvasId),
      depth: needDepth,
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
    const depthBeforeInsert = depthLevel;
    try {
      const res = await api("/api/insert/catalog-item", {
        method: "POST",
        body: JSON.stringify(body),
      });
      applyEditFlags(res);
      bumpMaxDepthFromGraph(res.graph);
      const newId = res.result?.id;
      const insertedSite = newId ? canvasToSiteId(newId) : null;
      if (insertedSite) expandOutlineAncestors(insertedSite);
      const targetDepth = insertedSite
        ? depthRequiredForSitePlace(insertedSite)
        : needDepth;
      maxDepth = Math.max(maxDepth, targetDepth, needDepth);
      if (targetDepth > depthBeforeInsert) {
        await setDepth(targetDepth);
      } else {
        graph = res.graph;
        depthLevel = Math.max(
          needDepth,
          graph.depth || depthLevel,
          targetDepth
        );
        maxDepth = Math.max(graph.max_depth || maxDepth, depthLevel);
        render();
        updateDepthLabel();
      }
      await loadOutline();
      if (newId) {
        await selectNode(newId);
        highlightOutlineSelection({ scrollTo: newId });
      }
      setStatus(t("status.catalogAdded"));
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

  /** Technical id from a localized label (ASCII; accents stripped). */
  function suggestIdFromLabel(label) {
    const raw = String(label || "").trim();
    if (!raw) return "NewItem";
    const ascii = raw.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
    let out = "";
    for (const ch of ascii) {
      if (/[A-Za-z0-9_-]/.test(ch)) out += ch;
      else out += "_";
    }
    out = out.replace(/_+/g, "_").replace(/^_|_$/g, "");
    return out || "NewItem";
  }

  function siblingIdsUnder(parentId, kind) {
    const used = new Set();
    const pid = parentId || ".";
    if (kind === "PlaceType") {
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
    if (kind === "PlaceType") {
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
    const localized = String(row.label || catalogTypeKey(row) || "").trim() || "NewItem";
    if (typeEl) typeEl.value = localized;
    if (descEl) descEl.value = row.description || "";
    let subtypeLabel = "—";
    if (subtypeId) {
      const hit = subtypeRows(catalogTypeKey(row)).find((x) => catalogSubtypeKey(x) === String(subtypeId));
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
      setStatus(t("status.kindAdded", { kind }));
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
    if (!locationId) {
      insertMsg(t("status.needCanvas"), true);
      return;
    }
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
      kind: (pendingCatalogInsert && pendingCatalogInsert.source_kind) || "ElementType",
      type_id: typeId,
      subtype: (pendingCatalogInsert && pendingCatalogInsert.subtype) || "",
      id: token,
      name: String(data.name || "").trim() || token,
      label: String(data.label || "").trim() || String(data.name || "").trim() || token,
      notes: data.notes || "",
    }).catch((err) => insertMsg(String(err.message || err), true));
    form.reset();
    resetCatalogInsertForm();
  }

  function renderPaletteSideList() {
    const qEl = document.getElementById("palette-search-side");
    const q = qEl ? qEl.value : "";
    const containers = paletteRows("PlaceType", q);
    const elements = paletteRows("ElementType", q);
    const elemsEnabled = elementsInsertEnabled();
    const needHint = t("palette.needsElectrical");
    const render = (hostId, rows, { asElements = false } = {}) => {
      const host = document.getElementById(hostId);
      if (!host) return;
      host.innerHTML = "";
      for (const row of rows) {
        const btn = document.createElement("button");
        btn.type = "button";
        const isElem = row.kind === "ElementType" || asElements;
        btn.className = "palette-item" + (isElem ? " element" : "");
        const fallback = isElem ? "box" : "folder-open";
        const icon = iconElement(
          row.icon || fallback,
          "palette-item-icon"
        );
        if (icon) btn.appendChild(icon);
        const label = document.createElement("span");
        label.className = "palette-item-label";
        label.textContent = row.label || catalogTypeKey(row);
        btn.appendChild(label);
        const idEl = document.createElement("span");
        idEl.className = "palette-item-id";
        idEl.textContent = catalogTypeKey(row);
        btn.appendChild(idEl);
        const baseTitle = [row.label || catalogTypeKey(row), catalogTypeKey(row)]
          .filter(Boolean)
          .join(" · ");
        if (isElem && !elemsEnabled) {
          btn.disabled = true;
          btn.title = needHint;
        } else {
          btn.title = baseTitle;
          btn.addEventListener("click", () => {
            const open = async () => {
              if (isElem) {
                try {
                  await ensureElectricalForElementInsert();
                } catch {
                  return;
                }
              }
              pendingCatalogInsert = {
                type_id: catalogTypeKey(row),
                subtype: "",
                source_kind: row.kind || "",
              };
              resetCatalogInsertForm();
              prefillCatalogInsertFromRow(row, "");
              openInsertModal("catalog-item");
            };
            open().catch((err) => setStatus(String(err.message || err)));
          });
        }
        host.appendChild(btn);
      }
    };
    render("palette-list-containers", containers);
    render("palette-list-elements", elements, { asElements: true });
    const elemGroup = document.getElementById("palette-group-elements");
    if (elemGroup) {
      elemGroup.classList.toggle("is-electrical-off", !elemsEnabled);
      elemGroup.title = elemsEnabled ? "" : needHint;
    }
    document
      .querySelectorAll("[data-palette-insert-action][data-needs-electrical]")
      .forEach((btn) => {
        btn.disabled = !elemsEnabled;
        btn.title = elemsEnabled ? "" : needHint;
      });
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
    if (kind === "element" && !elementsInsertEnabled()) {
      setStatus(t("palette.needsElectrical"));
      return;
    }
    if (kind === "element" && !showElectrical) {
      await setElectrical(true);
    }
    await loadPaletteCatalog();
    const sel = document.getElementById("insert-type-id");
    if (!sel) return;
    const typeClass = kind === "container" ? "PlaceType" : "ElementType";
    const rows = paletteRows(typeClass, "");
    sel.innerHTML = "";
    for (const row of rows) {
      const opt = document.createElement("option");
      opt.value = catalogTypeKey(row);
      opt.textContent = row.label || catalogTypeKey(row);
      sel.appendChild(opt);
    }
    const first = rows[0] && catalogTypeKey(rows[0]);
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
  document.querySelectorAll(".palette-group-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const group = btn.closest(".palette-group");
      if (!group) return;
      const collapsed = group.classList.toggle("collapsed");
      btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    });
  });
  document.querySelectorAll("[data-palette-insert-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.getAttribute("data-palette-insert-action");
      const run = async () => {
        if (btn.hasAttribute("data-needs-electrical")) {
          await ensureElectricalForElementInsert();
        }
        if (action === "conduit" || action === "conductor") {
          await beginWiringGesture(action);
        } else if (action === "cable") {
          await beginSheathFromSelection();
        }
      };
      run().catch((err) => setStatus(String(err.message || err)));
    });
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
    .then((st) => {
      applyWorkspaceStatus(st);
      if (
        isDesktopMode() &&
        st &&
        st.document &&
        !st.document.browser_origin &&
        st.document.yaml_path
      ) {
        return rememberDesktopRecent(st.document.yaml_path).then(() => st);
      }
      return st;
    })
    .then(() => loadLocations())
    .catch((err) => setStatus(String(err.message || err)));
