"""Pydantic models shared across routers."""
from typing import List, Optional, Literal

from pydantic import BaseModel, EmailStr, field_validator

# 10 spec roles + "employee" kept valid for the 9 existing users with that role
# (not bulk-relabeled — see alembic/versions/015_auth_hardening.py). Matches
# the DB CHECK constraint chk_users_role added by that migration exactly.
UserRole = Literal[
    "super_admin", "admin", "manager", "accountant", "purchase", "sales",
    "store", "production", "hr", "viewer", "employee",
]


# ---------------- Auth & Users ----------------
class LoginIn(BaseModel):
    # Plain str, not EmailStr: this field accepts a username too (see
    # _find_user_by_identifier in routers/auth.py) — EmailStr would 422-reject
    # any non-email username before that lookup ever ran.
    email: str
    password: str
    remember_me: bool = False
    company_code: Optional[str] = None
    captcha_token: Optional[str] = None
    captcha_answer: Optional[str] = None


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    username: Optional[str] = None
    phone: Optional[str] = None
    role: UserRole = "employee"
    permissions: Optional[dict] = None
    module_permissions: Optional[List[str]] = None
    password: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        from core.password_policy import validate_password
        return validate_password(v)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[UserRole] = None
    module_permissions: Optional[List[str]] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            from core.password_policy import validate_password
            return validate_password(v)
        return v



# ---------------- Inventory ----------------
class Warehouse(BaseModel):
    name: str
    location: str
    manager: Optional[str] = None


class Product(BaseModel):
    name: str
    sku: str
    category: str
    category_id: Optional[str] = None
    description: Optional[str] = None
    unit: str = "Nos"
    cost_price: float = 0
    selling_price: float = 0
    quantity: float = 0
    stock_quantity: Optional[float] = None
    low_stock_threshold: float = 10
    warehouse_id: Optional[str] = None
    image_url: Optional[str] = None
    image_path: Optional[str] = None
    hsn_code: Optional[str] = None
    gst_rate: float = 18.0



# ---------------- Purchase ----------------
class Supplier(BaseModel):
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    registration_type: Optional[Literal["Regular", "Composition", "Consumer", "Unregistered"]] = "Regular"
    pan_number: Optional[str] = None
    state_code: Optional[str] = None
    party_type: Optional[Literal["CUSTOMER", "SUPPLIER", "TRANSPORTER", "JOB_WORKER"]] = "SUPPLIER"
    registration_date: Optional[str] = None
    gst_status: Optional[str] = None
    # Extended fields
    vendor_code: Optional[str] = None
    vendor_rating: Optional[float] = 0.0
    payment_terms: Optional[str] = None
    pan_holder_name: Optional[str] = None
    pan_type: Optional[str] = None
    pan_status: Optional[str] = None
    aadhaar_number: Optional[str] = None
    aadhaar_holder_name: Optional[str] = None
    aadhaar_status: Optional[str] = None



class POItem(BaseModel):
    product_id: Optional[str] = None
    product_name: str
    description: Optional[str] = None
    sku: Optional[str] = ""
    quantity: float
    unit: Optional[str] = None
    uom: Optional[str] = None
    unit_price: float
    gst_rate: float = 18.0
    hsn_code: Optional[str] = None


class PurchaseOrder(BaseModel):
    po_number: Optional[str] = None
    supplier_id: str
    supplier_name: Optional[str] = None
    items: List[POItem]
    status: Literal["DRAFT", "SENT", "RECEIVED", "CANCELLED"] = "DRAFT"
    notes: Optional[str] = None
    remarks: Optional[str] = None
    expected_date: Optional[str] = None


# ---------------- CRM ----------------
class Customer(BaseModel):
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = "India"
    address: Optional[str] = None
    gstin: Optional[str] = None
    registration_type: Optional[Literal["Regular", "Composition", "Consumer", "Unregistered"]] = "Regular"
    pan_number: Optional[str] = None
    state_code: Optional[str] = None
    state: Optional[str] = None
    party_type: Optional[Literal["CUSTOMER", "SUPPLIER", "TRANSPORTER", "JOB_WORKER"]] = "CUSTOMER"
    registration_date: Optional[str] = None
    gst_status: Optional[str] = None
    # Extended fields
    customer_code: Optional[str] = None
    credit_limit: Optional[float] = 0.0
    payment_terms: Optional[str] = None
    pan_holder_name: Optional[str] = None
    pan_type: Optional[str] = None
    pan_status: Optional[str] = None
    aadhaar_number: Optional[str] = None
    aadhaar_holder_name: Optional[str] = None
    aadhaar_status: Optional[str] = None
    is_active: bool = True
    ledger_id: Optional[str] = None  # master_ledgers link; auto-created on create if omitted



class Lead(BaseModel):
    company_name: str
    contact_person: Optional[str] = None
    country: Optional[str] = "India"
    email: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = "Website"
    interested_in: Optional[str] = None
    estimated_value: float = 0
    status: Literal["NEW", "CONTACTED", "QUOTED", "WON", "LOST"] = "NEW"
    notes: Optional[str] = None
    next_follow_up: Optional[str] = None


# ---------------- Sales ----------------
SUPPORTED_CURRENCIES = ["INR", "USD", "AED", "EUR", "GBP"]


class SalesItem(BaseModel):
    product_id: Optional[str] = None
    product_name: str
    sku: Optional[str] = ""
    quantity: float
    unit: str = "Nos"
    unit_price: float
    gst_rate: float = 18.0
    hsn_code: Optional[str] = None


class Quotation(BaseModel):
    quote_number: Optional[str] = None
    customer_id: str
    customer_name: Optional[str] = None
    items: List[SalesItem]
    status: Literal["DRAFT", "SENT", "ACCEPTED", "REJECTED"] = "DRAFT"
    valid_until: Optional[str] = None
    notes: Optional[str] = None
    currency: Literal["INR", "USD", "AED", "EUR", "GBP"] = "INR"
    exchange_rate: float = 1.0


class SalesOrder(BaseModel):
    order_number: Optional[str] = None
    customer_id: str
    customer_name: Optional[str] = None
    items: List[SalesItem]
    status: Literal["PENDING", "CONFIRMED", "DISPATCHED", "DELIVERED", "CANCELLED"] = "PENDING"
    notes: Optional[str] = None
    currency: Literal["INR", "USD", "AED", "EUR", "GBP"] = "INR"
    exchange_rate: float = 1.0


class Invoice(BaseModel):
    invoice_number: Optional[str] = None
    invoice_type: Literal["TAX_INVOICE", "EXPORT_INVOICE", "DEBIT_NOTE", "CREDIT_NOTE", "PURCHASE_INVOICE"] = "TAX_INVOICE"
    sales_order_id: Optional[str] = None
    customer_id: str
    customer_name: Optional[str] = None
    items: List[SalesItem]
    status: Literal["UNPAID", "PARTIAL", "PAID"] = "UNPAID"
    payment_received: float = 0
    notes: Optional[str] = None
    currency: Literal["INR", "USD", "AED", "EUR", "GBP"] = "INR"
    exchange_rate: float = 1.0
    place_of_supply: Optional[str] = None
    taxable_value: float = 0.0
    cgst: float = 0.0
    sgst: float = 0.0
    igst: float = 0.0
    # E-Invoice
    irn: Optional[str] = None
    ack_no: Optional[str] = None
    ack_date: Optional[str] = None
    einvoice_qr_code: Optional[str] = None
    einvoice_status: Literal["PENDING", "GENERATED", "CANCELLED"] = "PENDING"
    # E-Way Bill
    ewb_number: Optional[str] = None
    ewb_date: Optional[str] = None
    ewb_status: Literal["PENDING", "GENERATED", "CANCELLED"] = "PENDING"
    transporter_name: Optional[str] = None
    vehicle_no: Optional[str] = None
    distance_km: Optional[float] = None
    transport_mode: Optional[Literal["ROAD", "RAIL", "AIR", "SHIP"]] = None


class Dispatch(BaseModel):
    challan_number: Optional[str] = None
    sales_order_id: Optional[str] = None
    customer_name: Optional[str] = None
    vehicle_no: str
    driver_name: str
    driver_phone: Optional[str] = None
    dispatch_date: str
    items: List[SalesItem] = []
    status: Literal["PENDING", "IN_TRANSIT", "DELIVERED"] = "PENDING"
    notes: Optional[str] = None


class CreditNote(BaseModel):
    credit_note_number: Optional[str] = None
    customer_id: str
    customer_name: Optional[str] = None
    original_invoice_id: Optional[str] = None
    items: List[SalesItem]
    status: Literal["DRAFT", "ISSUED"] = "DRAFT"
    notes: Optional[str] = None
    journal_entry_id: Optional[str] = None



# ---------------- Proforma Invoice (Export) ----------------
class PIItem(BaseModel):
    container_spec: Optional[str] = None  # e.g., "1x40 ft hc", "2x40 feet"
    description: str  # multi-line product description
    weight_per_unit: float = 0  # kg per piece
    quantity: float = 0
    unit_price: float = 0  # in chosen currency


class ProformaInvoice(BaseModel):
    pi_number: Optional[str] = None
    date: Optional[str] = None  # ISO date string
    validity_days: int = 30
    # Buyer
    buyer_name: str
    buyer_address: Optional[str] = None
    buyer_contact_person: Optional[str] = None
    buyer_email: Optional[str] = None
    buyer_phone: Optional[str] = None
    buyer_country: Optional[str] = None
    # Exporter (with sensible defaults)
    exporter_name: str = "GRAVITYONE ERP"
    exporter_address: Optional[str] = "Pune, Maharashtra, India"
    exporter_gstin: Optional[str] = "27AABCG1234F1Z5"
    exporter_iec: Optional[str] = None  # Importer Exporter Code
    # Bank details
    bank_name: Optional[str] = None
    bank_account_no: Optional[str] = None
    bank_swift: Optional[str] = None
    bank_iban: Optional[str] = None
    bank_branch: Optional[str] = None
    # Items & currency
    items: List[PIItem]
    currency: Literal["USD", "EUR", "GBP", "AED", "INR"] = "USD"
    # Logistics
    incoterms: Literal["FOB", "CIF", "CFR", "EXW", "CIP", "DAP", "DDP"] = "CIF"
    country_of_origin: str = "India"
    port_of_loading: Optional[str] = "Mundra Port, India"
    port_of_discharge: Optional[str] = None
    final_destination: Optional[str] = None
    # Terms
    payment_terms: str = "30% advance payment and balance 70% against the scan copy of the bill of lading."
    delivery_time: str = "Within 45-60 days after receiving confirmation on the same Proforma and advance payment."
    quantity_tolerance: str = "Min and Max 5% tolerance in weights & quantities."
    packing_notes: Optional[str] = None
    freight_clause: Optional[str] = None
    special_notes: Optional[str] = None
    # Status
    status: Literal["DRAFT", "SENT", "ACCEPTED", "CONVERTED", "CANCELLED"] = "DRAFT"


# ---------------- Company Profile ----------------
class CompanyProfile(BaseModel):
    name: str
    address: str
    gstin: str
    pan: Optional[str] = None
    state: str
    state_code: str
    city: Optional[str] = None
    pincode: Optional[str] = None
    country: Optional[str] = "India"
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    cin: Optional[str] = None
    iec: Optional[str] = None
    tagline: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_no: Optional[str] = None
    bank_ifsc: Optional[str] = None
    bank_branch: Optional[str] = None
    declaration: Optional[str] = None
    terms_conditions: Optional[str] = None
    logo_url: Optional[str] = None
    seal_url: Optional[str] = None


# ---------------- Job Work ----------------
class JobWorkChallanItem(BaseModel):
    product_id: Optional[str] = None
    product_name: str
    sku: Optional[str] = ""
    quantity: float
    unit: str = "Nos"
    description: Optional[str] = None
    remarks: Optional[str] = None
    is_custom: bool = False
    batch_id: Optional[str] = None
    serial_id: Optional[str] = None
    expiry_date: Optional[str] = None
    rate: Optional[float] = None      # None → backend fills from product cost_price
    gst_rate: Optional[float] = None  # None → backend fills from product; frontend may send null
    hsn_code: Optional[str] = None


class JobWorkChallan(BaseModel):
    challan_number: Optional[str] = None
    date: str
    job_worker_id: str
    job_worker_name: Optional[str] = None
    job_worker_gstin: Optional[str] = None
    contact_person: Optional[str] = None
    mobile: Optional[str] = None
    address: Optional[str] = None
    nature: str = "inputs"            # "inputs" | "capital_goods" — drives return-window days
    gst_type: str = "auto"            # "auto" | "intra" | "inter" — overrides GSTIN detection
    vehicle_no: Optional[str] = None
    driver_name: Optional[str] = None
    transport: Optional[str] = None
    lr_number: Optional[str] = None
    eway_bill_number: Optional[str] = None
    items: List[JobWorkChallanItem]
    status: Literal["DRAFT", "PENDING", "PARTIAL", "COMPLETED", "CANCELLED"] = "PENDING"
    notes: Optional[str] = None
    process_name: Optional[str] = None
    instructions: Optional[str] = None
    prepared_by: Optional[str] = None
    checked_by: Optional[str] = None


class JobWorkReceiptItem(BaseModel):
    # Links this receipt line to the exact challan line it's returning material
    # against — the precise replacement for the old product-id/name string
    # matching ("_item_key"), which could collide when two custom lines shared
    # a name. Optional only so legacy/loose callers don't 422; the router
    # resolves it from product_id when omitted.
    challan_item_id: Optional[str] = None
    product_id: Optional[str] = None
    product_name: str
    sku: Optional[str] = ""
    quantity_received: float
    # accepted_quantity is a distinct, user-entered field (goods can be received
    # but held for quality inspection before being accepted into usable stock).
    # None means "not yet specified" — the router defaults it to
    # quantity_received - rejected_quantity - scrap_quantity so existing callers
    # that don't send it keep working unchanged.
    accepted_quantity: Optional[float] = None
    rejected_quantity: float = 0.0
    scrap_quantity: float = 0.0
    is_custom: bool = False
    batch_id: Optional[str] = None
    serial_id: Optional[str] = None
    expiry_date: Optional[str] = None
    remarks: Optional[str] = None


class JobWorkReceipt(BaseModel):
    receipt_number: Optional[str] = None
    challan_id: Optional[str] = None
    date: str
    items: List[JobWorkReceiptItem]
    notes: Optional[str] = None


# ---------------- Audit Log ----------------
class AuditLog(BaseModel):
    action: Literal["CREATE", "UPDATE", "DELETE"]
    collection_name: str
    doc_id: str
    user_id: str
    user_name: str
    timestamp: str
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None


# ---------------- Auth Inputs / MFA ----------------
class ForgotPasswordIn(BaseModel):
    # email kept for back-compat with existing callers; identifier is the new,
    # wider field (email/username/phone). If identifier is omitted, email is
    # used — so existing clients sending only {"email": ...} are unaffected.
    email: Optional[EmailStr] = None
    identifier: Optional[str] = None
    method: Literal["link", "otp"] = "link"

    @field_validator("identifier")
    @classmethod
    def _default_identifier(cls, v, info):
        return v or info.data.get("email")


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        from core.password_policy import validate_password
        return validate_password(v)


class ResetPasswordOtpIn(BaseModel):
    identifier: str
    code: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        from core.password_policy import validate_password
        return validate_password(v)


class MfaLoginIn(BaseModel):
    mfa_token: str
    code: Optional[str] = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        from core.password_policy import validate_password
        return validate_password(v)


class ModulePermissionsIn(BaseModel):
    module_permissions: List[str]


class AdminResetPasswordIn(BaseModel):
    """Admin-initiated password reset for another user. If new_password is
    omitted, the server generates one and returns it once (shown to the admin
    to hand off out-of-band)."""
    new_password: Optional[str] = None

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            from core.password_policy import validate_password
            return validate_password(v)
        return v


# ---------------- Product Categories ----------------
class ProductCategory(BaseModel):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[str] = None
    status: Optional[str] = "Active"
    display_order: Optional[int] = 0


class ProductCategoryUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[str] = None
    status: Optional[str] = None
    display_order: Optional[int] = None


# ---------------- Additional MFA Inputs ----------------
class MfaVerifyIn(BaseModel):
    code: str


class MfaDisableIn(BaseModel):
    password: str


# ---------------- e-Way Bill ----------------
class EwbGenerateRequest(BaseModel):
    invoice_id: str
    transport_mode: Literal["ROAD", "RAIL", "AIR", "SHIP"]
    vehicle_number: Optional[str] = None
    distance_km: float
    vehicle_type: Optional[str] = "R"
    transporter_id: Optional[str] = None
    transporter_name: Optional[str] = None
    trans_doc_no: Optional[str] = None
    supply_type: Optional[str] = "OUTWARD"
    sub_supply_type: Optional[str] = "1"
    transaction_type: Optional[int] = 1


class EwbUpdateVehicleRequest(BaseModel):
    ewb_number: str
    vehicle_number: str
    from_place: str
    from_state_code: Optional[str] = None
    reason_code: int
    reason_remark: Optional[str] = None
    transport_mode: Optional[str] = "ROAD"
    trans_doc_no: Optional[str] = None
    trans_doc_date: Optional[str] = None


class EwbExtendRequest(BaseModel):
    ewb_number: str
    vehicle_number: Optional[str] = None
    from_place: str
    from_state_code: Optional[str] = None
    remaining_distance_km: float
    transport_mode: Optional[str] = "ROAD"
    reason_code: int
    reason_remark: Optional[str] = None
    consignment_status: Optional[str] = "TRANSIT"


class EwbCancelRequest(BaseModel):
    ewb_number: str
    reason_code: int
    reason_remark: Optional[str] = None


