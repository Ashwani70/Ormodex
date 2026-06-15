import "@/App.css";
import { useEffect } from "react";
import api from "@/lib/api";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Products from "@/pages/Products";
import Warehouses from "@/pages/Warehouses";
import StockLog from "@/pages/StockLog";
import Suppliers from "@/pages/Suppliers";
import PurchaseOrders from "@/pages/PurchaseOrders";
import Customers from "@/pages/Customers";
import Leads from "@/pages/Leads";
import Quotations from "@/pages/Quotations";
import SalesOrders from "@/pages/SalesOrders";
import Invoices from "@/pages/Invoices";
import Dispatches from "@/pages/Dispatches";
import ProformaInvoices from "@/pages/ProformaInvoices";
import Reports from "@/pages/Reports";
import Users from "@/pages/Users";
import EmailLog from "@/pages/EmailLog";
import HrDashboard from "@/pages/HrDashboard";
import Employees from "@/pages/Employees";
import HrSettings from "@/pages/HrSettings";
import Attendance from "@/pages/Attendance";
import HrLeaves from "@/pages/HrLeaves";
import Payroll from "@/pages/Payroll";
import MyPortal from "@/pages/MyPortal";
import QrCheckIn from "@/pages/QrCheckIn";
import PayslipShare from "@/pages/PayslipShare";
import Accounting from "@/pages/Accounting";
import GstAccounting from "@/pages/GstAccounting";
import Expenses from "@/pages/Expenses";
import LedgerBank from "@/pages/LedgerBank";
import Vouchers from "@/pages/Vouchers";
import MisReports from "@/pages/MisReports";
import AiAssistant from "@/pages/AiAssistant";
import ThemeSettings, { applyTheme } from "@/pages/ThemeSettings";
import CompanyMaster from "@/pages/CompanyMaster";
import JobWork from "@/pages/JobWork";
import VerificationDashboard from "@/pages/VerificationDashboard";
import ApiSettings from "@/pages/ApiSettings";
import Manufacturing from "@/pages/Manufacturing";
import Budget from "@/pages/Budget";
import FixedAssets from "@/pages/FixedAssets";
import Banking from "@/pages/Banking";
import Approvals from "@/pages/Approvals";
import ReportsDeep from "@/pages/ReportsDeep";
import Pricing from "@/pages/Pricing";
import Portal from "@/pages/Portal";
import Projects from "@/pages/Projects";
import POS from "@/pages/POS";
import Integration from "@/pages/Integration";
import Branches from "@/pages/Branches";
import StockItems from "@/pages/StockItems";
import Godowns from "@/pages/Godowns";
import StockTransfers from "@/pages/StockTransfers";
import InventoryReports from "@/pages/InventoryReports";
import Vendors from "@/pages/Vendors";
import PurchaseOrdersV2 from "@/pages/PurchaseOrdersV2";
import GRNs from "@/pages/GRNs";
import PurchaseBills from "@/pages/PurchaseBills";
import PurchaseReturns from "@/pages/PurchaseReturns";



function App() {
  // Apply theme from localStorage instantly on load, then sync with DB
  useEffect(() => {
    const saved = localStorage.getItem("gew_theme_settings");
    if (saved) {
      try {
        const theme = JSON.parse(saved);
        applyTheme(theme);
      } catch (e) {}
    }
    
    api.get("/theme-settings/active")
      .then((res) => {
        applyTheme(res.data);
        localStorage.setItem("gew_theme_settings", JSON.stringify(res.data));
      })
      .catch(() => {});
  }, []);

  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <Toaster
            position="top-right"
            theme="dark"
            toastOptions={{
              style: {
                background: "#09090b",
                border: "1px solid #27272a",
                color: "#fff",
                borderRadius: "0",
                fontFamily: "IBM Plex Sans",
              },
            }}
          />
          <Routes>
            <Route path="/login" element={<Login />} />
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
              <Route path="/warehouses" element={<Warehouses />} />
              <Route path="/stock-log" element={<StockLog />} />
              <Route path="/suppliers" element={<Suppliers />} />
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
              <Route path="/customers" element={<Customers />} />
              <Route path="/leads" element={<Leads />} />
              <Route path="/quotations" element={<Quotations />} />
              <Route path="/sales-orders" element={<SalesOrders />} />
              <Route path="/invoices" element={<Invoices />} />
              <Route path="/proforma-invoices" element={<ProformaInvoices />} />
              <Route path="/dispatches" element={<Dispatches />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/hr" element={<HrDashboard />} />
              <Route path="/hr/employees" element={<Employees />} />
              <Route path="/hr/settings" element={<HrSettings />} />
              <Route path="/hr/attendance" element={<Attendance />} />
              <Route path="/hr/leaves" element={<HrLeaves />} />
              <Route path="/hr/payroll" element={<Payroll />} />
              <Route path="/my-portal" element={<MyPortal />} />
              <Route path="/accounting" element={<Accounting />} />
              <Route path="/gst" element={<GstAccounting />} />
              <Route path="/verifications" element={<VerificationDashboard />} />
              <Route path="/verifications/settings" element={<ApiSettings />} />
              <Route path="/expenses" element={<Expenses />} />
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
                path="/email-log"
                element={
                  <ProtectedRoute adminOnly>
                    <EmailLog />
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
              <Route path="/job-work" element={<JobWork />} />
              <Route path="/manufacturing" element={<Manufacturing />} />
              <Route path="/budget" element={<Budget />} />
              <Route path="/fixed-assets" element={<FixedAssets />} />
              <Route path="/banking" element={<Banking />} />
              <Route path="/approvals" element={<Approvals />} />
              <Route path="/reports-deep" element={<ReportsDeep />} />
              <Route path="/pricing" element={<Pricing />} />
              <Route path="/projects" element={<Projects />} />
              <Route path="/integration" element={<ProtectedRoute adminOnly><Integration /></ProtectedRoute>} />
              <Route path="/branches" element={<Branches />} />

              <Route
                path="/admin/company-master"
                element={
                  <ProtectedRoute adminOnly>
                    <CompanyMaster />
                  </ProtectedRoute>
                }
              />

            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}

export default App;
