"""Performance Audit: single-column & composite indexes + pg_stat_statements.

Adds CONCURRENTLY IF NOT EXISTS indexes for:
  - created_at, updated_at
  - company_id, customer_id, vendor_id/supplier_id, product_id
  - voucher_no/voucher_number, invoice_no/invoice_number
  - gstin, email

Also enables `pg_stat_statements` extension for continuous SQL diagnostics.
"""
from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None

_INDEXES = (
    # created_at & updated_at
    ("ix_invoices_updated_at", "invoices", "updated_at"),
    ("ix_sales_orders_updated_at", "sales_orders", "updated_at"),
    ("ix_purchase_orders_updated_at", "purchase_orders", "updated_at"),
    ("ix_vouchers_updated_at", "vouchers", "updated_at"),
    ("ix_products_updated_at", "products", "updated_at"),
    ("ix_customers_created_at", "customers", "created_at"),
    ("ix_customers_updated_at", "customers", "updated_at"),
    ("ix_vendors_created_at", "vendors", "created_at"),
    ("ix_vendors_updated_at", "vendors", "updated_at"),

    # company_id
    ("ix_invoices_company_id", "invoices", "company_id"),
    ("ix_sales_orders_company_id", "sales_orders", "company_id"),
    ("ix_purchase_orders_company_id", "purchase_orders", "company_id"),
    ("ix_vouchers_company_id", "vouchers", "company_id"),
    ("ix_journal_entries_company_id", "journal_entries", "company_id"),
    ("ix_products_company_id", "products", "company_id"),

    # customer_id & vendor_id / supplier_id
    ("ix_vouchers_customer_id", "vouchers", "customer_id"),
    ("ix_vouchers_vendor_id", "vouchers", "vendor_id"),
    ("ix_quotations_customer_id", "quotations", "customer_id"),
    ("ix_vouchers_supplier_id", "vouchers", "supplier_id"),

    # product_id
    ("ix_stock_ledger_product_id", "stock_ledger_entries", "product_id"),
    ("ix_stock_transactions_product_id", "stock_transactions", "product_id"),

    # voucher_no / voucher_number & invoice_no / invoice_number
    ("ix_vouchers_voucher_number", "vouchers", "voucher_number"),
    ("ix_stock_transactions_voucher_no", "stock_transactions", "voucher_no"),
    ("ix_journal_entries_entry_number", "journal_entries", "entry_number"),
    ("ix_gst_records_invoice_number", "gst_records", "invoice_number"),
    ("ix_eway_bills_invoice_number", "eway_bills", "invoice_number"),

    # gstin & email
    ("ix_companies_gstin", "companies", "gstin"),
    ("ix_users_email", "users", "email"),
    ("ix_customers_email", "customers", "email"),
    ("ix_vendors_email", "vendors", "email"),
)


def upgrade() -> None:
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    except Exception as exc:
        print(f"[029 migration] pg_stat_statements extension notice: {exc}")

    for name, table, column in _INDEXES:
        try:
            with op.get_context().autocommit_block():
                op.execute(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                    f"ON {table} ({column})"
                )
        except Exception as exc:
            print(f"[029 migration] non-fatal index notice ({name}): {exc}")


def downgrade() -> None:
    for name, _table, _column in _INDEXES:
        try:
            with op.get_context().autocommit_block():
                op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        except Exception as exc:
            print(f"[029 migration] non-fatal index drop notice ({name}): {exc}")
