"""Indian-standard payroll engine + salary-slip PDF builder."""
import io
from calendar import monthrange
from datetime import date, datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from sqlalchemy import select, func, and_, or_
from .db import get_session
from .schema import Holiday, Shift, Attendance, Leave, LeaveType, Advance
from .words import amount_in_words

YELLOW = colors.HexColor("#FACC15")
BLACK = colors.HexColor("#0a0a0a")
LIGHT = colors.HexColor("#f4f4f5")
BORDER = colors.HexColor("#a1a1aa")

ESI_GROSS_LIMIT = 21000  # ESI applicable only if monthly gross ≤ ₹21,000


def _round(x: float) -> float:
    return round(x, 2)


def _r(x):
    """Render number for PDF."""
    try:
        return f"₹{float(x):,.2f}"
    except Exception:
        return f"₹{x}"


async def working_days_in_month(month: str, branch_id: Optional[str] = None, weekly_off_days: Optional[list] = None) -> dict:
    """Return total_days, weekly_offs, holidays, working_days for a given YYYY-MM."""
    y, m = (int(p) for p in month.split("-"))
    total = monthrange(y, m)[1]
    weekly_off_days = weekly_off_days or [6]  # default: Sunday off (Python weekday: Mon=0..Sun=6)
    weekly_offs = 0
    for d in range(1, total + 1):
        if date(y, m, d).weekday() in weekly_off_days:
            weekly_offs += 1
    async with get_session() as _s:
        _conds = [Holiday.holiday_date.like(f"{month}-%")]
        if branch_id:
            _conds.append(or_(Holiday.branch_id == branch_id, Holiday.branch_id.is_(None)))
        _res = await _s.execute(select(func.count()).select_from(Holiday).where(and_(*_conds)))
        holidays = _res.scalar_one()
    return {
        "total_days": total,
        "weekly_offs": weekly_offs,
        "holidays": holidays,
        "working_days": max(total - weekly_offs - holidays, 0),
    }


async def calculate_payslip(employee: dict, month: str, *, salary_structure: Optional[dict] = None) -> dict:
    """Compute payslip for an employee for the given month YYYY-MM. Pure function — no DB writes."""
    y, mo = (int(p) for p in month.split("-"))
    days_in_month = monthrange(y, mo)[1]
    # find shift weekly-offs
    shift = None
    if employee.get("shift_id"):
        async with get_session() as _s:
            _r = await _s.execute(select(Shift).where(Shift.id == employee["shift_id"]))
            _sr = _r.scalar_one_or_none()
            if _sr:
                _extra = getattr(_sr, "extra", None) or {}
                shift = {"weekly_off_days": _extra.get("weekly_off_days")}
    weekly_offs = (shift.get("weekly_off_days") if shift else None) or [6]
    if not isinstance(weekly_offs, list):
        weekly_offs = [6]

    info = await working_days_in_month(month, employee.get("branch_id"), weekly_offs)
    total_working_days = info["working_days"]

    # gather attendance for the month
    async with get_session() as _s:
        _r = await _s.execute(
            select(Attendance).where(
                and_(Attendance.employee_id == employee["id"],
                     Attendance.attendance_date.like(f"{month}-%"))
            )
        )
        # TODO: replace 0 with a.overtime_hours once the column is added to
        #       the Attendance table in schema.py and migrated in the DB.
        att = [{"status": a.status, "overtime_hours": 0} for a in _r.scalars().all()]
    present = 0.0
    ot_hours = 0.0
    for a in att:
        s = a.get("status")
        if s in ("PRESENT", "LATE"):
            present += 1
        elif s == "HALF_DAY":
            present += 0.5
        ot_hours += float(a.get("overtime_hours", 0) or 0)

    # paid leaves count as paid days
    async with get_session() as _s:
        _lr = await _s.execute(
            select(Leave).where(
                and_(Leave.employee_id == employee["id"],
                     Leave.status == "APPROVED",
                     Leave.from_date <= f"{month}-{days_in_month:02d}",
                     Leave.to_date >= f"{month}-01")
            )
        )
        leaves = [{"leave_type_id": lv.leave_type_id, "total_days": float(lv.days or 0)} for lv in _lr.scalars().all()]
        _ltr = await _s.execute(select(LeaveType))
        # Use each leave type's real paid flag so unpaid (LOP) leave deducts.
        # Defaults to paid=True for legacy rows where the flag is unset.
        leave_types = {
            lt.id: {"paid": bool(getattr(lt, "paid", True) if getattr(lt, "paid", True) is not None else True)}
            for lt in _ltr.scalars().all()
        }
    paid_leave_days = 0.0
    unpaid_leave_days = 0.0
    for lv in leaves:
        lt = leave_types.get(lv.get("leave_type_id"), {})
        td = float(lv.get("total_days", 0) or 0)
        if lt.get("paid", True):
            paid_leave_days += td
        else:
            unpaid_leave_days += td

    payable_days = present + paid_leave_days
    if payable_days > total_working_days:
        payable_days = float(total_working_days)
    factor = (payable_days / total_working_days) if total_working_days > 0 else 0.0

    ss = salary_structure or {
        "basic": float(employee.get("basic_salary", 0) or 0),
        "hra": 0, "da": 0, "conveyance": 0, "medical": 0,
        "special_allowance": 0, "other_allowance": 0,
        "pf_percent": 12.0, "enable_pf": True,
        "esi_employee_percent": 0.75, "esi_employer_percent": 3.25, "enable_esi": True,
        "professional_tax": 200, "tds_percent": 0,
        "overtime_rate_multiplier": 2.0,
    }

    basic = float(ss.get("basic", 0)) * factor
    hra = float(ss.get("hra", 0)) * factor
    da = float(ss.get("da", 0)) * factor
    conv = float(ss.get("conveyance", 0)) * factor
    med = float(ss.get("medical", 0)) * factor
    spl = float(ss.get("special_allowance", 0)) * factor
    other_allow = float(ss.get("other_allowance", 0)) * factor

    # OT: hourly basic = (full structure basic / total_working_days / 8) * multiplier
    hourly_basic = (float(ss.get("basic", 0)) / max(total_working_days, 1)) / 8 if total_working_days else 0
    ot_multiplier = float(ss.get("overtime_rate_multiplier", 2.0) or 2.0)
    ot_amount = ot_hours * hourly_basic * ot_multiplier

    earnings = {
        "basic": _round(basic),
        "hra": _round(hra),
        "da": _round(da),
        "conveyance": _round(conv),
        "medical": _round(med),
        "special_allowance": _round(spl),
        "other_allowance": _round(other_allow),
        "overtime": _round(ot_amount),
    }
    gross = _round(sum(earnings.values()))

    # Deductions
    pf = _round(basic * float(ss.get("pf_percent", 0)) / 100.0) if ss.get("enable_pf", True) else 0
    esi_emp = 0.0
    esi_employer = 0.0
    if ss.get("enable_esi", True) and gross > 0 and gross <= ESI_GROSS_LIMIT:
        esi_emp = _round(gross * float(ss.get("esi_employee_percent", 0)) / 100.0)
        esi_employer = _round(gross * float(ss.get("esi_employer_percent", 0)) / 100.0)
    pt = float(ss.get("professional_tax", 0) or 0)
    tds = _round(gross * float(ss.get("tds_percent", 0)) / 100.0)

    # Advances scheduled for recovery this month only — without the
    # recovery_month restriction every advance is recovered every month,
    # over-deducting payroll.
    async with get_session() as _s:
        _ar = await _s.execute(
            select(Advance).where(
                and_(Advance.party_id == employee["id"],
                     Advance.party_type == "employee",
                     Advance.recovery_month == month)
            )
        )
        advances = [{"amount": float(a.balance or 0)} for a in _ar.scalars().all()]
    advance_recovered = _round(sum(float(a.get("amount", 0)) for a in advances))

    deductions = {
        "pf": _round(pf),
        "esi_employee": _round(esi_emp),
        "professional_tax": _round(pt),
        "tds": _round(tds),
        "advance_recovered": _round(advance_recovered),
        "other_deduction": 0,
    }
    total_deduction = _round(sum(deductions.values()))
    net = _round(gross - total_deduction)

    return {
        "employee_id": employee["id"],
        "employee_code": employee.get("employee_code"),
        "employee_name": f"{employee.get('first_name','')} {employee.get('last_name','')}".strip(),
        "month": month,
        "total_working_days": total_working_days,
        "present_days": _round(present),
        "paid_leave_days": _round(paid_leave_days),
        "unpaid_leave_days": _round(unpaid_leave_days),
        "payable_days": _round(payable_days),
        "overtime_hours": _round(ot_hours),
        "earnings": earnings,
        "deductions": deductions,
        "gross_salary": gross,
        "total_deduction": total_deduction,
        "net_salary": net,
        "esi_employer": _round(esi_employer),
        "bonus": 0,
        "incentive": 0,
        "other_deduction_label": None,
        "amount_in_words": amount_in_words(net, "INR"),
    }


def build_payslip_pdf(payslip: dict, employee: dict, branch_name: str = "Ormodex ERP") -> bytes:
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9, leading=11)
    label = ParagraphStyle("label", parent=body, fontSize=7, textColor=colors.HexColor("#52525b"))
    head = ParagraphStyle("h", parent=body, fontSize=18, fontName="Helvetica-Bold", leading=20)

    story = []

    # Header
    month_label = datetime.strptime(payslip["month"], "%Y-%m").strftime("%B %Y")
    title_left = [
        Paragraph("GRAVITYONE ERP", head),
        Paragraph("AI-Powered Business Management Platform", label),
    ]
    title_right = [
        Paragraph("<b>SALARY SLIP</b>", ParagraphStyle("a", parent=body, fontSize=11, fontName="Helvetica-Bold")),
        Paragraph(f"For the month of <b>{month_label}</b>", body),
    ]
    header = Table([[title_left, title_right]], colWidths=[110 * mm, 70 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (1, 0), (1, 0), YELLOW),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
    ]))
    story.append(header)
    story.append(Spacer(1, 6))

    # Employee info
    emp_rows = [
        ["Employee Code", payslip.get("employee_code") or "—", "Branch", branch_name],
        ["Name", payslip.get("employee_name") or "—", "Designation", employee.get("designation") or "—"],
        ["PAN", employee.get("pan_number") or "—", "Bank A/C", employee.get("account_number") or "—"],
        ["IFSC", employee.get("ifsc_code") or "—", "Bank", employee.get("bank_name") or "—"],
    ]
    emp_tbl = Table(
        [[Paragraph(f"<b>{r[0]}</b>", label), r[1], Paragraph(f"<b>{r[2]}</b>", label), r[3]] for r in emp_rows],
        colWidths=[28 * mm, 62 * mm, 28 * mm, 62 * mm],
    )
    emp_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(emp_tbl)
    story.append(Spacer(1, 6))

    # Attendance summary
    att_rows = [[
        Paragraph("<b>Working Days</b>", label),
        Paragraph("<b>Present</b>", label),
        Paragraph("<b>Paid Leave</b>", label),
        Paragraph("<b>Unpaid Leave</b>", label),
        Paragraph("<b>Payable Days</b>", label),
        Paragraph("<b>OT Hours</b>", label),
    ], [
        str(payslip.get("total_working_days") or payslip.get("components", {}).get("total_working_days") or "—"),
        str(payslip.get("present_days") or payslip.get("components", {}).get("present_days") or "—"),
        str(payslip.get("paid_leave_days") or payslip.get("components", {}).get("paid_leave_days") or "—"),
        str(payslip.get("unpaid_leave_days") or payslip.get("components", {}).get("unpaid_leave_days") or "—"),
        str(payslip.get("payable_days") or payslip.get("components", {}).get("payable_days") or "—"),
        str(payslip.get("overtime_hours") or payslip.get("components", {}).get("overtime_hours") or "—"),
    ]]
    att_tbl = Table(att_rows, colWidths=[30 * mm] * 6)
    att_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(att_tbl)
    story.append(Spacer(1, 8))

    # Earnings & deductions side-by-side
    # Fields may be at top level (old rows) or nested in components JSONB (new rows)
    _comp = payslip.get("components") or {}
    earn = payslip.get("earnings") or _comp.get("earnings") or {}
    ded = payslip.get("deductions") or _comp.get("deductions") or {}
    _g = lambda key, d=payslip: d.get(key) or _comp.get(key) or 0
    earn_rows = [
        ["Basic", earn.get("basic", 0)],
        ["HRA", earn.get("hra", 0)],
        ["DA", earn.get("da", 0)],
        ["Conveyance", earn.get("conveyance", 0)],
        ["Medical", earn.get("medical", 0)],
        ["Special Allowance", earn.get("special_allowance", 0)],
        ["Other Allowance", earn.get("other_allowance", 0)],
        ["Overtime", earn.get("overtime", 0)],
    ]
    if _g("bonus"):
        earn_rows.append(["Bonus", _g("bonus")])
    if _g("incentive"):
        earn_rows.append(["Incentive", _g("incentive")])

    ded_rows = [
        ["PF", ded.get("pf", 0)],
        ["ESI (Employee)", ded.get("esi_employee", 0)],
        ["Professional Tax", ded.get("professional_tax", 0)],
        ["TDS", ded.get("tds", 0)],
        ["Advance Recovered", ded.get("advance_recovered", 0)],
    ]
    if ded.get("other_deduction"):
        ded_rows.append([payslip.get("other_deduction_label") or _comp.get("other_deduction_label") or "Other", ded["other_deduction"]])

    earnings_tbl = Table(
        [["EARNINGS", "Amount (₹)"]] + [[r[0], _r(r[1])] for r in earn_rows] + [["", ""]] * (max(0, len(ded_rows) - len(earn_rows))) + [["GROSS", _r(_g("gross_salary"))]],
        colWidths=[44 * mm, 32 * mm],
    )
    deductions_tbl = Table(
        [["DEDUCTIONS", "Amount (₹)"]] + [[r[0], _r(r[1])] for r in ded_rows] + [["", ""]] * (max(0, len(earn_rows) - len(ded_rows))) + [["TOTAL", _r(_g("total_deduction"))]],
        colWidths=[44 * mm, 32 * mm],
    )
    for t in (earnings_tbl, deductions_tbl):
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BLACK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), YELLOW),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("BOX", (0, 0), (-1, -1), 0.7, BLACK),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
    side = Table([[earnings_tbl, deductions_tbl]], colWidths=[80 * mm, 80 * mm])
    side.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(side)
    story.append(Spacer(1, 8))

    # Net pay block
    net_tbl = Table(
        [[Paragraph("<b>NET SALARY</b>", ParagraphStyle("n1", parent=body, fontSize=11, fontName="Helvetica-Bold")),
          Paragraph(f"<font name='Helvetica-Bold' size='14'>{_r(_g('net_salary'))}</font>", body)],
         [Paragraph("<b>In words</b>", label),
          Paragraph(payslip.get("amount_in_words", ""), body)]],
        colWidths=[110 * mm, 70 * mm],
    )
    net_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), YELLOW),
        ("BOX", (0, 0), (-1, -1), 0.7, BLACK),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(net_tbl)
    story.append(Spacer(1, 24))

    # Footer note
    story.append(Paragraph(
        "<font size='7' color='#71717a'>This is a system-generated salary slip and does not require a signature.</font>",
        body,
    ))

    pdf.build(story)
    return buf.getvalue()
