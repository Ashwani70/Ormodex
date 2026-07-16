"""Currency Master enhancements.

Pure unit tests — no live DB. Covers:
  - decimal_places must be a non-negative integer (Pydantic model guard)
  - PDF _money() resolves the right symbol per currency, with ASCII / ISO-code
    fallbacks so symbols never render as a .notdef box.
"""
import os
import sys

os.environ.setdefault("DB_NAME", "test_erp")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pydantic import ValidationError

from core.masters_models import Currency, CurrencyUpdate


# ══════════════════════════════════════════════════════════════
# decimal_places validation
# ══════════════════════════════════════════════════════════════

class TestDecimalPlaces:
    def test_zero_is_allowed(self):
        c = Currency(iso_code="JPY", symbol="¥", formal_name="Japanese Yen", decimal_places=0)
        assert c.decimal_places == 0

    def test_positive_allowed(self):
        c = Currency(iso_code="INR", symbol="₹", formal_name="Indian Rupee", decimal_places=2)
        assert c.decimal_places == 2

    def test_default_is_two(self):
        c = Currency(iso_code="USD", symbol="$", formal_name="US Dollar")
        assert c.decimal_places == 2

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            Currency(iso_code="USD", symbol="$", formal_name="US Dollar", decimal_places=-1)  # type: ignore

    def test_negative_rejected_on_update(self):
        with pytest.raises(ValidationError):
            CurrencyUpdate(decimal_places=-3)  # type: ignore

    def test_update_allows_none(self):
        # Partial update without touching decimals must stay valid.
        assert CurrencyUpdate(symbol="$").decimal_places is None


# ══════════════════════════════════════════════════════════════
# PDF money/symbol rendering
# ══════════════════════════════════════════════════════════════

class TestMoneySymbols:
    def test_usd_symbol(self):
        from core.pdf import _money
        assert _money(1000, "USD") == "$1,000.00"

    def test_ascii_safe_symbols(self):
        # A$, S$ etc. are ASCII so they're safe regardless of font support.
        from core.pdf import _money
        assert _money(50, "AUD").startswith("A$")
        assert _money(50, "SGD").startswith("S$")

    def test_unknown_currency_falls_back_to_iso_code(self):
        # Never return a bare number or an empty symbol for an unknown currency.
        from core.pdf import _money
        out = _money(99, "XYZ")
        assert out.startswith("XYZ ")
        assert "99" in out

    def test_inr_never_emits_notdef_without_unicode(self, monkeypatch):
        # When the font lacks ₹, _money must substitute "Rs." not the raw glyph.
        import core.pdf as pdfmod
        monkeypatch.setattr(pdfmod, "FONTS_SUPPORT_UNICODE", False)
        out = pdfmod._money(1234.5, "INR")
        assert "₹" not in out
        assert out.startswith("Rs.")
