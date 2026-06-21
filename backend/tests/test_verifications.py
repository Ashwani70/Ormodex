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
    s.user = data["user"]  # type: ignore
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
    assert r.json()["gst_api_key"] == "••••••••-key"

    # Verify that submitting "********" or masked keys preserves the existing key in the database
    # Let's post "••••••••-key" and a new PAN key, and make sure it keeps "test-gst-key"
    r = admin_session.post(
        f"{BASE_URL}/api/verifications/settings",
        json={
            "gst_api_key": "••••••••-key",
            "gst_api_enabled": True,
            "pan_api_key": "new-test-pan-key",
            "pan_api_enabled": True,
            "aadhaar_api_key": "••••••••-key",
            "aadhaar_api_enabled": True,
        }
    )
    assert r.status_code == 200
    assert r.json()["gst_api_key"] == "••••••••-key"
    assert r.json()["pan_api_key"] == "••••••••-key"

    # Direct DB verification to prove the keys were preserved / updated in the database
    import pymongo
    import os
    client = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db_val = client[os.environ.get("DB_NAME", "gravity_erp")].verification_settings.find_one({"id": "global"})
    assert db_val is not None, "verification_settings 'global' document not found in DB"
    assert db_val["gst_api_key"] == "test-gst-key"
    assert db_val["pan_api_key"] == "new-test-pan-key"
    assert db_val["aadhaar_api_key"] == "test-aadhaar-key"
    client.close()

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

def test_fetch_gstin_endpoint(admin_session, employee_session, anon_session):
    GSTIN = "27AAFCT1234A1Z5"
    NORM_FIELDS = {"company_name", "trade_name", "address", "state", "pincode", "status"}

    # 1. Unauthenticated -> 401
    r = anon_session.post(f"{BASE_URL}/api/customers/fetch-gstin", json={"gstin": GSTIN})
    assert r.status_code == 401

    # 2. Invalid GSTIN format -> 400 (no provider call made)
    r = admin_session.post(
        f"{BASE_URL}/api/customers/fetch-gstin", json={"gstin": "NOPE"}
    )
    assert r.status_code == 400
    assert "invalid gstin" in r.json()["detail"].lower()

    # 3. Valid GSTIN -> 200 with the full normalised shape.
    r = admin_session.post(
        f"{BASE_URL}/api/customers/fetch-gstin", json={"gstin": GSTIN}
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert NORM_FIELDS.issubset(data.keys())
    assert data["company_name"]  # legal name is always populated
    # The response must not carry a "source" of credentials — only public
    # registry fields (plus a cached flag and an optional demo notice).
    allowed = NORM_FIELDS | {"cached", "notice"}
    assert set(data.keys()).issubset(allowed), f"unexpected fields: {set(data) - allowed}"

    # 4. A regular employee can also fetch (it's part of the customer workflow).
    r = employee_session.post(
        f"{BASE_URL}/api/customers/fetch-gstin", json={"gstin": GSTIN}
    )
    assert r.status_code == 200

    # 5. Second call for the same GSTIN is served from the DB cache.
    r = admin_session.post(
        f"{BASE_URL}/api/customers/fetch-gstin", json={"gstin": GSTIN}
    )
    assert r.status_code == 200
    assert r.json().get("cached") is True


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


def test_ai_provider_settings_flow(admin_session):
    # 1. Get current settings and verify openai/gemini fields are present
    r = admin_session.get(f"{BASE_URL}/api/verifications/settings")
    assert r.status_code == 200
    settings = r.json()
    assert "openai_api_key" in settings
    assert "gemini_api_key" in settings

    # 2. Save settings with new openai and gemini key values
    payload = {
        "gst_api_key": settings.get("gst_api_key", ""),
        "gst_api_enabled": settings.get("gst_api_enabled", True),
        "pan_api_key": settings.get("pan_api_key", ""),
        "pan_api_enabled": settings.get("pan_api_enabled", True),
        "aadhaar_api_key": settings.get("aadhaar_api_key", ""),
        "aadhaar_api_enabled": settings.get("aadhaar_api_enabled", True),
        "openai_api_key": "sk-proj-test-save-openai-key",
        "gemini_api_key": "AIzaSy-test-save-gemini-key",
    }
    r = admin_session.post(f"{BASE_URL}/api/verifications/settings", json=payload)
    assert r.status_code == 200
    updated = r.json()
    assert updated["openai_api_key"] == "••••••••-key"
    assert updated["gemini_api_key"] == "••••••••-key"

    # 3. Check /providers endpoint to see if they show up as configured
    r = admin_session.get(f"{BASE_URL}/api/ai/providers")
    assert r.status_code == 200
    providers = r.json()
    assert providers["configured"]["openai"] is True
    assert providers["configured"]["gemini"] is True

    # 4. Restore settings back to empty or fallback values
    payload["openai_api_key"] = ""
    payload["gemini_api_key"] = ""
    r = admin_session.post(f"{BASE_URL}/api/verifications/settings", json=payload)
    assert r.status_code == 200


def test_gstverify_mock_search_endpoint(admin_session):
    # The endpoint returns mock results only when GSTVERIFY_API_KEY is not
    # configured. When a real key is present (e.g. loaded from .env), the
    # endpoint attempts a live lookup which may legitimately return 502 if the
    # upstream provider is unreachable. Assert accordingly for both states.
    from core import gstverify_gst

    r = admin_session.post(
        f"{BASE_URL}/api/verifications/gst/search-by-name",
        json={"query": "Reliance"}
    )
    if gstverify_gst.is_configured():
        # Live provider path: 200 with results, or 502 when upstream is down.
        assert r.status_code in (200, 502)
        if r.status_code == 200:
            assert isinstance(r.json(), list)
    else:
        # Mock path: deterministic results filtered by query.
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "gstin" in data[0]
        assert "RELIANCE" in data[0]["company_name"].upper()

    # Test query length < 3 (validated before any provider call, so it is
    # always a 400 regardless of configuration state).
    r = admin_session.post(
        f"{BASE_URL}/api/verifications/gst/search-by-name",
        json={"query": "Re"}
    )
    assert r.status_code == 400
    assert "at least 3 characters" in r.json()["detail"]


@pytest.mark.asyncio
async def test_gstverify_provider_unit_logic(monkeypatch):
    from core import gstverify_gst
    import httpx

    # Set mock API key
    monkeypatch.setenv("GSTVERIFY_API_KEY", "test-key-123")
    assert gstverify_gst.is_configured() is True

    # 1. Mock verify success response
    async def mock_get_verify_success(self, url, **kwargs):
        class MockResponse:
            status_code = 200
            def json(self):
                return {
                    "success": True,
                    "data": {
                        "gstin": "27AAAAA0000A1Z5",
                        "legal_name": "TEST COMPANY PRIVATE LIMITED",
                        "trade_name": "Test Co",
                        "status": "Active",
                        "constitution": "Private Limited Company",
                        "taxpayer_type": "Regular",
                        "registration_date": "01/07/2017",
                        "state": "Maharashtra",
                        "pan": "AAAAA0000A",
                        "address": "123 Business Road, Mumbai — 400001"
                    }
                }
            def raise_for_status(self):
                pass
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_verify_success)
    res = await gstverify_gst.lookup_gstin("27AAAAA0000A1Z5")
    assert res["company_name"] == "TEST COMPANY PRIVATE LIMITED"
    assert res["trade_name"] == "Test Co"
    assert res["pincode"] == "400001"
    assert res["source"] == "gstverify"

    # 2. Mock search success response
    async def mock_get_search_success(self, url, **kwargs):
        class MockResponse:
            status_code = 200
            def json(self):
                return {
                    "success": True,
                    "data": [
                        {
                            "gstin": "27AAACR5055K1ZT",
                            "legal_name": "RELIANCE INDUSTRIES LIMITED",
                            "trade_name": "Reliance",
                            "status": "Active",
                            "constitution": "Public Limited Company",
                            "state": "Maharashtra",
                            "pan": "AAACR5055K",
                            "registration_date": "01/07/2017",
                            "address": "Maker Chambers IV, Nariman Point, Mumbai 400021"
                        }
                    ]
                }
            def raise_for_status(self):
                pass
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_search_success)
    search_res = await gstverify_gst.search_by_name("Reliance")
    assert len(search_res) == 1
    assert search_res[0]["gstin"] == "27AAACR5055K1ZT"
    assert search_res[0]["company_name"] == "RELIANCE INDUSTRIES LIMITED"
    assert search_res[0]["pincode"] == "400021"

