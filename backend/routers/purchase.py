from typing import Optional, List
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException

from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.models import PurchaseOrder, Supplier
from core.product_stock_bridge import resolve_godown_id, resolve_stock_item_id_for_product
from core.stock_ledger import post_entry
from core.utils import (
    calc_totals,
    crud_create,
    crud_delete,
    crud_get,
    crud_list,
    crud_update,
    new_id,
    next_doc_number,
    now_iso,
    log_audit,
)

router = APIRouter(tags=["purchase"])


import re


async def check_gstin_before_save(gstin: Optional[str], data: dict):
    if not gstin:
        return
    gstin = gstin.strip().upper()
    pattern = re.compile(r"^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    if not pattern.match(gstin):
        raise HTTPException(status_code=400, detail="Invalid GSTIN format")
    
    settings = await db.verification_settings.find_one({"id": "global"})
    if settings and settings.get("gst_api_enabled"):
        data["gst_status"] = "ACTIVE"
        data["gstin"] = gstin
        if not data.get("pan_number"):
            data["pan_number"] = gstin[2:12]

# ---------- Suppliers ----------
@router.get("/suppliers")
async def list_suppliers(q: Optional[str] = None, _: dict = Depends(get_current_user)):
    return await crud_list("vendors", q, ["name", "company", "email", "phone"], sort_field="name")


@router.post("/suppliers")
async def create_supplier(payload: Supplier, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    await check_gstin_before_save(data.get("gstin"), data)
    if not data.get("vendor_code"):
        data["vendor_code"] = await next_doc_number("VND", "vendors")
    return await crud_create("vendors", data, user=user)


@router.put("/suppliers/{item_id}")
async def update_supplier(item_id: str, payload: Supplier, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    await check_gstin_before_save(data.get("gstin"), data)
    return await crud_update("vendors", item_id, data, user=user)


@router.delete("/suppliers/{item_id}")
async def delete_supplier(item_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("vendors", item_id, user=user)


# ---------- Purchase Orders ----------
@router.get("/purchase-orders")
async def list_pos(q: Optional[str] = None, _: dict = Depends(get_current_user)):
    return await crud_list("purchase_orders", q, ["po_number", "supplier_name", "status"])


@router.post("/purchase-orders")
async def create_po(payload: PurchaseOrder, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    if not data.get("po_number"):
        data["po_number"] = await next_doc_number("PO", "purchase_orders")
    if data.get("supplier_id") and not data.get("supplier_name"):
        sup = await db.vendors.find_one({"id": data["supplier_id"]}, {"_id": 0, "name": 1})
        if sup:
            data["supplier_name"] = sup["name"]
    data.update(calc_totals(data["items"]))
    return await crud_create("purchase_orders", data, user=user)


@router.put("/purchase-orders/{item_id}")
async def update_po(item_id: str, payload: PurchaseOrder, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    data.update(calc_totals(data["items"]))
    return await crud_update("purchase_orders", item_id, data, user=user)


@router.post("/purchase-orders/{item_id}/receive")
async def receive_po(item_id: str, user: dict = Depends(get_current_user)):
    po = await crud_get("purchase_orders", item_id)
    if po.get("status") == "RECEIVED":
        raise HTTPException(status_code=400, detail="Already received")
    
    old_values = await db.purchase_orders.find_one({"id": item_id}, {"_id": 0})

    items = po.get("items", [])
    # Each line posts its own valuation-priced ledger entry via post_entry —
    # no batch products read needed here anymore (post_entry resolves the
    # item's stock_item_id/rate itself); writes stay sequential regardless,
    # since this app binds one shared AsyncSession per HTTP request and
    # concurrent db.* calls against it raise SQLAlchemy's
    # IllegalStateChangeError (see the same note in mis_reports.py's
    # profitability_report).
    godown_id = await resolve_godown_id(None)
    for item in items:
        if not item.get("product_id"):
            continue
        stock_item_id = await resolve_stock_item_id_for_product(item["product_id"], user)
        await post_entry(
            stock_item_id=stock_item_id, godown_id=godown_id,
            qty=float(item["quantity"]), movement_type="PURCHASE",
            rate=float(item.get("unit_price") or 0),
            source_doc_type="purchase_order", source_doc_id=item_id,
            user=user,
        )
    await db.purchase_orders.update_one(
        {"id": item_id},
        {"$set": {"status": "RECEIVED", "received_at": now_iso(), "updated_at": now_iso()}},
    )

    # NOTE: goods receipt moves stock only. The accounting voucher (Dr Inventory +
    # Input GST, Cr Vendor) is posted by the Purchase Bill, not here — see
    # routers/purchase_v2.py and core.ledger_posting.post_purchase_bill_journal.

    new_values = await db.purchase_orders.find_one({"id": item_id}, {"_id": 0})
    await log_audit("UPDATE", "purchase_orders", item_id, user, old_values=old_values or {}, new_values=new_values or {})

    return {"ok": True}


@router.delete("/purchase-orders/{item_id}")
async def delete_po(item_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("purchase_orders", item_id, user=user)


# ─────────────────────── Goods Receipt Note (GRN) ───────────────────────

class GRNItem(BaseModel):
    product_id: str
    product_name: str
    sku: str
    quantity_ordered: float
    quantity_received: float
    unit: str = "Nos"
    unit_cost: float = 0.0


class GoodsReceiptNote(BaseModel):
    grn_number: Optional[str] = None
    purchase_order_id: str
    purchase_order_number: str
    supplier_id: str
    supplier_name: str
    received_date: str
    received_by: str
    items: List[GRNItem]
    remarks: Optional[str] = None


@router.get("/grn")
async def list_grns(q: Optional[str] = None, _: dict = Depends(get_current_user)):
    # pyrefly: ignore [bad-argument-type]
    return await crud_list("goods_receipt_notes", q, ["grn_number", "purchase_order_number", "supplier_name"])


@router.get("/grn/{item_id}")
async def get_grn(item_id: str, _: dict = Depends(get_current_user)):
    return await crud_get("goods_receipt_notes", item_id)


@router.post("/grn")
async def create_grn(payload: GoodsReceiptNote, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    if not data.get("grn_number"):
        data["grn_number"] = await next_doc_number("GRN", "goods_receipt_notes")
    # Pre-generate the id so the stock-transaction rows below can carry a real
    # source_doc_id link (crud_create() would otherwise assign it only after
    # the stock-posting loop has already run).
    data.setdefault("id", new_id())
    
    # Auto-adjust system stock for each item received. Each line posts its own
    # valuation-priced ledger entry via post_entry; writes stay sequential —
    # this app binds one shared AsyncSession per HTTP request, so concurrent
    # db.* calls against it raise SQLAlchemy's IllegalStateChangeError (see
    # the note in receive_po() above / mis_reports.py's profitability_report).
    grn_items = data.get("items", [])
    godown_id = await resolve_godown_id(None)
    for item in grn_items:
        if not item.get("product_id"):
            continue
        stock_item_id = await resolve_stock_item_id_for_product(item["product_id"], user)
        await post_entry(
            stock_item_id=stock_item_id, godown_id=godown_id,
            qty=float(item["quantity_received"]), movement_type="PURCHASE",
            rate=float(item.get("unit_cost") or 0),
            source_doc_type="grn_v1", source_doc_id=data["id"],
            user=user,
        )

    # Update PO status to RECEIVED
    po_id = data["purchase_order_id"]
    po = await db.purchase_orders.find_one({"id": po_id})
    if po:
        await db.purchase_orders.update_one(
            {"id": po_id},
            {"$set": {"status": "RECEIVED", "received_at": now_iso(), "updated_at": now_iso()}}
        )

    # Goods receipt moves stock only; the accounting voucher is posted by the
    # Purchase Bill (see routers/purchase_v2.py).
    return await crud_create("goods_receipt_notes", data, user=user)
