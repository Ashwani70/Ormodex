import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";

const TABS = ["Asset Register", "Categories", "IT Blocks", "Depreciation", "Disposals", "Schedule"];

const StatusBadge = ({ status }) => {
  const colors = {
    ACTIVE: "bg-green-950",
    DISPOSED: "bg-red-950",
    TRANSFERRED: "bg-blue-950",
    WRITTEN_OFF: "bg-zinc-800",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${colors[status] ?? "bg-zinc-800 text-zinc-400"}`}>
      {status}
    </span>
  );
};

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
    <input
      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yellow-400"
      {...props}
    />
  </div>
);

const Select = ({ label, children, ...props }) => (
  <div>
    {label && <label className="block text-xs text-zinc-400 mb-1">{label}</label>}
    <select
      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yellow-400"
      {...props}
    >
      {children}
    </select>
  </div>
);

const Btn = ({ children, onClick, variant = "primary", disabled, className = "" }) => {
  const base = "px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50";
  const variants = {
    primary: "bg-yellow-400 text-zinc-950 hover:bg-yellow-300",
    secondary: "bg-zinc-700 text-white hover:bg-zinc-600",
    danger: "bg-red-800 text-white hover:bg-red-700",
    ghost: "text-zinc-400 hover:text-white",
  };
  return (
    <button className={`${base} ${variants[variant]} ${className}`} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
};

const fmt = (n) => (n == null ? "—" : `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`);

// ════════════════════════════════════════════
// Asset Register Tab
// ════════════════════════════════════════════
function AssetRegisterTab({ categories }) {
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState({ q: "", category_id: "", status: "" });
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({
    description: "", category_id: "", purchase_date: "", capitalized_date: "",
    gross_value: "", salvage_value: "", branch_id: "", location: "", notes: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filter.q) params.q = filter.q;
      if (filter.category_id) params.category_id = filter.category_id;
      if (filter.status) params.status = filter.status;
      const { data } = await api.get("/fixed-assets/assets", { params });
      setAssets(data);
    } catch {
      setAssets([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    try {
      await api.post("/fixed-assets/assets", {
        ...form,
        gross_value: parseFloat(form.gross_value) || 0,
        salvage_value: parseFloat(form.salvage_value) || 0,
      });
      setShowForm(false);
      setForm({ description: "", category_id: "", purchase_date: "", capitalized_date: "", gross_value: "", salvage_value: "", branch_id: "", location: "", notes: "" });
      load();
    } catch (e) {
      alert(e.response?.data?.detail || "Error saving asset");
    }
  };

  // Enter-as-Tab across the Add Asset form; Ctrl+Enter/Ctrl+S saves, Esc
  // cancels, first field auto-focuses when the modal opens. This is the
  // page's primary create action, so it also owns the Ctrl+N shortcut.
  const assetFormRef = useRef(null);
  useEnterNavigation(assetFormRef, {
    enabled: showForm,
    autoFocus: true,
    onSave: () => save(),
    onCancel: () => setShowForm(false),
  });
  useModuleShortcuts({
    onNew: () => { if (!showForm) setShowForm(true); },
  });

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Fixed Asset Register"
        action={<Btn onClick={() => setShowForm(true)}>+ Add Asset</Btn>}
      />

      {/* Filters */}
      <Card>
        <div className="grid grid-cols-3 gap-3">
          <Input placeholder="Search..." value={filter.q} onChange={e => setFilter(f => ({ ...f, q: e.target.value }))} />
          <Select value={filter.category_id} onChange={e => setFilter(f => ({ ...f, category_id: e.target.value }))}>
            <option value="">All Categories</option>
            {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select value={filter.status} onChange={e => setFilter(f => ({ ...f, status: e.target.value }))}>
            <option value="">All Status</option>
            {["ACTIVE", "DISPOSED", "TRANSFERRED", "WRITTEN_OFF"].map(s => <option key={s} value={s}>{s}</option>)}
          </Select>
        </div>
      </Card>

      {/* Table */}
      <Card>
        {loading ? (
          <p className="text-zinc-500 text-sm text-center py-8">Loading...</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-zinc-400 border-b border-zinc-800">
                <th className="text-left py-2 pr-3">Code</th>
                <th className="text-left py-2 pr-3">Description</th>
                <th className="text-left py-2 pr-3">Category</th>
                <th className="text-right py-2 pr-3">Gross Value</th>
                <th className="text-right py-2 pr-3">CA WDV</th>
                <th className="text-left py-2 pr-3">Status</th>
                <th className="text-left py-2">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {assets.map(a => {
                const cat = categories.find(c => c.id === a.category_id);
                return (
                  <tr key={a.id} className="hover:bg-zinc-800/50">
                    <td className="py-2 pr-3 text-yellow-400 font-mono">{a.code}</td>
                    <td className="py-2 pr-3 text-white">{a.description}</td>
                    <td className="py-2 pr-3 text-zinc-400">{cat?.name ?? a.category_id}</td>
                    <td className="py-2 pr-3 text-right text-white">{fmt(a.gross_value)}</td>
                    <td className="py-2 pr-3 text-right text-emerald-400">{fmt(a.ca_opening_wdv)}</td>
                    <td className="py-2 pr-3"><StatusBadge status={a.status} /></td>
                    <td className="py-2">
                      <Btn variant="ghost" className="text-xs" onClick={() => setSelected(a)}>Details</Btn>
                    </td>
                  </tr>
                );
              })}
              {assets.length === 0 && (
                <tr><td colSpan={7} className="py-8 text-center text-zinc-500">No assets found</td></tr>
              )}
            </tbody>
          </table>
        )}
      </Card>

      {/* Add Form Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div ref={assetFormRef} className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-lg space-y-4">
            <h3 className="text-white font-semibold text-lg">Add Fixed Asset</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <Input label="Description *" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="e.g. CNC Machine Model XZ-100" />
              </div>
              <Select label="Category *" value={form.category_id} onChange={e => setForm(f => ({ ...f, category_id: e.target.value }))}>
                <option value="">Select category...</option>
                {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
              <Input label="Purchase Date *" type="date" value={form.purchase_date} onChange={e => setForm(f => ({ ...f, purchase_date: e.target.value }))} />
              <Input label="Capitalized / Put to Use Date *" type="date" value={form.capitalized_date} onChange={e => setForm(f => ({ ...f, capitalized_date: e.target.value }))} />
              <Input label="Gross Value (₹) *" type="text" inputMode="decimal" value={form.gross_value} onChange={e => setForm(f => ({ ...f, gross_value: e.target.value }))} />
              <Input label="Salvage Value (₹) — leave 0 for category default" type="text" inputMode="decimal" value={form.salvage_value} onChange={e => setForm(f => ({ ...f, salvage_value: e.target.value }))} />
              <Input label="Branch / Location" value={form.location} onChange={e => setForm(f => ({ ...f, location: e.target.value }))} />
              <Input label="Notes" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Btn variant="secondary" onClick={() => setShowForm(false)}>Cancel</Btn>
              <Btn onClick={save}>Save Asset</Btn>
            </div>
          </div>
        </div>
      )}

      {/* Asset Detail Panel */}
      {selected && <AssetDetailPanel asset={selected} categories={categories} onClose={() => { setSelected(null); load(); }} />}
    </div>
  );
}

// ════════════════════════════════════════════
// Asset Detail — dispose / transfer / revalue
// ════════════════════════════════════════════
function AssetDetailPanel({ asset, categories, onClose }) {
  const [txns, setTxns] = useState([]);
  const [action, setAction] = useState(null); // "dispose" | "transfer" | "revalue"
  const [form, setForm] = useState({});
  const cat = categories.find(c => c.id === asset.category_id);

  useEffect(() => {
    api.get(`/fixed-assets/assets/${asset.id}/transactions`)
      .then(r => setTxns(r.data))
      .catch(() => {});
  }, [asset.id]);

  const submit = async () => {
    try {
      const payload = { ...form };
      if (action === "dispose") {
        payload.sale_consideration = parseFloat(form.sale_consideration) || 0;
        await api.post(`/fixed-assets/assets/${asset.id}/dispose`, payload);
      } else if (action === "transfer") {
        await api.post(`/fixed-assets/assets/${asset.id}/transfer`, payload);
      } else if (action === "revalue") {
        payload.new_gross_value = parseFloat(form.new_gross_value) || 0;
        await api.post(`/fixed-assets/assets/${asset.id}/revalue`, payload);
      }
      setAction(null);
      onClose();
    } catch (e) {
      alert(e.response?.data?.detail || "Error");
    }
  };

  // Each dispose/transfer/revalue sub-form is a separate small panel gated by
  // `action`, but they share one submit() — so each gets its own ref/hook,
  // enabled only while its own panel is showing, all calling the same submit.
  const disposeFormRef = useRef(null);
  useEnterNavigation(disposeFormRef, {
    enabled: action === "dispose",
    autoFocus: true,
    onSave: () => submit(),
    onCancel: () => setAction(null),
  });
  const transferFormRef = useRef(null);
  useEnterNavigation(transferFormRef, {
    enabled: action === "transfer",
    autoFocus: true,
    onSave: () => submit(),
    onCancel: () => setAction(null),
  });
  const revalueFormRef = useRef(null);
  useEnterNavigation(revalueFormRef, {
    enabled: action === "revalue",
    autoFocus: true,
    onSave: () => submit(),
    onCancel: () => setAction(null),
  });

  const currentFY = () => {
    const now = new Date();
    const yr = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
    return `${yr}-${String(yr + 1).slice(-2)}`;
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-2xl space-y-4 max-h-screen overflow-y-auto">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-white font-semibold text-lg">{asset.description}</h3>
            <p className="text-zinc-400 text-sm">{asset.code} · {cat?.name}</p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-white text-xl">✕</button>
        </div>

        {/* Summary */}
        <div className="grid grid-cols-3 gap-3">
          {[
            ["Gross Value", fmt(asset.gross_value)],
            ["CA WDV", fmt(asset.ca_opening_wdv)],
            ["Residual", fmt(asset.salvage_value)],
            ["IT Cost", fmt(asset.it_cost_for_block)],
            ["IT WDV", fmt(asset.it_opening_wdv)],
            ["Status", <StatusBadge key="s" status={asset.status} />],
          ].map(([label, val]) => (
            <Card key={label} className="!p-3">
              <p className="text-xs text-zinc-400 mb-1">{label}</p>
              <div className="text-white font-medium">{val}</div>
            </Card>
          ))}
        </div>

        {/* Transaction History */}
        {txns.length > 0 && (
          <div>
            <p className="text-zinc-400 text-xs font-medium mb-2">Transaction History</p>
            <table className="w-full text-xs">
              <thead><tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left pb-1">Date</th><th className="text-left pb-1">Type</th><th className="text-right pb-1">Amount</th><th className="text-left pb-1">Notes</th>
              </tr></thead>
              <tbody className="divide-y divide-zinc-800">
                {txns.map((t, i) => (
                  <tr key={i}>
                    <td className="py-1 text-zinc-300">{t.date}</td>
                    <td className="py-1 text-zinc-400 capitalize">{t.type}</td>
                    <td className="py-1 text-right text-white">{fmt(t.amount)}</td>
                    <td className="py-1 text-zinc-500">{t.notes ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Actions */}
        {asset.status === "ACTIVE" && (
          <div className="flex gap-3 pt-2">
            <Btn variant="danger" onClick={() => { setAction("dispose"); setForm({ disposal_date: new Date().toISOString().slice(0, 10), sale_consideration: "", financial_year: currentFY(), notes: "" }); }}>Dispose</Btn>
            <Btn variant="secondary" onClick={() => { setAction("transfer"); setForm({ transfer_date: new Date().toISOString().slice(0, 10), to_branch_id: "", to_location: "", notes: "" }); }}>Transfer</Btn>
            <Btn variant="secondary" onClick={() => { setAction("revalue"); setForm({ revaluation_date: new Date().toISOString().slice(0, 10), new_gross_value: asset.gross_value, financial_year: currentFY(), notes: "" }); }}>Revalue</Btn>
          </div>
        )}

        {/* Action Sub-form */}
        {action === "dispose" && (
          <div ref={disposeFormRef}>
            <Card className="border-red-200 bg-red-50 dark:border-red-800/50 dark:bg-red-950/20">
              <p className="text-red-700 dark:text-red-400 text-sm font-medium mb-3">Disposal — Companies Act gain/loss + IT block reduction</p>
              <div className="grid grid-cols-2 gap-3">
                <Input label="Disposal Date" type="date" value={form.disposal_date} onChange={e => setForm(f => ({ ...f, disposal_date: e.target.value }))} />
                <Input label="Sale Consideration (₹)" type="text" inputMode="decimal" value={form.sale_consideration} onChange={e => setForm(f => ({ ...f, sale_consideration: e.target.value }))} />
                <Input label="Financial Year" value={form.financial_year} onChange={e => setForm(f => ({ ...f, financial_year: e.target.value }))} placeholder="2024-25" />
                <Input label="Notes" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
              </div>
              <div className="flex gap-3 mt-3">
                <Btn variant="danger" onClick={submit}>Confirm Disposal</Btn>
                <Btn variant="ghost" onClick={() => setAction(null)}>Cancel</Btn>
              </div>
            </Card>
          </div>
        )}

        {action === "transfer" && (
          <div ref={transferFormRef}>
            <Card>
              <p className="text-yellow-400 text-sm font-medium mb-3">Transfer to another branch</p>
              <div className="grid grid-cols-2 gap-3">
                <Input label="Transfer Date" type="date" value={form.transfer_date} onChange={e => setForm(f => ({ ...f, transfer_date: e.target.value }))} />
                <Input label="To Branch ID" value={form.to_branch_id} onChange={e => setForm(f => ({ ...f, to_branch_id: e.target.value }))} />
                <Input label="To Location" value={form.to_location} onChange={e => setForm(f => ({ ...f, to_location: e.target.value }))} />
                <Input label="Notes" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
              </div>
              <div className="flex gap-3 mt-3">
                <Btn onClick={submit}>Confirm Transfer</Btn>
                <Btn variant="ghost" onClick={() => setAction(null)}>Cancel</Btn>
              </div>
            </Card>
          </div>
        )}

        {action === "revalue" && (
          <div ref={revalueFormRef}>
            <Card className="border-blue-200 bg-blue-50 dark:border-blue-800/50 dark:bg-blue-950/20">
              <p className="text-blue-700 dark:text-blue-400 text-sm font-medium mb-3">Revaluation — surplus → Revaluation Reserve; adjusted future CA depreciation</p>
              <div className="grid grid-cols-2 gap-3">
                <Input label="Revaluation Date" type="date" value={form.revaluation_date} onChange={e => setForm(f => ({ ...f, revaluation_date: e.target.value }))} />
                <Input label="New Gross Value (₹)" type="text" inputMode="decimal" value={form.new_gross_value} onChange={e => setForm(f => ({ ...f, new_gross_value: e.target.value }))} />
                <Input label="Financial Year" value={form.financial_year} onChange={e => setForm(f => ({ ...f, financial_year: e.target.value }))} />
                <Input label="Notes" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
              </div>
              <div className="flex gap-3 mt-3">
                <Btn onClick={submit}>Confirm Revaluation</Btn>
                <Btn variant="ghost" onClick={() => setAction(null)}>Cancel</Btn>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

// ════════════════════════════════════════════
// Categories Tab
// ════════════════════════════════════════════
function CategoriesTab({ categories, itBlocks, onRefresh }) {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", companies_act_useful_life_years: "", companies_act_method: "SLM", companies_act_residual_pct: "5", it_block_id: "" });

  const save = async () => {
    try {
      await api.post("/fixed-assets/categories", {
        ...form,
        companies_act_useful_life_years: parseFloat(form.companies_act_useful_life_years),
        companies_act_residual_pct: parseFloat(form.companies_act_residual_pct),
      });
      setShowForm(false);
      onRefresh();
    } catch (e) {
      alert(e.response?.data?.detail || "Error");
    }
  };

  // Enter-as-Tab across the New Category form; Ctrl+Enter/Ctrl+S saves, Esc
  // cancels. Secondary panel — no Ctrl+N here (owned by AssetRegisterTab).
  const categoryFormRef = useRef(null);
  useEnterNavigation(categoryFormRef, {
    enabled: showForm,
    autoFocus: true,
    onSave: () => save(),
    onCancel: () => setShowForm(false),
  });

  return (
    <div className="space-y-4">
      <SectionHeader
        title="Asset Categories (Companies Act)"
        action={<Btn onClick={() => setShowForm(true)}>+ Add Category</Btn>}
      />
      <Card>
        <table className="w-full text-sm">
          <thead><tr className="text-zinc-400 border-b border-zinc-800">
            <th className="text-left py-2 pr-3">Name</th>
            <th className="text-left py-2 pr-3">Method</th>
            <th className="text-right py-2 pr-3">Useful Life (yrs)</th>
            <th className="text-right py-2 pr-3">Residual %</th>
            <th className="text-left py-2">IT Block</th>
          </tr></thead>
          <tbody className="divide-y divide-zinc-800">
            {categories.map(c => {
              const block = itBlocks.find(b => b.id === c.it_block_id);
              return (
                <tr key={c.id} className="hover:bg-zinc-800/50">
                  <td className="py-2 pr-3 text-white font-medium">{c.name}</td>
                  <td className="py-2 pr-3"><span className="text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-yellow-400">{c.companies_act_method}</span></td>
                  <td className="py-2 pr-3 text-right text-zinc-300">{c.companies_act_useful_life_years}</td>
                  <td className="py-2 pr-3 text-right text-zinc-300">{c.companies_act_residual_pct}%</td>
                  <td className="py-2 text-zinc-400 text-xs">{block?.block_name ?? "—"}</td>
                </tr>
              );
            })}
            {categories.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-zinc-500">No categories</td></tr>}
          </tbody>
        </table>
      </Card>

      {showForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div ref={categoryFormRef} className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-md space-y-4">
            <h3 className="text-white font-semibold">New Asset Category</h3>
            <Input label="Name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <Select label="Depreciation Method" value={form.companies_act_method} onChange={e => setForm(f => ({ ...f, companies_act_method: e.target.value }))}>
              <option value="SLM">SLM (Straight Line)</option>
              <option value="WDV">WDV (Written Down Value)</option>
            </Select>
            <Input label="Useful Life (years)" type="text" inputMode="decimal" value={form.companies_act_useful_life_years} onChange={e => setForm(f => ({ ...f, companies_act_useful_life_years: e.target.value }))} />
            <Input label="Residual Value %" type="text" inputMode="decimal" value={form.companies_act_residual_pct} onChange={e => setForm(f => ({ ...f, companies_act_residual_pct: e.target.value }))} />
            <Select label="IT Block (Income Tax Act)" value={form.it_block_id} onChange={e => setForm(f => ({ ...f, it_block_id: e.target.value }))}>
              <option value="">None</option>
              {itBlocks.map(b => <option key={b.id} value={b.id}>{b.block_name} ({b.it_depreciation_rate}%)</option>)}
            </Select>
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

// ════════════════════════════════════════════
// IT Blocks Tab
// ════════════════════════════════════════════
function ITBlocksTab({ itBlocks, onRefresh }) {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ block_name: "", asset_type: "tangible", it_depreciation_rate: "", financial_year: "2024-25", effective_from: "" });

  const save = async () => {
    try {
      await api.post("/fixed-assets/it-blocks", { ...form, it_depreciation_rate: parseFloat(form.it_depreciation_rate) });
      setShowForm(false);
      onRefresh();
    } catch (e) {
      alert(e.response?.data?.detail || "Error");
    }
  };

  // Enter-as-Tab across the New IT Block form; Ctrl+Enter/Ctrl+S saves, Esc
  // cancels. Secondary panel — no Ctrl+N here (owned by AssetRegisterTab).
  const itBlockFormRef = useRef(null);
  useEnterNavigation(itBlockFormRef, {
    enabled: showForm,
    autoFocus: true,
    onSave: () => save(),
    onCancel: () => setShowForm(false),
  });

  return (
    <div className="space-y-4">
      <SectionHeader
        title="IT Blocks — Income Tax Act Sec 32"
        action={<Btn onClick={() => setShowForm(true)}>+ Add Block</Btn>}
      />
      <Card>
        <p className="text-xs text-zinc-500 mb-3">Block-of-assets method: depreciation runs on the pool's WDV, not per asset. Half-rate applies when put to use &lt; 180 days in the year of addition.</p>
        <table className="w-full text-sm">
          <thead><tr className="text-zinc-400 border-b border-zinc-800">
            <th className="text-left py-2 pr-3">Block Name</th>
            <th className="text-left py-2 pr-3">Type</th>
            <th className="text-right py-2 pr-3">IT Rate</th>
            <th className="text-left py-2 pr-3">FY</th>
            <th className="text-left py-2">Effective From</th>
          </tr></thead>
          <tbody className="divide-y divide-zinc-800">
            {itBlocks.map(b => (
              <tr key={b.id} className="hover:bg-zinc-800/50">
                <td className="py-2 pr-3 text-white font-medium">{b.block_name}</td>
                <td className="py-2 pr-3 text-zinc-400 capitalize">{b.asset_type}</td>
                <td className="py-2 pr-3 text-right text-yellow-400 font-semibold">{b.it_depreciation_rate}%</td>
                <td className="py-2 pr-3 text-zinc-400">{b.financial_year}</td>
                <td className="py-2 text-zinc-400">{b.effective_from}</td>
              </tr>
            ))}
            {itBlocks.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-zinc-500">No IT blocks defined</td></tr>}
          </tbody>
        </table>
      </Card>

      {showForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div ref={itBlockFormRef} className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-md space-y-4">
            <h3 className="text-white font-semibold">New IT Block</h3>
            <Input label="Block Name" value={form.block_name} onChange={e => setForm(f => ({ ...f, block_name: e.target.value }))} placeholder="e.g. Plant & Machinery (15%)" />
            <Select label="Asset Type" value={form.asset_type} onChange={e => setForm(f => ({ ...f, asset_type: e.target.value }))}>
              <option value="tangible">Tangible</option>
              <option value="intangible">Intangible</option>
            </Select>
            <Input label="IT Depreciation Rate (%)" type="text" inputMode="decimal" value={form.it_depreciation_rate} onChange={e => setForm(f => ({ ...f, it_depreciation_rate: e.target.value }))} />
            <Input label="Financial Year" value={form.financial_year} onChange={e => setForm(f => ({ ...f, financial_year: e.target.value }))} placeholder="2024-25" />
            <Input label="Effective From" type="date" value={form.effective_from} onChange={e => setForm(f => ({ ...f, effective_from: e.target.value }))} />
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

// ════════════════════════════════════════════
// Depreciation Run Tab
// ════════════════════════════════════════════
function DepreciationTab() {
  const [form, setForm] = useState({ financial_year: "2024-25", basis: "companies_act", preview: true });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/fixed-assets/depreciation/run", form);
      setResult(data);
    } catch (e) {
      alert(e.response?.data?.detail || "Error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <SectionHeader title="Depreciation Run" />
      <Card>
        <div className="grid grid-cols-3 gap-4">
          <Input label="Financial Year" value={form.financial_year} onChange={e => setForm(f => ({ ...f, financial_year: e.target.value }))} placeholder="2024-25" />
          <Select label="Basis" value={form.basis} onChange={e => setForm(f => ({ ...f, basis: e.target.value }))}>
            <option value="companies_act">Companies Act (Schedule II)</option>
            <option value="income_tax">Income Tax Act (Sec 32 Block)</option>
          </Select>
          <div className="flex items-end gap-3">
            <label className="flex items-center gap-2 text-sm text-zinc-400 pb-2">
              <input type="checkbox" checked={form.preview} onChange={e => setForm(f => ({ ...f, preview: e.target.checked }))} className="rounded" />
              Preview only (don't post)
            </label>
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <Btn onClick={run} disabled={loading}>
            {loading ? "Running..." : form.preview ? "Preview Depreciation" : "Run & Post Depreciation"}
          </Btn>
          {!form.preview && <p className="text-xs text-amber-400">This will post depreciation permanently. Use Preview first.</p>}
        </div>
      </Card>

      {result && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-white font-semibold">{result.financial_year} · {result.basis === "companies_act" ? "Companies Act" : "Income Tax"} Depreciation</p>
              {result.preview && <span className="text-xs bg-amber-900 text-amber-300 px-2 py-0.5 rounded-full">PREVIEW — not posted</span>}
            </div>
            <p className="text-xl font-bold text-yellow-400">{fmt(result.total_depreciation)}</p>
          </div>

          <table className="w-full text-sm">
            <thead><tr className="text-zinc-400 border-b border-zinc-800">
              {result.basis === "companies_act" ? (
                <>
                  <th className="text-left py-2 pr-3">Code</th>
                  <th className="text-left py-2 pr-3">Description</th>
                  <th className="text-left py-2 pr-3">Method</th>
                  <th className="text-right py-2 pr-3">Opening WDV</th>
                  <th className="text-right py-2 pr-3">Days Held</th>
                  <th className="text-right py-2 pr-3">Depreciation</th>
                  <th className="text-right py-2">Closing WDV</th>
                </>
              ) : (
                <>
                  <th className="text-left py-2 pr-3">Block</th>
                  <th className="text-right py-2 pr-3">Opening WDV</th>
                  <th className="text-right py-2 pr-3">Additions</th>
                  <th className="text-right py-2 pr-3">Disposals</th>
                  <th className="text-right py-2 pr-3">Rate</th>
                  <th className="text-right py-2 pr-3">Depreciation</th>
                  <th className="text-right py-2">Closing WDV</th>
                </>
              )}
            </tr></thead>
            <tbody className="divide-y divide-zinc-800">
              {result.results.map((row, i) => (
                result.basis === "companies_act" ? (
                  <tr key={i} className={row.is_fully_depreciated ? "opacity-50" : ""}>
                    <td className="py-2 pr-3 text-yellow-400 font-mono">{row.asset_code}</td>
                    <td className="py-2 pr-3 text-white">{row.asset_description}</td>
                    <td className="py-2 pr-3 text-zinc-400">{row.method}</td>
                    <td className="py-2 pr-3 text-right">{fmt(row.opening_wdv)}</td>
                    <td className="py-2 pr-3 text-right text-zinc-400">{row.days_held}/{row.total_fy_days}</td>
                    <td className="py-2 pr-3 text-right text-amber-400 font-semibold">{fmt(row.depreciation)}</td>
                    <td className="py-2 text-right text-emerald-400">{fmt(row.closing_wdv)}</td>
                  </tr>
                ) : (
                  <tr key={i} className={row.block_extinguished ? "bg-red-50 dark:bg-red-950/20 text-red-700 dark:text-red-300" : ""}>
                    <td className="py-2 pr-3 text-white font-medium">{row.block_name}</td>
                    <td className="py-2 pr-3 text-right">{fmt(row.opening_wdv)}</td>
                    <td className="py-2 pr-3 text-right text-emerald-400">{fmt(row.additions + (row.half_rate_additions || 0))}</td>
                    <td className="py-2 pr-3 text-right text-red-400">{fmt(row.disposals)}</td>
                    <td className="py-2 pr-3 text-right text-yellow-400">{row.it_rate}%</td>
                    <td className="py-2 pr-3 text-right text-amber-400 font-semibold">{fmt(row.depreciation)}</td>
                    <td className="py-2 text-right text-emerald-400">
                      {fmt(row.closing_wdv)}
                      {row.block_extinguished && <span className="ml-2 text-xs text-red-400">STCG {fmt(row.stcg)}</span>}
                    </td>
                  </tr>
                )
              ))}
              {result.results.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-zinc-500">No assets to depreciate</td></tr>}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════
// Disposals Tab
// ════════════════════════════════════════════
function DisposalsTab() {
  const [txns, setTxns] = useState([]);
  useEffect(() => {
    api.get("/fixed-assets/transactions", { params: { txn_type: "disposal" } })
      .then(r => setTxns(r.data))
      .catch(() => {});
  }, []);

  return (
    <div className="space-y-4">
      <SectionHeader title="Disposal History" />
      <Card>
        <table className="w-full text-sm">
          <thead><tr className="text-zinc-400 border-b border-zinc-800">
            <th className="text-left py-2 pr-3">Asset</th>
            <th className="text-left py-2 pr-3">Date</th>
            <th className="text-right py-2 pr-3">CA WDV</th>
            <th className="text-right py-2 pr-3">Sale Value</th>
            <th className="text-right py-2 pr-3">CA Gain/Loss</th>
            <th className="text-left py-2">Type</th>
          </tr></thead>
          <tbody className="divide-y divide-zinc-800">
            {txns.map((t, i) => (
              <tr key={i}>
                <td className="py-2 pr-3 text-zinc-300">{t.asset_code}</td>
                <td className="py-2 pr-3 text-zinc-400">{t.date}</td>
                <td className="py-2 pr-3 text-right">{fmt(t.ca_wdv_at_disposal)}</td>
                <td className="py-2 pr-3 text-right text-white">{fmt(t.amount)}</td>
                <td className={`py-2 pr-3 text-right font-semibold ${t.ca_gain_loss >= 0 ? "text-emerald-400" : "text-red-400"}`}>{fmt(t.ca_gain_loss)}</td>
                <td className="py-2"><span className={`text-xs px-2 py-0.5 rounded-full ${t.ca_gain_loss_type === "GAIN" ? "bg-emerald-900 text-emerald-300" : t.ca_gain_loss_type === "LOSS" ? "bg-red-900 text-red-300" : "bg-zinc-700 text-zinc-300"}`}>{t.ca_gain_loss_type}</span></td>
              </tr>
            ))}
            {txns.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-zinc-500">No disposals recorded</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════
// Depreciation Schedule Report Tab
// ════════════════════════════════════════════
function ScheduleTab({ categories }) {
  const [params, setParams] = useState({ basis: "companies_act", financial_year: "2024-25", category_id: "" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get("/fixed-assets/depreciation-schedule", { params: { ...params, category_id: params.category_id || undefined } });
      setData(d);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <SectionHeader title="Depreciation Schedule Report" />
      <Card>
        <div className="grid grid-cols-4 gap-3 items-end">
          <Select label="Basis" value={params.basis} onChange={e => setParams(p => ({ ...p, basis: e.target.value }))}>
            <option value="companies_act">Companies Act</option>
            <option value="income_tax">Income Tax</option>
          </Select>
          <Input label="Financial Year" value={params.financial_year} onChange={e => setParams(p => ({ ...p, financial_year: e.target.value }))} />
          <Select label="Category" value={params.category_id} onChange={e => setParams(p => ({ ...p, category_id: e.target.value }))}>
            <option value="">All Categories</option>
            {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Btn onClick={load} disabled={loading}>Load Report</Btn>
        </div>
      </Card>

      {data && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <p className="text-zinc-400 text-sm">Total depreciation for {data.financial_year} ({data.basis})</p>
            <p className="text-2xl font-bold text-yellow-400">{fmt(data.total_depreciation)}</p>
          </div>
          <table className="w-full text-sm">
            <thead><tr className="text-zinc-400 border-b border-zinc-800">
              <th className="text-left py-2 pr-3">Asset</th>
              <th className="text-left py-2 pr-3">Category</th>
              <th className="text-right py-2 pr-3">Opening WDV</th>
              <th className="text-right py-2 pr-3">Depreciation</th>
              <th className="text-right py-2">Closing WDV</th>
            </tr></thead>
            <tbody className="divide-y divide-zinc-800">
              {data.rows.map((r, i) => (
                <tr key={i}>
                  <td className="py-2 pr-3 text-white">{r.asset_code || r.block_name} <span className="text-zinc-500 text-xs">{r.asset_description}</span></td>
                  <td className="py-2 pr-3 text-zinc-400">{r.category_name || "—"}</td>
                  <td className="py-2 pr-3 text-right">{fmt(r.opening_wdv)}</td>
                  <td className="py-2 pr-3 text-right text-amber-400">{fmt(r.depreciation)}</td>
                  <td className="py-2 text-right text-emerald-400">{fmt(r.closing_wdv)}</td>
                </tr>
              ))}
              {data.rows.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-zinc-500">No depreciation runs found for selected period</td></tr>}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════
// Main Page
// ════════════════════════════════════════════
export default function FixedAssets() {
  const [activeTab, setActiveTab] = useState(0);
  const [categories, setCategories] = useState([]);
  const [itBlocks, setItBlocks] = useState([]);
  const [catVersion, setCatVersion] = useState(0);

  const loadMeta = useCallback(async () => {
    try {
      const [cats, blocks] = await Promise.all([
        api.get("/fixed-assets/categories"),
        api.get("/fixed-assets/it-blocks"),
      ]);
      setCategories(cats.data);
      setItBlocks(blocks.data);
    } catch {/* silent */}
  }, []);

  useEffect(() => { loadMeta(); }, [loadMeta, catVersion]);

  const refreshMeta = () => setCatVersion(v => v + 1);

  const tabs = [
    <AssetRegisterTab key="reg" categories={categories} />,
    <CategoriesTab key="cat" categories={categories} itBlocks={itBlocks} onRefresh={refreshMeta} />,
    <ITBlocksTab key="it" itBlocks={itBlocks} onRefresh={refreshMeta} />,
    <DepreciationTab key="depr" />,
    <DisposalsTab key="disp" />,
    <ScheduleTab key="sched" categories={categories} />,
  ];

  return (
    <div className="min-h-screen bg-zinc-950 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white">Fixed Assets</h1>
          <p className="text-zinc-400 text-sm mt-1">
            Dual depreciation — Companies Act (Schedule II SLM/WDV) and Income Tax Act (Sec 32 block-of-assets)
          </p>
        </div>

        {/* Tab Nav */}
        <div className="flex gap-1 mb-6 bg-zinc-900 border border-zinc-800 rounded-xl p-1 w-fit">
          {TABS.map((tab, i) => (
            <button
              key={tab}
              onClick={() => setActiveTab(i)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === i
                  ? "bg-yellow-400 text-zinc-950"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {tabs[activeTab]}
      </div>
    </div>
  );
}
