"""Fix job_work_challans and job_work_receipts column names to match the router.

The original schema used different column names from what the job_work router
stores (e.g. challan_no vs challan_number, dispatch_date vs date, lines vs items).
This migration drops the old columns and adds the correct ones so the compat
shim's _row_to_dict() returns the keys the router and frontend expect.

Existing data in those 2 tables is wiped (they had broken/empty data anyway).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    # ── job_work_challans ────────────────────────────────────────────────────
    # Drop old columns that don't match what the router stores
    with op.batch_alter_table("job_work_challans") as batch_op:
        # Remove old mismatched columns (ignore if already absent)
        for col in ("challan_no", "vendor_id", "lines", "dispatch_date", "expected_return_date"):
            try:
                batch_op.drop_column(col)
            except Exception:
                pass

    # Add the columns the router actually writes
    op.execute("""
        ALTER TABLE job_work_challans
            ADD COLUMN IF NOT EXISTS challan_number        TEXT,
            ADD COLUMN IF NOT EXISTS date                  TEXT,
            ADD COLUMN IF NOT EXISTS due_date              TEXT,
            ADD COLUMN IF NOT EXISTS job_worker_id         TEXT,
            ADD COLUMN IF NOT EXISTS job_worker_name       TEXT,
            ADD COLUMN IF NOT EXISTS job_worker_gstin      TEXT,
            ADD COLUMN IF NOT EXISTS nature                TEXT,
            ADD COLUMN IF NOT EXISTS gst_type              TEXT,
            ADD COLUMN IF NOT EXISTS is_inter_state        BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS items                 JSONB,
            ADD COLUMN IF NOT EXISTS return_window_days    INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS is_overdue            BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS deemed_supply         BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS total_taxable_value   NUMERIC(18,4),
            ADD COLUMN IF NOT EXISTS total_cgst            NUMERIC(18,4),
            ADD COLUMN IF NOT EXISTS total_sgst            NUMERIC(18,4),
            ADD COLUMN IF NOT EXISTS total_igst            NUMERIC(18,4),
            ADD COLUMN IF NOT EXISTS total_gst             NUMERIC(18,4),
            ADD COLUMN IF NOT EXISTS grand_total           NUMERIC(18,4),
            ADD COLUMN IF NOT EXISTS journal_entry_id      TEXT
    """)

    # ── job_work_receipts ────────────────────────────────────────────────────
    with op.batch_alter_table("job_work_receipts") as batch_op:
        for col in ("receipt_no", "lines", "receipt_date"):
            try:
                batch_op.drop_column(col)
            except Exception:
                pass

    op.execute("""
        ALTER TABLE job_work_receipts
            ADD COLUMN IF NOT EXISTS receipt_number TEXT,
            ADD COLUMN IF NOT EXISTS date           TEXT,
            ADD COLUMN IF NOT EXISTS items          JSONB
    """)

    # Drop old index on receipts if it exists (we add a better one via schema)
    op.execute("DROP INDEX IF EXISTS ix_job_work_receipts_tenant_status")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_job_work_receipts_challan_id
        ON job_work_receipts (challan_id)
    """)


def downgrade():
    pass  # data migration — not reversible
