"""Migration 013 — encrypt stored verification secrets at rest.

One-time: read the existing plaintext gst_api_key from verification_settings,
encrypt it with Fernet, and mark the record as encrypted. No-op when no key is
configured (encryption disabled) or the record is already encrypted.
"""
import logging

from core import crypto

logger = logging.getLogger(__name__)

# Secret fields in verification_settings that should be encrypted at rest.
SECRET_FIELDS = ["gst_api_key", "pan_api_key", "aadhaar_api_key", "gemini_api_key"]


async def run(db):
    if not crypto.is_enabled():
        logger.info("Migration 013 — encryption disabled (no key); skipping")
        return

    doc = await db.verification_settings.find_one({"id": "global"})
    if not doc:
        logger.info("Migration 013 — no verification_settings; nothing to encrypt")
        return

    if doc.get("secrets_encrypted"):
        logger.info("Migration 013 — secrets already encrypted; skipping")
        return

    updates = {}
    for field in SECRET_FIELDS:
        val = doc.get(field)
        # Skip empty values and the seeded mock placeholders.
        if val and not str(val).startswith("mock-"):
            updates[field] = crypto.encrypt_secret(val)

    updates["secrets_encrypted"] = True
    await db.verification_settings.update_one({"id": "global"}, {"$set": updates})
    logger.info("Migration 013 — encrypted %d verification secret field(s)", len(updates) - 1)

    # ── einvoice_settings (IRP credentials) ─────────────────────────────────
    ei = await db.einvoice_settings.find_one({"id": "global"})
    if ei and not ei.get("secrets_encrypted"):
        ei_updates = {}
        pw = ei.get("irp_password")
        if pw:
            ei_updates["irp_password"] = crypto.encrypt_secret(pw)
        ei_updates["secrets_encrypted"] = True
        await db.einvoice_settings.update_one({"id": "global"}, {"$set": ei_updates})
        logger.info("Migration 013 — encrypted IRP credential")
