import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = "admin@gravityone.com"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123456")

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
    password = "EmpPass@1234"
    
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
    # 1. Get current settings and verify gemini fields are present
    r = admin_session.get(f"{BASE_URL}/api/verifications/settings")
    assert r.status_code == 200
    settings = r.json()
    assert "gemini_api_key" in settings

    # 2. Save settings with new gemini key values
    payload = {
        "gst_api_key": settings.get("gst_api_key", ""),
        "gst_api_enabled": settings.get("gst_api_enabled", True),
        "pan_api_key": settings.get("pan_api_key", ""),
        "pan_api_enabled": settings.get("pan_api_enabled", True),
        "aadhaar_api_key": settings.get("aadhaar_api_key", ""),
        "aadhaar_api_enabled": settings.get("aadhaar_api_enabled", True),
        "gemini_api_key": "AIzaSy-test-save-gemini-key",
    }
    r = admin_session.post(f"{BASE_URL}/api/verifications/settings", json=payload)
    assert r.status_code == 200
    updated = r.json()
    assert updated["gemini_api_key"] == "••••••••-key"

    # 3. Check /providers endpoint to see if they show up as configured
    r = admin_session.get(f"{BASE_URL}/api/ai/providers")
    assert r.status_code == 200
    providers = r.json()
    assert providers["configured"]["gemini"] is True

    # 4. Restore settings back to empty or fallback values
    payload["gemini_api_key"] = ""
    r = admin_session.post(f"{BASE_URL}/api/verifications/settings", json=payload)
    assert r.status_code == 200


def test_gstverify_mock_search_endpoint(admin_session):
    # The endpoint returns mock results when no GSTVerify API key is
    # configured in Settings. When a real key is saved in the Settings UI, the
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

    # Pass key directly (no env var fallback anymore)
    assert gstverify_gst.is_configured("test-key-123") is True

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
    res = await gstverify_gst.lookup_gstin("27AAAAA0000A1Z5", api_key="test-key-123")
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
    search_res = await gstverify_gst.search_by_name("Reliance", api_key="test-key-123")
    assert len(search_res) == 1
    assert search_res[0]["gstin"] == "27AAACR5055K1ZT"
    assert search_res[0]["company_name"] == "RELIANCE INDUSTRIES LIMITED"
    assert search_res[0]["pincode"] == "400021"


@pytest.mark.asyncio
async def test_rapidapi_gst_parses_live_envelope(monkeypatch):
    """The gst-return-status RapidAPI returns {'flag': true, 'data': {lgnm,
    tradeNam, pradr...}} — make sure the extractor reads those real field names
    (regression: name/trade name came back blank when only GSTVerify-style keys
    like 'tradeName' were read)."""
    from core import rapidapi_gst
    import httpx

    async def mock_get(self, url, **kwargs):
        class MockResponse:
            status_code = 200
            def json(self):
                return {
                    "flag": True,
                    "data": {
                        "gstin": "27AAACR5055K1ZT",
                        "lgnm": "RELIANCE INDUSTRIES LIMITED",
                        "tradeNam": "Reliance",
                        "sts": "Active",
                        "ctb": "Public Limited Company",
                        "rgdt": "01/07/2017",
                        "pradr": {
                            "adr": "Maker Chambers IV, Nariman Point, Mumbai 400021",
                            "addr": {"pncd": "400021"},
                        },
                    },
                }
            def raise_for_status(self):
                pass
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
    res = await rapidapi_gst.lookup_gstin("27AAACR5055K1ZT", api_key="rapid-key-123")
    assert res["company_name"] == "RELIANCE INDUSTRIES LIMITED"
    assert res["trade_name"] == "Reliance"
    assert res["address"].startswith("Maker Chambers IV")
    assert res["pincode"] == "400021"
    assert res["status"] == "ACTIVE"
    assert res["taxpayer_type"] == "Public Limited Company"
    assert res["source"] == "rapidapi"


@pytest.mark.asyncio
async def test_rapidapi_gst_checksum_failure_maps_to_not_found(monkeypatch):
    """The gst-return-status RapidAPI validates the GSTIN check digit *before*
    looking it up and returns a checksum failure as HTTP 503 with body
    {'success': false, 'message': 'GSTIN checksum failed'}. That's a permanent
    input error, not a transient outage — it must map to GstinNotFound so the
    user sees "invalid GSTIN" (and the provider fallback doesn't burn a second
    credit retrying it), not "service unavailable"."""
    from core import rapidapi_gst
    import httpx

    async def mock_get(self, url, **kwargs):
        class MockResponse:
            status_code = 503
            text = '{"success": false, "message": "GSTIN checksum failed"}'
            def json(self):
                return {"success": False, "message": "GSTIN checksum failed"}
            def raise_for_status(self):
                pass
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
    with pytest.raises(rapidapi_gst.GstinNotFound):
        await rapidapi_gst.lookup_gstin("27AAACR5055K1ZX", api_key="rapid-key-123")


@pytest.mark.asyncio
async def test_rapidapi_gst_genuine_5xx_is_unavailable(monkeypatch):
    """A real upstream 5xx (no input-related message) must still surface as a
    transient GstProviderUnavailable, not get swallowed as 'not found'."""
    from core import rapidapi_gst
    import httpx

    async def mock_get(self, url, **kwargs):
        class MockResponse:
            status_code = 502
            text = "Bad Gateway"
            def json(self):
                raise ValueError("not json")
            def raise_for_status(self):
                pass
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
    with pytest.raises(rapidapi_gst.GstProviderUnavailable):
        await rapidapi_gst.lookup_gstin("27AAACR5055K1Z7", api_key="rapid-key-123")


@pytest.mark.asyncio
async def test_gst_lookup_falls_back_to_other_provider_on_auth_error(monkeypatch):
    """A RapidAPI key saved while the provider dropdown is still on the
    GSTVerify default used to surface a misleading "authentication failed". The
    dispatcher must retry the same key against the alternate provider on a hard
    auth error and return that provider's result instead.

    Here the (default) GSTVerify provider rejects the key with a 401, and the
    lookup must transparently fall through to RapidAPI and succeed."""
    from routers import verifications
    from core import gstverify_gst, rapidapi_gst

    async def gstverify_rejects(gstin, api_key=None):
        raise gstverify_gst.GstProviderAuthError()

    async def rapidapi_succeeds(gstin, api_key=None):
        assert api_key == "rapid-key-123"  # same key, routed to the other provider
        return {
            "company_name": "RELIANCE INDUSTRIES LIMITED",
            "trade_name": "Reliance",
            "address": "Maker Chambers IV, Nariman Point, Mumbai 400021",
            "state": "Maharashtra",
            "pincode": "400021",
            "status": "ACTIVE",
            "state_code": "27",
            "pan": "AAACR5055K",
            "taxpayer_type": "Regular",
            "registration_date": "01/07/2017",
            "source": "rapidapi",
        }

    monkeypatch.setattr(gstverify_gst, "lookup_gstin", gstverify_rejects)
    monkeypatch.setattr(rapidapi_gst, "lookup_gstin", rapidapi_succeeds)

    # Provider selector left on the default ("gstverify") but the key is RapidAPI's.
    res = await verifications._lookup_gst_with_fallback(
        "27AAACR5055K1ZT", "rapid-key-123", "gstverify"
    )
    assert res["company_name"] == "RELIANCE INDUSTRIES LIMITED"
    assert res["trade_name"] == "Reliance"
    assert res["source"] == "rapidapi"


@pytest.mark.asyncio
async def test_gst_lookup_raises_auth_error_when_both_providers_reject(monkeypatch):
    """If the key is invalid for *both* providers, the auth error stands."""
    from routers import verifications
    from core import gstverify_gst, rapidapi_gst

    async def reject_gstverify(gstin, api_key=None):
        raise gstverify_gst.GstProviderAuthError()

    async def reject_rapidapi(gstin, api_key=None):
        raise rapidapi_gst.GstProviderAuthError()

    monkeypatch.setattr(gstverify_gst, "lookup_gstin", reject_gstverify)
    monkeypatch.setattr(rapidapi_gst, "lookup_gstin", reject_rapidapi)

    # Provider "rapidapi" is tried first, so its auth error is the one re-raised.
    with pytest.raises(rapidapi_gst.GstProviderAuthError):
        await verifications._lookup_gst_with_fallback(
            "27AAACR5055K1ZT", "bad-key", "rapidapi"
        )


@pytest.mark.asyncio
async def test_gst_lookup_falls_through_not_found_to_other_provider(monkeypatch):
    """A "not found" on the selected provider's limited free-tier dataset must
    fall through to the other provider, which may have the record. This is the
    vendor-form case: RapidAPI's free GSTIN endpoint returned no data, so we
    re-check GSTVerify before telling the user the GSTIN doesn't exist."""
    from routers import verifications
    from core import gstverify_gst, rapidapi_gst

    async def rapidapi_no_record(gstin, api_key=None):
        raise rapidapi_gst.GstinNotFound()

    async def gstverify_has_record(gstin, api_key=None):
        return {
            "company_name": "ACME PRIVATE LIMITED",
            "trade_name": "Acme",
            "address": "1 Industrial Area, Pune 411018",
            "state": "Maharashtra",
            "pincode": "411018",
            "status": "ACTIVE",
            "state_code": "27",
            "pan": "AAACA1111A",
            "taxpayer_type": "Regular",
            "registration_date": "01/07/2017",
            "source": "gstverify",
        }

    monkeypatch.setattr(rapidapi_gst, "lookup_gstin", rapidapi_no_record)
    monkeypatch.setattr(gstverify_gst, "lookup_gstin", gstverify_has_record)

    # Provider selected = rapidapi (tried first, returns nothing) -> GSTVerify wins.
    res = await verifications._lookup_gst_with_fallback(
        "27AAACA1111A1Z5", "some-key", "rapidapi"
    )
    assert res["company_name"] == "ACME PRIVATE LIMITED"
    assert res["source"] == "gstverify"


@pytest.mark.asyncio
async def test_gst_health_probe_interprets_provider_outcomes(monkeypatch):
    """The /gst/health live probe must map provider outcomes correctly:
    a real auth failure -> authenticated False; a "not found" or a transient
    provider error -> authenticated True (the key itself was accepted)."""
    from routers import verifications
    from core import gstverify_gst

    async def fake_settings():
        return {"gst_provider": "rapidapi", "gst_api_key": "rapid-key-123"}

    monkeypatch.setattr(verifications, "get_verification_settings", fake_settings)
    # resolve_gst_key reads the raw key; with no encryption it returns it as-is.

    # 1. Auth rejected by both providers -> not authenticated.
    async def reject(gstin, key, provider):
        raise gstverify_gst.GstProviderAuthError()
    monkeypatch.setattr(verifications, "_lookup_gst_with_fallback", reject)
    res = await verifications.gst_health(user={"id": "u", "name": "admin"})
    assert res["configured"] is True
    assert res["authenticated"] is False

    # 2. Probe GSTIN simply not found -> key authenticates fine.
    async def not_found(gstin, key, provider):
        raise gstverify_gst.GstinNotFound()
    monkeypatch.setattr(verifications, "_lookup_gst_with_fallback", not_found)
    res = await verifications.gst_health(user={"id": "u", "name": "admin"})
    assert res["authenticated"] is True

    # 3. Transient provider error (rate limit / outage) -> authenticated, warned.
    async def unavailable(gstin, key, provider):
        raise gstverify_gst.GstProviderUnavailable("Rate limit exceeded.")
    monkeypatch.setattr(verifications, "_lookup_gst_with_fallback", unavailable)
    res = await verifications.gst_health(user={"id": "u", "name": "admin"})
    assert res["authenticated"] is True
    assert "warning" in res

    # 4. Clean success -> authenticated, no warning.
    async def ok(gstin, key, provider):
        return {"company_name": "X", "trade_name": "X", "source": "rapidapi"}
    monkeypatch.setattr(verifications, "_lookup_gst_with_fallback", ok)
    res = await verifications.gst_health(user={"id": "u", "name": "admin"})
    assert res["authenticated"] is True
    assert res.get("warning") is None

