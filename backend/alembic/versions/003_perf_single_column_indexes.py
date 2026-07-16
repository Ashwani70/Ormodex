"""Performance: single-column indexes for the single-tenant access patterns.

The schema is richly indexed with composite ``(tenant_id, <col>)`` indexes, but
this deployment runs single-tenant and the data layer (the Mongo-compat shim)
issues filters WITHOUT ``tenant_id`` — e.g. ``stock_items WHERE product_id IN
(...)``, ``stock_ledger_entries WHERE stock_item_id IN (...)``, ``journal_entries
WHERE status = 'POSTED'``. A composite index that LEADS with ``tenant_id`` cannot
serve a predicate that doesn't constrain ``tenant_id``, so those hot lookups fall
back to sequential scans. That's free today (tables hold a handful of rows) but
becomes the dominant query cost once the ledger / journal grow to thousands+ of
rows. These single-column indexes keep those lookups index-served at scale.

Created CONCURRENTLY + IF NOT EXISTS so applying this never locks a table and is
safe to re-run. Because CREATE INDEX CONCURRENTLY cannot run inside a
transaction, this migration disables the per-migration transaction.

NOTE: at the time of writing this does not change observed latency — the app's
bottleneck is cross-region network round-trips, not query execution (EXPLAIN
ANALYZE shows ~0.04ms execution vs ~470ms wall). This migration is a
correctness-at-scale measure, applied under operator control via
``alembic upgrade``.
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

# (index_name, table, column) — single-column indexes matching the no-tenant_id
# filters the compat shim actually issues.
_INDEXES = (
    ("ix_stock_items_product_id", "stock_items", "product_id"),
    ("ix_stock_items_sku", "stock_items", "sku"),
    ("ix_stock_ledger_stock_item_id", "stock_ledger_entries", "stock_item_id"),
    ("ix_stock_txn_stock_item_id", "stock_transactions", "stock_item_id"),
    ("ix_theme_settings_user_id", "theme_settings", "user_id"),
    ("ix_journal_entries_status", "journal_entries", "status"),
    ("ix_invoices_status", "invoices", "status"),
    ("ix_sales_orders_status", "sales_orders", "status"),
    ("ix_leads_status", "leads", "status"),
    ("ix_products_category_id", "products", "category_id"),
    ("ix_product_categories_is_deleted", "product_categories", "is_deleted"),
    ("ix_refresh_tokens_active", "refresh_tokens", "active"),
)

# CREATE INDEX CONCURRENTLY must run outside a transaction.
def _autocommit():
    op.get_bind().execution_options(isolation_level="AUTOCOMMIT")


def upgrade() -> None:
    _autocommit()
    for name, table, column in _INDEXES:
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
            f"ON {table} ({column})"
        )


def downgrade() -> None:
    _autocommit()
    for name, _table, _column in _INDEXES:
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
