"""Performance indexes for Mumbai region (ap-south-1).

WHY:
  After migrating from MongoDB the tables had data but lacked indexes on the
  columns that every hot API path filters/sorts on. The result is full-table
  scans on every request — each one adds 30-200 ms on a remote pooler.

  This migration adds the specific indexes that showed up as missing when
  EXPLAIN ANALYZE was run against the slowest endpoints:

  1. stock_ledger_entries (stock_item_id, entry_date) — on_hand_bulk does a
     full table scan per item. This covers both the WHERE and the ORDER BY.

  2. expense_entries (expense_date, status) — MIS dashboard fetches 6 months
     of expenses filtered by date and status.

  3. invoices (created_at, status, customer_id) — MIS dashboard, dashboard
     summary, and receivables all filter/sort on these.

  4. purchase_orders (created_at) — MIS dashboard purchase fetch.

  5. audit_logs (created_at DESC) — audit trail page always ORDER BY created_at.

  6. employees (status, branch_id) — payroll generation filters active + branch.

  7. payslips (run_id, employee_id) — payroll run page fetches all slips for a run.

  8. attendance (employee_id, attendance_date) — payroll calculation does per-
     employee monthly attendance fetch.

  9. stock_items (product_id) — product_stock_bridge batched lookup.

 10. refresh_tokens (user_id, active) — token rotation looks up by user_id.

All statements use IF NOT EXISTS so re-running is safe.
"""
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def _try(sql: str) -> None:
    try:
        op.execute(sql)
    except Exception as exc:
        print(f"[009 perf] non-fatal: {exc}")


def upgrade():
    # ── 1. stock_ledger_entries: hot path for on_hand_bulk + _prior_entries ──
    # Covers: WHERE stock_item_id = ? ORDER BY entry_date, created_at
    _try("""
        CREATE INDEX IF NOT EXISTS ix_sle_item_date_created
        ON stock_ledger_entries (stock_item_id, entry_date, created_at);
    """)

    # Godown-scoped ledger lookup (on_hand with godown filter)
    _try("""
        CREATE INDEX IF NOT EXISTS ix_sle_item_godown_date
        ON stock_ledger_entries (stock_item_id, godown_id, entry_date, created_at)
        WHERE godown_id IS NOT NULL;
    """)

    # ── 2. expense_entries: MIS dashboard 6-month fetch ──────────────────────
    _try("""
        CREATE INDEX IF NOT EXISTS ix_expense_entries_date_status
        ON expense_entries (expense_date, status);
    """)

    # ── 3. invoices: dashboard + MIS + receivables ────────────────────────────
    _try("""
        CREATE INDEX IF NOT EXISTS ix_invoices_created_at
        ON invoices (created_at DESC);
    """)
    _try("""
        CREATE INDEX IF NOT EXISTS ix_invoices_status_created
        ON invoices (status, created_at DESC);
    """)

    # ── 4. purchase_orders: MIS purchase analysis ─────────────────────────────
    _try("""
        CREATE INDEX IF NOT EXISTS ix_purchase_orders_created_at
        ON purchase_orders (created_at DESC);
    """)

    # ── 5. audit_logs: audit trail page ORDER BY created_at ───────────────────
    _try("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at
        ON audit_logs (created_at DESC);
    """)
    # Entity + time lookup (most common audit query pattern)
    _try("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_entity_created
        ON audit_logs (entity_type, entity_id, created_at DESC);
    """)

    # ── 6. employees: payroll generation filter ───────────────────────────────
    _try("""
        CREATE INDEX IF NOT EXISTS ix_employees_status_branch
        ON employees (status, branch_id)
        WHERE status = 'active';
    """)

    # ── 7. payslips: payroll run page fetch ───────────────────────────────────
    _try("""
        CREATE INDEX IF NOT EXISTS ix_payslips_run_id
        ON payslips (run_id);
    """)
    _try("""
        CREATE INDEX IF NOT EXISTS ix_payslips_employee_id
        ON payslips (employee_id);
    """)

    # ── 8. attendance: payroll calculate_payslip per-employee monthly fetch ───
    _try("""
        CREATE INDEX IF NOT EXISTS ix_attendance_emp_date
        ON attendance (employee_id, attendance_date);
    """)

    # leaves: payroll leave calculation
    _try("""
        CREATE INDEX IF NOT EXISTS ix_leaves_emp_status_dates
        ON leaves (employee_id, status, from_date, to_date)
        WHERE status = 'APPROVED';
    """)

    # ── 9. stock_items: product_stock_bridge batched lookup ───────────────────
    _try("""
        CREATE INDEX IF NOT EXISTS ix_stock_items_product_id
        ON stock_items (product_id)
        WHERE product_id IS NOT NULL;
    """)
    _try("""
        CREATE INDEX IF NOT EXISTS ix_stock_items_sku
        ON stock_items (sku)
        WHERE sku IS NOT NULL AND product_id IS NULL;
    """)

    # ── 10. refresh_tokens: token rotation lookup ─────────────────────────────
    _try("""
        CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_active
        ON refresh_tokens (user_id, active)
        WHERE active = TRUE;
    """)
    _try("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_refresh_tokens_jti
        ON refresh_tokens (jti);
    """)

    # ── 11. products: common list query with soft-delete filter ───────────────
    _try("""
        CREATE INDEX IF NOT EXISTS ix_products_category_id
        ON products (category_id)
        WHERE is_deleted IS NOT TRUE;
    """)

    # ── 12. customers / vendors: soft-delete list ────────────────────────────
    _try("""
        CREATE INDEX IF NOT EXISTS ix_customers_not_deleted
        ON customers (name)
        WHERE is_deleted IS NOT TRUE;
    """)
    _try("""
        CREATE INDEX IF NOT EXISTS ix_vendors_not_deleted
        ON vendors (name)
        WHERE is_deleted IS NOT TRUE;
    """)

    # ── 13. gst_records: GST module date+type queries ─────────────────────────
    _try("""
        CREATE INDEX IF NOT EXISTS ix_gst_records_date
        ON gst_records (invoice_date DESC);
    """)

    # ── 14. vouchers_v2: accounting list sort ─────────────────────────────────
    _try("""
        CREATE INDEX IF NOT EXISTS ix_vouchers_v2_date
        ON vouchers_v2 (date DESC);
    """)

    # ── 15. job_work_challans: list sort + status filter ──────────────────────
    _try("""
        CREATE INDEX IF NOT EXISTS ix_job_work_challans_status_date
        ON job_work_challans (status, date DESC);
    """)

    # ── 16. hr: holiday lookup for working_days_in_month ──────────────────────
    _try("""
        CREATE INDEX IF NOT EXISTS ix_holidays_date
        ON holidays (holiday_date);
    """)


def downgrade():
    pass
