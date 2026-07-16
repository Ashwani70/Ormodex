"""Reusable PDF building blocks shared by every document type.

Each function returns a ReportLab flowable (or list of flowables) styled per
core/pdf_theme.py. Compose these in a doc-type-specific order inside
core/pdf.py's build_document_pdf — the components themselves carry no
document-type-specific logic.
"""
from __future__ import annotations

from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable, Paragraph, Spacer, Table, TableStyle,
)

from . import pdf_theme as T

CONTENT_W = T.CONTENT_WIDTH_MM * mm


# ─────────────────────────────────────────────────────────────────────────────
# RoundedCard — a Flowable wrapper that draws a rounded-rect card background
# behind arbitrary inner content (built as a nested Table). This is the one
# genuinely new rendering primitive the redesign needs: ReportLab's Table
# borders are always square-cornered, so "12px radius, subtle border, no
# heavy black boxes" requires drawing the card frame by hand on the canvas.
# ─────────────────────────────────────────────────────────────────────────────
class RoundedCard(Flowable):
    def __init__(self, inner_flowable, width, fill: Optional[colors.Color] = None,
                 stroke: Optional[colors.Color] = T.BORDER,
                 stroke_width=0.75, radius=T.RADIUS, pad=6):
        super().__init__()
        self.inner = inner_flowable
        self.width = width
        self.fill = fill
        self.stroke = stroke
        self.stroke_width = stroke_width
        self.radius = radius
        self.pad = pad
        iw, ih = inner_flowable.wrapOn(None, width - 2 * pad, 10_000)
        self.inner_h = ih
        self.height = ih + 2 * pad

    def wrap(self, aW, aH):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        if self.fill is not None:
            c.setFillColor(self.fill)
        if self.stroke is not None:
            c.setStrokeColor(self.stroke)
            c.setLineWidth(self.stroke_width)
        if self.fill is not None or self.stroke is not None:
            c.roundRect(0, 0, self.width, self.height, self.radius,
                        stroke=1 if self.stroke is not None else 0,
                        fill=1 if self.fill is not None else 0)
        c.restoreState()
        self.inner.wrapOn(c, self.width - 2 * self.pad, self.inner_h)
        self.inner.drawOn(c, self.pad, self.height - self.pad - self.inner_h)


def card(inner_flowable, width=CONTENT_W, fill=T.CARD_BG, stroke: Optional[colors.Color] = T.BORDER, pad=8):
    return RoundedCard(inner_flowable, width, fill=fill, stroke=stroke, pad=pad)


# ─────────────────────────────────────────────────────────────────────────────
# Paragraph style factory — every text style used across components pulls
# from the same typography scale so nothing drifts document to document.
# ─────────────────────────────────────────────────────────────────────────────
def styles():
    base = ParagraphStyle("base", fontName=T.FONT_REGULAR, fontSize=T.SIZE_BODY,
                          leading=T.SIZE_BODY * 1.35, textColor=T.TEXT)
    return {
        "company_name": ParagraphStyle("company_name", parent=base, fontName=T.FONT_BOLD,
                                       fontSize=T.SIZE_COMPANY_NAME, leading=T.SIZE_COMPANY_NAME * 1.15,
                                       textColor=T.TEXT),
        "company_meta": ParagraphStyle("company_meta", parent=base, fontSize=7.5,
                                       leading=10.5, textColor=T.TEXT_SECONDARY),
        "doc_title": ParagraphStyle("doc_title", parent=base, fontName=T.FONT_SEMIBOLD,
                                    fontSize=T.SIZE_DOC_TITLE, leading=T.SIZE_DOC_TITLE * 1.15,
                                    textColor=T.PRIMARY, alignment=2),
        "doc_number": ParagraphStyle("doc_number", parent=base, fontName=T.FONT_BOLD,
                                     fontSize=12, leading=15, textColor=T.TEXT, alignment=2),
        "doc_meta": ParagraphStyle("doc_meta", parent=base, fontSize=7.5,
                                   leading=10.5, textColor=T.TEXT_SECONDARY, alignment=2),
        "section_heading": ParagraphStyle("section_heading", parent=base, fontName=T.FONT_BOLD,
                                          fontSize=T.SIZE_SECTION_HEADING, leading=12,
                                          textColor=T.TEXT_SECONDARY, spaceAfter=3),
        "label": ParagraphStyle("label", parent=base, fontName=T.FONT_MEDIUM,
                                fontSize=T.SIZE_LABEL, leading=10, textColor=T.TEXT_MUTED),
        "value": ParagraphStyle("value", parent=base, fontName=T.FONT_MEDIUM,
                                fontSize=T.SIZE_BODY, leading=11.5, textColor=T.TEXT),
        "value_strong": ParagraphStyle("value_strong", parent=base, fontName=T.FONT_SEMIBOLD,
                                       fontSize=9.5, leading=12.5, textColor=T.TEXT),
        "body": base,
        "body_muted": ParagraphStyle("body_muted", parent=base, textColor=T.TEXT_SECONDARY),
        "table_header": ParagraphStyle("table_header", parent=base, fontName=T.FONT_SEMIBOLD,
                                       fontSize=7, leading=9, textColor=colors.white),
        "table_cell": ParagraphStyle("table_cell", parent=base, fontSize=8.25, leading=11),
        "table_cell_right": ParagraphStyle("table_cell_right", parent=base, fontSize=8.25,
                                           leading=11, alignment=2),
        "totals_label": ParagraphStyle("totals_label", parent=base, fontSize=T.SIZE_TOTALS - 1,
                                       leading=13, textColor=T.TEXT_SECONDARY),
        "totals_value": ParagraphStyle("totals_value", parent=base, fontSize=T.SIZE_TOTALS - 1,
                                       leading=13, textColor=T.TEXT, alignment=2),
        "grand_total_label": ParagraphStyle("grand_total_label", parent=base, fontName=T.FONT_BOLD,
                                            fontSize=T.SIZE_GRAND_TOTAL - 2, leading=16, textColor=T.PRIMARY),
        "grand_total_value": ParagraphStyle("grand_total_value", parent=base, fontName=T.FONT_BOLD,
                                            fontSize=T.SIZE_GRAND_TOTAL, leading=17, textColor=T.PRIMARY,
                                            alignment=2),
        "amount_words_label": ParagraphStyle("amount_words_label", parent=base, fontName=T.FONT_SEMIBOLD,
                                             fontSize=7.5, leading=10, textColor=T.PRIMARY),
        "amount_words_value": ParagraphStyle("amount_words_value", parent=base, fontName=T.FONT_MEDIUM,
                                             fontSize=9.5, leading=13, textColor=T.TEXT),
        "footer": ParagraphStyle("footer", parent=base, fontSize=6.5, leading=9, textColor=T.TEXT_MUTED),
        "sig_label": ParagraphStyle("sig_label", parent=base, fontName=T.FONT_MEDIUM,
                                    fontSize=7.5, leading=10, textColor=T.TEXT_SECONDARY, alignment=1),
        "sig_name": ParagraphStyle("sig_name", parent=base, fontName=T.FONT_SEMIBOLD,
                                   fontSize=8.5, leading=11, textColor=T.TEXT, alignment=1),
    }


_S = styles()


def _p(text, style_key="body"):
    return Paragraph(str(text) if text is not None else "", _S[style_key])


def table_cell_paragraph(text) -> Paragraph:
    """Build a Paragraph in the item table's own wrapping cell style — the
    style callers should use for a description cell passed into item_table()
    so long product names wrap identically to the rest of the table."""
    return _p(text, "table_cell")


# ─────────────────────────────────────────────────────────────────────────────
# Status badge — small pill, colored per doc status
# ─────────────────────────────────────────────────────────────────────────────
def status_badge(status: str):
    status = (status or "").upper()
    text_color, bg_color = T.STATUS_COLORS.get(status, T.DEFAULT_STATUS_COLOR)
    style = ParagraphStyle("badge", fontName=T.FONT_SEMIBOLD, fontSize=7.5,
                           leading=9, textColor=text_color, alignment=1)
    t = Table([[Paragraph(status or "—", style)]], colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg_color),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


# ─────────────────────────────────────────────────────────────────────────────
# Document header — company identity (left) + doc title/number/badge/dates
# (right), optional barcode beneath the number.
# ─────────────────────────────────────────────────────────────────────────────
def document_header(company: dict, doc_type: str, doc_number: str,
                    status: Optional[str] = None, issue_date: Optional[str] = None,
                    due_date: Optional[str] = None, due_label: str = "Due",
                    barcode_flowable=None, extra_meta: Optional[str] = None):
    from .pdf import _load_logo_image  # reuse existing logo fetch/scale helper

    company = company or {}
    logo = _load_logo_image(company.get("logo_url"), max_w_mm=26, max_h_mm=18)

    left_rows: list[Any] = []
    if logo is not None:
        left_rows.append([logo])
        left_rows.append([Spacer(1, 4)])
    left_rows.append([_p(company.get("name") or "Company Name", "company_name")])

    meta_bits = []
    addr = company.get("address")
    city_state = " · ".join(b for b in [company.get("city"), company.get("state")] if b)
    if addr:
        meta_bits.append(str(addr) + (f", {city_state}" if city_state else ""))
    elif city_state:
        meta_bits.append(city_state)
    ids = []
    if company.get("gstin"):
        ids.append(f"GSTIN {company['gstin']}")
    if company.get("pan"):
        ids.append(f"PAN {company['pan']}")
    if ids:
        meta_bits.append(" · ".join(ids))
    contact = []
    if company.get("phone"):
        contact.append(company["phone"])
    if company.get("email"):
        contact.append(company["email"])
    if company.get("website"):
        contact.append(company["website"])
    if contact:
        meta_bits.append(" · ".join(contact))
    for bit in meta_bits:
        left_rows.append([_p(bit, "company_meta")])

    left_table = Table(left_rows, colWidths=[100 * mm])
    left_table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    right_rows: list[Any] = [[_p(doc_type, "doc_title")], [_p(doc_number, "doc_number")]]
    if status:
        badge = status_badge(status)
        badge_wrap = Table([[badge]], colWidths=[None])
        badge_wrap.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                        ("TOPPADDING", (0, 0), (-1, -1), 2)]))
        right_rows.append([badge_wrap])
    date_bits = []
    if issue_date:
        date_bits.append(f"Issued {issue_date}")
    if due_date:
        date_bits.append(f"{due_label} {due_date}")
    if date_bits:
        right_rows.append([_p(" · ".join(date_bits), "doc_meta")])
    if extra_meta:
        right_rows.append([_p(extra_meta, "doc_meta")])
    if barcode_flowable is not None:
        bc_wrap = Table([[barcode_flowable]], colWidths=[None])
        bc_wrap.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                     ("TOPPADDING", (0, 0), (-1, -1), 5)]))
        right_rows.append([bc_wrap])

    right_table = Table(right_rows, colWidths=[80 * mm])
    right_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    outer = Table([[left_table, right_table]], colWidths=[110 * mm, 68 * mm])
    outer.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    divider = Table([[""]], colWidths=[CONTENT_W], rowHeights=[1.2])
    divider.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), T.BORDER)]))

    return [outer, Spacer(1, 8), divider, Spacer(1, 10)]


# ─────────────────────────────────────────────────────────────────────────────
# Party card — Supplier / Buyer identity, used in equal-width pairs
# ─────────────────────────────────────────────────────────────────────────────
def party_card(heading: str, name: str, party: dict, width, two_col: bool = False):
    """two_col=True lays the address/GSTIN/contact lines out as a 2-column
    grid instead of one-per-row — for full-width stacked cards (which have
    plenty of horizontal room to spare) this roughly halves the card's
    vertical footprint versus stacking every line, without shrinking type
    or padding."""
    party = party or {}

    lines = []
    addr = party.get("billing_address") or party.get("address")
    if addr:
        for ln in str(addr).split("\n"):
            if ln.strip():
                lines.append(ln.strip())
    city_bits = " · ".join(b for b in [party.get("city"), party.get("state"), party.get("pincode")] if b)
    if city_bits:
        lines.append(city_bits)
    ids = []
    if party.get("gstin"):
        ids.append(f"GSTIN {party['gstin']}")
    if party.get("pan"):
        ids.append(f"PAN {party['pan']}")
    if ids:
        lines.append(" · ".join(ids))
    contact_bits = []
    if party.get("contact_person"):
        contact_bits.append(party["contact_person"])
    ph = party.get("mobile") or party.get("phone")
    if ph:
        contact_bits.append(ph)
    if contact_bits:
        lines.append(" · ".join(contact_bits))
    if party.get("email"):
        lines.append(party["email"])

    if two_col and len(lines) > 1:
        rows: list[Any] = [[_p(heading, "section_heading"), ""], [_p(name or "—", "value_strong"), ""]]
        half = (len(lines) + 1) // 2
        left_lines, right_lines = lines[:half], lines[half:]
        for i in range(half):
            l = _p(left_lines[i], "value")
            r = _p(right_lines[i], "value") if i < len(right_lines) else ""
            rows.append([l, r])
        col_w = (width - 16) / 2
        inner = Table(rows, colWidths=[col_w, col_w])
        inner.setStyle(TableStyle([
            ("SPAN", (0, 0), (1, 0)), ("SPAN", (0, 1), (1, 1)),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 2), (-1, -1), 1.5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
        ]))
        return card(inner, width=width, fill=T.CARD_BG, stroke=T.BORDER, pad=6)

    rows = [[_p(heading, "section_heading")], [_p(name or "—", "value_strong")]]
    for ln in lines:
        rows.append([_p(ln, "value")])

    inner = Table(rows, colWidths=[width - 16])
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 1), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
    ]))
    return card(inner, width=width, fill=T.CARD_BG, stroke=T.BORDER, pad=8)


def party_card_row(left_card, right_card, gap_mm=6):
    w = (CONTENT_W - gap_mm * mm) / 2
    t = Table([[left_card, "", right_card]], colWidths=[w, gap_mm * mm, w])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


# ─────────────────────────────────────────────────────────────────────────────
# Detail cards — small label/value chips laid out in a responsive grid
# (used for Invoice Date / Due Date / PO No / Vehicle No / Transport / E-Way
# Bill / Place of Supply / Payment Terms / Currency / Prepared By etc.)
# Only pairs with a real, non-empty value are rendered.
# ─────────────────────────────────────────────────────────────────────────────
def detail_grid(pairs: list[tuple[str, Any]], columns: int = 4):
    pairs = [(label, value) for label, value in pairs if value not in (None, "", "—")]
    if not pairs:
        return None

    gap = 4 * mm
    cell_w = (CONTENT_W - gap * (columns - 1)) / columns
    cells = []
    for label, value in pairs:
        inner = Table([[_p(label.upper(), "label")], [_p(value, "value_strong")]],
                      colWidths=[cell_w - 14])
        inner.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ]))
        cells.append(card(inner, width=cell_w, fill=T.TABLE_HEADER_BG, stroke=T.BORDER_SOFT, pad=7))

    rows = []
    for i in range(0, len(cells), columns):
        row_cells = cells[i:i + columns]
        row = []
        widths = []
        for j, c in enumerate(row_cells):
            if j:
                row.append("")
                widths.append(gap)
            row.append(c)
            widths.append(cell_w)
        # pad the last row so column widths stay consistent
        while len(row_cells) < columns and len(row) < columns * 2 - 1:
            row.append("")
            widths.append(gap)
            row.append("")
            widths.append(cell_w)
            row_cells.append(None)
        t = Table([row], colWidths=widths)
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        rows.append(t)
        # Spacer BETWEEN rows only (not a trailing one after the last row) —
        # callers already add their own spacer after the whole grid, so a
        # trailing one here was pure redundant vertical space.
        if i + columns < len(cells):
            rows.append(Spacer(1, 4 * mm - 4))

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Item table — repeats its header row automatically across page breaks
# (Table(..., repeatRows=1) is ReportLab's native support for this).
# ─────────────────────────────────────────────────────────────────────────────
ITEM_TABLE_COLUMNS = [
    ("#", 9, "CENTER"),
    ("ITEM / DESCRIPTION", None, "LEFT"),   # flex column, gets remaining width
    ("HSN/SAC", 19, "CENTER"),
    ("UNIT", 10, "CENTER"),
    ("QTY", 12, "RIGHT"),
    ("RATE", 19, "RIGHT"),
    ("DISC", 14, "RIGHT"),
    ("TAXABLE", 24, "RIGHT"),
    ("GST %", 13, "RIGHT"),
    ("AMOUNT", 24, "RIGHT"),
]


def item_table(rows: list[dict], show_discount: bool = False):
    """rows: list of dicts with keys sno, description, hsn, unit, qty, rate,
    discount, taxable, gst_rate, amount (pre-formatted strings/Paragraphs)."""
    columns = ITEM_TABLE_COLUMNS if show_discount else [
        c for c in ITEM_TABLE_COLUMNS if c[0] != "DISC"
    ]
    fixed_mm = sum(w for _, w, _ in columns if w is not None)
    flex_mm = T.CONTENT_WIDTH_MM - fixed_mm
    col_widths = [((w if w is not None else flex_mm) * mm) for _, w, _ in columns]

    header_row = [Paragraph(label, _S["table_header"]) for label, _, _ in columns]

    data = [header_row]
    for r in rows:
        cells = []
        for label, _, align in columns:
            key = {
                "#": "sno", "ITEM / DESCRIPTION": "description", "HSN/SAC": "hsn",
                "UNIT": "unit", "QTY": "qty", "RATE": "rate", "DISC": "discount",
                "TAXABLE": "taxable", "GST %": "gst_rate", "AMOUNT": "amount",
            }[label]
            val = r.get(key, "")
            style_key = "table_cell" if label in ("#", "ITEM / DESCRIPTION") else "table_cell_right"
            cells.append(val if isinstance(val, Paragraph) else Paragraph(str(val), _S[style_key]))
        data.append(cells)

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), T.PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), T.FONT_REGULAR),
        ("FONTSIZE", (0, 0), (-1, -1), 8.25),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), 0, T.PRIMARY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, T.BORDER),
        ("BOX", (0, 0), (-1, -1), 0.75, T.BORDER),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), T.TABLE_ROW_ALT))
    t.setStyle(TableStyle(style))
    return t


# ─────────────────────────────────────────────────────────────────────────────
# Totals card — right-aligned summary block, only rows with real values shown
# ─────────────────────────────────────────────────────────────────────────────
def totals_card(rows: list[tuple[str, str]], grand_label: str, grand_value: str, width_mm=85):
    width = width_mm * mm
    inner_rows: list[Any] = []
    for label, value in rows:
        inner_rows.append([_p(label, "totals_label"), _p(value, "totals_value")])

    body = None
    if inner_rows:
        body = Table(inner_rows, colWidths=[width * 0.55 - 16, width * 0.45])
        body.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]))

    grand_row = Table([[_p(grand_label, "grand_total_label"), _p(grand_value, "grand_total_value")]],
                      colWidths=[width * 0.5 - 16, width * 0.5])
    grand_row.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    grand_card = card(grand_row, width=width - 2, fill=T.PRIMARY_SOFT, stroke=None, pad=6)

    pieces = []
    if body is not None:
        pieces.append([body])
        pieces.append([Spacer(1, 3)])
    pieces.append([grand_card])
    outer = Table(pieces, colWidths=[width])
    outer.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return card(outer, width=width, fill=T.CARD_BG, stroke=T.BORDER, pad=9)


def totals_row(totals_card_flowable):
    """Right-align the totals card within the full content width."""
    t = Table([["", totals_card_flowable]], colWidths=[CONTENT_W - totals_card_flowable.width, totals_card_flowable.width])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


# ─────────────────────────────────────────────────────────────────────────────
# Amount in words — highlighted card
# ─────────────────────────────────────────────────────────────────────────────
def amount_in_words_card(text: str):
    inner = Table([[_p("AMOUNT IN WORDS", "amount_words_label")], [_p(text, "amount_words_value")]],
                  colWidths=[CONTENT_W - 18])
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (0, 0), 3),
    ]))
    return card(inner, width=CONTENT_W, fill=T.PRIMARY_SOFT, stroke=None, pad=9)


# ─────────────────────────────────────────────────────────────────────────────
# Payment / bank details card
# ─────────────────────────────────────────────────────────────────────────────
def payment_card(bank: dict, payment_terms: Optional[str] = None, instructions: Optional[str] = None):
    bank = bank or {}
    rows: list[Any] = [[_p("PAYMENT DETAILS", "section_heading")]]
    bits = [
        ("Bank", bank.get("bank_name")),
        ("Account No.", bank.get("bank_account_no")),
        ("IFSC", bank.get("bank_ifsc")),
        ("Branch", bank.get("bank_branch")),
    ]
    bits = [(l, v) for l, v in bits if v]
    if bits:
        line = " · ".join(f"{l}: {v}" for l, v in bits)
        rows.append([_p(line, "value")])
    if payment_terms:
        rows.append([_p(f"Payment Terms: {payment_terms}", "value")])
    if instructions:
        rows.append([_p(instructions, "body_muted")])
    if len(rows) == 1:
        return None
    inner = Table(rows, colWidths=[CONTENT_W - 16])
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return card(inner, width=CONTENT_W, fill=T.CARD_BG, stroke=T.BORDER, pad=8)


# ─────────────────────────────────────────────────────────────────────────────
# Terms & conditions / declaration card
# ─────────────────────────────────────────────────────────────────────────────
def terms_card(heading: str, text: str, width=CONTENT_W):
    if not text:
        return None
    rows = [[_p(heading, "section_heading")], [_p(text, "body_muted")]]
    inner = Table(rows, colWidths=[width - 16])
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (0, 0), 2),
    ]))
    return card(inner, width=width, fill=T.CARD_BG, stroke=T.BORDER, pad=8)


# ─────────────────────────────────────────────────────────────────────────────
# Signature block — 2 or 3 equal columns depending on how much real data exists
# ─────────────────────────────────────────────────────────────────────────────
def signature_block(company_name: str, seal_flowable=None, prepared_by: Optional[str] = None,
                    checked_by: Optional[str] = None, counter_sign_label: Optional[str] = None,
                    counter_sign_seal: bool = False):
    """counter_sign_label adds a blank signature column BEFORE "Authorised
    Signatory" for documents that need the other party to countersign (e.g.
    a Proforma Invoice's "Buyer Acceptance / Signature") — unlike
    prepared_by/checked_by, it has no pre-filled name, just a label + line.
    counter_sign_seal reserves a stamp/seal placeholder above that column's
    line too, mirroring the "(Company Seal)" placeholder the signatory side
    gets when no seal image is on file (there's never a real image for the
    counterparty's seal, so this is always the text placeholder, never an
    actual image)."""
    columns: list[tuple[str, Optional[str]]] = []
    if prepared_by:
        columns.append(("PREPARED BY", prepared_by))
    if checked_by:
        columns.append(("CHECKED BY", checked_by))
    if counter_sign_label:
        columns.append((counter_sign_label, "__blank__"))
    columns.append(("AUTHORISED SIGNATORY", None))

    gap = 6 * mm
    n = len(columns)
    col_w = (CONTENT_W - gap * (n - 1)) / n

    cells = []
    for i, (label, name) in enumerate(columns):
        rows: list[Any] = []
        is_sig = label == "AUTHORISED SIGNATORY"
        is_counter = label == counter_sign_label
        if is_sig and seal_flowable is not None:
            rows.append([seal_flowable])
            rows.append([Spacer(1, 4)])
        elif is_sig and seal_flowable is None:
            rows.append([_p("(Company Seal)", "sig_label")])
            rows.append([Spacer(1, 4)])
        elif is_counter and counter_sign_seal:
            rows.append([_p("(Company Seal / Stamp)", "sig_label")])
            rows.append([Spacer(1, 4)])
        else:
            rows.append([Spacer(1, 13)])
        rows.append([_p("_" * 28, "sig_label")])
        if name and name != "__blank__":
            rows.append([_p(name, "sig_name")])
        elif is_sig:
            rows.append([_p(f"For {company_name}", "sig_name")])
        rows.append([_p(label, "sig_label")])
        rows.append([_p("Date: ______________", "sig_label")])
        t = Table(rows, colWidths=[col_w])
        t.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        cells.append(t)
        if i < n - 1:
            cells.append(None)

    row = []
    widths = []
    for i, cell in enumerate(cells):
        if cell is None:
            row.append("")
            widths.append(gap)
        else:
            row.append(cell)
            widths.append(col_w)
    outer = Table([row], colWidths=widths)
    outer.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LINEABOVE", (0, 0), (-1, 0), 0.75, T.BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
    ]))
    return outer


def signature_block_corner(company_name: str, seal_flowable=None, width_mm=70):
    """Single-column signature block, right-aligned: Company Name → (Company
    Seal placeholder or real seal image) → signature line → 'Authorised
    Signatory' → Date. No 'For {company}' filler row (company name is
    already the first line) — matches the compact bottom-right corner style
    used by TallyPrime/Zoho Books/Busy, as opposed to the wider multi-column
    signature_block() above (which stays available for docs that need
    Prepared By / Checked By / counter-signature columns alongside it)."""
    w = width_mm * mm
    rows: list[Any] = [[_p(company_name, "value_strong")], [Spacer(1, 3)]]
    if seal_flowable is not None:
        rows.append([seal_flowable])
    else:
        rows.append([_p("(Company Seal)", "sig_label")])
    rows.append([Spacer(1, 4)])
    rows.append([_p("_" * 26, "sig_label")])
    rows.append([_p("AUTHORISED SIGNATORY", "sig_label")])
    rows.append([_p("Date: ______________", "sig_label")])

    t = Table(rows, colWidths=[w])
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return t


def declaration_and_signature_row(declaration_flowable, signature_flowable, sig_width_mm=70):
    """Bottom row: Declaration card on the left (flexes to fill remaining
    width), signature block pinned to the bottom-right corner — replaces the
    old full-width centered signature_block() placement. If there's no
    declaration to show, the signature still renders alone, right-aligned."""
    sig_w = sig_width_mm * mm
    left_w = CONTENT_W - sig_w - 6 * mm

    left_cell = declaration_flowable if declaration_flowable is not None else ""
    t = Table([[left_cell, "", signature_flowable]], colWidths=[left_w, 6 * mm, sig_w])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


# ─────────────────────────────────────────────────────────────────────────────
# Watermark + footer/page-number — applied via canvas callback (onPage), not
# a flowable, since they need to draw at fixed page coordinates behind/around
# the flowable content on every page.
# ─────────────────────────────────────────────────────────────────────────────
def draw_watermark(c, page_w, page_h, text: str):
    if not text:
        return
    c.saveState()
    c.setFont(T.FONT_BOLD, 88)
    c.setFillColor(colors.Color(0.5, 0.5, 0.5, alpha=0.08))
    c.translate(page_w / 2, page_h / 2)
    c.rotate(40)
    c.drawCentredString(0, 0, text.upper())
    c.restoreState()


def draw_footer(c, page_w, page_num, page_count, company: dict, generated_at: str):
    company = company or {}
    c.saveState()
    c.setStrokeColor(T.BORDER)
    c.setLineWidth(0.5)
    margin = T.PAGE_MARGIN_MM * mm
    y = 12 * mm
    c.line(margin, y + 8, page_w - margin, y + 8)

    left_bits = []
    if company.get("website"):
        left_bits.append(company["website"])
    if company.get("email"):
        left_bits.append(company["email"])
    if company.get("phone"):
        left_bits.append(company["phone"])
    left_text = "  ·  ".join(left_bits) if left_bits else ""

    c.setFont(T.FONT_REGULAR, 6.5)
    c.setFillColor(T.TEXT_MUTED)
    if left_text:
        c.drawString(margin, y, left_text)
    c.drawCentredString(page_w / 2, y, f"Page {page_num} of {page_count}")
    c.drawRightString(page_w - margin, y, f"Generated by ORMODEX ERP · {generated_at}")
    c.restoreState()


def barcode_flowable(value: str, height_mm=8, bar_width=0.35):
    """Code128 barcode via ReportLab's own bundled barcode module (no new
    dependency). Code128 is itself a Flowable — it goes straight into a Table
    cell, no Drawing wrapper needed (unlike QrCodeWidget, which is a Shape).
    Returns None on any failure so a bad/empty value never breaks PDF
    generation."""
    if not value:
        return None
    try:
        from reportlab.graphics.barcode.code128 import Code128
        return Code128(str(value), barHeight=height_mm * mm, barWidth=bar_width)
    except Exception:
        return None
