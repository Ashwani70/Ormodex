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
    # ----- Inventory (posting implemented; signed stock-ledger movements) -----
    "delivery_note": TypeSpec("inventory", posts_to_stock=True, note="Sales dispatch → stock out"),
    "receipt_note": TypeSpec("inventory", posts_to_stock=True, note="Purchase receipt → stock in"),
    "rejections_in": TypeSpec("inventory", posts_to_stock=True),
    "rejections_out": TypeSpec("inventory", posts_to_stock=True),
    "physical_stock": TypeSpec("inventory", posts_to_stock=True, note="Adjustment: signed variance per line"),
    "material_in": TypeSpec("inventory", posts_to_stock=True),
    "material_out": TypeSpec("inventory", posts_to_stock=True),
    "job_work_challan": TypeSpec("inventory", posts_to_stock=True, note="Job work issue → WIP out (§143 window via reconciliation)"),
    "job_work_material_inward": TypeSpec("inventory", posts_to_stock=True, note="Job work receipt → WIP/FG in"),
    "non_returnable_gate_pass": TypeSpec("inventory", posts_to_stock=True),
    "stock_journal": TypeSpec("inventory", posts_to_stock=True, note="BOM consume→produce; cost rolls into FG"),
    "stock_transfer_interunit": TypeSpec("inventory", posts_to_stock=True, note="Out source + in dest; taxable+e-way when GSTIN differs"),
    "stock_transfer_material_interunit": TypeSpec("inventory", posts_to_stock=True, note="Out source + in dest at cost"),
    # ----- Order (no stock/books posting; track fulfilled vs pending via links) -----
    "purchase_order": TypeSpec("order", note="Receipt tracking via links chain"),
    "sales_order": TypeSpec("order", note="Dispatch tracking via links chain"),
    "job_work_in_order": TypeSpec("order"),
    "job_work_out_order": TypeSpec("order"),
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
    if voucher.get("statutory"):
        entry["statutory"] = voucher["statutory"]
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


# ───────────────────────── inventory posting ─────────────────────────

LEDGER = "stock_ledger_entries"

# parent_type → (movement_type, sign). sign +1 = stock in, -1 = stock out.
# WIP/FG semantics ride on movement_type for reporting; the ledger sign is what
# moves quantity. job_work_challan issues to a job worker (out of own stock);
# job_work_material_inward brings WIP/finished goods back in.
INVENTORY_DIRECTION: dict[str, tuple[str, int]] = {
    "receipt_note": ("PURCHASE_IN", +1),
    "material_in": ("MATERIAL_IN", +1),
    "rejections_in": ("REJECTION_IN", +1),
    "delivery_note": ("SALES_OUT", -1),
    "material_out": ("MATERIAL_OUT", -1),
    "rejections_out": ("REJECTION_OUT", -1),
    "job_work_challan": ("JOBWORK_WIP_OUT", -1),
    "job_work_material_inward": ("JOBWORK_WIP_IN", +1),
    "non_returnable_gate_pass": ("GATE_PASS_OUT", -1),
}


async def _stock_already_posted(voucher_id: str) -> bool:
    """Duplicate-movement guard: any ledger entry already sourced from this voucher?"""
    hit = await db[LEDGER].find_one(
        {"source_doc_type": "voucher", "source_doc_id": voucher_id}, {"_id": 0, "id": 1})
    return hit is not None


async def _post_inventory_movements(voucher: dict, user: dict, tenant: str, *, reverse: bool = False) -> Optional[dict]:
    """Post signed stock-ledger entries for a voucher's inventory_lines.

    Idempotent on (source_doc_type='voucher', source_doc_id=voucher id) — re-posting
    is a no-op. `reverse=True` flips the sign for cancellation/reversal documents
    and tags entries so they net the original out.
    """
    from .stock_ledger import post_entry  # local import avoids a circular dependency

    pt = voucher["parent_type"]
    movement_type, sign = INVENTORY_DIRECTION.get(pt, (pt.upper(), +1))
    if reverse:
        sign = -sign
        movement_type = f"REVERSAL_{movement_type}"

    lines = voucher.get("inventory_lines") or []
    if not lines:
        return None

    # Guard: never double-post the same voucher's movements (concurrent approves,
    # re-runs). For reversal we key on a distinct source so it can post once too.
    src_id = f"{voucher['id']}::rev" if reverse else voucher["id"]
    already = await db[LEDGER].find_one(
        {"source_doc_type": "voucher", "source_doc_id": src_id}, {"_id": 0, "id": 1})
    if already:
        return {"already_posted": True, "movements": 0}

    posted_ids = []
    for ln in lines:
        qty = abs(float(ln.get("qty", 0))) * sign
        if qty == 0:
            continue
        entry = await post_entry(
            stock_item_id=ln["stock_item_id"],
            godown_id=ln.get("location_id") or "default",
            qty=qty,
            movement_type=movement_type,
            rate=float(ln.get("rate") or 0.0) if qty > 0 else None,
            batch_id=ln.get("batch"),
            serial_id=ln.get("serial"),
            source_doc_type="voucher",
            source_doc_id=src_id,
            entry_date=reporting_date(voucher),
            user=user,
        )
        posted_ids.append(entry["id"])
    return {"movements": len(posted_ids), "ledger_entry_ids": posted_ids, "movement_type": movement_type}


@handler(
    "receipt_note", "material_in", "rejections_in",
    "delivery_note", "material_out", "rejections_out",
    "job_work_challan", "job_work_material_inward", "non_returnable_gate_pass",
)
async def _post_inventory(voucher: dict, user: dict, tenant: str):
    return await _post_inventory_movements(voucher, user, tenant)


@handler("physical_stock")
async def _post_physical_stock(voucher: dict, user: dict, tenant: str):
    """Stock adjustment / physical count: post the signed variance per line.

    Each inventory_line carries the *adjustment* qty (signed): + to correct up,
    − to correct down. Idempotent on the voucher id."""
    from .stock_ledger import post_entry

    if await _stock_already_posted(voucher["id"]):
        return {"already_posted": True, "movements": 0}
    posted_ids = []
    for ln in voucher.get("inventory_lines") or []:
        qty = float(ln.get("qty", 0))
        if qty == 0:
            continue
        entry = await post_entry(
            stock_item_id=ln["stock_item_id"],
            godown_id=ln.get("location_id") or "default",
            qty=qty,
            movement_type="ADJUSTMENT",
            rate=float(ln.get("rate") or 0.0) if qty > 0 else None,
            batch_id=ln.get("batch"),
            source_doc_type="voucher",
            source_doc_id=voucher["id"],
            entry_date=reporting_date(voucher),
            user=user,
        )
        posted_ids.append(entry["id"])
    return {"movements": len(posted_ids), "ledger_entry_ids": posted_ids, "movement_type": "ADJUSTMENT"}


def _split_consume_produce(lines: list) -> tuple[list, list]:
    """Partition stock_journal lines into (consume, produce).

    A line is a consume if role=='consume' or qty<0; a produce if role=='produce'
    or qty>0. role wins when present, so callers may pass positive qty for both."""
    consume, produce = [], []
    for ln in lines:
        role = ln.get("role")
        qty = float(ln.get("qty", 0))
        if role == "consume" or (role is None and qty < 0):
            consume.append(ln)
        elif role == "produce" or (role is None and qty > 0):
            produce.append(ln)
    return consume, produce


@handler("stock_journal")
async def _post_stock_journal(voucher: dict, user: dict, tenant: str):
    """Manufacturing / stock journal: consume components → produce finished goods,
    and/or move stock between godowns. Idempotent on the voucher id.

    Costing: the produced item's rate is the rolled-up cost of what was consumed
    (sum of consumed outward value) apportioned across produced qty — so value
    flows from inputs to output rather than being client-asserted. A pure
    inter-godown move (consume in godown A, produce same item in godown B) carries
    cost across at the consumed rate.
    """
    from .stock_ledger import post_entry

    if await _stock_already_posted(voucher["id"]):
        return {"already_posted": True, "movements": 0}

    consume, produce = _split_consume_produce(voucher.get("inventory_lines") or [])
    posted_ids = []
    consumed_value = 0.0

    # 1) Consume (outward) — priced by the ledger's valuation engine.
    for ln in consume:
        qty = abs(float(ln.get("qty", 0)))
        if qty == 0:
            continue
        entry = await post_entry(
            stock_item_id=ln["stock_item_id"],
            godown_id=ln.get("location_id") or "default",
            qty=-qty,
            movement_type="MFG_CONSUME",
            batch_id=ln.get("batch"), serial_id=ln.get("serial"),
            source_doc_type="voucher", source_doc_id=voucher["id"],
            entry_date=reporting_date(voucher), user=user,
        )
        posted_ids.append(entry["id"])
        consumed_value += abs(float(entry.get("value", 0)))

    # 2) Produce (inward) — rate rolled up from consumed value, unless the line
    # gives an explicit rate (e.g. by-product at a fixed cost).
    produced_qty = sum(abs(float(ln.get("qty", 0))) for ln in produce)
    rolled_rate = round(consumed_value / produced_qty, 4) if produced_qty > 0 else 0.0
    for ln in produce:
        qty = abs(float(ln.get("qty", 0)))
        if qty == 0:
            continue
        rate = float(ln["rate"]) if ln.get("rate") not in (None, "", 0) else rolled_rate
        entry = await post_entry(
            stock_item_id=ln["stock_item_id"],
            godown_id=ln.get("location_id") or "default",
            qty=qty,
            movement_type="MFG_PRODUCE",
            rate=rate,
            batch_id=ln.get("batch"), serial_id=ln.get("serial"),
            source_doc_type="voucher", source_doc_id=voucher["id"],
            entry_date=reporting_date(voucher), user=user,
        )
        posted_ids.append(entry["id"])

    return {"movements": len(posted_ids), "ledger_entry_ids": posted_ids,
            "movement_type": "STOCK_JOURNAL", "consumed_value": round(consumed_value, 2),
            "produced_rate": rolled_rate}


@handler("stock_transfer_interunit", "stock_transfer_material_interunit")
async def _post_interunit_transfer(voucher: dict, user: dict, tenant: str):
    """Inter-unit stock transfer: out of the source location, in to the destination.

    Each inventory_line moves one item; the source is `location_id` and the
    destination is `to_location_id`. Cost carries across at the outward (consumed)
    rate. When the two units have *different* GSTINs the move is a taxable supply
    (the voucher should carry statutory.gst + statutory.eway, and an accounting
    voucher is raised separately); when the same GSTIN it's an internal transfer
    at cost. This handler does the stock legs; the taxable-supply accounting leg
    is posted via a linked sales/purchase voucher (kept separate by design).
    """
    from .stock_ledger import post_entry

    if await _stock_already_posted(voucher["id"]):
        return {"already_posted": True, "movements": 0}

    interstate = bool((voucher.get("statutory") or {}).get("gst"))
    posted_ids = []
    for ln in voucher.get("inventory_lines") or []:
        qty = abs(float(ln.get("qty", 0)))
        if qty == 0:
            continue
        src = ln.get("location_id") or "default"
        dest = ln.get("to_location_id") or ln.get("tracking_ref") or "default"
        if src == dest:
            raise HTTPException(400, "Inter-unit transfer requires distinct source/destination locations")
        out = await post_entry(
            stock_item_id=ln["stock_item_id"], godown_id=src, qty=-qty,
            movement_type="TRANSFER_OUT", batch_id=ln.get("batch"), serial_id=ln.get("serial"),
            source_doc_type="voucher", source_doc_id=voucher["id"],
            entry_date=reporting_date(voucher), user=user,
        )
        # Carry cost across at the rate that left the source.
        carry_rate = float(out.get("rate") or 0.0)
        inn = await post_entry(
            stock_item_id=ln["stock_item_id"], godown_id=dest, qty=qty, rate=carry_rate,
            movement_type="TRANSFER_IN", batch_id=ln.get("batch"), serial_id=ln.get("serial"),
            source_doc_type="voucher", source_doc_id=voucher["id"],
            entry_date=reporting_date(voucher), user=user,
        )
        posted_ids += [out["id"], inn["id"]]

    return {"movements": len(posted_ids), "ledger_entry_ids": posted_ids,
            "movement_type": "INTERUNIT_TRANSFER", "taxable_supply": interstate}


async def _record_tds_entry_if_needed(voucher: dict, tenant: str, user: dict):
    statutory = voucher.get("statutory")
    if not statutory:
        return
    tds = statutory.get("tds")
    if not tds:
        return

    if hasattr(tds, "model_dump"):
        tds_data = tds.model_dump()
    elif isinstance(tds, dict):
        tds_data = tds
    else:
        return

    section_code = tds_data.get("section_code")
    if not section_code:
        return

    rate = float(tds_data.get("rate") or 0.0)
    amount = float(tds_data.get("amount") or 0.0)

    base_amount = tds_data.get("base_amount")
    if base_amount is not None:
        base_amount = float(base_amount)
    else:
        if rate > 0:
            base_amount = amount / (rate / 100.0)
        else:
            base_amount = amount

    net_amount = base_amount - amount

    party_id = voucher.get("party_id")
    party_name = "Unknown Party"
    party_pan = None

    if party_id:
        supp = await db["suppliers"].find_one(tenant_filter(tenant, {"id": party_id}), {"_id": 0, "name": 1, "pan_number": 1})
        if not supp:
            supp = await db["vendors"].find_one(tenant_filter(tenant, {"id": party_id}), {"_id": 0, "name": 1, "pan_number": 1})
        if not supp:
            supp = await db["customers"].find_one(tenant_filter(tenant, {"id": party_id}), {"_id": 0, "name": 1, "pan_number": 1})

        if supp:
            party_name = supp.get("name", party_name)
            party_pan = supp.get("pan_number")

    if party_name == "Unknown Party" and voucher.get("party_name"):
        party_name = voucher["party_name"]

    vdate = voucher.get("date") or date.today().isoformat()
    try:
        parts = vdate.split("-")
        if len(parts) >= 2:
            return_period = f"{parts[1]}{parts[0]}"
        else:
            return_period = date.today().strftime("%m%Y")
    except Exception:
        return_period = date.today().strftime("%m%Y")

    existing = await db["tds_entries"].find_one(
        tenant_filter(tenant, {"source_collection": "vouchers_v2", "source_id": voucher["id"]})
    )
    if existing:
        return

    tds_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant,
        "entry_date": vdate,
        "party_id": party_id,
        "party_name": party_name,
        "party_pan": party_pan,
        "tds_section": section_code,
        "base_amount": round(base_amount, 2),
        "tds_rate": rate,
        "tds_amount": round(amount, 2),
        "net_amount": round(net_amount, 2),
        "return_period": return_period,
        "status": "DEDUCTED",
        "source_collection": "vouchers_v2",
        "source_id": voucher["id"],
        "created_by": user.get("id", "system"),
        "created_at": now_iso(),
    }

    await db["tds_entries"].insert_one(tds_doc)
    tds_doc.pop("_id", None)
    await log_audit("CREATE", "tds_entries", tds_doc["id"], user, new_values=tds_doc)


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
    if result:
        await _record_tds_entry_if_needed(voucher, tenant, user)
    out = {"posted": bool(result), "parent_type": voucher["parent_type"]}
    if isinstance(result, dict):
        # Accounting handlers return a journal entry (has 'id'); inventory/journal/
        # transfer handlers return movement details. Surface everything the handler
        # reports except the raw JE 'id', which is exposed as journal_entry_id.
        if "id" in result:
            out["journal_entry_id"] = result["id"]
        for k, v in result.items():
            if k != "id":
                out[k] = v
        # An idempotent no-op (already posted) still counts as posted.
        if result.get("already_posted"):
            out["posted"] = True
    return out


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


# ═══════════════════════ Reversal / cancellation of posted documents ═══════════════════════

async def reverse_posting(voucher: dict, user: dict, tenant: str) -> dict:
    """Reverse a posted voucher's effects with explicit counter-movements.

    - Stock: posts opposite-sign ledger entries (idempotent, keyed `<id>::rev`),
      so on-hand nets back to pre-posting.
    - Books: posts a reversing (reports-aware) journal mirror of the original JE.
    Idempotent: a second call is a no-op. Returns what was reversed.
    """
    result: dict = {"reversed_stock": 0, "reversed_journal": False}

    spec = spec_for(voucher["parent_type"])

    # Stock side.
    if spec.posts_to_stock:
        inv = await _post_inventory_movements(voucher, user, tenant, reverse=True)
        if inv and not inv.get("already_posted"):
            result["reversed_stock"] = inv.get("movements", 0)

    # Books side: mirror the original journal entry (swap Dr/Cr), once.
    if spec.posts_to_books:
        orig = await db[JE_COLL].find_one(
            {"source_collection": "vouchers_v2", "source_id": voucher["id"], "tags": {"$nin": ["REVERSAL"]}},
            {"_id": 0})
        if orig:
            already = await db[JE_COLL].find_one({"reversed_for": orig["id"]}, {"_id": 0, "id": 1})
            if not already:
                mirror_lines = [
                    {**l, "debit": l.get("credit", 0), "credit": l.get("debit", 0)} for l in orig.get("lines", [])
                ]
                fy = await db.fiscal_years.find_one({"is_active": True})
                mirror = {
                    "id": str(uuid.uuid4()),
                    "entry_number": await _next_je_number(tenant),
                    "tenant_id": tenant,
                    "date": date.today().isoformat(),
                    "narration": f"Reversal of {orig.get('entry_number')} ({voucher.get('voucher_no')})",
                    "lines": mirror_lines,
                    "status": "POSTED",
                    "fiscal_year": (fy or {}).get("name") or orig.get("fiscal_year"),
                    "tags": ["AUTO", "VOUCHER", "REVERSAL"],
                    "source_collection": "vouchers_v2",
                    "source_id": voucher["id"],
                    "reversed_for": orig["id"],
                    "total_debit": orig.get("total_credit", 0),
                    "total_credit": orig.get("total_debit", 0),
                    "created_by": user.get("id", "system"),
                    "created_at": now_iso(),
                }
                await db[JE_COLL].insert_one(mirror)
                await log_audit("CREATE", JE_COLL, mirror["id"], user,
                                new_values={k: v for k, v in mirror.items() if k != "_id"})
                result["reversed_journal"] = True
                result["reversal_journal_entry_id"] = mirror["id"]
    return result


# ═══════════════════════ Cross-cutting rule helpers ═══════════════════════

VOUCHERS = "vouchers_v2"

# Return-window statute (CGST §143): inputs must come back within 1 year,
# capital goods within 3 years, else deemed supply.
RETURN_WINDOW_DAYS = {"inputs": 365, "capital_goods": 365 * 3}


# ── Order → fulfilment chain ──

async def order_fulfilment(order_id: str, tenant: str) -> dict:
    """Compute fulfilled vs pending qty per stock_item for an order, from the
    links chain: any approved voucher that references this order pulls down its
    open quantity. Works for purchase_order / sales_order / job_work_*_order."""
    order = await db[VOUCHERS].find_one(tenant_filter(tenant, {"id": order_id}), {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")

    ordered: dict[str, float] = {}
    for ln in order.get("inventory_lines", []):
        ordered[ln["stock_item_id"]] = ordered.get(ln["stock_item_id"], 0.0) + float(ln.get("qty", 0))

    # Downstream vouchers (delivery/GRN/invoice/inward) that link back to this
    # order. Only *posted* documents actually fulfil (movements written); reversed
    # ones become 'cancelled' and drop out automatically.
    downstream = await db[VOUCHERS].find(
        tenant_filter(tenant, {"status": "posted", "links.ref_voucher_id": order_id}),
        {"_id": 0},
    ).to_list(5000)

    fulfilled: dict[str, float] = {}
    for v in downstream:
        for ln in v.get("inventory_lines", []):
            fulfilled[ln["stock_item_id"]] = fulfilled.get(ln["stock_item_id"], 0.0) + float(ln.get("qty", 0))

    rows = []
    all_complete = True
    for item_id, oqty in ordered.items():
        fqty = round(fulfilled.get(item_id, 0.0), 4)
        pending = round(oqty - fqty, 4)
        if pending > 1e-9:
            all_complete = False
        rows.append({
            "stock_item_id": item_id, "ordered_qty": round(oqty, 4),
            "fulfilled_qty": fqty,
            "pending_qty": max(0.0, pending),
            # Backorder = unfulfilled balance still owed (same as pending here, but
            # named explicitly for SO dispatch / PO receipt tracking).
            "backorder_qty": max(0.0, pending),
            "over_fulfilled_qty": max(0.0, -pending),
        })

    return {
        "order_id": order_id,
        "order_no": order.get("voucher_no"),
        "parent_type": order.get("parent_type"),
        "lines": rows,
        "fully_fulfilled": all_complete and bool(rows),
        "has_backorder": any(r["backorder_qty"] > 1e-9 for r in rows),
        "fulfilling_voucher_ids": [v["id"] for v in downstream],
    }


# ── Job-work lifecycle (CGST §143) ──

def _days_between(start_iso: str, end_iso: str) -> int:
    try:
        return (date.fromisoformat(end_iso[:10]) - date.fromisoformat(start_iso[:10])).days
    except Exception:
        return 0


async def job_work_reconciliation(tenant: str, as_of: Optional[str] = None) -> dict:
    """Reconcile job-work-out challans against material-inward vouchers and flag
    return-window breaches. Returns per-challan pending qty + alert level.

    Goods type for the window is read from the challan's statutory.extra.goods_type
    ('inputs' | 'capital_goods'), defaulting to inputs (the 1-year window)."""
    as_of = as_of or date.today().isoformat()
    challans = await db[VOUCHERS].find(
        tenant_filter(tenant, {"parent_type": "job_work_challan", "status": "posted"}),
        {"_id": 0},
    ).to_list(5000)

    out = []
    for ch in challans:
        sent: dict[str, float] = {}
        for ln in ch.get("inventory_lines", []):
            sent[ln["stock_item_id"]] = sent.get(ln["stock_item_id"], 0.0) + float(ln.get("qty", 0))

        inwards = await db[VOUCHERS].find(
            tenant_filter(tenant, {"parent_type": "job_work_material_inward", "status": "posted",
                                   "links.ref_voucher_id": ch["id"]}),
            {"_id": 0},
        ).to_list(5000)
        received: dict[str, float] = {}
        for iw in inwards:
            for ln in iw.get("inventory_lines", []):
                received[ln["stock_item_id"]] = received.get(ln["stock_item_id"], 0.0) + float(ln.get("qty", 0))

        pending = {k: round(v - received.get(k, 0.0), 4) for k, v in sent.items()}
        total_pending = round(sum(max(0.0, p) for p in pending.values()), 4)

        goods_type = ((ch.get("statutory") or {}).get("extra") or {}).get("goods_type", "inputs")
        window = RETURN_WINDOW_DAYS.get(goods_type, RETURN_WINDOW_DAYS["inputs"])
        age = _days_between(ch.get("date", as_of), as_of)
        days_left = window - age

        if total_pending <= 1e-9:
            alert = "closed"
        elif days_left < 0:
            alert = "deemed_supply"      # window breached → deemed supply
        elif days_left <= 30:
            alert = "due_soon"
        else:
            alert = "open"

        out.append({
            "challan_id": ch["id"], "challan_no": ch.get("voucher_no"),
            "challan_date": ch.get("date"), "goods_type": goods_type,
            "window_days": window, "age_days": age, "days_left": days_left,
            "total_pending_qty": total_pending, "alert": alert,
            "pending_by_item": pending,
        })
    return {"as_of": as_of, "challans": out,
            "breached": [c for c in out if c["alert"] == "deemed_supply"]}


async def itc04_data(tenant: str, from_date: str, to_date: str) -> dict:
    """ITC-04 dataset: goods sent to job workers (challans) and received back
    (inwards) within a period. Reporting-grade extract, not the filed return."""
    challans = await db[VOUCHERS].find(
        tenant_filter(tenant, {"parent_type": "job_work_challan", "status": "posted",
                               "date": {"$gte": from_date, "$lte": to_date}}),
        {"_id": 0},
    ).to_list(10000)
    inwards = await db[VOUCHERS].find(
        tenant_filter(tenant, {"parent_type": "job_work_material_inward", "status": "posted",
                               "date": {"$gte": from_date, "$lte": to_date}}),
        {"_id": 0},
    ).to_list(10000)
    return {
        "from_date": from_date, "to_date": to_date,
        "table_4_goods_sent": [
            {"challan_no": c.get("voucher_no"), "date": c.get("date"), "party_id": c.get("party_id"),
             "lines": c.get("inventory_lines", [])} for c in challans
        ],
        "table_5a_goods_received": [
            {"inward_no": i.get("voucher_no"), "date": i.get("date"), "party_id": i.get("party_id"),
             "links": i.get("links", []), "lines": i.get("inventory_lines", [])} for i in inwards
        ],
    }


# ── Reversing / Memorandum exclusion + effective-date cutoff ──

def statutory_je_filter(tenant: str, *, as_of: Optional[str] = None,
                        use_effective_date: bool = False) -> dict:
    """Mongo filter for journal entries that belong in *statutory* reports
    (trial balance, GST ledgers). Excludes reports-only entries (reversing
    journals + their mirrors) and memorandum. Applies an effective-date cutoff
    when requested (effective_date drives the cutoff if set, else date)."""
    q: dict = {"tenant_id": tenant, "status": "POSTED", "reports_only": {"$ne": True}}
    # memorandum never creates a JE, but guard tag-wise too.
    q["tags"] = {"$nin": ["MEMORANDUM"]}
    if as_of:
        field = "effective_date" if use_effective_date else "date"
        q[field] = {"$lte": as_of}
    return q


def management_je_filter(tenant: str, *, as_of: Optional[str] = None,
                         use_effective_date: bool = False) -> dict:
    """Filter for *management* reports — includes reversing/memorandum entries
    that statutory reports exclude."""
    q: dict = {"tenant_id": tenant, "status": "POSTED"}
    if as_of:
        field = "effective_date" if use_effective_date else "date"
        q[field] = {"$lte": as_of}
    return q


def reporting_date(voucher: dict) -> Optional[str]:
    """The date a voucher counts on in reports: effective_date when set, else date."""
    return voucher.get("effective_date") or voucher.get("date")


# ═══════════════════════ Automated reconciliation engine ═══════════════════════
#
# Reconciliation matches *posted* documents and auto-advances them posted →
# reconciled, replacing the purely-manual /reconcile transition. It is conservative:
# a document is reconciled only when its match condition is fully met, and the run
# is idempotent (already-reconciled docs are skipped). Each match writes the
# evidence onto the document for audit.

ORDER_TYPES = {"sales_order", "purchase_order", "job_work_in_order", "job_work_out_order"}


async def _mark_reconciled(voucher_id: str, tenant: str, user: dict, evidence: dict):
    old = await db[VOUCHERS].find_one(tenant_filter(tenant, {"id": voucher_id}), {"_id": 0})
    if not old or old.get("status") == "reconciled":
        return False
    await db[VOUCHERS].update_one(
        tenant_filter(tenant, {"id": voucher_id}),
        {"$set": {"status": "reconciled", "reconciled_by": user.get("id", "system"),
                  "reconciled_at": now_iso(), "reconciliation": evidence, "updated_at": now_iso()}},
    )
    await log_audit("UPDATE", VOUCHERS, voucher_id, user,
                    old_values=old, new_values={**old, "status": "reconciled", "reconciliation": evidence})
    return True


async def reconcile_orders(tenant: str, user: dict) -> dict:
    """Auto-reconcile orders that are fully fulfilled by posted downstream docs.

    A posted order whose every line's pending_qty == 0 → reconciled, with the
    fulfilling voucher ids recorded as evidence. Partially fulfilled or back-
    ordered orders are left as-is."""
    orders = await db[VOUCHERS].find(
        tenant_filter(tenant, {"parent_type": {"$in": list(ORDER_TYPES)}, "status": "posted"}),
        {"_id": 0},
    ).to_list(5000)
    reconciled = []
    for o in orders:
        ff = await order_fulfilment(o["id"], tenant)
        if ff["fully_fulfilled"]:
            if await _mark_reconciled(o["id"], tenant, user,
                                      {"rule": "order_fully_fulfilled",
                                       "by": ff["fulfilling_voucher_ids"]}):
                reconciled.append(o["id"])
    return {"rule": "order_fulfilment", "reconciled": reconciled, "count": len(reconciled)}


async def reconcile_receipts_to_bills(tenant: str, user: dict) -> dict:
    """Auto-reconcile posted goods-receipts once a posted purchase bill links them.

    Matches receipt_note ← purchase voucher via the bill's links chain (3-way
    match readiness). The receipt is reconciled; the bill is the evidence."""
    bills = await db[VOUCHERS].find(
        tenant_filter(tenant, {"parent_type": "purchase", "status": {"$in": ["posted", "reconciled"]}}),
        {"_id": 0},
    ).to_list(5000)
    receipt_to_bill: dict[str, str] = {}
    for b in bills:
        for lk in b.get("links", []):
            if lk.get("ref_type") in ("receipt_note", "grn"):
                receipt_to_bill[lk["ref_voucher_id"]] = b["id"]

    reconciled = []
    for receipt_id, bill_id in receipt_to_bill.items():
        rc = await db[VOUCHERS].find_one(
            tenant_filter(tenant, {"id": receipt_id, "parent_type": "receipt_note", "status": "posted"}),
            {"_id": 0})
        if rc and await _mark_reconciled(receipt_id, tenant, user,
                                         {"rule": "matched_purchase_bill", "bill_id": bill_id}):
            reconciled.append(receipt_id)
    return {"rule": "grn_to_bill", "reconciled": reconciled, "count": len(reconciled)}


async def run_reconciliation(tenant: str, user: dict, rules: Optional[list[str]] = None) -> dict:
    """Run the reconciliation rules (all by default). Idempotent."""
    available = {
        "order_fulfilment": reconcile_orders,
        "grn_to_bill": reconcile_receipts_to_bills,
    }
    selected = rules or list(available)
    results = []
    total = 0
    for name in selected:
        fn = available.get(name)
        if not fn:
            raise HTTPException(400, f"Unknown reconciliation rule '{name}'. Known: {sorted(available)}")
        res = await fn(tenant, user)
        results.append(res)
        total += res["count"]
    return {"ok": True, "total_reconciled": total, "rules": results}
