"""Add document_numbering_settings — a generalized version of
po_numbering_settings for document types beyond Purchase Order (GRN, Invoice,
and future additions via core/document_numbering.py's DOC_TYPES registry).

WHY:
  Every document type except Purchase Order (dedicated po_numbering_settings
  table) and Vouchers (VoucherType master's own numbering_method/prefix/
  suffix/restart_rule) used a fixed next_doc_number(prefix, collection)
  counter with no AUTO/MANUAL toggle, no FY/branch template, no settings
  surface at all. This table backs the new generalized settings page
  (Admin -> Document Numbering) for GRN/Invoice, keyed by doc_type so adding
  a further document type later is a registry entry, not a new table.
"""
from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS document_numbering_settings (
            id TEXT PRIMARY KEY,
            mode TEXT DEFAULT 'AUTO',
            prefix TEXT DEFAULT '',
            fy_format TEXT DEFAULT '',
            branch_code TEXT DEFAULT '',
            separator TEXT DEFAULT '-',
            start_sequence INTEGER DEFAULT 1,
            sequence_length INTEGER DEFAULT 5,
            updated_at TEXT,
            updated_by TEXT
        )
    """)


def downgrade():
    pass  # additive; safe to leave
