"""Phase 2 pagination tests — shared helper + purchase_v2 + inventory_v2."""
import asyncio
from typing import Any

import core.utils as utils
import core.db
import core.masters_crud as mc

# ───────────────────── Fake Mongo helpers ─────────────────────


def _matches(doc, q):
    for k, v in q.items():
        if k == "$or":
            if not any(_matches(doc, sub) for sub in v):
                return False
            continue
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$ne" in v and actual == v["$ne"]:
                return False
            if "$regex" in v:
                import re
                if not (isinstance(actual, str) and re.search(v["$regex"], actual, re.I)):
                    return False
            if "$gte" in v and not (actual is not None and actual >= v["$gte"]):
                return False
            if "$lte" in v and not (actual is not None and actual <= v["$lte"]):
                return False
        elif actual != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)
    def sort(self, field, direction=1):
        self._docs.sort(key=lambda d: (d.get(field) is None, d.get(field)), reverse=direction < 0)
        return self
    def skip(self, n):
        self._docs = self._docs[n:]
        return self
    def limit(self, n):
        self._docs = self._docs[:n]
        return self
    async def to_list(self, _n):
        return [dict(d) for d in self._docs]


class _Collection:
    def __init__(self):
        self.docs = []
    async def insert_one(self, doc):
        d = dict(doc)
        d["_id"] = d.get("id")
        self.docs.append(d)
    async def find_one(self, q, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items() if k != "_id"):
                out = dict(d)
                out.pop("_id", None)
                return out
        return None
    def find(self, q=None, projection=None):
        q = q or {}
        return _Cursor([d for d in self.docs if _matches(d, q)])
    async def count_documents(self, q):
        q = q or {}
        return len([d for d in self.docs if _matches(d, q)])
    async def update_one(self, q, update, session=None, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items() if k != "_id"):
                for k2, v2 in (update.get("$set") or {}).items():
                    d[k2] = v2
                return type("R", (), {"modified_count": 1})()
        return type("R", (), {"modified_count": 0})()
    async def delete_one(self, q, session=None):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not all(d.get(k) == v for k, v in q.items() if k != "_id")]
        return type("R", (), {"deleted_count": before - len(self.docs)})()


class _DB:
    def __init__(self):
        self._collections = {}
        for name in [
            "journal_entries", "purchase_bills", "purchase_orders_v2",
            "goods_receipt_notes_v2", "purchase_returns", "vendors",
            "units_of_measure", "godowns", "stock_items", "batches",
            "serial_numbers", "stock_transfers", "companies",
            "chart_of_accounts",
        ]:
            c = _Collection()
            setattr(self, name, c)
            self._collections[name] = c
    def __getitem__(self, key):
        key = key.replace("-", "_")
        if key not in self._collections:
            c = _Collection()
            self._collections[key] = c
            setattr(self, key, c)
        return self._collections[key]
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]


def _setup():
    import core
    import core._mongo_compat
    db = _DB()
    core.db.db = db  # type: ignore
    utils.db = db    # type: ignore
    core._mongo_compat.db = db  # type: ignore
    asyncio.run(db.companies.insert_one({"id": "c1", "state_code": "27"}))
    return db


USER = {"id": "u1", "name": "Test", "role": "admin"}


# ════════════════════ paginated_list helper tests ════════════════════

def test_paginated_list_returns_envelope_when_paging():
    db = _setup()
    for i in range(25):
        asyncio.run(db.purchase_bills.insert_one({
            "id": f"b{i:03d}", "bill_number": f"BILL-{i:03d}",
            "created_at": f"2026-06-{i+1:02d}T00:00:00Z",
        }))
    r = asyncio.run(utils.paginated_list("purchase_bills", page=1, limit=10,
                                          sort_field="created_at"))
    assert r["total"] == 25 and r["page"] == 1
    assert len(r["items"]) == 10


def test_paginated_list_clamps_input():
    db = _setup()
    for i in range(5):
        asyncio.run(db.purchase_bills.insert_one({
            "id": f"b{i:03d}", "bill_number": f"BILL-{i:03d}",
            "created_at": f"2026-06-{i+1:02d}T00:00:00Z",
        }))
    r = asyncio.run(utils.paginated_list("purchase_bills", page=0, limit=99999,
                                          sort_field="created_at"))
    assert r["page"] == 1 and len(r["items"]) == 5  # only 5 exist, limit clamped to 200


def test_paginated_list_backward_compat_bare_array():
    db = _setup()
    for i in range(5):
        asyncio.run(db.purchase_bills.insert_one({
            "id": f"b{i:03d}", "bill_number": f"BILL-{i:03d}",
            "created_at": f"2026-06-{i+1:02d}T00:00:00Z",
        }))
    r = asyncio.run(utils.paginated_list("purchase_bills", sort_field="created_at"))
    assert isinstance(r, list) and len(r) == 5  # bare array when no page/limit


def test_paginated_list_search():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Alpha Corp", "gstin": "27AAAAA0001A1Z1",
                                        "created_at": "2026-06-01T00:00:00Z"}))
    asyncio.run(db.vendors.insert_one({"id": "v2", "name": "Beta Inc", "gstin": "27BBBBB0001A1Z1",
                                        "created_at": "2026-06-02T00:00:00Z"}))
    r = asyncio.run(utils.paginated_list("vendors", q="alpha",
                                          search_fields=["name", "gstin"],
                                          page=1, limit=50))
    assert r["total"] == 1 and r["items"][0]["name"] == "Alpha Corp"


def test_paginated_list_date_range():
    db = _setup()
    asyncio.run(db.purchase_bills.insert_one({
        "id": "b1", "bill_number": "BILL-001",
        "created_at": "2026-06-01T00:00:00Z",
    }))
    asyncio.run(db.purchase_bills.insert_one({
        "id": "b2", "bill_number": "BILL-002",
        "created_at": "2026-06-15T00:00:00Z",
    }))
    asyncio.run(db.purchase_bills.insert_one({
        "id": "b3", "bill_number": "BILL-003",
        "created_at": "2026-07-01T00:00:00Z",
    }))
    r = asyncio.run(utils.paginated_list("purchase_bills", from_date="2026-06-10",
                                          to_date="2026-06-30", page=1, limit=50,
                                          sort_field="created_at"))
    assert r["total"] == 1 and r["items"][0]["id"] == "b2"


# ════════════════════ Purchase v2 pagination tests ════════════════════

def test_list_vendors_paginated():
    db = _setup()
    for i in range(15):
        asyncio.run(db.vendors.insert_one({
            "id": f"v{i:03d}", "name": f"Vendor {i:03d}",
            "created_at": f"2026-06-{i+1:02d}T00:00:00Z",
        }))
    r = asyncio.run(utils.paginated_list("vendors", page=1, limit=5,
                                          search_fields=["name", "gstin", "email", "phone"],
                                          sort_field="name", sort_dir=1))
    assert r["total"] == 15 and len(r["items"]) == 5


def test_list_orders_paginated():
    db = _setup()
    for i in range(10):
        asyncio.run(db.purchase_orders_v2.insert_one({
            "id": f"po{i:03d}", "po_number": f"PO-{i:03d}",
            "vendor_name": f"Vendor {i:03d}", "status": "DRAFT",
            "created_at": f"2026-06-{i+1:02d}T00:00:00Z",
        }))
    r = asyncio.run(utils.paginated_list("purchase_orders_v2", page=1, limit=3,
                                          search_fields=["po_number", "vendor_name", "status"],
                                          sort_field="created_at", sort_dir=-1))
    assert r["total"] == 10 and len(r["items"]) == 3


def test_list_bills_paginated():
    db = _setup()
    for i in range(8):
        asyncio.run(db.purchase_bills.insert_one({
            "id": f"b{i:03d}", "bill_number": f"BILL-{i:03d}",
            "vendor_invoice_no": f"INV-{i:03d}", "vendor_name": f"Vendor {i:03d}",
            "created_at": f"2026-06-{i+1:02d}T00:00:00Z",
        }))
    r = asyncio.run(utils.paginated_list("purchase_bills", page=2, limit=5,
                                          search_fields=["bill_number", "vendor_invoice_no", "vendor_name"],
                                          sort_field="created_at", sort_dir=-1))
    assert r["total"] == 8 and r["page"] == 2 and len(r["items"]) == 3


def test_list_grns_paginated():
    db = _setup()
    for i in range(6):
        asyncio.run(db.goods_receipt_notes_v2.insert_one({
            "id": f"grn{i:03d}", "grn_number": f"GRN-{i:03d}",
            "vendor_name": f"Vendor {i:03d}",
            "created_at": f"2026-06-{i+1:02d}T00:00:00Z",
        }))
    r = asyncio.run(utils.paginated_list("goods_receipt_notes_v2", page=1, limit=10,
                                          search_fields=["grn_number", "vendor_name"],
                                          sort_field="created_at", sort_dir=-1))
    assert r["total"] == 6 and len(r["items"]) == 6


def test_list_returns_paginated():
    db = _setup()
    for i in range(12):
        asyncio.run(db.purchase_returns.insert_one({
            "id": f"r{i:03d}", "debit_note_number": f"DN-{i:03d}",
            "vendor_name": f"Vendor {i:03d}",
            "created_at": f"2026-06-{i+1:02d}T00:00:00Z",
        }))
    r = asyncio.run(utils.paginated_list("purchase_returns", page=1, limit=5,
                                          search_fields=["debit_note_number", "vendor_name"],
                                          sort_field="created_at", sort_dir=-1))
    assert r["total"] == 12 and len(r["items"]) == 5


# ════════════════════ Inventory v2 pagination tests ════════════════════

def test_list_units_paginated():
    db = _setup()
    for i in range(10):
        asyncio.run(db.units_of_measure.insert_one({
            "id": f"u{i:03d}", "name": f"Unit {i:03d}", "uqc_code": f"U{i:03d}",
            "created_at": f"2026-06-{i+1:02d}T00:00:00Z",
        }))
    r = asyncio.run(utils.paginated_list("units_of_measure", page=1, limit=3,
                                          search_fields=["name", "uqc_code"],
                                          sort_field="name", sort_dir=1))
    assert r["total"] == 10 and len(r["items"]) == 3


def test_list_godowns_paginated():
    db = _setup()
    for i in range(7):
        asyncio.run(db.godowns.insert_one({
            "id": f"g{i:03d}", "name": f"Godown {i:03d}", "address": f"Addr {i:03d}",
            "created_at": f"2026-06-{i+1:02d}T00:00:00Z",
        }))
    r = asyncio.run(utils.paginated_list("godowns", page=2, limit=3,
                                          search_fields=["name", "address"],
                                          sort_field="name", sort_dir=1))
    assert r["total"] == 7 and r["page"] == 2


def test_list_items_paginated():
    db = _setup()
    for i in range(20):
        asyncio.run(db.stock_items.insert_one({
            "id": f"si{i:03d}", "name": f"Item {i:03d}", "sku": f"SKU-{i:03d}",
            "hsn_sac_code": f"HS{i:03d}",
            "created_at": f"2026-06-{i+1:02d}T00:00:00Z",
            "reorder_level": 0,
        }))
    r = asyncio.run(utils.paginated_list("stock_items", page=3, limit=5,
                                          search_fields=["name", "sku", "hsn_sac_code"],
                                          sort_field="name", sort_dir=1))
    assert r["total"] == 20 and r["page"] == 3 and len(r["items"]) == 5


def test_list_batches_paginated():
    db = _setup()
    for i in range(6):
        asyncio.run(db.batches.insert_one({
            "id": f"bt{i:03d}", "stock_item_id": "si001",
            "created_at": f"2026-06-{i+1:02d}T00:00:00Z",
        }))
    r = asyncio.run(utils.paginated_list("batches", filt={"stock_item_id": "si001"},
                                          page=1, limit=3))
    assert r["total"] == 6 and len(r["items"]) == 3


def test_list_serials_paginated():
    db = _setup()
    for i in range(4):
        asyncio.run(db.serial_numbers.insert_one({
            "id": f"s{i:03d}", "stock_item_id": "si001",
            "created_at": f"2026-06-{i+1:02d}T00:00:00Z",
        }))
    r = asyncio.run(utils.paginated_list("serial_numbers", filt={"stock_item_id": "si001"},
                                          page=1, limit=2))
    assert r["total"] == 4 and len(r["items"]) == 2


def test_list_transfers_paginated():
    db = _setup()
    for i in range(9):
        asyncio.run(db.stock_transfers.insert_one({
            "id": f"t{i:03d}", "transfer_number": f"TRF-{i:03d}",
            "remarks": f"Transfer {i:03d}",
            "created_at": f"2026-06-{i+1:02d}T00:00:00Z",
        }))
    r = asyncio.run(utils.paginated_list("stock_transfers", page=1, limit=5,
                                          search_fields=["transfer_number", "remarks"],
                                          sort_field="created_at", sort_dir=-1))
    assert r["total"] == 9 and len(r["items"]) == 5


# ════════════════════ /api/v1 alias reachability ════════════════════
# These tests verify that the paginated_list function works when called
# from the same collections that would be accessed via /api/v1/* endpoints.

def test_paginated_list_works_across_collections():
    """Verify pagination works on all purchase_v2 and inventory_v2 collections."""
    db = _setup()
    collections = [
        "vendors", "purchase_orders_v2", "purchase_bills",
        "goods_receipt_notes_v2", "purchase_returns",
        "units_of_measure", "godowns", "stock_items",
        "batches", "serial_numbers", "stock_transfers",
    ]
    for coll in collections:
        asyncio.run(getattr(db, coll).insert_one({
            "id": "test-1", "name": "Test",
            "created_at": "2026-06-01T00:00:00Z",
        }))
        asyncio.run(getattr(db, coll).insert_one({
            "id": "test-2", "name": "Another",
            "created_at": "2026-06-02T00:00:00Z",
        }))
        r = asyncio.run(utils.paginated_list(coll, page=1, limit=1,
                                              sort_field="created_at"))
        assert r["total"] == 2 and len(r["items"]) == 1, f"Failed on {coll}"
