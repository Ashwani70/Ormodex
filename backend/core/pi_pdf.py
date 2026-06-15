"""Proforma Invoice PDF builder — export-grade format."""
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
    KeepTogether,
)

from .words import amount_in_words

YELLOW = colors.HexColor("#FACC15")
BLACK = colors.HexColor("#0a0a0a")
LIGHT = colors.HexColor("#f4f4f5")
BORDER = colors.HexColor("#a1a1aa")

CURRENCY_SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£", "AED": "AED ", "INR": "₹"}


def _money(amt, ccy):
    sym = CURRENCY_SYMBOL.get(ccy, "")
    try:
        return f"{sym}{float(amt):,.2f}"
    except Exception:
        return f"{sym}{amt}"


def build_pi_pdf(pi: dict) -> bytes:
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=12 * mm, bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=8.5, leading=11)
    body_bold = ParagraphStyle("bb", parent=body, fontName="Helvetica-Bold")
    label = ParagraphStyle("label", parent=body, fontSize=7, textColor=colors.HexColor("#52525b"))
    small = ParagraphStyle("small", parent=body, fontSize=7.5, leading=10)
    desc = ParagraphStyle("desc", parent=body, fontSize=8, leading=10)
    head = ParagraphStyle("head", parent=body, fontSize=18, fontName="Helvetica-Bold", leading=20)
    sub = ParagraphStyle("sub", parent=body, fontSize=8, textColor=colors.HexColor("#52525b"))

    story = []
    ccy = pi.get("currency", "USD")
    pi_number = pi.get("pi_number", "—")

    # ---------- Header banner ----------
    title = Table(
        [[
            [
                Paragraph("GRAVITYONE ERP", head),
                Paragraph(pi.get("exporter_address", "Pune, Maharashtra, India"), sub),
                Paragraph(
                    f"GSTIN: {pi.get('exporter_gstin') or '—'}{' · IEC: ' + pi['exporter_iec'] if pi.get('exporter_iec') else ''}",
                    sub,
                ),
            ],
            [
                Paragraph("PROFORMA INVOICE", ParagraphStyle("pititle", parent=body, fontSize=12, fontName="Helvetica-Bold", textColor=BLACK)),
                Paragraph(f"<b>PI No:</b> {pi_number}", body),
                Paragraph(f"<b>Date:</b> {pi.get('date') or datetime.now().strftime('%d/%m/%Y')}", body),
            ],
        ]],
        colWidths=[110 * mm, 72 * mm],
    )
    title.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (1, 0), (1, 0), YELLOW),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
    ]))
    story.append(title)
    story.append(Spacer(1, 6))

    # ---------- Buyer + Logistics ----------
    buyer_block = [
        Paragraph("<b>BUYER / CONSIGNEE</b>", label),
        Paragraph(f"<b>{pi.get('buyer_name', '—')}</b>", body_bold),
    ]
    if pi.get("buyer_address"):
        buyer_block.append(Paragraph(pi["buyer_address"].replace("\n", "<br/>"), small))
    if pi.get("buyer_country"):
        buyer_block.append(Paragraph(pi["buyer_country"], small))
    if pi.get("buyer_contact_person"):
        buyer_block.append(Paragraph(f"Contact: {pi['buyer_contact_person']}", small))
    if pi.get("buyer_email"):
        buyer_block.append(Paragraph(f"Email: {pi['buyer_email']}", small))
    if pi.get("buyer_phone"):
        buyer_block.append(Paragraph(f"Phone: {pi['buyer_phone']}", small))

    logistics_rows = [
        ["Country of Origin:", pi.get("country_of_origin", "India")],
        ["Port of Loading:", pi.get("port_of_loading", "—")],
        ["Port of Discharge:", pi.get("port_of_discharge", "—")],
        ["Final Destination:", pi.get("final_destination", "—")],
        ["Incoterms:", pi.get("incoterms", "CIF")],
        ["Currency:", ccy],
    ]
    logistics_table = Table(
        [[Paragraph(f"<b>{k}</b>", small), Paragraph(str(v or "—"), small)] for k, v in logistics_rows],
        colWidths=[30 * mm, 50 * mm],
    )
    logistics_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    info_table = Table([[buyer_block, logistics_table]], colWidths=[95 * mm, 87 * mm])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("LINEAFTER", (0, 0), (0, -1), 0.7, BORDER),
        ("LEFTPADDING", (0, 0), (0, -1), 8),
        ("LEFTPADDING", (1, 0), (1, -1), 4),
        ("RIGHTPADDING", (0, 0), (0, -1), 4),
        ("RIGHTPADDING", (1, 0), (1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 6))

    # ---------- Items ----------
    items = pi.get("items", []) or []
    header_row = [
        Paragraph("<font color='white' size='8'><b>#</b></font>", body),
        Paragraph("<font color='white' size='8'><b>CONTAINER</b></font>", body),
        Paragraph("<font color='white' size='8'><b>DESCRIPTION</b></font>", body),
        Paragraph("<font color='white' size='8'><b>WEIGHT/UNIT (KG)</b></font>", body),
        Paragraph("<font color='white' size='8'><b>QTY (PCS)</b></font>", body),
        Paragraph("<font color='white' size='8'><b>UNIT PRICE</b></font>", body),
        Paragraph("<font color='white' size='8'><b>NET WT (KG)</b></font>", body),
        Paragraph(f"<font color='white' size='8'><b>{pi.get('incoterms', 'CIF')} TOTAL</b></font>", body),
    ]
    rows: list[list[Any]] = [header_row]
    total_amount = 0.0
    total_weight = 0.0
    for i, it in enumerate(items, start=1):
        qty = float(it.get("quantity", 0) or 0)
        wpu = float(it.get("weight_per_unit", 0) or 0)
        unit = float(it.get("unit_price", 0) or 0)
        net_wt = qty * wpu
        line_total = qty * unit
        total_amount += line_total
        total_weight += net_wt
        rows.append([
            str(i),
            it.get("container_spec", "") or "",
            Paragraph(it.get("description", ""), desc),
            f"{wpu:,.2f}",
            f"{qty:,.0f}",
            _money(unit, ccy),
            f"{net_wt:,.2f}",
            _money(line_total, ccy),
        ])

    # totals row
    rows.append([
        "",
        "",
        Paragraph("<b>TOTAL</b>", body),
        "",
        "",
        "",
        f"{total_weight:,.2f}",
        Paragraph(f"<font name='Helvetica-Bold'>{_money(total_amount, ccy)}</font>", body),
    ])

    line_table = Table(
        rows,
        colWidths=[8 * mm, 20 * mm, 58 * mm, 18 * mm, 16 * mm, 22 * mm, 18 * mm, 22 * mm],
    )
    line_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLACK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 1), (1, -1), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDER),
        ("BACKGROUND", (0, -1), (-1, -1), YELLOW),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BOX", (0, 0), (-1, -1), 0.7, BLACK),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 4))

    # Amount in words
    in_words = amount_in_words(total_amount, ccy)
    story.append(
        Paragraph(
            f"<b>Total {pi.get('incoterms', 'CIF')} Price in {ccy} (in words):</b> {in_words}",
            body,
        )
    )
    story.append(Spacer(1, 8))

    # ---------- Bank + Terms ----------
    bank_lines = []
    if any([pi.get("bank_name"), pi.get("bank_account_no"), pi.get("bank_swift"), pi.get("bank_iban"), pi.get("bank_branch")]):
        bank_lines.append(Paragraph("<b>BANK DETAILS</b>", label))
        if pi.get("bank_name"):
            bank_lines.append(Paragraph(f"Bank: <b>{pi['bank_name']}</b>", small))
        if pi.get("bank_branch"):
            bank_lines.append(Paragraph(f"Branch: {pi['bank_branch']}", small))
        if pi.get("bank_account_no"):
            bank_lines.append(Paragraph(f"A/C No: {pi['bank_account_no']}", small))
        if pi.get("bank_swift"):
            bank_lines.append(Paragraph(f"SWIFT: {pi['bank_swift']}", small))
        if pi.get("bank_iban"):
            bank_lines.append(Paragraph(f"IBAN: {pi['bank_iban']}", small))
    else:
        bank_lines.append(Paragraph("<b>BANK DETAILS</b>", label))
        bank_lines.append(Paragraph("To be provided on request.", small))

    terms_lines = [Paragraph("<b>TERMS &amp; CONDITIONS</b>", label)]
    if pi.get("payment_terms"):
        terms_lines.append(Paragraph(f"<b>Payment:</b> {pi['payment_terms']}", small))
    if pi.get("delivery_time"):
        terms_lines.append(Paragraph(f"<b>Delivery:</b> {pi['delivery_time']}", small))
    if pi.get("quantity_tolerance"):
        terms_lines.append(Paragraph(f"<b>Tolerance:</b> {pi['quantity_tolerance']}", small))
    if pi.get("packing_notes"):
        terms_lines.append(Paragraph(f"<b>Packing:</b> {pi['packing_notes']}", small))
    if pi.get("freight_clause"):
        terms_lines.append(Paragraph(f"<b>Freight:</b> {pi['freight_clause']}", small))
    if pi.get("special_notes"):
        terms_lines.append(Paragraph(f"<b>Note:</b> {pi['special_notes']}", small))

    terms_table = Table([[bank_lines, terms_lines]], colWidths=[60 * mm, 122 * mm])
    terms_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("LINEAFTER", (0, 0), (0, -1), 0.7, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(terms_table)
    story.append(Spacer(1, 16))

    # ---------- Signature ----------
    sig_style = ParagraphStyle("sig", parent=body, fontSize=7, textColor=colors.HexColor("#52525b"))
    sig_rows = [
        [
            Paragraph("____________________________________<br/><b>BUYER ACCEPTANCE / SIGNATURE</b>", sig_style),
            Paragraph(
                "<para alignment='right'>For <b>GRAVITYONE ERP</b><br/><br/>____________________________________<br/><b>AUTHORISED SIGNATORY</b></para>",
                sig_style,
            ),
        ]
    ]
    sig_table = Table(sig_rows, colWidths=[91 * mm, 91 * mm])
    sig_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(KeepTogether(sig_table))

    pdf.build(story)
    return buf.getvalue()
