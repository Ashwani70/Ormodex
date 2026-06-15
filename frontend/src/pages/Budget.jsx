import { useState, useEffect } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  PieChart, BarChart2, Plus, RefreshCw, Trash2, Edit2,
  TrendingUp, TrendingDown, AlertTriangle, Building2, Target,
  CheckCircle2, Clock, DollarSign, ChevronDown, ChevronRight,
} from "lucide-react";

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });

const STATUS_COLORS = {
  DRAFT:    "bg-zinc-800 text-zinc-400 border-zinc-700",
  APPROVED: "bg-green-950 text-green-300 border-green-800",
  CLOSED:   "bg-purple-950 text-purple-300 border-purple-800",
};

const ALERT_COLORS = {
  CRITICAL: "bg-red-950/30 border-red-800 text-red-300",
  WARNING:  "bg-yellow-950/30 border-yellow-800 text-yellow-300",
};

function StatusBadge({ status }) {
  return (
    <span className={`text-[10px] font-mono font-bold uppercase border px-2 py-0.5 ${STATUS_COLORS[status] || "bg-zinc-800 text-zinc-400 border-zinc-700"}`}>
      {status}
    </span>
  );
}

function Card({ children, className = "" }) {
  return <div className={`bg-zinc-950 border border-zinc-800 ${className}`}>{children}</div>;
}

function SectionHdr({ title, sub }) {
  return (
    <div className="border-b border-zinc-800 px-5 py-3">
      <div className="font-mono text-[10px] uppercase tracking-widest text-yellow-400">{title}</div>
      {sub && <div className="text-xs text-zinc-500 mt-0.5">{sub}</div>}
    </div>
  );
}

// ─── Cost Centers Tab ─────────────────────────────────────────────

function CostCentersTab() {
  const [centers, setCenters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ code: "", name: "", center_type: "COST", manager: "", description: "", is_active: true });
  const [editId, setEditId] = useState(null);

  const load = async () => {
    try {
      const res = await api.get("/budget/cost-centers");
      setCenters(res.data || []);
    } catch { toast.error("Failed to load cost centers"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      if (editId) {
        await api.patch(`/budget/cost-centers/${editId}`, form);
        toast.success("Cost center updated");
      } else {
        await api.post("/budget/cost-centers", form);
        toast.success("Cost center created");
      }
      setShowForm(false); setEditId(null);
      setForm({ code: "", name: "", center_type: "COST", manager: "", description: "", is_active: true });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete this cost center?")) return;
    await api.delete(`/budget/cost-centers/${id}`);
    toast.success("Deleted"); load();
  };

  const startEdit = (cc) => {
    setForm(cc); setEditId(cc.id); setShowForm(true);
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <span className="font-mono text-xs text-zinc-500 uppercase">{centers.length} Cost/Profit Centers</span>
        <button onClick={() => { setShowForm(!showForm); setEditId(null); }}
          className="flex items-center gap-2 bg-yellow-400 hover:bg-yellow-500 text-black text-xs font-mono font-bold uppercase px-3 py-2 transition-colors">
          <Plus className="w-3.5 h-3.5" /> Add Center
        </button>
      </div>

      {showForm && (
        <Card className="p-5 space-y-4">
          <div className="font-mono text-xs uppercase tracking-widest text-yellow-400 border-b border-zinc-800 pb-2">
            {editId ? "Edit Cost Center" : "New Cost/Profit Center"}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div>
              <label className="label-overline block mb-1">Code</label>
              <input value={form.code} onChange={e => setForm(f => ({ ...f, code: e.target.value }))}
                placeholder="e.g. CC-001"
                className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
            </div>
            <div>
              <label className="label-overline block mb-1">Name</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Production Dept"
                className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
            </div>
            <div>
              <label className="label-overline block mb-1">Type</label>
              <select value={form.center_type} onChange={e => setForm(f => ({ ...f, center_type: e.target.value }))}
                className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400">
                <option value="COST">Cost Center</option>
                <option value="PROFIT">Profit Center</option>
              </select>
            </div>
            <div>
              <label className="label-overline block mb-1">Manager</label>
              <input value={form.manager || ""} onChange={e => setForm(f => ({ ...f, manager: e.target.value }))}
                className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
            </div>
            <div className="sm:col-span-2">
              <label className="label-overline block mb-1">Description</label>
              <input value={form.description || ""} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={save} className="bg-yellow-400 hover:bg-yellow-500 text-black text-xs font-mono font-bold uppercase px-4 py-2">Save</button>
            <button onClick={() => { setShowForm(false); setEditId(null); }} className="border border-zinc-700 text-zinc-400 text-xs font-mono uppercase px-4 py-2">Cancel</button>
          </div>
        </Card>
      )}

      <Card>
        <div className="divide-y divide-zinc-800/60">
          {loading && <div className="p-8 flex justify-center"><RefreshCw className="w-5 h-5 animate-spin text-yellow-400" /></div>}
          {!loading && centers.length === 0 && (
            <div className="p-10 text-center text-zinc-600 font-mono text-xs">No cost centers. Create departments or project centers.</div>
          )}
          {centers.map((cc) => (
            <div key={cc.id} className="px-5 py-3.5 flex items-center justify-between hover:bg-zinc-900/40 transition-colors">
              <div className="flex items-center gap-3">
                <div className={`w-2 h-2 rounded-full ${cc.center_type === "PROFIT" ? "bg-green-400" : "bg-blue-400"}`} />
                <div>
                  <div className="text-sm font-semibold text-zinc-100">{cc.name}</div>
                  <div className="text-xs text-zinc-500 font-mono">{cc.code} · {cc.center_type} CENTER{cc.manager ? ` · ${cc.manager}` : ""}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {!cc.is_active && <span className="text-[10px] font-mono text-zinc-600 uppercase">Inactive</span>}
                <button onClick={() => startEdit(cc)} className="text-zinc-600 hover:text-yellow-400 p-1 transition-colors"><Edit2 className="w-3.5 h-3.5" /></button>
                <button onClick={() => del(cc.id)} className="text-zinc-600 hover:text-red-400 p-1 transition-colors"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ─── Budgets Tab ──────────────────────────────────────────────────

function BudgetsTab() {
  const [budgets, setBudgets] = useState([]);
  const [coa, setCoa] = useState([]);
  const [centers, setCenters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: "", fiscal_year: new Date().getFullYear() + "-" + String(new Date().getFullYear() + 1).slice(-2),
    budget_type: "EXPENSE", period: "ANNUAL", period_label: "", cost_center_code: "",
    lines: [], notes: "", status: "DRAFT",
  });
  const [selectedBudget, setSelectedBudget] = useState(null);
  const [variance, setVariance] = useState(null);
  const [varianceLoading, setVarianceLoading] = useState(false);

  const load = async () => {
    try {
      const [bRes, coaRes, ccRes] = await Promise.all([
        api.get("/budget/budgets"),
        api.get("/accounting/chart-of-accounts"),
        api.get("/budget/cost-centers?is_active=true"),
      ]);
      setBudgets(bRes.data || []);
      setCoa(coaRes || []);
      setCenters(ccRes.data || []);
    } catch { toast.error("Failed to load budgets"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const addLine = () => setForm(f => ({
    ...f, lines: [...f.lines, { account_code: "", account_name: "", budgeted_amount: 0, cost_center_code: "" }]
  }));
  const removeLine = (i) => setForm(f => ({ ...f, lines: f.lines.filter((_, idx) => idx !== i) }));
  const updateLine = (i, field, val) => setForm(f => {
    const lines = [...f.lines];
    lines[i] = { ...lines[i], [field]: val };
    if (field === "account_code") {
      const acc = coa.find(a => a.code === val);
      if (acc) lines[i].account_name = acc.name;
    }
    return { ...f, lines };
  });

  const saveBudget = async () => {
    try {
      await api.post("/budget/budgets", form);
      toast.success("Budget created");
      setShowForm(false);
      setForm({ name: "", fiscal_year: "", budget_type: "EXPENSE", period: "ANNUAL", period_label: "", cost_center_code: "", lines: [], notes: "", status: "DRAFT" });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const approveBudget = async (id) => {
    try {
      await api.patch(`/budget/budgets/${id}`, { status: "APPROVED" });
      toast.success("Budget approved");
      load();
    } catch (e) { toast.error("Failed to approve"); }
  };

  const loadVariance = async (budget) => {
    setSelectedBudget(budget);
    setVarianceLoading(true);
    try {
      const res = await api.get(`/budget/variance-report?budget_id=${budget.id}`);
      setVariance(res.data);
    } catch { toast.error("Failed to load variance report"); }
    finally { setVarianceLoading(false); }
  };

  const totalBudget = (form.lines || []).reduce((s, l) => s + (parseFloat(l.budgeted_amount) || 0), 0);

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <span className="font-mono text-xs text-zinc-500 uppercase">{budgets.length} Budgets</span>
        <button onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 bg-yellow-400 hover:bg-yellow-500 text-black text-xs font-mono font-bold uppercase px-3 py-2 transition-colors">
          <Plus className="w-3.5 h-3.5" /> New Budget
        </button>
      </div>

      {showForm && (
        <Card className="p-5 space-y-4">
          <div className="font-mono text-xs uppercase tracking-widest text-yellow-400 border-b border-zinc-800 pb-2">New Budget</div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label className="label-overline block mb-1">Budget Name</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. FY 2024-25 Operations Budget"
                className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
            </div>
            <div>
              <label className="label-overline block mb-1">Fiscal Year</label>
              <input value={form.fiscal_year} onChange={e => setForm(f => ({ ...f, fiscal_year: e.target.value }))}
                placeholder="2024-25"
                className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
            </div>
            <div>
              <label className="label-overline block mb-1">Budget Type</label>
              <select value={form.budget_type} onChange={e => setForm(f => ({ ...f, budget_type: e.target.value }))}
                className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400">
                <option value="EXPENSE">Expense Budget</option>
                <option value="INCOME">Income Budget</option>
                <option value="CAPEX">Capital Expenditure</option>
              </select>
            </div>
            <div>
              <label className="label-overline block mb-1">Period</label>
              <select value={form.period} onChange={e => setForm(f => ({ ...f, period: e.target.value }))}
                className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400">
                <option value="ANNUAL">Annual</option>
                <option value="QUARTERLY">Quarterly</option>
                <option value="MONTHLY">Monthly</option>
              </select>
            </div>
            <div>
              <label className="label-overline block mb-1">Cost Center</label>
              <select value={form.cost_center_code} onChange={e => setForm(f => ({ ...f, cost_center_code: e.target.value }))}
                className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400">
                <option value="">All Centers</option>
                {centers.map(c => <option key={c.id} value={c.code}>{c.name} ({c.code})</option>)}
              </select>
            </div>
          </div>

          {/* Budget Lines */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="label-overline">Budget Lines · Total: ₹{inr(totalBudget)}</span>
              <button onClick={addLine} className="text-[10px] font-mono text-yellow-400 hover:text-yellow-300 flex items-center gap-1">
                <Plus className="w-3 h-3" /> Add Line
              </button>
            </div>
            {form.lines.map((line, i) => (
              <div key={i} className="flex gap-2 mb-2">
                <select value={line.account_code} onChange={e => updateLine(i, "account_code", e.target.value)}
                  className="flex-1 bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-2 py-1.5 focus:outline-none focus:border-yellow-400">
                  <option value="">Select account...</option>
                  {coa.map(a => <option key={a.code} value={a.code}>{a.code} — {a.name}</option>)}
                </select>
                <input type="number" value={line.budgeted_amount} onChange={e => updateLine(i, "budgeted_amount", parseFloat(e.target.value))}
                  placeholder="Amount ₹" className="w-28 bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-2 py-1.5 focus:outline-none focus:border-yellow-400" />
                <button onClick={() => removeLine(i)} className="text-red-500 hover:text-red-400 px-1"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            ))}
            {form.lines.length === 0 && (
              <div className="text-xs text-zinc-600 font-mono text-center py-4 border border-dashed border-zinc-800">
                Add budget lines for each account code you want to budget
              </div>
            )}
          </div>

          <textarea value={form.notes || ""} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
            placeholder="Notes..." rows={2}
            className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />

          <div className="flex gap-2">
            <button onClick={saveBudget} className="bg-yellow-400 hover:bg-yellow-500 text-black text-xs font-mono font-bold uppercase px-4 py-2">Create Budget</button>
            <button onClick={() => setShowForm(false)} className="border border-zinc-700 text-zinc-400 text-xs font-mono uppercase px-4 py-2">Cancel</button>
          </div>
        </Card>
      )}

      {/* Variance Report Panel */}
      {selectedBudget && (
        <Card className="border-yellow-800/40">
          <SectionHdr title={`Variance Report — ${selectedBudget.name}`} />
          {varianceLoading ? (
            <div className="p-8 flex justify-center"><RefreshCw className="w-5 h-5 animate-spin text-yellow-400" /></div>
          ) : variance ? (
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                  { label: "Total Budget", value: `₹${inr(variance.total_budget)}`, color: "text-zinc-300" },
                  { label: "Actual Spent", value: `₹${inr(variance.total_actual)}`, color: "text-blue-300" },
                  { label: "Variance", value: `₹${inr(variance.total_variance)}`, color: variance.total_variance >= 0 ? "text-green-300" : "text-red-300" },
                  { label: "% Used", value: `${variance.overall_pct_used}%`, color: variance.overall_pct_used > 100 ? "text-red-300" : variance.overall_pct_used > 80 ? "text-yellow-300" : "text-green-300" },
                ].map(k => (
                  <div key={k.label} className="bg-zinc-900/50 border border-zinc-800 p-3">
                    <div className={`font-display font-black text-xl ${k.color}`}>{k.value}</div>
                    <div className="font-mono text-[10px] uppercase text-zinc-500 mt-1">{k.label}</div>
                  </div>
                ))}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr>
                      <th className="text-left py-2 pr-4">Account</th>
                      <th className="text-right py-2 pr-4">Budget</th>
                      <th className="text-right py-2 pr-4">Actual</th>
                      <th className="text-right py-2 pr-4">Variance</th>
                      <th className="text-right py-2 pr-4">% Used</th>
                      <th className="text-left py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60">
                    {(variance.rows || []).map((row) => (
                      <tr key={row.account_code} className="hover:bg-zinc-900/40">
                        <td className="py-2 pr-4">
                          <div className="text-zinc-200">{row.account_name}</div>
                          <div className="text-zinc-600 font-mono text-[10px]">{row.account_code}</div>
                        </td>
                        <td className="text-right py-2 pr-4 text-zinc-400 font-mono">₹{inr(row.budgeted_amount)}</td>
                        <td className="text-right py-2 pr-4 text-zinc-300 font-mono">₹{inr(row.actual_amount)}</td>
                        <td className={`text-right py-2 pr-4 font-mono ${row.variance < 0 ? "text-red-400" : "text-green-400"}`}>
                          {row.variance < 0 ? "-" : "+"}₹{inr(Math.abs(row.variance))}
                        </td>
                        <td className="text-right py-2 pr-4">
                          <div className="flex items-center justify-end gap-2">
                            <div className="w-16 bg-zinc-800 h-1.5 rounded-full overflow-hidden">
                              <div className={`h-full rounded-full ${row.pct_used > 100 ? "bg-red-500" : row.pct_used > 80 ? "bg-yellow-400" : "bg-green-500"}`}
                                style={{ width: `${Math.min(100, row.pct_used)}%` }} />
                            </div>
                            <span className={`font-mono ${row.pct_used > 100 ? "text-red-400" : row.pct_used > 80 ? "text-yellow-400" : "text-green-400"}`}>
                              {row.pct_used}%
                            </span>
                          </div>
                        </td>
                        <td className="py-2">
                          <span className={`text-[9px] font-mono uppercase px-1.5 py-0.5 border ${
                            row.status === "OVER_BUDGET" ? "border-red-800 text-red-400 bg-red-950/20" :
                            row.status === "WARNING" ? "border-yellow-800 text-yellow-400 bg-yellow-950/20" :
                            "border-green-800 text-green-400 bg-green-950/20"
                          }`}>{row.status.replace(/_/g, " ")}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button onClick={() => { setSelectedBudget(null); setVariance(null); }}
                className="text-xs font-mono text-zinc-500 hover:text-zinc-300 underline">
                Close Variance Report
              </button>
            </div>
          ) : null}
        </Card>
      )}

      {/* Budget List */}
      <Card>
        <div className="divide-y divide-zinc-800/60">
          {loading && <div className="p-8 flex justify-center"><RefreshCw className="w-5 h-5 animate-spin text-yellow-400" /></div>}
          {!loading && budgets.length === 0 && (
            <div className="p-10 text-center text-zinc-600 font-mono text-xs">No budgets created yet.</div>
          )}
          {budgets.map((b) => (
            <div key={b.id} className="px-5 py-4 flex items-center justify-between hover:bg-zinc-900/40 transition-colors">
              <div>
                <div className="text-sm font-semibold text-zinc-100">{b.name}</div>
                <div className="text-xs text-zinc-500 font-mono">FY {b.fiscal_year} · {b.budget_type} · {b.period} · Total: ₹{inr(b.total_budget)}</div>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={b.status} />
                <button onClick={() => loadVariance(b)}
                  className="text-[10px] font-mono uppercase px-2 py-1 border border-zinc-700 text-zinc-400 hover:border-yellow-400 hover:text-yellow-400 transition-colors flex items-center gap-1">
                  <BarChart2 className="w-3 h-3" /> Variance
                </button>
                {b.status === "DRAFT" && (
                  <button onClick={() => approveBudget(b.id)}
                    className="text-[10px] font-mono uppercase px-2 py-1 border border-green-800 text-green-400 hover:bg-green-950 transition-colors">
                    Approve
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ─── Alerts Tab ───────────────────────────────────────────────────

function AlertsTab() {
  const [alerts, setAlerts] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const [alertRes, sumRes] = await Promise.all([
        api.get("/budget/alerts"),
        api.get("/budget/summary"),
      ]);
      setAlerts(alertRes.data || []);
      setSummary(sumRes.data);
    } catch { toast.error("Failed to load budget alerts"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-6">
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: "Total Budgets", value: summary.total_budgets, icon: Target, color: "text-zinc-300" },
            { label: "Approved", value: summary.approved_budgets, icon: CheckCircle2, color: "text-green-400" },
            { label: "Cost Centers", value: summary.total_cost_centers, icon: Building2, color: "text-blue-400" },
            { label: "Total Budgeted", value: `₹${inr(summary.total_budget_amount)}`, icon: DollarSign, color: "text-yellow-400" },
          ].map((k) => {
            const Icon = k.icon;
            return (
              <Card key={k.label} className="p-4">
                <Icon className={`w-4 h-4 mb-2 ${k.color}`} />
                <div className={`font-display font-black text-2xl ${k.color}`}>{k.value}</div>
                <div className="font-mono text-[10px] uppercase text-zinc-500 mt-1">{k.label}</div>
              </Card>
            );
          })}
        </div>
      )}

      <Card>
        <SectionHdr title="Budget Alerts" sub="Accounts at 80%+ utilization of approved budgets" />
        <div className="divide-y divide-zinc-800/60">
          {loading && <div className="p-8 flex justify-center"><RefreshCw className="w-5 h-5 animate-spin text-yellow-400" /></div>}
          {!loading && alerts.length === 0 && (
            <div className="p-10 text-center font-mono text-xs text-zinc-600">
              <CheckCircle2 className="w-8 h-8 text-green-700 mx-auto mb-2" />
              All budgets are within limits
            </div>
          )}
          {alerts.map((alert, i) => (
            <div key={i} className={`px-5 py-4 flex items-center justify-between ${ALERT_COLORS[alert.alert_level] || ""}`}>
              <div>
                <div className="flex items-center gap-2">
                  <AlertTriangle className={`w-3.5 h-3.5 ${alert.alert_level === "CRITICAL" ? "text-red-400" : "text-yellow-400"}`} />
                  <span className="text-sm font-semibold text-zinc-100">{alert.account_name}</span>
                </div>
                <div className="text-xs text-zinc-500 font-mono mt-0.5">
                  {alert.budget_name} · {alert.fiscal_year} · Code: {alert.account_code}
                </div>
              </div>
              <div className="text-right">
                <div className={`font-mono text-lg font-bold ${alert.pct_used > 100 ? "text-red-400" : "text-yellow-400"}`}>{alert.pct_used}%</div>
                <div className="text-xs text-zinc-500 font-mono">₹{inr(alert.actual_amount)} / ₹{inr(alert.budgeted_amount)}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ─── Main Budget Page ─────────────────────────────────────────────

const TABS = [
  { id: "alerts", label: "Overview & Alerts", icon: AlertTriangle },
  { id: "budgets", label: "Budgets", icon: Target },
  { id: "cost-centers", label: "Cost Centers", icon: Building2 },
];

export default function Budget() {
  const [tab, setTab] = useState("alerts");

  return (
    <div className="space-y-5">
      <div className="border-b border-zinc-800 pb-4">
        <div className="label-overline mb-2 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" />
          Financial Planning
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight text-zinc-50 uppercase">Budget & Cost Centers</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Cost centers, profit centers, budget planning, and variance analysis
        </p>
      </div>

      <div className="flex gap-0 border-b border-zinc-800">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-mono uppercase tracking-wider border-b-2 transition-colors ${
                tab === t.id ? "border-yellow-400 text-yellow-400" : "border-transparent text-zinc-500 hover:text-zinc-300"
              }`}>
              <Icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      <div>
        {tab === "alerts" && <AlertsTab />}
        {tab === "budgets" && <BudgetsTab />}
        {tab === "cost-centers" && <CostCentersTab />}
      </div>
    </div>
  );
}
