"""Migration 010 — POS: validators + indexes (incl. client_uuid idempotency)."""
import logging

logger = logging.getLogger(__name__)


async def run(db):
    # ── pos_sessions ──────────────────────────────────────────────────────────
    await db.command({
        "collMod": "pos_sessions",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "terminal", "cashier_id", "status"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "terminal": {"bsonType": "string"},
                    "cashier_id": {"bsonType": "string"},
                    "status": {"bsonType": "string", "enum": ["open", "closed"]},
                    "opening_cash": {"bsonType": ["int", "double"], "minimum": 0},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.pos_sessions.create_index("id", unique=True)
    await db.pos_sessions.create_index([("terminal", 1), ("status", 1)])
    await db.pos_sessions.create_index("cashier_id")

    # ── pos_sales ─────────────────────────────────────────────────────────────
    await db.command({
        "collMod": "pos_sales",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "client_uuid", "session_id", "grand_total"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "client_uuid": {"bsonType": "string"},
                    "session_id": {"bsonType": "string"},
                    "grand_total": {"bsonType": ["int", "double"], "minimum": 0},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.pos_sales.create_index("id", unique=True)
    # client_uuid UNIQUE is the idempotency guard — a replayed offline sale can
    # never insert twice.
    await db.pos_sales.create_index("client_uuid", unique=True)
    await db.pos_sales.create_index("session_id")
    await db.pos_sales.create_index("created_at")

    logger.info("Migration 010 — POS applied")
