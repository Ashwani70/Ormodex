"""Multi-tenant data backfill.

Phase 1 of the multi-company conversion (see core/tenant.py's docstring —
"multi-tenancy is one change away"). Every table that already carries a
tenant_id column (~148 of ~150 — added as scaffolding well before this
migration) gets any NULL tenant_id backfilled to the 'default' sentinel,
matching core/tenant.py's existing DEFAULT_TENANT fallback. This makes the
backfill a no-op description of the status quo, not a behavior change: today
resolve_tenant() already treats every user as tenant 'default' in practice
(User.tenant_id is never populated by routers/users.py's create_user), so
after this migration every ROW also explicitly says 'default' instead of
NULL meaning the same thing implicitly.

WHY NOW, SEPARATE FROM ENFORCEMENT:
  A later phase adds an enforcement layer (core/tenant.py's ContextVar +
  core/_mongo_compat.py / core/utils.py's crud_get/crud_update/crud_delete)
  that will filter every tenant-having table by tenant_id. That layer must
  never encounter a NULL tenant_id row once enforcement is live — NULL would
  either be invisible under a strict equality filter (data appears to
  vanish) or require special-casing (a grandfathering concept that makes no
  sense for tenant isolation, unlike the row-ownership feature's deliberate
  NULL-is-visible-to-everyone choice — a cross-tenant leak has no acceptable
  "grandfathered" version). Backfilling now, well before enforcement can ever
  be flipped on, means enforcement lands on already-consistent data.

  This migration does NOT add a NOT NULL constraint — that is a deliberate
  follow-up step after a soak period confirms the backfill is complete and
  correct (matching this repo's convention of not combining a data migration
  with a constraint tightening in the same migration; see 031's own
  additive-only downgrade() convention).

Also renames existing `counters` rows (core/schema.py's Counter table, used
by next_doc_number for document numbering) from `{collection}:{prefix}` to
`default:{collection}:{prefix}` so that once next_doc_number becomes
tenant-aware, the 'default' tenant's existing sequences continue from where
they left off instead of silently resetting to 1 (which could collide with
already-issued document numbers).

Table list is derived from information_schema at migration time rather than
hardcoded, so this migration stays correct even if new tenant_id-bearing
tables are added between when this file is written and when it runs.
"""
from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None

DEFAULT_TENANT = "default"


def _tenant_tables() -> list[str]:
    conn = op.get_bind()
    rows = conn.exec_driver_sql(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND column_name = 'tenant_id' "
        "ORDER BY table_name"
    ).fetchall()
    return [r[0] for r in rows]


def _try(sql: str, label: str) -> None:
    # SAVEPOINT per statement — matches 031_row_ownership.py's pattern so one
    # failing statement (e.g. a table locked, or already backfilled by a
    # partial prior run) doesn't abort the whole migration.
    try:
        with op.get_bind().begin_nested():
            op.execute(sql)
    except Exception as exc:
        print(f"[032] {label} non-fatal: {exc}")


def upgrade() -> None:
    tables = _tenant_tables()
    print(f"[032] backfilling tenant_id on {len(tables)} tables")
    for table in tables:
        _try(
            f'UPDATE "{table}" SET tenant_id = \'{DEFAULT_TENANT}\' WHERE tenant_id IS NULL',
            f"{table}.tenant_id backfill",
        )

    # Rename existing counter keys so document-numbering sequences carry
    # forward under the future tenant-scoped key format instead of resetting
    # to 1 the first time a tenant-aware next_doc_number() runs.
    _try(
        "UPDATE counters SET key = 'default:' || key "
        "WHERE key NOT LIKE 'default:%'",
        "counters.key rename",
    )


def downgrade() -> None:
    pass  # data-only backfill; safe to leave (NULLs were never distinguishable from 'default' in practice)
