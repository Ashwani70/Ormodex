/**
 * Canonical ERP navigation list.
 *
 * Single source of truth for both the sidebar AND the Ctrl+K global-search
 * "Pages" results, so every module that appears in the menu is also searchable
 * (they used to drift: search matched a short hardcoded list and silently
 * omitted most modules).
 *
 * Each item is either a section header (`{ section, roles }`) or a link
 * (`{ to, label, icon, roles, exact? }`). `roles` gates visibility per user role.
 */
import {
  LayoutDashboard,
  Boxes,
  Warehouse,
  Truck,
  Users,
  UserSquare,
  Hammer,
  ShoppingCart,
  FileText,
  Receipt,
  TrendingUp,
  Building2,
  PackageSearch,
  ScrollText,
  UsersRound,
  Mail,
  CalendarDays,
  IndianRupee,
  Briefcase,
  Settings,
  Clock,
  UserCircle,
  BookOpen,
  Shield,
  CreditCard,
  Landmark,
  FileSpreadsheet,
  BarChart2,
  Bot,
  Scale,
  Palette,
  Fingerprint,
  Factory,
  Target,
  Banknote,
  Building,
  CheckCircle2,
  Tags,
  FolderKanban,
  ScanLine,
  DatabaseZap,
  Network,
  DollarSign,
  ClipboardList,
  ArrowDownToLine,
  Hash,
} from "lucide-react";

const ERP_NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, exact: true, roles: ["admin", "hr", "accountant", "employee"] },
  { section: "INVENTORY", roles: ["admin", "accountant"] },
  { to: "/products", label: "Products", icon: Boxes, roles: ["admin", "accountant"] },
  { to: "/categories", label: "Categories", icon: Tags, roles: ["admin", "accountant"] },
  { to: "/stock-log", label: "Stock Log", icon: PackageSearch, roles: ["admin", "accountant"] },
  { to: "/job-work", label: "Job Work", icon: Hammer, roles: ["admin", "accountant"], exact: true },
  { to: "/job-work/challans/new", label: "Job Work Challan", icon: FileText, roles: ["admin", "accountant"] },
  { to: "/job-work/receipts/new", label: "Job Work Receipt", icon: ArrowDownToLine, roles: ["admin", "accountant"] },
  { to: "/job-work/reports", label: "Job Work Reports", icon: ClipboardList, roles: ["admin", "accountant"] },
  { to: "/manufacturing", label: "Manufacturing", icon: Factory, roles: ["admin", "accountant"] },
  { to: "/godowns", label: "Warehouses", icon: Warehouse, roles: ["admin", "accountant"] },
  { to: "/stock-transfers", label: "Stock Transfers", icon: Truck, roles: ["admin", "accountant"] },
  { to: "/inventory-reports", label: "Inventory Reports", icon: PackageSearch, roles: ["admin", "accountant"] },
  { section: "PURCHASE", roles: ["admin", "accountant"] },
  { to: "/vendors", label: "Vendors", icon: Building2, roles: ["admin", "accountant"] },
  { to: "/purchase-orders-v2", label: "Purchase Orders", icon: ShoppingCart, roles: ["admin", "accountant"] },
  { to: "/grns", label: "Goods Receipt", icon: PackageSearch, roles: ["admin", "accountant"] },
  { to: "/purchase-bills", label: "Purchase Bills", icon: Receipt, roles: ["admin", "accountant"] },
  { to: "/purchase-returns", label: "Purchase Returns", icon: FileText, roles: ["admin", "accountant"] },
  { section: "SALES & ERP", roles: ["admin", "accountant"] },
  { to: "/customers", label: "Customers", icon: UsersRound, roles: ["admin", "accountant"] },
  { to: "/leads", label: "Leads / CRM", icon: UserSquare, roles: ["admin", "accountant"] },
  { to: "/quotations", label: "Quotations", icon: ScrollText, roles: ["admin", "accountant"] },
  { to: "/sales-orders", label: "Sales Orders", icon: FileText, roles: ["admin", "accountant"] },
  { to: "/invoices", label: "GST Invoices", icon: Receipt, roles: ["admin", "accountant"] },
  { to: "/credit-notes", label: "Credit Notes", icon: FileText, roles: ["admin", "accountant"] },
  { to: "/proforma-invoices", label: "Proforma Invoices", icon: FileText, roles: ["admin"] },
  { to: "/dispatches", label: "Dispatches", icon: Truck, roles: ["admin", "accountant"] },
  { to: "/pricing", label: "Pricing & Schemes", icon: Tags, roles: ["admin", "accountant"] },
  { to: "/pos", label: "POS Counter", icon: ScanLine, roles: ["admin", "accountant"] },
];

const FINANCE_NAV = [
  { section: "FINANCE & ACCOUNTING", roles: ["admin", "accountant"] },
  { to: "/accounting", label: "Accounting", icon: BookOpen, roles: ["admin", "accountant"] },
  { to: "/accounting?tab=daybook", label: "Day Book", icon: BookOpen, roles: ["admin", "accountant"] },
  { to: "/accounting?tab=cashflow", label: "Cash Flow", icon: DollarSign, roles: ["admin", "accountant"] },
  { to: "/accounting?tab=interest", label: "Interest Outstanding", icon: Scale, roles: ["admin", "accountant"] },
  { to: "/gst", label: "GST Accounting", icon: Shield, roles: ["admin", "accountant"] },
  { to: "/verifications", label: "Verifications", icon: Fingerprint, roles: ["admin", "accountant", "hr"] },
  { to: "/expenses", label: "Expenses", icon: CreditCard, roles: ["admin", "accountant", "hr"] },
  { to: "/ledger", label: "Ledger & Bank", icon: Landmark, roles: ["admin", "accountant"] },
  { to: "/vouchers", label: "Vouchers", icon: Scale, roles: ["admin", "accountant"] },
  { to: "/budget", label: "Budget & Cost Centers", icon: Target, roles: ["admin", "accountant"] },
  { to: "/fixed-assets", label: "Fixed Assets", icon: Building, roles: ["admin", "accountant"] },
  { to: "/debtors-creditors", label: "Debtors & Creditors", icon: Scale, roles: ["admin", "accountant"] },
  { to: "/banking", label: "Banking & PDC", icon: Banknote, roles: ["admin", "accountant"] },
  { to: "/cheque-printing", label: "Cheque Printing", icon: Banknote, roles: ["admin", "accountant"] },
  { to: "/letterhead-designer", label: "Letterhead Designer", icon: FileText, roles: ["admin", "accountant"] },
  { to: "/approvals", label: "Approvals & Workflow", icon: CheckCircle2, roles: ["admin", "accountant", "hr"] },
  { to: "/projects", label: "Project Costing", icon: FolderKanban, roles: ["admin", "accountant"] },
];

const HR_NAV = [
  { section: "HR & PAYROLL", roles: ["admin", "hr", "accountant"] },
  { to: "/hr", label: "HR Dashboard", icon: Briefcase, roles: ["admin", "hr", "accountant"] },
  { to: "/hr/employees", label: "Employees", icon: Users, roles: ["admin", "hr"] },
  { to: "/hr/attendance", label: "Attendance", icon: Clock, roles: ["admin", "hr"] },
  { to: "/hr/biometric", label: "Biometric Attendance", icon: Fingerprint, roles: ["admin", "hr"] },
  { to: "/hr/leaves", label: "Leaves", icon: CalendarDays, roles: ["admin", "hr"] },
  { to: "/hr/payroll", label: "Payroll", icon: IndianRupee, roles: ["admin", "hr", "accountant"] },
  { to: "/hr/settings", label: "HR Settings", icon: Settings, roles: ["admin", "hr"] },
];

const INSIGHTS_NAV = [
  { section: "ANALYTICS", roles: ["admin", "accountant"] },
  { to: "/reports", label: "Reports", icon: TrendingUp, roles: ["admin", "accountant"] },
  { to: "/reports-deep", label: "Financial Reports", icon: BarChart2, roles: ["admin", "accountant"] },
  { to: "/mis-reports", label: "MIS Reports", icon: BarChart2, roles: ["admin", "accountant"] },
  { to: "/ai-assistant", label: "Gravity AI", icon: Bot, roles: ["admin", "accountant", "hr"] },
];

const MASTERS_NAV = [
  { section: "MASTERS", roles: ["admin", "accountant"] },
  { to: "/masters/groups", label: "Account Groups", icon: BookOpen, roles: ["admin", "accountant"] },
  { to: "/masters/ledgers", label: "Ledgers", icon: Landmark, roles: ["admin", "accountant"] },
  { to: "/masters/currencies", label: "Currencies", icon: IndianRupee, roles: ["admin", "accountant"] },
  { to: "/masters/rates", label: "Rates of Exchange", icon: Scale, roles: ["admin", "accountant"] },
  { to: "/masters/voucher-types", label: "Voucher Types", icon: FileText, roles: ["admin", "accountant"] },
  { to: "/masters/stock-groups", label: "Stock Groups", icon: Boxes, roles: ["admin", "accountant"] },
  { to: "/masters/stock-categories", label: "Stock Categories", icon: Tags, roles: ["admin", "accountant"] },
  { to: "/masters/units", label: "Units of Measure", icon: Scale, roles: ["admin", "accountant"] },
  { to: "/masters/locations", label: "Locations / Warehouses", icon: Warehouse, roles: ["admin", "accountant"] },
];

const STATUTORY_NAV = [
  { section: "STATUTORY", roles: ["admin", "accountant"] },
  { to: "/masters/gst-registrations", label: "GST Registrations", icon: Shield, roles: ["admin", "accountant"] },
  { to: "/masters/gst-classifications", label: "GST Classifications", icon: FileSpreadsheet, roles: ["admin", "accountant"] },
  { to: "/masters/tds-nature-of-payment", label: "TDS Nature of Payment", icon: Scale, roles: ["admin", "accountant"] },
  { to: "/masters/tcs-nature-of-goods", label: "TCS Nature of Goods", icon: Scale, roles: ["admin", "accountant"] },
  { to: "/masters/company-gst-details", label: "Company GST Details", icon: Building2, roles: ["admin", "accountant"] },
  { to: "/masters/tds-details", label: "TDS Details", icon: Fingerprint, roles: ["admin", "accountant"] },
  { to: "/masters/tcs-details", label: "TCS Details", icon: Fingerprint, roles: ["admin", "accountant"] },
  { to: "/masters/pan-cin-details", label: "PAN / CIN Details", icon: Fingerprint, roles: ["admin", "accountant"] },
];

const SYSTEM_NAV = [
  { section: "SYSTEM", roles: ["admin"] },
  { to: "/users", label: "Users", icon: Users, roles: ["admin"] },
  { to: "/admin/company-master", label: "Company Profile", icon: Building2, roles: ["admin"] },
  { to: "/admin/po-numbering", label: "PO Numbering", icon: FileText, roles: ["admin"] },
  { to: "/admin/document-numbering", label: "Document Numbering", icon: Hash, roles: ["admin"] },
  { to: "/integration", label: "Data & Integration", icon: DatabaseZap, roles: ["admin"] },
  { to: "/branches", label: "Branches & Multi-location", icon: Network, roles: ["admin", "accountant"] },
  { to: "/design-system", label: "Design System", icon: Palette, roles: ["admin"] },
];

const EMPLOYEE_NAV = [
  { section: "MY ACCOUNT", roles: ["employee"] },
  { to: "/my-portal", label: "My Portal", icon: UserCircle, roles: ["employee"] },
];

// Flat, ordered list rendered by the sidebar (sections + links interleaved).
export const ALL_NAV_ITEMS = [
  ...ERP_NAV, ...MASTERS_NAV, ...STATUTORY_NAV, ...FINANCE_NAV,
  ...HR_NAV, ...INSIGHTS_NAV, ...EMPLOYEE_NAV, ...SYSTEM_NAV,
];

// super_admin is a full alias of admin for every authorization check in this
// app (frontend nav visibility and route guards, backend router guards) —
// see backend/core/auth_utils.py's is_admin_role for the server-side twin.
export function isAdminRole(role) {
  return role === "admin" || role === "super_admin";
}

/** True if an item (section or link) is visible to the given user or role. */
export function isVisibleToRole(item, userOrRole) {
  const user = typeof userOrRole === "string" ? { role: userOrRole, module_permissions: [] } : userOrRole;
  if (!user) return false;
  const role = user.role || "employee";
  if (isAdminRole(role)) return true;

  // 1. Role-based check
  const hasRole = item.roles ? item.roles.includes(role) : true;
  if (hasRole) return true;

  // 2. Permission-based check (if role check failed, see if they have the specific module permission)
  const permissions = user.module_permissions || [];
  if (item.to) {
    const path = item.to;
    if (path.startsWith("/hr/payroll") && permissions.includes("payroll")) return true;
    if (path.startsWith("/hr") && permissions.includes("hr")) return true;
    if (path.startsWith("/products") && permissions.includes("inventory")) return true;
    if (path.startsWith("/categories") && permissions.includes("inventory")) return true;
    if (path.startsWith("/stock-log") && permissions.includes("inventory")) return true;
    if (path.startsWith("/job-work") && permissions.includes("inventory")) return true;
    if (path.startsWith("/manufacturing") && permissions.includes("inventory")) return true;
    if (path.startsWith("/godowns") && permissions.includes("inventory")) return true;
    if (path.startsWith("/stock-transfers") && permissions.includes("inventory")) return true;
    if (path.startsWith("/inventory-reports") && permissions.includes("inventory")) return true;
    if (path.startsWith("/vendors") && permissions.includes("purchase")) return true;
    if (path.startsWith("/purchase-orders") && permissions.includes("purchase")) return true;
    if (path.startsWith("/grns") && permissions.includes("purchase")) return true;
    if (path.startsWith("/purchase-bills") && permissions.includes("purchase")) return true;
    if (path.startsWith("/purchase-returns") && permissions.includes("purchase")) return true;
    if (path.startsWith("/customers") && permissions.includes("sales")) return true;
    if (path.startsWith("/leads") && permissions.includes("sales")) return true;
    if (path.startsWith("/quotations") && permissions.includes("sales")) return true;
    if (path.startsWith("/sales-orders") && permissions.includes("sales")) return true;
    if (path.startsWith("/invoices") && permissions.includes("sales")) return true;
    if (path.startsWith("/credit-notes") && permissions.includes("sales")) return true;
    if (path.startsWith("/dispatches") && permissions.includes("sales")) return true;
    if (path.startsWith("/pricing") && permissions.includes("sales")) return true;
    if (path.startsWith("/pos") && permissions.includes("pos")) return true;
    if (path.startsWith("/accounting") && permissions.includes("accounting")) return true;
    if (path.startsWith("/gst") && permissions.includes("gst")) return true;
    if (path.startsWith("/expenses") && permissions.includes("expenses")) return true;
    if (path.startsWith("/ledger") && permissions.includes("ledger")) return true;
    if (path.startsWith("/vouchers") && permissions.includes("vouchers")) return true;
    if (path.startsWith("/budget") && permissions.includes("accounting")) return true;
    if (path.startsWith("/fixed-assets") && permissions.includes("fixed_assets")) return true;
    if (path.startsWith("/debtors-creditors") && permissions.includes("ledger")) return true;
    if (path.startsWith("/banking") && permissions.includes("banking")) return true;
    if (path.startsWith("/cheque-printing") && permissions.includes("cheque_print")) return true;
    if (path.startsWith("/letterhead") && permissions.includes("letterhead_design")) return true;
    if (path.startsWith("/approvals") && permissions.includes("approver")) return true;
    if (path.startsWith("/projects") && permissions.includes("projects")) return true;
    if (path.startsWith("/reports-deep") && permissions.includes("reports")) return true;
    if (path.startsWith("/reports") && permissions.includes("reports")) return true;
    if (path.startsWith("/mis-reports") && permissions.includes("mis_reports")) return true;
    if (path.startsWith("/ai-assistant") && permissions.includes("ai_tools")) return true;
  }

  // 3. Section header check
  if (item.section) {
    const sec = item.section.toUpperCase();
    if (sec === "INVENTORY" && permissions.includes("inventory")) return true;
    if (sec === "PURCHASE" && permissions.includes("purchase")) return true;
    if ((sec === "SALES & ERP" || sec === "SALES") && permissions.includes("sales")) return true;
    if (sec === "FINANCE & ACCOUNTING" && (permissions.includes("accounting") || permissions.includes("ledger"))) return true;
    if (sec === "HR & PAYROLL" && (permissions.includes("hr") || permissions.includes("payroll"))) return true;
    if (sec === "ANALYTICS" && (permissions.includes("reports") || permissions.includes("mis_reports"))) return true;
  }

  return false;
}

/**
 * The user-visible navigable pages (no section headers), shaped for the global
 * search palette. This matches searchable pages based on role/module permissions.
 */
export function searchablePages(userOrRole) {
  const user = typeof userOrRole === "string" ? { role: userOrRole, module_permissions: [] } : userOrRole;
  return ALL_NAV_ITEMS
    .filter((it) => it.to && isVisibleToRole(it, user))
    .map((it) => ({ label: it.label, path: it.to, icon: it.icon }));
}
