import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Literal

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select, update

from . import cache
from .db import get_session
from .schema import User, RefreshToken

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MIN = 60 * 24
REFRESH_TOKEN_DAYS = 7

MAX_FAILED_LOGINS = 10
LOCKOUT_MINUTES = 30
CAPTCHA_THRESHOLD = 5


def jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode("utf-8"), h.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MIN),
        "type": "access",
    }
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


async def _insert_refresh_token_row(jti: str, user_id: str, expires_iso: str) -> None:
    from .utils import new_id, now_iso
    async with get_session() as session:
        session.add(RefreshToken(
            id=new_id(),
            jti=jti,
            user_id=user_id,
            active=True,
            expires_at=expires_iso,
            created_at=now_iso(),
        ))


async def _insert_user_device_row(jti: str, user_id: str, device_meta: dict) -> None:
    from .schema import UserDevice
    from .utils import new_id, now_iso
    now = now_iso()
    async with get_session() as session:
        session.add(UserDevice(
            id=new_id(),
            user_id=user_id,
            refresh_jti=jti,
            device_name=device_meta.get("device_name"),
            browser=device_meta.get("browser"),
            os=device_meta.get("os"),
            ip=device_meta.get("ip"),
            user_agent=device_meta.get("user_agent"),
            login_at=now,
            last_active_at=now,
            revoked=False,
            created_at=now,
        ))


async def create_refresh_token(user_id: str, device_meta: dict | None = None) -> str:
    jti = uuid.uuid4().hex
    expires_iso = (datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS)).isoformat()
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
        "type": "refresh",
        "jti": jti,
    }
    # These write to different tables/rows and don't depend on each other —
    # run concurrently instead of as two serial round-trips.
    writes = [_insert_refresh_token_row(jti, user_id, expires_iso)]
    if device_meta:
        writes.append(_insert_user_device_row(jti, user_id, device_meta))
    await asyncio.gather(*writes)
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


async def touch_device_activity(jti: str | None) -> None:
    """Best-effort bump of a device row's last_active_at on refresh. Cheap
    since /auth/refresh already looks the token up by jti."""
    if not jti:
        return
    from .utils import now_iso
    from .schema import UserDevice
    try:
        async with get_session() as session:
            await session.execute(
                update(UserDevice).where(UserDevice.refresh_jti == jti)
                .values(last_active_at=now_iso())
            )
    except Exception:
        pass  # device tracking is best-effort; never block a token refresh on it


async def revoke_device(user_id: str, device_id: str) -> bool:
    """Revoke one device/session: mark the user_devices row revoked and
    deactivate its refresh token so the device can no longer mint new access
    tokens. Returns False if the device isn't found for this user."""
    from .utils import now_iso
    from .schema import UserDevice
    async with get_session() as session:
        result = await session.execute(
            select(UserDevice).where(UserDevice.id == device_id, UserDevice.user_id == user_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            return False
        device.revoked = True
        device.revoked_at = now_iso()
        jti = device.refresh_jti
    if jti:
        async with get_session() as session:
            await session.execute(
                update(RefreshToken).where(RefreshToken.jti == jti).values(active=False)
            )
    return True


def is_locked_out(user: dict) -> bool:
    """True if the account is currently locked — either an admin-initiated
    hard lock (is_locked) or an auto-lockout window still in effect
    (locked_until in the future)."""
    if user.get("is_locked"):
        return True
    locked_until = user.get("locked_until")
    if not locked_until:
        return False
    try:
        until = datetime.fromisoformat(locked_until)
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return until > datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return False


async def record_failed_login(user: dict, ip: str | None = None) -> int:
    """Increment failed_login_count; auto-lock for LOCKOUT_MINUTES once
    MAX_FAILED_LOGINS is reached. Returns the new failed count."""
    from .db import db
    count = int(user.get("failed_login_count") or 0) + 1
    updates: dict = {"failed_login_count": count}
    if count >= MAX_FAILED_LOGINS:
        locked_until = (datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
        updates["locked_until"] = locked_until
    await db.users.update_one({"id": user["id"]}, {"$set": updates})
    invalidate_user_cache(user["id"])
    return count


async def record_successful_login(user: dict, ip: str | None = None) -> None:
    """Reset failed-login tracking and stamp last-login metadata on success."""
    from .db import db
    from .utils import now_iso
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "failed_login_count": 0,
            "locked_until": None,
            "last_login_at": now_iso(),
            "last_login_ip": ip,
        }},
    )
    invalidate_user_cache(user["id"])


async def rotate_refresh_token(payload: dict) -> str:
    jti = payload.get("jti")
    sub = payload.get("sub")
    if not jti or not sub:
        raise HTTPException(status_code=401, detail="Invalid token claims")
    async with get_session() as session:
        result = await session.execute(select(RefreshToken).where(RefreshToken.jti == jti))
        rt = result.scalar_one_or_none()
        if not rt or not rt.active:
            raise HTTPException(status_code=401, detail="Refresh token revoked or not found")
        rt.active = False
    return await create_refresh_token(sub)


async def revoke_user_refresh_tokens(user_id: str):
    async with get_session() as session:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.active == True)
            .values(active=False)
        )


async def revoke_user_devices(user_id: str) -> None:
    """Mark every user_devices row for this user revoked. Paired with
    revoke_user_refresh_tokens for a full "log out everywhere"."""
    from .utils import now_iso
    from .schema import UserDevice
    async with get_session() as session:
        await session.execute(
            update(UserDevice)
            .where(UserDevice.user_id == user_id, UserDevice.revoked == False)
            .values(revoked=True, revoked_at=now_iso())
        )


def issue_csrf_cookie(response: Response, remember_me: bool = True) -> str:
    """Set (or re-set) the non-httponly CSRF double-submit cookie and return
    its value. The frontend JS reads this cookie and echoes it back as
    X-CSRF-Token on state-changing requests (see server.py's csrf_check
    middleware) — it only proves "this JS runs on our origin", not
    authentication, so exposing it to JS is the whole point.

    Factored out of set_auth_cookies so routers/auth.py's GET /auth/csrf can
    reissue just this cookie (a CSRF-safe GET) when a client's copy has gone
    stale relative to the server's — e.g. after /auth/refresh rotates it —
    without forcing a full re-login.
    """
    is_prod = os.environ.get("ENV", "development").lower() == "production"
    secure = is_prod
    samesite: Literal["lax", "strict", "none"] = "none" if is_prod else "lax"
    max_age = ACCESS_TOKEN_MIN * 60 if remember_me else None
    token = uuid.uuid4().hex
    response.set_cookie("csrf_token", token, httponly=False, secure=secure, samesite=samesite, max_age=max_age, path="/")
    return token


def set_auth_cookies(response: Response, access: str, refresh: str, remember_me: bool = True):
    """Set the access/refresh cookies, plus a non-httponly CSRF double-submit
    cookie the frontend echoes back as X-CSRF-Token on state-changing requests
    (see server.py's csrf_check middleware). When remember_me is False, the
    cookies are set without max_age (session cookies) so the browser drops
    them on close — the JWTs themselves keep their normal expiry either way,
    so a tab left open still works for the full token lifetime; only a fully
    closed and reopened browser forces a fresh login."""
    is_prod = os.environ.get("ENV", "development").lower() == "production"
    secure = is_prod
    samesite: Literal["lax", "strict", "none"] = "none" if is_prod else "lax"
    access_max_age = ACCESS_TOKEN_MIN * 60 if remember_me else None
    refresh_max_age = REFRESH_TOKEN_DAYS * 86400 if remember_me else None
    response.set_cookie("access_token", access, httponly=True, secure=secure, samesite=samesite, max_age=access_max_age, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=secure, samesite=samesite, max_age=refresh_max_age, path="/")
    issue_csrf_cookie(response, remember_me=remember_me)


def clear_auth_cookies(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    response.delete_cookie("csrf_token", path="/")


def _read_token(request: Request) -> str | None:
    # Accept the access token only from the httponly cookie or the Authorization
    # header — never from a query parameter. Tokens in the URL leak into server
    # access logs, browser history, proxy logs and Referer headers. Browser <img>
    # tags already send the httponly cookie automatically, so authenticated file
    # serving works without exposing the token in the URL.
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    return token


async def get_current_user(request: Request) -> dict:
    token = _read_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token claims")

    # PERF: this runs on EVERY authenticated request. Re-fetching the same user
    # row from a cross-region pooler costs ~260ms per call, and a single page
    # fans out to ~10 requests → ~2.6s of pure auth round-trips. Cache the
    # sanitized user dict by id for a short TTL (30s). Profile edits / role
    # changes / deactivation invalidate `user:<id>` so they take effect at once
    # on this process; otherwise the change is visible within TTL_USER seconds.
    user = await cache.get_or_set(
        f"user:{sub}", cache.TTL_USER, lambda: _load_user(sub), cache_none=False
    )
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    # Reject a deactivated account even if it still holds an unexpired token
    # (access tokens live 24h). is_active defaults True, so existing users and
    # any row where the column is unset are unaffected.
    if user.get("is_active") is False:
        raise HTTPException(status_code=403, detail="Account is deactivated")
    return user


async def _load_user(user_id: str) -> dict | None:
    """Fetch + sanitize a user row by id (the cached loader for get_current_user)."""
    from .utils import _row_to_dict
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user_row = result.scalar_one_or_none()
    if not user_row:
        return None
    user = _row_to_dict(user_row)
    if user is None:
        return None
    user.pop("password_hash", None)
    if user.get("module_permissions") is None:
        user["module_permissions"] = []
    if user.get("permissions") is None:
        user["permissions"] = []
    return user


def invalidate_user_cache(user_id: str) -> None:
    """Drop a user's cached identity so the next request re-reads from the DB.

    Call after any write that changes auth-relevant fields: role,
    module_permissions, is_active, name/profile, password (logout-all)."""
    cache.invalidate(f"user:{user_id}")


def is_admin_role(role: str | None) -> bool:
    """True for both full-access roles. super_admin was added alongside the
    10-role spec (auth_hardening migration) as a distinct selectable role, but
    it must behave as a full alias of "admin" for every authorization check —
    every `_require_X` guard across routers/ should use this instead of a
    literal `role == "admin"` comparison."""
    return role in ("admin", "super_admin")


def bypasses_row_ownership(role: str | None) -> bool:
    """True for roles that skip row-level ownership filtering (see
    core/utils.py's OWNED_COLLECTIONS / apply_ownership_filter /
    assert_owns_or_404) — Manager sees every row, same as Admin/Super Admin,
    by explicit product decision for THIS feature only.

    Deliberately NOT folded into is_admin_role(): that function backs
    require_admin(), which gates ~120 admin-only endpoints (user management,
    security settings, etc.) across the app. Adding "manager" there would
    silently grant Manager full admin access everywhere, not just row-level
    visibility — a much bigger privilege change than intended. Use this
    function ONLY for the ownership-bypass checks introduced alongside
    OWNED_COLLECTIONS; use is_admin_role/require_admin for everything else.
    """
    return is_admin_role(role) or role == "manager"


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not is_admin_role(user.get("role")):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_hr_or_admin(user: dict = Depends(get_current_user)) -> dict:
    if not is_admin_role(user.get("role")) and user.get("role") != "hr" and "hr" not in user.get("module_permissions", []):
        raise HTTPException(status_code=403, detail="HR or Admin access required")
    return user


async def require_payroll_role(user: dict = Depends(get_current_user)) -> dict:
    if (not is_admin_role(user.get("role")) and user.get("role") not in ("hr", "accountant")
            and "payroll" not in user.get("module_permissions", [])):
        raise HTTPException(status_code=403, detail="HR/Accountant/Admin access required")
    return user


async def require_company_profile(user: dict = Depends(get_current_user)) -> dict:
    if not is_admin_role(user.get("role")) and "company_profile" not in user.get("module_permissions", []):
        raise HTTPException(status_code=403, detail="Company Profile access required")
    return user


async def require_po_numbering(user: dict = Depends(get_current_user)) -> dict:
    if not is_admin_role(user.get("role")) and "po_numbering" not in user.get("module_permissions", []):
        raise HTTPException(status_code=403, detail="PO Numbering access required")
    return user


async def require_document_numbering(user: dict = Depends(get_current_user)) -> dict:
    if not is_admin_role(user.get("role")) and "document_numbering" not in user.get("module_permissions", []):
        raise HTTPException(status_code=403, detail="Document Numbering access required")
    return user
