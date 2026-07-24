"""Configurable document numbering — AUTO or MANUAL mode, per document type.

Generalizes core.po_numbering's exact algorithm (same template shape, same
atomic-counter primitive, same permission model) to any document type instead
of being Purchase-Order-specific. Vouchers are NOT part of this — they already
have their own, separate, complete numbering system driven by the VoucherType
master (see core/voucher_numbering.py); this module is for the document types
that only ever had a fixed next_doc_number() counter (GRN, Invoice, and more
to come — add an entry to DOC_TYPES and one call-site swap).

Purchase Order is a special case: it keeps its own dedicated table
(po_numbering_settings, still owned by core/po_numbering.py /
routers/po_numbering.py) because routers/purchase_v2.py's PurchaseOrdersV2.jsx
frontend reads that endpoint directly. This module's "purchase_order" entry
reads/writes THAT SAME TABLE (not a separate copy) so there is only ever one
real PO-numbering config — see get_settings/save_settings below.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Any

from fastapi import HTTPException

from .auth_utils import is_admin_role
from .db import db
from .utils import now_iso

VALID_SEPARATORS = {"-", "/", ""}

# One entry per configurable document type: the collection its documents live
# in (for uniqueness checks + the counter key), the field name holding the
# document number, a sensible default prefix, and the permission suffix used
# for override/edit checks (e.g. "grn_number_override").
DOC_TYPES: dict[str, dict] = {
    "purchase_order": {
        "label": "Purchase Order", "collection": "purchase_orders_v2",
        "number_field": "po_number", "default_prefix": "PO", "perm_key": "po_number",
        # Purchase Order keeps its pre-existing dedicated settings table —
        # every other doc_type uses document_numbering_settings.
        "legacy_table": "po_numbering_settings",
    },
    "grn": {
        "label": "Goods Receipt Note", "collection": "goods_receipt_notes_v2",
        "number_field": "grn_number", "default_prefix": "GRN", "perm_key": "grn_number",
        "legacy_table": None,
    },
    "invoice": {
        "label": "Invoice", "collection": "invoices",
        "number_field": "invoice_number", "default_prefix": "INV", "perm_key": "invoice_number",
        "legacy_table": None,
    },
}

TABLE = "document_numbering_settings"


def _default_settings(doc_type: str) -> dict:
    cfg = DOC_TYPES[doc_type]
    return {
        "id": doc_type, "mode": "AUTO", "prefix": cfg["default_prefix"], "fy_format": "",
        "branch_code": "", "separator": "-", "start_sequence": 1, "sequence_length": 5,
    }


def has_perm(user: dict, doc_type: str, action: str) -> bool:
    """action: 'override' (supply own number in AUTO mode) or 'edit' (change settings)."""
    if is_admin_role((user or {}).get("role")):
        return True
    perm = f"{DOC_TYPES[doc_type]['perm_key']}_{action}"
    return perm in ((user or {}).get("module_permissions") or [])


def financial_year_label(d: Optional[datetime] = None) -> str:
    d = d or datetime.now(timezone.utc)
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


def _coerce_settings(doc_type: str, raw: dict | None) -> dict:
    s = {**_default_settings(doc_type), **(raw or {})}
    s["id"] = doc_type
    s["mode"] = "MANUAL" if str(s.get("mode", "AUTO")).upper() == "MANUAL" else "AUTO"
    if s.get("separator") not in VALID_SEPARATORS:
        s["separator"] = "-"
    try:
        s["start_sequence"] = max(1, int(s.get("start_sequence", 1)))
    except (TypeError, ValueError):
        s["start_sequence"] = 1
    try:
        s["sequence_length"] = max(1, min(12, int(s.get("sequence_length", 5))))
    except (TypeError, ValueError):
        s["sequence_length"] = 5
    for k in ("prefix", "fy_format", "branch_code"):
        s[k] = str(s.get(k) or "").strip()
    return s


def _table_for(doc_type: str) -> str:
    legacy = DOC_TYPES[doc_type].get("legacy_table")
    return legacy or TABLE


async def get_settings(doc_type: str) -> dict:
    if doc_type not in DOC_TYPES:
        raise HTTPException(404, f"Unknown document type '{doc_type}'")
    table = _table_for(doc_type)
    # The legacy po_numbering_settings table keys its single row "global",
    # not "purchase_order" — every other (new) table keys by doc_type itself.
    row_id = "global" if table == "po_numbering_settings" else doc_type
    row = await db[table].find_one({"id": row_id}, {"_id": 0})
    return _coerce_settings(doc_type, row)


async def save_settings(doc_type: str, payload: dict, user: dict) -> dict:
    if doc_type not in DOC_TYPES:
        raise HTTPException(404, f"Unknown document type '{doc_type}'")
    s = _coerce_settings(doc_type, payload)
    s["updated_at"] = now_iso()
    s["updated_by"] = (user or {}).get("id")
    table = _table_for(doc_type)
    row_id = "global" if table == "po_numbering_settings" else doc_type
    s["id"] = row_id
    await db[table].update_one({"id": row_id}, {"$set": s}, upsert=True)
    return await get_settings(doc_type)


def build_document_number(settings: dict, seq: int) -> str:
    sep = settings.get("separator", "-")
    seq_str = str(seq).zfill(int(settings.get("sequence_length", 5)))
    segments = [
        settings.get("branch_code", ""), settings.get("prefix", ""),
        settings.get("fy_format", ""), seq_str,
    ]
    segments = [seg for seg in segments if seg]
    return sep.join(segments) if sep else "".join(segments)


async def _next_sequence(doc_type: str, settings: dict) -> int:
    counter_key = f"document_numbering:{doc_type}_seq"
    start = int(settings.get("start_sequence", 1))

    existing = await db.counters.find_one({"_id": counter_key})
    if not existing:
        try:
            await db.counters.insert_one({"_id": counter_key, "seq": start - 1})
        except Exception:
            pass

    res = await db.counters.find_one_and_update(
        {"_id": counter_key},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return res["seq"] if res else start


async def is_unique(doc_type: str, number: str, exclude_id: Optional[str] = None) -> bool:
    cfg = DOC_TYPES[doc_type]
    q: dict[str, Any] = {cfg["number_field"]: number}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    clash = await db[cfg["collection"]].find_one(q)
    return clash is None


async def ensure_unique(doc_type: str, number: str, exclude_id: Optional[str] = None) -> None:
    if not await is_unique(doc_type, number, exclude_id):
        label = DOC_TYPES[doc_type]["label"]
        raise HTTPException(status_code=409, detail=f"{label} number '{number}' already exists")


async def generate_unique_auto_number(doc_type: str, settings: Optional[dict] = None) -> str:
    settings = settings or await get_settings(doc_type)
    for _ in range(50):
        seq = await _next_sequence(doc_type, settings)
        candidate = build_document_number(settings, seq)
        if await is_unique(doc_type, candidate):
            return candidate
    raise HTTPException(status_code=500, detail="Unable to allocate a unique document number")


async def allocate_document_number(doc_type: str, payload_number: Optional[str], user: dict) -> str:
    """Drop-in replacement for a bare `next_doc_number(prefix, collection)` call
    at a document's create endpoint — same call shape as po_numbering's
    allocate_po_number. Pass the caller-supplied number (if any) through as
    payload_number; returns the number to actually store."""
    settings = await get_settings(doc_type)
    supplied = (payload_number or "").strip()
    if supplied:
        if not has_perm(user, doc_type, "override"):
            perm = f"{DOC_TYPES[doc_type]['perm_key']}_override"
            raise HTTPException(status_code=403, detail=f"{perm} permission required")
        await ensure_unique(doc_type, supplied)
        return supplied
    if settings["mode"] == "MANUAL":
        label = DOC_TYPES[doc_type]["label"]
        raise HTTPException(status_code=400, detail=f"{label} number is required (numbering mode is Manual Entry)")
    return await generate_unique_auto_number(doc_type, settings)
