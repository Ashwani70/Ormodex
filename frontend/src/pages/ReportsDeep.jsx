import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { toast } from "sonner";

const Card = ({ children, className = "" }) => (
  <div className={`bg-zinc-900 border border-zinc-800 ${className}`} style={{ borderRadius: "var(--radius)" }}>
    {children}
  </div>
);

const Btn = ({ children, onClick, variant = "primary", disabled, className = "" }) => {
  const styles = {
    primary: "bg-yellow-400 text-black hover:bg-yellow-300",
    ghost: "border border-zinc-700 text-zinc-300 hover:border-yellow-400 hover:text-yellow-400",
  };
  return (
    <button onClick={onClick} disabled={disabled}
      className={`px-4 py-2 text-sm font-mono uppercase tracking-wider transition-colors disabled:opacity-40 ${styles[variant]} ${className}`}
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

const fmt = (v) =>
  v == null ? "—" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });

// ── Drill-down panel ──
function DrillPanel({ filters, onClose }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    api.get("/reports/drill", { params: filters })
      .then(({ data }) => setData(data))
      .catch(() => toast.error("Drill failed"));
  }, [filters]);
  return (
    <tr>
      <td colSpan={99} className="bg-zinc-950 p-0">
        <div className="p-4 border-l-4 border-yellow-400">
          <div className="flex justify-between items-center mb-2">
            <span className="text-xs font-mono uppercase tracking-wider text-yellow-400">
              Composing Vouchers {data ? `· ${data.line_count} lines · net ₹${fmt(data.net)}` : ""}
            </span>
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 text-xs font-mono">close ✕</button>
          </div>
          {!data ? <p className="text-zinc-500 text-sm">Loading…</p> : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] font-mono uppercase tracking-wider text-zinc-500 border-b border-zinc-800">
                  <th className="py-1.5 pr-3">Entry #</th><th className="pr-3">Date</th>
                  <th className="pr-3">Account</th><th className="pr-3">Narration</th>
                  <th className="pr-3 text-right">Debit</th><th className="pr-3 text-right">Credit</th>
                  <th className="text-right">Running</th>
                </tr>
              </thead>
              <tbody>
                {data.lines.map((l, i) => (
                  <tr key={i} className="border-b border-zinc-900 text-zinc-300">
                    <td className="py-1.5 pr-3 font-mono text-yellow-400">{l.entry_number || l.entry_id?.slice(0, 8)}</td>
                    <td className="pr-3">{l.date}</td>
                    <td className="pr-3">{l.account_name}</td>
                    <td className="pr-3 text-zinc-500 truncate max-w-xs">{l.narration}</td>
                    <td className="pr-3 text-right font-mono">{l.debit ? fmt(l.debit) : ""}</td>
                    <td className="pr-3 text-right font-mono">{l.credit ? fmt(l.credit) : ""}</td>
                    <td className="text-right font-mono text-zinc-400">{fmt(l.running_balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </td>
    </tr>
  );
}

// ── A line group (assets / income / etc.) with drillable rows ──
function LineGroup({ title, rows, columns, params, total }) {
  const [drill, setDrill] = useState(null);
  return (
    <>
      <tr className="bg-zinc-800/40">
        <td className="py-2 px-3 font-display font-bold text-zinc-100 uppercase text-xs tracking-wider" colSpan={1 + columns.length}>
          {title}
        </td>
      </tr>
      {rows.map((r, ri) => {
        const code = r.account_code;
        const drillKey = `${title}-${code}-${ri}`;
        return (
          <>
            <tr key={drillKey} className="border-b border-zinc-900 hover:bg-zinc-800/30 cursor-pointer"
              onClick={() => setDrill(drill === drillKey ? null : { ...params, account_code: code })}>
              <td className="py-1.5 px-3 text-zinc-300">
                <span className="text-yellow-400/60 mr-1">{drill === drillKey ? "▾" : "▸"}</span>
                {r.account_name || r.cost_center || code}
              </td>
              {columns.map((c, ci) => (
                <td key={ci} className="py-1.5 px-3 text-right font-mono text-zinc-200">
                  {fmt(c.cellLookup(code, r))}
                </td>
              ))}
            </tr>
            {drill === drillKey && <DrillPanel filters={drill} onClose={() => setDrill(null)} />}
          </>
        );
      })}
      {total != null && (
        <tr className="border-t-2 border-zinc-700 font-bold">
          <td className="py-2 px-3 text-zinc-100">Total {title}</td>
          {columns.map((c, ci) => (
            <td key={ci} className="py-2 px-3 text-right font-mono text-yellow-400">{fmt(c.total)}</td>
          ))}
        </tr>
      )}
    </>
  );
}

export default function ReportsDeep() {
  const [slug, setSlug] = useState("balance-sheet");
  const [catalog, setCatalog] = useState([]);
  const [fromFy, setFromFy] = useState("2024-25");
  const [toFy, setToFy] = useState("2024-25");
  const [compare, setCompare] = useState(false);
  const [branches, setBranches] = useState("");
  const [costCenters, setCostCenters] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [savedViews, setSavedViews] = useState([]);

  useEffect(() => {
    api.get("/reports/catalog").then(({ data }) => setCatalog(data.reports)).catch(() => {});
    api.get("/reports/saved-views").then(({ data }) => setSavedViews(data)).catch(() => {});
  }, []);

  const run = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/reports/run/${slug}`, {
        params: { fromFy, toFy: compare ? toFy : undefined, compare,
                  branches: branches || undefined, costCenters: costCenters || undefined },
      });
      setResult(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Report failed");
    } finally {
      setLoading(false);
    }
  }, [slug, fromFy, toFy, compare, branches, costCenters]);

  const saveView = async () => {
    const name = window.prompt("Save view as:");
    if (!name) return;
    try {
      await api.post("/reports/saved-views", {
        name, slug, params: { fromFy, toFy, compare, branches, costCenters },
      });
      const { data } = await api.get("/reports/saved-views");
      setSavedViews(data);
      toast.success("View saved");
    } catch (e) { toast.error("Save failed"); }
  };

  const loadView = (v) => {
    setSlug(v.slug);
    const p = v.params || {};
    setFromFy(p.fromFy || "2024-25");
    setToFy(p.toFy || "2024-25");
    setCompare(!!p.compare);
    setBranches(p.branches || "");
    setCostCenters(p.costCenters || "");
  };

  // Build comparative column descriptors from the response
  const cols = (result?.columns || []).map((col) => ({
    fy: col.fy,
    data: col.data,
  }));

  const baseParams = {
    fromFy, toFy: compare ? toFy : fromFy,
    branch: branches.split(",")[0] || undefined,
  };

  const renderFinancialReport = (groups) => {
    // groups: [{title, key, totalKey}]
    return (
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] font-mono uppercase tracking-wider text-zinc-500 border-b border-zinc-700">
            <th className="py-2 px-3">Account</th>
            {cols.map((c) => <th key={c.fy} className="py-2 px-3 text-right">{c.fy}</th>)}
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => {
            const rows = cols[0]?.data?.[g.key] || [];
            const columnDescriptors = cols.map((c) => ({
              cellLookup: (code) => (c.data[g.key] || []).find((x) => x.account_code === code)?.amount,
              total: c.data[g.totalKey],
            }));
            return (
              <LineGroup key={g.key} title={g.title} rows={rows} columns={columnDescriptors}
                params={baseParams} total={cols[0]?.data?.[g.totalKey]} />
            );
          })}
        </tbody>
      </table>
    );
  };

  const renderRatios = () => (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-[11px] font-mono uppercase tracking-wider text-zinc-500 border-b border-zinc-700">
          <th className="py-2 px-3">Ratio</th>
          {cols.map((c) => <th key={c.fy} className="py-2 px-3 text-right">{c.fy}</th>)}
        </tr>
      </thead>
      <tbody>
        {["current_ratio", "quick_ratio", "debt_equity_ratio", "gross_margin_pct",
          "net_margin_pct", "roce_pct", "inventory_days", "debtor_days"].map((k) => (
          <tr key={k} className="border-b border-zinc-900 hover:bg-zinc-800/30">
            <td className="py-1.5 px-3 text-zinc-300">{k.replace(/_/g, " ")}</td>
            {cols.map((c) => (
              <td key={c.fy} className="py-1.5 px-3 text-right font-mono text-zinc-200">
                {c.data[k] == null ? "—" : fmt(c.data[k])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );

  const renderFundFlow = () => {
    const d = cols[0]?.data;
    if (!d) return null;
    return (
      <div className="grid grid-cols-2 gap-6">
        <div>
          <h3 className="font-display font-bold text-emerald-400 mb-2 uppercase text-xs tracking-wider">Sources of Funds</h3>
          {d.sources.map((s, i) => (
            <div key={i} className="flex justify-between py-1 border-b border-zinc-900 text-sm">
              <span className="text-zinc-300">{s.name}</span><span className="font-mono text-zinc-200">{fmt(s.amount)}</span>
            </div>
          ))}
          <div className="flex justify-between py-2 font-bold border-t-2 border-zinc-700 mt-1">
            <span className="text-zinc-100">Total</span><span className="font-mono text-yellow-400">{fmt(d.total_sources)}</span>
          </div>
        </div>
        <div>
          <h3 className="font-display font-bold text-orange-400 mb-2 uppercase text-xs tracking-wider">Applications of Funds</h3>
          {d.applications.map((a, i) => (
            <div key={i} className="flex justify-between py-1 border-b border-zinc-900 text-sm">
              <span className="text-zinc-300">{a.name}</span><span className="font-mono text-zinc-200">{fmt(a.amount)}</span>
            </div>
          ))}
          <div className="flex justify-between py-2 font-bold border-t-2 border-zinc-700 mt-1">
            <span className="text-zinc-100">Total</span><span className="font-mono text-yellow-400">{fmt(d.total_applications)}</span>
          </div>
        </div>
      </div>
    );
  };

  const renderCostCenter = () => {
    const rows = cols[0]?.data?.rows || [];
    return (
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] font-mono uppercase tracking-wider text-zinc-500 border-b border-zinc-700">
            <th className="py-2 px-3">Cost Center</th>
            {cols.map((c) => <th key={c.fy} className="py-2 px-3 text-right">{c.fy}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <CostCenterRow key={ri} row={r} cols={cols} params={baseParams} />
          ))}
        </tbody>
      </table>
    );
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="font-display font-black text-2xl text-zinc-50 tracking-tight">Reports — Deeper</h1>
        <p className="text-zinc-500 text-sm mt-1">Ratio analysis, fund flow, comparative & consolidated statements — with drill-down to vouchers.</p>
      </div>

      {/* Controls */}
      <Card className="p-5 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-3 items-end">
          <Select label="Report" value={slug} onChange={(e) => setSlug(e.target.value)}>
            {catalog.map((r) => <option key={r.slug} value={r.slug}>{r.name}</option>)}
          </Select>
          <Input label="From FY" value={fromFy} onChange={(e) => setFromFy(e.target.value)} placeholder="2024-25" />
          <Input label="To FY" value={toFy} onChange={(e) => setToFy(e.target.value)} placeholder="2024-25" disabled={!compare} />
          <Input label="Branches (csv)" value={branches} onChange={(e) => setBranches(e.target.value)} placeholder="HO,MUM" />
          <Input label="Cost Centers (csv)" value={costCenters} onChange={(e) => setCostCenters(e.target.value)} placeholder="" />
          <label className="flex items-center gap-2 text-sm text-zinc-300 pb-2">
            <input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} className="accent-yellow-400" />
            Comparative
          </label>
        </div>
        <div className="flex gap-2 mt-4">
          <Btn onClick={run} disabled={loading}>{loading ? "Running…" : "Run Report"}</Btn>
          <Btn variant="ghost" onClick={saveView}>Save View</Btn>
        </div>
        {savedViews.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {savedViews.map((v) => (
              <button key={v.id} onClick={() => loadView(v)}
                className="text-xs font-mono px-2 py-1 border border-zinc-800 text-zinc-400 hover:border-yellow-400 hover:text-yellow-400">
                {v.name}
              </button>
            ))}
          </div>
        )}
      </Card>

      {/* Result */}
      {result && (
        <Card className="p-5">
          {slug === "balance-sheet" && renderFinancialReport([
            { title: "Assets", key: "assets", totalKey: "total_assets" },
            { title: "Liabilities", key: "liabilities", totalKey: "total_liabilities" },
            { title: "Equity", key: "equity", totalKey: "total_equity" },
          ])}
          {slug === "profit-loss" && renderFinancialReport([
            { title: "Income", key: "income", totalKey: "total_income" },
            { title: "Expense", key: "expense", totalKey: "total_expense" },
          ])}
          {slug === "ratios" && renderRatios()}
          {slug === "fund-flow" && renderFundFlow()}
          {slug === "cost-center" && renderCostCenter()}
        </Card>
      )}
    </div>
  );
}

function CostCenterRow({ row, cols, params }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr className="border-b border-zinc-900 hover:bg-zinc-800/30 cursor-pointer"
        onClick={() => setOpen((o) => !o)}>
        <td className="py-1.5 px-3 text-zinc-300">
          <span className="text-yellow-400/60 mr-1">{open ? "▾" : "▸"}</span>{row.cost_center}
        </td>
        {cols.map((c) => {
          const m = (c.data.rows || []).find((x) => x.cost_center === row.cost_center);
          return <td key={c.fy} className="py-1.5 px-3 text-right font-mono text-zinc-200">{fmt(m?.amount)}</td>;
        })}
      </tr>
      {open && <DrillPanel filters={{ ...params, cost_center: row.cost_center }} onClose={() => setOpen(false)} />}
    </>
  );
}
