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
import routers.purchase_v2
import routers.ledger


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
        doc = dict(doc)
        if "_id" not in doc:
            doc["_id"] = doc.get("id")
        self.docs.append(doc)
        return type("R", (), {"inserted_id": doc.get("id")})()

    async def insert_many(self, docs, session=None):
        for d in docs:
            await self.insert_one(d, session)
        return type("R", (), {"inserted_ids": [d.get("id") for d in docs]})()

    async def find_one(self, q, projection=None, session=None):
        for d in self.docs:
            match = True
            for k, v in q.items():
                if k == "_id":
                    if d.get("_id") != v:
                        match = False
                        break
                else:
                    if d.get(k) != v:
                        match = False
                        break
            if match:
                out = dict(d)
                out.pop("_id", None)
                return out
        return None

    def find(self, q=None, projection=None):
        q = q or {}
        res = []
        for d in self.docs:
            match = True
            for k, v in q.items():
                if isinstance(v, dict) and "$in" in v:
                    if d.get(k) not in v["$in"]:
                        match = False
                        break
                else:
                    if d.get(k) != v:
                        match = False
                        break
            if match:
                res.append(d)
        return _Cursor(res)

    async def count_documents(self, q):
        q = q or {}
        return len([d for d in self.docs if all(d.get(k) == v for k, v in q.items())])

    async def find_one_and_update(self, q, update, upsert=False, return_document=True):
        doc = None
        for d in self.docs:
            match = True
            for k, v in q.items():
                if k == "_id":
                    if d.get("_id") != v:
                        match = False
                        break
                else:
                    if d.get(k) != v:
                        match = False
                        break
            if match:
                doc = d
                break
        if not doc:
            if upsert:
                doc = dict(q)
                self.docs.append(doc)
            else:
                return None
        # Apply update
        inc_dict = update.get("$inc", {})
        for k, v in inc_dict.items():
            doc[k] = doc.get(k, 0) + v
        set_dict = update.get("$set", {})
        for k, v in set_dict.items():
            doc[k] = v
        return dict(doc)

    async def update_one(self, q, update, session=None, upsert=False):
        set_dict = update.get("$set", {})
        inc_dict = update.get("$inc", {})
        found = False
        for d in self.docs:
            match = True
            for k, v in q.items():
                if k == "_id":
                    if d.get("_id") != v:
                        match = False
                        break
                else:
                    if d.get(k) != v:
                        match = False
                        break
            if match:
                for k, v in set_dict.items():
                    d[k] = v
                for k, v in inc_dict.items():
                    d[k] = d.get(k, 0) + v
                found = True
                break
        if not found and upsert:
            new_doc = dict(q)
            for k, v in set_dict.items():
                new_doc[k] = v
            for k, v in inc_dict.items():
                new_doc[k] = v
            self.docs.append(new_doc)
        return type("R", (), {"modified_count": 1 if found else 0})()

    def aggregate(self, pipeline):
        group_stage = None
        for stage in pipeline:
            if "$group" in stage:
                group_stage = stage["$group"]
                break
        
        if group_stage:
            group_id_field = group_stage["_id"].replace("$", "")
            first_field = next(k for k, v in group_stage.items() if isinstance(v, dict) and "$first" in v)
            first_val_field = group_stage[first_field]["$first"].replace("$", "")
            sum_total_field = next(k for k, v in group_stage.items() if isinstance(v, dict) and "$sum" in v and v["$sum"] == "$total")
            sum_paid_field = next(k for k, v in group_stage.items() if isinstance(v, dict) and "$sum" in v and v["$sum"] == "$payment_received")
            
            groups = {}
            for doc in self.docs:
                gid = doc.get(group_id_field)
                if gid not in groups:
                    groups[gid] = {
                        "_id": gid,
                        first_field: doc.get(first_val_field),
                        sum_total_field: 0.0,
                        sum_paid_field: 0.0,
                        "count": 0
                    }
                groups[gid][sum_total_field] += float(doc.get("total") or 0.0)
                groups[gid][sum_paid_field] += float(doc.get("payment_received") or 0.0)
                groups[gid]["count"] += 1
            
            out_docs = list(groups.values())
            for d in out_docs:
                d["outstanding"] = round(d[sum_total_field] - d[sum_paid_field], 2)
            
            out_docs.sort(key=lambda x: x["outstanding"], reverse=True)
            return _Cursor(out_docs)
        
        return _Cursor([])


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
    from typing import Any
    db: Any = _DB()
    core.db.db = db
    utils.db = db
    routers.purchase_v2.db = db
    routers.ledger.db = db
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
    assert je is not None
    assert je["igst"] == 1800 and je["cgst"] == 0 and je["sgst"] == 0
    assert abs(je["total_debit"] - je["total_credit"]) < 0.01


def test_bill_with_tds_splits_payable():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "state_code": "27"}))
    je = asyncio.run(lp.post_purchase_bill_journal(
        db, bill_id="b1", bill_number="BILL-1", vendor_id="v1", vendor_name="V",
        lines=LINES, tds_rate=10, user=USER,  # 10% of 10,000 taxable = 1,000
    ))
    assert je is not None
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
    assert first is not None and second is not None
    assert first["id"] == second["id"]
    # Removed the unawaited count_documents call warning.
    assert len(db.journal_entries.docs) == 1


def test_return_journal_reverses_the_bill():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "state_code": "27"}))
    je = asyncio.run(lp.post_purchase_return_journal(
        db, return_id="r1", return_number="DN-1", vendor_id="v1", vendor_name="V",
        lines=LINES, user=USER,
    ))
    assert je is not None
    codes = {l["account_code"]: l for l in je["lines"]}
    # Reversal: AP debited (we owe less), Inventory + ITC credited (goods/credit go back)
    assert codes["2001"]["debit"] == 11800
    assert codes["1200"]["credit"] == 10000
    assert codes["1500"]["credit"] == 1800
    assert abs(je["total_debit"] - je["total_credit"]) < 0.01
    assert "RETURN" in je["tags"]


def test_posting_skips_without_chart_of_accounts():
    from typing import Any
    db: Any = _DB()
    core.db.db = db
    utils.db = db
    asyncio.run(db.companies.insert_one({"id": "c1", "state_code": "27"}))
    # No chart_of_accounts seeded -> poster returns None, never crashes.
    je = asyncio.run(lp.post_purchase_bill_journal(
        db, bill_id="b1", bill_number="BILL-1", vendor_id=None, vendor_name="V",
        lines=LINES, user=USER))
    assert je is None


def test_create_bill_endpoint():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))
    
    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill
    
    payload = PurchaseBill(
        vendor_invoice_no="INV-123",
        vendor_invoice_date="2026-06-01",
        vendor_id="v1",
        lines=[
            BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)
        ]
    )
    
    bill = asyncio.run(create_bill(payload, user=USER))
    assert bill is not None
    assert bill["total"] == 1180.0
    assert bill["payment_received"] == 0.0
    assert bill["status"] == "UNPAID"
    assert bill["journal_entry_id"] is not None


def test_record_bill_payment_endpoint():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))
    
    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill, record_bill_payment
    
    payload = PurchaseBill(
        vendor_invoice_no="INV-123",
        vendor_invoice_date="2026-06-01",
        vendor_id="v1",
        lines=[
            BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)
        ]
    )
    
    bill = asyncio.run(create_bill(payload, user=USER))
    assert bill is not None
    
    # Record partial payment
    updated_bill = asyncio.run(record_bill_payment(bill_id=bill["id"], amount=500.0, user=USER))
    assert updated_bill is not None
    assert updated_bill["payment_received"] == 500.0
    assert updated_bill["status"] == "PARTIAL"
    
    # Record remaining payment
    final_bill = asyncio.run(record_bill_payment(bill_id=bill["id"], amount=680.0, user=USER))
    assert final_bill is not None
    assert final_bill["payment_received"] == 1180.0
    assert final_bill["status"] == "PAID"
 
 
def test_ledger_party_endpoints():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))
    
    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill, record_bill_payment
    from routers.ledger import party_ledger, party_outstanding, ageing_report
    
    # Create a paid bill and an unpaid bill
    bill1 = asyncio.run(create_bill(PurchaseBill(
        vendor_invoice_no="INV-001",
        vendor_invoice_date="2026-06-01",
        vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)]
    ), user=USER))
    assert bill1 is not None
    asyncio.run(record_bill_payment(bill_id=bill1["id"], amount=1180.0, user=USER))
    
    bill2 = asyncio.run(create_bill(PurchaseBill(
        vendor_invoice_no="INV-002",
        vendor_invoice_date="2026-06-05",
        vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=20, rate=100, gst_rate=18)]
    ), user=USER))
    assert bill2 is not None
    
    # Test party ledger
    ledger_res = asyncio.run(party_ledger(party_type="SUPPLIER", party_id="v1", user=USER))
    assert len(ledger_res["invoices"]) == 2
    
    # Test party outstanding
    outstanding_res = asyncio.run(party_outstanding(party_type="SUPPLIER", user=USER))
    assert len(outstanding_res) == 1
    assert outstanding_res[0]["_id"] == "v1"
    assert outstanding_res[0]["outstanding"] == 2360.0  # bill2 total = 2360.0, bill1 outstanding = 0.0
    
    # Test ageing report
    ageing_res = asyncio.run(ageing_report(party_type="SUPPLIER", as_of_date="2026-06-10", user=USER))
    # bill2 date is 2026-06-05, as_of_date is 2026-06-10, age is 5 days (0-30 bucket)
    assert len(ageing_res["buckets"]["0-30"]) == 1
    assert ageing_res["buckets"]["0-30"][0]["outstanding"] == 2360.0

