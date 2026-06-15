import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import {
  PageHeader,
  StatTile,
  SectionTitle,
  StatusBadge,
  PrimaryButton,
  SecondaryButton,
} from "@/components/ui-kit";
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
} from "recharts";
import {
  Boxes,
  AlertTriangle,
  IndianRupee,
  Users,
  TrendingUp,
  ShoppingCart,
  Plus,
  Sparkles,
  RefreshCw,
  Clock,
  Activity,
  Database,
  HardDrive,
  CheckSquare,
  Square,
  Trash2,
  ListTodo,
  FileCheck,
  Bot,
  Package,
  Star,
  ArrowRight,
  ArrowUpRight,
  ArrowDownRight,
  Zap,
} from "lucide-react";
import { toast } from "sonner";

const inr = (n) =>
  Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

const AI_INSIGHT_ICONS = {
  SALES_SUMMARY: TrendingUp,
  TOP_CUSTOMER: Star,
  PENDING_APPROVALS: Clock,
  LOW_STOCK_ALERT: Package,
  UNPAID_INVOICES: AlertTriangle,
};

const AI_INSIGHT_ROUTES = {
  SALES_SUMMARY: "/mis-reports",
  TOP_CUSTOMER: "/customers",
  PENDING_APPROVALS: "/expenses",
  LOW_STOCK_ALERT: "/products",
  UNPAID_INVOICES: "/invoices",
};

const AI_INSIGHT_COLORS = {
  SALES_SUMMARY: "text-green-400 border-green-800/40 bg-green-950/10",
  TOP_CUSTOMER: "text-blue-400 border-blue-800/40 bg-blue-950/10",
  PENDING_APPROVALS: "text-yellow-400 border-yellow-800/40 bg-yellow-950/10",
  LOW_STOCK_ALERT: "text-orange-400 border-orange-800/40 bg-orange-950/10",
  UNPAID_INVOICES: "text-red-400 border-red-800/40 bg-red-950/10",
};

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [aiInsights, setAiInsights] = useState(null);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const navigate = useNavigate();
  
  // Daily checklist state
  const [tasks, setTasks] = useState([]);
  const [newTaskText, setNewTaskText] = useState("");

  // Live Digital Clock
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Fetch dashboard summary and audit logs
  const fetchDashboardData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    else setLoading(true);

    try {
      const [summaryRes, auditRes] = await Promise.all([
        api.get("/dashboard/summary"),
        api.get("/reports/audit"),
      ]);
      setData(summaryRes.data);
      setAuditLogs(auditRes.data.slice(0, 10)); // Take top 10 recent audits
      if (isManual) {
        toast.success("Metrics and activity log refreshed.");
      }
    } catch (err) {
      toast.error("Failed to load dashboard console metrics.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const fetchAiInsights = async () => {
    setInsightsLoading(true);
    try {
      const r = await api.get("/ai/business-insights");
      setAiInsights(r.data);
    } catch (e) {
      // Silently fail — AI may not be configured
    } finally {
      setInsightsLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
    fetchAiInsights();

    // Load daily checklist from localStorage
    const savedTasks = localStorage.getItem("gew_dashboard_tasks");
    if (savedTasks) {
      try {
        setTasks(JSON.parse(savedTasks));
      } catch (e) {
        initializeDefaultTasks();
      }
    } else {
      initializeDefaultTasks();
    }
  }, []);

  const initializeDefaultTasks = () => {
    const defaults = [
      { id: "t1", text: "Verify low stock levels & place POs", done: false },
      { id: "t2", text: "Confirm pending Sales Orders for dispatch", done: false },
      { id: "t3", text: "Review outsourcing Job Work challans", done: false },
      { id: "t4", text: "Verify GST invoice payments & outstandings", done: false },
      { id: "t5", text: "Generate payroll runs for employee payslips", done: false },
    ];
    setTasks(defaults);
    localStorage.setItem("gew_dashboard_tasks", JSON.stringify(defaults));
  };

  // Add custom task
  const handleAddTask = (e) => {
    e.preventDefault();
    if (!newTaskText.trim()) return;
    const updated = [
      ...tasks,
      { id: `t_${Date.now()}`, text: newTaskText.trim(), done: false },
    ];
    setTasks(updated);
    setNewTaskText("");
    localStorage.setItem("gew_dashboard_tasks", JSON.stringify(updated));
    toast.success("Checklist task added.");
  };

  // Toggle task checkbox
  const toggleTask = (id) => {
    const updated = tasks.map((t) => (t.id === id ? { ...t, done: !t.done } : t));
    setTasks(updated);
    localStorage.setItem("gew_dashboard_tasks", JSON.stringify(updated));
  };

  // Delete task
  const deleteTask = (id) => {
    const updated = tasks.filter((t) => t.id !== id);
    setTasks(updated);
    localStorage.setItem("gew_dashboard_tasks", JSON.stringify(updated));
  };

  // Format activity feed messages
  const formatAuditMessage = (log) => {
    const actor = log.user_name || "System";
    const collection = log.collection_name || "";
    const action = log.action || "ACTION";
    
    let modelName = collection.replace(/_/g, " ");
    // Capitalize first letter of each word
    modelName = modelName.replace(/\b\w/g, c => c.toUpperCase());

    const timeStr = new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    if (action === "CREATE") {
      return {
        text: `New ${modelName} entry generated`,
        sub: `Created by ${actor}`,
        badge: "CREATE",
        time: timeStr
      };
    } else if (action === "UPDATE") {
      return {
        text: `Modified ${modelName} properties`,
        sub: `Updated by ${actor}`,
        badge: "UPDATE",
        time: timeStr
      };
    } else {
      return {
        text: `Removed ${modelName} record`,
        sub: `Deleted by ${actor}`,
        badge: "DELETE",
        time: timeStr
      };
    }
  };

  const k = data?.kpis || {};
  const trend = (data?.sales_trend || []).length
    ? data.sales_trend
    : [
        { month: "M-5", revenue: 0 },
        { month: "M-4", revenue: 0 },
        { month: "M-3", revenue: 0 },
        { month: "M-2", revenue: 0 },
        { month: "M-1", revenue: 0 },
        { month: "Now", revenue: 0 },
      ];

  return (
    <div data-testid="dashboard-page" className="space-y-6">
      {/* Control Console Dashboard Header */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between border-b border-zinc-800 pb-5">
        <div>
          <div className="label-overline mb-2 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" />
            Operations Control Center
          </div>
          <h1
            data-testid="page-title"
            className="font-display font-black text-3xl sm:text-4xl tracking-tight text-zinc-50 uppercase"
          >
            Mission Control
          </h1>
          <p className="mt-2 text-sm text-zinc-400 max-w-2xl">
            Live operations dashboard for GravityOne ERP — manage sales, inventory, HR, accounting, procurement, and AI automation from a single intelligent platform.
          </p>
        </div>

        {/* Live System Diagnostics Widget */}
        <div className="flex flex-wrap items-center gap-4 bg-zinc-950/80 border border-zinc-800/80 p-3 sm:px-4 sm:py-2.5 rounded-md backdrop-blur-md shadow-lg">
          <div className="flex items-center gap-2 border-r border-zinc-800 pr-4">
            <Clock className="w-4 h-4 text-zinc-500" />
            <span className="font-mono text-xs text-zinc-300 font-semibold tracking-wider">
              {currentTime.toLocaleTimeString()}
            </span>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500 pulse-yellow" />
              <span className="font-mono text-[10px] uppercase text-zinc-400 font-bold">SYSTEM ACTIVE</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5 text-zinc-500" />
              <span className="font-mono text-[10px] uppercase text-emerald-400 font-bold">DB SYNCED</span>
            </div>
          </div>

          <button
            onClick={() => fetchDashboardData(true)}
            disabled={refreshing}
            className={`bg-zinc-900 border border-zinc-800 hover:border-yellow-400 hover:bg-zinc-800 text-zinc-300 hover:text-yellow-400 p-2 transition-all ${
              refreshing ? "animate-pulse" : ""
            }`}
            title="Refresh Console Statistics"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center p-24 border border-zinc-800 bg-zinc-950">
          <RefreshCw className="w-8 h-8 text-yellow-400 animate-spin mb-4" />
          <p className="font-mono text-xs uppercase text-zinc-500 tracking-widest">Hydrating dashboard metrics...</p>
        </div>
      ) : (
        <>
          {/* KPI grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
            <div className="relative group">
              <StatTile
                testid="kpi-products"
                label="Products catalog"
                value={k.total_products ?? 0}
                sub={`${k.low_stock ?? 0} low-stock alerts`}
              />
              <Boxes className="absolute right-4 top-4 w-4 h-4 text-zinc-600 group-hover:text-yellow-400 transition-colors pointer-events-none" />
            </div>

            <div className="relative group">
              <StatTile
                testid="kpi-inventory-value"
                label="Asset Valuation"
                value={`₹${inr(k.inventory_value)}`}
                sub="Total cost inventory on hand"
              />
              <HardDrive className="absolute right-4 top-4 w-4 h-4 text-zinc-600 group-hover:text-yellow-400 transition-colors pointer-events-none" />
            </div>

            <div className="relative group">
              <StatTile
                testid="kpi-revenue"
                label="Billed Revenue"
                value={`₹${inr(k.total_revenue)}`}
                sub={`₹${inr(k.outstanding)} outstanding ledger`}
                accent
              />
              <IndianRupee className="absolute right-4 top-4 w-4 h-4 text-zinc-600 group-hover:text-yellow-400 transition-colors pointer-events-none" />
            </div>

            <div className="relative group">
              <StatTile
                testid="kpi-customers"
                label="Clients / ERP Leads"
                value={k.customers ?? 0}
                sub={`${k.leads ?? 0} total leads registered`}
              />
              <Users className="absolute right-4 top-4 w-4 h-4 text-zinc-600 group-hover:text-yellow-400 transition-colors pointer-events-none" />
            </div>

            <div className="relative group">
              <StatTile
                testid="kpi-pending-orders"
                label="Pending dispatches"
                value={k.pending_orders ?? 0}
                sub={`${k.sales_orders ?? 0} confirmed orders`}
              />
              <ShoppingCart className="absolute right-4 top-4 w-4 h-4 text-zinc-600 group-hover:text-yellow-400 transition-colors pointer-events-none" />
            </div>
          </div>

          {/* Quick Operations Actions Strip */}
          <div className="flex flex-wrap items-center gap-3 bg-zinc-900 border border-zinc-800 p-4 shadow-md rounded-md justify-between">
            <span className="font-mono text-xs uppercase text-zinc-400 tracking-wider flex items-center gap-2">
              <Activity className="w-4 h-4 text-yellow-400" /> Quick Operations Dispatch
            </span>
            <div className="flex flex-wrap gap-2">
              <Link to="/sales-orders">
                <PrimaryButton icon={Plus} testid="dashboard-new-order">
                  NEW SALES ORDER
                </PrimaryButton>
              </Link>
              <Link to="/leads">
                <SecondaryButton icon={Sparkles}>
                  ADD ERP LEAD
                </SecondaryButton>
              </Link>
            </div>
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Sales trend */}
            <div className="lg:col-span-2 bg-zinc-950 border border-zinc-800 p-6 rounded-md shadow-lg">
              <SectionTitle>REVENUE TREND (LAST 6 MONTHS)</SectionTitle>
              <div className="h-80 w-full mt-4">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trend}>
                    <defs>
                      <linearGradient id="revenueGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="rgb(var(--yellow-400))" stopOpacity={0.4} />
                        <stop offset="100%" stopColor="rgb(var(--yellow-400))" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="rgb(var(--zinc-800))" vertical={false} />
                    <XAxis 
                      dataKey="month" 
                      stroke="rgb(var(--zinc-500))" 
                      tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} 
                      dy={10}
                    />
                    <YAxis 
                      stroke="rgb(var(--zinc-500))" 
                      tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} 
                      dx={-10}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "var(--radius)",
                        fontFamily: "IBM Plex Mono",
                        fontSize: "11px",
                        color: "hsl(var(--foreground))"
                      }}
                      labelStyle={{ color: "hsl(var(--primary))", fontWeight: "bold" }}
                      itemStyle={{ color: "hsl(var(--foreground))" }}
                    />
                    <Area
                      type="monotone"
                      dataKey="revenue"
                      name="Revenue"
                      stroke="rgb(var(--yellow-400))"
                      strokeWidth={2.5}
                      fill="url(#revenueGrad)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Lead funnel */}
            <div className="bg-zinc-950 border border-zinc-800 p-6 rounded-md shadow-lg">
              <SectionTitle>LEAD PIPELINE FUNNEL</SectionTitle>
              <div className="h-80 w-full mt-4">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data?.lead_funnel || []} layout="vertical">
                    <CartesianGrid stroke="rgb(var(--zinc-800))" horizontal={false} />
                    <XAxis 
                      type="number" 
                      stroke="rgb(var(--zinc-500))" 
                      tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} 
                      dy={10}
                    />
                    <YAxis 
                      dataKey="status" 
                      type="category" 
                      stroke="rgb(var(--zinc-500))" 
                      tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} 
                      width={80}
                      dx={-5}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "var(--radius)",
                        fontFamily: "IBM Plex Mono",
                        fontSize: "11px",
                        color: "hsl(var(--foreground))"
                      }}
                      itemStyle={{ color: "hsl(var(--primary))" }}
                    />
                    <Bar 
                      dataKey="count" 
                      name="Leads" 
                      fill="#019E2A"
                      radius={[0, 2, 2, 0]} 
                      maxBarSize={30}
                    />

                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* ── AI Business Insights Widget ─────────────────────────── */}
          <div className="bg-zinc-950 border border-zinc-800 p-5 relative overflow-hidden">
            {/* Gold accent bar */}
            <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-yellow-400 via-yellow-300 to-transparent" />
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 bg-yellow-400 flex items-center justify-center flex-shrink-0">
                  <Bot className="w-4 h-4 text-black" />
                </div>
                <div>
                  <div className="text-sm font-bold text-white">AI Business Insights</div>
                  <div className="flex items-center gap-1 mt-0.5">
                    <Zap className="w-2.5 h-2.5 text-yellow-400" />
                    <span className="font-mono text-[9px] uppercase tracking-widest text-yellow-400">Powered by Gravity Copilot</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={fetchAiInsights}
                  disabled={insightsLoading}
                  className="p-1.5 border border-zinc-800 text-zinc-500 hover:text-yellow-400 hover:border-yellow-400 transition-colors"
                >
                  <RefreshCw className={`w-3 h-3 ${insightsLoading ? "animate-spin" : ""}`} />
                </button>
                <Link to="/ai-assistant" className="flex items-center gap-1 text-[10px] font-mono text-zinc-500 hover:text-yellow-400 border border-zinc-800 hover:border-yellow-400 px-2 py-1 transition-colors">
                  Full AI Hub <ArrowRight className="w-2.5 h-2.5" />
                </Link>
              </div>
            </div>

            {insightsLoading ? (
              <div className="flex items-center gap-3 py-4">
                <div className="w-4 h-4 border-2 border-yellow-400 border-t-transparent rounded-full animate-spin" />
                <span className="text-xs text-zinc-500 font-mono">Generating AI insights...</span>
              </div>
            ) : aiInsights?.insights?.length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                {aiInsights.insights.map((ins, i) => {
                  const Icon = AI_INSIGHT_ICONS[ins.type] || Sparkles;
                  const colorCls = AI_INSIGHT_COLORS[ins.type] || "text-yellow-400 border-yellow-800/40 bg-yellow-950/10";
                  const route = AI_INSIGHT_ROUTES[ins.type];
                  const trend = ins.trend;
                  return (
                    <button
                      key={i}
                      onClick={() => route && navigate(route)}
                      className={`border p-3 text-left hover:opacity-90 transition-opacity ${colorCls}`}
                    >
                      <div className="flex items-center gap-1.5 mb-2">
                        <Icon className="w-3 h-3 flex-shrink-0" />
                        <span className="text-[9px] font-mono uppercase tracking-wider opacity-80 truncate">{ins.title}</span>
                      </div>
                      <div className="font-display font-black text-xl leading-none">
                        {typeof ins.value === "number" && ins.value > 1000
                          ? `₹${inr(ins.value)}`
                          : ins.value}
                      </div>
                      {ins.name && <div className="text-[9px] mt-1 opacity-70 truncate">{ins.name}</div>}
                      {ins.count && <div className="text-[9px] mt-0.5 opacity-60">{ins.count} records</div>}
                      {trend !== undefined && (
                        <div className={`flex items-center gap-0.5 mt-1 text-[9px] font-mono ${trend >= 0 ? "text-green-400" : "text-red-400"}`}>
                          {trend >= 0 ? <ArrowUpRight className="w-2.5 h-2.5" /> : <ArrowDownRight className="w-2.5 h-2.5" />}
                          {Math.abs(trend).toFixed(1)}% vs last month
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="flex items-center gap-3 py-3 px-4 border border-dashed border-zinc-800">
                <Bot className="w-5 h-5 text-zinc-700" />
                <div>
                  <div className="text-xs text-zinc-500">No AI insights available yet</div>
                  <div className="text-[9px] font-mono text-zinc-700 mt-0.5">Add an AI provider key in backend/.env to enable insights</div>
                </div>
              </div>
            )}
          </div>

          {/* Three-Column Bottom Hub */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Column 1: Low Stock Alerts */}
            <div className="bg-zinc-950 border border-zinc-800 p-6 rounded-md flex flex-col justify-between shadow-lg h-[460px]">
              <div>
                <SectionTitle
                  action={
                    <Link to="/products">
                      <SecondaryButton testid="view-low-stock">
                        CATALOG
                      </SecondaryButton>
                    </Link>
                  }
                >
                  <span className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-yellow-500 animate-bounce" />
                    Low-Stock Alerts
                  </span>
                </SectionTitle>
                
                <div className="overflow-y-auto max-h-[340px] pr-1 mt-4 space-y-3">
                  {data?.low_stock_items?.length ? (
                    data.low_stock_items.map((p) => {
                      const percentage = float(p.low_stock_threshold) > 0 ? Math.min(100, Math.max(0, (float(p.quantity) / float(p.low_stock_threshold)) * 100)) : 0;
                      return (
                        <div key={p.sku} className="border border-zinc-900 bg-zinc-900/20 p-3 flex flex-col gap-2">
                          <div className="flex justify-between items-start">
                            <div>
                              <div className="text-zinc-100 text-xs font-bold font-sans">{p.name}</div>
                              <div className="text-zinc-500 font-mono text-[10px] tracking-wider uppercase">{p.sku}</div>
                            </div>
                            <div className="text-right">
                              <span className="text-xs font-mono font-bold text-red-500 tabular">{p.quantity}</span>
                              <span className="text-[10px] text-zinc-500 font-mono"> / {p.low_stock_threshold} pcs</span>
                            </div>
                          </div>
                          {/* Stock Level Progress Indicator */}
                          <div className="w-full bg-zinc-900 h-1.5 rounded-full overflow-hidden">
                            <div 
                              className={`h-full transition-all ${
                                percentage <= 30 ? "bg-red-600" : percentage <= 60 ? "bg-amber-500" : "bg-yellow-400"
                              }`} 
                              style={{ width: `${percentage}%` }}
                            />
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-zinc-800">
                      <FileCheck className="w-8 h-8 text-zinc-700 mb-2" />
                      <div className="text-xs text-zinc-500 font-mono uppercase tracking-wider">All stock levels healthy</div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Column 2: System Activity Log Stream */}
            <div className="bg-zinc-950 border border-zinc-800 p-6 rounded-md shadow-lg h-[460px] flex flex-col justify-between">
              <div>
                <SectionTitle
                  action={
                    <Link to="/email-log">
                      <SecondaryButton>
                        LOGS
                      </SecondaryButton>
                    </Link>
                  }
                >
                  <span className="flex items-center gap-2">
                    <Activity className="w-4 h-4 text-yellow-500" />
                    System Stream
                  </span>
                </SectionTitle>

                <div className="overflow-y-auto max-h-[340px] pr-1 mt-4 space-y-3">
                  {auditLogs.length > 0 ? (
                    auditLogs.map((log) => {
                      const msg = formatAuditMessage(log);
                      return (
                        <div key={log.id} className="border border-zinc-900 bg-zinc-950 p-2.5 flex items-start gap-3">
                          <div className="mt-1">
                            {msg.badge === "CREATE" ? (
                              <span className="w-2 h-2 rounded-full bg-emerald-500 block" title="Record Created" />
                            ) : msg.badge === "UPDATE" ? (
                              <span className="w-2 h-2 rounded-full bg-sky-500 block" title="Record Updated" />
                            ) : (
                              <span className="w-2 h-2 rounded-full bg-rose-500 block" title="Record Deleted" />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-zinc-200 text-xs font-bold truncate">{msg.text}</div>
                            <div className="text-[10px] text-zinc-500 font-mono truncate mt-0.5">{msg.sub}</div>
                          </div>
                          <div className="text-[10px] text-zinc-600 font-mono">{msg.time}</div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-zinc-800">
                      <Clock className="w-8 h-8 text-zinc-700 mb-2" />
                      <div className="text-xs text-zinc-500 font-mono uppercase tracking-wider">No recent operations logged</div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Column 3: Daily Task Checklist Widget */}
            <div className="bg-zinc-950 border border-zinc-800 p-6 rounded-md shadow-lg h-[460px] flex flex-col justify-between">
              <div>
                <SectionTitle>
                  <span className="flex items-center gap-2">
                    <ListTodo className="w-4 h-4 text-yellow-500" />
                    Daily Checklist
                  </span>
                </SectionTitle>

                {/* Task Add Form */}
                <form onSubmit={handleAddTask} className="flex gap-1.5 mt-3">
                  <input
                    type="text"
                    value={newTaskText}
                    onChange={(e) => setNewTaskText(e.target.value)}
                    placeholder="New custom operation task..."
                    className="flex-1 bg-zinc-950 border border-zinc-800 text-xs px-2.5 py-1.5 text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-yellow-400"
                  />
                  <button 
                    type="submit"
                    className="bg-yellow-400 hover:bg-yellow-500 text-black px-3 font-mono font-bold text-xs uppercase"
                  >
                    ADD
                  </button>
                </form>

                {/* Checklist items list */}
                <div className="overflow-y-auto max-h-[250px] pr-1 mt-4 space-y-2">
                  {tasks.length > 0 ? (
                    tasks.map((task) => (
                      <div 
                        key={task.id} 
                        className="flex items-center justify-between border border-zinc-900 bg-zinc-900/10 p-2 px-3 group"
                      >
                        <button
                          type="button"
                          onClick={() => toggleTask(task.id)}
                          className="flex items-center gap-2.5 text-left min-w-0 flex-1"
                        >
                          {task.done ? (
                            <CheckSquare className="w-4 h-4 text-yellow-400 shrink-0" />
                          ) : (
                            <Square className="w-4 h-4 text-zinc-600 shrink-0 hover:text-zinc-400" />
                          )}
                          <span className={`text-[11px] font-mono leading-tight truncate ${
                            task.done ? "line-through text-zinc-600" : "text-zinc-300"
                          }`}>
                            {task.text}
                          </span>
                        </button>
                        <button
                          type="button"
                          onClick={() => deleteTask(task.id)}
                          className="text-zinc-700 hover:text-rose-500 p-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                          title="Remove Task"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))
                  ) : (
                    <div className="text-center p-6 text-zinc-600 font-mono text-[10px] uppercase border border-zinc-900">
                      Checklist is empty
                    </div>
                  )}
                </div>
              </div>

              {/* Reset to defaults button */}
              <div className="pt-4 border-t border-zinc-900 flex justify-end">
                <button
                  type="button"
                  onClick={initializeDefaultTasks}
                  className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 hover:text-yellow-400 transition-colors"
                >
                  Reset Defaults
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// Inline helper because we want this file to run clean
function float(val) {
  const f = parseFloat(val);
  return isNaN(f) ? 0.0 : f;
}
