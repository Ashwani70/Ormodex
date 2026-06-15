# Changelog

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
