"""Fix circular imports in utils.py and _mongo_compat.py."""
import os, re

BASE = os.path.dirname(__file__)

# ── Fix 1: utils.py — move schema imports inside _table() ─────────────────────
utils_path = os.path.join(BASE, "utils.py")
with open(utils_path, "r", encoding="utf-8") as f:
    utils_src = f.read()

# Remove the top-level schema imports
old_imports = """from .db import get_session
from .schema import (
    AuditLog, Counter,
    User, RefreshToken, Company, Lead, Customer, Vendor,
    Product, ProductCategory, Warehouse, Godown, StockItem,
    StockLedgerEntry, StockTransaction, StockTransfer, Batch, PhysicalVerification, QCReport,
    PurchaseOrder, PurchaseOrderV2, GoodsReceiptNoteV2, PurchaseBill, PurchaseReturn,
    VendorBillSubmission, PONumberAudit,
    Quotation, SalesOrder, Invoice, CreditNote, Dispatch, ProformaInvoice, PaymentLink,
    ChartOfAccount, MasterLedger, MasterGroup, CostCenter, FiscalYear, Currency, VoucherType,
    JournalEntry, Voucher, VoucherV2, VoucherCounter, ExpenseEntry, ExpenseCategory,
    Advance, InterestRule,
    BankAccount, BankEntry, BankStatement, BankStatementLine, BankFeedImport,
    PDC, ChequeTransaction, ChequeFormat,
    Employee, Attendance, AttendanceLog, Leave, LeaveType, Holiday, Shift,
    SalaryStructure, PayComponent, PayrollRun, Payslip, StatutoryParam, FnFSettlement, TDSDeclaration,
    GSTRecord, GSTFilingCache, GSTINCache, GSTReconciliation, TDSEntry, TCSEntry, EWayBill,
    FixedAsset, AssetCategory, AssetDepreciationRun, AssetTransaction,
    Project, ProjectCost, Task, TimesheetEntry,
    BOM, WorkOrder, ProductionJournal, WastageEntry,
    JobWorkChallan, JobWorkReceipt, RateTable,
    ApprovalPolicy, ApprovalRequest, ApprovalStep,
    POSSale, POSSession, PriceList, DiscountScheme,
    WebhookSubscription, WebhookDelivery, PortalUser, APIKey,
    Branch, InterBranchTransfer, Budget,
    ReportSummary, ReportSavedView, UploadedFile, OCRDocument,
    VerificationLog, AIChatHistory, AIConversation,
    VerificationSetting, EInvoiceSetting, PurchaseSetting, ThemeSetting,
    PONumberingSetting,
)"""

new_imports = """from .db import get_session"""

utils_src = utils_src.replace(old_imports, new_imports)

# Also add a lazy import at the top of _COLLECTION_MAP
# Replace the _COLLECTION_MAP dict definition to use lazy imports inside _table()
old_map_header = """# ── collection → model map ─────────────────────────────────────────────────────
_COLLECTION_MAP: dict = {"""

new_map_header = """# ── collection → model map ─────────────────────────────────────────────────────
# Built lazily on first call to avoid circular imports at module load time
_COLLECTION_MAP: dict | None = None


def _build_map() -> dict:
    from . import schema as _s
    return {"""

utils_src = utils_src.replace(old_map_header, new_map_header)

# Find the end of _COLLECTION_MAP and close the new function
old_map_footer = """    "audit_logs": AuditLog,
}


def _table(collection: str):"""

new_map_footer = """        "audit_logs": _s.AuditLog,
    }


def _table(collection: str):
    global _COLLECTION_MAP
    if _COLLECTION_MAP is None:
        _COLLECTION_MAP = _build_map()
"""

utils_src = utils_src.replace(old_map_footer, new_map_footer)

# Fix AuditLog and Counter references in the map to use _s.
# The whole map body needs to be prefixed with _s.
# We already replaced the header/footer; now fix the body entries
# Replace Model references in the map dict
import re

# Find the map dict body and prefix all class names
def prefix_map_values(src):
    # Find the map dict between _build_map() and the closing }
    start = src.find("def _build_map() -> dict:\n    from . import schema as _s\n    return {\n")
    if start == -1:
        return src
    start = src.find("return {", start) + len("return {")

    # find the matching close brace (accounting for nesting)
    depth = 1
    pos = start
    while pos < len(src) and depth > 0:
        if src[pos] == '{':
            depth += 1
        elif src[pos] == '}':
            depth -= 1
        pos += 1
    end = pos - 1  # position of closing }

    body = src[start:end]
    # Replace: "key": ClassName,  ->  "key": _s.ClassName,
    body = re.sub(r': ([A-Z][A-Za-z]+),', lambda m: f': _s.{m.group(1)},', body)
    return src[:start] + body + src[end:]

utils_src = prefix_map_values(utils_src)

# Also fix AuditLog references outside the map (in crud functions)
# These are direct usages like "session.add(AuditLog(...))"
# Replace with lazy import pattern
utils_src = utils_src.replace(
    "from .schema import AuditLog\n",
    ""
)
# Fix remaining AuditLog references in functions
utils_src = re.sub(
    r'\bAuditLog\b(?!\s*=)',
    '__import_AuditLog()',
    utils_src
)

# Actually, simpler: add AuditLog import at the top of each function that uses it
# Or better: just add a lazy helper at module top
lazy_audit = """
def _AuditLog():
    from .schema import AuditLog
    return AuditLog

"""
utils_src = utils_src.replace(
    "__import_AuditLog()",
    "_AuditLog()"
)

# Insert the lazy helper after the imports
utils_src = utils_src.replace(
    "from .db import get_session\n",
    "from .db import get_session\n" + lazy_audit
)

# Also fix Counter reference in next_doc_number
utils_src = re.sub(
    r'\bCounter\b(?!\s*=)',
    '__Counter()',
    utils_src
)
utils_src = utils_src.replace(
    "def _AuditLog():\n    from .schema import AuditLog\n    return AuditLog\n\n",
    "def _AuditLog():\n    from .schema import AuditLog\n    return AuditLog\n\ndef _Counter():\n    from .schema import Counter\n    return Counter\n\n"
)
utils_src = utils_src.replace("__Counter()", "_Counter()")

with open(utils_path, "w", encoding="utf-8") as f:
    f.write(utils_src)
print(f"Fixed utils.py: {len(utils_src)} chars")
print("  Sample check:", "from .db import get_session" in utils_src, "AuditLog" not in utils_src.split("def _AuditLog")[0])
