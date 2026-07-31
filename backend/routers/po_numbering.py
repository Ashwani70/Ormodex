"""Admin → Document Settings → Purchase Order Numbering.

GET/POST /settings/po-numbering manage the numbering template; a small
/preview helper lets the UI show the next number without reserving it.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from core.auth_utils import get_current_user, require_admin
from core import po_numbering as pn
from core.tenant import tenant_ctx

router = APIRouter(prefix="/settings/po-numbering", tags=["PO Numbering"])


class PONumberingSettings(BaseModel):
    mode: Literal["AUTO", "MANUAL"] = "AUTO"
    prefix: str = "PO"
    fy_format: str = ""
    branch_code: str = ""
    separator: str = "-"
    start_sequence: int = 1
    sequence_length: int = 5

    @field_validator("separator")
    @classmethod
    def _sep(cls, v: str) -> str:
        return v if v in pn.VALID_SEPARATORS else "-"


@router.get("")
async def read_settings(user: dict = Depends(get_current_user), tenant: str = Depends(tenant_ctx)):
    """Read the active numbering settings. Available to any authenticated user so
    the PO create screen can prefill / decide whether the number field is editable."""
    settings = await pn.get_settings(tenant)
    return {**settings, "can_override": pn.has_perm(user, pn.PERM_OVERRIDE),
            "can_edit": pn.has_perm(user, pn.PERM_EDIT)}


@router.post("")
async def write_settings(payload: PONumberingSettings, user: dict = Depends(require_admin),
                          tenant: str = Depends(tenant_ctx)):
    """Save numbering settings (admin only)."""
    return await pn.save_settings(payload.model_dump(), user=user, tenant_id=tenant)


@router.get("/preview")
async def preview_number(user: dict = Depends(get_current_user),
                         tenant: str = Depends(tenant_ctx),
                         seq: Optional[int] = None):
    """Show what the next auto-generated number would look like — without
    reserving a sequence value."""
    settings = await pn.get_settings(tenant)
    sample_seq = seq if seq is not None else settings["start_sequence"]
    return {"mode": settings["mode"], "preview": pn.build_po_number(settings, sample_seq)}
