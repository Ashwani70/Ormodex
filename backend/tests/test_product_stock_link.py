"""Unit tests for live stock-ledger enrichment of the Products list.

The Products page stores its own frozen quantity/cost/gst, but real stock is
saved via the v2 stock-ledger module. enrich_products_with_live_stock() overlays
the live values from a linked StockItem so the page reflects what was saved
elsewhere; these tests pin that overlay (and its fallbacks).
"""
import asyncio

import pytest

import core.product_stock_bridge as bridge


class _FakeCursor:
    def __init__(self, doc):
        self._doc = doc


async def _run(coro):
    return await coro


@pytest.fixture
def patch_bridge(monkeypatch):
    """Stub the two external dependencies of the enrichment helpers:
    db.stock_items.find_one (the link lookup) and on_hand (the ledger replay)."""
    state = {"stock_items": {}, "on_hand": {}}

    async def fake_find_one(query, projection=None):
        # Match by product_id, then by sku — mirroring find_linked_stock_item.
        if "product_id" in query:
            for it in state["stock_items"].values():
                if it.get("product_id") == query["product_id"]:
                    return it
            return None
        if "sku" in query:
            for it in state["stock_items"].values():
                if it.get("sku") == query["sku"]:
                    return it
            return None
        return None

    def fake_find(query, projection=None):
        results = []
        if "product_id" in query and "$in" in query["product_id"]:
            pids = query["product_id"]["$in"]
            for it in state["stock_items"].values():
                if it.get("product_id") in pids:
                    results.append(it)
        if "sku" in query and "$in" in query["sku"]:
            skus = query["sku"]["$in"]
            for it in state["stock_items"].values():
                if it.get("sku") in skus:
                    results.append(it)
        class Cursor:
            async def to_list(self, limit):
                return [dict(r) for r in results]
        return Cursor()

    async def fake_on_hand_bulk(stock_item_ids):
        return {sid: state["on_hand"].get(sid, {"qty": None, "value": 0.0}) for sid in stock_item_ids}

    monkeypatch.setattr(bridge.db, "stock_items",
                        type("C", (), {
                            "find_one": staticmethod(fake_find_one),
                            "find": staticmethod(fake_find)
                        }))
    monkeypatch.setattr(bridge, "on_hand_bulk", fake_on_hand_bulk)
    return state


def test_linked_product_gets_live_qty_cost_gst(patch_bridge):
    patch_bridge["stock_items"]["si1"] = {
        "id": "si1", "product_id": "p1", "sku": "SKU1", "gst_rate": 12.0,
    }
    patch_bridge["on_hand"]["si1"] = {"qty": 40.0, "value": 8000.0}

    products = [{
        "id": "p1", "sku": "SKU1",
        "quantity": 5, "cost_price": 100, "selling_price": 250, "gst_rate": 18,
    }]
    out = asyncio.run(bridge.enrich_products_with_live_stock(products))[0]

    assert out["stock_linked"] is True
    assert out["quantity"] == 40.0            # live on-hand, not the frozen 5
    assert out["cost_price"] == 200.0         # 8000 / 40 weighted-avg
    assert out["gst_rate"] == 12.0            # from the stock item
    assert out["selling_price"] == 250        # untouched — only lives on product


def test_unlinked_product_keeps_own_values(patch_bridge):
    products = [{
        "id": "p9", "sku": "NOPE",
        "quantity": 7, "cost_price": 100, "selling_price": 250, "gst_rate": 18,
    }]
    out = asyncio.run(bridge.enrich_products_with_live_stock(products))[0]

    assert out["stock_linked"] is False
    assert out["quantity"] == 7
    assert out["cost_price"] == 100
    assert out["gst_rate"] == 18


def test_linked_but_no_movement_keeps_cost_fallback(patch_bridge):
    # Linked item exists but the ledger has zero qty → don't divide by zero,
    # keep the product's own cost_price.
    patch_bridge["stock_items"]["si2"] = {
        "id": "si2", "product_id": "p2", "sku": "SKU2", "gst_rate": 5.0,
    }
    patch_bridge["on_hand"]["si2"] = {"qty": 0.0, "value": 0.0}

    products = [{
        "id": "p2", "sku": "SKU2",
        "quantity": 3, "cost_price": 99, "selling_price": 150, "gst_rate": 18,
    }]
    out = asyncio.run(bridge.enrich_products_with_live_stock(products))[0]

    assert out["stock_linked"] is True
    assert out["gst_rate"] == 5.0       # gst still synced
    assert out["quantity"] == 0.0       # live zero on-hand
    assert out["cost_price"] == 99      # fallback, no divide-by-zero


def test_link_by_sku_when_no_product_id_link(patch_bridge):
    # Stock item not linked by product_id, only an SKU match.
    patch_bridge["stock_items"]["si3"] = {
        "id": "si3", "product_id": None, "sku": "MATCH", "gst_rate": 28.0,
    }
    patch_bridge["on_hand"]["si3"] = {"qty": 10.0, "value": 500.0}

    products = [{
        "id": "pX", "sku": "MATCH",
        "quantity": 1, "cost_price": 10, "selling_price": 80, "gst_rate": 18,
    }]
    out = asyncio.run(bridge.enrich_products_with_live_stock(products))[0]

    assert out["stock_linked"] is True
    assert out["stock_item_id"] == "si3"
    assert out["quantity"] == 10.0
    assert out["cost_price"] == 50.0
    assert out["gst_rate"] == 28.0
