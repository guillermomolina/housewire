/**
 * HouseWire UI locale (en / es).
 * Prefer localStorage; else navigator.language (es* → es).
 */
(function (global) {
  "use strict";

  const LOCALE_KEY = "housewire-locale";
  const SUPPORTED = ["en", "es"];

  const MESSAGES = {
    en: {
      "app.aria": "Application",
      "menu.file": "File",
      "menu.file.open": "Open…",
      "menu.file.save": "Save",
      "menu.file.saveAs": "Save as…",
      "menu.file.close": "Close",
      "menu.edit": "Edit",
      "menu.edit.undo": "Undo",
      "menu.edit.redo": "Redo",
      "menu.edit.reset": "Reset",
      "menu.edit.cut": "Cut",
      "menu.edit.copy": "Copy",
      "menu.edit.paste": "Paste",
      "menu.edit.delete": "Delete",
      "menu.edit.autoLayout": "Auto-layout",
      "menu.edit.insert": "Insert",
      "menu.insert.socket": "Socket…",
      "menu.insert.lamp": "Lamp…",
      "menu.insert.feed": "Feed…",
      "menu.insert.element": "Element…",
      "menu.insert.container": "Container…",
      "menu.insert.palette": "Palette…",
      "palette.search": "Search",
      "palette.containers": "Containers",
      "palette.elements": "Elements",
      "insert.type": "Type",
      "insert.subtype": "Subtype",
      "insert.description": "Description",
      "insert.next": "Next",
      "insert.add": "Add",
      "insert.selectType": "Select one type.",
      "insert.idRequired": "ID is required.",
      "insert.placeNotFound": "Select a valid container before adding.",
      "insert.placeHint": "Move to preview (cursor = top-left). Click to place. Containers: drag to size.",
      "insert.placing": "Placing item…",
      "status.catalogAddedUnsaved": "catalog item added · unsaved",
      "menu.insert.cable": "Cable…",
      "menu.insert.conduit": "Conduit…",
      "menu.insert.comingSoon": "Coming soon",
      "menu.view": "View",
      "menu.view.electrical": "Electrical",
      "menu.view.dark": "Dark mode",
      "menu.view.light": "Light mode",
      "menu.view.zoomIn": "Zoom in",
      "menu.view.zoomOut": "Zoom out",
      "menu.view.fit": "Fit",
      "menu.view.panHint": "Pan: Space+drag, middle-click, or drag empty canvas",
      "menu.view.depthIn": "Depth in",
      "menu.view.depthOut": "Depth out",
      "menu.view.language": "Language",
      "menu.view.lang.en": "English",
      "menu.view.lang.es": "Spanish",
      "menu.help": "Help",
      "menu.help.about": "About HouseWire",
      "panel.outline": "Outline",
      "panel.outline.collapse": "Collapse outline",
      "panel.outline.show": "Show outline",
      "panel.nav": "Sidebar",
      "panel.palette": "Palette",
      "panel.palette.collapse": "Collapse palette",
      "panel.palette.expand": "Expand palette",
      "panel.nav.split": "Resize outline and palette",
      "panel.properties": "Properties",
      "panel.properties.collapse": "Collapse properties",
      "panel.properties.show": "Show properties",
      "panel.empty": "Select a box or element",
      "panel.props.heading": "Properties",
      "panel.props.elements": "Elements",
      "panel.props.conduits": "Conduits",
      "panel.props.cables": "Cables",
      "tabs.openFiles": "Open files",
      "aria.siteOutline": "Site outline",
      "tool.depthIn": "Depth in (Alt+wheel)",
      "tool.depthOut": "Depth out",
      "status.zoom": "Canvas zoom",
      "modal.confirm": "Confirm",
      "modal.path": "Path",
      "modal.cancel": "Cancel",
      "modal.close": "Close",
      "about.license": "License",
      "about.copyright": "Copyright",
      "about.modalTitle": "About",
      "about.author": "Author",
      "about.repository": "Repository",
      "about.version": "Version {v}",
      "props.siteRoot": "Site root",
      "props.key.id": "ID",
      "props.key.parent": "Parent",
      "props.key.name": "Name",
      "props.key.label": "Label",
      "props.key.type": "Type",
      "props.key.subtype": "Subtype",
      "props.key.install": "Install",
      "props.key.mount": "Mount",
      "props.key.openings": "Openings",
      "props.key.connects": "Connects",
      "props.key.notes": "Notes",
      "props.key.terminals": "Terminals",
      "props.key.flipVertical": "Flip vertical",
      "props.key.flipHorizontal": "Flip horizontal",
      "props.key.orientationNorthSouth": "Orientation v.",
      "props.key.orientationWestEast": "Orientation h.",
      "props.install.surface": "Surface",
      "props.install.in_wall": "In wall",
      "props.mount.wall": "Wall",
      "props.mount.ceiling": "Ceiling",
      "props.mount.floor": "Floor",
      "props.orientation.north_to_south": "North to South",
      "props.orientation.south_to_north": "South to North",
      "props.orientation.west_to_east": "West to East",
      "props.orientation.east_to_west": "East to West",
      "status.copied": "copied {n} item(s) · selection kept",
      "status.cut": "cut {n} item(s) · paste returns to source · unsaved",
      "status.pasted": "pasted {n} item(s) · unsaved",
      "status.pasteNeedParent": "Select one place (or elements under the same parent) to paste into",
      "status.cannotCopyRoot": "Cannot copy the site root",
      "status.cannotCutRoot": "Cannot cut the site root",
      "status.cannotDeleteRoot": "Cannot delete the site root",
      "status.moved": "Moved {n}",
      "status.movedUnsaved": "Moved {n} · unsaved",
      "status.resizedPlace": "Resized place",
      "status.resizedPlaceUnsaved": "Resized place · unsaved",
      "status.resizedElement": "Resized element",
      "status.resizedElementUnsaved": "Resized element · unsaved",
      "status.saved": "saved {n} file(s)",
      "status.dirty": "{n} dirty file(s)",
      "status.layoutPending": "layout pending",
      "status.savedOk": "saved",
      "status.unsaved": "unsaved",
    },
    es: {
      "app.aria": "Aplicación",
      "menu.file": "Archivo",
      "menu.file.open": "Abrir…",
      "menu.file.save": "Guardar",
      "menu.file.saveAs": "Guardar como…",
      "menu.file.close": "Cerrar",
      "menu.edit": "Editar",
      "menu.edit.undo": "Deshacer",
      "menu.edit.redo": "Rehacer",
      "menu.edit.reset": "Restablecer",
      "menu.edit.cut": "Cortar",
      "menu.edit.copy": "Copiar",
      "menu.edit.paste": "Pegar",
      "menu.edit.delete": "Eliminar",
      "menu.edit.autoLayout": "Auto-disposición",
      "menu.edit.insert": "Insertar",
      "menu.insert.socket": "Enchufe…",
      "menu.insert.lamp": "Lámpara…",
      "menu.insert.feed": "Alimentación…",
      "menu.insert.element": "Elemento…",
      "menu.insert.container": "Contenedor…",
      "menu.insert.palette": "Paleta…",
      "palette.search": "Buscar",
      "palette.containers": "Contenedores",
      "palette.elements": "Elementos",
      "insert.type": "Tipo",
      "insert.subtype": "Subtipo",
      "insert.description": "Descripción",
      "insert.next": "Siguiente",
      "insert.add": "Añadir",
      "insert.selectType": "Selecciona un tipo.",
      "insert.idRequired": "El ID es obligatorio.",
      "insert.placeNotFound": "Selecciona un contenedor válido antes de añadir.",
      "insert.placeHint": "Mueve para previsualizar (cursor = esquina superior izquierda). Clic para colocar. Contenedores: arrastra para dimensionar.",
      "insert.placing": "Colocando elemento…",
      "status.catalogAddedUnsaved": "elemento de catálogo añadido · sin guardar",
      "menu.insert.cable": "Cable…",
      "menu.insert.conduit": "Tubo…",
      "menu.insert.comingSoon": "Próximamente",
      "menu.view": "Ver",
      "menu.view.electrical": "Eléctrico",
      "menu.view.dark": "Modo oscuro",
      "menu.view.light": "Modo claro",
      "menu.view.zoomIn": "Acercar",
      "menu.view.zoomOut": "Alejar",
      "menu.view.fit": "Ajustar",
      "menu.view.panHint": "Pan: Espacio+arrastrar, clic medio o arrastrar el lienzo vacío",
      "menu.view.depthIn": "Más profundidad",
      "menu.view.depthOut": "Menos profundidad",
      "menu.view.language": "Idioma",
      "menu.view.lang.en": "Inglés",
      "menu.view.lang.es": "Español",
      "menu.help": "Ayuda",
      "menu.help.about": "Acerca de HouseWire",
      "panel.outline": "Esquema",
      "panel.outline.collapse": "Ocultar esquema",
      "panel.outline.show": "Mostrar esquema",
      "panel.nav": "Barra lateral",
      "panel.palette": "Paleta",
      "panel.palette.collapse": "Ocultar paleta",
      "panel.palette.expand": "Mostrar paleta",
      "panel.nav.split": "Redimensionar esquema y paleta",
      "panel.properties": "Propiedades",
      "panel.properties.collapse": "Ocultar propiedades",
      "panel.properties.show": "Mostrar propiedades",
      "panel.empty": "Selecciona una caja o elemento",
      "panel.props.heading": "Propiedades",
      "panel.props.elements": "Elementos",
      "panel.props.conduits": "Tubos",
      "panel.props.cables": "Cables",
      "tabs.openFiles": "Archivos abiertos",
      "aria.siteOutline": "Esquema del sitio",
      "tool.depthIn": "Más profundidad (Alt+rueda)",
      "tool.depthOut": "Menos profundidad",
      "status.zoom": "Zoom del lienzo",
      "modal.confirm": "Confirmar",
      "modal.path": "Ruta",
      "modal.cancel": "Cancelar",
      "modal.close": "Cerrar",
      "about.license": "Licencia",
      "about.copyright": "Copyright",
      "about.modalTitle": "Acerca de",
      "about.author": "Autor",
      "about.repository": "Repositorio",
      "about.version": "Versión {v}",
      "props.siteRoot": "Raíz del sitio",
      "props.key.id": "ID",
      "props.key.parent": "Padre",
      "props.key.name": "Nombre",
      "props.key.label": "Etiqueta",
      "props.key.type": "Tipo",
      "props.key.subtype": "Subtipo",
      "props.key.install": "Instalación",
      "props.key.mount": "Montaje",
      "props.key.openings": "Aberturas",
      "props.key.connects": "Conecta",
      "props.key.notes": "Notas",
      "props.key.terminals": "Bornes",
      "props.key.flipVertical": "Voltear vertical",
      "props.key.flipHorizontal": "Voltear horizontal",
      "props.key.orientationNorthSouth": "Orientación v.",
      "props.key.orientationWestEast": "Orientación h.",
      "props.install.surface": "Superficie",
      "props.install.in_wall": "Dentro de la pared",
      "props.mount.wall": "Pared",
      "props.mount.ceiling": "Techo",
      "props.mount.floor": "Suelo",
      "props.orientation.north_to_south": "Norte a Sur",
      "props.orientation.south_to_north": "Sur a Norte",
      "props.orientation.west_to_east": "Oeste a Este",
      "props.orientation.east_to_west": "Este a Oeste",
      "status.copied": "copiados {n} elemento(s) · selección conservada",
      "status.cut": "cortados {n} elemento(s) · pegar vuelve al origen · sin guardar",
      "status.pasted": "pegados {n} elemento(s) · sin guardar",
      "status.pasteNeedParent": "Selecciona un lugar (o elementos bajo el mismo padre) donde pegar",
      "status.cannotCopyRoot": "No se puede copiar la raíz del sitio",
      "status.cannotCutRoot": "No se puede cortar la raíz del sitio",
      "status.cannotDeleteRoot": "No se puede eliminar la raíz del sitio",
      "status.moved": "Movidos {n}",
      "status.movedUnsaved": "Movidos {n} · sin guardar",
      "status.resizedPlace": "Lugar redimensionado",
      "status.resizedPlaceUnsaved": "Lugar redimensionado · sin guardar",
      "status.resizedElement": "Elemento redimensionado",
      "status.resizedElementUnsaved": "Elemento redimensionado · sin guardar",
      "status.saved": "guardados {n} archivo(s)",
      "status.dirty": "{n} archivo(s) sin guardar",
      "status.layoutPending": "disposición pendiente",
      "status.savedOk": "guardado",
      "status.unsaved": "sin guardar",
    },
  };

  function normalizeLocale(raw) {
    const s = String(raw || "")
      .trim()
      .toLowerCase()
      .replace(/_/g, "-");
    if (!s) return "en";
    const primary = s.split("-", 1)[0];
    if (SUPPORTED.includes(primary)) return primary;
    if (s.startsWith("es")) return "es";
    return "en";
  }

  function detectBrowserLocale() {
    try {
      const list =
        (typeof navigator !== "undefined" &&
          (navigator.languages || [navigator.language])) ||
        [];
      for (const tag of list) {
        const loc = normalizeLocale(tag);
        if (SUPPORTED.includes(loc)) return loc;
      }
    } catch (_) {
      /* ignore */
    }
    return "en";
  }

  function loadStoredLocale() {
    try {
      const raw = localStorage.getItem(LOCALE_KEY);
      if (raw) return normalizeLocale(raw);
    } catch (_) {
      /* ignore */
    }
    return null;
  }

  let current = loadStoredLocale() || detectBrowserLocale();

  function t(key, vars) {
    const table = MESSAGES[current] || MESSAGES.en;
    let text = table[key] || MESSAGES.en[key] || key;
    if (vars && typeof vars === "object") {
      for (const [k, v] of Object.entries(vars)) {
        text = text.split(`{${k}}`).join(String(v));
      }
    }
    return text;
  }

  function applyDomTranslations(root) {
    const scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (!key) return;
      el.textContent = t(key);
    });
    scope.querySelectorAll("[data-i18n-title]").forEach((el) => {
      const key = el.getAttribute("data-i18n-title");
      if (!key) return;
      el.setAttribute("title", t(key));
    });
    scope.querySelectorAll("[data-i18n-aria]").forEach((el) => {
      const key = el.getAttribute("data-i18n-aria");
      if (!key) return;
      el.setAttribute("aria-label", t(key));
    });
    document.documentElement.setAttribute("lang", current);
  }

  function setLocale(next, opts) {
    const loc = normalizeLocale(next);
    current = loc;
    try {
      localStorage.setItem(LOCALE_KEY, loc);
    } catch (_) {
      /* ignore */
    }
    applyDomTranslations();
    if (opts && typeof opts.onChange === "function") opts.onChange(loc);
    return loc;
  }

  function getLocale() {
    return current;
  }

  global.HouseWireI18n = {
    LOCALE_KEY,
    SUPPORTED,
    t,
    getLocale,
    setLocale,
    normalizeLocale,
    applyDomTranslations,
    detectBrowserLocale,
  };
})(typeof window !== "undefined" ? window : globalThis);
