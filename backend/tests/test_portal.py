"""Tests for Customer/Vendor Portal — Module H.

Pure unit tests on the security-critical realm + scoping logic — no live DB.
Covers:
- portal token round-trip + realm separation (portal token != internal token)
- party_scoped() forces token party_id, overriding any client-supplied value
- assert_party_match() rejects cross-party access (raises 404, not 403)
- password hash/verify
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017/test")
os.environ.setdefault("DB_NAME", "test_erp")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import HTTPException

from core.portal_auth import (
    create_portal_token, decode_portal_token,
    party_scoped, assert_party_match,
    hash_password, verify_password, _portal_secret,
)


# ══════════════════════════════════════════════════════════════
# Token round-trip + realm separation
# ══════════════════════════════════════════════════════════════

class TestPortalToken:
    def test_round_trip(self):
        tok = create_portal_token("pu1", "CUST-1", "customer", "a@b.com")
        payload = decode_portal_token(tok)
        assert payload["sub"] == "pu1"
        assert payload["party_id"] == "CUST-1"
        assert payload["party_type"] == "customer"
        assert payload["type"] == "portal_access"

    def test_internal_token_rejected_by_portal(self):
        # An internal-style token (type "access") must not validate as portal.
        import jwt
        internal = jwt.encode(
            {"sub": "u1", "type": "access", "role": "admin"},
            _portal_secret(), algorithm="HS256",
        )
        with pytest.raises(HTTPException) as exc:
            decode_portal_token(internal)
        assert exc.value.status_code == 401

    def test_portal_token_not_decodable_by_internal_secret(self):
        # Portal secret is namespaced — a portal token signed with it won't
        # verify against the bare internal secret.
        import jwt
        tok = create_portal_token("pu1", "CUST-1", "customer", "a@b.com")
        internal_secret = os.environ["JWT_SECRET"]
        with pytest.raises(jwt.InvalidTokenError):
            jwt.decode(tok, internal_secret, algorithms=["HS256"])

    def test_tampered_token_rejected(self):
        tok = create_portal_token("pu1", "CUST-1", "customer", "a@b.com")
        with pytest.raises(HTTPException):
            decode_portal_token(tok + "tamper")

    def test_missing_party_id_rejected(self):
        import jwt
        bad = jwt.encode({"sub": "pu1", "type": "portal_access"}, _portal_secret(), algorithm="HS256")
        with pytest.raises(HTTPException) as exc:
            decode_portal_token(bad)
        assert exc.value.status_code == 401


# ══════════════════════════════════════════════════════════════
# party_scoped — the data-access-layer enforcer
# ══════════════════════════════════════════════════════════════

class TestPartyScoped:
    USER = {"party_id": "CUST-1", "party_type": "customer"}

    def test_injects_party_id(self):
        q = party_scoped({}, self.USER, party_field="customer_id")
        assert q["customer_id"] == "CUST-1"

    def test_overrides_client_supplied_party(self):
        # Even if a malicious client put a foreign id in the query, it's overwritten.
        q = party_scoped({"customer_id": "CUST-999"}, self.USER, party_field="customer_id")
        assert q["customer_id"] == "CUST-1"

    def test_preserves_other_filters(self):
        q = party_scoped({"status": "UNPAID"}, self.USER, party_field="customer_id")
        assert q["status"] == "UNPAID"
        assert q["customer_id"] == "CUST-1"

    def test_vendor_field(self):
        vendor = {"party_id": "VEND-7", "party_type": "vendor"}
        q = party_scoped({}, vendor, party_field="vendor_id")
        assert q["vendor_id"] == "VEND-7"

    def test_does_not_mutate_input(self):
        original = {"status": "PAID"}
        party_scoped(original, self.USER, party_field="customer_id")
        assert "customer_id" not in original  # original untouched


# ══════════════════════════════════════════════════════════════
# assert_party_match — cross-party guard
# ══════════════════════════════════════════════════════════════

class TestAssertPartyMatch:
    USER = {"party_id": "CUST-1"}

    def test_same_party_ok(self):
        assert_party_match("CUST-1", self.USER)  # no raise

    def test_cross_party_rejected_as_404(self):
        with pytest.raises(HTTPException) as exc:
            assert_party_match("CUST-2", self.USER)
        # 404 (not 403) so we don't leak that the other party's resource exists
        assert exc.value.status_code == 404

    def test_none_resource_rejected(self):
        with pytest.raises(HTTPException):
            assert_party_match(None, self.USER)


# ══════════════════════════════════════════════════════════════
# Passwords
# ══════════════════════════════════════════════════════════════

class TestPasswords:
    def test_hash_verify(self):
        h = hash_password("s3cret!")
        assert verify_password("s3cret!", h)

    def test_wrong_password(self):
        h = hash_password("s3cret!")
        assert not verify_password("nope", h)

    def test_hash_is_salted(self):
        assert hash_password("x") != hash_password("x")
