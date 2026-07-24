"""Pydantic models for the HRM & Payroll module."""
from typing import List, Optional, Literal

from pydantic import BaseModel, EmailStr


# ---------- Setup tables ----------
class Branch(BaseModel):
    name: str
    code: Optional[str] = None
    location: Optional[str] = None
    manager: Optional[str] = None


class Department(BaseModel):
    name: str
    description: Optional[str] = None
    branch_id: Optional[str] = None


class Designation(BaseModel):
    name: str
    description: Optional[str] = None


class Shift(BaseModel):
    name: str  # e.g., "General", "Day Shift", "Night Shift"
    start_time: str  # "09:00"
    end_time: str  # "18:00"
    weekly_off_days: List[int] = [0]  # 0=Sun..6=Sat
    late_grace_min: int = 10
    full_day_hours: float = 8
    half_day_hours: float = 4
    crosses_midnight: bool = False  # night shift: end_time is on the following calendar day


class Holiday(BaseModel):
    date: str  # YYYY-MM-DD
    name: str
    branch_id: Optional[str] = None  # null = applies to all branches
    description: Optional[str] = None


class LeaveType(BaseModel):
    name: str  # casual, sick, earned, lop
    annual_quota: float = 12
    paid: bool = True
    description: Optional[str] = None


# ---------- Employee ----------
class Employee(BaseModel):
    employee_code: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    gender: Optional[Literal["male", "female", "other"]] = None
    dob: Optional[str] = None
    joining_date: Optional[str] = None
    branch_id: Optional[str] = None
    department_id: Optional[str] = None
    designation: Optional[str] = None
    shift_id: Optional[str] = None
    reporting_to: Optional[str] = None
    salary_type: Literal["MONTHLY", "DAILY", "HOURLY"] = "MONTHLY"
    basic_salary: float = 0
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    pan_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    address: Optional[str] = None
    photo_path: Optional[str] = None
    status: Literal["active", "inactive", "terminated"] = "active"
    # Self-service login
    create_login: bool = False
    login_password: Optional[str] = None


class SalaryStructure(BaseModel):
    employee_id: str
    basic: float
    hra: float = 0
    da: float = 0
    conveyance: float = 0
    medical: float = 0
    special_allowance: float = 0
    other_allowance: float = 0
    pf_percent: float = 12.0  # of basic
    enable_pf: bool = True
    esi_employee_percent: float = 0.75  # of gross (when applicable)
    esi_employer_percent: float = 3.25
    enable_esi: bool = True
    professional_tax: float = 200
    tds_percent: float = 0
    overtime_rate_multiplier: float = 2.0  # 2x of hourly basic
    notes: Optional[str] = None


# ---------- Attendance & Leaves ----------
class Attendance(BaseModel):
    employee_id: str
    date: str  # YYYY-MM-DD
    check_in: Optional[str] = None  # HH:MM
    check_out: Optional[str] = None
    status: Literal[
        "PRESENT", "ABSENT", "HALF_DAY", "LEAVE", "HOLIDAY", "WEEKEND", "LATE"
    ] = "PRESENT"
    working_hours: float = 0
    overtime_hours: float = 0
    remarks: Optional[str] = None
    source: Literal["manual", "qr", "biometric", "self"] = "manual"


class AttendanceBulkRow(BaseModel):
    employee_id: str
    status: Literal["PRESENT", "ABSENT", "HALF_DAY", "LEAVE", "LATE"] = "PRESENT"
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    overtime_hours: float = 0
    remarks: Optional[str] = None


class AttendanceBulkIn(BaseModel):
    date: str
    rows: List[AttendanceBulkRow]


class CheckInOut(BaseModel):
    employee_id: str
    timestamp: Optional[str] = None  # HH:MM, defaults to now


class BiometricPunch(BaseModel):
    employee_code: str
    timestamp: str  # ISO datetime
    punch_type: Literal["IN", "OUT"]
    device_id: Optional[str] = None


class Leave(BaseModel):
    employee_id: str
    leave_type_id: str
    start_date: str
    end_date: str
    total_days: Optional[float] = None
    reason: Optional[str] = None


class LeaveDecision(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    rejection_reason: Optional[str] = None


class Advance(BaseModel):
    employee_id: str
    amount: float
    advance_date: str
    recovery_month: Optional[str] = None  # YYYY-MM
    remarks: Optional[str] = None


# ---------- Payroll ----------
class PayrollRunRequest(BaseModel):
    month: str  # YYYY-MM
    branch_id: Optional[str] = None
    employee_ids: Optional[List[str]] = None  # optional filter
    notes: Optional[str] = None


class PayslipBonusEdit(BaseModel):
    bonus: Optional[float] = None
    incentive: Optional[float] = None
    other_deduction: Optional[float] = None
    other_deduction_label: Optional[str] = None
    notes: Optional[str] = None
