"""Product to StockItem bridge — resolves product_id to stock_item_id using MongoDB."""
from typing import Optional

from .db import db
from .stock_ledger import on_hand
from .utils import crud_create, crud_get


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
    }, user=user)
    return stock_item["id"]


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
        return await db.stock_items.find_one({"sku": sku}, {"_id": 0})
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
        item = await find_linked_stock_item(p)
        if not item:
            continue
        p["stock_linked"] = True
        p["stock_item_id"] = item["id"]
        if item.get("gst_rate") is not None:
            p["gst_rate"] = item["gst_rate"]
        oh = await on_hand(item["id"])
        qty = oh.get("qty")
        if qty is not None:
            p["quantity"] = qty
            value = oh.get("value") or 0.0
            if qty:
                p["cost_price"] = round(value / qty, 2)
    return products


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
    out: dict[str, dict] = {}
    sid_by_pid: dict[str, str] = {}
    for pid in pids:
        sid_by_pid[pid] = await resolve_stock_item_id_for_product(pid)
    flags_by_sid = await stock_item_flags(list(sid_by_pid.values()))
    no_flags = {k: False for k in TRACKING_KEYS}
    for pid, sid in sid_by_pid.items():
        out[pid] = flags_by_sid.get(sid, dict(no_flags))
    return out


async def line_tracking_flags(lines: list[dict]) -> dict[int, dict]:
    product_ids = [ln.get("product_id") for ln in lines if ln.get("product_id")]
    direct_sids = [
        ln.get("stock_item_id") for ln in lines
        if not ln.get("product_id") and ln.get("stock_item_id")
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
