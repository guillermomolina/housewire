"use strict";

/**
 * Minimal Electron main process for HouseWire.
 *
 * Spawns ``python -m housewire serve`` (empty workspace), waits until the
 * HTTP port responds, then loads the UI. Native Open / Save As dialogs return
 * absolute paths so the renderer can call path-aware workspace APIs.
 */

const { app, BrowserWindow, dialog, ipcMain, Menu } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const net = require("net");
const path = require("path");

const PREFS_NAME = "desktop-prefs.json";
const DEFAULT_PORT = 8765;
const APP_ICON = path.join(__dirname, "icon.png");

/** @type {import('child_process').ChildProcess | null} */
let serverProc = null;
/** @type {BrowserWindow | null} */
let mainWindow = null;
let serverPort = DEFAULT_PORT;

function prefsPath() {
  return path.join(app.getPath("userData"), PREFS_NAME);
}

function loadPrefs() {
  try {
    const raw = fs.readFileSync(prefsPath(), "utf8");
    const data = JSON.parse(raw);
    return data && typeof data === "object" ? data : {};
  } catch {
    return {};
  }
}

function savePrefs(prefs) {
  try {
    fs.mkdirSync(path.dirname(prefsPath()), { recursive: true });
    fs.writeFileSync(prefsPath(), JSON.stringify(prefs, null, 2), "utf8");
  } catch {
    /* ignore */
  }
}

function rememberDirFromFile(filePath) {
  if (!filePath) return;
  const prefs = loadPrefs();
  prefs.lastOpenDir = path.dirname(filePath);
  savePrefs(prefs);
}

function defaultDialogPath(suggestedName) {
  const prefs = loadPrefs();
  const dir = prefs.lastOpenDir || app.getPath("documents");
  if (suggestedName) return path.join(dir, suggestedName);
  return dir;
}

function findPython() {
  const env = process.env.HOUSEWIRE_PYTHON;
  if (env) return env;
  // Prefer the repo venv when developing from a checkout.
  const repoRoot = path.resolve(__dirname, "..");
  for (const rel of [".venv/bin/python", ".venv/Scripts/python.exe"]) {
    const candidate = path.join(repoRoot, rel);
    if (fs.existsSync(candidate)) return candidate;
  }
  return process.platform === "win32" ? "python" : "python3";
}

function portFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen(port, "127.0.0.1");
  });
}

async function pickPort() {
  if (await portFree(DEFAULT_PORT)) return DEFAULT_PORT;
  for (let p = DEFAULT_PORT + 1; p < DEFAULT_PORT + 40; p += 1) {
    if (await portFree(p)) return p;
  }
  throw new Error("No free port near 8765 for housewire serve");
}

function waitForHttp(port, timeoutMs = 30000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tryOnce = () => {
      const req = http.get(
        { host: "127.0.0.1", port, path: "/api/about", timeout: 1000 },
        (res) => {
          res.resume();
          if (res.statusCode && res.statusCode < 500) {
            resolve();
            return;
          }
          retry();
        }
      );
      req.on("error", retry);
      req.on("timeout", () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        reject(new Error(`housewire serve did not become ready on :${port}`));
        return;
      }
      setTimeout(tryOnce, 200);
    };
    tryOnce();
  });
}

function startServer(port) {
  const python = findPython();
  const args = ["-m", "housewire", "serve", "--host", "127.0.0.1", "--port", String(port)];
  serverProc = spawn(python, args, {
    cwd: path.resolve(__dirname, ".."),
    env: { ...process.env },
    stdio: ["ignore", "pipe", "pipe"],
  });
  serverProc.stdout.on("data", (buf) => {
    process.stdout.write(`[serve] ${buf}`);
  });
  serverProc.stderr.on("data", (buf) => {
    process.stderr.write(`[serve] ${buf}`);
  });
  serverProc.on("exit", (code, signal) => {
    serverProc = null;
    if (mainWindow && !mainWindow.isDestroyed()) {
      dialog.showErrorBox(
        "HouseWire server stopped",
        `The embedded housewire serve process exited (code=${code}, signal=${signal}).`
      );
    }
  });
}

function stopServer() {
  if (!serverProc || serverProc.killed) return;
  const child = serverProc;
  serverProc = null;
  try {
    child.kill("SIGINT");
  } catch {
    /* ignore */
  }
  setTimeout(() => {
    if (!child.killed) {
      try {
        child.kill("SIGKILL");
      } catch {
        /* ignore */
      }
    }
  }, 2000);
}

function yamlFilters() {
  return [
    { name: "YAML", extensions: ["yaml", "yml"] },
    { name: "All Files", extensions: ["*"] },
  ];
}

function createWindow(port) {
  // Keep a single menu: the in-app HTML bar (Archivo/Editar/…). Hide Electron's
  // default File/Edit/View/Window chrome so it does not duplicate.
  Menu.setApplicationMenu(null);

  const winOpts = {
    width: 1280,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    title: "HouseWire",
    autoHideMenuBar: true,
  };
  if (fs.existsSync(APP_ICON)) {
    winOpts.icon = APP_ICON;
  }
  mainWindow = new BrowserWindow(winOpts);
  mainWindow.setMenuBarVisibility(false);
  mainWindow.loadURL(`http://127.0.0.1:${port}/`);
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

ipcMain.handle("desktop:open-yaml", async () => {
  const win = BrowserWindow.getFocusedWindow() || mainWindow;
  const result = await dialog.showOpenDialog(win, {
    title: "Open site YAML",
    defaultPath: defaultDialogPath(),
    properties: ["openFile"],
    filters: yamlFilters(),
  });
  if (result.canceled || !result.filePaths || !result.filePaths[0]) {
    return null;
  }
  const filePath = result.filePaths[0];
  rememberDirFromFile(filePath);
  return filePath;
});

ipcMain.handle("desktop:save-yaml-as", async (_event, suggestedName) => {
  const win = BrowserWindow.getFocusedWindow() || mainWindow;
  const result = await dialog.showSaveDialog(win, {
    title: "Save site YAML as",
    defaultPath: defaultDialogPath(suggestedName || "housewire.yaml"),
    filters: yamlFilters(),
  });
  if (result.canceled || !result.filePath) return null;
  let filePath = result.filePath;
  if (!/\.(ya?ml)$/i.test(filePath)) {
    filePath = `${filePath}.yaml`;
  }
  rememberDirFromFile(filePath);
  return filePath;
});

async function boot() {
  serverPort = await pickPort();
  startServer(serverPort);
  await waitForHttp(serverPort);
  createWindow(serverPort);
}

app.whenReady().then(() => {
  app.setName("HouseWire");
  if (process.platform === "linux" && fs.existsSync(APP_ICON)) {
    try {
      app.setIcon(APP_ICON);
      // Some Linux DEs also pick up the window icon from BrowserWindow.
    } catch {
      /* older Electron without setIcon */
    }
  }
  boot().catch((err) => {
    console.error(err);
    dialog.showErrorBox("HouseWire desktop failed to start", String(err && err.message ? err.message : err));
    stopServer();
    app.quit();
  });
});

app.on("window-all-closed", () => {
  stopServer();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  stopServer();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0 && serverPort) {
    createWindow(serverPort);
  }
});
