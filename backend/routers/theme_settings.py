from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import Optional
import jwt

from core.auth_utils import (
    get_current_user,
    _read_token,
    jwt_secret,
    JWT_ALGORITHM
)
from core.db import db
from core.utils import now_iso

router = APIRouter(prefix="/theme-settings", tags=["theme-settings"])

# ── Two fixed themes only. The frontend owns the full color definitions; the
# backend simply persists which one each user (and the company) has chosen. ──
VALID_THEMES = {"gravity", "template", "slate"}
DEFAULT_THEME_ID = "gravity"


class ThemeSettingsPayload(BaseModel):
    theme_id: str


def _theme_doc(theme_id: str) -> dict:
    tid = theme_id if theme_id in VALID_THEMES else DEFAULT_THEME_ID
    return {"theme_id": tid}


async def get_optional_user(request: Request) -> Optional[dict]:
    try:
        token = _read_token(request)
        if not token:
            return None
        payload = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        return user
    except Exception:
        return None


@router.get("/active")
async def get_active_theme(request: Request):
    """Retrieve the current active theme.
    If authenticated, returns the user's preference; otherwise the global company
    theme, defaulting to the Gravity brand.
    """
    user = await get_optional_user(request)

    if user:
        user_theme = await db.theme_settings.find_one({"user_id": user["id"]}, {"_id": 0})
        if user_theme:
            return _theme_doc(user_theme.get("theme_id", DEFAULT_THEME_ID))

    global_theme = await db.theme_settings.find_one({"id": "global_active"}, {"_id": 0})
    if global_theme:
        return _theme_doc(global_theme.get("theme_id", DEFAULT_THEME_ID))

    return _theme_doc(DEFAULT_THEME_ID)


@router.get("")
async def get_user_theme(user: dict = Depends(get_current_user)):
    """Get the logged-in user's theme selection."""
    theme = await db.theme_settings.find_one({"user_id": user["id"]}, {"_id": 0})
    if theme:
        return _theme_doc(theme.get("theme_id", DEFAULT_THEME_ID))

    global_theme = await db.theme_settings.find_one({"id": "global_active"}, {"_id": 0})
    if global_theme:
        return _theme_doc(global_theme.get("theme_id", DEFAULT_THEME_ID))

    return _theme_doc(DEFAULT_THEME_ID)


@router.post("")
async def save_theme(payload: ThemeSettingsPayload, user: dict = Depends(get_current_user)):
    """Save the chosen theme for the current user. If admin, also set it as the
    company-wide active theme."""
    doc = _theme_doc(payload.theme_id)
    doc["updated_at"] = now_iso()
    doc["updated_by"] = user["id"]

    await db.theme_settings.update_one(
        {"user_id": user["id"]},
        {"$set": {**doc, "user_id": user["id"]}},
        upsert=True
    )

    if user.get("role") == "admin":
        await db.theme_settings.update_one(
            {"id": "global_active"},
            {"$set": {**doc, "id": "global_active"}},
            upsert=True
        )

    return _theme_doc(doc["theme_id"])


@router.post("/reset")
async def reset_theme(user: dict = Depends(get_current_user)):
    """Reset to the default Gravity brand theme."""
    await db.theme_settings.delete_one({"user_id": user["id"]})
    if user.get("role") == "admin":
        await db.theme_settings.delete_one({"id": "global_active"})
    return _theme_doc(DEFAULT_THEME_ID)
