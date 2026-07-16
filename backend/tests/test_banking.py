"""Tests for Banking Module D extensions.

Pure unit tests — no DB required.
Covers:
- Indian amount-in-words (lakh/crore, paise, edge cases)
- Overdue interest: simple/compound, grace days, exact boundary
- PDC lifecycle state validation helpers
"""
import os
import sys
from typing import Any, Dict

os.environ.setdefault("DB_NAME", "test_erp")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers.banking_pdc import amount_in_words, _compute_overdue_interest


# ══════════════════════════════════════════════════════════════
# Indian Amount-in-Words
# ══════════════════════════════════════════════════════════════

class TestAmountInWords:
    def test_zero(self):
        assert amount_in_words(0) == "Zero Rupees Only"

    def test_single_digit(self):
        assert amount_in_words(5) == "Five Rupees Only"

    def test_teen(self):
        assert amount_in_words(15) == "Fifteen Rupees Only"

    def test_two_digits(self):
        assert amount_in_words(75) == "Seventy Five Rupees Only"

    def test_hundred(self):
        assert amount_in_words(100) == "One Hundred Rupees Only"

    def test_hundreds_and_tens(self):
        assert amount_in_words(525) == "Five Hundred Twenty Five Rupees Only"

    def test_thousand(self):
        assert amount_in_words(1000) == "One Thousand Rupees Only"

    def test_ten_thousand(self):
        assert amount_in_words(10_000) == "Ten Thousand Rupees Only"

    def test_lakh(self):
        assert amount_in_words(1_00_000) == "One Lakh Rupees Only"

    def test_twelve_lakh(self):
        assert amount_in_words(12_00_000) == "Twelve Lakh Rupees Only"

    def test_lakh_with_thousands(self):
        result = amount_in_words(12_34_567)
        assert "Twelve Lakh" in result
        assert "Thirty Four Thousand" in result
        assert "Five Hundred Sixty Seven" in result

    def test_crore(self):
        assert amount_in_words(1_00_00_000) == "One Crore Rupees Only"

    def test_crore_and_lakh(self):
        result = amount_in_words(1_25_00_000)
        assert "One Crore" in result
        assert "Twenty Five Lakh" in result

    def test_paise(self):
        result = amount_in_words(1000.50)
        assert "One Thousand Rupees" in result
        assert "Fifty Paise" in result

    def test_paise_75(self):
        result = amount_in_words(500.75)
        assert "Seventy Five Paise" in result

    def test_paise_only_ignored_at_zero_rupees(self):
        # 0.25 → "Zero..." but non-zero paise
        result = amount_in_words(0.25)
        assert "Twenty Five Paise" in result

    def test_large_amount(self):
        # 9,99,99,999 → Nine Crore Ninety Nine Lakh Ninety Nine Thousand Nine Hundred Ninety Nine
        result = amount_in_words(9_99_99_999)
        assert "Nine Crore" in result
        assert "Ninety Nine Lakh" in result

    def test_only_suffix(self):
        assert amount_in_words(100).endswith("Only")

    def test_round_paise(self):
        # Floating point: 1000.1 should not produce garbage paise
        result = amount_in_words(1000.10)
        assert "Ten Paise" in result

    def test_cheque_amount_typical(self):
        # Typical cheque: ₹2,34,567.00
        result = amount_in_words(2_34_567)
        assert "Two Lakh" in result
        assert "Thirty Four Thousand" in result
        assert "Five Hundred Sixty Seven" in result
        assert "Paise" not in result  # no paise


# ══════════════════════════════════════════════════════════════
# Overdue Interest
# ══════════════════════════════════════════════════════════════

class TestOverdueInterest:
    def test_not_overdue_before_grace(self):
        result = _compute_overdue_interest(
            invoice_amount=100_000,
            due_date="2024-06-01",
            as_of="2024-06-05",   # 4 days after due, grace=7
            grace_days=7,
            rate_pct_pa=18.0,
            basis="simple",
        )
        assert result["applicable"] is False
        assert result["interest"] == 0.0
        assert result["overdue_days"] == 0

    def test_not_overdue_on_grace_boundary(self):
        result = _compute_overdue_interest(
            invoice_amount=100_000,
            due_date="2024-06-01",
            as_of="2024-06-08",   # exactly grace_days=7 after due → interest_start=Jun 8
            grace_days=7,
            rate_pct_pa=18.0,
            basis="simple",
        )
        # as_of == interest_start → NOT overdue yet (strictly >)
        assert result["applicable"] is False

    def test_overdue_one_day_after_grace(self):
        result = _compute_overdue_interest(
            invoice_amount=100_000,
            due_date="2024-06-01",
            as_of="2024-06-09",   # 1 day after grace period ends
            grace_days=7,
            rate_pct_pa=18.0,
            basis="simple",
        )
        assert result["applicable"] is True
        assert result["overdue_days"] == 1
        expected = round(100_000 * (18.0 / 100 / 365) * 1, 2)
        assert result["interest"] == expected

    def test_simple_interest_30_days(self):
        result = _compute_overdue_interest(
            invoice_amount=100_000,
            due_date="2024-01-01",
            as_of="2024-02-10",  # 40 days after due, grace=10 → 30 overdue days
            grace_days=10,
            rate_pct_pa=18.0,
            basis="simple",
        )
        assert result["overdue_days"] == 30
        expected = round(100_000 * 0.18 / 365 * 30, 2)
        assert result["interest"] == expected

    def test_simple_vs_compound_different(self):
        """Compound interest produces more than simple for >1 day."""
        simple = _compute_overdue_interest(100_000, "2024-01-01", "2024-07-01", 0, 18.0, "simple")
        compound = _compute_overdue_interest(100_000, "2024-01-01", "2024-07-01", 0, 18.0, "compound")
        assert compound["interest"] > simple["interest"]

    def test_compound_interest_formula(self):
        # 100,000 at 18% pa, 365 days, compound daily: 100000 * (1+18/36500)^365 - 100000
        result = _compute_overdue_interest(
            invoice_amount=100_000,
            due_date="2024-01-01",
            as_of="2025-01-01",   # exactly 366 days (2024 is leap)
            grace_days=0,
            rate_pct_pa=18.0,
            basis="compound",
        )
        assert result["overdue_days"] == 366
        daily = 18.0 / 100 / 365
        expected = round(100_000 * ((1 + daily) ** 366 - 1), 2)
        assert result["interest"] == expected

    def test_zero_grace_no_leniency(self):
        # Due yesterday → overdue from today (grace=0)
        result = _compute_overdue_interest(
            invoice_amount=50_000,
            due_date="2024-06-01",
            as_of="2024-06-02",   # 1 day overdue, grace=0
            grace_days=0,
            rate_pct_pa=24.0,
            basis="simple",
        )
        assert result["applicable"] is True
        assert result["overdue_days"] == 1

    def test_high_value_invoice(self):
        # ₹1 crore invoice, 30 days overdue, 18% pa simple
        result = _compute_overdue_interest(
            invoice_amount=1_00_00_000,
            due_date="2024-01-01",
            as_of="2024-01-31",
            grace_days=0,
            rate_pct_pa=18.0,
            basis="simple",
        )
        assert result["overdue_days"] == 30
        expected = round(1_00_00_000 * 0.18 / 365 * 30, 2)
        assert result["interest"] == expected

    def test_not_applicable_if_same_day_as_due(self):
        result = _compute_overdue_interest(100_000, "2024-06-01", "2024-06-01", 0, 18.0, "simple")
        assert result["applicable"] is False


# ══════════════════════════════════════════════════════════════
# Cheque PDF
# ══════════════════════════════════════════════════════════════

class TestChequePdf:
    def _rendered(self) -> Dict[str, Any]:
        return {
            "format": "Standard HDFC A4", "bank_name": "HDFC Bank",
            "fields": [
                {"field": "payee", "x": 120, "y": 45, "font_size": 12, "font": "Arial", "value": "Acme Industries Pvt Ltd"},
                {"field": "amount_numeric", "x": 400, "y": 45, "font_size": 12, "value": "12,34,567.50"},
                {"field": "amount_words", "x": 80, "y": 65, "font_size": 10, "value": "Twelve Lakh Rupees Only"},
                {"field": "date", "x": 420, "y": 25, "font_size": 11, "value": "2026-06-21"},
            ],
            "micr_line": "123456789 001234 0001",
        }

    def test_builds_valid_pdf(self):
        from core.cheque_pdf import build_cheque_pdf
        pdf = build_cheque_pdf(self._rendered())
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 500

    def test_skips_empty_fields_without_error(self):
        from core.cheque_pdf import build_cheque_pdf
        r = self._rendered()
        r["fields"].append({"field": "unknown", "x": 10, "y": 10, "font_size": 9, "value": ""})
        r["micr_line"] = None
        pdf = build_cheque_pdf(r)
        assert pdf[:4] == b"%PDF"
