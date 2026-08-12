import { useEffect, useRef, useState } from "react";
import useDebounce from "@/hooks/useDebounce";
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
import SearchableSelect from "@/components/SearchableSelect";
import BulkDeleteBar, { SelectCheckbox } from "@/components/BulkDeleteBar";
import useBulkSelect from "@/hooks/useBulkSelect";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { Plus, Search, Pencil, Trash2, QrCode, AlertTriangle, RefreshCw, CheckCircle, Calendar, Eye } from "lucide-react";
import { STANDARD_UOMS, DEFAULT_UOM } from "@/config/uom";

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
  category: "",
  category_id: "",
  description: "",
  unit: DEFAULT_UOM,
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
        className="w-10 h-10 object-cover border border-border"
      />
    );
  }
  return <div className="w-10 h-10 hazard-stripe opacity-40" />;
}

export default function Products() {
  const [params, setParams] = useSearchParams();
  const [items, setItems] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  // Seed the search box from ?q= so the global search can deep-link here.
  const [q, setQ] = useState(params.get("q") || "");
  const [lowOnly, setLowOnly] = useState(params.get("low") === "1");
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [qrItem, setQrItem] = useState(null);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);

  // UOM master & quick-add popup
  const [uoms, setUoms] = useState(STANDARD_UOMS);
  const [uomModal, setUomModal] = useState(false);
  const [uomForm, setUomForm] = useState({ name: "", description: "" });
  const [savingUom, setSavingUom] = useState(false);

  // Category master + quick-add popup (create a category without leaving this page).
  const [categories, setCategories] = useState([]);
  const [catModal, setCatModal] = useState(false);
  const [catForm, setCatForm] = useState({ name: "", description: "" });
  const [savingCat, setSavingCat] = useState(false);
  // Product name autocomplete suggestions (existing products).
  const [nameFocused, setNameFocused] = useState(false);
  const nameBoxRef = useRef(null);

  // New stock analysis tabs state
  const [tab, setTab] = useState("catalog");
  const [agingData, setAgingData] = useState(null);
  const [agingDays, setAgingDays] = useState(90);
  const [valuationData, setValuationData] = useState(null);
  const [valuationMethod, setValuationMethod] = useState("WEIGHTED_AVERAGE");
  const [reorderData, setReorderData] = useState(null);
  const [verifications, setVerifications] = useState([]);
  const [showPvModal, setShowPvModal] = useState(false);
  const [editingPvId, setEditingPvId] = useState(null);
  const [viewPv, setViewPv] = useState(null);
  const [savingPv, setSavingPv] = useState(false);
  const [pvForm, setPvForm] = useState({
    verification_date: new Date().toISOString().split("T")[0],
    verified_by: "",
    warehouse_id: "",
    notes: "",
    items: [],
  });
  const [batches, setBatches] = useState([]);
  const [showBatchModal, setShowBatchModal] = useState(false);
  const [savingBatch, setSavingBatch] = useState(false);
  const [batchForm, setBatchForm] = useState({
    product_id: "",
    batch_number: "",
    manufacture_date: "",
    expiry_date: "",
    quantity: 0,
    unit_cost: 0,
    warehouse_id: "",
  });

  const debouncedQ = useDebounce(q, 300);
  const load = async () => {
    const r = await api.get("/products", { params: { q: debouncedQ, low_stock: lowOnly } });
    setItems(r.data);
  };

  const sel = useBulkSelect(items);
  const bulkDelete = async () => {
    const { ok, failed } = await sel.runDelete(
      (id) => api.delete(`/products/${id}`),
      { reload: load }
    );
    if (failed) toast.error(`Deleted ${ok}, failed ${failed}`);
    else toast.success(`Deleted ${ok} product${ok === 1 ? "" : "s"}`);
  };
  const loadWh = async () => {
    const r = await api.get("/inventory/v2/godowns");
    setWarehouses(r.data);
  };
  const loadCategories = async () => {
    try {
      const r = await api.get("/categories", { params: { status: "Active" } });
      setCategories(r.data);
    } catch {
      setCategories([]);
    }
  };

  const loadUoms = async () => {
    try {
      const r = await api.get("/inventory/uoms");
      if (Array.isArray(r.data) && r.data.length > 0) {
        setUoms(r.data);
      }
    } catch {
      setUoms(STANDARD_UOMS);
    }
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
  }, [tab, agingDays, valuationMethod, debouncedQ, lowOnly]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    loadWh();
    loadCategories();
    loadUoms();
  }, []);

  // Auto-open detail modal when navigated here via ?detail=<id> (e.g. from Ctrl+K search).
  useEffect(() => {
    const detailId = params.get("detail");
    if (!detailId || items.length === 0) return;
    const record = items.find((p) => p.id === detailId);
    if (record) {
      startEdit(record);
      const next = new URLSearchParams(params);
      next.delete("detail");
      setParams(next, { replace: true });
    }
  }, [params, items]); // eslint-disable-line react-hooks/exhaustive-deps

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

  // Auto-open the create form via ?new=1 — the global Alt+P shortcut
  // (useKeyboardShortcuts) navigates here with this flag so "Create Product"
  // is a single keystroke from anywhere in the app.
  useEffect(() => {
    if (params.get("new") !== "1") return;
    startNew();
    const next = new URLSearchParams(params);
    next.delete("new");
    setParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  // Global module shortcut: Ctrl/Cmd+N → new product. (Ctrl/Cmd+S for this
  // page's own form is already handled by the effect below, which also
  // knows about the "add category" sub-modal — left as-is to avoid a
  // double-submit if both handlers matched the same key.)
  useModuleShortcuts({
    onNew: () => { if (!open && tab === "catalog") startNew(); },
  });

  // Product name autocomplete: distinct existing names matching what's typed.
  const nameSuggestions = (() => {
    const term = (form.name || "").trim().toLowerCase();
    if (!term || editingId) return [];
    const seen = new Set();
    const out = [];
    for (const p of items) {
      const key = (p.name || "").toLowerCase();
      if (key && key.includes(term) && key !== term && !seen.has(key)) {
        seen.add(key);
        out.push(p);
        if (out.length >= 8) break;
      }
    }
    return out;
  })();

  // Pick an existing product → copy its catalog attributes onto the new product.
  const applyProductTemplate = (p) => {
    setForm((f) => ({
      ...f,
      name: p.name,
      category: p.category || "",
      category_id: p.category_id || "",
      unit: p.unit || f.unit,
      gst_rate: p.gst_rate ?? f.gst_rate,
      hsn_code: p.hsn_code || "",
      cost_price: p.cost_price ?? f.cost_price,
      image_path: p.image_path || "",
      image_url: p.image_path ? "" : (p.image_url || ""),
    }));
    setNameFocused(false);
  };

  // Quick-add a category from the product form, then auto-select it.
  const openCatModal = () => {
    if (!open) return;            // only meaningful while the product form is open
    setCatForm({ name: "", description: "" });
    setCatModal(true);
  };
  const saveCategory = async () => {
    const name = catForm.name.trim();
    if (!name) return toast.warning("Category name is required.");
    setSavingCat(true);
    try {
      const { data } = await api.post("/categories", {
        name, description: catForm.description.trim() || null, status: "Active",
      });
      await loadCategories();
      // Auto-select the freshly created category on the product form.
      setForm((f) => ({ ...f, category_id: data.id, category: data.name }));
      setCatModal(false);
      toast.success(`Category "${data.name}" added`);
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSavingCat(false);
    }
  };

  // Quick-add a UOM from the product form, then auto-select it.
  const openUomModal = () => {
    if (!open) return;
    setUomForm({ name: "", description: "" });
    setUomModal(true);
  };
  const saveUom = async () => {
    const name = uomForm.name.trim();
    if (!name) return toast.warning("UOM name is required.");
    setSavingUom(true);
    try {
      const { data } = await api.post("/inventory/uoms", {
        name, description: uomForm.description.trim() || null,
      });
      await loadUoms();
      const createdName = data.name || name;
      setForm((f) => ({ ...f, unit: createdName }));
      setUomModal(false);
      toast.success(`Unit of Measure "${createdName}" added`);
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSavingUom(false);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    // SKU is no longer entered by hand, but the backend still requires a unique
    // one. Auto-derive it from the name (+ short timestamp) when not already set
    // (existing products keep their SKU on edit).
    const autoSku = () => {
      const base = (form.name || "ITEM")
        .toUpperCase().replace(/[^A-Z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 12) || "ITEM";
      return `${base}-${Date.now().toString(36).toUpperCase().slice(-5)}`;
    };
    const payload = {
      ...form,
      sku: form.sku || autoSku(),
      category: form.category || "",
      category_id: form.category_id || null,
      cost_price: Number(form.cost_price) || 0,
      selling_price: Number(form.selling_price) || 0,
      quantity: Number(form.quantity) || 0,
      low_stock_threshold: Number(form.low_stock_threshold) || 10,
      gst_rate: Number(form.gst_rate) || 18,
      warehouse_id: form.warehouse_id || null,
    };
    // Strip UI-only / server-derived fields so they aren't persisted onto the
    // product record. (For linked products the list re-derives quantity/cost/gst
    // from the stock ledger on the next load, so the saved values are harmless.)
    delete payload.stock_linked;
    delete payload.stock_item_id;
    delete payload.warehouse_name;
    delete payload.product_count;
    if (saving) return;
    setSaving(true);
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
      toast.error(formatApiErrorDetail(e));
    } finally {
      setSaving(false);
    }
  };

  // Keyboard shortcuts (active while the product form is open):
  //   Alt+C → add a new category (still a bare page-level shortcut — it has
  //   no natural field to anchor a data-quick-create host to, unlike
  //   ItemSearch/PartySearch's inline quick-create).
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.altKey && (e.key === "c" || e.key === "C")) {
        e.preventDefault();
        openCatModal();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  // Enter-as-Tab data entry (see useEnterNavigation): Enter/Tab moves through
  // the product form field-by-field, Ctrl+Enter/Ctrl+S/Alt+S saves, Escape
  // cancels. Disabled while the category quick-add modal is open on top so
  // its own Enter/Escape aren't swallowed by this form's listener underneath.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: open && !catModal,
    autoFocus: true,
    onSave: () => submit(new Event("submit", { cancelable: true })),
    onCancel: () => setOpen(false),
  });

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
    setEditingPvId(null);
    setPvForm({
      verification_date: new Date().toISOString().split("T")[0],
      verified_by: "",
      warehouse_id: warehouses[0]?.id || "",
      notes: "",
      items: itemsList,
    });
    setShowPvModal(true);
  };

  const startEditPv = (v) => {
    setEditingPvId(v.id);
    setPvForm({
      verification_date: v.verification_date,
      verified_by: v.verified_by,
      warehouse_id: v.warehouse_id || "",
      notes: v.notes || "",
      items: (v.items || []).map(it => ({ ...it })),
    });
    setShowPvModal(true);
  };

  const openViewPv = (v) => setViewPv(v);

  const submitPv = async (e) => {
    e.preventDefault();
    if (savingPv) return;
    setSavingPv(true);
    try {
      if (editingPvId) {
        await api.put(`/stock/physical-verifications/${editingPvId}`, pvForm);
        toast.success("Physical verification updated");
      } else {
        await api.post("/stock/physical-verifications", pvForm);
        toast.success("Physical verification recorded as Draft");
      }
      setShowPvModal(false);
      setEditingPvId(null);
      loadVerifications();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to submit verification");
    } finally {
      setSavingPv(false);
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

  const deletePv = async (v) => {
    if (!window.confirm(`Delete physical verification dated ${v.verification_date}?`)) return;
    try {
      await api.delete(`/stock/physical-verifications/${v.id}`);
      toast.success("Physical verification deleted");
      loadVerifications();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to delete verification");
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
    if (savingBatch) return;
    setSavingBatch(true);
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
    } finally {
      setSavingBatch(false);
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
      <div className="flex gap-px bg-border border border-border mb-6 overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
        {TABS.map(t => (
          <button key={t.id} data-testid={`tab-${t.id}`} onClick={() => setTab(t.id)}
            className={`flex-shrink-0 px-4 py-3 text-xs font-mono uppercase tracking-wider transition-colors ${
              tab === t.id ? "bg-primary text-primary-foreground font-bold" : "bg-card text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}>{t.label}</button>
        ))}
      </div>

      {tab === "catalog" && (
        <>
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <div className="relative flex-1 min-w-[200px] max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
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
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:border-primary hover:text-primary"
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
            <div className="border border-border overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted text-muted-foreground">
                  <tr className="text-left label-overline">
                    <th className="px-3 py-2.5 w-10">
                      <SelectCheckbox
                        label="Select all products"
                        checked={sel.allSelected}
                        indeterminate={sel.someSelected}
                        onChange={sel.toggleAll}
                      />
                    </th>
                    <th className="px-3 py-2.5">Product</th>
                    <th className="px-3 py-2.5">SKU</th>
                    <th className="px-3 py-2.5">Category</th>
                    <th className="px-3 py-2.5">HSN</th>
                    <th className="px-3 py-2.5">Warehouse</th>
                    <th className="px-3 py-2.5 text-right">Stock Qty</th>
                    <th className="px-3 py-2.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((p, i) => {
                    return (
                      <tr
                        key={p.id}
                        data-testid={`product-row-${p.sku}`}
                        className={`border-t border-border hover:bg-muted/40 ${
                          sel.isSelected(p.id) ? "bg-primary/5" : i % 2 === 0 ? "bg-transparent" : "bg-muted/30"
                        }`}
                      >
                        <td className="px-3 py-2.5">
                          <SelectCheckbox
                            label={`Select product ${p.sku}`}
                            checked={sel.isSelected(p.id)}
                            onChange={() => sel.toggle(p.id)}
                          />
                        </td>
                        <td className="px-3 py-2.5 text-foreground">
                          <div className="flex items-center gap-3">
                            <ProductImageThumb product={p} />
                            <div className="text-foreground">{p.name}</div>
                          </div>
                        </td>
                        <td className="px-3 py-2.5 font-mono text-primary text-xs">
                          {p.sku}
                        </td>
                        <td className="px-3 py-2.5 text-foreground">{p.category}</td>
                        <td className="px-3 py-2.5 text-muted-foreground font-mono text-xs">
                          {p.hsn_code || "-"}
                        </td>
                        <td className="px-3 py-2.5 text-muted-foreground">
                          {p.warehouse_name || "-"}
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono text-xs text-foreground font-medium">
                          {p.quantity ?? 0} {p.unit || DEFAULT_UOM}
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          <div className="inline-flex gap-1">
                            <button
                              data-testid={`qr-${p.sku}`}
                              onClick={() => setQrItem(p)}
                              className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground flex items-center justify-center"
                            >
                              <QrCode className="w-3.5 h-3.5" />
                            </button>
                            <button
                              data-testid={`edit-${p.sku}`}
                              onClick={() => startEdit(p)}
                              className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground flex items-center justify-center"
                            >
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                            <button
                              data-testid={`delete-${p.sku}`}
                              onClick={() => onDelete(p)}
                              className="w-7 h-7 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground flex items-center justify-center"
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
          <div className="flex items-center gap-3 bg-card border border-border p-4" style={{ borderRadius: "var(--radius)" }}>
            <span className="label-overline">Aging Threshold (Days)</span>
            <Select value={agingDays} onChange={e => setAgingDays(parseInt(e.target.value))} className="w-28">
              <option value={30}>30 Days</option>
              <option value={60}>60 Days</option>
              <option value={90}>90 Days</option>
              <option value={180}>180 Days</option>
            </Select>
            <span className="text-xs text-muted-foreground italic">Identifies stock with no sales/dispatches in this period.</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <StatTile label="Total Items Checked" value={agingData.total_products} />
            <StatTile label="Slow Moving Items" value={agingData.slow_moving_count} accent={agingData.slow_moving_count > 0} />
            <StatTile label="Total Stock Value" value={`₹${Number(agingData.total_stock_value).toLocaleString("en-IN")}`} />
            <StatTile label="Slow Moving Value" value={`₹${Number(agingData.items?.filter(x => x.is_slow_moving).reduce((s, x) => s + x.stock_value, 0)).toLocaleString("en-IN")}`} />
          </div>

          <div className="border border-border overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted text-muted-foreground label-overline">
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
                  <tr key={item.product_id} className={`border-t border-border hover:bg-muted/40 ${idx % 2 === 0 ? "" : "bg-muted/30"}`}>
                    <td className="px-3 py-2 text-foreground font-semibold text-left">{item.name}</td>
                    <td className="px-3 py-2 font-mono text-xs text-primary text-left">{item.sku}</td>
                    <td className="px-3 py-2 text-right tabular text-foreground">{item.quantity} {item.unit}</td>
                    <td className="px-3 py-2 text-right tabular text-muted-foreground">₹{Number(item.cost_price).toLocaleString("en-IN")}</td>
                    <td className="px-3 py-2 text-right tabular text-foreground">₹{Number(item.stock_value).toLocaleString("en-IN")}</td>
                    <td className="px-3 py-2 font-mono text-xs text-muted-foreground text-left">{item.last_movement || "No movement"}</td>
                    <td className="px-3 py-2 text-right tabular text-foreground">{item.days_since_movement} days</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                        item.is_slow_moving ? "bg-red-50 border-red-200 text-red-700 font-bold" : "bg-emerald-50 border-emerald-200 text-emerald-700"
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
          <div className="flex items-center gap-3 bg-card border border-border p-4" style={{ borderRadius: "var(--radius)" }}>
            <span className="label-overline">Valuation Method</span>
            <Select value={valuationMethod} onChange={e => setValuationMethod(e.target.value)} className="w-48">
              <option value="WEIGHTED_AVERAGE">Weighted Average (Avg Cost)</option>
              <option value="FIFO">First In, First Out (FIFO)</option>
            </Select>
            <span className="text-xs text-muted-foreground italic">Select method to compute total inventory assets valuation.</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <StatTile label="Total Products" value={valuationData.total_products} />
            <StatTile label="Valuation Method" value={valuationData.method} />
            <StatTile label="Total Valued Assets" value={`₹${Number(valuationData.total_value).toLocaleString("en-IN")}`} accent />
          </div>

          <div className="border border-border overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted text-muted-foreground label-overline">
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
                  <tr key={item.product_id} className={`border-t border-border hover:bg-muted/40 ${idx % 2 === 0 ? "" : "bg-muted/30"}`}>
                    <td className="px-3 py-2 text-foreground font-semibold text-left">{item.name}</td>
                    <td className="px-3 py-2 font-mono text-xs text-primary text-left">{item.sku}</td>
                    <td className="px-3 py-2 text-muted-foreground text-left">{item.category}</td>
                    <td className="px-3 py-2 text-right tabular text-foreground">{item.quantity} {item.unit}</td>
                    <td className="px-3 py-2 text-right tabular text-foreground">₹{Number(item.unit_cost).toLocaleString("en-IN")}</td>
                    <td className="px-3 py-2 text-right tabular text-primary font-semibold">₹{Number(item.selling_price).toLocaleString("en-IN")}</td>
                    <td className="px-3 py-2 text-right tabular text-emerald-600 font-bold">₹{Number(item.total_value).toLocaleString("en-IN")}</td>
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

          <div className="border border-border overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted text-muted-foreground label-overline">
                <tr>
                  <th className="px-3 py-2 text-left">Product Name</th>
                  <th className="px-3 py-2 text-left">SKU</th>
                  <th className="px-3 py-2 text-right">Current Qty</th>
                  <th className="px-3 py-2 text-right">Reorder Level</th>
                  <th className="px-3 py-2 text-right">Shortage</th>
                  <th className="px-3 py-2 text-right">Suggested Order Qty</th>
                  <th className="px-3 py-2 text-right">Estimated Cost</th>
                  <th className="px-3 py-2 text-left">Preferred Vendor</th>
                </tr>
              </thead>
              <tbody>
                {reorderData.items?.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground font-mono">All products are above their reorder thresholds.</td>
                  </tr>
                )}
                {reorderData.items?.map((item, idx) => (
                  <tr key={item.product_id} className={`border-t border-border hover:bg-muted/40 ${idx % 2 === 0 ? "" : "bg-muted/30"}`}>
                    <td className="px-3 py-2 text-foreground font-semibold text-left">{item.name}</td>
                    <td className="px-3 py-2 font-mono text-xs text-primary text-left">{item.sku}</td>
                    <td className="px-3 py-2 text-right tabular text-red-600 font-bold">{item.current_quantity} {item.unit}</td>
                    <td className="px-3 py-2 text-right tabular text-muted-foreground">{item.reorder_level}</td>
                    <td className="px-3 py-2 text-right tabular text-red-500 font-extrabold">{item.shortage}</td>
                    <td className="px-3 py-2 text-right tabular text-emerald-600 font-bold">{item.suggested_order_qty}</td>
                    <td className="px-3 py-2 text-right tabular text-foreground">₹{Number(item.estimated_cost).toLocaleString("en-IN")}</td>
                    <td className="px-3 py-2 text-foreground font-semibold text-left">{item.preferred_supplier || "None"}</td>
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
          <div className="bg-card border border-border overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
            <table className="w-full text-sm">
              <thead className="bg-muted text-muted-foreground label-overline">
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
                    <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground font-mono">No stock verification records.</td>
                  </tr>
                )}
                {verifications.map((v, idx) => (
                  <tr key={v.id} className={`border-t border-border hover:bg-muted/40 ${idx % 2 === 0 ? "" : "bg-muted/30"}`}>
                    <td className="px-3 py-2 font-mono text-foreground text-left">{v.verification_date}</td>
                    <td className="px-3 py-2 text-foreground font-bold text-left">{v.created_by_name || v.verified_by}</td>
                    <td className="px-3 py-2 text-right tabular text-muted-foreground">{v.items_checked}</td>
                    <td className={`px-3 py-2 text-right tabular ${v.total_discrepancy > 0 ? "text-primary font-bold" : "text-muted-foreground"}`}>
                      {v.total_discrepancy}
                    </td>
                    <td className="px-3 py-2 text-left">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                        v.status === "APPROVED" ? "bg-emerald-50 border-emerald-200 text-emerald-700" : "bg-amber-50 border-amber-200 text-amber-700"
                      }`}>{v.status}</span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {v.status === "DRAFT" && (
                          <button onClick={() => approvePv(v.id)} className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-mono font-bold px-2.5 py-1 uppercase transition-colors" style={{ borderRadius: "var(--radius-sm)" }}>
                            Approve & Adjust
                          </button>
                        )}
                        <button onClick={() => openViewPv(v)} title="View" className="p-1.5 text-muted-foreground hover:text-primary hover:bg-muted transition-colors" style={{ borderRadius: "var(--radius-sm)" }}>
                          <Eye className="w-4 h-4" />
                        </button>
                        {v.status !== "APPROVED" && (
                          <>
                            <button onClick={() => startEditPv(v)} title="Edit" className="p-1.5 text-muted-foreground hover:text-primary hover:bg-muted transition-colors" style={{ borderRadius: "var(--radius-sm)" }}>
                              <Pencil className="w-4 h-4" />
                            </button>
                            <button onClick={() => deletePv(v)} title="Delete" className="p-1.5 text-muted-foreground hover:text-red-600 hover:bg-red-50 transition-colors" style={{ borderRadius: "var(--radius-sm)" }}>
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </>
                        )}
                      </div>
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
          <div className="bg-card border border-border overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
            <table className="w-full text-sm">
              <thead className="bg-muted text-muted-foreground label-overline">
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
                    <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground font-mono">No batch tracks loaded.</td>
                  </tr>
                )}
                {batches.map((b, idx) => (
                  <tr key={b.id} className={`border-t border-border hover:bg-muted/40 ${idx % 2 === 0 ? "" : "bg-muted/30"}`}>
                    <td className="px-3 py-2 text-foreground font-bold text-left">{b.product_name}</td>
                    <td className="px-3 py-2 font-mono text-xs text-primary text-left">{b.sku}</td>
                    <td className="px-3 py-2 font-mono text-foreground text-left">{b.batch_number}</td>
                    <td className="px-3 py-2 text-right tabular text-foreground">{b.quantity}</td>
                    <td className="px-3 py-2 font-mono text-muted-foreground text-xs text-left">{b.manufacture_date || "—"}</td>
                    <td className="px-3 py-2 font-mono text-red-600 text-xs font-semibold text-left">{b.expiry_date || "—"}</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                        b.expiry_status === "GOOD" ? "bg-emerald-50 border-emerald-200 text-emerald-700" :
                        b.expiry_status === "NEAR_EXPIRY" ? "bg-amber-50 border-amber-200 text-amber-700 font-bold" :
                        "bg-red-50 border-red-200 text-red-700 font-black"
                      }`}>{b.expiry_status || "GOOD"}</span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button onClick={() => onDeleteBatch(b.id)} className="text-red-600 hover:text-red-500 text-xs">
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
            <PrimaryButton testid="save-product" onClick={submit} disabled={saving}>
              {saving ? "Saving…" : "Save Product"}
            </PrimaryButton>
          </>
        }
      >
        <form ref={formRef} onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Product Name" required hint={editingId ? undefined : "Start typing to reuse an existing product's details"}>
            <div className="relative" ref={nameBoxRef}>
              <Input
                required
                data-testid="form-name"
                autoComplete="off"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                onFocus={() => setNameFocused(true)}
                onBlur={() => setTimeout(() => setNameFocused(false), 150)}
              />
              {nameFocused && nameSuggestions.length > 0 && (
                <ul
                  data-testid="name-autocomplete"
                  className="absolute z-50 mt-1 max-h-56 w-full overflow-auto border border-border bg-card shadow-lg"
                  style={{ borderRadius: "var(--radius-md)" }}
                >
                  {nameSuggestions.map((p) => (
                    <li
                      key={p.id}
                      data-testid={`name-suggestion-${p.sku}`}
                      onMouseDown={(e) => { e.preventDefault(); applyProductTemplate(p); }}
                      className="px-3 py-2 text-sm cursor-pointer hover:bg-muted flex items-center justify-between gap-2 text-foreground"
                    >
                      <span>{p.name}</span>
                      <span className="text-muted-foreground font-mono text-xs">{p.category || ""}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Field>
          <Field label="Category" hint="Alt+C to add a new category">
            <div className="flex items-center gap-2">
              <div className="flex-1">
                <SearchableSelect
                  testid="form-category"
                  placeholder="Search category…"
                  value={form.category_id}
                  options={categories.map((c) => ({
                    value: c.id, label: c.name, sublabel: c.code,
                  }))}
                  onChange={(id) => {
                    const c = categories.find((x) => x.id === id);
                    setForm({ ...form, category_id: id, category: c?.name || "" });
                  }}
                  onCreate={openCatModal}
                  createLabel="Create New Category"
                />
              </div>
              <button
                type="button"
                title="Add new category (Alt+C)"
                data-testid="add-category-btn"
                onClick={openCatModal}
                className="w-10 h-10 flex-shrink-0 border border-border hover:border-primary hover:text-primary text-muted-foreground flex items-center justify-center transition-colors"
                style={{ borderRadius: "var(--radius-md)" }}
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
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
          <Field
            label={editingId ? "Stock Quantity" : "Opening Quantity"}
            hint={
              editingId
                ? "Changing this posts a stock adjustment for the difference"
                : form.quantity
                ? `Initial stock: ${form.quantity} ${form.unit || DEFAULT_UOM}`
                : "Posted as an OPENING stock movement"
            }
          >
            <Input
              type="text"
              inputMode="decimal"
              data-testid="form-opening-quantity"
              value={form.quantity ?? ""}
              onChange={(e) => setForm({ ...form, quantity: e.target.value })}
            />
          </Field>
          <Field label="UOM (Unit of Measure)" required hint="Mandatory unit for stock transactions">
            <div className="flex items-center gap-2">
              <Select
                required
                data-testid="form-uom"
                value={form.unit || DEFAULT_UOM}
                onChange={(e) => {
                  if (e.target.value === "__ADD_NEW__") {
                    openUomModal();
                  } else {
                    setForm({ ...form, unit: e.target.value });
                  }
                }}
                className="flex-1"
              >
                {uoms.map((u) => (
                  <option key={u} value={u}>
                    {u}
                  </option>
                ))}
                <option value="__ADD_NEW__">+ Add Custom UOM...</option>
              </Select>
              <button
                type="button"
                title="Add custom UOM"
                data-testid="add-uom-btn"
                onClick={openUomModal}
                className="w-10 h-10 flex-shrink-0 border border-border hover:border-primary hover:text-primary text-muted-foreground flex items-center justify-center transition-colors"
                style={{ borderRadius: "var(--radius-md)" }}
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
          </Field>
          <Field label="Cost Price" hint="Values the opening quantity above (FIFO/LIFO/Weighted-Avg costing)">
            <Input
              type="text"
              inputMode="decimal"
              data-testid="form-cost-price"
              value={form.cost_price}
              onChange={(e) => setForm({ ...form, cost_price: e.target.value })}
            />
          </Field>

          <div className="md:col-span-2">
            <Field label="Product Image">
              <ImageUploader
                value={form.image_path || form.image_url}
                onChange={(p) => setForm({ ...form, image_path: p, image_url: "" })}
              />
            </Field>
          </div>
          <Field label="HSN Code">
            <Input
              value={form.hsn_code || ""}
              onChange={(e) => setForm({ ...form, hsn_code: e.target.value })}
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

      {/* Quick-add Category popup — create a category without leaving the product form */}
      <Modal
        open={catModal}
        onClose={() => setCatModal(false)}
        title="New Category"
        size="sm"
        testid="quick-category-modal"
        footer={
          <>
            <SecondaryButton onClick={() => setCatModal(false)}>Cancel</SecondaryButton>
            <PrimaryButton testid="save-quick-category" onClick={saveCategory} disabled={savingCat}>
              {savingCat ? "Saving…" : "Add Category"}
            </PrimaryButton>
          </>
        }
      >
        <form
          onSubmit={(e) => { e.preventDefault(); saveCategory(); }}
          className="space-y-3"
        >
          <Field label="Category Name" required>
            <Input
              required
              autoFocus
              data-testid="quick-category-name"
              value={catForm.name}
              onChange={(e) => setCatForm({ ...catForm, name: e.target.value })}
            />
          </Field>
          <Field label="Description">
            <Textarea
              rows={2}
              value={catForm.description}
              onChange={(e) => setCatForm({ ...catForm, description: e.target.value })}
            />
          </Field>
        </form>
      </Modal>

      {/* Quick-add UOM popup — create a custom UOM without leaving the product form */}
      <Modal
        open={uomModal}
        onClose={() => setUomModal(false)}
        title="New Unit of Measure (UOM)"
        size="sm"
        testid="quick-uom-modal"
        footer={
          <>
            <SecondaryButton onClick={() => setUomModal(false)}>Cancel</SecondaryButton>
            <PrimaryButton testid="save-quick-uom" onClick={saveUom} disabled={savingUom}>
              {savingUom ? "Saving…" : "Add UOM"}
            </PrimaryButton>
          </>
        }
      >
        <form
          onSubmit={(e) => { e.preventDefault(); saveUom(); }}
          className="space-y-3"
        >
          <Field label="UOM Name" required hint="e.g. Dozen, Crate, Packet">
            <Input
              required
              autoFocus
              data-testid="quick-uom-name"
              value={uomForm.name}
              onChange={(e) => setUomForm({ ...uomForm, name: e.target.value })}
            />
          </Field>
          <Field label="Description">
            <Textarea
              rows={2}
              value={uomForm.description}
              onChange={(e) => setUomForm({ ...uomForm, description: e.target.value })}
            />
          </Field>
        </form>
      </Modal>

      {/* Physical Stock Verification Modal */}
      <Modal
        open={showPvModal}
        onClose={() => { setShowPvModal(false); setEditingPvId(null); }}
        title={editingPvId ? "Edit Physical Stock Audit / Verification" : "Physical Stock Audit / Verification"}
        size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => { setShowPvModal(false); setEditingPvId(null); }}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submitPv} disabled={savingPv}>{savingPv ? "Saving…" : (editingPvId ? "Save Changes" : "Record Audit")}</PrimaryButton>
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

          <div className="border border-border max-h-[300px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-muted text-muted-foreground sticky top-0 label-overline">
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
                  <tr key={item.product_id} className="border-t border-border">
                    <td className="px-3 py-1.5 text-foreground text-left">{item.product_name}</td>
                    <td className="px-3 py-1.5 font-mono text-muted-foreground text-left">{item.sku}</td>
                    <td className="px-3 py-1.5 text-right tabular text-muted-foreground">{item.system_quantity}</td>
                    <td className="px-3 py-1.5 text-right pr-1">
                      <input
                        type="text" inputMode="decimal"
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
                        className="w-20 bg-background border border-input text-right text-xs px-2 py-1 text-foreground focus:outline-none focus:border-primary"
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
                        className="w-full bg-background border border-input text-xs px-2 py-1 text-foreground focus:outline-none focus:border-primary"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </form>
      </Modal>

      {/* Physical Stock Verification — View Modal */}
      <Modal
        open={!!viewPv}
        onClose={() => setViewPv(null)}
        title="Physical Verification Details"
        size="lg"
        footer={<SecondaryButton onClick={() => setViewPv(null)}>Close</SecondaryButton>}
      >
        {viewPv && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <Field label="Verification Date"><div className="text-sm font-mono text-foreground">{viewPv.verification_date}</div></Field>
              <Field label="Verified By / Inspector"><div className="text-sm text-foreground">{viewPv.created_by_name || viewPv.verified_by}</div></Field>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Warehouse">
                <div className="text-sm text-foreground">{warehouses.find(w => w.id === viewPv.warehouse_id)?.name || "—"}</div>
              </Field>
              <Field label="Status">
                <span className={`text-[10px] font-mono px-1.5 py-0.5 border ${
                  viewPv.status === "APPROVED" ? "bg-emerald-50 border-emerald-200 text-emerald-700" : "bg-amber-50 border-amber-200 text-amber-700"
                }`}>{viewPv.status}</span>
              </Field>
            </div>
            {viewPv.notes && (
              <Field label="Audit Notes / General Remarks"><div className="text-sm text-foreground">{viewPv.notes}</div></Field>
            )}
            <div className="border border-border max-h-[300px] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted text-muted-foreground sticky top-0 label-overline">
                  <tr>
                    <th className="px-3 py-2 text-left">Product Name</th>
                    <th className="px-3 py-2 text-left">SKU</th>
                    <th className="px-3 py-2 text-right">System Qty</th>
                    <th className="px-3 py-2 text-right">Physical Qty</th>
                    <th className="px-3 py-2 text-right">Discrepancy</th>
                    <th className="px-3 py-2 text-left">Remarks</th>
                  </tr>
                </thead>
                <tbody>
                  {(viewPv.items || []).map((item, idx) => (
                    <tr key={item.product_id || idx} className="border-t border-border">
                      <td className="px-3 py-1.5 text-foreground text-left">{item.product_name}</td>
                      <td className="px-3 py-1.5 font-mono text-muted-foreground text-left">{item.sku}</td>
                      <td className="px-3 py-1.5 text-right tabular text-muted-foreground">{item.system_quantity}</td>
                      <td className="px-3 py-1.5 text-right tabular text-foreground">{item.physical_quantity}</td>
                      <td className={`px-3 py-1.5 text-right tabular font-semibold ${Number(item.discrepancy) !== 0 ? "text-primary" : "text-muted-foreground"}`}>{item.discrepancy}</td>
                      <td className="px-3 py-1.5 text-left text-foreground">{item.remarks || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
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
            <PrimaryButton onClick={submitBatch} disabled={savingBatch}>{savingBatch ? "Saving…" : "Record Batch"}</PrimaryButton>
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
              <Input type="text" inputMode="decimal" required step="0.01" value={batchForm.quantity} onChange={e => setBatchForm(f => ({ ...f, quantity: e.target.value }))} />
            </Field>
            <Field label="Unit Cost Price (₹)">
              <Input type="text" inputMode="decimal" step="0.01" value={batchForm.unit_cost} onChange={e => setBatchForm(f => ({ ...f, unit_cost: e.target.value }))} />
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
              <div className="font-mono text-primary text-lg">
                {qrItem.sku}
              </div>
              <div className="text-foreground text-sm">{qrItem.name}</div>
            </div>
            <PrimaryButton onClick={() => window.print()}>Print</PrimaryButton>
          </div>
        )}
      </Modal>

      {tab === "catalog" && (
        <BulkDeleteBar
          count={sel.count}
          deleting={sel.deleting}
          onClear={sel.clear}
          onDelete={bulkDelete}
          noun="product"
        />
      )}
    </div>
  );
}
