"""Add tenant_id + doc_type to document_numbering_settings.

Part of making Company Profile / PO Numbering / Document Numbering genuinely
per-tenant (see core/tenant.py's tenant_ctx/resolve_tenant/stamp_tenant, the
same helpers core/masters_crud.py already uses for ~60 masters endpoints).
document_numbering_settings previously had no ORM class and no tenant_id
column at all — it was only ever reached via the dynamic db[...] compat path,
keyed by a bare `doc_type` id (e.g. "grn", "invoice") shared by every tenant.

doc_type is added as a real column (not folded into `id`) so a tenant's row
is found via {"tenant_id": tenant_id, "doc_type": doc_type} rather than a
composite string that would need parsing back apart — matching how the
DocumentNumberingSetting ORM class's other sibling tables use a plain
tenant_id column for scoping, never the primary key.

Table has 0 live rows (confirmed via introspection immediately before writing
this migration) — clean additive change, no backfill needed, unlike 032's
backfill of already-populated tables.
"""
from alembic import op

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def _try(sql: str, label: str) -> None:
    # SAVEPOINT per statement — matches 031/032's pattern so one failing
    # statement doesn't abort the whole migration.
    try:
        with op.get_bind().begin_nested():
            op.execute(sql)
    except Exception as exc:
        print(f"[033] {label} non-fatal: {exc}")


def upgrade() -> None:
    _try(
        "ALTER TABLE document_numbering_settings ADD COLUMN IF NOT EXISTS tenant_id TEXT",
        "document_numbering_settings.tenant_id",
    )
    _try(
        "ALTER TABLE document_numbering_settings ADD COLUMN IF NOT EXISTS doc_type TEXT",
        "document_numbering_settings.doc_type",
    )
    _try(
        "CREATE INDEX IF NOT EXISTS ix_document_numbering_settings_tenant_doctype "
        "ON document_numbering_settings (tenant_id, doc_type)",
        "ix_document_numbering_settings_tenant_doctype",
    )


def downgrade() -> None:
    pass  # additive-only; safe to leave
