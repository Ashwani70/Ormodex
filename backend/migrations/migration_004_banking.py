"""Migration 004 — Banking PDC: JSON Schema validators + indexes + seed defaults."""
import logging

logger = logging.getLogger(__name__)


async def run(db):
    # ── pdcs ─────────────────────────────────────────────────────────────────
    await db.command({
        "collMod": "pdcs",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "type", "party_id", "cheque_no", "amount", "instrument_date", "status"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "type": {"bsonType": "string", "enum": ["issued", "received"]},
                    "status": {"bsonType": "string", "enum": ["PENDING", "PRESENTED", "CLEARED", "BOUNCED", "CANCELLED"]},
                    "amount": {"bsonType": ["int", "double"], "minimum": 0},
                    "instrument_date": {"bsonType": "string"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.pdcs.create_index("id", unique=True)
    await db.pdcs.create_index([("type", 1), ("status", 1)])
    await db.pdcs.create_index("instrument_date")
    await db.pdcs.create_index("party_id")
    await db.pdcs.create_index("pdc_no")

    # ── cheque_formats ───────────────────────────────────────────────────────
    await db.command({
        "collMod": "cheque_formats",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "name", "bank_name"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "name": {"bsonType": "string"},
                    "bank_name": {"bsonType": "string"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.cheque_formats.create_index("id", unique=True)
    await db.cheque_formats.create_index("name")

    # ── bank_feed_imports ────────────────────────────────────────────────────
    await db.bank_feed_imports.create_index("id", unique=True, sparse=True)
    await db.bank_feed_imports.create_index("bank_account_id")

    # ── bank_statement_lines ─────────────────────────────────────────────────
    await db.command({
        "collMod": "bank_statement_lines",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "bank_account_id", "txn_date"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "bank_account_id": {"bsonType": "string"},
                    "match_status": {"bsonType": "string", "enum": ["UNMATCHED", "MATCHED", "IGNORED"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.bank_statement_lines.create_index("id", unique=True)
    await db.bank_statement_lines.create_index([("bank_account_id", 1), ("match_status", 1)])
    await db.bank_statement_lines.create_index("txn_date")

    # ── interest_rules ───────────────────────────────────────────────────────
    await db.command({
        "collMod": "interest_rules",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "name", "rate_pct_pa"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "name": {"bsonType": "string"},
                    "rate_pct_pa": {"bsonType": ["int", "double"], "minimum": 0},
                    "basis": {"bsonType": "string", "enum": ["simple", "compound"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.interest_rules.create_index("id", unique=True)
    await db.interest_rules.create_index("party_id", sparse=True)

    # ── bank_accounts ─────────────────────────────────────────────────────────
    await db.bank_accounts.create_index("id", unique=True, sparse=True)
    await db.bank_accounts.create_index("name")

    logger.info("Migration 004 — Banking PDC applied")

    await _seed_banking_defaults(db)


async def _seed_banking_defaults(db):
    if await db.interest_rules.count_documents({}) == 0:
        from core.utils import new_id, now_iso
        rules = [
            {"id": new_id(), "name": "Standard Overdue Interest (18% PA)", "party_id": None, "rate_pct_pa": 18.0, "grace_days": 7, "basis": "simple", "min_amount": 0.0, "created_at": now_iso()},
            {"id": new_id(), "name": "Export Overdue (LIBOR+2%, 30-day grace)", "party_id": None, "rate_pct_pa": 8.0, "grace_days": 30, "basis": "compound", "min_amount": 10000.0, "created_at": now_iso()},
        ]
        await db.interest_rules.insert_many(rules)

    if await db.cheque_formats.count_documents({}) == 0:
        from core.utils import new_id, now_iso
        await db.cheque_formats.insert_one({
            "id": new_id(),
            "name": "Standard HDFC A4",
            "bank_name": "HDFC Bank",
            "fields": [
                {"field": "payee", "x": 120, "y": 45, "font_size": 12, "font": "Arial"},
                {"field": "amount_numeric", "x": 400, "y": 45, "font_size": 12, "font": "Arial"},
                {"field": "amount_words", "x": 80, "y": 65, "font_size": 10, "font": "Arial"},
                {"field": "date", "x": 420, "y": 25, "font_size": 11, "font": "Arial"},
            ],
            "micr_line": "⑆123456789⑆ 001234⑆ 0001⑈",
            "created_at": now_iso(),
        })
