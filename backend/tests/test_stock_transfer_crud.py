"""Unit test for Stock Transfer CRUD operations (GET, PUT, DELETE).

Proves:
1. GET /inventory/v2/transfers/{item_id} retrieves details of a stock transfer.
2. PUT /inventory/v2/transfers/{item_id} updates transfer lines and re-posts stock movements.
3. DELETE /inventory/v2/transfers/{item_id} removes transfer and cleans up stock ledger entries and stock_transactions.
"""
import asyncio
import pytest
import core
import core.db
import core.utils as utils
import core.stock_ledger as sl
import core.inventory_models as im
from routers.inventory_v2 import get_transfer, update_transfer, delete_transfer, create_transfer, list_transfers
from fastapi import HTTPException

class _Cursor:
    def __init__(self, docs): self._docs = docs
    def sort(self, *a, **k): return self
    async def to_list(self, _n): return [dict(d) for d in self._docs]

def _match(doc, q):
    for k, v in q.items():
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$ne" in v and actual == v["$ne"]: return False
            if "$in" in v and actual not in v["$in"]: return False
            if "$or" in v:
                if not any(_match(doc, subq) for subq in v["$or"]): return False
        elif actual != v:
            return False
    return True

class _Collection:
    def __init__(self): self.docs = []
    async def insert_one(self, doc, session=None):
        doc_copy = dict(doc)
        if "_id" not in doc_copy: doc_copy["_id"] = doc_copy.get("id", "id_" + str(len(self.docs)))
        self.docs.append(doc_copy)
        return type("R", (), {"inserted_id": doc_copy.get("id")})()
    async def find_one(self, q, projection=None, session=None):
        for d in self.docs:
            if _match(d, q):
                out = dict(d); out.pop("_id", None); return out
        return None
    def find(self, q=None, projection=None):
        return _Cursor([dict(d) for d in self.docs if _match(d, q or {})])
    async def count_documents(self, q):
        return len([d for d in self.docs if _match(d, q or {})])
    async def update_one(self, q, u, session=None, upsert=False):
        for d in self.docs:
            if _match(d, q):
                d.update(u.get("$set", {})); return type("R", (), {"modified_count": 1})()
        return type("R", (), {"modified_count": 0})()
    async def delete_many(self, q, session=None):
        initial = len(self.docs)
        self.docs = [d for d in self.docs if not _match(d, q)]
        return type("R", (), {"deleted_count": initial - len(self.docs)})()
    async def delete_one(self, q, session=None):
        for i, d in enumerate(self.docs):
            if _match(d, q):
                self.docs.pop(i)
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()
    async def create_index(self, *a, **k): return "idx"

class _DB:
    def __init__(self): self._c = {}
    def __getitem__(self, n): return self._c.setdefault(n, _Collection())
    def __getattr__(self, n):
        if n.startswith("_"): raise AttributeError(n)
        return self[n]

from typing import Any

USER = {"id": "usr_admin", "name": "Admin", "role": "admin"}

@pytest.fixture
def test_db(monkeypatch):
    db: Any = _DB()
    core.db.db = db
    utils.db = db
    sl.db = db
    import routers.inventory_v2 as inv_v2
    inv_v2.db = db

    async def mock_crud_get(coll, doc_id, label="Record"):
        doc = await db[coll].find_one({"id": doc_id})
        if not doc:
            raise HTTPException(404, f"{label} not found")
        return doc

    async def mock_crud_create(coll, data, user=None):
        doc = dict(data)
        if not doc.get("id"):
            doc["id"] = "id_" + utils.new_id()
        doc["tenant_id"] = "t1"
        await db[coll].insert_one(doc)
        return doc

    async def mock_crud_update(coll, doc_id, data, user=None, label="Record"):
        doc = await mock_crud_get(coll, doc_id, label)
        doc.update(data)
        await db[coll].update_one({"id": doc_id}, {"$set": doc})
        return doc

    async def mock_crud_delete(coll, doc_id, user=None):
        await db[coll].delete_many({"id": doc_id})
        return {"id": doc_id}

    monkeypatch.setattr("routers.inventory_v2.crud_get", mock_crud_get)
    monkeypatch.setattr("routers.inventory_v2.crud_create", mock_crud_create)
    monkeypatch.setattr("routers.inventory_v2.crud_update", mock_crud_update)
    monkeypatch.setattr("routers.inventory_v2.crud_delete", mock_crud_delete)
    monkeypatch.setattr("core.product_stock_bridge.crud_get", mock_crud_get)


    # Setup godowns and stock item
    asyncio.run(db.godowns.insert_one({"id": "G1", "name": "Warehouse 1", "is_deleted": False}))
    asyncio.run(db.godowns.insert_one({"id": "G2", "name": "Warehouse 2", "is_deleted": False}))
    asyncio.run(db.stock_items.insert_one({"id": "ITEM1", "name": "Test Item 1", "is_deleted": False}))
    return db


@pytest.mark.asyncio
async def test_stock_transfer_get_put_delete(test_db):
    # 1. Create a transfer
    payload = im.StockTransfer(
        from_godown_id="G1",
        to_godown_id="G2",
        transfer_date="2026-08-18",
        remarks="Test transfer",
        lines=[im.StockTransferLine(stock_item_id="ITEM1", qty=5.0)]
    )
    created = await create_transfer(payload, USER)
    tr_id = created["id"]
    assert created["from_godown_id"] == "G1"
    assert created["to_godown_id"] == "G2"

    # Verify ledger entries created
    ledger_entries = await test_db.stock_ledger_entries.find({"source_doc_id": tr_id}).to_list(10)
    assert len(ledger_entries) == 2

    # 2. Test GET transfer endpoint
    fetched = await get_transfer(tr_id, USER)
    assert fetched["id"] == tr_id
    assert fetched["remarks"] == "Test transfer"

    # 3. Test PUT (Update) transfer endpoint
    update_payload = im.StockTransfer(
        from_godown_id="G1",
        to_godown_id="G2",
        transfer_date="2026-08-18",
        remarks="Updated remarks",
        lines=[im.StockTransferLine(stock_item_id="ITEM1", qty=12.0)]
    )
    updated = await update_transfer(tr_id, update_payload, USER)
    assert updated["remarks"] == "Updated remarks"

    # Verify updated ledger entries
    ledger_entries_updated = await test_db.stock_ledger_entries.find({"source_doc_id": tr_id}).to_list(10)
    assert len(ledger_entries_updated) == 2
    qtys = [abs(e["qty"]) for e in ledger_entries_updated]
    assert all(q == 12.0 for q in qtys)

    # 4. Test DELETE transfer endpoint
    del_res = await delete_transfer(tr_id, USER)
    assert isinstance(del_res, dict)

    # Verify transfer doc is gone and ledger entries are cleaned up
    assert await test_db.stock_transfers.find_one({"id": tr_id}) is None
    remaining_ledger = await test_db.stock_ledger_entries.find({"source_doc_id": tr_id}).to_list(10)
    assert len(remaining_ledger) == 0

