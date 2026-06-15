from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
import uuid

from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.models import CompanyProfile
from core.utils import now_iso, new_id

router = APIRouter(prefix="/company", tags=["Company Profile"])


@router.get("/active")
async def get_active_company():
    """Retrieve the current active company profile (defaulting to the first created one or placeholder)."""
    company = await db.companies.find_one({}, {"_id": 0})
    if not company:
        # Return fallback placeholder matching GravityOne ERP brand
        return {
            "id": "default",
            "name": "GRAVITYONE ERP",
            "address": "Gat No. 123, Jyotiba Nagar, Talawade, Pune - 411062, Maharashtra, India",
            "gstin": "27AABCG1234F1Z5",
            "pan": "AABCG1234F",
            "state": "Maharashtra",
            "state_code": "27",
            "email": "info@gravityone.com",
            "phone": "+91 20 2765 4321",
            "bank_name": "HDFC Bank Ltd",
            "bank_account_no": "50200012345678",
            "bank_ifsc": "HDFC0000012",
            "bank_branch": "Chinchwad, Pune",
            "terms_conditions": "1. Subject to Pune jurisdiction.\n2. Payment within 30 days of invoice.\n3. Goods once sold will not be taken back."
        }
    return company


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


@router.put("/{item_id}")
async def update_company(item_id: str, payload: CompanyProfile, _: dict = Depends(require_admin)):
    """Update a company profile."""
    data = payload.model_dump()
    data["updated_at"] = now_iso()
    res = await db.companies.update_one({"id": item_id}, {"$set": data})
    if res.matched_count == 0:
        # Try updating if it was "default" or singleton key
        if item_id == "default":
            data["id"] = new_id()
            data["created_at"] = now_iso()
            await db.companies.insert_one(data)
            data.pop("_id", None)
            return data
        raise HTTPException(status_code=404, detail="Company profile not found")
    
    updated = await db.companies.find_one({"id": item_id}, {"_id": 0})
    return updated


@router.delete("/{item_id}")
async def delete_company(item_id: str, _: dict = Depends(require_admin)):
    """Delete a company profile."""
    res = await db.companies.delete_one({"id": item_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Company profile not found")
    return {"ok": True}
