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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth_utils import get_current_user, require_admin, is_admin_role
from core.db import db
from core.product_stock_bridge import resolve_godown_id, resolve_stock_item_ids_for_products
from core.stock_ledger import post_entry

router = APIRouter(prefix="/stock", tags=["Stock Analysis"])


async def _fetch_products_by_ids_dict(product_ids: list[str]) -> dict[str, dict]:
    """Batch-read many products in ONE query instead of a find_one-per-id
    loop. Mirrors the identically-purposed helper already used in
    job_work.py/manufacturing.py."""
    ids = list({pid for pid in product_ids if pid})
    if not ids:
        return {}
    prods = await db.products.find({"id": {"$in": ids}}, {"_id": 0}).to_list(len(ids))
    return {p["id"]: p for p in prods}


def _require_inventory(user: dict):
    if (is_admin_role(user.get("role")) or user.get("role") == "accountant"):
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
    _cutoff = (date.today() - timedelta(days=days_threshold)).isoformat()

    q: dict = {"quantity": {"$gt": 0}}
    if warehouse_id:
        q["warehouse_id"] = warehouse_id

    products = await db.products.find(q, {"_id": 0}).to_list(5000)

    # Batch-read every product's outbound movements in ONE query instead of a
    # find_one per product (was an N+1 — 1+N round-trips). Reduced to the
    # latest one per product_id in Python (rows arrive sorted desc, so the
    # first one seen per product is the most recent).
    product_ids = [p["id"] for p in products]
    last_tx_by_product: dict[str, dict] = {}
    if product_ids:
        outbound_tx = await db.stock_transactions.find(
            {"product_id": {"$in": product_ids}, "delta": {"$lt": 0}},
            {"_id": 0, "product_id": 1, "created_at": 1},
        ).sort("created_at", -1).to_list(200000)
        for tx in outbound_tx:
            pid = tx.get("product_id")
            if pid and pid not in last_tx_by_product:
                last_tx_by_product[pid] = tx

    result = []
    for prod in products:
        pid = prod["id"]
        last_tx = last_tx_by_product.get(pid)
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
            "unit": prod.get("unit", "Nos"),
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

    # FIFO needs every product's inbound layers oldest-first. Batch-read them
    # ALL in one query instead of a find per product inside the loop below
    # (was an N+1 — 1+N round-trips, only when method=FIFO). Grouped by
    # product_id in Python, preserving the ascending order the FIFO
    # consumption loop needs (rows arrive sorted asc from the query).
    inbound_by_product: dict[str, list[dict]] = {}
    if method == "FIFO":
        product_ids = [p["id"] for p in products]
        if product_ids:
            all_inbound = await db.stock_transactions.find(
                {"product_id": {"$in": product_ids}, "delta": {"$gt": 0}},
                {"_id": 0},
            ).sort("created_at", 1).to_list(500000)
            for tx in all_inbound:
                pid = tx.get("product_id")
                if pid:
                    inbound_by_product.setdefault(pid, []).append(tx)

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
            inbound_txs = inbound_by_product.get(pid, [])[:500]

            remaining_qty = current_qty
            value = 0.0
            for tx in inbound_txs:
                if remaining_qty <= 0:
                    break
                tx_qty = min(float(tx.get("delta", 0)), remaining_qty)
                raw_cost = tx.get("unit_cost")
                if raw_cost is None:
                    raw_cost = prod.get("cost_price", 0)
                tx_cost = float(raw_cost or 0)
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
            "unit": prod.get("unit", "Nos"),
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
    # quantity vs low_stock_threshold is a column-vs-column compare, which the
    # data layer can't push down as a filter — fetch, filter + sort in Python.
    _all = await db.products.find({}, {"_id": 0}).to_list(10000)
    products = sorted(
        (p for p in _all
         if float(p.get("quantity") or 0) <= float(p.get("low_stock_threshold") or 0)),
        key=lambda p: float(p.get("quantity") or 0),
    )[:500]

    result = []
    for prod in products:
        qty = float(prod.get("quantity", 0))
        threshold = float(prod.get("low_stock_threshold", 10))
        suggested_qty = max(threshold * 2, threshold - qty)  # Order 2x threshold or enough to fill up

        # NOTE: a "preferred supplier from recent POs" lookup used to run
        # here (find_one({"items.product_id": prod["id"]}) per product — an
        # N+1). It never actually matched anything: purchase_orders.items is
        # a real JSONB column, and core._mongo_compat's dict-filter translator
        # has no support for a dotted "items.product_id" path into it, so the
        # filter always fell through to a no-op (see _to_filter's fallback to
        # sqlalchemy.false()) and preferred_supplier was always None. Removed
        # rather than batched — there was no query worth batching, just N
        # wasted round-trips for a result this endpoint already always
        # returned. Output is unchanged (still always None).
        last_po_item = None
        result.append({
            "product_id": prod["id"],
            "name": prod["name"],
            "sku": prod.get("sku", ""),
            "current_quantity": qty,
            "reorder_level": threshold,
            "shortage": max(0, threshold - qty),
            "suggested_order_qty": round(suggested_qty, 2),
            "unit": prod.get("unit", "Nos"),
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


@router.put("/physical-verifications/{pv_id}")
async def update_physical_verification(pv_id: str, data: PhysicalVerification, user=Depends(get_current_user)):
    _require_inventory(user)
    existing = await db.physical_verifications.find_one({"id": pv_id})
    if not existing:
        raise HTTPException(404, "Physical verification not found")
    if existing.get("status") == "APPROVED":
        raise HTTPException(400, "Cannot edit an approved verification")

    doc = data.model_dump()

    total_discrepancy = 0.0
    for item in doc["items"]:
        disc = item["physical_quantity"] - item["system_quantity"]
        item["discrepancy"] = round(disc, 3)
        total_discrepancy += abs(disc)

    doc["total_discrepancy"] = round(total_discrepancy, 3)
    doc["items_checked"] = len(doc["items"])
    doc["updated_by"] = user["id"]
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.physical_verifications.update_one({"id": pv_id}, {"$set": doc})
    updated = await db.physical_verifications.find_one({"id": pv_id}, {"_id": 0})
    return updated


@router.delete("/physical-verifications/{pv_id}")
async def delete_physical_verification(pv_id: str, user=Depends(get_current_user)):
    _require_inventory(user)
    existing = await db.physical_verifications.find_one({"id": pv_id})
    if not existing:
        raise HTTPException(404, "Physical verification not found")
    if existing.get("status") == "APPROVED":
        raise HTTPException(400, "Cannot delete an approved verification — stock adjustments were already posted")
    await db.physical_verifications.delete_one({"id": pv_id})
    return {"ok": True}


@router.post("/physical-verifications/{pv_id}/approve")
async def approve_and_adjust_stock(pv_id: str, user=Depends(require_admin)):
    """Approve verification and adjust system stock to match physical count."""
    pv = await db.physical_verifications.find_one({"id": pv_id})
    if not pv:
        raise HTTPException(404, "Physical verification not found")
    if pv.get("status") == "APPROVED":
        raise HTTPException(400, "Already approved")

    # Routed through the valuation-aware ledger (post_entry) so a physical-
    # count correction gets a real FIFO/LIFO/WA/Standard-Cost priced entry,
    # not just a flat quantity overwrite. No godown is recorded on a physical
    # verification line today, so this resolves the tenant's default the same
    # way manual adjustment and opening stock do (core.product_stock_bridge).
    # Products + stock_item_ids for every discrepant line are batched in TWO
    # queries total up front (was an N+1 — up to 6 queries per discrepant
    # item: a products find_one, resolve_stock_item_id_for_product's own up
    # to 3 queries, and resolve_godown_id's query, all repeated per item).
    discrepant_items = [
        item for item in pv.get("items", [])
        if abs(item.get("discrepancy", 0)) > 0.001
    ]
    product_ids = [item["product_id"] for item in discrepant_items]
    products_by_id = await _fetch_products_by_ids_dict(product_ids)
    stock_item_by_product = await resolve_stock_item_ids_for_products(product_ids, user)
    godown_id = await resolve_godown_id(None)

    adjustments = []
    for item in discrepant_items:
        disc = item.get("discrepancy", 0)
        prod = products_by_id.get(item["product_id"])
        if prod:
            rate = float(prod.get("cost_price") or 0) if disc > 0 else None
            await post_entry(
                stock_item_id=stock_item_by_product[item["product_id"]], godown_id=godown_id,
                qty=disc, movement_type="ADJUSTMENT", rate=rate,
                source_doc_type="physical_verification", source_doc_id=pv_id,
                user=user,
            )
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
