"""Migration 015 — Universal Cheque Printing: validators + indexes.

Adds cheque_templates and cheque_transactions collections, and a partial unique
index that enforces "one cheque number per bank account" across committed
(printed/cancelled) cheques while still allowing draft re-use.
"""
import logging

from migrations import collmod_safe

logger = logging.getLogger(__name__)


async def run(db):
    # ── cheque_templates ──────────────────────────────────────────────────────
    await collmod_safe(db, "cheque_templates", {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["id", "template_name", "bank_name"],
            "properties": {
                "id": {"bsonType": "string"},
                "template_name": {"bsonType": "string"},
                "bank_name": {"bsonType": "string"},
                "cheque_width_mm": {"bsonType": ["int", "double"], "minimum": 1},
                "cheque_height_mm": {"bsonType": ["int", "double"], "minimum": 1},
                "field_positions": {"bsonType": "array"},
                "is_active": {"bsonType": "bool"},
                "archived": {"bsonType": "bool"},
            },
        }
    })
    await db.cheque_templates.create_index("id", unique=True)
    await db.cheque_templates.create_index([("bank_name", 1), ("archived", 1)])

    # ── cheque_transactions ───────────────────────────────────────────────────
    await collmod_safe(db, "cheque_transactions", {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["id", "bank_account_id", "cheque_number", "payee_name", "amount", "status"],
            "properties": {
                "id": {"bsonType": "string"},
                "bank_account_id": {"bsonType": "string"},
                "cheque_number": {"bsonType": "string"},
                "payee_name": {"bsonType": "string"},
                "amount": {"bsonType": ["int", "double"], "exclusiveMinimum": 0},
                "status": {"bsonType": "string", "enum": ["draft", "printed", "cancelled"]},
            },
        }
    })
    await db.cheque_transactions.create_index("id", unique=True)
    await db.cheque_transactions.create_index("bank_account_id")
    # DB-level guarantee of cheque-number uniqueness per account for committed
    # cheques (mirrors the app-level check in the router; partial so drafts and
    # other statuses don't collide).
    await db.cheque_transactions.create_index(
        [("bank_account_id", 1), ("cheque_number", 1)],
        unique=True,
        partialFilterExpression={"status": {"$in": ["printed", "cancelled"]}},
        name="uniq_cheque_no_per_account",
    )
