from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import cache
from core.auth_utils import require_admin
from core.db import db
from core.models import CompanyProfile
from core.stock_valuation import (
    DEFAULT_METHOD,
    VALUATION_METHODS,
    canonical_method,
)
from core.utils import now_iso, new_id

router = APIRouter(prefix="/company", tags=["Company Profile"])

_DEFAULT_COMPANY = {
    "id": "default",
    "name": "GRAVITYONE ERP",
    "address": "Gat No. 123, Jyotiba Nagar, Talawade, Pune - 411062, Maharashtra, India",
    "gstin": "27AABCG1234F1Z5",
    "pan": "AABCG1234F",
    "state": "Maharashtra",
    "state_code": "27",
    "email": "info@ormodex.com",
    "phone": "+91 20 2765 4321",
    "bank_name": "HDFC Bank Ltd",
    "bank_account_no": "50200012345678",
    "bank_ifsc": "HDFC0000012",
    "bank_branch": "Chinchwad, Pune",
    "terms_conditions": "1. Subject to Pune jurisdiction.\n2. Payment within 30 days of invoice.\n3. Goods once sold will not be taken back.",
}


@router.get("/active")
async def get_active_company():
    """Retrieve the current active company profile (defaulting to the first created one or placeholder).

    Loads on every page via the Sidebar and changes only when an admin edits the
    profile, so it's cached for a short TTL; company writes invalidate "company:".

    Sorted by created_at ascending (oldest = "the" company row) so this is
    deterministic. This table is meant to be a singleton — see the note on
    update_company for how duplicate rows could previously appear; without a
    stable sort, which duplicate got returned as "active" was arbitrary, so a
    save could appear to succeed while the user was shown a totally different
    (older/newer) row on the next load.
    """
    async def _load():
        company = await db.companies.find_one({}, {"_id": 0}, sort=[("created_at", 1)])
        return company or _DEFAULT_COMPANY

    return await cache.get_or_set("company:active", cache.TTL_REFERENCE, _load)


@router.get("")
async def list_companies(_: dict = Depends(require_admin)):
    """List all configured company profiles."""
    return await db.companies.find({}, {"_id": 0}).to_list(100)


@router.post("")
async def create_company(payload: CompanyProfile, _: dict = Depends(require_admin)):
    """Create a new company profile."""
    data = payload.model_dump()
    data["id"] = new_id()
    data["created_at"] = now_iso()
    data["updated_at"] = now_iso()
    await db.companies.insert_one(data)
    data.pop("_id", None)
    return data


# ───────────────────── Inventory valuation settings ─────────────────────
# Registered BEFORE the "/{item_id}" routes so "valuation-settings" isn't
# captured as an item id by the parametrised PUT/GET below.

class ValuationSettings(BaseModel):
    valuation_method: str  # FIFO | LIFO | WEIGHTED_AVG | STANDARD_COST


@router.get("/valuation-settings")
async def get_valuation_settings(_: dict = Depends(require_admin)):
    """The company-wide default inventory valuation method.

    This is the fallback used for any stock item that doesn't override it. It is
    stored in company.extra.inventory_valuation_method (no dedicated column); an
    unset value means the engine default (WEIGHTED_AVG) applies.
    """
    company = await db.companies.find_one(
        {}, {"_id": 0, "extra": 1}, sort=[("created_at", 1)]
    ) or {}
    extra = company.get("extra") or {}
    method = canonical_method(extra.get("inventory_valuation_method")) or DEFAULT_METHOD
    return {
        "valuation_method": method,
        "options": list(VALUATION_METHODS),
        "is_default": extra.get("inventory_valuation_method") is None,
    }


@router.put("/valuation-settings")
async def update_valuation_settings(
    payload: ValuationSettings, _: dict = Depends(require_admin)
):
    """Set the company-wide default valuation method.

    Merges into company.extra so it doesn't clobber other settings, and only
    ever touches the single (oldest) company row — mirroring update_company's
    singleton handling. Invalidates the company cache so the new default takes
    effect on the next read.
    """
    method = canonical_method(payload.valuation_method)
    if method is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown valuation method. Allowed: {', '.join(VALUATION_METHODS)}",
        )

    company = await db.companies.find_one({}, {"_id": 0}, sort=[("created_at", 1)])
    if not company:
        raise HTTPException(status_code=404, detail="No company profile configured")

    extra = dict(company.get("extra") or {})
    extra["inventory_valuation_method"] = method
    await db.companies.update_one(
        {"id": company["id"]},
        {"$set": {"extra": extra, "updated_at": now_iso()}},
    )
    cache.invalidate_prefix("company:")
    return {"valuation_method": method, "options": list(VALUATION_METHODS)}


@router.put("/{item_id}")
async def update_company(item_id: str, payload: CompanyProfile, _: dict = Depends(require_admin)):
    """Update a company profile.

    This table is meant to hold exactly one row (the app has no real
    multi-company support — see get_active_company). If `item_id` doesn't
    match any row — the frontend sends the placeholder id "default" before
    its first GET has resolved, or its cached state is simply stale — find
    and update whatever row already exists instead of inserting a new one.
    Blindly inserting-on-mismatch (the old behavior) silently accumulated
    duplicate rows over time; which one get_active_company then returned was
    arbitrary, so a save could appear to succeed while a later reload showed
    an entirely different (older) row — exactly the "doesn't save properly"
    symptom this fixes. Only insert a genuinely new row when the table is
    empty.
    """
    data = payload.model_dump()
    data["updated_at"] = now_iso()
    res = await db.companies.update_one({"id": item_id}, {"$set": data})
    if res.matched_count == 0:
        existing = await db.companies.find_one({}, {"_id": 0}, sort=[("created_at", 1)])
        if existing:
            real_id = existing["id"]
            await db.companies.update_one({"id": real_id}, {"$set": data})
            updated = await db.companies.find_one({"id": real_id}, {"_id": 0})
            return updated
        data["id"] = new_id()
        data["created_at"] = now_iso()
        await db.companies.insert_one(data)
        data.pop("_id", None)
        return data

    updated = await db.companies.find_one({"id": item_id}, {"_id": 0})
    return updated


@router.delete("/{item_id}")
async def delete_company(item_id: str, _: dict = Depends(require_admin)):
    """Delete a company profile."""
    res = await db.companies.delete_one({"id": item_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Company profile not found")
    return {"ok": True}
