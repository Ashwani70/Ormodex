"""Add missing columns to purchase_bills table.

The table was created with old MongoDB field names (vendor_bill_no, bill_date,
total_amount). The purchase_v2 router uses the new names (vendor_invoice_no,
vendor_invoice_date, vendor_name, total, taxable, tds_rate, grn_ids,
purchase_order_id, journal_entry_id). These columns did not exist in the live
table, causing all purchase bill list rows to show blank Vendor Inv / Date /
Vendor / Voucher columns.
"""
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def _try(sql: str, label: str) -> None:
    # SAVEPOINT per statement — the backfills below reference old Mongo-era
    # columns (vendor_bill_no, bill_date, total_amount) that don't exist on a
    # fresh database, and without a savepoint that failure aborts the whole
    # migration transaction (see 007's _try for the full note).
    try:
        with op.get_bind().begin_nested():
            op.execute(sql)
    except Exception as exc:
        print(f"[010] {label} non-fatal: {exc}")


def upgrade():
    cols = [
        ("vendor_invoice_no",   "varchar", "NULL"),
        ("vendor_invoice_date", "varchar", "NULL"),
        ("vendor_name",         "varchar", "NULL"),
        ("purchase_order_id",   "varchar", "NULL"),
        ("grn_ids",             "jsonb",   "'[]'::jsonb"),
        ("taxable",             "numeric", "NULL"),
        ("total",               "numeric", "NULL"),
        ("tds_rate",            "numeric", "0"),
        ("journal_entry_id",    "varchar", "NULL"),
    ]
    for col, typ, default in cols:
        _try(
            f"ALTER TABLE purchase_bills "
            f"ADD COLUMN IF NOT EXISTS {col} {typ} DEFAULT {default}",
            col,
        )

    # Back-fill vendor_invoice_no from the old vendor_bill_no column for
    # existing rows so they show something instead of blank.
    _try("""
        UPDATE purchase_bills
        SET vendor_invoice_no = vendor_bill_no
        WHERE vendor_invoice_no IS NULL AND vendor_bill_no IS NOT NULL
    """, "backfill vendor_invoice_no")

    # Back-fill vendor_invoice_date from bill_date
    _try("""
        UPDATE purchase_bills
        SET vendor_invoice_date = bill_date::varchar
        WHERE vendor_invoice_date IS NULL AND bill_date IS NOT NULL
    """, "backfill vendor_invoice_date")

    # Back-fill total from total_amount
    _try("""
        UPDATE purchase_bills
        SET total = total_amount
        WHERE total IS NULL AND total_amount IS NOT NULL
    """, "backfill total")


def downgrade():
    pass
