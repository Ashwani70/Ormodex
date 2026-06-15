"""Stock Analysis Module.

Features:
- Inventory Aging Analysis (products not moved in X days)
- Stock Valuation (Weighted Average / FIFO)
- Physical Stock Verification / Audit
- Reorder suggestion list
- Batch & Expiry tracking endpoints
"""
import uuid
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.auth_utils import get_current_user, require_admin
from core.db import db

router = APIRouter(prefix="/stock", tags=["Stock Analysis"])


def _require_inventory(user: dict):
    if user.get("role") in ("admin", "accountant"):
        return user
    perms = user.get("module_permissions", [])
    if "inventory" not in perms:
        raise HTTPException(403, "Inventory module access required")
    return user


# ─────────────────────── Pydantic Models ───────────────────────

class PhysicalStockItem(BaseModel):
    product_id: str
    product_name: str
    sku: str
    system_quantity: float
    physical_quantity: float
    remarks: Optional[str] = None


class PhysicalVerification(BaseModel):
    verification_date: str
    verified_by: str
    warehouse_id: Optional[str] = None
    items: List[PhysicalStockItem]
    notes: Optional[str] = None
    status: Literal["DRAFT", "COMPLETED", "APPROVED"] = "DRAFT"


class BatchEntry(BaseModel):
    product_id: str
    product_name: str
    sku: str
    batch_number: str
    manufacture_date: Optional[str] = None
    expiry_date: Optional[str] = None
    quantity: float
    warehouse_id: Optional[str] = None
    unit_cost: float = 0.0


# ─────────────────────── Inventory Aging Analysis ───────────────────────

@router.get("/aging")
async def inventory_aging(
    days_threshold: int = 90,
    warehouse_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    """Products not involved in any sale/dispatch in the last N days (slow-moving/dead stock)."""
    _require_inventory(user)
    cutoff = (date.today() - timedelta(days=days_threshold)).isoformat()

    q: dict = {"quantity": {"$gt": 0}}
    if warehouse_id:
        q["warehouse_id"] = warehouse_id

    products = await db.products.find(q, {"_id": 0}).to_list(5000)

    result = []
    for prod in products:
        pid = prod["id"]
        # Find last outbound stock transaction
        last_tx = await db.stock_transactions.find_one(
            {"product_id": pid, "delta": {"$lt": 0}},
            {"_id": 0, "created_at": 1},
            sort=[("created_at", -1)]
        )
        last_movement = last_tx["created_at"][:10] if last_tx else prod.get("created_at", "")[:10]
        days_since = (date.today() - date.fromisoformat(last_movement[:10])).days if last_movement else 9999

        aging_bucket = (
            "0-30 days" if days_since <= 30 else
            "31-60 days" if days_since <= 60 else
            "61-90 days" if days_since <= 90 else
            "91-180 days" if days_since <= 180 else
            "180+ days"
        )

        stock_value = round(float(prod.get("quantity", 0)) * float(prod.get("cost_price", 0)), 2)

        result.append({
            "product_id": pid,
            "name": prod["name"],
            "sku": prod.get("sku", ""),
            "category": prod.get("category", ""),
            "quantity": prod.get("quantity", 0),
            "unit": prod.get("unit", "pcs"),
            "cost_price": prod.get("cost_price", 0),
            "stock_value": stock_value,
            "last_movement": last_movement,
            "days_since_movement": days_since,
            "aging_bucket": aging_bucket,
            "is_slow_moving": days_since > days_threshold,
        })

    # Sort by days_since_movement descending (oldest first)
    result.sort(key=lambda x: x["days_since_movement"], reverse=True)

    # Summary
    buckets = {}
    for r in result:
        b = r["aging_bucket"]
        if b not in buckets:
            buckets[b] = {"count": 0, "value": 0}
        buckets[b]["count"] += 1
        buckets[b]["value"] = round(buckets[b]["value"] + r["stock_value"], 2)

    return {
        "items": result,
        "summary": buckets,
        "total_products": len(result),
        "slow_moving_count": sum(1 for r in result if r["is_slow_moving"]),
        "total_stock_value": round(sum(r["stock_value"] for r in result), 2),
    }


# ─────────────────────── Stock Valuation ───────────────────────

@router.get("/valuation")
async def stock_valuation(
    method: Literal["WEIGHTED_AVERAGE", "FIFO"] = "WEIGHTED_AVERAGE",
    warehouse_id: Optional[str] = None,
    category: Optional[str] = None,
    user=Depends(get_current_user)
):
    """Calculate stock valuation using Weighted Average or FIFO method."""
    _require_inventory(user)

    q: dict = {"quantity": {"$gt": 0}}
    if warehouse_id:
        q["warehouse_id"] = warehouse_id
    if category:
        q["category"] = category

    products = await db.products.find(q, {"_id": 0}).to_list(5000)

    rows = []
    total_value = 0.0

    for prod in products:
        pid = prod["id"]
        current_qty = float(prod.get("quantity", 0))

        if method == "WEIGHTED_AVERAGE":
            # Use current cost_price as weighted average (simplified)
            unit_cost = float(prod.get("cost_price", 0))
            value = round(current_qty * unit_cost, 2)
        else:
            # FIFO: use earliest purchase price from purchase transactions
            inbound_txs = await db.stock_transactions.find(
                {"product_id": pid, "delta": {"$gt": 0}},
                {"_id": 0}
            ).sort("created_at", 1).to_list(500)

            remaining_qty = current_qty
            value = 0.0
            for tx in inbound_txs:
                if remaining_qty <= 0:
                    break
                tx_qty = min(float(tx.get("delta", 0)), remaining_qty)
                tx_cost = float(tx.get("unit_cost", prod.get("cost_price", 0)))
                value += tx_qty * tx_cost
                remaining_qty -= tx_qty

            unit_cost = round(value / max(current_qty, 0.001), 2)
            value = round(value, 2)

        rows.append({
            "product_id": pid,
            "name": prod["name"],
            "sku": prod.get("sku", ""),
            "category": prod.get("category", ""),
            "quantity": current_qty,
            "unit": prod.get("unit", "pcs"),
            "unit_cost": unit_cost,
            "total_value": value,
            "selling_price": prod.get("selling_price", 0),
            "valuation_method": method,
        })
        total_value += value

    rows.sort(key=lambda x: x["total_value"], reverse=True)

    # Category breakdown
    cat_summary: dict = {}
    for r in rows:
        cat = r["category"]
        if cat not in cat_summary:
            cat_summary[cat] = {"count": 0, "value": 0}
        cat_summary[cat]["count"] += 1
        cat_summary[cat]["value"] = round(cat_summary[cat]["value"] + r["total_value"], 2)

    return {
        "method": method,
        "items": rows,
        "category_summary": cat_summary,
        "total_products": len(rows),
        "total_value": round(total_value, 2),
    }


# ─────────────────────── Reorder Suggestions ───────────────────────

@router.get("/reorder-suggestions")
async def reorder_suggestions(user=Depends(get_current_user)):
    """Products at or below reorder level (low_stock_threshold)."""
    _require_inventory(user)
    products = await db.products.find(
        {"$expr": {"$lte": ["$quantity", "$low_stock_threshold"]}},
        {"_id": 0}
    ).sort("quantity", 1).to_list(500)

    result = []
    for prod in products:
        qty = float(prod.get("quantity", 0))
        threshold = float(prod.get("low_stock_threshold", 10))
        suggested_qty = max(threshold * 2, threshold - qty)  # Order 2x threshold or enough to fill up

        # Find preferred supplier from recent POs
        last_po_item = await db.purchase_orders.find_one(
            {"items.product_id": prod["id"]},
            {"_id": 0, "supplier_name": 1, "supplier_id": 1},
            sort=[("created_at", -1)]
        )
        result.append({
            "product_id": prod["id"],
            "name": prod["name"],
            "sku": prod.get("sku", ""),
            "current_quantity": qty,
            "reorder_level": threshold,
            "shortage": max(0, threshold - qty),
            "suggested_order_qty": round(suggested_qty, 2),
            "unit": prod.get("unit", "pcs"),
            "cost_price": prod.get("cost_price", 0),
            "estimated_cost": round(suggested_qty * float(prod.get("cost_price", 0)), 2),
            "preferred_supplier": last_po_item.get("supplier_name") if last_po_item else None,
            "preferred_supplier_id": last_po_item.get("supplier_id") if last_po_item else None,
        })

    return {
        "items": result,
        "total_items": len(result),
        "total_estimated_cost": round(sum(r["estimated_cost"] for r in result), 2),
    }


# ─────────────────────── Physical Stock Verification ───────────────────────

@router.get("/physical-verifications")
async def list_physical_verifications(
    warehouse_id: Optional[str] = None,
    status: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_inventory(user)
    q: dict = {}
    if warehouse_id:
        q["warehouse_id"] = warehouse_id
    if status:
        q["status"] = status
    items = await db.physical_verifications.find(q, {"_id": 0}).sort("verification_date", -1).to_list(200)
    return items


@router.get("/physical-verifications/{pv_id}")
async def get_physical_verification(pv_id: str, user=Depends(get_current_user)):
    _require_inventory(user)
    pv = await db.physical_verifications.find_one({"id": pv_id}, {"_id": 0})
    if not pv:
        raise HTTPException(404, "Physical verification not found")
    return pv


@router.post("/physical-verifications")
async def create_physical_verification(data: PhysicalVerification, user=Depends(get_current_user)):
    _require_inventory(user)
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())

    # Calculate discrepancies
    total_discrepancy = 0.0
    for item in doc["items"]:
        disc = item["physical_quantity"] - item["system_quantity"]
        item["discrepancy"] = round(disc, 3)
        total_discrepancy += abs(disc)

    doc["total_discrepancy"] = round(total_discrepancy, 3)
    doc["items_checked"] = len(doc["items"])
    doc["created_by"] = user["id"]
    doc["created_by_name"] = user.get("name", "")
    doc["created_at"] = datetime.now(timezone.utc).isoformat()

    await db.physical_verifications.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/physical-verifications/{pv_id}/approve")
async def approve_and_adjust_stock(pv_id: str, user=Depends(require_admin)):
    """Approve verification and adjust system stock to match physical count."""
    pv = await db.physical_verifications.find_one({"id": pv_id})
    if not pv:
        raise HTTPException(404, "Physical verification not found")
    if pv.get("status") == "APPROVED":
        raise HTTPException(400, "Already approved")

    adjustments = []
    for item in pv.get("items", []):
        disc = item.get("discrepancy", 0)
        if abs(disc) > 0.001:
            prod = await db.products.find_one({"id": item["product_id"]})
            if prod:
                new_qty = float(item["physical_quantity"])
                await db.products.update_one(
                    {"id": item["product_id"]},
                    {"$set": {"quantity": new_qty, "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
                # Log stock adjustment
                tx_id = str(uuid.uuid4())
                await db.stock_transactions.insert_one({
                    "id": tx_id,
                    "product_id": item["product_id"],
                    "product_name": item["product_name"],
                    "delta": disc,
                    "balance": new_qty,
                    "reason": f"Physical Stock Verification Adjustment (PV-{pv_id[:8]})",
                    "user_id": user["id"],
                    "user_name": user.get("name", "Admin"),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                adjustments.append({"product_id": item["product_id"], "adjustment": disc})

    await db.physical_verifications.update_one(
        {"id": pv_id},
        {"$set": {"status": "APPROVED", "approved_by": user["id"], "approved_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"ok": True, "adjustments_made": len(adjustments), "adjustments": adjustments}


# ─────────────────────── Batch & Expiry Tracking ───────────────────────

@router.get("/batches")
async def list_batches(
    product_id: Optional[str] = None,
    expiring_within_days: Optional[int] = None,
    user=Depends(get_current_user)
):
    _require_inventory(user)
    q: dict = {}
    if product_id:
        q["product_id"] = product_id
    if expiring_within_days is not None:
        cutoff = (date.today() + timedelta(days=expiring_within_days)).isoformat()
        q["expiry_date"] = {"$lte": cutoff, "$gte": date.today().isoformat()}
    batches = await db.batches.find(q, {"_id": 0}).sort("expiry_date", 1).to_list(1000)
    return batches


@router.post("/batches")
async def create_batch(data: BatchEntry, user=Depends(get_current_user)):
    _require_inventory(user)
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_by"] = user["id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    if doc.get("expiry_date"):
        expiry = date.fromisoformat(doc["expiry_date"])
        today = date.today()
        days_to_expiry = (expiry - today).days
        doc["days_to_expiry"] = days_to_expiry
        doc["expiry_status"] = "EXPIRED" if days_to_expiry < 0 else ("NEAR_EXPIRY" if days_to_expiry <= 30 else "GOOD")
    await db.batches.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/batches/{batch_id}")
async def delete_batch(batch_id: str, user=Depends(require_admin)):
    await db.batches.delete_one({"id": batch_id})
    return {"ok": True}
