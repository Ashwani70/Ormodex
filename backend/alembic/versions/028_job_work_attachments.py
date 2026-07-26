"""Add attachments column to job_work_challans / job_work_receipts.

WHY:
  Job Work Reports needed a way to attach a scanned/signed acknowledgement
  copy (or any other supporting document) to a challan or receipt row,
  same as the Warehouse module's `documents` array
  (project-warehouse-enterprise-redesign.md). Stored as a JSONB array of
  {id, name, path, size, content_type, uploaded_at} via the existing
  generic /uploads/document endpoint — no new storage backend needed.
"""
from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE IF EXISTS job_work_challans ADD COLUMN IF NOT EXISTS attachments JSONB DEFAULT NULL")
    op.execute("ALTER TABLE IF EXISTS job_work_receipts ADD COLUMN IF NOT EXISTS attachments JSONB DEFAULT NULL")


def downgrade():
    pass  # additive; safe to leave
