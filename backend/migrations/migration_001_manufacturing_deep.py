"""
Migration 001 — Manufacturing (deep) module
Adds JSON Schema validators and indexes for:
  - boms (enhanced with components/co_products/by_products)
  - work_orders (enhanced with godown_id, new status values)
  - production_journals
  - wastage_entries
  - job_work_challans (enhanced with due_date, taxable_value)
  - rate_tables (job-work return window config)

Run via:  python -m migrations.001_manufacturing_deep
Or called from server startup via apply_all().
"""
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient


async def run(db):
    await _boms(db)
    await _work_orders(db)
    await _production_journals(db)
    await _wastage_entries(db)
    await _job_work_challans(db)
    await _rate_tables(db)
    await _seed_rate_table_defaults(db)
    print("[migration 001] Done.")


# ── JSON Schema helpers ───────────────────────────────────────────────────────

async def _set_validator(db, collection: str, schema: dict):
    """Apply $jsonSchema validator; create collection if it doesn't exist."""
    existing = await db.list_collection_names()
    if collection not in existing:
        await db.create_collection(collection)
    await db.command({
        "collMod": collection,
        "validator": {"$jsonSchema": schema},
        "validationLevel": "moderate",   # don't reject existing docs that pre-date this migration
        "validationAction": "warn",      # warn rather than error so old data survives
    })


# ── Validators ────────────────────────────────────────────────────────────────

async def _boms(db):
    schema = {
        "bsonType": "object",
        "required": ["id", "finished_product_id", "finished_product_name"],
        "properties": {
            "id":                    {"bsonType": "string"},
            "finished_product_id":   {"bsonType": "string"},
            "finished_product_name": {"bsonType": "string"},
            "output_qty":            {"bsonType": ["double", "int", "decimal"]},
            "version":               {"bsonType": "string"},
            "status":                {"enum": ["ACTIVE", "DRAFT", "ARCHIVED"]},
            "valuation_method":      {"enum": ["FIFO", "WEIGHTED_AVG"]},
            "components": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["component_item_id"],
                    "properties": {
                        "component_item_id":   {"bsonType": "string"},
                        "qty_per":             {"bsonType": ["double", "int"]},
                        "scrap_pct":           {"bsonType": ["double", "int"]},
                        "is_optional":         {"bsonType": "bool"},
                    },
                },
            },
            "co_products": {"bsonType": "array"},
            "by_products": {"bsonType": "array"},
            "estimated_cost": {"bsonType": ["double", "int"]},
        },
    }
    await _set_validator(db, "boms", schema)
    await db.boms.create_index("finished_product_id")
    await db.boms.create_index([("finished_product_id", 1), ("status", 1)])
    print("[migration 001] boms validator + indexes applied")


async def _work_orders(db):
    schema = {
        "bsonType": "object",
        "required": ["id", "bom_id", "product_id", "quantity_planned"],
        "properties": {
            "id":               {"bsonType": "string"},
            "bom_id":           {"bsonType": "string"},
            "product_id":       {"bsonType": "string"},
            "quantity_planned":  {"bsonType": ["double", "int"]},
            "status": {
                "enum": [
                    "DRAFT", "RELEASED", "IN_PROGRESS",
                    "COMPLETED", "CLOSED", "CANCELLED",
                    # legacy values kept for backward compat
                    "PENDING", "QC_PENDING",
                ]
            },
        },
    }
    await _set_validator(db, "work_orders", schema)
    await db.work_orders.create_index("bom_id")
    await db.work_orders.create_index("status")
    print("[migration 001] work_orders validator + indexes applied")


async def _production_journals(db):
    schema = {
        "bsonType": "object",
        "required": ["id", "work_order_id", "date"],
        "properties": {
            "id":              {"bsonType": "string"},
            "work_order_id":   {"bsonType": "string"},
            "journal_number":  {"bsonType": "string"},
            "date":            {"bsonType": "string"},
            "consumption": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["item_id", "qty"],
                    "properties": {
                        "item_id":   {"bsonType": "string"},
                        "qty":       {"bsonType": ["double", "int"]},
                        "unit_cost": {"bsonType": ["double", "int"]},
                    },
                },
            },
            "output": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["item_id", "qty"],
                    "properties": {
                        "item_id":        {"bsonType": "string"},
                        "qty":            {"bsonType": ["double", "int"]},
                        "is_co_product":  {"bsonType": "bool"},
                        "is_by_product":  {"bsonType": "bool"},
                    },
                },
            },
            "total_material_cost": {"bsonType": ["double", "int"]},
            "unit_cost_fg":        {"bsonType": ["double", "int"]},
        },
    }
    await _set_validator(db, "production_journals", schema)
    await db.production_journals.create_index("work_order_id")
    await db.production_journals.create_index("date")
    print("[migration 001] production_journals validator + indexes applied")


async def _wastage_entries(db):
    schema = {
        "bsonType": "object",
        "required": ["id", "item_id", "qty"],
        "properties": {
            "id":          {"bsonType": "string"},
            "item_id":     {"bsonType": "string"},
            "qty":         {"bsonType": ["double", "int"]},
            "reason_code": {"enum": ["NORMAL", "ABNORMAL", "REWORK", "REJECTED"]},
            "valuation":   {"bsonType": ["double", "int"]},
        },
    }
    await _set_validator(db, "wastage_entries", schema)
    await db.wastage_entries.create_index("work_order_id")
    await db.wastage_entries.create_index("reason_code")
    print("[migration 001] wastage_entries validator + indexes applied")


async def _job_work_challans(db):
    schema = {
        "bsonType": "object",
        "required": ["id", "challan_number", "date", "job_worker_id"],
        "properties": {
            "id":               {"bsonType": "string"},
            "challan_number":   {"bsonType": "string"},
            "date":             {"bsonType": "string"},
            "job_worker_id":    {"bsonType": "string"},
            "due_date":         {"bsonType": ["string", "null"]},
            "return_window_days": {"bsonType": ["int", "double"]},
            "is_overdue":       {"bsonType": "bool"},
            "deemed_supply":    {"bsonType": "bool"},
            "status": {
                "enum": ["PENDING", "PARTIAL", "COMPLETED", "CANCELLED"]
            },
            "items": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "properties": {
                        "taxable_value": {"bsonType": ["double", "int"]},
                    },
                },
            },
        },
    }
    await _set_validator(db, "job_work_challans", schema)
    await db.job_work_challans.create_index("job_worker_id")
    await db.job_work_challans.create_index("due_date")
    await db.job_work_challans.create_index([("status", 1), ("is_overdue", 1)])
    print("[migration 001] job_work_challans validator + indexes applied")


async def _rate_tables(db):
    schema = {
        "bsonType": "object",
        "required": ["key"],
        "properties": {
            "key":           {"bsonType": "string"},
            "value":         {"bsonType": ["string", "int", "double", "null"]},
            "description":   {"bsonType": "string"},
            "effective_from": {"bsonType": ["string", "null"]},
            "effective_to":   {"bsonType": ["string", "null"]},
        },
    }
    await _set_validator(db, "rate_tables", schema)
    try:
        await db.rate_tables.create_index("key", unique=True)
    except Exception:
        pass
    print("[migration 001] rate_tables validator + index applied")


async def _seed_rate_table_defaults(db):
    """Insert default return-window values if not already present."""
    defaults = [
        {
            "key": "job_work_return_window_inputs",
            "value": 365,
            "description": "Days within which inputs sent to job worker must be returned (Rule 45 CGST 2017)",
            "effective_from": "2017-07-01",
            "effective_to": None,
        },
        {
            "key": "job_work_return_window_capital_goods",
            "value": 1095,
            "description": "Days within which capital goods sent to job worker must be returned (Rule 45 CGST 2017)",
            "effective_from": "2017-07-01",
            "effective_to": None,
        },
    ]
    for d in defaults:
        existing = await db.rate_tables.find_one({"key": d["key"]})
        if not existing:
            await db.rate_tables.insert_one(d)
    print("[migration 001] rate_table defaults seeded")


# ── Entry point ───────────────────────────────────────────────────────────────

async def apply_all():
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent.parent / ".env")
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_inst = client[os.environ["DB_NAME"]]
    try:
        await run(db_inst)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(apply_all())
