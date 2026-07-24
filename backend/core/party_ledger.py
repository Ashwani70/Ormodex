"""Auto-create a Chart-of-Accounts-linked ledger for a bank account, vendor,
or customer at creation time, so it can post through the voucher engine
(GST/TDS/attachments/approval) with no manual setup step.

Extracted from routers/ledger.py's original bank-account-only version so
vendors and customers (routers/purchase_v2.py, routers/sales.py) share the
exact same group/CoA/ledger creation instead of a third copy-paste. Every
master_ledgers row MUST carry a coa_account_id — the voucher engine blocks
posting (400) against any ledger that lacks one, see
[[project-gl-posting-audit-2026-07]] in project memory.
"""
import re

from core.db import db
from core.masters_crud import masters_create
from core.utils import new_id, now_iso

# One (group name, nature, CoA parent code, dr_cr) tuple per party kind.
# Banks and customers are ASSETs (Dr-natured); vendors are LIABILITIES
# (Cr-natured) — matches standard double-entry convention for balance sheet
# grouping (Trial Balance / Balance Sheet read the group's `nature`).
_PARTY_KIND = {
    "bank": {"group_name": "Bank Accounts", "nature": "Asset", "coa_type": "ASSET", "coa_parent": "1002", "coa_prefix": "BANK", "dr_cr": "Dr"},
    "vendor": {"group_name": "Sundry Creditors", "nature": "Liability", "coa_type": "LIABILITY", "coa_parent": "2001", "coa_prefix": "VEND", "dr_cr": "Cr"},
    "customer": {"group_name": "Sundry Debtors", "nature": "Asset", "coa_type": "ASSET", "coa_parent": "1100", "coa_prefix": "CUST", "dr_cr": "Dr"},
    # Catch-all for the Bank Entry modal's "New Ledger" quick-create — a
    # name-only ledger with no natural group of its own yet (the user can
    # move it to a proper group later from the Ledgers master).
    "general": {"group_name": "General Ledgers", "nature": "Asset", "coa_type": "ASSET", "coa_parent": "1500", "coa_prefix": "GEN", "dr_cr": "Dr"},
}


async def _ensure_group(kind: str, tenant_id: str, user: dict) -> str:
    spec = _PARTY_KIND[kind]
    existing = await db.master_groups.find_one(
        {"tenant_id": tenant_id, "name": spec["group_name"], "is_deleted": {"$ne": True}}
    )
    if existing:
        return existing["id"]
    doc = await masters_create(
        "master_groups",
        {"name": spec["group_name"], "parent_group_id": None, "nature": spec["nature"],
         "is_primary": True, "affects_gross_profit": False, "is_revenue": False},
        tenant_id, user,
    )
    return doc["id"]


async def _ensure_coa_code(kind: str, party_name: str) -> str:
    """Find-or-create a dedicated CoA code for one party — sharing one code
    across parties would collide balances in Trial Balance/Balance Sheet."""
    spec = _PARTY_KIND[kind]
    slug = re.sub(r"[^A-Z0-9]+", "", party_name.upper())[:6] or "ACCT"
    base_code = f"{spec['coa_prefix']}-{slug}"
    code = base_code
    n = 1
    while await db.chart_of_accounts.find_one({"code": code}):
        n += 1
        code = f"{base_code}{n}"
    doc = {
        "id": new_id(), "code": code, "name": f"{spec['group_name'].rstrip('s')} — {party_name}",
        "account_type": spec["coa_type"], "parent_code": spec["coa_parent"], "is_active": True,
        "opening_balance": 0.0, "currency": "INR", "tags": [kind],
        "created_at": now_iso(),
    }
    await db.chart_of_accounts.insert_one(doc)
    return doc["id"]


async def auto_create_party_ledger(
    kind: str, name: str, tenant_id: str, user: dict, *,
    opening_balance: float = 0.0, bank_details: dict | None = None,
    gstin: str | None = None, pan: str | None = None,
) -> str:
    """Create a master_ledgers row (+ its CoA account, + its group if not
    already there) for a bank account / vendor / customer. Returns the new
    ledger's id. `kind` is one of "bank", "vendor", "customer"."""
    spec = _PARTY_KIND[kind]
    group_id = await _ensure_group(kind, tenant_id, user)
    coa_account_id = await _ensure_coa_code(kind, name)
    ledger_doc = await masters_create(
        "master_ledgers",
        {
            "name": name, "group_id": group_id, "coa_account_id": coa_account_id,
            "opening_balance": opening_balance, "dr_cr": spec["dr_cr"],
            "gstin": gstin, "pan": pan,
            "bank_details": bank_details,
        },
        tenant_id, user, unique_fields=["name"],
    )
    return ledger_doc["id"]
