"""Cross-cutting voucher rules: numbering, fulfilment, job-work window, reporting.

In-memory fake DB (supports find/find_one/insert/count/find_one_and_update and
Mongo-style $lte/$ne/$nin/$gte + dotted links.ref_voucher_id + array contains).
"""
import asyncio

import pytest
from fastapi import HTTPException

import core.db
import core.utils as utils
import core.voucher_numbering as vn
import core.voucher_engine as ve


def _get(doc, dotted):
    cur = doc
    for part in dotted.split("."):
        if isinstance(cur, list):
            # links.ref_voucher_id → list membership of that subfield
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
                if v not in actual:
                    return False
                continue
            if actual != v:
                return False
            continue
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$lte" in v and not (actual is not None and actual <= v["$lte"]): return False
            if "$gte" in v and not (actual is not None and actual >= v["$gte"]): return False
            if "$ne" in v and actual == v["$ne"]: return False
            if "$nin" in v:
                vals = actual if isinstance(actual, list) else [actual]
                if any(x in v["$nin"] for x in vals): return False
        elif isinstance(actual, list):
            if v not in actual: return False
        elif actual != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs): self._docs = docs
    def sort(self, *a, **k): return self
    def skip(self, *a): return self
    def limit(self, *a): return self
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
    async def find_one_and_update(self, q, update, upsert=False, return_document=True):
        for d in self.docs:
            if _match(d, q):
                for k, v in update.get("$inc", {}).items(): d[k] = d.get(k, 0) + v
                return dict(d)
        if upsert:
            d = dict(q)
            for k, v in update.get("$inc", {}).items(): d[k] = v
            self.docs.append(d); return dict(d)
        return None
    async def update_one(self, q, update, session=None, upsert=False):
        for d in self.docs:
            if _match(d, q):
                d.update(update.get("$set", {})); return type("R", (), {"modified_count": 1})()
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
    core.db.db = db; utils.db = db; vn.db = db; ve.db = db
    return db


USER = {"id": "u1", "name": "T", "role": "admin"}
T = "t1"


def _seed_vtype(db, vid, **cfg):
    base = {"id": vid, "tenant_id": T, "is_deleted": False,
            "numbering_method": "auto", "prefix": "SV", "suffix": "", "restart_rule": "yearly"}
    base.update(cfg)
    asyncio.run(db.master_voucher_types.insert_one(base))


# ───────────────────────── numbering ─────────────────────────

def test_auto_numbering_is_sequential_and_unique():
    db = _setup(); _seed_vtype(db, "vt")
    n1 = asyncio.run(vn.generate_voucher_no(tenant=T, parent_type="sales", voucher_type_id="vt",
                                            fy="2026-27", voucher_date="2026-06-01"))
    n2 = asyncio.run(vn.generate_voucher_no(tenant=T, parent_type="sales", voucher_type_id="vt",
                                            fy="2026-27", voucher_date="2026-06-02"))
    assert n1 == "SV/2026-27/00001"
    assert n2 == "SV/2026-27/00002"


def test_yearly_restart_resets_per_fy():
    db = _setup(); _seed_vtype(db, "vt")
    a = asyncio.run(vn.generate_voucher_no(tenant=T, parent_type="sales", voucher_type_id="vt",
                                           fy="2026-27", voucher_date="2026-06-01"))
    b = asyncio.run(vn.generate_voucher_no(tenant=T, parent_type="sales", voucher_type_id="vt",
                                           fy="2027-28", voucher_date="2027-04-01"))
    assert a.endswith("00001") and b.endswith("00001")   # new FY restarts at 1
    assert "2026-27" in a and "2027-28" in b


def test_monthly_restart_buckets_by_month():
    db = _setup(); _seed_vtype(db, "vt", restart_rule="monthly")
    a = asyncio.run(vn.generate_voucher_no(tenant=T, parent_type="sales", voucher_type_id="vt",
                                           fy="2026-27", voucher_date="2026-06-01"))
    b = asyncio.run(vn.generate_voucher_no(tenant=T, parent_type="sales", voucher_type_id="vt",
                                           fy="2026-27", voucher_date="2026-07-01"))
    assert "2026-06" in a and a.endswith("00001")
    assert "2026-07" in b and b.endswith("00001")        # July restarts


def test_manual_numbering_requires_and_dedupes():
    db = _setup(); _seed_vtype(db, "vt", numbering_method="manual")
    # Missing manual number → 400.
    with pytest.raises(HTTPException) as e1:
        asyncio.run(vn.generate_voucher_no(tenant=T, parent_type="sales", voucher_type_id="vt",
                                           fy="2026-27", voucher_date="2026-06-01"))
    assert e1.value.status_code == 400
    # Supplied once → ok; insert it then a duplicate → 409.
    no = asyncio.run(vn.generate_voucher_no(tenant=T, parent_type="sales", voucher_type_id="vt",
                                            fy="2026-27", voucher_date="2026-06-01", manual_no="INV-1"))
    assert no == "INV-1"
    asyncio.run(db.vouchers_v2.insert_one({"id": "x", "tenant_id": T, "is_deleted": False,
                                           "voucher_type_id": "vt", "fiscal_year": "2026-27", "voucher_no": "INV-1"}))
    with pytest.raises(HTTPException) as e2:
        asyncio.run(vn.generate_voucher_no(tenant=T, parent_type="sales", voucher_type_id="vt",
                                           fy="2026-27", voucher_date="2026-06-01", manual_no="INV-1"))
    assert e2.value.status_code == 409


def test_numbering_method_none_returns_no_number():
    db = _setup(); _seed_vtype(db, "vt", numbering_method="none")
    no = asyncio.run(vn.generate_voucher_no(tenant=T, parent_type="journal", voucher_type_id="vt",
                                            fy="2026-27", voucher_date="2026-06-01"))
    assert no is None


def test_numbering_is_tenant_isolated():
    db = _setup(); _seed_vtype(db, "vt")
    asyncio.run(db.master_voucher_types.insert_one(
        {"id": "vt", "tenant_id": "t2", "is_deleted": False, "numbering_method": "auto",
         "prefix": "SV", "restart_rule": "yearly"}))
    a = asyncio.run(vn.generate_voucher_no(tenant="t1", parent_type="sales", voucher_type_id="vt", fy="2026-27", voucher_date="2026-06-01"))
    b = asyncio.run(vn.generate_voucher_no(tenant="t2", parent_type="sales", voucher_type_id="vt", fy="2026-27", voucher_date="2026-06-01"))
    assert a.endswith("00001") and b.endswith("00001")   # separate counters per tenant


# ───────────────────────── order fulfilment ─────────────────────────

def _approved_voucher(db, vid, parent_type, inv_lines, links=None):
    # 'posted' is the fulfilment-relevant state (movements written).
    asyncio.run(db.vouchers_v2.insert_one({
        "id": vid, "tenant_id": T, "is_deleted": False, "status": "posted",
        "parent_type": parent_type, "voucher_no": vid, "date": "2026-06-01",
        "inventory_lines": inv_lines, "links": links or [],
    }))


def test_order_fulfilment_pending_qty():
    db = _setup()
    _approved_voucher(db, "PO1", "purchase_order", [{"stock_item_id": "I1", "qty": 100}])
    # Two GRNs receive 60 then 30 against the PO.
    _approved_voucher(db, "GRN1", "receipt_note", [{"stock_item_id": "I1", "qty": 60}],
                      links=[{"ref_voucher_id": "PO1", "ref_type": "purchase_order"}])
    _approved_voucher(db, "GRN2", "receipt_note", [{"stock_item_id": "I1", "qty": 30}],
                      links=[{"ref_voucher_id": "PO1", "ref_type": "purchase_order"}])
    res = asyncio.run(ve.order_fulfilment("PO1", T))
    row = res["lines"][0]
    assert row["ordered_qty"] == 100 and row["fulfilled_qty"] == 90 and row["pending_qty"] == 10
    assert res["fully_fulfilled"] is False


def test_order_fulfilment_complete():
    db = _setup()
    _approved_voucher(db, "SO1", "sales_order", [{"stock_item_id": "I1", "qty": 5}])
    _approved_voucher(db, "DN1", "delivery_note", [{"stock_item_id": "I1", "qty": 5}],
                      links=[{"ref_voucher_id": "SO1", "ref_type": "sales_order"}])
    res = asyncio.run(ve.order_fulfilment("SO1", T))
    assert res["fully_fulfilled"] is True


# ───────────────────────── job-work return window ─────────────────────────

def test_job_work_window_breach_flags_deemed_supply():
    db = _setup()
    # Inputs sent >365 days ago, nothing returned → deemed supply.
    asyncio.run(db.vouchers_v2.insert_one({
        "id": "JC1", "tenant_id": T, "is_deleted": False, "status": "posted",
        "parent_type": "job_work_challan", "voucher_no": "JC1", "date": "2024-01-01",
        "inventory_lines": [{"stock_item_id": "I1", "qty": 50}],
        "statutory": {"extra": {"goods_type": "inputs"}}, "links": [],
    }))
    res = asyncio.run(ve.job_work_reconciliation(T, as_of="2026-06-16"))
    ch = res["challans"][0]
    assert ch["alert"] == "deemed_supply"
    assert ch["total_pending_qty"] == 50
    assert len(res["breached"]) == 1


def test_job_work_window_open_and_closed():
    db = _setup()
    # Capital goods, sent recently, fully returned → closed.
    asyncio.run(db.vouchers_v2.insert_one({
        "id": "JC2", "tenant_id": T, "is_deleted": False, "status": "posted",
        "parent_type": "job_work_challan", "voucher_no": "JC2", "date": "2026-05-01",
        "inventory_lines": [{"stock_item_id": "I1", "qty": 10}],
        "statutory": {"extra": {"goods_type": "capital_goods"}}, "links": [],
    }))
    asyncio.run(db.vouchers_v2.insert_one({
        "id": "MI1", "tenant_id": T, "is_deleted": False, "status": "posted",
        "parent_type": "job_work_material_inward", "voucher_no": "MI1", "date": "2026-05-20",
        "inventory_lines": [{"stock_item_id": "I1", "qty": 10}],
        "links": [{"ref_voucher_id": "JC2", "ref_type": "job_work_challan"}],
    }))
    res = asyncio.run(ve.job_work_reconciliation(T, as_of="2026-06-16"))
    ch = next(c for c in res["challans"] if c["challan_id"] == "JC2")
    assert ch["alert"] == "closed" and ch["window_days"] == 365 * 3


# ───────────────────────── statutory exclusion + effective-date cutoff ─────────────────────────

def test_statutory_filter_excludes_reversing_and_memorandum():
    f = ve.statutory_je_filter(T)
    assert f["reports_only"] == {"$ne": True}
    assert f["tags"] == {"$nin": ["MEMORANDUM"]}
    # Management filter has no such exclusion.
    assert "reports_only" not in ve.management_je_filter(T)


def test_effective_date_drives_cutoff_when_set():
    f = ve.statutory_je_filter(T, as_of="2026-06-30", use_effective_date=True)
    assert f["effective_date"] == {"$lte": "2026-06-30"}
    f2 = ve.statutory_je_filter(T, as_of="2026-06-30", use_effective_date=False)
    assert f2["date"] == {"$lte": "2026-06-30"}


def test_reporting_date_prefers_effective_date():
    assert ve.reporting_date({"date": "2026-06-01", "effective_date": "2026-07-01"}) == "2026-07-01"
    assert ve.reporting_date({"date": "2026-06-01"}) == "2026-06-01"
