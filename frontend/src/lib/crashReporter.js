// Lightweight crash/error logging — no third-party SDK or new backend endpoint.
//
// - Desktop (Electron): forwarded to main.js, which writes to a rotating file
//   in userData/logs/main.log (see desktop/logger.js).
// - Web/PWA: kept as a bounded ring buffer in localStorage so a support agent
//   can ask the user to open DevTools → Application → Local Storage and copy
//   `gew_error_log`, or a future admin screen can read it back.
const LOG_KEY = "gew_error_log";
const MAX_ENTRIES = 50;

export function reportError(error, context = {}) {
  const entry = {
    t: new Date().toISOString(),
    message: error?.message || String(error),
    stack: error?.stack || null,
    ...context,
  };

  if (typeof window !== "undefined" && window.ormodex?.logError) {
    window.ormodex.logError(entry);
    return;
  }

  try {
    const existing = JSON.parse(localStorage.getItem(LOG_KEY) || "[]");
    existing.push(entry);
    while (existing.length > MAX_ENTRIES) existing.shift();
    localStorage.setItem(LOG_KEY, JSON.stringify(existing));
  } catch {
    // localStorage full/unavailable — nothing more we can do locally.
  }
}

export function getLocalErrorLog() {
  try {
    return JSON.parse(localStorage.getItem(LOG_KEY) || "[]");
  } catch {
    return [];
  }
}

export function clearLocalErrorLog() {
  localStorage.removeItem(LOG_KEY);
}

// Installed once from index.js — catches errors React's own boundary can't
// (event handlers outside render, timers, promise rejections).
export function installGlobalHandlers() {
  window.addEventListener("error", (e) => {
    reportError(e.error || e.message, { source: "window.onerror" });
  });
  window.addEventListener("unhandledrejection", (e) => {
    reportError(e.reason, { source: "unhandledrejection" });
  });
}

// App version, exposed for a Settings/About screen. Desktop reports the
// Electron package version via the IPC bridge; the web build has no
// installer version, so it reports the frontend package's own version env.
export async function getAppVersion() {
  if (typeof window !== "undefined" && window.ormodex?.getConfig) {
    const cfg = await window.ormodex.getConfig();
    return { version: cfg.version, platform: cfg.platform || "desktop" };
  }
  return { version: process.env.REACT_APP_VERSION || "web", platform: "web" };
}
