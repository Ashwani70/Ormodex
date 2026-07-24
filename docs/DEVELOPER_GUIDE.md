# Developer Guide — Desktop & PWA layer

For engineers working on the cross-platform shell around the existing React +
FastAPI ERP. This does not re-document the ERP application itself (routes,
modules, backend models) — see the main repo docs/CLAUDE.md for that. This
covers the desktop/PWA-specific code added around it.

## Mental model

The backend and its REST API are **completely unchanged**. Everything in this
layer is: (1) different ways to package and run the *existing* React frontend,
and (2) small, additive frontend changes (secure token storage, native-bridge
hooks) that behave identically on web and degrade gracefully when the native
bridge isn't present.

**Golden rule when touching this layer:** any `window.ormodex?.xxx` check must
have a working fallback for when it's `undefined` (plain web/PWA build). Never
make a feature *require* Electron.

## Where things live

```
frontend/src/lib/
  tokenStore.js       In-memory + encrypted-at-rest mirror of the access token.
                      Read by api.js's request interceptor (sync), written by
                      AuthContext.jsx on login/refresh/logout.
  secureStorage.js    AES-GCM encrypt/decrypt over localStorage, backed by a
                      non-extractable CryptoKey cached in IndexedDB. Used by
                      tokenStore.js and portalApi.js's portal-token mirror.
  crashReporter.js    reportError() — routes to the Electron log file if
                      window.ormodex.logError exists, else a bounded
                      localStorage ring buffer. installGlobalHandlers() wires
                      window.onerror/unhandledrejection; ErrorBoundary.jsx
                      calls reportError() from componentDidCatch.
  pwa.js              Service worker registration, install-prompt capture
                      (beforeinstallprompt), registerBackgroundSync().

frontend/src/hooks/
  useNativeNotify.js  notify(title, body) — OS notification via Electron,
                      Web Notification API fallback otherwise.

frontend/public/
  service-worker.js   Hand-written SW (no Workbox dependency). Network-first
                       for /api/*, cache-first for the app shell, stale-while-
                       revalidate for other static assets, generic
                       'gew-sync' Background Sync tag.
  manifest.json        Web app manifest — icons, shortcuts, display mode.

desktop/
  main.js             Electron main process — see desktop/README.md for the
                       full breakdown (splash, updater, IPC handlers, security).
  preload.js           The ONLY way the renderer talks to main — contextBridge,
                       no direct Node access (nodeIntegration: false, sandbox:
                       true). Adding a new native capability means adding both
                       an ipcMain.handle in main.js AND an exposeInMainWorld
                       entry in preload.js.
  updater.js, logger.js, splash.html, splash-preload.js, menu.js
                       Supporting modules — see inline comments, each is small
                       and single-purpose.
```

## Adding a new native capability

1. Add an `ipcMain.handle("your:channel", async (_e, args) => {...})` in
   `desktop/main.js`.
2. Expose it in `desktop/preload.js` under `contextBridge.exposeInMainWorld`.
3. Call it from React as `window.ormodex?.yourMethod?.(...)`, always with a
   fallback path for when it's undefined.
4. If it's something a support agent might need to debug, log it through
   `log.info/warn/error` (from `desktop/logger.js`) rather than only
   `console.log`.

## Testing changes across all three targets

```bash
# Web (and what the PWA install wraps)
cd frontend && npm start                  # dev server, hot reload

# Desktop, against a dev build
cd desktop && npm run build:frontend && npm start

# PWA install/offline behavior specifically (needs a real HTTP origin —
# service workers don't register meaningfully from file:// or over plain
# CRA dev-server HMR websockets)
cd frontend && npm run build && npx serve -s build
```

To test the offline cache: open the served build, load a few pages, then use
DevTools → Network → Offline (or literally disconnect) and reload — the app
shell should still render (though most `/api/*` calls will correctly fail,
since only GETs are cached and only opportunistically).

To test auto-update locally without cutting a real GitHub Release: point
`electron-updater` at a local feed by setting `dev-app-update.yml` — see
electron-updater's own docs; this repo doesn't need that file in normal
development since CI is the only place installers get built and signed for
distribution.

## Known, deliberate limitations

- **XSS still reads the token.** `secureStorage.js` encrypts the token
  *at rest* (defends against someone reading localStorage/appdata files
  directly) but cannot defend against an attacker who already has JS
  execution in the page — see the comment at the top of that file. The real
  mitigation for that class of attack is CSP + output encoding on the backend,
  which is a separate, pre-existing concern.
- **macOS auto-update needs signing+notarization** to work end-to-end
  (Sparkle/electron-updater's mac target validates the update package's
  signature before installing). Until the app is signed, mac users must
  manually reinstall each new `.dmg`.
- **No mobile native app yet.** Android/iOS Capacitor or React Native wrapping
  was explicitly scoped out of this phase — the PWA is the current
  cross-platform mobile answer. See the Download Center's "coming soon" cards
  in `marketing/lib/site.js` (`MOBILE_DOWNLOADS`).
- **Background Sync only fires on Chromium-based browsers** (Chrome, Edge,
  Android Chrome). Safari and Firefox silently no-op — `pwa.js`'s
  `registerBackgroundSync()` returns `false` there, which POS.jsx already
  handles (its own online/offline event listeners are the primary sync path;
  Background Sync is a bonus for the "app was fully closed" case).
