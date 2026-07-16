"""Sales-side accounting: a customer credit note reverses the sale.

Drives core.ledger_posting.post_credit_note_journal against the in-memory async
Mongo fake reused from test_purchase_bill_posting. Proves:
  - the journal balances (debits == credits)
  - intra-state -> CGST+SGST debited, inter-state -> IGST debited
  - Sales Revenue + GST Payable are debited (reversed), Accounts Receivable credited
  - idempotency (same source_id posts once)
  - the create_credit_note endpoint posts only when the note is ISSUED
"""
import asyncio

import core.db
import core.utils as utils
import core.ledger_posting as lp
import routers.sales
from tests.test_purchase_bill_posting import _DB


def _setup(company_state="27"):
    from typing import Any
    db: Any = _DB()
    core.db.db = db
    utils.db = db
    routers.sales.db = db
    utils._txn_supported = False
    asyncio.run(db.companies.insert_one({"id": "c1", "state_code": company_state}))
    asyncio.run(db.fiscal_years.insert_one({"id": "fy", "name": "2026-27", "is_active": True}))
    for code, name in [("1100", "Accounts Receivable"), ("4001", "Sales Revenue"),
                       ("2003", "CGST Payable"), ("2004", "SGST Payable"),
                       ("2005", "IGST Payable")]:
        asyncio.run(db.chart_of_accounts.insert_one({"id": code, "code": code, "name": name}))
    return db


USER = {"id": "u1", "name": "T", "role": "admin"}
# 100 units @ 100 = 10,000 taxable; 18% GST = 1,800; gross = 11,800
ITEMS = [{"product_name": "Base jack", "quantity": 100, "unit_price": 100, "gst_rate": 18}]


def test_credit_note_journal_balanced_intrastate():
    db = _setup(company_state="27")
    asyncio.run(db.customers.insert_one({"id": "cust1", "state_code": "27"}))  # same state
    je = asyncio.run(lp.post_credit_note_journal(
        db, credit_note_id="cn1", credit_note_number="CN-1",
        customer_id="cust1", customer_name="Cust", items=ITEMS, user=USER,
    ))
    assert je is not None
    assert abs(je["total_debit"] - je["total_credit"]) < 0.01
    assert je["total_debit"] == 11800
    assert je["party_type"] == "CUSTOMER"
    assert je["cgst"] == 900 and je["sgst"] == 900 and je["igst"] == 0
    codes = {l["account_code"]: l for l in je["lines"]}
    # Reversal: Sales + GST Payable debited, Receivable credited.
    assert codes["4001"]["debit"] == 10000
    assert codes["2003"]["debit"] == 900
    assert codes["2004"]["debit"] == 900
    assert codes["1100"]["credit"] == 11800
    assert "CREDIT_NOTE" in je["tags"]


def test_credit_note_journal_interstate_uses_igst():
    db = _setup(company_state="27")
    asyncio.run(db.customers.insert_one({"id": "cust1", "state_code": "29"}))  # different state
    je = asyncio.run(lp.post_credit_note_journal(
        db, credit_note_id="cn1", credit_note_number="CN-1",
        customer_id="cust1", customer_name="Cust", items=ITEMS, user=USER,
    ))
    assert je is not None
    assert je["igst"] == 1800 and je["cgst"] == 0 and je["sgst"] == 0
    codes = {l["account_code"]: l for l in je["lines"]}
    assert codes["2005"]["debit"] == 1800
    assert "2003" not in codes and "2004" not in codes
    assert abs(je["total_debit"] - je["total_credit"]) < 0.01


def test_credit_note_posting_is_idempotent():
    db = _setup()
    asyncio.run(db.customers.insert_one({"id": "cust1", "state_code": "27"}))
    first = asyncio.run(lp.post_credit_note_journal(
        db, credit_note_id="cn1", credit_note_number="CN-1",
        customer_id="cust1", customer_name="Cust", items=ITEMS, user=USER))
    second = asyncio.run(lp.post_credit_note_journal(
        db, credit_note_id="cn1", credit_note_number="CN-1",
        customer_id="cust1", customer_name="Cust", items=ITEMS, user=USER))
    assert first is not None and second is not None
    assert first["id"] == second["id"]
    assert len(db.journal_entries.docs) == 1


def test_credit_note_skips_without_chart_of_accounts():
    from typing import Any
    db: Any = _DB()
    core.db.db = db
    utils.db = db
    asyncio.run(db.companies.insert_one({"id": "c1", "state_code": "27"}))
    # No chart_of_accounts seeded -> poster returns None, never crashes.
    je = asyncio.run(lp.post_credit_note_journal(
        db, credit_note_id="cn1", credit_note_number="CN-1",
        customer_id=None, customer_name="Cust", items=ITEMS, user=USER))
    assert je is None


def test_create_credit_note_endpoint_posts_only_when_issued():
    from core.models import CreditNote, SalesItem
    from routers.sales import create_credit_note

    # DRAFT: stored, totals computed, but NOT posted.
    db = _setup()
    asyncio.run(db.customers.insert_one({"id": "cust1", "name": "Cust A", "state_code": "27"}))
    draft = asyncio.run(create_credit_note(CreditNote(
        customer_id="cust1", status="DRAFT",
        items=[SalesItem(product_id="p", product_name="Base jack", sku="BJ", quantity=10, unit_price=100, gst_rate=18)],
    ), user=USER))
    assert draft["total"] == 1180.0
    assert draft.get("journal_entry_id") is None
    assert len(db.journal_entries.docs) == 0

    # ISSUED: stored AND posted.
    db = _setup()
    asyncio.run(db.customers.insert_one({"id": "cust1", "name": "Cust A", "state_code": "27"}))
    issued = asyncio.run(create_credit_note(CreditNote(
        customer_id="cust1", status="ISSUED",
        items=[SalesItem(product_id="p", product_name="Base jack", sku="BJ", quantity=10, unit_price=100, gst_rate=18)],
    ), user=USER))
    assert issued["total"] == 1180.0
    assert issued.get("journal_entry_id") is not None
    assert len(db.journal_entries.docs) == 1
