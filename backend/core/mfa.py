"""TOTP-based multi-factor authentication helpers.

Flow:
1. Enrollment (`/auth/mfa/enroll`) generates a TOTP secret and returns a
   provisioning URI (for a QR code) + the raw secret. MFA is NOT yet active —
   the secret is stored as `mfa_pending_secret` so a half-finished enrollment
   can't lock anyone out.
2. The user scans the QR in an authenticator app and submits a 6-digit code to
   `/auth/mfa/verify`. On success the pending secret is promoted to `mfa_secret`,
   `mfa_enabled=True`, and a set of one-time recovery codes is returned (shown
   once).
3. At login, if `mfa_enabled`, the password step returns a short-lived
   `mfa_token` instead of session cookies. `/auth/login/mfa` exchanges that
   token + a TOTP (or recovery) code for real auth cookies.

Secrets and recovery codes: the TOTP secret is the shared key, stored as-is
(it must be usable to verify codes; encrypting it only moves the problem since
the app needs the plaintext at verify time). Recovery codes are stored *hashed*
(bcrypt) — they're effectively passwords, so we never keep them in the clear.
"""
import os
import secrets
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt
import pyotp

from .auth_utils import JWT_ALGORITHM, jwt_secret

# The short-lived token issued between the password step and the TOTP step.
MFA_CHALLENGE_EXPIRE_MIN = 5
ISSUER_NAME = os.environ.get("MFA_ISSUER", "Ormodex ERP")
RECOVERY_CODE_COUNT = 10


def generate_secret() -> str:
    """A fresh base32 TOTP secret."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    """otpauth:// URI an authenticator app turns into a QR code."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER_NAME)


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP. `valid_window=1` tolerates one 30s step of clock
    drift in either direction (standard, keeps slightly-out-of-sync phones working)."""
    if not secret or not code:
        return False
    try:
        return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
    except Exception:
        return False


def generate_recovery_codes(n: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Human-friendly one-time codes (e.g. 'a1b2c3d4-e5f6g7h8')."""
    codes = []
    for _ in range(n):
        raw = secrets.token_hex(8)  # 16 hex chars
        codes.append(f"{raw[:8]}-{raw[8:]}")
    return codes


def hash_recovery_codes(codes: list[str]) -> list[str]:
    """bcrypt-hash recovery codes for storage. Normalised (lowercase, no dashes)
    so verification is forgiving of how the user retypes them."""
    return [
        bcrypt.hashpw(_normalise_code(c).encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        for c in codes
    ]


def _normalise_code(code: str) -> str:
    return code.strip().lower().replace("-", "").replace(" ", "")


def consume_recovery_code(code: str, hashed_codes: list[str]) -> int | None:
    """Return the index of the matching recovery-code hash, or None. Caller is
    responsible for removing that index so the code can't be reused."""
    if not code or not hashed_codes:
        return None
    candidate = _normalise_code(code).encode("utf-8")
    for i, h in enumerate(hashed_codes):
        try:
            if bcrypt.checkpw(candidate, h.encode("utf-8")):
                return i
        except Exception:
            continue
    return None


def create_mfa_challenge_token(user_id: str) -> str:
    """Short-lived token proving the password step passed; only valid for the
    TOTP exchange (`type=mfa_challenge`), never as an access token."""
    payload = {
        "sub": user_id,
        "type": "mfa_challenge",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=MFA_CHALLENGE_EXPIRE_MIN),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_mfa_challenge_token(token: str) -> str:
    """Return the user_id from a valid MFA challenge token, or raise jwt errors."""
    payload = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
    if payload.get("type") != "mfa_challenge":
        raise jwt.InvalidTokenError("Not an MFA challenge token")
    sub = payload.get("sub")
    if not sub:
        raise jwt.InvalidTokenError("Missing subject")
    return sub
