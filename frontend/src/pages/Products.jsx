import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import QRCode from "react-qr-code";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  StatTile,
  PrimaryButton,
  SecondaryButton,
  Input,
  Select,
  Textarea,
  Field,
  EmptyState,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import ImageUploader, { useImageBlob } from "@/components/ImageUploader";
import { Plus, Search, Pencil, Trash2, QrCode, AlertTriangle, RefreshCw, CheckCircle, Calendar } from "lucide-react";

const TABS = [
  { id: "catalog", label: "Catalog" },
  { id: "aging", label: "Inventory Aging" },
  { id: "valuation", label: "Stock Valuation" },
  { id: "reorder", label: "Reorder suggestions" },
  { id: "verification", label: "Physical Verification" },
  { id: "batches", label: "Batch & Expiry" },
];

const blank = {
  name: "",
  sku: "",
  category: "Cuplock",
  description: "",
  unit: "pcs",
  cost_price: 0,
  selling_price: 0,
  quantity: 0,
  low_stock_threshold: 10,
  warehouse_id: "",
  image_url: "",
  image_path: "",
  hsn_code: "",
  gst_rate: 18,
};

function ProductImageThumb({ product }) {
  const src = useImageBlob(product.image_path || product.image_url);
  if (src) {
    return (
      <img
        src={src}
        alt=""
        className="w-10 h-10 object-cover border border-zinc-800"
      />
    );
  }
  return <div className="w-10 h-10 hazard-stripe opacity-40" />;
}

export default function Products() {
  const [params] = useSearchParams();
  const [items, setItems] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [q, setQ] = useState("");
  const [lowOnly, setLowOnly] = useState(params.get("low") === "1");
  const [open, setOpen] = useState(false);
  const [qrItem, setQrItem] = useState(null);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);

  // New stock analysis tabs state
  const [tab, setTab] = useState("catalog");
  const [agingData, setAgingData] = useState(null);
  const [agingDays, setAgingDays] = useState(90);
  const [valuationData, setValuationData] = useState(null);
  const [valuationMethod, setValuationMethod] = useState("WEIGHTED_AVERAGE");
  const [reorderData, setReorderData] = useState(null);
  const [verifications, setVerifications] = useState([]);
  const [showPvModal, setShowPvModal] = useState(false);
  const [pvForm, setPvForm] = useState({
    verification_date: new Date().toISOString().split("T")[0],
    verified_by: "",
    warehouse_id: "",
    notes: "",
    items: [],
  });
  const [batches, setBatches] = useState([]);
  const [showBatchModal, setShowBatchModal] = useState(false);
  const [batchForm, setBatchForm] = useState({
    product_id: "",
    batch_number: "",
    manufacture_date: "",
    expiry_date: "",
    quantity: 0,
    unit_cost: 0,
    warehouse_id: "",
  });

  const load = async () => {
    const r = await api.get("/products", { params: { q, low_stock: lowOnly } });
    setItems(r.data);
  };
  const loadWh = async () => {
    const r = await api.get("/warehouses");
    setWarehouses(r.data);
  };

  const loadAging = async () => {
    try {
      const r = await api.get("/stock/aging", { params: { days_threshold: agingDays } });
      setAgingData(r.data);
    } catch (e) {
      toast.error("Failed to load aging analysis");
    }
  };

  const loadValuation = async () => {
    try {
      const r = await api.get("/stock/valuation", { params: { method: valuationMethod } });
      setValuationData(r.data);
    } catch (e) {
      toast.error("Failed to load valuation report");
    }
  };

  const loadReorder = async () => {
    try {
      const r = await api.get("/stock/reorder-suggestions");
      setReorderData(r.data);
    } catch (e) {
      toast.error("Failed to load reorder suggestions");
    }
  };

  const loadVerifications = async () => {
    try {
      const r = await api.get("/stock/physical-verifications");
      setVerifications(r.data || []);
    } catch (e) {
      toast.error("Failed to load physical verifications");
    }
  };

  const loadBatches = async () => {
    try {
      const r = await api.get("/stock/batches");
      setBatches(r.data || []);
    } catch (e) {
      toast.error("Failed to load batch list");
    }
  };

  useEffect(() => {
    if (tab === "catalog") load();
    else if (tab === "aging") loadAging();
    else if (tab === "valuation") loadValuation();
    else if (tab === "reorder") loadReorder();
    else if (tab === "verification") loadVerifications();
    else if (tab === "batches") loadBatches();
  }, [tab, agingDays, valuationMethod, q, lowOnly]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    loadWh();
  }, []);

  const startNew = () => {
    setForm(blank);
    setEditingId(null);
    setOpen(true);
  };
  const startEdit = (item) => {
    setForm({ ...blank, ...item });
    setEditingId(item.id);
    setOpen(true);
  };

  const submit = async (e) => {
    e.preventDefault();
    const payload = {
      ...form,
      cost_price: Number(form.cost_price),
      selling_price: Number(form.selling_price),
      quantity: Number(form.quantity),
      low_stock_threshold: Number(form.low_stock_threshold),
      gst_rate: Number(form.gst_rate),
      warehouse_id: form.warehouse_id || null,
    };
    try {
      if (editingId) {
        await api.put(`/products/${editingId}`, payload);
        toast.success("Product updated");
      } else {
        await api.post("/products", payload);
        toast.success("Product created");
      }
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const onDelete = async (item) => {
    if (!window.confirm(`Delete ${item.name}?`)) return;
    try {
      await api.delete(`/products/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const startPv = () => {
    const itemsList = items.map(p => ({
      product_id: p.id,
      product_name: p.name,
      sku: p.sku,
      system_quantity: p.quantity,
      physical_quantity: p.quantity,
      remarks: "",
    }));
    setPvForm({
      verification_date: new Date().toISOString().split("T")[0],
      verified_by: "",
      warehouse_id: warehouses[0]?.id || "",
      notes: "",
      items: itemsList,
    });
    setShowPvModal(true);
  };

  const submitPv = async (e) => {
    e.preventDefault();
    try {
      await api.post("/stock/physical-verifications", pvForm);
      toast.success("Physical verification recorded as Draft");
      setShowPvModal(false);
      loadVerifications();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to submit verification");
    }
  };

  const approvePv = async (id) => {
    try {
      await api.post(`/stock/physical-verifications/${id}/approve`);
      toast.success("Verification approved and stock levels adjusted!");
      loadVerifications();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Approval failed");
    }
  };

  const startBatch = () => {
    setBatchForm({
      product_id: items[0]?.id || "",
      batch_number: "",
      manufacture_date: new Date().toISOString().split("T")[0],
      expiry_date: new Date().toISOString().split("T")[0],
      quantity: 0,
      unit_cost: 0,
      warehouse_id: warehouses[0]?.id || "",
    });
    setShowBatchModal(true);
  };

  const submitBatch = async (e) => {
    e.preventDefault();
    try {
      const selectedProd = items.find(p => p.id === batchForm.product_id);
      await api.post("/stock/batches", {
        ...batchForm,
        product_name: selectedProd ? selectedProd.name : "",
        sku: selectedProd ? selectedProd.sku : "",
        quantity: parseFloat(batchForm.quantity),
        unit_cost: parseFloat(batchForm.unit_cost),
      });
      toast.success("Batch created successfully");
      setShowBatchModal(false);
      loadBatches();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to create batch");
    }
  };

  const onDeleteBatch = async (batchId) => {
    if (!window.confirm("Are you sure you want to delete this batch?")) return;
    try {
      await api.delete(`/stock/batches/${batchId}`);
      toast.success("Batch deleted");
      loadBatches();
    } catch (err) {
      toast.error("Failed to delete batch");
    }
  };

  return (
    <div data-testid="products-page">
      <PageHeader
        eyebrow="Inventory"
        title="Products & Stock Analysis"
        description="Master catalog, stock aging, valuation methods, physical audit and batch tracking."
        actions={
          <>
            {tab === "catalog" && (
              <PrimaryButton testid="new-product-btn" onClick={startNew} icon={Plus}>
                New product
              </PrimaryButton>
            )}
            {tab === "verification" && (
              <PrimaryButton onClick={startPv} icon={Plus}>
                Record Audit
              </PrimaryButton>
            )}
            {tab === "batches" && (
              <PrimaryButton onClick={startBatch} icon={Plus}>
                New Batch
              </PrimaryButton>
            )}
          </>
        }
      />

      {/* Tabs */}
      <div className="flex gap-px bg-zinc-800 border border-zinc-800 mb-6 overflow-x-auto">
        {TABS.map(t => (
          <button key={t.id} data-testid={`tab-${t.id}`} onClick={() => setTab(t.id)}
            className={`flex-shrink-0 px-4 py-3 text-xs font-mono uppercase tracking-wider transition-colors ${
              tab === t.id ? "bg-yellow-400 text-black font-bold" : "bg-zinc-950 text-zinc-400 hover:text-white hover:bg-zinc-900"
            }`}>{t.label}</button>
        ))}
      </div>

      {tab === "catalog" && (
        <>
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <div className="relative flex-1 min-w-[200px] max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
              <Input
                data-testid="search-products"
                placeholder="Search by name, SKU or category"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                className="pl-9"
              />
            </div>
            <button
              data-testid="filter-low-stock"
              onClick={() => setLowOnly((v) => !v)}
              className={`px-3 py-2 border text-xs font-mono uppercase tracking-wider transition-colors ${
                lowOnly
                  ? "bg-yellow-400 text-black border-yellow-400"
                  : "border-zinc-700 text-zinc-300 hover:border-yellow-400"
              }`}
            >
              <AlertTriangle className="inline w-3.5 h-3.5 mr-1" /> Low stock only
            </button>
          </div>

          {items.length === 0 ? (
            <EmptyState
              message="No products yet"
              action={
                <PrimaryButton onClick={startNew} icon={Plus}>
                  Add first product
                </PrimaryButton>
              }
            />
          ) : (
            <div className="border border-zinc-800 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-zinc-900">
                  <tr className="text-left label-overline">
                    <th className="px-3 py-2.5">Product</th>
                    <th className="px-3 py-2.5">SKU</th>
                    <th className="px-3 py-2.5">Category</th>
                    <th className="px-3 py-2.5">Warehouse</th>
                    <th className="px-3 py-2.5 text-right">Qty</th>
                    <th className="px-3 py-2.5 text-right">Cost</th>
                    <th className="px-3 py-2.5 text-right">Sell</th>
                    <th className="px-3 py-2.5">GST</th>
                    <th className="px-3 py-2.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((p, i) => {
                    const low =
                      Number(p.quantity) <= Number(p.low_stock_threshold || 0);
                    return (
                      <tr
                        key={p.id}
                        data-testid={`product-row-${p.sku}`}
                        className={`border-t border-zinc-900 hover:bg-zinc-900/60 ${
                          i % 2 === 0 ? "bg-transparent" : "bg-zinc-900/30"
                        }`}
                      >
                        <td className="px-3 py-2.5 text-white">
                          <div className="flex items-center gap-3">
                            <ProductImageThumb product={p} />
                            <div>
                              <div className="text-white">{p.name}</div>
                              <div className="text-xs text-zinc-500">{p.unit}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-3 py-2.5 font-mono text-yellow-400 text-xs">
                          {p.sku}
                        </td>
                        <td className="px-3 py-2.5 text-zinc-300">{p.category}</td>
                        <td className="px-3 py-2.5 text-zinc-400">
                          {p.warehouse_name || "-"}
                        </td>
                        <td
                          className={`px-3 py-2.5 text-right tabular ${
                            low ? "text-red-400 font-semibold" : "text-white"
                          }`}
                        >
                          {p.quantity}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular text-zinc-300">
                          ₹{Number(p.cost_price).toLocaleString("en-IN")}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular text-yellow-400 font-semibold">
                          ₹{Number(p.selling_price).toLocaleString("en-IN")}
                        </td>
                        <td className="px-3 py-2.5 text-zinc-400 font-mono text-xs">
                          {p.gst_rate}%
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          <div className="inline-flex gap-1">
                            <button
                              data-testid={`qr-${p.sku}`}
                              onClick={() => setQrItem(p)}
                              className="w-7 h-7 border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center"
                            >
                              <QrCode className="w-3.5 h-3.5" />
                            </button>
                            <button
                              data-testid={`edit-${p.sku}`}
                              onClick={() => startEdit(p)}
                              className="w-7 h-7 border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center"
                            >
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                            <button
                              data-testid={`delete-${p.sku}`}
                              onClick={() => onDelete(p)}
                              className="w-7 h-7 border border-zinc-800 hover:border-red-500 hover:text-red-400 text-zinc-400 flex items-center justify-center"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Stock Aging Analysis */}
      {tab === "aging" && agingData && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 bg-zinc-950 border border-zinc-850 p-4">
            <span className="label-overline">Aging Threshold (Days)</span>
            <Select value={agingDays} onChange={e => setAgingDays(parseInt(e.target.value))} className="w-28">
              <option value={30}>30 Days</option>
              <option value={60}>60 Days</option>
              <option value={90}>90 Days</option>
              <option value={180}>180 Days</option>
            </Select>
            <span className="text-xs text-zinc-500 italic">Identifies stock with no sales/dispatches in this period.</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <StatTile label="Total Items Checked" value={agingData.total_products} />
            <StatTile label="Slow Moving Items" value={agingData.slow_moving_count} accent={agingData.slow_moving_count > 0} />
            <StatTile label="Total Stock Value" value={`₹${Number(agingData.total_stock_value).toLocaleString("en-IN")}`} />
            <StatTile label="Slow Moving Value" value={`₹${Number(agingData.items?.filter(x => x.is_slow_moving).reduce((s, x) => s + x.stock_value, 0)).toLocaleString("en-IN")}`} />
          </div>

          <div className="border border-zinc-800 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900 label-overline">
                <tr>
                  <th className="px-3 py-2 text-left">Product Name</th>
                  <th className="px-3 py-2 text-left">SKU</th>
                  <th className="px-3 py-2 text-right">Quantity</th>
                  <th className="px-3 py-2 text-right">Unit Price</th>
                  <th className="px-3 py-2 text-right">Stock Value</th>
                  <th className="px-3 py-2 text-left">Last Movement</th>
                  <th className="px-3 py-2 text-right">Days Idle</th>
                  <th className="px-3 py-2 text-center">Status</th>
                </tr>
              </thead>
              <tbody>
                {agingData.items?.map((item, idx) => (
                  <tr key={item.product_id} className={`border-t border-zinc-900 hover:bg-zinc-900/60 ${idx % 2 === 0 ? "" : "bg-zinc-900/30"}`}>
                    <td className="px-3 py-2 text-white font-semibold text-left">{item.name}</td>
                    <td className="px-3 py-2 font-mono text-xs text-yellow-400 text-left">{item.sku}</td>
                    <td className="px-3 py-2 text-right tabular text-zinc-300">{item.quantity} {item.unit}</td>
                    <td className="px-3 py-2 text-right tabular text-zinc-400">₹{Number(item.cost_price).toLocaleString("en-IN")}</td>
                    <td className="px-3 py-2 text-right tabular text-zinc-200">₹{Number(item.stock_value).toLocaleString("en-IN")}</td>
                    <td className="px-3 py-2 font-mono text-xs text-zinc-500 text-left">{item.last_movement || "No movement"}</td>
                    <td className="px-3 py-2 text-right tabular text-zinc-300">{item.days_since_movement} days</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                        item.is_slow_moving ? "border-red-800 text-red-400 bg-red-950/20 font-bold" : "border-green-800 text-green-400 bg-green-950/20"
                      }`}>{item.is_slow_moving ? "SLOW MOVING" : "ACTIVE"}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Stock Valuation */}
      {tab === "valuation" && valuationData && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 bg-zinc-950 border border-zinc-850 p-4">
            <span className="label-overline">Valuation Method</span>
            <Select value={valuationMethod} onChange={e => setValuationMethod(e.target.value)} className="w-48">
              <option value="WEIGHTED_AVERAGE">Weighted Average (Avg Cost)</option>
              <option value="FIFO">First In, First Out (FIFO)</option>
            </Select>
            <span className="text-xs text-zinc-500 italic">Select method to compute total inventory assets valuation.</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <StatTile label="Total Products" value={valuationData.total_products} />
            <StatTile label="Valuation Method" value={valuationData.method} />
            <StatTile label="Total Valued Assets" value={`₹${Number(valuationData.total_value).toLocaleString("en-IN")}`} accent />
          </div>

          <div className="border border-zinc-800 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900 label-overline">
                <tr>
                  <th className="px-3 py-2 text-left">Product Name</th>
                  <th className="px-3 py-2 text-left">SKU</th>
                  <th className="px-3 py-2 text-left">Category</th>
                  <th className="px-3 py-2 text-right">In-Stock Quantity</th>
                  <th className="px-3 py-2 text-right">Valuation Cost</th>
                  <th className="px-3 py-2 text-right">Selling Price</th>
                  <th className="px-3 py-2 text-right">Total Asset Value</th>
                </tr>
              </thead>
              <tbody>
                {valuationData.items?.map((item, idx) => (
                  <tr key={item.product_id} className={`border-t border-zinc-900 hover:bg-zinc-900/60 ${idx % 2 === 0 ? "" : "bg-zinc-900/30"}`}>
                    <td className="px-3 py-2 text-white font-semibold text-left">{item.name}</td>
                    <td className="px-3 py-2 font-mono text-xs text-yellow-400 text-left">{item.sku}</td>
                    <td className="px-3 py-2 text-zinc-400 text-left">{item.category}</td>
                    <td className="px-3 py-2 text-right tabular text-zinc-300">{item.quantity} {item.unit}</td>
                    <td className="px-3 py-2 text-right tabular text-zinc-200">₹{Number(item.unit_cost).toLocaleString("en-IN")}</td>
                    <td className="px-3 py-2 text-right tabular text-yellow-500 font-semibold">₹{Number(item.selling_price).toLocaleString("en-IN")}</td>
                    <td className="px-3 py-2 text-right tabular text-green-400 font-bold">₹{Number(item.total_value).toLocaleString("en-IN")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Reorder suggestions */}
      {tab === "reorder" && reorderData && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <StatTile label="Products Needing Reorder" value={reorderData.total_items} accent={reorderData.total_items > 0} />
            <StatTile label="Total Reorder Cost" value={`₹${Number(reorderData.total_estimated_cost).toLocaleString("en-IN")}`} />
          </div>

          <div className="border border-zinc-800 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900 label-overline">
                <tr>
                  <th className="px-3 py-2 text-left">Product Name</th>
                  <th className="px-3 py-2 text-left">SKU</th>
                  <th className="px-3 py-2 text-right">Current Qty</th>
                  <th className="px-3 py-2 text-right">Reorder Level</th>
                  <th className="px-3 py-2 text-right">Shortage</th>
                  <th className="px-3 py-2 text-right">Suggested Order Qty</th>
                  <th className="px-3 py-2 text-right">Estimated Cost</th>
                  <th className="px-3 py-2 text-left">Preferred Supplier</th>
                </tr>
              </thead>
              <tbody>
                {reorderData.items?.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-zinc-650 font-mono">All products are above their reorder thresholds.</td>
                  </tr>
                )}
                {reorderData.items?.map((item, idx) => (
                  <tr key={item.product_id} className={`border-t border-zinc-900 hover:bg-zinc-900/60 ${idx % 2 === 0 ? "" : "bg-zinc-900/30"}`}>
                    <td className="px-3 py-2 text-white font-semibold text-left">{item.name}</td>
                    <td className="px-3 py-2 font-mono text-xs text-yellow-400 text-left">{item.sku}</td>
                    <td className="px-3 py-2 text-right tabular text-red-400 font-bold">{item.current_quantity} {item.unit}</td>
                    <td className="px-3 py-2 text-right tabular text-zinc-400">{item.reorder_level}</td>
                    <td className="px-3 py-2 text-right tabular text-red-500 font-extrabold">{item.shortage}</td>
                    <td className="px-3 py-2 text-right tabular text-green-400 font-bold">{item.suggested_order_qty}</td>
                    <td className="px-3 py-2 text-right tabular text-zinc-200">₹{Number(item.estimated_cost).toLocaleString("en-IN")}</td>
                    <td className="px-3 py-2 text-zinc-300 font-semibold text-left">{item.preferred_supplier || "None"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Physical Verification Audit */}
      {tab === "verification" && (
        <div className="space-y-4">
          <div className="bg-zinc-950 border border-zinc-800 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900 label-overline">
                <tr>
                  <th className="px-3 py-2 text-left">Verification Date</th>
                  <th className="px-3 py-2 text-left">Verified By</th>
                  <th className="px-3 py-2 text-right">Items Checked</th>
                  <th className="px-3 py-2 text-right">Total Discrepancies</th>
                  <th className="px-3 py-2 text-left">Status</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {verifications.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-zinc-650 font-mono">No stock verification records.</td>
                  </tr>
                )}
                {verifications.map((v, idx) => (
                  <tr key={v.id} className={`border-t border-zinc-900 hover:bg-zinc-900/60 ${idx % 2 === 0 ? "" : "bg-zinc-900/30"}`}>
                    <td className="px-3 py-2 font-mono text-zinc-300 text-left">{v.verification_date}</td>
                    <td className="px-3 py-2 text-white font-bold text-left">{v.created_by_name || v.verified_by}</td>
                    <td className="px-3 py-2 text-right tabular text-zinc-400">{v.items_checked}</td>
                    <td className={`px-3 py-2 text-right tabular ${v.total_discrepancy > 0 ? "text-yellow-400 font-bold" : "text-zinc-500"}`}>
                      {v.total_discrepancy}
                    </td>
                    <td className="px-3 py-2 text-left">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                        v.status === "APPROVED" ? "border-green-800 text-green-400 bg-green-950/20" : "border-yellow-800 text-yellow-400 bg-yellow-950/20"
                      }`}>{v.status}</span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      {v.status === "DRAFT" && (
                        <button onClick={() => approvePv(v.id)} className="bg-green-600 hover:bg-green-700 text-white text-xs font-mono font-bold px-2.5 py-1 uppercase transition-colors">
                          Approve & Adjust
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Batch & Expiry Tracking */}
      {tab === "batches" && (
        <div className="space-y-4">
          <div className="bg-zinc-950 border border-zinc-800 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900 label-overline">
                <tr>
                  <th className="px-3 py-2 text-left">Product</th>
                  <th className="px-3 py-2 text-left">SKU</th>
                  <th className="px-3 py-2 text-left">Batch Number</th>
                  <th className="px-3 py-2 text-right">Quantity</th>
                  <th className="px-3 py-2 text-left">Manufactured</th>
                  <th className="px-3 py-2 text-left">Expiry</th>
                  <th className="px-3 py-2 text-center">Status</th>
                  <th className="px-3 py-2 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {batches.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-zinc-650 font-mono">No batch tracks loaded.</td>
                  </tr>
                )}
                {batches.map((b, idx) => (
                  <tr key={b.id} className={`border-t border-zinc-900 hover:bg-zinc-900/60 ${idx % 2 === 0 ? "" : "bg-zinc-900/30"}`}>
                    <td className="px-3 py-2 text-white font-bold text-left">{b.product_name}</td>
                    <td className="px-3 py-2 font-mono text-xs text-yellow-400 text-left">{b.sku}</td>
                    <td className="px-3 py-2 font-mono text-zinc-300 text-left">{b.batch_number}</td>
                    <td className="px-3 py-2 text-right tabular text-zinc-300">{b.quantity}</td>
                    <td className="px-3 py-2 font-mono text-zinc-500 text-xs text-left">{b.manufacture_date || "—"}</td>
                    <td className="px-3 py-2 font-mono text-red-400 text-xs font-semibold text-left">{b.expiry_date || "—"}</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                        b.expiry_status === "GOOD" ? "border-green-800 text-green-400 bg-green-950/20" :
                        b.expiry_status === "NEAR_EXPIRY" ? "border-yellow-800 text-yellow-400 bg-yellow-950/20 font-bold" :
                        "border-red-800 text-red-400 bg-red-950/20 font-black"
                      }`}>{b.expiry_status || "GOOD"}</span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button onClick={() => onDeleteBatch(b.id)} className="text-red-500 hover:text-red-300 text-xs">
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editingId ? "Edit Product" : "New Product"}
        size="lg"
        testid="product-modal"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton testid="save-product" onClick={submit}>
              Save Product
            </PrimaryButton>
          </>
        }
      >
        <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Product Name" required>
            <Input
              required
              data-testid="form-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="SKU" required>
            <Input
              required
              data-testid="form-sku"
              value={form.sku}
              onChange={(e) => setForm({ ...form, sku: e.target.value })}
            />
          </Field>
          <Field label="Category">
            <Select
              data-testid="form-category"
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            >
              {[
                "Cuplock",
                "Ringlock",
                "Frame",
                "Planks",
                "Accessories",
                "Couplers",
                "Other",
              ].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </Select>
          </Field>
          <Field label="Unit">
            <Input
              value={form.unit}
              onChange={(e) => setForm({ ...form, unit: e.target.value })}
            />
          </Field>
          <Field label="Warehouse">
            <Select
              value={form.warehouse_id || ""}
              onChange={(e) =>
                setForm({ ...form, warehouse_id: e.target.value })
              }
            >
              <option value="">— Unassigned —</option>
              {warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </Select>
          </Field>
          <div className="md:col-span-2">
            <Field label="Product Image">
              <ImageUploader
                value={form.image_path || form.image_url}
                onChange={(p) => setForm({ ...form, image_path: p, image_url: "" })}
              />
            </Field>
          </div>
          <Field label="Cost Price (₹)">
            <Input
              type="number"
              step="0.01"
              value={form.cost_price}
              onChange={(e) =>
                setForm({ ...form, cost_price: e.target.value })
              }
            />
          </Field>
          <Field label="Selling Price (₹)">
            <Input
              type="number"
              step="0.01"
              value={form.selling_price}
              onChange={(e) =>
                setForm({ ...form, selling_price: e.target.value })
              }
            />
          </Field>
          <Field label="Quantity">
            <Input
              type="number"
              step="0.01"
              value={form.quantity}
              onChange={(e) => setForm({ ...form, quantity: e.target.value })}
            />
          </Field>
          <Field label="Low Stock Threshold">
            <Input
              type="number"
              step="1"
              value={form.low_stock_threshold}
              onChange={(e) =>
                setForm({ ...form, low_stock_threshold: e.target.value })
              }
            />
          </Field>
          <Field label="HSN Code">
            <Input
              value={form.hsn_code || ""}
              onChange={(e) => setForm({ ...form, hsn_code: e.target.value })}
            />
          </Field>
          <Field label="GST Rate (%)">
            <Input
              type="number"
              step="0.01"
              value={form.gst_rate}
              onChange={(e) => setForm({ ...form, gst_rate: e.target.value })}
            />
          </Field>
          <div className="md:col-span-2">
            <Field label="Description">
              <Textarea
                rows={3}
                value={form.description || ""}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
              />
            </Field>
          </div>
        </form>
      </Modal>

      {/* Physical Stock Verification Modal */}
      <Modal
        open={showPvModal}
        onClose={() => setShowPvModal(false)}
        title="Physical Stock Audit / Verification"
        size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setShowPvModal(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submitPv}>Record Audit</PrimaryButton>
          </>
        }
      >
        <form onSubmit={submitPv} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Verification Date" required>
              <Input type="date" required value={pvForm.verification_date} onChange={e => setPvForm(f => ({ ...f, verification_date: e.target.value }))} />
            </Field>
            <Field label="Verified By / Inspector" required>
              <Input required placeholder="Your name or employee code" value={pvForm.verified_by} onChange={e => setPvForm(f => ({ ...f, verified_by: e.target.value }))} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Warehouse">
              <Select value={pvForm.warehouse_id} onChange={e => setPvForm(f => ({ ...f, warehouse_id: e.target.value }))}>
                {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </Select>
            </Field>
            <Field label="Audit Notes / General Remarks">
              <Input placeholder="General inspection conditions, weather, etc." value={pvForm.notes || ""} onChange={e => setPvForm(f => ({ ...f, notes: e.target.value }))} />
            </Field>
          </div>

          <div className="border border-zinc-800 max-h-[300px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-zinc-900 sticky top-0 label-overline">
                <tr>
                  <th className="px-3 py-2 text-left">Product Name</th>
                  <th className="px-3 py-2 text-left">SKU</th>
                  <th className="px-3 py-2 text-right">System Qty</th>
                  <th className="px-3 py-2 text-right">Physical Qty</th>
                  <th className="px-3 py-2 text-left">Audit Remarks</th>
                </tr>
              </thead>
              <tbody>
                {pvForm.items?.map((item, idx) => (
                  <tr key={item.product_id} className="border-t border-zinc-900">
                    <td className="px-3 py-1.5 text-zinc-300 text-left">{item.product_name}</td>
                    <td className="px-3 py-1.5 font-mono text-zinc-500 text-left">{item.sku}</td>
                    <td className="px-3 py-1.5 text-right tabular text-zinc-500">{item.system_quantity}</td>
                    <td className="px-3 py-1.5 text-right pr-1">
                      <input
                        type="number"
                        step="0.001"
                        value={item.physical_quantity}
                        onChange={e => {
                          const val = parseFloat(e.target.value) || 0;
                          setPvForm(f => {
                            const newItems = [...f.items];
                            newItems[idx] = { ...newItems[idx], physical_quantity: val };
                            return { ...f, items: newItems };
                          });
                        }}
                        className="w-20 bg-zinc-900 border border-zinc-700 text-right text-xs px-2 py-1 text-white focus:outline-none focus:border-yellow-400"
                      />
                    </td>
                    <td className="px-3 py-1.5">
                      <input
                        type="text"
                        value={item.remarks || ""}
                        onChange={e => {
                          const val = e.target.value;
                          setPvForm(f => {
                            const newItems = [...f.items];
                            newItems[idx] = { ...newItems[idx], remarks: val };
                            return { ...f, items: newItems };
                          });
                        }}
                        placeholder="e.g. Broken packaging"
                        className="w-full bg-zinc-900 border border-zinc-800 text-xs px-2 py-1 text-zinc-300 focus:outline-none focus:border-yellow-400"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </form>
      </Modal>

      {/* Batch & Expiry Creation Modal */}
      <Modal
        open={showBatchModal}
        onClose={() => setShowBatchModal(false)}
        title="Record Batch Track Entry"
        size="md"
        footer={
          <>
            <SecondaryButton onClick={() => setShowBatchModal(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submitBatch}>Record Batch</PrimaryButton>
          </>
        }
      >
        <form onSubmit={submitBatch} className="space-y-4">
          <Field label="Select Product" required>
            <Select value={batchForm.product_id} onChange={e => setBatchForm(f => ({ ...f, product_id: e.target.value }))}>
              {items.map(p => <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>)}
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Batch Number" required>
              <Input required placeholder="e.g. BATCH-2026A" value={batchForm.batch_number} onChange={e => setBatchForm(f => ({ ...f, batch_number: e.target.value }))} />
            </Field>
            <Field label="Warehouse">
              <Select value={batchForm.warehouse_id} onChange={e => setBatchForm(f => ({ ...f, warehouse_id: e.target.value }))}>
                {warehouses.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Manufacture Date">
              <Input type="date" value={batchForm.manufacture_date} onChange={e => setBatchForm(f => ({ ...f, manufacture_date: e.target.value }))} />
            </Field>
            <Field label="Expiry Date">
              <Input type="date" value={batchForm.expiry_date} onChange={e => setBatchForm(f => ({ ...f, expiry_date: e.target.value }))} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Quantity" required>
              <Input type="number" required step="0.01" value={batchForm.quantity} onChange={e => setBatchForm(f => ({ ...f, quantity: e.target.value }))} />
            </Field>
            <Field label="Unit Cost Price (₹)">
              <Input type="number" step="0.01" value={batchForm.unit_cost} onChange={e => setBatchForm(f => ({ ...f, unit_cost: e.target.value }))} />
            </Field>
          </div>
        </form>
      </Modal>

      <Modal
        open={!!qrItem}
        onClose={() => setQrItem(null)}
        title={`QR Code · ${qrItem?.sku || ""}`}
        size="sm"
        testid="qr-modal"
        footer={
          <SecondaryButton onClick={() => setQrItem(null)}>Close</SecondaryButton>
        }
      >
        {qrItem && (
          <div className="flex flex-col items-center gap-4">
            <div className="bg-white p-5">
              <QRCode
                value={`SKU:${qrItem.sku}|NAME:${qrItem.name}`}
                size={200}
                bgColor="#ffffff"
                fgColor="#000000"
              />
            </div>
            <div className="text-center">
              <div className="font-mono text-yellow-400 text-lg">
                {qrItem.sku}
              </div>
              <div className="text-zinc-300 text-sm">{qrItem.name}</div>
            </div>
            <PrimaryButton onClick={() => window.print()}>Print</PrimaryButton>
          </div>
        )}
      </Modal>
    </div>
  );
}
