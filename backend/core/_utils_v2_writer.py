"""Temporary script — write utils.py v2 with lazy schema imports to break circular deps."""
import os

path = os.path.join(os.path.dirname(__file__), "utils.py")

CONTENT = '''\
from typing import Optional
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import get_session


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
        "company": _s.Company,
        "companies": _s.Company,
        "leads": _s.Lead,
        "customers": _s.Customer,
        "vendors": _s.Vendor,
        "suppliers": _s.Vendor,
        "products": _s.Product,
        "product_categories": _s.ProductCategory,
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
        "job_work_receipts": _s.JobWorkReceipt,
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
        "counters": _s.Counter,
        "audit_logs": _s.AuditLog,
    }


def _table(collection: str):
    global _COLLECTION_MAP
    if _COLLECTION_MAP is None:
        _COLLECTION_MAP = _build_collection_map()
    model = _COLLECTION_MAP.get(collection)
    if model is None:
        raise ValueError(f"No model mapped for collection: {collection!r}")
    return model


def _row_to_dict(row) -> Optional[dict]:
    """Convert a SQLAlchemy ORM row to a plain dict."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    d = {}
    for col in row.__table__.columns:
        d[col.name] = getattr(row, col.name)
    return d


# ── atomic sequence counter ────────────────────────────────────────────────────
async def next_doc_number(prefix: str, collection: str) -> str:
    Counter = _Counter()
    key = f"{collection}:{prefix}"
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
        "before": before,
        "after": after,
        "ip": ip,
        "user_agent": user_agent,
        "created_at": now_iso(),
    }


async def log_audit(entry: dict, session=None) -> None:
    AuditLog = _AuditLog()
    row = AuditLog(**entry)
    if session is not None:
        session.add(row)
    else:
        async with get_session() as s:
            s.add(row)


# ── generic CRUD ───────────────────────────────────────────────────────────────
async def crud_create(collection: str, data: dict, user: Optional[dict] = None) -> dict:
    AuditLog = _AuditLog()
    Model = _table(collection)
    if "id" not in data or not data["id"]:
        data["id"] = new_id()
    now = now_iso()
    data.setdefault("created_at", now)
    data.setdefault("updated_at", now)

    async with get_session() as session:
        row = Model(**{k: v for k, v in data.items() if hasattr(Model, k)})
        session.add(row)
        await session.flush()
        if user:
            session.add(AuditLog(**build_audit_entry(
                "create", collection, data["id"], user, after=data,
                tenant_id=data.get("tenant_id"),
            )))
    return data


async def crud_get(collection: str, doc_id: str) -> Optional[dict]:
    Model = _table(collection)
    async with get_session() as session:
        row = await session.get(Model, doc_id)
        return _row_to_dict(row)


async def crud_update(
    collection: str, doc_id: str, updates: dict, user: Optional[dict] = None
) -> Optional[dict]:
    AuditLog = _AuditLog()
    Model = _table(collection)
    updates["updated_at"] = now_iso()
    async with get_session() as session:
        row = await session.get(Model, doc_id)
        if row is None:
            return None
        before = _row_to_dict(row)
        for k, v in updates.items():
            if hasattr(row, k):
                setattr(row, k, v)
        if user:
            session.add(AuditLog(**build_audit_entry(
                "update", collection, doc_id, user, before=before, after=updates,
                tenant_id=getattr(row, "tenant_id", None),
            )))
    return await crud_get(collection, doc_id)


async def crud_delete(collection: str, doc_id: str, user: Optional[dict] = None) -> bool:
    AuditLog = _AuditLog()
    Model = _table(collection)
    async with get_session() as session:
        row = await session.get(Model, doc_id)
        if row is None:
            return False
        before = _row_to_dict(row)
        await session.delete(row)
        if user:
            session.add(AuditLog(**build_audit_entry(
                "delete", collection, doc_id, user, before=before,
                tenant_id=getattr(row, "tenant_id", None),
            )))
    return True


async def crud_list(
    collection: str,
    filters: Optional[dict] = None,
    limit: int = 100,
    skip: int = 0,
    q: Optional[dict] = None,
    search_fields=None,
    sort_field: str = "created_at",
    sort_dir: int = -1,
    filt: Optional[dict] = None,
) -> list[dict]:
    Model = _table(collection)
    effective_filters = filters or q or filt or {}
    async with get_session() as session:
        stmt = select(Model)
        if effective_filters:
            conditions = []
            for k, v in effective_filters.items():
                if hasattr(Model, k):
                    conditions.append(getattr(Model, k) == v)
            if conditions:
                stmt = stmt.where(and_(*conditions))
        col = getattr(Model, sort_field, None)
        if col is not None:
            stmt = stmt.order_by(col.desc() if sort_dir == -1 else col.asc())
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return [_row_to_dict(r) for r in result.scalars().all()]


async def paginated_list(
    collection: str,
    filters: Optional[dict] = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    limit: Optional[int] = None,
    q: Optional[dict] = None,
) -> dict:
    Model = _table(collection)
    effective_filters = filters or q or {}
    effective_page_size = max(1, limit or page_size or 1)
    page = max(1, page or 1)
    skip = (page - 1) * effective_page_size
    async with get_session() as session:
        stmt = select(Model)
        count_stmt = select(func.count()).select_from(Model)
        if effective_filters:
            conditions = []
            for k, v in effective_filters.items():
                if hasattr(Model, k):
                    conditions.append(getattr(Model, k) == v)
            if conditions:
                stmt = stmt.where(and_(*conditions))
                count_stmt = count_stmt.where(and_(*conditions))
        total = (await session.execute(count_stmt)).scalar_one()
        col = getattr(Model, sort_by, None)
        if col is not None:
            stmt = stmt.order_by(col.desc() if sort_dir == "desc" else col.asc())
        stmt = stmt.offset(skip).limit(effective_page_size)
        rows = (await session.execute(stmt)).scalars().all()
    return {
        "items": [_row_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": effective_page_size,
        "pages": (total + effective_page_size - 1) // effective_page_size,
    }


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
'''

if __name__ == "__main__":
    with open(path, "w", encoding="utf-8") as f:
        f.write(CONTENT)
    print(f"Written utils.py v2: {len(CONTENT)} chars")
