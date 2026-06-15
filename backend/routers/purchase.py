from typing import Optional, List
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException

from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.models import PurchaseOrder, Supplier
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
    return await crud_list("suppliers", q, ["name", "company", "email", "phone"], sort_field="name")


@router.post("/suppliers")
async def create_supplier(payload: Supplier, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    await check_gstin_before_save(data.get("gstin"), data)
    if not data.get("vendor_code"):
        data["vendor_code"] = await next_doc_number("VND", "suppliers")
    return await crud_create("suppliers", data, user=user)


@router.put("/suppliers/{item_id}")
async def update_supplier(item_id: str, payload: Supplier, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    await check_gstin_before_save(data.get("gstin"), data)
    return await crud_update("suppliers", item_id, data, user=user)


@router.delete("/suppliers/{item_id}")
async def delete_supplier(item_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("suppliers", item_id, user=user)


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
        sup = await db.suppliers.find_one({"id": data["supplier_id"]}, {"_id": 0, "name": 1})
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

    for item in po.get("items", []):
        prod = await db.products.find_one({"id": item["product_id"]}, {"_id": 0})
        if prod:
            new_qty = float(prod.get("quantity", 0)) + float(item["quantity"])
            await db.products.update_one(
                {"id": item["product_id"]},
                {"$set": {"quantity": new_qty, "updated_at": now_iso()}},
            )
            await db.stock_transactions.insert_one({
                "id": new_id(),
                "product_id": item["product_id"],
                "product_name": item["product_name"],
                "delta": float(item["quantity"]),
                "balance": new_qty,
                "reason": f"Purchase {po.get('po_number')}",
                "user_id": user["id"],
                "user_name": user.get("name", "Unknown"),
                "created_at": now_iso(),
            })
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
    unit: str = "pcs"
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
    return await crud_list("goods_receipt_notes", q, ["grn_number", "purchase_order_number", "supplier_name"])


@router.get("/grn/{item_id}")
async def get_grn(item_id: str, _: dict = Depends(get_current_user)):
    return await crud_get("goods_receipt_notes", item_id)


@router.post("/grn")
async def create_grn(payload: GoodsReceiptNote, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    if not data.get("grn_number"):
        data["grn_number"] = await next_doc_number("GRN", "goods_receipt_notes")
    
    # Auto-adjust system stock for each item received
    for item in data.get("items", []):
        prod = await db.products.find_one({"id": item["product_id"]}, {"_id": 0})
        if prod:
            new_qty = float(prod.get("quantity", 0)) + float(item["quantity_received"])
            await db.products.update_one(
                {"id": item["product_id"]},
                {"$set": {"quantity": new_qty, "updated_at": now_iso()}},
            )
            # Log stock transaction
            await db.stock_transactions.insert_one({
                "id": new_id(),
                "product_id": item["product_id"],
                "product_name": item["product_name"],
                "delta": float(item["quantity_received"]),
                "balance": new_qty,
                "reason": f"Goods Receipt {data.get('grn_number')} (PO-{data.get('purchase_order_number')})",
                "user_id": user["id"],
                "user_name": user.get("name", "Unknown"),
                "created_at": now_iso(),
            })

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
