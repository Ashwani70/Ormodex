"""Reusable double-entry posting for the purchase side of the ledger.

Receiving goods (PO receive / GRN) moves stock but historically never touched the
ledger, so Trial Balance, Inventory (asset) and Accounts Payable were blind to
purchases. This module posts a balanced, POSTED journal entry for a goods receipt:

    Dr 1200 Inventory               (taxable value)
    Dr 1500 GST Input Tax Credit    (CGST+SGST or IGST)
        Cr 2001 Accounts Payable    (grand total)

It is idempotent on (source_collection, source_id) so PO-receive and GRN — which
share the PO id — cannot double-post, and a re-run is a no-op.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Optional

# Chart-of-Accounts codes (seeded by /accounting/seed-coa).
ACC_INVENTORY = "1200"
ACC_GST_ITC = "1500"
ACC_ACCOUNTS_PAYABLE = "2001"
ACC_TDS_PAYABLE = "2006"


class ChartOfAccountsNotSeededError(Exception):
    """Raised when a poster needs a Chart of Accounts code that doesn't exist
    yet. Only used where silently skipping would leave the document's one
    purpose (posting accounting) silently unfulfilled — see
    post_purchase_bill_journal. GRN's post_purchase_journal deliberately does
    NOT raise this: goods receipt's job is moving stock, and that must not be
    blocked by an accounting setup gap, so it keeps returning None there."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _account_name(db, code: str, fallback: str) -> str:
    acc = await db.chart_of_accounts.find_one({"code": code}, {"_id": 0, "name": 1})
    return acc["name"] if acc else fallback


async def _next_entry_number(db, fiscal_year: str) -> str:
    count = await db.journal_entries.count_documents({"fiscal_year": fiscal_year})
    return f"JE/{fiscal_year}/{str(count + 1).zfill(5)}"


def _split_gst(gst_amount: float, interstate: bool) -> dict:
    """Split GST into CGST/SGST (intra-state) or IGST (inter-state)."""
    if interstate:
        return {"cgst": 0.0, "sgst": 0.0, "igst": round(gst_amount, 2)}
    half = round(gst_amount / 2, 2)
    return {"cgst": half, "sgst": round(gst_amount - half, 2), "igst": 0.0}


async def _is_interstate(db, supplier_id: Optional[str]) -> bool:
    """Place-of-supply: inter-state when the vendor's state differs from the tenant's."""
    supplier = None
    if supplier_id:
        supplier = await db.suppliers.find_one({"id": supplier_id}, {"_id": 0, "state_code": 1}) \
            or await db.vendors.find_one({"id": supplier_id}, {"_id": 0, "state_code": 1})
    company = await db.companies.find_one({}, {"_id": 0, "state_code": 1})
    company_state = (company or {}).get("state_code") or "27"  # matches /company/active default
    supplier_state = (supplier or {}).get("state_code")
    return bool(supplier_state and str(supplier_state) != str(company_state))


async def _persist_journal(db, *, source_collection, source_id, source_number, narration,
                           lines, party_id, party_name, gst, taxable,
                           entry_date, user, tags, party_type="SUPPLIER") -> dict:
    """Persist a balanced, POSTED journal entry and audit it. Shared by all posters."""
    fy = await db.fiscal_years.find_one({"is_active": True})
    fy_name = fy["name"] if fy else date.today().strftime("%Y-%y")
    total_debit = round(sum(l["debit"] for l in lines), 2)
    total_credit = round(sum(l["credit"] for l in lines), 2)

    entry = {
        "id": str(uuid.uuid4()),
        "entry_number": await _next_entry_number(db, fy_name),
        "date": entry_date or date.today().isoformat(),
        "narration": narration,
        "lines": lines,
        "status": "POSTED",
        "fiscal_year": fy_name,
        "reference": source_number,
        "tags": tags,
        "source_collection": source_collection,
        "source_id": source_id,
        "party_type": party_type,
        "party_id": party_id,
        "party_name": party_name,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "cgst": gst["cgst"],
        "sgst": gst["sgst"],
        "igst": gst["igst"],
        "taxable_amount": taxable,
        "created_by": (user or {}).get("id", "system"),
        "created_by_name": (user or {}).get("name", "System"),
        "created_at": _now_iso(),
    }
    await db.journal_entries.insert_one(entry)
    entry.pop("_id", None)
    from .utils import log_audit
    await log_audit("CREATE", "journal_entries", str(entry["id"]), user, new_values=entry)
    return entry


async def post_purchase_journal(
    db,
    *,
    source_collection: str,
    source_id: str,
    source_number: str,
    supplier_id: Optional[str],
    supplier_name: str,
    items: list,
    user: Optional[dict] = None,
    entry_date: Optional[str] = None,
    qty_field: str = "quantity",
) -> Optional[dict]:
    """Create (once) a POSTED purchase journal entry for a goods receipt.

    `items` are PO/GRN line dicts with quantity, unit_price/unit_cost and gst_rate.
    Returns the journal entry, the pre-existing one if already posted, or None when
    the Chart of Accounts has not been seeded (so goods receipt never breaks).
    """
    # Idempotency: at most one JE per source document (PO id).
    existing = await db.journal_entries.find_one(
        {"source_collection": source_collection, "source_id": source_id},
        {"_id": 0},
    )
    if existing:
        return existing

    # Need the payable + inventory accounts to exist before we can post.
    if not await db.chart_of_accounts.find_one({"code": ACC_ACCOUNTS_PAYABLE}):
        return None

    # Determine intra- vs inter-state from company state vs supplier state.
    interstate = False
    supplier = None
    if supplier_id:
        supplier = await db.suppliers.find_one(
            {"id": supplier_id}, {"_id": 0, "state_code": 1}
        )
    company = await db.companies.find_one({}, {"_id": 0, "state_code": 1})
    company_state = (company or {}).get("state_code") or "27"  # matches /company/active default
    supplier_state = (supplier or {}).get("state_code")
    if supplier_state and str(supplier_state) != str(company_state):
        interstate = True

    # Totals from line items.
    taxable = 0.0
    gst_amount = 0.0
    for it in items or []:
        qty = float(it.get(qty_field, it.get("quantity", 0)) or 0)
        price = float(it.get("unit_price", it.get("unit_cost", 0)) or 0)
        line = qty * price
        taxable += line
        gst_amount += line * float(it.get("gst_rate", 0) or 0) / 100.0

    taxable = round(taxable, 2)
    gst_amount = round(gst_amount, 2)
    grand_total = round(taxable + gst_amount, 2)
    if grand_total <= 0:
        return None

    gst = _split_gst(gst_amount, interstate)

    narration = f"Goods received against {source_number} from {supplier_name}"

    lines = [
        {
            "account_code": ACC_INVENTORY,
            "account_name": await _account_name(db, ACC_INVENTORY, "Inventory"),
            "debit": taxable,
            "credit": 0.0,
            "narration": narration,
        }
    ]
    if gst_amount > 0:
        lines.append({
            "account_code": ACC_GST_ITC,
            "account_name": await _account_name(db, ACC_GST_ITC, "GST Input Tax Credit"),
            "debit": gst_amount,
            "credit": 0.0,
            "narration": f"ITC ({'IGST' if interstate else 'CGST+SGST'}) on {source_number}",
        })
    lines.append({
        "account_code": ACC_ACCOUNTS_PAYABLE,
        "account_name": await _account_name(db, ACC_ACCOUNTS_PAYABLE, "Accounts Payable"),
        "debit": 0.0,
        "credit": grand_total,
        "narration": narration,
    })

    fy = await db.fiscal_years.find_one({"is_active": True})
    fy_name = fy["name"] if fy else date.today().strftime("%Y-%y")

    entry = {
        "id": str(uuid.uuid4()),
        "entry_number": await _next_entry_number(db, fy_name),
        "date": entry_date or date.today().isoformat(),
        "narration": narration,
        "lines": lines,
        "status": "POSTED",
        "fiscal_year": fy_name,
        "reference": source_number,
        "tags": ["AUTO", "PURCHASE"],
        # Traceability + idempotency key.
        "source_collection": source_collection,
        "source_id": source_id,
        "party_type": "SUPPLIER",
        "party_id": supplier_id,
        "party_name": supplier_name,
        "total_debit": grand_total,
        "total_credit": grand_total,
        "cgst": gst["cgst"],
        "sgst": gst["sgst"],
        "igst": gst["igst"],
        "taxable_amount": taxable,
        "created_by": (user or {}).get("id", "system"),
        "created_by_name": (user or {}).get("name", "System"),
        "created_at": _now_iso(),
    }

    await db.journal_entries.insert_one(entry)
    entry.pop("_id", None)

    # Auto-created journal entries are accounting records too — audit them.
    from .utils import log_audit
    await log_audit("CREATE", "journal_entries", str(entry["id"]), user, new_values=entry)

    return entry


def _sum_lines(lines: list, qty_field: str = "qty", rate_field: str = "rate") -> tuple[float, float]:
    """Return (taxable, gst_amount) from purchase lines."""
    taxable = 0.0
    gst_amount = 0.0
    for it in lines or []:
        qty = float(it.get(qty_field, 0) or 0)
        rate = float(it.get(rate_field, 0) or 0)
        line = qty * rate
        taxable += line
        gst_amount += line * float(it.get("gst_rate", 0) or 0) / 100.0
    return round(taxable, 2), round(gst_amount, 2)


async def post_purchase_bill_journal(
    db,
    *,
    bill_id: str,
    bill_number: str,
    vendor_id: Optional[str],
    vendor_name: str,
    lines: list,
    tds_rate: float = 0.0,
    user: Optional[dict] = None,
    entry_date: Optional[str] = None,
) -> Optional[dict]:
    """Post the accounting voucher for a vendor invoice (idempotent on the bill id):

        Dr 1200 Inventory            (taxable)
        Dr 1500 GST Input Tax Credit (CGST+SGST or IGST)
            Cr 2006 TDS Payable      (tds_rate % of taxable, if any)
            Cr 2001 Accounts Payable (balancing — net due to vendor)
    """
    existing = await db.journal_entries.find_one(
        {"source_collection": "purchase_bills", "source_id": bill_id}, {"_id": 0}
    )
    if existing:
        return existing
    if not await db.chart_of_accounts.find_one({"code": ACC_ACCOUNTS_PAYABLE}):
        # A missing Chart of Accounts is a tenant configuration error, not a
        # legitimate "nothing to post" case (unlike gross<=0 below) — it must
        # never be silently swallowed. Previously this returned None here,
        # which the caller (purchase_v2.create_bill) treated identically to
        # success: the bill saved with journal_entry_id=None and HTTP 200,
        # with no error surfaced anywhere. That let an entire tenant's
        # Purchase Bills post with zero accounting effect (invisible to Day
        # Book, Ledger, Trial Balance) until someone happened to notice.
        raise ChartOfAccountsNotSeededError(
            "Chart of Accounts is not set up — run Accounting → Seed Chart of "
            "Accounts before posting Purchase Bills, or this bill's accounting "
            "entries will never be created."
        )

    interstate = await _is_interstate(db, vendor_id)
    taxable, gst_amount = _sum_lines(lines)
    gross = round(taxable + gst_amount, 2)
    if gross <= 0:
        return None
    tds = round(taxable * float(tds_rate or 0) / 100.0, 2)
    payable = round(gross - tds, 2)
    gst = _split_gst(gst_amount, interstate)
    narration = f"Purchase bill {bill_number} from {vendor_name}"

    je_lines = [{
        "account_code": ACC_INVENTORY,
        "account_name": await _account_name(db, ACC_INVENTORY, "Inventory"),
        "debit": taxable, "credit": 0.0, "narration": narration,
    }]
    if gst_amount > 0:
        je_lines.append({
            "account_code": ACC_GST_ITC,
            "account_name": await _account_name(db, ACC_GST_ITC, "GST Input Tax Credit"),
            "debit": gst_amount, "credit": 0.0,
            "narration": f"ITC ({'IGST' if interstate else 'CGST+SGST'}) on {bill_number}",
        })
    if tds > 0:
        je_lines.append({
            "account_code": ACC_TDS_PAYABLE,
            "account_name": await _account_name(db, ACC_TDS_PAYABLE, "TDS Payable"),
            "debit": 0.0, "credit": tds, "narration": f"TDS @ {tds_rate}% on {bill_number}",
        })
    je_lines.append({
        "account_code": ACC_ACCOUNTS_PAYABLE,
        "account_name": await _account_name(db, ACC_ACCOUNTS_PAYABLE, "Accounts Payable"),
        "debit": 0.0, "credit": payable, "narration": narration,
    })

    return await _persist_journal(
        db, source_collection="purchase_bills", source_id=bill_id,
        source_number=bill_number, narration=narration, lines=je_lines,
        party_id=vendor_id, party_name=vendor_name, gst=gst,
        taxable=taxable, entry_date=entry_date, user=user,
        tags=["AUTO", "PURCHASE", "BILL"],
        party_type="SUPPLIER",
    )


async def post_purchase_return_journal(
    db,
    *,
    return_id: str,
    return_number: str,
    vendor_id: Optional[str],
    vendor_name: str,
    lines: list,
    user: Optional[dict] = None,
    entry_date: Optional[str] = None,
) -> Optional[dict]:
    """Reverse a purchase for a debit note / return (idempotent on the return id):

        Dr 2001 Accounts Payable     (gross — reduce what we owe the vendor)
            Cr 1200 Inventory        (taxable — goods going back)
            Cr 1500 GST Input Tax Credit (reverse the ITC claimed)
    """
    existing = await db.journal_entries.find_one(
        {"source_collection": "purchase_returns", "source_id": return_id}, {"_id": 0}
    )
    if existing:
        return existing
    if not await db.chart_of_accounts.find_one({"code": ACC_ACCOUNTS_PAYABLE}):
        return None

    interstate = await _is_interstate(db, vendor_id)
    taxable, gst_amount = _sum_lines(lines)
    gross = round(taxable + gst_amount, 2)
    if gross <= 0:
        return None
    gst = _split_gst(gst_amount, interstate)
    narration = f"Purchase return {return_number} to {vendor_name}"

    je_lines = [{
        "account_code": ACC_ACCOUNTS_PAYABLE,
        "account_name": await _account_name(db, ACC_ACCOUNTS_PAYABLE, "Accounts Payable"),
        "debit": gross, "credit": 0.0, "narration": narration,
    }, {
        "account_code": ACC_INVENTORY,
        "account_name": await _account_name(db, ACC_INVENTORY, "Inventory"),
        "debit": 0.0, "credit": taxable, "narration": narration,
    }]
    if gst_amount > 0:
        je_lines.append({
            "account_code": ACC_GST_ITC,
            "account_name": await _account_name(db, ACC_GST_ITC, "GST Input Tax Credit"),
            "debit": 0.0, "credit": gst_amount,
            "narration": f"ITC reversal ({'IGST' if interstate else 'CGST+SGST'}) on {return_number}",
        })

    return await _persist_journal(
        db, source_collection="purchase_returns", source_id=return_id,
        source_number=return_number, narration=narration, lines=je_lines,
        party_id=vendor_id, party_name=vendor_name, gst=gst,
        taxable=taxable, entry_date=entry_date, user=user,
        tags=["AUTO", "PURCHASE", "RETURN"],
        party_type="SUPPLIER",
    )


ACC_ACCOUNTS_RECEIVABLE = "1100"
ACC_SALES_REVENUE = "4001"
ACC_CGST_PAYABLE = "2003"
ACC_SGST_PAYABLE = "2004"
ACC_IGST_PAYABLE = "2005"


async def post_credit_note_journal(
    db,
    *,
    credit_note_id: str,
    credit_note_number: str,
    customer_id: Optional[str],
    customer_name: str,
    items: list,
    user: Optional[dict] = None,
    entry_date: Optional[str] = None,
) -> Optional[dict]:
    """Reverses sales revenue and GST payable, credits accounts receivable."""
    existing = await db.journal_entries.find_one(
        {"source_collection": "credit_notes", "source_id": credit_note_id}, {"_id": 0}
    )
    if existing:
        return existing

    if not await db.chart_of_accounts.find_one({"code": ACC_ACCOUNTS_RECEIVABLE}):
        return None

    # Determine intra- vs inter-state
    interstate = False
    customer = None
    if customer_id:
        customer = await db.customers.find_one({"id": customer_id}, {"_id": 0, "state_code": 1})
    company = await db.companies.find_one({}, {"_id": 0, "state_code": 1})
    company_state = (company or {}).get("state_code") or "27"
    customer_state = (customer or {}).get("state_code")
    if customer_state and str(customer_state) != str(company_state):
        interstate = True

    # Totals from line items
    taxable = 0.0
    gst_amount = 0.0
    for it in items or []:
        qty = float(it.get("quantity", 0) or 0)
        price = float(it.get("unit_price", 0) or 0)
        line = qty * price
        taxable += line
        gst_amount += line * float(it.get("gst_rate", 0) or 0) / 100.0

    taxable = round(taxable, 2)
    gst_amount = round(gst_amount, 2)
    gross = round(taxable + gst_amount, 2)
    if gross <= 0:
        return None

    gst = _split_gst(gst_amount, interstate)
    narration = f"Credit note {credit_note_number} for {customer_name}"

    je_lines = [{
        "account_code": ACC_SALES_REVENUE,
        "account_name": await _account_name(db, ACC_SALES_REVENUE, "Sales Revenue"),
        "debit": taxable, "credit": 0.0, "narration": narration,
    }]
    if gst_amount > 0:
        if interstate:
            je_lines.append({
                "account_code": ACC_IGST_PAYABLE,
                "account_name": await _account_name(db, ACC_IGST_PAYABLE, "IGST Payable"),
                "debit": gst_amount, "credit": 0.0,
                "narration": f"IGST reversal on {credit_note_number}",
            })
        else:
            cgst = gst["cgst"]
            sgst = gst["sgst"]
            if cgst > 0:
                je_lines.append({
                    "account_code": ACC_CGST_PAYABLE,
                    "account_name": await _account_name(db, ACC_CGST_PAYABLE, "CGST Payable"),
                    "debit": cgst, "credit": 0.0,
                    "narration": f"CGST reversal on {credit_note_number}",
                })
            if sgst > 0:
                je_lines.append({
                    "account_code": ACC_SGST_PAYABLE,
                    "account_name": await _account_name(db, ACC_SGST_PAYABLE, "SGST Payable"),
                    "debit": sgst, "credit": 0.0,
                    "narration": f"SGST reversal on {credit_note_number}",
                })
    je_lines.append({
        "account_code": ACC_ACCOUNTS_RECEIVABLE,
        "account_name": await _account_name(db, ACC_ACCOUNTS_RECEIVABLE, "Accounts Receivable"),
        "debit": 0.0, "credit": gross, "narration": narration,
    })

    return await _persist_journal(
        db, source_collection="credit_notes", source_id=credit_note_id,
        source_number=credit_note_number, narration=narration, lines=je_lines,
        party_id=customer_id, party_name=customer_name, gst=gst,
        taxable=taxable, entry_date=entry_date, user=user,
        tags=["AUTO", "SALES", "CREDIT_NOTE"],
        party_type="CUSTOMER",
    )

