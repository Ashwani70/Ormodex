"""
GSTIN detail lookup via the RapidAPI Hub GST Return Status API.
"""
import os
import httpx
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Base class and error categories matching other GST providers
class GstProviderError(Exception):
    """Base class for GST provider lookup failures."""
    user_message = "GST service error."

class GstProviderNotConfigured(GstProviderError):
    user_message = "GST lookup is not configured — provider credentials missing."

class GstProviderAuthError(GstProviderError):
    # RapidAPI keys are per-API subscriptions, so the usual cause here is a valid
    # key that simply isn't subscribed to *this* API. Say so, actionably.
    user_message = (
        "RapidAPI rejected the key. Make sure your RapidAPI account is subscribed "
        "to the \"GST Return Status\" API (gst-return-status) and the key is correct."
    )

class GstProviderUnavailable(GstProviderError):
    """Network / 5xx / timeout — transient, worth retrying later."""
    user_message = "GST service unavailable. Please try again shortly."

class GstinNotFound(GstProviderError):
    user_message = "No GST record found for this GSTIN."


_PLACEHOLDER_KEYS = {"", "your_rapidapi_key_here", "mock-gst-key-123"}


def resolve_api_key(api_key: Optional[str] = None) -> str:
    """Resolve the RapidAPI key, preferring an explicitly supplied one
    (e.g. the key saved in the Settings UI) over the env var fallback."""
    key = (api_key or "").strip()
    if key and key not in _PLACEHOLDER_KEYS:
        return key
    env_key = os.environ.get("RAPIDAPI_KEY", "").strip()
    return env_key if env_key not in _PLACEHOLDER_KEYS else ""


def is_configured(api_key: Optional[str] = None) -> bool:
    """True when a usable RapidAPI key is available (settings or env)."""
    return bool(resolve_api_key(api_key))


async def lookup_gstin(gstin: str, api_key: Optional[str] = None) -> dict:
    """
    Fetch taxpayer details from RapidAPI GST Return Status API and
    return them in the normalized shape the application expects.
    """
    api_key = resolve_api_key(api_key)
    if not api_key:
        raise GstProviderNotConfigured()

    gstin = gstin.strip().upper()

    api_host = os.environ.get("RAPIDAPI_HOST", "gst-return-status.p.rapidapi.com")

    url = f"https://{api_host}/free/gstin/{gstin}"
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": api_host,
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 429:
                raise GstProviderUnavailable("Rate limit exceeded.")
            if resp.status_code in (401, 403):
                # Log the body so a misconfigured subscription (wrong API on the
                # RapidAPI account, or a host/path the key isn't subscribed to)
                # is diagnosable — RapidAPI states the reason in the body.
                logger.error(
                    "RapidAPI GST lookup auth failed (%s): %s",
                    resp.status_code, resp.text[:300],
                )
                raise GstProviderAuthError()
            if resp.status_code == 404:
                raise GstinNotFound()
            if resp.status_code >= 500:
                # This API overloads 5xx for some *client* errors: a malformed /
                # checksum-invalid GSTIN comes back as HTTP 503 with a JSON body
                # {"success": false, "message": "GSTIN checksum failed"}. That's a
                # permanent input error, not a transient outage, so don't report
                # "service unavailable" (and don't let the provider fallback burn
                # a second credit retrying it). Inspect the body and map a clearly
                # input-related message to "not found"; treat anything else as a
                # genuine transient 5xx.
                body_msg = ""
                try:
                    body_msg = str((resp.json() or {}).get("message") or "")
                except Exception:
                    body_msg = resp.text[:200]
                low = body_msg.lower()
                if any(w in low for w in ("checksum", "invalid gstin", "malformed", "not a valid")):
                    logger.info("RapidAPI GST lookup rejected GSTIN %s: %s", gstin, body_msg)
                    raise GstinNotFound()
                logger.warning("RapidAPI GST lookup 5xx (%s): %s", resp.status_code, body_msg or "<empty>")
                raise GstProviderUnavailable()
            resp.raise_for_status()
            res_data = resp.json()
    except (httpx.TimeoutException, httpx.TransportError) as e:
        logger.warning("RapidAPI GST lookup network error: %s", type(e).__name__)
        raise GstProviderUnavailable() from e
    except GstProviderError:
        raise
    except Exception as e:
        logger.exception("Unexpected error during RapidAPI GST lookup")
        raise GstProviderUnavailable() from e

    # The gst-return-status RapidAPI returns {"flag": true, "data": {...}}; other
    # GST providers use {"success": true, ...}. Accept either truthy flag.
    # On failure it returns HTTP 200 with {"flag": false, "message": "..."} — so
    # the body, not the status code, carries the real reason. Surface it rather
    # than a blanket "not found", and distinguish auth/quota messages so the
    # provider fallback can retry against GSTVerify instead of dead-ending.
    ok = res_data.get("flag", res_data.get("success"))
    if not ok or "data" not in res_data:
        message = str(res_data.get("message") or res_data.get("error") or "").strip()
        low = message.lower()
        logger.warning("RapidAPI GST lookup returned no data: %s", message or "<empty>")
        if any(w in low for w in ("subscrib", "not subscribed", "api key", "apikey", "unauthor", "forbidden")):
            raise GstProviderAuthError()
        if any(w in low for w in ("quota", "rate limit", "too many", "exceeded")):
            raise GstProviderUnavailable("Rate limit or quota exceeded.")
        raise GstinNotFound()

    data = res_data["data"]

    # Extract name details. The live API uses GST-portal field names
    # (lgnm / tradeNam); tolerate the GSTVerify-style aliases too.
    legal_name = str(data.get("lgnm") or data.get("legal_name") or "").strip()
    trade_name = str(
        data.get("tradeNam") or data.get("tradeName") or data.get("trade_name") or legal_name or ""
    ).strip()
    if not legal_name:
        raise GstinNotFound()

    # Address: the API nests the principal place of business under `pradr`
    # (with an `adr` string), falling back to a flat `adr`/`address`.
    pradr = data.get("pradr") or {}
    address = str(
        (pradr.get("adr") if isinstance(pradr, dict) else None)
        or data.get("adr") or data.get("address") or ""
    ).strip()
    pincode = data.get("pincode")
    if not pincode and isinstance(pradr, dict):
        addr_obj = pradr.get("addr") or {}
        if isinstance(addr_obj, dict):
            pincode = addr_obj.get("pncd")
    if not pincode:
        # Pincodes in India are 6-digit numbers
        m = re.search(r"\b\d{6}\b", address)
        if m:
            pincode = m.group(0)

    # Get state from state mapping using state_code
    from routers.gst_accounting import STATE_CODES
    state_code = gstin[:2]
    state = STATE_CODES.get(state_code, "Maharashtra")

    return {
        "company_name": legal_name,
        "trade_name": trade_name,
        "address": address,
        "state": state,
        "pincode": str(pincode or "").strip(),
        "status": str(data.get("sts") or data.get("status") or "Active").upper(),
        "state_code": state_code,
        "pan": data.get("pan") or gstin[2:12],
        "taxpayer_type": data.get("dty") or data.get("ctb") or data.get("taxpayer_type") or "Regular",
        "registration_date": data.get("rgdt") or data.get("registration_date") or "",
        "source": "rapidapi",
    }
