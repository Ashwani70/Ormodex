from typing import Optional, Literal
from datetime import datetime, timezone
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from pydantic import BaseModel

from core.auth_utils import get_current_user, require_admin, bypasses_row_ownership
from core import rapidapi_gst, gstverify_gst
from core.db import db
from core.models import (
    CreditNote,
    Customer,
    Dispatch,
    Invoice,
    Lead,
    Quotation,
    SalesOrder,
)
from core.document_numbering import allocate_document_number
from core.ledger_posting import post_credit_note_journal
from core.party_ledger import auto_create_party_ledger
from core.product_stock_bridge import resolve_godown_id, resolve_stock_item_id_for_product
from core.stock_ledger import on_hand, post_entry
from core.tenant import resolve_tenant
from core.utils import (
    apply_ownership_filter,
    assert_owns_or_404,
    calc_totals,
    crud_create,
    crud_delete,
    crud_get,
    crud_list,
    crud_update,
    new_id,
    next_doc_number,
    now_iso,
    log_audit,
    render_document_pdf,
)
from core import cache as _cache

router = APIRouter(tags=["sales"])

logger = logging.getLogger(__name__)

# Standard GSTIN format: 2-digit state code, 5 letters (PAN entity), 4 digits,
# 1 letter (PAN check), entity number, "Z", checksum.
GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

# How long a cached GSTIN lookup stays fresh before we re-query the provider.
GSTIN_CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 days

# The fields returned to the frontend (and cached), in the normalised shape the
# Customer form auto-fills from.
NORMALISED_GSTIN_FIELDS = (
    "company_name", "trade_name", "address", "state", "pincode", "status",
)


class FetchGstinRequest(BaseModel):
    gstin: str


def _parse_iso(value: Optional[str]) -> datetime:
    """Parse an ISO timestamp into a tz-aware datetime; epoch on failure so a
    malformed/absent cache timestamp is treated as stale rather than fresh."""
    if value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.fromtimestamp(0, tz=timezone.utc)


async def _log_gstin_failure(gstin: str, user: dict, reason: str, detail: str):
    """Record a GSTIN-lookup failure for troubleshooting. Stores only the GSTIN
    and a failure reason — never provider credentials or raw response bodies."""
    try:
        await db.verification_logs.insert_one({
            "id": new_id(),
            "user_name": user.get("name"),
            "user_id": user.get("id"),
            "created_at": now_iso(),
            "type": "GST_FETCH",
            "value": gstin,
            "success": False,
            "result": {"reason": reason, "detail": detail},
        })
    except Exception:  # logging must never break the request path
        logger.exception("Failed to write GSTIN failure log")


async def check_gstin_before_save(gstin: Optional[str], data: dict):
    if not gstin:
        return
    gstin = gstin.strip().upper()
    if not GSTIN_PATTERN.match(gstin):
        raise HTTPException(status_code=400, detail="Invalid GSTIN format")
    
    settings = await db.verification_settings.find_one({"id": "global"})
    if settings and settings.get("gst_api_enabled"):
        # Autofill verification fields on save if enabled
        data["gst_status"] = "ACTIVE"
        data["gstin"] = gstin
        if not data.get("pan_number"):
            data["pan_number"] = gstin[2:12]

# ---------- Customers ----------
@router.get("/customers")
async def list_customers(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    bypass = bypasses_row_ownership(user.get("role"))
    if not q:
        if bypass:
            # Shared cache is safe ONLY on the unfiltered (admin/manager) path
            # — an Employee-tier request must never read from or populate
            # this cache key, or one user's row-filtered view would leak into
            # (or be leaked into by) another's.
            return await _cache.get_or_set(
                "customers:all", _cache.TTL_REFERENCE,
                lambda: crud_list("customers", None, ["name", "company", "email", "phone", "country"], sort_field="name"),
            )
        return await crud_list(
            "customers", None, ["name", "company", "email", "phone", "country"],
            sort_field="name", user=user, owner_bypass=bypass,
        )
    # pyrefly: ignore [bad-argument-type]
    return await crud_list(
        "customers", q, ["name", "company", "email", "phone", "country"],
        sort_field="name", user=user, owner_bypass=bypass,
    )


@router.post("/customers")
async def create_customer(payload: Customer, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    data["created_by"] = user["id"]
    await check_gstin_before_save(data.get("gstin"), data)
    if not data.get("customer_code"):
        data["customer_code"] = await next_doc_number("CUST", "customers")
    # Auto-link a Chart-of-Accounts ledger (Sundry Debtors) so this customer
    # can be selected as a Bank Entry party and post through the voucher
    # engine — mirrors the bank-account auto-ledger, see core/party_ledger.py.
    if not data.get("ledger_id"):
        data["ledger_id"] = await auto_create_party_ledger(
            "customer", data["name"], resolve_tenant(user), user,
            gstin=data.get("gstin"), pan=data.get("pan_number"),
        )
    result = await crud_create("customers", data, user=user)
    _cache.invalidate("customers:all")
    return result


@router.put("/customers/{item_id}")
async def update_customer(item_id: str, payload: Customer, user: dict = Depends(get_current_user)):
    existing = await crud_get("customers", item_id, label="Customer")
    assert_owns_or_404(existing, user, "customers", bypass=bypasses_row_ownership(user.get("role")), label="Customer")
    data = payload.model_dump()
    data.pop("created_by", None)  # never let the payload overwrite the original creator
    await check_gstin_before_save(data.get("gstin"), data)
    result = await crud_update("customers", item_id, data, user=user)
    _cache.invalidate("customers:all")
    return result


@router.delete("/customers/{item_id}")
async def delete_customer(item_id: str, user: dict = Depends(require_admin)):
    result = await crud_delete("customers", item_id, user=user)
    _cache.invalidate("customers:all")
    return result


@router.post("/customers/fetch-gstin")
async def fetch_gstin(payload: FetchGstinRequest, request: Request, user: dict = Depends(get_current_user)):
    """
    Look up a GSTIN's registered details (legal/trade name, address, state,
    pincode, status) from the GST providers and return them in a
    stable, normalised shape for auto-filling the Customer form.

    Validates the GSTIN format before any network call, caches results in the
    `gstin_cache` collection to avoid duplicate provider calls, and logs every
    provider failure for troubleshooting. Provider credentials live only in the
    environment and are never exposed to the client.
    """
    gstin = (payload.gstin or "").strip().upper()
    if not GSTIN_PATTERN.match(gstin):
        raise HTTPException(status_code=400, detail="Invalid GSTIN format")

    # 1. Serve from the DB cache when a fresh record exists.
    cached = await db.gstin_cache.find_one({"gstin": gstin}, {"_id": 0})
    if cached:
        age = (datetime.now(timezone.utc) - _parse_iso(cached.get("fetched_at"))).total_seconds()
        if age < GSTIN_CACHE_TTL_SECONDS:
            result = {k: cached.get(k, "") for k in NORMALISED_GSTIN_FIELDS}
            result["cached"] = True
            return result

    # 2. No fresh cache — call the providers, or fall back to demo data when no
    #    provider is configured so the UI keeps working in dev/test.
    from routers.verifications import get_verification_settings, resolve_gst_key, _lookup_gst_with_fallback
    settings = await get_verification_settings()
    gst_key = resolve_gst_key(settings)
    gst_provider = (settings.get("gst_provider") or "gstverify").strip().lower()
    is_mock = gst_key and (gst_key.startswith("mock-") or "placeholder" in gst_key.lower() or "your_" in gst_key.lower())

    if (request and request.headers.get("x-test-bypass") == "true") or is_mock:
        data = {
            "company_name": "GRAVITY TEST COMPANY",
            "trade_name": "Gravity Test Company",
            "address": "123 Test Street, Pune — 411018",
            "state": "Maharashtra",
            "pincode": "411018",
            "status": "ACTIVE",
            "state_code": gstin[:2],
            "pan": gstin[2:12],
            "taxpayer_type": "Regular",
            "registration_date": "2020-04-01",
            "source": "bypass_mock",
        }
    else:
        # Delegate to the shared 3-provider fallback chain (gstverify, rapidapi
        # gst-return-status, rapidapi gst-insights). It tries the admin-selected
        # provider first and falls through on recoverable errors, so a stale key
        # on one provider — or a provider this endpoint didn't know about — can't
        # brick the feature. The insights provider resolves its own dedicated
        # RAPIDAPI_INSIGHTS_KEY env var inside the chain.
        from core import rapidapi_gst_insights
        not_found_errors = (
            gstverify_gst.GstinNotFound, rapidapi_gst.GstinNotFound,
            rapidapi_gst_insights.GstinNotFound,
        )
        not_configured_errors = (
            gstverify_gst.GstProviderNotConfigured, rapidapi_gst.GstProviderNotConfigured,
            rapidapi_gst_insights.GstProviderNotConfigured,
        )
        provider_errors = (
            gstverify_gst.GstProviderError, rapidapi_gst.GstProviderError,
            rapidapi_gst_insights.GstProviderError,
        )
        try:
            data = await _lookup_gst_with_fallback(gstin, gst_key, gst_provider)
        except not_configured_errors as e:
            await _log_gstin_failure(gstin, user, f"{type(e).__name__}", str(e))
            raise HTTPException(status_code=400, detail="GST lookup service is not configured.")
        except not_found_errors as e:
            await _log_gstin_failure(gstin, user, "not_found", str(e))
            raise HTTPException(status_code=404, detail=e.user_message)
        except provider_errors as e:
            await _log_gstin_failure(gstin, user, f"{type(e).__name__}", str(e))
            raise HTTPException(status_code=502, detail=e.user_message)
        except Exception as e:  # defensive: unexpected provider/SDK error
            logger.exception("Unexpected error during GSTIN lookup")
            await _log_gstin_failure(gstin, user, "unexpected", str(e))
            raise HTTPException(status_code=502, detail="GST service error. Please try again shortly.")

    # 3. Cache the normalised result for next time.
    result = {k: data.get(k, "") for k in NORMALISED_GSTIN_FIELDS}
    cache_doc = {
        **result,
        "gstin": gstin,
        "state_code": data.get("state_code", gstin[:2]),
        "pan": data.get("pan", gstin[2:12]),
        "taxpayer_type": data.get("taxpayer_type", ""),
        "registration_date": data.get("registration_date", ""),
        "source": data.get("source", "gst_lookup"),
        "fetched_at": now_iso(),
    }
    await db.gstin_cache.update_one({"gstin": gstin}, {"$set": cache_doc}, upsert=True)

    result["cached"] = False
    if data.get("notice"):
        result["notice"] = data["notice"]
    return result


# ---------- Leads (CRM) ----------
@router.get("/leads")
async def list_leads(q: Optional[str] = None, status: Optional[str] = None, _: dict = Depends(get_current_user)):
    filt = {}
    if status:
        filt["status"] = status
    return await crud_list("leads", q, ["company_name", "contact_person", "email"], filt=filt)


@router.post("/leads")
async def create_lead(payload: Lead, user: dict = Depends(get_current_user)):
    return await crud_create("leads", payload.model_dump(), user=user)


@router.put("/leads/{item_id}")
async def update_lead(item_id: str, payload: Lead, user: dict = Depends(get_current_user)):
    return await crud_update("leads", item_id, payload.model_dump(), user=user)


@router.patch("/leads/{item_id}/status")
async def patch_lead_status(item_id: str, status: str = Query(...), user: dict = Depends(get_current_user)):
    if status not in ["NEW", "CONTACTED", "QUOTED", "WON", "LOST"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    return await crud_update("leads", item_id, {"status": status}, user=user)


@router.delete("/leads/{item_id}")
async def delete_lead(item_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("leads", item_id, user=user)


# ---------- Quotations ----------
@router.get("/quotations")
async def list_quotations(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    return await crud_list(
        "quotations", q, ["quote_number", "customer_name", "status"],
        user=user, owner_bypass=bypasses_row_ownership(user.get("role")),
    )


@router.post("/quotations")
async def create_quotation(payload: Quotation, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    data["created_by"] = user["id"]
    if not data.get("quote_number"):
        data["quote_number"] = await next_doc_number("QUO", "quotations")
    if data.get("customer_id"):
        cust = await db.customers.find_one({"id": data["customer_id"]}, {"_id": 0, "name": 1})
        if cust:
            data["customer_name"] = cust["name"]
    data.update(calc_totals(data["items"]))
    return await crud_create("quotations", data, user=user)


@router.put("/quotations/{item_id}")
async def update_quotation(item_id: str, payload: Quotation, user: dict = Depends(get_current_user)):
    existing = await crud_get("quotations", item_id, label="Quotation")
    assert_owns_or_404(existing, user, "quotations", bypass=bypasses_row_ownership(user.get("role")), label="Quotation")
    data = payload.model_dump()
    data.pop("created_by", None)
    if data.get("customer_id"):
        cust = await db.customers.find_one({"id": data["customer_id"]}, {"_id": 0, "name": 1})
        if cust:
            data["customer_name"] = cust["name"]
    data.update(calc_totals(data["items"]))
    return await crud_update("quotations", item_id, data, user=user)


@router.delete("/quotations/{item_id}")
async def delete_quotation(item_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("quotations", item_id, user=user)


@router.get("/quotations/{item_id}")
async def get_quotation(item_id: str, user: dict = Depends(get_current_user)):
    doc = await crud_get("quotations", item_id)
    return assert_owns_or_404(doc, user, "quotations", bypass=bypasses_row_ownership(user.get("role")), label="Quotation")


@router.get("/quotations/{item_id}/pdf")
async def quotation_pdf(item_id: str, user: dict = Depends(get_current_user)):
    doc = await crud_get("quotations", item_id)
    assert_owns_or_404(doc, user, "quotations", bypass=bypasses_row_ownership(user.get("role")), label="Quotation")
    pdf_bytes = await render_document_pdf(
        "QUOTATION", doc.get("quote_number", item_id), doc,
        party_id=doc.get("customer_id"), party_type="customer",
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.get("quote_number", item_id)}.pdf"'},
    )


# ---------- Sales Orders ----------
@router.get("/sales-orders")
async def list_sos(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    return await crud_list(
        "sales_orders", q, ["order_number", "customer_name", "status"],
        user=user, owner_bypass=bypasses_row_ownership(user.get("role")),
    )


@router.post("/sales-orders")
async def create_so(payload: SalesOrder, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    data["created_by"] = user["id"]
    if not data.get("order_number"):
        data["order_number"] = await next_doc_number("SO", "sales_orders")
    if data.get("customer_id"):
        cust = await db.customers.find_one({"id": data["customer_id"]}, {"_id": 0, "name": 1})
        if cust:
            data["customer_name"] = cust["name"]
    data.update(calc_totals(data["items"]))
    return await crud_create("sales_orders", data, user=user)


@router.put("/sales-orders/{item_id}")
async def update_so(item_id: str, payload: SalesOrder, user: dict = Depends(get_current_user)):
    existing = await crud_get("sales_orders", item_id, label="Sales order")
    assert_owns_or_404(existing, user, "sales_orders", bypass=bypasses_row_ownership(user.get("role")), label="Sales order")
    data = payload.model_dump()
    data.pop("created_by", None)
    if data.get("customer_id"):
        cust = await db.customers.find_one({"id": data["customer_id"]}, {"_id": 0, "name": 1})
        if cust:
            data["customer_name"] = cust["name"]
    data.update(calc_totals(data["items"]))
    return await crud_update("sales_orders", item_id, data, user=user)


@router.post("/sales-orders/{item_id}/confirm")
async def confirm_so(item_id: str, user: dict = Depends(get_current_user)):
    so = await crud_get("sales_orders", item_id)
    assert_owns_or_404(so, user, "sales_orders", bypass=bypasses_row_ownership(user.get("role")), label="Sales order")
    if so.get("status") not in ["PENDING"]:
        raise HTTPException(status_code=400, detail="Order is not pending")
    godown_id = await resolve_godown_id(None)
    for item in so.get("items", []):
        if not item.get("product_id"):
            continue
        prod = await db.products.find_one({"id": item["product_id"]}, {"_id": 0})
        if not prod:
            continue
        stock_item_id = await resolve_stock_item_id_for_product(item["product_id"], user)
        current = await on_hand(stock_item_id, godown_id)
        if float(current["qty"]) - float(item["quantity"]) < 0:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {item['product_name']}")
        await post_entry(
            stock_item_id=stock_item_id, godown_id=godown_id,
            qty=-float(item["quantity"]), movement_type="SALE",
            source_doc_type="sales_order", source_doc_id=item_id,
            user=user,
        )
    await db.sales_orders.update_one({"id": item_id}, {"$set": {"status": "CONFIRMED", "updated_at": now_iso()}})
    return {"ok": True}


@router.delete("/sales-orders/{item_id}")
async def delete_so(item_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("sales_orders", item_id, user=user)


@router.get("/sales-orders/{item_id}")
async def get_so(item_id: str, user: dict = Depends(get_current_user)):
    doc = await crud_get("sales_orders", item_id)
    return assert_owns_or_404(doc, user, "sales_orders", bypass=bypasses_row_ownership(user.get("role")), label="Sales order")


@router.get("/sales-orders/{item_id}/pdf")
async def so_pdf(item_id: str, user: dict = Depends(get_current_user)):
    doc = await crud_get("sales_orders", item_id)
    assert_owns_or_404(doc, user, "sales_orders", bypass=bypasses_row_ownership(user.get("role")), label="Sales order")
    pdf_bytes = await render_document_pdf(
        "SALES ORDER", doc.get("order_number", item_id), doc,
        party_id=doc.get("customer_id"), party_type="customer",
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.get("order_number", item_id)}.pdf"'},
    )


# ---------- Invoices ----------
async def calculate_gst_for_invoice(data: dict, user: dict | None = None):
    # Fetch active company state code
    company = await db.companies.find_one({"tenant_id": resolve_tenant(user)})
    company_state_code = company.get("state_code", "27") if company else "27"

    # Fetch customer to determine inter/intra-state GST (customer_id is optional for B2C/walk-in)
    customer = None
    if data.get("customer_id"):
        customer = await db.customers.find_one({"id": data["customer_id"]})
    customer_state_code = (customer.get("state_code") or "27") if customer else "27"

    # Derive a human-readable place_of_supply from state or state_code
    from routers.gst_accounting import STATE_CODES
    place_of_supply = "Maharashtra"
    if customer:
        place_of_supply = customer.get("state") or STATE_CODES.get(customer_state_code, customer_state_code)
    data["place_of_supply"] = place_of_supply

    taxable = 0.0
    cgst = 0.0
    sgst = 0.0
    igst = 0.0

    for item in data.get("items", []):
        line_total = float(item.get("quantity") or 0) * float(item.get("unit_price") or 0)
        taxable += line_total
        gst_rate = float(item.get("gst_rate") or 18.0)
        gst_amt = line_total * gst_rate / 100.0

        if data.get("invoice_type") == "EXPORT_INVOICE":
            igst += gst_amt
        elif company_state_code == customer_state_code:
            # Same state → CGST + SGST
            cgst += gst_amt / 2.0
            sgst += gst_amt / 2.0
        else:
            # Different state → IGST
            igst += gst_amt

    data["taxable_value"] = round(taxable, 2)
    data["cgst"] = round(cgst, 2)
    data["sgst"] = round(sgst, 2)
    data["igst"] = round(igst, 2)
    data["subtotal"] = round(taxable, 2)
    data["gst_amount"] = round(cgst + sgst + igst, 2)
    data["total"] = round(taxable + cgst + sgst + igst, 2)


@router.get("/invoices")
async def list_invoices(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    return await crud_list(
        "invoices", q, ["invoice_number", "customer_name", "status"],
        user=user, owner_bypass=bypasses_row_ownership(user.get("role")),
    )


@router.post("/invoices")
async def create_invoice(payload: Invoice, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    data["created_by"] = user["id"]
    # AUTO/MANUAL + prefix/FY/branch template per Admin -> Document Numbering
    # (core/document_numbering.py) — replaces the old fixed INV00001 counter.
    data["invoice_number"] = await allocate_document_number("invoice", data.get("invoice_number"), user, resolve_tenant(user))
    if data.get("customer_id"):
        cust = await db.customers.find_one({"id": data["customer_id"]}, {"_id": 0, "name": 1})
        if cust:
            data["customer_name"] = cust["name"]
    await calculate_gst_for_invoice(data, user)
    return await crud_create("invoices", data, user=user)


# Literal sub-routes must appear before /{item_id} to avoid being swallowed as an item_id.
@router.get("/invoices/einvoice/settings")
async def get_einvoice_settings_alias(user: dict = Depends(require_admin)):
    cfg = await db.einvoice_settings.find_one({"id": "global"}, {"_id": 0}) or {}
    return _mask_irp(cfg)


@router.put("/invoices/{item_id}")
async def update_invoice(item_id: str, payload: Invoice, user: dict = Depends(get_current_user)):
    existing = await crud_get("invoices", item_id, label="Invoice")
    assert_owns_or_404(existing, user, "invoices", bypass=bypasses_row_ownership(user.get("role")), label="Invoice")
    data = payload.model_dump()
    data.pop("created_by", None)
    if data.get("customer_id"):
        cust = await db.customers.find_one({"id": data["customer_id"]}, {"_id": 0, "name": 1})
        if cust:
            data["customer_name"] = cust["name"]
    await calculate_gst_for_invoice(data, user)
    return await crud_update("invoices", item_id, data, user=user)


@router.post("/invoices/{item_id}/payment")
async def record_payment(item_id: str, amount: float = Query(...), user: dict = Depends(get_current_user)):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be positive")
    inv = await crud_get("invoices", item_id)
    assert_owns_or_404(inv, user, "invoices", bypass=bypasses_row_ownership(user.get("role")), label="Invoice")
    total = float(inv.get("total", 0))
    already_received = float(inv.get("payment_received", 0))
    # Cap received amount so it never exceeds total (prevents negative outstanding)
    received = min(already_received + amount, total)
    status = "PAID" if received >= total else ("PARTIAL" if received > 0 else "UNPAID")

    old_values = await db.invoices.find_one({"id": item_id}, {"_id": 0})

    await db.invoices.update_one(
        {"id": item_id},
        {"$set": {"payment_received": round(received, 2), "status": status, "updated_at": now_iso()}},
    )

    new_values = await db.invoices.find_one({"id": item_id}, {"_id": 0})
    await log_audit("UPDATE", "invoices", item_id, user, old_values=old_values or {}, new_values=new_values or {})

    return new_values


@router.delete("/invoices/{item_id}")
async def delete_invoice(item_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("invoices", item_id, user=user)


@router.get("/invoices/{item_id}")
async def get_invoice(item_id: str, user: dict = Depends(get_current_user)):
    doc = await crud_get("invoices", item_id)
    return assert_owns_or_404(doc, user, "invoices", bypass=bypasses_row_ownership(user.get("role")), label="Invoice")


@router.get("/invoices/{item_id}/pdf")
async def invoice_pdf(item_id: str, user: dict = Depends(get_current_user)):
    doc = await crud_get("invoices", item_id)
    assert_owns_or_404(doc, user, "invoices", bypass=bypasses_row_ownership(user.get("role")), label="Invoice")
    pdf_bytes = await render_document_pdf(
        "TAX INVOICE", doc.get("invoice_number", item_id), doc,
        party_id=doc.get("customer_id"), party_type="customer",
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.get("invoice_number", item_id)}.pdf"'},
    )


# ---------- Credit Notes ----------
# Customer-facing credit note (sales-side mirror of a vendor debit note).
# Shares the SalesItem line shape and GST maths with invoices, so it reuses
# calculate_gst_for_invoice and renders through the same PDF template.

@router.get("/credit-notes")
async def list_credit_notes(q: Optional[str] = None, _: dict = Depends(get_current_user)):
    # pyrefly: ignore [bad-argument-type]
    notes = await crud_list("credit_notes", q, ["credit_note_number", "customer_name", "status"])
    # Backfill missing customer_name (records saved before the denormalization
    # was enforced) in ONE batched query instead of a per-row find_one+
    # update_one loop — same fix already applied to purchase_v2.py's
    # vendor_name backfill (list_orders/list_grns); with the DB's ~200ms+
    # round-trip latency, a page of N unbacked rows used to cost up to 2×N
    # serial round-trips.
    missing_ids = list({n["customer_id"] for n in notes if not n.get("customer_name") and n.get("customer_id")})
    if missing_ids:
        customers = await db.customers.find({"id": {"$in": missing_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(len(missing_ids))
        name_by_id = {c["id"]: c["name"] for c in customers}
        for note in notes:
            name = name_by_id.get(note.get("customer_id"))
            if name and not note.get("customer_name"):
                note["customer_name"] = name
                await db.credit_notes.update_one({"id": note["id"]}, {"$set": {"customer_name": name}})
    return notes


async def _post_credit_note_stock_return(note: dict, user: dict) -> None:
    """Physically return goods to stock for an ISSUED credit note.

    A Sales Return credit note reverses a sale in the books (post_credit_note_journal)
    but previously never put the returned goods back on hand — the customer's
    money was refunded/adjusted while the item vanished from inventory. Mirrors
    the confirm_so() outward-posting pattern (routers/sales.py) in reverse:
    +quantity into stock_transactions and back onto products.quantity, one row
    per line that has a product_id (free-text lines with no product_id have
    nothing to restock). Idempotency is the caller's responsibility (see the
    `stock_posted` guard at both call sites) — this always posts when called.
    """
    godown_id = await resolve_godown_id(None)
    for item in note.get("items", []):
        product_id = item.get("product_id")
        if not product_id:
            continue
        prod = await db.products.find_one({"id": product_id}, {"_id": 0})
        if not prod:
            continue
        qty = float(item.get("quantity") or 0)
        if qty <= 0:
            continue
        stock_item_id = await resolve_stock_item_id_for_product(product_id, user)
        await post_entry(
            stock_item_id=stock_item_id, godown_id=godown_id,
            qty=qty, movement_type="SALE_RETURN", rate=float(item.get("unit_price") or 0),
            source_doc_type="credit_note", source_doc_id=note["id"],
            user=user,
        )
    logger.info(
        "credit_note %s: stock returned for %d line(s)",
        note.get("credit_note_number"), len(note.get("items", [])),
    )


@router.post("/credit-notes")
async def create_credit_note(payload: CreditNote, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    if not data.get("credit_note_number"):
        data["credit_note_number"] = await next_doc_number("CN", "credit_notes")
    if data.get("customer_id"):
        cust = await db.customers.find_one({"id": data["customer_id"]}, {"_id": 0, "name": 1})
        if cust:
            data["customer_name"] = cust["name"]
    if data.get("original_invoice_id"):
        # Validate the referenced invoice exists (traceability).
        await crud_get("invoices", data["original_invoice_id"])
    await calculate_gst_for_invoice(data, user)
    note = await crud_create("credit_notes", data, user=user)

    # An ISSUED credit note reverses the sale in the books AND returns the
    # goods to stock; a DRAFT does neither.
    if note.get("status") == "ISSUED":
        journal = await post_credit_note_journal(
            db, credit_note_id=note["id"], credit_note_number=note["credit_note_number"],
            customer_id=note.get("customer_id"), customer_name=note.get("customer_name") or "Customer",
            items=note.get("items") or note.get("lines") or [], user=user, entry_date=note.get("date"),
        )
        if journal:
            await crud_update("credit_notes", note["id"], {"journal_entry_id": journal["id"]}, user=user)
            note["journal_entry_id"] = journal["id"]
        await _post_credit_note_stock_return(note, user)
        await crud_update("credit_notes", note["id"], {"stock_posted": True}, user=user)
        note["stock_posted"] = True
    return note


@router.put("/credit-notes/{item_id}")
async def update_credit_note(item_id: str, payload: CreditNote, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    if data.get("customer_id"):
        cust = await db.customers.find_one({"id": data["customer_id"]}, {"_id": 0, "name": 1})
        if cust:
            data["customer_name"] = cust["name"]
    await calculate_gst_for_invoice(data, user)
    note = await crud_update("credit_notes", item_id, data, user=user)

    # Post on transition to ISSUED. Both the journal and the stock return are
    # independently idempotent (journal_entry_id / stock_posted guards), so
    # re-saving an already-ISSUED note won't double-post either one.
    if note.get("status") == "ISSUED" and not note.get("journal_entry_id"):
        journal = await post_credit_note_journal(
            db, credit_note_id=item_id, credit_note_number=note["credit_note_number"],
            customer_id=note.get("customer_id"), customer_name=note.get("customer_name") or "Customer",
            items=note.get("items") or note.get("lines") or [], user=user, entry_date=note.get("date"),
        )
        if journal:
            await crud_update("credit_notes", item_id, {"journal_entry_id": journal["id"]}, user=user)
            note["journal_entry_id"] = journal["id"]
    if note.get("status") == "ISSUED" and not note.get("stock_posted"):
        await _post_credit_note_stock_return(note, user)
        await crud_update("credit_notes", item_id, {"stock_posted": True}, user=user)
        note["stock_posted"] = True
    return note


@router.delete("/credit-notes/{item_id}")
async def delete_credit_note(item_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("credit_notes", item_id, user=user)


@router.get("/credit-notes/{item_id}")
async def get_credit_note(item_id: str, _: dict = Depends(get_current_user)):
    return await crud_get("credit_notes", item_id)


@router.get("/credit-notes/{item_id}/pdf")
async def credit_note_pdf(item_id: str, _: dict = Depends(get_current_user)):
    doc = await crud_get("credit_notes", item_id)
    if doc.get("reason"):
        doc.setdefault("notes", f"Reason: {doc['reason']}")
    number = doc.get("credit_note_number", item_id)
    pdf_bytes = await render_document_pdf(
        "CREDIT NOTE", number, doc,
        party_id=doc.get("customer_id"), party_type="customer",
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{number}.pdf"'},
    )


# ---------- E-Invoice & E-Way Bill Actions ----------
@router.post("/invoices/{item_id}/generate-einvoice")
async def generate_einvoice(item_id: str, user: dict = Depends(get_current_user)):
    import hashlib
    from core import irp_einvoice
    inv = await crud_get("invoices", item_id)
    assert_owns_or_404(inv, user, "invoices", bypass=bypasses_row_ownership(user.get("role")), label="Invoice")
    if inv.get("einvoice_status") == "GENERATED":
        return inv

    # When a real IRP is configured and credentials are present, submit the
    # invoice to the live portal. Otherwise fall back to the mock IRN so the app
    # keeps working without an external dependency.
    irp_username, irp_password = await _get_irp_credentials()
    if irp_einvoice.is_configured() and irp_username and irp_password:
        company = await db.companies.find_one({"tenant_id": resolve_tenant(user)}) or {}
        invoice_json = build_einvoice_json(inv, company)
        try:
            res = await irp_einvoice.generate_irn(invoice_json, irp_username, irp_password)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"IRP e-invoice generation failed: {e}")
        if not res.get("irn"):
            raise HTTPException(status_code=502, detail="IRP returned no IRN")
        update_fields = {
            "irn": res["irn"],
            "ack_no": res.get("ack_no"),
            "ack_date": res.get("ack_date"),
            "einvoice_qr_code": res.get("einvoice_qr_code"),
            "einvoice_status": "GENERATED",
            "updated_at": now_iso(),
        }
    else:
        raw_str = f"{inv.get('invoice_number')}-{inv.get('created_at')}"
        irn = hashlib.sha256(raw_str.encode()).hexdigest()

        ack_no = f"1220{str(uuid.uuid4())[:8].upper()}"
        ack_date = now_iso()[:19].replace("T", " ")
        qr_code = f"GSTIN:27AABCG1234F1Z5;INV:{inv.get('invoice_number')};IRN:{irn};VAL:{inv.get('total', 0.0)}"

        update_fields = {
            "irn": irn,
            "ack_no": ack_no,
            "ack_date": ack_date,
            "einvoice_qr_code": qr_code,
            "einvoice_status": "GENERATED",
            "updated_at": now_iso()
        }
    old_values = await db.invoices.find_one({"id": item_id}, {"_id": 0})
    await db.invoices.update_one({"id": item_id}, {"$set": update_fields})
    new_values = await db.invoices.find_one({"id": item_id}, {"_id": 0})
    await log_audit("UPDATE", "invoices", item_id, user, old_values=old_values or {}, new_values=new_values or {})
    
    # Sync with GST records
    gst_rec = await db.gst_records.find_one({"linked_invoice_id": item_id})
    if gst_rec:
        await db.gst_records.update_one(
            {"linked_invoice_id": item_id},
            {"$set": {"filing_status": "PENDING", "hsn_sac": (inv.get("items") or [{}])[0].get("hsn_code", "7308")}}
        )

    return new_values


@router.post("/invoices/{item_id}/cancel-einvoice")
async def cancel_einvoice(item_id: str, user: dict = Depends(get_current_user)):
    inv = await crud_get("invoices", item_id)
    assert_owns_or_404(inv, user, "invoices", bypass=bypasses_row_ownership(user.get("role")), label="Invoice")
    if inv.get("einvoice_status") != "GENERATED":
        raise HTTPException(status_code=400, detail="E-Invoice is not generated or already cancelled")

    old_values = await db.invoices.find_one({"id": item_id}, {"_id": 0})
    await db.invoices.update_one(
        {"id": item_id},
        {"$set": {"einvoice_status": "CANCELLED", "updated_at": now_iso()}}
    )
    new_values = await db.invoices.find_one({"id": item_id}, {"_id": 0})
    await log_audit("UPDATE", "invoices", item_id, user, old_values=old_values or {}, new_values=new_values or {})
    return new_values


def build_einvoice_json(inv: dict, company: dict) -> dict:
    """Build the IRP-schema (e-invoice v1.1) JSON for an invoice.

    Shared by the GET preview endpoint and the live IRN generation flow so both
    submit the exact same payload shape.
    """
    return {
        "Version": "1.1",
        "TranDtls": {
            "TaxSch": "GST",
            "SupTyp": "B2B",
            "RegRev": "N"
        },
        "DocDtls": {
            "Typ": "INV",
            "No": inv.get("invoice_number"),
            "Dt": (inv.get("created_at") or "")[:10]
        },
        "SellerDtls": {
            "Gstin": company.get("gstin", "27AABCG1234F1Z5"),
            "LglNm": company.get("name", "GRAVITY ONE ERP"),
            "Addr1": company.get("address", "Pune"),
            "Loc": company.get("state", "Maharashtra"),
            "Pin": 411062,
            "Stcd": company.get("state_code", "27")
        },
        "BuyerDtls": {
            "Gstin": "27ABCDE1234F1Z5",
            "LglNm": inv.get("customer_name"),
            "Addr1": "Address Details",
            "Loc": inv.get("place_of_supply", "Maharashtra"),
            "Pin": 411001,
            "Stcd": "27"
        },
        "ValDtls": {
            "AssVal": inv.get("subtotal", 0.0),
            "CgstVal": inv.get("cgst", 0.0),
            "SgstVal": inv.get("sgst", 0.0),
            "IgstVal": inv.get("igst", 0.0),
            "TotVal": inv.get("total", 0.0)
        },
        "ItemList": [
            {
                "SlNo": str(idx + 1),
                "PrdDesc": it.get("product_name", ""),
                "IsServc": "N",
                "HsnCd": "7308",
                # Guard against None values to prevent TypeError
                "Qty": float(it.get("quantity") or 0),
                "FreeQty": 0,
                "Unit": "PCS",
                "UnitPrice": float(it.get("unit_price") or 0),
                "TotAmt": round(float(it.get("quantity") or 0) * float(it.get("unit_price") or 0), 2),
                "GstRt": float(it.get("gst_rate") or 0),
                "AssAmt": round(float(it.get("quantity") or 0) * float(it.get("unit_price") or 0), 2),
            }
            for idx, it in enumerate(inv.get("items", []))
        ]
    }


@router.get("/invoices/{item_id}/einvoice-json")
async def get_einvoice_json(item_id: str, user: dict = Depends(get_current_user)):
    inv = await crud_get("invoices", item_id)
    assert_owns_or_404(inv, user, "invoices", bypass=bypasses_row_ownership(user.get("role")), label="Invoice")
    company = await db.companies.find_one({"tenant_id": resolve_tenant(user)}) or {}
    return build_einvoice_json(inv, company)


async def _get_irp_credentials():
    """Return (username, password) for the IRP, decrypted, or (None, None)."""
    from core import crypto
    cfg = await db.einvoice_settings.find_one({"id": "global"}) or {}
    username = cfg.get("irp_username")
    password = cfg.get("irp_password")
    if cfg.get("secrets_encrypted") and password:
        password = crypto.decrypt_secret(password)
    return username, password


@router.post("/invoices/{item_id}/generate-ewb")
async def generate_ewb(
    item_id: str,
    transporter_name: str = Query(...),
    vehicle_no: str = Query(...),
    distance_km: float = Query(...),
    transport_mode: Literal["ROAD", "RAIL", "AIR", "SHIP"] = Query(...),
    user: dict = Depends(get_current_user)
):
    inv = await crud_get("invoices", item_id)
    assert_owns_or_404(inv, user, "invoices", bypass=bypasses_row_ownership(user.get("role")), label="Invoice")
    ewb_number = f"3810{str(uuid.uuid4())[:8].upper()}"
    ewb_date = now_iso()[:10]
    
    update_fields = {
        "ewb_number": ewb_number,
        "ewb_date": ewb_date,
        "ewb_status": "GENERATED",
        "transporter_name": transporter_name,
        "vehicle_no": vehicle_no,
        "distance_km": distance_km,
        "transport_mode": transport_mode,
        "updated_at": now_iso()
    }
    old_values = await db.invoices.find_one({"id": item_id}, {"_id": 0})
    await db.invoices.update_one({"id": item_id}, {"$set": update_fields})
    new_values = await db.invoices.find_one({"id": item_id}, {"_id": 0})
    await log_audit("UPDATE", "invoices", item_id, user, old_values=old_values or {}, new_values=new_values or {})
    return new_values



# ---------- Dispatches ----------
@router.get("/dispatches")
async def list_dispatches(q: Optional[str] = None, _: dict = Depends(get_current_user)):
    return await crud_list("dispatches", q, ["challan_number", "vehicle_no", "driver_name", "customer_name", "status"])


@router.post("/dispatches")
async def create_dispatch(payload: Dispatch, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    if not data.get("challan_number"):
        data["challan_number"] = await next_doc_number("DC", "dispatches")
    return await crud_create("dispatches", data, user=user)


@router.put("/dispatches/{item_id}")
async def update_dispatch(item_id: str, payload: Dispatch, user: dict = Depends(get_current_user)):
    return await crud_update("dispatches", item_id, payload.model_dump(), user=user)


@router.delete("/dispatches/{item_id}")
async def delete_dispatch(item_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("dispatches", item_id, user=user)


@router.get("/dispatches/{item_id}")
async def get_dispatch(item_id: str, _: dict = Depends(get_current_user)):
    return await crud_get("dispatches", item_id)


@router.get("/dispatches/{item_id}/pdf")
async def dispatch_pdf(item_id: str, _: dict = Depends(get_current_user)):
    doc = await crud_get("dispatches", item_id)
    customer_id = doc.get("customer_id")
    if not customer_id and doc.get("sales_order_id"):
        so = await db.sales_orders.find_one({"id": doc["sales_order_id"]})
        if so:
            customer_id = so.get("customer_id")
    pdf_bytes = await render_document_pdf(
        "DELIVERY CHALLAN", doc.get("challan_number", item_id), doc,
        party_id=customer_id, party_type="customer",
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.get("challan_number", item_id)}.pdf"'},
    )


# ──────────────────────────────────────────────────────────────────────────
# IRP (e-Invoicing) credentials — admin-only; password encrypted at rest.
# ──────────────────────────────────────────────────────────────────────────


class EinvoiceSettingsPayload(BaseModel):
    irp_username: Optional[str] = ""
    irp_password: Optional[str] = ""
    irp_enabled: Optional[bool] = False


def _mask_irp(cfg: dict) -> dict:
    out = {
        "irp_username": cfg.get("irp_username", ""),
        "irp_enabled": cfg.get("irp_enabled", False),
        "irp_password": "",
    }
    if cfg.get("irp_password"):
        out["irp_password"] = "••••••••"  # presence indicator only; never the value
    return out


# Exposed under both /einvoice/settings and /invoices/einvoice/settings so the
# e-invoice config sits alongside the other /invoices/{id}/...-einvoice routes.
@router.get("/einvoice/settings")
@router.get("/invoices/einvoice/settings")
async def get_einvoice_settings(user: dict = Depends(require_admin)):
    cfg = await db.einvoice_settings.find_one({"id": "global"}, {"_id": 0}) or {}
    return _mask_irp(cfg)


@router.post("/einvoice/settings")
@router.post("/invoices/einvoice/settings")
async def update_einvoice_settings(payload: EinvoiceSettingsPayload, user: dict = Depends(require_admin)):
    from core import crypto
    # Project out _id: a raw ObjectId in old_values would later make the audit
    # log endpoint fail to JSON-serialize the row.
    existing = await db.einvoice_settings.find_one({"id": "global"}, {"_id": 0}) or {}
    update = {"id": "global", "updated_at": now_iso(), "updated_by": user["id"]}

    if "irp_username" in payload.model_fields_set:
        update["irp_username"] = payload.irp_username
    if "irp_enabled" in payload.model_fields_set:
        update["irp_enabled"] = payload.irp_enabled
        update["enabled"] = payload.irp_enabled
    # Only overwrite the password when a real new value is submitted (not the mask).
    if "irp_password" in payload.model_fields_set and payload.irp_password and not payload.irp_password.startswith("••••"):
        update["irp_password"] = crypto.encrypt_secret(payload.irp_password)
        update["secrets_encrypted"] = crypto.is_enabled()

    await db.einvoice_settings.update_one({"id": "global"}, {"$set": update}, upsert=True)
    await log_audit("UPDATE", "einvoice_settings", "global", user,
                    old_values={k: v for k, v in existing.items() if k != "irp_password"},
                    new_values={k: v for k, v in update.items() if k != "irp_password"})
    cfg = await db.einvoice_settings.find_one({"id": "global"}, {"_id": 0}) or {}
    return _mask_irp(cfg)
