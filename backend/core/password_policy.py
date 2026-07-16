"""Password strength policy.

Enforced at the point a password is set (user creation, password change, MFA
flows). bcrypt happily hashes any string, so length/complexity must be checked
*before* hashing — this module is the single place that rule lives.

Policy (overridable via env for stricter deployments):
- minimum length 12 (PASSWORD_MIN_LENGTH)
- at least one lowercase, one uppercase, one digit, one symbol
- rejects a small set of obviously-weak passwords

Returns a list of human-readable failures so the API can surface all of them at
once rather than one-at-a-time.
"""
import os
import re

# bcrypt only hashes the first 72 *bytes*; anything longer is silently truncated,
# which would let a long password be weaker than it looks. Cap and reject instead.
BCRYPT_MAX_BYTES = 72

_COMMON = {
    "password", "password1", "passw0rd", "12345678", "123456789", "qwerty123",
    "admin123", "letmein123", "welcome123", "changeme123", "gravity123",
}


def _min_length() -> int:
    try:
        return max(12, int(os.environ.get("PASSWORD_MIN_LENGTH", 12)))
    except (TypeError, ValueError):
        return 12


def password_errors(password: str) -> list[str]:
    """Return a list of policy violations; empty list means the password passes."""
    errors: list[str] = []
    if password is None:
        return ["Password is required."]
    min_len = _min_length()
    if len(password) < min_len:
        errors.append(f"Password must be at least {min_len} characters.")
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        errors.append(f"Password must be at most {BCRYPT_MAX_BYTES} bytes.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain a lowercase letter.")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain an uppercase letter.")
    if not re.search(r"\d", password):
        errors.append("Password must contain a digit.")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("Password must contain a symbol.")
    if password.lower() in _COMMON:
        errors.append("Password is too common; choose something less guessable.")
    return errors


def validate_password(password: str) -> str:
    """Validate `password`, returning it unchanged if it passes.

    Raises ValueError (joined messages) on failure so it can be used directly as
    a Pydantic field validator.
    """
    errors = password_errors(password)
    if errors:
        raise ValueError(" ".join(errors))
    return password


PASSWORD_HISTORY_SIZE = 5


def is_password_reused(new_plaintext: str, history_hashes: list[str] | None, current_hash: str | None) -> bool:
    """True if `new_plaintext` matches the current password hash or any of the
    last PASSWORD_HISTORY_SIZE historical hashes. bcrypt hashes can't be
    reversed, so reuse detection has to bcrypt-compare against each stored hash
    rather than comparing plaintexts."""
    import bcrypt

    candidate = new_plaintext.encode("utf-8")
    for h in [current_hash, *(history_hashes or [])]:
        if not h:
            continue
        try:
            if bcrypt.checkpw(candidate, h.encode("utf-8")):
                return True
        except Exception:
            continue
    return False
