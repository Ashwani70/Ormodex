# Security Checklist — Production Go-Live

Verified against the actual codebase (not a generic checklist) — each item
notes exactly where it's enforced and what, specifically, you must configure
before go-live. Items marked **⚠ ACTION REQUIRED** are gaps found during this
deployment review that need a decision or a config change from you.

## Authentication & session security

- [x] **JWT** — HS256, `backend/core/auth_utils.py`. Access token
  (`ACCESS_TOKEN_MIN`) short-lived, refresh token (`REFRESH_TOKEN_DAYS`)
  longer-lived, both httpOnly cookies (not readable by JS).
- [ ] **⚠ ACTION REQUIRED — `ENV=production` must be set on Railway.**
  `set_auth_cookies()` gates the `Secure` cookie flag and `SameSite=None` on
  `os.environ.get("ENV") == "production"`. If this is left unset, cookies are
  issued **without `Secure`** and with `SameSite=Lax` — which will actually
  break cross-origin auth between `erp.mycompany.com` and
  `api.mycompany.com` (two different subdomains = cross-site under
  `SameSite=Lax`), so this isn't just a security gap, it will visibly break
  login if missed. Set it in both Railway services' Variables.
- [x] **JWT_SECRET** — must be a long random value, never the placeholder.
  Generate: `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
  Rotating it invalidates every existing session (all users must log in
  again) — plan a rotation for a low-traffic window if you ever need to do it.
- [x] **Rate limiting on login** — `core/rate_limit.py`, applied to
  `/auth/login` (see `routers/auth.py`). Documented limitation: in-process
  only, resets per deploy/restart, not shared across replicas. Fine for the
  single-replica deployment in `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`; revisit
  if you ever scale to multiple backend replicas.
- [x] **Account lockout** — `LOCKOUT_MINUTES` in `auth_utils.py` after
  repeated failed logins, independent of the rate limiter.
- [x] **MFA support** — `routers/mfa.py`, opt-in per account.

## CSRF

- [ ] **⚠ ACTION REQUIRED — `CSRF_ENFORCE` defaults to log-only, not blocking.**
  `server.py`'s `csrf_check` middleware logs a warning on token mismatch but
  does **not** reject the request unless `CSRF_ENFORCE=true` is explicitly
  set. Before go-live: set `CSRF_ENFORCE=true` on the backend service, watch
  the logs for a few days of real traffic first if you want to confirm no
  legitimate client is failing the check, then confirm it's really blocking
  by testing a request with a deliberately wrong `X-CSRF-Token`.
- [x] Double-submit cookie pattern — non-httpOnly `csrf_token` cookie, echoed
  back as `X-CSRF-Token` header by `frontend/src/lib/api.js`'s axios
  interceptor. Login/refresh/password-reset endpoints are exempted
  (`CSRF_EXEMPT_PREFIXES`) since they're the entry point before a CSRF
  cookie could exist yet.

## CORS

- [x] `server.py` — `allow_origins` is an explicit list (not `*`), sourced
  from `FRONTEND_URL` plus localhost dev origins. Confirm `FRONTEND_URL` is
  set to `https://erp.mycompany.com` in the backend's Railway variables
  (not left at the `localhost:3000` default).
- [x] `allow_credentials=True` paired with an explicit origin list (never
  wildcard) — required by the CORS spec anyway, already done correctly here.

## Encryption at rest

- [ ] **⚠ ACTION REQUIRED — `SETTINGS_ENCRYPTION_KEY` is currently UNSET.**
  `core/crypto.py` encrypts stored secrets (e.g. saved GST/e-Way Bill API
  credentials) with this key — **if it's not set, those secrets are stored in
  plaintext in Postgres right now**, and the code logs a warning on every
  startup saying exactly this. Generate one and set it before go-live:
  ```
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
  If you set this key **after** secrets already exist in plaintext, those
  existing rows are not automatically re-encrypted — re-save each affected
  settings record once the key is live so it gets encrypted going forward.
- [x] Passwords — bcrypt via `passlib` (`bcrypt==4.1.3` pinned in
  `requirements.txt`), never stored or logged in plaintext.

## File storage

- [ ] **⚠ ACTION REQUIRED — mount the Railway Volume before any real upload.**
  See `docs/PRODUCTION_DEPLOYMENT_GUIDE.md §2`. Without it, every product
  image / company logo / generated PDF uploaded is silently lost on the next
  deploy — the container disk is ephemeral otherwise.
- [x] Path traversal — `core/storage.py`'s `_local_paths()` resolves and
  validates every path stays inside `LOCAL_STORAGE_DIR`, raising on any
  attempt to escape it.
- [x] Upload content-type sniffing — magic-byte checks exist for at least the
  warehouse-document upload path (see project memory on the warehouse
  redesign); confirm this is applied consistently if you add new upload
  endpoints — a Content-Type header alone is client-supplied and untrustworthy.

## Headers

- [x] `server.py`'s `security_headers` middleware sets `X-Content-Type-Options:
  nosniff`, `X-Frame-Options: DENY`, and (in production) `Strict-Transport-
  Security`. `frontend/nginx.conf` sets the same headers again at the static-
  file layer as defense-in-depth.
- [ ] Consider adding a `Content-Security-Policy` header — not currently set
  anywhere in this codebase. Not added in this pass because a CSP strict
  enough to matter needs auditing every inline script/style and third-party
  resource (Google Fonts, any CDN scripts) the app actually loads, which is
  its own project — don't add a permissive/`unsafe-inline` CSP just to check
  a box, since that provides close to zero real protection.

## SQL injection

- [x] All database access goes through SQLAlchemy's parameterized query
  interface (async ORM/Core) — no raw string-interpolated SQL found in the
  routers/core modules during this review. Keep it that way: never
  f-string/`.format()` a value into a raw SQL string.

## XSS

- [x] React escapes all rendered content by default; a grep for
  `dangerouslySetInnerHTML` should be part of any future code review before
  adding new instances of it.
- [x] Backend never reflects unescaped user input into an HTML response (it's
  a pure JSON API).

## Audit logging

- [x] `backend/routers/audit.py` + `audit_logs` table already capture
  operator actions; `require_auditor_or_admin` gates who can read the log.
  Confirm which write paths actually call into the audit logger — this
  review didn't re-verify every single mutating endpoint writes an audit
  entry, only that the read/storage side exists and is access-controlled.

## Secrets hygiene

- [x] `backend/.env` is gitignored (`*.env` in `.gitignore`) and was never
  committed — confirmed via `git ls-files`.
- [x] `backend/.env.example` (this deployment) contains **no real secrets**,
  only placeholders and generation commands.
- [ ] Rotate `ADMIN_PASSWORD` immediately after first login in production —
  the seeded value is whatever's in your Railway variables, treat it as a
  bootstrap credential only.
- [ ] Store the real production `.env` values (JWT_SECRET, SETTINGS_ENCRYPTION_KEY,
  DATABASE_URL, all API keys) in a password manager or secrets vault, not just
  in Railway's dashboard — you need a recovery copy if the Railway project is
  ever lost/misconfigured.

## Dependency scanning

- [x] Already automated — `.github/workflows/security.yml` runs `pip-audit`
  (backend) and `npm audit` (frontend) on every push/PR. Nothing new needed
  here; this deploy adds a second workflow (`deploy.yml`) that doesn't
  duplicate or replace it.

## Summary of ACTION REQUIRED items before go-live

1. Set `ENV=production` on the backend Railway service.
2. Set `CSRF_ENFORCE=true` on the backend Railway service (after confirming
   the web client sends the header correctly).
3. Generate and set `SETTINGS_ENCRYPTION_KEY`.
4. Mount a Railway Volume at `/data/uploads` and set
   `LOCAL_STORAGE_DIR=/data/uploads` before the first real file upload.
5. Change `ADMIN_PASSWORD` immediately after first production login.
6. Back up your real `.env` values to a password manager.
