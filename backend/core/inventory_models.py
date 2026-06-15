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
    valuation_method: Literal["FIFO", "WEIGHTED_AVG"] = "WEIGHTED_AVG"
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
    valuation_method: Optional[Literal["FIFO", "WEIGHTED_AVG"]] = None
    reorder_level: Optional[float] = None
    reorder_qty: Optional[float] = None
    min_level: Optional[float] = None
    max_level: Optional[float] = None
    track_batch: Optional[bool] = None
    track_serial: Optional[bool] = None
    track_expiry: Optional[bool] = None


# ───────────────────────── Godown (warehouse, nestable) ─────────────────────────

class Godown(BaseModel):
    name: str
    address: Optional[str] = None
    parent_godown_id: Optional[str] = None


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
    stock_item_id: str
    qty: float  # positive
    batch_id: Optional[str] = None
    serial_id: Optional[str] = None


class StockTransfer(BaseModel):
    transfer_number: Optional[str] = None
    from_godown_id: str
    to_godown_id: str
    transfer_date: Optional[str] = None
    lines: List[StockTransferLine]
    remarks: Optional[str] = None


# ───────────────────────── Manual adjustment ─────────────────────────

class StockAdjustmentIn(BaseModel):
    stock_item_id: str
    godown_id: str
    qty: float  # signed
    rate: Optional[float] = None  # required for positive (inward) adjustment
    reason: str = "manual"
    batch_id: Optional[str] = None
    entry_date: Optional[str] = None
