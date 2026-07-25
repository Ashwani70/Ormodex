"""Quick diagnostic: test Supabase connection and query the tables behind
every endpoint that returned 500 in the server_run.log."""
import asyncio
import os
import sys
from pathlib import Path

# Make sure .env is loaded
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

async def main():
    # 1. Import DB layer
    try:
        from core.db import engine, AsyncSessionLocal
        print("[OK] core.db imported")
    except Exception as e:
        print(f"[FAIL] core.db import: {e}")
        sys.exit(1)

    # 2. Test raw connection
    from sqlalchemy import text
    try:
        async with engine.connect() as conn:
            r = await conn.execute(text("SELECT 1"))
            print(f"[OK] SELECT 1 → {r.scalar()}")
    except Exception as e:
        print(f"[FAIL] DB connection: {e}")
        sys.exit(1)

    # 3. Probe each failing table
    from core.utils import _table, _row_to_dict
    failing_collections = [
        "product_categories",   # GET /api/categories?status=Active  → 500
        "po_numbering_settings",# GET /api/settings/po-numbering     → 500
        "job_work_receipts",    # GET /api/job-work/receipts          → 500
        "sales_orders",         # GET /api/sales-orders               → 500
        "stock_items",          # GET /api/inventory/v2/items         → 500
        "users",                # POST /api/auth/login                → 500
    ]
    from sqlalchemy import select, inspect as sa_inspect
    async with AsyncSessionLocal() as session:
        for coll in failing_collections:
            try:
                Model = _table(coll)
                # Check table actually exists in DB
                stmt = select(Model).limit(1)
                result = await session.execute(stmt)
                row = result.scalars().first()
                if row:
                    d = _row_to_dict(row) or {}
                    print(f"[OK] {coll:30s} → has data (sample keys: {list(d.keys())[:5]})")
                else:
                    print(f"[OK] {coll:30s} → empty table (no rows)")
            except Exception as e:
                print(f"[FAIL] {coll:30s} → {type(e).__name__}: {e}")

    # 4. Test the auth flow specifically (find_one)
    print("\n--- Auth login simulation ---")
    from core.db import db
    try:
        user = await db.users.find_one({"email": os.environ.get("ADMIN_EMAIL", "admin@gravityone.com")})
        if user:
            print(f"[OK] Admin user found: {user.get('email')} / role={user.get('role')}")
            print(f"     Has password_hash: {bool(user.get('password_hash'))}")
        else:
            print("[WARN] Admin user NOT found — seed may not have run")
    except Exception as e:
        print(f"[FAIL] db.users.find_one: {type(e).__name__}: {e}")

    # 5. Test categories list
    print("\n--- Categories list simulation ---")
    try:
        rows = await db.product_categories.find(
            {"is_deleted": {"$ne": True}, "status": "Active"}, {"_id": 0}
        ).sort([("display_order", 1), ("name", 1)]).to_list(5000)
        print(f"[OK] product_categories: {len(rows)} rows")
    except Exception as e:
        print(f"[FAIL] product_categories list: {type(e).__name__}: {e}")

    # 6. Test receipts list
    print("\n--- Job work receipts list simulation ---")
    try:
        rows = await db.job_work_receipts.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
        print(f"[OK] job_work_receipts: {len(rows)} rows")
    except Exception as e:
        print(f"[FAIL] job_work_receipts list: {type(e).__name__}: {e}")

    # 7. Test sales_orders list
    print("\n--- Sales orders list simulation ---")
    try:
        rows = await db.sales_orders.find({}, {"_id": 0}).to_list(1000)
        print(f"[OK] sales_orders: {len(rows)} rows")
    except Exception as e:
        print(f"[FAIL] sales_orders list: {type(e).__name__}: {e}")

    # 8. Test inventory v2 items
    print("\n--- Inventory v2 items simulation ---")
    try:
        rows = await db.stock_items.find({}, {"_id": 0}).to_list(1000)
        print(f"[OK] stock_items: {len(rows)} rows")
    except Exception as e:
        print(f"[FAIL] stock_items list: {type(e).__name__}: {e}")

    await engine.dispose()
    print("\n=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
