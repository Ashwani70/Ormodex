"""Banking module — Bank Reconciliation, Cheque Management, Statement Entries.

Features:
- Manual bank statement entry (line by line)
- Auto-match statement lines against journal entries / vouchers
- Cheque register (issued / received / bounced)
- Unreconciled items report
- Bank reconciliation summary
"""
import uuid
from datetime import datetime, date, timezone
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.auth_utils import get_current_user, require_admin
from core.db import db

router = APIRouter(prefix="/banking", tags=["Banking"])


def _require_banking(user: dict):
    if user.get("role") in ("admin", "accountant"):
        return user
    perms = user.get("module_permissions", [])
    if "accounting" not in perms and "banking" not in perms:
        raise HTTPException(403, "Banking module access required")
    return user


# ─────────────────────── Pydantic Models ───────────────────────

class BankStatementLine(BaseModel):
    bank_account_code: str          # CoA account code e.g. "1002"
    bank_account_name: Optional[str] = None
    transaction_date: str           # ISO date
    value_date: Optional[str] = None
    description: str
    ref_number: Optional[str] = None  # cheque / UTR / NEFT ref
    debit: float = 0.0              # Money going out of bank
    credit: float = 0.0             # Money coming into bank
    source: Literal["MANUAL", "IMPORT"] = "MANUAL"


class BankStatementUpdate(BaseModel):
    description: Optional[str] = None
    ref_number: Optional[str] = None
    debit: Optional[float] = None
    credit: Optional[float] = None
    is_reconciled: Optional[bool] = None
    matched_entry_id: Optional[str] = None


class ChequeEntry(BaseModel):
    cheque_number: str
    bank_account_code: str
    cheque_type: Literal["ISSUED", "RECEIVED"]
    party_name: str
    amount: float
    cheque_date: str
    due_date: Optional[str] = None
    status: Literal["PENDING", "CLEARED", "BOUNCED", "CANCELLED"] = "PENDING"
    linked_voucher_id: Optional[str] = None
    remarks: Optional[str] = None


class ChequeUpdate(BaseModel):
    status: Optional[Literal["PENDING", "CLEARED", "BOUNCED", "CANCELLED"]] = None
    remarks: Optional[str] = None
    cleared_date: Optional[str] = None


# ─────────────────────── Bank Statement Endpoints ───────────────────────

@router.get("/statements")
async def list_bank_statements(
    bank_account_code: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    is_reconciled: Optional[bool] = None,
    page: int = 1,
    limit: int = 100,
    user=Depends(get_current_user)
):
    _require_banking(user)
    q: dict = {}
    if bank_account_code:
        q["bank_account_code"] = bank_account_code
    if from_date or to_date:
        q["transaction_date"] = {}
        if from_date:
            q["transaction_date"]["$gte"] = from_date
        if to_date:
            q["transaction_date"]["$lte"] = to_date
    if is_reconciled is not None:
        q["is_reconciled"] = is_reconciled
    total = await db.bank_statements.count_documents(q)
    skip = (page - 1) * limit
    items = await db.bank_statements.find(q, {"_id": 0}).sort("transaction_date", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "page": page, "items": items}


@router.post("/statements")
async def create_bank_statement_line(data: BankStatementLine, user=Depends(get_current_user)):
    _require_banking(user)
    # Fetch account name from CoA if not provided
    account_name = data.bank_account_name
    if not account_name:
        acc = await db.chart_of_accounts.find_one({"code": data.bank_account_code}, {"_id": 0, "name": 1})
        account_name = acc["name"] if acc else data.bank_account_code
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["bank_account_name"] = account_name
    doc["is_reconciled"] = False
    doc["matched_entry_id"] = None
    doc["created_by"] = user["id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.bank_statements.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/statements/{stmt_id}")
async def update_bank_statement_line(stmt_id: str, data: BankStatementUpdate, user=Depends(get_current_user)):
    _require_banking(user)
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.bank_statements.update_one({"id": stmt_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Statement line not found")
    return {"ok": True}


@router.delete("/statements/{stmt_id}")
async def delete_bank_statement_line(stmt_id: str, user=Depends(require_admin)):
    await db.bank_statements.delete_one({"id": stmt_id})
    return {"ok": True}


# ─────────────────────── Auto-Reconciliation ───────────────────────

@router.post("/reconcile/auto-match")
async def auto_reconcile(
    bank_account_code: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    """Auto-match unreconciled statement lines against posted journal entries by amount and date proximity."""
    _require_banking(user)

    q_stmt: dict = {"bank_account_code": bank_account_code, "is_reconciled": False}
    if from_date or to_date:
        q_stmt["transaction_date"] = {}
        if from_date:
            q_stmt["transaction_date"]["$gte"] = from_date
        if to_date:
            q_stmt["transaction_date"]["$lte"] = to_date

    stmt_lines = await db.bank_statements.find(q_stmt, {"_id": 0}).to_list(1000)

    # Build journal entries index for this account code
    q_je: dict = {"lines.account_code": bank_account_code, "status": "POSTED"}
    if from_date or to_date:
        q_je["date"] = {}
        if from_date:
            q_je["date"]["$gte"] = from_date
        if to_date:
            q_je["date"]["$lte"] = to_date

    journal_entries = await db.journal_entries.find(q_je, {"_id": 0}).to_list(5000)

    # Index journal entries by amount
    je_by_amount: dict = {}
    for je in journal_entries:
        for line in je.get("lines", []):
            if line["account_code"] == bank_account_code:
                net = round(line.get("debit", 0) - line.get("credit", 0), 2)
                key = abs(net)
                if key not in je_by_amount:
                    je_by_amount[key] = []
                je_by_amount[key].append({"je_id": je["id"], "net": net, "date": je["date"], "narration": je.get("narration", "")})

    matched_count = 0
    for stmt in stmt_lines:
        # Net from bank statement perspective (credit = inflow, debit = outflow)
        stmt_net = round(stmt.get("credit", 0) - stmt.get("debit", 0), 2)
        lookup_key = abs(stmt_net)
        candidates = je_by_amount.get(lookup_key, [])
        if candidates:
            best = candidates[0]  # Take first match
            await db.bank_statements.update_one(
                {"id": stmt["id"]},
                {"$set": {
                    "is_reconciled": True,
                    "matched_entry_id": best["je_id"],
                    "matched_narration": best["narration"],
                    "reconciled_at": datetime.now(timezone.utc).isoformat(),
                    "reconciled_by": user["id"],
                }}
            )
            je_by_amount[lookup_key].pop(0)  # Remove used entry
            matched_count += 1

    total_unreconciled = await db.bank_statements.count_documents(
        {"bank_account_code": bank_account_code, "is_reconciled": False}
    )
    return {
        "matched": matched_count,
        "unmatched": total_unreconciled,
        "message": f"Auto-matched {matched_count} statement lines"
    }


@router.get("/reconcile/report")
async def reconciliation_report(
    bank_account_code: str,
    as_of_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    """Generate a bank reconciliation statement."""
    _require_banking(user)
    cutoff = as_of_date or date.today().isoformat()

    # Bank balance per statement
    stmt_q = {"bank_account_code": bank_account_code, "transaction_date": {"$lte": cutoff}}
    stmt_lines = await db.bank_statements.find(stmt_q, {"_id": 0}).to_list(5000)
    bank_credits = sum(s.get("credit", 0) for s in stmt_lines)
    bank_debits = sum(s.get("debit", 0) for s in stmt_lines)
    bank_balance = round(bank_credits - bank_debits, 2)

    # Book balance per journal entries
    je_q = {"lines.account_code": bank_account_code, "status": "POSTED", "date": {"$lte": cutoff}}
    journal_entries = await db.journal_entries.find(je_q, {"_id": 0}).to_list(5000)
    book_balance = 0.0
    for je in journal_entries:
        for line in je.get("lines", []):
            if line["account_code"] == bank_account_code:
                book_balance += line.get("debit", 0) - line.get("credit", 0)
    book_balance = round(book_balance, 2)

    # Unreconciled items
    unreconciled = await db.bank_statements.find(
        {**stmt_q, "is_reconciled": False}, {"_id": 0}
    ).to_list(1000)

    unreconciled_total = sum(s.get("credit", 0) - s.get("debit", 0) for s in unreconciled)

    return {
        "bank_account_code": bank_account_code,
        "as_of_date": cutoff,
        "bank_balance": bank_balance,
        "book_balance": book_balance,
        "difference": round(bank_balance - book_balance, 2),
        "unreconciled_count": len(unreconciled),
        "unreconciled_total": round(unreconciled_total, 2),
        "unreconciled_items": unreconciled[:50],  # First 50
        "is_reconciled": abs(bank_balance - book_balance) < 0.01,
    }


# ─────────────────────── Cheque Management ───────────────────────

@router.get("/cheques")
async def list_cheques(
    cheque_type: Optional[str] = None,
    status: Optional[str] = None,
    bank_account_code: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    user=Depends(get_current_user)
):
    _require_banking(user)
    q: dict = {}
    if cheque_type:
        q["cheque_type"] = cheque_type
    if status:
        q["status"] = status
    if bank_account_code:
        q["bank_account_code"] = bank_account_code
    total = await db.cheques.count_documents(q)
    skip = (page - 1) * limit
    items = await db.cheques.find(q, {"_id": 0}).sort("cheque_date", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "page": page, "items": items}


@router.post("/cheques")
async def create_cheque(data: ChequeEntry, user=Depends(get_current_user)):
    _require_banking(user)
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_by"] = user["id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.cheques.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/cheques/{cheque_id}")
async def update_cheque(cheque_id: str, data: ChequeUpdate, user=Depends(get_current_user)):
    _require_banking(user)
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.cheques.update_one({"id": cheque_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Cheque not found")
    return {"ok": True}


@router.delete("/cheques/{cheque_id}")
async def delete_cheque(cheque_id: str, user=Depends(require_admin)):
    await db.cheques.delete_one({"id": cheque_id})
    return {"ok": True}


# ─────────────────────── Banking Dashboard ───────────────────────

@router.get("/dashboard")
async def banking_dashboard(user=Depends(get_current_user)):
    _require_banking(user)
    # Cheque stats
    pending_cheques = await db.cheques.count_documents({"status": "PENDING"})
    bounced_cheques = await db.cheques.count_documents({"status": "BOUNCED"})
    # Unreconciled items
    unreconciled_count = await db.bank_statements.count_documents({"is_reconciled": False})
    # Recent cheques
    recent_cheques = await db.cheques.find({}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
    # Recent statement lines
    recent_stmts = await db.bank_statements.find({}, {"_id": 0}).sort("transaction_date", -1).limit(5).to_list(5)
    return {
        "pending_cheques": pending_cheques,
        "bounced_cheques": bounced_cheques,
        "unreconciled_count": unreconciled_count,
        "recent_cheques": recent_cheques,
        "recent_statements": recent_stmts,
    }
