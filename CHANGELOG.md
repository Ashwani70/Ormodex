# Changelog

## Marketing website (Next.js) + public lead capture into CRM

A standalone B2B marketing site for Ormodex ERP, plus the backend hook that
turns demo-form submissions into CRM leads.

- **Added** `marketing/` — a separate **Next.js 14 (App Router) + Tailwind**
  project (Vercel-ready), independent of the product app in `frontend/`.
  Pages: Home, Features, Industries, Pricing, About, Contact, Blog (+ 5
  SEO articles targeting the brief's keywords). The homepage covers all 10
  requested sections (hero with dashboard mockup + logos, problems, feature
  cards, industries, benefits, product tour, pricing, testimonials, FAQ,
  contact/demo form). Includes scroll-reveal animations, a floating WhatsApp
  button, JSON-LD schema, `sitemap.xml`/`robots.txt`, OpenGraph metadata, and
  Google Analytics wiring. Brand palette (#4F46E5 / #10B981 / #0F172A) and Inter
  font per spec. `npm run build` produces 17 static/SSG routes.
- **Added** `backend/routers/public_leads.py` — unauthenticated
  `POST /api/public/demo-request` that creates a CRM **Lead** (`source =
  "Website"`), folding marketing-only fields (industry, users, requirements)
  into the lead notes. Rate-limited per IP (5 / 10 min) with a honeypot field to
  blunt spam; bounded/validated input (`EmailStr`, length & numeric limits).
- **Tests** — `tests/test_public_leads.py` (6): model validation, form→lead
  mapping, notes composition, and silent honeypot drop.

## Currency Master — searchable currency picker with auto-fill

The Currency master's manual "ISO Code" text box is replaced with a searchable
dropdown that auto-fills the related fields, so currencies are picked, not typed.

- **Added** `frontend/src/config/currencies.js` — predefined currency catalogue
  (the spec's 9 + common additions; expandable toward full ISO 4217), with
  `CURRENCY_BY_CODE` lookup and the `INR — Indian Rupee (₹)` option formatter.
- **Added** `frontend/src/components/CurrencySelect.jsx` — accessible combobox
  with type-ahead filtering (by code or name) and full keyboard navigation
  (↑/↓/Enter/Esc). Selecting a currency calls back with `{code,name,symbol,decimals}`.
- **Changed** `MasterScreen.jsx` — new `currency-picker` field type auto-fills
  ISO Code / Symbol / Formal Name / Decimal Places on selection. `readOnly`
  fields are locked (with a hint) and become editable **only for admins**
  (requirement 6). Client-side `unique` (duplicate ISO) and `nonNegativeInt`
  (decimal places) guards give instant feedback; the backend still enforces both.
- **Config** `mastersConfig.js` — ISO Code → `currency-picker` (`unique`);
  Symbol / Formal Name / Decimal Places → `readOnly`; Decimal Places gains
  `nonNegativeInt`. Stored field names unchanged (`iso_code`, `symbol`,
  `formal_name`, `decimal_places`, `is_base_currency`) — **fully backward
  compatible**; legacy/custom codes outside the catalogue still display & edit.
- **Backend** — `Currency` / `CurrencyUpdate` models now constrain
  `decimal_places` to ≥ 0; PDF `_money()` resolves symbols for the wider
  catalogue with ASCII-safe and ISO-code fallbacks so no currency renders as a
  `.notdef` box (requirement 8; complements the existing Unicode-font init).
- **Tests** — `tests/test_currency_master.py` (10): decimal-places validation and
  per-currency symbol rendering/fallbacks.

## Ctrl+K search — now covers every module

The global-search "Pages" results were driven by a hardcoded ~23-item shortlist,
so most modules (Cheque Printing, Job Work, Manufacturing, POS, Projects, Fixed
Assets, Vouchers, Branches, Masters, …) never appeared when searched.

- **Added** `frontend/src/lib/navItems.js` — single source of truth for the ERP
  navigation, exported as `ALL_NAV_ITEMS` plus `searchablePages(role)`. The
  sidebar (`components/Sidebar.jsx`) and the Ctrl+K palette
  (`components/Layout.jsx`) now both consume it, so they can't drift: **every menu
  page the user can reach is searchable** (role-filtered), each rendering its real
  lucide icon. Page results cap raised 6 → 12.
- **Backend** — `routers/search.py` record fan-out extended with 5 more entities:
  Projects, Job Work challans, PDC/Cheques, printed Cheques, and POS sales.
- **Tests** — `tests/test_global_search.py` gains a guard that the newer modules
  stay registered in the search entity list.

## Universal Cheque Printing — print on any Indian bank's CTS leaf, no external API

A new module to configure per-bank cheque templates and print onto pre-printed
CTS cheque leaves with millimetre-precise field placement.

- **Added** `routers/cheque_printing.py` (`/api/cheque-printing/*`, also under
  `/api/v1`) — bank-account master (extends the existing `bank_accounts` with
  holder/branch/cheque-type/linked-template), cheque-template manager
  (create/edit/**duplicate/activate/archive**, background-image upload via object
  storage, mm dimensions, per-field x/y/font/size/char-spacing/alignment), and the
  print workflow (`/cheques/preview`, `/cheques/print`, `/cheques/{id}/cancel`,
  `/cheques` register). Amount auto-converts to Indian lakh/crore words.
- **Added** `core/cheque_print_pdf.py` — ReportLab builder that sizes the page to
  the template's exact mm dimensions (so output drops onto a real leaf with no
  scaling), honours per-field font/alignment/character-spacing, and supports a
  **test-print** mode that overlays the alignment image + border for dry runs.
- **Validation & audit** — payee mandatory, amount > 0, **cheque number unique per
  bank account** (app check + partial unique index in migration 015); printed
  cheques are locked (status `draft`/`printed`/`cancelled`); cancellation requires
  a reason. Every create/update/print/cancel writes to `audit_logs`.
- **Security** — three new module-permission keys (`cheque_template_manage`,
  `cheque_print`, `cheque_cancel`) in `core/modules.py`; template changes are
  admin-restricted.
- **Frontend** — `pages/ChequePrinting.jsx` with Print / Bank Accounts / Templates
  tabs, including a drag-and-drop template editor with arrow-key fine-tuning and
  zoom; routed at `/cheque-printing` (guarded by `cheque_print`) with a sidebar link.
- **Migration** `migration_015_cheque_printing.py` — collections + indexes for
  `cheque_templates` and `cheque_transactions`.
- **Tests** — `tests/test_cheque_printing.py` (16): PDF builder, font mapping,
  field resolution, input validation, and Indian amount-in-words.

## Global search — find records across modules (Ctrl+K)

The top-bar "Search ERP modules…" palette previously only matched a hardcoded
list of page names. It now also searches **actual records** across the business.

- **Added** `routers/search.py` — `GET /api/search?q=` fans out concurrently
  across 14 collections (customers, leads, quotations, sales orders, invoices,
  dispatches, suppliers, products, purchase orders, GRNs, employees, expenses,
  vouchers, fixed assets), returning up to 5 hits each with a `module` label,
  `title`/`subtitle`, and a deep-link `path`. User input is **regex-escaped**
  before the Mongo `$regex` (prevents breakage / ReDoS); a failing collection
  can't sink the whole search.
- **Frontend** — the Ctrl+K palette now shows two groups: instant local **Pages**
  matches and debounced (250 ms) cross-module **Records** matches, each row
  deep-linking to its module. (`components/Layout.jsx`.)
- **Deep-link pre-filter** — Products and Employees now seed their search box from
  `?q=`, so a record hit lands on the page *and* filters to it. Other modules
  navigate to the correct page (their list views don't yet read a URL filter).
- **Tests** — `tests/test_global_search.py` (7): helper composition, the q-aware
  deep-link rule, regex escaping, and a fanned-out search against a stubbed db.

## Job Work Challan — per-item rate, GST, and GSTIN fetch

The job-work delivery challan now captures material valuation and GST metadata
(tracked for ITC-04; no tax is charged on a job-work despatch under Rule 45).

- **Changed** `JobWorkChallanItem` to add `rate`, `taxable_value`, `hsn_code`,
  `gst_rate` (plus `description`/`remarks`); `JobWorkChallan` gains
  `job_worker_gstin` and an explicit `nature` field.
- **Added** `_enrich_item_valuation()` in `routers/job_work.py`: rate defaults to
  the product's cost price (editable), `taxable_value` is always recomputed as
  `rate × quantity` so they can't drift, and `hsn_code`/`gst_rate` auto-fill from
  the catalog product. Applied on both create and edit. ITC-04 Table 4 now
  includes `rate` and `gst_rate`.
- **PDF** — the challan PDF gained HSN / Rate / GST% / Taxable Value columns, a
  total-taxable-value row, and the job worker's GSTIN in the header.
- **Frontend** (JobWork page) — line items have Rate and GST% inputs (auto-filled
  when a product is picked) with a live taxable-value column and total; a **Fetch
  GST** button looks up the job worker's GSTIN via the existing
  `/customers/fetch-gstin` (cached, multi-provider) and stamps it on the challan.
  Detail view + edit form surface the new fields.
- **Tests** — `tests/test_job_work_valuation.py` (5) for the enrichment helper and
  model (the full flow tests remain integration-style).

## Users & roles — fix module-permission wiring

Granting a non-admin user access to specific modules now actually works. The
router guards all read `user.module_permissions` (a list), but the user-create/
update API only ever stored a `permissions` dict — so module access for HR/
Accountant/Employee users silently did nothing. Aligned the two.

- **Added** `core/modules.py` — the single canonical catalog of grantable module
  keys (taken from the real `_require_*` guards) + `valid_module_keys()` which
  drops unknown keys and de-duplicates. One source of truth for guards, API, and
  UI so they can't drift.
- **Changed** `UserCreate`/`UserUpdate` to accept `module_permissions: List[str]`;
  `routers/users.py` now persists it (validated) on create and update.
- **Added** `PUT /api/users/{id}/module-permissions` (replace a user's access
  list) and `GET /api/users/modules` (catalog for the UI). The legacy
  `PATCH /{id}/permissions` is kept but documented as not read by guards.
- **Frontend** — the Users page role dropdown now includes **HR** and
  **Accountant** (was only Employee/Admin), plus a **Module access** checkbox grid
  driven by `GET /users/modules`. Hidden for admins (who have everything).
- **Note on HR** — HR/Payroll/Purchase routes are gated by the user's **role**
  (`require_hr_or_admin` etc.), not a module key, so HR access is granted by
  setting role=`hr`, while `module_permissions` controls granular access for
  `employee` users.
- **Tests** — `tests/test_module_permissions.py` (5): catalog/validator behaviour
  and that a granted key satisfies the matching guard while others 403.

## Auth hardening — password policy + TOTP multi-factor authentication

Closes the two remaining application-code gaps from the security checklist:
strong-password enforcement and MFA.

- **Added** `core/password_policy.py` — single source of truth for password
  strength: minimum length (12, overridable via `PASSWORD_MIN_LENGTH`),
  upper/lower/digit/symbol classes, a common-password blocklist, and a 72-byte
  bcrypt cap so long passwords can't be silently truncated. Wired into the
  `UserCreate`/`UserUpdate` Pydantic models (validates at the API boundary) and
  into the HR employee `create_login` path (which inserts users directly,
  bypassing the model). Returns all failures at once.
- **Added** TOTP MFA. `core/mfa.py` provides secret generation, provisioning-URI
  (QR) building, code verification with a ±1 step drift window, and one-time
  recovery codes (stored **bcrypt-hashed**, consumed on use). New `routers/mfa.py`
  exposes `/auth/mfa/{status,enroll,verify,disable}` and recovery-code
  regeneration; enrollment is two-phase (pending secret → verified → enabled) so
  a half-finished setup can't lock anyone out. Disable/regenerate require the
  account password.
- **Changed** the login flow (`routers/auth.py`): MFA-enabled accounts get a
  short-lived (5 min) `mfa_challenge` token from `/auth/login` instead of a
  session; `/auth/login/mfa` exchanges that token + a TOTP **or** recovery code
  for auth cookies. The MFA step is rate-limited per-IP and per-account like the
  password step.
- **Frontend** — `AuthContext` handles the `mfa_required` response and exposes
  `completeMfaLogin`; the login page renders a second code-entry step.
  `components/MfaSettings.jsx` is a drop-in card for enroll/QR/verify/disable +
  recovery-code display (uses the existing `react-qr-code` dep).
- **Tests** — `tests/test_password_policy.py` and `tests/test_mfa.py` (22 tests,
  function-level, no live server). Bumped 11-char integration-test fixtures to
  12+ chars to satisfy the new policy.
- **Changed** the seed admin's default password (`ADMIN_PASSWORD`) from the weak
  `admin123` to the policy-compliant `Admin@123456`, so a fresh install's admin
  isn't immediately forced to reset. Test fixtures and the login-page default/
  hint were updated to match. **Still set a unique strong `ADMIN_PASSWORD` via env
  before go-live** — the default is a known value.

### Forced reset for existing sub-policy passwords

- **Changed** `/auth/login`: after verifying a correct password, it is re-checked
  against the policy. A failing account is flagged `password_change_required`
  (persisted) and the flag is returned on the user; login still succeeds so the
  user can reach the change endpoint. A stale flag is cleared if the password is
  later compliant.
- **Added** `POST /auth/change-password` (`ChangePasswordIn`): verifies the
  current password, enforces the policy on the new one (model validator), rejects
  reuse of the same password, clears the reset flag, and revokes all refresh
  tokens (other sessions must re-authenticate) while re-issuing a session for the
  caller.
- **Frontend** — `AuthContext` exposes `changePassword` + `mustChangePassword`;
  `ProtectedRoute` renders the new `components/ForcePasswordChange.jsx` full-screen
  gate until a compliant password is set, so flagged users can't reach the app.
- **Tests** — `tests/test_forced_password_reset.py` (6): model validation + flag
  set/clear/idempotency with a stubbed `db.users`.

## Customer Master — GSTIN auto-fetch via Cashfree (`POST /api/customers/fetch-gstin`)

The Customer Master "Fetch Details" button now pulls registered GST details for
a GSTIN from the Cashfree GST verification API and auto-fills the form, with the
provider credentials kept entirely server-side.

- **Added** `core/cashfree_gst.py` — `lookup_gstin()` calls the provider's GSTIN
  endpoint and normalises the response to `company_name`, `trade_name`,
  `address`, `state`, `pincode`, `status` (plus `state_code`/`pan`). Bounded HTTP
  timeout with exponential-backoff retry on transient 5xx/network errors; typed
  error categories (`GstProviderNotConfigured` / `GstProviderAuthError` /
  `GstinNotFound` / `GstProviderUnavailable`) surfaced to users as clear
  messages. Logs only error *types* — never headers, credentials, or response
  bodies.
- **Added** `POST /api/customers/fetch-gstin` (in `routers/sales.py`, any
  authenticated user). Validates the GSTIN format **before** any network call;
  serves from a 30-day **DB cache** (`gstin_cache` collection) to avoid duplicate
  provider calls; logs every provider failure to `verification_logs`
  (`type: "GST_FETCH"`) for troubleshooting. Returns the normalised JSON with a
  `cached` flag. Falls back to demo data tagged `source: "mock"` with a `notice`
  when credentials are absent, so the UI/tests keep working in dev.
- **Config** — credentials are read **only** from env (`CASHFREE_CLIENT_ID`,
  `CASHFREE_CLIENT_SECRET`; optional `CASHFREE_GST_BASE_URL` /
  `CASHFREE_GST_PATH`). Never hardcoded, never stored in Mongo, never sent to the
  frontend.
- **Frontend** — `pages/Customers.jsx` "Fetch Details" button calls the new
  endpoint, shows loading → success/cached/error toasts, and auto-fills the
  (editable) Legal name, Trade name, Address, State, **Pincode** (new field), and
  GST status. Format is pre-checked client-side to skip pointless requests.
- **Model** — added `pincode` to the `Customer` model so the fetched pincode
  persists on save.
- **Tests** — `test_verifications.py::test_fetch_gstin_endpoint` covers 401 when
  unauthenticated, 400 on bad format, the full normalised shape on success, a
  field-allowlist guard (no credential/source leakage), employee access, and
  cache-hit on the second call. Full suite: 7 passed.

## GSTIN auto-fill via IRP (real lookup when configured)

The GST verification endpoint always returned hardcoded demo data, so enabling
the GST API key never fetched the real company name/address for a GSTIN.

- **Added** `lookup_gstin()` in `core/irp_einvoice.py` — calls the NIC e-invoice
  GSTIN-detail endpoint and returns legal/trade name, address, status, etc.
- **`/verifications/gst/validate`** now performs a real IRP lookup when the IRP
  is configured (`IRP_BASE_URL` set) and `IRP_USERNAME`/`IRP_PASSWORD` are
  present in the environment. Otherwise it returns demo data tagged
  `source: "mock"` with a `notice`, so demo values are never mistaken for real
  GST records.
- **Config** — IRP `base_url` and GSP `client_id`/`client_secret` are read from
  env (`IRP_BASE_URL`, `IRP_CLIENT_ID`, `IRP_CLIENT_SECRET`); never hardcoded.
  Credentials (`IRP_USERNAME`/`IRP_PASSWORD`) are env-only — never in source,
  never editable from the admin UI.
- **Provider-independent hardening** (works regardless of the eventual GSP auth
  flow): 24h in-process GSTIN result cache; bounded HTTP timeout with
  exponential-backoff retry on transient 5xx/network errors; typed error
  categories (`IRPNotConfigured` / `IRPAuthError` / `GstinNotFound` /
  `IRPUnavailable`) surfaced to users as clear messages; and a `check_auth()`
  health helper that verifies authentication separately from lookup. The IRP
  path logs only error *types* — never headers, tokens, password, or responses.
- **Health endpoint** — `GET /verifications/gst/health` (admin-only) answers one
  question: can the backend authenticate with the configured GST provider right
  now? It does NOT perform a GSTIN lookup. Returns a sanitized status
  (`configured`/`authenticated`/`provider`/`environment`/`last_checked_at`, or an
  `error` string) — never client_id/secret, username, token, or URL. Uses an
  8s auth timeout and caches the result for 45s. Settings → Verification API
  Settings now has a **Test Connection** button showing 🟢 Connected /
  🟡 Not configured / 🔴 Authentication failed, with admin-only detail.
- **Tests** — `tests/test_gst_health.py` covers the health contract fully
  offline (auth round-trip patched; no server/Mongo/network): not-configured,
  missing creds, auth success, auth failure, cache hit (skips re-auth), force
  bypass, >timeout handling, response-schema-no-drift, and a secret-leakage
  guard asserting client_id/secret/username/password/token/base_url never
  appear in any key or value. 8 tests, ~2.5s.
- **Deferred** — the NIC public-key/AES password-encryption handshake is NOT
  implemented; it varies by GSP and will be wired once the provider's API docs
  / Postman collection are available, to avoid speculative rework.

## Durable local object storage (logo / image uploads)

Uploaded images (company logo, product images) disappeared from the frontend
preview and PDF invoices after a server restart.

- **Root cause** — the fallback storage in `core/storage.py` kept object bytes
  in a per-process in-memory dict. It was lost on every restart, so
  `/files/{path}` and PDF logo loads returned "not found".
- **Fix** — `core/storage.py` is now a plain local-filesystem store. Objects are
  written under `LOCAL_STORAGE_DIR` (default `backend/uploads/`, gitignored) with
  a `.meta.json` sidecar for content type, durable across restarts. Path
  traversal is rejected. The hosted Emergent object-storage backend (and the
  `EMERGENT_LLM_KEY` it required) has been removed entirely — the app no longer
  depends on any external storage service or key.
- **Company branding on PDFs** — `build_doc_pdf` / `build_pi_pdf` /
  `build_ewaybill_pdf` / `build_jobwork_pdf` now render the configured company
  logo and name (resolved from the active company profile) in the document
  header, replacing the previously hardcoded "GRAVITYONE ERP" text.

> **⚠️ Action required after upgrade:** logos and product images uploaded
> *before* this fix were only ever held in volatile memory and are permanently
> gone. **Re-upload the company logo** (Company Master → Company Logo) and any
> affected product images once after deploying. They will persist from then on.

---

## Migration fixes — collMod guard on fresh databases

Migrations 002–005, 007–012 called `db.command({"collMod": ...})` directly on
collections that don't exist yet on a fresh database, producing `"ns does not
exist"` (NamespaceNotFound) errors. Migration 001 already had the correct pattern
via a `_set_validator` helper that creates the collection first.

- **Shared helper** — `migrations/__init__.py:collmod_safe()` checks whether the
  collection exists and calls `create_collection` before `collMod`, matching the
  approach used by migration 001.
- **10 migrations updated** — 002 (fixed_assets), 003 (payroll), 004 (banking),
  005 (approvals), 007 (pricing), 008 (portal), 009 (projects), 010 (pos),
  011 (integration), 012 (branches) — all `db.command({"collMod": ...})` calls
  replaced with `collmod_safe()`.

All 12 migrations now pass cleanly on startup with no warnings.

---

## API conventions — Phase 2 (extend pagination + /api/v1 aliases)

Extends the Phase 1 API conventions to the remaining high-volume router groups.

- **Shared pagination helper** — `core/utils.py:paginated_list()` returns the
  standard `{total, page, items}` envelope with search, equality filters, date
  ranges, and clamped page/limit (page≥1, 1≤limit≤200). Backward-compat: bare
  array returned when no paging params are supplied. The existing `crud_list()`
  continues unchanged for internal callers.
- **Purchase v2 pagination** — all 5 list endpoints (`/vendors`, `/orders`,
  `/grns`, `/bills`, `/returns`) now accept `page`/`limit`/`from_date`/`to_date`
  and return the standard envelope when paginated. Back-compat preserved.
- **Inventory v2 pagination** — all 6 master list endpoints (`/units`,
  `/godowns`, `/items`, `/batches`, `/serials`, `/transfers`) now accept
  `page`/`limit`/`from_date`/`to_date` and return the standard envelope.
- **/api/v1 aliases** — all ~40 router groups (accounting, ledger, inventory_v2,
  purchase_v2, HR, banking, vouchers, etc.) are now mounted under `/api/v1/*`
  in addition to `/api/*`, using the same router objects. Zero duplication.
- **Gap analysis** — `memory/phase-2-gap-analysis.md` documents the full audit
  of every router's pagination status, response formats, and deferred items.

Tests: `test_pagination_phase2.py` +17 — paginated_list helper envelope/clamping/
backward-compat/search/date-range, purchase v2 pagination (5 endpoints),
inventory v2 pagination (6 endpoints), cross-collection pagination.

Deferred (documented in gap analysis): Zod schemas, analytical report pagination
(trial-balance/P&L/balance-sheet/day-book are aggregate computations — would
produce wrong results if truncated), HR pagination, search parameter
standardisation, masters envelope format alignment.

---

## API conventions — Phase 1 (foundation masters: pagination + /api/v1)

Phase 1 of the API/frontend-conventions build. The 8 foundation masters (Group,
Ledger, Unit, Location, StockGroup, StockCategory, StockItem, GstClassification)
already had models + indexes + tenant-scoped CRUD + tests + a reusable CRA
master scaffold; this phase adds the missing API conventions.

- **Server-side pagination/filter/search** — `masters_list_paginated()` returns
  `{items, total, page, limit, pages}` with search, equality filters, and an
  inclusive date range; page/limit clamped (page≥1, 1≤limit≤200 — never trust the
  client). Wired into all 8 Phase-1 list endpoints via optional `page`/`limit`/
  `from_date`/`to_date` params. Back-compat: endpoints still return a bare array
  when no paging is requested, so the existing MasterScreen keeps working (it now
  also tolerates the `{items}` envelope).
- **/api/v1 alias** — masters + vouchers are also mounted under `/api/v1/*` (same
  router objects) in addition to the existing `/api/*` paths; nothing breaks.
- Frontend: kept the existing CRA config-driven `MasterScreen` (covers all 8) per
  the established stack — no Next.js. Zod mirroring deferred (documented).

Tests: `test_masters.py` +5 — pagination envelope/slicing, untrusted-input
clamping, tenant scoping, search filters total, soft-deleted excluded. Maintained
subset 113 passing, 2 skipped (replica-set txn tests).

Deferred to later phases (per the build plan, stop-after-each): Zod schemas,
voucher entry screen with dynamic line grids, Phases 2–8.

---

## Voucher engine — payroll posting + replica-set transactional tests

- **Payroll posting** — `payroll` now posts a balanced salary journal (Dr
  Salaries & Wages; Cr PF / ESI / PT / TDS payables; Cr net Salary Payable) from
  accounting_lines, idempotent and reversible. `attendance` is an explicit
  no-post source document (payable days / piece-rate). **All 34 parent_types are
  now implemented — nothing remains gated.**
- **Replica-set scaffolding** — `docker-compose.mongo-rs.yml` (single-node rs0)
  + `test_txn_rollback_integration.py`: proves the app's transactional write+audit
  path (`core.utils._write_with_audit`) **rolls back the business write when the
  audit insert fails inside the transaction**. Skips unless `MONGO_URL` is a
  replica set — closing the previously-documented gap once infra is available.

Tests: `test_payroll_posting.py` (5) — balanced salary JE, idempotent,
unbalanced rejected, reversal mirrors, attendance posts nothing. Maintained
subset 108 passing; +2 transactional-rollback tests skip until a replica set runs.

---

## Voucher engine — manufacturing, transfers, reconciliation, concurrency proof

Four milestones over the posting engine (each its own commit):

- **stock_journal (BOM)** — consume components (outward, engine-priced) → produce
  finished goods with cost rolled up from consumed value / produced qty; supports
  inter-godown moves. `core/voucher_engine._post_stock_journal`.
- **Inter-unit transfers** — `stock_transfer_interunit` / `_material_interunit`:
  stock out of source + in to destination, cost carried at the outward rate;
  `taxable_supply` flagged when `statutory.gst` present (different GSTIN), internal
  at cost otherwise. `InventoryLine.to_location_id` / `role` added.
- **Automated reconciliation engine** — `run_reconciliation(rules?)` advances
  posted → reconciled: `order_fulfilment` (order fully fulfilled by posted
  downstream docs) and `grn_to_bill` (receipt matched by a posted purchase bill).
  Idempotent, evidence recorded per match. `POST /run-reconciliation`.
- **Real-DB concurrency tests** — `test_concurrency_integration.py` runs against a
  live MongoDB: 20 racing inserts of the same movement key → exactly 1 survives
  (unique index `uniq_voucher_stock_movement`), and a concurrent engine post yields
  a single movement. Skips cleanly when no DB is reachable.

All 13 inventory parent_types now post; only payroll remains gated (deferred to
routers/payroll.py). Documented gap: transactional write+audit *rollback* needs a
replica set (local Mongo is standalone) — covered by app-level compensation + the
unique index, not a server transaction.

Maintained unit subset + integration: 102 passing.

---

## Voucher engine — document posting lifecycle + inventory/order handlers

Enables the operational flows: inventory posting, order fulfilment, job-work
issue→receipt→reconciliation, reversal, all on the unified voucher engine.

### Lifecycle
- States: draft → pending → approved → **posted** → **reconciled**, with
  **cancelled** as the reversal terminal. Approval now posts then advances to
  `posted` when movements/journal were written (orders that post nothing stay
  `approved`). New endpoints: `/{id}/reconcile`, `/{id}/reverse`.

### Inventory posting handlers (now `implemented=True`)
- receipt_note / material_in / rejections_in → **stock in**; delivery_note /
  material_out / rejections_out / non_returnable_gate_pass → **stock out**;
  job_work_challan → **WIP out**; job_work_material_inward → **WIP/FG in**;
  physical_stock → **signed adjustment**. Each posts signed StockLedgerEntry rows
  via the existing stock ledger (FIFO/WA valuation reused).
- Still deferred (gated 501): stock_journal (BOM), interunit transfers, payroll.

### Non-negotiables
- **Idempotent**: posting dedups on (source_doc_type='voucher', source_doc_id);
  re-posting is a no-op. Backed by a unique index `uniq_voucher_stock_movement`
  so duplicate inventory movements are impossible even under concurrent posting.
- **Reversible**: `reverse_posting()` posts opposite-sign stock movements +
  mirrors the journal (Dr↔Cr), idempotent, audited, with a reversal reference.
- **Auditable**: `voucher_journal_entry_id` doc→voucher ref; every post/reverse
  writes an audit record.
- **Posted-only**: order fulfilment and job-work reconciliation count only
  `posted` documents; inventory valuation reads posted movements only.

### Order fulfilment
- `order_fulfilment()` now reports `pending_qty`, `backorder_qty`,
  `over_fulfilled_qty`, `has_backorder` — partial fulfilment + backorder, SO
  dispatch / PO receipt tracking via the links chain.

### Tests (11) — `test_voucher_posting_lifecycle.py`, all pass
- receipt→stock-in, dispatch→stock-out; repeated + concurrent post idempotent
  (single movement); reversal nets stock back + mirrors JE (idempotent);
  job-work issue→receipt→reconciliation closed; partial fulfilment + backorder;
  fulfilment/recon ignore un-posted docs; valuation uses posted movements only.
- Updated cross-cutting + engine tests to the posted-only lifecycle.

Backend suite: 88 passing.

---

## Voucher engine — cross-cutting rules

Adds the cross-cutting behaviours over the unified voucher engine.

### Added — backend
- `core/voucher_numbering.py`: voucher_no generated per VoucherType config —
  honours `numbering_method` (auto / manual / none), `prefix`/`suffix`, and
  `restart_rule` (never / yearly / monthly). Sequences are allocated atomically
  via a per-key counter (db.voucher_counters, find_one_and_update), unique per
  **(tenant_id, voucher_type_id, financial_year[, period])**; manual numbers are
  uniqueness-checked (409 on dup); a unique DB index backstops it. Wired into
  voucher create (replaces the old count-based numbering).
- `core/voucher_engine.py` cross-cutting helpers:
  - `order_fulfilment()` — fulfilled vs pending qty per item from the links chain
    (delivery/GRN/invoice reference their order); `fully_fulfilled` flag.
  - `job_work_reconciliation()` — out-challan vs material-inward pending qty with
    §143 return-window alerts (inputs 1yr / capital goods 3yr → `deemed_supply` /
    `due_soon` / `open` / `closed`); `itc04_data()` extract (goods sent/received).
  - `statutory_je_filter()` / `management_je_filter()` — statutory reports (trial
    balance, GST ledgers) exclude reversing + memorandum (reports_only / tag);
    management reports include them. `reporting_date()` + cutoff use
    `effective_date` when set, else `date`.
- `routers/voucher_engine_router.py`: endpoints `/orders/{id}/fulfilment`,
  `/job-work/reconciliation`, `/job-work/itc-04`; numbering unique index +
  effective_date index in startup.
- `core/voucher_models.py`: `VoucherCreate.voucher_no` (for manual numbering).

### Tests (13) — `test_voucher_cross_cutting.py`, all pass
- Numbering: sequential+unique, yearly/monthly restart, manual required+dedup
  (409), method "none" → no number, tenant-isolated counters.
- Order fulfilment pending-qty (partial + complete).
- Job-work return window: breach → deemed_supply; recent+returned → closed.
- Statutory filter excludes reversing/memorandum; effective_date drives cutoff.

Backend suite: 77 passing.

---

## Unified Voucher engine (skeleton + accounting posting)

A single `vouchers_v2` collection + posting-rules engine for the full ~35
parent_type catalog, with maker-checker. **Scope this phase (agreed with user):**
accounting types post for real; inventory/order/payroll types are catalogued and
validated but posting is deferred (gated, never silently no-op). Coexists with the
legacy `/vouchers` router; existing stock_ledger / job_work / payroll modules
remain the source of truth for their domains until those handlers ship.

### Added — backend
- `core/voucher_models.py`: unified Voucher document — accounting_lines,
  inventory_lines, links (order→delivery→invoice chain), statutory blocks
  (gst/tds/tcs/eway/einvoice{irn,ack_no}), attachments. Pydantic v2, tenant-ready.
- `core/voucher_engine.py`: 34-type `CATALOG` (category + posts_to_books /
  posts_to_stock / implemented flags); validation (balanced Dr=Cr, contra-no-GST);
  posting-rules registry with handlers. Accounting handlers post a balanced,
  idempotent journal entry from accounting_lines. `memorandum` never posts;
  `reversing_journal` posts a reports-only entry + `auto_reverse_due()` sweep that
  mirrors it on the effective date. `post_voucher()` raises **501** for
  not-yet-implemented types so they can't be approved-as-posted.
- `routers/voucher_engine_router.py`: `/voucher-engine` — maker-checker lifecycle
  (create→draft, submit→pending, approve→approved+POST, cancel→soft-cancel),
  list/get/types, `run-reversing-journals`. Approval requires a distinct approver
  privilege; approved vouchers are immutable (must be reversed, not edited/cancelled).
  Tenant-scoped, audited; compound `(tenant_id, ...)` indexes; wired into server.

### Tests (10) — `test_voucher_engine.py`, all pass
- Accounting voucher posts a balanced, tenant-stamped journal entry; posting is
  idempotent (no double-post on re-approval).
- `memorandum` never posts; unbalanced lines rejected; contra rejects GST.
- `reversing_journal` posts reports-only and auto-reverses exactly once on due
  date (mirror swaps Dr/Cr).
- Not-implemented types are gated (501); posted entries carry the right tenant.

### Deferred (clearly flagged, not faked)
- Inventory/order/payroll posting handlers (delivery_note, GRN, stock_journal,
  job_work_challan §143/ITC-04, interunit transfer, payroll PF/ESI/PT/TDS, order
  fulfilment tracking). Each is in the catalog as `implemented=False`.
- Statutory automation (live e-invoice IRN generation, e-way bill API, GSTR
  filing) — the document carries the fields; integrations are later phases.
- No frontend for the voucher engine yet (backend + engine only this turn).

---

## Statutory Masters & Details

Extends the Masters subsystem with Indian statutory masters, reusing the same
tenant-scoped / audited / soft-delete foundation.

### Added — backend
- `core/masters_models.py`: list masters — GstRegistration, GstClassification,
  TdsNatureOfPayment, TcsNatureOfGoods; singletons — CompanyGstDetails,
  TdsDetails, TcsDetails, PanCinDetails.
- `core/masters_crud.py`: `singleton_get()` / `singleton_upsert()` — one document
  per tenant, get + upsert only (no list, no delete), partial-merge, audited.
- `routers/masters.py`: CRUD for the 4 statutory list masters + get/upsert for
  the 4 singletons (24 new endpoints, 64 total). New collections indexed with
  compound `(tenant_id, id)`; singletons indexed unique on `tenant_id` alone.

### Added — frontend
- `config/mastersConfig.js`: configs for the 4 list masters + a `SINGLETONS` map.
- `components/SingletonMaster.jsx`: single-form get+upsert screen (no list).
- `pages/MastersPage.jsx` dispatches list vs singleton by route key; new
  STATUTORY sidebar section (8 links).

### Tests (5 new, 14 in test_masters.py) — all pass
- Singleton: empty-get, upsert creates, idempotent partial-merge (one doc per
  tenant), tenant isolation, audited.
- Statutory list master: create + cross-tenant isolation.

---

## Masters & Voucher Types subsystem

Implements the Tally-style Masters subsystem (10 entities) on the repo's real
stack (FastAPI + MongoDB + CRA/JSX), adapted from a prompt that assumed
Next.js/TS/React-Query (absent here) and app-wide multi-tenancy (does not exist).
Frontend stack and tenancy approach chosen with the user.

### Added — backend
- `core/tenant.py`: single-source tenant resolution + `tenant_filter()` /
  `stamp_tenant()`. Masters are **tenant-ready**: every doc carries `tenant_id`,
  every read/write is scoped, defaulting to a `"default"` tenant until real
  multi-tenant auth lands (only `resolve_tenant()` changes then).
- `core/masters_crud.py`: shared CRUD enforcing the four non-negotiables —
  `tenant_id` on every doc, audit on every create/update/delete (reuses
  `log_audit`), **soft-delete only** (`is_deleted`/`deleted_at`, never hard
  delete), and tree-parent validation (same-tenant, no self/cycle).
- `core/masters_models.py`: Pydantic v2 models for Group, Ledger, Currency,
  RateOfExchange, VoucherType, StockGroup, StockCategory, StockItem, Unit,
  Location (+ partial *Update models).
- `routers/masters.py`: 40 endpoints (10 entities × CRUD) under `/masters`,
  RBAC-guarded; cross-reference + base-currency + compound-unit validation;
  `create_masters_indexes()` builds compound **(tenant_id, id)** unique indexes
  (tenant_id first) on every masters collection, wired into server startup.

### Added — frontend (CRA + JSX, reuses ui-kit)
- `components/MasterScreen.jsx`: one generic, config-driven list/create/edit/
  soft-delete screen (search, refs, conditional fields, offline-aware).
- `config/mastersConfig.js`: declarative field/column config for all 10 masters.
- `pages/MastersPage.jsx` + route `/masters/:key`; new MASTERS sidebar section.

### Tests (9, all pass) — `test_masters.py`
- **Tenant isolation** — a query as tenant A returns zero tenant-B rows; cross-
  tenant get returns 404. (Closes the DoD tenant-isolation gap for Masters.)
- Soft-delete sets the flag + hides from lists (doc never physically removed);
  cannot delete a parent with children.
- Audit written on create/update/delete (before/after captured).
- Tree validation: parent must exist in same tenant; self-parent rejected;
  unique name enforced per-tenant (same name allowed across tenants).

### Notes / still deferred
- Tenancy is enforced for **Masters collections only**; app-wide multi-tenancy
  (tenant_id on all legacy collections + auth-injected tenant context) remains a
  future enhancement. `resolve_tenant()` defaults to `"default"` today.
- Frontend verified by `craco build`, not click-tested against a live backend.

---


## Phase 1 — Foundation: Inventory + Purchase + Audit (adapted to FastAPI/MongoDB)

The work order assumed NestJS/Postgres/RLS; this repo is **FastAPI + MongoDB,
single-tenant**. Work was adapted to the real stack (see `PLAN.md`). All new
backend tests pass (**34**); the frontend `craco build` compiles clean.

### Added — Audit trail (cross-cutting)
- `core/utils.py`: append-only audit rows with full schema (`entity_type`,
  `entity_id`, `before_json`, `after_json`, `changed_fields`, `ip`, nullable
  `tenant_id`; legacy aliases retained). `_write_with_audit` makes the business
  write + audit insert atomic — a real Mongo transaction when the server
  supports it, else a compensating rollback so a change can never persist
  un-audited. `crud_create/update/delete` route through it.
- `routers/audit.py`: read-only `GET /audit-log` (filter by entity/user/action/
  date), tenant-scoped, RBAC-guarded to admin/auditor. No write routes.
- `backend/AUDIT.md`: design + the honest gap (Mongo has no per-collection
  REVOKE; DB-level immutability is a deployment control).

### Added — Inventory v2 (Tally-style stock ledger), under `/inventory/v2`
- `core/inventory_models.py`: UnitOfMeasure (UQC + compound units), StockItem
  (HSN/SAC, valuation method, reorder/min/max, batch/serial/expiry flags),
  Godown (nestable), Batch, SerialNumber, StockTransfer.
- `core/stock_valuation.py`: pure, pluggable **FIFO** (cost layers) and
  **Weighted-Average** strategies + `value_movements` dispatch.
- `core/stock_ledger.py`: append-only StockLedgerEntry posting; outward moves
  priced by the engine, scoped per godown; `on_hand()` derives qty/value.
- `routers/inventory_v2.py`: CRUD for units/godowns/items/batches/serials;
  `/adjust`; `/transfers` (paired out/in); reports — stock-summary,
  movement-analysis, stock-aging (FIFO-layer buckets), low-stock.

### Added — Purchase v2 (PO → GRN → Bill → Return), under `/purchase/v2`
- `core/purchase_models.py`: Vendor master, PurchaseOrderV2 (DRAFT → SENT →
  PARTIALLY_RECEIVED → RECEIVED → CLOSED/CANCELLED), GRNV2, PurchaseBill (TDS,
  GRN/PO linkage), PurchaseReturn/DebitNote.
- `core/ledger_posting.py`: `post_purchase_bill_journal` (Dr Inventory + Input
  GST, Cr TDS Payable, Cr Accounts Payable) and `post_purchase_return_journal`
  (the reverse). Both idempotent; reuse the existing accounting module.
- `routers/purchase_v2.py`: Vendor CRUD; PO lifecycle with received-qty rollup;
  GRN posts inward stock; Bill posts the voucher + `/bills/{id}/match`
  three-way compare; Return posts outward stock + reversing voucher; GRN
  over-receipt block/warn via `/purchase/v2/settings`.

### Added — Frontend (React, reuses existing design system)
- Screens: StockItems, Godowns, StockTransfers, Vendors, PurchaseOrdersV2,
  GRNs, PurchaseBills, PurchaseReturns, InventoryReports (tabbed).
- `hooks/useOnline.js` + `components/OfflineBanner.jsx`: online-only screens
  with an offline indicator that disables writes.
- Wired routes (`App.js`) and nav (`Sidebar.jsx`).

### Changed
- Phase-1 realignment: GRN / PO-receive no longer auto-post the accounting
  journal — goods receipt moves stock only; the **Purchase Bill** creates the
  vendor liability (correct accrual). Legacy `post_purchase_journal` retained
  but no longer called.
- Job Work "Generate Challan" modal (`JobWork.jsx`): searchable product picker
  (name/SKU/available qty, loading + "no products found" states), custom-product
  entry (name/description/UoM/quantity/remarks), Description column,
  `[+ Add Existing] [+ Add Custom]` buttons. Existing payload field names and
  challan flow preserved.

### Tests (34 passing)
- `test_stock_valuation.py` (9) — FIFO closing 300 / WA closing 260 on a mixed
  sequence, blended outward rates, oversell flagged, edge cases.
- `test_stock_ledger_service.py` (3) — same closing values through the DB path +
  per-godown FIFO isolation.
- `test_audit_trail.py` (7) — atomic write+audit, rollback on audit failure,
  changed-field diff, append-only/immutability.
- `test_purchase_bill_posting.py` (6) — balanced voucher (intra/inter-state GST),
  TDS splitting payable, idempotency, return reversal, CoA-unseeded skip.
- `test_rbac_guards.py` (9) — inventory/purchase/audit guards accept the right
  roles/permissions and 403 the rest.

### Known gaps / not done
- **Tenant isolation** — not implemented or tested; the app is single-tenant on
  MongoDB (no `tenant_id` scoping, no RLS). Cannot be tested until multi-tenancy
  is built. The DoD item is **not met** and is flagged rather than faked.
- Report **endpoints** are validated at the valuation-engine level, not via live
  HTTP integration tests (no running server/Mongo here).
- Frontend verified by build only, not click-tested against a live backend.
- Two purchase/inventory stacks coexist (legacy flat + v2 ledger); legacy
  retirement and a data backfill migration are deferred.

### Infrastructure
- `.gitignore`: exclude `mongodb_data/` (live DB files) and `scratch_test.py`.

### Deferred to a future phase (see PLAN.md → "Remaining items")
- **Multi-tenancy & tenant isolation** — future enhancement. Requires
  `tenant_id` on all business collections, tenant context in auth + every query,
  and an isolation test. Not started (single-tenant today).
- **Report endpoint integration tests** — live HTTP tests for
  `/inventory/v2/reports/*` and the purchase posting routes.
- **Legacy stack retirement + data backfill** from the flat model to v2.
