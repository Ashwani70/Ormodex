"""Multi-factor authentication (TOTP) enrollment and management.

Login-time MFA verification lives in routers/auth.py (it's part of the login
flow); this router owns enroll / verify / disable / status for the signed-in
user. See core/mfa.py for the crypto helpers and the overall flow.
"""
from fastapi import APIRouter, Depends, HTTPException

from core.auth_utils import get_current_user, verify_password
from core.db import db
from core.mfa import (
    generate_recovery_codes,
    generate_secret,
    hash_recovery_codes,
    provisioning_uri,
    verify_totp,
)
from core.models import MfaDisableIn, MfaVerifyIn
from core.utils import log_audit

router = APIRouter(prefix="/auth/mfa", tags=["mfa"])


@router.get("/status")
async def mfa_status(user: dict = Depends(get_current_user)):
    return {
        "enabled": bool(user.get("mfa_enabled")),
        "pending": bool(user.get("mfa_pending_secret")),
    }


@router.post("/enroll")
async def mfa_enroll(user: dict = Depends(get_current_user)):
    """Begin enrollment: issue a fresh secret + provisioning URI for the QR code.

    The secret is stored as `mfa_pending_secret` and MFA stays OFF until the user
    proves possession via /verify. Re-enrolling overwrites any pending secret.
    """
    if user.get("mfa_enabled"):
        raise HTTPException(status_code=400, detail="MFA is already enabled")
    secret = generate_secret()
    await db.users.update_one(
        {"id": user["id"]}, {"$set": {"mfa_pending_secret": secret}}
    )
    return {
        "secret": secret,
        "otpauth_uri": provisioning_uri(secret, user["email"]),
    }


@router.post("/verify")
async def mfa_verify(payload: MfaVerifyIn, user: dict = Depends(get_current_user)):
    """Confirm enrollment with a TOTP code; activates MFA and returns one-time
    recovery codes (shown once — they are stored hashed and cannot be re-shown)."""
    secret = user.get("mfa_pending_secret")
    if not secret:
        raise HTTPException(status_code=400, detail="No pending MFA enrollment; call /enroll first")
    if not verify_totp(secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid code")
    recovery_codes = generate_recovery_codes()
    await db.users.update_one(
        {"id": user["id"]},
        {
            "$set": {
                "mfa_secret": secret,
                "mfa_enabled": True,
                "mfa_recovery_hashes": hash_recovery_codes(recovery_codes),
            },
            "$unset": {"mfa_pending_secret": ""},
        },
    )
    await log_audit("UPDATE", "users", user["id"], user,
                    new_values={"mfa_enabled": True})
    return {"enabled": True, "recovery_codes": recovery_codes}


@router.post("/recovery-codes/regenerate")
async def regenerate_recovery_codes(payload: MfaDisableIn, user: dict = Depends(get_current_user)):
    """Issue a fresh set of recovery codes (invalidating the old set). Requires
    the account password, since recovery codes bypass the second factor."""
    if not user.get("mfa_enabled"):
        raise HTTPException(status_code=400, detail="MFA is not enabled")
    full = await db.users.find_one({"id": user["id"]})
    if not full or not verify_password(payload.password, full.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid password")
    recovery_codes = generate_recovery_codes()
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"mfa_recovery_hashes": hash_recovery_codes(recovery_codes)}},
    )
    return {"recovery_codes": recovery_codes}


@router.post("/disable")
async def mfa_disable(payload: MfaDisableIn, user: dict = Depends(get_current_user)):
    """Turn MFA off. Requires the account password to re-authenticate."""
    full = await db.users.find_one({"id": user["id"]})
    if not full or not verify_password(payload.password, full.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid password")
    if not full.get("mfa_enabled") and not full.get("mfa_pending_secret"):
        raise HTTPException(status_code=400, detail="MFA is not enabled")
    await db.users.update_one(
        {"id": user["id"]},
        {"$unset": {
            "mfa_secret": "",
            "mfa_pending_secret": "",
            "mfa_recovery_hashes": "",
        }, "$set": {"mfa_enabled": False}},
    )
    await log_audit("UPDATE", "users", user["id"], user,
                    new_values={"mfa_enabled": False})
    return {"enabled": False}
