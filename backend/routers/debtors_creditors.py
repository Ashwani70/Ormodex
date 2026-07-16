"""Debtors & Creditors (AR/AP) Management Router.

Covers:
- Customer ledger (Debtors / Accounts Receivable)
- Vendor ledger  (Creditors / Accounts Payable)
- Payment allocation (one payment ↔ many invoices, partial, TDS, discount)
- Ageing report (0-30 / 31-60 / 61-90 / 90-180 / 180+)
- Dashboard aggregates (totals, overdue, top 10, cash flow)
- Collection notes, reminders, promise-to-pay
- Credit limit management
- Outstanding / statement reports
- Hooks: called by sales, purchase, banking routers after document posting
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone, timedelta
from typing import Optional, Literal, List, Any

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, field_validator

from core.auth_utils import get_current_user, require_admin, is_admin_role
from core.db import db

router = APIRouter(prefix="/debtors-creditors", tags=["Debtors & Creditors"])

# ─────────────────────────── Permission guard ───────────────────────────

def _require_dc(user: dict) -> dict:
    if (is_admin_role(user.get("role")) or user.get("role") == "accountant"):
        return user
    perms = user.get("module_permissions", [])
    if "debtors_creditors" not in perms and "accounting" not in perms:
        raise HTTPException(403, "Debtors & Creditors module access required")
    return user


def _require_dc_write(user: dict) -> dict:
    _require_dc(user)
    if not is_admin_role(user.get("role")) and user.get("role") != "accountant":
        raise HTTPException(403, "Write access requires admin or accountant role")
    return user


# ─────────────────────────── Helpers ───────────────────────────

def _today() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def _parse_date(d: Optional[str]) -> Optional[date]:
    if not d:
        return None
    try:
        return date.fromisoformat(d[:10])
    except Exception:
        return None


def _overdue_days(due_date_str: Optional[str]) -> int:
    if not due_date_str:
        return 0
    d = _parse_date(due_date_str)
    if not d:
        return 0
    delta = (date.today() - d).days
    return max(0, delta)


def _age_bucket(days: int) -> str:
    if days <= 0:
        return "current"
    if days <= 30:
        return "0_30"
    if days <= 60:
        return "31_60"
    if days <= 90:
        return "61_90"
    if days <= 180:
        return "90_180"
    return "180_plus"


def _fmt_rupees(v: Any) -> float:
    try:
        return float(v or 0)
    except Exception:
        return 0.0


async def _get_party_name(party_type: str, party_id: str) -> str:
    if party_type == "customer":
        p = await db.customers.find_one({"id": party_id})
    else:
        p = await db.vendors.find_one({"id": party_id})
    if not p:
        return ""
    return p.get("name", "")


async def _next_voucher_no(tenant_id: str, prefix: str) -> str:
    count = await db.dc_ledger_entries.count_documents(
        {"tenant_id": tenant_id, "voucher_no": {"$regex": f"^{prefix}/"}}
    )
    fy = date.today().year
    return f"{prefix}/{fy}/{str(count + 1).zfill(5)}"


async def _recalc_party_balance(tenant_id: str, party_type: str, party_id: str) -> None:
    """Recompute and upsert dc_party_balances for a party."""
    entries = await db.dc_ledger_entries.find(
        {"tenant_id": tenant_id, "party_type": party_type, "party_id": party_id,
         "is_deleted": {"$ne": True}}
    ).to_list(10000)

    total_debit  = sum(_fmt_rupees(e.get("debit"))  for e in entries)
    total_credit = sum(_fmt_rupees(e.get("credit")) for e in entries)
    outstanding  = total_debit - total_credit

    overdue = 0.0
    for e in entries:
        if e.get("status") not in ("PAID", "CANCELLED"):
            due_dt = _parse_date(e.get("due_date"))
            if due_dt and due_dt < date.today():
                overdue += _fmt_rupees(e.get("debit")) - _fmt_rupees(e.get("credit"))

    last_txn      = max((e.get("entry_date", "") for e in entries), default="")
    pay_entries   = [e for e in entries if e.get("voucher_type") in
                     ("RECEIPT", "PAYMENT", "ADVANCE_RECEIVED", "ADVANCE_PAID")]
    last_payment  = max((e.get("entry_date", "") for e in pay_entries), default="")
    party_name    = await _get_party_name(party_type, party_id)

    existing = await db.dc_party_balances.find_one(
        {"tenant_id": tenant_id, "party_type": party_type, "party_id": party_id}
    )
    doc = {
        "tenant_id":          tenant_id,
        "party_type":         party_type,
        "party_id":           party_id,
        "party_name":         party_name,
        "total_debit":        total_debit,
        "total_credit":       total_credit,
        "outstanding":        outstanding,
        "overdue_amount":     overdue,
        "last_txn_date":      last_txn,
        "last_payment_date":  last_payment,
        "updated_at":         _now_iso(),
    }
    if existing:
        await db.dc_party_balances.update_one(
            {"tenant_id": tenant_id, "party_type": party_type, "party_id": party_id},
            {"$set": doc}
        )
    else:
        doc["id"] = _new_id()
        await db.dc_party_balances.insert_one(doc)


async def _update_entry_statuses(tenant_id: str, party_type: str, party_id: str) -> None:
    """After any ledger write recompute invoice status (OPEN/PARTIALLY_PAID/PAID/OVERDUE)."""
    invoice_types = ("SALES_INVOICE", "PURCHASE_BILL", "OPENING_BALANCE")
    invoices = await db.dc_ledger_entries.find(
        {"tenant_id": tenant_id, "party_type": party_type, "party_id": party_id,
         "voucher_type": {"$in": list(invoice_types)}, "is_deleted": {"$ne": True}}
    ).to_list(5000)

    # Sum up allocations per invoice
    allocs = await db.dc_payment_allocations.find(
        {"tenant_id": tenant_id, "party_type": party_type, "party_id": party_id}
    ).to_list(50000)
    alloc_by_inv: dict[str, float] = {}
    for a in allocs:
        inv_id = a.get("invoice_entry_id", "")
        alloc_by_inv[inv_id] = alloc_by_inv.get(inv_id, 0) + _fmt_rupees(a.get("allocated_amount"))

    # Status recomputation is pure in-memory work; collect each changed
    # invoice's own $set doc, then write them all in ONE bulk_update_by_id
    # call instead of an update_one per changed invoice inside the loop —
    # this runs after every ledger write/allocation/cancellation across the
    # app, and N grows with a customer's unpaid-invoice backlog (up to
    # hundreds for large customers).
    updates_by_id: dict = {}
    today = date.today()
    for inv in invoices:
        face_value = _fmt_rupees(inv.get("debit")) or _fmt_rupees(inv.get("credit"))
        paid       = alloc_by_inv.get(inv["id"], 0.0)
        due_d      = _parse_date(inv.get("due_date", ""))

        if inv.get("status") == "CANCELLED":
            continue
        if paid >= face_value - 0.01:
            new_status = "PAID"
        elif paid > 0:
            new_status = "PARTIALLY_PAID"
        elif due_d and due_d < today:
            new_status = "OVERDUE"
        else:
            new_status = "OPEN"

        if inv.get("status") != new_status:
            updates_by_id[inv["id"]] = {"$set": {"status": new_status, "updated_at": _now_iso()}}

    if updates_by_id:
        await db.dc_ledger_entries.bulk_update_by_id(updates_by_id)


# ─────────────────────────── Pydantic Schemas ───────────────────────────

class LedgerEntryIn(BaseModel):
    party_type:   Literal["customer", "vendor"]
    party_id:     str
    voucher_type: Literal[
        "SALES_INVOICE", "PURCHASE_BILL", "RECEIPT", "PAYMENT",
        "CREDIT_NOTE", "DEBIT_NOTE", "ADVANCE_RECEIVED", "ADVANCE_PAID",
        "OPENING_BALANCE", "JOURNAL"
    ]
    source_doc_id: Optional[str] = None
    entry_date:    str
    due_date:      Optional[str] = None
    debit:         float = 0.0
    credit:        float = 0.0
    narration:     Optional[str] = None
    branch_id:     Optional[str] = None
    fiscal_year:   Optional[str] = None


class PaymentAllocationIn(BaseModel):
    party_type:       Literal["customer", "vendor"]
    party_id:         str
    payment_entry_id: str
    allocations: List[dict]  # [{invoice_entry_id, allocated_amount, tds_amount?, discount_amount?, round_off?}]


class CreditLimitIn(BaseModel):
    customer_id:   str
    credit_limit:  float
    payment_terms: int = 30
    credit_hold:   bool = False
    notes:         Optional[str] = None


class CreditLimitUpdate(BaseModel):
    credit_limit:  Optional[float] = None
    payment_terms: Optional[int] = None
    credit_hold:   Optional[bool] = None
    notes:         Optional[str] = None


class CollectionNoteIn(BaseModel):
    party_type:           Literal["customer", "vendor"]
    party_id:             str
    note:                 str
    reminder_type:        Literal["EMAIL", "WHATSAPP", "SMS", "CALL", "VISIT"] = "CALL"
    promise_date:         Optional[str] = None
    promise_amount:       Optional[float] = None
    collection_executive: Optional[str] = None
    outcome:              Optional[str] = None


class ReminderIn(BaseModel):
    party_type: Literal["customer", "vendor"]
    party_id:   str
    channel:    Literal["EMAIL", "WHATSAPP", "SMS"]
    template:   Optional[str] = None
    recipient:  str


# ─────────────────────────── Ledger CRUD ───────────────────────────

@router.post("/ledger-entry")
async def create_ledger_entry(data: LedgerEntryIn, bg: BackgroundTasks, user=Depends(get_current_user)):
    _require_dc_write(user)
    tenant = user.get("tenant_id", "default")

    prefix_map = {
        "SALES_INVOICE": "SI", "PURCHASE_BILL": "PB", "RECEIPT": "RCV",
        "PAYMENT": "PAY", "CREDIT_NOTE": "CN", "DEBIT_NOTE": "DN",
        "ADVANCE_RECEIVED": "ADR", "ADVANCE_PAID": "ADP",
        "OPENING_BALANCE": "OB", "JOURNAL": "JV",
    }
    prefix = prefix_map.get(data.voucher_type, "DC")
    voucher_no = await _next_voucher_no(tenant, prefix)
    party_name = await _get_party_name(data.party_type, data.party_id)

    doc = {
        "id":            _new_id(),
        "tenant_id":     tenant,
        "party_type":    data.party_type,
        "party_id":      data.party_id,
        "party_name":    party_name,
        "voucher_type":  data.voucher_type,
        "voucher_no":    voucher_no,
        "source_doc_id": data.source_doc_id or "",
        "entry_date":    data.entry_date,
        "due_date":      data.due_date or "",
        "debit":         data.debit,
        "credit":        data.credit,
        "narration":     data.narration or "",
        "status":        "OPEN",
        "branch_id":     data.branch_id or "",
        "fiscal_year":   data.fiscal_year or str(date.today().year),
        "is_deleted":    False,
        "created_by":    user.get("id", ""),
        "created_at":    _now_iso(),
        "updated_at":    _now_iso(),
    }
    await db.dc_ledger_entries.insert_one(doc)
    bg.add_task(_recalc_party_balance, tenant, data.party_type, data.party_id)
    bg.add_task(_update_entry_statuses, tenant, data.party_type, data.party_id)
    doc.pop("_id", None)
    return doc


@router.get("/ledger")
async def get_party_ledger(
    party_type: Literal["customer", "vendor"],
    party_id:   str,
    from_date:  Optional[str] = None,
    to_date:    Optional[str] = None,
    voucher_type: Optional[str] = None,
    page:  int = 1,
    limit: int = 100,
    user=Depends(get_current_user),
):
    _require_dc(user)
    tenant = user.get("tenant_id", "default")
    q: dict = {"tenant_id": tenant, "party_type": party_type,
               "party_id": party_id, "is_deleted": {"$ne": True}}
    if from_date:
        q.setdefault("entry_date", {})["$gte"] = from_date
    if to_date:
        q.setdefault("entry_date", {})["$lte"] = to_date
    if voucher_type:
        q["voucher_type"] = voucher_type

    total   = await db.dc_ledger_entries.count_documents(q)
    entries = await db.dc_ledger_entries.find(q, {"_id": 0}).to_list(min(limit, 2000))

    # Sort by date asc, compute running balance
    entries.sort(key=lambda e: e.get("entry_date", ""))
    running = 0.0
    for e in entries:
        running += _fmt_rupees(e.get("debit")) - _fmt_rupees(e.get("credit"))
        e["running_balance"] = round(running, 2)
        e["overdue_days"]    = _overdue_days(e.get("due_date"))
        e["age_bucket"]      = _age_bucket(e["overdue_days"])

    # Apply page slice
    start = (page - 1) * limit
    paged = entries[start: start + limit]
    return {"total": total, "page": page, "limit": limit, "items": paged}


@router.patch("/ledger-entry/{entry_id}/cancel")
async def cancel_ledger_entry(entry_id: str, bg: BackgroundTasks, user=Depends(get_current_user)):
    _require_dc_write(user)
    tenant = user.get("tenant_id", "default")
    entry  = await db.dc_ledger_entries.find_one({"id": entry_id, "tenant_id": tenant})
    if not entry:
        raise HTTPException(404, "Ledger entry not found")
    if entry.get("status") == "CANCELLED":
        raise HTTPException(400, "Already cancelled")
    await db.dc_ledger_entries.update_one(
        {"id": entry_id, "tenant_id": tenant},
        {"$set": {"status": "CANCELLED", "updated_at": _now_iso()}}
    )
    bg.add_task(_recalc_party_balance, tenant, entry["party_type"], entry["party_id"])
    bg.add_task(_update_entry_statuses, tenant, entry["party_type"], entry["party_id"])
    return {"ok": True}


# ─────────────────────────── Opening Balance ───────────────────────────

class OpeningBalanceIn(BaseModel):
    party_type: Literal["customer", "vendor"]
    party_id:   str
    amount:     float
    as_of_date: str
    narration:  Optional[str] = None


@router.post("/opening-balance")
async def set_opening_balance(data: OpeningBalanceIn, bg: BackgroundTasks, user=Depends(get_current_user)):
    _require_dc_write(user)
    tenant = user.get("tenant_id", "default")

    # Cancel any prior OB
    existing_obs = await db.dc_ledger_entries.find(
        {"tenant_id": tenant, "party_type": data.party_type,
         "party_id": data.party_id, "voucher_type": "OPENING_BALANCE",
         "is_deleted": {"$ne": True}}
    ).to_list(100)
    for ob in existing_obs:
        await db.dc_ledger_entries.update_one(
            {"id": ob["id"]}, {"$set": {"status": "CANCELLED", "updated_at": _now_iso()}}
        )

    party_name = await _get_party_name(data.party_type, data.party_id)
    # For customers: OB is a debit (they owe us). For vendors: OB is a credit (we owe them).
    debit  = data.amount if data.party_type == "customer" else 0.0
    credit = data.amount if data.party_type == "vendor"   else 0.0
    fy     = data.as_of_date[:4]
    vno    = await _next_voucher_no(tenant, "OB")

    doc = {
        "id":            _new_id(),
        "tenant_id":     tenant,
        "party_type":    data.party_type,
        "party_id":      data.party_id,
        "party_name":    party_name,
        "voucher_type":  "OPENING_BALANCE",
        "voucher_no":    vno,
        "source_doc_id": "",
        "entry_date":    data.as_of_date,
        "due_date":      "",
        "debit":         debit,
        "credit":        credit,
        "narration":     data.narration or "Opening Balance",
        "status":        "OPEN",
        "branch_id":     "",
        "fiscal_year":   fy,
        "is_deleted":    False,
        "created_by":    user.get("id", ""),
        "created_at":    _now_iso(),
        "updated_at":    _now_iso(),
    }
    await db.dc_ledger_entries.insert_one(doc)
    bg.add_task(_recalc_party_balance, tenant, data.party_type, data.party_id)
    doc.pop("_id", None)
    return doc


# ─────────────────────────── Payment Allocation ───────────────────────────

@router.post("/allocate-payment")
async def allocate_payment(data: PaymentAllocationIn, bg: BackgroundTasks, user=Depends(get_current_user)):
    _require_dc_write(user)
    tenant = user.get("tenant_id", "default")

    payment = await db.dc_ledger_entries.find_one(
        {"id": data.payment_entry_id, "tenant_id": tenant}
    )
    if not payment:
        raise HTTPException(404, "Payment ledger entry not found")

    # Max allocatable = credit of payment entry
    payment_amount = _fmt_rupees(payment.get("credit")) or _fmt_rupees(payment.get("debit"))
    total_allocating = sum(_fmt_rupees(a.get("allocated_amount", 0)) for a in data.allocations)
    if total_allocating > payment_amount + 0.01:
        raise HTTPException(400, f"Allocation ₹{total_allocating} exceeds payment ₹{payment_amount}")

    inserted = []
    for a in data.allocations:
        inv_entry = await db.dc_ledger_entries.find_one(
            {"id": a.get("invoice_entry_id"), "tenant_id": tenant}
        )
        if not inv_entry:
            raise HTTPException(404, f"Invoice entry {a.get('invoice_entry_id')} not found")

        doc = {
            "id":                _new_id(),
            "tenant_id":         tenant,
            "party_type":        data.party_type,
            "party_id":          data.party_id,
            "payment_entry_id":  data.payment_entry_id,
            "invoice_entry_id":  a.get("invoice_entry_id"),
            "allocated_amount":  _fmt_rupees(a.get("allocated_amount", 0)),
            "tds_amount":        _fmt_rupees(a.get("tds_amount", 0)),
            "discount_amount":   _fmt_rupees(a.get("discount_amount", 0)),
            "round_off":         _fmt_rupees(a.get("round_off", 0)),
            "created_at":        _now_iso(),
            "created_by":        user.get("id", ""),
        }
        await db.dc_payment_allocations.insert_one(doc)
        inserted.append(doc)

    bg.add_task(_recalc_party_balance, tenant, data.party_type, data.party_id)
    bg.add_task(_update_entry_statuses, tenant, data.party_type, data.party_id)
    return {"ok": True, "allocations": [d["id"] for d in inserted]}


@router.get("/allocations/{payment_entry_id}")
async def get_payment_allocations(payment_entry_id: str, user=Depends(get_current_user)):
    _require_dc(user)
    tenant = user.get("tenant_id", "default")
    allocs = await db.dc_payment_allocations.find(
        {"tenant_id": tenant, "payment_entry_id": payment_entry_id}, {"_id": 0}
    ).to_list(500)
    return allocs


# ─────────────────────────── Outstanding (party-wise) ───────────────────────────

@router.get("/outstanding")
async def list_outstanding(
    party_type:    Literal["customer", "vendor"],
    overdue_only:  bool = False,
    search:        Optional[str] = None,
    branch_id:     Optional[str] = None,
    salesman_id:   Optional[str] = None,
    city:          Optional[str] = None,
    page:          int = 1,
    limit:         int = 50,
    sort_by:       str = "outstanding",
    sort_dir:      int = -1,
    user=Depends(get_current_user),
):
    _require_dc(user)
    tenant = user.get("tenant_id", "default")
    q: dict = {"tenant_id": tenant, "party_type": party_type}

    if overdue_only:
        q["overdue_amount"] = {"$gt": 0}
    if search:
        q["party_name"] = {"$regex": search}

    total   = await db.dc_party_balances.count_documents(q)
    records = await db.dc_party_balances.find(q, {"_id": 0}).to_list(5000)

    # Merge in party details (gstin, mobile, city)
    party_coll = "customers" if party_type == "customer" else "vendors"
    party_ids  = [r["party_id"] for r in records]
    if party_ids:
        parties = await db[party_coll].find(
            {"id": {"$in": party_ids}}, {"_id": 0}
        ).to_list(5000)
        party_map = {p["id"]: p for p in parties}
    else:
        party_map = {}

    results = []
    for r in records:
        p   = party_map.get(r["party_id"], {})
        outstanding = _fmt_rupees(r.get("outstanding"))
        if outstanding == 0 and not overdue_only:
            pass  # include zero balances
        rec = {
            **r,
            "gstin":       p.get("gstin", ""),
            "mobile":      p.get("phone", ""),
            "city":        str(p.get("city") or p.get("address") or ""),
            "credit_limit": _fmt_rupees(p.get("credit_limit")),
        }
        if isinstance(city, str) and city.strip():
            city_filter = city.lower()
            rec_city = str(rec.get("city") or "").lower()
            if city_filter not in rec_city:
                continue
        results.append(rec)

    # Sort
    def sort_key(x):
        val = x.get(sort_by, 0)
        try:
            return float(val or 0)
        except Exception:
            return str(val or "")

    results.sort(key=sort_key, reverse=(sort_dir == -1))

    start = (page - 1) * limit
    paged = results[start: start + limit]
    return {"total": len(results), "page": page, "limit": limit, "items": paged}


# ─────────────────────────── Invoice Outstanding ───────────────────────────

@router.get("/invoice-outstanding")
async def list_invoice_outstanding(
    party_type:   Literal["customer", "vendor"],
    party_id:     Optional[str] = None,
    status:       Optional[str] = None,
    from_date:    Optional[str] = None,
    to_date:      Optional[str] = None,
    overdue_only: bool = False,
    search:       Optional[str] = None,
    page:         int = 1,
    limit:        int = 100,
    user=Depends(get_current_user),
):
    _require_dc(user)
    tenant = user.get("tenant_id", "default")
    invoice_types = ["SALES_INVOICE", "PURCHASE_BILL", "OPENING_BALANCE"]

    q: dict = {
        "tenant_id":    tenant,
        "party_type":   party_type,
        "voucher_type": {"$in": invoice_types},
        "is_deleted":   {"$ne": True},
    }
    if party_id:
        q["party_id"] = party_id
    if status:
        q["status"] = status
    if from_date:
        q.setdefault("entry_date", {})["$gte"] = from_date
    if to_date:
        q.setdefault("entry_date", {})["$lte"] = to_date
    if search:
        q["$or"] = [
            {"party_name": {"$regex": search}},
            {"voucher_no": {"$regex": search}},
        ]

    total   = await db.dc_ledger_entries.count_documents(q)
    entries = await db.dc_ledger_entries.find(q, {"_id": 0}).to_list(min(limit * 5, 5000))

    # Compute allocations
    entry_ids = [e["id"] for e in entries]
    if entry_ids:
        allocs = await db.dc_payment_allocations.find(
            {"tenant_id": tenant, "invoice_entry_id": {"$in": entry_ids}}, {"_id": 0}
        ).to_list(50000)
        alloc_map: dict[str, float] = {}
        for a in allocs:
            inv_id = a.get("invoice_entry_id", "")
            alloc_map[inv_id] = alloc_map.get(inv_id, 0) + _fmt_rupees(a.get("allocated_amount"))
    else:
        alloc_map = {}

    today = date.today()
    results = []
    for e in entries:
        face   = _fmt_rupees(e.get("debit")) or _fmt_rupees(e.get("credit"))
        paid   = alloc_map.get(e["id"], 0.0)
        oust   = max(0.0, face - paid)
        days   = _overdue_days(e.get("due_date"))
        bucket = _age_bucket(days)

        if overdue_only and days <= 0:
            continue

        results.append({
            **e,
            "face_value":    face,
            "paid_amount":   paid,
            "outstanding":   oust,
            "overdue_days":  days,
            "age_bucket":    bucket,
        })

    start = (page - 1) * limit
    paged = results[start: start + limit]
    return {"total": total, "page": page, "limit": limit, "items": paged}


# ─────────────────────────── Ageing Report ───────────────────────────

@router.get("/ageing")
async def ageing_report(
    party_type: Literal["customer", "vendor"],
    as_of_date: Optional[str] = None,
    party_id:   Optional[str] = None,
    branch_id:  Optional[str] = None,
    user=Depends(get_current_user),
):
    _require_dc(user)
    tenant    = user.get("tenant_id", "default")
    as_of     = _parse_date(as_of_date) or date.today()
    inv_types = ["SALES_INVOICE", "PURCHASE_BILL", "OPENING_BALANCE"]

    q: dict = {
        "tenant_id":    tenant,
        "party_type":   party_type,
        "voucher_type": {"$in": inv_types},
        "is_deleted":   {"$ne": True},
        "status":       {"$nin": ["PAID", "CANCELLED"]},
    }
    if party_id:
        q["party_id"] = party_id
    if branch_id:
        q["branch_id"] = branch_id

    entries = await db.dc_ledger_entries.find(q, {"_id": 0}).to_list(50000)
    entry_ids = [e["id"] for e in entries]

    if entry_ids:
        allocs = await db.dc_payment_allocations.find(
            {"tenant_id": tenant, "invoice_entry_id": {"$in": entry_ids}}, {"_id": 0}
        ).to_list(200000)
        alloc_map: dict[str, float] = {}
        for a in allocs:
            k = a.get("invoice_entry_id", "")
            alloc_map[k] = alloc_map.get(k, 0) + _fmt_rupees(a.get("allocated_amount"))
    else:
        alloc_map = {}

    buckets_template = {
        "current": 0.0, "0_30": 0.0, "31_60": 0.0,
        "61_90": 0.0, "90_180": 0.0, "180_plus": 0.0
    }

    # Party-wise aggregation
    party_rows: dict[str, dict] = {}
    totals = dict(buckets_template)
    totals["total"] = 0.0

    for e in entries:
        face    = _fmt_rupees(e.get("debit")) or _fmt_rupees(e.get("credit"))
        paid    = alloc_map.get(e["id"], 0.0)
        oust    = max(0.0, face - paid)
        if oust <= 0:
            continue

        due_d = _parse_date(e.get("due_date"))
        if due_d:
            days = (as_of - due_d).days
        else:
            days = 0
        bucket = _age_bucket(max(0, days))

        pid = e.get("party_id", "")
        if pid not in party_rows:
            party_rows[pid] = {
                "party_id":   pid,
                "party_name": e.get("party_name", ""),
                "total":      0.0,
                **dict(buckets_template),
            }
        party_rows[pid][bucket] = round(party_rows[pid].get(bucket, 0) + oust, 2)
        party_rows[pid]["total"] = round(party_rows[pid]["total"] + oust, 2)
        totals[bucket] = round(totals.get(bucket, 0) + oust, 2)
        totals["total"] = round(totals["total"] + oust, 2)

    rows = sorted(party_rows.values(), key=lambda x: x["total"], reverse=True)
    return {"as_of_date": as_of.isoformat(), "rows": rows, "totals": totals}


# ─────────────────────────── Dashboard ───────────────────────────

@router.get("/dashboard")
async def dc_dashboard(user=Depends(get_current_user)):
    _require_dc(user)
    tenant = user.get("tenant_id", "default")
    today  = _today()

    # Pull all party balances
    balances = await db.dc_party_balances.find(
        {"tenant_id": tenant}, {"_id": 0}
    ).to_list(10000)

    debtors   = [b for b in balances if b.get("party_type") == "customer"]
    creditors = [b for b in balances if b.get("party_type") == "vendor"]

    total_debtors   = sum(_fmt_rupees(b.get("outstanding")) for b in debtors)
    total_creditors = sum(_fmt_rupees(b.get("outstanding")) for b in creditors)
    overdue_recv    = sum(_fmt_rupees(b.get("overdue_amount")) for b in debtors)
    overdue_pay     = sum(_fmt_rupees(b.get("overdue_amount")) for b in creditors)

    # Today's receipts and payments
    today_entries = await db.dc_ledger_entries.find(
        {"tenant_id": tenant, "entry_date": today, "is_deleted": {"$ne": True}}
    ).to_list(5000)
    today_receipts = sum(_fmt_rupees(e.get("credit")) for e in today_entries
                         if e.get("voucher_type") in ("RECEIPT", "ADVANCE_RECEIVED"))
    today_payments = sum(_fmt_rupees(e.get("debit")) for e in today_entries
                         if e.get("voucher_type") in ("PAYMENT", "ADVANCE_PAID"))

    # Top 10
    top_debtors   = sorted(debtors,   key=lambda x: _fmt_rupees(x.get("outstanding")), reverse=True)[:10]
    top_creditors = sorted(creditors, key=lambda x: _fmt_rupees(x.get("outstanding")), reverse=True)[:10]

    # Collection efficiency (last 30 days)
    thirty_days_ago = (date.today() - timedelta(days=30)).isoformat()
    period_invoices = await db.dc_ledger_entries.find(
        {"tenant_id": tenant, "party_type": "customer",
         "voucher_type": "SALES_INVOICE",
         "entry_date": {"$gte": thirty_days_ago},
         "is_deleted": {"$ne": True}}
    ).to_list(5000)
    period_receipts = await db.dc_ledger_entries.find(
        {"tenant_id": tenant, "party_type": "customer",
         "voucher_type": "RECEIPT",
         "entry_date": {"$gte": thirty_days_ago},
         "is_deleted": {"$ne": True}}
    ).to_list(5000)
    invoiced_30 = sum(_fmt_rupees(e.get("debit")) for e in period_invoices)
    collected_30 = sum(_fmt_rupees(e.get("credit")) for e in period_receipts)
    efficiency = (collected_30 / invoiced_30 * 100) if invoiced_30 > 0 else 0.0

    return {
        "total_debtors":     round(total_debtors,   2),
        "total_creditors":   round(total_creditors, 2),
        "net_outstanding":   round(total_debtors - total_creditors, 2),
        "overdue_receivables": round(overdue_recv,  2),
        "overdue_payables":    round(overdue_pay,   2),
        "today_receipts":    round(today_receipts,  2),
        "today_payments":    round(today_payments,  2),
        "collection_efficiency_30d": round(efficiency, 1),
        "top_debtors":   top_debtors,
        "top_creditors": top_creditors,
    }


# ─────────────────────────── Credit Limits ───────────────────────────

@router.get("/credit-limits")
async def list_credit_limits(user=Depends(get_current_user)):
    _require_dc(user)
    tenant = user.get("tenant_id", "default")
    limits = await db.dc_credit_limits.find(
        {"tenant_id": tenant}, {"_id": 0}
    ).to_list(5000)
    return limits


@router.post("/credit-limits")
async def upsert_credit_limit(data: CreditLimitIn, user=Depends(get_current_user)):
    _require_dc_write(user)
    tenant = user.get("tenant_id", "default")
    existing = await db.dc_credit_limits.find_one(
        {"tenant_id": tenant, "customer_id": data.customer_id}
    )
    doc = {
        "tenant_id":     tenant,
        "customer_id":   data.customer_id,
        "credit_limit":  data.credit_limit,
        "payment_terms": data.payment_terms,
        "credit_hold":   data.credit_hold,
        "notes":         data.notes or "",
        "updated_by":    user.get("id", ""),
        "updated_at":    _now_iso(),
    }
    if existing:
        await db.dc_credit_limits.update_one(
            {"tenant_id": tenant, "customer_id": data.customer_id},
            {"$set": doc}
        )
    else:
        doc["id"]         = _new_id()
        doc["created_at"] = _now_iso()
        await db.dc_credit_limits.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/credit-limits/{customer_id}")
async def get_credit_limit(customer_id: str, user=Depends(get_current_user)):
    _require_dc(user)
    tenant = user.get("tenant_id", "default")
    limit  = await db.dc_credit_limits.find_one(
        {"tenant_id": tenant, "customer_id": customer_id}
    )
    balance = await db.dc_party_balances.find_one(
        {"tenant_id": tenant, "party_type": "customer", "party_id": customer_id}
    )
    outstanding  = _fmt_rupees(balance.get("outstanding") if balance else 0)
    credit_limit = _fmt_rupees(limit.get("credit_limit") if limit else 0)
    return {
        "customer_id":     customer_id,
        "credit_limit":    credit_limit,
        "payment_terms":   limit.get("payment_terms", 30) if limit else 30,
        "credit_hold":     limit.get("credit_hold", False) if limit else False,
        "outstanding":     outstanding,
        "available_credit": max(0.0, credit_limit - outstanding),
        "utilisation_pct": round((outstanding / credit_limit * 100) if credit_limit > 0 else 0, 1),
    }


# ─────────────────────────── Collection Notes ───────────────────────────

@router.get("/collection-notes")
async def list_collection_notes(
    party_type: Optional[str] = None,
    party_id:   Optional[str] = None,
    from_date:  Optional[str] = None,
    to_date:    Optional[str] = None,
    page:       int = 1,
    limit:      int = 50,
    user=Depends(get_current_user),
):
    _require_dc(user)
    tenant = user.get("tenant_id", "default")
    q: dict = {"tenant_id": tenant, "is_deleted": {"$ne": True}}
    if party_type:
        q["party_type"] = party_type
    if party_id:
        q["party_id"] = party_id
    if from_date:
        q.setdefault("created_at", {})["$gte"] = from_date
    if to_date:
        q.setdefault("created_at", {})["$lte"] = to_date + "T23:59:59"
    total = await db.dc_collection_notes.count_documents(q)
    items = await db.dc_collection_notes.find(q, {"_id": 0}).to_list(limit)
    return {"total": total, "page": page, "limit": limit, "items": items}


@router.post("/collection-notes")
async def create_collection_note(data: CollectionNoteIn, user=Depends(get_current_user)):
    _require_dc(user)
    tenant     = user.get("tenant_id", "default")
    party_name = await _get_party_name(data.party_type, data.party_id)
    doc = {
        "id":                    _new_id(),
        "tenant_id":             tenant,
        "party_type":            data.party_type,
        "party_id":              data.party_id,
        "party_name":            party_name,
        "note":                  data.note,
        "reminder_type":         data.reminder_type,
        "reminder_sent_at":      None,
        "promise_date":          data.promise_date or "",
        "promise_amount":        data.promise_amount or 0,
        "collection_executive":  data.collection_executive or user.get("name", ""),
        "outcome":               data.outcome or "",
        "is_deleted":            False,
        "created_by":            user.get("id", ""),
        "created_at":            _now_iso(),
        "updated_at":            _now_iso(),
    }
    await db.dc_collection_notes.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/collection-notes/{note_id}")
async def update_collection_note(note_id: str, data: dict, user=Depends(get_current_user)):
    _require_dc(user)
    tenant = user.get("tenant_id", "default")
    note   = await db.dc_collection_notes.find_one({"id": note_id, "tenant_id": tenant})
    if not note:
        raise HTTPException(404, "Collection note not found")
    allowed = {"note", "promise_date", "promise_amount", "collection_executive", "outcome", "reminder_type"}
    upd = {k: v for k, v in data.items() if k in allowed}
    upd["updated_at"] = _now_iso()
    await db.dc_collection_notes.update_one({"id": note_id}, {"$set": upd})
    return {"ok": True}


@router.delete("/collection-notes/{note_id}")
async def delete_collection_note(note_id: str, user=Depends(get_current_user)):
    _require_dc_write(user)
    tenant = user.get("tenant_id", "default")
    await db.dc_collection_notes.update_one(
        {"id": note_id, "tenant_id": tenant},
        {"$set": {"is_deleted": True, "deleted_at": _now_iso()}}
    )
    return {"ok": True}


# ─────────────────────────── Reminder Log ───────────────────────────

@router.post("/reminders/send")
async def log_reminder(data: ReminderIn, user=Depends(get_current_user)):
    _require_dc(user)
    tenant     = user.get("tenant_id", "default")
    party_name = await _get_party_name(data.party_type, data.party_id)
    doc = {
        "id":          _new_id(),
        "tenant_id":   tenant,
        "party_type":  data.party_type,
        "party_id":    data.party_id,
        "party_name":  party_name,
        "channel":     data.channel,
        "template":    data.template or "default",
        "recipient":   data.recipient,
        "status":      "SENT",
        "sent_at":     _now_iso(),
        "error":       "",
        "created_by":  user.get("id", ""),
        "created_at":  _now_iso(),
    }
    await db.dc_reminder_logs.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/reminders")
async def list_reminders(
    party_type: Optional[str] = None,
    party_id:   Optional[str] = None,
    page:       int = 1,
    limit:      int = 50,
    user=Depends(get_current_user),
):
    _require_dc(user)
    tenant = user.get("tenant_id", "default")
    q: dict = {"tenant_id": tenant}
    if party_type:
        q["party_type"] = party_type
    if party_id:
        q["party_id"] = party_id
    total = await db.dc_reminder_logs.count_documents(q)
    items = await db.dc_reminder_logs.find(q, {"_id": 0}).to_list(limit)
    return {"total": total, "page": page, "limit": limit, "items": items}


# ─────────────────────────── Reports ───────────────────────────

@router.get("/reports/statement")
async def party_statement(
    party_type: Literal["customer", "vendor"],
    party_id:   str,
    from_date:  Optional[str] = None,
    to_date:    Optional[str] = None,
    user=Depends(get_current_user),
):
    """Full running-balance statement for one customer/vendor."""
    _require_dc(user)
    tenant = user.get("tenant_id", "default")
    q: dict = {
        "tenant_id":  tenant,
        "party_type": party_type,
        "party_id":   party_id,
        "is_deleted": {"$ne": True},
    }
    if from_date:
        q.setdefault("entry_date", {})["$gte"] = from_date
    if to_date:
        q.setdefault("entry_date", {})["$lte"] = to_date

    entries = await db.dc_ledger_entries.find(q, {"_id": 0}).to_list(50000)
    entries.sort(key=lambda e: e.get("entry_date", ""))

    balance = 0.0
    rows = []
    for e in entries:
        d = _fmt_rupees(e.get("debit"))
        c = _fmt_rupees(e.get("credit"))
        balance += d - c
        rows.append({
            "date":        e.get("entry_date"),
            "voucher_no":  e.get("voucher_no"),
            "voucher_type": e.get("voucher_type"),
            "narration":   e.get("narration"),
            "debit":       d,
            "credit":      c,
            "balance":     round(balance, 2),
            "source_doc_id": e.get("source_doc_id"),
            "due_date":    e.get("due_date"),
            "status":      e.get("status"),
        })

    party_name = await _get_party_name(party_type, party_id)
    return {
        "party_id":    party_id,
        "party_name":  party_name,
        "party_type":  party_type,
        "from_date":   from_date,
        "to_date":     to_date,
        "rows":        rows,
        "closing_balance": round(balance, 2),
    }


@router.get("/reports/outstanding-summary")
async def outstanding_summary(
    party_type: Literal["customer", "vendor"],
    as_of_date: Optional[str] = None,
    user=Depends(get_current_user),
):
    _require_dc(user)
    tenant = user.get("tenant_id", "default")
    balances = await db.dc_party_balances.find(
        {"tenant_id": tenant, "party_type": party_type}, {"_id": 0}
    ).to_list(10000)

    total_outstanding = sum(_fmt_rupees(b.get("outstanding")) for b in balances)
    total_overdue     = sum(_fmt_rupees(b.get("overdue_amount")) for b in balances)
    parties_with_balance = [b for b in balances if _fmt_rupees(b.get("outstanding")) > 0]
    parties_overdue      = [b for b in balances if _fmt_rupees(b.get("overdue_amount")) > 0]

    return {
        "total_outstanding":    round(total_outstanding, 2),
        "total_overdue":        round(total_overdue, 2),
        "total_parties":        len(balances),
        "parties_with_balance": len(parties_with_balance),
        "parties_overdue":      len(parties_overdue),
        "top_outstanding":      sorted(parties_with_balance,
                                       key=lambda x: _fmt_rupees(x.get("outstanding")),
                                       reverse=True)[:10],
    }


@router.get("/reports/daily-collection")
async def daily_collection_report(
    from_date: str,
    to_date:   str,
    user=Depends(get_current_user),
):
    _require_dc(user)
    tenant = user.get("tenant_id", "default")
    entries = await db.dc_ledger_entries.find(
        {
            "tenant_id":    tenant,
            "party_type":   "customer",
            "voucher_type": {"$in": ["RECEIPT", "ADVANCE_RECEIVED"]},
            "entry_date":   {"$gte": from_date, "$lte": to_date},
            "is_deleted":   {"$ne": True},
        },
        {"_id": 0}
    ).to_list(10000)

    day_map: dict[str, float] = {}
    for e in entries:
        d = e.get("entry_date", "")[:10]
        day_map[d] = day_map.get(d, 0) + _fmt_rupees(e.get("credit"))

    rows = [{"date": k, "amount": round(v, 2)} for k, v in sorted(day_map.items())]
    total = sum(r["amount"] for r in rows)
    return {"from_date": from_date, "to_date": to_date, "rows": rows, "total": round(total, 2)}


@router.get("/reports/interest")
async def interest_report(
    party_type:    Literal["customer", "vendor"] = "customer",
    interest_rate: float = 18.0,  # % per annum
    user=Depends(get_current_user),
):
    """Calculate simple interest on overdue outstanding."""
    _require_dc(user)
    tenant    = user.get("tenant_id", "default")
    today     = date.today()
    inv_types = ["SALES_INVOICE", "PURCHASE_BILL", "OPENING_BALANCE"]

    entries = await db.dc_ledger_entries.find(
        {"tenant_id": tenant, "party_type": party_type,
         "voucher_type": {"$in": inv_types},
         "status": {"$nin": ["PAID", "CANCELLED"]},
         "is_deleted": {"$ne": True}},
        {"_id": 0}
    ).to_list(50000)

    entry_ids = [e["id"] for e in entries]
    alloc_map: dict[str, float] = {}
    if entry_ids:
        allocs = await db.dc_payment_allocations.find(
            {"tenant_id": tenant, "invoice_entry_id": {"$in": entry_ids}}, {"_id": 0}
        ).to_list(200000)
        for a in allocs:
            k = a.get("invoice_entry_id", "")
            alloc_map[k] = alloc_map.get(k, 0) + _fmt_rupees(a.get("allocated_amount"))

    rows = []
    for e in entries:
        due_d = _parse_date(e.get("due_date"))
        if not due_d or due_d >= today:
            continue
        days  = (today - due_d).days
        face  = _fmt_rupees(e.get("debit")) or _fmt_rupees(e.get("credit"))
        paid  = alloc_map.get(e["id"], 0.0)
        oust  = max(0.0, face - paid)
        if oust <= 0:
            continue
        interest = round(oust * (interest_rate / 100) * (days / 365), 2)
        rows.append({
            "party_name":    e.get("party_name"),
            "party_id":      e.get("party_id"),
            "voucher_no":    e.get("voucher_no"),
            "entry_date":    e.get("entry_date"),
            "due_date":      e.get("due_date"),
            "outstanding":   oust,
            "overdue_days":  days,
            "interest_rate": interest_rate,
            "interest_amount": interest,
        })

    total_outstanding = sum(r["outstanding"] for r in rows)
    total_interest    = sum(r["interest_amount"] for r in rows)
    rows.sort(key=lambda x: x["interest_amount"], reverse=True)
    return {
        "party_type":       party_type,
        "interest_rate":    interest_rate,
        "as_of_date":       today.isoformat(),
        "rows":             rows,
        "total_outstanding": round(total_outstanding, 2),
        "total_interest":    round(total_interest, 2),
    }


# ─────────────────────────── Integration Hooks ───────────────────────────
# These endpoints are called internally by other routers (sales, purchase,
# banking) after posting a document. They are also exposed for manual use.

class DocPostIn(BaseModel):
    doc_type:     Literal["SALES_INVOICE", "PURCHASE_BILL", "CREDIT_NOTE",
                          "DEBIT_NOTE", "RECEIPT", "PAYMENT",
                          "ADVANCE_RECEIVED", "ADVANCE_PAID",
                          "SALES_RETURN", "PURCHASE_RETURN", "JOURNAL"]
    doc_id:       str
    party_type:   Literal["customer", "vendor"]
    party_id:     str
    entry_date:   str
    due_date:     Optional[str] = None
    amount:       float
    narration:    Optional[str] = None
    branch_id:    Optional[str] = None
    fiscal_year:  Optional[str] = None


async def post_dc_document(data: DocPostIn, *, tenant: str, created_by: str) -> Optional[dict]:
    """Post one dc_ledger_entries row for a document from another module
    (sales, purchase, banking), then recalc that party's balance/status
    in-line — same request/transaction as the caller, not a background task.

    Idempotent on (tenant, source_doc_id, voucher_type): a repost (e.g.
    update_bill re-posting after an edit) returns the existing row instead
    of creating a duplicate ledger entry. Returns None only when
    reposting is genuinely impossible to distinguish (never today — kept
    Optional for symmetry with the other posters in this pipeline).

    Mapping:
        SALES_INVOICE / OPENING_BALANCE(customer) → debit on customer
        RECEIPT / CN / SALES_RETURN                → credit on customer
        PURCHASE_BILL / OPENING_BALANCE(vendor)    → credit on vendor
        PAYMENT / DN / PURCHASE_RETURN             → debit on vendor
    """
    existing = await db.dc_ledger_entries.find_one({
        "tenant_id": tenant, "source_doc_id": data.doc_id, "voucher_type": data.doc_type,
        "is_deleted": {"$ne": True},
    }, {"_id": 0})
    if existing:
        return existing

    debit_types_customer = {"SALES_INVOICE", "DEBIT_NOTE"}
    credit_types_customer = {"RECEIPT", "CREDIT_NOTE", "SALES_RETURN", "ADVANCE_RECEIVED"}
    debit_types_vendor   = {"PAYMENT", "DEBIT_NOTE", "PURCHASE_RETURN", "ADVANCE_PAID"}
    credit_types_vendor  = {"PURCHASE_BILL", "CREDIT_NOTE"}

    if data.party_type == "customer":
        if data.doc_type in debit_types_customer:
            debit, credit = data.amount, 0.0
        elif data.doc_type in credit_types_customer:
            debit, credit = 0.0, data.amount
        else:  # JOURNAL etc — caller specifies sign via negative amount
            if data.amount >= 0:
                debit, credit = data.amount, 0.0
            else:
                debit, credit = 0.0, abs(data.amount)
    else:
        if data.doc_type in credit_types_vendor:
            debit, credit = 0.0, data.amount
        elif data.doc_type in debit_types_vendor:
            debit, credit = data.amount, 0.0
        else:
            if data.amount >= 0:
                debit, credit = 0.0, data.amount
            else:
                debit, credit = abs(data.amount), 0.0

    prefix_map = {
        "SALES_INVOICE":    "SI",  "PURCHASE_BILL":   "PB",
        "RECEIPT":          "RCV", "PAYMENT":         "PAY",
        "CREDIT_NOTE":      "CN",  "DEBIT_NOTE":      "DN",
        "ADVANCE_RECEIVED": "ADR", "ADVANCE_PAID":    "ADP",
        "SALES_RETURN":     "SRN", "PURCHASE_RETURN": "PRN",
        "JOURNAL":          "JV",
    }
    prefix    = prefix_map.get(data.doc_type, "DC")
    voucher_no = await _next_voucher_no(tenant, prefix)
    party_name = await _get_party_name(data.party_type, data.party_id)

    doc = {
        "id":            _new_id(),
        "tenant_id":     tenant,
        "party_type":    data.party_type,
        "party_id":      data.party_id,
        "party_name":    party_name,
        "voucher_type":  data.doc_type,
        "voucher_no":    voucher_no,
        "source_doc_id": data.doc_id,
        "entry_date":    data.entry_date,
        "due_date":      data.due_date or "",
        "debit":         debit,
        "credit":        credit,
        "narration":     data.narration or data.doc_type.replace("_", " ").title(),
        "status":        "OPEN",
        "branch_id":     data.branch_id or "",
        "fiscal_year":   data.fiscal_year or data.entry_date[:4],
        "is_deleted":    False,
        "created_by":    created_by,
        "created_at":    _now_iso(),
        "updated_at":    _now_iso(),
    }
    await db.dc_ledger_entries.insert_one(doc)
    # In-line, not a background task: the caller (e.g. purchase_v2.create_bill)
    # is inside its own request transaction and needs the party's balance to
    # be correct by the time it returns, not eventually-after-response.
    await _recalc_party_balance(tenant, data.party_type, data.party_id)
    await _update_entry_statuses(tenant, data.party_type, data.party_id)
    doc.pop("_id", None)
    return doc


@router.post("/post-document")
async def post_document(data: DocPostIn, user=Depends(get_current_user)):
    """HTTP entry point for the hook above — used when another module posts
    via its own separate request rather than an in-process call within the
    same transaction (see post_dc_document, which already does the balance
    recalc in-line before returning)."""
    _require_dc_write(user)
    tenant = user.get("tenant_id", "default")
    return await post_dc_document(data, tenant=tenant, created_by=user.get("id", ""))


# ─────────────────────────── Search ───────────────────────────

@router.get("/search")
async def dc_search(
    q:          str,
    party_type: Optional[Literal["customer", "vendor"]] = None,
    page:       int = 1,
    limit:      int = 30,
    user=Depends(get_current_user),
):
    _require_dc(user)
    tenant = user.get("tenant_id", "default")
    filt: dict = {
        "tenant_id":  tenant,
        "is_deleted": {"$ne": True},
        "$or": [
            {"party_name": {"$regex": q}},
            {"voucher_no": {"$regex": q}},
            {"source_doc_id": {"$regex": q}},
            {"narration": {"$regex": q}},
        ]
    }
    if party_type:
        filt["party_type"] = party_type

    total = await db.dc_ledger_entries.count_documents(filt)
    items = await db.dc_ledger_entries.find(filt, {"_id": 0}).to_list(limit)
    return {"total": total, "page": page, "limit": limit, "items": items}


# ─────────────────────────── Recalculate (admin utility) ───────────────────────────

@router.post("/admin/recalc-all-balances")
async def recalc_all_balances(bg: BackgroundTasks, user=Depends(require_admin)):
    tenant = user.get("tenant_id", "default")
    entries = await db.dc_ledger_entries.find(
        {"tenant_id": tenant, "is_deleted": {"$ne": True}},
        {"party_type": 1, "party_id": 1}
    ).to_list(100000)
    seen: set[tuple] = set()
    count = 0
    for e in entries:
        key = (e.get("party_type", ""), e.get("party_id", ""))
        if key in seen:
            continue
        seen.add(key)
        bg.add_task(_recalc_party_balance, tenant, key[0], key[1])
        bg.add_task(_update_entry_statuses, tenant, key[0], key[1])
        count += 1
    return {"queued": count, "message": f"Recalculating balances for {count} parties in background"}
