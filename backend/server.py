"""Slim FastAPI entry point. All business logic lives in routers/ and core/."""
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import logging
import os

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from core.db import db, close_db
from core.seed import seed_admin, seed_demo_data
from core.storage import init_storage
from routers.auth import router as auth_router
from routers.users import router as users_router
from routers.inventory import router as inventory_router
from routers.purchase import router as purchase_router
from routers.sales import router as sales_router
from routers.proforma import router as proforma_router
from routers.email import router as email_router
from routers.reports import router as reports_router
from routers.hr_setup import router as hr_setup_router
from routers.hr_employees import router as hr_employees_router
from routers.hr_attendance import router as hr_attendance_router
from routers.hr_payroll import router as hr_payroll_router
from routers.accounting import router as accounting_router
from routers.gst_accounting import router as gst_accounting_router
from routers.expense_mgmt import router as expense_mgmt_router
from routers.ledger import router as ledger_router
from routers.vouchers import router as vouchers_router
from routers.mis_reports import router as mis_reports_router
from routers.ai_assistant import router as ai_assistant_router
from routers.theme_settings import router as theme_settings_router
from routers.company import router as company_router
from routers.job_work import router as job_work_router
from routers.verifications import router as verifications_router
from routers.manufacturing import router as manufacturing_router
from routers.garment import router as garment_router
from routers.banking import router as banking_router
from routers.budget import router as budget_router
from routers.stock_analysis import router as stock_analysis_router
from routers.fixed_assets import router as fixed_assets_router
from routers.payroll import router as payroll_router
from routers.banking_pdc import router as banking_pdc_router
from routers.approvals import router as approvals_router
from routers.reports_engine import router as reports_engine_router
from routers.pricing import router as pricing_router
from routers.portal import router as portal_router
from routers.projects import router as projects_router
from routers.pos import router as pos_router
from routers.integration import router as integration_router
from routers.public_api import router as public_api_router
from routers.branches import router as branches_router
from routers.audit import router as audit_router
from routers.inventory_v2 import router as inventory_v2_router
from routers.purchase_v2 import router as purchase_v2_router
from routers.masters import router as masters_router, create_masters_indexes
from routers.voucher_engine_router import router as voucher_engine_router, create_voucher_engine_indexes
from migrations.migration_001_manufacturing_deep import run as _run_migration_001
from migrations.migration_002_fixed_assets import run as _run_migration_002
from migrations.migration_003_payroll import run as _run_migration_003
from migrations.migration_004_banking import run as _run_migration_004
from migrations.migration_005_approvals import run as _run_migration_005
from migrations.migration_006_reports import run as _run_migration_006
from migrations.migration_007_pricing import run as _run_migration_007
from migrations.migration_008_portal import run as _run_migration_008
from migrations.migration_009_projects import run as _run_migration_009
from migrations.migration_010_pos import run as _run_migration_010
from migrations.migration_011_integration import run as _run_migration_011
from migrations.migration_012_branches import run as _run_migration_012


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.users.create_index("email", unique=True)
    await db.products.create_index("sku", unique=True)
    await db.warehouses.create_index("name")
    await seed_admin()
    await seed_demo_data()
    try:
        await _run_migration_001(db)
        logger.info("Migration 001 applied")
    except Exception as e:
        logger.warning(f"Migration 001 skipped or failed (non-fatal): {e}")
    try:
        await _run_migration_002(db)
        logger.info("Migration 002 applied")
    except Exception as e:
        logger.warning(f"Migration 002 skipped or failed (non-fatal): {e}")
    try:
        await _run_migration_003(db)
        logger.info("Migration 003 applied")
    except Exception as e:
        logger.warning(f"Migration 003 skipped or failed (non-fatal): {e}")
    try:
        await _run_migration_004(db)
        logger.info("Migration 004 applied")
    except Exception as e:
        logger.warning(f"Migration 004 skipped or failed (non-fatal): {e}")
    try:
        await _run_migration_005(db)
        logger.info("Migration 005 applied")
    except Exception as e:
        logger.warning(f"Migration 005 skipped or failed (non-fatal): {e}")
    try:
        await _run_migration_006(db)
        logger.info("Migration 006 applied")
    except Exception as e:
        logger.warning(f"Migration 006 skipped or failed (non-fatal): {e}")
    try:
        await _run_migration_007(db)
        logger.info("Migration 007 applied")
    except Exception as e:
        logger.warning(f"Migration 007 skipped or failed (non-fatal): {e}")
    try:
        await _run_migration_008(db)
        logger.info("Migration 008 applied")
    except Exception as e:
        logger.warning(f"Migration 008 skipped or failed (non-fatal): {e}")
    try:
        await _run_migration_009(db)
        logger.info("Migration 009 applied")
    except Exception as e:
        logger.warning(f"Migration 009 skipped or failed (non-fatal): {e}")
    try:
        await _run_migration_010(db)
        logger.info("Migration 010 applied")
    except Exception as e:
        logger.warning(f"Migration 010 skipped or failed (non-fatal): {e}")
    try:
        await _run_migration_011(db)
        logger.info("Migration 011 applied")
    except Exception as e:
        logger.warning(f"Migration 011 skipped or failed (non-fatal): {e}")
    try:
        await _run_migration_012(db)
        logger.info("Migration 012 applied")
    except Exception as e:
        logger.warning(f"Migration 012 skipped or failed (non-fatal): {e}")
    try:
        await create_masters_indexes(db)
        logger.info("Masters compound (tenant_id, ...) indexes ensured")
    except Exception as e:
        logger.warning(f"Masters index creation skipped or failed (non-fatal): {e}")
    try:
        await create_voucher_engine_indexes(db)
        logger.info("Voucher engine compound (tenant_id, ...) indexes ensured")
    except Exception as e:
        logger.warning(f"Voucher engine index creation skipped or failed (non-fatal): {e}")
    try:
        init_storage()
        logger.info("Object storage initialised")
    except Exception as e:
        logger.warning(f"Object storage init failed (uploads disabled): {e}")

    yield

    close_db()


app = FastAPI(title="GravityOne ERP", lifespan=lifespan)

frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        frontend_url,
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"name": "GravityOne ERP", "status": "ok"}


# Mount feature routers
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(inventory_router)
api_router.include_router(purchase_router)
api_router.include_router(sales_router)
api_router.include_router(proforma_router)
api_router.include_router(email_router)
api_router.include_router(reports_router)
api_router.include_router(hr_setup_router)
api_router.include_router(hr_employees_router)
api_router.include_router(hr_attendance_router)
api_router.include_router(hr_payroll_router)
api_router.include_router(accounting_router)
api_router.include_router(gst_accounting_router)
api_router.include_router(expense_mgmt_router)
api_router.include_router(ledger_router)
api_router.include_router(vouchers_router)
api_router.include_router(mis_reports_router)
api_router.include_router(ai_assistant_router)
api_router.include_router(theme_settings_router)
api_router.include_router(company_router)
api_router.include_router(job_work_router)
api_router.include_router(verifications_router)
api_router.include_router(manufacturing_router)
api_router.include_router(garment_router)
api_router.include_router(banking_router)
api_router.include_router(budget_router)
api_router.include_router(stock_analysis_router)
api_router.include_router(fixed_assets_router)
api_router.include_router(payroll_router)
api_router.include_router(banking_pdc_router)
api_router.include_router(approvals_router)
api_router.include_router(reports_engine_router)
api_router.include_router(pricing_router)
api_router.include_router(portal_router)
api_router.include_router(projects_router)
api_router.include_router(pos_router)
api_router.include_router(integration_router)
api_router.include_router(public_api_router)
api_router.include_router(branches_router)
api_router.include_router(audit_router)
api_router.include_router(inventory_v2_router)
api_router.include_router(purchase_v2_router)
api_router.include_router(masters_router)
api_router.include_router(voucher_engine_router)


app.include_router(api_router)

# Versioned API alias: all major router groups are also reachable under /api/v1/*
# (spec convention) in addition to the existing /api/* paths. Same router objects,
# so behaviour is identical — no duplication, no breakage of /api/*.
v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(masters_router)
v1_router.include_router(voucher_engine_router)
v1_router.include_router(accounting_router)
v1_router.include_router(gst_accounting_router)
v1_router.include_router(ledger_router)
v1_router.include_router(vouchers_router)
v1_router.include_router(inventory_v2_router)
v1_router.include_router(purchase_v2_router)
v1_router.include_router(banking_router)
v1_router.include_router(banking_pdc_router)
v1_router.include_router(budget_router)
v1_router.include_router(expense_mgmt_router)
v1_router.include_router(hr_setup_router)
v1_router.include_router(hr_employees_router)
v1_router.include_router(hr_attendance_router)
v1_router.include_router(hr_payroll_router)
v1_router.include_router(payroll_router)
v1_router.include_router(manufacturing_router)
v1_router.include_router(job_work_router)
v1_router.include_router(sales_router)
v1_router.include_router(purchase_router)
v1_router.include_router(inventory_router)
v1_router.include_router(fixed_assets_router)
v1_router.include_router(approvals_router)
v1_router.include_router(verifications_router)
v1_router.include_router(ai_assistant_router)
v1_router.include_router(mis_reports_router)
v1_router.include_router(stock_analysis_router)
v1_router.include_router(reports_router)
v1_router.include_router(reports_engine_router)
v1_router.include_router(pricing_router)
v1_router.include_router(projects_router)
v1_router.include_router(branches_router)
v1_router.include_router(audit_router)
v1_router.include_router(portal_router)
v1_router.include_router(pos_router)
v1_router.include_router(company_router)
v1_router.include_router(theme_settings_router)
app.include_router(v1_router)




