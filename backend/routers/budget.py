"""Budget & Cost Centers module.

Features:
- Cost Center CRUD (departments/projects to track expenses against)
- Profit Centers CRUD
- Budget creation per fiscal year & cost center / account
- Budget vs Actual variance report
- Budget alert endpoint (accounts exceeding budget)
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth_utils import get_current_user, require_admin, is_admin_role
from core.db import db

router = APIRouter(prefix="/budget", tags=["Budget & Cost Centers"])


def _require_budget(user: dict):
    if (is_admin_role(user.get("role")) or user.get("role") == "accountant"):
        return user
    raise HTTPException(403, "Budget module access required")


# ─────────────────────── Pydantic Models ───────────────────────

class CostCenter(BaseModel):
    code: str
    name: str
    center_type: Literal["COST", "PROFIT"] = "COST"
    parent_code: Optional[str] = None
    manager: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True


class CostCenterUpdate(BaseModel):
    name: Optional[str] = None
    manager: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class BudgetLine(BaseModel):
    account_code: str
    account_name: Optional[str] = None
    budgeted_amount: float
    cost_center_code: Optional[str] = None


class Budget(BaseModel):
    name: str
    fiscal_year: str               # e.g. "2024-25"
    budget_type: Literal["INCOME", "EXPENSE", "CAPEX"] = "EXPENSE"
    period: Literal["ANNUAL", "QUARTERLY", "MONTHLY"] = "ANNUAL"
    period_label: Optional[str] = None   # e.g. "Q1", "Apr 2024"
    cost_center_code: Optional[str] = None
    lines: List[BudgetLine]
    notes: Optional[str] = None
    status: Literal["DRAFT", "APPROVED", "CLOSED"] = "DRAFT"


class BudgetUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[Literal["DRAFT", "APPROVED", "CLOSED"]] = None
    lines: Optional[List[BudgetLine]] = None


# ─────────────────────── Cost Centers ───────────────────────

@router.get("/cost-centers")
async def list_cost_centers(
    center_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    user=Depends(get_current_user)
):
    _require_budget(user)
    q: dict = {}
    if center_type:
        q["center_type"] = center_type
    if is_active is not None:
        q["is_active"] = is_active
    centers = await db.cost_centers.find(q, {"_id": 0}).sort("code", 1).to_list(500)
    return centers


@router.post("/cost-centers")
async def create_cost_center(data: CostCenter, user=Depends(require_admin)):
    existing = await db.cost_centers.find_one({"code": data.code})
    if existing:
        raise HTTPException(400, f"Cost center code '{data.code}' already exists")
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_by"] = user["id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.cost_centers.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/cost-centers/{cc_id}")
async def update_cost_center(cc_id: str, data: CostCenterUpdate, user=Depends(require_admin)):
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.cost_centers.update_one({"id": cc_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Cost center not found")
    return {"ok": True}


@router.delete("/cost-centers/{cc_id}")
async def delete_cost_center(cc_id: str, user=Depends(require_admin)):
    await db.cost_centers.delete_one({"id": cc_id})
    return {"ok": True}


# ─────────────────────── Budgets ───────────────────────

@router.get("/budgets")
async def list_budgets(
    fiscal_year: Optional[str] = None,
    cost_center_code: Optional[str] = None,
    status: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_budget(user)
    q: dict = {}
    if fiscal_year:
        q["fiscal_year"] = fiscal_year
    if cost_center_code:
        q["cost_center_code"] = cost_center_code
    if status:
        q["status"] = status
    budgets = await db.budgets.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return budgets


@router.get("/budgets/{budget_id}")
async def get_budget(budget_id: str, user=Depends(get_current_user)):
    _require_budget(user)
    b = await db.budgets.find_one({"id": budget_id}, {"_id": 0})
    if not b:
        raise HTTPException(404, "Budget not found")
    return b


@router.post("/budgets")
async def create_budget(data: Budget, user=Depends(require_admin)):
    # Resolve account names for lines
    lines = data.model_dump()["lines"]
    for line in lines:
        if not line.get("account_name"):
            acc = await db.chart_of_accounts.find_one({"code": line["account_code"]}, {"_id": 0, "name": 1})
            if acc:
                line["account_name"] = acc["name"]

    doc = data.model_dump()
    doc["lines"] = lines
    doc["id"] = str(uuid.uuid4())
    doc["total_budget"] = round(sum(l["budgeted_amount"] for l in lines), 2)
    doc["created_by"] = user["id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.budgets.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/budgets/{budget_id}")
async def update_budget(budget_id: str, data: BudgetUpdate, user=Depends(require_admin)):
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    if "lines" in upd:
        upd["total_budget"] = round(sum(l["budgeted_amount"] for l in upd["lines"]), 2)
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.budgets.update_one({"id": budget_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Budget not found")
    return {"ok": True}


@router.delete("/budgets/{budget_id}")
async def delete_budget(budget_id: str, user=Depends(require_admin)):
    await db.budgets.delete_one({"id": budget_id})
    return {"ok": True}


# ─────────────────────── Budget vs Actual ───────────────────────

@router.get("/variance-report")
async def budget_variance_report(
    budget_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    """Compare budgeted amounts vs actual spending from journal entries."""
    _require_budget(user)
    budget = await db.budgets.find_one({"id": budget_id}, {"_id": 0})
    if not budget:
        raise HTTPException(404, "Budget not found")

    # Get posted journal entries for the period
    q_je: dict = {"status": "POSTED"}
    if from_date or to_date:
        q_je["date"] = {}
        if from_date:
            q_je["date"]["$gte"] = from_date
        if to_date:
            q_je["date"]["$lte"] = to_date

    journal_entries = await db.journal_entries.find(q_je, {"_id": 0}).to_list(5000)

    # Compute actual per account code
    actuals: dict = {}
    for je in journal_entries:
        for line in je.get("lines", []):
            code = line["account_code"]
            debit = line.get("debit", 0)
            credit = line.get("credit", 0)
            actuals[code] = actuals.get(code, 0) + debit - credit

    # Build variance rows
    rows = []
    total_budget = 0
    total_actual = 0
    for line in budget.get("lines", []):
        code = line["account_code"]
        budgeted = line["budgeted_amount"]
        actual = abs(actuals.get(code, 0))
        variance = round(budgeted - actual, 2)
        pct_used = round((actual / max(budgeted, 0.01)) * 100, 1)
        rows.append({
            "account_code": code,
            "account_name": line.get("account_name", code),
            "cost_center_code": line.get("cost_center_code"),
            "budgeted_amount": budgeted,
            "actual_amount": round(actual, 2),
            "variance": variance,
            "pct_used": pct_used,
            "status": "OVER_BUDGET" if actual > budgeted else ("WARNING" if pct_used > 80 else "ON_TRACK"),
        })
        total_budget += budgeted
        total_actual += actual

    return {
        "budget_id": budget_id,
        "budget_name": budget.get("name"),
        "fiscal_year": budget.get("fiscal_year"),
        "from_date": from_date,
        "to_date": to_date,
        "rows": rows,
        "total_budget": round(total_budget, 2),
        "total_actual": round(total_actual, 2),
        "total_variance": round(total_budget - total_actual, 2),
        "overall_pct_used": round((total_actual / max(total_budget, 0.01)) * 100, 1),
    }


@router.get("/alerts")
async def budget_alerts(fiscal_year: Optional[str] = None, user=Depends(get_current_user)):
    """Return accounts that are over budget or at >80% utilization."""
    _require_budget(user)
    q: dict = {"status": "APPROVED"}
    if fiscal_year:
        q["fiscal_year"] = fiscal_year
    budgets = await db.budgets.find(q, {"_id": 0}).to_list(100)

    # Get all journal entries
    all_jes = await db.journal_entries.find({"status": "POSTED"}, {"_id": 0}).to_list(5000)
    actuals: dict = {}
    for je in all_jes:
        for line in je.get("lines", []):
            code = line["account_code"]
            actuals[code] = actuals.get(code, 0) + abs(line.get("debit", 0) - line.get("credit", 0))

    alerts = []
    for budget in budgets:
        for line in budget.get("lines", []):
            code = line["account_code"]
            budgeted = line["budgeted_amount"]
            actual = actuals.get(code, 0)
            pct = (actual / max(budgeted, 0.01)) * 100
            if pct > 80:
                alerts.append({
                    "budget_name": budget["name"],
                    "fiscal_year": budget["fiscal_year"],
                    "account_code": code,
                    "account_name": line.get("account_name", code),
                    "budgeted_amount": budgeted,
                    "actual_amount": round(actual, 2),
                    "pct_used": round(pct, 1),
                    "alert_level": "CRITICAL" if pct > 100 else "WARNING",
                })

    return sorted(alerts, key=lambda x: x["pct_used"], reverse=True)


@router.get("/summary")
async def budget_summary(fiscal_year: Optional[str] = None, user=Depends(get_current_user)):
    _require_budget(user)
    q: dict = {}
    if fiscal_year:
        q["fiscal_year"] = fiscal_year
    total_budgets = await db.budgets.count_documents(q)
    approved = await db.budgets.count_documents({**q, "status": "APPROVED"})
    total_cost_centers = await db.cost_centers.count_documents({"is_active": True})
    total_budget_amount = 0
    async for b in db.budgets.find(q, {"_id": 0, "total_budget": 1}):
        total_budget_amount += b.get("total_budget", 0)
    return {
        "total_budgets": total_budgets,
        "approved_budgets": approved,
        "total_cost_centers": total_cost_centers,
        "total_budget_amount": round(total_budget_amount, 2),
    }
