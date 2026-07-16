"""Automated reconciliation engine: posted docs → reconciled, idempotent.

Covers order-fulfilment reconciliation and GRN↔bill matching. In-memory fake DB.
"""
import asyncio

import core.db
import core.utils as utils
import core.voucher_engine as ve


def _get(doc, dotted):
    cur = doc
    for part in dotted.split("."):
        if isinstance(cur, list):
            return [(_get(x, part) if isinstance(x, dict) else None) for x in cur]
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _match(doc, q):
    for k, v in q.items():
        if "." in k:
            actual = _get(doc, k)
            if isinstance(actual, list):
                if v not in actual: return False
                continue
            if actual != v: return False
            continue
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$in" in v and actual not in v["$in"]: return False
            if "$ne" in v and actual == v["$ne"]: return False
        elif isinstance(actual, list):
            if v not in actual: return False
        elif actual != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs): self._docs = docs
    def sort(self, *a, **k): return self
    async def to_list(self, _n): return [dict(d) for d in self._docs]


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


class _DB:
    def __init__(self): self._c = {}
    def __getitem__(self, n): return self._c.setdefault(n, _Collection())
    def __getattr__(self, n):
        if n.startswith("_"): raise AttributeError(n)
        return self[n]


def _setup():
    db = _DB()
    core.db.db = db; utils.db = db; ve.db = db  # type: ignore[assignment]
    return db


USER = {"id": "u1", "name": "T", "role": "admin"}
T = "t1"


def _doc(db, vid, parent_type, *, status="posted", inv=None, links=None):
    d = {"id": vid, "tenant_id": T, "is_deleted": False, "status": status,
         "parent_type": parent_type, "voucher_no": vid, "date": "2026-06-01",
         "inventory_lines": inv or [], "links": links or []}
    asyncio.run(db.vouchers_v2.insert_one(d))
    return d


def _status(db, vid):
    return next(d for d in db.vouchers_v2.docs if d["id"] == vid)["status"]


# ───────────────────────── order fulfilment reconciliation ─────────────────────────

def test_fully_fulfilled_order_is_reconciled():
    db = _setup()
    _doc(db, "SO1", "sales_order", inv=[{"stock_item_id": "I1", "qty": 10}])
    _doc(db, "DN1", "delivery_note", inv=[{"stock_item_id": "I1", "qty": 10}],
         links=[{"ref_voucher_id": "SO1", "ref_type": "sales_order"}])
    res = asyncio.run(ve.run_reconciliation(T, USER, ["order_fulfilment"]))
    assert res["total_reconciled"] == 1
    assert _status(db, "SO1") == "reconciled"


def test_partial_order_is_not_reconciled():
    db = _setup()
    _doc(db, "SO1", "sales_order", inv=[{"stock_item_id": "I1", "qty": 10}])
    _doc(db, "DN1", "delivery_note", inv=[{"stock_item_id": "I1", "qty": 4}],
         links=[{"ref_voucher_id": "SO1", "ref_type": "sales_order"}])
    res = asyncio.run(ve.run_reconciliation(T, USER, ["order_fulfilment"]))
    assert res["total_reconciled"] == 0
    assert _status(db, "SO1") == "posted"


def test_reconciliation_is_idempotent():
    db = _setup()
    _doc(db, "SO1", "sales_order", inv=[{"stock_item_id": "I1", "qty": 5}])
    _doc(db, "DN1", "delivery_note", inv=[{"stock_item_id": "I1", "qty": 5}],
         links=[{"ref_voucher_id": "SO1", "ref_type": "sales_order"}])
    first = asyncio.run(ve.run_reconciliation(T, USER, ["order_fulfilment"]))
    second = asyncio.run(ve.run_reconciliation(T, USER, ["order_fulfilment"]))
    assert first["total_reconciled"] == 1
    assert second["total_reconciled"] == 0     # already reconciled, no re-do


# ───────────────────────── GRN ↔ bill reconciliation ─────────────────────────

def test_grn_reconciled_when_bill_links_it():
    db = _setup()
    _doc(db, "GRN1", "receipt_note", inv=[{"stock_item_id": "I1", "qty": 10}])
    _doc(db, "BILL1", "purchase", links=[{"ref_voucher_id": "GRN1", "ref_type": "receipt_note"}])
    res = asyncio.run(ve.run_reconciliation(T, USER, ["grn_to_bill"]))
    assert res["total_reconciled"] == 1
    assert _status(db, "GRN1") == "reconciled"


def test_grn_not_reconciled_without_bill():
    db = _setup()
    _doc(db, "GRN1", "receipt_note", inv=[{"stock_item_id": "I1", "qty": 10}])
    res = asyncio.run(ve.run_reconciliation(T, USER, ["grn_to_bill"]))
    assert res["total_reconciled"] == 0
    assert _status(db, "GRN1") == "posted"


def test_run_all_rules_and_unknown_rule_rejected():
    db = _setup()
    _doc(db, "SO1", "sales_order", inv=[{"stock_item_id": "I1", "qty": 2}])
    _doc(db, "DN1", "delivery_note", inv=[{"stock_item_id": "I1", "qty": 2}],
         links=[{"ref_voucher_id": "SO1", "ref_type": "sales_order"}])
    res = asyncio.run(ve.run_reconciliation(T, USER))   # all rules
    assert res["total_reconciled"] == 1

    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ve.run_reconciliation(T, USER, ["nope"]))
    assert exc.value.status_code == 400
