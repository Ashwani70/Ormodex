"""Iteration 4 backend tests — Resend email integration.

Covers: GET /email/status, POST /email/test (admin only), POST /email/{type}/{id}
for quotation/sales_order/invoice/dispatch/proforma; auth, 404, 400 unknown type,
last_sent_at + last_sent_to persistence, _id never in email_logs, GET /email/logs.
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = "admin@gravityone.com"
ADMIN_PASSWORD = "Admin@123"
DELIVERED = "delivered@resend.dev"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    s.user = data["user"]
    return s


@pytest.fixture(scope="module")
def employee_session(admin_session):
    email = "test_email_emp@gravityone.com"
    pw = "EmpPass@123"
    admin_session.post(f"{BASE_URL}/api/users", json={
        "name": "TEST Email Employee",
        "email": email,
        "phone": "9999999999",
        "role": "employee",
        "password": pw,
    })
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
    if r.status_code != 200:
        pytest.skip(f"employee login failed: {r.status_code}")
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


# ------- Status / Auth ----------
class TestEmailStatus:
    def test_status_unauth(self):
        r = requests.get(f"{BASE_URL}/api/email/status")
        assert r.status_code == 401

    def test_status_configured(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/email/status")
        assert r.status_code == 200
        body = r.json()
        assert body.get("configured") is True

    def test_logs_unauth(self):
        r = requests.get(f"{BASE_URL}/api/email/logs")
        assert r.status_code == 401


# ------- /email/test ----------
class TestEmailTest:
    def test_test_unauth(self):
        r = requests.post(f"{BASE_URL}/api/email/test", json={"to": DELIVERED})
        assert r.status_code == 401

    def test_test_employee_forbidden(self, employee_session):
        r = employee_session.post(f"{BASE_URL}/api/email/test", json={"to": DELIVERED})
        assert r.status_code == 403

    def test_test_invalid_email(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/email/test", json={"to": "not-an-email"})
        assert r.status_code == 422

    def test_test_admin_send(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/email/test", json={"to": DELIVERED})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("message_id"), f"missing message_id: {body}"
        admin_session.last_test_msg_id = body["message_id"]

    def test_logs_contain_test(self, admin_session):
        # tiny delay to allow log insert
        time.sleep(0.5)
        r = admin_session.get(f"{BASE_URL}/api/email/logs")
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert len(rows) >= 1
        for row in rows:
            assert "_id" not in row
        # most recent first
        assert rows[0].get("doc_type") == "test" or any(r.get("doc_type") == "test" for r in rows[:5])
        # status sent
        recent_test_rows = [r for r in rows if r.get("doc_type") == "test" and r.get("status") == "sent"]
        assert recent_test_rows, "expected at least one sent test log"


# ------- Doc-type email send ----------
def _ensure_quotation(s):
    # Try existing
    r = s.get(f"{BASE_URL}/api/quotations")
    if r.status_code == 200 and r.json():
        return r.json()[0]
    # else create one with a product
    pr = s.get(f"{BASE_URL}/api/products")
    pid = pr.json()[0]["id"] if pr.json() else None
    if not pid:
        # Create product
        cp = s.post(f"{BASE_URL}/api/products", json={
            "name": "TEST EMAIL PRODUCT", "sku": f"TEST-{int(time.time())}",
            "unit_price": 100, "stock_quantity": 100, "tax_rate": 18,
        })
        pid = cp.json()["id"]
    payload = {
        "customer_name": "TEST EMAIL Customer",
        "customer_email": DELIVERED,
        "customer_phone": "1234567890",
        "customer_address": "Addr",
        "items": [{"product_id": pid, "product_name": "TEST", "quantity": 1, "unit_price": 100, "tax_rate": 18, "discount": 0}],
        "status": "DRAFT",
        "notes": "test",
    }
    r2 = s.post(f"{BASE_URL}/api/quotations", json=payload)
    assert r2.status_code == 200, r2.text
    return r2.json()


def _ensure_proforma(s):
    r = s.get(f"{BASE_URL}/api/proforma-invoices")
    if r.status_code == 200 and r.json():
        return r.json()[0]
    payload = {
        "date": "2026-01-15",
        "buyer_name": "TEST BUYER",
        "buyer_email": DELIVERED,
        "items": [{"container_spec": "1x20", "description": "x", "weight_per_unit": 2, "quantity": 10, "unit_price": 100}],
        "currency": "USD", "incoterms": "FOB", "status": "DRAFT",
    }
    r2 = s.post(f"{BASE_URL}/api/proforma-invoices", json=payload)
    assert r2.status_code == 200, r2.text
    return r2.json()


class TestSendDocEmail:
    def test_unauth(self):
        r = requests.post(f"{BASE_URL}/api/email/quotation/anything", json={"to": DELIVERED})
        assert r.status_code == 401

    def test_unknown_doc_type(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/email/foo/anything", json={"to": DELIVERED})
        assert r.status_code == 400

    def test_nonexistent_doc(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/email/quotation/nonexistent-xyz", json={"to": DELIVERED})
        assert r.status_code == 404

    def test_invalid_email(self, admin_session):
        q = _ensure_quotation(admin_session)
        r = admin_session.post(f"{BASE_URL}/api/email/quotation/{q['id']}", json={"to": "bad-format"})
        assert r.status_code == 422

    def test_send_quotation(self, admin_session):
        q = _ensure_quotation(admin_session)
        r = admin_session.post(f"{BASE_URL}/api/email/quotation/{q['id']}", json={"to": DELIVERED, "message": "Hello"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("message_id")
        assert body.get("sent_to") == DELIVERED

        # GET the quotation back, expect last_sent_at and last_sent_to set
        rg = admin_session.get(f"{BASE_URL}/api/quotations/{q['id']}")
        assert rg.status_code == 200
        d = rg.json()
        assert d.get("last_sent_to") == DELIVERED
        assert d.get("last_sent_at")
        assert "_id" not in d

    def test_send_proforma(self, admin_session):
        p = _ensure_proforma(admin_session)
        r = admin_session.post(f"{BASE_URL}/api/email/proforma/{p['id']}", json={"to": DELIVERED})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        # Persist check
        rg = admin_session.get(f"{BASE_URL}/api/proforma-invoices/{p['id']}")
        assert rg.status_code == 200
        assert rg.json().get("last_sent_to") == DELIVERED

    def test_send_sales_order_if_present(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/sales-orders")
        if r.status_code != 200 or not r.json():
            pytest.skip("no sales orders to test")
        so = r.json()[0]
        rs = admin_session.post(f"{BASE_URL}/api/email/sales_order/{so['id']}", json={"to": DELIVERED})
        assert rs.status_code == 200, rs.text
        assert rs.json().get("ok") is True

    def test_send_invoice_if_present(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/invoices")
        if r.status_code != 200 or not r.json():
            pytest.skip("no invoices to test")
        inv = r.json()[0]
        ri = admin_session.post(f"{BASE_URL}/api/email/invoice/{inv['id']}", json={"to": DELIVERED})
        assert ri.status_code == 200, ri.text
        assert ri.json().get("ok") is True

    def test_send_dispatch_if_present(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/dispatches")
        if r.status_code != 200 or not r.json():
            pytest.skip("no dispatches to test")
        dis = r.json()[0]
        rd = admin_session.post(f"{BASE_URL}/api/email/dispatch/{dis['id']}", json={"to": DELIVERED})
        assert rd.status_code == 200, rd.text
        assert rd.json().get("ok") is True


# ------- Logs after sends ----------
class TestEmailLogs:
    def test_logs_have_doc_rows(self, admin_session):
        time.sleep(0.5)
        r = admin_session.get(f"{BASE_URL}/api/email/logs")
        assert r.status_code == 200
        rows = r.json()
        # Most recent first - check sorted desc
        for i in range(len(rows) - 1):
            assert rows[i]["created_at"] >= rows[i + 1]["created_at"]
        # No _id leaks
        for row in rows:
            assert "_id" not in row
        # quotation status sent rows expected
        sent_quot = [r for r in rows if r.get("doc_type") == "quotation" and r.get("status") == "sent"]
        assert sent_quot, "expected at least one sent quotation log"
        # message_id present when sent
        for r in sent_quot[:3]:
            assert r.get("message_id"), "sent log should carry message_id"


# ------- Regression sanity ----------
class TestRegression:
    def test_auth_me(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200

    def test_pi_list_no_id(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/proforma-invoices")
        assert r.status_code == 200
        for row in r.json():
            assert "_id" not in row
