"""Migration 011 — Data & Integration: indexes for keys, webhooks, backups."""
import logging

logger = logging.getLogger(__name__)


async def run(db):
    # ── api_keys ──────────────────────────────────────────────────────────────
    await db.api_keys.create_index("id", unique=True)
    await db.api_keys.create_index("key_hash", unique=True)
    await db.api_keys.create_index("active")

    # ── webhook_subscriptions ─────────────────────────────────────────────────
    await db.command({
        "collMod": "webhook_subscriptions",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "url", "events"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "url": {"bsonType": "string"},
                    "events": {"bsonType": "array"},
                    "active": {"bsonType": "bool"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.webhook_subscriptions.create_index("id", unique=True)
    await db.webhook_subscriptions.create_index([("active", 1), ("events", 1)])

    # ── webhook_deliveries ────────────────────────────────────────────────────
    await db.webhook_deliveries.create_index("id", unique=True)
    await db.webhook_deliveries.create_index([("status", 1), ("next_attempt_at", 1)])
    await db.webhook_deliveries.create_index("subscription_id")

    # ── backups ───────────────────────────────────────────────────────────────
    await db.backups.create_index("id", unique=True)
    await db.backups.create_index("created_at")

    logger.info("Migration 011 — Data & Integration applied")
