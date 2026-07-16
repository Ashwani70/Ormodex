"""Enterprise Letterhead PDF Engine.

Renders a multi-page document with a professional letterhead header and footer
onto every page, using ReportLab. All coordinates use millimetres (origin
top-left, y↓), converted internally to ReportLab's pt bottom-left system.

Key capabilities:
- A4 portrait / A4 landscape / Letter page sizes
- Configurable header height, footer height, margins
- Logo image (left/center/right), optional secondary logo
- Arbitrary text elements with full font/color/alignment control
- Diagonal watermark with configurable opacity
- Background image (full page)
- Header and footer divider lines with theme colours
- Auto page numbering
- Digital-signature placeholder area
- Thin-line professional table rendering for document bodies
"""
from __future__ import annotations

import io
import os
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ── Page size map ──────────────────────────────────────────────────────────────
_PAGE_SIZES: dict[str, tuple[float, float]] = {
    "A4":           A4,
    "A4_portrait":  A4,
    "A4_landscape": landscape(A4),
    "letter":       LETTER,
    "Letter":       LETTER,
}

# ── Built-in theme colour presets ─────────────────────────────────────────────
THEME_PRESETS: dict[str, dict[str, str]] = {
    "corporate_blue": {
        "primary_color": "#1a56db",
        "secondary_color": "#e8f0fe",
        "accent_color": "#f59e0b",
        "text_color": "#111827",
        "header_bg_color": "#1a56db",
        "footer_bg_color": "#f0f4ff",
        "header_text_color": "#ffffff",
        "footer_text_color": "#374151",
    },
    "modern_dark": {
        "primary_color": "#18181b",
        "secondary_color": "#27272a",
        "accent_color": "#facc15",
        "text_color": "#ffffff",
        "header_bg_color": "#18181b",
        "footer_bg_color": "#27272a",
        "header_text_color": "#ffffff",
        "footer_text_color": "#d4d4d8",
    },
    "luxury_gold": {
        "primary_color": "#78350f",
        "secondary_color": "#fef3c7",
        "accent_color": "#d97706",
        "text_color": "#1c1917",
        "header_bg_color": "#451a03",
        "footer_bg_color": "#fef3c7",
        "header_text_color": "#fef3c7",
        "footer_text_color": "#78350f",
    },
    "industrial_steel": {
        "primary_color": "#374151",
        "secondary_color": "#f3f4f6",
        "accent_color": "#ef4444",
        "text_color": "#111827",
        "header_bg_color": "#374151",
        "footer_bg_color": "#e5e7eb",
        "header_text_color": "#ffffff",
        "footer_text_color": "#374151",
    },
    "minimal_white": {
        "primary_color": "#ffffff",
        "secondary_color": "#f9fafb",
        "accent_color": "#6366f1",
        "text_color": "#111827",
        "header_bg_color": "#ffffff",
        "footer_bg_color": "#f9fafb",
        "header_text_color": "#111827",
        "footer_text_color": "#6b7280",
    },
    "executive_grey": {
        "primary_color": "#4b5563",
        "secondary_color": "#f3f4f6",
        "accent_color": "#0ea5e9",
        "text_color": "#111827",
        "header_bg_color": "#4b5563",
        "footer_bg_color": "#e5e7eb",
        "header_text_color": "#ffffff",
        "footer_text_color": "#374151",
    },
}


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    """Convert '#rrggbb' or 'rrggbb' to (r, g, b) floats in 0-1 range."""
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r / 255.0, g / 255.0, b / 255.0


def _color(h: Optional[str]) -> tuple[float, float, float]:
    """Safe colour parser — returns black on any error."""
    if not h:
        return 0.0, 0.0, 0.0
    try:
        return _hex_to_rgb(h)
    except Exception:
        return 0.0, 0.0, 0.0


def _align_const(align: str) -> int:
    return {
        "center": TA_CENTER,
        "right": TA_RIGHT,
    }.get((align or "left").lower(), TA_LEFT)


def _rl_align(align: str) -> str:
    return {"center": "centre", "right": "right"}.get((align or "left").lower(), "left")


# ── Low-level drawing helpers ──────────────────────────────────────────────────

def _draw_rect(c: canvas.Canvas, x_mm: float, y_mm: float, w_mm: float, h_mm: float,
               fill_color: Optional[str] = None, stroke_color: Optional[str] = None,
               line_width: float = 0) -> None:
    """Draw a filled/stroked rectangle. y_mm is from TOP of page."""
    page_h = c._pagesize[1]  # type: ignore[attr-defined]
    x = x_mm * mm
    y = page_h - (y_mm + h_mm) * mm
    w = w_mm * mm
    h = h_mm * mm
    if fill_color:
        c.setFillColorRGB(*_color(fill_color))
    if stroke_color and line_width > 0:
        c.setStrokeColorRGB(*_color(stroke_color))
        c.setLineWidth(line_width)
    c.rect(x, y, w, h,
           fill=1 if fill_color else 0,
           stroke=1 if (stroke_color and line_width > 0) else 0)


def _draw_line(c: canvas.Canvas, x1: float, y1: float, x2: float, y2: float,
               color: str, width: float = 0.5) -> None:
    """Draw a horizontal/diagonal line (coordinates in mm from top-left)."""
    page_h = c._pagesize[1]  # type: ignore[attr-defined]
    c.setStrokeColorRGB(*_color(color))
    c.setLineWidth(width)
    c.line(x1 * mm, page_h - y1 * mm, x2 * mm, page_h - y2 * mm)


def _draw_text(c: canvas.Canvas, text: str, x_mm: float, y_mm: float,
               font: str = "Helvetica", size: float = 10,
               color: str = "#111827", align: str = "left",
               max_width_mm: Optional[float] = None) -> None:
    """Draw a single text string at mm coordinates (y from top)."""
    if not text:
        return
    page_h = c._pagesize[1]  # type: ignore[attr-defined]
    x = x_mm * mm
    y = page_h - y_mm * mm - size  # baseline shift
    c.setFont(font, size)
    c.setFillColorRGB(*_color(color))

    if align == "right":
        c.drawRightString(x, y, text)
    elif align == "center":
        c.drawCentredString(x, y, text)
    else:
        c.drawString(x, y, text)


def _draw_image(c: canvas.Canvas, image_bytes: bytes,
                x_mm: float, y_mm: float, w_mm: float, h_mm: float) -> None:
    """Draw an image (bytes) at the given bounding box (mm, from top-left)."""
    if not image_bytes:
        return
    page_h = c._pagesize[1]  # type: ignore[attr-defined]
    try:
        reader = ImageReader(io.BytesIO(image_bytes))
        x = x_mm * mm
        y = page_h - (y_mm + h_mm) * mm
        c.drawImage(reader, x, y, w_mm * mm, h_mm * mm,
                    preserveAspectRatio=True, anchor="nw", mask="auto")
    except Exception:
        pass  # bad image must never abort the PDF


def _draw_watermark(c: canvas.Canvas, text: str,
                    page_w_mm: float, page_h_mm: float,
                    opacity: float = 0.08, angle: float = -45,
                    font_size: float = 60, color: str = "#888888") -> None:
    """Draw a diagonal watermark centred on the page."""
    if not text:
        return
    c.saveState()
    c.setFillColorRGB(*_color(color))
    c.setFont("Helvetica", font_size)
    # Set transparency (ReportLab 3.x)
    try:
        c.setFillAlpha(opacity)
    except Exception:
        pass
    cx = (page_w_mm / 2) * mm
    cy = (page_h_mm / 2) * mm
    c.translate(cx, cy)
    c.rotate(angle)
    c.drawCentredString(0, 0, text)
    c.restoreState()


# ── Main build function ────────────────────────────────────────────────────────

def build_letterhead_pdf(
    *,
    template: dict,
    content_pages: list[list[dict]],  # list of pages; each page is list of element dicts
    company: dict,
    logo_bytes: Optional[bytes] = None,
    logo2_bytes: Optional[bytes] = None,
    background_bytes: Optional[bytes] = None,
    total_pages: Optional[int] = None,
    printed_by: str = "",
    document_title: str = "",
    doc_number: str = "",
    doc_date: str = "",
    show_page_numbers: bool = True,
    digital_sig_label: str = "",
) -> bytes:
    """
    Build a complete letterhead PDF.

    template: dict with all LetterheadTemplate fields.
    content_pages: list of pages; each page is a list of element dicts:
        { type: "text"|"table"|"spacer", ... }
    company: company profile dict (name, address, gstin, etc.)
    """
    # ── Resolve page size ──────────────────────────────────────────────────────
    ps_key = template.get("page_size") or "A4"
    pagesize = _PAGE_SIZES.get(ps_key, A4)
    page_w_pt, page_h_pt = pagesize
    page_w_mm = page_w_pt / mm
    page_h_mm = page_h_pt / mm

    # ── Resolve margins ────────────────────────────────────────────────────────
    ml   = float(template.get("margin_left")   or 20)
    mr   = float(template.get("margin_right")  or 20)
    mt   = float(template.get("margin_top")    or 15)
    mb   = float(template.get("margin_bottom") or 15)
    hdr  = float(template.get("header_height") or 35)
    ftr  = float(template.get("footer_height") or 22)

    # ── Resolve theme ──────────────────────────────────────────────────────────
    theme_key   = template.get("theme") or "corporate_blue"
    preset      = THEME_PRESETS.get(theme_key, THEME_PRESETS["corporate_blue"])
    def _tc(field: str, fallback: str) -> str:
        return template.get(field) or preset.get(field) or fallback

    primary     = _tc("primary_color",     "#1a56db")
    secondary   = _tc("secondary_color",   "#e8f0fe")
    accent      = _tc("accent_color",      "#f59e0b")
    text_col    = _tc("text_color",        "#111827")
    hdr_bg      = _tc("header_bg_color",   "#1a56db")
    ftr_bg      = _tc("footer_bg_color",   "#f0f4ff")
    hdr_txt     = preset.get("header_text_color", "#ffffff")
    ftr_txt     = preset.get("footer_text_color", "#374151")

    font_family = template.get("font_family") or "Helvetica"
    body_size   = float(template.get("font_size_body") or 10)

    logo_pos    = template.get("logo_position") or "left"
    logo_w      = float(template.get("logo_width_mm")  or 40)
    logo_h      = float(template.get("logo_height_mm") or 18)

    wm_text     = template.get("watermark_text") or ""
    wm_opacity  = float(template.get("watermark_opacity")   or 0.08)
    wm_angle    = float(template.get("watermark_angle")     or -45)
    wm_size     = float(template.get("watermark_font_size") or 60)
    wm_color    = template.get("watermark_color") or "#888888"

    # ── Header / footer element lists ──────────────────────────────────────────
    hdr_elements = template.get("header_elements") or []
    ftr_elements = template.get("footer_elements") or []

    # ── Buffer & canvas ────────────────────────────────────────────────────────
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=pagesize)
    c.setTitle(document_title or template.get("template_name") or "Document")
    c.setAuthor(company.get("name") or "")

    n_pages = total_pages or max(1, len(content_pages))

    def _draw_header(page_num: int) -> None:
        """Draw background, logo, company info, divider for the header band."""
        # Background fill
        _draw_rect(c, ml, mt, page_w_mm - ml - mr, hdr,
                   fill_color=hdr_bg)

        # Background image (full page)
        if background_bytes:
            _draw_image(c, background_bytes, 0, 0, page_w_mm, page_h_mm)

        # Watermark (per-page, under header)
        if wm_text:
            _draw_watermark(c, wm_text, page_w_mm, page_h_mm,
                            wm_opacity, wm_angle, wm_size, wm_color)

        # ── Logo placement ──────────────────────────────────────────────────
        content_x = ml + 3
        logo_y    = mt + 3
        txt_x = ml + 6

        if logo_bytes:
            if logo_pos == "left":
                _draw_image(c, logo_bytes, content_x, logo_y, logo_w, logo_h)
                txt_x = content_x + logo_w + 5
            elif logo_pos == "center":
                lx = (page_w_mm - logo_w) / 2
                _draw_image(c, logo_bytes, lx, logo_y, logo_w, logo_h)
                txt_x = ml + 6
            elif logo_pos == "right":
                rx = page_w_mm - mr - logo_w - 3
                _draw_image(c, logo_bytes, rx, logo_y, logo_w, logo_h)
                txt_x = ml + 6

        # ── Secondary logo (top-right corner) ──────────────────────────────
        if logo2_bytes:
            rx2 = page_w_mm - mr - 30 - 3
            _draw_image(c, logo2_bytes, rx2, logo_y, 28, 14)

        # ── Company name (large, prominent) ────────────────────────────────
        cname = company.get("name") or ""
        tagline = company.get("tagline") or ""
        _draw_text(c, cname, txt_x, mt + 8, font_family + "-Bold" if font_family == "Helvetica" else font_family, 14, hdr_txt, "left")
        if tagline:
            _draw_text(c, tagline, txt_x, mt + 14, font_family, 8, hdr_txt, "left")

        # ── Contact info block (right side of header) ──────────────────────
        rx = page_w_mm - mr - 5
        cy_start = mt + 7
        c_gap = 4.5
        fields_right: list[str] = []
        if company.get("address"):
            fields_right.append(company["address"])
        if company.get("phone"):
            fields_right.append(f'Ph: {company["phone"]}')
        if company.get("email"):
            fields_right.append(f'E: {company["email"]}')
        if company.get("website"):
            fields_right.append(f'W: {company["website"]}')
        if company.get("gstin"):
            fields_right.append(f'GSTIN: {company["gstin"]}')
        if company.get("pan"):
            fields_right.append(f'PAN: {company["pan"]}')

        for i, line in enumerate(fields_right[:6]):
            _draw_text(c, line, rx, cy_start + i * c_gap, font_family, 7.5, hdr_txt, "right")

        # ── Custom header elements (drag-drop placed) ───────────────────────
        for el in hdr_elements:
            _render_element(c, el, hdr_txt, font_family, body_size, page_w_mm, page_h_mm,
                            page_num, n_pages, ml=ml, mr=mr,
                            company=company, logo_bytes=logo_bytes)

        # ── Bottom divider line ─────────────────────────────────────────────
        divider_y = mt + hdr + 1
        _draw_line(c, ml, divider_y, page_w_mm - mr, divider_y, accent, 1.0)

    def _draw_footer(page_num: int) -> None:
        """Draw footer band with page number, date, company info."""
        fy = page_h_mm - mb - ftr
        _draw_rect(c, ml, fy, page_w_mm - ml - mr, ftr, fill_color=ftr_bg)

        # Top divider
        _draw_line(c, ml, fy - 0.5, page_w_mm - mr, fy - 0.5, accent, 0.5)

        fy_txt = fy + 5
        # Left side: address / company details
        caddr = company.get("address") or ""
        _draw_text(c, caddr, ml + 3, fy_txt, font_family, 7, ftr_txt, "left")

        # Center: GSTIN, PAN
        center_x = page_w_mm / 2
        tax_parts = []
        if company.get("gstin"):
            tax_parts.append(f'GSTIN: {company["gstin"]}')
        if company.get("pan"):
            tax_parts.append(f'PAN: {company["pan"]}')
        _draw_text(c, "  |  ".join(tax_parts), center_x, fy_txt, font_family, 7, ftr_txt, "center")

        # Right side: page number & date
        if show_page_numbers:
            _draw_text(c, f"Page {page_num} of {n_pages}", page_w_mm - mr - 3, fy_txt, font_family, 7.5, ftr_txt, "right")

        # Second footer row
        fy_txt2 = fy_txt + 5
        email_w = company.get("email") or ""
        site    = company.get("website") or ""
        _draw_text(c, f'{email_w}  |  {site}', ml + 3, fy_txt2, font_family, 6.5, ftr_txt, "left")

        if doc_date:
            _draw_text(c, f"Date: {doc_date}", page_w_mm - mr - 3, fy_txt2, font_family, 6.5, ftr_txt, "right")

        # Custom footer elements
        for el in ftr_elements:
            _render_element(c, el, ftr_txt, font_family, body_size, page_w_mm, page_h_mm,
                            page_num, n_pages, ml=ml, mr=mr,
                            company=company, logo_bytes=logo_bytes)

        # Printed-by / confidential
        if printed_by:
            conf_y = fy_txt2 + 5
            _draw_text(c, f"Printed by: {printed_by}", ml + 3, conf_y, font_family, 6, ftr_txt, "left")
        _draw_text(c, "CONFIDENTIAL — FOR AUTHORISED USE ONLY", page_w_mm - mr - 3,
                   fy + ftr - 5, font_family, 5.5, ftr_txt, "right")

    # ── Render pages ───────────────────────────────────────────────────────────
    for page_idx, page_content in enumerate(content_pages if content_pages else [[]]):
        page_num = page_idx + 1

        _draw_header(page_num)
        _draw_footer(page_num)

        # ── Content area ────────────────────────────────────────────────────
        content_top = mt + hdr + 3          # mm from top of page
        content_bot = page_h_mm - mb - ftr - 3
        _cursor_y = content_top

        for el in (page_content or []):
            _cursor_y = _render_element(c, el, text_col, font_family, body_size,
                                        page_w_mm, page_h_mm, page_num, n_pages,
                                        ml=ml, mr=mr, cursor_y=_cursor_y,
                                        content_bot=content_bot,
                                        company=company, logo_bytes=logo_bytes)

        c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()


def _substitute_tokens(text: str, company: dict | None,
                       page_num: int, total_pages: int) -> str:
    """Replace {token} placeholders in a text element with live data.

    Supports the page tokens (always) plus company-profile tokens so a
    drag-and-drop text block like "{company_name}" or "GST: {company_gstin}"
    renders the real company details at PDF time. Unknown tokens are left as-is.
    Prefixed forms (e.g. {company_gstin}) and short forms (e.g. {gstin}) both
    resolve, so older/newer element data stays compatible.
    """
    company = company or {}
    mapping = {
        "page": str(page_num),
        "total": str(total_pages),
        "company_name": company.get("name") or "",
        "company_tagline": company.get("tagline") or "",
        "company_gstin": company.get("gstin") or "",
        "company_pan": company.get("pan") or "",
        "company_address": company.get("address") or "",
        "company_phone": company.get("phone") or "",
        "company_email": company.get("email") or "",
        "company_website": company.get("website") or "",
        # Short aliases
        "name": company.get("name") or "",
        "tagline": company.get("tagline") or "",
        "gstin": company.get("gstin") or "",
        "pan": company.get("pan") or "",
        "address": company.get("address") or "",
        "phone": company.get("phone") or "",
        "email": company.get("email") or "",
        "website": company.get("website") or "",
    }
    for token, val in mapping.items():
        text = text.replace("{" + token + "}", val)
    return text


def _render_element(c: canvas.Canvas, el: dict,
                    default_color: str, default_font: str, default_size: float,
                    page_w_mm: float, page_h_mm: float,
                    page_num: int, total_pages: int,
                    ml: float = 20, mr: float = 20,
                    cursor_y: float = 0, content_bot: float = 270,
                    company: dict | None = None,
                    logo_bytes: Optional[bytes] = None) -> float:
    """Render a single content element dict; returns updated cursor_y."""
    el_type = (el.get("type") or "text").lower()
    color   = el.get("color") or default_color
    font    = el.get("font")  or default_font
    size    = float(el.get("size") or default_size)
    align   = (el.get("align") or "left").lower()

    if el_type == "text":
        text = el.get("value") or el.get("text") or ""
        text = _substitute_tokens(text, company, page_num, total_pages)
        x_mm = el.get("x_mm")
        y_mm = el.get("y_mm")
        x = float(x_mm) if x_mm is not None else ml + 3
        y = float(y_mm) if y_mm is not None else cursor_y
        _draw_text(c, text, x, y, font, size, color, align)
        return y + size * 0.35 + 2

    elif el_type == "line":
        y_mm = el.get("y_mm")
        y = float(y_mm) if y_mm is not None else cursor_y
        _draw_line(c, ml, y, page_w_mm - mr, y, color, float(el.get("width") or 0.5))
        return y + 2

    elif el_type == "rect":
        x   = float(el.get("x_mm") or ml)
        y   = float(el.get("y_mm") or cursor_y)
        w   = float(el.get("w_mm") or (page_w_mm - ml - mr))
        h   = float(el.get("h_mm") or 8)
        _draw_rect(c, x, y, w, h, el.get("fill_color"), el.get("stroke_color"), float(el.get("line_width") or 0))
        return y + h + 1

    elif el_type == "spacer":
        return cursor_y + float(el.get("height") or 5)

    elif el_type in ("image", "logo"):
        x   = float(el.get("x_mm") or ml)
        y   = float(el.get("y_mm") or cursor_y)
        w   = float(el.get("w_mm") or 40)
        h_el = float(el.get("h_mm") or 20)
        # A "logo" block (or an image whose source is "logo"/"{logo}") renders
        # the template's uploaded logo; an explicit image block may carry its
        # own bytes. This lets the drag-drop designer place the company logo.
        src = (el.get("source") or el.get("value") or "").strip().lower()
        img = el.get("image_bytes")
        if img is None and (el_type == "logo" or src in ("logo", "{logo}", "")):
            img = logo_bytes
        if img:
            _draw_image(c, img, x, y, w, h_el)
        return y + h_el + 1

    return cursor_y


def build_preview_pdf(template: dict, company: dict,
                      logo_bytes: Optional[bytes] = None,
                      logo2_bytes: Optional[bytes] = None) -> bytes:
    """Build a single-page preview of the letterhead (no content body)."""
    sample_content = [[
        {"type": "text", "value": f"← Content area starts here (margins: {template.get('margin_left',20)}mm left, {template.get('margin_right',20)}mm right)", "size": 10, "color": "#6b7280"},
        {"type": "spacer", "height": 8},
        {"type": "text", "value": "Sample paragraph text: This is where invoice / purchase order / quotation body content will appear.", "size": 10, "color": "#374151"},
        {"type": "spacer", "height": 5},
        {"type": "line", "color": "#e5e7eb", "width": 0.5},
        {"type": "spacer", "height": 5},
        {"type": "text", "value": "← Footer band is shown below →", "size": 9, "color": "#9ca3af", "align": "center"},
    ]]
    return build_letterhead_pdf(
        template=template,
        content_pages=sample_content,
        company=company,
        logo_bytes=logo_bytes,
        logo2_bytes=logo2_bytes,
        document_title="Letterhead Preview",
        doc_number="PREVIEW-001",
        doc_date="2026-06-29",
        printed_by="Preview User",
        show_page_numbers=True,
        total_pages=1,
    )
