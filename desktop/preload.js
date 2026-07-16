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
});
