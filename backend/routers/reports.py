import asyncio
from datetime import datetime, timedelta, timezone
from typing import cast

from fastapi import APIRouter, Depends

from core import cache
from core.auth_utils import get_current_user
from core.db import db

router = APIRouter(tags=["reports"])

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _num(value) -> float:
    """Coerce a possibly-null/blank column value to a float.

    After the Postgres migration, every column is present in the row dict, so a
    nullable numeric column comes back as ``None`` (not a missing key). A bare
    ``float(row.get("total", 0))`` then raises ``TypeError`` because ``.get``'s
    default only fires on a *missing* key. This helper maps None/""/garbage → 0.0.
    """
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_dt(value):
    """Best-effort ISO parse; returns a date or None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except Exception:
            return None


def _pct_change(current: float, previous: float) -> float:
    """Period-over-period % change. 0 when there's no prior baseline."""
    if previous == 0:
        return 0.0
    return round((current - previous) / previous * 100, 1)


def _expense_from_entries(entries, accounts):
    """Expense total from POSTED journal lines on EXPENSE-type accounts
    (debit − credit), per the P&L convention. The ledger is the only source
    for expenses, so the dashboard reads them from here."""
    expense = 0.0
    for e in entries:
        for line in (e.get("lines") or []):
            if accounts.get(line.get("account_code"), {}).get("account_type") == "EXPENSE":
                expense += _num(line.get("debit")) - _num(line.get("credit"))
    return round(expense, 2)


# Cash/bank account codes from the default chart-of-accounts seed
# (accounting.py: "Cash in Hand", "Bank Account - Primary", "Petty Cash").
# There's no account_type of "CASH"/"BANK" in this schema (only ASSET/
# LIABILITY/EQUITY/INCOME/EXPENSE), so — same as /accounting/cash-flow —
# cash balance is identified by these specific codes, not by account_type.
CASH_ACCOUNT_CODES = {"1001", "1002", "1003"}


def _cash_from_entries(entries):
    """Net movement (debit − credit) on cash/bank accounts across ALL POSTED
    journal lines — mirrors _expense_from_entries but filters by account code
    instead of account_type, matching /accounting/cash-flow's definition."""
    net = 0.0
    for e in entries:
        for line in (e.get("lines") or []):
            if line.get("account_code") in CASH_ACCOUNT_CODES:
                net += _num(line.get("debit")) - _num(line.get("credit"))
    return round(net, 2)


@router.get("/dashboard/summary")
async def dashboard_summary(_: dict = Depends(get_current_user)):
    # The dashboard fans out ~9 cross-region reads (~2.3s cold). It's the same
    # for every user (single tenant) and tolerates being a few seconds stale, so
    # cache the whole computed payload briefly. Single-flight in get_or_set means
    # a concurrent refresh burst (multiple tabs / a re-login) runs the compute
    # ONCE; everyone else awaits that result instead of stampeding the DB.
    return await cache.get_or_set(
        "dashboard:summary", cache.TTL_DASHBOARD, _compute_dashboard_summary
    )


async def _compute_dashboard_summary() -> dict:
    from sqlalchemy import text
    from core.db import AsyncSessionLocal

    today = datetime.now(timezone.utc).date()
    six_months_ago = (today - timedelta(days=180)).isoformat()
    cur_start = today - timedelta(days=30)
    prev_start = today - timedelta(days=60)
    today_plus_1 = today + timedelta(days=1)

    # All queries run concurrently — each opens its own connection from the pool
    # so they don't block each other. 10 sequential round-trips (≈2.6s) become
    # 3 parallel batches (≈0.3s).
    async def _kpi_counts():
        async with AsyncSessionLocal() as s:
            r = await s.execute(text("""
                SELECT
                    (SELECT count(*) FROM products)                                        AS total_products,
                    (SELECT count(*) FROM products WHERE quantity <= low_stock_threshold)   AS low_stock,
                    (SELECT COALESCE(SUM(quantity * cost_price), 0) FROM products)         AS inv_val,
                    (SELECT count(*) FROM customers)                                       AS customers_count,
                    (SELECT count(*) FROM leads)                                           AS leads_count,
                    (SELECT count(*) FROM sales_orders)                                    AS sos,
                    (SELECT count(*) FROM sales_orders WHERE status = 'PENDING')           AS pending_sos,
                    (SELECT count(*) FROM employees)                                       AS total_employees,
                    (SELECT count(*) FROM employees WHERE status = 'active')               AS active_employees,
                    (SELECT COALESCE(SUM(COALESCE(total_amount, total, 0)), 0) FROM invoices) AS total_revenue,
                    (SELECT COALESCE(SUM(COALESCE(paid_amount, 0)), 0) FROM invoices)      AS received_revenue,
                    (SELECT count(*) FROM sales_orders
                      WHERE created_at >= :cur_start AND created_at < :today_plus_1)       AS cur_orders,
                    (SELECT count(*) FROM sales_orders
                      WHERE created_at >= :prev_start AND created_at < :cur_start)         AS prev_orders,
                    (SELECT COALESCE(SUM(COALESCE(total, total_amount, 0)), 0) FROM purchase_bills) AS purchase_total,
                    (SELECT COALESCE(SUM(COALESCE(payment_received, 0)), 0) FROM purchase_bills)    AS purchase_paid
            """), {"cur_start": cur_start.isoformat(), "today_plus_1": today_plus_1.isoformat(),
                   "prev_start": prev_start.isoformat()})
            return r.fetchone()

    async def _lead_statuses():
        async with AsyncSessionLocal() as s:
            r = await s.execute(text("SELECT status, count(*) FROM leads GROUP BY status"))
            return {row[0]: row[1] for row in r.fetchall() if row[0]}

    async def _invoices_recent():
        async with AsyncSessionLocal() as s:
            r = await s.execute(
                text("SELECT COALESCE(total_amount, total, 0) AS total, paid_amount, created_at, status FROM invoices WHERE created_at >= :six_months_ago"),
                {"six_months_ago": six_months_ago},
            )
            return [{"total": float(row[0] or 0), "payment_received": float(row[1] or 0),
                     "created_at": row[2].isoformat() if hasattr(row[2], "isoformat") else str(row[2]),
                     "status": row[3]} for row in r.fetchall()]

    async def _journal_entries():
        async with AsyncSessionLocal() as s:
            r = await s.execute(
                text("SELECT COALESCE(je_date, date) AS entry_date, lines FROM journal_entries WHERE status = 'POSTED' AND COALESCE(je_date, date) >= :six_months_ago"),
                {"six_months_ago": six_months_ago},
            )
            return [{"date": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
                     "lines": row[1]} for row in r.fetchall()]

    async def _accounts():
        async with AsyncSessionLocal() as s:
            r = await s.execute(text("SELECT code, account_type, opening_balance FROM chart_of_accounts"))
            return [{"code": row[0], "account_type": row[1], "opening_balance": _num(row[2])} for row in r.fetchall()]

    async def _cash_journal_entries():
        # Cash Balance is "as of today", not a trailing-6-months window like
        # the other journal-entries fetch above — needs every POSTED entry.
        async with AsyncSessionLocal() as s:
            r = await s.execute(text("SELECT lines FROM journal_entries WHERE status = 'POSTED'"))
            return [{"lines": row[0]} for row in r.fetchall()]

    async def _low_stock_list():
        async with AsyncSessionLocal() as s:
            r = await s.execute(text(
                "SELECT name, sku, quantity, low_stock_threshold FROM products "
                "WHERE quantity <= low_stock_threshold ORDER BY quantity ASC LIMIT 8"
            ))
            return [{"name": row[0], "sku": row[1],
                     "quantity": float(row[2] or 0), "low_stock_threshold": float(row[3] or 0)}
                    for row in r.fetchall()]

    # Fire all 7 queries in parallel — one pool connection each. asyncio.gather's
    # typeshed overloads only preserve per-argument return types up to 6
    # positional futures; a 7th collapses everything to a homogeneous union
    # and breaks pyright's inference below. Keep the well-typed 6-arg gather
    # and run the 7th (_cash_journal_entries) alongside it via gather() too,
    # so it still executes concurrently — just unpacked from its own call.
    (kpis_row, lead_status_counts, invoices, entries, accounts_raw, low_list), (cash_entries,) = await asyncio.gather(
        asyncio.gather(
            _kpi_counts(), _lead_statuses(), _invoices_recent(),
            _journal_entries(), _accounts(), _low_stock_list(),
        ),
        asyncio.gather(_cash_journal_entries()),
    )

    # kpis_row is always non-None (SELECT with scalar subqueries always returns one row)
    # but fetchone() is typed Optional[Row], so index via a safe helper.
    _r = kpis_row if kpis_row is not None else [0] * 15
    total_products   = int(_r[0] or 0)
    low_stock        = int(_r[1] or 0)
    inventory_value  = round(float(_r[2] or 0), 2)
    customers_count  = int(_r[3] or 0)
    leads_count      = int(_r[4] or 0)
    sos              = int(_r[5] or 0)
    pending_sos      = int(_r[6] or 0)
    total_employees  = int(_r[7] or 0)
    active_employees = int(_r[8] or 0)
    total_revenue    = round(float(_r[9] or 0), 2)
    received_revenue = round(float(_r[10] or 0), 2)
    outstanding      = round(total_revenue - received_revenue, 2)
    cur_orders       = int(_r[11] or 0)
    prev_orders      = int(_r[12] or 0)
    purchase_total   = round(float(_r[13] or 0), 2)
    purchase_paid    = round(float(_r[14] or 0), 2)
    payables         = round(purchase_total - purchase_paid, 2)
    open_leads       = sum(lead_status_counts.get(s, 0) for s in ("NEW", "CONTACTED", "QUOTED"))

    # Cash Balance = opening balance of cash/bank accounts + net (debit −
    # credit) of every POSTED journal line against those same accounts,
    # as-of-today — same definition /accounting/cash-flow uses.
    cash_opening = round(sum(
        a["opening_balance"] for a in accounts_raw if a["code"] in CASH_ACCOUNT_CODES
    ), 2)
    cash_balance = round(cash_opening + _cash_from_entries(cash_entries), 2)

    by_month = {}
    for inv in invoices:
        ca = inv.get("created_at")
        if not ca:
            continue
        try:
            dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
            key = dt.strftime("%Y-%m")
            by_month[key] = by_month.get(key, 0) + _num(inv.get("total"))
        except Exception:
            pass
    months = sorted(by_month.keys())[-6:]
    sales_trend = [{"month": m, "revenue": round(by_month[m], 2)} for m in months]

    funnel = [
        {"status": st, "count": lead_status_counts.get(st, 0)}
        for st in ("NEW", "CONTACTED", "QUOTED", "WON", "LOST")
    ]

    # ── Income vs Expense ──
    today_date = datetime.now(timezone.utc).date()
    week_start = today_date - timedelta(days=today_date.weekday())  # Monday
    accounts = {a["code"]: a for a in accounts_raw}

    # Expense entry buckets (ledger).
    exp_week = {i: [] for i in range(7)}          # 0=Mon … 6=Sun
    exp_month = {}                                # "YYYY-MM" -> [entries]
    for e in entries:
        d = _parse_dt(e.get("date"))
        if not d:
            continue
        if week_start <= d <= week_start + timedelta(days=6):
            exp_week[d.weekday()].append(e)
        exp_month.setdefault(d.strftime("%Y-%m"), []).append(e)

    # Income buckets (invoices, by created_at).
    inc_week = {i: 0.0 for i in range(7)}
    inc_month = {}
    for inv in invoices:
        d = _parse_dt(inv.get("created_at"))
        if not d:
            continue
        amt = _num(inv.get("total"))
        if week_start <= d <= week_start + timedelta(days=6):
            inc_week[d.weekday()] += amt
        mk = d.strftime("%Y-%m")
        inc_month[mk] = inc_month.get(mk, 0.0) + amt

    ie_weekly = [
        {"label": WEEKDAY_LABELS[i],
         "income": round(inc_week[i], 2),
         "expense": _expense_from_entries(exp_week[i], accounts)}
        for i in range(7)
    ]

    # Union of months that have either income or expense, last 6.
    ie_months = sorted(set(inc_month) | set(exp_month))[-6:]
    ie_monthly = [
        {"label": m,
         "income": round(inc_month.get(m, 0.0), 2),
         "expense": _expense_from_entries(exp_month.get(m, []), accounts)}
        for m in ie_months
    ]

    # ── KPI trend deltas: current 30-day window vs the prior 30-day window ──
    cur_start = today - timedelta(days=30)
    prev_start = today - timedelta(days=60)

    def _rev_in(lo, hi):
        return round(sum(
            _num(i.get("total")) for i in invoices
            if (pd := _parse_dt(i.get("created_at"))) and lo <= pd < hi
        ), 2)

    cur_rev = _rev_in(cur_start, today + timedelta(days=1))
    prev_rev = _rev_in(prev_start, cur_start)

    trends = {
        "revenue": _pct_change(cur_rev, prev_rev),
        "orders": _pct_change(cur_orders, prev_orders),
    }

    return {
        "kpis": {
            "total_products": total_products,
            "low_stock": low_stock,
            "inventory_value": inventory_value,
            "customers": customers_count,
            "leads": leads_count,
            "open_leads": open_leads,
            "total_revenue": total_revenue,
            "outstanding": outstanding,
            "sales_orders": sos,
            "pending_orders": pending_sos,
            "active_employees": active_employees,
            "total_employees": total_employees,
            "purchase_total": purchase_total,
            "payables": payables,
            "cash_balance": cash_balance,
        },
        "sales_trend": sales_trend,
        "lead_funnel": funnel,
        "low_stock_items": low_list,
        "income_expense": {"weekly": ie_weekly, "monthly": ie_monthly},
        "trends": trends,
    }


@router.get("/diagnostics/perf")
async def perf_diagnostics(_: dict = Depends(get_current_user)):
    """Live performance counters: cache hit-rate + cumulative SQL stats.

    Lets you confirm the cache is doing its job in production (a healthy hit_rate
    on a warm process should be well above 0.5) and watch the global slow-query
    count. The SQL stats are process-cumulative since boot."""
    from core.db import query_stats
    return {"cache": cache.stats(), "sql": query_stats()}


@router.get("/reports/inventory")
async def report_inventory(_: dict = Depends(get_current_user)):
    return await db.products.find({}, {"_id": 0}).to_list(5000)


@router.get("/reports/sales")
async def report_sales(_: dict = Depends(get_current_user)):
    return await db.invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)


@router.get("/reports/profit")
async def report_profit(_: dict = Depends(get_current_user)):
    invoices = await db.invoices.find({}, {"_id": 0}).to_list(5000)
    products = await db.products.find({}, {"_id": 0}).to_list(5000)
    cost_map = {p["id"]: float(p.get("cost_price", 0)) for p in products}

    total_revenue = 0.0
    total_cost = 0.0
    rows = []
    for inv in invoices:
        rev = float(inv.get("subtotal", 0))
        cost = sum(cost_map.get(it.get("product_id"), 0) * float(it.get("quantity", 0)) for it in inv.get("items", []))
        total_revenue += rev
        total_cost += cost
        rows.append({
            "invoice_number": inv.get("invoice_number"),
            "customer_name": inv.get("customer_name"),
            "revenue": round(rev, 2),
            "cost": round(cost, 2),
            "profit": round(rev - cost, 2),
            "created_at": inv.get("created_at"),
        })
    return {
        "total_revenue": round(total_revenue, 2),
        "total_cost": round(total_cost, 2),
        "total_profit": round(total_revenue - total_cost, 2),
        "rows": rows,
    }


@router.get("/reports/audit")
async def report_audit(_: dict = Depends(get_current_user)):
    return await db.audit_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(1000)

