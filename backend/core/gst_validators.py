"""Reusable GST / e-Way Bill validation utilities.

Pure, dependency-free format validators used by the e-Way Bill (and other GST)
flows. Each ``validate_*`` returns ``(ok: bool, error: str | None)`` so callers
can surface a precise message; ``is_*`` thin wrappers return just the bool.

These check *format/structure* only — they do not call the government portal.
A format-valid GSTIN/HSN can still be unregistered/inactive; that is confirmed
by the live NIC/GSTN lookup, not here.
"""
from __future__ import annotations

import re

# 15-char GSTIN: 2-digit state code, 10-char PAN, entity number, 'Z', checksum.
GSTIN_PATTERN = re.compile(r"^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

# Indian PIN code: 6 digits, first digit 1-9 (no leading zero).
PINCODE_PATTERN = re.compile(r"^[1-9][0-9]{5}$")

# HSN (goods) / SAC (services) code: 4, 6 or 8 digits (HSN) — SAC is 6.
HSN_PATTERN = re.compile(r"^\d{4}(\d{2})?(\d{2})?$")

# Vehicle registration number, NIC e-Way Bill accepted formats. NIC stores it
# without spaces/hyphens and uppercased. Covers the common BHARAT/state series:
#   AA 00 AA 0000   (e.g. MH12AB1234)
#   AA 00 A 0000    (single middle letter, e.g. MH12A1234)
#   AA 00 0000      (no middle letter, older series)
#   AA 0000         (defence/older)
# plus the BH (Bharat) series: 00 BH 0000 AA.
VEHICLE_PATTERNS = (
    re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$"),  # standard state series
    re.compile(r"^[A-Z]{2}[0-9]{1,2}[0-9]{4}$"),            # no middle letters
    re.compile(r"^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$"),          # Bharat (BH) series
)

# Valid GST state codes (01-37 plus 97 Other Territory, 99 Centre Jurisdiction).
VALID_STATE_CODES = {f"{i:02d}" for i in range(1, 38)} | {"97", "99"}


def normalize_gstin(gstin: str | None) -> str:
    return (gstin or "").strip().upper().replace(" ", "")


def normalize_vehicle(vehicle: str | None) -> str:
    """NIC stores vehicle numbers uppercased with no spaces/hyphens."""
    return re.sub(r"[\s\-]", "", (vehicle or "").strip().upper())


def validate_gstin(gstin: str | None) -> tuple[bool, str | None]:
    g = normalize_gstin(gstin)
    if not g:
        return False, "GSTIN is required."
    if len(g) != 15:
        return False, "GSTIN must be 15 characters."
    if not GSTIN_PATTERN.match(g):
        return False, "Invalid GSTIN format."
    if g[:2] not in VALID_STATE_CODES:
        return False, f"Invalid GST state code '{g[:2]}'."
    return True, None


def validate_pincode(pincode: str | int | None) -> tuple[bool, str | None]:
    p = str(pincode or "").strip()
    if not p:
        return False, "PIN code is required."
    if not PINCODE_PATTERN.match(p):
        return False, "Invalid Indian PIN code (must be 6 digits, not starting with 0)."
    return True, None


def validate_hsn(hsn: str | int | None) -> tuple[bool, str | None]:
    h = str(hsn or "").strip()
    if not h:
        return False, "HSN/SAC code is required."
    if not HSN_PATTERN.match(h):
        return False, "Invalid HSN/SAC code (must be 4, 6 or 8 digits)."
    return True, None


def validate_vehicle_number(vehicle: str | None) -> tuple[bool, str | None]:
    v = normalize_vehicle(vehicle)
    if not v:
        return False, "Vehicle number is required."
    if not (4 <= len(v) <= 11):
        return False, "Vehicle number length is invalid."
    if any(p.match(v) for p in VEHICLE_PATTERNS):
        return True, None
    return False, "Invalid vehicle number format (e.g. MH12AB1234)."


# Thin boolean wrappers --------------------------------------------------------

def is_valid_gstin(gstin: str | None) -> bool:
    return validate_gstin(gstin)[0]


def is_valid_pincode(pincode: str | int | None) -> bool:
    return validate_pincode(pincode)[0]


def is_valid_hsn(hsn: str | int | None) -> bool:
    return validate_hsn(hsn)[0]


def is_valid_vehicle_number(vehicle: str | None) -> bool:
    return validate_vehicle_number(vehicle)[0]
