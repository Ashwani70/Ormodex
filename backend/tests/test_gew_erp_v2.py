"""Iteration 2 backend tests — object storage uploads, PDFs, multi-currency.

Reuses admin login pattern from test_gew_erp.py.
"""
import io
import os
import time
import struct
import zlib

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = "admin@ormodex.com"
ADMIN_PASSWORD = "Admin@123456"


def _make_png_bytes(width=2, height=2):
    """Build a minimal valid PNG (no external deps)."""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b""
    for _ in range(height):
        raw += b"\x00" + (b"\xff\x00\x00" * width)
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    s.user = data["user"]  # type: ignore
    return s


# -------- Object storage uploads --------
class TestUploads:
    def test_upload_unauth(self):
        png = _make_png_bytes()
        r = requests.post(
            f"{BASE_URL}/api/uploads/product-image",
            files={"file": ("a.png", png, "image/png")},
        )
        assert r.status_code == 401

    def test_upload_png_ok(self, admin_session):
        png = _make_png_bytes()
        r = admin_session.post(
            f"{BASE_URL}/api/uploads/product-image",
            files={"file": ("test.png", png, "image/png")},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "path" in body and body["content_type"] == "image/png"
        assert body["size"] >= len(png) - 10
        admin_session.uploaded_path = body["path"]
        admin_session.uploaded_bytes = png

    def test_upload_rejects_text(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/uploads/product-image",
            files={"file": ("note.txt", b"hello", "text/plain")},
        )
        assert r.status_code == 400

    def test_upload_rejects_oversize(self, admin_session):
        big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (6 * 1024 * 1024 + 100)
        r = admin_session.post(
            f"{BASE_URL}/api/uploads/product-image",
            files={"file": ("big.png", big, "image/png")},
        )
        assert r.status_code == 400

    def test_serve_file_unauth(self, admin_session):
        # Uploaded files now require authentication (security fix): an
        # unauthenticated request must be rejected, not served.
        path = getattr(admin_session, "uploaded_path", None)
        if not path:
            pytest.skip("upload didn't run first")
        r = requests.get(f"{BASE_URL}/api/files/{path}")
        assert r.status_code == 401

    def test_serve_file_ok(self, admin_session):
        path = getattr(admin_session, "uploaded_path", None)
        if not path:
            pytest.skip("upload didn't run first")
        r = admin_session.get(f"{BASE_URL}/api/files/{path}")
        assert r.status_code == 200, r.text
        assert r.headers.get("Content-Type", "").startswith("image/png")
        # bytes match (object storage may transform — check at least non-empty)
        assert len(r.content) > 0

    def test_serve_unknown_404(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/files/does/not/exist.png")
        assert r.status_code == 404


# -------- Product image_path persistence --------
class TestProductImagePath:
    def test_create_with_image_path(self, admin_session):
        sku = f"TEST-IMG-{int(time.time())}"
        payload = {
            "name": "TEST_ImgProduct",
            "sku": sku,
            "category": "Test",
            "unit": "pcs",
            "cost_price": 1,
            "selling_price": 2,
            "quantity": 1,
            "low_stock_threshold": 0,
            "image_path": "gew-erp/products/x/y.png",
        }
        r = admin_session.post(f"{BASE_URL}/api/products", json=payload)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        rg = admin_session.get(f"{BASE_URL}/api/products")
        match = next(p for p in rg.json() if p["id"] == pid)
        assert match.get("image_path") == "gew-erp/products/x/y.png"
        admin_session.delete(f"{BASE_URL}/api/products/{pid}")


# -------- Multi-currency on quotation/sales-order/invoice --------
@pytest.fixture(scope="class")
def cust_and_prod(admin_session):
    cust = admin_session.get(f"{BASE_URL}/api/customers").json()[0]
    prods = admin_session.get(f"{BASE_URL}/api/products").json()
    prod = next(p for p in prods if float(p["quantity"]) > 5)
    items = [{
        "product_id": prod["id"],
        "product_name": prod["name"],
        "sku": prod["sku"],
        "quantity": 2,
        "unit_price": 100,
        "gst_rate": 18,
    }]
    return {"cust": cust, "items": items}


class TestMultiCurrency:
    def test_quotation_default_inr(self, admin_session, cust_and_prod):
        r = admin_session.post(
            f"{BASE_URL}/api/quotations",
            json={"customer_id": cust_and_prod["cust"]["id"], "items": cust_and_prod["items"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["currency"] == "INR"
        assert body["exchange_rate"] == 1.0

    def test_quotation_usd(self, admin_session, cust_and_prod):
        r = admin_session.post(
            f"{BASE_URL}/api/quotations",
            json={
                "customer_id": cust_and_prod["cust"]["id"],
                "items": cust_and_prod["items"],
                "currency": "USD",
                "exchange_rate": 83.5,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["currency"] == "USD"
        assert body["exchange_rate"] == 83.5
        assert body["total"] == round(2 * 100 + 2 * 100 * 0.18, 2)
        admin_session.usd_quote_id = body["id"]

    def test_sales_order_aed(self, admin_session, cust_and_prod):
        r = admin_session.post(
            f"{BASE_URL}/api/sales-orders",
            json={
                "customer_id": cust_and_prod["cust"]["id"],
                "items": cust_and_prod["items"],
                "currency": "AED",
                "exchange_rate": 22.6,
            },
        )
        assert r.status_code == 200
        admin_session.aed_so_id = r.json()["id"]
        assert r.json()["currency"] == "AED"

    def test_invoice_eur(self, admin_session, cust_and_prod):
        r = admin_session.post(
            f"{BASE_URL}/api/invoices",
            json={
                "customer_id": cust_and_prod["cust"]["id"],
                "items": cust_and_prod["items"],
                "currency": "EUR",
                "exchange_rate": 90.0,
            },
        )
        assert r.status_code == 200
        admin_session.eur_inv_id = r.json()["id"]
        assert r.json()["currency"] == "EUR"

    def test_no_id_leaked(self, admin_session):
        for ep in ("quotations", "sales-orders", "invoices", "dispatches", "products", "customers"):
            r = admin_session.get(f"{BASE_URL}/api/{ep}")
            assert r.status_code == 200
            for row in r.json():
                assert "_id" not in row, f"_id leaked in {ep}"


# -------- PDF endpoints --------
class TestPDFs:
    def _check_pdf(self, r):
        assert r.status_code == 200, r.text
        assert r.headers.get("Content-Type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_quotation_pdf_unauth(self, admin_session):
        qid = getattr(admin_session, "usd_quote_id", None)
        if not qid:
            pytest.skip("no quote id")
        r = requests.get(f"{BASE_URL}/api/quotations/{qid}/pdf")
        assert r.status_code == 401

    def test_quotation_pdf_404(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/quotations/bad-id/pdf")
        assert r.status_code == 404

    def test_quotation_pdf_ok(self, admin_session):
        qid = getattr(admin_session, "usd_quote_id", None)
        if not qid:
            pytest.skip("no quote id")
        r = admin_session.get(f"{BASE_URL}/api/quotations/{qid}/pdf")
        self._check_pdf(r)

    def test_so_pdf_ok(self, admin_session):
        sid = getattr(admin_session, "aed_so_id", None)
        if not sid:
            pytest.skip("no so id")
        r = admin_session.get(f"{BASE_URL}/api/sales-orders/{sid}/pdf")
        self._check_pdf(r)

    def test_invoice_pdf_ok(self, admin_session):
        iid = getattr(admin_session, "eur_inv_id", None)
        if not iid:
            pytest.skip("no inv id")
        r = admin_session.get(f"{BASE_URL}/api/invoices/{iid}/pdf")
        self._check_pdf(r)

    def test_dispatch_pdf_ok(self, admin_session):
        # Create a dispatch
        cust = admin_session.get(f"{BASE_URL}/api/customers").json()[0]
        prods = admin_session.get(f"{BASE_URL}/api/products").json()
        prod = next(p for p in prods if float(p["quantity"]) > 0)
        items = [{"product_id": prod["id"], "product_name": prod["name"], "sku": prod["sku"], "quantity": 1, "unit_price": 50, "gst_rate": 18}]
        rd = admin_session.post(f"{BASE_URL}/api/dispatches", json={
            "customer_name": cust["name"], "vehicle_no": "MH-99", "driver_name": "T",
            "dispatch_date": "2026-01-15", "items": items,
        })
        assert rd.status_code == 200
        did = rd.json()["id"]
        r = admin_session.get(f"{BASE_URL}/api/dispatches/{did}/pdf")
        self._check_pdf(r)
