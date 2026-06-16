"""Inventory v2 — Tally-style stock ledger: masters, movements, transfers, reports.

Mounted at /inventory/v2 to coexist with the legacy flat inventory router. Stock
qty/value are always derived from the StockLedgerEntry via the valuation engine.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.inventory_models import (
    Batch, Godown, SerialNumber, StockAdjustmentIn, StockItem, StockItemUpdate,
    StockTransfer, UnitOfMeasure,
)
from core.stock_ledger import LEDGER, on_hand, post_entry
from core.stock_valuation import value_movements
from core.utils import (
    crud_create, crud_delete, crud_get, crud_list, crud_update, next_doc_number,
    paginated_list,
)

router = APIRouter(prefix="/inventory/v2", tags=["Inventory v2"])


def _require_inventory(user: dict) -> dict:
    if user.get("role") == "admin":
        return user
    if "inventory" in (user.get("module_permissions") or []):
        return user
    raise HTTPException(status_code=403, detail="Inventory module access required")


# ───────────────────────── Units of Measure ─────────────────────────

@router.get("/units")
async def list_units(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                     from_date: Optional[str] = None, to_date: Optional[str] = None,
                     user: dict = Depends(get_current_user)):
    _require_inventory(user)
    return await paginated_list("units_of_measure", page=page, limit=limit, q=q,
                                 search_fields=["name", "uqc_code"],
                                 sort_field="name", sort_dir=1,
                                 from_date=from_date, to_date=to_date)


@router.post("/units")
async def create_unit(payload: UnitOfMeasure, user: dict = Depends(get_current_user)):
    _require_inventory(user)
    data = payload.model_dump()
    if data.get("base_unit_id") and not data.get("conversion_factor"):
        raise HTTPException(400, "conversion_factor is required for a compound unit")
    return await crud_create("units_of_measure", data, user=user)


@router.put("/units/{item_id}")
async def update_unit(item_id: str, payload: UnitOfMeasure, user: dict = Depends(get_current_user)):
    _require_inventory(user)
    return await crud_update("units_of_measure", item_id, payload.model_dump(), user=user)


@router.delete("/units/{item_id}")
async def delete_unit(item_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("units_of_measure", item_id, user=user)


# ───────────────────────── Godowns (nestable) ─────────────────────────

@router.get("/godowns")
async def list_godowns(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                       from_date: Optional[str] = None, to_date: Optional[str] = None,
                       user: dict = Depends(get_current_user)):
    _require_inventory(user)
    return await paginated_list("godowns", page=page, limit=limit, q=q,
                                 search_fields=["name", "address"],
                                 sort_field="name", sort_dir=1,
                                 from_date=from_date, to_date=to_date)


@router.post("/godowns")
async def create_godown(payload: Godown, user: dict = Depends(get_current_user)):
    _require_inventory(user)
    data = payload.model_dump()
    if data.get("parent_godown_id"):
        await crud_get("godowns", data["parent_godown_id"])  # 404 if parent missing
    return await crud_create("godowns", data, user=user)


@router.put("/godowns/{item_id}")
async def update_godown(item_id: str, payload: Godown, user: dict = Depends(get_current_user)):
    _require_inventory(user)
    if payload.parent_godown_id == item_id:
        raise HTTPException(400, "A godown cannot be its own parent")
    return await crud_update("godowns", item_id, payload.model_dump(), user=user)


@router.delete("/godowns/{item_id}")
async def delete_godown(item_id: str, user: dict = Depends(require_admin)):
    if await db[LEDGER].find_one({"godown_id": item_id}):
        raise HTTPException(400, "Cannot delete a godown with stock movements")
    return await crud_delete("godowns", item_id, user=user)


# ───────────────────────── Stock Items (master) ─────────────────────────

@router.get("/items")
async def list_items(
    q: Optional[str] = None,
    low_stock: bool = False,
    page: Optional[int] = None,
    limit: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require_inventory(user)
    items = await paginated_list("stock_items", page=page, limit=limit, q=q,
                                  search_fields=["name", "sku", "hsn_sac_code"],
                                  sort_field="name", sort_dir=1,
                                  from_date=from_date, to_date=to_date)
    if low_stock:
        raw = items if isinstance(items, list) else items.get("items", [])
        flagged = []
        for it in raw:
            oh = await on_hand(it["id"])
            if oh["qty"] <= float(it.get("reorder_level", 0)):
                it["on_hand_qty"] = oh["qty"]
                flagged.append(it)
        return flagged
    return items


@router.get("/items/{item_id}")
async def get_item(item_id: str, user: dict = Depends(get_current_user)):
    _require_inventory(user)
    item = await crud_get("stock_items", item_id)
    item["on_hand"] = await on_hand(item_id)
    return item


@router.post("/items")
async def create_item(payload: StockItem, user: dict = Depends(get_current_user)):
    _require_inventory(user)
    data = payload.model_dump()
    item = await crud_create("stock_items", data, user=user)
    # Seed opening stock as an OPENING ledger entry if provided.
    if data.get("opening_stock_qty"):
        qty = float(data["opening_stock_qty"])
        val = float(data.get("opening_stock_value") or 0.0)
        rate = (val / qty) if qty else 0.0
        # Opening stock needs a godown; use the first one if any exists.
        first_godown = await db.godowns.find_one({}, {"_id": 0, "id": 1})
        godown_id = first_godown["id"] if first_godown else "default"
        await post_entry(
            stock_item_id=item["id"], godown_id=godown_id, qty=qty,
            movement_type="OPENING", rate=rate,
            source_doc_type="stock_item", source_doc_id=item["id"], user=user,
        )
    return item


@router.put("/items/{item_id}")
async def update_item(item_id: str, payload: StockItemUpdate, user: dict = Depends(get_current_user)):
    _require_inventory(user)
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    return await crud_update("stock_items", item_id, data, user=user)


@router.delete("/items/{item_id}")
async def delete_item(item_id: str, user: dict = Depends(require_admin)):
    if await db[LEDGER].find_one({"stock_item_id": item_id}):
        raise HTTPException(400, "Cannot delete an item with stock movements")
    return await crud_delete("stock_items", item_id, user=user)


# ───────────────────────── Batches & Serials ─────────────────────────

@router.get("/batches")
async def list_batches(stock_item_id: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                       from_date: Optional[str] = None, to_date: Optional[str] = None,
                       user: dict = Depends(get_current_user)):
    _require_inventory(user)
    filt = {"stock_item_id": stock_item_id} if stock_item_id else None
    return await paginated_list("batches", page=page, limit=limit, filt=filt,
                                 sort_field="created_at", sort_dir=-1,
                                 from_date=from_date, to_date=to_date)


@router.post("/batches")
async def create_batch(payload: Batch, user: dict = Depends(get_current_user)):
    _require_inventory(user)
    item = await crud_get("stock_items", payload.stock_item_id)
    if not (item.get("track_batch") or item.get("track_expiry")):
        raise HTTPException(400, "Item is not batch/expiry tracked")
    return await crud_create("batches", payload.model_dump(), user=user)


@router.get("/serials")
async def list_serials(stock_item_id: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                       from_date: Optional[str] = None, to_date: Optional[str] = None,
                       user: dict = Depends(get_current_user)):
    _require_inventory(user)
    filt = {"stock_item_id": stock_item_id} if stock_item_id else None
    return await paginated_list("serial_numbers", page=page, limit=limit, filt=filt,
                                 sort_field="created_at", sort_dir=-1,
                                 from_date=from_date, to_date=to_date)


@router.post("/serials")
async def create_serial(payload: SerialNumber, user: dict = Depends(get_current_user)):
    _require_inventory(user)
    item = await crud_get("stock_items", payload.stock_item_id)
    if not item.get("track_serial"):
        raise HTTPException(400, "Item is not serial tracked")
    return await crud_create("serial_numbers", payload.model_dump(), user=user)


# ───────────────────────── Movements ─────────────────────────

@router.post("/adjust")
async def adjust_stock(payload: StockAdjustmentIn, user: dict = Depends(get_current_user)):
    _require_inventory(user)
    await crud_get("stock_items", payload.stock_item_id)  # 404 if missing
    await crud_get("godowns", payload.godown_id)
    if payload.qty == 0:
        raise HTTPException(400, "qty must be non-zero")
    if payload.qty > 0 and payload.rate is None:
        raise HTTPException(400, "rate is required for an inward adjustment")
    entry = await post_entry(
        stock_item_id=payload.stock_item_id, godown_id=payload.godown_id,
        qty=payload.qty, movement_type="ADJUSTMENT", rate=payload.rate,
        batch_id=payload.batch_id, source_doc_type="adjustment",
        entry_date=payload.entry_date, user=user,
    )
    return entry


@router.post("/transfers")
async def create_transfer(payload: StockTransfer, user: dict = Depends(get_current_user)):
    _require_inventory(user)
    if payload.from_godown_id == payload.to_godown_id:
        raise HTTPException(400, "Source and destination godowns must differ")
    await crud_get("godowns", payload.from_godown_id)
    await crud_get("godowns", payload.to_godown_id)

    data = payload.model_dump()
    if not data.get("transfer_number"):
        data["transfer_number"] = await next_doc_number("TRF", "stock_transfers")
    data["transfer_date"] = data.get("transfer_date") or date.today().isoformat()
    transfer = await crud_create("stock_transfers", data, user=user)

    # Post paired TRANSFER_OUT (priced by engine) then TRANSFER_IN at same cost.
    for line in data["lines"]:
        out = await post_entry(
            stock_item_id=line["stock_item_id"], godown_id=data["from_godown_id"],
            qty=-abs(line["qty"]), movement_type="TRANSFER_OUT",
            batch_id=line.get("batch_id"), serial_id=line.get("serial_id"),
            source_doc_type="stock_transfer", source_doc_id=transfer["id"],
            entry_date=data["transfer_date"], user=user,
        )
        await post_entry(
            stock_item_id=line["stock_item_id"], godown_id=data["to_godown_id"],
            qty=abs(line["qty"]), movement_type="TRANSFER_IN",
            rate=out["rate"],  # carry the cost that left the source
            batch_id=line.get("batch_id"), serial_id=line.get("serial_id"),
            source_doc_type="stock_transfer", source_doc_id=transfer["id"],
            entry_date=data["transfer_date"], user=user,
        )
    return transfer


@router.get("/transfers")
async def list_transfers(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                         from_date: Optional[str] = None, to_date: Optional[str] = None,
                         user: dict = Depends(get_current_user)):
    _require_inventory(user)
    return await paginated_list("stock_transfers", page=page, limit=limit, q=q,
                                 search_fields=["transfer_number", "remarks"],
                                 sort_field="created_at", sort_dir=-1,
                                 from_date=from_date, to_date=to_date)


# ───────────────────────── Reports ─────────────────────────

def _date_filter(from_date: Optional[str], to_date: Optional[str]) -> dict:
    rng: dict = {}
    if from_date:
        rng["$gte"] = from_date
    if to_date:
        rng["$lte"] = to_date
    return {"entry_date": rng} if rng else {}


@router.get("/reports/stock-summary")
async def stock_summary(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Per item: opening / inward / outward / closing (qty + value), and a per-godown split."""
    _require_inventory(user)
    items = await db.stock_items.find({}, {"_id": 0}).to_list(5000)
    out = []
    for it in items:
        method = it.get("valuation_method", "WEIGHTED_AVG")
        all_entries = await db[LEDGER].find(
            {"stock_item_id": it["id"]}, {"_id": 0}
        ).sort([("entry_date", 1), ("created_at", 1)]).to_list(100000)

        before = [e for e in all_entries if not from_date or e["entry_date"] < from_date]
        in_period = [
            e for e in all_entries
            if (not from_date or e["entry_date"] >= from_date)
            and (not to_date or e["entry_date"] <= to_date)
        ]

        opening = value_movements(before, method)
        closing = value_movements(before + in_period, method)
        inward_qty = sum(e["qty"] for e in in_period if e["qty"] > 0)
        outward_qty = -sum(e["qty"] for e in in_period if e["qty"] < 0)
        inward_val = sum(e["value"] for e in in_period if e["qty"] > 0)
        outward_val = -sum(e["value"] for e in in_period if e["qty"] < 0)

        # Per-godown closing breakdown.
        godown_ids = {e["godown_id"] for e in before + in_period}
        per_godown = []
        for gid in godown_ids:
            g_entries = [e for e in (before + in_period) if e["godown_id"] == gid]
            g_val = value_movements(g_entries, method)
            per_godown.append({
                "godown_id": gid, "qty": g_val.closing_qty, "value": g_val.closing_value,
            })

        out.append({
            "stock_item_id": it["id"], "name": it["name"],
            "valuation_method": method,
            "opening_qty": opening.closing_qty, "opening_value": opening.closing_value,
            "inward_qty": round(inward_qty, 4), "inward_value": round(inward_val, 4),
            "outward_qty": round(outward_qty, 4), "outward_value": round(outward_val, 4),
            "closing_qty": closing.closing_qty, "closing_value": closing.closing_value,
            "per_godown": per_godown,
        })
    return out


@router.get("/reports/movement-analysis")
async def movement_analysis(
    stock_item_id: str = Query(...),
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Raw ledger entries for an item over a period, oldest first."""
    _require_inventory(user)
    q = {"stock_item_id": stock_item_id, **_date_filter(from_date, to_date)}
    entries = await db[LEDGER].find(q, {"_id": 0}).sort(
        [("entry_date", 1), ("created_at", 1)]
    ).to_list(100000)
    return {"stock_item_id": stock_item_id, "entries": entries, "count": len(entries)}


@router.get("/reports/stock-aging")
async def stock_aging(
    as_of_date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Bucket remaining stock by age of its surviving inward layer (FIFO layers)."""
    _require_inventory(user)
    today = date.fromisoformat(as_of_date) if as_of_date else date.today()
    items = await db.stock_items.find({}, {"_id": 0}).to_list(5000)

    buckets_template = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    report = []
    for it in items:
        entries = await db[LEDGER].find(
            {"stock_item_id": it["id"]}, {"_id": 0}
        ).sort([("entry_date", 1), ("created_at", 1)]).to_list(100000)
        # Age always uses FIFO layers, regardless of valuation method, since
        # aging is about the physical age of remaining stock.
        result = value_movements(entries, "FIFO")
        buckets = dict(buckets_template)
        for layer in result.layers:
            try:
                layer_date = date.fromisoformat((layer.entry_date or "")[:10])
                age = (today - layer_date).days
            except ValueError:
                age = 0
            val = layer.qty * layer.rate
            if age <= 30:
                buckets["0-30"] += val
            elif age <= 60:
                buckets["31-60"] += val
            elif age <= 90:
                buckets["61-90"] += val
            else:
                buckets["90+"] += val
        if result.closing_qty > 0:
            report.append({
                "stock_item_id": it["id"], "name": it["name"],
                "closing_qty": result.closing_qty,
                "closing_value": result.closing_value,
                "buckets": {k: round(v, 2) for k, v in buckets.items()},
            })
    return {"as_of_date": today.isoformat(), "items": report}


@router.get("/reports/low-stock")
async def low_stock_alert(user: dict = Depends(get_current_user)):
    """Items whose closing qty <= reorder_level."""
    _require_inventory(user)
    items = await db.stock_items.find({}, {"_id": 0}).to_list(5000)
    alerts = []
    for it in items:
        oh = await on_hand(it["id"])
        reorder = float(it.get("reorder_level", 0))
        if oh["qty"] <= reorder:
            alerts.append({
                "stock_item_id": it["id"], "name": it["name"],
                "closing_qty": oh["qty"], "reorder_level": reorder,
                "reorder_qty": it.get("reorder_qty", 0),
                "shortfall": round(reorder - oh["qty"], 4),
            })
    return alerts
