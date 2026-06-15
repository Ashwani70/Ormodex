"""Migration 005 — Approvals & Workflow: validators + indexes + seed sample policy."""
import logging

logger = logging.getLogger(__name__)


async def run(db):
    # ── approval_policies ─────────────────────────────────────────────────────
    await db.command({
        "collMod": "approval_policies",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "name", "entity_type"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "name": {"bsonType": "string"},
                    "entity_type": {"bsonType": "string"},
                    "condition": {"bsonType": "object"},
                    "active": {"bsonType": "bool"},
                    "priority": {"bsonType": ["int", "double"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.approval_policies.create_index("id", unique=True)
    await db.approval_policies.create_index([("entity_type", 1), ("active", 1)])

    # ── approval_steps ────────────────────────────────────────────────────────
    await db.command({
        "collMod": "approval_steps",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "policy_id", "sequence"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "policy_id": {"bsonType": "string"},
                    "sequence": {"bsonType": ["int", "double"]},
                    "mode": {"bsonType": "string", "enum": ["any_one", "all"]},
                    "sla_hours": {"bsonType": ["int", "double"], "minimum": 0},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.approval_steps.create_index("id", unique=True)
    await db.approval_steps.create_index([("policy_id", 1), ("sequence", 1)])

    # ── approval_requests ─────────────────────────────────────────────────────
    await db.command({
        "collMod": "approval_requests",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "entity_type", "entity_id", "status"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "entity_type": {"bsonType": "string"},
                    "entity_id": {"bsonType": "string"},
                    "status": {"bsonType": "string",
                               "enum": ["pending", "approved", "rejected", "returned"]},
                    "current_step": {"bsonType": ["int", "double"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.approval_requests.create_index("id", unique=True)
    await db.approval_requests.create_index([("entity_type", 1), ("entity_id", 1)])
    await db.approval_requests.create_index("status")
    await db.approval_requests.create_index("requested_by")

    logger.info("Migration 005 — Approvals & Workflow applied")

    await _seed_approval_defaults(db)


async def _seed_approval_defaults(db):
    """Seed one illustrative policy: PO above ₹1,00,000 needs manager sign-off."""
    if await db.approval_policies.count_documents({}) > 0:
        return
    from core.utils import new_id, now_iso

    policy_id = new_id()
    await db.approval_policies.insert_one({
        "id": policy_id,
        "name": "PO above ₹1,00,000 — Manager sign-off",
        "entity_type": "purchase_order",
        "condition": {"total": {"$gt": 100000}},
        "branch_scope": None,
        "active": True,
        "priority": 10,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    await db.approval_steps.insert_one({
        "id": new_id(),
        "policy_id": policy_id,
        "sequence": 1,
        "approver_role": "manager",
        "approver_user_id": None,
        "mode": "any_one",
        "sla_hours": 24,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
