"""Pydantic models for the eSSL Biometric Attendance Integration module."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class BiometricDeviceIn(BaseModel):
    name: str
    serial_number: Optional[str] = None
    branch_id: Optional[str] = None
    device_model: Optional[str] = None
    integration_mode: Literal["push", "poll"] = "push"
    host: Optional[str] = None  # required for poll mode
    port: int = 4370
    api_path: Optional[str] = None  # e.g. "/iclock/getrequest" (ADMS-style) or vendor REST path
    poll_interval_seconds: int = Field(default=300, ge=60, le=86400)
    is_active: bool = True
    notes: Optional[str] = None


class BiometricDeviceUpdate(BaseModel):
    name: Optional[str] = None
    serial_number: Optional[str] = None
    branch_id: Optional[str] = None
    device_model: Optional[str] = None
    integration_mode: Optional[Literal["push", "poll"]] = None
    host: Optional[str] = None
    port: Optional[int] = None
    api_path: Optional[str] = None
    poll_interval_seconds: Optional[int] = Field(default=None, ge=60, le=86400)
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class EmployeeDeviceMappingIn(BaseModel):
    device_id: str
    employee_id: str
    device_enrollment_id: str  # the device's own numeric user id for this person


class DevicePunchIn(BaseModel):
    """Shape of one punch as reported by an eSSL/ADMS-style device push.
    device_enrollment_id is the device's own user id (not our employee_id) —
    resolved via EmployeeDeviceMapping. punch_id, if the device provides one,
    is used as part of the dedup key; otherwise device_id+enrollment+time is used."""
    device_enrollment_id: str
    timestamp: str  # ISO datetime
    direction: Optional[Literal["IN", "OUT"]] = None  # None = device doesn't distinguish; inferred
    punch_id: Optional[str] = None
    raw: Optional[dict] = None


class DevicePushIn(BaseModel):
    """Body of an inbound push webhook from one device — may batch several punches."""
    punches: List[DevicePunchIn]


class SyncTriggerIn(BaseModel):
    device_id: Optional[str] = None  # None = sync all active devices


class AttendanceRuleIn(BaseModel):
    shift_id: Optional[str] = None  # None = tenant-wide default rule
    late_grace_minutes: int = 10
    early_leave_grace_minutes: int = 10
    half_day_threshold_hours: float = 4.0
    full_day_threshold_hours: float = 8.0
    overtime_after_hours: float = 9.0
    missing_punch_action: Literal["flag", "absent", "ignore"] = "flag"
    is_active: bool = True


class AttendanceRuleUpdate(BaseModel):
    late_grace_minutes: Optional[int] = None
    early_leave_grace_minutes: Optional[int] = None
    half_day_threshold_hours: Optional[float] = None
    full_day_threshold_hours: Optional[float] = None
    overtime_after_hours: Optional[float] = None
    missing_punch_action: Optional[Literal["flag", "absent", "ignore"]] = None
    is_active: Optional[bool] = None


class MonthlyAggregateRunIn(BaseModel):
    period: str  # "MMYYYY", matches routers/payroll.py's period key
    employee_ids: Optional[List[str]] = None  # None = all employees with attendance in the period


class AttendanceCorrectionIn(BaseModel):
    employee_id: str
    attendance_date: str  # YYYY-MM-DD
    requested_check_in: Optional[str] = None  # HH:MM
    requested_check_out: Optional[str] = None
    requested_status: Optional[str] = None  # e.g. force PRESENT/LEAVE without punch times
    reason: str


class AttendanceCorrectionDecision(BaseModel):
    status: Literal["APPROVED", "REJECTED"]
    rejection_reason: Optional[str] = None
