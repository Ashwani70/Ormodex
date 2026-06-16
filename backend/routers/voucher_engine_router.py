"""Unified voucher engine API — one collection (vouchers_v2) for all parent types.

Maker-checker lifecycle: draft → pending → approved (posts) → (cancelled).
Only an *approved* voucher posts to books/stock (via core.voucher_engine).
Tenant-scoped, audited, soft-cancel (never hard delete).

Mounted at /voucher-engine. Coexists with the legacy /vouchers router.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth_utils import get_current_user
from core.db import db
from core.tenant import stamp_tenant, tenant_ctx, tenant_filter
from core.utils import log_audit, new_id, now_iso
from core.voucher_engine import (
    CATALOG, auto_reverse_due, post_voucher, spec_for, validate_voucher,
)
from core.voucher_models import VoucherCreate, VoucherUpdate

router = APIRouter(prefix="/voucher-engine", tags=["Voucher Engine"])

COLL = "vouchers_v2"


def _require_voucher(user: dict) -> dict:
    if user.get("role") in ("admin", "accountant"):
        return user
    perms = user.get("module_permissions") or []
    if any(p in perms for p in ("vouchers", "accounting", "inventory")):
        return user
    raise HTTPException(403, "Voucher module access required")


def _require_approver(user: dict) -> dict:
    # Maker-checker: approval is a distinct privilege from creation.
    if user.get("role") == "admin":
        return user
    perms = user.get("module_permissions") or []
    if "approve_vouchers" in perms or "approver" in perms:
        return user
    raise HTTPException(403, "Approver privilege required to approve vouchers")


async def _next_voucher_no(parent_type: str, voucher_type_id: Optional[str], tenant: str) -> str:
    """Auto number: prefer the linked VoucherType master's prefix, else parent_type."""
    fy = await db.fiscal_years.find_one({"is_active": True})
    fy_name = fy["name"] if fy else date.today().strftime("%Y-%y")
    prefix = parent_type[:3].upper()
    if voucher_type_id:
        vt = await db["master_voucher_types"].find_one(
            tenant_filter(tenant, {"id": voucher_type_id}), {"_id": 0, "prefix": 1})
        if vt and vt.get("prefix"):
            prefix = vt["prefix"]
    count = await db[COLL].count_documents(
        tenant_filter(tenant, {"parent_type": parent_type, "fiscal_year": fy_name}, include_deleted=True))
    return f"{prefix}/{fy_name}/{str(count + 1).zfill(5)}"


@router.get("/types")
async def list_parent_types(user: dict = Depends(get_current_user)):
    """The parent_type catalog with posting capabilities (for UI + transparency)."""
    _require_voucher(user)
    return {
        pt: {
            "category": s.category, "posts_to_books": s.posts_to_books,
            "posts_to_stock": s.posts_to_stock, "implemented": s.implemented, "note": s.note,
        }
        for pt, s in CATALOG.items()
    }


@router.get("")
async def list_vouchers(
    parent_type: Optional[str] = None,
    status: Optional[str] = None,
    party_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    page: int = 1,
    limit: int = Query(50, le=200),
    tenant: str = Depends(tenant_ctx),
    user: dict = Depends(get_current_user),
):
    _require_voucher(user)
    extra: dict = {}
    if parent_type:
        extra["parent_type"] = parent_type
    if status:
        extra["status"] = status
    if party_id:
        extra["party_id"] = party_id
    if from_date or to_date:
        rng: dict = {}
        if from_date:
            rng["$gte"] = from_date
        if to_date:
            rng["$lte"] = to_date
        extra["date"] = rng
    filt = tenant_filter(tenant, extra)
    total = await db[COLL].count_documents(filt)
    skip = (page - 1) * limit
    items = await db[COLL].find(filt, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "page": page, "items": items}


@router.get("/{voucher_id}")
async def get_voucher(voucher_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    _require_voucher(user)
    v = await db[COLL].find_one(tenant_filter(tenant, {"id": voucher_id}), {"_id": 0})
    if not v:
        raise HTTPException(404, "Voucher not found")
    return v


@router.post("")
async def create_voucher(payload: VoucherCreate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    """Create a voucher in DRAFT. Validated against its parent_type's rules."""
    _require_voucher(user)
    spec_for(payload.parent_type)  # 400 on unknown type
    doc = payload.model_dump()
    doc["id"] = new_id()
    stamp_tenant(doc, tenant)
    fy = await db.fiscal_years.find_one({"is_active": True})
    doc["fiscal_year"] = fy["name"] if fy else date.today().strftime("%Y-%y")
    doc["voucher_no"] = await _next_voucher_no(payload.parent_type, payload.voucher_type_id, tenant)
    doc["status"] = "draft"
    doc["is_deleted"] = False
    doc["created_by"] = user["id"]
    doc["approved_by"] = None
    doc["created_at"] = now_iso()
    doc["updated_at"] = now_iso()
    validate_voucher(doc)
    await db[COLL].insert_one(doc)
    doc.pop("_id", None)
    await log_audit("CREATE", COLL, doc["id"], user, new_values=doc)
    return doc


@router.patch("/{voucher_id}")
async def update_voucher(voucher_id: str, payload: VoucherUpdate, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    """Edit a draft/pending voucher. Approved and cancelled vouchers are immutable."""
    _require_voucher(user)
    v = await db[COLL].find_one(tenant_filter(tenant, {"id": voucher_id}), {"_id": 0})
    if not v:
        raise HTTPException(404, "Voucher not found")
    if v["status"] in ("approved", "cancelled"):
        raise HTTPException(400, f"Cannot edit a {v['status']} voucher")
    changes = {k: val for k, val in payload.model_dump(exclude_unset=True).items()}
    changes["updated_at"] = now_iso()
    merged = {**v, **changes}
    validate_voucher(merged)
    await db[COLL].update_one(tenant_filter(tenant, {"id": voucher_id}), {"$set": changes})
    new_doc = await db[COLL].find_one(tenant_filter(tenant, {"id": voucher_id}), {"_id": 0})
    await log_audit("UPDATE", COLL, voucher_id, user, old_values=v, new_values=new_doc)
    return new_doc


@router.post("/{voucher_id}/submit")
async def submit_voucher(voucher_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    """Maker step: draft → pending (ready for a checker)."""
    _require_voucher(user)
    v = await db[COLL].find_one(tenant_filter(tenant, {"id": voucher_id}), {"_id": 0})
    if not v:
        raise HTTPException(404, "Voucher not found")
    if v["status"] not in ("draft",):
        raise HTTPException(400, f"Can only submit a draft (this is '{v['status']}')")
    validate_voucher(v)
    await db[COLL].update_one(tenant_filter(tenant, {"id": voucher_id}),
                             {"$set": {"status": "pending", "updated_at": now_iso()}})
    await log_audit("UPDATE", COLL, voucher_id, user, old_values=v, new_values={**v, "status": "pending"})
    return {"ok": True, "status": "pending"}


@router.post("/{voucher_id}/approve")
async def approve_voucher(voucher_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    """Checker step: pending → approved, then POST to books/stock. Idempotent."""
    _require_approver(user)
    v = await db[COLL].find_one(tenant_filter(tenant, {"id": voucher_id}), {"_id": 0})
    if not v:
        raise HTTPException(404, "Voucher not found")
    if v["status"] == "approved":
        return {"ok": True, "status": "approved", "already": True}
    if v["status"] != "pending":
        raise HTTPException(400, f"Can only approve a pending voucher (this is '{v['status']}')")
    validate_voucher(v)
    # Post FIRST; only flip to approved if posting succeeds (so an un-posted
    # voucher is never left marked approved).
    posting = await post_voucher(v, user, tenant)
    await db[COLL].update_one(
        tenant_filter(tenant, {"id": voucher_id}),
        {"$set": {"status": "approved", "approved_by": user["id"],
                  "approved_at": now_iso(), "updated_at": now_iso(),
                  "posting_result": posting}},
    )
    new_doc = await db[COLL].find_one(tenant_filter(tenant, {"id": voucher_id}), {"_id": 0})
    await log_audit("UPDATE", COLL, voucher_id, user, old_values=v, new_values=new_doc)
    return {"ok": True, "status": "approved", "posting": posting}


@router.post("/{voucher_id}/cancel")
async def cancel_voucher(voucher_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    """Soft-cancel (never hard delete). Approved vouchers cannot be cancelled here —
    they must be reversed with a counter-voucher to preserve the audit trail."""
    _require_voucher(user)
    v = await db[COLL].find_one(tenant_filter(tenant, {"id": voucher_id}), {"_id": 0})
    if not v:
        raise HTTPException(404, "Voucher not found")
    if v["status"] == "approved":
        raise HTTPException(400, "Approved vouchers cannot be cancelled — post a reversing/credit voucher instead")
    if v["status"] == "cancelled":
        return {"ok": True, "status": "cancelled", "already": True}
    await db[COLL].update_one(tenant_filter(tenant, {"id": voucher_id}),
                             {"$set": {"status": "cancelled", "cancelled_by": user["id"],
                                       "cancelled_at": now_iso(), "updated_at": now_iso()}})
    await log_audit("UPDATE", COLL, voucher_id, user, old_values=v, new_values={**v, "status": "cancelled"})
    return {"ok": True, "status": "cancelled"}


@router.post("/run-reversing-journals")
async def run_reversing_journals(as_of: Optional[str] = None, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    """Post the mirror of any reversing journal whose effective date has arrived."""
    _require_voucher(user)
    reversed_count = await auto_reverse_due(tenant, as_of, user)
    return {"ok": True, "reversed": reversed_count}


async def create_voucher_engine_indexes(database):
    """Compound (tenant_id, ...) indexes for the unified voucher collection."""
    await database[COLL].create_index([("tenant_id", 1), ("id", 1)], unique=True)
    await database[COLL].create_index([("tenant_id", 1), ("parent_type", 1), ("status", 1)])
    await database[COLL].create_index([("tenant_id", 1), ("date", 1)])
