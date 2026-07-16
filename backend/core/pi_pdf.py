"""Proforma Invoice PDF builder — premium export-invoice layout.

Shares the same design system as the domestic GST documents (core/pdf_theme.py,
core/pdf_components.py) but keeps its own item-table/terms composition since a
PI describes an export shipment (containers, incoterms, freight, weights) —
a genuinely different shape from a GST tax invoice (HSN/GST%/CGST-SGST), not
just a relabeling. No business logic here: totals are computed the same way
the original builder did (qty * unit_price, weight = qty * weight_per_unit).
"""
import io
from datetime import datetime, timedelta
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Spacer, Paragraph

from . import pdf_theme as T
from . import pdf_components as C
from .pdf import clean_unicode, _fmt_date, _numbered_canvas_factory, _load_logo_image
from .words import amount_in_words

CURRENCY_SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£", "AED": "AED ", "INR": "₹"}


def _money(amt, ccy: str) -> str:
    sym = CURRENCY_SYMBOL.get(ccy, f"{ccy} ")
    try:
        return f"{sym}{float(amt):,.2f}"
    except Exception:
        return f"{sym}{amt}"


def _validity_date(pi: dict) -> str | None:
    """PI validity is stored as a day-count (validity_days), not a stored
    due date — compute the display date from date + validity_days."""
    date_str = pi.get("date")
    days = pi.get("validity_days")
    if not date_str or not days:
        return None
    try:
        base = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        valid_until = base + timedelta(days=int(days))
        return _fmt_date(valid_until.isoformat())
    except Exception:
        return None


def build_pi_pdf(pi: dict, company: dict | None = None) -> bytes:
    pi = clean_unicode(pi)
    company_data: dict = clean_unicode(company) if company else {}
    ccy = pi.get("currency", "USD")
    pi_number = pi.get("pi_number") or "—"
    status = pi.get("status")

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=T.PAGE_MARGIN_MM * mm,
                            rightMargin=T.PAGE_MARGIN_MM * mm,
                            topMargin=T.PAGE_MARGIN_MM * mm,
                            bottomMargin=(T.PAGE_MARGIN_MM + 4) * mm,
                            title=f"Proforma Invoice {pi_number}")
    story: list[Any] = []

    # ── Header ────────────────────────────────────────────────────────────────
    # Exporter identity: prefer live company profile, fall back to the
    # per-document exporter_* fields the PI model stores for cases where no
    # active company profile is configured.
    header_company = dict(company_data) if company_data else {}
    header_company.setdefault("name", pi.get("exporter_name"))
    header_company.setdefault("address", pi.get("exporter_address"))
    header_company.setdefault("gstin", pi.get("exporter_gstin"))

    issue_date = _fmt_date(pi.get("date")) if pi.get("date") else None
    valid_until = _validity_date(pi)
    story += C.document_header(
        header_company, "PROFORMA INVOICE", pi_number, status=status,
        issue_date=issue_date, due_date=valid_until, due_label="Valid Until",
        extra_meta=f"Currency: {ccy}",
    )

    # ── Exporter + Buyer cards ───────────────────────────────────────────────
    card_w = (C.CONTENT_W - 6 * mm) / 2
    exporter_party = {
        "address": pi.get("exporter_address"),
        "gstin": pi.get("exporter_gstin"),
        "contact_person": (f"IEC {pi['exporter_iec']}" if pi.get("exporter_iec") else None),
    }
    buyer_party = {
        "address": pi.get("buyer_address"),
        "city": pi.get("buyer_country"),
        "contact_person": pi.get("buyer_contact_person"),
        "phone": pi.get("buyer_phone"),
        "email": pi.get("buyer_email"),
    }
    left = C.party_card("EXPORTER / SUPPLIER", header_company.get("name") or "—", exporter_party, width=card_w)
    right = C.party_card("BUYER / CONSIGNEE", pi.get("buyer_name") or "—", buyer_party, width=card_w)
    story.append(C.party_card_row(left, right))
    story.append(Spacer(1, 8))

    # ── Shipment / logistics detail grid ─────────────────────────────────────
    detail_pairs = [
        ("Incoterms", pi.get("incoterms")),
        ("Country of Origin", pi.get("country_of_origin")),
        ("Port of Loading", pi.get("port_of_loading")),
        ("Port of Discharge", pi.get("port_of_discharge")),
        ("Final Destination", pi.get("final_destination")),
        ("Quantity Tolerance", pi.get("quantity_tolerance")),
    ]
    grid = C.detail_grid(detail_pairs, columns=3)
    if grid:
        story += grid
        story.append(Spacer(1, 4))

    # ── Item table ────────────────────────────────────────────────────────────
    items = pi.get("items", []) or []
    rows, totals = _build_pi_rows(items, ccy)
    if rows:
        story.append(_pi_item_table(rows))
        story.append(Spacer(1, 6))

        summary_rows = [("Total Net Weight", f"{totals['weight']:,.2f} kg")]
        tot_card = C.totals_card(summary_rows, f"{pi.get('incoterms', 'CIF')} TOTAL",
                                 _money(totals["amount"], ccy))
        story.append(C.totals_row(tot_card))
        story.append(Spacer(1, 5))

        story.append(C.amount_in_words_card(
            f"{pi.get('incoterms', 'CIF')} value in {ccy}: {amount_in_words(totals['amount'], ccy)}"
        ))
        story.append(Spacer(1, 5))

    # ── Bank details ──────────────────────────────────────────────────────────
    bank = {
        "bank_name": pi.get("bank_name"),
        "bank_account_no": pi.get("bank_account_no"),
        "bank_ifsc": pi.get("bank_swift"),  # payment_card labels this "IFSC" — SWIFT plays the same role here
        "bank_branch": pi.get("bank_branch"),
    }
    payment = C.payment_card(bank, payment_terms=pi.get("payment_terms"),
                             instructions=(f"IBAN: {pi['bank_iban']}" if pi.get("bank_iban") else None))
    if payment:
        story.append(payment)
        story.append(Spacer(1, 4))

    # ── Terms & conditions ────────────────────────────────────────────────────
    terms_bits = []
    if pi.get("delivery_time"):
        terms_bits.append(f"Delivery: {pi['delivery_time']}")
    if pi.get("packing_notes"):
        terms_bits.append(f"Packing: {pi['packing_notes']}")
    if pi.get("freight_clause"):
        terms_bits.append(f"Freight: {pi['freight_clause']}")
    if pi.get("special_notes"):
        terms_bits.append(f"Note: {pi['special_notes']}")
    terms = C.terms_card("TERMS & CONDITIONS", "  |  ".join(terms_bits)) if terms_bits else None
    if terms:
        story.append(terms)
        story.append(Spacer(1, 5))

    # ── Signature block ───────────────────────────────────────────────────────
    # A Proforma Invoice is countersigned by the buyer to accept it (unlike a
    # domestic tax invoice, which only needs the seller's authorised
    # signatory) — add that column back alongside our own signatory.
    seal = _load_logo_image(company_data.get("seal_url"), max_w_mm=20, max_h_mm=20) if company_data.get("seal_url") else None
    sig = C.signature_block(header_company.get("name") or "—", seal_flowable=seal,
                            counter_sign_label="BUYER ACCEPTANCE / SIGNATURE",
                            counter_sign_seal=True)
    story.append(sig)

    watermark_text = _watermark_for_pi_status(status)
    canvas_cls = _numbered_canvas_factory(header_company, watermark_text)
    pdf.build(story, canvasmaker=canvas_cls)
    return buf.getvalue()


def _watermark_for_pi_status(status: str | None) -> str | None:
    s = (status or "").upper()
    if s == "CANCELLED":
        return "CANCELLED"
    if s == "DRAFT":
        return "DRAFT"
    return None


def _build_pi_rows(items: list[dict], ccy: str) -> tuple[list[dict], dict]:
    rows = []
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
        rows.append({
            "sno": str(i),
            "container": it.get("container_spec") or "—",
            "description": C.table_cell_paragraph(it.get("description", "")),
            "weight_unit": f"{wpu:,.2f}",
            "qty": f"{qty:,.0f}",
            "rate": _money(unit, ccy),
            "net_weight": f"{net_wt:,.2f}",
            "amount": _money(line_total, ccy),
        })
    return rows, {"amount": total_amount, "weight": total_weight}


_PI_COLUMNS = [
    ("#", 7, "sno"),
    ("CONTAINER", 20, "container"),
    ("DESCRIPTION", None, "description"),
    ("WT/UNIT (KG)", 18, "weight_unit"),
    ("QTY (PCS)", 16, "qty"),
    ("UNIT PRICE", 22, "rate"),
    ("NET WT (KG)", 18, "net_weight"),
    ("AMOUNT", 24, "amount"),
]


def _pi_item_table(rows: list[dict]):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    fixed_mm = sum(w for _, w, _ in _PI_COLUMNS if w is not None)
    flex_mm = T.CONTENT_WIDTH_MM - fixed_mm
    col_widths = [((w if w is not None else flex_mm) * mm) for _, w, _ in _PI_COLUMNS]

    styles = C.styles()
    header_row = [Paragraph(label, styles["table_header"]) for label, _, _ in _PI_COLUMNS]
    data = [header_row]
    for r in rows:
        cells = []
        for label, _, key in _PI_COLUMNS:
            val = r.get(key, "")
            style_key = "table_cell" if label in ("#", "CONTAINER", "DESCRIPTION") else "table_cell_right"
            cells.append(val if isinstance(val, Paragraph) else Paragraph(str(val), styles[style_key]))
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
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, T.BORDER),
        ("BOX", (0, 0), (-1, -1), 0.75, T.BORDER),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), T.TABLE_ROW_ALT))
    t.setStyle(TableStyle(style))
    return t
