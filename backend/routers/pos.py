"""POS — Point of Sale (Module J).

Fast billing counter that posts to the same sales/ledger engine. Built for a
keyboard/scanner-first, offline-capable (PWA) front end:

- `pos_sessions`: a cashier opens a terminal with opening cash, transacts, then
  closes with a counted cash figure → cash-drawer reconciliation.
- `pos_sales`: each sale carries a client-generated `client_uuid`. Sync is
  IDEMPOTENT — re-posting the same client_uuid returns the original sale instead
  of double-posting. This is what makes offline-queue + sync-on-reconnect safe.
- Payment split across cash / card / UPI must equal the sale total.
- GST receipt data is returned thermal-formatted (rate-wise CGST/SGST/IGST
  breakup, amount-in-words) for the printer.

Reuses inventory (stock decrement) and the Indian amount-in-words helper from
the banking module.

Collections: pos_sessions, pos_sales
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel
from datetime import date

from core.auth_utils import get_current_user, is_admin_role
from core.db import db
from core.utils import now_iso, new_id, next_doc_number
from routers.banking_pdc import amount_in_words

router = APIRouter(prefix="/pos", tags=["POS"])


def _require_pos(user: dict):
    if (is_admin_role(user.get("role")) or user.get("role") in ("accountant", "cashier")):
        return user
    if "pos" in user.get("module_permissions", []):
        return user
    raise HTTPException(403, "POS access required")


# ══════════════════════════════════════════════════════════════
# Models
# ══════════════════════════════════════════════════════════════

class OpenSession(BaseModel):
    terminal: str
    opening_cash: float = 0.0
    notes: Optional[str] = None


class CloseSession(BaseModel):
    counted_cash: float                  # physically counted at close
    notes: Optional[str] = None


class PaymentSplit(BaseModel):
    cash: float = 0.0
    card: float = 0.0
    upi: float = 0.0


class POSLine(BaseModel):
    item_id: str
    name: Optional[str] = None
    qty: float
    unit_price: float
    gst_rate: float = 18.0
    hsn_code: Optional[str] = None


class POSSale(BaseModel):
    client_uuid: str                     # client-generated; the idempotency key
    session_id: str
    lines: list[POSLine]
    payment: PaymentSplit
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    place_of_supply: Optional[str] = None
    is_interstate: bool = False          # decides IGST vs CGST+SGST
    created_at_client: Optional[str] = None   # when made offline


# ══════════════════════════════════════════════════════════════
# GST + total computation (pure, testable)
# ══════════════════════════════════════════════════════════════

def _compute_sale_totals(lines: list[dict], is_interstate: bool) -> dict:
    """
    Compute taxable value, rate-wise GST breakup and grand total.
    Returns per-rate buckets so the thermal receipt can print the GST summary.
    """
    taxable = 0.0
    gst_buckets: dict[float, dict] = {}   # rate → {taxable, cgst, sgst, igst}
    for ln in lines:
        line_taxable = round(ln["qty"] * ln["unit_price"], 2)
        taxable += line_taxable
        rate = ln.get("gst_rate", 0.0)
        bucket = gst_buckets.setdefault(rate, {"taxable": 0.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0})
        bucket["taxable"] = round(bucket["taxable"] + line_taxable, 2)
        gst_amt = round(line_taxable * rate / 100.0, 2)
        if is_interstate:
            bucket["igst"] = round(bucket["igst"] + gst_amt, 2)
        else:
            bucket["cgst"] = round(bucket["cgst"] + gst_amt / 2, 2)
            bucket["sgst"] = round(bucket["sgst"] + gst_amt / 2, 2)

    total_cgst = round(sum(b["cgst"] for b in gst_buckets.values()), 2)
    total_sgst = round(sum(b["sgst"] for b in gst_buckets.values()), 2)
    total_igst = round(sum(b["igst"] for b in gst_buckets.values()), 2)
    taxable = round(taxable, 2)
    grand_total = round(taxable + total_cgst + total_sgst + total_igst, 2)
    return {
        "taxable_value": taxable,
        "cgst": total_cgst,
        "sgst": total_sgst,
        "igst": total_igst,
        "total_gst": round(total_cgst + total_sgst + total_igst, 2),
        "grand_total": grand_total,
        "gst_breakup": [
            {"rate": r, **b} for r, b in sorted(gst_buckets.items())
        ],
    }


def _validate_payment(payment: dict, grand_total: float) -> dict:
    """Payment split must cover the grand total. Returns tender/change."""
    tendered = round(payment.get("cash", 0) + payment.get("card", 0) + payment.get("upi", 0), 2)
    if tendered + 0.01 < grand_total:
        raise HTTPException(400, f"Payment {tendered} is less than total {grand_total}")
    # Change only ever comes back in cash
    change = round(tendered - grand_total, 2)
    return {"tendered": tendered, "change": change}


def _round_half_up(x: float) -> float:
    return round(x, 2)


# ══════════════════════════════════════════════════════════════
# Sessions
# ══════════════════════════════════════════════════════════════

@router.post("/sessions")
async def open_session(payload: OpenSession, user: dict = Depends(get_current_user)):
    _require_pos(user)
    # one open session per terminal
    existing = await db.pos_sessions.find_one(
        {"terminal": payload.terminal, "status": "open"}, {"_id": 0})
    if existing:
        raise HTTPException(400, f"Terminal '{payload.terminal}' already has an open session")
    doc = {
        "id": new_id(),
        "session_no": await next_doc_number("POS", "pos_sessions"),
        "terminal": payload.terminal,
        "cashier_id": user["id"],
        "cashier_name": user.get("name", user.get("email", "")),
        "opening_cash": payload.opening_cash,
        "status": "open",
        "opened_at": now_iso(),
        "notes": payload.notes,
    }
    await db.pos_sessions.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/sessions")
async def list_sessions(status: Optional[str] = None, terminal: Optional[str] = None,
                        user: dict = Depends(get_current_user)):
    _require_pos(user)
    filt = {}
    if status:
        filt["status"] = status
    if terminal:
        filt["terminal"] = terminal
    return await db.pos_sessions.find(filt, {"_id": 0}).sort("opened_at", -1).to_list(500)


async def _session_cash_summary(session_id: str) -> dict:
    """Expected cash = opening + cash receipts − cash change given."""
    session = await db.pos_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(404, "Session not found")
    sales = await db.pos_sales.find({"session_id": session_id, "voided": {"$ne": True}}, {"_id": 0}).to_list(5000)
    cash_in = round(sum(s["payment"].get("cash", 0) for s in sales), 2)
    change_out = round(sum(s.get("change", 0) for s in sales), 2)
    card_total = round(sum(s["payment"].get("card", 0) for s in sales), 2)
    upi_total = round(sum(s["payment"].get("upi", 0) for s in sales), 2)
    expected_cash = round(session.get("opening_cash", 0) + cash_in - change_out, 2)
    return {
        "opening_cash": session.get("opening_cash", 0),
        "cash_sales": cash_in,
        "change_given": change_out,
        "card_total": card_total,
        "upi_total": upi_total,
        "expected_cash": expected_cash,
        "sales_count": len(sales),
        "gross_sales": round(sum(s.get("grand_total", 0) for s in sales), 2),
    }


@router.get("/sessions/{session_id}/summary")
async def session_summary(session_id: str, user: dict = Depends(get_current_user)):
    _require_pos(user)
    return await _session_cash_summary(session_id)


@router.post("/sessions/{session_id}/close")
async def close_session(session_id: str, payload: CloseSession, user: dict = Depends(get_current_user)):
    """Close a session and reconcile the cash drawer (counted vs expected)."""
    _require_pos(user)
    session = await db.pos_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] != "open":
        raise HTTPException(400, "Session already closed")

    summary = await _session_cash_summary(session_id)
    variance = round(payload.counted_cash - summary["expected_cash"], 2)

    recon = {
        **summary,
        "counted_cash": payload.counted_cash,
        "variance": variance,                       # +over / −short
        "status": "balanced" if abs(variance) < 0.01 else ("over" if variance > 0 else "short"),
    }
    await db.pos_sessions.update_one(
        {"id": session_id},
        {"$set": {"status": "closed", "closed_at": now_iso(), "closed_by": user["id"],
                  "reconciliation": recon, "close_notes": payload.notes}},
    )
    return {"session_id": session_id, "reconciliation": recon}


# ══════════════════════════════════════════════════════════════
# Sales — idempotent (offline-sync-safe)
# ══════════════════════════════════════════════════════════════

@router.post("/sales")
async def create_sale(payload: POSSale, user: dict = Depends(get_current_user)):
    """
    Post a POS sale. IDEMPOTENT on client_uuid: a replayed offline sale returns
    the original record (no double-post, no double stock decrement).
    """
    _require_pos(user)

    # Idempotency: if this client_uuid already posted, return it unchanged.
    existing = await db.pos_sales.find_one({"client_uuid": payload.client_uuid}, {"_id": 0})
    if existing:
        return {"duplicate": True, "sale": existing}

    session = await db.pos_sessions.find_one({"id": payload.session_id}, {"_id": 0})
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] != "open":
        raise HTTPException(400, "Cannot bill against a closed session")
    if not payload.lines:
        raise HTTPException(400, "Sale has no lines")

    lines = [ln.model_dump() for ln in payload.lines]
    totals = _compute_sale_totals(lines, payload.is_interstate)
    pay = _validate_payment(payload.payment.model_dump(), totals["grand_total"])

    sale = {
        "id": new_id(),
        "client_uuid": payload.client_uuid,
        "receipt_no": await next_doc_number("RCP", "pos_sales"),
        "session_id": payload.session_id,
        "terminal": session["terminal"],
        "cashier_id": user["id"],
        "customer_id": payload.customer_id,
        "customer_name": payload.customer_name,
        "place_of_supply": payload.place_of_supply,
        "is_interstate": payload.is_interstate,
        "lines": lines,
        "payment": payload.payment.model_dump(),
        "tendered": pay["tendered"],
        "change": pay["change"],
        **totals,
        "created_at": now_iso(),
        "created_at_client": payload.created_at_client,
        "voided": False,
    }

    # Insert with client_uuid uniqueness guarding against a race (two replays at once).
    try:
        await db.pos_sales.insert_one(sale)
    except Exception:
        # duplicate key on client_uuid → the other replay won; return that one.
        again = await db.pos_sales.find_one({"client_uuid": payload.client_uuid}, {"_id": 0})
        if again:
            return {"duplicate": True, "sale": again}
        raise

    # Decrement stock for each line (best-effort; POS reuses inventory).
    for ln in lines:
        await db.products.update_one({"id": ln["item_id"]}, {"$inc": {"quantity": -ln["qty"]}})

    # Post a lightweight sales voucher to the ledger engine.
    voucher = {
        "id": new_id(),
        "voucher_number": sale["receipt_no"],
        "voucher_type": "RECEIPT",
        "date": date.today().isoformat(),
        "party_type": "CUSTOMER",
        "party_id": payload.customer_id,
        "party_name": payload.customer_name or "Walk-in",
        "amount": totals["grand_total"],
        "payment_mode": "CASH" if payload.payment.cash >= totals["grand_total"] else "OTHER",
        "narration": f"POS sale {sale['receipt_no']} @ {session['terminal']}",
        "status": "APPROVED",
        "source": "pos",
        "pos_sale_id": sale["id"],
        "created_at": now_iso(),
    }
    await db.vouchers.insert_one(voucher)
    await db.pos_sales.update_one({"id": sale["id"]}, {"$set": {"voucher_id": voucher["id"]}})
    sale["voucher_id"] = voucher["id"]

    sale.pop("_id", None)
    return {"duplicate": False, "sale": sale, "receipt": _build_receipt(sale, session)}


@router.post("/sales/sync")
async def sync_sales(payload: list[POSSale], user: dict = Depends(get_current_user)):
    """
    Bulk sync of offline-queued sales. Each is processed idempotently; the
    response reports per-sale outcome so the client can clear its local queue.
    """
    _require_pos(user)
    results = []
    for sale in payload:
        try:
            r = await create_sale(sale, user)  # reuses idempotent path
            sale_data = r.get("sale")
            sale_id = sale_data.get("id") if isinstance(sale_data, dict) else ""
            results.append({"client_uuid": sale.client_uuid,
                            "status": "duplicate" if r.get("duplicate") else "posted",
                            "sale_id": sale_id})
        except HTTPException as e:
            results.append({"client_uuid": sale.client_uuid, "status": "error", "detail": e.detail})
    posted = sum(1 for r in results if r["status"] == "posted")
    dupes = sum(1 for r in results if r["status"] == "duplicate")
    return {"synced": len(results), "posted": posted, "duplicates": dupes, "results": results}


# ══════════════════════════════════════════════════════════════
# Thermal GST receipt
# ══════════════════════════════════════════════════════════════

def _build_receipt(sale: dict, session: dict) -> dict:
    """Thermal-formatted, GST-compliant receipt payload (40-col friendly)."""
    return {
        "receipt_no": sale["receipt_no"],
        "date": sale["created_at"][:19].replace("T", " "),
        "terminal": sale["terminal"],
        "cashier": session.get("cashier_name"),
        "customer": sale.get("customer_name") or "Walk-in",
        "lines": [
            {"name": ln.get("name") or ln["item_id"], "qty": ln["qty"],
             "rate": ln["unit_price"], "amount": round(ln["qty"] * ln["unit_price"], 2),
             "gst_rate": ln.get("gst_rate", 0), "hsn": ln.get("hsn_code")}
            for ln in sale["lines"]
        ],
        "taxable_value": sale["taxable_value"],
        "gst_breakup": sale["gst_breakup"],
        "cgst": sale["cgst"], "sgst": sale["sgst"], "igst": sale["igst"],
        "grand_total": sale["grand_total"],
        "amount_in_words": amount_in_words(sale["grand_total"]),
        "payment": sale["payment"],
        "tendered": sale["tendered"],
        "change": sale["change"],
        "footer": "Thank you! Goods once sold are subject to store policy.",
    }


@router.get("/sales/{sale_id}/receipt")
async def get_receipt(sale_id: str, user: dict = Depends(get_current_user)):
    _require_pos(user)
    sale = await db.pos_sales.find_one({"id": sale_id}, {"_id": 0})
    if not sale:
        raise HTTPException(404, "Sale not found")
    session = await db.pos_sessions.find_one({"id": sale["session_id"]}, {"_id": 0}) or {}
    return _build_receipt(sale, session)


@router.get("/sales")
async def list_sales(session_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_pos(user)
    filt = {"session_id": session_id} if session_id else {}
    return await db.pos_sales.find(filt, {"_id": 0}).sort("created_at", -1).to_list(2000)
