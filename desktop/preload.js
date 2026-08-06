"use strict";

/**
 * Electron preload: expose a narrow desktop bridge to the HouseWire UI.
 * The renderer talks to the Python server for document state; this bridge
 * only provides native Open / Save As dialogs that return absolute paths.
 */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("housewireDesktop", {
  getMode: () => "desktop",
  openYaml: () => ipcRenderer.invoke("desktop:open-yaml"),
  saveYamlAs: (suggestedName) =>
    ipcRenderer.invoke("desktop:save-yaml-as", suggestedName || "housewire.yaml"),
});
