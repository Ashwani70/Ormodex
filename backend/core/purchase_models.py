"""Purchase v2 — Vendor master + PO → GRN → Bill → Return lifecycle.

Aligned to accrual accounting: a GRN moves stock (inward StockLedgerEntry); the
PurchaseBill creates the accounting voucher (Dr Inventory/Purchases + Input GST,
Cr Vendor). The chain PO → GRN → Bill is traceable but each link is optional so
small traders can raise a standalone GRN or Bill.
"""
from typing import List, Optional, Literal

from pydantic import BaseModel


# ───────────────────────── Vendor (supplier master) ─────────────────────────

class Vendor(BaseModel):
    name: str
    gstin: Optional[str] = None
    pan: Optional[str] = None
    billing_address: Optional[str] = None
    shipping_address: Optional[str] = None
    state_code: Optional[str] = None  # place-of-supply: IGST vs CGST+SGST
    payment_terms_days: int = 0
    opening_balance: float = 0.0
    email: Optional[str] = None
    phone: Optional[str] = None
    vendor_code: Optional[str] = None


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    billing_address: Optional[str] = None
    shipping_address: Optional[str] = None
    state_code: Optional[str] = None
    payment_terms_days: Optional[int] = None
    email: Optional[str] = None
    phone: Optional[str] = None


# ───────────────────────── Purchase Order ─────────────────────────

POStatus = Literal["DRAFT", "SENT", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED", "CANCELLED"]


class POLine(BaseModel):
    stock_item_id: str
    item_name: Optional[str] = None
    qty: float
    rate: float
    gst_rate: float = 18.0
    # Running tally of how much has been received against this line (server-managed).
    received_qty: float = 0.0


class PurchaseOrderV2(BaseModel):
    po_number: Optional[str] = None
    vendor_id: str
    vendor_name: Optional[str] = None
    expected_date: Optional[str] = None
    status: POStatus = "DRAFT"
    lines: List[POLine]
    notes: Optional[str] = None


# ───────────────────────── Goods Receipt Note ─────────────────────────

class GRNLine(BaseModel):
    stock_item_id: str
    item_name: Optional[str] = None
    po_line_index: Optional[int] = None  # links back to the PO line
    qty_received: float
    rate: float = 0.0
    gst_rate: float = 18.0
    batch_id: Optional[str] = None
    serial_id: Optional[str] = None
    expiry_date: Optional[str] = None


class GRNV2(BaseModel):
    grn_number: Optional[str] = None
    purchase_order_id: Optional[str] = None  # optional: standalone GRN allowed
    vendor_id: str
    vendor_name: Optional[str] = None
    godown_id: str
    received_date: Optional[str] = None
    lines: List[GRNLine]
    remarks: Optional[str] = None


# ───────────────────────── Purchase Bill (vendor invoice) ─────────────────────────

class BillLine(BaseModel):
    stock_item_id: str
    item_name: Optional[str] = None
    qty: float
    rate: float
    gst_rate: float = 18.0


class PurchaseBill(BaseModel):
    bill_number: Optional[str] = None          # internal number
    vendor_invoice_no: str                     # vendor's invoice number
    vendor_invoice_date: str
    vendor_id: str
    vendor_name: Optional[str] = None
    purchase_order_id: Optional[str] = None    # three-way-match linkage
    grn_ids: List[str] = []                    # one or more GRNs
    lines: List[BillLine]
    tds_rate: float = 0.0                       # % withheld, if applicable
    notes: Optional[str] = None
    payment_received: float = 0.0
    status: Literal["UNPAID", "PARTIAL", "PAID"] = "UNPAID"


# ───────────────────────── Purchase Return / Debit Note ─────────────────────────

class ReturnLine(BaseModel):
    stock_item_id: str
    item_name: Optional[str] = None
    qty: float          # positive; posted as outward
    rate: float = 0.0
    gst_rate: float = 18.0
    batch_id: Optional[str] = None


class PurchaseReturn(BaseModel):
    debit_note_number: Optional[str] = None
    vendor_id: str
    vendor_name: Optional[str] = None
    purchase_bill_id: Optional[str] = None
    grn_id: Optional[str] = None
    godown_id: str
    return_date: Optional[str] = None
    lines: List[ReturnLine]
    reason: Optional[str] = None
