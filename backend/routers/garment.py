from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional, Literal, Dict
from pydantic import BaseModel

from core import cache
from core.auth_utils import get_current_user, is_admin_role
from core.db import db
from core.utils import (
    now_iso, new_id, next_doc_number,
    crud_create, crud_list, crud_get, crud_update, crud_delete
)

router = APIRouter(prefix="/garment", tags=["Garment Manufacturing"])

def _require_garment(user: dict):
    if (is_admin_role(user.get("role")) or user.get("role") == "accountant"):
        return user
    perms = user.get("module_permissions", [])
    if "inventory" not in perms and "sales" not in perms:
        raise HTTPException(403, "Garment module access required")
    return user

# -------- Pydantic Models --------
class TechPackMaterial(BaseModel):
    item_name: str
    item_type: Literal["FABRIC", "TRIM"]
    consumption: float  # e.g., 1.25 meters per unit
    unit: str = "MTR"
    color: str

class SizeSpec(BaseModel):
    measurement_point: str  # Chest, Length, Sleeve, etc.
    size_charts: Dict[str, float]  # e.g., {"S": 40.0, "M": 42.0, "L": 44.0}

class TechPack(BaseModel):
    style_code: str
    style_name: str
    season: str
    buyer_name: str
    materials: List[TechPackMaterial] = []
    size_specs: List[SizeSpec] = []
    sample_status: Literal["DRAFT", "PROTOTYPE", "FIT_SAMPLE", "APPROVED"] = "DRAFT"
    notes: Optional[str] = None

class SizeColorMatrixItem(BaseModel):
    size: str
    color: str
    quantity: float
    cutting_qty: float = 0.0
    stitching_qty: float = 0.0
    finishing_qty: float = 0.0
    packing_qty: float = 0.0

class BuyerOrder(BaseModel):
    order_number: Optional[str] = None
    buyer_name: str
    style_code: str
    delivery_date: str
    matrix: List[SizeColorMatrixItem]
    status: Literal["PENDING", "CUTTING", "STITCHING", "FINISHING", "PACKING", "COMPLETED"] = "PENDING"
    notes: Optional[str] = None

class MatrixProgressUpdate(BaseModel):
    size: str
    color: str
    step: Literal["cutting", "stitching", "finishing", "packing"]
    quantity_done: float

class FabricTrim(BaseModel):
    item_name: str
    item_type: Literal["FABRIC", "TRIM"]
    roll_number: Optional[str] = None  # Roll ID for fabric
    color: str
    quantity: float  # meters (MTR) or pcs
    unit: str = "MTR"
    location: Optional[str] = None

class StitchingLine(BaseModel):
    line_number: str
    operator_count: int = 15
    target_hourly_qty: float = 20.0
    actual_hourly_qty: float = 18.0
    active_buyer_order_id: Optional[str] = None
    active_style: Optional[str] = None

class ExportDoc(BaseModel):
    shipping_bill_no: str
    date: str
    buyer_name: str
    invoice_number: str
    customs_exchange_rate: float = 83.5
    container_details: str
    clearance_status: Literal["PENDING", "CUSTOMS_CLEARED", "PORT_ARRIVED", "SHIPPED"] = "PENDING"
    checklist: Dict[str, bool] = {"packing_list": False, "shipping_bill": False, "commercial_invoice": False}


# ---------------- Tech Packs Endpoints ----------------

@router.get("/tech-packs")
async def list_tech_packs(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_list("tech_packs", q, ["style_code", "style_name", "buyer_name"])

@router.get("/tech-packs/{tp_id}")
async def get_tech_pack(tp_id: str, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_get("tech_packs", tp_id)

@router.post("/tech-packs")
async def create_tech_pack(payload: TechPack, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_create("tech_packs", payload.model_dump(), user)

@router.put("/tech-packs/{tp_id}")
async def update_tech_pack(tp_id: str, payload: TechPack, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_update("tech_packs", tp_id, payload.model_dump(), user)

@router.delete("/tech-packs/{tp_id}")
async def delete_tech_pack(tp_id: str, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_delete("tech_packs", tp_id, user)


# ---------------- Buyer Orders Endpoints ----------------

@router.get("/buyer-orders")
async def list_buyer_orders(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_list("buyer_orders", q, ["order_number", "buyer_name", "style_code"])

@router.get("/buyer-orders/{order_id}")
async def get_buyer_order(order_id: str, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_get("buyer_orders", order_id)

@router.post("/buyer-orders")
async def create_buyer_order(payload: BuyerOrder, user: dict = Depends(get_current_user)):
    _require_garment(user)
    doc = payload.model_dump()
    doc["order_number"] = await next_doc_number("BORD", "buyer_orders")
    return await crud_create("buyer_orders", doc, user)

@router.put("/buyer-orders/{order_id}")
async def update_buyer_order(order_id: str, payload: BuyerOrder, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_update("buyer_orders", order_id, payload.model_dump(), user)

@router.post("/buyer-orders/{order_id}/progress")
async def update_buyer_order_matrix_progress(order_id: str, payload: MatrixProgressUpdate, user: dict = Depends(get_current_user)):
    """Logs production stage quantities (cutting, stitching, finishing, packing) in size-color matrix."""
    _require_garment(user)
    order = await db.buyer_orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(404, "Buyer Order not found")
        
    matrix = order.get("matrix", [])
    updated = False
    
    # Locate size/color combo and increment progress qty
    for it in matrix:
        if it["size"] == payload.size and it["color"] == payload.color:
            target_field = f"{payload.step}_qty"
            current_val = float(it.get(target_field, 0.0))
            max_val = float(it["quantity"])
            
            # Allow progress up to total ordered quantity
            if current_val + payload.quantity_done > max_val + 1e-5:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot record progress of {payload.quantity_done} for {payload.step.upper()} - exceeds ordered limit of {max_val} (Current progress: {current_val})"
                )
            it[target_field] = current_val + payload.quantity_done
            updated = True
            break
            
    if not updated:
        raise HTTPException(400, f"Size-Color combination '{payload.color}/{payload.size}' not found in Buyer Order matrix")
        
    # Check overall status of order based on packed quantity vs total ordered quantity
    total_ordered = sum(float(it["quantity"]) for it in matrix)
    total_packed = sum(float(it.get("packing_qty", 0.0)) for it in matrix)
    total_cutting = sum(float(it.get("cutting_qty", 0.0)) for it in matrix)
    total_stitching = sum(float(it.get("stitching_qty", 0.0)) for it in matrix)
    
    new_status = "PENDING"
    if total_packed >= total_ordered - 1e-5:
        new_status = "COMPLETED"
    elif total_packed > 0:
        new_status = "PACKING"
    elif total_stitching > 0:
        new_status = "STITCHING"
    elif total_cutting > 0:
        new_status = "CUTTING"
        
    await db.buyer_orders.update_one(
        {"id": order_id},
        {"$set": {"matrix": matrix, "status": new_status, "updated_at": now_iso()}}
    )
    
    return {"status": new_status, "matrix": matrix}

@router.delete("/buyer-orders/{order_id}")
async def delete_buyer_order(order_id: str, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_delete("buyer_orders", order_id, user)


# ---------------- Fabric & Trims (MTR) Endpoints ----------------

@router.get("/fabric-trims")
async def list_fabric_trims(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_list("fabric_trims", q, ["item_name", "roll_number", "color"])

@router.post("/fabric-trims")
async def create_fabric_trim_roll(payload: FabricTrim, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_create("fabric_trims", payload.model_dump(), user)

@router.put("/fabric-trims/{item_id}")
async def update_fabric_trim(item_id: str, payload: FabricTrim, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_update("fabric_trims", item_id, payload.model_dump(), user)

@router.delete("/fabric-trims/{item_id}")
async def delete_fabric_trim(item_id: str, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_delete("fabric_trims", item_id, user)


# ---------------- Production Line Balancing Endpoints ----------------

@router.get("/line-balancing")
async def list_lines(user: dict = Depends(get_current_user)):
    _require_garment(user)
    # Check if lines have been initialized
    lines = await db.stitching_lines.find({}, {"_id": 0}).sort("line_number", 1).to_list(100)
    if not lines:
        # Seed 6 default production lines
        default_lines = [
            {"id": new_id(), "line_number": f"Line {i}", "operator_count": 12 + i, "target_hourly_qty": 20.0 + i*2, "actual_hourly_qty": 18.0 + i, "active_buyer_order_id": None, "active_style": f"Style FG-{100+i}", "created_at": now_iso(), "updated_at": now_iso()}
            for i in range(1, 7)
        ]
        await db.stitching_lines.insert_many(default_lines)
        lines = [{k: v for k, v in l.items() if k != "_id"} for l in default_lines]
    return lines

@router.post("/line-balancing")
async def create_line(payload: StitchingLine, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_create("stitching_lines", payload.model_dump(), user)

@router.put("/line-balancing/{line_id}")
async def update_line(line_id: str, payload: StitchingLine, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_update("stitching_lines", line_id, payload.model_dump(), user)


# ---------------- Export Documentation Endpoints ----------------

@router.get("/export-docs")
async def list_export_docs(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_list("export_docs", q, ["shipping_bill_no", "buyer_name", "invoice_number"])

@router.post("/export-docs")
async def create_export_doc(payload: ExportDoc, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_create("export_docs", payload.model_dump(), user)

@router.put("/export-docs/{doc_id}")
async def update_export_doc(doc_id: str, payload: ExportDoc, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_update("export_docs", doc_id, payload.model_dump(), user)

@router.delete("/export-docs/{doc_id}")
async def delete_export_doc(doc_id: str, user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await crud_delete("export_docs", doc_id, user)


# ---------------- Garment Dashboard Stats ----------------

@router.get("/dashboard")
async def get_garment_dashboard(user: dict = Depends(get_current_user)):
    _require_garment(user)
    return await cache.get_or_set(
        "garment:dashboard", cache.TTL_DASHBOARD, _compute_garment_dashboard
    )


async def _compute_garment_dashboard() -> dict:
    total_orders = await db.buyer_orders.count_documents({})
    completed_orders = await db.buyer_orders.count_documents({"status": "COMPLETED"})
    active_orders = await db.buyer_orders.count_documents({"status": {"$ne": "COMPLETED"}})
    
    # Calculate Line Efficiency
    lines = await db.stitching_lines.find({}, {"_id": 0}).to_list(100)
    avg_efficiency = 0.0
    if lines:
        eff_sum = sum((float(l["actual_hourly_qty"]) / float(l["target_hourly_qty"]) * 100) for l in lines if float(l["target_hourly_qty"]) > 0)
        avg_efficiency = round(eff_sum / len(lines), 2)
        
    # Fabric stock totals
    fabrics = await db.fabric_trims.find({"item_type": "FABRIC"}, {"_id": 0}).to_list(500)
    total_fabric_mtr = sum(float(f["quantity"]) for f in fabrics)
    
    recent_orders = await db.buyer_orders.find({}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)
    
    return {
        "total_orders": total_orders,
        "completed_orders": completed_orders,
        "active_orders": active_orders,
        "average_line_efficiency": avg_efficiency,
        "total_fabric_meters": total_fabric_mtr,
        "recent_buyer_orders": recent_orders
    }
