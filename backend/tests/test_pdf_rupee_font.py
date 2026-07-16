"""Tests for rupee-glyph-aware font initialisation in core.pdf.

Root cause being guarded against: the old init only checked that a font file
existed and registered with reportlab, never that it contained ₹ (U+20B9).
A font without that glyph makes reportlab draw its .notdef box (a black square),
which is what users saw instead of ₹.

These tests pin the contract:
  * _font_has_rupee() inspects the cmap and rejects symbol fonts.
  * init_fonts() prefers a rupee-capable font (pass 1) and otherwise falls back
    to any usable font (pass 2) while reporting FONTS_SUPPORT_UNICODE correctly.
  * Generated PDFs carry ₹ when supported and "Rs." when not.

They avoid third-party font-synthesis libraries (fontTools is not installed) by
using real system fonts where available and monkeypatching the candidate list
for the fallback / missing-directory cases.
"""
import os

import pytest

from core import pdf as pdfmod


# --- helpers ---------------------------------------------------------------

def _system_font(*names):
    """Return the first existing path among common system font locations."""
    dirs = []
    if os.name == "nt":
        dirs.append(os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"))
    else:
        dirs += [
            "/usr/share/fonts/truetype/dejavu",
            "/usr/share/fonts/truetype/liberation",
            "/usr/share/fonts/TTF",
        ]
    for d in dirs:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    return None


RUPEE_FONT = _system_font("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf",
                          "LiberationSans-Regular.ttf")
SYMBOL_FONT = _system_font("wingding.ttf", "symbol.ttf")


@pytest.fixture(autouse=True)
def _restore_font_globals():
    """init_fonts() mutates module globals directly; restore them per test so
    monkeypatched candidate lists don't leak font selections across tests."""
    saved = (pdfmod.FONT_REGULAR, pdfmod.FONT_BOLD, pdfmod.FONTS_SUPPORT_UNICODE)
    yield
    pdfmod.FONT_REGULAR, pdfmod.FONT_BOLD, pdfmod.FONTS_SUPPORT_UNICODE = saved


# --- _font_has_rupee -------------------------------------------------------

@pytest.mark.skipif(RUPEE_FONT is None, reason="no rupee-capable system font available")
def test_font_with_rupee_glyph_detected():
    assert pdfmod._font_has_rupee(RUPEE_FONT) is True


@pytest.mark.skipif(SYMBOL_FONT is None, reason="no symbol font available on this OS")
def test_symbol_font_rejected():
    # Wingdings / Symbol have no U+20B9 entry in their cmap.
    assert pdfmod._font_has_rupee(SYMBOL_FONT) is False


def test_missing_font_path_returns_false():
    assert pdfmod._font_has_rupee("/no/such/font/file.ttf") is False


def test_detection_is_cached():
    pdfmod._font_has_rupee.cache_clear()
    if RUPEE_FONT:
        pdfmod._font_has_rupee(RUPEE_FONT)
        pdfmod._font_has_rupee(RUPEE_FONT)
        info = pdfmod._font_has_rupee.cache_info()
        assert info.hits >= 1


# --- init_fonts two-pass behaviour ----------------------------------------

@pytest.mark.skipif(RUPEE_FONT is None, reason="no rupee-capable system font available")
def test_pass1_picks_rupee_font(monkeypatch):
    bold = RUPEE_FONT  # reuse same file as "bold" for the test
    monkeypatch.setattr(pdfmod, "_candidate_fonts",
                        lambda: [(RUPEE_FONT, bold, "ProbeRupee")])
    assert pdfmod.init_fonts() is True
    assert pdfmod.FONT_REGULAR == "ProbeRupee"


def test_pass2_fallback_when_no_rupee(monkeypatch):
    # A registrable font, but force the detector to say it lacks ₹.
    fallback = RUPEE_FONT or SYMBOL_FONT
    if fallback is None:
        pytest.skip("no registrable system font available")
    monkeypatch.setattr(pdfmod, "_candidate_fonts",
                        lambda: [(fallback, fallback, "ProbeNoRupee")])
    monkeypatch.setattr(pdfmod, "_font_has_rupee", lambda *a, **k: False)
    assert pdfmod.init_fonts() is False
    assert pdfmod.FONT_REGULAR == "ProbeNoRupee"


def test_missing_font_directory_graceful_fallback(monkeypatch):
    # No candidate fonts at all -> must not raise, returns False, keeps Helvetica.
    monkeypatch.setattr(pdfmod, "_candidate_fonts", lambda: [])
    monkeypatch.setattr(pdfmod, "FONT_REGULAR", "Helvetica")
    monkeypatch.setattr(pdfmod, "FONT_BOLD", "Helvetica-Bold")
    assert pdfmod.init_fonts() is False
    assert pdfmod.FONT_REGULAR == "Helvetica"


# --- end-to-end PDF content ------------------------------------------------

def _sample_doc():
    return {
        "customer_name": "Neha",
        "currency": "INR",
        "created_at": "2026-06-17T00:00:00",
        "subtotal": 510.0,
        "gst_amount": 91.8,
        "total": 601.8,
        "igst": 91.8,
        "items": [{
            "product_name": "U-Head Jack 600mm", "sku": "UHJ-600",
            "quantity": 1, "unit_price": 510.0, "gst_rate": 18.0,
        }],
    }


def _pdf_text(data: bytes):
    """Extract text via pypdf if installed, else return None (skip-signal).

    Raw byte scanning is unreliable because reportlab stores text as font glyph
    codes inside compressed streams, so callers must skip when this returns None.
    """
    try:
        from pypdf import PdfReader  # type: ignore
        import io
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    except ImportError:
        return None


def test_pdf_builds_and_is_nonempty():
    data = pdfmod.build_doc_pdf("SALES ORDER", "SO-26-00033", _sample_doc())
    assert data[:4] == b"%PDF"
    assert len(data) > 1000


def test_amount_in_words_renders_rupees_ascii():
    # The amount-in-words string is what keeps INR readable when ₹ is
    # unavailable; it is pure ASCII ("Rupees"/"Paise") so it survives both modes.
    from core.words import amount_in_words
    words = amount_in_words(601.8, "INR")
    assert "Rupees" in words
    assert "₹" not in words


def test_pdf_text_contains_rupee_when_supported(monkeypatch):
    text = _pdf_text(pdfmod.build_doc_pdf("SALES ORDER", "SO", _sample_doc()))
    if text is None:
        pytest.skip("pypdf not installed; cannot inspect PDF text layer")
    if not pdfmod.FONTS_SUPPORT_UNICODE:
        pytest.skip("active font lacks ₹; covered by the Rs. case instead")
    assert "₹" in text


def test_pdf_text_contains_rs_when_unsupported(monkeypatch):
    # clean_unicode() runs inside build_doc_pdf and swaps ₹ -> "Rs." based on
    # the module flag, so forcing it False must yield "Rs." in the output.
    monkeypatch.setattr(pdfmod, "FONTS_SUPPORT_UNICODE", False)
    text = _pdf_text(pdfmod.build_doc_pdf("SALES ORDER", "SO", _sample_doc()))
    if text is None:
        pytest.skip("pypdf not installed; cannot inspect PDF text layer")
    assert "Rs" in text
    assert "₹" not in text


def test_clean_unicode_substitutes_rs_when_unsupported(monkeypatch):
    monkeypatch.setattr(pdfmod, "FONTS_SUPPORT_UNICODE", False)
    out = pdfmod.clean_unicode({"a": "₹510.00", "b": ["₹1", {"c": "₹2"}]})
    assert "₹" not in str(out)
    assert "Rs." in out["a"]


def test_clean_unicode_passthrough_when_supported(monkeypatch):
    monkeypatch.setattr(pdfmod, "FONTS_SUPPORT_UNICODE", True)
    assert pdfmod.clean_unicode("₹510.00") == "₹510.00"


# --- bundled font + plain-string cell regressions --------------------------

def test_bundled_dejavu_font_is_shipped_and_has_rupee():
    """The repo ships a Unicode font so rendering never depends on host fonts
    (the prod box rendered ₹ as a black square because its host font lacked the
    glyph). Both weights must contain U+20B9."""
    for fn in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"):
        path = os.path.join(pdfmod._BUNDLED_FONT_DIR, fn)
        assert os.path.exists(path), f"bundled font missing: {path}"
        assert pdfmod._font_has_rupee(path) is True


def test_init_prefers_bundled_font():
    """Default init (no monkeypatch) must select the bundled DejaVu font and
    report Unicode support, so ₹ is always available."""
    pdfmod.init_fonts()
    assert pdfmod.FONT_REGULAR == "DejaVuSans"
    assert pdfmod.FONTS_SUPPORT_UNICODE is True


def test_pass1_requires_rupee_in_both_weights(monkeypatch):
    """Checking only the regular face let through fonts whose bold face lacked ₹
    (or vice-versa), leaving half the currency cells as black boxes. Pass 1 must
    fall through to pass 2 when either weight is missing the glyph."""
    fallback = RUPEE_FONT or SYMBOL_FONT
    if fallback is None:
        pytest.skip("no registrable system font available")
    reg_path, bold_path = fallback, fallback + "#bold"
    monkeypatch.setattr(pdfmod, "_candidate_fonts",
                        lambda: [(reg_path, bold_path, "ProbeHalf")])
    # Regular has ₹, bold does not -> pass 1 must reject, pass 2 registers it as
    # non-Unicode (so _money() uses "Rs." instead of a black box).
    monkeypatch.setattr(pdfmod, "_font_has_rupee",
                        lambda path: path == reg_path)
    assert pdfmod.init_fonts() is False
    assert pdfmod.FONTS_SUPPORT_UNICODE is False


def test_line_item_table_uses_unicode_font_for_plain_cells():
    """Plain-string rate/amount cells default to Helvetica (no ₹ glyph). The
    table style must force FONT_REGULAR so they don't render as black boxes."""
    pdfmod.init_fonts()
    data = pdfmod.build_doc_pdf("TAX INVOICE", "INV-1", _sample_doc())
    # The bundled font name must be embedded for the document to render ₹ in the
    # plain-string columns.
    assert b"DejaVu" in data


# --- company branding (name + logo) on PDFs --------------------------------

def test_pdf_uses_company_name_when_provided():
    """The invoice header (and footer) must show the configured company name,
    not the hardcoded 'GRAVITYONE ERP' default."""
    company = {"name": "ACME SCAFFOLDING PVT LTD", "address": "Pune", "gstin": "27AABCA1234F1Z5"}
    data = pdfmod.build_doc_pdf("TAX INVOICE", "INV-1", _sample_doc(), company=company)
    text = _pdf_text(data)
    if text is None:
        pytest.skip("pypdf not installed; cannot inspect PDF text layer")
    assert "ACME SCAFFOLDING PVT LTD" in text


def test_pdf_falls_back_to_default_company_name():
    data = pdfmod.build_doc_pdf("TAX INVOICE", "INV-1", _sample_doc())
    text = _pdf_text(data)
    if text is None:
        pytest.skip("pypdf not installed; cannot inspect PDF text layer")
    assert "GRAVITYONE ERP" in text


def test_logo_embedded_in_pdf(monkeypatch):
    """A configured logo (resolved via core.storage) must be embedded as an
    image in the PDF; a real PNG signature ends up in the output stream."""
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc````\x00\x00"
        b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    monkeypatch.setattr(pdfmod, "_load_logo_image", pdfmod._load_logo_image)
    # Stub get_object so the loader resolves our PNG without touching storage.
    import core.storage as storage
    monkeypatch.setattr(storage, "get_object", lambda path: (png, "image/png"))
    company = {"name": "ACME", "logo_url": "gew-erp/products/u1/logo.png"}
    data = pdfmod.build_doc_pdf("TAX INVOICE", "INV-1", _sample_doc(), company=company)
    assert data[:4] == b"%PDF"
    # reportlab re-encodes images, so assert the build succeeded and an image
    # XObject is present rather than scanning for raw PNG bytes.
    assert b"/Image" in data or b"/XObject" in data


def test_bad_logo_url_does_not_break_pdf(monkeypatch):
    """A missing/broken logo must never crash PDF generation."""
    import core.storage as storage
    def boom(path):
        raise FileNotFoundError(path)
    monkeypatch.setattr(storage, "get_object", boom)
    company = {"name": "ACME", "logo_url": "gew-erp/missing.png"}
    data = pdfmod.build_doc_pdf("TAX INVOICE", "INV-1", _sample_doc(), company=company)
    assert data[:4] == b"%PDF"
    assert len(data) > 1000
