"""PDF document builder using reportlab."""
import io
import os
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


from functools import lru_cache
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

YELLOW = colors.HexColor("#FACC15")
BLACK = colors.HexColor("#0a0a0a")
LIGHT = colors.HexColor("#f4f4f5")

FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONTS_SUPPORT_UNICODE = False

# Fonts we ship in the repo so PDF rendering never depends on whatever fonts
# happen to be installed on the deploy host. DejaVu Sans contains the rupee
# glyph (U+20B9) in both weights, which is what was rendering as a black box
# (■ / .notdef) when the host font lacked it.
_BUNDLED_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


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


def _candidate_fonts():
    # Bundled font first — always present, always has the rupee glyph.
    candidates = [
        (
            os.path.join(_BUNDLED_FONT_DIR, "DejaVuSans.ttf"),
            os.path.join(_BUNDLED_FONT_DIR, "DejaVuSans-Bold.ttf"),
            "DejaVuSans",
        ),
    ]

    dirs = []
    if os.name == "nt":
        dirs.append(os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"))
    else:
        dirs += [
            "/usr/share/fonts/truetype/dejavu",
            "/usr/share/fonts/truetype/liberation",
            "/usr/share/fonts/TTF",
        ]
    host_candidates = [
        ("segoeui.ttf", "segoeuib.ttf", "SegoeUI"),
        ("arial.ttf", "arialbd.ttf", "Arial"),
        ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSansHost"),
        ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf", "LiberationSans"),
    ]
    for d in dirs:
        if not os.path.exists(d):
            continue
        for reg_file, bold_file, name in host_candidates:
            reg_path = os.path.join(d, reg_file)
            bold_path = os.path.join(d, bold_file)
            if os.path.exists(reg_path) and os.path.exists(bold_path):
                candidates.append((reg_path, bold_path, name))
    return candidates


def init_fonts() -> bool:
    global FONT_REGULAR, FONT_BOLD, FONTS_SUPPORT_UNICODE
    candidates = _candidate_fonts()

    # Pass 1: a font whose *both* weights contain the rupee glyph. Checking only
    # the regular face previously let through fonts where the bold face had the
    # glyph but the regular one didn't (or vice-versa), so half the currency
    # cells still rendered as a black box.
    for reg_path, bold_path, name in candidates:
        if _font_has_rupee(reg_path) and _font_has_rupee(bold_path):
            try:
                pdfmetrics.registerFont(TTFont(name, reg_path))
                pdfmetrics.registerFont(TTFont(f"{name}-Bold", bold_path))

                FONT_REGULAR = name
                FONT_BOLD = f"{name}-Bold"
                FONTS_SUPPORT_UNICODE = True
                return True
            except Exception:
                pass

    # Pass 2: Fall back to any registrable candidate font (no rupee support →
    # _money() substitutes "Rs." so nothing renders as a box).
    for reg_path, bold_path, name in candidates:
        try:
            pdfmetrics.registerFont(TTFont(name, reg_path))
            pdfmetrics.registerFont(TTFont(f"{name}-Bold", bold_path))

            FONT_REGULAR = name
            FONT_BOLD = f"{name}-Bold"
            FONTS_SUPPORT_UNICODE = False
            return False
        except Exception:
            pass

    # Fallback to Helvetica
    FONT_REGULAR = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"
    FONTS_SUPPORT_UNICODE = False
    return False

def clean_unicode(val: Any) -> Any:
    if FONTS_SUPPORT_UNICODE:
        return val
    if isinstance(val, str):
        return val.replace("₹", "Rs.")
    if isinstance(val, list):
        return [clean_unicode(item) for item in val]
    if isinstance(val, dict):
        return {k: clean_unicode(v) for k, v in val.items()}
    return val

def get_styles_with_fonts():
    styles = getSampleStyleSheet()
    for name in list(styles.byName.keys()):
        style = styles[name]
        if hasattr(style, "fontName"):
            if style.fontName == "Helvetica":
                style.fontName = FONT_REGULAR
            elif style.fontName == "Helvetica-Bold":
                style.fontName = FONT_BOLD
    return styles

CURRENCY_SYMBOLS = {
    "INR": "₹",
    "USD": "$",
    "AED": "AED ",
    "EUR": "€",
    "GBP": "£",
    "AUD": "A$",
    "SGD": "S$",
    "CAD": "C$",
}


def _money(amount, currency="INR"):
    sym = CURRENCY_SYMBOLS.get(currency, f"{currency} ")
    if currency == "INR" and not FONTS_SUPPORT_UNICODE:
        sym = "Rs."
    try:
        return f"{sym}{float(amount):,.2f}"
    except Exception:
        return f"{sym}{amount}"


_DEFAULT_COMPANY = {
    "name": "GRAVITYONE ERP",
    "tagline": "AI-POWERED BUSINESS MANAGEMENT PLATFORM",
    "address_line": "Pune, Maharashtra · India · GSTIN 27AABCG1234F1Z5",
}


def _load_logo_image(logo_url, max_w_mm=40, max_h_mm=20):
    """Resolve a company logo (storage path or http URL) into a reportlab Image,
    scaled to fit within the header without distortion. Returns None on any
    failure so PDF generation never breaks because of a bad/missing logo."""
    if not logo_url:
        return None
    try:
        from reportlab.platypus import Image as RLImage
        from reportlab.lib.utils import ImageReader

        data = None
        if str(logo_url).startswith("http"):
            import requests
            resp = requests.get(logo_url, timeout=10)
            resp.raise_for_status()
            data = resp.content
        else:
            # Local/object storage path — import lazily to avoid a hard
            # dependency (and circular import) at module load time.
            from core.storage import get_object
            data, _ = get_object(logo_url)
        if not data:
            return None

        reader = ImageReader(io.BytesIO(data))
        iw, ih = reader.getSize()
        if not iw or not ih:
            return None
        max_w, max_h = max_w_mm * mm, max_h_mm * mm
        scale = min(max_w / iw, max_h / ih)
        return RLImage(io.BytesIO(data), width=iw * scale, height=ih * scale)
    except Exception:
        return None


def _company_block(styles, company: dict | None = None):
    # Each line needs `leading` (line height) matched to its font size, otherwise
    # the 18pt title only gets ~12pt of vertical space and the lines below it
    # render on top of it (overlap).
    company = company or _DEFAULT_COMPANY
    title_style = ParagraphStyle(
        "CompanyTitle", parent=styles["Normal"],
        fontName=FONT_BOLD, fontSize=18, leading=22, textColor=BLACK,
        spaceAfter=3,
    )
    sub_style = ParagraphStyle(
        "CompanySub", parent=styles["Normal"],
        fontSize=8, leading=11, textColor=colors.HexColor("#52525b"),
    )
    addr_style = ParagraphStyle(
        "CompanyAddr", parent=styles["Normal"],
        fontSize=8, leading=11, textColor=colors.HexColor("#71717a"),
        spaceBefore=2,
    )

    name = company.get("name") or _DEFAULT_COMPANY["name"]
    tagline = company.get("tagline")
    addr_line = company.get("address_line")
    if addr_line is None:
        # Build a sensible single-line address from a real company profile.
        bits = [company.get("address"), company.get("state")]
        gstin = company.get("gstin")
        addr_line = " · ".join([b for b in bits if b])
        if gstin:
            addr_line = (addr_line + " · " if addr_line else "") + f"GSTIN {gstin}"

    block = []
    logo = _load_logo_image(company.get("logo_url"))
    if logo is not None:
        block.append(logo)
        block.append(Spacer(1, 4))
    block.append(Paragraph(name, title_style))
    if tagline:
        block.append(Paragraph(tagline, sub_style))
    if addr_line:
        block.append(Paragraph(addr_line, addr_style))
    return block


def build_doc_pdf(doc_type: str, doc_number: str, doc: dict, party_label: str = "CUSTOMER", company: dict | None = None) -> bytes:
    """Generic builder for QUOTATION / SALES ORDER / TAX INVOICE / DISPATCH CHALLAN."""
    doc = clean_unicode(doc)
    company = clean_unicode(company) if company else None
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    styles = get_styles_with_fonts()
    story = []

    # Header table: company info | doc badge
    badge = Table(
        [
            [Paragraph(f"<font size='8'><b>{doc_type}</b></font>", styles["Normal"])],
            [Paragraph(f"<font size='14' name='{FONT_BOLD}'>{doc_number}</font>", styles["Normal"])],
        ],
        colWidths=[55 * mm],
    )
    badge.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), YELLOW),
                ("TEXTCOLOR", (0, 0), (0, -1), BLACK),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    company_block = _company_block(styles, company)
    header = Table([[company_block, badge]], colWidths=[110 * mm, 60 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header)
    story.append(Spacer(1, 6))
    story.append(Table([[""]], colWidths=[174 * mm], rowHeights=[2], style=[("BACKGROUND", (0, 0), (-1, -1), BLACK)]))
    story.append(Spacer(1, 8))

    # Bill To
    customer = doc.get("customer_name") or "—"
    created = doc.get("created_at") or datetime.now().isoformat()
    try:
        date_str = datetime.fromisoformat(created.replace("Z", "+00:00")).strftime("%d %b %Y")
    except Exception:
        date_str = created[:10]

    meta = [
        [
            Paragraph(f"<font size='7' color='#71717a'><b>{party_label.upper()}</b></font>", styles["Normal"]),
            Paragraph("<font size='7' color='#71717a'><b>DATE</b></font>", styles["Normal"]),
        ],
        [
            Paragraph(f"<font size='10'><b>{customer}</b></font>", styles["Normal"]),
            Paragraph(f"<font size='10'>{date_str}</font>", styles["Normal"]),
        ],
    ]
    meta_table = Table(meta, colWidths=[100 * mm, 70 * mm])
    meta_table.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, 0), 2), ("TOPPADDING", (0, 1), (-1, 1), 0)]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Line items
    items = doc.get("items", []) or []
    currency = doc.get("currency") or "INR"
    if items:
        rows: list[list[Any]] = [[
            Paragraph("<font color='white' size='8'><b>#</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>DESCRIPTION</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>SKU</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>QTY</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>RATE</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>GST</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>AMOUNT</b></font>", styles["Normal"]),
        ]]
        cell_style = ParagraphStyle("cell", parent=styles["Normal"], fontName=FONT_REGULAR, fontSize=9, leading=11)
        sku_style = ParagraphStyle("skucell", parent=cell_style, fontSize=8, leading=10)
        for i, it in enumerate(items, start=1):
            line = float(it.get("quantity", 0)) * float(it.get("unit_price", 0))
            rows.append([
                str(i),
                Paragraph(str(it.get("product_name", "")), cell_style),
                Paragraph(str(it.get("sku", "")), sku_style),
                str(it.get("quantity", "")),
                _money(it.get("unit_price", 0), currency),
                f"{it.get('gst_rate', 0)}%",
                _money(line, currency),
            ])
        line_table = Table(rows, colWidths=[9 * mm, 55 * mm, 30 * mm, 14 * mm, 22 * mm, 14 * mm, 30 * mm])
        line_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BLACK),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    # Plain-string cells (rate/amount) default to Helvetica, which
                    # has no rupee glyph and renders ₹ as a black box — force our
                    # Unicode-capable font on the whole table.
                    ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#d4d4d8")),
                ]
            )
        )
        story.append(line_table)

        subtotal = doc.get("subtotal", 0)
        gst = doc.get("gst_amount", 0)
        total = doc.get("total", 0)
        totals = [
            ["", Paragraph("<font size='8' color='#52525b'><b>SUBTOTAL</b></font>", styles["Normal"]), _money(subtotal, currency)],
            ["", Paragraph("<font size='8' color='#52525b'><b>GST</b></font>", styles["Normal"]), _money(gst, currency)],
            ["", Paragraph("<font size='10' color='#0a0a0a'><b>TOTAL</b></font>", styles["Normal"]), Paragraph(f"<font size='12' name='{FONT_BOLD}'>{_money(total, currency)}</font>", styles["Normal"])],
        ]
        totals_table = Table(totals, colWidths=[94 * mm, 40 * mm, 40 * mm])
        totals_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("BACKGROUND", (1, 2), (-1, 2), YELLOW),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(totals_table)

        if currency != "INR":
            rate = doc.get("exchange_rate") or 1
            story.append(Spacer(1, 4))
            story.append(
                Paragraph(
                    f"<font size='8' color='#71717a'>Exchange rate: 1 {currency} = ₹{rate:,.2f} · INR equivalent: ₹{(float(total) * float(rate)):,.2f}</font>",
                    styles["Normal"],
                )
            )

    # Dispatch-specific (vehicle, driver)
    if doc_type == "DISPATCH CHALLAN":
        story.append(Spacer(1, 10))
        d_rows = [
            [
                Paragraph("<font size='7' color='#71717a'><b>VEHICLE</b></font>", styles["Normal"]),
                Paragraph("<font size='7' color='#71717a'><b>DRIVER</b></font>", styles["Normal"]),
                Paragraph("<font size='7' color='#71717a'><b>DRIVER PHONE</b></font>", styles["Normal"]),
                Paragraph("<font size='7' color='#71717a'><b>DISPATCH DATE</b></font>", styles["Normal"]),
            ],
            [
                doc.get("vehicle_no", "—"),
                doc.get("driver_name", "—"),
                doc.get("driver_phone", "—"),
                doc.get("dispatch_date", "—"),
            ],
        ]
        d_table = Table(d_rows, colWidths=[42 * mm] * 4)
        d_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(d_table)

    if doc.get("notes"):
        story.append(Spacer(1, 12))
        story.append(Paragraph("<font size='7' color='#71717a'><b>NOTES</b></font>", styles["Normal"]))
        story.append(Paragraph(f"<font size='9'>{doc['notes']}</font>", styles["Normal"]))

    # Footer signatures
    story.append(Spacer(1, 30))
    sig_style = ParagraphStyle("sig", parent=styles["Normal"], fontSize=7, textColor=colors.HexColor("#52525b"))
    company_name = (company or {}).get("name") or _DEFAULT_COMPANY["name"]
    sig_rows = [
        [
            Paragraph(f"____________________<br/><b>{party_label.upper()} SIGNATURE</b>", sig_style),
            Paragraph(f"____________________<br/><b>FOR {company_name.upper()}</b>", sig_style),
        ]
    ]
    sig_table = Table(sig_rows, colWidths=[85 * mm, 85 * mm])
    sig_table.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    story.append(sig_table)

    pdf.build(story)
    return buf.getvalue()


def normalize_purchase_doc(doc: dict, party_field: str = "vendor") -> dict:
    if "items" in doc and "customer_name" in doc:
        return doc

    out = dict(doc)
    items = []
    for line in doc.get("lines", []):
        qty_val = line.get("qty") if line.get("qty") is not None else line.get("quantity", 0)
        rate_val = line.get("rate") if line.get("rate") is not None else line.get("unit_price", 0)
        items.append({
            "product_name": line.get("product_name") or line.get("item_name") or "",
            "hsn_code": line.get("hsn_code") or line.get("hsn_sac_code") or "",
            "quantity": qty_val if qty_val is not None else 0,
            "unit_price": rate_val if rate_val is not None else 0,
            "gst_rate": line.get("gst_rate") or 0,
        })
    out["items"] = items

    if party_field in doc:
        out["customer"] = doc[party_field]
    if f"{party_field}_name" in doc:
        out["customer_name"] = doc[f"{party_field}_name"]

    subtotal = 0.0
    gst = 0.0
    for item in items:
        qty = float(item["quantity"] or 0.0)
        price = float(item["unit_price"] or 0.0)
        rate = float(item["gst_rate"] or 0.0)
        line_val = qty * price
        subtotal += line_val
        gst += line_val * rate / 100.0

    if "subtotal" not in out:
        out["subtotal"] = round(subtotal, 2)
    if "gst_amount" not in out:
        out["gst_amount"] = round(gst, 2)
    if "total" not in out:
        out["total"] = round(subtotal + gst, 2)

    return out


def build_jobwork_pdf(challan: dict, company: dict | None = None) -> bytes:
    challan = clean_unicode(challan)
    company = clean_unicode(company) if company else None
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    styles = get_styles_with_fonts()
    story = []

    badge = Table(
        [
            [Paragraph("<font size='8'><b>JOB WORK CHALLAN</b></font>", styles["Normal"])],
            [Paragraph(f"<font size='14' name='{FONT_BOLD}'>{challan.get('challan_number', '—')}</font>", styles["Normal"])],
        ],
        colWidths=[55 * mm],
    )
    badge.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), YELLOW),
                ("TEXTCOLOR", (0, 0), (0, -1), BLACK),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    company_block = _company_block(styles, company)
    header = Table([[company_block, badge]], colWidths=[110 * mm, 60 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header)
    story.append(Spacer(1, 6))
    story.append(Table([[""]], colWidths=[174 * mm], rowHeights=[2], style=[("BACKGROUND", (0, 0), (-1, -1), BLACK)]))
    story.append(Spacer(1, 8))

    worker = challan.get("job_worker_name") or "—"
    c_date = challan.get("date") or "—"
    meta = [
        [
            Paragraph("<font size='7' color='#71717a'><b>JOB WORKER</b></font>", styles["Normal"]),
            Paragraph("<font size='7' color='#71717a'><b>DATE</b></font>", styles["Normal"]),
        ],
        [
            Paragraph(f"<font size='10'><b>{worker}</b></font>", styles["Normal"]),
            Paragraph(f"<font size='10'>{c_date}</font>", styles["Normal"]),
        ],
    ]
    meta_table = Table(meta, colWidths=[100 * mm, 70 * mm])
    meta_table.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, 0), 2), ("TOPPADDING", (0, 1), (-1, 1), 0)]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    items = challan.get("items", []) or []
    rows: list[list[Any]] = [[
        Paragraph("<font color='white' size='8'><b>#</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>PRODUCT/DESCRIPTION</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>SKU</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>QUANTITY</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>UNIT</b></font>", styles["Normal"]),
    ]]
    for i, it in enumerate(items, start=1):
        rows.append([
            str(i),
            it.get("product_name", ""),
            it.get("sku", ""),
            str(it.get("quantity", 0)),
            it.get("unit", "pcs"),
        ])
    line_table = Table(rows, colWidths=[15 * mm, 90 * mm, 30 * mm, 20 * mm, 19 * mm])
    line_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BLACK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#d4d4d8")),
            ]
        )
    )
    story.append(line_table)
    story.append(Spacer(1, 15))

    disclaimer = (
        "<b>Statutory Declaration (Section 143):</b> This challan is issued under the provisions of "
        "Section 143 of the CGST Act, 2017. The goods specified above are sent for job work and are to "
        "be returned to the principal place of business within 1 year (for inputs) or 3 years (for capital goods) "
        "of being sent out. This movement does not constitute a supply under GST, and no tax is payable on this document."
    )
    story.append(Paragraph(f"<font size='8' color='#52525b'>{disclaimer}</font>", styles["Normal"]))
    
    if challan.get("notes"):
        story.append(Spacer(1, 10))
        story.append(Paragraph("<font size='7' color='#71717a'><b>NOTES</b></font>", styles["Normal"]))
        story.append(Paragraph(f"<font size='9'>{challan['notes']}</font>", styles["Normal"]))

    story.append(Spacer(1, 30))
    sig_style = ParagraphStyle("sig", parent=styles["Normal"], fontSize=7, textColor=colors.HexColor("#52525b"))
    sig_rows = [
        [
            Paragraph("____________________<br/><b>JOB WORK WORKER ACKNOWLEDGEMENT</b>", sig_style),
            Paragraph("____________________<br/><b>AUTHORIZED SIGNATORY</b>", sig_style),
        ]
    ]
    sig_table = Table(sig_rows, colWidths=[85 * mm, 85 * mm])
    sig_table.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    story.append(sig_table)

    pdf.build(story)
    return buf.getvalue()


def build_jobwork_report_pdf(report: dict) -> bytes:
    report = clean_unicode(report)
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    styles = get_styles_with_fonts()
    story = []

    title_style = ParagraphStyle("RepTitle", parent=styles["Normal"], fontName=FONT_BOLD, fontSize=16, leading=20, spaceAfter=15)
    story.append(Paragraph("JOB WORK CONSOLIDATED REPORT", title_style))

    df = report.get("date_from") or "All time"
    dt = report.get("date_to") or "All time"
    story.append(Paragraph(f"<font size='9' color='#52525b'>Period: {df} to {dt}</font>", styles["Normal"]))
    story.append(Spacer(1, 10))

    summary = report.get("summary") or {}
    stats_data = [
        [
            Paragraph("<b>Total Challans:</b>", styles["Normal"]), str(summary.get("total_challans", 0)),
            Paragraph("<b>Total Job Workers:</b>", styles["Normal"]), str(summary.get("total_job_workers", 0)),
        ],
        [
            Paragraph("<b>Taxable Value:</b>", styles["Normal"]), _money(summary.get("total_taxable_value", 0)),
            Paragraph("<b>Total GST:</b>", styles["Normal"]), _money(summary.get("total_gst", 0)),
        ],
        [
            Paragraph("<b>Overdue Challans:</b>", styles["Normal"]), str(summary.get("overdue_challans", 0)),
            "", ""
        ]
    ]
    stats_table = Table(stats_data, colWidths=[40 * mm, 45 * mm, 40 * mm, 45 * mm])
    stats_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 15))

    story.append(Paragraph("<b>JOB WORKER SUMMARY</b>", styles["Normal"]))
    story.append(Spacer(1, 5))
    workers_rows: list[list[Any]] = [[
        Paragraph("<font color='white' size='7'><b>NAME</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='7'><b>CHALLANS</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='7'><b>QTY SENT</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='7'><b>QTY RECV</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='7'><b>PENDING</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='7'><b>VAL (TAXABLE)</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='7'><b>OVERDUE</b></font>", styles["Normal"]),
    ]]
    for w in report.get("job_workers", []):
        workers_rows.append([
            w.get("job_worker_name", ""),
            str(w.get("challans", 0)),
            str(w.get("qty_sent", 0)),
            str(w.get("qty_received", 0)),
            str(w.get("qty_pending", 0)),
            _money(w.get("taxable_value", 0)),
            str(w.get("overdue", 0)),
        ])
    w_table = Table(workers_rows, colWidths=[55 * mm, 18 * mm, 20 * mm, 20 * mm, 20 * mm, 27 * mm, 20 * mm])
    w_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLACK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#e4e4e7")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(w_table)
    story.append(Spacer(1, 15))

    story.append(Paragraph("<b>AGING OF PENDING QUANTITY</b>", styles["Normal"]))
    story.append(Spacer(1, 5))
    aging_rows: list[list[Any]] = [[
        Paragraph("<font color='white' size='7'><b>BUCKET (DAYS)</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='7'><b>PENDING QTY</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='7'><b>ESTIMATED VALUE</b></font>", styles["Normal"]),
    ]]
    for a in report.get("aging", []):
        aging_rows.append([
            a.get("bucket", ""),
            str(a.get("quantity_pending", 0)),
            _money(a.get("value_pending", 0)),
        ])
    a_table = Table(aging_rows, colWidths=[60 * mm, 60 * mm, 60 * mm])
    a_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLACK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#e4e4e7")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(a_table)

    pdf.build(story)
    return buf.getvalue()


def build_bank_statement_pdf(
    account_name: str, lines: list, from_date: str = "", to_date: str = "",
    opening_balance: float = 0.0
) -> bytes:
    account_name = clean_unicode(account_name)
    lines = clean_unicode(lines)
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    styles = get_styles_with_fonts()
    story = []

    title_style = ParagraphStyle("RepTitle", parent=styles["Normal"], fontName=FONT_BOLD, fontSize=16, leading=20, spaceAfter=15)
    story.append(Paragraph("BANK STATEMENT", title_style))
    story.append(Paragraph(f"<font size='11'><b>{account_name}</b></font>", styles["Normal"]))
    if from_date or to_date:
        story.append(Paragraph(f"<font size='8' color='#52525b'>Period: {from_date} to {to_date}</font>", styles["Normal"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph(f"<b>Opening Balance:</b> {_money(opening_balance)}", styles["Normal"]))
    story.append(Spacer(1, 10))

    rows: list[list[Any]] = [[
        Paragraph("<font color='white' size='8'><b>DATE</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>DESCRIPTION</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>REF NO</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>DEBIT (DR)</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>CREDIT (CR)</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>BALANCE</b></font>", styles["Normal"]),
    ]]
    
    current_balance = opening_balance
    for line in lines:
        deb = float(line.get("debit") or 0.0)
        crd = float(line.get("credit") or 0.0)
        current_balance += crd - deb
        rows.append([
            line.get("transaction_date") or "",
            line.get("description") or "",
            line.get("ref_number") or "",
            _money(deb) if deb else "—",
            _money(crd) if crd else "—",
            _money(current_balance),
        ])
        
    s_table = Table(rows, colWidths=[24 * mm, 60 * mm, 24 * mm, 24 * mm, 24 * mm, 24 * mm])
    s_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLACK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#e4e4e7")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(s_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph(f"<b>Closing Balance:</b> {_money(current_balance)}", styles["Normal"]))

    pdf.build(story)
    return buf.getvalue()


def build_ewaybill_pdf(ewb: dict, company: dict | None = None) -> bytes:
    ewb = clean_unicode(ewb)
    company = clean_unicode(company) if company else None
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    styles = get_styles_with_fonts()
    story = []

    badge = Table(
        [
            [Paragraph("<font size='8'><b>e-Way Bill</b></font>", styles["Normal"])],
            [Paragraph(f"<font size='14' name='{FONT_BOLD}'>{ewb.get('ewb_number', '—')}</font>", styles["Normal"])],
        ],
        colWidths=[55 * mm],
    )
    badge.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), YELLOW),
                ("TEXTCOLOR", (0, 0), (0, -1), BLACK),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    company_block = _company_block(styles, company)
    header = Table([[company_block, badge]], colWidths=[110 * mm, 60 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header)
    story.append(Spacer(1, 6))
    story.append(Table([[""]], colWidths=[174 * mm], rowHeights=[2], style=[("BACKGROUND", (0, 0), (-1, -1), BLACK)]))
    story.append(Spacer(1, 8))

    # Details: EWB Number, Date, Status
    status = ewb.get("status") or "GENERATED"
    date_str = ewb.get("ewb_date") or ewb.get("created_at") or "—"
    if len(date_str) > 10:
        date_str = date_str[:10]

    meta = [
        [
            Paragraph("<font size='7' color='#71717a'><b>e-Way Bill STATUS</b></font>", styles["Normal"]),
            Paragraph("<font size='7' color='#71717a'><b>GENERATED DATE</b></font>", styles["Normal"]),
        ],
        [
            Paragraph(f"<font size='10'><b>{status}</b></font>", styles["Normal"]),
            Paragraph(f"<font size='10'>{date_str}</font>", styles["Normal"]),
        ],
    ]
    meta_table = Table(meta, colWidths=[100 * mm, 70 * mm])
    meta_table.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, 0), 2), ("TOPPADDING", (0, 1), (-1, 1), 0)]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # From / To section
    from_name = ewb.get("from_name") or "—"
    from_gstin = ewb.get("from_gstin") or "—"
    from_place = ewb.get("from_place") or "—"
    from_addr = ewb.get("from_address") or "—"

    to_name = ewb.get("to_name") or "—"
    to_gstin = ewb.get("to_gstin") or "—"
    to_place = ewb.get("to_place") or "—"
    to_addr = ewb.get("to_address") or "—"

    from_block = [
        Paragraph("<b>FROM (CONSIGNOR)</b>", ParagraphStyle("h_from", parent=styles["Normal"], fontSize=7, textColor=colors.HexColor("#52525b"))),
        Paragraph(f"<b>{from_name}</b>", ParagraphStyle("from_n", parent=styles["Normal"], fontSize=9, fontName=FONT_BOLD)),
        Paragraph(f"GSTIN: {from_gstin}", ParagraphStyle("from_g", parent=styles["Normal"], fontSize=8)),
        Paragraph(f"Address: {from_addr}", ParagraphStyle("from_a", parent=styles["Normal"], fontSize=8)),
        Paragraph(f"Place: {from_place}", ParagraphStyle("from_p", parent=styles["Normal"], fontSize=8)),
    ]

    to_block = [
        Paragraph("<b>TO (CONSIGNEE)</b>", ParagraphStyle("h_to", parent=styles["Normal"], fontSize=7, textColor=colors.HexColor("#52525b"))),
        Paragraph(f"<b>{to_name}</b>", ParagraphStyle("to_n", parent=styles["Normal"], fontSize=9, fontName=FONT_BOLD)),
        Paragraph(f"GSTIN: {to_gstin}", ParagraphStyle("to_g", parent=styles["Normal"], fontSize=8)),
        Paragraph(f"Address: {to_addr}", ParagraphStyle("to_a", parent=styles["Normal"], fontSize=8)),
        Paragraph(f"Place: {to_place}", ParagraphStyle("to_p", parent=styles["Normal"], fontSize=8)),
    ]

    parties_table = Table([[from_block, to_block]], colWidths=[87 * mm, 87 * mm])
    parties_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d4d4d8")),
        ("LINEAFTER", (0, 0), (0, -1), 0.5, colors.HexColor("#d4d4d8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(parties_table)
    story.append(Spacer(1, 10))

    # Transport / Vehicle Details
    t_mode = ewb.get("transport_mode") or "ROAD"
    vehicle = ewb.get("vehicle_no") or ewb.get("vehicle_number") or "—"
    dist = f"{ewb.get('distance_km') or 0} km"
    trans_name = ewb.get("transporter_name") or "—"
    trans_id = ewb.get("transporter_id") or "—"

    trans_rows = [
        [
            Paragraph("<font size='7' color='#71717a'><b>TRANSPORT MODE</b></font>", styles["Normal"]),
            Paragraph("<font size='7' color='#71717a'><b>VEHICLE NO</b></font>", styles["Normal"]),
            Paragraph("<font size='7' color='#71717a'><b>DISTANCE</b></font>", styles["Normal"]),
        ],
        [
            Paragraph(f"<b>{t_mode}</b>", styles["Normal"]),
            Paragraph(f"<b>{vehicle}</b>", styles["Normal"]),
            Paragraph(f"<b>{dist}</b>", styles["Normal"]),
        ],
        [
            Paragraph("<font size='7' color='#71717a'><b>TRANSPORTER NAME</b></font>", styles["Normal"]),
            Paragraph("<font size='7' color='#71717a'><b>TRANSPORTER ID</b></font>", styles["Normal"]),
            Paragraph("", styles["Normal"]),
        ],
        [
            Paragraph(f"<b>{trans_name}</b>", styles["Normal"]),
            Paragraph(f"<b>{trans_id}</b>", styles["Normal"]),
            Paragraph("", styles["Normal"]),
        ]
    ]
    trans_table = Table(trans_rows, colWidths=[58 * mm, 58 * mm, 58 * mm])
    trans_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                ("BACKGROUND", (0, 2), (-1, 2), LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 1), (-1, 1), 0.5, colors.HexColor("#e4e4e7")),
                ("LINEBELOW", (0, 3), (-1, 3), 0.5, colors.HexColor("#e4e4e7")),
            ]
        )
    )
    story.append(trans_table)
    story.append(Spacer(1, 10))

    # Items section
    items = ewb.get("items", []) or []
    if items:
        rows: list[list[Any]] = [[
            Paragraph("<font color='white' size='8'><b>#</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>PRODUCT</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>SKU</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>QTY</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>RATE</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>GST</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>AMOUNT</b></font>", styles["Normal"]),
        ]]
        cell_style = ParagraphStyle("ecell", parent=styles["Normal"], fontName=FONT_REGULAR, fontSize=9, leading=11)
        sku_style = ParagraphStyle("eskucell", parent=cell_style, fontSize=8, leading=10)
        for i, it in enumerate(items, start=1):
            qty = float(it.get("quantity", 0))
            rate = float(it.get("unit_price", 0))
            line = qty * rate
            rows.append([
                str(i),
                Paragraph(str(it.get("product_name", "")), cell_style),
                Paragraph(str(it.get("sku", "")), sku_style),
                str(qty),
                _money(rate),
                f"{it.get('gst_rate', 0)}%",
                _money(line),
            ])
        line_table = Table(rows, colWidths=[9 * mm, 55 * mm, 30 * mm, 14 * mm, 22 * mm, 14 * mm, 30 * mm])
        line_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BLACK),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#d4d4d8")),
                ]
            )
        )
        story.append(line_table)

    total_val = ewb.get("total_invoice_value") or 0
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<b>Total Invoice Value:</b> {_money(total_val)}", ParagraphStyle("tot_val", parent=styles["Normal"], fontSize=10, fontName=FONT_BOLD)))

    pdf.build(story)
    return buf.getvalue()


init_fonts()

