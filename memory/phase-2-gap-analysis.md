# Phase 2 Gap Analysis — API Standardisation Build

## Baseline (Phase 1)

Phase 1 delivered pagination/filter/search on the 8 foundation masters (`/masters/*`)
and `/api/v1` aliases for `masters_router` + `voucher_engine_router`.
Verification: 352 passed, 2 skipped (replica-set txn tests). Tag: `phase-1-api-conventions`.

---

## 1. What Already Exists

### Pagination (`{total, page, items}` envelope)
| Router | Endpoints |
|---|---|
| `vouchers.py` | `GET /vouchers` |
| `voucher_engine_router.py` | `GET /voucher-engine` |
| `accounting.py` | `GET /accounting/journal-entries` |
| `ledger.py` | `GET /ledger/bank-entries` |
| `banking.py` | `GET /banking/statements`, `/banking/cheques` |
| `expense_mgmt.py` | `GET /expenses` |
| `gst_accounting.py` | `GET /gst/records` (TDS, TCS) |
| `audit.py` | `GET /audit/logs` |
| `masters.py` | 8 list endpoints (with extra `limit` + `pages` fields) |

### Date Parameter Convention
`from_date` / `to_date` is the dominant convention, used consistently in 15+ routers.
Outlier: `hr_attendance.py` uses `date_from` / `date_to`.

### Search Parameter Convention
Two conventions coexist: `q` (crud_list/masters_list) and `search` (vouchers/accounting).

### `/api/v1` Alias
Only `masters_router` + `voucher_engine_router` are mounted under `/api/v1/*`.

---

## 2. What Is Missing (Genuinely Missing)

### A. High-Volume List Endpoints Without Pagination

**purchase_v2.py** — ALL 5 list endpoints return bare arrays:
- `GET /purchase/v2/vendors`, `/orders`, `/grns`, `/bills`, `/returns`
- No `from_date`/`to_date` support
- Risk: unbounded `.to_list(2000)`

**inventory_v2.py** — ALL 6 master list endpoints return bare arrays:
- `GET /inventory/v2/units`, `/godowns`, `/items`, `/batches`, `/serials`, `/transfers`
- Reports use `.to_list(5000)` / `.to_list(100000)` — cursor-based pagination needed

**accounting.py** — Report endpoints unchecked:
- `/general-ledger` (.to_list(1000)), `/trial-balance`, `/profit-loss`,
  `/balance-sheet`, `/day-book`, `/cash-flow`, `/interest-outstanding`
- All accept dates but return unbounded arrays

**hr_payroll.py** / **hr_attendance.py** / **hr_employees.py**:
- `/hr/payslips` (.to_list(5000)), `/hr/attendance` (.to_list(5000)),
  `/hr/employees` (crud_list -> 2000)

**budget.py** — `/budget/cost-centers`, `/budget/budgets`, `/budget/alerts`

### B. `/api/v1` Aliases Missing For All Non-Masters Router Groups
~18 router groups (accounting, ledger, inventory_v2, purchase_v2, vouchers,
banking, budget, HR routers, expense_mgmt, gst_accounting, etc.) lack `/api/v1` aliases.

### C. No Shared Pagination Helper
`crud_list()` in `core/utils.py` returns a bare array.
`masters_list_paginated()` in `core/masters_crud.py` is paginated but masters-only.
No generic paginated CRUD helper exists — each new router would inline the pattern.

### D. `/api/v1` / `public_api.py` Namespace Collision Risk
`public_api.py` already mounts at `/api/v1/...` with separate API-key auth.
Aliasing internal routers at the same prefix may cause route conflicts.

---

## 3. Changes Needed (to Avoid Duplicate Work)

### Must Do (Net-New Foundational)
1. **Create `core/utils.py:paginated_list()`** — a generic pagination helper that
   wraps the existing `masters_list_paginated` pattern for any collection.
   Backward-compatible: same signature as `crud_list()` when page=None.
   Response shape: `{total, page, items}` (standard envelope).

2. **Refactor `crud_list()`** to call `paginated_list()` when paging params are
   supplied, preserving bare-array return when they are absent.

3. **Extend `/api/v1` aliases** to all internal router groups in `server.py`,
   reusing the same router objects. Handle the `public_api.py` collision by
   keeping public_api at a separate prefix (e.g., `/api/public/v1`).

4. **Add pagination to purchase_v2.py** — all 5 list endpoints.

5. **Add pagination to inventory_v2.py** — all 6 master list endpoints.

6. **Add pagination to high-volume accounting report endpoints** —
   general-ledger, trial-balance, day-book, cash-flow.

### Should Do (Medium Priority)
7. **Add pagination to HR endpoints** — `/hr/payslips`, `/hr/attendance`,
   `/hr/employees`.

8. **Standardize date parameters** in `hr_attendance.py` (`date_from` → `from_date`).

### Deferred (Non-Blocking, Documented)
- Zod schema mirroring on frontend (documented follow-up).
- Standardize search parameter name (`q` vs `search`) — backward-compat aliases.
- Align masters envelope (`limit`/`pages` fields) — not worth breaking existing
  frontend MasterScreen.
- Legacy stack retirement (Phase 1 of PLAN.md remaining items).

---

## 4. Implementation Order (Phase 2)

| Step | Change | Tests | Priority |
|------|--------|-------|----------|
| 1 | `core/utils.py:paginated_list()` helper | unit test covering envelope, clamping, search, date range | Foundational |
| 2 | `/api/v1` aliases for all router groups | integration: each router reachable at `/api/v1/...` | Foundational |
| 3 | Paginate `purchase_v2.py` list endpoints | 3 tests per endpoint | High |
| 4 | Paginate `inventory_v2.py` list endpoints | 3 tests per endpoint | High |
| 5 | Paginate `accounting.py` report endpoints | 2 tests per endpoint | Medium |
| 6 | Paginate HR endpoints | 2 tests per endpoint | Medium |

---

## 5. Backward Compatibility Guarantees

- Bare-array return preserved when `page`/`limit` are absent.
- Existing `crud_list()` callers unchanged.
- `/api/*` paths continue to work alongside `/api/v1/*`.
- `from_alias`/`to_alias` backward-compat in accounting.py kept (but deprecated).
