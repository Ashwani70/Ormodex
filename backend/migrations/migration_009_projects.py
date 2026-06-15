"""Migration 009 — Project & Job Costing: validators + indexes."""
import logging

logger = logging.getLogger(__name__)


async def run(db):
    # ── projects ──────────────────────────────────────────────────────────────
    await db.command({
        "collMod": "projects",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "code", "name"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "code": {"bsonType": "string"},
                    "name": {"bsonType": "string"},
                    "budget": {"bsonType": ["int", "double"], "minimum": 0},
                    "billing": {"bsonType": "string", "enum": ["fixed", "time_and_materials"]},
                    "status": {"bsonType": "string", "enum": ["active", "on_hold", "closed"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.projects.create_index("id", unique=True)
    await db.projects.create_index("code", unique=True)
    await db.projects.create_index("customer_id")
    await db.projects.create_index("status")

    # ── tasks ─────────────────────────────────────────────────────────────────
    await db.tasks.create_index("id", unique=True)
    await db.tasks.create_index("project_id")

    # ── timesheet_entries ─────────────────────────────────────────────────────
    await db.command({
        "collMod": "timesheet_entries",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "user_id", "project_id", "date", "hours"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "user_id": {"bsonType": "string"},
                    "project_id": {"bsonType": "string"},
                    "hours": {"bsonType": ["int", "double"], "minimum": 0},
                    "billable": {"bsonType": "bool"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.timesheet_entries.create_index("id", unique=True)
    await db.timesheet_entries.create_index([("project_id", 1), ("date", 1)])
    await db.timesheet_entries.create_index([("user_id", 1), ("date", 1)])
    await db.timesheet_entries.create_index([("project_id", 1), ("billable", 1), ("invoiced", 1)])

    # ── project_costs ─────────────────────────────────────────────────────────
    await db.project_costs.create_index("id", unique=True)
    await db.project_costs.create_index("project_id")
    await db.project_costs.create_index("voucher_id")

    # journal_entries gain a project_id dimension — index it (line-level too)
    await db.journal_entries.create_index("project_id")
    await db.journal_entries.create_index("lines.project_id")

    logger.info("Migration 009 — Project & Job Costing applied")
