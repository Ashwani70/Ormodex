"""eSSL Biometric Attendance Integration.

Device registry, employee<->device enrollment mapping, inbound push webhook
(HMAC-authenticated per device, mirrors core.webhooks' signing convention),
manual + scheduled poll sync, raw punch logs, derived daily attendance,
monthly payroll aggregate, attendance rules, device health, and sync history.

RBAC: admin, or "hr"/"biometric" in module_permissions (mirrors the
_require_hr-style local check used by routers/payroll.py rather than a
shared Depends, since this module's permission set doesn't match any
existing shared dependency).
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.auth_utils import get_current_user, require_admin, is_admin_role
from core.biometric_models import (
    AttendanceCorrectionDecision, AttendanceCorrectionIn,
    AttendanceRuleIn, AttendanceRuleUpdate, BiometricDeviceIn, BiometricDeviceUpdate,
    DevicePushIn, EmployeeDeviceMappingIn, MonthlyAggregateRunIn, SyncTriggerIn,
)
from core.biometric_sync import (
    aggregate_monthly_paid_days, approve_correction, derive_daily_attendance,
    ingest_push, poll_device, retry_failed_syncs,
)
from core.db import db
from core.utils import crud_delete, log_audit, new_id, now_iso
from core.webhooks import verify_signature

router = APIRouter(prefix="/biometric", tags=["biometric-attendance"])


def _require_biometric(user: dict) -> dict:
    if is_admin_role(user.get("role")) or user.get("role") == "hr":
        return user
    perms = user.get("module_permissions") or []
    if "biometric" in perms or "hr" in perms:
        return user
    raise HTTPException(status_code=403, detail="Biometric Attendance module access required")


# ───────────────────────── devices ─────────────────────────

@router.get("/devices")
async def list_devices(branch_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_biometric(user)
    filt: dict = {"is_deleted": {"$ne": True}}
    if branch_id:
        filt["branch_id"] = branch_id
    devices = await db.biometric_devices.find(filt, {"_id": 0}).sort("name", 1).to_list(500)
    for d in devices:
        d.pop("push_secret", None)  # never leak the HMAC secret in list responses
    return devices


@router.get("/devices/{device_id}")
async def get_device(device_id: str, user: dict = Depends(get_current_user)):
    _require_biometric(user)
    device = await db.biometric_devices.find_one({"id": device_id}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device.pop("push_secret", None)
    return device


@router.post("/devices")
async def create_device(payload: BiometricDeviceIn, user: dict = Depends(get_current_user)):
    _require_biometric(user)
    data = payload.model_dump()
    if data["integration_mode"] == "poll" and not data.get("host"):
        raise HTTPException(status_code=400, detail="host is required for poll-mode devices")
    import secrets
    doc = {
        "id": new_id(), **data,
        "push_secret": secrets.token_hex(32),
        "last_sync_at": None, "last_sync_status": None, "last_seen_at": None,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.biometric_devices.insert_one(doc)
    await log_audit("CREATE", "biometric_devices", doc["id"], user, new_values=doc)
    return doc  # secret is returned once, on creation only — same convention as API key provisioning


@router.put("/devices/{device_id}")
async def update_device(device_id: str, payload: BiometricDeviceUpdate, user: dict = Depends(get_current_user)):
    _require_biometric(user)
    existing = await db.biometric_devices.find_one({"id": device_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Device not found")
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    updates["updated_at"] = now_iso()
    await db.biometric_devices.update_one({"id": device_id}, {"$set": updates})
    await log_audit("UPDATE", "biometric_devices", device_id, user, old_values=existing, new_values={**existing, **updates})
    updated = await db.biometric_devices.find_one({"id": device_id}, {"_id": 0})
    updated.pop("push_secret", None)
    return updated


@router.post("/devices/{device_id}/rotate-secret")
async def rotate_device_secret(device_id: str, user: dict = Depends(require_admin)):
    """Issue a new HMAC push secret for a device (e.g. after a suspected leak).
    The old secret stops working immediately — the device/gateway config must
    be updated with the new one shown here (shown once, like on creation)."""
    device = await db.biometric_devices.find_one({"id": device_id}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    import secrets
    new_secret = secrets.token_hex(32)
    await db.biometric_devices.update_one({"id": device_id}, {"$set": {"push_secret": new_secret, "updated_at": now_iso()}})
    await log_audit("UPDATE", "biometric_devices", device_id, user, old_values={"push_secret": "***"}, new_values={"push_secret": "***rotated***"})
    return {"device_id": device_id, "push_secret": new_secret}


@router.delete("/devices/{device_id}")
async def delete_device(device_id: str, user: dict = Depends(require_admin)):
    return await crud_delete("biometric_devices", device_id, user=user)


# ───────────────────────── employee <-> device mapping ─────────────────────────

@router.get("/devices/{device_id}/mappings")
async def list_device_mappings(device_id: str, user: dict = Depends(get_current_user)):
    _require_biometric(user)
    rows = await db.employee_device_mappings.find({"device_id": device_id}, {"_id": 0}).to_list(5000)
    emp_ids = list({r["employee_id"] for r in rows})
    emap = {
        e["id"]: f"{e.get('first_name', '')} {e.get('last_name', '')}".strip() + f" ({e.get('employee_code', '')})"
        for e in await db.employees.find({"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "employee_code": 1}).to_list(2000)
    } if emp_ids else {}
    for r in rows:
        r["employee_name"] = emap.get(r["employee_id"], "-")
    return rows


@router.post("/mappings")
async def create_mapping(payload: EmployeeDeviceMappingIn, user: dict = Depends(get_current_user)):
    _require_biometric(user)
    device = await db.biometric_devices.find_one({"id": payload.device_id}, {"_id": 0, "id": 1})
    if not device:
        raise HTTPException(status_code=400, detail="Unknown device_id")
    employee = await db.employees.find_one({"id": payload.employee_id}, {"_id": 0, "id": 1})
    if not employee:
        raise HTTPException(status_code=400, detail="Unknown employee_id")
    existing = await db.employee_device_mappings.find_one(
        {"device_id": payload.device_id, "device_enrollment_id": payload.device_enrollment_id}, {"_id": 0},
    )
    if existing:
        raise HTTPException(status_code=409, detail="This device enrollment id is already mapped to an employee")
    doc = {"id": new_id(), **payload.model_dump(), "is_active": True,
           "created_at": now_iso(), "updated_at": now_iso()}
    await db.employee_device_mappings.insert_one(doc)
    await log_audit("CREATE", "employee_device_mappings", doc["id"], user, new_values=doc)
    return doc


@router.delete("/mappings/{mapping_id}")
async def delete_mapping(mapping_id: str, user: dict = Depends(get_current_user)):
    _require_biometric(user)
    return await crud_delete("employee_device_mappings", mapping_id, user=user)


# ───────────────────────── inbound push webhook (device auth, not user auth) ─────────────────────────

@router.post("/devices/{device_id}/push", status_code=202)
async def device_push(device_id: str, payload: DevicePushIn, request: Request):
    """Inbound punch push from a device/gateway. Authenticated via a per-device
    HMAC signature (X-Webhook-Timestamp/X-Webhook-Signature headers), same
    scheme as core.webhooks.sign_payload/verify_signature — NOT the internal
    JWT cookie flow, since the caller is an unattended device, not a logged-in
    user. 202 (not 200) because ingestion is fire-and-forget from the
    device's point of view; the response body still reports what happened
    for devices/gateways that do log it."""
    device = await db.biometric_devices.find_one({"id": device_id, "is_active": True}, {"_id": 0})
    if not device:
        raise HTTPException(status_code=404, detail="Unknown or inactive device")

    signature = request.headers.get("X-Webhook-Signature")
    timestamp = request.headers.get("X-Webhook-Timestamp")
    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing signature headers")
    body = (await request.body()).decode("utf-8")
    if not verify_signature(device.get("push_secret", ""), body, signature, timestamp):
        raise HTTPException(status_code=401, detail="Invalid signature")

    punches = [
        {
            "device_enrollment_id": p.device_enrollment_id,
            "timestamp": p.timestamp,
            "direction": p.direction,
            "punch_id": p.punch_id,
            "raw": p.raw,
        }
        for p in payload.punches
    ]
    result = await ingest_push(db, device=device, punches=punches)
    return {"ok": True, **result}


# ───────────────────────── sync (manual + scheduled share this path) ─────────────────────────

@router.post("/sync")
async def trigger_sync(payload: SyncTriggerIn, user: dict = Depends(get_current_user)):
    """Manually trigger a poll-mode sync. Push-mode devices have nothing to
    poll (they push on their own schedule) and are skipped with a note."""
    _require_biometric(user)
    if payload.device_id:
        devices = await db.biometric_devices.find({"id": payload.device_id, "is_active": True}, {"_id": 0}).to_list(1)
    else:
        devices = await db.biometric_devices.find({"is_active": True}, {"_id": 0}).to_list(500)

    results = []
    for device in devices:
        if device.get("integration_mode") != "poll":
            results.append({"device_id": device["id"], "device_name": device["name"], "skipped": "push-mode device"})
            continue
        r = await poll_device(db, device=device, trigger="manual", triggered_by=user.get("id", "unknown"))
        results.append({"device_id": device["id"], "device_name": device["name"], **r})

    derived = await derive_daily_attendance(db, tenant_id=user.get("tenant_id"))
    return {"devices_synced": len(results), "results": results, "derived": derived}


@router.post("/sync/retry-failed")
async def retry_failed(user: dict = Depends(require_admin)):
    return await retry_failed_syncs(db)


@router.get("/sync/history")
async def sync_history(
    device_id: Optional[str] = None, status: Optional[str] = None,
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    _require_biometric(user)
    filt: dict = {}
    if device_id:
        filt["device_id"] = device_id
    if status:
        filt["status"] = status
    if date_from or date_to:
        filt["started_at"] = {}
        if date_from:
            filt["started_at"]["$gte"] = date_from
        if date_to:
            filt["started_at"]["$lte"] = date_to + "T23:59:59"
    runs = await db.attendance_sync_runs.find(filt, {"_id": 0}).sort("started_at", -1).to_list(1000)
    device_ids = list({r["device_id"] for r in runs if r.get("device_id")})
    dmap = {d["id"]: d["name"] for d in await db.biometric_devices.find({"id": {"$in": device_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(500)} if device_ids else {}
    for r in runs:
        r["device_name"] = dmap.get(r.get("device_id"), "-")
    return runs


# ───────────────────────── raw logs ─────────────────────────

@router.get("/logs")
async def raw_logs(
    device_id: Optional[str] = None, employee_id: Optional[str] = None,
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    processed: Optional[bool] = None,
    user: dict = Depends(get_current_user),
):
    _require_biometric(user)
    filt: dict = {}
    if device_id:
        filt["device_id"] = device_id
    if employee_id:
        filt["employee_id"] = employee_id
    if processed is not None:
        filt["processed"] = processed
    if date_from or date_to:
        filt["log_time"] = {}
        if date_from:
            filt["log_time"]["$gte"] = f"{date_from}T00:00:00"
        if date_to:
            filt["log_time"]["$lte"] = f"{date_to}T23:59:59"
    rows = await db.attendance_logs.find(filt, {"_id": 0}).sort("log_time", -1).to_list(5000)
    emp_ids = list({r["employee_id"] for r in rows if r.get("employee_id")})
    emap = {
        e["id"]: f"{e.get('first_name', '')} {e.get('last_name', '')}".strip() + f" ({e.get('employee_code', '')})"
        for e in await db.employees.find({"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "employee_code": 1}).to_list(2000)
    } if emp_ids else {}
    for r in rows:
        r["employee_name"] = emap.get(r.get("employee_id"), "Unmapped")
    return rows


# ───────────────────────── attendance rules ─────────────────────────

@router.get("/rules")
async def list_rules(user: dict = Depends(get_current_user)):
    _require_biometric(user)
    return await db.attendance_rules.find({}, {"_id": 0}).sort("created_at", 1).to_list(200)


@router.post("/rules")
async def create_rule(payload: AttendanceRuleIn, user: dict = Depends(get_current_user)):
    _require_biometric(user)
    if payload.shift_id:
        existing = await db.attendance_rules.find_one({"shift_id": payload.shift_id, "is_active": True}, {"_id": 0})
    else:
        existing = await db.attendance_rules.find_one({"shift_id": None, "is_active": True}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=409, detail="An active rule already exists for this shift (edit it instead)")
    doc = {"id": new_id(), **payload.model_dump(), "created_at": now_iso(), "updated_at": now_iso()}
    await db.attendance_rules.insert_one(doc)
    await log_audit("CREATE", "attendance_rules", doc["id"], user, new_values=doc)
    return doc


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, payload: AttendanceRuleUpdate, user: dict = Depends(get_current_user)):
    _require_biometric(user)
    existing = await db.attendance_rules.find_one({"id": rule_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    updates["updated_at"] = now_iso()
    await db.attendance_rules.update_one({"id": rule_id}, {"$set": updates})
    await log_audit("UPDATE", "attendance_rules", rule_id, user, old_values=existing, new_values={**existing, **updates})
    return await db.attendance_rules.find_one({"id": rule_id}, {"_id": 0})


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, user: dict = Depends(get_current_user)):
    _require_biometric(user)
    return await crud_delete("attendance_rules", rule_id, user=user)


# ───────────────────────── attendance correction / approval ─────────────────────────

@router.get("/corrections")
async def list_corrections(status: Optional[str] = None, employee_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_biometric(user)
    filt: dict = {}
    if status:
        filt["status"] = status
    if employee_id:
        filt["employee_id"] = employee_id
    rows = await db.attendance_corrections.find(filt, {"_id": 0}).sort("requested_at", -1).to_list(2000)
    emp_ids = list({r["employee_id"] for r in rows})
    emap = {
        e["id"]: f"{e.get('first_name', '')} {e.get('last_name', '')}".strip() + f" ({e.get('employee_code', '')})"
        for e in await db.employees.find({"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "employee_code": 1}).to_list(2000)
    } if emp_ids else {}
    for r in rows:
        r["employee_name"] = emap.get(r["employee_id"], "-")
    return rows


@router.post("/corrections")
async def submit_correction(payload: AttendanceCorrectionIn, user: dict = Depends(get_current_user)):
    """Any authenticated user can submit a correction request for themselves
    (self-service, mirrors routers/hr_attendance.py's /me/* pattern); HR/admin
    can submit on behalf of any employee. Either way it starts PENDING —
    submitting never changes attendance directly, only approval does."""
    employee = await db.employees.find_one({"id": payload.employee_id}, {"_id": 0, "id": 1})
    if not employee:
        raise HTTPException(status_code=400, detail="Unknown employee_id")
    if not payload.requested_check_in and not payload.requested_check_out and not payload.requested_status:
        raise HTTPException(status_code=400, detail="Provide at least a requested check-in/out time or a requested status")
    doc = {
        "id": new_id(), **payload.model_dump(), "status": "PENDING",
        "requested_by": user.get("id"), "requested_at": now_iso(),
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.attendance_corrections.insert_one(doc)
    await log_audit("CREATE", "attendance_corrections", doc["id"], user, new_values=doc)
    return doc


@router.post("/corrections/{correction_id}/decide")
async def decide_correction(correction_id: str, payload: AttendanceCorrectionDecision, user: dict = Depends(get_current_user)):
    _require_biometric(user)
    correction = await db.attendance_corrections.find_one({"id": correction_id}, {"_id": 0})
    if not correction:
        raise HTTPException(status_code=404, detail="Correction request not found")
    if correction["status"] != "PENDING":
        raise HTTPException(status_code=409, detail=f"Correction already {correction['status'].lower()}")

    if payload.status == "REJECTED":
        await db.attendance_corrections.update_one(
            {"id": correction_id},
            {"$set": {"status": "REJECTED", "decided_by": user.get("id"), "decided_at": now_iso(),
                      "rejection_reason": payload.rejection_reason, "updated_at": now_iso()}},
        )
        await log_audit("UPDATE", "attendance_corrections", correction_id, user, old_values=correction, new_values={"status": "REJECTED"})
        return {"status": "REJECTED"}

    try:
        result = await approve_correction(db, correction=correction, decided_by=user.get("id", "unknown"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await log_audit("UPDATE", "attendance_corrections", correction_id, user, old_values=correction, new_values={"status": "APPROVED", **result})
    return {"status": "APPROVED", "attendance": result}


# ───────────────────────── payroll aggregate ─────────────────────────

@router.post("/payroll/aggregate")
async def run_monthly_aggregate(payload: MonthlyAggregateRunIn, user: dict = Depends(get_current_user)):
    """Roll a month's daily attendance + approved leave into the paid_days
    summary routers/payroll.py's LOP calculation reads. Run this before
    generating a payroll run for the period."""
    _require_biometric(user)
    return await aggregate_monthly_paid_days(db, period=payload.period, employee_ids=payload.employee_ids)


# ───────────────────────── dashboard & device health ─────────────────────────

@router.get("/dashboard")
async def dashboard(user: dict = Depends(get_current_user)):
    _require_biometric(user)
    today = date.today().isoformat()

    devices = await db.biometric_devices.find({"is_deleted": {"$ne": True}}, {"_id": 0}).to_list(500)
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(hours=24)
    device_health = []
    healthy, stale, never_synced = 0, 0, 0
    for d in devices:
        last_seen = d.get("last_seen_at")
        health = "never_synced"
        if last_seen:
            try:
                seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                health = "healthy" if seen_dt >= stale_cutoff else "stale"
            except Exception:
                health = "unknown"
        if health == "healthy":
            healthy += 1
        elif health == "stale":
            stale += 1
        else:
            never_synced += 1
        device_health.append({
            "device_id": d["id"], "device_name": d["name"], "is_active": d.get("is_active", True),
            "last_seen_at": last_seen, "last_sync_status": d.get("last_sync_status"), "health": health,
        })

    todays_logs = await db.attendance_logs.count_documents({"log_time": {"$gte": f"{today}T00:00:00", "$lte": f"{today}T23:59:59"}})
    unmapped_recent = await db.attendance_logs.count_documents({
        "log_time": {"$gte": f"{today}T00:00:00"}, "employee_id": None,
    })
    pending_runs = await db.attendance_sync_runs.count_documents({"status": {"$in": ["running", "failed"]}})
    total_present_today = await db.attendance.count_documents({"date": today, "status": {"$in": ["PRESENT", "LATE"]}})
    total_active_employees = await db.employees.count_documents({"status": "active"})

    return {
        "devices_total": len(devices), "devices_healthy": healthy, "devices_stale": stale,
        "devices_never_synced": never_synced, "device_health": device_health,
        "punches_today": todays_logs, "unmapped_punches_recent": unmapped_recent,
        "pending_or_failed_sync_runs": pending_runs,
        "present_today": total_present_today, "active_employees": total_active_employees,
    }
