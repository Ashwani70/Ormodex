"""Admin → Document Settings → Document Numbering (generalized).

GET /settings/document-numbering/types lists the configurable document types
(for the frontend's type selector); GET/POST /{doc_type} manage each type's
numbering template; GET /{doc_type}/preview shows the next number without
reserving it. Purchase Order is included in the type list but reads/writes
through its own pre-existing table — see core/document_numbering.py's
module docstring — so routers/po_numbering.py's endpoints keep working
unchanged for any caller still using them directly (PurchaseOrdersV2.jsx).
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from core.auth_utils import get_current_user, require_admin
from core import document_numbering as dn
from core.tenant import tenant_ctx

router = APIRouter(prefix="/settings/document-numbering", tags=["Document Numbering"])


class DocumentNumberingSettings(BaseModel):
    mode: Literal["AUTO", "MANUAL"] = "AUTO"
    prefix: str = ""
    fy_format: str = ""
    branch_code: str = ""
    separator: str = "-"
    start_sequence: int = 1
    sequence_length: int = 5

    @field_validator("separator")
    @classmethod
    def _sep(cls, v: str) -> str:
        return v if v in dn.VALID_SEPARATORS else "-"


@router.get("/types")
async def list_document_types(_: dict = Depends(get_current_user)):
    """Registry of configurable document types, for the settings page's type selector."""
    return [{"doc_type": k, "label": v["label"]} for k, v in dn.DOC_TYPES.items()]


@router.get("/{doc_type}")
async def read_settings(doc_type: str, user: dict = Depends(get_current_user),
                        tenant: str = Depends(tenant_ctx)):
    """Read the active numbering settings for one document type. Available to
    any authenticated user so a document's create screen can prefill / decide
    whether the number field is editable."""
    settings = await dn.get_settings(doc_type, tenant)
    return {**settings,
            "can_override": dn.has_perm(user, doc_type, "override"),
            "can_edit": dn.has_perm(user, doc_type, "edit")}


@router.post("/{doc_type}")
async def write_settings(doc_type: str, payload: DocumentNumberingSettings, user: dict = Depends(require_admin),
                         tenant: str = Depends(tenant_ctx)):
    """Save numbering settings for one document type (admin only)."""
    return await dn.save_settings(doc_type, payload.model_dump(), user=user, tenant_id=tenant)


@router.get("/{doc_type}/preview")
async def preview_number(doc_type: str, user: dict = Depends(get_current_user),
                         tenant: str = Depends(tenant_ctx), seq: Optional[int] = None):
    """Show what the next auto-generated number would look like — without
    reserving a sequence value."""
    settings = await dn.get_settings(doc_type, tenant)
    sample_seq = seq if seq is not None else settings["start_sequence"]
    return {"mode": settings["mode"], "preview": dn.build_document_number(settings, sample_seq)}
