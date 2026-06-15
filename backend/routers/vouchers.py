"""Voucher Management Router.

Handles: Receipt, Payment, Contra, Journal, Debit Note, Credit Note, Expense vouchers.
Includes: auto-numbering, approval workflow, party linkage.
"""
import uuid
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.accounting_models import Voucher, VoucherUpdate, VoucherType
from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.utils import log_audit, now_iso

router = APIRouter(prefix="/vouchers", tags=["Vouchers"])


def _require_voucher(user: dict):
    if user.get("role") == "admin":
        return user
    perms = user.get("module_permissions", [])
    if "vouchers" not in perms and "accounting" not in perms:
        raise HTTPException(403, "Voucher module access required")
    return user


async def _next_voucher_number(voucher_type: str) -> str:
    fy = await db.fiscal_years.find_one({"is_active": True})
    fy_name = fy["name"] if fy else date.today().strftime("%Y-%y")
    prefix_map = {
        "RECEIPT": "RV", "PAYMENT": "PV", "CONTRA": "CV",
        "JOURNAL": "JV", "DEBIT_NOTE": "DN", "CREDIT_NOTE": "CN", "EXPENSE": "EV",
    }
    p = prefix_map.get(voucher_type, "VCH")
    count = await db.vouchers.count_documents({"voucher_type": voucher_type, "fiscal_year": fy_name})
    return f"{p}/{fy_name}/{str(count + 1).zfill(5)}"


@router.get("")
async def list_vouchers(
    voucher_type: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    party_id: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    user=Depends(get_current_user)
):
    _require_voucher(user)
    q: dict = {}
    if voucher_type:
        q["voucher_type"] = voucher_type
    if status:
        q["status"] = status
    if from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date
    if party_id:
        q["party_id"] = party_id
    if search:
        q["$or"] = [
            {"voucher_number": {"$regex": search, "$options": "i"}},
            {"party_name": {"$regex": search, "$options": "i"}},
            {"narration": {"$regex": search, "$options": "i"}},
        ]
    total = await db.vouchers.count_documents(q)
    skip = (page - 1) * limit
    items = await db.vouchers.find(q, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "page": page, "items": items}


@router.post("")
async def create_voucher(data: Voucher, user=Depends(get_current_user)):
    _require_voucher(user)
    fy = await db.fiscal_years.find_one({"is_active": True})
    fy_name = fy["name"] if fy else date.today().strftime("%Y-%y")

    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["voucher_number"] = await _next_voucher_number(data.voucher_type)
    doc["fiscal_year"] = fy_name
    doc["created_by"] = user["id"]
    doc["created_by_name"] = user.get("name", "")
    doc["created_at"] = now_iso()

    # Auto-post for non-approval workflow (for admin)
    if user.get("role") == "admin" and doc["status"] == "DRAFT":
        doc["status"] = "APPROVED"

    await db.vouchers.insert_one(doc)
    doc.pop("_id", None)

    await log_audit("CREATE", "vouchers", doc["id"], user, new_values=doc)

    # Create linked journal entry automatically for approved vouchers
    if doc["status"] == "APPROVED":
        await _auto_create_journal(doc, user)

    return doc


# NOTE: This route MUST come before /{voucher_id} to avoid "summary" being
# interpreted as a voucher ID.
@router.get("/summary/stats")
async def voucher_stats(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_voucher(user)
    q: dict = {"status": "APPROVED"}
    if from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date

    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": "$voucher_type",
            "count": {"$sum": 1},
            "total_amount": {"$sum": "$amount"},
        }},
    ]
    results = await db.vouchers.aggregate(pipeline).to_list(20)
    return {"by_type": results}


@router.get("/{voucher_id}")
async def get_voucher(voucher_id: str, user=Depends(get_current_user)):
    _require_voucher(user)
    v = await db.vouchers.find_one({"id": voucher_id}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Voucher not found")
    return v


@router.patch("/{voucher_id}")
async def update_voucher(voucher_id: str, data: VoucherUpdate, user=Depends(get_current_user)):
    _require_voucher(user)
    v = await db.vouchers.find_one({"id": voucher_id})
    if not v:
        raise HTTPException(404, "Not found")
    if v.get("status") == "CANCELLED":
        raise HTTPException(400, "Cannot modify cancelled voucher")

    upd = {k: val for k, val in data.model_dump().items() if val is not None}
    upd["updated_at"] = now_iso()
    upd["updated_by"] = user["id"]

    old_values = await db.vouchers.find_one({"id": voucher_id}, {"_id": 0})

    await db.vouchers.update_one({"id": voucher_id}, {"$set": upd})

    new_values = await db.vouchers.find_one({"id": voucher_id}, {"_id": 0})
    await log_audit("UPDATE", "vouchers", voucher_id, user, old_values=old_values, new_values=new_values)

    # If newly approved, create journal entry
    if new_values and upd.get("status") == "APPROVED" and v.get("status") != "APPROVED":
        await _auto_create_journal(new_values, user)

    return {"ok": True}


@router.delete("/{voucher_id}")
async def cancel_voucher(voucher_id: str, user=Depends(require_admin)):
    v = await db.vouchers.find_one({"id": voucher_id})
    if not v:
        raise HTTPException(404, "Not found")

    old_values = await db.vouchers.find_one({"id": voucher_id}, {"_id": 0})

    await db.vouchers.update_one(
        {"id": voucher_id},
        {"$set": {"status": "CANCELLED", "cancelled_by": user["id"], "cancelled_at": now_iso()}}
    )

    new_values = await db.vouchers.find_one({"id": voucher_id}, {"_id": 0})
    await log_audit("DELETE", "vouchers", voucher_id, user, old_values=old_values, new_values=new_values)

    return {"ok": True}


async def _auto_create_journal(voucher: dict, user: dict):
    """Auto-generate a balanced journal entry from an approved voucher."""
    lines = []
    vtype = voucher.get("voucher_type")
    amount = voucher.get("amount", 0)
    party = voucher.get("party_name", "Party")
    mode = voucher.get("payment_mode", "CASH")

    # Simple default mappings (can be customized via CoA)
    cash_acc = {"code": "1001", "name": "Cash in Hand"}
    bank_acc = {"code": "1002", "name": "Bank Account - Primary"}
    recv_acc = {"code": "1100", "name": "Accounts Receivable"}
    pay_acc = {"code": "2001", "name": "Accounts Payable"}
    debit_acc = cash_acc if mode == "CASH" else bank_acc

    if vtype == "RECEIPT":
        lines = [
            {"account_code": debit_acc["code"], "account_name": debit_acc["name"], "debit": amount, "credit": 0},
            {"account_code": recv_acc["code"], "account_name": recv_acc["name"], "debit": 0, "credit": amount},
        ]
    elif vtype == "PAYMENT":
        lines = [
            {"account_code": pay_acc["code"], "account_name": pay_acc["name"], "debit": amount, "credit": 0},
            {"account_code": debit_acc["code"], "account_name": debit_acc["name"], "debit": 0, "credit": amount},
        ]
    elif vtype == "CONTRA":
        lines = [
            {"account_code": bank_acc["code"], "account_name": bank_acc["name"], "debit": amount, "credit": 0},
            {"account_code": cash_acc["code"], "account_name": cash_acc["name"], "debit": 0, "credit": amount},
        ]
    elif vtype in ("DEBIT_NOTE", "CREDIT_NOTE", "EXPENSE", "JOURNAL"):
        # Use user-defined lines or skip auto-journal
        if not voucher.get("lines"):
            return

    if not lines and voucher.get("lines"):
        lines = voucher["lines"]

    if not lines:
        return

    fy = await db.fiscal_years.find_one({"is_active": True})
    fy_name = fy["name"] if fy else date.today().strftime("%Y-%y")
    count = await db.journal_entries.count_documents({"fiscal_year": fy_name})

    entry = {
        "id": str(uuid.uuid4()),
        "entry_number": f"JE/{fy_name}/{str(count + 1).zfill(5)}",
        "date": voucher.get("date"),
        "narration": f"Auto: {vtype} | {party} | {voucher.get('voucher_number', '')}",
        "lines": lines,
        "status": "POSTED",
        "fiscal_year": fy_name,
        "reference": voucher.get("voucher_number"),
        "created_by": user["id"],
        "created_at": now_iso(),
        "total_debit": amount,
        "total_credit": amount,
    }
    await db.journal_entries.insert_one(entry)
    await db.vouchers.update_one(
        {"id": voucher["id"]},
        {"$set": {"journal_entry_id": entry["id"]}}
    )
