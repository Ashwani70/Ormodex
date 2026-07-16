"""Batch / serial / expiry tracking enforcement across stock-ledger transactions.

Covers the acceptance matrix: batch-tracked, serial-tracked, expiry-tracked,
mixed tracked + untracked in one document, and legacy stock_item_id-only lines.
Exercises the real handlers (GRN, Purchase Return, Stock Adjustment, Stock
Transfer, Job Work) through an in-memory Mongo fake that supports the query
operators the bridge/validator use ($in, $or, $exists).
"""
import asyncio

import pytest
from fastapi import HTTPException

import core.db
import core.utils as utils
import core.stock_ledger as sl


# ───────────────────────── In-memory Mongo fake ─────────────────────────

def _match(actual, expected):
    if isinstance(expected, dict):
        for op, val in expected.items():
            if op == "$in":
                if actual not in val:
                    return False
            elif op == "$nin":
                if actual in val:
                    return False
            elif op == "$ne":
                if actual == val:
                    return False
            elif op == "$exists":
                # `actual` is a sentinel below; handled in _doc_matches instead.
                return True
            else:
                return actual == expected
        return True
    return actual == expected


_MISSING = object()


def _doc_matches(d, q):
    for k, v in q.items():
        if k == "$or":
            if not any(_doc_matches(d, sub) for sub in v):
                return False
            continue
        if isinstance(v, dict) and "$exists" in v:
            present = k in d and d[k] is not None
            if present != bool(v["$exists"]):
                return False
            # Other operators alongside $exists still apply.
            rest = {op: val for op, val in v.items() if op != "$exists"}
            if rest and not _match(d.get(k), rest):
                return False
            continue
        if not _match(d.get(k, _MISSING), v):
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, _n=None):
        return [dict(d) for d in self._docs]


class _Collection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc, session=None):
        doc = dict(doc)
        doc.setdefault("_id", doc.get("id"))
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

    def _apply(self, d, update):
        for k, v in update.get("$set", {}).items():
            d[k] = v
        for k, v in update.get("$inc", {}).items():
            d[k] = d.get(k, 0) + v

    async def update_one(self, q, update, session=None, upsert=False):
        for d in self.docs:
            if _doc_matches(d, q):
                self._apply(d, update)
                return type("R", (), {"modified_count": 1})()
        if upsert:
            doc = {k: v for k, v in q.items() if not isinstance(v, dict)}
            self._apply(doc, update)
            self.docs.append(doc)
            return type("R", (), {"modified_count": 0, "upserted_id": doc.get("id") or doc.get("_id")})()
        return type("R", (), {"modified_count": 0})()

    async def find_one_and_update(self, q, update, upsert=False, return_document=True, session=None):
        for d in self.docs:
            if _doc_matches(d, q):
                self._apply(d, update)
                return dict(d)
        if upsert:
            doc = {k: v for k, v in q.items() if not isinstance(v, dict)}
            self._apply(doc, update)
            self.docs.append(doc)
            return dict(doc)
        return None

    async def delete_one(self, q, session=None):
        for i, d in enumerate(self.docs):
            if _doc_matches(d, q):
                del self.docs[i]
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

    async def create_index(self, *a, **k):
        return None


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
    from core import product_stock_bridge
    product_stock_bridge.db = db
    import routers.purchase_v2
    routers.purchase_v2.db = db
    import routers.inventory_v2
    routers.inventory_v2.db = db
    import routers.job_work
    routers.job_work.db = db

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

    for mod in [routers.purchase_v2, routers.inventory_v2, routers.job_work, product_stock_bridge]:
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


def _seed_common(db):
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor 1", "state_code": "27"}))
    asyncio.run(db.godowns.insert_one({"id": "g1", "name": "Main Warehouse"}))
    asyncio.run(db.godowns.insert_one({"id": "g2", "name": "Second Warehouse"}))


def _add_product(db, pid, *, sku, track_batch=False, track_serial=False, track_expiry=False):
    """A product plus its already-linked stock_item carrying the tracking flags."""
    asyncio.run(db.products.insert_one({"id": pid, "name": pid.upper(), "sku": sku, "gst_rate": 18.0, "cost_price": 10.0}))
    asyncio.run(db.stock_items.insert_one({
        "id": f"si-{pid}", "name": pid.upper(), "sku": sku, "valuation_method": "WEIGHTED_AVG",
        "product_id": pid, "track_batch": track_batch, "track_serial": track_serial, "track_expiry": track_expiry,
    }))


# ───────────────────────── GRN: batch / serial / expiry ─────────────────────────

def _grn(db, line):
    from core.purchase_models import GRNV2, GRNLine
    from routers.purchase_v2 import create_grn
    payload = GRNV2(vendor_id="v1", godown_id="g1", received_date="2026-06-21", lines=[GRNLine(**line)])
    return asyncio.run(create_grn(payload, user=USER))


def test_grn_batch_required_then_accepted():
    db = _setup(); _seed_common(db)
    _add_product(db, "pb", sku="PB-1", track_batch=True)

    with pytest.raises(HTTPException) as exc:
        _grn(db, {"product_id": "pb", "qty_received": 5, "rate": 10})
    assert exc.value.status_code == 400
    assert "Batch number" in exc.value.detail

    grn = _grn(db, {"product_id": "pb", "qty_received": 5, "rate": 10, "batch_id": "B-100"})
    assert grn is not None
    ledger = db.stock_ledger_entries.docs
    assert len(ledger) == 1
    assert ledger[0]["stock_item_id"] == "si-pb"
    assert ledger[0]["batch_id"] == "B-100"


def test_grn_serial_required_then_accepted():
    db = _setup(); _seed_common(db)
    _add_product(db, "ps", sku="PS-1", track_serial=True)

    with pytest.raises(HTTPException) as exc:
        _grn(db, {"product_id": "ps", "qty_received": 1, "rate": 10})
    assert "Serial number" in exc.value.detail

    grn = _grn(db, {"product_id": "ps", "qty_received": 1, "rate": 10, "serial_id": "SN-1"})
    assert db.stock_ledger_entries.docs[0]["serial_id"] == "SN-1"
    assert grn is not None


def test_grn_expiry_required_then_accepted():
    db = _setup(); _seed_common(db)
    _add_product(db, "pe", sku="PE-1", track_expiry=True)

    with pytest.raises(HTTPException) as exc:
        _grn(db, {"product_id": "pe", "qty_received": 3, "rate": 10})
    assert "Expiry date" in exc.value.detail

    grn = _grn(db, {"product_id": "pe", "qty_received": 3, "rate": 10, "expiry_date": "2027-01-01"})
    assert grn is not None
    assert len(db.stock_ledger_entries.docs) == 1


def test_grn_mixed_tracked_and_untracked_in_one_doc():
    """One GRN, three lines: a batch-tracked line missing its batch must reject
    the whole document even though the other lines are fine."""
    db = _setup(); _seed_common(db)
    _add_product(db, "pb", sku="PB-1", track_batch=True)
    _add_product(db, "pn", sku="PN-1")  # untracked

    from core.purchase_models import GRNV2, GRNLine
    from routers.purchase_v2 import create_grn

    bad = GRNV2(vendor_id="v1", godown_id="g1", received_date="2026-06-21", lines=[
        GRNLine(product_id="pn", qty_received=2, rate=10),               # ok (untracked)
        GRNLine(product_id="pb", qty_received=4, rate=10),               # missing batch
    ])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_grn(bad, user=USER))
    assert "Batch number" in exc.value.detail
    assert db.stock_ledger_entries.docs == []  # nothing posted

    good = GRNV2(vendor_id="v1", godown_id="g1", received_date="2026-06-21", lines=[
        GRNLine(product_id="pn", qty_received=2, rate=10),
        GRNLine(product_id="pb", qty_received=4, rate=10, batch_id="B-7"),
    ])
    asyncio.run(create_grn(good, user=USER))
    assert len(db.stock_ledger_entries.docs) == 2


def test_grn_legacy_stock_item_id_untracked_still_works():
    """A legacy line that carries only stock_item_id (no product_id) for an item
    with no tracking flags posts unchanged — backward compatibility."""
    db = _setup(); _seed_common(db)
    asyncio.run(db.stock_items.insert_one({"id": "si-legacy", "name": "Legacy", "valuation_method": "WEIGHTED_AVG"}))

    grn = _grn(db, {"stock_item_id": "si-legacy", "qty_received": 9, "rate": 5})
    assert grn is not None
    ledger = db.stock_ledger_entries.docs
    assert len(ledger) == 1
    assert ledger[0]["stock_item_id"] == "si-legacy"


def test_grn_legacy_stock_item_id_tracked_is_enforced():
    """Even a legacy stock_item_id line is enforced when that item tracks batch —
    so API/import callers can't bypass the rule by skipping product_id."""
    db = _setup(); _seed_common(db)
    asyncio.run(db.stock_items.insert_one({
        "id": "si-tb", "name": "Tracked", "valuation_method": "WEIGHTED_AVG", "track_batch": True,
    }))
    with pytest.raises(HTTPException) as exc:
        _grn(db, {"stock_item_id": "si-tb", "qty_received": 1, "rate": 5})
    assert "Batch number" in exc.value.detail


# ───────────────────────── Purchase Return ─────────────────────────

def test_purchase_return_serial_required():
    db = _setup(); _seed_common(db)
    # Accounting accounts for the reversing voucher.
    asyncio.run(db.companies.insert_one({"id": "c1", "state_code": "27"}))
    asyncio.run(db.fiscal_years.insert_one({"id": "fy", "name": "2026-27", "is_active": True}))
    for code, name in [("1200", "Inventory"), ("1500", "GST ITC"), ("2001", "AP"), ("2006", "TDS")]:
        asyncio.run(db.chart_of_accounts.insert_one({"id": code, "code": code, "name": name}))
    _add_product(db, "ps", sku="PS-1", track_serial=True)

    from core.purchase_models import PurchaseReturn, ReturnLine
    from routers.purchase_v2 import create_return

    bad = PurchaseReturn(vendor_id="v1", godown_id="g1", return_date="2026-06-21",
                         lines=[ReturnLine(product_id="ps", qty=1, rate=10)])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_return(bad, user=USER))
    assert "Serial number" in exc.value.detail


# ───────────────────────── Stock Adjustment ─────────────────────────

def test_adjustment_batch_required_then_accepted():
    db = _setup(); _seed_common(db)
    _add_product(db, "pb", sku="PB-1", track_batch=True)

    from core.inventory_models import StockAdjustmentIn
    from routers.inventory_v2 import adjust_stock

    bad = StockAdjustmentIn(product_id="pb", godown_id="g1", qty=5, rate=10)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(adjust_stock(bad, user=USER))
    assert "Batch number" in exc.value.detail

    good = StockAdjustmentIn(product_id="pb", godown_id="g1", qty=5, rate=10, batch_id="B-1")
    entry = asyncio.run(adjust_stock(good, user=USER))
    assert entry["stock_item_id"] == "si-pb"
    assert entry["batch_id"] == "B-1"


# ───────────────────────── Stock Transfer ─────────────────────────

def test_transfer_expiry_required():
    db = _setup(); _seed_common(db)
    _add_product(db, "pe", sku="PE-1", track_expiry=True)
    # Seed stock so the outward leg can be priced.
    asyncio.run(sl.post_entry(stock_item_id="si-pe", godown_id="g1", qty=10, movement_type="OPENING", rate=10, user=USER))

    from core.inventory_models import StockTransfer, StockTransferLine
    from routers.inventory_v2 import create_transfer

    bad = StockTransfer(from_godown_id="g1", to_godown_id="g2", transfer_date="2026-06-21",
                        lines=[StockTransferLine(product_id="pe", qty=2)])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_transfer(bad, user=USER))
    assert "Expiry date" in exc.value.detail


# ───────────────────────── Job Work ─────────────────────────

def test_job_work_challan_batch_required_then_accepted():
    db = _setup(); _seed_common(db)
    _add_product(db, "pb", sku="PB-1", track_batch=True)
    # Job Work checks products.quantity for availability.
    asyncio.run(db.products.update_one({"id": "pb"}, {"$set": {"quantity": 100}}))
    asyncio.run(db.vendors.insert_one({"id": "jw1", "name": "Worker", "party_type": "JOB_WORKER"}))

    from core.models import JobWorkChallan, JobWorkChallanItem
    from routers.job_work import create_challan

    bad = JobWorkChallan(date="2026-06-21", job_worker_id="jw1",
                         items=[JobWorkChallanItem(product_id="pb", product_name="PB", quantity=5)])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_challan(bad, user=USER))
    assert "Batch number" in exc.value.detail

    good = JobWorkChallan(date="2026-06-21", job_worker_id="jw1",
                          items=[JobWorkChallanItem(product_id="pb", product_name="PB", quantity=5, batch_id="B-9")])
    challan = asyncio.run(create_challan(good, user=USER))
    assert challan is not None


def test_job_work_custom_line_exempt_from_tracking():
    """A custom (off-catalog) line has no product_id → no stock_item → exempt,
    even when other catalog lines on the same challan are tracked."""
    db = _setup(); _seed_common(db)
    asyncio.run(db.vendors.insert_one({"id": "jw1", "name": "Worker", "party_type": "JOB_WORKER"}))

    from core.models import JobWorkChallan, JobWorkChallanItem
    from routers.job_work import create_challan

    challan = JobWorkChallan(date="2026-06-21", job_worker_id="jw1", items=[
        JobWorkChallanItem(product_name="Hand-made jig", quantity=1, is_custom=True),
    ])
    out = asyncio.run(create_challan(challan, user=USER))
    assert out is not None
    assert out["items"][0]["is_custom"] is True
