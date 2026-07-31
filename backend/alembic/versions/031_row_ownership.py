"""Row-level data ownership isolation.

Adds `created_by` (the user who created the row) to the 7 tables an
Employee-tier user's visibility is now scoped to (see core/utils.py's
OWNED_COLLECTIONS / apply_ownership_filter / assert_owns_or_404, and the
router changes in routers/sales.py, routers/purchase_v2.py, routers/search.py):

    customers, vendors, quotations, sales_orders, invoices,
    purchase_orders_v2, purchase_bills

WHY:
  Nothing in this schema previously tracked "who created this row" — an
  Employee-tier user could list, view, edit, or export every other user's
  customers/quotations/sales orders/invoices/vendors/purchase records. This
  is a NEW column, not a backfill: every existing row gets created_by = NULL,
  which is deliberately treated as "grandfathered" (visible to everyone,
  never hidden) rather than "owned by nobody, hidden from everyone" — the
  latter would look like mass data loss to every non-admin user on rollout
  day. See assert_owns_or_404's NULL-guard in core/utils.py.

  Composite (tenant_id, created_by) indexes, not a bare created_by index,
  matching every other index in this schema — the ownership filter is always
  applied alongside (or in place of, in this single-tenant deployment) the
  existing tenant scoping in practice.
"""
from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None

_TABLES = (
    "customers", "vendors", "quotations", "sales_orders",
    "invoices", "purchase_orders_v2", "purchase_bills",
)


def _try(sql: str, label: str) -> None:
    # SAVEPOINT per statement — matches 010_purchase_bills_columns.py's
    # pattern so one failing statement (e.g. a table already having the
    # column from a partial prior run) doesn't abort the whole migration.
    try:
        with op.get_bind().begin_nested():
            op.execute(sql)
    except Exception as exc:
        print(f"[031] {label} non-fatal: {exc}")


def upgrade() -> None:
    for table in _TABLES:
        _try(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS created_by TEXT DEFAULT NULL",
            f"{table}.created_by",
        )
        _try(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_created_by "
            f"ON {table} (tenant_id, created_by)",
            f"ix_{table}_tenant_created_by",
        )


def downgrade() -> None:
    pass  # additive-only; safe to leave
