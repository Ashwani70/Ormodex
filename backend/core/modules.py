"""Canonical list of module-permission keys.

Every router guard checks `user.module_permissions` for one of these keys (an
`admin` role bypasses all of them). Keeping the list in one place means the
user-admin API, the frontend toggles, and the guards can't drift apart.

The keys below were taken from the actual `_require_*` guards in routers/ — keep
them in sync. Some routers accept several keys for one area (e.g. ledger also
accepts "accounting"/"cash_bank"); the granular keys are all listed so an admin
can grant exactly what a guard looks for.
"""

# (key, human label) — label is for UI display only.
MODULES: list[tuple[str, str]] = [
    ("inventory", "Inventory"),
    ("purchase", "Purchase"),
    ("sales", "Sales"),
    ("dispatch", "Dispatch"),
    ("accounting", "Accounting"),
    ("gst", "GST & Tax"),
    ("banking", "Banking"),
    ("cash_bank", "Cash & Bank"),
    ("cheque_template_manage", "Cheque Template Management"),
    ("cheque_print", "Cheque Printing"),
    ("cheque_cancel", "Cheque Cancellation"),
    ("payroll", "Payroll"),
    ("hr", "HR & Employees"),
    ("biometric", "Biometric Attendance"),
    ("manufacturing", "Manufacturing"),
    ("pricing", "Pricing"),
    ("pos", "Point of Sale"),
    ("fixed_assets", "Fixed Assets"),
    ("expenses", "Expense Management"),
    ("ledger", "Ledger"),
    ("vouchers", "Vouchers"),
    ("approve_vouchers", "Approve Vouchers"),
    ("approver", "Approver"),
    ("masters", "Masters"),
    ("mis_reports", "MIS Reports"),
    ("reports", "Reports"),
    ("ai_tools", "AI Tools"),
    ("integration", "Integration"),
    ("branch_admin", "Branch Admin"),
    ("audit", "Audit Logs"),
    ("letterhead_design", "Letterhead Designer"),
    ("letterhead_manage", "Letterhead Template Management"),
    ("company_profile", "Company Profile"),
    ("po_numbering", "PO Numbering"),
    ("po_number_edit", "PO Number Manual Entry"),
    ("po_number_override", "PO Number Override"),
    ("document_numbering", "Document Numbering"),
]

MODULE_KEYS: set[str] = {key for key, _ in MODULES}


def valid_module_keys(keys: list[str] | None) -> list[str]:
    """Return only the recognised keys, de-duplicated and order-preserved.

    Unknown keys are silently dropped rather than raising, so a stale frontend
    or a renamed module can't 500 the user-admin API; the effect is simply that
    the bogus key grants nothing.
    """
    seen: set[str] = set()
    out: list[str] = []
    for k in keys or []:
        if k in MODULE_KEYS and k not in seen:
            seen.add(k)
            out.append(k)
    return out
