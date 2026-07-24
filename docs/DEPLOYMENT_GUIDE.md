# Deployment Guide — Desktop & PWA Distribution

How the desktop installers and installable PWA get from source to running in
front of users, **given a backend that's already deployed**. For standing up
the actual production backend/frontend hosting (Railway, domains, database,
CI/CD, monitoring, backups), see `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` — that
guide covers the server side; this one covers desktop/PWA distribution on top
of it.

## Architecture recap

```
                     ┌─────────────────────┐
                     │   FastAPI backend    │  ← unchanged, existing deployment
                     │  (Postgres/Supabase) │
                     └──────────┬──────────┘
                                │ HTTPS REST API
       ┌────────────────────────┼────────────────────────┐
       │                        │                        │
┌──────▼──────┐        ┌────────▼────────┐      ┌────────▼────────┐
│  Web build   │        │  Desktop shell   │      │  PWA (same web   │
│ (browser)    │        │ (Electron, thin  │      │  build, installed│
│              │        │  client, no DB)  │      │  from a browser) │
└──────────────┘        └─────────────────┘      └──────────────────┘
```

All three frontends are **the same React build** — the desktop shell just
wraps it in a native window and overrides the API base URL at runtime; the
PWA is the same static files plus a service worker. There is no separate
"desktop backend" or "mobile backend" to deploy.

## Web / PWA deployment

1. Build: `cd frontend && npm run build` (see `docs/BUILD_GUIDE.md`).
2. Deploy `frontend/build/` to your static host / CDN as you already do.
3. **Nothing extra required for the PWA to work** — `manifest.json` and
   `service-worker.js` are already in `public/` and ship with every build.
4. Confirm your host serves the site over **HTTPS** (service workers refuse
   to register over plain HTTP, except on `localhost`).
5. Confirm your host does **not** rewrite `/service-worker.js` or
   `/manifest.json` — if you have an SPA catch-all rewrite rule, exclude these
   two paths (and the icon files the manifest references) from it.

### Cache invalidation on release

The service worker uses a versioned cache name (`CACHE_VERSION` in
`frontend/public/service-worker.js`). Bump that constant whenever you ship a
release that must force clients to drop old cached assets — otherwise a
previously-installed PWA may keep serving a stale shell until the browser
gets around to checking for a SW update on its own schedule.

## Desktop installer distribution

Desktop installers are **not deployed to a server** — they're built once per
release and downloaded/installed by each user (see `docs/RELEASE_GUIDE.md`
for the actual cut-a-release steps). What you deploy is:

1. The **backend API** (unchanged, existing process) — every installed
   desktop app talks to this over HTTPS.
2. The **download links** — the marketing site's `/download` page links to
   `github.com/<repo>/releases/latest/download/<stable-name>`, which always
   resolves to the newest published release with zero redeploy needed when a
   new version ships.
3. **The auto-update feed** — `latest.yml` / `latest-mac.yml` /
   `latest-linux.yml`, uploaded to the same GitHub Release by CI. Already-
   installed apps poll this on launch and every 4 hours (`desktop/updater.js`)
   and self-update without needing anything from you beyond publishing the
   Release.

## Environment configuration by target

| Setting | Web build | Desktop build |
|---|---|---|
| Backend URL | `REACT_APP_BACKEND_URL` at build time | `DEFAULT_BACKEND_URL` in `desktop/main.js`, or `GRAVITYONE_BACKEND_URL` env var, or in-app "ERP Server…" — resolved at **runtime**, not baked into the build |
| Auth | httpOnly cookie (primary) + Bearer token fallback, same backend for both | same — the desktop shell is just another HTTP client |

**Before your first real desktop release:** update `DEFAULT_BACKEND_URL` in
`desktop/main.js` from the placeholder (`https://api.ormodex.com`) to your
actual production API host. Until then, self-built desktop apps are usable
but require every user to manually set the server URL once via **File → ERP
Server…**.

## Rollback

- **Web/PWA:** redeploy the previous `frontend/build/` to your host — the
  service worker's stale-while-revalidate/network-first strategy means
  clients pick up the rollback on their next load (or immediately for API
  calls, which are always network-first).
- **Desktop:** you cannot force-downgrade an already-updated install. To
  stop the bad version from spreading further, delete/unpublish the bad
  GitHub Release (or its `latest*.yml` files specifically) so
  `electron-updater` stops offering it to users who haven't updated yet.
