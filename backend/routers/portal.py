"""Customer / Vendor Portal — Module H.

External-facing API under /portal/*, in a SEPARATE auth realm (core/portal_auth).
Every query is hard-scoped to the token's party_id at the data-access layer
(party_scoped) — client-supplied party ids are never trusted.

Customers: view invoices/statement, pay online (gateway link → receipt voucher).
Vendors:   submit bills (→ internal review queue → Purchase + approvals), track
           payment status (read-only mirror of internal payment voucher).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from typing import Optional, Literal
from pydantic import BaseModel
from datetime import date

from core.db import db
from core.utils import now_iso, new_id, next_doc_number
from core.auth_utils import require_admin
from core.rate_limit import client_ip, rate_limit
from core.portal_auth import (
    get_portal_user, require_customer, require_vendor,
    create_portal_token, hash_password, verify_password,
    party_scoped, assert_party_match,
)

router = APIRouter(prefix="/portal", tags=["Customer/Vendor Portal"])


# ══════════════════════════════════════════════════════════════
# Models
# ══════════════════════════════════════════════════════════════

class PortalLogin(BaseModel):
    email: str
    password: str


class PortalUserCreate(BaseModel):
    party_id: str
    party_type: Literal["customer", "vendor"]
    email: str
    password: str
    name: Optional[str] = None


class PayRequest(BaseModel):
    gateway: Literal["razorpay", "stripe", "payu", "mock"] = "mock"


class PaymentCallback(BaseModel):
    txn_ref: str
    success: bool = True


class BillSubmission(BaseModel):
    amount: float
    bill_number: Optional[str] = None
    bill_date: Optional[str] = None
    file_ref: Optional[str] = None        # uploaded file pointer
    description: Optional[str] = None


# ══════════════════════════════════════════════════════════════
# Portal auth (separate realm)
# ══════════════════════════════════════════════════════════════

@router.post("/auth/login")
async def portal_login(payload: PortalLogin, request: Request, response: Response):
    email = payload.email.lower().strip()
    # Brute-force / credential-stuffing protection, per-IP and per-account.
    ip = client_ip(request)
    rate_limit(f"portal-login:ip:{ip}", limit=10, window_seconds=300, request=request)
    rate_limit(f"portal-login:acct:{email}", limit=5, window_seconds=300, request=request)
    pu = await db.portal_users.find_one({"email": email})
    if not pu or not verify_password(payload.password, pu.get("password_hash", "")):
        raise HTTPException(401, "Invalid email or password")
    if pu.get("status") not in (None, "active"):
        raise HTTPException(403, f"Portal account is {pu.get('status')}")
    token = create_portal_token(pu["id"], pu["party_id"], pu["party_type"], pu["email"])
    # portal cookie is namespaced separately from internal access_token
    response.set_cookie("portal_token", token, httponly=True, samesite="lax", path="/", max_age=60 * 60 * 12)
    return {
        "token": token,
        "party_type": pu["party_type"],
        "party_id": pu["party_id"],
        "name": pu.get("name"),
        "email": pu["email"],
    }


@router.post("/auth/logout")
async def portal_logout(response: Response, _: dict = Depends(get_portal_user)):
    response.delete_cookie("portal_token", path="/")
    return {"ok": True}


@router.get("/auth/me")
async def portal_me(portal_user: dict = Depends(get_portal_user)):
    return {
        "party_id": portal_user["party_id"],
        "party_type": portal_user["party_type"],
        "email": portal_user["email"],
        "name": portal_user.get("name"),
    }


# Provisioning is an INTERNAL-admin action; gated by the internal admin realm.
@router.post("/admin/users")
async def provision_portal_user(payload: PortalUserCreate, _admin: dict = Depends(require_admin)):
    """
    Create a portal login for a party. This is an internal-admin action: it
    requires a logged-in internal admin (require_admin), NOT a portal token —
    otherwise anyone could self-provision a portal login for any party_id and
    read that party's invoices/statements.
    """
    email = payload.email.lower().strip()
    if await db.portal_users.find_one({"email": email}):
        raise HTTPException(400, "Portal user with this email already exists")
    doc = {
        "id": new_id(),
        "party_id": payload.party_id,
        "party_type": payload.party_type,
        "email": email,
        "name": payload.name,
        "password_hash": hash_password(payload.password),
        "status": "active",
        "created_at": now_iso(),
    }
    await db.portal_users.insert_one(doc)
    doc.pop("_id", None)
    doc.pop("password_hash", None)
    return doc


# ══════════════════════════════════════════════════════════════
# Customer: invoices & statement
# ══════════════════════════════════════════════════════════════

@router.get("/invoices")
async def portal_invoices(
    status: Optional[str] = None,
    portal_user: dict = Depends(require_customer),
):
    """List the calling customer's invoices — hard-scoped to token party_id."""
    q = party_scoped({}, portal_user, party_field="customer_id")
    if status:
        q["status"] = status
    invoices = await db.invoices.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for inv in invoices:
        inv["outstanding"] = round(inv.get("total", 0) - inv.get("payment_received", 0), 2)
    return invoices


@router.get("/invoices/{invoice_id}")
async def portal_invoice_detail(invoice_id: str, portal_user: dict = Depends(require_customer)):
    # fetch by id then assert ownership (defense in depth — never trust the id)
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Not found")
    assert_party_match(inv.get("customer_id"), portal_user)
    inv["outstanding"] = round(inv.get("total", 0) - inv.get("payment_received", 0), 2)
    return inv


@router.get("/statement")
async def portal_statement(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    portal_user: dict = Depends(require_customer),
):
    """Running statement of the customer's invoices and receipts."""
    q = party_scoped({}, portal_user, party_field="customer_id")
    if from_date or to_date:
        q["created_at"] = {}
        if from_date:
            q["created_at"]["$gte"] = from_date
        if to_date:
            q["created_at"]["$lte"] = to_date + "T23:59:59"
    invoices = await db.invoices.find(q, {"_id": 0}).sort("created_at", 1).to_list(2000)

    lines = []
    running = 0.0
    for inv in invoices:
        total = inv.get("total", 0)
        paid = inv.get("payment_received", 0)
        running += total - paid
        lines.append({
            "date": inv.get("created_at", "")[:10],
            "invoice_no": inv.get("invoice_number"),
            "invoice_id": inv.get("id"),
            "debit": total,
            "credit": paid,
            "running_balance": round(running, 2),
            "status": inv.get("status"),
        })
    return {
        "party_id": portal_user["party_id"],
        "opening_balance": 0.0,
        "lines": lines,
        "closing_balance": round(running, 2),
    }


# ══════════════════════════════════════════════════════════════
# Customer: pay online
# ══════════════════════════════════════════════════════════════

@router.post("/invoices/{invoice_id}/pay")
async def portal_pay(invoice_id: str, payload: PayRequest, portal_user: dict = Depends(require_customer)):
    """
    Create a payment link for the invoice's outstanding amount.
    Real gateways return a redirect URL; the success webhook hits /pay/callback.
    """
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Not found")
    assert_party_match(inv.get("customer_id"), portal_user)

    outstanding = round(inv.get("total", 0) - inv.get("payment_received", 0), 2)
    if outstanding <= 0:
        raise HTTPException(400, "Invoice already paid")

    link = {
        "id": new_id(),
        "invoice_id": invoice_id,
        "party_id": portal_user["party_id"],
        "gateway": payload.gateway,
        "amount": outstanding,
        "status": "created",
        "txn_ref": None,
        "created_at": now_iso(),
    }
    await db.payment_links.insert_one(link)
    link.pop("_id", None)
    # Mock gateway returns a synthetic pay URL; real gateway integration swaps this.
    return {
        "payment_link_id": link["id"],
        "amount": outstanding,
        "gateway": payload.gateway,
        "pay_url": f"/portal/pay/{link['id']}/mock-checkout",
        "status": "created",
    }


@router.post("/pay/{payment_link_id}/callback")
async def portal_pay_callback(payment_link_id: str, payload: PaymentCallback):
    """
    Gateway success/failure webhook. On success, posts a receipt voucher
    (transaction) and marks the invoice paid. Idempotent on txn_ref.
    """
    link = await db.payment_links.find_one({"id": payment_link_id}, {"_id": 0})
    if not link:
        raise HTTPException(404, "Payment link not found")
    if link["status"] == "paid":
        return {"status": "already_paid", "payment_link_id": payment_link_id}

    if not payload.success:
        await db.payment_links.update_one(
            {"id": payment_link_id},
            {"$set": {"status": "failed", "txn_ref": payload.txn_ref, "updated_at": now_iso()}},
        )
        return {"status": "failed"}

    inv = await db.invoices.find_one({"id": link["invoice_id"]}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice not found")

    # Use a transaction so receipt voucher + invoice update + link update commit atomically.
    client = db.client
    async def _post(session=None):
        voucher_no = await next_doc_number("RCPT", "vouchers")
        receipt = {
            "id": new_id(),
            "voucher_number": voucher_no,
            "voucher_type": "RECEIPT",
            "date": date.today().isoformat(),
            "party_type": "CUSTOMER",
            "party_id": link["party_id"],
            "party_name": inv.get("customer_name"),
            "amount": link["amount"],
            "payment_mode": "OTHER",
            "reference_doc": inv.get("invoice_number"),
            "narration": f"Online receipt via {link['gateway']} (txn {payload.txn_ref}) for invoice {inv.get('invoice_number')}",
            "status": "APPROVED",
            "source": "portal_payment",
            "payment_link_id": payment_link_id,
            "created_at": now_iso(),
        }
        await db.vouchers.insert_one(receipt, session=session)

        new_paid = round(inv.get("payment_received", 0) + link["amount"], 2)
        new_status = "PAID" if new_paid >= round(inv.get("total", 0), 2) else "PARTIAL"
        await db.invoices.update_one(
            {"id": inv["id"]},
            {"$set": {"payment_received": new_paid, "status": new_status, "updated_at": now_iso()}},
            session=session,
        )
        await db.payment_links.update_one(
            {"id": payment_link_id},
            {"$set": {"status": "paid", "txn_ref": payload.txn_ref,
                      "receipt_voucher_id": receipt["id"], "paid_at": now_iso()}},
            session=session,
        )
        return receipt["id"], new_status

    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                receipt_id, new_status = await _post(session)
    except Exception:
        # Standalone Mongo (no replica set) can't do multi-doc txns — fall back
        # to sequential writes. Still posts receipt + marks invoice.
        receipt_id, new_status = await _post(None)

    return {
        "status": "paid",
        "receipt_voucher_id": receipt_id,
        "invoice_status": new_status,
        "amount": link["amount"],
    }


# ══════════════════════════════════════════════════════════════
# Vendor: bill submission → internal review queue
# ══════════════════════════════════════════════════════════════

@router.post("/bills")
async def portal_submit_bill(payload: BillSubmission, portal_user: dict = Depends(require_vendor)):
    """Vendor submits a bill. Lands in the internal review queue as 'submitted'."""
    doc = {
        "id": new_id(),
        "submission_no": await next_doc_number("VBILL", "vendor_bill_submissions"),
        "vendor_id": portal_user["party_id"],   # from token, never client input
        "amount": payload.amount,
        "bill_number": payload.bill_number,
        "bill_date": payload.bill_date,
        "file_ref": payload.file_ref,
        "description": payload.description,
        "status": "submitted",
        "linked_purchase_invoice_id": None,
        "submitted_at": now_iso(),
    }
    await db.vendor_bill_submissions.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/bills")
async def portal_list_bills(portal_user: dict = Depends(require_vendor)):
    q = party_scoped({}, portal_user, party_field="vendor_id")
    return await db.vendor_bill_submissions.find(q, {"_id": 0}).sort("submitted_at", -1).to_list(1000)


@router.get("/bills/{bill_id}/status")
async def portal_bill_status(bill_id: str, portal_user: dict = Depends(require_vendor)):
    """Read-only status mirror, including linked payment voucher status if paid."""
    bill = await db.vendor_bill_submissions.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(404, "Not found")
    assert_party_match(bill.get("vendor_id"), portal_user)

    payment_status = None
    if bill.get("status") == "paid" and bill.get("payment_voucher_id"):
        pv = await db.vouchers.find_one({"id": bill["payment_voucher_id"]}, {"_id": 0, "status": 1, "amount": 1, "date": 1})
        if pv:
            payment_status = {"voucher_status": pv.get("status"), "amount": pv.get("amount"), "date": pv.get("date")}

    return {
        "bill_id": bill_id,
        "submission_no": bill.get("submission_no"),
        "status": bill.get("status"),
        "amount": bill.get("amount"),
        "linked_purchase_invoice_id": bill.get("linked_purchase_invoice_id"),
        "payment": payment_status,
    }


# ══════════════════════════════════════════════════════════════
# Internal: vendor-bill review queue (internal realm)
# ══════════════════════════════════════════════════════════════
# These endpoints are consumed by internal staff. They live here for cohesion
# but use the INTERNAL auth dependency.

from core.auth_utils import get_current_user as _internal_user


@router.get("/internal/bill-queue")
async def internal_bill_queue(status: Optional[str] = None, user: dict = Depends(_internal_user)):
    q = {}
    if status:
        q["status"] = status
    return await db.vendor_bill_submissions.find(q, {"_id": 0}).sort("submitted_at", 1).to_list(2000)


@router.post("/internal/bills/{bill_id}/promote")
async def internal_promote_bill(bill_id: str, user: dict = Depends(_internal_user)):
    """
    Move a submitted vendor bill into Purchase as a purchase invoice and route it
    through the approval chain (Module E). Sets bill status → under_review.
    """
    bill = await db.vendor_bill_submissions.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(404, "Bill not found")
    if bill["status"] not in ("submitted",):
        raise HTTPException(400, f"Bill is '{bill['status']}', expected submitted")

    # Create a purchase invoice shell in draft (approval-state = draft so it can submit)
    pi = {
        "id": new_id(),
        "invoice_number": await next_doc_number("PINV", "invoices"),
        "invoice_type": "PURCHASE_INVOICE",
        "supplier_id": bill["vendor_id"],
        "total": bill["amount"],
        "status": "UNPAID",
        "approval_state": "draft",
        "source_bill_submission_id": bill_id,
        "created_at": now_iso(),
    }
    await db.invoices.insert_one(pi)

    await db.vendor_bill_submissions.update_one(
        {"id": bill_id},
        {"$set": {"status": "under_review", "linked_purchase_invoice_id": pi["id"], "updated_at": now_iso()}},
    )
    return {
        "bill_id": bill_id,
        "purchase_invoice_id": pi["id"],
        "status": "under_review",
        "next": "submit the purchase invoice via POST /approvals/voucher/{id}/submit or the purchase flow",
    }
