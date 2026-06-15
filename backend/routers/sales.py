from typing import Optional, Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.models import (
    Customer,
    Dispatch,
    Invoice,
    Lead,
    Quotation,
    SalesOrder,
)
from core.pdf import build_doc_pdf
from core.utils import (
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
)

router = APIRouter(tags=["sales"])


import re

async def check_gstin_before_save(gstin: Optional[str], data: dict):
    if not gstin:
        return
    gstin = gstin.strip().upper()
    pattern = re.compile(r"^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    if not pattern.match(gstin):
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
async def list_customers(q: Optional[str] = None, _: dict = Depends(get_current_user)):
    return await crud_list("customers", q, ["name", "company", "email", "phone", "country"], sort_field="name")


@router.post("/customers")
async def create_customer(payload: Customer, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    await check_gstin_before_save(data.get("gstin"), data)
    if not data.get("customer_code"):
        data["customer_code"] = await next_doc_number("CUST", "customers")
    return await crud_create("customers", data, user=user)


@router.put("/customers/{item_id}")
async def update_customer(item_id: str, payload: Customer, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    await check_gstin_before_save(data.get("gstin"), data)
    return await crud_update("customers", item_id, data, user=user)


@router.delete("/customers/{item_id}")
async def delete_customer(item_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("customers", item_id, user=user)


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
async def list_quotations(q: Optional[str] = None, _: dict = Depends(get_current_user)):
    return await crud_list("quotations", q, ["quote_number", "customer_name", "status"])


@router.post("/quotations")
async def create_quotation(payload: Quotation, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    if not data.get("quote_number"):
        data["quote_number"] = await next_doc_number("QUO", "quotations")
    if data.get("customer_id") and not data.get("customer_name"):
        cust = await db.customers.find_one({"id": data["customer_id"]}, {"_id": 0, "name": 1})
        if cust:
            data["customer_name"] = cust["name"]
    data.update(calc_totals(data["items"]))
    return await crud_create("quotations", data, user=user)


@router.put("/quotations/{item_id}")
async def update_quotation(item_id: str, payload: Quotation, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    data.update(calc_totals(data["items"]))
    return await crud_update("quotations", item_id, data, user=user)


@router.delete("/quotations/{item_id}")
async def delete_quotation(item_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("quotations", item_id, user=user)


@router.get("/quotations/{item_id}")
async def get_quotation(item_id: str, _: dict = Depends(get_current_user)):
    return await crud_get("quotations", item_id)


@router.get("/quotations/{item_id}/pdf")
async def quotation_pdf(item_id: str, _: dict = Depends(get_current_user)):
    doc = await crud_get("quotations", item_id)
    pdf_bytes = build_doc_pdf("QUOTATION", doc.get("quote_number", item_id), doc)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.get("quote_number", item_id)}.pdf"'},
    )


# ---------- Sales Orders ----------
@router.get("/sales-orders")
async def list_sos(q: Optional[str] = None, _: dict = Depends(get_current_user)):
    return await crud_list("sales_orders", q, ["order_number", "customer_name", "status"])


@router.post("/sales-orders")
async def create_so(payload: SalesOrder, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    if not data.get("order_number"):
        data["order_number"] = await next_doc_number("SO", "sales_orders")
    if data.get("customer_id") and not data.get("customer_name"):
        cust = await db.customers.find_one({"id": data["customer_id"]}, {"_id": 0, "name": 1})
        if cust:
            data["customer_name"] = cust["name"]
    data.update(calc_totals(data["items"]))
    return await crud_create("sales_orders", data, user=user)


@router.put("/sales-orders/{item_id}")
async def update_so(item_id: str, payload: SalesOrder, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    data.update(calc_totals(data["items"]))
    return await crud_update("sales_orders", item_id, data, user=user)


@router.post("/sales-orders/{item_id}/confirm")
async def confirm_so(item_id: str, user: dict = Depends(get_current_user)):
    so = await crud_get("sales_orders", item_id)
    if so.get("status") not in ["PENDING"]:
        raise HTTPException(status_code=400, detail="Order is not pending")
    for item in so.get("items", []):
        prod = await db.products.find_one({"id": item["product_id"]}, {"_id": 0})
        if not prod:
            continue
        new_qty = float(prod.get("quantity", 0)) - float(item["quantity"])
        if new_qty < 0:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {item['product_name']}")
        await db.products.update_one(
            {"id": item["product_id"]},
            {"$set": {"quantity": new_qty, "updated_at": now_iso()}},
        )
        await db.stock_transactions.insert_one({
            "id": new_id(),
            "product_id": item["product_id"],
            "product_name": item["product_name"],
            "delta": -float(item["quantity"]),
            "balance": new_qty,
            "reason": f"Sales {so.get('order_number')}",
            "user_id": user["id"],
            "user_name": user.get("name", "Unknown"),
            "created_at": now_iso(),
        })
    await db.sales_orders.update_one({"id": item_id}, {"$set": {"status": "CONFIRMED", "updated_at": now_iso()}})
    return {"ok": True}


@router.delete("/sales-orders/{item_id}")
async def delete_so(item_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("sales_orders", item_id, user=user)


@router.get("/sales-orders/{item_id}")
async def get_so(item_id: str, _: dict = Depends(get_current_user)):
    return await crud_get("sales_orders", item_id)


@router.get("/sales-orders/{item_id}/pdf")
async def so_pdf(item_id: str, _: dict = Depends(get_current_user)):
    doc = await crud_get("sales_orders", item_id)
    pdf_bytes = build_doc_pdf("SALES ORDER", doc.get("order_number", item_id), doc)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.get("order_number", item_id)}.pdf"'},
    )


# ---------- Invoices ----------
async def calculate_gst_for_invoice(data: dict):
    # Fetch active company state code
    company = await db.companies.find_one({})
    company_state_code = company.get("state_code", "27") if company else "27"

    # Fetch customer to determine inter/intra-state GST
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
async def list_invoices(q: Optional[str] = None, _: dict = Depends(get_current_user)):
    return await crud_list("invoices", q, ["invoice_number", "customer_name", "status"])


@router.post("/invoices")
async def create_invoice(payload: Invoice, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    if not data.get("invoice_number"):
        data["invoice_number"] = await next_doc_number("INV", "invoices")
    if data.get("customer_id") and not data.get("customer_name"):
        cust = await db.customers.find_one({"id": data["customer_id"]}, {"_id": 0, "name": 1})
        if cust:
            data["customer_name"] = cust["name"]
    await calculate_gst_for_invoice(data)
    return await crud_create("invoices", data, user=user)


@router.put("/invoices/{item_id}")
async def update_invoice(item_id: str, payload: Invoice, user: dict = Depends(get_current_user)):
    data = payload.model_dump()
    await calculate_gst_for_invoice(data)
    return await crud_update("invoices", item_id, data, user=user)


@router.post("/invoices/{item_id}/payment")
async def record_payment(item_id: str, amount: float = Query(...), user: dict = Depends(get_current_user)):
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be positive")
    inv = await crud_get("invoices", item_id)
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
async def get_invoice(item_id: str, _: dict = Depends(get_current_user)):
    return await crud_get("invoices", item_id)


@router.get("/invoices/{item_id}/pdf")
async def invoice_pdf(item_id: str, _: dict = Depends(get_current_user)):
    doc = await crud_get("invoices", item_id)
    company = await db.companies.find_one({})
    doc["company"] = company
    pdf_bytes = build_doc_pdf("TAX INVOICE", doc.get("invoice_number", item_id), doc)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.get("invoice_number", item_id)}.pdf"'},
    )


# ---------- E-Invoice & E-Way Bill Actions ----------
@router.post("/invoices/{item_id}/generate-einvoice")
async def generate_einvoice(item_id: str, user: dict = Depends(get_current_user)):
    import hashlib
    inv = await crud_get("invoices", item_id)
    if inv.get("einvoice_status") == "GENERATED":
        return inv

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


@router.get("/invoices/{item_id}/einvoice-json")
async def get_einvoice_json(item_id: str, _: dict = Depends(get_current_user)):
    inv = await crud_get("invoices", item_id)
    company = await db.companies.find_one({}) or {}
    
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


@router.post("/invoices/{item_id}/generate-ewb")
async def generate_ewb(
    item_id: str,
    transporter_name: str = Query(...),
    vehicle_no: str = Query(...),
    distance_km: float = Query(...),
    transport_mode: Literal["ROAD", "RAIL", "AIR", "SHIP"] = Query(...),
    user: dict = Depends(get_current_user)
):
    await crud_get("invoices", item_id)
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
    pdf_bytes = build_doc_pdf("DISPATCH CHALLAN", doc.get("challan_number", item_id), doc)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.get("challan_number", item_id)}.pdf"'},
    )
