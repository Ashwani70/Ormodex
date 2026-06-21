// Headless smoke test: boots the real Electron main process, loads the bundled
// app/ under file://, and asserts the renderer initialised with the runtime
// backend URL from the preload bridge. Exits non-zero on failure.
//
//   GRAVITYONE_BACKEND_URL=https://smoke.example npx electron scripts/smoke-test.js

const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");

const EXPECTED = process.env.GRAVITYONE_BACKEND_URL || "https://api.gravityone.com";

app.whenReady().then(async () => {
  // Mirror the production config IPC so the injected bootstrap can resolve.
  ipcMain.handle("config:get", () => ({ backendUrl: EXPECTED, version: app.getVersion() }));

  const win = new BrowserWindow({
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  let failed = false;
  win.webContents.on("console-message", (_e, _lvl, msg) => console.log("[renderer]", msg));

  await win.loadFile(path.join(__dirname, "..", "app", "index.html"));

  // Give the deferred bundle + bootstrap a moment, then assert.
  await new Promise((r) => setTimeout(r, 4000));

  const result = await win.webContents.executeJavaScript(`(() => ({
    backend: window.__GRAVITYONE_BACKEND_URL__ || null,
    hasRoot: !!document.getElementById('root'),
    rootHasContent: (document.getElementById('root')||{}).childElementCount > 0,
    title: document.title,
  }))()`);

  console.log("Smoke result:", JSON.stringify(result));

  if (result.backend !== EXPECTED) {
    console.error(`✗ backend URL mismatch: got ${result.backend}, expected ${EXPECTED}`);
    failed = true;
  }
  if (!result.hasRoot) {
    console.error("✗ React #root element missing — app did not load");
    failed = true;
  }

  if (!failed) console.log("✓ Smoke test passed: app loads under file:// and backend URL is wired");
  app.exit(failed ? 1 : 0);
});
