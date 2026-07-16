"""Inventory endpoints: products, warehouses, stock log, file uploads."""
import logging
import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, Response

from core import cache
from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.models import Product, Warehouse
from core.product_stock_bridge import enrich_products_with_live_stock, resolve_godown_id, resolve_stock_item_id_for_product
from core.stock_ledger import on_hand, post_entry
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

logger = logging.getLogger(__name__)

router = APIRouter(tags=["inventory"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
EXT_BY_TYPE = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
MAX_IMAGE_BYTES = 6 * 1024 * 1024  # 6 MB

# Warehouse documents: images + PDFs. 20 MB cap for scanned agreements/layouts.
ALLOWED_DOC_TYPES = {**{t: EXT_BY_TYPE[t] for t in ALLOWED_IMAGE_TYPES}, "application/pdf": "pdf"}
MAX_DOC_BYTES = 20 * 1024 * 1024  # 20 MB


def _sniff_ok(content_type: str, data: bytes) -> bool:
    """Best-effort magic-byte check so a mislabelled Content-Type can't smuggle
    an unexpected file type past the allow-list. Only validates the types we
    accept; unknown-but-allowed types fall through as OK."""
    sigs = {
        "image/jpeg": [b"\xff\xd8\xff"],
        "image/png": [b"\x89PNG\r\n\x1a\n"],
        "image/gif": [b"GIF87a", b"GIF89a"],
        "application/pdf": [b"%PDF-"],
        # WEBP: "RIFF"...."WEBP"
        "image/webp": [b"RIFF"],
    }
    expected = sigs.get(content_type)
    if not expected:
        return True
    if content_type == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return any(data.startswith(sig) for sig in expected)


# ---------- Warehouses ----------
@router.get("/warehouses")
async def list_warehouses(q: Optional[str] = None, _: dict = Depends(get_current_user)):
    rows = await crud_list("warehouses", q, ["name", "location", "manager"], sort_field="name")
    logger.info("GET /warehouses q=%r → %d rows", q, len(rows))
    return rows


@router.post("/warehouses")
async def create_warehouse(payload: Warehouse, user: dict = Depends(get_current_user)):
    result = await crud_create("warehouses", payload.model_dump(), user=user)
    logger.info("POST /warehouses created id=%s name=%r by user=%s",
                result.get("id"), result.get("name"), user.get("id"))
    return result


@router.put("/warehouses/{item_id}")
async def update_warehouse(item_id: str, payload: Warehouse, user: dict = Depends(get_current_user)):
    result = await crud_update("warehouses", item_id, payload.model_dump(), user=user)
    logger.info("PUT /warehouses/%s updated by user=%s", item_id, user.get("id"))
    return result


@router.delete("/warehouses/{item_id}")
async def delete_warehouse(
    item_id: str,
    force: bool = Query(False, description="Force delete warehouse and cascade delete all its products and stock transactions"),
    user: dict = Depends(require_admin)
):
    if not force:
        # Block deletion if the warehouse is referenced by any product or stock transaction/movement.
        if (
            await db.products.find_one({"warehouse_id": item_id})
            or await db["stock_transactions"].find_one({"godown_id": item_id})
            or await db["stock_transactions"].find_one({"warehouse_id": item_id})
        ):
            raise HTTPException(400, "Cannot delete a warehouse with stock movements")
    else:
        # Clean up related records
        await db.products.delete_many({"warehouse_id": item_id})
        await db["stock_transactions"].delete_many({"godown_id": item_id})
        await db["stock_transactions"].delete_many({"warehouse_id": item_id})

    result = await crud_delete("warehouses", item_id, user=user)
    logger.info("DELETE /warehouses/%s force=%s by user=%s", item_id, force, user.get("id"))
    return result


# ---------- Products ----------
@router.get("/products")
async def list_products(
    q: Optional[str] = None,
    low_stock: Optional[bool] = False,
    _: dict = Depends(get_current_user),
):
    # The Products page loads the default (unfiltered) list on every screen
    # entry, and that list costs ~5-6 sequential cross-region round-trips
    # (products + stock-link resolution + ledger valuation + warehouses). Cache
    # the default list for a short TTL, but GENERATION-GUARD it: the cache key
    # embeds cache.generation("stock"), which any product / stock-item / ledger
    # write bumps (see _mongo_compat + crud_*). So a stock movement orphans the
    # cached list immediately — no stale on-hand qty — while back-to-back reads
    # within the TTL (and no writes) are served from memory. Searches and the
    # low-stock view are varied/less hot, so they bypass the cache.
    cache_key = None
    if not q and not low_stock:
        cache_key = f"products:list:gen{cache.generation('stock')}"
        cached = cache.get(cache_key)
        if cached is not cache._MISS:
            return cached

    products = await crud_list("products", q, ["name", "sku", "category"])
    # Overlay live quantity / cost / GST from the stock-ledger module so the
    # Products page reflects what was saved via purchases/GRN/stock movements,
    # instead of the product's own frozen fields. Done before low-stock filtering
    # so the filter uses the live on-hand quantity.
    products = await enrich_products_with_live_stock(products)
    if low_stock:
        products = [p for p in products if p.get("quantity", 0) <= p.get("low_stock_threshold", 0)]
    wh_ids = list({p.get("warehouse_id") for p in products if p.get("warehouse_id")})
    wh_map = {}
    if wh_ids:
        whs = await db.warehouses.find({"id": {"$in": wh_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
        wh_map = {w["id"]: w["name"] for w in whs}
        godowns = await db.godowns.find({"id": {"$in": wh_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
        for g in godowns:
            wh_map[g["id"]] = g["name"]
    for p in products:
        p["warehouse_name"] = wh_map.get(p.get("warehouse_id"), "-")
    if cache_key is not None:
        cache.set(cache_key, products, cache.TTL_DASHBOARD)
    return products


async def _resolve_category(data: dict) -> dict:
    """Keep category_id (FK) and category (name) in sync on a product payload.

    If a category_id is given, the canonical name is copied from the category
    master. Otherwise, when only a name is given, link it to a matching category
    by name (no auto-create here — categories are managed on the Category page).
    """
    cat_id = data.get("category_id")
    if cat_id:
        cat = await db.product_categories.find_one(
            {"id": cat_id, "is_deleted": {"$ne": True}}, {"_id": 0, "name": 1})
        if not cat:
            raise HTTPException(status_code=400, detail="Selected category not found")
        data["category"] = cat["name"]
    elif data.get("category"):
        match = await db.product_categories.find_one(
            {"name": {"$regex": f"^{re.escape(data['category'].strip())}$", "$options": "i"},
             "is_deleted": {"$ne": True}},
            {"_id": 0, "id": 1})
        data["category_id"] = match["id"] if match else None
    return data


@router.post("/products")
async def create_product(payload: Product, user: dict = Depends(get_current_user)):
    if await db.products.find_one({"sku": payload.sku}):
        raise HTTPException(status_code=400, detail="SKU already exists")
    data = await _resolve_category(payload.model_dump())
    product = await crud_create("products", data)

    # A product created with an opening quantity must have a movement to
    # explain it — otherwise Stock Log shows 0 opening/inward/closing for it
    # forever, and (since the opening_stock migration to post_entry) it also
    # never gets an initial FIFO/LIFO/WA cost layer, which would make every
    # later outward movement mis-valued.
    qty = float(data.get("quantity") or 0)
    if qty > 0:
        stock_item_id = await resolve_stock_item_id_for_product(product["id"], user)
        godown_id = await resolve_godown_id(data.get("warehouse_id"))
        entry = await post_entry(
            stock_item_id=stock_item_id, godown_id=godown_id,
            qty=qty, movement_type="OPENING", rate=float(data.get("cost_price") or 0),
            source_doc_type="product_opening_stock", source_doc_id=product["id"],
            user=user,
        )
        logger.info("product %s: opening stock movement posted qty=%s entry=%s", product["id"], qty, entry["id"])
    return product


@router.put("/products/{item_id}")
async def update_product(item_id: str, payload: Product, _: dict = Depends(get_current_user)):
    if await db.products.find_one({"sku": payload.sku, "id": {"$ne": item_id}}):
        raise HTTPException(status_code=400, detail="SKU already exists")
    data = await _resolve_category(payload.model_dump())
    return await crud_update("products", item_id, data)


@router.delete("/products/{item_id}")
async def delete_product(item_id: str, _: dict = Depends(require_admin)):
    return await crud_delete("products", item_id)


@router.post("/products/{item_id}/adjust")
async def adjust_stock(
    item_id: str,
    delta: float = Query(...),
    reason: str = Query("manual"),
    godown_id: Optional[str] = Query(None),
    rate: Optional[float] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Manual stock adjustment, routed through the valuation-aware stock
    ledger (post_entry) rather than a flat products.quantity write — see
    core/stock_ledger.py. Every adjustment now gets a real FIFO/LIFO/WA/
    Standard-Cost priced ledger entry, not just a Stock Log display row.

    godown_id: falls back to the item's only/first godown when the caller
    doesn't specify one (this endpoint predates warehouse selection and has
    no frontend caller today — see product_stock_bridge for the product ->
    stock_item link). Ambiguous when a product has stock in more than one
    godown; callers that care about a specific location should pass it.
    """
    if delta == 0:
        raise HTTPException(status_code=400, detail="delta must be non-zero")
    product = await crud_get("products", item_id)
    stock_item_id = await resolve_stock_item_id_for_product(item_id, user)

    resolved_godown_id = await resolve_godown_id(godown_id)

    if delta < 0:
        current = await on_hand(stock_item_id, resolved_godown_id)
        if float(current["qty"]) + delta < 0:
            raise HTTPException(status_code=400, detail="Insufficient stock")
    elif rate is None:
        rate = float(product.get("cost_price") or 0)

    entry = await post_entry(
        stock_item_id=stock_item_id, godown_id=resolved_godown_id,
        qty=delta, movement_type="ADJUSTMENT", rate=rate,
        source_doc_type="product_adjust", source_doc_id=item_id,
        user=user,
    )
    logger.info("product %s: manual adjustment posted delta=%s reason=%r entry=%s", item_id, delta, reason, entry["id"])
    new_qty = float((await on_hand(stock_item_id, resolved_godown_id))["qty"])
    return {"ok": True, "new_quantity": new_qty, "entry_id": entry["id"]}


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


@router.post("/uploads/document")
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Generic document/photo upload (images + PDF). Used by the Warehouse module
    for photos, insurance, fire-safety, layout, and agreement attachments."""
    content_type = file.content_type
    if not content_type or content_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, WEBP, GIF, or PDF are allowed")
    data = await file.read()
    if len(data) > MAX_DOC_BYTES:
        raise HTTPException(status_code=400, detail="File must be under 20MB")
    if not _sniff_ok(content_type, data):
        raise HTTPException(status_code=400, detail="File content does not match its declared type")
    ext = ALLOWED_DOC_TYPES.get(content_type, "bin")
    path = f"{APP_NAME}/documents/{user['id']}/{uuid.uuid4()}.{ext}"
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
    return {
        "path": result["path"],
        "size": result.get("size", len(data)),
        "content_type": content_type,
        "name": file.filename,
    }


@router.get("/files/{path:path}")
async def serve_file(path: str, user: dict = Depends(get_current_user)):
    # Authenticated: uploaded files (invoices, payslips, product images) may be
    # sensitive, so a valid session is required. Browser <img> tags send the
    # httponly auth cookie automatically, so in-app images keep working without
    # exposing the token in the URL. Intentionally-public branding (the company
    # logo on the public payslip page) is served by /public/logo below.
    record = await db.uploaded_files.find_one({"path": path}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    data, content_type = get_object(path)
    return Response(content=data, media_type=record.get("content_type", content_type))


@router.get("/public/logo")
async def serve_public_logo():
    """Serve the active company's logo without authentication.

    Company branding is non-sensitive and is shown on unauthenticated pages
    (e.g. the public payslip share link). Only the configured company logo path
    is reachable here — arbitrary file paths are not accepted, so this cannot be
    used to read other uploads.
    """
    company = await db.companies.find_one({}, {"_id": 0, "logo_url": 1})
    logo_path = (company or {}).get("logo_url")
    if not logo_path:
        raise HTTPException(status_code=404, detail="No logo configured")
    record = await db.uploaded_files.find_one({"path": logo_path}, {"_id": 0})
    try:
        data, content_type = get_object(logo_path)
    except Exception:
        raise HTTPException(status_code=404, detail="Logo not found")
    media = (record or {}).get("content_type", content_type)
    # Cacheable: logos change rarely and contain no per-user data.
    return Response(content=data, media_type=media, headers={"Cache-Control": "public, max-age=3600"})
