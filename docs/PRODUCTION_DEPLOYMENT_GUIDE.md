# Production Deployment Guide

How to deploy Ormodex ERP to production on Railway, with a custom domain,
Supabase Postgres, and the security/CI/CD setup described in
`docs/SECURITY_CHECKLIST.md` and `.github/workflows/deploy.yml`.

**Stack as actually deployed** (see `docs/BUILD_GUIDE.md` for the historical
note that this is CRA, not Vite, despite older docs mentioning Vite):

```
                          ┌───────────────────────────┐
                          │   Supabase Postgres        │
                          │   (managed, existing)      │
                          └──────────────┬─────────────┘
                                         │ asyncpg (Supavisor pooler, :6543)
                          ┌──────────────▼─────────────┐
   DNS: api.mycompany.com │  Railway service: backend   │
   ───────────────────────▶  FastAPI + Gunicorn+Uvicorn  │
                          │  Dockerfile: backend/         │
                          │  Volume mounted at /data/uploads │
                          └──────────────┬─────────────┘
                                         │ HTTPS REST API
                          ┌──────────────▼─────────────┐
   DNS: erp.mycompany.com │  Railway service: frontend   │
   ───────────────────────▶  Nginx serving CRA build     │
                          │  Dockerfile: frontend/        │
                          └────────────────────────────┘
```

Two separate Railway services in **one Railway project**, each built from its
own Dockerfile in this monorepo, each with its own custom domain. Railway
terminates TLS for both — you never touch a certificate directly.

## 1. Prerequisites

- A Railway account with a payment method attached (the free trial tier does
  not support custom domains or the volume feature this setup needs).
- Your Supabase project already exists (it does — `DATABASE_URL` etc. are
  already in `backend/.env`).
- DNS access for `mycompany.com` (or your real domain) at your registrar/DNS
  provider.
- The GitHub repo connected to Railway (Railway → New Project → Deploy from
  GitHub repo).

## 2. Create the two Railway services

From the Railway dashboard, in one project:

### Backend service
1. **New Service → GitHub Repo** → select this repo.
2. **Settings → Source → Root Directory:** `backend`
3. Railway auto-detects `backend/Dockerfile` and `backend/railway.json`.
4. **Settings → Networking → Generate Domain** (temporary `*.up.railway.app`
   URL — use this to verify the deploy before wiring the real domain).
5. **Variables** — paste in every key from `backend/.env.example`, using your
   **real** Supabase pooler connection string, a freshly generated
   `JWT_SECRET` and `SETTINGS_ENCRYPTION_KEY` (commands are in the template),
   and `FRONTEND_URL=https://erp.mycompany.com`.
6. **Settings → Volumes → New Volume** — mount path `/data/uploads`, any size
   (start with 1–5 GB; product images/logos/PDFs are small). This is what
   makes `LOCAL_STORAGE_DIR=/data/uploads` (set in step 5) actually durable
   across deploys — **do this before your first real upload**, or files saved
   before the volume exists will vanish on the next deploy.

### Frontend service
1. **New Service → GitHub Repo** → same repo.
2. **Settings → Source → Root Directory:** `frontend`
3. Railway auto-detects `frontend/Dockerfile` and `frontend/railway.json`.
4. **Variables** — set `REACT_APP_BACKEND_URL` to the backend's Railway
   domain from step 4 above (temporarily), and mark it as a **build-time**
   variable (Railway → Variables → the toggle/checkbox for build args) since
   CRA inlines it into the JS bundle — a runtime-only variable would have no
   effect.
5. **Settings → Networking → Generate Domain** for now, same as the backend.
6. Deploy, confirm you can load the temporary URL and hit login.

**Verify end-to-end on the temporary URLs before touching DNS** — it's much
easier to debug a Railway networking issue without a domain/DNS layer on top
of it.

## 3. Point your domain at Railway

For each service, in Railway: **Settings → Networking → Custom Domain → Add
Domain**, enter `erp.mycompany.com` (frontend service) or
`api.mycompany.com` (backend service). Railway shows you a CNAME target
(`something.up.railway.app` or similar — copy the exact value it shows you,
it's unique per service).

At your DNS provider, add:

| Type | Host | Value | TTL |
|---|---|---|---|
| CNAME | `erp` | `<value Railway showed you for the frontend service>` | Auto/3600 |
| CNAME | `api` | `<value Railway showed you for the backend service>` | Auto/3600 |

(If your registrar doesn't support a CNAME at a subdomain — some don't allow
CNAME + other records at the same apex — use their "ALIAS"/"ANAME" record
type instead; Railway's docs cover provider-specific quirks.)

**SSL certificate:** Railway automatically provisions and renews a Let's
Encrypt certificate for each custom domain once the CNAME resolves — no
Certbot, no manual renewal, nothing for you to run. This typically completes
within a few minutes of the DNS record propagating; can take up to an hour on
slow-propagating registrars.

**HTTPS redirect:** Railway's edge redirects HTTP → HTTPS automatically for
custom domains — you don't need a redirect rule in `nginx.conf`.

## 4. Re-point the two services at their real domains

Once both custom domains are verified (green checkmark in Railway):

1. Backend service → Variables → `FRONTEND_URL=https://erp.mycompany.com`
   (should already be set from step 2, confirm it matches exactly).
2. Frontend service → Variables → `REACT_APP_BACKEND_URL=https://api.mycompany.com`,
   then **redeploy** (CRA bakes this in at build time — an env var change
   alone does nothing until the next build runs).
3. Confirm CORS: open `https://erp.mycompany.com`, log in, and check the
   Network tab shows no CORS errors against `https://api.mycompany.com`.
4. **Desktop/PWA clients** (from the previous session's work) — the desktop
   app's `desktop/main.js` already defaults `DEFAULT_BACKEND_URL` to
   `https://api.ormodex.com`. If that's genuinely your production API host,
   no change is needed and existing/future desktop builds already point at
   it. If your real domain differs, update that one constant before cutting
   the next desktop release (see `docs/RELEASE_GUIDE.md`) — everyone using
   File → "ERP Server…" to override it is unaffected either way.

## 5. Database — Supabase production configuration

Already managed by Supabase; what you're responsible for configuring:

- **Connection pooling:** already handled — `backend/core/db.py` auto-detects
  the Supavisor pooler and configures SQLAlchemy correctly for it (disabled
  prepared statements, warm pool, pre-ping, recycle — see the extensive
  comments in that file). Just make sure `DATABASE_URL` in Railway uses the
  **pooler host** (`aws-*.pooler.supabase.com:6543`), not the direct host —
  the direct host is IPv6-only and will fail to connect from Railway's
  network entirely.
- **Automatic backups:** Supabase → Project Settings → Database → Backups.
  Daily backups are included on paid Supabase plans (7-day retention on Pro,
  longer on higher tiers); the free tier has **no automatic backups** — if
  you're on the free tier, see `docs/BACKUP_RECOVERY_GUIDE.md` for a
  `pg_dump`-based scheduled backup you must run yourself.
- **Row Level Security (RLS):** Supabase Postgres has RLS available, but this
  app's authorization model is enforced entirely in the FastAPI layer
  (`core/auth_utils.py`'s `get_current_user`/`require_admin` and each
  router's own permission checks) — the backend connects with a service-role-
  equivalent Postgres user, not per-end-user Supabase Auth sessions. **RLS
  policies are not currently used and enabling them without also changing how
  the backend connects would not add protection** (the backend's DB role
  would need RLS-aware policies keyed to a Postgres role per tenant/user,
  which this schema doesn't have). Leave RLS off unless you're prepared to
  redesign the connection model around it — enabling it blind on tables the
  backend already fully controls access to would only risk breaking queries.
- **Migrations:** `alembic` — see `docs/BUILD_GUIDE.md § Backend` for the dev
  command; production migrations run via `.github/workflows/deploy.yml`'s
  migrate step (after backend build, before traffic switches — see CI/CD
  section below).
- **Performance indexes:** this schema already has indexes for its hot
  query paths (see `backend/alembic/versions/*` migration files for the
  ones added over time, e.g. `ledger_entries`, `stock_transactions`). Adding
  new ones is a normal Alembic migration — profile via `SQL_TIMING=true` +
  `SQL_SLOW_MS` (see `.env.example`) to find a genuinely slow query before
  adding an index speculatively.
- **Monitoring:** Supabase → Project → Reports gives you built-in query
  performance, connection count, and disk usage dashboards — no separate
  tool needed for basic DB monitoring. See `docs/MONITORING_GUIDE.md` for
  what to actually watch.

## 6. Redis / API caching — deliberately NOT added

The request for "Redis caching" was evaluated and **not implemented**: the
app already has `backend/core/cache.py`, a documented in-process TTL cache
(user identity, category/product lists, dashboard summaries) with a known,
explicit limitation — it's per-process, so it doesn't share state across
Railway replicas. Since this deployment runs **one replica per service** (see
§8 Scaling below), that limitation doesn't currently bite. Introducing Redis
now would add an operational dependency (another service to deploy, monitor,
and pay for) with no present benefit — revisit only if/when you actually scale
the backend to multiple replicas, at which point both the cache and
`core/rate_limit.py`'s in-process rate limiter would need a shared Redis
backing to keep working correctly across replicas.

## 7. First deploy checklist

1. Push to `main` (or run the `deploy.yml` workflow manually) — see
   `.github/workflows/deploy.yml`.
2. Confirm the backend's `/health` endpoint returns `{"status": "ok"}` at
   `https://api.mycompany.com/health`.
3. Confirm `SKIP_STARTUP_SEED` — leave unset (or `false`) for the very first
   deploy so the admin user gets seeded; **then set it to `true`** on all
   subsequent deploys so a restart doesn't re-run seed logic.
4. Log in at `https://erp.mycompany.com` with `ADMIN_EMAIL`/`ADMIN_PASSWORD`
   from your Railway variables, then **immediately change that password** —
   see `docs/SECURITY_CHECKLIST.md`.
5. Upload a test product image, redeploy the backend service, confirm the
   image is still there (proves the Volume is correctly mounted before real
   data depends on it).
6. Run through `docs/FINAL_VERIFICATION_CHECKLIST.md` in full.

## 8. Scaling notes (not enabled by default)

Railway can run multiple replicas of a service, but **don't enable this
without also addressing**:
- `core/rate_limit.py` and `core/cache.py` are in-process only (see §6).
- `desktop/updater.js`-style background tasks in the backend (e.g. the
  biometric sync scheduler in `server.py`'s lifespan) would run once **per
  replica** unless guarded — check `core/biometric_sync.py` before scaling
  past 1 replica, since duplicate scheduled runs could double-process data.

For most single-company ERP deployments, one backend replica is enough —
FastAPI + async I/O handles substantial concurrent load per instance, and the
actual bottleneck observed in this codebase's own perf audits was Supabase
cross-region latency, not CPU (see the project's own performance-audit
memory notes) — horizontal scaling wouldn't have fixed that anyway.
