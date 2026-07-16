# Security Audit — Ormodex ERP

_Date: 2026-06-17 · Scope: backend (FastAPI) + frontend (React) auth, secrets,
file handling, CORS, public API, and dependencies._

> **Honest framing:** No application is "unhackable," and no one can promise
> that. Security is layers that raise the cost of an attack and shrink the blast
> radius when something slips. This audit lists what is already done well, the
> concrete weaknesses found, and a prioritized fix list. It does **not** cover
> infrastructure (TLS termination, OS patching, MongoDB network exposure,
> backups, WAF, secrets manager) — those live outside this repo and matter just
> as much.

---

## ✅ Already solid

- **Secret API keys are server-side only.** `OPENAI_API_KEY`, `GEMINI_API_KEY`,
  `RESEND_API_KEY`, etc. live in `backend/.env` and are read via
  `os.environ` in backend code. They are **never** sent to or referenced by the
  frontend bundle. The only frontend env var is `REACT_APP_BACKEND_URL` (a
  public URL, not a secret). → Your "no one sees my API key in the front" goal
  is already met.
- **No hardcoded secret values** in frontend source (scanned for `sk-`, `AIza`,
  `re_`, hex blobs — none found).
- **`.env` is gitignored** and not tracked by git.
- **Passwords** hashed with bcrypt (`bcrypt.hashpw` + per-hash salt).
- **JWT** main app uses `os.environ["JWT_SECRET"]` (hard fails if unset — no weak
  default), HS256, access + refresh token split, httponly cookies.
- **Public API keys** generated with `secrets.token_urlsafe(32)`, stored only as
  SHA-256 hash (`key_hash`), shown to the user once, with per-key scope checks.
- **Audit-log redaction** of sensitive fields (`api_key`, `secret`, `password`,
  `token`) already exists in `core/utils.py`.
- **GSP/GST AES-256-ECB** in `crypto_utils.py` is dictated by the government GST
  Suvidha Provider protocol (fixed envelope format, HMAC-verified) — not a free
  design choice, leave as-is.

---

## ⚠️ Findings (prioritized)

### HIGH

**H1 — `/api/files/{path}` has no authentication.**
`routers/inventory.py::serve_file` serves any uploaded object to anyone who
knows (or guesses) the path. Paths embed a UUID so they're not trivially
enumerable, but they leak via referrer headers, browser history, and shared
links, and there is no access control. Anyone with a URL can fetch invoices,
payslips, product images, logos.
→ **Fix:** require authentication, OR scope file access, while keeping
intentionally-public assets (company logo, portal payslip share) working via a
separate, explicitly-public path or signed short-lived token.

**H2 — Token accepted from `?auth=` query parameter.**
`auth_utils.py::_read_token` falls back to `request.query_params.get("auth")`.
Access tokens in URLs leak into server/proxy logs, browser history, and
`Referer` headers sent to third parties. This is a well-known token-leak vector.
→ **Fix:** remove the query-param fallback; use Authorization header or
httponly cookie only. (Requires the file-serving `<img>` usage to send the
cookie instead — see H1 fix.)

**H3 — No rate limiting on `/auth/login` (or anywhere).**
Brute-force and credential-stuffing are unthrottled. An attacker can try
unlimited password guesses.
→ **Fix:** add per-IP + per-account rate limiting on login (and ideally on
refresh, password reset, public API). `slowapi` or a small Mongo/in-memory
counter.

### MEDIUM

**M1 — Portal token falls back to `"dev-secret"`.**
`core/portal_auth.py::_portal_secret` uses
`os.environ.get("JWT_SECRET") or ... or "dev-secret"`. If `JWT_SECRET` is unset
in production, portal tokens are signed with a publicly-known string → anyone
can forge portal sessions.
→ **Fix:** fail loudly when `JWT_SECRET` is missing, like the main app does.

**M2 — No security response headers.**
No HSTS, `X-Content-Type-Options`, `X-Frame-Options`/CSP frame-ancestors,
`Referrer-Policy`. Leaves room for clickjacking, MIME-sniffing, referrer leaks.
→ **Fix:** add a lightweight security-headers middleware.

**M3 — Access token lifetime is 24 hours.** ✅ FIXED
Now env-driven: `ACCESS_TOKEN_EXPIRE_MINUTES` (default **30**) and
`REFRESH_TOKEN_EXPIRE_DAYS` (default **14**). Refresh tokens are **rotated** on
every `/refresh` (unique `jti` recorded in `refresh_tokens`), with **reuse
detection**: presenting an already-rotated token revokes all of that user's
tokens (theft signal). Logout revokes all refresh tokens. A TTL index on
`expires_at` auto-purges expired records.

### LOW / INFO

**L1 — CORS `allow_methods=["*"]`, `allow_headers=["*"]` with credentials.**
Origins are explicitly listed (good), so this is acceptable, but wildcards are
broader than needed.

**L2 — Debug `print()` of key-configured state** in `ai_assistant.py`. ✅ FIXED
Removed the two `DEBUG RELOAD: ... API_KEY is SET/NOT SET` prints.

**L3 — Dependency scanning** not in CI. ✅ FIXED
Added `.github/workflows/security.yml`: `pip-audit -r backend/requirements.txt
--strict` and `npm audit --audit-level=high` on push/PR to main & master.

---

## Out of scope (infrastructure — your responsibility to verify)

- TLS/HTTPS enforced at the edge (so httponly+secure cookies actually apply).
- MongoDB not exposed to the public internet; auth enabled on the DB.
- `JWT_SECRET` is a long random value in production (≥32 random bytes), rotated
  if ever leaked.
- Object storage is the local filesystem (`LOCAL_STORAGE_DIR`); ensure the
  uploads directory has correct OS permissions and is on durable/backed-up storage.
- Backups + restore tested. Secrets in a manager, not a plaintext `.env` on a
  shared box.
- Server/OS patching, firewall, rate limiting at the LB/CDN/WAF layer.

---

## Fix plan (this PR)

1. **H1** — auth-gate `/api/files`, add an explicit public path for logo/payslip.
2. **H2** — drop the `?auth=` query-param token fallback.
3. **H3** — add login rate limiting.
4. **M1** — portal secret fails closed.
5. **M2** — security-headers middleware.

L2/L3 and M3 noted for follow-up.
