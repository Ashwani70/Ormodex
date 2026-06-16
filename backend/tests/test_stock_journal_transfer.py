"""stock_journal (BOM consume→produce) and inter-unit transfer posting.

In-memory fake DB; drives the voucher engine + stock ledger directly.
Proves cost roll-up (consumed value → produced FG rate) and cost-carrying
transfers between godowns, both idempotent.
"""
import asyncio

import core.db
import core.utils as utils
import core.voucher_engine as ve
import core.stock_ledger as sl


class _Cursor:
    def __init__(self, docs): self._docs = docs
    def sort(self, *a, **k): return self
    async def to_list(self, _n): return [dict(d) for d in self._docs]


def _match(doc, q):
    for k, v in q.items():
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$ne" in v and actual == v["$ne"]: return False
        elif actual != v:
            return False
    return True


class _Collection:
    def __init__(self): self.docs = []
    async def insert_one(self, doc, session=None):
        self.docs.append(dict(doc)); return type("R", (), {"inserted_id": doc.get("id")})()
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
    async def create_index(self, *a, **k): return "idx"


class _DB:
    def __init__(self): self._c = {}
    def __getitem__(self, n): return self._c.setdefault(n, _Collection())
    def __getattr__(self, n):
        if n.startswith("_"): raise AttributeError(n)
        return self[n]


def _setup():
    db = _DB()
    core.db.db = db; utils.db = db; ve.db = db; sl.db = db
    asyncio.run(db.fiscal_years.insert_one({"id": "fy", "name": "2026-27", "is_active": True}))
    for iid in ("RM1", "RM2", "FG", "ITEM"):
        asyncio.run(db.stock_items.insert_one(
            {"id": iid, "tenant_id": "t1", "is_deleted": False, "valuation_method": "WEIGHTED_AVG"}))
    return db


USER = {"id": "u1", "name": "T", "role": "admin"}
T = "t1"


def _post(db, vid, parent_type, inv_lines, statutory=None):
    v = {"id": vid, "tenant_id": T, "is_deleted": False, "status": "approved",
         "parent_type": parent_type, "voucher_no": vid, "date": "2026-06-01",
         "inventory_lines": inv_lines, "accounting_lines": [], "links": [], "statutory": statutory}
    asyncio.run(db.vouchers_v2.insert_one(v))
    return asyncio.run(ve.post_voucher(v, USER, T))


def _onhand(item, godown=None):
    return asyncio.run(sl.on_hand(item, godown))


# ───────────────────────── stock_journal (BOM) ─────────────────────────

def test_stock_journal_rolls_consumed_cost_into_fg():
    db = _setup()
    # Seed raw-material stock: RM1 10@100, RM2 5@40.
    _post(db, "G1", "receipt_note", [{"stock_item_id": "RM1", "location_id": "W", "qty": 10, "rate": 100}])
    _post(db, "G2", "receipt_note", [{"stock_item_id": "RM2", "location_id": "W", "qty": 5, "rate": 40}])
    # Consume 4 RM1 (400) + 5 RM2 (200) = 600 → produce 2 FG. FG rate = 300.
    res = _post(db, "SJ1", "stock_journal", [
        {"stock_item_id": "RM1", "location_id": "W", "qty": 4, "role": "consume"},
        {"stock_item_id": "RM2", "location_id": "W", "qty": 5, "role": "consume"},
        {"stock_item_id": "FG", "location_id": "W", "qty": 2, "role": "produce"},
    ])
    assert res["consumed_value"] == 600 and res["produced_rate"] == 300
    fg = _onhand("FG")
    assert fg["qty"] == 2 and fg["value"] == 600        # cost flowed input→output
    assert _onhand("RM1")["qty"] == 6                   # 10 − 4
    assert _onhand("RM2")["qty"] == 0                   # 5 − 5


def test_stock_journal_is_idempotent():
    db = _setup()
    _post(db, "G1", "receipt_note", [{"stock_item_id": "RM1", "location_id": "W", "qty": 10, "rate": 100}])
    v = {"id": "SJ1", "tenant_id": T, "is_deleted": False, "status": "approved",
         "parent_type": "stock_journal", "voucher_no": "SJ1", "date": "2026-06-01",
         "inventory_lines": [
             {"stock_item_id": "RM1", "location_id": "W", "qty": 4, "role": "consume"},
             {"stock_item_id": "FG", "location_id": "W", "qty": 1, "role": "produce"}],
         "links": [], "statutory": None}
    asyncio.run(db.vouchers_v2.insert_one(v))
    asyncio.run(ve.post_voucher(v, USER, T))
    again = asyncio.run(ve.post_voucher(v, USER, T))
    assert again.get("already_posted") is True
    # 1 receipt + 2 journal legs = 3 entries, not 5.
    assert len([d for d in db.stock_ledger_entries.docs]) == 3


# ───────────────────────── inter-unit transfer ─────────────────────────

def test_interunit_transfer_moves_stock_and_carries_cost():
    db = _setup()
    _post(db, "G1", "receipt_note", [{"stock_item_id": "ITEM", "location_id": "UNIT_A", "qty": 100, "rate": 25}])
    res = _post(db, "TR1", "stock_transfer_material_interunit",
                [{"stock_item_id": "ITEM", "location_id": "UNIT_A", "to_location_id": "UNIT_B", "qty": 30}])
    assert res["movements"] == 2 and res["taxable_supply"] is False
    assert _onhand("ITEM", "UNIT_A")["qty"] == 70
    b = _onhand("ITEM", "UNIT_B")
    assert b["qty"] == 30 and b["value"] == 750         # carried at 25/unit


def test_interunit_transfer_flags_taxable_when_gst_present():
    db = _setup()
    _post(db, "G1", "receipt_note", [{"stock_item_id": "ITEM", "location_id": "UNIT_A", "qty": 10, "rate": 25}])
    res = _post(db, "TR1", "stock_transfer_interunit",
                [{"stock_item_id": "ITEM", "location_id": "UNIT_A", "to_location_id": "UNIT_B", "qty": 5}],
                statutory={"gst": {"igst": 90, "taxable_value": 500}})
    assert res["taxable_supply"] is True               # different-GSTIN supply
    assert _onhand("ITEM", "UNIT_B")["qty"] == 5


def test_interunit_transfer_rejects_same_location():
    db = _setup()
    _post(db, "G1", "receipt_note", [{"stock_item_id": "ITEM", "location_id": "UNIT_A", "qty": 10, "rate": 25}])
    import pytest
    from fastapi import HTTPException
    v = {"id": "TR1", "tenant_id": T, "is_deleted": False, "status": "approved",
         "parent_type": "stock_transfer_material_interunit", "voucher_no": "TR1", "date": "2026-06-01",
         "inventory_lines": [{"stock_item_id": "ITEM", "location_id": "UNIT_A", "to_location_id": "UNIT_A", "qty": 5}],
         "links": [], "statutory": None}
    asyncio.run(db.vouchers_v2.insert_one(v))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ve.post_voucher(v, USER, T))
    assert exc.value.status_code == 400
