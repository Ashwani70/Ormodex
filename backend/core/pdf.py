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

from . import pdf_theme as T_theme

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


def _company_block(styles, company: dict | None = None, col_width_mm: float = 110):
    # Returns a single-column nested Table so that all elements (logo + text)
    # stack correctly when placed inside a parent Table cell. Returning a plain
    # list caused ReportLab to render only the first item and overlap the rest.
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
        bits = [company.get("address"), company.get("state")]
        gstin = company.get("gstin")
        addr_line = " · ".join([b for b in bits if b])
        if gstin:
            addr_line = (addr_line + " · " if addr_line else "") + f"GSTIN {gstin}"

    rows = []
    logo = _load_logo_image(company.get("logo_url"))
    if logo is not None:
        rows.append([logo])
        rows.append([Spacer(1, 4)])
    rows.append([Paragraph(name, title_style)])
    if tagline:
        rows.append([Paragraph(tagline, sub_style)])
    if addr_line:
        rows.append([Paragraph(addr_line, addr_style)])

    inner = Table(rows, colWidths=[col_width_mm * mm])
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return inner


# ══════════════════════════════════════════════════════════════════════════════
# Shared "professional" document layout
#
# One reusable builder (build_document_pdf) renders every core document — GST
# invoice, purchase invoice/order, sales order, quotation, delivery challan,
# credit/debit note — with an identical, print-ready A4 layout: supplier + buyer
# identity boxes, a meta strip (numbers/dates/PO/e-way/vehicle), an item table
# with a GST split (CGST/SGST/IGST), round-off + grand total, amount in words,
# and a footer with payment terms / bank details / declaration / signatory.
# Change the design here once and every document follows it.
# ══════════════════════════════════════════════════════════════════════════════

_UNITS = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
          "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
          "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two_digit_words(n: int) -> str:
    if n < 20:
        return _UNITS[n]
    return (_TENS[n // 10] + (" " + _UNITS[n % 10] if n % 10 else "")).strip()


def _three_digit_words(n: int) -> str:
    out = ""
    if n >= 100:
        out += _UNITS[n // 100] + " Hundred"
        n %= 100
        if n:
            out += " and "
    if n:
        out += _two_digit_words(n)
    return out.strip()


def amount_in_words(amount, currency: str = "INR") -> str:
    """Convert a number to words using the Indian numbering system (lakh/crore).

    Returns e.g. "Rupees One Lakh Twenty Three Thousand Four Hundred and Fifty
    and Fifty Paise Only". Used for the mandatory 'amount in words' line on tax
    invoices. Falls back gracefully on bad input.
    """
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        return ""
    unit_name = {"INR": ("Rupees", "Paise"), "USD": ("Dollars", "Cents"),
                 "EUR": ("Euros", "Cents"), "GBP": ("Pounds", "Pence")}.get(currency, (currency, "Cents"))
    whole = int(amount)
    paise = round((amount - whole) * 100)

    if whole == 0:
        words = "Zero"
    else:
        parts = []
        crore = whole // 10_000_000
        whole %= 10_000_000
        lakh = whole // 100_000
        whole %= 100_000
        thousand = whole // 1000
        whole %= 1000
        hundred = whole
        if crore:
            parts.append(_three_digit_words(crore) + " Crore")
        if lakh:
            parts.append(_two_digit_words(lakh) + " Lakh")
        if thousand:
            parts.append(_two_digit_words(thousand) + " Thousand")
        if hundred:
            parts.append(_three_digit_words(hundred))
        words = " ".join(parts)

    result = f"{unit_name[0]} {words}"
    if paise:
        result += f" and {_two_digit_words(paise)} {unit_name[1]}"
    return result + " Only"


def _fmt_date(value) -> str:
    """Best-effort date → 'DD Mon YYYY'."""
    if not value:
        return "—"
    s = str(value)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%d %b %Y")
    except Exception:
        return s[:10]


def _party_lines(party: dict) -> list[str]:
    """Ordered display lines for a supplier/buyer identity box (skips blanks)."""
    lines: list[str] = []
    addr = party.get("billing_address") or party.get("address")
    if addr:
        lines += [ln for ln in str(addr).split("\n") if ln.strip()]
    st = party.get("state")
    sc = party.get("state_code")
    if st or sc:
        lines.append(f"State: {st or '—'}" + (f" ({sc})" if sc else ""))
    if party.get("gstin"):
        lines.append(f"GSTIN: {party['gstin']}")
    if party.get("pan"):
        lines.append(f"PAN: {party['pan']}")
    cp = party.get("contact_person")
    if cp:
        lines.append(f"Contact: {cp}")
    ph = party.get("mobile") or party.get("phone")
    if ph:
        lines.append(f"Mobile: {ph}")
    if party.get("email"):
        lines.append(f"Email: {party['email']}")
    return lines


def _party_box(styles, heading: str, name: str, party: dict, accent=BLACK) -> Table:
    """A bordered identity box (SUPPLIER / BUYER) with name + detail lines."""
    hstyle = ParagraphStyle("pbhead", parent=styles["Normal"], fontName=FONT_BOLD,
                            fontSize=7, textColor=colors.white, leading=9)
    nstyle = ParagraphStyle("pbname", parent=styles["Normal"], fontName=FONT_BOLD,
                            fontSize=10, textColor=BLACK, leading=13, spaceAfter=1)
    lstyle = ParagraphStyle("pbline", parent=styles["Normal"], fontSize=7.5,
                            textColor=colors.HexColor("#3f3f46"), leading=10)
    body: list[list[Any]] = [[Paragraph(heading, hstyle)]]
    body.append([Paragraph(name or "—", nstyle)])
    for ln in _party_lines(party):
        body.append([Paragraph(ln, lstyle)])
    t = Table(body, colWidths=[85 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), accent),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#d4d4d8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 3),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
        ("TOPPADDING", (0, 1), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _numbered_canvas_factory(company: dict | None, watermark_text: str | None):
    """Returns a Canvas subclass that defers footer/watermark drawing until
    save(), at which point the true total page count is known (two-pass
    technique — ReportLab doesn't know page count while building page 1)."""
    from reportlab.pdfgen import canvas as _canvas_mod
    from . import pdf_components as C

    class _NumberedCanvas(_canvas_mod.Canvas):
        def __init__(self, *args, **kwargs):
            _canvas_mod.Canvas.__init__(self, *args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()  # type: ignore[attr-defined]

        def save(self):
            total = len(self._saved_page_states)
            generated_at = datetime.now().strftime("%d %b %Y %H:%M")
            for i, state in enumerate(self._saved_page_states, start=1):
                self.__dict__.update(state)
                page_w = self._pagesize[0]  # type: ignore[attr-defined]
                page_h = self._pagesize[1]  # type: ignore[attr-defined]
                if watermark_text:
                    C.draw_watermark(self, page_w, page_h, watermark_text)
                C.draw_footer(self, page_w, i, total, company or {}, generated_at)
                _canvas_mod.Canvas.showPage(self)
            _canvas_mod.Canvas.save(self)

    return _NumberedCanvas


def build_document_pdf(
    *,
    doc_type: str,
    doc_number: str,
    doc: dict,
    company: dict | None = None,
    party: dict | None = None,
    party_role: str = "BUYER",
    supplier_role: str = "SUPPLIER",
) -> bytes:
    """Reusable premium layout shared by every core document type (invoices,
    orders, challans, notes). `company` is our own company profile (the
    constant supplier for sales docs, or 'our' side generally). `party` is
    the resolved counterparty (buyer for sales, supplier/vendor for
    purchase) fetched live from the master DB. Either box is populated from
    whichever side each document represents.
    """
    from . import pdf_components as C

    doc = clean_unicode(doc)
    company_data: dict = clean_unicode(company) if company else {}
    party_data: dict = clean_unicode(party) if party else {}
    currency = doc.get("currency") or "INR"
    status = doc.get("status") or doc.get("einvoice_status")

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=T_theme.PAGE_MARGIN_MM * mm,
                            rightMargin=T_theme.PAGE_MARGIN_MM * mm,
                            topMargin=T_theme.PAGE_MARGIN_MM * mm,
                            bottomMargin=(T_theme.PAGE_MARGIN_MM + 2) * mm,
                            title=f"{doc_type} {doc_number}")
    story: list[Any] = []

    # ── Header: company identity + doc title/number/badge/dates/barcode ─────────
    issue_date = _fmt_date(doc.get("date") or doc.get("invoice_date") or doc.get("challan_date") or doc.get("created_at"))
    due_date = _fmt_date(doc.get("due_date")) if doc.get("due_date") else None
    barcode = C.barcode_flowable(doc_number)
    story += C.document_header(company_data, doc_type, doc_number, status=status,
                               issue_date=issue_date, due_date=due_date, barcode_flowable=barcode)

    # ── Our Company, then Party — stacked full-width sections (not side by
    # side): Our Company always renders first, per the "Bill From" convention,
    # followed by the counterparty (Buyer/Supplier) below it. ────────────────
    party_name = party_data.get("name") or doc.get("customer_name") or "—"
    party_heading = party_role if party_role == "BUYER" else supplier_role
    story.append(C.party_card("OUR COMPANY (BILL FROM)", company_data.get("name") or "—", company_data, width=C.CONTENT_W, two_col=True))
    story.append(Spacer(1, 5))
    story.append(C.party_card(party_heading, party_name, party_data, width=C.CONTENT_W, two_col=True))
    story.append(Spacer(1, 6))

    # ── Document detail grid: only fields with a real value render ──────────────
    detail_pairs = [
        ("Date", issue_date if issue_date != "—" else None),
        ("Due Date", due_date),
        ("PO Number", doc.get("po_number") or doc.get("reference")),
        ("Vehicle No.", doc.get("vehicle_no")),
        ("Transport", doc.get("transport") or doc.get("transport_name")),
        ("E-Way Bill", doc.get("eway_bill_no") or doc.get("ewb_number")),
        ("LR/GR No.", doc.get("lr_number") or doc.get("lr_no") or doc.get("gr_number")),
        ("Place of Supply", party_data.get("place_of_supply") or doc.get("place_of_supply") or party_data.get("state")),
        ("Payment Terms", doc.get("payment_terms") or doc.get("terms_of_delivery") or doc.get("delivery_terms")),
        ("Currency", currency if currency != "INR" else None),
        ("Exchange Rate", doc.get("exchange_rate") if doc.get("exchange_rate") not in (None, 1, 1.0) else None),
        ("Driver", doc.get("driver_name")),
        ("Dispatch Date", _fmt_date(doc.get("dispatch_date")) if doc.get("dispatch_date") else None),
        ("Delivery Date", _fmt_date(doc.get("delivery_date")) if doc.get("delivery_date") else None),
    ]
    grid = C.detail_grid(detail_pairs, columns=4)
    if grid:
        story += grid
        story.append(Spacer(1, 6))

    # ── Delivery address / instructions (only when present) ─────────────────────
    del_addr = doc.get("delivery_address")
    del_instr = doc.get("delivery_instructions")
    if del_addr or del_instr:
        text_bits = []
        if del_addr:
            text_bits.append(str(del_addr).replace("\n", ", "))
        if del_instr:
            text_bits.append(str(del_instr))
        delivery = C.terms_card("DELIVERY", " — ".join(text_bits))
        if delivery:
            story.append(delivery)
            story.append(Spacer(1, 6))

    # ── Item table with GST split ────────────────────────────────────────────────
    items = doc.get("items", []) or []
    if items:
        rows, totals = _build_item_rows(items, currency, doc)
        story.append(C.item_table(rows, show_discount=totals["has_discount"]))
        story.append(Spacer(1, 6))

        # ── Totals card ───────────────────────────────────────────────────────────
        summary_rows = [("Taxable Value", _money(totals["taxable"], currency))]
        if totals["discount"]:
            summary_rows.append(("Discount", "-" + _money(totals["discount"], currency)))
        if totals["freight"]:
            summary_rows.append(("Freight", _money(totals["freight"], currency)))
        if totals["packing"]:
            summary_rows.append(("Packing Charges", _money(totals["packing"], currency)))
        if totals["inter_state"]:
            summary_rows.append(("IGST", _money(totals["igst"], currency)))
        else:
            summary_rows.append(("CGST", _money(totals["cgst"], currency)))
            summary_rows.append(("SGST", _money(totals["sgst"], currency)))
        if totals["cess"]:
            summary_rows.append(("CESS", _money(totals["cess"], currency)))
        if abs(totals["round_off"]) >= 0.01:
            summary_rows.append(("Round Off", _money(totals["round_off"], currency)))

        tot_card = C.totals_card(summary_rows, "GRAND TOTAL", _money(totals["grand"], currency))
        story.append(C.totals_row(tot_card))
        story.append(Spacer(1, 6))

        # ── Amount in words ────────────────────────────────────────────────────────
        story.append(C.amount_in_words_card(amount_in_words(totals["grand"], currency)))
        story.append(Spacer(1, 5))

    # ── Payment details ──────────────────────────────────────────────────────────
    pay_terms = doc.get("payment_terms") or doc.get("terms")
    payment = C.payment_card(company_data, payment_terms=pay_terms)
    if payment:
        story.append(payment)
        story.append(Spacer(1, 3))

    # ── Declaration (left) + Signature block (bottom-right) ─────────────────────
    # Note: deliberately NOT wrapped in KeepTogether. ReportLab's KeepTogether
    # always reports an oversized height on its first wrap() pass (by design,
    # to force Platypus to re-evaluate on a fresh frame) — for a ~30mm-tall
    # block that reliably pushes it to a lonely near-blank page even when 40mm+
    # of real space remains. A plain Table (as these components already build)
    # won't split a single row across a page break on its own, which is all the
    # protection this needs.
    declaration = company_data.get("declaration") or doc.get("declaration") or \
        "We declare that this document shows the actual particulars of the goods/services described and that all particulars are true and correct."
    sig_width_mm = 70
    terms = C.terms_card("DECLARATION", declaration, width=C.CONTENT_W - sig_width_mm * mm - 6 * mm)

    seal = _load_logo_image(company_data.get("seal_url"), max_w_mm=20, max_h_mm=20) if company_data.get("seal_url") else None
    sig = C.signature_block_corner(company_data.get("name") or "—", seal_flowable=seal, width_mm=sig_width_mm)

    story.append(C.declaration_and_signature_row(terms, sig, sig_width_mm=sig_width_mm))

    watermark_text = _watermark_for_status(status, doc)
    canvas_cls = _numbered_canvas_factory(company_data, watermark_text)
    pdf.build(story, canvasmaker=canvas_cls)
    return buf.getvalue()


def _watermark_for_status(status: str | None, doc: dict) -> str | None:
    """Only a small set of statuses get a printed watermark — everything
    else (e.g. a routine DRAFT purchase order mid-edit) stays clean."""
    if doc.get("is_copy"):
        return "COPY"
    s = (status or "").upper()
    if s in ("CANCELLED", "REJECTED"):
        return "CANCELLED"
    if s == "PAID":
        return "PAID"
    if s == "DRAFT":
        return "DRAFT"
    return None


def _build_item_rows(items: list[dict], currency: str, doc: dict) -> tuple[list[dict], dict]:
    """Shared item-row + totals computation for the new item_table component.
    Mirrors the GST math _append_item_table_with_gst used (CGST/SGST split
    for intra-state, IGST for inter-state), reading only fields that already
    exist on the documents — no new stored fields required."""
    from . import pdf_components as C

    inter_state = bool(doc.get("is_inter_state"))
    total_taxable = total_cgst = total_sgst = total_igst = total_discount = 0.0
    rows = []
    for i, it in enumerate(items, start=1):
        qty = float(it.get("quantity", 0) or 0)
        rate = float(it.get("unit_price", it.get("rate", 0)) or 0)
        discount = float(it.get("discount", 0) or 0)
        gross = qty * rate
        taxable_value = it.get("taxable_value")
        taxable = float(taxable_value) if taxable_value is not None else max(gross - discount, 0.0)
        gst_rate = float(it.get("gst_rate", 0) or 0)
        gst_amt = round(taxable * gst_rate / 100.0, 2)
        total_taxable += taxable
        total_discount += discount
        if inter_state:
            total_igst += gst_amt
        else:
            total_cgst += round(gst_amt / 2, 2)
            total_sgst += gst_amt - round(gst_amt / 2, 2)
        hsn = it.get("hsn_code") or it.get("hsn_sac_code") or it.get("hsn") or "—"
        rows.append({
            "sno": str(i),
            "description": C.table_cell_paragraph(it.get("product_name", "")),
            "hsn": str(hsn),
            "unit": it.get("unit") or "pcs",
            "qty": f"{qty:g}",
            "rate": _money(rate, currency),
            "discount": _money(discount, currency) if discount else "—",
            "taxable": _money(taxable, currency),
            "gst_rate": f"{gst_rate:g}%",
            "amount": _money(taxable + gst_amt, currency),
        })

    total_gst = round(total_cgst + total_sgst + total_igst, 2)
    freight = float(doc.get("freight_charges") or doc.get("freight") or 0)
    packing = float(doc.get("packing_charges") or 0)
    cess = float(doc.get("cess") or 0)
    pre_round = round(total_taxable + total_gst + freight + packing + cess, 2)
    stored_grand = doc.get("grand_total")
    grand = float(stored_grand) if stored_grand is not None else round(pre_round)
    round_off = round(grand - pre_round, 2)

    totals = {
        "taxable": total_taxable, "cgst": total_cgst, "sgst": total_sgst, "igst": total_igst,
        "discount": total_discount, "freight": freight, "packing": packing, "cess": cess,
        "round_off": round_off, "grand": grand, "inter_state": inter_state,
        "has_discount": total_discount > 0,
    }
    return rows, totals


def _append_meta_band(story: list, styles, pairs: list) -> None:
    """Render one bordered 6-column label/value band (dates, transport, etc.)."""
    mlabel = ParagraphStyle("ml", parent=styles["Normal"], fontSize=6.5, textColor=colors.HexColor("#71717a"))
    mval = ParagraphStyle("mv", parent=styles["Normal"], fontSize=8, fontName=FONT_BOLD, textColor=BLACK, leading=10)
    rows = [
        [Paragraph(lbl, mlabel) for lbl, _ in pairs],
        [Paragraph(str(val), mval) for _, val in pairs],
    ]
    n = len(pairs)
    table = Table(rows, colWidths=[(180 / n) * mm] * n)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d4d4d8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e4e4e7")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(table)


def _company_as_party(company: dict | None) -> dict:
    """Normalize our company profile into the party-box shape."""
    c = company or _DEFAULT_COMPANY
    return {
        "name": c.get("name"),
        "billing_address": c.get("address") or c.get("address_line"),
        "state": c.get("state"),
        "state_code": c.get("state_code"),
        "gstin": c.get("gstin"),
        "pan": c.get("pan"),
        "phone": c.get("phone"),
        "email": c.get("email"),
        "contact_person": c.get("contact_person"),
    }


def _append_item_table_with_gst(story: list, styles, doc: dict, currency: str) -> None:
    items = doc.get("items", []) or []
    if not items:
        return
    header = [
        "#", "DESCRIPTION", "HSN/SAC", "QTY", "RATE", "TAXABLE", "GST%", "AMOUNT",
    ]
    rows: list[list[Any]] = [[Paragraph(f"<font color='white' size='7.5'><b>{h}</b></font>", styles["Normal"]) for h in header]]
    cell = ParagraphStyle("c", parent=styles["Normal"], fontName=FONT_REGULAR, fontSize=8, leading=10)

    total_taxable = total_cgst = total_sgst = total_igst = 0.0
    inter_state = bool(doc.get("is_inter_state"))
    for i, it in enumerate(items, start=1):
        qty = float(it.get("quantity", 0) or 0)
        rate = float(it.get("unit_price", it.get("rate", 0)) or 0)
        taxable = float(it.get("taxable_value") if it.get("taxable_value") is not None else qty * rate)
        gst_rate = float(it.get("gst_rate", 0) or 0)
        gst_amt = round(taxable * gst_rate / 100.0, 2)
        total_taxable += taxable
        if inter_state:
            total_igst += gst_amt
        else:
            total_cgst += round(gst_amt / 2, 2)
            total_sgst += gst_amt - round(gst_amt / 2, 2)
        hsn = it.get("hsn_code") or it.get("hsn_sac_code") or it.get("hsn") or "—"
        rows.append([
            str(i),
            Paragraph(str(it.get("product_name", "")), cell),
            str(hsn),
            f"{qty:g}",
            _money(rate, currency),
            _money(taxable, currency),
            f"{gst_rate:g}%",
            _money(taxable + gst_amt, currency),
        ])
    line_table = Table(rows, colWidths=[8 * mm, 58 * mm, 20 * mm, 16 * mm, 22 * mm, 24 * mm, 12 * mm, 20 * mm])
    line_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLACK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor("#e4e4e7")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d4d4d8")),
    ]))
    story.append(line_table)

    # Totals block with CGST/SGST/IGST + round-off + grand total.
    total_gst = round(total_cgst + total_sgst + total_igst, 2)
    pre_round = round(total_taxable + total_gst, 2)
    stored_grand = doc.get("grand_total")
    grand = float(stored_grand) if stored_grand is not None else round(pre_round)
    round_off = round(grand - pre_round, 2)

    trows: list[list[Any]] = [["", "Taxable Value", _money(total_taxable, currency)]]
    if inter_state:
        trows.append(["", "IGST", _money(total_igst, currency)])
    else:
        trows.append(["", "CGST", _money(total_cgst, currency)])
        trows.append(["", "SGST", _money(total_sgst, currency)])
    if abs(round_off) >= 0.01:
        trows.append(["", "Round Off", _money(round_off, currency)])
    trows.append(["", Paragraph(f"<font size='10'><b>GRAND TOTAL</b></font>", styles["Normal"]),
                  Paragraph(f"<font size='11' name='{FONT_BOLD}'>{_money(grand, currency)}</font>", styles["Normal"])])
    totals = Table(trows, colWidths=[100 * mm, 40 * mm, 40 * mm])
    totals.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR), ("FONTSIZE", (1, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BACKGROUND", (1, -1), (-1, -1), YELLOW),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEABOVE", (1, -1), (-1, -1), 0.5, BLACK),
    ]))
    story.append(totals)


def _append_document_footer(story: list, styles, doc: dict, company: dict | None) -> None:
    company = company or {}
    small = ParagraphStyle("f", parent=styles["Normal"], fontSize=7.5, textColor=colors.HexColor("#3f3f46"), leading=10)
    head = ParagraphStyle("fh", parent=styles["Normal"], fontSize=7, fontName=FONT_BOLD, textColor=colors.HexColor("#71717a"))

    # Payment terms (stored per-document; falls back to a dash).
    pay_terms = doc.get("payment_terms") or doc.get("terms") or "—"
    bank_bits = []
    if company.get("bank_name"):
        bank_bits.append(f"Bank: {company['bank_name']}")
    if company.get("bank_account_no"):
        bank_bits.append(f"A/C: {company['bank_account_no']}")
    if company.get("bank_ifsc"):
        bank_bits.append(f"IFSC: {company['bank_ifsc']}")
    if company.get("bank_branch"):
        bank_bits.append(f"Branch: {company['bank_branch']}")

    story.append(Spacer(1, 10))
    left_cells: list[Any] = [Paragraph("PAYMENT TERMS", head), Paragraph(str(pay_terms), small), Spacer(1, 4)]
    if bank_bits:
        left_cells += [Paragraph("BANK DETAILS", head), Paragraph(" · ".join(bank_bits), small), Spacer(1, 4)]
    declaration = company.get("declaration") or doc.get("declaration") or \
        "We declare that this document shows the actual particulars of the goods/services described and that all particulars are true and correct."
    left_cells += [Paragraph("DECLARATION", head), Paragraph(declaration, small)]
    left_col = Table([[c] for c in left_cells], colWidths=[110 * mm])
    left_col.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                  ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))

    sig_style = ParagraphStyle("sig", parent=styles["Normal"], fontSize=7.5, textColor=colors.HexColor("#3f3f46"))
    company_name = company.get("name") or _DEFAULT_COMPANY["name"]

    # Company seal: use the uploaded seal image when present, else a labelled
    # placeholder ring so the seal area is always reserved on the printed doc.
    seal = _load_logo_image(company.get("seal_url"), max_w_mm=24, max_h_mm=24) if company.get("seal_url") else None
    if seal is not None:
        seal_cell: Any = seal
    else:
        seal_style = ParagraphStyle("seal", parent=styles["Normal"], fontSize=6,
                                    textColor=colors.HexColor("#a1a1aa"), alignment=2)
        seal_cell = Paragraph("(Company Seal)", seal_style)

    sig_col = Table([
        [Paragraph(f"For <b>{company_name}</b>", sig_style)],
        [seal_cell],
        [Spacer(1, 8)],
        [Paragraph("_____________________________", sig_style)],
        [Paragraph("<b>Authorised Signatory</b>", sig_style)],
    ], colWidths=[60 * mm])
    sig_col.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))

    footer = Table([[left_col, sig_col]], colWidths=[112 * mm, 62 * mm])
    footer.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(footer)


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
        # colWidths: 9+50+20+25+13+20+13+24 = 174mm
        rows: list[list[Any]] = [[
            Paragraph("<font color='white' size='8'><b>#</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>DESCRIPTION</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>HSN/SAC</b></font>", styles["Normal"]),
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
            hsn = it.get("hsn_code") or it.get("hsn_sac_code") or it.get("hsn") or "—"
            rows.append([
                str(i),
                Paragraph(str(it.get("product_name", "")), cell_style),
                hsn,
                Paragraph(str(it.get("sku", "")), sku_style),
                str(it.get("quantity", "")),
                _money(it.get("unit_price", 0), currency),
                f"{it.get('gst_rate', 0)}%",
                _money(line, currency),
            ])
        line_table = Table(rows, colWidths=[9 * mm, 50 * mm, 20 * mm, 25 * mm, 13 * mm, 20 * mm, 13 * mm, 24 * mm])
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
                    ("ALIGN", (4, 1), (-1, -1), "RIGHT"),  # QTY col onwards right-aligned (col 4 after HSN added)
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
            "sku": line.get("sku") or line.get("item_code") or "",
            "hsn_code": line.get("hsn_code") or line.get("hsn_sac_code") or line.get("hsn") or "",
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
    """Job Work Challan (Outward) — built on the shared _party_box/
    _append_meta_band helpers (same visual language as every other document
    in the app) with job-work-specific additions layered on top: no GST/
    pricing columns (a §143 challan is not a supply), the statutory
    disclaimer, and dual signature lines (job-worker acknowledgement +
    receiver's signature, distinct from our own authorized signatory)."""
    challan = clean_unicode(challan)
    company = clean_unicode(company) if company else None
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Job Work Challan {challan.get('challan_number', '')}")
    styles = get_styles_with_fonts()
    story: list[Any] = []

    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.barcode.code128 import Code128

    # ── Header: company identity + QR + barcode + badge ─────────────────────
    badge = Table(
        [[Paragraph("<font size='9'><b>JOB WORK CHALLAN</b></font>", styles["Normal"])],
         [Paragraph(f"<font size='13' name='{FONT_BOLD}'>{challan.get('challan_number', '—')}</font>", styles["Normal"])]],
        colWidths=[50 * mm],
    )
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), YELLOW), ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#eab308")),
    ]))

    item_summaries = [
        f"{it.get('product_name', '')[:10]} ({it.get('quantity', 0)} {it.get('uom', 'pcs')})"
        for it in (challan.get("items", []) or [])
    ]
    qr_text = (
        f"challan={challan.get('challan_number', '—')};date={challan.get('date', '—')};"
        f"due={challan.get('due_date', '—')};worker={challan.get('job_worker_name', '—')};"
        f"items={len(item_summaries)}"
    )
    qr_size = 32 * mm
    qr = QrCodeWidget(value=qr_text)
    qr.barWidth = qr_size
    qr.barHeight = qr_size
    qr_drawing = Drawing(qr_size, qr_size)
    qr_drawing.add(qr)

    # Code128 is itself a Flowable (unlike QrCodeWidget, which is a Shape that
    # needs a Drawing container) — it goes straight into the table cell.
    barcode = Code128(challan.get("challan_number", "") or "—", barHeight=8 * mm, barWidth=0.35)

    codes_col = Table([[qr_drawing], [Spacer(1, 4)], [barcode]], colWidths=[50 * mm])
    codes_col.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))

    header = Table([[_company_block(styles, company, col_width_mm=90), codes_col, badge]],
                   colWidths=[90 * mm, 40 * mm, 50 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header)
    story.append(Spacer(1, 4))
    story.append(Table([[""]], colWidths=[180 * mm], rowHeights=[2],
                       style=[("BACKGROUND", (0, 0), (-1, -1), BLACK)]))
    story.append(Spacer(1, 8))

    # ── Job Worker (party) box + our company box ─────────────────────────────
    jw_party = {
        "address": challan.get("address"),
        "gstin": challan.get("job_worker_gstin"),
        "contact_person": challan.get("contact_person"),
        "mobile": challan.get("mobile"),
    }
    supplier_side = _company_as_party(company)
    left = _party_box(styles, "JOB WORKER", challan.get("job_worker_name") or "—", jw_party)
    right = _party_box(styles, "PRINCIPAL (US)", supplier_side.get("name") or "—", supplier_side, accent=colors.HexColor("#3f3f46"))
    boxes = Table([[left, "", right]], colWidths=[85 * mm, 10 * mm, 85 * mm])
    boxes.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(boxes)
    story.append(Spacer(1, 8))

    # ── Meta band: date / due date ────────────────────────────────────────────
    due_date = challan.get("due_date") or "—"
    core_pairs = [
        ("DATE", challan.get("date") or "—"),
        ("DUE DATE", due_date),
        ("NATURE", (challan.get("nature") or "inputs").replace("_", " ").title()),
        ("STATUS", challan.get("status") or "—"),
    ]
    _append_meta_band(story, styles, core_pairs)

    # ── Transport band (Vehicle/Driver/Transport/LR/E-Way Bill) ──────────────
    transport_pairs = [
        ("VEHICLE NO.", challan.get("vehicle_no") or "—"),
        ("DRIVER", challan.get("driver_name") or "—"),
        ("TRANSPORT", challan.get("transport") or "—"),
        ("LR NO.", challan.get("lr_number") or "—"),
        ("E-WAY BILL NO.", challan.get("eway_bill_number") or "—"),
    ]
    story.append(Spacer(1, 4))
    _append_meta_band(story, styles, transport_pairs)
    story.append(Spacer(1, 8))

    # ── Material grid — no GST/pricing columns (not a supply) ─────────────────
    items = challan.get("items", []) or []
    rows: list[list[Any]] = [[
        Paragraph("<font color='white' size='8'><b>#</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>ITEM CODE</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>PRODUCT/DESCRIPTION</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>HSN</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>SENT QTY</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>UOM</b></font>", styles["Normal"]),
    ]]
    for i, it in enumerate(items, start=1):
        hsn = it.get("hsn_code") or "—"
        rows.append([
            str(i),
            Paragraph(it.get("sku") or "—", styles["Normal"]),
            Paragraph(it.get("product_name", ""), styles["Normal"]),
            hsn,
            str(it.get("quantity", 0)),
            it.get("uom", "pcs"),
        ])
    line_table = Table(rows, colWidths=[8 * mm, 32 * mm, 82 * mm, 20 * mm, 20 * mm, 18 * mm])
    line_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLACK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#d4d4d8")),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 12))

    if challan.get("process_name"):
        story.append(Paragraph(f"<font size='8' color='#52525b'><b>Process:</b> {challan['process_name']}</font>", styles["Normal"]))
    if challan.get("instructions"):
        story.append(Paragraph(f"<font size='8' color='#52525b'><b>Instructions:</b> {challan['instructions']}</font>", styles["Normal"]))
    if challan.get("notes"):
        story.append(Paragraph(f"<font size='8' color='#52525b'><b>Notes:</b> {challan['notes']}</font>", styles["Normal"]))
    story.append(Spacer(1, 8))

    disclaimer = (
        "<b>Statutory Declaration (Section 143):</b> This challan is issued under the provisions of "
        "Section 143 of the CGST Act, 2017. The goods specified above are sent for job work and are to "
        "be returned to the principal place of business within 1 year (for inputs) or 3 years (for capital goods) "
        "of being sent out. This movement does not constitute a supply under GST, and no tax is payable on this document."
    )
    story.append(Paragraph(f"<font size='7.5' color='#52525b'>{disclaimer}</font>", styles["Normal"]))

    terms_text = (
        "1. The goods sent herewith are for job work under Section 143 of the CGST Act, 2017 and are not a supply.<br/>"
        "2. The job worker must return the processed goods within 1 year of issue (or 3 years for capital goods).<br/>"
        "3. Any wastage/scrap generated must be either returned or tax paid on it by the job worker."
    )
    story.append(Spacer(1, 6))
    story.append(Paragraph("<font size='7' color='#71717a'><b>TERMS & CONDITIONS</b></font>", styles["Normal"]))
    story.append(Paragraph(f"<font size='7' color='#71717a'>{terms_text}</font>", styles["Normal"]))

    # ── Sign-off: Prepared / Checked / three signature lines ─────────────────
    story.append(Spacer(1, 14))
    prep_bits = []
    if challan.get("prepared_by"):
        prep_bits.append(f"Prepared By: {challan['prepared_by']}")
    if challan.get("checked_by"):
        prep_bits.append(f"Checked By: {challan['checked_by']}")
    if prep_bits:
        story.append(Paragraph(f"<font size='7.5' color='#71717a'>{' · '.join(prep_bits)}</font>", styles["Normal"]))
        story.append(Spacer(1, 10))

    sig_style = ParagraphStyle("sig", parent=styles["Normal"], fontSize=7, textColor=colors.HexColor("#52525b"))
    sig_rows = [[
        Paragraph("____________________<br/><b>JOB WORKER ACKNOWLEDGEMENT</b>", sig_style),
        Paragraph("____________________<br/><b>RECEIVER'S SIGNATURE</b>", sig_style),
        Paragraph("____________________<br/><b>AUTHORIZED SIGNATORY</b>", sig_style),
    ]]
    sig_table = Table(sig_rows, colWidths=[60 * mm, 60 * mm, 60 * mm])
    sig_table.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "CENTER"), ("ALIGN", (2, 0), (2, 0), "RIGHT")]))
    story.append(sig_table)

    pdf.build(story)
    return buf.getvalue()


def build_jobwork_receipt_pdf(receipt: dict, challan: dict | None = None, company: dict | None = None) -> bytes:
    """Job Work Receipt (Inward) — built on the shared _party_box/
    _append_meta_band helpers. Distinct document from the Challan: shows
    Received/Accepted/Rejected/Scrap, never Sent-side pricing."""
    receipt = clean_unicode(receipt)
    challan_data: dict = clean_unicode(challan) if challan else {}
    company = clean_unicode(company) if company else None
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Job Work Receipt {receipt.get('receipt_number', '')}")
    styles = get_styles_with_fonts()
    story: list[Any] = []

    badge = Table(
        [[Paragraph("<font size='9'><b>MATERIAL INWARD RECEIPT</b></font>", styles["Normal"])],
         [Paragraph(f"<font size='13' name='{FONT_BOLD}'>{receipt.get('receipt_number', '—')}</font>", styles["Normal"])]],
        colWidths=[60 * mm],
    )
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), YELLOW), ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#eab308")),
    ]))
    header = Table([[_company_block(styles, company, col_width_mm=120), badge]], colWidths=[120 * mm, 60 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header)
    story.append(Spacer(1, 4))
    story.append(Table([[""]], colWidths=[180 * mm], rowHeights=[2],
                       style=[("BACKGROUND", (0, 0), (-1, -1), BLACK)]))
    story.append(Spacer(1, 8))

    jw_party = {
        "gstin": challan_data.get("job_worker_gstin"),
        "contact_person": challan_data.get("contact_person"),
        "mobile": challan_data.get("mobile"),
    }
    supplier_side = _company_as_party(company)
    left = _party_box(styles, "JOB WORKER", challan_data.get("job_worker_name") or "—", jw_party)
    right = _party_box(styles, "PRINCIPAL (US)", supplier_side.get("name") or "—", supplier_side, accent=colors.HexColor("#3f3f46"))
    boxes = Table([[left, "", right]], colWidths=[85 * mm, 10 * mm, 85 * mm])
    boxes.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(boxes)
    story.append(Spacer(1, 8))

    core_pairs = [
        ("RECEIPT DATE", receipt.get("date") or "—"),
        ("AGAINST CHALLAN", challan_data.get("challan_number") or "—"),
        ("CHALLAN DATE", challan_data.get("date") or "—"),
    ]
    _append_meta_band(story, styles, core_pairs)
    story.append(Spacer(1, 8))

    items = receipt.get("items", []) or []
    rows: list[list[Any]] = [[
        Paragraph("<font color='white' size='8'><b>#</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>PRODUCT</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>SKU</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>RECEIVED</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>ACCEPTED</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>REJECTED</b></font>", styles["Normal"]),
        Paragraph("<font color='white' size='8'><b>SCRAP</b></font>", styles["Normal"]),
    ]]
    for i, it in enumerate(items, start=1):
        rows.append([
            str(i),
            Paragraph(it.get("product_name", ""), styles["Normal"]),
            it.get("sku", "") or "—",
            str(it.get("quantity_received", 0)),
            str(it.get("accepted_quantity", 0) or 0),
            str(it.get("rejected_quantity", 0) or 0),
            str(it.get("scrap_quantity", 0) or 0),
        ])
    line_table = Table(rows, colWidths=[8 * mm, 62 * mm, 30 * mm, 20 * mm, 20 * mm, 20 * mm, 20 * mm])
    line_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLACK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#d4d4d8")),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 12))

    if receipt.get("notes"):
        story.append(Paragraph("<font size='7' color='#71717a'><b>NOTES</b></font>", styles["Normal"]))
        story.append(Paragraph(f"<font size='9'>{receipt['notes']}</font>", styles["Normal"]))
        story.append(Spacer(1, 10))

    story.append(Spacer(1, 16))
    sig_style = ParagraphStyle("sig", parent=styles["Normal"], fontSize=7, textColor=colors.HexColor("#52525b"))
    sig_rows = [[
        Paragraph("____________________<br/><b>RECEIVED BY (STORES)</b>", sig_style),
        Paragraph("____________________<br/><b>AUTHORIZED SIGNATORY</b>", sig_style),
    ]]
    sig_table = Table(sig_rows, colWidths=[90 * mm, 90 * mm])
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
        # colWidths: 9+45+20+25+13+20+13+24 = 169mm (slightly narrower — parties table is 87+87=174)
        rows: list[list[Any]] = [[
            Paragraph("<font color='white' size='8'><b>#</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>PRODUCT</b></font>", styles["Normal"]),
            Paragraph("<font color='white' size='8'><b>HSN/SAC</b></font>", styles["Normal"]),
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
            hsn = it.get("hsn_code") or it.get("hsn_sac_code") or it.get("hsn") or "—"
            rows.append([
                str(i),
                Paragraph(str(it.get("product_name", "")), cell_style),
                hsn,
                Paragraph(str(it.get("sku", "")), sku_style),
                str(qty),
                _money(rate),
                f"{it.get('gst_rate', 0)}%",
                _money(line),
            ])
        line_table = Table(rows, colWidths=[9 * mm, 50 * mm, 20 * mm, 25 * mm, 13 * mm, 20 * mm, 13 * mm, 24 * mm])
        line_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BLACK),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
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

