"""Module-permission wiring tests.

Proves the catalog/validator behave, that UserCreate accepts module_permissions,
and that a granted key actually satisfies the corresponding router guard (the
bug this fixes: create-user stored `permissions` but guards read
`module_permissions`).
"""
import os

os.environ.setdefault("JWT_SECRET", "test-secret-for-module-perm-tests")

from core.modules import MODULE_KEYS, valid_module_keys
from core.models import UserCreate
from routers.inventory_v2 import _require_inventory
from routers.accounting import _require_accounting

import pytest
from fastapi import HTTPException


def test_valid_module_keys_drops_unknown_and_dedups():
    assert valid_module_keys(["inventory", "bogus", "inventory", "sales"]) == ["inventory", "sales"]
    assert valid_module_keys([]) == []
    assert valid_module_keys(None) == []


def test_catalog_covers_guard_keys():
    # Keys the guards in this test reference must exist in the catalog.
    for k in ("inventory", "accounting", "sales", "payroll", "audit"):
        assert k in MODULE_KEYS


def test_usercreate_accepts_module_permissions():
    u = UserCreate(
        name="Op", email="op@example.com", password="Str0ng!Passw0rd",
        module_permissions=["inventory", "sales"],
    )
    assert u.module_permissions == ["inventory", "sales"]


def test_granted_module_satisfies_guard():
    # An employee granted "inventory" passes the inventory guard...
    user = {"role": "employee", "module_permissions": valid_module_keys(["inventory"])}
    assert _require_inventory(user) is user
    # ...but not the accounting guard.
    with pytest.raises(HTTPException) as exc:
        _require_accounting(user)
    assert exc.value.status_code == 403


def test_admin_bypasses_guards_without_modules():
    admin = {"role": "admin", "module_permissions": []}
    assert _require_inventory(admin) is admin
    assert _require_accounting(admin) is admin
