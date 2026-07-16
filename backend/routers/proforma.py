from typing import Optional

from fastapi import APIRouter, Depends, Response

from core.auth_utils import require_admin
from core.models import ProformaInvoice
from core.pi_pdf import build_pi_pdf
from core.utils import (
    crud_create,
    crud_delete,
    crud_get,
    crud_list,
    crud_update,
    get_active_company,
    next_doc_number,
)

router = APIRouter(tags=["proforma"])


def _compute_totals(items):
    total_qty = 0.0
    total_weight = 0.0
    total_amount = 0.0
    for it in items:
        q = float(it.get("quantity", 0) or 0)
        w = float(it.get("weight_per_unit", 0) or 0)
        u = float(it.get("unit_price", 0) or 0)
        total_qty += q
        total_weight += q * w
        total_amount += q * u
    return {
        "total_quantity": round(total_qty, 2),
        "total_net_weight": round(total_weight, 2),
        "total_amount": round(total_amount, 2),
    }


@router.get("/proforma-invoices")
async def list_pis(q: Optional[str] = None, _: dict = Depends(require_admin)):
    return await crud_list("proforma_invoices", q, ["pi_number", "buyer_name", "status", "buyer_country"])


@router.post("/proforma-invoices")
async def create_pi(payload: ProformaInvoice, _: dict = Depends(require_admin)):
    data = payload.model_dump()
    if not data.get("pi_number"):
        data["pi_number"] = await next_doc_number("PI", "proforma_invoices")
    data.update(_compute_totals(data["items"]))
    return await crud_create("proforma_invoices", data)


@router.put("/proforma-invoices/{item_id}")
async def update_pi(item_id: str, payload: ProformaInvoice, _: dict = Depends(require_admin)):
    data = payload.model_dump()
    data.update(_compute_totals(data["items"]))
    return await crud_update("proforma_invoices", item_id, data)


@router.get("/proforma-invoices/{item_id}")
async def get_pi(item_id: str, _: dict = Depends(require_admin)):
    return await crud_get("proforma_invoices", item_id)


@router.delete("/proforma-invoices/{item_id}")
async def delete_pi(item_id: str, _: dict = Depends(require_admin)):
    return await crud_delete("proforma_invoices", item_id)


@router.get("/proforma-invoices/{item_id}/pdf")
async def pi_pdf(item_id: str, _: dict = Depends(require_admin)):
    pi = await crud_get("proforma_invoices", item_id)
    pdf_bytes = build_pi_pdf(pi, company=await get_active_company())
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{pi.get("pi_number", item_id)}.pdf"'},
    )
