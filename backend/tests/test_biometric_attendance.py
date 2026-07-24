"""eSSL Biometric Attendance Integration: dedup, ingestion, derivation, retry/backoff, payroll aggregate.

Drives core.biometric_sync against an in-memory async Mongo fake (same style
as test_voucher_engine.py). Proves:
  - the same punch ingested twice (push retry, poll overlap) dedups, not duplicates
  - unmapped device enrollment ids are recorded (not silently dropped) but never
    folded into daily attendance
  - daily derivation reuses the shift/late-grace convention and computes OT
  - a failed poll schedules a retry with the same backoff curve as core.webhooks
  - the monthly payroll aggregate writes the {employee_id, period, paid_days}
    row routers/payroll.py's LOP calculation reads, and a period-row never
    collides with a daily row on a date-range query
"""
import asyncio
from datetime import datetime, timedelta, timezone

import core.biometric_sync as bs


def _matches(doc, q):
    for k, v in q.items():
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$gte" in v and not (actual is not None and actual >= v["$gte"]):
                return False
            if "$lte" in v and not (actual is not None and actual <= v["$lte"]):
                return False
            if "$lt" in v and not (actual is not None and actual < v["$lt"]):
                return False
            if "$in" in v and actual not in v["$in"]:
                return False
        elif v is None:
            if actual is not None:
                return False
        elif actual != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, _n):
        return [dict(d) for d in self._docs]


class _Collection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc, session=None):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": doc.get("id")})()

    async def insert_many(self, docs):
        for d in docs:
            self.docs.append(dict(d))

    async def find_one(self, q, projection=None, session=None):
        for d in self.docs:
            if _matches(d, q):
                out = dict(d)
                out.pop("_id", None)
                return out
        return None

    def find(self, q=None, projection=None):
        return _Cursor([dict(d) for d in self.docs if _matches(d, q or {})])

    async def count_documents(self, q):
        return len([d for d in self.docs if _matches(d, q or {})])

    async def update_one(self, q, update, session=None):
        for d in self.docs:
            if _matches(d, q):
                d.update(update.get("$set", {}))
                return type("R", (), {"matched_count": 1})()
        return type("R", (), {"matched_count": 0})()

    async def update_many(self, q, update):
        n = 0
        for d in self.docs:
            if _matches(d, q):
                d.update(update.get("$set", {}))
                n += 1
        return type("R", (), {"modified_count": n})()


class _DB:
    def __init__(self):
        self._c = {}

    def __getitem__(self, n):
        return self._c.setdefault(n, _Collection())

    def __getattr__(self, n):
        if n.startswith("_"):
            raise AttributeError(n)
        return self[n]


def _setup():
    db = _DB()
    return db


DEVICE = {
    "id": "dev1", "tenant_id": "t1", "name": "Main Gate", "integration_mode": "poll",
    "host": "10.0.0.5", "port": 4370, "api_path": "/iclock/getrequest",
    "last_sync_at": None, "poll_interval_seconds": 300, "is_active": True,
}


# ───────────────────────── dedup + ingestion ─────────────────────────

def test_same_punch_ingested_twice_dedups_not_duplicates():
    db = _setup()
    asyncio.run(db.employee_device_mappings.insert_one({
        "device_id": "dev1", "employee_id": "e1", "device_enrollment_id": "101", "is_active": True,
    }))
    punch = {"device_enrollment_id": "101", "timestamp": "2026-07-01T09:05:00", "direction": "IN", "punch_id": "p1"}

    first = asyncio.run(bs._ingest_punches(db, device=DEVICE, punches=[punch], source="poll", sync_run_id=None))
    second = asyncio.run(bs._ingest_punches(db, device=DEVICE, punches=[punch], source="poll", sync_run_id=None))

    assert first == {"fetched": 1, "new": 1, "duplicate": 0, "unmapped": 0}
    assert second == {"fetched": 1, "new": 0, "duplicate": 1, "unmapped": 0}
    assert len(db.attendance_logs.docs) == 1


def test_dedup_key_falls_back_to_composite_when_device_has_no_punch_id():
    db = _setup()
    asyncio.run(db.employee_device_mappings.insert_one({
        "device_id": "dev1", "employee_id": "e1", "device_enrollment_id": "101", "is_active": True,
    }))
    # No punch_id at all — same enrollment+timestamp(minute) must still dedup.
    punch = {"device_enrollment_id": "101", "timestamp": "2026-07-01T09:05:00", "direction": "IN"}
    asyncio.run(bs._ingest_punches(db, device=DEVICE, punches=[punch], source="poll", sync_run_id=None))
    result = asyncio.run(bs._ingest_punches(db, device=DEVICE, punches=[punch], source="poll", sync_run_id=None))
    assert result["duplicate"] == 1
    assert len(db.attendance_logs.docs) == 1


def test_unmapped_enrollment_is_recorded_not_dropped():
    db = _setup()
    # No mapping created for enrollment "999".
    punch = {"device_enrollment_id": "999", "timestamp": "2026-07-01T09:00:00", "direction": "IN", "punch_id": "p9"}
    result = asyncio.run(bs._ingest_punches(db, device=DEVICE, punches=[punch], source="poll", sync_run_id=None))
    assert result["unmapped"] == 1
    assert result["new"] == 1  # still written, for visibility/mapping later
    row = db.attendance_logs.docs[0]
    assert row["employee_id"] is None
    assert row["employee_code"] == "999"
    assert row["processed"] is True  # never queued for daily derivation while unmapped


def test_ingest_updates_device_last_seen_only_when_something_new_written():
    db = _setup()
    asyncio.run(db.biometric_devices.insert_one(dict(DEVICE)))
    asyncio.run(db.employee_device_mappings.insert_one({
        "device_id": "dev1", "employee_id": "e1", "device_enrollment_id": "101", "is_active": True,
    }))
    punch = {"device_enrollment_id": "101", "timestamp": "2026-07-01T09:00:00", "punch_id": "p1"}
    asyncio.run(bs._ingest_punches(db, device=DEVICE, punches=[punch], source="poll", sync_run_id=None))
    device = db.biometric_devices.docs[0]
    assert device["last_seen_at"] is not None


# ───────────────────────── daily derivation ─────────────────────────

def test_derive_daily_attendance_computes_late_and_overtime():
    db = _setup()
    asyncio.run(db.employees.insert_one({"id": "e1", "shift_id": None, "status": "active"}))
    asyncio.run(db.attendance_logs.insert_one({
        "id": "l1", "tenant_id": "t1", "employee_id": "e1", "log_time": "2026-07-01T09:20:00",
        "direction": "IN", "device_id": "dev1", "processed": False,
    }))
    asyncio.run(db.attendance_logs.insert_one({
        "id": "l2", "tenant_id": "t1", "employee_id": "e1", "log_time": "2026-07-01T19:30:00",
        "direction": "OUT", "device_id": "dev1", "processed": False,
    }))

    result = asyncio.run(bs.derive_daily_attendance(db, tenant_id="t1"))
    assert result["processed_days"] == 1

    att = db.attendance.docs[0]
    assert att["check_in"] == "09:20"
    assert att["check_out"] == "19:30"
    assert att["status"] == "LATE"  # 20 min past default 09:00 start, grace 10 min
    assert att["late"] is True
    assert att["working_hours"] == 10.17
    assert att["overtime_hours"] == 1.17  # 10.17 - 9.0 default overtime_after_hours
    assert att["source"] == "biometric"

    # Raw logs marked processed so a second derivation run is a no-op.
    assert all(d["processed"] for d in db.attendance_logs.docs)
    result2 = asyncio.run(bs.derive_daily_attendance(db, tenant_id="t1"))
    assert result2 == {"processed_days": 0, "processed_punches": 0}


def test_derive_daily_attendance_missing_punch_flagged_by_default_rule():
    db = _setup()
    asyncio.run(db.employees.insert_one({"id": "e1", "shift_id": None, "status": "active"}))
    asyncio.run(db.attendance_logs.insert_one({
        "id": "l1", "tenant_id": "t1", "employee_id": "e1", "log_time": "2026-07-01T09:00:00",
        "direction": "IN", "device_id": "dev1", "processed": False,
    }))
    asyncio.run(bs.derive_daily_attendance(db, tenant_id="t1"))
    att = db.attendance.docs[0]
    assert att["missing_punch"] is True
    assert att["check_out"] is None
    assert att["status"] == "PRESENT"  # default rule's missing_punch_action="flag", not "absent"


def test_derive_daily_attendance_missing_punch_absent_when_rule_configured():
    db = _setup()
    asyncio.run(db.employees.insert_one({"id": "e1", "shift_id": None, "status": "active"}))
    asyncio.run(db.attendance_rules.insert_one({
        "tenant_id": "t1", "shift_id": None, "is_active": True,
        "late_grace_minutes": 10, "early_leave_grace_minutes": 10,
        "half_day_threshold_hours": 4.0, "full_day_threshold_hours": 8.0,
        "overtime_after_hours": 9.0, "missing_punch_action": "absent",
    }))
    asyncio.run(db.attendance_logs.insert_one({
        "id": "l1", "tenant_id": "t1", "employee_id": "e1", "log_time": "2026-07-01T09:00:00",
        "direction": "IN", "device_id": "dev1", "processed": False,
    }))
    asyncio.run(bs.derive_daily_attendance(db, tenant_id="t1"))
    assert db.attendance.docs[0]["status"] == "ABSENT"


def test_derive_daily_attendance_half_day_below_threshold():
    db = _setup()
    asyncio.run(db.employees.insert_one({"id": "e1", "shift_id": None, "status": "active"}))
    asyncio.run(db.attendance_logs.insert_one({
        "id": "l1", "tenant_id": "t1", "employee_id": "e1", "log_time": "2026-07-01T09:00:00",
        "direction": "IN", "device_id": "dev1", "processed": False,
    }))
    asyncio.run(db.attendance_logs.insert_one({
        "id": "l2", "tenant_id": "t1", "employee_id": "e1", "log_time": "2026-07-01T12:00:00",
        "direction": "OUT", "device_id": "dev1", "processed": False,
    }))
    asyncio.run(bs.derive_daily_attendance(db, tenant_id="t1"))
    assert db.attendance.docs[0]["status"] == "HALF_DAY"
    assert db.attendance.docs[0]["working_hours"] == 3.0


def test_derive_daily_attendance_weekly_off_not_flagged_as_missing_punch():
    """2026-07-05 is a Sunday. Default shift (weekly_off_days=[0], 0=Sun) makes
    it a day off — a single stray punch (e.g. dropping by the office) must not
    be posted as a missing-punch PRESENT/ABSENT."""
    db = _setup()
    asyncio.run(db.employees.insert_one({"id": "e1", "shift_id": None, "status": "active"}))
    asyncio.run(db.attendance_logs.insert_one({
        "id": "l1", "tenant_id": "t1", "employee_id": "e1", "log_time": "2026-07-05T10:00:00",
        "direction": "IN", "device_id": "dev1", "processed": False,
    }))
    asyncio.run(bs.derive_daily_attendance(db, tenant_id="t1"))
    att = db.attendance.docs[0]
    assert att["status"] == "WEEKEND"
    assert att["missing_punch"] is False


def test_derive_daily_attendance_weekly_off_respects_shift_configured_days():
    """2026-07-04 is a Saturday (shift dow 6). A shift with weekly_off_days=[6]
    must treat Saturday as off even though the tenant default is Sunday."""
    db = _setup()
    asyncio.run(db.shifts.insert_one({
        "id": "sh1", "start_time": "09:00", "end_time": "18:00", "weekly_off_days": [6],
    }))
    asyncio.run(db.employees.insert_one({"id": "e1", "shift_id": "sh1", "status": "active"}))
    asyncio.run(db.attendance_logs.insert_one({
        "id": "l1", "tenant_id": "t1", "employee_id": "e1", "log_time": "2026-07-04T09:10:00",
        "direction": "IN", "device_id": "dev1", "processed": False,
    }))
    asyncio.run(bs.derive_daily_attendance(db, tenant_id="t1"))
    assert db.attendance.docs[0]["status"] == "WEEKEND"


def test_derive_daily_attendance_holiday_takes_precedence_over_punches():
    db = _setup()
    asyncio.run(db.employees.insert_one({"id": "e1", "shift_id": None, "status": "active", "branch_id": None}))
    asyncio.run(db.holidays.insert_one({"holiday_date": "2026-07-01", "branch_id": None, "name": "Bakri Eid"}))
    asyncio.run(db.attendance_logs.insert_one({
        "id": "l1", "tenant_id": "t1", "employee_id": "e1", "log_time": "2026-07-01T09:00:00",
        "direction": "IN", "device_id": "dev1", "processed": False,
    }))
    asyncio.run(db.attendance_logs.insert_one({
        "id": "l2", "tenant_id": "t1", "employee_id": "e1", "log_time": "2026-07-01T18:00:00",
        "direction": "OUT", "device_id": "dev1", "processed": False,
    }))
    asyncio.run(bs.derive_daily_attendance(db, tenant_id="t1"))
    att = db.attendance.docs[0]
    assert att["status"] == "HOLIDAY"
    assert att["overtime_hours"] == 0.0  # holiday overrides OT even though 9h were worked


def test_derive_daily_attendance_branch_specific_holiday_scopes_to_branch():
    db = _setup()
    asyncio.run(db.employees.insert_one({"id": "e_pune", "shift_id": None, "status": "active", "branch_id": "pune"}))
    asyncio.run(db.employees.insert_one({"id": "e_mumbai", "shift_id": None, "status": "active", "branch_id": "mumbai"}))
    asyncio.run(db.holidays.insert_one({"holiday_date": "2026-07-01", "branch_id": "pune", "name": "Local Festival"}))
    for emp_id in ("e_pune", "e_mumbai"):
        asyncio.run(db.attendance_logs.insert_one({
            "id": f"l_{emp_id}", "tenant_id": "t1", "employee_id": emp_id, "log_time": "2026-07-01T09:00:00",
            "direction": "IN", "device_id": "dev1", "processed": False,
        }))
    asyncio.run(bs.derive_daily_attendance(db, tenant_id="t1"))
    by_emp = {d["employee_id"]: d for d in db.attendance.docs}
    assert by_emp["e_pune"]["status"] == "HOLIDAY"
    assert by_emp["e_mumbai"]["status"] != "HOLIDAY"  # Mumbai has no such holiday


# ───────────────────────── midnight-crossing shifts ─────────────────────────

def test_derive_daily_attendance_night_shift_crossing_midnight_pairs_correctly():
    """Night shift 22:00-06:00. IN at 22:10 on day 1, OUT at 06:05 on day 2
    must land on ONE attendance row for day 1 — not split into a day-1 row
    with a missing check-out and a day-2 row with a missing check-in."""
    db = _setup()
    asyncio.run(db.shifts.insert_one({
        "id": "night", "start_time": "22:00", "end_time": "06:00", "crosses_midnight": True,
        "weekly_off_days": [], "late_grace_min": 15,
    }))
    asyncio.run(db.employees.insert_one({"id": "e1", "shift_id": "night", "status": "active"}))
    asyncio.run(db.attendance_rules.insert_one({
        "tenant_id": "t1", "shift_id": "night", "is_active": True,
        "late_grace_minutes": 15, "early_leave_grace_minutes": 10,
        "half_day_threshold_hours": 4.0, "full_day_threshold_hours": 7.0,
        "overtime_after_hours": 8.5, "missing_punch_action": "flag",
    }))
    asyncio.run(db.attendance_logs.insert_one({
        "id": "l1", "tenant_id": "t1", "employee_id": "e1", "log_time": "2026-07-01T22:10:00",
        "direction": "IN", "device_id": "dev1", "processed": False,
    }))
    asyncio.run(db.attendance_logs.insert_one({
        "id": "l2", "tenant_id": "t1", "employee_id": "e1", "log_time": "2026-07-02T06:05:00",
        "direction": "OUT", "device_id": "dev1", "processed": False,
    }))

    result = asyncio.run(bs.derive_daily_attendance(db, tenant_id="t1"))
    assert result["processed_days"] == 1  # one shift-day, not two
    assert len(db.attendance.docs) == 1

    att = db.attendance.docs[0]
    assert att["date"] == "2026-07-01"  # attributed to the shift's start day
    assert att["check_in"] == "22:10"
    assert att["check_out"] == "06:05"
    assert att["working_hours"] == 7.92  # 22:10 -> 06:05 spans into the next calendar day only in wall-clock terms
    assert att["missing_punch"] is False


def test_derive_daily_attendance_night_shift_early_morning_punch_not_a_new_day():
    """A lone early-morning punch (e.g. 05:30, before the night shift's 06:00
    end_time) with no matching IN the same calendar day must be attributed to
    the PREVIOUS shift-day, not treated as the start of a brand new one."""
    db = _setup()
    asyncio.run(db.shifts.insert_one({
        "id": "night", "start_time": "22:00", "end_time": "06:00", "crosses_midnight": True,
        "weekly_off_days": [],
    }))
    asyncio.run(db.employees.insert_one({"id": "e1", "shift_id": "night", "status": "active"}))
    asyncio.run(db.attendance_logs.insert_one({
        "id": "l1", "tenant_id": "t1", "employee_id": "e1", "log_time": "2026-07-02T05:30:00",
        "direction": "OUT", "device_id": "dev1", "processed": False,
    }))
    asyncio.run(bs.derive_daily_attendance(db, tenant_id="t1"))
    assert db.attendance.docs[0]["date"] == "2026-07-01"  # previous day, not 2026-07-02


def test_derive_daily_attendance_day_shift_unaffected_by_midnight_crossing_logic():
    """crosses_midnight=False (the default) must behave exactly as before —
    a punch is always attributed to its own calendar date."""
    db = _setup()
    asyncio.run(db.shifts.insert_one({"id": "day", "start_time": "09:00", "end_time": "18:00", "weekly_off_days": []}))
    asyncio.run(db.employees.insert_one({"id": "e1", "shift_id": "day", "status": "active"}))
    asyncio.run(db.attendance_logs.insert_one({
        "id": "l1", "tenant_id": "t1", "employee_id": "e1", "log_time": "2026-07-01T05:30:00",
        "direction": "IN", "device_id": "dev1", "processed": False,
    }))
    asyncio.run(bs.derive_daily_attendance(db, tenant_id="t1"))
    assert db.attendance.docs[0]["date"] == "2026-07-01"


# ───────────────────────── attendance correction / approval ─────────────────────────

def test_approve_correction_recomputes_late_and_status_from_shift_rule():
    """Approving a correction must go through the SAME derivation logic as a
    device-derived day — not just write the requested times verbatim — so
    late/status/hours stay consistent regardless of source."""
    db = _setup()
    asyncio.run(db.employees.insert_one({"id": "e1", "shift_id": None, "status": "active"}))
    correction = {
        "id": "corr1", "employee_id": "e1", "attendance_date": "2026-07-01",
        "requested_check_in": "09:20", "requested_check_out": "19:00",
        "requested_status": None, "status": "PENDING",
    }
    asyncio.run(db.attendance_corrections.insert_one(dict(correction)))
    result = asyncio.run(bs.approve_correction(db, correction=correction, decided_by="hr1"))
    assert result["status"] == "LATE"  # 09:20 is 20 min past default 09:00 start, grace 10 min
    assert result["source"] == "correction"
    assert result["check_in"] == "09:20"
    assert result["check_out"] == "19:00"

    stored_correction = db.attendance_corrections.docs[0]
    assert stored_correction["status"] == "APPROVED"
    assert stored_correction["decided_by"] == "hr1"

    att = next(d for d in db.attendance.docs if d.get("date") == "2026-07-01")
    assert att["status"] == "LATE"


def test_approve_correction_with_status_only_skips_derivation():
    """A correction requesting just a status (e.g. 'device was down, mark me
    PRESENT') with no punch times is used as-is — there's nothing to derive."""
    db = _setup()
    asyncio.run(db.employees.insert_one({"id": "e1", "shift_id": None, "status": "active"}))
    correction = {
        "id": "corr1", "employee_id": "e1", "attendance_date": "2026-07-01",
        "requested_check_in": None, "requested_check_out": None,
        "requested_status": "PRESENT", "status": "PENDING",
    }
    result = asyncio.run(bs.approve_correction(db, correction=correction, decided_by="hr1"))
    assert result["status"] == "PRESENT"
    assert result["working_hours"] == 0.0


def test_approve_correction_respects_weekly_off():
    """Even a correction request must not override a genuine weekly off —
    approving one for a Sunday still derives WEEKEND, not the requester's
    literal check-in/out times as PRESENT/LATE."""
    db = _setup()
    asyncio.run(db.employees.insert_one({"id": "e1", "shift_id": None, "status": "active"}))
    correction = {
        "id": "corr1", "employee_id": "e1", "attendance_date": "2026-07-05",  # Sunday
        "requested_check_in": "09:00", "requested_check_out": "18:00",
        "requested_status": None, "status": "PENDING",
    }
    result = asyncio.run(bs.approve_correction(db, correction=correction, decided_by="hr1"))
    assert result["status"] == "WEEKEND"


def test_approve_correction_updates_existing_attendance_row_not_duplicate():
    db = _setup()
    asyncio.run(db.employees.insert_one({"id": "e1", "shift_id": None, "status": "active"}))
    asyncio.run(db.attendance.insert_one({
        "id": "att1", "employee_id": "e1", "date": "2026-07-01", "status": "ABSENT",
        "check_in": None, "check_out": None, "missing_punch": True,
    }))
    correction = {
        "id": "corr1", "employee_id": "e1", "attendance_date": "2026-07-01",
        "requested_check_in": "09:00", "requested_check_out": "18:00",
        "requested_status": None, "status": "PENDING",
    }
    asyncio.run(bs.approve_correction(db, correction=correction, decided_by="hr1"))
    assert len(db.attendance.docs) == 1  # updated in place, not a second row
    assert db.attendance.docs[0]["status"] == "PRESENT"


# ───────────────────────── poll / retry / backoff ─────────────────────────

def test_poll_device_success_records_sync_run_and_updates_device():
    db = _setup()
    asyncio.run(db.biometric_devices.insert_one(dict(DEVICE)))
    asyncio.run(db.employee_device_mappings.insert_one({
        "device_id": "dev1", "employee_id": "e1", "device_enrollment_id": "101", "is_active": True,
    }))

    async def fake_fetch(self, since):
        return [{"device_enrollment_id": "101", "timestamp": "2026-07-01T09:00:00", "punch_id": "p1"}]

    orig = bs.EsslDeviceAdapter.fetch_punches
    bs.EsslDeviceAdapter.fetch_punches = fake_fetch
    try:
        result = asyncio.run(bs.poll_device(db, device=DEVICE, trigger="manual", triggered_by="u1"))
    finally:
        bs.EsslDeviceAdapter.fetch_punches = orig

    assert result["status"] == "success"
    assert result["new"] == 1
    run = db.attendance_sync_runs.docs[0]
    assert run["status"] == "success"
    assert run["trigger"] == "manual"
    device = db.biometric_devices.docs[0]
    assert device["last_sync_status"] == "success"


def test_poll_device_failure_schedules_retry_with_backoff():
    db = _setup()
    asyncio.run(db.biometric_devices.insert_one(dict(DEVICE)))

    async def fake_fetch_fail(self, since):
        raise ConnectionError("device unreachable")

    orig = bs.EsslDeviceAdapter.fetch_punches
    bs.EsslDeviceAdapter.fetch_punches = fake_fetch_fail
    try:
        before = datetime.now(timezone.utc)
        result = asyncio.run(bs.poll_device(db, device=DEVICE, trigger="scheduled", triggered_by="system"))
    finally:
        bs.EsslDeviceAdapter.fetch_punches = orig

    assert result["status"] == "failed"
    run = db.attendance_sync_runs.docs[0]
    assert run["status"] == "failed"
    assert run["error_message"] == "device unreachable"
    next_attempt = datetime.fromisoformat(run["next_attempt_at"])
    # backoff_delay(1) == 5 seconds (core.webhooks convention, reused as-is).
    assert 4 <= (next_attempt - before).total_seconds() <= 8
    device = db.biometric_devices.docs[0]
    assert device["last_sync_status"] == "failed"


def test_retry_failed_syncs_gives_up_after_max_attempts():
    db = _setup()
    asyncio.run(db.biometric_devices.insert_one(dict(DEVICE)))
    asyncio.run(db.attendance_sync_runs.insert_one({
        "id": "run1", "tenant_id": "t1", "device_id": "dev1", "trigger": "scheduled",
        "status": "failed", "attempt": bs.MAX_SYNC_ATTEMPTS - 1,
        "next_attempt_at": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
        "punches_fetched": 0, "punches_new": 0, "punches_duplicate": 0,
    }))

    async def fake_fetch_fail(self, since):
        raise ConnectionError("still down")

    orig = bs.EsslDeviceAdapter.fetch_punches
    bs.EsslDeviceAdapter.fetch_punches = fake_fetch_fail
    try:
        result = asyncio.run(bs.retry_failed_syncs(db))
    finally:
        bs.EsslDeviceAdapter.fetch_punches = orig

    assert result == {"due": 1, "retried": 0, "given_up": 1}
    run = db.attendance_sync_runs.docs[0]
    assert run["status"] == "failed"
    assert run["next_attempt_at"] is None  # no further retry scheduled


def test_retry_failed_syncs_skips_runs_not_yet_due():
    db = _setup()
    asyncio.run(db.biometric_devices.insert_one(dict(DEVICE)))
    asyncio.run(db.attendance_sync_runs.insert_one({
        "id": "run1", "tenant_id": "t1", "device_id": "dev1", "status": "failed", "attempt": 1,
        "next_attempt_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }))
    result = asyncio.run(bs.retry_failed_syncs(db))
    assert result == {"due": 0, "retried": 0, "given_up": 0}


# ───────────────────────── monthly payroll aggregate ─────────────────────────

def test_aggregate_monthly_paid_days_counts_present_late_half_day_and_leave():
    db = _setup()
    period = "072026"
    rows = [
        {"employee_id": "e1", "date": "2026-07-01", "status": "PRESENT"},
        {"employee_id": "e1", "date": "2026-07-02", "status": "LATE"},
        {"employee_id": "e1", "date": "2026-07-03", "status": "HALF_DAY"},
        {"employee_id": "e1", "date": "2026-07-04", "status": "ABSENT"},
        {"employee_id": "e1", "date": "2026-07-05", "status": "LEAVE"},
    ]
    for r in rows:
        asyncio.run(db.attendance.insert_one({"id": r["date"], **r}))
    asyncio.run(db.leaves.insert_one({
        "employee_id": "e1", "status": "APPROVED", "leave_type_id": "lt1",
        "from_date": "2026-07-05", "to_date": "2026-07-05",
    }))
    asyncio.run(db.leave_types.insert_one({"id": "lt1", "paid": True}))

    result = asyncio.run(bs.aggregate_monthly_paid_days(db, period=period, employee_ids=["e1"]))
    assert result["employees_processed"] == 1

    period_row = next(d for d in db.attendance.docs if d.get("period") == period)
    # 1 (PRESENT) + 1 (LATE) + 0.5 (HALF_DAY) + 0 (ABSENT) + 1 (paid LEAVE) = 3.5
    assert period_row["paid_days"] == 3.5
    assert period_row["employee_id"] == "e1"


def test_aggregate_monthly_paid_days_unpaid_leave_contributes_zero():
    db = _setup()
    asyncio.run(db.attendance.insert_one({"id": "d1", "employee_id": "e1", "date": "2026-07-05", "status": "LEAVE"}))
    asyncio.run(db.leaves.insert_one({
        "employee_id": "e1", "status": "APPROVED", "leave_type_id": "lop",
        "from_date": "2026-07-05", "to_date": "2026-07-05",
    }))
    asyncio.run(db.leave_types.insert_one({"id": "lop", "paid": False}))
    result = asyncio.run(bs.aggregate_monthly_paid_days(db, period="072026", employee_ids=["e1"]))
    assert result["employees_processed"] == 1
    period_row = next(d for d in db.attendance.docs if d.get("period") == "072026")
    assert period_row["paid_days"] == 0.0


def test_period_row_never_matches_a_daily_date_range_query():
    """A period-aggregate row (date=None) must not show up when a daily
    report queries attendance by a date range — SQL NULL comparisons never
    satisfy a $gte/$lte range, so this is really testing the fake DB's
    _matches honors that same semantic (mirrors core/_mongo_compat.py's
    real col >= / col <= translation, which SQL NULL-fails identically)."""
    db = _setup()
    asyncio.run(db.attendance.insert_one({"id": "d1", "employee_id": "e1", "date": "2026-07-01", "status": "PRESENT"}))
    asyncio.run(bs.aggregate_monthly_paid_days(db, period="072026", employee_ids=["e1"]))

    daily_rows = [d for d in db.attendance.docs if _matches(d, {"date": {"$gte": "2026-07-01", "$lte": "2026-07-31"}})]
    assert len(daily_rows) == 1
    assert daily_rows[0]["date"] == "2026-07-01"
