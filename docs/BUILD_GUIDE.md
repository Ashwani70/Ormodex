# Build Guide

How to build Ormodex ERP from source — web, desktop, and the PWA bundle. This
covers what exists in this repository today; mobile (Capacitor/React Native)
build steps will be added in a later phase (see the project's mobile-scope
notes — not yet built).

## Prerequisites

- Node.js 20.x (matches CI — see `.github/workflows/desktop-release.yml`)
- npm (ships with Node)
- Windows: no extra tooling needed for `dist:win`
- macOS `.dmg` builds: **must run on an actual Mac** (electron-builder can't
  cross-compile a signed/notarizable `.dmg` from Windows/Linux)
- Linux `.AppImage`/`.deb`: builds fine on Linux or via the CI runner; local
  builds on Windows/macOS are unsupported by electron-builder for these targets

## 1. Web build (also the source for desktop + PWA)

```bash
cd frontend
npm ci
npm run build          # → frontend/build/
```

This single build is used three ways:
- Served directly as the web app / PWA (it already contains
  `service-worker.js` and `manifest.json` in `public/`, copied into `build/`).
- Copied into `desktop/app/` for the Electron shell (see step 2).
- Deployed to your web host as-is for browser access.

**Environment variables** (`.env` / `.env.production` in `frontend/`):
- `REACT_APP_BACKEND_URL` — your FastAPI backend's base URL (web build only;
  the desktop build overrides this at runtime — see below).

## 2. Desktop build

```bash
cd desktop
npm install
npm i -D sharp png-to-ico     # icon tooling, once
node scripts/gen-icons.js     # icon.png + icon.ico from build-resources/icon.svg

npm run dist:win     # Windows: .exe (NSIS) + .msi
npm run dist:mac     # macOS only: .dmg (arm64 + x64)
npm run dist:linux   # Linux: .AppImage + .deb
```

`npm run build:frontend` (run automatically by the `dist:*` scripts) builds
`../frontend` with `PUBLIC_URL=.` so asset paths work under `file://`, then
injects a small bootstrap script so the app reads its backend URL from
Electron at runtime instead of a value baked in at build time. See
`desktop/scripts/build-frontend.js` for the exact mechanism.

Output lands in `desktop/release/`.

**Fast iteration without a full installer:**
```bash
npm run pack    # unpacked app in desktop/release/<platform>-unpacked/
npm start       # runs main.js against an existing desktop/app/ build
```

## 3. PWA — nothing extra to build

The PWA is just the web build (step 1). `frontend/public/service-worker.js`
and `manifest.json` ship as static files; no bundler plugin or extra build
step is required. To sanity-check it built correctly:

```bash
test -f frontend/build/service-worker.js && test -f frontend/build/manifest.json && echo OK
```

(This exact check runs in CI as the `pwa-check` job — see
`.github/workflows/desktop-release.yml`.)

To test PWA installability locally, serve the build over HTTP (service
workers require a secure context — `localhost` counts):
```bash
npx serve -s frontend/build
```

## 4. Marketing site (download center, docs, etc.)

```bash
cd marketing
npm ci
npm run build
npm start   # or `next start` for production, `next dev` for local dev
```

Relevant env vars (`.env.local`):
- `NEXT_PUBLIC_ERP_APP_URL` — where the hosted ERP app lives (Login button,
  PWA install link)
- `NEXT_PUBLIC_GH_RELEASES_REPO` — `owner/repo` for desktop installer downloads
- `NEXT_PUBLIC_APP_VERSION` — cosmetic version shown on the Download page

## 5. Backend (unchanged)

The FastAPI backend is untouched by any of the above — see the existing
backend README/docs for its own setup. All desktop/PWA/mobile work in this
repo talks to it over the same REST API the browser build already uses.

```bash
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8001
```
