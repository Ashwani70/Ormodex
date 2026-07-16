"""Tests for forced-password-reset on login + the change-password endpoint.

Covers:
- ChangePasswordIn enforces the policy on the new password.
- _flag_password_if_weak sets the flag for a weak (but correct) password,
  clears a stale flag for a now-compliant one, and is idempotent.

DB access is stubbed: _flag_password_if_weak only calls db.users.update_one,
so a tiny recording fake is enough — no live MongoDB needed.
"""
import os

import pytest
from pydantic import ValidationError

os.environ.setdefault("JWT_SECRET", "test-secret-for-reset-tests")

from core.models import ChangePasswordIn

STRONG = "Str0ng!Passw0rd"
WEAK = "admin123"


# ───────────────────────── model validation ─────────────────────────

def test_change_password_rejects_weak_new():
    with pytest.raises(ValidationError):
        ChangePasswordIn(current_password="whatever", new_password="weak")


def test_change_password_accepts_strong_new():
    m = ChangePasswordIn(current_password="whatever", new_password=STRONG)
    assert m.new_password == STRONG


# ───────────────────────── flag logic ─────────────────────────

class _FakeUsers:
    """Records update_one calls and applies $set/$unset to an in-memory store."""
    def __init__(self, doc):
        self.doc = doc
        self.calls = []

    async def update_one(self, flt, update):
        self.calls.append(update)
        for k, v in update.get("$set", {}).items():
            self.doc[k] = v
        for k in update.get("$unset", {}):
            self.doc.pop(k, None)


@pytest.fixture
def patched_db(monkeypatch):
    """Patch routers.auth.db.users with a fake bound to a single user doc."""
    from routers import auth as auth_module

    def _bind(doc):
        fake = _FakeUsers(doc)
        monkeypatch.setattr(auth_module.db, "users", fake)
        return fake

    return _bind


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_weak_password_sets_flag(patched_db):
    from routers.auth import _flag_password_if_weak
    user = {"id": "u1"}
    fake = patched_db(user)
    _run(_flag_password_if_weak(user, WEAK))
    assert user.get("password_change_required") is True
    assert fake.calls and "$set" in fake.calls[0]


def test_strong_password_no_flag(patched_db):
    from routers.auth import _flag_password_if_weak
    user = {"id": "u2"}
    fake = patched_db(user)
    _run(_flag_password_if_weak(user, STRONG))
    assert "password_change_required" not in user
    assert fake.calls == []


def test_stale_flag_cleared_when_now_compliant(patched_db):
    from routers.auth import _flag_password_if_weak
    user = {"id": "u3", "password_change_required": True}
    fake = patched_db(user)
    _run(_flag_password_if_weak(user, STRONG))
    assert "password_change_required" not in user
    assert fake.calls and "$unset" in fake.calls[0]


def test_already_flagged_weak_is_idempotent(patched_db):
    from routers.auth import _flag_password_if_weak
    user = {"id": "u4", "password_change_required": True}
    fake = patched_db(user)
    _run(_flag_password_if_weak(user, WEAK))
    # Already flagged + still weak -> no redundant write.
    assert fake.calls == []
    assert user["password_change_required"] is True
