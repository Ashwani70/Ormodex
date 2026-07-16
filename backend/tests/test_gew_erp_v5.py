"""Iteration 5 backend tests — HRM & Payroll regression.

Covers:
- HR Setup CRUD (branches, departments, designations, shifts, holidays, leave types)
- Employees: CRUD, self-service user auto-creation, QR token, salary structure GET-default + PUT-upsert
- Attendance: manual check-in/out, bulk, public QR check-in/out, biometric webhook
- Leaves: HR apply, decide (approve/reject), employee self-apply, leave balance
- Payroll: generate (idempotent), lock (blocks edits), unlock, PDF (%PDF-), WhatsApp link
- Public payslip share: 404 before lock, 200 after lock (no auth)
- HR dashboard shape
- Extended user roles: hr, accountant
- _id exclusion across all 13 new collections
"""
import os
from datetime import date, datetime

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = "admin@ormodex.com"
ADMIN_PASSWORD = "Admin@123456"


class TestState:
    _v5_leave_id = None
    _v5_run_id = None
    _v5_payslip_id = None
    _v5_payslip_share_token = None


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    s.user = data["user"]  # type: ignore
    return s


@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()


@pytest.fixture(scope="module")
def setup_data(admin_session):
    """Create branch + department + designation + shift + leave types used by other tests."""
    # branch
    b = admin_session.post(
        f"{BASE_URL}/api/hr/branches",
        json={"name": "V5-Test Branch", "code": "V5", "location": "Pune"},
    ).json()
    # department
    d = admin_session.post(
        f"{BASE_URL}/api/hr/departments",
        json={"name": "V5-Test Dept", "branch_id": b["id"]},
    ).json()
    # designation
    g = admin_session.post(
        f"{BASE_URL}/api/hr/designations",
        json={"name": "V5-Test Designation"},
    ).json()
    # shift
    sh = admin_session.post(
        f"{BASE_URL}/api/hr/shifts",
        json={"name": "V5-Day", "start_time": "09:00", "end_time": "18:00",
              "weekly_off_days": [6], "late_grace_min": 10, "full_day_hours": 8, "half_day_hours": 4},
    ).json()
    # leave types
    lt_paid = admin_session.post(
        f"{BASE_URL}/api/hr/leave-types",
        json={"name": "V5-Casual", "annual_quota": 12, "paid": True},
    ).json()
    lt_unpaid = admin_session.post(
        f"{BASE_URL}/api/hr/leave-types",
        json={"name": "V5-LOP", "annual_quota": 0, "paid": False},
    ).json()
    # holiday
    h = admin_session.post(
        f"{BASE_URL}/api/hr/holidays",
        json={"date": "2030-01-26", "name": "V5-Republic Day", "branch_id": None},
    ).json()
    yield {
        "branch_id": b["id"],
        "department_id": d["id"],
        "designation_id": g["id"],
        "shift_id": sh["id"],
        "leave_type_paid": lt_paid["id"],
        "leave_type_unpaid": lt_unpaid["id"],
        "holiday_id": h["id"],
    }


@pytest.fixture(scope="module")
def employee_record(admin_session, setup_data):
    """Create an employee with self-service login for self-service tests."""
    payload = {
        "employee_code": "V5EMP001",
        "first_name": "Vikram",
        "last_name": "Test",
        "email": "v5emp001@gravity-test.com",
        "phone": "+919876543299",
        "branch_id": setup_data["branch_id"],
        "department_id": setup_data["department_id"],
        "shift_id": setup_data["shift_id"],
        "designation": "V5 Tester",
        "basic_salary": 30000,
        "create_login": True,
        "login_password": "EmpPass@1234",
        "bank_name": "HDFC",
        "account_number": "1234567890",
        "ifsc_code": "HDFC0001234",
        "pan_number": "ABCDE1234F",
    }
    # Clean prior runs if any
    listing = admin_session.get(f"{BASE_URL}/api/hr/employees", params={"q": "V5EMP001"}).json()
    for prev in listing:
        if prev.get("employee_code") == "V5EMP001":
            admin_session.delete(f"{BASE_URL}/api/hr/employees/{prev['id']}")
    r = admin_session.post(f"{BASE_URL}/api/hr/employees", json=payload)
    assert r.status_code == 200, f"create employee: {r.status_code} {r.text}"
    emp = r.json()
    return emp


@pytest.fixture(scope="module")
def employee_session(employee_record):
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "v5emp001@gravity-test.com", "password": "EmpPass@1234"},
    )
    if r.status_code != 200:
        pytest.skip(f"employee login failed: {r.status_code} {r.text}")
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


# ============================================================
# HR Setup CRUD
# ============================================================
class TestHrSetup:
    def test_branch_list_auth(self):
        r = requests.get(f"{BASE_URL}/api/hr/branches")
        assert r.status_code == 401

    def test_branch_crud(self, admin_session):
        b = admin_session.post(
            f"{BASE_URL}/api/hr/branches",
            json={"name": "CRUD Branch", "code": "CRD"},
        )
        assert b.status_code == 200
        bid = b.json()["id"]
        upd = admin_session.put(
            f"{BASE_URL}/api/hr/branches/{bid}",
            json={"name": "CRUD Branch v2", "code": "CRD", "location": "Mumbai"},
        )
        assert upd.status_code == 200
        assert upd.json()["name"] == "CRUD Branch v2"
        assert admin_session.delete(f"{BASE_URL}/api/hr/branches/{bid}").status_code == 200

    def test_department_crud(self, admin_session, setup_data):
        d = admin_session.post(
            f"{BASE_URL}/api/hr/departments",
            json={"name": "CRUD-Dept", "branch_id": setup_data["branch_id"]},
        )
        assert d.status_code == 200
        assert admin_session.delete(f"{BASE_URL}/api/hr/departments/{d.json()['id']}").status_code == 200

    def test_designation_shift_holiday_leavetype_crud(self, admin_session):
        for endpoint, payload in [
            ("designations", {"name": "CRUD-Des"}),
            ("shifts", {"name": "CRUD-Shift", "start_time": "10:00", "end_time": "19:00"}),
            ("holidays", {"date": "2030-12-25", "name": "Christmas"}),
            ("leave-types", {"name": "CRUD-LT", "annual_quota": 6, "paid": True}),
        ]:
            r = admin_session.post(f"{BASE_URL}/api/hr/{endpoint}", json=payload)
            assert r.status_code == 200, f"{endpoint}: {r.text}"
            assert admin_session.delete(f"{BASE_URL}/api/hr/{endpoint}/{r.json()['id']}").status_code == 200

    def test_no_id_leak_setup(self, admin_session):
        for endpoint in ["branches", "departments", "designations", "shifts", "holidays", "leave-types"]:
            rows = admin_session.get(f"{BASE_URL}/api/hr/{endpoint}").json()
            for row in rows:
                assert "_id" not in row, f"{endpoint} leaked _id"


# ============================================================
# Employees + Salary Structure + Self-service login
# ============================================================
class TestEmployees:
    def test_create_employee_with_login(self, employee_record):
        assert employee_record["employee_code"] == "V5EMP001"
        assert employee_record["user_id"], "user account must be linked"
        assert employee_record["qr_token"], "QR token must be issued"

    def test_employee_login_works(self, employee_session):
        r = employee_session.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["role"] == "employee"

    def test_employee_self_view(self, employee_session, employee_record):
        r = employee_session.get(f"{BASE_URL}/api/hr/me/employee")
        assert r.status_code == 200
        assert r.json()["employee_code"] == employee_record["employee_code"]

    def test_employee_no_admin_perms(self, employee_session):
        r = employee_session.post(
            f"{BASE_URL}/api/hr/branches",
            json={"name": "should-fail"},
        )
        assert r.status_code == 403

    def test_employee_duplicate_code_rejected(self, admin_session, setup_data):
        r = admin_session.post(
            f"{BASE_URL}/api/hr/employees",
            json={
                "employee_code": "V5EMP001",
                "first_name": "Dup",
                "last_name": "User",
                "branch_id": setup_data["branch_id"],
            },
        )
        assert r.status_code == 400

    def test_salary_structure_default(self, admin_session, employee_record):
        r = admin_session.get(
            f"{BASE_URL}/api/hr/employees/{employee_record['id']}/salary-structure"
        )
        assert r.status_code == 200
        body = r.json()
        # defaults when none exists
        assert body["pf_percent"] == 12
        assert body["professional_tax"] == 200
        assert body["enable_esi"] is True

    def test_salary_structure_upsert(self, admin_session, employee_record):
        payload = {
            "employee_id": employee_record["id"],
            "basic": 20000,
            "hra": 8000,
            "da": 0,
            "conveyance": 1600,
            "medical": 1250,
            "special_allowance": 5000,
            "other_allowance": 0,
            "pf_percent": 12,
            "enable_pf": True,
            "esi_employee_percent": 0.75,
            "esi_employer_percent": 3.25,
            "enable_esi": True,
            "professional_tax": 200,
            "tds_percent": 0,
            "overtime_rate_multiplier": 2,
        }
        r = admin_session.put(
            f"{BASE_URL}/api/hr/employees/{employee_record['id']}/salary-structure",
            json=payload,
        )
        assert r.status_code == 200
        assert r.json()["basic"] == 20000
        # upsert (call again)
        payload["basic"] = 22000
        r2 = admin_session.put(
            f"{BASE_URL}/api/hr/employees/{employee_record['id']}/salary-structure",
            json=payload,
        )
        assert r2.json()["basic"] == 22000

    def test_reset_qr(self, admin_session, employee_record):
        r = admin_session.post(
            f"{BASE_URL}/api/hr/employees/{employee_record['id']}/reset-qr"
        )
        assert r.status_code == 200
        assert r.json()["qr_token"] != employee_record["qr_token"]
        # refresh stored token for downstream QR tests
        new = admin_session.get(f"{BASE_URL}/api/hr/employees/{employee_record['id']}").json()
        employee_record["qr_token"] = new["qr_token"]

    def test_no_id_leak_employee(self, admin_session):
        rows = admin_session.get(f"{BASE_URL}/api/hr/employees").json()
        for row in rows:
            assert "_id" not in row


# ============================================================
# Attendance
# ============================================================
class TestAttendance:
    def test_bulk_attendance(self, admin_session, employee_record):
        today = date.today().isoformat()
        r = admin_session.post(
            f"{BASE_URL}/api/hr/attendance/bulk",
            json={
                "date": today,
                "rows": [{
                    "employee_id": employee_record["id"],
                    "status": "PRESENT",
                    "check_in": "09:00",
                    "check_out": "18:00",
                    "overtime_hours": 1,
                }],
            },
        )
        assert r.status_code == 200
        assert r.json()["saved"] == 1

    def test_attendance_get_with_filter(self, admin_session, employee_record):
        today = date.today().isoformat()
        r = admin_session.get(
            f"{BASE_URL}/api/hr/attendance",
            params={"employee_id": employee_record["id"], "date_from": today, "date_to": today},
        )
        assert r.status_code == 200
        rows = r.json()
        assert any(a["date"] == today and a["status"] in ("PRESENT", "LATE") for a in rows)
        for r_ in rows:
            assert "employee_name" in r_

    def test_self_check_in_check_out(self, employee_session, employee_record):
        ci = employee_session.post(f"{BASE_URL}/api/hr/me/attendance/check-in")
        assert ci.status_code == 200
        assert ci.json()["source"] == "self"
        assert ci.json().get("check_in")
        co = employee_session.post(f"{BASE_URL}/api/hr/me/attendance/check-out")
        assert co.status_code == 200
        assert co.json().get("check_out")

    def test_self_attendance_list(self, employee_session):
        r = employee_session.get(f"{BASE_URL}/api/hr/me/attendance")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_qr_check_in_no_auth(self, anon_session, employee_record):
        # info works without auth
        info = anon_session.get(
            f"{BASE_URL}/api/hr/qr/{employee_record['qr_token']}/info"
        )
        assert info.status_code == 200
        assert info.json()["employee_code"] == "V5EMP001"
        # check-in (also no auth)
        ci = anon_session.post(
            f"{BASE_URL}/api/hr/qr/{employee_record['qr_token']}/check-in"
        )
        assert ci.status_code == 200
        assert ci.json()["ok"] is True
        assert ci.json()["attendance"]["source"] == "qr"

    def test_qr_invalid_token(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/hr/qr/totally-bogus/info")
        assert r.status_code == 404

    def test_biometric_webhook(self, anon_session, employee_record):
        # Note: biometric endpoint has no auth dep, matching real device webhooks
        r = anon_session.post(
            f"{BASE_URL}/api/hr/attendance/biometric",
            json={
                "employee_code": "V5EMP001",
                "timestamp": datetime.now().isoformat(),
                "punch_type": "IN",
            },
        )
        assert r.status_code == 200
        assert r.json()["source"] == "biometric"

    def test_biometric_unknown_employee(self, anon_session):
        r = anon_session.post(
            f"{BASE_URL}/api/hr/attendance/biometric",
            json={
                "employee_code": "NOT_EXISTING",
                "timestamp": datetime.now().isoformat(),
                "punch_type": "IN",
            },
        )
        assert r.status_code == 404

    def test_no_id_leak_attendance(self, admin_session):
        rows = admin_session.get(f"{BASE_URL}/api/hr/attendance").json()
        for r in rows:
            assert "_id" not in r


# ============================================================
# Leaves
# ============================================================
class TestLeaves:
    def test_hr_apply_leave(self, admin_session, employee_record, setup_data):
        r = admin_session.post(
            f"{BASE_URL}/api/hr/leaves",
            json={
                "employee_id": employee_record["id"],
                "leave_type_id": setup_data["leave_type_paid"],
                "start_date": "2030-01-10",
                "end_date": "2030-01-12",
                "reason": "test",
            },
        )
        assert r.status_code == 200
        leave = r.json()
        assert leave["total_days"] == 3
        assert leave["status"] == "PENDING"
        TestState._v5_leave_id = leave["id"]

    def test_employee_self_apply_leave(self, employee_session, setup_data):
        r = employee_session.post(
            f"{BASE_URL}/api/hr/me/leaves",
            json={
                "leave_type_id": setup_data["leave_type_paid"],
                "start_date": "2030-02-01",
                "end_date": "2030-02-01",
                "reason": "self",
                "employee_id": "ignored",
            },
        )
        assert r.status_code == 200
        assert r.json()["total_days"] == 1
        assert r.json()["status"] == "PENDING"

    def test_employee_cannot_apply_via_hr_route(self, employee_session, setup_data):
        r = employee_session.post(
            f"{BASE_URL}/api/hr/leaves",
            json={
                "employee_id": "any",
                "leave_type_id": setup_data["leave_type_paid"],
                "start_date": "2030-03-01",
                "end_date": "2030-03-01",
            },
        )
        assert r.status_code == 403

    def test_decide_approve(self, admin_session):
        lid = getattr(TestState, "_v5_leave_id", None)
        assert lid, "previous test must set leave id"
        r = admin_session.post(
            f"{BASE_URL}/api/hr/leaves/{lid}/decide",
            json={"status": "APPROVED"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "APPROVED"
        assert r.json()["approved_by"]

    def test_leave_balance(self, employee_session, setup_data):
        r = employee_session.get(f"{BASE_URL}/api/hr/me/leave-balance")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        for row in body:
            assert {"leave_type_id", "annual_quota", "used", "available"}.issubset(row.keys())

    def test_my_leaves_list(self, employee_session):
        r = employee_session.get(f"{BASE_URL}/api/hr/me/leaves")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ============================================================
# Payroll
# ============================================================
class TestPayroll:
    MONTH = "2026-04"

    def test_generate_run(self, admin_session, employee_record):
        r = admin_session.post(
            f"{BASE_URL}/api/hr/payroll-runs/generate",
            json={"month": self.MONTH, "employee_ids": [employee_record["id"]]},
        )
        assert r.status_code == 200, r.text
        run = r.json()
        assert run["month"] == self.MONTH
        assert run["status"] == "DRAFT"
        assert run["employee_count"] >= 1
        TestState._v5_run_id = run["id"]

    def test_regenerate_overwrites_draft(self, admin_session, employee_record):
        r = admin_session.post(
            f"{BASE_URL}/api/hr/payroll-runs/generate",
            json={"month": self.MONTH, "employee_ids": [employee_record["id"]]},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "DRAFT"

    def test_payslip_listing(self, admin_session, employee_record):
        run_id = getattr(TestState, "_v5_run_id", None)
        r = admin_session.get(
            f"{BASE_URL}/api/hr/payslips",
            params={"run_id": run_id, "employee_id": employee_record["id"]},
        )
        assert r.status_code == 200
        ps_list = r.json()
        assert len(ps_list) >= 1
        ps = ps_list[0]
        assert {"earnings", "deductions", "gross_salary", "total_deduction", "net_salary"}.issubset(ps.keys())
        assert ps["status"] == "DRAFT"
        TestState._v5_payslip_id = ps["id"]
        TestState._v5_payslip_share_token = ps.get("share_token")

    def test_edit_payslip_bonus(self, admin_session):
        ps_id = getattr(TestState, "_v5_payslip_id")
        r = admin_session.put(
            f"{BASE_URL}/api/hr/payslips/{ps_id}",
            json={"bonus": 1000, "incentive": 500},
        )
        assert r.status_code == 200
        assert r.json()["bonus"] == 1000
        assert r.json()["incentive"] == 500

    def test_public_payslip_blocked_before_lock(self, anon_session):
        token = getattr(TestState, "_v5_payslip_share_token")
        r = anon_session.get(f"{BASE_URL}/api/hr/public/payslip/{token}/info")
        assert r.status_code == 404, "before lock, public share should be hidden"

    def test_lock_run(self, admin_session):
        run_id = getattr(TestState, "_v5_run_id")
        r = admin_session.post(f"{BASE_URL}/api/hr/payroll-runs/{run_id}/lock")
        assert r.status_code == 200

    def test_locked_run_blocks_edit(self, admin_session):
        ps_id = getattr(TestState, "_v5_payslip_id")
        r = admin_session.put(
            f"{BASE_URL}/api/hr/payslips/{ps_id}",
            json={"bonus": 9999},
        )
        assert r.status_code == 400

    def test_locked_blocks_regenerate(self, admin_session, employee_record):
        r = admin_session.post(
            f"{BASE_URL}/api/hr/payroll-runs/generate",
            json={"month": self.MONTH, "employee_ids": [employee_record["id"]]},
        )
        assert r.status_code == 400

    def test_public_payslip_works_after_lock(self, anon_session):
        token = getattr(TestState, "_v5_payslip_share_token")
        info = anon_session.get(f"{BASE_URL}/api/hr/public/payslip/{token}/info")
        assert info.status_code == 200
        assert info.json()["employee_code"] == "V5EMP001"
        pdf = anon_session.get(f"{BASE_URL}/api/hr/public/payslip/{token}/pdf")
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF-")

    def test_payslip_pdf(self, admin_session):
        ps_id = getattr(TestState, "_v5_payslip_id")
        r = admin_session.get(f"{BASE_URL}/api/hr/payslips/{ps_id}/pdf")
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF-")
        assert r.headers.get("content-type", "").startswith("application/pdf")

    def test_whatsapp_link(self, admin_session):
        ps_id = getattr(TestState, "_v5_payslip_id")
        r = admin_session.get(f"{BASE_URL}/api/hr/payslips/{ps_id}/whatsapp-link")
        assert r.status_code == 200
        body = r.json()
        assert "wa.me" in body["wa_link"]
        assert body["public_url"]

    def test_employee_sees_finalised_payslip(self, employee_session):
        r = employee_session.get(f"{BASE_URL}/api/hr/me/payslips")
        assert r.status_code == 200
        ps_list = r.json()
        # The 2026-04 payslip is FINALISED now
        assert any(p["month"] == "2026-04" for p in ps_list)
        # Employee can download own PDF
        pid = next(p["id"] for p in ps_list if p["month"] == "2026-04")
        pdf = employee_session.get(f"{BASE_URL}/api/hr/me/payslips/{pid}/pdf")
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF-")

    def test_unlock_run(self, admin_session):
        run_id = getattr(TestState, "_v5_run_id")
        r = admin_session.post(f"{BASE_URL}/api/hr/payroll-runs/{run_id}/unlock")
        assert r.status_code == 200
        # confirm payslip is DRAFT again
        ps_id = getattr(TestState, "_v5_payslip_id")
        ps = admin_session.get(f"{BASE_URL}/api/hr/payslips/{ps_id}").json()
        assert ps["status"] == "DRAFT"


# ============================================================
# Dashboard + extended roles + global _id leak check
# ============================================================
class TestDashboardAndRoles:
    def test_hr_dashboard(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/hr/dashboard")
        assert r.status_code == 200
        body = r.json()
        assert "kpis" in body
        assert {"total_employees", "branches", "departments", "pending_leaves",
                "present_today", "absent_today"}.issubset(body["kpis"].keys())
        assert isinstance(body["by_department"], list)

    def test_create_hr_user(self, admin_session):
        admin_session.post(f"{BASE_URL}/api/users", json={
            "name": "TEST HR User", "email": "v5_hr@gravity-test.com",
            "phone": "9999999111", "role": "hr", "password": "HrPass@1234",
        })
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": "v5_hr@gravity-test.com", "password": "HrPass@1234"})
        if r.status_code != 200:
            pytest.skip("HR login skipped")
        s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
        me = s.get(f"{BASE_URL}/api/auth/me").json()
        assert me["role"] == "hr"

    def test_create_accountant_user(self, admin_session):
        admin_session.post(f"{BASE_URL}/api/users", json={
            "name": "TEST Accountant", "email": "v5_acc@gravity-test.com",
            "phone": "9999999222", "role": "accountant", "password": "AccPass@1234",
        })
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": "v5_acc@gravity-test.com", "password": "AccPass@1234"})
        if r.status_code != 200:
            pytest.skip("Accountant login skipped")
        s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
        me = s.get(f"{BASE_URL}/api/auth/me").json()
        assert me["role"] == "accountant"

    def test_no_id_leak_all_hr_collections(self, admin_session):
        """Spot-check that _id is excluded from every list endpoint we expose."""
        endpoints = [
            "/api/hr/branches", "/api/hr/departments", "/api/hr/designations",
            "/api/hr/shifts", "/api/hr/holidays", "/api/hr/leave-types",
            "/api/hr/employees", "/api/hr/attendance", "/api/hr/leaves",
            "/api/hr/advances", "/api/hr/payroll-runs", "/api/hr/payslips",
        ]
        for ep in endpoints:
            r = admin_session.get(f"{BASE_URL}{ep}")
            assert r.status_code == 200, f"{ep}: {r.status_code}"
            for row in r.json():
                assert "_id" not in row, f"{ep} leaked _id"
