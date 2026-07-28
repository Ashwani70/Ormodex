"""Add uoms master table + uom column on stock ledger tables.

WHY:
  Products previously stored a free-text `unit` string with no master list
  and no default, so most rows silently ended up "pcs". The New Product form
  now offers a mandatory UOM dropdown (standard list + custom), and custom
  UOMs created from that dropdown are persisted in the new `uoms` table
  (core/schema.py's UOM model + the /api/inventory/uoms endpoints in
  routers/inventory.py).

  stock_ledger_entries and stock_transactions had no `uom` column at all, so
  a posted movement couldn't display its unit without joining back to
  stock_items — this adds it as a real column on both (matching how
  stock_items.uom was added previously). stock_transactions has neither an
  `extra` nor `data` JSONB fallback column, so an unmapped `uom` key would
  otherwise be silently dropped by the ORM insert (core/_mongo_compat.py's
  `hasattr(Model, k)` filter) rather than persisted.
"""
from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS uoms (
            id TEXT PRIMARY KEY,
            tenant_id TEXT,
            name TEXT,
            symbol TEXT,
            description TEXT,
            is_deleted BOOLEAN DEFAULT false,
            deleted_at TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_uoms_tenant_id ON uoms (tenant_id)
    """)
    op.execute("ALTER TABLE stock_ledger_entries ADD COLUMN IF NOT EXISTS uom TEXT")
    op.execute("ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS uom TEXT")


def downgrade():
    pass  # additive; safe to leave
