"""Stock ledger posting service — the DB layer over the valuation engine.

Every stock movement is an append-only StockLedgerEntry. On-hand qty and value
are always derived by replaying entries through core.stock_valuation, never
stored denormalised, so valuation can never drift from the ledger.

Outward movements (qty < 0) are priced by the item's valuation_method using all
its prior entries. Inward movements carry the supplied rate.

Dual-write to `stock_transactions`
-----------------------------------
The Stock Log grid, its summary cards (opening/inward/outward/closing/value),
and its negative-stock count (routers/stock_log.py) all read exclusively from
`stock_transactions` — a separate, older table keyed by product_id/godown_id
rather than stock_item_id. Historically each v1 voucher router (purchase.py,
sales.py, job_work.py, manufacturing.py) wrote that table directly, while v2
flows (purchase_v2.py GRN/returns, inventory_v2.py adjustments/opening stock)
call `post_entry` and only ever wrote `stock_ledger_entries`. Result: any stock
posted through a v2 endpoint was invisible to Stock Log and skewed its
negative-stock count (inward legs missing, outward legs present).

`post_entry` now mirrors every posting into `stock_transactions` itself, so
this can't drift again — no call site needs to remember to do it separately
(Stock Transfer used to do this by hand; that's now redundant but harmless).
The mirror is best-effort: a failure there is logged and swallowed rather than
failing the ledger write, since stock_ledger_entries is the source of truth for
valuation and must never be blocked by a reporting-table write.

As of migration 022, `stock_ledger_entries` also carries product_id/
product_name/doc_type/voucher_no/user_id/user_name/reason directly (resolved
once per post_entry call, reused by the mirror) — a superset of
`stock_transactions`'s columns. Readers still use `stock_transactions`
exclusively today (routers/stock_log.py etc.); this is groundwork for
eventually repointing them and retiring the second table, not a completed
cutover — see the stock ledger unification project notes.

Transitional sync to `products.quantity`
------------------------------------------
As v1 direct-write call sites are migrated to call `post_entry` (stock ledger
unification, 2026-07), `products.quantity` stops being written by them
directly. But it is still read directly (not via product_stock_bridge) by
~13 call sites — dashboard/MIS KPIs, low-stock alerts, MRP shortage calc, and
every v1 call site not yet migrated — so `post_entry` keeps it in sync via a
best-effort `$inc`, the same way it keeps `stock_transactions` in sync. This
is a transitional shim, not a second source of truth: once every writer AND
reader of `products.quantity` is migrated (writers onto `post_entry`, readers
onto `product_stock_bridge`), the column and this sync should be retired.
"""
import logging
from datetime import date

from .db import db
from .stock_valuation import resolve_method, value_movements
from .tenant import DEFAULT_TENANT, resolve_tenant
from .utils import log_audit, new_id, now_iso

logger = logging.getLogger(__name__)

LEDGER = "stock_ledger_entries"
LEGACY_TXN = "stock_transactions"

# stock_ledger_entries.movement_type -> stock_transactions.doc_type. Stock Log
# renders unmapped values as-is (routers/stock_log.py _DOC_TYPE_LABELS), so an
# unrecognised movement_type still shows up, just unlabelled.
_MOVEMENT_TO_DOC_TYPE = {
    "PURCHASE": "PURCHASE",
    "SALE": "SALES",
    "SALE_RETURN": "SALES_RETURN",
    "TRANSFER_IN": "STOCK_TRANSFER",
    "TRANSFER_OUT": "STOCK_TRANSFER",
    "ADJUSTMENT": "ADJUSTMENT",
    "OPENING": "OPENING_STOCK",
}


async def _mirror_to_legacy_transaction(entry: dict) -> None:
    """Best-effort mirror of one stock_ledger_entries row into stock_transactions.

    `entry` already carries product_id/name/doc_type/voucher_no/reason/
    user_id/user_name — post_entry resolves and denormalizes those onto the
    ledger row itself now (migration 022), so this mirror is a pure reshape,
    no second stock_items lookup. Never raises — Stock Log visibility must
    not be able to break a stock posting.
    """
    try:
        qty = float(entry["qty"])
        await db[LEGACY_TXN].insert_one({
            "id": new_id(),
            "product_id": entry["product_id"],
            "product_name": entry["product_name"],
            "godown_id": entry.get("godown_id"),
            "batch_id": entry.get("batch_id"),
            "doc_type": entry["doc_type"],
            "source_doc_type": entry.get("source_doc_type"),
            "voucher_no": entry.get("source_doc_id"),
            "source_doc_id": entry.get("source_doc_id"),
            "qty": abs(qty),
            "rate": entry.get("rate"),
            "value": entry.get("value"),
            "uom": entry.get("uom"),
            "delta": qty,
            "balance": None,  # Stock Log computes running balance at read time
            "reason": entry["reason"],
            "user_id": entry.get("user_id"),
            "user_name": entry.get("user_name"),
            "created_at": entry.get("created_at") or now_iso(),
        })
        logger.info(
            "stock_ledger: mirrored entry %s (item=%s qty=%s) into stock_transactions",
            entry["id"], entry["stock_item_id"], qty,
        )
    except Exception:
        logger.exception(
            "stock_ledger: failed to mirror entry %s into stock_transactions "
            "(Stock Log grid will not show this movement until backfilled)",
            entry.get("id"),
        )
        return None


async def _sync_product_quantity(product_id: str | None, delta: float) -> None:
    """Best-effort denormalised products.quantity update, kept in sync so the
    ~13 call sites that still read products.quantity directly (dashboard KPIs,
    low-stock alerts, MRP shortage calc, and the not-yet-migrated v1 posting
    paths in purchase.py/sales.py/job_work.py/manufacturing.py) don't silently
    go stale as call sites are migrated to post_entry one at a time. This is a
    transitional shim, not the source of truth — stock_ledger_entries is;
    products.quantity should be retired once every writer and every reader in
    the table above (see stock ledger unification project notes) is migrated
    to read live stock via product_stock_bridge instead. Never raises for the
    same reason as the stock_transactions mirror.
    """
    if not product_id:
        return
    try:
        await db.products.update_one(
            {"id": product_id},
            {"$inc": {"quantity": delta}, "$set": {"updated_at": now_iso()}},
        )
    except Exception:
        logger.exception(
            "stock_ledger: failed to sync products.quantity for product %s (delta=%s)",
            product_id, delta,
        )


async def _company_default_method(tenant_id: str = DEFAULT_TENANT) -> str | None:
    """This tenant's default valuation method, or None if unset.

    Stored in ``company.extra.inventory_valuation_method`` (JSONB) so it needs
    no schema migration and matches how the rest of the app packs settings.
    """
    company = await db.companies.find_one({"tenant_id": tenant_id}, {"_id": 0, "extra": 1}) or {}
    extra = company.get("extra") or {}
    return extra.get("inventory_valuation_method")


async def _item_valuation(stock_item_id: str, tenant_id: str = DEFAULT_TENANT) -> tuple[str, float]:
    """Resolve an item's effective valuation method and standard cost.

    Method resolution is Item Override → Company Default → engine default,
    all via ``stock_valuation.resolve_method`` so there is a single source of
    truth for the precedence rule. ``standard_cost`` is only meaningful for the
    STANDARD_COST method but is always returned so callers stay simple.
    """
    item = await db.stock_items.find_one(
        {"id": stock_item_id},
        {"_id": 0, "valuation_method": 1, "standard_cost": 1, "extra": 1},
    ) or {}
    extra = item.get("extra") or {}
    std = item.get("standard_cost")
    if std is None:
        std = extra.get("standard_cost")
    method = resolve_method(
        item.get("valuation_method"), await _company_default_method(tenant_id)
    )
    return method, float(std or 0.0)


async def _item_method(stock_item_id: str, tenant_id: str = DEFAULT_TENANT) -> str:
    """Back-compat shim: effective method only (used by callers that don't
    need the standard cost). Prefer ``_item_valuation`` in new code."""
    method, _ = await _item_valuation(stock_item_id, tenant_id)
    return method


async def item_valuation_configs(
    stock_item_ids: list[str], tenant_id: str = DEFAULT_TENANT,
) -> dict[str, tuple[str, float]]:
    """Batched (method, standard_cost) resolution for many items in 2 queries.

    Public helper so report/aggregation endpoints can resolve each item's
    effective valuation the same way ``post_entry``/``on_hand`` do — Item
    Override → Company Default → engine default — without repeating the
    precedence logic or the ``standard_cost`` fetch per call site. Every
    requested id is present in the result (unknown items resolve to the company
    default with a 0 standard). Reads the company default once for the whole set.
    """
    ids = [sid for sid in dict.fromkeys(stock_item_ids) if sid]
    if not ids:
        return {}
    items = await db.stock_items.find(
        {"id": {"$in": ids}},
        {"_id": 0, "id": 1, "valuation_method": 1, "standard_cost": 1, "extra": 1},
    ).to_list(len(ids))
    company_default = await _company_default_method(tenant_id)
    by_id = {it["id"]: it for it in items}
    out: dict[str, tuple[str, float]] = {}
    for sid in ids:
        it = by_id.get(sid) or {}
        extra = it.get("extra") or {}
        std = it.get("standard_cost")
        if std is None:
            std = extra.get("standard_cost")
        out[sid] = (
            resolve_method(it.get("valuation_method"), company_default),
            float(std or 0.0),
        )
    return out


async def _prior_entries(stock_item_id: str, godown_id: str | None = None) -> list[dict]:
    """Ledger entries for an item, oldest-first (valuation needs full history).

    Scoped to a godown when given, so cost layers stay physically located —
    a FIFO outward from one godown consumes only that godown's layers.
    """
    q = {"stock_item_id": stock_item_id}
    if godown_id:
        q["godown_id"] = godown_id
    return await db[LEDGER].find(q, {"_id": 0}).sort(
        [("entry_date", 1), ("created_at", 1)]
    ).to_list(10000)


async def post_entry(
    *,
    stock_item_id: str,
    godown_id: str,
    qty: float,
    movement_type: str,
    rate: float | None = None,
    batch_id: str | None = None,
    serial_id: str | None = None,
    source_doc_type: str | None = None,
    source_doc_id: str | None = None,
    entry_date: str | None = None,
    user: dict | None = None,
) -> dict:
    """Append one signed StockLedgerEntry, pricing outward moves via the engine.

    Also mirrors into stock_transactions so the Stock Log grid sees it — see
    the module docstring's "Dual-write" note. Returns the persisted entry
    (with computed rate/value).
    """
    logger.info(
        "stock_ledger.post_entry: posting item=%s godown=%s qty=%s type=%s source=%s/%s",
        stock_item_id, godown_id, qty, movement_type, source_doc_type, source_doc_id,
    )
    entry_date = entry_date or date.today().isoformat()

    if qty < 0:
        # Price the outward move: replay history + this move under the item's method.
        method, standard_cost = await _item_valuation(stock_item_id, resolve_tenant(user))
        history = await _prior_entries(stock_item_id, godown_id)
        this_move = {"qty": qty, "entry_date": entry_date}
        result = value_movements(history + [this_move], method,
                                 standard_cost=standard_cost)
        priced = result.priced_movements[-1]
        rate = priced["rate"]
        value = priced["value"]
    else:
        # Inward: carry the supplied purchase rate. Under STANDARD_COST the
        # ledger row still records the actual purchase rate/value — valuation at
        # standard is applied when the history is replayed (on_hand / pricing an
        # outward move), so purchase-price variance stays recoverable.
        rate = (rate or 0.0)
        value = round(qty * rate, 4)

    # Resolved once, used both to denormalize onto this row (so
    # stock_ledger_entries is a complete superset of stock_transactions on
    # its own — see migration 022) and by the stock_transactions mirror
    # below, so this is a single stock_items lookup, not two.
    item = await db.stock_items.find_one(
        {"id": stock_item_id}, {"_id": 0, "id": 1, "name": 1, "product_id": 1, "uom": 1}
    ) or {}
    linked_product_id = item.get("product_id")
    doc_type = _MOVEMENT_TO_DOC_TYPE.get(movement_type, movement_type)

    entry = {
        "id": new_id(),
        "stock_item_id": stock_item_id,
        "godown_id": godown_id,
        "batch_id": batch_id,
        "serial_id": serial_id,
        "qty": qty,
        "rate": rate,
        "value": value,
        "movement_type": movement_type,
        "source_doc_type": source_doc_type,
        "source_doc_id": source_doc_id,
        "entry_date": entry_date,
        "created_at": now_iso(),
        "product_id": linked_product_id or stock_item_id,
        "product_name": item.get("name") or stock_item_id,
        "uom": item.get("uom") or "Nos",
        "doc_type": doc_type,
        "voucher_no": source_doc_id,
        "user_id": (user or {}).get("id"),
        "user_name": (user or {}).get("name", ""),
        "reason": f"{doc_type} (v2 stock_item {stock_item_id})",
    }
    await db[LEDGER].insert_one(entry)
    entry.pop("_id", None)
    logger.info(
        "stock_ledger.post_entry: inserted stock_ledger_entries id=%s rate=%s value=%s",
        entry["id"], rate, value,
    )
    await log_audit("CREATE", LEDGER, entry["id"], user, new_values=entry)
    await _mirror_to_legacy_transaction(entry)
    await _sync_product_quantity(linked_product_id, qty)
    logger.info("stock_ledger.post_entry: success for entry %s", entry["id"])
    return entry


async def on_hand(stock_item_id: str, godown_id: str | None = None) -> dict:
    """Current qty + value for an item (optionally a single godown)."""
    q = {"stock_item_id": stock_item_id}
    if godown_id:
        q["godown_id"] = godown_id
    entries = await db[LEDGER].find(q, {"_id": 0}).sort(
        [("entry_date", 1), ("created_at", 1)]
    ).to_list(10000)
    method, standard_cost = await _item_valuation(stock_item_id)
    result = value_movements(entries, method, standard_cost=standard_cost)
    return {
        "stock_item_id": stock_item_id,
        "godown_id": godown_id,
        "qty": result.closing_qty,
        "value": result.closing_value,
        "method": method,
    }


async def on_hand_bulk(stock_item_ids: list[str]) -> dict[str, dict]:
    """On-hand qty + value for many items in a fixed number of queries.

    The per-item ``on_hand`` does two round-trips each (ledger + method); calling
    it in a loop is an N+1 that's brutal on a high-latency remote DB. This loads
    *all* ledger entries for the given items and all their valuation methods in
    two queries total, then values each item's movements in Python.

    Returns ``{stock_item_id: {qty, value, method}}`` for every requested id
    (items with no movements come back as qty/value 0).
    """
    ids = [sid for sid in dict.fromkeys(stock_item_ids) if sid]
    if not ids:
        return {}

    # One query for item valuation config, one company-default read, one query
    # for all ledger entries — a fixed number of round-trips regardless of N.
    items = await db.stock_items.find(
        {"id": {"$in": ids}},
        {"_id": 0, "id": 1, "valuation_method": 1, "standard_cost": 1, "extra": 1},
    ).to_list(len(ids))
    company_default = await _company_default_method()
    cfg_by_id: dict[str, tuple[str, float]] = {}
    for it in items:
        extra = it.get("extra") or {}
        std = it.get("standard_cost")
        if std is None:
            std = extra.get("standard_cost")
        cfg_by_id[it["id"]] = (
            resolve_method(it.get("valuation_method"), company_default),
            float(std or 0.0),
        )

    entries = await db[LEDGER].find(
        {"stock_item_id": {"$in": ids}}, {"_id": 0}
    ).sort([("entry_date", 1), ("created_at", 1)]).to_list(1000000)

    by_item: dict[str, list[dict]] = {sid: [] for sid in ids}
    for e in entries:
        sid = e.get("stock_item_id")
        if sid in by_item:
            by_item[sid].append(e)

    out: dict[str, dict] = {}
    for sid in ids:
        method, standard_cost = cfg_by_id.get(sid, (resolve_method(None, company_default), 0.0))
        result = value_movements(by_item[sid], method, standard_cost=standard_cost)
        out[sid] = {
            "stock_item_id": sid,
            "qty": result.closing_qty,
            "value": result.closing_value,
            "method": method,
        }
    return out
