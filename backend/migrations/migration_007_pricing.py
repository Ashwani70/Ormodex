"""Migration 007 — Pricing & Schemes: validators + indexes."""
import logging

logger = logging.getLogger(__name__)


async def run(db):
    # ── price_lists ───────────────────────────────────────────────────────────
    await db.command({
        "collMod": "price_lists",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "name", "assigned_to"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "name": {"bsonType": "string"},
                    "currency": {"bsonType": "string"},
                    "assigned_to": {"bsonType": "object"},
                    "items": {"bsonType": "array"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.price_lists.create_index("id", unique=True)
    await db.price_lists.create_index("assigned_to.type")
    await db.price_lists.create_index("assigned_to.id")
    await db.price_lists.create_index("items.item_id")

    # ── discount_schemes ──────────────────────────────────────────────────────
    await db.command({
        "collMod": "discount_schemes",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "name", "type", "applies_to"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "name": {"bsonType": "string"},
                    "type": {"bsonType": "string", "enum": ["slab", "flat", "free_qty"]},
                    "applies_to": {"bsonType": "string", "enum": ["item", "group", "all"]},
                    "slabs": {"bsonType": "array"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.discount_schemes.create_index("id", unique=True)
    await db.discount_schemes.create_index([("applies_to", 1), ("applies_to_id", 1)])

    # ── godown_rates ──────────────────────────────────────────────────────────
    await db.command({
        "collMod": "godown_rates",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "item_id", "godown_id", "rate"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "item_id": {"bsonType": "string"},
                    "godown_id": {"bsonType": "string"},
                    "rate": {"bsonType": ["int", "double"], "minimum": 0},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.godown_rates.create_index("id", unique=True)
    await db.godown_rates.create_index([("item_id", 1), ("godown_id", 1)], unique=True)

    logger.info("Migration 007 — Pricing & Schemes applied")
