"""Stock Log rebuild: voucher_no column + indexes for the paginated ledger grid.

WHY:
  stock_transactions is the live-populated stock-movement table (178+ real
  rows from Purchase/Sales/Job Work/Manufacturing today) but most of its
  columns (godown_id, batch_id, doc_type, source_doc_id, rate, value,
  direction) exist on the ORM/DB already yet are never written by any
  router — the actual voucher number only ever lived embedded in a free-text
  `reason` string (e.g. "Job Work Issue JWC00011"). The new Stock Log needs a
  real voucher_no column (distinct from source_doc_id, which is an opaque row
  id) so it can render + filter a structured "Voucher No" column instead of
  parsing text.

  Also adds the indexes the new paginated/filtered/sorted ledger endpoint
  needs: product, date (created_at), user, doc_type, godown — matching the
  filter set exposed in the new Stock Log header (product/warehouse/date
  range/voucher type/user). Without these, GET /stock-log/entries falls back
  to sequential scans once the table grows past a few thousand rows.

  CREATE INDEX CONCURRENTLY (no table lock) + IF NOT EXISTS (idempotent),
  matching the pattern established in 005/018.
"""
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None

def _concurrent(sql: str):
    try:
        with op.get_context().autocommit_block():
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {sql}")
    except Exception as exc:
        print(f"[019 migration] non-fatal: {exc}")


def upgrade():
    op.execute("ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS voucher_no TEXT")

    _concurrent("ix_stock_txn_product_id   ON stock_transactions (product_id)")
    _concurrent("ix_stock_txn_created_at   ON stock_transactions (created_at)")
    _concurrent("ix_stock_txn_user_id      ON stock_transactions (user_id)")
    _concurrent("ix_stock_txn_doc_type     ON stock_transactions (doc_type)")
    _concurrent("ix_stock_txn_godown_id    ON stock_transactions (godown_id)")
    _concurrent("ix_stock_txn_voucher_no   ON stock_transactions (voucher_no)")
    # Covers the grid's default sort (newest first) filtered by product — the
    # single most common query shape (product search + date-desc listing).
    _concurrent("ix_stock_txn_product_created ON stock_transactions (product_id, created_at DESC)")


def downgrade():
    pass   # additive; safe to leave
