"""
Official NIC / GSTN e-Way Bill API integration.

This is the server-side integration layer for the Government of India e-Way Bill
system (https://docs.ewaybillgst.gov.in / GSP). It speaks ONLY the official
NIC/GSTN REST API. There is NO web scraping, browser automation, or captcha
handling anywhere in this codebase — those are prohibited and unnecessary.

Auth model (NIC EWB API v1.03):
  1. POST /ewayapi/v1.03/auth with the GSTIN/username/password plus the GSP
     app key & secret  ->  an auth token (and a session key). Tokens are
     short-lived; we cache them in-process and refresh before expiry.
  2. Each operation POSTs an action payload with the auth token header.

All credentials come from environment variables (see EWB_* below) and are never
logged. Requests and responses are logged with sensitive fields masked via
:func:`mask_sensitive`.

Configuration is isolated in ``EWB_CONFIG`` so wiring a specific GSP/sandbox is
a single edit. Until ``base_url`` is set (EWB_BASE_URL), :func:`is_configured`
returns False and the router falls back to a deterministic sandbox simulator so
the rest of the app (and tests) work without live credentials.
"""
from __future__ import annotations

import os
import time
import json
import asyncio
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx

logger = logging.getLogger("nic_ewaybill")


# ── Error taxonomy ───────────────────────────────────────────────────────────
class EWBError(Exception):
    """Base class for e-Way Bill API failures."""
    user_message = "e-Way Bill service error."


class EWBNotConfigured(EWBError):
    user_message = "e-Way Bill credentials are not configured."


class EWBAuthError(EWBError):
    user_message = "e-Way Bill authentication failed — check NIC credentials."


class EWBUnavailable(EWBError):
    """Network / 5xx / timeout — transient, worth retrying."""
    user_message = "e-Way Bill service unavailable. Please try again shortly."


class EWBValidationError(EWBError):
    """The NIC API rejected the request (4xx with an error payload)."""
    def __init__(self, message: str):
        super().__init__(message)
        self.user_message = message


# ── Configuration (env-driven) ───────────────────────────────────────────────
EWB_CONFIG: dict[str, Any] = {
    "base_url": os.environ.get("EWB_BASE_URL", "").rstrip("/"),
    "environment": os.environ.get("EWB_ENV", "sandbox"),
    "client_id": os.environ.get("EWB_CLIENT_ID", ""),
    "client_secret": os.environ.get("EWB_CLIENT_SECRET", ""),
    "username": os.environ.get("EWB_USERNAME", ""),
    "password": os.environ.get("EWB_PASSWORD", ""),
    "gstin": os.environ.get("EWB_GSTIN", ""),
    # Endpoint paths (NIC EWB API v1.03 conventions; override per GSP if needed).
    "auth_path": os.environ.get("EWB_AUTH_PATH", "/ewayapi/v1.03/auth"),
    "generate_path": os.environ.get("EWB_GENERATE_PATH", "/ewayapi/v1.03/genewaybill"),
    "getewb_path": os.environ.get("EWB_GET_PATH", "/ewayapi/v1.03/getewaybill"),
    "update_vehicle_path": os.environ.get("EWB_UPDATE_VEHICLE_PATH", "/ewayapi/v1.03/vehewb"),
    "extend_path": os.environ.get("EWB_EXTEND_PATH", "/ewayapi/v1.03/extendvalidity"),
    "cancel_path": os.environ.get("EWB_CANCEL_PATH", "/ewayapi/v1.03/canewb"),
    # Auth token presentation + caching.
    "auth_header": "Authorization",
    "auth_scheme": "Bearer",
    "token_ttl_seconds": int(os.environ.get("EWB_TOKEN_TTL_SECONDS", "21600")),  # ~6h
    # Resilience.
    "http_timeout_seconds": float(os.environ.get("EWB_HTTP_TIMEOUT", "30")),
    "max_retries": int(os.environ.get("EWB_MAX_RETRIES", "3")),
    "retry_base_delay": 0.5,
}

# Fields whose values must never appear in logs (request or response).
_SENSITIVE_KEYS = {
    "password", "client_secret", "clientsecret", "client_id", "clientid",
    "authtoken", "auth_token", "token", "sek", "appkey", "app_key", "key",
    "authorization", "secret", "userName", "username", "user_name",
}


def is_configured() -> bool:
    """True only when a real NIC/GSP base URL + credentials are present."""
    c = EWB_CONFIG
    return bool(c["base_url"] and c["username"] and c["password"] and c["gstin"])


def environment() -> str:
    return EWB_CONFIG.get("environment") or "sandbox"


def public_status() -> dict:
    """Non-secret status for a health endpoint — never leaks URL or credentials."""
    return {
        "configured": is_configured(),
        "environment": environment(),
        "provider": "NIC",
    }


# ── Sensitive-data masking ───────────────────────────────────────────────────
def _mask_value(val: Any) -> Any:
    if isinstance(val, str):
        if len(val) <= 4:
            return "****"
        return val[:2] + "***" + val[-2:]
    return "****"


def mask_sensitive(obj: Any) -> Any:
    """Deep-copy ``obj`` with any sensitive key's value masked. Used before
    logging request/response bodies so credentials/tokens never hit the logs."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower().replace("_", "") in {s.replace("_", "") for s in _SENSITIVE_KEYS}:
                out[k] = _mask_value(v)
            else:
                out[k] = mask_sensitive(v)
        return out
    if isinstance(obj, list):
        return [mask_sensitive(v) for v in obj]
    return obj


def _log_exchange(action: str, request_body: Any, response_body: Any, status_code: int) -> None:
    """Structured, masked log of one API exchange (for the audit/debug trail)."""
    try:
        logger.info(
            "EWB %s [%s] status=%s req=%s resp=%s",
            action,
            environment(),
            status_code,
            json.dumps(mask_sensitive(request_body))[:2000],
            json.dumps(mask_sensitive(response_body))[:2000],
        )
    except Exception:  # logging must never break the request
        logger.info("EWB %s status=%s (unserialisable bodies)", action, status_code)


# ── Token cache ──────────────────────────────────────────────────────────────
# {gstin: (token, expires_at_epoch)}
_token_cache: dict[str, tuple[str, float]] = {}
_token_lock = asyncio.Lock()


async def _request_with_retry(method: str, url: str, **kwargs) -> httpx.Response:
    """HTTP with bounded timeout + exponential backoff on transient (5xx/network)
    failures. 4xx is returned as-is. Never logs URL query, headers, or body."""
    timeout = EWB_CONFIG["http_timeout_seconds"]
    attempts = max(1, EWB_CONFIG["max_retries"])
    base_delay = EWB_CONFIG["retry_base_delay"]
    last_exc: Optional[Exception] = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(attempts):
            try:
                resp = await client.request(method, url, **kwargs)
                if resp.status_code >= 500 and attempt < attempts - 1:
                    logger.warning("EWB %s returned %s; retrying", method, resp.status_code)
                    await asyncio.sleep(base_delay * (2 ** attempt))
                    continue
                return resp
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_exc = e
                logger.warning("EWB %s transient error (attempt %d/%d): %s",
                               method, attempt + 1, attempts, type(e).__name__)
                if attempt < attempts - 1:
                    await asyncio.sleep(base_delay * (2 ** attempt))
                    continue
    raise EWBUnavailable() from last_exc


async def _get_token() -> str:
    gstin = EWB_CONFIG["gstin"]
    now = time.time()
    cached = _token_cache.get(gstin)
    if cached and cached[1] > now:
        return cached[0]

    async with _token_lock:
        cached = _token_cache.get(gstin)
        if cached and cached[1] > time.time():
            return cached[0]

        url = EWB_CONFIG["base_url"] + EWB_CONFIG["auth_path"]
        body = {
            "action": "ACCESSTOKEN",
            "gstin": gstin,
            "username": EWB_CONFIG["username"],
            "password": EWB_CONFIG["password"],
            "app_key": EWB_CONFIG["client_id"],
            "client_id": EWB_CONFIG["client_id"],
            "client_secret": EWB_CONFIG["client_secret"],
        }
        # NEVER log `body` (password/secret) — _log_exchange masks it.
        resp = await _request_with_retry("POST", url, json=body)
        data = _safe_json(resp)
        _log_exchange("AUTH", body, data, resp.status_code)
        if resp.status_code in (401, 403):
            raise EWBAuthError()
        if resp.status_code >= 400:
            raise EWBUnavailable()

        token = _dig(data, ["data", "authtoken"]) or _dig(data, ["AuthToken"]) or data.get("token")
        if not token:
            raise EWBAuthError()
        _token_cache[gstin] = (token, time.time() + EWB_CONFIG["token_ttl_seconds"])
        return token


def invalidate_token() -> None:
    _token_cache.pop(EWB_CONFIG.get("gstin", ""), None)


# ── Helpers ──────────────────────────────────────────────────────────────────
def _dig(obj: Any, path: list[str]) -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _safe_json(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {"raw": data}
    except Exception:
        return {"raw": resp.text[:1000]}


async def _call(action: str, path: str, payload: dict) -> dict:
    """Authenticated POST of an action payload, with one token-refresh retry on
    401 and masked request/response logging. Raises a typed EWBError on failure."""
    if not is_configured():
        raise EWBNotConfigured()
    token = await _get_token()
    url = EWB_CONFIG["base_url"] + path
    headers = {
        EWB_CONFIG["auth_header"]: f'{EWB_CONFIG["auth_scheme"]} {token}'.strip(),
        "gstin": EWB_CONFIG["gstin"],
    }
    resp = await _request_with_retry("POST", url, headers=headers, json=payload)
    if resp.status_code == 401:
        invalidate_token()
        token = await _get_token()
        headers[EWB_CONFIG["auth_header"]] = f'{EWB_CONFIG["auth_scheme"]} {token}'.strip()
        resp = await _request_with_retry("POST", url, headers=headers, json=payload)

    data = _safe_json(resp)
    _log_exchange(action, payload, data, resp.status_code)

    if resp.status_code in (401, 403):
        raise EWBAuthError()
    if resp.status_code >= 500:
        raise EWBUnavailable()
    # NIC returns 4xx (or 200 with status flag) carrying a structured error.
    if resp.status_code >= 400 or _is_nic_error(data):
        raise EWBValidationError(_extract_error(data))
    # Unwrap the NIC envelope ({"status":"1","data":{...}}) when present.
    inner = _dig(data, ["data"])
    return inner if isinstance(inner, dict) else data


def _is_nic_error(data: dict) -> bool:
    status = str(data.get("status", "")).lower()
    return status in ("0", "error", "false") or "error" in data and "data" not in data


def _extract_error(data: dict) -> str:
    err = data.get("error") or data.get("Error") or _dig(data, ["data", "error"])
    if isinstance(err, dict):
        return err.get("message") or err.get("errorMessage") or json.dumps(err)[:300]
    if isinstance(err, list) and err:
        return "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in err)[:300]
    if isinstance(err, str):
        return err
    return data.get("message") or "e-Way Bill request was rejected by NIC."


# ── Public operations ────────────────────────────────────────────────────────
async def generate_ewb(payload: dict) -> dict:
    """Generate an e-Way Bill. ``payload`` must be a NIC-schema dict
    (see :func:`build_ewb_payload`). Returns the NIC data block including
    ``ewayBillNo``, ``ewayBillDate`` and ``validUpto``."""
    return await _call("GENERATE", EWB_CONFIG["generate_path"], payload)


async def get_ewb(ewb_number: str) -> dict:
    return await _call("GET", EWB_CONFIG["getewb_path"], {"ewbNo": _as_int(ewb_number)})


async def update_vehicle(payload: dict) -> dict:
    """payload: {ewbNo, vehicleNo, fromPlace, fromState, reasonCode, reasonRem, transMode}"""
    return await _call("UPDATE_VEHICLE", EWB_CONFIG["update_vehicle_path"], payload)


async def extend_validity(payload: dict) -> dict:
    """payload: {ewbNo, vehicleNo, fromPlace, fromState, remainingDistance,
    transMode, extnRsnCode, extnRemarks, ...}"""
    return await _call("EXTEND", EWB_CONFIG["extend_path"], payload)


async def cancel_ewb(ewb_number: str, reason_code: int, reason_remark: str) -> dict:
    payload = {"ewbNo": _as_int(ewb_number), "cancelRsnCode": reason_code,
               "cancelRmrk": reason_remark}
    return await _call("CANCEL", EWB_CONFIG["cancel_path"], payload)


def _as_int(v: Any) -> int:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return 0


# ── NIC payload builder ──────────────────────────────────────────────────────
SUPPLY_TYPE = {"OUTWARD": "O", "INWARD": "I"}
TRANS_MODE_CODE = {"ROAD": "1", "RAIL": "2", "AIR": "3", "SHIP": "4"}


def build_ewb_payload(invoice: dict, company: dict, customer: dict, transport: dict) -> dict:
    """Assemble the official NIC ``genewaybill`` request from our domain objects.

    All amounts/HSN/quantities are taken from the invoice line items. Distance,
    transporter and vehicle come from ``transport``. The shape follows the NIC
    EWB API v1.03 generate schema.
    """
    items = invoice.get("items", []) or []

    def _line_taxable(it: dict) -> float:
        return round(float(it.get("quantity") or 0) * float(it.get("unit_price") or 0), 2)

    taxable = round(sum(_line_taxable(it) for it in items), 2)
    cgst = float(invoice.get("cgst", 0) or 0)
    sgst = float(invoice.get("sgst", 0) or 0)
    igst = float(invoice.get("igst", 0) or 0)

    seller_state = str(company.get("state_code") or (company.get("gstin") or "27")[:2])
    buyer_state = str(customer.get("state_code") or (customer.get("gstin") or seller_state)[:2])

    return {
        "supplyType": SUPPLY_TYPE.get(transport.get("supply_type", "OUTWARD"), "O"),
        "subSupplyType": str(transport.get("sub_supply_type", "1")),  # 1 = Supply
        "docType": "INV",
        "docNo": invoice.get("invoice_number"),
        "docDate": _to_nic_date(invoice.get("created_at") or invoice.get("invoice_date")),
        "fromGstin": company.get("gstin") or EWB_CONFIG["gstin"],
        "fromTrdName": company.get("name", ""),
        "fromAddr1": (company.get("address") or "")[:120],
        "fromPlace": company.get("city") or company.get("state") or "",
        "fromPincode": _as_int(company.get("pincode")),
        "fromStateCode": _as_int(seller_state),
        "actFromStateCode": _as_int(seller_state),
        "toGstin": customer.get("gstin") or "URP",  # URP = unregistered person
        "toTrdName": customer.get("name") or invoice.get("customer_name", ""),
        "toAddr1": (customer.get("address") or "")[:120],
        "toPlace": customer.get("city") or customer.get("state") or invoice.get("place_of_supply", ""),
        "toPincode": _as_int(customer.get("pincode")),
        "toStateCode": _as_int(buyer_state),
        "actToStateCode": _as_int(buyer_state),
        "transactionType": int(transport.get("transaction_type", 1)),
        "totalValue": taxable,
        "cgstValue": cgst,
        "sgstValue": sgst,
        "igstValue": igst,
        "cessValue": 0.0,
        "totInvValue": round(taxable + cgst + sgst + igst, 2),
        "transporterId": transport.get("transporter_id", ""),
        "transporterName": transport.get("transporter_name", ""),
        "transDocNo": transport.get("trans_doc_no", ""),
        "transMode": TRANS_MODE_CODE.get(transport.get("transport_mode", "ROAD"), "1"),
        "transDistance": str(int(transport.get("distance_km") or 0)),
        "vehicleNo": transport.get("vehicle_number", ""),
        "vehicleType": transport.get("vehicle_type", "R"),  # R = Regular
        "itemList": [
            {
                "itemNo": idx + 1,
                "productName": it.get("product_name", ""),
                "productDesc": it.get("product_name", ""),
                "hsnCode": _as_int(it.get("hsn_code") or it.get("hsn_sac") or 0),
                "quantity": float(it.get("quantity") or 0),
                "qtyUnit": (it.get("unit") or "NOS").upper()[:3],
                "taxableAmount": _line_taxable(it),
                "cgstRate": float(it.get("gst_rate") or 0) / 2 if not igst else 0,
                "sgstRate": float(it.get("gst_rate") or 0) / 2 if not igst else 0,
                "igstRate": float(it.get("gst_rate") or 0) if igst else 0,
                "cessRate": 0,
            }
            for idx, it in enumerate(items)
        ],
    }


def _to_nic_date(value: Any) -> str:
    """NIC expects dd/mm/yyyy. Raises ValueError on unparseable input."""
    s = str(value or "")[:10]
    try:
        return datetime.fromisoformat(s).strftime("%d/%m/%Y")
    except Exception:
        raise ValueError(f"Invalid date value for NIC e-way bill: {value!r}")


# ── Deterministic sandbox simulator ──────────────────────────────────────────
# Used ONLY when is_configured() is False, so the app/tests run end-to-end
# without live NIC credentials. It mimics the NIC response shape. It performs no
# network/browser activity. Replace by setting EWB_BASE_URL + EWB_* creds.
def simulate_generate(payload: dict) -> dict:
    seed = f"{payload.get('docNo')}-{payload.get('fromGstin')}-{datetime.now(timezone.utc).isoformat()}"
    digest = hashlib.sha256(seed.encode()).hexdigest()
    # 12-digit EWB number, NIC-style.
    ewb_no = "3" + str(int(digest[:15], 16))[:11]
    now = datetime.now(timezone.utc)
    valid_upto = now + timedelta(days=1)  # < 100 km → 1 day validity
    return {
        "ewayBillNo": ewb_no,
        "ewayBillDate": now.strftime("%d/%m/%Y %I:%M:%S %p"),
        "validUpto": valid_upto.strftime("%d/%m/%Y %I:%M:%S %p"),
        "alert": "",
        "_simulated": True,
    }


def simulate_update_vehicle(ewb_no: str, vehicle_no: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "ewayBillNo": ewb_no,
        "vehicleUpdateDate": now.strftime("%d/%m/%Y %I:%M:%S %p"),
        "validUpto": (now + timedelta(days=1)).strftime("%d/%m/%Y %I:%M:%S %p"),
        "vehicleNo": vehicle_no,
        "_simulated": True,
    }


def simulate_extend(ewb_no: str, extra_days: int = 1) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "ewayBillNo": ewb_no,
        "validUpto": (now + timedelta(days=extra_days)).strftime("%d/%m/%Y %I:%M:%S %p"),
        "_simulated": True,
    }


def simulate_cancel(ewb_no: str) -> dict:
    return {
        "ewayBillNo": ewb_no,
        "cancelDate": datetime.now(timezone.utc).strftime("%d/%m/%Y %I:%M:%S %p"),
        "_simulated": True,
    }


def parse_nic_datetime(value: str | None) -> Optional[datetime]:
    """Parse a NIC dd/mm/yyyy[ hh:mm:ss AM] timestamp into an aware datetime."""
    if not value:
        return None
    s = value.strip()
    for fmt in ("%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
