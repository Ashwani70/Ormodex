"""Tenant scoping — Masters subsystem helpers, plus the request-scoped
enforcement layer for the wider multi-company conversion.

This ERP was single-tenant in practice (no per-tenant auth context existed),
but the Masters collections were built tenant-ready so multi-tenancy was "one
change away" — a handful of subsystems (masters, voucher engine, debtors/
creditors, letterhead designer, job-work items, biometric) already:

- Carry a `tenant_id` on every document.
- Get a compound index with `tenant_id` first.
- Filter/stamp every read/write through `tenant_filter()` / `stamp_tenant()`,
  which resolve the tenant from ONE place: `resolve_tenant()`.

That part of this module is UNCHANGED and still the right tool for those 6
subsystems. `resolve_tenant()` still returns the user's `tenant_id` if
present, else `DEFAULT_TENANT` — and since no user has a real `tenant_id` yet
(Phase 3, not built here), it still always resolves to `"default"` today.

WHAT'S NEW (Phase 2 of the multi-company conversion): a request-scoped
ContextVar (`bind_tenant`/`unbind_tenant`/`current_tenant`) that
core/_mongo_compat.py and core/utils.py's crud_get/crud_update/crud_delete
read to auto-filter/auto-stamp EVERY tenant-having table, not just the 6
subsystems that call tenant_filter()/stamp_tenant() by hand. This is gated
behind TENANT_ENFORCEMENT (default OFF) — with the flag off, current_tenant()
always returns DEFAULT_TENANT, so every table (already backfilled to
'default' by alembic/versions/032_tenant_backfill.py) matches and nothing
observably changes. Flipping the flag on is a later, separate phase — this
module only builds the mechanism and proves it correct while inert.

KNOWN GAP, DELIBERATELY NOT FIXED HERE (must be resolved before
TENANT_ENFORCEMENT can ever be turned on in production): several code paths
run outside the HTTP request lifecycle that binds this ContextVar, so they
will see it unset — under fail-closed semantics (see current_tenant()) any
of these that queries a tenant-having table would need to bind a tenant (or
an explicit bypass) manually before doing so:
  - server.py's startup `asyncio.create_task(scheduler_loop(_db))`
    (biometric attendance sync) and `asyncio.create_task(_run_startup_init())`
    — both run before/outside any request, doing cross-tenant seeding/drift
    work by nature, not user-scoped reads.
  - routers/debtors_creditors.py and routers/payroll.py's FastAPI
    `BackgroundTasks` handlers — these run AFTER the response is sent, by
    which point the request's contextvar has already been reset() by the
    binding middleware; a detached BackgroundTasks callback does not
    automatically inherit a "live" copy the way an awaited call within the
    same request does.
This module does not attempt to fix these — it documents them so a future
phase enabling enforcement finds this comment instead of a mystery outage.
"""
import os
from contextvars import ContextVar
from typing import Optional

from fastapi import Depends

from .auth_utils import get_current_user

DEFAULT_TENANT = "default"

# Sentinel meaning "explicitly bypass tenant filtering for this request" —
# reserved for a future super_admin cross-tenant dependency (not built here).
# Distinct from "unset" so a bypass can never be confused with "forgot to
# bind a tenant" under fail-closed semantics.
TENANT_BYPASS = "__ALL__"

# OFF by default — see current_tenant()'s docstring for exactly what each
# state means. Read once at import, matching core/db.py's env-var-gated
# constants style elsewhere in this module family.
TENANT_ENFORCEMENT = os.getenv("TENANT_ENFORCEMENT", "0") == "1"

# Request-scoped "which tenant is this request for" — set by request
# middleware (mirrors core/db.py's _request_session ContextVar exactly,
# including the Token-based set()/reset() pattern rather than set(None), so
# nested binds/exception paths correctly restore the PRIOR value instead of
# stomping it). Not yet bound by any middleware in this phase — that wiring
# is Phase 3 (auth/JWT), once there's a real per-user tenant_id to bind.
_current_tenant: ContextVar[Optional[str]] = ContextVar("_current_tenant", default=None)


def bind_tenant(tenant_id: str):
    """Set by request middleware; returns the ContextVar token for reset()."""
    return _current_tenant.set(tenant_id)


def unbind_tenant(token) -> None:
    _current_tenant.reset(token)


def current_tenant() -> str:
    """The tenant id the enforcement layer (core/_mongo_compat.py,
    core/utils.py's crud_get/crud_update/crud_delete) should filter/stamp by
    for the current request.

    Two states when unset (no bind_tenant() call happened for this request —
    e.g. no middleware wired yet, or one of the non-request code paths
    documented in this module's docstring):
      - TENANT_ENFORCEMENT off (default, this phase): return DEFAULT_TENANT.
        Matches today's actual behavior (every row already backfilled to
        'default'; resolve_tenant() already falls back the same way) — the
        enforcement layer added in this phase is provably a no-op while the
        flag is off.
      - TENANT_ENFORCEMENT on (a later phase): raise, rather than silently
        returning DEFAULT_TENANT or skipping the filter. Fail-closed is the
        confirmed design: a tenant-scoped query with no known tenant must
        reject, never guess or return cross-tenant data. Any genuinely
        cross-tenant caller must pass TENANT_BYPASS explicitly via a future
        super_admin-gated dependency, never rely on "just don't bind
        anything."
    """
    val = _current_tenant.get()
    if val is not None:
        return val
    if not TENANT_ENFORCEMENT:
        return DEFAULT_TENANT
    raise RuntimeError(
        "current_tenant() called with no tenant bound and TENANT_ENFORCEMENT "
        "is on — refusing to fail open. See core/tenant.py's module "
        "docstring for the known non-request code paths that must bind a "
        "tenant (or an explicit bypass) before this can be enabled safely."
    )


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
