import { NavLink, useNavigate, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Boxes,
  Warehouse,
  Truck,
  Users,
  UserSquare,
  ShoppingCart,
  FileText,
  Receipt,
  TrendingUp,
  Building2,
  PackageSearch,
  LogOut,
  ScrollText,
  UsersRound,
  Hammer,
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
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const ERP_NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, exact: true, roles: ["admin", "hr", "accountant", "employee"] },
  { section: "INVENTORY", roles: ["admin", "accountant"] },
  { to: "/products", label: "Products", icon: Boxes, roles: ["admin", "accountant"] },
  { to: "/warehouses", label: "Warehouses", icon: Warehouse, roles: ["admin", "accountant"] },
  { to: "/stock-log", label: "Stock Log", icon: PackageSearch, roles: ["admin", "accountant"] },
  { to: "/job-work", label: "Job Work Outsource", icon: Hammer, roles: ["admin", "accountant"] },
  { to: "/manufacturing", label: "Manufacturing", icon: Factory, roles: ["admin", "accountant"] },
  { to: "/stock-items", label: "Stock Items", icon: Boxes, roles: ["admin", "accountant"] },
  { to: "/godowns", label: "Godowns", icon: Warehouse, roles: ["admin", "accountant"] },
  { to: "/stock-transfers", label: "Stock Transfers", icon: Truck, roles: ["admin", "accountant"] },
  { to: "/inventory-reports", label: "Inventory Reports", icon: PackageSearch, roles: ["admin", "accountant"] },
  { section: "PURCHASE", roles: ["admin", "accountant"] },
  { to: "/suppliers", label: "Suppliers", icon: Building2, roles: ["admin", "accountant"] },
  { to: "/purchase-orders", label: "Purchase Orders", icon: ShoppingCart, roles: ["admin", "accountant"] },
  { to: "/vendors", label: "Vendors", icon: Building2, roles: ["admin", "accountant"] },
  { to: "/purchase-orders-v2", label: "Purchase Orders (v2)", icon: ShoppingCart, roles: ["admin", "accountant"] },
  { to: "/grns", label: "Goods Receipt", icon: PackageSearch, roles: ["admin", "accountant"] },
  { to: "/purchase-bills", label: "Purchase Bills", icon: Receipt, roles: ["admin", "accountant"] },
  { to: "/purchase-returns", label: "Purchase Returns", icon: FileText, roles: ["admin", "accountant"] },
  { section: "SALES & ERP", roles: ["admin", "accountant"] },
  { to: "/customers", label: "Customers", icon: UsersRound, roles: ["admin", "accountant"] },
  { to: "/leads", label: "Leads / CRM", icon: UserSquare, roles: ["admin", "accountant"] },
  { to: "/quotations", label: "Quotations", icon: ScrollText, roles: ["admin", "accountant"] },
  { to: "/sales-orders", label: "Sales Orders", icon: FileText, roles: ["admin", "accountant"] },
  { to: "/invoices", label: "GST Invoices", icon: Receipt, roles: ["admin", "accountant"] },
  { to: "/proforma-invoices", label: "Proforma Invoices", icon: FileText, roles: ["admin", "accountant"] },
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
  { to: "/banking", label: "Banking & PDC", icon: Banknote, roles: ["admin", "accountant"] },
  { to: "/approvals", label: "Approvals & Workflow", icon: CheckCircle2, roles: ["admin", "accountant", "hr"] },
  { to: "/projects", label: "Project Costing", icon: FolderKanban, roles: ["admin", "accountant"] },
];

const HR_NAV = [
  { section: "HR & PAYROLL", roles: ["admin", "hr", "accountant"] },
  { to: "/hr", label: "HR Dashboard", icon: Briefcase, roles: ["admin", "hr", "accountant"] },
  { to: "/hr/employees", label: "Employees", icon: Users, roles: ["admin", "hr"] },
  { to: "/hr/attendance", label: "Attendance", icon: Clock, roles: ["admin", "hr"] },
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
  { to: "/masters/stock-items", label: "Stock Items", icon: PackageSearch, roles: ["admin", "accountant"] },
  { to: "/masters/units", label: "Units of Measure", icon: Scale, roles: ["admin", "accountant"] },
  { to: "/masters/locations", label: "Locations / Godowns", icon: Warehouse, roles: ["admin", "accountant"] },
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
  { to: "/email-log", label: "Email Log", icon: Mail, roles: ["admin"] },
  { to: "/admin/company-master", label: "Company Profile", icon: Building2, roles: ["admin"] },
  { to: "/integration", label: "Data & Integration", icon: DatabaseZap, roles: ["admin"] },
  { to: "/branches", label: "Branches & Multi-location", icon: Network, roles: ["admin", "accountant"] },
];


const EMPLOYEE_NAV = [
  { section: "MY ACCOUNT", roles: ["employee"] },
  { to: "/my-portal", label: "My Portal", icon: UserCircle, roles: ["employee"] },
];

const ALL = [...ERP_NAV, ...MASTERS_NAV, ...STATUTORY_NAV, ...FINANCE_NAV, ...HR_NAV, ...INSIGHTS_NAV, ...EMPLOYEE_NAV, ...SYSTEM_NAV];


function visible(item, role) {
  return item.roles ? item.roles.includes(role) : true;
}

export default function Sidebar({ open, onClose }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const role = user?.role || "employee";

  return (
    <aside
      data-testid="app-sidebar"
      className="h-full w-full bg-[hsl(var(--sidebar-background))] border-r border-[hsl(var(--sidebar-border))] text-[hsl(var(--sidebar-foreground))] flex flex-col"
    >
      <div className="border-b border-[hsl(var(--sidebar-border))] px-5 py-5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-primary flex items-center justify-center text-primary-foreground" style={{ borderRadius: "var(--radius)" }}>
            <Hammer className="w-5 h-5 text-primary-foreground" strokeWidth={2.5} />
          </div>
          <div>
            <div className="font-display font-black text-[hsl(var(--sidebar-foreground))] text-base leading-tight tracking-tight">
              GravityOne
            </div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-primary">
              ERP Platform
            </div>
          </div>
        </div>
        <div className="mt-3 hazard-stripe h-1.5 w-full" />
      </div>

      <nav className="flex-1 overflow-y-auto py-3">
        {ALL.filter((it) => visible(it, role)).map((item, i) => {
          if (item.section) {
            return (
              <div key={`s-${i}-${item.section}`} className="px-5 pt-4 pb-2 label-overline">
                {item.section}
              </div>
            );
          }
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.exact}
              data-testid={`nav-${item.to.replace(/^\//, "").replace(/\//g, "-").replace(/\?/, "-").replace(/=/, "-") || "dashboard"}`}
              onClick={onClose}
              className={({ isActive }) => {
                const isItActive = item.to.includes("?")
                  ? (location.pathname + location.search) === item.to
                  : isActive && !location.search;
                return `relative flex items-center gap-3 px-5 py-2.5 text-sm font-medium transition-colors duration-100 ${
                  isItActive
                    ? "bg-primary/10 text-primary border-l-4 border-primary pl-4"
                    : "text-zinc-400 hover:text-zinc-50 hover:bg-primary/5 border-l-4 border-transparent"
                }`;
              }}
            >
              <Icon className="w-4 h-4" strokeWidth={2} />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="border-t border-[hsl(var(--sidebar-border))] p-4">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-9 h-9 bg-primary text-primary-foreground font-display font-black flex items-center justify-center" style={{ borderRadius: "var(--radius)" }}>
            {user?.name?.[0]?.toUpperCase() || "?"}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-[hsl(var(--sidebar-foreground))] truncate">
              {user?.name || "—"}
            </div>
            <div className="font-mono text-[10px] uppercase tracking-wider text-zinc-500">
              {user?.role}
            </div>
          </div>
        </div>
        <button
          data-testid="logout-btn"
          onClick={async () => {
            try {
              await logout();
            } catch (_) {
              // proceed to login regardless
            }
            navigate("/login");
          }}
          className="w-full flex items-center justify-center gap-2 border border-[hsl(var(--sidebar-border))] hover:border-primary hover:text-primary text-[hsl(var(--sidebar-foreground))] text-sm font-mono uppercase tracking-wider py-2 transition-colors opacity-80 hover:opacity-100"
          style={{ borderRadius: "var(--radius)" }}
        >
          <LogOut className="w-4 h-4" /> Sign out
        </button>
      </div>
    </aside>
  );
}
