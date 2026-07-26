"""PostgreSQL schema hardening: constraints, FK-style indexes, and GIN indexes.

WHY:
  After the MongoDB→Postgres migration the tables have correct columns but lack:
  - UNIQUE constraints (e.g. users.email was unique in Mongo via index; now only
    declared unique on the SQLAlchemy column but the DB constraint may be absent
    on tables created via create_all on an already-partially-created schema).
  - CHECK constraints on enum-like TEXT columns (status, role, action).
  - GIN indexes for full-text / JSONB containment search on items/extra columns.
  - Composite indexes on the most common (tenant_id, date) / (tenant_id, status)
    query patterns.
  - Non-null defaults for boolean flags that should never be NULL.

All statements use IF NOT EXISTS / DO NOTHING so re-running is safe.
"""
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def _try(sql: str) -> None:
    """Execute SQL; swallow errors so one bad statement doesn't abort the whole migration.

    Runs on a SAVEPOINT (begin_nested): in Postgres a failed statement aborts
    the surrounding transaction, so a bare try/except would leave every later
    statement failing with InFailedSQLTransaction and the migration unable to
    commit. Rolling back to the savepoint keeps the transaction healthy.
    """
    try:
        with op.get_bind().begin_nested():
            op.execute(sql)
    except Exception as exc:
        print(f"[007 migration] non-fatal: {exc}")


def upgrade():
    # ── 1. UNIQUE constraints ──────────────────────────────────────────────────

    # users.email — was unique in Mongo; must be unique in Postgres
    _try("""
        DO $$ BEGIN
            ALTER TABLE users ADD CONSTRAINT uq_users_email UNIQUE (email);
        EXCEPTION WHEN duplicate_table THEN NULL; END $$;
    """)

    # customers: unique email per tenant (where email is non-null)
    _try("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_email_tenant
        ON customers (tenant_id, email)
        WHERE email IS NOT NULL AND email != '';
    """)

    # vendors: unique email per tenant
    _try("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_vendors_email_tenant
        ON vendors (tenant_id, email)
        WHERE email IS NOT NULL AND email != '';
    """)

    # products: unique SKU per tenant
    _try("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_products_sku_tenant
        ON products (tenant_id, sku)
        WHERE sku IS NOT NULL AND sku != '';
    """)

    # stock_items: unique name per tenant
    _try("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_items_name_tenant
        ON stock_items (tenant_id, name)
        WHERE name IS NOT NULL;
    """)

    # bank_accounts: unique account_number per tenant
    _try("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_bank_accounts_number_tenant
        ON bank_accounts (tenant_id, account_number)
        WHERE account_number IS NOT NULL AND account_number != '';
    """)

    # chart_of_accounts: unique code per tenant
    _try("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_coa_code_tenant
        ON chart_of_accounts (tenant_id, code)
        WHERE code IS NOT NULL AND code != '';
    """)

    # api_keys: unique key value (globally unique secret)
    _try("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_api_keys_key
        ON api_keys (key_value)
        WHERE key_value IS NOT NULL;
    """)

    # ── 2. CHECK constraints on status / enum TEXT columns — REMOVED ──────────
    # These constraints listed value sets that were never validated against
    # what the app actually writes: purchase_v2 sets PO status 'SENT'/'PARTIAL',
    # core/utils.py audits lowercase 'create'/'update'/'delete', auth/approvals
    # audit 'LOGIN_SUCCESS'/'SUBMIT'/'APPROVE_FINAL'/…, and 015 later drops
    # chk_users_role because roles are user-definable. None of them ever
    # applied in production (before the SAVEPOINT fix, 007's first failed
    # statement silently aborted the whole migration) — but on a fresh database
    # they DID apply and instantly rejected legitimate app writes. Drop them
    # anywhere they may have landed instead.
    for tbl, chk in [
        ("invoices", "chk_invoices_status"),
        ("purchase_orders", "chk_purchase_orders_status"),
        ("purchase_orders_v2", "chk_purchase_orders_v2_status"),
        ("grn_v2", "chk_grn_v2_status"),
        ("sales_orders", "chk_sales_orders_status"),
        ("payroll_runs", "chk_payroll_runs_status"),
        ("audit_logs", "chk_audit_logs_action"),
        ("users", "chk_users_role"),
    ]:
        _try(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS {chk};")

    # ── 3. GIN indexes for JSONB columns ─────────────────────────────────────

    # products.extra — searched by custom fields
    _try("""
        CREATE INDEX IF NOT EXISTS gin_products_extra
        ON products USING gin(extra jsonb_path_ops)
        WHERE extra IS NOT NULL;
    """)

    # job_work_challans.items — searched for product_id within JSONB array
    _try("""
        CREATE INDEX IF NOT EXISTS gin_job_work_challans_items
        ON job_work_challans USING gin(items jsonb_path_ops)
        WHERE items IS NOT NULL;
    """)

    # invoices — line items search
    _try("""
        CREATE INDEX IF NOT EXISTS gin_invoices_items
        ON invoices USING gin(items jsonb_path_ops)
        WHERE items IS NOT NULL;
    """)

    # purchase_bills — line items search
    _try("""
        CREATE INDEX IF NOT EXISTS gin_purchase_bills_items
        ON purchase_bills USING gin(items jsonb_path_ops)
        WHERE items IS NOT NULL;
    """)

    # vouchers_v2.inventory_lines — stock movement lookup
    _try("""
        CREATE INDEX IF NOT EXISTS gin_vouchers_v2_inventory_lines
        ON vouchers_v2 USING gin(inventory_lines jsonb_path_ops)
        WHERE inventory_lines IS NOT NULL;
    """)

    # stock_ledger_entries.extra
    _try("""
        CREATE INDEX IF NOT EXISTS gin_stock_ledger_extra
        ON stock_ledger_entries USING gin(extra jsonb_path_ops)
        WHERE extra IS NOT NULL;
    """)

    # ── 4. Composite indexes for common query patterns ─────────────────────────

    # customers — search by tenant + name (most common list filter)
    _try("""
        CREATE INDEX IF NOT EXISTS ix_customers_tenant_name
        ON customers (tenant_id, name)
        WHERE is_deleted = FALSE OR is_deleted IS NULL;
    """)

    # vendors — same
    _try("""
        CREATE INDEX IF NOT EXISTS ix_vendors_tenant_name
        ON vendors (tenant_id, name)
        WHERE is_deleted = FALSE OR is_deleted IS NULL;
    """)

    # invoices — tenant + date (dashboard / date-range filters)
    _try("""
        CREATE INDEX IF NOT EXISTS ix_invoices_tenant_date
        ON invoices (tenant_id, date DESC);
    """)

    # invoices — tenant + status (outstanding receivables)
    _try("""
        CREATE INDEX IF NOT EXISTS ix_invoices_tenant_status
        ON invoices (tenant_id, status);
    """)

    # invoices — tenant + customer (customer statement)
    _try("""
        CREATE INDEX IF NOT EXISTS ix_invoices_tenant_customer
        ON invoices (tenant_id, customer_id);
    """)

    # purchase_bills — tenant + vendor + date
    _try("""
        CREATE INDEX IF NOT EXISTS ix_purchase_bills_tenant_vendor_date
        ON purchase_bills (tenant_id, vendor_id, date DESC);
    """)

    # sales_orders — tenant + date
    _try("""
        CREATE INDEX IF NOT EXISTS ix_sales_orders_tenant_date
        ON sales_orders (tenant_id, date DESC);
    """)

    # purchase_orders_v2 — tenant + date
    _try("""
        CREATE INDEX IF NOT EXISTS ix_po_v2_tenant_date
        ON purchase_orders_v2 (tenant_id, date DESC);
    """)

    # grn_v2 — tenant + date
    _try("""
        CREATE INDEX IF NOT EXISTS ix_grn_v2_tenant_date
        ON grn_v2 (tenant_id, date DESC);
    """)

    # stock_ledger_entries — stock_item + date (stock history lookups)
    _try("""
        CREATE INDEX IF NOT EXISTS ix_sle_stock_item_date
        ON stock_ledger_entries (stock_item_id, date DESC);
    """)

    # stock_ledger_entries — unique voucher-stock-movement constraint
    # (was enforced by MongoDB partial unique index; now enforced in Postgres)
    _try("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_voucher_stock_movement
        ON stock_ledger_entries (
            source_doc_type, source_doc_id, stock_item_id,
            movement_type,
            COALESCE(batch_id, ''),
            COALESCE(serial_id, '')
        )
        WHERE source_doc_type = 'voucher';
    """)

    # payslips — tenant + employee + period
    _try("""
        CREATE INDEX IF NOT EXISTS ix_payslips_tenant_employee_period
        ON payslips (tenant_id, employee_id, pay_period);
    """)

    # audit_logs — entity lookup (most common audit query)
    _try("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_entity
        ON audit_logs (tenant_id, entity_type, entity_id, created_at DESC);
    """)

    # journal_entries — tenant + date
    _try("""
        CREATE INDEX IF NOT EXISTS ix_journal_entries_tenant_date
        ON journal_entries (tenant_id, date DESC);
    """)

    # employees — tenant + is_active (HR lists always filter active)
    _try("""
        CREATE INDEX IF NOT EXISTS ix_employees_tenant_active
        ON employees (tenant_id, is_active)
        WHERE is_active = TRUE;
    """)

    # attendance — employee + date (attendance report)
    _try("""
        CREATE INDEX IF NOT EXISTS ix_attendance_employee_date
        ON attendance (employee_id, date DESC);
    """)

    # gst_records — tenant + period + gstin
    _try("""
        CREATE INDEX IF NOT EXISTS ix_gst_records_tenant_period
        ON gst_records (tenant_id, period, gstin);
    """)

    # ── 5. Non-null boolean defaults for columns that should never be NULL ─────

    _try("ALTER TABLE users ALTER COLUMN is_active SET DEFAULT TRUE;")
    _try("ALTER TABLE customers ALTER COLUMN is_deleted SET DEFAULT FALSE;")
    _try("ALTER TABLE vendors ALTER COLUMN is_deleted SET DEFAULT FALSE;")
    _try("ALTER TABLE products ALTER COLUMN is_deleted SET DEFAULT FALSE;")
    _try("ALTER TABLE employees ALTER COLUMN is_active SET DEFAULT TRUE;")
    _try("ALTER TABLE stock_items ALTER COLUMN is_deleted SET DEFAULT FALSE;")

    # ── 6. Partial indexes for soft-delete patterns ────────────────────────────

    # products — only non-deleted products in catalog queries
    _try("""
        CREATE INDEX IF NOT EXISTS ix_products_tenant_active
        ON products (tenant_id, name)
        WHERE is_deleted = FALSE OR is_deleted IS NULL;
    """)

    # ── 7. trgm indexes for ILIKE search (requires pg_trgm extension) ─────────

    _try("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    for table, col in [
        ("customers", "name"),
        ("customers", "company"),
        ("customers", "gstin"),
        ("vendors", "name"),
        ("vendors", "company"),
        ("vendors", "gstin"),
        ("products", "name"),
        ("products", "sku"),
        ("employees", "name"),
        ("invoices", "invoice_number"),
        ("purchase_orders_v2", "po_number"),
        ("stock_items", "name"),
    ]:
        _try(f"""
            CREATE INDEX IF NOT EXISTS trgm_{table}_{col}
            ON {table} USING gin({col} gin_trgm_ops)
            WHERE {col} IS NOT NULL;
        """)


def downgrade():
    # Constraints and indexes — not reversible (data-safe; just performance/integrity)
    pass
