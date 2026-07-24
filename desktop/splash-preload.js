// Minimal bridge for the splash screen only — relays the main process's
// online/offline probe result into the sandboxed splash renderer.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("splashBridge", {
  onStatus: (cb) => ipcRenderer.on("splash:status", (_e, status) => cb(status)),
});
