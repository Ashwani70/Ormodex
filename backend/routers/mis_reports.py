"""MIS Reports Router.

Advanced analytics, KPI dashboards, Excel/PDF export.
"""
import io
import uuid
from datetime import datetime, date, timedelta
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Response

from core.auth_utils import get_current_user, require_admin
from core.db import db

router = APIRouter(prefix="/mis", tags=["MIS Reports"])


def _require_mis(user: dict):
    if user.get("role") == "admin":
        return user
    perms = user.get("module_permissions", [])
    if not any(p in perms for p in ("mis_reports", "accounting", "reports")):
        raise HTTPException(403, "MIS Reports module access required")
    return user


# ─────────────────────────── Main KPI Dashboard ───────────────────────────

@router.get("/dashboard")
async def mis_dashboard(user=Depends(get_current_user)):
    _require_mis(user)
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    year_start = today.replace(month=1, day=1).isoformat()
    prev_month_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1).isoformat()
    prev_month_end = (today.replace(day=1) - timedelta(days=1)).isoformat()

    # Current month sales
    sales_pipeline = [
        {"$match": {"created_at": {"$gte": month_start}}},
        {"$group": {"_id": None, "revenue": {"$sum": "$total"}, "count": {"$sum": 1}}},
    ]
    sales_agg = await db.invoices.aggregate(sales_pipeline).to_list(1)
    current_revenue = sales_agg[0]["revenue"] if sales_agg else 0
    sales_count = sales_agg[0]["count"] if sales_agg else 0

    # Previous month sales
    prev_sales = await db.invoices.aggregate([
        {"$match": {"created_at": {"$gte": prev_month_start, "$lte": prev_month_end}}},
        {"$group": {"_id": None, "revenue": {"$sum": "$total"}}},
    ]).to_list(1)
    prev_revenue = prev_sales[0]["revenue"] if prev_sales else 0
    revenue_growth = round(((current_revenue - prev_revenue) / max(prev_revenue, 1)) * 100, 1)

    # Current month purchases
    purchase_agg = await db.purchase_orders.aggregate([
        {"$match": {"created_at": {"$gte": month_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    purchase_total = purchase_agg[0]["total"] if purchase_agg else 0

    # Expenses
    expense_agg = await db.expense_entries.aggregate([
        {"$match": {"date": {"$gte": month_start}, "status": "APPROVED"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    expense_total = expense_agg[0]["total"] if expense_agg else 0

    # Outstanding receivables
    outstanding_agg = await db.invoices.aggregate([
        {"$match": {"status": {"$in": ["UNPAID", "PARTIAL"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}, "paid": {"$sum": "$payment_received"}}},
    ]).to_list(1)
    receivables = 0
    if outstanding_agg:
        receivables = outstanding_agg[0]["total"] - outstanding_agg[0]["paid"]

    # Active customers, suppliers
    customer_count = await db.customers.count_documents({})
    supplier_count = await db.suppliers.count_documents({})
    product_count = await db.products.count_documents({})

    # Low stock
    low_stock_count = await db.products.count_documents(
        {"$expr": {"$lte": ["$quantity", "$low_stock_threshold"]}}
    )

    # Monthly trend (last 6 months)
    trend_data = []
    for i in range(5, -1, -1):
        m_date = today.replace(day=1) - timedelta(days=i * 30)
        m_start = m_date.replace(day=1).isoformat()
        m_end = (m_date.replace(day=28) + timedelta(days=4)).replace(day=1).isoformat()
        label = m_date.strftime("%b %Y")

        m_sales = await db.invoices.aggregate([
            {"$match": {"created_at": {"$gte": m_start, "$lt": m_end}}},
            {"$group": {"_id": None, "total": {"$sum": "$total"}}},
        ]).to_list(1)
        m_exp = await db.expense_entries.aggregate([
            {"$match": {"date": {"$gte": m_start, "$lt": m_end}, "status": "APPROVED"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]).to_list(1)

        trend_data.append({
            "month": label,
            "revenue": m_sales[0]["total"] if m_sales else 0,
            "expenses": m_exp[0]["total"] if m_exp else 0,
            "profit": (m_sales[0]["total"] if m_sales else 0) - (m_exp[0]["total"] if m_exp else 0),
        })

    # Top products by revenue
    top_products = await db.invoices.aggregate([
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.product_name",
            "total_revenue": {"$sum": {"$multiply": ["$items.quantity", "$items.unit_price"]}},
            "units_sold": {"$sum": "$items.quantity"},
        }},
        {"$sort": {"total_revenue": -1}},
        {"$limit": 5},
    ]).to_list(5)

    # Top customers
    top_customers = await db.invoices.aggregate([
        {"$group": {"_id": "$customer_name", "total": {"$sum": "$total"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
        {"$limit": 5},
    ]).to_list(5)

    return {
        "kpis": {
            "current_month_revenue": round(current_revenue, 2),
            "revenue_growth_pct": revenue_growth,
            "sales_count": sales_count,
            "purchase_total": round(purchase_total, 2),
            "expense_total": round(expense_total, 2),
            "gross_profit": round(current_revenue - purchase_total - expense_total, 2),
            "receivables_outstanding": round(receivables, 2),
            "customer_count": customer_count,
            "supplier_count": supplier_count,
            "product_count": product_count,
            "low_stock_count": low_stock_count,
        },
        "monthly_trend": trend_data,
        "top_products": top_products,
        "top_customers": top_customers,
    }


# ─────────────────────────── Sales Analysis ───────────────────────────

@router.get("/sales-analysis")
async def sales_analysis(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    group_by: str = "month",  # month | customer | product
    user=Depends(get_current_user)
):
    _require_mis(user)
    q: dict[str, Any] = {}
    if from_date or to_date:
        q["created_at"] = {}
        if from_date:
            q["created_at"]["$gte"] = from_date
        if to_date:
            q["created_at"]["$lte"] = to_date

    pipeline: list[dict[str, Any]] = []
    if group_by == "customer":
        pipeline = [
            {"$match": q},
            {"$group": {
                "_id": "$customer_name",
                "total_revenue": {"$sum": "$total"},
                "invoice_count": {"$sum": 1},
                "avg_invoice": {"$avg": "$total"},
            }},
            {"$sort": {"total_revenue": -1}},
        ]
    elif group_by == "product":
        pipeline = [
            {"$match": q},
            {"$unwind": "$items"},
            {"$group": {
                "_id": "$items.product_name",
                "total_revenue": {"$sum": {"$multiply": ["$items.quantity", "$items.unit_price"]}},
                "units_sold": {"$sum": "$items.quantity"},
            }},
            {"$sort": {"total_revenue": -1}},
        ]
    else:
        pipeline = [
            {"$match": q},
            {"$group": {
                "_id": {"$substr": ["$created_at", 0, 7]},
                "total_revenue": {"$sum": "$total"},
                "invoice_count": {"$sum": 1},
            }},
            {"$sort": {"_id": 1}},
        ]

    results = await db.invoices.aggregate(pipeline).to_list(100)
    return {"group_by": group_by, "data": results}


# ─────────────────────────── Purchase Analysis ───────────────────────────

@router.get("/purchase-analysis")
async def purchase_analysis(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    group_by: str = "month",
    user=Depends(get_current_user)
):
    _require_mis(user)
    q: dict[str, Any] = {}
    if from_date or to_date:
        q["created_at"] = {}
        if from_date:
            q["created_at"]["$gte"] = from_date
        if to_date:
            q["created_at"]["$lte"] = to_date

    pipeline: list[dict[str, Any]] = []
    if group_by == "supplier":
        pipeline = [
            {"$match": q},
            {"$group": {
                "_id": "$supplier_name",
                "total_purchase": {"$sum": "$total"},
                "order_count": {"$sum": 1},
            }},
            {"$sort": {"total_purchase": -1}},
        ]
    elif group_by == "product":
        pipeline = [
            {"$match": q},
            {"$unwind": "$items"},
            {"$group": {
                "_id": "$items.product_name",
                "total_cost": {"$sum": {"$multiply": ["$items.quantity", "$items.unit_price"]}},
                "total_qty": {"$sum": "$items.quantity"},
            }},
            {"$sort": {"total_cost": -1}},
        ]
    else:
        pipeline = [
            {"$match": q},
            {"$group": {
                "_id": {"$substr": ["$created_at", 0, 7]},
                "total_purchase": {"$sum": "$total"},
                "order_count": {"$sum": 1},
            }},
            {"$sort": {"_id": 1}},
        ]

    results = await db.purchase_orders.aggregate(pipeline).to_list(100)
    return {"group_by": group_by, "data": results}


# ─────────────────────────── Profitability Report ───────────────────────────

@router.get("/profitability")
async def profitability_report(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_mis(user)
    q_sales: dict[str, Any] = {}
    q_exp: dict[str, Any] = {}
    if from_date or to_date:
        if from_date:
            q_sales.setdefault("created_at", {})["$gte"] = from_date
            q_exp.setdefault("date", {})["$gte"] = from_date
        if to_date:
            q_sales.setdefault("created_at", {})["$lte"] = to_date
            q_exp.setdefault("date", {})["$lte"] = to_date

    sales_agg = await db.invoices.aggregate([
        {"$match": q_sales},
        {"$group": {"_id": None, "revenue": {"$sum": "$total"}}},
    ]).to_list(1)
    revenue = sales_agg[0]["revenue"] if sales_agg else 0

    purchase_agg = await db.purchase_orders.aggregate([
        {"$match": q_sales},
        {"$group": {"_id": None, "cogs": {"$sum": "$total"}}},
    ]).to_list(1)
    cogs = purchase_agg[0]["cogs"] if purchase_agg else 0

    q_exp["status"] = "APPROVED"
    expense_agg = await db.expense_entries.aggregate([
        {"$match": q_exp},
        {"$group": {
            "_id": "$category",
            "total": {"$sum": "$amount"},
        }},
    ]).to_list(50)
    total_expenses = sum(e["total"] for e in expense_agg)

    gross_profit = revenue - cogs
    net_profit = gross_profit - total_expenses
    gross_margin = round((gross_profit / max(revenue, 1)) * 100, 1)
    net_margin = round((net_profit / max(revenue, 1)) * 100, 1)

    return {
        "revenue": round(revenue, 2),
        "cogs": round(cogs, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_margin_pct": gross_margin,
        "operating_expenses": round(total_expenses, 2),
        "expense_breakdown": expense_agg,
        "net_profit": round(net_profit, 2),
        "net_margin_pct": net_margin,
        "from_date": from_date,
        "to_date": to_date,
    }


# ─────────────────────────── Excel Export ───────────────────────────

@router.get("/export/sales-excel")
async def export_sales_excel(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_mis(user)
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(500, "openpyxl not installed. Run: pip install openpyxl")

    q: dict[str, Any] = {}
    if from_date:
        q.setdefault("created_at", {})["$gte"] = from_date
    if to_date:
        q.setdefault("created_at", {})["$lte"] = to_date

    invoices = await db.invoices.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)

    wb = openpyxl.Workbook()
    ws = wb.active
    if ws is None:
        raise HTTPException(500, "Could not create active worksheet")
    ws.title = "Sales Report"

    # Header style
    header_fill = PatternFill(start_color="1A1A2E", end_color="1A1A2E", fill_type="solid")
    header_font = Font(color="FFD700", bold=True)

    headers = ["Invoice No", "Date", "Customer", "Currency", "Total", "Paid", "Outstanding", "Status"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[get_column_letter(col)].width = 18

    for row_idx, inv in enumerate(invoices, 2):
        total = inv.get("total", 0)
        paid = inv.get("payment_received", 0)
        ws.cell(row=row_idx, column=1, value=inv.get("invoice_number", ""))
        ws.cell(row=row_idx, column=2, value=inv.get("created_at", "")[:10])
        ws.cell(row=row_idx, column=3, value=inv.get("customer_name", ""))
        ws.cell(row=row_idx, column=4, value=inv.get("currency", "INR"))
        ws.cell(row=row_idx, column=5, value=round(total, 2))
        ws.cell(row=row_idx, column=6, value=round(paid, 2))
        ws.cell(row=row_idx, column=7, value=round(total - paid, 2))
        ws.cell(row=row_idx, column=8, value=inv.get("status", ""))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"sales_report_{date.today().isoformat()}.xlsx"
    return Response(
        content=buf.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/expense-excel")
async def export_expense_excel(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_mis(user)
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(500, "openpyxl not installed. Run: pip install openpyxl")

    q: dict[str, Any] = {"status": "APPROVED"}
    if from_date:
        q.setdefault("date", {})["$gte"] = from_date
    if to_date:
        q.setdefault("date", {})["$lte"] = to_date

    expenses = await db.expense_entries.find(q, {"_id": 0}).sort("date", -1).to_list(2000)

    wb = openpyxl.Workbook()
    ws = wb.active
    if ws is None:
        raise HTTPException(500, "Could not create active worksheet")
    ws.title = "Expense Report"

    header_fill = PatternFill(start_color="1A1A2E", end_color="1A1A2E", fill_type="solid")
    header_font = Font(color="FFD700", bold=True)

    headers = ["Date", "Category", "Department", "Description", "Amount", "Payment Mode", "Status", "Approved By"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        ws.column_dimensions[get_column_letter(col)].width = 18

    for i, e in enumerate(expenses, 2):
        ws.cell(row=i, column=1, value=e.get("date", ""))
        ws.cell(row=i, column=2, value=e.get("category", ""))
        ws.cell(row=i, column=3, value=e.get("department", ""))
        ws.cell(row=i, column=4, value=e.get("description", ""))
        ws.cell(row=i, column=5, value=round(e.get("amount", 0), 2))
        ws.cell(row=i, column=6, value=e.get("payment_mode", ""))
        ws.cell(row=i, column=7, value=e.get("status", ""))
        ws.cell(row=i, column=8, value=e.get("approved_by_name", ""))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"expense_report_{date.today().isoformat()}.xlsx"
    return Response(
        content=buf.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
