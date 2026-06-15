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

Total new tests across phases: **25 passing**.

## Out of scope (explicitly not doing)

- No NestJS/Postgres/RLS. No multi-tenancy. No refactor of existing CRUD/audit helpers.
- Sales→ledger posting (symmetric gap, but not this phase).
- Supplier-invoice/bill entity (POs currently double as the payable document here).
