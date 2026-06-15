"""Migration 008 — Customer/Vendor Portal: validators + indexes."""
import logging

logger = logging.getLogger(__name__)


async def run(db):
    # ── portal_users (separate realm) ─────────────────────────────────────────
    await db.command({
        "collMod": "portal_users",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "party_id", "party_type", "email", "password_hash"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "party_id": {"bsonType": "string"},
                    "party_type": {"bsonType": "string", "enum": ["customer", "vendor"]},
                    "email": {"bsonType": "string"},
                    "status": {"bsonType": "string", "enum": ["active", "suspended", "disabled"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.portal_users.create_index("id", unique=True)
    await db.portal_users.create_index("email", unique=True)
    await db.portal_users.create_index([("party_type", 1), ("party_id", 1)])

    # ── vendor_bill_submissions ───────────────────────────────────────────────
    await db.command({
        "collMod": "vendor_bill_submissions",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "vendor_id", "amount", "status"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "vendor_id": {"bsonType": "string"},
                    "amount": {"bsonType": ["int", "double"], "minimum": 0},
                    "status": {"bsonType": "string",
                               "enum": ["submitted", "under_review", "approved", "paid", "rejected"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.vendor_bill_submissions.create_index("id", unique=True)
    await db.vendor_bill_submissions.create_index([("vendor_id", 1), ("status", 1)])
    await db.vendor_bill_submissions.create_index("status")

    # ── payment_links ─────────────────────────────────────────────────────────
    await db.command({
        "collMod": "payment_links",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "invoice_id", "amount", "status"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "invoice_id": {"bsonType": "string"},
                    "party_id": {"bsonType": "string"},
                    "amount": {"bsonType": ["int", "double"], "minimum": 0},
                    "status": {"bsonType": "string",
                               "enum": ["created", "paid", "failed", "expired"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.payment_links.create_index("id", unique=True)
    await db.payment_links.create_index("invoice_id")
    await db.payment_links.create_index("party_id")

    logger.info("Migration 008 — Customer/Vendor Portal applied")
