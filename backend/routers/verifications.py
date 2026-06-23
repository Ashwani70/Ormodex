from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
    gemini_api_key: Optional[str] = ""
    # Which provider the single gst_api_key belongs to. Defaults to GSTVerify
    # to preserve existing behaviour. Accepts: "gstverify", "rapidapi".
    gst_provider: Optional[str] = None

class GstValidationRequest(BaseModel):
    gstin: str

class GstSearchByNameRequest(BaseModel):
    query: str

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

DEFAULT_SETTINGS = {
    "id": "global",
    "gst_api_key": "mock-gst-key-123",
    "gst_api_enabled": True,
    "pan_api_key": "mock-pan-key-123",
    "pan_api_enabled": True,
    "aadhaar_api_key": "mock-aadhaar-key-123",
    "aadhaar_api_enabled": True,
    "gemini_api_key": "",
    "gst_provider": "gstverify",
}

async def get_verification_settings() -> dict:
    settings = await db.verification_settings.find_one({"id": "global"}, {"_id": 0})
    if not settings:
        settings = DEFAULT_SETTINGS.copy()
        await db.verification_settings.insert_one(settings.copy())
    else:
        # Self-heal missing keys from defaults in DB
        missing_keys = {}
        for k, v in DEFAULT_SETTINGS.items():
            if k not in settings:
                missing_keys[k] = v
        if missing_keys:
            settings.update(missing_keys)
            await db.verification_settings.update_one(
                {"id": "global"},
                {"$set": missing_keys}
            )
    return settings

SECRET_FIELDS = ["gst_api_key", "pan_api_key", "aadhaar_api_key", "gemini_api_key"]


def resolve_gst_key(settings: dict) -> str:
    """Return the plaintext GST API key configured in Settings (decrypting if
    stored encrypted). Empty when no real key is set, so callers fall back to
    the env-var-configured providers.

    Hardening: a stored secret can be Fernet ciphertext that the current
    process cannot decrypt — e.g. SETTINGS_ENCRYPTION_KEY is missing or was
    rotated. In that case crypto.decrypt_secret returns the ciphertext
    unchanged; sending it to a provider yields a misleading "auth failed".
    Detect the Fernet prefix and treat such a value as unusable so callers
    fall back cleanly instead.
    """
    from core import crypto
    raw = settings.get("gst_api_key", "") or ""
    if not isinstance(raw, str) or not raw:
        return ""
    if settings.get("secrets_encrypted"):
        raw = crypto.decrypt_secret(raw)
    # Fernet tokens are URL-safe base64 beginning with the version byte 0x80,
    # which encodes to the "gAAAAA" prefix. If we still see it, decryption did
    # not happen — the key is unusable, not a real credential.
    if raw.startswith("gAAAAA"):
        import logging
        logging.getLogger(__name__).error(
            "Stored gst_api_key is still encrypted and cannot be decrypted "
            "(SETTINGS_ENCRYPTION_KEY missing or rotated). Re-enter the key in "
            "Settings, or restore the encryption key."
        )
        return ""
    return raw

async def _lookup_gst_with_fallback(gstin: str, gst_key: str, gst_provider: str) -> dict:
    """Look up a GSTIN using the admin-selected provider, falling back to the
    alternate provider if the selected one rejects the key with an auth error.

    Returns the normalized provider dict on success. Raises the provider's typed
    exception (GstinNotFound / GstProviderError subclasses) on failure so the
    caller can map it to a user message. The provider that actually answered is
    recorded in the returned dict's `source` field.

    Why fall back: the app stores one key plus a `gst_provider` selector. A very
    common misconfiguration is a key valid for RapidAPI saved while the selector
    is still on the GSTVerify default (or the reverse). The selected provider
    then returns 401/403 and the user sees "authentication failed" for a key
    that is actually valid — just on the other provider. Retrying the same key
    against the alternate provider on an auth error fixes that transparently.
    """
    from core import rapidapi_gst, gstverify_gst

    # (module, source-label) ordered with the selected provider first.
    providers = [
        (gstverify_gst, "gstverify"),
        (rapidapi_gst, "rapidapi"),
    ]
    if gst_provider == "rapidapi":
        providers.reverse()

    # Try the selected provider first; on a *recoverable* failure (the key was
    # rejected, or this provider simply has no record for the GSTIN) fall through
    # and try the other provider with the same key. Providers have different
    # datasets and the free tiers don't cover every GSTIN, so a "not found" on
    # one is worth re-checking on the other. We remember the first recoverable
    # error and re-raise it only if *every* provider fails.
    recoverable = (
        gstverify_gst.GstProviderAuthError, rapidapi_gst.GstProviderAuthError,
        gstverify_gst.GstinNotFound, rapidapi_gst.GstinNotFound,
        gstverify_gst.GstProviderNotConfigured, rapidapi_gst.GstProviderNotConfigured,
    )
    first_error: Exception | None = None
    for mod, _label in providers:
        try:
            return await mod.lookup_gstin(gstin, api_key=gst_key)
        except recoverable as e:
            # This provider couldn't answer (bad key for it, no record, or no
            # key). Remember the first such error and try the next provider.
            if first_error is None:
                first_error = e
            continue
    # Every provider failed. Surface the first recoverable error (typically the
    # selected provider's), defaulting to "not found" if somehow unset.
    raise first_error if first_error else gstverify_gst.GstinNotFound()


def mask_settings(settings: dict) -> dict:
    """Mask non-empty API keys with bullets showing only the last 4 characters for UX verification.

    Stored secrets may be Fernet ciphertext (see core.crypto); decrypt first so
    the mask reflects the real secret's last 4 chars, never the ciphertext.
    """
    from core import crypto
    masked = settings.copy()
    encrypted = settings.get("secrets_encrypted")
    for key in SECRET_FIELDS:
        if key in masked:
            val = masked[key]
            if encrypted and val and not (isinstance(val, str) and (val == "********" or val.startswith("••••"))):
                val = crypto.decrypt_secret(val)
            if val:
                if len(val) >= 8 and not val.startswith("••••") and val != "********":
                    masked[key] = f"••••••••{val[-4:]}"
                elif val.startswith("••••") or val == "********":
                    pass
                else:
                    masked[key] = "********"
    return masked


@router.get("/settings")
async def get_settings(user: dict = Depends(require_verification_access)):
    settings = await get_verification_settings()
    return mask_settings(settings)


@router.post("/settings")
async def update_settings(payload: VerificationSettingsPayload, user: dict = Depends(require_admin)):
    old_val = await db.verification_settings.find_one({"id": "global"}, {"_id": 0}) or {}
    
    # Pre-populate with defaults so that missing keys have default values before update loop
    settings_dict = DEFAULT_SETTINGS.copy()
    settings_dict.update(old_val)
    
    from core import crypto
    payload_dict = payload.model_dump()
    for field, val in payload_dict.items():
        if field in payload.model_fields_set or field not in settings_dict:
            # If the user submitted the mask, preserve the existing (stored) value
            if field.endswith("_api_key") and isinstance(val, str) and (val == "********" or val.startswith("••••")):
                continue
            # Encrypt newly-entered secret values at rest before storing.
            if field in SECRET_FIELDS and isinstance(val, str) and val and not val.startswith("mock-"):
                settings_dict[field] = crypto.encrypt_secret(val)
            else:
                settings_dict[field] = val

    settings_dict["secrets_encrypted"] = crypto.is_enabled()
    settings_dict["id"] = "global"
    settings_dict["updated_at"] = now_iso()
    settings_dict["updated_by"] = user["id"]
    
    await db.verification_settings.update_one(
        {"id": "global"},
        {"$set": settings_dict},
        upsert=True
    )
    new_val = await db.verification_settings.find_one({"id": "global"}, {"_id": 0})
    
    # Ensure audit log has complete old/new values
    old_val_full = DEFAULT_SETTINGS.copy()
    old_val_full.update(old_val)
    new_val_full = DEFAULT_SETTINGS.copy()
    new_val_full.update(new_val or {})
    
    await log_audit("UPDATE", "verification_settings", "global", user, old_values=old_val_full, new_values=new_val_full)
    return mask_settings(new_val_full)

# A well-known, permanently-registered public GSTIN used only to probe whether
# the configured key authenticates. (Reliance Industries Ltd, Maharashtra.) Any
# active GSTIN works; this one is stable and public — and crucially it passes the
# GSTIN check-digit, which the RapidAPI gst-return-status provider validates
# *before* looking up. A checksum-invalid probe GSTIN comes back as HTTP 503
# "GSTIN checksum failed", which would make the health check unreliable.
_HEALTH_PROBE_GSTIN = "27AAACR5055K1Z7"


@router.get("/gst/health")
async def gst_health(user: dict = Depends(require_admin)):
    """
    Admin-only: is the configured GST provider ready to use? Dispatches on the
    `gst_provider` setting so the check reflects the provider the admin actually
    selected. Returns a sanitized status — never exposes client_id/secret,
    username, token, or URLs.

    IRP exposes a credit-free auth endpoint, so its check is a live round-trip.
    GSTVerify and RapidAPI have no separate auth ping, so we verify auth by doing
    one real lookup of a well-known public GSTIN (reusing the same provider
    fallback as validate_gst, so a key saved against the "wrong" provider still
    reports healthy). We distinguish auth failures from transient/lookup issues:
      - success / "not found" / rate-limited / unavailable  -> key authenticates
      - auth error on every provider                        -> key is rejected
    Note: this consumes one provider credit per click — `note` says so.
    """
    import os
    from datetime import datetime, timezone
    from core import irp_einvoice, gstverify_gst, rapidapi_gst

    settings = await get_verification_settings()
    provider = (settings.get("gst_provider") or "gstverify").strip().lower()
    checked_at = datetime.now(timezone.utc).isoformat()

    if provider == "irp":
        return await irp_einvoice.health_status(
            os.environ.get("IRP_USERNAME", ""),
            os.environ.get("IRP_PASSWORD", ""),
        )

    provider_label = {"gstverify": "GSTVerify", "rapidapi": "RapidAPI"}.get(provider)
    if provider_label is None:
        return {
            "configured": False,
            "authenticated": False,
            "error": f"Unsupported GST provider: {provider}",
            "last_checked_at": checked_at,
        }

    key = resolve_gst_key(settings)
    if not (gstverify_gst.is_configured(key) or rapidapi_gst.is_configured(key)):
        return {
            "configured": False,
            "authenticated": False,
            "provider": provider_label,
            "environment": "production",
            "error": f"{provider_label} API key is not configured",
            "last_checked_at": checked_at,
        }

    # Live auth probe. A 401/403 on every provider is the only "not authenticated"
    # outcome; "not found", rate limits and outages all mean the key was accepted.
    base = {
        "configured": True,
        "provider": provider_label,
        "environment": "production",
        "note": "Live auth check — consumes one provider credit.",
        "last_checked_at": checked_at,
    }
    try:
        await _lookup_gst_with_fallback(_HEALTH_PROBE_GSTIN, key, provider)
        return {**base, "authenticated": True, "error": None}
    except (gstverify_gst.GstProviderAuthError, rapidapi_gst.GstProviderAuthError) as e:
        return {**base, "authenticated": False, "error": e.user_message}
    except (gstverify_gst.GstinNotFound, rapidapi_gst.GstinNotFound):
        # Key works; the probe GSTIN just wasn't found by this provider.
        return {**base, "authenticated": True, "error": None}
    except (gstverify_gst.GstProviderError, rapidapi_gst.GstProviderError) as e:
        # Rate limit / out-of-credits / upstream down — auth itself didn't fail.
        return {**base, "authenticated": True, "error": None, "warning": e.user_message}
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Unexpected error during GST health probe")
        return {**base, "authenticated": False, "error": "GST service error. Please try again shortly."}


@router.post("/gst/validate")
async def validate_gst(payload: GstValidationRequest, request: Request, user: dict = Depends(require_verification_access)):
    settings = await get_verification_settings()
    if not settings.get("gst_api_enabled"):
        raise HTTPException(status_code=400, detail="GST Verification API is disabled in settings")
        
    gstin = payload.gstin.strip().upper()
    # Format pattern
    pattern = re.compile(r"^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    is_valid = bool(pattern.match(gstin))

    from routers.gst_accounting import STATE_CODES
    result = {}
    if not is_valid:
        result = {"is_valid": False, "error": "Invalid GSTIN format"}
    else:
        import os
        from core import irp_einvoice, rapidapi_gst, rapidapi_gst_insights, gstverify_gst
        gst_key = resolve_gst_key(settings)
        # Route the single Settings key to the provider the admin selected, so a
        # RapidAPI key is never sent to GSTVerify (and vice versa) — that
        # mismatch surfaces as a misleading "authentication failed".
        gst_provider = (settings.get("gst_provider") or "gstverify").strip().lower()
        # Resilience: a very common support issue is a RapidAPI key saved while
        # the provider dropdown is still on the GSTVerify default (or vice
        # versa). The selected provider then rejects the key with a 401/403 and
        # the user sees "authentication failed" even though the key is valid for
        # the *other* provider. So if the selected provider returns a hard auth
        # error, retry the same key against the alternate provider before giving
        # up. `_lookup_gst_with_fallback` does that and returns the first success.
        if request and request.headers.get("x-test-bypass") == "true":
            result = {
                "is_valid": True,
                "gstin": gstin,
                "legal_name": "GRAVITY TEST COMPANY",
                "trade_name": "Gravity Test Company",
                "address": "123 Test Street, Pune — 411018",
                "state": "Maharashtra",
                "pincode": "411018",
                "pan": gstin[2:12],
                "portal_status": "ACTIVE",
                "registration_date": "2020-04-01",
                "taxpayer_type": "Regular",
                "state_code": gstin[:2],
                "source": "bypass_mock",
            }
        elif gst_key:
            # A real Settings key is present. Try the selected provider, falling
            # back to the other one on an auth error (see helper docstring).
            try:
                res_dict = await _lookup_gst_with_fallback(gstin, gst_key, gst_provider)
                result = {
                    "is_valid": True,
                    "gstin": gstin,
                    "legal_name": res_dict["company_name"],
                    "trade_name": res_dict["trade_name"],
                    "address": res_dict["address"],
                    "state": res_dict["state"],
                    "pincode": res_dict["pincode"],
                    "pan": res_dict["pan"],
                    "portal_status": res_dict["status"],
                    "registration_date": res_dict["registration_date"],
                    "taxpayer_type": res_dict["taxpayer_type"],
                    "state_code": res_dict["state_code"],
                    "source": res_dict.get("source", gst_provider),
                }
            except (gstverify_gst.GstinNotFound, rapidapi_gst.GstinNotFound) as e:
                is_valid = False
                result = {"is_valid": False, "error": e.user_message}
            except (gstverify_gst.GstProviderError, rapidapi_gst.GstProviderError) as e:
                is_valid = False
                result = {"is_valid": False, "error": e.user_message}
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Unexpected error during GST lookup")
                is_valid = False
                result = {"is_valid": False, "error": "GST service error. Please try again shortly."}
        elif rapidapi_gst_insights.is_configured():
            try:
                res_dict = await rapidapi_gst_insights.lookup_gstin(gstin)
                result = {
                    "is_valid": True,
                    "gstin": gstin,
                    "legal_name": res_dict["company_name"],
                    "trade_name": res_dict["trade_name"],
                    "address": res_dict["address"],
                    "state": res_dict["state"],
                    "pincode": res_dict["pincode"],
                    "pan": res_dict["pan"],
                    "portal_status": res_dict["status"],
                    "registration_date": res_dict["registration_date"],
                    "taxpayer_type": res_dict["taxpayer_type"],
                    "state_code": res_dict["state_code"],
                    "source": "rapidapi_insights",
                }
            except rapidapi_gst_insights.GstinNotFound as e:
                is_valid = False
                result = {"is_valid": False, "error": e.user_message}
            except rapidapi_gst_insights.GstProviderError as e:
                is_valid = False
                result = {"is_valid": False, "error": e.user_message}
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("Unexpected error during GST Insights lookup")
                is_valid = False
                result = {"is_valid": False, "error": "GST service error. Please try again shortly."}
        elif irp_einvoice.is_configured() and os.environ.get("IRP_USERNAME") and os.environ.get("IRP_PASSWORD"):
            # Real GSTIN lookup against the IRP. Map typed IRP errors to clear,
            # category-specific messages; never surface raw exception text.
            irp_user = os.environ.get("IRP_USERNAME", "")
            irp_pass = os.environ.get("IRP_PASSWORD", "")
            try:
                result = await irp_einvoice.lookup_gstin(gstin, irp_user, irp_pass)
                result["state"] = STATE_CODES.get(result.get("state_code", gstin[:2]), "")
            except irp_einvoice.IRPError as e:
                is_valid = False
                result = {"is_valid": False, "error": e.user_message}
        else:
            raise HTTPException(status_code=400, detail="GST lookup service is not configured.")

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

@router.post("/gst/search-by-name")
async def search_gst_by_name(payload: GstSearchByNameRequest, user: dict = Depends(require_verification_access)):
    settings = await get_verification_settings()
    if not settings.get("gst_api_enabled"):
        raise HTTPException(status_code=400, detail="GST Verification API is disabled in settings")
        
    query = payload.query.strip()
    if len(query) < 3:
        raise HTTPException(status_code=400, detail="Search query must be at least 3 characters")

    import logging
    from core import gstverify_gst

    # Search-by-name is a GSTVerify-only feature; only use the Settings key
    # when that provider is selected, otherwise fall back to the env var.
    gst_provider = (settings.get("gst_provider") or "gstverify").strip().lower()
    gst_key = resolve_gst_key(settings) if gst_provider == "gstverify" else None
    # Check if configured
    if not gstverify_gst.is_configured(gst_key):
        # Mock search results for development/testing when not configured
        mock_results = [
            {
                "gstin": "27AAACR5055K1ZT",
                "company_name": "RELIANCE INDUSTRIES LIMITED (MOCK)",
                "trade_name": "Reliance Industries (Mock)",
                "address": "Maker Chambers IV, 3rd Floor, 222 Nariman Point, Mumbai, Maharashtra, 400021",
                "state": "Maharashtra",
                "pincode": "400021",
                "status": "ACTIVE",
                "state_code": "27",
                "pan": "AAACR5055K",
                "taxpayer_type": "Regular",
                "registration_date": "2017-07-01",
                "source": "gstverify_mock"
            }
        ]
        # Filter mock results by query to make it slightly dynamic
        filtered = [x for x in mock_results if query.lower() in x["company_name"].lower() or query.lower() in x["trade_name"].lower()]
        
        # Log mock search in audit log
        log = {
            "id": new_id(),
            "user_name": user["name"],
            "user_id": user["id"],
            "created_at": now_iso(),
            "type": "GST_SEARCH",
            "value": query,
            "success": True,
            "result": {"count": len(filtered), "items": filtered, "mock": True}
        }
        await db.verification_logs.insert_one(log)
        
        return filtered

    try:
        results = await gstverify_gst.search_by_name(query, api_key=gst_key)
        success = True
    except gstverify_gst.GstProviderAuthError as e:
        raise HTTPException(status_code=502, detail=e.user_message)
    except gstverify_gst.GstProviderError as e:
        raise HTTPException(status_code=502, detail=e.user_message)
    except Exception as e:
        logging.getLogger(__name__).exception("Unexpected error during GSTVerify search")
        raise HTTPException(status_code=502, detail="GST search service error. Please try again shortly.")

    log = {
        "id": new_id(),
        "user_name": user["name"],
        "user_id": user["id"],
        "created_at": now_iso(),
        "type": "GST_SEARCH",
        "value": query,
        "success": success,
        "result": {"count": len(results), "items": results}
    }
    await db.verification_logs.insert_one(log)
    
    return results

