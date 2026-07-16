"""Tests for Purchase Order V2 edit (PUT) and delete (DELETE) endpoints."""
import asyncio
import pytest
from fastapi import HTTPException
import core
import core.db
import core.utils as utils
import core.stock_ledger as sl
import core.po_numbering
from core.purchase_models import PurchaseOrderV2, POLine
from routers.purchase_v2 import create_order, update_order, delete_order

# Reuse the in-memory DB doubles from the GRN test module.
from tests.test_grn_v2 import _DB, USER


def _setup():
    from typing import Any
    db: Any = _DB()
    core.db.db = db
    utils.db = db
    sl.db = db
    core.po_numbering.db = db
    import routers.purchase_v2
    routers.purchase_v2.db = db
    from core import product_stock_bridge
    product_stock_bridge.db = db

    async def mock_crud_create(collection: str, data: dict, user: dict | None = None) -> dict:
        if not data.get("id"):
            data["id"] = utils.new_id()
        doc = dict(data)
        doc.setdefault("created_at", utils.now_iso())
        doc.setdefault("updated_at", utils.now_iso())
        await db[collection].insert_one(doc)
        return doc

    async def mock_crud_get(collection: str, doc_id: str, label: str = "Record") -> dict:
        doc = await db[collection].find_one({"id": doc_id})
        if not doc:
            raise HTTPException(404, f"{label} not found")
        return doc

    async def mock_crud_update(collection: str, doc_id: str, updates: dict, user: dict | None = None, label: str = "Record") -> dict:
        updates = dict(updates)
        updates["updated_at"] = utils.now_iso()
        await db[collection].update_one({"id": doc_id}, {"$set": updates})
        return await mock_crud_get(collection, doc_id, label=label)

    async def mock_crud_delete(collection: str, doc_id: str, user: dict | None = None) -> bool:
        res = await db[collection].delete_one({"id": doc_id})
        return res.deleted_count > 0

    for mod in [routers.purchase_v2, product_stock_bridge]:
        if hasattr(mod, "crud_create"):
            setattr(mod, "crud_create", mock_crud_create)
        if hasattr(mod, "crud_get"):
            setattr(mod, "crud_get", mock_crud_get)
        if hasattr(mod, "crud_update"):
            setattr(mod, "crud_update", mock_crud_update)
        if hasattr(mod, "crud_delete"):
            setattr(mod, "crud_delete", mock_crud_delete)

    return db


def _make_po(db, qty=10.0):
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor 1", "state_code": "27"}))
    asyncio.run(db.stock_items.insert_one({"id": "i1", "name": "Item 1", "valuation_method": "WEIGHTED_AVG"}))
    payload = PurchaseOrderV2(
        vendor_id="v1",
        lines=[POLine(stock_item_id="i1", qty=qty, rate=100.0, gst_rate=18.0)],
    )
    return asyncio.run(create_order(payload, user=USER))


def test_update_order_recomputes_total_and_keeps_po_number():
    db = _setup()
    po = _make_po(db)
    original_number = po["po_number"]

    # Re-submitting the SAME number must not change it (no-op); totals recompute.
    # Deliberate number changes are covered in test_po_numbering.py — they require
    # the po_number_edit permission and a Draft PO, and are audited.
    edit = PurchaseOrderV2(
        po_number=original_number,
        vendor_id="v1",
        lines=[POLine(stock_item_id="i1", qty=5.0, rate=200.0, gst_rate=18.0)],
    )
    updated = asyncio.run(update_order(po["id"], edit, user=USER))

    assert updated["po_number"] == original_number
    assert updated["lines"][0]["qty"] == 5.0
    # 5 * 200 * 1.18 = 1180.0
    assert updated["total"] == 1180.0
    assert updated["lines"][0]["received_qty"] == 0.0


def test_update_order_blocked_after_receipt():
    db = _setup()
    po = _make_po(db)
    # Simulate goods received against the line.
    asyncio.run(db.purchase_orders_v2.update_one(
        {"id": po["id"]},
        {"$set": {"lines": [{**po["lines"][0], "received_qty": 4.0}]}},
    ))

    edit = PurchaseOrderV2(vendor_id="v1", lines=[POLine(stock_item_id="i1", qty=3.0, rate=100.0)])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_order(po["id"], edit, user=USER))
    assert exc.value.status_code == 400
    assert "received goods" in exc.value.detail


def test_update_unknown_order_returns_named_404():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor 1"}))
    edit = PurchaseOrderV2(vendor_id="v1", lines=[POLine(stock_item_id="i1", qty=1.0, rate=10.0)])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(update_order("nope", edit, user=USER))
    assert exc.value.status_code == 404
    assert exc.value.detail == "Purchase order not found"


def test_delete_order_succeeds_when_unreceived():
    db = _setup()
    po = _make_po(db)
    res = asyncio.run(delete_order(po["id"], user=USER))
    # crud_delete returns a truthy bool on success (or a dict for soft-delete paths).
    assert res is True or (isinstance(res, dict) and (res.get("ok") or res.get("soft_deleted")))
    assert asyncio.run(db.purchase_orders_v2.find_one({"id": po["id"]})) is None


def test_delete_order_blocked_after_receipt():
    db = _setup()
    po = _make_po(db)
    asyncio.run(db.purchase_orders_v2.update_one(
        {"id": po["id"]},
        {"$set": {"lines": [{**po["lines"][0], "received_qty": 2.0}]}},
    ))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_order(po["id"], user=USER))
    assert exc.value.status_code == 400
    assert "received goods" in exc.value.detail


def test_delete_order_blocked_when_grn_linked():
    db = _setup()
    po = _make_po(db)
    asyncio.run(db.goods_receipt_notes_v2.insert_one({"id": "grn1", "purchase_order_id": po["id"]}))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(delete_order(po["id"], user=USER))
    assert exc.value.status_code == 400
    assert "goods receipt note" in exc.value.detail
