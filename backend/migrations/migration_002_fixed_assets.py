"""Migration 002 — Fixed Assets: JSON Schema validators + indexes."""
import logging

logger = logging.getLogger(__name__)


async def run(db):
    # ── asset_categories ────────────────────────────────────────────────────
    await db.command({
        "collMod": "asset_categories",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "name", "companies_act_useful_life_years", "companies_act_method"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "name": {"bsonType": "string"},
                    "companies_act_useful_life_years": {"bsonType": ["int", "double"], "minimum": 0.5},
                    "companies_act_method": {"bsonType": "string", "enum": ["SLM", "WDV"]},
                    "companies_act_residual_pct": {"bsonType": ["int", "double"], "minimum": 0, "maximum": 100},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.asset_categories.create_index("id", unique=True)
    await db.asset_categories.create_index("name")

    # ── it_blocks ────────────────────────────────────────────────────────────
    await db.command({
        "collMod": "it_blocks",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "block_name", "it_depreciation_rate", "financial_year"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "block_name": {"bsonType": "string"},
                    "it_depreciation_rate": {"bsonType": ["int", "double"], "minimum": 0, "maximum": 100},
                    "financial_year": {"bsonType": "string"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.it_blocks.create_index("id", unique=True)
    await db.it_blocks.create_index([("block_name", 1), ("financial_year", 1)])

    # ── fixed_assets ─────────────────────────────────────────────────────────
    await db.command({
        "collMod": "fixed_assets",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "description", "category_id", "gross_value", "capitalized_date"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "description": {"bsonType": "string"},
                    "category_id": {"bsonType": "string"},
                    "gross_value": {"bsonType": ["int", "double"], "minimum": 0},
                    "status": {"bsonType": "string", "enum": ["ACTIVE", "DISPOSED", "TRANSFERRED", "WRITTEN_OFF"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.fixed_assets.create_index("id", unique=True)
    await db.fixed_assets.create_index("code")
    await db.fixed_assets.create_index("category_id")
    await db.fixed_assets.create_index("status")
    await db.fixed_assets.create_index("branch_id")

    # ── asset_depreciation_runs ──────────────────────────────────────────────
    await db.command({
        "collMod": "asset_depreciation_runs",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["financial_year", "basis"],
                "properties": {
                    "financial_year": {"bsonType": "string"},
                    "basis": {"bsonType": "string", "enum": ["companies_act", "income_tax"]},
                    "depreciation": {"bsonType": ["int", "double"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.asset_depreciation_runs.create_index("id", unique=True, sparse=True)
    await db.asset_depreciation_runs.create_index([("asset_id", 1), ("financial_year", 1), ("basis", 1)])
    await db.asset_depreciation_runs.create_index([("block_id", 1), ("financial_year", 1), ("basis", 1)])

    # ── asset_transactions ───────────────────────────────────────────────────
    await db.command({
        "collMod": "asset_transactions",
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["id", "asset_id", "type", "date"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "type": {"bsonType": "string", "enum": ["disposal", "transfer", "revaluation"]},
                    "date": {"bsonType": "string"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "warn",
    })
    await db.asset_transactions.create_index("id", unique=True)
    await db.asset_transactions.create_index([("asset_id", 1), ("type", 1)])
    await db.asset_transactions.create_index("date")

    logger.info("Migration 002 — Fixed Assets applied")

    # ── Seed default data ────────────────────────────────────────────────────
    await _seed_asset_defaults(db)


async def _seed_asset_defaults(db):
    if await db.it_blocks.count_documents({}) == 0:
        from core.utils import new_id, now_iso
        blocks = [
            {"id": new_id(), "block_name": "Buildings (10%)", "asset_type": "tangible", "it_depreciation_rate": 10.0, "financial_year": "2024-25", "effective_from": "2024-04-01", "effective_to": None, "created_at": now_iso()},
            {"id": new_id(), "block_name": "Plant & Machinery (15%)", "asset_type": "tangible", "it_depreciation_rate": 15.0, "financial_year": "2024-25", "effective_from": "2024-04-01", "effective_to": None, "created_at": now_iso()},
            {"id": new_id(), "block_name": "Computers & Servers (40%)", "asset_type": "tangible", "it_depreciation_rate": 40.0, "financial_year": "2024-25", "effective_from": "2024-04-01", "effective_to": None, "created_at": now_iso()},
            {"id": new_id(), "block_name": "Vehicles (30%)", "asset_type": "tangible", "it_depreciation_rate": 30.0, "financial_year": "2024-25", "effective_from": "2024-04-01", "effective_to": None, "created_at": now_iso()},
            {"id": new_id(), "block_name": "Furniture & Fixtures (10%)", "asset_type": "tangible", "it_depreciation_rate": 10.0, "financial_year": "2024-25", "effective_from": "2024-04-01", "effective_to": None, "created_at": now_iso()},
        ]
        await db.it_blocks.insert_many(blocks)

    if await db.asset_categories.count_documents({}) == 0:
        from core.utils import new_id, now_iso
        p_and_m_block = await db.it_blocks.find_one({"block_name": "Plant & Machinery (15%)"}, {"_id": 0, "id": 1})
        computer_block = await db.it_blocks.find_one({"block_name": "Computers & Servers (40%)"}, {"_id": 0, "id": 1})
        building_block = await db.it_blocks.find_one({"block_name": "Buildings (10%)"}, {"_id": 0, "id": 1})
        vehicle_block = await db.it_blocks.find_one({"block_name": "Vehicles (30%)"}, {"_id": 0, "id": 1})
        cats = [
            {"id": new_id(), "name": "Plant & Machinery", "companies_act_useful_life_years": 15.0, "companies_act_method": "SLM", "companies_act_residual_pct": 5.0, "it_block_id": p_and_m_block["id"] if p_and_m_block else None, "created_at": now_iso()},
            {"id": new_id(), "name": "Computers & Servers", "companies_act_useful_life_years": 3.0, "companies_act_method": "SLM", "companies_act_residual_pct": 5.0, "it_block_id": computer_block["id"] if computer_block else None, "created_at": now_iso()},
            {"id": new_id(), "name": "Office Buildings", "companies_act_useful_life_years": 60.0, "companies_act_method": "SLM", "companies_act_residual_pct": 5.0, "it_block_id": building_block["id"] if building_block else None, "created_at": now_iso()},
            {"id": new_id(), "name": "Vehicles", "companies_act_useful_life_years": 8.0, "companies_act_method": "WDV", "companies_act_residual_pct": 5.0, "it_block_id": vehicle_block["id"] if vehicle_block else None, "created_at": now_iso()},
            {"id": new_id(), "name": "Office Equipment", "companies_act_useful_life_years": 5.0, "companies_act_method": "SLM", "companies_act_residual_pct": 5.0, "it_block_id": p_and_m_block["id"] if p_and_m_block else None, "created_at": now_iso()},
        ]
        await db.asset_categories.insert_many(cats)
