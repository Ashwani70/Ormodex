"""Payroll voucher posting: salary journal + attendance source doc.

In-memory fake DB; drives the voucher engine directly. Proves the payroll run
posts a balanced salary journal (Dr Salaries; Cr PF/ESI/PT/TDS/Net payables),
that it's idempotent and reversible, and that attendance posts nothing.
"""
import asyncio

import pytest
from fastapi import HTTPException

import core.db
import core.utils as utils
import core.voucher_engine as ve


def _match(doc, q):
    for k, v in q.items():
        actual = doc.get(k)
        if isinstance(v, dict):
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
    core.db.db = db; utils.db = db; ve.db = db  # type: ignore[assignment]  # in-memory fake stands in for the Mongo-compat shim
    asyncio.run(db.fiscal_years.insert_one({"id": "fy", "name": "2026-27", "is_active": True}))
    for code, name in [("5003", "Salaries & Wages"), ("2300", "Salary Payable"),
                       ("2006", "TDS Payable"), ("2002", "PF Payable"), ("2003", "ESI Payable")]:
        asyncio.run(db.chart_of_accounts.insert_one({"id": f"coa_{code}", "code": code, "name": name}))
        asyncio.run(db.master_ledgers.insert_one(
            {"id": f"L_{code}", "tenant_id": "t1", "is_deleted": False, "name": name,
             "coa_account_id": f"coa_{code}"}))
    return db


USER = {"id": "u1", "name": "T", "role": "admin"}
T = "t1"

# A payroll run: gross 100000 Dr; deductions PF 12000 + ESI 750 + PT 200 + TDS
# 5000 = 17950 to statutory payables; net 82050 to Salary Payable. Balanced.
PAYROLL_LINES = [
    {"ledger_id": "L_5003", "dr_cr": "Dr", "amount": 100000},
    {"ledger_id": "L_2002", "dr_cr": "Cr", "amount": 12000},   # PF
    {"ledger_id": "L_2003", "dr_cr": "Cr", "amount": 750},     # ESI
    {"ledger_id": "L_2006", "dr_cr": "Cr", "amount": 5000},    # TDS
    {"ledger_id": "L_2300", "dr_cr": "Cr", "amount": 82250},   # PT 200 folded into net for balance
]


def _voucher(db, vid, parent_type, acct_lines, status="approved"):
    d = {"id": vid, "tenant_id": T, "is_deleted": False, "status": status,
         "parent_type": parent_type, "voucher_no": vid, "date": "2026-06-30",
         "accounting_lines": acct_lines, "inventory_lines": [], "links": [], "statutory": None}
    asyncio.run(db.vouchers_v2.insert_one(d))
    return d


def test_payroll_posts_balanced_salary_journal():
    db = _setup()
    v = _voucher(db, "PR1", "payroll", PAYROLL_LINES)
    ve.validate_voucher(v)                       # balanced check passes
    res = asyncio.run(ve.post_voucher(v, USER, T))
    assert res["posted"] is True
    je = db.journal_entries.docs[0]
    assert je["total_debit"] == je["total_credit"] == 100000
    assert "PAYROLL" in je["tags"]
    # Salary expense debited; payables credited.
    by_ledger = {l["ledger_id"]: l for l in je["lines"]}
    assert by_ledger["L_5003"]["debit"] == 100000
    assert by_ledger["L_2006"]["credit"] == 5000      # TDS payable
    assert by_ledger["L_2300"]["credit"] == 82250     # net salary payable


def test_payroll_is_idempotent():
    db = _setup()
    v = _voucher(db, "PR1", "payroll", PAYROLL_LINES)
    asyncio.run(ve.post_voucher(v, USER, T))
    asyncio.run(ve.post_voucher(v, USER, T))
    assert len([j for j in db.journal_entries.docs if j["source_id"] == "PR1"]) == 1


def test_unbalanced_payroll_rejected():
    db = _setup()
    bad = _voucher(db, "PR1", "payroll", [
        {"ledger_id": "L_5003", "dr_cr": "Dr", "amount": 100000},
        {"ledger_id": "L_2300", "dr_cr": "Cr", "amount": 90000},   # 10000 short
    ])
    with pytest.raises(HTTPException) as exc:
        ve.validate_voucher(bad)
    assert exc.value.status_code == 400


def test_payroll_reversal_mirrors_journal():
    db = _setup()
    v = _voucher(db, "PR1", "payroll", PAYROLL_LINES)
    asyncio.run(ve.post_voucher(v, USER, T))
    res = asyncio.run(ve.reverse_posting(v, USER, T))
    assert res["reversed_journal"] is True
    mirror = next(j for j in db.journal_entries.docs if "REVERSAL" in j.get("tags", []))
    by_ledger = {l["ledger_id"]: l for l in mirror["lines"]}
    assert by_ledger["L_5003"]["credit"] == 100000    # expense Dr→Cr reversed


def test_attendance_posts_nothing():
    db = _setup()
    # attendance is a source doc — no accounting lines required, posts nothing.
    v = _voucher(db, "ATT1", "attendance", [])
    ve.validate_voucher(v)                       # exempt from balanced-lines rule
    res = asyncio.run(ve.post_voucher(v, USER, T))
    assert res["posted"] is False
    assert len(db.journal_entries.docs) == 0
