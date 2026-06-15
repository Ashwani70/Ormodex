import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";

const TABS = ["Dashboard", "Pay Components", "Salary Structures", "Payroll Runs", "Payslips", "Statutory", "Form 16", "F&F Settlement"];

const Card = ({ children, className = "" }) => (
  <div className={`bg-zinc-900 border border-zinc-800 rounded-xl p-4 ${className}`}>{children}</div>
);

const SectionHeader = ({ title, action }) => (
  <div className="flex items-center justify-between mb-4">
    <h2 className="text-lg font-semibold text-white">{title}</h2>
    {action}
  </div>
);

const Input = ({ label, ...props }) => (
  <div>
    {label && <label className="block text-xs text-zinc-400 mb-1">{label}</label>}
    <input className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yellow-400" {...props} />
  </div>
);

const Select = ({ label, children, ...props }) => (
  <div>
    {label && <label className="block text-xs text-zinc-400 mb-1">{label}</label>}
    <select className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yellow-400" {...props}>
      {children}
    </select>
  </div>
);

const Btn = ({ children, onClick, variant = "primary", disabled, className = "" }) => {
  const variants = {
    primary: "bg-yellow-400 text-zinc-950 hover:bg-yellow-300",
    secondary: "bg-zinc-700 text-white hover:bg-zinc-600",
    danger: "bg-red-800 text-white hover:bg-red-700",
    ghost: "text-zinc-400 hover:text-white",
    success: "bg-emerald-700 text-white hover:bg-emerald-600",
  };
  return (
    <button className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${variants[variant]} ${className}`} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
};

const StatusBadge = ({ status }) => {
  const colors = {
    DRAFT: "bg-zinc-700 text-zinc-300",
    PROCESSED: "bg-blue-900 text-blue-300",
    POSTED: "bg-emerald-900 text-emerald-300",
    CANCELLED: "bg-red-900 text-red-300",
  };
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${colors[status] ?? "bg-zinc-700 text-zinc-300"}`}>{status}</span>;
};

const fmt = (n) => `₹${Number(n ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const pct = (n) => `${Number(n ?? 0).toFixed(2)}%`;

// Dashboard
function DashboardTab() {
  const [runs, setRuns] = useState([]);
  useEffect(() => {
    api.get("/payroll/runs").then(r => setRuns(r.data.slice(-6).reverse())).catch(() => {});
  }, []);
  const latest = runs[0];
  return (
    <div className="space-y-4">
      <SectionHeader title="Payroll Dashboard" />
      {latest && (
        <div className="grid grid-cols-4 gap-4">
          {[
            ["Period", latest.period],
            ["Total Gross", fmt(latest.total_gross)],
            ["Total Net", fmt(latest.total_net)],
            ["Status", <StatusBadge key="s" status={latest.status} />],
          ].map(([label, val]) => (
            <Card key={label}><p className="text-xs text-zinc-400 mb-1">{label}</p><div className="text-white font-semibold">{val}</div></Card>
          ))}
        </div>
      )}
      {latest && (
        <div className="grid grid-cols-4 gap-4">
          {[
            ["Employee PF", fmt(latest.total_pf_employee)],
            ["Employer PF", fmt(latest.total_pf_employer)],
            ["Employee ESI", fmt(latest.total_esi_employee)],
            ["TDS Deducted", fmt(latest.total_tds)],
          ].map(([label, val]) => (
            <Card key={label} className="bg-zinc-900/50"><p className="text-xs text-zinc-500 mb-1">{label}</p><p className="text-emerald-400 font-medium">{val}</p></Card>
          ))}
        </div>
      )}
      <Card>
        <p className="text-zinc-400 text-sm font-medium mb-3">Recent Runs</p>
        <table className="w-full text-sm">
          <thead><tr className="text-zinc-500 border-b border-zinc-800">
            <th className="text-left pb-2">Period</th><th className="text-left pb-2">FY</th><th className="text-right pb-2">Employees</th><th className="text-right pb-2">Gross</th><th className="text-right pb-2">Net</th><th className="text-left pb-2">Status</th>
          </tr></thead>
          <tbody className="divide-y divide-zinc-800">
            {runs.map(r => (
              <tr key={r.id}>
                <td className="py-2 text-white font-mono">{r.period}</td>
                <td className="py-2 text-zinc-400">{r.financial_year}</td>
                <td className="py-2 text-right text-zinc-300">{r.employee_count ?? "—"}</td>
                <td className="py-2 text-right">{fmt(r.total_gross)}</td>
                <td className="py-2 text-right text-emerald-400">{fmt(r.total_net)}</td>
                <td className="py-2"><StatusBadge status={r.status} /></td>
              </tr>
            ))}
            {runs.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-zinc-500">No payroll runs yet</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// Pay Components
function PayComponentsTab() {
  const [components, setComponents] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", type: "earning", calc: "flat", taxable: true, pf_applicable: false, esi_applicable: false, pt_applicable: false });

  const load = () => api.get("/payroll/pay-components").then(r => setComponents(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const save = async () => {
    try { await api.post("/payroll/pay-components", form); setShowForm(false); load(); }
    catch (e) { alert(e.response?.data?.detail || "Error"); }
  };

  return (
    <div className="space-y-4">
      <SectionHeader title="Pay Components" action={<Btn onClick={() => setShowForm(true)}>+ Add Component</Btn>} />
      <Card>
        <table className="w-full text-sm">
          <thead><tr className="text-zinc-400 border-b border-zinc-800">
            <th className="text-left py-2 pr-3">Name</th><th className="text-left py-2 pr-3">Type</th><th className="text-left py-2 pr-3">Calc</th>
            <th className="text-center py-2 pr-2">Taxable</th><th className="text-center py-2 pr-2">PF</th><th className="text-center py-2 pr-2">ESI</th><th className="text-center py-2">PT</th>
          </tr></thead>
          <tbody className="divide-y divide-zinc-800">
            {components.map(c => (
              <tr key={c.id} className="hover:bg-zinc-800/40">
                <td className="py-2 pr-3 text-white font-medium">{c.name}</td>
                <td className="py-2 pr-3"><span className={`text-xs px-2 py-0.5 rounded-full ${c.type === "earning" ? "bg-emerald-900 text-emerald-300" : c.type === "deduction" ? "bg-red-900 text-red-300" : "bg-blue-900 text-blue-300"}`}>{c.type}</span></td>
                <td className="py-2 pr-3 text-zinc-400 text-xs">{c.calc}</td>
                {["taxable", "pf_applicable", "esi_applicable", "pt_applicable"].map(k => (
                  <td key={k} className="py-2 text-center">{c[k] ? <span className="text-emerald-400">✓</span> : <span className="text-zinc-600">—</span>}</td>
                ))}
              </tr>
            ))}
            {components.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-zinc-500">No pay components</td></tr>}
          </tbody>
        </table>
      </Card>
      {showForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-md space-y-4">
            <h3 className="text-white font-semibold">New Pay Component</h3>
            <Input label="Name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <Select label="Type" value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))}>
              <option value="earning">Earning</option><option value="deduction">Deduction</option><option value="reimbursement">Reimbursement</option>
            </Select>
            <Select label="Calc Method" value={form.calc} onChange={e => setForm(f => ({ ...f, calc: e.target.value }))}>
              <option value="flat">Flat Amount</option><option value="percent_of_basic">% of Basic</option><option value="formula">Formula</option>
            </Select>
            <div className="grid grid-cols-2 gap-3">
              {[["taxable", "Taxable"], ["pf_applicable", "PF Applicable"], ["esi_applicable", "ESI Applicable"], ["pt_applicable", "PT Applicable"]].map(([k, label]) => (
                <label key={k} className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                  <input type="checkbox" checked={!!form[k]} onChange={() => setForm(f => ({ ...f, [k]: !f[k] }))} className="rounded" />{label}
                </label>
              ))}
            </div>
            <div className="flex justify-end gap-3">
              <Btn variant="secondary" onClick={() => setShowForm(false)}>Cancel</Btn>
              <Btn onClick={save}>Save</Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Salary Structures
function SalaryStructuresTab() {
  const [structures, setStructures] = useState([]);
  const [components, setComponents] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ employee_id: "", effective_from: "", lines: [] });

  const load = () => {
    api.get("/payroll/salary-structures").then(r => setStructures(r.data)).catch(() => {});
    api.get("/payroll/pay-components").then(r => setComponents(r.data)).catch(() => {});
    api.get("/hr/employees").then(r => setEmployees(r.data)).catch(() => api.get("/employees").then(r => setEmployees(r.data)).catch(() => {}));
  };
  useEffect(() => { load(); }, []);

  const compMap = Object.fromEntries(components.map(c => [c.id, c]));
  const addLine = () => setForm(f => ({ ...f, lines: [...f.lines, { pay_component_id: "", amount: 0, percent: 0 }] }));
  const updateLine = (i, key, val) => setForm(f => { const lines = [...f.lines]; lines[i] = { ...lines[i], [key]: val }; return { ...f, lines }; });

  const save = async () => {
    try {
      await api.post("/payroll/salary-structures", { ...form, lines: form.lines.map(l => ({ ...l, amount: parseFloat(l.amount) || 0, percent: parseFloat(l.percent) || 0 })) });
      setShowForm(false); load();
    } catch (e) { alert(e.response?.data?.detail || "Error"); }
  };

  return (
    <div className="space-y-4">
      <SectionHeader title="Salary Structures" action={<Btn onClick={() => setShowForm(true)}>+ New Structure</Btn>} />
      <Card>
        <table className="w-full text-sm">
          <thead><tr className="text-zinc-400 border-b border-zinc-800"><th className="text-left py-2 pr-3">Employee</th><th className="text-left py-2 pr-3">Effective From</th><th className="text-right py-2">Components</th></tr></thead>
          <tbody className="divide-y divide-zinc-800">
            {structures.map(s => {
              const emp = employees.find(e => e.id === s.employee_id);
              return <tr key={s.id} className="hover:bg-zinc-800/40"><td className="py-2 pr-3 text-white">{emp?.name ?? s.employee_id}</td><td className="py-2 pr-3 text-zinc-400">{s.effective_from}</td><td className="py-2 text-right text-zinc-400">{s.lines?.length ?? 0}</td></tr>;
            })}
            {structures.length === 0 && <tr><td colSpan={3} className="py-6 text-center text-zinc-500">No salary structures</td></tr>}
          </tbody>
        </table>
      </Card>
      {showForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-2xl space-y-4 max-h-screen overflow-y-auto">
            <h3 className="text-white font-semibold">New Salary Structure</h3>
            <div className="grid grid-cols-2 gap-3">
              <Select label="Employee *" value={form.employee_id} onChange={e => setForm(f => ({ ...f, employee_id: e.target.value }))}>
                <option value="">Select employee...</option>
                {employees.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
              </Select>
              <Input label="Effective From *" type="date" value={form.effective_from} onChange={e => setForm(f => ({ ...f, effective_from: e.target.value }))} />
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm text-zinc-400">Pay Lines</p>
                <Btn variant="secondary" className="text-xs !px-2 !py-1" onClick={addLine}>+ Add Line</Btn>
              </div>
              {form.lines.map((line, i) => {
                const comp = compMap[line.pay_component_id];
                return (
                  <div key={i} className="grid grid-cols-12 gap-2 mb-2 items-end">
                    <div className="col-span-5">
                      <Select value={line.pay_component_id} onChange={e => updateLine(i, "pay_component_id", e.target.value)}>
                        <option value="">Select component...</option>
                        {components.map(c => <option key={c.id} value={c.id}>{c.name} ({c.type})</option>)}
                      </Select>
                    </div>
                    <div className="col-span-5">
                      {comp?.calc === "percent_of_basic"
                        ? <Input type="number" placeholder="Percent %" value={line.percent} onChange={e => updateLine(i, "percent", e.target.value)} />
                        : <Input type="number" placeholder="Amount" value={line.amount} onChange={e => updateLine(i, "amount", e.target.value)} />}
                    </div>
                    <div className="col-span-2">
                      <button onClick={() => setForm(f => ({ ...f, lines: f.lines.filter((_, idx) => idx !== i) }))} className="w-full py-2 text-red-400 hover:text-red-300 text-sm">✕</button>
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="flex justify-end gap-3">
              <Btn variant="secondary" onClick={() => setShowForm(false)}>Cancel</Btn>
              <Btn onClick={save}>Save Structure</Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Payroll Runs
function PayrollRunsTab() {
  const [runs, setRuns] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ period: "", financial_year: "2024-25" });
  const [processing, setProcessing] = useState(null);
  const [runResult, setRunResult] = useState(null);

  const load = () => api.get("/payroll/runs").then(r => setRuns(r.data.reverse())).catch(() => {});
  useEffect(() => { load(); }, []);

  const createRun = async () => {
    try { await api.post("/payroll/runs", form); setShowForm(false); load(); }
    catch (e) { alert(e.response?.data?.detail || "Error"); }
  };

  const processRun = async (runId) => {
    setProcessing(runId);
    try { const { data } = await api.post(`/payroll/runs/${runId}/process`); setRunResult(data); load(); }
    catch (e) { alert(e.response?.data?.detail || "Error"); }
    finally { setProcessing(null); }
  };

  const postRun = async (runId) => {
    if (!confirm("Post this payroll run? This action cannot be undone.")) return;
    try { await api.post(`/payroll/runs/${runId}/post`); load(); }
    catch (e) { alert(e.response?.data?.detail || "Error"); }
  };

  return (
    <div className="space-y-4">
      <SectionHeader title="Payroll Runs" action={<Btn onClick={() => setShowForm(true)}>+ New Run</Btn>} />
      <Card>
        <table className="w-full text-sm">
          <thead><tr className="text-zinc-400 border-b border-zinc-800">
            <th className="text-left py-2 pr-3">Period</th><th className="text-left py-2 pr-3">FY</th><th className="text-right py-2 pr-3">Employees</th>
            <th className="text-right py-2 pr-3">Total Gross</th><th className="text-right py-2 pr-3">Total Net</th><th className="text-left py-2 pr-3">Status</th><th className="text-left py-2">Actions</th>
          </tr></thead>
          <tbody className="divide-y divide-zinc-800">
            {runs.map(r => (
              <tr key={r.id} className="hover:bg-zinc-800/40">
                <td className="py-2 pr-3 text-white font-mono">{r.period}</td>
                <td className="py-2 pr-3 text-zinc-400">{r.financial_year}</td>
                <td className="py-2 pr-3 text-right text-zinc-300">{r.employee_count ?? "—"}</td>
                <td className="py-2 pr-3 text-right">{fmt(r.total_gross)}</td>
                <td className="py-2 pr-3 text-right text-emerald-400">{fmt(r.total_net)}</td>
                <td className="py-2 pr-3"><StatusBadge status={r.status} /></td>
                <td className="py-2 flex gap-2">
                  {r.status === "DRAFT" && <Btn variant="secondary" className="text-xs !px-2 !py-1" onClick={() => processRun(r.id)} disabled={processing === r.id}>{processing === r.id ? "Processing..." : "Process"}</Btn>}
                  {r.status === "PROCESSED" && <Btn variant="success" className="text-xs !px-2 !py-1" onClick={() => postRun(r.id)}>Post</Btn>}
                </td>
              </tr>
            ))}
            {runs.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-zinc-500">No payroll runs</td></tr>}
          </tbody>
        </table>
      </Card>
      {runResult && (
        <Card className="border-emerald-800/40">
          <div className="flex items-center justify-between mb-3">
            <p className="text-emerald-400 font-medium">Run Complete — {runResult.period}</p>
            <button onClick={() => setRunResult(null)} className="text-zinc-400 hover:text-white">✕</button>
          </div>
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div><p className="text-zinc-400 text-xs">Processed</p><p className="text-white font-semibold">{runResult.processed} employees</p></div>
            <div><p className="text-zinc-400 text-xs">Total Gross</p><p className="text-white font-semibold">{fmt(runResult.summary?.total_gross)}</p></div>
            <div><p className="text-zinc-400 text-xs">Total Net</p><p className="text-emerald-400 font-semibold">{fmt(runResult.summary?.total_net)}</p></div>
          </div>
          {runResult.errors?.length > 0 && (
            <div className="mt-3 bg-red-950/30 border border-red-800/40 rounded-lg p-3">
              <p className="text-red-400 text-xs font-medium mb-1">Errors ({runResult.errors.length})</p>
              {runResult.errors.map((e, i) => <p key={i} className="text-xs text-red-300">{e.employee_id}: {e.error}</p>)}
            </div>
          )}
        </Card>
      )}
      {showForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-sm space-y-4">
            <h3 className="text-white font-semibold">New Payroll Run</h3>
            <Input label="Period (MMYYYY)" placeholder="e.g. 062025" value={form.period} onChange={e => setForm(f => ({ ...f, period: e.target.value }))} />
            <Input label="Financial Year" placeholder="e.g. 2025-26" value={form.financial_year} onChange={e => setForm(f => ({ ...f, financial_year: e.target.value }))} />
            <div className="flex justify-end gap-3">
              <Btn variant="secondary" onClick={() => setShowForm(false)}>Cancel</Btn>
              <Btn onClick={createRun}>Create Run</Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Payslips
function PayslipDetail({ payslip: p, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-2xl space-y-4 max-h-screen overflow-y-auto">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-white font-semibold text-lg">{p.employee_name}</h3>
            <p className="text-zinc-400 text-sm">Period: {p.period} · FY: {p.financial_year} · Days: {p.paid_days}/{p.total_days}{p.lop_days > 0 ? ` (LOP: ${p.lop_days})` : ""}</p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-white text-xl">✕</button>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Card>
            <p className="text-xs text-zinc-400 font-medium mb-2">Earnings</p>
            {p.earnings?.map((e, i) => (
              <div key={i} className="flex justify-between text-sm py-1 border-b border-zinc-800">
                <span className="text-zinc-300">{e.name}</span><span className="text-white">{fmt(e.amount)}</span>
              </div>
            ))}
            <div className="flex justify-between text-sm pt-2 font-semibold">
              <span className="text-white">Gross</span><span className="text-yellow-400">{fmt(p.gross)}</span>
            </div>
          </Card>
          <Card>
            <p className="text-xs text-zinc-400 font-medium mb-2">Deductions</p>
            {[["Employee PF", p.pf], ["Employee ESI", p.esi], ["Professional Tax", p.pt], ["TDS", p.tds]].map(([label, val]) => (
              <div key={label} className="flex justify-between text-sm py-1 border-b border-zinc-800">
                <span className="text-zinc-300">{label}</span><span className="text-red-400">{fmt(val)}</span>
              </div>
            ))}
            {p.other_deductions?.map((d, i) => (
              <div key={i} className="flex justify-between text-sm py-1 border-b border-zinc-800">
                <span className="text-zinc-300">{d.name}</span><span className="text-red-400">{fmt(d.amount)}</span>
              </div>
            ))}
            <div className="flex justify-between text-sm pt-2 font-semibold">
              <span className="text-white">Net Pay</span><span className="text-emerald-400">{fmt(p.net)}</span>
            </div>
          </Card>
        </div>
        {p.statutory?.tds && (
          <Card className="bg-amber-950/20 border-amber-800/30">
            <p className="text-xs text-amber-400 font-medium mb-2">TDS Computation — {p.statutory.tds.regime?.toUpperCase()} Regime</p>
            <div className="grid grid-cols-3 gap-3 text-xs">
              {[["Projected Annual Gross", fmt(p.statutory.tds.annual_gross)], ["Std Deduction", fmt(p.statutory.tds.standard_deduction)], ["Exemptions", fmt(p.statutory.tds.exemptions)], ["Taxable Income", fmt(p.statutory.tds.annual_taxable_income)], ["Annual Tax", fmt(p.statutory.tds.annual_tax)], ["Monthly TDS", fmt(p.statutory.tds.monthly_tds)]].map(([label, val]) => (
                <div key={label}><p className="text-zinc-500">{label}</p><p className="text-white font-medium">{val}</p></div>
              ))}
            </div>
          </Card>
        )}
        <Card className="bg-zinc-800/50">
          <p className="text-xs text-zinc-400 font-medium mb-2">Employer Contributions</p>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="flex justify-between"><span className="text-zinc-400">Employer PF</span><span className="text-white">{fmt(p.employer_pf)}</span></div>
            <div className="flex justify-between"><span className="text-zinc-400">Employer ESI</span><span className="text-white">{fmt(p.employer_esi)}</span></div>
          </div>
        </Card>
      </div>
    </div>
  );
}

function PayslipsTab() {
  const [payslips, setPayslips] = useState([]);
  const [filter, setFilter] = useState({ period: "", employee_id: "" });
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    const params = {};
    if (filter.period) params.period = filter.period;
    if (filter.employee_id) params.employee_id = filter.employee_id;
    try { const { data } = await api.get("/payroll/payslips", { params }); setPayslips(data); }
    catch { setPayslips([]); }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <SectionHeader title="Payslips" />
      <Card>
        <div className="grid grid-cols-3 gap-3">
          <Input placeholder="Period (MMYYYY)" value={filter.period} onChange={e => setFilter(f => ({ ...f, period: e.target.value }))} />
          <Input placeholder="Employee ID" value={filter.employee_id} onChange={e => setFilter(f => ({ ...f, employee_id: e.target.value }))} />
          <Btn onClick={load}>Search</Btn>
        </div>
      </Card>
      <Card>
        <table className="w-full text-sm">
          <thead><tr className="text-zinc-400 border-b border-zinc-800">
            <th className="text-left py-2 pr-3">Employee</th><th className="text-left py-2 pr-3">Period</th>
            <th className="text-right py-2 pr-3">Gross</th><th className="text-right py-2 pr-3">PF</th><th className="text-right py-2 pr-3">ESI</th>
            <th className="text-right py-2 pr-3">TDS</th><th className="text-right py-2 pr-3">Net</th><th className="text-left py-2">Status</th>
          </tr></thead>
          <tbody className="divide-y divide-zinc-800">
            {payslips.map(p => (
              <tr key={p.id} className="hover:bg-zinc-800/40 cursor-pointer" onClick={() => setSelected(p)}>
                <td className="py-2 pr-3 text-white">{p.employee_name}</td>
                <td className="py-2 pr-3 text-zinc-400 font-mono">{p.period}</td>
                <td className="py-2 pr-3 text-right">{fmt(p.gross)}</td>
                <td className="py-2 pr-3 text-right text-blue-400">{fmt(p.pf)}</td>
                <td className="py-2 pr-3 text-right text-purple-400">{fmt(p.esi)}</td>
                <td className="py-2 pr-3 text-right text-amber-400">{fmt(p.tds)}</td>
                <td className="py-2 pr-3 text-right text-emerald-400 font-semibold">{fmt(p.net)}</td>
                <td className="py-2"><StatusBadge status={p.status} /></td>
              </tr>
            ))}
            {payslips.length === 0 && <tr><td colSpan={8} className="py-6 text-center text-zinc-500">No payslips found</td></tr>}
          </tbody>
        </table>
      </Card>
      {selected && <PayslipDetail payslip={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

// Statutory Params
function StatutoryTab() {
  const [params, setParams] = useState([]);
  useEffect(() => { api.get("/payroll/statutory-params").then(r => setParams(r.data)).catch(() => {}); }, []);
  return (
    <div className="space-y-4">
      <SectionHeader title="Statutory Parameters (FY-versioned)" />
      <Card>
        <p className="text-xs text-zinc-500 mb-3">All statutory rates are FY-versioned. Add a new entry per FY — changing params for a new FY changes output with no code change.</p>
        {params.map(p => (
          <div key={p.id} className="mb-4 pb-4 border-b border-zinc-800">
            <p className="text-yellow-400 font-semibold mb-2">FY {p.financial_year}</p>
            <div className="grid grid-cols-4 gap-3 text-sm">
              {[["PF Wage Ceiling", fmt(p.pf_wage_ceiling)], ["Employee PF Rate", pct(p.pf_employee_rate)], ["Employer EPF Rate", pct(p.pf_employer_epf_rate)], ["Employer EPS Rate", pct(p.pf_employer_eps_rate)], ["ESI Wage Ceiling", fmt(p.esi_wage_ceiling)], ["Employee ESI Rate", pct(p.esi_employee_rate)], ["Employer ESI Rate", pct(p.esi_employer_rate)], ["Standard Deduction", fmt(p.standard_deduction)], ["Cess Rate", pct(p.cess_rate)]].map(([label, val]) => (
                <div key={label}><p className="text-zinc-500 text-xs">{label}</p><p className="text-white">{val}</p></div>
              ))}
            </div>
            {p.tds_new_regime_slabs?.length > 0 && (
              <div className="mt-3">
                <p className="text-xs text-zinc-400 mb-1">TDS New Regime Slabs</p>
                <div className="flex flex-wrap gap-2">
                  {p.tds_new_regime_slabs.map((s, i) => (
                    <span key={i} className="text-xs bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded">{s.max_income ? `${fmt(s.min_income)}–${fmt(s.max_income)}` : `>${fmt(s.min_income)}`}: {s.rate}%</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
        {params.length === 0 && <p className="text-zinc-500 text-sm py-4 text-center">No statutory params configured — seed data will populate FY 2024-25 defaults</p>}
      </Card>
    </div>
  );
}

// Form 16
function Form16Tab() {
  const [employees, setEmployees] = useState([]);
  const [form, setForm] = useState({ employee_id: "", fy: "2024-25" });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/hr/employees").then(r => setEmployees(r.data)).catch(() => api.get("/employees").then(r => setEmployees(r.data)).catch(() => {}));
  }, []);

  const generate = async () => {
    if (!form.employee_id) return;
    setLoading(true);
    try { const { data } = await api.get(`/payroll/form16/${form.employee_id}`, { params: { fy: form.fy } }); setResult(data); }
    catch (e) { alert(e.response?.data?.detail || "Error"); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      <SectionHeader title="Form 16 Generator" />
      <Card>
        <div className="grid grid-cols-3 gap-3 items-end">
          <Select label="Employee" value={form.employee_id} onChange={e => setForm(f => ({ ...f, employee_id: e.target.value }))}>
            <option value="">Select employee...</option>
            {employees.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
          </Select>
          <Input label="Financial Year" value={form.fy} onChange={e => setForm(f => ({ ...f, fy: e.target.value }))} />
          <Btn onClick={generate} disabled={loading}>{loading ? "Generating..." : "Generate Form 16"}</Btn>
        </div>
      </Card>
      {result && (
        <>
          <Card className="border-blue-800/40">
            <p className="text-blue-400 font-semibold mb-3">Part A — TDS Deducted at Source</p>
            <div className="flex justify-between items-center">
              <p className="text-white">{result.part_a.employee_name} · FY {result.part_a.financial_year}</p>
              <p className="text-yellow-400 text-xl font-bold">{fmt(result.part_a.total_tds_deposited)}</p>
            </div>
            <div className="mt-3 grid grid-cols-4 gap-2">
              {result.part_a.quarters?.map(q => (
                <div key={q.quarter} className="bg-zinc-800 rounded-lg p-2">
                  <p className="text-xs text-zinc-500">{q.quarter}</p>
                  <p className="text-white text-sm font-medium">{fmt(q.tds)}</p>
                </div>
              ))}
            </div>
          </Card>
          <Card className="border-emerald-800/40">
            <p className="text-emerald-400 font-semibold mb-3">Part B — Computation of Total Income ({result.part_b.regime?.toUpperCase()} Regime)</p>
            <div className="space-y-2 text-sm">
              {[["Total Gross Salary", result.part_b.total_gross_salary], ["Less: Standard Deduction", -result.part_b.standard_deduction], ["Less: Chapter VI-A Exemptions", -result.part_b.exemptions_80c_80d_hra], ["Add: Other Income", result.part_b.other_income]].map(([label, val]) => (
                <div key={label} className="flex justify-between py-1 border-b border-zinc-800">
                  <span className="text-zinc-300">{label}</span><span className={val < 0 ? "text-red-400" : "text-white"}>{fmt(Math.abs(val))}</span>
                </div>
              ))}
              <div className="flex justify-between py-2 font-semibold border-b border-zinc-700">
                <span className="text-white">Annual Taxable Income</span><span className="text-yellow-400">{fmt(result.part_b.annual_taxable_income)}</span>
              </div>
              {[["Income Tax", result.part_b.income_tax], ["Cess (4%)", result.part_b.cess]].map(([label, val]) => (
                <div key={label} className="flex justify-between py-1 border-b border-zinc-800">
                  <span className="text-zinc-300">{label}</span><span className="text-amber-400">{fmt(val)}</span>
                </div>
              ))}
              <div className="flex justify-between py-2 font-bold">
                <span className="text-white">Tax Payable</span><span className="text-yellow-400 text-lg">{fmt(result.part_b.annual_tax_payable)}</span>
              </div>
              {result.part_b.tax_refundable > 0 && <div className="bg-emerald-950/30 border border-emerald-800/40 rounded-lg p-3"><p className="text-emerald-400 text-sm font-semibold">Tax Refundable: {fmt(result.part_b.tax_refundable)}</p></div>}
              {result.part_b.tax_balance_payable > 0 && <div className="bg-red-950/30 border border-red-800/40 rounded-lg p-3"><p className="text-red-400 text-sm font-semibold">Balance Tax Payable: {fmt(result.part_b.tax_balance_payable)}</p></div>}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

// F&F Settlement
function FNFTab() {
  const [employees, setEmployees] = useState([]);
  const [form, setForm] = useState({ employee_id: "", last_working_day: "", financial_year: "2024-25", notice_recovery: "0", leave_encashment_days: "0", other_recoveries: "0", notes: "" });
  const [result, setResult] = useState(null);

  useEffect(() => {
    api.get("/hr/employees").then(r => setEmployees(r.data)).catch(() => api.get("/employees").then(r => setEmployees(r.data)).catch(() => {}));
  }, []);

  const compute = async () => {
    if (!form.employee_id) return;
    try {
      const payload = { ...form, notice_recovery: parseFloat(form.notice_recovery) || 0, leave_encashment_days: parseFloat(form.leave_encashment_days) || 0, other_recoveries: parseFloat(form.other_recoveries) || 0 };
      const { data } = await api.post(`/payroll/fnf/${form.employee_id}`, payload);
      setResult(data);
    } catch (e) { alert(e.response?.data?.detail || "Error"); }
  };

  return (
    <div className="space-y-4">
      <SectionHeader title="Full & Final Settlement" />
      <Card>
        <div className="grid grid-cols-3 gap-3">
          <Select label="Employee *" value={form.employee_id} onChange={e => setForm(f => ({ ...f, employee_id: e.target.value }))}>
            <option value="">Select employee...</option>
            {employees.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
          </Select>
          <Input label="Last Working Day *" type="date" value={form.last_working_day} onChange={e => setForm(f => ({ ...f, last_working_day: e.target.value }))} />
          <Input label="Financial Year" value={form.financial_year} onChange={e => setForm(f => ({ ...f, financial_year: e.target.value }))} />
          <Input label="Leave Encashment Days" type="number" value={form.leave_encashment_days} onChange={e => setForm(f => ({ ...f, leave_encashment_days: e.target.value }))} />
          <Input label="Notice Recovery (₹)" type="number" value={form.notice_recovery} onChange={e => setForm(f => ({ ...f, notice_recovery: e.target.value }))} />
          <Input label="Other Recoveries (₹)" type="number" value={form.other_recoveries} onChange={e => setForm(f => ({ ...f, other_recoveries: e.target.value }))} />
          <div className="col-span-3"><Input label="Notes" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} /></div>
        </div>
        <div className="mt-4"><Btn onClick={compute}>Compute F&amp;F Settlement</Btn></div>
      </Card>
      {result && (
        <Card className="border-yellow-800/40">
          <p className="text-yellow-400 font-semibold mb-3">F&amp;F Worksheet — {result.employee_name}</p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-zinc-400 mb-2 font-medium">Payable to Employee</p>
              {[["Salary for LWD Month", result.salary_for_lwd_month], [`Leave Encashment (${result.leave_encashment_days} days)`, result.leave_encashment], [`Gratuity${result.gratuity_eligible ? "" : " (not eligible — <5 yrs)"}`, result.gratuity]].map(([label, val]) => (
                <div key={label} className="flex justify-between text-sm py-1 border-b border-zinc-800">
                  <span className="text-zinc-300">{label}</span><span className="text-emerald-400">{fmt(val)}</span>
                </div>
              ))}
              <div className="flex justify-between text-sm py-2 font-semibold">
                <span className="text-white">Total Payable</span><span className="text-yellow-400">{fmt(result.total_payable)}</span>
              </div>
            </div>
            <div>
              <p className="text-xs text-zinc-400 mb-2 font-medium">Recoveries</p>
              {[["Notice Recovery", result.notice_recovery], ["Other Recoveries", result.other_recoveries]].map(([label, val]) => (
                <div key={label} className="flex justify-between text-sm py-1 border-b border-zinc-800">
                  <span className="text-zinc-300">{label}</span><span className="text-red-400">{fmt(val)}</span>
                </div>
              ))}
              <div className="flex justify-between text-sm py-2 font-semibold">
                <span className="text-white">Total Recoveries</span><span className="text-red-400">{fmt(result.total_recoveries)}</span>
              </div>
            </div>
          </div>
          <div className="mt-4 bg-zinc-800 rounded-lg p-4 flex items-center justify-between">
            <p className="text-zinc-400 text-sm">Service: {result.years_of_service} yrs · Joined: {result.date_of_joining} · LWD: {result.last_working_day}</p>
            <div className="text-right">
              <p className="text-xs text-zinc-400">Net Payable</p>
              <p className={`text-2xl font-bold ${result.net_payable >= 0 ? "text-emerald-400" : "text-red-400"}`}>{fmt(result.net_payable)}</p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

export default function Payroll() {
  const [activeTab, setActiveTab] = useState(0);

  const tabs = [
    <DashboardTab key="dash" />,
    <PayComponentsTab key="comp" />,
    <SalaryStructuresTab key="struct" />,
    <PayrollRunsTab key="runs" />,
    <PayslipsTab key="slips" />,
    <StatutoryTab key="stat" />,
    <Form16Tab key="f16" />,
    <FNFTab key="fnf" />,
  ];

  return (
    <div className="min-h-screen bg-zinc-950 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white">Payroll</h1>
          <p className="text-zinc-400 text-sm mt-1">Full Indian statutory payroll — PF · ESI · PT (state-wise) · TDS (old &amp; new regime) · Form 16 · F&amp;F</p>
        </div>
        <div className="flex gap-1 mb-6 bg-zinc-900 border border-zinc-800 rounded-xl p-1 flex-wrap">
          {TABS.map((tab, i) => (
            <button key={tab} onClick={() => setActiveTab(i)} className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${activeTab === i ? "bg-yellow-400 text-zinc-950" : "text-zinc-400 hover:text-white"}`}>{tab}</button>
          ))}
        </div>
        {tabs[activeTab]}
      </div>
    </div>
  );
}
