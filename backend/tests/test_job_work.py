"""End-to-end integration tests for the Job Work module with isolated test data."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = "admin@gravityone.com"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "user" in data and "access_token" in data
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    s.user = data["user"]
    return s


class TestJobWorkFlow:
    def test_job_work_crud_and_inventory_flow(self, admin_session):
        # 1. Create a unique test product and job worker (supplier) to ensure complete test isolation
        unique_suffix = f"{int(time.time() * 1000)}"
        sku = f"JW-SKU-{unique_suffix}"
        
        prod_payload = {
            "name": f"JW-Test-Product-{unique_suffix}",
            "sku": sku,
            "category": "Test",
            "unit": "pcs",
            "cost_price": 10.0,
            "selling_price": 20.0,
            "quantity": 100.0,
            "low_stock_threshold": 5.0
        }
        r_prod = admin_session.post(f"{BASE_URL}/api/products", json=prod_payload)
        assert r_prod.status_code == 200, f"Failed to create test product: {r_prod.text}"
        prod = r_prod.json()
        prod_id = prod["id"]
        prod_name = prod["name"]
        prod_sku = prod["sku"]
        initial_qty = float(prod["quantity"])

        sup_payload = {
            "name": f"JW-Worker-{unique_suffix}",
            "company": f"JW-Worker-Co-{unique_suffix}"
        }
        r_sup = admin_session.post(f"{BASE_URL}/api/suppliers", json=sup_payload)
        assert r_sup.status_code == 200, f"Failed to create test supplier: {r_sup.text}"
        worker = r_sup.json()
        worker_id = worker["id"]
        worker_name = worker["company"]

        # 2. Generate a Job Work Challan (JWC)
        challan_payload = {
            "date": "2026-05-27",
            "job_worker_id": worker_id,
            "job_worker_name": worker_name,
            "items": [
                {
                    "product_id": prod_id,
                    "product_name": prod_name,
                    "sku": prod_sku,
                    "quantity": 5.0,
                    "unit": "pcs"
                }
            ],
            "notes": "Testing outsource fabrication"
        }

        r_create = admin_session.post(f"{BASE_URL}/api/job-work/challans", json=challan_payload)
        assert r_create.status_code == 200, f"Failed to create JWC: {r_create.text}"
        jwc = r_create.json()
        assert jwc["challan_number"].startswith("JWC-")
        assert jwc["status"] == "PENDING"
        jwc_id = jwc["id"]

        # Verify product quantity decreased by 5
        prod_after_jwc = next(p for p in admin_session.get(f"{BASE_URL}/api/products").json() if p["id"] == prod_id)
        assert float(prod_after_jwc["quantity"]) == initial_qty - 5.0

        # Verify stock transaction exists
        txns = admin_session.get(f"{BASE_URL}/api/stock-transactions").json()
        assert any(t["product_id"] == prod_id and t["delta"] == -5.0 for t in txns)

        # 3. Log a partial material receipt (3 out of 5 returned, with 1 scrap)
        # Note: challan_id is NOT included in the request body (testing our fix!)
        receipt_payload_1 = {
            "date": "2026-05-28",
            "items": [
                {
                    "product_id": prod_id,
                    "product_name": prod_name,
                    "sku": prod_sku,
                    "quantity_received": 3.0,
                    "scrap_quantity": 1.0
                }
            ],
            "notes": "First partial delivery"
        }

        r_recv_1 = admin_session.post(f"{BASE_URL}/api/job-work/challans/{jwc_id}/receipt", json=receipt_payload_1)
        assert r_recv_1.status_code == 200, f"Failed to register first receipt: {r_recv_1.text}"
        jwr_1 = r_recv_1.json()
        assert jwr_1["receipt_number"].startswith("JWR-")
        assert jwr_1["challan_id"] == jwc_id

        # Verify product quantity increased by 3
        prod_after_recv_1 = next(p for p in admin_session.get(f"{BASE_URL}/api/products").json() if p["id"] == prod_id)
        assert float(prod_after_recv_1["quantity"]) == initial_qty - 5.0 + 3.0

        # Verify challan status updated to PARTIAL
        jwc_after_1 = admin_session.get(f"{BASE_URL}/api/job-work/challans/{jwc_id}").json()
        assert jwc_after_1["status"] == "PARTIAL"

        # Verify pending report has 2 pending items
        pending_report = admin_session.get(f"{BASE_URL}/api/job-work/reports/pending").json()
        match_pending = next((p for p in pending_report if p["challan_id"] == jwc_id and p["product_id"] == prod_id), None)
        assert match_pending is not None
        assert float(match_pending["quantity_sent"]) == 5.0
        assert float(match_pending["quantity_received"]) == 3.0
        assert float(match_pending["quantity_pending"]) == 2.0

        # 4. Log remaining material receipt (remaining 2 received)
        receipt_payload_2 = {
            "date": "2026-05-29",
            "items": [
                {
                    "product_id": prod_id,
                    "product_name": prod_name,
                    "sku": prod_sku,
                    "quantity_received": 2.0,
                    "scrap_quantity": 0.0
                }
            ],
            "notes": "Final delivery"
        }

        r_recv_2 = admin_session.post(f"{BASE_URL}/api/job-work/challans/{jwc_id}/receipt", json=receipt_payload_2)
        assert r_recv_2.status_code == 200, f"Failed to register second receipt: {r_recv_2.text}"

        # Verify product quantity returned to initial quantity
        prod_after_recv_2 = next(p for p in admin_session.get(f"{BASE_URL}/api/products").json() if p["id"] == prod_id)
        assert float(prod_after_recv_2["quantity"]) == initial_qty

        # Verify challan status updated to COMPLETED
        jwc_after_2 = admin_session.get(f"{BASE_URL}/api/job-work/challans/{jwc_id}").json()
        assert jwc_after_2["status"] == "COMPLETED"

        # Verify pending report no longer has this item pending
        pending_report_2 = admin_session.get(f"{BASE_URL}/api/job-work/reports/pending").json()
        match_pending_2 = next((p for p in pending_report_2 if p["challan_id"] == jwc_id and p["product_id"] == prod_id), None)
        assert match_pending_2 is None

        # 5. Cleanup created resources
        r_del_prod = admin_session.delete(f"{BASE_URL}/api/products/{prod_id}")
        assert r_del_prod.status_code == 200
        r_del_sup = admin_session.delete(f"{BASE_URL}/api/suppliers/{worker_id}")
        assert r_del_sup.status_code == 200
