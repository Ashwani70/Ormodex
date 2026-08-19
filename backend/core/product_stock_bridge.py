"""Product to StockItem bridge — resolves product_id to stock_item_id using MongoDB."""
from typing import Optional

from fastapi import HTTPException

from .db import db
from .stock_ledger import on_hand, on_hand_bulk
from .utils import crud_create, crud_get


async def resolve_godown_id(godown_id: Optional[str]) -> str:
    """Use the given godown, or fall back to the tenant's oldest one.

    Shared by every v1 posting path that predates warehouse selection (manual
    adjustment, opening stock, physical verification, job work, ...). Raises
    rather than inventing a placeholder id — silently attributing a movement
    to a nonexistent/arbitrary godown would corrupt per-godown FIFO/LIFO layer
    scoping in core.stock_ledger.post_entry.
    """
    if godown_id:
        return godown_id
    cursor = db.godowns.find({}, {"_id": 0, "id": 1})
    if hasattr(cursor, "sort"):
        cursor = cursor.sort("created_at", 1)
    godowns = await cursor.to_list(1) if hasattr(cursor, "to_list") else []
    first_godown = godowns[0] if godowns else await db.godowns.find_one({}, {"_id": 0, "id": 1})
    if not first_godown:
        raise HTTPException(status_code=400, detail="No godown exists — create a warehouse/godown first")
    return first_godown["id"]


async def resolve_stock_item_id_for_product(product_id: str, user: Optional[dict] = None) -> str:
    product = await crud_get("products", product_id, label="Product")

    linked = await db.stock_items.find_one({"product_id": product_id})
    if linked:
        return linked["id"]

    sku = (product.get("sku") or "").strip()
    if sku:
        match = await db.stock_items.find_one({
            "sku": sku,
            "$or": [{"product_id": None}, {"product_id": {"$exists": False}}]
        })
        if match:
            await db.stock_items.update_one({"id": match["id"]}, {"$set": {"product_id": product_id}})
            return match["id"]

    stock_item = await crud_create("stock_items", {
        "name": product.get("name") or product_id,
        "item_type": "GOODS",
        "hsn_sac_code": product.get("hsn_code"),
        "gst_rate": float(product.get("gst_rate", 18.0) or 18.0),
        "valuation_method": "WEIGHTED_AVG",
        "sku": sku or None,
        "product_id": product_id,
        "uom": product.get("unit") or "Nos",
    }, user=user)
    return stock_item["id"]


async def resolve_stock_item_ids_for_products(
    product_ids: list[str], user: Optional[dict] = None
) -> dict[str, str]:
    """Batched product_id -> stock_item_id resolution for many products in a
    bounded number of queries, instead of calling resolve_stock_item_id_for_product
    in a loop (an N+1 — up to 3 queries per product: crud_get, stock_items
    lookup, and a possible sku-match/create). Used by every posting loop that
    used to resolve one line at a time (job_work.py's _post_job_work_movements,
    manufacturing.py's complete_work_order/create_production_journal).

    Mirrors resolve_stock_item_id_for_product's own precedence exactly
    (product_id link -> unlinked SKU match -> lazy-create), just batched:
    1) one $in query for products already linked by product_id
    2) one $in query, over the still-unresolved products, for an unlinked
       SKU match (claims it, same as the single-item version)
    3) any products still unresolved fall through to the single-item
       resolver (which lazily creates a stock_items row) — this only costs
       per-product queries for the rare miss, not the common case.
    """
    ids = [pid for pid in dict.fromkeys(product_ids) if pid]
    if not ids:
        return {}

    linked = await db.stock_items.find({"product_id": {"$in": ids}}, {"_id": 0}).to_list(len(ids))
    result: dict[str, str] = {}
    for it in linked:
        pid = it.get("product_id")
        if pid and pid not in result:
            result[pid] = it["id"]

    unresolved_ids = [pid for pid in ids if pid not in result]
    if unresolved_ids:
        products = await db.products.find(
            {"id": {"$in": unresolved_ids}}, {"_id": 0, "id": 1, "sku": 1}
        ).to_list(len(unresolved_ids))
        skus = [s for p in products if (s := (p.get("sku") or "").strip())]
        sku_by_product = {p["id"]: (p.get("sku") or "").strip() for p in products}
        if skus:
            sku_matches = await db.stock_items.find({
                "sku": {"$in": skus},
                "$or": [{"product_id": None}, {"product_id": {"$exists": False}}],
            }, {"_id": 0}).to_list(len(skus))
            match_by_sku: dict[str, dict] = {}
            for it in sku_matches:
                sk = (it.get("sku") or "").strip()
                if sk and sk not in match_by_sku:
                    match_by_sku[sk] = it
            for pid in list(unresolved_ids):
                sku = sku_by_product.get(pid)
                match = match_by_sku.get(sku) if sku else None
                if match:
                    await db.stock_items.update_one(
                        {"id": match["id"]}, {"$set": {"product_id": pid}}
                    )
                    result[pid] = match["id"]
                    unresolved_ids.remove(pid)

    # Rare fallback: products with no existing link and no SKU match need a
    # new stock_items row created — one query per remaining product, same
    # cost the single-item resolver always had for this case.
    for pid in unresolved_ids:
        result[pid] = await resolve_stock_item_id_for_product(pid, user)

    return result


async def find_linked_stock_item(product: dict) -> Optional[dict]:
    """Return the StockItem already linked to a product, WITHOUT creating one.

    Read-only counterpart to resolve_stock_item_id_for_product: used by GET
    endpoints that want live stock-ledger values but must not mutate data. Links
    by product_id first, then by an exact SKU match.
    """
    pid = product.get("id")
    if pid:
        linked = await db.stock_items.find_one({"product_id": pid}, {"_id": 0})
        if linked:
            return linked
    sku = (product.get("sku") or "").strip()
    if sku:
        return await db.stock_items.find_one(
            {"sku": sku, "$or": [{"product_id": None}, {"product_id": {"$exists": False}}]},
            {"_id": 0},
        )
    return None


async def enrich_products_with_live_stock(products: list[dict]) -> list[dict]:
    """Overlay live stock-ledger values onto a list of product dicts.

    For each product linked to a StockItem (by product_id or SKU), replaces:
      • quantity   ← on-hand qty derived from the stock ledger
      • cost_price ← weighted-avg cost (ledger value / qty)
      • gst_rate   ← the linked StockItem's gst_rate
    The product's own value is kept as a fallback when there is no link or no
    movement yet. selling_price is left untouched — it lives only on the product.
    Each enriched product gets `stock_linked: bool` so the UI can show the source.
    """
    for p in products:
        p["stock_linked"] = False
        p["stock_quantity"] = float(p.get("quantity") or 0.0)
    if not products:
        return products

    items_by_pid = await _linked_stock_items_for(products)
    if not items_by_pid:
        for p in products:
            p["stock_quantity"] = float(p.get("quantity") or 0.0)
        return products

    oh_by_sid = await on_hand_bulk([it["id"] for it in items_by_pid.values()])

    for p in products:
        pid = p.get("id")
        if pid is None:
            p["stock_quantity"] = float(p.get("quantity") or 0.0)
            continue
        item = items_by_pid.get(pid)
        if not item:
            p["stock_quantity"] = float(p.get("quantity") or 0.0)
            continue
        p["stock_linked"] = True
        p["stock_item_id"] = item["id"]
        if item.get("gst_rate") is not None:
            p["gst_rate"] = item["gst_rate"]

        wh_id = p.get("warehouse_id")
        oh_bulk = oh_by_sid.get(item["id"]) or {}
        if wh_id:
            oh_godown = await on_hand(item["id"], wh_id)
            g_qty = oh_godown.get("qty", 0.0)
            if g_qty != 0.0 or not oh_bulk.get("qty"):
                qty = g_qty
                val = oh_godown.get("value") or 0.0
            else:
                qty = oh_bulk.get("qty")
                val = oh_bulk.get("value") or 0.0
        else:
            qty = oh_bulk.get("qty")
            val = oh_bulk.get("value") or 0.0

        if qty is not None:
            p["quantity"] = qty
            p["stock_quantity"] = qty
            if qty:
                p["cost_price"] = round(val / qty, 2)
        else:
            p["stock_quantity"] = float(p.get("quantity") or 0.0)
    return products



async def _linked_stock_items_for(products: list[dict]) -> dict[str, dict]:
    """Resolve each product → its linked StockItem in a fixed number of queries.

    Read-only (never creates/links). Mirrors find_linked_stock_item's rules
    (by product_id first, then by an unlinked exact-SKU match) but batched:
    two IN-queries instead of one or two per product. Keyed by product id.
    """
    pids = [pid for p in products if (pid := p.get("id"))]
    if not pids:
        return {}

    # 1) Items already linked by product_id.
    linked = await db.stock_items.find(
        {"product_id": {"$in": pids}}, {"_id": 0}
    ).to_list(len(pids) * 4)
    by_pid: dict[str, dict] = {}
    for it in linked:
        pid = it.get("product_id")
        if pid and pid not in by_pid:
            by_pid[pid] = it

    # 2) For products still unlinked, fall back to an unlinked exact-SKU match.
    unresolved = [p for p in products if p.get("id") and p["id"] not in by_pid]
    skus = [s for p in unresolved if (s := (p.get("sku") or "").strip())]
    if skus:
        sku_items = await db.stock_items.find(
            {"sku": {"$in": skus},
             "$or": [{"product_id": None}, {"product_id": {"$exists": False}}]},
            {"_id": 0},
        ).to_list(len(skus) * 4)
        sku_map: dict[str, dict] = {}
        for it in sku_items:
            sk = (it.get("sku") or "").strip()
            if sk and sk not in sku_map:
                sku_map[sk] = it
        for p in unresolved:
            sk = (p.get("sku") or "").strip()
            if sk and sk in sku_map:
                by_pid[p["id"]] = sku_map[sk]

    return by_pid


async def resolve_line_stock_item(line: dict, user: Optional[dict] = None) -> dict:
    product_id = line.get("product_id")
    if product_id:
        line["stock_item_id"] = await resolve_stock_item_id_for_product(product_id, user)
    return line


TRACKING_KEYS = ("track_batch", "track_serial", "track_expiry")


def _flags_from_item(item) -> dict:
    return {k: bool(item.get(k)) for k in TRACKING_KEYS}


async def stock_item_flags(stock_item_ids: list[str]) -> dict[str, dict]:
    ids = [sid for sid in set(stock_item_ids) if sid]
    if not ids:
        return {}
    items = await db.stock_items.find({"id": {"$in": ids}}).to_list(len(ids))
    return {it["id"]: _flags_from_item(it) for it in items}


async def product_flags(product_ids: list[str]) -> dict[str, dict]:
    pids = [pid for pid in set(product_ids) if pid]
    no_flags = {k: False for k in TRACKING_KEYS}
    if not pids:
        return {}
    # Batch: two IN-queries instead of one find_one per product (was N+1).
    products = await db.products.find({"id": {"$in": pids}}).to_list(len(pids))
    items_by_pid = await _linked_stock_items_for(products)
    flags_by_sid = await stock_item_flags([it["id"] for it in items_by_pid.values()])
    return {
        pid: flags_by_sid.get(items_by_pid[pid]["id"], dict(no_flags))
        if pid in items_by_pid else dict(no_flags)
        for pid in pids
    }


async def line_tracking_flags(lines: list[dict]) -> dict[int, dict]:
    product_ids: list[str] = [pid for ln in lines if (pid := ln.get("product_id"))]
    direct_sids: list[str] = [
        sid for ln in lines
        if not ln.get("product_id") and (sid := ln.get("stock_item_id"))
    ]
    by_pid = await product_flags(product_ids) if product_ids else {}
    by_sid = await stock_item_flags(direct_sids) if direct_sids else {}
    no_flags = {k: False for k in TRACKING_KEYS}

    out = {}
    for idx, ln in enumerate(lines):
        pid = ln.get("product_id")
        sid = ln.get("stock_item_id")
        if pid:
            out[idx] = by_pid.get(pid, dict(no_flags))
        elif sid:
            out[idx] = by_sid.get(sid, dict(no_flags))
        else:
            out[idx] = dict(no_flags)
    return out
