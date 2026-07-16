import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

const Card = ({ children, className = "" }) => (
  <div className={`bg-zinc-900 border border-zinc-800 ${className}`} style={{ borderRadius: "var(--radius)" }}>{children}</div>
);
const SectionHeader = ({ title, subtitle, right }) => (
  <div className="flex items-start justify-between mb-4">
    <div>
      <h2 className="font-display font-black text-zinc-50 text-lg tracking-tight">{title}</h2>
      {subtitle && <p className="text-zinc-500 text-sm mt-0.5">{subtitle}</p>}
    </div>
    {right}
  </div>
);
const Btn = ({ children, onClick, variant = "primary", disabled }) => {
  const styles = {
    primary: "bg-yellow-400 text-black hover:bg-yellow-300",
    ghost: "border border-zinc-700 text-zinc-300 hover:border-yellow-400 hover:text-yellow-400",
  };
  return (
    <button onClick={onClick} disabled={disabled}
      className={`px-4 py-2 text-sm font-mono uppercase tracking-wider transition-colors disabled:opacity-40 ${styles[variant]}`}
      style={{ borderRadius: "var(--radius)" }}>{children}</button>
  );
};
const Input = ({ label, ...props }) => (
  <label className="block">
    {label && <span className="block text-xs font-mono uppercase tracking-wider text-zinc-500 mb-1">{label}</span>}
    <input {...props}
      className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-yellow-400 focus:outline-none"
      style={{ borderRadius: "var(--radius)" }} />
  </label>
);
const Select = ({ label, children, ...props }) => (
  <label className="block">
    {label && <span className="block text-xs font-mono uppercase tracking-wider text-zinc-500 mb-1">{label}</span>}
    <select {...props}
      className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-yellow-400 focus:outline-none"
      style={{ borderRadius: "var(--radius)" }}>{children}</select>
  </label>
);
const fmt = (v) => (v == null ? "—" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 }));

// ── Project list + P&L drill ──
function ProjectsTab({ onOpen }) {
  const [projects, setProjects] = useState([]);
  const [pnls, setPnls] = useState({});
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({ code: "", name: "", customer_id: "", budget: "", billing: "time_and_materials", overhead_pct: "0" });

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/projects");
      setProjects(data);
      const map = {};
      await Promise.all(data.map(async (p) => {
        try { map[p.id] = (await api.get(`/projects/${p.id}/pnl`)).data; } catch {}
      }));
      setPnls(map);
    } catch { toast.error("Failed to load projects"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.code || !form.name) return toast.error("Code and name required");
    try {
      await api.post("/projects", {
        code: form.code, name: form.name, customer_id: form.customer_id || null,
        budget: Number(form.budget || 0), billing: form.billing,
        overhead_pct: Number(form.overhead_pct || 0),
      });
      toast.success("Project created");
      setShow(false);
      setForm({ code: "", name: "", customer_id: "", budget: "", billing: "time_and_materials", overhead_pct: "0" });
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Create failed"); }
  };

  return (
    <div>
      <SectionHeader title="Projects" subtitle="Profitability & budget burn at a glance"
        right={<Btn onClick={() => setShow((v) => !v)}>{show ? "Cancel" : "+ New Project"}</Btn>} />

      {show && (
        <Card className="p-5 mb-5">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <Input label="Code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="PRJ-001" />
            <Input label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <Input label="Customer ID" value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value })} />
            <Input label="Budget" type="text" inputMode="decimal" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} />
            <Select label="Billing" value={form.billing} onChange={(e) => setForm({ ...form, billing: e.target.value })}>
              <option value="time_and_materials">Time & Materials</option>
              <option value="fixed">Fixed</option>
            </Select>
            <Input label="Overhead %" type="text" inputMode="decimal" value={form.overhead_pct} onChange={(e) => setForm({ ...form, overhead_pct: e.target.value })} />
          </div>
          <div className="mt-4"><Btn onClick={create}>Create Project</Btn></div>
        </Card>
      )}

      <Card className="p-4">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] font-mono uppercase text-zinc-500 border-b border-zinc-800">
            <th className="py-2">Project</th><th>Billing</th><th className="text-right">Budget</th>
            <th className="text-right">Revenue</th><th className="text-right">Cost</th>
            <th className="text-right">Profit</th><th className="text-right">Burn</th>
          </tr></thead>
          <tbody>
            {projects.map((p) => {
              const pnl = pnls[p.id];
              const profit = pnl?.pnl?.profit;
              const burn = pnl?.budget_vs_actual?.burn_pct;
              return (
                <tr key={p.id} className="border-b border-zinc-900 hover:bg-zinc-800/30 cursor-pointer" onClick={() => onOpen(p.id)}>
                  <td className="py-2 text-zinc-200"><span className="font-mono text-yellow-400 mr-2">{p.code}</span>{p.name}</td>
                  <td className="text-zinc-400 font-mono text-xs">{p.billing === "fixed" ? "Fixed" : "T&M"}</td>
                  <td className="text-right font-mono text-zinc-300">₹{fmt(p.budget)}</td>
                  <td className="text-right font-mono text-zinc-300">₹{fmt(pnl?.pnl?.revenue)}</td>
                  <td className="text-right font-mono text-zinc-300">₹{fmt(pnl?.pnl?.total_cost)}</td>
                  <td className={`text-right font-mono ${profit >= 0 ? "text-emerald-400" : "text-red-400"}`}>₹{fmt(profit)}</td>
                  <td className="text-right font-mono">
                    {burn == null ? "—" : <span className={burn > 100 ? "text-red-400" : burn > 80 ? "text-amber-400" : "text-zinc-400"}>{fmt(burn)}%</span>}
                  </td>
                </tr>
              );
            })}
            {projects.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-zinc-500">No projects yet.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ── P&L detail ──
function PnlDetail({ projectId, onBack }) {
  const [pnl, setPnl] = useState(null);

  const load = useCallback(async () => {
    try { setPnl((await api.get(`/projects/${projectId}/pnl`)).data); }
    catch { toast.error("Failed to load P&L"); }
  }, [projectId]);
  useEffect(() => { load(); }, [load]);

  const billTime = async () => {
    try {
      const { data } = await api.post(`/projects/${projectId}/bill-time`);
      toast.success(`Draft invoice ${data.invoice_number} · ₹${fmt(data.total)} (${data.entries_billed} entries)`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Bill-time failed"); }
  };

  if (!pnl) return <p className="text-zinc-500 text-sm">Loading…</p>;
  const p = pnl.pnl;
  const bva = pnl.budget_vs_actual;

  return (
    <div>
      <button onClick={onBack} className="text-yellow-400 text-sm font-mono mb-4">← back to projects</button>
      <SectionHeader title={`${pnl.project.code} — ${pnl.project.name}`}
        subtitle={`${pnl.project.billing} · budget ₹${fmt(pnl.project.budget)}`}
        right={pnl.project.billing === "time_and_materials" && pnl.billable.uninvoiced_billable_value > 0 ?
          <Btn onClick={billTime}>Bill ₹{fmt(pnl.billable.uninvoiced_billable_value)} Time</Btn> : null} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KPI label="Revenue" value={`₹${fmt(p.revenue)}`} />
        <KPI label="Total Cost" value={`₹${fmt(p.total_cost)}`} accent="text-orange-400" />
        <KPI label="Profit" value={`₹${fmt(p.profit)}`} accent={p.profit >= 0 ? "text-emerald-400" : "text-red-400"} sub={p.margin_pct != null ? `${fmt(p.margin_pct)}% margin` : ""} />
        <KPI label="Budget Burn" value={bva.burn_pct == null ? "—" : `${fmt(bva.burn_pct)}%`} accent={bva.over_budget ? "text-red-400" : "text-zinc-100"} sub={`₹${fmt(bva.remaining)} left`} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Card className="p-4">
          <div className="text-[11px] font-mono uppercase text-zinc-500 mb-2">Cost Breakdown</div>
          <Row label="Direct cost" value={p.direct_cost} />
          <Row label="Time cost" value={p.time_cost} />
          <Row label={`Overhead (${p.overhead_pct}%)`} value={p.overhead} />
          <div className="border-t border-zinc-700 mt-1 pt-1"><Row label="Total" value={p.total_cost} bold /></div>
        </Card>
        <Card className="p-4">
          <div className="text-[11px] font-mono uppercase text-zinc-500 mb-2">Timesheet</div>
          <Row label="Total hours" value={pnl.timesheet_hours} money={false} />
          <Row label="Billable value" value={pnl.billable.total_billable_value} />
          <Row label="Uninvoiced billable" value={pnl.billable.uninvoiced_billable_value} />
        </Card>
        <Card className="p-4">
          <div className="text-[11px] font-mono uppercase text-zinc-500 mb-2">Drill — Revenue Lines</div>
          {pnl.revenue_lines.map((r, i) => (
            <Row key={i} label={r.account_name} value={r.amount} sub={`${r.entry_ids.length} vouchers`} />
          ))}
          {pnl.revenue_lines.length === 0 && <p className="text-zinc-600 text-xs">No tagged revenue</p>}
        </Card>
      </div>

      <Card className="p-4">
        <div className="text-[11px] font-mono uppercase text-zinc-500 mb-2">Drill — Cost Lines (tagged vouchers)</div>
        <table className="w-full text-sm">
          <tbody>
            {pnl.cost_lines.map((c, i) => (
              <tr key={i} className="border-b border-zinc-900">
                <td className="py-1.5 text-zinc-300">{c.account_name}</td>
                <td className="py-1.5 text-right font-mono text-zinc-200">₹{fmt(c.amount)}</td>
                <td className="py-1.5 text-right text-zinc-600 text-xs font-mono">{c.entry_ids.length} vouchers</td>
              </tr>
            ))}
            {pnl.cost_lines.length === 0 && <tr><td className="py-3 text-zinc-600 text-xs">No tagged direct costs</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

const KPI = ({ label, value, sub, accent = "text-zinc-100" }) => (
  <div className="bg-zinc-950 border border-zinc-800 p-3" style={{ borderRadius: "var(--radius)" }}>
    <div className="text-[11px] font-mono uppercase tracking-wider text-zinc-500">{label}</div>
    <div className={`text-lg font-display font-black ${accent}`}>{value}</div>
    {sub && <div className="text-[11px] text-zinc-600 font-mono">{sub}</div>}
  </div>
);
const Row = ({ label, value, sub, bold, money = true }) => (
  <div className="flex justify-between py-1 text-sm">
    <span className={bold ? "text-zinc-100 font-bold" : "text-zinc-400"}>{label}{sub && <span className="text-zinc-600 text-xs ml-1">· {sub}</span>}</span>
    <span className={`font-mono ${bold ? "text-yellow-400 font-bold" : "text-zinc-200"}`}>{money ? "₹" : ""}{fmt(value)}</span>
  </div>
);

// ── Weekly timesheet grid ──
function TimesheetTab() {
  const [projects, setProjects] = useState([]);
  const [form, setForm] = useState({ user_id: "", project_id: "", date: new Date().toISOString().slice(0, 10), hours: "", rate: "", cost_rate: "", billable: true });
  const [entries, setEntries] = useState([]);

  const load = useCallback(async () => {
    try {
      setProjects((await api.get("/projects")).data);
      setEntries((await api.get("/projects/timesheets")).data);
    } catch { toast.error("Failed to load"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!form.user_id || !form.project_id || !form.hours) return toast.error("User, project & hours required");
    try {
      await api.post("/projects/timesheets", {
        user_id: form.user_id, project_id: form.project_id, date: form.date,
        hours: Number(form.hours), rate: Number(form.rate || 0), cost_rate: Number(form.cost_rate || 0),
        billable: form.billable,
      });
      toast.success("Entry logged");
      setForm({ ...form, hours: "" });
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  return (
    <div>
      <SectionHeader title="Timesheets" subtitle="Log billable & non-billable hours" />
      <Card className="p-5 mb-5">
        <div className="grid grid-cols-2 md:grid-cols-7 gap-2 items-end">
          <Input label="User ID" value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} />
          <Select label="Project" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
            <option value="">—</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
          </Select>
          <Input label="Date" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          <Input label="Hours" type="text" inputMode="decimal" value={form.hours} onChange={(e) => setForm({ ...form, hours: e.target.value })} />
          <Input label="Bill Rate" type="text" inputMode="decimal" value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })} />
          <Input label="Cost Rate" type="text" inputMode="decimal" value={form.cost_rate} onChange={(e) => setForm({ ...form, cost_rate: e.target.value })} />
          <Btn onClick={add}>Log</Btn>
        </div>
        <label className="flex items-center gap-2 text-sm text-zinc-300 mt-3">
          <input type="checkbox" checked={form.billable} onChange={(e) => setForm({ ...form, billable: e.target.checked })} className="accent-yellow-400" />
          Billable
        </label>
      </Card>

      <Card className="p-4">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] font-mono uppercase text-zinc-500 border-b border-zinc-800">
            <th className="py-2">Date</th><th>User</th><th>Project</th><th className="text-right">Hours</th>
            <th className="text-right">Bill ₹</th><th>Billable</th><th>Invoiced</th>
          </tr></thead>
          <tbody>
            {entries.map((e) => {
              const proj = projects.find((p) => p.id === e.project_id);
              return (
                <tr key={e.id} className="border-b border-zinc-900">
                  <td className="py-1.5 text-zinc-400">{e.date}</td>
                  <td className="text-zinc-300 font-mono text-xs">{e.user_id?.slice(0, 8)}</td>
                  <td className="text-zinc-300">{proj?.code || e.project_id?.slice(0, 8)}</td>
                  <td className="text-right font-mono text-zinc-200">{e.hours}</td>
                  <td className="text-right font-mono text-zinc-300">₹{fmt((e.hours || 0) * (e.rate || 0))}</td>
                  <td>{e.billable ? <span className="text-emerald-400 text-xs">yes</span> : <span className="text-zinc-600 text-xs">no</span>}</td>
                  <td>{e.invoiced ? <span className="text-blue-400 text-xs">✓</span> : <span className="text-zinc-600 text-xs">—</span>}</td>
                </tr>
              );
            })}
            {entries.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-zinc-500">No entries.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ── Shell ──
const TABS = [{ id: "projects", label: "Projects" }, { id: "timesheets", label: "Timesheets" }];

export default function Projects() {
  const [tab, setTab] = useState("projects");
  const [openProject, setOpenProject] = useState(null);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="font-display font-black text-2xl text-zinc-50 tracking-tight">Project & Job Costing</h1>
        <p className="text-zinc-500 text-sm mt-1">Timesheets, billable hours, and project-wise P&L with drill-down.</p>
      </div>

      {!openProject && (
        <div className="flex gap-1 border-b border-zinc-800 mb-6">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`px-4 py-2.5 text-sm font-mono uppercase tracking-wider border-b-2 -mb-px ${
                tab === t.id ? "border-yellow-400 text-yellow-400" : "border-transparent text-zinc-500 hover:text-zinc-300"}`}>
              {t.label}
            </button>
          ))}
        </div>
      )}

      {openProject ? (
        <PnlDetail projectId={openProject} onBack={() => setOpenProject(null)} />
      ) : tab === "projects" ? (
        <ProjectsTab onOpen={setOpenProject} />
      ) : (
        <TimesheetTab />
      )}
    </div>
  );
}
