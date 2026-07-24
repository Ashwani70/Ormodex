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

const { app, BrowserWindow, shell, dialog, ipcMain, Notification } = require("electron");
const path = require("path");
const fs = require("fs");
const https = require("https");
const http = require("http");
const buildMenu = require("./menu");
const log = require("./logger");
const { setupAutoUpdate, checkForUpdatesNow } = require("./updater");

const isDev = !app.isPackaged;

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

// Reachability probe used by the offline splash screen — a plain HTTPS/HTTP
// request rather than pulling a fetch polyfill into the main process.
function pingBackend(url, timeoutMs = 6000) {
  return new Promise((resolve) => {
    let target;
    try {
      target = new URL(`${url}/api/health`);
    } catch {
      resolve(false);
      return;
    }
    const lib = target.protocol === "http:" ? http : https;
    const req = lib.request(
      { hostname: target.hostname, port: target.port, path: target.pathname, method: "GET", timeout: timeoutMs },
      (res) => {
        resolve(res.statusCode < 500);
        res.resume();
      }
    );
    req.on("timeout", () => { req.destroy(); resolve(false); });
    req.on("error", () => resolve(false));
    req.end();
  });
}

// ── Window ───────────────────────────────────────────────────────────
let mainWindow = null;
let splashWindow = null;

function iconForPlatform() {
  if (process.platform === "win32") return "icon.ico";
  if (process.platform === "darwin") return "icon.icns";
  return "icon.png";
}

function createSplash() {
  splashWindow = new BrowserWindow({
    width: 420,
    height: 320,
    frame: false,
    resizable: false,
    movable: false,
    backgroundColor: "#070912",
    show: true,
    icon: path.join(__dirname, "build-resources", iconForPlatform()),
    webPreferences: {
      preload: path.join(__dirname, "splash-preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  splashWindow.loadFile(path.join(__dirname, "splash.html"));
  return splashWindow;
}

function createMainWindow() {
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
      // Native devtools are a real risk on a production business app (token/data
      // inspection, arbitrary IPC probing). Only ever enabled in dev builds.
      devTools: isDev,
    },
  });

  // The CRA build is copied into app/ at build time. The injected env-config.js
  // (loaded before the bundle) tells the React app which backend to call.
  mainWindow.loadFile(path.join(__dirname, "app", "index.html"));

  mainWindow.once("ready-to-show", () => {
    // Launch maximized (professional "fills the screen" feel) rather than a
    // forced OS-level kiosk fullscreen, which would hide window controls.
    mainWindow.maximize();
    mainWindow.show();
    if (splashWindow && !splashWindow.isDestroyed()) splashWindow.close();
  });

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

  // Belt-and-suspenders devtools lock: also block the shortcuts, in case a
  // packaging misconfiguration ever left devTools:true in a release build.
  mainWindow.webContents.on("before-input-event", (event, input) => {
    if (isDev) return;
    const key = (input.key || "").toUpperCase();
    const blocked =
      key === "F12" ||
      (input.control && input.shift && (key === "I" || key === "J" || key === "C")) ||
      (input.meta && input.alt && key === "I");
    if (blocked) event.preventDefault();
  });

  mainWindow.webContents.on("render-process-gone", (_e, details) => {
    log.error("Renderer process crashed", details);
    dialog.showErrorBox(
      "Ormodex ERP crashed",
      `The application view stopped responding (${details.reason}). It will restart.\n\nA diagnostic log has been saved.`
    );
    createMainWindow();
  });

  mainWindow.on("unresponsive", () => log.warn("Renderer became unresponsive"));

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  buildMenu({
    onChangeServer: promptForServer,
    getBackendUrl: backendUrl,
    onCheckForUpdates: () => checkForUpdatesNow(log),
  });

  setupAutoUpdate(mainWindow, log);
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
  platform: process.platform,
}));

// ── Native notifications (renderer asks main to show an OS-level toast) ──
ipcMain.handle("notify:show", (_e, { title, body, silent } = {}) => {
  if (!Notification.isSupported()) return false;
  new Notification({
    title: title || "Ormodex ERP",
    body: body || "",
    silent: !!silent,
    icon: path.join(__dirname, "build-resources", "icon.png"),
  }).show();
  return true;
});

// ── Native print (current view, or an in-memory PDF export) ──
ipcMain.handle("print:current", (_e, options = {}) =>
  new Promise((resolve) => {
    if (!mainWindow) return resolve(false);
    mainWindow.webContents.print({ silent: false, printBackground: true, ...options }, (ok) => resolve(ok));
  })
);

ipcMain.handle("print:toPdf", async (_e, options = {}) => {
  if (!mainWindow) return null;
  const data = await mainWindow.webContents.printToPDF({ printBackground: true, ...options });
  return data.toString("base64");
});

// ── File save (download) — renderer hands over bytes, main shows a native Save dialog ──
ipcMain.handle("file:save", async (_e, { suggestedName, base64 } = {}) => {
  const { canceled, filePath } = await dialog.showSaveDialog(mainWindow, {
    defaultPath: suggestedName || "download",
  });
  if (canceled || !filePath) return { saved: false };
  fs.writeFileSync(filePath, Buffer.from(base64, "base64"));
  shell.showItemInFolder(filePath);
  return { saved: true, filePath };
});

// ── File open (upload) — native file picker, returns path + base64 content ──
ipcMain.handle("file:open", async (_e, options = {}) => {
  const { canceled, filePaths } = await dialog.showOpenDialog(mainWindow, {
    properties: ["openFile"],
    filters: options.filters,
  });
  if (canceled || !filePaths.length) return null;
  const filePath = filePaths[0];
  const buf = fs.readFileSync(filePath);
  return { name: path.basename(filePath), path: filePath, base64: buf.toString("base64") };
});

// Renderer console/runtime errors forwarded to the main-process log file.
ipcMain.on("log:error", (_e, payload) => log.error("Renderer error", payload));

// Splash-time connectivity probe, callable again from inside the app (e.g. a
// "Retry connection" button on an in-page offline banner).
ipcMain.handle("net:checkBackend", async () => pingBackend(backendUrl()));

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

  app.whenReady().then(async () => {
    log.info(`Ormodex ERP starting — v${app.getVersion()} (${process.platform})`);
    createSplash();
    const online = await pingBackend(backendUrl());
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.webContents.send("splash:status", online ? "online" : "offline");
    }
    // Give the splash a brief, deliberate beat so the online/offline state is
    // readable instead of flickering past, then proceed regardless — the app
    // itself also has an in-page offline banner once loaded.
    setTimeout(createMainWindow, online ? 400 : 1400);
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
  });
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

process.on("uncaughtException", (err) => log.error("uncaughtException", { message: err.message, stack: err.stack }));
process.on("unhandledRejection", (err) => log.error("unhandledRejection", { message: String(err) }));
