"""Add source_doc_type to stock_transactions so Stock Log can disambiguate
which page a "view voucher" drill-down should open.

WHY:
  stock_transactions.doc_type alone is too coarse — all inward-purchase
  posting paths (PO direct receive, v1 GRN, v2 GRN) share doc_type="PURCHASE",
  so the drill-down resolver (routers/stock_log.py resolve_voucher) always
  routed to /purchase-orders even for GRN-originated rows, where the actual
  document lives at /grns. stock_ledger_entries already carries
  source_doc_type (see migration 022 / the stock_ledger schema fix in
  server.py's lifespan); this table — the legacy mirror Stock Log actually
  reads — never did. See project memory
  project-stocklog-grn-route-mislabel.md for the full trace.
"""
from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE IF EXISTS stock_transactions ADD COLUMN IF NOT EXISTS source_doc_type TEXT DEFAULT NULL")
    # Backfill: doc_type is the best guess for historical rows written before
    # this column existed — still coarse (won't distinguish GRN from a PO
    # direct receive on old rows) but strictly better than NULL, and new rows
    # get the real value from post_entry going forward.
    op.execute("UPDATE stock_transactions SET source_doc_type = doc_type WHERE source_doc_type IS NULL AND doc_type IS NOT NULL")


def downgrade():
    pass  # additive; safe to leave
