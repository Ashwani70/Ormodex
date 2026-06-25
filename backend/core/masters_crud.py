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
