"""Full cheque printing module — extend cheque_transactions + add cheque_issue_register.

Adds all columns required for:
- Auto-fill from vouchers (source_type, source_id, voucher_number, narration, company_name)
- Full lifecycle (void, cleared, bounced, reprint tracking, print_ip)
- Cheque issue register table
"""
from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    # ── cheque_transactions: add missing columns ─────────────────────────────────
    new_cols = [
        ("bank_name",              "varchar", "NULL"),
        ("template_id",            "varchar", "NULL"),
        ("cheque_number",          "varchar", "NULL"),
        ("payee_name",             "varchar", "NULL"),
        ("amount_in_words",        "varchar", "NULL"),
        ("source_type",            "varchar", "NULL"),
        ("source_id",              "varchar", "NULL"),
        ("voucher_number",         "varchar", "NULL"),
        ("narration",              "text",    "NULL"),
        ("company_name",           "varchar", "NULL"),
        ("is_void",                "boolean", "FALSE"),
        ("void_reason",            "text",    "NULL"),
        ("void_at",                "varchar", "NULL"),
        ("void_by",                "varchar", "NULL"),
        ("cancelled_at",           "varchar", "NULL"),
        ("cancelled_by",           "varchar", "NULL"),
        ("cancellation_reason",    "text",    "NULL"),
        ("cleared_date",           "varchar", "NULL"),
        ("bounced_date",           "varchar", "NULL"),
        ("bounced_reason",         "text",    "NULL"),
        ("printed_at",             "varchar", "NULL"),
        ("printed_by",             "varchar", "NULL"),
        ("printer",                "varchar", "NULL"),
        ("reprint_count",          "integer", "0"),
        ("last_reprint_at",        "varchar", "NULL"),
        ("last_reprint_by",        "varchar", "NULL"),
        ("print_ip",               "varchar", "NULL"),
        ("reprint_log",            "jsonb",   "NULL"),
        ("account_payee",          "boolean", "TRUE"),
        ("test_print",             "boolean", "FALSE"),
    ]
    for col, typ, default in new_cols:
        op.execute(
            f"ALTER TABLE cheque_transactions ADD COLUMN IF NOT EXISTS "
            f"{col} {typ} DEFAULT {default}"
        )

    # Add indexes
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cheque_txns_tenant_bank "
        "ON cheque_transactions (tenant_id, bank_account_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cheque_txns_tenant_date "
        "ON cheque_transactions (tenant_id, cheque_date)"
    )

    # ── cheque_issue_register ────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS cheque_issue_register (
            id          varchar PRIMARY KEY,
            tenant_id   varchar,
            bank_account_id varchar,
            bank_name   varchar,
            cheque_number varchar,
            cheque_txn_id varchar,
            payee_name  varchar,
            amount      numeric(18,4),
            cheque_date varchar,
            issue_date  varchar,
            status      varchar,
            voucher_number varchar,
            narration   text,
            issued_by   varchar,
            created_at  varchar,
            updated_at  varchar
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cheque_reg_tenant_id "
        "ON cheque_issue_register (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cheque_reg_tenant_bank "
        "ON cheque_issue_register (tenant_id, bank_account_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cheque_reg_tenant_date "
        "ON cheque_issue_register (tenant_id, issue_date)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS cheque_issue_register")
    drop_cols = [
        "bank_name", "template_id", "cheque_number", "payee_name", "amount_in_words",
        "source_type", "source_id", "voucher_number", "narration", "company_name",
        "is_void", "void_reason", "void_at", "void_by", "cancelled_at", "cancelled_by",
        "cancellation_reason", "cleared_date", "bounced_date", "bounced_reason",
        "printed_at", "printed_by", "printer", "reprint_count", "last_reprint_at",
        "last_reprint_by", "print_ip", "reprint_log", "account_payee", "test_print",
    ]
    for col in drop_cols:
        op.execute(f"ALTER TABLE cheque_transactions DROP COLUMN IF EXISTS {col}")
