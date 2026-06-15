"""Inventory endpoints: products, warehouses, stock log, file uploads."""
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, Response

from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.models import Product, Warehouse
from core.storage import APP_NAME, get_object, put_object
from core.utils import (
    crud_create,
    crud_delete,
    crud_get,
    crud_list,
    crud_update,
    new_id,
    now_iso,
)

router = APIRouter(tags=["inventory"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
EXT_BY_TYPE = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
MAX_IMAGE_BYTES = 6 * 1024 * 1024  # 6 MB


# ---------- Warehouses ----------
@router.get("/warehouses")
async def list_warehouses(q: Optional[str] = None, _: dict = Depends(get_current_user)):
    return await crud_list("warehouses", q, ["name", "location", "manager"], sort_field="name")


@router.post("/warehouses")
async def create_warehouse(payload: Warehouse, user: dict = Depends(get_current_user)):
    return await crud_create("warehouses", payload.model_dump(), user=user)


@router.put("/warehouses/{item_id}")
async def update_warehouse(item_id: str, payload: Warehouse, user: dict = Depends(get_current_user)):
    return await crud_update("warehouses", item_id, payload.model_dump(), user=user)


@router.delete("/warehouses/{item_id}")
async def delete_warehouse(item_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("warehouses", item_id, user=user)


# ---------- Products ----------
@router.get("/products")
async def list_products(
    q: Optional[str] = None,
    low_stock: Optional[bool] = False,
    _: dict = Depends(get_current_user),
):
    products = await crud_list("products", q, ["name", "sku", "category"])
    if low_stock:
        products = [p for p in products if p.get("quantity", 0) <= p.get("low_stock_threshold", 0)]
    wh_ids = list({p.get("warehouse_id") for p in products if p.get("warehouse_id")})
    wh_map = {}
    if wh_ids:
        whs = await db.warehouses.find({"id": {"$in": wh_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
        wh_map = {w["id"]: w["name"] for w in whs}
    for p in products:
        p["warehouse_name"] = wh_map.get(p.get("warehouse_id"), "-")
    return products


@router.post("/products")
async def create_product(payload: Product, _: dict = Depends(get_current_user)):
    if await db.products.find_one({"sku": payload.sku}):
        raise HTTPException(status_code=400, detail="SKU already exists")
    return await crud_create("products", payload.model_dump())


@router.put("/products/{item_id}")
async def update_product(item_id: str, payload: Product, _: dict = Depends(get_current_user)):
    if await db.products.find_one({"sku": payload.sku, "id": {"$ne": item_id}}):
        raise HTTPException(status_code=400, detail="SKU already exists")
    return await crud_update("products", item_id, payload.model_dump())


@router.delete("/products/{item_id}")
async def delete_product(item_id: str, _: dict = Depends(require_admin)):
    return await crud_delete("products", item_id)


@router.post("/products/{item_id}/adjust")
async def adjust_stock(
    item_id: str,
    delta: float = Query(...),
    reason: str = Query("manual"),
    user: dict = Depends(get_current_user),
):
    product = await crud_get("products", item_id)
    new_qty = float(product.get("quantity", 0)) + delta
    if new_qty < 0:
        raise HTTPException(status_code=400, detail="Insufficient stock")
    await db.products.update_one({"id": item_id}, {"$set": {"quantity": new_qty, "updated_at": now_iso()}})
    await db.stock_transactions.insert_one({
        "id": new_id(),
        "product_id": item_id,
        "product_name": product.get("name"),
        "delta": delta,
        "balance": new_qty,
        "reason": reason,
        "user_id": user["id"],
        "user_name": user.get("name", ""),
        "created_at": now_iso(),
    })
    return {"ok": True, "new_quantity": new_qty}


# ---------- Stock log ----------
@router.get("/stock-transactions")
async def list_stock_tx(_: dict = Depends(get_current_user)):
    return await db.stock_transactions.find({}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)


# ---------- File uploads (object storage) ----------
@router.post("/uploads/product-image")
async def upload_product_image(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    content_type = file.content_type
    if not content_type or content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, WEBP, GIF are allowed")
    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image must be under 6MB")
    ext = EXT_BY_TYPE.get(content_type, "bin")
    path = f"{APP_NAME}/products/{user['id']}/{uuid.uuid4()}.{ext}"
    result = put_object(path, data, content_type)
    await db.uploaded_files.insert_one({
        "id": new_id(),
        "path": result["path"],
        "size": result.get("size", len(data)),
        "content_type": content_type,
        "original_filename": file.filename,
        "uploaded_by": user["id"],
        "created_at": now_iso(),
    })
    return {"path": result["path"], "size": result.get("size", len(data)), "content_type": content_type}


@router.get("/files/{path:path}")
async def serve_file(path: str, user: dict = Depends(get_current_user)):
    record = await db.uploaded_files.find_one({"path": path}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    data, content_type = get_object(path)
    return Response(content=data, media_type=record.get("content_type", content_type))
