import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import {
  Boxes, Plus, ArrowDownToLine, ArrowUpFromLine,
  TrendingDown, AlertTriangle, FileText, Trash2,
} from "lucide-react";
import {
  PageHeader, PrimaryButton, SecondaryButton,
  Field, Input, Textarea, Select, StatusBadge, EmptyState,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const num = (n, d = 2) => Number(n || 0).toFixed(d);

export default function JobWork() {
  const [challans, setChallans] = useState([]);
  const [receipts, setReceipts] = useState([]);
  const [products, setProducts] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("challans");
  const [pendingReport, setPendingReport] = useState([]);
  const [itc04, setItc04] = useState(null);
  const [itc04Period, setItc04Period] = useState(() => {
    const d = new Date();
    return `${String(d.getMonth() + 1).padStart(2, "0")}${d.getFullYear()}`;
  });

  const [isChallanModalOpen, setIsChallanModalOpen] = useState(false);
  const [isReceiptModalOpen, setIsReceiptModalOpen] = useState(false);
  const [selectedChallan, setSelectedChallan] = useState(null);

  const [newChallan, setNewChallan] = useState({
    job_worker_id: "", date: new Date().toISOString().split("T")[0],
    nature: "inputs",
    items: [{ product_id: "", quantity: 1, sku: "", product_name: "", is_custom: false }],
    notes: "",
  });

  const [newReceipt, setNewReceipt] = useState({
    date: new Date().toISOString().split("T")[0], items: [], notes: "",
  });

  const loadData = async () => {
    setLoading(true);
    try {
      const [cRes, pRes, sRes] = await Promise.all([
        api.get("/job-work/challans"),
        api.get("/products"),
        api.get("/suppliers"),
      ]);
      setChallans(cRes.data);
      setProducts(pRes.data);
      setSuppliers(sRes.data);
    } catch { toast.error("Failed to load Job Work data."); }
    finally { setLoading(false); }
  };

  const loadReceipts = async () => {
    try { const res = await api.get("/job-work/receipts"); setReceipts(res.data); }
    catch { /* non-fatal */ }
  };

  const loadPendingReport = async () => {
    try { const res = await api.get("/job-work/reports/pending"); setPendingReport(res.data); }
    catch { /* non-fatal */ }
  };

  const loadItc04 = async (period) => {
    try {
      const res = await api.get(`/job-work/itc-04?period=${period}`);
      setItc04(res.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load ITC-04"); }
  };

  useEffect(() => { loadData(); }, []);

  useEffect(() => {
    if (tab === "receipts") loadReceipts();
    else if (tab === "pending") loadPendingReport();
    else if (tab === "itc04") loadItc04(itc04Period);
  }, [tab]);

  const handleCreateChallan = async (e) => {
    e.preventDefault();
    if (!newChallan.job_worker_id) { toast.warning("Please select a Job Worker."); return; }

    for (const it of newChallan.items) {
      if (it.is_custom) {
        if (!String(it.product_name || "").trim()) { toast.warning("Please enter a product name for the manual line item."); return; }
      } else if (!it.product_id) {
        toast.warning("Please select a product for each line item."); return;
      }
    }

    const finalItems = newChallan.items.map(it => {
      if (it.is_custom) {
        return { product_id: null, product_name: it.product_name.trim(), sku: it.sku || "", quantity: parseFloat(it.quantity), unit: it.unit || "pcs", is_custom: true };
      }
      const pr = products.find(p => p.id === it.product_id);
      return { product_id: it.product_id, product_name: pr?.name || "", sku: pr?.sku || "", quantity: parseFloat(it.quantity), unit: pr?.unit || "pcs", is_custom: false };
    });
    for (const item of finalItems) {
      if (item.is_custom) continue;
      const pr = products.find(p => p.id === item.product_id);
      if (pr && item.quantity > parseFloat(pr.quantity || 0)) {
        toast.error(`Insufficient stock for ${pr.name}. Available: ${pr.quantity}`); return;
      }
    }

    try {
      const worker = suppliers.find(s => s.id === newChallan.job_worker_id);
      await api.post("/job-work/challans", { ...newChallan, job_worker_name: worker?.company || worker?.name || "", items: finalItems });
      toast.success("Job Work Challan generated!");
      setIsChallanModalOpen(false);
      setNewChallan({ job_worker_id: "", date: new Date().toISOString().split("T")[0], nature: "inputs", items: [{ product_id: "", quantity: 1, sku: "", product_name: "", is_custom: false }], notes: "" });
      loadData();
    } catch (err) { toast.error("Failed: " + (err.response?.data?.detail || "")); }
  };

  const handleOpenReceiptModal = async (challan) => {
    setSelectedChallan(challan);
    try {
      const res = await api.get(`/job-work/receipts?challan_id=${challan.id}`);
      const keyOf = (it) => (it.is_custom || !it.product_id) ? `custom::${it.product_name || ""}` : it.product_id;
      const receivedMap = {};
      res.data.forEach(r => r.items?.forEach(it => {
        const k = keyOf(it);
        receivedMap[k] = (receivedMap[k] || 0) + parseFloat(it.quantity_received || 0);
      }));
      setNewReceipt({
        date: new Date().toISOString().split("T")[0],
        items: challan.items.map(it => {
          const recv = receivedMap[keyOf(it)] || 0;
          const pend = Math.max(0, it.quantity - recv);
          return { product_id: it.product_id || null, product_name: it.product_name, sku: it.sku || "", is_custom: !!it.is_custom, quantity_sent: it.quantity, quantity_already_received: recv, quantity_pending: pend, quantity_received: pend, scrap_quantity: 0 };
        }),
        notes: "",
      });
      setIsReceiptModalOpen(true);
    } catch { toast.error("Failed to load existing receipts."); }
  };

  const handleCreateReceipt = async (e) => {
    e.preventDefault();
    for (const item of newReceipt.items) {
      if (item.quantity_received > item.quantity_pending + 1e-5) {
        toast.error(`Received qty for ${item.product_name} exceeds pending (${item.quantity_pending}).`); return;
      }
    }
    try {
      await api.post(`/job-work/challans/${selectedChallan.id}/receipt`, newReceipt);
      toast.success("Material receipt registered!");
      setIsReceiptModalOpen(false);
      loadData();
    } catch (err) { toast.error("Failed: " + (err.response?.data?.detail || "")); }
  };

  const TABS_DEF = [
    { id: "challans", label: "Challans Sent", icon: ArrowUpFromLine },
    { id: "receipts", label: "Receipts Inward", icon: ArrowDownToLine },
    { id: "pending",  label: "Pending Report",  icon: TrendingDown },
    { id: "itc04",    label: "ITC-04",          icon: FileText },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Inventory & Production"
        title="Job Work Processing"
        description="Track materials sent to job workers · Record returns · Monitor overdue challans · Generate ITC-04."
        actions={<PrimaryButton icon={Plus} onClick={() => setIsChallanModalOpen(true)}>NEW JOB WORK CHALLAN</PrimaryButton>}
      />

      {/* Tab bar */}
      <div className="flex border-b border-zinc-800 gap-4">
        {TABS_DEF.map(t => {
          const Icon = t.icon;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`py-3 px-1 font-mono text-xs uppercase tracking-wider border-b-2 flex items-center gap-1.5 transition-colors ${
                tab === t.id ? "border-primary text-primary font-bold" : "border-transparent text-zinc-400 hover:text-zinc-200"
              }`}>
              <Icon className="w-3.5 h-3.5" />{t.label}
            </button>
          );
        })}
      </div>

      {/* ── Challans Tab ─────────────────────────────────────────────────────── */}
      {tab === "challans" && (
        <div className="space-y-4">
          {challans.length === 0 ? (
            <EmptyState message="No Job Work Challans yet" />
          ) : (
            <div className="border border-zinc-800 bg-zinc-950 overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-zinc-800 bg-zinc-900/50 text-zinc-400">
                    <th className="p-3 uppercase">Challan No</th>
                    <th className="p-3 uppercase">Date</th>
                    <th className="p-3 uppercase">Due Date</th>
                    <th className="p-3 uppercase">Job Worker</th>
                    <th className="p-3 uppercase">Items Sent</th>
                    <th className="p-3 uppercase">Status</th>
                    <th className="p-3 uppercase text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {challans.map(c => {
                    const overdue = c.is_overdue || c.deemed_supply;
                    return (
                      <tr key={c.id} className={`border-b border-zinc-900 hover:bg-zinc-900/20 ${overdue ? "text-red-300" : "text-zinc-100"}`}>
                        <td className="p-3 font-bold text-primary">{c.challan_number}</td>
                        <td className="p-3">{c.date}</td>
                        <td className={`p-3 ${overdue ? "text-red-400 font-bold" : "text-zinc-400"}`}>
                          {c.due_date || "—"}
                          {overdue && <span className="ml-1 text-[9px] border border-red-700 text-red-400 px-1 uppercase">Overdue</span>}
                        </td>
                        <td className="p-3">{c.job_worker_name}</td>
                        <td className="p-3">
                          {c.items?.map(it => (
                            <div key={it.product_id}>{it.product_name} — <span className="font-bold">{it.quantity}</span> {it.unit}
                              {it.taxable_value > 0 && <span className="text-zinc-500 ml-1">(₹{inr(it.taxable_value)})</span>}
                            </div>
                          ))}
                        </td>
                        <td className="p-3">
                          <StatusBadge status={c.status} />
                          {overdue && <div className="mt-1 text-[9px] text-red-400 uppercase">Deemed Supply</div>}
                        </td>
                        <td className="p-3 text-right">
                          {c.status !== "COMPLETED" && (
                            <button onClick={() => handleOpenReceiptModal(c)}
                              className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 px-2 py-1 font-mono text-[10px] uppercase font-bold">
                              LOG RECEIPT
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Receipts Tab ──────────────────────────────────────────────────────── */}
      {tab === "receipts" && (
        <div className="space-y-4">
          {receipts.length === 0 ? <EmptyState message="No inward receipts logged yet" /> : (
            <div className="border border-zinc-800 bg-zinc-950 overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-zinc-800 bg-zinc-900/50 text-zinc-400">
                    <th className="p-3 uppercase">Receipt No</th>
                    <th className="p-3 uppercase">Date</th>
                    <th className="p-3 uppercase">Items Received</th>
                    <th className="p-3 uppercase">Scrap</th>
                    <th className="p-3 uppercase">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {receipts.map(r => (
                    <tr key={r.id} className="border-b border-zinc-900 hover:bg-zinc-900/20 text-zinc-100">
                      <td className="p-3 font-bold text-green-500">{r.receipt_number}</td>
                      <td className="p-3">{r.date}</td>
                      <td className="p-3">
                        {r.items?.map(it => <div key={it.product_id}>{it.product_name} — <span className="font-bold">{it.quantity_received}</span></div>)}
                      </td>
                      <td className="p-3">
                        {r.items?.map(it => (
                          <div key={it.product_id} className="text-zinc-500">
                            {it.scrap_quantity > 0 ? `${it.product_name}: ${it.scrap_quantity} scrap` : "—"}
                          </div>
                        ))}
                      </td>
                      <td className="p-3 text-zinc-400">{r.notes || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Pending Report ────────────────────────────────────────────────────── */}
      {tab === "pending" && (
        <div className="space-y-4">
          {pendingReport.length === 0 ? <EmptyState message="No pending materials at job workers" /> : (
            <div className="border border-zinc-800 bg-zinc-950 overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-zinc-800 bg-zinc-900/50 text-zinc-400">
                    <th className="p-3 uppercase">Challan</th>
                    <th className="p-3 uppercase">Job Worker</th>
                    <th className="p-3 uppercase">Product</th>
                    <th className="p-3 uppercase">Sent</th>
                    <th className="p-3 uppercase">Received</th>
                    <th className="p-3 uppercase text-primary">Pending</th>
                    <th className="p-3 uppercase">Due Date</th>
                    <th className="p-3 uppercase">Days Left</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingReport.map((p, i) => {
                    const overdue = p.is_overdue;
                    const critical = !overdue && p.days_remaining !== null && p.days_remaining <= 30;
                    return (
                      <tr key={i} className={`border-b border-zinc-900 hover:bg-zinc-900/20 ${overdue ? "text-red-300" : "text-zinc-100"}`}>
                        <td className="p-3">{p.challan_number}</td>
                        <td className="p-3">{p.job_worker_name}</td>
                        <td className="p-3">{p.product_name}</td>
                        <td className="p-3">{p.quantity_sent}</td>
                        <td className="p-3 text-green-500">{num(p.quantity_received)}</td>
                        <td className="p-3 font-bold text-primary">{num(p.quantity_pending)}</td>
                        <td className={`p-3 ${overdue ? "text-red-400 font-bold" : "text-zinc-400"}`}>{p.due_date || "—"}</td>
                        <td className={`p-3 font-mono ${overdue ? "text-red-400 font-bold" : critical ? "text-yellow-400" : "text-zinc-400"}`}>
                          {overdue ? "OVERDUE" : p.days_remaining !== null ? `${p.days_remaining}d` : "—"}
                          {p.deemed_supply && <div className="text-[9px] text-red-400 uppercase">Deemed Supply</div>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── ITC-04 Tab ────────────────────────────────────────────────────────── */}
      {tab === "itc04" && (
        <div className="space-y-4">
          <div className="flex items-end gap-4">
            <div>
              <label className="block font-mono text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Period (MMYYYY)</label>
              <input
                value={itc04Period}
                onChange={e => setItc04Period(e.target.value)}
                placeholder="e.g. 062025"
                maxLength={6}
                className="bg-background border border-input text-foreground text-xs px-3 py-2 focus:outline-none focus:border-primary w-36 transition-colors"
              />
            </div>
            <PrimaryButton onClick={() => loadItc04(itc04Period)}>Generate ITC-04</PrimaryButton>
          </div>

          {itc04 && (
            <div className="space-y-6">
              {/* Summary */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                  { label: "Challans Issued", value: itc04.summary.total_challans_issued },
                  { label: "Receipts Received", value: itc04.summary.total_receipts },
                  { label: "Taxable Value Sent", value: `₹${inr(itc04.summary.total_taxable_value_sent)}` },
                  { label: "Overdue Challans", value: itc04.summary.overdue_challans, danger: itc04.summary.overdue_challans > 0 },
                ].map(s => (
                  <div key={s.label} className="bg-card border border-border p-4 rounded-md text-card-foreground">
                    <div className={`font-mono font-black text-2xl ${s.danger ? "text-red-400" : "text-foreground"}`}>{s.value}</div>
                    <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground mt-1">{s.label}</div>
                  </div>
                ))}
              </div>

              {/* Table 4 */}
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                  Table 4 — Goods Dispatched to Job Worker ({itc04.period_label})
                </div>
                <div className="border border-border bg-card overflow-x-auto rounded-md">
                  <table className="w-full text-xs font-mono">
                    <thead>
                      <tr className="border-b border-border bg-muted/50 text-muted-foreground">
                        <th className="p-3 text-left uppercase">Challan No</th>
                        <th className="p-3 text-left uppercase">Date</th>
                        <th className="p-3 text-left uppercase">Due Date</th>
                        <th className="p-3 text-left uppercase">Job Worker</th>
                        <th className="p-3 text-left uppercase">Product</th>
                        <th className="p-3 text-right uppercase">Qty Sent</th>
                        <th className="p-3 text-right uppercase">Taxable Value</th>
                        <th className="p-3 text-left uppercase">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {itc04.table4_outward_challans.length === 0 && (
                        <tr><td colSpan={8} className="p-6 text-center text-muted-foreground">No outward challans in this period</td></tr>
                      )}
                      {itc04.table4_outward_challans.map((row, i) => (
                        <tr key={i} className={`border-b border-border hover:bg-muted/20 ${row.is_overdue ? "text-red-300" : "text-foreground"}`}>
                          <td className="p-3 font-bold text-primary">{row.challan_number}</td>
                          <td className="p-3">{row.challan_date}</td>
                          <td className={`p-3 ${row.is_overdue ? "text-red-400 font-bold" : "text-muted-foreground"}`}>{row.due_date || "—"}</td>
                          <td className="p-3">{row.job_worker_name}</td>
                          <td className="p-3">{row.product_name}</td>
                          <td className="p-3 text-right">{num(row.quantity_sent, 4)} {row.unit}</td>
                          <td className="p-3 text-right">₹{inr(row.taxable_value)}</td>
                          <td className="p-3">
                            <StatusBadge status={row.challan_status} />
                            {row.is_overdue && <span className="ml-1 text-[9px] text-red-400 uppercase border border-red-800 px-1">Deemed Supply</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Table 5 */}
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-2">
                  Table 5 — Goods Received Back from Job Worker ({itc04.period_label})
                </div>
                <div className="border border-border bg-card overflow-x-auto rounded-md">
                  <table className="w-full text-xs font-mono">
                    <thead>
                      <tr className="border-b border-border bg-muted/50 text-muted-foreground">
                        <th className="p-3 text-left uppercase">Receipt No</th>
                        <th className="p-3 text-left uppercase">Date</th>
                        <th className="p-3 text-left uppercase">Orig. Challan</th>
                        <th className="p-3 text-left uppercase">Job Worker</th>
                        <th className="p-3 text-left uppercase">Product</th>
                        <th className="p-3 text-right uppercase">Qty Received</th>
                        <th className="p-3 text-right uppercase">Scrap</th>
                      </tr>
                    </thead>
                    <tbody>
                      {itc04.table5_inward_receipts.length === 0 && (
                        <tr><td colSpan={7} className="p-6 text-center text-muted-foreground">No inward receipts in this period</td></tr>
                      )}
                      {itc04.table5_inward_receipts.map((row, i) => (
                        <tr key={i} className="border-b border-border hover:bg-muted/20 text-foreground">
                          <td className="p-3 font-bold text-green-500">{row.receipt_number}</td>
                          <td className="p-3">{row.receipt_date}</td>
                          <td className="p-3 text-muted-foreground">{row.original_challan_number}</td>
                          <td className="p-3">{row.job_worker_name}</td>
                          <td className="p-3">{row.product_name}</td>
                          <td className="p-3 text-right">{num(row.quantity_received, 4)} {row.unit}</td>
                          <td className="p-3 text-right text-muted-foreground">{row.scrap_quantity > 0 ? num(row.scrap_quantity, 4) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="text-muted-foreground font-mono text-[10px]">
                Note: ITC-04 must be filed quarterly. This report covers challans issued/received in {itc04.period_label}.
                Deemed supply arises when goods are not returned within the statutory window (365 days for inputs, 1095 days for capital goods).
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Modal: New Challan ─────────────────────────────────────────────────── */}
      <Modal open={isChallanModalOpen} onClose={() => setIsChallanModalOpen(false)} title="Generate Job Work Challan">
        <form onSubmit={handleCreateChallan} className="space-y-4">
          <Field label="Outsource Job Worker" required>
            <Select value={newChallan.job_worker_id} onChange={e => setNewChallan(p => ({ ...p, job_worker_id: e.target.value }))} required>
              <option value="">Select outsourced partner…</option>
              {suppliers.map(s => <option key={s.id} value={s.id}>{s.company ? `${s.company} (${s.name})` : s.name}</option>)}
            </Select>
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Challan Date" required>
              <Input type="date" value={newChallan.date} onChange={e => setNewChallan(p => ({ ...p, date: e.target.value }))} required />
            </Field>
            <Field label="Nature of Goods">
              <Select value={newChallan.nature} onChange={e => setNewChallan(p => ({ ...p, nature: e.target.value }))}>
                <option value="inputs">Inputs (1-yr window)</option>
                <option value="capital_goods">Capital Goods (3-yr window)</option>
              </Select>
            </Field>
          </div>

          <div className="space-y-3 pt-2">
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground block">Material Line Items</span>
            <div className="border border-border overflow-x-auto rounded-md">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-border bg-muted/40 text-muted-foreground">
                    <th className="p-2.5 uppercase font-semibold">Product</th>
                    <th className="p-2.5 uppercase font-semibold w-28 text-right">Quantity</th>
                    <th className="p-2.5 uppercase font-semibold w-28 text-right">Available</th>
                    <th className="p-2.5 uppercase font-semibold w-12 text-center">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {newChallan.items.map((item, idx) => {
                    const selectedProduct = !item.is_custom && products.find(p => p.id === item.product_id);
                    const availableQty = item.is_custom ? "—" : selectedProduct ? `${selectedProduct.quantity} ${selectedProduct.unit || "pcs"}` : "—";
                    const isOverStock = !item.is_custom && selectedProduct && parseFloat(item.quantity || 0) > parseFloat(selectedProduct.quantity || 0);

                    const toggleCustom = () => {
                      const updated = [...newChallan.items];
                      updated[idx] = { ...updated[idx], is_custom: !updated[idx].is_custom, product_id: "", product_name: "", sku: "" };
                      setNewChallan(p => ({ ...p, items: updated }));
                    };

                    return (
                      <tr key={idx} className="border-b border-border hover:bg-muted/10">
                        <td className="p-2">
                          {item.is_custom ? (
                            <Input
                              type="text"
                              value={item.product_name}
                              placeholder="Write product name…"
                              onChange={e => {
                                const updated = [...newChallan.items];
                                updated[idx].product_name = e.target.value;
                                setNewChallan(p => ({ ...p, items: updated }));
                              }}
                              required
                              className="h-9 py-1"
                            />
                          ) : (
                            <Select
                              value={item.product_id}
                              onChange={e => {
                                const updated = [...newChallan.items];
                                updated[idx].product_id = e.target.value;
                                setNewChallan(p => ({ ...p, items: updated }));
                              }}
                              required
                              className="h-9 py-1"
                            >
                              <option value="">Select product…</option>
                              {products.map(p => {
                                const isSelectedElsewhere = newChallan.items.some((it, i) => i !== idx && !it.is_custom && it.product_id === p.id);
                                return (
                                  <option key={p.id} value={p.id} disabled={isSelectedElsewhere}>
                                    {p.name} ({p.sku})
                                  </option>
                                );
                              })}
                            </Select>
                          )}
                          <button
                            type="button"
                            onClick={toggleCustom}
                            className="mt-1 font-mono text-[10px] uppercase tracking-wider text-primary hover:underline"
                          >
                            {item.is_custom ? "Pick from list" : "Write manually"}
                          </button>
                        </td>
                        <td className="p-2 text-right">
                          <Input
                            type="number"
                            value={item.quantity}
                            onChange={e => {
                              const updated = [...newChallan.items];
                              updated[idx].quantity = e.target.value;
                              setNewChallan(p => ({ ...p, items: updated }));
                            }}
                            min="0.001"
                            step="any"
                            required
                            className={`h-9 py-1 text-right ${isOverStock ? "border-red-500 focus:border-red-500 focus:ring-red-500 text-red-400" : ""}`}
                          />
                        </td>
                        <td className={`p-2 text-right tabular text-xs font-semibold ${isOverStock ? "text-red-400" : "text-muted-foreground"}`}>
                          {availableQty}
                          {isOverStock && <div className="text-[9px] text-red-500 uppercase mt-0.5">Over Stock</div>}
                        </td>
                        <td className="p-2 text-center">
                          <button
                            type="button"
                            onClick={() => {
                              if (newChallan.items.length > 1) {
                                setNewChallan(p => ({ ...p, items: p.items.filter((_, i) => i !== idx) }));
                              } else {
                                toast.warning("Challan must contain at least one item.");
                              }
                            }}
                            className="w-8 h-8 border border-border text-red-400 hover:border-red-500 hover:text-red-300 transition-colors flex items-center justify-center mx-auto bg-background"
                            style={{ borderRadius: "var(--radius)" }}
                            title="Delete Row"
                          >
                            <Trash2 className="w-3.5 h-3.5 text-red-400" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <SecondaryButton
              icon={Plus}
              onClick={() => setNewChallan(p => ({ ...p, items: [...p.items, { product_id: "", quantity: 1, sku: "", product_name: "", is_custom: false }] }))}
            >
              + Add Product
            </SecondaryButton>
          </div>

          <Field label="Notes">
            <Textarea value={newChallan.notes} onChange={e => setNewChallan(p => ({ ...p, notes: e.target.value }))} placeholder="e.g. Galvanizing, fabrication instructions" rows={2} />
          </Field>

          <div className="flex justify-end gap-2 pt-4">
            <SecondaryButton onClick={() => setIsChallanModalOpen(false)}>CANCEL</SecondaryButton>
            <PrimaryButton type="submit">GENERATE CHALLAN</PrimaryButton>
          </div>
        </form>
      </Modal>

      {/* ── Modal: Record Receipt ──────────────────────────────────────────────── */}
      <Modal open={isReceiptModalOpen} onClose={() => setIsReceiptModalOpen(false)} title="Record Material Inward Receipt">
        {selectedChallan && (
          <form onSubmit={handleCreateReceipt} className="space-y-4">
            <div className="font-mono text-xs text-muted-foreground">
              From: <span className="text-foreground font-bold">{selectedChallan.job_worker_name}</span>
              {" · "}Challan: <span className="text-foreground font-bold">{selectedChallan.challan_number}</span>
              {selectedChallan.is_overdue && (
                <div className="mt-1 flex items-center gap-1 text-red-400 text-[10px]">
                  <AlertTriangle className="w-3 h-3" /> This challan is overdue — deemed supply provisions may apply.
                </div>
              )}
            </div>

            <Field label="Inward Date" required>
              <Input type="date" value={newReceipt.date} onChange={e => setNewReceipt(p => ({ ...p, date: e.target.value }))} required />
            </Field>

            <div className="space-y-3">
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground block">Receive Quantities</span>
              {newReceipt.items.map((item, idx) => (
                <div key={idx} className="bg-card p-3 border border-border space-y-2 text-card-foreground">
                  <div className="font-bold text-foreground">{item.product_name} ({item.sku})</div>
                  <div className="grid grid-cols-4 gap-2">
                    <Field label="Sent"><Input value={item.quantity_sent} disabled readOnly /></Field>
                    <Field label="Already Recv"><Input value={item.quantity_already_received || 0} disabled readOnly /></Field>
                    <Field label="Received Qty" required>
                      <Input type="number" value={item.quantity_received}
                        onChange={e => {
                          const updated = [...newReceipt.items];
                          updated[idx].quantity_received = e.target.value === "" ? "" : parseFloat(e.target.value);
                          setNewReceipt(p => ({ ...p, items: updated }));
                        }} max={item.quantity_pending} min="0" step="any" required />
                    </Field>
                    <Field label="Scrap Qty">
                      <Input type="number" value={item.scrap_quantity}
                        onChange={e => {
                          const updated = [...newReceipt.items];
                          updated[idx].scrap_quantity = e.target.value === "" ? 0 : parseFloat(e.target.value);
                          setNewReceipt(p => ({ ...p, items: updated }));
                        }} min="0" step="any" />
                    </Field>
                  </div>
                </div>
              ))}
            </div>

            <Field label="Remarks">
              <Textarea value={newReceipt.notes} onChange={e => setNewReceipt(p => ({ ...p, notes: e.target.value }))} placeholder="Damage, delivery notes, etc." rows={2} />
            </Field>

            <div className="flex justify-end gap-2 pt-4">
              <SecondaryButton onClick={() => setIsReceiptModalOpen(false)}>CANCEL</SecondaryButton>
              <PrimaryButton type="submit">LOG RECEIPT RETURN</PrimaryButton>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
