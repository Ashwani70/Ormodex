"""Job Work router — two strictly-separated vouchers.

Covers:
- Job Work Challan (Outward): materials sent to a job worker, no GST charged.
- Job Work Receipt (Inward): materials returned, partial/rejected/scrap split.
- Return-window tracking (Rule 45: 1 yr inputs / 3 yrs capital goods).
- Deemed-supply flagging for overdue challans.
- ITC-04 period statement (GSTR-ITC-04).
- Pending / Completed / Overdue material reports.

Storage: real child tables (job_work_challan_items, job_work_receipt_items),
not JSONB arrays — a receipt line references its exact challan_item_id, so
matching is a join on a real foreign key rather than product-name string
matching. See alembic/versions/016_job_work_normalize.py.

Challan and Receipt are read/written through entirely separate code paths.
Nothing here ever unions or mixes the two into one query result.
"""
import inspect
import io
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from typing import Optional
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, delete as sa_delete

from core.auth_utils import get_current_user, is_admin_role
from core.db import db, get_session
from core.models import JobWorkChallan, JobWorkReceipt
from core.pdf import build_jobwork_receipt_pdf, build_jobwork_report_pdf
from core.product_stock_bridge import resolve_godown_id, resolve_stock_item_ids_for_products
from core.schema import (
    JobWorkChallan as JobWorkChallanRow,
    JobWorkChallanItem,
    JobWorkReceipt as JobWorkReceiptRow,
    JobWorkReceiptItem,
)
from core.stock_ledger import post_entry
from core.tracking_validation import validate_tracking_fields
from core.utils import now_iso, new_id, next_doc_number, get_active_company, log_audit, render_document_pdf

log = logging.getLogger("job_work")
router = APIRouter(prefix="/job-work", tags=["Job Work"])

_OPEN_STATUSES = ("DRAFT", "PENDING", "PARTIAL")
_CLOSED_STATUSES = ("COMPLETED", "CANCELLED")


def _normalize_status(status: str | None) -> str:
    """Normalize status strings from legacy Mongo data (lowercase/None → PENDING)."""
    if not status:
        return "PENDING"
    return status.upper()


def _require_job_work(user: dict):
    if (is_admin_role(user.get("role")) or user.get("role") == "accountant"):
        return user
    perms = user.get("module_permissions", [])
    if "inventory" not in perms and "sales" not in perms and "manufacturing" not in perms:
        raise HTTPException(403, "Job work module access required")
    return user


def _row_dict(row) -> dict:
    """Flatten a SQLAlchemy ORM row into a plain dict of its mapped columns."""
    return {c.key: getattr(row, c.key) for c in row.__table__.columns}


def _resolve_accepted_quantity(item: dict) -> None:
    """Fill item["accepted_quantity"] in place when the caller didn't send it
    (defaults to received - rejected - scrap), and raise 400 if the three
    together exceed the received quantity. Shared by create/update receipt so
    the rule can't drift between the two endpoints."""
    if item.get("accepted_quantity") is None:
        item["accepted_quantity"] = max(
            0.0,
            float(item["quantity_received"])
            - float(item.get("rejected_quantity", 0) or 0)
            - float(item.get("scrap_quantity", 0) or 0),
        )
    total = (
        float(item["accepted_quantity"])
        + float(item.get("rejected_quantity", 0) or 0)
        + float(item.get("scrap_quantity", 0) or 0)
    )
    if total > float(item["quantity_received"]) + 1e-5:
        raise HTTPException(
            400,
            f"Accepted + rejected + scrap ({total}) exceeds received quantity "
            f"({item['quantity_received']}) for '{item['product_name']}'.",
        )


def _enrich_item_valuation(item: dict, prod: dict | None) -> None:
    """Fill rate / taxable_value / hsn / gst on a challan line in place.

    rate defaults to the product cost price when not supplied; taxable_value is
    always recomputed as rate * quantity so the two can't drift. hsn_code and
    gst_rate are pulled from the product when the line doesn't already carry
    them (a custom line keeps whatever the user typed). No GST is charged on
    the challan — these are tracked for ITC-04 only.
    """
    qty = float(item.get("quantity", 0) or 0)
    prod = prod or {}
    rate = item.get("rate")
    if rate in (None, ""):
        rate = float(prod.get("cost_price", 0) or 0)
    rate = float(rate or 0)
    item["rate"] = round(rate, 2)
    item["amount"] = round(rate * qty, 2)
    item["taxable_value"] = round(rate * qty, 2)
    if not item.get("hsn_code") and prod.get("hsn_code"):
        item["hsn_code"] = prod.get("hsn_code")
    if item.get("gst_rate") in (None, "") and prod.get("gst_rate") is not None:
        item["gst_rate"] = float(prod.get("gst_rate") or 0)


async def _fetch_products_by_ids(items: list[dict]) -> dict[str, dict]:
    """Batch-read every catalog product referenced by `items` in ONE query
    instead of a find_one per line item — every challan/receipt handler in
    this file loops over its items 1-3 times (enrich, stock-move, reverse),
    each previously re-querying the product per line. Custom (free-text)
    lines have no product_id and are skipped. Callers still loop
    sequentially over the returned dict for any writes — this app binds one
    shared AsyncSession per request, so the writes themselves can't be
    asyncio.gather'd (see the shared-session note in purchase.py)."""
    product_ids = list({item["product_id"] for item in items if item.get("product_id") and not item.get("is_custom")})
    if not product_ids:
        return {}
    prods = await db.products.find({"id": {"$in": product_ids}}).to_list(len(product_ids))
    return {p["id"]: p for p in prods}


async def _post_job_work_movements(
    items: list[dict], user: dict, *, sign: int, movement_type: str,
    qty_field: str, source_doc_type: str, source_doc_id: str | None,
    best_effort: bool = False,
) -> list[str]:
    """Post one signed stock_ledger_entries movement per catalog line item,
    replacing the old direct products.quantity + stock_transactions writes —
    every Job Work movement (issue, edit-reversal, receipt, receipt-reversal)
    now gets real FIFO/LIFO/WA/Standard-Cost valuation via post_entry instead
    of a flat quantity delta. Custom (free-text) lines have no product_id and
    never moved stock, so they're skipped exactly as before.

    sign: +1 for an inward movement (receipt, edit-reversal of an issue),
    -1 for outward (issue, reversal of a receipt) — applied to qty_field.
    No godown is captured on a Job Work line today, so this resolves the
    tenant's default the same way manual adjustment/opening stock/physical
    verification do (core.product_stock_bridge.resolve_godown_id).

    best_effort: when True (reversal call sites only — delete/cancel), a line
    whose product has since been deleted from the catalog is SKIPPED with a
    warning instead of raising and aborting every other line's reversal.
    Creating a NEW movement must still fail loud on a missing product
    (best_effort stays False there) — this only relaxes the already-posted
    case, where the product's continued existence was never actually a
    precondition for reversing a movement it made in the past. Returns the
    product_ids of any skipped lines so the caller can surface them.
    """
    godown_id = await resolve_godown_id(None)
    product_ids = [item["product_id"] for item in items if not item.get("is_custom") and item.get("product_id")]
    skipped: list[str] = []
    if best_effort:
        stock_item_by_product: dict[str, str] = {}
        for pid in dict.fromkeys(product_ids):
            try:
                stock_item_by_product.update(await resolve_stock_item_ids_for_products([pid], user))
            except HTTPException:
                log.warning(
                    "job_work: skipping stock reversal for deleted product %s (source=%s/%s)",
                    pid, source_doc_type, source_doc_id,
                )
                skipped.append(pid)
    else:
        stock_item_by_product = await resolve_stock_item_ids_for_products(product_ids, user)
    for item in items:
        if item.get("is_custom") or not item.get("product_id"):
            continue
        if item["product_id"] not in stock_item_by_product:
            continue  # only reachable via best_effort's skip list above
        qty = float(item.get(qty_field, 0) or 0)
        if not qty:
            continue
        stock_item_id = stock_item_by_product[item["product_id"]]
        signed_qty = sign * abs(qty)
        rate = float(item.get("rate") or 0) if signed_qty > 0 else None
        await post_entry(
            stock_item_id=stock_item_id, godown_id=godown_id,
            qty=signed_qty, movement_type=movement_type, rate=rate,
            source_doc_type=source_doc_type, source_doc_id=source_doc_id,
            user=user,
        )
    return skipped


# ── GST computation (reference only — no tax charged on a §143 challan) ───────

async def _resolve_state_codes(challan: dict) -> tuple[str, str]:
    """Return (company_state_code, job_worker_state_code)."""
    company = await db.companies.find_one({})
    company_state = (company.get("state_code") if company else None) or "27"

    gstin = (challan.get("job_worker_gstin") or "").strip()
    if len(gstin) >= 2 and gstin[:2].isdigit():
        return company_state, gstin[:2]

    jw_id = challan.get("job_worker_id")
    if jw_id:
        party = await db.vendors.find_one({"id": jw_id}) or await db.customers.find_one({"id": jw_id})
        if party:
            code = party.get("state_code")
            pg = (party.get("gstin") or "").strip()
            if not code and len(pg) >= 2 and pg[:2].isdigit():
                code = pg[:2]
            if code:
                return company_state, str(code)
    return company_state, company_state


async def _resolve_inter_state(challan: dict) -> bool:
    """A manual gst_type of intra/inter wins outright; "auto" compares state codes."""
    gst_type = (challan.get("gst_type") or "auto").lower()
    if gst_type == "inter":
        return True
    if gst_type == "intra":
        return False
    company_state, jw_state = await _resolve_state_codes(challan)
    return jw_state != company_state


def _compute_line_gst(item: dict, inter_state: bool) -> None:
    """Compute one line's CGST/SGST/IGST + line_total in place."""
    taxable = float(item.get("taxable_value", 0) or 0)
    rate = float(item.get("gst_rate", 0) or 0)
    gst_amt = round(taxable * rate / 100.0, 2)
    cgst = sgst = igst = 0.0
    if inter_state:
        igst = gst_amt
    else:
        cgst = round(gst_amt / 2.0, 2)
        sgst = round(gst_amt - cgst, 2)  # absorb rounding into sgst
    item["cgst"] = cgst
    item["sgst"] = sgst
    item["igst"] = igst
    item["line_total"] = round(taxable + cgst + sgst + igst, 2)


def _challan_totals(items: list[dict]) -> dict:
    total_taxable = sum(float(i.get("taxable_value", 0) or 0) for i in items)
    total_cgst = sum(float(i.get("cgst", 0) or 0) for i in items)
    total_sgst = sum(float(i.get("sgst", 0) or 0) for i in items)
    total_igst = sum(float(i.get("igst", 0) or 0) for i in items)
    total_gst = total_cgst + total_sgst + total_igst
    return {
        "total_taxable_value": round(total_taxable, 2),
        "total_cgst": round(total_cgst, 2),
        "total_sgst": round(total_sgst, 2),
        "total_igst": round(total_igst, 2),
        "total_gst": round(total_gst, 2),
        "grand_total": round(total_taxable + total_gst, 2),
    }


# ── Return-window helper ──────────────────────────────────────────────────────

async def _get_return_window_days(nature: str = "inputs") -> int:
    """Statutory return window (Rule 45, CGST Rules 2017), overridable via rate_tables."""
    key = "job_work_return_window_capital" if nature == "capital_goods" else "job_work_return_window_inputs"
    rate = await db.rate_tables.find_one({"key": key}, {"_id": 0})
    if rate and rate.get("value"):
        return int(rate["value"])
    return 1095 if nature == "capital_goods" else 365


def _due_date(challan_date: str, window_days: int) -> str:
    try:
        dt = datetime.fromisoformat(challan_date)
    except ValueError:
        dt = datetime.now(timezone.utc)
    due = dt + timedelta(days=window_days)
    return due.date().isoformat()


def _is_overdue(due_date: str) -> bool:
    """True if due_date (ISO date string) is strictly before today (UTC)."""
    today = datetime.now(timezone.utc).date().isoformat()
    return bool(due_date and due_date < today)


# ══════════════════════════════════════════════════════════════
# Shared item-table helpers
# ══════════════════════════════════════════════════════════════

async def _insert_challan_items(session, challan_id: str, tenant_id: str | None, items: list[dict]) -> list[dict]:
    """Bulk-insert child rows for a challan's line items; returns the rows
    (with generated ids) as plain dicts so the caller can use them immediately
    (e.g. for PDF rendering) without a round-trip re-read."""
    now = now_iso()
    out = []
    for idx, item in enumerate(items):
        row_id = new_id()
        row = JobWorkChallanItem(
            id=row_id, challan_id=challan_id, tenant_id=tenant_id, line_no=idx,
            product_id=item.get("product_id"), product_name=item.get("product_name"),
            sku=item.get("sku"), description=item.get("description"),
            hsn_code=item.get("hsn_code"), uom=item.get("unit") or item.get("uom") or "pcs",
            is_custom=bool(item.get("is_custom")),
            quantity=item.get("quantity"), rate=item.get("rate"), amount=item.get("amount"),
            gst_rate=item.get("gst_rate"), taxable_value=item.get("taxable_value"),
            cgst=item.get("cgst", 0), sgst=item.get("sgst", 0), igst=item.get("igst", 0),
            line_total=item.get("line_total"),
            batch_id=item.get("batch_id"), serial_id=item.get("serial_id"),
            expiry_date=item.get("expiry_date"), remarks=item.get("remarks"),
            created_at=now, updated_at=now,
        )
        session.add(row)
        out.append({**item, "id": row_id, "line_no": idx})
    return out


async def _fetch_challan_items(challan_id: str) -> list[dict]:
    try:
        async with get_session() as session:
            result = await session.execute(
                select(JobWorkChallanItem).where(JobWorkChallanItem.challan_id == challan_id).order_by(JobWorkChallanItem.line_no)
            )
            rows = [_row_dict(r) for r in result.scalars().all()]
            if rows:
                return rows
    except Exception:
        pass
    if hasattr(db, "job_work_challan_items"):
        cursor = db.job_work_challan_items.find({"challan_id": challan_id})
        if hasattr(cursor, "to_list"):
            res = cursor.to_list(1000)
            items = (await res) if inspect.isawaitable(res) else (res or [])
            return items if isinstance(items, list) else []
    return []


async def _fetch_challan_items_for_ids(challan_ids: list[str]) -> dict[str, list[dict]]:
    if not challan_ids:
        return {}
    try:
        async with get_session() as session:
            result = await session.execute(
                select(JobWorkChallanItem).where(JobWorkChallanItem.challan_id.in_(challan_ids)).order_by(JobWorkChallanItem.line_no)
            )
            by_challan: dict[str, list[dict]] = {}
            for r in result.scalars().all():
                by_challan.setdefault(r.challan_id, []).append(_row_dict(r))
            if by_challan:
                return by_challan
    except Exception:
        pass
    if hasattr(db, "job_work_challan_items"):
        cursor = db.job_work_challan_items.find({"challan_id": {"$in": challan_ids}})
        if hasattr(cursor, "to_list"):
            res = cursor.to_list(1000)
            items = (await res) if inspect.isawaitable(res) else (res or [])
        else:
            items = []
        by_challan = {}
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and "challan_id" in it:
                    by_challan.setdefault(it["challan_id"], []).append(it)
        return by_challan
    return {}


async def _received_by_challan_item(challan_ids: list[str]) -> dict[str, float]:
    """Sum quantity_received per challan_item_id across every logged receipt
    for the given challans. Returns {challan_item_id: total_received}."""
    if not challan_ids:
        return {}
    async with get_session() as session:
        challan_item_ids_result = await session.execute(
            select(JobWorkChallanItem.id).where(JobWorkChallanItem.challan_id.in_(challan_ids))
        )
        item_ids = [r[0] for r in challan_item_ids_result.all()]
        if not item_ids:
            return {}
        result = await session.execute(
            select(JobWorkReceiptItem.challan_item_id, JobWorkReceiptItem.quantity_received)
            .where(JobWorkReceiptItem.challan_item_id.in_(item_ids))
        )
        received: dict[str, float] = {}
        for challan_item_id, qty in result.all():
            if challan_item_id is None:
                continue
            received[challan_item_id] = received.get(challan_item_id, 0.0) + float(qty or 0)
        return received


# ══════════════════════════════════════════════════════════════
# Challans (Outward)
# ══════════════════════════════════════════════════════════════

async def _fetch_enriched_challans(q: Optional[str], overdue_only: bool, status: Optional[str] = None) -> list[dict]:
    """Query job_work_challans headers, join in their line items from
    job_work_challan_items, and enrich with received/pending qty per line by
    summing job_work_receipt_items. Never touches job_work_receipts headers."""
    filt: dict = {}
    if q:
        filt["$or"] = [
            {"challan_number": {"$regex": q, "$options": "i"}},
            {"job_worker_name": {"$regex": q, "$options": "i"}},
        ]
    if status:
        filt["status"] = status
    if overdue_only:
        filt["is_overdue"] = True
        filt["status"] = {"$nin": list(_CLOSED_STATUSES) + [s.lower() for s in _CLOSED_STATUSES]}

    challans = await db.job_work_challans.find(filt, {"_id": 0}).sort("date", -1).to_list(1000)
    challan_ids = [c["id"] for c in challans]

    items_by_challan = await _fetch_challan_items_for_ids(challan_ids)
    received_by_item = await _received_by_challan_item(challan_ids)

    today = datetime.now(timezone.utc).date().isoformat()
    for c in challans:
        c["status"] = _normalize_status(c.get("status"))
        c.setdefault("challan_number", None)
        c.setdefault("date", None)
        c.setdefault("due_date", None)
        c.setdefault("job_worker_name", None)
        c.setdefault("nature", "inputs")
        c.setdefault("gst_type", "auto")
        c.setdefault("vehicle_no", None)
        c.setdefault("transport", None)

        items = items_by_challan.get(c["id"], [])
        for item in items:
            sent = float(item.get("quantity", 0) or 0)
            recv = received_by_item.get(item["id"], 0.0)
            item["quantity_received"] = recv
            item["quantity_pending"] = max(0.0, sent - recv)
        c["items"] = items

        if c.get("due_date") and c["status"] not in _CLOSED_STATUSES:
            c["is_overdue"] = c["due_date"] < today
            c["deemed_supply"] = c["is_overdue"]
        else:
            c["is_overdue"] = False
            c["deemed_supply"] = False

    return challans


@router.get("/challans")
async def list_challans(
    q: Optional[str] = None,
    overdue_only: bool = False,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    user: dict = Depends(get_current_user),
):
    _require_job_work(user)
    challans = await _fetch_enriched_challans(q, overdue_only, status)
    total = len(challans)
    start = (page - 1) * limit
    items = challans[start: start + limit]
    return {"total": total, "page": page, "limit": limit, "items": items}


@router.get("/challans/export")
async def export_challans(
    q: Optional[str] = None,
    overdue_only: bool = False,
    user: dict = Depends(get_current_user),
):
    """Download all matching challan line items as an .xlsx workbook (one row per line item)."""
    _require_job_work(user)
    from openpyxl import Workbook

    challans = await _fetch_enriched_challans(q, overdue_only)

    wb = Workbook()
    ws = wb.active
    if ws is None:
        raise HTTPException(500, "Could not create workbook sheet")
    ws.title = "Challans Sent"
    headers = ["Challan No", "Challan Date", "Due Date", "Job Worker", "Item Name", "Item Code",
               "UOM", "Sent Qty", "Received Qty", "Pending Qty", "Status", "Taxable Value", "Overdue"]
    ws.append(headers)
    for c in challans:
        for item in c.get("items", []):
            ws.append([
                c.get("challan_number", ""),
                c.get("date", ""),
                c.get("due_date", ""),
                c.get("job_worker_name", ""),
                item.get("product_name", ""),
                item.get("sku", ""),
                item.get("uom", "pcs"),
                float(item.get("quantity", 0) or 0),
                float(item.get("quantity_received", 0) or 0),
                float(item.get("quantity_pending", 0) or 0),
                c.get("status", ""),
                float(item.get("taxable_value", 0) or 0),
                "Yes" if c.get("is_overdue") else "No",
            ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="job-work-challans.xlsx"'},
    )


@router.get("/challans/{item_id}")
async def get_challan(item_id: str, user: dict = Depends(get_current_user)):
    _require_job_work(user)
    c = await db.job_work_challans.find_one({"id": item_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Challan not found")
    c["status"] = _normalize_status(c.get("status"))
    c.setdefault("challan_number", None)
    c.setdefault("date", None)
    c.setdefault("due_date", None)
    c.setdefault("job_worker_name", None)
    c.setdefault("nature", "inputs")
    c.setdefault("gst_type", "auto")
    c.setdefault("vehicle_no", None)
    c.setdefault("transport", None)

    items = await _fetch_challan_items(item_id)
    received_by_item = await _received_by_challan_item([item_id])
    for item in items:
        sent = float(item.get("quantity", 0) or 0)
        recv = received_by_item.get(item["id"], 0.0)
        item["quantity_received"] = recv
        item["quantity_pending"] = max(0.0, sent - recv)
    c["items"] = items

    today = datetime.now(timezone.utc).date().isoformat()
    if c.get("due_date") and c["status"] not in _CLOSED_STATUSES:
        c["is_overdue"] = c["due_date"] < today
        c["deemed_supply"] = c["is_overdue"]
    else:
        c["is_overdue"] = False
        c["deemed_supply"] = False

    return c


@router.get("/challans/{item_id}/pdf")
async def challan_pdf(item_id: str, user: dict = Depends(get_current_user)):
    """Rendered through the same shared premium template as Purchase Orders
    (rate/HSN/GST/taxable/amount columns + totals card) so job work challans
    look consistent with every other document in the app. The values shown
    are for ITC-04 valuation/reconciliation only — the §143 declaration below
    the item table still makes clear no supply/tax event occurs."""
    _require_job_work(user)
    c = await db.job_work_challans.find_one({"id": item_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Challan not found")
    items = await _fetch_challan_items(item_id)
    for item in items:
        item["unit"] = item.get("uom") or item.get("unit") or "pcs"
    c["items"] = items
    number = c.get("challan_number") or item_id
    pdf_bytes = await render_document_pdf(
        "JOB WORK CHALLAN", number, c,
        party_id=c.get("job_worker_id"), party_type="vendor",
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{number}.pdf"'},
    )


@router.post("/challans")
async def create_challan(payload: JobWorkChallan, user: dict = Depends(get_current_user)):
    _require_job_work(user)
    data = payload.model_dump()
    items = data.pop("items")
    data["id"] = new_id()

    jw_id = data.get("job_worker_id")
    if not jw_id:
        raise HTTPException(400, "job_worker_id is required")
    party = await db.vendors.find_one({"id": jw_id}) or await db.customers.find_one({"id": jw_id})
    if not party:
        raise HTTPException(400, f"Job Worker with ID '{jw_id}' not found.")
    # Auto-fill contact/GSTIN/address from the vendor record when the caller
    # didn't supply them explicitly (Tally-style "select party, rest auto-fills").
    data.setdefault("job_worker_gstin", party.get("gstin"))
    if not data.get("contact_person"):
        data["contact_person"] = party.get("extra", {}).get("contact_person") if isinstance(party.get("extra"), dict) else None
    if not data.get("mobile"):
        extra = party.get("extra") if isinstance(party.get("extra"), dict) else {}
        data["mobile"] = (extra or {}).get("mobile") or party.get("phone")
    if not data.get("address"):
        data["address"] = party.get("address")

    if not data.get("challan_number"):
        data["challan_number"] = await next_doc_number("JWC", "job_work_challans")

    nature = data.get("nature") or "inputs"
    window_days = await _get_return_window_days(nature)
    data["due_date"] = _due_date(data.get("date", now_iso()), window_days)
    data["return_window_days"] = window_days
    data["is_overdue"] = False
    data["deemed_supply"] = False

    # Batch-read every referenced product ONCE — both the enrichment loop and
    # the stock-move loop below used to re-query per line item (up to 2
    # round-trips per line); neither loop writes to products, so one snapshot
    # taken up front is correct for both passes within this single request.
    products_by_id = await _fetch_products_by_ids(items)

    # Enrich rate/taxable_value/hsn/gst on each item and validate stock. Custom
    # (free-text) items have no catalog product: skip lookup/stock/movement.
    for item in items:
        if item.get("is_custom") or not item.get("product_id"):
            item["is_custom"] = True
            item["product_id"] = None
            _enrich_item_valuation(item, None)
            continue
        prod = products_by_id.get(item["product_id"])
        if not prod:
            raise HTTPException(400, f"Product '{item.get('product_name', item['product_id'])}' not found.")
        item["product_name"] = prod["name"]
        item["sku"] = prod.get("sku", "")
        item["unit"] = prod.get("unit", "pcs")
        _enrich_item_valuation(item, prod)

    await validate_tracking_fields(items)

    is_draft = data.get("status") == "DRAFT"

    # Inventory only moves once the challan actually leaves as a real
    # dispatch — a Draft is a work-in-progress document, not yet sent.
    if not is_draft:
        await _post_job_work_movements(
            items, user, sign=-1, movement_type="JOB_WORK",
            qty_field="quantity", source_doc_type="job_work_challan",
            source_doc_id=data["id"],
        )

    inter_state = await _resolve_inter_state(data)
    for item in items:
        _compute_line_gst(item, inter_state)
    data["is_inter_state"] = inter_state
    data.update(_challan_totals(items))

    data["status"] = "DRAFT" if is_draft else "PENDING"
    data["created_at"] = now_iso()
    data["updated_at"] = now_iso()

    async with get_session() as session:
        session.add(JobWorkChallanRow(**{k: v for k, v in data.items() if hasattr(JobWorkChallanRow, k)}))
        saved_items = await _insert_challan_items(session, data["id"], data.get("tenant_id"), items)

    await log_audit("CREATE", "job_work_challans", data["id"], user, new_values={**data, "items": saved_items})

    data["items"] = saved_items
    return data


@router.put("/challans/{item_id}")
async def update_challan(item_id: str, payload: JobWorkChallan, user: dict = Depends(get_current_user)):
    """Edit a challan. Only allowed while DRAFT or PENDING with NO receipts
    logged — a received challan is partly fulfilled and editing it would
    corrupt stock / ITC-04. Reverses original inventory movements (if any were
    made — a Draft never moved stock) and re-applies for the edited lines."""
    _require_job_work(user)
    existing = await db.job_work_challans.find_one({"id": item_id})
    if not existing:
        raise HTTPException(404, "Challan not found")

    existing_status = _normalize_status(existing.get("status"))
    if existing_status not in ("DRAFT", "PENDING"):
        raise HTTPException(409, f"Only Draft or Pending challans can be edited (current status: {existing_status}).")

    receipt_count = await db.job_work_receipts.count_documents({"challan_id": item_id})
    if receipt_count > 0:
        raise HTTPException(409, "Cannot edit a challan once material receipts have been logged.")

    data = payload.model_dump()
    items = data.pop("items")

    jw_id = data.get("job_worker_id")
    if jw_id:
        party = await db.vendors.find_one({"id": jw_id}) or await db.customers.find_one({"id": jw_id})
        if not party:
            raise HTTPException(400, f"Job Worker with ID '{jw_id}' not found.")

    existing_items = await _fetch_challan_items(item_id)
    was_draft = existing_status == "DRAFT"

    # Reverse the original inventory reduction (catalog items only, and only
    # if the previous save actually moved stock — Drafts never did).
    if not was_draft:
        await _post_job_work_movements(
            existing_items, user, sign=1, movement_type="JOB_WORK_REVERSAL",
            qty_field="quantity", source_doc_type="job_work_challan_edit_reversal",
            source_doc_id=item_id,
        )

    # Batch-read for the enrich pass below (names/sku/unit/rate) — unrelated
    # to the reversal above now that stock math goes through post_entry
    # rather than a stale in-memory products.quantity snapshot.
    products_by_id = await _fetch_products_by_ids(items)

    for item in items:
        if item.get("is_custom") or not item.get("product_id"):
            item["is_custom"] = True
            item["product_id"] = None
            _enrich_item_valuation(item, None)
            continue
        prod = products_by_id.get(item["product_id"])
        if not prod:
            raise HTTPException(400, f"Product '{item.get('product_name', item['product_id'])}' not found.")
        item["product_name"] = prod["name"]
        item["sku"] = prod.get("sku", "")
        item["unit"] = prod.get("unit", "pcs")
        _enrich_item_valuation(item, prod)

    await validate_tracking_fields(items)

    challan_number = existing.get("challan_number", "")
    is_draft = data.get("status") == "DRAFT"

    if not is_draft:
        await _post_job_work_movements(
            items, user, sign=-1, movement_type="JOB_WORK",
            qty_field="quantity", source_doc_type="job_work_challan_edit",
            source_doc_id=item_id,
        )

    nature = data.get("nature") or existing.get("nature") or "inputs"
    window_days = await _get_return_window_days(nature)
    data["due_date"] = _due_date(data.get("date", now_iso()), window_days)
    data["return_window_days"] = window_days

    inter_state = await _resolve_inter_state({
        **data,
        "job_worker_id": data.get("job_worker_id") or existing.get("job_worker_id"),
    })
    for item in items:
        _compute_line_gst(item, inter_state)
    data["is_inter_state"] = inter_state
    data.update(_challan_totals(items))

    data["id"] = item_id
    data["challan_number"] = challan_number
    data["status"] = "DRAFT" if is_draft else "PENDING"
    data["is_overdue"] = False
    data["deemed_supply"] = False
    data["created_at"] = existing.get("created_at", now_iso())
    data["updated_at"] = now_iso()

    async with get_session() as session:
        row = await session.get(JobWorkChallanRow, item_id)
        for k, v in data.items():
            if hasattr(row, k):
                setattr(row, k, v)
        await session.execute(sa_delete(JobWorkChallanItem).where(JobWorkChallanItem.challan_id == item_id))
        saved_items = await _insert_challan_items(session, item_id, data.get("tenant_id"), items)

    await log_audit("UPDATE", "job_work_challans", item_id, user,
                     old_values={**existing, "items": existing_items}, new_values={**data, "items": saved_items})

    data["items"] = saved_items
    return data


@router.delete("/challans/{item_id}")
async def delete_challan(item_id: str, user: dict = Depends(get_current_user)):
    """Delete a challan, in any status. Draft/Pending (no receipts) is a plain
    delete with its own outward stock reversed. Partial/Completed cascades:
    every receipt logged against it is deleted first (each reversing its own
    inward return, same as delete_receipt), THEN the challan's full original
    outward posting is reversed, THEN the challan itself is deleted — so
    nothing is left orphaned and stock ends up exactly where it would be had
    the challan never existed. Same permission bar as every other status
    (_require_job_work) — user's explicit choice over restricting this
    further to admin-only."""
    _require_job_work(user)
    existing = await db.job_work_challans.find_one({"id": item_id})
    if not existing:
        raise HTTPException(404, "Challan not found")

    current_status = _normalize_status(existing.get("status"))
    if current_status == "CANCELLED":
        raise HTTPException(409, "Challan is already cancelled — nothing to delete.")

    items = await _fetch_challan_items(item_id)
    skipped_products: list[str] = []

    # Cascade: delete every receipt against this challan first, each
    # reversing its own inward return exactly as delete_receipt does alone —
    # so a challan with receipts is never left with orphaned receipt rows
    # pointing at a challan_id that no longer exists. best_effort=True: a
    # line whose product was since deleted from the catalog must not abort
    # the whole delete (see _post_job_work_movements) — old challans commonly
    # outlive a product that's since been removed from the catalog.
    receipts = await db.job_work_receipts.find({"challan_id": item_id}, {"_id": 0}).to_list(1000)
    for receipt in receipts:
        async with get_session() as session:
            result = await session.execute(select(JobWorkReceiptItem).where(JobWorkReceiptItem.receipt_id == receipt["id"]))
            receipt_items = [_row_dict(r) for r in result.scalars().all()]
        skipped_products += await _reverse_receipt_inventory(
            receipt_items, user, f"{receipt.get('receipt_number', '')} (deleted with challan)",
            receipt_id=receipt["id"], receipt_number=receipt.get("receipt_number", ""),
            best_effort=True,
        )
        async with get_session() as session:
            await session.execute(sa_delete(JobWorkReceiptItem).where(JobWorkReceiptItem.receipt_id == receipt["id"]))
            row = await session.get(JobWorkReceiptRow, receipt["id"])
            if row:
                await session.delete(row)
        await log_audit("DELETE", "job_work_receipts", receipt["id"], user, old_values={**receipt, "items": receipt_items})

    # Reverse the challan's own original outward posting — a Draft never
    # posted any (per_post_job_work_movements's own "custom lines never moved
    # stock" + Draft-status skip elsewhere), everything else did, for the
    # FULL original quantity now that every receipt (which already reversed
    # its own portion) has just been deleted above.
    if current_status != "DRAFT":
        skipped_products += await _post_job_work_movements(
            items, user, sign=1, movement_type="JOB_WORK_REVERSAL",
            qty_field="quantity", source_doc_type="job_work_challan_delete",
            source_doc_id=item_id, best_effort=True,
        )

    if skipped_products:
        log.warning(
            "job_work: challan %s deleted with %d line(s) whose product no longer exists — "
            "stock could not be reversed for: %s",
            item_id, len(skipped_products), skipped_products,
        )

    je_id = existing.get("journal_entry_id")
    if je_id:
        await db.journal_entries.update_one(
            {"id": je_id},
            {"$set": {"status": "REVERSED", "updated_at": now_iso()}},
        )

    await log_audit("DELETE", "job_work_challans", item_id, user, old_values={**existing, "items": items})

    async with get_session() as session:
        await session.execute(sa_delete(JobWorkChallanItem).where(JobWorkChallanItem.challan_id == item_id))
        row = await session.get(JobWorkChallanRow, item_id)
        if row:
            await session.delete(row)

    return {"_stock_reversal_skipped": skipped_products}


@router.post("/challans/{item_id}/cancel")
async def cancel_challan(item_id: str, user: dict = Depends(get_current_user)):
    """Cancel a challan that has already moved material — the path
    delete_challan itself points a caller at once a challan is PARTIAL/
    COMPLETED and can no longer be hard-deleted (delete would silently lose
    track of the material that already left, or is still outstanding).

    Only the portion still with the job worker (sent minus already-received)
    is reversed back into stock — the received portion already cycled back
    correctly through its own receipt/_apply_receipt_inventory, reversing it
    again here would double-count. Existing receipts are left untouched (they
    remain the true record of what actually came back); no further receipts
    can be logged against a CANCELLED challan (see create_receipt's status
    check)."""
    _require_job_work(user)
    existing = await db.job_work_challans.find_one({"id": item_id})
    if not existing:
        raise HTTPException(404, "Challan not found")

    current_status = _normalize_status(existing.get("status"))
    if current_status in _CLOSED_STATUSES:
        raise HTTPException(409, f"Challan is already {current_status}.")

    items = await _fetch_challan_items(item_id)
    received_by_item = await _received_by_challan_item([item_id])
    outstanding_items = []
    for it in items:
        sent = float(it.get("quantity") or 0)
        recv = received_by_item.get(it["id"], 0.0)
        outstanding = sent - recv
        if outstanding > 1e-6:
            outstanding_items.append({**it, "quantity": outstanding})

    skipped_products: list[str] = []
    if outstanding_items:
        skipped_products = await _post_job_work_movements(
            outstanding_items, user, sign=1, movement_type="JOB_WORK_REVERSAL",
            qty_field="quantity", source_doc_type="job_work_challan_cancel",
            source_doc_id=item_id, best_effort=True,
        )

    await db.job_work_challans.update_one(
        {"id": item_id},
        {"$set": {"status": "CANCELLED", "is_overdue": False, "deemed_supply": False,
                   "cancelled_by": user["id"], "cancelled_at": now_iso(), "updated_at": now_iso()}},
    )
    new_values = await db.job_work_challans.find_one({"id": item_id}, {"_id": 0}) or {}
    await log_audit("UPDATE", "job_work_challans", item_id, user, old_values=existing, new_values=new_values)
    if skipped_products:
        new_values["_stock_reversal_skipped"] = skipped_products
    return new_values


@router.post("/challans/{item_id}/attachments")
async def add_challan_attachment(item_id: str, payload: dict, user: dict = Depends(get_current_user)):
    """Attach an already-uploaded document (via /uploads/document) to a
    challan — e.g. a scanned job worker acknowledgement copy."""
    _require_job_work(user)
    challan = await db.job_work_challans.find_one({"id": item_id})
    if not challan:
        raise HTTPException(404, "Challan not found")
    attachment = {
        "id": new_id(),
        "name": payload.get("name") or "document",
        "path": payload["path"],
        "size": payload.get("size"),
        "content_type": payload.get("content_type"),
        "uploaded_by": user["id"],
        "uploaded_at": now_iso(),
    }
    attachments = list(challan.get("attachments") or []) + [attachment]
    await db.job_work_challans.update_one({"id": item_id}, {"$set": {"attachments": attachments, "updated_at": now_iso()}})
    return attachment


@router.delete("/challans/{item_id}/attachments/{attachment_id}")
async def remove_challan_attachment(item_id: str, attachment_id: str, user: dict = Depends(get_current_user)):
    _require_job_work(user)
    challan = await db.job_work_challans.find_one({"id": item_id})
    if not challan:
        raise HTTPException(404, "Challan not found")
    attachments = [a for a in (challan.get("attachments") or []) if a.get("id") != attachment_id]
    await db.job_work_challans.update_one({"id": item_id}, {"$set": {"attachments": attachments, "updated_at": now_iso()}})
    return {"ok": True}


# ══════════════════════════════════════════════════════════════
# Receipts (Inward)
# ══════════════════════════════════════════════════════════════

async def _resync_challan_status(challan_id: str) -> None:
    """Roll up all receipts logged against a challan and set its lifecycle
    status (PENDING/PARTIAL/COMPLETED) accordingly. Recomputes is_overdue too
    — a challan still PARTIAL past its due date must stay flagged overdue even
    after a receipt is logged; only reaching COMPLETED clears it."""
    challan = await db.job_work_challans.find_one({"id": challan_id})
    if not challan:
        return
    items = await _fetch_challan_items(challan_id)
    received_by_item = await _received_by_challan_item([challan_id])

    completed = True
    partial = False
    for it in items:
        sent = float(it["quantity"] or 0)
        recv = received_by_item.get(it["id"], 0.0)
        if recv < sent - 1e-6:
            completed = False
        if recv > 1e-6:
            partial = True

    new_status = "COMPLETED" if completed else ("PARTIAL" if partial else "PENDING")

    if new_status == "COMPLETED":
        is_overdue = False
    else:
        today = datetime.now(timezone.utc).date().isoformat()
        due_date = challan.get("due_date")
        is_overdue = bool(due_date and due_date < today)

    await db.job_work_challans.update_one(
        {"id": challan_id},
        {"$set": {"status": new_status, "is_overdue": is_overdue, "deemed_supply": is_overdue, "updated_at": now_iso()}},
    )


async def _reverse_receipt_inventory(
    receipt_items: list[dict], user: dict, reason_suffix: str,
    receipt_id: str | None = None, receipt_number: str | None = None,
    best_effort: bool = False,
) -> list[str]:
    return await _post_job_work_movements(
        receipt_items, user, sign=-1, movement_type="JOB_WORK_REVERSAL",
        qty_field="quantity_received", source_doc_type="job_work_receipt_reversal",
        source_doc_id=receipt_id, best_effort=best_effort,
    )


async def _apply_receipt_inventory(
    receipt_items: list[dict], user: dict, reason_suffix: str,
    receipt_id: str | None = None, receipt_number: str | None = None,
) -> None:
    await _post_job_work_movements(
        receipt_items, user, sign=1, movement_type="JOB_WORK_RECEIPT",
        qty_field="quantity_received", source_doc_type="job_work_receipt",
        source_doc_id=receipt_id,
    )


def _resolve_challan_item_id(item: dict, challan_items_by_id: dict, challan_items_by_product: dict) -> str:
    """Resolve which challan line this receipt line is against. Prefers the
    explicit challan_item_id sent by the client (the precise, new mechanism);
    falls back to product_id/name matching only for older callers that don't
    send it yet."""
    cid = item.get("challan_item_id")
    if cid and cid in challan_items_by_id:
        return cid
    key = item.get("product_id") or f"custom::{item.get('product_name', '')}"
    match = challan_items_by_product.get(key)
    if not match:
        raise HTTPException(
            400,
            f"'{item.get('product_name')}' does not match any line on this challan.",
        )
    return match["id"]


@router.post("/challans/{item_id}/receipt")
async def create_receipt(item_id: str, payload: JobWorkReceipt, user: dict = Depends(get_current_user)):
    _require_job_work(user)
    challan = await db.job_work_challans.find_one({"id": item_id})
    if not challan:
        raise HTTPException(status_code=404, detail="Challan not found")
    challan_status = _normalize_status(challan.get("status"))
    if challan_status in _CLOSED_STATUSES:
        raise HTTPException(409, f"Cannot log a receipt against a {challan_status} challan.")

    data = payload.model_dump()
    items = data.pop("items")
    data["id"] = new_id()

    if data.get("receipt_number"):
        dup = await db.job_work_receipts.find_one({"receipt_number": data["receipt_number"]})
        if dup:
            raise HTTPException(400, f"Receipt number '{data['receipt_number']}' already exists.")
    if not data.get("receipt_number"):
        data["receipt_number"] = await next_doc_number("JWR", "job_work_receipts")
    data["challan_id"] = item_id

    challan_items = await _fetch_challan_items(item_id)
    challan_items_by_id = {ci["id"]: ci for ci in challan_items}
    challan_items_by_product = {
        (ci.get("product_id") or f"custom::{ci.get('product_name', '')}"): ci for ci in challan_items
    }
    received_by_item = await _received_by_challan_item([item_id])
    products_by_id = await _fetch_products_by_ids(items)

    for item in items:
        if item.get("is_custom") or not item.get("product_id"):
            item["is_custom"] = True
            item["product_id"] = None
        else:
            prod = products_by_id.get(item["product_id"])
            if prod:
                item["product_name"] = prod["name"]
                item["sku"] = prod.get("sku", "")

        challan_item_id = _resolve_challan_item_id(item, challan_items_by_id, challan_items_by_product)
        item["challan_item_id"] = challan_item_id
        ci = challan_items_by_id[challan_item_id]
        sent_qty = float(ci["quantity"] or 0)
        already_received = received_by_item.get(challan_item_id, 0.0)
        pending_qty = sent_qty - already_received

        if float(item["quantity_received"]) > pending_qty + 1e-5:
            raise HTTPException(
                400,
                f"Received quantity ({item['quantity_received']}) exceeds pending "
                f"({pending_qty}) for '{item['product_name']}'.",
            )
        _resolve_accepted_quantity(item)
        # Track this line's contribution so a second line against the SAME
        # challan item within the same receipt payload is validated correctly.
        received_by_item[challan_item_id] = already_received + float(item["quantity_received"])

    await validate_tracking_fields(items)

    data["created_at"] = now_iso()
    data["status"] = "PARTIAL"  # placeholder; real status is challan-level, kept for legacy column compat

    async with get_session() as session:
        session.add(JobWorkReceiptRow(**{k: v for k, v in data.items() if hasattr(JobWorkReceiptRow, k)}))
        now = now_iso()
        saved_items = []
        for item in items:
            row_id = new_id()
            session.add(JobWorkReceiptItem(
                id=row_id, receipt_id=data["id"], tenant_id=data.get("tenant_id"),
                challan_item_id=item["challan_item_id"],
                product_id=item.get("product_id"), product_name=item.get("product_name"),
                sku=item.get("sku"), is_custom=bool(item.get("is_custom")),
                quantity_received=item.get("quantity_received"),
                accepted_quantity=item.get("accepted_quantity"),
                rejected_quantity=item.get("rejected_quantity", 0),
                scrap_quantity=item.get("scrap_quantity", 0),
                batch_id=item.get("batch_id"), serial_id=item.get("serial_id"),
                expiry_date=item.get("expiry_date"), remarks=item.get("remarks"),
                created_at=now, updated_at=now,
            ))
            saved_items.append({**item, "id": row_id})

    await _apply_receipt_inventory(
        saved_items, user, data["receipt_number"],
        receipt_id=data["id"], receipt_number=data["receipt_number"],
    )
    await _resync_challan_status(item_id)

    await log_audit("CREATE", "job_work_receipts", data["id"], user, new_values={**data, "items": saved_items})

    data["items"] = saved_items
    return data


@router.put("/receipts/{item_id}")
async def update_receipt(item_id: str, payload: JobWorkReceipt, user: dict = Depends(get_current_user)):
    """Edit a logged receipt. Reverses its original inventory return,
    re-validates against pending (excluding this receipt's own prior
    contribution), re-applies inventory, and re-syncs the parent challan's
    status. Never touches job_work_challans rows directly."""
    _require_job_work(user)
    existing = await db.job_work_receipts.find_one({"id": item_id})
    if not existing:
        raise HTTPException(404, "Receipt not found")

    challan_id = existing["challan_id"]
    challan = await db.job_work_challans.find_one({"id": challan_id})
    if not challan:
        raise HTTPException(404, "Parent challan not found")

    async with get_session() as session:
        result = await session.execute(select(JobWorkReceiptItem).where(JobWorkReceiptItem.receipt_id == item_id))
        existing_items = [_row_dict(r) for r in result.scalars().all()]

    await _reverse_receipt_inventory(
        existing_items, user, f"{existing.get('receipt_number', '')} (edit reversal)",
        receipt_id=item_id, receipt_number=existing.get("receipt_number", ""),
    )

    data = payload.model_dump()
    items = data.pop("items")

    challan_items = await _fetch_challan_items(challan_id)
    challan_items_by_id = {ci["id"]: ci for ci in challan_items}
    challan_items_by_product = {
        (ci.get("product_id") or f"custom::{ci.get('product_name', '')}"): ci for ci in challan_items
    }
    # Pending must be computed against OTHER receipts only (this one's
    # original contribution was just reversed above).
    async with get_session() as session:
        result = await session.execute(
            select(JobWorkReceiptItem.challan_item_id, JobWorkReceiptItem.quantity_received)
            .where(JobWorkReceiptItem.receipt_id != item_id, JobWorkReceiptItem.challan_item_id.in_(list(challan_items_by_id)))
        )
        received_by_item: dict = {}
        for cid, qty in result.all():
            if cid is None:
                continue
            received_by_item[cid] = received_by_item.get(cid, 0.0) + float(qty or 0)

    products_by_id = await _fetch_products_by_ids(items)
    for item in items:
        if item.get("is_custom") or not item.get("product_id"):
            item["is_custom"] = True
            item["product_id"] = None
        else:
            prod = products_by_id.get(item["product_id"])
            if prod:
                item["product_name"] = prod["name"]
                item["sku"] = prod.get("sku", "")

        challan_item_id = _resolve_challan_item_id(item, challan_items_by_id, challan_items_by_product)
        item["challan_item_id"] = challan_item_id
        ci = challan_items_by_id[challan_item_id]
        sent_qty = float(ci["quantity"] or 0)
        already_received = received_by_item.get(challan_item_id, 0.0)
        pending_qty = sent_qty - already_received

        if float(item["quantity_received"]) > pending_qty + 1e-5:
            raise HTTPException(
                400,
                f"Received quantity ({item['quantity_received']}) exceeds pending "
                f"({pending_qty}) for '{item['product_name']}'.",
            )
        _resolve_accepted_quantity(item)
        received_by_item[challan_item_id] = already_received + float(item["quantity_received"])

    await validate_tracking_fields(items)

    data["id"] = item_id
    data["receipt_number"] = existing.get("receipt_number")
    data["challan_id"] = challan_id
    data["created_at"] = existing.get("created_at", now_iso())
    data["updated_at"] = now_iso()

    async with get_session() as session:
        row = await session.get(JobWorkReceiptRow, item_id)
        for k, v in data.items():
            if hasattr(row, k):
                setattr(row, k, v)
        await session.execute(sa_delete(JobWorkReceiptItem).where(JobWorkReceiptItem.receipt_id == item_id))
        now = now_iso()
        saved_items = []
        for item in items:
            row_id = new_id()
            session.add(JobWorkReceiptItem(
                id=row_id, receipt_id=item_id, tenant_id=data.get("tenant_id"),
                challan_item_id=item["challan_item_id"],
                product_id=item.get("product_id"), product_name=item.get("product_name"),
                sku=item.get("sku"), is_custom=bool(item.get("is_custom")),
                quantity_received=item.get("quantity_received"),
                accepted_quantity=item.get("accepted_quantity"),
                rejected_quantity=item.get("rejected_quantity", 0),
                scrap_quantity=item.get("scrap_quantity", 0),
                batch_id=item.get("batch_id"), serial_id=item.get("serial_id"),
                expiry_date=item.get("expiry_date"), remarks=item.get("remarks"),
                created_at=now, updated_at=now,
            ))
            saved_items.append({**item, "id": row_id})

    await _apply_receipt_inventory(
        saved_items, user, f"{data['receipt_number']} (edited)",
        receipt_id=item_id, receipt_number=data["receipt_number"],
    )
    await _resync_challan_status(challan_id)

    await log_audit("UPDATE", "job_work_receipts", item_id, user,
                     old_values={**existing, "items": existing_items}, new_values={**data, "items": saved_items})

    data["items"] = saved_items
    return data


@router.delete("/receipts/{item_id}")
async def delete_receipt(item_id: str, user: dict = Depends(get_current_user)):
    """Delete a logged receipt. Reverses its inventory return and re-syncs the
    parent challan's status/balance from the remaining receipts."""
    _require_job_work(user)
    existing = await db.job_work_receipts.find_one({"id": item_id})
    if not existing:
        raise HTTPException(404, "Receipt not found")

    challan_id = existing["challan_id"]

    async with get_session() as session:
        result = await session.execute(select(JobWorkReceiptItem).where(JobWorkReceiptItem.receipt_id == item_id))
        items = [_row_dict(r) for r in result.scalars().all()]

    skipped_products = await _reverse_receipt_inventory(
        items, user, f"{existing.get('receipt_number', '')} (deleted)",
        receipt_id=item_id, receipt_number=existing.get("receipt_number", ""),
        best_effort=True,
    )

    if skipped_products:
        log.warning(
            "job_work: receipt %s deleted with %d line(s) whose product no longer exists — "
            "stock could not be reversed for: %s",
            item_id, len(skipped_products), skipped_products,
        )

    async with get_session() as session:
        await session.execute(sa_delete(JobWorkReceiptItem).where(JobWorkReceiptItem.receipt_id == item_id))
        row = await session.get(JobWorkReceiptRow, item_id)
        if row:
            await session.delete(row)

    await _resync_challan_status(challan_id)

    await log_audit("DELETE", "job_work_receipts", item_id, user, old_values={**existing, "items": items})

    return {"_stock_reversal_skipped": skipped_products}


@router.post("/receipts/{item_id}/attachments")
async def add_receipt_attachment(item_id: str, payload: dict, user: dict = Depends(get_current_user)):
    """Attach an already-uploaded document (via /uploads/document) to a
    receipt — e.g. a scanned job worker acknowledgement copy."""
    _require_job_work(user)
    receipt = await db.job_work_receipts.find_one({"id": item_id})
    if not receipt:
        raise HTTPException(404, "Receipt not found")
    attachment = {
        "id": new_id(),
        "name": payload.get("name") or "document",
        "path": payload["path"],
        "size": payload.get("size"),
        "content_type": payload.get("content_type"),
        "uploaded_by": user["id"],
        "uploaded_at": now_iso(),
    }
    attachments = list(receipt.get("attachments") or []) + [attachment]
    await db.job_work_receipts.update_one({"id": item_id}, {"$set": {"attachments": attachments, "updated_at": now_iso()}})
    return attachment


@router.delete("/receipts/{item_id}/attachments/{attachment_id}")
async def remove_receipt_attachment(item_id: str, attachment_id: str, user: dict = Depends(get_current_user)):
    _require_job_work(user)
    receipt = await db.job_work_receipts.find_one({"id": item_id})
    if not receipt:
        raise HTTPException(404, "Receipt not found")
    attachments = [a for a in (receipt.get("attachments") or []) if a.get("id") != attachment_id]
    await db.job_work_receipts.update_one({"id": item_id}, {"$set": {"attachments": attachments, "updated_at": now_iso()}})
    return {"ok": True}


@router.get("/receipts/{item_id}/pdf")
async def receipt_pdf(item_id: str, user: dict = Depends(get_current_user)):
    _require_job_work(user)
    r = await db.job_work_receipts.find_one({"id": item_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Receipt not found")
    async with get_session() as session:
        result = await session.execute(select(JobWorkReceiptItem).where(JobWorkReceiptItem.receipt_id == item_id))
        r["items"] = [_row_dict(row) for row in result.scalars().all()]
    challan = await db.job_work_challans.find_one({"id": r.get("challan_id")}, {"_id": 0})
    pdf_bytes = build_jobwork_receipt_pdf(r, challan=challan, company=await get_active_company())
    number = r.get("receipt_number") or item_id
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{number}.pdf"'},
    )


# ══════════════════════════════════════════════════════════════
# Receipts list
# ══════════════════════════════════════════════════════════════

async def _fetch_enriched_receipts(challan_id: Optional[str], q: Optional[str]) -> list[dict]:
    """Query job_work_receipts headers, join in job_work_receipt_items, and
    enrich with challan_number/job_worker_name + per-line sent/pending qty by
    joining job_work_challan_items via challan_item_id. Never touches
    job_work_challans as a primary result — only for enrichment lookups."""
    filt: dict = {}
    if challan_id:
        filt["challan_id"] = challan_id
    receipts = await db.job_work_receipts.find(filt, {"_id": 0}).sort("created_at", -1).to_list(1000)

    c_ids = list({r["challan_id"] for r in receipts if r.get("challan_id")})
    challans = await db.job_work_challans.find({"id": {"$in": c_ids}}).to_list(len(c_ids) + 10) if c_ids else []
    challan_map = {c["id"]: c for c in challans}

    items_by_receipt: dict[str, list] = {}
    if receipts:
        async with get_session() as session:
            result = await session.execute(
                select(JobWorkReceiptItem).where(JobWorkReceiptItem.receipt_id.in_([r["id"] for r in receipts]))
            )
            for row in result.scalars().all():
                items_by_receipt.setdefault(row.receipt_id, []).append(_row_dict(row))

    challan_item_ids = {it.get("challan_item_id") for items in items_by_receipt.values() for it in items if it.get("challan_item_id")}
    challan_items_by_id: dict = {}
    if challan_item_ids:
        async with get_session() as session:
            result = await session.execute(select(JobWorkChallanItem).where(JobWorkChallanItem.id.in_(list(challan_item_ids))))
            challan_items_by_id = {row.id: _row_dict(row) for row in result.scalars().all()}

    received_by_item = await _received_by_challan_item(c_ids)

    for r in receipts:
        c_id = r.get("challan_id")
        c = challan_map.get(c_id)
        r["challan_number"] = c.get("challan_number") if c else "—"
        r["job_worker_id"] = c.get("job_worker_id") if c else None
        r["job_worker_name"] = c.get("job_worker_name") if c else "—"

        items = items_by_receipt.get(r["id"], [])
        any_pending = False
        for it in items:
            ci = challan_items_by_id.get(it.get("challan_item_id"), {})
            sent = float(ci.get("quantity", 0) or 0)
            it["quantity_sent"] = sent
            it["rate"] = ci.get("rate", 0)
            it.setdefault("rejected_quantity", 0.0)
            it.setdefault("scrap_quantity", 0.0)
            if it.get("accepted_quantity") is None:
                it["accepted_quantity"] = max(
                    0.0,
                    float(it.get("quantity_received", 0) or 0)
                    - float(it["rejected_quantity"])
                    - float(it["scrap_quantity"]),
                )
            total_recv_for_item = received_by_item.get(it.get("challan_item_id"), 0.0)
            pending = max(0.0, sent - total_recv_for_item)
            it["quantity_pending"] = pending
            if pending > 1e-6:
                any_pending = True
        r["items"] = items
        r["status"] = "PARTIAL" if any_pending else "COMPLETED"

    if q:
        needle = q.strip().lower()
        receipts = [
            r for r in receipts
            if needle in (r.get("receipt_number") or "").lower()
            or needle in (r.get("challan_number") or "").lower()
            or needle in (r.get("job_worker_name") or "").lower()
        ]

    return receipts


@router.get("/receipts")
async def list_receipts(
    challan_id: Optional[str] = None,
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    user: dict = Depends(get_current_user),
):
    _require_job_work(user)
    receipts = await _fetch_enriched_receipts(challan_id, q)
    total = len(receipts)
    start = (page - 1) * limit
    items = receipts[start: start + limit]
    return {"total": total, "page": page, "limit": limit, "items": items}


@router.get("/receipts/export")
async def export_receipts(
    challan_id: Optional[str] = None,
    q: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Download all matching receipt line items as an .xlsx workbook (one row per line item)."""
    _require_job_work(user)
    from openpyxl import Workbook

    receipts = await _fetch_enriched_receipts(challan_id, q)

    wb = Workbook()
    ws = wb.active
    if ws is None:
        raise HTTPException(500, "Could not create workbook sheet")
    ws.title = "Receipts Inward"
    headers = ["Receipt No", "Receipt Date", "Challan No", "Job Worker", "Item Name",
               "Sent Qty", "Received Qty", "Accepted Qty", "Rejected Qty", "Scrap Qty",
               "Pending Qty", "Status", "Remarks"]
    ws.append(headers)
    for r in receipts:
        for item in r.get("items", []):
            ws.append([
                r.get("receipt_number", ""),
                r.get("date", ""),
                r.get("challan_number", ""),
                r.get("job_worker_name", ""),
                item.get("product_name", ""),
                float(item.get("quantity_sent", 0) or 0),
                float(item.get("quantity_received", 0) or 0),
                float(item.get("accepted_quantity", 0) or 0),
                float(item.get("rejected_quantity", 0) or 0),
                float(item.get("scrap_quantity", 0) or 0),
                float(item.get("quantity_pending", 0) or 0),
                r.get("status", ""),
                item.get("remarks") or r.get("notes", "") or "",
            ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="job-work-receipts.xlsx"'},
    )


# ══════════════════════════════════════════════════════════════
# Challan → receipt pre-fill (Tally-style: pick a challan, everything auto-loads)
# ══════════════════════════════════════════════════════════════

@router.get("/challans/{item_id}/receipt-form")
async def get_receipt_form_data(item_id: str, user: dict = Depends(get_current_user)):
    """Everything the Receipt (Inward) voucher needs once a challan is picked:
    each open line's sent/previously-received/pending qty, ready to render as
    read-only fields with only Current Receipt Qty/Accepted/Rejected/Scrap/
    Remarks left for the user to type."""
    _require_job_work(user)
    challan = await db.job_work_challans.find_one({"id": item_id}, {"_id": 0})
    if not challan:
        raise HTTPException(404, "Challan not found")

    items = await _fetch_challan_items(item_id)
    received_by_item = await _received_by_challan_item([item_id])

    lines = []
    for it in items:
        sent = float(it.get("quantity", 0) or 0)
        prev_received = received_by_item.get(it["id"], 0.0)
        pending = max(0.0, sent - prev_received)
        lines.append({
            "challan_item_id": it["id"],
            "product_id": it.get("product_id"),
            "product_name": it.get("product_name"),
            "sku": it.get("sku"),
            "is_custom": it.get("is_custom"),
            "uom": it.get("uom"),
            "quantity_sent": sent,
            "quantity_already_received": prev_received,
            "quantity_pending": pending,
        })

    return {
        "challan_id": challan["id"],
        "challan_number": challan.get("challan_number"),
        "job_worker_id": challan.get("job_worker_id"),
        "job_worker_name": challan.get("job_worker_name"),
        "due_date": challan.get("due_date"),
        "is_overdue": challan.get("is_overdue"),
        "status": _normalize_status(challan.get("status")),
        "lines": lines,
    }


# ══════════════════════════════════════════════════════════════
# Pending / Completed / Overdue material reports (separated menus)
# ══════════════════════════════════════════════════════════════

async def _pending_rows(status_filter: list[str] | None = None, overdue_only: bool = False) -> list[dict]:
    q: dict = {"status": {"$in": list(status_filter)}} if status_filter else {}
    challans = await db.job_work_challans.find(q).to_list(1000)
    challan_ids = [c["id"] for c in challans]

    items_by_challan = await _fetch_challan_items_for_ids(challan_ids)
    received_by_item = await _received_by_challan_item(challan_ids)

    today = datetime.now(timezone.utc).date().isoformat()
    today_dt = datetime.now(timezone.utc).date()
    rows = []
    for c in challans:
        is_overdue = bool(c.get("due_date") and c["due_date"] < today and _normalize_status(c.get("status")) not in _CLOSED_STATUSES)
        if overdue_only and not is_overdue:
            continue

        days_pending = None
        if c.get("date"):
            try:
                challan_date = datetime.fromisoformat(c["date"].split("T")[0]).date()
                days_pending = (today_dt - challan_date).days
            except Exception:
                pass

        c_items = items_by_challan.get(c["id"]) or c.get("items") or []
        for item in c_items:
            sent = float(item.get("quantity", 0) or 0)
            item_id = item.get("id")
            received = received_by_item.get(item_id, 0.0) if item_id else 0.0
            pending = sent - received
            if pending <= 1e-6:
                continue
            days_remaining = None
            if c.get("due_date"):
                try:
                    due = datetime.fromisoformat(c["due_date"]).date()
                    days_remaining = (due - today_dt).days
                except ValueError:
                    pass
            rows.append({
                "challan_id": c["id"],
                "challan_number": c["challan_number"],
                "date": c["date"],
                "due_date": c.get("due_date"),
                "days_remaining": days_remaining,
                "days_pending": days_pending,
                "is_overdue": is_overdue,
                "overdue_status": "Overdue" if is_overdue else "Active",
                "deemed_supply": is_overdue,
                "job_worker_id": c.get("job_worker_id"),
                "job_worker_name": c["job_worker_name"],
                "product_id": item.get("product_id"),
                "product_name": item.get("product_name"),
                "sku": item.get("sku", ""),
                "quantity_sent": sent,
                "quantity_received": received,
                "quantity_pending": round(pending, 4),
                "unit": item.get("uom", "pcs"),
                "rate": item.get("rate", 0),
                "taxable_value": item.get("taxable_value", 0),
            })
    return rows


@router.get("/reports/pending")
async def get_pending_job_work(user: dict = Depends(get_current_user)):
    """Outstanding materials at job workers with overdue flag."""
    _require_job_work(user)
    return await _pending_rows(status_filter=["PENDING", "PARTIAL", "DRAFT"])


@router.get("/reports/completed")
async def get_completed_job_work(
    date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Challans fully returned (status COMPLETED) — separate menu from Pending."""
    _require_job_work(user)
    q: dict = {"status": "COMPLETED"}
    if date_from or date_to:
        rng: dict = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        q["date"] = rng
    challans = await db.job_work_challans.find(q, {"_id": 0}).sort("date", -1).to_list(1000)
    challan_ids = [c["id"] for c in challans]
    items_by_challan = await _fetch_challan_items_for_ids(challan_ids)
    received_by_item = await _received_by_challan_item(challan_ids)
    for c in challans:
        items = items_by_challan.get(c["id"], [])
        for item in items:
            sent = float(item.get("quantity", 0) or 0)
            recv = received_by_item.get(item["id"], 0.0)
            item["quantity_received"] = recv
            item["quantity_pending"] = max(0.0, sent - recv)
        c["items"] = items
    return challans


@router.get("/reports/overdue")
async def get_overdue_job_work(user: dict = Depends(get_current_user)):
    """Challans past their return-window due date with material still
    outstanding — separate menu from the general Pending report."""
    _require_job_work(user)
    return await _pending_rows(status_filter=["PENDING", "PARTIAL"], overdue_only=True)


# ══════════════════════════════════════════════════════════════
# Job Work Report (per-challan history + job-worker/GST/aging summary)
# ══════════════════════════════════════════════════════════════

def _age_bucket(days: int) -> str:
    if days <= 30:
        return "0-30"
    if days <= 90:
        return "31-90"
    if days <= 180:
        return "91-180"
    return "180+"


async def _build_jobwork_report(date_from: Optional[str], date_to: Optional[str]) -> dict:
    """Consolidated report: per-job-worker summary, GST/tax roll-up, aging of
    pending material, and one row per challan (Sent/Received/Pending/Status)."""
    filt: dict = {}
    if date_from or date_to:
        rng: dict = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        filt["date"] = rng

    challans = await db.job_work_challans.find(filt, {"_id": 0}).sort("date", -1).to_list(5000)
    challan_ids = [c["id"] for c in challans]
    items_by_challan = await _fetch_challan_items_for_ids(challan_ids)
    received_by_item = await _received_by_challan_item(challan_ids)

    # scrap totals per challan, summed from receipt items against its lines
    scrap_by_challan: dict[str, float] = {}
    if challan_ids:
        async with get_session() as session:
            result = await session.execute(
                select(JobWorkChallanItem.challan_id, JobWorkReceiptItem.scrap_quantity)
                .join(JobWorkReceiptItem, JobWorkReceiptItem.challan_item_id == JobWorkChallanItem.id)
                .where(JobWorkChallanItem.challan_id.in_(challan_ids))
            )
            for cid, scrap in result.all():
                scrap_by_challan[cid] = scrap_by_challan.get(cid, 0.0) + float(scrap or 0)

    today = datetime.now(timezone.utc).date()
    today_iso = today.isoformat()

    workers: dict = {}
    gst = {"taxable_value": 0.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0, "total_gst": 0.0}
    aging = {"0-30": 0.0, "31-90": 0.0, "91-180": 0.0, "180+": 0.0}
    aging_value = {"0-30": 0.0, "31-90": 0.0, "91-180": 0.0, "180+": 0.0}
    overdue_total = 0
    challan_rows: list[dict] = []

    for c in challans:
        items = items_by_challan.get(c["id"], [])
        is_overdue = bool(c.get("due_date") and c["due_date"] < today_iso and c.get("status") not in _CLOSED_STATUSES)
        if is_overdue:
            overdue_total += 1

        c_sent = sum(float(it.get("quantity", 0) or 0) for it in items)
        c_received = sum(received_by_item.get(it["id"], 0.0) for it in items)
        c_pending = max(0.0, c_sent - c_received)
        row_status = c.get("status") or "PENDING"
        if is_overdue:
            row_status = "OVERDUE"
        challan_rows.append({
            "challan_id": c["id"],
            "challan_number": c.get("challan_number"),
            "date": c.get("date"),
            "due_date": c.get("due_date"),
            "job_worker_name": c.get("job_worker_name") or "—",
            "quantity_sent": round(c_sent, 4),
            "quantity_received": round(c_received, 4),
            "quantity_pending": round(c_pending, 4),
            "status": row_status,
        })

        wid = c.get("job_worker_id") or "—"
        w = workers.setdefault(wid, {
            "job_worker_id": wid,
            "job_worker_name": c.get("job_worker_name") or "—",
            "job_worker_gstin": c.get("job_worker_gstin") or "",
            "challans": 0, "qty_sent": 0.0, "qty_received": 0.0,
            "qty_pending": 0.0, "scrap": 0.0, "taxable_value": 0.0,
            "total_gst": 0.0, "overdue": 0,
        })
        w["challans"] += 1
        w["scrap"] += scrap_by_challan.get(c["id"], 0.0)
        if is_overdue:
            w["overdue"] += 1
        w["taxable_value"] += float(c.get("total_taxable_value", 0) or 0)
        w["total_gst"] += float(c.get("total_gst", 0) or 0)

        gst["taxable_value"] += float(c.get("total_taxable_value", 0) or 0)
        gst["cgst"] += float(c.get("total_cgst", 0) or 0)
        gst["sgst"] += float(c.get("total_sgst", 0) or 0)
        gst["igst"] += float(c.get("total_igst", 0) or 0)
        gst["total_gst"] += float(c.get("total_gst", 0) or 0)

        days_out = None
        if c.get("date"):
            try:
                days_out = (today - datetime.fromisoformat(c["date"]).date()).days
            except ValueError:
                days_out = None
        for item in items:
            sent = float(item.get("quantity", 0) or 0)
            recv = received_by_item.get(item["id"], 0.0)
            pending = sent - recv
            w["qty_sent"] += sent
            w["qty_received"] += recv
            if pending > 1e-6:
                w["qty_pending"] += pending
                if days_out is not None:
                    bucket = _age_bucket(days_out)
                    aging[bucket] += round(pending, 4)
                    rate = float(item.get("rate", 0) or 0)
                    aging_value[bucket] += round(pending * rate, 2)

    worker_list = sorted(workers.values(), key=lambda x: x["taxable_value"], reverse=True)
    for w in worker_list:
        for k in ("qty_sent", "qty_received", "qty_pending", "scrap", "taxable_value", "total_gst"):
            w[k] = round(w[k], 2)

    for k in gst:
        gst[k] = round(gst[k], 2)
    aging = {k: round(v, 4) for k, v in aging.items()}
    aging_value = {k: round(v, 2) for k, v in aging_value.items()}

    return {
        "date_from": date_from,
        "date_to": date_to,
        "summary": {
            "total_challans": len(challans),
            "total_job_workers": len(worker_list),
            "total_taxable_value": gst["taxable_value"],
            "total_gst": gst["total_gst"],
            "overdue_challans": overdue_total,
        },
        "job_workers": worker_list,
        "gst_summary": gst,
        "aging": [
            {"bucket": b, "quantity_pending": aging[b], "value_pending": aging_value[b]}
            for b in ("0-30", "31-90", "91-180", "180+")
        ],
        "challans": sorted(challan_rows, key=lambda r: r["date"] or "", reverse=True),
    }


@router.get("/reports/summary")
async def get_jobwork_report(
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD inclusive"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD inclusive"),
    user: dict = Depends(get_current_user),
):
    """Consolidated Job Work report: job-worker summary, GST summary, aging, per-challan rows."""
    _require_job_work(user)
    return await _build_jobwork_report(date_from, date_to)


@router.get("/reports/summary/pdf")
async def jobwork_report_pdf(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Printable PDF of the consolidated Job Work report."""
    _require_job_work(user)
    report = await _build_jobwork_report(date_from, date_to)
    pdf_bytes = build_jobwork_report_pdf(report)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="job-work-report.pdf"'},
    )


# ══════════════════════════════════════════════════════════════
# Dashboard
# ══════════════════════════════════════════════════════════════

@router.get("/dashboard")
async def get_dashboard(user: dict = Depends(get_current_user)):
    """Stat cards: Total Challans, Pending, Partial, Completed, Overdue,
    Material at Job Worker (value of pending qty across open challans)."""
    _require_job_work(user)
    challans = await db.job_work_challans.find({}, {"_id": 0}).to_list(5000)
    challan_ids = [c["id"] for c in challans]
    items_by_challan = await _fetch_challan_items_for_ids(challan_ids)
    received_by_item = await _received_by_challan_item(challan_ids)

    today = datetime.now(timezone.utc).date().isoformat()
    counts: dict[str, int | float] = {"total": len(challans), "draft": 0, "pending": 0, "partial": 0, "completed": 0, "overdue": 0}
    material_value = 0.0

    for c in challans:
        status = _normalize_status(c.get("status"))
        if status == "DRAFT":
            counts["draft"] += 1
        elif status == "PENDING":
            counts["pending"] += 1
        elif status == "PARTIAL":
            counts["partial"] += 1
        elif status == "COMPLETED":
            counts["completed"] += 1

        is_overdue = bool(c.get("due_date") and c["due_date"] < today and status not in _CLOSED_STATUSES)
        if is_overdue:
            counts["overdue"] += 1

        for item in items_by_challan.get(c["id"], []):
            sent = float(item.get("quantity", 0) or 0)
            recv = received_by_item.get(item["id"], 0.0)
            pending = max(0.0, sent - recv)
            material_value += pending * float(item.get("rate", 0) or 0)

    counts["material_at_job_worker_value"] = round(material_value, 2)
    return counts


# ══════════════════════════════════════════════════════════════
# ITC-04 Statement
# ══════════════════════════════════════════════════════════════

@router.get("/itc-04")
async def get_itc04(
    period: str = Query(..., description="Period in MMYYYY format, e.g. '062025'"),
    user: dict = Depends(get_current_user),
):
    """
    ITC-04 — Statement of goods dispatched to / received from job worker.
    Table 4: outward challans in the period. Table 5: inward receipts in the period.
    """
    _require_job_work(user)

    if len(period) != 6 or not period.isdigit():
        raise HTTPException(400, "period must be MMYYYY, e.g. '062025'")

    mm = period[:2]
    yyyy = period[2:]
    period_start = f"{yyyy}-{mm}-01"
    next_month = int(mm) % 12 + 1
    next_year = int(yyyy) + (1 if next_month == 1 else 0)
    period_end = f"{next_year}-{next_month:02d}-01"

    outward_challans = await db.job_work_challans.find(
        {"date": {"$gte": period_start, "$lt": period_end}}, {"_id": 0},
    ).sort("date", 1).to_list(2000)
    items_by_challan = await _fetch_challan_items_for_ids([c["id"] for c in outward_challans])

    table4 = []
    for c in outward_challans:
        c_items = items_by_challan.get(c["id"]) or c.get("items") or []
        for item in c_items:
            table4.append({
                "challan_number": c["challan_number"],
                "challan_date": c["date"],
                "due_date": c.get("due_date"),
                "job_worker_name": c.get("job_worker_name", ""),
                "job_worker_gstin": c.get("job_worker_gstin", ""),
                "nature": c.get("nature", "inputs"),
                "product_name": item.get("product_name", ""),
                "hsn_code": item.get("hsn_code", ""),
                "quantity_sent": float(item.get("quantity", 0) or 0),
                "unit": item.get("uom", "pcs"),
                "rate": float(item.get("rate", 0) or 0),
                "gst_rate": float(item.get("gst_rate", 0) or 0),
                "taxable_value": float(item.get("taxable_value", 0) or 0),
                "is_overdue": c.get("is_overdue", False),
                "challan_status": c.get("status", ""),
            })

    inward_receipts = await db.job_work_receipts.find(
        {"date": {"$gte": period_start, "$lt": period_end}}, {"_id": 0},
    ).sort("date", 1).to_list(2000)

    challan_ids = list({r["challan_id"] for r in inward_receipts if r.get("challan_id")})
    ref_challans: dict = {}
    if challan_ids:
        found = await db.job_work_challans.find({"id": {"$in": challan_ids}}, {"_id": 0}).to_list(len(challan_ids))
        ref_challans = {c["id"]: c for c in found}

    async with get_session() as session:
        receipt_ids = [r["id"] for r in inward_receipts]
        if receipt_ids:
            result = await session.execute(select(JobWorkReceiptItem).where(JobWorkReceiptItem.receipt_id.in_(receipt_ids)))
            items_by_receipt: dict = {}
            for row in result.scalars().all():
                items_by_receipt.setdefault(row.receipt_id, []).append(_row_dict(row))
        else:
            items_by_receipt = {}

    table5 = []
    for r in inward_receipts:
        ref = ref_challans.get(r.get("challan_id", ""), {})
        r_items = items_by_receipt.get(r["id"]) or r.get("items") or []
        for item in r_items:
            table5.append({
                "receipt_number": r.get("receipt_number", ""),
                "receipt_date": r.get("date", ""),
                "original_challan_number": ref.get("challan_number", ""),
                "original_challan_date": ref.get("date", ""),
                "job_worker_name": ref.get("job_worker_name", ""),
                "product_name": item.get("product_name", ""),
                "quantity_received": float(item.get("quantity_received", 0) or 0),
                "scrap_quantity": float(item.get("scrap_quantity", 0) or 0),
                "unit": "pcs",
            })

    total_sent = sum(row["quantity_sent"] for row in table4)
    total_received = sum(row["quantity_received"] for row in table5)
    total_scrap = sum(row["scrap_quantity"] for row in table5)
    total_taxable_value_sent = sum(row["taxable_value"] for row in table4)
    overdue_count = sum(1 for row in table4 if row["is_overdue"])

    return {
        "period": period,
        "period_label": f"{mm}/{yyyy}",
        "table4_outward_challans": table4,
        "table5_inward_receipts": table5,
        "summary": {
            "total_challans_issued": len(outward_challans),
            "total_receipts": len(inward_receipts),
            "total_quantity_sent": round(total_sent, 4),
            "total_quantity_received": round(total_received, 4),
            "total_scrap": round(total_scrap, 4),
            "total_taxable_value_sent": round(total_taxable_value_sent, 2),
            "overdue_challans": overdue_count,
        },
    }
