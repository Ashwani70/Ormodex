import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
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

def test_delete_godown_checks(admin_session):
    # --- Part 1: Stock Ledgers / Adjustments block ---
    r = admin_session.post(f"{BASE_URL}/api/inventory/v2/godowns", json={
        "name": "Delete Test Godown",
        "address": "123 Test St",
        "parent_godown_id": None
    })
    assert r.status_code == 200, r.text
    godown_id = r.json()["id"]

    # Try to delete clean godown - should succeed
    r_del = admin_session.delete(f"{BASE_URL}/api/inventory/v2/godowns/{godown_id}")
    assert r_del.status_code == 200, r_del.text

    # --- Part 2: Stock Transfer from_godown_id block ---
    g1_resp = admin_session.post(f"{BASE_URL}/api/inventory/v2/godowns", json={
        "name": "Trans Source Godown",
        "parent_godown_id": None
    })
    g1_id = g1_resp.json()["id"]

    g2_resp = admin_session.post(f"{BASE_URL}/api/inventory/v2/godowns", json={
        "name": "Trans Dest Godown",
        "parent_godown_id": None
    })
    g2_id = g2_resp.json()["id"]

    # Create a stock item
    r_item = admin_session.post(f"{BASE_URL}/api/inventory/v2/items", json={
        "name": "Transfer Test Item",
        "sku": f"SKU-TR-{g1_id}",
        "unit_id": "pcs",
        "valuation_method": "FIFO"
    })
    assert r_item.status_code == 200, r_item.text
    item_id = r_item.json()["id"]

    # Adjust stock in g1 so it has something to transfer
    admin_session.post(f"{BASE_URL}/api/inventory/v2/adjust", json={
        "stock_item_id": item_id,
        "godown_id": g1_id,
        "qty": 10.0,
        "rate": 100.0,
        "entry_date": "2026-06-29"
    })

    # Perform stock transfer from g1 to g2
    r_transfer = admin_session.post(f"{BASE_URL}/api/inventory/v2/transfers", json={
        "from_godown_id": g1_id,
        "to_godown_id": g2_id,
        "transfer_date": "2026-06-29",
        "lines": [{
            "stock_item_id": item_id,
            "qty": 5.0
        }]
    })
    assert r_transfer.status_code == 200, r_transfer.text

    # Both g1 (source) and g2 (destination) are referenced in transfers & ledger, and must block deletion
    assert admin_session.delete(f"{BASE_URL}/api/inventory/v2/godowns/{g1_id}").status_code == 400
    assert admin_session.delete(f"{BASE_URL}/api/inventory/v2/godowns/{g2_id}").status_code == 400

    # Test force delete - should succeed and cascade delete
    assert admin_session.delete(f"{BASE_URL}/api/inventory/v2/godowns/{g1_id}", params={"force": "true"}).status_code == 200
    assert admin_session.delete(f"{BASE_URL}/api/inventory/v2/godowns/{g2_id}", params={"force": "true"}).status_code == 200

    # Clean up test item
    admin_session.delete(f"{BASE_URL}/api/inventory/v2/items/{item_id}")


def test_delete_legacy_warehouse_checks(admin_session):
    # Create legacy warehouse
    r = admin_session.post(f"{BASE_URL}/api/warehouses", json={
        "name": "Legacy Delete Test WH",
        "location": "Test Loc",
        "manager": "Test Manager"
    })
    assert r.status_code == 200, r.text
    wh_id = r.json()["id"]

    # Delete clean legacy warehouse - should succeed
    r_del = admin_session.delete(f"{BASE_URL}/api/warehouses/{wh_id}")
    assert r_del.status_code == 200, r_del.text

    # Create another legacy warehouse
    r2 = admin_session.post(f"{BASE_URL}/api/warehouses", json={
        "name": "Legacy Delete Test WH 2",
        "location": "Test Loc 2",
        "manager": "Test Manager 2"
    })
    assert r2.status_code == 200, r2.text
    wh_id2 = r2.json()["id"]

    # Create product linked to this warehouse
    r_prod = admin_session.post(f"{BASE_URL}/api/products", json={
        "name": "Test Product for Warehouse",
        "sku": f"SKU-WH-{wh_id2}",
        "category": "Test Category",
        "unit": "pcs",
        "cost_price": 50.0,
        "selling_price": 80.0,
        "quantity": 10,
        "warehouse_id": wh_id2
    })
    assert r_prod.status_code == 200, r_prod.text
    prod_id = r_prod.json()["id"]

    # Attempting to delete warehouse with linked products must fail with 400
    r_del2 = admin_session.delete(f"{BASE_URL}/api/warehouses/{wh_id2}")
    assert r_del2.status_code == 400
    assert "Cannot delete a warehouse with stock movements" in r_del2.text

    # Clean up product
    admin_session.delete(f"{BASE_URL}/api/products/{prod_id}")
