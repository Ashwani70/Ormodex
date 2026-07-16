# Audit Trail — design & compliance notes

Implements India's audit-trail mandate (Companies (Accounts) Rules, proviso to
Rule 3(1); auditor reporting under Rule 11(g), effective FY 2023-24): every
create / edit / delete on accounting records must be logged, immutable, and
non-disableable.

## How it works on this stack

The original work order targeted NestJS/Postgres with a TypeORM subscriber and
`REVOKE UPDATE/DELETE` grants. This codebase is **FastAPI + MongoDB**, so the
mechanism differs while the guarantees are preserved:

- **Capture point** — `core.utils.log_audit` writes an append-only row to the
  `audit_logs` collection. It is invoked automatically by the shared
  `crud_create` / `crud_update` / `crud_delete` helpers that every module's
  write path already uses, plus auto-created accounting records such as the
  purchase journal entry (`core.ledger_posting`). There is no per-call flag to
  disable it — turning it off would mean not calling the shared CRUD helper,
  which would also skip the business write.

- **Atomicity** — `core.utils._write_with_audit` wraps the business write and
  its audit insert:
  - If MongoDB is a **replica set / sharded cluster** (transactions available),
    both run in one multi-document transaction — commit together or roll back
    together.
  - On a **standalone** server (no transactions), the business write runs first;
    if the audit insert then fails, the business write is **compensated**
    (the create is deleted, the delete re-inserted, the update reverted). So a
    business change can never persist without its audit row.
  - Proven by `tests/test_audit_trail.py` (incl. the rollback-on-audit-failure
    case, which exercises the standalone path).

- **Row schema** — `id`, `tenant_id`, `user_id`, `entity_type`, `entity_id`,
  `action` (CREATE/UPDATE/DELETE), `before_json`, `after_json`,
  `changed_fields`, `ip`, `created_at`. Legacy aliases (`collection_name`,
  `doc_id`, `old_values`, `new_values`, `timestamp`) are retained so existing
  readers (`/reports/audit`) keep working.

- **Read access** — `GET /audit` (alias: `GET /audit-log`) (`routers/audit.py`), filterable by entity,
  entity id, user, action and date range, tenant-scoped, and RBAC-guarded to
  `admin` / `auditor` roles (or an explicit `audit` module permission). The
  router exposes **only GET** routes — no application path updates or deletes a
  row (asserted by a test).

## Known gap vs. a Postgres `REVOKE`-based control

On MongoDB there is no per-collection `GRANT/REVOKE UPDATE,DELETE` equivalent to
Postgres. Application-level immutability is enforced (no write path mutates
`audit_logs`), but for **DB-enforced** immutability the deployment should also:

1. Run the app under a Mongo user whose role grants only `find` + `insert` on the
   `audit_logs` collection (no `update`/`remove`). This is the operational
   equivalent of revoking UPDATE/DELETE grants.
2. Prefer a replica-set deployment so write+audit atomicity uses real
   transactions rather than the compensating-rollback fallback.

These are deployment/ops controls, intentionally **not** faked in code.

## `tenant_id`

This ERP is currently single-tenant (no `tenant_id` on business records). The
audit row carries a nullable `tenant_id` and the read endpoint scopes by it when
present, so multi-tenancy can be switched on later without a schema change here.
