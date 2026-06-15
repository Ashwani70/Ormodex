"""Audit-trail guarantees for India's Companies Accounts Rules mandate.

Proves the two properties the mandate hinges on, at the data layer:

  1. A business write and its audit row commit together — if the audit insert
     fails, the business write is rolled back (never persists un-audited).
  2. An audit row, once written, cannot be mutated through the application —
     core.utils exposes no update/delete path for audit_logs, and the read
     endpoint is read-only + RBAC-guarded.

These run without a live server or a real MongoDB: core.db.db is monkeypatched
with a minimal in-memory async fake, and coroutines are driven with asyncio.run
(no pytest-asyncio plugin required, matching what's installed here).
"""
import asyncio

import core.db
import core.utils as utils


# ─────────────────────────────────────────────────────────────────────────────
# Minimal in-memory async Mongo substitute (only what crud_*/log_audit touch)
# ─────────────────────────────────────────────────────────────────────────────

class _FakeCollection:
    def __init__(self, fail_on_insert=False):
        self.docs: list[dict] = []
        self.fail_on_insert = fail_on_insert

    async def insert_one(self, doc, session=None):
        if self.fail_on_insert:
            raise RuntimeError("simulated audit-store failure")
        # Mongo would stamp _id; mimic it so callers that pop("_id") still work.
        stored = dict(doc)
        stored.setdefault("_id", f"oid_{len(self.docs)}")
        self.docs.append(stored)
        return type("R", (), {"inserted_id": stored["_id"]})()

    async def find_one(self, q, projection=None, session=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                out = {k: v for k, v in d.items()}
                if projection and projection.get("_id") == 0:
                    out.pop("_id", None)
                return out
        return None

    async def update_one(self, q, update, session=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(update.get("$set", {}))
                return type("R", (), {"matched_count": 1})()
        return type("R", (), {"matched_count": 0})()

    async def replace_one(self, q, doc, session=None):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in q.items()):
                self.docs[i] = dict(doc)
                return type("R", (), {"matched_count": 1})()
        return type("R", (), {"matched_count": 0})()

    async def delete_one(self, q, session=None):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in q.items()):
                self.docs.pop(i)
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

    def count(self):
        return len(self.docs)


class _FakeDB:
    """Standalone (non-replica-set) Mongo: transactions unsupported, so crud_*
    exercises the compensating-rollback fallback path — the harder case to prove."""
    def __init__(self, audit_fails=False):
        self._cols: dict[str, _FakeCollection] = {}
        self.audit_logs = _FakeCollection(fail_on_insert=audit_fails)
        self._cols["audit_logs"] = self.audit_logs

    def __getitem__(self, name):
        if name not in self._cols:
            self._cols[name] = _FakeCollection()
        return self._cols[name]

    def __getattr__(self, name):
        # Attribute access (db.foo) maps to the same collections as db["foo"].
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]


def _patch_db(fake):
    """Point both core.db.db and the already-imported core.utils.db at the fake."""
    core.db.db = fake
    utils.db = fake
    utils._txn_supported = False  # force the no-transaction fallback path


USER = {"id": "u1", "name": "Auditor Tester", "role": "admin"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Atomicity: write + audit commit together (rollback if audit fails)
# ─────────────────────────────────────────────────────────────────────────────

def test_create_writes_business_doc_and_audit_row_together():
    fake = _FakeDB()
    _patch_db(fake)

    doc = asyncio.run(utils.crud_create("purchase_orders", {"po_number": "PO-1"}, user=USER))

    assert fake["purchase_orders"].count() == 1
    assert fake.audit_logs.count() == 1
    log = fake.audit_logs.docs[0]
    assert log["action"] == "CREATE"
    assert log["entity_type"] == "purchase_orders"
    assert log["entity_id"] == doc["id"]
    assert log["after_json"]["po_number"] == "PO-1"
    # Mongo's _id must never leak into the captured snapshot.
    assert "_id" not in (log["after_json"] or {})


def test_create_rolls_back_business_doc_when_audit_insert_fails():
    fake = _FakeDB(audit_fails=True)
    _patch_db(fake)

    raised = False
    try:
        asyncio.run(utils.crud_create("purchase_orders", {"po_number": "PO-2"}, user=USER))
    except RuntimeError:
        raised = True

    assert raised, "audit failure should propagate"
    # The business write must NOT persist without its audit row.
    assert fake["purchase_orders"].count() == 0
    assert fake.audit_logs.count() == 0


def test_update_records_changed_fields():
    fake = _FakeDB()
    _patch_db(fake)

    doc = asyncio.run(utils.crud_create("suppliers", {"name": "Acme", "phone": "111"}, user=USER))
    asyncio.run(utils.crud_update("suppliers", doc["id"], {"phone": "222"}, user=USER))

    update_log = [l for l in fake.audit_logs.docs if l["action"] == "UPDATE"][0]
    assert "phone" in update_log["changed_fields"]
    assert "name" not in update_log["changed_fields"]
    assert update_log["before_json"]["phone"] == "111"
    assert update_log["after_json"]["phone"] == "222"


def test_delete_captures_before_image_and_audit():
    fake = _FakeDB()
    _patch_db(fake)

    doc = asyncio.run(utils.crud_create("suppliers", {"name": "Gone Inc"}, user=USER))
    asyncio.run(utils.crud_delete("suppliers", doc["id"], user=USER))

    assert fake["suppliers"].count() == 0
    del_log = [l for l in fake.audit_logs.docs if l["action"] == "DELETE"][0]
    assert del_log["before_json"]["name"] == "Gone Inc"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Immutability: no application path mutates an audit row
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
    # No audit helper hints at mutation/removal of existing rows.
    forbidden = ("update", "edit", "delete", "remove", "purge", "modify")
    offenders = [n for n in audit_names if any(f in n.lower() for f in forbidden)]
    assert offenders == [], f"audit helpers must be append-only, found: {offenders}"
    # And the only public audit writer is the append-only log_audit.
    assert "log_audit" in audit_names


def test_changed_fields_ignores_timestamp_noise():
    """updated_at/created_at churn must not register as a substantive change."""
    fields = utils._diff_fields(
        {"name": "X", "updated_at": "t1"},
        {"name": "X", "updated_at": "t2"},
    )
    assert fields == []
