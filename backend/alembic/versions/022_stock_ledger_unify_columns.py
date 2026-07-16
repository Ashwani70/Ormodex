"""Stock ledger unification: denormalize product_id/name + user + reason onto stock_ledger_entries.

WHY:
  Every stock-posting call site in the app now goes through
  core.stock_ledger.post_entry (see the 2026-07 "stock ledger unification"
  writer migration — 17 v1 direct-write routers moved onto it). post_entry
  writes stock_ledger_entries (the valuation-aware, item-keyed ledger) and
  then best-effort mirrors a second row into stock_transactions (the older,
  product-keyed table Stock Log/reports read) via
  _mirror_to_legacy_transaction — because stock_ledger_entries was missing
  the columns that mirror needs to exist standalone: product_id, product_name
  (it's keyed by stock_item_id, not product_id), user_id, user_name, reason.
  (doc_type and voucher_no already exist on stock_ledger_entries as legacy
  columns from migration 019/the pre-rebuild schema.)

  This migration adds those five columns so stock_ledger_entries becomes a
  complete superset of stock_transactions's data on its own row — the
  foundation for eventually retiring the second table and the mirror/dual-
  write entirely. This migration does NOT change any reader (Stock Log still
  reads stock_transactions exactly as before) and does NOT stop the mirror —
  post_entry starts populating these new columns on the SAME insert it
  already does, purely additive. Zero behavior change for any endpoint.

  CREATE INDEX CONCURRENTLY (no table lock) + IF NOT EXISTS (idempotent),
  matching the pattern established in 005/018/019/021.
"""
from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None

transaction_per_migration = False   # required for CONCURRENTLY


def _concurrent(sql: str):
    try:
        op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {sql}")
    except Exception as exc:
        print(f"[022 migration] non-fatal: {exc}")


def upgrade():
    op.execute("ALTER TABLE stock_ledger_entries ADD COLUMN IF NOT EXISTS product_id TEXT")
    op.execute("ALTER TABLE stock_ledger_entries ADD COLUMN IF NOT EXISTS product_name TEXT")
    op.execute("ALTER TABLE stock_ledger_entries ADD COLUMN IF NOT EXISTS user_id TEXT")
    op.execute("ALTER TABLE stock_ledger_entries ADD COLUMN IF NOT EXISTS user_name TEXT")
    op.execute("ALTER TABLE stock_ledger_entries ADD COLUMN IF NOT EXISTS reason TEXT")

    # product_id mirrors stock_transactions' most common filter/join column —
    # future readers (once repointed) will need this indexed the same way.
    _concurrent("ix_stock_ledger_product_id ON stock_ledger_entries (product_id)")
    _concurrent("ix_stock_ledger_user_id    ON stock_ledger_entries (user_id)")


def downgrade():
    pass   # additive; safe to leave
