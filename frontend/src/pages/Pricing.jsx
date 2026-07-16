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
const Btn = ({ children, onClick, variant = "primary", disabled, className = "" }) => {
  const styles = {
    primary: "bg-yellow-400 text-black hover:bg-yellow-300",
    ghost: "border border-zinc-700 text-zinc-300 hover:border-yellow-400 hover:text-yellow-400",
    danger: "border border-red-700 text-red-400 hover:bg-red-500/10",
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
const fmt = (v) => (v == null ? "—" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 }));

// ══════════════════════════════════════════════════════════════
// Tab: Price Lists
// ══════════════════════════════════════════════════════════════
function PriceListsTab() {
  const [lists, setLists] = useState([]);
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({ name: "", currency: "INR", assigned_type: "customer", assigned_id: "", valid_from: "", valid_to: "", priority: 0 });
  const [rows, setRows] = useState([{ item_id: "", uom: "pcs", rate: "", min_qty: "0" }]);

  const load = useCallback(async () => {
    try { setLists((await api.get("/pricing/price-lists")).data); }
    catch { toast.error("Failed to load price lists"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.name) return toast.error("Name required");
    try {
      await api.post("/pricing/price-lists", {
        name: form.name, currency: form.currency,
        valid_from: form.valid_from || null, valid_to: form.valid_to || null,
        priority: Number(form.priority || 0),
        assigned_to: { type: form.assigned_type, id: form.assigned_type === "all" ? null : form.assigned_id },
        items: rows.filter((r) => r.item_id && r.rate).map((r) => ({
          item_id: r.item_id, uom: r.uom, rate: Number(r.rate), min_qty: Number(r.min_qty || 0),
        })),
      });
      toast.success("Price list created");
      setShow(false);
      setForm({ name: "", currency: "INR", assigned_type: "customer", assigned_id: "", valid_from: "", valid_to: "", priority: 0 });
      setRows([{ item_id: "", uom: "pcs", rate: "", min_qty: "0" }]);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Create failed"); }
  };

  return (
    <div>
      <SectionHeader title="Price Lists" subtitle="Customer / group rate cards with volume tiers"
        right={<Btn onClick={() => setShow((v) => !v)}>{show ? "Cancel" : "+ New List"}</Btn>} />

      {show && (
        <Card className="p-5 mb-5">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Input label="List Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Wholesale — North" />
            <Select label="Assigned To" value={form.assigned_type} onChange={(e) => setForm({ ...form, assigned_type: e.target.value })}>
              <option value="customer">Customer</option>
              <option value="group">Customer Group</option>
              <option value="all">All</option>
            </Select>
            <Input label="Customer / Group ID" value={form.assigned_id} disabled={form.assigned_type === "all"}
              onChange={(e) => setForm({ ...form, assigned_id: e.target.value })} placeholder="id" />
            <Input label="Valid From" type="date" value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} />
            <Input label="Valid To" type="date" value={form.valid_to} onChange={(e) => setForm({ ...form, valid_to: e.target.value })} />
            <Input label="Priority" type="text" inputMode="decimal" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} />
          </div>

          <div className="mt-5">
            <span className="block text-xs font-mono uppercase tracking-wider text-zinc-500 mb-2">Items (volume tiers via min qty)</span>
            <div className="space-y-2">
              {rows.map((r, i) => (
                <div key={i} className="grid grid-cols-12 gap-2">
                  <input className="col-span-5 bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-zinc-100" placeholder="item_id"
                    value={r.item_id} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, item_id: e.target.value } : x))} />
                  <input className="col-span-2 bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-zinc-100" placeholder="uom"
                    value={r.uom} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, uom: e.target.value } : x))} />
                  <input className="col-span-2 bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-zinc-100" placeholder="rate" type="text" inputMode="decimal"
                    value={r.rate} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, rate: e.target.value } : x))} />
                  <input className="col-span-2 bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-zinc-100" placeholder="min qty" type="text" inputMode="decimal"
                    value={r.min_qty} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, min_qty: e.target.value } : x))} />
                  <button onClick={() => setRows(rows.filter((_, j) => j !== i))} className="col-span-1 text-red-400 hover:text-red-300">✕</button>
                </div>
              ))}
            </div>
            <button onClick={() => setRows([...rows, { item_id: "", uom: "pcs", rate: "", min_qty: "0" }])}
              className="mt-2 text-xs font-mono text-yellow-400 hover:text-yellow-300">+ add item row</button>
          </div>
          <div className="mt-4"><Btn onClick={create}>Create Price List</Btn></div>
        </Card>
      )}

      <div className="space-y-3">
        {lists.map((l) => (
          <Card key={l.id} className="p-4">
            <div className="flex justify-between">
              <div>
                <h3 className="font-display font-bold text-zinc-50">{l.name}</h3>
                <div className="text-xs text-zinc-500 font-mono mt-1">
                  {l.assigned_to?.type}{l.assigned_to?.id ? ` · ${l.assigned_to.id}` : ""} · {l.currency} · {l.items?.length || 0} items
                  {l.valid_from && ` · ${l.valid_from}→${l.valid_to || "∞"}`}
                </div>
              </div>
              <span className="text-xs font-mono text-zinc-600">priority {l.priority || 0}</span>
            </div>
            {l.items?.length > 0 && (
              <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
                {l.items.slice(0, 8).map((it, i) => (
                  <div key={i} className="text-xs bg-zinc-950 px-2 py-1 border border-zinc-800">
                    <span className="text-zinc-400">{it.item_id.slice(0, 8)}</span> ·{" "}
                    <span className="text-yellow-400 font-mono">₹{fmt(it.rate)}</span>
                    {it.min_qty > 0 && <span className="text-zinc-600"> @≥{it.min_qty}</span>}
                  </div>
                ))}
              </div>
            )}
          </Card>
        ))}
        {lists.length === 0 && <Card className="p-8 text-center text-zinc-500 text-sm">No price lists yet.</Card>}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// Tab: Discount Schemes (slab grid)
// ══════════════════════════════════════════════════════════════
function SchemesTab() {
  const [schemes, setSchemes] = useState([]);
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({ name: "", type: "slab", applies_to: "all", applies_to_id: "", valid_from: "", valid_to: "", stackable: false, priority: 0 });
  const [slabs, setSlabs] = useState([{ from_qty: "0", to_qty: "", discount_pct: "", discount_amount: "", free_item_id: "", free_qty: "" }]);

  const load = useCallback(async () => {
    try { setSchemes((await api.get("/pricing/discount-schemes")).data); }
    catch { toast.error("Failed to load schemes"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.name) return toast.error("Name required");
    try {
      await api.post("/pricing/discount-schemes", {
        name: form.name, type: form.type, applies_to: form.applies_to,
        applies_to_id: form.applies_to === "all" ? null : form.applies_to_id,
        valid_from: form.valid_from || null, valid_to: form.valid_to || null,
        stackable: form.stackable, priority: Number(form.priority || 0),
        slabs: slabs.map((s) => ({
          from_qty: Number(s.from_qty || 0),
          to_qty: s.to_qty === "" ? null : Number(s.to_qty),
          discount_pct: s.discount_pct === "" ? null : Number(s.discount_pct),
          discount_amount: s.discount_amount === "" ? null : Number(s.discount_amount),
          free_item_id: s.free_item_id || null,
          free_qty: s.free_qty === "" ? null : Number(s.free_qty),
        })),
      });
      toast.success("Scheme created");
      setShow(false);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Create failed"); }
  };

  return (
    <div>
      <SectionHeader title="Discount Schemes" subtitle="Slab / flat / free-qty schemes"
        right={<Btn onClick={() => setShow((v) => !v)}>{show ? "Cancel" : "+ New Scheme"}</Btn>} />

      {show && (
        <Card className="p-5 mb-5">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Input label="Scheme Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Diwali Slab" />
            <Select label="Type" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
              <option value="slab">Slab</option><option value="flat">Flat</option><option value="free_qty">Free Qty</option>
            </Select>
            <Select label="Applies To" value={form.applies_to} onChange={(e) => setForm({ ...form, applies_to: e.target.value })}>
              <option value="all">All Items</option><option value="item">Item</option><option value="group">Item Group</option>
            </Select>
            <Input label="Item / Group ID" value={form.applies_to_id} disabled={form.applies_to === "all"}
              onChange={(e) => setForm({ ...form, applies_to_id: e.target.value })} />
            <Input label="Valid From" type="date" value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} />
            <Input label="Valid To" type="date" value={form.valid_to} onChange={(e) => setForm({ ...form, valid_to: e.target.value })} />
          </div>
          <label className="flex items-center gap-2 text-sm text-zinc-300 mt-3">
            <input type="checkbox" checked={form.stackable} onChange={(e) => setForm({ ...form, stackable: e.target.checked })} className="accent-yellow-400" />
            Stackable with other schemes
          </label>

          <div className="mt-5">
            <span className="block text-xs font-mono uppercase tracking-wider text-zinc-500 mb-2">Slab grid</span>
            <div className="grid grid-cols-12 gap-2 text-[11px] font-mono uppercase text-zinc-600 mb-1">
              <span className="col-span-2">From</span><span className="col-span-2">To</span>
              <span className="col-span-2">Disc %</span><span className="col-span-2">Disc ₹</span>
              <span className="col-span-2">Free item</span><span className="col-span-1">Free qty</span>
            </div>
            <div className="space-y-2">
              {slabs.map((s, i) => (
                <div key={i} className="grid grid-cols-12 gap-2">
                  {["from_qty", "to_qty", "discount_pct", "discount_amount", "free_item_id", "free_qty"].map((field, ci) => (
                    <input key={field}
                      className={`${field === "free_item_id" ? "col-span-2" : ci === 5 ? "col-span-1" : "col-span-2"} bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-sm text-zinc-100`}
                      type={field === "free_item_id" ? "text" : "number"}
                      value={s[field]} onChange={(e) => setSlabs(slabs.map((x, j) => j === i ? { ...x, [field]: e.target.value } : x))} />
                  ))}
                  <button onClick={() => setSlabs(slabs.filter((_, j) => j !== i))} className="col-span-1 text-red-400">✕</button>
                </div>
              ))}
            </div>
            <button onClick={() => setSlabs([...slabs, { from_qty: "", to_qty: "", discount_pct: "", discount_amount: "", free_item_id: "", free_qty: "" }])}
              className="mt-2 text-xs font-mono text-yellow-400 hover:text-yellow-300">+ add slab</button>
          </div>
          <div className="mt-4"><Btn onClick={create}>Create Scheme</Btn></div>
        </Card>
      )}

      <div className="space-y-3">
        {schemes.map((s) => (
          <Card key={s.id} className="p-4">
            <div className="flex justify-between items-start">
              <div>
                <h3 className="font-display font-bold text-zinc-50">{s.name}</h3>
                <div className="text-xs text-zinc-500 font-mono mt-1">
                  {s.type} · {s.applies_to}{s.applies_to_id ? ` ${s.applies_to_id}` : ""}
                  {s.stackable && " · stackable"} · {s.slabs?.length || 0} slabs
                </div>
              </div>
            </div>
            {s.slabs?.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {s.slabs.map((sl, i) => (
                  <span key={i} className="text-xs bg-zinc-950 px-2 py-1 border border-zinc-800 text-zinc-400">
                    {sl.from_qty}–{sl.to_qty ?? "∞"}:{" "}
                    {sl.discount_pct != null ? `${sl.discount_pct}%` :
                     sl.discount_amount != null ? `₹${sl.discount_amount}` :
                     sl.free_item_id ? `free ${sl.free_qty}×${sl.free_item_id.slice(0, 6)}` : "—"}
                  </span>
                ))}
              </div>
            )}
          </Card>
        ))}
        {schemes.length === 0 && <Card className="p-8 text-center text-zinc-500 text-sm">No schemes yet.</Card>}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// Tab: Resolver / "Why this price"
// ══════════════════════════════════════════════════════════════
function ResolverTab() {
  const [q, setQ] = useState({ itemId: "", qty: "1", customerId: "", godownId: "", allowStacking: false });
  const [res, setRes] = useState(null);

  const resolve = async () => {
    if (!q.itemId) return toast.error("Item id required");
    try {
      const { data } = await api.get("/pricing/resolve", {
        params: {
          itemId: q.itemId, qty: Number(q.qty || 1),
          customerId: q.customerId || undefined, godownId: q.godownId || undefined,
          allowStacking: q.allowStacking,
        },
      });
      setRes(data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Resolve failed"); }
  };

  return (
    <div>
      <SectionHeader title="Price Resolver" subtitle="Explain the effective price for any item / customer / warehouse" />
      <Card className="p-5 mb-5">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
          <Input label="Item ID" value={q.itemId} onChange={(e) => setQ({ ...q, itemId: e.target.value })} />
          <Input label="Qty" type="text" inputMode="decimal" value={q.qty} onChange={(e) => setQ({ ...q, qty: e.target.value })} />
          <Input label="Customer ID" value={q.customerId} onChange={(e) => setQ({ ...q, customerId: e.target.value })} />
          <Input label="Warehouse ID" value={q.godownId} onChange={(e) => setQ({ ...q, godownId: e.target.value })} />
          <Btn onClick={resolve}>Resolve</Btn>
        </div>
        <label className="flex items-center gap-2 text-sm text-zinc-300 mt-3">
          <input type="checkbox" checked={q.allowStacking} onChange={(e) => setQ({ ...q, allowStacking: e.target.checked })} className="accent-yellow-400" />
          Allow scheme stacking
        </label>
      </Card>

      {res && (
        <Card className="p-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <KPI label="Base Rate" value={`₹${fmt(res.base_rate)}`} sub={res.rate_source} />
            <KPI label="Gross" value={`₹${fmt(res.gross_amount)}`} />
            <KPI label="Discount" value={`₹${fmt(res.discount_amount)}`} accent="text-orange-400" />
            <KPI label="Net" value={`₹${fmt(res.net_amount)}`} accent="text-emerald-400" sub={`@₹${fmt(res.effective_rate)}/unit`} />
          </div>

          <div className="bg-zinc-950 border-l-4 border-yellow-400 p-4 mb-4">
            <div className="text-xs font-mono uppercase tracking-wider text-yellow-400 mb-2">Why this price</div>
            <ol className="text-sm text-zinc-300 space-y-1">
              {res.resolution_chain.map((step, i) => (
                <li key={i}>{i === res.resolution_chain.length - 1 ? "✓" : "✗"} {step}</li>
              ))}
            </ol>
            <div className="mt-2 text-sm text-zinc-400">
              Rate from <b className="text-yellow-400">{res.rate_source_name}</b> ({res.rate_source})
            </div>
          </div>

          {res.applied_schemes.length > 0 && (
            <div className="mb-4">
              <div className="text-xs font-mono uppercase tracking-wider text-zinc-500 mb-2">Applied Schemes</div>
              {res.applied_schemes.map((s, i) => (
                <div key={i} className="text-sm text-zinc-300 py-1 border-b border-zinc-900">
                  ▸ {s.description} {s.discount_amount > 0 && <span className="text-orange-400 font-mono">−₹{fmt(s.discount_amount)}</span>}
                </div>
              ))}
            </div>
          )}

          {res.free_lines.length > 0 && (
            <div className="bg-emerald-500/10 border border-emerald-700 p-3">
              <div className="text-xs font-mono uppercase tracking-wider text-emerald-400 mb-1">Free Lines (zero value, real stock impact)</div>
              {res.free_lines.map((f, i) => (
                <div key={i} className="text-sm text-emerald-300">+ {f.qty} × {f.item_id} @ ₹0 — via {f.scheme_name}</div>
              ))}
            </div>
          )}
        </Card>
      )}
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

// ══════════════════════════════════════════════════════════════
const TABS = [
  { id: "lists", label: "Price Lists" },
  { id: "schemes", label: "Discount Schemes" },
  { id: "resolver", label: "Why This Price" },
];

export default function Pricing() {
  const [tab, setTab] = useState("lists");
  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="font-display font-black text-2xl text-zinc-50 tracking-tight">Pricing & Schemes</h1>
        <p className="text-zinc-500 text-sm mt-1">Customer rate cards, discount schemes, and a deterministic, explainable price resolver.</p>
      </div>
      <div className="flex gap-1 border-b border-zinc-800 mb-6">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2.5 text-sm font-mono uppercase tracking-wider transition-colors border-b-2 -mb-px ${
              tab === t.id ? "border-yellow-400 text-yellow-400" : "border-transparent text-zinc-500 hover:text-zinc-300"}`}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "lists" && <PriceListsTab />}
      {tab === "schemes" && <SchemesTab />}
      {tab === "resolver" && <ResolverTab />}
    </div>
  );
}
