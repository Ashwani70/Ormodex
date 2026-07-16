"""Configurable Purchase Order numbering — AUTO or MANUAL mode using MongoDB."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Any

from fastapi import HTTPException

from .auth_utils import is_admin_role
from .db import db
from .utils import now_iso, new_id

SETTINGS_ID = "global"
PO_COLLECTION = "purchase_orders_v2"
VALID_SEPARATORS = {"-", "/", ""}
DEFAULT_SETTINGS = {
    "id": SETTINGS_ID, "mode": "AUTO", "prefix": "PO", "fy_format": "",
    "branch_code": "", "separator": "-", "start_sequence": 1, "sequence_length": 5,
}
PERM_OVERRIDE = "po_number_override"
PERM_EDIT = "po_number_edit"


def has_perm(user: dict, perm: str) -> bool:
    if is_admin_role((user or {}).get("role")):
        return True
    return perm in ((user or {}).get("module_permissions") or [])


def financial_year_label(d: Optional[datetime] = None) -> str:
    d = d or datetime.now(timezone.utc)
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


def _coerce_settings(raw: dict | None) -> dict:
    s = {**DEFAULT_SETTINGS, **(raw or {})}
    s["id"] = SETTINGS_ID
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


async def get_settings() -> dict:
    row = await db.po_numbering_settings.find_one({"id": SETTINGS_ID}, {"_id": 0})
    return _coerce_settings(row)


async def save_settings(payload: dict, user: dict) -> dict:
    s = _coerce_settings(payload)
    s["updated_at"] = now_iso()
    s["updated_by"] = (user or {}).get("id")
    await db.po_numbering_settings.update_one(
        {"id": SETTINGS_ID},
        {"$set": s},
        upsert=True
    )
    return await get_settings()


def build_po_number(settings: dict, seq: int) -> str:
    sep = settings.get("separator", "-")
    seq_str = str(seq).zfill(int(settings.get("sequence_length", 5)))
    segments = [
        settings.get("branch_code", ""), settings.get("prefix", ""),
        settings.get("fy_format", ""), seq_str,
    ]
    segments = [seg for seg in segments if seg]
    return sep.join(segments) if sep else "".join(segments)


async def _next_sequence(settings: dict) -> int:
    counter_key = f"{PO_COLLECTION}_po_number_seq"
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
        return_document=True
    )
    return res["seq"] if res else start


async def is_unique(po_number: str, exclude_id: Optional[str] = None) -> bool:
    q: dict[str, Any] = {"po_number": po_number}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    clash = await db[PO_COLLECTION].find_one(q)
    return clash is None


async def ensure_unique(po_number: str, exclude_id: Optional[str] = None) -> None:
    if not await is_unique(po_number, exclude_id):
        raise HTTPException(status_code=409, detail=f"PO number '{po_number}' already exists")


async def generate_unique_auto_number(settings: Optional[dict] = None) -> str:
    settings = settings or await get_settings()
    for _ in range(50):
        seq = await _next_sequence(settings)
        candidate = build_po_number(settings, seq)
        if await is_unique(candidate):
            return candidate
    raise HTTPException(status_code=500, detail="Unable to allocate a unique PO number")


async def allocate_po_number(payload_number: Optional[str], user: dict) -> str:
    settings = await get_settings()
    supplied = (payload_number or "").strip()
    if supplied:
        if not has_perm(user, PERM_OVERRIDE):
            raise HTTPException(status_code=403, detail="po_number_override permission required")
        await ensure_unique(supplied)
        return supplied
    if settings["mode"] == "MANUAL":
        raise HTTPException(status_code=400, detail="PO number is required (numbering mode is Manual Entry)")
    return await generate_unique_auto_number(settings)


_LOCKED_STATUSES = {"SENT", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED", "APPROVED"}


async def compute_locked(po: dict) -> bool:
    if po.get("po_number_locked"):
        return True
    if po.get("status") in _LOCKED_STATUSES:
        return True
    if po.get("approved_at") or po.get("approval_status") == "APPROVED":
        return True
    po_id = po.get("id")
    if not po_id:
        return False
    grn = await db.goods_receipt_notes_v2.find_one({"purchase_order_id": po_id})
    if grn:
        return True
    bill = await db.purchase_bills.find_one({"purchase_order_id": po_id})
    if bill:
        return True
    ewb = await db.eway_bills.find_one({"purchase_order_id": po_id})
    if ewb:
        return True
    return False


async def record_number_change(po_id: str, old_number: Optional[str],
                                new_number: str, user: dict, reason: str | None) -> dict:
    entry_id = new_id()
    await db.po_number_audit.insert_one({
        "id": entry_id,
        "purchase_order_id": po_id,
        "old_po_number": old_number,
        "new_po_number": new_number,
        "changed_by": (user or {}).get("id", "system"),
        "changed_by_name": (user or {}).get("name", "System"),
        "reason": (reason or "").strip() or None,
        "changed_at": now_iso(),
    })
    return {
        "id": entry_id, "purchase_order_id": po_id,
        "old_po_number": old_number, "new_po_number": new_number,
        "changed_by": (user or {}).get("id", "system"),
        "changed_at": now_iso(),
    }


async def number_audit_history(po_id: str) -> list[dict]:
    return await db.po_number_audit.find(
        {"purchase_order_id": po_id},
        {"_id": 0}
    ).sort("changed_at", -1).limit(500).to_list(500)
