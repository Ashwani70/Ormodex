"""eSSL Biometric Attendance Integration — sync engine.

Two ingestion paths feed the same pipeline:
  1. Push: a device (or its ADMS/cloud gateway) POSTs punches to our webhook,
     authenticated per-device via HMAC (core.webhooks.sign_payload/verify_signature),
     same pattern as the outbound webhook delivery in Module K.
  2. Poll: a scheduled or manually-triggered sync pulls punches from a device's
     REST endpoint via EsslDeviceAdapter.

Both paths converge on `_ingest_punches`, which dedups (unique dedup_key),
resolves device_enrollment_id -> employee_id via EmployeeDeviceMapping, and
writes raw rows to attendance_logs. A separate derivation step
(`derive_daily_attendance`) folds unprocessed raw punches into the daily
`attendance` summary (status/check-in/check-out/late/OT), reusing the same
shift-resolution + late-detection convention as routers/hr_attendance.py so
manual, QR, and biometric-sourced attendance stay consistent. A monthly
aggregator (`aggregate_monthly_paid_days`) then rolls daily attendance +
approved leave into the `{employee_id, period, paid_days}` summary row that
routers/payroll.py's LOP calculation reads (that row was never written by
anything before this module — payroll's LOP silently defaulted to zero).
"""
from __future__ import annotations

import asyncio
import hashlib
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

from .utils import new_id, now_iso
from .webhooks import backoff_delay, next_attempt_time

MAX_SYNC_ATTEMPTS = 5


# ───────────────────────── dedup ─────────────────────────

def _dedup_key(device_id: str, punch_id: Optional[str], device_enrollment_id: str, timestamp: str) -> str:
    """Stable key so the same punch ingested twice (push retry, poll overlap
    window, webhook re-delivery) is a no-op, not a duplicate row. Prefers the
    device's own punch id when it provides one; falls back to a composite of
    device+enrollment+timestamp (rounded to the minute — most eSSL terminals
    only report minute-resolution punches, so two truly distinct punches in
    the same device-minute for the same person are vanishingly rare and, if
    they did occur, are indistinguishable duplicates from any consumer's
    point of view anyway)."""
    if punch_id:
        raw = f"{device_id}:punch:{punch_id}"
    else:
        raw = f"{device_id}:{device_enrollment_id}:{timestamp[:16]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ───────────────────────── device adapter ─────────────────────────

class EsslDeviceAdapter:
    """HTTP client for pull-mode devices/gateways. Assumes the device or its
    local gateway exposes a reachable REST endpoint (true for on-prem/VPN
    deployments — a cloud-hosted backend cannot reach a LAN-only terminal
    directly). Endpoint shape varies across eSSL product lines (eTimeTrackLite,
    BioTime/ADMS-compatible terminals, X-series), so `api_path` is configurable
    per device rather than hardcoded; this default assumes a JSON array of
    punch records at `GET {host}:{port}{api_path}?from=<iso>`."""

    def __init__(self, device: dict, *, timeout: float = 15.0):
        self.device = device
        self.timeout = timeout

    def _base_url(self) -> str:
        host = self.device["host"]
        port = self.device.get("port") or 4370
        return f"http://{host}:{port}"

    async def fetch_punches(self, since: Optional[str]) -> list[dict]:
        """Returns raw punch dicts: {device_enrollment_id, timestamp, direction?, punch_id?, raw}.
        Raises on transport/HTTP failure — caller (poll_device) records it as a failed sync attempt."""
        path = self.device.get("api_path") or "/iclock/getrequest"
        url = f"{self._base_url()}{path}"
        params = {"from": since} if since else {}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            body = resp.json()

        records = body if isinstance(body, list) else body.get("records", [])
        out = []
        for r in records:
            out.append({
                "device_enrollment_id": str(r.get("user_id") or r.get("enrollment_id") or r.get("pin", "")),
                "timestamp": r.get("timestamp") or r.get("check_time") or r.get("time", ""),
                "direction": r.get("direction") or r.get("status"),
                "punch_id": str(r["id"]) if r.get("id") is not None else None,
                "raw": r,
            })
        return out


# ───────────────────────── ingestion (shared by push + poll) ─────────────────────────

async def _ingest_punches(db, *, device: dict, punches: list[dict], source: str,
                          sync_run_id: Optional[str]) -> dict:
    """Resolve enrollment->employee, dedup, and write raw attendance_logs rows.
    Returns {fetched, new, duplicate, unmapped}."""
    tenant_id = device.get("tenant_id")
    device_id = device["id"]

    mappings = await db.employee_device_mappings.find(
        {"device_id": device_id, "is_active": True}, {"_id": 0},
    ).to_list(5000)
    enrollment_to_employee = {m["device_enrollment_id"]: m["employee_id"] for m in mappings}

    fetched = len(punches)
    new_count = 0
    duplicate_count = 0
    unmapped_count = 0

    for p in punches:
        enrollment_id = p.get("device_enrollment_id")
        employee_id = enrollment_to_employee.get(enrollment_id)
        if not employee_id:
            unmapped_count += 1
            # Still recorded (not silently discarded) so an admin can see it in
            # Raw Logs / the dashboard's unmapped counter, map the enrollment
            # id, and reprocess — but never folded into daily attendance while
            # employee_id is NULL (derive_daily_attendance filters on it).

        key = _dedup_key(device_id, p.get("punch_id"), enrollment_id, p["timestamp"])
        existing = await db.attendance_logs.find_one({"dedup_key": key}, {"_id": 0, "id": 1})
        if existing:
            duplicate_count += 1
            continue

        await db.attendance_logs.insert_one({
            "id": new_id(),
            "tenant_id": tenant_id,
            "employee_id": employee_id,
            "employee_code": enrollment_id if not employee_id else None,
            "log_time": p["timestamp"],
            "direction": p.get("direction"),
            "device_id": device_id,
            "dedup_key": key,
            "sync_run_id": sync_run_id,
            "source": source,
            "raw_payload": p.get("raw"),
            "processed": employee_id is None,  # unmapped punches are never "pending processing"
            "created_at": now_iso(),
        })
        new_count += 1

    if new_count > 0:
        await db.biometric_devices.update_one(
            {"id": device_id}, {"$set": {"last_seen_at": now_iso()}},
        )

    return {"fetched": fetched, "new": new_count, "duplicate": duplicate_count, "unmapped": unmapped_count}


async def ingest_push(db, *, device: dict, punches: list[dict]) -> dict:
    """Entry point for the webhook push path — no sync run wraps a push (each
    push is its own event), but the device's health/last_seen is still updated."""
    return await _ingest_punches(db, device=device, punches=punches, source="webhook", sync_run_id=None)


# ───────────────────────── poll / scheduled sync ─────────────────────────

async def poll_device(db, *, device: dict, trigger: str, triggered_by: str) -> dict:
    """Run one poll-mode sync attempt for a device: create a running
    AttendanceSyncRun row, fetch punches since last_sync_at, ingest them, and
    mark the run success/failed. On failure, schedules a retry (same
    exponential-backoff convention as core.webhooks.deliver_pending) up to
    MAX_SYNC_ATTEMPTS, after which the device's last_sync_status is "failed"
    and no further automatic retry is scheduled for this run."""
    run_id = new_id()
    started = now_iso()
    await db.attendance_sync_runs.insert_one({
        "id": run_id, "tenant_id": device.get("tenant_id"), "device_id": device["id"],
        "trigger": trigger, "status": "running", "started_at": started,
        "punches_fetched": 0, "punches_new": 0, "punches_duplicate": 0,
        "attempt": 1, "triggered_by": triggered_by, "created_at": started,
    })

    try:
        adapter = EsslDeviceAdapter(device)
        punches = await adapter.fetch_punches(device.get("last_sync_at"))
        result = await _ingest_punches(db, device=device, punches=punches, source="poll", sync_run_id=run_id)
        await db.attendance_sync_runs.update_one(
            {"id": run_id},
            {"$set": {
                "status": "success", "finished_at": now_iso(),
                "punches_fetched": result["fetched"], "punches_new": result["new"],
                "punches_duplicate": result["duplicate"],
            }},
        )
        await db.biometric_devices.update_one(
            {"id": device["id"]},
            {"$set": {"last_sync_at": now_iso(), "last_sync_status": "success", "last_seen_at": now_iso()}},
        )
        return {"run_id": run_id, "status": "success", **result}
    except Exception as exc:
        await db.attendance_sync_runs.update_one(
            {"id": run_id},
            {"$set": {"status": "failed", "finished_at": now_iso(), "error_message": str(exc)[:2000],
                      "next_attempt_at": next_attempt_time(1)}},
        )
        await db.biometric_devices.update_one(
            {"id": device["id"]}, {"$set": {"last_sync_status": "failed"}},
        )
        return {"run_id": run_id, "status": "failed", "error": str(exc)}


async def retry_failed_syncs(db) -> dict:
    """Retry sync runs that failed and are due (mirrors core.webhooks.deliver_pending's
    pending/retrying queue-processing shape). Intended to be called by the same
    scheduler tick as poll_device, or hit manually via POST /biometric/sync/retry-failed."""
    now = datetime.now(timezone.utc).isoformat()
    due = await db.attendance_sync_runs.find(
        {"status": "failed", "next_attempt_at": {"$lte": now}, "attempt": {"$lt": MAX_SYNC_ATTEMPTS}},
        {"_id": 0},
    ).to_list(200)

    retried, given_up = 0, 0
    for run in due:
        device = await db.biometric_devices.find_one({"id": run["device_id"]}, {"_id": 0})
        if not device or not device.get("is_active"):
            continue
        attempt = run["attempt"] + 1
        try:
            adapter = EsslDeviceAdapter(device)
            punches = await adapter.fetch_punches(device.get("last_sync_at"))
            result = await _ingest_punches(db, device=device, punches=punches, source="poll", sync_run_id=run["id"])
            await db.attendance_sync_runs.update_one(
                {"id": run["id"]},
                {"$set": {"status": "success", "finished_at": now_iso(), "attempt": attempt,
                          "punches_fetched": result["fetched"], "punches_new": result["new"],
                          "punches_duplicate": result["duplicate"]}},
            )
            await db.biometric_devices.update_one(
                {"id": device["id"]},
                {"$set": {"last_sync_at": now_iso(), "last_sync_status": "success", "last_seen_at": now_iso()}},
            )
            retried += 1
        except Exception as exc:
            if attempt >= MAX_SYNC_ATTEMPTS:
                await db.attendance_sync_runs.update_one(
                    {"id": run["id"]},
                    {"$set": {"status": "failed", "attempt": attempt, "finished_at": now_iso(),
                              "error_message": str(exc)[:2000], "next_attempt_at": None}},
                )
                given_up += 1
            else:
                await db.attendance_sync_runs.update_one(
                    {"id": run["id"]},
                    {"$set": {"attempt": attempt, "error_message": str(exc)[:2000],
                              "next_attempt_at": next_attempt_time(attempt)}},
                )
    return {"due": len(due), "retried": retried, "given_up": given_up}


# ───────────────────────── derivation: raw punches -> daily attendance ─────────────────────────

async def _resolve_rule(db, tenant_id: Optional[str], shift_id: Optional[str]) -> dict:
    rule = None
    if shift_id:
        rule = await db.attendance_rules.find_one(
            {"tenant_id": tenant_id, "shift_id": shift_id, "is_active": True}, {"_id": 0},
        )
    if not rule:
        rule = await db.attendance_rules.find_one(
            {"tenant_id": tenant_id, "shift_id": None, "is_active": True}, {"_id": 0},
        )
    return rule or {
        "late_grace_minutes": 10, "early_leave_grace_minutes": 10,
        "half_day_threshold_hours": 4.0, "full_day_threshold_hours": 8.0,
        "overtime_after_hours": 9.0, "missing_punch_action": "flag",
    }


async def _resolve_shift(db, employee: dict) -> dict:
    sid = employee.get("shift_id")
    if sid:
        s = await db.shifts.find_one({"id": sid}, {"_id": 0})
        if s:
            return s
    return {"start_time": "09:00", "end_time": "18:00"}


def _worked_hours(check_in: str, check_out: str) -> float:
    try:
        a = datetime.strptime(check_in, "%H:%M")
        b = datetime.strptime(check_out, "%H:%M")
        if b < a:
            # Check-out's clock time is earlier than check-in's — the shift
            # crossed midnight (e.g. IN 22:10, OUT 06:05 the next calendar
            # day). Both were parsed onto the same reference date since only
            # HH:MM is stored, so add a day to the checkout side to get the
            # real elapsed duration instead of a negative one clamped to 0.
            b += timedelta(days=1)
        diff = (b - a).total_seconds() / 3600
        return round(max(diff, 0.0), 2)
    except Exception:
        return 0.0


def _is_late(check_in: str, shift_start: str, grace_minutes: int) -> bool:
    try:
        ci = datetime.strptime(check_in, "%H:%M")
        s_start = datetime.strptime(shift_start, "%H:%M")
        return (ci - s_start).total_seconds() / 60 > grace_minutes
    except Exception:
        return False


def _is_early_leave(check_out: str, shift_end: str, grace_minutes: int) -> bool:
    try:
        co = datetime.strptime(check_out, "%H:%M")
        s_end = datetime.strptime(shift_end, "%H:%M")
        return (s_end - co).total_seconds() / 60 > grace_minutes
    except Exception:
        return False


def _shift_day_for_punch(dt: datetime, shift: dict) -> date:
    """Which shift-day a punch belongs to. For a normal shift this is just
    the punch's own calendar date. For a shift flagged crosses_midnight
    (e.g. 22:00-06:00), a punch that lands before the shift's own start_time
    is the tail end of the PREVIOUS day's shift, not the start of a new one —
    a checkout can legitimately land some time after the nominal end_time
    (grace period, running late, unpaid overtime), so the cutoff is the
    shift's start_time (the point at which a genuinely NEW shift-day's first
    IN punch could occur) rather than its end_time. Without this, a
    night-shift punch-out at 00:30 (or 06:05, or 08:00) would be grouped as
    its own day — an unmatched single IN-less punch — and the real shift day
    would show a missing check-out instead of a complete pair."""
    if not shift.get("crosses_midnight"):
        return dt.date()
    try:
        start_t = datetime.strptime(shift.get("start_time", "22:00"), "%H:%M").time()
    except Exception:
        start_t = datetime.strptime("22:00", "%H:%M").time()
    if dt.time() < start_t:
        return (dt - timedelta(days=1)).date()
    return dt.date()


async def _is_weekly_off_or_holiday(db, employee: dict, shift: dict, d: date) -> Optional[str]:
    """Returns "WEEKEND" or "HOLIDAY" if `d` is a non-working day for this
    employee, else None. Checked BEFORE deriving status from punches so a
    stray office visit on a day off doesn't get mis-posted as LATE/HALF_DAY,
    and a legitimate no-punch on a day off is never flagged as a missing punch.
    Not tenant-scoped, matching routers/hr_setup.py's holiday endpoints, which
    don't filter by tenant either (single-tenant deployment)."""
    weekly_off_days = shift.get("weekly_off_days") or [0]
    # shift.weekly_off_days uses 0=Sun..6=Sat; Python's date.weekday() is 0=Mon..6=Sun.
    shift_dow = (d.weekday() + 1) % 7  # Mon(0)->1 ... Sun(6)->0
    if shift_dow in weekly_off_days:
        return "WEEKEND"

    branch_id = employee.get("branch_id")
    d_iso = d.isoformat()
    holiday = await db.holidays.find_one(
        {"holiday_date": d_iso, "branch_id": branch_id}, {"_id": 0, "id": 1},
    ) if branch_id else None
    if not holiday:
        holiday = await db.holidays.find_one({"holiday_date": d_iso, "branch_id": None}, {"_id": 0, "id": 1})
    return "HOLIDAY" if holiday else None


def _derive_attendance_patch(
    shift: dict, rule: dict, first_in: Optional[str], last_out: Optional[str], off_reason: Optional[str],
) -> dict:
    """Pure status/hours/late/OT derivation from a resolved check-in/check-out
    pair, shared by derive_daily_attendance's per-punch-group loop AND
    approve_correction (so a manually-approved correction recomputes late/OT/
    status through the exact same rule logic as a device-derived day, instead
    of the approver having to compute those by hand)."""
    if off_reason:
        worked = _worked_hours(first_in, last_out) if first_in and last_out else 0.0
        return {
            "check_in": first_in, "check_out": last_out, "status": off_reason,
            "working_hours": worked, "overtime_hours": 0.0, "source": "biometric",
            "late": False, "early_leave": False, "missing_punch": False,
            "updated_at": now_iso(),
        }

    worked = _worked_hours(first_in, last_out) if first_in and last_out else 0.0
    late = _is_late(first_in, shift.get("start_time", "09:00"), rule["late_grace_minutes"]) if first_in else False
    early = _is_early_leave(last_out, shift.get("end_time", "18:00"), rule["early_leave_grace_minutes"]) if first_in and last_out else False

    if not first_in:
        status = "ABSENT"
        missing_punch = True
    elif last_out is None:
        status = "PRESENT" if rule["missing_punch_action"] != "absent" else "ABSENT"
        missing_punch = True
    elif worked >= rule["full_day_threshold_hours"]:
        status = "LATE" if late else "PRESENT"
        missing_punch = False
    elif worked >= rule["half_day_threshold_hours"]:
        status = "HALF_DAY"
        missing_punch = False
    else:
        status = "HALF_DAY"
        missing_punch = False

    overtime = max(0.0, round(worked - rule["overtime_after_hours"], 2)) if worked else 0.0
    return {
        "check_in": first_in, "check_out": last_out, "status": status,
        "working_hours": worked, "overtime_hours": overtime,
        "source": "biometric", "late": late, "early_leave": early,
        "missing_punch": missing_punch, "updated_at": now_iso(),
    }


async def derive_daily_attendance(db, *, tenant_id: Optional[str], target_date: Optional[str] = None) -> dict:
    """Fold unprocessed raw punches into the daily `attendance` summary.

    Groups unprocessed attendance_logs by (employee_id, shift-day) — shift-day
    normally equals the punch's calendar date, but for a crosses_midnight
    shift an early-morning punch is attributed to the PREVIOUS day (see
    _shift_day_for_punch) so a night shift's IN/OUT pair lands on one row
    instead of splitting into two broken ones. Takes the earliest punch as
    check-in and latest as check-out (a person may punch more than twice a
    day — only first/last matter for hours/late/early, same convention as
    the existing manual check-in/check-out flow). Before deriving status from
    punches, checks whether the shift-day is a weekly off or holiday for this
    employee (_is_weekly_off_or_holiday) — those days are marked WEEKEND/
    HOLIDAY outright and never flagged as a missing punch, regardless of
    whether punches exist. Applies the resolved AttendanceRule (falling back
    to shift-independent defaults), and upserts into `attendance` with
    source="biometric" — the same table and shape routers/hr_attendance.py
    already writes, so Attendance Register / reports are agnostic to how a
    day's attendance was captured.
    """
    filt: dict = {"processed": False}
    if tenant_id:
        filt["tenant_id"] = tenant_id
    if target_date:
        filt["log_time"] = {"$gte": f"{target_date}T00:00:00", "$lte": f"{target_date}T23:59:59"}
    raw = await db.attendance_logs.find(filt, {"_id": 0}).to_list(20000)
    if not raw:
        return {"processed_days": 0, "processed_punches": 0}

    # Punches are grouped per-employee first (not per-employee-date) because
    # a crosses_midnight shift needs each employee's OWN shift to decide which
    # calendar day a punch belongs to — that requires resolving the employee/
    # shift before grouping, not after.
    by_employee: dict[str, list[dict]] = {}
    for p in raw:
        try:
            dt = datetime.fromisoformat(p["log_time"].replace("Z", "+00:00"))
        except Exception:
            continue
        by_employee.setdefault(p["employee_id"], []).append({**p, "_dt": dt})

    processed_ids = []
    days_written = 0
    for employee_id, punches in by_employee.items():
        employee = await db.employees.find_one({"id": employee_id}, {"_id": 0})
        if not employee:
            continue
        shift = await _resolve_shift(db, employee)
        rule = await _resolve_rule(db, tenant_id, employee.get("shift_id"))

        by_shift_day: dict = {}
        for p in punches:
            shift_day = _shift_day_for_punch(p["_dt"], shift)
            by_shift_day.setdefault(shift_day, []).append(p)

        for shift_day, day_punches in by_shift_day.items():
            day_punches.sort(key=lambda p: p["_dt"])
            first_in = day_punches[0]["_dt"].strftime("%H:%M")
            last_out = day_punches[-1]["_dt"].strftime("%H:%M") if len(day_punches) > 1 else None
            d = shift_day.isoformat()

            off_reason = await _is_weekly_off_or_holiday(db, employee, shift, shift_day)
            patch = _derive_attendance_patch(shift, rule, first_in, last_out, off_reason)

            existing = await db.attendance.find_one({"employee_id": employee_id, "date": d}, {"_id": 0})
            if existing:
                await db.attendance.update_one({"employee_id": employee_id, "date": d}, {"$set": patch})
            else:
                await db.attendance.insert_one({
                    "id": new_id(), "employee_id": employee_id, "date": d,
                    "created_at": now_iso(), **patch,
                })
            days_written += 1
            processed_ids.extend(p["id"] for p in day_punches)

    for i in range(0, len(processed_ids), 500):
        chunk = processed_ids[i:i + 500]
        await db.attendance_logs.update_many(
            {"id": {"$in": chunk}}, {"$set": {"processed": True, "processed_at": now_iso()}},
        )

    return {"processed_days": days_written, "processed_punches": len(processed_ids)}


# ───────────────────────── monthly payroll aggregate ─────────────────────────

def _period_days(mm: int, yyyy: int) -> int:
    return monthrange(yyyy, mm)[1]


async def aggregate_monthly_paid_days(db, *, period: str, employee_ids: Optional[list[str]] = None) -> dict:
    """Roll a month's daily `attendance` + approved `leaves` into the
    `{employee_id, period, paid_days}` summary row that routers/payroll.py's
    LOP calculation reads (routers/payroll.py:480-485). This row was
    previously never written by anything, so every payroll run silently
    treated every employee as zero-LOP; this aggregator is what actually
    makes biometric attendance affect payroll.

    paid_days = days present/late/half-day(0.5) + approved leave days marked
    paid + weekends/holidays (treated as paid, matching the existing
    attendance.py STATUS_OPTIONS which already has WEEKEND/HOLIDAY as
    non-absence statuses) - unpaid leave/absent days.
    """
    mm = int(period[:2])
    yyyy = int(period[2:])
    total_days = _period_days(mm, yyyy)
    date_from = f"{yyyy:04d}-{mm:02d}-01"
    date_to = f"{yyyy:04d}-{mm:02d}-{total_days:02d}"

    filt: dict = {"date": {"$gte": date_from, "$lte": date_to}}
    if employee_ids:
        filt["employee_id"] = {"$in": employee_ids}
    else:
        filt = {"date": {"$gte": date_from, "$lte": date_to}}
    daily = await db.attendance.find(filt, {"_id": 0}).to_list(200000)

    by_employee: dict[str, list[dict]] = {}
    for row in daily:
        by_employee.setdefault(row["employee_id"], []).append(row)

    target_employee_ids = employee_ids or list(by_employee.keys())
    written = 0
    for employee_id in target_employee_ids:
        rows = by_employee.get(employee_id, [])
        paid_days = 0.0
        for r in rows:
            status = r.get("status")
            if status in ("PRESENT", "LATE", "HOLIDAY", "WEEKEND"):
                paid_days += 1.0
            elif status == "HALF_DAY":
                paid_days += 0.5
            elif status == "LEAVE":
                lv = await db.leaves.find_one(
                    {"employee_id": employee_id, "status": "APPROVED",
                     "from_date": {"$lte": r["date"]}, "to_date": {"$gte": r["date"]}},
                    {"_id": 0},
                )
                if lv:
                    lt = await db.leave_types.find_one({"id": lv.get("leave_type_id")}, {"_id": 0})
                    if (lt or {}).get("paid", True):
                        paid_days += 1.0
            # ABSENT and unmatched LEAVE contribute 0.

        existing = await db.attendance.find_one({"employee_id": employee_id, "period": period}, {"_id": 0})
        patch = {"employee_id": employee_id, "period": period, "paid_days": round(paid_days, 2),
                 "total_days": total_days, "updated_at": now_iso()}
        if existing:
            await db.attendance.update_one({"employee_id": employee_id, "period": period}, {"$set": patch})
        else:
            await db.attendance.insert_one({"id": new_id(), "date": None, "created_at": now_iso(), **patch})
        written += 1

    return {"period": period, "employees_processed": written, "total_days": total_days}


# ───────────────────────── attendance correction / approval ─────────────────────────

async def approve_correction(db, *, correction: dict, decided_by: str) -> dict:
    """Re-derive the corrected day's attendance row through the same rule/
    shift logic as a device-derived day (_derive_attendance_patch), rather
    than writing the requester's raw input straight into `attendance` —
    late/OT/status must stay consistent regardless of whether a day's
    check-in/check-out came from a device or a correction. If
    requested_status is given with no punch times (e.g. "mark me PRESENT,
    the device was down all day"), that status is used as-is with zero
    computed hours rather than derived, since there's nothing to derive from.
    """
    employee = await db.employees.find_one({"id": correction["employee_id"]}, {"_id": 0})
    if not employee:
        raise ValueError(f"Employee '{correction['employee_id']}' not found")
    shift = await _resolve_shift(db, employee)
    rule = await _resolve_rule(db, employee.get("tenant_id"), employee.get("shift_id"))
    shift_day = date.fromisoformat(correction["attendance_date"])

    first_in = correction.get("requested_check_in")
    last_out = correction.get("requested_check_out")

    if correction.get("requested_status") and not (first_in and last_out):
        patch = {
            "check_in": first_in, "check_out": last_out, "status": correction["requested_status"],
            "working_hours": 0.0, "overtime_hours": 0.0, "source": "correction",
            "late": False, "early_leave": False, "missing_punch": False, "updated_at": now_iso(),
        }
    else:
        off_reason = await _is_weekly_off_or_holiday(db, employee, shift, shift_day)
        patch = _derive_attendance_patch(shift, rule, first_in, last_out, off_reason)
        patch["source"] = "correction"

    d = correction["attendance_date"]
    existing = await db.attendance.find_one({"employee_id": correction["employee_id"], "date": d}, {"_id": 0})
    if existing:
        await db.attendance.update_one({"employee_id": correction["employee_id"], "date": d}, {"$set": patch})
    else:
        await db.attendance.insert_one({
            "id": new_id(), "employee_id": correction["employee_id"], "date": d,
            "created_at": now_iso(), **patch,
        })

    await db.attendance_corrections.update_one(
        {"id": correction["id"]},
        {"$set": {"status": "APPROVED", "decided_by": decided_by, "decided_at": now_iso(), "updated_at": now_iso()}},
    )
    return patch


# ───────────────────────── in-process scheduler ─────────────────────────
#
# No job queue exists in this stack (no Celery/Redis/APScheduler — confirmed
# absent app-wide; only FastAPI BackgroundTasks and admin-triggered sweep
# endpoints like /webhooks/deliver and /approvals/sla/sweep exist elsewhere,
# meant to be hit by an external cron). "Scheduled synchronization" for this
# module is a first-class requirement, not an incidental one, so a minimal
# asyncio interval loop is started at app startup instead — it calls the same
# poll_device()/derive_daily_attendance() functions the manual /biometric/sync
# endpoint uses, so manual and scheduled sync are one code path, not two.
# Single-process only (same limitation already documented for the rate
# limiter elsewhere in this codebase) — fine for this single-instance deployment.

_SCHEDULER_TICK_SECONDS = 60


async def _run_due_device_syncs(db) -> None:
    devices = await db.biometric_devices.find(
        {"is_active": True, "integration_mode": "poll"}, {"_id": 0},
    ).to_list(500)
    now = datetime.now(timezone.utc)
    for device in devices:
        interval = int(device.get("poll_interval_seconds") or 300)
        last_sync = device.get("last_sync_at")
        due = True
        if last_sync:
            try:
                last_dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
                due = (now - last_dt).total_seconds() >= interval
            except Exception:
                due = True
        if due:
            await poll_device(db, device=device, trigger="scheduled", triggered_by="system")


async def scheduler_loop(db, *, tick_seconds: int = _SCHEDULER_TICK_SECONDS) -> None:
    """Runs forever until cancelled. Each tick: sync any poll-mode device
    whose interval has elapsed, retry any due failed sync runs, then fold new
    raw punches into daily attendance. Exceptions in one tick are logged
    (import kept local to avoid a hard dependency on server.py's logger
    config at module-import time) and never kill the loop — a bad device or a
    transient DB blip must not silently stop scheduling for every other device.
    """
    import logging
    logger = logging.getLogger("biometric_scheduler")
    while True:
        try:
            await _run_due_device_syncs(db)
            await retry_failed_syncs(db)
            await derive_daily_attendance(db, tenant_id=None)
        except Exception:
            logger.exception("Biometric scheduler tick failed (will retry next tick)")
        await asyncio.sleep(tick_seconds)
