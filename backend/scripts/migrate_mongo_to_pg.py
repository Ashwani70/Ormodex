"""MongoDB → PostgreSQL data migration script.

Usage (from the backend/ directory):
    python scripts/migrate_mongo_to_pg.py [--collections col1 col2 ...] [--dry-run]

What it does:
1. Connects to MongoDB (MONGO_URL / DB_NAME from .env).
2. Connects to PostgreSQL (DATABASE_URL from .env) and runs create_all so the
   tables exist.
3. For each collection, dumps every document from Mongo and upserts it into the
   matching PostgreSQL table using INSERT … ON CONFLICT (id) DO UPDATE.
4. Prints a per-collection summary (copied, skipped, errors).

Design decisions:
- JSONB columns accept any dict/list from MongoDB documents — no reshaping needed.
- Only columns present in the SQLAlchemy model are written; unknown MongoDB fields
  go into `extra` (JSONB) if that column exists, otherwise they are dropped.
- The script is idempotent: run it multiple times safely.
- Soft-deleted documents (is_deleted=True in Mongo) are migrated as-is.
- The `_id` ObjectId field is always dropped.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# ── bootstrap path & env ──────────────────────────────────────────────────────
_BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv
load_dotenv(_BACKEND / ".env")

# ── collection → model map (import after path setup) ─────────────────────────
from core.db import Base, engine
from core.utils import _table
import core.schema  # noqa: F401 — registers all models

# All collections that have corresponding PG tables.
ALL_COLLECTIONS: list[str] = [
    "users", "refresh_tokens",
    "vendors", "customers", "leads",
    "products", "product_categories", "warehouses", "stock_items", "godowns",
    "stock_transactions", "stock_transfers", "batches", "physical_verifications",
    "purchase_orders", "purchase_orders_v2", "goods_receipt_notes_v2",
    "purchase_bills", "purchase_returns",
    "quotations", "sales_orders", "invoices", "credit_notes", "dispatches",
    "proforma_invoices",
    "journal_entries", "vouchers", "voucher_counters", "chart_of_accounts",
    "expense_entries", "expense_categories",
    "bank_accounts", "bank_entries", "bank_statements", "bank_statement_lines",
    "pdcs", "cheque_transactions", "cheque_formats",
    "employees", "attendance", "attendance_logs", "leaves", "leave_types",
    "holidays", "shifts", "salary_structures", "pay_components",
    "payroll_runs", "payslips", "statutory_params", "fnf_settlements",
    "tds_declarations",
    "master_ledgers", "master_groups", "cost_centers", "fiscal_years",
    "currencies", "voucher_types",
    "gst_records", "gst_filing_cache", "gstin_cache", "gst_reconciliation",
    "tds_entries", "tcs_entries", "eway_bills",
    "fixed_assets", "asset_categories", "asset_depreciation_runs",
    "asset_transactions",
    "projects", "project_costs", "tasks", "timesheet_entries",
    "boms", "work_orders", "production_journals", "wastage_entries",
    "job_work_challans", "job_work_receipts", "rate_tables",
    "approval_policies", "approval_requests", "approval_steps",
    "pos_sales", "pos_sessions",
    "price_lists", "discount_schemes",
    "webhook_subscriptions", "webhook_deliveries",
    "portal_users",
    "branches", "inter_branch_transfers",
    "budgets",
    "audit_logs", "counters", "companies",
    "verification_settings", "einvoice_settings", "purchase_settings",
    "theme_settings", "po_numbering_settings",
    "report_summaries", "report_saved_views",
    "uploaded_files", "ocr_documents", "verification_logs",
    "ai_chat_history", "ai_conversations",
    "api_keys", "payment_links", "advances", "interest_rules",
    "qc_reports", "vendor_bill_submissions", "bank_feed_imports",
    "po_number_audit",
]


def _clean(doc: dict) -> dict:
    """Drop _id and coerce any non-JSON-serialisable values to strings."""
    doc.pop("_id", None)
    result: dict = {}
    for k, v in doc.items():
        try:
            json.dumps(v)
            result[k] = v
        except (TypeError, ValueError):
            result[k] = str(v)
    return result


def _split_columns(collection: str, doc: dict) -> tuple[dict, dict]:
    """Split a Mongo document into (known_cols, extra) for PG insertion."""
    Model = _table(collection)
    known: dict = {}
    extra: dict = {}
    for k, v in doc.items():
        if hasattr(Model, k):
            known[k] = v
        else:
            extra[k] = v
    # If the model has an `extra` JSONB column, pack unknown fields there.
    if extra and hasattr(Model, "extra"):
        existing_extra = known.get("extra") or {}
        if isinstance(existing_extra, dict):
            known["extra"] = {**extra, **existing_extra}
        else:
            known["extra"] = extra
    return known, extra


async def migrate_collection(
    mongo_db,
    pg_session,
    collection: str,
    dry_run: bool = False,
) -> dict[str, int]:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    Model = _table(collection)
    cursor = mongo_db[collection].find({}, {"_id": 0})
    docs = await cursor.to_list(length=None)

    copied = skipped = errors = 0
    # Group cleaned docs by their exact set of known columns — an
    # INSERT ... ON CONFLICT DO UPDATE statement's column list is fixed, so
    # only same-shaped rows (which is the common case: documents in one
    # Mongo collection almost always share a schema) can share one
    # executemany-style batched call. Each group still executes as one
    # statement against a LIST of param dicts (SQLAlchemy batches that into
    # one DBAPI executemany), instead of one execute() per document — was
    # one round trip per row, and a large collection (journal_entries,
    # stock_transactions) can be tens of thousands of documents.
    groups: dict[tuple[str, ...], list[dict]] = {}
    group_raw: dict[tuple[str, ...], list[dict]] = {}
    for raw in docs:
        doc = _clean(raw)
        if not doc.get("id"):
            skipped += 1
            continue
        known, _ = _split_columns(collection, doc)
        if not known:
            skipped += 1
            continue
        key = tuple(sorted(known.keys()))
        groups.setdefault(key, []).append(known)
        group_raw.setdefault(key, []).append(raw)

    if dry_run:
        copied = sum(len(v) for v in groups.values())
        return {"copied": copied, "skipped": skipped, "errors": errors}

    for key, rows in groups.items():
        # .values() scoped to this group's exact column set — without it,
        # SQLAlchemy compiles the INSERT against every model column, and a
        # batched execute() with row dicts that don't carry ALL of those
        # keys fails with a missing-parameter error. The literal values
        # here are placeholders; execute() below supplies the real
        # per-row values from `rows`.
        placeholder_values = {k: None for k in key}
        update_cols = {k: pg_insert(Model).excluded[k] for k in key if k != "id"}
        stmt = (
            pg_insert(Model)
            .values(**placeholder_values)
            .on_conflict_do_update(index_elements=["id"], set_=update_cols)
        )
        try:
            # Chunked at 500 rows per executemany call so one collection's
            # whole dataset doesn't build a single oversized batch.
            for i in range(0, len(rows), 500):
                await pg_session.execute(stmt, rows[i:i + 500])
            copied += len(rows)
        except Exception:
            # A batch-level failure falls back to one-by-one for just this
            # group, so a single bad row's exact id is still identifiable
            # (matches the original script's per-row error reporting)
            # instead of losing the whole same-shaped batch to one bad row.
            for row, raw in zip(rows, group_raw[key]):
                try:
                    row_update_cols = {k: v for k, v in row.items() if k != "id"}
                    row_stmt = pg_insert(Model).values(**row).on_conflict_do_update(
                        index_elements=["id"], set_=row_update_cols,
                    )
                    await pg_session.execute(row_stmt)
                    copied += 1
                except Exception as exc:
                    errors += 1
                    print(f"  [ERROR] {collection} id={raw.get('id', '?')}: {exc}")

    await pg_session.commit()

    return {"copied": copied, "skipped": skipped, "errors": errors}


async def main(collections: list[str], dry_run: bool) -> None:
    try:
        import motor.motor_asyncio as motor
    except ImportError:
        print("ERROR: motor is required for reading MongoDB. Install it temporarily:")
        print("  pip install motor")
        sys.exit(1)

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "gravity_erp")
    print(f"Connecting to MongoDB: {mongo_url}/{db_name}")

    mongo_client = motor.AsyncIOMotorClient(mongo_url)
    mongo_db = mongo_client[db_name]

    # Bootstrap PG schema
    print(f"Bootstrapping PostgreSQL schema …")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Schema ready.")

    from sqlalchemy.ext.asyncio import AsyncSession
    from core.db import AsyncSessionLocal

    totals = {"copied": 0, "skipped": 0, "errors": 0}
    async with AsyncSessionLocal() as pg_session:
        for col in collections:
            try:
                _table(col)  # validate mapping exists
            except RuntimeError:
                print(f"  [SKIP] {col} — no PG model registered, skipping")
                continue
            print(f"  Migrating {col} …", end="", flush=True)
            stats = await migrate_collection(mongo_db, pg_session, col, dry_run=dry_run)
            print(f" copied={stats['copied']} skipped={stats['skipped']} errors={stats['errors']}")
            for k in totals:
                totals[k] += stats[k]

    await engine.dispose()
    mongo_client.close()

    print()
    print("=" * 50)
    print(f"Migration {'(DRY RUN) ' if dry_run else ''}complete:")
    print(f"  Copied : {totals['copied']}")
    print(f"  Skipped: {totals['skipped']}")
    print(f"  Errors : {totals['errors']}")
    if totals["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate MongoDB data to PostgreSQL")
    parser.add_argument(
        "--collections", nargs="*", default=ALL_COLLECTIONS,
        help="Space-separated list of collections to migrate (default: all)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Read from Mongo but don't write to PostgreSQL",
    )
    args = parser.parse_args()
    asyncio.run(main(args.collections, args.dry_run))
