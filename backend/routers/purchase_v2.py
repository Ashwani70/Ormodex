"""Purchase v2 — Vendor master + PO -> GRN -> Bill -> Return lifecycle.

Mounted at /purchase/v2. Aligned to accrual accounting and the v2 stock ledger:
- GRN posts INWARD StockLedgerEntry rows (stock only, no accounting).
- PurchaseBill posts the accounting voucher via core.ledger_posting.
- PurchaseReturn posts OUTWARD stock + a reversing voucher.

The chain is optional but traceable: standalone GRNs/Bills are allowed, and a
bill links back to its GRN(s) and PO for three-way matching.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.ledger_posting import post_purchase_bill_journal, post_purchase_return_journal
from core.purchase_models import (
    GRNV2, PurchaseBill, PurchaseOrderV2, PurchaseReturn, Vendor, VendorUpdate,
)
from core.stock_ledger import post_entry
from core.utils import crud_create, crud_get, crud_list, crud_update, next_doc_number, now_iso

router = APIRouter(prefix="/purchase/v2", tags=["Purchase v2"])


def _require_purchase(user: dict) -> dict:
    if user.get("role") in ("admin", "accountant"):
        return user
    if "purchase" in (user.get("module_permissions") or []):
        return user
    raise HTTPException(status_code=403, detail="Purchase module access required")


async def _grn_over_receipt_blocked() -> bool:
    """Tenant setting: block (True) or merely warn (False) on over-receipt vs PO."""
    settings = await db.purchase_settings.find_one({"id": "global"}, {"_id": 0})
    return bool((settings or {}).get("block_grn_over_receipt", True))


# ───────────────────────── Vendor master ─────────────────────────

@router.get("/vendors")
async def list_vendors(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    return await crud_list("vendors", q, ["name", "gstin", "email", "phone"], sort_field="name")


@router.post("/vendors")
async def create_vendor(payload: Vendor, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    data = payload.model_dump()
    if not data.get("vendor_code"):
        data["vendor_code"] = await next_doc_number("VND", "vendors")
    return await crud_create("vendors", data, user=user)


@router.put("/vendors/{vendor_id}")
async def update_vendor(vendor_id: str, payload: VendorUpdate, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    return await crud_update("vendors", vendor_id, data, user=user)


@router.get("/vendors/{vendor_id}")
async def get_vendor(vendor_id: str, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    return await crud_get("vendors", vendor_id)


# ───────────────────────── Purchase Order ─────────────────────────

def _line_amount(line: dict) -> float:
    base = float(line.get("qty", 0)) * float(line.get("rate", 0))
    return round(base * (1 + float(line.get("gst_rate", 0)) / 100.0), 2)


@router.get("/orders")
async def list_orders(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    return await crud_list("purchase_orders_v2", q, ["po_number", "vendor_name", "status"])


@router.get("/orders/{po_id}")
async def get_order(po_id: str, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    return await crud_get("purchase_orders_v2", po_id)


@router.post("/orders")
async def create_order(payload: PurchaseOrderV2, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    data = payload.model_dump()
    if not data.get("po_number"):
        data["po_number"] = await next_doc_number("PO", "purchase_orders_v2")
    vendor = await crud_get("vendors", data["vendor_id"])
    data["vendor_name"] = data.get("vendor_name") or vendor.get("name")
    for ln in data["lines"]:
        ln["amount"] = _line_amount(ln)
        ln["received_qty"] = ln.get("received_qty", 0.0)
    data["total"] = round(sum(ln["amount"] for ln in data["lines"]), 2)
    return await crud_create("purchase_orders_v2", data, user=user)


@router.patch("/orders/{po_id}/status")
async def set_order_status(po_id: str, status: str = Query(...), user: dict = Depends(get_current_user)):
    _require_purchase(user)
    valid = {"DRAFT", "SENT", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED", "CANCELLED"}
    if status not in valid:
        raise HTTPException(400, f"Invalid status. One of {sorted(valid)}")
    await crud_get("purchase_orders_v2", po_id)
    return await crud_update("purchase_orders_v2", po_id, {"status": status}, user=user)


# ───────────────────────── Goods Receipt Note ─────────────────────────

async def _recompute_po_receipt_status(po_id: str, user: dict):
    """Roll up received_qty across all GRNs for a PO and set its lifecycle status."""
    po = await db.purchase_orders_v2.find_one({"id": po_id}, {"_id": 0})
    if not po:
        return
    grns = await db.goods_receipt_notes_v2.find({"purchase_order_id": po_id}, {"_id": 0}).to_list(1000)
    received_by_idx: dict[int, float] = {}
    for g in grns:
        for gl in g.get("lines", []):
            idx = gl.get("po_line_index")
            if idx is not None:
                received_by_idx[idx] = received_by_idx.get(idx, 0.0) + float(gl.get("qty_received", 0))

    lines = po.get("lines", [])
    fully = True
    any_received = False
    for i, ln in enumerate(lines):
        ln["received_qty"] = received_by_idx.get(i, 0.0)
        if ln["received_qty"] > 0:
            any_received = True
        if ln["received_qty"] + 1e-9 < float(ln.get("qty", 0)):
            fully = False

    if fully:
        status = "RECEIVED"
    elif any_received:
        status = "PARTIALLY_RECEIVED"
    else:
        status = po.get("status", "SENT")
    await crud_update("purchase_orders_v2", po_id, {"lines": lines, "status": status}, user=user)


@router.get("/grns")
async def list_grns(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    return await crud_list("goods_receipt_notes_v2", q, ["grn_number", "vendor_name"])


@router.post("/grns")
async def create_grn(payload: GRNV2, user: dict = Depends(get_current_user)):
    """Post a GRN: writes inward StockLedgerEntry rows. PO link is optional."""
    _require_purchase(user)
    data = payload.model_dump()
    await crud_get("godowns", data["godown_id"])
    vendor = await crud_get("vendors", data["vendor_id"])
    data["vendor_name"] = data.get("vendor_name") or vendor.get("name")
    data["received_date"] = data.get("received_date") or date.today().isoformat()
    if not data.get("grn_number"):
        data["grn_number"] = await next_doc_number("GRN", "goods_receipt_notes_v2")

    po = None
    if data.get("purchase_order_id"):
        po = await crud_get("purchase_orders_v2", data["purchase_order_id"])

    # Quantity reconciliation: a GRN line cannot exceed the PO's remaining qty.
    if po:
        block = await _grn_over_receipt_blocked()
        warnings = []
        for gl in data["lines"]:
            idx = gl.get("po_line_index")
            if idx is None or idx >= len(po.get("lines", [])):
                continue
            po_line = po["lines"][idx]
            remaining = float(po_line.get("qty", 0)) - float(po_line.get("received_qty", 0))
            if float(gl["qty_received"]) > remaining + 1e-9:
                msg = (f"Line {idx}: receiving {gl['qty_received']} exceeds remaining "
                       f"{round(remaining, 4)} on PO {po.get('po_number')}")
                if block:
                    raise HTTPException(400, msg)
                warnings.append(msg)
        if warnings:
            data["over_receipt_warnings"] = warnings

    # Persist the GRN, then post inward stock for each line.
    grn = await crud_create("goods_receipt_notes_v2", data, user=user)
    ledger_entries = []
    for gl in data["lines"]:
        entry = await post_entry(
            stock_item_id=gl["stock_item_id"], godown_id=data["godown_id"],
            qty=abs(float(gl["qty_received"])), movement_type="PURCHASE",
            rate=float(gl.get("rate", 0)), batch_id=gl.get("batch_id"),
            serial_id=gl.get("serial_id"),
            source_doc_type="grn", source_doc_id=grn["id"],
            entry_date=data["received_date"], user=user,
        )
        ledger_entries.append(entry["id"])
    grn["stock_ledger_entry_ids"] = ledger_entries

    if po:
        await _recompute_po_receipt_status(po["id"], user)
    return grn


# ───────────────────────── Purchase Bill ─────────────────────────

@router.get("/bills")
async def list_bills(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    return await crud_list("purchase_bills", q, ["bill_number", "vendor_invoice_no", "vendor_name"])


@router.post("/bills")
async def create_bill(payload: PurchaseBill, user: dict = Depends(get_current_user)):
    """Post a vendor invoice: creates the accounting voucher (Dr Inventory + Input
    GST, Cr Vendor, Cr TDS). Links to GRN(s)/PO for three-way matching."""
    _require_purchase(user)
    data = payload.model_dump()
    vendor = await crud_get("vendors", data["vendor_id"])
    data["vendor_name"] = data.get("vendor_name") or vendor.get("name")
    if not data.get("bill_number"):
        data["bill_number"] = await next_doc_number("BILL", "purchase_bills")

    # Validate any linked GRNs exist (traceability for three-way match).
    for gid in data.get("grn_ids", []):
        await crud_get("goods_receipt_notes_v2", gid)
    if data.get("purchase_order_id"):
        await crud_get("purchase_orders_v2", data["purchase_order_id"])

    data["taxable"] = round(sum(float(l["qty"]) * float(l["rate"]) for l in data["lines"]), 2)
    bill = await crud_create("purchase_bills", data, user=user)

    journal = await post_purchase_bill_journal(
        db, bill_id=bill["id"], bill_number=bill["bill_number"],
        vendor_id=data["vendor_id"], vendor_name=data["vendor_name"],
        lines=data["lines"], tds_rate=float(data.get("tds_rate", 0)),
        user=user, entry_date=data.get("vendor_invoice_date"),
    )
    await crud_update("purchase_bills", bill["id"],
                      {"journal_entry_id": journal["id"] if journal else None}, user=user)
    bill["journal_entry_id"] = journal["id"] if journal else None
    return bill


@router.get("/bills/{bill_id}/match")
async def three_way_match(bill_id: str, user: dict = Depends(get_current_user)):
    """Compare PO vs GRN vs Bill quantities/values for the linked documents."""
    _require_purchase(user)
    bill = await crud_get("purchase_bills", bill_id)
    bill_qty = round(sum(float(l["qty"]) for l in bill.get("lines", [])), 4)

    grn_qty = 0.0
    for gid in bill.get("grn_ids", []):
        grn = await db.goods_receipt_notes_v2.find_one({"id": gid}, {"_id": 0})
        if grn:
            grn_qty += sum(float(l.get("qty_received", 0)) for l in grn.get("lines", []))

    po_qty = None
    po_id = bill.get("purchase_order_id")
    if po_id:
        po = await db.purchase_orders_v2.find_one({"id": po_id}, {"_id": 0})
        if po:
            po_qty = round(sum(float(l.get("qty", 0)) for l in po.get("lines", [])), 4)

    return {
        "bill_id": bill_id,
        "po_id": po_id,
        "grn_ids": bill.get("grn_ids", []),
        "po_qty": po_qty,
        "grn_qty": round(grn_qty, 4),
        "bill_qty": bill_qty,
        "qty_matched": (po_qty is None or abs((po_qty or 0) - bill_qty) < 1e-6)
                       and (not bill.get("grn_ids") or abs(grn_qty - bill_qty) < 1e-6),
    }


# ───────────────────────── Purchase Return / Debit Note ─────────────────────────

@router.get("/returns")
async def list_returns(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    return await crud_list("purchase_returns", q, ["debit_note_number", "vendor_name"])


@router.post("/returns")
async def create_return(payload: PurchaseReturn, user: dict = Depends(get_current_user)):
    """Post a purchase return: outward StockLedgerEntry + reversing voucher."""
    _require_purchase(user)
    data = payload.model_dump()
    await crud_get("godowns", data["godown_id"])
    vendor = await crud_get("vendors", data["vendor_id"])
    data["vendor_name"] = data.get("vendor_name") or vendor.get("name")
    data["return_date"] = data.get("return_date") or date.today().isoformat()
    if not data.get("debit_note_number"):
        data["debit_note_number"] = await next_doc_number("DN", "purchase_returns")

    ret = await crud_create("purchase_returns", data, user=user)

    # Outward stock for each returned line (priced by the valuation engine).
    ledger_entries = []
    for ln in data["lines"]:
        entry = await post_entry(
            stock_item_id=ln["stock_item_id"], godown_id=data["godown_id"],
            qty=-abs(float(ln["qty"])), movement_type="ADJUSTMENT",
            batch_id=ln.get("batch_id"),
            source_doc_type="purchase_return", source_doc_id=ret["id"],
            entry_date=data["return_date"], user=user,
        )
        ledger_entries.append(entry["id"])
    ret["stock_ledger_entry_ids"] = ledger_entries

    journal = await post_purchase_return_journal(
        db, return_id=ret["id"], return_number=ret["debit_note_number"],
        vendor_id=data["vendor_id"], vendor_name=data["vendor_name"],
        lines=data["lines"], user=user, entry_date=data["return_date"],
    )
    await crud_update("purchase_returns", ret["id"],
                      {"journal_entry_id": journal["id"] if journal else None}, user=user)
    ret["journal_entry_id"] = journal["id"] if journal else None
    return ret


# ───────────────────────── Tenant setting ─────────────────────────

@router.put("/settings")
async def update_settings(block_grn_over_receipt: bool = Query(...), user: dict = Depends(require_admin)):
    """Toggle whether GRN over-receipt vs the PO is blocked (True) or only warned."""
    await db.purchase_settings.update_one(
        {"id": "global"},
        {"$set": {"id": "global", "block_grn_over_receipt": block_grn_over_receipt,
                  "updated_at": now_iso()}},
        upsert=True,
    )
    return {"ok": True, "block_grn_over_receipt": block_grn_over_receipt}
