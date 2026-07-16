"""Tests for POS — Module J.

Pure unit tests on the billing math — no live DB required.
Covers:
- GST computation: intra-state (CGST+SGST) vs inter-state (IGST), rate buckets
- payment split validation + change
- (idempotency on client_uuid is enforced by a unique index + the find-first
  guard in create_sale; the pure totals/payment logic is what's unit-tested here)
"""
import os
import sys

os.environ.setdefault("DB_NAME", "test_erp")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import HTTPException

from routers.pos import _compute_sale_totals, _validate_payment


# ══════════════════════════════════════════════════════════════
# GST computation
# ══════════════════════════════════════════════════════════════

class TestSaleTotals:
    LINES = [
        {"item_id": "A", "qty": 2, "unit_price": 100, "gst_rate": 18},   # taxable 200
        {"item_id": "B", "qty": 1, "unit_price": 500, "gst_rate": 18},   # taxable 500
    ]

    def test_taxable_value(self):
        t = _compute_sale_totals(self.LINES, is_interstate=False)
        assert t["taxable_value"] == 700.0

    def test_intrastate_splits_cgst_sgst(self):
        t = _compute_sale_totals(self.LINES, is_interstate=False)
        # 18% of 700 = 126; split → 63 + 63
        assert t["cgst"] == 63.0
        assert t["sgst"] == 63.0
        assert t["igst"] == 0.0
        assert t["grand_total"] == 826.0

    def test_interstate_uses_igst(self):
        t = _compute_sale_totals(self.LINES, is_interstate=True)
        assert t["igst"] == 126.0
        assert t["cgst"] == 0.0
        assert t["sgst"] == 0.0
        assert t["grand_total"] == 826.0

    def test_multiple_gst_rates_bucketed(self):
        lines = [
            {"item_id": "A", "qty": 1, "unit_price": 100, "gst_rate": 5},
            {"item_id": "B", "qty": 1, "unit_price": 100, "gst_rate": 18},
        ]
        t = _compute_sale_totals(lines, is_interstate=False)
        rates = {b["rate"]: b for b in t["gst_breakup"]}
        assert set(rates) == {5, 18}
        # 5% of 100 = 5 → 2.5+2.5; 18% of 100 = 18 → 9+9
        assert rates[5]["cgst"] == 2.5
        assert rates[18]["cgst"] == 9.0
        assert t["total_gst"] == 23.0

    def test_zero_gst(self):
        lines = [{"item_id": "A", "qty": 3, "unit_price": 50, "gst_rate": 0}]
        t = _compute_sale_totals(lines, is_interstate=False)
        assert t["total_gst"] == 0.0
        assert t["grand_total"] == 150.0

    def test_gst_breakup_sorted_by_rate(self):
        lines = [
            {"item_id": "A", "qty": 1, "unit_price": 100, "gst_rate": 28},
            {"item_id": "B", "qty": 1, "unit_price": 100, "gst_rate": 5},
            {"item_id": "C", "qty": 1, "unit_price": 100, "gst_rate": 12},
        ]
        t = _compute_sale_totals(lines, is_interstate=False)
        assert [b["rate"] for b in t["gst_breakup"]] == [5, 12, 28]


# ══════════════════════════════════════════════════════════════
# Payment split + change
# ══════════════════════════════════════════════════════════════

class TestPayment:
    def test_exact_cash(self):
        r = _validate_payment({"cash": 826, "card": 0, "upi": 0}, 826.0)
        assert r["change"] == 0.0
        assert r["tendered"] == 826.0

    def test_cash_with_change(self):
        r = _validate_payment({"cash": 1000, "card": 0, "upi": 0}, 826.0)
        assert r["change"] == 174.0

    def test_split_tender(self):
        r = _validate_payment({"cash": 300, "card": 500, "upi": 26}, 826.0)
        assert r["tendered"] == 826.0
        assert r["change"] == 0.0

    def test_underpayment_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _validate_payment({"cash": 500, "card": 0, "upi": 0}, 826.0)
        assert exc.value.status_code == 400

    def test_card_overpayment_still_records_change(self):
        # tendered exceeds total; change is computed (store policy may refuse, but math holds)
        r = _validate_payment({"cash": 0, "card": 900, "upi": 0}, 826.0)
        assert r["change"] == 74.0

    def test_penny_tolerance(self):
        # 1 paisa short is allowed by the +0.01 tolerance
        r = _validate_payment({"cash": 825.99, "card": 0, "upi": 0}, 826.0)
        assert r["tendered"] == 825.99


# ══════════════════════════════════════════════════════════════
# Cash reconciliation math (the close logic computes variance the same way)
# ══════════════════════════════════════════════════════════════

class TestReconciliation:
    def test_expected_cash_formula(self):
        # expected = opening + cash_sales − change_given
        opening, cash_sales, change = 2000, 5000, 174
        expected = round(opening + cash_sales - change, 2)
        assert expected == 6826

    def test_variance_balanced(self):
        expected, counted = 6826, 6826
        assert round(counted - expected, 2) == 0.0

    def test_variance_short(self):
        expected, counted = 6826, 6800
        assert round(counted - expected, 2) == -26.0  # short

    def test_variance_over(self):
        expected, counted = 6826, 6850
        assert round(counted - expected, 2) == 24.0   # over
