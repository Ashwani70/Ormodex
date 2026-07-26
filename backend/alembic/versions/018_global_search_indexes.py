"""Global search: trigram GIN indexes across every module the Ctrl+K palette covers.

WHY:
  Migration 005 added pg_trgm + GIN indexes for a handful of columns (product/
  vendor/customer names, invoice_no). The new unified global-search endpoint
  (routers/search.py) runs one UNION ALL query across ~20 tables covering every
  ERP module (masters, purchase, sales, finance, production, HR), matching on
  document numbers, party names, emails, phones, GSTIN/PAN, employee codes,
  etc. Each of those columns needs its own trigram GIN index or the ILIKE
  '%term%' / similarity() branch for that table falls back to a sequential
  scan — fine at today's row counts, but the whole point of this migration is
  to keep it fast as data grows.

  All created CONCURRENTLY + IF NOT EXISTS — zero table lock, safe to re-run.
  CREATE INDEX CONCURRENTLY cannot run inside a transaction, so (matching 005)
  each statement runs inside Alembic's autocommit_block().
"""
from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def _concurrent(sql: str):
    try:
        with op.get_context().autocommit_block():
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {sql}")
    except Exception as exc:
        print(f"[018 migration] non-fatal: {exc}")


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── Masters ────────────────────────────────────────────────────────────
    _concurrent("ix_trgm_customers_company  ON customers  USING GIN (company gin_trgm_ops)")
    _concurrent("ix_trgm_customers_email    ON customers  USING GIN (email gin_trgm_ops)")
    _concurrent("ix_trgm_customers_phone    ON customers  USING GIN (phone gin_trgm_ops)")
    _concurrent("ix_trgm_vendors_email      ON vendors    USING GIN (email gin_trgm_ops)")
    _concurrent("ix_trgm_vendors_phone      ON vendors    USING GIN (phone gin_trgm_ops)")
    _concurrent("ix_trgm_employees_name     ON employees  USING GIN (name gin_trgm_ops)")
    _concurrent("ix_trgm_employees_code     ON employees  USING GIN (emp_code gin_trgm_ops)")
    _concurrent("ix_trgm_employees_email    ON employees  USING GIN (email gin_trgm_ops)")
    _concurrent("ix_trgm_employees_phone    ON employees  USING GIN (phone gin_trgm_ops)")
    _concurrent("ix_trgm_master_ledgers_name ON master_ledgers USING GIN (name gin_trgm_ops)")
    _concurrent("ix_trgm_warehouses_name    ON warehouses USING GIN (name gin_trgm_ops)")
    _concurrent("ix_trgm_godowns_name       ON godowns    USING GIN (name gin_trgm_ops)")
    _concurrent("ix_trgm_product_categories_name ON product_categories USING GIN (name gin_trgm_ops)")

    # ── Inventory ──────────────────────────────────────────────────────────
    _concurrent("ix_trgm_products_hsn       ON products    USING GIN (hsn_code gin_trgm_ops)")
    _concurrent("ix_trgm_stock_items_sku    ON stock_items USING GIN (sku gin_trgm_ops)")
    _concurrent("ix_batches_batch_no        ON batches (batch_no)")

    # ── Purchase ───────────────────────────────────────────────────────────
    _concurrent("ix_trgm_po_v2_number       ON purchase_orders_v2 USING GIN (po_number gin_trgm_ops)")
    _concurrent("ix_trgm_grn_v2_number      ON grn_v2             USING GIN (grn_number gin_trgm_ops)")
    _concurrent("ix_trgm_purchase_bills_number ON purchase_bills  USING GIN (bill_number gin_trgm_ops)")
    _concurrent("ix_trgm_purchase_bills_vendor_name ON purchase_bills USING GIN (vendor_name gin_trgm_ops)")

    # ── Sales ──────────────────────────────────────────────────────────────
    _concurrent("ix_trgm_quotations_no      ON quotations   USING GIN (quotation_no gin_trgm_ops)")
    _concurrent("ix_trgm_sales_orders_no    ON sales_orders USING GIN (so_number gin_trgm_ops)")
    _concurrent("ix_trgm_invoices_number    ON invoices     USING GIN (invoice_number gin_trgm_ops)")
    _concurrent("ix_trgm_credit_notes_no    ON credit_notes USING GIN (cn_number gin_trgm_ops)")
    _concurrent("ix_trgm_dispatches_no      ON dispatches   USING GIN (dispatch_no gin_trgm_ops)")
    _concurrent("ix_trgm_proforma_no        ON proforma_invoices USING GIN (pi_number gin_trgm_ops)")
    _concurrent("ix_trgm_leads_company      ON leads        USING GIN (company_name gin_trgm_ops)")
    _concurrent("ix_trgm_leads_contact      ON leads        USING GIN (contact_person gin_trgm_ops)")
    _concurrent("ix_trgm_leads_email        ON leads        USING GIN (email gin_trgm_ops)")
    _concurrent("ix_trgm_leads_phone        ON leads        USING GIN (phone gin_trgm_ops)")

    # ── Finance ────────────────────────────────────────────────────────────
    _concurrent("ix_trgm_vouchers_no        ON vouchers     USING GIN (voucher_no gin_trgm_ops)")
    _concurrent("ix_trgm_vouchers_number    ON vouchers     USING GIN (voucher_number gin_trgm_ops)")
    _concurrent("ix_trgm_vouchers_party     ON vouchers     USING GIN (party_name gin_trgm_ops)")
    _concurrent("ix_trgm_expense_no         ON expense_entries USING GIN (expense_no gin_trgm_ops)")
    _concurrent("ix_trgm_fixed_assets_name  ON fixed_assets USING GIN (name gin_trgm_ops)")

    # ── Production / Job Work ─────────────────────────────────────────────
    _concurrent("ix_trgm_boms_product_name  ON boms USING GIN (finished_product_name gin_trgm_ops)")
    _concurrent("ix_trgm_boms_sku           ON boms USING GIN (sku gin_trgm_ops)")
    _concurrent("ix_work_orders_number      ON work_orders (wo_number)")
    _concurrent("ix_trgm_jwc_number         ON job_work_challans USING GIN (challan_number gin_trgm_ops)")
    _concurrent("ix_trgm_jwc_worker_name    ON job_work_challans USING GIN (job_worker_name gin_trgm_ops)")

    # ── Cheque / Banking (already-shipped modules, missing from 005) ──────
    _concurrent("ix_trgm_pdcs_cheque_no     ON pdcs USING GIN (cheque_no gin_trgm_ops)")
    _concurrent("ix_trgm_cheque_txn_number  ON cheque_transactions USING GIN (cheque_number gin_trgm_ops)")

    # ── Composite (status, created_at) to keep grouped/paginated result
    #    fetches (module drill-down pages) fast without needing tenant_id ──
    _concurrent("ix_employees_status        ON employees (status)")
    _concurrent("ix_leads_status_created    ON leads (status, created_at)")


def downgrade():
    pass   # indexes are additive; safe to leave
