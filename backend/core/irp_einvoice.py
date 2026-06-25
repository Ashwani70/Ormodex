"""
Live e-Invoicing via the IRP (Invoice Registration Portal).

The IRP is the government e-invoicing system: you submit an invoice's JSON and
it returns an IRN (Invoice Reference Number), a signed QR code, and an
acknowledgement number/date. Access is via NIC directly or through a GSP.

The provider-specific endpoints, auth flow, and response field locations are
isolated in IRP_CONFIG below so wiring a specific IRP/GSP is a single edit once
their docs are known. Until base_url is set, is_configured() returns False and
callers fall back to their existing mock behaviour.

Typical IRP auth flow (varies by GSP — confirm against your docs):
  1. POST credentials (username, password) + GSP app key/secret  ->  auth token
     (+ often a session encryption key with a short TTL).
  2. POST the invoice JSON with the auth token  ->  IRN, SignedQRCode, AckNo, AckDt.

SECURITY: never log the password, auth token, or session key.
"""
import os
import time
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


# ── Clear error categories ──────────────────────────────────────────────────
# Distinct exception types so callers can map failures to specific, friendly
# user messages instead of a single generic error.
class IRPError(Exception):
    """Base class for IRP lookup failures."""
    user_message = "GST service error."


class IRPNotConfigured(IRPError):
    user_message = "IRP credentials missing — GST lookup is not configured."


class IRPAuthError(IRPError):
    user_message = "GST service authentication failed — check IRP credentials."


class IRPUnavailable(IRPError):
    """Network / 5xx / timeout — transient, worth retrying later."""
    user_message = "GST service unavailable. Please try again shortly."


class GstinNotFound(IRPError):
    user_message = "No GST record found for this GSTIN."

# ──────────────────────────────────────────────────────────────────────────
# Provider configuration — fill in from the IRP / GSP API documentation.
# ──────────────────────────────────────────────────────────────────────────
IRP_CONFIG: dict[str, Any] = {
    # Base URL of the IRP/GSP, e.g. the NIC sandbox or your GSP's host.
    "base_url": "",
    # ── Authentication ──────────────────────────────────────────────────
    "auth_path": "/eivital/v1.04/auth",
    "auth_method": "POST",
    # Field names the auth endpoint expects in the request body.
    "auth_user_field": "UserName",
    "auth_pass_field": "Password",
    # Extra static fields some GSPs require on auth (app key, client id, etc.).
    # These are NOT secrets per se but live in env/DB config, not here.
    "auth_extra_fields": {},
    # Where the auth token sits in the response (dotted path).
    "auth_token_path": ["Data", "AuthToken"],
    "token_ttl_seconds": 3300,  # refresh slightly before the ~6h/1h expiry
    # ── Generate IRN ────────────────────────────────────────────────────
    "generate_path": "/eicore/v1.03/Invoice",
    "generate_method": "POST",
    # How the auth token is presented on the generate request.
    "auth_header": "Authorization",
    "auth_scheme": "Bearer",
    # Where the IRN / QR / ack fields sit in the generate response.
    "result_path": ["Data"],
    "irn_field": "Irn",
    "qr_field": "SignedQRCode",
    "ackno_field": "AckNo",
    "ackdt_field": "AckDt",
    # ── Cancel IRN ──────────────────────────────────────────────────────
    "cancel_path": "/eicore/v1.03/Invoice/Cancel",
    "cancel_method": "POST",
    # ── GSTIN detail lookup (auto-fill name/address from a GSTIN) ────────
    # NIC e-invoice GSTIN-details endpoint. The taxpayer GSTIN is appended
    # to this path (e.g. .../GstinDetails/27ABCDE1234F1Z5).
    "gstin_detail_path": "/eivital/v1.04/Master/gstin",
    "gstin_detail_method": "GET",
    # Where the GSTIN detail fields sit in the response (dotted path to the
    # data object) and the field names inside it.
    "gstin_result_path": ["Data"],
    "gstin_legal_name_field": "LegalName",
    "gstin_trade_name_field": "TradeName",
    "gstin_address1_field": "AddrBnm",
    "gstin_address2_field": "AddrFlno",
    "gstin_street_field": "AddrSt",
    "gstin_location_field": "AddrLoc",
    "gstin_pincode_field": "AddrPncd",
    "gstin_state_field": "StateCode",
    "gstin_status_field": "Status",
    "gstin_type_field": "TxpType",
    "gstin_regdt_field": "DtReg",
    # ── Resilience ──────────────────────────────────────────────────────
    "http_timeout_seconds": 20.0,
    "max_retries": 3,            # attempts for transient (5xx/network/timeout)
    "retry_base_delay": 0.5,     # exponential backoff: 0.5s, 1s, 2s, ...
    # ── GSTIN result cache ──────────────────────────────────────────────
    "gstin_cache_ttl_seconds": 24 * 3600,  # 24h
}

# NIC requires the base URL and a GSP client id/secret in addition to the
# per-user UserName/Password. These are NOT in source — they come from env so
# they can be provisioned per deployment without a code change. The moment they
# are set, is_configured() flips to True and real lookups replace the mock.
IRP_CONFIG["base_url"] = os.environ.get("IRP_BASE_URL", IRP_CONFIG["base_url"])
# Non-secret descriptive metadata for the health endpoint. Safe to expose:
# a provider label and which environment (sandbox/production) — never the URL.
IRP_CONFIG["provider"] = os.environ.get("IRP_PROVIDER", "NIC")
IRP_CONFIG["environment"] = os.environ.get("IRP_ENVIRONMENT", "sandbox")
IRP_CONFIG["auth_extra_fields"] = {
    k: v for k, v in {
        # Common GSP header/body field names; harmless if the GSP ignores extras.
        "client_id": os.environ.get("IRP_CLIENT_ID", ""),
        "client_secret": os.environ.get("IRP_CLIENT_SECRET", ""),
    }.items() if v
}

# In-process token cache: {username: (token, expires_at_epoch)}
_token_cache: dict[str, tuple[str, float]] = {}
_token_lock = asyncio.Lock()

# In-process GSTIN lookup cache: {gstin: (result_dict, expires_at_epoch)}.
# Holds only public registry data (name/address/status) — no secrets.
_gstin_cache: dict[str, tuple[dict, float]] = {}


async def _request_with_retry(method: str, url: str, **kwargs) -> httpx.Response:
    """
    Issue an HTTP request with bounded timeout and exponential-backoff retry on
    transient failures (timeouts, network errors, 5xx). 4xx is returned as-is so
    the caller can distinguish auth/not-found. Never logs headers or bodies.
    """
    timeout = IRP_CONFIG["http_timeout_seconds"]
    attempts = max(1, IRP_CONFIG["max_retries"])
    base_delay = IRP_CONFIG["retry_base_delay"]
    last_exc: Optional[Exception] = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(attempts):
            try:
                resp = await client.request(method, url, **kwargs)
                if resp.status_code >= 500 and attempt < attempts - 1:
                    logger.warning("IRP %s returned %s; retrying", method, resp.status_code)
                    await asyncio.sleep(base_delay * (2 ** attempt))
                    continue
                return resp
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_exc = e
                # Log the error type only — never the URL query, headers, or body.
                logger.warning("IRP %s transient error (attempt %d/%d): %s",
                               method, attempt + 1, attempts, type(e).__name__)
                if attempt < attempts - 1:
                    await asyncio.sleep(base_delay * (2 ** attempt))
                    continue
    raise IRPUnavailable() from last_exc


def is_configured() -> bool:
    """True only when a real IRP base URL has been set."""
    return bool(IRP_CONFIG.get("base_url"))


def _dig(obj, path: list[str]):
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


# Brief health-result cache: (status_dict, expires_at_epoch). Avoids hitting the
# provider's auth endpoint on every "Test Connection" click.
HEALTH_CACHE_TTL_SECONDS = 45
HEALTH_AUTH_TIMEOUT_SECONDS = 8.0
_health_cache: Optional[tuple[dict, float]] = None


async def health_status(username: str, password: str, force: bool = False) -> dict:
    """
    Answer one question: "can the backend authenticate with the configured GST
    provider right now?" — WITHOUT performing a GSTIN lookup.

    Returns a SANITIZED status object (no client_id/secret, username, token, or
    URL ever included). Never raises; never logs headers or auth responses.
    Result is cached for HEALTH_CACHE_TTL_SECONDS to avoid needless auth calls.
    """
    global _health_cache
    now = time.time()
    if not force and _health_cache and _health_cache[1] > now:
        return _health_cache[0]

    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not is_configured() or not (username and password):
        status = {
            "configured": False,
            "authenticated": False,
            "error": "IRP credentials are not configured",
            "last_checked_at": checked_at,
        }
        _health_cache = (status, now + HEALTH_CACHE_TTL_SECONDS)
        return status

    try:
        _token_cache.pop(username, None)  # force a fresh auth round-trip
        # Short timeout for an interactive health probe — fail fast.
        await asyncio.wait_for(
            _get_token(username, password),
            timeout=HEALTH_AUTH_TIMEOUT_SECONDS,
        )
        status = {
            "configured": True,
            "authenticated": True,
            "provider": IRP_CONFIG.get("provider", "NIC"),
            "environment": IRP_CONFIG.get("environment", "sandbox"),
            "last_checked_at": checked_at,
        }
    except (IRPError, asyncio.TimeoutError):
        # Single generic auth-failure message — no provider internals leaked.
        status = {
            "configured": True,
            "authenticated": False,
            "error": "Authentication failed",
            "last_checked_at": checked_at,
        }

    _health_cache = (status, now + HEALTH_CACHE_TTL_SECONDS)
    return status


async def _get_token(username: str, password: str) -> str:
    now = time.time()
    cached = _token_cache.get(username)
    if cached and cached[1] > now:
        return cached[0]

    async with _token_lock:
        cached = _token_cache.get(username)
        if cached and cached[1] > time.time():
            return cached[0]

        url = IRP_CONFIG["base_url"].rstrip("/") + IRP_CONFIG["auth_path"]
        body = {
            IRP_CONFIG["auth_user_field"]: username,
            IRP_CONFIG["auth_pass_field"]: password,
            **IRP_CONFIG.get("auth_extra_fields", {}),
        }
        # NOTE: never log `body` (contains the password) or the response (token).
        resp = await _request_with_retry("POST", url, json=body)
        if resp.status_code in (401, 403):
            raise IRPAuthError()
        if resp.status_code >= 400:
            raise IRPUnavailable()
        data = resp.json()

        token = _dig(data, IRP_CONFIG["auth_token_path"])
        if not token:
            raise IRPAuthError()

        _token_cache[username] = (token, time.time() + IRP_CONFIG["token_ttl_seconds"])
        return token


def _normalise_result(data: dict) -> dict:
    """Extract IRN / QR / ack fields from the provider response into a stable shape."""
    result = _dig(data, IRP_CONFIG["result_path"])
    if not isinstance(result, dict):
        result = data
    return {
        "irn": result.get(IRP_CONFIG["irn_field"]),
        "einvoice_qr_code": result.get(IRP_CONFIG["qr_field"]),
        "ack_no": result.get(IRP_CONFIG["ackno_field"]),
        "ack_date": result.get(IRP_CONFIG["ackdt_field"]),
        "raw": result,
    }


async def generate_irn(invoice_json: dict, username: str, password: str) -> dict:
    """
    Submit an invoice (in IRP schema) to the IRP and return the IRN, signed QR
    code, ack number and ack date. Raises on network/auth/HTTP errors.
    """
    token = await _get_token(username, password)
    url = IRP_CONFIG["base_url"].rstrip("/") + IRP_CONFIG["generate_path"]
    headers = {IRP_CONFIG["auth_header"]: f'{IRP_CONFIG["auth_scheme"]} {token}'.strip()}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=headers, json=invoice_json)
        if resp.status_code == 401:
            _token_cache.pop(username, None)
            token = await _get_token(username, password)
            headers[IRP_CONFIG["auth_header"]] = f'{IRP_CONFIG["auth_scheme"]} {token}'.strip()
            resp = await client.post(url, headers=headers, json=invoice_json)
        resp.raise_for_status()
        data = resp.json()

    return _normalise_result(data)


async def cancel_irn(irn: str, reason_code: str, reason_text: str,
                     username: str, password: str) -> dict:
    """Cancel a previously generated IRN. Raises on error."""
    token = await _get_token(username, password)
    url = IRP_CONFIG["base_url"].rstrip("/") + IRP_CONFIG["cancel_path"]
    headers = {IRP_CONFIG["auth_header"]: f'{IRP_CONFIG["auth_scheme"]} {token}'.strip()}
    body = {"Irn": irn, "CnlRsn": reason_code, "CnlRem": reason_text}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        return resp.json()


async def lookup_gstin(gstin: str, username: str, password: str) -> dict:
    """
    Fetch a taxpayer's registered details (legal/trade name, address, status)
    for a GSTIN from the IRP and return them in the stable shape that
    validate_gst returns.

    Results are cached in-process for gstin_cache_ttl_seconds. Raises a typed
    IRPError subclass (IRPNotConfigured / IRPAuthError / GstinNotFound /
    IRPUnavailable) so callers can show a specific message.

    Only call this when is_configured() is True.
    """
    if not is_configured():
        raise IRPNotConfigured()

    # Serve from cache when fresh.
    cached = _gstin_cache.get(gstin)
    if cached and cached[1] > time.time():
        return cached[0]

    token = await _get_token(username, password)
    base = IRP_CONFIG["base_url"].rstrip("/") + IRP_CONFIG["gstin_detail_path"]
    url = f"{base}/{gstin}"
    headers = {IRP_CONFIG["auth_header"]: f'{IRP_CONFIG["auth_scheme"]} {token}'.strip()}

    resp = await _request_with_retry("GET", url, headers=headers)
    if resp.status_code == 401:
        # Token may have expired — refresh once and retry.
        _token_cache.pop(username, None)
        token = await _get_token(username, password)
        headers[IRP_CONFIG["auth_header"]] = f'{IRP_CONFIG["auth_scheme"]} {token}'.strip()
        resp = await _request_with_retry("GET", url, headers=headers)
    if resp.status_code in (401, 403):
        raise IRPAuthError()
    if resp.status_code == 404:
        raise GstinNotFound()
    if resp.status_code >= 400:
        raise IRPUnavailable()
    data = resp.json()

    detail = _dig(data, IRP_CONFIG["gstin_result_path"])
    if not isinstance(detail, dict):
        detail = data if isinstance(data, dict) else {}

    def _f(key: str) -> str:
        return (detail.get(IRP_CONFIG[key]) or "") if IRP_CONFIG.get(key) else ""

    address = ", ".join(p for p in (
        _f("gstin_address1_field"),
        _f("gstin_address2_field"),
        _f("gstin_street_field"),
        _f("gstin_location_field"),
    ) if p)

    if not _f("gstin_legal_name_field"):
        # IRP returned 200 but no taxpayer record for this GSTIN.
        raise GstinNotFound()

    result = {
        "is_valid": True,
        "gstin": gstin,
        "legal_name": _f("gstin_legal_name_field"),
        "trade_name": _f("gstin_trade_name_field"),
        "address": address,
        "pincode": _f("gstin_pincode_field"),
        "state_code": _f("gstin_state_field") or gstin[:2],
        "pan": gstin[2:12],
        "portal_status": _f("gstin_status_field"),
        "taxpayer_type": _f("gstin_type_field"),
        "registration_date": _f("gstin_regdt_field"),
        "source": "irp",
    }
    _gstin_cache[gstin] = (result, time.time() + IRP_CONFIG["gstin_cache_ttl_seconds"])
    return result
