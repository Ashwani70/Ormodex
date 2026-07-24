"""Unified Voucher document — one shape for every transaction type.

A single `vouchers_v2` collection holds all parent types (accounting, inventory,
order, payroll). Posting behaviour is decided by `core.voucher_engine` based on
`parent_type`; only an *approved* voucher posts to books/stock (maker-checker).

This is the input/transport model. tenant_id, voucher_no, status transitions,
audit and posting refs are managed by the engine, not supplied by the client.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel


# Every parent_type the engine knows about (catalog lives in voucher_engine).
ParentType = Literal[
    # Accounting
    "contra", "payment", "receipt", "journal", "sales", "purchase",
    "credit_note", "debit_note", "export_sales", "purchase_import",
    "service_invoice", "purchase_expenses", "job_work_expenses",
    "reversing_journal", "memorandum",
    # Inventory
    "delivery_note", "receipt_note", "rejections_in", "rejections_out",
    "physical_stock", "stock_journal", "material_in", "material_out",
    "job_work_challan", "job_work_material_inward", "non_returnable_gate_pass",
    "stock_transfer_interunit", "stock_transfer_material_interunit",
    # Order
    "purchase_order", "sales_order", "job_work_in_order", "job_work_out_order",
    # Payroll
    "attendance", "payroll",
]

VoucherStatus = Literal["draft", "pending", "approved", "cancelled"]


class GstDetails(BaseModel):
    taxable_value: float = 0.0
    igst: float = 0.0
    cgst: float = 0.0
    sgst: float = 0.0
    cess: float = 0.0
    gst_rate: float = 0.0
    hsn_sac: Optional[str] = None
    reverse_charge: bool = False
    place_of_supply: Optional[str] = None


class AccountingLine(BaseModel):
    ledger_id: str
    dr_cr: Literal["Dr", "Cr"]
    amount: float
    gst_details: Optional[GstDetails] = None
    narration: Optional[str] = None
    cost_center_id: Optional[str] = None


class InventoryLine(BaseModel):
    stock_item_id: str
    location_id: Optional[str] = None       # source godown
    to_location_id: Optional[str] = None    # destination godown (transfers)
    qty: float
    rate: float = 0.0
    amount: float = 0.0
    role: Optional[str] = None              # "consume" | "produce" (stock_journal)
    batch: Optional[str] = None
    serial: Optional[str] = None
    tracking_ref: Optional[str] = None


class VoucherLink(BaseModel):
    ref_voucher_id: str
    ref_type: str  # e.g. "sales_order", "delivery_note"


class TdsBlock(BaseModel):
    section_code: Optional[str] = None
    rate: float = 0.0
    amount: float = 0.0
    base_amount: Optional[float] = None


class TcsBlock(BaseModel):
    nature_code: Optional[str] = None
    rate: float = 0.0
    amount: float = 0.0


class EwayBlock(BaseModel):
    eway_bill_no: Optional[str] = None
    valid_until: Optional[str] = None
    distance_km: Optional[float] = None


class EinvoiceBlock(BaseModel):
    irn: Optional[str] = None
    ack_no: Optional[str] = None
    ack_date: Optional[str] = None
    signed_qr: Optional[str] = None


class StatutoryBlock(BaseModel):
    gst: Optional[GstDetails] = None
    tds: Optional[TdsBlock] = None
    tcs: Optional[TcsBlock] = None
    eway: Optional[EwayBlock] = None
    einvoice: Optional[EinvoiceBlock] = None
    # Free-form extras for type-specific fields (shipping bill, BOE, LUT, etc.).
    extra: Optional[dict] = None


class Attachment(BaseModel):
    name: str
    path: str
    content_type: Optional[str] = None


class VoucherCreate(BaseModel):
    voucher_type_id: Optional[str] = None       # FK to master_voucher_types (optional)
    parent_type: ParentType
    voucher_no: Optional[str] = None            # supplied only when numbering_method == "manual"
    date: str
    effective_date: Optional[str] = None
    narration: Optional[str] = None
    reference_no: Optional[str] = None
    party_id: Optional[str] = None
    accounting_lines: List[AccountingLine] = []
    inventory_lines: List[InventoryLine] = []
    links: List[VoucherLink] = []
    statutory: Optional[StatutoryBlock] = None
    attachments: List[Attachment] = []


class VoucherUpdate(BaseModel):
    date: Optional[str] = None
    effective_date: Optional[str] = None
    narration: Optional[str] = None
    reference_no: Optional[str] = None
    party_id: Optional[str] = None
    accounting_lines: Optional[List[AccountingLine]] = None
    inventory_lines: Optional[List[InventoryLine]] = None
    links: Optional[List[VoucherLink]] = None
    statutory: Optional[StatutoryBlock] = None
    attachments: Optional[List[Attachment]] = None
