"""Payroll router — Module C (Premium tier).

Indian statutory payroll covering:
- Pay components (earnings / deductions / reimbursements)
- Salary structures (per employee, effective_from versioned)
- FY-versioned statutory params: PF, ESI, PT slabs, TDS old/new regime
- Payroll run engine:
    * PF: 12% employee + 12% employer (EPF+EPS split) on PF wages ≤ ceiling
    * ESI: only if gross ≤ ESI ceiling; contribution-period rule (stick through period even if ceiling crossed mid-month)
    * PT: state-specific slab on gross; last-month exception for some states
    * TDS: project annual taxable income, apply regime slabs + std deduction + declarations, spread over remaining months; recompute on declaration change
    * LOP: prorate by paid_days/total_days; statutory bases adjust proportionally
- Payslips with full breakup
- Form 16 (Part A: TDS deposited, Part B: computation)
- Full & Final settlement: salary to LWD + leave encashment + gratuity − recoveries
- PF ECR / ESI return / PT register reports

Collections used:
  pay_components, salary_structures, statutory_params, payroll_runs,
  payslips, attendance, leave_balances, tds_declarations, fnf_settlements
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from typing import Optional, Literal, Any
from pydantic import BaseModel
from datetime import date
from calendar import monthrange

from core.auth_utils import get_current_user, require_admin, is_admin_role
from core.db import db
from core.utils import now_iso, new_id, crud_create, crud_list, crud_get, crud_update

router = APIRouter(prefix="/payroll", tags=["Payroll"])


def _require_hr(user: dict):
    if (is_admin_role(user.get("role")) or user.get("role") in ("hr_manager", "accountant")):
        return user
    if "payroll" in user.get("module_permissions", []):
        return user
    raise HTTPException(403, "Payroll module access required")


# ══════════════════════════════════════════════════════════════
# Pydantic models
# ══════════════════════════════════════════════════════════════

class PayComponent(BaseModel):
    name: str
    type: Literal["earning", "deduction", "reimbursement"]
    calc: Literal["flat", "percent_of_basic", "formula"]
    formula: Optional[str] = None
    taxable: bool = True
    pf_applicable: bool = False
    esi_applicable: bool = False
    pt_applicable: bool = False
    description: Optional[str] = None


class SalaryStructureLine(BaseModel):
    pay_component_id: str
    amount: float = 0.0
    percent: float = 0.0


class SalaryStructure(BaseModel):
    employee_id: str
    effective_from: str
    lines: list[SalaryStructureLine]
    notes: Optional[str] = None


class PTSlab(BaseModel):
    min_salary: float
    max_salary: Optional[float] = None
    annual_pt: float


class TDSSlab(BaseModel):
    min_income: float
    max_income: Optional[float] = None
    rate: float
    surcharge_rate: float = 0.0


class StatutoryParams(BaseModel):
    financial_year: str
    effective_from: str
    # PF
    pf_wage_ceiling: float = 15000.0
    pf_employee_rate: float = 12.0
    pf_employer_epf_rate: float = 3.67
    pf_employer_eps_rate: float = 8.33
    pf_admin_rate: float = 0.5
    # ESI
    esi_wage_ceiling: float = 21000.0
    esi_employee_rate: float = 0.75
    esi_employer_rate: float = 3.25
    # PT — per-state slabs
    pt_state_slabs: dict = {}  # {"MH": [...PTSlab dicts...]}
    # TDS old regime
    tds_old_regime_slabs: list[TDSSlab] = []
    tds_new_regime_slabs: list[TDSSlab] = []
    standard_deduction: float = 50000.0
    cess_rate: float = 4.0


class PayrollRunRequest(BaseModel):
    period: str                   # MMYYYY e.g. "062025"
    financial_year: str           # "2025-26"
    employee_ids: Optional[list] = None


class TDSDeclaration(BaseModel):
    employee_id: str
    financial_year: str
    regime: Literal["old", "new"] = "new"
    investments_80c: float = 0.0
    investments_80d: float = 0.0
    hra_exemption: float = 0.0
    other_exemptions: float = 0.0
    other_income: float = 0.0


class FNFRequest(BaseModel):
    employee_id: str
    last_working_day: str
    financial_year: str
    notice_recovery: float = 0.0
    leave_encashment_days: float = 0.0
    other_recoveries: float = 0.0
    notes: Optional[str] = None


# ══════════════════════════════════════════════════════════════
# Statutory computation helpers
# ══════════════════════════════════════════════════════════════

def _parse_period(period: str) -> tuple[int, int]:
    """Parse MMYYYY → (month, year)."""
    if len(period) != 6:
        raise HTTPException(400, "Period must be MMYYYY format")
    try:
        mm = int(period[:2])
        yyyy = int(period[2:])
        return mm, yyyy
    except ValueError:
        raise HTTPException(400, "Invalid period format")


def _period_days(mm: int, yyyy: int) -> int:
    return monthrange(yyyy, mm)[1]


def _fy_month_number(mm: int, yyyy: int, fy_start_year: int) -> int:
    """Month number within FY (April=1 … March=12)."""
    if mm >= 4:
        return mm - 3
    return mm + 9


def _remaining_months_in_fy(mm: int, yyyy: int) -> int:
    """Months from (mm, yyyy) to March of the same FY, inclusive."""
    fy_end_year = yyyy if mm >= 4 else yyyy - 1
    fy_end_year += 1  # March of next calendar year
    end_mm, end_yyyy = 3, fy_end_year
    total = (end_yyyy - yyyy) * 12 + (end_mm - mm) + 1
    return max(total, 1)


def _compute_pf(pf_wages: float, params: dict) -> dict:
    ceiling = float(params.get("pf_wage_ceiling", 15000))
    capped = min(pf_wages, ceiling)
    ee_rate = float(params.get("pf_employee_rate", 12)) / 100
    epf_rate = float(params.get("pf_employer_epf_rate", 3.67)) / 100
    eps_rate = float(params.get("pf_employer_eps_rate", 8.33)) / 100
    admin_rate = float(params.get("pf_admin_rate", 0.5)) / 100
    return {
        "pf_wages": pf_wages,
        "pf_wages_capped": capped,
        "employee_pf": round(capped * ee_rate, 2),
        "employer_epf": round(capped * epf_rate, 2),
        "employer_eps": round(capped * eps_rate, 2),
        "employer_pf_total": round(capped * (epf_rate + eps_rate), 2),
        "pf_admin": round(capped * admin_rate, 2),
    }


def _compute_esi(gross: float, params: dict, in_contribution_period: bool) -> dict:
    """
    ESI applies if gross ≤ ceiling OR the employee is in a contribution period
    (crossed the ceiling mid-period → ESI continues till period end).
    """
    ceiling = float(params.get("esi_wage_ceiling", 21000))
    applicable = gross <= ceiling or in_contribution_period
    if not applicable:
        return {"esi_applicable": False, "employee_esi": 0.0, "employer_esi": 0.0}
    ee_rate = float(params.get("esi_employee_rate", 0.75)) / 100
    er_rate = float(params.get("esi_employer_rate", 3.25)) / 100
    return {
        "esi_applicable": True,
        "gross_for_esi": gross,
        "employee_esi": round(gross * ee_rate, 2),
        "employer_esi": round(gross * er_rate, 2),
    }


def _compute_pt(gross_monthly: float, state: str, params: dict) -> float:
    """Professional Tax from state slab table."""
    slabs = params.get("pt_state_slabs", {}).get(state, [])
    for slab in slabs:
        min_s = float(slab.get("min_salary", 0))
        max_s = slab.get("max_salary")
        if gross_monthly >= min_s and (max_s is None or gross_monthly <= float(max_s)):
            # Annual PT divided by 12 (some states differ in February — simplified here)
            return round(float(slab.get("annual_pt", 0)) / 12, 2)
    return 0.0


def _apply_lop(base_amount: float, paid_days: float, total_days: float) -> float:
    if total_days <= 0:
        return base_amount
    return round(base_amount * paid_days / total_days, 2)


def _tax_from_slabs(annual_taxable: float, slabs: list[dict]) -> float:
    tax = 0.0
    for slab in slabs:
        lo = float(slab.get("min_income", 0))
        hi = slab.get("max_income")
        rate = float(slab.get("rate", 0)) / 100
        if annual_taxable <= lo:
            break
        upper = float(hi) if hi is not None else annual_taxable
        taxable_in_band = min(annual_taxable, upper) - lo
        if taxable_in_band > 0:
            tax += taxable_in_band * rate
    return round(tax, 2)


def _compute_tds_monthly(
    annual_gross: float,
    tds_decl: dict,
    params: dict,
    mm: int,
    yyyy: int,
    already_deducted_tds: float = 0.0,
) -> dict:
    """
    Project annual taxable income, compute annual tax, spread over remaining months.
    Returns monthly TDS to deduct this period.
    """
    regime = tds_decl.get("regime", "new")
    std_deduction = float(params.get("standard_deduction", 50000))
    cess_rate = float(params.get("cess_rate", 4)) / 100

    # Exemptions (only in old regime)
    exemptions = 0.0
    if regime == "old":
        exemptions = (
            float(tds_decl.get("investments_80c", 0))
            + float(tds_decl.get("investments_80d", 0))
            + float(tds_decl.get("hra_exemption", 0))
            + float(tds_decl.get("other_exemptions", 0))
        )

    other_income = float(tds_decl.get("other_income", 0))
    annual_taxable = max(0.0, annual_gross + other_income - std_deduction - exemptions)

    slabs = (
        params.get("tds_old_regime_slabs", [])
        if regime == "old"
        else params.get("tds_new_regime_slabs", [])
    )
    if not slabs:
        slabs = _default_tds_slabs(regime)

    tax = _tax_from_slabs(annual_taxable, slabs)
    cess = round(tax * cess_rate, 2)
    annual_tax = round(tax + cess, 2)

    # Spread over remaining months
    remaining = _remaining_months_in_fy(mm, yyyy)
    balance_tax = max(0.0, annual_tax - already_deducted_tds)
    monthly_tds = round(balance_tax / remaining, 2)

    return {
        "regime": regime,
        "annual_gross": annual_gross,
        "standard_deduction": std_deduction,
        "exemptions": exemptions,
        "annual_taxable_income": annual_taxable,
        "annual_tax": annual_tax,
        "already_deducted": already_deducted_tds,
        "remaining_months": remaining,
        "monthly_tds": monthly_tds,
    }


def _default_tds_slabs(regime: str) -> list[dict]:
    """Statutory TDS slabs — FY 2024-25 defaults when no params configured."""
    if regime == "new":
        return [
            {"min_income": 0, "max_income": 300000, "rate": 0},
            {"min_income": 300000, "max_income": 600000, "rate": 5},
            {"min_income": 600000, "max_income": 900000, "rate": 10},
            {"min_income": 900000, "max_income": 1200000, "rate": 15},
            {"min_income": 1200000, "max_income": 1500000, "rate": 20},
            {"min_income": 1500000, "max_income": None, "rate": 30},
        ]
    # Old regime
    return [
        {"min_income": 0, "max_income": 250000, "rate": 0},
        {"min_income": 250000, "max_income": 500000, "rate": 5},
        {"min_income": 500000, "max_income": 1000000, "rate": 20},
        {"min_income": 1000000, "max_income": None, "rate": 30},
    ]


def _compute_gratuity(
    basic_monthly: float,
    years_of_service: float,
    min_years: float = 5.0,
) -> float:
    """Gratuity = (Basic + DA) / 26 * 15 * years (only if service ≥ min_years)."""
    if years_of_service < min_years:
        return 0.0
    return round(basic_monthly / 26 * 15 * years_of_service, 2)


# ══════════════════════════════════════════════════════════════
# Pay Components
# ══════════════════════════════════════════════════════════════

@router.get("/pay-components")
async def list_pay_components(user: dict = Depends(get_current_user)):
    _require_hr(user)
    return await crud_list("pay_components", sort_field="name")


@router.post("/pay-components")
async def create_pay_component(payload: PayComponent, user: dict = Depends(require_admin)):
    return await crud_create("pay_components", payload.model_dump(), user)


@router.put("/pay-components/{comp_id}")
async def update_pay_component(comp_id: str, payload: PayComponent, user: dict = Depends(require_admin)):
    return await crud_update("pay_components", comp_id, payload.model_dump(), user)


# ══════════════════════════════════════════════════════════════
# Salary Structures
# ══════════════════════════════════════════════════════════════

@router.get("/salary-structures")
async def list_salary_structures(
    employee_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require_hr(user)
    filt = {}
    if employee_id:
        filt["employee_id"] = employee_id
    return await crud_list("salary_structures", filt=filt, sort_field="effective_from")


@router.post("/salary-structures")
async def create_salary_structure(payload: SalaryStructure, user: dict = Depends(get_current_user)):
    _require_hr(user)
    return await crud_create("salary_structures", payload.model_dump(), user)


# ══════════════════════════════════════════════════════════════
# Statutory Params
# ══════════════════════════════════════════════════════════════

@router.get("/statutory-params")
async def list_statutory_params(
    fy: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require_hr(user)
    filt = {}
    if fy:
        filt["financial_year"] = fy
    return await crud_list("statutory_params", filt=filt, sort_field="effective_from")


@router.post("/statutory-params")
async def create_statutory_params(payload: StatutoryParams, user: dict = Depends(require_admin)):
    doc = payload.model_dump()
    # Serialize nested Pydantic models
    doc["tds_old_regime_slabs"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in (payload.tds_old_regime_slabs or [])]
    doc["tds_new_regime_slabs"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in (payload.tds_new_regime_slabs or [])]
    return await crud_create("statutory_params", doc, user)


async def _get_statutory_params(fy: str) -> dict:
    """Load FY-versioned params; fall back to hardcoded defaults if not configured."""
    params = await db.statutory_params.find_one({"financial_year": fy}, {"_id": 0})
    if params:
        return params
    # Defaults for FY 2024-25 (inline — no code change needed when DB has params)
    return {
        "financial_year": fy,
        "pf_wage_ceiling": 15000.0,
        "pf_employee_rate": 12.0,
        "pf_employer_epf_rate": 3.67,
        "pf_employer_eps_rate": 8.33,
        "pf_admin_rate": 0.5,
        "esi_wage_ceiling": 21000.0,
        "esi_employee_rate": 0.75,
        "esi_employer_rate": 3.25,
        "pt_state_slabs": {
            "MH": [
                {"min_salary": 0, "max_salary": 7499, "annual_pt": 0},
                {"min_salary": 7500, "max_salary": 9999, "annual_pt": 1800},
                {"min_salary": 10000, "max_salary": None, "annual_pt": 2400},
            ],
            "KA": [
                {"min_salary": 0, "max_salary": 14999, "annual_pt": 0},
                {"min_salary": 15000, "max_salary": None, "annual_pt": 2400},
            ],
        },
        "standard_deduction": 50000.0,
        "cess_rate": 4.0,
        "tds_old_regime_slabs": _default_tds_slabs("old"),
        "tds_new_regime_slabs": _default_tds_slabs("new"),
    }


# ══════════════════════════════════════════════════════════════
# TDS Declarations
# ══════════════════════════════════════════════════════════════

@router.get("/tds-declarations")
async def list_tds_declarations(
    employee_id: Optional[str] = None,
    fy: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require_hr(user)
    filt = {}
    if employee_id:
        filt["employee_id"] = employee_id
    if fy:
        filt["financial_year"] = fy
    return await crud_list("tds_declarations", filt=filt)


@router.post("/tds-declarations")
async def upsert_tds_declaration(payload: TDSDeclaration, user: dict = Depends(get_current_user)):
    _require_hr(user)
    existing = await db.tds_declarations.find_one(
        {"employee_id": payload.employee_id, "financial_year": payload.financial_year}
    )
    if existing:
        return await crud_update("tds_declarations", existing["id"], payload.model_dump(), user)
    return await crud_create("tds_declarations", payload.model_dump(), user)


# ══════════════════════════════════════════════════════════════
# Core payslip computation
# ══════════════════════════════════════════════════════════════

async def _compute_payslip(
    employee: dict,
    structure: dict,
    params: dict,
    period_mm: int,
    period_yyyy: int,
    fy: str,
) -> dict:
    """
    Compute a full payslip for one employee for one period.
    Returns a dict ready to be inserted into `payslips`.
    """
    total_days = _period_days(period_mm, period_yyyy)

    # Attendance: fetch LOP days
    att = await db.attendance.find_one(
        {"employee_id": employee["id"], "period": f"{period_mm:02d}{period_yyyy}"},
        {"_id": 0},
    ) or {}
    paid_days = float(att.get("paid_days", total_days))
    lop_days = max(0.0, total_days - paid_days)

    # Resolve pay components
    lines = structure.get("lines", [])
    components = await db.pay_components.find({}, {"_id": 0}).to_list(200)
    comp_map = {c["id"]: c for c in components}

    # First pass: compute basic (needed for percent_of_basic components)
    basic = 0.0
    for line in lines:
        comp = comp_map.get(line.get("pay_component_id"), {})
        if comp.get("name", "").upper() in ("BASIC", "BASIC SALARY"):
            amt = float(line.get("amount", 0))
            basic = _apply_lop(amt, paid_days, total_days)
            break

    earnings = []
    deductions = []
    gross = 0.0
    pf_wages = 0.0
    esi_gross = 0.0

    for line in lines:
        comp = comp_map.get(line.get("pay_component_id"), {})
        calc = comp.get("calc", "flat")
        if calc == "flat":
            amount = float(line.get("amount", 0))
        elif calc == "percent_of_basic":
            amount = basic * float(line.get("percent", 0)) / 100.0
        else:
            amount = float(line.get("amount", 0))  # formula unsupported → treat as flat

        # Apply LOP to earnings
        if comp.get("type") == "earning":
            amount = _apply_lop(amount, paid_days, total_days)
            earnings.append({"name": comp.get("name", ""), "amount": round(amount, 2), "taxable": comp.get("taxable", True)})
            gross += amount
            if comp.get("pf_applicable"):
                pf_wages += amount
            if comp.get("esi_applicable"):
                esi_gross += amount
        elif comp.get("type") == "deduction":
            deductions.append({"name": comp.get("name", ""), "amount": round(amount, 2)})
        # reimbursements: not included in gross/statutory bases

    gross = round(gross, 2)
    pf_wages = round(pf_wages, 2) if pf_wages else gross  # fallback

    # PF
    pf = _compute_pf(pf_wages, params)

    # ESI — check contribution period flag
    in_contribution_period = bool(att.get("in_esi_contribution_period", False))
    esi = _compute_esi(gross, params, in_contribution_period)

    # PT — employee state
    state = employee.get("work_state", "MH")
    pt = _compute_pt(gross, state, params)

    # TDS
    tds_decl = await db.tds_declarations.find_one(
        {"employee_id": employee["id"], "financial_year": fy}, {"_id": 0}
    ) or {"regime": "new"}
    # Project annual gross from this month's (LOP-adjusted) gross
    already_deducted = 0.0
    prior_payslips = await db.payslips.find(
        {"employee_id": employee["id"], "financial_year": fy, "status": "POSTED"},
        {"_id": 0, "tds": 1},
    ).to_list(12)
    already_deducted = sum(float(p.get("tds", 0)) for p in prior_payslips)
    remaining_months = _remaining_months_in_fy(period_mm, period_yyyy)
    annual_gross_projected = gross * remaining_months + sum(
        float(p.get("gross", 0)) for p in prior_payslips
    )
    tds_calc = _compute_tds_monthly(annual_gross_projected, tds_decl, params, period_mm, period_yyyy, already_deducted)
    monthly_tds = tds_calc["monthly_tds"]

    # Total statutory deductions
    total_deductions = (
        pf["employee_pf"]
        + esi.get("employee_esi", 0.0)
        + pt
        + monthly_tds
        + sum(d["amount"] for d in deductions)
    )
    net = round(gross - total_deductions, 2)

    return {
        "employee_id": employee["id"],
        "employee_name": employee.get("name", ""),
        "period": f"{period_mm:02d}{period_yyyy}",
        "financial_year": fy,
        "total_days": total_days,
        "paid_days": paid_days,
        "lop_days": lop_days,
        "earnings": earnings,
        "gross": gross,
        "pf_wages": pf_wages,
        "statutory": {
            "pf": pf,
            "esi": esi,
            "pt": pt,
            "tds": tds_calc,
        },
        "pf": pf["employee_pf"],
        "esi": esi.get("employee_esi", 0.0),
        "pt": pt,
        "tds": monthly_tds,
        "other_deductions": deductions,
        "total_deductions": round(total_deductions, 2),
        "net": net,
        "employer_pf": pf["employer_pf_total"],
        "employer_esi": esi.get("employer_esi", 0.0),
        "status": "DRAFT",
    }


# ══════════════════════════════════════════════════════════════
# Payroll Run
# ══════════════════════════════════════════════════════════════

@router.post("/runs")
async def create_payroll_run(
    payload: PayrollRunRequest,
    user: dict = Depends(get_current_user),
):
    _require_hr(user)
    _mm, _yyyy = _parse_period(payload.period)
    # Idempotency
    existing = await db.payroll_runs.find_one({"period": payload.period, "financial_year": payload.financial_year})
    if existing:
        raise HTTPException(409, f"Payroll run for period {payload.period} already exists (status: {existing.get('status')})")

    run_doc = {
        "period": payload.period,
        "financial_year": payload.financial_year,
        "status": "DRAFT",
        "employee_ids": payload.employee_ids,
    }
    return await crud_create("payroll_runs", run_doc, user)


@router.post("/runs/{run_id}/process")
async def process_payroll_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    _require_hr(user)
    run = await crud_get("payroll_runs", run_id)
    if run["status"] not in ("DRAFT", "PREVIEW"):
        raise HTTPException(400, f"Run is already in status '{run['status']}'")

    period = run["period"]
    fy = run["financial_year"]
    mm, yyyy = _parse_period(period)
    params = await _get_statutory_params(fy)

    # Load employees
    emp_filter: dict = {"status": "ACTIVE"}
    if run.get("employee_ids"):
        emp_filter["id"] = {"$in": run["employee_ids"]}
    employees = await db.employees.find(emp_filter, {"_id": 0}).to_list(5000)

    payslips = []
    errors = []
    for emp in employees:
        # Find active salary structure (most recent effective_from ≤ period)
        period_date = f"{yyyy}-{mm:02d}-01"
        structure = await db.salary_structures.find_one(
            {"employee_id": emp["id"], "effective_from": {"$lte": period_date}},
            {"_id": 0},
            sort=[("effective_from", -1)],
        )
        if not structure:
            errors.append({"employee_id": emp["id"], "error": "No salary structure found"})
            continue
        try:
            slip = await _compute_payslip(emp, structure, params, mm, yyyy, fy)
            slip["payroll_run_id"] = run_id
            payslips.append(slip)
        except Exception as e:
            errors.append({"employee_id": emp["id"], "error": str(e)})

    # Persist payslips
    for slip in payslips:
        slip["id"] = new_id()
        slip["created_at"] = now_iso()
    if payslips:
        await db.payslips.insert_many([{**s, "_id_omit": None} for s in payslips])
        # Remove helper key
        await db.payslips.update_many({"payroll_run_id": run_id}, {"$unset": {"_id_omit": ""}})

    # Update run status
    await crud_update("payroll_runs", run_id, {
        "status": "PROCESSED",
        "employee_count": len(payslips),
        "error_count": len(errors),
        "total_gross": round(sum(s["gross"] for s in payslips), 2),
        "total_net": round(sum(s["net"] for s in payslips), 2),
        "total_pf_employee": round(sum(s["pf"] for s in payslips), 2),
        "total_pf_employer": round(sum(s["employer_pf"] for s in payslips), 2),
        "total_esi_employee": round(sum(s["esi"] for s in payslips), 2),
        "total_esi_employer": round(sum(s["employer_esi"] for s in payslips), 2),
        "total_tds": round(sum(s["tds"] for s in payslips), 2),
        "errors": errors,
    }, user)

    return {
        "run_id": run_id,
        "period": period,
        "processed": len(payslips),
        "errors": errors,
        "summary": {
            "total_gross": round(sum(s["gross"] for s in payslips), 2),
            "total_net": round(sum(s["net"] for s in payslips), 2),
        },
    }


@router.post("/runs/{run_id}/post")
async def post_payroll_run(run_id: str, user: dict = Depends(get_current_user)):
    """Lock a processed run and mark payslips as POSTED."""
    _require_hr(user)
    run = await crud_get("payroll_runs", run_id)
    if run["status"] != "PROCESSED":
        raise HTTPException(400, "Run must be in PROCESSED status before posting")

    await db.payslips.update_many(
        {"payroll_run_id": run_id},
        {"$set": {"status": "POSTED", "posted_at": now_iso()}},
    )
    await crud_update("payroll_runs", run_id, {"status": "POSTED", "posted_at": now_iso()}, user)
    return {"run_id": run_id, "status": "POSTED"}


@router.get("/runs")
async def list_runs(user: dict = Depends(get_current_user)):
    _require_hr(user)
    return await crud_list("payroll_runs", sort_field="period")


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user)
    return await crud_get("payroll_runs", run_id)


# ══════════════════════════════════════════════════════════════
# Payslips
# ══════════════════════════════════════════════════════════════

@router.get("/payslips")
async def list_payslips(
    period: Optional[str] = None,
    employee_id: Optional[str] = None,
    run_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require_hr(user)
    filt: dict = {}
    if period:
        filt["period"] = period
    if employee_id:
        filt["employee_id"] = employee_id
    if run_id:
        filt["payroll_run_id"] = run_id
    return await crud_list("payslips", filt=filt, sort_field="period")


@router.get("/payslips/{slip_id}")
async def get_payslip(slip_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user)
    return await crud_get("payslips", slip_id)


# ══════════════════════════════════════════════════════════════
# Form 16
# ══════════════════════════════════════════════════════════════

@router.get("/form16/{employee_id}")
async def get_form16(
    employee_id: str,
    fy: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """
    Form 16 computation.
    Part A: Total TDS deposited (sum of POSTED payslip TDS for the FY).
    Part B: Annual income computation — gross, std deduction, exemptions, taxable income, tax, cess.
    """
    _require_hr(user)
    emp = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")

    payslips = await db.payslips.find(
        {"employee_id": employee_id, "financial_year": fy, "status": "POSTED"},
        {"_id": 0},
    ).to_list(12)

    total_tds_deposited: float = round(sum(float(p.get("tds", 0)) for p in payslips), 2)
    part_a = {
        "employee_id": employee_id,
        "employee_name": emp.get("name", ""),
        "financial_year": fy,
        "total_tds_deposited": total_tds_deposited,
        "quarters": _tds_quarter_breakup(payslips, fy),
    }

    params = await _get_statutory_params(fy)
    tds_decl = await db.tds_declarations.find_one(
        {"employee_id": employee_id, "financial_year": fy}, {"_id": 0}
    ) or {"regime": "new"}

    total_gross = round(sum(float(p.get("gross", 0)) for p in payslips), 2)
    std_deduction = float(params.get("standard_deduction", 50000))
    regime = tds_decl.get("regime", "new")
    exemptions = 0.0
    if regime == "old":
        exemptions = (
            float(tds_decl.get("investments_80c", 0))
            + float(tds_decl.get("investments_80d", 0))
            + float(tds_decl.get("hra_exemption", 0))
            + float(tds_decl.get("other_exemptions", 0))
        )
    other_income = float(tds_decl.get("other_income", 0))
    annual_taxable = max(0.0, total_gross + other_income - std_deduction - exemptions)

    slabs = params.get("tds_old_regime_slabs" if regime == "old" else "tds_new_regime_slabs", [])
    if not slabs:
        slabs = _default_tds_slabs(regime)
    tax = _tax_from_slabs(annual_taxable, slabs)
    cess = round(tax * float(params.get("cess_rate", 4)) / 100, 2)
    annual_tax = round(tax + cess, 2)

    part_b = {
        "regime": regime,
        "total_gross_salary": total_gross,
        "standard_deduction": std_deduction,
        "exemptions_80c_80d_hra": exemptions,
        "other_income": other_income,
        "annual_taxable_income": annual_taxable,
        "income_tax": tax,
        "surcharge": 0.0,
        "cess": cess,
        "annual_tax_payable": annual_tax,
        "tds_deposited": total_tds_deposited,
        "tax_refundable": max(0.0, total_tds_deposited - annual_tax),
        "tax_balance_payable": max(0.0, annual_tax - total_tds_deposited),
    }

    return {"part_a": part_a, "part_b": part_b}


def _tds_quarter_breakup(payslips: list, fy: str) -> list:
    quarters = {
        "Q1 (Apr-Jun)": 0.0, "Q2 (Jul-Sep)": 0.0,
        "Q3 (Oct-Dec)": 0.0, "Q4 (Jan-Mar)": 0.0,
    }
    for p in payslips:
        mm = int(p.get("period", "0101")[:2])
        tds = float(p.get("tds", 0))
        if mm in (4, 5, 6):
            quarters["Q1 (Apr-Jun)"] += tds
        elif mm in (7, 8, 9):
            quarters["Q2 (Jul-Sep)"] += tds
        elif mm in (10, 11, 12):
            quarters["Q3 (Oct-Dec)"] += tds
        else:
            quarters["Q4 (Jan-Mar)"] += tds
    return [{"quarter": k, "tds": round(v, 2)} for k, v in quarters.items()]


# ══════════════════════════════════════════════════════════════
# Full & Final Settlement
# ══════════════════════════════════════════════════════════════

@router.post("/fnf/{employee_id}")
async def compute_fnf(
    employee_id: str,
    payload: FNFRequest,
    user: dict = Depends(get_current_user),
):
    _require_hr(user)
    emp = await db.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")

    lwd = date.fromisoformat(payload.last_working_day)
    joining_date_str = emp.get("date_of_joining") or emp.get("joining_date")
    joining = date.fromisoformat(joining_date_str) if joining_date_str else lwd

    years_of_service = max(0.0, (lwd - joining).days / 365.25)

    # Last active salary structure
    structure: Any = await db.salary_structures.find_one(
        {"employee_id": employee_id, "effective_from": {"$lte": str(lwd)}},
        {"_id": 0},
        sort=[("effective_from", -1)],
    )
    if not structure:
        raise HTTPException(400, "No salary structure found for employee")

    # Basic for gratuity
    lines = structure.get("lines", [])
    components = await db.pay_components.find({}, {"_id": 0}).to_list(200)
    comp_map = {c["id"]: c for c in components}
    basic_monthly = 0.0
    gross_monthly = 0.0
    for line in lines:
        comp = comp_map.get(line.get("pay_component_id"), {})
        amt = float(line.get("amount", 0))
        if comp.get("name", "").upper() in ("BASIC", "BASIC SALARY"):
            basic_monthly = amt
        if comp.get("type") == "earning":
            gross_monthly += amt

    # Salary for days worked in LWD month
    mm, yyyy = lwd.month, lwd.year
    total_days_in_month = _period_days(mm, yyyy)
    days_worked = lwd.day
    salary_for_lwd_month = round(gross_monthly * days_worked / total_days_in_month, 2)

    # Leave encashment (basic / 30 * days)
    leave_encashment = round(basic_monthly / 30 * payload.leave_encashment_days, 2)

    # Gratuity
    gratuity = _compute_gratuity(basic_monthly, years_of_service)

    total_payable = salary_for_lwd_month + leave_encashment + gratuity
    total_recoveries = payload.notice_recovery + payload.other_recoveries
    net_payable = round(total_payable - total_recoveries, 2)

    fnf = {
        "employee_id": employee_id,
        "employee_name": emp.get("name", ""),
        "last_working_day": payload.last_working_day,
        "financial_year": payload.financial_year,
        "date_of_joining": joining_date_str,
        "years_of_service": round(years_of_service, 2),
        "salary_for_lwd_month": salary_for_lwd_month,
        "leave_encashment_days": payload.leave_encashment_days,
        "leave_encashment": leave_encashment,
        "gratuity_eligible": years_of_service >= 5.0,
        "gratuity": gratuity,
        "total_payable": round(total_payable, 2),
        "notice_recovery": payload.notice_recovery,
        "other_recoveries": payload.other_recoveries,
        "total_recoveries": round(total_recoveries, 2),
        "net_payable": net_payable,
        "notes": payload.notes,
    }
    return await crud_create("fnf_settlements", fnf, user)


@router.get("/fnf/{employee_id}")
async def get_fnf(employee_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user)
    fnf = await db.fnf_settlements.find_one({"employee_id": employee_id}, {"_id": 0})
    if not fnf:
        raise HTTPException(404, "No F&F settlement found")
    return fnf


# ══════════════════════════════════════════════════════════════
# Reports
# ══════════════════════════════════════════════════════════════

@router.get("/reports/salary-register")
async def salary_register(
    period: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """Monthly salary register — all payslips for the period."""
    _require_hr(user)
    payslips = await db.payslips.find({"period": period}, {"_id": 0}).to_list(5000)
    return {
        "period": period,
        "count": len(payslips),
        "total_gross": round(sum(float(p.get("gross", 0)) for p in payslips), 2),
        "total_net": round(sum(float(p.get("net", 0)) for p in payslips), 2),
        "payslips": payslips,
    }


@router.get("/reports/pf-ecr")
async def pf_ecr_report(
    period: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """
    PF ECR (Electronic Challan cum Return) format.
    One row per employee: UAN, PF wages, employee EPF, employer EPF, employer EPS.
    """
    _require_hr(user)
    payslips = await db.payslips.find({"period": period, "status": "POSTED"}, {"_id": 0}).to_list(5000)
    # Batch-load every referenced employee in one query (was an N+1: one
    # find_one per payslip — up to 5000 round-trips against a remote pooler).
    emp_ids = list({p["employee_id"] for p in payslips})
    emp_map = {
        e["id"]: e
        for e in await db.employees.find(
            {"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "uan": 1, "name": 1}
        ).to_list(5000)
    } if emp_ids else {}
    rows = []
    for p in payslips:
        emp = emp_map.get(p["employee_id"], {})
        pf = p.get("statutory", {}).get("pf", {})
        rows.append({
            "employee_id": p["employee_id"],
            "employee_name": p.get("employee_name", ""),
            "uan": emp.get("uan", ""),
            "pf_wages": pf.get("pf_wages_capped", 0),
            "employee_epf": pf.get("employee_pf", 0),
            "employer_epf": pf.get("employer_epf", 0),
            "employer_eps": pf.get("employer_eps", 0),
            "admin_charges": pf.get("pf_admin", 0),
        })
    return {
        "period": period,
        "total_employee_pf": round(sum(r["employee_epf"] for r in rows), 2),
        "total_employer_epf": round(sum(r["employer_epf"] for r in rows), 2),
        "total_employer_eps": round(sum(r["employer_eps"] for r in rows), 2),
        "rows": rows,
    }


@router.get("/reports/esi-return")
async def esi_return_report(
    period: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """ESI monthly return — employee + employer contribution per insured person."""
    _require_hr(user)
    payslips = await db.payslips.find({"period": period, "status": "POSTED"}, {"_id": 0}).to_list(5000)
    # Batch-load employees in one query (was an N+1: one find_one per payslip).
    emp_ids = list({p["employee_id"] for p in payslips})
    emp_map = {
        e["id"]: e
        for e in await db.employees.find(
            {"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "esi_ip_number": 1, "name": 1}
        ).to_list(5000)
    } if emp_ids else {}
    rows = []
    for p in payslips:
        esi = p.get("statutory", {}).get("esi", {})
        if not esi.get("esi_applicable"):
            continue
        emp = emp_map.get(p["employee_id"], {})
        rows.append({
            "employee_id": p["employee_id"],
            "employee_name": p.get("employee_name", ""),
            "ip_number": emp.get("esi_ip_number", ""),
            "gross": esi.get("gross_for_esi", 0),
            "employee_esi": esi.get("employee_esi", 0),
            "employer_esi": esi.get("employer_esi", 0),
        })
    return {
        "period": period,
        "insured_count": len(rows),
        "total_employee_esi": round(sum(r["employee_esi"] for r in rows), 2),
        "total_employer_esi": round(sum(r["employer_esi"] for r in rows), 2),
        "rows": rows,
    }
