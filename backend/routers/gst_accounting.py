"""GST Accounting Router.

Features:
- GSTIN validation (format check + mock GST portal lookup)
- GST record management (sales & purchase)
- GSTR-1 report generation
- GSTR-3B computation
- ITC (Input Tax Credit) tracking
- GST reconciliation (GSTR-2B vs books)
- HSN/SAC summary report
- GST liability dashboard
"""
import re
import uuid
import os
from datetime import datetime, date, timezone
from typing import Optional, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.accounting_models import GstRecord, GstinLookup, GstReconcileRecord
from core.auth_utils import get_current_user, require_admin
from core.db import db
from core import crypto_utils

router = APIRouter(prefix="/gst", tags=["GST"])

async def process_sandbox_gateway_logic(envelope: dict) -> dict:
    ek = os.getenv("GST_EK", "super-secret-gst-encryption-key-32chars")
    try:
        # Decrypt request
        payload = crypto_utils.decrypt_payload(envelope, ek)
    except Exception as e:
        raise ValueError(f"Decryption / HMAC validation failed: {str(e)}")
        
    action = envelope.get("action")
    
    if action == "validate-gstin":
        gstin = payload.get("gstin", "").strip().upper()
        res_payload = {
            "gstin": gstin,
            "is_valid": True,
            "state_code": gstin[:2],
            "state_name": STATE_CODES.get(gstin[:2], "Unknown"),
            "pan": gstin[2:12],
            "entity_type": gstin[12],
            "checksum": gstin[-1],
            "portal_status": "ACTIVE",
            "legal_name": "GravityOne ERP Private Limited",
            "trade_name": "GravityOne ERP",
            "address": "Plot No. 42, GIDC Industrial Estate, Pune, Maharashtra, 411062",
            "registration_date": "2020-04-01",
            "taxpayer_type": "Regular",
            "source": "GST_PORTAL"
        }
    elif action == "generate-einvoice":
        import hashlib
        inv_num = payload.get("invoice_number", "INV-MOCK")
        raw_str = f"{inv_num}-{datetime.now(timezone.utc).isoformat()}"
        irn = hashlib.sha256(raw_str.encode()).hexdigest()
        ack_no = f"1220{str(uuid.uuid4())[:8].upper()}"
        ack_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        qr_code = f"GSTIN:27AABCG1234F1Z5;INV:{inv_num};IRN:{irn};VAL:{payload.get('total', 0.0)}"
        
        res_payload = {
            "irn": irn,
            "ack_no": ack_no,
            "ack_date": ack_date,
            "einvoice_qr_code": qr_code,
            "einvoice_status": "GENERATED"
        }
    else:
        raise ValueError(f"Unknown GSP gateway action: {action}")
        
    # Encrypt response
    return crypto_utils.encrypt_payload(res_payload, action, ek)

async def _call_gsp_portal(envelope: dict) -> dict:
    portal_url = os.getenv("GST_PORTAL_URL", "")
    if not portal_url:
        return await process_sandbox_gateway_logic(envelope)
        
    headers = {"X-API-Key": os.getenv("GST_API_KEY", "mock-gst-api-key-123")}
    async with httpx.AsyncClient() as client:
        response = await client.post(portal_url, json=envelope, headers=headers, timeout=10.0)
        response.raise_for_status()
        return response.json()


@router.post("/sandbox/gateway")
async def sandbox_gateway(envelope: dict):
    """GSP Sandbox Gateway mimicking the official encrypted API."""
    try:
        return await process_sandbox_gateway_logic(envelope)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



GSTIN_PATTERN = re.compile(
    r"^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
)

STATE_CODES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana", "07": "Delhi",
    "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra & Nagar Haveli", "27": "Maharashtra",
    "28": "Andhra Pradesh (Old)", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman & Nicobar", "36": "Telangana", "37": "Andhra Pradesh",
}


def _require_gst(user: dict):
    if user.get("role") == "admin":
        return user
    perms = user.get("module_permissions", [])
    if "gst" not in perms and "accounting" not in perms:
        raise HTTPException(403, "GST module access required")
    return user


# ─────────────────────────── GSTIN Validation ───────────────────────────

@router.post("/validate-gstin")
async def validate_gstin(data: GstinLookup, user=Depends(get_current_user)):
    """Validate GSTIN format and return decoded info."""
    gstin = data.gstin.strip().upper()
    is_valid = bool(GSTIN_PATTERN.match(gstin))
    if not is_valid:
        return {
            "gstin": gstin,
            "is_valid": False,
            "error": "Invalid GSTIN format"
        }

    try:
        ek = os.getenv("GST_EK", "super-secret-gst-encryption-key-32chars")
        envelope = crypto_utils.encrypt_payload({"gstin": gstin}, "validate-gstin", ek)
        res_envelope = await _call_gsp_portal(envelope)
        result = crypto_utils.decrypt_payload(res_envelope, ek)
        # Extract PAN from characters 3 to 12 (indices 2 to 11)
        result["pan"] = gstin[2:12]
        return result
    except Exception as e:
        return {
            "gstin": gstin,
            "is_valid": True,
            "state_code": gstin[:2],
            "state_name": STATE_CODES.get(gstin[:2], "Unknown"),
            "pan": gstin[2:12],
            "entity_type": gstin[12],
            "checksum": gstin[-1],
            "portal_status": "ACTIVE",
            "legal_name": "GravityOne ERP Private Limited",
            "trade_name": "GravityOne ERP",
            "address": "Plot No. 42, GIDC Industrial Estate, Pune, Maharashtra, 411062",
            "registration_date": "2020-04-01",
            "taxpayer_type": "Regular",
            "source": "LOCAL_FALLBACK",
            "gateway_error": str(e)
        }



# ─────────────────────────── GST Records (Sales & Purchase) ───────────────────────────

@router.get("/records")
async def list_gst_records(
    gst_type: Optional[str] = None,
    return_period: Optional[str] = None,
    filing_status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    user=Depends(get_current_user)
):
    _require_gst(user)
    q: dict = {}
    if gst_type:
        q["gst_type"] = gst_type
    if return_period:
        q["return_period"] = return_period
    if filing_status:
        q["filing_status"] = filing_status
    if search:
        q["$or"] = [
            {"invoice_number": {"$regex": search, "$options": "i"}},
            {"party_name": {"$regex": search, "$options": "i"}},
            {"party_gstin": {"$regex": search, "$options": "i"}},
        ]
    total = await db.gst_records.count_documents(q)
    skip = (page - 1) * limit
    items = await db.gst_records.find(q, {"_id": 0}).sort("invoice_date", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "page": page, "items": items}


@router.post("/records")
async def create_gst_record(data: GstRecord, user=Depends(get_current_user)):
    _require_gst(user)
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_by"] = user["id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.gst_records.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/records/{record_id}")
async def get_gst_record(record_id: str, user=Depends(get_current_user)):
    _require_gst(user)
    r = await db.gst_records.find_one({"id": record_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "GST record not found")
    return r


@router.delete("/records/{record_id}")
async def delete_gst_record(record_id: str, user=Depends(require_admin)):
    await db.gst_records.delete_one({"id": record_id})
    return {"ok": True}


# ─────────────────────────── Auto-sync from Invoices ───────────────────────────

@router.post("/sync-from-invoices")
async def sync_gst_from_invoices(
    return_period: Optional[str] = None,
    user=Depends(get_current_user)
):
    """Pull sales invoices and create GST records for them."""
    _require_gst(user)
    q = {"status": {"$in": ["UNPAID", "PARTIAL", "PAID"]}}
    invoices = await db.invoices.find(q, {"_id": 0}).to_list(2000)

    created = 0
    for inv in invoices:
        existing = await db.gst_records.find_one({"linked_invoice_id": inv["id"]})
        if existing:
            continue

        # Compute GST totals from line items
        taxable = 0.0
        cgst = sgst = igst = 0.0
        for item in inv.get("items", []):
            qty = item.get("quantity", 0)
            price = item.get("unit_price", 0)
            rate = item.get("gst_rate", 18.0)
            line_total = qty * price
            taxable += line_total
            gst_amt = line_total * rate / 100
            # Assume domestic = CGST+SGST, export = IGST
            currency = inv.get("currency", "INR")
            if currency == "INR":
                cgst += gst_amt / 2
                sgst += gst_amt / 2
            else:
                igst += gst_amt

        period = return_period or date.today().strftime("%m%Y")
        record = {
            "id": str(uuid.uuid4()),
            "invoice_number": inv.get("invoice_number", ""),
            "invoice_date": inv.get("created_at", "")[:10],
            "party_name": inv.get("customer_name", ""),
            "taxable_amount": round(taxable, 2),
            "cgst": round(cgst, 2),
            "sgst": round(sgst, 2),
            "igst": round(igst, 2),
            "cess": 0.0,
            "total_amount": round(taxable + cgst + sgst + igst, 2),
            "gst_type": "SALES",
            "return_period": period,
            "filing_status": "PENDING",
            "source": "MANUAL",
            "linked_invoice_id": inv["id"],
            "created_by": user["id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.gst_records.insert_one(record)
        created += 1

    return {"synced": created, "return_period": return_period}


# ─────────────────────────── GSTR-1 ───────────────────────────

@router.get("/gstr1")
async def gstr1_report(
    return_period: str = Query(..., description="Format: MMYYYY e.g. 052024"),
    user=Depends(get_current_user)
):
    _require_gst(user)
    q = {"gst_type": "SALES", "return_period": return_period}
    records = await db.gst_records.find(q, {"_id": 0}).to_list(5000)

    b2b = [r for r in records if r.get("party_gstin")]
    b2c = [r for r in records if not r.get("party_gstin")]

    total_taxable = round(sum(r.get("taxable_amount", 0) for r in records), 2)
    total_cgst = round(sum(r.get("cgst", 0) for r in records), 2)
    total_sgst = round(sum(r.get("sgst", 0) for r in records), 2)
    total_igst = round(sum(r.get("igst", 0) for r in records), 2)
    total_tax = round(total_cgst + total_sgst + total_igst, 2)

    return {
        "return_period": return_period,
        "b2b_invoices": b2b,
        "b2c_invoices": b2c,
        "summary": {
            "total_invoices": len(records),
            "total_taxable": total_taxable,
            "total_cgst": total_cgst,
            "total_sgst": total_sgst,
            "total_igst": total_igst,
            "total_tax": total_tax,
            "grand_total": round(total_taxable + total_tax, 2),
        }
    }


# ─────────────────────────── GSTR-3B ───────────────────────────

@router.get("/gstr3b")
async def gstr3b_report(
    return_period: str = Query(...),
    user=Depends(get_current_user)
):
    _require_gst(user)
    # Outward supplies (Sales)
    sales_q = {"gst_type": "SALES", "return_period": return_period}
    sales = await db.gst_records.find(sales_q, {"_id": 0}).to_list(5000)

    # Inward supplies (Purchase - ITC)
    purchase_q = {"gst_type": "PURCHASE", "return_period": return_period}
    purchases = await db.gst_records.find(purchase_q, {"_id": 0}).to_list(5000)

    out_taxable = round(sum(r.get("taxable_amount", 0) for r in sales), 2)
    out_cgst = round(sum(r.get("cgst", 0) for r in sales), 2)
    out_sgst = round(sum(r.get("sgst", 0) for r in sales), 2)
    out_igst = round(sum(r.get("igst", 0) for r in sales), 2)
    out_tax = round(out_cgst + out_sgst + out_igst, 2)

    itc_cgst = round(sum(r.get("cgst", 0) for r in purchases), 2)
    itc_sgst = round(sum(r.get("sgst", 0) for r in purchases), 2)
    itc_igst = round(sum(r.get("igst", 0) for r in purchases), 2)
    itc_total = round(itc_cgst + itc_sgst + itc_igst, 2)

    net_cgst = round(out_cgst - itc_cgst, 2)
    net_sgst = round(out_sgst - itc_sgst, 2)
    net_igst = round(out_igst - itc_igst, 2)
    net_payable = round(net_cgst + net_sgst + net_igst, 2)

    return {
        "return_period": return_period,
        "outward_supplies": {
            "taxable_value": out_taxable,
            "cgst": out_cgst,
            "sgst": out_sgst,
            "igst": out_igst,
            "total_tax": out_tax,
        },
        "itc_available": {
            "cgst": itc_cgst,
            "sgst": itc_sgst,
            "igst": itc_igst,
            "total_itc": itc_total,
        },
        "net_tax_payable": {
            "cgst": max(0, net_cgst),
            "sgst": max(0, net_sgst),
            "igst": max(0, net_igst),
            "total": max(0, net_payable),
        },
    }


# ─────────────────────────── ITC (Input Tax Credit) Tracking ───────────────────────────

@router.get("/itc-summary")
async def itc_summary(
    return_period: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_gst(user)
    q = {"gst_type": "PURCHASE"}
    if return_period:
        q["return_period"] = return_period

    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": "$return_period",
            "total_cgst_itc": {"$sum": "$cgst"},
            "total_sgst_itc": {"$sum": "$sgst"},
            "total_igst_itc": {"$sum": "$igst"},
            "total_taxable": {"$sum": "$taxable_amount"},
            "invoice_count": {"$sum": 1},
        }},
        {"$sort": {"_id": -1}},
    ]
    results = await db.gst_records.aggregate(pipeline).to_list(24)
    return results


# ─────────────────────────── HSN/SAC Summary ───────────────────────────

@router.get("/hsn-summary")
async def hsn_summary(
    return_period: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_gst(user)
    q = {"gst_type": "SALES", "hsn_sac": {"$ne": None}}
    if return_period:
        q["return_period"] = return_period

    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": "$hsn_sac",
            "total_taxable": {"$sum": "$taxable_amount"},
            "total_cgst": {"$sum": "$cgst"},
            "total_sgst": {"$sum": "$sgst"},
            "total_igst": {"$sum": "$igst"},
            "invoice_count": {"$sum": 1},
        }},
        {"$sort": {"total_taxable": -1}},
    ]
    results = await db.gst_records.aggregate(pipeline).to_list(100)
    return results


# ─────────────────────────── GST Dashboard ───────────────────────────

@router.get("/dashboard")
async def gst_dashboard(user=Depends(get_current_user)):
    _require_gst(user)
    current_period = date.today().strftime("%m%Y")
    prev_periods = []
    today = date.today()
    for i in range(6):
        m = (today.month - i - 1) % 12 + 1
        y = today.year if today.month - i - 1 >= 0 else today.year - 1
        prev_periods.append(f"{m:02d}{y}")

    pipeline = [
        {"$match": {"return_period": {"$in": prev_periods}}},
        {"$group": {
            "_id": {"period": "$return_period", "type": "$gst_type"},
            "total_tax": {"$sum": {"$add": ["$cgst", "$sgst", "$igst"]}},
            "count": {"$sum": 1},
        }},
    ]
    monthly = await db.gst_records.aggregate(pipeline).to_list(100)

    # Current period summary
    total_sales_tax = 0.0
    total_itc = 0.0
    async for r in db.gst_records.find({"return_period": current_period}, {"_id": 0}):
        tax = r.get("cgst", 0) + r.get("sgst", 0) + r.get("igst", 0)
        if r.get("gst_type") == "SALES":
            total_sales_tax += tax
        else:
            total_itc += tax

    pending_filing = await db.gst_records.count_documents({"filing_status": "PENDING"})

    return {
        "current_period": current_period,
        "gst_liability": round(total_sales_tax, 2),
        "itc_available": round(total_itc, 2),
        "net_payable": round(max(0, total_sales_tax - total_itc), 2),
        "pending_invoices": pending_filing,
        "monthly_trend": monthly,
    }


# ─────────────────────────── GST Reconciliation (GSTR-2B) ───────────────────────────

@router.get("/reconciliation")
async def list_reconciliation(
    return_period: Optional[str] = None,
    match_status: Optional[str] = None,
    user=Depends(get_current_user)
):
    _require_gst(user)
    q: dict = {}
    if return_period:
        q["return_period"] = return_period
    if match_status:
        q["match_status"] = match_status
    items = await db.gst_reconciliation.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@router.post("/reconciliation/auto-match")
async def auto_reconcile(return_period: str, user=Depends(get_current_user)):
    """Auto-match purchase records in books with GSTR-2B portal data (mock)."""
    _require_gst(user)
    purchases = await db.gst_records.find(
        {"gst_type": "PURCHASE", "return_period": return_period}, {"_id": 0}
    ).to_list(2000)

    results = []
    for p in purchases:
        # In production, compare with actual GSTR-2B data from GSP
        # Mock: assume all records are "MATCHED"
        rec = {
            "id": str(uuid.uuid4()),
            "return_period": return_period,
            "purchase_record_id": p["id"],
            "portal_invoice_number": p.get("invoice_number"),
            "portal_gstin": p.get("party_gstin"),
            "portal_taxable_amount": p.get("taxable_amount"),
            "portal_tax": p.get("cgst", 0) + p.get("sgst", 0) + p.get("igst", 0),
            "match_status": "MATCHED",
            "remarks": "Auto-matched via mock reconciliation",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": user["id"],
        }
        await db.gst_reconciliation.update_one(
            {"purchase_record_id": p["id"], "return_period": return_period},
            {"$setOnInsert": rec},
            upsert=True
        )
        results.append(rec)

    return {"reconciled": len(results), "return_period": return_period}


# ─────────────────────────── TDS Management ───────────────────────────

TDS_SECTIONS = {
    "194A": "Interest (other than securities)",
    "194B": "Winnings from lottery / crossword puzzle",
    "194C": "Payment to contractor",
    "194D": "Insurance commission",
    "194G": "Commission on lottery tickets",
    "194H": "Commission or brokerage",
    "194I": "Rent",
    "194J": "Professional / technical services",
    "194Q": "Purchase of goods",
    "192":  "Salary",
    "194":  "Dividend",
}


class TdsEntry(BaseModel):
    entry_date: str
    party_name: str
    party_pan: Optional[str] = None
    party_id: Optional[str] = None      # customer/supplier id
    tds_section: str                    # e.g. "194J"
    base_amount: float                  # Amount on which TDS is calculated
    tds_rate: float                     # percentage e.g. 10
    tds_amount: float                   # base_amount * tds_rate / 100
    net_amount: float                   # base_amount - tds_amount
    return_period: str                  # MMYYYY
    challan_no: Optional[str] = None
    deposit_date: Optional[str] = None
    status: Literal["DEDUCTED", "DEPOSITED"] = "DEDUCTED"
    remarks: Optional[str] = None


class TcsEntry(BaseModel):
    entry_date: str
    party_name: str
    party_pan: Optional[str] = None
    party_id: Optional[str] = None
    tcs_section: str                    # e.g. "206C"
    base_amount: float
    tcs_rate: float
    tcs_amount: float
    gross_amount: float                 # base_amount + tcs_amount
    return_period: str
    challan_no: Optional[str] = None
    deposit_date: Optional[str] = None
    status: Literal["COLLECTED", "DEPOSITED"] = "COLLECTED"
    remarks: Optional[str] = None


@router.get("/tds-sections")
async def list_tds_sections(user=Depends(get_current_user)):
    """Return available TDS sections with descriptions."""
    _require_gst(user)
    return [{"code": k, "description": v} for k, v in TDS_SECTIONS.items()]


@router.get("/tds")
async def list_tds_entries(
    return_period: Optional[str] = None,
    tds_section: Optional[str] = None,
    status: Optional[str] = None,
    party_name: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    user=Depends(get_current_user)
):
    _require_gst(user)
    q: dict = {}
    if return_period:
        q["return_period"] = return_period
    if tds_section:
        q["tds_section"] = tds_section
    if status:
        q["status"] = status
    if party_name:
        q["party_name"] = {"$regex": party_name, "$options": "i"}
    total = await db.tds_entries.count_documents(q)
    skip = (page - 1) * limit
    items = await db.tds_entries.find(q, {"_id": 0}).sort("entry_date", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "page": page, "items": items}


@router.post("/tds")
async def create_tds_entry(data: TdsEntry, user=Depends(get_current_user)):
    _require_gst(user)
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_by"] = user["id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    # Auto-compute if not provided
    if not doc.get("tds_amount"):
        doc["tds_amount"] = round(doc["base_amount"] * doc["tds_rate"] / 100, 2)
    if not doc.get("net_amount"):
        doc["net_amount"] = round(doc["base_amount"] - doc["tds_amount"], 2)
    await db.tds_entries.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/tds/{entry_id}")
async def update_tds_entry(entry_id: str, data: dict, user=Depends(get_current_user)):
    _require_gst(user)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.tds_entries.update_one({"id": entry_id}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "TDS entry not found")
    return {"ok": True}


@router.delete("/tds/{entry_id}")
async def delete_tds_entry(entry_id: str, user=Depends(require_admin)):
    await db.tds_entries.delete_one({"id": entry_id})
    return {"ok": True}


@router.get("/tds-summary")
async def tds_summary(
    return_period: Optional[str] = None,
    user=Depends(get_current_user)
):
    """TDS challan summary — section-wise aggregation."""
    _require_gst(user)
    q: dict = {}
    if return_period:
        q["return_period"] = return_period
    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": {"section": "$tds_section", "status": "$status"},
            "total_base": {"$sum": "$base_amount"},
            "total_tds": {"$sum": "$tds_amount"},
            "total_net": {"$sum": "$net_amount"},
            "entry_count": {"$sum": 1},
        }},
        {"$sort": {"_id.section": 1}},
    ]
    results = await db.tds_entries.aggregate(pipeline).to_list(100)
    total_tds = await db.tds_entries.aggregate([
        {"$match": q},
        {"$group": {"_id": None, "total": {"$sum": "$tds_amount"}, "deposited": {"$sum": {"$cond": [{"$eq": ["$status", "DEPOSITED"]}, "$tds_amount", 0]}}}},
    ]).to_list(1)
    return {
        "return_period": return_period,
        "section_summary": results,
        "total_tds_deducted": total_tds[0]["total"] if total_tds else 0,
        "total_tds_deposited": total_tds[0]["deposited"] if total_tds else 0,
        "total_tds_pending": round((total_tds[0]["total"] - total_tds[0]["deposited"]) if total_tds else 0, 2),
    }


# ─────────────────────────── TCS Management ───────────────────────────

@router.get("/tcs")
async def list_tcs_entries(
    return_period: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    user=Depends(get_current_user)
):
    _require_gst(user)
    q: dict = {}
    if return_period:
        q["return_period"] = return_period
    if status:
        q["status"] = status
    total = await db.tcs_entries.count_documents(q)
    skip = (page - 1) * limit
    items = await db.tcs_entries.find(q, {"_id": 0}).sort("entry_date", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "page": page, "items": items}


@router.post("/tcs")
async def create_tcs_entry(data: TcsEntry, user=Depends(get_current_user)):
    _require_gst(user)
    doc = data.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_by"] = user["id"]
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    if not doc.get("tcs_amount"):
        doc["tcs_amount"] = round(doc["base_amount"] * doc["tcs_rate"] / 100, 2)
    if not doc.get("gross_amount"):
        doc["gross_amount"] = round(doc["base_amount"] + doc["tcs_amount"], 2)
    await db.tcs_entries.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/tcs/{entry_id}")
async def update_tcs_entry(entry_id: str, data: dict, user=Depends(get_current_user)):
    _require_gst(user)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.tcs_entries.update_one({"id": entry_id}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "TCS entry not found")
    return {"ok": True}


@router.delete("/tcs/{entry_id}")
async def delete_tcs_entry(entry_id: str, user=Depends(require_admin)):
    await db.tcs_entries.delete_one({"id": entry_id})
    return {"ok": True}


@router.get("/tcs-summary")
async def tcs_summary(return_period: Optional[str] = None, user=Depends(get_current_user)):
    _require_gst(user)
    q: dict = {}
    if return_period:
        q["return_period"] = return_period
    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": "$tcs_section",
            "total_base": {"$sum": "$base_amount"},
            "total_tcs": {"$sum": "$tcs_amount"},
            "total_gross": {"$sum": "$gross_amount"},
            "entry_count": {"$sum": 1},
        }},
    ]
    results = await db.tcs_entries.aggregate(pipeline).to_list(50)
    return {"return_period": return_period, "sections": results}
