"""Slim FastAPI entry point. All business logic lives in routers/ and core/."""
# Trigger reload for new DB bootstrap
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env", override=True)

import asyncio
import logging
import os

from fastapi import APIRouter, Depends, FastAPI, Request
from starlette.middleware.cors import CORSMiddleware

from core.compression import SkipAlreadyCompressedGZipMiddleware

from core.db import (
    AsyncSessionLocal,
    Base,
    bind_request_session,
    close_db,
    engine,
    unbind_request_session,
    warm_pool,
)
from core.seed import seed_admin, seed_demo_data, seed_default_coa
from core.storage import init_storage
from routers.auth import router as auth_router
from routers.mfa import router as mfa_router
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
from routers.biometric_attendance import router as biometric_attendance_router
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
from routers.masters import router as masters_router
from routers.voucher_engine_router import router as voucher_engine_router
from routers.categories import router as categories_router
from routers.po_numbering import router as po_numbering_router
from routers.document_numbering import router as document_numbering_router
from routers.cheque_printing import router as cheque_printing_router
from routers.debtors_creditors import router as debtors_creditors_router
from routers.letterhead_designer import router as letterhead_designer_router
from routers.search import router as search_router
from routers.stock_log import router as stock_log_router


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bootstrap schema (idempotent — IF NOT EXISTS semantics).
    #
    # `create_all` runs a per-table reflection check before issuing any DDL, so
    # against a remote Postgres (e.g. Supabase) it costs one network round-trip
    # per model (118+ tables ≈ 20s) on EVERY boot — even when nothing is missing.
    # That made startup look hung. We first do a single cheap COUNT against the
    # catalog and skip the expensive bootstrap once the expected tables exist.
    from sqlalchemy import text

    # DDL (create_all + column drift) is a dev/local convenience only. In
    # production the schema is owned by Alembic migrations, so never auto-DDL
    # there — it can mask drift, race across replicas, and bypass review.
    is_prod = os.environ.get("ENV", "development").lower() == "production"
    if is_prod:
        logger.info("Production environment — skipping schema bootstrap (managed by Alembic migrations)")
    else:
        expected = len(Base.metadata.tables)
        schema_bootstrapped = False
        async with engine.begin() as conn:
            present = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
            ).scalar() or 0
            if present < expected:
                await conn.run_sync(Base.metadata.create_all)
                schema_bootstrapped = True
                logger.info("PostgreSQL schema bootstrapped (created missing tables)")
            else:
                logger.info("PostgreSQL schema present (%s tables) — bootstrap skipped", present)

        # Column-level drift: create_all never ALTERs existing tables. Only run
        # when we just created tables — NOT on every boot. Running ~80 ALTER TABLE
        # round-trips to a remote Supabase pooler added 15–30s to startup for no
        # benefit once the schema is already present (Alembic owns prod drift).
        if schema_bootstrapped or os.environ.get("SCHEMA_DRIFT_SYNC", "").lower() in ("1", "true", "yes"):
            _drift_columns = [
                # auth
                ("users", "username", "varchar", "NULL"),
                ("users", "mfa_enabled", "boolean", "false"),
                ("users", "mfa_secret", "varchar", "NULL"),
                ("users", "mfa_pending_secret", "varchar", "NULL"),
                ("users", "mfa_recovery_hashes", "jsonb", "NULL"),
                ("users", "password_change_required", "boolean", "false"),
                ("users", "password_history", "jsonb", "'[]'::jsonb"),
                ("users", "last_password_change", "varchar", "NULL"),
                ("users", "failed_login_count", "integer", "0"),
                ("users", "locked_until", "varchar", "NULL"),
                ("users", "is_locked", "boolean", "false"),
                ("users", "force_change_reason", "varchar", "NULL"),
                ("users", "last_login_at", "varchar", "NULL"),
                ("users", "last_login_ip", "varchar", "NULL"),
                # stock
                ("stock_transactions", "balance", "numeric", "NULL"),
                ("stock_transactions", "delta", "numeric", "NULL"),
                ("stock_transactions", "product_id", "varchar", "NULL"),
                ("stock_transactions", "product_name", "varchar", "NULL"),
                ("stock_transactions", "reason", "varchar", "NULL"),
                ("stock_transactions", "user_id", "varchar", "NULL"),
                ("stock_transactions", "user_name", "varchar", "NULL"),
                ("stock_transactions", "created_by", "varchar", "NULL"),
                # purchase_bills — new columns missing from migrated table
                ("purchase_bills", "vendor_invoice_no",   "varchar", "NULL"),
                ("purchase_bills", "vendor_invoice_date", "varchar", "NULL"),
                ("purchase_bills", "vendor_name",         "varchar", "NULL"),
                ("purchase_bills", "purchase_order_id",   "varchar", "NULL"),
                ("purchase_bills", "grn_ids",             "jsonb",   "'[]'::jsonb"),
                ("purchase_bills", "taxable",             "numeric", "NULL"),
                ("purchase_bills", "total",               "numeric", "NULL"),
                ("purchase_bills", "tds_rate",            "numeric", "0"),
                ("purchase_bills", "journal_entry_id",    "varchar", "NULL"),
                # vendor_bill_submissions
                ("vendor_bill_submissions", "bill_date", "varchar", "NULL"),
                ("vendor_bill_submissions", "description", "varchar", "NULL"),
                ("vendor_bill_submissions", "file_ref", "varchar", "NULL"),
                ("vendor_bill_submissions", "linked_purchase_invoice_id", "varchar", "NULL"),
                ("vendor_bill_submissions", "submission_no", "varchar", "NULL"),
                ("po_number_audit", "changed_by_name", "varchar", "NULL"),
                ("po_number_audit", "new_po_number", "varchar", "NULL"),
                ("po_number_audit", "old_po_number", "varchar", "NULL"),
                ("po_number_audit", "purchase_order_id", "varchar", "NULL"),
                # sales
                ("invoices", "approval_state", "varchar", "NULL"),
                ("invoices", "invoice_number", "varchar", "NULL"),
                ("invoices", "invoice_type", "varchar", "NULL"),
                ("invoices", "source_bill_submission_id", "varchar", "NULL"),
                ("invoices", "supplier_id", "varchar", "NULL"),
                ("invoices", "total", "numeric", "NULL"),
                ("payment_links", "gateway", "varchar", "NULL"),
                ("payment_links", "party_id", "varchar", "NULL"),
                ("payment_links", "txn_ref", "varchar", "NULL"),
                # chart_of_accounts — missing functional columns
                ("chart_of_accounts", "description", "varchar", "NULL"),
                ("chart_of_accounts", "is_active", "boolean", "true"),
                ("chart_of_accounts", "opening_balance", "numeric", "0"),
                ("chart_of_accounts", "currency", "varchar", "'INR'"),
                ("chart_of_accounts", "tags", "jsonb", "'[]'::jsonb"),
                # accounting
                ("journal_entries", "cgst", "numeric", "NULL"),
                ("journal_entries", "created_by", "varchar", "NULL"),
                ("journal_entries", "created_by_name", "varchar", "NULL"),
                ("journal_entries", "date", "varchar", "NULL"),
                ("journal_entries", "entry_number", "varchar", "NULL"),
                ("journal_entries", "fiscal_year", "varchar", "NULL"),
                ("journal_entries", "igst", "numeric", "NULL"),
                ("journal_entries", "party_id", "varchar", "NULL"),
                ("journal_entries", "party_name", "varchar", "NULL"),
                ("journal_entries", "party_type", "varchar", "NULL"),
                ("journal_entries", "reference", "varchar", "NULL"),
                ("journal_entries", "sgst", "numeric", "NULL"),
                ("journal_entries", "source_collection", "varchar", "NULL"),
                ("journal_entries", "tags", "jsonb", "'{}'::jsonb"),
                ("journal_entries", "taxable_amount", "numeric", "NULL"),
                ("journal_entries", "total_credit", "numeric", "NULL"),
                ("journal_entries", "total_debit", "numeric", "NULL"),
                ("vouchers", "date", "varchar", "NULL"),
                ("vouchers", "party_id", "varchar", "NULL"),
                ("vouchers", "party_name", "varchar", "NULL"),
                ("vouchers", "party_type", "varchar", "NULL"),
                ("vouchers", "payment_link_id", "varchar", "NULL"),
                ("vouchers", "payment_mode", "varchar", "NULL"),
                ("vouchers", "pos_sale_id", "varchar", "NULL"),
                ("vouchers", "reference_doc", "varchar", "NULL"),
                ("vouchers", "source", "varchar", "NULL"),
                ("vouchers", "voucher_number", "varchar", "NULL"),
                # HR / payroll
                ("leave_types", "paid", "boolean", "true"),
                ("advances", "recovery_month", "varchar", "NULL"),
                # GST / e-way bill
                ("gst_records", "cess", "numeric", "NULL"),
                ("gst_records", "cgst", "numeric", "NULL"),
                ("gst_records", "created_by", "varchar", "NULL"),
                ("gst_records", "filing_status", "varchar", "NULL"),
                ("gst_records", "gst_type", "varchar", "NULL"),
                ("gst_records", "igst", "numeric", "NULL"),
                ("gst_records", "invoice_date", "varchar", "NULL"),
                ("gst_records", "invoice_number", "varchar", "NULL"),
                ("gst_records", "linked_invoice_id", "varchar", "NULL"),
                ("gst_records", "party_name", "varchar", "NULL"),
                ("gst_records", "return_period", "varchar", "NULL"),
                ("gst_records", "sgst", "numeric", "NULL"),
                ("gst_records", "source", "varchar", "NULL"),
                ("gst_records", "taxable_amount", "numeric", "NULL"),
                ("gst_records", "total_amount", "numeric", "NULL"),
                ("eway_bills", "created_by", "varchar", "NULL"),
                ("eway_bills", "distance_km", "numeric", "NULL"),
                ("eway_bills", "environment", "varchar", "NULL"),
                ("eway_bills", "ewb_date", "varchar", "NULL"),
                ("eway_bills", "from_gstin", "varchar", "NULL"),
                ("eway_bills", "government_response", "jsonb", "'{}'::jsonb"),
                ("eway_bills", "invoice_date", "varchar", "NULL"),
                ("eway_bills", "invoice_id", "varchar", "NULL"),
                ("eway_bills", "invoice_number", "varchar", "NULL"),
                ("eway_bills", "qr_value", "varchar", "NULL"),
                ("eway_bills", "simulated", "boolean", "false"),
                ("eway_bills", "to_gstin", "varchar", "NULL"),
                ("eway_bills", "total_invoice_value", "numeric", "NULL"),
                ("eway_bills", "trans_doc_no", "varchar", "NULL"),
                ("eway_bills", "transport_mode", "varchar", "NULL"),
                ("eway_bills", "transporter_id", "varchar", "NULL"),
                ("eway_bills", "transporter_name", "varchar", "NULL"),
                ("eway_bills", "valid_until_iso", "varchar", "NULL"),
                ("eway_bills", "vehicle_number", "varchar", "NULL"),
                # fixed assets
                ("asset_depreciation_runs", "asset_code", "varchar", "NULL"),
                ("asset_depreciation_runs", "asset_description", "varchar", "NULL"),
                ("asset_depreciation_runs", "asset_id", "varchar", "NULL"),
                ("asset_depreciation_runs", "basis", "varchar", "NULL"),
                ("asset_depreciation_runs", "closing_wdv", "numeric", "NULL"),
                ("asset_depreciation_runs", "days_held", "integer", "NULL"),
                ("asset_depreciation_runs", "depreciation", "numeric", "NULL"),
                ("asset_depreciation_runs", "financial_year", "varchar", "NULL"),
                ("asset_depreciation_runs", "gross_value", "numeric", "NULL"),
                ("asset_depreciation_runs", "is_fully_depreciated", "boolean", "false"),
                ("asset_depreciation_runs", "method", "varchar", "NULL"),
                ("asset_depreciation_runs", "opening_wdv", "numeric", "NULL"),
                ("asset_depreciation_runs", "residual_value", "numeric", "NULL"),
                ("asset_depreciation_runs", "total_fy_days", "integer", "NULL"),
                # POS
                ("pos_sales", "cashier_id", "varchar", "NULL"),
                ("pos_sales", "change", "numeric", "NULL"),
                ("pos_sales", "client_uuid", "varchar", "NULL"),
                ("pos_sales", "created_at_client", "varchar", "NULL"),
                ("pos_sales", "customer_id", "varchar", "NULL"),
                ("pos_sales", "customer_name", "varchar", "NULL"),
                ("pos_sales", "is_interstate", "boolean", "false"),
                ("pos_sales", "payment", "jsonb", "'{}'::jsonb"),
                ("pos_sales", "place_of_supply", "varchar", "NULL"),
                ("pos_sales", "receipt_no", "varchar", "NULL"),
                ("pos_sales", "tendered", "numeric", "NULL"),
                ("pos_sales", "terminal", "varchar", "NULL"),
                ("pos_sales", "voided", "boolean", "false"),
                ("pos_sessions", "cashier_id", "varchar", "NULL"),
                ("pos_sessions", "cashier_name", "varchar", "NULL"),
                ("pos_sessions", "session_no", "varchar", "NULL"),
                ("pos_sessions", "terminal", "varchar", "NULL"),
                # integrations
                ("webhook_subscriptions", "active", "boolean", "true"),
                ("webhook_subscriptions", "max_attempts", "integer", "3"),
                ("api_keys", "active", "boolean", "true"),
                ("api_keys", "created_by", "varchar", "NULL"),
                ("api_keys", "key_prefix", "varchar", "NULL"),
                ("portal_users", "name", "varchar", "NULL"),
                ("portal_users", "status", "varchar", "NULL"),
                # reports
                ("report_saved_views", "params", "jsonb", "'{}'::jsonb"),
                ("report_saved_views", "slug", "varchar", "NULL"),
                ("report_saved_views", "user_id", "varchar", "NULL"),
                # files
                ("uploaded_files", "content_type", "varchar", "NULL"),
                ("uploaded_files", "original_filename", "varchar", "NULL"),
                # branches
                ("inter_branch_transfers", "created_by", "varchar", "NULL"),
                ("inter_branch_transfers", "eway_bill_no", "varchar", "NULL"),
                ("inter_branch_transfers", "eway_bill_required", "boolean", "false"),
                ("inter_branch_transfers", "from_branch", "varchar", "NULL"),
                ("inter_branch_transfers", "from_branch_name", "varchar", "NULL"),
                ("inter_branch_transfers", "from_gstin", "varchar", "NULL"),
                ("inter_branch_transfers", "in_voucher_id", "varchar", "NULL"),
                ("inter_branch_transfers", "items", "jsonb", "'[]'::jsonb"),
                ("inter_branch_transfers", "out_voucher_id", "varchar", "NULL"),
                ("inter_branch_transfers", "to_branch", "varchar", "NULL"),
                ("inter_branch_transfers", "to_branch_name", "varchar", "NULL"),
                ("inter_branch_transfers", "to_gstin", "varchar", "NULL"),
                # PO numbering
                ("po_numbering_settings", "mode", "varchar", "'AUTO'"),
                ("po_numbering_settings", "fy_format", "varchar", "''"),
                ("po_numbering_settings", "branch_code", "varchar", "''"),
                ("po_numbering_settings", "separator", "varchar", "'-'"),
                ("po_numbering_settings", "start_sequence", "integer", "1"),
                ("po_numbering_settings", "sequence_length", "integer", "5"),
                ("po_numbering_settings", "updated_by", "varchar", "NULL"),
                # stock_ledger_entries — real write fields that post_entry uses
                ("stock_ledger_entries", "qty",             "numeric", "NULL"),
                ("stock_ledger_entries", "value",           "numeric", "NULL"),
                ("stock_ledger_entries", "movement_type",   "varchar", "NULL"),
                ("stock_ledger_entries", "source_doc_type", "varchar", "NULL"),
                ("stock_ledger_entries", "entry_date",      "varchar", "NULL"),
                ("stock_ledger_entries", "serial_id",       "varchar", "NULL"),
                ("stock_ledger_entries", "extra",           "jsonb",   "NULL"),
                # stock_transactions — Stock Log rebuild: human-readable voucher
                # number (source_doc_id is an opaque row id, not display-friendly)
                ("stock_transactions", "voucher_no", "varchar", "NULL"),
            ]
            async with engine.begin() as conn:
                for _tbl, _col, _type, _default in _drift_columns:
                    try:
                        await conn.execute(text(
                            f"ALTER TABLE IF EXISTS {_tbl} "
                            f"ADD COLUMN IF NOT EXISTS {_col} {_type} DEFAULT {_default}"
                        ))
                    except Exception:
                        logger.warning(f"Could not add drift column {_tbl}.{_col} — skipping")
            logger.info("Drift columns reconciled")

    # Always ensure stock_ledger_entries has the columns that post_entry writes.
    # These were missing from the initial schema migration, causing all inventory
    # reports to return empty/zero results. Idempotent — ADD COLUMN IF NOT EXISTS.
    _stock_ledger_fix = """
        ALTER TABLE IF EXISTS stock_ledger_entries ADD COLUMN IF NOT EXISTS qty             NUMERIC(18,4) DEFAULT NULL;
        ALTER TABLE IF EXISTS stock_ledger_entries ADD COLUMN IF NOT EXISTS value           NUMERIC(18,4) DEFAULT NULL;
        ALTER TABLE IF EXISTS stock_ledger_entries ADD COLUMN IF NOT EXISTS movement_type   TEXT DEFAULT NULL;
        ALTER TABLE IF EXISTS stock_ledger_entries ADD COLUMN IF NOT EXISTS source_doc_type TEXT DEFAULT NULL;
        ALTER TABLE IF EXISTS stock_ledger_entries ADD COLUMN IF NOT EXISTS entry_date      TEXT DEFAULT NULL;
        ALTER TABLE IF EXISTS stock_ledger_entries ADD COLUMN IF NOT EXISTS serial_id       TEXT DEFAULT NULL;
        ALTER TABLE IF EXISTS stock_ledger_entries ADD COLUMN IF NOT EXISTS extra           JSONB DEFAULT NULL;
        ALTER TABLE IF EXISTS stock_ledger_entries ADD COLUMN IF NOT EXISTS product_id      TEXT DEFAULT NULL;
        ALTER TABLE IF EXISTS stock_ledger_entries ADD COLUMN IF NOT EXISTS product_name    TEXT DEFAULT NULL;
        ALTER TABLE IF EXISTS stock_ledger_entries ADD COLUMN IF NOT EXISTS user_id         TEXT DEFAULT NULL;
        ALTER TABLE IF EXISTS stock_ledger_entries ADD COLUMN IF NOT EXISTS user_name       TEXT DEFAULT NULL;
        ALTER TABLE IF EXISTS stock_ledger_entries ADD COLUMN IF NOT EXISTS reason          TEXT DEFAULT NULL;
        UPDATE stock_ledger_entries SET entry_date = txn_date   WHERE entry_date IS NULL AND txn_date IS NOT NULL;
        UPDATE stock_ledger_entries SET qty = COALESCE(qty_in,0) - COALESCE(qty_out,0) WHERE qty IS NULL AND (qty_in IS NOT NULL OR qty_out IS NOT NULL);
        UPDATE stock_ledger_entries SET value = COALESCE(value_in,0) - COALESCE(value_out,0) WHERE value IS NULL AND (value_in IS NOT NULL OR value_out IS NOT NULL);
        UPDATE stock_ledger_entries SET source_doc_type = doc_type WHERE source_doc_type IS NULL AND doc_type IS NOT NULL;
    """
    try:
        async with engine.begin() as conn:
            for _stmt in [s.strip() for s in _stock_ledger_fix.strip().split(";") if s.strip()]:
                await conn.execute(text(_stmt))
        logger.info("stock_ledger_entries schema ensured")
    except Exception as _e:
        logger.warning("stock_ledger_entries schema fix skipped (non-fatal): %s", _e)

    # stock_transactions (the legacy mirror Stock Log actually reads) never
    # got source_doc_type even though stock_ledger_entries above did — so the
    # "view voucher" drill-down couldn't tell a v2 GRN apart from a plain PO
    # receive (both doc_type="PURCHASE") and always routed to /purchase-orders.
    # Mirrors alembic migration 026. Idempotent — ADD COLUMN IF NOT EXISTS.
    _stock_txn_source_type_fix = """
        ALTER TABLE IF EXISTS stock_transactions ADD COLUMN IF NOT EXISTS source_doc_type TEXT DEFAULT NULL;
        UPDATE stock_transactions SET source_doc_type = doc_type WHERE source_doc_type IS NULL AND doc_type IS NOT NULL;
    """
    try:
        async with engine.begin() as conn:
            for _stmt in [s.strip() for s in _stock_txn_source_type_fix.strip().split(";") if s.strip()]:
                await conn.execute(text(_stmt))
        logger.info("stock_transactions.source_doc_type ensured")
    except Exception as _e:
        logger.warning("stock_transactions source_doc_type fix skipped (non-fatal): %s", _e)

    # document_numbering_settings — generalized AUTO/MANUAL numbering config
    # for document types beyond Purchase Order (which keeps its own dedicated
    # po_numbering_settings table) and Vouchers (own VoucherType-driven
    # system). Mirrors alembic migration 027. Idempotent.
    _document_numbering_ddl = """
        CREATE TABLE IF NOT EXISTS document_numbering_settings (
            id TEXT PRIMARY KEY,
            mode TEXT DEFAULT 'AUTO',
            prefix TEXT DEFAULT '',
            fy_format TEXT DEFAULT '',
            branch_code TEXT DEFAULT '',
            separator TEXT DEFAULT '-',
            start_sequence INTEGER DEFAULT 1,
            sequence_length INTEGER DEFAULT 5,
            updated_at TEXT,
            updated_by TEXT
        );
    """
    try:
        async with engine.begin() as conn:
            for _stmt in [s.strip() for s in _document_numbering_ddl.strip().split(";") if s.strip()]:
                await conn.execute(text(_stmt))
        logger.info("document_numbering_settings table ensured")
    except Exception as _e:
        logger.warning("document_numbering_settings table fix skipped (non-fatal): %s", _e)

    # Valuation-engine columns: standard_cost (per-unit std for STANDARD_COST
    # method) and extra (JSONB, back-compat home for standard_cost on old rows).
    # Idempotent — the valuation resolver reads these, so they must exist before
    # any STANDARD_COST item is priced. Mirrors alembic migration 020.
    _stock_item_valuation_fix = """
        ALTER TABLE IF EXISTS stock_items ADD COLUMN IF NOT EXISTS standard_cost NUMERIC(18,4) DEFAULT NULL;
        ALTER TABLE IF EXISTS stock_items ADD COLUMN IF NOT EXISTS extra         JSONB         DEFAULT NULL;
    """
    try:
        async with engine.begin() as conn:
            for _stmt in [s.strip() for s in _stock_item_valuation_fix.strip().split(";") if s.strip()]:
                await conn.execute(text(_stmt))
        logger.info("stock_items valuation columns ensured")
    except Exception as _e:
        logger.warning("stock_items valuation schema fix skipped (non-fatal): %s", _e)

    # Stock Log fix: source_doc_id index for voucher drill-down/backfill lookups
    # on both tables. Mirrors alembic migration 021 (plain CREATE INDEX here,
    # not CONCURRENTLY, since this runs inside the same transaction as the
    # other startup drift-ensure statements above).
    _stock_log_index_fix = """
        CREATE INDEX IF NOT EXISTS ix_stock_txn_source_doc_id ON stock_transactions (source_doc_id);
        CREATE INDEX IF NOT EXISTS ix_stock_ledger_source_doc_id ON stock_ledger_entries (source_doc_id);
    """
    try:
        async with engine.begin() as conn:
            for _stmt in [s.strip() for s in _stock_log_index_fix.strip().split(";") if s.strip()]:
                await conn.execute(text(_stmt))
        logger.info("stock_log source_doc_id indexes ensured")
    except Exception as _e:
        logger.warning("stock_log index fix skipped (non-fatal): %s", _e)

    # Ledger→Chart of Accounts link: voucher_engine stamps account_code onto
    # journal lines by resolving each line's ledger_id through this column.
    # Without it, Trial Balance/P&L/Balance Sheet KeyError on any
    # voucher-engine-posted entry (they group strictly by account_code).
    # Mirrors alembic migration 023.
    _ledger_coa_link_fix = """
        ALTER TABLE IF EXISTS master_ledgers ADD COLUMN IF NOT EXISTS coa_account_id TEXT DEFAULT NULL;
        CREATE INDEX IF NOT EXISTS ix_master_ledgers_coa_account_id ON master_ledgers (coa_account_id);
    """
    try:
        async with engine.begin() as conn:
            for _stmt in [s.strip() for s in _ledger_coa_link_fix.strip().split(";") if s.strip()]:
                await conn.execute(text(_stmt))
        logger.info("master_ledgers.coa_account_id ensured")
    except Exception as _e:
        logger.warning("ledger CoA link fix skipped (non-fatal): %s", _e)

    # eSSL Biometric Attendance Integration: fixes attendance's silently-
    # dropped columns (check_in/check_out/working_hours/overtime_hours/source
    # had no matching ORM column and no extra/data catch-all, so the Mongo-
    # compat shim's insert_one/update_one dropped them on every write) and
    # adds the payroll-aggregate columns (period/paid_days/total_days) plus
    # the new device/mapping/sync-run/rule tables. Mirrors alembic migration 024.
    _biometric_attendance_fix = """
        ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS check_in TEXT;
        ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS check_out TEXT;
        ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS working_hours NUMERIC(18,4);
        ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS overtime_hours NUMERIC(18,4);
        ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS source TEXT;
        ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS late BOOLEAN;
        ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS early_leave BOOLEAN;
        ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS missing_punch BOOLEAN;
        ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS remarks TEXT;
        ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS period TEXT;
        ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS paid_days NUMERIC(18,4);
        ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS total_days INTEGER;
        CREATE INDEX IF NOT EXISTS ix_attendance_employee_period ON attendance (employee_id, period);
        ALTER TABLE IF EXISTS attendance_logs ADD COLUMN IF NOT EXISTS employee_code TEXT;
        ALTER TABLE IF EXISTS attendance_logs ADD COLUMN IF NOT EXISTS dedup_key TEXT;
        ALTER TABLE IF EXISTS attendance_logs ADD COLUMN IF NOT EXISTS sync_run_id TEXT;
        ALTER TABLE IF EXISTS attendance_logs ADD COLUMN IF NOT EXISTS source TEXT;
        ALTER TABLE IF EXISTS attendance_logs ADD COLUMN IF NOT EXISTS raw_payload JSONB;
        ALTER TABLE IF EXISTS attendance_logs ADD COLUMN IF NOT EXISTS processed BOOLEAN DEFAULT FALSE;
        ALTER TABLE IF EXISTS attendance_logs ADD COLUMN IF NOT EXISTS processed_at TEXT;
        CREATE UNIQUE INDEX IF NOT EXISTS ix_attendance_logs_dedup_key ON attendance_logs (dedup_key);
        CREATE INDEX IF NOT EXISTS ix_attendance_logs_tenant_device ON attendance_logs (tenant_id, device_id);
        CREATE INDEX IF NOT EXISTS ix_attendance_logs_tenant_time ON attendance_logs (tenant_id, log_time);
        CREATE TABLE IF NOT EXISTS biometric_devices (
            id TEXT PRIMARY KEY, tenant_id TEXT, name TEXT, serial_number TEXT,
            branch_id TEXT, device_model TEXT, integration_mode TEXT, host TEXT,
            port INTEGER DEFAULT 4370, api_path TEXT, push_secret TEXT,
            poll_interval_seconds INTEGER DEFAULT 300, is_active BOOLEAN DEFAULT TRUE,
            last_sync_at TEXT, last_sync_status TEXT, last_seen_at TEXT, notes TEXT,
            is_deleted BOOLEAN DEFAULT FALSE, deleted_at TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_biometric_devices_tenant_id ON biometric_devices (tenant_id);
        CREATE INDEX IF NOT EXISTS ix_biometric_devices_tenant_branch ON biometric_devices (tenant_id, branch_id);
        CREATE TABLE IF NOT EXISTS employee_device_mappings (
            id TEXT PRIMARY KEY, tenant_id TEXT, device_id TEXT, employee_id TEXT,
            device_enrollment_id TEXT, is_active BOOLEAN DEFAULT TRUE, created_at TEXT, updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_emp_device_map_tenant_id ON employee_device_mappings (tenant_id);
        CREATE INDEX IF NOT EXISTS ix_emp_device_map_tenant_device ON employee_device_mappings (tenant_id, device_id);
        CREATE INDEX IF NOT EXISTS ix_emp_device_map_tenant_employee ON employee_device_mappings (tenant_id, employee_id);
        CREATE UNIQUE INDEX IF NOT EXISTS ix_emp_device_map_device_enrollment ON employee_device_mappings (device_id, device_enrollment_id);
        CREATE TABLE IF NOT EXISTS attendance_sync_runs (
            id TEXT PRIMARY KEY, tenant_id TEXT, device_id TEXT, trigger TEXT, status TEXT,
            started_at TEXT, finished_at TEXT, punches_fetched INTEGER DEFAULT 0,
            punches_new INTEGER DEFAULT 0, punches_duplicate INTEGER DEFAULT 0,
            error_message TEXT, attempt INTEGER DEFAULT 1, next_attempt_at TEXT,
            triggered_by TEXT, created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_att_sync_runs_tenant_id ON attendance_sync_runs (tenant_id);
        CREATE INDEX IF NOT EXISTS ix_att_sync_runs_tenant_device ON attendance_sync_runs (tenant_id, device_id);
        CREATE INDEX IF NOT EXISTS ix_att_sync_runs_status ON attendance_sync_runs (tenant_id, status);
        CREATE TABLE IF NOT EXISTS attendance_rules (
            id TEXT PRIMARY KEY, tenant_id TEXT, shift_id TEXT,
            late_grace_minutes INTEGER DEFAULT 10, early_leave_grace_minutes INTEGER DEFAULT 10,
            half_day_threshold_hours NUMERIC(18,4), full_day_threshold_hours NUMERIC(18,4),
            overtime_after_hours NUMERIC(18,4), missing_punch_action TEXT,
            is_active BOOLEAN DEFAULT TRUE, created_at TEXT, updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_attendance_rules_tenant_id ON attendance_rules (tenant_id);
    """
    try:
        async with engine.begin() as conn:
            for _stmt in [s.strip() for s in _biometric_attendance_fix.strip().split(";") if s.strip()]:
                await conn.execute(text(_stmt))
        logger.info("Biometric attendance schema ensured")
    except Exception as _e:
        logger.warning("Biometric attendance schema fix skipped (non-fatal): %s", _e)

    # Shift's silently-dropped columns (weekly_off_days/late_grace_min/
    # full_day_hours/half_day_hours/crosses_midnight had no matching ORM
    # column and no extra/data catch-all, so every shift save dropped them)
    # + attendance_corrections for the correction/approval workflow.
    # Mirrors alembic migration 025.
    _shift_and_correction_fix = """
        ALTER TABLE IF EXISTS shifts ADD COLUMN IF NOT EXISTS weekly_off_days JSONB;
        ALTER TABLE IF EXISTS shifts ADD COLUMN IF NOT EXISTS late_grace_min INTEGER DEFAULT 10;
        ALTER TABLE IF EXISTS shifts ADD COLUMN IF NOT EXISTS full_day_hours NUMERIC(18,4);
        ALTER TABLE IF EXISTS shifts ADD COLUMN IF NOT EXISTS half_day_hours NUMERIC(18,4);
        ALTER TABLE IF EXISTS shifts ADD COLUMN IF NOT EXISTS crosses_midnight BOOLEAN DEFAULT FALSE;
        CREATE TABLE IF NOT EXISTS attendance_corrections (
            id TEXT PRIMARY KEY, tenant_id TEXT, employee_id TEXT, attendance_date TEXT,
            requested_check_in TEXT, requested_check_out TEXT, requested_status TEXT,
            reason TEXT, status TEXT, requested_by TEXT, requested_at TEXT,
            decided_by TEXT, decided_at TEXT, rejection_reason TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_att_corrections_tenant_id ON attendance_corrections (tenant_id);
        CREATE INDEX IF NOT EXISTS ix_att_corrections_tenant_employee ON attendance_corrections (tenant_id, employee_id);
        CREATE INDEX IF NOT EXISTS ix_att_corrections_status ON attendance_corrections (tenant_id, status);
    """
    try:
        async with engine.begin() as conn:
            for _stmt in [s.strip() for s in _shift_and_correction_fix.strip().split(";") if s.strip()]:
                await conn.execute(text(_stmt))
        logger.info("Shift columns + attendance corrections schema ensured")
    except Exception as _e:
        logger.warning("Shift/correction schema fix skipped (non-fatal): %s", _e)

    # Database indexes for inventory query optimization
    _inventory_performance_indexes = """
        CREATE INDEX IF NOT EXISTS ix_stock_ledger_item_godown_date ON stock_ledger_entries (stock_item_id, godown_id, entry_date);
        CREATE INDEX IF NOT EXISTS ix_stock_ledger_godown_date ON stock_ledger_entries (godown_id, entry_date);
        CREATE INDEX IF NOT EXISTS ix_stock_transactions_product_created ON stock_transactions (product_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_stock_transactions_godown_created ON stock_transactions (godown_id, created_at);
        CREATE INDEX IF NOT EXISTS ix_stock_transactions_doc_type_created ON stock_transactions (doc_type, created_at);
        CREATE INDEX IF NOT EXISTS ix_stock_transfers_status ON stock_transfers (status);
        CREATE INDEX IF NOT EXISTS ix_product_categories_deleted_name ON product_categories (is_deleted, name);
    """
    try:
        async with engine.begin() as conn:
            for _stmt in [s.strip() for s in _inventory_performance_indexes.strip().split(";") if s.strip()]:
                await conn.execute(text(_stmt))
        logger.info("Inventory performance indexes ensured")
    except Exception as _e:
        logger.warning("Inventory performance index fix skipped (non-fatal): %s", _e)

    if os.environ.get("SKIP_POOL_WARMUP", "").lower() not in ("1", "true", "yes"):
        await warm_pool()
        logger.info("Database connection pool warmed")
    else:
        logger.info("Pool warmup skipped (SKIP_POOL_WARMUP=1)")

    skip_seed = os.environ.get("SKIP_STARTUP_SEED", "").lower() in ("1", "true", "yes")
    if skip_seed:
        logger.info("Startup seed skipped (SKIP_STARTUP_SEED=1)")
    else:
        await seed_admin()
        logger.info("Admin user ensured")

        try:
            already = await seed_demo_data()
            if already:
                logger.info("Demo data already present — seed skipped")
            else:
                logger.info("Demo data seeded")
        except Exception as e:
            logger.warning(f"Demo data seed skipped (non-fatal): {e}")

        try:
            already = await seed_default_coa()
            if already:
                logger.info("Chart of Accounts already seeded — skipped")
            else:
                logger.info("Chart of Accounts seeded (41 default accounts)")
        except Exception as e:
            logger.warning(f"CoA seed skipped (non-fatal): {e}")

    try:
        init_storage()
        logger.info("Object storage initialised")
    except Exception as e:
        logger.warning(f"Object storage init failed (uploads disabled): {e}")

    from core.biometric_sync import scheduler_loop
    from core.db import db as _db
    biometric_scheduler_task = asyncio.create_task(scheduler_loop(_db))
    logger.info("Biometric attendance scheduler started")

    yield

    biometric_scheduler_task.cancel()
    try:
        await biometric_scheduler_task
    except asyncio.CancelledError:
        pass

    await close_db()


app = FastAPI(title="Ormodex ERP", lifespan=lifespan)
app.add_middleware(SkipAlreadyCompressedGZipMiddleware, minimum_size=1000)


import time as _time
from fastapi.responses import JSONResponse

from core.db import query_stats as _query_stats


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Convert unexpected errors into proper JSON responses.

    Stale-connection and timeout errors return 503 (Service Unavailable) so the
    frontend/client knows to retry. All other unhandled exceptions return 500.
    Logging is done here so every unhandled error appears in the server log with
    its full traceback, even when uvicorn's own handler would swallow it.
    """
    import traceback as _tb
    msg = str(exc)
    # Classify stale-connection errors as 503 (transient; safe to retry)
    stale_markers = (
        "ConnectionDoesNotExistError", "connection was closed",
        "server closed the connection unexpectedly",
        "SSL connection has been closed", "CannotConnectNowError",
    )
    is_stale = any(m in msg for m in stale_markers)
    status = 503 if is_stale else 500
    detail = "Database temporarily unavailable. Please retry." if is_stale else "Internal server error."
    logger.error("Unhandled exception [%s %s]: %s\n%s",
                 request.method, request.url.path, exc,
                 _tb.format_exc())
    return JSONResponse(status_code=status, content={"detail": detail})


_STALE_CONN_MARKERS = (
    "ConnectionDoesNotExistError",
    "connection was closed",
    "server closed the connection unexpectedly",
    "SSL connection has been closed",
    "CannotConnectNowError",
)


def _is_stale_conn(exc: Exception) -> bool:
    msg = str(exc)
    return any(m in msg for m in _STALE_CONN_MARKERS)


@app.middleware("http")
async def request_db_session(request: Request, call_next):
    """Reuse one DB session for all db.* calls within a single HTTP request.

    Also stamps timing headers so per-endpoint latency and DB round-trip counts
    are observable from the browser network tab / a benchmark harness:
      X-Process-Time-Ms : total server time for the request
      X-DB-Queries      : SQL statements this request issued (round-trip count —
                          the real KPI against a cross-region pooler)
      X-DB-Time-Ms      : cumulative SQL time for those statements

    Retries once when a stale-connection error occurs (pool held a dead connection).
    pool_pre_ping catches most cases; this is a belt-and-suspenders guard for the
    race window between the pre-ping SELECT 1 and the first real statement.
    """
    q0 = _query_stats()
    t0 = _time.perf_counter()

    async def _run_with_session():
        async with AsyncSessionLocal() as session:
            token = bind_request_session(session)
            try:
                resp = await call_next(request)
                await session.commit()
                return resp
            except Exception:
                await session.rollback()
                raise
            finally:
                unbind_request_session(token)

    try:
        response = await _run_with_session()
    except Exception as exc:
        if _is_stale_conn(exc):
            # Dispose all stale connections and retry once with a fresh pool.
            await engine.dispose()
            response = await _run_with_session()
        else:
            raise

    q1 = _query_stats()
    response.headers["X-Process-Time-Ms"] = f"{(_time.perf_counter() - t0) * 1000:.0f}"
    response.headers["X-DB-Queries"] = str(q1["count"] - q0["count"])
    response.headers["X-DB-Time-Ms"] = f"{q1['total_ms'] - q0['total_ms']:.0f}"
    return response


raw_frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
frontend_origins = [u.strip() for u in raw_frontend_url.split(",") if u.strip()]
origins = list(set(frontend_origins + [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]))
allow_vercel_regex = os.environ.get("ALLOW_VERCEL_REGEX", "true").lower() in ("1", "true", "yes")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.vercel\.app" if allow_vercel_regex else None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "X-Requested-With"],
)


# ── CSRF (double-submit cookie) ──────────────────────────────────────────────
# The access/refresh cookies are httponly + SameSite=None in production (needed
# because the frontend and API are on different origins), which means SameSite
# alone doesn't block cross-site requests the way it would same-site. A
# double-submit CSRF token is defense-in-depth: _issue_session sets a
# non-httponly "csrf_token" cookie; the frontend's axios instance is expected
# to echo it back as X-CSRF-Token on state-changing requests.
#
# Rolled out log-only first (never blocks a request) so a client that doesn't
# yet send the header — including the Electron desktop build's Bearer-token
# fallback path — isn't silently broken. Flip CSRF_ENFORCE=true once the web
# and desktop clients are confirmed to send the header correctly.
CSRF_EXEMPT_PREFIXES = ("/api/auth/login", "/api/auth/refresh", "/api/auth/forgot-password", "/api/auth/reset-password")
CSRF_SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


@app.middleware("http")
async def csrf_check(request: Request, call_next):
    if (
        request.method not in CSRF_SAFE_METHODS
        and not request.url.path.startswith(CSRF_EXEMPT_PREFIXES)
    ):
        cookie_token = request.cookies.get("csrf_token")
        header_token = request.headers.get("X-CSRF-Token")
        if cookie_token and cookie_token != header_token:
            enforce = os.environ.get("CSRF_ENFORCE", "").lower() in ("1", "true", "yes")
            if enforce:
                return JSONResponse(status_code=403, content={"detail": "CSRF token missing or invalid"})
            logger.warning(
                "CSRF token mismatch (log-only) [%s %s]: cookie=%s header=%s",
                request.method, request.url.path, bool(cookie_token), bool(header_token),
            )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Attach defensive security headers to every response.

    These are cheap, broadly-compatible hardening headers that protect against
    MIME sniffing, clickjacking, referrer leakage and (in production) downgrade
    to plain HTTP. The API serves JSON, not HTML, so a strict default CSP that
    disallows framing/embedding is safe and does not affect the SPA, which is
    served separately by the static host / CDN.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
    )
    if os.environ.get("ENV", "development").lower() == "production":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


api_router = APIRouter(prefix="/api")


@app.get("/health")
async def health():
    """Lightweight liveness probe — no DB call, used by benchmarks and load-balancers."""
    return {"status": "ok"}


@api_router.get("/")
async def root():
    return {"name": "Ormodex ERP", "status": "ok"}


from core.auth_utils import require_admin as _require_admin


@api_router.get("/diagnostics")
async def diagnostics(_admin: dict = Depends(_require_admin)):
    """Real-time performance snapshot: cache stats, DB query counters, pool state.

    Admin-only: exposes internal pool/query counters and cache internals, which
    are operational details that shouldn't be world-readable in production.
    """
    from core import cache as _cache
    from core.db import query_stats as _qs, engine as _engine

    pool = _engine.pool
    pool_info: dict = {}
    try:
        pool_info = {
            "checked_in": pool.checkedin() if hasattr(pool, "checkedin") else None,  # type: ignore[attr-defined]
            "checked_out": pool.checkedout() if hasattr(pool, "checkedout") else None,  # type: ignore[attr-defined]
            "overflow": pool.overflow() if hasattr(pool, "overflow") else None,  # type: ignore[attr-defined]
            "invalid": pool.invalidated() if hasattr(pool, "invalidated") else None,  # type: ignore[attr-defined]
        }
    except Exception:
        pass

    return {
        "cache": _cache.stats(),
        "db_queries": _qs(),
        "pool": pool_info,
    }


# Mount feature routers
api_router.include_router(auth_router)
api_router.include_router(mfa_router)
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
api_router.include_router(biometric_attendance_router)
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
api_router.include_router(categories_router)
api_router.include_router(po_numbering_router)
api_router.include_router(document_numbering_router)
api_router.include_router(cheque_printing_router)
api_router.include_router(debtors_creditors_router)
api_router.include_router(letterhead_designer_router)
api_router.include_router(search_router)
api_router.include_router(stock_log_router)

app.include_router(api_router)

# Versioned API alias
v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(masters_router)
v1_router.include_router(voucher_engine_router)
v1_router.include_router(categories_router)
v1_router.include_router(po_numbering_router)
v1_router.include_router(document_numbering_router)
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
v1_router.include_router(biometric_attendance_router)
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
v1_router.include_router(cheque_printing_router)
app.include_router(v1_router)
