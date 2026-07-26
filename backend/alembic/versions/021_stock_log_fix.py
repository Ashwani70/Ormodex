"""Stock Log fix: source_doc_id index + backfill marker support.

WHY:
  Several v2 posting flows (GRN, Purchase Return, Stock Adjustment, v2 Opening
  Stock) call core.stock_ledger.post_entry, which wrote only
  stock_ledger_entries and never mirrored into stock_transactions — the table
  Stock Log, its summary cards, and its negative-stock count all read
  exclusively from. post_entry now mirrors every posting into
  stock_transactions (see core/stock_ledger.py's "Dual-write" note), and
  scripts/backfill_stock_transactions.py catches up everything posted before
  that fix.

  This migration adds the one index that backfill/drill-down queries need and
  migration 019 didn't add: source_doc_id (voucher_no was already indexed
  there, but resolving "all movements for this voucher" by source_doc_id was
  not). Also indexes stock_ledger_entries.source_doc_id for the same reason on
  the v2 side (GRN/Purchase Return "resolve voucher" lookups).

  CREATE INDEX CONCURRENTLY (no table lock) + IF NOT EXISTS (idempotent),
  matching the pattern established in 005/018/019.
"""
from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None

def _concurrent(sql: str):
    try:
        with op.get_context().autocommit_block():
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {sql}")
    except Exception as exc:
        print(f"[021 migration] non-fatal: {exc}")


def upgrade():
    _concurrent("ix_stock_txn_source_doc_id ON stock_transactions (source_doc_id)")
    _concurrent("ix_stock_ledger_source_doc_id ON stock_ledger_entries (source_doc_id)")


def downgrade():
    pass   # additive; safe to leave
