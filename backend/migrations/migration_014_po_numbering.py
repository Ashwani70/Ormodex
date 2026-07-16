"""Migration 014 — Configurable Purchase Order numbering.

- Unique index on purchase_orders_v2.po_number (the core uniqueness guarantee).
- po_number_audit collection + validator + indexes for the change trail.
- Seed default numbering settings (AUTO, prefix "PO") if none exist.
"""
import logging

from migrations import collmod_safe

logger = logging.getLogger(__name__)


async def run(db):
    # ── purchase_orders_v2: unique PO number ─────────────────────────────────
    # Partial index so legacy rows without a po_number don't trip the unique
    # constraint (Mongo treats missing keys as null, which would collide).
    await db.purchase_orders_v2.create_index(
        "po_number", unique=True,
        partialFilterExpression={"po_number": {"$type": "string"}},
        name="uniq_po_number",
    )

    # ── po_number_audit ──────────────────────────────────────────────────────
    await collmod_safe(db, "po_number_audit", {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["id", "purchase_order_id", "new_po_number", "changed_by"],
            "properties": {
                "id": {"bsonType": "string"},
                "purchase_order_id": {"bsonType": "string"},
                "old_po_number": {"bsonType": ["string", "null"]},
                "new_po_number": {"bsonType": "string"},
                "changed_by": {"bsonType": "string"},
                "reason": {"bsonType": ["string", "null"]},
                "changed_at": {"bsonType": "string"},
            },
        }
    })
    await db.po_number_audit.create_index("id", unique=True)
    await db.po_number_audit.create_index("purchase_order_id")
    await db.po_number_audit.create_index("changed_at")

    # ── po_numbering_settings (singleton) ────────────────────────────────────
    await db.po_numbering_settings.create_index("id", unique=True)
    if await db.po_numbering_settings.count_documents({}) == 0:
        from core.po_numbering import DEFAULT_SETTINGS
        from core.utils import now_iso
        await db.po_numbering_settings.insert_one({
            **DEFAULT_SETTINGS, "created_at": now_iso(), "updated_at": now_iso(),
        })

    logger.info("Migration 014 — PO numbering applied")
