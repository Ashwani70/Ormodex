"""Voucher numbering — unique per (tenant_id, voucher_type_id, financial_year).

Driven by the VoucherType master's config:
  - numbering_method: "auto" (engine generates) | "manual" (client supplies,
    engine enforces uniqueness) | "none" (no number).
  - prefix / suffix.
  - restart_rule: "never" | "yearly" (per FY) | "monthly" (per FY+month).

Sequence allocation is atomic via a per-key counter (db.voucher_counters,
find_one_and_update $inc) — the same primitive core.utils.next_doc_number uses —
so concurrent creates and prior deletions can never collide or reuse a number.
A unique index on (tenant_id, voucher_type_id, financial_year, voucher_no)
backstops it at the DB level.
"""
from datetime import date
from typing import Optional

from fastapi import HTTPException

from .db import db
from .tenant import tenant_filter

VOUCHERS = "vouchers_v2"
COUNTERS = "voucher_counters"
DEFAULT_METHOD = "auto"


def _period_token(restart_rule: str, voucher_date: str) -> str:
    """The restart bucket within a financial year."""
    if restart_rule == "monthly":
        # voucher_date is ISO (YYYY-MM-DD); month bucket = YYYY-MM.
        return (voucher_date or date.today().isoformat())[:7]
    return ""  # yearly / never share one bucket per FY


async def _voucher_type_config(voucher_type_id: Optional[str], tenant: str) -> dict:
    if not voucher_type_id:
        return {"numbering_method": DEFAULT_METHOD, "prefix": None, "suffix": None, "restart_rule": "yearly"}
    vt = await db["master_voucher_types"].find_one(
        tenant_filter(tenant, {"id": voucher_type_id}),
        {"_id": 0, "numbering_method": 1, "prefix": 1, "suffix": 1, "restart_rule": 1},
    )
    if not vt:
        raise HTTPException(400, "voucher_type_id not found in this tenant")
    return vt


async def _allocate_seq(tenant: str, voucher_type_id: Optional[str], fy: str, period: str) -> int:
    """Atomically allocate the next sequence for a numbering bucket."""
    key = f"{tenant}|{voucher_type_id or 'default'}|{fy}|{period}"
    res = await db[COUNTERS].find_one_and_update(
        {"_id": key},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return (res or {}).get("seq", 1)


async def assert_unique(tenant: str, voucher_type_id: Optional[str], fy: str, voucher_no: str):
    """Reject a duplicate number within (tenant, voucher_type_id, FY)."""
    clash = await db[VOUCHERS].find_one(
        tenant_filter(
            tenant,
            {"voucher_type_id": voucher_type_id, "fiscal_year": fy, "voucher_no": voucher_no},
            include_deleted=True,
        ),
        {"_id": 0, "id": 1},
    )
    if clash:
        raise HTTPException(409, f"Voucher number '{voucher_no}' already exists for this type in {fy}")


async def generate_voucher_no(
    *,
    tenant: str,
    parent_type: str,
    voucher_type_id: Optional[str],
    fy: str,
    voucher_date: str,
    manual_no: Optional[str] = None,
) -> Optional[str]:
    """Resolve the voucher_no per the VoucherType config.

    Returns the number string, or None when numbering_method == "none".
    Raises 400/409 on manual-mode misuse or duplicates.
    """
    cfg = await _voucher_type_config(voucher_type_id, tenant)
    method = cfg.get("numbering_method") or DEFAULT_METHOD

    if method == "none":
        return None

    if method == "manual":
        if not manual_no:
            raise HTTPException(400, "This voucher type uses manual numbering — voucher_no is required")
        await assert_unique(tenant, voucher_type_id, fy, manual_no)
        return manual_no

    # auto
    prefix = cfg.get("prefix") or parent_type[:3].upper()
    suffix = cfg.get("suffix") or ""
    restart_rule = cfg.get("restart_rule") or "yearly"
    period = _period_token(restart_rule, voucher_date)
    seq = await _allocate_seq(tenant, voucher_type_id, fy, period)
    period_seg = f"/{period}" if period else ""
    number = f"{prefix}/{fy}{period_seg}/{str(seq).zfill(5)}{suffix}"
    # Belt-and-suspenders: the atomic counter makes this near-impossible, but a
    # manual number earlier in the same bucket could in theory collide.
    await assert_unique(tenant, voucher_type_id, fy, number)
    return number


async def create_numbering_indexes(database):
    """Unique index backstopping numbering at the DB level."""
    await database[VOUCHERS].create_index(
        [("tenant_id", 1), ("voucher_type_id", 1), ("fiscal_year", 1), ("voucher_no", 1)],
        unique=True,
        partialFilterExpression={"voucher_no": {"$type": "string"}},  # allow many null (numbering_method=none)
        name="uniq_voucher_no_per_type_fy",
    )
