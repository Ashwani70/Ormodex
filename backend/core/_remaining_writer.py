"""Temporary script — run once to write remaining core files, then delete."""
import os

BASE = os.path.dirname(__file__)

files = {}

# ── email.py ──────────────────────────────────────────────────────────────────
files["email.py"] = '''\
"""Resend email helper — sends transactional emails and logs to email_logs."""
import base64
import os
from typing import Optional

import resend

from .utils import new_id, now_iso


def _resend_client():
    resend.api_key = os.environ.get("RESEND_API_KEY", "")
    return resend


async def log_email(*args, **kwargs) -> None:
    pass


async def send_email(
    to: str,
    subject: str,
    html: str,
    tenant_id: Optional[str] = None,
    template: str = "",
) -> bool:
    try:
        client = _resend_client()
        client.Emails.send({
            "from": "Ormodex ERP <no-reply@ormodex.com>",
            "to": [to],
            "subject": subject,
            "html": html,
        })
        await log_email(to, subject, template, "sent", tenant_id=tenant_id)
        return True
    except Exception as e:
        await log_email(to, subject, template, "failed", error=str(e), tenant_id=tenant_id)
        return False
'''

# ── portal_auth.py ────────────────────────────────────────────────────────────
files["portal_auth.py"] = '''\
"""Vendor/customer portal JWT auth helpers."""
import os
from datetime import datetime, timezone, timedelta
from functools import wraps

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

from .db import get_session
from .schema import PortalUser
from .utils import _row_to_dict

JWT_ALGORITHM = "HS256"
PORTAL_TOKEN_DAYS = 7


def _jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def _hash(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def _verify(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except Exception:
        return False


def create_portal_token(portal_user_id: str, party_type: str, party_id: str) -> str:
    payload = {
        "sub": portal_user_id,
        "party_type": party_type,
        "party_id": party_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=PORTAL_TOKEN_DAYS),
        "type": "portal",
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


async def get_portal_user(request: Request) -> dict:
    token = request.cookies.get("portal_token") or request.headers.get("Authorization", "").removeprefix("Bearer ").strip() or None
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "portal":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    from sqlalchemy import select
    async with get_session() as session:
        result = await session.execute(select(PortalUser).where(PortalUser.id == payload["sub"]))
        row = result.scalar_one_or_none()
    if not row or not row.is_active:
        raise HTTPException(status_code=401, detail="Portal user not found or inactive")
    return _row_to_dict(row)


def party_scoped(func):
    """Decorator: injects portal_user from request, checks it is active."""
    @wraps(func)
    async def wrapper(*args, request: Request, **kwargs):
        portal_user = await get_portal_user(request)
        return await func(*args, request=request, portal_user=portal_user, **kwargs)
    return wrapper


def assert_party_match(portal_user: dict, party_type: str, party_id: str):
    if portal_user.get("party_type") != party_type or portal_user.get("party_id") != party_id:
        raise HTTPException(status_code=403, detail="Access denied")
'''

# ── stock_ledger.py ───────────────────────────────────────────────────────────
files["stock_ledger.py"] = '''\
"""Stock ledger posting service — append-only StockLedgerEntry via SQLAlchemy."""
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, and_

from .db import get_session
from .schema import StockLedgerEntry, StockItem
from .utils import new_id, now_iso


async def _item_method(stock_item_id: str, session) -> str:
    result = await session.execute(
        select(StockItem.valuation_method).where(StockItem.id == stock_item_id)
    )
    return result.scalar_one_or_none() or "WEIGHTED_AVG"


async def _prior_entries(stock_item_id: str, godown_id: Optional[str], session) -> list:
    conditions = [StockLedgerEntry.stock_item_id == stock_item_id]
    if godown_id:
        conditions.append(StockLedgerEntry.godown_id == godown_id)
    result = await session.execute(
        select(StockLedgerEntry)
        .where(and_(*conditions))
        .order_by(StockLedgerEntry.txn_date, StockLedgerEntry.created_at)
    )
    return result.scalars().all()


def value_movements(entries: list) -> list[dict]:
    """Replay entries into running balance list (FIFO/WAVG compatible)."""
    layers = []
    running_qty = Decimal(0)
    running_value = Decimal(0)
    for e in entries:
        qty_in = Decimal(str(e.qty_in or 0))
        qty_out = Decimal(str(e.qty_out or 0))
        rate = Decimal(str(e.rate or 0))
        if qty_in > 0:
            running_qty += qty_in
            running_value += qty_in * rate
        if qty_out > 0:
            avg = running_value / running_qty if running_qty else Decimal(0)
            val_out = qty_out * avg
            running_qty -= qty_out
            running_value -= val_out
        layers.append({
            "id": e.id,
            "running_qty": float(running_qty),
            "running_value": float(running_value),
        })
    return layers


async def post_entry(
    tenant_id: str,
    stock_item_id: str,
    doc_type: str,
    source_doc_id: str,
    txn_date: str,
    qty_in: float = 0.0,
    qty_out: float = 0.0,
    rate: float = 0.0,
    godown_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    serial_no: Optional[str] = None,
    voucher_no: Optional[str] = None,
    session=None,
) -> dict:
    async def _do(s):
        prior = await _prior_entries(stock_item_id, godown_id, s)
        movements = value_movements(prior)
        if movements:
            last = movements[-1]
            running_qty = last["running_qty"]
            running_value = last["running_value"]
        else:
            running_qty = 0.0
            running_value = 0.0

        new_qty = running_qty + qty_in - qty_out
        avg_rate = (running_value / running_qty) if running_qty else rate
        value_in = qty_in * rate
        value_out = qty_out * avg_rate
        new_value = running_value + value_in - value_out

        entry = StockLedgerEntry(
            id=new_id(),
            tenant_id=tenant_id,
            stock_item_id=stock_item_id,
            godown_id=godown_id,
            batch_id=batch_id,
            serial_no=serial_no,
            doc_type=doc_type,
            source_doc_id=source_doc_id,
            voucher_no=voucher_no,
            txn_date=txn_date,
            qty_in=qty_in,
            qty_out=qty_out,
            rate=rate,
            value_in=value_in,
            value_out=value_out,
            running_qty=new_qty,
            running_value=new_value,
            created_at=now_iso(),
        )
        s.add(entry)
        return {
            "id": entry.id,
            "running_qty": new_qty,
            "running_value": new_value,
        }

    if session is not None:
        return await _do(session)
    async with get_session() as s:
        return await _do(s)


async def on_hand(tenant_id: str, stock_item_id: str, godown_id: Optional[str] = None) -> dict:
    async with get_session() as session:
        entries = await _prior_entries(stock_item_id, godown_id, session)
        if not entries:
            return {"qty": 0.0, "value": 0.0}
        movements = value_movements(entries)
        last = movements[-1]
        return {"qty": last["running_qty"], "value": last["running_value"]}
'''

# ── masters_crud.py ───────────────────────────────────────────────────────────
files["masters_crud.py"] = '''\
"""Shared CRUD for Masters: tenant-scoped, audited, soft-delete only."""
from typing import Optional

from sqlalchemy import select, func, and_, or_

from .db import get_session
from .schema import AuditLog
from .utils import new_id, now_iso, _table, _row_to_dict, build_audit_entry


def _tenant_conditions(Model, tenant_id: Optional[str], extra: Optional[dict] = None):
    conditions = [Model.is_deleted == False]
    if tenant_id:
        conditions.append(Model.tenant_id == tenant_id)
    if extra:
        for k, v in extra.items():
            if hasattr(Model, k):
                conditions.append(getattr(Model, k) == v)
    return conditions


async def masters_create(
    collection: str,
    data: dict,
    tenant_id: Optional[str] = None,
    user: Optional[dict] = None,
) -> dict:
    Model = _table(collection)
    if "id" not in data or not data["id"]:
        data["id"] = new_id()
    now = now_iso()
    data.setdefault("created_at", now)
    data.setdefault("updated_at", now)
    if tenant_id:
        data.setdefault("tenant_id", tenant_id)
    data["is_deleted"] = False

    async with get_session() as session:
        row = Model(**{k: v for k, v in data.items() if hasattr(Model, k)})
        session.add(row)
        await session.flush()
        if user:
            session.add(AuditLog(**build_audit_entry(
                "create", collection, data["id"], user, after=data,
                tenant_id=data.get("tenant_id"),
            )))
    return data


async def masters_list(
    collection: str,
    tenant_id: Optional[str] = None,
    extra: Optional[dict] = None,
    limit: int = 500,
    skip: int = 0,
    search: Optional[str] = None,
    search_field: str = "name",
) -> list[dict]:
    Model = _table(collection)
    async with get_session() as session:
        conditions = _tenant_conditions(Model, tenant_id, extra)
        stmt = select(Model).where(and_(*conditions))
        if search and hasattr(Model, search_field):
            col = getattr(Model, search_field)
            stmt = stmt.where(col.ilike(f"%{search}%"))
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return [_row_to_dict(r) for r in result.scalars().all()]


async def masters_list_paginated(
    collection: str,
    tenant_id: Optional[str] = None,
    extra: Optional[dict] = None,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    search_field: str = "name",
) -> dict:
    Model = _table(collection)
    skip = (page - 1) * page_size
    async with get_session() as session:
        conditions = _tenant_conditions(Model, tenant_id, extra)
        base = and_(*conditions)
        count_stmt = select(func.count()).select_from(Model).where(base)
        stmt = select(Model).where(base)
        if search and hasattr(Model, search_field):
            col = getattr(Model, search_field)
            extra_cond = col.ilike(f"%{search}%")
            count_stmt = count_stmt.where(extra_cond)
            stmt = stmt.where(extra_cond)
        total = (await session.execute(count_stmt)).scalar_one()
        if hasattr(Model, "name"):
            stmt = stmt.order_by(Model.name)
        stmt = stmt.offset(skip).limit(page_size)
        rows = (await session.execute(stmt)).scalars().all()
    return {
        "items": [_row_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


async def masters_get(collection: str, doc_id: str, tenant_id: Optional[str] = None) -> Optional[dict]:
    Model = _table(collection)
    async with get_session() as session:
        conditions = [Model.id == doc_id]
        if hasattr(Model, "is_deleted"):
            conditions.append(Model.is_deleted == False)
        if tenant_id:
            conditions.append(Model.tenant_id == tenant_id)
        result = await session.execute(select(Model).where(and_(*conditions)))
        return _row_to_dict(result.scalar_one_or_none())


async def masters_update(
    collection: str,
    doc_id: str,
    updates: dict,
    tenant_id: Optional[str] = None,
    user: Optional[dict] = None,
) -> Optional[dict]:
    Model = _table(collection)
    updates["updated_at"] = now_iso()
    async with get_session() as session:
        result = await session.execute(select(Model).where(Model.id == doc_id))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        before = _row_to_dict(row)
        for k, v in updates.items():
            if hasattr(row, k):
                setattr(row, k, v)
        if user:
            session.add(AuditLog(**build_audit_entry(
                "update", collection, doc_id, user, before=before, after=updates,
                tenant_id=getattr(row, "tenant_id", None),
            )))
    return await masters_get(collection, doc_id)


async def masters_soft_delete(
    collection: str,
    doc_id: str,
    tenant_id: Optional[str] = None,
    user: Optional[dict] = None,
) -> bool:
    Model = _table(collection)
    async with get_session() as session:
        result = await session.execute(select(Model).where(Model.id == doc_id))
        row = result.scalar_one_or_none()
        if row is None:
            return False
        before = _row_to_dict(row)
        row.is_deleted = True
        row.deleted_at = now_iso()
        if user:
            session.add(AuditLog(**build_audit_entry(
                "delete", collection, doc_id, user, before=before,
                tenant_id=getattr(row, "tenant_id", None),
            )))
    return True


async def singleton_get(collection: str, tenant_id: Optional[str] = None) -> Optional[dict]:
    Model = _table(collection)
    async with get_session() as session:
        conditions = []
        if tenant_id and hasattr(Model, "tenant_id"):
            conditions.append(Model.tenant_id == tenant_id)
        stmt = select(Model)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        result = await session.execute(stmt.limit(1))
        return _row_to_dict(result.scalar_one_or_none())


async def singleton_upsert(
    collection: str,
    data: dict,
    tenant_id: Optional[str] = None,
) -> dict:
    existing = await singleton_get(collection, tenant_id)
    if existing:
        return await masters_update(collection, existing["id"], data, tenant_id)
    if tenant_id:
        data.setdefault("tenant_id", tenant_id)
    return await masters_create(collection, data, tenant_id)


async def _validate_parent(collection: str, parent_id: str, tenant_id: Optional[str]) -> bool:
    existing = await masters_get(collection, parent_id, tenant_id)
    return existing is not None


async def _check_unique(collection: str, field: str, value: str, exclude_id: Optional[str], tenant_id: Optional[str]) -> bool:
    Model = _table(collection)
    async with get_session() as session:
        conditions = [
            getattr(Model, field) == value,
            Model.is_deleted == False,
        ]
        if tenant_id:
            conditions.append(Model.tenant_id == tenant_id)
        if exclude_id:
            conditions.append(Model.id != exclude_id)
        result = await session.execute(select(func.count()).select_from(Model).where(and_(*conditions)))
        return result.scalar_one() == 0
'''

# ── masters_models.py — keep backward-compat stub ─────────────────────────────
# masters_models.py is used by many routers for Pydantic schemas — leave it alone

# write all files
for fname, content in files.items():
    out = os.path.join(BASE, fname)
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Written {fname}: {len(content)} chars")
