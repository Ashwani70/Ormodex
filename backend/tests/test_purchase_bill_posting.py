"""Purchase v2 accounting: bill posts a balanced voucher; return reverses it.

Drives core.ledger_posting.post_purchase_bill_journal / post_purchase_return_journal
against an in-memory async Mongo fake — no live server/DB. Proves:
  - bill journal balances (debits == credits), incl. TDS withholding
  - intra-state -> CGST+SGST, inter-state -> IGST
  - return journal reverses the bill (AP debited, Inventory+ITC credited)
  - idempotency (same source_id posts once)
"""
import asyncio

import core.db
import core.utils as utils
import core.ledger_posting as lp


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, _n):
        return [dict(d) for d in self._docs]


class _Collection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc, session=None):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": doc.get("id")})()

    async def find_one(self, q, projection=None, session=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                out = dict(d)
                out.pop("_id", None)
                return out
        return None

    def find(self, q=None, projection=None):
        q = q or {}
        return _Cursor([d for d in self.docs if all(d.get(k) == v for k, v in q.items())])

    async def count_documents(self, q):
        q = q or {}
        return len([d for d in self.docs if all(d.get(k) == v for k, v in q.items())])


class _DB:
    def __init__(self):
        self._cols = {}

    def __getitem__(self, name):
        return self._cols.setdefault(name, _Collection())

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]


def _setup(company_state="27"):
    db = _DB()
    core.db.db = db
    utils.db = db
    utils._txn_supported = False
    # Minimal seeded references.
    asyncio.run(db.companies.insert_one({"id": "c1", "state_code": company_state}))
    asyncio.run(db.fiscal_years.insert_one({"id": "fy", "name": "2026-27", "is_active": True}))
    for code, name in [("1200", "Inventory"), ("1500", "GST Input Tax Credit"),
                       ("2001", "Accounts Payable"), ("2006", "TDS Payable")]:
        asyncio.run(db.chart_of_accounts.insert_one({"id": code, "code": code, "name": name}))
    return db


USER = {"id": "u1", "name": "T", "role": "admin"}
# 100 units @ 100 = 10,000 taxable; 18% GST = 1,800; gross = 11,800
LINES = [{"stock_item_id": "i1", "qty": 100, "rate": 100, "gst_rate": 18}]


def _je(db):
    return db.journal_entries.docs[-1]


def test_bill_journal_is_balanced_intrastate():
    db = _setup(company_state="27")
    asyncio.run(db.vendors.insert_one({"id": "v1", "state_code": "27"}))  # same state
    je = asyncio.run(lp.post_purchase_bill_journal(
        db, bill_id="b1", bill_number="BILL-1", vendor_id="v1", vendor_name="V",
        lines=LINES, tds_rate=0, user=USER,
    ))
    assert je is not None
    assert abs(je["total_debit"] - je["total_credit"]) < 0.01
    assert je["total_debit"] == 11800
    # Intra-state: CGST+SGST, no IGST
    assert je["cgst"] == 900 and je["sgst"] == 900 and je["igst"] == 0
    codes = {l["account_code"]: l for l in je["lines"]}
    assert codes["1200"]["debit"] == 10000   # inventory taxable
    assert codes["1500"]["debit"] == 1800     # input GST
    assert codes["2001"]["credit"] == 11800   # full payable (no TDS)


def test_bill_journal_interstate_uses_igst():
    db = _setup(company_state="27")
    asyncio.run(db.vendors.insert_one({"id": "v1", "state_code": "29"}))  # different state
    je = asyncio.run(lp.post_purchase_bill_journal(
        db, bill_id="b1", bill_number="BILL-1", vendor_id="v1", vendor_name="V",
        lines=LINES, user=USER,
    ))
    assert je["igst"] == 1800 and je["cgst"] == 0 and je["sgst"] == 0
    assert abs(je["total_debit"] - je["total_credit"]) < 0.01


def test_bill_with_tds_splits_payable():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "state_code": "27"}))
    je = asyncio.run(lp.post_purchase_bill_journal(
        db, bill_id="b1", bill_number="BILL-1", vendor_id="v1", vendor_name="V",
        lines=LINES, tds_rate=10, user=USER,  # 10% of 10,000 taxable = 1,000
    ))
    codes = {l["account_code"]: l for l in je["lines"]}
    assert codes["2006"]["credit"] == 1000          # TDS withheld
    assert codes["2001"]["credit"] == 11800 - 1000  # net payable to vendor
    assert abs(je["total_debit"] - je["total_credit"]) < 0.01


def test_bill_posting_is_idempotent():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "state_code": "27"}))
    first = asyncio.run(lp.post_purchase_bill_journal(
        db, bill_id="b1", bill_number="BILL-1", vendor_id="v1", vendor_name="V",
        lines=LINES, user=USER))
    second = asyncio.run(lp.post_purchase_bill_journal(
        db, bill_id="b1", bill_number="BILL-1", vendor_id="v1", vendor_name="V",
        lines=LINES, user=USER))
    assert first["id"] == second["id"]
    assert db.journal_entries.count_documents({"source_collection": "purchase_bills"}) is not None
    assert len(db.journal_entries.docs) == 1


def test_return_journal_reverses_the_bill():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "state_code": "27"}))
    je = asyncio.run(lp.post_purchase_return_journal(
        db, return_id="r1", return_number="DN-1", vendor_id="v1", vendor_name="V",
        lines=LINES, user=USER,
    ))
    codes = {l["account_code"]: l for l in je["lines"]}
    # Reversal: AP debited (we owe less), Inventory + ITC credited (goods/credit go back)
    assert codes["2001"]["debit"] == 11800
    assert codes["1200"]["credit"] == 10000
    assert codes["1500"]["credit"] == 1800
    assert abs(je["total_debit"] - je["total_credit"]) < 0.01
    assert "RETURN" in je["tags"]


def test_posting_skips_without_chart_of_accounts():
    db = _DB()
    core.db.db = db
    utils.db = db
    asyncio.run(db.companies.insert_one({"id": "c1", "state_code": "27"}))
    # No chart_of_accounts seeded -> poster returns None, never crashes.
    je = asyncio.run(lp.post_purchase_bill_journal(
        db, bill_id="b1", bill_number="BILL-1", vendor_id=None, vendor_name="V",
        lines=LINES, user=USER))
    assert je is None
