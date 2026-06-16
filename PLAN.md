# PLAN — Close the purchase→ledger accounting loop

## Reality check (why this plan differs from the work order)

The work order assumes **NestJS / TypeORM / PostgreSQL with `tenant_id` + RLS**. This repo is
actually **FastAPI (Python) + MongoDB (Motor)**, single-tenant (no `tenant_id`/`company_id`,
no RLS — and Mongo has no RLS). Inventory, purchase (incl. GRN), and the audit trail
**already exist and are wired**. So most of the work order is already done or inapplicable.

Per the user's decision ("adapt to real stack"), this phase implements only the one genuinely
missing piece the work order points at:

> "a purchase bill must post to the ledger; a GRN must move stock"

A GRN already **moves stock**. Nothing currently **posts to the ledger** on purchase — in fact
no module auto-creates journal entries today, so receiving goods is invisible to Trial Balance,
the Inventory asset, P&L, and Accounts Payable. This closes that loop, following existing
conventions (no new stack, no refactors).

## Conventions discovered (reused, not reinvented)

- Ledger primitive: `db.journal_entries`, model `JournalEntry`/`JournalLine` in
  `core/accounting_models.py`. Lines carry `account_code`, `account_name`, `debit`, `credit`.
- Reports (`/accounting/trial-balance`, `/profit-loss`, `/balance-sheet`, `/general-ledger`)
  read **only `status: "POSTED"`** entries.
- Entry numbering: `_next_entry_number(fy)` → `JE/<fy>/00001`; active fiscal year from
  `db.fiscal_years` where `is_active`.
- CoA already seeded with the accounts we need: `1200 Inventory`, `1500 GST Input Tax Credit`,
  `2001 Accounts Payable`, `5002 Purchase Expenses`.
- GST split: intra-state → CGST+SGST (each half); inter-state → IGST. Company state from
  `db.companies` (`/company/active`, `state_code`); supplier state from `supplier.state_code`.
- Audit: `core.utils.log_audit`.

## Changes

1. **`core/ledger_posting.py`** (new): one reusable helper
   `post_purchase_journal(db, *, source_collection, source_id, source_number, supplier_id,
   supplier_name, date, items, user)`.
   - Computes taxable total + CGST/SGST/IGST (intra vs inter-state via company vs supplier state).
   - Builds a balanced double entry:
     - **Dr** `1200 Inventory` = taxable value
     - **Dr** `1500 GST Input Tax Credit` = total GST (if > 0)
     - **Cr** `2001 Accounts Payable` = grand total
   - Persists as a `POSTED` journal entry with `reference = source_number`,
     `source_collection`/`source_id` for traceability.
   - **Idempotent**: keyed on `(source_collection, source_id)`; if an entry already exists it
     returns it without creating a duplicate (so PO-receive + GRN, or re-runs, can't double-post).
   - Skips silently (returns `None`) if the CoA isn't seeded, so it never breaks goods receipt.

2. **`routers/purchase.py`**: call `post_purchase_journal` from both `receive_po` and
   `create_grn` after stock is moved. Same `source_id` (the PO id) → at most one JE per PO.
   Add a `journal_entry_id` field to the response.

## Audit trail (cross-cutting) — DONE

Adapted from the NestJS/Postgres spec to FastAPI/Mongo (see `backend/AUDIT.md`):

- `core/utils.py`: enriched audit row (`entity_type`/`entity_id`, `before_json`/
  `after_json`, `changed_fields`, `ip`, nullable `tenant_id`; legacy aliases
  kept). New `_write_with_audit` makes business write + audit insert atomic —
  Mongo transaction when the server supports it, else compensating rollback.
  `crud_create/update/delete` now route through it.
- `routers/audit.py` (new): read-only `GET /audit-log` with entity/user/action/
  date filters, tenant-scoped, RBAC-guarded to admin/auditor; wired in server.py.
- `core/ledger_posting.py`: auto-created journal entries are audited too.
- `tests/test_audit_trail.py`: 7 tests proving atomic commit, rollback-on-audit-
  failure, changed-field diffing, and append-only/immutability. All pass.

Honest gap: MongoDB has no per-collection REVOKE; DB-enforced immutability is a
deployment control (restricted Mongo role + replica set), documented in AUDIT.md.

## Inventory v2 — Tally-style stock ledger — DONE

Built as a self-contained subsystem under `/inventory/v2`, coexisting with the
legacy flat Product/stock_transactions model (untouched, still used by PO/GRN/
manufacturing). Stock qty/value are always **derived** from the ledger via the
valuation engine — never stored denormalised, so they cannot drift.

- `core/inventory_models.py`: UnitOfMeasure (UQC + compound units), StockItem
  (HSN/SAC, valuation_method, reorder/min/max, batch/serial/expiry flags),
  Godown (nestable), Batch, SerialNumber, StockTransfer, adjustment/entry inputs.
- `core/stock_valuation.py`: pure, pluggable FIFO (explicit cost layers, oldest-
  first) and Weighted-Average (running avg) strategies + `value_movements`
  dispatch. No DB — fully unit-testable.
- `core/stock_ledger.py`: append-only StockLedgerEntry posting; outward moves
  priced by the engine over the item's prior history, **scoped per godown** so
  FIFO layers stay physically located. `on_hand()` derives qty/value. Audited.
- `routers/inventory_v2.py` (24 routes): CRUD for units/godowns/items/batches/
  serials; `/adjust`; `/transfers` (paired TRANSFER_OUT priced + TRANSFER_IN at
  the same cost); reports: stock-summary (opening/inward/outward/closing + per-
  godown), movement-analysis, stock-aging (FIFO-layer age buckets), low-stock.
  RBAC-guarded; wired in server.py.
- Tests (all pass): `test_stock_valuation.py` (9 — FIFO 300 / WA 260 on the
  mixed sequence + edges), `test_stock_ledger_service.py` (3 — same closing
  values through the DB path + per-godown FIFO isolation).

## Purchase v2 — PO → GRN → Bill → Return lifecycle — DONE

Built under `/purchase/v2`, aligned to accrual accounting and wired into the v2
stock ledger (Phase 2) + accounting (Phase 1). **Realignment:** Phase-1 GRN/
PO-receive no longer auto-posts the accounting journal — goods receipt moves
stock only; the financial liability is created by the Purchase Bill (correct
accrual: receipt ≠ vendor invoice). Confirmed with the user.

- `core/purchase_models.py`: Vendor (gstin/pan/state_code/payment_terms_days/
  opening_balance/billing+shipping addr), PurchaseOrderV2 (DRAFT/SENT/
  PARTIALLY_RECEIVED/RECEIVED/CLOSED/CANCELLED + per-line received_qty), GRNV2
  (godown + batch/serial/expiry lines, optional PO link), PurchaseBill
  (vendor_invoice_no/date, grn_ids, po link, TDS), PurchaseReturn/DebitNote.
- `core/ledger_posting.py`: refactored shared `_persist_journal` + `_is_interstate`;
  added `post_purchase_bill_journal` (Dr Inventory + Input GST, Cr TDS Payable,
  Cr Accounts Payable) and `post_purchase_return_journal` (the reverse). Both
  idempotent on source id; hook the existing accounting module (no duplicate
  ledger logic). Legacy `post_purchase_journal` kept but no longer called.
- `routers/purchase_v2.py`: Vendor CRUD; PO lifecycle (status transitions,
  received_qty rollup → PARTIALLY_RECEIVED/RECEIVED); GRN posts inward stock
  ledger entries; Bill posts the voucher + `/bills/{id}/match` three-way compare;
  Return posts outward stock + reversing voucher. Qty reconciliation: GRN cannot
  over-receive vs PO (block or warn per `/purchase/v2/settings` tenant toggle).
  Wired in server.py.
- Tests (6, all pass): `test_purchase_bill_posting.py` — balanced bill voucher
  (intra CGST+SGST / inter-state IGST), TDS splitting the payable, idempotency,
  return reverses the bill, graceful skip when CoA unseeded.

## Frontend (Phase 4 of work order) — DONE

10 screens reusing the existing design system (ui-kit, Modal, sonner, `@/` alias,
dark zinc/yellow theme), online-only with an offline indicator that disables
writes (the only offline mechanism in the repo is POS-local; no generic queue):
- Masters: `StockItems.jsx` (conditional batch/serial/expiry), `Godowns.jsx`
  (nesting), `Vendors.jsx`.
- Documents: `StockTransfers.jsx`, `PurchaseOrdersV2.jsx`, `GRNs.jsx`
  (per-item conditional batch/serial/expiry capture), `PurchaseBills.jsx` (TDS,
  GRN/PO linkage, live totals), `PurchaseReturns.jsx`.
- Reports: `InventoryReports.jsx` (tabbed summary / movement / aging / low-stock).
- Shared: `hooks/useOnline.js`, `components/OfflineBanner.jsx`. Wired into
  `App.js` routes and `Sidebar.jsx` nav. `craco build` compiles clean.
- Also hardened the Job Work challan modal: searchable product picker
  (name/SKU/qty, loading + "no products" states), custom-product entry
  (name/desc/UoM/remarks), Description column. `JobWork.jsx` only.

Total new tests across phases: **34 passing** (9 valuation, 3 stock-ledger
service, 7 audit, 6 purchase-bill posting, 9 RBAC guards).

## Definition of Done — honest status

- [x] **Audit trail logs every create/edit/delete atomically and cannot be
  disabled or mutated.** Done via shared `crud_*` → `_write_with_audit`
  (transaction when available, else compensating rollback); read-only RBAC
  endpoint; tests in `test_audit_trail.py`. DB-level immutability (revoke
  grants) is a deployment control documented in `backend/AUDIT.md` — Mongo has
  no per-collection REVOKE, so it can't be enforced in code.
- [x] **Stock item / godown / batch / serial masters with conditional tracking.**
  Backend `inventory_v2`, frontend forms enforce batch/serial/expiry only when
  the item tracks them.
- [x] **GRN posts inward stock; transfers move stock; valuation (FIFO + WA)
  correct and tested.** `test_stock_valuation.py` + `test_stock_ledger_service.py`
  (incl. per-godown FIFO isolation).
- [x] **PO → GRN → Bill posts to the existing accounting ledger; debit notes
  reverse.** `test_purchase_bill_posting.py` proves balanced voucher + reversal.
- [x] **Four inventory reports return correct numbers.** Reports derive from the
  same valuation engine the unit tests assert; report endpoints reuse
  `value_movements`. (Report *endpoints* are not separately integration-tested —
  see gap note below.)
- [~] **Tenant isolation and RBAC verified by tests.** RBAC: DONE
  (`test_rbac_guards.py`, 9 tests). **Tenant isolation: NOT MET** — this app is
  single-tenant on MongoDB; there is no `tenant_id` scoping or RLS to test. A
  real isolation test cannot exist until multi-tenancy is built. Flagged, not
  faked.
- [x] **PLAN.md + CHANGELOG.** This file + `CHANGELOG.md`.

### Known gaps (not done)
- **Tenant isolation** — no tenancy exists; see above.
- **Report endpoints** are proven only at the valuation-engine level, not via
  live HTTP integration tests (no running server/Mongo in this environment).
- **Frontend** verified by `craco build` only — not click-tested against a live
  backend.
- Two parallel purchase/inventory stacks now coexist (legacy flat model +
  v2 stock-ledger); legacy retirement + data backfill migration are deferred.

## Remaining items (next phase)

Carried forward and explicitly deferred from this phase:

1. **Multi-tenancy & tenant isolation — PARTIALLY DONE (Masters), rest FUTURE.**
   The **Masters subsystem is now tenant-scoped** (`core/tenant.py` +
   `core/masters_crud.py`): every masters doc carries `tenant_id`, every query is
   filtered by it, compound `(tenant_id, id)` indexes exist, and a real
   tenant-isolation test passes (`test_masters.py`). Today the tenant resolves to
   a `"default"` sentinel via `resolve_tenant()` until auth carries a tenant.
   Remaining (app-wide) work to fully close the DoD item:
   - a `tenant_id` on every business collection and on `audit_logs`;
   - tenant context threaded through auth (JWT claim → request scope) and
     injected into every `crud_*` / query filter so no read or write can cross
     tenants;
   - a test proving "a query as tenant A returns zero tenant-B rows".
   Note: MongoDB has no RLS, so isolation must be enforced in the application
   data layer (or via per-tenant databases) — there is no Postgres-style
   `REVOKE`/RLS equivalent. Tracked as a future enhancement, not a bug.

2. **Report endpoint integration tests.**
   The four inventory reports (`/inventory/v2/reports/*`) and the purchase
   posting endpoints are validated at the engine/unit level. Add live HTTP
   integration tests (running server + Mongo, or `httpx.AsyncClient` against the
   FastAPI app) asserting the JSON shape and numbers end-to-end, including
   auth/RBAC on each route.

3. **Legacy stack retirement + data backfill** (lower priority): migrate
   `suppliers`/`purchase_orders`/`products`/`stock_transactions` into the v2
   `vendors`/`purchase_orders_v2`/`stock_items`/stock-ledger collections, then
   retire the legacy routes once the frontend is fully on v2.

## Out of scope (explicitly not doing)

- No NestJS/Postgres/RLS. No multi-tenancy. No refactor of existing CRUD/audit helpers.
- Sales→ledger posting (symmetric gap, but not this phase).
- Supplier-invoice/bill entity (POs currently double as the payable document here).
