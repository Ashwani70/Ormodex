"""Inventory v2 — Tally-style stock ledger entities.

A rigorous, entry-based stock model that coexists with the legacy flat
Product/stock_transactions model (which PO/GRN/manufacturing still use). The
StockLedgerEntry is the single source of truth for quantity and valuation;
on-hand and value are always derived from it, never stored denormalised.
"""
from typing import List, Optional, Literal

from pydantic import BaseModel


# ───────────────────────── Unit of Measure ─────────────────────────

class UnitOfMeasure(BaseModel):
    name: str
    uqc_code: str  # GST-mandated Unit Quantity Code, e.g. NOS, KGS, BOX, PCS, MTR
    decimal_places: int = 2
    # Compound unit support: 1 (this unit) = conversion_factor x base_unit.
    base_unit_id: Optional[str] = None
    conversion_factor: Optional[float] = None  # qty of base units per 1 of this unit


# ───────────────────────── Stock Item (master) ─────────────────────────

class StockItem(BaseModel):
    name: str
    item_type: Literal["GOODS", "SERVICE"] = "GOODS"
    hsn_sac_code: Optional[str] = None
    gst_rate: float = 18.0
    default_unit_id: Optional[str] = None
    opening_stock_qty: float = 0.0
    opening_stock_value: float = 0.0
    # Per-item override. Blank/None on the item means "use the company default".
    # Standard-cost items should also set `standard_cost`.
    valuation_method: Optional[Literal[
        "FIFO", "LIFO", "WEIGHTED_AVG", "STANDARD_COST"
    ]] = None
    standard_cost: Optional[float] = None
    reorder_level: float = 0.0
    reorder_qty: float = 0.0
    min_level: float = 0.0
    max_level: float = 0.0
    track_batch: bool = False
    track_serial: bool = False
    track_expiry: bool = False
    sku: Optional[str] = None


class StockItemUpdate(BaseModel):
    name: Optional[str] = None
    hsn_sac_code: Optional[str] = None
    gst_rate: Optional[float] = None
    default_unit_id: Optional[str] = None
    valuation_method: Optional[Literal[
        "FIFO", "LIFO", "WEIGHTED_AVG", "STANDARD_COST"
    ]] = None
    standard_cost: Optional[float] = None
    reorder_level: Optional[float] = None
    reorder_qty: Optional[float] = None
    min_level: Optional[float] = None
    max_level: Optional[float] = None
    track_batch: Optional[bool] = None
    track_serial: Optional[bool] = None
    track_expiry: Optional[bool] = None


# ───────────────────────── Godown (warehouse, nestable) ─────────────────────────

WarehouseType = Literal[
    "MAIN", "BRANCH", "RAW_MATERIAL", "FINISHED_GOODS",
    "WIP", "SCRAP", "TRANSIT", "CONSIGNMENT",
]
WarehouseStatus = Literal["ACTIVE", "INACTIVE"]


class WarehouseBin(BaseModel):
    """A rack/shelf/bin location inside a warehouse. Stored in the parent
    warehouse's ``bins`` list (packed into godowns.extra JSONB)."""
    id: Optional[str] = None
    code: str                       # unique-within-warehouse bin code, also the barcode value
    name: Optional[str] = None
    kind: Literal["RACK", "SHELF", "BIN", "ZONE", "COLD_STORAGE", "DISPATCH", "RETURNS"] = "BIN"
    parent_bin_id: Optional[str] = None   # nest bins under racks/zones
    capacity: Optional[float] = None
    barcode: Optional[str] = None   # defaults to code
    notes: Optional[str] = None


class WarehouseDocument(BaseModel):
    """An uploaded document/photo attached to the warehouse (path in object storage)."""
    id: Optional[str] = None
    category: Literal[
        "INSURANCE", "FIRE_SAFETY", "LAYOUT", "AGREEMENT", "IMAGE", "OTHER",
    ] = "OTHER"
    name: str
    path: str                       # object-storage path returned by the upload endpoint
    content_type: Optional[str] = None
    size: Optional[int] = None


class Godown(BaseModel):
    # --- Core (backward compatible: name/address/parent kept as the first
    #     three fields the existing Warehouses page and all consumers use) ---
    name: str
    address: Optional[str] = None
    parent_godown_id: Optional[str] = None

    # --- Tab 1: General ---
    code: Optional[str] = None                # auto-generated when blank (WH00001)
    short_name: Optional[str] = None
    warehouse_type: WarehouseType = "MAIN"
    status: WarehouseStatus = "ACTIVE"
    company_id: Optional[str] = None
    branch_id: Optional[str] = None
    cost_center_id: Optional[str] = None

    # --- Tab 2: Location ---
    country: Optional[str] = "India"
    state: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    map_url: Optional[str] = None
    photo_path: Optional[str] = None          # object-storage path of the warehouse photo

    # --- Tab 3: Inventory settings ---
    allow_negative_stock: bool = False
    enable_batch: bool = False
    enable_serial: bool = False
    enable_bin: bool = False
    valuation_method: Literal[
        "FIFO", "LIFO", "WEIGHTED_AVG", "STANDARD_COST"
    ] = "WEIGHTED_AVG"
    min_stock: Optional[float] = None
    max_stock: Optional[float] = None
    safety_stock: Optional[float] = None
    reorder_level: Optional[float] = None
    reorder_qty: Optional[float] = None
    cycle_count_frequency: Optional[Literal[
        "NONE", "DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY",
    ]] = "NONE"

    # --- Tab 4: Bin management ---
    enable_rack_bin: bool = False
    bins: List[WarehouseBin] = []

    # --- Tab 5: Security ---
    manager_name: Optional[str] = None
    manager_phone: Optional[str] = None
    manager_email: Optional[str] = None
    allowed_user_ids: List[str] = []
    allowed_roles: List[str] = []
    approval_required: bool = False
    read_only: bool = False
    allow_stock_transfer: bool = True
    allow_direct_issue: bool = True

    # --- Tab 6: Documents ---
    documents: List[WarehouseDocument] = []
    notes: Optional[str] = None


# ───────────────────────── Batch & Serial ─────────────────────────

class Batch(BaseModel):
    stock_item_id: str
    batch_number: str
    mfg_date: Optional[str] = None
    expiry_date: Optional[str] = None


class SerialNumber(BaseModel):
    stock_item_id: str
    serial: str
    status: Literal["IN_STOCK", "SOLD", "RETURNED"] = "IN_STOCK"


# ───────────────────────── Stock Ledger Entry ─────────────────────────

MovementType = Literal[
    "OPENING", "PURCHASE", "SALE", "TRANSFER_IN", "TRANSFER_OUT", "ADJUSTMENT"
]


class StockLedgerEntryIn(BaseModel):
    """Caller-supplied movement. For inward moves provide `rate`; for outward
    moves the valuation engine computes rate/value, so `rate` is ignored."""
    stock_item_id: str
    godown_id: str
    qty: float  # signed: + inward, - outward
    movement_type: MovementType
    rate: Optional[float] = None  # cost per unit (inward only)
    batch_id: Optional[str] = None
    serial_id: Optional[str] = None
    source_doc_type: Optional[str] = None
    source_doc_id: Optional[str] = None
    entry_date: Optional[str] = None  # ISO date; defaults to today


# ───────────────────────── Stock Transfer ─────────────────────────

class StockTransferLine(BaseModel):
    stock_item_id: Optional[str] = None
    product_id: Optional[str] = None
    qty: float  # positive
    batch_id: Optional[str] = None
    serial_id: Optional[str] = None
    expiry_date: Optional[str] = None


class StockTransfer(BaseModel):
    transfer_number: Optional[str] = None
    from_godown_id: str
    to_godown_id: str
    transfer_date: Optional[str] = None
    lines: List[StockTransferLine]
    remarks: Optional[str] = None


# ───────────────────────── Manual adjustment ─────────────────────────

class StockAdjustmentIn(BaseModel):
    stock_item_id: Optional[str] = None
    product_id: Optional[str] = None
    godown_id: str
    qty: float  # signed
    rate: Optional[float] = None  # required for positive (inward) adjustment
    reason: str = "manual"
    batch_id: Optional[str] = None
    serial_id: Optional[str] = None
    expiry_date: Optional[str] = None
    entry_date: Optional[str] = None
