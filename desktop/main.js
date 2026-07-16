// Ormodex ERP — Electron main process.
//
// This is a THIN CLIENT: it ships the built React UI locally and calls your hosted
// backend over HTTPS. The backend/database is NOT bundled — set the server URL once
// and every device shares the same data.
//
// Backend URL resolution (first match wins):
//   1. GRAVITYONE_BACKEND_URL environment variable (power users / kiosks)
//   2. A value the user saved in-app (userData/config.json)
//   3. DEFAULT_BACKEND_URL below (baked default for your production server)

const { app, BrowserWindow, shell, dialog, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");
const buildMenu = require("./menu");

// ── Configuration ────────────────────────────────────────────────────
// Change this to your production API host before cutting a release, or override
// per-install via the GRAVITYONE_BACKEND_URL env var / in-app Settings.
//
// ⚠ PLACEHOLDER — the production backend is not deployed yet. Replace this with
// your real API host before cutting a public release. Until then, end-users can
// point the app at any server via File → ERP Server… (or the env var above).
const DEFAULT_BACKEND_URL = "https://api.ormodex.com";

const CONFIG_PATH = () => path.join(app.getPath("userData"), "config.json");

function readConfig() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG_PATH(), "utf8"));
  } catch {
    return {};
  }
}

function writeConfig(patch) {
  const next = { ...readConfig(), ...patch };
  fs.writeFileSync(CONFIG_PATH(), JSON.stringify(next, null, 2));
  return next;
}

function backendUrl() {
  const fromEnv = process.env.GRAVITYONE_BACKEND_URL;
  const fromCfg = readConfig().backendUrl;
  return (fromEnv || fromCfg || DEFAULT_BACKEND_URL).replace(/\/$/, "");
}

// ── Window ───────────────────────────────────────────────────────────
let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    backgroundColor: "#070912",
    show: false,
    title: "Ormodex ERP",
    icon: path.join(__dirname, "build-resources", iconForPlatform()),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  // The CRA build is copied into app/ at build time. The injected env-config.js
  // (loaded before the bundle) tells the React app which backend to call.
  mainWindow.loadFile(path.join(__dirname, "app", "index.html"));

  mainWindow.once("ready-to-show", () => mainWindow.show());

  // Open external links (docs, marketing site, mailto) in the user's browser,
  // never inside the app window.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) {
      shell.openExternal(url);
      return { action: "deny" };
    }
    return { action: "allow" };
  });

  // Block in-app navigation to arbitrary external origins (defense in depth).
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith("file://")) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  buildMenu({ onChangeServer: promptForServer, getBackendUrl: backendUrl });
}

function iconForPlatform() {
  if (process.platform === "win32") return "icon.ico";
  if (process.platform === "darwin") return "icon.icns";
  return "icon.png";
}

// ── In-app server configuration ──────────────────────────────────────
async function promptForServer() {
  const current = backendUrl();
  const { response } = await dialog.showMessageBox(mainWindow, {
    type: "question",
    title: "ERP Server",
    message: "Where is your Ormodex ERP server?",
    detail: `Current: ${current}\n\nEnter a new server URL to connect this device to a different backend. The app will reload.`,
    buttons: ["Keep current", "Change…"],
    defaultId: 0,
    cancelId: 0,
  });
  if (response !== 1) return;

  // Electron has no native text-input dialog; use a tiny prompt window.
  const input = await textPrompt(current);
  if (input && /^https?:\/\//.test(input)) {
    writeConfig({ backendUrl: input.replace(/\/$/, "") });
    if (mainWindow) mainWindow.reload();
  } else if (input) {
    dialog.showErrorBox("Invalid URL", "Server URL must start with http:// or https://");
  }
}

function textPrompt(initial) {
  return new Promise((resolve) => {
    const win = new BrowserWindow({
      width: 460,
      height: 200,
      parent: mainWindow,
      modal: true,
      resizable: false,
      minimizable: false,
      maximizable: false,
      backgroundColor: "#0b0e1a",
      title: "ERP Server URL",
      webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true },
    });
    const html = `data:text/html,${encodeURIComponent(`
      <body style="font-family:system-ui;background:#0b0e1a;color:#e2e8f0;margin:0;padding:20px">
        <label style="font-size:13px;display:block;margin-bottom:8px">Server URL</label>
        <input id="u" value="${initial}" style="width:100%;box-sizing:border-box;padding:10px;border-radius:8px;border:1px solid #334;background:#070912;color:#fff;font-size:14px"/>
        <div style="margin-top:16px;text-align:right">
          <button onclick="window.close()" style="padding:8px 14px;margin-right:8px;border-radius:8px;border:1px solid #334;background:transparent;color:#cbd5e1;cursor:pointer">Cancel</button>
          <button onclick="window.ormodex.submitServer(document.getElementById('u').value)" style="padding:8px 14px;border-radius:8px;border:0;background:#6366f1;color:#fff;cursor:pointer">Save</button>
        </div>
        <script>document.getElementById('u').focus();document.getElementById('u').select();
        document.getElementById('u').addEventListener('keydown',e=>{if(e.key==='Enter')window.ormodex.submitServer(e.target.value)});</script>
      </body>`)}`;
    ipcMain.once("server:submit", (_e, value) => {
      resolve(value);
      if (!win.isDestroyed()) win.close();
    });
    win.on("closed", () => resolve(null));
    win.loadURL(html);
  });
}

// Expose backend URL + app version to the renderer via preload bridge.
ipcMain.handle("config:get", () => ({
  backendUrl: backendUrl(),
  version: app.getVersion(),
}));

// ── App lifecycle ────────────────────────────────────────────────────
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(createWindow);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
