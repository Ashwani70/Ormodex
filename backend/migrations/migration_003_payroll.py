"""Migration 003 — Payroll: JSON Schema validators + indexes + seed statutory defaults."""
import logging

logger = logging.getLogger(__name__)


async def run(db):
    # ── pay_components ───────────────────────────────────────────────────────
    await db.command({
        "collMod": "pay_components",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "name", "type", "calc"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "name": {"bsonType": "string"},
                    "type": {"bsonType": "string", "enum": ["earning", "deduction", "reimbursement"]},
                    "calc": {"bsonType": "string", "enum": ["flat", "percent_of_basic", "formula"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.pay_components.create_index("id", unique=True)
    await db.pay_components.create_index("name")

    # ── salary_structures ────────────────────────────────────────────────────
    await db.command({
        "collMod": "salary_structures",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "employee_id", "effective_from"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "employee_id": {"bsonType": "string"},
                    "effective_from": {"bsonType": "string"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.salary_structures.create_index("id", unique=True)
    await db.salary_structures.create_index([("employee_id", 1), ("effective_from", -1)])

    # ── statutory_params ─────────────────────────────────────────────────────
    await db.command({
        "collMod": "statutory_params",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "financial_year"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "financial_year": {"bsonType": "string"},
                    "pf_wage_ceiling": {"bsonType": ["int", "double"]},
                    "esi_wage_ceiling": {"bsonType": ["int", "double"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.statutory_params.create_index("id", unique=True)
    await db.statutory_params.create_index("financial_year")

    # ── payroll_runs ─────────────────────────────────────────────────────────
    await db.command({
        "collMod": "payroll_runs",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "period", "financial_year", "status"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "period": {"bsonType": "string"},
                    "status": {"bsonType": "string", "enum": ["DRAFT", "PROCESSED", "POSTED", "CANCELLED"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.payroll_runs.create_index("id", unique=True)
    await db.payroll_runs.create_index([("period", 1), ("financial_year", 1)], unique=True)

    # ── payslips ──────────────────────────────────────────────────────────────
    await db.command({
        "collMod": "payslips",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "employee_id", "period", "status"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "employee_id": {"bsonType": "string"},
                    "period": {"bsonType": "string"},
                    "status": {"bsonType": "string", "enum": ["DRAFT", "POSTED", "CANCELLED"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.payslips.create_index("id", unique=True)
    await db.payslips.create_index([("employee_id", 1), ("period", 1)])
    await db.payslips.create_index([("run_id", 1)])
    await db.payslips.create_index([("financial_year", 1), ("status", 1)])

    # ── tds_declarations ─────────────────────────────────────────────────────
    await db.tds_declarations.create_index("id", unique=True, sparse=True)
    await db.tds_declarations.create_index([("employee_id", 1), ("financial_year", 1)], unique=True)

    # ── fnf_settlements ──────────────────────────────────────────────────────
    await db.fnf_settlements.create_index("id", unique=True, sparse=True)
    await db.fnf_settlements.create_index("employee_id")

    # ── attendance (ensure index) ──────────────────────────────────────────
    await db.attendance.create_index([("employee_id", 1), ("period", 1)])

    logger.info("Migration 003 — Payroll applied")

    await _seed_payroll_defaults(db)


async def _seed_payroll_defaults(db):
    """Seed standard pay components and FY 2024-25 statutory params if absent."""
    if await db.pay_components.count_documents({}) == 0:
        from core.utils import new_id, now_iso
        components = [
            {"id": new_id(), "name": "Basic Salary", "type": "earning", "calc": "flat", "taxable": True, "pf_applicable": True, "esi_applicable": True, "pt_applicable": True, "created_at": now_iso()},
            {"id": new_id(), "name": "HRA", "type": "earning", "calc": "percent_of_basic", "taxable": False, "pf_applicable": False, "esi_applicable": True, "pt_applicable": False, "created_at": now_iso()},
            {"id": new_id(), "name": "Special Allowance", "type": "earning", "calc": "flat", "taxable": True, "pf_applicable": False, "esi_applicable": True, "pt_applicable": False, "created_at": now_iso()},
            {"id": new_id(), "name": "Conveyance Allowance", "type": "earning", "calc": "flat", "taxable": True, "pf_applicable": False, "esi_applicable": True, "pt_applicable": False, "created_at": now_iso()},
            {"id": new_id(), "name": "Medical Reimbursement", "type": "reimbursement", "calc": "flat", "taxable": False, "pf_applicable": False, "esi_applicable": False, "pt_applicable": False, "created_at": now_iso()},
            {"id": new_id(), "name": "Advance Recovery", "type": "deduction", "calc": "flat", "taxable": False, "pf_applicable": False, "esi_applicable": False, "pt_applicable": False, "created_at": now_iso()},
        ]
        await db.pay_components.insert_many(components)

    if await db.statutory_params.count_documents({}) == 0:
        from core.utils import new_id, now_iso
        from routers.payroll import _default_tds_slabs
        params = {
            "id": new_id(),
            "financial_year": "2024-25",
            "effective_from": "2024-04-01",
            "pf_wage_ceiling": 15000.0,
            "pf_employee_rate": 12.0,
            "pf_employer_epf_rate": 3.67,
            "pf_employer_eps_rate": 8.33,
            "pf_admin_rate": 0.5,
            "esi_wage_ceiling": 21000.0,
            "esi_employee_rate": 0.75,
            "esi_employer_rate": 3.25,
            "standard_deduction": 50000.0,
            "cess_rate": 4.0,
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
                "TN": [
                    {"min_salary": 0, "max_salary": None, "annual_pt": 0},
                ],
            },
            "tds_old_regime_slabs": _default_tds_slabs("old"),
            "tds_new_regime_slabs": _default_tds_slabs("new"),
            "created_at": now_iso(),
        }
        await db.statutory_params.insert_one(params)
