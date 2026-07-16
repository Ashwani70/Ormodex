"""Company profile: add PDF-header fields (website, CIN, IEC, state code, bank details).

WHY:
  Professional invoice/PDF headers across the ERP need the full legal supplier
  identity: website, CIN, IEC, GST state code, and bank details for the payment
  block. These are first-class, queryable company attributes, so they get real
  columns rather than living in the `extra` JSONB. All are nullable and added
  idempotently, so existing single-company rows and old PDFs keep working.

  Party (customer/vendor) display fields — billing/shipping address, state code,
  contact person, place of supply — and per-document payment terms are stored
  via the existing `extra`/JSONB auto-pack mechanism (see core/utils.py
  crud_create/_row_to_dict), so no column changes are needed there and old
  documents remain fully backward-compatible.
"""
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


_COLUMNS = [
    "website VARCHAR(255)",
    "cin VARCHAR(64)",
    "iec VARCHAR(64)",
    "state_code VARCHAR(8)",
    "bank_name VARCHAR(255)",
    "bank_account_no VARCHAR(64)",
    "bank_ifsc VARCHAR(32)",
    "bank_branch VARCHAR(255)",
    "declaration TEXT",
    "seal_url VARCHAR(512)",
]


def upgrade():
    for col in _COLUMNS:
        op.execute(f"ALTER TABLE company ADD COLUMN IF NOT EXISTS {col}")


def downgrade():
    for col in _COLUMNS:
        name = col.split()[0]
        op.execute(f"ALTER TABLE company DROP COLUMN IF EXISTS {name}")
