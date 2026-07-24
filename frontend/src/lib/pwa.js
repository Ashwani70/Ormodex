// PWA bootstrap: service worker registration, install-prompt capture, and a
// thin background-sync registration helper. No new dependency — plain SW API.

let deferredInstallPrompt = null;
const installListeners = new Set();

export function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  // Desktop (Electron) build runs from file:// with no HTTP origin for a SW
  // to control, and doesn't need one — the native shell already gives it an
  // offline-capable local UI. Skip registration there.
  if (window.location.protocol === "file:") return;

  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch((err) => {
      console.error("Service worker registration failed:", err);
    });
  });
}

// Captures the browser's native "Add to Home Screen" / install prompt so the
// app can show its own "Install Ormodex ERP" button instead of relying on the
// browser's address-bar icon alone (Chrome/Edge desktop, Android Chrome).
export function listenForInstallPrompt() {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
    installListeners.forEach((cb) => cb(true));
  });
  window.addEventListener("appinstalled", () => {
    deferredInstallPrompt = null;
    installListeners.forEach((cb) => cb(false));
  });
}

export function canInstall() {
  return !!deferredInstallPrompt;
}

export function onInstallAvailabilityChange(cb) {
  installListeners.add(cb);
  return () => installListeners.delete(cb);
}

export async function promptInstall() {
  if (!deferredInstallPrompt) return { outcome: "unavailable" };
  deferredInstallPrompt.prompt();
  const choice = await deferredInstallPrompt.userChoice;
  deferredInstallPrompt = null;
  return choice; // { outcome: 'accepted' | 'dismissed' }
}

// Ask the service worker to retry a sync next time connectivity returns, even
// if the app/tab is fully closed (Chromium-based browsers only — Safari/
// Firefox silently no-op since they don't implement Background Sync).
export async function registerBackgroundSync(tag = "gew-sync") {
  if (!("serviceWorker" in navigator)) return false;
  try {
    const reg = await navigator.serviceWorker.ready;
    if (!("sync" in reg)) return false;
    await reg.sync.register(tag);
    return true;
  } catch {
    return false;
  }
}

// Fires cb whenever the service worker broadcasts a background-sync wakeup —
// e.g. POS can use this to trigger syncQueue() even if the reconnect happened
// while the window was in the background.
export function onBackgroundSyncMessage(cb) {
  if (!("serviceWorker" in navigator)) return () => {};
  const handler = (event) => {
    if (event.data?.type === "GEW_BACKGROUND_SYNC") cb();
  };
  navigator.serviceWorker.addEventListener("message", handler);
  return () => navigator.serviceWorker.removeEventListener("message", handler);
}
