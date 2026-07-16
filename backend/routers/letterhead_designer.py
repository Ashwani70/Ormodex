"""Enterprise Letterhead & Document Designer — full CRUD + PDF preview + versioning.

Endpoints:
  Templates  : list, get, create, update, soft-delete, clone, set-default
  Versions   : list history, restore snapshot
  Uploads    : logo, secondary logo, background image
  PDF        : preview render
  Documents  : get/update apply_to list
  Seed       : seed 6 premium default themes

RBAC:
  letterhead_design   — read, preview, assign to docs
  letterhead_manage   — create, update, delete, clone, set-default, seed
  admin               — everything
"""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from core.auth_utils import get_current_user, is_admin_role
from core.db import db
from core.letterhead_pdf import THEME_PRESETS, build_preview_pdf
from core.storage import get_object, put_object
from core.utils import crud_create, crud_get, crud_list, crud_update, log_audit, new_id, now_iso

router = APIRouter(prefix="/letterhead", tags=["Letterhead Designer"])


# ── RBAC helpers ───────────────────────────────────────────────────────────────

def _req_read(user: dict) -> dict:
    if is_admin_role(user.get("role")):
        return user
    if "letterhead_design" in user.get("module_permissions", []) or \
       "letterhead_manage" in user.get("module_permissions", []):
        return user
    raise HTTPException(403, "'letterhead_design' permission required")


def _req_manage(user: dict) -> dict:
    if is_admin_role(user.get("role")):
        return user
    if "letterhead_manage" in user.get("module_permissions", []):
        return user
    raise HTTPException(403, "'letterhead_manage' permission required")


def _tid(user: dict) -> str:
    return user.get("tenant_id") or user.get("company_id") or "default"


# ── Pydantic models ────────────────────────────────────────────────────────────

class TemplateBase(BaseModel):
    theme: str = "corporate_blue"
    page_size: str = "A4"
    margin_top: float = 20.0
    margin_bottom: float = 20.0
    margin_left: float = 20.0
    margin_right: float = 20.0
    header_height: float = 35.0
    footer_height: float = 22.0
    logo_position: str = "left"
    logo_url: Optional[str] = None
    logo2_url: Optional[str] = None
    logo_width_mm: float = 40.0
    logo_height_mm: float = 18.0
    header_elements: list = Field(default_factory=list)
    footer_elements: list = Field(default_factory=list)
    watermark_text: Optional[str] = None
    watermark_opacity: float = 0.08
    watermark_angle: float = -45.0
    watermark_font_size: float = 60.0
    watermark_color: str = "#888888"
    background_image: Optional[str] = None
    primary_color: str = "#1a56db"
    secondary_color: str = "#f3f4f6"
    accent_color: str = "#f59e0b"
    text_color: str = "#111827"
    header_bg_color: str = "#1a56db"
    footer_bg_color: str = "#f0f4ff"
    font_family: str = "Helvetica"
    font_size_body: float = 10.0
    applied_to: list = Field(default_factory=list)
    is_default: bool = False
    branch_id: Optional[str] = None
    change_note: Optional[str] = None


class TemplateIn(TemplateBase):
    template_name: str


class TemplateUpdate(TemplateBase):
    template_name: Optional[str] = None


class StatusPatch(BaseModel):
    is_active: bool


class ApplyToUpdate(BaseModel):
    applied_to: list


class RestoreVersionIn(BaseModel):
    change_note: Optional[str] = "Restored from version history"


# ── Premium default themes ─────────────────────────────────────────────────────

_PREMIUM_TEMPLATES: list[dict] = [
    {
        "template_name": "Corporate Blue",
        "theme": "corporate_blue",
        "page_size": "A4",
        "margin_top": 15.0, "margin_bottom": 15.0,
        "margin_left": 20.0, "margin_right": 20.0,
        "header_height": 38.0, "footer_height": 24.0,
        "logo_position": "left",
        "logo_width_mm": 45.0, "logo_height_mm": 20.0,
        "primary_color": "#1a56db", "secondary_color": "#e8f0fe",
        "accent_color": "#f59e0b", "text_color": "#111827",
        "header_bg_color": "#1a56db", "footer_bg_color": "#f0f4ff",
        "font_family": "Helvetica", "font_size_body": 10.0,
        "header_elements": [
            {"type": "text", "value": "{company_name}", "x_mm": 60, "y_mm": 20, "size": 16, "color": "#ffffff", "align": "left"},
            {"type": "text", "value": "{company_tagline}", "x_mm": 60, "y_mm": 28, "size": 8, "color": "#e0e7ff", "align": "left"},
        ],
        "footer_elements": [
            {"type": "text", "value": "Page {page} of {total}", "x_mm": None, "y_mm": None, "size": 7.5, "color": "#374151", "align": "right"},
        ],
        "applied_to": [],
    },
    {
        "template_name": "Modern Dark",
        "theme": "modern_dark",
        "page_size": "A4",
        "margin_top": 15.0, "margin_bottom": 15.0,
        "margin_left": 20.0, "margin_right": 20.0,
        "header_height": 38.0, "footer_height": 22.0,
        "logo_position": "left",
        "logo_width_mm": 42.0, "logo_height_mm": 18.0,
        "primary_color": "#18181b", "secondary_color": "#27272a",
        "accent_color": "#facc15", "text_color": "#ffffff",
        "header_bg_color": "#18181b", "footer_bg_color": "#27272a",
        "font_family": "Helvetica", "font_size_body": 10.0,
        "header_elements": [],
        "footer_elements": [],
        "applied_to": [],
    },
    {
        "template_name": "Luxury Gold",
        "theme": "luxury_gold",
        "page_size": "A4",
        "margin_top": 18.0, "margin_bottom": 18.0,
        "margin_left": 22.0, "margin_right": 22.0,
        "header_height": 42.0, "footer_height": 26.0,
        "logo_position": "center",
        "logo_width_mm": 50.0, "logo_height_mm": 22.0,
        "primary_color": "#78350f", "secondary_color": "#fef3c7",
        "accent_color": "#d97706", "text_color": "#1c1917",
        "header_bg_color": "#451a03", "footer_bg_color": "#fef3c7",
        "font_family": "Helvetica", "font_size_body": 10.0,
        "header_elements": [],
        "footer_elements": [],
        "applied_to": [],
    },
    {
        "template_name": "Industrial Steel",
        "theme": "industrial_steel",
        "page_size": "A4",
        "margin_top": 15.0, "margin_bottom": 15.0,
        "margin_left": 20.0, "margin_right": 20.0,
        "header_height": 36.0, "footer_height": 22.0,
        "logo_position": "left",
        "logo_width_mm": 40.0, "logo_height_mm": 18.0,
        "primary_color": "#374151", "secondary_color": "#f3f4f6",
        "accent_color": "#ef4444", "text_color": "#111827",
        "header_bg_color": "#374151", "footer_bg_color": "#e5e7eb",
        "font_family": "Helvetica", "font_size_body": 10.0,
        "header_elements": [],
        "footer_elements": [],
        "applied_to": [],
    },
    {
        "template_name": "Minimal White",
        "theme": "minimal_white",
        "page_size": "A4",
        "margin_top": 15.0, "margin_bottom": 15.0,
        "margin_left": 18.0, "margin_right": 18.0,
        "header_height": 32.0, "footer_height": 20.0,
        "logo_position": "left",
        "logo_width_mm": 38.0, "logo_height_mm": 16.0,
        "primary_color": "#ffffff", "secondary_color": "#f9fafb",
        "accent_color": "#6366f1", "text_color": "#111827",
        "header_bg_color": "#ffffff", "footer_bg_color": "#f9fafb",
        "font_family": "Helvetica", "font_size_body": 10.0,
        "header_elements": [],
        "footer_elements": [],
        "applied_to": [],
    },
    {
        "template_name": "Executive Grey",
        "theme": "executive_grey",
        "page_size": "A4",
        "margin_top": 16.0, "margin_bottom": 16.0,
        "margin_left": 20.0, "margin_right": 20.0,
        "header_height": 36.0, "footer_height": 22.0,
        "logo_position": "left",
        "logo_width_mm": 42.0, "logo_height_mm": 18.0,
        "primary_color": "#4b5563", "secondary_color": "#f3f4f6",
        "accent_color": "#0ea5e9", "text_color": "#111827",
        "header_bg_color": "#4b5563", "footer_bg_color": "#e5e7eb",
        "font_family": "Helvetica", "font_size_body": 10.0,
        "header_elements": [],
        "footer_elements": [],
        "applied_to": [],
    },
]

_DOC_TYPES: list[str] = [
    "quotation", "purchase_order", "purchase_bill", "sales_order",
    "gst_invoice", "delivery_challan", "credit_note", "debit_note",
    "payment_voucher", "receipt_voucher", "journal_voucher",
    "expense_report", "payslip", "bank_statement", "proforma_invoice",
    "work_order", "packing_list", "lr_copy", "e_way_bill", "custom",
]


# ── Helper: save version snapshot ─────────────────────────────────────────────

async def _save_version(tmpl: dict, changed_by: str, note: str) -> None:
    tid = tmpl.get("tenant_id") or "default"
    ver_num = (tmpl.get("version") or 1)
    await crud_create("letterhead_versions", {
        "id": new_id(),
        "tenant_id": tid,
        "template_id": tmpl["id"],
        "version": ver_num,
        "snapshot": tmpl,
        "changed_by": changed_by,
        "change_note": note or "",
        "created_at": now_iso(),
    })


async def _get_company(tid: str) -> dict:
    co = await db.companies.find_one({"tenant_id": tid})
    return co or {}


def _load_logo_bytes(path: Optional[str]) -> Optional[bytes]:
    if not path:
        return None
    try:
        data, _ = get_object(path)
        return data
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# TEMPLATES — CRUD
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/templates")
async def list_templates(
    branch_id: Optional[str] = None,
    include_deleted: bool = False,
    user: dict = Depends(get_current_user),
):
    _req_read(user)
    flt: dict = {"tenant_id": _tid(user)}
    if not include_deleted:
        flt["is_deleted"] = {"$ne": True}
    if branch_id:
        flt["branch_id"] = branch_id
    rows = await crud_list("letterhead_templates", filt=flt, sort_field="created_at", sort_dir=-1)
    return {"items": rows, "total": len(rows)}


@router.get("/templates/{template_id}")
async def get_template(
    template_id: str,
    user: dict = Depends(get_current_user),
):
    _req_read(user)
    tmpl = await crud_get("letterhead_templates", template_id)
    if not tmpl or tmpl.get("is_deleted"):
        raise HTTPException(404, "Template not found")
    if tmpl.get("tenant_id") != _tid(user):
        raise HTTPException(404, "Template not found")
    return tmpl


@router.post("/templates", status_code=201)
async def create_template(
    body: TemplateIn,
    request: Request,
    user: dict = Depends(get_current_user),
):
    _req_manage(user)
    tid = _tid(user)
    now = now_iso()
    uid = user.get("id") or user.get("user_id") or ""

    # If setting as default, clear others
    if body.is_default:
        await db.letterhead_templates.update_many(
            {"tenant_id": tid, "is_default": True},
            {"$set": {"is_default": False, "updated_at": now}},
        )

    template_id = new_id()
    doc = {
        "id": template_id, "tenant_id": tid,
        **body.model_dump(exclude={"change_note"}),
        "version": 1, "is_active": True, "is_deleted": False,
        "created_by": uid, "updated_by": uid,
        "created_at": now, "updated_at": now,
    }
    await crud_create("letterhead_templates", doc)
    await log_audit("CREATE", "letterhead_templates", template_id, user, new_values={"name": body.template_name})
    return doc


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    body: TemplateUpdate,
    request: Request,
    user: dict = Depends(get_current_user),
):
    _req_manage(user)
    tid = _tid(user)
    tmpl = await crud_get("letterhead_templates", template_id)
    if not tmpl or tmpl.get("is_deleted") or tmpl.get("tenant_id") != tid:
        raise HTTPException(404, "Template not found")

    # Save version before overwriting
    note = body.change_note or "Updated via designer"
    await _save_version(tmpl, user.get("id") or "", note)

    now = now_iso()
    uid = user.get("id") or user.get("user_id") or ""

    if body.is_default:
        await db.letterhead_templates.update_many(
            {"tenant_id": tid, "is_default": True, "id": {"$ne": template_id}},
            {"$set": {"is_default": False, "updated_at": now}},
        )

    updates = {k: v for k, v in body.model_dump(exclude={"change_note"}, exclude_unset=True).items()}
    updates["updated_by"] = uid
    updates["updated_at"] = now
    updates["version"] = (tmpl.get("version") or 1) + 1

    updated = await crud_update("letterhead_templates", template_id, updates)
    await log_audit("UPDATE", "letterhead_templates", template_id, user, new_values={"name": tmpl.get("template_name")})
    return updated


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    user: dict = Depends(get_current_user),
):
    _req_manage(user)
    tid = _tid(user)
    tmpl = await crud_get("letterhead_templates", template_id)
    if not tmpl or tmpl.get("tenant_id") != tid:
        raise HTTPException(404, "Template not found")
    if tmpl.get("is_default"):
        raise HTTPException(400, "Cannot delete the default template. Set another template as default first.")

    await crud_update("letterhead_templates", template_id, {
        "is_deleted": True,
        "deleted_at": now_iso(),
        "updated_at": now_iso(),
    })
    await log_audit("DELETE", "letterhead_templates", template_id, user, new_values={"name": tmpl.get("template_name")})


@router.post("/templates/{template_id}/set-default")
async def set_default(
    template_id: str,
    user: dict = Depends(get_current_user),
):
    _req_manage(user)
    tid = _tid(user)
    tmpl = await crud_get("letterhead_templates", template_id)
    if not tmpl or tmpl.get("is_deleted") or tmpl.get("tenant_id") != tid:
        raise HTTPException(404, "Template not found")
    now = now_iso()
    await db.letterhead_templates.update_many(
        {"tenant_id": tid, "is_default": True},
        {"$set": {"is_default": False, "updated_at": now}},
    )
    await crud_update("letterhead_templates", template_id, {"is_default": True, "updated_at": now})
    await log_audit("SET_DEFAULT", "letterhead_templates", template_id, user, new_values={"name": tmpl.get("template_name")})
    return {"ok": True, "default_id": template_id}


@router.post("/templates/{template_id}/clone", status_code=201)
async def clone_template(
    template_id: str,
    user: dict = Depends(get_current_user),
):
    _req_manage(user)
    tid = _tid(user)
    src = await crud_get("letterhead_templates", template_id)
    if not src or src.get("is_deleted") or src.get("tenant_id") != tid:
        raise HTTPException(404, "Template not found")

    now = now_iso()
    uid = user.get("id") or ""
    clone_id = new_id()
    clone = {**src}
    clone["id"] = clone_id
    clone["template_name"] = f'{src["template_name"]} (Copy)'
    clone["is_default"] = False
    clone["version"] = 1
    clone["created_by"] = uid
    clone["updated_by"] = uid
    clone["created_at"] = now
    clone["updated_at"] = now
    clone["is_deleted"] = False
    clone["deleted_at"] = None

    await crud_create("letterhead_templates", clone)
    await log_audit("CLONE", "letterhead_templates", clone_id, user, new_values={"source_id": template_id})
    return clone


@router.patch("/templates/{template_id}/status")
async def toggle_status(
    template_id: str,
    body: StatusPatch,
    user: dict = Depends(get_current_user),
):
    _req_manage(user)
    tid = _tid(user)
    tmpl = await crud_get("letterhead_templates", template_id)
    if not tmpl or tmpl.get("is_deleted") or tmpl.get("tenant_id") != tid:
        raise HTTPException(404, "Template not found")
    updated = await crud_update("letterhead_templates", template_id, {
        "is_active": body.is_active, "updated_at": now_iso()
    })
    return updated


@router.patch("/templates/{template_id}/apply-to")
async def update_apply_to(
    template_id: str,
    body: ApplyToUpdate,
    user: dict = Depends(get_current_user),
):
    _req_read(user)
    tid = _tid(user)
    tmpl = await crud_get("letterhead_templates", template_id)
    if not tmpl or tmpl.get("is_deleted") or tmpl.get("tenant_id") != tid:
        raise HTTPException(404, "Template not found")
    bad = [d for d in body.applied_to if d not in _DOC_TYPES]
    if bad:
        raise HTTPException(400, f"Unknown document types: {bad}")
    updated = await crud_update("letterhead_templates", template_id, {
        "applied_to": body.applied_to, "updated_at": now_iso()
    })
    await log_audit("APPLY_TO", "letterhead_templates", template_id, user, new_values={"applied_to": body.applied_to})
    return updated


# ══════════════════════════════════════════════════════════════════════════════
# VERSION HISTORY
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/templates/{template_id}/versions")
async def list_versions(
    template_id: str,
    user: dict = Depends(get_current_user),
):
    _req_read(user)
    rows = await crud_list(
        "letterhead_versions",
        filt={"template_id": template_id},
        sort_field="version",
        sort_dir=-1,
    )
    return {"items": rows, "total": len(rows)}


@router.post("/templates/{template_id}/versions/{version_id}/restore")
async def restore_version(
    template_id: str,
    version_id: str,
    body: RestoreVersionIn,
    user: dict = Depends(get_current_user),
):
    _req_manage(user)
    tid = _tid(user)
    tmpl = await crud_get("letterhead_templates", template_id)
    if not tmpl or tmpl.get("tenant_id") != tid:
        raise HTTPException(404, "Template not found")
    ver = await crud_get("letterhead_versions", version_id)
    if not ver or ver.get("template_id") != template_id:
        raise HTTPException(404, "Version not found")

    # Save current state as a version before restoring
    await _save_version(tmpl, user.get("id") or "", "Auto-saved before restore")

    snapshot: dict = ver.get("snapshot") or {}
    preserve = {"id", "tenant_id", "version", "created_by", "created_at", "is_deleted", "deleted_at"}
    updates = {k: v for k, v in snapshot.items() if k not in preserve}
    updates["updated_at"] = now_iso()
    updates["updated_by"] = user.get("id") or ""
    updates["version"] = (tmpl.get("version") or 1) + 1

    restored = await crud_update("letterhead_templates", template_id, updates)
    await log_audit("RESTORE", "letterhead_templates", template_id, user, new_values={
        "version_id": version_id, "note": body.change_note
    })
    return restored


# ══════════════════════════════════════════════════════════════════════════════
# FILE UPLOADS — logo, logo2, background
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/templates/{template_id}/upload-logo")
async def upload_logo(
    template_id: str,
    file: UploadFile = File(...),
    slot: str = "primary",
    user: dict = Depends(get_current_user),
):
    _req_manage(user)
    tid = _tid(user)
    tmpl = await crud_get("letterhead_templates", template_id)
    if not tmpl or tmpl.get("is_deleted") or tmpl.get("tenant_id") != tid:
        raise HTTPException(404, "Template not found")
    if file.content_type not in ("image/png", "image/jpeg", "image/svg+xml", "image/webp"):
        raise HTTPException(400, "Only PNG, JPEG, SVG, WEBP allowed")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Logo file must be < 5 MB")
    ext = (file.filename or "").rsplit(".", 1)[-1] if "." in (file.filename or "") else "png"
    key = f"letterhead/{tid}/{template_id}/logo_{slot}.{ext}"
    result = put_object(key, data, file.content_type or "image/png")
    stored_path = result["path"]
    field = "logo_url" if slot == "primary" else "logo2_url"
    await crud_update("letterhead_templates", template_id, {field: stored_path, "updated_at": now_iso()})
    return {"url": stored_path, "slot": slot}


@router.post("/templates/{template_id}/upload-background")
async def upload_background(
    template_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    _req_manage(user)
    tid = _tid(user)
    tmpl = await crud_get("letterhead_templates", template_id)
    if not tmpl or tmpl.get("is_deleted") or tmpl.get("tenant_id") != tid:
        raise HTTPException(404, "Template not found")
    if file.content_type not in ("image/png", "image/jpeg"):
        raise HTTPException(400, "Only PNG or JPEG allowed for background")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "Background image must be < 10 MB")
    ext = (file.filename or "").rsplit(".", 1)[-1] if "." in (file.filename or "") else "jpg"
    key = f"letterhead/{tid}/{template_id}/bg.{ext}"
    result = put_object(key, data, file.content_type or "image/jpeg")
    stored_path = result["path"]
    await crud_update("letterhead_templates", template_id, {
        "background_image": stored_path, "updated_at": now_iso()
    })
    return {"url": stored_path}


# ══════════════════════════════════════════════════════════════════════════════
# PDF PREVIEW
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/templates/{template_id}/preview.pdf")
async def preview_pdf(
    template_id: str,
    user: dict = Depends(get_current_user),
):
    _req_read(user)
    tid = _tid(user)
    tmpl = await crud_get("letterhead_templates", template_id)
    if not tmpl or tmpl.get("is_deleted") or tmpl.get("tenant_id") != tid:
        raise HTTPException(404, "Template not found")

    company = await _get_company(tid)
    logo_bytes = _load_logo_bytes(tmpl.get("logo_url"))
    logo2_bytes = _load_logo_bytes(tmpl.get("logo2_url"))

    pdf_bytes = build_preview_pdf(
        template=tmpl,
        company=company,
        logo_bytes=logo_bytes,
        logo2_bytes=logo2_bytes,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="letterhead_preview.pdf"'},
    )


# ══════════════════════════════════════════════════════════════════════════════
# FILE SERVE — logos and backgrounds stored under letterhead/
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/files/{path:path}")
async def serve_file(path: str, user: dict = Depends(get_current_user)):
    """Serve an uploaded letterhead asset (logo, background) by its storage path."""
    _req_read(user)
    try:
        data, content_type = get_object(path)
    except FileNotFoundError:
        raise HTTPException(404, "File not found")
    return Response(content=data, media_type=content_type,
                    headers={"Cache-Control": "public, max-age=3600"})


# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENT TYPES LIST
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/document-types")
async def list_document_types(user: dict = Depends(get_current_user)):
    _req_read(user)
    return {"items": _DOC_TYPES}


@router.get("/document-types/{doc_type}/template")
async def get_template_for_doc(
    doc_type: str,
    branch_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Return the active template assigned to a given document type."""
    _req_read(user)
    tid = _tid(user)
    flt: dict = {
        "tenant_id": tid,
        "is_deleted": {"$ne": True},
        "is_active": True,
        "applied_to": {"$elemMatch": {"$eq": doc_type}},
    }
    if branch_id:
        flt["branch_id"] = branch_id
    rows = await crud_list("letterhead_templates", filt=flt, sort_field="is_default", sort_dir=-1)
    if rows:
        return rows[0]
    # Fall back to default template
    def_row = await db.letterhead_templates.find_one({
        "tenant_id": tid, "is_default": True, "is_deleted": {"$ne": True}
    })
    if def_row:
        return def_row
    raise HTTPException(404, f"No template found for document type '{doc_type}'")


# ══════════════════════════════════════════════════════════════════════════════
# SEED 6 PREMIUM THEMES
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/seed-defaults", status_code=201)
async def seed_defaults(user: dict = Depends(get_current_user)):
    _req_manage(user)
    tid = _tid(user)
    uid = user.get("id") or user.get("user_id") or ""
    now = now_iso()
    created: list[str] = []
    skipped: list[str] = []

    for tmpl_def in _PREMIUM_TEMPLATES:
        existing = await db.letterhead_templates.find_one({
            "tenant_id": tid,
            "template_name": tmpl_def["template_name"],
            "is_deleted": {"$ne": True},
        })
        if existing:
            skipped.append(tmpl_def["template_name"])
            continue
        doc = {
            "id": new_id(),
            "tenant_id": tid,
            "branch_id": None,
            **tmpl_def,
            "watermark_text": None,
            "watermark_opacity": 0.08,
            "watermark_angle": -45.0,
            "watermark_font_size": 60.0,
            "watermark_color": "#888888",
            "background_image": None,
            "logo_url": None, "logo2_url": None,
            "is_default": False,
            "is_active": True,
            "version": 1,
            "created_by": uid, "updated_by": uid,
            "is_deleted": False, "deleted_at": None,
            "created_at": now, "updated_at": now,
        }
        await crud_create("letterhead_templates", doc)
        created.append(tmpl_def["template_name"])

    await log_audit("SEED", "letterhead_templates", "bulk", user, new_values={
        "created": created, "skipped": skipped
    })
    return {
        "created": created,
        "skipped": skipped,
        "message": f"{len(created)} template(s) seeded, {len(skipped)} already existed.",
    }


# ══════════════════════════════════════════════════════════════════════════════
# THEME PRESETS (read-only reference)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/theme-presets")
async def get_theme_presets(user: dict = Depends(get_current_user)):
    _req_read(user)
    items = [{"key": k, "label": k.replace("_", " ").title(), **v} for k, v in THEME_PRESETS.items()]
    return {"items": items}
