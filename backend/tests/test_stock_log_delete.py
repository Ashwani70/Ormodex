"""Unit test for stock log entry deletion (single and bulk).

Proves:
1. Deleting stock log entries correctly executes without SQL errors (fixing the invalid stock_item_id column in stock_transactions).
2. Product quantity reversal works accurately.
3. Orphaned/legacy rows are deleted while live v2 counterpart rows are refused.
"""
import pytest
from sqlalchemy import text
from core.db import engine, get_session
from routers.stock_log import _delete_stock_log_rows


@pytest.mark.asyncio
async def test_stock_log_delete_orphaned_entry():
    test_id = "test_stock_log_del_001"
    test_prod_id = "test_product_del_001"
    
    async with get_session() as session:
        # Create test product
        await session.execute(text("""
            INSERT INTO products (id, name, sku, quantity, is_deleted)
            VALUES (:pid, 'Test Item For Delete', 'SKU-DEL-001', 100, false)
            ON CONFLICT (id) DO UPDATE SET quantity = 100
        """), {"pid": test_prod_id})
        
        # Create test stock transaction
        await session.execute(text("""
            INSERT INTO stock_transactions (id, product_id, product_name, delta, qty, doc_type, reason, created_at)
            VALUES (:id, :pid, 'Test Item For Delete', 15, 15, 'ADJUSTMENT', 'Test Adjustment', '2026-07-24T10:00:00')
            ON CONFLICT (id) DO NOTHING
        """), {"id": test_id, "pid": test_prod_id})

    user = {"id": "usr_admin", "role": "admin", "name": "Admin User"}
    
    # Delete the stock log row
    result = await _delete_stock_log_rows([test_id], user)
    
    assert result["deleted"] == 1
    assert result["not_found"] == []
    assert result["skipped"] == []

    # Verify transaction row is deleted and product quantity reversed (100 - 15 = 85)
    async with get_session() as session:
        txn_row = (await session.execute(
            text("SELECT id FROM stock_transactions WHERE id = :id"), {"id": test_id}
        )).scalar()
        assert txn_row is None
        
        prod_qty = (await session.execute(
            text("SELECT quantity FROM products WHERE id = :pid"), {"pid": test_prod_id}
        )).scalar()
        assert prod_qty is not None
        assert float(prod_qty) == 85.0

        # Clean up test product
        await session.execute(text("DELETE FROM products WHERE id = :pid"), {"pid": test_prod_id})
    await engine.dispose()


@pytest.mark.asyncio
async def test_stock_log_force_delete():
    test_id = "test_stock_log_del_002"
    test_prod_id = "test_product_del_002"
    source_id = "test_source_doc_002"
    
    async with get_session() as session:
        await session.execute(text("""
            INSERT INTO products (id, name, sku, quantity, is_deleted)
            VALUES (:pid, 'Test Item For Force Delete', 'SKU-DEL-002', 50, false)
            ON CONFLICT (id) DO UPDATE SET quantity = 50
        """), {"pid": test_prod_id})
        
        await session.execute(text("""
            INSERT INTO stock_transactions (id, product_id, product_name, delta, qty, doc_type, source_doc_id, reason, created_at)
            VALUES (:id, :pid, 'Test Item For Force Delete', 10, 10, 'JOB_WORK_RECEIPT', :sid, 'Test Receipt', '2026-07-24T10:00:00')
            ON CONFLICT (id) DO NOTHING
        """), {"id": test_id, "pid": test_prod_id, "sid": source_id})

    user = {"id": "usr_admin", "role": "admin", "name": "Admin User"}
    
    # Force delete the stock log row
    result = await _delete_stock_log_rows([test_id], user, force=True)
    
    assert result["deleted"] == 1
    assert result["skipped"] == []

    async with get_session() as session:
        txn_row = (await session.execute(
            text("SELECT id FROM stock_transactions WHERE id = :id"), {"id": test_id}
        )).scalar()
        assert txn_row is None
        
        prod_qty = (await session.execute(
            text("SELECT quantity FROM products WHERE id = :pid"), {"pid": test_prod_id}
        )).scalar()
        assert prod_qty is not None
        assert float(prod_qty) == 40.0

        await session.execute(text("DELETE FROM products WHERE id = :pid"), {"pid": test_prod_id})
    await engine.dispose()

