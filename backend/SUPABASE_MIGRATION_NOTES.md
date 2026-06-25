# Supabase / Postgres migration — status & known gaps

Branch: `migrate/supabase`. Data layer moved from MongoDB (motor) to Supabase
Postgres via SQLAlchemy + asyncpg, with a Mongo-style compatibility shim
(`core/_mongo_compat.py`) so the 52 router modules keep their existing calls.

## ✅ Done & verified (no live DB needed)
- `core/db.py` → SQLAlchemy async engine reading `DATABASE_URL`.
- Schema (`core/schema.py`), `utils.py` (v2, lazy imports), shim, auth, email,
  masters, seed, server applied.
- `portal_auth.py` + `stock_ledger.py` restored from the original (the codemod's
  rewrites were incomplete); their few Mongo calls run via the shim.
- All of `core`, `server.py`, and **52/52 routers import cleanly**.
- `requirements.txt`: sqlalchemy/asyncpg/alembic added, motor retired.

## ⏳ Needs a live Supabase DATABASE_URL (set in backend/.env)
1. `alembic upgrade head` — create the ~100 tables on Supabase.
2. Seed the admin user.
3. Smoke-test endpoints (login, list/create products, post a voucher).

## ⚠️ KNOWN GAP — aggregation pipelines return empty
`MongoCollectionCompat.aggregate()` in `core/_mongo_compat.py` is a STUB:

    async def aggregate(self, pipeline): return []   # always empty!

So these **read/report endpoints import & run but return zero/empty data**
(40 call sites across 9 modules). Core accounting *posting* is NOT affected
(ledger_posting.py / voucher_engine.py use no aggregates).

Affected (by call count):
- routers/mis_reports.py      (14)  — MIS dashboards / monthly rollups
- routers/ai_assistant.py     (10)
- routers/gst_accounting.py    (6)  — GST summaries
- routers/reports_engine.py    (3)
- routers/expense_mgmt.py      (3)
- routers/vouchers.py          (1)
- routers/projects.py          (1)
- routers/ledger.py            (1)
- routers/hr_payroll.py        (1)

Most pipelines are `$match` + `$group`/`$sum` (revenue/expense totals, top
customers) — mechanically translatable to SQL `SUM(...) ... GROUP BY ...`.
A few use `$unwind`/`$lookup` (line-item explosion, joins) needing more care.

### Options to close the gap
1. Implement a real `aggregate()` in the shim covering `$match/$group/$sum/
   $count/$sort/$limit/$unwind` → SQLAlchemy. Fixes most call sites centrally.
2. Rewrite each report endpoint as native SQLAlchemy queries (most robust;
   per-endpoint effort).
3. Leave reports returning empty for now, ship transactional features first.

DO NOT treat reports/dashboards as trustworthy until this is closed — a P&L or
GST report showing ₹0 looks like real data, not an error.
