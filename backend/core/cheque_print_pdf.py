"""Universal cheque PDF builder (millimetre-precise).

Renders a cheque onto a page sized to the template's physical dimensions
(``cheque_width_mm`` × ``cheque_height_mm``), placing each field at the exact
millimetre coordinate the template author configured. Because the page is the
real cheque size and coordinates are in mm, the output drops straight onto a
pre-printed CTS cheque leaf with no scaling guesswork — works for any Indian
bank once its template is configured.

Coordinate convention (matches the on-screen authoring grid):
  - origin is the TOP-LEFT of the leaf, x → right, y → down, both in mm.
  - ReportLab's native origin is bottom-left, so we flip y here.

Test-print mode overlays the uploaded background image and a light border so the
operator can verify alignment before committing a real leaf.
"""
import io
from typing import Optional

from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# Field keys the template may position. Mirrors the frontend authoring palette.
FIELD_KEYS = (
    "date",
    "payee_name",
    "amount_words",
    "amount_figures",
    "account_payee",
    "signature_marker",
)

# Map a template font hint to a ReportLab core font (always embedded, no files).
_FONT_MAP = {
    "courier": "Courier",
    "mono": "Courier",
    "times": "Times-Roman",
    "serif": "Times-Roman",
    "helvetica": "Helvetica",
    "arial": "Helvetica",
    "sans": "Helvetica",
}


def _font_for(name: Optional[str]) -> str:
    n = (name or "").lower()
    for hint, font in _FONT_MAP.items():
        if hint in n:
            return font
    return "Helvetica"


def _draw_spaced(c: canvas.Canvas, x: float, y: float, text: str,
                 char_spacing: float, align: str, font: str, size: float) -> None:
    """Draw text honouring character spacing and alignment.

    char_spacing is in points (extra space added between glyphs). Alignment is
    computed against the anchor x using the spaced width so right/centre land
    where the author expects.
    """
    if char_spacing and char_spacing != 0:
        # Width including the inter-character padding.
        widths = [c.stringWidth(ch, font, size) for ch in text]
        total = sum(widths) + char_spacing * max(0, len(text) - 1)
    else:
        total = c.stringWidth(text, font, size)

    if align == "right":
        start_x = x - total
    elif align == "center":
        start_x = x - total / 2.0
    else:
        start_x = x

    if not char_spacing:
        c.drawString(start_x, y, text)
        return

    cursor = start_x
    for ch in text:
        c.drawString(cursor, y, ch)
        cursor += c.stringWidth(ch, font, size) + char_spacing


def build_cheque_pdf(
    *,
    width_mm: float,
    height_mm: float,
    fields: list[dict],
    background_bytes: Optional[bytes] = None,
    test_print: bool = False,
) -> bytes:
    """Render a cheque to PDF bytes.

    fields: list of resolved field dicts, each with:
        field, value, x_mm, y_mm, font_family, font_size, char_spacing, align
    background_bytes: raw image to overlay (test-print/preview only).
    test_print: when True, draws the background + a border + crop ticks so the
        operator can dry-run alignment on plain paper before using a real leaf.
    """
    page = (width_mm * mm, height_mm * mm)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page)
    c.setTitle("Cheque")

    page_h_pt = height_mm * mm

    # Test print: lay down the alignment aids first so text sits on top.
    if test_print:
        if background_bytes:
            try:
                c.drawImage(
                    ImageReader(io.BytesIO(background_bytes)),
                    0, 0, width=width_mm * mm, height=height_mm * mm,
                    preserveAspectRatio=False, mask="auto",
                )
            except Exception:
                # A bad/unsupported image must never abort the print.
                pass
        c.setStrokeColorRGB(0.7, 0.7, 0.7)
        c.setLineWidth(0.5)
        c.rect(0, 0, width_mm * mm, height_mm * mm)

    for fld in fields:
        value = str(fld.get("value", "") or "")
        if not value:
            continue
        font = _font_for(fld.get("font_family"))
        size = max(5.0, float(fld.get("font_size", 11) or 11))
        x = float(fld.get("x_mm", 0) or 0) * mm
        # y is the field's top edge from the top of the leaf; flip to bottom-left
        # and drop one font height so text sits below that edge.
        y = page_h_pt - (float(fld.get("y_mm", 0) or 0) * mm) - size
        spacing = float(fld.get("char_spacing", 0) or 0)
        align = (fld.get("align") or "left").lower()

        c.setFont(font, size)
        c.setFillColorRGB(0, 0, 0)
        _draw_spaced(c, x, y, value, spacing, align, font, size)

    c.showPage()
    c.save()
    return buf.getvalue()
