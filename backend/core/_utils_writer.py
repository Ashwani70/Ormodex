"""Temporary script — run once to write utils.py, then delete."""
import os

path = os.path.join(os.path.dirname(__file__), "utils.py")

CONTENT = '''\
from typing import Optional
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import get_session
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
)


def new_id() -> str:
    return uuid.uuid4().hex


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── collection → model map ─────────────────────────────────────────────────────
_COLLECTION_MAP: dict = {
    "users": User,
    "refresh_tokens": RefreshToken,
    "company": Company,
    "leads": Lead,
    "customers": Customer,
    "vendors": Vendor,
    "suppliers": Vendor,
    "products": Product,
    "product_categories": ProductCategory,
    "warehouses": Warehouse,
    "godowns": Godown,
    "stock_items": StockItem,
    "stock_ledger_entries": StockLedgerEntry,
    "stock_transactions": StockTransaction,
    "stock_transfers": StockTransfer,
    "batches": Batch,
    "physical_verifications": PhysicalVerification,
    "qc_reports": QCReport,
    "purchase_orders": PurchaseOrder,
    "purchase_orders_v2": PurchaseOrderV2,
    "grn_v2": GoodsReceiptNoteV2,
    "purchase_bills": PurchaseBill,
    "purchase_returns": PurchaseReturn,
    "vendor_bill_submissions": VendorBillSubmission,
    "po_number_audit": PONumberAudit,
    "quotations": Quotation,
    "sales_orders": SalesOrder,
    "invoices": Invoice,
    "credit_notes": CreditNote,
    "dispatches": Dispatch,
    "proforma_invoices": ProformaInvoice,
    "payment_links": PaymentLink,
    "chart_of_accounts": ChartOfAccount,
    "master_ledgers": MasterLedger,
    "master_groups": MasterGroup,
    "cost_centers": CostCenter,
    "fiscal_years": FiscalYear,
    "currencies": Currency,
    "voucher_types": VoucherType,
    "journal_entries": JournalEntry,
    "vouchers": Voucher,
    "vouchers_v2": VoucherV2,
    "voucher_counters": VoucherCounter,
    "expense_entries": ExpenseEntry,
    "expense_categories": ExpenseCategory,
    "advances": Advance,
    "interest_rules": InterestRule,
    "bank_accounts": BankAccount,
    "bank_entries": BankEntry,
    "bank_statements": BankStatement,
    "bank_statement_lines": BankStatementLine,
    "bank_feed_imports": BankFeedImport,
    "pdcs": PDC,
    "cheque_transactions": ChequeTransaction,
    "cheque_formats": ChequeFormat,
    "employees": Employee,
    "attendance": Attendance,
    "attendance_logs": AttendanceLog,
    "leaves": Leave,
    "leave_types": LeaveType,
    "holidays": Holiday,
    "shifts": Shift,
    "salary_structures": SalaryStructure,
    "pay_components": PayComponent,
    "payroll_runs": PayrollRun,
    "payslips": Payslip,
    "statutory_params": StatutoryParam,
    "fnf_settlements": FnFSettlement,
    "tds_declarations": TDSDeclaration,
    "gst_records": GSTRecord,
    "gst_filing_cache": GSTFilingCache,
    "gstin_cache": GSTINCache,
    "gst_reconciliations": GSTReconciliation,
    "tds_entries": TDSEntry,
    "tcs_entries": TCSEntry,
    "eway_bills": EWayBill,
    "fixed_assets": FixedAsset,
    "asset_categories": AssetCategory,
    "asset_depreciation_runs": AssetDepreciationRun,
    "asset_transactions": AssetTransaction,
    "projects": Project,
    "project_costs": ProjectCost,
    "tasks": Task,
    "timesheet_entries": TimesheetEntry,
    "boms": BOM,
    "work_orders": WorkOrder,
    "production_journals": ProductionJournal,
    "wastage_entries": WastageEntry,
    "job_work_challans": JobWorkChallan,
    "job_work_receipts": JobWorkReceipt,
    "rate_tables": RateTable,
    "approval_policies": ApprovalPolicy,
    "approval_requests": ApprovalRequest,
    "approval_steps": ApprovalStep,
    "pos_sales": POSSale,
    "pos_sessions": POSSession,
    "price_lists": PriceList,
    "discount_schemes": DiscountScheme,
    "webhook_subscriptions": WebhookSubscription,
    "webhook_deliveries": WebhookDelivery,
    "portal_users": PortalUser,
    "api_keys": APIKey,
    "branches": Branch,
    "inter_branch_transfers": InterBranchTransfer,
    "budgets": Budget,
    "report_summaries": ReportSummary,
    "report_saved_views": ReportSavedView,
    "uploaded_files": UploadedFile,
    "ocr_documents": OCRDocument,
    "verification_logs": VerificationLog,
    "ai_chat_history": AIChatHistory,
    "ai_conversations": AIConversation,
    "verification_settings": VerificationSetting,
    "einvoice_settings": EInvoiceSetting,
    "purchase_settings": PurchaseSetting,
    "theme_settings": ThemeSetting,
    "po_numbering_settings": PONumberingSetting,
    "counters": Counter,
    "audit_logs": AuditLog,
}


def _table(collection: str):
    model = _COLLECTION_MAP.get(collection)
    if model is None:
        raise ValueError(f"No model mapped for collection: {collection!r}")
    return model


def _row_to_dict(row) -> dict:
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
    row = AuditLog(**entry)
    if session is not None:
        session.add(row)
    else:
        async with get_session() as s:
            s.add(row)


async def _write_with_audit(do_write, audit_entry: dict) -> dict:
    async with get_session() as session:
        result = await do_write(session)
        session.add(AuditLog(**audit_entry))
        return result


# ── generic CRUD ───────────────────────────────────────────────────────────────
async def crud_create(collection: str, data: dict, user: Optional[dict] = None) -> dict:
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
) -> list[dict]:
    Model = _table(collection)
    async with get_session() as session:
        stmt = select(Model)
        if filters:
            conditions = []
            for k, v in filters.items():
                if hasattr(Model, k):
                    conditions.append(getattr(Model, k) == v)
            if conditions:
                stmt = stmt.where(and_(*conditions))
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
) -> dict:
    Model = _table(collection)
    skip = (page - 1) * page_size
    async with get_session() as session:
        stmt = select(Model)
        count_stmt = select(func.count()).select_from(Model)
        if filters:
            conditions = []
            for k, v in filters.items():
                if hasattr(Model, k):
                    conditions.append(getattr(Model, k) == v)
            if conditions:
                stmt = stmt.where(and_(*conditions))
                count_stmt = count_stmt.where(and_(*conditions))
        total = (await session.execute(count_stmt)).scalar_one()
        col = getattr(Model, sort_by, None)
        if col is not None:
            stmt = stmt.order_by(col.desc() if sort_dir == "desc" else col.asc())
        stmt = stmt.offset(skip).limit(page_size)
        rows = (await session.execute(stmt)).scalars().all()
    return {
        "items": [_row_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }
'''

with open(path, "w", encoding="utf-8") as f:
    f.write(CONTENT)

print(f"Written {len(CONTENT)} chars")
