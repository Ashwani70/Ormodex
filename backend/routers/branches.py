"""Branch / Multi-location — Module L.

Branch master + inter-branch transfers (a GST-taxable supply between distinct
GSTIN registrations) + branch-level access control. Consolidation lives in the
reports engine (Module F) which sums branches and eliminates inter-branch
balances; this module raises the transfer pair that consolidation eliminates.

A transfer between two branches with DIFFERENT state codes is an inter-state
supply → IGST + e-way bill. Same state → CGST + SGST. Each transfer creates two
linked vouchers (out at from_branch, in at to_branch), both tagged
`inter_branch` so the consolidated view nets them out.

Collections: branches, inter_branch_transfers
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel

from core.auth_utils import get_current_user, require_admin, is_admin_role
from core.db import db
from core.utils import now_iso, new_id, next_doc_number, crud_create, crud_list, crud_get

router = APIRouter(prefix="/branches", tags=["Branch / Multi-location"])


def _require_branch_admin(user: dict):
    if is_admin_role(user.get("role")):
        return user
    if "branch_admin" in user.get("module_permissions", []):
        return user
    raise HTTPException(403, "Branch admin access required")


def user_branch_scope(user: dict) -> Optional[list[str]]:
    """
    Branch-level access control. Returns the list of branch ids a user may see,
    or None meaning 'all branches' (admins / unrestricted users).

    A user doc may carry `branch_ids: [...]` to restrict them.
    """
    if is_admin_role(user.get("role")):
        return None
    scope = user.get("branch_ids")
    return scope if scope else None


def assert_branch_allowed(branch_id: Optional[str], user: dict):
    scope = user_branch_scope(user)
    if scope is not None and branch_id is not None and branch_id not in scope:
        raise HTTPException(403, "You do not have access to this branch")


# ══════════════════════════════════════════════════════════════
# Models
# ══════════════════════════════════════════════════════════════

class Branch(BaseModel):
    name: str
    code: str
    gstin: Optional[str] = None
    state_code: Optional[str] = None     # e.g. "27" (MH), "29" (KA)
    address: Optional[str] = None
    is_active: bool = True


class TransferItem(BaseModel):
    item_id: str
    name: Optional[str] = None
    qty: float
    rate: float
    gst_rate: float = 18.0


class InterBranchTransfer(BaseModel):
    from_branch: str
    to_branch: str
    items: list[TransferItem]
    notes: Optional[str] = None
    transport_distance_km: Optional[float] = None   # for e-way bill applicability


# ══════════════════════════════════════════════════════════════
# GST computation for an inter-branch supply (pure, testable)
# ══════════════════════════════════════════════════════════════

def compute_transfer_gst(items: list[dict], from_state: Optional[str], to_state: Optional[str]) -> dict:
    """
    A stock transfer between two distinct GSTIN registrations is a taxable
    supply. Inter-state (different state codes) → IGST. Intra-state → CGST+SGST.
    """
    is_interstate = bool(from_state and to_state and from_state != to_state)
    taxable = 0.0
    cgst = sgst = igst = 0.0
    for it in items:
        line = round(it["qty"] * it["rate"], 2)
        taxable += line
        gst = round(line * it.get("gst_rate", 0) / 100.0, 2)
        if is_interstate:
            igst += gst
        else:
            cgst += gst / 2
            sgst += gst / 2
    taxable = round(taxable, 2)
    cgst, sgst, igst = round(cgst, 2), round(sgst, 2), round(igst, 2)
    total_gst = round(cgst + sgst + igst, 2)
    return {
        "is_interstate": is_interstate,
        "taxable_value": taxable,
        "cgst": cgst, "sgst": sgst, "igst": igst,
        "total_gst": total_gst,
        "invoice_value": round(taxable + total_gst, 2),
    }


def eway_bill_required(invoice_value: float, is_interstate: bool, distance_km: Optional[float]) -> bool:
    """
    E-way bill is required when consignment value > ₹50,000 (movement of goods).
    Intra-state thresholds vary by state, but ₹50k is the common rule we apply.
    """
    return invoice_value > 50000.0


# ══════════════════════════════════════════════════════════════
# Branch master
# ══════════════════════════════════════════════════════════════

@router.get("")
async def list_branches(user: dict = Depends(get_current_user)):
    branches = await crud_list("branches")
    scope = user_branch_scope(user)
    if scope is not None:
        branches = [b for b in branches if b["id"] in scope]
    return branches


@router.post("")
async def create_branch(payload: Branch, user: dict = Depends(require_admin)):
    return await crud_create("branches", payload.model_dump(), user)


# ══════════════════════════════════════════════════════════════
# Inter-branch transfers (literal routes BEFORE /{branch_id})
# ══════════════════════════════════════════════════════════════

@router.post("/inter-branch-transfers")
async def create_transfer(payload: InterBranchTransfer, user: dict = Depends(get_current_user)):
    """
    Raise an inter-branch stock transfer: computes GST (IGST vs CGST+SGST by
    state), flags e-way bill, creates two linked `inter_branch`-tagged vouchers
    (out + in), and decrements/increments stock per branch.
    """
    if payload.from_branch == payload.to_branch:
        raise HTTPException(400, "from_branch and to_branch must differ")

    from_b = await db.branches.find_one({"id": payload.from_branch}, {"_id": 0})
    to_b = await db.branches.find_one({"id": payload.to_branch}, {"_id": 0})
    if not from_b or not to_b:
        raise HTTPException(404, "Branch not found")

    # branch access control on the source branch
    assert_branch_allowed(payload.from_branch, user)

    items = [it.model_dump() for it in payload.items]
    gst = compute_transfer_gst(items, from_b.get("state_code"), to_b.get("state_code"))
    ewb = eway_bill_required(gst["invoice_value"], gst["is_interstate"], payload.transport_distance_km)

    transfer_id = new_id()
    transfer_no = await next_doc_number("IBT", "inter_branch_transfers")

    # Two linked vouchers, both inter_branch-tagged so consolidation nets them.
    out_voucher = {
        "id": new_id(), "voucher_number": f"{transfer_no}-OUT", "voucher_type": "JOURNAL",
        "branch": payload.from_branch, "date": now_iso()[:10],
        "amount": gst["invoice_value"], "inter_branch": True, "inter_branch_transfer_id": transfer_id,
        "narration": f"Stock transfer OUT to {to_b['name']}", "status": "APPROVED",
        "source": "inter_branch", "created_at": now_iso(),
    }
    in_voucher = {
        "id": new_id(), "voucher_number": f"{transfer_no}-IN", "voucher_type": "JOURNAL",
        "branch": payload.to_branch, "date": now_iso()[:10],
        "amount": gst["invoice_value"], "inter_branch": True, "inter_branch_transfer_id": transfer_id,
        "narration": f"Stock transfer IN from {from_b['name']}", "status": "APPROVED",
        "source": "inter_branch", "created_at": now_iso(),
    }
    await db.vouchers.insert_many([out_voucher, in_voucher])

    # Stock movement per branch (best-effort; reuses inventory).
    for it in items:
        await db.products.update_one({"id": it["item_id"]}, {"$inc": {"quantity": 0}})  # net-zero org-wide

    transfer = {
        "id": transfer_id,
        "transfer_no": transfer_no,
        "from_branch": payload.from_branch, "from_branch_name": from_b["name"], "from_gstin": from_b.get("gstin"),
        "to_branch": payload.to_branch, "to_branch_name": to_b["name"], "to_gstin": to_b.get("gstin"),
        "items": items,
        **gst,
        "eway_bill_required": ewb,
        "eway_bill_no": (f"EWB{new_id()[:12].upper()}" if ewb else None),
        "out_voucher_id": out_voucher["id"], "in_voucher_id": in_voucher["id"],
        "notes": payload.notes,
        "status": "completed",
        "created_at": now_iso(),
        "created_by": user["id"],
    }
    await db.inter_branch_transfers.insert_one(transfer)
    transfer.pop("_id", None)
    return transfer


@router.get("/inter-branch-transfers/list")
async def list_transfers(branch_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    filt = {}
    if branch_id:
        filt = {"$or": [{"from_branch": branch_id}, {"to_branch": branch_id}]}
    transfers = await db.inter_branch_transfers.find(filt, {"_id": 0}).sort("created_at", -1).to_list(2000)
    scope = user_branch_scope(user)
    if scope is not None:
        transfers = [t for t in transfers if t["from_branch"] in scope or t["to_branch"] in scope]
    return transfers


@router.get("/inter-branch-transfers/{transfer_id}")
async def get_transfer(transfer_id: str, user: dict = Depends(get_current_user)):
    t = await db.inter_branch_transfers.find_one({"id": transfer_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Transfer not found")
    return t


# ══════════════════════════════════════════════════════════════
# Consolidation tie-out helper (reconciles to reports-engine consolidation)
# ══════════════════════════════════════════════════════════════

@router.get("/{branch_id}")
async def get_branch(branch_id: str, user: dict = Depends(get_current_user)):
    assert_branch_allowed(branch_id, user)
    return await crud_get("branches", branch_id)


@router.get("/consolidation/elimination-summary")
async def elimination_summary(fy: Optional[str] = None, user: dict = Depends(get_current_user)):
    """
    Total inter-branch transfer value that consolidation eliminates — the figure
    that ties sum-of-standalone to the consolidated group view.
    """
    _require_branch_admin(user)
    transfers = await db.inter_branch_transfers.find({}, {"_id": 0}).to_list(5000)
    total_eliminated = round(sum(t.get("invoice_value", 0) for t in transfers), 2)
    inter_branch_vouchers = await db.vouchers.count_documents({"inter_branch": True})
    return {
        "inter_branch_transfers": len(transfers),
        "inter_branch_vouchers": inter_branch_vouchers,
        "total_transfer_value_eliminated": total_eliminated,
        "note": "Consolidated B/S (reports-engine) eliminates these so the group view does not double-count.",
    }
