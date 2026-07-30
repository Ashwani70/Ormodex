// Ormodex ERP — PWA service worker.
//
// Strategy:
//   • App shell (HTML/JS/CSS/icons) — cache-first with network fallback, so the
//     installed app opens instantly and still works with no connection.
//   • API calls (/api/*) — network-first with a short cache fallback, so GET
//     requests made while briefly offline can still render *something* (stale
//     dashboard/list data) instead of a blank error screen. Writes (POST/PUT/
//     PATCH/DELETE) are never cached or replayed here — the app's own pages
//     (e.g. POS) already own their offline-write queues; this worker doesn't
//     duplicate that business logic.
//   • Background Sync — a generic 'gew-sync' tag any page can request via
//     registerBackgroundSync() in src/lib/pwa.js; on reconnect (even if the
//     tab is closed, Chromium-based browsers only) this posts a message any
//     open client can react to, and pages that were already tracking their own
//     queue (POS) pick it up from there.

const CACHE_VERSION = "v2";
const SHELL_CACHE = `ormodex-shell-${CACHE_VERSION}`;
const API_CACHE = `ormodex-api-${CACHE_VERSION}`;

const SHELL_ASSETS = [
  "/",
  "/index.html",
  "/manifest.json",
  "/favicon.ico",
  "/favicon-16x16.png",
  "/favicon-32x32.png",
  "/android-chrome-192x192.png",
  "/android-chrome-512x512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== SHELL_CACHE && k !== API_CACHE)
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

function isApiRequest(url) {
  return url.pathname.startsWith("/api/");
}

function isNavigationOrShell(request, url) {
  return request.mode === "navigate" || SHELL_ASSETS.includes(url.pathname);
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return; // never intercept writes
  const url = new URL(request.url);
  if (url.origin !== self.location.origin && !isApiRequest(url)) return; // cross-origin (fonts CDN etc.) — let the browser handle it

  if (isApiRequest(url)) {
    // Network-first: always prefer live data; fall back to the last-seen
    // response only when the network is actually unreachable.
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(API_CACHE).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || Response.error()))
    );
    return;
  }

  if (isNavigationOrShell(request, url)) {
    // Network-first for the HTML shell. CRA fingerprints every JS/CSS chunk
    // with a content hash per build, so a cache-first index.html can go
    // stale after a deploy and keep referencing chunk files that no longer
    // exist on the server — the app loads blank until a hard refresh
    // bypasses the Cache API. Always try the network first; only fall back
    // to the cached shell when genuinely offline.
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(SHELL_CACHE).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match("/index.html")))
    );
    return;
  }

  // Other same-origin static assets (JS/CSS bundles, images): stale-while-revalidate.
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request).then((response) => {
        const copy = response.clone();
        caches.open(SHELL_CACHE).then((cache) => cache.put(request, copy));
        return response;
      }).catch(() => cached);
      return cached || network;
    })
  );
});

// Generic background sync: any page can call registerBackgroundSync('gew-sync')
// (see src/lib/pwa.js). When the browser fires it — including after the app
// was closed and connectivity returned — broadcast to open clients so a page
// like POS can trigger its own queue flush if it's mounted, and so a future
// mount can check "was there a pending sync" via this message.
self.addEventListener("sync", (event) => {
  if (event.tag !== "gew-sync") return;
  event.waitUntil(
    self.clients.matchAll({ type: "window" }).then((clients) => {
      clients.forEach((client) => client.postMessage({ type: "GEW_BACKGROUND_SYNC" }));
    })
  );
});
