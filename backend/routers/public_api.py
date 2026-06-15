"""Public versioned REST API — Module K.

`/api/v1/*` authenticated by API key (header `X-API-Key`) with scope checks.
Separate from the internal cookie-authenticated surface. Read-oriented; every
endpoint requires a scope the key was granted.
"""
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from typing import Optional

from core.db import db

# NOTE: this router is mounted at /v1 under the /api prefix → /api/v1/*
router = APIRouter(prefix="/v1", tags=["Public API v1"])


async def _api_key_auth(request: Request) -> dict:
    raw = request.headers.get("X-API-Key", "")
    if not raw:
        raise HTTPException(401, "X-API-Key header required")
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    key = await db.api_keys.find_one({"key_hash": key_hash, "active": True}, {"_id": 0})
    if not key:
        raise HTTPException(401, "Invalid or revoked API key")
    return key


def require_scope(scope: str):
    async def _dep(key: dict = Depends(_api_key_auth)) -> dict:
        scopes = key.get("scopes", [])
        if scope not in scopes and "*" not in scopes:
            raise HTTPException(403, f"API key lacks required scope '{scope}'")
        return key
    return _dep


@router.get("/ping")
async def ping(key: dict = Depends(_api_key_auth)):
    return {"ok": True, "key_name": key.get("name"), "scopes": key.get("scopes")}


@router.get("/invoices")
async def v1_invoices(
    status: Optional[str] = None,
    limit: int = Query(100, le=1000),
    key: dict = Depends(require_scope("invoices:read")),
):
    q = {"status": status} if status else {}
    return await db.invoices.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)


@router.get("/invoices/{invoice_id}")
async def v1_invoice(invoice_id: str, key: dict = Depends(require_scope("invoices:read"))):
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Not found")
    return inv


@router.get("/products")
async def v1_products(limit: int = Query(100, le=1000),
                      key: dict = Depends(require_scope("products:read"))):
    return await db.products.find({}, {"_id": 0}).limit(limit).to_list(limit)


@router.get("/customers")
async def v1_customers(limit: int = Query(100, le=1000),
                       key: dict = Depends(require_scope("customers:read"))):
    return await db.customers.find({}, {"_id": 0}).limit(limit).to_list(limit)
