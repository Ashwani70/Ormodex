import os
from datetime import datetime, timezone, timedelta

from .auth_utils import hash_password, verify_password
from .db import db
from .utils import new_id, now_iso


async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "id": new_id(),
            "name": "Administrator",
            "email": admin_email,
            "phone": "+91 9876543210",
            "role": "admin",
            "password_hash": hash_password(admin_password),
            "created_at": now_iso(),
        })
    elif not verify_password(admin_password, existing.get("password_hash", "")):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}},
        )


async def seed_demo_data():
    if await db.warehouses.count_documents({}) == 0:
        wh1_id = new_id()
        wh2_id = new_id()
        await db.warehouses.insert_many([
            {"id": wh1_id, "name": "Main Warehouse - Pune", "location": "Pune, MH", "manager": "Rohan Patil", "created_at": now_iso(), "updated_at": now_iso()},
            {"id": wh2_id, "name": "Export Yard - Mumbai", "location": "Mumbai, MH", "manager": "Suresh Iyer", "created_at": now_iso(), "updated_at": now_iso()},
        ])

        prods = [
            {"name": "Cuplock Vertical 3.0m", "sku": "CV-3000", "category": "Cuplock", "unit": "pcs", "cost_price": 1200, "selling_price": 1650, "quantity": 320, "low_stock_threshold": 100, "warehouse_id": wh1_id, "hsn_code": "7308", "gst_rate": 18.0},
            {"name": "Cuplock Ledger 1.5m", "sku": "CL-1500", "category": "Cuplock", "unit": "pcs", "cost_price": 480, "selling_price": 690, "quantity": 540, "low_stock_threshold": 200, "warehouse_id": wh1_id, "hsn_code": "7308", "gst_rate": 18.0},
            {"name": "Adjustable Base Jack 600mm", "sku": "ABJ-600", "category": "Accessories", "unit": "pcs", "cost_price": 320, "selling_price": 480, "quantity": 80, "low_stock_threshold": 100, "warehouse_id": wh1_id, "hsn_code": "7308", "gst_rate": 18.0},
            {"name": "U-Head Jack 600mm", "sku": "UHJ-600", "category": "Accessories", "unit": "pcs", "cost_price": 340, "selling_price": 510, "quantity": 210, "low_stock_threshold": 80, "warehouse_id": wh1_id, "hsn_code": "7308", "gst_rate": 18.0},
            {"name": "Steel Plank 2.5m", "sku": "SP-2500", "category": "Planks", "unit": "pcs", "cost_price": 880, "selling_price": 1180, "quantity": 45, "low_stock_threshold": 50, "warehouse_id": wh2_id, "hsn_code": "7308", "gst_rate": 18.0},
            {"name": "Ringlock Standard 2.0m", "sku": "RL-2000", "category": "Ringlock", "unit": "pcs", "cost_price": 980, "selling_price": 1380, "quantity": 180, "low_stock_threshold": 60, "warehouse_id": wh2_id, "hsn_code": "7308", "gst_rate": 18.0},
        ]
        now = now_iso()
        await db.products.insert_many([{**p, "id": new_id(), "image_url": None, "image_path": None, "description": None, "created_at": now, "updated_at": now} for p in prods])

    if await db.customers.count_documents({}) == 0:
        await db.customers.insert_many([
            {"id": new_id(), "name": "Rajesh Khanna", "company": "Skyline Builders Pvt Ltd", "email": "rajesh@skyline.in", "phone": "+919876512345", "country": "India", "address": "Mumbai, MH", "gstin": "27ABCDE1234F1Z5", "created_at": now_iso(), "updated_at": now_iso()},
            {"id": new_id(), "name": "Ahmed Al-Mansouri", "company": "Gulf Construction LLC", "email": "ahmed@gulfcon.ae", "phone": "+971501234567", "country": "UAE", "address": "Dubai, UAE", "gstin": None, "created_at": now_iso(), "updated_at": now_iso()},
            {"id": new_id(), "name": "Priya Mehta", "company": "Mehta Infra", "email": "priya@mehta.in", "phone": "+919812345600", "country": "India", "address": "Ahmedabad, GJ", "gstin": "24XYZAB1234C1Z2", "created_at": now_iso(), "updated_at": now_iso()},
        ])

    if await db.suppliers.count_documents({}) == 0:
        await db.suppliers.insert_many([
            {"id": new_id(), "name": "Vikram Singh", "company": "JSW Steel Ltd", "email": "sales@jsw.com", "phone": "+919811112222", "address": "Mumbai", "gstin": "27JSWST1234F1Z5", "created_at": now_iso(), "updated_at": now_iso()},
            {"id": new_id(), "name": "Mohammed Khan", "company": "Tata Steel", "email": "khan@tata.com", "phone": "+919833334444", "address": "Jamshedpur", "gstin": "20TATA1234F1Z5", "created_at": now_iso(), "updated_at": now_iso()},
        ])

    # ── Manufacturing demo seed ────────────────────────────────────────────────
    if await db.boms.count_documents({}) == 0:
        # Fetch two raw-material products to use as components
        prods = await db.products.find({}, {"_id": 0, "id": 1, "name": 1, "sku": 1}).to_list(6)
        if len(prods) >= 4:
            rm1, rm2, rm3, fg = prods[1], prods[2], prods[3], prods[0]  # use existing products

            sub_bom_id = new_id()
            main_bom_id = new_id()

            # Level-2 sub-assembly BOM (rm2 + rm3 → sub-assembly)
            await db.boms.insert_one({
                "id": sub_bom_id,
                "finished_product_id": rm1["id"],
                "finished_product_name": rm1["name"],
                "sku": rm1.get("sku", ""),
                "output_qty": 1.0,
                "uom": "pcs",
                "version": "1.0",
                "status": "ACTIVE",
                "valuation_method": "WEIGHTED_AVG",
                "components": [
                    {"component_item_id": rm2["id"], "component_item_name": rm2["name"], "qty_per": 2.0, "uom": "pcs", "scrap_pct": 5.0, "is_optional": False},
                    {"component_item_id": rm3["id"], "component_item_name": rm3["name"], "qty_per": 1.0, "uom": "pcs", "scrap_pct": 0.0, "is_optional": False},
                ],
                "co_products": [], "by_products": [], "routing_steps": [], "items": [],
                "estimated_cost": 0.0, "notes": "Demo sub-assembly BOM",
                "created_at": now_iso(), "updated_at": now_iso(),
            })

            # Level-1 main BOM (rm1 sub-assembly + rm3 → fg)
            await db.boms.insert_one({
                "id": main_bom_id,
                "finished_product_id": fg["id"],
                "finished_product_name": fg["name"],
                "sku": fg.get("sku", ""),
                "output_qty": 1.0,
                "uom": "pcs",
                "version": "1.0",
                "status": "ACTIVE",
                "valuation_method": "WEIGHTED_AVG",
                "components": [
                    {"component_item_id": rm1["id"], "component_item_name": rm1["name"], "qty_per": 3.0, "uom": "pcs", "scrap_pct": 10.0, "is_optional": False},
                    {"component_item_id": rm3["id"], "component_item_name": rm3["name"], "qty_per": 0.5, "uom": "pcs", "scrap_pct": 0.0, "is_optional": True},
                ],
                "co_products": [],
                "by_products": [
                    {"item_id": rm2["id"], "item_name": rm2["name"], "qty_per": 0.1, "uom": "pcs", "realizable_value_per": 50.0},
                ],
                "routing_steps": [
                    {"step_index": 1, "operation_name": "Cutting", "workstation": "CNC-1", "labor_time_mins": 15.0, "machine_time_mins": 10.0, "cost_per_min": 2.5},
                    {"step_index": 2, "operation_name": "Assembly", "workstation": "WS-2", "labor_time_mins": 20.0, "machine_time_mins": 0.0, "cost_per_min": 1.8},
                ],
                "items": [],
                "estimated_cost": 0.0,
                "notes": "Demo 2-level BOM with by-product and scrap",
                "created_at": now_iso(), "updated_at": now_iso(),
            })

    # ── Rate table defaults (job-work return windows) ─────────────────────────
    if await db.rate_tables.count_documents({}) == 0:
        await db.rate_tables.insert_many([
            {"key": "job_work_return_window_inputs", "value": 365, "description": "Job work return window for inputs (Rule 45 CGST)", "effective_from": "2017-07-01", "effective_to": None},
            {"key": "job_work_return_window_capital_goods", "value": 1095, "description": "Job work return window for capital goods (Rule 45 CGST)", "effective_from": "2017-07-01", "effective_to": None},
        ])

    if await db.leads.count_documents({}) == 0:
        await db.leads.insert_many([
            {"id": new_id(), "company_name": "Emirates Build Co.", "contact_person": "Faisal Ahmed", "country": "UAE", "email": "faisal@emiratesbuild.ae", "phone": "+971502223344", "source": "Trade Show", "interested_in": "Cuplock System 50T", "estimated_value": 4500000, "status": "QUOTED", "notes": "Wants delivery in 30 days", "next_follow_up": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(), "created_at": now_iso(), "updated_at": now_iso()},
            {"id": new_id(), "company_name": "L&T Construction", "contact_person": "Sandeep Rao", "country": "India", "email": "sandeep@lnt.in", "phone": "+919811223344", "source": "Referral", "interested_in": "Ringlock Scaffolding", "estimated_value": 1800000, "status": "CONTACTED", "notes": "Site visit pending", "next_follow_up": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(), "created_at": now_iso(), "updated_at": now_iso()},
            {"id": new_id(), "company_name": "Saudi Bin Ladin Group", "contact_person": "Yusuf Al-Saud", "country": "Saudi Arabia", "email": "yusuf@sblg.sa", "phone": "+966501112233", "source": "Website", "interested_in": "Steel Planks bulk", "estimated_value": 9200000, "status": "NEW", "notes": "Initial inquiry", "next_follow_up": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), "created_at": now_iso(), "updated_at": now_iso()},
            {"id": new_id(), "company_name": "Reliance Industries", "contact_person": "Anil Patel", "country": "India", "email": "anil@ril.in", "phone": "+919898989898", "source": "Cold Call", "interested_in": "Custom scaffolding for refinery", "estimated_value": 6700000, "status": "WON", "notes": "Order confirmed", "next_follow_up": None, "created_at": now_iso(), "updated_at": now_iso()},
        ])
