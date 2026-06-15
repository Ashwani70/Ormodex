"""Read-only audit-trail endpoint.

Backs India's audit-trail mandate (Companies Accounts Rules, proviso to Rule
3(1); auditor reporting Rule 11(g)). The log is append-only — there are
deliberately no POST/PATCH/DELETE routes here. Writes happen automatically via
core.utils.log_audit on every create/update/delete. Access is restricted to
admin and auditor roles.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth_utils import get_current_user
from core.db import db

router = APIRouter(prefix="/audit-log", tags=["Audit Trail"])


async def require_auditor_or_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") in ("admin", "auditor"):
        return user
    # Allow an explicit module permission too, mirroring other routers' RBAC.
    if "audit" in (user.get("module_permissions") or []):
        return user
    raise HTTPException(status_code=403, detail="Auditor or Admin access required")


@router.get("")
async def list_audit_log(
    entity_type: Optional[str] = Query(None, description="Filter by collection/entity, e.g. 'purchase_orders'"),
    entity_id: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = Query(None, regex="^(CREATE|UPDATE|DELETE)$"),
    from_date: Optional[str] = Query(None, description="ISO date/datetime, inclusive lower bound"),
    to_date: Optional[str] = Query(None, description="ISO date/datetime, inclusive upper bound"),
    page: int = 1,
    limit: int = Query(50, le=500),
    user: dict = Depends(require_auditor_or_admin),
):
    q: dict = {}
    # Tenant scoping — single-tenant today, but scope by the caller's tenant when present.
    if user.get("tenant_id"):
        q["tenant_id"] = user["tenant_id"]
    if entity_type:
        # Match both the portable field and the legacy alias.
        q["$or"] = [{"entity_type": entity_type}, {"collection_name": entity_type}]
    if entity_id:
        q["$and"] = q.get("$and", []) + [{"$or": [{"entity_id": entity_id}, {"doc_id": entity_id}]}]
    if user_id:
        q["user_id"] = user_id
    if action:
        q["action"] = action
    if from_date or to_date:
        rng: dict = {}
        if from_date:
            rng["$gte"] = from_date
        if to_date:
            rng["$lte"] = to_date
        q["created_at"] = rng

    total = await db.audit_logs.count_documents(q)
    skip = (page - 1) * limit
    items = (
        await db.audit_logs.find(q, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )
    return {"total": total, "page": page, "limit": limit, "items": items}


@router.get("/{entry_id}")
async def get_audit_entry(entry_id: str, user: dict = Depends(require_auditor_or_admin)):
    entry = await db.audit_logs.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Audit entry not found")
    if user.get("tenant_id") and entry.get("tenant_id") != user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Audit entry not found")
    return entry
