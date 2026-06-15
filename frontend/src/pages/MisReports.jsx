import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import {
  PageHeader,
  StatTile,
  SectionTitle,
  PrimaryButton,
  SecondaryButton,
  Input,
  Select,
  EmptyState,
} from "@/components/ui-kit";
import { RefreshCw, Download, TrendingUp, Package, Users, BarChart2 } from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, LineChart, Line, Legend,
} from "recharts";

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

const TABS = [
  { id: "dashboard", label: "MIS Dashboard" },
  { id: "sales", label: "Sales Analysis" },
  { id: "purchase", label: "Purchase Analysis" },
  { id: "profitability", label: "Profitability" },
  { id: "export", label: "Export" },
];

const CHART_STYLE = {
  contentStyle: { backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "var(--radius)", fontFamily: "IBM Plex Mono", fontSize: 11, color: "hsl(var(--foreground))" },
  labelStyle: { color: "hsl(var(--primary))" },
  itemStyle: { color: "hsl(var(--foreground))" }
};

export default function MisReports() {
  const [tab, setTab] = useState("dashboard");
  const [dashboard, setDashboard] = useState(null);
  const [salesData, setSalesData] = useState(null);
  const [purchaseData, setPurchaseData] = useState(null);
  const [profitability, setProfitability] = useState(null);
  const [loading, setLoading] = useState(false);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [salesGroupBy, setSalesGroupBy] = useState("month");
  const [purchaseGroupBy, setPurchaseGroupBy] = useState("month");
  const [exporting, setExporting] = useState(false);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/mis/dashboard");
      setDashboard(r.data);
    } finally { setLoading(false); }
  }, []);

  const loadSales = useCallback(async () => {
    setLoading(true);
    try {
      const params = { group_by: salesGroupBy };
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/mis/sales-analysis", { params });
      setSalesData(r.data);
    } finally { setLoading(false); }
  }, [salesGroupBy, fromDate, toDate]);

  const loadPurchase = useCallback(async () => {
    setLoading(true);
    try {
      const params = { group_by: purchaseGroupBy };
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/mis/purchase-analysis", { params });
      setPurchaseData(r.data);
    } finally { setLoading(false); }
  }, [purchaseGroupBy, fromDate, toDate]);

  const loadProfitability = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/mis/profitability", { params });
      setProfitability(r.data);
    } finally { setLoading(false); }
  }, [fromDate, toDate]);

  useEffect(() => {
    if (tab === "dashboard") loadDashboard();
    if (tab === "sales") loadSales();
    if (tab === "purchase") loadPurchase();
    if (tab === "profitability") loadProfitability();
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const exportSalesExcel = async () => {
    setExporting(true);
    try {
      const params = {};
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/mis/export/sales-excel", { params, responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `sales_report_${new Date().toISOString().split("T")[0]}.xlsx`;
      a.click();
    } catch (e) {
      console.error(e);
    } finally { setExporting(false); }
  };

  const exportExpenseExcel = async () => {
    setExporting(true);
    try {
      const params = {};
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/mis/export/expense-excel", { params, responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `expense_report_${new Date().toISOString().split("T")[0]}.xlsx`;
      a.click();
    } catch (e) {
      console.error(e);
    } finally { setExporting(false); }
  };

  const kpis = dashboard?.kpis || {};

  return (
    <div data-testid="mis-reports-page">
      <PageHeader
        eyebrow="Analytics"
        title="MIS Reports"
        description="Management Information System — advanced analytics, KPIs, and Excel exports."
        actions={
          <SecondaryButton icon={RefreshCw} onClick={() => {
            if (tab === "dashboard") loadDashboard();
          }}>Refresh</SecondaryButton>
        }
      />

      {/* Date filters */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="flex items-center gap-2">
          <span className="label-overline">From</span>
          <Input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} className="w-36" />
        </div>
        <div className="flex items-center gap-2">
          <span className="label-overline">To</span>
          <Input type="date" value={toDate} onChange={e => setToDate(e.target.value)} className="w-36" />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-px bg-zinc-800 border border-zinc-800 mb-6 overflow-x-auto">
        {TABS.map(t => (
          <button key={t.id} data-testid={`tab-${t.id}`} onClick={() => setTab(t.id)}
            className={`flex-shrink-0 px-4 py-3 text-xs font-mono uppercase tracking-wider transition-colors ${
              tab === t.id ? "bg-yellow-400 text-black font-bold" : "bg-zinc-950 text-zinc-400 hover:text-white hover:bg-zinc-900"
            }`}>{t.label}</button>
        ))}
      </div>

      {loading && <div className="text-zinc-500 font-mono text-xs uppercase p-8 text-center">Loading data...</div>}

      {/* MIS Dashboard */}
      {!loading && tab === "dashboard" && dashboard && (
        <div className="space-y-6">
          {/* KPI Grid */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatTile label="Monthly Revenue" value={`₹${inr(kpis.current_month_revenue)}`} accent />
            <StatTile label="Revenue Growth" value={`${kpis.revenue_growth_pct > 0 ? "+" : ""}${kpis.revenue_growth_pct}%`} sub="vs last month" />
            <StatTile label="Sales Count" value={kpis.sales_count} />
            <StatTile label="Gross Profit" value={`₹${inr(kpis.gross_profit)}`} />
            <StatTile label="Receivables" value={`₹${inr(kpis.receivables_outstanding)}`} />
            <StatTile label="Low Stock" value={kpis.low_stock_count} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatTile label="Purchases" value={`₹${inr(kpis.purchase_total)}`} />
            <StatTile label="Expenses" value={`₹${inr(kpis.expense_total)}`} />
            <StatTile label="Customers" value={kpis.customer_count} />
            <StatTile label="Products" value={kpis.product_count} />
          </div>

          {/* Monthly Trend Chart */}
          <div className="border border-zinc-800 bg-zinc-950 p-5">
            <SectionTitle>Revenue vs Expenses (Last 6 Months)</SectionTitle>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={dashboard.monthly_trend}>
                  <defs>
                    <linearGradient id="gRev" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="rgb(var(--yellow-400))" stopOpacity={0.7} />
                      <stop offset="100%" stopColor="rgb(var(--yellow-400))" stopOpacity={0.05} />
                    </linearGradient>
                    <linearGradient id="gExp" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#DA5E2D" stopOpacity={0.5} />
                      <stop offset="100%" stopColor="#DA5E2D" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgb(var(--zinc-800))" vertical={false} />
                  <XAxis dataKey="month" stroke="rgb(var(--zinc-500))" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} />
                  <YAxis stroke="rgb(var(--zinc-500))" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} />
                  <Tooltip {...CHART_STYLE} />
                  <Legend />
                  <Area type="monotone" dataKey="revenue" stroke="rgb(var(--yellow-400))" strokeWidth={2} fill="url(#gRev)" name="Revenue" />
                  <Area type="monotone" dataKey="expenses" stroke="#DA5E2D" strokeWidth={2} fill="url(#gExp)" name="Expenses" />

                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Top Products & Customers */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-px bg-zinc-800 border border-zinc-800">
            <div className="bg-zinc-950 p-5">
              <SectionTitle><Package className="w-4 h-4" /> Top Products</SectionTitle>
              <table className="w-full text-sm">
                <thead><tr className="label-overline border-b border-zinc-800"><th className="text-left py-2">Product</th><th className="text-right py-2">Units</th><th className="text-right py-2">Revenue</th></tr></thead>
                <tbody>
                  {(dashboard.top_products || []).map((p, i) => (
                    <tr key={i} className="border-b border-zinc-900">
                      <td className="py-2 text-white text-xs">{p._id}</td>
                      <td className="py-2 text-right tabular text-zinc-400 text-xs">{p.units_sold}</td>
                      <td className="py-2 text-right tabular text-yellow-400 font-mono text-xs">₹{inr(p.total_revenue)}</td>
                    </tr>
                  ))}
                  {!dashboard.top_products?.length && <tr><td colSpan={3} className="py-4 text-center text-zinc-600 text-xs">No data</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="bg-zinc-950 p-5">
              <SectionTitle><Users className="w-4 h-4" /> Top Customers</SectionTitle>
              <table className="w-full text-sm">
                <thead><tr className="label-overline border-b border-zinc-800"><th className="text-left py-2">Customer</th><th className="text-right py-2">Invoices</th><th className="text-right py-2">Total</th></tr></thead>
                <tbody>
                  {(dashboard.top_customers || []).map((c, i) => (
                    <tr key={i} className="border-b border-zinc-900">
                      <td className="py-2 text-white text-xs">{c._id}</td>
                      <td className="py-2 text-right tabular text-zinc-400 text-xs">{c.count}</td>
                      <td className="py-2 text-right tabular text-yellow-400 font-mono text-xs">₹{inr(c.total)}</td>
                    </tr>
                  ))}
                  {!dashboard.top_customers?.length && <tr><td colSpan={3} className="py-4 text-center text-zinc-600 text-xs">No data</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Sales Analysis */}
      {!loading && tab === "sales" && (
        <div className="space-y-4">
          <div className="flex gap-2 mb-4">
            <Select value={salesGroupBy} onChange={e => setSalesGroupBy(e.target.value)} className="w-36">
              <option value="month">By Month</option>
              <option value="customer">By Customer</option>
              <option value="product">By Product</option>
            </Select>
            <PrimaryButton onClick={loadSales}>Apply</PrimaryButton>
          </div>
          {salesData ? (
            <>
              <div className="border border-zinc-800 bg-zinc-950 p-5">
                <SectionTitle>Sales {salesGroupBy === "month" ? "Trend" : `by ${salesGroupBy}`}</SectionTitle>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={(salesData.data || []).map(d => ({ ...d, name: d._id, value: d.total_revenue }))}>
                      <CartesianGrid stroke="rgb(var(--zinc-800))" vertical={false} />
                      <XAxis dataKey="name" stroke="rgb(var(--zinc-500))" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} />
                      <YAxis stroke="rgb(var(--zinc-500))" tick={{ fontSize: 10 }} />
                      <Tooltip {...CHART_STYLE} />
                      <Bar dataKey="value" fill="rgb(var(--yellow-400))" name="Revenue" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <table className="w-full text-sm border border-zinc-800">
                <thead><tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                  <th className="text-left px-4 py-2">{salesGroupBy === "month" ? "Month" : salesGroupBy === "customer" ? "Customer" : "Product"}</th>
                  <th className="text-right px-4 py-2">Revenue</th>
                  {salesData.group_by === "customer" && <th className="text-right px-4 py-2">Invoices</th>}
                  {salesData.group_by === "product" && <th className="text-right px-4 py-2">Units Sold</th>}
                </tr></thead>
                <tbody>
                  {(salesData.data || []).map((d, i) => (
                    <tr key={i} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                      <td className="px-4 py-2 text-white">{d._id}</td>
                      <td className="px-4 py-2 text-right tabular text-yellow-400 font-mono">₹{inr(d.total_revenue)}</td>
                      {d.invoice_count !== undefined && <td className="px-4 py-2 text-right text-zinc-400">{d.invoice_count}</td>}
                      {d.units_sold !== undefined && <td className="px-4 py-2 text-right text-zinc-400">{d.units_sold}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <EmptyState message="No sales data" />
          )}
        </div>
      )}

      {/* Purchase Analysis */}
      {!loading && tab === "purchase" && (
        <div className="space-y-4">
          <div className="flex gap-2 mb-4">
            <Select value={purchaseGroupBy} onChange={e => setPurchaseGroupBy(e.target.value)} className="w-36">
              <option value="month">By Month</option>
              <option value="supplier">By Supplier</option>
              <option value="product">By Product</option>
            </Select>
            <PrimaryButton onClick={loadPurchase}>Apply</PrimaryButton>
          </div>
          {purchaseData ? (
            <table className="w-full text-sm border border-zinc-800">
              <thead><tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                <th className="text-left px-4 py-2">{purchaseGroupBy}</th>
                <th className="text-right px-4 py-2">Purchase Total</th>
                {purchaseData.group_by === "supplier" && <th className="text-right px-4 py-2">Orders</th>}
              </tr></thead>
              <tbody>
                {(purchaseData.data || []).map((d, i) => (
                  <tr key={i} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                    <td className="px-4 py-2 text-white">{d._id}</td>
                    <td className="px-4 py-2 text-right tabular text-yellow-400 font-mono">₹{inr(d.total_purchase || d.total_cost)}</td>
                    {d.order_count !== undefined && <td className="px-4 py-2 text-right text-zinc-400">{d.order_count}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState message="No purchase data" />
          )}
        </div>
      )}

      {/* Profitability */}
      {!loading && tab === "profitability" && (
        <div className="space-y-4">
          <SecondaryButton icon={RefreshCw} onClick={loadProfitability}>Refresh</SecondaryButton>
          {profitability ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatTile label="Revenue" value={`₹${inr(profitability.revenue)}`} accent />
                <StatTile label="COGS" value={`₹${inr(profitability.cogs)}`} />
                <StatTile label="Gross Profit" value={`₹${inr(profitability.gross_profit)}`} sub={`${profitability.gross_margin_pct}% margin`} />
                <StatTile label="Net Profit" value={`₹${inr(profitability.net_profit)}`} sub={`${profitability.net_margin_pct}% margin`} />
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="border border-zinc-800 bg-zinc-950 p-4">
                  <SectionTitle>Profitability Waterfall</SectionTitle>
                  <div className="space-y-3">
                    {[
                      { label: "Revenue", value: profitability.revenue, color: "#019E2A" },
                      { label: "Cost of Goods Sold", value: -profitability.cogs, color: "#DA5E2D" },
                      { label: "Gross Profit", value: profitability.gross_profit, color: "#2961BE" },
                      { label: "Operating Expenses", value: -profitability.operating_expenses, color: "#DA5E2D" },
                      { label: "Net Profit", value: profitability.net_profit, color: profitability.net_profit >= 0 ? "#019E2A" : "#DA5E2D" },
                    ].map(item => (
                      <div key={item.label}>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-zinc-400 font-mono">{item.label}</span>
                          <span className={`font-mono font-bold ${item.value >= 0 ? "text-green-400" : "text-red-400"}`}>₹{inr(Math.abs(item.value))}</span>
                        </div>
                        <div className="h-2 bg-zinc-800">
                          <div className="h-2" style={{ width: `${Math.min(100, (Math.abs(item.value) / profitability.revenue) * 100)}%`, backgroundColor: item.color }} />
                        </div>
                      </div>
                    ))}

                  </div>
                </div>
                <div className="border border-zinc-800 bg-zinc-950 p-4">
                  <SectionTitle>Expense Breakdown</SectionTitle>
                  <table className="w-full text-sm">
                    <tbody>
                      {(profitability.expense_breakdown || []).map((e, i) => (
                        <tr key={i} className="border-b border-zinc-900">
                          <td className="py-2 text-white text-xs">{e._id || "Other"}</td>
                          <td className="py-2 text-right tabular text-red-400 font-mono text-xs">₹{inr(e.total)}</td>
                        </tr>
                      ))}
                      {!profitability.expense_breakdown?.length && (
                        <tr><td colSpan={2} className="py-4 text-center text-zinc-600 text-xs">No expense data</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            <EmptyState message="No profitability data" />
          )}
        </div>
      )}

      {/* Export Tab */}
      {tab === "export" && (
        <div className="space-y-4 max-w-lg">
          <SectionTitle><Download className="w-4 h-4" /> Excel Exports</SectionTitle>
          <p className="text-sm text-zinc-400">Download detailed reports in Excel format. Apply date filters above before exporting.</p>
          <div className="space-y-3">
            <div className="border border-zinc-800 bg-zinc-900 p-4 flex items-center justify-between">
              <div>
                <div className="font-semibold text-white">Sales Report</div>
                <div className="text-xs text-zinc-500 font-mono">All invoices with payment status</div>
              </div>
              <PrimaryButton icon={Download} onClick={exportSalesExcel} disabled={exporting} testid="export-sales-btn">
                {exporting ? "Exporting..." : "Download XLSX"}
              </PrimaryButton>
            </div>
            <div className="border border-zinc-800 bg-zinc-900 p-4 flex items-center justify-between">
              <div>
                <div className="font-semibold text-white">Expense Report</div>
                <div className="text-xs text-zinc-500 font-mono">Approved expenses by category and department</div>
              </div>
              <PrimaryButton icon={Download} onClick={exportExpenseExcel} disabled={exporting} testid="export-expense-btn">
                {exporting ? "Exporting..." : "Download XLSX"}
              </PrimaryButton>
            </div>
          </div>
          <div className="border border-dashed border-zinc-700 p-4 mt-4">
            <p className="text-xs text-zinc-500 font-mono">Note: Excel exports require <code className="text-yellow-400">openpyxl</code> installed on the backend. Run: <code className="text-yellow-400">pip install openpyxl</code></p>
          </div>
        </div>
      )}
    </div>
  );
}
