"""Add the columns the PO numbering engine reads/writes.

The initial PG model for ``po_numbering_settings`` only kept
prefix/padding/start_at, but core/po_numbering.py persists mode, separator,
FY/branch codes and sequence bounds. Those $set fields were silently dropped on
save, so configured templates had no effect. This adds them back. Idempotent.
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("mode", "varchar", "'AUTO'"),
    ("fy_format", "varchar", "''"),
    ("branch_code", "varchar", "''"),
    ("separator", "varchar", "'-'"),
    ("start_sequence", "integer", "1"),
    ("sequence_length", "integer", "5"),
    ("updated_by", "varchar", "NULL"),
)


def upgrade() -> None:
    for col, type_, default in _COLUMNS:
        op.execute(
            f"ALTER TABLE IF EXISTS po_numbering_settings "
            f"ADD COLUMN IF NOT EXISTS {col} {type_} DEFAULT {default}"
        )


def downgrade() -> None:
    for col, _type, _default in _COLUMNS:
        op.execute(
            f"ALTER TABLE IF EXISTS po_numbering_settings DROP COLUMN IF EXISTS {col}"
        )
