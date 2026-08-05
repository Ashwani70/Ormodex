import "@/App.css";
import { lazy, Suspense, useEffect } from "react";
import api from "@/lib/api";
import { BrowserRouter, HashRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/context/AuthContext";
import { ModalStackProvider } from "@/context/ModalStackContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";
import ErrorBoundary from "@/components/ErrorBoundary";
// ThemeSettings exports applyTheme which is called at startup (not route-load),
// so it must remain an eager import.
import { applyTheme } from "@/pages/ThemeSettings";

// ── Lazy page imports ────────────────────────────────────────────────────────
// Each page is code-split into its own chunk. The initial JS bundle only
// includes the shell (Layout, AuthProvider, routing); each page's JS loads
// on first navigation, cutting initial bundle from ~2 MB to ~120 KB and
// first-paint from ~4-8 s to <1 s on a cold load.
const lazy_ = (path) => lazy(() => import(`@/pages/${path}`));

const Login               = lazy_("Login");
const ResetPassword       = lazy_("ResetPassword");
const Dashboard           = lazy_("Dashboard");
const Products            = lazy_("Products");
const Categories          = lazy_("Categories");
const Warehouses          = lazy_("Warehouses");
const StockLog            = lazy_("StockLog");
const PurchaseOrders      = lazy_("PurchaseOrders");
const Customers           = lazy_("Customers");
const Leads               = lazy_("Leads");
const Quotations          = lazy_("Quotations");
const SalesOrders         = lazy_("SalesOrders");
const Invoices            = lazy_("Invoices");
const CreditNotes         = lazy_("CreditNotes");
const Dispatches          = lazy_("Dispatches");
const ProformaInvoices    = lazy_("ProformaInvoices");
const Reports             = lazy_("Reports");
const Users               = lazy_("Users");
const HrDashboard         = lazy_("HrDashboard");
const Employees           = lazy_("Employees");
const HrSettings          = lazy_("HrSettings");
const Attendance          = lazy_("Attendance");
const BiometricAttendance = lazy_("BiometricAttendance");
const HrLeaves            = lazy_("HrLeaves");
const Payroll             = lazy_("Payroll");
const MyPortal            = lazy_("MyPortal");
const QrCheckIn           = lazy_("QrCheckIn");
const PayslipShare        = lazy_("PayslipShare");
const Accounting          = lazy_("Accounting");
const GstAccounting       = lazy_("GstAccounting");
const Expenses            = lazy_("Expenses");
const LedgerBank          = lazy_("LedgerBank");
const Vouchers            = lazy_("Vouchers");
const MisReports          = lazy_("MisReports");
const AiAssistant         = lazy_("AiAssistant");
const ThemeSettings       = lazy_("ThemeSettings");
const PoNumberingSettings = lazy_("PoNumberingSettings");
const DocumentNumberingSettings = lazy_("DocumentNumberingSettings");
const CompanyMaster       = lazy_("CompanyMaster");
const JobWork             = lazy_("JobWork");
const JobWorkDashboard    = lazy_("JobWorkDashboard");
const JobWorkChallan      = lazy_("JobWorkChallan");
const JobWorkReceipt      = lazy_("JobWorkReceipt");
const JobWorkReports      = lazy_("JobWorkReports");
const VerificationDashboard = lazy_("VerificationDashboard");
const ApiSettings         = lazy_("ApiSettings");
const Manufacturing       = lazy_("Manufacturing");
const Budget              = lazy_("Budget");
const FixedAssets         = lazy_("FixedAssets");
const Banking             = lazy_("Banking");
const ChequePrinting      = lazy_("ChequePrinting");
const Approvals           = lazy_("Approvals");
const ReportsDeep         = lazy_("ReportsDeep");
const Pricing             = lazy_("Pricing");
const Portal              = lazy_("Portal");
const Projects            = lazy_("Projects");
const POS                 = lazy_("POS");
const Integration         = lazy_("Integration");
const Branches            = lazy_("Branches");
const StockItems          = lazy_("StockItems");
const Godowns             = lazy_("Godowns");
const StockTransfers      = lazy_("StockTransfers");
const InventoryReports    = lazy_("InventoryReports");
const Vendors             = lazy_("Vendors");
const PurchaseOrdersV2    = lazy_("PurchaseOrdersV2");
const GRNs                = lazy_("GRNs");
const PurchaseBills       = lazy_("PurchaseBills");
const PurchaseReturns     = lazy_("PurchaseReturns");
const MastersPage         = lazy_("MastersPage");
const DesignSystem        = lazy_("DesignSystem");
const DebtorsCreditors    = lazy_("DebtorsCreditors");
const LetterheadDesigner  = lazy_("LetterheadDesigner");
const Profile             = lazy_("Profile");

// Minimal spinner shown while a lazy chunk is loading (typically <200ms on a
// warm CDN). Matches the app background so there's no flash of white.
function PageLoader() {
  return (
    <div className="flex items-center justify-center h-screen bg-background">
      <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

function App() {
  // Apply theme from localStorage instantly on load, then sync with DB
  useEffect(() => {
    const saved = localStorage.getItem("gew_theme_settings");
    if (saved) {
      try {
        applyTheme(JSON.parse(saved));
      } catch (e) {}
    }

    api.get("/theme-settings/active")
      .then((res) => {
        applyTheme(res.data);
        localStorage.setItem("gew_theme_settings", JSON.stringify(res.data));
      })
      .catch(() => {});
  }, []);

  // Under file:// (the Electron desktop build) BrowserRouter can't manipulate the
  // path, so fall back to HashRouter. The web build keeps clean BrowserRouter URLs.
  const Router =
    typeof window !== "undefined" && window.location.protocol === "file:"
      ? HashRouter
      : BrowserRouter;

  return (
    <div className="App">
      <AuthProvider>
        <Router>
        <ModalStackProvider>
          <Toaster
            position="top-right"
            theme="light"
            richColors
            closeButton
            duration={5000}
            toastOptions={{
              style: {
                borderRadius: "var(--radius-md)",
                fontFamily: "Inter, system-ui, sans-serif",
                boxShadow: "var(--shadow-md)",
              },
            }}
          />
          <ErrorBoundary>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/reset-password" element={<ResetPassword />} />
              {/* Partner portal — SEPARATE realm, outside the internal ProtectedRoute/Layout */}
              <Route path="/portal/*" element={<Portal />} />
              {/* POS — full-screen counter, internal auth but outside the Layout chrome */}
              <Route path="/pos" element={<ProtectedRoute><POS /></ProtectedRoute>} />
              <Route path="/qr/:token" element={<QrCheckIn />} />
              <Route path="/payslip/:token" element={<PayslipShare />} />
              <Route
                element={
                  <ProtectedRoute>
                    <Layout />
                  </ProtectedRoute>
                }
              >
                <Route index element={<Dashboard />} />
                <Route path="/products" element={<Products />} />
                <Route path="/categories" element={<Categories />} />
                <Route path="/warehouses" element={<Warehouses />} />
                <Route path="/stock-log" element={<StockLog />} />
                <Route path="/suppliers" element={<Vendors />} />
                <Route path="/purchase-orders" element={<PurchaseOrders />} />
                {/* Inventory & Purchase v2 (stock-ledger backed) */}
                <Route path="/stock-items" element={<StockItems />} />
                <Route path="/godowns" element={<Godowns />} />
                <Route path="/stock-transfers" element={<StockTransfers />} />
                <Route path="/inventory-reports" element={<InventoryReports />} />
                <Route path="/vendors" element={<Vendors />} />
                <Route path="/purchase-orders-v2" element={<PurchaseOrdersV2 />} />
                <Route path="/grns" element={<GRNs />} />
                <Route path="/purchase-bills" element={<PurchaseBills />} />
                <Route path="/purchase-returns" element={<PurchaseReturns />} />
                {/* Masters subsystem (config-driven) */}
                <Route path="/masters/:key" element={<MastersPage />} />
                <Route path="/customers" element={<Customers />} />
                <Route path="/leads" element={<Leads />} />
                <Route path="/quotations" element={<Quotations />} />
                <Route path="/sales-orders" element={<SalesOrders />} />
                <Route path="/invoices" element={<Invoices />} />
                <Route path="/credit-notes" element={<CreditNotes />} />
                <Route
                  path="/proforma-invoices"
                  element={
                    <ProtectedRoute adminOnly>
                      <ProformaInvoices />
                    </ProtectedRoute>
                  }
                />
                <Route path="/dispatches" element={<Dispatches />} />
                <Route
                  path="/reports"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "accountant"]} allowedPermission="reports">
                      <Reports />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/hr"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "hr"]} allowedPermission="hr">
                      <HrDashboard />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/hr/employees"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "hr"]} allowedPermission="hr">
                      <Employees />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/hr/settings"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "hr"]} allowedPermission="hr">
                      <HrSettings />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/hr/attendance"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "hr"]} allowedPermission="hr">
                      <Attendance />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/hr/biometric"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "hr"]} allowedPermission="hr">
                      <BiometricAttendance />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/hr/leaves"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "hr"]} allowedPermission="hr">
                      <HrLeaves />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/hr/payroll"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "hr", "accountant"]} allowedPermission="payroll">
                      <Payroll />
                    </ProtectedRoute>
                  }
                />
                <Route path="/my-portal" element={<MyPortal />} />
                <Route path="/accounting" element={<Accounting />} />
                <Route path="/gst" element={<GstAccounting />} />
                <Route path="/verifications" element={<VerificationDashboard />} />
                <Route path="/verifications/settings" element={<ApiSettings />} />
                <Route
                  path="/expenses"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "accountant", "hr"]} allowedPermission="expenses">
                      <Expenses />
                    </ProtectedRoute>
                  }
                />
                <Route path="/ledger" element={<LedgerBank />} />
                <Route path="/vouchers" element={<Vouchers />} />
                <Route path="/mis-reports" element={<MisReports />} />
                <Route path="/ai-assistant" element={<AiAssistant />} />
                <Route
                  path="/users"
                  element={
                    <ProtectedRoute adminOnly>
                      <Users />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/profile"
                  element={
                    <ProtectedRoute>
                      <Profile />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/admin/theme-settings"
                  element={
                    <ProtectedRoute adminOnly>
                      <ThemeSettings />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/admin/po-numbering"
                  element={
                    <ProtectedRoute allowedPermission="po_numbering">
                      <PoNumberingSettings />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/admin/document-numbering"
                  element={
                    <ProtectedRoute allowedPermission="document_numbering">
                      <DocumentNumberingSettings />
                    </ProtectedRoute>
                  }
                />
                <Route path="/design-system" element={<DesignSystem />} />
                <Route path="/job-work" element={<JobWorkDashboard />} />
                <Route path="/job-work/challans/new" element={<JobWorkChallan />} />
                <Route path="/job-work/challans/:id" element={<JobWorkChallan />} />
                <Route path="/job-work/receipts/new" element={<JobWorkReceipt />} />
                <Route path="/job-work/receipts/:id" element={<JobWorkReceipt />} />
                <Route path="/job-work/reports" element={<JobWorkReports />} />
                <Route path="/job-work/reports/:tab" element={<JobWorkReports />} />
                <Route path="/job-work/legacy" element={<JobWork />} />
                <Route
                  path="/manufacturing"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "accountant"]} allowedPermission="manufacturing">
                      <Manufacturing />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/budget"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "accountant"]}>
                      <Budget />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/fixed-assets"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "accountant"]} allowedPermission="fixed_assets">
                      <FixedAssets />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/debtors-creditors"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "accountant"]} allowedPermission="accounting">
                      <DebtorsCreditors />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/banking"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "accountant"]} allowedPermission="banking">
                      <Banking />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/cheque-printing"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "accountant"]} allowedPermission="cheque_print">
                      <ChequePrinting />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/letterhead-designer"
                  element={
                    <ProtectedRoute allowedRoles={["admin", "accountant"]} allowedPermission="letterhead_design">
                      <LetterheadDesigner />
                    </ProtectedRoute>
                  }
                />
                <Route path="/approvals" element={<Approvals />} />
                <Route path="/reports-deep" element={<ReportsDeep />} />
                <Route path="/pricing" element={<Pricing />} />
                <Route path="/projects" element={<Projects />} />
                <Route path="/integration" element={<ProtectedRoute adminOnly><Integration /></ProtectedRoute>} />
                <Route path="/branches" element={<Branches />} />
                <Route
                  path="/admin/company-master"
                  element={
                    <ProtectedRoute allowedPermission="company_profile">
                      <CompanyMaster />
                    </ProtectedRoute>
                  }
                />
              </Route>
            </Routes>
          </Suspense>
          </ErrorBoundary>
        </ModalStackProvider>
        </Router>
      </AuthProvider>
    </div>
  );
}

export default App;
