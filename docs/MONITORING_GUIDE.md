# Monitoring Guide

What to watch after go-live, and where each signal actually comes from in
this codebase — no new dependency added for basic monitoring (Railway +
Supabase's built-in dashboards cover most of it out of the box).

## Application logs

- **Backend:** Gunicorn's `--access-logfile -` / `--error-logfile -` (see
  `backend/Dockerfile`) write to stdout/stderr, which Railway captures
  automatically — **Railway dashboard → your backend service → Logs** (or
  `railway logs --service backend` via the CLI). Application-level logging
  (`logging.basicConfig` in `server.py`) writes through the same stdout, so
  `logger.info/warning/error` calls throughout `core/`/`routers/` show up in
  the same place.
- **Frontend (browser-side):** the desktop/PWA work from the previous
  session added `frontend/src/lib/crashReporter.js` — unhandled JS errors and
  React error-boundary catches are logged. On the plain web build (no
  Electron bridge) these land in a bounded `localStorage` ring buffer
  (`gew_error_log`, max 50 entries) rather than a server-side log — there is
  no backend endpoint that receives frontend errors today. If you want
  centralized frontend error visibility, see "Error tracking" below.
- **Nginx (frontend container):** Railway captures the Nginx access/error
  logs from the frontend service the same way as the backend.

## Server monitoring

Railway's dashboard (per service) already shows, with zero extra setup:
- CPU / memory usage over time
- Deploy history and restart events
- Request count (via the metrics tab, once traffic flows)

Set a Railway **alert** (Project → Settings → Notifications, or per-service)
for deploy failures and for a service crossing memory limits — the free
tier's default alerts cover crash/restart events already.

## Database monitoring

**Supabase → your project → Reports** gives you, without any extra
integration:
- Query performance (slowest queries, most-called queries)
- Active connections vs. your plan's connection limit
- Disk/storage usage
- Cache hit rate

Additionally, this backend has its **own** built-in DB observability that
Supabase's dashboard can't see (per-request, not aggregate):
- Every HTTP response carries `X-Process-Time-Ms`, `X-DB-Queries`, and
  `X-DB-Time-Ms` headers (see `server.py`'s `request_db_session` middleware)
  — visible in the browser Network tab or `curl -i`, useful for spotting a
  newly-slow endpoint during manual testing.
- `GET /api/diagnostics` (admin-only, see `server.py`) returns live cache
  stats, cumulative DB query counters, and connection pool state
  (checked-in/checked-out/overflow/invalid). Use this as a quick "is the pool
  healthy" check without needing a dashboard.

**Target from the original ask — DB query <100ms:** this is realistic for
same-region queries but this deployment has an inherent cross-region latency
cost (Railway's region vs. Supabase's Mumbai/ap-south-1 region — see the
project's own dashboard-latency-fix notes) that no amount of query
optimization removes. If <100ms is a hard requirement, deploy the Railway
services in the region geographically closest to your Supabase project
(Railway → service Settings → Region), which is the single highest-leverage
change available — bigger than any query-level optimization for a
already-pooled, already-indexed schema like this one.

## API monitoring / uptime

Nothing is configured for external uptime checking today. Recommended
(free-tier friendly, no code changes needed):
- **UptimeRobot** or **Better Uptime** (free tiers exist) — point at
  `https://api.mycompany.com/health` (lightweight, no DB call — see
  `server.py`) on a 1–5 minute interval, and `https://erp.mycompany.com/healthz`
  for the frontend.
- Both existing health endpoints are intentionally cheap (no DB round-trip)
  so hitting them frequently doesn't add real load.

## Error tracking

**Not currently integrated with an external service** (e.g. Sentry). The
codebase has the pieces that would feed one:
- Backend: `global_exception_handler` in `server.py` already logs every
  unhandled exception with a full traceback before returning a JSON error —
  a Sentry SDK's FastAPI integration would slot in at this exact point
  (`sentry_sdk.init()` + its ASGI middleware) with minimal change.
- Frontend: `crashReporter.js`'s `reportError()` is already the single choke
  point every error flows through — swapping its body to also call
  `Sentry.captureException()` would centralize frontend errors without
  touching every call site.

This wasn't added in this pass because it requires a Sentry (or equivalent)
account and DSN that only you can provision — the integration points above
are ready the moment you have one.

## Performance metrics vs. the original targets

| Target | Current reality | Where it's measured |
|---|---|---|
| Page load <2s | Achievable — CRA build is code-split (73 lazy-loaded routes), gzip'd by Nginx, images optimized this pass. Real-world number depends on the user's distance from Railway's region. | Browser DevTools → Network/Performance tab; Lighthouse. |
| API response <500ms | Achievable for same-region; cross-region (Railway ↔ Supabase) adds latency outside app control — see Region note above. | `X-Process-Time-Ms` response header. |
| DB query <100ms | See Region note above — same-region is realistic, cross-region often isn't, regardless of indexing. | `X-DB-Time-Ms` response header, Supabase Reports. |

## Health dashboard

No dedicated dashboard page exists in-app. The closest things today:
- `GET /health` — liveness only (`{"status": "ok"}`), no auth, cheap.
- `GET /api/diagnostics` — admin-only, richer (cache/pool/query stats), see
  above.
- Railway's own per-service dashboard — the practical "health dashboard" for
  this deployment; building a custom one would duplicate what Railway/Supabase
  already show for no real gain at this scale.
