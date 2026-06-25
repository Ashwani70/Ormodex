"""Cheque PDF builder.

Renders a cheque to a print-ready PDF sized to a standard Indian CTS-2010 leaf
(≈ 8" × 3.66"), positioning each field from the format's authoring coordinates.

The cheque formats author field positions against a 500 × 200 canvas (the same
space the frontend preview uses); we scale those into the physical page so the
on-screen preview, browser print, and this PDF all line up.
"""
import io

from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

# Physical cheque leaf.
PAGE_W = 8.0 * inch
PAGE_H = 3.66 * inch

# Authoring coordinate space the format fields are defined in (top-left origin).
CANVAS_W = 500.0
CANVAS_H = 200.0


def _font_for(name: str) -> str:
    """Map a format's font hint to a reportlab core font (always available)."""
    n = (name or "").lower()
    if "courier" in n or "mono" in n:
        return "Courier"
    if "times" in n or "serif" in n:
        return "Times-Roman"
    return "Helvetica"


def build_cheque_pdf(rendered: dict) -> bytes:
    """Build the cheque PDF from a rendered cheque dict (see _render_cheque)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"Cheque — {rendered.get('format', '')}")

    sx = PAGE_W / CANVAS_W
    sy = PAGE_H / CANVAS_H

    for fld in rendered.get("fields", []):
        value = str(fld.get("value", "") or "")
        if not value:
            continue
        # Authoring coords are top-left origin; reportlab's are bottom-left.
        x = float(fld.get("x", 0) or 0) * sx
        y_top = float(fld.get("y", 0) or 0) * sy
        # font_size authored in px against the 200-tall canvas → scale to points.
        size = max(6.0, float(fld.get("font_size", 12) or 12) * sy)
        baseline = PAGE_H - y_top - size  # drop below the field's top edge
        c.setFont(_font_for(fld.get("font")), size)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(x, baseline, value)

    micr = rendered.get("micr_line")
    if micr:
        c.setFont("Courier", 11)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(0.6 * inch, 0.18 * inch, str(micr))

    c.showPage()
    c.save()
    return buf.getvalue()
