"""Job Work: normalize line items into real child tables + Tally-style header fields.

WHY:
  The Job Work module is being redesigned into two strictly-separated,
  keyboard-driven vouchers (Challan Outward / Receipt Inward), modeled after
  Tally Prime. Line items were previously stored as JSONB arrays on the parent
  challan/receipt row; the new router queries real child tables with proper
  joins/GROUP BY instead of Python-side dict aggregation over JSONB, and a
  receipt line now references its exact challan_item_id rather than matching
  by product-id/name string ("_item_key") — this is both faster and more
  precise (two custom lines with the same name no longer collide).

  The legacy `items` JSONB column is kept (not dropped) on both parent tables
  as a safety net during the transition — nothing is destroyed. A separate
  one-off Python script (run once, outside this migration) backfills the new
  child tables from the legacy JSONB for any pre-existing rows.

  New nullable header columns support the Tally-style Challan header/footer:
  contact person + transport details (driver/LR/e-way bill), process/return
  metadata, and sign-off fields. All additive — existing rows are unaffected.
"""
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


_CHALLAN_COLUMNS = [
    "contact_person TEXT",
    "driver_name TEXT",
    "lr_number TEXT",
    "eway_bill_number TEXT",
    "process_name TEXT",
    "instructions TEXT",
    "prepared_by TEXT",
    "checked_by TEXT",
]


def _try(sql: str) -> None:
    # SAVEPOINT per statement — a failure otherwise aborts the surrounding
    # migration transaction (see 007's _try for the full note).
    try:
        with op.get_bind().begin_nested():
            op.execute(sql)
    except Exception as exc:
        print(f"[016 migration] non-fatal: {exc}")


def upgrade():
    for col in _CHALLAN_COLUMNS:
        _try(f"ALTER TABLE job_work_challans ADD COLUMN IF NOT EXISTS {col}")

    op.execute("""
        CREATE TABLE IF NOT EXISTS job_work_challan_items (
            id TEXT PRIMARY KEY,
            challan_id TEXT NOT NULL,
            tenant_id TEXT,
            line_no INTEGER,
            product_id TEXT,
            product_name TEXT,
            sku TEXT,
            description TEXT,
            hsn_code TEXT,
            uom TEXT,
            is_custom BOOLEAN DEFAULT FALSE,
            quantity NUMERIC(18,4),
            rate NUMERIC(18,4),
            amount NUMERIC(18,4),
            gst_rate NUMERIC(6,2),
            taxable_value NUMERIC(18,4),
            cgst NUMERIC(18,4),
            sgst NUMERIC(18,4),
            igst NUMERIC(18,4),
            line_total NUMERIC(18,4),
            batch_id TEXT,
            serial_id TEXT,
            expiry_date TEXT,
            remarks TEXT,
            created_at TEXT,
            updated_at TEXT
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_jw_challan_items_challan_id ON job_work_challan_items (challan_id);")

    op.execute("""
        CREATE TABLE IF NOT EXISTS job_work_receipt_items (
            id TEXT PRIMARY KEY,
            receipt_id TEXT NOT NULL,
            tenant_id TEXT,
            challan_item_id TEXT,
            product_id TEXT,
            product_name TEXT,
            sku TEXT,
            is_custom BOOLEAN DEFAULT FALSE,
            quantity_received NUMERIC(18,4),
            accepted_quantity NUMERIC(18,4),
            rejected_quantity NUMERIC(18,4) DEFAULT 0,
            scrap_quantity NUMERIC(18,4) DEFAULT 0,
            batch_id TEXT,
            serial_id TEXT,
            expiry_date TEXT,
            remarks TEXT,
            created_at TEXT,
            updated_at TEXT
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_jw_receipt_items_receipt_id ON job_work_receipt_items (receipt_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_jw_receipt_items_challan_item_id ON job_work_receipt_items (challan_item_id);")


def downgrade():
    op.execute("DROP TABLE IF EXISTS job_work_receipt_items")
    op.execute("DROP TABLE IF EXISTS job_work_challan_items")
    for col in _CHALLAN_COLUMNS:
        name = col.split()[0]
        op.execute(f"ALTER TABLE job_work_challans DROP COLUMN IF EXISTS {name}")
