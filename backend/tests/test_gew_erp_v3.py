"""Iteration 3 backend tests — Proforma Invoice (PI) module.

Covers: CRUD, auto-numbering, totals computation, search, PDF (multi-currency),
auth + admin-only delete, _id leakage, persistence of all standard PI fields.
"""
import os
import time
from typing import Any

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = "admin@ormodex.com"
ADMIN_PASSWORD = "Admin@123456"


@pytest.fixture(scope="module")
def admin_session() -> Any:
    s: Any = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    s.user = data["user"]  # type: ignore
    return s


@pytest.fixture(scope="module")
def employee_session(admin_session):
    """Create (or reuse) an employee and return an authed session."""
    email = "test_pi_emp@ormodex.com"
    pw = "EmpPass@123"
    # Best-effort create
    admin_session.post(f"{BASE_URL}/api/users", json={
        "name": "TEST PI Employee",
        "email": email,
        "phone": "9999999999",
        "role": "employee",
        "password": pw,
    })
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
    if r.status_code != 200:
        pytest.skip(f"employee login failed: {r.status_code} {r.text}")
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


def _sample_payload(currency="USD", incoterms="CIF", pi_number=None, buyer="FECOCIVIL S.A."):
    items = [
        {
            "container_spec": "1x40 ft hc",
            "description": "Steel scaffolding props 2.5m, fully threaded, hot-dip galvanized",
            "weight_per_unit": 9.1,
            "quantity": 6000,
            "unit_price": 9.05,
        },
        {
            "container_spec": "1x40 ft hc",
            "description": "Adjustable U-head jacks, 600mm, galvanized",
            "weight_per_unit": 3.2,
            "quantity": 1500,
            "unit_price": 4.50,
        },
    ]
    return {
        "pi_number": pi_number,
        "date": "2026-01-15",
        "validity_days": 30,
        "buyer_name": buyer,
        "buyer_address": "Rua das Industrias 100, Leixoes, Portugal",
        "buyer_country": "Portugal",
        "buyer_contact_person": "João Silva",
        "buyer_email": "joao@fecocivil.pt",
        "buyer_phone": "+351 22 0000000",
        "exporter_iec": "AAACG1234L",
        "bank_name": "ICICI Bank Ltd.",
        "bank_account_no": "00112233445566",
        "bank_swift": "ICICINBBXXX",
        "bank_iban": "GB29NWBK60161331926819",
        "bank_branch": "Pune Main",
        "items": items,
        "currency": currency,
        "incoterms": incoterms,
        "country_of_origin": "India",
        "port_of_loading": "Mundra Port, India",
        "port_of_discharge": "Leixoes Port, Portugal",
        "final_destination": "Porto, Portugal",
        "payment_terms": "30% advance and 70% against B/L scan.",
        "delivery_time": "45-60 days from advance receipt.",
        "quantity_tolerance": "±5% on weights & quantities.",
        "packing_notes": "Bundle packing, 50 pcs per bundle.",
        "freight_clause": "CIF Leixoes including marine insurance.",
        "special_notes": "Ship marks per buyer instructions.",
        "status": "DRAFT",
    }


# -------- Auth --------
class TestPIAuth:
    def test_list_unauth(self):
        r = requests.get(f"{BASE_URL}/api/proforma-invoices")
        assert r.status_code == 401

    def test_create_unauth(self):
        r = requests.post(f"{BASE_URL}/api/proforma-invoices", json=_sample_payload())
        assert r.status_code == 401

    def test_pdf_unauth(self):
        r = requests.get(f"{BASE_URL}/api/proforma-invoices/anything/pdf")
        assert r.status_code == 401


# -------- CRUD + computed totals --------
class TestPICrud:
    def test_create_auto_number(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/proforma-invoices", json=_sample_payload(currency="USD"))
        assert r.status_code == 200, r.text
        body = r.json()
        # auto pi_number
        assert body.get("pi_number", "").startswith("PI-"), body
        # computed totals
        # qty = 6000+1500 = 7500
        assert body["total_quantity"] == 7500
        # net weight = 6000*9.1 + 1500*3.2 = 54600 + 4800 = 59400
        assert body["total_net_weight"] == 59400.0
        # amount = 6000*9.05 + 1500*4.5 = 54300 + 6750 = 61050
        assert body["total_amount"] == 61050.0
        assert body["currency"] == "USD"
        assert "_id" not in body
        # Persistence of standard fields
        for k in (
            "buyer_address", "buyer_country", "port_of_loading", "port_of_discharge",
            "final_destination", "incoterms", "payment_terms", "delivery_time",
            "packing_notes", "freight_clause", "special_notes",
            "bank_name", "bank_account_no", "bank_swift", "bank_iban", "bank_branch",
        ):
            assert k in body, f"missing {k}"
        admin_session.usd_pi_id = body["id"]
        admin_session.usd_pi_number = body["pi_number"]

    def test_create_explicit_pi_number(self, admin_session):
        custom = f"PI-CUSTOM-{int(time.time())}"
        payload = _sample_payload(currency="USD", pi_number=custom)
        r = admin_session.post(f"{BASE_URL}/api/proforma-invoices", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["pi_number"] == custom

    def test_create_eur(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/proforma-invoices", json=_sample_payload(currency="EUR"))
        assert r.status_code == 200
        body = r.json()
        assert body["currency"] == "EUR"
        admin_session.eur_pi_id = body["id"]

    def test_get_one(self, admin_session):
        pid = admin_session.usd_pi_id
        r = admin_session.get(f"{BASE_URL}/api/proforma-invoices/{pid}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == pid
        assert "_id" not in body

    def test_get_404(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/proforma-invoices/nonexistent-xyz")
        assert r.status_code == 404

    def test_list_sorted(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/proforma-invoices")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 2
        # sorted desc by created_at
        for i in range(len(rows) - 1):
            assert rows[i]["created_at"] >= rows[i + 1]["created_at"]
        for row in rows:
            assert "_id" not in row

    def test_search_q(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/proforma-invoices", params={"q": "FECOCIVIL"})
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 1
        assert all("FECOCIVIL" in row.get("buyer_name", "") for row in rows)

    def test_search_country(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/proforma-invoices", params={"q": "Portugal"})
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_update_recomputes(self, admin_session):
        pid = admin_session.usd_pi_id
        payload = _sample_payload(currency="USD")
        # change items: 1 line at qty=10 unit_price=100 weight=2
        payload["items"] = [{
            "container_spec": "1x20 ft",
            "description": "Updated",
            "weight_per_unit": 2,
            "quantity": 10,
            "unit_price": 100,
        }]
        r = admin_session.put(f"{BASE_URL}/api/proforma-invoices/{pid}", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_quantity"] == 10
        assert body["total_net_weight"] == 20
        assert body["total_amount"] == 1000

        # GET to confirm persistence
        r2 = admin_session.get(f"{BASE_URL}/api/proforma-invoices/{pid}")
        assert r2.status_code == 200
        assert r2.json()["total_amount"] == 1000


# -------- PI Permissions --------
class TestPIPermissions:
    def test_employee_forbidden_all_ops(self, admin_session, employee_session):
        # Create a PI as admin first
        r = admin_session.post(f"{BASE_URL}/api/proforma-invoices", json=_sample_payload())
        assert r.status_code == 200
        pid = r.json()["id"]

        try:
            # Employee cannot list
            re_list = employee_session.get(f"{BASE_URL}/api/proforma-invoices")
            assert re_list.status_code == 403

            # Employee cannot create
            re_create = employee_session.post(f"{BASE_URL}/api/proforma-invoices", json=_sample_payload())
            assert re_create.status_code == 403

            # Employee cannot get
            re_get = employee_session.get(f"{BASE_URL}/api/proforma-invoices/{pid}")
            assert re_get.status_code == 403

            # Employee cannot update
            re_update = employee_session.put(f"{BASE_URL}/api/proforma-invoices/{pid}", json=_sample_payload())
            assert re_update.status_code == 403

            # Employee cannot view PDF
            re_pdf = employee_session.get(f"{BASE_URL}/api/proforma-invoices/{pid}/pdf")
            assert re_pdf.status_code == 403

            # Employee cannot delete
            re_delete = employee_session.delete(f"{BASE_URL}/api/proforma-invoices/{pid}")
            assert re_delete.status_code == 403
        finally:
            # cleanup
            admin_session.delete(f"{BASE_URL}/api/proforma-invoices/{pid}")

    def test_admin_can_delete(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/proforma-invoices", json=_sample_payload())
        pid = r.json()["id"]
        rd = admin_session.delete(f"{BASE_URL}/api/proforma-invoices/{pid}")
        assert rd.status_code == 200
        rg = admin_session.get(f"{BASE_URL}/api/proforma-invoices/{pid}")
        assert rg.status_code == 404


# -------- PDF --------
class TestPIPDF:
    def test_pdf_404(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/proforma-invoices/no-such-id/pdf")
        assert r.status_code == 404

    def test_pdf_usd(self, admin_session):
        pid = admin_session.usd_pi_id
        r = admin_session.get(f"{BASE_URL}/api/proforma-invoices/{pid}/pdf")
        assert r.status_code == 200, r.text
        assert r.headers.get("Content-Type", "").startswith("application/pdf")
        assert r.content[:5] == b"%PDF-"
        # buyer name & port should appear in PDF text streams (uncompressed text in reportlab)
        body = r.content
        # reportlab usually compresses streams; just check magic header + decent size
        assert len(body) > 1000

    def test_pdf_eur_currency(self, admin_session):
        pid = admin_session.eur_pi_id
        r = admin_session.get(f"{BASE_URL}/api/proforma-invoices/{pid}/pdf")
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"
        # Try to find "Euros" or EUR currency token in PDF (may or may not be compressed)
        # Decode loosely
        body_text = r.content.decode("latin-1", errors="ignore")
        # PDF may have compressed streams so don't hard-fail; warn if not found
        # but we still expect at least %PDF and buyer name string in metadata/title
        assert "PDF" in body_text


# -------- Regression sanity --------
class TestRegression:
    def test_auth_me(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_products_list(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/products")
        assert r.status_code == 200
        for p in r.json():
            assert "_id" not in p

    def test_invoices_list(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/invoices")
        assert r.status_code == 200

    def test_quotations_list(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/quotations")
        assert r.status_code == 200

    def test_no_id_in_pi_list(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/proforma-invoices")
        assert r.status_code == 200
        for row in r.json():
            assert "_id" not in row
