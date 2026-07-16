"""Enterprise Global Search — one query, every module, Ctrl+K.

Powers the top-bar command palette. A single parametrized SQL statement
(UNION ALL across every searchable table) is sent in ONE round-trip to
Postgres, ranked by trigram similarity, and grouped into modules on the way
back out. That "one round trip" property is deliberate: this deployment's
dominant latency cost is the cross-region hop to the Supabase pooler
(~150-260ms per round trip, see core/db.py), not query planning — so the
biggest lever for a sub-200ms search is round-trip count, not clever SQL.

Design notes:
- Raw SQL via `text()` + bound params only — never string-interpolate the
  search term (SQL injection). asyncpg/SQLAlchemy sends it as a real bind
  parameter.
- Fuzzy/typo-tolerant matching: `similarity(col, :term)` (pg_trgm) OR'd with
  a plain `ILIKE '%term%'` (substring/prefix, catches short queries where
  trigram similarity is too weak to pass any reasonable threshold). Rank by
  the max similarity across a row's matched columns, best matches first.
- RBAC: each entity in _ENTITIES declares the module_permission keys that
  grant it. Branches the user can't see are dropped BEFORE the SQL is built
  (never sent to the DB, never returned to the client) — admins bypass all
  checks (`is_admin_role`).
- Every search is fire-and-forget logged to audit_logs for compliance.
"""
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from core.auth_utils import get_current_user, is_admin_role
from core.db import get_session
from core.utils import log_audit

router = APIRouter(prefix="/search", tags=["search"])

MIN_QUERY_LEN = 2
PER_ENTITY_LIMIT = 8
TOTAL_LIMIT = 60
# Below this raw ILIKE substring match still fires; trigram similarity() on
# very short strings is unreliable (e.g. "ab" vs "abc" scores low), so we
# always OR in a plain substring/prefix match too.
SIMILARITY_THRESHOLD = 0.15


class _Entity:
    """One searchable table. `select_sql` must produce exactly the columns:
    id, title, subtitle, doc_number, status, occurred_at, rank — in that order,
    aliased, so every branch of the UNION ALL lines up."""

    __slots__ = ("key", "label", "icon", "route", "select_sql", "perms")

    def __init__(self, key, label, icon, route, select_sql, perms):
        self.key = key
        self.label = label
        self.icon = icon
        self.route = route
        self.select_sql = select_sql
        self.perms = perms  # tuple of module_permission keys; any() grants access


def _match(cols: list[str]) -> str:
    """Build the WHERE clause: fuzzy trigram OR plain substring, across all
    given columns, all guarded against NULL."""
    parts = [f"{c} ILIKE :like OR similarity({c}, :term) > :thresh" for c in cols]
    return " OR ".join(f"({p})" for p in parts)


def _rank(cols: list[str]) -> str:
    exprs = ", ".join(f"similarity(coalesce({c}, ''), :term)" for c in cols)
    return f"greatest({exprs})"


# Every entity the palette can surface. `perms` keys are checked against the
# caller's module_permissions (admins bypass). Route/detail_param mirror the
# app's query-param deep-link convention (?detail=<id> opens the record modal
# on that module's list page; a handful of modules use a real /:id route).
_ENTITIES: list[_Entity] = [
    _Entity(
        "products", "Products", "package", "/products",
        f"""SELECT id, name AS title,
                   concat_ws(' | ', sku, category) AS subtitle,
                   sku AS doc_number, CASE WHEN is_deleted THEN 'ARCHIVED' ELSE 'ACTIVE' END AS status,
                   updated_at AS occurred_at, {_rank(['name', 'sku', 'hsn_code'])} AS rank
            FROM products
            WHERE coalesce(is_deleted, false) = false AND ({_match(['name', 'sku', 'hsn_code'])})""",
        ("inventory", "masters"),
    ),
    _Entity(
        "customers", "Customers", "user", "/customers",
        f"""SELECT id, name AS title,
                   concat_ws(' | ', company, phone, email) AS subtitle,
                   gstin AS doc_number, CASE WHEN is_deleted THEN 'ARCHIVED' ELSE 'ACTIVE' END AS status,
                   updated_at AS occurred_at, {_rank(['name', 'company', 'email', 'phone', 'gstin', 'pan'])} AS rank
            FROM customers
            WHERE coalesce(is_deleted, false) = false AND ({_match(['name', 'company', 'email', 'phone', 'gstin', 'pan'])})""",
        ("sales", "masters"),
    ),
    _Entity(
        "vendors", "Vendors", "truck", "/vendors",
        f"""SELECT id, name AS title,
                   concat_ws(' | ', company, phone, email) AS subtitle,
                   gstin AS doc_number, CASE WHEN is_deleted THEN 'ARCHIVED' ELSE 'ACTIVE' END AS status,
                   updated_at AS occurred_at, {_rank(['name', 'company', 'email', 'phone', 'gstin', 'pan'])} AS rank
            FROM vendors
            WHERE coalesce(is_deleted, false) = false AND ({_match(['name', 'company', 'email', 'phone', 'gstin', 'pan'])})""",
        ("purchase", "masters"),
    ),
    _Entity(
        "employees", "Employees", "users", "/hr/employees",
        f"""SELECT id, name AS title,
                   concat_ws(' | ', designation, department, phone) AS subtitle,
                   emp_code AS doc_number, coalesce(status, 'ACTIVE') AS status,
                   updated_at AS occurred_at, {_rank(['name', 'emp_code', 'email', 'phone', 'designation'])} AS rank
            FROM employees
            WHERE coalesce(is_deleted, false) = false AND ({_match(['name', 'emp_code', 'email', 'phone', 'designation'])})""",
        ("hr", "payroll"),
    ),
    _Entity(
        "leads", "Leads", "target", "/leads",
        f"""SELECT id, company_name AS title,
                   concat_ws(' | ', contact_person, phone, email) AS subtitle,
                   NULL AS doc_number, coalesce(status, 'NEW') AS status,
                   updated_at AS occurred_at, {_rank(['company_name', 'contact_person', 'email', 'phone'])} AS rank
            FROM leads
            WHERE coalesce(is_deleted, false) = false AND ({_match(['company_name', 'contact_person', 'email', 'phone'])})""",
        ("sales", "masters"),
    ),
    _Entity(
        "master_ledgers", "Ledgers", "book", "/masters/ledgers",
        f"""SELECT id, name AS title, NULL AS subtitle, NULL AS doc_number,
                   CASE WHEN is_deleted THEN 'ARCHIVED' ELSE 'ACTIVE' END AS status,
                   updated_at AS occurred_at, {_rank(['name'])} AS rank
            FROM master_ledgers
            WHERE coalesce(is_deleted, false) = false AND ({_match(['name'])})""",
        ("masters", "accounting", "ledger"),
    ),
    _Entity(
        "quotations", "Quotations", "file-text", "/quotations",
        f"""SELECT q.id, q.quotation_no AS title,
                   concat_ws(' | ', c.name, q.status) AS subtitle,
                   q.quotation_no AS doc_number, q.status AS status,
                   q.quotation_date AS occurred_at, {_rank(['q.quotation_no'])} AS rank
            FROM quotations q LEFT JOIN customers c ON c.id = q.customer_id
            WHERE {_match(['q.quotation_no'])}""",
        ("sales",),
    ),
    _Entity(
        "sales_orders", "Sales Orders", "shopping-cart", "/sales-orders",
        f"""SELECT so.id, so.so_number AS title,
                   concat_ws(' | ', c.name, so.status) AS subtitle,
                   so.so_number AS doc_number, so.status AS status,
                   so.order_date AS occurred_at, {_rank(['so.so_number'])} AS rank
            FROM sales_orders so LEFT JOIN customers c ON c.id = so.customer_id
            WHERE {_match(['so.so_number'])}""",
        ("sales",),
    ),
    _Entity(
        "invoices", "Tax Invoices", "receipt", "/invoices",
        f"""SELECT i.id, coalesce(i.invoice_number, i.invoice_no) AS title,
                   concat_ws(' | ', c.name, i.status) AS subtitle,
                   coalesce(i.invoice_number, i.invoice_no) AS doc_number, i.status AS status,
                   i.invoice_date AS occurred_at,
                   {_rank(['i.invoice_no', 'i.invoice_number'])} AS rank
            FROM invoices i LEFT JOIN customers c ON c.id = i.customer_id
            WHERE {_match(['i.invoice_no', 'i.invoice_number'])}""",
        ("sales", "accounting"),
    ),
    _Entity(
        "credit_notes", "Credit Notes", "file-minus", "/credit-notes",
        f"""SELECT cn.id, cn.cn_number AS title,
                   concat_ws(' | ', c.name, cn.status) AS subtitle,
                   cn.cn_number AS doc_number, cn.status AS status,
                   cn.cn_date AS occurred_at, {_rank(['cn.cn_number'])} AS rank
            FROM credit_notes cn LEFT JOIN customers c ON c.id = cn.customer_id
            WHERE {_match(['cn.cn_number'])}""",
        ("sales", "accounting"),
    ),
    _Entity(
        "proforma_invoices", "Proforma Invoices", "file-text", "/proforma-invoices",
        f"""SELECT pi.id, pi.pi_number AS title,
                   concat_ws(' | ', c.name, pi.status) AS subtitle,
                   pi.pi_number AS doc_number, pi.status AS status,
                   pi.pi_date AS occurred_at, {_rank(['pi.pi_number'])} AS rank
            FROM proforma_invoices pi LEFT JOIN customers c ON c.id = pi.customer_id
            WHERE {_match(['pi.pi_number'])}""",
        ("sales",),
    ),
    _Entity(
        "dispatches", "Delivery Challans", "truck", "/dispatches",
        f"""SELECT id, dispatch_no AS title, status AS subtitle,
                   dispatch_no AS doc_number, status AS status,
                   dispatch_date AS occurred_at, {_rank(['dispatch_no'])} AS rank
            FROM dispatches
            WHERE {_match(['dispatch_no'])}""",
        ("sales", "dispatch"),
    ),
    _Entity(
        "purchase_orders_v2", "Purchase Orders", "shopping-bag", "/purchase-orders-v2",
        f"""SELECT po.id, po.po_number AS title,
                   concat_ws(' | ', v.name, po.status) AS subtitle,
                   po.po_number AS doc_number, po.status AS status,
                   po.order_date AS occurred_at, {_rank(['po.po_number'])} AS rank
            FROM purchase_orders_v2 po LEFT JOIN vendors v ON v.id = po.vendor_id
            WHERE {_match(['po.po_number'])}""",
        ("purchase",),
    ),
    _Entity(
        "grn_v2", "GRNs", "package-check", "/grns",
        f"""SELECT g.id, g.grn_number AS title,
                   concat_ws(' | ', v.name, g.status) AS subtitle,
                   g.grn_number AS doc_number, g.status AS status,
                   g.receipt_date AS occurred_at, {_rank(['g.grn_number'])} AS rank
            FROM grn_v2 g LEFT JOIN vendors v ON v.id = g.vendor_id
            WHERE {_match(['g.grn_number'])}""",
        ("purchase", "inventory"),
    ),
    _Entity(
        "purchase_bills", "Purchase Invoices", "file-text", "/purchase-bills",
        f"""SELECT id, coalesce(bill_number, vendor_bill_no) AS title,
                   concat_ws(' | ', vendor_name, status) AS subtitle,
                   coalesce(bill_number, vendor_bill_no) AS doc_number, status AS status,
                   bill_date AS occurred_at,
                   {_rank(['bill_number', 'vendor_invoice_no', 'vendor_name'])} AS rank
            FROM purchase_bills
            WHERE {_match(['bill_number', 'vendor_invoice_no', 'vendor_name'])}""",
        ("purchase", "accounting"),
    ),
    _Entity(
        "vouchers", "Vouchers", "book-open", "/vouchers",
        f"""SELECT id, coalesce(voucher_number, voucher_no) AS title,
                   concat_ws(' | ', voucher_type, party_name) AS subtitle,
                   coalesce(voucher_number, voucher_no) AS doc_number, status AS status,
                   voucher_date AS occurred_at,
                   {_rank(['voucher_no', 'voucher_number', 'party_name', 'narration'])} AS rank
            FROM vouchers
            WHERE {_match(['voucher_no', 'voucher_number', 'party_name', 'narration'])}""",
        ("vouchers", "accounting", "cash_bank"),
    ),
    _Entity(
        "expense_entries", "Expenses", "credit-card", "/expenses",
        f"""SELECT id, expense_no AS title, status AS subtitle,
                   expense_no AS doc_number, status AS status,
                   expense_date AS occurred_at, {_rank(['expense_no'])} AS rank
            FROM expense_entries
            WHERE {_match(['expense_no'])}""",
        ("expenses", "accounting"),
    ),
    _Entity(
        "fixed_assets", "Fixed Assets", "box", "/fixed-assets",
        f"""SELECT id, name AS title, status AS subtitle, NULL AS doc_number,
                   status AS status, updated_at AS occurred_at, {_rank(['name'])} AS rank
            FROM fixed_assets
            WHERE coalesce(is_deleted, false) = false AND ({_match(['name'])})""",
        ("fixed_assets",),
    ),
    _Entity(
        "boms", "Bill of Materials", "layers", "/manufacturing",
        f"""SELECT id, finished_product_name AS title,
                   concat_ws(' | ', sku, version, status) AS subtitle,
                   sku AS doc_number, status AS status,
                   updated_at AS occurred_at, {_rank(['finished_product_name', 'sku'])} AS rank
            FROM boms
            WHERE coalesce(is_deleted, false) = false AND ({_match(['finished_product_name', 'sku'])})""",
        ("manufacturing",),
    ),
    _Entity(
        "work_orders", "Work Orders", "settings", "/manufacturing",
        f"""SELECT id, wo_number AS title, status AS subtitle,
                   wo_number AS doc_number, status AS status,
                   start_date AS occurred_at, {_rank(['wo_number'])} AS rank
            FROM work_orders
            WHERE {_match(['wo_number'])}""",
        ("manufacturing",),
    ),
    _Entity(
        "job_work_challans", "Job Work", "repeat", "/job-work",
        f"""SELECT id, challan_number AS title,
                   concat_ws(' | ', job_worker_name, status) AS subtitle,
                   challan_number AS doc_number, status AS status,
                   date AS occurred_at, {_rank(['challan_number', 'job_worker_name'])} AS rank
            FROM job_work_challans
            WHERE {_match(['challan_number', 'job_worker_name'])}""",
        ("manufacturing",),
    ),
    _Entity(
        "pdcs", "PDC / Cheques", "clipboard", "/banking",
        f"""SELECT id, cheque_no AS title, status AS subtitle,
                   cheque_no AS doc_number, status AS status,
                   due_date AS occurred_at, {_rank(['cheque_no'])} AS rank
            FROM pdcs
            WHERE {_match(['cheque_no'])}""",
        ("banking", "cash_bank"),
    ),
    _Entity(
        "cheque_transactions", "Cheque Printing", "printer", "/cheque-printing",
        f"""SELECT id, cheque_number AS title,
                   concat_ws(' | ', payee_name, status) AS subtitle,
                   cheque_number AS doc_number, status AS status,
                   cheque_date AS occurred_at, {_rank(['cheque_number', 'payee_name'])} AS rank
            FROM cheque_transactions
            WHERE {_match(['cheque_number', 'payee_name'])}""",
        ("cheque_print", "banking"),
    ),
    _Entity(
        "projects", "Projects", "folder", "/projects",
        f"""SELECT p.id, p.name AS title,
                   concat_ws(' | ', c.name, p.status) AS subtitle,
                   NULL AS doc_number, p.status AS status,
                   p.updated_at AS occurred_at, {_rank(['p.name'])} AS rank
            FROM projects p LEFT JOIN customers c ON c.id = p.customer_id
            WHERE coalesce(p.is_deleted, false) = false AND ({_match(['p.name'])})""",
        ("projects", "accounting", "sales"),
    ),
]

# Deep-link routes whose list page reads `?q=` to pre-filter (rather than the
# default `?detail=<id>` record-modal convention).
_Q_AWARE_ROUTES = {"/products", "/hr/employees", "/masters/ledgers", "/vendors"}
_DETAIL_AWARE_ROUTES = {"/vendors", "/customers", "/products", "/masters/ledgers"}
# job-work challans have a real /:id route rather than a query-param deep link.
_ID_ROUTE_OVERRIDES = {"job_work_challans": "/job-work/challans/{id}"}


def _visible_entities(user: dict) -> list[_Entity]:
    if is_admin_role(user.get("role")):
        return _ENTITIES
    perms = set(user.get("module_permissions") or [])
    return [e for e in _ENTITIES if perms.intersection(e.perms)]


def _build_path(entity: _Entity, row_id: str, title: str) -> str:
    override = _ID_ROUTE_OVERRIDES.get(entity.key)
    if override:
        return override.format(id=row_id)
    if entity.route in _DETAIL_AWARE_ROUTES:
        return f"{entity.route}?detail={row_id}"
    if entity.route in _Q_AWARE_ROUTES and title:
        return f"{entity.route}?q={title}"
    return entity.route


@router.get("")
async def global_search(request: Request, q: Optional[str] = None, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Search every ERP module in one round-trip. Grouped by module, ranked by
    fuzzy match quality, capped per-module and overall."""
    query = (q or "").strip()
    if len(query) < MIN_QUERY_LEN:
        return {"query": query, "groups": {}, "count": 0, "took_ms": 0}

    started = time.perf_counter()
    entities = _visible_entities(user)
    if not entities:
        return {"query": query, "groups": {}, "count": 0, "took_ms": 0}

    params = {"term": query, "like": f"%{query}%", "thresh": SIMILARITY_THRESHOLD}
    branches = []
    for e in entities:
        # Each branch's own ORDER BY/LIMIT must be parenthesized as a derived
        # table — an unparenthesized ORDER BY/LIMIT after a UNION ALL member
        # binds to the WHOLE union, not that member, and is a syntax error
        # anywhere but the final branch.
        branches.append(
            f"(SELECT '{e.key}' AS entity, id, title, subtitle, doc_number, status, "
            f"occurred_at, rank FROM ({e.select_sql}) t_{e.key} "
            f"ORDER BY rank DESC LIMIT {PER_ENTITY_LIMIT})"
        )
    sql = " UNION ALL ".join(branches) + f" ORDER BY rank DESC LIMIT {TOTAL_LIMIT}"

    try:
        async with get_session() as session:
            rows = (await session.execute(text(sql), params)).mappings().all()
    except Exception:
        # A bad column/table in any one branch must not 500 the whole palette;
        # degrade to empty results rather than break every page's search box.
        return {"query": query, "groups": {}, "count": 0, "took_ms": 0, "error": "search_unavailable"}

    by_key = {e.key: e for e in entities}
    groups: dict[str, list[dict]] = {}
    total = 0
    for row in rows:
        entity = by_key.get(row["entity"])
        if entity is None:
            continue
        title = str(row["title"] or "—")
        hit = {
            "id": row["id"],
            "title": title,
            "subtitle": row["subtitle"] or "",
            "docNumber": row["doc_number"],
            "status": row["status"],
            "date": row["occurred_at"].isoformat() if hasattr(row["occurred_at"], "isoformat") else row["occurred_at"],
            "module": entity.label,
            "icon": entity.icon,
            "path": _build_path(entity, row["id"], title),
        }
        groups.setdefault(entity.key, []).append(hit)
        total += 1

    took_ms = round((time.perf_counter() - started) * 1000, 1)

    # Fire-and-forget audit trail (never block/break the search response on
    # a logging failure — auditing must not be able to take the palette down).
    try:
        await log_audit(
            "SEARCH", "global_search", None, user,
            new_values={"query": query, "result_count": total},
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except Exception:
        pass

    return {"query": query, "groups": groups, "count": total, "took_ms": took_ms}


@router.get("/modules")
async def search_modules(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Module metadata (label/icon) for the entities this user can search —
    lets the frontend render empty-state group chips before any query runs."""
    entities = _visible_entities(user)
    return {
        "modules": [
            {"key": e.key, "label": e.label, "icon": e.icon} for e in entities
        ]
    }
