"""End-to-end integration tests for the Job Work module with isolated test data."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = "admin@ormodex.com"
ADMIN_PASSWORD = "Admin@123456"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "user" in data and "access_token" in data
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    s.user = data["user"]  # type: ignore
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
        assert jwc["challan_number"].startswith("JWC")
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
        assert jwr_1["receipt_number"].startswith("JWR")
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

    def test_edit_pending_challan_reconciles_inventory_and_locks_after_receipt(self, admin_session):
        """A PENDING challan with no receipts can be edited; inventory deltas are
        reversed and re-applied. Once a receipt is logged, editing is rejected."""
        unique_suffix = f"{int(time.time() * 1000)}"
        prod_payload = {
            "name": f"JW-Edit-Product-{unique_suffix}",
            "sku": f"JW-EDIT-{unique_suffix}",
            "category": "Test", "unit": "pcs",
            "cost_price": 10.0, "selling_price": 20.0,
            "quantity": 100.0, "low_stock_threshold": 5.0,
        }
        prod = admin_session.post(f"{BASE_URL}/api/products", json=prod_payload).json()
        prod_id = prod["id"]
        initial_qty = float(prod["quantity"])

        worker = admin_session.post(
            f"{BASE_URL}/api/suppliers",
            json={"name": f"JW-Edit-Worker-{unique_suffix}", "company": f"JW-Edit-Co-{unique_suffix}"},
        ).json()
        worker_id = worker["id"]

        # Create challan sending 5 units → stock 100 - 5 = 95
        challan = admin_session.post(f"{BASE_URL}/api/job-work/challans", json={
            "date": "2026-05-27", "job_worker_id": worker_id, "job_worker_name": worker["company"],
            "items": [{"product_id": prod_id, "product_name": prod["name"], "sku": prod["sku"],
                       "quantity": 5.0, "unit": "pcs"}],
            "notes": "before edit",
        }).json()
        jwc_id = challan["id"]
        q_after_create = float(next(p for p in admin_session.get(f"{BASE_URL}/api/products").json() if p["id"] == prod_id)["quantity"])
        assert q_after_create == initial_qty - 5.0

        # Edit quantity 5 → 8 : reversal (+5) then re-apply (-8) ⇒ stock 100 - 8 = 92
        r_edit = admin_session.put(f"{BASE_URL}/api/job-work/challans/{jwc_id}", json={
            "date": "2026-05-27", "job_worker_id": worker_id, "job_worker_name": worker["company"],
            "items": [{"product_id": prod_id, "product_name": prod["name"], "sku": prod["sku"],
                       "quantity": 8.0, "unit": "pcs"}],
            "notes": "after edit",
        })
        assert r_edit.status_code == 200, f"Edit failed: {r_edit.text}"
        edited = r_edit.json()
        assert edited["id"] == jwc_id
        assert edited["challan_number"] == challan["challan_number"]  # number preserved
        assert edited["notes"] == "after edit"
        assert float(edited["items"][0]["quantity"]) == 8.0
        q_after_edit = float(next(p for p in admin_session.get(f"{BASE_URL}/api/products").json() if p["id"] == prod_id)["quantity"])
        assert q_after_edit == initial_qty - 8.0

        # Log a receipt, then editing must be rejected (409)
        admin_session.post(f"{BASE_URL}/api/job-work/challans/{jwc_id}/receipt", json={
            "date": "2026-05-28",
            "items": [{"product_id": prod_id, "product_name": prod["name"], "sku": prod["sku"],
                       "quantity_received": 2.0, "scrap_quantity": 0.0}],
        })
        r_locked = admin_session.put(f"{BASE_URL}/api/job-work/challans/{jwc_id}", json={
            "date": "2026-05-27", "job_worker_id": worker_id, "job_worker_name": worker["company"],
            "items": [{"product_id": prod_id, "product_name": prod["name"], "sku": prod["sku"],
                       "quantity": 4.0, "unit": "pcs"}],
        })
        assert r_locked.status_code == 409, f"Expected edit lock, got {r_locked.status_code}: {r_locked.text}"

        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/products/{prod_id}")
        admin_session.delete(f"{BASE_URL}/api/suppliers/{worker_id}")

    def test_job_work_extended_validations_and_features(self, admin_session):
        unique_suffix = f"{int(time.time() * 1000)}"
        sku = f"JW-VAL-{unique_suffix}"

        # 1. Create product
        prod = admin_session.post(f"{BASE_URL}/api/products", json={
            "name": f"JW-Val-Prod-{unique_suffix}",
            "sku": sku,
            "category": "Test",
            "unit": "pcs",
            "cost_price": 12.0,
            "selling_price": 24.0,
            "quantity": 50.0,
            "low_stock_threshold": 5.0
        }).json()
        prod_id = prod["id"]

        # 2. Test invalid job worker validation
        challan_payload = {
            "date": "2026-05-27",
            "job_worker_id": "invalid-worker-id",
            "items": [{"product_id": prod_id, "product_name": prod["name"], "sku": prod["sku"], "quantity": 10.0, "unit": "pcs"}]
        }
        r_fail = admin_session.post(f"{BASE_URL}/api/job-work/challans", json=challan_payload)
        assert r_fail.status_code == 400
        assert "not found" in r_fail.text

        # 3. Create valid supplier
        worker = admin_session.post(f"{BASE_URL}/api/suppliers", json={
            "name": f"JW-Val-Worker-{unique_suffix}",
            "company": f"JW-Val-Co-{unique_suffix}"
        }).json()
        worker_id = worker["id"]

        # 4. Create valid challan
        challan_payload["job_worker_id"] = worker_id
        challan_payload["job_worker_name"] = worker["company"]
        r_ok = admin_session.post(f"{BASE_URL}/api/job-work/challans", json=challan_payload)
        assert r_ok.status_code == 200
        jwc = r_ok.json()
        jwc_id = jwc["id"]

        # 5. Test PDF generation endpoint
        r_pdf = admin_session.get(f"{BASE_URL}/api/job-work/challans/{jwc_id}/pdf")
        assert r_pdf.status_code == 200
        assert r_pdf.headers.get("content-type") == "application/pdf"

        # 6. Test over-receipt prevention
        receipt_payload = {
            "date": "2026-05-28",
            "receipt_number": f"JWR-TEST-{unique_suffix}",
            "items": [{"product_id": prod_id, "product_name": prod["name"], "sku": prod["sku"], "quantity_received": 15.0}]
        }
        r_over = admin_session.post(f"{BASE_URL}/api/job-work/challans/{jwc_id}/receipt", json=receipt_payload)
        assert r_over.status_code == 400
        assert "exceeds pending" in r_over.text

        # 7. Create valid receipt (partial)
        receipt_payload["items"][0]["quantity_received"] = 4.0
        r_rec_ok = admin_session.post(f"{BASE_URL}/api/job-work/challans/{jwc_id}/receipt", json=receipt_payload)
        assert r_rec_ok.status_code == 200

        # 8. Test duplicate receipt number prevention
        r_dup = admin_session.post(f"{BASE_URL}/api/job-work/challans/{jwc_id}/receipt", json=receipt_payload)
        assert r_dup.status_code == 400
        assert "already exists" in r_dup.text

        # 9. Verify receipts listing contains enriched fields
        receipts_list = admin_session.get(f"{BASE_URL}/api/job-work/receipts").json()
        match_receipt = next((r for r in receipts_list.get("items", []) if r["receipt_number"] == receipt_payload["receipt_number"]), None)
        assert match_receipt is not None
        assert match_receipt["challan_number"] == jwc["challan_number"]
        assert match_receipt["job_worker_name"] == worker["company"]
        assert match_receipt["items"][0]["quantity_sent"] == 10.0
        assert match_receipt["items"][0]["quantity_pending"] == 6.0
        receipt_id = match_receipt["id"]

        # 10. Test deleting the receipt
        r_del_rec = admin_session.delete(f"{BASE_URL}/api/job-work/receipts/{receipt_id}")
        assert r_del_rec.status_code == 200

        # 11. Test deleting the challan
        r_del_chal = admin_session.delete(f"{BASE_URL}/api/job-work/challans/{jwc_id}")
        assert r_del_chal.status_code == 200

        # 12. Cleanup
        admin_session.delete(f"{BASE_URL}/api/products/{prod_id}")
        admin_session.delete(f"{BASE_URL}/api/suppliers/{worker_id}")
