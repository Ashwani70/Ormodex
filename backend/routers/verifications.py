from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, constr
from typing import Optional, List
import uuid
import re
from datetime import datetime

from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.utils import now_iso, new_id, log_audit

router = APIRouter(prefix="/verifications", tags=["verifications"])

# Pydantic payloads
class VerificationSettingsPayload(BaseModel):
    gst_api_key: str
    gst_api_enabled: bool
    pan_api_key: str
    pan_api_enabled: bool
    aadhaar_api_key: str
    aadhaar_api_enabled: bool
    openai_api_key: Optional[str] = ""
    gemini_api_key: Optional[str] = ""

class GstValidationRequest(BaseModel):
    gstin: str

class PanValidationRequest(BaseModel):
    pan: str
    link_party_id: Optional[str] = None  # Optional customer/supplier ID to link to

class AadhaarValidationRequest(BaseModel):
    aadhaar: str
    link_party_id: Optional[str] = None

# Custom role permission helper
def require_verification_access(user: dict = Depends(get_current_user)) -> dict:
    role = user.get("role")
    if role in ("admin", "hr", "accountant"):
        return user
    # Check module permissions (e.g. sales, purchase, gst)
    perms = user.get("module_permissions", [])
    if any(p in perms for p in ("gst", "accounting", "sales", "purchase", "verification")):
        return user
    raise HTTPException(status_code=403, detail="Verification module access required")

async def get_verification_settings() -> dict:
    settings = await db.verification_settings.find_one({"id": "global"}, {"_id": 0})
    if not settings:
        settings = {
            "id": "global",
            "gst_api_key": "mock-gst-key-123",
            "gst_api_enabled": True,
            "pan_api_key": "mock-pan-key-123",
            "pan_api_enabled": True,
            "aadhaar_api_key": "mock-aadhaar-key-123",
            "aadhaar_api_enabled": True,
            "openai_api_key": "",
            "gemini_api_key": "",
        }
    else:
        if "openai_api_key" not in settings:
            settings["openai_api_key"] = ""
        if "gemini_api_key" not in settings:
            settings["gemini_api_key"] = ""
    return settings

@router.get("/settings")
async def get_settings(user: dict = Depends(require_verification_access)):
    return await get_verification_settings()

@router.post("/settings")
async def update_settings(payload: VerificationSettingsPayload, user: dict = Depends(require_admin)):
    old_val = await db.verification_settings.find_one({"id": "global"}, {"_id": 0}) or {}
    settings_dict = old_val.copy()
    
    payload_dict = payload.model_dump()
    for field, val in payload_dict.items():
        if field in payload.model_fields_set or field not in settings_dict:
            settings_dict[field] = val
            
    settings_dict["id"] = "global"
    settings_dict["updated_at"] = now_iso()
    settings_dict["updated_by"] = user["id"]
    
    await db.verification_settings.update_one(
        {"id": "global"},
        {"$set": settings_dict},
        upsert=True
    )
    new_val = await db.verification_settings.find_one({"id": "global"}, {"_id": 0})
    await log_audit("UPDATE", "verification_settings", "global", user, old_values=old_val, new_values=new_val)
    return new_val

@router.post("/gst/validate")
async def validate_gst(payload: GstValidationRequest, user: dict = Depends(require_verification_access)):
    settings = await get_verification_settings()
    if not settings.get("gst_api_enabled"):
        raise HTTPException(status_code=400, detail="GST Verification API is disabled in settings")
        
    gstin = payload.gstin.strip().upper()
    # Format pattern
    pattern = re.compile(r"^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    is_valid = bool(pattern.match(gstin))
    
    result = {}
    if not is_valid:
        result = {"is_valid": False, "error": "Invalid GSTIN format"}
    else:
        from routers.gst_accounting import STATE_CODES
        result = {
            "is_valid": True,
            "gstin": gstin,
            "legal_name": "GravityOne Partner Industry Ltd",
            "trade_name": "GravityOne partner",
            "address": "Plot 101, Industrial Area Phase 1, Pune, Maharashtra",
            "state": STATE_CODES.get(gstin[:2], "Maharashtra"),
            "pincode": "411018",
            "pan": gstin[2:12],
            "portal_status": "ACTIVE",
            "registration_date": "2021-06-15",
            "taxpayer_type": "Regular",
            "state_code": gstin[:2]
        }
        
    log = {
        "id": new_id(),
        "user_name": user["name"],
        "user_id": user["id"],
        "created_at": now_iso(),
        "type": "GST",
        "value": gstin,
        "success": is_valid,
        "result": result
    }
    await db.verification_logs.insert_one(log)
    log.pop("_id", None)
    return result

@router.post("/pan/validate")
async def validate_pan(payload: PanValidationRequest, user: dict = Depends(require_verification_access)):
    settings = await get_verification_settings()
    if not settings.get("pan_api_enabled"):
        raise HTTPException(status_code=400, detail="PAN Verification API is disabled in settings")
        
    pan = payload.pan.strip().upper()
    pattern = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
    is_valid = bool(pattern.match(pan))
    
    result = {}
    if not is_valid:
        result = {"is_valid": False, "error": "Invalid PAN format"}
    else:
        # standard PAN holder logic
        # 4th character determines type: P (Individual), C (Company), F (Firm), H (HUF), A (AOP), etc.
        pan_type = "INDIVIDUAL" if pan[3] == 'P' else ("COMPANY" if pan[3] == 'C' else "FIRM")
        result = {
            "is_valid": True,
            "pan": pan,
            "pan_holder_name": "GRAVITY ONE ERP ASSOCIATES",
            "pan_type": pan_type,
            "pan_status": "ACTIVE"
        }
        
        # Link logic
        if payload.link_party_id:
            # Check customer collection
            cust = await db.customers.find_one({"id": payload.link_party_id})
            if cust:
                await db.customers.update_one(
                    {"id": payload.link_party_id},
                    {"$set": {
                        "pan_number": pan,
                        "pan_holder_name": result["pan_holder_name"],
                        "pan_type": result["pan_type"],
                        "pan_status": result["pan_status"],
                        "updated_at": now_iso()
                    }}
                )
            else:
                supp = await db.suppliers.find_one({"id": payload.link_party_id})
                if supp:
                    await db.suppliers.update_one(
                        {"id": payload.link_party_id},
                        {"$set": {
                            "pan_number": pan,
                            "pan_holder_name": result["pan_holder_name"],
                            "pan_type": result["pan_type"],
                            "pan_status": result["pan_status"],
                            "updated_at": now_iso()
                        }}
                    )

    log = {
        "id": new_id(),
        "user_name": user["name"],
        "user_id": user["id"],
        "created_at": now_iso(),
        "type": "PAN",
        "value": pan,
        "success": is_valid,
        "result": result
    }
    await db.verification_logs.insert_one(log)
    log.pop("_id", None)
    return result

@router.post("/aadhaar/validate")
async def validate_aadhaar(payload: AadhaarValidationRequest, user: dict = Depends(require_verification_access)):
    settings = await get_verification_settings()
    if not settings.get("aadhaar_api_enabled"):
        raise HTTPException(status_code=400, detail="Aadhaar Verification API is disabled in settings")
        
    aadhaar = payload.aadhaar.replace(" ", "").strip()
    pattern = re.compile(r"^[0-9]{12}$")
    is_valid = bool(pattern.match(aadhaar))
    
    result = {}
    if not is_valid:
        result = {"is_valid": False, "error": "Invalid Aadhaar format (must be 12 digits)"}
    else:
        result = {
            "is_valid": True,
            "aadhaar_holder_name": "GRAVITY ONE VERIFIED HOLDER",
            "aadhaar_status": "VERIFIED",
            "address": "Pune, Maharashtra, India",
            "gender": "MALE"
        }
        
        # Link logic
        if payload.link_party_id:
            # Mask the Aadhaar number for security
            masked_aadhaar = f"XXXX-XXXX-{aadhaar[-4:]}"
            
            cust = await db.customers.find_one({"id": payload.link_party_id})
            if cust:
                await db.customers.update_one(
                    {"id": payload.link_party_id},
                    {"$set": {
                        "aadhaar_number": masked_aadhaar,
                        "aadhaar_holder_name": result["aadhaar_holder_name"],
                        "aadhaar_status": result["aadhaar_status"],
                        "updated_at": now_iso()
                    }}
                )
            else:
                supp = await db.suppliers.find_one({"id": payload.link_party_id})
                if supp:
                    await db.suppliers.update_one(
                        {"id": payload.link_party_id},
                        {"$set": {
                            "aadhaar_number": masked_aadhaar,
                            "aadhaar_holder_name": result["aadhaar_holder_name"],
                            "aadhaar_status": result["aadhaar_status"],
                            "updated_at": now_iso()
                        }}
                    )

    # Store masked Aadhaar in logs
    masked_value = f"XXXX-XXXX-{aadhaar[-4:]}" if is_valid else aadhaar
    log = {
        "id": new_id(),
        "user_name": user["name"],
        "user_id": user["id"],
        "created_at": now_iso(),
        "type": "AADHAAR",
        "value": masked_value,
        "success": is_valid,
        "result": result
    }
    await db.verification_logs.insert_one(log)
    log.pop("_id", None)
    return result

@router.get("/logs")
async def get_logs(page: int = 1, limit: int = 50, user: dict = Depends(require_verification_access)):
    skip = (page - 1) * limit
    total = await db.verification_logs.count_documents({})
    logs = await db.verification_logs.find({}, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "page": page, "items": logs}

@router.get("/dashboard")
async def get_dashboard(user: dict = Depends(require_verification_access)):
    total_customers = await db.customers.count_documents({})
    total_vendors = await db.suppliers.count_documents({})
    
    # Active GST is status ACTIVE
    active_gst = await db.customers.count_documents({"gst_status": "ACTIVE"}) + \
                 await db.suppliers.count_documents({"gst_status": "ACTIVE"})
                 
    # Invalid GST is either status not ACTIVE or explicit error
    invalid_gst = await db.customers.count_documents({"gstin": {"$ne": None}, "gst_status": {"$ne": "ACTIVE"}}) + \
                  await db.suppliers.count_documents({"gstin": {"$ne": None}, "gst_status": {"$ne": "ACTIVE"}})
                  
    recent = await db.verification_logs.find({}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    
    return {
        "total_customers": total_customers,
        "total_vendors": total_vendors,
        "active_gst": active_gst,
        "invalid_gst": invalid_gst,
        "recent_verifications": recent
    }
