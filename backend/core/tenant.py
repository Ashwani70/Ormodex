"""Tenant scoping for the Masters subsystem.

This ERP is currently single-tenant on MongoDB (no per-tenant auth context yet),
but the Masters collections are built tenant-ready so multi-tenancy is one change
away and nothing has to be faked:

- Every masters document carries a `tenant_id`.
- Every collection gets a compound index with `tenant_id` first.
- Every read/write is filtered through `tenant_filter()` / stamped via
  `stamp_tenant()`, which resolve the tenant from ONE place: `resolve_tenant()`.

Today `resolve_tenant()` returns the user's `tenant_id` if present, else the
`DEFAULT_TENANT` sentinel. When real multi-tenancy lands, only `resolve_tenant()`
(and the auth dependency feeding it) needs to change — call sites stay the same.
"""
from typing import Optional

from fastapi import Depends

from .auth_utils import get_current_user

DEFAULT_TENANT = "default"


def resolve_tenant(user: Optional[dict]) -> str:
    """The single source of truth for "which tenant is this request for?"."""
    if user and user.get("tenant_id"):
        return user["tenant_id"]
    return DEFAULT_TENANT


async def tenant_ctx(user: dict = Depends(get_current_user)) -> str:
    """FastAPI dependency yielding the caller's tenant id."""
    return resolve_tenant(user)


def tenant_filter(tenant_id: str, extra: Optional[dict] = None, *, include_deleted: bool = False) -> dict:
    """Build a query filter scoped to a tenant, excluding soft-deleted docs."""
    q: dict = {"tenant_id": tenant_id}
    if not include_deleted:
        q["is_deleted"] = {"$ne": True}
    if extra:
        q.update(extra)
    return q


def stamp_tenant(doc: dict, tenant_id: str) -> dict:
    """Stamp tenant_id onto a document before insert."""
    doc["tenant_id"] = tenant_id
    return doc
