"""Pydantic v2 models for the Masters subsystem (accounting + inventory).

These are *input* models (what the API accepts). tenant_id, id, audit and
soft-delete fields are added by core.masters_crud, never supplied by the client.
Tree masters self-reference via a parent_*_id field.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ════════════════════════ Accounting Masters ════════════════════════

Nature = Literal["Asset", "Liability", "Income", "Expense"]


class Group(BaseModel):
    name: str
    parent_group_id: Optional[str] = None
    nature: Nature
    is_primary: bool = False
    affects_gross_profit: bool = False
    is_revenue: bool = False


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    parent_group_id: Optional[str] = None
    nature: Optional[Nature] = None
    is_primary: Optional[bool] = None
    affects_gross_profit: Optional[bool] = None
    is_revenue: Optional[bool] = None


class BankDetails(BaseModel):
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    bank_name: Optional[str] = None
    ifsc: Optional[str] = None
    branch: Optional[str] = None


class MailingAddress(BaseModel):
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: Optional[str] = "India"


GstRegType = Literal["Regular", "Composition", "Unregistered", "Consumer", "SEZ", "Overseas"]


class Ledger(BaseModel):
    name: str
    group_id: str
    coa_account_id: str  # links to chart_of_accounts.id — required so the voucher engine can post a real account_code
    opening_balance: float = 0.0
    dr_cr: Literal["Dr", "Cr"] = "Dr"
    gstin: Optional[str] = None
    pan: Optional[str] = None
    state: Optional[str] = None
    gst_registration_type: Optional[GstRegType] = None
    tds_applicable: bool = False
    product_id: Optional[str] = None
    product_name_manual: Optional[str] = None
    bank_details: Optional[BankDetails] = None
    mailing_address: Optional[MailingAddress] = None


class LedgerUpdate(BaseModel):
    name: Optional[str] = None
    group_id: Optional[str] = None
    coa_account_id: Optional[str] = None
    opening_balance: Optional[float] = None
    dr_cr: Optional[Literal["Dr", "Cr"]] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    state: Optional[str] = None
    gst_registration_type: Optional[GstRegType] = None
    tds_applicable: Optional[bool] = None
    product_id: Optional[str] = None
    product_name_manual: Optional[str] = None
    bank_details: Optional[BankDetails] = None
    mailing_address: Optional[MailingAddress] = None


class Currency(BaseModel):
    symbol: str
    iso_code: str
    formal_name: str
    decimal_places: int = Field(default=2, ge=0)
    is_base_currency: bool = False


class CurrencyUpdate(BaseModel):
    symbol: Optional[str] = None
    iso_code: Optional[str] = None
    formal_name: Optional[str] = None
    decimal_places: Optional[int] = Field(default=None, ge=0)
    is_base_currency: Optional[bool] = None


class RateOfExchange(BaseModel):
    currency_id: str
    effective_date: str  # ISO date
    std_rate: float
    selling_rate: Optional[float] = None
    buying_rate: Optional[float] = None


class RateOfExchangeUpdate(BaseModel):
    effective_date: Optional[str] = None
    std_rate: Optional[float] = None
    selling_rate: Optional[float] = None
    buying_rate: Optional[float] = None


# Tally-style voucher parent types.
VoucherParentType = Literal[
    "Payment", "Receipt", "Contra", "Journal",
    "Sales", "Purchase", "Credit Note", "Debit Note",
    "Stock Journal", "Physical Stock", "Delivery Note", "Receipt Note",
    "Sales Order", "Purchase Order", "Quotation", "Job Work",
    "Memorandum", "Reversing Journal", "Payroll", "Attendance",
]


class PrintConfig(BaseModel):
    title: Optional[str] = None
    copies: int = 1
    show_company_logo: bool = True
    show_gst_summary: bool = True


class VoucherType(BaseModel):
    name: str
    parent_type: VoucherParentType
    numbering_method: Literal["auto", "manual", "none"] = "auto"
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    restart_rule: Literal["never", "yearly", "monthly"] = "yearly"
    print_config: Optional[PrintConfig] = None
    use_effective_date: bool = False
    is_active: bool = True


class VoucherTypeUpdate(BaseModel):
    name: Optional[str] = None
    parent_type: Optional[VoucherParentType] = None
    numbering_method: Optional[Literal["auto", "manual", "none"]] = None
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    restart_rule: Optional[Literal["never", "yearly", "monthly"]] = None
    print_config: Optional[PrintConfig] = None
    use_effective_date: Optional[bool] = None
    is_active: Optional[bool] = None


# ════════════════════════ Inventory Masters ════════════════════════

class StockGroup(BaseModel):
    name: str
    parent_group_id: Optional[str] = None
    add_quantities: bool = True


class StockGroupUpdate(BaseModel):
    name: Optional[str] = None
    parent_group_id: Optional[str] = None
    add_quantities: Optional[bool] = None


class StockCategory(BaseModel):
    name: str
    parent_category_id: Optional[str] = None


class StockCategoryUpdate(BaseModel):
    name: Optional[str] = None
    parent_category_id: Optional[str] = None


class Unit(BaseModel):
    symbol: str
    formal_name: str
    decimal_places: int = 2
    type: Literal["simple", "compound"] = "simple"
    conversion_factor: Optional[float] = None  # for compound: how many base units
    base_unit_id: Optional[str] = None         # for compound: the base unit


class UnitUpdate(BaseModel):
    symbol: Optional[str] = None
    formal_name: Optional[str] = None
    decimal_places: Optional[int] = None
    type: Optional[Literal["simple", "compound"]] = None
    conversion_factor: Optional[float] = None
    base_unit_id: Optional[str] = None


class AlternateUnit(BaseModel):
    unit_id: str
    conversion_factor: float


ValuationMethod = Literal["FIFO", "Avg", "LIFO", "Std"]


class StockItem(BaseModel):
    name: str
    stock_group_id: Optional[str] = None
    category_id: Optional[str] = None
    base_unit_id: str
    alternate_unit: Optional[AlternateUnit] = None
    hsn_sac: Optional[str] = None
    gst_rate: float = 0.0
    opening_qty: float = 0.0
    opening_rate: float = 0.0
    valuation_method: ValuationMethod = "Avg"
    reorder_level: float = 0.0
    batch_enabled: bool = False
    serial_enabled: bool = False
    bom_id: Optional[str] = None


class StockItemUpdate(BaseModel):
    name: Optional[str] = None
    stock_group_id: Optional[str] = None
    category_id: Optional[str] = None
    base_unit_id: Optional[str] = None
    alternate_unit: Optional[AlternateUnit] = None
    hsn_sac: Optional[str] = None
    gst_rate: Optional[float] = None
    opening_qty: Optional[float] = None
    opening_rate: Optional[float] = None
    valuation_method: Optional[ValuationMethod] = None
    reorder_level: Optional[float] = None
    batch_enabled: Optional[bool] = None
    serial_enabled: Optional[bool] = None
    bom_id: Optional[str] = None


class LocationAddress(BaseModel):
    line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None


class Location(BaseModel):
    name: str
    parent_location_id: Optional[str] = None
    address: Optional[LocationAddress] = None
    allow_negative_stock: bool = False
    is_third_party: bool = False


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    parent_location_id: Optional[str] = None
    address: Optional[LocationAddress] = None
    allow_negative_stock: Optional[bool] = None
    is_third_party: Optional[bool] = None


# ════════════════════════ Statutory Masters (list) ════════════════════════

class GstRegistration(BaseModel):
    gstin: str
    registration_type: Literal["Regular", "Composition", "SEZ", "Unregistered"]
    state: Optional[str] = None
    periodicity: Literal["Monthly", "Quarterly"] = "Monthly"
    e_invoice_applicable: bool = False
    e_way_applicable: bool = False


class GstRegistrationUpdate(BaseModel):
    gstin: Optional[str] = None
    registration_type: Optional[Literal["Regular", "Composition", "SEZ", "Unregistered"]] = None
    state: Optional[str] = None
    periodicity: Optional[Literal["Monthly", "Quarterly"]] = None
    e_invoice_applicable: Optional[bool] = None
    e_way_applicable: Optional[bool] = None


class GstClassification(BaseModel):
    name: str
    hsn_sac: str
    taxability: Literal["Taxable", "Exempt", "Nil Rated", "Non-GST"] = "Taxable"
    igst_rate: float = 0.0
    cgst_rate: float = 0.0
    sgst_rate: float = 0.0
    cess_rate: float = 0.0
    is_reverse_charge: bool = False


class GstClassificationUpdate(BaseModel):
    name: Optional[str] = None
    hsn_sac: Optional[str] = None
    taxability: Optional[Literal["Taxable", "Exempt", "Nil Rated", "Non-GST"]] = None
    igst_rate: Optional[float] = None
    cgst_rate: Optional[float] = None
    sgst_rate: Optional[float] = None
    cess_rate: Optional[float] = None
    is_reverse_charge: Optional[bool] = None


class TdsNatureOfPayment(BaseModel):
    section_code: str           # e.g. "194C", "194J"
    description: str
    threshold: float = 0.0
    rate_with_pan: float = 0.0
    rate_without_pan: float = 20.0
    surcharge: float = 0.0
    cess: float = 0.0


class TdsNatureOfPaymentUpdate(BaseModel):
    section_code: Optional[str] = None
    description: Optional[str] = None
    threshold: Optional[float] = None
    rate_with_pan: Optional[float] = None
    rate_without_pan: Optional[float] = None
    surcharge: Optional[float] = None
    cess: Optional[float] = None


class TcsNatureOfGoods(BaseModel):
    nature_code: str            # e.g. "6CE"
    description: str
    rate: float = 0.0
    threshold: float = 0.0


class TcsNatureOfGoodsUpdate(BaseModel):
    nature_code: Optional[str] = None
    description: Optional[str] = None
    rate: Optional[float] = None
    threshold: Optional[float] = None


# ════════════════════════ Statutory Details (singleton per tenant) ════════════════════════
# One document per tenant. Get + upsert only (no list, no delete). All fields
# optional so a partial upsert is valid; the upsert merges onto the existing doc.

class CompanyGstDetails(BaseModel):
    gstin: Optional[str] = None
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None
    registration_type: Optional[Literal["Regular", "Composition", "SEZ", "Unregistered"]] = None
    state: Optional[str] = None
    state_code: Optional[str] = None
    periodicity: Optional[Literal["Monthly", "Quarterly"]] = None
    e_invoice_applicable: Optional[bool] = None
    e_way_applicable: Optional[bool] = None
    gst_username: Optional[str] = None


class TdsDetails(BaseModel):
    tan: Optional[str] = None
    deductor_type: Optional[str] = None
    responsible_person_name: Optional[str] = None
    responsible_person_pan: Optional[str] = None
    responsible_person_designation: Optional[str] = None


class TcsDetails(BaseModel):
    tan: Optional[str] = None
    collector_type: Optional[str] = None
    responsible_person_name: Optional[str] = None
    responsible_person_pan: Optional[str] = None
    responsible_person_designation: Optional[str] = None


class PanCinDetails(BaseModel):
    pan: Optional[str] = None
    cin: Optional[str] = None
    tan: Optional[str] = None
    company_type: Optional[str] = None
    incorporation_date: Optional[str] = None
