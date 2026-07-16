"""Repair job_work_challans: normalize status, backfill NULL display columns.

WHY:
  After migration from MongoDB, some challan rows have:
    - status = NULL or lowercase ('pending', 'completed') instead of the
      PENDING / COMPLETED / PARTIAL / CANCELLED literals the router expects.
      This caused the DELETE endpoint's `status != 'PENDING'` guard to always
      fire, returning 409 for every delete → "Deleted 0, Failed N" in the UI.
    - challan_number / date / job_worker_name = NULL because old Mongo docs
      may have been stored with different key names that didn't map to the new
      Postgres columns during the initial migration pass.

FIX:
  1. Upper-case every status value so the router's Literal guard matches.
  2. Default NULL status → 'PENDING' (safe: a challan that was never finished
     is pending by definition).
  3. Add a CHECK constraint so future inserts can't write a bad status.
  4. Create an index on challan_number for fast lookup / doc-number generation.
"""
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Normalize status: uppercase all values, default NULL → PENDING
    op.execute("""
        UPDATE job_work_challans
        SET status = UPPER(status)
        WHERE status IS NOT NULL
          AND status != UPPER(status)
    """)
    op.execute("""
        UPDATE job_work_challans
        SET status = 'PENDING'
        WHERE status IS NULL OR TRIM(status) = ''
    """)

    # 2. Add CHECK constraint so the column stays consistent
    op.execute("""
        ALTER TABLE job_work_challans
        DROP CONSTRAINT IF EXISTS chk_job_work_challans_status
    """)
    op.execute("""
        ALTER TABLE job_work_challans
        ADD CONSTRAINT chk_job_work_challans_status
        CHECK (status IN ('PENDING', 'PARTIAL', 'COMPLETED', 'CANCELLED'))
    """)

    # 3. Index on challan_number (used for doc-number lookups and search)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_job_work_challans_challan_number
        ON job_work_challans (challan_number)
    """)

    # 4. Index on date for ordering (all list queries sort by date DESC)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_job_work_challans_date
        ON job_work_challans (date)
    """)

    # 5. Default nature / gst_type for legacy rows missing them
    op.execute("""
        UPDATE job_work_challans
        SET nature = 'inputs'
        WHERE nature IS NULL OR TRIM(nature) = ''
    """)
    op.execute("""
        UPDATE job_work_challans
        SET gst_type = 'auto'
        WHERE gst_type IS NULL OR TRIM(gst_type) = ''
    """)


def downgrade():
    op.execute("DROP CONSTRAINT IF EXISTS chk_job_work_challans_status")
    op.execute("DROP INDEX IF EXISTS ix_job_work_challans_challan_number")
    op.execute("DROP INDEX IF EXISTS ix_job_work_challans_date")
