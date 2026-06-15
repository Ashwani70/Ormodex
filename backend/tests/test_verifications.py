import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = "admin@gravityone.com"
ADMIN_PASSWORD = "Admin@123"

@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    s.user = data["user"]
    return s

@pytest.fixture(scope="module")
def employee_session(admin_session):
    # Create employee user if not exists, then login
    email = "test_emp_ver@gravity-test.com"
    password = "EmpPass@123"
    
    # Check if exists, or delete/create
    admin_session.post(
        f"{BASE_URL}/api/users",
        json={
            "name": "Test Employee Verification",
            "email": email,
            "phone": "9999999999",
            "role": "employee",
            "password": password,
            "permissions": {}
        }
    )
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
    )
    assert r.status_code == 200
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    return s

@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()

def test_verification_settings_flow(admin_session, employee_session, anon_session):
    # 1. Unauthenticated gets setting -> 401
    r = anon_session.get(f"{BASE_URL}/api/verifications/settings")
    assert r.status_code == 401

    # 2. Employee (no perms) gets setting -> 403
    r = employee_session.get(f"{BASE_URL}/api/verifications/settings")
    assert r.status_code == 403

    # 3. Admin gets settings -> 200
    r = admin_session.get(f"{BASE_URL}/api/verifications/settings")
    assert r.status_code == 200
    settings = r.json()
    assert "gst_api_enabled" in settings
    assert "pan_api_enabled" in settings
    assert "aadhaar_api_enabled" in settings

    # 4. Admin updates settings
    r = admin_session.post(
        f"{BASE_URL}/api/verifications/settings",
        json={
            "gst_api_key": "test-gst-key",
            "gst_api_enabled": True,
            "pan_api_key": "test-pan-key",
            "pan_api_enabled": True,
            "aadhaar_api_key": "test-aadhaar-key",
            "aadhaar_api_enabled": True,
        }
    )
    assert r.status_code == 200
    assert r.json()["gst_api_key"] == "test-gst-key"

    # 5. Non-admin updates settings -> 403
    r = employee_session.post(
        f"{BASE_URL}/api/verifications/settings",
        json={
            "gst_api_key": "hack-key",
            "gst_api_enabled": False,
            "pan_api_key": "hack-key",
            "pan_api_enabled": False,
            "aadhaar_api_key": "hack-key",
            "aadhaar_api_enabled": False,
        }
    )
    assert r.status_code == 403

def test_gst_validation(admin_session, employee_session):
    # 1. Valid GSTIN format
    r = admin_session.post(
        f"{BASE_URL}/api/verifications/gst/validate",
        json={"gstin": "27AAAAA1111A1Z1"}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["is_valid"] is True
    assert data["state_code"] == "27"
    assert data["pan"] == "AAAAA1111A"
    assert data["portal_status"] == "ACTIVE"

    # 2. Invalid GSTIN format
    r = admin_session.post(
        f"{BASE_URL}/api/verifications/gst/validate",
        json={"gstin": "INVALIDGSTIN"}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["is_valid"] is False
    assert "error" in data

    # 3. Disable GST API and verify it returns 400
    admin_session.post(
        f"{BASE_URL}/api/verifications/settings",
        json={
            "gst_api_key": "test-gst-key",
            "gst_api_enabled": False,
            "pan_api_key": "test-pan-key",
            "pan_api_enabled": True,
            "aadhaar_api_key": "test-aadhaar-key",
            "aadhaar_api_enabled": True,
        }
    )
    r = admin_session.post(
        f"{BASE_URL}/api/verifications/gst/validate",
        json={"gstin": "27AAAAA1111A1Z1"}
    )
    assert r.status_code == 400
    assert "disabled" in r.json()["detail"].lower()

    # Re-enable GST API for subsequent tests
    admin_session.post(
        f"{BASE_URL}/api/verifications/settings",
        json={
            "gst_api_key": "test-gst-key",
            "gst_api_enabled": True,
            "pan_api_key": "test-pan-key",
            "pan_api_enabled": True,
            "aadhaar_api_key": "test-aadhaar-key",
            "aadhaar_api_enabled": True,
        }
    )

def test_pan_validation_and_link(admin_session):
    # 1. Create a customer to link
    cust_r = admin_session.post(
        f"{BASE_URL}/api/customers",
        json={
            "name": "PAN Link Test Customer",
            "company": "PAN Link Test Ltd",
            "email": "pan_test@gravity.com",
            "phone": "9876543210",
            "country": "India",
            "address": "Test Address",
            "registration_type": "Regular",
            "gstin": "27ABCDE1234F1Z5",
        }
    )
    assert cust_r.status_code == 200
    cust = cust_r.json()
    cust_id = cust["id"]

    # 2. Validate valid PAN and link to customer
    pan_val = "ABCPD1234A" # P indicates Individual
    r = admin_session.post(
        f"{BASE_URL}/api/verifications/pan/validate",
        json={"pan": pan_val, "link_party_id": cust_id}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["is_valid"] is True
    assert data["pan_type"] == "INDIVIDUAL"
    assert data["pan_status"] == "ACTIVE"

    # 3. Retrieve customer and verify details are updated
    cust_get = admin_session.get(f"{BASE_URL}/api/customers")
    assert cust_get.status_code == 200
    cust_list = cust_get.json()
    updated_cust = next(c for c in cust_list if c["id"] == cust_id)
    assert updated_cust["pan_number"] == pan_val
    assert updated_cust["pan_holder_name"] == "GRAVITY ONE ERP ASSOCIATES"
    assert updated_cust["pan_type"] == "INDIVIDUAL"
    assert updated_cust["pan_status"] == "ACTIVE"

    # 4. Invalid PAN format
    r = admin_session.post(
        f"{BASE_URL}/api/verifications/pan/validate",
        json={"pan": "INVALIDPAN"}
    )
    assert r.status_code == 200
    assert r.json()["is_valid"] is False

    # Clean up customer
    admin_session.delete(f"{BASE_URL}/api/customers/{cust_id}")

def test_aadhaar_validation_and_link(admin_session):
    # 1. Create a supplier to link
    supp_r = admin_session.post(
        f"{BASE_URL}/api/suppliers",
        json={
            "name": "Aadhaar Link Test Vendor",
            "company": "Aadhaar Link Test Ltd",
            "email": "aadhaar_test@gravity.com",
            "phone": "9876543211",
            "address": "Test Address",
            "registration_type": "Regular",
            "gstin": "27ABCDE1234F1Z5",
        }
    )
    assert supp_r.status_code == 200
    supp = supp_r.json()
    supp_id = supp["id"]

    # 2. Validate valid Aadhaar and link (verify masking)
    aadhaar_val = "123456789012"
    r = admin_session.post(
        f"{BASE_URL}/api/verifications/aadhaar/validate",
        json={"aadhaar": aadhaar_val, "link_party_id": supp_id}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["is_valid"] is True
    assert data["aadhaar_status"] == "VERIFIED"

    # 3. Retrieve supplier and verify details are masked
    supp_get = admin_session.get(f"{BASE_URL}/api/suppliers")
    assert supp_get.status_code == 200
    supp_list = supp_get.json()
    updated_supp = next(s for s in supp_list if s["id"] == supp_id)
    assert updated_supp["aadhaar_number"] == "XXXX-XXXX-9012"
    assert updated_supp["aadhaar_holder_name"] == "GRAVITY ONE VERIFIED HOLDER"
    assert updated_supp["aadhaar_status"] == "VERIFIED"

    # 4. Invalid Aadhaar format
    r = admin_session.post(
        f"{BASE_URL}/api/verifications/aadhaar/validate",
        json={"aadhaar": "1234"}
    )
    assert r.status_code == 200
    assert r.json()["is_valid"] is False

    # Clean up supplier
    admin_session.delete(f"{BASE_URL}/api/suppliers/{supp_id}")

def test_logs_and_dashboard(admin_session):
    # Get logs
    r = admin_session.get(f"{BASE_URL}/api/verifications/logs")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "items" in data
    assert len(data["items"]) >= 2
    # Verify Aadhaar is masked in log values
    aadhaar_log = next((item for item in data["items"] if item["type"] == "AADHAAR" and item["success"]), None)
    if aadhaar_log:
        assert aadhaar_log["value"] == "XXXX-XXXX-9012"

    # Get dashboard stats
    r = admin_session.get(f"{BASE_URL}/api/verifications/dashboard")
    assert r.status_code == 200
    dashboard = r.json()
    assert "total_customers" in dashboard
    assert "total_vendors" in dashboard
    assert "active_gst" in dashboard
    assert "invalid_gst" in dashboard
    assert "recent_verifications" in dashboard
