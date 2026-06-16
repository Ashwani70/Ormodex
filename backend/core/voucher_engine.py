"""Voucher posting engine — catalog + posting-rules registry + dispatch.

One handler per parent_type decides what an *approved* voucher does. Maker-checker
(status draft → pending → approved) is enforced by the router; this module only
posts when called for an approved voucher, and posting is idempotent on the
voucher id so re-approval/re-runs can't double-post.

Scope of THIS implementation (per the agreed plan):
  - ACCOUNTING types: real posting to journal_entries from accounting_lines
    (balanced double-entry), reusing the existing accounting module's conventions.
    `memorandum` never posts; `reversing_journal` posts a reports-only entry that
    auto-reverses on its effective date.
  - INVENTORY / ORDER / PAYROLL types: registered and validated, but NOT yet
    posting to stock/books — they store the document and are clearly flagged
    `posts=False` / "not yet implemented". Existing routers (stock_ledger,
    job_work, payroll, manufacturing) remain the source of truth until these
    handlers are filled in a later phase.
"""
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Awaitable, Callable, Optional

from fastapi import HTTPException

from .db import db
from .tenant import tenant_filter
from .utils import log_audit, now_iso

JE_COLL = "journal_entries"


# ───────────────────────── catalog ─────────────────────────

@dataclass
class TypeSpec:
    category: str                 # accounting | inventory | order | payroll
    posts_to_books: bool = False  # posts journal entries
    posts_to_stock: bool = False  # posts stock ledger entries
    implemented: bool = True      # is the posting handler actually built yet?
    note: str = ""


# The full parent_type catalog. `implemented=False` means "validated + stored,
# but posting is deferred to a later phase" — never silently a no-op that looks done.
CATALOG: dict[str, TypeSpec] = {
    # ----- Accounting (posting implemented) -----
    "contra": TypeSpec("accounting", posts_to_books=True, note="Cash/bank both legs, no GST"),
    "payment": TypeSpec("accounting", posts_to_books=True, note="TDS on payment supported via statutory.tds"),
    "receipt": TypeSpec("accounting", posts_to_books=True, note="TCS / advance-GST via statutory"),
    "journal": TypeSpec("accounting", posts_to_books=True),
    "sales": TypeSpec("accounting", posts_to_books=True, note="GST output; e-invoice/e-way refs stored"),
    "purchase": TypeSpec("accounting", posts_to_books=True, note="ITC; RCM via statutory.gst.reverse_charge"),
    "credit_note": TypeSpec("accounting", posts_to_books=True, note="Links original invoice"),
    "debit_note": TypeSpec("accounting", posts_to_books=True, note="Reverses ITC"),
    "export_sales": TypeSpec("accounting", posts_to_books=True, note="LUT/with-tax; shipping bill in statutory.extra"),
    "purchase_import": TypeSpec("accounting", posts_to_books=True, note="IGST on import; BOE in statutory.extra"),
    "service_invoice": TypeSpec("accounting", posts_to_books=True, note="SAC, no inventory"),
    "purchase_expenses": TypeSpec("accounting", posts_to_books=True, note="Apportionment to item value: later phase"),
    "job_work_expenses": TypeSpec("accounting", posts_to_books=True, note="GST + TDS 194C via statutory"),
    "reversing_journal": TypeSpec("accounting", posts_to_books=True, note="Reports-only; auto-reverses on effective date"),
    "memorandum": TypeSpec("accounting", posts_to_books=False, note="Never posts to books"),
    # ----- Inventory (deferred: existing stock_ledger/job_work remain source of truth) -----
    "delivery_note": TypeSpec("inventory", posts_to_stock=True, implemented=False),
    "receipt_note": TypeSpec("inventory", posts_to_stock=True, implemented=False),
    "rejections_in": TypeSpec("inventory", posts_to_stock=True, implemented=False),
    "rejections_out": TypeSpec("inventory", posts_to_stock=True, implemented=False),
    "physical_stock": TypeSpec("inventory", posts_to_stock=True, implemented=False),
    "stock_journal": TypeSpec("inventory", posts_to_stock=True, implemented=False),
    "material_in": TypeSpec("inventory", posts_to_stock=True, implemented=False),
    "material_out": TypeSpec("inventory", posts_to_stock=True, implemented=False),
    "job_work_challan": TypeSpec("inventory", posts_to_stock=True, implemented=False, note="§143, ITC-04, return-window: see routers/job_work.py"),
    "job_work_material_inward": TypeSpec("inventory", posts_to_stock=True, implemented=False),
    "non_returnable_gate_pass": TypeSpec("inventory", posts_to_stock=True, implemented=False),
    "stock_transfer_interunit": TypeSpec("inventory", posts_to_stock=True, posts_to_books=True, implemented=False),
    "stock_transfer_material_interunit": TypeSpec("inventory", posts_to_stock=True, implemented=False),
    # ----- Order (no posting; track fulfilled vs pending via links) -----
    "purchase_order": TypeSpec("order", implemented=False, note="Tracks fulfilment via links chain"),
    "sales_order": TypeSpec("order", implemented=False),
    "job_work_in_order": TypeSpec("order", implemented=False),
    "job_work_out_order": TypeSpec("order", implemented=False),
    # ----- Payroll (deferred: existing payroll router remains source of truth) -----
    "attendance": TypeSpec("payroll", implemented=False),
    "payroll": TypeSpec("payroll", posts_to_books=True, implemented=False, note="PF/ESI/PT/TDS: see routers/payroll.py"),
}


def spec_for(parent_type: str) -> TypeSpec:
    spec = CATALOG.get(parent_type)
    if not spec:
        raise HTTPException(400, f"Unknown parent_type '{parent_type}'")
    return spec


# ───────────────────────── validation ─────────────────────────

def validate_voucher(doc: dict):
    """Shape validation that applies before a voucher can be submitted/approved."""
    spec = spec_for(doc["parent_type"])
    lines = doc.get("accounting_lines") or []
    if spec.posts_to_books and spec.implemented and doc["parent_type"] not in ("memorandum",):
        if not lines:
            raise HTTPException(400, f"{doc['parent_type']} requires accounting_lines")
        dr = round(sum(l["amount"] for l in lines if l["dr_cr"] == "Dr"), 2)
        cr = round(sum(l["amount"] for l in lines if l["dr_cr"] == "Cr"), 2)
        if abs(dr - cr) > 0.01:
            raise HTTPException(400, f"Voucher not balanced: Dr {dr} ≠ Cr {cr}")
    if doc["parent_type"] == "contra":
        # Contra carries no GST on any line.
        if any(l.get("gst_details") for l in lines):
            raise HTTPException(400, "Contra vouchers cannot carry GST")


# ───────────────────────── posting handlers ─────────────────────────

PostFn = Callable[[dict, dict, str], Awaitable[Optional[dict]]]
_HANDLERS: dict[str, PostFn] = {}


def handler(*parent_types: str):
    def deco(fn: PostFn):
        for pt in parent_types:
            _HANDLERS[pt] = fn
        return fn
    return deco


async def _next_je_number(tenant: str) -> str:
    fy = await db.fiscal_years.find_one({"is_active": True})
    fy_name = fy["name"] if fy else date.today().strftime("%Y-%y")
    count = await db[JE_COLL].count_documents({"fiscal_year": fy_name})
    return f"JE/{fy_name}/{str(count + 1).zfill(5)}"


async def _ledger_name(ledger_id: str, tenant: str) -> str:
    led = await db["master_ledgers"].find_one(tenant_filter(tenant, {"id": ledger_id}), {"_id": 0, "name": 1})
    return (led or {}).get("name", ledger_id)


async def _post_journal_from_lines(voucher: dict, tenant: str, user: dict, *, reversing: bool = False) -> Optional[dict]:
    """Post a balanced journal entry from a voucher's accounting_lines.

    Idempotent on (source_collection=vouchers_v2, source_id=voucher id).
    """
    existing = await db[JE_COLL].find_one(
        {"source_collection": "vouchers_v2", "source_id": voucher["id"]}, {"_id": 0})
    if existing:
        return existing

    lines = voucher.get("accounting_lines") or []
    je_lines = []
    for l in lines:
        je_lines.append({
            "ledger_id": l["ledger_id"],
            "account_name": await _ledger_name(l["ledger_id"], tenant),
            "debit": round(l["amount"], 2) if l["dr_cr"] == "Dr" else 0.0,
            "credit": round(l["amount"], 2) if l["dr_cr"] == "Cr" else 0.0,
            "narration": l.get("narration"),
            "gst_details": l.get("gst_details"),
        })
    total = round(sum(x["debit"] for x in je_lines), 2)

    fy = await db.fiscal_years.find_one({"is_active": True})
    fy_name = fy["name"] if fy else date.today().strftime("%Y-%y")
    entry = {
        "id": str(uuid.uuid4()),
        "entry_number": await _next_je_number(tenant),
        "tenant_id": tenant,
        "date": voucher.get("date"),
        "effective_date": voucher.get("effective_date"),
        "narration": voucher.get("narration") or f"{voucher['parent_type']} {voucher.get('voucher_no','')}",
        "lines": je_lines,
        "status": "POSTED",
        "fiscal_year": fy_name,
        "reference": voucher.get("voucher_no"),
        "tags": ["AUTO", "VOUCHER", voucher["parent_type"].upper()] + (["REVERSING"] if reversing else []),
        "source_collection": "vouchers_v2",
        "source_id": voucher["id"],
        "party_id": voucher.get("party_id"),
        "total_debit": total,
        "total_credit": total,
        "reports_only": reversing,  # reversing journals don't affect final books
        "created_by": user.get("id", "system"),
        "created_at": now_iso(),
    }
    await db[JE_COLL].insert_one(entry)
    entry.pop("_id", None)
    await log_audit("CREATE", JE_COLL, entry["id"], user, new_values=entry)
    return entry


# All implemented accounting types post a balanced JE from their lines. The
# statutory nuances (TDS/TCS/RCM/e-invoice) are captured on the voucher's
# `statutory` block and carried onto the entry; line-level GST rides on each line.
@handler(
    "contra", "payment", "receipt", "journal", "sales", "purchase",
    "credit_note", "debit_note", "export_sales", "purchase_import",
    "service_invoice", "purchase_expenses", "job_work_expenses",
)
async def _post_accounting(voucher: dict, user: dict, tenant: str):
    return await _post_journal_from_lines(voucher, tenant, user)


@handler("reversing_journal")
async def _post_reversing(voucher: dict, user: dict, tenant: str):
    # Reports-only entry, flagged so financial statements can exclude it; the
    # auto-reverse on `effective_date` is handled by the reversing sweep below.
    return await _post_journal_from_lines(voucher, tenant, user, reversing=True)


@handler("memorandum")
async def _post_memorandum(voucher: dict, user: dict, tenant: str):
    return None  # explicitly never posts to books


async def post_voucher(voucher: dict, user: dict, tenant: str) -> dict:
    """Dispatch an approved voucher to its posting handler.

    Returns a small posting result describing what happened. Raises if a type's
    posting is not yet implemented (so it cannot be silently approved-as-posted).
    """
    spec = spec_for(voucher["parent_type"])
    if not spec.implemented:
        raise HTTPException(
            501,
            f"Posting for '{voucher['parent_type']}' is not implemented yet in the voucher "
            f"engine. Use the existing module for this domain, or approve once the handler ships.",
        )
    fn = _HANDLERS.get(voucher["parent_type"])
    if not fn:
        return {"posted": False, "reason": "no handler"}
    result = await fn(voucher, user, tenant)
    return {
        "posted": bool(result),
        "journal_entry_id": result.get("id") if result else None,
        "parent_type": voucher["parent_type"],
    }


async def auto_reverse_due(tenant: str, as_of: Optional[str], user: dict) -> int:
    """Sweep: post the mirror of any reversing_journal whose effective_date has
    arrived. Idempotent via a `reversed_for` marker. Returns count reversed."""
    as_of = as_of or date.today().isoformat()
    src = await db[JE_COLL].find(
        {"tenant_id": tenant, "tags": "REVERSING", "effective_date": {"$lte": as_of}},
        {"_id": 0},
    ).to_list(2000)
    count = 0
    for je in src:
        already = await db[JE_COLL].find_one({"reversed_for": je["id"]}, {"_id": 0, "id": 1})
        if already:
            continue
        mirror_lines = [
            {**l, "debit": l.get("credit", 0), "credit": l.get("debit", 0)} for l in je.get("lines", [])
        ]
        mirror = {
            "id": str(uuid.uuid4()),
            "entry_number": await _next_je_number(tenant),
            "tenant_id": tenant,
            "date": as_of,
            "narration": f"Auto-reversal of {je.get('entry_number')}",
            "lines": mirror_lines,
            "status": "POSTED",
            "fiscal_year": je.get("fiscal_year"),
            "tags": ["AUTO", "REVERSING_MIRROR"],
            "reversed_for": je["id"],
            "reports_only": True,
            "total_debit": je.get("total_credit", 0),
            "total_credit": je.get("total_debit", 0),
            "created_by": user.get("id", "system"),
            "created_at": now_iso(),
        }
        await db[JE_COLL].insert_one(mirror)
        await log_audit("CREATE", JE_COLL, mirror["id"], user, new_values={k: v for k, v in mirror.items() if k != "_id"})
        count += 1
    return count
