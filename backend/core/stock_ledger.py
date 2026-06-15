"""Stock ledger posting service — the DB layer over the valuation engine.

Every stock movement is an append-only StockLedgerEntry. On-hand qty and value
are always derived by replaying entries through core.stock_valuation, never
stored denormalised, so valuation can never drift from the ledger.

Outward movements (qty < 0) are priced by the item's valuation_method using all
its prior entries. Inward movements carry the supplied rate.
"""
from datetime import date

from .db import db
from .stock_valuation import value_movements
from .utils import log_audit, new_id, now_iso

LEDGER = "stock_ledger_entries"


async def _item_method(stock_item_id: str) -> str:
    item = await db.stock_items.find_one(
        {"id": stock_item_id}, {"_id": 0, "valuation_method": 1}
    )
    return (item or {}).get("valuation_method", "WEIGHTED_AVG")


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
    ).to_list(100000)


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
        method = await _item_method(stock_item_id)
        history = await _prior_entries(stock_item_id, godown_id)
        this_move = {"qty": qty, "entry_date": entry_date}
        result = value_movements(history + [this_move], method)
        priced = result.priced_movements[-1]
        rate = priced["rate"]
        value = priced["value"]
    else:
        rate = float(rate or 0.0)
        value = round(qty * rate, 4)

    entry = {
        "id": new_id(),
        "stock_item_id": stock_item_id,
        "godown_id": godown_id,
        "batch_id": batch_id,
        "serial_id": serial_id,
        "qty": float(qty),
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
    ).to_list(100000)
    method = await _item_method(stock_item_id)
    result = value_movements(entries, method)
    return {
        "stock_item_id": stock_item_id,
        "godown_id": godown_id,
        "qty": result.closing_qty,
        "value": result.closing_value,
        "method": method,
    }
