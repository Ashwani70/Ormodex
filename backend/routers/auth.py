from fastapi import APIRouter, Depends, HTTPException, Request, Response

from core.auth_utils import (
    JWT_ALGORITHM,
    CAPTCHA_THRESHOLD,
    create_access_token,
    create_refresh_token,
    get_current_user,
    is_locked_out,
    issue_csrf_cookie,
    jwt_secret,
    record_failed_login,
    record_successful_login,
    revoke_device,
    revoke_user_devices,
    revoke_user_refresh_tokens,
    rotate_refresh_token,
    set_auth_cookies,
    clear_auth_cookies,
    touch_device_activity,
    verify_password,
)
from core.captcha import generate_challenge, verify_challenge
from core.db import db
from core.mfa import (
    consume_recovery_code,
    create_mfa_challenge_token,
    decode_mfa_challenge_token,
    verify_totp,
)
from core.models import (
    ChangePasswordIn, ForgotPasswordIn, LoginIn, MfaLoginIn, ResetPasswordIn,
    ResetPasswordOtpIn,
)
from core.password_policy import password_errors, is_password_reused, PASSWORD_HISTORY_SIZE
from core.rate_limit import client_ip, rate_limit
from core.auth_utils import hash_password
from core.user_agent import parse_user_agent
from core.utils import log_audit, new_id, now_iso
from core.email import (
    is_configured as email_configured,
    render_otp_email_html,
    render_password_reset_html,
    render_security_notification_html,
    send_email_sync,
)

import asyncio
import hashlib
import os
import jwt

router = APIRouter(prefix="/auth", tags=["auth"])

RESET_TOKEN_EXPIRE_MINUTES = 30
OTP_TOKEN_EXPIRE_MINUTES = 10
OTP_MAX_ATTEMPTS = 5


async def _flag_password_if_weak(user: dict, plaintext: str) -> None:
    """If the just-verified password no longer meets policy, mark the account so
    the app forces a change. Login still succeeds (the user needs a session to
    reach the change-password endpoint); the frontend gates on the flag.

    Persisted (not just computed) so it survives even if the policy is later
    relaxed, and so an admin can see which accounts are non-compliant.

    Only ever auto-*sets* the flag for a policy violation, and only auto-
    *clears* it when it was set for that same reason (force_change_reason is
    unset/"policy"). An admin-forced reset (force_change_reason="admin_reset")
    must survive a strong-password login — only change-password/reset-password
    should be able to clear that, otherwise the very next login with the
    admin-issued temp password would silently defeat the forced-change.
    """
    weak = bool(password_errors(plaintext))
    reason = user.get("force_change_reason")
    if weak and not user.get("password_change_required"):
        await db.users.update_one(
            {"id": user["id"]}, {"$set": {"password_change_required": True, "force_change_reason": "policy"}}
        )
        user["password_change_required"] = True
        user["force_change_reason"] = "policy"
    elif not weak and user.get("password_change_required") and reason in (None, "policy"):
        # Password was changed elsewhere to a compliant one; clear a stale flag.
        await db.users.update_one(
            {"id": user["id"]}, {"$unset": {"password_change_required": "", "force_change_reason": ""}}
        )
        user.pop("password_change_required", None)
        user.pop("force_change_reason", None)


def _device_meta(request: Request) -> dict:
    ua = request.headers.get("user-agent", "")
    parsed = parse_user_agent(ua)
    return {**parsed, "user_agent": ua, "ip": client_ip(request)}


async def _record_login_history(
    *, user_id: str | None, identifier: str, request: Request,
    success: bool, failure_reason: str | None = None,
) -> None:
    meta = _device_meta(request)
    now = now_iso()
    await db.login_history.insert_one({
        "id": new_id(),
        "user_id": user_id,
        "email_attempted": identifier,
        "ip": meta["ip"],
        "user_agent": meta["user_agent"],
        "device_name": meta["device_name"],
        "browser": meta["browser"],
        "os": meta["os"],
        "success": success,
        "failure_reason": failure_reason,
        "logged_in_at": now if success else None,
        "created_at": now,
    })


async def _send_security_email(user: dict, event_type: str, details: dict | None = None) -> None:
    """Best-effort security notification — never let email failures break auth."""
    if not user.get("email") or not email_configured():
        return
    try:
        html = render_security_notification_html(event_type, details)
        subjects = {
            "password_changed": "Ormodex ERP · Your password was changed",
            "new_device_login": "Ormodex ERP · New sign-in to your account",
            "mfa_enabled": "Ormodex ERP · Two-factor authentication enabled",
            "mfa_disabled": "Ormodex ERP · Two-factor authentication disabled",
            "multiple_failed_logins": "Ormodex ERP · Multiple failed sign-in attempts",
        }
        send_email_sync(to=user["email"], subject=subjects.get(event_type, "Ormodex ERP · Security notice"), html=html)
    except Exception:
        pass


async def _is_new_device(user_id: str, ip: str) -> bool:
    """Heuristic: no successful login_history row for this user+IP in the
    lookback window means this is (as far as we can tell) a new device/location."""
    if not ip or ip == "unknown":
        return False
    existing = await db.login_history.find_one({"user_id": user_id, "ip": ip, "success": True})
    return existing is None


async def _issue_session(user: dict, response: Response, request: Request | None = None, remember_me: bool = True) -> dict:
    """Mint access+refresh tokens, set cookies, and return the sanitised user."""
    access = create_access_token(user["id"], user["email"], user["role"])
    device_meta = _device_meta(request) if request else None
    refresh = await create_refresh_token(user["id"], device_meta=device_meta)
    set_auth_cookies(response, access, refresh, remember_me=remember_me)
    user.pop("_id", None)
    user.pop("password_hash", None)
    user.pop("mfa_secret", None)
    user.pop("mfa_pending_secret", None)
    user.pop("mfa_recovery_hashes", None)
    user.pop("password_history", None)
    return {"user": user, "access_token": access}


async def _find_user_by_identifier(identifier: str) -> dict | None:
    """Look up a user by email first, then by username, then by phone."""
    user = await db.users.find_one({"email": identifier})
    if not user:
        user = await db.users.find_one({"username": identifier})
    if not user:
        user = await db.users.find_one({"phone": identifier})
    return user


@router.post("/login")
async def login(payload: LoginIn, request: Request, response: Response):
    identifier = payload.email.lower().strip()
    # Throttle brute-force / credential-stuffing: per-IP (broad) and per-account
    # (targeted). Checked before any DB/password work so it can't be bypassed.
    ip = client_ip(request)
    rate_limit(f"login:ip:{ip}", limit=10, window_seconds=300, request=request)
    rate_limit(f"login:acct:{identifier}", limit=5, window_seconds=300, request=request)

    company_code_required = os.environ.get("LOGIN_COMPANY_CODE", "").strip()
    if company_code_required and (payload.company_code or "").strip() != company_code_required:
        await _record_login_history(user_id=None, identifier=identifier, request=request, success=False, failure_reason="bad_company_code")
        raise HTTPException(status_code=401, detail="Invalid email/username or password")

    user = await _find_user_by_identifier(identifier)

    # CAPTCHA required once the account has racked up enough recent failures.
    if user and int(user.get("failed_login_count") or 0) >= CAPTCHA_THRESHOLD:
        if not verify_challenge(payload.captcha_token or "", payload.captcha_answer or ""):
            raise HTTPException(status_code=400, detail="CAPTCHA verification required or incorrect. Please try again.")

    if user and is_locked_out(user):
        await _record_login_history(user_id=user["id"], identifier=identifier, request=request, success=False, failure_reason="locked")
        raise HTTPException(status_code=423, detail="Account is locked due to too many failed attempts. Try again later.")

    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        if user:
            count = await record_failed_login(user, ip)
            await log_audit("LOGIN_FAILED", "users", user["id"], user, ip=ip, user_agent=request.headers.get("user-agent"))
            # Notify exactly once, at the threshold crossing — not on every
            # failure after it, which would spam the account owner.
            if count == CAPTCHA_THRESHOLD:
                await _send_security_email(user, "multiple_failed_logins", {"Failed attempts": str(count)})
        await _record_login_history(user_id=user["id"] if user else None, identifier=identifier, request=request, success=False, failure_reason="bad_password")
        raise HTTPException(status_code=401, detail="Invalid email/username or password")

    # Force a reset if this (correct) password no longer meets the policy.
    await _flag_password_if_weak(user, payload.password)

    # If the account has MFA enabled, the password is only the first factor: hand
    # back a short-lived challenge token instead of a session and require the
    # TOTP/recovery step at /login/mfa. No auth cookies are set here.
    if user.get("mfa_enabled"):
        return {
            "mfa_required": True,
            "mfa_token": create_mfa_challenge_token(user["id"]),
        }

    # Must read "is this IP new for this user" BEFORE the history row below is
    # written, or every login would look new. Everything after that is an
    # independent write (different tables/rows) — run them concurrently
    # instead of serially, since each round-trip to the DB costs real wall-
    # clock time under cross-region latency.
    is_new_device = await _is_new_device(user["id"], ip)
    session_task = _issue_session(user, response, request=request, remember_me=payload.remember_me)
    session_result, *_ = await asyncio.gather(
        session_task,
        record_successful_login(user, ip),
        _record_login_history(user_id=user["id"], identifier=identifier, request=request, success=True),
        log_audit("LOGIN_SUCCESS", "users", user["id"], user, ip=ip, user_agent=request.headers.get("user-agent")),
    )
    if is_new_device:
        await _send_security_email(user, "new_device_login", {"IP address": ip, "Time": now_iso()})
    return session_result


@router.post("/login/mfa")
async def login_mfa(payload: MfaLoginIn, request: Request, response: Response):
    """Second login factor: exchange the challenge token + a TOTP (or recovery)
    code for a real session."""
    ip = client_ip(request)
    rate_limit(f"mfa:ip:{ip}", limit=10, window_seconds=300, request=request)
    try:
        user_id = decode_mfa_challenge_token(payload.mfa_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="MFA session expired; log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid MFA token")
    rate_limit(f"mfa:acct:{user_id}", limit=5, window_seconds=300, request=request)
    user = await db.users.find_one({"id": user_id})
    if not user or not user.get("mfa_enabled"):
        raise HTTPException(status_code=401, detail="Invalid MFA token")

    code = (payload.code or "").strip()
    matched = verify_totp(user.get("mfa_secret", ""), code)
    idx = None
    if not matched:
        # Fall back to a one-time recovery code; consume it so it can't be reused.
        idx = consume_recovery_code(code, user.get("mfa_recovery_hashes", []))

    if not matched and idx is None:
        raise HTTPException(status_code=401, detail="Invalid code")

    if idx is not None:
        remaining = list(user.get("mfa_recovery_hashes", []))
        remaining.pop(idx)
        await db.users.update_one(
            {"id": user_id}, {"$set": {"mfa_recovery_hashes": remaining}}
        )

    is_new_device = await _is_new_device(user["id"], ip)
    await record_successful_login(user, ip)
    await _record_login_history(user_id=user["id"], identifier=user.get("email", ""), request=request, success=True)
    await log_audit("LOGIN_SUCCESS", "users", user["id"], user, ip=ip, user_agent=request.headers.get("user-agent"))
    if is_new_device:
        await _send_security_email(user, "new_device_login", {"IP address": ip, "Time": now_iso()})
    return await _issue_session(user, response, request=request)


@router.get("/captcha")
async def captcha(request: Request):
    rate_limit(f"captcha:ip:{client_ip(request)}", limit=20, window_seconds=300, request=request)
    return generate_challenge()


@router.post("/logout")
async def logout(request: Request, response: Response, user: dict = Depends(get_current_user)):
    # Revoke all refresh tokens so a stolen/old refresh token can't mint access
    # tokens after the user has logged out.
    await revoke_user_refresh_tokens(user["id"])
    rt = request.cookies.get("refresh_token")
    if rt:
        try:
            payload = jwt.decode(rt, jwt_secret(), algorithms=[JWT_ALGORITHM])
            jti = payload.get("jti")
            if jti:
                await revoke_device(user["id"], jti)
        except jwt.InvalidTokenError:
            pass
    await db.login_history.update_one(
        {"user_id": user["id"], "logged_out_at": None},
        {"$set": {"logged_out_at": now_iso()}},
    )
    await log_audit("LOGOUT", "users", user["id"], user)
    clear_auth_cookies(response)
    return {"ok": True}


@router.post("/logout-all")
async def logout_all(response: Response, user: dict = Depends(get_current_user)):
    """Revoke every refresh token and device session for this user — "log out
    everywhere" — not just the caller's own session."""
    await revoke_user_refresh_tokens(user["id"])
    await revoke_user_devices(user["id"])
    await log_audit("LOGOUT_ALL", "users", user["id"], user)
    clear_auth_cookies(response)
    return {"ok": True}


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordIn,
    response: Response,
    user: dict = Depends(get_current_user),
):
    """Change the signed-in user's password.

    Used both for routine changes and to satisfy a forced reset
    (`password_change_required`). Verifies the current password, enforces the
    policy on the new one (via the model validator), blocks reuse of the last
    PASSWORD_HISTORY_SIZE passwords, clears the reset flag, and revokes all
    refresh tokens so other sessions must re-authenticate.
    """
    full = await db.users.find_one({"id": user["id"]})
    if not full or not verify_password(payload.current_password, full.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if is_password_reused(payload.new_password, full.get("password_history"), full.get("password_hash")):
        raise HTTPException(status_code=400, detail=f"New password must not match your current or last {PASSWORD_HISTORY_SIZE} passwords")

    history = list(full.get("password_history") or [])
    old_hash = full.get("password_hash")
    if old_hash:
        history.insert(0, old_hash)
    history = history[:PASSWORD_HISTORY_SIZE]

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "password_hash": hash_password(payload.new_password),
            "password_history": history,
            "last_password_change": now_iso(),
        },
         "$unset": {"password_change_required": "", "force_change_reason": ""}},
    )
    # Revoke refresh tokens everywhere, then re-issue a session for this caller so
    # they stay logged in here while other devices are forced to re-authenticate.
    await revoke_user_refresh_tokens(user["id"])
    await revoke_user_devices(user["id"])
    fresh = await db.users.find_one({"id": user["id"]})
    if not fresh:
        raise HTTPException(status_code=404, detail="User not found")
    await log_audit("PASSWORD_CHANGED", "users", user["id"], user)
    await _send_security_email(fresh, "password_changed")
    return await _issue_session(fresh, response)


# ── Forgot / Reset Password ─────────────────────────────────────────────────

def _create_reset_token(user_id: str) -> str:
    """Mint a short-lived JWT for password reset."""
    from datetime import datetime, timezone, timedelta
    payload = {
        "sub": user_id,
        "type": "reset",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


def _create_otp_token(user_id: str, code: str) -> str:
    """Mint a short-lived JWT embedding a hash of the OTP (not the code itself)."""
    from datetime import datetime, timezone, timedelta
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    payload = {
        "sub": user_id,
        "type": "reset_otp",
        "code_hash": code_hash,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=OTP_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


def _frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordIn, request: Request):
    """Send a password-reset link or OTP to the user's email.

    Always returns {"ok": true} regardless of whether the account was found,
    to prevent user enumeration.
    """
    ip = client_ip(request)
    rate_limit(f"forgot:ip:{ip}", limit=5, window_seconds=300, request=request)

    identifier = (payload.identifier or payload.email or "").strip()
    identifier_lower = identifier.lower()
    rate_limit(f"forgot:acct:{identifier_lower}", limit=3, window_seconds=300, request=request)

    user = await _find_user_by_identifier(identifier_lower) or await _find_user_by_identifier(identifier)
    if user and user.get("email") and email_configured():
        try:
            if payload.method == "otp":
                import random
                code = f"{random.randint(0, 999999):06d}"
                token = _create_otp_token(user["id"], code)
                # The OTP token itself isn't returned to the caller — it's only
                # useful alongside the emailed code, and /auth/reset-password/otp
                # looks the pending token up server-side via a short-lived cache
                # keyed by identifier so the frontend UX doesn't need to carry it.
                from core import cache
                cache.set(f"otp_reset:{user['id']}", token, ttl=OTP_TOKEN_EXPIRE_MINUTES * 60)
                cache.set(f"otp_attempts:{user['id']}", 0, ttl=OTP_TOKEN_EXPIRE_MINUTES * 60)
                html = render_otp_email_html(code=code, expires_minutes=OTP_TOKEN_EXPIRE_MINUTES)
                send_email_sync(to=user["email"], subject="Ormodex ERP · Password Reset Code", html=html)
            else:
                token = _create_reset_token(user["id"])
                reset_link = f"{_frontend_url()}/reset-password?token={token}"
                html = render_password_reset_html(reset_link=reset_link, expires_minutes=RESET_TOKEN_EXPIRE_MINUTES)
                send_email_sync(to=user["email"], subject="Ormodex ERP · Password Reset", html=html)
        except Exception:
            pass  # Don't leak email delivery errors to the caller

    # Always return success — no user enumeration
    return {"ok": True, "message": "If that account is registered, a reset code/link has been sent."}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordIn, request: Request):
    """Reset the password using a token from the forgot-password email."""
    ip = client_ip(request)
    rate_limit(f"reset:ip:{ip}", limit=10, window_seconds=300, request=request)

    try:
        decoded = jwt.decode(payload.token, jwt_secret(), algorithms=[JWT_ALGORITHM])
        if decoded.get("type") != "reset":
            raise HTTPException(status_code=400, detail="Invalid reset token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Reset link has expired. Please request a new one.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid reset token")

    user_id = decoded.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid reset token")

    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await _apply_password_reset(user, payload.new_password)
    return {"ok": True, "message": "Password has been reset successfully. Please log in with your new password."}


@router.post("/reset-password/otp")
async def reset_password_otp(payload: ResetPasswordOtpIn, request: Request):
    """Reset the password using the 6-digit OTP emailed by /forgot-password
    (method="otp"). Separate endpoint so the existing token-based
    /reset-password (used by ResetPassword.jsx) is untouched."""
    ip = client_ip(request)
    rate_limit(f"reset-otp:ip:{ip}", limit=10, window_seconds=300, request=request)

    identifier = payload.identifier.strip().lower()
    user = await _find_user_by_identifier(identifier) or await _find_user_by_identifier(payload.identifier.strip())
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    from core import cache
    attempts = cache.get_default(f"otp_attempts:{user['id']}", 0)
    if attempts >= OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many attempts. Please request a new code.")
    cache.set(f"otp_attempts:{user['id']}", attempts + 1, ttl=OTP_TOKEN_EXPIRE_MINUTES * 60)

    token = cache.get_default(f"otp_reset:{user['id']}")
    if not token:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    try:
        decoded = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
        if decoded.get("type") != "reset_otp" or decoded.get("sub") != user["id"]:
            raise HTTPException(status_code=400, detail="Invalid or expired code")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Code has expired. Please request a new one.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    code_hash = hashlib.sha256(payload.code.strip().encode("utf-8")).hexdigest()
    if code_hash != decoded.get("code_hash"):
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    cache.invalidate(f"otp_reset:{user['id']}", f"otp_attempts:{user['id']}")
    await _apply_password_reset(user, payload.new_password)
    return {"ok": True, "message": "Password has been reset successfully. Please log in with your new password."}


async def _apply_password_reset(user: dict, new_password: str) -> None:
    if is_password_reused(new_password, user.get("password_history"), user.get("password_hash")):
        raise HTTPException(status_code=400, detail=f"New password must not match your current or last {PASSWORD_HISTORY_SIZE} passwords")

    history = list(user.get("password_history") or [])
    old_hash = user.get("password_hash")
    if old_hash:
        history.insert(0, old_hash)
    history = history[:PASSWORD_HISTORY_SIZE]

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "password_hash": hash_password(new_password),
            "password_history": history,
            "last_password_change": now_iso(),
        },
         "$unset": {"password_change_required": "", "force_change_reason": ""}},
    )
    # Revoke all sessions so the user must log in fresh with the new password.
    await revoke_user_refresh_tokens(user["id"])
    await revoke_user_devices(user["id"])
    await log_audit("PASSWORD_RESET", "users", user["id"], user)
    await _send_security_email(user, "password_changed")


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@router.get("/csrf")
async def issue_csrf(response: Response, user: dict = Depends(get_current_user)):
    """Re-issue the CSRF double-submit cookie for the current session.

    GET is a CSRF-safe method (see server.py's csrf_check), so this can't be
    used to forge a state change — it only lets an already-authenticated
    session recover from a stale/rotated csrf_token cookie (e.g. after a
    token refresh reissued it, see set_auth_cookies) without forcing a full
    re-login. The frontend calls this once and retries on a 403 whose detail
    matches CSRF_MISMATCH_DETAIL (see api.js).
    """
    token = issue_csrf_cookie(response)
    return {"csrf_token": token}


@router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    rt = request.cookies.get("refresh_token")
    if not rt:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(rt, jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token claims")
    user = await db.users.find_one({"id": sub}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    # Rotate the refresh token: the old one is invalidated and a new one issued.
    # Reuse of a rotated token is detected inside rotate_refresh_token (401).
    new_refresh = await rotate_refresh_token(payload)
    await touch_device_activity(payload.get("jti"))
    access = create_access_token(user["id"], user["email"], user["role"])
    set_auth_cookies(response, access, new_refresh)
    return {"ok": True, "access_token": access}


# ── Devices / Sessions ───────────────────────────────────────────────────────

@router.get("/devices")
async def list_devices(user: dict = Depends(get_current_user)):
    devices = await db.user_devices.find(
        {"user_id": user["id"], "revoked": False}, {"_id": 0}
    ).sort("last_active_at", -1).to_list(100)
    return devices


@router.delete("/devices/{device_id}")
async def delete_device(device_id: str, user: dict = Depends(get_current_user)):
    ok = await revoke_device(user["id"], device_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Device not found")
    await log_audit("DEVICE_REVOKED", "user_devices", device_id, user)
    return {"ok": True}


@router.get("/login-history")
async def my_login_history(user: dict = Depends(get_current_user), limit: int = 50):
    items = await db.login_history.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(min(limit, 200)).to_list(200)
    return items
