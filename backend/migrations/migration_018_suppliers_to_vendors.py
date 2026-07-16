"""Migration 018 — Suppliers to Vendors data migration.

Migrates all documents from the legacy ``suppliers`` collection into the unified
``vendors`` collection. Preserves existing vendor records and prevents duplicates
by checking the document ID. Maps fields like pan_number -> pan and address -> billing_address
where appropriate for compatibility.
"""
import logging

logger = logging.getLogger(__name__)


async def run(db):
    try:
        # Check if the suppliers collection has documents
        suppliers_count = await db.suppliers.count_documents({})
        if suppliers_count == 0:
            logger.info("Migration 018: No legacy suppliers found. Skipping.")
            return

        logger.info("Migration 018: Migrating %d suppliers to vendors collection...", suppliers_count)
        migrated = 0
        async for supplier in db.suppliers.find({}):
            supp_id = supplier.get("id")
            if not supp_id:
                continue

            # Ensure compatibility mappings
            if "pan_number" in supplier and "pan" not in supplier:
                supplier["pan"] = supplier["pan_number"]
            if "pan" in supplier and "pan_number" not in supplier:
                supplier["pan_number"] = supplier["pan"]
            if "address" in supplier and "billing_address" not in supplier:
                supplier["billing_address"] = supplier["address"]
            if "billing_address" in supplier and "address" not in supplier:
                supplier["address"] = supplier["billing_address"]

            # Remove Mongo's internal _id if present in document
            supplier.pop("_id", None)

            # Check if vendor already exists with this ID
            existing = await db.vendors.find_one({"id": supp_id})
            if not existing:
                await db.vendors.insert_one(supplier)
                migrated += 1
            else:
                # Merge any missing fields into the existing vendor record
                updated_fields = {}
                for key, val in supplier.items():
                    if key not in existing or existing[key] in (None, ""):
                        updated_fields[key] = val
                if updated_fields:
                    await db.vendors.update_one({"id": supp_id}, {"$set": updated_fields})
                    migrated += 1

        logger.info("Migration 018: Migrated or updated %d documents in the vendors collection", migrated)
    except Exception as e:
        logger.error("Migration 018: Failed to migrate suppliers to vendors: %s", e)
        raise
