"use strict";

/**
 * Electron preload: expose a narrow desktop bridge to the HouseWire UI.
 * The renderer talks to the Python server for document state; this bridge
 * provides native Open / Save As dialogs, recent paths, and window actions.
 */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("housewireDesktop", {
  getMode: () => "desktop",
  openYaml: () => ipcRenderer.invoke("desktop:open-yaml"),
  saveYamlAs: (suggestedName) =>
    ipcRenderer.invoke("desktop:save-yaml-as", suggestedName || "housewire.yaml"),
  listRecent: () => ipcRenderer.invoke("desktop:recent-list"),
  rememberRecent: (filePath) =>
    ipcRenderer.invoke("desktop:recent-add", filePath),
  forgetRecent: (filePath) =>
    ipcRenderer.invoke("desktop:recent-remove", filePath),
  quit: () => ipcRenderer.invoke("desktop:quit"),
  toggleFullscreen: () => ipcRenderer.invoke("desktop:toggle-fullscreen"),
});
