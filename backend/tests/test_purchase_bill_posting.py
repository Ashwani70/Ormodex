"""Purchase v2 accounting: bill posts a balanced voucher; return reverses it.

Drives core.ledger_posting.post_purchase_bill_journal / post_purchase_return_journal
against an in-memory async Mongo fake — no live server/DB. Proves:
  - bill journal balances (debits == credits), incl. TDS withholding
  - intra-state -> CGST+SGST, inter-state -> IGST
  - return journal reverses the bill (AP debited, Inventory+ITC credited)
  - idempotency (same source_id posts once)
"""
import asyncio
from datetime import date

import core.db
import core.utils as utils
import core.ledger_posting as lp
import routers.purchase_v2
import routers.ledger
import routers.debtors_creditors
import routers.accounting


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
                elif isinstance(v, dict) and "$ne" in v:
                    if d.get(k) == v["$ne"]:
                        match = False
                        break
                elif isinstance(v, dict) and "$in" in v:
                    if d.get(k) not in v["$in"]:
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
                if isinstance(v, dict) and ("$gte" in v or "$lte" in v or "$gt" in v or "$lt" in v):
                    dv = d.get(k)
                    if "$gte" in v and not (dv is not None and dv >= v["$gte"]):
                        match = False
                        break
                    if "$lte" in v and not (dv is not None and dv <= v["$lte"]):
                        match = False
                        break
                    if "$gt" in v and not (dv is not None and dv > v["$gt"]):
                        match = False
                        break
                    if "$lt" in v and not (dv is not None and dv < v["$lt"]):
                        match = False
                        break
                elif isinstance(v, dict) and "$in" in v:
                    if d.get(k) not in v["$in"]:
                        match = False
                        break
                elif isinstance(v, dict) and "$ne" in v:
                    if d.get(k) == v["$ne"]:
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

    async def delete_one(self, q, session=None):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in q.items()):
                del self.docs[i]
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

    async def delete_many(self, q, session=None):
        q = q or {}
        before = len(self.docs)
        self.docs = [d for d in self.docs if not all(d.get(k) == v for k, v in q.items())]
        return type("R", (), {"deleted_count": before - len(self.docs)})()

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
    from fastapi import HTTPException
    db: Any = _DB()
    core.db.db = db
    utils.db = db
    routers.purchase_v2.db = db
    routers.ledger.db = db
    routers.debtors_creditors.db = db
    utils._txn_supported = False

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

    for mod in [routers.purchase_v2, routers.ledger, lp]:
        if hasattr(mod, "crud_create"):
            setattr(mod, "crud_create", mock_crud_create)
        if hasattr(mod, "crud_get"):
            setattr(mod, "crud_get", mock_crud_get)
        if hasattr(mod, "crud_update"):
            setattr(mod, "crud_update", mock_crud_update)
        if hasattr(mod, "crud_delete"):
            setattr(mod, "crud_delete", mock_crud_delete)

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


def test_posting_raises_without_chart_of_accounts():
    """A missing CoA is a tenant config error, not a legitimate no-op — the
    poster must raise so create_bill/update_bill surface it as a real error
    (409) instead of silently saving a bill with zero accounting effect."""
    from typing import Any
    db: Any = _DB()
    core.db.db = db
    utils.db = db
    asyncio.run(db.companies.insert_one({"id": "c1", "state_code": "27"}))
    try:
        asyncio.run(lp.post_purchase_bill_journal(
            db, bill_id="b1", bill_number="BILL-1", vendor_id=None, vendor_name="V",
            lines=LINES, user=USER))
        assert False, "expected ChartOfAccountsNotSeededError"
    except lp.ChartOfAccountsNotSeededError:
        pass


def test_posting_skips_when_bill_gross_is_zero():
    """gross<=0 IS a legitimate no-op (e.g. an all-free-sample bill) and must
    stay silent — distinct from the missing-CoA case above."""
    db = _setup()
    je = asyncio.run(lp.post_purchase_bill_journal(
        db, bill_id="b1", bill_number="BILL-1", vendor_id=None, vendor_name="V",
        lines=[{"stock_item_id": "i1", "qty": 0, "rate": 0, "gst_rate": 18}], user=USER))
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


def test_create_bill_without_grn_warns_no_stock_effect():
    """GRN owns stock movement, Bill owns accounting (by design — see
    purchase_v2's module docstring). A standalone bill (no linked GRN) posts
    accounting with ZERO stock-quantity effect anywhere — non-blocking, but
    the response must say so, since it's easy to mistake for goods actually
    being received."""
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))

    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill

    bill = asyncio.run(create_bill(PurchaseBill(
        vendor_invoice_no="INV-NOGRN", vendor_invoice_date="2026-06-01", vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)],
    ), user=USER))
    assert bill.get("stock_impact_warning")
    assert "GRN" in bill["stock_impact_warning"]


def test_create_bill_with_grn_has_no_stock_warning():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))
    asyncio.run(db.goods_receipt_notes_v2.insert_one({
        "id": "grn1", "vendor_id": "v1", "godown_id": "gd1", "lines": [],
    }))

    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill

    bill = asyncio.run(create_bill(PurchaseBill(
        vendor_invoice_no="INV-WITHGRN", vendor_invoice_date="2026-06-01", vendor_id="v1",
        grn_ids=["grn1"],
        lines=[BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)],
    ), user=USER))
    assert not bill.get("stock_impact_warning")


def test_create_bill_also_posts_to_debtors_creditors_module():
    """A posted Purchase Bill must show up in the Debtors & Creditors
    module's own Supplier Outstanding (/debtors-creditors/outstanding), not
    just /ledger/party-outstanding — previously the dc_ledger_entries/
    post_document hook existed but nothing ever called it, so a user on the
    D&C page never saw Purchase Bills at all."""
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))

    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill

    bill = asyncio.run(create_bill(PurchaseBill(
        vendor_invoice_no="INV-DC-1", vendor_invoice_date="2026-06-01", vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)],
    ), user=USER))

    dc_rows = [d for d in db.dc_ledger_entries.docs
               if d.get("source_doc_id") == bill["id"] and d.get("voucher_type") == "PURCHASE_BILL"]
    assert len(dc_rows) == 1
    assert dc_rows[0]["party_id"] == "v1"
    assert dc_rows[0]["party_type"] == "vendor"
    assert dc_rows[0]["credit"] == 1180.0  # PURCHASE_BILL credits the vendor (money owed)
    assert dc_rows[0]["debit"] == 0.0

    balances = [b for b in db.dc_party_balances.docs if b.get("party_id") == "v1"]
    assert len(balances) == 1
    assert balances[0]["total_credit"] == 1180.0
    assert balances[0]["outstanding"] == -1180.0  # negative = owed to the vendor

    # Re-posting the same bill id must not create a second dc_ledger_entries
    # row (idempotent, same as the journal poster).
    from routers.debtors_creditors import post_dc_document, DocPostIn
    asyncio.run(post_dc_document(
        DocPostIn(doc_type="PURCHASE_BILL", doc_id=bill["id"], party_type="vendor",
                  party_id="v1", entry_date="2026-06-01", amount=1180.0),
        tenant="default", created_by="u1",
    ))
    dc_rows_after = [d for d in db.dc_ledger_entries.docs
                     if d.get("source_doc_id") == bill["id"] and d.get("voucher_type") == "PURCHASE_BILL"]
    assert len(dc_rows_after) == 1


def test_update_bill_reprices_debtors_creditors_entry():
    """Editing a bill must re-price its dc_ledger_entries row too (not just
    the journal) — the old hard-reset-and-repost pattern used for
    journal_entries is mirrored for dc_ledger_entries."""
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))

    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill, update_bill

    bill = asyncio.run(create_bill(PurchaseBill(
        vendor_invoice_no="INV-DC-2", vendor_invoice_date="2026-06-01", vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)],
    ), user=USER))

    asyncio.run(update_bill(bill["id"], PurchaseBill(
        vendor_invoice_no="INV-DC-2", vendor_invoice_date="2026-06-01", vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=20, rate=100, gst_rate=18)],
    ), user=USER))

    dc_rows = [d for d in db.dc_ledger_entries.docs
               if d.get("source_doc_id") == bill["id"] and d.get("voucher_type") == "PURCHASE_BILL"]
    assert len(dc_rows) == 1  # old row replaced, not duplicated
    assert dc_rows[0]["credit"] == 2360.0  # 20 * 100 * 1.18


def test_delete_bill_removes_debtors_creditors_entry():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))

    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill, delete_bill

    bill = asyncio.run(create_bill(PurchaseBill(
        vendor_invoice_no="INV-DC-3", vendor_invoice_date="2026-06-01", vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)],
    ), user=USER))

    asyncio.run(delete_bill(bill["id"], user=USER))

    dc_rows = [d for d in db.dc_ledger_entries.docs if d.get("source_doc_id") == bill["id"]]
    assert dc_rows == []
    balances = [b for b in db.dc_party_balances.docs if b.get("party_id") == "v1"]
    assert balances[0]["outstanding"] == 0.0


def test_create_bill_endpoint_raises_409_without_chart_of_accounts():
    """End-to-end: POST /purchase/v2/bills must surface the missing-CoA case
    as a real 409, not silently save a bill with journal_entry_id=None."""
    from typing import Any
    from fastapi import HTTPException
    db: Any = _DB()
    core.db.db = db
    utils.db = db
    routers.purchase_v2.db = db
    utils._txn_supported = False

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

    for mod in [routers.purchase_v2]:
        setattr(mod, "crud_create", mock_crud_create)
        setattr(mod, "crud_get", mock_crud_get)

    asyncio.run(db.companies.insert_one({"id": "c1", "state_code": "27"}))
    asyncio.run(db.fiscal_years.insert_one({"id": "fy", "name": "2026-27", "is_active": True}))
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))
    # Deliberately no chart_of_accounts seeded.

    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill

    payload = PurchaseBill(
        vendor_invoice_no="INV-123", vendor_invoice_date="2026-06-01", vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)],
    )
    try:
        asyncio.run(create_bill(payload, user=USER))
        assert False, "expected HTTPException(409)"
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "Chart of Accounts" in exc.detail
    # No bill row was left behind uncommitted-but-visible in this fake DB —
    # in the real app the whole request rolls back on this exception since
    # crud_create's insert and the journal post share one session/transaction.


def test_update_bill_reposts_voucher():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))

    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill, update_bill

    bill = asyncio.run(create_bill(PurchaseBill(
        vendor_invoice_no="INV-1", vendor_invoice_date="2026-06-01", vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)],
    ), user=USER))
    old_je = bill["journal_entry_id"]
    assert old_je is not None
    assert bill["total"] == 1180.0

    # Edit: double the qty -> total doubles, old voucher reversed, new one posted.
    updated = asyncio.run(update_bill(bill["id"], PurchaseBill(
        vendor_invoice_no="INV-1", vendor_invoice_date="2026-06-01", vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=20, rate=100, gst_rate=18)],
    ), user=USER))
    assert updated["total"] == 2360.0
    assert updated["bill_number"] == bill["bill_number"]   # number preserved
    assert updated["journal_entry_id"] is not None
    # Exactly one live voucher for this bill (old reversed).
    jes = [j for j in db.journal_entries.docs if j.get("source_id") == bill["id"]]
    assert len(jes) == 1
    assert jes[0]["total_debit"] == 2360.0


def test_update_bill_blocked_after_payment():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))

    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill, update_bill, record_bill_payment
    from fastapi import HTTPException

    bill = asyncio.run(create_bill(PurchaseBill(
        vendor_invoice_no="INV-1", vendor_invoice_date="2026-06-01", vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)],
    ), user=USER))
    asyncio.run(record_bill_payment(bill_id=bill["id"], amount=500.0, user=USER))

    try:
        asyncio.run(update_bill(bill["id"], PurchaseBill(
            vendor_invoice_no="INV-1", vendor_invoice_date="2026-06-01", vendor_id="v1",
            lines=[BillLine(stock_item_id="i1", qty=20, rate=100, gst_rate=18)],
        ), user=USER))
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 400


def test_delete_bill_reverses_voucher():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))

    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill, delete_bill

    bill = asyncio.run(create_bill(PurchaseBill(
        vendor_invoice_no="INV-1", vendor_invoice_date="2026-06-01", vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)],
    ), user=USER))
    assert db.journal_entries.docs

    asyncio.run(delete_bill(bill["id"], user=USER))
    # Bill gone and its voucher reversed (no journal left for the source).
    assert asyncio.run(db.purchase_bills.find_one({"id": bill["id"]})) is None
    assert [j for j in db.journal_entries.docs if j.get("source_id") == bill["id"]] == []


def test_delete_bill_requires_admin():
    # delete_bill depends on require_admin; a non-admin user is rejected with 403.
    from core.auth_utils import require_admin
    from fastapi import HTTPException

    asyncio.run(require_admin(user={"id": "u2", "role": "admin"}))  # admin passes
    try:
        asyncio.run(require_admin(user={"id": "u3", "role": "accountant"}))
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 403


def test_delete_bill_blocked_after_payment():
    db = _setup()
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))

    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill, delete_bill, record_bill_payment
    from fastapi import HTTPException

    bill = asyncio.run(create_bill(PurchaseBill(
        vendor_invoice_no="INV-1", vendor_invoice_date="2026-06-01", vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)],
    ), user=USER))
    asyncio.run(record_bill_payment(bill_id=bill["id"], amount=500.0, user=USER))

    try:
        asyncio.run(delete_bill(bill["id"], user=USER))
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 400


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


def test_day_book_shows_backdated_bill_when_range_given():
    """A Purchase Bill posted today but dated in the past (the normal case —
    vendor invoices arrive after the fact) must appear in Day Book once the
    caller passes a date range covering the invoice date."""
    db = _setup()
    routers.accounting.db = db
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))

    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill
    from routers.accounting import day_book

    bill = asyncio.run(create_bill(PurchaseBill(
        vendor_invoice_no="INV-BACKDATED", vendor_invoice_date="2026-05-01", vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)],
    ), user=USER))
    assert bill["journal_entry_id"] is not None

    result = asyncio.run(day_book(from_date="2026-05-01", to_date="2026-05-01", user=USER))
    assert result["is_default_range"] is False
    assert result["applied_from"] == "2026-05-01"
    assert result["total_records"] > 0
    account_names = {row["account_name"] for row in result["entries"]}
    assert "Inventory" in account_names or "Accounts Payable" in account_names


def test_day_book_default_range_flags_itself_and_misses_backdated_bill():
    """Without an explicit range, Day Book defaults to today — the response
    must say so (is_default_range=True) rather than silently returning an
    empty/partial list with no explanation, and a bill dated in the past
    genuinely does NOT show up under that default (documents the actual
    behavior, not a change to it)."""
    db = _setup()
    routers.accounting.db = db
    asyncio.run(db.vendors.insert_one({"id": "v1", "name": "Vendor A", "state_code": "27"}))

    from core.purchase_models import PurchaseBill, BillLine
    from routers.purchase_v2 import create_bill
    from routers.accounting import day_book

    asyncio.run(create_bill(PurchaseBill(
        vendor_invoice_no="INV-OLD", vendor_invoice_date="2020-01-01", vendor_id="v1",
        lines=[BillLine(stock_item_id="i1", qty=10, rate=100, gst_rate=18)],
    ), user=USER))

    result = asyncio.run(day_book(user=USER))
    assert result["is_default_range"] is True
    assert result["applied_from"] == result["applied_to"] == date.today().isoformat()
    assert result["total_records"] == 0  # the 2020-01-01 bill is correctly absent under "today"

