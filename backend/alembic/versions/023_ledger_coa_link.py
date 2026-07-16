"""Link master_ledgers to chart_of_accounts so the voucher engine can post real account_code values.

WHY:
  core.voucher_engine's journal lines were keyed by ledger_id/account_name
  only — no account_code. Every financial report (Trial Balance/P&L/Balance
  Sheet in routers/accounting.py, plus reports_engine.py's aggregations)
  groups strictly by line["account_code"], so any voucher posted through the
  voucher engine (Payment/Receipt/Contra/Journal/Sales/Purchase/Credit-Debit
  Notes/Payroll) either crashed those reports (KeyError) or silently grouped
  under a blank account. master_ledgers and chart_of_accounts were two
  entirely separate, unlinked hierarchies with no mapping between them.

  This adds a nullable coa_account_id column (references chart_of_accounts.id)
  on master_ledgers. Ledger create/update now requires it; voucher_engine
  resolves it to the CoA row's `code` at posting time and stamps that onto
  each journal line. A ledger with no mapping blocks posting with a clear
  error (see core/voucher_engine.py) rather than silently producing an
  unreportable entry.

  Existing ledgers are backfilled best-effort by a Python script
  (scripts/backfill_ledger_coa_links.py) since name/nature matching needs
  real logic, not SQL — this migration only adds the column.
"""
from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE IF EXISTS master_ledgers ADD COLUMN IF NOT EXISTS coa_account_id TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS ix_master_ledgers_coa_account_id ON master_ledgers (coa_account_id)")


def downgrade():
    pass  # additive; safe to leave
