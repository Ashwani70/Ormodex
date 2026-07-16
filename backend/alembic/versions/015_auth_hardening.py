"""Auth hardening: MFA/lockout columns on users, device + login-history tables.

WHY:
  MFA (core/mfa.py, routers/mfa.py) and forced-password-reset
  (_flag_password_if_weak in routers/auth.py) already write mfa_* and
  password_change_required via db.users.update_one, but the User ORM model had
  no such columns — the Mongo-compat $set handler silently drops any key that
  isn't a mapped column, so those writes were no-ops. This migration adds the
  real columns so that code actually persists, plus lockout/CAPTCHA counters,
  password history (reuse prevention), and two new tables for device/session
  management and login history, all nullable/defaulted so existing rows are
  unaffected.

  The role CHECK constraint is widened from the 4-value Pydantic literal to
  the 10 roles requested by the auth spec, plus "employee" kept valid (11
  total) since live data already has 9 users with that role and relabeling
  them was explicitly deferred to a manual admin decision rather than done by
  this migration.
"""
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


_USER_COLUMNS = [
    "mfa_enabled BOOLEAN DEFAULT FALSE",
    "mfa_secret TEXT",
    "mfa_pending_secret TEXT",
    "mfa_recovery_hashes JSONB",
    "password_change_required BOOLEAN DEFAULT FALSE",
    "password_history JSONB DEFAULT '[]'::jsonb",
    "last_password_change TEXT",
    "failed_login_count INTEGER DEFAULT 0",
    "locked_until TEXT",
    "is_locked BOOLEAN DEFAULT FALSE",
    "force_change_reason TEXT",
    "last_login_at TEXT",
    "last_login_ip TEXT",
]


def _try(sql: str) -> None:
    """Execute SQL; swallow errors so one bad statement doesn't abort the migration."""
    try:
        op.execute(sql)
    except Exception as exc:
        print(f"[015 migration] non-fatal: {exc}")


def upgrade():
    for col in _USER_COLUMNS:
        _try(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col}")

    _try("""
        ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_users_role;
    """)
    _try("""
        ALTER TABLE users
        ADD CONSTRAINT chk_users_role
        CHECK (role IN ('super_admin','admin','manager','accountant','purchase',
                        'sales','store','production','hr','viewer','employee'));
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_devices (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            refresh_jti TEXT,
            device_name TEXT,
            browser TEXT,
            os TEXT,
            ip TEXT,
            user_agent TEXT,
            login_at TEXT,
            last_active_at TEXT,
            revoked BOOLEAN DEFAULT FALSE,
            revoked_at TEXT,
            created_at TEXT
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_devices_user_id ON user_devices (user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_devices_jti ON user_devices (refresh_jti);")

    op.execute("""
        CREATE TABLE IF NOT EXISTS login_history (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            email_attempted TEXT,
            ip TEXT,
            user_agent TEXT,
            device_name TEXT,
            browser TEXT,
            os TEXT,
            success BOOLEAN NOT NULL,
            failure_reason TEXT,
            logged_in_at TEXT,
            logged_out_at TEXT,
            created_at TEXT
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_login_history_user_id ON login_history (user_id, created_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_login_history_created ON login_history (created_at DESC);")


def downgrade():
    op.execute("DROP TABLE IF EXISTS login_history")
    op.execute("DROP TABLE IF EXISTS user_devices")
    _try("ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_users_role")
    for col in _USER_COLUMNS:
        name = col.split()[0]
        op.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {name}")
