"""eSSL Biometric Attendance Integration: new tables + fix silently-dropped Attendance columns.

WHY:
  The `attendance` table's ORM model only declared id/tenant_id/employee_id/
  date/status/in_time/out_time/shift_id/notes — no check_in/check_out/
  working_hours/overtime_hours/source, and no extra/data catch-all column
  either. Every write through the Mongo-compat shim's insert_one/update_one
  (which routers/hr_attendance.py uses for ALL attendance writes: manual
  check-in, QR check-in, bulk attendance, the existing basic biometric
  webhook) does `Model(**{k: v for k, v in doc.items() if hasattr(Model, k)})`
  — any field with no matching column is silently dropped, permanently. So
  check-in/check-out times and OT hours were already being lost on every
  save in a real Postgres deployment, independent of this feature. Likewise
  routers/payroll.py's LOP calculation reads `attendance.find_one({employee_id,
  period})` expecting paid_days/period columns that never existed — payroll's
  LOP silently defaulted to zero for every employee.

  This migration adds those columns (all nullable, additive — no existing
  data affected) plus the new tables for the biometric integration module:
  biometric_devices, employee_device_mappings, attendance_sync_runs,
  attendance_rules, and extends attendance_logs with dedup/processing columns.
"""
from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade():
    # ── fix attendance's silently-dropped columns ──
    op.execute("ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS check_in TEXT")
    op.execute("ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS check_out TEXT")
    op.execute("ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS working_hours NUMERIC(18,4)")
    op.execute("ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS overtime_hours NUMERIC(18,4)")
    op.execute("ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS source TEXT")
    op.execute("ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS late BOOLEAN")
    op.execute("ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS early_leave BOOLEAN")
    op.execute("ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS missing_punch BOOLEAN")
    op.execute("ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS remarks TEXT")
    op.execute("ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS period TEXT")
    op.execute("ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS paid_days NUMERIC(18,4)")
    op.execute("ALTER TABLE IF EXISTS attendance ADD COLUMN IF NOT EXISTS total_days INTEGER")
    op.execute("CREATE INDEX IF NOT EXISTS ix_attendance_employee_period ON attendance (employee_id, period)")

    # ── attendance_logs: dedup + processing bookkeeping ──
    op.execute("ALTER TABLE IF EXISTS attendance_logs ADD COLUMN IF NOT EXISTS employee_code TEXT")
    op.execute("ALTER TABLE IF EXISTS attendance_logs ADD COLUMN IF NOT EXISTS dedup_key TEXT")
    op.execute("ALTER TABLE IF EXISTS attendance_logs ADD COLUMN IF NOT EXISTS sync_run_id TEXT")
    op.execute("ALTER TABLE IF EXISTS attendance_logs ADD COLUMN IF NOT EXISTS source TEXT")
    op.execute("ALTER TABLE IF EXISTS attendance_logs ADD COLUMN IF NOT EXISTS raw_payload JSONB")
    op.execute("ALTER TABLE IF EXISTS attendance_logs ADD COLUMN IF NOT EXISTS processed BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE IF EXISTS attendance_logs ADD COLUMN IF NOT EXISTS processed_at TEXT")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_attendance_logs_dedup_key ON attendance_logs (dedup_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_attendance_logs_tenant_device ON attendance_logs (tenant_id, device_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_attendance_logs_tenant_time ON attendance_logs (tenant_id, log_time)")

    # ── biometric_devices ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS biometric_devices (
            id TEXT PRIMARY KEY,
            tenant_id TEXT,
            name TEXT,
            serial_number TEXT,
            branch_id TEXT,
            device_model TEXT,
            integration_mode TEXT,
            host TEXT,
            port INTEGER DEFAULT 4370,
            api_path TEXT,
            push_secret TEXT,
            poll_interval_seconds INTEGER DEFAULT 300,
            is_active BOOLEAN DEFAULT TRUE,
            last_sync_at TEXT,
            last_sync_status TEXT,
            last_seen_at TEXT,
            notes TEXT,
            is_deleted BOOLEAN DEFAULT FALSE,
            deleted_at TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_biometric_devices_tenant_id ON biometric_devices (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_biometric_devices_tenant_branch ON biometric_devices (tenant_id, branch_id)")

    # ── employee_device_mappings ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS employee_device_mappings (
            id TEXT PRIMARY KEY,
            tenant_id TEXT,
            device_id TEXT,
            employee_id TEXT,
            device_enrollment_id TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_emp_device_map_tenant_id ON employee_device_mappings (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_emp_device_map_tenant_device ON employee_device_mappings (tenant_id, device_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_emp_device_map_tenant_employee ON employee_device_mappings (tenant_id, employee_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_emp_device_map_device_enrollment ON employee_device_mappings (device_id, device_enrollment_id)")

    # ── attendance_sync_runs ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS attendance_sync_runs (
            id TEXT PRIMARY KEY,
            tenant_id TEXT,
            device_id TEXT,
            trigger TEXT,
            status TEXT,
            started_at TEXT,
            finished_at TEXT,
            punches_fetched INTEGER DEFAULT 0,
            punches_new INTEGER DEFAULT 0,
            punches_duplicate INTEGER DEFAULT 0,
            error_message TEXT,
            attempt INTEGER DEFAULT 1,
            next_attempt_at TEXT,
            triggered_by TEXT,
            created_at TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_att_sync_runs_tenant_id ON attendance_sync_runs (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_att_sync_runs_tenant_device ON attendance_sync_runs (tenant_id, device_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_att_sync_runs_status ON attendance_sync_runs (tenant_id, status)")

    # ── attendance_rules ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS attendance_rules (
            id TEXT PRIMARY KEY,
            tenant_id TEXT,
            shift_id TEXT,
            late_grace_minutes INTEGER DEFAULT 10,
            early_leave_grace_minutes INTEGER DEFAULT 10,
            half_day_threshold_hours NUMERIC(18,4),
            full_day_threshold_hours NUMERIC(18,4),
            overtime_after_hours NUMERIC(18,4),
            missing_punch_action TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_attendance_rules_tenant_id ON attendance_rules (tenant_id)")


def downgrade():
    pass  # additive; safe to leave
