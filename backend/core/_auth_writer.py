"""Temporary script — run once to write auth_utils.py, then delete."""
import os

path = os.path.join(os.path.dirname(__file__), "auth_utils.py")

CONTENT = '''\
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Literal

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select, update

from .db import get_session
from .schema import User, RefreshToken

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MIN = 60 * 24
REFRESH_TOKEN_DAYS = 7


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


async def create_refresh_token(user_id: str) -> str:
    from .utils import new_id, now_iso
    jti = uuid.uuid4().hex
    expires_iso = (datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS)).isoformat()
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
        "type": "refresh",
        "jti": jti,
    }
    async with get_session() as session:
        session.add(RefreshToken(
            id=new_id(),
            jti=jti,
            user_id=user_id,
            active=True,
            expires_at=expires_iso,
            created_at=now_iso(),
        ))
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


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


def set_auth_cookies(response: Response, access: str, refresh: str):
    is_prod = os.environ.get("ENV", "development").lower() == "production"
    secure = is_prod
    samesite: Literal["lax", "strict", "none"] = "none" if is_prod else "lax"
    response.set_cookie("access_token", access, httponly=True, secure=secure, samesite=samesite, max_age=ACCESS_TOKEN_MIN * 60, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=secure, samesite=samesite, max_age=REFRESH_TOKEN_DAYS * 86400, path="/")


def clear_auth_cookies(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


def _read_token(request: Request) -> str | None:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        token = request.query_params.get("auth")
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
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == sub))
        user_row = result.scalar_one_or_none()
    if not user_row:
        raise HTTPException(status_code=401, detail="User not found")
    from .utils import _row_to_dict
    user = _row_to_dict(user_row)
    user.pop("password_hash", None)
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_hr_or_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("admin", "hr"):
        raise HTTPException(status_code=403, detail="HR or Admin access required")
    return user


async def require_payroll_role(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("admin", "hr", "accountant"):
        raise HTTPException(status_code=403, detail="HR/Accountant/Admin access required")
    return user
'''

with open(path, "w", encoding="utf-8") as f:
    f.write(CONTENT)

print(f"Written {len(CONTENT)} chars")
