"""Migration 016 — Product ↔ StockItem link.

Adds the ``product_id`` link on stock_items (see core.product_stock_bridge) so
the v2 purchase flow can pick a Product and post against a backing stock_item
without breaking inventory valuation. Backfills the link for any unlinked
stock_item whose ``sku`` matches a product's, so existing catalogs line up
before the first product-keyed purchase.

Idempotent: re-running only links stock_items that aren't linked yet.
"""
import logging

logger = logging.getLogger(__name__)


async def run(db):
    # Index for the bridge's "find stock_item by product_id" lookup. Sparse so
    # the many stock_items without a product link don't bloat the index.
    await db.stock_items.create_index("product_id", sparse=True)

    # Backfill: adopt unlinked stock_items into products by matching SKU.
    products = await db.products.find(
        {"sku": {"$nin": [None, ""]}}, {"_id": 0, "id": 1, "sku": 1}
    ).to_list(100000)
    by_sku: dict[str, str] = {}
    for p in products:
        # First product wins for a given SKU; SKUs are expected unique anyway.
        by_sku.setdefault((p.get("sku") or "").strip(), p["id"])

    linked = 0
    for sku, product_id in by_sku.items():
        res = await db.stock_items.update_one(
            {
                "sku": sku,
                "$or": [{"product_id": None}, {"product_id": {"$exists": False}}],
            },
            {"$set": {"product_id": product_id}},
        )
        linked += res.modified_count
    logger.info("Migration 016: linked %d stock_items to products by SKU", linked)
