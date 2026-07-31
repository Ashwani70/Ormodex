"""HR Attendance + QR check-in + Biometric webhook + Leaves + Advances."""
from datetime import datetime, date
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException

from core.auth_utils import get_current_user, require_hr_or_admin, bypasses_row_ownership
from core.db import db
from core.hr_models import (
    Advance,
    AttendanceBulkIn,
    BiometricPunch,
    CheckInOut,
    Leave,
    LeaveDecision,
)
from core.utils import crud_create, crud_delete, crud_get, crud_list, crud_update, new_id, now_iso

router = APIRouter(prefix="/hr", tags=["hr-attendance"])


# ---------- Helpers ----------
def _today_iso() -> str:
    return date.today().isoformat()


def _now_hhmm() -> str:
    return datetime.now().strftime("%H:%M")


def _compute_hours(check_in: Optional[str], check_out: Optional[str]) -> float:
    if not (check_in and check_out):
        return 0.0
    try:
        a = datetime.strptime(check_in, "%H:%M")
        b = datetime.strptime(check_out, "%H:%M")
        diff = (b - a).total_seconds() / 3600
        return round(max(diff, 0.0), 2)
    except Exception:
        return 0.0


async def _resolve_shift(employee: dict) -> dict:
    sid = employee.get("shift_id")
    if sid:
        s = await db.shifts.find_one({"id": sid}, {"_id": 0})
        if s:
            return s
    return {"start_time": "09:00", "end_time": "18:00", "full_day_hours": 8, "half_day_hours": 4, "late_grace_min": 10}


def _is_late(check_in: str, shift: dict) -> bool:
    try:
        ci = datetime.strptime(check_in, "%H:%M")
        s_start = datetime.strptime(shift.get("start_time", "09:00"), "%H:%M")
        grace = int(shift.get("late_grace_min", 10))
        return (ci - s_start).total_seconds() / 60 > grace
    except Exception:
        return False


async def _employee_from_user(user: dict) -> dict:
    emp = await db.employees.find_one({"user_id": user["id"]}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="No employee record linked to this account")
    return emp


def _has_hr_access(user: dict) -> bool:
    """Full HR visibility: admin/super_admin/manager (bypasses_row_ownership),
    the dedicated "hr" role, or anyone explicitly granted the "hr" module
    permission. Anyone else only ever sees their OWN attendance regardless of
    what employee_id they pass — see list_attendance/attendance_check_in/
    attendance_check_out below."""
    return (
        bypasses_row_ownership(user.get("role"))
        or user.get("role") == "hr"
        or "hr" in (user.get("module_permissions") or [])
    )


# ---------- Attendance (HR view) ----------
@router.get("/attendance")
async def list_attendance(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    employee_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    filt = {}
    if date_from and date_to:
        filt["date"] = {"$gte": date_from, "$lte": date_to}
    elif date_from:
        filt["date"] = {"$gte": date_from}
    elif date_to:
        filt["date"] = {"$lte": date_to}
    if _has_hr_access(user):
        if employee_id:
            filt["employee_id"] = employee_id
    else:
        # Never trust a client-supplied employee_id here — force-scope to the
        # caller's OWN linked employee record regardless of what was passed.
        emp = await db.employees.find_one({"user_id": user["id"]}, {"_id": 0, "id": 1})
        if not emp:
            return []
        filt["employee_id"] = emp["id"]
    rows = await db.attendance.find(filt, {"_id": 0}).sort([("date", -1), ("employee_id", 1)]).to_list(5000)
    # enrich with names
    ids = list({r["employee_id"] for r in rows})
    emap = {
        e["id"]: f"{e.get('first_name','')} {e.get('last_name','')}".strip() + f" ({e.get('employee_code','')})"
        for e in await db.employees.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "employee_code": 1}).to_list(2000)
    }
    for r in rows:
        r["employee_name"] = emap.get(r["employee_id"], "-")
    return rows


async def _upsert_attendance(*, employee_id: str, d: str, patch: dict) -> dict:
    """Idempotent attendance upsert per (employee_id, date)."""
    existing = await db.attendance.find_one({"employee_id": employee_id, "date": d}, {"_id": 0})
    if existing:
        merged: dict[str, Any] = {**existing, **patch}
        merged["working_hours"] = _compute_hours(merged.get("check_in"), merged.get("check_out"))
        merged["updated_at"] = now_iso()
        await db.attendance.update_one({"employee_id": employee_id, "date": d}, {"$set": merged})
        return merged
    new: dict[str, Any] = {
        "id": new_id(),
        "employee_id": employee_id,
        "date": d,
        "status": "PRESENT",
        "working_hours": 0,
        "overtime_hours": 0,
        "source": "manual",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        **patch,
    }
    new["working_hours"] = _compute_hours(new.get("check_in"), new.get("check_out"))
    await db.attendance.insert_one(new)
    new.pop("_id", None)
    return new


async def _resolve_checkin_employee_id(payload_employee_id: str, user: dict) -> str:
    """HR/admin/manager may check in/out on behalf of any employee (payload
    value trusted, matching this endpoint's existing manual-entry purpose).
    Anyone else can only ever check themselves in/out — a client-supplied
    employee_id for someone else is silently overridden, never trusted."""
    if _has_hr_access(user):
        return payload_employee_id
    emp = await _employee_from_user(user)
    return emp["id"]


@router.post("/attendance/check-in")
async def attendance_check_in(payload: CheckInOut, user: dict = Depends(get_current_user)):
    employee_id = await _resolve_checkin_employee_id(payload.employee_id, user)
    emp = await crud_get("employees", employee_id)
    shift = await _resolve_shift(emp)
    ts = payload.timestamp or _now_hhmm()
    status = "LATE" if _is_late(ts, shift) else "PRESENT"
    return await _upsert_attendance(
        employee_id=employee_id,
        d=_today_iso(),
        patch={"check_in": ts, "status": status, "source": "manual"},
    )


@router.post("/attendance/check-out")
async def attendance_check_out(payload: CheckInOut, user: dict = Depends(get_current_user)):
    employee_id = await _resolve_checkin_employee_id(payload.employee_id, user)
    ts = payload.timestamp or _now_hhmm()
    return await _upsert_attendance(
        employee_id=employee_id,
        d=_today_iso(),
        patch={"check_out": ts},
    )


@router.post("/attendance/bulk")
async def attendance_bulk(payload: AttendanceBulkIn, _: dict = Depends(require_hr_or_admin)):
    """Same idempotent per-(employee_id, date) upsert semantics as
    _upsert_attendance, batched: one query to find which rows already exist
    for this date, then ONE bulk_update_by_id for the existing ones and ONE
    chunked insert_many for the new ones — instead of an insert_one/
    update_one pair per employee inside a loop (was up to hundreds of round
    trips for a full day's attendance sheet).
    """
    employee_ids = [row.employee_id for row in payload.rows]
    existing_rows = await db.attendance.find(
        {"employee_id": {"$in": employee_ids}, "date": payload.date}, {"_id": 0}
    ).to_list(len(employee_ids)) if employee_ids else []
    existing_by_employee = {r["employee_id"]: r for r in existing_rows}

    updates_by_id: dict = {}
    new_rows: list = []
    saved = []
    for row in payload.rows:
        patch = {
            "status": row.status,
            "check_in": row.check_in,
            "check_out": row.check_out,
            "overtime_hours": row.overtime_hours,
            "remarks": row.remarks,
            "source": "manual",
        }
        existing = existing_by_employee.get(row.employee_id)
        if existing:
            merged: dict[str, Any] = {**existing, **patch}
            merged["working_hours"] = _compute_hours(merged.get("check_in"), merged.get("check_out"))
            merged["updated_at"] = now_iso()
            updates_by_id[existing["id"]] = {"$set": merged}
            saved.append(merged)
        else:
            new_row: dict[str, Any] = {
                "id": new_id(),
                "employee_id": row.employee_id,
                "date": payload.date,
                "status": "PRESENT",
                "working_hours": 0,
                "overtime_hours": 0,
                "source": "manual",
                "created_at": now_iso(),
                "updated_at": now_iso(),
                **patch,
            }
            new_row["working_hours"] = _compute_hours(new_row.get("check_in"), new_row.get("check_out"))
            new_rows.append(new_row)
            saved.append(new_row)

    if updates_by_id:
        await db.attendance.bulk_update_by_id(updates_by_id)
    for i in range(0, len(new_rows), 500):
        await db.attendance.insert_many(new_rows[i:i + 500])

    return {"saved": len(saved)}


@router.delete("/attendance/{item_id}")
async def delete_attendance(item_id: str, _: dict = Depends(require_hr_or_admin)):
    return await crud_delete("attendance", item_id)


# ---------- Self-service ----------
@router.get("/me/attendance")
async def my_attendance(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    emp = await _employee_from_user(user)
    filt = {"employee_id": emp["id"]}
    if date_from and date_to:
        filt["date"] = {"$gte": date_from, "$lte": date_to}
    return await db.attendance.find(filt, {"_id": 0}).sort("date", -1).to_list(500)


@router.post("/me/attendance/check-in")
async def my_check_in(user: dict = Depends(get_current_user)):
    emp = await _employee_from_user(user)
    shift = await _resolve_shift(emp)
    ts = _now_hhmm()
    status = "LATE" if _is_late(ts, shift) else "PRESENT"
    return await _upsert_attendance(
        employee_id=emp["id"],
        d=_today_iso(),
        patch={"check_in": ts, "status": status, "source": "self"},
    )


@router.post("/me/attendance/check-out")
async def my_check_out(user: dict = Depends(get_current_user)):
    emp = await _employee_from_user(user)
    return await _upsert_attendance(
        employee_id=emp["id"],
        d=_today_iso(),
        patch={"check_out": _now_hhmm()},
    )


# ---------- QR check-in (public) ----------
@router.get("/qr/{token}/info")
async def qr_info(token: str):
    emp = await db.employees.find_one(
        {"qr_token": token, "status": "active"},
        {"_id": 0, "first_name": 1, "last_name": 1, "employee_code": 1, "id": 1},
    )
    if not emp:
        raise HTTPException(status_code=404, detail="Invalid QR token")
    return emp


@router.post("/qr/{token}/check-in")
async def qr_check_in(token: str):
    emp = await db.employees.find_one({"qr_token": token, "status": "active"}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Invalid QR token")
    shift = await _resolve_shift(emp)
    ts = _now_hhmm()
    status = "LATE" if _is_late(ts, shift) else "PRESENT"
    rec = await _upsert_attendance(
        employee_id=emp["id"],
        d=_today_iso(),
        patch={"check_in": ts, "status": status, "source": "qr"},
    )
    return {"ok": True, "attendance": rec, "employee_name": f"{emp.get('first_name','')} {emp.get('last_name','')}"}


@router.post("/qr/{token}/check-out")
async def qr_check_out(token: str):
    emp = await db.employees.find_one({"qr_token": token, "status": "active"}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Invalid QR token")
    rec = await _upsert_attendance(
        employee_id=emp["id"],
        d=_today_iso(),
        patch={"check_out": _now_hhmm()},
    )
    return {"ok": True, "attendance": rec}


# ---------- Biometric webhook ----------
@router.post("/attendance/biometric")
async def biometric_punch(payload: BiometricPunch):
    """Receives raw punches from a biometric device. employee_code is mapped to employee_id."""
    emp = await db.employees.find_one({"employee_code": payload.employee_code}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Unknown employee_code")
    try:
        dt = datetime.fromisoformat(payload.timestamp.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid timestamp")
    d = dt.date().isoformat()
    hhmm = dt.strftime("%H:%M")
    shift = await _resolve_shift(emp)
    if payload.punch_type == "IN":
        status = "LATE" if _is_late(hhmm, shift) else "PRESENT"
        return await _upsert_attendance(
            employee_id=emp["id"], d=d,
            patch={"check_in": hhmm, "status": status, "source": "biometric"},
        )
    return await _upsert_attendance(
        employee_id=emp["id"], d=d,
        patch={"check_out": hhmm, "source": "biometric"},
    )


# ---------- Leaves ----------
def _calc_days(start: str, end: str) -> float:
    try:
        a = datetime.strptime(start, "%Y-%m-%d").date()
        b = datetime.strptime(end, "%Y-%m-%d").date()
        return float((b - a).days + 1)
    except Exception:
        return 1.0


async def _enrich_leaves(leaves: list) -> list:
    emp_ids = list({lv["employee_id"] for lv in leaves})
    lt_ids = list({lv.get("leave_type_id") for lv in leaves if lv.get("leave_type_id")})
    emap = {
        e["id"]: f"{e.get('first_name','')} {e.get('last_name','')} ({e.get('employee_code','')})"
        for e in await db.employees.find({"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "employee_code": 1}).to_list(2000)
    } if emp_ids else {}
    lt_map = {
        lt["id"]: lt["name"]
        for lt in await db.leave_types.find({"id": {"$in": lt_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
    } if lt_ids else {}
    for lv in leaves:
        lv["employee_name"] = emap.get(lv["employee_id"], "-")
        lv["leave_type_name"] = lt_map.get(lv.get("leave_type_id"), "-")
    return leaves


@router.get("/leaves")
async def list_leaves(status: Optional[str] = None, _: dict = Depends(get_current_user)):
    filt = {}
    if status:
        filt["status"] = status
    leaves = await db.leaves.find(filt, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return await _enrich_leaves(leaves)


@router.post("/leaves")
async def apply_leave(payload: Leave, user: dict = Depends(require_hr_or_admin)):
    """HR/Admin applies a leave on behalf of any employee."""
    data = payload.model_dump()
    if not data.get("total_days"):
        data["total_days"] = _calc_days(data["start_date"], data["end_date"])
    data["status"] = "PENDING"
    return await crud_create("leaves", data, user=user)


@router.post("/me/leaves")
async def apply_my_leave(payload: Leave, user: dict = Depends(get_current_user)):
    emp = await _employee_from_user(user)
    data = payload.model_dump()
    data["employee_id"] = emp["id"]
    if not data.get("total_days"):
        data["total_days"] = _calc_days(data["start_date"], data["end_date"])
    data["status"] = "PENDING"
    return await crud_create("leaves", data)


@router.get("/me/leaves")
async def my_leaves(user: dict = Depends(get_current_user)):
    emp = await _employee_from_user(user)
    return await db.leaves.find({"employee_id": emp["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.get("/me/leave-balance")
async def my_leave_balance(user: dict = Depends(get_current_user)):
    emp = await _employee_from_user(user)
    leave_types = await db.leave_types.find({}, {"_id": 0}).to_list(100)
    year = datetime.now().year
    out = []
    for lt in leave_types:
        # Used = sum of approved leaves in this year for this type
        used = 0.0
        approved = await db.leaves.find(
            {
                "employee_id": emp["id"],
                "leave_type_id": lt["id"],
                "status": "APPROVED",
                "start_date": {"$regex": f"^{year}-"},
            },
            {"_id": 0, "total_days": 1},
        ).to_list(200)
        used = sum(float(a.get("total_days", 0)) for a in approved)
        out.append({
            "leave_type_id": lt["id"],
            "leave_type_name": lt["name"],
            "annual_quota": lt.get("annual_quota", 0),
            "used": used,
            "available": max(0, float(lt.get("annual_quota", 0)) - used),
        })
    return out


@router.post("/leaves/{item_id}/decide")
async def decide_leave(item_id: str, payload: LeaveDecision, user: dict = Depends(require_hr_or_admin)):
    update = {
        "status": payload.status,
        "approved_by": user.get("name"),
        "approved_by_id": user.get("id"),
        "approved_at": now_iso(),
    }
    if payload.status == "REJECTED":
        update["rejection_reason"] = payload.rejection_reason
    return await crud_update("leaves", item_id, update)


@router.delete("/leaves/{item_id}")
async def delete_leave(item_id: str, _: dict = Depends(require_hr_or_admin)):
    return await crud_delete("leaves", item_id)


# ---------- Advances ----------
@router.get("/advances")
async def list_advances(_: dict = Depends(require_hr_or_admin)):
    return await crud_list("advances", sort_field="created_at")


@router.post("/advances")
async def create_advance(payload: Advance, _: dict = Depends(require_hr_or_admin)):
    return await crud_create("advances", payload.model_dump())


@router.delete("/advances/{item_id}")
async def delete_advance(item_id: str, _: dict = Depends(require_hr_or_admin)):
    return await crud_delete("advances", item_id)
