"""All PostgreSQL table definitions for the ERP (SQLAlchemy ORM)."""
from typing import Any

from sqlalchemy import Boolean, Column, Index, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from .db import Base


# These helpers return Column objects but are annotated -> Any so the type
# checker treats instance attribute access (e.g. row.active) as the runtime
# value type, not Column[T]. (The schema uses the classic Column style rather
# than Mapped[] annotations.) Purely a typing hint — no runtime effect.
def _pk() -> Any: return Column(Text, primary_key=True)
def _ts(n=True) -> Any: return Column(Text, nullable=n)
def _bool(d=False) -> Any: return Column(Boolean, nullable=False, default=d)
def _jsonb() -> Any: return Column(JSONB, nullable=True)
def _text(n=True) -> Any: return Column(Text, nullable=n)
def _int(d=0) -> Any: return Column(Integer, nullable=True, default=d)
def _num() -> Any: return Column(Numeric(18, 4), nullable=True)


# ── auth ───────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_tenant_id", "tenant_id"),
        Index("ix_users_email", "email"),
    )
    id = _pk(); name = _text(); email = Column(Text, nullable=False, unique=True)
    phone = _text(); role = _text(); password_hash = _text(); tenant_id = _text()
    module_permissions = _jsonb(); permissions = _jsonb(); is_active = _bool(True)
    created_at = _ts(); updated_at = _ts()
    username = _text()  # drift: written by routers, was dropped by migration
    # MFA (TOTP) — see core/mfa.py, routers/mfa.py
    mfa_enabled = _bool(False); mfa_secret = _text(); mfa_pending_secret = _text()
    mfa_recovery_hashes = _jsonb()
    # Password policy / lockout
    password_change_required = _bool(False)
    password_history = _jsonb()  # last 5 password hashes, FIFO
    last_password_change = _text()
    failed_login_count = _int(0)
    locked_until = _text()  # ISO ts; NULL = not auto-locked
    is_locked = _bool(False)  # admin-initiated hard lock
    force_change_reason = _text()  # "policy" | "admin_reset" | NULL
    last_login_at = _text(); last_login_ip = _text()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_jti", "jti"),
        Index("ix_refresh_tokens_user_id", "user_id"),
    )
    id = _pk(); jti = Column(Text, nullable=False, unique=True); user_id = _text()
    active = _bool(True); expires_at = _ts(); created_at = _ts()


class UserDevice(Base):
    __tablename__ = "user_devices"
    __table_args__ = (
        Index("ix_user_devices_user_id", "user_id"),
        Index("ix_user_devices_jti", "refresh_jti"),
    )
    id = _pk(); user_id = _text(n=False); refresh_jti = _text()
    device_name = _text(); browser = _text(); os = _text()
    ip = _text(); user_agent = _text(); login_at = _text(); last_active_at = _text()
    revoked = _bool(False); revoked_at = _text(); created_at = _text()


class LoginHistory(Base):
    __tablename__ = "login_history"
    __table_args__ = (
        Index("ix_login_history_user_id", "user_id"),
        Index("ix_login_history_created", "created_at"),
    )
    id = _pk(); user_id = _text(); email_attempted = _text()
    ip = _text(); user_agent = _text(); device_name = _text(); browser = _text(); os = _text()
    success = Column(Boolean, nullable=False)
    failure_reason = _text()
    logged_in_at = _text(); logged_out_at = _text(); created_at = _text()


# ── company / settings ─────────────────────────────────────────────────────────
class Company(Base):
    __tablename__ = "company"
    __table_args__ = (Index("ix_company_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); gstin = _text(); pan = _text()
    address = _text(); city = _text(); state = _text(); pincode = _text(); country = _text()
    email = _text(); phone = _text(); logo_url = _text(); fiscal_year_start = _text()
    currency = _text()
    # Professional PDF-header identity (migration 014). All nullable.
    website = _text(); cin = _text(); iec = _text(); state_code = _text()
    bank_name = _text(); bank_account_no = _text(); bank_ifsc = _text(); bank_branch = _text()
    declaration = _text(); seal_url = _text()
    extra = _jsonb(); created_at = _ts(); updated_at = _ts()


class VerificationSetting(Base):
    __tablename__ = "verification_settings"
    __table_args__ = (Index("ix_verification_settings_tenant_key", "tenant_id", "key"),)
    id = _pk(); tenant_id = _text(); key = _text(); value = _jsonb(); updated_at = _ts()


class EInvoiceSetting(Base):
    __tablename__ = "einvoice_settings"
    __table_args__ = (Index("ix_einvoice_settings_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); enabled = _bool(); irn_api_url = _text()
    irn_api_key = _text(); extra = _jsonb(); updated_at = _ts()


class PurchaseSetting(Base):
    __tablename__ = "purchase_settings"
    __table_args__ = (Index("ix_purchase_settings_tenant_key", "tenant_id", "key"),)
    id = _pk(); tenant_id = _text(); key = _text(); value = _jsonb(); updated_at = _ts()


class ThemeSetting(Base):
    __tablename__ = "theme_settings"
    __table_args__ = (Index("ix_theme_settings_tenant_key", "tenant_id", "key"),)
    id = _pk(); tenant_id = _text(); key = _text(); value = _jsonb(); updated_at = _ts()


class PONumberingSetting(Base):
    __tablename__ = "po_numbering_settings"
    __table_args__ = (Index("ix_po_numbering_settings_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); prefix = _text(); padding = _int(6)
    reset_on = _text(); start_at = _int(1); updated_at = _ts()
    # drift: the numbering engine (core/po_numbering.py) reads/writes these.
    # The original Postgres model only kept prefix/padding/start_at, so mode,
    # separator, FY/branch and sequence settings were silently dropped on save.
    mode = _text(); fy_format = _text(); branch_code = _text(); separator = _text()
    start_sequence = _int(1); sequence_length = _int(5); updated_by = _text()


# ── CRM ────────────────────────────────────────────────────────────────────────
class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_tenant_id", "tenant_id"),
        Index("ix_leads_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); company_name = _text(); contact_person = _text()
    country = _text(); email = _text(); phone = _text(); source = _text()
    interested_in = _text(); estimated_value = _num(); status = _text(); notes = _text()
    next_follow_up = _ts(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_tenant_id", "tenant_id"),
        Index("ix_customers_tenant_gstin", "tenant_id", "gstin"),
        Index("ix_customers_tenant_name", "tenant_id", "name"),
    )
    id = _pk(); tenant_id = _text(); name = _text(); company = _text(); email = _text()
    phone = _text(); country = _text(); address = _text(); gstin = _text(); pan = _text()
    credit_limit = _num(); payment_terms = _text(); price_list_id = _text()
    ledger_id = _text(); extra = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (
        Index("ix_vendors_tenant_id", "tenant_id"),
        Index("ix_vendors_tenant_gstin", "tenant_id", "gstin"),
        Index("ix_vendors_tenant_name", "tenant_id", "name"),
    )
    id = _pk(); tenant_id = _text(); name = _text(); company = _text(); email = _text()
    phone = _text(); address = _text(); gstin = _text(); pan = _text()
    payment_terms = _text(); tds_applicable = _bool(); tds_section = _text()
    tds_rate = _num(); ledger_id = _text(); extra = _jsonb(); is_deleted = _bool()
    deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


# ── inventory ──────────────────────────────────────────────────────────────────
class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_tenant_id", "tenant_id"),
        Index("ix_products_tenant_sku", "tenant_id", "sku"),
        Index("ix_products_tenant_category", "tenant_id", "category"),
        Index("ix_products_tenant_name", "tenant_id", "name"),
    )
    id = _pk(); tenant_id = _text(); name = _text(); sku = _text(); category = _text()
    category_id = _text()
    unit = _text(); cost_price = _num(); selling_price = _num(); quantity = _num()
    low_stock_threshold = _num(); warehouse_id = _text(); hsn_code = _text()
    gst_rate = _num(); image_url = _text(); image_path = _text(); description = _text()
    extra = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class ProductCategory(Base):
    __tablename__ = "product_categories"
    __table_args__ = (Index("ix_product_categories_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); parent_id = _text()
    code = _text(); description = _text(); status = _text(); display_order = _int()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (Index("ix_warehouses_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); location = _text(); manager = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class Godown(Base):
    __tablename__ = "godowns"
    __table_args__ = (
        Index("ix_godowns_tenant_id", "tenant_id"),
        Index("ix_godowns_tenant_warehouse", "tenant_id", "warehouse_id"),
    )
    id = _pk(); tenant_id = _text(); name = _text(); warehouse_id = _text()
    location = _text(); extra = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class StockItem(Base):
    __tablename__ = "stock_items"
    __table_args__ = (
        Index("ix_stock_items_tenant_id", "tenant_id"),
        Index("ix_stock_items_tenant_sku", "tenant_id", "sku"),
        Index("ix_stock_items_tenant_product", "tenant_id", "product_id"),
    )
    id = _pk(); tenant_id = _text(); name = _text(); sku = _text(); product_id = _text()
    uom = _text(); hsn_code = _text(); gst_rate = _num(); valuation_method = _text()
    # Per-unit standard cost, used only when valuation_method == STANDARD_COST.
    # Nullable: falls back to actual inward rate when unset. Existing rows may
    # instead carry it in `extra.standard_cost` (read-compatible).
    standard_cost = _num()
    track_batches = _bool(); track_serial = _bool(); is_deleted = _bool()
    deleted_at = _ts(); created_at = _ts(); updated_at = _ts(); extra = _jsonb()


class StockLedgerEntry(Base):
    __tablename__ = "stock_ledger_entries"
    __table_args__ = (
        Index("ix_stock_ledger_tenant_id", "tenant_id"),
        Index("ix_stock_ledger_tenant_item", "tenant_id", "stock_item_id"),
        Index("ix_stock_ledger_tenant_godown", "tenant_id", "godown_id"),
        Index("ix_stock_ledger_tenant_doc", "tenant_id", "source_doc_type", "source_doc_id"),
    )
    id = _pk(); tenant_id = _text(); stock_item_id = _text(); godown_id = _text()
    # Fields written by stock_ledger.post_entry (the authoritative writer)
    qty = _num(); rate = _num(); value = _num()
    movement_type = _text(); source_doc_type = _text(); source_doc_id = _text()
    entry_date = _text(); batch_id = _text(); serial_id = _text()
    created_at = _ts()
    # Legacy columns kept for backward compat (existing rows / old routers)
    serial_no = _text(); doc_type = _text(); voucher_no = _text()
    qty_in = _num(); qty_out = _num(); value_in = _num(); value_out = _num()
    running_qty = _num(); running_value = _num(); txn_date = _ts()
    extra = _jsonb()
    # Stock ledger unification (2026-07): denormalized so this row is a
    # complete superset of stock_transactions on its own, without needing a
    # stock_items join — product_id/name (this table is keyed by
    # stock_item_id, not product_id), the posting user, and a free-text
    # reason. See alembic/versions/022_stock_ledger_unify_columns.py.
    product_id = _text(); product_name = _text()
    user_id = _text(); user_name = _text(); reason = _text()


class StockTransaction(Base):
    __tablename__ = "stock_transactions"
    __table_args__ = (
        Index("ix_stock_txn_tenant_id", "tenant_id"),
        Index("ix_stock_txn_tenant_item", "tenant_id", "stock_item_id"),
    )
    id = _pk(); tenant_id = _text(); stock_item_id = _text(); godown_id = _text()
    batch_id = _text(); doc_type = _text(); source_doc_id = _text(); txn_date = _ts()
    qty = _num(); rate = _num(); value = _num(); direction = _text(); notes = _text()
    created_at = _ts()
    # drift: written by routers, were dropped by migration
    balance = _num(); delta = _num(); product_id = _text(); product_name = _text()
    reason = _text(); user_id = _text(); user_name = _text()
    # Stock Log rebuild (2026-07-14): human-readable voucher number, distinct from
    # source_doc_id (an opaque row id) — populated alongside doc_type going
    # forward; historical rows fall back to parsing it out of `reason`.
    voucher_no = _text()
    # doc_type alone can't distinguish e.g. a v2 GRN from a plain PO direct
    # receive (both "PURCHASE") — needed so the drill-down knows which page to
    # open. See migration 026 / project-stocklog-grn-route-mislabel.md.
    source_doc_type = _text()


class StockTransfer(Base):
    __tablename__ = "stock_transfers"
    __table_args__ = (
        Index("ix_stock_transfers_tenant_id", "tenant_id"),
        Index("ix_stock_transfers_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); from_godown_id = _text(); to_godown_id = _text()
    items = _jsonb(); status = _text(); transfer_date = _ts(); notes = _text()
    created_at = _ts(); updated_at = _ts()


class Batch(Base):
    __tablename__ = "batches"
    __table_args__ = (
        Index("ix_batches_tenant_id", "tenant_id"),
        Index("ix_batches_tenant_item", "tenant_id", "stock_item_id"),
    )
    id = _pk(); tenant_id = _text(); stock_item_id = _text(); batch_no = _text()
    mfg_date = _ts(); exp_date = _ts(); extra = _jsonb(); created_at = _ts()


class PhysicalVerification(Base):
    __tablename__ = "physical_verifications"
    __table_args__ = (
        Index("ix_phys_verif_tenant_id", "tenant_id"),
        Index("ix_phys_verif_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); godown_id = _text(); verification_date = _ts()
    items = _jsonb(); status = _text(); notes = _text(); created_at = _ts(); updated_at = _ts()


class QCReport(Base):
    __tablename__ = "qc_reports"
    __table_args__ = (
        Index("ix_qc_reports_tenant_id", "tenant_id"),
        Index("ix_qc_reports_tenant_doc", "tenant_id", "source_doc_id", "doc_type"),
    )
    id = _pk(); tenant_id = _text(); source_doc_id = _text(); doc_type = _text()
    items = _jsonb(); result = _text(); notes = _text(); created_at = _ts(); updated_at = _ts()


# ── purchase ───────────────────────────────────────────────────────────────────
class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        Index("ix_purchase_orders_tenant_id", "tenant_id"),
        Index("ix_purchase_orders_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); vendor_id = _text(); po_number = _text()
    status = _text(); items = _jsonb(); total_amount = _num(); notes = _text()
    order_date = _ts(); created_at = _ts(); updated_at = _ts()


class PurchaseOrderV2(Base):
    __tablename__ = "purchase_orders_v2"
    __table_args__ = (
        Index("ix_po_v2_tenant_id", "tenant_id"),
        Index("ix_po_v2_tenant_status", "tenant_id", "status"),
        Index("ix_po_v2_tenant_vendor", "tenant_id", "vendor_id"),
    )
    id = _pk(); tenant_id = _text(); vendor_id = _text(); po_number = _text()
    status = _text(); lines = _jsonb(); gst_details = _jsonb(); total_amount = _num()
    notes = _text(); order_date = _ts(); created_at = _ts(); updated_at = _ts()


class GoodsReceiptNoteV2(Base):
    __tablename__ = "grn_v2"
    __table_args__ = (
        Index("ix_grn_v2_tenant_id", "tenant_id"),
        Index("ix_grn_v2_tenant_status", "tenant_id", "status"),
        Index("ix_grn_v2_tenant_po", "tenant_id", "po_id"),
    )
    id = _pk(); tenant_id = _text(); purchase_order_id = Column("po_id", Text); vendor_id = _text()
    grn_number = _text(); status = _text(); lines = _jsonb(); gst_details = _jsonb()
    total_amount = _num(); notes = _text(); receipt_date = _ts()
    created_at = _ts(); updated_at = _ts()


class PurchaseBill(Base):
    __tablename__ = "purchase_bills"
    __table_args__ = (
        Index("ix_purchase_bills_tenant_id", "tenant_id"),
        Index("ix_purchase_bills_tenant_status", "tenant_id", "status"),
        Index("ix_purchase_bills_tenant_vendor", "tenant_id", "vendor_id"),
    )
    id = _pk(); tenant_id = _text(); vendor_id = _text()
    # legacy single-GRN link (old Mongo field — kept for backward compat)
    grn_id = _text()
    # new fields used by purchase_v2 router
    bill_number = _text(); vendor_invoice_no = _text(); vendor_invoice_date = _text()
    vendor_name = _text(); purchase_order_id = _text(); grn_ids = _jsonb()
    lines = _jsonb(); gst_details = _jsonb()
    taxable = _num(); total = _num(); tds_rate = _num()
    payment_received = _num(); status = _text(); notes = _text()
    journal_entry_id = _text()
    # legacy field aliases (old Mongo schema — preserved so existing rows still read)
    vendor_bill_no = _text(); total_amount = _num(); bill_date = _ts()
    created_at = _ts(); updated_at = _ts()


class PurchaseReturn(Base):
    __tablename__ = "purchase_returns"
    __table_args__ = (
        Index("ix_purchase_returns_tenant_id", "tenant_id"),
        Index("ix_purchase_returns_tenant_status", "tenant_id", "status"),
        Index("ix_purchase_returns_tenant_vendor", "tenant_id", "vendor_id"),
    )
    id = _pk(); tenant_id = _text(); vendor_id = _text(); bill_id = _text()
    return_number = _text(); status = _text(); lines = _jsonb(); gst_details = _jsonb()
    total_amount = _num(); notes = _text(); return_date = _ts()
    created_at = _ts(); updated_at = _ts()


class VendorBillSubmission(Base):
    __tablename__ = "vendor_bill_submissions"
    __table_args__ = (
        Index("ix_vendor_bill_sub_tenant_id", "tenant_id"),
        Index("ix_vendor_bill_sub_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); vendor_id = _text(); bill_number = _text()
    amount = _num(); status = _text(); files = _jsonb(); notes = _text()
    submitted_at = _ts(); created_at = _ts(); updated_at = _ts()
    # drift: written by routers, were dropped by migration
    bill_date = _ts(); description = _text(); file_ref = _text()
    linked_purchase_invoice_id = _text(); submission_no = _text()


class PONumberAudit(Base):
    __tablename__ = "po_number_audit"
    __table_args__ = (Index("ix_po_number_audit_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); po_id = _text(); old_number = _text()
    new_number = _text(); changed_by = _text(); changed_at = _ts(); reason = _text()
    # drift: written by routers, were dropped by migration
    changed_by_name = _text(); new_po_number = _text(); old_po_number = _text()
    purchase_order_id = _text()


# ── sales ──────────────────────────────────────────────────────────────────────
class Quotation(Base):
    __tablename__ = "quotations"
    __table_args__ = (
        Index("ix_quotations_tenant_id", "tenant_id"),
        Index("ix_quotations_tenant_status", "tenant_id", "status"),
        Index("ix_quotations_tenant_customer", "tenant_id", "customer_id"),
    )
    id = _pk(); tenant_id = _text(); customer_id = _text(); quotation_no = _text()
    status = _text(); lines = _jsonb(); gst_details = _jsonb(); total_amount = _num()
    notes = _text(); valid_until = _ts(); quotation_date = _ts()
    created_at = _ts(); updated_at = _ts()


class SalesOrder(Base):
    __tablename__ = "sales_orders"
    __table_args__ = (
        Index("ix_sales_orders_tenant_id", "tenant_id"),
        Index("ix_sales_orders_tenant_status", "tenant_id", "status"),
        Index("ix_sales_orders_tenant_customer", "tenant_id", "customer_id"),
    )
    id = _pk(); tenant_id = _text(); customer_id = _text(); so_number = _text()
    status = _text(); lines = _jsonb(); gst_details = _jsonb(); total_amount = _num()
    notes = _text(); delivery_date = _ts(); order_date = _ts()
    created_at = _ts(); updated_at = _ts()


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_tenant_id", "tenant_id"),
        Index("ix_invoices_tenant_status", "tenant_id", "status"),
        Index("ix_invoices_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_invoices_tenant_date", "tenant_id", "invoice_date"),
    )
    id = _pk(); tenant_id = _text(); customer_id = _text(); so_id = _text()
    invoice_no = _text(); status = _text(); lines = _jsonb(); gst_details = _jsonb()
    total_amount = _num(); paid_amount = _num(); balance_due = _num(); notes = _text()
    invoice_date = _ts(); due_date = _ts(); created_at = _ts(); updated_at = _ts()
    # drift: written by routers, were dropped by migration
    approval_state = _text(); invoice_number = _text(); invoice_type = _text()
    source_bill_submission_id = _text(); supplier_id = _text(); total = _num()

    @property
    def payment_received(self):
        return self.paid_amount

    @payment_received.setter
    def payment_received(self, value):
        self.paid_amount = value

    @property
    def items(self):
        return self.lines

    @items.setter
    def items(self, value):
        self.lines = value


class CreditNote(Base):
    __tablename__ = "credit_notes"
    __table_args__ = (
        Index("ix_credit_notes_tenant_id", "tenant_id"),
        Index("ix_credit_notes_tenant_status", "tenant_id", "status"),
        Index("ix_credit_notes_tenant_customer", "tenant_id", "customer_id"),
    )
    id = _pk(); tenant_id = _text(); customer_id = _text(); invoice_id = _text()
    cn_number = _text(); status = _text(); lines = _jsonb(); gst_details = _jsonb()
    total_amount = _num(); notes = _text(); cn_date = _ts()
    created_at = _ts(); updated_at = _ts()


class Dispatch(Base):
    __tablename__ = "dispatches"
    __table_args__ = (
        Index("ix_dispatches_tenant_id", "tenant_id"),
        Index("ix_dispatches_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); invoice_id = _text(); so_id = _text()
    dispatch_no = _text(); status = _text(); lines = _jsonb(); notes = _text()
    dispatch_date = _ts(); created_at = _ts(); updated_at = _ts()


class ProformaInvoice(Base):
    __tablename__ = "proforma_invoices"
    __table_args__ = (
        Index("ix_proforma_inv_tenant_id", "tenant_id"),
        Index("ix_proforma_inv_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); customer_id = _text(); pi_number = _text()
    status = _text(); lines = _jsonb(); gst_details = _jsonb(); total_amount = _num()
    notes = _text(); pi_date = _ts(); valid_until = _ts()
    created_at = _ts(); updated_at = _ts()


class PaymentLink(Base):
    __tablename__ = "payment_links"
    __table_args__ = (
        Index("ix_payment_links_tenant_id", "tenant_id"),
        Index("ix_payment_links_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); invoice_id = _text(); amount = _num()
    status = _text(); url = _text(); expires_at = _ts()
    created_at = _ts(); updated_at = _ts()
    gateway = _text(); party_id = _text(); txn_ref = _text()  # drift


# ── accounting ────────────────────────────────────────────────────────────────
class ChartOfAccount(Base):
    __tablename__ = "chart_of_accounts"
    __table_args__ = (
        Index("ix_coa_tenant_id", "tenant_id"),
        Index("ix_coa_tenant_code", "tenant_id", "code"),
        Index("ix_coa_tenant_group", "tenant_id", "group_id"),
    )
    id = _pk(); tenant_id = _text(); code = _text(); name = _text()
    group_id = _text(); account_type = _text(); parent_id = _text()
    description = _text(); is_active = _bool(True); opening_balance = _num()
    currency = _text(); tags = _jsonb()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class MasterLedger(Base):
    __tablename__ = "master_ledgers"
    __table_args__ = (
        Index("ix_master_ledgers_tenant_id", "tenant_id"),
        Index("ix_master_ledgers_tenant_group", "tenant_id", "group_id"),
    )
    id = _pk(); tenant_id = _text(); name = _text(); group_id = _text()
    opening_balance = _num(); balance_type = _text(); is_deleted = _bool()
    deleted_at = _ts(); created_at = _ts(); updated_at = _ts()
    # Links this ledger to a chart_of_accounts row (by id) so the voucher
    # engine can stamp a real account_code onto journal lines — every
    # financial report (Trial Balance/P&L/Balance Sheet) groups by
    # account_code, which master_ledgers never carried on its own.
    coa_account_id = _text()


class MasterGroup(Base):
    __tablename__ = "master_groups"
    __table_args__ = (Index("ix_master_groups_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); parent_id = _text()
    nature = _text(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class CostCenter(Base):
    __tablename__ = "cost_centers"
    __table_args__ = (Index("ix_cost_centers_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); parent_id = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class FiscalYear(Base):
    __tablename__ = "fiscal_years"
    __table_args__ = (Index("ix_fiscal_years_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); label = _text(); start_date = _ts()
    end_date = _ts(); is_current = _bool(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class Currency(Base):
    __tablename__ = "currencies"
    __table_args__ = (Index("ix_currencies_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); code = _text(); name = _text()
    symbol = _text(); exchange_rate = _num(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class VoucherType(Base):
    __tablename__ = "voucher_types"
    __table_args__ = (Index("ix_voucher_types_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); nature = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        Index("ix_je_tenant_id", "tenant_id"),
        Index("ix_je_tenant_status", "tenant_id", "status"),
        Index("ix_je_tenant_date", "tenant_id", "je_date"),
        Index("ix_je_tenant_source", "tenant_id", "source_id", "source_type"),
    )
    id = _pk(); tenant_id = _text(); je_number = _text(); source_id = _text()
    source_type = _text(); je_date = _ts(); narration = _text(); lines = _jsonb()
    status = _text(); created_at = _ts(); updated_at = _ts()
    # drift: written by routers, were dropped by migration
    cgst = _num(); created_by = _text(); created_by_name = _text(); date = _ts()
    entry_number = _text(); fiscal_year = _text(); igst = _num(); party_id = _text()
    party_name = _text(); party_type = _text(); reference = _text(); sgst = _num()
    source_collection = _text(); tags = _jsonb(); taxable_amount = _num()
    total_credit = _num(); total_debit = _num()


class Voucher(Base):
    __tablename__ = "vouchers"
    __table_args__ = (
        Index("ix_vouchers_tenant_id", "tenant_id"),
        Index("ix_vouchers_tenant_status", "tenant_id", "status"),
        Index("ix_vouchers_tenant_type", "tenant_id", "voucher_type"),
        Index("ix_vouchers_tenant_date", "tenant_id", "voucher_date"),
    )
    id = _pk(); tenant_id = _text(); voucher_no = _text(); voucher_type = _text()
    voucher_date = _ts(); amount = _num(); narration = _text(); lines = _jsonb()
    status = _text(); created_at = _ts(); updated_at = _ts()
    # drift: written by routers, were dropped by migration
    date = _ts(); party_id = _text(); party_name = _text(); party_type = _text()
    payment_link_id = _text(); payment_mode = _text(); pos_sale_id = _text()
    reference_doc = _text(); source = _text(); voucher_number = _text()


class VoucherV2(Base):
    __tablename__ = "vouchers_v2"
    __table_args__ = (
        Index("ix_vouchers_v2_tenant_id", "tenant_id"),
        Index("ix_vouchers_v2_tenant_status", "tenant_id", "status"),
        Index("ix_vouchers_v2_tenant_type", "tenant_id", "voucher_type"),
        Index("ix_vouchers_v2_tenant_date", "tenant_id", "voucher_date"),
    )
    id = _pk(); tenant_id = _text(); voucher_no = _text(); voucher_type = _text()
    parent_type = _text(); source_id = _text(); voucher_date = _ts(); amount = _num()
    narration = _text(); accounting_lines = _jsonb(); inventory_lines = _jsonb()
    gst_details = _jsonb(); status = _text(); posted = _bool(); posted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class VoucherCounter(Base):
    __tablename__ = "voucher_counters"
    __table_args__ = (Index("ix_voucher_counters_tenant_key", "tenant_id", "key"),)
    id = _pk(); tenant_id = _text(); key = _text(); seq = _int(0)


class ExpenseEntry(Base):
    __tablename__ = "expense_entries"
    __table_args__ = (
        Index("ix_expense_entries_tenant_id", "tenant_id"),
        Index("ix_expense_entries_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); expense_no = _text(); category_id = _text()
    amount = _num(); tax_amount = _num(); total_amount = _num(); status = _text()
    lines = _jsonb(); notes = _text(); expense_date = _ts(); approved_by = _text()
    approved_at = _ts(); created_at = _ts(); updated_at = _ts()


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    __table_args__ = (Index("ix_expense_cats_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); ledger_id = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class Advance(Base):
    __tablename__ = "advances"
    __table_args__ = (
        Index("ix_advances_tenant_id", "tenant_id"),
        Index("ix_advances_tenant_status", "tenant_id", "status"),
        Index("ix_advances_tenant_party", "tenant_id", "party_type", "party_id"),
    )
    id = _pk(); tenant_id = _text(); party_type = _text(); party_id = _text()
    amount = _num(); balance = _num(); status = _text(); notes = _text()
    recovery_month = _text()  # YYYY-MM the advance is scheduled to be recovered
    advance_date = _ts(); created_at = _ts(); updated_at = _ts()


class InterestRule(Base):
    __tablename__ = "interest_rules"
    __table_args__ = (Index("ix_interest_rules_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); rate = _num(); period = _text()
    apply_to = _text(); extra = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


# ── banking ────────────────────────────────────────────────────────────────────
class BankAccount(Base):
    __tablename__ = "bank_accounts"
    __table_args__ = (
        Index("ix_bank_accounts_tenant_id", "tenant_id"),
        Index("ix_bank_accounts_tenant_ledger", "tenant_id", "ledger_id"),
    )
    id = _pk(); tenant_id = _text(); name = _text(); bank_name = _text()
    account_number = _text(); ifsc = _text(); branch = _text(); account_type = _text()
    opening_balance = _num(); current_balance = _num(); ledger_id = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class BankEntry(Base):
    __tablename__ = "bank_entries"
    __table_args__ = (
        Index("ix_bank_entries_tenant_id", "tenant_id"),
        Index("ix_bank_entries_tenant_account", "tenant_id", "bank_account_id"),
        Index("ix_bank_entries_tenant_date", "tenant_id", "entry_date"),
    )
    id = _pk(); tenant_id = _text(); bank_account_id = _text(); entry_type = _text()
    amount = _num(); narration = _text(); reference = _text(); entry_date = _ts()
    is_reconciled = _bool(); reconciled_at = _ts(); extra = _jsonb()
    created_at = _ts(); updated_at = _ts()


class BankStatement(Base):
    __tablename__ = "bank_statements"
    __table_args__ = (
        Index("ix_bank_statements_tenant_id", "tenant_id"),
        Index("ix_bank_statements_tenant_account", "tenant_id", "bank_account_id"),
    )
    id = _pk(); tenant_id = _text(); bank_account_id = _text()
    statement_date = _ts(); file_url = _text(); status = _text(); lines_count = _int(0)
    extra = _jsonb(); created_at = _ts(); updated_at = _ts()


class BankStatementLine(Base):
    __tablename__ = "bank_statement_lines"
    __table_args__ = (
        Index("ix_bank_stmt_lines_tenant_id", "tenant_id"),
        Index("ix_bank_stmt_lines_tenant_account", "tenant_id", "bank_account_id"),
        Index("ix_bank_stmt_lines_tenant_stmt", "tenant_id", "statement_id"),
    )
    id = _pk(); tenant_id = _text(); statement_id = _text(); bank_account_id = _text()
    txn_date = _ts(); description = _text(); debit = _num(); credit = _num()
    balance = _num(); is_matched = _bool(); matched_entry_id = _text()
    extra = _jsonb(); created_at = _ts()


class BankFeedImport(Base):
    __tablename__ = "bank_feed_imports"
    __table_args__ = (Index("ix_bank_feed_imports_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); bank_account_id = _text(); imported_at = _ts()
    lines_count = _int(0); source = _text(); extra = _jsonb(); created_at = _ts()


class PDC(Base):
    __tablename__ = "pdcs"
    __table_args__ = (
        Index("ix_pdcs_tenant_id", "tenant_id"),
        Index("ix_pdcs_tenant_status", "tenant_id", "status"),
        Index("ix_pdcs_tenant_party", "tenant_id", "party_type", "party_id"),
    )
    id = _pk(); tenant_id = _text(); bank_account_id = _text(); party_type = _text()
    party_id = _text(); cheque_no = _text(); amount = _num(); due_date = _ts()
    status = _text(); notes = _text(); created_at = _ts(); updated_at = _ts()


class ChequeTransaction(Base):
    __tablename__ = "cheque_transactions"
    __table_args__ = (
        Index("ix_cheque_txns_tenant_id", "tenant_id"),
        Index("ix_cheque_txns_tenant_status", "tenant_id", "status"),
        Index("ix_cheque_txns_tenant_bank", "tenant_id", "bank_account_id"),
        Index("ix_cheque_txns_tenant_date", "tenant_id", "cheque_date"),
    )
    id = _pk(); tenant_id = _text(); bank_account_id = _text(); bank_name = _text()
    template_id = _text(); cheque_number = _text()
    # legacy columns kept for backward compat
    party_type = _text(); party_id = _text(); cheque_no = _text()
    # Payee / financial data
    payee_name = _text(); amount = _num(); cheque_date = _ts()
    amount_in_words = _text()
    # Source voucher integration
    source_type = _text()   # payment_voucher | supplier_payment | customer_refund | expense_payment | bank_payment
    source_id = _text()     # id of the source voucher
    voucher_number = _text(); narration = _text(); company_name = _text()
    # Lifecycle
    status = _text()        # pending | printed | reprinted | cancelled | void | cleared | bounced
    is_void = _bool()
    void_reason = _text(); void_at = _ts(); void_by = _text()
    cancelled_at = _ts(); cancelled_by = _text(); cancellation_reason = _text()
    cleared_date = _text(); bounced_date = _text(); bounced_reason = _text()
    # Print tracking
    printed_at = _ts(); printed_by = _text(); printer = _text()
    reprint_count = _int(0); last_reprint_at = _ts(); last_reprint_by = _text()
    print_ip = _text(); reprint_log = _jsonb()
    # Misc
    account_payee = _bool(True); test_print = _bool()
    notes = _text(); created_at = _ts(); updated_at = _ts()


class ChequeIssueRegister(Base):
    """Cheque issue register — one entry per cheque leaf consumed."""
    __tablename__ = "cheque_issue_register"
    __table_args__ = (
        Index("ix_cheque_reg_tenant_id", "tenant_id"),
        Index("ix_cheque_reg_tenant_bank", "tenant_id", "bank_account_id"),
        Index("ix_cheque_reg_tenant_date", "tenant_id", "issue_date"),
    )
    id = _pk(); tenant_id = _text(); bank_account_id = _text(); bank_name = _text()
    cheque_number = _text(); cheque_txn_id = _text()
    payee_name = _text(); amount = _num(); cheque_date = _ts(); issue_date = _ts()
    status = _text(); voucher_number = _text(); narration = _text()
    issued_by = _text(); created_at = _ts(); updated_at = _ts()


class ChequeFormat(Base):
    __tablename__ = "cheque_formats"
    __table_args__ = (Index("ix_cheque_formats_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); bank_name = _text(); layout = _jsonb()
    is_default = _bool(); created_at = _ts(); updated_at = _ts()


# ── HR ─────────────────────────────────────────────────────────────────────────
class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        Index("ix_employees_tenant_id", "tenant_id"),
        Index("ix_employees_tenant_status", "tenant_id", "status"),
        Index("ix_employees_tenant_dept", "tenant_id", "department"),
    )
    id = _pk(); tenant_id = _text(); emp_code = _text(); name = _text()
    email = _text(); phone = _text(); department = _text(); designation = _text()
    date_of_joining = _ts(); date_of_leaving = _ts(); status = _text(); extra = _jsonb()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        Index("ix_attendance_tenant_id", "tenant_id"),
        Index("ix_attendance_tenant_employee", "tenant_id", "employee_id"),
        Index("ix_attendance_tenant_date", "tenant_id", "attendance_date"),
        # One row per (employee, period) for the monthly payroll aggregate —
        # partial index would be ideal but plain columns keep this portable.
        Index("ix_attendance_employee_period", "employee_id", "period"),
    )
    from sqlalchemy.orm import synonym
    id = _pk(); tenant_id = _text(); employee_id = _text()
    date = Column("attendance_date", Text, nullable=True)
    attendance_date = synonym("date")
    status = _text(); in_time = _ts(); out_time = _ts(); shift_id = _text()
    notes = _text(); created_at = _ts(); updated_at = _ts()
    # Daily fields written by routers/hr_attendance.py's manual/QR/bulk/webhook
    # flows and core/biometric_sync.py's derivation — were previously silently
    # dropped on every write (no matching column, no extra/data catch-all).
    check_in = _text(); check_out = _text()
    working_hours = _num(); overtime_hours = _num()
    source = _text()  # "manual" | "qr" | "biometric" | "self"
    late = _bool(); early_leave = _bool(); missing_punch = _bool()
    remarks = _text()
    # Monthly payroll-aggregate fields (core.biometric_sync.aggregate_monthly_paid_days).
    # A period-aggregate row has date=NULL and period="MMYYYY"; a daily row has
    # date set and period=NULL — the two never collide on a date-range filter
    # since SQL NULL comparisons never match a $gte/$lte range.
    period = _text(); paid_days = _num(); total_days = _int()


class AttendanceLog(Base):
    """Raw punch log — one row per device punch, before dedup/derivation into
    the daily `attendance` summary. `dedup_key` (device_id + raw device punch
    id, or device_id + employee_code + log_time when the device has no punch
    id) makes re-ingesting the same punch a no-op instead of a duplicate row."""
    __tablename__ = "attendance_logs"
    __table_args__ = (
        Index("ix_attendance_logs_tenant_id", "tenant_id"),
        Index("ix_attendance_logs_tenant_employee", "tenant_id", "employee_id"),
        Index("ix_attendance_logs_tenant_device", "tenant_id", "device_id"),
        Index("ix_attendance_logs_tenant_time", "tenant_id", "log_time"),
        Index("ix_attendance_logs_dedup_key", "dedup_key", unique=True),
    )
    id = _pk(); tenant_id = _text(); employee_id = _text(); log_time = _ts()
    direction = _text(); device_id = _text(); created_at = _ts()
    employee_code = _text()  # as reported by the device, kept even if mapping is later changed
    dedup_key = _text()
    sync_run_id = _text()  # which AttendanceSyncRun ingested this punch (NULL for direct webhook pushes)
    source = _text()  # "webhook" | "poll"
    raw_payload = _jsonb()  # device's original punch record, for troubleshooting
    processed = _bool(False)  # True once folded into the daily attendance summary
    processed_at = _ts()


class BiometricDevice(Base):
    """A registered eSSL (or compatible ADMS/push) biometric device/terminal."""
    __tablename__ = "biometric_devices"
    __table_args__ = (
        Index("ix_biometric_devices_tenant_id", "tenant_id"),
        Index("ix_biometric_devices_tenant_branch", "tenant_id", "branch_id"),
    )
    id = _pk(); tenant_id = _text(); name = _text(); serial_number = _text()
    branch_id = _text()  # nullable; hr_branches.id
    device_model = _text()  # e.g. "eSSL X990", "eSSL BioTime"
    integration_mode = _text()  # "push" | "poll"
    host = _text(); port = _int(4370); api_path = _text()  # poll-mode connection details
    push_secret = _text()  # HMAC secret for verifying this device's inbound webhook pushes
    poll_interval_seconds = _int(300)
    is_active = _bool(True)
    last_sync_at = _ts(); last_sync_status = _text()  # "success" | "partial" | "failed"
    last_seen_at = _ts()  # last time we received ANY punch or successful poll — device health signal
    notes = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class EmployeeDeviceMapping(Base):
    """Maps a device's own enrollment id for a person to our employee_id —
    devices identify punches by their own numeric user id, not employee_code."""
    __tablename__ = "employee_device_mappings"
    __table_args__ = (
        Index("ix_emp_device_map_tenant_id", "tenant_id"),
        Index("ix_emp_device_map_tenant_device", "tenant_id", "device_id"),
        Index("ix_emp_device_map_tenant_employee", "tenant_id", "employee_id"),
        Index("ix_emp_device_map_device_enrollment", "device_id", "device_enrollment_id", unique=True),
    )
    id = _pk(); tenant_id = _text(); device_id = _text(); employee_id = _text()
    device_enrollment_id = _text()  # the device's own user/enrollment number
    is_active = _bool(True)
    created_at = _ts(); updated_at = _ts()


class AttendanceSyncRun(Base):
    """One row per sync attempt (manual or scheduled) against one device —
    the sync history / audit trail."""
    __tablename__ = "attendance_sync_runs"
    __table_args__ = (
        Index("ix_att_sync_runs_tenant_id", "tenant_id"),
        Index("ix_att_sync_runs_tenant_device", "tenant_id", "device_id"),
        Index("ix_att_sync_runs_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); device_id = _text()
    trigger = _text()  # "manual" | "scheduled" | "webhook"
    status = _text()  # "running" | "success" | "partial" | "failed"
    started_at = _ts(); finished_at = _ts()
    punches_fetched = _int(0); punches_new = _int(0); punches_duplicate = _int(0)
    error_message = _text()
    attempt = _int(1)
    next_attempt_at = _ts()  # set when status=failed and a retry is scheduled
    triggered_by = _text()  # user id, or "system" for scheduled runs
    created_at = _ts()


class AttendanceRule(Base):
    """Per-tenant (optionally per-shift) late/early/OT/missing-punch rules
    used to derive attendance status from raw punches."""
    __tablename__ = "attendance_rules"
    __table_args__ = (Index("ix_attendance_rules_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); shift_id = _text()  # NULL = tenant-wide default
    late_grace_minutes = _int(10)
    early_leave_grace_minutes = _int(10)
    half_day_threshold_hours = _num()  # worked hours below this -> HALF_DAY
    full_day_threshold_hours = _num()  # worked hours at/above this -> PRESENT
    overtime_after_hours = _num()  # hours beyond this on a working day count as OT
    missing_punch_action = _text()  # "flag" | "absent" | "ignore"
    is_active = _bool(True)
    created_at = _ts(); updated_at = _ts()


class AttendanceCorrection(Base):
    """Employee/HR-requested change to a derived attendance day, gated by
    HR/admin approval. Approving one re-runs derive_daily_attendance's rule
    logic against the corrected check-in/check-out rather than hand-editing
    the attendance row, so late/OT/paid_days recompute consistently."""
    __tablename__ = "attendance_corrections"
    __table_args__ = (
        Index("ix_att_corrections_tenant_id", "tenant_id"),
        Index("ix_att_corrections_tenant_employee", "tenant_id", "employee_id"),
        Index("ix_att_corrections_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); employee_id = _text(); attendance_date = _text()
    requested_check_in = _text(); requested_check_out = _text(); requested_status = _text()
    reason = _text(); status = _text()  # "PENDING" | "APPROVED" | "REJECTED"
    requested_by = _text(); requested_at = _ts()
    decided_by = _text(); decided_at = _ts(); rejection_reason = _text()
    created_at = _ts(); updated_at = _ts()


class Leave(Base):
    __tablename__ = "leaves"
    __table_args__ = (
        Index("ix_leaves_tenant_id", "tenant_id"),
        Index("ix_leaves_tenant_employee", "tenant_id", "employee_id"),
        Index("ix_leaves_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); employee_id = _text(); leave_type_id = _text()
    from_date = _ts(); to_date = _ts(); days = _num(); reason = _text()
    status = _text(); approved_by = _text(); approved_at = _ts()
    created_at = _ts(); updated_at = _ts()


class LeaveType(Base):
    __tablename__ = "leave_types"
    __table_args__ = (Index("ix_leave_types_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); annual_quota = _num()
    paid = _bool(True)
    carry_forward = _bool(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class Holiday(Base):
    __tablename__ = "holidays"
    __table_args__ = (Index("ix_holidays_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); holiday_date = _ts()
    optional = _bool(); created_at = _ts(); updated_at = _ts()
    branch_id = _text()  # nullable; None = applies to all branches


class Shift(Base):
    __tablename__ = "shifts"
    __table_args__ = (Index("ix_shifts_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); start_time = _text()
    end_time = _text(); grace_minutes = _int(0); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()
    # core/hr_models.py's Shift Pydantic model has declared these since before
    # this ORM class existed, but they had no matching column and Shift has no
    # extra/data catch-all — every create/update of a shift silently dropped
    # weekly_off_days/late_grace_min/full_day_hours/half_day_hours, so
    # routers/hr_attendance.py's late-detection always fell back to its
    # hardcoded defaults regardless of what was configured.
    weekly_off_days = _jsonb()  # list[int], 0=Sun..6=Sat
    late_grace_min = _int(10)
    full_day_hours = _num()
    half_day_hours = _num()
    crosses_midnight = _bool(False)  # night shift whose end_time is on the following calendar day


# ── payroll ────────────────────────────────────────────────────────────────────
class SalaryStructure(Base):
    __tablename__ = "salary_structures"
    __table_args__ = (Index("ix_salary_structs_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text()
    extra = Column("components", JSONB, nullable=True)
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class PayComponent(Base):
    __tablename__ = "pay_components"
    __table_args__ = (Index("ix_pay_components_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); component_type = _text()
    formula = _text(); is_taxable = _bool(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (
        Index("ix_payroll_runs_tenant_id", "tenant_id"),
        Index("ix_payroll_runs_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); month = _text(); year = _int()
    status = _text(); total_gross = _num(); total_deductions = _num()
    total_net = _num(); notes = _text(); run_at = _ts(); extra = _jsonb()
    created_at = _ts(); updated_at = _ts()


class Payslip(Base):
    __tablename__ = "payslips"
    __table_args__ = (
        Index("ix_payslips_tenant_id", "tenant_id"),
        Index("ix_payslips_tenant_employee", "tenant_id", "employee_id"),
        Index("ix_payslips_tenant_run", "tenant_id", "payroll_run_id"),
    )
    id = _pk(); tenant_id = _text(); payroll_run_id = _text(); employee_id = _text()
    month = _text(); year = _int(); gross = _num(); deductions = _num(); net = _num()
    components = _jsonb(); status = _text(); created_at = _ts(); updated_at = _ts()


class StatutoryParam(Base):
    __tablename__ = "statutory_params"
    __table_args__ = (Index("ix_statutory_params_tenant_key", "tenant_id", "key"),)
    id = _pk(); tenant_id = _text(); key = _text(); value = _jsonb()
    effective_from = _ts(); updated_at = _ts()


class FnFSettlement(Base):
    __tablename__ = "fnf_settlements"
    __table_args__ = (
        Index("ix_fnf_settlements_tenant_id", "tenant_id"),
        Index("ix_fnf_settlements_tenant_employee", "tenant_id", "employee_id"),
    )
    id = _pk(); tenant_id = _text(); employee_id = _text(); settlement_date = _ts()
    components = _jsonb(); total = _num(); status = _text(); notes = _text()
    created_at = _ts(); updated_at = _ts()


class TDSDeclaration(Base):
    __tablename__ = "tds_declarations"
    __table_args__ = (
        Index("ix_tds_declarations_tenant_id", "tenant_id"),
        Index("ix_tds_declarations_tenant_employee", "tenant_id", "employee_id"),
    )
    id = _pk(); tenant_id = _text(); employee_id = _text(); fy = _text()
    declarations = _jsonb(); submitted_at = _ts(); created_at = _ts(); updated_at = _ts()


# ── GST & taxation ────────────────────────────────────────────────────────────
class GSTRecord(Base):
    __tablename__ = "gst_records"
    __table_args__ = (
        Index("ix_gst_records_tenant_id", "tenant_id"),
        Index("ix_gst_records_tenant_gstin", "tenant_id", "gstin"),
        Index("ix_gst_records_tenant_period", "tenant_id", "period"),
    )
    id = _pk(); tenant_id = _text(); gstin = _text(); return_type = _text()
    period = _text(); data = _jsonb(); status = _text(); filed_at = _ts()
    created_at = _ts(); updated_at = _ts()
    # drift: written by routers, were dropped by migration
    cess = _num(); cgst = _num(); created_by = _text(); filing_status = _text()
    gst_type = _text(); igst = _num(); invoice_date = _ts(); invoice_number = _text()
    linked_invoice_id = _text(); party_name = _text(); return_period = _text()
    sgst = _num(); source = _text(); taxable_amount = _num(); total_amount = _num()


class GSTFilingCache(Base):
    __tablename__ = "gst_filing_cache"
    __table_args__ = (
        Index("ix_gst_filing_cache_tenant_id", "tenant_id"),
        Index("ix_gst_filing_cache_tenant_gstin", "tenant_id", "gstin"),
    )
    id = _pk(); tenant_id = _text(); gstin = _text(); period = _text()
    return_type = _text(); data = _jsonb(); cached_at = _ts()


class GSTINCache(Base):
    __tablename__ = "gstin_cache"
    __table_args__ = (Index("ix_gstin_cache_gstin", "gstin"),)
    id = _pk(); gstin = Column(Text, nullable=False, unique=True)
    data = _jsonb(); cached_at = _ts()


class GSTReconciliation(Base):
    __tablename__ = "gst_reconciliations"
    __table_args__ = (
        Index("ix_gst_recs_tenant_id", "tenant_id"),
        Index("ix_gst_recs_tenant_period", "tenant_id", "period"),
    )
    id = _pk(); tenant_id = _text(); period = _text(); status = _text()
    mismatches = _jsonb(); created_at = _ts(); updated_at = _ts()


class TDSEntry(Base):
    __tablename__ = "tds_entries"
    __table_args__ = (
        Index("ix_tds_entries_tenant_id", "tenant_id"),
        Index("ix_tds_entries_tenant_party", "tenant_id", "party_type", "party_id"),
    )
    id = _pk(); tenant_id = _text(); source_doc_id = _text(); party_type = _text()
    party_id = _text(); section = _text(); rate = _num(); base_amount = _num()
    tds_amount = _num(); entry_date = _ts(); status = _text(); created_at = _ts()


class TCSEntry(Base):
    __tablename__ = "tcs_entries"
    __table_args__ = (
        Index("ix_tcs_entries_tenant_id", "tenant_id"),
        Index("ix_tcs_entries_tenant_customer", "tenant_id", "customer_id"),
    )
    id = _pk(); tenant_id = _text(); source_doc_id = _text(); customer_id = _text()
    section = _text(); rate = _num(); base_amount = _num(); tcs_amount = _num()
    entry_date = _ts(); status = _text(); created_at = _ts()


class EWayBill(Base):
    __tablename__ = "eway_bills"
    __table_args__ = (
        Index("ix_eway_bills_tenant_id", "tenant_id"),
        Index("ix_eway_bills_tenant_status", "tenant_id", "status"),
        Index("ix_eway_bills_tenant_source", "tenant_id", "source_doc_id", "doc_type"),
    )
    id = _pk(); tenant_id = _text(); source_doc_id = _text(); doc_type = _text()
    ewb_number = _text(); status = _text(); valid_until = _ts(); data = _jsonb()
    created_at = _ts(); updated_at = _ts()
    # drift: written by routers, were dropped by migration
    created_by = _text(); distance_km = _num(); environment = _text(); ewb_date = _ts()
    from_gstin = _text(); government_response = _jsonb(); invoice_date = _ts()
    invoice_id = _text(); invoice_number = _text(); qr_value = _text(); simulated = _bool()
    to_gstin = _text(); total_invoice_value = _num(); trans_doc_no = _text()
    transport_mode = _text(); transporter_id = _text(); transporter_name = _text()
    valid_until_iso = _text(); vehicle_number = _text()


# ── fixed assets ──────────────────────────────────────────────────────────────
class FixedAsset(Base):
    __tablename__ = "fixed_assets"
    __table_args__ = (
        Index("ix_fixed_assets_tenant_id", "tenant_id"),
        Index("ix_fixed_assets_tenant_status", "tenant_id", "status"),
        Index("ix_fixed_assets_tenant_category", "tenant_id", "category_id"),
    )
    id = _pk(); tenant_id = _text(); name = _text(); category_id = _text()
    purchase_date = _ts(); cost = _num(); salvage_value = _num()
    useful_life_years = _num(); depreciation_method = _text(); status = _text()
    extra = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class AssetCategory(Base):
    __tablename__ = "asset_categories"
    __table_args__ = (Index("ix_asset_cats_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); depreciation_method = _text()
    rate = _num(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class AssetDepreciationRun(Base):
    __tablename__ = "asset_depreciation_runs"
    __table_args__ = (
        Index("ix_asset_depr_runs_tenant_id", "tenant_id"),
        Index("ix_asset_depr_runs_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); run_date = _ts(); status = _text()
    entries = _jsonb(); created_at = _ts(); updated_at = _ts()
    # drift: written by routers, were dropped by migration
    asset_code = _text(); asset_description = _text(); asset_id = _text(); basis = _text()
    closing_wdv = _num(); days_held = _int(); depreciation = _num(); financial_year = _text()
    gross_value = _num(); is_fully_depreciated = _bool(); method = _text()
    opening_wdv = _num(); residual_value = _num(); total_fy_days = _int()


class AssetTransaction(Base):
    __tablename__ = "asset_transactions"
    __table_args__ = (
        Index("ix_asset_txns_tenant_id", "tenant_id"),
        Index("ix_asset_txns_tenant_asset", "tenant_id", "asset_id"),
    )
    id = _pk(); tenant_id = _text(); asset_id = _text(); txn_type = _text()
    amount = _num(); txn_date = _ts(); notes = _text(); created_at = _ts()


# ── projects ───────────────────────────────────────────────────────────────────
class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_tenant_id", "tenant_id"),
        Index("ix_projects_tenant_status", "tenant_id", "status"),
        Index("ix_projects_tenant_customer", "tenant_id", "customer_id"),
    )
    id = _pk(); tenant_id = _text(); name = _text(); customer_id = _text()
    status = _text(); budget = _num(); start_date = _ts(); end_date = _ts()
    notes = _text(); extra = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class ProjectCost(Base):
    __tablename__ = "project_costs"
    __table_args__ = (
        Index("ix_project_costs_tenant_id", "tenant_id"),
        Index("ix_project_costs_tenant_project", "tenant_id", "project_id"),
    )
    id = _pk(); tenant_id = _text(); project_id = _text(); cost_type = _text()
    amount = _num(); notes = _text(); cost_date = _ts(); created_at = _ts(); updated_at = _ts()


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_tenant_id", "tenant_id"),
        Index("ix_tasks_tenant_project", "tenant_id", "project_id"),
        Index("ix_tasks_tenant_status", "tenant_id", "status"),
        Index("ix_tasks_tenant_assigned", "tenant_id", "assigned_to"),
    )
    id = _pk(); tenant_id = _text(); project_id = _text(); name = _text()
    assigned_to = _text(); status = _text(); priority = _text(); due_date = _ts()
    notes = _text(); created_at = _ts(); updated_at = _ts()


class TimesheetEntry(Base):
    __tablename__ = "timesheet_entries"
    __table_args__ = (
        Index("ix_timesheet_tenant_id", "tenant_id"),
        Index("ix_timesheet_tenant_project", "tenant_id", "project_id"),
        Index("ix_timesheet_tenant_employee", "tenant_id", "employee_id"),
    )
    id = _pk(); tenant_id = _text(); project_id = _text(); task_id = _text()
    employee_id = _text(); hours = _num(); notes = _text(); entry_date = _ts()
    created_at = _ts(); updated_at = _ts()


# ── manufacturing ─────────────────────────────────────────────────────────────
class BOM(Base):
    __tablename__ = "boms"
    __table_args__ = (
        Index("ix_boms_tenant_id", "tenant_id"),
        Index("ix_boms_tenant_product", "tenant_id", "finished_product_id"),
        Index("ix_boms_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); finished_product_id = _text()
    finished_product_name = _text(); sku = _text(); output_qty = _num(); uom = _text()
    version = _text(); status = _text(); valuation_method = _text()
    components = _jsonb(); co_products = _jsonb(); by_products = _jsonb()
    routing_steps = _jsonb(); items = _jsonb(); estimated_cost = _num(); notes = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        Index("ix_work_orders_tenant_id", "tenant_id"),
        Index("ix_work_orders_tenant_status", "tenant_id", "status"),
        Index("ix_work_orders_tenant_bom", "tenant_id", "bom_id"),
    )
    id = _pk(); tenant_id = _text(); bom_id = _text(); wo_number = _text()
    status = _text(); planned_qty = _num(); produced_qty = _num()
    start_date = _ts(); end_date = _ts(); notes = _text()
    created_at = _ts(); updated_at = _ts()


class ProductionJournal(Base):
    __tablename__ = "production_journals"
    __table_args__ = (
        Index("ix_prod_journals_tenant_id", "tenant_id"),
        Index("ix_prod_journals_tenant_wo", "tenant_id", "work_order_id"),
    )
    id = _pk(); tenant_id = _text(); work_order_id = _text(); journal_date = _ts()
    lines = _jsonb(); status = _text(); notes = _text(); created_at = _ts(); updated_at = _ts()


class WastageEntry(Base):
    __tablename__ = "wastage_entries"
    __table_args__ = (
        Index("ix_wastage_tenant_id", "tenant_id"),
        Index("ix_wastage_tenant_wo", "tenant_id", "work_order_id"),
    )
    id = _pk(); tenant_id = _text(); work_order_id = _text(); entry_date = _ts()
    lines = _jsonb(); notes = _text(); created_at = _ts(); updated_at = _ts()


# ── job work ───────────────────────────────────────────────────────────────────
class JobWorkChallan(Base):
    __tablename__ = "job_work_challans"
    __table_args__ = (
        Index("ix_job_work_challans_tenant_id", "tenant_id"),
        Index("ix_job_work_challans_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text()
    challan_number = _text()        # e.g. JWC00001
    date = _text()                  # ISO date string
    due_date = _text()              # computed return deadline
    job_worker_id = _text()
    job_worker_name = _text()
    job_worker_gstin = _text()
    nature = _text()                # "inputs" | "capital_goods"
    gst_type = _text()              # "auto" | "intra" | "inter"
    vehicle_no = _text()
    transport = _text()
    is_inter_state = _bool()
    items = _jsonb()                # legacy JSONB array — kept for rollback safety, no longer written to
    status = _text()
    notes = _text()
    return_window_days = _int(0)
    is_overdue = _bool()
    deemed_supply = _bool()
    total_taxable_value = _num()
    total_cgst = _num(); total_sgst = _num(); total_igst = _num()
    total_gst = _num(); grand_total = _num()
    journal_entry_id = _text()
    created_at = _ts(); updated_at = _ts()
    # Tally-style header/footer fields
    contact_person = _text(); driver_name = _text(); lr_number = _text()
    eway_bill_number = _text(); process_name = _text(); instructions = _text()
    prepared_by = _text(); checked_by = _text()
    attachments = _jsonb()  # [{id, name, path, size, content_type, uploaded_at}]


class JobWorkChallanItem(Base):
    __tablename__ = "job_work_challan_items"
    __table_args__ = (Index("ix_jw_challan_items_challan_id", "challan_id"),)
    id = _pk(); challan_id = _text(n=False); tenant_id = _text()
    line_no = _int(0)
    product_id = _text(); product_name = _text(); sku = _text(); description = _text()
    hsn_code = _text(); uom = _text(); is_custom = _bool(False)
    quantity = _num(); rate = _num(); amount = _num()
    gst_rate = _num(); taxable_value = _num()
    cgst = _num(); sgst = _num(); igst = _num(); line_total = _num()
    batch_id = _text(); serial_id = _text(); expiry_date = _text(); remarks = _text()
    created_at = _ts(); updated_at = _ts()


class JobWorkReceipt(Base):
    __tablename__ = "job_work_receipts"
    __table_args__ = (
        Index("ix_job_work_receipts_tenant_id", "tenant_id"),
        Index("ix_job_work_receipts_challan_id", "challan_id"),
    )
    id = _pk(); tenant_id = _text()
    receipt_number = _text()        # e.g. JWR00001
    challan_id = _text()
    date = _text()                  # ISO date string
    items = _jsonb()                # legacy JSONB array — kept for rollback safety, no longer written to
    notes = _text()
    status = _text()
    created_at = _ts(); updated_at = _ts()
    attachments = _jsonb()  # [{id, name, path, size, content_type, uploaded_at}]


class JobWorkReceiptItem(Base):
    __tablename__ = "job_work_receipt_items"
    __table_args__ = (
        Index("ix_jw_receipt_items_receipt_id", "receipt_id"),
        Index("ix_jw_receipt_items_challan_item_id", "challan_item_id"),
    )
    id = _pk(); receipt_id = _text(n=False); tenant_id = _text()
    challan_item_id = _text()
    product_id = _text(); product_name = _text(); sku = _text(); is_custom = _bool(False)
    quantity_received = _num(); accepted_quantity = _num()
    rejected_quantity = _num(); scrap_quantity = _num()
    batch_id = _text(); serial_id = _text(); expiry_date = _text(); remarks = _text()
    created_at = _ts(); updated_at = _ts()


class RateTable(Base):
    __tablename__ = "rate_tables"
    __table_args__ = (Index("ix_rate_tables_tenant_key", "tenant_id", "key"),)
    id = _pk(); tenant_id = _text(); key = _text(); value = _jsonb()
    description = _text(); effective_from = _ts(); effective_to = _ts()
    created_at = _ts(); updated_at = _ts()


# ── approvals ─────────────────────────────────────────────────────────────────
class ApprovalPolicy(Base):
    __tablename__ = "approval_policies"
    __table_args__ = (Index("ix_approval_policies_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); doc_type = _text()
    conditions = _jsonb(); steps = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_tenant_id", "tenant_id"),
        Index("ix_approval_requests_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); policy_id = _text(); doc_type = _text()
    source_id = _text(); status = _text(); current_step = _int(0); history = _jsonb()
    created_at = _ts(); updated_at = _ts()


class ApprovalStep(Base):
    __tablename__ = "approval_steps"
    __table_args__ = (
        Index("ix_approval_steps_tenant_id", "tenant_id"),
        Index("ix_approval_steps_tenant_request", "tenant_id", "request_id"),
    )
    id = _pk(); tenant_id = _text(); request_id = _text(); step_index = _int(0)
    approver_id = _text(); status = _text(); notes = _text(); actioned_at = _ts()
    created_at = _ts(); updated_at = _ts()


# ── POS ────────────────────────────────────────────────────────────────────────
class POSSale(Base):
    __tablename__ = "pos_sales"
    __table_args__ = (
        Index("ix_pos_sales_tenant_id", "tenant_id"),
        Index("ix_pos_sales_tenant_status", "tenant_id", "status"),
        Index("ix_pos_sales_tenant_session", "tenant_id", "session_id"),
    )
    id = _pk(); tenant_id = _text(); session_id = _text(); sale_no = _text()
    lines = _jsonb(); gst_details = _jsonb(); total_amount = _num()
    paid_amount = _num(); payment_mode = _text(); status = _text(); sale_date = _ts()
    created_at = _ts(); updated_at = _ts()
    # drift: written by routers, were dropped by migration
    cashier_id = _text(); change = _num(); client_uuid = _text(); created_at_client = _ts()
    customer_id = _text(); customer_name = _text(); is_interstate = _bool(); payment = _jsonb()
    place_of_supply = _text(); receipt_no = _text(); tendered = _num(); terminal = _text()
    voided = _bool()


class POSSession(Base):
    __tablename__ = "pos_sessions"
    __table_args__ = (
        Index("ix_pos_sessions_tenant_id", "tenant_id"),
        Index("ix_pos_sessions_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); opened_by = _text(); opened_at = _ts()
    closed_at = _ts(); opening_cash = _num(); closing_cash = _num(); status = _text()
    notes = _text(); created_at = _ts(); updated_at = _ts()
    # drift: written by routers, were dropped by migration
    cashier_id = _text(); cashier_name = _text(); session_no = _text(); terminal = _text()


class PriceList(Base):
    __tablename__ = "price_lists"
    __table_args__ = (Index("ix_price_lists_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); currency = _text()
    lines = _jsonb(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


class DiscountScheme(Base):
    __tablename__ = "discount_schemes"
    __table_args__ = (Index("ix_discount_schemes_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); conditions = _jsonb()
    discount_pct = _num(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


# ── integrations / portal ─────────────────────────────────────────────────────
class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"
    __table_args__ = (Index("ix_webhook_subs_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); url = _text(); events = _jsonb(); secret = _text()
    is_active = _bool(True); created_at = _ts(); updated_at = _ts()
    active = _bool(True); max_attempts = _int()  # drift


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index("ix_webhook_deliveries_tenant_id", "tenant_id"),
        Index("ix_webhook_deliveries_tenant_sub", "tenant_id", "subscription_id"),
    )
    id = _pk(); tenant_id = _text(); subscription_id = _text(); event = _text()
    payload = _jsonb(); status = _text(); response_code = _int(); delivered_at = _ts()
    created_at = _ts()


class PortalUser(Base):
    __tablename__ = "portal_users"
    __table_args__ = (
        Index("ix_portal_users_tenant_id", "tenant_id"),
        Index("ix_portal_users_tenant_party", "tenant_id", "party_type", "party_id"),
    )
    id = _pk(); tenant_id = _text(); party_type = _text(); party_id = _text()
    email = Column(Text, nullable=False, unique=True); password_hash = _text()
    is_active = _bool(True); created_at = _ts(); updated_at = _ts()
    name = _text(); status = _text()  # drift


class APIKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_keys_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); key_hash = _text()
    scopes = _jsonb(); is_active = _bool(True); expires_at = _ts()
    created_at = _ts(); updated_at = _ts()
    active = _bool(True); created_by = _text(); key_prefix = _text()  # drift


# ── branches ───────────────────────────────────────────────────────────────────
class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (Index("ix_branches_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); address = _text(); gstin = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class InterBranchTransfer(Base):
    __tablename__ = "inter_branch_transfers"
    __table_args__ = (
        Index("ix_ibt_tenant_id", "tenant_id"),
        Index("ix_ibt_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); from_branch_id = _text(); to_branch_id = _text()
    transfer_no = _text(); status = _text(); lines = _jsonb(); transfer_date = _ts()
    notes = _text(); created_at = _ts(); updated_at = _ts()
    # drift: written by routers, were dropped by migration
    created_by = _text(); eway_bill_no = _text(); eway_bill_required = _bool()
    from_branch = _text(); from_branch_name = _text(); from_gstin = _text()
    in_voucher_id = _text(); items = _jsonb(); out_voucher_id = _text(); to_branch = _text()
    to_branch_name = _text(); to_gstin = _text()


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        Index("ix_budgets_tenant_id", "tenant_id"),
        Index("ix_budgets_tenant_fy", "tenant_id", "fy"),
    )
    id = _pk(); tenant_id = _text(); name = _text(); fy = _text()
    lines = _jsonb(); status = _text(); is_deleted = _bool(); deleted_at = _ts()
    created_at = _ts(); updated_at = _ts()


# ── audit / system ────────────────────────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_id", "tenant_id"),
        Index("ix_audit_logs_tenant_collection", "tenant_id", "collection"),
        Index("ix_audit_logs_tenant_doc", "tenant_id", "doc_id"),
    )
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
    __table_args__ = (
        Index("ix_report_summaries_tenant_id", "tenant_id"),
        Index("ix_report_summaries_tenant_type", "tenant_id", "report_type"),
    )
    id = _pk(); tenant_id = _text(); report_type = _text(); period = _text()
    data = _jsonb(); generated_at = _ts(); created_at = _ts()


class ReportSavedView(Base):
    __tablename__ = "report_saved_views"
    __table_args__ = (
        Index("ix_report_saved_views_tenant_id", "tenant_id"),
        Index("ix_report_saved_views_tenant_type", "tenant_id", "report_type"),
    )
    id = _pk(); tenant_id = _text(); name = _text(); report_type = _text()
    filters = _jsonb(); created_by = _text(); created_at = _ts(); updated_at = _ts()
    params = _jsonb(); slug = _text(); user_id = _text()  # drift


# ── storage / files ───────────────────────────────────────────────────────────
class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    __table_args__ = (Index("ix_uploaded_files_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); filename = _text(); original_name = _text()
    mime_type = _text(); size = _int(0); url = _text(); path = _text()
    uploaded_by = _text(); created_at = _ts()
    content_type = _text(); original_filename = _text()  # drift


class OCRDocument(Base):
    __tablename__ = "ocr_documents"
    __table_args__ = (
        Index("ix_ocr_docs_tenant_id", "tenant_id"),
        Index("ix_ocr_docs_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); file_id = _text(); status = _text()
    extracted_data = _jsonb(); ocr_provider = _text(); created_at = _ts(); updated_at = _ts()


class VerificationLog(Base):
    __tablename__ = "verification_logs"
    __table_args__ = (
        Index("ix_verification_logs_tenant_id", "tenant_id"),
        Index("ix_verification_logs_tenant_type", "tenant_id", "verification_type"),
    )
    id = _pk(); tenant_id = _text(); verification_type = _text(); identifier = _text()
    result = _jsonb(); status = _text(); provider = _text(); created_at = _ts()
    # The verification routers write Mongo-era field names (type/value/success +
    # the acting user). The migrated model originally lacked these, so the compat
    # shim silently dropped them on insert and reads returned the wrong shape
    # (KeyError 'type'/'success' in the UI/tests). Keep both name sets.
    type = _text(); value = _text(); success = _bool(); user_name = _text(); user_id = _text()


# ── AI / chat ──────────────────────────────────────────────────────────────────
class AIChatHistory(Base):
    __tablename__ = "ai_chat_history"
    __table_args__ = (
        Index("ix_ai_chat_tenant_id", "tenant_id"),
        Index("ix_ai_chat_tenant_user", "tenant_id", "user_id"),
    )
    id = _pk(); tenant_id = _text(); user_id = _text(); role = _text()
    content = _text(); created_at = _ts()


class AIConversation(Base):
    __tablename__ = "ai_conversations"
    __table_args__ = (
        Index("ix_ai_conversations_tenant_id", "tenant_id"),
        Index("ix_ai_conversations_tenant_user", "tenant_id", "user_id"),
    )
    id = _pk(); tenant_id = _text(); user_id = _text(); title = _text()
    messages = _jsonb(); created_at = _ts(); updated_at = _ts()


# ── tables missed by the initial Mongo→Postgres migration ───────────────────────
# These collections are referenced by routers but had no model, so every read
# returned empty and every write was silently swallowed by the compat shim
# (model=None → _FakeInsertResult). Columns mirror each router's Pydantic
# payload; `extra`/JSONB columns carry the nested/list fields. tenant_id +
# is_deleted/deleted_at follow the codebase's soft-delete CRUD convention.

# HR setup
class HRBranch(Base):
    __tablename__ = "hr_branches"
    __table_args__ = (Index("ix_hr_branches_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); code = _text()
    location = _text(); manager = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class HRDepartment(Base):
    __tablename__ = "hr_departments"
    __table_args__ = (
        Index("ix_hr_departments_tenant_id", "tenant_id"),
        Index("ix_hr_departments_tenant_branch", "tenant_id", "branch_id"),
    )
    id = _pk(); tenant_id = _text(); name = _text(); description = _text()
    branch_id = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class HRDesignation(Base):
    __tablename__ = "hr_designations"
    __table_args__ = (Index("ix_hr_designations_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); name = _text(); description = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


# HR payroll
class OvertimeEntry(Base):
    __tablename__ = "overtime_entries"
    __table_args__ = (
        Index("ix_overtime_tenant_id", "tenant_id"),
        Index("ix_overtime_tenant_employee", "tenant_id", "employee_id"),
    )
    id = _pk(); tenant_id = _text(); employee_id = _text(); date = _text()
    month = _text(); hours = _num(); reason = _text(); approved = _bool()
    approved_by = _text(); created_by = _text(); created_at = _ts(); updated_at = _ts()


class SalaryPayment(Base):
    __tablename__ = "salary_payments"
    __table_args__ = (
        Index("ix_salary_payments_tenant_id", "tenant_id"),
        Index("ix_salary_payments_tenant_employee", "tenant_id", "employee_id"),
    )
    id = _pk(); tenant_id = _text(); employee_id = _text(); payslip_id = _text()
    month = _text(); payment_type = _text(); amount = _num(); payment_date = _text()
    payment_mode = _text(); reference = _text(); gross_salary = _num()
    net_salary = _num(); notes = _text(); created_by = _text(); created_at = _ts()


# Banking — cheque register (distinct from PDC's cheque_transactions)
class Cheque(Base):
    __tablename__ = "cheques"
    __table_args__ = (
        Index("ix_cheques_tenant_id", "tenant_id"),
        Index("ix_cheques_tenant_status", "tenant_id", "status"),
        Index("ix_cheques_tenant_bank", "tenant_id", "bank_account_code"),
    )
    id = _pk(); tenant_id = _text(); cheque_number = _text(); bank_account_code = _text()
    cheque_type = _text(); party_name = _text(); amount = _num(); cheque_date = _text()
    due_date = _text(); status = _text(); linked_voucher_id = _text()
    remarks = _text(); cleared_date = _text(); created_by = _text()
    created_at = _ts(); updated_at = _ts()


# Cheque printing — per-bank print layout (distinct from cheque_formats)
class ChequeTemplate(Base):
    __tablename__ = "cheque_templates"
    __table_args__ = (Index("ix_cheque_templates_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); template_name = _text(); bank_name = _text()
    cheque_width_mm = _num(); cheque_height_mm = _num(); field_positions = _jsonb()
    background_image = _text(); is_active = _bool(); archived = _bool()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


# Pricing — per-godown item rate
class GodownRate(Base):
    __tablename__ = "godown_rates"
    __table_args__ = (
        Index("ix_godown_rates_tenant_id", "tenant_id"),
        Index("ix_godown_rates_tenant_item", "tenant_id", "item_id"),
    )
    id = _pk(); tenant_id = _text(); item_id = _text(); godown_id = _text()
    rate = _num()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


# Fixed assets — Income-Tax depreciation blocks
class ITBlock(Base):
    __tablename__ = "it_blocks"
    __table_args__ = (Index("ix_it_blocks_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); block_name = _text(); asset_type = _text()
    it_depreciation_rate = _num(); financial_year = _text(); effective_from = _text()
    effective_to = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


# Garment module
class BuyerOrder(Base):
    __tablename__ = "buyer_orders"
    __table_args__ = (
        Index("ix_buyer_orders_tenant_id", "tenant_id"),
        Index("ix_buyer_orders_tenant_status", "tenant_id", "status"),
    )
    id = _pk(); tenant_id = _text(); order_number = _text(); buyer_name = _text()
    style_code = _text(); delivery_date = _text(); matrix = _jsonb()
    status = _text(); notes = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class FabricTrim(Base):
    __tablename__ = "fabric_trims"
    __table_args__ = (Index("ix_fabric_trims_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); item_name = _text(); item_type = _text()
    roll_number = _text(); color = _text(); quantity = _num(); unit = _text()
    location = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class StitchingLine(Base):
    __tablename__ = "stitching_lines"
    __table_args__ = (Index("ix_stitching_lines_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); line_number = _text(); operator_count = _int()
    target_hourly_qty = _num(); actual_hourly_qty = _num()
    active_buyer_order_id = _text(); active_style = _text()
    is_deleted = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


# Integration — full-snapshot backups
class Backup(Base):
    __tablename__ = "backups"
    __table_args__ = (Index("ix_backups_tenant_id", "tenant_id"),)
    id = _pk(); tenant_id = _text(); label = _text(); collections = _jsonb()
    counts = _jsonb(); total_docs = _int(); snapshot = _jsonb()
    created_by = _text(); created_at = _ts()


# ── Debtors & Creditors (AR/AP) ────────────────────────────────────────────────

class DcLedgerEntry(Base):
    """Immutable double-entry ledger lines for debtors/creditors.

    Every document (invoice, payment, CN, DN, advance, opening balance, JV)
    that affects a party's outstanding posts one or more rows here.  Outstanding
    is always derived by summing (debit - credit); it is never stored directly.
    """
    __tablename__ = "dc_ledger_entries"
    __table_args__ = (
        Index("ix_dc_ledger_party",    "tenant_id", "party_type", "party_id"),
        Index("ix_dc_ledger_voucher",  "tenant_id", "voucher_no"),
        Index("ix_dc_ledger_doc",      "tenant_id", "source_doc_id"),
        Index("ix_dc_ledger_due_date", "tenant_id", "due_date"),
        Index("ix_dc_ledger_date",     "tenant_id", "entry_date"),
        Index("ix_dc_ledger_status",   "tenant_id", "status"),
    )
    id            = _pk()
    tenant_id     = _text()
    # party_type: "customer" | "vendor"
    party_type    = _text()
    party_id      = _text()
    party_name    = _text()
    # voucher_type: SALES_INVOICE | PURCHASE_BILL | RECEIPT | PAYMENT |
    #               CREDIT_NOTE | DEBIT_NOTE | ADVANCE_RECEIVED |
    #               ADVANCE_PAID | OPENING_BALANCE | JOURNAL
    voucher_type  = _text()
    voucher_no    = _text()
    source_doc_id = _text()   # FK to invoices/purchase_bills/vouchers etc.
    entry_date    = _text()   # ISO date
    due_date      = _text()   # ISO date (nullable for payments)
    # For debtors: invoice posts debit; receipt posts credit
    # For creditors: bill posts credit; payment posts debit
    debit         = _num()
    credit        = _num()
    narration     = _text()
    # status: OPEN | PARTIALLY_PAID | PAID | CANCELLED | OVERDUE
    status        = _text()
    branch_id     = _text()
    fiscal_year   = _text()
    is_deleted    = _bool()
    deleted_at    = _ts()
    created_by    = _text()
    created_at    = _ts()
    updated_at    = _ts()


class DcPaymentAllocation(Base):
    """Links a payment/receipt to the invoice(s) it settles (many-to-many)."""
    __tablename__ = "dc_payment_allocations"
    __table_args__ = (
        Index("ix_dc_alloc_payment",  "tenant_id", "payment_entry_id"),
        Index("ix_dc_alloc_invoice",  "tenant_id", "invoice_entry_id"),
        Index("ix_dc_alloc_party",    "tenant_id", "party_type", "party_id"),
    )
    id               = _pk()
    tenant_id        = _text()
    party_type       = _text()
    party_id         = _text()
    # Both point to dc_ledger_entries.id
    payment_entry_id = _text()
    invoice_entry_id = _text()
    allocated_amount = _num()
    tds_amount       = _num()
    discount_amount  = _num()
    round_off        = _num()
    created_at       = _ts()
    created_by       = _text()


class DcPartyBalance(Base):
    """Materialised running balance per party (updated on every ledger write).

    Used for fast dashboard aggregates and credit-limit checks.
    The source-of-truth is always dc_ledger_entries; this is a cache.
    """
    __tablename__ = "dc_party_balances"
    __table_args__ = (
        Index("ix_dc_party_balance_tenant_party", "tenant_id", "party_type", "party_id", unique=True),
    )
    id               = _pk()
    tenant_id        = _text()
    party_type       = _text()   # "customer" | "vendor"
    party_id         = _text()
    party_name       = _text()
    total_debit      = _num()
    total_credit     = _num()
    outstanding      = _num()    # = total_debit - total_credit  (positive = party owes us / we owe vendor)
    overdue_amount   = _num()
    last_txn_date    = _text()
    last_payment_date = _text()
    updated_at       = _ts()


class DcCreditLimit(Base):
    """Per-customer credit limit and terms."""
    __tablename__ = "dc_credit_limits"
    __table_args__ = (
        Index("ix_dc_credit_limits_tenant_customer", "tenant_id", "customer_id", unique=True),
    )
    id              = _pk()
    tenant_id       = _text()
    customer_id     = _text()
    credit_limit    = _num()
    payment_terms   = _int()   # days
    credit_hold     = _bool()
    notes           = _text()
    updated_by      = _text()
    updated_at      = _ts()
    created_at      = _ts()


class DcCollectionNote(Base):
    """Collection follow-up notes and reminders per party."""
    __tablename__ = "dc_collection_notes"
    __table_args__ = (
        Index("ix_dc_collection_notes_tenant_party", "tenant_id", "party_type", "party_id"),
        Index("ix_dc_collection_notes_promise_date", "tenant_id", "promise_date"),
    )
    id                   = _pk()
    tenant_id            = _text()
    party_type           = _text()
    party_id             = _text()
    party_name           = _text()
    note                 = _text()
    # reminder_type: EMAIL | WHATSAPP | SMS | CALL | VISIT
    reminder_type        = _text()
    reminder_sent_at     = _ts()
    promise_date         = _text()   # ISO date — customer's promise-to-pay date
    promise_amount       = _num()
    collection_executive = _text()
    outcome              = _text()
    is_deleted           = _bool()
    created_by           = _text()
    created_at           = _ts()
    updated_at           = _ts()


class DcReminderLog(Base):
    """History of every automated / manual reminder dispatched."""
    __tablename__ = "dc_reminder_logs"
    __table_args__ = (
        Index("ix_dc_reminder_logs_tenant_party", "tenant_id", "party_type", "party_id"),
        Index("ix_dc_reminder_logs_sent_at",      "tenant_id", "sent_at"),
    )
    id           = _pk()
    tenant_id    = _text()
    party_type   = _text()
    party_id     = _text()
    party_name   = _text()
    channel      = _text()   # EMAIL | WHATSAPP | SMS
    template     = _text()
    recipient    = _text()   # email / phone
    status       = _text()   # SENT | FAILED | PENDING
    sent_at      = _ts()
    error        = _text()
    created_by   = _text()
    created_at   = _ts()


# ── Letterhead Designer ────────────────────────────────────────────────────────

class LetterheadTemplate(Base):
    """Visual letterhead template — stores all layout, style, and element data."""
    __tablename__ = "letterhead_templates"
    __table_args__ = (
        Index("ix_letterhead_templates_tenant_id", "tenant_id"),
        Index("ix_letterhead_templates_tenant_default", "tenant_id", "is_default"),
    )
    id              = _pk()
    tenant_id       = _text()
    branch_id       = _text()          # optional branch-specific template
    template_name   = _text()
    theme           = _text()          # corporate_blue | modern_dark | luxury_gold | industrial_steel | minimal_white | executive_grey | custom
    # Page settings
    page_size       = _text()          # A4 | A4_landscape | letter
    margin_top      = _num()           # mm
    margin_bottom   = _num()
    margin_left     = _num()
    margin_right    = _num()
    header_height   = _num()           # mm
    footer_height   = _num()           # mm
    # Header layout
    logo_position   = _text()          # left | center | right
    logo_url        = _text()          # storage path
    logo2_url       = _text()          # secondary logo
    logo_width_mm   = _num()
    logo_height_mm  = _num()
    # Header elements (JSONB — list of element dicts with type/x/y/w/h/style)
    header_elements = _jsonb()
    # Footer elements
    footer_elements = _jsonb()
    # Watermark
    watermark_text  = _text()
    watermark_opacity = _num()
    watermark_angle   = _num()
    watermark_font_size = _num()
    watermark_color   = _text()
    background_image  = _text()        # storage path for background
    # Colors & typography
    primary_color   = _text()
    secondary_color = _text()
    accent_color    = _text()
    text_color      = _text()
    header_bg_color = _text()
    footer_bg_color = _text()
    font_family     = _text()          # Inter | Roboto | Helvetica | Times | Montserrat | etc.
    font_size_body  = _num()
    # Document applicability (JSONB list of doc_type strings)
    applied_to      = _jsonb()
    # Status
    is_default      = _bool()
    is_active       = _bool(True)
    version         = _int(1)
    # Metadata
    created_by      = _text()
    updated_by      = _text()
    is_deleted      = _bool(); deleted_at = _ts(); created_at = _ts(); updated_at = _ts()


class LetterheadVersion(Base):
    """Immutable snapshot of a letterhead template saved on each update."""
    __tablename__ = "letterhead_versions"
    __table_args__ = (
        Index("ix_letterhead_versions_template_id", "template_id"),
        Index("ix_letterhead_versions_tenant_id", "tenant_id"),
    )
    id              = _pk()
    tenant_id       = _text()
    template_id     = _text()          # parent letterhead_templates.id
    version         = _int(1)
    snapshot        = _jsonb()          # full template dict at this version
    changed_by      = _text()
    change_note     = _text()
    created_at      = _ts()
