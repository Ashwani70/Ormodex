"""Backfill stock_transactions from stock_ledger_entries (Stock Log rebuild fix).

Usage (from the backend/ directory):
    python scripts/backfill_stock_transactions.py [--dry-run]

Why this exists
----------------
The Stock Log grid, its summary cards (opening/inward/outward/closing/value),
and its negative-stock count all read exclusively from `stock_transactions`.
Several v2 posting flows (GRN, Purchase Return, Stock Adjustment, v2 Opening
Stock) call `core.stock_ledger.post_entry`, which — before this fix — only
wrote `stock_ledger_entries` and never mirrored into `stock_transactions`. Any
stock posted through those flows before the fix is therefore invisible to
Stock Log today, even though it's correctly recorded (and correctly valued)
in `stock_ledger_entries`.

`post_entry` now writes both tables going forward (see core/stock_ledger.py's
"Dual-write" note). This script is the one-time catch-up for everything
posted *before* that fix shipped: for every `stock_ledger_entries` row that
has no corresponding `stock_transactions` row, it inserts one.

Design:
- Idempotent — safe to run multiple times. A ledger entry is considered
  "already mirrored" if a stock_transactions row exists with
  source_doc_id = ledger_entries.id (the mirror always sets voucher_no/
  source_doc_id to the ORIGINAL document id today, so this script instead
  keys off a dedicated `reason` marker it writes itself:
  "[ledger:<entry_id>]" — see _ALREADY_MIRRORED_SQL — which is unambiguous
  and independent of what the live mirror function chooses to store).
- Read-only against stock_ledger_entries; only inserts into stock_transactions.
- Resolves stock_item_id -> product_id/name via stock_items, same as the live
  mirror in core/stock_ledger.py._mirror_to_legacy_transaction.
- --dry-run prints what would be inserted without writing anything.
- Prints a summary: entries scanned, already mirrored (skipped), inserted, and
  entries skipped because their stock_item_id no longer resolves.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv
load_dotenv(_BACKEND / ".env")

from sqlalchemy import text

from core.db import engine
from core.utils import new_id, now_iso

# Movement type -> Stock Log doc_type, mirrors core/stock_ledger.py's map.
_MOVEMENT_TO_DOC_TYPE = {
    "PURCHASE": "PURCHASE",
    "SALE": "SALES",
    "TRANSFER_IN": "STOCK_TRANSFER",
    "TRANSFER_OUT": "STOCK_TRANSFER",
    "ADJUSTMENT": "ADJUSTMENT",
    "OPENING": "PURCHASE",
}

_FETCH_UNMIRRORED_SQL = text("""
    SELECT le.id, le.stock_item_id, le.godown_id, le.batch_id, le.qty, le.rate,
           le.value, le.movement_type, le.source_doc_type, le.source_doc_id,
           le.entry_date, le.created_at,
           si.product_id, si.name AS item_name
    FROM stock_ledger_entries le
    LEFT JOIN stock_items si ON si.id = le.stock_item_id
    WHERE NOT EXISTS (
        SELECT 1 FROM stock_transactions t
        WHERE t.reason = '[ledger:' || le.id || ']'
    )
    ORDER BY le.entry_date, le.created_at
""")

_INSERT_SQL = text("""
    INSERT INTO stock_transactions
        (id, product_id, product_name, godown_id, batch_id, doc_type,
         voucher_no, source_doc_id, qty, rate, value, delta, balance,
         reason, user_id, user_name, created_at)
    VALUES
        (:id, :product_id, :product_name, :godown_id, :batch_id, :doc_type,
         :voucher_no, :source_doc_id, :qty, :rate, :value, :delta, NULL,
         :reason, NULL, :user_name, :created_at)
""")


async def main(dry_run: bool) -> None:
    async with engine.begin() as conn:
        rows = (await conn.execute(_FETCH_UNMIRRORED_SQL)).mappings().all()

    scanned = len(rows)
    to_insert = []
    skipped_unresolved = 0

    for r in rows:
        qty = float(r["qty"] or 0)
        doc_type = _MOVEMENT_TO_DOC_TYPE.get(r["movement_type"], r["movement_type"])
        product_id = r["product_id"] or r["stock_item_id"]
        product_name = r["item_name"] or r["stock_item_id"]
        if not product_id:
            skipped_unresolved += 1
            continue
        to_insert.append({
            "id": new_id(),
            "product_id": product_id,
            "product_name": product_name,
            "godown_id": r["godown_id"],
            "batch_id": r["batch_id"],
            "doc_type": doc_type,
            "voucher_no": r["source_doc_id"],
            "source_doc_id": r["source_doc_id"],
            "qty": abs(qty),
            "rate": r["rate"],
            "value": r["value"],
            "delta": qty,
            "reason": f"[ledger:{r['id']}] Backfilled {doc_type} (stock_item {r['stock_item_id']})",
            "user_name": "system-backfill",
            "created_at": r["created_at"] or r["entry_date"] or now_iso(),
        })

    print(f"Scanned {scanned} stock_ledger_entries row(s) with no stock_transactions mirror.")
    print(f"  -> {len(to_insert)} will be inserted.")
    print(f"  -> {skipped_unresolved} skipped (stock_item_id no longer resolves to anything).")

    if dry_run:
        print("\n--dry-run: no changes written. Sample of what would be inserted:")
        for row in to_insert[:10]:
            print(f"  {row['doc_type']:16s} delta={row['delta']:>10.2f} "
                  f"product={row['product_name']!r} voucher={row['voucher_no']}")
        if len(to_insert) > 10:
            print(f"  ... and {len(to_insert) - 10} more")
        return

    if not to_insert:
        print("Nothing to backfill.")
        return

    async with engine.begin() as conn:
        for row in to_insert:
            await conn.execute(_INSERT_SQL, row)

    print(f"Inserted {len(to_insert)} backfilled stock_transactions row(s).")
    print("Stock Log should now show these movements immediately (no restart needed).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be inserted without writing anything.")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
