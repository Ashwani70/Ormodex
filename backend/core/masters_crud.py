"""Shared CRUD for Masters: tenant-scoped, audited, soft-delete only.

Every masters collection uses these helpers so the four non-negotiables are
enforced in one place:
  - tenant_id on every doc (via core.tenant)
  - audit record on every create/update/delete (via core.utils.log_audit)
  - soft-delete only (is_deleted / deleted_at) — never hard delete
  - tree masters validate parent_id (same tenant, not self, no cycle)

Masters are not side-effecting vouchers, so they do NOT go through maker-checker
(per spec, only ledger/inventory-posting vouchers do). VoucherType *defines*
voucher types but posts nothing itself, so it is a plain master too.
"""
from typing import Optional

from fastapi import HTTPException

from .db import db
from .tenant import stamp_tenant, tenant_filter
from .utils import log_audit, new_id, now_iso


async def masters_create(collection: str, doc: dict, tenant_id: str, user: dict,
                         *, unique_fields: Optional[list[str]] = None,
                         parent_field: Optional[str] = None) -> dict:
    if parent_field:
        await _validate_parent(collection, doc.get(parent_field), tenant_id)
    if unique_fields:
        await _check_unique(collection, doc, tenant_id, unique_fields, exclude_id=None)

    doc["id"] = new_id()
    stamp_tenant(doc, tenant_id)
    doc["is_deleted"] = False
    doc["deleted_at"] = None
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    await db[collection].insert_one(doc)
    doc.pop("_id", None)
    await log_audit("CREATE", collection, doc["id"], user, new_values=doc)
    return doc


async def masters_list(collection: str, tenant_id: str, *, q: Optional[str] = None,
                       search_fields: Optional[list[str]] = None,
                       extra: Optional[dict] = None, sort_field: str = "name") -> list[dict]:
    """Back-compat array list (unpaginated). Prefer masters_list_paginated for
    list endpoints; this remains for internal callers that want every row."""
    filt = tenant_filter(tenant_id, extra)
    if q and search_fields:
        filt["$or"] = [{f: {"$regex": q, "$options": "i"}} for f in search_fields]
    return await db[collection].find(filt, {"_id": 0}).sort(sort_field, 1).to_list(5000)


async def masters_list_paginated(collection: str, tenant_id: str, *, q: Optional[str] = None,
                                 search_fields: Optional[list[str]] = None,
                                 extra: Optional[dict] = None, sort_field: str = "name",
                                 page: int = 1, limit: int = 50,
                                 from_date: Optional[str] = None, to_date: Optional[str] = None,
                                 date_field: str = "created_at") -> dict:
    """Server-side paginated, filterable, searchable list.

    Returns {items, total, page, limit, pages}. `extra` carries equality filters
    (party/type/status etc.); `from_date`/`to_date` apply an inclusive range on
    `date_field`. Never trusts client paging: page>=1, 1<=limit<=200.
    """
    page = max(1, int(page or 1))
    limit = max(1, min(200, int(limit or 50)))
    filt = tenant_filter(tenant_id, extra)
    if q and search_fields:
        filt["$or"] = [{f: {"$regex": q, "$options": "i"}} for f in search_fields]
    if from_date or to_date:
        rng: dict = {}
        if from_date:
            rng["$gte"] = from_date
        if to_date:
            rng["$lte"] = to_date
        filt[date_field] = rng

    total = await db[collection].count_documents(filt)
    skip = (page - 1) * limit
    items = await db[collection].find(filt, {"_id": 0}).sort(sort_field, 1).skip(skip).limit(limit).to_list(limit)
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit else 0,
    }


async def masters_get(collection: str, item_id: str, tenant_id: str) -> dict:
    doc = await db[collection].find_one(tenant_filter(tenant_id, {"id": item_id}), {"_id": 0})
    if not doc:
        raise HTTPException(404, "Not found")
    return doc


async def masters_update(collection: str, item_id: str, changes: dict, tenant_id: str, user: dict,
                         *, unique_fields: Optional[list[str]] = None,
                         parent_field: Optional[str] = None) -> dict:
    old = await db[collection].find_one(tenant_filter(tenant_id, {"id": item_id}), {"_id": 0})
    if not old:
        raise HTTPException(404, "Not found")
    if parent_field and parent_field in changes:
        await _validate_parent(collection, changes.get(parent_field), tenant_id, child_id=item_id)
    if unique_fields:
        await _check_unique(collection, {**old, **changes}, tenant_id, unique_fields, exclude_id=item_id)

    changes["updated_at"] = now_iso()
    await db[collection].update_one(tenant_filter(tenant_id, {"id": item_id}), {"$set": changes})
    new_doc = await masters_get(collection, item_id, tenant_id)
    await log_audit("UPDATE", collection, item_id, user, old_values=old, new_values=new_doc)
    return new_doc


async def masters_soft_delete(collection: str, item_id: str, tenant_id: str, user: dict,
                              *, child_parent_field: Optional[str] = None) -> dict:
    old = await db[collection].find_one(tenant_filter(tenant_id, {"id": item_id}), {"_id": 0})
    if not old:
        raise HTTPException(404, "Not found")
    # Block deleting a tree node that still has (non-deleted) children.
    if child_parent_field:
        kid = await db[collection].find_one(
            tenant_filter(tenant_id, {child_parent_field: item_id}), {"_id": 0, "id": 1})
        if kid:
            raise HTTPException(400, "Cannot delete: this record has child records. Reassign or delete them first.")
    await db[collection].update_one(
        tenant_filter(tenant_id, {"id": item_id}),
        {"$set": {"is_deleted": True, "deleted_at": now_iso(), "updated_at": now_iso()}},
    )
    await log_audit("DELETE", collection, item_id, user, old_values=old)
    return {"ok": True, "soft_deleted": True}


# ───────────────────────── singleton (one doc per tenant) ─────────────────────────

async def singleton_get(collection: str, tenant_id: str) -> dict:
    """Return the tenant's single document, or an empty shell if none exists yet."""
    doc = await db[collection].find_one(tenant_filter(tenant_id), {"_id": 0})
    return doc or {"tenant_id": tenant_id, "exists": False}


async def singleton_upsert(collection: str, changes: dict, tenant_id: str, user: dict) -> dict:
    """Create-or-merge the tenant's single document and audit the change.

    Partial: only provided fields are merged onto any existing doc. There is no
    delete and no list for singletons — get + upsert only, per spec.
    """
    existing = await db[collection].find_one(tenant_filter(tenant_id), {"_id": 0})
    if existing:
        changes = {**changes, "updated_at": now_iso()}
        await db[collection].update_one(tenant_filter(tenant_id), {"$set": changes})
        new_doc = await db[collection].find_one(tenant_filter(tenant_id), {"_id": 0}) or {**existing, **changes}
        await log_audit("UPDATE", collection, existing.get("id", tenant_id), user,
                        old_values=existing, new_values=new_doc)
        return new_doc
    doc = dict(changes)
    doc["id"] = new_id()
    stamp_tenant(doc, tenant_id)
    doc["is_deleted"] = False
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    await db[collection].insert_one(doc)
    doc.pop("_id", None)
    await log_audit("CREATE", collection, doc["id"], user, new_values=doc)
    return doc


# ───────────────────────── internal helpers ─────────────────────────

async def _validate_parent(collection: str, parent_id, tenant_id: str, *, child_id: Optional[str] = None):
    if not parent_id:
        return  # top-level node
    if child_id and parent_id == child_id:
        raise HTTPException(400, "A record cannot be its own parent")
    parent = await db[collection].find_one(tenant_filter(tenant_id, {"id": parent_id}), {"_id": 0, "id": 1})
    if not parent:
        raise HTTPException(400, "Parent record not found in this tenant")
    # Cycle guard: walk up the chain, make sure we never reach child_id.
    if child_id:
        seen = set()
        cur = parent_id
        while cur:
            if cur == child_id:
                raise HTTPException(400, "Circular parent reference")
            if cur in seen:
                break
            seen.add(cur)
            node = await db[collection].find_one(
                tenant_filter(tenant_id, {"id": cur}), {"_id": 0})
            cur = node and _parent_value(node)


def _parent_value(node: dict):
    for f in ("parent_group_id", "parent_category_id", "parent_location_id", "parent_id", "base_unit_id"):
        if f in node:
            return node[f]
    return None


async def _check_unique(collection: str, doc: dict, tenant_id: str, fields: list[str], exclude_id: Optional[str]):
    for f in fields:
        val = doc.get(f)
        if val in (None, ""):
            continue
        extra = {f: val}
        if exclude_id:
            extra["id"] = {"$ne": exclude_id}
        clash = await db[collection].find_one(tenant_filter(tenant_id, extra), {"_id": 0, "id": 1})
        if clash:
            raise HTTPException(400, f"A record with {f}='{val}' already exists")
