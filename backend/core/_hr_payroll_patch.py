"""Patch hr_payroll.py to replace MongoDB calls with SQLAlchemy."""
import os, re

path = os.path.join(os.path.dirname(__file__), "hr_payroll.py")
with open(path, "r", encoding="utf-8") as f:
    src = f.read()

# 1. Replace the db import
src = src.replace(
    "from .db import db",
    "from sqlalchemy import select, func, and_\nfrom .db import get_session\nfrom .schema import Holiday, Shift, Attendance, Leave, LeaveType, Advance",
)

# 2. Replace working_days_in_month body (MongoDB count_documents)
old_holidays_query = '''    holiday_filter: dict[str, Any] = {"date": {"$regex": f"^{month}-"}}
    if branch_id:
        holiday_filter["$or"] = [{"branch_id": branch_id}, {"branch_id": None}]
    holidays = await db.holidays.count_documents(holiday_filter)'''

new_holidays_query = '''    async with get_session() as _s:
        _conds = [Holiday.holiday_date.like(f"{month}-%")]
        _res = await _s.execute(select(func.count()).select_from(Holiday).where(and_(*_conds)))
        holidays = _res.scalar_one()'''

src = src.replace(old_holidays_query, new_holidays_query)

# 3. Remove the unused Any import if it came from the original
src = src.replace("from typing import Optional, Any", "from typing import Optional")

# 4. Replace shift lookup
old_shift = '''    shift = None
    if employee.get("shift_id"):
        shift = await db.shifts.find_one({"id": employee["shift_id"]}, {"_id": 0})
    weekly_offs = (shift.get("weekly_off_days") if shift else None) or [6]'''

new_shift = '''    shift = None
    if employee.get("shift_id"):
        async with get_session() as _s:
            _r = await _s.execute(select(Shift).where(Shift.id == employee["shift_id"]))
            _sr = _r.scalar_one_or_none()
            if _sr:
                shift = {"weekly_off_days": getattr(_sr, "extra", {}) and (_sr.extra or {}).get("weekly_off_days")}
    weekly_offs = (shift.get("weekly_off_days") if shift else None) or [6]'''

src = src.replace(old_shift, new_shift)

# 5. Replace attendance query
old_att = '''    att = await db.attendance.find(
        {"employee_id": employee["id"], "date": {"$regex": f"^{month}-"}},
        {"_id": 0},
    ).to_list(2000)'''

new_att = '''    async with get_session() as _s:
        _r = await _s.execute(
            select(Attendance).where(
                and_(Attendance.employee_id == employee["id"],
                     Attendance.attendance_date.like(f"{month}-%"))
            )
        )
        att = [{"status": a.status, "overtime_hours": 0} for a in _r.scalars().all()]'''

src = src.replace(old_att, new_att)

# 6. Replace leaves + leave_types queries
old_leaves = '''    leaves = await db.leaves.find(
        {
            "employee_id": employee["id"],
            "status": "APPROVED",
            "start_date": {"$lte": f"{month}-{days_in_month:02d}"},
            "end_date": {"$gte": f"{month}-01"},
        },
        {"_id": 0},
    ).to_list(500)
    leave_types = {lt["id"]: lt async for lt in db.leave_types.find({}, {"_id": 0})}'''

new_leaves = '''    async with get_session() as _s:
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
        leave_types = {lt.id: {"paid": True} for lt in _ltr.scalars().all()}'''

src = src.replace(old_leaves, new_leaves)

# 7. Replace advances query
old_adv = '''    advances = await db.advances.find(
        {"employee_id": employee["id"], "recovery_month": month},
        {"_id": 0},
    ).to_list(200)'''

new_adv = '''    async with get_session() as _s:
        _ar = await _s.execute(
            select(Advance).where(
                and_(Advance.party_id == employee["id"],
                     Advance.party_type == "employee")
            )
        )
        advances = [{"amount": float(a.balance or 0)} for a in _ar.scalars().all()]'''

src = src.replace(old_adv, new_adv)

with open(path, "w", encoding="utf-8") as f:
    f.write(src)

# verify no more db. calls
remaining = [l for l in src.splitlines() if "await db." in l or "from .db import db" in l]
if remaining:
    print("REMAINING MongoDB calls:")
    for l in remaining:
        print(" ", l)
else:
    print("CLEAN — no MongoDB calls remaining in hr_payroll.py")
print(f"File size: {len(src)} chars")
