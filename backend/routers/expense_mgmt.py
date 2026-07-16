"""Expense Management Router.

Features:
- Expense categories (CRUD)
- Expense entries with approval workflow
- Department-wise expenses
- Recurring expense setup
- Expense analytics
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from core.accounting_models import ExpenseCategory, ExpenseEntry, ExpenseUpdate
from core.auth_utils import get_current_user, require_admin, is_admin_role
from core.db import db

router = APIRouter(prefix="/expenses", tags=["Expenses"])


def _require_expense(user: dict):
    if (is_admin_role(user.get("role")) or user.get("role") in ("hr", "accountant")):
        return user
    perms = user.get("module_permissions", [])
    if "expenses" not in perms and "accounting" not in perms:
        raise HTTPException(403, "Expense module access required")
    return user


# ─────────────────────────── Expense Categories ───────────────────────────

@router.get("/categories")
async def list_categories(user=Depends(get_current_user)):
    _require_expense(user)
    cats = await db.expense_categories.find({}, {"_id": 0}).sort("name", 1).to_list(100)
    return cats


@router.post("/categories")
async def create_category(data: ExpenseCategory, user=Depends(require_admin)):
    existing = await db.expense_categories.find_one({"name": data.name})
    if existing:
        raise HTTPException(400, "Category already exists")
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.expense_categories.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/categories/{cat_id}")
async def update_category(cat_id: str, data: ExpenseCategory, user=Depends(require_admin)):
    upd = data.model_dump()
    await db.expense_categories.update_one({"id": cat_id}, {"$set": upd})
    return {"ok": True}


@router.delete("/categories/{cat_id}")
async def delete_category(cat_id: str, user=Depends(require_admin)):
    await db.expense_categories.delete_one({"id": cat_id})
    return {"ok": True}


# ─────────────────────────── Expense Entries ───────────────────────────

@router.get("")
async def list_expenses(
    status: Optional[str] = None,
    category: Optional[str] = None,
    department: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    user=Depends(get_current_user)
):
    _require_expense(user)
    q: dict = {}
    if status:
        q["status"] = status
    if category:
        q["category"] = category
    if department:
        q["department"] = department
    if from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date
    if search:
        q["$or"] = [
            {"description": {"$regex": search, "$options": "i"}},
            {"category": {"$regex": search, "$options": "i"}},
        ]
    total = await db.expense_entries.count_documents(q)
    skip = (page - 1) * limit
    items = await db.expense_entries.find(q, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "page": page, "items": items}


@router.post("")
async def create_expense(data: ExpenseEntry, user=Depends(get_current_user)):
    _require_expense(user)
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["submitted_by"] = user["id"]
    doc["submitted_by_name"] = user.get("name", "")
    doc["created_at"] = datetime.now(timezone.utc).isoformat()

    # Admin expenses are auto-approved
    if is_admin_role(user.get("role")):
        doc["status"] = "APPROVED"
        doc["approved_by"] = user["id"]
        doc["approved_at"] = datetime.now(timezone.utc).isoformat()

    await db.expense_entries.insert_one(doc)

    if is_admin_role(user.get("role")):
        await _create_expense_journal(doc, user)

    doc.pop("_id", None)
    return doc


# NOTE: Analytics routes MUST come before /{expense_id} so FastAPI matches
# the literal path "/analytics/..." before trying to match "analytics" as
# an expense_id parameter.

@router.get("/analytics/summary")
async def expense_analytics(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_expense(user)
    q: dict = {"status": "APPROVED"}
    if from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date

    # By category
    by_category = await db.expense_entries.aggregate([
        {"$match": q},
        {"$group": {
            "_id": "$category",
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"total": -1}},
    ]).to_list(50)

    # By department
    by_department = await db.expense_entries.aggregate([
        {"$match": q},
        {"$group": {
            "_id": "$department",
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"total": -1}},
    ]).to_list(50)

    # Monthly trend
    monthly = await db.expense_entries.aggregate([
        {"$match": q},
        {"$group": {
            "_id": {"$substr": ["$date", 0, 7]},
            "total": {"$sum": "$amount"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]).to_list(24)

    total_approved = sum(r["total"] for r in by_category)
    pending_count = await db.expense_entries.count_documents({"status": "PENDING"})

    return {
        "total_approved": round(total_approved, 2),
        "pending_count": pending_count,
        "by_category": by_category,
        "by_department": by_department,
        "monthly_trend": monthly,
    }


@router.get("/analytics/recurring")
async def recurring_expenses(user=Depends(get_current_user)):
    _require_expense(user)
    items = await db.expense_entries.find(
        {"is_recurring": True},
        {"_id": 0}
    ).sort("date", -1).to_list(100)
    return items


@router.get("/{expense_id}")
async def get_expense(expense_id: str, user=Depends(get_current_user)):
    _require_expense(user)
    e = await db.expense_entries.find_one({"id": expense_id}, {"_id": 0})
    if not e:
        raise HTTPException(404, "Expense not found")
    return e


@router.patch("/{expense_id}")
async def update_expense(expense_id: str, data: ExpenseUpdate, user=Depends(get_current_user)):
    e = await db.expense_entries.find_one({"id": expense_id})
    if not e:
        raise HTTPException(404, "Not found")

    # Only admin/manager can approve/reject
    if data.status in ("APPROVED", "REJECTED"):
        if not is_admin_role(user.get("role")) and user.get("role") != "hr":
            raise HTTPException(403, "Only admin or HR can approve/reject expenses")

    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    if data.status in ("APPROVED", "REJECTED"):
        upd["approved_by"] = user["id"]
        upd["approved_by_name"] = user.get("name", "")
        upd["approved_at"] = datetime.now(timezone.utc).isoformat()

    await db.expense_entries.update_one({"id": expense_id}, {"$set": upd})

    # Auto-create journal entry for approved expenses
    if data.status == "APPROVED":
        updated = await db.expense_entries.find_one({"id": expense_id}, {"_id": 0})
        if updated:
            await _create_expense_journal(updated, user)

    return {"ok": True}


@router.delete("/{expense_id}")
async def delete_expense(expense_id: str, user=Depends(require_admin)):
    await db.expense_entries.delete_one({"id": expense_id})
    return {"ok": True}


async def _create_expense_journal(expense: dict, user: dict):
    """Create an auto journal entry for an approved expense."""
    import uuid as _uuid
    from datetime import date as _date

    fy = await db.fiscal_years.find_one({"is_active": True})
    fy_name = fy["name"] if fy else _date.today().strftime("%Y-%y")
    count = await db.journal_entries.count_documents({"fiscal_year": fy_name})

    # Map category to expense GL account
    category_accounts = {
        "Rent": "5004",
        "Utilities": "5005",
        "Transport": "5006",
        "Marketing": "5007",
        "Office Supplies": "5008",
        "Bank Charges": "5009",
    }
    expense_code = category_accounts.get(expense.get("category", ""), "5011")
    mode = expense.get("payment_mode", "CASH")
    cash_code = "1001" if mode == "CASH" else "1002"
    cash_name = "Cash in Hand" if mode == "CASH" else "Bank Account - Primary"

    entry = {
        "id": str(_uuid.uuid4()),
        "entry_number": f"JE/{fy_name}/{str(count + 1).zfill(5)}",
        "date": expense.get("date"),
        "narration": f"Expense: {expense.get('description', '')} | {expense.get('category', '')}",
        "lines": [
            {"account_code": expense_code, "account_name": expense.get("category", "Expense"), "debit": expense["amount"], "credit": 0},
            {"account_code": cash_code, "account_name": cash_name, "debit": 0, "credit": expense["amount"]},
        ],
        "status": "POSTED",
        "fiscal_year": fy_name,
        "reference": expense["id"],
        "created_by": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_debit": expense["amount"],
        "total_credit": expense["amount"],
    }
    await db.journal_entries.insert_one(entry)
