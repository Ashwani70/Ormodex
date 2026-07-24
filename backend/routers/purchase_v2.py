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

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from core.auth_utils import get_current_user, require_admin, is_admin_role
from core.db import db
from core.pdf import normalize_purchase_doc
from core.ledger_posting import ChartOfAccountsNotSeededError, post_purchase_bill_journal, post_purchase_return_journal
from core.party_ledger import auto_create_party_ledger
from core.product_stock_bridge import resolve_line_stock_item
from routers.debtors_creditors import DocPostIn, post_dc_document, _recalc_party_balance
from core.tenant import resolve_tenant
from core.tracking_validation import validate_tracking_fields
from core.purchase_models import (
    GRNV2, PurchaseBill, PurchaseOrderV2, PurchaseReturn, Vendor, VendorUpdate,
)
from core.stock_ledger import post_entry
from core.utils import crud_create, crud_delete, crud_get, crud_update, log_audit, next_doc_number, now_iso, paginated_list, render_document_pdf
from core import po_numbering as pn
from core.document_numbering import allocate_document_number
from core import cache as _cache

router = APIRouter(prefix="/purchase/v2", tags=["Purchase v2"])


def _require_purchase(user: dict) -> dict:
    if (is_admin_role(user.get("role")) or user.get("role") == "accountant"):
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
async def list_vendors(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                       from_date: Optional[str] = None, to_date: Optional[str] = None,
                       user: dict = Depends(get_current_user)):
    _require_purchase(user)
    # Cache the unfiltered full list (dropdown population) — avoids a 260 ms
    # round-trip on every form that needs the vendor picker.
    if not q and page is None and limit is None and not from_date and not to_date:
        return await _cache.get_or_set(
            "vendors:all", _cache.TTL_REFERENCE,
            lambda: paginated_list("vendors", sort_field="name", sort_dir=1),
        )
    return await paginated_list("vendors", page=page, limit=limit, q=q,
                                 search_fields=["name", "company", "gstin", "email", "phone"],
                                 sort_field="name", sort_dir=1,
                                 from_date=from_date, to_date=to_date, date_field="created_at")


@router.post("/vendors")
async def create_vendor(payload: Vendor, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    data = payload.model_dump()
    if not data.get("vendor_code"):
        data["vendor_code"] = await next_doc_number("VND", "vendors")
    # Auto-link a Chart-of-Accounts ledger (Sundry Creditors) so this vendor
    # can be selected as a Bank Entry party and post through the voucher
    # engine — mirrors the bank-account auto-ledger, see core/party_ledger.py.
    if not data.get("ledger_id"):
        data["ledger_id"] = await auto_create_party_ledger(
            "vendor", data["name"], resolve_tenant(user), user,
            opening_balance=data.get("opening_balance", 0.0),
            gstin=data.get("gstin"), pan=data.get("pan") or data.get("pan_number"),
        )
    result = await crud_create("vendors", data, user=user)
    _cache.invalidate("vendors:all")
    return result


@router.put("/vendors/{vendor_id}")
async def update_vendor(vendor_id: str, payload: VendorUpdate, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    result = await crud_update("vendors", vendor_id, data, user=user)
    _cache.invalidate("vendors:all")
    return result


@router.get("/vendors/{vendor_id}")
async def get_vendor(vendor_id: str, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    return await crud_get("vendors", vendor_id)


@router.delete("/vendors/{vendor_id}")
async def delete_vendor(vendor_id: str, user: dict = Depends(require_admin)):
    result = await crud_delete("vendors", vendor_id, user=user)
    _cache.invalidate("vendors:all")
    return result


# ───────────────────────── Purchase Order ─────────────────────────

def _line_amount(line: dict) -> float:
    base = float(line.get("qty", 0)) * float(line.get("rate", 0))
    return round(base * (1 + float(line.get("gst_rate", 0)) / 100.0), 2)


@router.get("/orders")
async def list_orders(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                      from_date: Optional[str] = None, to_date: Optional[str] = None,
                      user: dict = Depends(get_current_user)):
    _require_purchase(user)
    result = await paginated_list("purchase_orders_v2", page=page, limit=limit, q=q,
                                   search_fields=["po_number", "vendor_name", "status"],
                                   sort_field="created_at", sort_dir=-1,
                                   from_date=from_date, to_date=to_date)
    rows = result["items"] if isinstance(result, dict) else result
    # Backfill missing vendor_name in ONE batched query instead of a per-row
    # find_one+update_one loop — with the DB's ~200ms+ round-trip latency, a
    # page of N unbacked rows used to cost up to 2×N serial round-trips.
    missing_ids = list({po["vendor_id"] for po in rows if not po.get("vendor_name") and po.get("vendor_id")})
    if missing_ids:
        vendors = await db.vendors.find({"id": {"$in": missing_ids}}, {"_id": 0, "id": 1, "name": 1, "company": 1}).to_list(len(missing_ids))
        name_by_id = {v["id"]: (v.get("company") or v.get("name")) for v in vendors}
        for po in rows:
            name = name_by_id.get(po.get("vendor_id"))
            if name and not po.get("vendor_name"):
                po["vendor_name"] = name
                await db.purchase_orders_v2.update_one({"id": po["id"]}, {"$set": {"vendor_name": name}})
    return result


@router.get("/orders/{po_id}")
async def get_order(po_id: str, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    return await crud_get("purchase_orders_v2", po_id)


@router.post("/orders")
async def create_order(payload: PurchaseOrderV2, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    data = payload.model_dump()
    reason = data.pop("po_number_reason", None)
    supplied_number = data.get("po_number")
    # Resolve the PO number per the configured numbering mode + permissions and
    # guarantee uniqueness across the database before persisting.
    data["po_number"] = await pn.allocate_po_number(supplied_number, user)
    data["po_number_locked"] = False
    vendor = await crud_get("vendors", data["vendor_id"])
    data["vendor_name"] = data.get("vendor_name") or vendor.get("company") or vendor.get("name")
    for ln in data["lines"]:
        await resolve_line_stock_item(ln, user)  # product_id → backing stock_item_id
        ln["amount"] = _line_amount(ln)
        ln["received_qty"] = ln.get("received_qty", 0.0)
    data["total"] = round(sum(ln["amount"] for ln in data["lines"]), 2)
    po = await crud_create("purchase_orders_v2", data, user=user)
    # A user-supplied number on create is itself auditable.
    if (supplied_number or "").strip():
        await pn.record_number_change(po["id"], None, po["po_number"], user, reason)
    return po


@router.patch("/orders/{po_id}/status")
async def set_order_status(po_id: str, status: str = Query(...), user: dict = Depends(get_current_user)):
    _require_purchase(user)
    valid = {"DRAFT", "SENT", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED", "CANCELLED"}
    if status not in valid:
        raise HTTPException(400, f"Invalid status. One of {sorted(valid)}")
    await crud_get("purchase_orders_v2", po_id)
    return await crud_update("purchase_orders_v2", po_id, {"status": status}, user=user)


@router.put("/orders/{po_id}")
async def update_order(po_id: str, payload: PurchaseOrderV2, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    existing = await crud_get("purchase_orders_v2", po_id, label="Purchase order")
    # Once any goods have been received against the PO, its lines drive receipt
    # reconciliation — editing them would corrupt the running tally, so block it.
    if any(float(ln.get("received_qty", 0)) > 0 for ln in existing.get("lines", [])):
        raise HTTPException(400, "Cannot edit a purchase order that has received goods. Create a new PO instead.")
    if existing.get("status") in ("RECEIVED", "CLOSED", "CANCELLED"):
        raise HTTPException(400, f"Cannot edit a {existing['status']} purchase order.")

    data = payload.model_dump()
    reason = data.pop("po_number_reason", None)
    vendor = await crud_get("vendors", data["vendor_id"], label="Vendor")
    data["vendor_name"] = data.get("vendor_name") or vendor.get("company") or vendor.get("name")

    # ── PO number edit rules ─────────────────────────────────────────────────
    # The number may change only when the PO is still a Draft AND the number is
    # not locked, and only by a user holding `po_number_edit`. Any change is
    # written to the po_number_audit trail. Otherwise the existing number stands.
    old_number = existing.get("po_number")
    requested = (data.get("po_number") or "").strip()
    number_changed = bool(requested) and requested != old_number
    if number_changed:
        locked = await pn.compute_locked(existing)
        if existing.get("status") != "DRAFT" or locked:
            raise HTTPException(400, "PO number is locked — it can only be changed while the PO is in Draft status.")
        if not pn.has_perm(user, pn.PERM_EDIT):
            raise HTTPException(403, "You do not have permission to change a PO number (po_number_edit required)")
        await pn.ensure_unique(requested, exclude_id=po_id)
        data["po_number"] = requested
    else:
        # po_number is otherwise server-managed; never let the client change it.
        data["po_number"] = old_number
    data["po_number_locked"] = await pn.compute_locked({**existing, **data})
    for ln in data["lines"]:
        await resolve_line_stock_item(ln, user)  # product_id → backing stock_item_id
        ln["amount"] = _line_amount(ln)
        ln["received_qty"] = 0.0
    data["total"] = round(sum(ln["amount"] for ln in data["lines"]), 2)
    data.pop("status", None)  # status changes go through the dedicated endpoint
    updated = await crud_update("purchase_orders_v2", po_id, data, user=user)
    if number_changed:
        await pn.record_number_change(po_id, old_number, requested, user, reason)
    return updated


@router.get("/orders/{po_id}/number-audit")
async def order_number_audit(po_id: str, user: dict = Depends(get_current_user)):
    """PO-number change history (old → new, who, when, why) for the details page."""
    _require_purchase(user)
    await crud_get("purchase_orders_v2", po_id, label="Purchase order")
    return await pn.number_audit_history(po_id)


@router.delete("/orders/{po_id}")
async def delete_order(po_id: str, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    existing = await crud_get("purchase_orders_v2", po_id, label="Purchase order")
    if any(float(ln.get("received_qty", 0)) > 0 for ln in existing.get("lines", [])):
        raise HTTPException(400, "Cannot delete a purchase order that has received goods.")
    grn = await db.goods_receipt_notes_v2.find_one({"purchase_order_id": po_id}, {"_id": 0, "id": 1})
    if grn:
        raise HTTPException(400, "Cannot delete a purchase order linked to a goods receipt note.")
    return await crud_delete("purchase_orders_v2", po_id, user=user)


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
async def list_grns(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                    from_date: Optional[str] = None, to_date: Optional[str] = None,
                    user: dict = Depends(get_current_user)):
    _require_purchase(user)
    result = await paginated_list("goods_receipt_notes_v2", page=page, limit=limit, q=q,
                                  search_fields=["grn_number", "vendor_name"],
                                  sort_field="created_at", sort_dir=-1,
                                  from_date=from_date, to_date=to_date)
    rows = result["items"] if isinstance(result, dict) else result
    # Same batched-lookup fix as list_orders() above — one $in query instead
    # of a per-row find_one+update_one loop.
    missing_ids = list({grn["vendor_id"] for grn in rows if not grn.get("vendor_name") and grn.get("vendor_id")})
    if missing_ids:
        vendors = await db.vendors.find({"id": {"$in": missing_ids}}, {"_id": 0, "id": 1, "name": 1, "company": 1}).to_list(len(missing_ids))
        name_by_id = {v["id"]: (v.get("company") or v.get("name")) for v in vendors}
        for grn in rows:
            name = name_by_id.get(grn.get("vendor_id"))
            if name and not grn.get("vendor_name"):
                grn["vendor_name"] = name
                await db.goods_receipt_notes_v2.update_one({"id": grn["id"]}, {"$set": {"vendor_name": name}})
    for grn in rows:
        if not grn.get("received_date") and grn.get("created_at"):
            grn["received_date"] = grn["created_at"][:10]
    return result


@router.post("/grns")
async def create_grn(payload: GRNV2, user: dict = Depends(get_current_user)):
    """Post a GRN: writes inward StockLedgerEntry rows. PO link is optional."""
    _require_purchase(user)
    data = payload.model_dump()
    await crud_get("godowns", data["godown_id"], label="Warehouse")
    vendor = await crud_get("vendors", data["vendor_id"], label="Vendor")
    data["vendor_name"] = data.get("vendor_name") or vendor.get("company") or vendor.get("name")
    data["received_date"] = data.get("received_date") or date.today().isoformat()
    # AUTO/MANUAL + prefix/FY/branch template per Admin -> Document Numbering
    # (core/document_numbering.py) — replaces the old fixed GRN00001 counter.
    data["grn_number"] = await allocate_document_number("grn", data.get("grn_number"), user)

    # Resolve product_id → backing stock_item_id on every line up front, so the
    # over-receipt check, persisted GRN, and ledger postings all agree.
    for gl in data["lines"]:
        await resolve_line_stock_item(gl, user)
    # Enforce batch/serial/expiry per the stock_item's tracking flags.
    await validate_tracking_fields(data["lines"])

    po = None
    if data.get("purchase_order_id"):
        po = await crud_get("purchase_orders_v2", data["purchase_order_id"], label="Purchase order")

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
    
    # Save the stock_ledger_entry_ids to the database document
    grn = await crud_update("goods_receipt_notes_v2", grn["id"], {"stock_ledger_entry_ids": ledger_entries}, user=user)

    if po:
        await _recompute_po_receipt_status(po["id"], user)
    return grn


@router.delete("/grns/{grn_id}")
async def delete_grn(grn_id: str, user: dict = Depends(get_current_user)):
    """Delete a GRN: reverses its inward stock movement (posts an equal
    outward entry via the same valuation-aware post_entry, rather than
    mutating/deleting the original ledger rows — same pattern as job-work
    challan/receipt deletes) and rolls the linked PO's received_qty back down.
    Blocked if a Purchase Bill already references this GRN (three-way match
    integrity — the bill's Dr Inventory/Cr Vendor posting assumed this stock
    receipt happened)."""
    _require_purchase(user)
    grn = await crud_get("goods_receipt_notes_v2", grn_id, label="GRN")

    # grn_ids is a JSONB array column — {"grn_ids": grn_id} would compile to
    # "grn_ids = '<id>'" (whole-array-equals-scalar, never true) via the Mongo
    # compat shim's plain-value path (core/_mongo_compat.py _to_filter), not
    # an array-contains check. Filter in Python instead, same approach
    # _recompute_po_receipt_status already uses for GRNs-by-PO above.
    all_bills = await db.purchase_bills.find({}, {"_id": 0, "id": 1, "bill_number": 1, "grn_ids": 1}).to_list(5000)
    referencing_bill = next((b for b in all_bills if grn_id in (b.get("grn_ids") or [])), None)
    if referencing_bill:
        raise HTTPException(
            409,
            f"Cannot delete GRN {grn.get('grn_number', grn_id)}: "
            f"Purchase Bill {referencing_bill.get('bill_number', referencing_bill['id'])} already references it. "
            f"Delete or unlink that bill first.",
        )

    lines = grn.get("lines") or []
    if isinstance(lines, str):
        try:
            import json
            lines = json.loads(lines)
        except Exception:
            lines = []
    if not isinstance(lines, list):
        lines = []

    for gl in lines:
        if not isinstance(gl, dict) or not gl.get("stock_item_id"):
            continue
        godown_id = grn.get("godown_id") or gl.get("godown_id") or "MAIN"
        raw_qty = gl.get("qty_received") if gl.get("qty_received") is not None else gl.get("qty", 0)
        try:
            qty_val = float(raw_qty or 0)
        except (ValueError, TypeError):
            qty_val = 0.0

        if qty_val <= 0:
            continue

        await post_entry(
            stock_item_id=gl["stock_item_id"], godown_id=godown_id,
            qty=-abs(qty_val), movement_type="GRN_REVERSAL",
            batch_id=gl.get("batch_id"), serial_id=gl.get("serial_id"),
            source_doc_type="grn_reversal", source_doc_id=grn_id,
            entry_date=date.today().isoformat(), user=user,
        )

    await crud_delete("goods_receipt_notes_v2", grn_id, user=user)

    if grn.get("purchase_order_id"):
        await _recompute_po_receipt_status(grn["purchase_order_id"], user)
    return {"ok": True}


# ───────────────────────── Purchase Bill ─────────────────────────

@router.get("/bills")
async def list_bills(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                     from_date: Optional[str] = None, to_date: Optional[str] = None,
                     user: dict = Depends(get_current_user)):
    _require_purchase(user)
    return await paginated_list("purchase_bills", page=page, limit=limit, q=q,
                                 search_fields=["bill_number", "vendor_invoice_no", "vendor_name"],
                                 sort_field="created_at", sort_dir=-1,
                                 from_date=from_date, to_date=to_date)


@router.post("/bills")
async def create_bill(payload: PurchaseBill, user: dict = Depends(get_current_user)):
    """Post a vendor invoice: creates the accounting voucher (Dr Inventory + Input
    GST, Cr Vendor, Cr TDS). Links to GRN(s)/PO for three-way matching."""
    _require_purchase(user)
    data = payload.model_dump()
    vendor = await crud_get("vendors", data["vendor_id"])
    data["vendor_name"] = data.get("vendor_name") or vendor.get("company") or vendor.get("name")
    if not data.get("bill_number"):
        data["bill_number"] = await next_doc_number("BILL", "purchase_bills")
 
    # Validate any linked GRNs exist (traceability for three-way match).
    for gid in data.get("grn_ids", []):
        await crud_get("goods_receipt_notes_v2", gid)
    if data.get("purchase_order_id"):
        await crud_get("purchase_orders_v2", data["purchase_order_id"])

    for ln in data["lines"]:
        await resolve_line_stock_item(ln, user)  # product_id → backing stock_item_id

    taxable = round(sum(float(l["qty"]) * float(l["rate"]) for l in data["lines"]), 2)
    gst_amount = round(sum(float(l["qty"]) * float(l["rate"]) * float(l.get("gst_rate", 0)) / 100.0 for l in data["lines"]), 2)
    total = round(taxable + gst_amount, 2)
    
    data["taxable"] = taxable
    data["total"] = total
    data["payment_received"] = 0.0
    data["status"] = "UNPAID"
    
    bill = await crud_create("purchase_bills", data, user=user)

    # A Purchase Bill's whole purpose is posting accounting — unlike GRN
    # (whose job is moving stock and must not be blocked by an accounting
    # setup gap), a Bill that can't post its journal has failed at the one
    # thing it's for. Surface that as a real error instead of silently
    # saving a bill with journal_entry_id=None and no accounting effect —
    # the request rolls back (same transaction as the bill insert above),
    # so no half-posted bill is left behind.
    try:
        journal = await post_purchase_bill_journal(
            db, bill_id=bill["id"], bill_number=bill["bill_number"],
            vendor_id=data["vendor_id"], vendor_name=data.get("vendor_name") or "Vendor",
            lines=data["lines"], tds_rate=float(data.get("tds_rate", 0)),
            user=user, entry_date=data.get("vendor_invoice_date"),
        )
    except ChartOfAccountsNotSeededError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await crud_update("purchase_bills", bill["id"],
                      {"journal_entry_id": journal["id"] if journal else None}, user=user)
    bill["journal_entry_id"] = journal["id"] if journal else None

    # Also post to the Debtors & Creditors module (dc_ledger_entries) so its
    # own Supplier Outstanding page reflects this bill — previously only
    # /ledger/party-outstanding (a separate, direct purchase_bills query) did,
    # while /debtors-creditors/outstanding never saw Purchase Bills at all
    # despite a documented integration hook existing for exactly this (see
    # post_dc_document's docstring) that nothing ever called. In-line, same
    # transaction as the rest of this request — not a fire-and-forget hook.
    await post_dc_document(
        DocPostIn(
            doc_type="PURCHASE_BILL", doc_id=bill["id"],
            party_type="vendor", party_id=data["vendor_id"],
            entry_date=data.get("vendor_invoice_date") or now_iso()[:10],
            amount=total,
            narration=f"Purchase bill {bill['bill_number']} from {data.get('vendor_name') or 'Vendor'}",
        ),
        tenant=user.get("tenant_id", "default"), created_by=user.get("id", ""),
    )

    # GRN owns stock movement, Bill owns accounting (see this module's
    # docstring) — a standalone bill with no linked GRN is explicitly
    # allowed, but it means Dr Inventory just posted in the ledger with ZERO
    # matching effect on Stock Log/Stock Summary/on-hand quantity anywhere.
    # Non-blocking — the workflow is intentional for accounting-only entry —
    # but the caller should know, since this is easy to mistake for "stock
    # was received" when it wasn't.
    if not data.get("grn_ids"):
        bill["stock_impact_warning"] = (
            "This bill has no linked GRN — it posted accounting only. "
            "Stock quantity/on-hand was NOT updated anywhere. Create/link a "
            "Goods Receipt Note if the goods were actually received."
        )
    return bill


@router.put("/bills/{bill_id}")
async def update_bill(bill_id: str, payload: PurchaseBill, user: dict = Depends(get_current_user)):
    """Edit a posted vendor invoice. The bill's accounting voucher is reversed and
    re-posted from the new lines/TDS. Blocked once any payment has been recorded,
    because that would desync the payment status / outstanding balance."""
    _require_purchase(user)
    existing = await crud_get("purchase_bills", bill_id, label="Purchase bill")
    if float(existing.get("payment_received", 0)) > 0:
        raise HTTPException(400, "Cannot edit a bill that has payments recorded. Reverse the payment first.")

    data = payload.model_dump()
    vendor = await crud_get("vendors", data["vendor_id"], label="Vendor")
    data["vendor_name"] = data.get("vendor_name") or vendor.get("company") or vendor.get("name")
    # bill_number is server-managed — never let the client change it.
    data["bill_number"] = existing.get("bill_number")

    for gid in data.get("grn_ids", []):
        await crud_get("goods_receipt_notes_v2", gid)
    if data.get("purchase_order_id"):
        await crud_get("purchase_orders_v2", data["purchase_order_id"])

    for ln in data["lines"]:
        await resolve_line_stock_item(ln, user)  # product_id → backing stock_item_id

    taxable = round(sum(float(l["qty"]) * float(l["rate"]) for l in data["lines"]), 2)
    gst_amount = round(sum(float(l["qty"]) * float(l["rate"]) * float(l.get("gst_rate", 0)) / 100.0 for l in data["lines"]), 2)
    data["taxable"] = taxable
    data["total"] = round(taxable + gst_amount, 2)
    data["payment_received"] = 0.0
    data["status"] = "UNPAID"

    # Reverse the old voucher, then re-post a fresh one from the edited bill.
    if existing.get("journal_entry_id"):
        await db.journal_entries.delete_one({"id": existing["journal_entry_id"]})
    await db.journal_entries.delete_many({"source_collection": "purchase_bills", "source_id": bill_id})
    # Same hard reset for the Debtors & Creditors ledger row (post_dc_document
    # is idempotent-by-source-doc-id, so it must be deleted first or the edit
    # wouldn't actually re-price the vendor's outstanding balance).
    await db.dc_ledger_entries.delete_many({"source_doc_id": bill_id, "voucher_type": "PURCHASE_BILL"})

    updated = await crud_update("purchase_bills", bill_id, data, user=user)
    try:
        journal = await post_purchase_bill_journal(
            db, bill_id=bill_id, bill_number=updated["bill_number"],
            vendor_id=data["vendor_id"], vendor_name=data.get("vendor_name") or "Vendor",
            lines=data["lines"], tds_rate=float(data.get("tds_rate", 0)),
            user=user, entry_date=data.get("vendor_invoice_date"),
        )
    except ChartOfAccountsNotSeededError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await crud_update("purchase_bills", bill_id,
                      {"journal_entry_id": journal["id"] if journal else None}, user=user)
    updated["journal_entry_id"] = journal["id"] if journal else None

    await post_dc_document(
        DocPostIn(
            doc_type="PURCHASE_BILL", doc_id=bill_id,
            party_type="vendor", party_id=data["vendor_id"],
            entry_date=data.get("vendor_invoice_date") or now_iso()[:10],
            amount=updated["total"],
            narration=f"Purchase bill {updated['bill_number']} from {data.get('vendor_name') or 'Vendor'}",
        ),
        tenant=user.get("tenant_id", "default"), created_by=user.get("id", ""),
    )
    return updated


@router.delete("/bills/{bill_id}")
async def delete_bill(bill_id: str, user: dict = Depends(require_admin)):
    """Delete a vendor invoice and reverse its accounting voucher. Admin only.
    Blocked once any payment has been recorded."""
    existing = await crud_get("purchase_bills", bill_id, label="Purchase bill")
    if float(existing.get("payment_received", 0)) > 0:
        raise HTTPException(400, "Cannot delete a bill that has payments recorded. Reverse the payment first.")
    if existing.get("journal_entry_id"):
        await db.journal_entries.delete_one({"id": existing["journal_entry_id"]})
    await db.journal_entries.delete_many({"source_collection": "purchase_bills", "source_id": bill_id})
    dc_rows = await db.dc_ledger_entries.find(
        {"source_doc_id": bill_id, "voucher_type": "PURCHASE_BILL"}, {"_id": 0, "tenant_id": 1, "party_id": 1}
    ).to_list(10)
    await db.dc_ledger_entries.delete_many({"source_doc_id": bill_id, "voucher_type": "PURCHASE_BILL"})
    for row in dc_rows:
        await _recalc_party_balance(row.get("tenant_id") or "default", "vendor", row["party_id"])
    return await crud_delete("purchase_bills", bill_id, user=user)


@router.post("/bills/{bill_id}/payment")
async def record_bill_payment(bill_id: str, amount: float = Query(...), user: dict = Depends(get_current_user)):
    _require_purchase(user)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be positive")
    
    bill = await crud_get("purchase_bills", bill_id)
    
    taxable = float(bill.get("taxable") or 0.0)
    total = bill.get("total")
    if total is None:
        gst_amount = sum(float(l["qty"]) * float(l["rate"]) * float(l.get("gst_rate", 0)) / 100.0 for l in bill.get("lines", []))
        total = taxable + gst_amount
    total = round(total, 2)
    
    tds_rate = float(bill.get("tds_rate", 0.0))
    tds = round(taxable * tds_rate / 100.0, 2)
    payable = round(total - tds, 2)
    
    already_paid = float(bill.get("payment_received", 0.0))
    received = min(already_paid + amount, payable)
    status = "PAID" if received >= payable else ("PARTIAL" if received > 0 else "UNPAID")

    old_values = await db.purchase_bills.find_one({"id": bill_id}, {"_id": 0})
    await db.purchase_bills.update_one(
        {"id": bill_id},
        {"$set": {"payment_received": round(received, 2), "status": status, "updated_at": now_iso()}},
    )
    new_values = await db.purchase_bills.find_one({"id": bill_id}, {"_id": 0})
    await log_audit("UPDATE", "purchase_bills", bill_id, user, old_values=old_values or {}, new_values=new_values or {})
    return new_values


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


async def _vendor_doc_for_pdf(doc: dict) -> dict:
    """Attach vendor master + company onto a purchase doc and normalise it onto
    the sales-shaped doc that build_doc_pdf consumes."""
    doc = dict(doc)
    if doc.get("vendor_id"):
        vendor = await db.vendors.find_one({"id": doc["vendor_id"]}, {"_id": 0})
        if vendor:
            doc["vendor"] = vendor
            doc.setdefault("vendor_name", vendor.get("company") or vendor.get("name"))
            doc.setdefault("place_of_supply", vendor.get("state"))
    doc["company"] = await db.companies.find_one({}, {"_id": 0})
    return normalize_purchase_doc(doc, party_field="vendor")


def _pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}.pdf"'},
    )


@router.get("/orders/{po_id}/pdf")
async def order_pdf(po_id: str, user: dict = Depends(get_current_user)):
    """Purchase order PDF, rendered through the shared vendor-document template."""
    _require_purchase(user)
    po = await crud_get("purchase_orders_v2", po_id)
    number = po.get("po_number") or po_id
    doc = await _vendor_doc_for_pdf(po)
    pdf_bytes = await render_document_pdf(
        "PURCHASE ORDER", number, doc,
        party_id=po.get("vendor_id"), party_type="vendor", company=doc.get("company"),
    )
    return _pdf_response(pdf_bytes, number)


@router.get("/bills/{bill_id}/pdf")
async def bill_pdf(bill_id: str, user: dict = Depends(get_current_user)):
    _require_purchase(user)
    bill = await crud_get("purchase_bills", bill_id)
    number = bill.get("bill_number") or bill.get("vendor_invoice_no") or bill_id
    doc = await _vendor_doc_for_pdf(bill)
    pdf_bytes = await render_document_pdf(
        "PURCHASE INVOICE", number, doc,
        party_id=bill.get("vendor_id"), party_type="vendor", company=doc.get("company"),
    )
    return _pdf_response(pdf_bytes, number)


@router.get("/grns/{grn_id}/pdf")
async def grn_pdf(grn_id: str, user: dict = Depends(get_current_user)):
    """Goods Receipt Note PDF, rendered through the shared professional layout.

    GRN lines carry `qty_received` (not the sales `quantity`/`unit_price`), so we
    map them into the shared item shape before rendering. Vendor details are
    auto-fetched live from the master by render_document_pdf.
    """
    _require_purchase(user)
    grn = await crud_get("goods_receipt_notes_v2", grn_id, label="GRN")
    number = grn.get("grn_number") or grn_id
    doc = dict(grn)
    doc["items"] = [{
        "product_name": ln.get("product_name") or ln.get("item_name") or "",
        "sku": ln.get("sku") or ln.get("item_code") or "",
        "hsn_code": ln.get("hsn_code") or ln.get("hsn") or "",
        "quantity": ln.get("qty_received") if ln.get("qty_received") is not None else ln.get("qty", 0),
        "unit_price": ln.get("rate", 0),
        "gst_rate": ln.get("gst_rate", 0),
    } for ln in (grn.get("lines") or [])]
    doc.setdefault("date", grn.get("received_date"))
    doc.setdefault("po_number", None)
    company = await db.companies.find_one({}, {"_id": 0})
    pdf_bytes = await render_document_pdf(
        "GOODS RECEIPT NOTE", number, doc,
        party_id=grn.get("vendor_id"), party_type="vendor", company=company,
    )
    return _pdf_response(pdf_bytes, number)


# ───────────────────────── Purchase Return / Debit Note ─────────────────────────

@router.get("/returns")
async def list_returns(q: Optional[str] = None, page: Optional[int] = None, limit: Optional[int] = None,
                       from_date: Optional[str] = None, to_date: Optional[str] = None,
                       user: dict = Depends(get_current_user)):
    _require_purchase(user)
    return await paginated_list("purchase_returns", page=page, limit=limit, q=q,
                                 search_fields=["debit_note_number", "vendor_name"],
                                 sort_field="created_at", sort_dir=-1,
                                 from_date=from_date, to_date=to_date)


@router.post("/returns")
async def create_return(payload: PurchaseReturn, user: dict = Depends(get_current_user)):
    """Post a purchase return: outward StockLedgerEntry + reversing voucher."""
    _require_purchase(user)
    data = payload.model_dump()
    await crud_get("godowns", data["godown_id"])
    vendor = await crud_get("vendors", data["vendor_id"])
    data["vendor_name"] = data.get("vendor_name") or vendor.get("company") or vendor.get("name")
    data["return_date"] = data.get("return_date") or date.today().isoformat()
    if not data.get("debit_note_number"):
        data["debit_note_number"] = await next_doc_number("DN", "purchase_returns")

    for ln in data["lines"]:
        await resolve_line_stock_item(ln, user)  # product_id → backing stock_item_id
    # Enforce batch/serial/expiry per the stock_item's tracking flags.
    await validate_tracking_fields(data["lines"])

    ret = await crud_create("purchase_returns", data, user=user)

    # Outward stock for each returned line (priced by the valuation engine).
    ledger_entries = []
    for ln in data["lines"]:
        entry = await post_entry(
            stock_item_id=ln["stock_item_id"], godown_id=data["godown_id"],
            qty=-abs(float(ln["qty"])), movement_type="ADJUSTMENT",
            batch_id=ln.get("batch_id"), serial_id=ln.get("serial_id"),
            source_doc_type="purchase_return", source_doc_id=ret["id"],
            entry_date=data["return_date"], user=user,
        )
        ledger_entries.append(entry["id"])

    journal = await post_purchase_return_journal(
        db, return_id=ret["id"], return_number=ret["debit_note_number"],
        vendor_id=data["vendor_id"], vendor_name=data.get("vendor_name") or "Vendor",
        lines=data["lines"], user=user, entry_date=data["return_date"],
    )
    ret = await crud_update(
        "purchase_returns",
        ret["id"],
        {
            "journal_entry_id": journal["id"] if journal else None,
            "stock_ledger_entry_ids": ledger_entries,
        },
        user=user,
    )
    return ret


@router.get("/returns/{return_id}/pdf")
async def return_pdf(return_id: str, user: dict = Depends(get_current_user)):
    """Debit note PDF for a purchase return."""
    _require_purchase(user)
    ret = await crud_get("purchase_returns", return_id)
    number = ret.get("debit_note_number") or return_id
    doc = await _vendor_doc_for_pdf(ret)
    if ret.get("reason"):
        doc.setdefault("notes", f"Reason: {ret['reason']}")
    pdf_bytes = await render_document_pdf(
        "DEBIT NOTE", number, doc,
        party_id=ret.get("vendor_id"), party_type="vendor", company=doc.get("company"),
    )
    return _pdf_response(pdf_bytes, number)


@router.get("/credit-notes/{note_id}/pdf")
async def credit_note_pdf(note_id: str, user: dict = Depends(get_current_user)):
    """Credit note PDF. The CreditNote schema (core.models) is customer-based
    with SalesItem lines, so it renders straight through the invoice template;
    a vendor-keyed fallback remains for any legacy purchase-side credit notes."""
    _require_purchase(user)
    note = await db.credit_notes.find_one({"id": note_id}, {"_id": 0})
    if not note:
        raise HTTPException(status_code=404, detail="Credit note not found")
    number = note.get("credit_note_number") or note.get("number") or note_id
    note = dict(note)
    note["company"] = await db.companies.find_one({}, {"_id": 0})
    # Credit notes may reference either a customer or a vendor; prefer customer.
    if note.get("customer_id"):
        doc = normalize_purchase_doc(note, party_field="customer")
        party_id, party_type = note.get("customer_id"), "customer"
    else:
        doc = await _vendor_doc_for_pdf(note)
        party_id, party_type = note.get("vendor_id"), "vendor"
    pdf_bytes = await render_document_pdf(
        "CREDIT NOTE", number, doc,
        party_id=party_id, party_type=party_type, company=doc.get("company"),
    )
    return _pdf_response(pdf_bytes, number)


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
