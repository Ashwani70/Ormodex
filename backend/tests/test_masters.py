"""Masters subsystem: tenant isolation, soft-delete, audit, tree validation.

Drives core.masters_crud against an in-memory async Mongo fake (no live server).
Proves the four non-negotiables for the new Masters collections:
  - tenant_id stamped on every doc; a query as tenant A returns zero tenant-B rows
  - soft-delete only (is_deleted/deleted_at); listed results exclude deleted
  - every create/update/delete writes an audit record
  - tree masters validate parent (cross-tenant parent rejected, self-parent rejected)
"""
import asyncio

import pytest
from fastapi import HTTPException

import core.db
import core.utils as utils
import core.masters_crud as mc


# ── In-memory async Mongo fake supporting the operators masters_crud uses ──

def _matches(doc, q):
    for k, v in q.items():
        if k == "$or":
            if not any(_matches(doc, sub) for sub in v):
                return False
            continue
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$ne" in v and actual == v["$ne"]:
                return False
            if "$regex" in v:
                import re
                if not (isinstance(actual, str) and re.search(v["$regex"], actual, re.I)):
                    return False
            if "$gte" in v and not (actual is not None and actual >= v["$gte"]):
                return False
            if "$lte" in v and not (actual is not None and actual <= v["$lte"]):
                return False
        elif actual != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs): self._docs = docs
    def sort(self, field, direction=1):
        self._docs.sort(key=lambda d: (d.get(field) is None, d.get(field)), reverse=direction < 0)
        return self
    def skip(self, n): self._docs = self._docs[n:]; return self
    def limit(self, n): self._docs = self._docs[:n]; return self
    async def to_list(self, _n): return [dict(d) for d in self._docs]


class _Collection:
    def __init__(self): self.docs = []
    async def insert_one(self, doc, session=None):
        self.docs.append(dict(doc)); return type("R", (), {"inserted_id": doc.get("id")})()
    async def find_one(self, q, projection=None, session=None):
        for d in self.docs:
            if _matches(d, q):
                out = dict(d); out.pop("_id", None); return out
        return None
    def find(self, q=None, projection=None):
        return _Cursor([dict(d) for d in self.docs if _matches(d, q or {})])
    async def count_documents(self, q):
        return len([d for d in self.docs if _matches(d, q or {})])
    async def update_one(self, q, update, session=None):
        for d in self.docs:
            if _matches(d, q):
                d.update(update.get("$set", {})); return type("R", (), {"matched_count": 1})()
        return type("R", (), {"matched_count": 0})()
    async def create_index(self, *a, **k): return "idx"


class _DB:
    def __init__(self): self._c = {}
    def __getitem__(self, n): return self._c.setdefault(n, _Collection())
    def __getattr__(self, n):
        if n.startswith("_"): raise AttributeError(n)
        return self[n]


def _setup():
    db = _DB()
    core.db.db = db
    utils.db = db
    mc.db = db
    return db


USER = {"id": "u1", "name": "Tester", "role": "admin"}
GROUPS = "master_groups"


def _make_group(tenant, name, parent=None):
    return asyncio.run(mc.masters_create(
        GROUPS, {"name": name, "nature": "Asset", "parent_group_id": parent},
        tenant, USER, unique_fields=["name"], parent_field="parent_group_id"))


# ───────────────────────── Tenant isolation ─────────────────────────

def test_tenant_isolation_list_excludes_other_tenant():
    db = _setup()
    _make_group("tenantA", "Cash A")
    _make_group("tenantB", "Cash B")

    a_rows = asyncio.run(mc.masters_list(GROUPS, "tenantA"))
    b_rows = asyncio.run(mc.masters_list(GROUPS, "tenantB"))

    assert [r["name"] for r in a_rows] == ["Cash A"]
    assert [r["name"] for r in b_rows] == ["Cash B"]
    # The non-negotiable: a query as tenant A returns zero tenant-B rows.
    assert all(r["tenant_id"] == "tenantA" for r in a_rows)
    assert not any(r["name"] == "Cash B" for r in a_rows)


def test_tenant_cannot_get_other_tenants_doc():
    db = _setup()
    g = _make_group("tenantA", "Secret A")
    # Same id, different tenant → not found.
    with pytest.raises(HTTPException) as exc:
        asyncio.run(mc.masters_get(GROUPS, g["id"], "tenantB"))
    assert exc.value.status_code == 404


def test_every_doc_carries_tenant_id():
    db = _setup()
    g = _make_group("tenantA", "Bank")
    assert g["tenant_id"] == "tenantA"
    assert g["is_deleted"] is False and g["deleted_at"] is None


# ───────────────────────── Soft delete ─────────────────────────

def test_soft_delete_sets_flag_and_hides_from_list():
    db = _setup()
    g = _make_group("t1", "Temp")
    res = asyncio.run(mc.masters_soft_delete(GROUPS, g["id"], "t1", USER))
    assert res["soft_deleted"] is True

    # Document still physically present (never hard-deleted)...
    raw = db[GROUPS].docs[0]
    assert raw["is_deleted"] is True and raw["deleted_at"] is not None
    # ...but excluded from normal listing and get.
    assert asyncio.run(mc.masters_list(GROUPS, "t1")) == []
    with pytest.raises(HTTPException):
        asyncio.run(mc.masters_get(GROUPS, g["id"], "t1"))


def test_cannot_delete_parent_with_children():
    db = _setup()
    parent = _make_group("t1", "Parent")
    _make_group("t1", "Child", parent=parent["id"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(mc.masters_soft_delete(GROUPS, parent["id"], "t1", USER, child_parent_field="parent_group_id"))
    assert exc.value.status_code == 400


# ───────────────────────── Audit ─────────────────────────

def test_create_update_delete_each_write_audit():
    db = _setup()
    g = _make_group("t1", "Audited")
    asyncio.run(mc.masters_update(GROUPS, g["id"], {"name": "Renamed"}, "t1", USER, unique_fields=["name"]))
    asyncio.run(mc.masters_soft_delete(GROUPS, g["id"], "t1", USER))

    actions = [a["action"] for a in db.audit_logs.docs]
    assert actions == ["CREATE", "UPDATE", "DELETE"]
    upd = next(a for a in db.audit_logs.docs if a["action"] == "UPDATE")
    assert upd["before_json"]["name"] == "Audited"
    assert upd["after_json"]["name"] == "Renamed"


# ───────────────────────── Tree parent validation ─────────────────────────

def test_parent_must_exist_in_same_tenant():
    db = _setup()
    other = _make_group("tenantA", "Foreign Parent")
    # Creating in tenantB referencing tenantA's group must fail.
    with pytest.raises(HTTPException) as exc:
        asyncio.run(mc.masters_create(
            GROUPS, {"name": "Child", "nature": "Asset", "parent_group_id": other["id"]},
            "tenantB", USER, parent_field="parent_group_id"))
    assert exc.value.status_code == 400


def test_self_parent_rejected_on_update():
    db = _setup()
    g = _make_group("t1", "Node")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(mc.masters_update(
            GROUPS, g["id"], {"parent_group_id": g["id"]}, "t1", USER, parent_field="parent_group_id"))
    assert exc.value.status_code == 400


def test_unique_name_enforced_per_tenant():
    db = _setup()
    _make_group("t1", "Dup")
    with pytest.raises(HTTPException) as exc:
        _make_group("t1", "Dup")
    assert exc.value.status_code == 400
    # But the same name is fine in a different tenant.
    assert _make_group("t2", "Dup")["name"] == "Dup"


# ───────────────────────── Statutory singletons (get + upsert) ─────────────────────────

SING = "statutory_company_gst_details"


def test_singleton_get_empty_then_upsert_creates():
    db = _setup()
    empty = asyncio.run(mc.singleton_get(SING, "t1"))
    assert empty.get("exists") is False  # no doc yet

    created = asyncio.run(mc.singleton_upsert(SING, {"gstin": "27AAA", "state": "MH"}, "t1", USER))
    assert created["gstin"] == "27AAA"
    assert created["tenant_id"] == "t1"
    fetched = asyncio.run(mc.singleton_get(SING, "t1"))
    assert fetched["gstin"] == "27AAA"


def test_singleton_upsert_is_idempotent_and_merges_partial():
    db = _setup()
    asyncio.run(mc.singleton_upsert(SING, {"gstin": "27AAA", "state": "MH"}, "t1", USER))
    # Second upsert with a partial field merges, does not create a 2nd doc.
    asyncio.run(mc.singleton_upsert(SING, {"state": "KA"}, "t1", USER))

    docs = [d for d in db[SING].docs if d["tenant_id"] == "t1"]
    assert len(docs) == 1                      # still exactly one doc per tenant
    assert docs[0]["gstin"] == "27AAA"         # untouched field preserved
    assert docs[0]["state"] == "KA"            # provided field updated


def test_singleton_is_tenant_isolated():
    db = _setup()
    asyncio.run(mc.singleton_upsert(SING, {"gstin": "27-A"}, "tenantA", USER))
    asyncio.run(mc.singleton_upsert(SING, {"gstin": "29-B"}, "tenantB", USER))
    assert asyncio.run(mc.singleton_get(SING, "tenantA"))["gstin"] == "27-A"
    assert asyncio.run(mc.singleton_get(SING, "tenantB"))["gstin"] == "29-B"


def test_singleton_upsert_audited():
    db = _setup()
    asyncio.run(mc.singleton_upsert(SING, {"gstin": "27-A"}, "t1", USER))
    asyncio.run(mc.singleton_upsert(SING, {"gstin": "27-B"}, "t1", USER))
    actions = [a["action"] for a in db.audit_logs.docs]
    assert actions == ["CREATE", "UPDATE"]


# ───────────────────────── Statutory list master (TDS section) ─────────────────────────

TDS = "master_tds_nature_of_payment"


def test_statutory_list_master_create_and_isolate():
    db = _setup()
    asyncio.run(mc.masters_create(
        TDS, {"section_code": "194C", "description": "Contractors", "rate_with_pan": 1.0},
        "t1", USER, unique_fields=["section_code"]))
    rows_a = asyncio.run(mc.masters_list(TDS, "t1", sort_field="section_code"))
    rows_b = asyncio.run(mc.masters_list(TDS, "t2", sort_field="section_code"))
    assert [r["section_code"] for r in rows_a] == ["194C"]
    assert rows_b == []  # other tenant sees nothing


# ───────────────────────── Server-side pagination / filter / search ─────────────────────────

def _seed_groups(db, n, tenant="t1"):
    for i in range(n):
        asyncio.run(mc.masters_create(
            GROUPS, {"name": f"G{i:03d}", "nature": "Asset"}, tenant, USER, unique_fields=["name"]))


def test_pagination_envelope_shape_and_slicing():
    db = _setup()
    _seed_groups(db, 25)
    p1 = asyncio.run(mc.masters_list_paginated(GROUPS, "t1", page=1, limit=10))
    assert p1["total"] == 25 and p1["page"] == 1 and p1["limit"] == 10 and p1["pages"] == 3
    assert len(p1["items"]) == 10
    assert [r["name"] for r in p1["items"]] == [f"G{i:03d}" for i in range(10)]  # sorted by name

    p3 = asyncio.run(mc.masters_list_paginated(GROUPS, "t1", page=3, limit=10))
    assert len(p3["items"]) == 5      # remainder
    assert p3["items"][0]["name"] == "G020"


def test_pagination_clamps_untrusted_input():
    db = _setup()
    _seed_groups(db, 5)
    # page < 1 and limit > 200 are clamped (never trust the client).
    r = asyncio.run(mc.masters_list_paginated(GROUPS, "t1", page=0, limit=99999))
    assert r["page"] == 1 and r["limit"] == 200


def test_pagination_is_tenant_scoped():
    db = _setup()
    _seed_groups(db, 3, tenant="t1")
    _seed_groups(db, 7, tenant="t2")
    assert asyncio.run(mc.masters_list_paginated(GROUPS, "t1", page=1, limit=50))["total"] == 3
    assert asyncio.run(mc.masters_list_paginated(GROUPS, "t2", page=1, limit=50))["total"] == 7


def test_pagination_search_filters_total():
    db = _setup()
    asyncio.run(mc.masters_create(GROUPS, {"name": "Cash", "nature": "Asset"}, "t1", USER, unique_fields=["name"]))
    asyncio.run(mc.masters_create(GROUPS, {"name": "Bank", "nature": "Asset"}, "t1", USER, unique_fields=["name"]))
    r = asyncio.run(mc.masters_list_paginated(GROUPS, "t1", q="cash", search_fields=["name"], page=1, limit=50))
    assert r["total"] == 1 and r["items"][0]["name"] == "Cash"


def test_pagination_excludes_soft_deleted():
    db = _setup()
    g = asyncio.run(mc.masters_create(GROUPS, {"name": "Temp", "nature": "Asset"}, "t1", USER, unique_fields=["name"]))
    asyncio.run(mc.masters_soft_delete(GROUPS, g["id"], "t1", USER))
    r = asyncio.run(mc.masters_list_paginated(GROUPS, "t1", page=1, limit=50))
    assert r["total"] == 0
