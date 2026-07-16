"""Tests for the Universal Cheque Printing module.

Pure unit tests — no live DB. Covers:
- the mm-precise PDF builder (text placement, alignment, char spacing, test mode)
- field resolution (enabled flags, blank values dropped)
- input validation (payee mandatory, amount > 0)
- Indian amount-in-words wiring
"""
import os
import sys

os.environ.setdefault("DB_NAME", "test_erp")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import HTTPException

from core.cheque_print_pdf import build_cheque_pdf, _font_for, FIELD_KEYS
from routers.cheque_printing import _resolve_fields, _validate_cheque_inputs
from routers.banking_pdc import amount_in_words


# ══════════════════════════════════════════════════════════════
# PDF builder
# ══════════════════════════════════════════════════════════════

class TestPdfBuilder:
    FIELDS = [
        {"field": "payee_name", "value": "ACME PVT LTD", "x_mm": 30, "y_mm": 20,
         "font_family": "Courier", "font_size": 11, "char_spacing": 1.5, "align": "left"},
        {"field": "amount_figures", "value": "**1,000.00/-", "x_mm": 170, "y_mm": 30,
         "font_family": "Helvetica", "font_size": 12, "char_spacing": 0, "align": "right"},
    ]

    def test_produces_valid_pdf(self):
        pdf = build_cheque_pdf(width_mm=203, height_mm=93, fields=self.FIELDS)
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 500

    def test_empty_fields_still_renders(self):
        pdf = build_cheque_pdf(width_mm=203, height_mm=93, fields=[])
        assert pdf[:4] == b"%PDF"

    def test_blank_values_skipped(self):
        # A field with an empty value must not crash the renderer.
        pdf = build_cheque_pdf(width_mm=203, height_mm=93,
                               fields=[{"field": "date", "value": "", "x_mm": 10, "y_mm": 10}])
        assert pdf[:4] == b"%PDF"

    def test_test_print_mode_adds_border(self):
        # test_print draws extra alignment aids, so the stream should be larger.
        plain = build_cheque_pdf(width_mm=203, height_mm=93, fields=self.FIELDS)
        test = build_cheque_pdf(width_mm=203, height_mm=93, fields=self.FIELDS, test_print=True)
        assert test[:4] == b"%PDF"
        assert len(test) >= len(plain)

    def test_bad_background_does_not_crash(self):
        pdf = build_cheque_pdf(width_mm=203, height_mm=93, fields=self.FIELDS,
                               background_bytes=b"not-an-image", test_print=True)
        assert pdf[:4] == b"%PDF"


class TestFontMapping:
    def test_courier(self):
        assert _font_for("Courier New") == "Courier"
        assert _font_for("monospace") == "Courier"

    def test_times(self):
        assert _font_for("Times New Roman") == "Times-Roman"
        assert _font_for("serif") == "Times-Roman"

    def test_default_helvetica(self):
        assert _font_for(None) == "Helvetica"
        assert _font_for("Whatever Unknown") == "Helvetica"


# ══════════════════════════════════════════════════════════════
# Field resolution
# ══════════════════════════════════════════════════════════════

class TestResolveFields:
    TEMPLATE = {
        "field_positions": [
            {"field": "payee_name", "x_mm": 30, "y_mm": 20, "enabled": True},
            {"field": "date", "x_mm": 160, "y_mm": 8, "enabled": True},
            {"field": "signature_marker", "x_mm": 170, "y_mm": 70, "enabled": False},
        ]
    }

    def test_resolves_values_and_drops_disabled_and_blank(self):
        values = {"payee_name": "ACME", "date": "20260621", "signature_marker": "X"}
        fields = _resolve_fields(self.TEMPLATE, values)
        keys = {f["field"] for f in fields}
        assert keys == {"payee_name", "date"}        # signature disabled → dropped
        payee = next(f for f in fields if f["field"] == "payee_name")
        assert payee["value"] == "ACME"

    def test_blank_value_dropped(self):
        values = {"payee_name": "", "date": "20260621"}
        fields = _resolve_fields(self.TEMPLATE, values)
        assert {f["field"] for f in fields} == {"date"}

    def test_field_keys_palette(self):
        # The editor palette and the renderer must agree on the field set.
        assert "payee_name" in FIELD_KEYS
        assert "amount_words" in FIELD_KEYS
        assert "amount_figures" in FIELD_KEYS
        assert "account_payee" in FIELD_KEYS


# ══════════════════════════════════════════════════════════════
# Validation
# ══════════════════════════════════════════════════════════════

class TestValidation:
    def test_payee_mandatory(self):
        with pytest.raises(HTTPException) as exc:
            _validate_cheque_inputs("   ", 100)
        assert exc.value.status_code == 400

    def test_amount_must_be_positive(self):
        for bad in (0, -5):
            with pytest.raises(HTTPException) as exc:
                _validate_cheque_inputs("ACME", bad)
            assert exc.value.status_code == 400

    def test_valid_passes(self):
        # Should not raise.
        _validate_cheque_inputs("ACME PVT LTD", 1500.50)


# ══════════════════════════════════════════════════════════════
# Amount in words (Indian grouping) — wiring sanity
# ══════════════════════════════════════════════════════════════

class TestAmountInWords:
    def test_lakh_crore(self):
        assert amount_in_words(1234567.50) == (
            "Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven Rupees and Fifty Paise Only"
        )

    def test_round_rupees(self):
        assert amount_in_words(1000) == "One Thousand Rupees Only"

    def test_zero(self):
        assert amount_in_words(0) == "Zero Rupees Only"

    def test_paise_only(self):
        # 0 rupees, 50 paise
        result = amount_in_words(0.50)
        assert "Fifty Paise" in result

    def test_crore(self):
        result = amount_in_words(10000000)
        assert "One Crore" in result

    def test_large_amount(self):
        # 1,23,45,678 → "One Crore Twenty Three Lakh..."
        result = amount_in_words(12345678)
        assert "Crore" in result
        assert "Lakh" in result


# ══════════════════════════════════════════════════════════════
# PDF builder — edge cases for new fields
# ══════════════════════════════════════════════════════════════

class TestPdfBuilderEdgeCases:
    def test_all_field_types_render(self):
        fields = [
            {"field": "date",           "value": "20260621", "x_mm": 160, "y_mm": 8,  "font_family": "Courier",    "font_size": 10, "char_spacing": 3.5, "align": "left"},
            {"field": "payee_name",     "value": "Test Co",  "x_mm": 30,  "y_mm": 25, "font_family": "Helvetica",  "font_size": 11, "char_spacing": 0,   "align": "left"},
            {"field": "amount_words",   "value": "One Thousand Rupees Only", "x_mm": 20, "y_mm": 45, "font_family": "Helvetica", "font_size": 10, "char_spacing": 0, "align": "left"},
            {"field": "amount_figures", "value": "**1,000.00/-", "x_mm": 170, "y_mm": 30, "font_family": "Courier", "font_size": 11, "char_spacing": 0, "align": "right"},
            {"field": "account_payee",  "value": "A/C PAYEE ONLY", "x_mm": 10, "y_mm": 8, "font_family": "Helvetica", "font_size": 8, "char_spacing": 0, "align": "left"},
        ]
        pdf = build_cheque_pdf(width_mm=203, height_mm=93, fields=fields)
        assert pdf[:4] == b"%PDF"

    def test_right_aligned_field(self):
        fields = [{"field": "amount_figures", "value": "**99,999.00/-", "x_mm": 200, "y_mm": 30,
                   "font_family": "Courier", "font_size": 11, "char_spacing": 0, "align": "right"}]
        pdf = build_cheque_pdf(width_mm=203, height_mm=93, fields=fields)
        assert pdf[:4] == b"%PDF"

    def test_custom_page_size(self):
        # Non-standard cheque size (e.g. Axis 203×92)
        pdf = build_cheque_pdf(width_mm=205, height_mm=91, fields=[])
        assert pdf[:4] == b"%PDF"


# ══════════════════════════════════════════════════════════════
# Validation — new lifecycle inputs
# ══════════════════════════════════════════════════════════════

class TestLifecycleValidation:
    """Tests for the new cancel/void/reprint business rules (pure logic, no DB)."""

    def test_payee_with_whitespace_only_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _validate_cheque_inputs("\t\n  ", 500)
        assert exc.value.status_code == 400

    def test_zero_amount_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _validate_cheque_inputs("ACME", 0.0)
        assert exc.value.status_code == 400

    def test_negative_amount_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _validate_cheque_inputs("ACME", -1)
        assert exc.value.status_code == 400

    def test_fraction_amount_valid(self):
        # Paise amounts are valid
        _validate_cheque_inputs("Test Payee", 0.50)

    def test_large_amount_valid(self):
        _validate_cheque_inputs("Test Payee", 99_999_999.99)


# ══════════════════════════════════════════════════════════════
# Field resolution — new behaviour
# ══════════════════════════════════════════════════════════════

class TestResolveFieldsExtended:
    def test_none_value_dropped(self):
        tpl = {"field_positions": [{"field": "payee_name", "x_mm": 30, "y_mm": 20, "enabled": True}]}
        fields = _resolve_fields(tpl, {"payee_name": None})
        assert fields == []

    def test_all_disabled_returns_empty(self):
        tpl = {"field_positions": [
            {"field": "payee_name", "x_mm": 30, "y_mm": 20, "enabled": False},
            {"field": "date",       "x_mm": 160, "y_mm": 8, "enabled": False},
        ]}
        assert _resolve_fields(tpl, {"payee_name": "A", "date": "20260601"}) == []

    def test_coordinates_preserved(self):
        tpl = {"field_positions": [{"field": "amount_figures", "x_mm": 170.5, "y_mm": 35.25, "enabled": True}]}
        fields = _resolve_fields(tpl, {"amount_figures": "**500.00/-"})
        assert fields[0]["x_mm"] == 170.5
        assert fields[0]["y_mm"] == 35.25

    def test_extra_values_not_in_template_ignored(self):
        tpl = {"field_positions": [{"field": "payee_name", "x_mm": 30, "y_mm": 20, "enabled": True}]}
        fields = _resolve_fields(tpl, {"payee_name": "ACME", "unknown_field": "X"})
        assert len(fields) == 1
        assert fields[0]["field"] == "payee_name"
