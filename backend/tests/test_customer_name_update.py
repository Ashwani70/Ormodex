import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = "admin@ormodex.com"
ADMIN_PASSWORD = "Admin@123456"


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    return s


def test_customer_name_update_on_invoice_so_quote(admin_session):
    # 1. Create two customers
    r_cust_a = admin_session.post(
        f"{BASE_URL}/api/customers",
        json={
            "name": "Customer Alice Ltd",
            "company": "Alice Corp",
            "email": "alice@test.com",
            "phone": "9999999991",
            "country": "India",
            "state_code": "27",
            "state": "Maharashtra",
        },
    )
    assert r_cust_a.status_code == 200, r_cust_a.text
    cust_a = r_cust_a.json()

    r_cust_b = admin_session.post(
        f"{BASE_URL}/api/customers",
        json={
            "name": "Customer Bob Ltd",
            "company": "Bob Corp",
            "email": "bob@test.com",
            "phone": "9999999992",
            "country": "India",
            "state_code": "27",
            "state": "Maharashtra",
        },
    )
    assert r_cust_b.status_code == 200, r_cust_b.text
    cust_b = r_cust_b.json()

    # Get a product to use
    prods = admin_session.get(f"{BASE_URL}/api/products").json()
    assert len(prods) > 0, "No products found in DB"
    prod = prods[0]
    items = [{
        "product_id": prod["id"],
        "product_name": prod["name"],
        "sku": prod["sku"],
        "quantity": 1,
        "unit_price": 100.0,
        "gst_rate": 18.0,
    }]

    # --- INVOICES TEST ---
    # Create invoice for Customer A
    r_inv = admin_session.post(
        f"{BASE_URL}/api/invoices",
        json={
            "customer_id": cust_a["id"],
            "items": items,
            "invoice_type": "TAX_INVOICE",
            "currency": "INR",
            "exchange_rate": 1.0,
        },
    )
    assert r_inv.status_code == 200, r_inv.text
    inv = r_inv.json()
    assert inv["customer_name"] == "Customer Alice Ltd"

    # Update invoice, changing customer to Customer B
    r_inv_upd = admin_session.put(
        f"{BASE_URL}/api/invoices/{inv['id']}",
        json={
            "customer_id": cust_b["id"],
            "customer_name": inv["customer_name"],  # frontend sends existing customer_name
            "items": items,
            "invoice_type": "TAX_INVOICE",
            "currency": "INR",
            "exchange_rate": 1.0,
        },
    )
    assert r_inv_upd.status_code == 200, r_inv_upd.text
    inv_upd = r_inv_upd.json()
    # Customer name should be updated to Customer B!
    assert inv_upd["customer_name"] == "Customer Bob Ltd"

    # --- QUOTATIONS TEST ---
    # Create quotation for Customer A
    r_q = admin_session.post(
        f"{BASE_URL}/api/quotations",
        json={
            "customer_id": cust_a["id"],
            "items": items,
            "currency": "INR",
            "exchange_rate": 1.0,
        },
    )
    assert r_q.status_code == 200, r_q.text
    q = r_q.json()
    assert q["customer_name"] == "Customer Alice Ltd"

    # Update quotation, changing customer to Customer B
    r_q_upd = admin_session.put(
        f"{BASE_URL}/api/quotations/{q['id']}",
        json={
            "customer_id": cust_b["id"],
            "customer_name": q["customer_name"],
            "items": items,
            "currency": "INR",
            "exchange_rate": 1.0,
        },
    )
    assert r_q_upd.status_code == 200, r_q_upd.text
    q_upd = r_q_upd.json()
    assert q_upd["customer_name"] == "Customer Bob Ltd"

    # --- SALES ORDERS TEST ---
    # Create sales order for Customer A
    r_so = admin_session.post(
        f"{BASE_URL}/api/sales-orders",
        json={
            "customer_id": cust_a["id"],
            "items": items,
            "currency": "INR",
            "exchange_rate": 1.0,
        },
    )
    assert r_so.status_code == 200, r_so.text
    so = r_so.json()
    assert so["customer_name"] == "Customer Alice Ltd"

    # Update sales order, changing customer to Customer B
    r_so_upd = admin_session.put(
        f"{BASE_URL}/api/sales-orders/{so['id']}",
        json={
            "customer_id": cust_b["id"],
            "customer_name": so["customer_name"],
            "items": items,
            "currency": "INR",
            "exchange_rate": 1.0,
        },
    )
    assert r_so_upd.status_code == 200, r_so_upd.text
    so_upd = r_so_upd.json()
    assert so_upd["customer_name"] == "Customer Bob Ltd"

    # Clean up
    admin_session.delete(f"{BASE_URL}/api/invoices/{inv['id']}")
    admin_session.delete(f"{BASE_URL}/api/quotations/{q['id']}")
    admin_session.delete(f"{BASE_URL}/api/sales-orders/{so['id']}")
    admin_session.delete(f"{BASE_URL}/api/customers/{cust_a['id']}")
    admin_session.delete(f"{BASE_URL}/api/customers/{cust_b['id']}")
