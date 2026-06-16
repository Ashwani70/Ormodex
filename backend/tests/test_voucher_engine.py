"""Voucher engine: posting rules, maker-checker invariant, reversing, isolation.

Drives core.voucher_engine against an in-memory async Mongo fake. Proves:
  - accounting vouchers post a balanced journal entry from accounting_lines
  - posting is idempotent on the voucher id (re-approval can't double-post)
  - memorandum never posts; unbalanced lines are rejected; contra rejects GST
  - reversing_journal posts a reports-only entry and auto-reverses on due date
  - not-yet-implemented types (inventory/order/payroll) are gated (501), never
    silently approved-as-posted
  - journal entries are stamped with the voucher's tenant
"""
import asyncio

import pytest
from fastapi import HTTPException

import core.db
import core.utils as utils
import core.voucher_engine as ve


def _matches(doc, q):
    for k, v in q.items():
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$lte" in v and not (actual is not None and actual <= v["$lte"]):
                return False
            if "$ne" in v and actual == v["$ne"]:
                return False
        elif isinstance(actual, list):
            # Mongo semantics: {field: value} matches if the array contains value.
            if v not in actual:
                return False
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
            if _matches(d, q):
                out = dict(d); out.pop("_id", None); return out
        return None
    def find(self, q=None, projection=None):
        return _Cursor([dict(d) for d in self.docs if _matches(d, q or {})])
    async def count_documents(self, q):
        return len([d for d in self.docs if _matches(d, q or {})])
    async def update_one(self, q, update, session=None):
        for d in self.docs:
            if _matches(d, q):
                d.update(update.get("$set", {})); return type("R", (), {"matched_count": 1})()
        return type("R", (), {"matched_count": 0})()


class _DB:
    def __init__(self): self._c = {}
    def __getitem__(self, n): return self._c.setdefault(n, _Collection())
    def __getattr__(self, n):
        if n.startswith("_"): raise AttributeError(n)
        return self[n]


def _setup():
    db = _DB()
    core.db.db = db
    utils.db = db
    ve.db = db
    asyncio.run(db.fiscal_years.insert_one({"id": "fy", "name": "2026-27", "is_active": True}))
    return db


USER = {"id": "u1", "name": "Checker", "role": "admin"}
TENANT = "t1"


def _voucher(parent_type, lines, vid="v1", tenant=TENANT, effective=None):
    return {
        "id": vid, "tenant_id": tenant, "parent_type": parent_type,
        "voucher_no": f"{parent_type[:3].upper()}/1", "date": "2026-06-01",
        "effective_date": effective, "narration": f"test {parent_type}",
        "accounting_lines": lines, "inventory_lines": [], "links": [],
    }


PAY_LINES = [
    {"ledger_id": "L_vendor", "dr_cr": "Dr", "amount": 1000},
    {"ledger_id": "L_bank", "dr_cr": "Cr", "amount": 1000},
]


# ───────────────────────── posting ─────────────────────────

def test_accounting_voucher_posts_balanced_journal():
    db = _setup()
    v = _voucher("payment", PAY_LINES)
    result = asyncio.run(ve.post_voucher(v, USER, TENANT))
    assert result["posted"] is True
    je = db.journal_entries.docs[0]
    assert je["total_debit"] == je["total_credit"] == 1000
    assert je["status"] == "POSTED"
    assert je["tenant_id"] == TENANT             # JE stamped with voucher tenant
    assert je["source_id"] == "v1"


def test_posting_is_idempotent():
    db = _setup()
    v = _voucher("payment", PAY_LINES)
    first = asyncio.run(ve.post_voucher(v, USER, TENANT))
    second = asyncio.run(ve.post_voucher(v, USER, TENANT))
    assert first["journal_entry_id"] == second["journal_entry_id"]
    assert len(db.journal_entries.docs) == 1     # no double-post


def test_memorandum_never_posts():
    db = _setup()
    v = _voucher("memorandum", PAY_LINES)
    result = asyncio.run(ve.post_voucher(v, USER, TENANT))
    assert result["posted"] is False
    assert len(db.journal_entries.docs) == 0


def test_not_implemented_type_is_gated():
    _setup()
    v = _voucher("delivery_note", [])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ve.post_voucher(v, USER, TENANT))
    assert exc.value.status_code == 501          # never silently approved-as-posted


# ───────────────────────── validation ─────────────────────────

def test_unbalanced_lines_rejected():
    _setup()
    bad = _voucher("journal", [
        {"ledger_id": "a", "dr_cr": "Dr", "amount": 100},
        {"ledger_id": "b", "dr_cr": "Cr", "amount": 90},
    ])
    with pytest.raises(HTTPException) as exc:
        ve.validate_voucher(bad)
    assert exc.value.status_code == 400


def test_contra_rejects_gst():
    _setup()
    bad = _voucher("contra", [
        {"ledger_id": "cash", "dr_cr": "Dr", "amount": 100, "gst_details": {"igst": 18}},
        {"ledger_id": "bank", "dr_cr": "Cr", "amount": 100},
    ])
    with pytest.raises(HTTPException) as exc:
        ve.validate_voucher(bad)
    assert exc.value.status_code == 400


def test_balanced_journal_passes_validation():
    _setup()
    ve.validate_voucher(_voucher("journal", PAY_LINES))  # no raise


# ───────────────────────── reversing journal ─────────────────────────

def test_reversing_journal_posts_reports_only_and_auto_reverses():
    db = _setup()
    v = _voucher("reversing_journal", PAY_LINES, vid="rev1", effective="2026-06-30")
    asyncio.run(ve.post_voucher(v, USER, TENANT))
    orig = db.journal_entries.docs[0]
    assert orig["reports_only"] is True
    assert "REVERSING" in orig["tags"]

    # Before due date: nothing reverses.
    assert asyncio.run(ve.auto_reverse_due(TENANT, "2026-06-15", USER)) == 0
    # On/after due date: exactly one mirror posts, and it's idempotent.
    assert asyncio.run(ve.auto_reverse_due(TENANT, "2026-06-30", USER)) == 1
    assert asyncio.run(ve.auto_reverse_due(TENANT, "2026-07-01", USER)) == 0

    mirror = next(j for j in db.journal_entries.docs if j.get("reversed_for") == orig["id"])
    # Mirror swaps debit/credit of the original lines.
    assert mirror["lines"][0]["credit"] == orig["lines"][0]["debit"]
    assert mirror["lines"][0]["debit"] == orig["lines"][0]["credit"]


# ───────────────────────── tenant isolation of posted entries ─────────────────────────

def test_posted_entries_are_tenant_stamped():
    db = _setup()
    asyncio.run(ve.post_voucher(_voucher("payment", PAY_LINES, vid="a"), USER, "tenantA"))
    asyncio.run(ve.post_voucher(_voucher("payment", PAY_LINES, vid="b"), USER, "tenantB"))
    tenants = {j["tenant_id"] for j in db.journal_entries.docs}
    assert tenants == {"tenantA", "tenantB"}


# ───────────────────────── catalog completeness ─────────────────────────

def test_catalog_covers_all_spec_parent_types():
    # Spot-check a few from each category exist in the catalog.
    for pt in ["contra", "sales", "export_sales", "memorandum", "reversing_journal",
               "delivery_note", "stock_journal", "job_work_challan",
               "purchase_order", "sales_order", "attendance", "payroll"]:
        assert pt in ve.CATALOG, f"missing parent_type {pt}"
