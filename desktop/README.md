# Gravity One ERP — Desktop App

Real native installers for **Windows (`.exe`), macOS (`.dmg`) and Linux (`.AppImage`/`.deb`)**.

This is an **Electron thin client**: it ships the built React UI locally and talks to
your **hosted backend** over HTTPS. The backend and database are **not** bundled — set
the server URL once and every device shares the same data.

```
desktop/
├── main.js                  Electron main process (window, security, server config)
├── preload.js               Secure IPC bridge (no Node in the renderer)
├── menu.js                  Native menu + "ERP Server…" switcher
├── package.json             electron-builder config (win/mac/linux targets)
├── scripts/
│   ├── build-frontend.js    Builds ../frontend and copies it into app/
│   └── gen-icons.js         Generates icon.png / icon.ico from icon.svg
├── build-resources/icon.svg Brand icon source (raster icons generated in CI)
└── app/                     ← generated: the built React UI (gitignored)
```

## How the backend URL is resolved

The desktop build overrides the API at **runtime** (the web build is unchanged).
First match wins:

1. `GRAVITYONE_BACKEND_URL` environment variable
2. A URL the user saved via **File → ERP Server…** (stored in userData/config.json)
3. `DEFAULT_BACKEND_URL` in [`main.js`](main.js) — **set this to your production API
   host before releasing** (default `https://api.gravityone.com`)

The frontend reads it through `window.__GRAVITYONE_BACKEND_URL__`, wired up in
`frontend/src/lib/api.js` and `portalApi.js`.

## Build locally

```bash
# from desktop/
npm install
npm i -D sharp png-to-ico   # icon tooling (once)
node scripts/gen-icons.js   # creates icon.png + icon.ico

npm run dist:win    # → release/GravityOne-ERP-Setup-<v>.exe
npm run dist:linux  # → release/GravityOne-ERP-<v>.AppImage + .deb
npm run dist:mac    # macOS ONLY — .dmg can't be built on Windows/Linux
```

`npm run pack` makes an unpacked app (fast smoke test, no installer).
`npm start` runs the app against an existing `app/` build for development.

## Release via CI (recommended)

`.github/workflows/desktop-release.yml` builds all three OSes and uploads the
installers to a **GitHub Release**:

```bash
# bump the version in desktop/package.json first, then:
git tag v2.4.0
git push origin v2.4.0
```

The marketing site's download buttons point at
`github.com/<repo>/releases/latest/download/...` (see `marketing/lib/site.js`),
so they start working the moment a release is published — no website redeploy needed.

### Stable download names (no version drift)

Each release uploads **two copies** of every installer:

- a **versioned** file for humans browsing the release
  (`GravityOne-ERP-Setup-2.4.0.exe`)
- a **version-less alias** the website links to
  (`GravityOne-ERP-Setup.exe`, `GravityOne-ERP.dmg`, `GravityOne-ERP.AppImage`)

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
