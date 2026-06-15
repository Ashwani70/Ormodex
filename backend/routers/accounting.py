"""Accounting & Financial Reports router.

Covers:
- Fiscal Year management
- Chart of Accounts (CoA) CRUD
- Journal Entry creation, listing, approval, posting
- General Ledger query
- Trial Balance
- Profit & Loss
- Balance Sheet
- Day Book
"""
import uuid
from datetime import datetime, date, timezone
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from core.accounting_models import (
    ChartOfAccount, ChartOfAccountUpdate,
    FiscalYear, FiscalYearUpdate,
    JournalEntry, JournalEntryUpdate,
)
from core.auth_utils import get_current_user, require_admin
from core.db import db

router = APIRouter(prefix="/accounting", tags=["Accounting"])


# ─────────────────────────── Helpers ───────────────────────────

def _require_accounting(user: dict):
    if user.get("role") == "admin":
        return user
    perms = user.get("module_permissions", [])
    if "accounting" not in perms:
        raise HTTPException(status_code=403, detail="Accounting module access required")
    return user


async def _next_entry_number(fiscal_year: str) -> str:
    count = await db.journal_entries.count_documents({"fiscal_year": fiscal_year})
    return f"JE/{fiscal_year}/{str(count + 1).zfill(5)}"


async def _next_voucher_prefix(voucher_type: str, fiscal_year: str) -> str:
    prefix_map = {
        "RECEIPT": "RV", "PAYMENT": "PV", "CONTRA": "CV",
        "JOURNAL": "JV", "DEBIT_NOTE": "DN", "CREDIT_NOTE": "CN", "EXPENSE": "EV",
    }
    p = prefix_map.get(voucher_type, "VCH")
    count = await db.vouchers.count_documents({"voucher_type": voucher_type, "fiscal_year": fiscal_year})
    return f"{p}/{fiscal_year}/{str(count + 1).zfill(5)}"


# ─────────────────────────── Fiscal Year ───────────────────────────

@router.get("/fiscal-years")
async def list_fiscal_years(user=Depends(get_current_user)):
    _require_accounting(user)
    years = await db.fiscal_years.find({}, {"_id": 0}).to_list(50)
    return years


@router.post("/fiscal-years")
async def create_fiscal_year(data: FiscalYear, user=Depends(require_admin)):
    existing = await db.fiscal_years.find_one({"name": data.name})
    if existing:
        raise HTTPException(400, "Fiscal year already exists")
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.fiscal_years.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/fiscal-years/{fy_id}")
async def update_fiscal_year(fy_id: str, data: FiscalYearUpdate, user=Depends(require_admin)):
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    await db.fiscal_years.update_one({"id": fy_id}, {"$set": upd})
    return {"ok": True}


# ─────────────────────────── Chart of Accounts ───────────────────────────

@router.get("/chart-of-accounts")
async def list_coa(account_type: Optional[str] = None, user=Depends(get_current_user)):
    _require_accounting(user)
    q = {}
    if account_type:
        q["account_type"] = account_type
    accounts = await db.chart_of_accounts.find(q, {"_id": 0}).sort("code", 1).to_list(500)
    return accounts


@router.post("/chart-of-accounts")
async def create_account(data: ChartOfAccount, user=Depends(require_admin)):
    existing = await db.chart_of_accounts.find_one({"code": data.code})
    if existing:
        raise HTTPException(400, f"Account code '{data.code}' already exists")
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by"] = user["id"]
    await db.chart_of_accounts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/chart-of-accounts/{account_id}")
async def update_account(account_id: str, data: ChartOfAccountUpdate, user=Depends(require_admin)):
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    res = await db.chart_of_accounts.update_one({"id": account_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Account not found")
    return {"ok": True}


@router.delete("/chart-of-accounts/{account_id}")
async def delete_account(account_id: str, user=Depends(require_admin)):
    # Fetch account to get its code
    account = await db.chart_of_accounts.find_one({"id": account_id}, {"_id": 0, "code": 1})
    if not account:
        raise HTTPException(404, "Account not found")
    # Check if this specific account code has any journal entries
    usage = await db.journal_entries.count_documents({"lines.account_code": account["code"]})
    if usage > 0:
        # Soft delete only — cannot hard delete accounts with journal history
        await db.chart_of_accounts.update_one({"id": account_id}, {"$set": {"is_active": False}})
        return {"ok": True, "soft_deleted": True, "message": f"Account deactivated (has {usage} journal entries)"}
    await db.chart_of_accounts.delete_one({"id": account_id})
    return {"ok": True}


# ─────────────────────────── Journal Entries ───────────────────────────

@router.get("/journal-entries")
async def list_journal_entries(
    status: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    user=Depends(get_current_user)
):
    _require_accounting(user)
    q = {}
    if status:
        q["status"] = status
    if from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date
    if search:
        q["$or"] = [
            {"entry_number": {"$regex": search, "$options": "i"}},
            {"narration": {"$regex": search, "$options": "i"}},
        ]
    total = await db.journal_entries.count_documents(q)
    skip = (page - 1) * limit
    entries = await db.journal_entries.find(q, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "page": page, "items": entries}


@router.post("/journal-entries")
async def create_journal_entry(data: JournalEntry, user=Depends(get_current_user)):
    _require_accounting(user)
    # Validate double-entry: debits == credits
    total_debit = sum(l.debit for l in data.lines)
    total_credit = sum(l.credit for l in data.lines)
    if abs(total_debit - total_credit) > 0.01:
        raise HTTPException(400, f"Journal entry not balanced: Debit {total_debit} ≠ Credit {total_credit}")

    # Get active fiscal year
    fy = await db.fiscal_years.find_one({"is_active": True})
    fy_name = fy["name"] if fy else date.today().strftime("%Y-%y")

    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["fiscal_year"] = fy_name
    doc["entry_number"] = await _next_entry_number(fy_name)
    doc["created_by"] = user["id"]
    doc["created_by_name"] = user.get("name", "")
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["total_debit"] = total_debit
    doc["total_credit"] = total_credit

    await db.journal_entries.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/journal-entries/{entry_id}")
async def get_journal_entry(entry_id: str, user=Depends(get_current_user)):
    _require_accounting(user)
    entry = await db.journal_entries.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(404, "Journal entry not found")
    return entry


@router.patch("/journal-entries/{entry_id}")
async def update_journal_entry(entry_id: str, data: JournalEntryUpdate, user=Depends(get_current_user)):
    _require_accounting(user)
    entry = await db.journal_entries.find_one({"id": entry_id})
    if not entry:
        raise HTTPException(404, "Not found")
    if entry.get("status") == "POSTED":
        raise HTTPException(400, "Posted entries cannot be modified")
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    upd["updated_by"] = user["id"]
    await db.journal_entries.update_one({"id": entry_id}, {"$set": upd})
    return {"ok": True}


# ─────────────────────────── General Ledger ───────────────────────────

@router.get("/general-ledger")
async def general_ledger(
    account_code: str = Query(...),
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_accounting(user)
    q: dict[str, Any] = {"lines.account_code": account_code, "status": "POSTED"}
    if from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date

    entries = await db.journal_entries.find(q, {"_id": 0}).sort("date", 1).to_list(1000)

    # Flatten to ledger lines
    ledger_lines = []
    running_balance = 0.0
    for e in entries:
        for line in e.get("lines", []):
            if line["account_code"] == account_code:
                debit = line.get("debit", 0)
                credit = line.get("credit", 0)
                running_balance += (debit - credit)
                ledger_lines.append({
                    "date": e["date"],
                    "entry_number": e.get("entry_number"),
                    "narration": e.get("narration"),
                    "debit": debit,
                    "credit": credit,
                    "balance": round(running_balance, 2),
                })

    account = await db.chart_of_accounts.find_one({"code": account_code}, {"_id": 0})
    return {"account": account, "lines": ledger_lines}


# ─────────────────────────── Trial Balance ───────────────────────────

@router.get("/trial-balance")
async def trial_balance(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_accounting(user)
    q: dict[str, Any] = {"status": "POSTED"}
    if from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date

    entries = await db.journal_entries.find(q, {"_id": 0}).to_list(5000)
    balances: dict = {}
    for e in entries:
        for line in e.get("lines", []):
            code = line["account_code"]
            if code not in balances:
                balances[code] = {"account_code": code, "account_name": line["account_name"], "debit": 0, "credit": 0}
            balances[code]["debit"] += line.get("debit", 0)
            balances[code]["credit"] += line.get("credit", 0)

    rows = []
    total_debit = 0
    total_credit = 0
    for code, b in sorted(balances.items()):
        b["debit"] = round(b["debit"], 2)
        b["credit"] = round(b["credit"], 2)
        total_debit += b["debit"]
        total_credit += b["credit"]
        rows.append(b)

    return {
        "rows": rows,
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "is_balanced": abs(total_debit - total_credit) < 0.01,
    }


# ─────────────────────────── P&L Statement ───────────────────────────

@router.get("/profit-loss")
async def profit_and_loss(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_accounting(user)
    q: dict[str, Any] = {"status": "POSTED"}
    if from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date

    entries = await db.journal_entries.find(q, {"_id": 0}).to_list(5000)

    # Get all accounts to find types
    accounts = {a["code"]: a for a in await db.chart_of_accounts.find({}, {"_id": 0}).to_list(500)}

    income = {}
    expense = {}
    for e in entries:
        for line in e.get("lines", []):
            code = line["account_code"]
            acc = accounts.get(code, {})
            acc_type = acc.get("account_type")
            net = line.get("credit", 0) - line.get("debit", 0)
            if acc_type == "INCOME":
                income[code] = income.get(code, {"code": code, "name": line["account_name"], "amount": 0})
                income[code]["amount"] += net
            elif acc_type == "EXPENSE":
                expense[code] = expense.get(code, {"code": code, "name": line["account_name"], "amount": 0})
                expense[code]["amount"] += (line.get("debit", 0) - line.get("credit", 0))

    total_income = round(sum(v["amount"] for v in income.values()), 2)
    total_expense = round(sum(v["amount"] for v in expense.values()), 2)
    net_profit = round(total_income - total_expense, 2)

    return {
        "income": sorted(income.values(), key=lambda x: x["code"]),
        "expense": sorted(expense.values(), key=lambda x: x["code"]),
        "total_income": total_income,
        "total_expense": total_expense,
        "net_profit": net_profit,
        "from_date": from_date,
        "to_date": to_date,
    }


# ─────────────────────────── Balance Sheet ───────────────────────────

@router.get("/balance-sheet")
async def balance_sheet(as_of_date: Optional[str] = None, user=Depends(get_current_user)):
    _require_accounting(user)
    q: dict[str, Any] = {"status": "POSTED"}
    if as_of_date:
        q["date"] = {"$lte": as_of_date}

    entries = await db.journal_entries.find(q, {"_id": 0}).to_list(5000)
    accounts = {a["code"]: a for a in await db.chart_of_accounts.find({}, {"_id": 0}).to_list(500)}

    summary: dict = {}
    for e in entries:
        for line in e.get("lines", []):
            code = line["account_code"]
            acc = accounts.get(code, {})
            if code not in summary:
                summary[code] = {
                    "code": code,
                    "name": line["account_name"],
                    "account_type": acc.get("account_type"),
                    "debit": 0,
                    "credit": 0,
                }
            summary[code]["debit"] += line.get("debit", 0)
            summary[code]["credit"] += line.get("credit", 0)

    assets, liabilities, equity = [], [], []
    for code, row in sorted(summary.items()):
        row["balance"] = round(row["debit"] - row["credit"], 2)
        t = row.get("account_type")
        if t == "ASSET":
            assets.append(row)
        elif t == "LIABILITY":
            liabilities.append(row)
        elif t == "EQUITY":
            equity.append(row)

    total_assets = round(sum(r["balance"] for r in assets), 2)
    total_liabilities = round(sum(r["balance"] for r in liabilities), 2)
    total_equity = round(sum(r["balance"] for r in equity), 2)

    return {
        "as_of_date": as_of_date or date.today().isoformat(),
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
    }


# ─────────────────────────── Day Book ───────────────────────────

@router.get("/day-book")
async def day_book(
    day: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_accounting(user)
    q = {}
    if day:
        q["date"] = day
    elif from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date
    else:
        q["date"] = date.today().isoformat()

    entries = await db.journal_entries.find(q, {"_id": 0}).sort("date", 1).to_list(500)
    vouchers = await db.vouchers.find(q, {"_id": 0}).sort("date", 1).to_list(500)

    return {
        "journal_entries": entries,
        "vouchers": vouchers,
        "total_entries": len(entries) + len(vouchers),
    }


# ─────────────────────────── Seed Default CoA ───────────────────────────

@router.post("/seed-coa")
async def seed_default_coa(user=Depends(require_admin)):
    """Seed a standard Chart of Accounts if none exists."""
    existing = await db.chart_of_accounts.count_documents({})
    if existing > 0:
        return {"message": "Chart of Accounts already seeded", "count": existing}

    default_accounts: list[dict[str, Any]] = [
        # ASSETS
        {"code": "1001", "name": "Cash in Hand", "account_type": "ASSET"},
        {"code": "1002", "name": "Bank Account - Primary", "account_type": "ASSET"},
        {"code": "1003", "name": "Petty Cash", "account_type": "ASSET"},
        {"code": "1100", "name": "Accounts Receivable", "account_type": "ASSET"},
        {"code": "1200", "name": "Inventory", "account_type": "ASSET"},
        {"code": "1300", "name": "Prepaid Expenses", "account_type": "ASSET"},
        {"code": "1400", "name": "Fixed Assets", "account_type": "ASSET"},
        {"code": "1401", "name": "Plant & Machinery", "account_type": "ASSET"},
        {"code": "1402", "name": "Vehicles", "account_type": "ASSET"},
        {"code": "1500", "name": "GST Input Tax Credit", "account_type": "ASSET"},
        # LIABILITIES
        {"code": "2001", "name": "Accounts Payable", "account_type": "LIABILITY"},
        {"code": "2002", "name": "GST Payable", "account_type": "LIABILITY"},
        {"code": "2003", "name": "CGST Payable", "account_type": "LIABILITY"},
        {"code": "2004", "name": "SGST Payable", "account_type": "LIABILITY"},
        {"code": "2005", "name": "IGST Payable", "account_type": "LIABILITY"},
        {"code": "2006", "name": "TDS Payable", "account_type": "LIABILITY"},
        {"code": "2100", "name": "Short-Term Loans", "account_type": "LIABILITY"},
        {"code": "2200", "name": "Long-Term Loans", "account_type": "LIABILITY"},
        {"code": "2300", "name": "Salary Payable", "account_type": "LIABILITY"},
        # EQUITY
        {"code": "3001", "name": "Owner's Capital", "account_type": "EQUITY"},
        {"code": "3002", "name": "Retained Earnings", "account_type": "EQUITY"},
        {"code": "3003", "name": "Current Year Profit/Loss", "account_type": "EQUITY"},
        # INCOME
        {"code": "4001", "name": "Sales Revenue", "account_type": "INCOME"},
        {"code": "4002", "name": "Export Revenue", "account_type": "INCOME"},
        {"code": "4003", "name": "Service Income", "account_type": "INCOME"},
        {"code": "4004", "name": "Interest Income", "account_type": "INCOME"},
        {"code": "4005", "name": "Other Income", "account_type": "INCOME"},
        # EXPENSES
        {"code": "5001", "name": "Cost of Goods Sold", "account_type": "EXPENSE"},
        {"code": "5002", "name": "Purchase Expenses", "account_type": "EXPENSE"},
        {"code": "5003", "name": "Salaries & Wages", "account_type": "EXPENSE"},
        {"code": "5004", "name": "Rent Expense", "account_type": "EXPENSE"},
        {"code": "5005", "name": "Utilities Expense", "account_type": "EXPENSE"},
        {"code": "5006", "name": "Transport & Logistics", "account_type": "EXPENSE"},
        {"code": "5007", "name": "Marketing & Advertising", "account_type": "EXPENSE"},
        {"code": "5008", "name": "Office Supplies", "account_type": "EXPENSE"},
        {"code": "5009", "name": "Bank Charges", "account_type": "EXPENSE"},
        {"code": "5010", "name": "Depreciation", "account_type": "EXPENSE"},
        {"code": "5011", "name": "Miscellaneous Expenses", "account_type": "EXPENSE"},
    ]

    docs = []
    for a in default_accounts:
        a["id"] = str(uuid.uuid4())
        a["is_active"] = True
        a["opening_balance"] = 0.0
        a["currency"] = "INR"
        a["tags"] = []
        a["created_at"] = datetime.now(timezone.utc).isoformat()
        docs.append(a)

    await db.chart_of_accounts.insert_many(docs)
    return {"message": f"Seeded {len(docs)} accounts", "count": len(docs)}


# ─────────────────────────── Cash Flow Statement (Indirect Method) ───────────────────────────

@router.get("/cash-flow")
async def cash_flow_statement(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    """Generate Cash Flow Statement using indirect method from journal entries."""
    _require_accounting(user)

    q: dict[str, Any] = {"status": "POSTED"}
    if from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date

    entries = await db.journal_entries.find(q, {"_id": 0}).to_list(10000)
    accounts = {a["code"]: a for a in await db.chart_of_accounts.find({}, {"_id": 0}).to_list(500)}

    # Net income from P&L
    income_total = 0.0
    expense_total = 0.0

    # Balance sheet movements
    asset_changes: dict = {}
    liability_changes: dict = {}

    for e in entries:
        for line in e.get("lines", []):
            code = line["account_code"]
            acc = accounts.get(code, {})
            acc_type = acc.get("account_type")
            debit = line.get("debit", 0)
            credit = line.get("credit", 0)

            if acc_type == "INCOME":
                income_total += credit - debit
            elif acc_type == "EXPENSE":
                expense_total += debit - credit
            elif acc_type == "ASSET":
                asset_changes[code] = asset_changes.get(code, 0) + debit - credit
            elif acc_type == "LIABILITY":
                liability_changes[code] = liability_changes.get(code, 0) + credit - debit

    net_profit = round(income_total - expense_total, 2)

    # Operating activities (working capital changes)
    working_capital_items = []
    cash_accounts = {"1001", "1002", "1003"}  # Cash/Bank accounts

    # Receivables change (negative = increase in receivables = cash outflow)
    receivables_change = round(sum(v for k, v in asset_changes.items() if k in ("1100",)), 2)
    if receivables_change != 0:
        working_capital_items.append({
            "label": "Change in Accounts Receivable",
            "amount": -receivables_change,
            "type": "WORKING_CAPITAL"
        })

    # Inventory change
    inventory_change = round(sum(v for k, v in asset_changes.items() if k in ("1200",)), 2)
    if inventory_change != 0:
        working_capital_items.append({
            "label": "Change in Inventory",
            "amount": -inventory_change,
            "type": "WORKING_CAPITAL"
        })

    # Payables change (positive = increase in payables = cash inflow)
    payables_change = round(sum(v for k, v in liability_changes.items() if k in ("2001",)), 2)
    if payables_change != 0:
        working_capital_items.append({
            "label": "Change in Accounts Payable",
            "amount": payables_change,
            "type": "WORKING_CAPITAL"
        })

    working_capital_net = round(sum(w["amount"] for w in working_capital_items), 2)
    operating_cash_flow = round(net_profit + working_capital_net, 2)

    # Investing activities (Fixed asset changes)
    investing_items = []
    fixed_asset_change = round(sum(v for k, v in asset_changes.items() if k in ("1400", "1401", "1402")), 2)
    if fixed_asset_change != 0:
        investing_items.append({
            "label": "Purchase/Sale of Fixed Assets",
            "amount": -fixed_asset_change,
            "type": "INVESTING"
        })
    investing_cash_flow = round(sum(i["amount"] for i in investing_items), 2)

    # Financing activities (Equity/Loan changes)
    financing_items = []
    equity_change = round(sum(v for k, v in liability_changes.items() if k in ("3001", "3002", "2100", "2200")), 2)
    if equity_change != 0:
        financing_items.append({
            "label": "Equity/Loan Changes",
            "amount": equity_change,
            "type": "FINANCING"
        })
    financing_cash_flow = round(sum(f["amount"] for f in financing_items), 2)

    net_cash_change = round(operating_cash_flow + investing_cash_flow + financing_cash_flow, 2)

    return {
        "from_date": from_date,
        "to_date": to_date,
        "operating_activities": {
            "net_profit": net_profit,
            "working_capital_adjustments": working_capital_items,
            "working_capital_net": working_capital_net,
            "net_operating_cash_flow": operating_cash_flow,
        },
        "investing_activities": {
            "items": investing_items,
            "net_investing_cash_flow": investing_cash_flow,
        },
        "financing_activities": {
            "items": financing_items,
            "net_financing_cash_flow": financing_cash_flow,
        },
        "net_cash_change": net_cash_change,
    }


# ─────────────────────────── Interest on Outstanding ───────────────────────────

@router.get("/interest-on-outstanding")
async def interest_on_outstanding(
    annual_rate: float = Query(18.0, description="Annual interest rate (%)"),
    as_of_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    """Calculate interest on overdue invoices at a given annual interest rate."""
    _require_accounting(user)
    today = date.fromisoformat(as_of_date) if as_of_date else date.today()

    invoices = await db.invoices.find(
        {"status": {"$in": ["UNPAID", "PARTIAL"]}},
        {"_id": 0}
    ).to_list(5000)

    results = []
    total_outstanding = 0.0
    total_interest = 0.0

    for inv in invoices:
        inv_total = float(inv.get("total", 0))
        paid = float(inv.get("payment_received", 0))
        outstanding = round(inv_total - paid, 2)
        if outstanding <= 0:
            continue

        # Invoice date — use created_at as proxy
        inv_date_str = (inv.get("created_at") or "")[:10]
        if not inv_date_str:
            continue
        try:
            inv_date = date.fromisoformat(inv_date_str)
        except ValueError:
            continue

        days_overdue = max(0, (today - inv_date).days)
        daily_rate = annual_rate / 365 / 100
        interest = round(outstanding * daily_rate * days_overdue, 2)

        results.append({
            "invoice_number": inv.get("invoice_number", ""),
            "customer_name": inv.get("customer_name", ""),
            "invoice_date": inv_date_str,
            "invoice_total": inv_total,
            "amount_outstanding": outstanding,
            "days_overdue": days_overdue,
            "interest_rate_pa": annual_rate,
            "interest_amount": interest,
            "total_due_with_interest": round(outstanding + interest, 2),
        })
        total_outstanding += outstanding
        total_interest += interest

    results.sort(key=lambda x: x["days_overdue"], reverse=True)
    return {
        "annual_rate": annual_rate,
        "as_of_date": today.isoformat(),
        "invoices": results,
        "total_outstanding": round(total_outstanding, 2),
        "total_interest": round(total_interest, 2),
        "total_due_with_interest": round(total_outstanding + total_interest, 2),
    }
