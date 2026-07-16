"""Centralized design tokens for every PDF document in the ERP.

One file owns color, typography, spacing, borders, and page geometry so every
document type (invoices, orders, challans, vouchers, reports) shares one
visual language. Change a value here and it applies everywhere.

Font loading lives here too: Inter is the primary typeface (bundled in
core/fonts/, SIL OFL licensed), registered in four weights. DejaVu Sans is
kept as an automatic fallback if the Inter files are ever missing, so PDF
generation never hard-fails on a font problem.
"""
import os
from functools import lru_cache

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ─────────────────────────────────────────────────────────────────────────────
# Color palette
# ─────────────────────────────────────────────────────────────────────────────
BACKGROUND = colors.HexColor("#FFFFFF")
PRIMARY = colors.HexColor("#2563EB")
PRIMARY_SOFT = colors.HexColor("#EFF6FF")
ACCENT = colors.HexColor("#14B8A6")
SUCCESS = colors.HexColor("#10B981")
WARNING = colors.HexColor("#F59E0B")
DANGER = colors.HexColor("#EF4444")
TEXT = colors.HexColor("#111827")
TEXT_SECONDARY = colors.HexColor("#6B7280")
TEXT_MUTED = colors.HexColor("#9CA3AF")
BORDER = colors.HexColor("#E5E7EB")
BORDER_SOFT = colors.HexColor("#F3F4F6")
TABLE_HEADER_BG = colors.HexColor("#F8FAFC")
TABLE_ROW_ALT = colors.HexColor("#FAFBFC")
CARD_BG = colors.HexColor("#FFFFFF")

# Status badge colors: (text color, background color)
STATUS_COLORS = {
    "DRAFT":     (colors.HexColor("#6B7280"), colors.HexColor("#F3F4F6")),
    "PENDING":   (colors.HexColor("#B45309"), colors.HexColor("#FEF3C7")),
    "UNPAID":    (colors.HexColor("#B45309"), colors.HexColor("#FEF3C7")),
    "PARTIAL":   (colors.HexColor("#B45309"), colors.HexColor("#FEF3C7")),
    "PAID":      (colors.HexColor("#047857"), colors.HexColor("#D1FAE5")),
    "APPROVED":  (colors.HexColor("#047857"), colors.HexColor("#D1FAE5")),
    "COMPLETED": (colors.HexColor("#047857"), colors.HexColor("#D1FAE5")),
    "ACCEPTED":  (colors.HexColor("#047857"), colors.HexColor("#D1FAE5")),
    "SENT":      (colors.HexColor("#1D4ED8"), colors.HexColor("#DBEAFE")),
    "CANCELLED": (colors.HexColor("#B91C1C"), colors.HexColor("#FEE2E2")),
    "REJECTED":  (colors.HexColor("#B91C1C"), colors.HexColor("#FEE2E2")),
    "OVERDUE":   (colors.HexColor("#B91C1C"), colors.HexColor("#FEE2E2")),
}
DEFAULT_STATUS_COLOR = (colors.HexColor("#374151"), colors.HexColor("#F3F4F6"))

# ─────────────────────────────────────────────────────────────────────────────
# Page geometry
# ─────────────────────────────────────────────────────────────────────────────
PAGE_MARGIN_MM = 16
CONTENT_WIDTH_MM = 210 - (2 * PAGE_MARGIN_MM)  # A4 width minus margins

# ─────────────────────────────────────────────────────────────────────────────
# Typography scale (points)
# ─────────────────────────────────────────────────────────────────────────────
SIZE_COMPANY_NAME = 20   # spec asks 26px screen ≈ scaled down for print density
SIZE_DOC_TITLE = 16
SIZE_SECTION_HEADING = 9
SIZE_LABEL = 7.5
SIZE_BODY = 8.5
SIZE_TOTALS = 10.5
SIZE_GRAND_TOTAL = 13.5

RADIUS = 4  # ReportLab flowables don't support true border-radius; used by
            # rounded-rect card backgrounds drawn via canvas helpers.

# ─────────────────────────────────────────────────────────────────────────────
# Fonts — Inter primary, DejaVu Sans fallback
# ─────────────────────────────────────────────────────────────────────────────
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

FONT_REGULAR = "Helvetica"
FONT_MEDIUM = "Helvetica"
FONT_SEMIBOLD = "Helvetica-Bold"
FONT_BOLD = "Helvetica-Bold"
FONTS_SUPPORT_UNICODE = False


@lru_cache(maxsize=32)
def _font_has_rupee(font_path: str) -> bool:
    try:
        if not font_path or not os.path.exists(font_path):
            return False
        font_name = f"TempCheck_{os.path.basename(font_path)}"
        f = TTFont(font_name, font_path)
        return f.face.charToGlyph.get(0x20B9) is not None
    except Exception:
        return False


def _try_register_weight_set(reg, medium, semibold, bold, family_name) -> bool:
    """Register a 4-weight family under distinct PostScript names. Returns
    True only if all four files exist, load, and the regular+bold faces both
    contain the rupee glyph (so currency never renders as a missing-glyph box)."""
    paths = [reg, medium, semibold, bold]
    if not all(os.path.exists(p) for p in paths):
        return False
    if not (_font_has_rupee(reg) and _font_has_rupee(bold)):
        return False
    try:
        pdfmetrics.registerFont(TTFont(family_name, reg))
        pdfmetrics.registerFont(TTFont(f"{family_name}-Medium", medium))
        pdfmetrics.registerFont(TTFont(f"{family_name}-SemiBold", semibold))
        pdfmetrics.registerFont(TTFont(f"{family_name}-Bold", bold))
        return True
    except Exception:
        return False


def _try_register_pair(reg_path, bold_path, name) -> bool:
    if not (os.path.exists(reg_path) and os.path.exists(bold_path)):
        return False
    if not (_font_has_rupee(reg_path) and _font_has_rupee(bold_path)):
        return False
    try:
        pdfmetrics.registerFont(TTFont(name, reg_path))
        pdfmetrics.registerFont(TTFont(f"{name}-Bold", bold_path))
        return True
    except Exception:
        return False


def _host_font_dirs():
    if os.name == "nt":
        return [os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")]
    return ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation", "/usr/share/fonts/TTF"]


def init_fonts() -> bool:
    """Register the PDF font family. Preference order:
    1. Bundled Inter (Regular/Medium/SemiBold/Bold) — the design system's font.
    2. Bundled DejaVu Sans (regular+bold only; Medium/SemiBold alias to these).
    3. Any host system font with the rupee glyph in both weights.
    4. Bare Helvetica (guaranteed by PDF spec, but no rupee glyph — currency
       falls back to "Rs." via clean_unicode when this path is hit).

    Returns True if unicode (₹) is supported by the registered family.
    """
    global FONT_REGULAR, FONT_MEDIUM, FONT_SEMIBOLD, FONT_BOLD, FONTS_SUPPORT_UNICODE

    inter_reg = os.path.join(_FONT_DIR, "Inter-Regular.ttf")
    inter_med = os.path.join(_FONT_DIR, "Inter-Medium.ttf")
    inter_semi = os.path.join(_FONT_DIR, "Inter-SemiBold.ttf")
    inter_bold = os.path.join(_FONT_DIR, "Inter-Bold.ttf")
    if _try_register_weight_set(inter_reg, inter_med, inter_semi, inter_bold, "Inter"):
        FONT_REGULAR, FONT_MEDIUM, FONT_SEMIBOLD, FONT_BOLD = "Inter", "Inter-Medium", "Inter-SemiBold", "Inter-Bold"
        FONTS_SUPPORT_UNICODE = True
        return True

    dejavu_reg = os.path.join(_FONT_DIR, "DejaVuSans.ttf")
    dejavu_bold = os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")
    if _try_register_pair(dejavu_reg, dejavu_bold, "DejaVuSans"):
        FONT_REGULAR = FONT_MEDIUM = "DejaVuSans"
        FONT_SEMIBOLD = FONT_BOLD = "DejaVuSans-Bold"
        FONTS_SUPPORT_UNICODE = True
        return True

    host_candidates = [
        ("segoeui.ttf", "segoeuib.ttf", "SegoeUI"),
        ("arial.ttf", "arialbd.ttf", "Arial"),
        ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf", "LiberationSans"),
    ]
    for d in _host_font_dirs():
        if not os.path.exists(d):
            continue
        for reg_file, bold_file, name in host_candidates:
            reg_path, bold_path = os.path.join(d, reg_file), os.path.join(d, bold_file)
            if _try_register_pair(reg_path, bold_path, name):
                FONT_REGULAR = FONT_MEDIUM = name
                FONT_SEMIBOLD = FONT_BOLD = f"{name}-Bold"
                FONTS_SUPPORT_UNICODE = True
                return True

    FONT_REGULAR = FONT_MEDIUM = "Helvetica"
    FONT_SEMIBOLD = FONT_BOLD = "Helvetica-Bold"
    FONTS_SUPPORT_UNICODE = False
    return False


init_fonts()


def mm_(v: float) -> float:
    """Shorthand: millimetres to points."""
    return v * mm
