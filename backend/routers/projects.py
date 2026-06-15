"""Project & Job Costing — Module I.

Projects carry budgets and a billing mode (fixed / T&M). Any revenue/cost
voucher (journal entry line) may carry an optional `project_id` dimension;
`project_costs` additionally links specific vouchers to projects. Timesheet
entries capture billable hours at a rate.

Project P&L = tagged revenue − (tagged direct costs + allocated time cost +
overhead), computed by aggregation over `journal_entries` (status POSTED) plus
timesheet time-cost. Billable hours roll into a draft T&M invoice. Budget-vs-
actual burn comes from the same aggregation.

Collections: projects, tasks, timesheet_entries, project_costs
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Literal
from pydantic import BaseModel
from datetime import date

from core.auth_utils import get_current_user
from core.db import db
from core.utils import now_iso, new_id, next_doc_number, crud_create, crud_list, crud_get, crud_update

router = APIRouter(prefix="/projects", tags=["Project & Job Costing"])


def _require_projects(user: dict):
    if user.get("role") in ("admin", "accountant"):
        return user
    if any(p in user.get("module_permissions", []) for p in ("projects", "accounting", "sales")):
        return user
    raise HTTPException(403, "Projects module access required")


# ══════════════════════════════════════════════════════════════
# Models
# ══════════════════════════════════════════════════════════════

class Project(BaseModel):
    code: str
    name: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    budget: float = 0.0
    billing: Literal["fixed", "time_and_materials"] = "time_and_materials"
    overhead_pct: float = 0.0           # % uplift on direct+time cost
    status: Literal["active", "on_hold", "closed"] = "active"
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class Task(BaseModel):
    project_id: str
    name: str
    estimated_hours: float = 0.0
    status: Literal["open", "in_progress", "done"] = "open"


class TimesheetEntry(BaseModel):
    user_id: str
    project_id: str
    task_id: Optional[str] = None
    date: str
    hours: float
    billable: bool = True
    rate: float = 0.0                   # billing rate per hour (for T&M)
    cost_rate: float = 0.0              # internal cost per hour (for P&L)
    notes: Optional[str] = None
    invoiced: bool = False


class ProjectCostLink(BaseModel):
    project_id: str
    voucher_id: str
    amount: float
    cost_type: Literal["direct", "overhead", "material", "subcontract"] = "direct"
    narration: Optional[str] = None


# ══════════════════════════════════════════════════════════════
# Projects & tasks CRUD
# ══════════════════════════════════════════════════════════════

@router.get("")
async def list_projects(status: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_projects(user)
    filt = {"status": status} if status else {}
    return await crud_list("projects", filt=filt)


@router.post("")
async def create_project(payload: Project, user: dict = Depends(get_current_user)):
    _require_projects(user)
    return await crud_create("projects", payload.model_dump(), user)


@router.get("/{project_id}")
async def get_project(project_id: str, user: dict = Depends(get_current_user)):
    _require_projects(user)
    return await crud_get("projects", project_id)


@router.put("/{project_id}")
async def update_project(project_id: str, payload: Project, user: dict = Depends(get_current_user)):
    _require_projects(user)
    return await crud_update("projects", project_id, payload.model_dump(), user)


@router.get("/{project_id}/tasks")
async def list_tasks(project_id: str, user: dict = Depends(get_current_user)):
    _require_projects(user)
    return await crud_list("tasks", filt={"project_id": project_id})


@router.post("/tasks")
async def create_task(payload: Task, user: dict = Depends(get_current_user)):
    _require_projects(user)
    return await crud_create("tasks", payload.model_dump(), user)


# ══════════════════════════════════════════════════════════════
# Timesheets
# ══════════════════════════════════════════════════════════════

@router.post("/timesheets")
async def create_timesheet(payload: TimesheetEntry, user: dict = Depends(get_current_user)):
    _require_projects(user)
    return await crud_create("timesheet_entries", payload.model_dump(), user)


@router.get("/timesheets")
async def list_timesheets(
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require_projects(user)
    filt: dict = {}
    if project_id:
        filt["project_id"] = project_id
    if user_id:
        filt["user_id"] = user_id
    if from_date or to_date:
        filt["date"] = {}
        if from_date:
            filt["date"]["$gte"] = from_date
        if to_date:
            filt["date"]["$lte"] = to_date
    return await crud_list("timesheet_entries", filt=filt, sort_field="date")


# ══════════════════════════════════════════════════════════════
# Project costs (explicit voucher→project links)
# ══════════════════════════════════════════════════════════════

@router.post("/costs")
async def link_cost(payload: ProjectCostLink, user: dict = Depends(get_current_user)):
    _require_projects(user)
    return await crud_create("project_costs", payload.model_dump(), user)


@router.get("/{project_id}/costs")
async def list_costs(project_id: str, user: dict = Depends(get_current_user)):
    _require_projects(user)
    return await crud_list("project_costs", filt={"project_id": project_id})


# ══════════════════════════════════════════════════════════════
# P&L computation helpers (pure, testable)
# ══════════════════════════════════════════════════════════════

def _time_cost(entries: list[dict]) -> float:
    """Sum of internal time cost = hours × cost_rate over all timesheet entries."""
    return round(sum(e.get("hours", 0) * e.get("cost_rate", 0) for e in entries), 2)


def _billable_value(entries: list[dict], only_uninvoiced: bool = False) -> float:
    """Sum of billable hours × rate (the T&M revenue these hours represent)."""
    total = 0.0
    for e in entries:
        if not e.get("billable"):
            continue
        if only_uninvoiced and e.get("invoiced"):
            continue
        total += e.get("hours", 0) * e.get("rate", 0)
    return round(total, 2)


def _compute_pnl(tagged_revenue: float, tagged_direct_cost: float,
                 time_cost: float, overhead_pct: float) -> dict:
    """
    Project P&L:
      total cost = direct cost + time cost + overhead
      overhead   = (direct + time) × overhead_pct%
      profit     = revenue − total cost
    """
    base_cost = round(tagged_direct_cost + time_cost, 2)
    overhead = round(base_cost * overhead_pct / 100.0, 2)
    total_cost = round(base_cost + overhead, 2)
    profit = round(tagged_revenue - total_cost, 2)
    margin = round(profit / tagged_revenue * 100, 2) if tagged_revenue else None
    return {
        "revenue": round(tagged_revenue, 2),
        "direct_cost": round(tagged_direct_cost, 2),
        "time_cost": time_cost,
        "overhead_pct": overhead_pct,
        "overhead": overhead,
        "total_cost": total_cost,
        "profit": profit,
        "margin_pct": margin,
    }


async def _project_ledger_amounts(project_id: str) -> dict:
    """
    Aggregate journal-entry lines carrying this project_id into revenue and
    direct cost, collecting voucher ids for drill-down.

    A line counts toward revenue if its account is INCOME (credit−debit), and
    toward direct cost if its account is EXPENSE (debit−credit). project_id can
    live at the entry level or the line level (we match either).
    """
    pipeline = [
        {"$match": {"status": "POSTED",
                    "$or": [{"project_id": project_id}, {"lines.project_id": project_id}]}},
        {"$unwind": "$lines"},
        {"$match": {"$or": [{"project_id": project_id}, {"lines.project_id": project_id}]}},
        {"$group": {
            "_id": "$lines.account_code",
            "account_name": {"$first": "$lines.account_name"},
            "debit": {"$sum": {"$ifNull": ["$lines.debit", 0]}},
            "credit": {"$sum": {"$ifNull": ["$lines.credit", 0]}},
            "entry_ids": {"$addToSet": "$id"},
        }},
    ]
    rows = await db.journal_entries.aggregate(pipeline).to_list(2000)
    accounts = {a["code"]: a for a in await db.chart_of_accounts.find({}, {"_id": 0}).to_list(1000)}

    revenue = 0.0
    direct_cost = 0.0
    revenue_lines, cost_lines = [], []
    for r in rows:
        acc = accounts.get(r["_id"], {})
        atype = acc.get("account_type")
        if atype == "INCOME":
            amt = round(r["credit"] - r["debit"], 2)
            revenue += amt
            revenue_lines.append({"account_code": r["_id"], "account_name": r["account_name"],
                                  "amount": amt, "entry_ids": r["entry_ids"]})
        elif atype == "EXPENSE":
            amt = round(r["debit"] - r["credit"], 2)
            direct_cost += amt
            cost_lines.append({"account_code": r["_id"], "account_name": r["account_name"],
                               "amount": amt, "entry_ids": r["entry_ids"]})
    return {
        "revenue": round(revenue, 2), "direct_cost": round(direct_cost, 2),
        "revenue_lines": revenue_lines, "cost_lines": cost_lines,
    }


# ══════════════════════════════════════════════════════════════
# Project P&L endpoint
# ══════════════════════════════════════════════════════════════

@router.get("/{project_id}/pnl")
async def project_pnl(project_id: str, user: dict = Depends(get_current_user)):
    """Full project P&L with drill-down voucher ids and budget-vs-actual burn."""
    _require_projects(user)
    project = await crud_get("projects", project_id)

    ledger = await _project_ledger_amounts(project_id)
    entries = await db.timesheet_entries.find({"project_id": project_id}, {"_id": 0}).to_list(5000)
    time_cost = _time_cost(entries)

    pnl = _compute_pnl(ledger["revenue"], ledger["direct_cost"], time_cost,
                       project.get("overhead_pct", 0.0))

    budget = project.get("budget", 0.0)
    burn_pct = round(pnl["total_cost"] / budget * 100, 2) if budget else None

    return {
        "project": {"id": project_id, "code": project.get("code"), "name": project.get("name"),
                    "billing": project.get("billing"), "budget": budget},
        "pnl": pnl,
        "budget_vs_actual": {
            "budget": budget,
            "actual_cost": pnl["total_cost"],
            "remaining": round(budget - pnl["total_cost"], 2),
            "burn_pct": burn_pct,
            "over_budget": (pnl["total_cost"] > budget) if budget else False,
        },
        "billable": {
            "total_billable_value": _billable_value(entries),
            "uninvoiced_billable_value": _billable_value(entries, only_uninvoiced=True),
        },
        "revenue_lines": ledger["revenue_lines"],
        "cost_lines": ledger["cost_lines"],
        "timesheet_hours": round(sum(e.get("hours", 0) for e in entries), 2),
    }


# ══════════════════════════════════════════════════════════════
# Bill time → draft T&M invoice
# ══════════════════════════════════════════════════════════════

@router.post("/{project_id}/bill-time")
async def bill_time(project_id: str, user: dict = Depends(get_current_user)):
    """
    Roll uninvoiced billable hours into a DRAFT invoice for T&M projects.
    Marks the billed timesheet entries invoiced. Idempotent: only picks up
    entries not yet invoiced.
    """
    _require_projects(user)
    project = await crud_get("projects", project_id)
    if project.get("billing") != "time_and_materials":
        raise HTTPException(400, "bill-time only applies to time_and_materials projects")

    entries = await db.timesheet_entries.find(
        {"project_id": project_id, "billable": True, "invoiced": {"$ne": True}}, {"_id": 0}
    ).to_list(5000)
    billable = [e for e in entries if e.get("hours", 0) * e.get("rate", 0) > 0]
    if not billable:
        raise HTTPException(400, "No uninvoiced billable hours to bill")

    # Group billable hours into invoice lines (one line per rate band)
    by_rate: dict[float, dict] = {}
    for e in billable:
        rate = e.get("rate", 0)
        band = by_rate.setdefault(rate, {"hours": 0.0, "rate": rate})
        band["hours"] += e.get("hours", 0)

    items = []
    total = 0.0
    for rate, band in sorted(by_rate.items()):
        line_total = round(band["hours"] * rate, 2)
        total += line_total
        items.append({
            "description": f"Billable hours @ ₹{rate}/hr",
            "quantity": round(band["hours"], 2),
            "unit_price": rate,
            "amount": line_total,
            "project_id": project_id,
        })

    invoice = {
        "id": new_id(),
        "invoice_number": await next_doc_number("INV", "invoices"),
        "invoice_type": "TAX_INVOICE",
        "customer_id": project.get("customer_id"),
        "customer_name": project.get("customer_name"),
        "project_id": project_id,
        "items": items,
        "total": round(total, 2),
        "taxable_value": round(total, 2),
        "status": "UNPAID",
        "payment_received": 0,
        "source": "project_time_billing",
        "approval_state": "draft",
        "created_at": now_iso(),
    }
    await db.invoices.insert_one(invoice)

    entry_ids = [e["id"] for e in billable]
    await db.timesheet_entries.update_many(
        {"id": {"$in": entry_ids}},
        {"$set": {"invoiced": True, "invoice_id": invoice["id"], "updated_at": now_iso()}},
    )

    invoice.pop("_id", None)
    return {
        "invoice_id": invoice["id"],
        "invoice_number": invoice["invoice_number"],
        "total": invoice["total"],
        "lines": len(items),
        "entries_billed": len(entry_ids),
        "status": "draft",
    }
