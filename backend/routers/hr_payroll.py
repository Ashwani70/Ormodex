"""HR Payroll runs + Payslips + PDF + Public share."""
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Response

from core import cache
from core.auth_utils import get_current_user, require_payroll_role
from core.db import db
from core.hr_models import PayrollRunRequest, PayslipBonusEdit
from core.hr_payroll import build_payslip_pdf, calculate_payslip, working_days_in_month
from core.utils import crud_get, new_id, next_doc_number, now_iso

router = APIRouter(prefix="/hr", tags=["hr-payroll"])


def _enrich_payslip(ps: dict) -> dict:
    """Merge components JSONB into top-level so PDF builder can find all fields."""
    comp = ps.get("components") or {}
    if isinstance(comp, dict):
        merged = {**comp, **ps}  # ps top-level wins over components
        merged["components"] = comp
        return merged
    return ps


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
        await db.payslips.delete_many({"payroll_run_id": run_id})
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

    # Generate payslips — compute all concurrently then bulk-insert in one round-trip.
    import asyncio as _asyncio
    from sqlalchemy.dialects.postgresql import insert as _pg_insert
    from core.db import get_session as _get_session
    from core.schema import Payslip as _Payslip

    async def _calc(emp):
        ps = await calculate_payslip(emp, payload.month, salary_structure=structures.get(emp["id"]))
        ps["id"] = new_id()
        ps["payroll_run_id"] = run_id
        ps["share_token"] = new_id()
        ps["status"] = "DRAFT"
        ps["created_at"] = now_iso()
        ps["updated_at"] = now_iso()
        return ps

    payslip_docs = await _asyncio.gather(*(_calc(e) for e in employees))
    created = len(payslip_docs)

    if payslip_docs:
        async with _get_session() as _sess:
            _rows = []
            for ps in payslip_docs:
                row_data = {
                    "id": ps["id"],
                    "tenant_id": ps.get("tenant_id"),
                    "payroll_run_id": ps.get("payroll_run_id") or run_id,
                    "employee_id": ps["employee_id"],
                    "month": ps["month"],
                    "year": int(ps["month"].split("-")[0]),
                    "gross": ps["gross_salary"],
                    "deductions": ps["total_deduction"],
                    "net": ps["net_salary"],
                    "status": ps["status"],
                    "created_at": ps["created_at"],
                    "updated_at": ps["updated_at"],
                    "components": {
                        k: v for k, v in ps.items()
                        if k not in ("id", "tenant_id", "payroll_run_id", "employee_id",
                                     "month", "year", "status", "created_at", "updated_at")
                    }
                }
                _rows.append(row_data)
            await _sess.execute(
                _pg_insert(_Payslip).values(_rows).on_conflict_do_nothing(index_elements=["id"])
            )

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
    await db.payslips.update_many({"payroll_run_id": item_id}, {"$set": {"status": "FINALISED", "updated_at": now_iso()}})
    return {"ok": True}


@router.post("/payroll-runs/{item_id}/unlock")
async def unlock_run(item_id: str, user: dict = Depends(require_payroll_role)):
    res = await db.payroll_runs.update_one(
        {"id": item_id},
        {"$set": {"status": "DRAFT", "updated_at": now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await db.payslips.update_many({"payroll_run_id": item_id}, {"$set": {"status": "DRAFT", "updated_at": now_iso()}})
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
        filt["payroll_run_id"] = run_id
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
    _run_ref = ps.get("payroll_run_id") or ps.get("run_id")
    run = await db.payroll_runs.find_one({"id": _run_ref}, {"_id": 0})
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
    ps = _enrich_payslip(await crud_get("payslips", item_id))
    emp = await crud_get("employees", ps["employee_id"])
    branch_name = "Ormodex ERP"
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
    ps = _enrich_payslip(ps)
    branch_name = "Ormodex ERP"
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
    _comp = ps.get("components") or {}
    return {
        "employee_name": ps.get("employee_name") or _comp.get("employee_name"),
        "employee_code": ps.get("employee_code") or _comp.get("employee_code"),
        "month": ps.get("month"),
        "net_salary": ps.get("net_salary") or ps.get("net") or _comp.get("net_salary"),
        "amount_in_words": ps.get("amount_in_words") or _comp.get("amount_in_words"),
    }


@router.get("/public/payslip/{token}/pdf")
async def public_payslip_pdf(token: str):
    ps = await db.payslips.find_one({"share_token": token, "status": "FINALISED"}, {"_id": 0})
    if not ps:
        raise HTTPException(status_code=404, detail="Not found")
    ps = _enrich_payslip(ps)
    emp = await db.employees.find_one({"id": ps["employee_id"]}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    branch_name = "Ormodex ERP"
    if emp.get("branch_id"):
        b = await db.hr_branches.find_one({"id": emp["branch_id"]}, {"_id": 0, "name": 1})
        if b:
            branch_name = b["name"]
    pdf_bytes = build_payslip_pdf(ps, emp, branch_name=branch_name)
    return Response(content=pdf_bytes, media_type="application/pdf")


# ---------- HR Dashboard ----------
@router.get("/dashboard")
async def hr_dashboard(_: dict = Depends(get_current_user)):
    return await cache.get_or_set(
        "hr:dashboard", cache.TTL_DASHBOARD, _compute_hr_dashboard
    )


async def _compute_hr_dashboard() -> dict:
    from datetime import date as _d
    today_iso = _d.today().isoformat()

    # PERF: fetch employees and today's attendance ONCE each, then derive the
    # active count + department headcount + present/absent in Python. Previously
    # `employees` was queried 3× and `attendance` 2× (sequential round-trips to a
    # cross-region pooler). The remaining counts hit distinct small collections.
    employees = await db.employees.find(
        {}, {"_id": 0, "status": 1, "department_id": 1}
    ).to_list(20000)
    total_employees = sum(1 for e in employees if e.get("status") == "active")

    today_attendance = await db.attendance.find(
        {"date": today_iso}, {"_id": 0, "status": 1}
    ).to_list(20000)
    present_today = sum(1 for a in today_attendance if a.get("status") in ("PRESENT", "LATE"))
    absent_today = sum(1 for a in today_attendance if a.get("status") == "ABSENT")

    total_branches = await db.hr_branches.count_documents({})
    total_departments = await db.hr_departments.count_documents({})
    pending_leaves = await db.leaves.count_documents({"status": "PENDING"})

    # latest payroll run
    last_run = await db.payroll_runs.find_one({}, {"_id": 0}, sort=[("month", -1)])

    # Department headcount (active employees) from the single fetch above.
    dept_counts: dict = {}
    for e in employees:
        if e.get("status") == "active":
            dept_counts[e.get("department_id")] = dept_counts.get(e.get("department_id"), 0) + 1
    dept_map = {
        d["id"]: d["name"]
        for d in await db.hr_departments.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
    }
    by_department = [
        {"department": dept_map.get(dept_id, "Unassigned"), "count": count}
        for dept_id, count in dept_counts.items()
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


# ──────────────────────────────────────────────────────────────
# Salary Advances
# ──────────────────────────────────────────────────────────────

@router.get("/advances")
async def list_advances(
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    _: dict = Depends(require_payroll_role),
):
    filt: dict = {}
    if employee_id:
        filt["employee_id"] = employee_id
    if status:
        filt["status"] = status
    return await db.advances.find(filt, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/advances")
async def create_advance(payload: dict, user: dict = Depends(require_payroll_role)):
    required = {"employee_id", "amount", "advance_date"}
    if not required.issubset(payload):
        from fastapi import HTTPException as _H
        raise _H(400, f"Required fields: {required}")
    doc = {
        "id": new_id(),
        "employee_id": payload["employee_id"],
        "amount": float(payload["amount"]),
        "advance_date": payload["advance_date"],
        "recovery_month": payload.get("recovery_month"),
        "reason": payload.get("reason", ""),
        "status": "PENDING",
        "paid": False,
        "paid_amount": 0.0,
        "paid_date": None,
        "payment_mode": None,
        "reference": None,
        "notes": payload.get("notes", ""),
        "created_by": user.get("name"),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.advances.insert_one(doc)
    return doc


@router.patch("/advances/{advance_id}")
async def update_advance(advance_id: str, payload: dict, _: dict = Depends(require_payroll_role)):
    adv = await db.advances.find_one({"id": advance_id})
    if not adv:
        from fastapi import HTTPException as _H
        raise _H(404, "Advance not found")
    allowed = {"recovery_month", "reason", "status", "notes"}
    upd = {k: v for k, v in payload.items() if k in allowed}
    upd["updated_at"] = now_iso()
    await db.advances.update_one({"id": advance_id}, {"$set": upd})
    return await db.advances.find_one({"id": advance_id}, {"_id": 0})


@router.post("/advances/{advance_id}/pay")
async def pay_advance(advance_id: str, payload: dict, user: dict = Depends(require_payroll_role)):
    """Record full or partial payment disbursed to the employee for an advance."""
    adv = await db.advances.find_one({"id": advance_id})
    if not adv:
        from fastapi import HTTPException as _H
        raise _H(404, "Advance not found")
    paid_amount = float(payload.get("paid_amount") or adv["amount"])
    upd = {
        "paid": True,
        "paid_amount": paid_amount,
        "paid_date": payload.get("paid_date", now_iso()[:10]),
        "payment_mode": payload.get("payment_mode", "CASH"),
        "reference": payload.get("reference", ""),
        "status": "PAID",
        "updated_at": now_iso(),
        "paid_by": user.get("name"),
    }
    await db.advances.update_one({"id": advance_id}, {"$set": upd})
    return await db.advances.find_one({"id": advance_id}, {"_id": 0})


@router.delete("/advances/{advance_id}")
async def delete_advance(advance_id: str, _: dict = Depends(require_payroll_role)):
    res = await db.advances.delete_one({"id": advance_id})
    if res.deleted_count == 0:
        from fastapi import HTTPException as _H
        raise _H(404, "Advance not found")
    return {"ok": True}


# ──────────────────────────────────────────────────────────────
# Overtime Entries (manual entry separate from attendance)
# ──────────────────────────────────────────────────────────────

@router.get("/overtime")
async def list_overtime(
    employee_id: Optional[str] = None,
    month: Optional[str] = None,
    _: dict = Depends(require_payroll_role),
):
    filt: dict = {}
    if employee_id:
        filt["employee_id"] = employee_id
    if month:
        filt["month"] = month
    return await db.overtime_entries.find(filt, {"_id": 0}).sort("date", -1).to_list(1000)


@router.post("/overtime")
async def create_overtime(payload: dict, user: dict = Depends(require_payroll_role)):
    required = {"employee_id", "date", "hours"}
    if not required.issubset(payload):
        from fastapi import HTTPException as _H
        raise _H(400, f"Required fields: {required}")
    month = payload["date"][:7]  # YYYY-MM from YYYY-MM-DD
    doc = {
        "id": new_id(),
        "employee_id": payload["employee_id"],
        "date": payload["date"],
        "month": month,
        "hours": float(payload["hours"]),
        "reason": payload.get("reason", ""),
        "approved": False,
        "approved_by": None,
        "created_by": user.get("name"),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.overtime_entries.insert_one(doc)
    return doc


@router.patch("/overtime/{ot_id}/approve")
async def approve_overtime(ot_id: str, user: dict = Depends(require_payroll_role)):
    res = await db.overtime_entries.update_one(
        {"id": ot_id},
        {"$set": {"approved": True, "approved_by": user.get("name"), "updated_at": now_iso()}},
    )
    if res.matched_count == 0:
        from fastapi import HTTPException as _H
        raise _H(404, "Not found")
    return await db.overtime_entries.find_one({"id": ot_id}, {"_id": 0})


@router.delete("/overtime/{ot_id}")
async def delete_overtime(ot_id: str, _: dict = Depends(require_payroll_role)):
    res = await db.overtime_entries.delete_one({"id": ot_id})
    if res.deleted_count == 0:
        from fastapi import HTTPException as _H
        raise _H(404, "Not found")
    return {"ok": True}


# ──────────────────────────────────────────────────────────────
# Salary Payments (full / partial disbursement against payslip)
# ──────────────────────────────────────────────────────────────

@router.get("/salary-payments")
async def list_salary_payments(
    employee_id: Optional[str] = None,
    month: Optional[str] = None,
    _: dict = Depends(require_payroll_role),
):
    filt: dict = {}
    if employee_id:
        filt["employee_id"] = employee_id
    if month:
        filt["month"] = month
    return await db.salary_payments.find(filt, {"_id": 0}).sort("payment_date", -1).to_list(1000)


@router.post("/salary-payments")
async def record_salary_payment(payload: dict, user: dict = Depends(require_payroll_role)):
    required = {"employee_id", "month", "amount", "payment_date", "payment_type"}
    if not required.issubset(payload):
        from fastapi import HTTPException as _H
        raise _H(400, f"Required fields: {required}")

    payslip = await db.payslips.find_one({"employee_id": payload["employee_id"], "month": payload["month"]}, {"_id": 0})
    doc = {
        "id": new_id(),
        "employee_id": payload["employee_id"],
        "payslip_id": payslip["id"] if payslip else None,
        "month": payload["month"],
        "payment_type": payload["payment_type"],  # "ADVANCE_PAYMENT" | "FULL_PAYMENT" | "PARTIAL_PAYMENT"
        "amount": float(payload["amount"]),
        "payment_date": payload["payment_date"],
        "payment_mode": payload.get("payment_mode", "BANK"),
        "reference": payload.get("reference", ""),
        "gross_salary": payslip.get("gross_salary") if payslip else None,
        "net_salary": payslip.get("net_salary") if payslip else None,
        "notes": payload.get("notes", ""),
        "created_by": user.get("name"),
        "created_at": now_iso(),
    }
    await db.salary_payments.insert_one(doc)
    if payslip and payload["payment_type"] == "FULL_PAYMENT":
        await db.payslips.update_one({"id": payslip["id"]}, {"$set": {"payment_status": "PAID", "updated_at": now_iso()}})
    return doc
