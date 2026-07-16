import { useState, useEffect, useCallback, useRef } from "react";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import useGridKeyNav from "@/hooks/useGridKeyNav";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
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
const fmt = (v) => (v == null ? "—" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

// ── Branch master ──
function BranchesTab({ branches, reload }) {
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({ name: "", code: "", gstin: "", state_code: "", address: "" });

  const create = async () => {
    if (!form.name || !form.code) return toast.error("Name and code required");
    try {
      await api.post("/branches", form);
      toast.success("Branch created"); setShow(false);
      setForm({ name: "", code: "", gstin: "", state_code: "", address: "" });
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  // Enter-as-Tab across the New Branch form; Ctrl+Enter/Ctrl+S saves, Esc
  // cancels. Primary create action on this tab → owns Ctrl+N.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: show,
    autoFocus: true,
    onSave: create,
    onCancel: () => setShow(false),
  });
  useModuleShortcuts({
    onNew: () => { if (!show) setShow(true); },
  });

  return (
    <div>
      <SectionHeader title="Branch Master" subtitle="Each branch may have its own GSTIN / state"
        right={<Btn onClick={() => setShow((v) => !v)}>{show ? "Cancel" : "+ New Branch"}</Btn>} />
      {show && (
        <Card className="p-5 mb-5">
          <div ref={formRef} className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <Input label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <Input label="Code" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="MUM" />
            <Input label="GSTIN" value={form.gstin} onChange={(e) => setForm({ ...form, gstin: e.target.value })} />
            <Input label="State Code" value={form.state_code} onChange={(e) => setForm({ ...form, state_code: e.target.value })} placeholder="27" />
            <Input label="Address" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          </div>
          <div className="mt-4"><Btn onClick={create}>Create Branch</Btn></div>
        </Card>
      )}
      <Card className="p-4">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] font-mono uppercase text-zinc-500 border-b border-zinc-800">
            <th className="py-2">Code</th><th>Name</th><th>GSTIN</th><th>State</th>
          </tr></thead>
          <tbody>
            {branches.map((b) => (
              <tr key={b.id} className="border-b border-zinc-900">
                <td className="py-2 font-mono text-yellow-400">{b.code}</td>
                <td className="text-zinc-200">{b.name}</td>
                <td className="text-zinc-400 font-mono text-xs">{b.gstin || "—"}</td>
                <td className="text-zinc-400">{b.state_code || "—"}</td>
              </tr>
            ))}
            {branches.length === 0 && <tr><td colSpan={4} className="py-6 text-center text-zinc-500">No branches.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ── Inter-branch transfer ──
function TransferTab({ branches }) {
  const [form, setForm] = useState({ from_branch: "", to_branch: "" });
  const [items, setItems] = useState([{ item_id: "", name: "", qty: "", rate: "", gst_rate: "18" }]);
  const [result, setResult] = useState(null);
  const [transfers, setTransfers] = useState([]);

  const loadTransfers = useCallback(async () => {
    try { setTransfers((await api.get("/branches/inter-branch-transfers/list")).data); } catch {}
  }, []);
  useEffect(() => { loadTransfers(); }, [loadTransfers]);

  const submit = async () => {
    if (!form.from_branch || !form.to_branch) return toast.error("Pick both branches");
    if (form.from_branch === form.to_branch) return toast.error("Branches must differ");
    try {
      const { data } = await api.post("/branches/inter-branch-transfers", {
        from_branch: form.from_branch, to_branch: form.to_branch,
        items: items.filter((i) => i.item_id && i.qty).map((i) => ({
          item_id: i.item_id, name: i.name, qty: Number(i.qty), rate: Number(i.rate), gst_rate: Number(i.gst_rate),
        })),
      });
      setResult(data);
      toast.success(`Transfer ${data.transfer_no} · ${data.is_interstate ? "IGST" : "CGST+SGST"}`);
      loadTransfers();
    } catch (e) { toast.error(e?.response?.data?.detail || "Transfer failed"); }
  };

  // Items grid: item_id, name, qty, rate, gst — 5 columns. Enter on the last
  // cell of the last row appends a new item.
  const addItem = () => setItems((prev) => [...prev, { item_id: "", name: "", qty: "", rate: "", gst_rate: "18" }]);
  const insertItemAfter = (i) => setItems((prev) => {
    const next = [...prev];
    next.splice(i + 1, 0, { item_id: "", name: "", qty: "", rate: "", gst_rate: "18" });
    return next;
  });
  const removeItemKeepingOne = (i) => setItems((prev) =>
    prev.length > 1 ? prev.filter((_, j) => j !== i) : [{ item_id: "", name: "", qty: "", rate: "", gst_rate: "18" }]);
  const itemsGrid = useGridKeyNav({
    rowCount: items.length,
    colCount: 5,
    onRowComplete: addItem,
    onInsertRow: insertItemAfter,
    onDeleteRow: removeItemKeepingOne,
  });

  // Enter-as-Tab across the whole transfer form (header fields + items
  // grid, marked data-grid-managed). Ctrl+Enter/Ctrl+S raises the transfer.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: true,
    onSave: submit,
  });

  return (
    <div>
      <SectionHeader title="Inter-Branch Transfer" subtitle="GST-taxable supply between distinct GSTINs (IGST if different states)" />
      <Card className="p-5 mb-5">
        <div ref={formRef}>
          <div className="grid grid-cols-2 gap-3 mb-4">
            <Select label="From Branch" value={form.from_branch} onChange={(e) => setForm({ ...form, from_branch: e.target.value })}>
              <option value="">—</option>{branches.map((b) => <option key={b.id} value={b.id}>{b.code} ({b.state_code})</option>)}
            </Select>
            <Select label="To Branch" value={form.to_branch} onChange={(e) => setForm({ ...form, to_branch: e.target.value })}>
              <option value="">—</option>{branches.map((b) => <option key={b.id} value={b.id}>{b.code} ({b.state_code})</option>)}
            </Select>
          </div>
          <span className="block text-xs font-mono uppercase text-zinc-500 mb-2">Items</span>
          <div data-grid-managed>
            {items.map((it, i) => (
              <div key={i} className="grid grid-cols-12 gap-2 mb-2">
                <input className="col-span-4 bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-sm text-zinc-100" placeholder="item_id"
                  value={it.item_id} onChange={(e) => setItems(items.map((x, j) => j === i ? { ...x, item_id: e.target.value } : x))}
                  ref={itemsGrid.registerCell(i, 0)} onKeyDown={itemsGrid.handleKeyDown(i, 0)} />
                <input className="col-span-3 bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-sm text-zinc-100" placeholder="name"
                  value={it.name} onChange={(e) => setItems(items.map((x, j) => j === i ? { ...x, name: e.target.value } : x))}
                  ref={itemsGrid.registerCell(i, 1)} onKeyDown={itemsGrid.handleKeyDown(i, 1)} />
                <input className="col-span-2 bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-sm text-zinc-100" placeholder="qty" type="text" inputMode="decimal"
                  value={it.qty} onChange={(e) => setItems(items.map((x, j) => j === i ? { ...x, qty: e.target.value } : x))}
                  ref={itemsGrid.registerCell(i, 2)} onKeyDown={itemsGrid.handleKeyDown(i, 2)} />
                <input className="col-span-2 bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-sm text-zinc-100" placeholder="rate" type="text" inputMode="decimal"
                  value={it.rate} onChange={(e) => setItems(items.map((x, j) => j === i ? { ...x, rate: e.target.value } : x))}
                  ref={itemsGrid.registerCell(i, 3)} onKeyDown={itemsGrid.handleKeyDown(i, 3)} />
                <input className="col-span-1 bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-sm text-zinc-100" placeholder="gst" type="text" inputMode="decimal"
                  value={it.gst_rate} onChange={(e) => setItems(items.map((x, j) => j === i ? { ...x, gst_rate: e.target.value } : x))}
                  ref={itemsGrid.registerCell(i, 4)} onKeyDown={itemsGrid.handleKeyDown(i, 4)} />
              </div>
            ))}
          </div>
          <button onClick={addItem}
            className="text-xs font-mono text-yellow-400 hover:text-yellow-300">+ add item</button>
          <div className="mt-4"><Btn onClick={submit}>Raise Transfer</Btn></div>
        </div>
      </Card>

      {result && (
        <Card className="p-5 mb-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-display font-bold text-emerald-400">{result.transfer_no} ✓</h3>
            <span className={`text-xs font-mono px-2 py-1 ${result.is_interstate ? "text-blue-400 bg-blue-500/10" : "text-zinc-300 bg-zinc-800"}`}>
              {result.is_interstate ? "INTER-STATE · IGST" : "INTRA-STATE · CGST+SGST"}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div><span className="text-zinc-500">Taxable</span><div className="font-mono text-zinc-100">₹{fmt(result.taxable_value)}</div></div>
            <div><span className="text-zinc-500">CGST</span><div className="font-mono text-zinc-100">₹{fmt(result.cgst)}</div></div>
            <div><span className="text-zinc-500">SGST</span><div className="font-mono text-zinc-100">₹{fmt(result.sgst)}</div></div>
            <div><span className="text-zinc-500">IGST</span><div className="font-mono text-zinc-100">₹{fmt(result.igst)}</div></div>
            <div><span className="text-zinc-500">Invoice Value</span><div className="font-mono text-yellow-400">₹{fmt(result.invoice_value)}</div></div>
            <div><span className="text-zinc-500">E-way Bill</span><div className="font-mono text-zinc-100">{result.eway_bill_required ? result.eway_bill_no : "not required"}</div></div>
          </div>
        </Card>
      )}

      <Card className="p-4">
        <h3 className="font-display font-bold text-zinc-50 mb-3">Recent Transfers</h3>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] font-mono uppercase text-zinc-500 border-b border-zinc-800">
            <th className="py-2">Transfer</th><th>From → To</th><th>Tax</th><th className="text-right">Value</th><th>E-way</th>
          </tr></thead>
          <tbody>
            {transfers.map((t) => (
              <tr key={t.id} className="border-b border-zinc-900">
                <td className="py-2 font-mono text-yellow-400">{t.transfer_no}</td>
                <td className="text-zinc-300">{t.from_branch_name} → {t.to_branch_name}</td>
                <td className="text-zinc-400 text-xs">{t.is_interstate ? "IGST" : "CGST+SGST"}</td>
                <td className="text-right font-mono text-zinc-200">₹{fmt(t.invoice_value)}</td>
                <td className="text-xs text-zinc-500">{t.eway_bill_no || "—"}</td>
              </tr>
            ))}
            {transfers.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-zinc-500">No transfers.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ── Consolidated B/S (standalone vs consolidated toggle) ──
function ConsolidationTab({ branches }) {
  const [fy, setFy] = useState("2024-25");
  const [data, setData] = useState(null);

  const run = async () => {
    try {
      const { data } = await api.get("/reports/consolidated/balance-sheet", { params: { fy } });
      setData(data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Consolidation failed"); }
  };

  return (
    <div>
      <SectionHeader title="Consolidated Balance Sheet" subtitle="Sum of standalone branches, inter-branch eliminated"
        right={<div className="flex gap-2 items-end"><Input label="FY" value={fy} onChange={(e) => setFy(e.target.value)} /><Btn onClick={run}>Consolidate</Btn></div>} />
      {data && (
        <div className="space-y-4">
          <Card className="p-4">
            <div className="text-xs font-mono uppercase text-zinc-500 mb-2">Standalone Branches</div>
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] font-mono uppercase text-zinc-500 border-b border-zinc-800">
                <th className="py-1">Branch</th><th className="text-right">Assets</th><th className="text-right">Liabilities</th><th className="text-right">Equity</th>
              </tr></thead>
              <tbody>
                {Object.entries(data.standalone).map(([b, v]) => (
                  <tr key={b} className="border-b border-zinc-900">
                    <td className="py-1.5 text-zinc-300 font-mono">{b}</td>
                    <td className="text-right font-mono text-zinc-200">₹{fmt(v.total_assets)}</td>
                    <td className="text-right font-mono text-zinc-200">₹{fmt(v.total_liabilities)}</td>
                    <td className="text-right font-mono text-zinc-200">₹{fmt(v.total_equity)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          {data.eliminations.length > 0 && (
            <Card className="p-4">
              <div className="text-xs font-mono uppercase text-amber-400 mb-2">Inter-Branch Eliminations</div>
              {data.eliminations.map((e, i) => (
                <div key={i} className="flex justify-between text-sm py-1 border-b border-zinc-900">
                  <span className="text-zinc-300">{e.name}</span><span className="font-mono text-amber-400">−₹{fmt(e.eliminated)}</span>
                </div>
              ))}
            </Card>
          )}

          <Card className="p-4">
            <div className="text-xs font-mono uppercase text-emerald-400 mb-2">Consolidated Group</div>
            <div className="grid grid-cols-3 gap-3">
              <KPI label="Total Assets" value={data.consolidated.total_assets} />
              <KPI label="Total Liabilities" value={data.consolidated.total_liabilities} />
              <KPI label="Total Equity" value={data.consolidated.total_equity} />
            </div>
            <div className={`mt-3 text-sm font-mono ${data.reconciliation.ties ? "text-emerald-400" : "text-red-400"}`}>
              {data.reconciliation.ties ? "✓ Ties to sum of standalones net of eliminations" : "✗ Does not tie — review"}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

const KPI = ({ label, value }) => (
  <div className="bg-zinc-950 border border-zinc-800 p-3" style={{ borderRadius: "var(--radius)" }}>
    <div className="text-[11px] font-mono uppercase tracking-wider text-zinc-500">{label}</div>
    <div className="text-lg font-display font-black text-zinc-100">₹{fmt(value)}</div>
  </div>
);

const TABS = [
  { id: "branches", label: "Branches" },
  { id: "transfers", label: "Inter-Branch Transfers" },
  { id: "consolidation", label: "Consolidation" },
];

export default function Branches() {
  const [tab, setTab] = useState("branches");
  const [branches, setBranches] = useState([]);

  const reload = useCallback(async () => {
    try { setBranches((await api.get("/branches")).data); } catch {}
  }, []);
  useEffect(() => { reload(); }, [reload]);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="font-display font-black text-2xl text-zinc-50 tracking-tight">Branch / Multi-location</h1>
        <p className="text-zinc-500 text-sm mt-1">Branch books, inter-branch transfers with GST, and consolidated reporting.</p>
      </div>
      <div className="flex gap-1 border-b border-zinc-800 mb-6">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2.5 text-sm font-mono uppercase tracking-wider border-b-2 -mb-px ${
              tab === t.id ? "border-yellow-400 text-yellow-400" : "border-transparent text-zinc-500 hover:text-zinc-300"}`}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "branches" && <BranchesTab branches={branches} reload={reload} />}
      {tab === "transfers" && <TransferTab branches={branches} />}
      {tab === "consolidation" && <ConsolidationTab branches={branches} />}
    </div>
  );
}
