"""Email send endpoints — sends a doc PDF as an attachment via Resend."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.email import (
    is_configured,
    render_doc_email_html,
    send_email_sync,
)
from core.pdf import build_jobwork_receipt_pdf
from core.pi_pdf import build_pi_pdf
from core.utils import get_active_company, now_iso, render_document_pdf

router = APIRouter(prefix="/email", tags=["email"])


class SendRequest(BaseModel):
    to: EmailStr
    subject: Optional[str] = None
    message: Optional[str] = None


class TestSendRequest(BaseModel):
    to: EmailStr


# --- doc dispatch table ---
_DOC_TABLE = {
    "quotation": ("quotations", "quote_number", "QUOTATION", "Quotation"),
    "sales_order": ("sales_orders", "order_number", "SALES ORDER", "Sales Order"),
    "invoice": ("invoices", "invoice_number", "TAX INVOICE", "GST Invoice"),
    "dispatch": ("dispatches", "challan_number", "DISPATCH CHALLAN", "Dispatch Challan"),
    "proforma": ("proforma_invoices", "pi_number", "PROFORMA INVOICE", "Proforma Invoice"),
    "job_work_challan": ("job_work_challans", "challan_number", "JOB WORK CHALLAN", "Job Work Challan"),
    "job_work_receipt": ("job_work_receipts", "receipt_number", "MATERIAL INWARD RECEIPT", "Job Work Receipt"),
}


async def _load_doc_for_email(doc_type: str, doc_id: str) -> dict | None:
    """Job Work docs store their line items in a child table, not inline on
    the header row — fetch and attach them the same way the job_work router
    does, so _build_pdf gets a complete doc regardless of doc_type."""
    collection = _DOC_TABLE[doc_type][0]
    doc = await db[collection].find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        return None
    if doc_type == "job_work_challan":
        from routers.job_work import _fetch_challan_items, _received_by_challan_item
        items = await _fetch_challan_items(doc_id)
        received_by_item = await _received_by_challan_item([doc_id])
        for item in items:
            sent = float(item.get("quantity", 0) or 0)
            item["quantity_received"] = received_by_item.get(item["id"], 0.0)
            item["quantity_pending"] = max(0.0, sent - item["quantity_received"])
            item["unit"] = item.get("uom") or item.get("unit") or "Nos"
        doc["items"] = items
    elif doc_type == "job_work_receipt":
        from sqlalchemy import select
        from core.db import get_session
        from core.schema import JobWorkReceiptItem
        async with get_session() as session:
            result = await session.execute(select(JobWorkReceiptItem).where(JobWorkReceiptItem.receipt_id == doc_id))
            doc["items"] = [{c.key: getattr(row, c.key) for c in row.__table__.columns} for row in result.scalars().all()]
    return doc


async def _resolve_customer_id(doc_type: str, doc: dict) -> str | None:
    """Dispatches don't always carry customer_id directly — fall back to the
    linked sales order, same as the standalone /dispatches/{id}/pdf route."""
    customer_id = doc.get("customer_id")
    if not customer_id and doc_type == "dispatch" and doc.get("sales_order_id"):
        so = await db.sales_orders.find_one({"id": doc["sales_order_id"]})
        if so:
            customer_id = so.get("customer_id")
    return customer_id


async def _build_pdf(doc_type: str, doc: dict, doc_number: str, company: dict | None = None) -> bytes:
    if doc_type == "proforma":
        return build_pi_pdf(doc, company=company)
    if doc_type == "job_work_receipt":
        return build_jobwork_receipt_pdf(doc, company=company)
    # Quotation / Sales Order / Invoice / Dispatch / Job Work Challan — the
    # same premium layout every download/view PDF endpoint uses, so the
    # emailed attachment looks identical to what's seen in-app (and gets a
    # live-resolved party box instead of whatever was baked into the doc at
    # send time).
    type_label = _DOC_TABLE[doc_type][2]
    if doc_type == "job_work_challan":
        return await render_document_pdf(type_label, doc_number, doc, party_id=doc.get("job_worker_id"),
                                         party_type="vendor", company=company)
    customer_id = await _resolve_customer_id(doc_type, doc)
    return await render_document_pdf(type_label, doc_number, doc, party_id=customer_id,
                                     party_type="customer", company=company)


def _resolve_recipient_name(doc: dict, doc_type: str) -> str:
    if doc_type == "proforma":
        return doc.get("buyer_contact_person") or doc.get("buyer_name") or "Sir/Madam"
    if doc_type in ("job_work_challan", "job_work_receipt"):
        return doc.get("job_worker_name") or doc.get("contact_person") or "Sir/Madam"
    return doc.get("customer_name") or "Sir/Madam"


@router.get("/status")
async def email_status(_: dict = Depends(get_current_user)):
    return {"configured": is_configured()}





@router.post("/test")
async def email_test(payload: TestSendRequest, user: dict = Depends(require_admin)):
    if not is_configured():
        raise HTTPException(status_code=400, detail="Email service is not configured (RESEND_API_KEY missing)")
    html = render_doc_email_html(
        recipient_name=user.get("name", "Operator"),
        doc_label="System Test",
        doc_number="TEST-OK",
        intro="If you can read this, the Resend integration is wired up correctly.",
    )
    try:
        result = send_email_sync(
            to=payload.to,
            subject="Ormodex ERP · Test email",
            html=html,
        )
        message_id = (result or {}).get("id")
        return {"ok": True, "message_id": message_id}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Email send failed: {e}")


@router.post("/{doc_type}/{doc_id}")
async def send_doc_email(doc_type: str, doc_id: str, payload: SendRequest, user: dict = Depends(get_current_user)):
    if doc_type not in _DOC_TABLE:
        raise HTTPException(status_code=400, detail="Unknown document type")
    if not is_configured():
        raise HTTPException(status_code=400, detail="Email service is not configured (RESEND_API_KEY missing)")
    collection, num_field, _type_label, friendly = _DOC_TABLE[doc_type]
    doc = await _load_doc_for_email(doc_type, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc_number = doc.get(num_field, doc_id)
    recipient_name = _resolve_recipient_name(doc, doc_type)
    subject = payload.subject or f"{friendly} {doc_number} — Ormodex ERP"
    html = render_doc_email_html(
        recipient_name=recipient_name,
        doc_label=friendly,
        doc_number=doc_number,
        intro=payload.message,
    )
    pdf_bytes = await _build_pdf(doc_type, doc, doc_number, company=await get_active_company())
    filename = f"{doc_number}.pdf"

    try:
        result = send_email_sync(
            to=payload.to,
            subject=subject,
            html=html,
            attachment_bytes=pdf_bytes,
            attachment_filename=filename,
        )
        message_id = (result or {}).get("id")
        await db[collection].update_one(
            {"id": doc_id},
            {"$set": {
                "last_sent_at": now_iso(),
                "last_sent_to": payload.to,
                "updated_at": now_iso(),
            }},
        )
        return {"ok": True, "message_id": message_id, "sent_to": payload.to}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Email send failed: {e}")
