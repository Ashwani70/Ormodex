"""Pydantic models shared across routers."""
from typing import List, Optional, Literal

from pydantic import BaseModel, EmailStr


# ---------------- Auth & Users ----------------
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    role: Literal["admin", "hr", "accountant", "employee"] = "employee"
    permissions: Optional[dict] = None
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[Literal["admin", "hr", "accountant", "employee"]] = None
    password: Optional[str] = None


# ---------------- Inventory ----------------
class Warehouse(BaseModel):
    name: str
    location: str
    manager: Optional[str] = None


class Product(BaseModel):
    name: str
    sku: str
    category: str
    description: Optional[str] = None
    unit: str = "pcs"
    cost_price: float = 0
    selling_price: float = 0
    quantity: float = 0
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
    product_id: str
    product_name: str
    sku: str
    quantity: float
    unit_price: float
    gst_rate: float = 18.0


class PurchaseOrder(BaseModel):
    po_number: Optional[str] = None
    supplier_id: str
    supplier_name: Optional[str] = None
    items: List[POItem]
    status: Literal["DRAFT", "SENT", "RECEIVED", "CANCELLED"] = "DRAFT"
    notes: Optional[str] = None
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
    product_id: str
    product_name: str
    sku: str
    quantity: float
    unit_price: float
    gst_rate: float = 18.0


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
    email: Optional[str] = None
    phone: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_no: Optional[str] = None
    bank_ifsc: Optional[str] = None
    bank_branch: Optional[str] = None
    terms_conditions: Optional[str] = None
    logo_url: Optional[str] = None


# ---------------- Job Work ----------------
class JobWorkChallanItem(BaseModel):
    product_id: Optional[str] = None
    product_name: str
    sku: Optional[str] = ""
    quantity: float
    unit: str = "pcs"
    is_custom: bool = False


class JobWorkChallan(BaseModel):
    challan_number: Optional[str] = None
    date: str
    job_worker_id: str
    job_worker_name: Optional[str] = None
    items: List[JobWorkChallanItem]
    status: Literal["PENDING", "PARTIAL", "COMPLETED", "CANCELLED"] = "PENDING"
    notes: Optional[str] = None


class JobWorkReceiptItem(BaseModel):
    product_id: Optional[str] = None
    product_name: str
    sku: Optional[str] = ""
    quantity_received: float
    scrap_quantity: float = 0.0
    is_custom: bool = False


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

