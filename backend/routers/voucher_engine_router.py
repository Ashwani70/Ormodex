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
    CATALOG, auto_reverse_due, itc04_data, job_work_reconciliation,
    order_fulfilment, post_voucher, reverse_posting, run_reconciliation,
    spec_for, validate_voucher,
)
from core.voucher_numbering import create_numbering_indexes, generate_voucher_no
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
    fy_name = fy["name"] if fy else date.today().strftime("%Y-%y")
    doc["fiscal_year"] = fy_name
    doc["voucher_no"] = await generate_voucher_no(
        tenant=tenant,
        parent_type=payload.parent_type,
        voucher_type_id=payload.voucher_type_id,
        fy=fy_name,
        voucher_date=payload.date,
        manual_no=payload.voucher_no,
    )
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
    if v["status"] in ("approved", "posted"):
        return {"ok": True, "status": v["status"], "already": True}
    if v["status"] != "pending":
        raise HTTPException(400, f"Can only approve a pending voucher (this is '{v['status']}')")
    validate_voucher(v)
    # Post FIRST; only advance state if posting succeeds (so a document is never
    # left marked posted without its movements/voucher). Idempotent in the engine.
    posting = await post_voucher(v, user, tenant)
    # Lifecycle: a doc that wrote movements/journal becomes 'posted'; a doc that
    # posts nothing (orders) becomes 'approved'.
    new_status = "posted" if posting.get("posted") else "approved"
    fields = {"status": new_status, "approved_by": user["id"],
              "approved_at": now_iso(), "updated_at": now_iso(), "posting_result": posting}
    if new_status == "posted":
        fields["posted_at"] = now_iso()
        if posting.get("journal_entry_id"):
            fields["voucher_journal_entry_id"] = posting["journal_entry_id"]  # doc→voucher ref
    await db[COLL].update_one(tenant_filter(tenant, {"id": voucher_id}), {"$set": fields})
    new_doc = await db[COLL].find_one(tenant_filter(tenant, {"id": voucher_id}), {"_id": 0})
    await log_audit("UPDATE", COLL, voucher_id, user, old_values=v, new_values=new_doc)
    return {"ok": True, "status": new_status, "posting": posting}


@router.post("/{voucher_id}/reconcile")
async def reconcile_voucher(voucher_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    """Final lifecycle step: posted → reconciled (e.g. matched against bank/GRN)."""
    _require_voucher(user)
    v = await db[COLL].find_one(tenant_filter(tenant, {"id": voucher_id}), {"_id": 0})
    if not v:
        raise HTTPException(404, "Voucher not found")
    if v["status"] == "reconciled":
        return {"ok": True, "status": "reconciled", "already": True}
    if v["status"] != "posted":
        raise HTTPException(400, f"Can only reconcile a posted voucher (this is '{v['status']}')")
    await db[COLL].update_one(tenant_filter(tenant, {"id": voucher_id}),
                             {"$set": {"status": "reconciled", "reconciled_by": user["id"],
                                       "reconciled_at": now_iso(), "updated_at": now_iso()}})
    await log_audit("UPDATE", COLL, voucher_id, user, old_values=v, new_values={**v, "status": "reconciled"})
    return {"ok": True, "status": "reconciled"}


@router.post("/{voucher_id}/reverse")
async def reverse_voucher(voucher_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    """Explicitly reverse a posted/reconciled document: post opposite stock
    movements + a reversing journal, then mark it 'cancelled' with a reversal ref.
    Idempotent — re-reversing is a no-op. Approval (checker) privilege required."""
    _require_approver(user)
    v = await db[COLL].find_one(tenant_filter(tenant, {"id": voucher_id}), {"_id": 0})
    if not v:
        raise HTTPException(404, "Voucher not found")
    if v["status"] not in ("posted", "reconciled"):
        raise HTTPException(400, f"Only posted/reconciled documents can be reversed (this is '{v['status']}')")
    reversal = await reverse_posting(v, user, tenant)
    await db[COLL].update_one(
        tenant_filter(tenant, {"id": voucher_id}),
        {"$set": {"status": "cancelled", "reversed_by": user["id"],
                  "reversed_at": now_iso(), "updated_at": now_iso(), "reversal_result": reversal}},
    )
    new_doc = await db[COLL].find_one(tenant_filter(tenant, {"id": voucher_id}), {"_id": 0})
    await log_audit("UPDATE", COLL, voucher_id, user, old_values=v, new_values=new_doc)
    return {"ok": True, "status": "cancelled", "reversal": reversal}


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


@router.get("/orders/{order_id}/fulfilment")
async def order_fulfilment_status(order_id: str, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    """Fulfilled vs pending qty for an order, computed from the links chain."""
    _require_voucher(user)
    return await order_fulfilment(order_id, tenant)


@router.get("/job-work/reconciliation")
async def job_work_recon(as_of: Optional[str] = None, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    """Out-challan vs material-inward reconciliation with §143 return-window alerts."""
    _require_voucher(user)
    return await job_work_reconciliation(tenant, as_of)


@router.get("/job-work/itc-04")
async def job_work_itc04(from_date: str = Query(...), to_date: str = Query(...),
                         tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    """ITC-04 dataset (goods sent / received back) for a period."""
    _require_voucher(user)
    return await itc04_data(tenant, from_date, to_date)


@router.post("/run-reversing-journals")
async def run_reversing_journals(as_of: Optional[str] = None, tenant: str = Depends(tenant_ctx), user: dict = Depends(get_current_user)):
    """Post the mirror of any reversing journal whose effective date has arrived."""
    _require_voucher(user)
    reversed_count = await auto_reverse_due(tenant, as_of, user)
    return {"ok": True, "reversed": reversed_count}


@router.post("/run-reconciliation")
async def run_reconciliation_endpoint(rules: Optional[list[str]] = None,
                                      tenant: str = Depends(tenant_ctx),
                                      user: dict = Depends(get_current_user)):
    """Auto-reconcile posted documents (orders fully fulfilled, GRNs matched to a
    purchase bill) and advance them posted → reconciled. Idempotent."""
    _require_voucher(user)
    return await run_reconciliation(tenant, user, rules)


async def create_voucher_engine_indexes(database):
    """Compound (tenant_id, ...) indexes for the unified voucher collection."""
    await database[COLL].create_index([("tenant_id", 1), ("id", 1)], unique=True)
    await database[COLL].create_index([("tenant_id", 1), ("parent_type", 1), ("status", 1)])
    await database[COLL].create_index([("tenant_id", 1), ("date", 1)])
    await database[COLL].create_index([("tenant_id", 1), ("effective_date", 1)])
    # Numbering uniqueness per (tenant, voucher_type_id, FY, voucher_no).
    await create_numbering_indexes(database)
    # Duplicate-movement guard: at most one stock-ledger entry per source doc/line.
    # This is the DB-level backstop behind the app's check-then-insert dedup, making
    # duplicate inventory movements impossible even under concurrent posting.
    await database["stock_ledger_entries"].create_index(
        [("source_doc_type", 1), ("source_doc_id", 1), ("stock_item_id", 1),
         ("movement_type", 1), ("batch_id", 1), ("serial_id", 1)],
        unique=True,
        partialFilterExpression={"source_doc_type": "voucher"},
        name="uniq_voucher_stock_movement",
    )
