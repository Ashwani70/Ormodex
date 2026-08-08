"""Integration tests for UOM (Unit of Measure) endpoints and product unit
integration — run against a live server, same pattern as test_job_work.py."""
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


def test_uom_listing_and_creation(admin_session):
    # 1. Fetch UOM list — must contain standard UOMs including 'Nos'
    resp = admin_session.get(f"{BASE_URL}/api/inventory/uoms")
    assert resp.status_code == 200, resp.text
    uoms = resp.json()
    assert isinstance(uoms, list)
    assert "Nos" in uoms
    assert "Pcs" in uoms
    assert "Kg" in uoms
    assert "Meter" in uoms
    assert "Litre" in uoms

    # 2. Create a custom UOM (unique per run so repeated test runs don't collide)
    custom_name = f"Dozen-{int(time.time() * 1000)}"
    resp = admin_session.post(f"{BASE_URL}/api/inventory/uoms", json={
        "name": custom_name, "description": "12 units pack",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == custom_name

    # 3. Verify custom UOM appears in the UOM list
    resp = admin_session.get(f"{BASE_URL}/api/inventory/uoms")
    assert resp.status_code == 200
    updated_uoms = resp.json()
    assert custom_name in updated_uoms


def test_product_creation_with_uom(admin_session):
    # 1. Create product without specifying unit — should default to "Nos"
    sku1 = f"TEST-UOM-NOS-{int(time.time() * 1000)}"
    prod1_payload = {
        "name": "Test Bolt Nos",
        "sku": sku1,
        "category": "Hardware",
        "quantity": 100,
        "cost_price": 5.0,
        "selling_price": 10.0,
    }
    resp = admin_session.post(f"{BASE_URL}/api/products", json=prod1_payload)
    assert resp.status_code == 200, resp.text
    prod1 = resp.json()
    assert prod1["unit"] == "Nos"
    assert prod1["quantity"] == 100

    # 2. Create product with custom UOM "Kg"
    sku2 = f"TEST-UOM-KG-{int(time.time() * 1000)}"
    prod2_payload = {
        "name": "Steel Wire Kg",
        "sku": sku2,
        "category": "Raw Material",
        "unit": "Kg",
        "quantity": 25,
        "cost_price": 150.0,
        "selling_price": 200.0,
    }
    resp = admin_session.post(f"{BASE_URL}/api/products", json=prod2_payload)
    assert resp.status_code == 200, resp.text
    prod2 = resp.json()
    assert prod2["unit"] == "Kg"
    assert prod2["quantity"] == 25

    # 3. Update product UOM
    update_payload = {**prod2, "unit": "Ton"}
    resp = admin_session.put(f"{BASE_URL}/api/products/{prod2['id']}", json=update_payload)
    assert resp.status_code == 200, resp.text
    updated_prod = resp.json()
    assert updated_prod["unit"] == "Ton"
