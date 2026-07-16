"""Manufacturing (deep) router.

Covers:
- Multi-level BOM with scrap%, co-products, by-products, version management
- BOM explosion with cycle detection
- Work Orders: draft→released→in_progress→completed→closed
- Production Journals (raw→WIP→FG) with cost rollup
- Wastage entries (normal absorbed into FG cost; abnormal → expense)
- QC reports
- MRP engine
- Dashboard
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Literal
from pydantic import BaseModel

from core import cache
from core.auth_utils import get_current_user, is_admin_role
from core.db import db
from core.product_stock_bridge import (
    resolve_godown_id, resolve_stock_item_id_for_product, resolve_stock_item_ids_for_products,
)
from core.stock_ledger import post_entry
from core.utils import (
    now_iso, new_id, next_doc_number,
    crud_create, crud_list, crud_get, crud_update, crud_delete,
)

router = APIRouter(prefix="/manufacturing", tags=["Manufacturing"])


def _require_mfg(user: dict):
    if (is_admin_role(user.get("role")) or user.get("role") == "accountant"):
        return user
    perms = user.get("module_permissions", [])
    if "manufacturing" not in perms:
        raise HTTPException(status_code=403, detail="Manufacturing module access required")
    return user


# ══════════════════════════════════════════════════════════════
# Pydantic Models
# ══════════════════════════════════════════════════════════════

class BOMComponent(BaseModel):
    component_item_id: str
    component_item_name: str
    qty_per: float = 1.0          # qty per 1 unit of FG output
    uom: str = "pcs"
    scrap_pct: float = 0.0        # 0–100 — extra qty consumed as scrap
    is_optional: bool = False
    # backward-compat aliases (existing UI sends these)
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None

    def effective_item_id(self) -> str:
        return self.component_item_id or self.product_id or ""

    def effective_item_name(self) -> str:
        return self.component_item_name or self.product_name or ""

    def effective_qty(self) -> float:
        return self.qty_per if self.qty_per else (self.quantity or 1.0)

    def gross_qty(self) -> float:
        """Qty required including scrap allowance."""
        return self.effective_qty() * (1.0 + self.scrap_pct / 100.0)


class CoProduct(BaseModel):
    item_id: str
    item_name: str
    qty_per: float = 0.0
    uom: str = "pcs"
    cost_allocation_pct: float = 0.0   # % of total joint manufacturing cost


class ByProduct(BaseModel):
    item_id: str
    item_name: str
    qty_per: float = 0.0
    uom: str = "pcs"
    realizable_value_per: float = 0.0  # INR credit per unit produced


class RoutingStep(BaseModel):
    step_index: int
    operation_name: str
    workstation: str = ""
    labor_time_mins: float = 0.0
    machine_time_mins: float = 0.0
    cost_per_min: float = 0.0


class BOMModel(BaseModel):
    # Primary identifiers
    finished_product_id: str
    finished_product_name: str
    sku: str = ""
    output_qty: float = 1.0
    uom: str = "pcs"
    version: str = "1.0"
    status: Literal["ACTIVE", "DRAFT", "ARCHIVED"] = "DRAFT"
    valuation_method: Literal["FIFO", "WEIGHTED_AVG"] = "WEIGHTED_AVG"
    # Components / co-products / by-products
    components: List[BOMComponent] = []
    co_products: List[CoProduct] = []
    by_products: List[ByProduct] = []
    # Routing (kept for backward compat)
    routing_steps: List[RoutingStep] = []
    # Legacy field name alias for existing UI
    items: Optional[List[dict]] = None
    estimated_cost: float = 0.0
    notes: Optional[str] = None

    def resolved_components(self) -> List[BOMComponent]:
        """Return components, merging legacy `items` list if `components` is empty."""
        if self.components:
            return self.components
        if self.items:
            result = []
            for it in self.items:
                result.append(BOMComponent(
                    component_item_id=it.get("product_id", ""),
                    component_item_name=it.get("product_name", ""),
                    qty_per=float(it.get("quantity", 1)),
                    uom=it.get("unit", "pcs"),
                    scrap_pct=float(it.get("scrap_pct", 0)),
                ))
            return result
        return []


# ─── Work Order ────────────────────────────────────────────────────────────────

class WOStepProgress(BaseModel):
    step_index: int
    operation_name: str
    status: Literal["PENDING", "IN_PROGRESS", "COMPLETED"] = "PENDING"
    completed_qty: float = 0.0
    machine_hours: float = 0.0
    labor_hours: float = 0.0


class WorkOrder(BaseModel):
    bom_id: str
    product_id: str
    product_name: str
    quantity_planned: float
    quantity_produced: float = 0.0
    godown_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None
    steps: List[WOStepProgress] = []
    status: Literal["DRAFT", "RELEASED", "IN_PROGRESS", "COMPLETED", "CLOSED", "CANCELLED",
                    # Legacy compat
                    "PENDING", "QC_PENDING"] = "DRAFT"
    notes: Optional[str] = None


# ─── Production Journal ────────────────────────────────────────────────────────

class ConsumptionLine(BaseModel):
    item_id: str
    item_name: str
    batch_no: Optional[str] = None
    serial_no: Optional[str] = None
    qty: float
    uom: str = "pcs"
    location_id: Optional[str] = None   # godown / bin
    unit_cost: float = 0.0              # cost per unit (FIFO/WA resolved at save)


class OutputLine(BaseModel):
    item_id: str
    item_name: str
    qty: float
    uom: str = "pcs"
    batch_no: Optional[str] = None
    is_co_product: bool = False
    is_by_product: bool = False
    unit_cost: float = 0.0


class ProductionJournal(BaseModel):
    work_order_id: str
    date: str
    consumption: List[ConsumptionLine] = []
    output: List[OutputLine] = []
    notes: Optional[str] = None


# ─── Wastage Entry ────────────────────────────────────────────────────────────

class WastageEntry(BaseModel):
    work_order_id: Optional[str] = None
    item_id: str
    item_name: str
    qty: float
    uom: str = "pcs"
    reason_code: Literal["NORMAL", "ABNORMAL", "REWORK", "REJECTED"] = "NORMAL"
    valuation: float = 0.0          # total cost value of the waste
    production_journal_id: Optional[str] = None


# ─── QC ──────────────────────────────────────────────────────────────────────

class QCDefect(BaseModel):
    defect_type: str
    quantity: float
    severity: Literal["MINOR", "MAJOR", "CRITICAL"] = "MINOR"


class QCReport(BaseModel):
    work_order_id: str
    product_id: str
    product_name: str
    quantity_checked: float
    quantity_passed: float
    quantity_failed: float
    defects: List[QCDefect] = []
    inspector_name: str
    notes: Optional[str] = None
    status: Literal["PASSED", "FAILED", "PARTIAL"] = "PASSED"


# ══════════════════════════════════════════════════════════════
# BOM helpers
# ══════════════════════════════════════════════════════════════

async def _resolve_bom_for_item(item_id: str, bom_index: Optional[dict[str, dict]] = None) -> Optional[dict]:
    """Return the ACTIVE or latest BOM for a finished good, or None.

    Pass a pre-built `bom_index` (see `_load_bom_index`) to resolve from an
    in-memory dict instead of issuing a query — used by every caller that
    resolves BOMs in a loop or in BOM-explosion recursion (was an N+1: up to
    2 queries per component, compounding at every recursion level). Falls
    back to a live per-item lookup when no index is supplied.
    """
    if bom_index is not None:
        return bom_index.get(item_id)
    bom = await db.boms.find_one(
        {"finished_product_id": item_id, "status": "ACTIVE"},
        {"_id": 0},
        sort=[("version", -1)],
    )
    if not bom:
        bom = await db.boms.find_one(
            {"$or": [
                {"finished_product_id": item_id},
                {"finished_good_item_id": item_id},
            ]},
            {"_id": 0},
            sort=[("version", -1)],
        )
    return bom


async def _load_bom_index() -> dict[str, dict]:
    """Load every BOM once and index by finished_product_id, replicating
    _resolve_bom_for_item's own precedence (ACTIVE + highest version wins;
    otherwise highest version of any status). The BOM table is small and
    bounded (one row per finished-good version, not per transaction), so one
    full read here is far cheaper than the up-to-2-queries-per-lookup this
    replaces across an entire BOM explosion (which can call it once per
    component per recursion level).
    """
    boms = await db.boms.find({}, {"_id": 0}).sort("version", -1).to_list(20000)
    index: dict[str, dict] = {}
    for bom in boms:
        fg_id = bom.get("finished_product_id") or bom.get("finished_good_item_id")
        if not fg_id:
            continue
        existing = index.get(fg_id)
        if existing is None:
            index[fg_id] = bom
        elif bom.get("status") == "ACTIVE" and existing.get("status") != "ACTIVE":
            # Sorted by version desc, so the first ACTIVE one seen is the
            # highest-version ACTIVE BOM — matches _resolve_bom_for_item's
            # "ACTIVE preferred" rule even though we're scanning all statuses.
            index[fg_id] = bom
    return index


def _bom_components(bom: dict) -> list:
    """Return normalized component list from a BOM doc (handles both old and new shape)."""
    comps = bom.get("components") or []
    if not comps:
        comps = bom.get("items") or []
    return comps


async def _fetch_products_by_ids(product_ids: list[str]) -> dict[str, dict]:
    """Batch-read every product in ONE query instead of a find_one per BOM
    component/consumption/output line — work-order completion and
    production-journal posting used to re-query the same product once per
    validation pass and once per write pass (2-3x the line count in
    round-trips). Callers loop sequentially over the returned dict for
    writes — this app binds one shared AsyncSession per request, so the
    writes themselves can't be asyncio.gather'd (see the shared-session
    note in purchase.py / job_work.py)."""
    ids = list({pid for pid in product_ids if pid})
    if not ids:
        return {}
    prods = await db.products.find({"id": {"$in": ids}}).to_list(len(ids))
    return {p["id"]: p for p in prods}


async def _explode_bom(
    bom: dict,
    target_qty: float,
    ancestor_ids: set,
    depth: int = 0,
    bom_index: Optional[dict[str, dict]] = None,
) -> dict:
    """
    Recursively explode a BOM to raw requirements.
    Returns {item_id: {item_name, uom, required_qty, depth}} plus a list of
    sub-assembly BOMs found.  Raises 400 on a cycle.

    Pass `bom_index` (see `_load_bom_index`) to resolve every component's
    possible sub-BOM from one pre-loaded in-memory dict instead of a query
    per component per recursion level (was an N+1 that compounds with BOM
    depth). Top-level callers should load the index once and pass it through;
    it's optional only so a single ad-hoc resolution still works standalone.
    """
    if depth > 10:
        raise HTTPException(400, "BOM recursion depth exceeded 10 levels")

    fg_id = bom.get("finished_product_id") or bom.get("finished_good_item_id", "")
    output_qty = float(bom.get("output_qty") or 1.0)
    factor = target_qty / output_qty if output_qty else target_qty

    raw: dict = {}
    components = _bom_components(bom)

    for comp in components:
        c_id = comp.get("component_item_id") or comp.get("product_id") or ""
        c_name = comp.get("component_item_name") or comp.get("product_name") or ""
        qty_per = float(comp.get("qty_per") or comp.get("quantity") or 1.0)
        scrap_pct = float(comp.get("scrap_pct", 0.0))
        uom = comp.get("uom") or comp.get("unit") or "pcs"

        gross_qty_per = qty_per * (1.0 + scrap_pct / 100.0)
        needed = gross_qty_per * factor

        # Check if this component itself is a sub-assembly
        if c_id in ancestor_ids:
            raise HTTPException(
                400,
                f"Cyclic BOM detected: item '{c_name}' ({c_id}) appears in its own ancestry",
            )

        sub_bom = await _resolve_bom_for_item(c_id, bom_index)
        if sub_bom:
            # Recurse — component is itself a manufactured FG
            sub_raw = await _explode_bom(
                sub_bom,
                target_qty=needed,
                ancestor_ids=ancestor_ids | {fg_id},
                depth=depth + 1,
                bom_index=bom_index,
            )
            for sid, sv in sub_raw.items():
                if sid in raw:
                    raw[sid]["required_qty"] += sv["required_qty"]
                else:
                    raw[sid] = {**sv, "depth": depth + 1}
        else:
            # Leaf — true raw material
            if c_id in raw:
                raw[c_id]["required_qty"] += needed
            else:
                raw[c_id] = {
                    "item_id": c_id,
                    "item_name": c_name,
                    "uom": uom,
                    "required_qty": needed,
                    "scrap_pct": scrap_pct,
                    "depth": depth,
                }

    return raw


async def _weighted_avg_cost(item_id: str) -> float:
    """Approximate weighted-average unit cost from products collection."""
    prod = await db.products.find_one({"id": item_id}, {"_id": 0, "cost_price": 1})
    return float(prod.get("cost_price", 0)) if prod else 0.0


# ══════════════════════════════════════════════════════════════
# BOM Endpoints
# ══════════════════════════════════════════════════════════════

@router.get("/boms")
@router.get("/bom")
async def list_boms(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_mfg(user)
    return await crud_list("boms", q, ["finished_product_name", "sku", "version"])


@router.get("/bom/{bom_id}")
async def get_bom(bom_id: str, user: dict = Depends(get_current_user)):
    _require_mfg(user)
    return await crud_get("boms", bom_id)


@router.post("/bom")
async def create_bom(payload: BOMModel, user: dict = Depends(get_current_user)):
    _require_mfg(user)

    # Cycle detection: make sure this FG's components don't lead back to
    # itself. bom_index is loaded ONCE (all BOMs, small/bounded table) and
    # reused for every component's sub-BOM lookup + the recursive explosion
    # below — was an N+1 (up to 2 queries per component, compounding with
    # BOM depth inside _explode_bom's recursion).
    bom_index = await _load_bom_index()
    ancestors: set = {payload.finished_product_id}
    for comp in payload.resolved_components():
        cid = comp.effective_item_id()
        if cid == payload.finished_product_id:
            raise HTTPException(400, "Component cannot be the same as the finished good (cycle)")
        sub_bom = await _resolve_bom_for_item(cid, bom_index)
        if sub_bom:
            try:
                await _explode_bom(sub_bom, 1.0, ancestors, bom_index=bom_index)
            except HTTPException:
                raise HTTPException(400, f"Adding this component creates a cyclic BOM via '{comp.effective_item_name()}'")

    doc = payload.model_dump()

    # Normalize legacy items → components
    if not doc.get("components") and doc.get("items"):
        doc["components"] = [
            {
                "component_item_id": it.get("product_id", ""),
                "component_item_name": it.get("product_name", ""),
                "qty_per": float(it.get("quantity", 1)),
                "uom": it.get("unit", "pcs"),
                "scrap_pct": float(it.get("scrap_pct", 0)),
                "is_optional": False,
            }
            for it in (doc["items"] or [])
        ]

    # Estimate cost — batch-read every component's product ONCE instead of
    # _weighted_avg_cost's find_one per component (was an N+1).
    components_by_id = await _fetch_products_by_ids(
        [comp.effective_item_id() for comp in payload.resolved_components()]
    )
    total_cost = 0.0
    for comp in payload.resolved_components():
        unit_cost = float((components_by_id.get(comp.effective_item_id()) or {}).get("cost_price", 0))
        total_cost += unit_cost * comp.gross_qty()
    for step in (payload.routing_steps or []):
        total_cost += (step.labor_time_mins + step.machine_time_mins) * step.cost_per_min
    doc["estimated_cost"] = round(total_cost, 2)

    return await crud_create("boms", doc, user)


@router.put("/bom/{bom_id}")
async def update_bom(bom_id: str, payload: BOMModel, user: dict = Depends(get_current_user)):
    _require_mfg(user)
    doc = payload.model_dump()

    # Normalize legacy items → components
    if not doc.get("components") and doc.get("items"):
        doc["components"] = [
            {
                "component_item_id": it.get("product_id", ""),
                "component_item_name": it.get("product_name", ""),
                "qty_per": float(it.get("quantity", 1)),
                "uom": it.get("unit", "pcs"),
                "scrap_pct": float(it.get("scrap_pct", 0)),
                "is_optional": False,
            }
            for it in (doc["items"] or [])
        ]

    # Batch-read every component's product ONCE instead of _weighted_avg_cost's
    # find_one per component (was an N+1).
    components_by_id = await _fetch_products_by_ids(
        [comp.effective_item_id() for comp in payload.resolved_components()]
    )
    total_cost = 0.0
    for comp in payload.resolved_components():
        unit_cost = float((components_by_id.get(comp.effective_item_id()) or {}).get("cost_price", 0))
        total_cost += unit_cost * comp.gross_qty()
    for step in (payload.routing_steps or []):
        total_cost += (step.labor_time_mins + step.machine_time_mins) * step.cost_per_min
    doc["estimated_cost"] = round(total_cost, 2)

    return await crud_update("boms", bom_id, doc, user)


@router.delete("/bom/{bom_id}")
async def delete_bom(bom_id: str, user: dict = Depends(get_current_user)):
    _require_mfg(user)
    return await crud_delete("boms", bom_id, user)


@router.get("/bom/{bom_id}/explode")
async def explode_bom(
    bom_id: str,
    qty: float = Query(1.0, gt=0, description="Target output quantity"),
    user: dict = Depends(get_current_user),
):
    """
    Multi-level BOM explosion.
    Returns the flat list of raw material requirements (with scrap applied at
    each level) needed to produce `qty` units of the finished good.
    Raises 400 if a cyclic dependency is found.
    """
    _require_mfg(user)
    bom = await crud_get("boms", bom_id)

    fg_id = bom.get("finished_product_id") or bom.get("finished_good_item_id", "")
    bom_index = await _load_bom_index()
    raw_map = await _explode_bom(bom, target_qty=qty, ancestor_ids={fg_id}, bom_index=bom_index)

    # Enrich with current stock levels
    result = []
    item_ids = list(raw_map.keys())
    products_by_id = {}
    if item_ids:
        prods = await db.products.find(
            {"id": {"$in": item_ids}},
            {"_id": 0, "id": 1, "quantity": 1, "cost_price": 1}
        ).to_list(len(item_ids))
        products_by_id = {p["id"]: p for p in prods}

    for item_id, req in raw_map.items():
        prod = products_by_id.get(item_id)
        on_hand = float(prod.get("quantity", 0)) if prod else 0.0
        unit_cost = float(prod.get("cost_price", 0)) if prod else 0.0
        result.append({
            **req,
            "on_hand": on_hand,
            "shortage": max(0.0, req["required_qty"] - on_hand),
            "unit_cost": unit_cost,
            "total_cost": round(req["required_qty"] * unit_cost, 2),
        })

    result.sort(key=lambda x: (x["depth"], x["item_name"]))
    return {
        "bom_id": bom_id,
        "finished_product": bom.get("finished_product_name", ""),
        "target_qty": qty,
        "raw_requirements": result,
        "total_material_cost": round(sum(r["total_cost"] for r in result), 2),
    }


# ══════════════════════════════════════════════════════════════
# Work Order Endpoints
# ══════════════════════════════════════════════════════════════

@router.get("/work-orders")
async def list_work_orders(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_mfg(user)
    return await crud_list("work_orders", q, ["product_name", "wo_number"])


@router.get("/work-orders/{wo_id}")
async def get_work_order(wo_id: str, user: dict = Depends(get_current_user)):
    _require_mfg(user)
    return await crud_get("work_orders", wo_id)


@router.post("/work-orders")
async def create_work_order(payload: WorkOrder, user: dict = Depends(get_current_user)):
    _require_mfg(user)
    doc = payload.model_dump()
    doc["wo_number"] = await next_doc_number("WO", "work_orders")
    doc["status"] = "DRAFT"

    # Auto-populate routing steps from BOM if not provided
    if not doc.get("steps"):
        bom = await db.boms.find_one({"id": doc["bom_id"]})
        if bom:
            doc["steps"] = [
                {
                    "step_index": s["step_index"],
                    "operation_name": s["operation_name"],
                    "status": "PENDING",
                    "completed_qty": 0.0,
                    "machine_hours": 0.0,
                    "labor_hours": 0.0,
                }
                for s in (bom.get("routing_steps") or [])
            ]

    return await crud_create("work_orders", doc, user)


@router.put("/work-orders/{wo_id}")
async def update_work_order(wo_id: str, payload: WorkOrder, user: dict = Depends(get_current_user)):
    _require_mfg(user)
    return await crud_update("work_orders", wo_id, payload.model_dump(), user)


@router.post("/work-orders/{wo_id}/release")
async def release_work_order(wo_id: str, user: dict = Depends(get_current_user)):
    """Draft → Released. Locks the BOM version and reserves material."""
    _require_mfg(user)
    wo = await crud_get("work_orders", wo_id)
    if wo["status"] not in ("DRAFT", "PENDING"):
        raise HTTPException(400, f"Cannot release Work Order in status '{wo['status']}'")
    return await crud_update("work_orders", wo_id, {"status": "RELEASED"}, user)


@router.post("/work-orders/{wo_id}/start")
async def start_work_order(wo_id: str, user: dict = Depends(get_current_user)):
    _require_mfg(user)
    wo = await crud_get("work_orders", wo_id)
    if wo["status"] not in ("RELEASED", "PENDING"):
        raise HTTPException(400, f"Cannot start Work Order in status '{wo['status']}'")
    return await crud_update("work_orders", wo_id, {"status": "IN_PROGRESS", "start_date": now_iso()}, user)


@router.post("/work-orders/{wo_id}/complete")
async def complete_work_order(wo_id: str, user: dict = Depends(get_current_user)):
    """
    IN_PROGRESS → QC_PENDING (legacy) or COMPLETED.
    Deducts BOM ingredients from inventory and adds FG stock.
    All stock movements are sequential; on any failure the endpoint returns an
    error without partial writes where possible.
    """
    _require_mfg(user)
    wo = await crud_get("work_orders", wo_id)
    if wo["status"] != "IN_PROGRESS":
        raise HTTPException(400, "Only In Progress Work Orders can be completed")

    bom = await db.boms.find_one({"id": wo["bom_id"]})
    if not bom:
        raise HTTPException(400, f"BOM {wo['bom_id']} not found")

    components = _bom_components(bom)
    qty_factor = float(wo["quantity_planned"])

    # Batch-read every component product ONCE — the validate pass and the
    # deduct pass used to each re-query per component (2x round-trips per
    # component). Neither pass writes before both have read, so one shared
    # snapshot is correct; the deduct pass below tracks a running quantity
    # per product_id so two components referencing the same product (rare
    # but not disallowed by the BOM shape) still stack their deductions.
    component_ids = [comp.get("component_item_id") or comp.get("product_id") or "" for comp in components]
    products_by_id = await _fetch_products_by_ids(component_ids)

    # 1. Pre-validate stock for all components
    for comp in components:
        c_id = comp.get("component_item_id") or comp.get("product_id") or ""
        c_name = comp.get("component_item_name") or comp.get("product_name") or ""
        qty_per = float(comp.get("qty_per") or comp.get("quantity") or 1.0)
        scrap_pct = float(comp.get("scrap_pct", 0.0))
        needed = qty_per * (1.0 + scrap_pct / 100.0) * qty_factor

        prod = products_by_id.get(c_id)
        if not prod:
            raise HTTPException(400, f"Component '{c_name}' not found in inventory")
        available = float(prod.get("quantity", 0))
        if needed > available + 1e-6:
            raise HTTPException(
                400,
                f"Insufficient stock for '{c_name}'. Need {needed:.4f}, available {available:.4f}",
            )

    # 2. Deduct component stock — each posts its own valuation-priced ledger
    # entry via post_entry rather than a flat products.quantity write, so raw
    # material consumption now gets real FIFO/LIFO/WA/Standard-Cost costing.
    # No godown is captured on a BOM component today, so this resolves the
    # tenant's default the same way the other migrated v1 flows do (see
    # core.product_stock_bridge.resolve_godown_id). stock_item_id resolution
    # for every component + the FG is batched in ONE call rather than resolved
    # per-line inside the loop (was an N+1 — up to 3 queries per component).
    godown_id = await resolve_godown_id(None)
    all_ids = [comp.get("component_item_id") or comp.get("product_id") or "" for comp in components]
    all_ids.append(wo["product_id"])
    stock_item_by_product = await resolve_stock_item_ids_for_products(all_ids, user)

    for comp in components:
        c_id = comp.get("component_item_id") or comp.get("product_id") or ""
        qty_per = float(comp.get("qty_per") or comp.get("quantity") or 1.0)
        scrap_pct = float(comp.get("scrap_pct", 0.0))
        needed = qty_per * (1.0 + scrap_pct / 100.0) * qty_factor

        await post_entry(
            stock_item_id=stock_item_by_product[c_id], godown_id=godown_id,
            qty=-needed, movement_type="MANUFACTURING",
            source_doc_type="work_order_consumption", source_doc_id=wo["id"],
            user=user,
        )

    # 3. Add FG stock
    fg = await db.products.find_one({"id": wo["product_id"]})
    if fg:
        await post_entry(
            stock_item_id=stock_item_by_product[wo["product_id"]], godown_id=godown_id,
            qty=float(wo["quantity_planned"]), movement_type="MANUFACTURING",
            rate=float(fg.get("cost_price") or 0),
            source_doc_type="work_order_output", source_doc_id=wo["id"],
            user=user,
        )

    return await crud_update(
        "work_orders", wo_id,
        {"status": "COMPLETED", "end_date": now_iso(), "quantity_produced": float(wo["quantity_planned"])},
        user,
    )


@router.post("/work-orders/{wo_id}/close")
async def close_work_order(wo_id: str, user: dict = Depends(get_current_user)):
    """COMPLETED → CLOSED (final archival state)."""
    _require_mfg(user)
    wo = await crud_get("work_orders", wo_id)
    if wo["status"] not in ("COMPLETED", "QC_PENDING"):
        raise HTTPException(400, f"Cannot close Work Order in status '{wo['status']}'")
    return await crud_update("work_orders", wo_id, {"status": "CLOSED"}, user)


@router.delete("/work-orders/{wo_id}")
async def delete_work_order(wo_id: str, user: dict = Depends(get_current_user)):
    _require_mfg(user)
    wo = await crud_get("work_orders", wo_id)
    if wo["status"] not in ("DRAFT", "PENDING", "CANCELLED"):
        raise HTTPException(400, "Only DRAFT or CANCELLED Work Orders can be deleted")
    return await crud_delete("work_orders", wo_id, user)


# ══════════════════════════════════════════════════════════════
# Production Journal Endpoints
# ══════════════════════════════════════════════════════════════

@router.get("/production-journals")
async def list_production_journals(
    work_order_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require_mfg(user)
    filt = {}
    if work_order_id:
        filt["work_order_id"] = work_order_id
    return await crud_list("production_journals", filt=filt)


@router.get("/production-journals/{journal_id}")
async def get_production_journal(journal_id: str, user: dict = Depends(get_current_user)):
    _require_mfg(user)
    return await crud_get("production_journals", journal_id)


@router.post("/production-journals")
async def create_production_journal(
    payload: ProductionJournal,
    user: dict = Depends(get_current_user),
):
    """
    Post a production journal: consume raw materials → produce FG / co-products.
    Stock movements are validated first then applied sequentially.
    Wastage beyond BOM scrap_pct is flagged as ABNORMAL automatically.
    """
    _require_mfg(user)

    wo = await crud_get("work_orders", payload.work_order_id)
    if wo["status"] not in ("RELEASED", "IN_PROGRESS"):
        raise HTTPException(400, f"Cannot post journal against WO in status '{wo['status']}'")

    # Batch-read every consumption-line product ONCE — the validate, cost-
    # resolution, and deduct passes below used to each re-query per line (up
    # to 3x round-trips per line). None of the first two passes write, so one
    # shared snapshot is correct for all three; the deduct pass tracks a
    # running quantity per product_id so duplicate item_ids across lines
    # still stack their deductions instead of racing on a stale snapshot.
    consumption_products = await _fetch_products_by_ids([line.item_id for line in payload.consumption])

    # ── 1. Pre-validate consumption stock ──────────────────────────────────
    for line in payload.consumption:
        prod = consumption_products.get(line.item_id)
        if not prod:
            raise HTTPException(400, f"Item '{line.item_name}' ({line.item_id}) not found")
        if float(prod.get("quantity", 0)) < line.qty - 1e-6:
            raise HTTPException(
                400,
                f"Insufficient stock for '{line.item_name}'. Available: {prod.get('quantity', 0)}, need {line.qty}",
            )

    doc = payload.model_dump()
    doc["journal_number"] = await next_doc_number("PJ", "production_journals")
    # Pre-generate the id so the stock-transaction rows below can carry a real
    # source_doc_id link (crud_create() assigns it only after both posting
    # loops have already run).
    doc.setdefault("id", new_id())

    # ── 2. Cost resolution per consumption line ────────────────────────────
    total_material_cost = 0.0
    for line in doc["consumption"]:
        if not line.get("unit_cost"):
            prod = consumption_products.get(line["item_id"])
            line["unit_cost"] = float(prod.get("cost_price", 0)) if prod else 0.0
        total_material_cost += line["unit_cost"] * line["qty"]

    # ── 3. Deduct consumption from stock — each posts its own valuation-
    # priced ledger entry via post_entry rather than a flat quantity write.
    # No godown is captured on a Production Journal line today, so this
    # resolves the tenant's default the same way the other migrated v1 flows
    # do (see core.product_stock_bridge.resolve_godown_id). stock_item_id
    # resolution for every consumption + output line is batched in ONE call
    # up front rather than resolved per-line inside each loop (was an N+1 —
    # up to 3 queries per line, across two separate loops).
    godown_id = await resolve_godown_id(None)
    all_ids = [line["item_id"] for line in doc["consumption"]] + [o["item_id"] for o in doc["output"]]
    stock_item_by_product = await resolve_stock_item_ids_for_products(all_ids, user)

    for line in doc["consumption"]:
        item_id = line["item_id"]
        await post_entry(
            stock_item_id=stock_item_by_product[item_id], godown_id=godown_id,
            qty=-line["qty"], movement_type="PRODUCTION",
            source_doc_type="production_journal_consumption", source_doc_id=doc["id"],
            user=user,
        )

    # ── 4. Add output to stock ─────────────────────────────────────────────
    fg_qty_total = sum(
        o["qty"] for o in doc["output"]
        if not o.get("is_by_product")
    )
    by_product_credit = 0.0
    output_products = await _fetch_products_by_ids([o["item_id"] for o in doc["output"]])
    for out_line in doc["output"]:
        item_id = out_line["item_id"]
        prod = output_products.get(item_id)
        if not prod:
            continue
        rate = float(out_line.get("unit_cost") or prod.get("cost_price") or 0)
        await post_entry(
            stock_item_id=stock_item_by_product[item_id], godown_id=godown_id,
            qty=out_line["qty"], movement_type="PRODUCTION", rate=rate,
            source_doc_type="production_journal_output", source_doc_id=doc["id"],
            user=user,
        )
        if out_line.get("is_by_product"):
            by_product_credit += rate * out_line["qty"]

    # ── 5. Record net material cost on journal ─────────────────────────────
    doc["total_material_cost"] = round(total_material_cost - by_product_credit, 2)
    doc["unit_cost_fg"] = round(doc["total_material_cost"] / fg_qty_total, 4) if fg_qty_total else 0.0

    # Mark WO as in_progress if it was RELEASED
    if wo["status"] == "RELEASED":
        await db.work_orders.update_one(
            {"id": payload.work_order_id},
            {"$set": {"status": "IN_PROGRESS", "updated_at": now_iso()}},
        )

    return await crud_create("production_journals", doc, user)


# ══════════════════════════════════════════════════════════════
# Wastage Entry Endpoints
# ══════════════════════════════════════════════════════════════

@router.get("/wastage")
async def list_wastage(
    work_order_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require_mfg(user)
    filt = {}
    if work_order_id:
        filt["work_order_id"] = work_order_id
    return await crud_list("wastage_entries", filt=filt)


@router.post("/wastage")
async def create_wastage(payload: WastageEntry, user: dict = Depends(get_current_user)):
    """
    Log a wastage entry.
    NORMAL wastage cost is absorbed into FG cost (no separate P&L posting).
    ABNORMAL wastage is flagged — it should be expensed via the accounting module.
    """
    _require_mfg(user)
    doc = payload.model_dump()
    doc["wastage_number"] = await next_doc_number("WE", "wastage_entries")

    if not doc.get("valuation"):
        prod = await db.products.find_one({"id": payload.item_id})
        if prod:
            doc["valuation"] = round(float(prod.get("cost_price", 0)) * payload.qty, 2)

    return await crud_create("wastage_entries", doc, user)


# ══════════════════════════════════════════════════════════════
# QC Endpoints (kept + enhanced)
# ══════════════════════════════════════════════════════════════

@router.get("/qc")
async def list_qc_reports(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_mfg(user)
    return await crud_list("qc_reports", q, ["product_name", "inspector_name", "qc_number"])


@router.get("/qc/{qc_id}")
async def get_qc_report(qc_id: str, user: dict = Depends(get_current_user)):
    _require_mfg(user)
    return await crud_get("qc_reports", qc_id)


@router.post("/qc")
async def create_qc_report(payload: QCReport, user: dict = Depends(get_current_user)):
    """File QC report; adds passed FG to stock; updates WO status."""
    _require_mfg(user)
    wo = await crud_get("work_orders", payload.work_order_id)
    if wo["status"] not in ("QC_PENDING", "IN_PROGRESS", "COMPLETED"):
        raise HTTPException(400, "QC reports can only be filed against active/QC-pending WOs")

    doc = payload.model_dump()
    doc["qc_number"] = await next_doc_number("QC", "qc_reports")

    # If WO was in QC_PENDING flow, add passed FG to stock
    if wo["status"] == "QC_PENDING":
        prod = await db.products.find_one({"id": payload.product_id})
        if prod:
            stock_item_id = await resolve_stock_item_id_for_product(payload.product_id, user)
            godown_id = await resolve_godown_id(None)
            await post_entry(
                stock_item_id=stock_item_id, godown_id=godown_id,
                qty=payload.quantity_passed, movement_type="MANUFACTURING",
                rate=float(prod.get("cost_price") or 0),
                source_doc_type="qc_report", source_doc_id=wo["id"],
                user=user,
            )

        wo_status = "COMPLETED" if payload.status == "PASSED" else "IN_PROGRESS"
        await db.work_orders.update_one(
            {"id": payload.work_order_id},
            {"$set": {"status": wo_status, "quantity_produced": payload.quantity_passed, "updated_at": now_iso()}},
        )

    return await crud_create("qc_reports", doc, user)


# ══════════════════════════════════════════════════════════════
# MRP Engine
# ══════════════════════════════════════════════════════════════

@router.get("/mrp")
async def calculate_mrp(user: dict = Depends(get_current_user)):
    """MRP: aggregate raw material needs for all active WOs vs current stock."""
    _require_mfg(user)
    return await cache.get_or_set(
        "manufacturing:mrp", cache.TTL_DASHBOARD, _compute_mrp
    )


async def _compute_mrp() -> list:
    active_wos = await db.work_orders.find(
        {"status": {"$in": ["RELEASED", "IN_PROGRESS", "PENDING"]}},
        {"_id": 0},
    ).to_list(1000)

    # Load every BOM ONCE (bom_index, keyed by finished_product_id) instead
    # of a find_one per active work order AND per sub-assembly component
    # inside _explode_bom's recursion — this whole function is
    # cache.get_or_set'd (TTL_DASHBOARD), so it only pays this cost on a
    # cache miss, but a multi-level BOM explosion across many active WOs
    # used to cost 1 round-trip per top-level WO PLUS up to 2 more per
    # sub-assembly component at every recursion level.
    bom_index = await _load_bom_index()
    boms_by_id = {wo["bom_id"]: bom_index.get(wo["bom_id"]) for wo in active_wos if wo.get("bom_id")}
    # bom_index is keyed by finished_product_id, not bom id, so a WO's
    # bom_id needs its own direct lookup when it isn't the winning version
    # for that finished good — fall back to a batched-by-id fetch for those.
    missing_bom_ids = [bid for bid, b in boms_by_id.items() if b is None]
    if missing_bom_ids:
        found = await db.boms.find({"id": {"$in": missing_bom_ids}}, {"_id": 0}).to_list(len(missing_bom_ids))
        boms_by_id.update({b["id"]: b for b in found})

    requirements: dict = {}
    for wo in active_wos:
        bom = boms_by_id.get(wo.get("bom_id"))
        if not bom:
            continue
        qty_factor = float(wo["quantity_planned"]) - float(wo.get("quantity_produced", 0))
        if qty_factor <= 0:
            continue
        fg_id = bom.get("finished_product_id") or bom.get("finished_good_item_id", "")
        try:
            raw = await _explode_bom(bom, target_qty=qty_factor, ancestor_ids={fg_id}, bom_index=bom_index)
        except HTTPException:
            continue
        for item_id, req in raw.items():
            if item_id in requirements:
                requirements[item_id]["needed"] += req["required_qty"]
            else:
                requirements[item_id] = {
                    "product_id": item_id,
                    "product_name": req["item_name"],
                    "unit": req["uom"],
                    "needed": req["required_qty"],
                }

    mrp_list = []
    product_ids = list(requirements.keys())
    products_by_id = {}
    if product_ids:
        prods = await db.products.find(
            {"id": {"$in": product_ids}},
            {"_id": 0, "id": 1, "sku": 1, "quantity": 1}
        ).to_list(len(product_ids))
        products_by_id = {p["id"]: p for p in prods}

    for pid, req in requirements.items():
        prod = products_by_id.get(pid)
        stock = float(prod.get("quantity", 0)) if prod else 0.0
        shortage = req["needed"] - stock
        mrp_list.append({
            "product_id": pid,
            "product_name": req["product_name"],
            "sku": prod.get("sku", "") if prod else "",
            "unit": req["unit"],
            "quantity_required": round(req["needed"], 4),
            "quantity_on_hand": stock,
            "shortage": round(max(0.0, shortage), 4),
            "reorder_recommendation": round(max(0.0, shortage) * 1.2, 4) if shortage > 0 else 0.0,
        })
    return mrp_list


# ══════════════════════════════════════════════════════════════
# Dashboard
# ══════════════════════════════════════════════════════════════

@router.get("/dashboard")
async def get_dashboard_summary(user: dict = Depends(get_current_user)):
    _require_mfg(user)
    return await cache.get_or_set(
        "manufacturing:dashboard", cache.TTL_DASHBOARD, _compute_manufacturing_dashboard
    )


async def _compute_manufacturing_dashboard() -> dict:
    active_count = await db.work_orders.count_documents(
        {"status": {"$in": ["RELEASED", "IN_PROGRESS", "PENDING"]}}
    )
    completed_count = await db.work_orders.count_documents({"status": {"$in": ["COMPLETED", "CLOSED"]}})
    qc_pending_count = await db.work_orders.count_documents({"status": "QC_PENDING"})
    journal_count = await db.production_journals.count_documents({})
    wastage_abnormal = await db.wastage_entries.count_documents({"reason_code": "ABNORMAL"})

    reports = await db.qc_reports.find({}, {"_id": 0}).to_list(1000)
    total_checked = sum(float(r.get("quantity_checked", 0)) for r in reports)
    total_passed = sum(float(r.get("quantity_passed", 0)) for r in reports)
    total_failed = sum(float(r.get("quantity_failed", 0)) for r in reports)

    qc_pass_rate = 100.0 if total_checked == 0 else round((total_passed / total_checked) * 100, 2)
    scrap_rate = 0.0 if total_checked == 0 else round((total_failed / total_checked) * 100, 2)

    recent_wos = await db.work_orders.find(
        {"status": {"$in": ["DRAFT", "RELEASED", "IN_PROGRESS", "QC_PENDING"]}},
        {"_id": 0},
    ).sort("created_at", -1).limit(5).to_list(5)

    recent_journals = await db.production_journals.find({}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)

    return {
        "active_work_orders": active_count,
        "completed_work_orders": completed_count,
        "qc_pending_count": qc_pending_count,
        "production_journals": journal_count,
        "abnormal_wastage_entries": wastage_abnormal,
        "qc_pass_rate": qc_pass_rate,
        "scrap_rate": scrap_rate,
        "recent_work_orders": recent_wos,
        "recent_journals": recent_journals,
    }
