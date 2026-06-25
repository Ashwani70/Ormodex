"""
GSTIN detail lookup and search via the GSTVerify.co.in API.
"""
import os
import httpx
import logging
import re
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Base class and error categories matching the other providers
class GstProviderError(Exception):
    """Base class for GST provider lookup failures."""
    user_message = "GST service error."

class GstProviderNotConfigured(GstProviderError):
    user_message = "GST lookup is not configured — provider credentials missing."

class GstProviderAuthError(GstProviderError):
    user_message = "GST service authentication failed — check provider credentials."

class GstProviderUnavailable(GstProviderError):
    """Network / 5xx / timeout / rate limits — transient, worth retrying later."""
    user_message = "GST service unavailable. Please try again shortly."

class GstinNotFound(GstProviderError):
    user_message = "No GST record found for this query."


_PLACEHOLDER_KEYS = {"", "your_gstverify_api_key_here", "mock-gst-key-123"}


def resolve_api_key(api_key: Optional[str] = None) -> str:
    """Resolve the GSTVerify key from the explicitly supplied one
    (e.g. the key saved in the Settings UI). No env-var fallback."""
    key = (api_key or "").strip()
    if key and key not in _PLACEHOLDER_KEYS:
        return key
    return ""


def is_configured(api_key: Optional[str] = None) -> bool:
    """True when a usable GSTVerify API key is available (settings or env)."""
    return bool(resolve_api_key(api_key))


async def lookup_gstin(gstin: str, api_key: Optional[str] = None) -> dict:
    """
    Fetch taxpayer details from GSTVerify.co.in API and
    return them in the normalized shape the application expects.
    """
    api_key = resolve_api_key(api_key)
    if not api_key:
        raise GstProviderNotConfigured()

    gstin = gstin.strip().upper()

    url = f"https://gstverify.co.in/api/v1/verify/{gstin}"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code in (401, 403):
                raise GstProviderAuthError()
            if resp.status_code == 402:
                # Out of credits (402 Payment Required)
                logger.error("GSTVerify API key is out of credits (402)")
                raise GstProviderUnavailable("Out of API credits.")
            if resp.status_code == 422:
                raise GstinNotFound()
            if resp.status_code == 404:
                raise GstinNotFound()
            if resp.status_code == 429:
                raise GstProviderUnavailable("Rate limit exceeded.")
            if resp.status_code >= 500:
                raise GstProviderUnavailable()
            resp.raise_for_status()
            res_data = resp.json()
    except (httpx.TimeoutException, httpx.TransportError) as e:
        logger.warning("GSTVerify API lookup network error: %s", type(e).__name__)
        raise GstProviderUnavailable() from e
    except GstProviderError:
        raise
    except Exception as e:
        logger.exception("Unexpected error during GSTVerify lookup")
        raise GstProviderUnavailable() from e

    if not res_data.get("success") or "data" not in res_data:
        raise GstinNotFound()

    data = res_data["data"]

    # Extract name details
    legal_name = str(data.get("legal_name") or "").strip()
    trade_name = str(data.get("trade_name") or legal_name or "").strip()
    if not legal_name:
        raise GstinNotFound()

    # Address and pincode extraction
    address = str(data.get("address") or "").strip()
    pincode = data.get("pincode")
    if not pincode:
        # Pincodes in India are 6-digit numbers
        m = re.search(r"\b\d{6}\b", address)
        if m:
            pincode = m.group(0)

    # Get state from state mapping using state_code
    from routers.gst_accounting import STATE_CODES
    state_code = gstin[:2]
    state = data.get("state") or STATE_CODES.get(state_code, "Maharashtra")

    return {
        "company_name": legal_name,
        "trade_name": trade_name,
        "address": address,
        "state": state,
        "pincode": str(pincode or "").strip(),
        "status": str(data.get("status") or "Active").upper(),
        "state_code": state_code,
        "pan": data.get("pan") or gstin[2:12],
        "taxpayer_type": data.get("taxpayer_type") or "Regular",
        "registration_date": data.get("registration_date") or "",
        "source": "gstverify",
    }


async def search_by_name(query: str, api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search GSTINs by company/business name using GSTVerify.co.in.
    Returns a list of normalized matching business details.
    """
    api_key = resolve_api_key(api_key)
    if not api_key:
        raise GstProviderNotConfigured()

    query = query.strip()
    if len(query) < 3:
        raise ValueError("Search query must be at least 3 characters.")
    # URL encode query string
    from urllib.parse import quote
    encoded_query = quote(query)
    url = f"https://gstverify.co.in/api/v1/search/name/{encoded_query}"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code in (401, 403):
                raise GstProviderAuthError()
            if resp.status_code == 402:
                logger.error("GSTVerify API key is out of credits (402)")
                raise GstProviderUnavailable("Out of API credits.")
            if resp.status_code == 422:
                return []
            if resp.status_code == 404:
                return []
            if resp.status_code == 429:
                raise GstProviderUnavailable("Rate limit exceeded.")
            if resp.status_code >= 500:
                raise GstProviderUnavailable()
            resp.raise_for_status()
            res_data = resp.json()
    except (httpx.TimeoutException, httpx.TransportError) as e:
        logger.warning("GSTVerify search network error: %s", type(e).__name__)
        raise GstProviderUnavailable() from e
    except GstProviderError:
        raise
    except Exception as e:
        logger.exception("Unexpected error during GSTVerify search")
        raise GstProviderUnavailable() from e

    if not res_data.get("success") or "data" not in res_data:
        return []

    results = []
    # Data is a list of results
    items = res_data["data"]
    if not isinstance(items, list):
        items = [items] if isinstance(items, dict) else []

    from routers.gst_accounting import STATE_CODES

    for item in items:
        gstin = str(item.get("gstin") or "").strip().upper()
        if not gstin:
            continue
        legal_name = str(item.get("legal_name") or "").strip()
        trade_name = str(item.get("trade_name") or legal_name or "").strip()
        address = str(item.get("address") or "").strip()
        
        pincode = item.get("pincode")
        if not pincode:
            m = re.search(r"\b\d{6}\b", address)
            if m:
                pincode = m.group(0)

        state_code = gstin[:2]
        state = item.get("state") or STATE_CODES.get(state_code, "Maharashtra")

        results.append({
            "gstin": gstin,
            "company_name": legal_name,
            "trade_name": trade_name,
            "address": address,
            "state": state,
            "pincode": str(pincode or "").strip(),
            "status": str(item.get("status") or "Active").upper(),
            "state_code": state_code,
            "pan": item.get("pan") or gstin[2:12],
            "taxpayer_type": item.get("taxpayer_type") or "Regular",
            "registration_date": item.get("registration_date") or "",
            "source": "gstverify",
        })

    return results
