from datetime import datetime

from fastapi import APIRouter, Depends

from core.auth_utils import get_current_user
from core.db import db

router = APIRouter(tags=["reports"])


@router.get("/dashboard/summary")
async def dashboard_summary(_: dict = Depends(get_current_user)):
    products = await db.products.find(
        {}, {"_id": 0, "quantity": 1, "low_stock_threshold": 1, "selling_price": 1, "cost_price": 1}
    ).to_list(5000)
    total_products = len(products)
    low_stock = sum(1 for p in products if float(p.get("quantity", 0)) <= float(p.get("low_stock_threshold", 0)))
    inventory_value = round(sum(float(p.get("quantity", 0)) * float(p.get("cost_price", 0)) for p in products), 2)

    customers_count = await db.customers.count_documents({})
    leads_count = await db.leads.count_documents({})
    open_leads = await db.leads.count_documents({"status": {"$in": ["NEW", "CONTACTED", "QUOTED"]}})

    invoices = await db.invoices.find({}, {"_id": 0, "total": 1, "payment_received": 1, "created_at": 1, "status": 1}).to_list(5000)
    total_revenue = round(sum(float(i.get("total", 0)) for i in invoices), 2)
    received_revenue = round(sum(float(i.get("payment_received", 0)) for i in invoices), 2)
    outstanding = round(total_revenue - received_revenue, 2)

    sos = await db.sales_orders.count_documents({})
    pending_sos = await db.sales_orders.count_documents({"status": "PENDING"})

    by_month = {}
    for inv in invoices:
        ca = inv.get("created_at")
        if not ca:
            continue
        try:
            dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
            key = dt.strftime("%Y-%m")
            by_month[key] = by_month.get(key, 0) + float(inv.get("total", 0))
        except Exception:
            pass
    months = sorted(by_month.keys())[-6:]
    sales_trend = [{"month": m, "revenue": round(by_month[m], 2)} for m in months]

    funnel = []
    for st in ["NEW", "CONTACTED", "QUOTED", "WON", "LOST"]:
        c = await db.leads.count_documents({"status": st})
        funnel.append({"status": st, "count": c})

    all_products = await db.products.find(
        {}, {"_id": 0, "name": 1, "sku": 1, "quantity": 1, "low_stock_threshold": 1}
    ).to_list(5000)
    low_list = [p for p in all_products if float(p.get("quantity", 0)) <= float(p.get("low_stock_threshold", 0))]
    low_list = sorted(low_list, key=lambda p: float(p.get("quantity", 0)))[:8]

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
        },
        "sales_trend": sales_trend,
        "lead_funnel": funnel,
        "low_stock_items": low_list,
    }


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

