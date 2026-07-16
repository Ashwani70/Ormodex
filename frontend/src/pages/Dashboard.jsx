import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PrimaryButton, SecondaryButton } from "@/components/ui-kit";
import ActivityTable from "@/components/ActivityTable";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import {
  TrendingUp,
  ShoppingCart,
  Boxes,
  Landmark,
  CreditCard,
  Wallet,
  Users,
  AlertTriangle,
  Plus,
  SlidersHorizontal,
  Download,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";
import { toast } from "sonner";

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const shortInr = (n) => {
  const v = Number(n || 0);
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(1)}Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`;
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(0)}K`;
  return `₹${v}`;
};

// ── KPI card ─────────────────────────────────────────────────────────
// Icon tile, large tabular value and a colored trend chip — matches the
// reference. `tone` picks the icon tile color from the Aurora tokens.
function KpiCard({ icon: Icon, label, value, trend, tone = "primary" }) {
  const tones = {
    primary: "bg-blue-500/10 text-blue-600 border border-blue-500/20",
    accent: "bg-indigo-500/10 text-indigo-600 border border-indigo-500/20",
    warning: "bg-amber-500/10 text-amber-700 border border-amber-500/20",
    info: "bg-emerald-500/10 text-emerald-600 border border-emerald-500/20",
  };
  const up = (trend ?? 0) >= 0;
  return (
    <div
      className="bg-card border border-border p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-lg relative overflow-hidden group"
      style={{ borderRadius: "var(--radius-lg)" }}
    >
      <div className="absolute -right-6 -bottom-6 w-24 h-24 bg-current opacity-[0.02] rounded-full blur-xl group-hover:scale-125 transition-transform duration-500" />
      
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className={`w-10 h-10 inline-flex items-center justify-center rounded-xl transition-transform duration-300 group-hover:scale-110 ${tones[tone]}`}>
            <Icon className="w-5 h-5" />
          </span>
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
        </div>
        {trend !== undefined && trend !== null && (
          <span
            className={`inline-flex items-center gap-0.5 text-[11px] font-semibold px-2 py-0.5 rounded-full ${
              up ? "bg-emerald-500/10 text-emerald-600" : "bg-red-500/10 text-red-600"
            }`}
          >
            {up ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
            {Math.abs(trend)}%
          </span>
        )}
      </div>
      <div className="flex items-baseline justify-between">
        <span className="text-3xl font-bold tracking-tight text-foreground tabular-nums">{value}</span>
      </div>
    </div>
  );
}

// Card shell for the two charts: title + optional period dropdown.
function ChartCard({ title, period, onPeriod, empty, loading, children }) {
  return (
    <div
      className="bg-card border border-border p-6 flex flex-col transition-all duration-300 hover:shadow-md"
      style={{ borderRadius: "var(--radius-lg)" }}
    >
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">{title}</h3>
        <select
          value={period}
          onChange={(e) => onPeriod(e.target.value)}
          aria-label={`${title} period`}
          className="h-8 px-3 text-xs bg-muted/50 border border-border text-foreground hover:border-zinc-400 focus:border-primary focus:outline-none transition-all duration-200"
          style={{ borderRadius: "var(--radius-sm)" }}
        >
          <option value="week">View by Week</option>
          <option value="month">View by Month</option>
        </select>
      </div>
      <div className="h-64 w-full">
        {loading ? (
          <div className="h-full flex flex-col justify-end gap-2 pb-2 animate-pulse">
            {[60, 85, 45, 70, 55, 90, 40].map((h, i) => (
              <div key={i} className="flex items-end gap-1 flex-1">
                <div className="flex-1 bg-muted rounded-t" style={{ height: `${h}%` }} />
              </div>
            ))}
          </div>
        ) : empty ? (
          <div className="h-full flex items-center justify-center text-muted-foreground font-mono text-xs uppercase tracking-wider">
            No data for this period
          </div>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-card border border-border p-3 shadow-lg rounded-[var(--radius-sm)] text-xs">
        <p className="font-bold text-muted-foreground uppercase tracking-wider text-[10px] mb-1.5">{label}</p>
        {payload.map((p, idx) => (
          <p key={idx} className="font-semibold flex items-center justify-between gap-4 py-0.5">
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ backgroundColor: p.color || p.fill }} />
              {p.name}
            </span>
            <span className="font-mono text-foreground font-bold">₹{Number(p.value).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
          </p>
        ))}
      </div>
    );
  }
  return null;
};

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [salesPeriod, setSalesPeriod] = useState("week");
  const [eiPeriod, setEiPeriod] = useState("week");
  const navigate = useNavigate();
  const { user } = useAuth();
  const firstName = (user?.name || "").trim().split(" ")[0] || "there";

  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/dashboard/summary");
      setData(data);
    } catch (err) {
      if (err?.response?.status === 401) return; // interceptor handles redirect
      toast.error("Failed to load dashboard metrics.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const k = data?.kpis || {};

  // Sales performance — real data. Monthly: invoice revenue by month
  // (sales_trend). Weekly: this week's income per weekday (income_expense).
  const salesData = useMemo(() => {
    if (salesPeriod === "month") {
      return (data?.sales_trend || []).map((t) => ({ label: t.month, value: Number(t.revenue || 0) }));
    }
    return (data?.income_expense?.weekly || []).map((d) => ({ label: d.label, value: d.income }));
  }, [data, salesPeriod]);

  // Expense vs Income — real series from POSTED journal entries (P&L basis).
  const eiData = useMemo(() => {
    const ie = data?.income_expense;
    if (!ie) return [];
    return eiPeriod === "month" ? ie.monthly || [] : ie.weekly || [];
  }, [data, eiPeriod]);

  const employeesValue = k.active_employees != null && k.total_employees != null
    ? `${k.active_employees} / ${k.total_employees}`
    : (k.employees ?? "—");

  return (
    <div data-testid="dashboard-page" className="space-y-6">
      {/* ── Welcome header ─────────────────────────────────────────── */}
      <div className="relative overflow-hidden bg-white bg-gradient-to-br from-white via-white to-[hsl(var(--primary)/0.06)] p-6 sm:p-8 rounded-[var(--radius-lg)] border border-[hsl(var(--border))] shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="absolute top-0 right-0 w-72 h-72 bg-[hsl(var(--primary)/0.08)] rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-10 left-10 w-48 h-48 bg-[hsl(var(--primary)/0.05)] rounded-full blur-2xl pointer-events-none" />
        <div className="absolute inset-y-0 left-0 w-1.5 bg-gradient-to-b from-[var(--primary-color)] to-[var(--accent-color)] pointer-events-none" />

        <div className="relative z-10">
          <span className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.2em] text-[var(--primary-hover)] bg-[var(--primary-soft)] px-2.5 py-1 rounded-full mb-3 border border-[hsl(var(--primary)/0.25)]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            System Active
          </span>
          <h1 data-testid="page-title" className="text-2xl sm:text-3xl font-bold tracking-tight text-[var(--text)] flex items-center gap-2.5">
            Welcome back, {firstName} <span className="animate-bounce">👋</span>
          </h1>
          <p className="mt-2 text-[var(--text-muted)] text-sm max-w-xl">
            Here's the latest summary for Gravity Engineering Works. Monitor active sales orders, payroll processing, and low stock items.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 relative z-10">
          <SecondaryButton
            icon={SlidersHorizontal}
            onClick={() => toast.info("Filters will be available in the next release.")}
          >
            Filter
          </SecondaryButton>
          <SecondaryButton
            icon={Download}
            onClick={() => toast.success("Exporting dashboard report...")}
          >
            Export Report
          </SecondaryButton>
          <PrimaryButton
            icon={Plus}
            testid="dashboard-create-new"
            onClick={() => navigate("/sales-orders")}
          >
            Create New
          </PrimaryButton>
        </div>
      </div>

      {/* ── KPI cards: Sales, Purchase, Stock, Receivables, Payables, Cash Balance ── */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="bg-card border border-border p-6 animate-pulse" style={{ borderRadius: "var(--radius-lg)" }}>
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-muted" />
                <div className="h-3 w-24 bg-muted rounded" />
              </div>
              <div className="h-8 w-32 bg-muted rounded" />
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          <KpiCard
            icon={TrendingUp}
            tone="primary"
            label="Sales"
            value={`₹${inr(k.total_revenue)}`}
            trend={data?.trends?.revenue}
          />
          <KpiCard
            icon={ShoppingCart}
            tone="accent"
            label="Purchase"
            value={`₹${inr(k.purchase_total)}`}
          />
          <KpiCard
            icon={Boxes}
            tone="info"
            label="Stock Value"
            value={`₹${inr(k.inventory_value)}`}
          />
          <KpiCard
            icon={Landmark}
            tone="info"
            label="Receivables"
            value={`₹${inr(k.outstanding)}`}
          />
          <KpiCard
            icon={CreditCard}
            tone="warning"
            label="Payables"
            value={`₹${inr(k.payables)}`}
          />
          <KpiCard
            icon={Wallet}
            tone="primary"
            label="Cash Balance"
            value={`₹${inr(k.cash_balance)}`}
          />
        </div>
      )}

      {/* ── Secondary stats: headcount + stock alerts ─────────────────── */}
      {!loading && (
        <div className="flex flex-wrap items-center gap-4 sm:gap-6 px-1 text-xs">
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            <Users className="w-3.5 h-3.5" /> Active Employees:
            <strong className="text-foreground font-semibold">{employeesValue}</strong>
          </span>
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            <AlertTriangle className="w-3.5 h-3.5" /> Low Stock:
            <strong className="text-foreground font-semibold">{k.low_stock ?? 0} items</strong>
          </span>
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            <ShoppingCart className="w-3.5 h-3.5" /> Sales Orders:
            <strong className="text-foreground font-semibold">{inr(k.sales_orders ?? k.pending_orders ?? 0)}</strong>
          </span>
        </div>
      )}

      {/* ── Charts ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="Sales Performance" period={salesPeriod} onPeriod={setSalesPeriod} empty={!loading && salesData.length === 0} loading={loading}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={salesData} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
              <defs>
                <linearGradient id="salesGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" stroke="hsl(var(--muted-foreground))" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis stroke="hsl(var(--muted-foreground))" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={64} tickFormatter={shortInr} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="value" name="Revenue" stroke="hsl(var(--primary))" strokeWidth={2.5} fill="url(#salesGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Expense vs Income" period={eiPeriod} onPeriod={setEiPeriod} empty={!loading && eiData.length === 0} loading={loading}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={eiData} margin={{ top: 8, right: 8, left: 8, bottom: 0 }} barGap={4}>
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" stroke="hsl(var(--muted-foreground))" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis stroke="hsl(var(--muted-foreground))" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={64} tickFormatter={shortInr} />
              <Tooltip content={<CustomTooltip />} />
              <Legend iconType="circle" wrapperStyle={{ fontSize: "11px" }} />
              <Bar dataKey="income" name="Income" fill="hsl(var(--primary))" radius={[3, 3, 0, 0]} maxBarSize={14} />
              <Bar dataKey="expense" name="Expense" fill="hsl(var(--secondary))" radius={[3, 3, 0, 0]} maxBarSize={14} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* ── Recent Activity ────────────────────────────────────────── */}
      <ActivityTable loading={loading} />
    </div>
  );
}
