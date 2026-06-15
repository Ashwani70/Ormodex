"""PDF document builder using reportlab."""
import io
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


YELLOW = colors.HexColor("#FACC15")
BLACK = colors.HexColor("#0a0a0a")
LIGHT = colors.HexColor("#f4f4f5")

CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "AED": "AED ", "EUR": "€", "GBP": "£"}


def _money(amount, currency="INR"):
    sym = CURRENCY_SYMBOLS.get(currency, "")
    try:
        return f"{sym}{float(amount):,.2f}"
    except Exception:
        return f"{sym}{amount}"


def _company_block(styles):
    # Each line needs `leading` (line height) matched to its font size, otherwise
    # the 18pt title only gets ~12pt of vertical space and the lines below it
    # render on top of it (overlap).
    title_style = ParagraphStyle(
        "CompanyTitle", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=BLACK,
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
    return [
        Paragraph("GRAVITYONE ERP", title_style),
        Paragraph("AI-POWERED BUSINESS MANAGEMENT PLATFORM", sub_style),
        Paragraph("Pune, Maharashtra · India · GSTIN 27AABCG1234F1Z5", addr_style),
    ]


def build_doc_pdf(doc_type: str, doc_number: str, doc: dict) -> bytes:
    """Generic builder for QUOTATION / SALES ORDER / TAX INVOICE / DISPATCH CHALLAN."""
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    story = []

    # Header table: company info | doc badge
    badge = Table(
        [
            [Paragraph(f"<font size='8'><b>{doc_type}</b></font>", styles["Normal"])],
            [Paragraph(f"<font size='14' name='Helvetica-Bold'>{doc_number}</font>", styles["Normal"])],
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

    company = _company_block(styles)
    header = Table([[company, badge]], colWidths=[110 * mm, 60 * mm])
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
            Paragraph("<font size='7' color='#71717a'><b>BILL TO</b></font>", styles["Normal"]),
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
        for i, it in enumerate(items, start=1):
            line = float(it.get("quantity", 0)) * float(it.get("unit_price", 0))
            rows.append([
                str(i),
                it.get("product_name", ""),
                it.get("sku", ""),
                str(it.get("quantity", "")),
                _money(it.get("unit_price", 0), currency),
                f"{it.get('gst_rate', 0)}%",
                _money(line, currency),
            ])
        line_table = Table(rows, colWidths=[10 * mm, 64 * mm, 25 * mm, 15 * mm, 22 * mm, 14 * mm, 24 * mm])
        line_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BLACK),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
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
            ["", Paragraph("<font size='10' color='#0a0a0a'><b>TOTAL</b></font>", styles["Normal"]), Paragraph(f"<font size='12' name='Helvetica-Bold'>{_money(total, currency)}</font>", styles["Normal"])],
        ]
        totals_table = Table(totals, colWidths=[100 * mm, 50 * mm, 24 * mm])
        totals_table.setStyle(
            TableStyle(
                [
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
    sig_rows = [
        [
            Paragraph("____________________<br/><b>CUSTOMER SIGNATURE</b>", sig_style),
            Paragraph("____________________<br/><b>FOR GRAVITYONE ERP</b>", sig_style),
        ]
    ]
    sig_table = Table(sig_rows, colWidths=[85 * mm, 85 * mm])
    sig_table.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    story.append(sig_table)

    pdf.build(story)
    return buf.getvalue()
