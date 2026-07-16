"""Universal Cheque Printing — works with any Indian bank, no external API.

Three masters drive the module:
  - bank_accounts          : extended with cheque-specific fields (holder, cheque_type, template).
  - cheque_templates       : per-bank print layout — physical mm dimensions plus
                             per-field coordinates/font/spacing/alignment, authored
                             against a real cheque leaf, lifecycle-managed
                             (draft → active → archived, plus duplicate).
  - cheque_transactions    : each printed/cancelled/void cheque, immutable once printed.
  - cheque_issue_register  : one row per consumed cheque leaf (the official register).

Auto-fill from payment vouchers:
  Sources: payment_voucher, supplier_payment, customer_refund, expense_payment, bank_payment
  Fields: payee_name, amount, cheque_date, bank_account, voucher_number, narration, company_name

RBAC: cheque_template_manage (templates, admin), cheque_print, cheque_cancel.
All create/update/print/reprint/cancel/void actions land in audit_logs.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, Query
from typing import Optional, Literal, List
from pydantic import BaseModel, Field

from core.auth_utils import get_current_user, is_admin_role
from core.db import db
from core.storage import put_object, get_object
from core.utils import now_iso, new_id, crud_create, crud_list, crud_get, crud_update, log_audit
from core.cheque_print_pdf import build_cheque_pdf, FIELD_KEYS
from routers.banking_pdc import amount_in_words

router = APIRouter(prefix="/cheque-printing", tags=["Cheque Printing"])


# ══════════════════════════════════════════════════════════════
# RBAC guards
# ══════════════════════════════════════════════════════════════

def _require(user: dict, permission: str):
    if is_admin_role(user.get("role")):
        return user
    if permission in user.get("module_permissions", []):
        return user
    raise HTTPException(403, f"'{permission}' permission required")


def _require_template_admin(user: dict):
    if is_admin_role(user.get("role")):
        return user
    if "cheque_template_manage" in user.get("module_permissions", []):
        return user
    raise HTTPException(403, "Cheque template management is restricted to administrators")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ══════════════════════════════════════════════════════════════
# Pydantic Models
# ══════════════════════════════════════════════════════════════

class FieldPosition(BaseModel):
    field: str
    x_mm: float = 0.0
    y_mm: float = 0.0
    font_family: str = "Helvetica"
    font_size: float = 11.0
    char_spacing: float = 0.0
    align: Literal["left", "center", "right"] = "left"
    enabled: bool = True


class BankAccountIn(BaseModel):
    bank_name: str
    branch_name: Optional[str] = None
    account_holder_name: str
    account_number: str
    ifsc_code: str
    cheque_type: Literal["single", "top-stub", "side-stub"] = "single"
    template_id: Optional[str] = None
    opening_balance: float = 0.0


class ChequeTemplateIn(BaseModel):
    template_name: str
    bank_name: str
    cheque_width_mm: float = 203.0
    cheque_height_mm: float = 93.0
    field_positions: list[FieldPosition] = Field(default_factory=list)
    background_image: Optional[str] = None
    is_active: bool = False


class ChequeRequestBase(BaseModel):
    bank_account_id: str
    payee_name: str
    amount: float
    cheque_date: str
    account_payee: bool = True
    narration: Optional[str] = None
    company_name: Optional[str] = None
    # Voucher linkage (optional — caller may link a source voucher)
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    voucher_number: Optional[str] = None


class ChequePreviewRequest(ChequeRequestBase):
    cheque_number: Optional[str] = None


class ChequePrintRequest(ChequeRequestBase):
    cheque_number: str
    printer: Optional[str] = None
    test_print: bool = False


class BulkPrintItem(BaseModel):
    bank_account_id: str
    payee_name: str
    amount: float
    cheque_date: str
    cheque_number: str
    account_payee: bool = True
    narration: Optional[str] = None
    company_name: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    voucher_number: Optional[str] = None


class BulkPrintRequest(BaseModel):
    items: List[BulkPrintItem]
    printer: Optional[str] = None


class ChequeCancelRequest(BaseModel):
    reason: str


class ChequeVoidRequest(BaseModel):
    reason: str


class ChequeStatusUpdateRequest(BaseModel):
    status: Literal["cleared", "bounced"]
    cleared_date: Optional[str] = None
    bounced_date: Optional[str] = None
    bounced_reason: Optional[str] = None


# ══════════════════════════════════════════════════════════════
# Shared rendering helpers
# ══════════════════════════════════════════════════════════════

_ACCOUNT_PAYEE_TEXT = "A/C PAYEE ONLY"


async def _resolve_template(account: dict) -> dict:
    template_id = account.get("template_id")
    if not template_id:
        raise HTTPException(400, "Bank account has no linked cheque template")
    tpl = await db.cheque_templates.find_one({"id": template_id}, {"_id": 0})
    if not tpl:
        raise HTTPException(404, "Linked cheque template not found")
    if tpl.get("archived"):
        raise HTTPException(400, "Linked cheque template is archived")
    return tpl


def _resolve_fields(template: dict, values: dict) -> list[dict]:
    resolved = []
    for fld in template.get("field_positions", []):
        key = fld.get("field", "")
        if not fld.get("enabled", True):
            continue
        value = values.get(key, "")
        if value in (None, ""):
            continue
        resolved.append({**fld, "value": value})
    return resolved


async def _build_render(req: ChequeRequestBase) -> dict:
    account = await crud_get("bank_accounts", req.bank_account_id)
    template = await _resolve_template(account)
    words = amount_in_words(req.amount)
    values = {
        "date": (req.cheque_date or "").replace("-", ""),
        "payee_name": req.payee_name,
        "amount_words": words,
        "amount_figures": f"**{req.amount:,.2f}/-",
        "account_payee": _ACCOUNT_PAYEE_TEXT if req.account_payee else "",
        "signature_marker": "",
    }
    fields = _resolve_fields(template, values)
    return {
        "account": account,
        "template": template,
        "amount_words": words,
        "fields": fields,
        "values": values,
    }


# ══════════════════════════════════════════════════════════════
# Voucher data auto-fetch
# ══════════════════════════════════════════════════════════════

SOURCE_COLLECTIONS = {
    "payment_voucher":    "vouchers",
    "supplier_payment":   "vouchers",
    "customer_refund":    "vouchers",
    "expense_payment":    "expense_entries",
    "bank_payment":       "bank_entries",
}

# Fields per source type to extract (payee, amount, date, voucher_no, narration)
async def _fetch_voucher(source_type: str, source_id: str) -> dict:
    """Return a dict with keys payee_name, amount, cheque_date, voucher_number, narration."""
    if source_type in ("payment_voucher", "supplier_payment", "customer_refund", "bank_payment"):
        col = "vouchers"
        doc = await db[col].find_one({"id": source_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, f"Voucher {source_id} not found")
        return {
            "payee_name": doc.get("party_name") or doc.get("payee_name") or "",
            "amount": float(doc.get("amount") or 0),
            "cheque_date": (doc.get("voucher_date") or doc.get("date") or "")[:10],
            "voucher_number": doc.get("voucher_no") or doc.get("voucher_number") or "",
            "narration": doc.get("narration") or "",
            "bank_account_id": doc.get("bank_account_id") or "",
        }
    elif source_type == "expense_payment":
        doc = await db.expense_entries.find_one({"id": source_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, f"Expense entry {source_id} not found")
        return {
            "payee_name": doc.get("payee_name") or doc.get("vendor_name") or "Expense Payee",
            "amount": float(doc.get("total_amount") or doc.get("amount") or 0),
            "cheque_date": (doc.get("expense_date") or "")[:10],
            "voucher_number": doc.get("expense_no") or "",
            "narration": doc.get("notes") or "",
            "bank_account_id": doc.get("bank_account_id") or "",
        }
    raise HTTPException(400, f"Unknown source_type: {source_type}")


@router.get("/vouchers/payment")
async def list_payment_vouchers(
    source_type: str = Query("payment_voucher", description="payment_voucher|supplier_payment|customer_refund|expense_payment|bank_payment"),
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    party_name: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """List vouchers of the requested type for the cheque-print picker."""
    _require(user, "cheque_print")

    if source_type == "expense_payment":
        filt: dict = {}
        if from_date:
            filt["expense_date"] = {"$gte": from_date}
        if to_date:
            existing = filt.get("expense_date", {})
            existing["$lte"] = to_date
            filt["expense_date"] = existing
        rows = await db.expense_entries.find(filt, {"_id": 0}).to_list(200)
        return [{"id": r.get("id"), "voucher_number": r.get("expense_no"), "party_name": r.get("payee_name") or r.get("vendor_name"), "amount": r.get("total_amount") or r.get("amount"), "date": r.get("expense_date"), "narration": r.get("notes"), "source_type": "expense_payment"} for r in rows]

    # payment_voucher / supplier_payment / customer_refund / bank_payment → vouchers collection
    type_map = {
        "payment_voucher": "PAYMENT",
        "supplier_payment": "PAYMENT",
        "customer_refund": "RECEIPT",
        "bank_payment": "PAYMENT",
    }
    filt = {"voucher_type": type_map.get(source_type, "PAYMENT")}
    if from_date:
        filt["voucher_date"] = {"$gte": from_date}
    if to_date:
        existing = filt.get("voucher_date", {})
        existing["$lte"] = to_date
        filt["voucher_date"] = existing
    if party_name:
        filt["party_name"] = {"$regex": party_name, "$options": "i"}

    rows = await db.vouchers.find(filt, {"_id": 0}).sort("voucher_date", -1).to_list(500)
    return [{"id": r.get("id"), "voucher_number": r.get("voucher_no") or r.get("voucher_number"), "party_name": r.get("party_name"), "amount": r.get("amount"), "date": r.get("voucher_date") or r.get("date"), "narration": r.get("narration"), "bank_account_id": r.get("bank_account_id"), "source_type": source_type} for r in rows]


@router.get("/vouchers/payment/{source_type}/{source_id}")
async def get_voucher_for_cheque(source_type: str, source_id: str, user: dict = Depends(get_current_user)):
    """Fetch auto-fill data for a single voucher."""
    _require(user, "cheque_print")
    data = await _fetch_voucher(source_type, source_id)
    return data


# ══════════════════════════════════════════════════════════════
# Bank Account Master
# ══════════════════════════════════════════════════════════════

@router.get("/bank-accounts")
async def list_bank_accounts(user: dict = Depends(get_current_user)):
    _require(user, "cheque_print")
    return await crud_list("bank_accounts", sort_field="bank_name")


@router.post("/bank-accounts")
async def create_bank_account(payload: BankAccountIn, user: dict = Depends(get_current_user)):
    _require_template_admin(user)
    return await crud_create("bank_accounts", payload.model_dump(), user)


@router.put("/bank-accounts/{account_id}")
async def update_bank_account(account_id: str, payload: BankAccountIn, user: dict = Depends(get_current_user)):
    _require_template_admin(user)
    return await crud_update("bank_accounts", account_id, payload.model_dump(), user)


# ══════════════════════════════════════════════════════════════
# Cheque Template Manager
# ══════════════════════════════════════════════════════════════

@router.get("/templates")
async def list_templates(
    bank_name: Optional[str] = None,
    include_archived: bool = False,
    user: dict = Depends(get_current_user),
):
    _require(user, "cheque_print")
    filt: dict = {}
    if bank_name:
        filt["bank_name"] = bank_name
    if not include_archived:
        filt["archived"] = {"$ne": True}
    return await crud_list("cheque_templates", filt=filt, sort_field="template_name")


@router.get("/templates/{template_id}")
async def get_template(template_id: str, user: dict = Depends(get_current_user)):
    _require(user, "cheque_print")
    return await crud_get("cheque_templates", template_id)


# /templates/seed-defaults is a literal route that must be registered before
# /templates/{template_id} — otherwise "seed-defaults" would be swallowed as template_id.
@router.post("/templates/seed-defaults")
async def seed_default_templates_early(user: dict = Depends(get_current_user)):
    """Create the standard bank templates if they don't already exist (idempotent)."""
    _require_template_admin(user)
    created = []
    for tpl in _DEFAULT_TEMPLATES:
        existing = await db.cheque_templates.find_one(
            {"bank_name": tpl["bank_name"], "template_name": tpl["template_name"]},
            {"_id": 0, "id": 1},
        )
        if not existing:
            doc = {**tpl}
            saved = await crud_create("cheque_templates", doc, user)
            created.append(saved.get("template_name"))
    return {"created": created, "total": len(created)}


@router.post("/templates")
async def create_template(payload: ChequeTemplateIn, user: dict = Depends(get_current_user)):
    _require_template_admin(user)
    doc = payload.model_dump()
    doc["archived"] = False
    return await crud_create("cheque_templates", doc, user)


@router.put("/templates/{template_id}")
async def update_template(template_id: str, payload: ChequeTemplateIn, user: dict = Depends(get_current_user)):
    _require_template_admin(user)
    return await crud_update("cheque_templates", template_id, payload.model_dump(), user)


@router.post("/templates/{template_id}/duplicate")
async def duplicate_template(template_id: str, user: dict = Depends(get_current_user)):
    _require_template_admin(user)
    src = await crud_get("cheque_templates", template_id)
    clone = {k: v for k, v in src.items() if k not in ("id", "created_at", "updated_at")}
    clone["template_name"] = f"{src.get('template_name', 'Template')} (Copy)"
    clone["is_active"] = False
    clone["archived"] = False
    return await crud_create("cheque_templates", clone, user)


@router.post("/templates/{template_id}/activate")
async def activate_template(template_id: str, user: dict = Depends(get_current_user)):
    _require_template_admin(user)
    tpl = await crud_get("cheque_templates", template_id)
    if tpl.get("archived"):
        raise HTTPException(400, "Cannot activate an archived template")
    return await crud_update("cheque_templates", template_id, {"is_active": True}, user)


@router.post("/templates/{template_id}/archive")
async def archive_template(template_id: str, user: dict = Depends(get_current_user)):
    _require_template_admin(user)
    await crud_get("cheque_templates", template_id)
    return await crud_update("cheque_templates", template_id, {"archived": True, "is_active": False}, user)


@router.post("/templates/{template_id}/background")
async def upload_background(
    template_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    _require_template_admin(user)
    await crud_get("cheque_templates", template_id)
    content_type = file.content_type or "image/png"
    if not content_type.startswith("image/"):
        raise HTTPException(400, "Background must be an image")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    ext = (content_type.split("/")[-1] or "png").split(";")[0]
    path = f"cheque-templates/{template_id}/{new_id()}.{ext}"
    put_object(path, data, content_type)
    await crud_update("cheque_templates", template_id, {"background_image": path}, user)
    return {"background_image": path}


@router.get("/templates/{template_id}/background")
async def fetch_background(template_id: str, user: dict = Depends(get_current_user)):
    _require(user, "cheque_print")
    tpl = await crud_get("cheque_templates", template_id)
    path = tpl.get("background_image")
    if not path:
        raise HTTPException(404, "No background image for this template")
    data, content_type = get_object(path)
    return Response(content=data, media_type=content_type)


@router.get("/field-keys")
async def field_keys(user: dict = Depends(get_current_user)):
    _require(user, "cheque_print")
    return {"fields": list(FIELD_KEYS)}


# ══════════════════════════════════════════════════════════════
# Default bank templates seeder
# ══════════════════════════════════════════════════════════════

_DEFAULT_TEMPLATES = [
    {
        "template_name": "SBI Standard",
        "bank_name": "SBI",
        "cheque_width_mm": 203.0,
        "cheque_height_mm": 93.0,
        "field_positions": [
            {"field": "date",           "x_mm": 148, "y_mm": 14, "font_family": "Courier", "font_size": 10, "char_spacing": 3.5, "align": "left", "enabled": True},
            {"field": "payee_name",     "x_mm": 28,  "y_mm": 30, "font_family": "Helvetica", "font_size": 11, "char_spacing": 0, "align": "left", "enabled": True},
            {"field": "amount_words",   "x_mm": 18,  "y_mm": 50, "font_family": "Helvetica", "font_size": 10, "char_spacing": 0, "align": "left", "enabled": True},
            {"field": "amount_figures", "x_mm": 168, "y_mm": 36, "font_family": "Courier",   "font_size": 11, "char_spacing": 0, "align": "right", "enabled": True},
            {"field": "account_payee",  "x_mm": 10,  "y_mm": 10, "font_family": "Helvetica", "font_size": 8,  "char_spacing": 0, "align": "left", "enabled": True},
        ],
        "is_active": True, "archived": False,
    },
    {
        "template_name": "HDFC Standard",
        "bank_name": "HDFC",
        "cheque_width_mm": 205.0,
        "cheque_height_mm": 93.0,
        "field_positions": [
            {"field": "date",           "x_mm": 152, "y_mm": 14, "font_family": "Courier", "font_size": 10, "char_spacing": 4.0, "align": "left", "enabled": True},
            {"field": "payee_name",     "x_mm": 30,  "y_mm": 32, "font_family": "Helvetica", "font_size": 11, "char_spacing": 0, "align": "left", "enabled": True},
            {"field": "amount_words",   "x_mm": 18,  "y_mm": 52, "font_family": "Helvetica", "font_size": 10, "char_spacing": 0, "align": "left", "enabled": True},
            {"field": "amount_figures", "x_mm": 170, "y_mm": 38, "font_family": "Courier",   "font_size": 11, "char_spacing": 0, "align": "right", "enabled": True},
            {"field": "account_payee",  "x_mm": 10,  "y_mm": 10, "font_family": "Helvetica", "font_size": 8,  "char_spacing": 0, "align": "left", "enabled": True},
        ],
        "is_active": True, "archived": False,
    },
    {
        "template_name": "ICICI Standard",
        "bank_name": "ICICI",
        "cheque_width_mm": 203.0,
        "cheque_height_mm": 91.0,
        "field_positions": [
            {"field": "date",           "x_mm": 150, "y_mm": 12, "font_family": "Courier", "font_size": 10, "char_spacing": 4.0, "align": "left", "enabled": True},
            {"field": "payee_name",     "x_mm": 26,  "y_mm": 30, "font_family": "Helvetica", "font_size": 11, "char_spacing": 0, "align": "left", "enabled": True},
            {"field": "amount_words",   "x_mm": 18,  "y_mm": 50, "font_family": "Helvetica", "font_size": 10, "char_spacing": 0, "align": "left", "enabled": True},
            {"field": "amount_figures", "x_mm": 168, "y_mm": 36, "font_family": "Courier",   "font_size": 11, "char_spacing": 0, "align": "right", "enabled": True},
            {"field": "account_payee",  "x_mm": 10,  "y_mm": 8,  "font_family": "Helvetica", "font_size": 8,  "char_spacing": 0, "align": "left", "enabled": True},
        ],
        "is_active": True, "archived": False,
    },
    {
        "template_name": "PNB Standard",
        "bank_name": "PNB",
        "cheque_width_mm": 204.0,
        "cheque_height_mm": 93.0,
        "field_positions": [
            {"field": "date",           "x_mm": 148, "y_mm": 15, "font_family": "Courier", "font_size": 10, "char_spacing": 3.8, "align": "left", "enabled": True},
            {"field": "payee_name",     "x_mm": 28,  "y_mm": 33, "font_family": "Helvetica", "font_size": 11, "char_spacing": 0, "align": "left", "enabled": True},
            {"field": "amount_words",   "x_mm": 18,  "y_mm": 52, "font_family": "Helvetica", "font_size": 10, "char_spacing": 0, "align": "left", "enabled": True},
            {"field": "amount_figures", "x_mm": 168, "y_mm": 38, "font_family": "Courier",   "font_size": 11, "char_spacing": 0, "align": "right", "enabled": True},
            {"field": "account_payee",  "x_mm": 10,  "y_mm": 10, "font_family": "Helvetica", "font_size": 8,  "char_spacing": 0, "align": "left", "enabled": True},
        ],
        "is_active": True, "archived": False,
    },
    {
        "template_name": "Axis Bank Standard",
        "bank_name": "Axis",
        "cheque_width_mm": 203.0,
        "cheque_height_mm": 92.0,
        "field_positions": [
            {"field": "date",           "x_mm": 149, "y_mm": 13, "font_family": "Courier", "font_size": 10, "char_spacing": 4.0, "align": "left", "enabled": True},
            {"field": "payee_name",     "x_mm": 27,  "y_mm": 31, "font_family": "Helvetica", "font_size": 11, "char_spacing": 0, "align": "left", "enabled": True},
            {"field": "amount_words",   "x_mm": 18,  "y_mm": 51, "font_family": "Helvetica", "font_size": 10, "char_spacing": 0, "align": "left", "enabled": True},
            {"field": "amount_figures", "x_mm": 169, "y_mm": 37, "font_family": "Courier",   "font_size": 11, "char_spacing": 0, "align": "right", "enabled": True},
            {"field": "account_payee",  "x_mm": 10,  "y_mm": 9,  "font_family": "Helvetica", "font_size": 8,  "char_spacing": 0, "align": "left", "enabled": True},
        ],
        "is_active": True, "archived": False,
    },
    {
        "template_name": "Custom Bank (Blank)",
        "bank_name": "Custom",
        "cheque_width_mm": 203.0,
        "cheque_height_mm": 93.0,
        "field_positions": [],
        "is_active": False, "archived": False,
    },
]


@router.post("/templates/seed-defaults")
async def seed_default_templates(user: dict = Depends(get_current_user)):
    """Create the standard bank templates if they don't already exist (idempotent)."""
    _require_template_admin(user)
    created = []
    for tpl in _DEFAULT_TEMPLATES:
        existing = await db.cheque_templates.find_one(
            {"bank_name": tpl["bank_name"], "template_name": tpl["template_name"]},
            {"_id": 0, "id": 1},
        )
        if not existing:
            doc = {**tpl}
            saved = await crud_create("cheque_templates", doc, user)
            created.append(saved.get("template_name"))
    return {"created": created, "total": len(created)}


# ══════════════════════════════════════════════════════════════
# Validation helpers
# ══════════════════════════════════════════════════════════════

def _validate_cheque_inputs(payee_name: str, amount: float):
    if not (payee_name or "").strip():
        raise HTTPException(400, "Payee name is mandatory")
    if amount <= 0:
        raise HTTPException(400, "Amount must be greater than zero")


async def _assert_unique_cheque_number(bank_account_id: str, cheque_number: str):
    existing = await db.cheque_transactions.find_one(
        {"bank_account_id": bank_account_id, "cheque_number": cheque_number,
         "status": {"$in": ["printed", "reprinted", "cancelled", "void", "cleared", "bounced"]}},
        {"_id": 0, "id": 1},
    )
    if existing:
        raise HTTPException(409, f"Cheque number {cheque_number} already used for this bank account")


# ══════════════════════════════════════════════════════════════
# Cheque Printing workflow
# ══════════════════════════════════════════════════════════════

@router.post("/cheques/preview")
async def preview_cheque(req: ChequePreviewRequest, user: dict = Depends(get_current_user)):
    _require(user, "cheque_print")
    _validate_cheque_inputs(req.payee_name, req.amount)
    render = await _build_render(req)
    tpl = render["template"]
    return {
        "amount_words": render["amount_words"],
        "cheque_width_mm": tpl.get("cheque_width_mm"),
        "cheque_height_mm": tpl.get("cheque_height_mm"),
        "background_image": tpl.get("background_image"),
        "fields": render["fields"],
        "values": render["values"],
    }


async def _do_print_pdf(req: ChequeRequestBase, cheque_number: str, test_print: bool, printer: Optional[str], user: dict, ip: str) -> tuple[bytes, Optional[dict]]:
    """Render the PDF and, if not a test print, save the transaction + issue register entry."""
    _validate_cheque_inputs(req.payee_name, req.amount)

    if not test_print:
        await _assert_unique_cheque_number(req.bank_account_id, cheque_number)

    render = await _build_render(req)
    account = render["account"]
    tpl = render["template"]

    background_bytes = None
    if test_print and tpl.get("background_image"):
        try:
            background_bytes, _ = get_object(tpl["background_image"])
        except Exception:
            background_bytes = None

    pdf_bytes = build_cheque_pdf(
        width_mm=float(tpl.get("cheque_width_mm", 203.0)),
        height_mm=float(tpl.get("cheque_height_mm", 93.0)),
        fields=render["fields"],
        background_bytes=background_bytes,
        test_print=test_print,
    )

    saved = None
    if not test_print:
        # Double-check after render (parallel requests race window)
        await _assert_unique_cheque_number(req.bank_account_id, cheque_number)
        now = now_iso()
        txn = {
            "bank_account_id": req.bank_account_id,
            "bank_name": account.get("bank_name"),
            "template_id": tpl.get("id"),
            "cheque_number": cheque_number,
            "payee_name": req.payee_name,
            "amount": req.amount,
            "amount_in_words": render["amount_words"],
            "cheque_date": req.cheque_date,
            "narration": req.narration or "",
            "company_name": req.company_name or "",
            "source_type": req.source_type or "",
            "source_id": req.source_id or "",
            "voucher_number": req.voucher_number or "",
            "account_payee": req.account_payee,
            "status": "printed",
            "printed_at": now,
            "printed_by": user.get("id"),
            "printer": printer or "",
            "reprint_count": 0,
            "reprint_log": [],
            "print_ip": ip,
        }
        saved = await crud_create("cheque_transactions", txn, user)
        # Cheque issue register entry
        reg = {
            "bank_account_id": req.bank_account_id,
            "bank_name": account.get("bank_name"),
            "cheque_number": cheque_number,
            "cheque_txn_id": saved["id"],
            "payee_name": req.payee_name,
            "amount": req.amount,
            "cheque_date": req.cheque_date,
            "issue_date": now[:10],
            "status": "printed",
            "voucher_number": req.voucher_number or "",
            "narration": req.narration or "",
            "issued_by": user.get("id"),
        }
        await crud_create("cheque_issue_register", reg, user)
        await log_audit("PRINT", "cheque_transactions", saved["id"], user, new_values={
            "bank_account_id": req.bank_account_id,
            "cheque_number": cheque_number,
            "amount": req.amount,
            "printer": printer,
            "print_ip": ip,
            "printed_at": now,
        })

    return pdf_bytes, saved


@router.post("/cheques/print")
async def print_cheque(req: ChequePrintRequest, request: Request, user: dict = Depends(get_current_user)):
    _require(user, "cheque_print")
    ip = _client_ip(request)
    pdf_bytes, _ = await _do_print_pdf(req, req.cheque_number, req.test_print, req.printer, user, ip)
    safe = "".join(c for c in (req.payee_name or "cheque") if c.isalnum() or c in " -_").strip() or "cheque"
    suffix = "-TEST" if req.test_print else ""
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="cheque-{safe}{suffix}.pdf"'},
    )


@router.post("/cheques/bulk-print")
async def bulk_print_cheques(req: BulkPrintRequest, request: Request, user: dict = Depends(get_current_user)):
    """Print multiple cheques as separate PDF bytes; returns a ZIP of PDFs."""
    _require(user, "cheque_print")
    if not req.items:
        raise HTTPException(400, "No items in bulk print request")
    if len(req.items) > 50:
        raise HTTPException(400, "Bulk print is limited to 50 cheques at a time")

    import io, zipfile
    ip = _client_ip(request)
    zip_buf = io.BytesIO()
    results = []
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, item in enumerate(req.items):
            try:
                base = ChequeRequestBase(
                    bank_account_id=item.bank_account_id,
                    payee_name=item.payee_name,
                    amount=item.amount,
                    cheque_date=item.cheque_date,
                    account_payee=item.account_payee,
                    narration=item.narration,
                    company_name=item.company_name,
                    source_type=item.source_type,
                    source_id=item.source_id,
                    voucher_number=item.voucher_number,
                )
                pdf_bytes, saved = await _do_print_pdf(base, item.cheque_number, False, req.printer, user, ip)
                safe = "".join(c for c in item.payee_name if c.isalnum() or c in " -_").strip() or f"cheque_{i+1}"
                fname = f"{i+1:02d}_{item.cheque_number}_{safe}.pdf"
                zf.writestr(fname, pdf_bytes)
                results.append({"cheque_number": item.cheque_number, "status": "printed", "id": saved.get("id") if saved else None})
            except HTTPException as exc:
                results.append({"cheque_number": item.cheque_number, "status": "error", "detail": exc.detail})

    zip_buf.seek(0)
    return Response(
        content=zip_buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=bulk-cheques.zip", "X-Print-Results": str(len(results))},
    )


@router.post("/cheques/{cheque_id}/reprint")
async def reprint_cheque(cheque_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Reprint an existing printed/reprinted cheque (same number, increments reprint_count)."""
    _require(user, "cheque_print")
    cheque = await crud_get("cheque_transactions", cheque_id)
    if cheque.get("status") in ("cancelled", "void"):
        raise HTTPException(400, f"Cannot reprint a {cheque.get('status')} cheque")

    ip = _client_ip(request)
    account = await crud_get("bank_accounts", cheque["bank_account_id"])
    tpl = await _resolve_template(account)
    words = amount_in_words(float(cheque["amount"]))
    values = {
        "date": (cheque.get("cheque_date") or "").replace("-", ""),
        "payee_name": cheque.get("payee_name", ""),
        "amount_words": words,
        "amount_figures": f"**{float(cheque['amount']):,.2f}/-",
        "account_payee": _ACCOUNT_PAYEE_TEXT if cheque.get("account_payee", True) else "",
        "signature_marker": "",
    }
    fields = _resolve_fields(tpl, values)
    pdf_bytes = build_cheque_pdf(
        width_mm=float(tpl.get("cheque_width_mm", 203.0)),
        height_mm=float(tpl.get("cheque_height_mm", 93.0)),
        fields=fields,
    )

    now = now_iso()
    reprint_log = list(cheque.get("reprint_log") or [])
    reprint_log.append({"at": now, "by": user.get("id"), "ip": ip})
    await crud_update("cheque_transactions", cheque_id, {
        "status": "reprinted",
        "reprint_count": int(cheque.get("reprint_count") or 0) + 1,
        "last_reprint_at": now,
        "last_reprint_by": user.get("id"),
        "reprint_log": reprint_log,
    }, user)
    await log_audit("REPRINT", "cheque_transactions", cheque_id, user, new_values={"reprint_count": int(cheque.get("reprint_count") or 0) + 1, "ip": ip})

    safe = "".join(c for c in (cheque.get("payee_name") or "cheque") if c.isalnum() or c in " -_").strip() or "cheque"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="reprint-{safe}.pdf"'},
    )


# ══════════════════════════════════════════════════════════════
# Cheque lifecycle management
# ══════════════════════════════════════════════════════════════

@router.get("/cheques")
async def list_cheques(
    bank_account_id: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    payee_name: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require(user, "cheque_print")
    filt: dict = {}
    if bank_account_id:
        filt["bank_account_id"] = bank_account_id
    if status:
        filt["status"] = status
    if from_date:
        filt["cheque_date"] = {"$gte": from_date}
    if to_date:
        existing = filt.get("cheque_date", {})
        if isinstance(existing, dict):
            existing["$lte"] = to_date
        else:
            existing = {"$gte": existing, "$lte": to_date} if existing else {"$lte": to_date}
        filt["cheque_date"] = existing
    if payee_name:
        filt["payee_name"] = {"$regex": payee_name, "$options": "i"}
    return await crud_list("cheque_transactions", filt=filt, sort_field="printed_at")


@router.get("/cheques/{cheque_id}")
async def get_cheque(cheque_id: str, user: dict = Depends(get_current_user)):
    _require(user, "cheque_print")
    return await crud_get("cheque_transactions", cheque_id)


@router.post("/cheques/{cheque_id}/cancel")
async def cancel_cheque(cheque_id: str, req: ChequeCancelRequest, user: dict = Depends(get_current_user)):
    _require(user, "cheque_cancel")
    if not (req.reason or "").strip():
        raise HTTPException(400, "Cancellation reason is mandatory")
    cheque = await crud_get("cheque_transactions", cheque_id)
    if cheque.get("status") in ("cancelled", "void"):
        raise HTTPException(400, f"Cheque is already {cheque.get('status')}")

    now = now_iso()
    result = await crud_update("cheque_transactions", cheque_id, {
        "status": "cancelled",
        "cancelled_at": now,
        "cancelled_by": user.get("id"),
        "cancellation_reason": req.reason,
    }, user)
    await db.cheque_issue_register.update_one(
        {"cheque_txn_id": cheque_id},
        {"$set": {"status": "cancelled", "updated_at": now}},
    )
    await log_audit("CANCEL", "cheque_transactions", cheque_id, user,
                    old_values={"status": cheque.get("status")},
                    new_values={"status": "cancelled", "cancellation_reason": req.reason})
    return result


@router.post("/cheques/{cheque_id}/void")
async def void_cheque(cheque_id: str, req: ChequeVoidRequest, user: dict = Depends(get_current_user)):
    """Void a cheque — stronger than cancel. Void means the cheque leaf was destroyed/spoiled."""
    _require(user, "cheque_cancel")
    if not (req.reason or "").strip():
        raise HTTPException(400, "Void reason is mandatory")
    cheque = await crud_get("cheque_transactions", cheque_id)
    if cheque.get("is_void"):
        raise HTTPException(400, "Cheque is already voided")

    now = now_iso()
    result = await crud_update("cheque_transactions", cheque_id, {
        "status": "void",
        "is_void": True,
        "void_reason": req.reason,
        "void_at": now,
        "void_by": user.get("id"),
    }, user)
    await db.cheque_issue_register.update_one(
        {"cheque_txn_id": cheque_id},
        {"$set": {"status": "void", "updated_at": now}},
    )
    await log_audit("VOID", "cheque_transactions", cheque_id, user,
                    old_values={"status": cheque.get("status")},
                    new_values={"status": "void", "void_reason": req.reason})
    return result


@router.post("/cheques/{cheque_id}/status")
async def update_cheque_status(cheque_id: str, req: ChequeStatusUpdateRequest, user: dict = Depends(get_current_user)):
    """Mark a cheque as cleared or bounced (bank confirmation)."""
    _require(user, "cheque_print")
    cheque = await crud_get("cheque_transactions", cheque_id)
    if cheque.get("status") in ("cancelled", "void"):
        raise HTTPException(400, f"Cannot update status of a {cheque.get('status')} cheque")

    update: dict = {"status": req.status}
    if req.status == "cleared":
        update["cleared_date"] = req.cleared_date or now_iso()[:10]
    elif req.status == "bounced":
        update["bounced_date"] = req.bounced_date or now_iso()[:10]
        if req.bounced_reason:
            update["bounced_reason"] = req.bounced_reason

    result = await crud_update("cheque_transactions", cheque_id, update, user)
    now = now_iso()
    await db.cheque_issue_register.update_one(
        {"cheque_txn_id": cheque_id},
        {"$set": {"status": req.status, "updated_at": now}},
    )
    await log_audit("STATUS_UPDATE", "cheque_transactions", cheque_id, user,
                    old_values={"status": cheque.get("status")},
                    new_values=update)
    return result


# ══════════════════════════════════════════════════════════════
# Cheque Issue Register
# ══════════════════════════════════════════════════════════════

@router.get("/register")
async def cheque_issue_register(
    bank_account_id: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require(user, "cheque_print")
    filt: dict = {}
    if bank_account_id:
        filt["bank_account_id"] = bank_account_id
    if status:
        filt["status"] = status
    if from_date:
        filt["issue_date"] = {"$gte": from_date}
    if to_date:
        existing = filt.get("issue_date", {})
        if isinstance(existing, dict):
            existing["$lte"] = to_date
        else:
            existing = {"$lte": to_date}
        filt["issue_date"] = existing
    return await crud_list("cheque_issue_register", filt=filt, sort_field="issue_date")


# ══════════════════════════════════════════════════════════════
# Reports
# ══════════════════════════════════════════════════════════════

@router.get("/reports/cheque-register")
async def report_cheque_register(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    bank_account_id: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Cheque register report — all cheques with full details."""
    _require(user, "cheque_print")
    filt: dict = {}
    if bank_account_id:
        filt["bank_account_id"] = bank_account_id
    if status:
        filt["status"] = status
    if from_date:
        filt["cheque_date"] = {"$gte": from_date}
    if to_date:
        existing = filt.get("cheque_date", {})
        if isinstance(existing, dict):
            existing["$lte"] = to_date
        else:
            existing = {"$lte": to_date}
        filt["cheque_date"] = existing
    cheques = await crud_list("cheque_transactions", filt=filt, sort_field="cheque_date")
    total_amount = sum(float(c.get("amount") or 0) for c in cheques if c.get("status") not in ("cancelled", "void"))
    return {
        "rows": cheques,
        "total_count": len(cheques),
        "total_amount": round(total_amount, 2),
        "from_date": from_date,
        "to_date": to_date,
    }


@router.get("/reports/bank-wise")
async def report_bank_wise(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Bank-wise cheque summary."""
    _require(user, "cheque_print")
    filt: dict = {}
    if from_date:
        filt["cheque_date"] = {"$gte": from_date}
    if to_date:
        existing = filt.get("cheque_date", {})
        if isinstance(existing, dict):
            existing["$lte"] = to_date
        else:
            existing = {"$lte": to_date}
        filt["cheque_date"] = existing
    cheques = await crud_list("cheque_transactions", filt=filt)
    summary: dict = {}
    for c in cheques:
        bank = c.get("bank_name") or "Unknown"
        if bank not in summary:
            summary[bank] = {"bank_name": bank, "total_cheques": 0, "total_amount": 0.0, "printed": 0, "cancelled": 0, "cleared": 0, "bounced": 0, "void": 0}
        summary[bank]["total_cheques"] += 1
        if c.get("status") not in ("cancelled", "void"):
            summary[bank]["total_amount"] += float(c.get("amount") or 0)
        st = c.get("status") or "printed"
        if st in summary[bank]:
            summary[bank][st] += 1
    rows = sorted(summary.values(), key=lambda x: x["bank_name"])
    return {"rows": rows, "from_date": from_date, "to_date": to_date}


@router.get("/reports/party-wise")
async def report_party_wise(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    bank_account_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Party (payee) wise cheque summary."""
    _require(user, "cheque_print")
    filt: dict = {}
    if bank_account_id:
        filt["bank_account_id"] = bank_account_id
    if from_date:
        filt["cheque_date"] = {"$gte": from_date}
    if to_date:
        existing = filt.get("cheque_date", {})
        if isinstance(existing, dict):
            existing["$lte"] = to_date
        else:
            existing = {"$lte": to_date}
        filt["cheque_date"] = existing
    cheques = await crud_list("cheque_transactions", filt=filt)
    summary: dict = {}
    for c in cheques:
        party = (c.get("payee_name") or "Unknown").strip()
        if party not in summary:
            summary[party] = {"payee_name": party, "total_cheques": 0, "total_amount": 0.0, "cheques": []}
        summary[party]["total_cheques"] += 1
        if c.get("status") not in ("cancelled", "void"):
            summary[party]["total_amount"] += float(c.get("amount") or 0)
        summary[party]["cheques"].append({"cheque_number": c.get("cheque_number"), "amount": c.get("amount"), "cheque_date": c.get("cheque_date"), "status": c.get("status")})
    rows = sorted(summary.values(), key=lambda x: x["payee_name"])
    return {"rows": rows, "from_date": from_date, "to_date": to_date}


@router.get("/reports/outstanding")
async def report_outstanding(
    bank_account_id: Optional[str] = None,
    as_of_date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Outstanding cheques — printed/reprinted but not yet cleared or bounced."""
    _require(user, "cheque_print")
    filt: dict = {"status": {"$in": ["printed", "reprinted"]}}
    if bank_account_id:
        filt["bank_account_id"] = bank_account_id
    if as_of_date:
        filt["cheque_date"] = {"$lte": as_of_date}
    cheques = await crud_list("cheque_transactions", filt=filt, sort_field="cheque_date")
    total = sum(float(c.get("amount") or 0) for c in cheques)
    return {"rows": cheques, "total_outstanding": round(total, 2), "count": len(cheques), "as_of_date": as_of_date}


@router.get("/reports/date-wise")
async def report_date_wise(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    bank_account_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Date-wise cheque summary grouped by cheque_date."""
    _require(user, "cheque_print")
    filt: dict = {}
    if bank_account_id:
        filt["bank_account_id"] = bank_account_id
    if from_date:
        filt["cheque_date"] = {"$gte": from_date}
    if to_date:
        existing = filt.get("cheque_date", {})
        if isinstance(existing, dict):
            existing["$lte"] = to_date
        else:
            existing = {"$lte": to_date}
        filt["cheque_date"] = existing
    cheques = await crud_list("cheque_transactions", filt=filt, sort_field="cheque_date")
    by_date: dict = {}
    for c in cheques:
        d = (c.get("cheque_date") or "")[:10]
        if d not in by_date:
            by_date[d] = {"date": d, "count": 0, "total_amount": 0.0, "cheques": []}
        by_date[d]["count"] += 1
        if c.get("status") not in ("cancelled", "void"):
            by_date[d]["total_amount"] += float(c.get("amount") or 0)
        by_date[d]["cheques"].append(c)
    rows = [v for _, v in sorted(by_date.items())]
    return {"rows": rows, "from_date": from_date, "to_date": to_date}


@router.get("/cheque-history/{cheque_id}")
async def cheque_history(cheque_id: str, user: dict = Depends(get_current_user)):
    """Full audit history for a specific cheque transaction."""
    _require(user, "cheque_print")
    await crud_get("cheque_transactions", cheque_id)
    logs = await crud_list("audit_logs", filt={"document_id": cheque_id}, sort_field="created_at")
    return {"logs": logs}
