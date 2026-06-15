"""Ledger Management Router.

Covers:
- Party ledger (customer/supplier outstanding)
- Ledger ageing report
- Bank account management
- Bank entries (debit/credit)
- Bank statement import + reconciliation
- Bank reconciliation matching
"""
import uuid
from datetime import datetime, date, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.accounting_models import (
    BankAccount, BankEntry, BankStatementLine, ReconcileMatch,
)
from core.auth_utils import get_current_user, require_admin
from core.db import db

router = APIRouter(prefix="/ledger", tags=["Ledger"])


def _require_ledger(user: dict):
    if user.get("role") == "admin":
        return user
    perms = user.get("module_permissions", [])
    if not any(p in perms for p in ("ledger", "accounting", "cash_bank")):
        raise HTTPException(403, "Ledger module access required")
    return user


# ─────────────────────────── Bank Accounts ───────────────────────────

@router.get("/bank-accounts")
async def list_bank_accounts(user=Depends(get_current_user)):
    _require_ledger(user)
    accounts = await db.bank_accounts.find({}, {"_id": 0}).sort("name", 1).to_list(100)
    return accounts


@router.post("/bank-accounts")
async def create_bank_account(data: BankAccount, user=Depends(require_admin)):
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["current_balance"] = data.opening_balance
    await db.bank_accounts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/bank-accounts/{account_id}")
async def update_bank_account(account_id: str, data: dict, user=Depends(require_admin)):
    await db.bank_accounts.update_one({"id": account_id}, {"$set": data})
    return {"ok": True}


# ─────────────────────────── Bank Entries ───────────────────────────

@router.get("/bank-entries")
async def list_bank_entries(
    bank_account_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    is_reconciled: Optional[bool] = None,
    page: int = 1,
    limit: int = 50,
    user=Depends(get_current_user)
):
    _require_ledger(user)
    q: dict = {}
    if bank_account_id:
        q["bank_account_id"] = bank_account_id
    if from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date
    if is_reconciled is not None:
        q["is_reconciled"] = is_reconciled
    total = await db.bank_entries.count_documents(q)
    skip = (page - 1) * limit
    items = await db.bank_entries.find(q, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "page": page, "items": items}


@router.post("/bank-entries")
async def create_bank_entry(data: BankEntry, user=Depends(get_current_user)):
    _require_ledger(user)
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_by"] = user["id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.bank_entries.insert_one(doc)

    # Update bank account balance
    delta = data.amount if data.entry_type == "CREDIT" else -data.amount
    await db.bank_accounts.update_one(
        {"id": data.bank_account_id},
        {"$inc": {"current_balance": delta}}
    )

    doc.pop("_id", None)
    return doc


# ─────────────────────────── Bank Statement Import ───────────────────────────

@router.get("/bank-statement")
async def list_statement_lines(
    bank_account_id: str = Query(...),
    is_matched: Optional[bool] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_ledger(user)
    q: dict = {"bank_account_id": bank_account_id}
    if is_matched is not None:
        q["is_matched"] = is_matched
    if from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date
    items = await db.bank_statement_lines.find(q, {"_id": 0}).sort("date", 1).to_list(1000)
    return items


@router.post("/bank-statement/import")
async def import_statement_lines(lines: list[BankStatementLine], user=Depends(get_current_user)):
    _require_ledger(user)
    docs = []
    for line in lines:
        doc = line.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["imported_at"] = datetime.now(timezone.utc).isoformat()
        doc["imported_by"] = user["id"]
        docs.append(doc)
    if docs:
        await db.bank_statement_lines.insert_many(docs)
    return {"imported": len(docs)}


@router.post("/bank-statement/reconcile")
async def reconcile_entry(data: ReconcileMatch, user=Depends(get_current_user)):
    _require_ledger(user)
    await db.bank_statement_lines.update_one(
        {"id": data.statement_line_id},
        {"$set": {"is_matched": True, "matched_entry_id": data.bank_entry_id, "matched_at": datetime.now(timezone.utc).isoformat()}}
    )
    await db.bank_entries.update_one(
        {"id": data.bank_entry_id},
        {"$set": {"is_reconciled": True, "statement_line_id": data.statement_line_id}}
    )
    return {"ok": True}


@router.post("/bank-statement/unmatch/{statement_line_id}")
async def unmatch_statement_line(statement_line_id: str, user=Depends(get_current_user)):
    _require_ledger(user)
    line = await db.bank_statement_lines.find_one({"id": statement_line_id})
    if not line:
        raise HTTPException(404, "Statement line not found")
    if line.get("matched_entry_id"):
        await db.bank_entries.update_one(
            {"id": line["matched_entry_id"]},
            {"$set": {"is_reconciled": False}}
        )
    await db.bank_statement_lines.update_one(
        {"id": statement_line_id},
        {"$set": {"is_matched": False, "matched_entry_id": None}}
    )
    return {"ok": True}


# ─────────────────────────── Party Ledger (Customer/Supplier) ───────────────────────────

@router.get("/party-ledger")
async def party_ledger(
    party_type: str = Query(..., regex="^(CUSTOMER|SUPPLIER)$"),
    party_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_ledger(user)
    q: dict = {"party_type": party_type, "status": "APPROVED"}
    if party_id:
        q["party_id"] = party_id
    if from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date

    vouchers = await db.vouchers.find(q, {"_id": 0}).sort("date", 1).to_list(2000)

    # Also get invoices / purchase orders
    if party_type == "CUSTOMER":
        invoices = await db.invoices.find(
            {"customer_id": party_id} if party_id else {},
            {"_id": 0}
        ).sort("created_at", 1).to_list(1000)
    else:
        invoices = await db.purchase_orders.find(
            {"supplier_id": party_id} if party_id else {},
            {"_id": 0}
        ).sort("created_at", 1).to_list(1000)

    return {"vouchers": vouchers, "invoices": invoices}


@router.get("/party-outstanding")
async def party_outstanding(
    party_type: str = Query(..., regex="^(CUSTOMER|SUPPLIER)$"),
    user=Depends(get_current_user)
):
    _require_ledger(user)
    if party_type == "CUSTOMER":
        collection = db.invoices
        party_field = "customer_id"
        name_field = "customer_name"
    else:
        collection = db.purchase_orders
        party_field = "supplier_id"
        name_field = "supplier_name"

    pipeline = [
        {"$group": {
            "_id": f"${party_field}",
            "party_name": {"$first": f"${name_field}"},
            "total_amount": {"$sum": "$total"},
            "paid_amount": {"$sum": "$payment_received"},
            "count": {"$sum": 1},
        }},
        {"$addFields": {"outstanding": {"$subtract": ["$total_amount", "$paid_amount"]}}},
        {"$sort": {"outstanding": -1}},
    ]
    results = await collection.aggregate(pipeline).to_list(200)
    return results


# ─────────────────────────── Ledger Ageing Report ───────────────────────────

@router.get("/ageing-report")
async def ageing_report(
    party_type: str = Query(..., regex="^(CUSTOMER|SUPPLIER)$"),
    as_of_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_ledger(user)
    today = date.fromisoformat(as_of_date) if as_of_date else date.today()

    if party_type == "CUSTOMER":
        collection = db.invoices
        q = {"status": {"$in": ["UNPAID", "PARTIAL"]}}
    else:
        collection = db.purchase_orders
        q = {"status": {"$in": ["SENT", "RECEIVED"]}}

    docs = await collection.find(q, {"_id": 0}).to_list(2000)

    buckets = {"0-30": [], "31-60": [], "61-90": [], "90+": []}
    for doc in docs:
        try:
            doc_date = date.fromisoformat(doc.get("created_at", "")[:10])
            age = (today - doc_date).days
        except Exception:
            age = 0

        outstanding = doc.get("total", 0) - doc.get("payment_received", 0)
        entry = {
            "id": doc.get("id"),
            "party_name": doc.get("customer_name") or doc.get("supplier_name", ""),
            "invoice_no": doc.get("invoice_number") or doc.get("po_number", ""),
            "date": doc.get("created_at", "")[:10],
            "age_days": age,
            "outstanding": round(outstanding, 2),
        }

        if age <= 30:
            buckets["0-30"].append(entry)
        elif age <= 60:
            buckets["31-60"].append(entry)
        elif age <= 90:
            buckets["61-90"].append(entry)
        else:
            buckets["90+"].append(entry)

    totals = {k: round(sum(e["outstanding"] for e in v), 2) for k, v in buckets.items()}
    return {"buckets": buckets, "totals": totals, "as_of_date": today.isoformat()}
