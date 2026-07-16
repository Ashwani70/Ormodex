"""Regression tests for the purchase / job-work / bank-statement PDF builders.

These guard the builders added alongside the sales templates:
  * normalize_purchase_doc() maps lines/qty/rate → items/quantity/unit_price and
    recomputes subtotal/GST/total from the lines.
  * build_doc_pdf() renders PURCHASE INVOICE / DEBIT NOTE / CREDIT NOTE with a
    switchable party label.
  * build_jobwork_pdf() renders a money-free challan.
  * build_bank_statement_pdf() renders a ledger and carries a running balance.

Like test_pdf_rupee_font, text-layer assertions skip when pypdf is unavailable
(reportlab stores glyph codes in compressed streams, so byte-scanning is
unreliable); the build-and-nonempty checks always run.
"""
import io

import pytest

from core import pdf as pdfmod


def _pdf_text(data: bytes):
    """Extract the text layer via pypdf, or None when it isn't installed."""
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return None
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(p.extract_text() or "" for p in reader.pages)


def _is_pdf(data: bytes) -> bool:
    return data[:4] == b"%PDF" and len(data) > 1000


# --- normalize_purchase_doc -------------------------------------------------

def test_normalize_maps_lines_and_computes_totals():
    doc = {
        "vendor_name": "Acme Steel Co",
        "vendor": {"name": "Acme Steel Co", "gstin": "27ABCDE1234F1Z1"},
        "lines": [
            {"item_name": "MS Plate 10mm", "qty": 50, "rate": 85.5, "gst_rate": 18},
            {"item_name": "Welding Rod", "qty": 200, "rate": 12, "gst_rate": 18},
        ],
    }
    out = pdfmod.normalize_purchase_doc(doc, party_field="vendor")

    # lines → items with the sales-shaped field names
    assert len(out["items"]) == 2
    assert out["items"][0]["product_name"] == "MS Plate 10mm"
    assert out["items"][0]["quantity"] == 50
    assert out["items"][0]["unit_price"] == 85.5

    # party mapped onto customer / customer_name
    assert out["customer_name"] == "Acme Steel Co"
    assert out["customer"]["gstin"] == "27ABCDE1234F1Z1"

    # totals derived from the lines: 50*85.5 + 200*12 = 4275 + 2400 = 6675
    assert out["subtotal"] == 6675.0
    assert out["gst_amount"] == round(6675.0 * 0.18, 2)
    assert out["total"] == round(6675.0 * 1.18, 2)


def test_normalize_leaves_sales_shaped_doc_untouched():
    doc = {"items": [{"product_name": "X", "quantity": 1, "unit_price": 10}], "customer_name": "Neha"}
    assert pdfmod.normalize_purchase_doc(doc) is doc


def test_normalize_prefers_stored_totals_over_computed():
    doc = {
        "vendor_name": "V",
        "lines": [{"item_name": "A", "qty": 1, "rate": 100, "gst_rate": 18}],
        "subtotal": 999.0,  # stored value must win over the computed 100.0
    }
    out = pdfmod.normalize_purchase_doc(doc, party_field="vendor")
    assert out["subtotal"] == 999.0


# --- purchase invoice / debit note / credit note ----------------------------

def _vendor_doc():
    return {
        "vendor_name": "Acme Steel Co",
        "vendor": {"name": "Acme Steel Co", "address": "MIDC Pune", "gstin": "27ABCDE1234F1Z1"},
        "place_of_supply": "Maharashtra",
        "lines": [{"item_name": "MS Plate 10mm", "qty": 50, "rate": 85.5, "gst_rate": 18}],
    }


@pytest.mark.parametrize("label", ["PURCHASE ORDER", "PURCHASE INVOICE", "DEBIT NOTE", "CREDIT NOTE"])
def test_vendor_docs_build(label):
    doc = pdfmod.normalize_purchase_doc(_vendor_doc(), party_field="vendor")
    data = pdfmod.build_doc_pdf(label, "DOC-1", doc, party_label="VENDOR")
    assert _is_pdf(data)


def test_purchase_order_text_layer():
    doc = pdfmod.normalize_purchase_doc(_vendor_doc(), party_field="vendor")
    text = _pdf_text(pdfmod.build_doc_pdf("PURCHASE ORDER", "PO-9", doc, party_label="VENDOR"))
    if text is None:
        pytest.skip("pypdf not installed; cannot inspect PDF text layer")
    assert "PURCHASE ORDER" in text
    assert "Acme Steel Co" in text
    assert "MS Plate 10mm" in text


def test_purchase_invoice_text_layer():
    doc = pdfmod.normalize_purchase_doc(_vendor_doc(), party_field="vendor")
    text = _pdf_text(pdfmod.build_doc_pdf("PURCHASE INVOICE", "BILL-7", doc, party_label="VENDOR"))
    if text is None:
        pytest.skip("pypdf not installed; cannot inspect PDF text layer")
    assert "PURCHASE INVOICE" in text
    assert "VENDOR" in text
    assert "Acme Steel Co" in text
    assert "MS Plate 10mm" in text


def test_credit_note_fixed_schema_renders_customer_side():
    # The CreditNote schema is already sales-shaped (items + customer), so it
    # renders straight through build_doc_pdf without normalize_purchase_doc.
    doc = {
        "credit_note_number": "CN-1",
        "customer_name": "Ormodex Partner Ltd",
        "customer": {"name": "Ormodex Partner Ltd", "gstin": "03ABBFG0319E1Z7"},
        "reason": "Sales return",
        "items": [{"product_name": "Base jack", "quantity": 10, "unit_price": 120, "gst_rate": 18}],
        "subtotal": 1200.0, "gst_amount": 216.0, "total": 1416.0, "igst": 216.0,
    }
    text = _pdf_text(pdfmod.build_doc_pdf("CREDIT NOTE", "CN-1", doc, party_label="CUSTOMER"))
    if text is None:
        pytest.skip("pypdf not installed; cannot inspect PDF text layer")
    assert "CREDIT NOTE" in text
    assert "CUSTOMER" in text
    assert "Ormodex Partner Ltd" in text
    assert "Base jack" in text


# --- job work challan -------------------------------------------------------

def _challan():
    return {
        "challan_number": "JWC-11", "date": "2026-06-15", "job_worker_name": "Sharma Fab",
        "nature": "inputs", "status": "PENDING",
        "items": [
            {"product_name": "Casting blank A", "sku": "CB-A", "quantity": 120, "unit": "pcs"},
            {"product_name": "Shaft rod", "sku": "SR-9", "quantity": 40, "unit": "pcs"},
        ],
        "notes": "Return after machining.",
    }


def test_jobwork_builds():
    assert _is_pdf(pdfmod.build_jobwork_pdf(_challan()))


def test_jobwork_text_layer_has_no_money_and_section_143():
    text = _pdf_text(pdfmod.build_jobwork_pdf(_challan()))
    if text is None:
        pytest.skip("pypdf not installed; cannot inspect PDF text layer")
    assert "JOB WORK CHALLAN" in text
    assert "Sharma Fab" in text
    assert "Casting blank A" in text
    assert "Section 143" in text  # the non-supply / no-GST disclaimer
    # money columns must not appear on a job-work challan
    assert "RATE" not in text
    assert "AMOUNT" not in text


def test_jobwork_handles_empty_items():
    assert _is_pdf(pdfmod.build_jobwork_pdf({"challan_number": "JWC-0", "items": []}))


# --- bank statement ---------------------------------------------------------

def _stmt_lines():
    return [
        {"transaction_date": "2026-06-02", "description": "NEFT from Customer X", "ref_number": "N1", "credit": 50000, "debit": 0},
        {"transaction_date": "2026-06-05", "description": "Vendor payment", "ref_number": "C45", "credit": 0, "debit": 18000},
        {"transaction_date": "2026-06-09", "description": "Bank charges", "ref_number": "", "credit": 0, "debit": 236},
    ]


def test_bank_statement_builds():
    data = pdfmod.build_bank_statement_pdf(
        "HDFC Current A/c", _stmt_lines(),
        from_date="2026-06-01", to_date="2026-06-30", opening_balance=12500.0,
    )
    assert _is_pdf(data)


def test_bank_statement_text_layer_and_running_balance():
    text = _pdf_text(pdfmod.build_bank_statement_pdf(
        "HDFC Current A/c", _stmt_lines(),
        from_date="2026-06-01", to_date="2026-06-30", opening_balance=12500.0,
    ))
    if text is None:
        pytest.skip("pypdf not installed; cannot inspect PDF text layer")
    assert "BANK STATEMENT" in text
    assert "HDFC Current A/c" in text
    assert "Opening Balance" in text
    # closing balance: 12500 + 50000 - 18000 - 236 = 44264
    assert "44,264" in text


def test_bank_statement_empty_lines_builds():
    data = pdfmod.build_bank_statement_pdf("Empty A/c", [], opening_balance=0.0)
    assert _is_pdf(data)
