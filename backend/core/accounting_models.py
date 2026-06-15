"""Pydantic models for the Accounting & AI add-on module."""
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


# ─────────────────────────── Fiscal Year ───────────────────────────

class FiscalYear(BaseModel):
    name: str          # e.g. "2024-25"
    start_date: str    # ISO date
    end_date: str
    is_active: bool = True
    is_locked: bool = False


class FiscalYearUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_locked: Optional[bool] = None


# ─────────────────────────── Chart of Accounts ───────────────────────────

class AccountType(str, Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class ChartOfAccount(BaseModel):
    code: str            # e.g. "1001"
    name: str
    account_type: AccountType
    parent_code: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    opening_balance: float = 0.0
    currency: str = "INR"
    tags: List[str] = []


class ChartOfAccountUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    opening_balance: Optional[float] = None
    tags: Optional[List[str]] = None


# ─────────────────────────── Journal Entry ───────────────────────────

class JournalLine(BaseModel):
    account_code: str
    account_name: str
    debit: float = 0.0
    credit: float = 0.0
    narration: Optional[str] = None
    cost_center: Optional[str] = None


class JournalEntry(BaseModel):
    entry_number: Optional[str] = None
    date: str
    narration: str
    lines: List[JournalLine]
    status: Literal["DRAFT", "APPROVED", "POSTED"] = "DRAFT"
    fiscal_year: Optional[str] = None
    reference: Optional[str] = None
    tags: List[str] = []


class JournalEntryUpdate(BaseModel):
    status: Optional[Literal["DRAFT", "APPROVED", "POSTED"]] = None
    narration: Optional[str] = None


# ─────────────────────────── Vouchers ───────────────────────────

class VoucherType(str, Enum):
    RECEIPT = "RECEIPT"
    PAYMENT = "PAYMENT"
    CONTRA = "CONTRA"
    JOURNAL = "JOURNAL"
    DEBIT_NOTE = "DEBIT_NOTE"
    CREDIT_NOTE = "CREDIT_NOTE"
    EXPENSE = "EXPENSE"


class VoucherLine(BaseModel):
    account_code: str
    account_name: str
    amount: float
    narration: Optional[str] = None


class Voucher(BaseModel):
    voucher_number: Optional[str] = None
    voucher_type: VoucherType
    date: str
    party_type: Optional[Literal["CUSTOMER", "SUPPLIER", "BANK", "CASH"]] = None
    party_id: Optional[str] = None
    party_name: Optional[str] = None
    amount: float
    narration: Optional[str] = None
    payment_mode: Optional[Literal["CASH", "CHEQUE", "NEFT", "RTGS", "UPI", "OTHER"]] = None
    cheque_number: Optional[str] = None
    cheque_date: Optional[str] = None
    bank_account: Optional[str] = None
    lines: List[VoucherLine] = []
    status: Literal["DRAFT", "PENDING", "APPROVED", "CANCELLED"] = "DRAFT"
    journal_entry_id: Optional[str] = None
    reference_doc: Optional[str] = None  # e.g. Invoice number


class VoucherUpdate(BaseModel):
    status: Optional[Literal["DRAFT", "PENDING", "APPROVED", "CANCELLED"]] = None
    narration: Optional[str] = None


# ─────────────────────────── Bank & Cash ───────────────────────────

class BankAccount(BaseModel):
    name: str              # e.g. "HDFC Current A/C"
    account_number: str
    bank_name: str
    branch: Optional[str] = None
    ifsc: Optional[str] = None
    account_type: Literal["CURRENT", "SAVINGS", "CC", "OD"] = "CURRENT"
    opening_balance: float = 0.0
    currency: str = "INR"
    is_active: bool = True


class BankEntry(BaseModel):
    bank_account_id: str
    date: str
    entry_type: Literal["DEBIT", "CREDIT"]
    amount: float
    description: str
    reference: Optional[str] = None        # cheque no / UTR
    party_name: Optional[str] = None
    is_reconciled: bool = False
    voucher_id: Optional[str] = None


class BankStatementLine(BaseModel):
    """Imported bank statement row for reconciliation."""
    bank_account_id: str
    date: str
    description: str
    debit: float = 0.0
    credit: float = 0.0
    balance: Optional[float] = None
    reference: Optional[str] = None
    is_matched: bool = False
    matched_entry_id: Optional[str] = None


class ReconcileMatch(BaseModel):
    statement_line_id: str
    bank_entry_id: str


# ─────────────────────────── Expense Management ───────────────────────────

class ExpenseCategory(BaseModel):
    name: str
    description: Optional[str] = None
    budget_monthly: Optional[float] = None
    gl_account_code: Optional[str] = None


class ExpenseEntry(BaseModel):
    date: str
    category: str
    department: Optional[str] = None
    amount: float
    description: str
    paid_by: Optional[str] = None
    payment_mode: Optional[Literal["CASH", "CHEQUE", "NEFT", "UPI", "CARD"]] = "CASH"
    status: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"
    approved_by: Optional[str] = None
    receipt_url: Optional[str] = None
    is_recurring: bool = False
    recurrence: Optional[Literal["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY"]] = None
    gst_amount: float = 0.0
    notes: Optional[str] = None


class ExpenseUpdate(BaseModel):
    status: Optional[Literal["PENDING", "APPROVED", "REJECTED"]] = None
    notes: Optional[str] = None


# ─────────────────────────── GST Records ───────────────────────────

class GstRecord(BaseModel):
    invoice_number: str
    invoice_date: str
    party_name: str
    party_gstin: Optional[str] = None
    our_gstin: Optional[str] = None
    place_of_supply: Optional[str] = None
    taxable_amount: float = 0.0
    cgst: float = 0.0
    sgst: float = 0.0
    igst: float = 0.0
    cess: float = 0.0
    total_amount: float = 0.0
    hsn_sac: Optional[str] = None
    gst_type: Literal["SALES", "PURCHASE"] = "SALES"
    return_period: Optional[str] = None   # e.g. "052024" = May 2024
    filing_status: Optional[Literal["FILED", "PENDING", "MISMATCH"]] = "PENDING"
    source: Literal["MANUAL", "OCR", "GST_PORTAL"] = "MANUAL"
    linked_invoice_id: Optional[str] = None


class GstReconcileRecord(BaseModel):
    """GSTR-2B vs Purchase Invoice match."""
    purchase_record_id: Optional[str] = None
    portal_invoice_number: Optional[str] = None
    portal_gstin: Optional[str] = None
    portal_taxable_amount: Optional[float] = None
    portal_tax: Optional[float] = None
    match_status: Literal["MATCHED", "MISMATCH", "MISSING_IN_PORTAL", "MISSING_IN_BOOKS"] = "MISSING_IN_BOOKS"
    remarks: Optional[str] = None


class GstinLookup(BaseModel):
    gstin: str


# ─────────────────────────── OCR Documents ───────────────────────────

class OcrDocument(BaseModel):
    file_url: str
    file_name: str
    doc_type: Optional[Literal["INVOICE", "RECEIPT", "BANK_STATEMENT", "GST_BILL", "CHALLAN", "OTHER"]] = None
    extracted_data: Optional[Dict[str, Any]] = None
    status: Literal["PENDING", "PROCESSED", "FAILED"] = "PENDING"
    entry_created: Optional[str] = None   # ID of auto-created entry
    confidence_score: Optional[float] = None


# ─────────────────────────── AI Chat ───────────────────────────

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    context: Optional[str] = None   # page context e.g. "journal_entry"


class VendorCompareRequest(BaseModel):
    product_name: str
    supplier_ids: Optional[List[str]] = None


# ─────────────────────────── Module Permissions ───────────────────────────

ALL_MODULES = [
    "accounting", "vouchers", "ledger", "gst", "cash_bank",
    "expenses", "mis_reports", "ai_tools", "inventory",
    "purchase", "sales", "hr", "payroll", "reports",
]


class ModulePermissionUpdate(BaseModel):
    module_permissions: List[str]
