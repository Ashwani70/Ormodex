"""Portal authentication realm — Module H.

A SEPARATE auth realm from internal users (core/auth_utils.py). Portal tokens:
- carry type "portal_access" (internal tokens are "access") — the two are
  mutually non-interchangeable; an internal token is rejected here and a portal
  token is rejected by get_current_user.
- embed the immutable `party_id` + `party_type` the session is scoped to.

Defense-in-depth scoping
------------------------
`party_scoped(query, portal_user)` ALWAYS injects the party_id taken from the
*token* (never from client input) into every query. Even if a handler forgets
to filter, or a client tampers with a body/param, the data-access layer forces
the scope. `assert_party_match` is a second guard for path/param ids.
"""
import os
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

from .db import db

PORTAL_JWT_ALGORITHM = "HS256"
PORTAL_ACCESS_MIN = 60 * 12   # 12h portal sessions


def _portal_secret() -> str:
    # Derive a distinct secret from the internal one so portal tokens can never
    # be replayed against the internal realm (and vice-versa) even by accident.
    # Fails closed (raises) if neither env var is set — matching
    # core/auth_utils.py's jwt_secret(). A hardcoded fallback here would let
    # anyone forge valid portal tokens against any deployment that forgot to
    # set JWT_SECRET/SECRET_KEY, since the fallback string is public (it's in
    # this source file).
    base = os.environ.get("JWT_SECRET") or os.environ.get("SECRET_KEY")
    if not base:
        raise RuntimeError(
            "JWT_SECRET or SECRET_KEY must be set — refusing to sign portal "
            "tokens with a hardcoded fallback secret."
        )
    return base + "::portal"


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode("utf-8"), h.encode("utf-8"))
    except Exception:
        return False


def create_portal_token(portal_user_id: str, party_id: str, party_type: str, email: str) -> str:
    payload = {
        "sub": portal_user_id,
        "party_id": party_id,
        "party_type": party_type,
        "email": email,
        "type": "portal_access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=PORTAL_ACCESS_MIN),
    }
    return jwt.encode(payload, _portal_secret(), algorithm=PORTAL_JWT_ALGORITHM)


def decode_portal_token(token: str) -> dict:
    """Decode + validate a portal token. Raises 401 on any problem, including an
    internal-realm token presented to the portal."""
    try:
        payload = jwt.decode(token, _portal_secret(), algorithms=[PORTAL_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Portal session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid portal token")
    if payload.get("type") != "portal_access":
        raise HTTPException(status_code=401, detail="Not a portal token")
    if not payload.get("party_id") or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid portal token claims")
    return payload


def _read_portal_token(request: Request) -> str | None:
    token = request.cookies.get("portal_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    return token


async def get_portal_user(request: Request) -> dict:
    """FastAPI dependency yielding the authenticated portal user (with party scope)."""
    token = _read_portal_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Portal authentication required")
    payload = decode_portal_token(token)

    pu = await db.portal_users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not pu:
        raise HTTPException(status_code=401, detail="Portal user not found")
    if pu.get("status") not in (None, "active"):
        raise HTTPException(status_code=403, detail=f"Portal account is {pu.get('status')}")
    # The token's party binding is authoritative; if the stored user drifted, reject.
    if pu.get("party_id") != payload["party_id"] or pu.get("party_type") != payload["party_type"]:
        raise HTTPException(status_code=403, detail="Portal account / token party mismatch")
    return pu


def require_customer(portal_user: dict = Depends(get_portal_user)) -> dict:
    if portal_user.get("party_type") != "customer":
        raise HTTPException(status_code=403, detail="Customer portal access required")
    return portal_user


def require_vendor(portal_user: dict = Depends(get_portal_user)) -> dict:
    if portal_user.get("party_type") != "vendor":
        raise HTTPException(status_code=403, detail="Vendor portal access required")
    return portal_user


# ── The data-access-layer scope enforcer (defense in depth) ──

def party_scoped(query: dict, portal_user: dict, party_field: str = "party_id") -> dict:
    """
    Force the query to the token's party. Overwrites any caller/client-supplied
    value for the scope field — the token is the ONLY source of truth.
    """
    scoped = dict(query or {})
    scoped[party_field] = portal_user["party_id"]
    return scoped


def assert_party_match(resource_party_id: str | None, portal_user: dict):
    """
    Second guard: after fetching a resource by id, confirm it belongs to the
    token's party. Rejects cross-party access even if the query somehow returned
    a foreign document. Returns nothing; raises 404 (not 403, to avoid leaking
    existence) on mismatch.
    """
    if resource_party_id != portal_user["party_id"]:
        raise HTTPException(status_code=404, detail="Not found")
