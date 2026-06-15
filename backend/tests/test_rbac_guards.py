"""RBAC guard tests for the Phase 1-3 routers.

Each v2 router gates writes behind a role/permission guard. These tests prove the
guards accept the right principals and raise 403 for everyone else. They call the
guard functions directly (no live server needed).

NOTE ON TENANT ISOLATION: the DoD also asks for a tenant-isolation test ("a query
as tenant A returns zero tenant-B rows"). This ERP is single-tenant on MongoDB —
there is no tenant_id scoping on business collections and no RLS (Mongo has none).
A meaningful isolation test cannot exist until multi-tenancy is built, so it is
intentionally absent rather than faked. See PLAN.md / CHANGELOG.md.
"""
import asyncio

import pytest
from fastapi import HTTPException

from routers.inventory_v2 import _require_inventory
from routers.purchase_v2 import _require_purchase
from routers.audit import require_auditor_or_admin


def _expect_403(fn, user):
    try:
        fn(user)
    except HTTPException as e:
        assert e.status_code == 403
        return
    raise AssertionError("expected HTTPException(403)")


# ───────────────────────── Inventory guard ─────────────────────────

def test_inventory_allows_admin():
    assert _require_inventory({"role": "admin"})["role"] == "admin"


def test_inventory_allows_module_permission():
    user = {"role": "employee", "module_permissions": ["inventory"]}
    assert _require_inventory(user) is user


def test_inventory_rejects_other_role():
    _expect_403(_require_inventory, {"role": "employee", "module_permissions": []})


# ───────────────────────── Purchase guard ─────────────────────────

def test_purchase_allows_admin_and_accountant():
    assert _require_purchase({"role": "admin"})["role"] == "admin"
    assert _require_purchase({"role": "accountant"})["role"] == "accountant"


def test_purchase_allows_module_permission():
    user = {"role": "employee", "module_permissions": ["purchase"]}
    assert _require_purchase(user) is user


def test_purchase_rejects_other_role():
    _expect_403(_require_purchase, {"role": "hr", "module_permissions": []})


# ───────────────────────── Audit-log guard (admin/auditor only) ─────────────────────────

def test_audit_allows_admin_and_auditor():
    assert asyncio.run(require_auditor_or_admin(user={"role": "admin"}))["role"] == "admin"
    assert asyncio.run(require_auditor_or_admin(user={"role": "auditor"}))["role"] == "auditor"


def test_audit_allows_audit_permission():
    user = {"role": "employee", "module_permissions": ["audit"]}
    assert asyncio.run(require_auditor_or_admin(user=user)) is user


def test_audit_rejects_plain_user():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_auditor_or_admin(user={"role": "accountant", "module_permissions": []}))
    assert exc.value.status_code == 403
