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
  Field,
  EmptyState,
  StatusBadge,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import { toast } from "sonner";
import { Plus, RefreshCw, CheckCircle, XCircle, Clock, Search } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell,
} from "recharts";

const inr = (n) =>
  Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });

const TABS = [
  { id: "list", label: "Expenses" },
  { id: "analytics", label: "Analytics" },
  { id: "categories", label: "Categories" },
];

const PAYMENT_MODES = ["CASH", "CHEQUE", "NEFT", "UPI", "CARD"];
const STATUSES = ["PENDING", "APPROVED", "REJECTED"];

const PIE_COLORS = ["#2961BE", "#019E2A", "#DA5E2D", "#8B5CF6", "#F59E0B", "#EF4444"];

export default function Expenses() {
  const [tab, setTab] = useState("list");
  const [expenses, setExpenses] = useState([]);
  const [categories, setCategories] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [showCatModal, setShowCatModal] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [total, setTotal] = useState(0);

  const [form, setForm] = useState({
    description: "", amount: 0, date: new Date().toISOString().split("T")[0],
    category: "", department: "", payment_mode: "CASH",
    is_recurring: false, status: "PENDING", notes: "",
  });
  const [catForm, setCatForm] = useState({ name: "", description: "", budget_monthly: 0 });

  const loadExpenses = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (statusFilter) params.status = statusFilter;
      if (search) params.search = search;
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/expenses", { params });
      setExpenses(r.data.items || []);
      setTotal(r.data.total || 0);
    } finally { setLoading(false); }
  }, [statusFilter, search, fromDate, toDate]);

  const loadCategories = useCallback(async () => {
    const r = await api.get("/expenses/categories");
    setCategories(r.data);
  }, []);

  const loadAnalytics = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      const r = await api.get("/expenses/analytics/summary", { params });
      setAnalytics(r.data);
    } finally { setLoading(false); }
  }, [fromDate, toDate]);

  useEffect(() => {
    loadCategories();
    if (tab === "list") loadExpenses();
    if (tab === "analytics") loadAnalytics();
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const createExpense = async (e) => {
    e.preventDefault();
    try {
      await api.post("/expenses", { ...form, amount: parseFloat(form.amount) });
      toast.success("Expense submitted");
      setShowModal(false);
      setForm({ description: "", amount: 0, date: new Date().toISOString().split("T")[0], category: "", department: "", payment_mode: "CASH", is_recurring: false, status: "PENDING", notes: "" });
      loadExpenses();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const approveExpense = async (id, status) => {
    try {
      await api.patch(`/expenses/${id}`, { status });
      toast.success(`Expense ${status.toLowerCase()}`);
      loadExpenses();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const deleteExpense = async (id) => {
    if (!window.confirm("Delete this expense?")) return;
    try {
      await api.delete(`/expenses/${id}`);
      toast.success("Deleted");
      loadExpenses();
    } catch (e) {
      toast.error("Failed to delete");
    }
  };

  const createCategory = async (e) => {
    e.preventDefault();
    try {
      await api.post("/expenses/categories", { ...catForm, budget_monthly: parseFloat(catForm.budget_monthly) });
      toast.success("Category created");
      setShowCatModal(false);
      setCatForm({ name: "", description: "", budget_monthly: 0 });
      loadCategories();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const pendingExpenses = expenses.filter(e => e.status === "PENDING");
  const approvedTotal = expenses.filter(e => e.status === "APPROVED").reduce((s, e) => s + (e.amount || 0), 0);

  return (
    <div data-testid="expenses-page">
      <PageHeader
        eyebrow="Finance"
        title="Expense Management"
        description="Submit, review and approve company expenses with departmental tracking."
        actions={
          <PrimaryButton icon={Plus} onClick={() => setShowModal(true)} testid="add-expense-btn">
            New Expense
          </PrimaryButton>
        }
      />

      {/* KPI tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <StatTile label="Total Expenses" value={total} />
        <StatTile label="Pending Approval" value={pendingExpenses.length} />
        <StatTile label="Approved Total" value={`₹${inr(approvedTotal)}`} accent />
        <StatTile label="Categories" value={categories.length} />
      </div>

      {/* Tabs */}
      <div className="flex gap-px bg-zinc-800 border border-zinc-800 mb-6">
        {TABS.map(t => (
          <button key={t.id} data-testid={`tab-${t.id}`} onClick={() => setTab(t.id)}
            className={`px-4 py-3 text-xs font-mono uppercase tracking-wider transition-colors ${
              tab === t.id ? "bg-yellow-400 text-black font-bold" : "bg-zinc-950 text-zinc-400 hover:text-white hover:bg-zinc-900"
            }`}>{t.label}</button>
        ))}
      </div>

      {/* Filters */}
      {tab === "list" && (
        <div className="flex flex-wrap gap-2 mb-4">
          <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search..." className="w-48" />
          <Select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="w-36">
            <option value="">All Status</option>
            {STATUSES.map(s => <option key={s}>{s}</option>)}
          </Select>
          <Input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} className="w-36" />
          <Input type="date" value={toDate} onChange={e => setToDate(e.target.value)} className="w-36" />
          <SecondaryButton icon={Search} onClick={loadExpenses}>Filter</SecondaryButton>
        </div>
      )}

      {/* Expense List */}
      {tab === "list" && (
        loading ? (
          <div className="text-zinc-500 font-mono text-xs uppercase p-8 text-center">Loading...</div>
        ) : expenses.length === 0 ? (
          <EmptyState message="No expenses" action={<PrimaryButton icon={Plus} onClick={() => setShowModal(true)}>Add Expense</PrimaryButton>} />
        ) : (
          <table className="w-full text-sm border border-zinc-800">
            <thead>
              <tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                <th className="text-left px-4 py-2">Date</th>
                <th className="text-left px-4 py-2">Description</th>
                <th className="text-left px-4 py-2">Category</th>
                <th className="text-left px-4 py-2">Dept</th>
                <th className="text-right px-4 py-2">Amount</th>
                <th className="text-left px-4 py-2">Mode</th>
                <th className="text-left px-4 py-2">Submitted By</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-right px-4 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {expenses.map((e, i) => (
                <tr key={e.id} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                  <td className="px-4 py-2 font-mono text-zinc-400 text-xs">{e.date}</td>
                  <td className="px-4 py-2 text-white text-xs max-w-xs truncate">{e.description}</td>
                  <td className="px-4 py-2 text-zinc-300 text-xs">{e.category}</td>
                  <td className="px-4 py-2 text-zinc-400 text-xs">{e.department || "—"}</td>
                  <td className="px-4 py-2 text-right tabular font-semibold text-yellow-400">₹{inr(e.amount)}</td>
                  <td className="px-4 py-2 font-mono text-xs text-zinc-400">{e.payment_mode}</td>
                  <td className="px-4 py-2 text-xs text-zinc-400">{e.submitted_by_name || "—"}</td>
                  <td className="px-4 py-2">
                    <span className={`text-[10px] font-mono uppercase px-1.5 py-0.5 border ${
                      e.status === "APPROVED" ? "border-green-800 bg-green-950 text-green-400" :
                      e.status === "REJECTED" ? "border-red-800 bg-red-950 text-red-400" :
                      "border-yellow-800 bg-yellow-950 text-yellow-400"
                    }`}>{e.status}</span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    {e.status === "PENDING" && (
                      <div className="flex gap-1 justify-end">
                        <button onClick={() => approveExpense(e.id, "APPROVED")} className="text-green-400 hover:text-green-300 transition-colors" title="Approve">
                          <CheckCircle className="w-4 h-4" />
                        </button>
                        <button onClick={() => approveExpense(e.id, "REJECTED")} className="text-red-400 hover:text-red-300 transition-colors" title="Reject">
                          <XCircle className="w-4 h-4" />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}

      {/* Analytics Tab */}
      {tab === "analytics" && (
        <div className="space-y-6">
          <div className="flex gap-2 mb-4">
            <Input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} className="w-36" />
            <Input type="date" value={toDate} onChange={e => setToDate(e.target.value)} className="w-36" />
            <SecondaryButton icon={RefreshCw} onClick={loadAnalytics}>Refresh</SecondaryButton>
          </div>
          {loading ? (
            <div className="text-zinc-500 font-mono text-xs uppercase p-8 text-center">Loading...</div>
          ) : analytics ? (
            <>
              <div className="grid grid-cols-2 gap-3 mb-6">
                <StatTile label="Total Approved" value={`₹${inr(analytics.total_approved)}`} accent />
                <StatTile label="Pending Approvals" value={analytics.pending_count} />
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="border border-zinc-800 bg-zinc-950 p-4">
                  <SectionTitle>By Category</SectionTitle>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={analytics.by_category.map(b => ({ name: b._id, value: b.total }))} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name }) => name}>
                          {analytics.by_category.map((_, idx) => <Cell key={idx} fill={idx === 0 ? "hsl(var(--primary))" : PIE_COLORS[idx % PIE_COLORS.length]} stroke="hsl(var(--card))" strokeWidth={2} />)}
                        </Pie>
                        <Tooltip contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "var(--radius)", fontFamily: "IBM Plex Mono", color: "hsl(var(--foreground))" }} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </div>
                <div className="border border-zinc-800 bg-zinc-950 p-4">
                  <SectionTitle>Monthly Trend</SectionTitle>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={analytics.monthly_trend.map(m => ({ month: m._id, amount: m.total }))}>
                        <CartesianGrid stroke="rgb(var(--zinc-800))" vertical={false} />
                        <XAxis dataKey="month" stroke="rgb(var(--zinc-500))" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} />
                        <YAxis stroke="rgb(var(--zinc-500))" tick={{ fontSize: 10 }} />
                        <Tooltip contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "var(--radius)", fontFamily: "IBM Plex Mono", color: "hsl(var(--foreground))" }} />
                        <Bar dataKey="amount" fill="rgb(var(--yellow-400))" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <EmptyState message="No analytics data" />
          )}
        </div>
      )}

      {/* Categories Tab */}
      {tab === "categories" && (
        <div>
          <div className="flex justify-end mb-4">
            <PrimaryButton icon={Plus} onClick={() => setShowCatModal(true)} testid="add-category-btn">
              Add Category
            </PrimaryButton>
          </div>
          {categories.length === 0 ? (
            <EmptyState message="No categories" />
          ) : (
            <table className="w-full text-sm border border-zinc-800">
              <thead><tr className="label-overline border-b border-zinc-800 bg-zinc-900">
                <th className="text-left px-4 py-2">Name</th>
                <th className="text-left px-4 py-2">Description</th>
                <th className="text-right px-4 py-2">Budget Limit</th>
              </tr></thead>
              <tbody>
                {categories.map((c, i) => (
                  <tr key={c.id} className={`border-b border-zinc-900 hover:bg-zinc-900 ${i % 2 === 1 ? "bg-zinc-900/30" : ""}`}>
                    <td className="px-4 py-2 text-yellow-400 font-semibold">{c.name}</td>
                    <td className="px-4 py-2 text-zinc-400 text-xs">{c.description || "—"}</td>
                    <td className="px-4 py-2 text-right tabular text-white">
                      {c.budget_monthly ? `₹${inr(c.budget_monthly)}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Add Expense Modal */}
      <Modal open={showModal} onClose={() => setShowModal(false)} title="New Expense">
        <form onSubmit={createExpense} className="space-y-4">
          <Field label="Description" required><Input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} required /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Amount (₹)" required><Input type="number" step="0.01" value={form.amount} onChange={e => setForm(f => ({ ...f, amount: e.target.value }))} required /></Field>
            <Field label="Date" required><Input type="date" value={form.date} onChange={e => setForm(f => ({ ...f, date: e.target.value }))} required /></Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Category">
              <Select value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>
                <option value="">Select...</option>
                {categories.map(c => <option key={c.id} value={c.name}>{c.name}</option>)}
              </Select>
            </Field>
            <Field label="Department"><Input value={form.department} onChange={e => setForm(f => ({ ...f, department: e.target.value }))} placeholder="e.g. Operations" /></Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Payment Mode">
              <Select value={form.payment_mode} onChange={e => setForm(f => ({ ...f, payment_mode: e.target.value }))}>
                {PAYMENT_MODES.map(m => <option key={m}>{m}</option>)}
              </Select>
            </Field>
            <Field label="Notes"><Input value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} /></Field>
          </div>
          <div className="flex gap-2 items-center">
            <input type="checkbox" id="recurring" checked={form.is_recurring} onChange={e => setForm(f => ({ ...f, is_recurring: e.target.checked }))} className="w-4 h-4 accent-yellow-400" />
            <label htmlFor="recurring" className="text-sm text-zinc-300">Recurring expense</label>
          </div>
          <div className="flex gap-2 justify-end pt-2">
            <SecondaryButton onClick={() => setShowModal(false)}>Cancel</SecondaryButton>
            <PrimaryButton type="submit">Submit</PrimaryButton>
          </div>
        </form>
      </Modal>

      {/* Add Category Modal */}
      <Modal open={showCatModal} onClose={() => setShowCatModal(false)} title="Add Expense Category">
        <form onSubmit={createCategory} className="space-y-4">
          <Field label="Category Name" required><Input value={catForm.name} onChange={e => setCatForm(f => ({ ...f, name: e.target.value }))} required /></Field>
          <Field label="Description"><Input value={catForm.description} onChange={e => setCatForm(f => ({ ...f, description: e.target.value }))} /></Field>
          <Field label="Monthly Budget Limit (₹)"><Input type="number" step="0.01" value={catForm.budget_monthly} onChange={e => setCatForm(f => ({ ...f, budget_monthly: e.target.value }))} /></Field>
          <div className="flex gap-2 justify-end pt-2">
            <SecondaryButton onClick={() => setShowCatModal(false)}>Cancel</SecondaryButton>
            <PrimaryButton type="submit">Create</PrimaryButton>
          </div>
        </form>
      </Modal>
    </div>
  );
}
