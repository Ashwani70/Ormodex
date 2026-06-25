"""
At-rest encryption for stored secrets (e.g. GST/IPR API password).

Uses Fernet (symmetric AES) from the `cryptography` package. The key lives in
the SETTINGS_ENCRYPTION_KEY environment variable and MUST NOT be committed to
Git or stored in MongoDB.

Generate a key once with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

If the key is not configured, encryption is disabled and values pass through
unchanged. This keeps the app running before the key is provisioned; secrets
simply remain plaintext until a key is set and the migration runs. Never log
decrypted secrets.
"""
import os
import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_key = os.environ.get("SETTINGS_ENCRYPTION_KEY")
_cipher = None
if _key:
    try:
        _cipher = Fernet(_key.encode())
    except Exception as e:  # malformed key
        logger.error("SETTINGS_ENCRYPTION_KEY is set but invalid; encryption disabled: %s", e)
        _cipher = None
else:
    logger.warning(
        "SETTINGS_ENCRYPTION_KEY not set — secret encryption is DISABLED. "
        "Stored secrets will remain plaintext until a key is provisioned."
    )


def is_enabled() -> bool:
    """True when a valid encryption key is configured."""
    return _cipher is not None


def encrypt_secret(value: str) -> str:
    """Encrypt a plaintext secret. Returns plaintext unchanged if disabled."""
    if not value or _cipher is None:
        return value
    return _cipher.encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    """
    Decrypt a stored secret. If encryption is disabled, or the value is not a
    valid Fernet token (e.g. legacy plaintext), the value is returned as-is.
    """
    if not value or _cipher is None:
        return value
    try:
        return _cipher.decrypt(value.encode()).decode()
    except InvalidToken:
        # Value was never encrypted (legacy plaintext) — return unchanged.
        return value
