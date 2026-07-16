"""Audit-trail guarantees for India's Companies Accounts Rules mandate.

Proves the two properties the mandate hinges on, at the data layer:

  1. A business write and its audit row commit together — if the audit insert
     fails, the business write is rolled back (never persists un-audited).
  2. An audit row, once written, cannot be mutated through the application —
     core.utils exposes no update/delete path for audit_logs, and the read
     endpoint is read-only + RBAC-guarded.

Post-migration these run against the real PostgreSQL/Supabase data layer:
`crud_create`/`crud_update`/`crud_delete` write the business row and its audit
row in one `get_session()` transaction, so atomicity is a real DB property here
(not a fake's simulation). Each test reads the audit row back from the
`audit_logs` table and cleans up everything it created.

Audit row schema (current, post-migration): action ('create'/'update'/'delete'),
collection, doc_id, before (JSONB), after (JSONB), user_id, created_at.
"""
import asyncio

import pytest

import core.utils as utils
from core.db import db


USER = {"id": "u1", "name": "Auditor Tester", "role": "admin"}


async def _audit_rows_for(collection: str, doc_id: str) -> list[dict]:
    """Read every audit row written for one business document, newest first."""
    return await db.audit_logs.find(
        {"collection": collection, "doc_id": doc_id}
    ).sort("created_at", -1).to_list(50)


async def _cleanup(collection: str, doc_id: str):
    """Remove the business row + its audit trail so the shared DB stays clean."""
    await db.audit_logs.delete_many({"collection": collection, "doc_id": doc_id})
    await db[collection].delete_one({"id": doc_id})


# ─────────────────────────────────────────────────────────────────────────────
# 1. Atomicity: write + audit commit together (rollback if audit fails)
# ─────────────────────────────────────────────────────────────────────────────

def test_create_writes_business_doc_and_audit_row_together():
    doc = asyncio.run(utils.crud_create("purchase_orders", {"po_number": "AUDIT-PO-1"}, user=USER))
    try:
        # Business row persisted.
        row = asyncio.run(db.purchase_orders.find_one({"id": doc["id"]}))
        assert row is not None
        assert row["po_number"] == "AUDIT-PO-1"

        # Exactly one audit row, with the create action + after-image.
        logs = asyncio.run(_audit_rows_for("purchase_orders", doc["id"]))
        assert len(logs) == 1
        log = logs[0]
        assert log["action"] == "create"
        assert log["collection"] == "purchase_orders"
        assert log["doc_id"] == doc["id"]
        assert log["after"]["po_number"] == "AUDIT-PO-1"
        # Mongo's _id must never leak into the captured snapshot.
        assert "_id" not in (log["after"] or {})
    finally:
        asyncio.run(_cleanup("purchase_orders", doc["id"]))


def test_create_rolls_back_business_doc_when_audit_insert_fails(monkeypatch):
    """If the audit row can't be written, the business row must NOT persist —
    they share one transaction. We force the audit insert to fail by making the
    audit-entry builder raise, then assert nothing was committed."""
    doc_id_holder = {}

    real_build = utils.build_audit_entry

    def boom(*args, **kwargs):
        # Capture the id that crud_create allocated, then sabotage the audit write.
        entry = real_build(*args, **kwargs)
        doc_id_holder["id"] = entry.get("doc_id")
        raise RuntimeError("simulated audit-store failure")

    monkeypatch.setattr(utils, "build_audit_entry", boom)

    raised = False
    try:
        asyncio.run(utils.crud_create("purchase_orders", {"po_number": "AUDIT-PO-2"}, user=USER))
    except RuntimeError:
        raised = True
    monkeypatch.undo()

    assert raised, "audit failure should propagate"
    # The business write must NOT persist without its audit row.
    pid = doc_id_holder.get("id")
    if pid:
        row = asyncio.run(db.purchase_orders.find_one({"id": pid}))
        assert row is None, "business row must roll back when audit insert fails"
        asyncio.run(_cleanup("purchase_orders", pid))
    # Belt-and-braces: no audit row for this PO number either.
    leaked = asyncio.run(db.purchase_orders.find({"po_number": "AUDIT-PO-2"}).to_list(10))
    for r in leaked:
        asyncio.run(_cleanup("purchase_orders", r["id"]))
    assert leaked == [], "no business row should exist for the failed create"


def test_update_records_changed_fields():
    doc = asyncio.run(utils.crud_create("vendors", {"name": "Acme", "phone": "111"}, user=USER))
    try:
        asyncio.run(utils.crud_update("vendors", doc["id"], {"phone": "222"}, user=USER))

        logs = asyncio.run(_audit_rows_for("vendors", doc["id"]))
        update_log = [l for l in logs if l["action"] == "update"][0]
        # The update audit carries the before-image and the applied changes.
        assert update_log["before"]["phone"] == "111"
        assert update_log["after"]["phone"] == "222"
        # The substantive change is the phone, not the name.
        changed = utils._diff_fields(update_log["before"], update_log["after"])
        assert "phone" in changed
        assert "name" not in changed
    finally:
        asyncio.run(_cleanup("vendors", doc["id"]))


def test_delete_captures_before_image_and_audit():
    doc = asyncio.run(utils.crud_create("vendors", {"name": "Gone Inc"}, user=USER))
    asyncio.run(utils.crud_delete("vendors", doc["id"], user=USER))
    try:
        # Business row is gone.
        assert asyncio.run(db.vendors.find_one({"id": doc["id"]})) is None
        logs = asyncio.run(_audit_rows_for("vendors", doc["id"]))
        del_log = [l for l in logs if l["action"] == "delete"][0]
        assert del_log["before"]["name"] == "Gone Inc"
    finally:
        # crud_delete removed the business row; clear the audit trail.
        asyncio.run(db.audit_logs.delete_many({"collection": "vendors", "doc_id": doc["id"]}))


# ─────────────────────────────────────────────────────────────────────────────
# 2. Immutability: no application path mutates an audit row (pure/structural)
# ─────────────────────────────────────────────────────────────────────────────

def test_audit_module_exposes_no_write_routes():
    """The audit router is read-only: only GET routes, no POST/PATCH/PUT/DELETE."""
    from routers.audit import router

    methods = set()
    for route in router.routes:
        methods |= set(getattr(route, "methods", set()))
    methods.discard("HEAD")
    methods.discard("OPTIONS")
    assert methods == {"GET"}, f"audit router must be read-only, got {methods}"


def test_utils_has_no_audit_update_or_delete_helper():
    """core.utils offers no helper that updates or deletes audit rows."""
    audit_names = [n for n in dir(utils) if "audit" in n.lower()]
    forbidden = ("update", "edit", "delete", "remove", "purge", "modify")
    offenders = [n for n in audit_names if any(f in n.lower() for f in forbidden)]
    assert offenders == [], f"audit helpers must be append-only, found: {offenders}"
    assert "log_audit" in audit_names


def test_changed_fields_ignores_timestamp_noise():
    """updated_at/created_at churn must not register as a substantive change."""
    fields = utils._diff_fields(
        {"name": "X", "updated_at": "t1"},
        {"name": "X", "updated_at": "t2"},
    )
    assert fields == []
