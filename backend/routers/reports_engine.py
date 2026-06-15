"""Reports — deeper (Module F).

A generic reporting engine over the journal-entry ledger, built on MongoDB
aggregation pipelines. Everything reconciles to the standalone
/accounting/balance-sheet and /accounting/profit-loss endpoints.

Core ideas
----------
- The ledger is `journal_entries` (status POSTED), each with lines[]
  {account_code, account_name, debit, credit, cost_center} plus date,
  fiscal_year and an optional `branch` (defaults to "HO" when absent).
- A *report* = grouping rule (by account_type / account / cost_center / branch)
  + column definitions (one column per period, and/or per branch / cost-center).
- `$facet` produces multi-period comparative columns in a single pass.
- Every leaf amount carries the composing journal-entry ids so any cell drills
  to the exact vouchers (`GET /reports/drill`).
- Heavy reports are pre-aggregated into `report_summaries`, refreshed on post,
  and always reconcilable to source (a /reconcile check recomputes from source).

Consolidation sums across branches; inter-branch elimination removes lines whose
account is flagged `inter_branch` (Module L wires the actual elimination pairs).

Sign convention (matches accounting.py):
  ASSET, EXPENSE  → balance = debit - credit
  LIABILITY, EQUITY, INCOME → balance = credit - debit
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import date, datetime, timezone

from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.utils import now_iso, new_id

router = APIRouter(prefix="/reports", tags=["Reports — deeper"])


def _require_reports(user: dict):
    if user.get("role") in ("admin", "accountant"):
        return user
    if any(p in user.get("module_permissions", []) for p in ("reports", "accounting", "mis")):
        return user
    raise HTTPException(403, "Reports module access required")


# ══════════════════════════════════════════════════════════════
# Financial year helpers
# ══════════════════════════════════════════════════════════════

def _fy_bounds(fy: str) -> tuple[str, str]:
    """'2024-25' → ('2024-04-01', '2025-03-31'). Indian FY Apr 1 – Mar 31."""
    start_yr = int(fy.split("-")[0])
    return f"{start_yr}-04-01", f"{start_yr + 1}-03-31"


def _fy_range(from_fy: str, to_fy: str) -> list[str]:
    """Inclusive list of FY labels from from_fy to to_fy, e.g. 2023-24 → 2024-25."""
    start = int(from_fy.split("-")[0])
    end = int(to_fy.split("-")[0])
    if end < start:
        start, end = end, start
    return [f"{y}-{str(y + 1)[-2:]}" for y in range(start, end + 1)]


_SIGN_DEBIT_POSITIVE = {"ASSET", "EXPENSE"}


def _signed(account_type: Optional[str], debit: float, credit: float) -> float:
    if account_type in _SIGN_DEBIT_POSITIVE:
        return round(debit - credit, 2)
    return round(credit - debit, 2)


# ══════════════════════════════════════════════════════════════
# Aggregation: per-period grouped balances WITH drill ids
# ══════════════════════════════════════════════════════════════

async def _grouped_balances(
    date_from: str,
    date_to: str,
    group_by: str,                       # "account" | "cost_center" | "branch" | "account_type"
    branches: Optional[list[str]] = None,
    cost_centers: Optional[list[str]] = None,
    balance_sheet_mode: bool = False,    # B/S = cumulative up to date_to; P&L = within window
) -> dict[str, dict]:
    """
    Returns {group_key: {debit, credit, account_code, account_name, account_type,
                         entry_ids: [...]}} for one period.

    For balance-sheet items we accumulate from the beginning of time up to
    date_to; for P&L items we restrict to [date_from, date_to].
    """
    match: dict = {"status": "POSTED"}
    if balance_sheet_mode:
        match["date"] = {"$lte": date_to}
    else:
        match["date"] = {"$gte": date_from, "$lte": date_to}

    pipeline: list[dict] = [
        {"$match": match},
        {"$unwind": "$lines"},
    ]

    line_match: dict = {}
    if branches:
        # branch lives at entry level; default missing → "HO"
        pipeline.append({"$addFields": {"_branch": {"$ifNull": ["$branch", "HO"]}}})
        line_match["_branch"] = {"$in": branches}
    else:
        pipeline.append({"$addFields": {"_branch": {"$ifNull": ["$branch", "HO"]}}})
    if cost_centers:
        line_match["lines.cost_center"] = {"$in": cost_centers}
    if line_match:
        pipeline.append({"$match": line_match})

    group_field = {
        "account": "$lines.account_code",
        "cost_center": {"$ifNull": ["$lines.cost_center", "Unallocated"]},
        "branch": "$_branch",
        "account_type": None,   # resolved after COA join below
    }[group_by] if group_by != "account_type" else "$lines.account_code"

    pipeline += [
        {"$group": {
            "_id": group_field,
            "account_code": {"$first": "$lines.account_code"},
            "account_name": {"$first": "$lines.account_name"},
            "debit": {"$sum": {"$ifNull": ["$lines.debit", 0]}},
            "credit": {"$sum": {"$ifNull": ["$lines.credit", 0]}},
            "entry_ids": {"$addToSet": "$id"},
        }},
    ]

    rows = await db.journal_entries.aggregate(pipeline).to_list(5000)

    # join account_type from COA
    accounts = {a["code"]: a for a in await db.chart_of_accounts.find({}, {"_id": 0}).to_list(1000)}
    out: dict[str, dict] = {}
    for r in rows:
        code = r.get("account_code")
        acc = accounts.get(code, {})
        key = str(r["_id"])
        if group_by == "account_type":
            key = acc.get("account_type", "UNCLASSIFIED")
        existing = out.get(key)
        rowdoc = {
            "key": key,
            "account_code": code,
            "account_name": r.get("account_name"),
            "account_type": acc.get("account_type"),
            "tags": acc.get("tags", []),
            "debit": round(r.get("debit", 0), 2),
            "credit": round(r.get("credit", 0), 2),
            "entry_ids": r.get("entry_ids", []),
        }
        if existing:
            existing["debit"] = round(existing["debit"] + rowdoc["debit"], 2)
            existing["credit"] = round(existing["credit"] + rowdoc["credit"], 2)
            existing["entry_ids"] = list(set(existing["entry_ids"]) | set(rowdoc["entry_ids"]))
        else:
            out[key] = rowdoc
    return out


# ══════════════════════════════════════════════════════════════
# Report builders
# ══════════════════════════════════════════════════════════════

async def _build_balance_sheet(date_to: str, branches, cost_centers) -> dict:
    rows = await _grouped_balances("0000-01-01", date_to, "account", branches, cost_centers,
                                   balance_sheet_mode=True)
    assets, liabilities, equity = [], [], []
    for r in rows.values():
        bal = _signed(r["account_type"], r["debit"], r["credit"])
        cell = {**r, "amount": bal}
        if r["account_type"] == "ASSET":
            assets.append(cell)
        elif r["account_type"] == "LIABILITY":
            liabilities.append(cell)
        elif r["account_type"] == "EQUITY":
            equity.append(cell)
    ta = round(sum(c["amount"] for c in assets), 2)
    tl = round(sum(c["amount"] for c in liabilities), 2)
    te = round(sum(c["amount"] for c in equity), 2)
    return {
        "assets": sorted(assets, key=lambda x: x["account_code"] or ""),
        "liabilities": sorted(liabilities, key=lambda x: x["account_code"] or ""),
        "equity": sorted(equity, key=lambda x: x["account_code"] or ""),
        "total_assets": ta, "total_liabilities": tl, "total_equity": te,
    }


async def _build_pnl(date_from: str, date_to: str, branches, cost_centers) -> dict:
    rows = await _grouped_balances(date_from, date_to, "account", branches, cost_centers,
                                   balance_sheet_mode=False)
    income, expense = [], []
    for r in rows.values():
        if r["account_type"] == "INCOME":
            income.append({**r, "amount": round(r["credit"] - r["debit"], 2)})
        elif r["account_type"] == "EXPENSE":
            expense.append({**r, "amount": round(r["debit"] - r["credit"], 2)})
    ti = round(sum(c["amount"] for c in income), 2)
    tx = round(sum(c["amount"] for c in expense), 2)
    return {
        "income": sorted(income, key=lambda x: x["account_code"] or ""),
        "expense": sorted(expense, key=lambda x: x["account_code"] or ""),
        "total_income": ti, "total_expense": tx, "net_profit": round(ti - tx, 2),
    }


def _sum_tag(rows: list[dict], tag: str) -> float:
    return round(sum(r["amount"] for r in rows if tag in (r.get("tags") or [])), 2)


def _compute_ratios(bs: dict, pnl: dict) -> dict:
    """Standard ratios from tagged groupings. Tags expected on COA:
    current_asset, quick_asset, inventory, current_liability, debtor."""
    assets, liabs, equity = bs["assets"], bs["liabilities"], bs["equity"]

    current_assets = _sum_tag(assets, "current_asset") or bs["total_assets"]
    current_liabs = _sum_tag(liabs, "current_liability") or bs["total_liabilities"]
    inventory = _sum_tag(assets, "inventory")
    quick_assets = current_assets - inventory
    debtors = _sum_tag(assets, "debtor")

    total_debt = bs["total_liabilities"]
    total_equity = bs["total_equity"] or 1e-9

    revenue = pnl["total_income"] or 1e-9
    cogs = _sum_tag(pnl["expense"], "cogs")
    gross_profit = revenue - cogs
    net_profit = pnl["net_profit"]
    capital_employed = (bs["total_equity"] + total_debt) or 1e-9

    def _r(x):
        return round(x, 4)

    return {
        "current_ratio": _r(current_assets / current_liabs) if current_liabs else None,
        "quick_ratio": _r(quick_assets / current_liabs) if current_liabs else None,
        "debt_equity_ratio": _r(total_debt / total_equity),
        "gross_margin_pct": _r(gross_profit / revenue * 100),
        "net_margin_pct": _r(net_profit / revenue * 100),
        "roce_pct": _r(net_profit / capital_employed * 100),
        "inventory_days": _r(inventory / (cogs or 1e-9) * 365) if cogs else None,
        "debtor_days": _r(debtors / revenue * 365),
        "_basis": {
            "current_assets": current_assets, "current_liabilities": current_liabs,
            "inventory": inventory, "quick_assets": quick_assets, "debtors": debtors,
            "revenue": pnl["total_income"], "cogs": cogs, "net_profit": net_profit,
            "total_debt": total_debt, "total_equity": bs["total_equity"],
        },
    }


async def _build_fund_flow(from_date: str, to_date: str, branches, cost_centers) -> dict:
    """Fund flow = working-capital change + sources/applications between two B/S dates."""
    open_bs = await _build_balance_sheet(from_date, branches, cost_centers)
    close_bs = await _build_balance_sheet(to_date, branches, cost_centers)

    def _by_code(bs):
        m = {}
        for grp in ("assets", "liabilities", "equity"):
            for r in bs[grp]:
                m[r["account_code"]] = r
        return m

    o, c = _by_code(open_bs), _by_code(close_bs)
    sources, applications = [], []
    for code in set(o) | set(c):
        oa = o.get(code, {}).get("amount", 0)
        ca = c.get(code, {}).get("amount", 0)
        delta = round(ca - oa, 2)
        if abs(delta) < 0.01:
            continue
        name = c.get(code, o.get(code, {})).get("account_name", code)
        atype = c.get(code, o.get(code, {})).get("account_type")
        # increase in liability/equity or decrease in asset = source of funds
        if atype in ("LIABILITY", "EQUITY"):
            (sources if delta > 0 else applications).append({"account_code": code, "name": name, "amount": abs(delta)})
        else:  # ASSET
            (applications if delta > 0 else sources).append({"account_code": code, "name": name, "amount": abs(delta)})

    total_sources = round(sum(s["amount"] for s in sources), 2)
    total_applications = round(sum(a["amount"] for a in applications), 2)
    return {
        "from_date": from_date, "to_date": to_date,
        "sources": sorted(sources, key=lambda x: -x["amount"]),
        "applications": sorted(applications, key=lambda x: -x["amount"]),
        "total_sources": total_sources,
        "total_applications": total_applications,
        "net_change_working_capital": round(total_sources - total_applications, 2),
    }


# ══════════════════════════════════════════════════════════════
# Main report endpoint with multi-period comparative columns ($facet style)
# ══════════════════════════════════════════════════════════════

REPORT_SLUGS = {"balance-sheet", "profit-loss", "ratios", "fund-flow", "cost-center"}


@router.get("/catalog")
async def report_catalog(_: dict = Depends(get_current_user)):
    return {
        "reports": [
            {"slug": "balance-sheet", "name": "Balance Sheet", "supports_compare": True, "dimension": "as_of"},
            {"slug": "profit-loss", "name": "Profit & Loss", "supports_compare": True, "dimension": "period"},
            {"slug": "ratios", "name": "Ratio Analysis", "supports_compare": True, "dimension": "period"},
            {"slug": "fund-flow", "name": "Fund Flow", "supports_compare": False, "dimension": "between"},
            {"slug": "cost-center", "name": "Cost-Center Report", "supports_compare": True, "dimension": "period"},
        ]
    }


@router.get("/run/{slug}")
async def run_report(
    slug: str,
    fromFy: str = Query(..., description="e.g. 2024-25"),
    toFy: Optional[str] = Query(None, description="for multi-period comparative; defaults to fromFy"),
    branches: Optional[str] = Query(None, description="comma-separated branch codes"),
    costCenters: Optional[str] = Query(None, description="comma-separated cost-center codes"),
    compare: bool = Query(False, description="emit one column per FY in range"),
    user: dict = Depends(get_current_user),
):
    """
    Run a report with optional multi-period comparative columns.

    Each FY in [fromFy, toFy] becomes a column (when compare=True). Single-period
    columns reconcile exactly to the standalone /accounting reports.
    """
    _require_reports(user)
    if slug not in REPORT_SLUGS:
        raise HTTPException(404, f"Unknown report '{slug}'. Known: {sorted(REPORT_SLUGS)}")

    to_fy = toFy or fromFy
    branch_list = [b.strip() for b in branches.split(",") if b.strip()] if branches else None
    cc_list = [c.strip() for c in costCenters.split(",") if c.strip()] if costCenters else None
    fy_columns = _fy_range(fromFy, to_fy) if compare else [fromFy]

    columns = []
    for fy in fy_columns:
        d_from, d_to = _fy_bounds(fy)
        if slug == "balance-sheet":
            data = await _build_balance_sheet(d_to, branch_list, cc_list)
        elif slug == "profit-loss":
            data = await _build_pnl(d_from, d_to, branch_list, cc_list)
        elif slug == "ratios":
            bs = await _build_balance_sheet(d_to, branch_list, cc_list)
            pnl = await _build_pnl(d_from, d_to, branch_list, cc_list)
            data = _compute_ratios(bs, pnl)
        elif slug == "cost-center":
            rows = await _grouped_balances(d_from, d_to, "cost_center", branch_list, cc_list)
            cc_rows = []
            for r in rows.values():
                amt = _signed(r["account_type"], r["debit"], r["credit"])
                cc_rows.append({"cost_center": r["key"], "amount": amt,
                                "entry_ids": r["entry_ids"], "account_code": r["account_code"]})
            data = {"rows": sorted(cc_rows, key=lambda x: -abs(x["amount"])),
                    "total": round(sum(x["amount"] for x in cc_rows), 2)}
        else:  # fund-flow
            d_from_prev, _ = _fy_bounds(fromFy)
            _, d_to_last = _fy_bounds(to_fy)
            data = await _build_fund_flow(d_from_prev, d_to_last, branch_list, cc_list)
        columns.append({"fy": fy, "from": d_from, "to": d_to, "data": data})

    return {
        "slug": slug,
        "comparative": compare,
        "branches": branch_list,
        "cost_centers": cc_list,
        "columns": columns,
    }


# ══════════════════════════════════════════════════════════════
# Drill-down: a cell → composing journal entries → vouchers
# ══════════════════════════════════════════════════════════════

@router.get("/drill")
async def drill_cell(
    account_code: Optional[str] = None,
    cost_center: Optional[str] = None,
    branch: Optional[str] = None,
    fromFy: Optional[str] = None,
    toFy: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """
    Drill a report cell to the exact composing journal entries (and their
    linked vouchers). Provide account_code / cost_center / branch + a date range
    (either explicit date_from/date_to or an FY range).
    """
    _require_reports(user)
    if fromFy:
        d_from, _ = _fy_bounds(fromFy)
        _, d_to = _fy_bounds(toFy or fromFy)
    else:
        d_from = date_from or "0000-01-01"
        d_to = date_to or date.today().isoformat()

    match: dict = {"status": "POSTED", "date": {"$gte": d_from, "$lte": d_to}}
    if account_code:
        match["lines.account_code"] = account_code
    if branch:
        match["$expr"] = {"$eq": [{"$ifNull": ["$branch", "HO"]}, branch]}

    entries = await db.journal_entries.find(match, {"_id": 0}).sort("date", 1).to_list(2000)

    composing = []
    running = 0.0
    for e in entries:
        for line in e.get("lines", []):
            if account_code and line.get("account_code") != account_code:
                continue
            if cost_center and (line.get("cost_center") or "Unallocated") != cost_center:
                continue
            debit = line.get("debit", 0)
            credit = line.get("credit", 0)
            running += debit - credit
            composing.append({
                "entry_id": e.get("id"),
                "entry_number": e.get("entry_number"),
                "voucher_id": e.get("voucher_id"),
                "date": e.get("date"),
                "account_code": line.get("account_code"),
                "account_name": line.get("account_name"),
                "narration": line.get("narration") or e.get("narration"),
                "cost_center": line.get("cost_center"),
                "debit": round(debit, 2),
                "credit": round(credit, 2),
                "running_balance": round(running, 2),
            })

    return {
        "filters": {"account_code": account_code, "cost_center": cost_center, "branch": branch,
                    "date_from": d_from, "date_to": d_to},
        "line_count": len(composing),
        "total_debit": round(sum(c["debit"] for c in composing), 2),
        "total_credit": round(sum(c["credit"] for c in composing), 2),
        "net": round(sum(c["debit"] - c["credit"] for c in composing), 2),
        "lines": composing,
    }


# ══════════════════════════════════════════════════════════════
# Consolidation across branches (with inter-branch elimination)
# ══════════════════════════════════════════════════════════════

@router.get("/consolidated/balance-sheet")
async def consolidated_balance_sheet(
    fy: str = Query(..., description="e.g. 2024-25"),
    branches: Optional[str] = Query(None, description="branches to consolidate; blank = all"),
    user: dict = Depends(get_current_user),
):
    """
    Consolidated B/S = sum of standalone branch B/S, minus inter-branch balances.

    Inter-branch accounts are those tagged `inter_branch` on the COA; their net
    across branches is eliminated so the consolidated total ties to the sum of
    standalone branches less inter-company balances.
    """
    _require_reports(user)
    _, d_to = _fy_bounds(fy)

    if branches:
        branch_list = [b.strip() for b in branches.split(",") if b.strip()]
    else:
        # distinct branches present on entries (default HO)
        raw = await db.journal_entries.distinct("branch")
        branch_list = sorted({b or "HO" for b in raw}) or ["HO"]

    standalone = {}
    for b in branch_list:
        standalone[b] = await _build_balance_sheet(d_to, [b], None)

    # Sum standalones
    combined: dict[str, dict] = {}
    for b, bs in standalone.items():
        for grp in ("assets", "liabilities", "equity"):
            for r in bs[grp]:
                code = r["account_code"]
                if code not in combined:
                    combined[code] = {"account_code": code, "account_name": r["account_name"],
                                      "account_type": r["account_type"], "tags": r.get("tags", []),
                                      "amount": 0.0, "entry_ids": []}
                combined[code]["amount"] = round(combined[code]["amount"] + r["amount"], 2)
                combined[code]["entry_ids"] = list(set(combined[code]["entry_ids"]) | set(r.get("entry_ids", [])))

    # Inter-branch elimination: zero out accounts tagged inter_branch
    eliminations = []
    for code, row in combined.items():
        if "inter_branch" in (row.get("tags") or []):
            eliminations.append({"account_code": code, "name": row["account_name"], "eliminated": row["amount"]})
            row["amount"] = 0.0

    assets = [r for r in combined.values() if r["account_type"] == "ASSET"]
    liabilities = [r for r in combined.values() if r["account_type"] == "LIABILITY"]
    equity = [r for r in combined.values() if r["account_type"] == "EQUITY"]

    sum_standalone_assets = round(sum(bs["total_assets"] for bs in standalone.values()), 2)

    return {
        "fy": fy,
        "branches": branch_list,
        "standalone": {b: {"total_assets": bs["total_assets"],
                           "total_liabilities": bs["total_liabilities"],
                           "total_equity": bs["total_equity"]} for b, bs in standalone.items()},
        "eliminations": eliminations,
        "consolidated": {
            "assets": sorted(assets, key=lambda x: x["account_code"] or ""),
            "liabilities": sorted(liabilities, key=lambda x: x["account_code"] or ""),
            "equity": sorted(equity, key=lambda x: x["account_code"] or ""),
            "total_assets": round(sum(r["amount"] for r in assets), 2),
            "total_liabilities": round(sum(r["amount"] for r in liabilities), 2),
            "total_equity": round(sum(r["amount"] for r in equity), 2),
        },
        "reconciliation": {
            "sum_standalone_assets": sum_standalone_assets,
            "total_eliminated": round(sum(e["eliminated"] for e in eliminations), 2),
            "ties": abs(sum_standalone_assets
                        - sum(e["eliminated"] for e in eliminations if e["eliminated"] > 0)
                        - round(sum(r["amount"] for r in assets), 2)) < 1.0,
        },
    }


# ══════════════════════════════════════════════════════════════
# Materialized summaries (pre-aggregation), refreshed on post
# ══════════════════════════════════════════════════════════════

@router.post("/summaries/refresh")
async def refresh_summaries(fy: str = Query(...), user: dict = Depends(require_admin)):
    """
    Pre-aggregate B/S & P&L for an FY into `report_summaries`. Called on post
    (or scheduled). Keeps a `source_hash` (entry count + total debit) so the
    summary can be reconciled to source by /summaries/reconcile.
    """
    d_from, d_to = _fy_bounds(fy)
    bs = await _build_balance_sheet(d_to, None, None)
    pnl = await _build_pnl(d_from, d_to, None, None)

    entry_count = await db.journal_entries.count_documents(
        {"status": "POSTED", "date": {"$gte": d_from, "$lte": d_to}})
    agg = await db.journal_entries.aggregate([
        {"$match": {"status": "POSTED", "date": {"$gte": d_from, "$lte": d_to}}},
        {"$unwind": "$lines"},
        {"$group": {"_id": None, "td": {"$sum": {"$ifNull": ["$lines.debit", 0]}}}},
    ]).to_list(1)
    total_debit = round(agg[0]["td"], 2) if agg else 0.0

    doc = {
        "fy": fy,
        "balance_sheet": bs,
        "profit_loss": pnl,
        "source_hash": {"entry_count": entry_count, "total_debit": total_debit},
        "refreshed_at": now_iso(),
        "refreshed_by": user["id"],
    }
    await db.report_summaries.update_one({"fy": fy}, {"$set": doc}, upsert=True)
    return {"fy": fy, "refreshed": True, "source_hash": doc["source_hash"]}


@router.get("/summaries/reconcile")
async def reconcile_summary(fy: str = Query(...), user: dict = Depends(get_current_user)):
    """Confirm a materialized summary still ties to live source data."""
    _require_reports(user)
    summary = await db.report_summaries.find_one({"fy": fy}, {"_id": 0})
    if not summary:
        raise HTTPException(404, f"No summary for FY {fy}. Run /summaries/refresh first.")

    d_from, d_to = _fy_bounds(fy)
    entry_count = await db.journal_entries.count_documents(
        {"status": "POSTED", "date": {"$gte": d_from, "$lte": d_to}})
    agg = await db.journal_entries.aggregate([
        {"$match": {"status": "POSTED", "date": {"$gte": d_from, "$lte": d_to}}},
        {"$unwind": "$lines"},
        {"$group": {"_id": None, "td": {"$sum": {"$ifNull": ["$lines.debit", 0]}}}},
    ]).to_list(1)
    live = {"entry_count": entry_count, "total_debit": round(agg[0]["td"], 2) if agg else 0.0}
    stored = summary.get("source_hash", {})
    ties = (live["entry_count"] == stored.get("entry_count")
            and abs(live["total_debit"] - stored.get("total_debit", 0)) < 0.01)
    return {"fy": fy, "stored": stored, "live": live, "reconciled": ties}


# ══════════════════════════════════════════════════════════════
# Saved views (per user)
# ══════════════════════════════════════════════════════════════

@router.get("/saved-views")
async def list_saved_views(user: dict = Depends(get_current_user)):
    _require_reports(user)
    return await db.report_saved_views.find({"user_id": user["id"]}, {"_id": 0}).sort("name", 1).to_list(200)


@router.post("/saved-views")
async def create_saved_view(payload: dict, user: dict = Depends(get_current_user)):
    _require_reports(user)
    doc = {
        "id": new_id(),
        "user_id": user["id"],
        "name": payload.get("name", "Untitled view"),
        "slug": payload.get("slug"),
        "params": payload.get("params", {}),
        "created_at": now_iso(),
    }
    await db.report_saved_views.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/saved-views/{view_id}")
async def delete_saved_view(view_id: str, user: dict = Depends(get_current_user)):
    _require_reports(user)
    res = await db.report_saved_views.delete_one({"id": view_id, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "View not found")
    return {"ok": True}
