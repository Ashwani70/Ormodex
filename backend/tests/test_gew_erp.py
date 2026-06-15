"""Comprehensive backend tests for Gravity Engineering Works ERP."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = "admin@gravityone.com"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "user" in data and "access_token" in data
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    s.user = data["user"]
    return s


# -------- Auth --------
class TestAuth:
    def test_root(self):
        r = requests.get(f"{BASE_URL}/api/")
        assert r.status_code == 200

    def test_login_success_and_no_id(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == ADMIN_EMAIL
        assert body["role"] == "admin"
        assert "_id" not in body
        assert "password_hash" not in body

    def test_login_invalid(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code == 401

    def test_unauth_protected(self):
        r = requests.get(f"{BASE_URL}/api/products")
        assert r.status_code == 401

    def test_logout(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        token = r.json()["access_token"]
        s.headers.update({"Authorization": f"Bearer {token}"})
        rl = s.post(f"{BASE_URL}/api/auth/logout")
        assert rl.status_code == 200


# -------- Warehouses --------
class TestWarehouses:
    def test_create_list(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/warehouses", json={"name": "TEST_WH_A", "location": "Test City", "manager": "Tester"})
        assert r.status_code == 200, r.text
        wh = r.json()
        assert wh["name"] == "TEST_WH_A"
        assert "id" in wh and "_id" not in wh
        admin_session.wh_id = wh["id"]
        r2 = admin_session.get(f"{BASE_URL}/api/warehouses")
        assert r2.status_code == 200
        assert any(w["id"] == wh["id"] for w in r2.json())

    def test_update_delete(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/warehouses", json={"name": "TEST_WH_B", "location": "City B"})
        wid = r.json()["id"]
        ru = admin_session.put(f"{BASE_URL}/api/warehouses/{wid}", json={"name": "TEST_WH_B2", "location": "City B2"})
        assert ru.status_code == 200
        assert ru.json()["name"] == "TEST_WH_B2"
        rd = admin_session.delete(f"{BASE_URL}/api/warehouses/{wid}")
        assert rd.status_code == 200


# -------- Products --------
class TestProducts:
    def test_list_seeded(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/products")
        assert r.status_code == 200
        prods = r.json()
        assert len(prods) >= 1
        assert all("_id" not in p for p in prods)
        assert all("warehouse_name" in p for p in prods)

    def test_low_stock_filter(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/products", params={"low_stock": "true"})
        assert r.status_code == 200
        for p in r.json():
            assert float(p["quantity"]) <= float(p["low_stock_threshold"])

    def test_crud_and_sku_unique(self, admin_session):
        sku = f"TEST-SKU-{int(time.time())}"
        payload = {"name": "TEST_Product", "sku": sku, "category": "Test", "unit": "pcs", "cost_price": 10, "selling_price": 20, "quantity": 50, "low_stock_threshold": 5}
        r = admin_session.post(f"{BASE_URL}/api/products", json=payload)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        # Duplicate SKU
        r_dup = admin_session.post(f"{BASE_URL}/api/products", json=payload)
        assert r_dup.status_code == 400
        # Update
        payload2 = dict(payload, name="TEST_Product_Updated", quantity=60)
        ru = admin_session.put(f"{BASE_URL}/api/products/{pid}", json=payload2)
        assert ru.status_code == 200
        assert ru.json()["name"] == "TEST_Product_Updated"
        # Adjust
        ra = admin_session.post(f"{BASE_URL}/api/products/{pid}/adjust", params={"delta": -10, "reason": "test"})
        assert ra.status_code == 200
        assert ra.json()["new_quantity"] == 50.0
        # Negative stock blocked
        rneg = admin_session.post(f"{BASE_URL}/api/products/{pid}/adjust", params={"delta": -1000, "reason": "test"})
        assert rneg.status_code == 400
        # Stock txns
        rt = admin_session.get(f"{BASE_URL}/api/stock-transactions")
        assert rt.status_code == 200
        assert any(t["product_id"] == pid for t in rt.json())
        # Delete (admin)
        rd = admin_session.delete(f"{BASE_URL}/api/products/{pid}")
        assert rd.status_code == 200


# -------- Suppliers / Customers --------
class TestSimpleCRUD:
    def test_supplier(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/suppliers", json={"name": "TEST_Sup", "company": "TestCo"})
        assert r.status_code == 200
        sid = r.json()["id"]
        admin_session.delete(f"{BASE_URL}/api/suppliers/{sid}")

    def test_customer(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/customers", json={"name": "TEST_Cust", "company": "CustCo", "country": "India"})
        assert r.status_code == 200
        admin_session.test_customer_id = r.json()["id"]


# -------- Leads --------
class TestLeads:
    def test_lead_flow(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/leads", json={"company_name": "TEST_LeadCo", "contact_person": "Tester", "estimated_value": 50000})
        assert r.status_code == 200
        lid = r.json()["id"]
        rp = admin_session.patch(f"{BASE_URL}/api/leads/{lid}/status", params={"status": "WON"})
        assert rp.status_code == 200
        assert rp.json()["status"] == "WON"
        rb = admin_session.patch(f"{BASE_URL}/api/leads/{lid}/status", params={"status": "INVALID"})
        assert rb.status_code == 400
        admin_session.delete(f"{BASE_URL}/api/leads/{lid}")


# -------- PO --------
class TestPurchaseOrders:
    def test_po_create_receive(self, admin_session):
        # Get a supplier and product
        sup = admin_session.get(f"{BASE_URL}/api/suppliers").json()[0]
        prod = admin_session.get(f"{BASE_URL}/api/products").json()[0]
        before_qty = float(prod["quantity"])
        po_payload = {
            "supplier_id": sup["id"],
            "items": [{"product_id": prod["id"], "product_name": prod["name"], "sku": prod["sku"], "quantity": 5, "unit_price": 100}],
        }
        r = admin_session.post(f"{BASE_URL}/api/purchase-orders", json=po_payload)
        assert r.status_code == 200, r.text
        po = r.json()
        assert po["po_number"].startswith("PO-")
        assert po["total"] > 0
        rcv = admin_session.post(f"{BASE_URL}/api/purchase-orders/{po['id']}/receive")
        assert rcv.status_code == 200
        # Verify stock increased
        prod2 = admin_session.get(f"{BASE_URL}/api/products").json()
        match = next(p for p in prod2 if p["id"] == prod["id"])
        assert float(match["quantity"]) == before_qty + 5
        # Already received
        rcv2 = admin_session.post(f"{BASE_URL}/api/purchase-orders/{po['id']}/receive")
        assert rcv2.status_code == 400


# -------- SO + Invoice + Dispatch --------
class TestSalesFlow:
    def test_full_sales_flow(self, admin_session):
        cust = admin_session.get(f"{BASE_URL}/api/customers").json()[0]
        prods = admin_session.get(f"{BASE_URL}/api/products").json()
        prod = next(p for p in prods if float(p["quantity"]) > 5)
        before = float(prod["quantity"])
        items = [{"product_id": prod["id"], "product_name": prod["name"], "sku": prod["sku"], "quantity": 2, "unit_price": 500, "gst_rate": 18}]

        # Quotation
        rq = admin_session.post(f"{BASE_URL}/api/quotations", json={"customer_id": cust["id"], "items": items})
        assert rq.status_code == 200, rq.text
        assert rq.json()["quote_number"].startswith("QUO-")
        assert rq.json()["total"] == round(2*500 + 2*500*0.18, 2)

        # SO
        rs = admin_session.post(f"{BASE_URL}/api/sales-orders", json={"customer_id": cust["id"], "items": items})
        assert rs.status_code == 200
        so = rs.json()
        assert so["order_number"].startswith("SO-")
        rconf = admin_session.post(f"{BASE_URL}/api/sales-orders/{so['id']}/confirm")
        assert rconf.status_code == 200
        # confirm again should fail
        rconf2 = admin_session.post(f"{BASE_URL}/api/sales-orders/{so['id']}/confirm")
        assert rconf2.status_code == 400
        # Stock deducted
        prods2 = admin_session.get(f"{BASE_URL}/api/products").json()
        match = next(p for p in prods2 if p["id"] == prod["id"])
        assert float(match["quantity"]) == before - 2

        # Invoice
        ri = admin_session.post(f"{BASE_URL}/api/invoices", json={"customer_id": cust["id"], "sales_order_id": so["id"], "items": items})
        assert ri.status_code == 200
        inv = ri.json()
        assert inv["invoice_number"].startswith("INV-")
        total = inv["total"]
        # Partial payment
        rp1 = admin_session.post(f"{BASE_URL}/api/invoices/{inv['id']}/payment", params={"amount": total/2})
        assert rp1.status_code == 200
        assert rp1.json()["status"] == "PARTIAL"
        rp2 = admin_session.post(f"{BASE_URL}/api/invoices/{inv['id']}/payment", params={"amount": total/2})
        assert rp2.json()["status"] == "PAID"

        # Dispatch
        rd = admin_session.post(f"{BASE_URL}/api/dispatches", json={"sales_order_id": so["id"], "customer_name": cust["name"], "vehicle_no": "MH-12-XX-1234", "driver_name": "Test Driver", "dispatch_date": "2026-01-15", "items": items})
        assert rd.status_code == 200
        assert rd.json()["challan_number"].startswith("DC-")

    def test_so_insufficient_stock(self, admin_session):
        cust = admin_session.get(f"{BASE_URL}/api/customers").json()[0]
        prod = admin_session.get(f"{BASE_URL}/api/products").json()[0]
        items = [{"product_id": prod["id"], "product_name": prod["name"], "sku": prod["sku"], "quantity": 999999, "unit_price": 100, "gst_rate": 18}]
        rs = admin_session.post(f"{BASE_URL}/api/sales-orders", json={"customer_id": cust["id"], "items": items})
        assert rs.status_code == 200
        rconf = admin_session.post(f"{BASE_URL}/api/sales-orders/{rs.json()['id']}/confirm")
        assert rconf.status_code == 400


# -------- Dashboard & Reports --------
class TestDashboard:
    def test_summary(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/dashboard/summary")
        assert r.status_code == 200
        d = r.json()
        for k in ("kpis", "sales_trend", "lead_funnel", "low_stock_items"):
            assert k in d
        assert "total_products" in d["kpis"]

    def test_reports(self, admin_session):
        for ep in ("inventory", "sales", "profit"):
            r = admin_session.get(f"{BASE_URL}/api/reports/{ep}")
            assert r.status_code == 200, ep


# -------- Users management (admin) --------
class TestUsersAdmin:
    def test_create_employee_and_role_check(self, admin_session):
        email = f"test_emp_{int(time.time())}@test.com"
        r = admin_session.post(f"{BASE_URL}/api/users", json={"name": "TEST_Emp", "email": email, "password": "Pass@123", "role": "employee"})
        assert r.status_code == 200, r.text
        uid = r.json()["id"]
        assert "_id" not in r.json()
        assert "password_hash" not in r.json()

        # Login as employee
        emp = requests.Session()
        rl = emp.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "Pass@123"})
        assert rl.status_code == 200
        emp.headers.update({"Authorization": f"Bearer {rl.json()['access_token']}"})
        # Employee CAN list products
        rp = emp.get(f"{BASE_URL}/api/products")
        assert rp.status_code == 200
        # Employee CANNOT delete products
        prods = rp.json()
        if prods:
            rd = emp.delete(f"{BASE_URL}/api/products/{prods[0]['id']}")
            assert rd.status_code == 403
        # Employee CANNOT list users
        ru = emp.get(f"{BASE_URL}/api/users")
        assert ru.status_code == 403

        # Update + delete employee
        rup = admin_session.put(f"{BASE_URL}/api/users/{uid}", json={"name": "TEST_Emp_Updated"})
        assert rup.status_code == 200
        rdel = admin_session.delete(f"{BASE_URL}/api/users/{uid}")
        assert rdel.status_code == 200

    def test_admin_cannot_self_delete(self, admin_session):
        rd = admin_session.delete(f"{BASE_URL}/api/users/{admin_session.user['id']}")
        assert rd.status_code == 400
