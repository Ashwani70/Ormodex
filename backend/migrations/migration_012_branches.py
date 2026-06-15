"""Migration 012 — Branch / Multi-location: validators + indexes + seed HO."""
import logging

logger = logging.getLogger(__name__)


async def run(db):
    # ── branches ──────────────────────────────────────────────────────────────
    await db.command({
        "collMod": "branches",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "name", "code"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "name": {"bsonType": "string"},
                    "code": {"bsonType": "string"},
                    "state_code": {"bsonType": ["string", "null"]},
                    "is_active": {"bsonType": "bool"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.branches.create_index("id", unique=True)
    await db.branches.create_index("code", unique=True)
    await db.branches.create_index("state_code")

    # ── inter_branch_transfers ────────────────────────────────────────────────
    await db.command({
        "collMod": "inter_branch_transfers",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "from_branch", "to_branch"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "from_branch": {"bsonType": "string"},
                    "to_branch": {"bsonType": "string"},
                    "invoice_value": {"bsonType": ["int", "double"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.inter_branch_transfers.create_index("id", unique=True)
    await db.inter_branch_transfers.create_index("from_branch")
    await db.inter_branch_transfers.create_index("to_branch")

    # vouchers carry inter_branch flag — index for consolidation elimination
    await db.vouchers.create_index("inter_branch", sparse=True)
    await db.vouchers.create_index("branch")

    logger.info("Migration 012 — Branch / Multi-location applied")

    # Seed a default Head Office branch so single-location setups work unchanged.
    if await db.branches.count_documents({}) == 0:
        from core.utils import new_id, now_iso
        await db.branches.insert_one({
            "id": new_id(), "name": "Head Office", "code": "HO",
            "gstin": "27AABCG1234F1Z5", "state_code": "27",
            "address": "Pune, Maharashtra", "is_active": True,
            "created_at": now_iso(), "updated_at": now_iso(),
        })
