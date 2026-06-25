"""All PostgreSQL table definitions for the ERP (SQLAlchemy ORM)."""
from sqlalchemy import Boolean, Column, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from .db import Base


def _pk(): return Column(Text, primary_key=True)
def _ts(n=True): return Column(Text, nullable=n)
def _bool(d=False): return Column(Boolean, nullable=False, default=d)
def _jsonb(): return Column(JSONB, nullable=True)
def _text(n=True): return Column(Text, nullable=n)
def _int(d=0): return Column(Integer, nullable=True, default=d)
def _num(): return Column(Numeric(18, 4), nullable=True)


# ── auth ───────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"
    id = _pk(); name = _text(); email = Column(Text, nullable=False, unique=True)
    phone = _text(); role = _text(); password_hash = _text(); tenant_id = _text()
    module_permissions = _jsonb(); permissions = _jsonb(); is_active = _bool(True)
    created_at = _ts(); updated_at = _ts()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = _pk(); jti = Column(Text, nullable=False, unique=True); user_id = _text()
    active = _bool(True); expires_at = _ts(); created_at = _ts()


# ── company / settings ─────────────────────────────────────────────────────────
class Company(Base):
    __tablename__ = "company"
    id = _pk(); tenant_id = _text(); name = _text(); gstin = _text(); pan = _text()
    address = _text(); city = _text(); state = _text(); pincode = _text(); country = _text()
    email = _text(); phone = _text(); logo_url = _text(); fiscal_year_start = _text()
    currency = _text(); extra = _jsonb(); created_at = _ts(); updated_at = _ts()


class VerificationSetting(Base):
    __tablename__ = "verification_settings"
    id = _pk(); tenant_id = _text(); key = _text(); value = _jsonb(); updated_at = _ts()


class EInvoiceSetting(Base):
    __tablename__ = "einvoice_settings"
    id = _pk(); tenant_id = _text(); enabled = _bool(); irn_api_url = _text()
    irn_api_key = _text(); extra = _jsonb(); updated_at = _ts()


class PurchaseSetting(Base):
    __tablename__ = "purchase_settings"
    id = _pk(); tenant_id = _text(); key = _text(); value = _jsonb(); updated_at = _ts()


class ThemeSetting(Base):
    __tablename__ = "theme_settings"
    id = _pk(); tenant_id = _text(); key = _text(); value = _jsonb(); updated_at = _ts()


class PONumberingSetting(Base):
    __tablename__ = "po_numbering_settings"
    id = _pk(); tenant_id = _text(); prefix = _text(); padding = _int(6)
    reset_on = _text(); start_at = _int(1); updated_at = _ts()


# ── CRM ────────────────────────────────────────────────────────────────────────
class Lead(Base):
    __tablename__ = "leads"
    id = _pk(); tenant_id = _text(); company_name = _text(); contact_person = _text()
    country = _text(); email = _text(); phone = _text(); source = _text()
    interested_in = _text(); estimated_value = _num(); status = _text(); notes = _text()
    next_follow_up = _ts(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class Customer(Base):
    __tablename__ = "customers"
    id = _pk(); tenant_id = _text(); name = _text(); company = _text(); email = _text()
    phone = _text(); country = _text(); address = _text(); gstin = _text(); pan = _text()
    credit_limit = _num(); payment_terms = _text(); price_list_id = _text()
    ledger_id = _text(); extra = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class Vendor(Base):
    __tablename__ = "vendors"
    id = _pk(); tenant_id = _text(); name = _text(); company = _text(); email = _text()
    phone = _text(); address = _text(); gstin = _text(); pan = _text()
    payment_terms = _text(); tds_applicable = _bool(); tds_section = _text()
    tds_rate = _num(); ledger_id = _text(); extra = _jsonb(); is_deleted = _bool()
    deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


# ── inventory ──────────────────────────────────────────────────────────────────
class Product(Base):
    __tablename__ = "products"
    id = _pk(); tenant_id = _text(); name = _text(); sku = _text(); category = _text()
    unit = _text(); cost_price = _num(); selling_price = _num(); quantity = _num()
    low_stock_threshold = _num(); warehouse_id = _text(); hsn_code = _text()
    gst_rate = _num(); image_url = _text(); image_path = _text(); description = _text()
    extra = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class ProductCategory(Base):
    __tablename__ = "product_categories"
    id = _pk(); tenant_id = _text(); name = _text(); parent_id = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class Warehouse(Base):
    __tablename__ = "warehouses"
    id = _pk(); tenant_id = _text(); name = _text(); location = _text(); manager = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class Godown(Base):
    __tablename__ = "godowns"
    id = _pk(); tenant_id = _text(); name = _text(); warehouse_id = _text()
    location = _text(); extra = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class StockItem(Base):
    __tablename__ = "stock_items"
    id = _pk(); tenant_id = _text(); name = _text(); sku = _text(); product_id = _text()
    uom = _text(); hsn_code = _text(); gst_rate = _num(); valuation_method = _text()
    track_batches = _bool(); track_serial = _bool(); is_deleted = _bool()
    deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class StockLedgerEntry(Base):
    __tablename__ = "stock_ledger_entries"
    id = _pk(); tenant_id = _text(); stock_item_id = _text(); godown_id = _text()
    batch_id = _text(); serial_no = _text(); doc_type = _text(); source_doc_id = _text()
    voucher_no = _text(); txn_date = _ts(); qty_in = _num(); qty_out = _num()
    rate = _num(); value_in = _num(); value_out = _num(); running_qty = _num()
    running_value = _num(); created_at = _ts()


class StockTransaction(Base):
    __tablename__ = "stock_transactions"
    id = _pk(); tenant_id = _text(); stock_item_id = _text(); godown_id = _text()
    batch_id = _text(); doc_type = _text(); source_doc_id = _text(); txn_date = _ts()
    qty = _num(); rate = _num(); value = _num(); direction = _text(); notes = _text()
    created_at = _ts()


class StockTransfer(Base):
    __tablename__ = "stock_transfers"
    id = _pk(); tenant_id = _text(); from_godown_id = _text(); to_godown_id = _text()
    items = _jsonb(); status = _text(); transfer_date = _ts(); notes = _text()
    created_at = _ts(); updated_at = _ts()


class Batch(Base):
    __tablename__ = "batches"
    id = _pk(); tenant_id = _text(); stock_item_id = _text(); batch_no = _text()
    mfg_date = _ts(); exp_date = _ts(); extra = _jsonb(); created_at = _ts()


class PhysicalVerification(Base):
    __tablename__ = "physical_verifications"
    id = _pk(); tenant_id = _text(); godown_id = _text(); verification_date = _ts()
    items = _jsonb(); status = _text(); notes = _text(); created_at = _ts(); updated_at = _ts()


class QCReport(Base):
    __tablename__ = "qc_reports"
    id = _pk(); tenant_id = _text(); source_doc_id = _text(); doc_type = _text()
    items = _jsonb(); result = _text(); notes = _text(); created_at = _ts(); updated_at = _ts()


# ── purchase ───────────────────────────────────────────────────────────────────
class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id = _pk(); tenant_id = _text(); vendor_id = _text(); po_number = _text()
    status = _text(); items = _jsonb(); total_amount = _num(); notes = _text()
    order_date = _ts(); created_at = _ts(); updated_at = _ts()


class PurchaseOrderV2(Base):
    __tablename__ = "purchase_orders_v2"
    id = _pk(); tenant_id = _text(); vendor_id = _text(); po_number = _text()
    status = _text(); lines = _jsonb(); gst_details = _jsonb(); total_amount = _num()
    notes = _text(); order_date = _ts(); created_at = _ts(); updated_at = _ts()


class GoodsReceiptNoteV2(Base):
    __tablename__ = "grn_v2"
    id = _pk(); tenant_id = _text(); po_id = _text(); vendor_id = _text()
    grn_number = _text(); status = _text(); lines = _jsonb(); gst_details = _jsonb()
    total_amount = _num(); notes = _text(); receipt_date = _ts()
    created_at = _ts(); updated_at = _ts()


class PurchaseBill(Base):
    __tablename__ = "purchase_bills"
    id = _pk(); tenant_id = _text(); vendor_id = _text(); grn_id = _text()
    bill_number = _text(); vendor_bill_no = _text(); status = _text(); lines = _jsonb()
    gst_details = _jsonb(); total_amount = _num(); notes = _text(); bill_date = _ts()
    created_at = _ts(); updated_at = _ts()


class PurchaseReturn(Base):
    __tablename__ = "purchase_returns"
    id = _pk(); tenant_id = _text(); vendor_id = _text(); bill_id = _text()
    return_number = _text(); status = _text(); lines = _jsonb(); gst_details = _jsonb()
    total_amount = _num(); notes = _text(); return_date = _ts()
    created_at = _ts(); updated_at = _ts()


class VendorBillSubmission(Base):
    __tablename__ = "vendor_bill_submissions"
    id = _pk(); tenant_id = _text(); vendor_id = _text(); bill_number = _text()
    amount = _num(); status = _text(); files = _jsonb(); notes = _text()
    submitted_at = _ts(); created_at = _ts(); updated_at = _ts()


class PONumberAudit(Base):
    __tablename__ = "po_number_audit"
    id = _pk(); tenant_id = _text(); po_id = _text(); old_number = _text()
    new_number = _text(); changed_by = _text(); changed_at = _ts(); reason = _text()


# ── sales ──────────────────────────────────────────────────────────────────────
class Quotation(Base):
    __tablename__ = "quotations"
    id = _pk(); tenant_id = _text(); customer_id = _text(); quotation_no = _text()
    status = _text(); lines = _jsonb(); gst_details = _jsonb(); total_amount = _num()
    notes = _text(); valid_until = _ts(); quotation_date = _ts()
    created_at = _ts(); updated_at = _ts()


class SalesOrder(Base):
    __tablename__ = "sales_orders"
    id = _pk(); tenant_id = _text(); customer_id = _text(); so_number = _text()
    status = _text(); lines = _jsonb(); gst_details = _jsonb(); total_amount = _num()
    notes = _text(); delivery_date = _ts(); order_date = _ts()
    created_at = _ts(); updated_at = _ts()


class Invoice(Base):
    __tablename__ = "invoices"
    id = _pk(); tenant_id = _text(); customer_id = _text(); so_id = _text()
    invoice_no = _text(); status = _text(); lines = _jsonb(); gst_details = _jsonb()
    total_amount = _num(); paid_amount = _num(); balance_due = _num(); notes = _text()
    invoice_date = _ts(); due_date = _ts(); created_at = _ts(); updated_at = _ts()


class CreditNote(Base):
    __tablename__ = "credit_notes"
    id = _pk(); tenant_id = _text(); customer_id = _text(); invoice_id = _text()
    cn_number = _text(); status = _text(); lines = _jsonb(); gst_details = _jsonb()
    total_amount = _num(); notes = _text(); cn_date = _ts()
    created_at = _ts(); updated_at = _ts()


class Dispatch(Base):
    __tablename__ = "dispatches"
    id = _pk(); tenant_id = _text(); invoice_id = _text(); so_id = _text()
    dispatch_no = _text(); status = _text(); lines = _jsonb(); notes = _text()
    dispatch_date = _ts(); created_at = _ts(); updated_at = _ts()


class ProformaInvoice(Base):
    __tablename__ = "proforma_invoices"
    id = _pk(); tenant_id = _text(); customer_id = _text(); pi_number = _text()
    status = _text(); lines = _jsonb(); gst_details = _jsonb(); total_amount = _num()
    notes = _text(); pi_date = _ts(); valid_until = _ts()
    created_at = _ts(); updated_at = _ts()


class PaymentLink(Base):
    __tablename__ = "payment_links"
    id = _pk(); tenant_id = _text(); invoice_id = _text(); amount = _num()
    status = _text(); url = _text(); expires_at = _ts()
    created_at = _ts(); updated_at = _ts()


# ── accounting ────────────────────────────────────────────────────────────────
class ChartOfAccount(Base):
    __tablename__ = "chart_of_accounts"
    id = _pk(); tenant_id = _text(); code = _text(); name = _text()
    group_id = _text(); account_type = _text(); parent_id = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class MasterLedger(Base):
    __tablename__ = "master_ledgers"
    id = _pk(); tenant_id = _text(); name = _text(); group_id = _text()
    opening_balance = _num(); balance_type = _text(); is_deleted = _bool()
    deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class MasterGroup(Base):
    __tablename__ = "master_groups"
    id = _pk(); tenant_id = _text(); name = _text(); parent_id = _text()
    nature = _text(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class CostCenter(Base):
    __tablename__ = "cost_centers"
    id = _pk(); tenant_id = _text(); name = _text(); parent_id = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class FiscalYear(Base):
    __tablename__ = "fiscal_years"
    id = _pk(); tenant_id = _text(); label = _text(); start_date = _ts()
    end_date = _ts(); is_current = _bool(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class Currency(Base):
    __tablename__ = "currencies"
    id = _pk(); tenant_id = _text(); code = _text(); name = _text()
    symbol = _text(); exchange_rate = _num(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class VoucherType(Base):
    __tablename__ = "voucher_types"
    id = _pk(); tenant_id = _text(); name = _text(); nature = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    id = _pk(); tenant_id = _text(); je_number = _text(); source_id = _text()
    source_type = _text(); je_date = _ts(); narration = _text(); lines = _jsonb()
    status = _text(); created_at = _ts(); updated_at = _ts()


class Voucher(Base):
    __tablename__ = "vouchers"
    id = _pk(); tenant_id = _text(); voucher_no = _text(); voucher_type = _text()
    voucher_date = _ts(); amount = _num(); narration = _text(); lines = _jsonb()
    status = _text(); created_at = _ts(); updated_at = _ts()


class VoucherV2(Base):
    __tablename__ = "vouchers_v2"
    id = _pk(); tenant_id = _text(); voucher_no = _text(); voucher_type = _text()
    parent_type = _text(); source_id = _text(); voucher_date = _ts(); amount = _num()
    narration = _text(); accounting_lines = _jsonb(); inventory_lines = _jsonb()
    gst_details = _jsonb(); status = _text(); posted = _bool(); posted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class VoucherCounter(Base):
    __tablename__ = "voucher_counters"
    id = _pk(); tenant_id = _text(); key = _text(); seq = _int(0)


class ExpenseEntry(Base):
    __tablename__ = "expense_entries"
    id = _pk(); tenant_id = _text(); expense_no = _text(); category_id = _text()
    amount = _num(); tax_amount = _num(); total_amount = _num(); status = _text()
    lines = _jsonb(); notes = _text(); expense_date = _ts(); approved_by = _text()
    approved_at = _ts(); created_at = _ts(); updated_at = _ts()


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    id = _pk(); tenant_id = _text(); name = _text(); ledger_id = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class Advance(Base):
    __tablename__ = "advances"
    id = _pk(); tenant_id = _text(); party_type = _text(); party_id = _text()
    amount = _num(); balance = _num(); status = _text(); notes = _text()
    advance_date = _ts(); created_at = _ts(); updated_at = _ts()


class InterestRule(Base):
    __tablename__ = "interest_rules"
    id = _pk(); tenant_id = _text(); name = _text(); rate = _num(); period = _text()
    apply_to = _text(); extra = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


# ── banking ────────────────────────────────────────────────────────────────────
class BankAccount(Base):
    __tablename__ = "bank_accounts"
    id = _pk(); tenant_id = _text(); name = _text(); bank_name = _text()
    account_number = _text(); ifsc = _text(); branch = _text(); account_type = _text()
    opening_balance = _num(); current_balance = _num(); ledger_id = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class BankEntry(Base):
    __tablename__ = "bank_entries"
    id = _pk(); tenant_id = _text(); bank_account_id = _text(); entry_type = _text()
    amount = _num(); narration = _text(); reference = _text(); entry_date = _ts()
    is_reconciled = _bool(); reconciled_at = _ts(); extra = _jsonb()
    created_at = _ts(); updated_at = _ts()


class BankStatement(Base):
    __tablename__ = "bank_statements"
    id = _pk(); tenant_id = _text(); bank_account_id = _text()
    statement_date = _ts(); file_url = _text(); status = _text(); lines_count = _int(0)
    extra = _jsonb(); created_at = _ts(); updated_at = _ts()


class BankStatementLine(Base):
    __tablename__ = "bank_statement_lines"
    id = _pk(); tenant_id = _text(); statement_id = _text(); bank_account_id = _text()
    txn_date = _ts(); description = _text(); debit = _num(); credit = _num()
    balance = _num(); is_matched = _bool(); matched_entry_id = _text()
    extra = _jsonb(); created_at = _ts()


class BankFeedImport(Base):
    __tablename__ = "bank_feed_imports"
    id = _pk(); tenant_id = _text(); bank_account_id = _text(); imported_at = _ts()
    lines_count = _int(0); source = _text(); extra = _jsonb(); created_at = _ts()


class PDC(Base):
    __tablename__ = "pdcs"
    id = _pk(); tenant_id = _text(); bank_account_id = _text(); party_type = _text()
    party_id = _text(); cheque_no = _text(); amount = _num(); due_date = _ts()
    status = _text(); notes = _text(); created_at = _ts(); updated_at = _ts()


class ChequeTransaction(Base):
    __tablename__ = "cheque_transactions"
    id = _pk(); tenant_id = _text(); bank_account_id = _text(); party_type = _text()
    party_id = _text(); cheque_no = _text(); amount = _num(); cheque_date = _ts()
    status = _text(); notes = _text(); created_at = _ts(); updated_at = _ts()


class ChequeFormat(Base):
    __tablename__ = "cheque_formats"
    id = _pk(); tenant_id = _text(); bank_name = _text(); layout = _jsonb()
    is_default = _bool(); created_at = _ts(); updated_at = _ts()


# ── HR ─────────────────────────────────────────────────────────────────────────
class Employee(Base):
    __tablename__ = "employees"
    id = _pk(); tenant_id = _text(); emp_code = _text(); name = _text()
    email = _text(); phone = _text(); department = _text(); designation = _text()
    date_of_joining = _ts(); date_of_leaving = _ts(); status = _text(); extra = _jsonb()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class Attendance(Base):
    __tablename__ = "attendance"
    id = _pk(); tenant_id = _text(); employee_id = _text(); attendance_date = _ts()
    status = _text(); in_time = _ts(); out_time = _ts(); shift_id = _text()
    notes = _text(); created_at = _ts(); updated_at = _ts()


class AttendanceLog(Base):
    __tablename__ = "attendance_logs"
    id = _pk(); tenant_id = _text(); employee_id = _text(); log_time = _ts()
    direction = _text(); device_id = _text(); created_at = _ts()


class Leave(Base):
    __tablename__ = "leaves"
    id = _pk(); tenant_id = _text(); employee_id = _text(); leave_type_id = _text()
    from_date = _ts(); to_date = _ts(); days = _num(); reason = _text()
    status = _text(); approved_by = _text(); approved_at = _ts()
    created_at = _ts(); updated_at = _ts()


class LeaveType(Base):
    __tablename__ = "leave_types"
    id = _pk(); tenant_id = _text(); name = _text(); annual_quota = _num()
    carry_forward = _bool(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class Holiday(Base):
    __tablename__ = "holidays"
    id = _pk(); tenant_id = _text(); name = _text(); holiday_date = _ts()
    optional = _bool(); created_at = _ts(); updated_at = _ts()


class Shift(Base):
    __tablename__ = "shifts"
    id = _pk(); tenant_id = _text(); name = _text(); start_time = _text()
    end_time = _text(); grace_minutes = _int(0); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


# ── payroll ────────────────────────────────────────────────────────────────────
class SalaryStructure(Base):
    __tablename__ = "salary_structures"
    id = _pk(); tenant_id = _text(); name = _text(); components = _jsonb()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class PayComponent(Base):
    __tablename__ = "pay_components"
    id = _pk(); tenant_id = _text(); name = _text(); component_type = _text()
    formula = _text(); is_taxable = _bool(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    id = _pk(); tenant_id = _text(); month = _text(); year = _int()
    status = _text(); total_gross = _num(); total_deductions = _num()
    total_net = _num(); notes = _text(); run_at = _ts()
    created_at = _ts(); updated_at = _ts()


class Payslip(Base):
    __tablename__ = "payslips"
    id = _pk(); tenant_id = _text(); payroll_run_id = _text(); employee_id = _text()
    month = _text(); year = _int(); gross = _num(); deductions = _num(); net = _num()
    components = _jsonb(); status = _text(); created_at = _ts(); updated_at = _ts()


class StatutoryParam(Base):
    __tablename__ = "statutory_params"
    id = _pk(); tenant_id = _text(); key = _text(); value = _jsonb()
    effective_from = _ts(); updated_at = _ts()


class FnFSettlement(Base):
    __tablename__ = "fnf_settlements"
    id = _pk(); tenant_id = _text(); employee_id = _text(); settlement_date = _ts()
    components = _jsonb(); total = _num(); status = _text(); notes = _text()
    created_at = _ts(); updated_at = _ts()


class TDSDeclaration(Base):
    __tablename__ = "tds_declarations"
    id = _pk(); tenant_id = _text(); employee_id = _text(); fy = _text()
    declarations = _jsonb(); submitted_at = _ts(); created_at = _ts(); updated_at = _ts()


# ── GST & taxation ────────────────────────────────────────────────────────────
class GSTRecord(Base):
    __tablename__ = "gst_records"
    id = _pk(); tenant_id = _text(); gstin = _text(); return_type = _text()
    period = _text(); data = _jsonb(); status = _text(); filed_at = _ts()
    created_at = _ts(); updated_at = _ts()


class GSTFilingCache(Base):
    __tablename__ = "gst_filing_cache"
    id = _pk(); tenant_id = _text(); gstin = _text(); period = _text()
    return_type = _text(); data = _jsonb(); cached_at = _ts()


class GSTINCache(Base):
    __tablename__ = "gstin_cache"
    id = _pk(); gstin = Column(Text, nullable=False, unique=True)
    data = _jsonb(); cached_at = _ts()


class GSTReconciliation(Base):
    __tablename__ = "gst_reconciliations"
    id = _pk(); tenant_id = _text(); period = _text(); status = _text()
    mismatches = _jsonb(); created_at = _ts(); updated_at = _ts()


class TDSEntry(Base):
    __tablename__ = "tds_entries"
    id = _pk(); tenant_id = _text(); source_doc_id = _text(); party_type = _text()
    party_id = _text(); section = _text(); rate = _num(); base_amount = _num()
    tds_amount = _num(); entry_date = _ts(); status = _text(); created_at = _ts()


class TCSEntry(Base):
    __tablename__ = "tcs_entries"
    id = _pk(); tenant_id = _text(); source_doc_id = _text(); customer_id = _text()
    section = _text(); rate = _num(); base_amount = _num(); tcs_amount = _num()
    entry_date = _ts(); status = _text(); created_at = _ts()


class EWayBill(Base):
    __tablename__ = "eway_bills"
    id = _pk(); tenant_id = _text(); source_doc_id = _text(); doc_type = _text()
    ewb_number = _text(); status = _text(); valid_until = _ts(); data = _jsonb()
    created_at = _ts(); updated_at = _ts()


# ── fixed assets ──────────────────────────────────────────────────────────────
class FixedAsset(Base):
    __tablename__ = "fixed_assets"
    id = _pk(); tenant_id = _text(); name = _text(); category_id = _text()
    purchase_date = _ts(); cost = _num(); salvage_value = _num()
    useful_life_years = _num(); depreciation_method = _text(); status = _text()
    extra = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class AssetCategory(Base):
    __tablename__ = "asset_categories"
    id = _pk(); tenant_id = _text(); name = _text(); depreciation_method = _text()
    rate = _num(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class AssetDepreciationRun(Base):
    __tablename__ = "asset_depreciation_runs"
    id = _pk(); tenant_id = _text(); run_date = _ts(); status = _text()
    entries = _jsonb(); created_at = _ts(); updated_at = _ts()


class AssetTransaction(Base):
    __tablename__ = "asset_transactions"
    id = _pk(); tenant_id = _text(); asset_id = _text(); txn_type = _text()
    amount = _num(); txn_date = _ts(); notes = _text(); created_at = _ts()


# ── projects ───────────────────────────────────────────────────────────────────
class Project(Base):
    __tablename__ = "projects"
    id = _pk(); tenant_id = _text(); name = _text(); customer_id = _text()
    status = _text(); budget = _num(); start_date = _ts(); end_date = _ts()
    notes = _text(); extra = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class ProjectCost(Base):
    __tablename__ = "project_costs"
    id = _pk(); tenant_id = _text(); project_id = _text(); cost_type = _text()
    amount = _num(); notes = _text(); cost_date = _ts(); created_at = _ts(); updated_at = _ts()


class Task(Base):
    __tablename__ = "tasks"
    id = _pk(); tenant_id = _text(); project_id = _text(); name = _text()
    assigned_to = _text(); status = _text(); priority = _text(); due_date = _ts()
    notes = _text(); created_at = _ts(); updated_at = _ts()


class TimesheetEntry(Base):
    __tablename__ = "timesheet_entries"
    id = _pk(); tenant_id = _text(); project_id = _text(); task_id = _text()
    employee_id = _text(); hours = _num(); notes = _text(); entry_date = _ts()
    created_at = _ts(); updated_at = _ts()


# ── manufacturing ─────────────────────────────────────────────────────────────
class BOM(Base):
    __tablename__ = "boms"
    id = _pk(); tenant_id = _text(); finished_product_id = _text()
    finished_product_name = _text(); sku = _text(); output_qty = _num(); uom = _text()
    version = _text(); status = _text(); valuation_method = _text()
    components = _jsonb(); co_products = _jsonb(); by_products = _jsonb()
    routing_steps = _jsonb(); items = _jsonb(); estimated_cost = _num(); notes = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class WorkOrder(Base):
    __tablename__ = "work_orders"
    id = _pk(); tenant_id = _text(); bom_id = _text(); wo_number = _text()
    status = _text(); planned_qty = _num(); produced_qty = _num()
    start_date = _ts(); end_date = _ts(); notes = _text()
    created_at = _ts(); updated_at = _ts()


class ProductionJournal(Base):
    __tablename__ = "production_journals"
    id = _pk(); tenant_id = _text(); work_order_id = _text(); journal_date = _ts()
    lines = _jsonb(); status = _text(); notes = _text(); created_at = _ts(); updated_at = _ts()


class WastageEntry(Base):
    __tablename__ = "wastage_entries"
    id = _pk(); tenant_id = _text(); work_order_id = _text(); entry_date = _ts()
    lines = _jsonb(); notes = _text(); created_at = _ts(); updated_at = _ts()


# ── job work ───────────────────────────────────────────────────────────────────
class JobWorkChallan(Base):
    __tablename__ = "job_work_challans"
    id = _pk(); tenant_id = _text(); challan_no = _text(); vendor_id = _text()
    status = _text(); lines = _jsonb(); dispatch_date = _ts()
    expected_return_date = _ts(); notes = _text(); created_at = _ts(); updated_at = _ts()


class JobWorkReceipt(Base):
    __tablename__ = "job_work_receipts"
    id = _pk(); tenant_id = _text(); receipt_no = _text(); challan_id = _text()
    status = _text(); lines = _jsonb(); receipt_date = _ts(); notes = _text()
    created_at = _ts(); updated_at = _ts()


class RateTable(Base):
    __tablename__ = "rate_tables"
    id = _pk(); tenant_id = _text(); key = _text(); value = _jsonb()
    description = _text(); effective_from = _ts(); effective_to = _ts()
    created_at = _ts(); updated_at = _ts()


# ── approvals ─────────────────────────────────────────────────────────────────
class ApprovalPolicy(Base):
    __tablename__ = "approval_policies"
    id = _pk(); tenant_id = _text(); name = _text(); doc_type = _text()
    conditions = _jsonb(); steps = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    id = _pk(); tenant_id = _text(); policy_id = _text(); doc_type = _text()
    source_id = _text(); status = _text(); current_step = _int(0); history = _jsonb()
    created_at = _ts(); updated_at = _ts()


class ApprovalStep(Base):
    __tablename__ = "approval_steps"
    id = _pk(); tenant_id = _text(); request_id = _text(); step_index = _int(0)
    approver_id = _text(); status = _text(); notes = _text(); actioned_at = _ts()
    created_at = _ts(); updated_at = _ts()


# ── POS ────────────────────────────────────────────────────────────────────────
class POSSale(Base):
    __tablename__ = "pos_sales"
    id = _pk(); tenant_id = _text(); session_id = _text(); sale_no = _text()
    lines = _jsonb(); gst_details = _jsonb(); total_amount = _num()
    paid_amount = _num(); payment_mode = _text(); status = _text(); sale_date = _ts()
    created_at = _ts(); updated_at = _ts()


class POSSession(Base):
    __tablename__ = "pos_sessions"
    id = _pk(); tenant_id = _text(); opened_by = _text(); opened_at = _ts()
    closed_at = _ts(); opening_cash = _num(); closing_cash = _num(); status = _text()
    notes = _text(); created_at = _ts(); updated_at = _ts()


class PriceList(Base):
    __tablename__ = "price_lists"
    id = _pk(); tenant_id = _text(); name = _text(); currency = _text()
    lines = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class DiscountScheme(Base):
    __tablename__ = "discount_schemes"
    id = _pk(); tenant_id = _text(); name = _text(); conditions = _jsonb()
    discount_pct = _num(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


# ── integrations / portal ─────────────────────────────────────────────────────
class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"
    id = _pk(); tenant_id = _text(); url = _text(); events = _jsonb(); secret = _text()
    is_active = _bool(True); created_at = _ts(); updated_at = _ts()


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id = _pk(); tenant_id = _text(); subscription_id = _text(); event = _text()
    payload = _jsonb(); status = _text(); response_code = _int(); delivered_at = _ts()
    created_at = _ts()


class PortalUser(Base):
    __tablename__ = "portal_users"
    id = _pk(); tenant_id = _text(); party_type = _text(); party_id = _text()
    email = Column(Text, nullable=False, unique=True); password_hash = _text()
    is_active = _bool(True); created_at = _ts(); updated_at = _ts()


class APIKey(Base):
    __tablename__ = "api_keys"
    id = _pk(); tenant_id = _text(); name = _text(); key_hash = _text()
    scopes = _jsonb(); is_active = _bool(True); expires_at = _ts()
    created_at = _ts(); updated_at = _ts()


# ── branches ───────────────────────────────────────────────────────────────────
class Branch(Base):
    __tablename__ = "branches"
    id = _pk(); tenant_id = _text(); name = _text(); address = _text(); gstin = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class InterBranchTransfer(Base):
    __tablename__ = "inter_branch_transfers"
    id = _pk(); tenant_id = _text(); from_branch_id = _text(); to_branch_id = _text()
    transfer_no = _text(); status = _text(); lines = _jsonb(); transfer_date = _ts()
    notes = _text(); created_at = _ts(); updated_at = _ts()


class Budget(Base):
    __tablename__ = "budgets"
    id = _pk(); tenant_id = _text(); name = _text(); fy = _text()
    lines = _jsonb(); status = _text(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


# ── audit / system ────────────────────────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = _pk(); tenant_id = _text(); action = _text(); collection = _text()
    doc_id = _text(); user_id = _text(); user_email = _text()
    before = _jsonb(); after = _jsonb(); ip = _text(); user_agent = _text()
    created_at = _ts()


class Counter(Base):
    __tablename__ = "counters"
    key = Column(Text, primary_key=True)
    seq = Column(Integer, nullable=False, default=0)


# ── reports ────────────────────────────────────────────────────────────────────
class ReportSummary(Base):
    __tablename__ = "report_summaries"
    id = _pk(); tenant_id = _text(); report_type = _text(); period = _text()
    data = _jsonb(); generated_at = _ts(); created_at = _ts()


class ReportSavedView(Base):
    __tablename__ = "report_saved_views"
    id = _pk(); tenant_id = _text(); name = _text(); report_type = _text()
    filters = _jsonb(); created_by = _text(); created_at = _ts(); updated_at = _ts()


# ── storage / files ───────────────────────────────────────────────────────────
class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id = _pk(); tenant_id = _text(); filename = _text(); original_name = _text()
    mime_type = _text(); size = _int(0); url = _text(); path = _text()
    uploaded_by = _text(); created_at = _ts()


class OCRDocument(Base):
    __tablename__ = "ocr_documents"
    id = _pk(); tenant_id = _text(); file_id = _text(); status = _text()
    extracted_data = _jsonb(); ocr_provider = _text(); created_at = _ts(); updated_at = _ts()


class VerificationLog(Base):
    __tablename__ = "verification_logs"
    id = _pk(); tenant_id = _text(); verification_type = _text(); identifier = _text()
    result = _jsonb(); status = _text(); provider = _text(); created_at = _ts()


# ── AI / chat ──────────────────────────────────────────────────────────────────
class AIChatHistory(Base):
    __tablename__ = "ai_chat_history"
    id = _pk(); tenant_id = _text(); user_id = _text(); role = _text()
    content = _text(); created_at = _ts()


class AIConversation(Base):
    __tablename__ = "ai_conversations"
    id = _pk(); tenant_id = _text(); user_id = _text(); title = _text()
    messages = _jsonb(); created_at = _ts(); updated_at = _ts()
