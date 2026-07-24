"""Fix Shift's silently-dropped columns; add attendance correction/approval workflow.

WHY:
  core/hr_models.py's Shift Pydantic model has declared weekly_off_days/
  late_grace_min/full_day_hours/half_day_hours since before the ORM Shift
  class existed, but the ORM class never had matching columns and Shift has
  no extra/data catch-all — every shift create/update silently dropped them
  (core/utils.py's crud_create/crud_update only keep keys with a matching
  column when there's no overflow column to fall back to). So
  routers/hr_attendance.py's late-detection always used its hardcoded
  defaults regardless of what an admin configured on a shift, and the new
  biometric-attendance derivation (core/biometric_sync.py) had no way to
  know a shift's weekly offs or whether it crosses midnight.

  Also adds attendance_corrections for the correction/approval workflow:
  an employee (or HR, on their behalf) requests a change to a derived day's
  attendance (e.g. "the device missed my punch, I was actually here"); HR/
  admin approves or rejects, and approval re-derives that day's attendance
  row with the corrected check-in/check-out feeding the same derivation
  logic (so late/OT/paid_days recompute consistently rather than being
  hand-edited).
"""
from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE IF EXISTS shifts ADD COLUMN IF NOT EXISTS weekly_off_days JSONB")
    op.execute("ALTER TABLE IF EXISTS shifts ADD COLUMN IF NOT EXISTS late_grace_min INTEGER DEFAULT 10")
    op.execute("ALTER TABLE IF EXISTS shifts ADD COLUMN IF NOT EXISTS full_day_hours NUMERIC(18,4)")
    op.execute("ALTER TABLE IF EXISTS shifts ADD COLUMN IF NOT EXISTS half_day_hours NUMERIC(18,4)")
    op.execute("ALTER TABLE IF EXISTS shifts ADD COLUMN IF NOT EXISTS crosses_midnight BOOLEAN DEFAULT FALSE")

    op.execute("""
        CREATE TABLE IF NOT EXISTS attendance_corrections (
            id TEXT PRIMARY KEY,
            tenant_id TEXT,
            employee_id TEXT,
            attendance_date TEXT,
            requested_check_in TEXT,
            requested_check_out TEXT,
            requested_status TEXT,
            reason TEXT,
            status TEXT,
            requested_by TEXT,
            requested_at TEXT,
            decided_by TEXT,
            decided_at TEXT,
            rejection_reason TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_att_corrections_tenant_id ON attendance_corrections (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_att_corrections_tenant_employee ON attendance_corrections (tenant_id, employee_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_att_corrections_status ON attendance_corrections (tenant_id, status)")


def downgrade():
    pass  # additive; safe to leave
