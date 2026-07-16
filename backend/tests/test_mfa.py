"""MFA (TOTP) helper tests.

Covers the crypto helpers in core/mfa.py directly (no live server / DB): secret
generation, TOTP verification with clock-drift window, recovery-code hashing +
one-time consumption, and the short-lived challenge token round-trip.
"""
import os

import jwt
import pyotp
import pytest

# JWT_SECRET must exist before importing modules that read it at call time.
os.environ.setdefault("JWT_SECRET", "test-secret-for-mfa-tests")

from core.mfa import (
    consume_recovery_code,
    create_mfa_challenge_token,
    decode_mfa_challenge_token,
    generate_recovery_codes,
    generate_secret,
    hash_recovery_codes,
    provisioning_uri,
    verify_totp,
)


def test_secret_and_uri():
    secret = generate_secret()
    assert len(secret) >= 16
    uri = provisioning_uri(secret, "user@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "user%40example.com" in uri or "user@example.com" in uri


def test_verify_totp_accepts_current_code():
    secret = generate_secret()
    code = pyotp.TOTP(secret).now()
    assert verify_totp(secret, code) is True


def test_verify_totp_rejects_wrong_code():
    secret = generate_secret()
    assert verify_totp(secret, "000000") is False
    assert verify_totp(secret, "") is False
    assert verify_totp("", "123456") is False


def test_recovery_codes_generate_and_hash():
    codes = generate_recovery_codes(5)
    assert len(codes) == 5
    assert len(set(codes)) == 5  # all unique
    hashes = hash_recovery_codes(codes)
    assert len(hashes) == 5
    assert all(h.startswith("$2") for h in hashes)  # bcrypt format


def test_consume_recovery_code_matches_and_normalises():
    codes = generate_recovery_codes(3)
    hashes = hash_recovery_codes(codes)
    # Matches even if the user retypes with different case / spacing.
    messy = codes[1].upper().replace("-", " - ")
    idx = consume_recovery_code(messy, hashes)
    assert idx == 1


def test_consume_recovery_code_rejects_unknown():
    hashes = hash_recovery_codes(generate_recovery_codes(3))
    assert consume_recovery_code("not-a-real-code", hashes) is None
    assert consume_recovery_code("", hashes) is None


def test_challenge_token_roundtrip():
    token = create_mfa_challenge_token("user-123")
    assert decode_mfa_challenge_token(token) == "user-123"


def test_challenge_token_rejects_wrong_type():
    # An access-shaped token must not be accepted as an MFA challenge.
    from core.auth_utils import JWT_ALGORITHM, jwt_secret
    bad = jwt.encode({"sub": "x", "type": "access"}, jwt_secret(), algorithm=JWT_ALGORITHM)
    with pytest.raises(jwt.InvalidTokenError):
        decode_mfa_challenge_token(bad)
