# Ormodex ERP — Desktop App

Real native installers for **Windows (`.exe` / `.msi`), macOS (`.dmg`) and Linux
(`.AppImage` / `.deb`)**.

Two backend targets ("mode") are supported:

- **Cloud** (the original thin-client mode): ships the built React UI locally
  and talks to your **hosted backend** over HTTPS. The backend/database are
  not bundled — every device pointed at the same server shares the same data.
- **Local** (offline mode): bundles a real Postgres instance and a copy of
  the FastAPI backend, both run as local child processes bound to
  `127.0.0.1` only. The app works with **zero internet access**. Data stays
  on that one device only — there is no cloud sync yet (a later phase).

On first-ever launch with no saved preference, the app tries the cloud
server; if it's unreachable, it automatically falls back to local mode so a
first-time user never lands on a dead end. After that, the mode is sticky —
switch it explicitly via **File → ERP Server…**.

```
desktop/
├── main.js                  Electron main process (window, security, server/mode config, IPC)
├── local-stack.js           Owns the local Postgres + local backend child processes
├── local-env.js             Generates/persists local-mode secrets (JWT, encryption key, ports)
├── preload.js               Secure IPC bridge (no Node in the renderer)
├── splash.html               Mode-aware splash screen (online / offline / starting local db)
├── splash-preload.js         Bridge for the splash screen only
├── menu.js                  Native menu — Server/mode switcher, Print, Check for Updates
├── logger.js                 Rotating file logger (userData/logs/main.log)
├── updater.js                 electron-updater wiring (GitHub Releases feed)
├── package.json             electron-builder config (win/mac/linux/msi targets, extraResources)
├── scripts/
│   ├── build-frontend.js    Builds ../frontend and copies it into app/
│   ├── build-python.js      Bundles a portable Python + backend deps for local mode
│   ├── copy-backend.js      Copies ../backend source (minus secrets/tests) for local mode
│   └── gen-icons.js         Generates icon.png / icon.ico from icon.svg
├── build-resources/icon.svg Brand icon source (raster icons generated in CI)
├── app/                     ← generated: the built React UI (gitignored)
├── backend-src/             ← generated: backend source for local mode (gitignored)
└── runtime/python/          ← generated: bundled Python per-platform (gitignored)
```

## Local (offline) mode — how it works

`local-stack.js` starts two child processes when the resolved mode is
`"local"`:

1. **Postgres**, via the `embedded-postgres` npm package, data directory
   `userData/pgdata` (persists across restarts — only initializes once).
2. **The real, unmodified FastAPI backend**, via a bundled Python interpreter
   running `uvicorn server:app`, pointed at that local Postgres.

Both are bound to `127.0.0.1` only — never LAN-reachable. Secrets (JWT
signing key, settings-encryption key, generated DB password, and the ports
picked at first run) are generated once and persisted in
`userData/local-secrets.json`, kept separate from the human-edited
`config.json` so restarts don't invalidate existing sessions.

`backend/core/db.py` and `server.py` needed **zero code changes** for this —
`DATABASE_URL` already defaults to a local Postgres connection string, and
the dev-mode startup path (`ENV=development`, which local mode sets) already
auto-creates the schema and seeds an admin user.

Local mode is stopped gracefully (SIGTERM → wait → SIGKILL if needed, then
Postgres) on app quit, and re-started fresh on next launch if still selected.

## What's built in

| Requirement | How it's implemented |
|---|---|
| Auto-update | `electron-updater` (`updater.js`), checks on launch + every 4h, prompts to restart. Feed is GitHub Releases — see [Release via CI](#release-via-ci-recommended). |
| Offline splash screen | `splash.html` — pings the backend before the main window opens, shows online/offline state. |
| Native notifications | `Notification.isSupported()` in `main.js`, exposed to the renderer as `window.ormodex.notify(...)`. |
| File upload/download | Native Save/Open dialogs (`file:save` / `file:open` IPC), used by `frontend/src/lib/currency.js`'s `downloadPdf()` when running inside Electron. |
| Native print | `webContents.print()` / `printToPDF()`, plus the existing `window.print()` calls already work unmodified (Chromium handles those natively). |
| Secure session | Access token encrypted at rest via Web Crypto AES-GCM — see `frontend/src/lib/secureStorage.js` + `tokenStore.js`. |
| Full-screen/maximized launch | Window opens `.maximize()`d on `ready-to-show`. |
| Professional icon | `build-resources/icon.svg` → generated `.ico`/`.png`/`.icns` via `gen-icons.js`. |
| Disable devtools in production | `webPreferences.devTools: isDev` + blocked shortcuts (F12, Ctrl+Shift+I/J/C) when packaged. |
| Crash reporting / error logging | `logger.js` writes rotating JSON-line logs; renderer errors forwarded via `log:error` IPC; React `ErrorBoundary` and `window.onerror`/`unhandledrejection` all report through `frontend/src/lib/crashReporter.js`. |
| Native menus / keyboard shortcuts | `menu.js` — File/Edit/View/Window/Help, Ctrl+P print, Check for Updates. |
| Fully offline (local) mode | Bundled Postgres + bundled FastAPI backend as local child processes (`local-stack.js`) — see [Local (offline) mode](#local-offline-mode--how-it-works) above. |

## How the backend URL and mode are resolved

The desktop build overrides the API at **runtime** (the web build is unchanged).

Mode (`"cloud"` | `"local"`), first match wins:

1. `GRAVITYONE_MODE` environment variable
2. A mode the user saved via **File → ERP Server…** (stored in userData/config.json)
3. `"auto"` — resolved once on true first launch: cloud if reachable, local
   otherwise. Sticky after that.

Backend URL, first match wins:

1. `GRAVITYONE_BACKEND_URL` environment variable
2. If mode is `"local"` and the local stack is running: its `127.0.0.1` URL
3. A URL the user saved via **File → ERP Server…** (stored in userData/config.json)
4. `DEFAULT_BACKEND_URL` in [`main.js`](main.js) — **set this to your production API
   host before releasing** (default `https://api.ormodex.com`)

The frontend reads it through `window.__GRAVITYONE_BACKEND_URL__`, wired up in
`frontend/src/lib/api.js` and `portalApi.js`.

## Build locally

```bash
# from desktop/
npm install
npm i -D sharp png-to-ico   # icon tooling (once)
node scripts/gen-icons.js   # creates icon.png + icon.ico

npm run dist:win    # → release/Ormodex-ERP-Setup-<v>.exe + .msi
npm run dist:linux  # → release/Ormodex-ERP-<v>.AppImage + .deb
npm run dist:mac    # macOS ONLY — .dmg can't be built on Windows/Linux
```

Each `dist*`/`pack` script now also runs `build:python` (downloads a portable
Python 3.12.7 — pinned to match `render.yaml`'s production version — and
installs `backend/requirements-desktop.txt` into it) and `copy:backend`
(copies `../backend` source, excluding `.env`/tests/caches) before invoking
`electron-builder`, so packaged installers always include a working local
mode. **These two bundling steps must run natively per target OS** — you
cannot produce a Windows local-mode bundle from a Linux/macOS machine or vice
versa; CI (`desktop-release.yml`) already builds natively per OS, so this
isn't a new constraint there.

To run just the bundling steps (e.g. to inspect the output, or for local dev
without a full installer build):

```bash
npm run build:python    # → runtime/python/<platform>-<arch>/
npm run copy:backend    # → backend-src/
```

`npm run pack` makes an unpacked app (fast smoke test, no installer).
`npm start` runs the app against an existing `app/` build for development —
in dev, local mode reads Python from `runtime/python/<platform>-<arch>/`
(same layout `build:python` produces) and backend source directly from
`../backend`, so running `npm run build:python` once locally is enough to
test local mode without a full package/install cycle.

## Release via CI (recommended)

`.github/workflows/desktop-release.yml` builds all three OSes (plus a fast
PWA-build sanity check) and uploads the installers to a **GitHub Release**:

```bash
# bump the version in desktop/package.json first, then:
git tag v2.4.0
git push origin v2.4.0
```

The marketing site's download buttons point at
`github.com/<repo>/releases/latest/download/...` (see `marketing/lib/site.js`),
so they start working the moment a release is published — no website redeploy needed.

### Auto-update feed

`electron-builder` also emits `latest.yml` (Windows), `latest-mac.yml`, and
`latest-linux.yml` alongside the installers — these are what `electron-updater`
(`updater.js`) polls to learn a newer version exists. The workflow uploads them
to the Release automatically; **don't rename or remove them**, and don't hand-edit
a Release after the fact without keeping these files in sync with the real assets.

### Stable download names (no version drift)

Each release uploads **two copies** of every installer:

- a **versioned** file for humans browsing the release
  (`Ormodex-ERP-Setup-2.4.0.exe`)
- a **version-less alias** the website links to
  (`Ormodex-ERP-Setup.exe`, `Ormodex-ERP-Setup.msi`, `Ormodex-ERP.dmg`, `Ormodex-ERP.AppImage`)

Because the website uses the stable aliases, the download links keep working
across releases even if `desktop/package.json` `version` and
`NEXT_PUBLIC_APP_VERSION` drift apart — no more 404s. The alias step lives in
`.github/workflows/desktop-release.yml`; keep its names in sync with `site.js`.

## Code signing

Currently **unsigned** — users see an "unknown developer" warning on first launch
(Windows SmartScreen / macOS Gatekeeper). To sign later, supply certs via env/secrets:

- **Windows:** `CSC_LINK` (base64 .pfx) + `CSC_KEY_PASSWORD`
- **macOS:** Apple Developer ID cert + `APPLE_ID` / `APPLE_APP_SPECIFIC_PASSWORD`
  for notarization, then flip `CSC_IDENTITY_AUTO_DISCOVERY` back on in the workflow.

Auto-update over an unsigned build still works (electron-updater doesn't require
signing to *check* for and download updates), but Windows SmartScreen will
re-warn on every new unsigned installer a user runs manually. Signing removes
that friction entirely — see `docs/RELEASE_GUIDE.md`.

## Logs & diagnostics

- **Windows:** `%APPDATA%/Ormodex ERP/logs/main.log`
- **macOS:** `~/Library/Application Support/Ormodex ERP/logs/main.log`
- **Linux:** `~/.config/Ormodex ERP/logs/main.log`

Rotates at 2 MB (`main.log` → `main.log.1`). Ask a user having trouble to send
this file rather than a screenshot when reporting a crash.
