"""HR: add branch_id to holidays for per-branch holiday calendars.

WHY:
  working_days_in_month() in core/hr_payroll.py already accepts and threads
  through a branch_id (from routers/hr_payroll.py and per-employee payroll
  calculation), intending to filter holidays by branch. But the holidays
  table never had a branch_id column, so the filter silently never applied
  and every branch shared one calendar. This adds the column (nullable —
  NULL means "applies to all branches") so that filtering actually works.
"""
from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.execute("ALTER TABLE holidays ADD COLUMN IF NOT EXISTS branch_id TEXT")
        op.execute("CREATE INDEX IF NOT EXISTS ix_holidays_branch_id ON holidays (branch_id)")
    except Exception as exc:
        print(f"[017 migration] non-fatal: {exc}")


def downgrade():
    try:
        op.execute("ALTER TABLE holidays DROP COLUMN IF EXISTS branch_id")
    except Exception as exc:
        print(f"[017 migration] downgrade non-fatal: {exc}")
