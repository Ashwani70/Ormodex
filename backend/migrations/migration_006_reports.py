"""Migration 006 — Reports deeper: indexes for the reporting engine + summaries."""
import logging

logger = logging.getLogger(__name__)


async def run(db):
    # Ledger query acceleration — the engine matches on status+date and unwinds lines.
    await db.journal_entries.create_index([("status", 1), ("date", 1)])
    await db.journal_entries.create_index("lines.account_code")
    await db.journal_entries.create_index("lines.cost_center")
    await db.journal_entries.create_index("branch")
    await db.journal_entries.create_index("fiscal_year")

    # Materialized summaries
    await db.report_summaries.create_index("fy", unique=True)

    # Saved views (per user)
    await db.report_saved_views.create_index("id", unique=True)
    await db.report_saved_views.create_index([("user_id", 1), ("name", 1)])

    logger.info("Migration 006 — Reports deeper applied")
