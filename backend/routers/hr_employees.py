"""HR Employees + Salary Structures + QR check-in token."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from core.auth_utils import (
    get_current_user,
    hash_password,
    require_admin,
    require_hr_or_admin,
)
from core.password_policy import password_errors
from core.db import db
from core.hr_models import Employee, SalaryStructure
from core.utils import crud_create, crud_get, crud_list, crud_update, new_id, now_iso

router = APIRouter(prefix="/hr", tags=["hr-employees"])


async def _enrich_employees(employees: list) -> list:
    branch_ids = list({e.get("branch_id") for e in employees if e.get("branch_id")})
    dept_ids = list({e.get("department_id") for e in employees if e.get("department_id")})
    shift_ids = list({e.get("shift_id") for e in employees if e.get("shift_id")})
    b_map = {b["id"]: b["name"] for b in await db.hr_branches.find({"id": {"$in": branch_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(500)} if branch_ids else {}
    d_map = {d["id"]: d["name"] for d in await db.hr_departments.find({"id": {"$in": dept_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(500)} if dept_ids else {}
    s_map = {s["id"]: s["name"] for s in await db.shifts.find({"id": {"$in": shift_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(500)} if shift_ids else {}
    for e in employees:
        e["branch_name"] = b_map.get(e.get("branch_id"), "-")
        e["department_name"] = d_map.get(e.get("department_id"), "-")
        e["shift_name"] = s_map.get(e.get("shift_id"), "-")
    return employees


@router.get("/employees")
async def list_employees(
    q: Optional[str] = None,
    branch_id: Optional[str] = None,
    department_id: Optional[str] = None,
    status: Optional[str] = None,
    _: dict = Depends(get_current_user),
):
    filt = {}
    if branch_id:
        filt["branch_id"] = branch_id
    if department_id:
        filt["department_id"] = department_id
    if status:
        filt["status"] = status
    items = await crud_list(
        "employees", q,
        ["employee_code", "first_name", "last_name", "phone", "email", "designation"],
        sort_field="employee_code",
        filt=filt,
    )
    return await _enrich_employees(items)


@router.post("/employees")
async def create_employee(payload: Employee, _: dict = Depends(require_hr_or_admin)):
    if await db.employees.find_one({"employee_code": payload.employee_code}):
        raise HTTPException(status_code=400, detail="Employee code already exists")

    data = payload.model_dump()
    create_login = data.pop("create_login", False)
    login_password = data.pop("login_password", None)

    # Auto-link to an existing user with the same email, or create a new login
    user_id = None
    if data.get("email"):
        existing_user = await db.users.find_one({"email": data["email"].lower()})
        if existing_user:
            user_id = existing_user["id"]

    if create_login and not user_id:
        if not data.get("email"):
            raise HTTPException(status_code=400, detail="Email is required to create login")
        if not login_password:
            raise HTTPException(status_code=400, detail="Initial password required for login")
        # This path creates a login user directly (not via UserCreate), so the
        # password policy must be enforced here too.
        pw_errors = password_errors(login_password)
        if pw_errors:
            raise HTTPException(status_code=400, detail=" ".join(pw_errors))
        user_id = new_id()
        await db.users.insert_one({
            "id": user_id,
            "name": f"{data['first_name']} {data['last_name']}".strip(),
            "email": data["email"].lower(),
            "phone": data.get("phone"),
            "role": "employee",
            "password_hash": hash_password(login_password),
            "created_at": now_iso(),
        })
    data["user_id"] = user_id
    data["qr_token"] = new_id()
    return await crud_create("employees", data)


@router.get("/employees/{item_id}")
async def get_employee(item_id: str, _: dict = Depends(get_current_user)):
    emp = await crud_get("employees", item_id)
    return (await _enrich_employees([emp]))[0]


@router.put("/employees/{item_id}")
async def update_employee(item_id: str, payload: Employee, _: dict = Depends(require_hr_or_admin)):
    existing = await db.employees.find_one(
        {"employee_code": payload.employee_code, "id": {"$ne": item_id}}
    )
    if existing:
        raise HTTPException(status_code=400, detail="Employee code already used")
    data = payload.model_dump()
    data.pop("create_login", None)
    data.pop("login_password", None)
    
    # Auto-link to user account if a matching email exists
    if data.get("email"):
        existing_user = await db.users.find_one({"email": data["email"].lower()})
        if existing_user:
            data["user_id"] = existing_user["id"]
        else:
            data["user_id"] = None
    else:
        data["user_id"] = None
    return await crud_update("employees", item_id, data)


@router.delete("/employees/{item_id}")
async def delete_employee(item_id: str, _: dict = Depends(require_admin)):
    emp = await db.employees.find_one({"id": item_id}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Cascade delete all employee dependencies to prevent Foreign Key violations in Postgres
    await db.attendance.delete_many({"employee_id": item_id})
    await db.attendance_logs.delete_many({"employee_id": item_id})
    await db.leaves.delete_many({"employee_id": item_id})
    await db.payslips.delete_many({"employee_id": item_id})
    await db.fnf_settlements.delete_many({"employee_id": item_id})
    await db.tds_declarations.delete_many({"employee_id": item_id})
    await db.timesheet_entries.delete_many({"employee_id": item_id})
    await db.overtime_entries.delete_many({"employee_id": item_id})
    await db.salary_payments.delete_many({"employee_id": item_id})
    await db.salary_structures.delete_many({"employee_id": item_id})

    if emp.get("user_id"):
        await db.users.delete_one({"id": emp["user_id"]})
    await db.employees.delete_one({"id": item_id})
    return {"ok": True}


@router.post("/employees/{item_id}/reset-qr")
async def reset_qr(item_id: str, _: dict = Depends(require_hr_or_admin)):
    token = new_id()
    res = await db.employees.update_one({"id": item_id}, {"$set": {"qr_token": token, "updated_at": now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"qr_token": token}


# ----- self-service -----
@router.get("/me/employee")
async def my_employee(user: dict = Depends(get_current_user)):
    emp = await db.employees.find_one({"user_id": user["id"]}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="No employee record linked to your account")
    return (await _enrich_employees([emp]))[0]


# ----- salary structure -----
@router.get("/employees/{employee_id}/salary-structure")
async def get_salary_structure(employee_id: str, _: dict = Depends(require_hr_or_admin)):
    ss = await db.salary_structures.find_one({"employee_id": employee_id}, {"_id": 0})
    if not ss:
        emp = await crud_get("employees", employee_id)
        return {
            "employee_id": employee_id,
            "basic": float(emp.get("basic_salary", 0)),
            "hra": 0, "da": 0, "conveyance": 0, "medical": 0,
            "special_allowance": 0, "other_allowance": 0,
            "pf_percent": 12, "enable_pf": True,
            "esi_employee_percent": 0.75, "esi_employer_percent": 3.25, "enable_esi": True,
            "professional_tax": 200, "tds_percent": 0,
            "overtime_rate_multiplier": 2.0,
        }
    return ss


@router.put("/employees/{employee_id}/salary-structure")
async def upsert_salary_structure(employee_id: str, payload: SalaryStructure, _: dict = Depends(require_hr_or_admin)):
    data = payload.model_dump()
    data["employee_id"] = employee_id
    existing = await db.salary_structures.find_one({"employee_id": employee_id}, {"_id": 0})
    if existing:
        await db.salary_structures.update_one(
            {"employee_id": employee_id},
            {"$set": {**data, "updated_at": now_iso()}},
        )
        return await db.salary_structures.find_one({"employee_id": employee_id}, {"_id": 0})
    data["id"] = new_id()
    data["created_at"] = now_iso()
    data["updated_at"] = now_iso()
    await db.salary_structures.insert_one(data)
    return await db.salary_structures.find_one({"employee_id": employee_id}, {"_id": 0})
