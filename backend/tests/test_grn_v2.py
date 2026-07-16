"""Tests for Goods Receipt Note (GRN) V2 creation and PO status updates."""
import asyncio
import pytest
from fastapi import HTTPException
import core
import core.db
import core.utils as utils
import core.stock_ledger as sl
import core.po_numbering
from core.purchase_models import PurchaseOrderV2, POLine, GRNV2, GRNLine, PurchaseReturn, ReturnLine
from routers.purchase_v2 import create_order, create_grn, create_return

class _Cursor:
    def __init__(self, docs):
        self._docs = docs
    def sort(self, *a, **k):
        return self
    def limit(self, n):
        self._docs = self._docs[:n]
        return self
    async def to_list(self, _n):
        return [dict(d) for d in self._docs]

def _match_value(actual, expected):
    """Support a small subset of Mongo query operators used by the app/tests."""
    if isinstance(expected, dict):
        for op, val in expected.items():
            if op == "$ne":
                if actual == val:
                    return False
            elif op == "$type":
                want_str = val == "string" or (isinstance(val, (list, tuple)) and "string" in val)
                if want_str and not isinstance(actual, str):
                    return False
            else:  # unknown operator — fall back to equality on the dict
                return actual == expected
        return True
    return actual == expected


def _doc_matches(d, q):
    return all(_match_value(d.get(k), v) for k, v in q.items())


def _apply_update(doc, update, inserted=False):
    for k, v in update.get("$set", {}).items():
        doc[k] = v
    for k, v in update.get("$inc", {}).items():
        doc[k] = doc.get(k, 0) + v
    if inserted:
        for k, v in update.get("$setOnInsert", {}).items():
            doc[k] = v


class _Collection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc, session=None):
        doc = dict(doc)
        if "_id" not in doc:
            doc["_id"] = doc.get("id")
        self.docs.append(doc)
        return type("R", (), {"inserted_id": doc.get("id")})()

    async def find_one(self, q, projection=None, session=None):
        for d in self.docs:
            if _doc_matches(d, q):
                out = dict(d)
                out.pop("_id", None)
                return out
        return None

    def find(self, q=None, projection=None):
        q = q or {}
        return _Cursor([d for d in self.docs if _doc_matches(d, q)])

    async def count_documents(self, q):
        return len([d for d in self.docs if _doc_matches(d, q)])

    async def create_index(self, *a, **k):
        return None

    async def find_one_and_update(self, q, update, upsert=False, return_document=True):
        for d in self.docs:
            if _doc_matches(d, q):
                _apply_update(d, update, inserted=False)
                return dict(d)
        if upsert:
            doc = {k: v for k, v in q.items() if not isinstance(v, dict)}
            _apply_update(doc, update, inserted=True)
            self.docs.append(doc)
            return dict(doc)
        return None

    async def update_one(self, q, update, session=None, upsert=False):
        for d in self.docs:
            if _doc_matches(d, q):
                _apply_update(d, update, inserted=False)
                return type("R", (), {"modified_count": 1})()
        if upsert:
            doc = {k: v for k, v in q.items() if not isinstance(v, dict)}
            _apply_update(doc, update, inserted=True)
            self.docs.append(doc)
            return type("R", (), {"modified_count": 0, "upserted_id": doc.get("id")})()
        return type("R", (), {"modified_count": 0})()

    async def delete_one(self, q, session=None):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in q.items()):
                del self.docs[i]
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

class _DB:
    def __init__(self):
        self._cols = {}
    def __getitem__(self, name):
        return self._cols.setdefault(name, _Collection())
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

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

USER = {"id": "u1", "name": "T", "role": "admin"}

def test_grn_creation_updates_stock_and_po():
    db = _setup()
    
    # 1. Insert minimum data
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor 1", "state_code": "27"}))
    asyncio.run(db.stock_items.insert_one({"id": "i1", "name": "Item 1", "valuation_method": "WEIGHTED_AVG"}))
    asyncio.run(db.godowns.insert_one({"id": "g1", "name": "Main Godown"}))
    
    # 2. Create Purchase Order
    po_payload = PurchaseOrderV2(
        vendor_id="v1",
        expected_date="2026-06-30",
        lines=[
            POLine(stock_item_id="i1", qty=10.0, rate=100.0, gst_rate=18.0)
        ]
    )
    po = asyncio.run(create_order(po_payload, user=USER))
    assert po is not None
    assert po["status"] == "DRAFT"
    
    # Simulate PO sent to vendor
    asyncio.run(db.purchase_orders_v2.update_one({"id": po["id"]}, {"$set": {"status": "SENT"}}))
    
    # 3. Create GRN receiving 4 items (partial receipt)
    grn_payload = GRNV2(
        purchase_order_id=po["id"],
        vendor_id="v1",
        godown_id="g1",
        received_date="2026-06-21",
        lines=[
            GRNLine(stock_item_id="i1", po_line_index=0, qty_received=4.0, rate=100.0, gst_rate=18.0)
        ]
    )
    
    grn = asyncio.run(create_grn(grn_payload, user=USER))
    assert grn is not None
    
    # Verify stock ledger entries
    ledger_entries = db.stock_ledger_entries.docs
    assert len(ledger_entries) == 1
    assert ledger_entries[0]["stock_item_id"] == "i1"
    assert ledger_entries[0]["qty"] == 4.0
    assert ledger_entries[0]["rate"] == 100.0
    
    # Verify PO v2 received qty and status
    po_updated = asyncio.run(db.purchase_orders_v2.find_one({"id": po["id"]}))
    assert po_updated is not None
    assert po_updated["status"] == "PARTIALLY_RECEIVED"
    assert po_updated["lines"][0]["received_qty"] == 4.0
    
    # Verify if grn in db has stock_ledger_entry_ids saved
    grn_db = asyncio.run(db.goods_receipt_notes_v2.find_one({"id": grn["id"]}))
    assert grn_db is not None
    assert "stock_ledger_entry_ids" in grn_db
    assert len(grn_db["stock_ledger_entry_ids"]) == 1
    assert grn_db["stock_ledger_entry_ids"][0] == ledger_entries[0]["id"]


def test_purchase_return_creation_updates_stock_and_ids():
    db = _setup()
    
    # Insert minimum data
    asyncio.run(db.companies.insert_one({"id": "c1", "state_code": "27"}))
    asyncio.run(db.fiscal_years.insert_one({"id": "fy", "name": "2026-27", "is_active": True}))
    for code, name in [("1200", "Inventory"), ("1500", "GST Input Tax Credit"),
                       ("2001", "Accounts Payable"), ("2006", "TDS Payable")]:
        asyncio.run(db.chart_of_accounts.insert_one({"id": code, "code": code, "name": name}))
        
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor 1", "state_code": "27"}))
    asyncio.run(db.stock_items.insert_one({"id": "i1", "name": "Item 1", "valuation_method": "WEIGHTED_AVG"}))
    asyncio.run(db.godowns.insert_one({"id": "g1", "name": "Main Godown"}))
    
    # Create a Purchase Return
    return_payload = PurchaseReturn(
        vendor_id="v1",
        godown_id="g1",
        return_date="2026-06-21",
        lines=[
            ReturnLine(stock_item_id="i1", qty=2.0, rate=100.0, gst_rate=18.0)
        ]
    )
    
    ret = asyncio.run(create_return(return_payload, user=USER))
    assert ret is not None
    
    # Verify stock ledger entries (negative qty for return)
    ledger_entries = db.stock_ledger_entries.docs
    assert len(ledger_entries) == 1
    assert ledger_entries[0]["stock_item_id"] == "i1"
    assert ledger_entries[0]["qty"] == -2.0
    
    # Verify if purchase return in db has stock_ledger_entry_ids saved
    ret_db = asyncio.run(db.purchase_returns.find_one({"id": ret["id"]}))
    assert ret_db is not None
    assert "stock_ledger_entry_ids" in ret_db
    assert len(ret_db["stock_ledger_entry_ids"]) == 1
    assert ret_db["stock_ledger_entry_ids"][0] == ledger_entries[0]["id"]
    assert "journal_entry_id" in ret_db


def test_grn_unknown_godown_returns_named_404():
    """A bogus godown_id must surface a specific, named 404 — not a bare
    'Not found' — so the user knows which reference is broken."""
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor 1", "state_code": "27"}))
    asyncio.run(db.stock_items.insert_one({"id": "i1", "name": "Item 1", "valuation_method": "WEIGHTED_AVG"}))

    grn_payload = GRNV2(
        vendor_id="v1",
        godown_id="does-not-exist",
        received_date="2026-06-21",
        lines=[GRNLine(stock_item_id="i1", qty_received=1.0, rate=10.0, gst_rate=18.0)],
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_grn(grn_payload, user=USER))
    assert exc.value.status_code == 404
    assert exc.value.detail == "Warehouse not found"


def test_grn_unknown_vendor_returns_named_404():
    """A bogus vendor_id (with a valid godown) names the vendor in the 404."""
    db = _setup()
    asyncio.run(db.godowns.insert_one({"id": "g1", "name": "Main Godown"}))
    asyncio.run(db.stock_items.insert_one({"id": "i1", "name": "Item 1", "valuation_method": "WEIGHTED_AVG"}))

    grn_payload = GRNV2(
        vendor_id="does-not-exist",
        godown_id="g1",
        received_date="2026-06-21",
        lines=[GRNLine(stock_item_id="i1", qty_received=1.0, rate=10.0, gst_rate=18.0)],
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_grn(grn_payload, user=USER))
    assert exc.value.status_code == 404
    assert exc.value.detail == "Vendor not found"


def test_grn_unknown_purchase_order_returns_named_404():
    """A bogus purchase_order_id (with valid godown + vendor) names the PO."""
    db = _setup()
    asyncio.run(db.godowns.insert_one({"id": "g1", "name": "Main Godown"}))
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor 1", "state_code": "27"}))
    asyncio.run(db.stock_items.insert_one({"id": "i1", "name": "Item 1", "valuation_method": "WEIGHTED_AVG"}))

    grn_payload = GRNV2(
        purchase_order_id="does-not-exist",
        vendor_id="v1",
        godown_id="g1",
        received_date="2026-06-21",
        lines=[GRNLine(stock_item_id="i1", qty_received=1.0, rate=10.0, gst_rate=18.0)],
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_grn(grn_payload, user=USER))
    assert exc.value.status_code == 404
    assert exc.value.detail == "Purchase order not found"


# ───────────────── Product → stock_item bridge (link to products) ─────────────────

def test_grn_by_product_id_auto_creates_and_links_stock_item():
    """A GRN line carrying product_id (no stock_item_id) auto-creates a backing
    stock_item, links it back to the product, and posts the ledger entry against
    that resolved stock_item_id — so inventory valuation stays keyed correctly."""
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor 1", "state_code": "27"}))
    asyncio.run(db.godowns.insert_one({"id": "g1", "name": "Main Warehouse"}))
    asyncio.run(db.products.insert_one({
        "id": "p1", "name": "Widget", "sku": "WID-1", "hsn_code": "8483",
        "gst_rate": 18.0, "cost_price": 50.0,
    }))

    grn_payload = GRNV2(
        vendor_id="v1", godown_id="g1", received_date="2026-06-21",
        lines=[GRNLine(product_id="p1", qty_received=3.0, rate=50.0, gst_rate=18.0)],
    )
    asyncio.run(create_grn(grn_payload, user=USER))

    # A stock_item was created and linked to the product.
    si = asyncio.run(db.stock_items.find_one({"product_id": "p1"}))
    assert si is not None
    assert si["name"] == "Widget"
    assert si["sku"] == "WID-1"

    # The ledger entry is keyed by the resolved stock_item id, not the product id.
    ledger = db.stock_ledger_entries.docs
    assert len(ledger) == 1
    assert ledger[0]["stock_item_id"] == si["id"]
    assert ledger[0]["stock_item_id"] != "p1"
    assert ledger[0]["qty"] == 3.0


def test_grn_by_product_id_reuses_linked_stock_item():
    """When a stock_item is already linked to the product, the GRN reuses it
    instead of creating a second one."""
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor 1", "state_code": "27"}))
    asyncio.run(db.godowns.insert_one({"id": "g1", "name": "Main Warehouse"}))
    asyncio.run(db.products.insert_one({"id": "p1", "name": "Widget", "sku": "WID-1", "gst_rate": 18.0}))
    asyncio.run(db.stock_items.insert_one({
        "id": "si-existing", "name": "Widget", "sku": "WID-1",
        "valuation_method": "WEIGHTED_AVG", "product_id": "p1",
    }))

    grn_payload = GRNV2(
        vendor_id="v1", godown_id="g1", received_date="2026-06-21",
        lines=[GRNLine(product_id="p1", qty_received=2.0, rate=50.0, gst_rate=18.0)],
    )
    asyncio.run(create_grn(grn_payload, user=USER))

    # No new stock_item created; the linked one is used.
    linked = [d for d in db.stock_items.docs if d.get("product_id") == "p1"]
    assert len(linked) == 1
    ledger = db.stock_ledger_entries.docs
    assert len(ledger) == 1
    assert ledger[0]["stock_item_id"] == "si-existing"


def test_grn_unknown_product_returns_named_404():
    """A bogus product_id surfaces a specific, named 404."""
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor 1", "state_code": "27"}))
    asyncio.run(db.godowns.insert_one({"id": "g1", "name": "Main Warehouse"}))

    grn_payload = GRNV2(
        vendor_id="v1", godown_id="g1", received_date="2026-06-21",
        lines=[GRNLine(product_id="does-not-exist", qty_received=1.0, rate=10.0, gst_rate=18.0)],
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_grn(grn_payload, user=USER))
    assert exc.value.status_code == 404
    assert exc.value.detail == "Product not found"

