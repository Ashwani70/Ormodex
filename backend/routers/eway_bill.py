"""
e-Way Bill router — official NIC/GSTN integration for sales invoices.

Endpoints (all server-side; the frontend never talks to NIC directly):
  POST /api/ewaybill/generate
  GET  /api/ewaybill/{ewb_number}
  POST /api/ewaybill/update-vehicle
  POST /api/ewaybill/extend-validity
  POST /api/ewaybill/cancel
  GET  /api/ewaybill/{ewb_number}/pdf
  GET  /api/ewaybill/status            (config/env health — no secrets)

Security:
  - Role-based access (admin full; accounts generate+view; dispatch update-vehicle;
    viewer read-only). See _PERMS below.
  - Rate-limited per user+action.
  - Every action writes an audit_logs row (sensitive values are masked by the
    audit layer and by nic_ewaybill.mask_sensitive in the integration logs).
  - Credentials live only in env vars and are never returned or logged.

Validation before generation:
  - GSTIN / HSN / PIN / vehicle-number format checks (core.gst_validators).
  - Invoice value must exceed Rs 50,000.
  - No existing active e-Way Bill for the same invoice (dedup).
  - If e-invoicing is configured/enabled, the invoice must already have an IRN.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from core.auth_utils import get_current_user, is_admin_role
from core.db import db
from core.models import (
    EwbGenerateRequest, EwbUpdateVehicleRequest, EwbExtendRequest, EwbCancelRequest,
)
from core import nic_ewaybill as nic
from core import gst_validators as gv
from core.pdf import build_ewaybill_pdf
from core.rate_limit import rate_limit, client_ip
from core.utils import now_iso, new_id, log_audit

router = APIRouter(prefix="/ewaybill", tags=["e-Way Bill"])

EWB_THRESHOLD = 50000.0  # Rupees — e-Way Bill mandatory above this consignment value.


# ── RBAC ─────────────────────────────────────────────────────────────────────
# Map each EWB capability to the roles allowed. Admin is always allowed.
# `module_permissions` (e.g. "sales"/"dispatch") also grant where noted, so the
# existing per-module permission model keeps working alongside named roles.
_PERMS: dict[str, set[str]] = {
    "view": {"admin", "accountant", "accounts", "dispatch", "viewer"},
    "generate": {"admin", "accountant", "accounts"},
    "update_vehicle": {"admin", "accountant", "accounts", "dispatch"},
    "extend": {"admin", "accountant", "accounts", "dispatch"},
    "cancel": {"admin", "accountant", "accounts"},
}


def _require(user: dict, capability: str) -> dict:
    role = (user.get("role") or "").lower()
    if is_admin_role(role):
        return user
    if role in _PERMS.get(capability, set()):
        return user
    # Fall back to module_permissions: "sales"/"gst" can generate/view/cancel,
    # "dispatch" can update vehicle / extend.
    perms = set(user.get("module_permissions", []) or [])
    if capability in ("view", "generate", "cancel", "extend") and ({"sales", "gst", "accounting"} & perms):
        return user
    if capability in ("view", "update_vehicle", "extend") and "dispatch" in perms:
        return user
    raise HTTPException(403, f"You do not have permission to {capability.replace('_', ' ')} e-Way Bills.")


def _rl(user: dict, request: Request, action: str, limit: int = 30, window: int = 60) -> None:
    """Per-user+action rate limit (defence-in-depth; NIC also throttles)."""
    key = f"ewb:{action}:{user.get('id') or client_ip(request)}"
    rate_limit(key, limit=limit, window_seconds=window, request=request)


# ── Helpers ──────────────────────────────────────────────────────────────────
async def _get_invoice(invoice_id: str) -> dict:
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return inv


async def _company() -> dict:
    return await db.companies.find_one({}, {"_id": 0}) or {}


async def _customer(inv: dict) -> dict:
    cid = inv.get("customer_id")
    if cid:
        c = await db.customers.find_one({"id": cid}, {"_id": 0})
        if c:
            return c
    return {"name": inv.get("customer_name", ""), "gstin": None}


async def _einvoicing_enabled() -> bool:
    """e-invoicing is 'on' if the IRP integration is configured, or an admin has
    flipped the einvoice_settings toggle."""
    try:
        from core import irp_einvoice
        if irp_einvoice.is_configured():
            return True
    except Exception:
        pass
    cfg = await db.einvoice_settings.find_one({"id": "global"}) or {}
    return bool(cfg.get("enabled"))


def _validate_for_generation(inv: dict, company: dict, customer: dict, req: EwbGenerateRequest) -> None:
    """Run all pre-generation format + business checks. Raises HTTP 400 with a
    precise, user-facing message on the first failure."""
    errors: list[str] = []

    # Seller GSTIN (must be present + valid).
    seller_gstin = company.get("gstin") or nic.EWB_CONFIG.get("gstin")
    ok, err = gv.validate_gstin(seller_gstin)
    if not ok:
        errors.append(f"Seller GSTIN: {err}")

    # Buyer GSTIN — optional (URP allowed) but validated when present.
    buyer_gstin = customer.get("gstin")
    if buyer_gstin:
        ok, err = gv.validate_gstin(buyer_gstin)
        if not ok:
            errors.append(f"Buyer GSTIN: {err}")

    # PIN codes (seller required; buyer required when registered/intra-doc).
    if company.get("pincode"):
        ok, err = gv.validate_pincode(company.get("pincode"))
        if not ok:
            errors.append(f"Seller PIN: {err}")
    if customer.get("pincode"):
        ok, err = gv.validate_pincode(customer.get("pincode"))
        if not ok:
            errors.append(f"Buyer PIN: {err}")

    # HSN code on every line.
    items = inv.get("items", []) or []
    if not items:
        errors.append("Invoice has no line items.")
    for idx, it in enumerate(items, start=1):
        hsn = it.get("hsn_code") or it.get("hsn_sac")
        ok, err = gv.validate_hsn(hsn)
        if not ok:
            errors.append(f"Item {idx} ({it.get('product_name','')}): {err}")

    # Vehicle number required + valid for road transport.
    if req.transport_mode == "ROAD":
        ok, err = gv.validate_vehicle_number(req.vehicle_number)
        if not ok:
            errors.append(err or "Valid vehicle number required for road transport.")

    # Distance must be positive.
    if not (float(req.distance_km or 0) > 0):
        errors.append("Transport distance (km) must be greater than 0.")

    if errors:
        raise HTTPException(400, {"message": "e-Way Bill validation failed", "errors": errors})


def _invoice_value(inv: dict) -> float:
    return float(inv.get("total") or inv.get("subtotal") or inv.get("taxable_value") or 0)


def _enrich_pdf_fields(ewb: dict, inv: dict, company: dict, customer: dict) -> dict:
    """Add the denormalised fields the PDF builder reads (kept off the hot path)."""
    ewb = dict(ewb)
    ewb.setdefault("from_name", company.get("name"))
    ewb.setdefault("from_gstin", company.get("gstin") or nic.EWB_CONFIG.get("gstin"))
    ewb.setdefault("from_address", company.get("address"))
    ewb.setdefault("from_place", company.get("city") or company.get("state"))
    ewb.setdefault("to_name", customer.get("name") or inv.get("customer_name"))
    ewb.setdefault("to_gstin", customer.get("gstin"))
    ewb.setdefault("to_address", customer.get("address"))
    ewb.setdefault("to_place", customer.get("city") or customer.get("state") or inv.get("place_of_supply"))
    ewb.setdefault("invoice_date", (inv.get("created_at") or "")[:10])
    ewb.setdefault("total_invoice_value", _invoice_value(inv))
    ewb.setdefault("items", inv.get("items", []))
    return ewb


# ── Generate ─────────────────────────────────────────────────────────────────
@router.post("/generate")
async def generate_eway_bill(
    req: EwbGenerateRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    _require(user, "generate")
    _rl(user, request, "generate", limit=20, window=60)

    inv = await _get_invoice(req.invoice_id)
    company = await _company()
    customer = await _customer(inv)

    # Dedup: an active e-Way Bill already exists for this invoice.
    existing = await db.eway_bills.find_one(
        {"invoice_id": req.invoice_id, "status": {"$nin": ["CANCELLED", "EXPIRED"]}},
        {"_id": 0},
    )
    if existing:
        raise HTTPException(409, f"An active e-Way Bill ({existing.get('ewb_number')}) already exists for this invoice.")

    # Threshold: consignment value must exceed Rs 50,000.
    if _invoice_value(inv) <= EWB_THRESHOLD:
        raise HTTPException(
            400, f"Invoice value (Rs {_invoice_value(inv):,.2f}) does not exceed Rs {EWB_THRESHOLD:,.0f}; "
                 "an e-Way Bill is not required."
        )

    # IRN gate: if e-invoicing is enabled, the IRN must be generated first.
    if await _einvoicing_enabled() and not inv.get("irn"):
        raise HTTPException(
            409, "e-Invoicing is enabled — generate the IRN (e-invoice) for this invoice before the e-Way Bill."
        )

    # Format + business validation.
    _validate_for_generation(inv, company, customer, req)

    transport = {
        "transport_mode": req.transport_mode,
        "distance_km": req.distance_km,
        "vehicle_number": gv.normalize_vehicle(req.vehicle_number) if req.vehicle_number else "",
        "vehicle_type": req.vehicle_type,
        "transporter_id": req.transporter_id or "",
        "transporter_name": req.transporter_name or "",
        "trans_doc_no": req.trans_doc_no or "",
        "supply_type": req.supply_type,
        "sub_supply_type": req.sub_supply_type,
        "transaction_type": req.transaction_type,
    }
    payload = nic.build_ewb_payload(inv, company, customer, transport)

    # Call NIC (or the deterministic sandbox simulator when not configured).
    try:
        if nic.is_configured():
            gov = await nic.generate_ewb(payload)
            simulated = False
        else:
            gov = nic.simulate_generate(payload)
            simulated = True
    except nic.EWBError as e:
        raise HTTPException(502, e.user_message)

    ewb_number = str(gov.get("ewayBillNo") or gov.get("ewbNo") or "")
    if not ewb_number:
        raise HTTPException(502, "NIC did not return an e-Way Bill number.")

    valid_dt = nic.parse_nic_datetime(gov.get("validUpto"))
    doc = {
        "id": new_id(),
        "invoice_id": req.invoice_id,
        "ewb_number": ewb_number,
        "ewb_date": gov.get("ewayBillDate"),
        "valid_until": gov.get("validUpto"),
        "valid_until_iso": valid_dt.isoformat() if valid_dt else None,
        "status": "GENERATED",
        "vehicle_number": transport["vehicle_number"],
        "transporter_id": transport["transporter_id"],
        "transporter_name": transport["transporter_name"],
        "transport_mode": req.transport_mode,
        "distance_km": req.distance_km,
        "trans_doc_no": transport["trans_doc_no"],
        "invoice_number": inv.get("invoice_number"),
        "invoice_date": (inv.get("created_at") or "")[:10],
        "total_invoice_value": _invoice_value(inv),
        "from_gstin": company.get("gstin") or nic.EWB_CONFIG.get("gstin"),
        "to_gstin": customer.get("gstin"),
        "qr_value": f"{ewb_number}/{company.get('gstin') or ''}/{gov.get('ewayBillDate','')}",
        "government_response": gov,
        "environment": nic.environment(),
        "simulated": simulated,
        "created_by": user["id"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.eway_bills.insert_one(doc)
    doc.pop("_id", None)

    # Keep the invoice's denormalised EWB fields and dispatch status in sync.
    await db.invoices.update_one(
        {"id": req.invoice_id},
        {"$set": {
            "ewb_number": ewb_number,
            "ewb_date": doc["ewb_date"],
            "ewb_status": "GENERATED",
            "vehicle_no": doc["vehicle_number"],
            "transporter_name": doc["transporter_name"],
            "distance_km": req.distance_km,
            "transport_mode": req.transport_mode,
            "dispatch_status": "READY_FOR_DISPATCH",
            "updated_at": now_iso(),
        }},
    )

    doc_id: str = str(doc["id"])
    await log_audit("CREATE", "eway_bills", doc_id, user, new_values=doc, ip=client_ip(request))
    return doc


# ── Get details ──────────────────────────────────────────────────────────────
@router.get("/status")
async def ewb_status(user: dict = Depends(get_current_user)):
    """Non-secret config/health for the UI (configured? sandbox/prod?)."""
    _require(user, "view")
    return nic.public_status()


@router.get("/by-invoice/{invoice_id}")
async def get_ewb_by_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    """Latest e-Way Bill for an invoice (drives the invoice-page section)."""
    _require(user, "view")
    ewb = await db.eway_bills.find_one(
        {"invoice_id": invoice_id}, {"_id": 0, "government_response": 0},
        sort=[("created_at", -1)],
    )
    return ewb or {"status": "NOT_GENERATED", "invoice_id": invoice_id}


@router.get("/{ewb_number}")
async def get_eway_bill(ewb_number: str, refresh: bool = False, user: dict = Depends(get_current_user)):
    _require(user, "view")
    ewb = await db.eway_bills.find_one({"ewb_number": ewb_number}, {"_id": 0})
    if not ewb:
        raise HTTPException(404, "e-Way Bill not found")

    # Optionally re-pull live status from NIC.
    if refresh and nic.is_configured():
        try:
            gov = await nic.get_ewb(ewb_number)
            await db.eway_bills.update_one(
                {"ewb_number": ewb_number},
                {"$set": {"government_response": gov, "updated_at": now_iso()}},
            )
            ewb["government_response"] = gov
        except nic.EWBError:
            pass  # keep stored copy on transient failure

    ewb = _mark_expired_if_due(ewb)
    return ewb


def _mark_expired_if_due(ewb: dict) -> dict:
    """Flip GENERATED → EXPIRED in the returned doc when past validity (display
    only; the stored row is updated lazily on the next write)."""
    if ewb.get("status") == "GENERATED" and ewb.get("valid_until_iso"):
        from datetime import datetime, timezone
        try:
            if datetime.fromisoformat(ewb["valid_until_iso"]) < datetime.now(timezone.utc):
                ewb = dict(ewb)
                ewb["status"] = "EXPIRED"
        except ValueError:
            pass
    return ewb


# ── Update vehicle ───────────────────────────────────────────────────────────
@router.post("/update-vehicle")
async def update_vehicle(
    req: EwbUpdateVehicleRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    _require(user, "update_vehicle")
    _rl(user, request, "update_vehicle")

    ewb = await db.eway_bills.find_one({"ewb_number": req.ewb_number})
    if not ewb:
        raise HTTPException(404, "e-Way Bill not found")
    if ewb.get("status") != "GENERATED":
        raise HTTPException(409, f"Cannot update vehicle on a {ewb.get('status')} e-Way Bill.")

    ok, err = gv.validate_vehicle_number(req.vehicle_number)
    if not ok:
        raise HTTPException(400, err)
    vehicle = gv.normalize_vehicle(req.vehicle_number)

    payload = {
        "ewbNo": int(req.ewb_number) if req.ewb_number.isdigit() else req.ewb_number,
        "vehicleNo": vehicle,
        "fromPlace": req.from_place,
        "fromState": int(req.from_state_code or "") if (req.from_state_code or "").isdigit() else 0,
        "reasonCode": req.reason_code,
        "reasonRem": req.reason_remark,
        "transMode": nic.TRANS_MODE_CODE.get(req.transport_mode or "", "1"),
        "transDocNo": req.trans_doc_no or "",
        "transDocDate": req.trans_doc_date or "",
    }
    try:
        gov = await nic.update_vehicle(payload) if nic.is_configured() \
            else nic.simulate_update_vehicle(req.ewb_number, vehicle)
    except nic.EWBError as e:
        raise HTTPException(502, e.user_message)

    old = {k: ewb.get(k) for k in ("vehicle_number", "transport_mode")}
    set_fields = {
        "vehicle_number": vehicle,
        "transport_mode": req.transport_mode,
        "trans_doc_no": req.trans_doc_no or ewb.get("trans_doc_no"),
        "government_response_vehicle": gov,
        "updated_at": now_iso(),
    }
    await db.eway_bills.update_one({"ewb_number": req.ewb_number}, {"$set": set_fields})
    await db.invoices.update_one(
        {"id": ewb.get("invoice_id")},
        {"$set": {"vehicle_no": vehicle, "transport_mode": req.transport_mode, "updated_at": now_iso()}},
    )
    await log_audit("UPDATE", "eway_bills", ewb["id"], user,
                    old_values=old, new_values=set_fields, ip=client_ip(request))
    return {"ewb_number": req.ewb_number, "vehicle_number": vehicle, "government_response": gov}


# ── Extend validity ──────────────────────────────────────────────────────────
@router.post("/extend-validity")
async def extend_validity(
    req: EwbExtendRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    _require(user, "extend")
    _rl(user, request, "extend")

    ewb = await db.eway_bills.find_one({"ewb_number": req.ewb_number})
    if not ewb:
        raise HTTPException(404, "e-Way Bill not found")
    if ewb.get("status") not in ("GENERATED", "EXPIRED"):
        raise HTTPException(409, f"Cannot extend a {ewb.get('status')} e-Way Bill.")

    payload = {
        "ewbNo": int(req.ewb_number) if req.ewb_number.isdigit() else req.ewb_number,
        "vehicleNo": gv.normalize_vehicle(req.vehicle_number) if req.vehicle_number else ewb.get("vehicle_number", ""),
        "fromPlace": req.from_place,
        "fromState": int(req.from_state_code or "") if (req.from_state_code or "").isdigit() else 0,
        "remainingDistance": str(int(req.remaining_distance_km or 0)),
        "extnRsnCode": req.reason_code,
        "extnRemarks": req.reason_remark,
        "transMode": nic.TRANS_MODE_CODE.get(req.transport_mode or "", "1"),
        "consignmentStatus": req.consignment_status,
    }
    try:
        gov = await nic.extend_validity(payload) if nic.is_configured() \
            else nic.simulate_extend(req.ewb_number)
    except nic.EWBError as e:
        raise HTTPException(502, e.user_message)

    valid_dt = nic.parse_nic_datetime(gov.get("validUpto"))
    set_fields = {
        "valid_until": gov.get("validUpto") or ewb.get("valid_until"),
        "valid_until_iso": valid_dt.isoformat() if valid_dt else ewb.get("valid_until_iso"),
        "status": "GENERATED",
        "government_response_extend": gov,
        "updated_at": now_iso(),
    }
    await db.eway_bills.update_one({"ewb_number": req.ewb_number}, {"$set": set_fields})
    await log_audit("UPDATE", "eway_bills", ewb["id"], user,
                    old_values={"valid_until": ewb.get("valid_until")},
                    new_values=set_fields, ip=client_ip(request))
    return {"ewb_number": req.ewb_number, "valid_until": set_fields["valid_until"], "government_response": gov}


# ── Cancel ───────────────────────────────────────────────────────────────────
@router.post("/cancel")
async def cancel_eway_bill(
    req: EwbCancelRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    _require(user, "cancel")
    _rl(user, request, "cancel")

    ewb = await db.eway_bills.find_one({"ewb_number": req.ewb_number})
    if not ewb:
        raise HTTPException(404, "e-Way Bill not found")
    if ewb.get("status") == "CANCELLED":
        raise HTTPException(409, "e-Way Bill is already cancelled.")

    try:
        gov = await nic.cancel_ewb(req.ewb_number, req.reason_code, req.reason_remark or "") \
            if nic.is_configured() else nic.simulate_cancel(req.ewb_number)
    except nic.EWBError as e:
        raise HTTPException(502, e.user_message)

    set_fields = {
        "status": "CANCELLED",
        "cancel_reason_code": req.reason_code,
        "cancel_reason_remark": req.reason_remark,
        "cancelled_at": now_iso(),
        "government_response_cancel": gov,
        "updated_at": now_iso(),
    }
    await db.eway_bills.update_one({"ewb_number": req.ewb_number}, {"$set": set_fields})
    await db.invoices.update_one(
        {"id": ewb.get("invoice_id")},
        {"$set": {"ewb_status": "CANCELLED", "updated_at": now_iso()}},
    )
    await log_audit("UPDATE", "eway_bills", ewb["id"], user,
                    old_values={"status": ewb.get("status")},
                    new_values=set_fields, ip=client_ip(request))
    return {"ewb_number": req.ewb_number, "status": "CANCELLED", "government_response": gov}


# ── PDF ──────────────────────────────────────────────────────────────────────
@router.get("/{ewb_number}/pdf")
async def eway_bill_pdf(ewb_number: str, user: dict = Depends(get_current_user)):
    _require(user, "view")
    ewb = await db.eway_bills.find_one({"ewb_number": ewb_number}, {"_id": 0})
    if not ewb:
        raise HTTPException(404, "e-Way Bill not found")

    inv = await db.invoices.find_one({"id": ewb.get("invoice_id")}, {"_id": 0}) or {}
    company = await _company()
    customer = await _customer(inv)
    pdf_bytes = build_ewaybill_pdf(_enrich_pdf_fields(ewb, inv, company, customer), company=company)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="EWB-{ewb_number}.pdf"'},
    )
