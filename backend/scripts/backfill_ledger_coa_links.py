"""Backfill master_ledgers.coa_account_id for ledgers created before it was required.

Usage (from the backend/ directory):
    python scripts/backfill_ledger_coa_links.py [--dry-run]

Why this exists
----------------
master_ledgers (the Tally-style Group/Ledger hierarchy used by the voucher
engine) and chart_of_accounts (the code-keyed hierarchy every financial
report groups by) were two entirely separate, unlinked tables. A new
coa_account_id column links a ledger to the chart_of_accounts row whose code
gets stamped onto its journal lines at posting time (core/voucher_engine.py).
Ledgers created before this link existed have coa_account_id = NULL, which
now blocks them from posting (see _ledger_coa in voucher_engine.py) until
someone assigns one.

This script best-effort auto-matches each unmapped ledger to a
chart_of_accounts row using two signals:
  1. Nature: the ledger's master_groups.nature (Asset/Liability/Income/
     Expense — no Equity value exists in this hierarchy) is upper-cased to
     match chart_of_accounts.account_type (ASSET/LIABILITY/INCOME/EXPENSE).
  2. Name similarity: within that nature, the CoA account whose name shares
     the most words with the ledger's name (case-insensitive token overlap).
     A ledger named "HDFC Bank Current A/c" under an Asset group should match
     "Bank Account - Primary" over "Cash in Hand" if "bank" appears in both.

A ledger only gets auto-matched when there is at least one shared token
between its name and the candidate's name (a nature match alone is not
enough — that would silently pick an arbitrary account within the nature).
Ledgers that don't confidently match are left NULL and reported so an admin
can assign them by hand in Masters > Ledgers. This mirrors the "block
posting" behavior already enforced by core/voucher_engine.py rather than
guessing — a wrong auto-assigned account_code would be worse than an
explicit block.

Design mirrors scripts/backfill_stock_transactions.py: idempotent (only
touches rows where coa_account_id IS NULL), --dry-run prints what would
change without writing, chunked updates.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import defaultdict
from pathlib import Path

_BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv
load_dotenv(_BACKEND / ".env")

from sqlalchemy import text

from core.db import engine

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(name: str) -> set[str]:
    return set(_WORD_RE.findall((name or "").lower()))


_FETCH_UNMAPPED_LEDGERS_SQL = text("""
    SELECT l.id, l.name, l.group_id, g.nature
    FROM master_ledgers l
    LEFT JOIN master_groups g ON g.id = l.group_id
    WHERE l.coa_account_id IS NULL AND (l.is_deleted IS NULL OR l.is_deleted = FALSE)
    ORDER BY l.name
""")

_FETCH_COA_SQL = text("""
    SELECT id, code, name, account_type
    FROM chart_of_accounts
    WHERE is_deleted IS NULL OR is_deleted = FALSE
""")

_UPDATE_SQL = text("""
    UPDATE master_ledgers SET coa_account_id = :coa_account_id WHERE id = :id
""")


async def main(dry_run: bool) -> None:
    async with engine.begin() as conn:
        ledgers = (await conn.execute(_FETCH_UNMAPPED_LEDGERS_SQL)).mappings().all()
        coa_rows = (await conn.execute(_FETCH_COA_SQL)).mappings().all()

    by_type: dict[str, list] = defaultdict(list)
    for a in coa_rows:
        by_type[(a["account_type"] or "").upper()].append(a)

    matched, unmatched = [], []
    for l in ledgers:
        nature = (l["nature"] or "").upper()  # Asset/Liability/Income/Expense -> ASSET/...
        candidates = by_type.get(nature, [])
        ledger_tokens = _tokens(l["name"])

        best, best_score = None, 0
        for a in candidates:
            score = len(ledger_tokens & _tokens(a["name"]))
            if score > best_score:
                best, best_score = a, score

        if best and best_score > 0:
            matched.append((l, best))
        else:
            unmatched.append(l)

    print(f"{len(ledgers)} ledger(s) with no coa_account_id.")
    print(f"  -> {len(matched)} auto-matched by nature + name overlap.")
    print(f"  -> {len(unmatched)} left unmapped (no confident match) — assign these by hand.")

    if matched:
        print("\nMatches" + (" (dry-run, not written)" if dry_run else "") + ":")
        for l, a in matched:
            print(f"  {l['name']!r:40s} -> {a['code']} {a['name']!r}")

    if unmatched:
        print("\nUnmapped (need manual assignment in Masters > Ledgers):")
        for l in unmatched:
            print(f"  {l['name']!r} (nature={l['nature']!r})")

    if dry_run or not matched:
        return

    async with engine.begin() as conn:
        await conn.execute(
            _UPDATE_SQL,
            [{"id": l["id"], "coa_account_id": a["id"]} for l, a in matched],
        )
    print(f"\nUpdated {len(matched)} ledger(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print matches without writing anything.")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
