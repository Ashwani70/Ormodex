import pytest
import requests
import uuid
from concurrent.futures import ThreadPoolExecutor

BASE_URL = "http://127.0.0.1:8000"

def unique_sku(prefix="SKU"):
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

class TestProductEditStockFlow:
    """Automated test suite verifying the ERP Product Edit stock quantity fix and concurrency controls."""

    def test_case_1_increase_stock_58_to_60(self, admin_session):
        """1. 58 -> 60 = 60: Adjustment must be +2, final stock must be 60."""
        payload = {
            "name": "TEST_Prod_58_60",
            "sku": unique_sku("P58-60"),
            "category": "Testing",
            "quantity": 58.0,
            "cost_price": 100.0,
            "selling_price": 150.0,
            "unit": "Nos",
        }
        r_create = admin_session.post(f"{BASE_URL}/api/products", json=payload)
        assert r_create.status_code == 200, r_create.text
        pid = r_create.json()["id"]

        # Edit Product: set quantity = 60
        update_payload = dict(r_create.json(), quantity=60.0)
        r_update = admin_session.put(f"{BASE_URL}/api/products/{pid}", json=update_payload)
        assert r_update.status_code == 200, r_update.text
        res = r_update.json()

        # Check API response fields
        assert res["success"] is True
        assert res["old_quantity"] == 58.0
        assert res["new_quantity"] == 60.0
        assert res["adjustment_quantity"] == 2.0
        assert res["stock_quantity"] == 60.0

        # Check DB state via GET /api/products
        prods = admin_session.get(f"{BASE_URL}/api/products").json()
        p_db = next(p for p in prods if p["id"] == pid)
        assert float(p_db["quantity"]) == 60.0

        # Check ledger entries: should have opening 58 + adjustment 2
        txns = admin_session.get(f"{BASE_URL}/api/stock-transactions").json()
        p_txns = [t for t in txns if t.get("product_id") == pid or t.get("source_doc_id") == pid]
        adj_txns = [t for t in p_txns if t.get("source_doc_type") == "product_adjust"]
        assert len(adj_txns) == 1
        assert float(adj_txns[0]["qty"]) == 2.0

        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/products/{pid}")

    def test_case_2_decrease_stock_58_to_50(self, admin_session):
        """2. 58 -> 50 = 50: Adjustment must be -8, final stock must be 50."""
        r_create = admin_session.post(f"{BASE_URL}/api/products", json={
            "name": "TEST_Prod_58_50", "sku": unique_sku("P58-50"), "category": "Testing", "quantity": 58.0, "unit": "Nos"
        })
        assert r_create.status_code == 200, r_create.text
        pid = r_create.json()["id"]

        r_update = admin_session.put(f"{BASE_URL}/api/products/{pid}", json=dict(r_create.json(), quantity=50.0))
        assert r_update.status_code == 200, r_update.text
        res = r_update.json()

        assert res["old_quantity"] == 58.0
        assert res["new_quantity"] == 50.0
        assert res["adjustment_quantity"] == -8.0
        assert res["stock_quantity"] == 50.0

        prods = admin_session.get(f"{BASE_URL}/api/products").json()
        p_db = next(p for p in prods if p["id"] == pid)
        assert float(p_db["quantity"]) == 50.0

        admin_session.delete(f"{BASE_URL}/api/products/{pid}")

    def test_case_3_no_change_58_to_58(self, admin_session):
        """3. 58 -> 58 = 58: Adjustment must be 0 and no ledger entry created."""
        r_create = admin_session.post(f"{BASE_URL}/api/products", json={
            "name": "TEST_Prod_58_58", "sku": unique_sku("P58-58"), "category": "Testing", "quantity": 58.0, "unit": "Nos"
        })
        assert r_create.status_code == 200, r_create.text
        pid = r_create.json()["id"]

        r_update = admin_session.put(f"{BASE_URL}/api/products/{pid}", json=dict(r_create.json(), quantity=58.0))
        assert r_update.status_code == 200, r_update.text
        res = r_update.json()

        assert res["old_quantity"] == 58.0
        assert res["new_quantity"] == 58.0
        assert res["adjustment_quantity"] == 0.0
        assert res["stock_quantity"] == 58.0

        txns = admin_session.get(f"{BASE_URL}/api/stock-transactions").json()
        adj_txns = [t for t in txns if (t.get("product_id") == pid or t.get("source_doc_id") == pid) and t.get("source_doc_type") == "product_adjust"]
        assert len(adj_txns) == 0

        admin_session.delete(f"{BASE_URL}/api/products/{pid}")

    def test_case_4_zero_to_ten(self, admin_session):
        """4. 0 -> 10 = 10."""
        r_create = admin_session.post(f"{BASE_URL}/api/products", json={
            "name": "TEST_Prod_0_10", "sku": unique_sku("P0-10"), "category": "Testing", "quantity": 0.0, "unit": "Nos"
        })
        assert r_create.status_code == 200, r_create.text
        pid = r_create.json()["id"]

        r_update = admin_session.put(f"{BASE_URL}/api/products/{pid}", json=dict(r_create.json(), quantity=10.0))
        assert r_update.status_code == 200, r_update.text
        res = r_update.json()

        assert res["stock_quantity"] == 10.0
        assert res["adjustment_quantity"] == 10.0

        admin_session.delete(f"{BASE_URL}/api/products/{pid}")

    def test_case_5_hundred_to_zero(self, admin_session):
        """5. 100 -> 0 = 0."""
        r_create = admin_session.post(f"{BASE_URL}/api/products", json={
            "name": "TEST_Prod_100_0", "sku": unique_sku("P100-0"), "category": "Testing", "quantity": 100.0, "unit": "Nos"
        })
        assert r_create.status_code == 200, r_create.text
        pid = r_create.json()["id"]

        r_update = admin_session.put(f"{BASE_URL}/api/products/{pid}", json=dict(r_create.json(), quantity=0.0))
        assert r_update.status_code == 200, r_update.text
        res = r_update.json()

        assert res["stock_quantity"] == 0.0
        assert res["adjustment_quantity"] == -100.0

        admin_session.delete(f"{BASE_URL}/api/products/{pid}")

    def test_case_6_multiple_consecutive_edits(self, admin_session):
        """6. Multiple consecutive edits (58 -> 60 -> 65 -> 62) do not accumulate incorrectly."""
        r_create = admin_session.post(f"{BASE_URL}/api/products", json={
            "name": "TEST_Prod_Consecutive", "sku": unique_sku("P-CONS"), "category": "Testing", "quantity": 58.0, "unit": "Nos"
        })
        assert r_create.status_code == 200, r_create.text
        pid = r_create.json()["id"]

        # Edit 1: 58 -> 60
        r1 = admin_session.put(f"{BASE_URL}/api/products/{pid}", json=dict(r_create.json(), quantity=60.0))
        assert r1.json()["stock_quantity"] == 60.0

        # Edit 2: 60 -> 65
        r2 = admin_session.put(f"{BASE_URL}/api/products/{pid}", json=dict(r1.json(), quantity=65.0))
        assert r2.json()["stock_quantity"] == 65.0

        # Edit 3: 65 -> 62
        r3 = admin_session.put(f"{BASE_URL}/api/products/{pid}", json=dict(r2.json(), quantity=62.0))
        assert r3.json()["stock_quantity"] == 62.0

        prods = admin_session.get(f"{BASE_URL}/api/products").json()
        p_db = next(p for p in prods if p["id"] == pid)
        assert float(p_db["quantity"]) == 62.0

        admin_session.delete(f"{BASE_URL}/api/products/{pid}")

    def test_case_7_and_8_double_click_and_retry(self, admin_session):
        """7 & 8. Double-click Save Product and API retry do not create duplicate adjustments."""
        r_create = admin_session.post(f"{BASE_URL}/api/products", json={
            "name": "TEST_Prod_DoubleClick", "sku": unique_sku("P-DBL"), "category": "Testing", "quantity": 58.0, "unit": "Nos"
        })
        assert r_create.status_code == 200, r_create.text
        pid = r_create.json()["id"]
        update_data = dict(r_create.json(), quantity=60.0)

        # First submit
        r1 = admin_session.put(f"{BASE_URL}/api/products/{pid}", json=update_data)
        assert r1.json()["adjustment_quantity"] == 2.0

        # Immediate second submit (double-click simulation)
        r2 = admin_session.put(f"{BASE_URL}/api/products/{pid}", json=update_data)
        assert r2.json()["stock_quantity"] == 60.0
        assert r2.json()["adjustment_quantity"] == 0.0

        # Third submit (retry simulation)
        r3 = admin_session.put(f"{BASE_URL}/api/products/{pid}", json=update_data)
        assert r3.json()["stock_quantity"] == 60.0
        assert r3.json()["adjustment_quantity"] == 0.0

        # Ledger should only have ONE product_adjust entry
        txns = admin_session.get(f"{BASE_URL}/api/stock-transactions").json()
        adj_txns = [t for t in txns if (t.get("product_id") == pid or t.get("source_doc_id") == pid) and t.get("source_doc_type") == "product_adjust"]
        assert len(adj_txns) == 1

        admin_session.delete(f"{BASE_URL}/api/products/{pid}")

    def test_case_9_concurrent_edits(self, admin_session):
        """9. Concurrent edits do not corrupt stock balance."""
        r_create = admin_session.post(f"{BASE_URL}/api/products", json={
            "name": "TEST_Prod_Concurrent", "sku": unique_sku("P-CONC"), "category": "Testing", "quantity": 58.0, "unit": "Nos"
        })
        assert r_create.status_code == 200, r_create.text
        pid = r_create.json()["id"]
        p_data = r_create.json()

        headers = {"Authorization": admin_session.headers.get("Authorization")}

        def send_update(target_qty):
            body = dict(p_data, quantity=float(target_qty))
            return requests.put(f"{BASE_URL}/api/products/{pid}", json=body, headers=headers)

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut1 = executor.submit(send_update, 60.0)
            fut2 = executor.submit(send_update, 60.0)
            res1 = fut1.result()
            res2 = fut2.result()

        assert res1.status_code == 200
        assert res2.status_code == 200

        prods = admin_session.get(f"{BASE_URL}/api/products").json()
        p_db = next(p for p in prods if p["id"] == pid)
        assert float(p_db["quantity"]) == 60.0

        admin_session.delete(f"{BASE_URL}/api/products/{pid}")

    def test_case_10_edit_then_stock_in(self, admin_session):
        """10. Product Edit (58 -> 60) followed by Stock In (+60) produces exact stock = 120."""
        r_create = admin_session.post(f"{BASE_URL}/api/products", json={
            "name": "TEST_Prod_Edit_Then_In", "sku": unique_sku("P-IN"), "category": "Testing", "quantity": 58.0, "unit": "Nos"
        })
        assert r_create.status_code == 200, r_create.text
        pid = r_create.json()["id"]

        # Product Edit: 58 -> 60
        admin_session.put(f"{BASE_URL}/api/products/{pid}", json=dict(r_create.json(), quantity=60.0))

        # Stock In: adjust stock by +60 via adjust endpoint
        r_in = admin_session.post(f"{BASE_URL}/api/products/{pid}/adjust", params={"delta": 60.0, "reason": "purchase_receipt"})
        assert r_in.status_code == 200
        assert float(r_in.json()["new_quantity"]) == 120.0

        prods = admin_session.get(f"{BASE_URL}/api/products").json()
        p_db = next(p for p in prods if p["id"] == pid)
        assert float(p_db["quantity"]) == 120.0

        admin_session.delete(f"{BASE_URL}/api/products/{pid}")

    def test_case_11_edit_then_stock_out(self, admin_session):
        """11. Product Edit (58 -> 60) followed by Stock Out (-15) produces exact stock = 45."""
        r_create = admin_session.post(f"{BASE_URL}/api/products", json={
            "name": "TEST_Prod_Edit_Then_Out", "sku": unique_sku("P-OUT"), "category": "Testing", "quantity": 58.0, "unit": "Nos"
        })
        assert r_create.status_code == 200, r_create.text
        pid = r_create.json()["id"]

        # Product Edit: 58 -> 60
        admin_session.put(f"{BASE_URL}/api/products/{pid}", json=dict(r_create.json(), quantity=60.0))

        # Stock Out: adjust stock by -15
        r_out = admin_session.post(f"{BASE_URL}/api/products/{pid}/adjust", params={"delta": -15.0, "reason": "sale_dispatch"})
        assert r_out.status_code == 200
        assert float(r_out.json()["new_quantity"]) == 45.0

        prods = admin_session.get(f"{BASE_URL}/api/products").json()
        p_db = next(p for p in prods if p["id"] == pid)
        assert float(p_db["quantity"]) == 45.0

        admin_session.delete(f"{BASE_URL}/api/products/{pid}")

    def test_case_12_stock_ledger_equals_product_stock(self, admin_session):
        """12. Stock ledger balance equals product actual stock."""
        r_create = admin_session.post(f"{BASE_URL}/api/products", json={
            "name": "TEST_Prod_Ledger_Balance", "sku": unique_sku("P-BAL"), "category": "Testing", "quantity": 58.0, "unit": "Nos"
        })
        assert r_create.status_code == 200, r_create.text
        pid = r_create.json()["id"]

        admin_session.put(f"{BASE_URL}/api/products/{pid}", json=dict(r_create.json(), quantity=60.0))

        prods = admin_session.get(f"{BASE_URL}/api/products").json()
        p_db = next(p for p in prods if p["id"] == pid)
        product_qty = float(p_db["quantity"])

        txns = admin_session.get(f"{BASE_URL}/api/stock-transactions").json()
        p_txns = [t for t in txns if t.get("product_id") == pid or t.get("source_doc_id") == pid]
        ledger_qty = sum(float(t.get("qty", 0)) for t in p_txns)

        assert product_qty == 60.0
        assert ledger_qty == 60.0

        admin_session.delete(f"{BASE_URL}/api/products/{pid}")
