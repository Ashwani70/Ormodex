"""Job Work Challan: Add vehicle_no and transport columns.

WHY:
  To support professional PDF generation and tracking of transportation details on Job Work Challans.
"""
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE job_work_challans ADD COLUMN IF NOT EXISTS vehicle_no VARCHAR(255)")
    op.execute("ALTER TABLE job_work_challans ADD COLUMN IF NOT EXISTS transport VARCHAR(255)")


def downgrade():
    op.execute("ALTER TABLE job_work_challans DROP COLUMN IF EXISTS vehicle_no")
    op.execute("ALTER TABLE job_work_challans DROP COLUMN IF EXISTS transport")
