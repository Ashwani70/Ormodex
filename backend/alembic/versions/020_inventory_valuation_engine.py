"""Inventory valuation engine: standard-cost + valuation config columns.

WHY:
  The valuation engine now supports five methods — FIFO, LIFO, Weighted-Average,
  Standard Cost — with resolution precedence Item Override → Company Default →
  engine default. Two new pieces of persisted config back this:

    stock_items.standard_cost  NUMERIC  — per-unit standard cost, consulted only
                                          when an item resolves to STANDARD_COST.
                                          NULL falls back to actual inward rate.
    stock_items.extra          JSONB    — back-compat home for standard_cost on
                                          rows written before this column, plus
                                          future per-item valuation settings.

  The company-wide default method is stored in the existing company.extra JSONB
  (extra.inventory_valuation_method), so it needs no DDL here.

  All idempotent (ADD COLUMN IF NOT EXISTS) so it is safe on any existing DB and
  matches the startup drift-reconcile in server.py.
"""
from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE IF EXISTS stock_items "
        "ADD COLUMN IF NOT EXISTS standard_cost NUMERIC(18,4) DEFAULT NULL"
    )
    op.execute(
        "ALTER TABLE IF EXISTS stock_items "
        "ADD COLUMN IF NOT EXISTS extra JSONB DEFAULT NULL"
    )


def downgrade():
    # Non-destructive by default: keep the columns. Uncomment to fully revert.
    # op.execute("ALTER TABLE IF EXISTS stock_items DROP COLUMN IF EXISTS standard_cost")
    # op.execute("ALTER TABLE IF EXISTS stock_items DROP COLUMN IF EXISTS extra")
    pass
