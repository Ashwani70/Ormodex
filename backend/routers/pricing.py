"""Pricing & Schemes — Module G.

Plugs into sales/purchase pricing resolution with a deterministic, explainable
price resolver plus discount schemes (slab / flat / free-qty).

Resolution order (first hit wins), per spec:
    1. customer-specific price list   (price_lists.assigned_to = {type: customer, id})
    2. customer-group price list      (price_lists.assigned_to = {type: group, id})
    3. godown (warehouse) rate        (godown_rates by item + godown)
    4. item default                   (products.selling_price)

After the base rate is resolved, the best applicable discount scheme is applied
(default = best single scheme; stacking only if scheme.stackable and a global
allow_stacking flag). Free-qty schemes add a zero-value line with real stock
impact. The applied rule chain is returned so every line is auditable
("why this price").

Collections: price_lists, discount_schemes, godown_rates
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Literal
from pydantic import BaseModel
from datetime import date

from core.auth_utils import get_current_user, require_admin, is_admin_role
from core.db import db
from core.utils import now_iso, crud_create, crud_list, crud_get, crud_update

router = APIRouter(prefix="/pricing", tags=["Pricing & Schemes"])


def _require_pricing(user: dict):
    if (is_admin_role(user.get("role")) or user.get("role") == "accountant"):
        return user
    if any(p in user.get("module_permissions", []) for p in ("pricing", "sales", "inventory")):
        return user
    raise HTTPException(403, "Pricing module access required")


def _within_window(valid_from: Optional[str], valid_to: Optional[str], as_of: str) -> bool:
    if valid_from and as_of < valid_from:
        return False
    if valid_to and as_of > valid_to:
        return False
    return True


# ══════════════════════════════════════════════════════════════
# Pydantic models
# ══════════════════════════════════════════════════════════════

class PriceListItem(BaseModel):
    item_id: str
    uom: str = "pcs"
    rate: float
    min_qty: float = 0.0


class AssignedTo(BaseModel):
    type: Literal["customer", "group", "all"]
    id: Optional[str] = None


class PriceList(BaseModel):
    name: str
    currency: str = "INR"
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    assigned_to: AssignedTo
    items: list[PriceListItem] = []
    priority: int = 0


class SchemeSlab(BaseModel):
    from_qty: float
    to_qty: Optional[float] = None       # None = open-ended
    discount_pct: Optional[float] = None
    discount_amount: Optional[float] = None
    free_item_id: Optional[str] = None
    free_qty: Optional[float] = None


class DiscountScheme(BaseModel):
    name: str
    type: Literal["slab", "flat", "free_qty"]
    applies_to: Literal["item", "group", "all"]
    applies_to_id: Optional[str] = None  # item_id or group_id when not "all"
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    slabs: list[SchemeSlab] = []
    stackable: bool = False
    priority: int = 0


class GodownRate(BaseModel):
    item_id: str
    godown_id: str
    rate: float


# ══════════════════════════════════════════════════════════════
# CRUD: Price Lists
# ══════════════════════════════════════════════════════════════

@router.get("/price-lists")
async def list_price_lists(user: dict = Depends(get_current_user)):
    _require_pricing(user)
    return await crud_list("price_lists")


@router.post("/price-lists")
async def create_price_list(payload: PriceList, user: dict = Depends(require_admin)):
    return await crud_create("price_lists", payload.model_dump(), user)


@router.put("/price-lists/{list_id}")
async def update_price_list(list_id: str, payload: PriceList, user: dict = Depends(require_admin)):
    return await crud_update("price_lists", list_id, payload.model_dump(), user)


@router.post("/price-lists/{list_id}/bulk-items")
async def bulk_upsert_items(list_id: str, items: list[PriceListItem], user: dict = Depends(require_admin)):
    """Bulk replace/merge price-list items (import path). Merges by item_id+uom."""
    pl = await crud_get("price_lists", list_id)
    existing = {(i["item_id"], i.get("uom", "pcs")): i for i in pl.get("items", [])}
    for it in items:
        existing[(it.item_id, it.uom)] = it.model_dump()
    return await crud_update("price_lists", list_id, {"items": list(existing.values())}, user)


# ══════════════════════════════════════════════════════════════
# CRUD: Discount Schemes
# ══════════════════════════════════════════════════════════════

@router.get("/discount-schemes")
async def list_schemes(user: dict = Depends(get_current_user)):
    _require_pricing(user)
    return await crud_list("discount_schemes")


@router.post("/discount-schemes")
async def create_scheme(payload: DiscountScheme, user: dict = Depends(require_admin)):
    return await crud_create("discount_schemes", payload.model_dump(), user)


@router.put("/discount-schemes/{scheme_id}")
async def update_scheme(scheme_id: str, payload: DiscountScheme, user: dict = Depends(require_admin)):
    return await crud_update("discount_schemes", scheme_id, payload.model_dump(), user)


# ══════════════════════════════════════════════════════════════
# CRUD: Godown Rates
# ══════════════════════════════════════════════════════════════

@router.get("/godown-rates")
async def list_godown_rates(item_id: Optional[str] = None, godown_id: Optional[str] = None,
                            user: dict = Depends(get_current_user)):
    _require_pricing(user)
    filt = {}
    if item_id:
        filt["item_id"] = item_id
    if godown_id:
        filt["godown_id"] = godown_id
    return await crud_list("godown_rates", filt=filt)


@router.post("/godown-rates")
async def upsert_godown_rate(payload: GodownRate, user: dict = Depends(require_admin)):
    existing = await db.godown_rates.find_one(
        {"item_id": payload.item_id, "godown_id": payload.godown_id}, {"_id": 0})
    if existing:
        return await crud_update("godown_rates", existing["id"], {"rate": payload.rate}, user)
    return await crud_create("godown_rates", payload.model_dump(), user)


# ══════════════════════════════════════════════════════════════
# Base-rate resolution
# ══════════════════════════════════════════════════════════════

def _pick_list_item(price_list: dict, item_id: str, qty: float) -> Optional[dict]:
    """Best matching line in a price list for the qty (respecting min_qty)."""
    candidates = [
        i for i in price_list.get("items", [])
        if i["item_id"] == item_id and qty >= i.get("min_qty", 0)
    ]
    if not candidates:
        return None
    # highest min_qty that still qualifies (volume tier inside a single list)
    return max(candidates, key=lambda i: i.get("min_qty", 0))


async def _resolve_base_rate(item_id: str, customer_id: Optional[str], godown_id: Optional[str],
                             qty: float, as_of: str) -> dict:
    """
    Walk the deterministic resolution chain and return the base rate plus the
    rule that produced it. Always returns a result (item default as last resort).
    """
    chain = []  # audit of what was tried

    # Customer group, if the customer carries one
    group_id = None
    if customer_id:
        cust = await db.customers.find_one({"id": customer_id}, {"_id": 0, "group_id": 1})
        group_id = (cust or {}).get("group_id")

    lists = await db.price_lists.find({}, {"_id": 0}).to_list(1000)
    # sort by priority desc so an explicit higher-priority list wins ties
    lists.sort(key=lambda l: l.get("priority", 0), reverse=True)

    # 1. customer-specific list
    if customer_id:
        for pl in lists:
            at = pl.get("assigned_to", {})
            if at.get("type") == "customer" and at.get("id") == customer_id and _within_window(
                    pl.get("valid_from"), pl.get("valid_to"), as_of):
                hit = _pick_list_item(pl, item_id, qty)
                if hit:
                    return {"rate": hit["rate"], "source": "customer_price_list",
                            "source_id": pl["id"], "source_name": pl["name"],
                            "uom": hit.get("uom", "pcs"), "min_qty": hit.get("min_qty", 0),
                            "chain": chain + [f"customer list '{pl['name']}'"]}
        chain.append("no customer-specific list matched")

    # 2. group list
    if group_id:
        for pl in lists:
            at = pl.get("assigned_to", {})
            if at.get("type") == "group" and at.get("id") == group_id and _within_window(
                    pl.get("valid_from"), pl.get("valid_to"), as_of):
                hit = _pick_list_item(pl, item_id, qty)
                if hit:
                    return {"rate": hit["rate"], "source": "group_price_list",
                            "source_id": pl["id"], "source_name": pl["name"],
                            "uom": hit.get("uom", "pcs"), "min_qty": hit.get("min_qty", 0),
                            "chain": chain + [f"group list '{pl['name']}'"]}
        chain.append("no group list matched")

    # 3. godown rate
    if godown_id:
        gr = await db.godown_rates.find_one({"item_id": item_id, "godown_id": godown_id}, {"_id": 0})
        if gr:
            return {"rate": gr["rate"], "source": "godown_rate", "source_id": gr.get("id"),
                    "source_name": f"godown {godown_id}", "uom": "pcs", "min_qty": 0,
                    "chain": chain + [f"godown rate for {godown_id}"]}
        chain.append("no godown rate")

    # 4. item default
    product = await db.products.find_one({"id": item_id}, {"_id": 0, "selling_price": 1, "name": 1})
    if not product:
        raise HTTPException(404, f"Item '{item_id}' not found and no price-list/godown rate applies")
    return {"rate": product.get("selling_price", 0.0), "source": "item_default",
            "source_id": item_id, "source_name": product.get("name", item_id),
            "uom": "pcs", "min_qty": 0, "chain": chain + ["item default selling_price"]}


# ══════════════════════════════════════════════════════════════
# Scheme application
# ══════════════════════════════════════════════════════════════

def _slab_for_qty(scheme: dict, qty: float) -> Optional[dict]:
    """Find the slab whose [from_qty, to_qty) window contains qty. to_qty=None = open-ended.
    Boundary rule: from_qty is inclusive, to_qty is inclusive (slab applies up to and including to_qty)."""
    for slab in scheme.get("slabs", []):
        lo = slab.get("from_qty", 0)
        hi = slab.get("to_qty")
        if qty >= lo and (hi is None or qty <= hi):
            return slab
    return None


def _scheme_applies(scheme: dict, item_id: str, group_id: Optional[str]) -> bool:
    at = scheme.get("applies_to")
    if at == "all":
        return True
    if at == "item":
        return scheme.get("applies_to_id") == item_id
    if at == "group":
        return group_id is not None and scheme.get("applies_to_id") == group_id
    return False


def _compute_scheme_benefit(scheme: dict, base_rate: float, qty: float) -> Optional[dict]:
    """
    Return the benefit of one scheme at this qty/rate, or None if it does nothing.
    benefit = {discount_amount, free_line: {...} | None, description}
    """
    stype = scheme["type"]
    line_value = base_rate * qty

    if stype == "flat":
        slab = (scheme.get("slabs") or [{}])[0]
        disc = 0.0
        if slab.get("discount_pct"):
            disc = line_value * slab["discount_pct"] / 100.0
        elif slab.get("discount_amount"):
            disc = slab["discount_amount"]
        if disc <= 0:
            return None
        return {"discount_amount": round(disc, 2), "free_line": None,
                "description": f"{scheme['name']}: flat discount {round(disc, 2)}"}

    if stype == "slab":
        slab = _slab_for_qty(scheme, qty)
        if not slab:
            return None
        disc = 0.0
        if slab.get("discount_pct"):
            disc = line_value * slab["discount_pct"] / 100.0
        elif slab.get("discount_amount"):
            disc = slab["discount_amount"]
        if disc <= 0:
            return None
        tier = f"{slab.get('from_qty', 0)}–{slab.get('to_qty', '∞')}"
        return {"discount_amount": round(disc, 2), "free_line": None,
                "description": f"{scheme['name']}: slab {tier} → {slab.get('discount_pct') or ''}"
                               f"{'%' if slab.get('discount_pct') else ''}"}

    if stype == "free_qty":
        slab = _slab_for_qty(scheme, qty)
        if not slab or not slab.get("free_item_id") or not slab.get("free_qty"):
            return None
        return {"discount_amount": 0.0,
                "free_line": {"item_id": slab["free_item_id"], "qty": slab["free_qty"],
                              "rate": 0.0, "is_free": True, "scheme_id": scheme.get("id"),
                              "scheme_name": scheme["name"]},
                "description": f"{scheme['name']}: free {slab['free_qty']} × {slab['free_item_id']}"}

    return None


async def _apply_schemes(item_id: str, group_id: Optional[str], base_rate: float, qty: float,
                         as_of: str, allow_stacking: bool) -> dict:
    schemes = await db.discount_schemes.find({}, {"_id": 0}).to_list(1000)
    applicable = [
        s for s in schemes
        if _scheme_applies(s, item_id, group_id)
        and _within_window(s.get("valid_from"), s.get("valid_to"), as_of)
    ]
    applicable.sort(key=lambda s: s.get("priority", 0), reverse=True)

    benefits = []
    for s in applicable:
        b = _compute_scheme_benefit(s, base_rate, qty)
        if b:
            benefits.append({"scheme": s, "benefit": b})

    if not benefits:
        return {"total_discount": 0.0, "free_lines": [], "applied_schemes": []}

    if allow_stacking:
        # only schemes flagged stackable may combine; otherwise take the single best
        stackables = [b for b in benefits if b["scheme"].get("stackable")]
        non_stack = [b for b in benefits if not b["scheme"].get("stackable")]
        if stackables:
            chosen = stackables
        elif non_stack:
            chosen = [max(non_stack, key=lambda b: b["benefit"]["discount_amount"])]
        else:
            chosen = []
    else:
        # best single scheme by money saved (treat a free line by its notional value 0 → use discount)
        chosen = [max(benefits, key=lambda b: b["benefit"]["discount_amount"])]
        # but if the best money discount is 0 and a free_qty exists, prefer the free line
        if chosen and chosen[0]["benefit"]["discount_amount"] == 0:
            free_ones = [b for b in benefits if b["benefit"]["free_line"]]
            if free_ones:
                chosen = [free_ones[0]]

    total_discount = round(sum(b["benefit"]["discount_amount"] for b in chosen), 2)
    free_lines = [b["benefit"]["free_line"] for b in chosen if b["benefit"]["free_line"]]
    applied = [{"scheme_id": b["scheme"].get("id"), "scheme_name": b["scheme"]["name"],
                "type": b["scheme"]["type"], "description": b["benefit"]["description"],
                "discount_amount": b["benefit"]["discount_amount"]} for b in chosen]
    return {"total_discount": total_discount, "free_lines": free_lines, "applied_schemes": applied}


# ══════════════════════════════════════════════════════════════
# Resolve endpoint — the integration point for sales/purchase
# ══════════════════════════════════════════════════════════════

@router.get("/resolve")
async def resolve_price(
    itemId: str = Query(...),
    qty: float = Query(1.0),
    customerId: Optional[str] = Query(None),
    godownId: Optional[str] = Query(None),
    asOf: Optional[str] = Query(None),
    allowStacking: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    """
    Resolve the effective price for an item, fully explained.

    Returns base rate (+ which rule produced it), discount schemes applied,
    any free-qty lines, and the net per-unit / line totals — everything needed
    to write an auditable voucher line.
    """
    _require_pricing(user)
    as_of = asOf or date.today().isoformat()

    base = await _resolve_base_rate(itemId, customerId, godownId, qty, as_of)

    group_id = None
    if customerId:
        cust = await db.customers.find_one({"id": customerId}, {"_id": 0, "group_id": 1})
        group_id = (cust or {}).get("group_id")

    schemes = await _apply_schemes(itemId, group_id, base["rate"], qty, as_of, allowStacking)

    gross = round(base["rate"] * qty, 2)
    net = round(gross - schemes["total_discount"], 2)
    effective_rate = round(net / qty, 4) if qty else base["rate"]

    return {
        "item_id": itemId,
        "qty": qty,
        "as_of": as_of,
        "base_rate": base["rate"],
        "rate_source": base["source"],
        "rate_source_name": base["source_name"],
        "resolution_chain": base["chain"],
        "gross_amount": gross,
        "discount_amount": schemes["total_discount"],
        "net_amount": net,
        "effective_rate": effective_rate,
        "free_lines": schemes["free_lines"],
        "applied_schemes": schemes["applied_schemes"],
        # the audit blob to stamp on the voucher line
        "pricing_audit": {
            "rate_source": base["source"],
            "rate_source_id": base["source_id"],
            "resolution_chain": base["chain"],
            "applied_schemes": schemes["applied_schemes"],
            "resolved_at": now_iso(),
            "resolved_by": user["id"],
        },
    }
