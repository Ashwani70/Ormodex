"""Job Work router.

Covers:
- Outward delivery challans (goods sent to job worker, no GST charged)
- Inward receipt (goods returned, partial + scrap)
- Return-window tracking (Rule 45: 1 yr inputs / 3 yrs capital goods)
- Deemed-supply flagging for overdue challans
- ITC-04 period statement (GSTR-ITC-04)
- Pending material report
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone, timedelta

from core.auth_utils import get_current_user
from core.db import db
from core.models import JobWorkChallan, JobWorkReceipt
from core.utils import now_iso, new_id, next_doc_number

router = APIRouter(prefix="/job-work", tags=["Job Work"])


def _item_key(item: dict) -> str:
    """Matching key for a line item. Catalog items use product_id; custom
    (off-catalog) items have no product_id, so fall back to their name."""
    if item.get("is_custom") or not item.get("product_id"):
        return f"custom::{item.get('product_name', '')}"
    return item["product_id"]


def _require_job_work(user: dict):
    if user.get("role") in ("admin", "accountant"):
        return user
    perms = user.get("module_permissions", [])
    if "inventory" not in perms and "sales" not in perms and "manufacturing" not in perms:
        raise HTTPException(403, "Job work module access required")
    return user


# ── Return-window helper ──────────────────────────────────────────────────────

async def _get_return_window_days(nature: str = "inputs") -> int:
    """
    Read the configurable return window from rate_tables collection.
    Falls back to statutory defaults: 1 yr (365 days) for inputs,
    3 yrs (1095 days) for capital goods (Rule 45, CGST Rules 2017).
    """
    key = "job_work_return_window_capital" if nature == "capital_goods" else "job_work_return_window_inputs"
    rate = await db.rate_tables.find_one({"key": key}, {"_id": 0})
    if rate and rate.get("value"):
        return int(rate["value"])
    return 1095 if nature == "capital_goods" else 365


def _due_date(challan_date: str, window_days: int) -> str:
    try:
        dt = datetime.fromisoformat(challan_date)
    except ValueError:
        dt = datetime.now(timezone.utc)
    due = dt + timedelta(days=window_days)
    return due.date().isoformat()


def _is_overdue(due_date_str: str) -> bool:
    try:
        due = datetime.fromisoformat(due_date_str).date()
    except ValueError:
        return False
    return due < datetime.now(timezone.utc).date()


# ══════════════════════════════════════════════════════════════
# Challans (Outward)
# ══════════════════════════════════════════════════════════════

@router.get("/challans")
async def list_challans(
    q: Optional[str] = None,
    overdue_only: bool = False,
    user: dict = Depends(get_current_user),
):
    _require_job_work(user)
    filt: dict = {}
    if q:
        filt["$or"] = [
            {"challan_number": {"$regex": q, "$options": "i"}},
            {"job_worker_name": {"$regex": q, "$options": "i"}},
        ]
    if overdue_only:
        filt["is_overdue"] = True
        filt["status"] = {"$nin": ["COMPLETED", "CANCELLED"]}

    challans = await db.job_work_challans.find(filt, {"_id": 0}).sort("date", -1).to_list(1000)

    # Refresh overdue flag in-band (lightweight; avoids a separate background job)
    today = datetime.now(timezone.utc).date().isoformat()
    for c in challans:
        if c.get("due_date") and c["status"] not in ("COMPLETED", "CANCELLED"):
            c["is_overdue"] = c["due_date"] < today
            c["deemed_supply"] = c["is_overdue"]
        else:
            c["is_overdue"] = False
            c["deemed_supply"] = False

    return challans


@router.get("/challans/{item_id}")
async def get_challan(item_id: str, user: dict = Depends(get_current_user)):
    _require_job_work(user)
    c = await db.job_work_challans.find_one({"id": item_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Challan not found")
    return c


@router.post("/challans")
async def create_challan(payload: JobWorkChallan, user: dict = Depends(get_current_user)):
    _require_job_work(user)
    data = payload.model_dump()
    data["id"] = new_id()
    if not data.get("challan_number"):
        data["challan_number"] = await next_doc_number("JWC", "job_work_challans")

    # Determine nature and compute return-window due date
    nature = data.get("nature", "inputs")
    window_days = await _get_return_window_days(nature)
    data["due_date"] = _due_date(data.get("date", now_iso()), window_days)
    data["return_window_days"] = window_days
    data["is_overdue"] = False
    data["deemed_supply"] = False

    # Enrich taxable_value on each item and validate stock.
    # Custom (free-text) items have no catalog product: skip lookup, stock
    # check and inventory movement — they are off-catalog material.
    for item in data.get("items", []):
        if item.get("is_custom") or not item.get("product_id"):
            item["is_custom"] = True
            item["product_id"] = None
            continue
        prod = await db.products.find_one({"id": item["product_id"]})
        if not prod:
            raise HTTPException(400, f"Product '{item.get('product_name', item['product_id'])}' not found.")
        available_qty = float(prod.get("quantity", 0))
        requested_qty = float(item["quantity"])
        if requested_qty > available_qty:
            raise HTTPException(
                400,
                f"Insufficient stock for '{prod['name']}'. Available: {available_qty}, Requested: {requested_qty}",
            )
        # Capture taxable value (no GST charged on job-work challan, but value tracked for ITC-04)
        if not item.get("taxable_value"):
            item["taxable_value"] = round(float(prod.get("cost_price", 0)) * requested_qty, 2)

    # Process inventory reduction (catalog items only)
    for item in data.get("items", []):
        if item.get("is_custom") or not item.get("product_id"):
            continue
        prod = await db.products.find_one({"id": item["product_id"]}) or {}
        new_qty = float(prod.get("quantity", 0)) - float(item["quantity"])
        await db.products.update_one(
            {"id": item["product_id"]},
            {"$set": {"quantity": new_qty, "updated_at": now_iso()}},
        )
        await db.stock_transactions.insert_one({
            "id": new_id(),
            "product_id": item["product_id"],
            "product_name": item["product_name"],
            "delta": -float(item["quantity"]),
            "balance": new_qty,
            "reason": f"Job Work Issue {data['challan_number']}",
            "user_id": user["id"],
            "user_name": user.get("name", ""),
            "created_at": now_iso(),
        })

    data["status"] = "PENDING"
    data["created_at"] = now_iso()
    data["updated_at"] = now_iso()
    await db.job_work_challans.insert_one(data)
    data.pop("_id", None)
    return data


# ══════════════════════════════════════════════════════════════
# Receipts (Inward)
# ══════════════════════════════════════════════════════════════

@router.post("/challans/{item_id}/receipt")
async def create_receipt(item_id: str, payload: JobWorkReceipt, user: dict = Depends(get_current_user)):
    _require_job_work(user)
    challan = await db.job_work_challans.find_one({"id": item_id})
    if not challan:
        raise HTTPException(status_code=404, detail="Challan not found")

    data = payload.model_dump()
    data["id"] = new_id()
    if not data.get("receipt_number"):
        data["receipt_number"] = await next_doc_number("JWR", "job_work_receipts")
    data["challan_id"] = item_id

    # Compute already-received quantities
    existing_receipts = await db.job_work_receipts.find({"challan_id": item_id}).to_list(100)
    received_map: dict = {}
    for r in existing_receipts:
        for it in r.get("items", []):
            k = _item_key(it)
            received_map[k] = received_map.get(k, 0.0) + float(it.get("quantity_received", 0))

    challan_items_map = {_item_key(it): float(it["quantity"]) for it in challan.get("items", [])}

    for item in data.get("items", []):
        k = _item_key(item)
        sent_qty = challan_items_map.get(k, 0.0)
        already_received = received_map.get(k, 0.0)
        pending_qty = sent_qty - already_received

        if float(item["quantity_received"]) > pending_qty + 1e-5:
            raise HTTPException(
                400,
                f"Received quantity ({item['quantity_received']}) exceeds pending "
                f"({pending_qty}) for '{item['product_name']}'.",
            )

    data["created_at"] = now_iso()
    await db.job_work_receipts.insert_one(data)

    # Process inventory return (catalog items only; custom items are off-catalog)
    for item in data.get("items", []):
        if item.get("is_custom") or not item.get("product_id"):
            continue
        prod = await db.products.find_one({"id": item["product_id"]}) or {}
        new_qty = float(prod.get("quantity", 0)) + float(item["quantity_received"])
        await db.products.update_one(
            {"id": item["product_id"]},
            {"$set": {"quantity": new_qty, "updated_at": now_iso()}},
        )
        await db.stock_transactions.insert_one({
            "id": new_id(),
            "product_id": item["product_id"],
            "product_name": item["product_name"],
            "delta": float(item["quantity_received"]),
            "balance": new_qty,
            "reason": f"Job Work Receipt {data['receipt_number']}",
            "user_id": user["id"],
            "user_name": user.get("name", ""),
            "created_at": now_iso(),
        })

    # Re-compute total received and update challan status
    all_receipts = await db.job_work_receipts.find({"challan_id": item_id}).to_list(200)
    received_map = {}
    for r in all_receipts:
        for it in r.get("items", []):
            k = _item_key(it)
            received_map[k] = received_map.get(k, 0.0) + float(it.get("quantity_received", 0))

    completed = True
    partial = False
    for it in challan.get("items", []):
        sent = float(it["quantity"])
        recv = received_map.get(_item_key(it), 0.0)
        if recv < sent - 1e-6:
            completed = False
        if recv > 1e-6:
            partial = True

    new_status = "COMPLETED" if completed else ("PARTIAL" if partial else "PENDING")
    await db.job_work_challans.update_one(
        {"id": item_id},
        {"$set": {"status": new_status, "is_overdue": False, "deemed_supply": False, "updated_at": now_iso()}},
    )

    data.pop("_id", None)
    return data


# ══════════════════════════════════════════════════════════════
# Receipts list
# ══════════════════════════════════════════════════════════════

@router.get("/receipts")
async def list_receipts(challan_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_job_work(user)
    filt = {}
    if challan_id:
        filt["challan_id"] = challan_id
    return await db.job_work_receipts.find(filt, {"_id": 0}).sort("created_at", -1).to_list(1000)


# ══════════════════════════════════════════════════════════════
# Pending material report
# ══════════════════════════════════════════════════════════════

@router.get("/reports/pending")
async def get_pending_job_work(user: dict = Depends(get_current_user)):
    """Outstanding materials at job workers with overdue flag."""
    _require_job_work(user)
    challans = await db.job_work_challans.find(
        {"status": {"$in": ["PENDING", "PARTIAL"]}},
    ).to_list(1000)

    today = datetime.now(timezone.utc).date().isoformat()
    pending_list = []
    for c in challans:
        receipts = await db.job_work_receipts.find({"challan_id": c["id"]}).to_list(500)
        received_map: dict = {}
        for r in receipts:
            for it in r.get("items", []):
                k = _item_key(it)
                received_map[k] = received_map.get(k, 0.0) + float(it.get("quantity_received", 0))

        is_overdue = bool(c.get("due_date") and c["due_date"] < today)

        for item in c.get("items", []):
            sent = float(item["quantity"])
            received = received_map.get(_item_key(item), 0.0)
            pending = sent - received
            if pending > 1e-6:
                days_remaining = None
                if c.get("due_date"):
                    try:
                        due = datetime.fromisoformat(c["due_date"]).date()
                        days_remaining = (due - datetime.now(timezone.utc).date()).days
                    except ValueError:
                        pass
                pending_list.append({
                    "challan_id": c["id"],
                    "challan_number": c["challan_number"],
                    "date": c["date"],
                    "due_date": c.get("due_date"),
                    "days_remaining": days_remaining,
                    "is_overdue": is_overdue,
                    "deemed_supply": is_overdue,
                    "job_worker_name": c["job_worker_name"],
                    "product_id": item["product_id"],
                    "product_name": item["product_name"],
                    "sku": item.get("sku", ""),
                    "quantity_sent": sent,
                    "quantity_received": received,
                    "quantity_pending": round(pending, 4),
                    "unit": item.get("unit", "pcs"),
                    "taxable_value": item.get("taxable_value", 0),
                })
    return pending_list


# ══════════════════════════════════════════════════════════════
# ITC-04 Statement
# ══════════════════════════════════════════════════════════════

@router.get("/itc-04")
async def get_itc04(
    period: str = Query(..., description="Period in MMYYYY format, e.g. '062025'"),
    user: dict = Depends(get_current_user),
):
    """
    ITC-04 — Statement of goods dispatched to / received from job worker.

    Format:
    - Table 4: Goods sent to job worker (outward challans in the period)
    - Table 5: Goods received from job worker (inward receipts in the period)
    - Summary: sent vs received vs pending vs scrap
    """
    _require_job_work(user)

    if len(period) != 6 or not period.isdigit():
        raise HTTPException(400, "period must be MMYYYY, e.g. '062025'")

    mm = period[:2]
    yyyy = period[2:]
    period_start = f"{yyyy}-{mm}-01"
    # End of month
    next_month = int(mm) % 12 + 1
    next_year = int(yyyy) + (1 if next_month == 1 else 0)
    period_end = f"{next_year}-{next_month:02d}-01"

    # Table 4: Challans issued in the period
    outward_challans = await db.job_work_challans.find(
        {"date": {"$gte": period_start, "$lt": period_end}},
        {"_id": 0},
    ).sort("date", 1).to_list(2000)

    table4 = []
    for c in outward_challans:
        for item in c.get("items", []):
            table4.append({
                "challan_number": c["challan_number"],
                "challan_date": c["date"],
                "due_date": c.get("due_date"),
                "job_worker_name": c.get("job_worker_name", ""),
                "job_worker_gstin": c.get("job_worker_gstin", ""),
                "nature": c.get("nature", "inputs"),
                "product_name": item.get("product_name", ""),
                "hsn_code": item.get("hsn_code", ""),
                "quantity_sent": float(item.get("quantity", 0)),
                "unit": item.get("unit", "pcs"),
                "taxable_value": float(item.get("taxable_value", 0)),
                "is_overdue": c.get("is_overdue", False),
                "challan_status": c.get("status", ""),
            })

    # Table 5: Receipts inward in the period
    inward_receipts = await db.job_work_receipts.find(
        {"date": {"$gte": period_start, "$lt": period_end}},
        {"_id": 0},
    ).sort("date", 1).to_list(2000)

    # Build a challan reference map
    challan_ids = {r["challan_id"] for r in inward_receipts if r.get("challan_id")}
    ref_challans: dict = {}
    for cid in challan_ids:
        c = await db.job_work_challans.find_one({"id": cid}, {"_id": 0})
        if c:
            ref_challans[cid] = c

    table5 = []
    for r in inward_receipts:
        ref = ref_challans.get(r.get("challan_id", ""), {})
        for item in r.get("items", []):
            table5.append({
                "receipt_number": r.get("receipt_number", ""),
                "receipt_date": r.get("date", ""),
                "original_challan_number": ref.get("challan_number", ""),
                "original_challan_date": ref.get("date", ""),
                "job_worker_name": ref.get("job_worker_name", ""),
                "product_name": item.get("product_name", ""),
                "quantity_received": float(item.get("quantity_received", 0)),
                "scrap_quantity": float(item.get("scrap_quantity", 0)),
                "unit": item.get("unit", "pcs"),
            })

    # Summary
    total_sent = sum(row["quantity_sent"] for row in table4)
    total_received = sum(row["quantity_received"] for row in table5)
    total_scrap = sum(row["scrap_quantity"] for row in table5)
    total_taxable_value_sent = sum(row["taxable_value"] for row in table4)
    overdue_count = sum(1 for row in table4 if row["is_overdue"])

    return {
        "period": period,
        "period_label": f"{mm}/{yyyy}",
        "table4_outward_challans": table4,
        "table5_inward_receipts": table5,
        "summary": {
            "total_challans_issued": len(outward_challans),
            "total_receipts": len(inward_receipts),
            "total_quantity_sent": round(total_sent, 4),
            "total_quantity_received": round(total_received, 4),
            "total_scrap": round(total_scrap, 4),
            "total_taxable_value_sent": round(total_taxable_value_sent, 2),
            "overdue_challans": overdue_count,
        },
    }
