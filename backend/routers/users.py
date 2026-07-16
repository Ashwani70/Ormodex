import secrets

from fastapi import APIRouter, Depends, HTTPException

from core.auth_utils import (
    hash_password, invalidate_user_cache, require_admin,
    revoke_user_devices, revoke_user_refresh_tokens,
)
from core.db import db
from core.email import is_configured as email_configured, render_security_notification_html, send_email_sync
from core.models import AdminResetPasswordIn, ModulePermissionsIn, UserCreate, UserUpdate
from core.modules import MODULES, valid_module_keys
from core.utils import log_audit, new_id, now_iso

router = APIRouter(prefix="/users", tags=["users"])


async def _notify_admin_reset(user: dict) -> None:
    """Notify the user their password was reset by an admin. Deliberately does
    not include the temp password in the email — that's handed to the admin
    once in the API response, out-of-band from the user's own inbox."""
    if not user.get("email") or not email_configured():
        return
    try:
        html = render_security_notification_html("password_changed", {"Reset by": "An administrator"})
        send_email_sync(to=user["email"], subject="Ormodex ERP · Your password was reset by an administrator", html=html)
    except Exception:
        pass


@router.get("/modules")
async def list_modules(_: dict = Depends(require_admin)):
    """The catalog of grantable module keys + labels, for the user-admin UI."""
    return [{"key": key, "label": label} for key, label in MODULES]


@router.get("")
async def list_users(_: dict = Depends(require_admin)):
    return await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)


@router.post("")
async def create_user(payload: UserCreate, current: dict = Depends(require_admin)):
    email = payload.email.lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")
    username = (payload.username or "").strip().lower() or None
    if username:
        existing_uname = await db.users.find_one({"username": username})
        if existing_uname:
            raise HTTPException(status_code=400, detail="Username already taken")
    doc = {
        "id": new_id(),
        "name": payload.name,
        "email": email,
        "username": username,
        "phone": payload.phone,
        "role": payload.role,
        "permissions": payload.permissions or {},
        # Drop unknown keys so a bad value can't be persisted; guards read this.
        "module_permissions": valid_module_keys(payload.module_permissions or []),
        "password_hash": hash_password(payload.password),
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    doc.pop("_id", None)
    doc.pop("password_hash", None)
    await log_audit("USER_CREATED", "users", doc["id"], current, new_values={"email": email, "role": payload.role})
    return doc


@router.put("/{user_id}")
async def update_user(user_id: str, payload: UserUpdate, current: dict = Depends(require_admin)):
    before = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not before:
        raise HTTPException(status_code=404, detail="User not found")

    update = {}
    if payload.name is not None:
        update["name"] = payload.name
    if payload.username is not None:
        uname = payload.username.strip().lower() or None
        if uname:
            existing_uname = await db.users.find_one({"username": uname, "id": {"$ne": user_id}})
            if existing_uname:
                raise HTTPException(status_code=400, detail="Username already taken")
        update["username"] = uname
    if payload.phone is not None:
        update["phone"] = payload.phone
    if payload.role is not None:
        update["role"] = payload.role
    if payload.module_permissions is not None:
        update["module_permissions"] = valid_module_keys(payload.module_permissions)
    if payload.is_active is not None:
        update["is_active"] = payload.is_active
    if payload.password:
        update["password_hash"] = hash_password(payload.password)
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")

    res = await db.users.update_one({"id": user_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    invalidate_user_cache(user_id)  # role/perms/profile/password may have changed

    after = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    await log_audit("USER_UPDATED", "users", user_id, current, old_values=before, new_values=after)
    if payload.role is not None and payload.role != before.get("role"):
        await log_audit("ROLE_CHANGED", "users", user_id, current,
                         old_values={"role": before.get("role")}, new_values={"role": payload.role})
    if payload.module_permissions is not None and payload.module_permissions != before.get("module_permissions"):
        await log_audit("PERMISSION_CHANGED", "users", user_id, current,
                         old_values={"module_permissions": before.get("module_permissions")},
                         new_values={"module_permissions": update["module_permissions"]})
    return after


@router.put("/{user_id}/module-permissions")
async def set_module_permissions(user_id: str, payload: ModulePermissionsIn, current: dict = Depends(require_admin)):
    """Replace a user's module access list (validated against the catalog)."""
    before = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not before:
        raise HTTPException(status_code=404, detail="User not found")
    keys = valid_module_keys(payload.module_permissions)
    res = await db.users.update_one({"id": user_id}, {"$set": {"module_permissions": keys}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    invalidate_user_cache(user_id)
    await log_audit("PERMISSION_CHANGED", "users", user_id, current,
                     old_values={"module_permissions": before.get("module_permissions")},
                     new_values={"module_permissions": keys})
    return await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})


@router.patch("/{user_id}/permissions")
async def update_user_permissions(user_id: str, permissions: dict, current: dict = Depends(require_admin)):
    # Legacy: writes the free-form `permissions` dict (not read by router guards).
    # Prefer PUT /{user_id}/module-permissions for access control.
    res = await db.users.update_one({"id": user_id}, {"$set": {"permissions": permissions}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    invalidate_user_cache(user_id)
    return await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})


@router.delete("/{user_id}")
async def delete_user(user_id: str, current: dict = Depends(require_admin)):
    if user_id == current["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    res = await db.users.delete_one({"id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    invalidate_user_cache(user_id)
    return {"ok": True}


# ── Admin security controls ─────────────────────────────────────────────────

@router.post("/{user_id}/lock")
async def lock_user(user_id: str, current: dict = Depends(require_admin)):
    res = await db.users.update_one({"id": user_id}, {"$set": {"is_locked": True}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    invalidate_user_cache(user_id)
    await revoke_user_refresh_tokens(user_id)
    await revoke_user_devices(user_id)
    await log_audit("USER_LOCKED", "users", user_id, current)
    return {"ok": True}


@router.post("/{user_id}/unlock")
async def unlock_user(user_id: str, current: dict = Depends(require_admin)):
    res = await db.users.update_one(
        {"id": user_id},
        {"$set": {"is_locked": False, "locked_until": None, "failed_login_count": 0}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    invalidate_user_cache(user_id)
    await log_audit("USER_UNLOCKED", "users", user_id, current)
    return {"ok": True}


@router.post("/{user_id}/force-password-change")
async def force_password_change(user_id: str, current: dict = Depends(require_admin)):
    res = await db.users.update_one(
        {"id": user_id},
        {"$set": {"password_change_required": True, "force_change_reason": "admin_reset"}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    invalidate_user_cache(user_id)
    await log_audit("FORCE_PASSWORD_CHANGE", "users", user_id, current)
    return {"ok": True}


@router.post("/{user_id}/reset-password")
async def admin_reset_password(user_id: str, payload: AdminResetPasswordIn, current: dict = Depends(require_admin)):
    """Admin-initiated password reset. Forces a change on next login, revokes
    all of that user's sessions, and emails them a notice (best-effort)."""
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    from core.password_policy import PASSWORD_HISTORY_SIZE
    temp_password = payload.new_password or (secrets.token_urlsafe(9) + "Aa1!")
    history = list(user.get("password_history") or [])
    old_hash = user.get("password_hash")
    if old_hash:
        history.insert(0, old_hash)
    history = history[:PASSWORD_HISTORY_SIZE]

    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "password_hash": hash_password(temp_password),
            "password_history": history,
            "last_password_change": now_iso(),
            "password_change_required": True,
            "force_change_reason": "admin_reset",
        }},
    )
    invalidate_user_cache(user_id)
    await revoke_user_refresh_tokens(user_id)
    await revoke_user_devices(user_id)
    await log_audit("ADMIN_PASSWORD_RESET", "users", user_id, current)
    await _notify_admin_reset(user)
    return {"ok": True, "temp_password": temp_password}


@router.get("/{user_id}/login-history")
async def user_login_history(user_id: str, _: dict = Depends(require_admin), limit: int = 50):
    items = await db.login_history.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("created_at", -1).limit(min(limit, 200)).to_list(200)
    return items


@router.get("/{user_id}/devices")
async def user_devices(user_id: str, _: dict = Depends(require_admin)):
    devices = await db.user_devices.find(
        {"user_id": user_id, "revoked": False}, {"_id": 0}
    ).sort("last_active_at", -1).to_list(100)
    return devices
