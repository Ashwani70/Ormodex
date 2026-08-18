"""Add missing columns (transfer_number, lines, remarks, extra) to stock_transfers table.

WHY:
  Stock transfers saved transfer_number, lines, and remarks in request bodies,
  but the stock_transfers ORM table definition was missing these columns and an
  extra JSONB overflow bucket, causing transfer_number and lines to be silently
  dropped on save.
"""
from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE IF EXISTS stock_transfers ADD COLUMN IF NOT EXISTS transfer_number TEXT")
    op.execute("ALTER TABLE IF EXISTS stock_transfers ADD COLUMN IF NOT EXISTS lines JSONB")
    op.execute("ALTER TABLE IF EXISTS stock_transfers ADD COLUMN IF NOT EXISTS remarks TEXT")
    op.execute("ALTER TABLE IF EXISTS stock_transfers ADD COLUMN IF NOT EXISTS extra JSONB")


def downgrade():
    pass
