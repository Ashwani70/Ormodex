"""Inventory v2 — Tally-style stock ledger: masters, movements, transfers, reports.

Mounted at /inventory/v2 to coexist with the legacy flat inventory router. Stock
qty/value are always derived from the StockLedgerEntry via the valuation engine.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core import cache
from core.auth_utils import get_current_user, require_admin, is_admin_role
from core.db import db
from core.inventory_models import (
    Batch, Godown, SerialNumber, StockAdjustmentIn, StockItem, StockItemUpdate,
    StockTransfer, UnitOfMeasure,
)
from core.product_stock_bridge import product_flags, resolve_godown_id, resolve_line_stock_item, stock_item_flags
from core.stock_ledger import (
    LEDGER, item_valuation_configs, on_hand, on_hand_bulk, post_entry,
)
from core.stock_valuation import DEFAULT_METHOD, value_movements
from core.tenant import resolve_tenant


def _value(movements: list[dict], cfg: tuple[str, float] | None):
    """Value a movement list under a resolved (method, standard_cost) config.

    Central helper so every report/aggregation site prices LIFO and
    Standard-Cost items correctly (threading standard_cost) and stays robust to
    an unset/unknown stored method — instead of each site re-deriving it.
    """
    method, std = cfg or (DEFAULT_METHOD, 0.0)
    return value_movements(movements, method, standard_cost=std)
from core.tracking_validation import validate_tracking_fields
from core.utils import (
    crud_create, crud_delete, crud_get, crud_update, new_id, next_doc_number,
    paginated_list,
)
from pydantic import BaseModel


class TrackingFlagsQuery(BaseModel):
    product_ids: list[str] = []
    stock_item_ids: list[str] = []

router = APIRouter(prefix="/inventory/v2", tags=["Inventory v2"])


def _require_inventory(user: dict) -> dict:
    if is_admin_role(user.get("role")):
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


# ───────────────────────── Warehouses / Godowns (nestable) ─────────────────────────
# The `godowns` table is the single warehouse master. The enterprise fields
# (type, location, inventory settings, bins, security, documents) ride in the
# `extra` JSONB column via the crud_* overflow packing, so no schema migration
# is needed and every existing consumer (GRN, transfers, stock log, pricing)
# keeps working off name/address/parent_godown_id.


async def _next_warehouse_code() -> str:
    return await next_doc_number("WH", "godowns")


def _assign_bin_ids(bins: list[dict]) -> list[dict]:
    """Ensure every bin has an id and a barcode (defaults to its code)."""
    for b in bins or []:
        if not b.get("id"):
            b["id"] = new_id()
        if not b.get("barcode"):
            b["barcode"] = b.get("code")
    return bins or []


@router.get("/godowns")
async def list_godowns(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                       from_date: Optional[str] = None, to_date: Optional[str] = None,
                       user: dict = Depends(get_current_user)):
    _require_inventory(user)
    return await paginated_list("godowns", page=page, limit=limit, q=q,
                                 search_fields=["name", "address", "code", "short_name", "city"],
                                 sort_field="name", sort_dir=1,
                                 from_date=from_date, to_date=to_date)


@router.get("/godowns/{item_id}")
async def get_godown(item_id: str, user: dict = Depends(get_current_user)):
    """One warehouse with its live stock value + on-hand item count."""
    _require_inventory(user)
    wh = await crud_get("godowns", item_id, label="Warehouse")
    entries = await db[LEDGER].find({"godown_id": item_id}, {"_id": 0}).sort(
        [("entry_date", 1), ("created_at", 1)]
    ).to_list(1000000)
    by_item: dict[str, list[dict]] = {}
    for e in entries:
        sid = e.get("stock_item_id")
        if sid:
            by_item.setdefault(sid, []).append(e)
    cfgs = await item_valuation_configs(list(by_item), resolve_tenant(user)) if by_item else {}
    stock_value = 0.0
    active_items = 0
    for sid, evs in by_item.items():
        res = _value(evs, cfgs.get(sid))
        stock_value += res.closing_value
        if res.closing_qty > 0:
            active_items += 1
    wh["stock_value"] = round(stock_value, 2)
    wh["active_item_count"] = active_items
    return wh


@router.post("/godowns")
async def create_godown(payload: Godown, user: dict = Depends(get_current_user)):
    _require_inventory(user)
    data = payload.model_dump()
    if data.get("parent_godown_id"):
        await crud_get("godowns", data["parent_godown_id"])  # 404 if parent missing
    if not data.get("code"):
        data["code"] = await _next_warehouse_code()
    data["bins"] = _assign_bin_ids(data.get("bins") or [])
    return await crud_create("godowns", data, user=user)


@router.put("/godowns/{item_id}")
async def update_godown(item_id: str, payload: Godown, user: dict = Depends(require_admin)):
    if payload.parent_godown_id == item_id:
        raise HTTPException(400, "A warehouse cannot be its own parent")
    data = payload.model_dump()
    existing = await crud_get("godowns", item_id, label="Warehouse")
    # Preserve the immutable code once assigned.
    if not data.get("code"):
        data["code"] = existing.get("code") or await _next_warehouse_code()
    data["bins"] = _assign_bin_ids(data.get("bins") or [])
    return await crud_update("godowns", item_id, data, user=user, label="Warehouse")


@router.delete("/godowns/{item_id}")
async def delete_godown(
    item_id: str,
    force: bool = Query(False, description="Force delete godown and cascade delete all its stock movements / transfers"),
    user: dict = Depends(require_admin)
):
    if not force:
        # Block deletion if the godown has any ledger entries, transactions, transfers, or physical verifications.
        if (
            await db[LEDGER].find_one({"godown_id": item_id})
            or await db["stock_transactions"].find_one({"godown_id": item_id})
            or await db["stock_transfers"].find_one({"$or": [{"from_godown_id": item_id}, {"to_godown_id": item_id}]})
            or await db["physical_verifications"].find_one({"godown_id": item_id})
        ):
            raise HTTPException(400, "Cannot delete a warehouse with stock movements")
    else:
        # Clean up related records
        await db[LEDGER].delete_many({"godown_id": item_id})
        await db["stock_transactions"].delete_many({"godown_id": item_id})
        await db["stock_transfers"].delete_many({"$or": [{"from_godown_id": item_id}, {"to_godown_id": item_id}]})
        await db["physical_verifications"].delete_many({"godown_id": item_id})

    return await crud_delete("godowns", item_id, user=user)


@router.get("/warehouses/next-code")
async def peek_warehouse_code(user: dict = Depends(get_current_user)):
    """Preview the next auto-generated warehouse code without consuming it.

    Uses the same WH##### format the create endpoint assigns. The count-based
    preview is advisory only; the create endpoint mints the authoritative code
    from the atomic sequence, so a preview may differ under concurrent creates.
    """
    _require_inventory(user)
    n = await db.godowns.count_documents({})
    return {"code": f"WH{n + 1:05d}"}


# ───────────────────────── Warehouse dashboard & AI insights ─────────────────────────


async def _warehouse_stock_index() -> dict:
    """Compute per-warehouse and per-(warehouse,item) closing qty+value in a
    bounded number of queries, plus today's inward/outward movement counts.

    Returns a dict:
      { "by_wh": {wh_id: {value, item_count, low_stock, out_of_stock}},
        "wh_item": {(wh_id, item_id): {qty, value, method, item_name, reorder}},
        "today_in": int, "today_out": int, "movement_value": float }
    """
    items = await db.stock_items.find({}, {"_id": 0}).to_list(20000)
    cfg_by_id = await item_valuation_configs([it["id"] for it in items])
    name_by_id = {it["id"]: it.get("name", "") for it in items}
    reorder_by_id = {it["id"]: float(it.get("reorder_level") or 0) for it in items}

    entries = await db[LEDGER].find({}, {"_id": 0}).sort(
        [("entry_date", 1), ("created_at", 1)]
    ).to_list(2000000)

    grouped: dict[tuple, list[dict]] = {}
    today = date.today().isoformat()
    today_in = today_out = 0
    for e in entries:
        key = (e.get("godown_id"), e.get("stock_item_id"))
        grouped.setdefault(key, []).append(e)
        if (e.get("entry_date") or "")[:10] == today:
            if (e.get("qty") or 0) > 0:
                today_in += 1
            elif (e.get("qty") or 0) < 0:
                today_out += 1

    wh_item: dict[tuple, dict] = {}
    by_wh: dict[str, dict] = {}
    for (wh_id, item_id), evs in grouped.items():
        res = _value(evs, cfg_by_id.get(item_id))
        wh_item[(wh_id, item_id)] = {
            "qty": res.closing_qty, "value": res.closing_value,
            "item_name": name_by_id.get(item_id, ""),
            "reorder": reorder_by_id.get(item_id, 0.0),
        }
        agg = by_wh.setdefault(wh_id, {"value": 0.0, "item_count": 0, "low_stock": 0, "out_of_stock": 0})
        agg["value"] += res.closing_value
        if res.closing_qty > 0:
            agg["item_count"] += 1
            if res.closing_qty <= reorder_by_id.get(item_id, 0.0):
                agg["low_stock"] += 1
        elif res.closing_qty <= 0:
            agg["out_of_stock"] += 1
    return {"by_wh": by_wh, "wh_item": wh_item, "today_in": today_in, "today_out": today_out}


@router.get("/warehouses/dashboard")
async def warehouse_dashboard(user: dict = Depends(get_current_user)):
    """KPI + chart data for the Warehouse dashboard header.

    Cached (TTL_DASHBOARD, keyed by the "stock" cache generation): this does
    5 DB round-trips including two full stock_ledger_entries scans, and every
    round-trip costs ~260ms cross-region (see core/cache.py's WHY note) — an
    uncached load was measured taking long enough to trip the frontend's 30s
    axios timeout and surface as a generic "Something went wrong" failure.
    The generation bumps on every stock_ledger_entries/stock_items/products
    write (core/_mongo_compat.py _STOCK_GEN_COLLECTIONS), so a fresh post_entry
    invalidates this immediately rather than serving stale KPIs.
    """
    _require_inventory(user)
    return await cache.get_or_set(
        f"warehouse_dashboard:{cache.generation('stock')}",
        cache.TTL_DASHBOARD, _compute_warehouse_dashboard,
    )


async def _compute_warehouse_dashboard() -> dict:
    warehouses = await db.godowns.find({}, {"_id": 0}).to_list(5000)
    idx = await _warehouse_stock_index()
    by_wh = idx["by_wh"]

    total_value = sum(v["value"] for v in by_wh.values())
    total_low = sum(v["low_stock"] for v in by_wh.values())
    total_out = sum(v["out_of_stock"] for v in by_wh.values())

    pending_transfers = await db.stock_transfers.count_documents({"status": {"$in": ["PENDING", "IN_TRANSIT", None]}})

    # Per-warehouse occupancy heat-map cells (value share vs. max).
    max_val = max((v["value"] for v in by_wh.values()), default=0.0) or 1.0
    heat = []
    for wh in warehouses:
        cell = by_wh.get(wh["id"], {"value": 0.0, "item_count": 0, "low_stock": 0, "out_of_stock": 0})
        heat.append({
            "id": wh["id"], "name": wh.get("name", ""), "code": wh.get("code"),
            "type": wh.get("warehouse_type", "MAIN"),
            "status": wh.get("status", "ACTIVE"),
            "value": round(cell["value"], 2),
            "item_count": cell["item_count"],
            "low_stock": cell["low_stock"],
            "occupancy": round(min(100.0, cell["value"] / max_val * 100.0), 1),
        })
    heat.sort(key=lambda c: c["value"], reverse=True)

    # 30-day stock-movement chart (net value in/out per day).
    from datetime import timedelta
    start = (date.today() - timedelta(days=29)).isoformat()
    recent = await db[LEDGER].find(
        {"entry_date": {"$gte": start}}, {"_id": 0, "entry_date": 1, "qty": 1, "value": 1}
    ).to_list(500000)
    days: dict[str, dict] = {}
    for i in range(30):
        d = (date.today() - timedelta(days=29 - i)).isoformat()
        days[d] = {"date": d, "inward": 0.0, "outward": 0.0}
    for e in recent:
        d = (e.get("entry_date") or "")[:10]
        if d in days:
            val = abs(float(e.get("value") or 0))
            if (e.get("qty") or 0) >= 0:
                days[d]["inward"] += val
            else:
                days[d]["outward"] += val
    movement_chart = [
        {**v, "inward": round(v["inward"], 2), "outward": round(v["outward"], 2)}
        for v in days.values()
    ]

    return {
        "total_warehouses": len(warehouses),
        "active_warehouses": sum(1 for w in warehouses if w.get("status", "ACTIVE") == "ACTIVE"),
        "total_inventory_value": round(total_value, 2),
        "low_stock": total_low,
        "out_of_stock": total_out,
        "pending_transfers": pending_transfers,
        "today_receipts": idx["today_in"],
        "today_dispatch": idx["today_out"],
        "occupancy": round(sum(c["occupancy"] for c in heat) / len(heat), 1) if heat else 0.0,
        "heat_map": heat,
        "movement_chart": movement_chart,
    }


@router.get("/warehouses/{item_id}/insights")
async def warehouse_insights(item_id: str, user: dict = Depends(get_current_user)):
    """AI-style operational insights for a single warehouse, derived from the
    stock ledger (no LLM call — deterministic analytics)."""
    _require_inventory(user)
    wh = await crud_get("godowns", item_id, label="Warehouse")

    entries = await db[LEDGER].find({"godown_id": item_id}, {"_id": 0}).sort(
        [("entry_date", 1), ("created_at", 1)]
    ).to_list(1000000)
    item_ids = list({e.get("stock_item_id") for e in entries if e.get("stock_item_id")})
    items = await db.stock_items.find({"id": {"$in": item_ids}}, {"_id": 0}).to_list(len(item_ids) or 1) if item_ids else []
    item_by_id = {it["id"]: it for it in items}
    cfg_by_id = await item_valuation_configs(item_ids, resolve_tenant(user))

    by_item: dict[str, list[dict]] = {}
    for e in entries:
        sid = e.get("stock_item_id")
        if sid:
            by_item.setdefault(sid, []).append(e)

    from datetime import timedelta
    cutoff_90 = (date.today() - timedelta(days=90)).isoformat()
    cutoff_30 = (date.today() - timedelta(days=30)).isoformat()

    stock_value = 0.0
    dead_stock = []            # positive qty but no outward movement in 90d
    fast_moving = []           # by outward qty in last 30d
    slow_moving = []           # positive qty, low turnover in 30d
    reorder_suggestions = []
    stockout_risk = []

    for sid, evs in by_item.items():
        it = item_by_id.get(sid, {})
        res = _value(evs, cfg_by_id.get(sid))
        qty, val = res.closing_qty, res.closing_value
        stock_value += val
        name = it.get("name", sid)
        reorder = float(it.get("reorder_level") or 0)

        out_30 = -sum(float(e.get("qty") or 0) for e in evs
                      if (e.get("qty") or 0) < 0 and (e.get("entry_date") or "")[:10] >= cutoff_30)
        out_90 = -sum(float(e.get("qty") or 0) for e in evs
                      if (e.get("qty") or 0) < 0 and (e.get("entry_date") or "")[:10] >= cutoff_90)

        if qty > 0 and out_90 <= 0:
            dead_stock.append({"stock_item_id": sid, "name": name, "qty": qty, "value": round(val, 2)})
        if out_30 > 0:
            fast_moving.append({"stock_item_id": sid, "name": name, "out_30d": round(out_30, 2)})
        if qty > 0 and out_30 < max(1.0, reorder * 0.1):
            slow_moving.append({"stock_item_id": sid, "name": name, "qty": qty, "out_30d": round(out_30, 2)})
        if reorder and qty <= reorder:
            reorder_suggestions.append({
                "stock_item_id": sid, "name": name, "on_hand": qty,
                "reorder_level": reorder,
                "suggested_qty": float(it.get("reorder_qty") or 0) or round(max(reorder - qty, reorder), 2),
            })
        # Days-of-cover: on-hand / avg daily consumption over 30d.
        daily = out_30 / 30.0
        if daily > 0:
            days_cover = qty / daily
            if days_cover < 14:
                stockout_risk.append({
                    "stock_item_id": sid, "name": name,
                    "days_cover": round(days_cover, 1),
                    "expected_stockout": (date.today() + timedelta(days=int(days_cover))).isoformat(),
                })

    fast_moving.sort(key=lambda x: x["out_30d"], reverse=True)
    slow_moving.sort(key=lambda x: x["out_30d"])
    dead_stock.sort(key=lambda x: x["value"], reverse=True)
    stockout_risk.sort(key=lambda x: x["days_cover"])

    # Inventory health score: penalise dead + out-of-cover, reward turnover.
    active = sum(1 for evs in by_item.values() if value_movements(evs, "WEIGHTED_AVG").closing_qty > 0) or 1
    health = 100.0
    health -= min(40.0, len(dead_stock) / active * 100.0 * 0.6)
    health -= min(30.0, len(stockout_risk) / active * 100.0 * 0.5)
    health -= min(15.0, len(reorder_suggestions) / active * 100.0 * 0.3)
    health = round(max(0.0, health), 0)

    # Storage utilisation: on-hand qty vs. sum of bin capacities (if bins have capacity).
    bin_capacity = sum(float(b.get("capacity") or 0) for b in (wh.get("bins") or []))
    total_qty = sum(value_movements(evs, "WEIGHTED_AVG").closing_qty for evs in by_item.values())
    utilisation = round(min(100.0, total_qty / bin_capacity * 100.0), 1) if bin_capacity else None

    return {
        "warehouse_id": item_id,
        "warehouse_name": wh.get("name"),
        "stock_value": round(stock_value, 2),
        "storage_utilisation": utilisation,
        "inventory_health_score": health,
        "dead_stock": dead_stock[:20],
        "fast_moving": fast_moving[:10],
        "slow_moving": slow_moving[:10],
        "reorder_suggestions": reorder_suggestions[:20],
        "expected_stockout": stockout_risk[:20],
    }


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
        if isinstance(raw, list) and raw:
            item_ids = [it["id"] for it in raw if it.get("id")]
            bulk_oh = await on_hand_bulk(item_ids)
            for it in raw:
                oh = bulk_oh.get(it["id"], {"qty": 0.0})
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
        godown_id = await resolve_godown_id(None)
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


@router.post("/tracking-flags")
async def tracking_flags(payload: TrackingFlagsQuery, user: dict = Depends(get_current_user)):
    """Resolve batch/serial/expiry tracking flags for a set of products and/or
    stock items, so the UI can show (and require) the right fields per line.

    Keys in the response are the ids the caller supplied: product ids under
    ``products`` (resolved through the product→stock_item bridge), stock-item
    ids under ``stock_items``. Each value is
    {track_batch, track_serial, track_expiry}.
    """
    _require_inventory(user)
    return {
        "products": await product_flags(payload.product_ids),
        "stock_items": await stock_item_flags(payload.stock_item_ids),
    }


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
    line = payload.model_dump()
    # Resolve product_id → backing stock_item_id (no-op for legacy stock_item_id).
    await resolve_line_stock_item(line, user)
    if not line.get("stock_item_id"):
        raise HTTPException(400, "product_id or stock_item_id is required")
    await crud_get("stock_items", line["stock_item_id"])  # 404 if missing
    await crud_get("godowns", payload.godown_id)
    if payload.qty == 0:
        raise HTTPException(400, "qty must be non-zero")
    if payload.qty > 0 and payload.rate is None:
        raise HTTPException(400, "rate is required for an inward adjustment")
    # Enforce batch/serial/expiry per the stock_item's tracking flags.
    await validate_tracking_fields([line])
    entry = await post_entry(
        stock_item_id=line["stock_item_id"], godown_id=payload.godown_id,
        qty=payload.qty, movement_type="ADJUSTMENT", rate=payload.rate,
        batch_id=line.get("batch_id"), serial_id=line.get("serial_id"),
        source_doc_type="adjustment",
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
    # Resolve product_id → backing stock_item_id on each line, then enforce
    # batch/serial/expiry per the stock_item's tracking flags before posting.
    for line in data["lines"]:
        await resolve_line_stock_item(line, user)
        if not line.get("stock_item_id"):
            raise HTTPException(400, "Each transfer line needs a product_id or stock_item_id")
    await validate_tracking_fields(data["lines"])
    if not data.get("transfer_number"):
        data["transfer_number"] = await next_doc_number("TRF", "stock_transfers")
    data["transfer_date"] = data.get("transfer_date") or date.today().isoformat()
    transfer = await crud_create("stock_transfers", data, user=user)

    # Post paired TRANSFER_OUT (priced by engine) then TRANSFER_IN at same cost.
    # post_entry mirrors each posting into stock_transactions itself (see
    # core/stock_ledger.py's dual-write note), so the Stock Log grid picks up
    # both legs automatically — no manual mirroring needed here.
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
    cfg_by_id = await item_valuation_configs([it["id"] for it in items], resolve_tenant(user))

    # Batch-read every item's ledger history in ONE query instead of a
    # find_one-per-item loop (was a genuine N+1 — 1 + N round-trips, each
    # ~260ms cross-region, see core/cache.py's WHY note — timing out the
    # frontend's 30s axios timeout with even a modest item count). Mirrors
    # the batched pattern stock_aging already uses below.
    item_ids = [it["id"] for it in items if it.get("id")]
    all_ledger_entries = await db[LEDGER].find(
        {"stock_item_id": {"$in": item_ids}}, {"_id": 0}
    ).sort([("entry_date", 1), ("created_at", 1)]).to_list(1000000) if item_ids else []
    entries_by_item: dict[str, list[dict]] = {sid: [] for sid in item_ids}
    for e in all_ledger_entries:
        sid = e.get("stock_item_id")
        if sid in entries_by_item:
            entries_by_item[sid].append(e)

    out = []
    for it in items:
        cfg = cfg_by_id.get(it["id"])
        method = (cfg or (DEFAULT_METHOD, 0.0))[0]
        all_entries = entries_by_item.get(it["id"], [])

        def _safe_date(e: dict) -> str:
            return e.get("entry_date") or "9999-12-31"

        before = [e for e in all_entries if not from_date or _safe_date(e) < from_date]
        in_period = [
            e for e in all_entries
            if (not from_date or _safe_date(e) >= from_date)
            and (not to_date or _safe_date(e) <= to_date)
        ]

        opening = _value(before, cfg)
        closing = _value(before + in_period, cfg)
        inward_qty = sum(float(e.get("qty") or 0) for e in in_period if (e.get("qty") or 0) > 0)
        outward_qty = -sum(float(e.get("qty") or 0) for e in in_period if (e.get("qty") or 0) < 0)
        inward_val = sum(float(e.get("value") or 0) for e in in_period if (e.get("qty") or 0) > 0)
        outward_val = -sum(float(e.get("value") or 0) for e in in_period if (e.get("qty") or 0) < 0)

        # Per-godown closing breakdown.
        godown_ids = {e["godown_id"] for e in before + in_period if e.get("godown_id")}
        per_godown = []
        for gid in godown_ids:
            g_entries = [e for e in (before + in_period) if e.get("godown_id") == gid]
            g_val = _value(g_entries, cfg)
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
    ).to_list(50000)
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
    if not items:
        return {"as_of_date": today.isoformat(), "items": []}

    item_ids = [it["id"] for it in items if it.get("id")]
    all_entries = await db[LEDGER].find(
        {"stock_item_id": {"$in": item_ids}}, {"_id": 0}
    ).sort([("entry_date", 1), ("created_at", 1)]).to_list(1000000)

    entries_by_item: dict[str, list[dict]] = {sid: [] for sid in item_ids}
    for e in all_entries:
        sid = e.get("stock_item_id")
        if sid in entries_by_item:
            entries_by_item[sid].append(e)

    buckets_template = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    report = []
    for it in items:
        entries = entries_by_item.get(it["id"], [])
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
    if not items:
        return []
    
    item_ids = [it["id"] for it in items if it.get("id")]
    bulk_oh = await on_hand_bulk(item_ids)
    
    alerts = []
    for it in items:
        oh = bulk_oh.get(it["id"], {"qty": 0.0})
        reorder = float(it.get("reorder_level", 0))
        if oh["qty"] <= reorder:
            alerts.append({
                "stock_item_id": it["id"], "name": it["name"],
                "closing_qty": oh["qty"], "reorder_level": reorder,
                "reorder_qty": it.get("reorder_qty", 0),
                "shortfall": round(reorder - oh["qty"], 4),
            })
    return alerts
