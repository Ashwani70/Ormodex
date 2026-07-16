"""Banking Module D extensions.

Adds on top of the existing banking.py:
- PDC (Post-Dated Cheque) register: issued / received, full lifecycle
    pending → presented → cleared / bounced
    PDC parked in PDC control ledger; only moves to bank on clearing
- Cheque printing with Indian amount-in-words (lakh/crore)
- Bank feed import + auto-reconciliation (MongoDB aggregation match)
- Overdue interest (simple / compound, configurable grace days per interest_rule)

Collections:
  pdcs, cheque_formats, bank_feed_imports, bank_statement_lines, interest_rules
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Literal
from pydantic import BaseModel
from datetime import date, timedelta

from core.auth_utils import get_current_user, require_admin, is_admin_role
from core.db import db
from core.utils import now_iso, new_id, next_doc_number, crud_create, crud_list, crud_get, crud_update

router = APIRouter(prefix="/banking-pdc", tags=["Banking PDC"])


def _require_banking(user: dict):
    if (is_admin_role(user.get("role")) or user.get("role") == "accountant"):
        return user
    if "banking" in user.get("module_permissions", []):
        return user
    raise HTTPException(403, "Banking module access required")


# ══════════════════════════════════════════════════════════════
# Indian amount-in-words
# ══════════════════════════════════════════════════════════════

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
         "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
         "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two_digits(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _three_digits(n: int) -> str:
    if n >= 100:
        return _ONES[n // 100] + " Hundred" + (" " + _two_digits(n % 100) if n % 100 else "")
    return _two_digits(n)


def amount_in_words(amount: float) -> str:
    """
    Convert a rupee amount to Indian English words.
    e.g. 12_34_567.50 → "Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven Rupees and Fifty Paise Only"
    """
    amount = round(amount, 2)
    rupees = int(amount)
    paise = round((amount - rupees) * 100)

    if rupees == 0 and paise == 0:
        return "Zero Rupees Only"

    def _rupee_words(n: int) -> str:
        if n == 0:
            return ""
        parts = []
        crore = n // 10_000_000
        n %= 10_000_000
        lakh = n // 100_000
        n %= 100_000
        thousand = n // 1_000
        n %= 1_000
        hundred_part = n

        if crore:
            parts.append(_three_digits(crore) + " Crore")
        if lakh:
            parts.append(_two_digits(lakh) + " Lakh")
        if thousand:
            parts.append(_two_digits(thousand) + " Thousand")
        if hundred_part:
            parts.append(_three_digits(hundred_part))
        return " ".join(parts)

    words = _rupee_words(rupees)
    result = (words + " Rupees").strip()
    if paise:
        result += " and " + _two_digits(paise) + " Paise"
    return result + " Only"


# ══════════════════════════════════════════════════════════════
# Pydantic models
# ══════════════════════════════════════════════════════════════

class PDCModel(BaseModel):
    type: Literal["issued", "received"]
    party_id: str
    party_name: Optional[str] = None
    cheque_no: str
    bank_name: str
    amount: float
    instrument_date: str         # the date on the cheque (post-dated)
    bank_account_id: Optional[str] = None
    linked_voucher_id: Optional[str] = None
    notes: Optional[str] = None


class ClearBounceRequest(BaseModel):
    action_date: str
    bank_account_id: Optional[str] = None
    bounce_charges: float = 0.0
    notes: Optional[str] = None


class ChequePrintRequest(BaseModel):
    pdc_id: Optional[str] = None
    payee_name: str
    amount: float
    amount_date: str
    format_id: str


class ChequePrintFormat(BaseModel):
    name: str
    bank_name: str
    fields: list    # [{"field": "payee", "x": 120, "y": 45, "font_size": 12, ...}]
    micr_line: Optional[str] = None


class BankFeedImportRequest(BaseModel):
    bank_account_id: str
    file_format: Literal["csv", "ofx", "mt940"] = "csv"


class BankStatementLine(BaseModel):
    bank_account_id: str
    txn_date: str
    narration: str
    debit: float = 0.0
    credit: float = 0.0
    reference: Optional[str] = None
    balance: Optional[float] = None


class InterestRule(BaseModel):
    name: str
    party_id: Optional[str] = None   # None = global default
    rate_pct_pa: float
    grace_days: int = 0
    basis: Literal["simple", "compound"] = "simple"
    min_amount: float = 0.0          # minimum invoice amount to trigger interest


class InterestRunRequest(BaseModel):
    as_of_date: str
    rule_id: Optional[str] = None
    party_id: Optional[str] = None
    create_debit_notes: bool = False


# ══════════════════════════════════════════════════════════════
# PDC Register
# ══════════════════════════════════════════════════════════════

@router.get("/pdc")
async def list_pdcs(
    pdc_type: Optional[str] = None,
    status: Optional[str] = None,
    party_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require_banking(user)
    filt: dict = {}
    if pdc_type:
        filt["type"] = pdc_type
    if status:
        filt["status"] = status
    if party_id:
        filt["party_id"] = party_id
    return await crud_list("pdcs", filt=filt, sort_field="instrument_date")


@router.post("/pdc")
async def create_pdc(payload: PDCModel, user: dict = Depends(get_current_user)):
    _require_banking(user)
    doc = payload.model_dump()
    doc["pdc_no"] = await next_doc_number("PDC", "pdcs")
    doc["status"] = "PENDING"
    doc["is_overdue"] = False
    return await crud_create("pdcs", doc, user)


@router.get("/pdc/maturing")
async def pdcs_maturing(
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    user: dict = Depends(get_current_user),
):
    """PDCs maturing (instrument_date) between from_date and to_date — for alert/dashboard."""
    _require_banking(user)
    pdcs = await db.pdcs.find(
        {"status": "PENDING", "instrument_date": {"$gte": from_date, "$lte": to_date}},
        {"_id": 0},
    ).sort("instrument_date", 1).to_list(1000)
    today = date.today().isoformat()
    for p in pdcs:
        p["days_to_maturity"] = (
            date.fromisoformat(p["instrument_date"]) - date.today()
        ).days
        p["is_overdue"] = p["instrument_date"] < today
    return pdcs


@router.post("/pdc/{pdc_id}/present")
async def present_pdc(pdc_id: str, user: dict = Depends(get_current_user)):
    """Mark PDC as presented to bank (not yet cleared)."""
    _require_banking(user)
    pdc = await crud_get("pdcs", pdc_id)
    if pdc["status"] != "PENDING":
        raise HTTPException(400, f"PDC is in status '{pdc['status']}', expected PENDING")
    return await crud_update("pdcs", pdc_id, {"status": "PRESENTED", "presented_at": now_iso()}, user)


@router.post("/pdc/{pdc_id}/clear")
async def clear_pdc(
    pdc_id: str,
    payload: ClearBounceRequest,
    user: dict = Depends(get_current_user),
):
    """
    Clear a PDC.
    - PDC control ledger entry is reversed.
    - Bank account ledger is debited/credited.
    - Status → CLEARED.
    """
    _require_banking(user)
    pdc = await crud_get("pdcs", pdc_id)
    if pdc["status"] not in ("PENDING", "PRESENTED"):
        raise HTTPException(400, f"Cannot clear PDC in status '{pdc['status']}'")

    result = await crud_update("pdcs", pdc_id, {
        "status": "CLEARED",
        "cleared_at": payload.action_date,
        "cleared_bank_account_id": payload.bank_account_id,
        "clearing_notes": payload.notes,
    }, user)

    # Accounting entry (stub — real implementation wires to accounting router)
    journal_note = f"PDC {pdc.get('pdc_no', pdc_id)} cleared — {pdc['type']} cheque no {pdc['cheque_no']}"
    return {
        "pdc": result,
        "accounting": {
            "action": "PDC_CLEARED",
            "debit": "Bank Account" if pdc["type"] == "received" else "PDC Control (Issued)",
            "credit": "PDC Control (Received)" if pdc["type"] == "received" else "Bank Account",
            "amount": pdc["amount"],
            "narration": journal_note,
        },
    }


@router.post("/pdc/{pdc_id}/bounce")
async def bounce_pdc(
    pdc_id: str,
    payload: ClearBounceRequest,
    user: dict = Depends(get_current_user),
):
    """
    Bounce a PDC.
    - Reversal journal entry.
    - Optional bounce charges debited to party.
    - Status → BOUNCED.
    """
    _require_banking(user)
    pdc = await crud_get("pdcs", pdc_id)
    if pdc["status"] not in ("PENDING", "PRESENTED"):
        raise HTTPException(400, f"Cannot bounce PDC in status '{pdc['status']}'")

    result = await crud_update("pdcs", pdc_id, {
        "status": "BOUNCED",
        "bounced_at": payload.action_date,
        "bounce_charges": payload.bounce_charges,
        "bounce_notes": payload.notes,
    }, user)

    return {
        "pdc": result,
        "accounting": {
            "action": "PDC_BOUNCED",
            "reversal": True,
            "bounce_charges": payload.bounce_charges,
            "narration": f"PDC {pdc.get('pdc_no', pdc_id)} bounced — cheque no {pdc['cheque_no']}",
        },
    }


# ══════════════════════════════════════════════════════════════
# Cheque Printing
# ══════════════════════════════════════════════════════════════

@router.get("/cheque-formats")
async def list_cheque_formats(user: dict = Depends(get_current_user)):
    _require_banking(user)
    return await crud_list("cheque_formats", sort_field="name")


@router.post("/cheque-formats")
async def create_cheque_format(payload: ChequePrintFormat, user: dict = Depends(require_admin)):
    return await crud_create("cheque_formats", payload.model_dump(), user)


async def _render_cheque(payload: ChequePrintRequest) -> dict:
    """Resolve a cheque format + field values for a print request.

    Shared by the JSON preview endpoint and the PDF endpoint so on-screen
    preview, browser print, and archived PDF all render identically.
    """
    fmt = await db.cheque_formats.find_one({"id": payload.format_id}, {"_id": 0})
    if not fmt:
        raise HTTPException(404, f"Cheque format '{payload.format_id}' not found")

    words = amount_in_words(payload.amount)

    field_values = {
        "payee": payload.payee_name,
        "amount_numeric": f"{payload.amount:,.2f}",
        "amount_words": words,
        "date": payload.amount_date,
    }

    # If linked to a PDC, also fetch additional context.
    pdc_context = None
    if payload.pdc_id:
        pdc = await db.pdcs.find_one({"id": payload.pdc_id}, {"_id": 0})
        if pdc:
            pdc_context = {"cheque_no": pdc.get("cheque_no"), "party_id": pdc.get("party_id")}

    rendered_fields = [
        {**field_def, "value": field_values.get(field_def.get("field", ""), "")}
        for field_def in fmt.get("fields", [])
    ]

    return {
        "format": fmt.get("name"),
        "bank_name": fmt.get("bank_name"),
        "fields": rendered_fields,
        "amount_words": words,
        "micr_line": fmt.get("micr_line"),
        "pdc_context": pdc_context,
    }


@router.post("/cheques/print")
async def print_cheque(payload: ChequePrintRequest, user: dict = Depends(get_current_user)):
    """
    Render cheque print data.
    Returns field coordinates + values (including Indian amount-in-words).
    The frontend uses these coordinates for the on-screen preview and browser
    print; /cheques/pdf renders the same data to an archivable PDF.
    """
    _require_banking(user)
    return await _render_cheque(payload)


@router.post("/cheques/pdf")
async def cheque_pdf(payload: ChequePrintRequest, user: dict = Depends(get_current_user)):
    """Render the cheque to a print-ready PDF sized to a real cheque leaf.

    The fields are positioned from the same format coordinates the preview uses,
    so the archived PDF matches what prints on the physical cheque."""
    _require_banking(user)
    from fastapi import Response
    from core.cheque_pdf import build_cheque_pdf

    rendered = await _render_cheque(payload)
    pdf_bytes = build_cheque_pdf(rendered)
    safe_payee = "".join(c for c in (payload.payee_name or "cheque") if c.isalnum() or c in " -_").strip() or "cheque"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="cheque-{safe_payee}.pdf"'},
    )


# ══════════════════════════════════════════════════════════════
# Bank Feed Import & Reconciliation
# ══════════════════════════════════════════════════════════════

@router.post("/bank-feeds/import")
async def import_bank_feed(
    bank_account_id: str,
    lines: list[BankStatementLine],
    user: dict = Depends(get_current_user),
):
    """Import parsed bank statement lines. Caller parses CSV/OFX/MT940 and POSTs structured lines."""
    _require_banking(user)
    if not lines:
        raise HTTPException(400, "No lines provided")

    import_doc = {
        "bank_account_id": bank_account_id,
        "imported_at": now_iso(),
        "line_count": len(lines),
    }
    feed_doc = await crud_create("bank_feed_imports", import_doc, user)
    feed_id = feed_doc["id"]

    line_docs = []
    for line in lines:
        line_docs.append({
            "id": new_id(),
            "feed_id": feed_id,
            "bank_account_id": bank_account_id,
            "txn_date": line.txn_date,
            "narration": line.narration,
            "debit": line.debit,
            "credit": line.credit,
            "reference": line.reference,
            "balance": line.balance,
            "match_status": "UNMATCHED",
            "created_at": now_iso(),
        })
    if line_docs:
        await db.bank_statement_lines.insert_many(line_docs)

    return {"feed_id": feed_id, "lines_imported": len(line_docs)}


@router.post("/bank-recon/match")
async def auto_match_bank_recon(
    bank_account_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Auto-match bank statement lines against PDC payments and vouchers.
    Strategy: match by (amount OR reference) within ±3 day window.
    Uses aggregation pipeline for bulk matching.
    Returns matched pairs + unmatched lines on both sides.
    """
    _require_banking(user)

    # Unmatched statement lines
    stmt_lines = await db.bank_statement_lines.find(
        {"bank_account_id": bank_account_id, "match_status": "UNMATCHED"},
        {"_id": 0},
    ).to_list(5000)

    # Cleared PDCs for this account
    cleared_pdcs = await db.pdcs.find(
        {"cleared_bank_account_id": bank_account_id, "status": "CLEARED"},
        {"_id": 0},
    ).to_list(5000)

    matched = []
    unmatched_stmt = []
    pdc_matched_ids = set()
    updates_by_id: dict = {}

    for line in stmt_lines:
        line_amount = line.get("credit", 0) or line.get("debit", 0)
        line_date = date.fromisoformat(line["txn_date"])
        best_match = None

        for pdc in cleared_pdcs:
            if pdc["id"] in pdc_matched_ids:
                continue
            if abs(pdc["amount"] - line_amount) < 0.01:
                pdc_date_raw = pdc.get("cleared_at") or pdc.get("instrument_date") or "2000-01-01"
                pdc_date = date.fromisoformat(pdc_date_raw[:10])
                if abs((line_date - pdc_date).days) <= 3:
                    best_match = pdc
                    break

        if best_match:
            matched.append({"statement_line": line, "matched_pdc": best_match})
            pdc_matched_ids.add(best_match["id"])
            updates_by_id[line["id"]] = {"$set": {"match_status": "MATCHED", "matched_pdc_id": best_match["id"]}}
        else:
            unmatched_stmt.append(line)

    # Matching above is pure in-memory work; the writes it decided on are
    # applied in ONE bulk_update_by_id call instead of an update_one per
    # match inside the loop — was up to 5000 individual round trips.
    if updates_by_id:
        await db.bank_statement_lines.bulk_update_by_id(updates_by_id)

    unmatched_pdcs = [p for p in cleared_pdcs if p["id"] not in pdc_matched_ids]

    return {
        "bank_account_id": bank_account_id,
        "matched_count": len(matched),
        "unmatched_statement_lines": len(unmatched_stmt),
        "unmatched_pdcs": len(unmatched_pdcs),
        "matched": matched,
        "unmatched_stmt": unmatched_stmt,
        "unmatched_pdcs_list": unmatched_pdcs,
    }


@router.get("/bank-recon/summary")
async def bank_recon_summary(
    bank_account_id: str,
    user: dict = Depends(get_current_user),
):
    _require_banking(user)
    total = await db.bank_statement_lines.count_documents({"bank_account_id": bank_account_id})
    matched = await db.bank_statement_lines.count_documents({"bank_account_id": bank_account_id, "match_status": "MATCHED"})
    unmatched = total - matched
    return {"total_lines": total, "matched": matched, "unmatched": unmatched}


# ══════════════════════════════════════════════════════════════
# Interest Rules & Overdue Interest
# ══════════════════════════════════════════════════════════════

@router.get("/interest-rules")
async def list_interest_rules(user: dict = Depends(get_current_user)):
    _require_banking(user)
    return await crud_list("interest_rules", sort_field="name")


@router.post("/interest-rules")
async def create_interest_rule(payload: InterestRule, user: dict = Depends(require_admin)):
    return await crud_create("interest_rules", payload.model_dump(), user)


def _compute_overdue_interest(
    invoice_amount: float,
    due_date: str,
    as_of: str,
    grace_days: int,
    rate_pct_pa: float,
    basis: str,
) -> dict:
    """
    Compute overdue interest on an invoice.

    grace_days: number of days after due_date before interest kicks in.
    basis: "simple" or "compound" (daily compounding).
    """
    due = date.fromisoformat(due_date)
    as_of_d = date.fromisoformat(as_of)
    interest_start = due + timedelta(days=grace_days)

    if as_of_d <= interest_start:
        return {"overdue_days": 0, "interest": 0.0, "applicable": False}

    overdue_days = (as_of_d - interest_start).days
    daily_rate = rate_pct_pa / 100.0 / 365.0

    if basis == "compound":
        interest = invoice_amount * ((1 + daily_rate) ** overdue_days - 1)
    else:
        interest = invoice_amount * daily_rate * overdue_days

    return {
        "overdue_days": overdue_days,
        "grace_days": grace_days,
        "rate_pct_pa": rate_pct_pa,
        "basis": basis,
        "interest": round(interest, 2),
        "applicable": True,
    }


@router.post("/interest/run")
async def run_overdue_interest(
    payload: InterestRunRequest,
    user: dict = Depends(get_current_user),
):
    """
    Compute overdue interest for unpaid invoices.
    Finds unpaid/partial sales invoices past due + grace; computes interest per rule.
    Returns list of debit note candidates; optionally creates them.
    """
    _require_banking(user)

    # Load applicable rule
    rule_filter: dict = {}
    if payload.rule_id:
        rule_filter["id"] = payload.rule_id
    elif payload.party_id:
        rule_filter["party_id"] = payload.party_id
    else:
        rule_filter["party_id"] = None  # global rule

    rule = await db.interest_rules.find_one(rule_filter, {"_id": 0})
    if not rule:
        # Fall back to global
        rule = await db.interest_rules.find_one({"party_id": None}, {"_id": 0})
    if not rule:
        raise HTTPException(404, "No interest rule found. Create one via POST /interest-rules")

    # Load overdue invoices (from sales orders / invoices collection)
    inv_filter: dict = {"status": {"$in": ["PENDING", "PARTIAL"]}, "due_date": {"$lt": payload.as_of_date}}
    if payload.party_id:
        inv_filter["customer_id"] = payload.party_id

    invoices = await db.sales_orders.find(inv_filter, {"_id": 0}).to_list(5000)

    results = []
    for inv in invoices:
        amount = float(inv.get("total_amount", 0) or inv.get("grand_total", 0))
        if amount < rule.get("min_amount", 0):
            continue
        due_date = inv.get("due_date", "")
        if not due_date:
            continue

        calc = _compute_overdue_interest(
            invoice_amount=amount,
            due_date=due_date,
            as_of=payload.as_of_date,
            grace_days=int(rule.get("grace_days", 0)),
            rate_pct_pa=float(rule.get("rate_pct_pa", 0)),
            basis=rule.get("basis", "simple"),
        )
        if not calc["applicable"]:
            continue

        entry = {
            "invoice_id": inv.get("id", ""),
            "invoice_no": inv.get("order_number", ""),
            "customer_id": inv.get("customer_id", ""),
            "invoice_amount": amount,
            "due_date": due_date,
            **calc,
            "rule_name": rule.get("name", ""),
        }

        if payload.create_debit_notes and calc["interest"] > 0:
            debit_note = {
                "type": "overdue_interest",
                "party_id": inv.get("customer_id", ""),
                "source_invoice_id": inv.get("id", ""),
                "amount": calc["interest"],
                "as_of_date": payload.as_of_date,
                "rule_id": rule.get("id"),
                "narration": f"Overdue interest on invoice {inv.get('order_number', '')} @ {rule['rate_pct_pa']}% pa",
            }
            dn_doc = await crud_create("debit_notes", debit_note, user)
            entry["debit_note_id"] = dn_doc["id"]

        results.append(entry)

    return {
        "as_of_date": payload.as_of_date,
        "rule": rule.get("name"),
        "invoices_checked": len(invoices),
        "interest_applicable": len(results),
        "total_interest": round(sum(r["interest"] for r in results), 2),
        "results": results,
        "debit_notes_created": payload.create_debit_notes,
    }


# ══════════════════════════════════════════════════════════════
# Bank Accounts (supplement existing banking.py)
# ══════════════════════════════════════════════════════════════

@router.get("/bank-accounts")
async def list_bank_accounts(user: dict = Depends(get_current_user)):
    _require_banking(user)
    return await crud_list("bank_accounts", sort_field="name")


@router.post("/bank-accounts")
async def create_bank_account(
    name: str,
    account_no_masked: str,
    ifsc: str,
    opening_balance: float = 0.0,
    ledger_id: Optional[str] = None,
    user: dict = Depends(require_admin),
):
    doc = {
        "name": name,
        "account_no_masked": account_no_masked,
        "ifsc": ifsc,
        "opening_balance": opening_balance,
        "ledger_id": ledger_id,
    }
    return await crud_create("bank_accounts", doc, user)
