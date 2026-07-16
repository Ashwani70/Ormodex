import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = "admin@ormodex.com"
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
    return s

@pytest.fixture(scope="module")
def accounts_session(admin_session):
    email = f"accounts_{uuid.uuid4().hex[:6]}@ormodex.com"
    password = "AccountsPass@123"
    
    admin_session.post(
        f"{BASE_URL}/api/users",
        json={
            "name": "Test Accountant",
            "email": email,
            "phone": "9876543211",
            "role": "accountant",
            "password": password,
            "module_permissions": ["sales", "accounting"]
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
def dispatch_session(admin_session):
    email = f"dispatch_{uuid.uuid4().hex[:6]}@ormodex.com"
    password = "DispatchPass@123"
    
    admin_session.post(
        f"{BASE_URL}/api/users",
        json={
            "name": "Test Dispatcher",
            "email": email,
            "phone": "9876543212",
            "role": "employee",
            "password": password,
            "module_permissions": ["dispatch"]
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
def viewer_session(admin_session):
    email = f"viewer_{uuid.uuid4().hex[:6]}@ormodex.com"
    password = "ViewerPass@123"
    
    admin_session.post(
        f"{BASE_URL}/api/users",
        json={
            "name": "Test Viewer",
            "email": email,
            "phone": "9876543213",
            "role": "employee",
            "password": password,
            "module_permissions": []  # empty module permissions, viewer only
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

def test_eway_bill_integration_flow(admin_session, accounts_session, dispatch_session, viewer_session, anon_session):
    # Setup prerequisite records: company profile, customer
    # Ensure company profile exists
    admin_session.post(
        f"{BASE_URL}/api/company",
        json={
            "name": "Ormodex",
            "address": "123 Industrial Area, Pune",
            "gstin": "27AABCG1234F1Z5",
            "state": "Maharashtra",
            "state_code": "27",
            "phone": "9876543210",
            "email": "info@ormodex.com"
        }
    )

    # Ensure a customer exists with valid GSTIN
    cust_res = admin_session.post(
        f"{BASE_URL}/api/customers",
        json={
            "name": "Acme Builders",
            "company": "Acme Builders Pvt Ltd",
            "email": "acme@builders.com",
            "phone": "9999999999",
            "address": "456 Construction St, Mumbai",
            "gstin": "27ABCDE1234F1Z5",
            "state_code": "27",
            "state": "Maharashtra",
            "pincode": "400001",
            "registration_type": "Regular"
        }
    )
    assert cust_res.status_code == 200
    customer_id = cust_res.json()["id"]

    # Ensure a product with HSN code exists
    prod_res = admin_session.post(
        f"{BASE_URL}/api/products",
        json={
            "name": "Scaffolding Tubes",
            "sku": f"ST-{uuid.uuid4().hex[:6].upper()}",
            "category": "Steel",
            "unit": "pcs",
            "cost_price": 500.0,
            "selling_price": 700.0,
            "quantity": 1000.0,
            "low_stock_threshold": 10.0,
            "hsn_code": "7308",
            "gst_rate": 18.0
        }
    )
    assert prod_res.status_code == 200
    product = prod_res.json()

    # 1. Create a low-value invoice (₹40,000 taxable -> less than ₹50,000 total)
    inv_low_res = admin_session.post(
        f"{BASE_URL}/api/invoices",
        json={
            "customer_id": customer_id,
            "invoice_type": "TAX_INVOICE",
            "items": [
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "sku": product["sku"],
                    "quantity": 50,
                    "unit_price": 600.0,  # total 30,000 + GST = 35,400
                    "gst_rate": 18.0,
                    "hsn_code": product["hsn_code"]
                }
            ],
            "notes": "Low value test"
        }
    )
    assert inv_low_res.status_code == 200
    invoice_low_id = inv_low_res.json()["id"]

    # 2. Create a high-value invoice (₹60,000 taxable -> greater than ₹50,000 total)
    inv_high_res = admin_session.post(
        f"{BASE_URL}/api/invoices",
        json={
            "customer_id": customer_id,
            "invoice_type": "TAX_INVOICE",
            "items": [
                {
                    "product_id": product["id"],
                    "product_name": product["name"],
                    "sku": product["sku"],
                    "quantity": 100,
                    "unit_price": 600.0,  # total 60,000 + GST = 70,800
                    "gst_rate": 18.0,
                    "hsn_code": product["hsn_code"]
                }
            ],
            "notes": "High value test"
        }
    )
    assert inv_high_res.status_code == 200
    invoice_high = inv_high_res.json()
    invoice_high_id = invoice_high["id"]

    # --- Test Threshold Constraint ---
    # Attempting to generate EWB for low-value invoice should fail
    ewb_low_res = admin_session.post(
        f"{BASE_URL}/api/ewaybill/generate",
        json={
            "invoice_id": invoice_low_id,
            "transport_mode": "ROAD",
            "distance_km": 120.0,
            "vehicle_number": "MH12AB1234"
        }
    )
    assert ewb_low_res.status_code == 400
    assert "does not exceed Rs" in ewb_low_res.text

    # --- Test E-Invoicing Gate Constraint ---
    # First, let's enable e-Invoicing global setting to test the constraint
    admin_session.post(
        f"{BASE_URL}/api/verifications/settings",
        json={
            "gst_api_key": "test-gst-key",
            "gst_api_enabled": True,  # this simulates e-invoicing configured/enabled
            "pan_api_key": "test-pan-key",
            "pan_api_enabled": True,
            "aadhaar_api_key": "test-aadhaar-key",
            "aadhaar_api_enabled": True
        }
    )
    r_setting = admin_session.post(
        f"{BASE_URL}/api/invoices/einvoice/settings",
        json={
            "irp_username": "test-irp-user",
            "irp_password": "test-irp-password",
            "irp_enabled": True
        }
    )
    assert r_setting.status_code == 200, f"Failed to enable e-invoicing settings: {r_setting.text}"
    
    # Attempting to generate EWB for high-value invoice without IRN should fail
    ewb_no_irn_res = admin_session.post(
        f"{BASE_URL}/api/ewaybill/generate",
        json={
            "invoice_id": invoice_high_id,
            "transport_mode": "ROAD",
            "distance_km": 120.0,
            "vehicle_number": "MH12AB1234"
        }
    )
    assert ewb_no_irn_res.status_code == 409, ewb_no_irn_res.text
    assert "generate the IRN" in ewb_no_irn_res.text

    # Disable the setting or set IRN on the invoice. Let's disable the global e-invoicing setting for simplicity,
    # or let's generate the IRN on the invoice using the e-invoice endpoint!
    # Let's generate E-Invoice first!
    einv_res = admin_session.post(f"{BASE_URL}/api/invoices/{invoice_high_id}/generate-einvoice")
    assert einv_res.status_code == 200

    # --- Test Format Validations ---
    # 1. Invalid vehicle number format
    ewb_bad_veh = admin_session.post(
        f"{BASE_URL}/api/ewaybill/generate",
        json={
            "invoice_id": invoice_high_id,
            "transport_mode": "ROAD",
            "distance_km": 120.0,
            "vehicle_number": "MH-12-AB-123"  # invalid format
        }
    )
    assert ewb_bad_veh.status_code == 400
    assert "validation failed" in ewb_bad_veh.text or "Invalid vehicle number" in ewb_bad_veh.text

    # 2. Invalid distance (must be > 0)
    ewb_bad_dist = admin_session.post(
        f"{BASE_URL}/api/ewaybill/generate",
        json={
            "invoice_id": invoice_high_id,
            "transport_mode": "ROAD",
            "distance_km": 0.0,
            "vehicle_number": "MH12AB1234"
        }
    )
    assert ewb_bad_dist.status_code == 400
    assert "validation failed" in ewb_bad_dist.text or "distance" in ewb_bad_dist.text

    # --- Test Successful Generation ---
    # Generating EWB using admin_session (has permission)
    ewb_gen_res = admin_session.post(
        f"{BASE_URL}/api/ewaybill/generate",
        json={
            "invoice_id": invoice_high_id,
            "transport_mode": "ROAD",
            "distance_km": 120.0,
            "vehicle_number": "MH12AB1234",
            "transporter_name": "VRL Logistics",
            "transporter_id": "27ABCDE1234F1Z5"
        }
    )
    assert ewb_gen_res.status_code == 200
    ewb_data = ewb_gen_res.json()
    ewb_number = ewb_data["ewb_number"]
    assert ewb_number is not None
    assert ewb_data["status"] == "GENERATED"
    assert ewb_data["vehicle_number"] == "MH12AB1234"

    # --- Test Duplicate Prevention ---
    ewb_dup_res = admin_session.post(
        f"{BASE_URL}/api/ewaybill/generate",
        json={
            "invoice_id": invoice_high_id,
            "transport_mode": "ROAD",
            "distance_km": 120.0,
            "vehicle_number": "MH12AB1234"
        }
    )
    assert ewb_dup_res.status_code == 409
    assert "already exists" in ewb_dup_res.text

    # --- Test Get Details ---
    # By EWB number
    ewb_get_res = admin_session.get(f"{BASE_URL}/api/ewaybill/{ewb_number}")
    assert ewb_get_res.status_code == 200
    assert ewb_get_res.json()["ewb_number"] == ewb_number
    assert ewb_get_res.json()["status"] == "GENERATED"

    # By Invoice ID
    ewb_by_inv_res = admin_session.get(f"{BASE_URL}/api/ewaybill/by-invoice/{invoice_high_id}")
    assert ewb_by_inv_res.status_code == 200
    assert ewb_by_inv_res.json()["ewb_number"] == ewb_number

    # --- Test Update Vehicle ---
    # Dispatcher has permission to update vehicle
    up_veh_res = dispatch_session.post(
        f"{BASE_URL}/api/ewaybill/update-vehicle",
        json={
            "ewb_number": ewb_number,
            "vehicle_number": "MH12CD5678",
            "from_place": "Pune",
            "reason_code": 1,
            "reason_remark": "Breakdown of first vehicle"
        }
    )
    assert up_veh_res.status_code == 200
    assert up_veh_res.json()["vehicle_number"] == "MH12CD5678"

    # Verify update reflected in GET EWB and Invoice
    ewb_get_updated = admin_session.get(f"{BASE_URL}/api/ewaybill/{ewb_number}")
    assert ewb_get_updated.json()["vehicle_number"] == "MH12CD5678"

    # Viewer cannot update vehicle
    up_veh_viewer_res = viewer_session.post(
        f"{BASE_URL}/api/ewaybill/update-vehicle",
        json={
            "ewb_number": ewb_number,
            "vehicle_number": "MH12EF9012",
            "from_place": "Pune",
            "reason_code": 1
        }
    )
    assert up_veh_viewer_res.status_code == 403

    # --- Test Extend Validity ---
    ext_res = dispatch_session.post(
        f"{BASE_URL}/api/ewaybill/extend-validity",
        json={
            "ewb_number": ewb_number,
            "remaining_distance_km": 50.0,
            "from_place": "Mumbai",
            "reason_code": 1,
            "reason_remark": "Traffic delay"
        }
    )
    assert ext_res.status_code == 200
    assert ext_res.json()["valid_until"] is not None

    # --- Test Cancel EWB ---
    # Viewer cannot cancel
    cancel_viewer_res = viewer_session.post(
        f"{BASE_URL}/api/ewaybill/cancel",
        json={
            "ewb_number": ewb_number,
            "reason_code": 2,
            "reason_remark": "Order cancelled"
        }
    )
    assert cancel_viewer_res.status_code == 403

    # Dispatcher cannot cancel
    cancel_dispatch_res = dispatch_session.post(
        f"{BASE_URL}/api/ewaybill/cancel",
        json={
            "ewb_number": ewb_number,
            "reason_code": 2,
            "reason_remark": "Order cancelled"
        }
    )
    assert cancel_dispatch_res.status_code == 403

    # Accountant (accounts_session) can cancel
    cancel_acc_res = accounts_session.post(
        f"{BASE_URL}/api/ewaybill/cancel",
        json={
            "ewb_number": ewb_number,
            "reason_code": 2,
            "reason_remark": "Order cancelled"
        }
    )
    assert cancel_acc_res.status_code == 200
    assert cancel_acc_res.json()["status"] == "CANCELLED"

    # Verify cancel reflected in GET EWB and Invoice
    ewb_get_cancelled = admin_session.get(f"{BASE_URL}/api/ewaybill/{ewb_number}")
    assert ewb_get_cancelled.json()["status"] == "CANCELLED"

    # --- Test PDF Download ---
    pdf_res = admin_session.get(f"{BASE_URL}/api/ewaybill/{ewb_number}/pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers.get("content-type") == "application/pdf"
    assert len(pdf_res.content) > 0

    # --- Test Audit Logs ---
    # Fetch audit logs to ensure events were recorded
    audit_res = admin_session.get(f"{BASE_URL}/api/audit")
    assert audit_res.status_code == 200
    audit_logs = audit_res.json()["items"]
    
    # We should have at least the CREATE log and UPDATE logs for eway_bills
    ewb_audit_actions = [log["action"] for log in audit_logs if log["collection_name"] == "eway_bills"]
    assert "CREATE" in ewb_audit_actions
    assert "UPDATE" in ewb_audit_actions

    # Cleanup e-Invoicing settings
    admin_session.post(
        f"{BASE_URL}/api/invoices/einvoice/settings",
        json={
            "irp_username": "",
            "irp_password": "",
            "irp_enabled": False
        }
    )
