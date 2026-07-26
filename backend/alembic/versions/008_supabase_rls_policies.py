"""Supabase Row Level Security (RLS) policies.

WHY:
  This ERP is single-tenant and the API is always accessed through the FastAPI
  backend using a service-role connection (the pooler URL in DATABASE_URL). The
  Supabase anon/authenticated roles are NOT used for direct table access — all
  business logic runs under the postgres role via SQLAlchemy.

  Nevertheless, enabling RLS on all public tables is defence-in-depth:
  - If a developer accidentally uses the anon key or a Supabase client library
    they cannot read or write any row.
  - The Supabase Data API (PostgREST) cannot serve any data without an explicit
    policy, so accidental API exposure is blocked.
  - The service_role key (used by the backend) BYPASSES RLS by design, so
    enabling RLS does NOT break the application.

POLICY DESIGN:
  - All tables: ENABLE RLS.
  - A single permissive policy grants FULL access to the `service_role` (the
    Postgres role used by the backend's pooler connection). This mirrors the
    single-superuser access pattern the app already uses.
  - No policy is granted to `anon` or `authenticated` roles — direct table
    access from the Supabase JS SDK or REST API is blocked entirely.

TO VERIFY after applying:
    SELECT schemaname, tablename, rowsecurity
    FROM pg_tables
    WHERE schemaname = 'public' AND rowsecurity = TRUE;
"""
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

# Tables that exist in the public schema and need RLS enabled.
# This list mirrors the SQLAlchemy models in schema.py.
_TABLES = [
    "users", "refresh_tokens",
    "company", "verification_settings", "einvoice_settings", "purchase_settings",
    "theme_settings", "po_numbering_settings", "counters",
    "leads", "customers", "vendors",
    "products", "product_categories", "warehouses", "godowns",
    "stock_items", "stock_ledger_entries", "stock_transactions",
    "stock_transfers", "batches", "physical_verifications", "qc_reports",
    "purchase_orders", "purchase_orders_v2", "grn_v2",
    "purchase_bills", "purchase_returns", "vendor_bill_submissions",
    "po_number_audit", "quotations", "sales_orders", "invoices",
    "credit_notes", "dispatches", "proforma_invoices", "payment_links",
    "chart_of_accounts", "master_ledgers", "master_groups", "cost_centers",
    "fiscal_years", "currencies", "voucher_types", "journal_entries",
    "vouchers", "vouchers_v2", "voucher_counters",
    "expense_entries", "expense_categories", "advances", "interest_rules",
    "bank_accounts", "bank_entries", "bank_statements", "bank_statement_lines",
    "bank_feed_imports", "pdcs", "cheque_transactions", "cheque_formats",
    "employees", "attendance", "attendance_logs", "leaves", "leave_types",
    "holidays", "shifts", "salary_structures", "pay_components",
    "payroll_runs", "payslips", "statutory_params", "fnf_settlements",
    "tds_declarations",
    "gst_records", "gst_filing_cache", "gstin_cache",
    "gst_reconciliations", "tds_entries", "tcs_entries", "eway_bills",
    "fixed_assets", "asset_categories", "asset_depreciation_runs",
    "asset_transactions",
    "projects", "project_costs", "tasks", "timesheet_entries",
    "boms", "work_orders", "production_journals", "wastage_entries",
    "job_work_challans", "job_work_receipts", "rate_tables",
    "approval_policies", "approval_requests", "approval_steps",
    "pos_sales", "pos_sessions", "price_lists", "discount_schemes",
    "webhook_subscriptions", "webhook_deliveries",
    "portal_users", "api_keys", "branches", "inter_branch_transfers",
    "budgets", "report_summaries", "report_saved_views",
    "uploaded_files", "ocr_documents", "verification_logs",
    "ai_chat_history", "ai_conversations",
    "audit_logs",
    # Tables added post-migration (from audit 2026-06)
    "hr_branches", "hr_departments", "hr_designations",
    "overtime_entries", "salary_payments",
    "cheques", "cheque_templates", "godown_rates", "it_blocks",
    "buyer_orders", "fabric_trims", "stitching_lines", "backups",
]


def _upgrade_table(table: str) -> None:
    # Enable RLS
    op.execute(f'ALTER TABLE IF EXISTS "{table}" ENABLE ROW LEVEL SECURITY;')
    # Force RLS even for table owner (belt-and-suspenders)
    op.execute(f'ALTER TABLE IF EXISTS "{table}" FORCE ROW LEVEL SECURITY;')
    # Grant full access to service_role (the backend's DB role).
    # Guarded on pg_roles: service_role only exists on Supabase — on a
    # vanilla Postgres (CI service container, local dev) CREATE POLICY
    # ... TO service_role would raise "role does not exist" and poison
    # the surrounding migration transaction, so skip it cleanly there.
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role')
            AND NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = '{table}'
                  AND policyname = 'service_role_full_access'
            ) THEN
                EXECUTE $policy$
                    CREATE POLICY service_role_full_access
                    ON public."{table}"
                    AS PERMISSIVE
                    FOR ALL
                    TO service_role
                    USING (true)
                    WITH CHECK (true)
                $policy$;
            END IF;
        END $$;
    """)


def upgrade():
    for table in _TABLES:
        try:
            # SAVEPOINT per table: without it one failed statement aborts the
            # whole migration transaction and every later table's statements
            # die with InFailedSQLTransaction despite the try/except.
            with op.get_bind().begin_nested():
                _upgrade_table(table)
        except Exception as exc:
            # Non-fatal: table may not exist yet in this environment
            print(f"[008 RLS] skipped {table}: {exc}")

    # Revoke direct access from anon and authenticated roles for all public tables.
    # The backend never uses these roles — only service_role goes through the pooler.
    # Guarded on pg_roles: these roles exist only on Supabase (see note above).
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;
            END IF;
        END $$;
    """)


def downgrade():
    for table in _TABLES:
        try:
            with op.get_bind().begin_nested():
                op.execute(f'DROP POLICY IF EXISTS service_role_full_access ON public."{table}";')
                op.execute(f'ALTER TABLE IF EXISTS "{table}" DISABLE ROW LEVEL SECURITY;')
        except Exception:
            pass
