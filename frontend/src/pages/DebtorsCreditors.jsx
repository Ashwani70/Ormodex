import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import {
  TrendingUp, TrendingDown, AlertCircle, CheckCircle2, Clock, RefreshCw,
  Search, Filter, Download, Plus, ChevronDown, ChevronUp, X, Send,
  FileText, CreditCard, Banknote, Users, Building2, Phone, Mail,
  MessageSquare, Calendar, DollarSign, BarChart2, ArrowUpRight, Eye,
  Printer, Share2, MoreHorizontal, Edit2, Trash2, Bell, Loader2,
} from "lucide-react";

// ─── Design tokens (matches Aurora system) ───────────────────────────────────
const fmt = (n) =>
  `₹${Number(n ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
const fmtK = (n) => {
  const v = Number(n ?? 0);
  if (Math.abs(v) >= 10_00_000) return `₹${(v / 10_00_000).toFixed(1)}L`;
  if (Math.abs(v) >= 1_000) return `₹${(v / 1_000).toFixed(1)}K`;
  return fmt(v);
};
const today = () => new Date().toISOString().slice(0, 10);
const diffDays = (d) => {
  if (!d) return 0;
  return Math.max(0, Math.floor((Date.now() - new Date(d)) / 86400000));
};
const ageBucketLabel = (days) => {
  if (days <= 0) return "Current";
  if (days <= 30) return "0–30 Days";
  if (days <= 60) return "31–60 Days";
  if (days <= 90) return "61–90 Days";
  if (days <= 180) return "90–180 Days";
  return "180+ Days";
};
const ageBucketColor = (days) => {
  if (days <= 0) return "text-emerald-400";
  if (days <= 30) return "text-yellow-400";
  if (days <= 60) return "text-orange-400";
  if (days <= 90) return "text-red-400";
  if (days <= 180) return "text-red-500";
  return "text-red-600";
};

// ─── Reusable UI primitives ───────────────────────────────────────────────────
const Card = ({ children, className = "" }) => (
  <div className={`bg-card border border-border rounded-xl p-4 ${className}`}>{children}</div>
);

const Btn = ({ children, onClick, variant = "primary", disabled, size = "md", className = "" }) => {
  const vs = {
    primary:   "bg-primary text-primary-foreground hover:opacity-90",
    secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
    ghost:     "text-muted-foreground hover:text-foreground hover:bg-accent",
    danger:    "bg-destructive text-destructive-foreground hover:opacity-90",
    success:   "bg-emerald-600 text-white hover:bg-emerald-500",
    outline:   "border border-border text-foreground hover:bg-accent",
  };
  const ss = { sm: "px-3 py-1.5 text-xs", md: "px-4 py-2 text-sm", lg: "px-5 py-2.5 text-sm" };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`${vs[variant]} ${ss[size]} rounded-lg font-medium transition-all disabled:opacity-50 flex items-center gap-1.5 ${className}`}
    >
      {children}
    </button>
  );
};

const Input = ({ label, className = "", ...props }) => (
  <div className={className}>
    {label && <label className="block text-xs text-muted-foreground mb-1">{label}</label>}
    <input
      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
      {...props}
    />
  </div>
);

const Select = ({ label, children, className = "", ...props }) => (
  <div className={className}>
    {label && <label className="block text-xs text-muted-foreground mb-1">{label}</label>}
    <select
      className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
      {...props}
    >
      {children}
    </select>
  </div>
);

const Badge = ({ children, color = "default" }) => {
  const c = {
    default:  "bg-secondary text-secondary-foreground",
    green:    "bg-emerald-900/40 text-emerald-400",
    yellow:   "bg-yellow-900/40 text-yellow-400",
    orange:   "bg-orange-900/40 text-orange-400",
    red:      "bg-red-900/40 text-red-400",
    blue:     "bg-blue-900/40 text-blue-400",
    purple:   "bg-purple-900/40 text-purple-400",
  };
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${c[color] ?? c.default}`}>{children}</span>;
};

const statusBadge = (status) => {
  const m = {
    OPEN:           { label: "Open",           color: "blue" },
    PARTIALLY_PAID: { label: "Partial",         color: "yellow" },
    PAID:           { label: "Paid",            color: "green" },
    OVERDUE:        { label: "Overdue",         color: "red" },
    CANCELLED:      { label: "Cancelled",       color: "default" },
  };
  const x = m[status] ?? { label: status, color: "default" };
  return <Badge color={x.color}>{x.label}</Badge>;
};

const Spinner = ({ size = 16 }) => (
  <Loader2 size={size} className="animate-spin text-muted-foreground" />
);

const EmptyState = ({ message = "No records found." }) => (
  <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-2">
    <FileText size={32} className="opacity-30" />
    <p className="text-sm">{message}</p>
  </div>
);

const Modal = ({ open, onClose, title, children, wide = false }) => {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div
        className={`bg-card border border-border rounded-2xl shadow-2xl w-full ${wide ? "max-w-4xl" : "max-w-lg"} max-h-[90vh] overflow-y-auto`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border sticky top-0 bg-card z-10">
          <h2 className="font-semibold text-foreground">{title}</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground p-1 rounded-lg hover:bg-accent">
            <X size={18} />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
};

// ─── Stat Card ───────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, icon: Icon, trend, color = "blue" }) {
  const colors = {
    blue:   "from-blue-500/10 to-blue-600/5 border-blue-500/20",
    green:  "from-emerald-500/10 to-emerald-600/5 border-emerald-500/20",
    red:    "from-red-500/10 to-red-600/5 border-red-500/20",
    orange: "from-orange-500/10 to-orange-600/5 border-orange-500/20",
    purple: "from-purple-500/10 to-purple-600/5 border-purple-500/20",
    yellow: "from-yellow-500/10 to-yellow-600/5 border-yellow-500/20",
  };
  const iconColors = {
    blue: "text-blue-400", green: "text-emerald-400", red: "text-red-400",
    orange: "text-orange-400", purple: "text-purple-400", yellow: "text-yellow-400",
  };
  return (
    <div className={`bg-gradient-to-br ${colors[color]} border rounded-xl p-4 flex items-start gap-3`}>
      <div className={`p-2 rounded-lg bg-card/50 ${iconColors[color]}`}>
        <Icon size={20} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-muted-foreground truncate">{label}</p>
        <p className="text-xl font-bold text-foreground mt-0.5 truncate">{fmtK(value)}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
        {trend !== undefined && (
          <p className={`text-xs mt-0.5 flex items-center gap-0.5 ${trend >= 0 ? "text-emerald-400" : "text-red-400"}`}>
            {trend >= 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
            {Math.abs(trend).toFixed(1)}%
          </p>
        )}
      </div>
    </div>
  );
}

// ─── Ageing Bar ──────────────────────────────────────────────────────────────
function AgeingBar({ data }) {
  const buckets = [
    { key: "current",  label: "Current",    color: "bg-emerald-500" },
    { key: "0_30",     label: "0–30",       color: "bg-yellow-500" },
    { key: "31_60",    label: "31–60",      color: "bg-orange-500" },
    { key: "61_90",    label: "61–90",      color: "bg-red-400" },
    { key: "90_180",   label: "90–180",     color: "bg-red-500" },
    { key: "180_plus", label: "180+",       color: "bg-red-700" },
  ];
  const total = buckets.reduce((s, b) => s + (data?.[b.key] ?? 0), 0) || 1;
  return (
    <div>
      <div className="flex h-3 rounded-full overflow-hidden gap-0.5">
        {buckets.map((b) => {
          const pct = ((data?.[b.key] ?? 0) / total) * 100;
          return pct > 0 ? (
            <div
              key={b.key}
              className={`${b.color} transition-all`}
              style={{ width: `${pct}%` }}
              title={`${b.label}: ${fmt(data?.[b.key])}`}
            />
          ) : null;
        })}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
        {buckets.map((b) => (
          <div key={b.key} className="flex items-center gap-1 text-xs text-muted-foreground">
            <span className={`w-2 h-2 rounded-full ${b.color}`} />
            <span>{b.label}: {fmtK(data?.[b.key] ?? 0)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Dashboard Tab ────────────────────────────────────────────────────────────
function DashboardTab() {
  const [dash, setDash]     = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/debtors-creditors/dashboard");
      setDash(data);
    } catch { toast.error("Failed to load dashboard"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex justify-center py-20"><Spinner size={32} /></div>;
  if (!dash)   return <EmptyState message="Could not load dashboard." />;

  return (
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Debtors (AR)" value={dash.total_debtors}   icon={TrendingUp}   color="blue" />
        <StatCard label="Total Creditors (AP)" value={dash.total_creditors} icon={TrendingDown} color="purple" />
        <StatCard label="Overdue Receivables" value={dash.overdue_receivables} icon={AlertCircle} color="red" />
        <StatCard label="Overdue Payables"    value={dash.overdue_payables}    icon={AlertCircle} color="orange" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Today's Receipts"  value={dash.today_receipts}   icon={CheckCircle2}  color="green" />
        <StatCard label="Today's Payments"  value={dash.today_payments}   icon={CreditCard}    color="yellow" />
        <StatCard label="Net Outstanding"   value={dash.net_outstanding}  icon={DollarSign}    color="blue"
          sub={dash.net_outstanding >= 0 ? "Net receivable" : "Net payable"} />
        <StatCard label="Collection Eff. (30d)" value={`${dash.collection_efficiency_30d}%`}
          icon={BarChart2} color="green"
          sub={`${dash.collection_efficiency_30d >= 80 ? "On track" : "Needs attention"}`} />
      </div>

      {/* Top 10 Debtors / Creditors */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <h3 className="font-semibold text-foreground mb-3 flex items-center gap-2">
            <Users size={16} className="text-primary" /> Top 10 Debtors
          </h3>
          <div className="space-y-2">
            {(dash.top_debtors || []).map((d, i) => (
              <div key={d.party_id} className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground w-5">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-foreground truncate">{d.party_name}</p>
                  <div className="w-full bg-secondary rounded-full h-1 mt-1">
                    <div
                      className="bg-primary h-1 rounded-full"
                      style={{ width: `${Math.min(100, (d.outstanding / (dash.top_debtors[0]?.outstanding || 1)) * 100)}%` }}
                    />
                  </div>
                </div>
                <span className="text-sm font-medium text-foreground whitespace-nowrap">{fmtK(d.outstanding)}</span>
              </div>
            ))}
            {!dash.top_debtors?.length && <p className="text-sm text-muted-foreground">No debtors.</p>}
          </div>
        </Card>

        <Card>
          <h3 className="font-semibold text-foreground mb-3 flex items-center gap-2">
            <Building2 size={16} className="text-purple-400" /> Top 10 Creditors
          </h3>
          <div className="space-y-2">
            {(dash.top_creditors || []).map((d, i) => (
              <div key={d.party_id} className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground w-5">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-foreground truncate">{d.party_name}</p>
                  <div className="w-full bg-secondary rounded-full h-1 mt-1">
                    <div
                      className="bg-purple-500 h-1 rounded-full"
                      style={{ width: `${Math.min(100, (d.outstanding / (dash.top_creditors[0]?.outstanding || 1)) * 100)}%` }}
                    />
                  </div>
                </div>
                <span className="text-sm font-medium text-foreground whitespace-nowrap">{fmtK(d.outstanding)}</span>
              </div>
            ))}
            {!dash.top_creditors?.length && <p className="text-sm text-muted-foreground">No creditors.</p>}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ─── Outstanding Tab ──────────────────────────────────────────────────────────
function OutstandingTab({ partyType }) {
  const [rows, setRows]         = useState([]);
  const [total, setTotal]       = useState(0);
  const [loading, setLoading]   = useState(false);
  const [search, setSearch]     = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [page, setPage]         = useState(1);
  const [sortBy, setSortBy]     = useState("outstanding");
  const [sortDir, setSortDir]   = useState(-1);
  const [selected, setSelected] = useState(null);
  const LIMIT = 50;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/debtors-creditors/outstanding", {
        params: { party_type: partyType, search: search || undefined,
                  overdue_only: overdueOnly, page, limit: LIMIT, sort_by: sortBy, sort_dir: sortDir }
      });
      setRows(data.items || []);
      setTotal(data.total || 0);
    } catch { toast.error("Failed to load outstanding"); }
    finally { setLoading(false); }
  }, [partyType, search, overdueOnly, page, sortBy, sortDir]);

  useEffect(() => { setPage(1); }, [partyType, search, overdueOnly]);
  useEffect(() => { load(); }, [load]);

  const toggleSort = (col) => {
    if (sortBy === col) setSortDir(d => -d);
    else { setSortBy(col); setSortDir(-1); }
  };
  const SortIcon = ({ col }) => sortBy === col
    ? (sortDir === -1 ? <ChevronDown size={13} /> : <ChevronUp size={13} />)
    : null;

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={`Search ${partyType === "customer" ? "customers" : "vendors"}…`}
            className="w-full bg-background border border-border rounded-lg pl-9 pr-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
          <input type="checkbox" checked={overdueOnly} onChange={e => setOverdueOnly(e.target.checked)}
            className="rounded border-border" />
          Overdue only
        </label>
        <Btn variant="ghost" size="sm" onClick={load}>
          <RefreshCw size={13} /> Refresh
        </Btn>
      </div>

      {/* Totals bar */}
      {rows.length > 0 && (
        <div className="flex flex-wrap gap-4 px-4 py-3 bg-secondary/50 rounded-lg text-sm">
          <span className="text-muted-foreground">Showing {rows.length} of {total}</span>
          <span className="text-foreground font-medium">
            Total: {fmt(rows.reduce((s, r) => s + Number(r.outstanding ?? 0), 0))}
          </span>
          <span className="text-red-400">
            Overdue: {fmt(rows.reduce((s, r) => s + Number(r.overdue_amount ?? 0), 0))}
          </span>
        </div>
      )}

      {/* Table */}
      <div className="border border-border rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-secondary/50 text-left text-xs text-muted-foreground">
              <th className="px-4 py-3 cursor-pointer" onClick={() => toggleSort("party_name")}>
                <span className="flex items-center gap-1">{partyType === "customer" ? "Customer" : "Vendor"} <SortIcon col="party_name" /></span>
              </th>
              <th className="px-4 py-3">Mobile</th>
              <th className="px-4 py-3">GSTIN</th>
              <th className="px-4 py-3 cursor-pointer" onClick={() => toggleSort("outstanding")}>
                <span className="flex items-center gap-1">Outstanding <SortIcon col="outstanding" /></span>
              </th>
              <th className="px-4 py-3 cursor-pointer" onClick={() => toggleSort("overdue_amount")}>
                <span className="flex items-center gap-1">Overdue <SortIcon col="overdue_amount" /></span>
              </th>
              <th className="px-4 py-3">Last Txn</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} className="py-12 text-center"><Spinner /></td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={7}><EmptyState /></td></tr>
            )}
            {!loading && rows.map((row) => (
              <tr key={row.party_id} className="border-t border-border hover:bg-accent/30 transition-colors">
                <td className="px-4 py-3">
                  <p className="font-medium text-foreground">{row.party_name}</p>
                  <p className="text-xs text-muted-foreground">{row.city}</p>
                </td>
                <td className="px-4 py-3 text-muted-foreground">{row.mobile || "—"}</td>
                <td className="px-4 py-3 text-xs font-mono text-muted-foreground">{row.gstin || "—"}</td>
                <td className="px-4 py-3 font-medium text-foreground">{fmt(row.outstanding)}</td>
                <td className="px-4 py-3">
                  {Number(row.overdue_amount) > 0
                    ? <span className="text-red-400 font-medium">{fmt(row.overdue_amount)}</span>
                    : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="px-4 py-3 text-muted-foreground text-xs">{row.last_txn_date?.slice(0, 10) || "—"}</td>
                <td className="px-4 py-3">
                  <Btn variant="ghost" size="sm" onClick={() => setSelected(row)}>
                    <Eye size={13} /> Ledger
                  </Btn>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {total > LIMIT && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>Page {page} of {Math.ceil(total / LIMIT)}</span>
          <div className="flex gap-2">
            <Btn variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>Prev</Btn>
            <Btn variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page * LIMIT >= total}>Next</Btn>
          </div>
        </div>
      )}

      {/* Ledger Drawer */}
      {selected && (
        <LedgerModal partyType={partyType} partyId={selected.party_id}
          partyName={selected.party_name} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

// ─── Ledger Modal ─────────────────────────────────────────────────────────────
function LedgerModal({ partyType, partyId, partyName, onClose }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate]     = useState(today());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/debtors-creditors/ledger", {
        params: { party_type: partyType, party_id: partyId,
                  from_date: fromDate || undefined, to_date: toDate || undefined, limit: 500 }
      });
      setEntries(data.items || []);
    } catch { toast.error("Failed to load ledger"); }
    finally { setLoading(false); }
  }, [partyType, partyId, fromDate, toDate]);

  useEffect(() => { load(); }, [load]);

  const totalDebit  = entries.reduce((s, e) => s + Number(e.debit  ?? 0), 0);
  const totalCredit = entries.reduce((s, e) => s + Number(e.credit ?? 0), 0);
  const closing     = totalDebit - totalCredit;

  return (
    <Modal open onClose={onClose} title={`Ledger — ${partyName}`} wide>
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2 items-end">
          <Input label="From" type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} className="w-36" />
          <Input label="To"   type="date" value={toDate}   onChange={e => setToDate(e.target.value)}   className="w-36" />
          <Btn onClick={load} variant="primary" size="sm"><RefreshCw size={13} /> Apply</Btn>
        </div>

        {/* Summary */}
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div className="bg-secondary/50 rounded-lg p-3 text-center">
            <p className="text-xs text-muted-foreground">Total Debit</p>
            <p className="font-bold text-foreground">{fmt(totalDebit)}</p>
          </div>
          <div className="bg-secondary/50 rounded-lg p-3 text-center">
            <p className="text-xs text-muted-foreground">Total Credit</p>
            <p className="font-bold text-foreground">{fmt(totalCredit)}</p>
          </div>
          <div className={`rounded-lg p-3 text-center ${closing >= 0 ? "bg-red-900/20" : "bg-emerald-900/20"}`}>
            <p className="text-xs text-muted-foreground">Balance</p>
            <p className={`font-bold ${closing >= 0 ? "text-red-400" : "text-emerald-400"}`}>{fmt(Math.abs(closing))}</p>
          </div>
        </div>

        <div className="overflow-x-auto border border-border rounded-xl">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-secondary/50 text-muted-foreground">
                <th className="px-3 py-2 text-left">Date</th>
                <th className="px-3 py-2 text-left">Voucher No</th>
                <th className="px-3 py-2 text-left">Type</th>
                <th className="px-3 py-2 text-left">Narration</th>
                <th className="px-3 py-2 text-right">Debit</th>
                <th className="px-3 py-2 text-right">Credit</th>
                <th className="px-3 py-2 text-right">Balance</th>
                <th className="px-3 py-2 text-center">Status</th>
                <th className="px-3 py-2 text-center">Age</th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={9} className="py-8 text-center"><Spinner /></td></tr>}
              {!loading && entries.length === 0 && <tr><td colSpan={9}><EmptyState /></td></tr>}
              {!loading && entries.map((e) => (
                <tr key={e.id} className="border-t border-border hover:bg-accent/20">
                  <td className="px-3 py-2 text-muted-foreground">{e.entry_date?.slice(0, 10)}</td>
                  <td className="px-3 py-2 font-mono">{e.voucher_no}</td>
                  <td className="px-3 py-2 text-muted-foreground">{e.voucher_type?.replace(/_/g, " ")}</td>
                  <td className="px-3 py-2 text-muted-foreground max-w-[180px] truncate">{e.narration}</td>
                  <td className="px-3 py-2 text-right">{Number(e.debit)  > 0 ? fmt(e.debit)  : "—"}</td>
                  <td className="px-3 py-2 text-right">{Number(e.credit) > 0 ? fmt(e.credit) : "—"}</td>
                  <td className={`px-3 py-2 text-right font-medium ${Number(e.running_balance) >= 0 ? "text-red-400" : "text-emerald-400"}`}>
                    {fmt(Math.abs(e.running_balance))}
                  </td>
                  <td className="px-3 py-2 text-center">{statusBadge(e.status)}</td>
                  <td className={`px-3 py-2 text-center ${ageBucketColor(e.overdue_days)}`}>
                    {e.overdue_days > 0 ? `${e.overdue_days}d` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Modal>
  );
}

// ─── Ageing Report Tab ────────────────────────────────────────────────────────
function AgeingTab({ partyType }) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(false);
  const [asOf, setAsOf]       = useState(today());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get("/debtors-creditors/ageing", {
        params: { party_type: partyType, as_of_date: asOf }
      });
      setData(d);
    } catch { toast.error("Failed to load ageing report"); }
    finally { setLoading(false); }
  }, [partyType, asOf]);

  useEffect(() => { load(); }, [load]);

  const buckets = [
    { key: "current",  label: "Current" },
    { key: "0_30",     label: "0–30 Days" },
    { key: "31_60",    label: "31–60 Days" },
    { key: "61_90",    label: "61–90 Days" },
    { key: "90_180",   label: "90–180 Days" },
    { key: "180_plus", label: "180+ Days" },
  ];
  const bucketColors = {
    current: "text-emerald-400", "0_30": "text-yellow-400",
    "31_60": "text-orange-400",  "61_90": "text-red-400",
    "90_180": "text-red-500",    "180_plus": "text-red-600",
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Input label="As of Date" type="date" value={asOf} onChange={e => setAsOf(e.target.value)} className="w-40" />
        <Btn onClick={load} variant="primary" size="sm"><RefreshCw size={13} /> Refresh</Btn>
      </div>

      {data && (
        <Card>
          <h3 className="text-sm font-medium text-muted-foreground mb-3">Ageing Summary</h3>
          <AgeingBar data={data.totals} />
          <div className="grid grid-cols-3 md:grid-cols-7 gap-3 mt-4">
            {buckets.map(b => (
              <div key={b.key} className="text-center">
                <p className="text-xs text-muted-foreground">{b.label}</p>
                <p className={`text-sm font-bold mt-1 ${bucketColors[b.key]}`}>{fmtK(data.totals[b.key] ?? 0)}</p>
              </div>
            ))}
            <div className="text-center">
              <p className="text-xs text-muted-foreground">Total</p>
              <p className="text-sm font-bold mt-1 text-foreground">{fmtK(data.totals.total ?? 0)}</p>
            </div>
          </div>
        </Card>
      )}

      <div className="border border-border rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-secondary/50 text-left text-xs text-muted-foreground">
              <th className="px-4 py-3">{partyType === "customer" ? "Customer" : "Vendor"}</th>
              {buckets.map(b => <th key={b.key} className="px-4 py-3 text-right">{b.label}</th>)}
              <th className="px-4 py-3 text-right font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={8} className="py-12 text-center"><Spinner /></td></tr>}
            {!loading && (!data?.rows?.length) && <tr><td colSpan={8}><EmptyState /></td></tr>}
            {!loading && (data?.rows || []).map((row) => (
              <tr key={row.party_id} className="border-t border-border hover:bg-accent/20">
                <td className="px-4 py-3 font-medium text-foreground">{row.party_name}</td>
                {buckets.map(b => (
                  <td key={b.key} className={`px-4 py-3 text-right ${row[b.key] > 0 ? bucketColors[b.key] : "text-muted-foreground"}`}>
                    {row[b.key] > 0 ? fmt(row[b.key]) : "—"}
                  </td>
                ))}
                <td className="px-4 py-3 text-right font-bold text-foreground">{fmt(row.total)}</td>
              </tr>
            ))}
            {/* Totals row */}
            {data?.totals && (
              <tr className="border-t-2 border-border bg-secondary/30">
                <td className="px-4 py-3 font-bold text-foreground">Total</td>
                {buckets.map(b => (
                  <td key={b.key} className={`px-4 py-3 text-right font-bold ${bucketColors[b.key]}`}>
                    {data.totals[b.key] > 0 ? fmt(data.totals[b.key]) : "—"}
                  </td>
                ))}
                <td className="px-4 py-3 text-right font-bold text-foreground">{fmt(data.totals.total)}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Invoice Outstanding Tab ──────────────────────────────────────────────────
function InvoiceOutstandingTab({ partyType }) {
  const [rows, setRows]         = useState([]);
  const [total, setTotal]       = useState(0);
  const [loading, setLoading]   = useState(false);
  const [search, setSearch]     = useState("");
  const [status, setStatus]     = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate]     = useState("");
  const [page, setPage]         = useState(1);
  const LIMIT = 50;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/debtors-creditors/invoice-outstanding", {
        params: {
          party_type: partyType, search: search || undefined,
          status: status || undefined, from_date: fromDate || undefined,
          to_date: toDate || undefined, overdue_only: overdueOnly, page, limit: LIMIT
        }
      });
      setRows(data.items || []);
      setTotal(data.total || 0);
    } catch { toast.error("Failed to load invoice outstanding"); }
    finally { setLoading(false); }
  }, [partyType, search, status, fromDate, toDate, overdueOnly, page]);

  useEffect(() => { setPage(1); }, [partyType, search, status, overdueOnly]);
  useEffect(() => { load(); }, [load]);

  const [alloc, setAlloc] = useState(null); // invoice row for allocation

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search invoice / party…"
            className="bg-background border border-border rounded-lg pl-9 pr-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <Select value={status} onChange={e => setStatus(e.target.value)} label="Status">
          <option value="">All Status</option>
          <option value="OPEN">Open</option>
          <option value="PARTIALLY_PAID">Partially Paid</option>
          <option value="OVERDUE">Overdue</option>
          <option value="PAID">Paid</option>
          <option value="CANCELLED">Cancelled</option>
        </Select>
        <Input label="From" type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} className="w-36" />
        <Input label="To"   type="date" value={toDate}   onChange={e => setToDate(e.target.value)}   className="w-36" />
        <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer mt-4">
          <input type="checkbox" checked={overdueOnly} onChange={e => setOverdueOnly(e.target.checked)} className="rounded" />
          Overdue only
        </label>
        <Btn variant="ghost" size="sm" onClick={load} className="mt-4"><RefreshCw size={13} /></Btn>
      </div>

      {rows.length > 0 && (
        <div className="flex flex-wrap gap-4 px-4 py-2 bg-secondary/50 rounded-lg text-sm">
          <span className="text-muted-foreground">{total} records</span>
          <span>Outstanding: <b className="text-foreground">{fmt(rows.reduce((s, r) => s + Number(r.outstanding ?? 0), 0))}</b></span>
        </div>
      )}

      <div className="border border-border rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-secondary/50 text-left text-xs text-muted-foreground">
              <th className="px-4 py-3">{partyType === "customer" ? "Customer" : "Vendor"}</th>
              <th className="px-4 py-3">Invoice No</th>
              <th className="px-4 py-3">Invoice Date</th>
              <th className="px-4 py-3">Due Date</th>
              <th className="px-4 py-3 text-right">Amount</th>
              <th className="px-4 py-3 text-right">Paid</th>
              <th className="px-4 py-3 text-right">Outstanding</th>
              <th className="px-4 py-3">Ageing</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={10} className="py-12 text-center"><Spinner /></td></tr>}
            {!loading && rows.length === 0 && <tr><td colSpan={10}><EmptyState /></td></tr>}
            {!loading && rows.map((row) => (
              <tr key={row.id} className="border-t border-border hover:bg-accent/20 transition-colors">
                <td className="px-4 py-3 font-medium text-foreground">{row.party_name}</td>
                <td className="px-4 py-3 font-mono text-xs">{row.voucher_no}</td>
                <td className="px-4 py-3 text-muted-foreground">{row.entry_date?.slice(0, 10)}</td>
                <td className="px-4 py-3 text-muted-foreground">{row.due_date?.slice(0, 10) || "—"}</td>
                <td className="px-4 py-3 text-right">{fmt(row.face_value)}</td>
                <td className="px-4 py-3 text-right text-emerald-400">{row.paid_amount > 0 ? fmt(row.paid_amount) : "—"}</td>
                <td className="px-4 py-3 text-right font-medium text-foreground">{fmt(row.outstanding)}</td>
                <td className={`px-4 py-3 text-xs ${ageBucketColor(row.overdue_days)}`}>
                  {ageBucketLabel(row.overdue_days)}
                </td>
                <td className="px-4 py-3">{statusBadge(row.status)}</td>
                <td className="px-4 py-3">
                  {row.status !== "PAID" && row.status !== "CANCELLED" && (
                    <Btn variant="ghost" size="sm" onClick={() => setAlloc(row)}>
                      <CreditCard size={13} /> Allocate
                    </Btn>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {total > LIMIT && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>Page {page}</span>
          <div className="flex gap-2">
            <Btn variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>Prev</Btn>
            <Btn variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page * LIMIT >= total}>Next</Btn>
          </div>
        </div>
      )}

      {alloc && (
        <AllocateModal
          partyType={partyType}
          invoiceEntry={alloc}
          onClose={() => setAlloc(null)}
          onDone={() => { setAlloc(null); load(); }}
        />
      )}
    </div>
  );
}

// ─── Allocate Modal ───────────────────────────────────────────────────────────
function AllocateModal({ partyType, invoiceEntry, onClose, onDone }) {
  const [paymentEntries, setPaymentEntries] = useState([]);
  const [selectedPayment, setSelectedPayment] = useState("");
  const [amount, setAmount]           = useState(String(invoiceEntry.outstanding));
  const [tds, setTds]                 = useState("0");
  const [discount, setDiscount]       = useState("0");
  const [roundOff, setRoundOff]       = useState("0");
  const [saving, setSaving]           = useState(false);

  useEffect(() => {
    api.get("/debtors-creditors/ledger", {
      params: { party_type: partyType, party_id: invoiceEntry.party_id,
                voucher_type: partyType === "customer" ? "RECEIPT" : "PAYMENT", limit: 200 }
    }).then(r => setPaymentEntries(r.data.items || [])).catch(() => {});
  }, [partyType, invoiceEntry.party_id]);

  const save = async () => {
    if (!selectedPayment) { toast.error("Select a payment entry"); return; }
    setSaving(true);
    try {
      await api.post("/debtors-creditors/allocate-payment", {
        party_type: partyType, party_id: invoiceEntry.party_id,
        payment_entry_id: selectedPayment,
        allocations: [{
          invoice_entry_id: invoiceEntry.id,
          allocated_amount: parseFloat(amount) || 0,
          tds_amount:       parseFloat(tds) || 0,
          discount_amount:  parseFloat(discount) || 0,
          round_off:        parseFloat(roundOff) || 0,
        }]
      });
      toast.success("Payment allocated successfully");
      onDone();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Allocation failed");
    } finally {
      setSaving(false);
    }
  };

  // Enter-as-Tab across the Allocate Payment form; Ctrl+Enter/Ctrl+S saves,
  // Esc cancels, first field auto-focuses when the modal opens.
  const allocateFormRef = useRef(null);
  useEnterNavigation(allocateFormRef, {
    enabled: true,
    autoFocus: true,
    onSave: () => save(),
    onCancel: onClose,
  });

  return (
    <Modal open onClose={onClose} title={`Allocate Payment — ${invoiceEntry.voucher_no}`}>
      <div ref={allocateFormRef} className="space-y-4">
        <div className="bg-secondary/50 rounded-lg p-3 text-sm">
          <div className="flex justify-between"><span className="text-muted-foreground">Party:</span><span className="font-medium">{invoiceEntry.party_name}</span></div>
          <div className="flex justify-between mt-1"><span className="text-muted-foreground">Outstanding:</span><span className="font-bold text-red-400">{fmt(invoiceEntry.outstanding)}</span></div>
        </div>
        <Select label="Payment Entry" value={selectedPayment} onChange={e => setSelectedPayment(e.target.value)}>
          <option value="">— Select payment —</option>
          {paymentEntries.map(p => (
            <option key={p.id} value={p.id}>
              {p.voucher_no} | {p.entry_date?.slice(0, 10)} | {fmt(p.credit || p.debit)}
            </option>
          ))}
        </Select>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Allocated Amount (₹)" type="text" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} />
          <Input label="TDS (₹)"              type="text" inputMode="decimal" value={tds}    onChange={e => setTds(e.target.value)} />
          <Input label="Discount (₹)"         type="text" inputMode="decimal" value={discount} onChange={e => setDiscount(e.target.value)} />
          <Input label="Round Off (₹)"        type="text" inputMode="decimal" value={roundOff} onChange={e => setRoundOff(e.target.value)} />
        </div>
        <div className="flex gap-2 justify-end">
          <Btn variant="outline" onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" onClick={save} disabled={saving}>
            {saving ? <Spinner size={13} /> : <CheckCircle2 size={13} />} Allocate
          </Btn>
        </div>
      </div>
    </Modal>
  );
}

// ─── Collection Notes Tab ─────────────────────────────────────────────────────
function CollectionTab({ partyType }) {
  const [notes, setNotes]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [partySearch, setPartySearch] = useState("");
  const [parties, setParties] = useState([]);
  const [form, setForm] = useState({
    party_id: "", party_name: "", note: "", reminder_type: "CALL",
    promise_date: "", promise_amount: "", collection_executive: "", outcome: "",
  });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/debtors-creditors/collection-notes", {
        params: { party_type: partyType, limit: 50 }
      });
      setNotes(data.items || []);
      setTotal(data.total || 0);
    } catch { toast.error("Failed to load collection notes"); }
    finally { setLoading(false); }
  }, [partyType]);

  useEffect(() => { load(); }, [load]);

  const searchParties = useCallback(async (q) => {
    if (!q) { setParties([]); return; }
    const coll = partyType === "customer" ? "/customers" : "/vendors";
    try {
      const { data } = await api.get(coll, { params: { search: q, limit: 20 } });
      setParties(data.items || data || []);
    } catch {}
  }, [partyType]);

  useEffect(() => { searchParties(partySearch); }, [partySearch, searchParties]);

  const setParty = (p) => {
    setForm(f => ({ ...f, party_id: p.id, party_name: p.name }));
    setPartySearch(p.name);
    setParties([]);
  };

  const save = async () => {
    if (!form.party_id) { toast.error("Select a party"); return; }
    if (!form.note.trim()) { toast.error("Enter a note"); return; }
    setSaving(true);
    try {
      await api.post("/debtors-creditors/collection-notes", {
        party_type: partyType, party_id: form.party_id,
        note: form.note, reminder_type: form.reminder_type,
        promise_date:  form.promise_date  || undefined,
        promise_amount: parseFloat(form.promise_amount) || undefined,
        collection_executive: form.collection_executive || undefined,
        outcome: form.outcome || undefined,
      });
      toast.success("Collection note saved");
      setShowForm(false);
      setForm({ party_id: "", party_name: "", note: "", reminder_type: "CALL", promise_date: "", promise_amount: "", collection_executive: "", outcome: "" });
      setPartySearch("");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  // Enter-as-Tab across the New Collection Note form; Ctrl+Enter/Ctrl+S
  // saves, Esc cancels, first field auto-focuses when the panel opens.
  const collectionFormRef = useRef(null);
  useEnterNavigation(collectionFormRef, {
    enabled: showForm,
    autoFocus: true,
    onSave: () => save(),
    onCancel: () => setShowForm(false),
  });

  const sendReminder = async (note, channel) => {
    const party = partyType === "customer"
      ? await api.get(`/customers/${note.party_id}`).then(r => r.data).catch(() => null)
      : await api.get(`/vendors/${note.party_id}`).then(r => r.data).catch(() => null);
    const recipient = channel === "EMAIL"
      ? (party?.email || "")
      : (party?.phone || "");
    if (!recipient) { toast.error(`No ${channel.toLowerCase()} on file`); return; }
    try {
      await api.post("/debtors-creditors/reminders/send", {
        party_type: partyType, party_id: note.party_id,
        channel, recipient,
      });
      toast.success(`${channel} reminder logged`);
    } catch { toast.error("Failed to log reminder"); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-foreground">{total} Collection Notes</h3>
        <div className="flex gap-2">
          <Btn variant="ghost" size="sm" onClick={load}><RefreshCw size={13} /></Btn>
          <Btn variant="primary" size="sm" onClick={() => setShowForm(true)}>
            <Plus size={13} /> Add Note
          </Btn>
        </div>
      </div>

      {/* Add Note Form */}
      {showForm && (
        <Card className="border-primary/30">
          <h4 className="font-medium text-foreground mb-3">New Collection Note</h4>
          <div ref={collectionFormRef} className="space-y-3">
            <div className="relative">
              <Input label={partyType === "customer" ? "Customer" : "Vendor"} value={partySearch}
                onChange={e => { setPartySearch(e.target.value); setForm(f => ({ ...f, party_id: "", party_name: "" })); }}
                placeholder="Search by name…" />
              {parties.length > 0 && (
                <div className="absolute z-10 top-full left-0 right-0 bg-card border border-border rounded-lg mt-1 shadow-xl overflow-y-auto max-h-40">
                  {parties.map(p => (
                    <button key={p.id} onClick={() => setParty(p)}
                      className="w-full px-3 py-2 text-sm text-left hover:bg-accent text-foreground">
                      {p.name} {p.gstin ? `(${p.gstin})` : ""}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Select label="Type" value={form.reminder_type} onChange={e => setForm(f => ({ ...f, reminder_type: e.target.value }))}>
                {["EMAIL","WHATSAPP","SMS","CALL","VISIT"].map(t => <option key={t}>{t}</option>)}
              </Select>
              <Input label="Promise Date" type="date" value={form.promise_date} onChange={e => setForm(f => ({ ...f, promise_date: e.target.value }))} />
              <Input label="Promise Amount" type="text" inputMode="decimal" value={form.promise_amount} onChange={e => setForm(f => ({ ...f, promise_amount: e.target.value }))} />
              <Input label="Collection Executive" value={form.collection_executive} onChange={e => setForm(f => ({ ...f, collection_executive: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Note</label>
              <textarea rows={3} value={form.note} onChange={e => setForm(f => ({ ...f, note: e.target.value }))}
                className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground resize-none focus:outline-none focus:ring-1 focus:ring-primary" />
            </div>
            <Input label="Outcome" value={form.outcome} onChange={e => setForm(f => ({ ...f, outcome: e.target.value }))} placeholder="e.g. Payment promised by Friday" />
            <div className="flex gap-2 justify-end">
              <Btn variant="outline" onClick={() => setShowForm(false)}>Cancel</Btn>
              <Btn variant="primary" onClick={save} disabled={saving}>
                {saving ? <Spinner size={13} /> : <Plus size={13} />} Save
              </Btn>
            </div>
          </div>
        </Card>
      )}

      {/* Notes list */}
      {loading && <div className="flex justify-center py-8"><Spinner /></div>}
      {!loading && notes.length === 0 && <EmptyState message="No collection notes yet." />}
      {!loading && notes.map(note => (
        <Card key={note.id} className="group">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-secondary">
              <MessageSquare size={16} className="text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-foreground">{note.party_name}</span>
                <Badge color={
                  note.reminder_type === "CALL" ? "blue" :
                  note.reminder_type === "EMAIL" ? "purple" :
                  note.reminder_type === "WHATSAPP" ? "green" : "default"
                }>{note.reminder_type}</Badge>
                {note.promise_date && (
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <Calendar size={11} /> Promise: {note.promise_date}
                    {note.promise_amount ? ` (${fmt(note.promise_amount)})` : ""}
                  </span>
                )}
              </div>
              <p className="text-sm text-foreground mt-1">{note.note}</p>
              {note.outcome && <p className="text-xs text-muted-foreground mt-1 italic">Outcome: {note.outcome}</p>}
              <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                {note.collection_executive && <span>{note.collection_executive}</span>}
                <span>{note.created_at?.slice(0, 10)}</span>
              </div>
            </div>
            <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <Btn variant="ghost" size="sm" onClick={() => sendReminder(note, "EMAIL")} title="Email reminder">
                <Mail size={13} />
              </Btn>
              <Btn variant="ghost" size="sm" onClick={() => sendReminder(note, "WHATSAPP")} title="WhatsApp reminder">
                <Phone size={13} />
              </Btn>
              <Btn variant="ghost" size="sm" onClick={() => sendReminder(note, "SMS")} title="SMS reminder">
                <Send size={13} />
              </Btn>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

// ─── Credit Limit Tab ─────────────────────────────────────────────────────────
function CreditLimitTab() {
  const [rows, setRows]       = useState([]);
  const [loading, setLoading] = useState(false);
  const [editRow, setEditRow] = useState(null);
  const [customers, setCustomers] = useState([]);
  const [custSearch, setCustSearch] = useState("");
  const [form, setForm] = useState({ customer_id: "", customer_name: "", credit_limit: "", payment_terms: "30", credit_hold: false, notes: "" });
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/debtors-creditors/credit-limits");
      setRows(data || []);
    } catch { toast.error("Failed to load credit limits"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const searchCust = useCallback(async (q) => {
    if (!q) { setCustomers([]); return; }
    try {
      const { data } = await api.get("/customers", { params: { search: q, limit: 20 } });
      setCustomers(data.items || data || []);
    } catch {}
  }, []);

  useEffect(() => { searchCust(custSearch); }, [custSearch, searchCust]);

  const save = async () => {
    if (!form.customer_id) { toast.error("Select a customer"); return; }
    setSaving(true);
    try {
      await api.post("/debtors-creditors/credit-limits", {
        customer_id:   form.customer_id,
        credit_limit:  parseFloat(form.credit_limit) || 0,
        payment_terms: parseInt(form.payment_terms)  || 30,
        credit_hold:   form.credit_hold,
        notes:         form.notes,
      });
      toast.success("Credit limit saved");
      setShowForm(false);
      setForm({ customer_id: "", customer_name: "", credit_limit: "", payment_terms: "30", credit_hold: false, notes: "" });
      setCustSearch("");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    } finally { setSaving(false); }
  };

  // Enter-as-Tab across the Set Credit Limit form; Ctrl+Enter/Ctrl+S saves,
  // Esc cancels, first field auto-focuses when the panel opens.
  const creditLimitFormRef = useRef(null);
  useEnterNavigation(creditLimitFormRef, {
    enabled: showForm,
    autoFocus: true,
    onSave: () => save(),
    onCancel: () => setShowForm(false),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-foreground">Customer Credit Limits</h3>
        <Btn variant="primary" size="sm" onClick={() => setShowForm(true)}>
          <Plus size={13} /> Set Limit
        </Btn>
      </div>

      {showForm && (
        <Card className="border-primary/30">
          <h4 className="font-medium mb-3">Set Credit Limit</h4>
          <div ref={creditLimitFormRef} className="space-y-3">
            <div className="relative">
              <Input label="Customer" value={custSearch}
                onChange={e => { setCustSearch(e.target.value); setForm(f => ({ ...f, customer_id: "" })); }}
                placeholder="Search customer…" />
              {customers.length > 0 && (
                <div className="absolute z-10 top-full left-0 right-0 bg-card border border-border rounded-lg mt-1 shadow-xl max-h-40 overflow-y-auto">
                  {customers.map(c => (
                    <button key={c.id} onClick={() => { setForm(f => ({ ...f, customer_id: c.id, customer_name: c.name })); setCustSearch(c.name); setCustomers([]); }}
                      className="w-full px-3 py-2 text-sm text-left hover:bg-accent text-foreground">{c.name}</button>
                  ))}
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Credit Limit (₹)" type="text" inputMode="decimal" value={form.credit_limit} onChange={e => setForm(f => ({ ...f, credit_limit: e.target.value }))} />
              <Input label="Payment Terms (days)" type="text" inputMode="decimal" value={form.payment_terms} onChange={e => setForm(f => ({ ...f, payment_terms: e.target.value }))} />
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.credit_hold} onChange={e => setForm(f => ({ ...f, credit_hold: e.target.checked }))} className="rounded" />
              <span className="text-foreground">Credit Hold</span>
            </label>
            <Input label="Notes" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
            <div className="flex gap-2 justify-end">
              <Btn variant="outline" onClick={() => setShowForm(false)}>Cancel</Btn>
              <Btn variant="primary" onClick={save} disabled={saving}>
                {saving ? <Spinner size={13} /> : <CheckCircle2 size={13} />} Save
              </Btn>
            </div>
          </div>
        </Card>
      )}

      <div className="border border-border rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-secondary/50 text-left text-xs text-muted-foreground">
              <th className="px-4 py-3">Customer</th>
              <th className="px-4 py-3 text-right">Credit Limit</th>
              <th className="px-4 py-3 text-right">Outstanding</th>
              <th className="px-4 py-3 text-right">Available</th>
              <th className="px-4 py-3">Terms</th>
              <th className="px-4 py-3">Hold</th>
              <th className="px-4 py-3">Notes</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={7} className="py-12 text-center"><Spinner /></td></tr>}
            {!loading && rows.length === 0 && <tr><td colSpan={7}><EmptyState /></td></tr>}
            {!loading && rows.map(row => (
              <tr key={row.id} className="border-t border-border hover:bg-accent/20">
                <td className="px-4 py-3 font-medium text-foreground">{row.customer_id}</td>
                <td className="px-4 py-3 text-right">{fmt(row.credit_limit)}</td>
                <td className="px-4 py-3 text-right text-red-400">—</td>
                <td className="px-4 py-3 text-right text-emerald-400">—</td>
                <td className="px-4 py-3 text-muted-foreground">{row.payment_terms}d</td>
                <td className="px-4 py-3">
                  {row.credit_hold
                    ? <Badge color="red">Hold</Badge>
                    : <Badge color="green">Active</Badge>}
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground">{row.notes || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Reports Tab ──────────────────────────────────────────────────────────────
function ReportsTab({ partyType }) {
  const [reportType, setReportType] = useState("statement");
  const [partyId, setPartyId]       = useState("");
  const [partyName, setPartyName]   = useState("");
  const [partySearch, setPartySearch] = useState("");
  const [parties, setParties]       = useState([]);
  const [fromDate, setFromDate]     = useState("");
  const [toDate, setToDate]         = useState(today());
  const [data, setData]             = useState(null);
  const [loading, setLoading]       = useState(false);

  const searchParties = useCallback(async (q) => {
    if (!q) { setParties([]); return; }
    const coll = partyType === "customer" ? "/customers" : "/vendors";
    try {
      const { data } = await api.get(coll, { params: { search: q, limit: 20 } });
      setParties(data.items || data || []);
    } catch {}
  }, [partyType]);

  useEffect(() => { searchParties(partySearch); }, [partySearch, searchParties]);

  const run = async () => {
    setLoading(true);
    setData(null);
    try {
      if (reportType === "statement") {
        if (!partyId) { toast.error("Select a party"); setLoading(false); return; }
        const { data: d } = await api.get("/debtors-creditors/reports/statement", {
          params: { party_type: partyType, party_id: partyId, from_date: fromDate || undefined, to_date: toDate }
        });
        setData(d);
      } else if (reportType === "daily_collection") {
        if (!fromDate) { toast.error("Select from date"); setLoading(false); return; }
        const { data: d } = await api.get("/debtors-creditors/reports/daily-collection", {
          params: { from_date: fromDate, to_date: toDate }
        });
        setData(d);
      } else if (reportType === "interest") {
        const { data: d } = await api.get("/debtors-creditors/reports/interest", {
          params: { party_type: partyType }
        });
        setData(d);
      } else if (reportType === "outstanding_summary") {
        const { data: d } = await api.get("/debtors-creditors/reports/outstanding-summary", {
          params: { party_type: partyType }
        });
        setData(d);
      }
    } catch { toast.error("Report generation failed"); }
    finally { setLoading(false); }
  };

  const exportCSV = () => {
    if (!data) return;
    let csv = "";
    if (reportType === "statement" && data.rows) {
      csv = "Date,Voucher No,Type,Narration,Debit,Credit,Balance\n";
      csv += data.rows.map(r => `${r.date},${r.voucher_no},${r.voucher_type},"${r.narration}",${r.debit},${r.credit},${r.balance}`).join("\n");
    } else if (reportType === "daily_collection" && data.rows) {
      csv = "Date,Amount\n";
      csv += data.rows.map(r => `${r.date},${r.amount}`).join("\n");
    }
    if (!csv) return;
    const a = document.createElement("a");
    a.href = "data:text/csv," + encodeURIComponent(csv);
    a.download = `${reportType}_${today()}.csv`;
    a.click();
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Select label="Report Type" value={reportType} onChange={e => { setReportType(e.target.value); setData(null); }}>
          <option value="statement">Party Statement</option>
          <option value="outstanding_summary">Outstanding Summary</option>
          <option value="daily_collection">Daily Collection</option>
          <option value="interest">Interest Report</option>
        </Select>
        {["statement"].includes(reportType) && (
          <div className="relative">
            <Input label={partyType === "customer" ? "Customer" : "Vendor"} value={partySearch}
              onChange={e => { setPartySearch(e.target.value); setPartyId(""); setPartyName(""); }}
              placeholder="Search…" />
            {parties.length > 0 && (
              <div className="absolute z-10 top-full left-0 right-0 bg-card border border-border rounded-lg mt-1 shadow-xl max-h-40 overflow-y-auto">
                {parties.map(p => (
                  <button key={p.id} onClick={() => { setPartyId(p.id); setPartyName(p.name); setPartySearch(p.name); setParties([]); }}
                    className="w-full px-3 py-2 text-sm text-left hover:bg-accent text-foreground">{p.name}</button>
                ))}
              </div>
            )}
          </div>
        )}
        {["statement", "daily_collection"].includes(reportType) && (
          <>
            <Input label="From" type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} className="w-36" />
            <Input label="To"   type="date" value={toDate}   onChange={e => setToDate(e.target.value)}   className="w-36" />
          </>
        )}
        <Btn variant="primary" onClick={run} disabled={loading}>
          {loading ? <Spinner size={13} /> : <BarChart2 size={13} />} Generate
        </Btn>
        {data && <Btn variant="outline" onClick={exportCSV}><Download size={13} /> Export CSV</Btn>}
      </div>

      {/* Statement */}
      {reportType === "statement" && data && (
        <div className="space-y-3">
          <Card>
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-foreground">{data.party_name}</h3>
                <p className="text-xs text-muted-foreground">{data.from_date || "All time"} → {data.to_date}</p>
              </div>
              <div className="text-right">
                <p className="text-xs text-muted-foreground">Closing Balance</p>
                <p className={`text-lg font-bold ${data.closing_balance >= 0 ? "text-red-400" : "text-emerald-400"}`}>
                  {fmt(Math.abs(data.closing_balance))}
                  <span className="text-xs ml-1 font-normal">{data.closing_balance >= 0 ? "Dr" : "Cr"}</span>
                </p>
              </div>
            </div>
          </Card>
          <div className="border border-border rounded-xl overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-secondary/50 text-left text-muted-foreground">
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2">Voucher No</th>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Narration</th>
                  <th className="px-3 py-2 text-right">Debit</th>
                  <th className="px-3 py-2 text-right">Credit</th>
                  <th className="px-3 py-2 text-right">Balance</th>
                  <th className="px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {(data.rows || []).map((r, i) => (
                  <tr key={i} className="border-t border-border hover:bg-accent/20">
                    <td className="px-3 py-2 text-muted-foreground">{r.date}</td>
                    <td className="px-3 py-2 font-mono">{r.voucher_no}</td>
                    <td className="px-3 py-2 text-muted-foreground">{r.voucher_type?.replace(/_/g, " ")}</td>
                    <td className="px-3 py-2 text-muted-foreground max-w-[200px] truncate">{r.narration}</td>
                    <td className="px-3 py-2 text-right">{r.debit > 0 ? fmt(r.debit) : "—"}</td>
                    <td className="px-3 py-2 text-right">{r.credit > 0 ? fmt(r.credit) : "—"}</td>
                    <td className={`px-3 py-2 text-right font-medium ${r.balance >= 0 ? "text-red-400" : "text-emerald-400"}`}>
                      {fmt(Math.abs(r.balance))}
                    </td>
                    <td className="px-3 py-2">{statusBadge(r.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Daily Collection */}
      {reportType === "daily_collection" && data && (
        <div className="space-y-3">
          <Card>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">{data.from_date} → {data.to_date}</span>
              <span className="font-bold text-foreground">Total: {fmt(data.total)}</span>
            </div>
          </Card>
          <div className="border border-border rounded-xl overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-secondary/50 text-muted-foreground text-xs">
                  <th className="px-4 py-2 text-left">Date</th>
                  <th className="px-4 py-2 text-right">Collection</th>
                </tr>
              </thead>
              <tbody>
                {(data.rows || []).map((r) => (
                  <tr key={r.date} className="border-t border-border">
                    <td className="px-4 py-2">{r.date}</td>
                    <td className="px-4 py-2 text-right font-medium text-emerald-400">{fmt(r.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Interest */}
      {reportType === "interest" && data && (
        <div className="space-y-3">
          <div className="flex gap-4 text-sm">
            <Card className="flex-1 text-center">
              <p className="text-xs text-muted-foreground">Total Outstanding</p>
              <p className="font-bold text-foreground">{fmt(data.total_outstanding)}</p>
            </Card>
            <Card className="flex-1 text-center">
              <p className="text-xs text-muted-foreground">Total Interest ({data.interest_rate}% p.a.)</p>
              <p className="font-bold text-red-400">{fmt(data.total_interest)}</p>
            </Card>
          </div>
          <div className="border border-border rounded-xl overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-secondary/50 text-muted-foreground text-xs">
                  <th className="px-3 py-2 text-left">Party</th>
                  <th className="px-3 py-2 text-left">Invoice</th>
                  <th className="px-3 py-2 text-left">Due Date</th>
                  <th className="px-3 py-2 text-right">Outstanding</th>
                  <th className="px-3 py-2 text-right">Days</th>
                  <th className="px-3 py-2 text-right">Interest</th>
                </tr>
              </thead>
              <tbody>
                {(data.rows || []).map((r, i) => (
                  <tr key={i} className="border-t border-border hover:bg-accent/20">
                    <td className="px-3 py-2 font-medium">{r.party_name}</td>
                    <td className="px-3 py-2 font-mono text-xs">{r.voucher_no}</td>
                    <td className="px-3 py-2 text-muted-foreground">{r.due_date}</td>
                    <td className="px-3 py-2 text-right">{fmt(r.outstanding)}</td>
                    <td className={`px-3 py-2 text-right ${ageBucketColor(r.overdue_days)}`}>{r.overdue_days}</td>
                    <td className="px-3 py-2 text-right text-red-400 font-medium">{fmt(r.interest_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Outstanding Summary */}
      {reportType === "outstanding_summary" && data && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <StatCard label="Total Outstanding" value={data.total_outstanding} icon={DollarSign} color="blue" />
          <StatCard label="Total Overdue"     value={data.total_overdue}     icon={AlertCircle} color="red" />
          <Card>
            <p className="text-xs text-muted-foreground">Parties</p>
            <p className="text-2xl font-bold text-foreground mt-1">{data.total_parties}</p>
            <p className="text-xs text-muted-foreground mt-1">{data.parties_with_balance} with balance · {data.parties_overdue} overdue</p>
          </Card>
          <div className="md:col-span-3">
            <Card>
              <h3 className="font-medium text-foreground mb-3">Top Outstanding</h3>
              <div className="space-y-2">
                {(data.top_outstanding || []).map((p, i) => (
                  <div key={p.party_id} className="flex items-center gap-3 text-sm">
                    <span className="text-muted-foreground w-5">{i + 1}</span>
                    <span className="flex-1 text-foreground">{p.party_name}</span>
                    <span className="font-medium text-foreground">{fmt(p.outstanding)}</span>
                    <span className="text-red-400 text-xs">{fmt(p.overdue_amount)} overdue</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
const TABS = [
  { key: "dashboard",      label: "Dashboard",         icon: BarChart2 },
  { key: "debtors",        label: "Debtors (AR)",       icon: TrendingUp },
  { key: "creditors",      label: "Creditors (AP)",     icon: TrendingDown },
  { key: "inv_debtors",    label: "Invoice Outst. (AR)", icon: FileText },
  { key: "inv_creditors",  label: "Invoice Outst. (AP)", icon: FileText },
  { key: "ageing_debtors", label: "Ageing (AR)",        icon: Clock },
  { key: "ageing_creditors","label": "Ageing (AP)",     icon: Clock },
  { key: "collection",     label: "Collection",         icon: MessageSquare },
  { key: "credit_limits",  label: "Credit Limits",      icon: CreditCard },
  { key: "reports",        label: "Reports",            icon: BarChart2 },
];

export default function DebtorsCreditors() {
  const [tab, setTab]         = useState("dashboard");
  const [showNewEntry, setShowNewEntry] = useState(false);

  const currentTab = TABS.find(t => t.key === tab) || TABS[0];

  // "New Entry" is this page's one prominent, page-level create action
  // (header button, works from any tab) — so it owns the Ctrl+N shortcut.
  useModuleShortcuts({
    onNew: () => { if (!showNewEntry) setShowNewEntry(true); },
  });

  return (
    <div className="min-h-screen bg-background">
      {/* Page header */}
      <div className="sticky top-0 z-30 bg-background/95 backdrop-blur border-b border-border px-4 py-3">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-lg font-bold text-foreground">Debtors & Creditors</h1>
            <p className="text-xs text-muted-foreground">Accounts Receivable · Accounts Payable · Collection</p>
          </div>
          <div className="flex items-center gap-2">
            <Btn variant="outline" size="sm" onClick={() => setShowNewEntry(true)}>
              <Plus size={13} /> New Entry
            </Btn>
          </div>
        </div>

        {/* Tabs — horizontally scrollable on mobile */}
        <div className="flex items-center gap-1 mt-3 overflow-x-auto pb-1 scrollbar-none">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.key;
            return (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground hover:bg-accent"
                }`}
              >
                <Icon size={13} />
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Content */}
      <div className="p-4 md:p-6">
        {tab === "dashboard"        && <DashboardTab />}
        {tab === "debtors"          && <OutstandingTab partyType="customer" />}
        {tab === "creditors"        && <OutstandingTab partyType="vendor" />}
        {tab === "inv_debtors"      && <InvoiceOutstandingTab partyType="customer" />}
        {tab === "inv_creditors"    && <InvoiceOutstandingTab partyType="vendor" />}
        {tab === "ageing_debtors"   && <AgeingTab partyType="customer" />}
        {tab === "ageing_creditors" && <AgeingTab partyType="vendor" />}
        {tab === "collection"       && <CollectionTab partyType="customer" />}
        {tab === "credit_limits"    && <CreditLimitTab />}
        {tab === "reports"          && <ReportsTab partyType="customer" />}
      </div>

      {/* New Manual Entry Modal */}
      {showNewEntry && (
        <NewEntryModal
          onClose={() => setShowNewEntry(false)}
          onDone={() => { setShowNewEntry(false); }}
        />
      )}
    </div>
  );
}

// ─── New Manual Ledger Entry Modal ────────────────────────────────────────────
function NewEntryModal({ onClose, onDone }) {
  const [form, setForm] = useState({
    party_type: "customer", party_id: "", party_name: "",
    voucher_type: "SALES_INVOICE", entry_date: today(), due_date: "",
    debit: "", credit: "", narration: "",
  });
  const [parties, setParties]     = useState([]);
  const [partySearch, setPartySearch] = useState("");
  const [saving, setSaving]       = useState(false);

  const searchParties = useCallback(async (q) => {
    if (!q) { setParties([]); return; }
    const coll = form.party_type === "customer" ? "/customers" : "/vendors";
    try {
      const { data } = await api.get(coll, { params: { search: q, limit: 20 } });
      setParties(data.items || data || []);
    } catch {}
  }, [form.party_type]);

  useEffect(() => { searchParties(partySearch); }, [partySearch, searchParties]);

  const save = async () => {
    if (!form.party_id)      { toast.error("Select a party"); return; }
    if (!form.voucher_type)  { toast.error("Select voucher type"); return; }
    if (!form.entry_date)    { toast.error("Enter date"); return; }
    const debit  = parseFloat(form.debit)  || 0;
    const credit = parseFloat(form.credit) || 0;
    if (debit === 0 && credit === 0) { toast.error("Enter debit or credit amount"); return; }
    setSaving(true);
    try {
      await api.post("/debtors-creditors/ledger-entry", {
        party_type:   form.party_type,
        party_id:     form.party_id,
        voucher_type: form.voucher_type,
        entry_date:   form.entry_date,
        due_date:     form.due_date || undefined,
        debit, credit,
        narration: form.narration || undefined,
      });
      toast.success("Ledger entry created");
      onDone();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to create entry");
    } finally { setSaving(false); }
  };

  // Enter-as-Tab across the New Ledger Entry form; Ctrl+Enter/Ctrl+S saves,
  // Esc cancels, first field auto-focuses when the modal opens.
  const newEntryFormRef = useRef(null);
  useEnterNavigation(newEntryFormRef, {
    enabled: true,
    autoFocus: true,
    onSave: () => save(),
    onCancel: onClose,
  });

  const VOUCHER_TYPES_CUSTOMER = [
    "SALES_INVOICE", "RECEIPT", "CREDIT_NOTE", "DEBIT_NOTE",
    "ADVANCE_RECEIVED", "OPENING_BALANCE", "JOURNAL"
  ];
  const VOUCHER_TYPES_VENDOR = [
    "PURCHASE_BILL", "PAYMENT", "CREDIT_NOTE", "DEBIT_NOTE",
    "ADVANCE_PAID", "OPENING_BALANCE", "JOURNAL"
  ];

  return (
    <Modal open onClose={onClose} title="New Ledger Entry">
      <div ref={newEntryFormRef} className="space-y-4">
        <Select label="Party Type" value={form.party_type}
          onChange={e => { setForm(f => ({ ...f, party_type: e.target.value, party_id: "", party_name: "" })); setPartySearch(""); setParties([]); }}>
          <option value="customer">Customer (Debtor)</option>
          <option value="vendor">Vendor (Creditor)</option>
        </Select>

        <div className="relative">
          <Input label={form.party_type === "customer" ? "Customer" : "Vendor"}
            value={partySearch}
            onChange={e => { setPartySearch(e.target.value); setForm(f => ({ ...f, party_id: "", party_name: "" })); }}
            placeholder="Search…" />
          {parties.length > 0 && (
            <div className="absolute z-10 top-full left-0 right-0 bg-card border border-border rounded-lg mt-1 shadow-xl max-h-40 overflow-y-auto">
              {parties.map(p => (
                <button key={p.id}
                  onClick={() => { setForm(f => ({ ...f, party_id: p.id, party_name: p.name })); setPartySearch(p.name); setParties([]); }}
                  className="w-full px-3 py-2 text-sm text-left hover:bg-accent text-foreground">
                  {p.name}
                </button>
              ))}
            </div>
          )}
        </div>

        <Select label="Voucher Type" value={form.voucher_type}
          onChange={e => setForm(f => ({ ...f, voucher_type: e.target.value }))}>
          {(form.party_type === "customer" ? VOUCHER_TYPES_CUSTOMER : VOUCHER_TYPES_VENDOR).map(v => (
            <option key={v} value={v}>{v.replace(/_/g, " ")}</option>
          ))}
        </Select>

        <div className="grid grid-cols-2 gap-3">
          <Input label="Entry Date" type="date" value={form.entry_date}
            onChange={e => setForm(f => ({ ...f, entry_date: e.target.value }))} />
          <Input label="Due Date" type="date" value={form.due_date}
            onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))} />
          <Input label="Debit (₹)" type="text" inputMode="decimal" value={form.debit}
            onChange={e => setForm(f => ({ ...f, debit: e.target.value }))} />
          <Input label="Credit (₹)" type="text" inputMode="decimal" value={form.credit}
            onChange={e => setForm(f => ({ ...f, credit: e.target.value }))} />
        </div>

        <div>
          <label className="block text-xs text-muted-foreground mb-1">Narration</label>
          <textarea rows={2} value={form.narration}
            onChange={e => setForm(f => ({ ...f, narration: e.target.value }))}
            className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground resize-none focus:outline-none focus:ring-1 focus:ring-primary" />
        </div>

        <div className="flex gap-2 justify-end">
          <Btn variant="outline" onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" onClick={save} disabled={saving}>
            {saving ? <Spinner size={13} /> : <Plus size={13} />} Create
          </Btn>
        </div>
      </div>
    </Modal>
  );
}
