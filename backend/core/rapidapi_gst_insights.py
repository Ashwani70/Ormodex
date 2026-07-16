"""
GSTIN detail lookup via the RapidAPI Hub "GST Insights API"
(gst-insights-api.p.rapidapi.com).

This is a sibling provider to core.rapidapi_gst (which targets the
gst-return-status host). It returns taxpayer details in the same
normalized shape the application expects, so the verifications router can
fall back to it like any other provider.

Configure via env:
    RAPIDAPI_INSIGHTS_KEY   RapidAPI key (required)
    RAPIDAPI_INSIGHTS_HOST  override host (default gst-insights-api.p.rapidapi.com)
"""
import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_HOST = "gst-insights-api.p.rapidapi.com"


# Error categories matching core.rapidapi_gst so router handling is uniform.
class GstProviderError(Exception):
    """Base class for GST provider lookup failures."""
    user_message = "GST service error."

class GstProviderNotConfigured(GstProviderError):
    user_message = "GST lookup is not configured — provider credentials missing."

class GstProviderAuthError(GstProviderError):
    user_message = "GST service authentication failed — check provider credentials."

class GstProviderUnavailable(GstProviderError):
    """Network / 5xx / timeout — transient, worth retrying later."""
    user_message = "GST service unavailable. Please try again shortly."

class GstinNotFound(GstProviderError):
    user_message = "No GST record found for this GSTIN."


_PLACEHOLDER_KEYS = {"", "your_rapidapi_key_here", "mock-gst-key-123"}


def resolve_api_key(api_key: Optional[str] = None) -> str:
    """Resolve the RapidAPI key, preferring an explicitly supplied one
    (e.g. the key saved in the Settings UI) over the env var fallback. This
    mirrors core.rapidapi_gst so the verifications router can pass the Settings
    key here exactly as it does for the other RapidAPI provider."""
    key = (api_key or "").strip()
    if key and key not in _PLACEHOLDER_KEYS:
        return key
    env_key = os.environ.get("RAPIDAPI_INSIGHTS_KEY", "").strip()
    return env_key if env_key not in _PLACEHOLDER_KEYS else ""


def is_configured(api_key: Optional[str] = None) -> bool:
    """True when a usable RapidAPI key is available (settings or env)."""
    return bool(resolve_api_key(api_key))


def _normalize_date(value: Optional[str]) -> str:
    """Convert the provider's DD/MM/YYYY dates to ISO YYYY-MM-DD; pass through
    anything that doesn't match rather than guessing."""
    if not value:
        return ""
    value = value.strip()
    parts = value.split("/")
    if len(parts) == 3 and all(parts):
        dd, mm, yyyy = parts
        if len(yyyy) == 4:
            return f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}"
    return value


async def lookup_gstin(gstin: str, api_key: Optional[str] = None) -> dict:
    """
    Fetch taxpayer details from the GST Insights API and return them in the
    normalized shape the application expects. `api_key` (the Settings key) takes
    precedence over the RAPIDAPI_INSIGHTS_KEY env var.
    """
    api_key = resolve_api_key(api_key)
    if not api_key:
        raise GstProviderNotConfigured()

    gstin = gstin.strip().upper()

    api_host = os.environ.get("RAPIDAPI_INSIGHTS_HOST", DEFAULT_HOST)

    url = f"https://{api_host}/getGSTDetailsUsingGST/{gstin}"
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": api_host,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code in (401, 403):
                raise GstProviderAuthError()
            if resp.status_code == 404:
                raise GstinNotFound()
            if resp.status_code >= 500:
                raise GstProviderUnavailable()
            resp.raise_for_status()
            res_data = resp.json()
    except (httpx.TimeoutException, httpx.TransportError) as e:
        logger.warning("GST Insights lookup network error: %s", type(e).__name__)
        raise GstProviderUnavailable() from e
    except GstProviderError:
        raise
    except Exception as e:
        logger.exception("Unexpected error during GST Insights lookup")
        raise GstProviderUnavailable() from e

    # data is an array; the record (if any) is the first element.
    records = res_data.get("data")
    if not res_data.get("success") or not isinstance(records, list) or not records:
        raise GstinNotFound()

    data = records[0]

    legal_name = str(data.get("legalName") or "").strip()
    trade_name = str(data.get("tradeName") or legal_name or "").strip()
    if not legal_name:
        raise GstinNotFound()

    # Address is a nested object; flatten the populated parts into one line.
    addr = ((data.get("principalAddress") or {}).get("address")) or {}
    addr_parts = [
        addr.get("buildingNumber"),
        addr.get("buildingName"),
        addr.get("floorNumber"),
        addr.get("street"),
        addr.get("location"),
        addr.get("locality"),
        addr.get("district"),
        addr.get("pincode"),
    ]
    address = ", ".join(str(p).strip() for p in addr_parts if p is not None and str(p).strip())

    pincode = str(addr.get("pincode") or "").strip()

    # The provider returns the state *name* in stateCode; fall back to the
    # GSTIN's numeric state code -> name mapping if absent.
    state = str(addr.get("stateCode") or "").strip()
    state_code = gstin[:2]
    if not state:
        from routers.gst_accounting import STATE_CODES
        state = STATE_CODES.get(state_code, "")

    return {
        "company_name": legal_name,
        "trade_name": trade_name,
        "address": address,
        "state": state,
        "pincode": pincode,
        "status": str(data.get("status") or "Active").upper(),
        "state_code": state_code,
        "pan": gstin[2:12],
        "taxpayer_type": str(data.get("taxType") or "Regular").strip(),
        "registration_date": _normalize_date(data.get("registrationDate")),
        "source": "rapidapi_insights",
    }
