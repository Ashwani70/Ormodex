# Changelog

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
