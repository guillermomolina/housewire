  /* === 00-files.js: Web vs Electron file backends ===
   * Fragment of the UI IIFE (bundled into ../app.js).
   * Edit this file, then run: python scripts/bundle_ui_app.py
   *
   * Desktop (Electron): window.housewireDesktop → native dialogs + server paths.
   * Web: File System Access / <input type="file"> + open-content temps.
   */

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

  function isDesktopMode() {
    const bridge = window.housewireDesktop;
    return Boolean(
      bridge &&
        typeof bridge.openYaml === "function" &&
        typeof bridge.saveYamlAs === "function"
    );
  }

  function desktopBridge() {
    return window.housewireDesktop || null;
  }

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

  async function pickOpenYamlFileWeb() {
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

  async function pickSaveYamlFileWeb(suggestedName, content) {
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

  /**
   * Whether Save can write without a Save As dialog.
   * Desktop / serve-opened sites: server has a real path (!browser_origin).
   * Web picker docs: need a FileSystemFileHandle for write-back.
   */
  function documentHasSaveTarget() {
    if (!hasDocument || !activeDocId) return false;
    if (!activeDocBrowserOrigin) return true;
    if (isDesktopMode()) return false;
    return Boolean(fileHandles[activeDocId]);
  }
