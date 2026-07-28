// Secure bridge between the sandboxed renderer (React app) and the main process.
// Only a minimal, explicit surface is exposed — no Node access in the renderer.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("ormodex", {
  // Renderer calls this on boot to learn which backend to talk to. The injected
  // env-config.js uses it to set window.__GRAVITYONE_BACKEND_URL__ before the
  // React bundle reads process.env.REACT_APP_BACKEND_URL.
  getConfig: () => ipcRenderer.invoke("config:get"),
  // Used by the "ERP Server URL" prompt window.
  submitServer: (value) => ipcRenderer.send("server:submit", value),

  // Native OS notification (the renderer falls back to the Web Notification
  // API when this bridge isn't present, e.g. the plain web/PWA build).
  notify: (title, body, opts = {}) => ipcRenderer.invoke("notify:show", { title, body, ...opts }),

  // Native print dialog for the current view, or an in-memory PDF export
  // (base64) the renderer can hand to its existing download flow.
  printCurrent: (options) => ipcRenderer.invoke("print:current", options),
  printToPdf: (options) => ipcRenderer.invoke("print:toPdf", options),

  // Native save-file / open-file dialogs so downloads/uploads feel like a
  // real desktop app instead of a browser download tray.
  saveFile: (suggestedName, base64) => ipcRenderer.invoke("file:save", { suggestedName, base64 }),
  openFile: (filters) => ipcRenderer.invoke("file:open", { filters }),

  // Forward a renderer-side error to the main-process log file (crash
  // reporting without a third-party SDK or network dependency).
  logError: (payload) => ipcRenderer.send("log:error", payload),

  // Re-probe backend reachability from inside the loaded app (e.g. a "Retry"
  // button on an in-page offline banner).
  checkBackend: () => ipcRenderer.invoke("net:checkBackend"),

  // Whether the bundled local Postgres/backend (offline mode) is currently
  // running, and its URL — groundwork for a future in-app mode indicator.
  getLocalStatus: () => ipcRenderer.invoke("local:status"),
});
