import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  Factory, ClipboardList, Package, FlaskConical, BarChart3,
  Plus, RefreshCw, ChevronRight, ChevronDown, PlayCircle,
  CheckCircle2, XCircle, AlertTriangle, Layers, Cog,
  TrendingUp, BookOpen, Trash2, Edit2, Zap, GitBranch,
  ArrowRight, Boxes, Send, Lock,
} from "lucide-react";

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const num = (n, d = 4) => Number(n || 0).toFixed(d).replace(/\.?0+$/, "") || "0";

const STATUS_COLORS = {
  DRAFT:       "bg-zinc-800 text-zinc-400 border-zinc-700",
  PENDING:     "bg-zinc-800 text-zinc-300 border-zinc-700",
  RELEASED:    "bg-blue-950 text-blue-300 border-blue-800",
  IN_PROGRESS: "bg-indigo-950 text-indigo-300 border-indigo-800",
  QC_PENDING:  "bg-yellow-950 text-yellow-300 border-yellow-800",
  COMPLETED:   "bg-green-950 text-green-300 border-green-800",
  CLOSED:      "bg-purple-950 text-purple-300 border-purple-800",
  CANCELLED:   "bg-red-950 text-red-300 border-red-800",
  ACTIVE:      "bg-green-950 text-green-300 border-green-800",
  ARCHIVED:    "bg-zinc-800 text-zinc-500 border-zinc-700",
  PASSED:      "bg-green-950 text-green-300 border-green-800",
  FAILED:      "bg-red-950 text-red-300 border-red-800",
  PARTIAL:     "bg-yellow-950 text-yellow-300 border-yellow-800",
  NORMAL:      "bg-zinc-800 text-zinc-400 border-zinc-700",
  ABNORMAL:    "bg-red-950 text-red-400 border-red-800",
};

function StatusBadge({ status }) {
  return (
    <span className={`text-[10px] font-mono font-bold uppercase border px-2 py-0.5 ${STATUS_COLORS[status] || "bg-zinc-800 text-zinc-400 border-zinc-700"}`}>
      {status?.replace(/_/g, " ")}
    </span>
  );
}

function Card({ children, className = "" }) {
  return <div className={`bg-zinc-950 border border-zinc-800 ${className}`}>{children}</div>;
}

function SectionHeader({ title, action }) {
  return (
    <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-3">
      <span className="font-mono text-[10px] uppercase tracking-widest text-zinc-400">{title}</span>
      {action}
    </div>
  );
}

function FieldLabel({ children }) {
  return <label className="block font-mono text-[10px] uppercase tracking-wider text-zinc-500 mb-1">{children}</label>;
}

function Input({ className = "", ...props }) {
  return (
    <input
      className={`w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400 ${className}`}
      {...props}
    />
  );
}

function Select({ children, className = "", ...props }) {
  return (
    <select
      className={`w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400 ${className}`}
      {...props}
    >
      {children}
    </select>
  );
}

function Btn({ onClick, children, variant = "primary", className = "", ...props }) {
  const base = "text-xs font-mono font-bold uppercase px-3 py-2 transition-colors flex items-center gap-1.5";
  const styles = {
    primary: "bg-yellow-400 hover:bg-yellow-500 text-black",
    secondary: "border border-zinc-700 text-zinc-400 hover:text-zinc-200",
    danger: "border border-red-800 text-red-400 hover:bg-red-950",
    ghost: "text-zinc-500 hover:text-zinc-200",
  };
  return <button onClick={onClick} className={`${base} ${styles[variant]} ${className}`} {...props}>{children}</button>;
}

// ─── Dashboard ─────────────────────────────────────────────────────────────

function MfgDashboard() {
  const [data, setData] = useState(null);
  const [mrp, setMrp] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const [dash, mrpRes] = await Promise.all([
        api.get("/manufacturing/dashboard"),
        api.get("/manufacturing/mrp"),
      ]);
      setData(dash.data);
      setMrp(mrpRes.data || []);
    } catch { toast.error("Failed to load manufacturing dashboard"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  if (loading) return <div className="flex justify-center py-12"><RefreshCw className="w-6 h-6 text-yellow-400 animate-spin" /></div>;

  const d = data || {};
  const kpis = [
    { label: "Active WOs", value: d.active_work_orders ?? 0, icon: ClipboardList, color: "text-blue-400" },
    { label: "Completed", value: d.completed_work_orders ?? 0, icon: CheckCircle2, color: "text-green-400" },
    { label: "QC Pending", value: d.qc_pending_count ?? 0, icon: FlaskConical, color: "text-yellow-400" },
    { label: "Prod Journals", value: d.production_journals ?? 0, icon: BookOpen, color: "text-indigo-400" },
    { label: "QC Pass Rate", value: `${d.qc_pass_rate ?? 100}%`, icon: TrendingUp, color: "text-emerald-400" },
    { label: "Abnormal Waste", value: d.abnormal_wastage_entries ?? 0, icon: AlertTriangle, color: "text-red-400" },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        {kpis.map((k) => {
          const Icon = k.icon;
          return (
            <Card key={k.label} className="p-4 relative group hover:border-zinc-700 transition-colors">
              <Icon className={`w-4 h-4 absolute top-3 right-3 ${k.color} opacity-60 group-hover:opacity-100 transition-opacity`} />
              <div className="font-mono font-black text-2xl text-zinc-50 mt-1">{k.value}</div>
              <div className="font-mono text-[10px] uppercase tracking-wider text-zinc-500 mt-1">{k.label}</div>
            </Card>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <SectionHeader title="Recent Active Work Orders" />
          <div className="divide-y divide-zinc-800/60">
            {!(d.recent_work_orders?.length) && <div className="p-8 text-center text-zinc-600 font-mono text-xs">No active work orders</div>}
            {(d.recent_work_orders || []).map((wo) => (
              <div key={wo.id} className="px-5 py-3 flex items-center justify-between hover:bg-zinc-900/40">
                <div>
                  <div className="text-sm font-semibold text-zinc-100">{wo.product_name}</div>
                  <div className="text-xs text-zinc-500 font-mono">{wo.wo_number} · Qty: {wo.quantity_planned}</div>
                </div>
                <StatusBadge status={wo.status} />
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <SectionHeader title="MRP — Material Shortages" />
          <div className="divide-y divide-zinc-800/60">
            {mrp.filter(m => m.shortage > 0).length === 0 && <div className="p-8 text-center text-zinc-600 font-mono text-xs">No shortages detected</div>}
            {mrp.filter(m => m.shortage > 0).slice(0, 8).map((m) => (
              <div key={m.product_id} className="px-5 py-3 flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold text-zinc-100">{m.product_name}</div>
                  <div className="text-xs text-zinc-500 font-mono">{m.sku} · On-hand: {num(m.quantity_on_hand, 2)} {m.unit}</div>
                </div>
                <div className="text-right">
                  <div className="text-red-400 font-mono text-xs font-bold">Short: {num(m.shortage, 2)}</div>
                  <div className="text-zinc-500 font-mono text-[10px]">Need: {num(m.quantity_required, 2)}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ─── BOM Tab ───────────────────────────────────────────────────────────────

function BOMTab() {
  const [boms, setBoms] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [explodeResult, setExplodeResult] = useState(null);
  const [editId, setEditId] = useState(null);

  const blankForm = () => ({
    finished_product_id: "", finished_product_name: "", sku: "",
    output_qty: 1, version: "1.0", status: "DRAFT",
    valuation_method: "WEIGHTED_AVG",
    components: [], co_products: [], by_products: [],
    routing_steps: [], notes: "",
    // legacy compat
    items: [],
  });
  const [form, setForm] = useState(blankForm());

  const load = async () => {
    try {
      const [bomRes, prodRes] = await Promise.all([
        api.get("/manufacturing/bom"),
        api.get("/products?limit=500"),
      ]);
      setBoms(bomRes.data || []);
      setProducts(prodRes.data?.items || prodRes.data || []);
    } catch { toast.error("Failed to load BOM data"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const handleProductSelect = (e) => {
    const prod = products.find(p => p.id === e.target.value);
    setForm(f => ({ ...f, finished_product_id: e.target.value, finished_product_name: prod?.name || "", sku: prod?.sku || "" }));
  };

  // ── Component rows ─────────────────────────────────────────────────────────
  const addComp = () => setForm(f => ({
    ...f,
    components: [...f.components, { component_item_id: "", component_item_name: "", qty_per: 1, uom: "pcs", scrap_pct: 0, is_optional: false }],
    items: [...(f.items || []), { product_id: "", product_name: "", quantity: 1, unit: "pcs", scrap_pct: 0 }],
  }));
  const removeComp = (i) => setForm(f => ({ ...f, components: f.components.filter((_, idx) => idx !== i), items: (f.items || []).filter((_, idx) => idx !== i) }));
  const updateComp = (i, field, val) => setForm(f => {
    const comps = [...f.components];
    const legacyItems = [...(f.items || [])];
    comps[i] = { ...comps[i], [field]: val };
    if (field === "component_item_id") {
      const prod = products.find(p => p.id === val);
      comps[i].component_item_name = prod?.name || "";
      if (legacyItems[i]) { legacyItems[i].product_id = val; legacyItems[i].product_name = prod?.name || ""; }
    }
    if (field === "qty_per" && legacyItems[i]) legacyItems[i].quantity = val;
    if (field === "uom" && legacyItems[i]) legacyItems[i].unit = val;
    if (field === "scrap_pct" && legacyItems[i]) legacyItems[i].scrap_pct = val;
    return { ...f, components: comps, items: legacyItems };
  });

  // ── Co-product rows ───────────────────────────────────────────────────────
  const addCoProd = () => setForm(f => ({ ...f, co_products: [...f.co_products, { item_id: "", item_name: "", qty_per: 1, uom: "pcs", cost_allocation_pct: 0 }] }));
  const removeCoProd = (i) => setForm(f => ({ ...f, co_products: f.co_products.filter((_, idx) => idx !== i) }));
  const updateCoProd = (i, field, val) => setForm(f => {
    const arr = [...f.co_products];
    arr[i] = { ...arr[i], [field]: val };
    if (field === "item_id") { const p = products.find(p => p.id === val); arr[i].item_name = p?.name || ""; }
    return { ...f, co_products: arr };
  });

  // ── By-product rows ───────────────────────────────────────────────────────
  const addByProd = () => setForm(f => ({ ...f, by_products: [...f.by_products, { item_id: "", item_name: "", qty_per: 0, uom: "pcs", realizable_value_per: 0 }] }));
  const removeByProd = (i) => setForm(f => ({ ...f, by_products: f.by_products.filter((_, idx) => idx !== i) }));
  const updateByProd = (i, field, val) => setForm(f => {
    const arr = [...f.by_products];
    arr[i] = { ...arr[i], [field]: val };
    if (field === "item_id") { const p = products.find(p => p.id === val); arr[i].item_name = p?.name || ""; }
    return { ...f, by_products: arr };
  });

  const save = async () => {
    try {
      if (editId) {
        await api.put(`/manufacturing/bom/${editId}`, form);
        toast.success("BOM updated");
      } else {
        await api.post("/manufacturing/bom", form);
        toast.success("BOM created");
      }
      setShowForm(false); setEditId(null); setForm(blankForm()); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const explode = async (bomId, qty = 1) => {
    try {
      const res = await api.get(`/manufacturing/bom/${bomId}/explode?qty=${qty}`);
      setExplodeResult({ bomId, ...res.data });
    } catch (e) { toast.error(e.response?.data?.detail || "Explosion failed"); }
  };

  const startEdit = (bom) => {
    setForm({
      ...blankForm(),
      ...bom,
      components: bom.components?.length ? bom.components : (bom.items || []).map(it => ({
        component_item_id: it.product_id || it.component_item_id || "",
        component_item_name: it.product_name || it.component_item_name || "",
        qty_per: it.quantity || it.qty_per || 1,
        uom: it.unit || it.uom || "pcs",
        scrap_pct: it.scrap_pct || 0,
        is_optional: it.is_optional || false,
      })),
    });
    setEditId(bom.id);
    setShowForm(true);
  };

  const deleteBom = async (id) => {
    if (!window.confirm("Delete this BOM?")) return;
    try { await api.delete(`/manufacturing/bom/${id}`); toast.success("BOM deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <span className="font-mono text-xs text-zinc-500 uppercase tracking-wider">{boms.length} Bills of Materials</span>
        <Btn onClick={() => { setShowForm(!showForm); setEditId(null); setForm(blankForm()); }}><Plus className="w-3.5 h-3.5" /> New BOM</Btn>
      </div>

      {showForm && (
        <Card className="p-5 space-y-5">
          <div className="font-mono text-xs uppercase tracking-widest text-yellow-400 border-b border-zinc-800 pb-2">
            {editId ? "Edit BOM" : "New Bill of Materials"}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <div className="sm:col-span-2">
              <FieldLabel>Finished Good</FieldLabel>
              <Select value={form.finished_product_id} onChange={handleProductSelect}>
                <option value="">Select product…</option>
                {products.map(p => <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>)}
              </Select>
            </div>
            <div>
              <FieldLabel>Output Qty</FieldLabel>
              <Input type="number" value={form.output_qty} min="0.001" step="any"
                onChange={e => setForm(f => ({ ...f, output_qty: parseFloat(e.target.value) }))} />
            </div>
            <div>
              <FieldLabel>Version</FieldLabel>
              <Input value={form.version} onChange={e => setForm(f => ({ ...f, version: e.target.value }))} />
            </div>
            <div>
              <FieldLabel>Status</FieldLabel>
              <Select value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
                {["DRAFT","ACTIVE","ARCHIVED"].map(s => <option key={s}>{s}</option>)}
              </Select>
            </div>
            <div>
              <FieldLabel>Valuation</FieldLabel>
              <Select value={form.valuation_method} onChange={e => setForm(f => ({ ...f, valuation_method: e.target.value }))}>
                <option value="WEIGHTED_AVG">Weighted Avg</option>
                <option value="FIFO">FIFO</option>
              </Select>
            </div>
          </div>

          {/* Components */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <FieldLabel>Components / Raw Materials</FieldLabel>
              <Btn variant="ghost" onClick={addComp}><Plus className="w-3 h-3" /> Add</Btn>
            </div>
            <div className="space-y-1.5">
              {(form.components || []).map((c, i) => (
                <div key={i} className="grid grid-cols-12 gap-1.5 items-center">
                  <div className="col-span-4">
                    <Select value={c.component_item_id} onChange={e => updateComp(i, "component_item_id", e.target.value)}>
                      <option value="">Select component…</option>
                      {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </Select>
                  </div>
                  <div className="col-span-2"><Input type="number" value={c.qty_per} placeholder="Qty/unit" step="any" min="0" onChange={e => updateComp(i, "qty_per", parseFloat(e.target.value) || 0)} /></div>
                  <div className="col-span-2"><Input value={c.uom} placeholder="UOM" onChange={e => updateComp(i, "uom", e.target.value)} /></div>
                  <div className="col-span-2"><Input type="number" value={c.scrap_pct} placeholder="Scrap %" step="any" min="0" max="100" onChange={e => updateComp(i, "scrap_pct", parseFloat(e.target.value) || 0)} /></div>
                  <div className="col-span-1 flex items-center gap-1">
                    <input type="checkbox" checked={c.is_optional} onChange={e => updateComp(i, "is_optional", e.target.checked)} className="accent-yellow-400" title="Optional" />
                  </div>
                  <div className="col-span-1 flex justify-end">
                    <button onClick={() => removeComp(i)} className="text-zinc-600 hover:text-red-400"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                </div>
              ))}
              {form.components?.length > 0 && (
                <div className="grid grid-cols-12 gap-1.5 text-[10px] text-zinc-600 font-mono px-0.5">
                  <div className="col-span-4">Component</div>
                  <div className="col-span-2">Qty/unit</div>
                  <div className="col-span-2">UOM</div>
                  <div className="col-span-2">Scrap %</div>
                  <div className="col-span-1">Opt?</div>
                </div>
              )}
            </div>
          </div>

          {/* Co-Products */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <FieldLabel>Co-Products (joint output)</FieldLabel>
              <Btn variant="ghost" onClick={addCoProd}><Plus className="w-3 h-3" /> Add</Btn>
            </div>
            {(form.co_products || []).map((cp, i) => (
              <div key={i} className="grid grid-cols-10 gap-1.5 items-center mb-1.5">
                <div className="col-span-4">
                  <Select value={cp.item_id} onChange={e => updateCoProd(i, "item_id", e.target.value)}>
                    <option value="">Select co-product…</option>
                    {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </Select>
                </div>
                <div className="col-span-2"><Input type="number" value={cp.qty_per} placeholder="Qty/unit" step="any" min="0" onChange={e => updateCoProd(i, "qty_per", parseFloat(e.target.value) || 0)} /></div>
                <div className="col-span-2"><Input value={cp.uom} placeholder="UOM" onChange={e => updateCoProd(i, "uom", e.target.value)} /></div>
                <div className="col-span-1"><Input type="number" value={cp.cost_allocation_pct} placeholder="Cost%" step="any" min="0" max="100" onChange={e => updateCoProd(i, "cost_allocation_pct", parseFloat(e.target.value) || 0)} /></div>
                <div className="col-span-1 flex justify-end">
                  <button onClick={() => removeCoProd(i)} className="text-zinc-600 hover:text-red-400"><Trash2 className="w-3.5 h-3.5" /></button>
                </div>
              </div>
            ))}
          </div>

          {/* By-Products */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <FieldLabel>By-Products (credited at realizable value)</FieldLabel>
              <Btn variant="ghost" onClick={addByProd}><Plus className="w-3 h-3" /> Add</Btn>
            </div>
            {(form.by_products || []).map((bp, i) => (
              <div key={i} className="grid grid-cols-10 gap-1.5 items-center mb-1.5">
                <div className="col-span-4">
                  <Select value={bp.item_id} onChange={e => updateByProd(i, "item_id", e.target.value)}>
                    <option value="">Select by-product…</option>
                    {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </Select>
                </div>
                <div className="col-span-2"><Input type="number" value={bp.qty_per} placeholder="Qty/unit" step="any" min="0" onChange={e => updateByProd(i, "qty_per", parseFloat(e.target.value) || 0)} /></div>
                <div className="col-span-2"><Input value={bp.uom} placeholder="UOM" onChange={e => updateByProd(i, "uom", e.target.value)} /></div>
                <div className="col-span-1"><Input type="number" value={bp.realizable_value_per} placeholder="₹/unit" step="any" min="0" onChange={e => updateByProd(i, "realizable_value_per", parseFloat(e.target.value) || 0)} /></div>
                <div className="col-span-1 flex justify-end">
                  <button onClick={() => removeByProd(i)} className="text-zinc-600 hover:text-red-400"><Trash2 className="w-3.5 h-3.5" /></button>
                </div>
              </div>
            ))}
          </div>

          <textarea value={form.notes || ""} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
            placeholder="Notes…" rows={2}
            className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />

          <div className="flex gap-2 pt-1">
            <Btn onClick={save}>{editId ? "Update BOM" : "Create BOM"}</Btn>
            <Btn variant="secondary" onClick={() => { setShowForm(false); setEditId(null); }}>Cancel</Btn>
          </div>
        </Card>
      )}

      {/* BOM Explosion Result */}
      {explodeResult && (
        <Card className="p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="font-mono text-xs uppercase tracking-widest text-yellow-400">
              BOM Explosion — {explodeResult.finished_product} × {explodeResult.target_qty}
            </div>
            <button onClick={() => setExplodeResult(null)} className="text-zinc-500 hover:text-zinc-300"><XCircle className="w-4 h-4" /></button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800">
                  <th className="text-left py-1 pr-4">Material</th>
                  <th className="text-right pr-4">Required Qty</th>
                  <th className="text-right pr-4">On Hand</th>
                  <th className="text-right pr-4 text-red-400">Shortage</th>
                  <th className="text-right pr-4">Unit Cost</th>
                  <th className="text-right">Total Cost</th>
                </tr>
              </thead>
              <tbody>
                {(explodeResult.raw_requirements || []).map((r, i) => (
                  <tr key={i} className={`border-b border-zinc-900 ${r.shortage > 0 ? "text-red-300" : "text-zinc-300"}`}>
                    <td className="py-1 pr-4">
                      {"  ".repeat(r.depth || 0)}{r.depth > 0 && "└ "}{r.item_name}
                      {r.scrap_pct > 0 && <span className="ml-1 text-zinc-500">+{r.scrap_pct}% scrap</span>}
                    </td>
                    <td className="text-right pr-4">{num(r.required_qty)} {r.uom}</td>
                    <td className="text-right pr-4 text-zinc-400">{num(r.on_hand)}</td>
                    <td className={`text-right pr-4 font-bold ${r.shortage > 0 ? "text-red-400" : "text-green-500"}`}>{r.shortage > 0 ? num(r.shortage) : "OK"}</td>
                    <td className="text-right pr-4 text-zinc-500">₹{inr(r.unit_cost)}</td>
                    <td className="text-right text-zinc-400">₹{inr(r.total_cost)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="text-zinc-300 font-bold border-t border-zinc-700">
                  <td colSpan={5} className="py-1 text-right pr-4 text-zinc-500">Total Material Cost</td>
                  <td className="text-right">₹{inr(explodeResult.total_material_cost)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </Card>
      )}

      {/* BOM List */}
      <Card>
        <div className="divide-y divide-zinc-800/60">
          {loading && <div className="p-8 flex justify-center"><RefreshCw className="w-5 h-5 animate-spin text-yellow-400" /></div>}
          {!loading && boms.length === 0 && <div className="p-10 text-center text-zinc-600 font-mono text-xs">No BOMs created yet.</div>}
          {boms.map((bom) => (
            <div key={bom.id}>
              <div className="px-5 py-4 flex items-center justify-between hover:bg-zinc-900/40 cursor-pointer"
                onClick={() => setExpandedId(expandedId === bom.id ? null : bom.id)}>
                <div className="flex items-center gap-3">
                  {expandedId === bom.id ? <ChevronDown className="w-4 h-4 text-yellow-400" /> : <ChevronRight className="w-4 h-4 text-zinc-500" />}
                  <div>
                    <div className="text-sm font-semibold text-zinc-100">{bom.finished_product_name}</div>
                    <div className="text-xs text-zinc-500 font-mono">
                      {bom.sku} · v{bom.version} · {(bom.components?.length || bom.items?.length || 0)} components
                      {bom.co_products?.length > 0 && ` · ${bom.co_products.length} co-products`}
                      {bom.by_products?.length > 0 && ` · ${bom.by_products.length} by-products`}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-zinc-400">Est. ₹{inr(bom.estimated_cost)}</span>
                  <StatusBadge status={bom.status} />
                  <button onClick={e => { e.stopPropagation(); explode(bom.id); }}
                    className="text-zinc-600 hover:text-blue-400 p-1 transition-colors" title="Explode BOM">
                    <GitBranch className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={e => { e.stopPropagation(); startEdit(bom); }} className="text-zinc-600 hover:text-yellow-400 p-1"><Edit2 className="w-3.5 h-3.5" /></button>
                  <button onClick={e => { e.stopPropagation(); deleteBom(bom.id); }} className="text-zinc-600 hover:text-red-400 p-1"><Trash2 className="w-3.5 h-3.5" /></button>
                </div>
              </div>
              {expandedId === bom.id && (
                <div className="px-10 pb-5 grid grid-cols-1 lg:grid-cols-3 gap-4 text-xs">
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Components</div>
                    <table className="w-full"><thead><tr className="text-zinc-600"><th className="text-left">Material</th><th className="text-right">Qty</th><th className="text-right">Scrap%</th></tr></thead>
                      <tbody>{(bom.components?.length ? bom.components : bom.items || []).map((c, i) => (
                        <tr key={i} className="text-zinc-300">
                          <td>{c.component_item_name || c.product_name}</td>
                          <td className="text-right text-zinc-400">{c.qty_per || c.quantity} {c.uom || c.unit}</td>
                          <td className="text-right text-zinc-500">{c.scrap_pct || 0}%</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                  {bom.co_products?.length > 0 && (
                    <div>
                      <div className="font-mono text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Co-Products</div>
                      {bom.co_products.map((cp, i) => (
                        <div key={i} className="text-zinc-300">{cp.item_name} — {cp.qty_per} {cp.uom} ({cp.cost_allocation_pct}% cost)</div>
                      ))}
                    </div>
                  )}
                  {bom.by_products?.length > 0 && (
                    <div>
                      <div className="font-mono text-[10px] uppercase tracking-wider text-zinc-500 mb-2">By-Products</div>
                      {bom.by_products.map((bp, i) => (
                        <div key={i} className="text-zinc-300">{bp.item_name} — {bp.qty_per} {bp.uom} @ ₹{inr(bp.realizable_value_per)}/unit</div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ─── Work Orders Tab ───────────────────────────────────────────────────────

function WorkOrdersTab() {
  const [wos, setWos] = useState([]);
  const [boms, setBoms] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ bom_id: "", product_id: "", product_name: "", quantity_planned: 1, notes: "" });

  const load = async () => {
    try {
      const [woRes, bomRes, prodRes] = await Promise.all([
        api.get("/manufacturing/work-orders"),
        api.get("/manufacturing/bom"),
        api.get("/products?limit=500"),
      ]);
      setWos(woRes.data || []);
      setBoms(bomRes.data || []);
      setProducts(prodRes.data?.items || prodRes.data || []);
    } catch { toast.error("Failed to load work orders"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const handleBomSelect = (e) => {
    const bom = boms.find(b => b.id === e.target.value);
    setForm(f => ({ ...f, bom_id: e.target.value, product_id: bom?.finished_product_id || "", product_name: bom?.finished_product_name || "" }));
  };

  const createWO = async () => {
    try { await api.post("/manufacturing/work-orders", form); toast.success("Work Order created"); setShowForm(false); setForm({ bom_id: "", product_id: "", product_name: "", quantity_planned: 1, notes: "" }); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const action = async (id, act, label) => {
    try { await api.post(`/manufacturing/work-orders/${id}/${act}`); toast.success(`Work Order ${label}`); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Action failed"); }
  };

  const deleteWO = async (id, status) => {
    if (!["DRAFT", "PENDING", "CANCELLED"].includes(status)) { toast.error("Only DRAFT/CANCELLED WOs can be deleted"); return; }
    if (!window.confirm("Delete this Work Order?")) return;
    try { await api.delete(`/manufacturing/work-orders/${id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Delete failed"); }
  };

  const STATUS_ORDER = ["DRAFT", "PENDING", "RELEASED", "IN_PROGRESS", "QC_PENDING", "COMPLETED", "CLOSED", "CANCELLED"];
  const grouped = STATUS_ORDER.reduce((acc, s) => { acc[s] = wos.filter(w => w.status === s); return acc; }, {});

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <span className="font-mono text-xs text-zinc-500 uppercase tracking-wider">{wos.length} Work Orders</span>
        <Btn onClick={() => setShowForm(!showForm)}><Plus className="w-3.5 h-3.5" /> New Work Order</Btn>
      </div>

      {showForm && (
        <Card className="p-5 space-y-4">
          <div className="font-mono text-xs uppercase tracking-widest text-yellow-400 border-b border-zinc-800 pb-2">New Work Order</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <FieldLabel>Bill of Materials</FieldLabel>
              <Select value={form.bom_id} onChange={handleBomSelect}>
                <option value="">Select BOM…</option>
                {boms.map(b => <option key={b.id} value={b.id}>{b.finished_product_name} v{b.version}</option>)}
              </Select>
            </div>
            <div>
              <FieldLabel>Planned Quantity</FieldLabel>
              <Input type="number" value={form.quantity_planned} min="0.001" step="any"
                onChange={e => setForm(f => ({ ...f, quantity_planned: parseFloat(e.target.value) }))} />
            </div>
          </div>
          <textarea value={form.notes || ""} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="Notes…" rows={2}
            className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
          <div className="flex gap-2">
            <Btn onClick={createWO}>Create WO</Btn>
            <Btn variant="secondary" onClick={() => setShowForm(false)}>Cancel</Btn>
          </div>
        </Card>
      )}

      {/* Kanban-style status columns */}
      <div className="overflow-x-auto pb-2">
        <div className="flex gap-4 min-w-max">
          {["DRAFT","RELEASED","IN_PROGRESS","COMPLETED"].map(status => (
            <div key={status} className="w-64">
              <div className="flex items-center gap-2 mb-2">
                <StatusBadge status={status} />
                <span className="text-zinc-600 font-mono text-[10px]">{grouped[status]?.length || 0}</span>
              </div>
              <div className="space-y-2">
                {(grouped[status] || []).map(wo => (
                  <Card key={wo.id} className="p-3 hover:border-zinc-700 transition-colors">
                    <div className="text-xs font-semibold text-zinc-100 truncate">{wo.product_name}</div>
                    <div className="font-mono text-[10px] text-zinc-500 mt-0.5">{wo.wo_number} · {wo.quantity_planned} units</div>
                    <div className="flex gap-1 mt-2 flex-wrap">
                      {wo.status === "DRAFT" && (
                        <button onClick={() => action(wo.id, "release", "released")}
                          className="text-[9px] font-mono uppercase border border-blue-800 text-blue-400 px-1.5 py-0.5 hover:bg-blue-950 flex items-center gap-0.5">
                          <Lock className="w-2.5 h-2.5" /> Release
                        </button>
                      )}
                      {(wo.status === "RELEASED" || wo.status === "PENDING") && (
                        <button onClick={() => action(wo.id, "start", "started")}
                          className="text-[9px] font-mono uppercase border border-indigo-800 text-indigo-400 px-1.5 py-0.5 hover:bg-indigo-950 flex items-center gap-0.5">
                          <PlayCircle className="w-2.5 h-2.5" /> Start
                        </button>
                      )}
                      {wo.status === "IN_PROGRESS" && (
                        <button onClick={() => action(wo.id, "complete", "completed")}
                          className="text-[9px] font-mono uppercase border border-green-800 text-green-400 px-1.5 py-0.5 hover:bg-green-950 flex items-center gap-0.5">
                          <CheckCircle2 className="w-2.5 h-2.5" /> Complete
                        </button>
                      )}
                      {wo.status === "COMPLETED" && (
                        <button onClick={() => action(wo.id, "close", "closed")}
                          className="text-[9px] font-mono uppercase border border-purple-800 text-purple-400 px-1.5 py-0.5 hover:bg-purple-950 flex items-center gap-0.5">
                          <CheckCircle2 className="w-2.5 h-2.5" /> Close
                        </button>
                      )}
                      {["DRAFT","PENDING","CANCELLED"].includes(wo.status) && (
                        <button onClick={() => deleteWO(wo.id, wo.status)}
                          className="text-[9px] font-mono uppercase border border-zinc-700 text-zinc-500 px-1.5 py-0.5 hover:bg-zinc-900 flex items-center gap-0.5">
                          <Trash2 className="w-2.5 h-2.5" />
                        </button>
                      )}
                    </div>
                  </Card>
                ))}
                {!(grouped[status]?.length) && (
                  <div className="text-center py-6 text-zinc-700 font-mono text-[10px]">—</div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Production Journal Tab ────────────────────────────────────────────────

function ProductionJournalTab() {
  const [journals, setJournals] = useState([]);
  const [wos, setWos] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    work_order_id: "", date: new Date().toISOString().split("T")[0],
    consumption: [], output: [], notes: "",
  });

  const load = async () => {
    try {
      const [jRes, woRes, pRes] = await Promise.all([
        api.get("/manufacturing/production-journals"),
        api.get("/manufacturing/work-orders"),
        api.get("/products?limit=500"),
      ]);
      setJournals(jRes.data || []);
      setWos((woRes.data || []).filter(w => ["RELEASED","IN_PROGRESS"].includes(w.status)));
      setProducts(pRes.data?.items || pRes.data || []);
    } catch { toast.error("Failed to load journals"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const handleWOSelect = (e) => {
    const wo = wos.find(w => w.id === e.target.value);
    if (!wo) { setForm(f => ({ ...f, work_order_id: e.target.value })); return; }
    // Pre-fill output with the WO's FG
    setForm(f => ({
      ...f, work_order_id: e.target.value,
      output: [{ item_id: wo.product_id, item_name: wo.product_name, qty: wo.quantity_planned, uom: "pcs", is_co_product: false, is_by_product: false }],
    }));
  };

  const addConsumption = () => setForm(f => ({ ...f, consumption: [...f.consumption, { item_id: "", item_name: "", qty: 1, uom: "pcs", batch_no: "" }] }));
  const removeConsumption = (i) => setForm(f => ({ ...f, consumption: f.consumption.filter((_, idx) => idx !== i) }));
  const updateConsumption = (i, field, val) => setForm(f => {
    const arr = [...f.consumption];
    arr[i] = { ...arr[i], [field]: val };
    if (field === "item_id") { const p = products.find(p => p.id === val); arr[i].item_name = p?.name || ""; }
    return { ...f, consumption: arr };
  });

  const addOutput = () => setForm(f => ({ ...f, output: [...f.output, { item_id: "", item_name: "", qty: 1, uom: "pcs", is_co_product: false, is_by_product: false }] }));
  const removeOutput = (i) => setForm(f => ({ ...f, output: f.output.filter((_, idx) => idx !== i) }));
  const updateOutput = (i, field, val) => setForm(f => {
    const arr = [...f.output];
    arr[i] = { ...arr[i], [field]: val };
    if (field === "item_id") { const p = products.find(p => p.id === val); arr[i].item_name = p?.name || ""; }
    return { ...f, output: arr };
  });

  const save = async () => {
    if (!form.work_order_id) { toast.error("Select a Work Order"); return; }
    if (!form.consumption.length && !form.output.length) { toast.error("Add at least one consumption or output line"); return; }
    try {
      await api.post("/manufacturing/production-journals", form);
      toast.success("Production journal posted");
      setShowForm(false);
      setForm({ work_order_id: "", date: new Date().toISOString().split("T")[0], consumption: [], output: [], notes: "" });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Post failed"); }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <span className="font-mono text-xs text-zinc-500 uppercase tracking-wider">{journals.length} Production Journals</span>
        <Btn onClick={() => setShowForm(!showForm)}><Plus className="w-3.5 h-3.5" /> Post Journal</Btn>
      </div>

      {showForm && (
        <Card className="p-5 space-y-5">
          <div className="font-mono text-xs uppercase tracking-widest text-yellow-400 border-b border-zinc-800 pb-2">New Production Journal</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <FieldLabel>Work Order</FieldLabel>
              <Select value={form.work_order_id} onChange={handleWOSelect}>
                <option value="">Select WO (Released / In Progress)…</option>
                {wos.map(w => <option key={w.id} value={w.id}>{w.wo_number} — {w.product_name} × {w.quantity_planned}</option>)}
              </Select>
            </div>
            <div>
              <FieldLabel>Date</FieldLabel>
              <Input type="date" value={form.date} onChange={e => setForm(f => ({ ...f, date: e.target.value }))} />
            </div>
          </div>

          {/* Two-pane: Consume | Output */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Consume */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <FieldLabel>Consume (Raw Materials → WIP)</FieldLabel>
                <Btn variant="ghost" onClick={addConsumption}><Plus className="w-3 h-3" /> Add</Btn>
              </div>
              <div className="space-y-1.5">
                {form.consumption.map((c, i) => (
                  <div key={i} className="flex gap-1.5 items-center">
                    <div className="flex-1">
                      <Select value={c.item_id} onChange={e => updateConsumption(i, "item_id", e.target.value)}>
                        <option value="">Select item…</option>
                        {products.map(p => <option key={p.id} value={p.id}>{p.name} (Stock: {p.quantity})</option>)}
                      </Select>
                    </div>
                    <Input type="number" value={c.qty} placeholder="Qty" step="any" min="0" className="w-20"
                      onChange={e => updateConsumption(i, "qty", parseFloat(e.target.value) || 0)} />
                    <Input value={c.batch_no || ""} placeholder="Batch" className="w-20"
                      onChange={e => updateConsumption(i, "batch_no", e.target.value)} />
                    <button onClick={() => removeConsumption(i)} className="text-zinc-600 hover:text-red-400"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                ))}
                {!form.consumption.length && <div className="text-zinc-600 font-mono text-[10px] py-2">No consumption lines</div>}
              </div>
            </div>

            {/* Output */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <FieldLabel>Output (WIP → Finished Goods)</FieldLabel>
                <Btn variant="ghost" onClick={addOutput}><Plus className="w-3 h-3" /> Add</Btn>
              </div>
              <div className="space-y-1.5">
                {form.output.map((o, i) => (
                  <div key={i} className="flex gap-1.5 items-center">
                    <div className="flex-1">
                      <Select value={o.item_id} onChange={e => updateOutput(i, "item_id", e.target.value)}>
                        <option value="">Select item…</option>
                        {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                      </Select>
                    </div>
                    <Input type="number" value={o.qty} placeholder="Qty" step="any" min="0" className="w-20"
                      onChange={e => updateOutput(i, "qty", parseFloat(e.target.value) || 0)} />
                    <select value={o.is_by_product ? "by" : o.is_co_product ? "co" : "fg"}
                      onChange={e => updateOutput(i, e.target.value === "by" ? "is_by_product" : "is_co_product",
                        e.target.value !== "fg")}
                      className="w-20 bg-zinc-900 border border-zinc-700 text-zinc-300 text-[10px] px-1 py-2 focus:outline-none focus:border-yellow-400">
                      <option value="fg">FG</option>
                      <option value="co">Co-Prod</option>
                      <option value="by">By-Prod</option>
                    </select>
                    <button onClick={() => removeOutput(i)} className="text-zinc-600 hover:text-red-400"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                ))}
                {!form.output.length && <div className="text-zinc-600 font-mono text-[10px] py-2">No output lines</div>}
              </div>
            </div>
          </div>

          <textarea value={form.notes || ""} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="Notes…" rows={2}
            className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />

          <div className="flex gap-2">
            <Btn onClick={save}><Send className="w-3.5 h-3.5" /> Post Journal</Btn>
            <Btn variant="secondary" onClick={() => setShowForm(false)}>Cancel</Btn>
          </div>
        </Card>
      )}

      <Card>
        <div className="divide-y divide-zinc-800/60">
          {loading && <div className="p-8 flex justify-center"><RefreshCw className="w-5 h-5 animate-spin text-yellow-400" /></div>}
          {!loading && journals.length === 0 && <div className="p-10 text-center text-zinc-600 font-mono text-xs">No production journals posted yet.</div>}
          {journals.map(j => (
            <div key={j.id} className="px-5 py-4 hover:bg-zinc-900/40">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <span className="font-mono text-xs text-yellow-400 font-bold">{j.journal_number}</span>
                  <span className="font-mono text-xs text-zinc-500 ml-3">{j.date}</span>
                </div>
                <div className="font-mono text-xs text-zinc-400">
                  Cost: ₹{inr(j.total_material_cost)} · FG unit cost: ₹{inr(j.unit_cost_fg)}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 text-xs">
                <div>
                  <div className="text-zinc-600 font-mono text-[10px] uppercase mb-1">Consumed</div>
                  {(j.consumption || []).map((c, i) => (
                    <div key={i} className="text-zinc-400">{c.item_name} — {num(c.qty)} {c.uom}</div>
                  ))}
                </div>
                <div>
                  <div className="text-zinc-600 font-mono text-[10px] uppercase mb-1">Output</div>
                  {(j.output || []).map((o, i) => (
                    <div key={i} className="text-zinc-300">{o.item_name} — {num(o.qty)} {o.uom}
                      {o.is_co_product && <span className="ml-1 text-[9px] text-indigo-400">[CO-PROD]</span>}
                      {o.is_by_product && <span className="ml-1 text-[9px] text-zinc-500">[BY-PROD]</span>}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ─── Wastage Tab ──────────────────────────────────────────────────────────

function WastageTab() {
  const [entries, setEntries] = useState([]);
  const [wos, setWos] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ work_order_id: "", item_id: "", item_name: "", qty: 1, uom: "pcs", reason_code: "NORMAL", valuation: 0 });

  const load = async () => {
    try {
      const [wRes, woRes, pRes] = await Promise.all([
        api.get("/manufacturing/wastage"),
        api.get("/manufacturing/work-orders"),
        api.get("/products?limit=500"),
      ]);
      setEntries(wRes.data || []);
      setWos(woRes.data || []);
      setProducts(pRes.data?.items || pRes.data || []);
    } catch { toast.error("Failed to load wastage entries"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      await api.post("/manufacturing/wastage", form);
      toast.success("Wastage entry logged");
      setShowForm(false);
      setForm({ work_order_id: "", item_id: "", item_name: "", qty: 1, uom: "pcs", reason_code: "NORMAL", valuation: 0 });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
  };

  const totalAbnormal = entries.filter(e => e.reason_code === "ABNORMAL").reduce((s, e) => s + (e.valuation || 0), 0);

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <span className="font-mono text-xs text-zinc-500 uppercase tracking-wider">{entries.length} Wastage Entries</span>
          {totalAbnormal > 0 && <span className="ml-3 font-mono text-xs text-red-400">Abnormal loss: ₹{inr(totalAbnormal)}</span>}
        </div>
        <Btn onClick={() => setShowForm(!showForm)}><Plus className="w-3.5 h-3.5" /> Log Wastage</Btn>
      </div>

      {showForm && (
        <Card className="p-5 space-y-4">
          <div className="font-mono text-xs uppercase tracking-widest text-yellow-400 border-b border-zinc-800 pb-2">Log Wastage Entry</div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <FieldLabel>Work Order (optional)</FieldLabel>
              <Select value={form.work_order_id} onChange={e => setForm(f => ({ ...f, work_order_id: e.target.value }))}>
                <option value="">None</option>
                {wos.map(w => <option key={w.id} value={w.id}>{w.wo_number} — {w.product_name}</option>)}
              </Select>
            </div>
            <div className="sm:col-span-2">
              <FieldLabel>Item</FieldLabel>
              <Select value={form.item_id} onChange={e => {
                const p = products.find(p => p.id === e.target.value);
                setForm(f => ({ ...f, item_id: e.target.value, item_name: p?.name || "", uom: p?.unit || "pcs" }));
              }}>
                <option value="">Select item…</option>
                {products.map(p => <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>)}
              </Select>
            </div>
            <div>
              <FieldLabel>Qty</FieldLabel>
              <Input type="number" value={form.qty} min="0" step="any" onChange={e => setForm(f => ({ ...f, qty: parseFloat(e.target.value) || 0 }))} />
            </div>
            <div>
              <FieldLabel>UOM</FieldLabel>
              <Input value={form.uom} onChange={e => setForm(f => ({ ...f, uom: e.target.value }))} />
            </div>
            <div>
              <FieldLabel>Reason</FieldLabel>
              <Select value={form.reason_code} onChange={e => setForm(f => ({ ...f, reason_code: e.target.value }))}>
                {["NORMAL","ABNORMAL","REWORK","REJECTED"].map(r => <option key={r}>{r}</option>)}
              </Select>
            </div>
            <div>
              <FieldLabel>Valuation (₹)</FieldLabel>
              <Input type="number" value={form.valuation} min="0" step="any" onChange={e => setForm(f => ({ ...f, valuation: parseFloat(e.target.value) || 0 }))} />
            </div>
          </div>
          {form.reason_code === "ABNORMAL" && (
            <div className="flex items-center gap-2 text-xs text-red-400 bg-red-950/20 border border-red-900 px-3 py-2">
              <AlertTriangle className="w-3.5 h-3.5" /> Abnormal wastage will be flagged for P&amp;L expense posting via the accounting module.
            </div>
          )}
          <div className="flex gap-2">
            <Btn onClick={save}>Log Entry</Btn>
            <Btn variant="secondary" onClick={() => setShowForm(false)}>Cancel</Btn>
          </div>
        </Card>
      )}

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left px-5 py-2">Ref</th>
                <th className="text-left px-3 py-2">Item</th>
                <th className="text-right px-3 py-2">Qty</th>
                <th className="text-left px-3 py-2">Reason</th>
                <th className="text-right px-3 py-2">Valuation</th>
                <th className="text-left px-3 py-2">WO</th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={6} className="p-8 text-center"><RefreshCw className="w-4 h-4 animate-spin text-yellow-400 mx-auto" /></td></tr>}
              {!loading && entries.length === 0 && <tr><td colSpan={6} className="p-8 text-center text-zinc-600">No wastage entries.</td></tr>}
              {entries.map(e => (
                <tr key={e.id} className={`border-b border-zinc-900 hover:bg-zinc-900/30 ${e.reason_code === "ABNORMAL" ? "text-red-300" : "text-zinc-300"}`}>
                  <td className="px-5 py-3 font-bold text-yellow-400">{e.wastage_number}</td>
                  <td className="px-3 py-3">{e.item_name}</td>
                  <td className="px-3 py-3 text-right">{num(e.qty)} {e.uom}</td>
                  <td className="px-3 py-3"><StatusBadge status={e.reason_code} /></td>
                  <td className="px-3 py-3 text-right">₹{inr(e.valuation)}</td>
                  <td className="px-3 py-3 text-zinc-500">{e.work_order_id ? wos.find(w => w.id === e.work_order_id)?.wo_number || "—" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// ─── QC Tab ────────────────────────────────────────────────────────────────

function QCTab() {
  const [reports, setReports] = useState([]);
  const [pendingWOs, setPendingWOs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    work_order_id: "", product_id: "", product_name: "",
    quantity_checked: 0, quantity_passed: 0, quantity_failed: 0,
    inspector_name: "", notes: "", status: "PASSED", defects: [],
  });

  const load = async () => {
    try {
      const [qcRes, woRes] = await Promise.all([
        api.get("/manufacturing/qc"),
        api.get("/manufacturing/work-orders"),
      ]);
      setReports(qcRes.data || []);
      setPendingWOs((woRes.data || []).filter(w => w.status === "QC_PENDING"));
    } catch { toast.error("Failed to load QC data"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const handleWOSelect = (e) => {
    const wo = pendingWOs.find(w => w.id === e.target.value);
    setForm(f => ({ ...f, work_order_id: e.target.value, product_id: wo?.product_id || "", product_name: wo?.product_name || "", quantity_checked: wo?.quantity_planned || 0 }));
  };

  const save = async () => {
    try { await api.post("/manufacturing/qc", form); toast.success("QC Report filed"); setShowForm(false); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "QC save failed"); }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <span className="font-mono text-xs text-zinc-500 uppercase tracking-wider">{reports.length} QC Reports · {pendingWOs.length} WOs pending</span>
        <Btn onClick={() => setShowForm(!showForm)}><Plus className="w-3.5 h-3.5" /> File QC Report</Btn>
      </div>

      {showForm && (
        <Card className="p-5 space-y-4">
          <div className="font-mono text-xs uppercase tracking-widest text-yellow-400 border-b border-zinc-800 pb-2">New QC Report</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <FieldLabel>Work Order (QC Pending)</FieldLabel>
              <Select value={form.work_order_id} onChange={handleWOSelect}>
                <option value="">Select WO…</option>
                {pendingWOs.map(w => <option key={w.id} value={w.id}>{w.wo_number} — {w.product_name}</option>)}
              </Select>
            </div>
            <div><FieldLabel>Inspector Name</FieldLabel><Input value={form.inspector_name} onChange={e => setForm(f => ({ ...f, inspector_name: e.target.value }))} /></div>
            <div><FieldLabel>Qty Checked</FieldLabel><Input type="number" value={form.quantity_checked} onChange={e => setForm(f => ({ ...f, quantity_checked: parseFloat(e.target.value) }))} /></div>
            <div><FieldLabel>Qty Passed</FieldLabel>
              <Input type="number" value={form.quantity_passed} onChange={e => {
                const p = parseFloat(e.target.value);
                setForm(f => ({ ...f, quantity_passed: p, quantity_failed: Math.max(0, f.quantity_checked - p), status: p >= f.quantity_checked ? "PASSED" : (p > 0 ? "PARTIAL" : "FAILED") }));
              }} />
            </div>
          </div>
          <textarea value={form.notes || ""} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="QC notes…" rows={2}
            className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs px-3 py-2 focus:outline-none focus:border-yellow-400" />
          <div className="flex gap-2">
            <Btn onClick={save}>File Report</Btn>
            <Btn variant="secondary" onClick={() => setShowForm(false)}>Cancel</Btn>
          </div>
        </Card>
      )}

      <Card>
        <div className="divide-y divide-zinc-800/60">
          {loading && <div className="p-8 flex justify-center"><RefreshCw className="w-5 h-5 animate-spin text-yellow-400" /></div>}
          {!loading && reports.length === 0 && <div className="p-10 text-center text-zinc-600 font-mono text-xs">No QC reports.</div>}
          {reports.map(r => (
            <div key={r.id} className="px-5 py-4 flex items-center justify-between hover:bg-zinc-900/40">
              <div>
                <div className="text-sm font-semibold text-zinc-100">{r.product_name}</div>
                <div className="text-xs text-zinc-500 font-mono">{r.qc_number} · {r.inspector_name} · Passed: {r.quantity_passed}/{r.quantity_checked}</div>
              </div>
              <div className="flex items-center gap-3">
                {r.quantity_failed > 0 && <span className="font-mono text-xs text-red-400">Rejected: {r.quantity_failed}</span>}
                <StatusBadge status={r.status} />
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────────────────

const TABS = [
  { id: "dashboard",  label: "Dashboard",          icon: BarChart3     },
  { id: "bom",        label: "Bill of Materials",   icon: Layers        },
  { id: "work-orders",label: "Work Orders",         icon: ClipboardList },
  { id: "journals",   label: "Production Journals", icon: BookOpen      },
  { id: "wastage",    label: "Wastage",             icon: AlertTriangle },
  { id: "qc",         label: "Quality Control",     icon: FlaskConical  },
];

export default function Manufacturing() {
  const [tab, setTab] = useState("dashboard");

  return (
    <div className="space-y-5">
      <div className="border-b border-zinc-800 pb-4">
        <div className="font-mono text-[10px] uppercase tracking-widest text-zinc-500 mb-2 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" />
          Manufacturing Operations
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight text-zinc-50 uppercase">Manufacturing</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Multi-level BOM · Work Orders · Production Journals · Wastage · QC · MRP
        </p>
      </div>

      <div className="flex gap-0 border-b border-zinc-800 overflow-x-auto">
        {TABS.map(t => {
          const Icon = t.icon;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-mono uppercase tracking-wider border-b-2 transition-colors whitespace-nowrap ${
                tab === t.id ? "border-yellow-400 text-yellow-400" : "border-transparent text-zinc-500 hover:text-zinc-300"
              }`}>
              <Icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      <div>
        {tab === "dashboard"   && <MfgDashboard />}
        {tab === "bom"         && <BOMTab />}
        {tab === "work-orders" && <WorkOrdersTab />}
        {tab === "journals"    && <ProductionJournalTab />}
        {tab === "wastage"     && <WastageTab />}
        {tab === "qc"          && <QCTab />}
      </div>
    </div>
  );
}
