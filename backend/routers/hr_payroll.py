"""HR Payroll runs + Payslips + PDF + Public share."""
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Response

from core.auth_utils import get_current_user, require_payroll_role
from core.db import db
from core.hr_models import PayrollRunRequest, PayslipBonusEdit
from core.hr_payroll import build_payslip_pdf, calculate_payslip, working_days_in_month
from core.utils import crud_get, new_id, next_doc_number, now_iso

router = APIRouter(prefix="/hr", tags=["hr-payroll"])


# ---------- Payroll runs ----------
@router.get("/payroll-runs")
async def list_runs(_: dict = Depends(require_payroll_role)):
    return await db.payroll_runs.find({}, {"_id": 0}).sort("month", -1).to_list(500)


@router.get("/payroll-runs/{item_id}")
async def get_run(item_id: str, _: dict = Depends(require_payroll_role)):
    return await crud_get("payroll_runs", item_id)


@router.post("/payroll-runs/generate")
async def generate_run(payload: PayrollRunRequest, user: dict = Depends(require_payroll_role)):
    # Block regenerate if already locked
    existing = await db.payroll_runs.find_one({"month": payload.month}, {"_id": 0})
    if existing and existing.get("status") == "LOCKED":
        raise HTTPException(status_code=400, detail="Payroll for this month is locked")

    # employee selection
    filt: dict[str, Any] = {"status": "active"}
    if payload.branch_id:
        filt["branch_id"] = payload.branch_id
    if payload.employee_ids:
        filt["id"] = {"$in": payload.employee_ids}
    employees = await db.employees.find(filt, {"_id": 0}).to_list(5000)
    if not employees:
        raise HTTPException(status_code=400, detail="No active employees match the filter")

    structures = {
        s["employee_id"]: s
        for s in await db.salary_structures.find({}, {"_id": 0}).to_list(5000)
    }

    # Upsert run
    if existing:
        run_id = existing["id"]
        await db.payroll_runs.update_one(
            {"id": run_id},
            {"$set": {"branch_id": payload.branch_id, "notes": payload.notes, "status": "DRAFT", "updated_at": now_iso()}},
        )
        # delete previous draft payslips for this run
        await db.payslips.delete_many({"run_id": run_id})
    else:
        run_id = new_id()
        run_number = await next_doc_number("RUN", "payroll_runs")
        await db.payroll_runs.insert_one({
            "id": run_id,
            "run_number": run_number,
            "month": payload.month,
            "branch_id": payload.branch_id,
            "status": "DRAFT",
            "notes": payload.notes,
            "generated_by": user.get("name"),
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })

    # Generate payslips
    created = 0
    for emp in employees:
        ps = await calculate_payslip(emp, payload.month, salary_structure=structures.get(emp["id"]))
        ps["id"] = new_id()
        ps["run_id"] = run_id
        ps["share_token"] = new_id()
        ps["status"] = "DRAFT"
        ps["created_at"] = now_iso()
        ps["updated_at"] = now_iso()
        await db.payslips.insert_one(ps)
        created += 1

    info = await working_days_in_month(payload.month, payload.branch_id)
    await db.payroll_runs.update_one(
        {"id": run_id},
        {"$set": {
            "total_working_days": info["working_days"],
            "employee_count": created,
            "updated_at": now_iso(),
        }},
    )
    return await crud_get("payroll_runs", run_id)


@router.post("/payroll-runs/{item_id}/lock")
async def lock_run(item_id: str, user: dict = Depends(require_payroll_role)):
    res = await db.payroll_runs.update_one(
        {"id": item_id},
        {"$set": {"status": "LOCKED", "locked_by": user.get("name"), "locked_at": now_iso(), "updated_at": now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await db.payslips.update_many({"run_id": item_id}, {"$set": {"status": "FINALISED", "updated_at": now_iso()}})
    return {"ok": True}


@router.post("/payroll-runs/{item_id}/unlock")
async def unlock_run(item_id: str, user: dict = Depends(require_payroll_role)):
    res = await db.payroll_runs.update_one(
        {"id": item_id},
        {"$set": {"status": "DRAFT", "updated_at": now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await db.payslips.update_many({"run_id": item_id}, {"$set": {"status": "DRAFT", "updated_at": now_iso()}})
    return {"ok": True}


# ---------- Payslips ----------
@router.get("/payslips")
async def list_payslips(
    run_id: Optional[str] = None,
    month: Optional[str] = None,
    employee_id: Optional[str] = None,
    _: dict = Depends(require_payroll_role),
):
    filt = {}
    if run_id:
        filt["run_id"] = run_id
    if month:
        filt["month"] = month
    if employee_id:
        filt["employee_id"] = employee_id
    return await db.payslips.find(filt, {"_id": 0}).sort("employee_code", 1).to_list(5000)


@router.get("/payslips/{item_id}")
async def get_payslip(item_id: str, _: dict = Depends(require_payroll_role)):
    return await crud_get("payslips", item_id)


@router.put("/payslips/{item_id}")
async def edit_payslip(item_id: str, payload: PayslipBonusEdit, _: dict = Depends(require_payroll_role)):
    ps = await crud_get("payslips", item_id)
    run = await db.payroll_runs.find_one({"id": ps.get("run_id")}, {"_id": 0})
    if run and run.get("status") == "LOCKED":
        raise HTTPException(status_code=400, detail="Payroll is locked")

    update = {}
    if payload.bonus is not None:
        update["bonus"] = payload.bonus
    if payload.incentive is not None:
        update["incentive"] = payload.incentive
    if payload.other_deduction is not None:
        update["deductions"] = {**ps.get("deductions", {}), "other_deduction": payload.other_deduction}
    if payload.other_deduction_label is not None:
        update["other_deduction_label"] = payload.other_deduction_label
    if payload.notes is not None:
        update["notes"] = payload.notes

    merged = {**ps, **update}
    gross = float(merged.get("gross_salary", 0))
    bonus = float(merged.get("bonus", 0))
    incentive = float(merged.get("incentive", 0))
    deductions = merged.get("deductions", {})
    total_deduction = sum(float(v or 0) for v in deductions.values())
    gross_total = round(gross + bonus + incentive, 2)
    net = round(gross_total - total_deduction, 2)
    update["total_deduction"] = round(total_deduction, 2)
    update["net_salary"] = net
    from core.words import amount_in_words
    update["amount_in_words"] = amount_in_words(net, "INR")
    update["updated_at"] = now_iso()

    await db.payslips.update_one({"id": item_id}, {"$set": update})
    return await crud_get("payslips", item_id)


@router.get("/payslips/{item_id}/pdf")
async def payslip_pdf(item_id: str, _: dict = Depends(require_payroll_role)):
    ps = await crud_get("payslips", item_id)
    emp = await crud_get("employees", ps["employee_id"])
    branch_name = "GravityOne ERP"
    if emp.get("branch_id"):
        b = await db.hr_branches.find_one({"id": emp["branch_id"]}, {"_id": 0, "name": 1})
        if b:
            branch_name = b["name"]
    pdf_bytes = build_payslip_pdf(ps, emp, branch_name=branch_name)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="payslip_{ps.get("employee_code")}_{ps.get("month")}.pdf"'},
    )


@router.get("/payslips/{item_id}/whatsapp-link")
async def payslip_whatsapp(item_id: str, _: dict = Depends(require_payroll_role)):
    ps = await crud_get("payslips", item_id)
    emp = await crud_get("employees", ps["employee_id"])
    if not emp.get("phone"):
        raise HTTPException(status_code=400, detail="Employee has no phone number")
    import os
    frontend = os.environ.get("FRONTEND_URL", "")
    public_url = f"{frontend}/payslip/{ps.get('share_token')}"
    phone = emp["phone"].replace("+", "").replace(" ", "").replace("-", "")
    msg = f"Hello {emp.get('first_name')}, your salary slip for {ps.get('month')} is available here:\n{public_url}"
    from urllib.parse import quote
    return {
        "wa_link": f"https://wa.me/{phone}?text={quote(msg)}",
        "public_url": public_url,
    }


# ---------- Self-service ----------
@router.get("/me/payslips")
async def my_payslips(user: dict = Depends(get_current_user)):
    emp = await db.employees.find_one({"user_id": user["id"]}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="No employee record linked")
    return await db.payslips.find(
        {"employee_id": emp["id"], "status": "FINALISED"},
        {"_id": 0},
    ).sort("month", -1).to_list(120)


@router.get("/me/payslips/{item_id}/pdf")
async def my_payslip_pdf(item_id: str, user: dict = Depends(get_current_user)):
    emp = await db.employees.find_one({"user_id": user["id"]}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="No employee record linked")
    ps = await db.payslips.find_one({"id": item_id, "employee_id": emp["id"]}, {"_id": 0})
    if not ps or ps.get("status") != "FINALISED":
        raise HTTPException(status_code=404, detail="Not available")
    branch_name = "GravityOne ERP"
    if emp.get("branch_id"):
        b = await db.hr_branches.find_one({"id": emp["branch_id"]}, {"_id": 0, "name": 1})
        if b:
            branch_name = b["name"]
    pdf_bytes = build_payslip_pdf(ps, emp, branch_name=branch_name)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="payslip_{ps.get("month")}.pdf"'},
    )


# ---------- Public payslip via share token (no auth) ----------
@router.get("/public/payslip/{token}/info")
async def public_payslip_info(token: str):
    ps = await db.payslips.find_one({"share_token": token, "status": "FINALISED"}, {"_id": 0})
    if not ps:
        raise HTTPException(status_code=404, detail="Not found or not finalised")
    return {
        "employee_name": ps.get("employee_name"),
        "employee_code": ps.get("employee_code"),
        "month": ps.get("month"),
        "net_salary": ps.get("net_salary"),
        "amount_in_words": ps.get("amount_in_words"),
    }


@router.get("/public/payslip/{token}/pdf")
async def public_payslip_pdf(token: str):
    ps = await db.payslips.find_one({"share_token": token, "status": "FINALISED"}, {"_id": 0})
    if not ps:
        raise HTTPException(status_code=404, detail="Not found")
    emp = await db.employees.find_one({"id": ps["employee_id"]}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    branch_name = "GravityOne ERP"
    if emp.get("branch_id"):
        b = await db.hr_branches.find_one({"id": emp["branch_id"]}, {"_id": 0, "name": 1})
        if b:
            branch_name = b["name"]
    pdf_bytes = build_payslip_pdf(ps, emp, branch_name=branch_name)
    return Response(content=pdf_bytes, media_type="application/pdf")


# ---------- HR Dashboard ----------
@router.get("/dashboard")
async def hr_dashboard(_: dict = Depends(get_current_user)):
    total_employees = await db.employees.count_documents({"status": "active"})
    total_branches = await db.hr_branches.count_documents({})
    total_departments = await db.hr_departments.count_documents({})
    pending_leaves = await db.leaves.count_documents({"status": "PENDING"})
    from datetime import date as _d
    today_iso = _d.today().isoformat()
    present_today = await db.attendance.count_documents({"date": today_iso, "status": {"$in": ["PRESENT", "LATE"]}})
    absent_today = await db.attendance.count_documents({"date": today_iso, "status": "ABSENT"})

    # latest payroll run
    last_run = await db.payroll_runs.find_one({}, {"_id": 0}, sort=[("month", -1)])

    # Department headcount
    pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {"_id": "$department_id", "count": {"$sum": 1}}},
    ]
    by_dept = await db.employees.aggregate(pipeline).to_list(100)
    dept_map = {
        d["id"]: d["name"]
        for d in await db.hr_departments.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
    }
    by_department = [
        {"department": dept_map.get(b["_id"], "Unassigned"), "count": b["count"]}
        for b in by_dept
    ]

    return {
        "kpis": {
            "total_employees": total_employees,
            "branches": total_branches,
            "departments": total_departments,
            "pending_leaves": pending_leaves,
            "present_today": present_today,
            "absent_today": absent_today,
            "latest_run": last_run.get("month") if last_run else None,
            "latest_run_status": last_run.get("status") if last_run else None,
            "latest_run_employees": last_run.get("employee_count") if last_run else 0,
        },
        "by_department": by_department,
    }
