"""Email send endpoints — sends a doc PDF as an attachment via Resend."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from core.auth_utils import get_current_user, require_admin
from core.db import db
from core.email import (
    is_configured,
    log_email,
    render_doc_email_html,
    send_email_sync,
)
from core.pdf import build_doc_pdf
from core.pi_pdf import build_pi_pdf
from core.utils import crud_get, now_iso

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
}


def _build_pdf(doc_type: str, doc: dict, doc_number: str) -> bytes:
    if doc_type == "proforma":
        return build_pi_pdf(doc)
    type_label = _DOC_TABLE[doc_type][2]
    return build_doc_pdf(type_label, doc_number, doc)


def _resolve_recipient_name(doc: dict, doc_type: str) -> str:
    if doc_type == "proforma":
        return doc.get("buyer_contact_person") or doc.get("buyer_name") or "Sir/Madam"
    return doc.get("customer_name") or "Sir/Madam"


@router.get("/status")
async def email_status(_: dict = Depends(get_current_user)):
    return {"configured": is_configured()}


@router.get("/logs")
async def email_logs(_: dict = Depends(get_current_user)):
    return await db.email_logs.find({}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)


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
            subject="GravityOne ERP · Test email",
            html=html,
        )
        message_id = (result or {}).get("id")
        await log_email(
            to=payload.to,
            subject="GravityOne ERP · Test email",
            doc_type="test",
            doc_id="-",
            doc_number="TEST-OK",
            sent_by=user,
            status="sent",
            message_id=message_id,
        )
        return {"ok": True, "message_id": message_id}
    except Exception as e:
        await log_email(
            to=payload.to,
            subject="GravityOne ERP · Test email",
            doc_type="test",
            doc_id="-",
            doc_number="TEST-OK",
            sent_by=user,
            status="failed",
            error=str(e),
        )
        raise HTTPException(status_code=502, detail=f"Email send failed: {e}")


@router.post("/{doc_type}/{doc_id}")
async def send_doc_email(doc_type: str, doc_id: str, payload: SendRequest, user: dict = Depends(get_current_user)):
    if doc_type not in _DOC_TABLE:
        raise HTTPException(status_code=400, detail="Unknown document type")
    if not is_configured():
        raise HTTPException(status_code=400, detail="Email service is not configured (RESEND_API_KEY missing)")
    collection, num_field, type_label, friendly = _DOC_TABLE[doc_type]
    doc = await db[collection].find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc_number = doc.get(num_field, doc_id)
    recipient_name = _resolve_recipient_name(doc, doc_type)
    subject = payload.subject or f"{friendly} {doc_number} — GravityOne ERP"
    html = render_doc_email_html(
        recipient_name=recipient_name,
        doc_label=friendly,
        doc_number=doc_number,
        intro=payload.message,
    )
    pdf_bytes = _build_pdf(doc_type, doc, doc_number)
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
        await log_email(
            to=payload.to,
            subject=subject,
            doc_type=doc_type,
            doc_id=doc_id,
            doc_number=doc_number,
            sent_by=user,
            status="sent",
            message_id=message_id,
        )
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
        await log_email(
            to=payload.to,
            subject=subject,
            doc_type=doc_type,
            doc_id=doc_id,
            doc_number=doc_number,
            sent_by=user,
            status="failed",
            error=str(e),
        )
        raise HTTPException(status_code=502, detail=f"Email send failed: {e}")
