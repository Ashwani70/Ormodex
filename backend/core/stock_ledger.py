"""Stock ledger posting service — the DB layer over the valuation engine.

Every stock movement is an append-only StockLedgerEntry. On-hand qty and value
are always derived by replaying entries through core.stock_valuation, never
stored denormalised, so valuation can never drift from the ledger.

Outward movements (qty < 0) are priced by the item's valuation_method using all
its prior entries. Inward movements carry the supplied rate.
"""
from datetime import date

from .db import db
from .stock_valuation import resolve_method, value_movements
from .utils import log_audit, new_id, now_iso

LEDGER = "stock_ledger_entries"


async def _company_default_method() -> str | None:
    """The company-wide default valuation method, or None if unset.

    Stored in ``company.extra.inventory_valuation_method`` (JSONB) so it needs
    no schema migration and matches how the rest of the app packs settings.
    """
    company = await db.companies.find_one({}, {"_id": 0, "extra": 1}) or {}
    extra = company.get("extra") or {}
    return extra.get("inventory_valuation_method")


async def _item_valuation(stock_item_id: str) -> tuple[str, float]:
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
        item.get("valuation_method"), await _company_default_method()
    )
    return method, float(std or 0.0)


async def _item_method(stock_item_id: str) -> str:
    """Back-compat shim: effective method only (used by callers that don't
    need the standard cost). Prefer ``_item_valuation`` in new code."""
    method, _ = await _item_valuation(stock_item_id)
    return method


async def item_valuation_configs(stock_item_ids: list[str]) -> dict[str, tuple[str, float]]:
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
    company_default = await _company_default_method()
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

    Returns the persisted entry (with computed rate/value).
    """
    entry_date = entry_date or date.today().isoformat()

    if qty < 0:
        # Price the outward move: replay history + this move under the item's method.
        method, standard_cost = await _item_valuation(stock_item_id)
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
    }
    await db[LEDGER].insert_one(entry)
    entry.pop("_id", None)
    await log_audit("CREATE", LEDGER, entry["id"], user, new_values=entry)
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
