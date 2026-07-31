from typing import Any, Optional
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException

from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import get_session



# ── Mongo-compat shims (kept so routers/tests that reference the old data layer
# keep working and type-checking during the Postgres migration). `_txn_supported`
# is vestigial — Postgres always has transactions — but tests still patch it to
# force the no-transaction fallback path. ────────────────────────────────────
_txn_supported: Optional[bool] = True


async def _transactions_available() -> bool:
    """Whether the data layer supports multi-statement transactions.

    Always True on Postgres; retained as a patch point for tests that exercise
    the non-transactional fallback by setting ``utils._txn_supported = False``.
    """
    return bool(_txn_supported)


class _LazyDB:
    """Lazy proxy to the Mongo-compat ``db`` facade.

    A module-level ``__getattr__`` was used before, but Python only consults a
    module's ``__getattr__`` for *external* attribute access (``core.utils.db``);
    a bare ``db`` reference *inside* this module's own functions goes through the
    normal globals lookup, which never triggers ``__getattr__`` and raised
    ``NameError: name 'db' is not defined`` (e.g. in ``crud_list``).

    This proxy is a real module global, so in-module references resolve, while
    the underlying facade is still imported lazily on first use to avoid the
    utils ↔ _mongo_compat circular import (_mongo_compat imports _table from here).
    """
    __slots__ = ()

    def _facade(self):
        from ._mongo_compat import db as _db
        return _db

    def __getattr__(self, name):
        return getattr(self._facade(), name)

    def __getitem__(self, name):
        return self._facade()[name]


db = _LazyDB()


def new_id() -> str:
    return uuid.uuid4().hex


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── lazy schema helpers (break circular import) ────────────────────────────────
def _AuditLog():
    from .schema import AuditLog
    return AuditLog


def _Counter():
    from .schema import Counter
    return Counter


# ── collection → model map (lazy) ─────────────────────────────────────────────
_COLLECTION_MAP: Optional[dict] = None


def _build_collection_map() -> dict:
    from . import schema as _s
    return {
        "users": _s.User,
        "refresh_tokens": _s.RefreshToken,
        "user_devices": _s.UserDevice,
        "login_history": _s.LoginHistory,
        "company": _s.Company,
        "companies": _s.Company,
        "leads": _s.Lead,
        "customers": _s.Customer,
        "vendors": _s.Vendor,
        "suppliers": _s.Vendor,
        "products": _s.Product,
        "product_categories": _s.ProductCategory,
        "uoms": _s.UOM,
        "warehouses": _s.Warehouse,
        "godowns": _s.Godown,
        "stock_items": _s.StockItem,
        "stock_ledger_entries": _s.StockLedgerEntry,
        "stock_transactions": _s.StockTransaction,
        "stock_transfers": _s.StockTransfer,
        "batches": _s.Batch,
        "physical_verifications": _s.PhysicalVerification,
        "qc_reports": _s.QCReport,
        "purchase_orders": _s.PurchaseOrder,
        "purchase_orders_v2": _s.PurchaseOrderV2,
        "grn_v2": _s.GoodsReceiptNoteV2,
        # purchase_v2.py / po_numbering.py refer to this collection by its long
        # name; the model's physical table is grn_v2. Without this alias every
        # GRN-v2 read returned empty and every write silently no-op'd.
        "goods_receipt_notes_v2": _s.GoodsReceiptNoteV2,
        "purchase_bills": _s.PurchaseBill,
        "purchase_returns": _s.PurchaseReturn,
        "vendor_bill_submissions": _s.VendorBillSubmission,
        "po_number_audit": _s.PONumberAudit,
        "quotations": _s.Quotation,
        "sales_orders": _s.SalesOrder,
        "invoices": _s.Invoice,
        "credit_notes": _s.CreditNote,
        "dispatches": _s.Dispatch,
        "proforma_invoices": _s.ProformaInvoice,
        "payment_links": _s.PaymentLink,
        "chart_of_accounts": _s.ChartOfAccount,
        "master_ledgers": _s.MasterLedger,
        "master_groups": _s.MasterGroup,
        "cost_centers": _s.CostCenter,
        "fiscal_years": _s.FiscalYear,
        "currencies": _s.Currency,
        "voucher_types": _s.VoucherType,
        "journal_entries": _s.JournalEntry,
        "vouchers": _s.Voucher,
        "vouchers_v2": _s.VoucherV2,
        "voucher_counters": _s.VoucherCounter,
        "expense_entries": _s.ExpenseEntry,
        "expense_categories": _s.ExpenseCategory,
        "advances": _s.Advance,
        "interest_rules": _s.InterestRule,
        "bank_accounts": _s.BankAccount,
        "bank_entries": _s.BankEntry,
        "bank_statements": _s.BankStatement,
        "bank_statement_lines": _s.BankStatementLine,
        "bank_feed_imports": _s.BankFeedImport,
        "pdcs": _s.PDC,
        "cheque_transactions": _s.ChequeTransaction,
        "cheque_formats": _s.ChequeFormat,
        "employees": _s.Employee,
        "attendance": _s.Attendance,
        "attendance_logs": _s.AttendanceLog,
        "biometric_devices": _s.BiometricDevice,
        "employee_device_mappings": _s.EmployeeDeviceMapping,
        "attendance_sync_runs": _s.AttendanceSyncRun,
        "attendance_rules": _s.AttendanceRule,
        "attendance_corrections": _s.AttendanceCorrection,
        "leaves": _s.Leave,
        "leave_types": _s.LeaveType,
        "holidays": _s.Holiday,
        "shifts": _s.Shift,
        "salary_structures": _s.SalaryStructure,
        "pay_components": _s.PayComponent,
        "payroll_runs": _s.PayrollRun,
        "payslips": _s.Payslip,
        "statutory_params": _s.StatutoryParam,
        "fnf_settlements": _s.FnFSettlement,
        "tds_declarations": _s.TDSDeclaration,
        "gst_records": _s.GSTRecord,
        "gst_filing_cache": _s.GSTFilingCache,
        "gstin_cache": _s.GSTINCache,
        "gst_reconciliations": _s.GSTReconciliation,
        # gst_accounting.py uses the singular form; alias to the same model so
        # reconciliation reads/writes hit the gst_reconciliations table.
        "gst_reconciliation": _s.GSTReconciliation,
        "tds_entries": _s.TDSEntry,
        "tcs_entries": _s.TCSEntry,
        "eway_bills": _s.EWayBill,
        "fixed_assets": _s.FixedAsset,
        "asset_categories": _s.AssetCategory,
        "asset_depreciation_runs": _s.AssetDepreciationRun,
        "asset_transactions": _s.AssetTransaction,
        "projects": _s.Project,
        "project_costs": _s.ProjectCost,
        "tasks": _s.Task,
        "timesheet_entries": _s.TimesheetEntry,
        "boms": _s.BOM,
        "work_orders": _s.WorkOrder,
        "production_journals": _s.ProductionJournal,
        "wastage_entries": _s.WastageEntry,
        "job_work_challans": _s.JobWorkChallan,
        "job_work_challan_items": _s.JobWorkChallanItem,
        "job_work_receipts": _s.JobWorkReceipt,
        "job_work_receipt_items": _s.JobWorkReceiptItem,
        "rate_tables": _s.RateTable,
        "approval_policies": _s.ApprovalPolicy,
        "approval_requests": _s.ApprovalRequest,
        "approval_steps": _s.ApprovalStep,
        "pos_sales": _s.POSSale,
        "pos_sessions": _s.POSSession,
        "price_lists": _s.PriceList,
        "discount_schemes": _s.DiscountScheme,
        "webhook_subscriptions": _s.WebhookSubscription,
        "webhook_deliveries": _s.WebhookDelivery,
        "portal_users": _s.PortalUser,
        "api_keys": _s.APIKey,
        "branches": _s.Branch,
        "inter_branch_transfers": _s.InterBranchTransfer,
        "budgets": _s.Budget,
        "report_summaries": _s.ReportSummary,
        "report_saved_views": _s.ReportSavedView,
        "uploaded_files": _s.UploadedFile,
        "ocr_documents": _s.OCRDocument,
        "verification_logs": _s.VerificationLog,
        "ai_chat_history": _s.AIChatHistory,
        "ai_conversations": _s.AIConversation,
        "verification_settings": _s.VerificationSetting,
        "einvoice_settings": _s.EInvoiceSetting,
        "purchase_settings": _s.PurchaseSetting,
        "theme_settings": _s.ThemeSetting,
        "po_numbering_settings": _s.PONumberingSetting,
        "document_numbering_settings": _s.DocumentNumberingSetting,
        "counters": _s.Counter,
        "audit_logs": _s.AuditLog,
        # Tables missed by the initial migration (added after audit found these
        # collections were unmapped → silent empty reads / swallowed writes).
        "hr_branches": _s.HRBranch,
        "hr_departments": _s.HRDepartment,
        "hr_designations": _s.HRDesignation,
        "overtime_entries": _s.OvertimeEntry,
        "salary_payments": _s.SalaryPayment,
        "cheques": _s.Cheque,
        "cheque_templates": _s.ChequeTemplate,
        "godown_rates": _s.GodownRate,
        "it_blocks": _s.ITBlock,
        "buyer_orders": _s.BuyerOrder,
        "fabric_trims": _s.FabricTrim,
        "stitching_lines": _s.StitchingLine,
        "backups": _s.Backup,
        # Debtors & Creditors (AR/AP)
        "dc_ledger_entries":     _s.DcLedgerEntry,
        "dc_payment_allocations": _s.DcPaymentAllocation,
        "dc_party_balances":     _s.DcPartyBalance,
        "dc_credit_limits":      _s.DcCreditLimit,
        "dc_collection_notes":   _s.DcCollectionNote,
        "dc_reminder_logs":      _s.DcReminderLog,
        # Letterhead Designer
        "letterhead_templates":  _s.LetterheadTemplate,
        "letterhead_versions":   _s.LetterheadVersion,
        # Cheque issue register (added in migration 011)
        "cheque_issue_register": _s.ChequeIssueRegister,
    }


def _table(collection: str):
    global _COLLECTION_MAP
    if _COLLECTION_MAP is None:
        _COLLECTION_MAP = _build_collection_map()
    model = _COLLECTION_MAP.get(collection)
    if model is None:
        raise ValueError(f"No model mapped for collection: {collection!r}")
    return model


def _alias_items_to_lines(doc: dict) -> dict:
    """Map the app-facing `items` field onto the real `lines` JSONB column.

    Every sales/purchase document router (Invoice, Quotation, SalesOrder,
    PurchaseOrderV2, GRN, PurchaseBill, PurchaseReturn, CreditNote, Dispatch,
    ProformaInvoice, ...) reads/writes `items`, but their ORM tables in
    schema.py store the line-item array under a column literally named
    `lines` (not `items`, and not the generic `extra`/`data` overflow columns
    the generic packer in crud_create/crud_update already understands). Without
    this, `items` silently has nowhere to go — it's dropped on write and the
    document round-trips with no line items at all (see: GST Invoice PDFs
    missing qty/rate/HSN because the DB row never had them)."""
    if "items" in doc:
        doc = dict(doc)
        doc["lines"] = doc.pop("items")
    return doc


# JSONB "overflow" column names, in priority order, that a table might use to
# hold fields with no dedicated column of their own. Keep in sync with
# _mongo_compat.py's _OVERFLOW_COLUMNS — that file covers db[collection].*
# writes, this one covers crud_create/crud_update. `gst_details` is what the
# sales/purchase document tables (Quotation, SalesOrder, Invoice, ..., and
# ProformaInvoice) actually have; nothing writes whole-document data into it
# under its literal name, so it's safe to reuse the same way extra/data are.
_OVERFLOW_COLUMNS = ("extra", "data", "gst_details")


def _find_overflow_column(Model) -> Optional[str]:
    for name in _OVERFLOW_COLUMNS:
        if hasattr(Model, name):
            return name
    return None


def _pack_overflow_fields(data: dict, Model) -> dict:
    """Move any key with no matching column into the table's overflow JSONB
    column (see _OVERFLOW_COLUMNS), merging with whatever's already there.
    Used by both crud_create and crud_update so a field like `buyer_name` or
    `bank_name` (real request data, no dedicated column) doesn't silently
    vanish on save — see _alias_items_to_lines for the sibling bug this
    mirrors (items -> lines instead of extra/data)."""
    col = _find_overflow_column(Model)
    if col is None:
        return data
    data = dict(data)
    current = data.get(col) or {}
    current = dict(current) if isinstance(current, dict) else {}
    overflow_keys = [k for k in data.keys() if k not in ("id", col) and not hasattr(Model, k)]
    for k in overflow_keys:
        current[k] = data.pop(k)
    if current:
        data[col] = current
    return data


def _prepare_payslip_doc(doc: dict) -> dict:
    doc = dict(doc)
    gross = doc.pop("gross_salary", doc.get("gross"))
    net = doc.pop("net_salary", doc.get("net"))
    total_ded = doc.get("total_deduction")
    if total_ded is None:
        ded_val = doc.get("deductions")
        if isinstance(ded_val, (int, float)):
            total_ded = ded_val
        elif isinstance(ded_val, dict):
            total_ded = sum(float(x or 0) for x in ded_val.values())
    comp = doc.get("components") or {}
    if not isinstance(comp, dict):
        comp = {}
    else:
        comp = dict(comp)
    payslip_columns = {"id", "tenant_id", "payroll_run_id", "employee_id", "month", "year", "gross", "deductions", "net", "components", "status", "created_at", "updated_at"}
    for k in list(doc.keys()):
        if k not in payslip_columns and k != "total_deduction":
            comp[k] = doc.pop(k)
    doc["gross"] = gross
    doc["deductions"] = total_ded
    doc["net"] = net
    doc["components"] = comp
    return doc


def _row_to_dict(row) -> Optional[dict]:
    """Convert a SQLAlchemy ORM row to a plain dict."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    d = {}
    mapper = getattr(row, "__mapper__", None)
    if mapper is not None:
        for attr in mapper.attrs:
            if hasattr(attr, "columns"):
                val = getattr(row, attr.key)
                if isinstance(val, Decimal):
                    val = float(val)
                d[attr.key] = val
    else:
        table = getattr(row, "__table__", None)
        if table is not None:
            for col in table.columns:
                try:
                    val = getattr(row, col.name)
                    if isinstance(val, Decimal):
                        val = float(val)
                    d[col.name] = val
                except AttributeError:
                    pass
        else:
            for k, v in getattr(row, "__dict__", {}).items():
                if not k.startswith("_"):
                    if isinstance(v, Decimal):
                        v = float(v)
                    d[k] = v

    # Unpack `extra` JSONB column if present to restore MongoDB-compatible top-level keys
    extra = d.get("extra")
    if isinstance(extra, dict):
        for k, v in extra.items():
            d.setdefault(k, v)

    # Unpack `data` JSONB column if present to restore MongoDB-compatible top-level keys
    data = d.get("data")
    if isinstance(data, dict):
        for k, v in data.items():
            d.setdefault(k, v)

    # Unpack `gst_details` JSONB column the same way, for the sales/purchase
    # document tables that use it as their overflow bucket (see
    # _apply_set_update's _OVERFLOW_COLUMNS in _mongo_compat.py). setdefault
    # only — never clobbers a real column or a genuine GST-details value.
    gst_details = d.get("gst_details")
    if isinstance(gst_details, dict):
        for k, v in gst_details.items():
            d.setdefault(k, v)

    # Alias `lines` back to `items` — the app-facing name every sales/purchase
    # document router reads (see _alias_items_to_lines for why the DB column
    # is named `lines` instead). Only when the table doesn't already have its
    # own real `items` column (e.g. StockTransfer, legacy PurchaseOrder).
    if "lines" in d and "items" not in d:
        d["items"] = d["lines"]

    # Special handling for Payslip ORM model to restore MongoDB-compatible top-level keys
    if getattr(row, "__tablename__", None) == "payslips":
        d["gross_salary"] = d.get("gross")
        d["total_deduction"] = d.get("deductions")
        d["net_salary"] = d.get("net")
        comp = d.get("components") or {}
        if isinstance(comp, dict):
            d["earnings"] = comp.get("earnings", {})
            d["deductions"] = comp.get("deductions", {})
            for k, v in comp.items():
                if k not in ("earnings", "deductions"):
                    d.setdefault(k, v)

    return d


# ── atomic sequence counter ────────────────────────────────────────────────────
async def next_doc_number(prefix: str, collection: str, tenant_id: Optional[str] = None) -> str:
    """`tenant_id` defaults to core.tenant.DEFAULT_TENANT ("default") so every
    existing call site (sales/purchase/manufacturing/... routers) keeps
    producing the exact same keys/numbers it does today without being
    touched. Callers that DO know their tenant (post-Phase-3 auth wiring)
    should pass it explicitly so sequences are scoped per company instead of
    shared — migration 032_tenant_backfill.py renames existing counter rows
    to the "default:"-prefixed key format in anticipation of this.
    """
    from .tenant import DEFAULT_TENANT
    Counter = _Counter()
    key = f"{tenant_id or DEFAULT_TENANT}:{collection}:{prefix}"
    async with get_session() as session:
        stmt = (
            pg_insert(Counter)
            .values(key=key, seq=1)
            .on_conflict_do_update(
                index_elements=["key"],
                set_={"seq": Counter.seq + 1},
            )
            .returning(Counter.seq)
        )
        result = await session.execute(stmt)
        seq = result.scalar_one()
    return f"{prefix}{seq:05d}"


# ── audit helpers ──────────────────────────────────────────────────────────────
def _json_safe(value):
    """Make a value safe to store in a JSONB column.

    Audit ``before``/``after`` snapshots come straight from ``_row_to_dict``, so
    they carry raw column values. Postgres ``numeric`` columns come back as
    ``Decimal`` and date/time columns as ``datetime``/``date`` — neither is JSON
    serializable, so writing them into the JSONB audit columns raised
    ``TypeError: Object of type Decimal is not JSON serializable`` and turned
    every delete/update of a record with such a column (e.g. a customer with a
    ``credit_limit``) into a 500. Coerce recursively: Decimal→float,
    date/datetime→ISO string, leaving JSON-native types untouched.
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def build_audit_entry(
    action: str,
    collection: str,
    doc_id: str,
    user: Optional[dict] = None,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    tenant_id: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    return {
        "id": new_id(),
        "tenant_id": tenant_id or (user or {}).get("tenant_id"),
        "action": action,
        "collection": collection,
        "doc_id": doc_id,
        "user_id": (user or {}).get("id"),
        "user_email": (user or {}).get("email"),
        # Coerce to JSON-safe values — these go into JSONB columns and raw
        # Decimal/datetime from the ORM row would otherwise 500 the write.
        "before": _json_safe(before),
        "after": _json_safe(after),
        "ip": ip,
        "user_agent": user_agent,
        "created_at": now_iso(),
    }


async def log_audit(
    action,
    collection: Optional[str] = None,
    doc_id: Optional[str] = None,
    user: Optional[dict] = None,
    *,
    old_values: Optional[dict] = None,
    new_values: Optional[dict] = None,
    tenant_id: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    session=None,
) -> None:
    """Write one audit row.

    Two call styles are supported so all routers keep working through the
    Mongo→Postgres migration:

      * legacy:  log_audit("CREATE", coll, doc_id, user, new_values=doc, ip=...)
      * direct:  log_audit(build_audit_entry(...))  # `action` is the entry dict

    `old_values`/`new_values` map to the `before`/`after` JSONB columns.
    """
    if isinstance(action, dict):
        entry = dict(action)
    else:
        if not user:
            return  # nothing to attribute the change to
        entry = build_audit_entry(
            action, collection or "", doc_id or "", user,
            before=old_values, after=new_values,
            tenant_id=tenant_id, ip=ip, user_agent=user_agent,
        )
    # Legacy aliases for consumers/tests that read the *_json field names. The
    # data layer drops keys that aren't real columns, so these are harmless in
    # Postgres and available to the in-memory fake used by the unit suite.
    entry.setdefault("before_json", entry.get("before"))
    entry.setdefault("after_json", entry.get("after"))
    from ._mongo_compat import db  # lazy: avoids utils ↔ _mongo_compat cycle
    await db.audit_logs.insert_one(entry, session=session)


# ── generic CRUD ───────────────────────────────────────────────────────────────
# Collections whose writes must invalidate the generation-guarded "stock" cache
# (the /products list). The compat shim covers db.* writes; these crud_* helpers
# bypass it, so they bump the generation here too. Keep in sync with
# _mongo_compat._STOCK_GEN_COLLECTIONS.
_STOCK_GEN_COLLECTIONS = frozenset({"products", "stock_ledger_entries", "stock_items"})
_CATEGORY_COLLECTIONS = frozenset({"product_categories"})


def _bump_stock_gen_if_needed(collection: str) -> None:
    from . import cache
    if collection in _STOCK_GEN_COLLECTIONS:
        cache.bump_generation("stock")
    if collection in _CATEGORY_COLLECTIONS:
        cache.invalidate_prefix("categories:")


async def crud_create(collection: str, data: dict, user: Optional[dict] = None) -> dict:
    AuditLog = _AuditLog()
    Model = _table(collection)
    if "id" not in data or not data["id"]:
        data["id"] = new_id()
    now = now_iso()
    data.setdefault("created_at", now)
    data.setdefault("updated_at", now)
    if hasattr(Model, "tenant_id"):
        from .tenant import TENANT_ENFORCEMENT, current_tenant
        if TENANT_ENFORCEMENT:
            data.setdefault("tenant_id", current_tenant())

    if collection == "payslips":
        data = _prepare_payslip_doc(data)
    elif hasattr(Model, "lines") and not hasattr(Model, "items"):
        data = _alias_items_to_lines(data)

    data = _pack_overflow_fields(data, Model)

    async with get_session() as session:
        row = Model(**{k: v for k, v in data.items() if hasattr(Model, k)})
        session.add(row)
        await session.flush()
        if user:
            session.add(AuditLog(**build_audit_entry(
                "create", collection, data["id"], user, after=data,
                tenant_id=data.get("tenant_id"),
            )))
    _bump_stock_gen_if_needed(collection)

    # Unpack the overflow column before returning to preserve expected fields
    # on the POST response (mirrors _row_to_dict's read-path unpacking).
    overflow_col = _find_overflow_column(Model)
    if overflow_col and isinstance(data.get(overflow_col), dict):
        for k, v in data[overflow_col].items():
            data.setdefault(k, v)
    if collection == "payslips":
        data["gross_salary"] = data.get("gross")
        data["total_deduction"] = data.get("deductions")
        data["net_salary"] = data.get("net")
        comp = data.get("components") or {}
        if isinstance(comp, dict):
            data["earnings"] = comp.get("earnings", {})
            data["deductions"] = comp.get("deductions", {})
            for k, v in comp.items():
                if k not in ("earnings", "deductions"):
                    data.setdefault(k, v)

    return data


# ── Row-level ownership (2026-07-29) ─────────────────────────────────────────
# An Employee-tier user only sees rows they created in these 7 tables — every
# other table (Products, Inventory, Accounting, Dashboard/Reports, etc.) stays
# gated by module_permissions alone, as before. See alembic/versions/
# 031_row_ownership.py for the created_by column + composite-index migration,
# and core/auth_utils.py's bypasses_row_ownership() for who skips this
# filtering (Admin/Super Admin/Manager, plus whatever a specific router's own
# access rule already grants — e.g. purchase_v2's accountant/"purchase"-
# permission check, computed by the caller and passed in as `bypass`).
OWNED_COLLECTIONS: frozenset[str] = frozenset({
    "customers", "vendors", "quotations", "sales_orders",
    "invoices", "purchase_orders_v2", "purchase_bills",
})


def apply_ownership_filter(
    filt: Optional[dict], user: dict, collection: str, *, bypass: bool = False,
) -> dict:
    """Merge a "created_by is me, OR created_by is NULL (grandfathered
    pre-feature rows)" constraint into a list-query filter dict for an
    Employee-tier user reading one of OWNED_COLLECTIONS.

    Nested under "$and" rather than writing a top-level "created_by"/"$or"
    key directly: crud_list/paginated_list add their OWN "$or" for text
    search AFTER calling this function, and a second top-level "$or" key
    would silently overwrite this one (last-write-wins on the same dict
    key) — "$and": [{"$or": [...]}] composes safely no matter what the
    caller adds to the filter afterward.

    A plain {"created_by": user_id} equality would ALSO be wrong on its own
    even without the collision risk: SQL's three-valued NULL logic means
    "created_by = :uid" never matches created_by IS NULL rows, which would
    hide every pre-existing (grandfathered) row from every Employee-tier
    user — exactly the "looks like mass data loss on rollout day" outcome
    the grandfathering decision was meant to avoid. Explicit $exists:false
    (-> IS NULL) covers that case.

    `bypass` is computed by the CALLER, not re-derived here: each router
    already has its own access rule (sales.py has none — any non-bypass role
    is row-filtered; purchase_v2.py requires accountant role or the
    "purchase" module permission before you can reach these endpoints at
    all), so there is no single global "who bypasses" expression to hardcode.
    """
    from .auth_utils import bypasses_row_ownership
    f = dict(filt or {})
    if collection not in OWNED_COLLECTIONS or bypass or bypasses_row_ownership(user.get("role")):
        return f
    ownership_clause = {"$or": [{"created_by": user.get("id")}, {"created_by": {"$exists": False}}]}
    existing_and = f.pop("$and", None)
    f["$and"] = ([*existing_and, ownership_clause] if existing_and else [ownership_clause])
    return f


def assert_owns_or_404(
    doc: dict, user: dict, collection: str, *, bypass: bool = False, label: str = "Record",
) -> dict:
    """For a single fetched row from OWNED_COLLECTIONS, 404 (never 403 — don't
    leak that another user's record exists) when an Employee-tier user reads
    a row they didn't create.

    Rows with created_by IS NULL (everything that existed before this
    feature shipped — nobody "owns" them in the new system) are deliberately
    grandfathered as visible to everyone: the alternative (hiding them from
    every non-admin user until manually reassigned) would look like mass
    data loss on the day this ships, for data that was never actually
    private under the old model.

    Call this explicitly at each GET-by-id/PUT/DELETE site for the 7 owned
    collections — crud_get/crud_update/crud_delete stay untouched since
    they're shared with dozens of non-owned collections (products, company,
    settings, ...) where this check would be wrong.
    """
    from .auth_utils import bypasses_row_ownership
    if collection in OWNED_COLLECTIONS and not bypass and not bypasses_row_ownership(user.get("role")):
        owner = doc.get("created_by")
        if owner and owner != user.get("id"):
            raise HTTPException(status_code=404, detail=f"{label} not found")
    return doc


def _tenant_where(Model, stmt):
    """Append a tenant_id condition to a select()/update-target statement when
    Model is tenant-scoped and enforcement is on — the core/utils.py-side
    counterpart of core/_mongo_compat.py's _tenant_cond, needed because
    crud_get/crud_update/crud_delete use SQLAlchemy select()/session.get()
    directly rather than going through the compat layer's _to_filter(). Not
    shared as one function across both modules to avoid a circular import
    (core/_mongo_compat.py already imports from core/utils.py); both read the
    same core.tenant.current_tenant()/TENANT_ENFORCEMENT source of truth, so
    the two implementations can't drift in meaning, only in file location.
    """
    if not hasattr(Model, "tenant_id"):
        return stmt
    from .tenant import TENANT_BYPASS, TENANT_ENFORCEMENT, current_tenant
    if not TENANT_ENFORCEMENT:
        return stmt
    tenant = current_tenant()
    if tenant == TENANT_BYPASS:
        return stmt
    return stmt.where(Model.tenant_id == tenant)


async def crud_get(collection: str, doc_id: str, label: str = "Record") -> dict:
    """Fetch one document by id, or raise 404.

    Returns a plain dict (never None) so callers can subscript/`.get()` the
    result directly. `label` customises the 404 message (e.g. "Product not found").

    Uses select(Model).where(...) rather than session.get() (a PK-only
    lookup with no room for an extra WHERE clause) specifically so this can
    be tenant-filtered — see _tenant_where. Returns the SAME "not found" 404
    regardless of whether the row doesn't exist at all or exists in a
    different tenant, matching the row-ownership feature's "404, never 403 —
    don't leak that another tenant's/user's record exists" precedent.
    """
    Model = _table(collection)
    async with get_session() as session:
        stmt = _tenant_where(Model, select(Model).where(Model.id == doc_id))
        row = (await session.execute(stmt.limit(1))).scalars().first()
        doc = _row_to_dict(row)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return doc


async def get_active_company() -> dict:
    """Active company profile used for PDF branding (name, address, logo).

    Returns an empty dict if none is configured; the PDF builders fall back to
    their default branding in that case. Reads the first row of the `company`
    table (single-company today).
    """
    Model = _table("company")
    async with get_session() as session:
        row = (await session.execute(select(Model).limit(1))).scalars().first()
        return _row_to_dict(row) or {}


async def resolve_party(party_id: Optional[str], party_type: str = "customer") -> dict:
    """Fetch a buyer/supplier fresh from the master DB and normalise it for PDFs.

    The PDF always reflects current master data (billing/shipping address, GSTIN,
    PAN, state, contact person, place of supply) rather than any stale copy on
    the document — so an invoice can't show an out-of-date address. Looks up
    `customers` first (or `vendors` when party_type is 'vendor'/'supplier'), then
    falls back to the other collection, so a party stored on either side resolves.
    Returns {} when the id is missing/unknown; callers then use whatever the
    document already carries, keeping old documents working.
    """
    if not party_id:
        return {}
    order = ("vendors", "customers") if party_type in ("vendor", "supplier") else ("customers", "vendors")
    row = None
    for coll in order:
        Model = _table(coll)
        async with get_session() as session:
            row = await session.get(Model, party_id)
        if row is not None:
            break
    d = _row_to_dict(row)
    if not d:
        return {}
    # Normalise into the shape core/pdf.py _party_box / meta strip consume.
    # billing/shipping/state/state_code/contact_person/place_of_supply may be
    # top-level columns or live in `extra` (auto-unpacked by _row_to_dict).
    return {
        "id": d.get("id"),
        "name": d.get("company") or d.get("name"),
        "billing_address": d.get("billing_address") or d.get("address"),
        "shipping_address": d.get("shipping_address") or d.get("billing_address") or d.get("address"),
        "gstin": d.get("gstin"),
        "pan": d.get("pan"),
        "state": d.get("state"),
        "state_code": d.get("state_code"),
        "contact_person": d.get("contact_person") or d.get("name"),
        "mobile": d.get("mobile") or d.get("phone"),
        "email": d.get("email"),
        "place_of_supply": d.get("place_of_supply") or d.get("state"),
        "payment_terms": d.get("payment_terms"),
    }


async def render_document_pdf(
    doc_type: str, doc_number: str, doc: dict, *,
    party_id: Optional[str] = None, party_type: str = "customer",
    company: Optional[dict] = None,
) -> bytes:
    """One entry point every core document PDF endpoint uses.

    Resolves the counterparty live from the master DB (so the PDF always shows
    current buyer/supplier details), loads the active company when not supplied,
    and delegates to the single reusable professional layout (build_document_pdf).
    `party_type` 'vendor'/'supplier' flips the boxes to purchase orientation.
    Falls back to whatever the document carries when the party can't be resolved,
    so old documents keep rendering.
    """
    from core.pdf import build_document_pdf  # lazy: avoid import cycle at load

    if company is None:
        company = await get_active_company()
    party = await resolve_party(party_id, party_type)
    party_role = "SUPPLIER" if party_type in ("vendor", "supplier") else "BUYER"
    return build_document_pdf(
        doc_type=doc_type, doc_number=doc_number, doc=doc,
        company=company, party=party, party_role=party_role,
    )


async def crud_update(
    collection: str, doc_id: str, updates: dict, user: Optional[dict] = None,
    label: str = "Record",
) -> dict:
    AuditLog = _AuditLog()
    Model = _table(collection)
    updates["updated_at"] = now_iso()

    if collection == "payslips":
        updates = _prepare_payslip_doc(updates)
    elif hasattr(Model, "lines") and not hasattr(Model, "items"):
        updates = _alias_items_to_lines(updates)

    overflow_col = _find_overflow_column(Model)
    updates = _pack_overflow_fields(updates, Model)

    async with get_session() as session:
        stmt = _tenant_where(Model, select(Model).where(Model.id == doc_id))
        row = (await session.execute(stmt.limit(1))).scalars().first()
        if row is None:
            raise HTTPException(status_code=404, detail=f"{label} not found")
        before = _row_to_dict(row)
        for k, v in updates.items():
            if hasattr(row, k):
                if k == overflow_col and getattr(row, k) and isinstance(v, dict):
                    # Merge into whatever the row already has, don't clobber
                    # fields that weren't part of this update.
                    existing = getattr(row, k) or {}
                    if isinstance(existing, dict):
                        setattr(row, k, {**existing, **v})
                    else:
                        setattr(row, k, v)
                else:
                    setattr(row, k, v)
        after = _row_to_dict(row)
        if user:
            session.add(AuditLog(**build_audit_entry(
                "update", collection, doc_id, user, before=before, after=after,
                tenant_id=getattr(row, "tenant_id", None),
            )))
    _bump_stock_gen_if_needed(collection)
    return await crud_get(collection, doc_id)


async def crud_delete(collection: str, doc_id: str, user: Optional[dict] = None) -> bool:
    AuditLog = _AuditLog()
    Model = _table(collection)
    async with get_session() as session:
        stmt = _tenant_where(Model, select(Model).where(Model.id == doc_id))
        row = (await session.execute(stmt.limit(1))).scalars().first()
        if row is None:
            return False
        before = _row_to_dict(row)
        await session.delete(row)
        if user:
            session.add(AuditLog(**build_audit_entry(
                "delete", collection, doc_id, user, before=before,
                tenant_id=getattr(row, "tenant_id", None),
            )))
    _bump_stock_gen_if_needed(collection)
    return True


async def crud_list(collection, q=None, search_fields=None, sort_field="created_at",
                    sort_dir=-1, filt=None, user: Optional[dict] = None,
                    owner_bypass: bool = False) -> list[dict]:
    """List documents with optional substring search and equality filters.

    `q` + `search_fields` build a case-insensitive OR-regex search; `filt`
    carries equality filters. Runs through the Mongo-compat data layer so the
    same call shape works as before the Postgres migration.

    `user`/`owner_bypass`: when `collection` is one of OWNED_COLLECTIONS and
    `user` is supplied, applies row-level ownership filtering (see
    apply_ownership_filter). Omitting `user` is a true no-op — every existing
    caller that doesn't pass it behaves exactly as before.
    """
    f = dict(filt or {})
    if user is not None:
        f = apply_ownership_filter(f, user, collection, bypass=owner_bypass)
    if q and search_fields:
        f["$or"] = [{x: {"$regex": q, "$options": "i"}} for x in search_fields]
    from ._mongo_compat import db  # lazy: avoids utils ↔ _mongo_compat cycle
    return await db[collection].find(f, {"_id": 0}).sort(sort_field, sort_dir).to_list(2000)


async def paginated_list(collection, *, page=None, limit=None, q=None,
                         search_fields=None, sort_field="created_at", sort_dir=-1,
                         filt=None, from_date=None, to_date=None, date_field="created_at",
                         user: Optional[dict] = None, owner_bypass: bool = False) -> Any:
    """Generic paginated, filterable, searchable list helper.

    Returns the standard envelope {total, page, items} when paging params
    are supplied, or a bare array when page/limit are None (backward compat).
    Page/limit are clamped: page>=1, 1<=limit<=200.

    `user`/`owner_bypass`: see crud_list — same row-ownership behavior,
    same no-op-when-omitted guarantee.
    """
    f = dict(filt or {})
    if user is not None:
        f = apply_ownership_filter(f, user, collection, bypass=owner_bypass)
    if q and search_fields:
        f["$or"] = [{x: {"$regex": q, "$options": "i"}} for x in search_fields]
    if from_date or to_date:
        rng: dict = {}
        if from_date:
            rng["$gte"] = from_date
        if to_date:
            rng["$lte"] = to_date
        f[date_field] = rng

    from ._mongo_compat import db  # lazy: avoids utils ↔ _mongo_compat cycle
    if page is not None or limit is not None:
        page = max(1, int(page or 1))
        limit = max(1, min(200, int(limit or 50)))
        total = await db[collection].count_documents(f)
        skip = (page - 1) * limit
        items = await db[collection].find(f, {"_id": 0}).sort(sort_field, sort_dir).skip(skip).limit(limit).to_list(limit)
        return {"total": total, "page": page, "items": items}
    return await db[collection].find(f, {"_id": 0}).sort(sort_field, sort_dir).to_list(2000)


# ── misc helpers ───────────────────────────────────────────────────────────────
_AUDIT_IGNORED_FIELDS = frozenset({"_id", "updated_at", "created_at"})


def calc_totals(items: list) -> dict:
    sub = 0.0
    gst = 0.0
    for it in items:
        line = float(it.get("quantity", 0)) * float(it.get("unit_price", 0))
        sub += line
        gst += line * float(it.get("gst_rate", 0)) / 100.0
    return {
        "subtotal": round(sub, 2),
        "gst_amount": round(gst, 2),
        "total": round(sub + gst, 2),
    }


def _diff_fields(old: Optional[dict], new: Optional[dict]) -> list[str]:
    old = old or {}
    new = new or {}
    keys = (set(old) | set(new)) - _AUDIT_IGNORED_FIELDS
    return sorted(k for k in keys if old.get(k) != new.get(k))
