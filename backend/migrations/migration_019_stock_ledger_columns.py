"""Migration 019 — Fix stock_ledger_entries schema.

The original schema used legacy column names (qty_in/qty_out/txn_date/doc_type)
that don't match what stock_ledger.post_entry actually writes (qty/rate/value/
entry_date/movement_type/source_doc_type/source_doc_id/serial_id). This caused
all inventory reports to return empty/zero results.

Adds the missing columns; legacy columns are kept for backward compatibility.
"""
import logging

logger = logging.getLogger(__name__)

ADD_COLUMNS_SQL = """
DO $$
BEGIN
    -- Core fields written by post_entry
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stock_ledger_entries' AND column_name='qty') THEN
        ALTER TABLE stock_ledger_entries ADD COLUMN qty NUMERIC(18,4);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stock_ledger_entries' AND column_name='value') THEN
        ALTER TABLE stock_ledger_entries ADD COLUMN value NUMERIC(18,4);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stock_ledger_entries' AND column_name='movement_type') THEN
        ALTER TABLE stock_ledger_entries ADD COLUMN movement_type TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stock_ledger_entries' AND column_name='source_doc_type') THEN
        ALTER TABLE stock_ledger_entries ADD COLUMN source_doc_type TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stock_ledger_entries' AND column_name='entry_date') THEN
        ALTER TABLE stock_ledger_entries ADD COLUMN entry_date TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stock_ledger_entries' AND column_name='serial_id') THEN
        ALTER TABLE stock_ledger_entries ADD COLUMN serial_id TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='stock_ledger_entries' AND column_name='extra') THEN
        ALTER TABLE stock_ledger_entries ADD COLUMN extra JSONB;
    END IF;

    -- Backfill entry_date from txn_date for any rows written by the old schema
    UPDATE stock_ledger_entries
    SET entry_date = txn_date
    WHERE entry_date IS NULL AND txn_date IS NOT NULL;

    -- Backfill qty from qty_in - qty_out for old rows
    UPDATE stock_ledger_entries
    SET qty = COALESCE(qty_in, 0) - COALESCE(qty_out, 0)
    WHERE qty IS NULL AND (qty_in IS NOT NULL OR qty_out IS NOT NULL);

    -- Backfill value from value_in - value_out for old rows
    UPDATE stock_ledger_entries
    SET value = COALESCE(value_in, 0) - COALESCE(value_out, 0)
    WHERE value IS NULL AND (value_in IS NOT NULL OR value_out IS NOT NULL);

    -- Backfill source_doc_type from doc_type for old rows
    UPDATE stock_ledger_entries
    SET source_doc_type = doc_type
    WHERE source_doc_type IS NULL AND doc_type IS NOT NULL;

    -- Performance index on entry_date for report date-range queries
    IF NOT EXISTS (SELECT 1 FROM pg_indexes
                   WHERE tablename='stock_ledger_entries'
                   AND indexname='ix_stock_ledger_entry_date') THEN
        CREATE INDEX ix_stock_ledger_entry_date
            ON stock_ledger_entries (stock_item_id, entry_date);
    END IF;
END$$;
"""


async def run(db):
    try:
        from core.db import engine
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text(ADD_COLUMNS_SQL))
        logger.info("Migration 019: stock_ledger_entries columns added/backfilled OK")
    except Exception as exc:
        logger.error("Migration 019 failed: %s", exc)
        raise
