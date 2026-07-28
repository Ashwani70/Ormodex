import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Field, Select, EmptyState,
  FormSection, CollapsibleFormSection, SummaryCard, Badge, NumericInput,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import ItemSearch from "@/components/ItemSearch";
import useOnline from "@/hooks/useOnline";
import usePdfAction from "@/hooks/usePdfAction";
import useAccordionState from "@/hooks/useAccordionState";
import BulkDeleteBar, { SelectCheckbox } from "@/components/BulkDeleteBar";
import useBulkSelect from "@/hooks/useBulkSelect";
import { STANDARD_UOMS, DEFAULT_UOM } from "@/config/uom";
import useGridKeyNav from "@/hooks/useGridKeyNav";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import {
  Plus, X, Download, Pencil, Trash2, Lock, PenLine, Package,
  TrendingDown, TrendingUp, Boxes, ShoppingCart, FileText, ImageOff, MapPin,
  ChevronsUpDown,
} from "lucide-react";

// Which sections start open — Basic Info expanded by default per spec; Line
// Items is a plain (non-collapsible) FormSection so it's always visible.
const PO_SECTION_DEFAULTS = { numbering: true, details: true };

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const qtyFmt = (n) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });

/* Small colored KPI tile for the Inventory Status card. */
function InvKpi({ tone, icon: Icon, label, value, unit }) {
  const tones = {
    green: "border-[#BBF7D0] bg-[#F0FDF4] text-[#166534]",
    blue: "border-[#BFDBFE] bg-[#EFF6FF] text-[#1E40AF]",
    red: "border-[#FECACA] bg-[#FEF2F2] text-[#991B1B]",
  };
  return (
    <div className={`rounded-xl border p-3 ${tones[tone]}`}>
      <div className="flex items-center gap-1.5 text-xs font-medium">
        <Icon className="h-3.5 w-3.5" /> {label}
      </div>
      <div className="mt-1 font-display text-lg font-bold tabular">
        {value}{unit ? <span className="ml-1 text-xs font-normal">{unit}</span> : null}
      </div>
    </div>
  );
}

const STATUSES = ["DRAFT", "SENT", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED", "CANCELLED"];
const STATUS_TONE = { DRAFT: "neutral", SENT: "info", PARTIALLY_RECEIVED: "warning", RECEIVED: "success", CLOSED: "success", CANCELLED: "danger" };
const blankLine = () => ({ product_id: "", product_name: "", hsn_code: "", unit: DEFAULT_UOM, qty: "", rate: "", gst_rate: "", _manual: false, _gst_type: "GST", _cgst: "", _sgst: "", _igst: "" });
const blank = () => ({ vendor_id: "", expected_date: "", status: "DRAFT", notes: "", lines: [blankLine()], po_number: "", po_number_reason: "" });

const lineBase = (l) => (parseFloat(l.qty) || 0) * (parseFloat(l.rate) || 0);
const lineTotal = (l) => lineBase(l) * (1 + (parseFloat(l.gst_rate) || 0) / 100);

export default function PurchaseOrdersV2() {
  const online = useOnline();
  const { run: downloadPoPdf, busyId } = usePdfAction();
  const [items, setItems] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [orders, setOrders] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank());
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  // Numbering config: { mode, can_override, can_edit, ...template }
  const [numbering, setNumbering] = useState(null);
  const [numberAudit, setNumberAudit] = useState([]);
  const [editingPo, setEditingPo] = useState(null);
  // Stock summary keyed by item name and SKU for the product search card
  const [stockMap, setStockMap] = useState({});
  // Most-recently-selected product → drives the right-rail Inventory/Product cards
  const [activeProductId, setActiveProductId] = useState("");
  // Which form sections are expanded — persisted so a section left open stays
  // open next time this form is used ("remember last expanded state").
  const acc = useAccordionState("po-form-sections", PO_SECTION_DEFAULTS);

  const isReceived = (po) =>
    (po.lines || []).some((l) => parseFloat(l.received_qty) > 0) ||
    ["RECEIVED", "CLOSED", "CANCELLED"].includes(po.status);

  // Only POs without received goods can be deleted — restrict selection to those.
  const deletableOrders = orders.filter((po) => !isReceived(po));
  const sel = useBulkSelect(deletableOrders);

  const bulkDelete = async () => {
    if (!online) return toast.warning("You are offline — deletion is disabled.");
    const { ok, failed } = await sel.runDelete(
      (id) => api.delete(`/purchase/v2/orders/${id}`),
      { reload: load }
    );
    if (failed) toast.error(`Deleted ${ok}, failed ${failed}`);
    else toast.success(`Deleted ${ok} purchase order${ok === 1 ? "" : "s"}`);
  };

  // A locked number can never be edited from the UI (server enforces too).
  const isNumberLocked = (po) =>
    !!po && (po.po_number_locked || po.status !== "DRAFT" || isReceived(po));

  const load = async () => {
    const [it, vd, po, num] = await Promise.all([
      api.get("/products"),
      api.get("/purchase/v2/vendors"),
      api.get("/purchase/v2/orders"),
      api.get("/settings/po-numbering").catch(() => ({ data: null })),
    ]);
    setItems(it.data); setVendors(vd.data); setOrders(po.data);
    setNumbering(num.data);
  };
  useEffect(() => { load(); }, []);

  const setLine = (idx, patch) =>
    setForm((f) => ({ ...f, lines: f.lines.map((l, i) => (i === idx ? { ...l, ...patch } : l)) }));
  const toggleLineManual = (idx) =>
    setForm((f) => ({
      ...f,
      lines: f.lines.map((l, i) =>
        i === idx ? { ...l, _manual: !l._manual, product_id: "", product_name: "" } : l
      ),
    }));

  const setGstType = (idx, type) =>
    setForm((f) => ({
      ...f,
      lines: f.lines.map((l, i) => {
        if (i !== idx) return l;
        const cur = parseFloat(l.gst_rate) || 0;
        if (type === "GST")        return { ...l, _gst_type: type };
        if (type === "CGST_SGST")  return { ...l, _gst_type: type, _cgst: cur / 2, _sgst: cur / 2 };
        if (type === "IGST")       return { ...l, _gst_type: type, _igst: cur };
        return l;
      }),
    }));
  const addLine = () => setForm((f) => ({ ...f, lines: [...f.lines, blankLine()] }));
  const removeLine = (idx) => setForm((f) => ({ ...f, lines: f.lines.filter((_, i) => i !== idx) }));
  const insertLineAfter = (idx) =>
    setForm((f) => {
      const lines = [...f.lines];
      lines.splice(idx + 1, 0, blankLine());
      return { ...f, lines };
    });
  const removeLineKeepingOne = (idx) =>
    setForm((f) => ({
      ...f,
      lines: f.lines.length > 1 ? f.lines.filter((_, i) => i !== idx) : [blankLine()],
    }));

  // Keyboard-first line-item entry (Tally-style), same pattern as SalesOrders.jsx.
  // Columns: Product(0) → Description(1) → HSN/SAC(2) → Ordered Qty(3) → Unit(4)
  // → Rate(5) → GST(6, or 6+7 for CGST+SGST). Discount is a disabled placeholder
  // (not yet wired to the backend) so it is skipped from the grid entirely.
  const gstColsForRow = (row) => (form.lines[row]?._gst_type === "CGST_SGST" ? 8 : 7);
  const gridNav = useGridKeyNav({
    rowCount: form.lines.length,
    colCount: gstColsForRow,
    onRowComplete: addLine,
    onInsertRow: insertLineAfter,
    onDeleteRow: removeLineKeepingOne,
  });

  // Picking a product on a line: prefill from catalog + surface it in the side cards.
  const pickProduct = (idx, pid) => {
    const p = items.find((i) => i.id === pid);
    const rate = p?.cost_price != null ? Number(p.cost_price) : "";
    const gst = p?.gst_rate != null ? Number(p.gst_rate) : "";
    const half = gst !== "" ? gst / 2 : "";
    setLine(idx, {
      product_id: pid,
      ...(p ? {
        hsn_code: p.hsn_code || "",
        unit: p.unit || DEFAULT_UOM,
        rate,
        gst_rate: gst,
        _cgst: half,
        _sgst: half,
        _igst: gst,
      } : {}),
    });
    setActiveProductId(pid || "");
  };

  const subtotal = form.lines.reduce((s, l) => s + (parseFloat(l.qty) || 0) * (parseFloat(l.rate) || 0), 0);
  const gstAmount = form.lines.reduce((s, l) => {
    const base = (parseFloat(l.qty) || 0) * (parseFloat(l.rate) || 0);
    return s + base * (parseFloat(l.gst_rate) || 0) / 100;
  }, 0);
  const cgstAmount = form.lines.reduce((s, l) => {
    if (l._gst_type !== "CGST_SGST") return s;
    return s + (parseFloat(l.qty) || 0) * (parseFloat(l.rate) || 0) * (parseFloat(l._cgst) || 0) / 100;
  }, 0);
  const sgstAmount = form.lines.reduce((s, l) => {
    if (l._gst_type !== "CGST_SGST") return s;
    return s + (parseFloat(l.qty) || 0) * (parseFloat(l.rate) || 0) * (parseFloat(l._sgst) || 0) / 100;
  }, 0);
  const igstAmount = form.lines.reduce((s, l) => {
    if (l._gst_type !== "IGST") return s;
    return s + (parseFloat(l.qty) || 0) * (parseFloat(l.rate) || 0) * (parseFloat(l._igst) || 0) / 100;
  }, 0);
  const total = subtotal + gstAmount;
  const hasCgstSgst = form.lines.some((l) => l._gst_type === "CGST_SGST");
  const hasIgst = form.lines.some((l) => l._gst_type === "IGST");

  const fetchStockMap = async () => {
    try {
      const { data } = await api.get("/inventory/v2/reports/stock-summary");
      const map = {};
      data.forEach((s) => { map[s.name] = s; if (s.sku) map[s.sku] = s; });
      setStockMap(map);
    } catch { /* non-fatal */ }
  };

  const openCreate = async () => {
    setEditingId(null);
    setEditingPo(null);
    setNumberAudit([]);
    setActiveProductId("");
    fetchStockMap();
    const f = blank();
    if (numbering?.mode === "AUTO") {
      try {
        const { data } = await api.get("/settings/po-numbering/preview");
        f.po_number = data.preview || "";
      } catch { /* non-fatal */ }
    }
    setForm(f);
    setOpen(true);
  };

  const openEdit = async (po) => {
    setEditingId(po.id);
    setEditingPo(po);
    setActiveProductId("");
    fetchStockMap();
    setForm({
      vendor_id: po.vendor_id || "",
      expected_date: po.expected_date || "",
      status: po.status || "DRAFT",
      notes: po.notes || "",
      po_number: po.po_number || "",
      po_number_reason: "",
      lines: (po.lines || []).map((l) => {
        const gst = l.gst_rate ?? 18;
        const gstType = l.gst_type || "GST";
        return {
          product_id: l.product_id || "",
          product_name: l.product_name || "",
          hsn_code: l.hsn_code || "",
          unit: l.unit || DEFAULT_UOM,
          qty: l.qty != null && l.qty !== 0 ? l.qty : "",
          rate: l.rate != null && l.rate !== 0 ? l.rate : "",
          gst_rate: gst !== "" ? gst : "",
          _manual: !l.product_id && !!l.product_name,
          _gst_type: gstType,
          _cgst: gstType === "CGST_SGST" ? (l.cgst_rate ?? (parseFloat(gst) || 0) / 2) : (parseFloat(gst) || 0) / 2,
          _sgst: gstType === "CGST_SGST" ? (l.sgst_rate ?? (parseFloat(gst) || 0) / 2) : (parseFloat(gst) || 0) / 2,
          _igst: gstType === "IGST" ? ((l.igst_rate ?? parseFloat(gst)) || 0) : parseFloat(gst) || 0,
        };
      }),
    });
    setNumberAudit([]);
    try {
      const { data } = await api.get(`/purchase/v2/orders/${po.id}/number-audit`);
      setNumberAudit(data || []);
    } catch { /* non-fatal */ }
    setOpen(true);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    const lines = form.lines
      .filter((l) => (l._manual ? l.product_name?.trim() : l.product_id) && parseFloat(l.qty) > 0)
      .map((l) => ({
        product_id: l._manual ? null : l.product_id,
        product_name: l._manual ? l.product_name : items.find((i) => i.id === l.product_id)?.name,
        hsn_code: l.hsn_code || null,
        unit: l.unit || DEFAULT_UOM,
        qty: parseFloat(l.qty), rate: parseFloat(l.rate) || 0, gst_rate: parseFloat(l.gst_rate) || 0,
        gst_type: l._gst_type || "GST",
        cgst_rate: l._gst_type === "CGST_SGST" ? parseFloat(l._cgst) || 0 : null,
        sgst_rate: l._gst_type === "CGST_SGST" ? parseFloat(l._sgst) || 0 : null,
        igst_rate: l._gst_type === "IGST" ? parseFloat(l._igst) || 0 : null,
      }));
    if (lines.length === 0) return toast.error("Add at least one line.");

    const body = { ...form, expected_date: form.expected_date || null, lines };
    if (editingId) {
      // On edit, only send po_number when it actually changed (a real rename);
      // otherwise let the server keep the existing one. Drop the auto-preview noise.
      if ((form.po_number || "") === (editingPo?.po_number || "")) {
        delete body.po_number;
        delete body.po_number_reason;
      }
    } else {
      // On create, the number field is only meaningful as an override. In AUTO
      // mode without override permission it's just a prefilled preview — drop it
      // so the server assigns the real sequenced number.
      const isManual = numbering?.mode === "MANUAL";
      const canOverride = numbering?.can_override;
      if (!isManual && !canOverride) {
        delete body.po_number;
      }
      if (!body.po_number) delete body.po_number;
    }

    if (saving) return;
    setSaving(true);
    try {
      if (editingId) {
        await api.put(`/purchase/v2/orders/${editingId}`, body);
        toast.success("Purchase order updated");
      } else {
        await api.post("/purchase/v2/orders", body);
        toast.success("Purchase order created");
      }
      setOpen(false);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  // Enter-as-Tab data entry engine (see useEnterNavigation): Enter moves to the
  // next field anywhere in this form, falling through to the grid's own Enter
  // handling inside the line-item table (data-grid-managed below). Ctrl+Enter
  // saves, Ctrl+Shift+Enter saves and opens a fresh blank PO, Escape cancels.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: open,
    autoFocus: true,
    onSave: () => submit(new Event("submit", { cancelable: true })),
    onSaveAndNew: async () => {
      await submit(new Event("submit", { cancelable: true }));
      openCreate();
    },
    onCancel: () => setOpen(false),
  });

  const remove = async (po) => {
    if (!online) return toast.warning("You are offline — deletion is disabled.");
    if (!window.confirm(`Delete purchase order ${po.po_number}? This cannot be undone.`)) return;
    try {
      await api.delete(`/purchase/v2/orders/${po.id}`);
      toast.success("Purchase order deleted");
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  const changeStatus = async (po, status) => {
    if (!online) return toast.warning("You are offline — changes are disabled.");
    try {
      await api.patch(`/purchase/v2/orders/${po.id}/status?status=${status}`);
      toast.success(`Status → ${status}`);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  // Global module shortcut: Ctrl/Cmd+N → new PO (when the list is showing, not
  // already editing one). Ctrl+Enter/Ctrl+Shift+Enter save via useEnterNavigation
  // above, since Enter-based save is the primary keyboard-first flow here.
  useModuleShortcuts({
    onNew: () => { if (!open) openCreate(); },
  });

  // ── Right-rail product/inventory derivations (display only) ────────────
  const activeProduct = items.find((i) => i.id === activeProductId) || null;
  const activeStock = activeProduct
    ? (stockMap[activeProduct.name] || stockMap[activeProduct.sku] || null)
    : null;
  const avgCost = activeStock && activeStock.closing_qty
    ? activeStock.closing_value / activeStock.closing_qty
    : (activeProduct ? Number(activeProduct.cost_price || 0) : 0);
  const productLocation = (() => {
    const pg = activeStock?.per_godown;
    if (Array.isArray(pg) && pg.length) return pg[0].godown_name || pg[0].name || "Main Warehouse";
    return activeStock ? "Main Warehouse" : "—";
  })();
  // Per-line available-stock lookup for the grid column.
  const lineStock = (l) => {
    if (l._manual || !l.product_id) return null;
    const p = items.find((i) => i.id === l.product_id);
    if (!p) return null;
    return stockMap[p.name] || stockMap[p.sku] || null;
  };

  return (
    <div data-testid="purchase-orders-v2-page">
      <PageHeader
        eyebrow="Purchase"
        title="Purchase Orders"
        description="Raise POs against vendors. Receipt status updates as GRNs are posted."
        actions={
          <PrimaryButton testid="new-po" icon={Plus} disabled={!online}
            onClick={openCreate}>
            New PO
          </PrimaryButton>
        }
      />
      <OfflineBanner online={online} />

      {orders.length === 0 ? (
        <EmptyState message="No purchase orders yet" />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="border-b border-border label-overline">
                <th className="px-3 py-2.5 w-10">
                  <SelectCheckbox
                    label="Select all deletable purchase orders"
                    checked={sel.allSelected}
                    indeterminate={sel.someSelected}
                    onChange={sel.toggleAll}
                  />
                </th>
                <th className="px-3 py-2.5">PO Number</th>
                <th className="px-3 py-2.5">Vendor</th>
                <th className="px-3 py-2.5">Expected</th>
                <th className="px-3 py-2.5 text-right">Total</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((po) => (
                <tr key={po.id} data-testid={`po-row-${po.id}`} className={`border-b border-border hover:bg-muted/40 text-foreground ${sel.isSelected(po.id) ? "bg-primary/5" : ""}`}>
                  <td className="px-3 py-2.5">
                    {!isReceived(po) ? (
                      <SelectCheckbox
                        label={`Select purchase order ${po.po_number}`}
                        checked={sel.isSelected(po.id)}
                        onChange={() => sel.toggle(po.id)}
                      />
                    ) : (
                      <Lock className="w-3.5 h-3.5 text-muted-foreground/40 mx-auto" title="Cannot delete a PO with received goods" />
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-foreground font-semibold">
                    <span className="inline-flex items-center gap-1.5">
                      {po.po_number}
                      {isNumberLocked(po) && (
                        <Lock className="w-3 h-3 text-muted-foreground" title="PO number is locked" data-testid={`po-lock-${po.id}`} />
                      )}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-muted-foreground">{po.vendor_name || "—"}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{po.expected_date || "—"}</td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground tabular">{po.total != null ? Number(po.total).toLocaleString("en-IN") : "—"}</td>
                  <td className="px-3 py-2.5">
                    <Select value={po.status} onChange={(e) => changeStatus(po, e.target.value)}
                      className="text-xs py-1 h-9" disabled={!online}>
                      {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </Select>
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        onClick={() => downloadPoPdf(`/purchase/v2/orders/${po.id}/pdf`, `${po.po_number}.pdf`, po.id)}
                        disabled={busyId === po.id}
                        title="Download PDF"
                        data-testid={`po-pdf-${po.id}`}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center disabled:opacity-50"
                      >
                        <Download className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => openEdit(po)}
                        disabled={!online || isReceived(po)}
                        title={isReceived(po) ? "Cannot edit a PO with received goods" : "Edit"}
                        data-testid={`po-edit-${po.id}`}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center disabled:opacity-40"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => remove(po)}
                        disabled={!online || isReceived(po)}
                        title={isReceived(po) ? "Cannot delete a PO with received goods" : "Delete"}
                        data-testid={`po-delete-${po.id}`}
                        className="w-7 h-7 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground inline-flex items-center justify-center disabled:opacity-40"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editingId ? "Edit Purchase Order" : "New Purchase Order"}
        icon={ShoppingCart}
        size="full"
        bodyClassName="p-6 bg-[var(--bg)]"
        headerExtra={
          <div className="hidden items-center gap-3 sm:flex">
            <Badge tone={STATUS_TONE[form.status] || "neutral"}>{form.status}</Badge>
            <span className="rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground">
              PO # <span className="font-semibold text-foreground">{form.po_number || (numbering?.mode === "MANUAL" ? "Manual" : "Auto on save")}</span>
            </span>
          </div>
        }
        footer={
          <div className="flex w-full flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">
              Grand Total <span className="font-display font-bold text-base text-primary">₹{inr(total)}</span>
            </span>
            <div className="flex items-center gap-2">
              <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
              <PrimaryButton onClick={submit} testid="save-po" disabled={!online || saving} icon={ShoppingCart}
                className="bg-gradient-to-r from-[#2563EB] to-[#1D4ED8]">
                {saving ? "Saving…" : (editingId ? "Save Changes" : "Create PO")}
              </PrimaryButton>
            </div>
          </div>
        }
      >
        <form ref={formRef} id="po-form" onSubmit={submit} className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="flex min-w-0 flex-col gap-6">

            <div className="flex justify-end gap-2 -mb-2">
              <SecondaryButton icon={ChevronsUpDown} className="h-8 px-2.5 text-xs" onClick={acc.expandAll}>Expand All</SecondaryButton>
              <SecondaryButton icon={ChevronsUpDown} className="h-8 px-2.5 text-xs" onClick={acc.collapseAll}>Collapse All</SecondaryButton>
            </div>

            {/* ── PO numbering (logic preserved verbatim) ─────────────── */}
            {(() => {
              const locked = editingId ? isNumberLocked(editingPo) : false;
              const numberEditable = editingId
                ? (!locked && !!numbering?.can_edit)
                : (numbering?.mode === "MANUAL" || !!numbering?.can_override);
              const showReason = editingId && numberEditable &&
                (form.po_number || "") !== (editingPo?.po_number || "");
              return (
                <CollapsibleFormSection
                  title="PO Numbering" icon={FileText} grid={false}
                  open={acc.isOpen("numbering")} onOpenChange={() => acc.toggle("numbering")}
                >
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-x-5 gap-y-4">
                    <Field label="PO Number" required={!editingId && numbering?.mode === "MANUAL"}>
                      <div className="relative">
                        <Input
                          data-testid="po-number-input"
                          value={form.po_number || ""}
                          disabled={!numberEditable}
                          placeholder={numbering?.mode === "MANUAL" ? "Enter PO number" : "Auto-generated"}
                          onChange={(e) => setForm({ ...form, po_number: e.target.value })}
                        />
                        {locked && (
                          <Lock className="w-3.5 h-3.5 text-muted-foreground absolute right-2.5 top-1/2 -translate-y-1/2" />
                        )}
                      </div>
                    </Field>
                    {showReason && (
                      <Field label="Reason for change" required>
                        <Input
                          data-testid="po-number-reason"
                          value={form.po_number_reason || ""}
                          onChange={(e) => setForm({ ...form, po_number_reason: e.target.value })}
                          placeholder="e.g. corrected typo"
                        />
                      </Field>
                    )}
                  </div>
                  {!numberEditable && (
                    <p className="mt-3 text-xs text-muted-foreground">
                      {locked
                        ? "This PO number is locked (the PO has been approved, received, billed, or is no longer a draft)."
                        : editingId
                          ? "You don't have permission to change PO numbers (po_number_edit required)."
                          : numbering?.mode === "AUTO"
                            ? "Number is auto-generated. You need po_number_override to customise it."
                            : "You need po_number_override to enter a manual PO number."}
                    </p>
                  )}
                  {numberAudit.length > 0 && (
                    <div className="mt-3 pt-1">
                      <div className="label-overline mb-1.5">PO Number History</div>
                      <div className="space-y-1" data-testid="po-number-audit">
                        {numberAudit.map((a) => (
                          <div key={a.id} className="text-xs text-muted-foreground flex flex-wrap gap-x-2">
                            <span className="text-foreground font-medium">{a.old_po_number || "—"} → {a.new_po_number}</span>
                            <span>by {a.changed_by_name || a.changed_by}</span>
                            <span>{(a.changed_at || "").slice(0, 19).replace("T", " ")}</span>
                            {a.reason && <span className="italic">“{a.reason}”</span>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </CollapsibleFormSection>
              );
            })()}

            {/* ── Purchase Order Details (4-col) ──────────────────────── */}
            <CollapsibleFormSection
              title="Purchase Order Details" icon={FileText} cols={4}
              open={acc.isOpen("details")} onOpenChange={() => acc.toggle("details")}
            >
              <Field label="Vendor" required>
                <Select required value={form.vendor_id} data-testid="po-vendor"
                  onChange={(e) => setForm({ ...form, vendor_id: e.target.value })}>
                  <option value="">— Select vendor —</option>
                  {vendors.map((v) => <option key={v.id} value={v.id}>{v.company || v.name}</option>)}
                </Select>
              </Field>
              <Field label="Expected Date">
                <Input type="date" value={form.expected_date}
                  onChange={(e) => setForm({ ...form, expected_date: e.target.value })} />
              </Field>
              <Field label="Status">
                <Select value={form.status} disabled={!!editingId}
                  onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </Select>
              </Field>
              <Field label="Remarks">
                <Input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Short note" />
              </Field>

              {/* Below have no backend field yet — shown disabled so the layout is
                  complete without pretending the data persists. */}
              <Field label="Reference" hint="Not stored yet — needs an API field.">
                <Input placeholder="Reference no." disabled />
              </Field>
              <Field label="Buyer" hint="Not stored yet — needs an API field.">
                <Input placeholder="Buyer name" disabled />
              </Field>
              <Field label="Currency" hint="Single-currency for now.">
                <Select disabled><option>INR ₹</option></Select>
              </Field>
              <Field label="Warehouse" hint="Set on the GRN at receipt time.">
                <Input placeholder="Chosen at GRN" disabled />
              </Field>
              <Field label="Supplier GSTIN" hint="Not stored on the PO yet.">
                <Input placeholder="From vendor master" disabled />
              </Field>
              <Field label="Payment Terms" hint="Not stored yet — needs an API field.">
                <Input placeholder="e.g. Net 30" disabled />
              </Field>
              <Field label="Delivery Address" hint="Not stored yet — needs an API field.">
                <Input placeholder="Ship-to address" disabled />
              </Field>
            </CollapsibleFormSection>

            {/* ── Line items ──────────────────────────────────────────── */}
            <FormSection
              title="Line Items"
              icon={Package}
              grid={false}
              actions={
                <div className="flex flex-wrap items-center gap-2">
                  <span className="hidden text-xs text-muted-foreground sm:inline-flex items-center gap-2">
                    <Package className="w-3 h-3" /> catalog
                    <PenLine className="w-3 h-3 text-[var(--warning)]" /> manual
                  </span>
                  <SecondaryButton icon={Plus} className="h-9 px-3 text-xs" onClick={addLine}>Add line</SecondaryButton>
                </div>
              }
            >
              <div className="overflow-x-auto rounded-lg border border-border">
                <table data-grid-managed className="w-full text-left text-xs table-fixed" style={{ minWidth: "1180px" }}>
                  <colgroup>
                    <col style={{ width: "32px" }} />
                    <col style={{ width: "210px" }} />
                    <col style={{ width: "130px" }} />
                    <col style={{ width: "76px" }} />
                    <col style={{ width: "76px" }} />
                    <col style={{ width: "76px" }} />
                    <col style={{ width: "64px" }} />
                    <col style={{ width: "84px" }} />
                    <col style={{ width: "70px" }} />
                    <col style={{ width: "150px" }} />
                    <col style={{ width: "90px" }} />
                    <col style={{ width: "36px" }} />
                  </colgroup>
                  <thead className="sticky top-0 z-10">
                    <tr className="border-b border-border bg-muted text-muted-foreground">
                      <th className="px-1.5 py-2.5 text-center font-semibold">#</th>
                      <th className="px-1.5 py-2.5 font-semibold">Product</th>
                      <th className="px-1.5 py-2.5 font-semibold">Description</th>
                      <th className="px-1.5 py-2.5 font-semibold">HSN/SAC</th>
                      <th className="px-1.5 py-2.5 text-right font-semibold">Available</th>
                      <th className="px-1.5 py-2.5 text-right font-semibold">Ordered</th>
                      <th className="px-1.5 py-2.5 font-semibold">Unit</th>
                      <th className="px-1.5 py-2.5 text-right font-semibold">Rate</th>
                      <th className="px-1.5 py-2.5 text-right font-semibold">Disc.</th>
                      <th className="px-1.5 py-2.5 font-semibold">GST</th>
                      <th className="px-1.5 py-2.5 text-right font-semibold">Amount</th>
                      <th className="px-1.5 py-2.5 text-center font-semibold">Del</th>
                    </tr>
                  </thead>
                  <tbody>
                    {form.lines.map((l, idx) => {
                      const s = lineStock(l);
                      return (
                        <tr key={idx} className="border-b border-border align-top hover:bg-muted/30">
                          <td className="px-1.5 py-1.5 text-center align-middle text-muted-foreground">{idx + 1}</td>
                          <td className="px-1.5 py-1.5">
                            <div className="flex items-start gap-1">
                              <button
                                type="button"
                                title={l._manual ? "Switch to catalog product" : "Enter product manually"}
                                onClick={() => toggleLineManual(idx)}
                                className={`mt-px flex h-9 w-8 flex-shrink-0 items-center justify-center rounded-lg border transition-colors ${l._manual ? "border-[var(--warning)] text-[var(--warning)]" : "border-border text-muted-foreground hover:border-primary hover:text-primary"}`}
                              >
                                {l._manual ? <PenLine className="h-3.5 w-3.5" /> : <Package className="h-3.5 w-3.5" />}
                              </button>
                              {l._manual ? (
                                <Input
                                  placeholder="Product name"
                                  value={l.product_name}
                                  onChange={(e) => setLine(idx, { product_name: e.target.value })}
                                  ref={gridNav.registerCell(idx, 0)}
                                  onKeyDown={gridNav.handleKeyDown(idx, 0)}
                                  className="h-9 px-2"
                                />
                              ) : (
                                <div className="flex-1 min-w-0">
                                  <ItemSearch
                                    products={items}
                                    stockMap={stockMap}
                                    value={l.product_id}
                                    onChange={(pid) => pickProduct(idx, pid)}
                                    inputRef={gridNav.registerCell(idx, 0)}
                                    onKeyDown={gridNav.handleKeyDown(idx, 0)}
                                  />
                                </div>
                              )}
                            </div>
                          </td>
                          <td className="px-1.5 py-1.5">
                            <Input placeholder="Description" value={l.description || ""}
                              onChange={(e) => setLine(idx, { description: e.target.value })}
                              ref={gridNav.registerCell(idx, 1)} onKeyDown={gridNav.handleKeyDown(idx, 1)}
                              className="h-9 px-2" />
                          </td>
                          <td className="px-1.5 py-1.5">
                            <Input placeholder="7308" value={l.hsn_code || ""}
                              onChange={(e) => setLine(idx, { hsn_code: e.target.value })}
                              ref={gridNav.registerCell(idx, 2)} onKeyDown={gridNav.handleKeyDown(idx, 2)}
                              className="h-9 px-2" />
                          </td>
                          <td className="px-1.5 py-1.5 text-right align-middle tabular">
                            {s ? (
                              <span className={s.closing_qty > 0 ? "text-[var(--success)] font-medium" : "text-[var(--danger)] font-medium"}>
                                {qtyFmt(s.closing_qty)}
                              </span>
                            ) : <span className="text-muted-foreground">—</span>}
                          </td>
                          <td className="px-1.5 py-1.5">
                            <NumericInput compact value={l.qty} onChange={(v) => setLine(idx, { qty: v })} placeholder="0"
                              ref={gridNav.registerCell(idx, 3)} onKeyDown={gridNav.handleKeyDown(idx, 3)}
                              className="h-9 w-full" />
                          </td>
                          <td className="px-1.5 py-1.5">
                            <Select value={l.unit || DEFAULT_UOM} onChange={(e) => setLine(idx, { unit: e.target.value })}
                              ref={gridNav.registerCell(idx, 4)} onKeyDown={gridNav.handleKeyDown(idx, 4)}
                              className="h-9 px-1.5">
                              {STANDARD_UOMS.map((u) => <option key={u} value={u}>{u}</option>)}
                            </Select>
                          </td>
                          <td className="px-1.5 py-1.5">
                            <NumericInput compact value={l.rate} onChange={(v) => setLine(idx, { rate: v })} placeholder="0.00"
                              ref={gridNav.registerCell(idx, 5)} onKeyDown={gridNav.handleKeyDown(idx, 5)}
                              className="h-9 w-full" />
                          </td>
                          <td className="px-1.5 py-1.5">
                            <NumericInput compact value="" disabled placeholder="0" className="h-9 w-full" />
                          </td>
                          <td className="px-1.5 py-1.5">
                            {/* GST type + rate — logic preserved */}
                            <div className="space-y-1">
                              <div className="flex flex-wrap gap-1">
                                {["GST", "CGST+SGST", "IGST"].map((label) => {
                                  const key = label === "CGST+SGST" ? "CGST_SGST" : label;
                                  const active = l._gst_type === key;
                                  return (
                                    <button
                                      key={key}
                                      type="button"
                                      onClick={() => setGstType(idx, key)}
                                      className={`rounded-md border px-1 py-0.5 text-[9px] font-medium leading-tight transition-colors ${active ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground hover:border-primary hover:text-primary"}`}
                                    >
                                      {label}
                                    </button>
                                  );
                                })}
                              </div>
                              {l._gst_type === "GST" && (
                                <NumericInput compact value={l.gst_rate} onChange={(v) => setLine(idx, { gst_rate: v })} placeholder="18" max={100} aria-label="GST %"
                                  ref={gridNav.registerCell(idx, 6)} onKeyDown={gridNav.handleKeyDown(idx, 6)} className="h-8 w-full" />
                              )}
                              {l._gst_type === "CGST_SGST" && (
                                <div className="flex gap-1">
                                  <NumericInput compact value={l._cgst} onChange={(v) => { const n = parseFloat(v) || 0; setLine(idx, { _cgst: v, gst_rate: n + (parseFloat(l._sgst) || 0) }); }} placeholder="9" max={100} aria-label="CGST %"
                                    ref={gridNav.registerCell(idx, 6)} onKeyDown={gridNav.handleKeyDown(idx, 6)} className="h-8 w-1/2" />
                                  <NumericInput compact value={l._sgst} onChange={(v) => { const n = parseFloat(v) || 0; setLine(idx, { _sgst: v, gst_rate: (parseFloat(l._cgst) || 0) + n }); }} placeholder="9" max={100} aria-label="SGST %"
                                    ref={gridNav.registerCell(idx, 7)} onKeyDown={gridNav.handleKeyDown(idx, 7)} className="h-8 w-1/2" />
                                </div>
                              )}
                              {l._gst_type === "IGST" && (
                                <NumericInput compact value={l._igst} onChange={(v) => { setLine(idx, { _igst: v, gst_rate: v }); }} placeholder="18" max={100} aria-label="IGST %"
                                  ref={gridNav.registerCell(idx, 6)} onKeyDown={gridNav.handleKeyDown(idx, 6)} className="h-8 w-full" />
                              )}
                            </div>
                          </td>
                          <td className="px-1.5 py-1.5 text-right align-middle tabular font-semibold text-foreground">
                            ₹{inr(lineTotal(l))}
                          </td>
                          <td className="px-1 py-1.5 text-center align-middle">
                            <button type="button" onClick={() => removeLine(idx)} aria-label="Remove line"
                              className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:border-[var(--danger)] hover:bg-[#FEE2E2] hover:text-[var(--danger)] mx-auto">
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </FormSection>
          </div>

          {/* ── Right rail: inventory + product + order summary ───────── */}
          <aside className="flex min-w-0 flex-col gap-6">
            <div className="lg:sticky lg:top-4 flex flex-col gap-6">
              {/* Inventory Status (only after a product is picked) */}
              {activeProduct && (
                <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <h3 className="mb-3 font-display font-semibold text-sm text-foreground">Inventory Status</h3>
                  <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
                    <InvKpi tone="green" icon={Boxes} label="Current Stock" value={qtyFmt(activeStock?.closing_qty ?? activeProduct.quantity ?? 0)} unit={activeProduct.unit} />
                    <InvKpi tone="blue" icon={TrendingUp} label="Incoming" value={qtyFmt(activeStock?.inward_qty ?? 0)} unit={activeProduct.unit} />
                    <InvKpi tone="red" icon={TrendingDown} label="Reserved / Outward" value={qtyFmt(activeStock?.outward_qty ?? 0)} unit={activeProduct.unit} />
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2.5 text-sm">
                    <div>
                      <div className="label-overline">Available Stock</div>
                      <div className="font-semibold text-foreground tabular">{qtyFmt(activeStock?.closing_qty ?? 0)} {activeProduct.unit}</div>
                    </div>
                    <div>
                      <div className="label-overline">Location</div>
                      <div className="flex items-center gap-1 font-medium text-foreground"><MapPin className="h-3.5 w-3.5 text-muted-foreground" />{productLocation}</div>
                    </div>
                    <div>
                      <div className="label-overline">Average Cost</div>
                      <div className="font-medium text-foreground tabular">₹{inr(avgCost)}</div>
                    </div>
                    <div>
                      <div className="label-overline">Catalog Cost</div>
                      <div className="font-medium text-foreground tabular">₹{inr(activeProduct.cost_price)}</div>
                    </div>
                  </div>
                  <p className="mt-3 text-[11px] text-muted-foreground">
                    Last purchase / last sale price are not exposed by the API yet.
                  </p>
                </div>
              )}

              {/* Product Information */}
              {activeProduct && (
                <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <h3 className="mb-3 font-display font-semibold text-sm text-foreground">Product Information</h3>
                  <div className="flex gap-4">
                    <div className="flex h-20 w-20 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border bg-[var(--bg)]">
                      {activeProduct.image_url ? (
                        <img src={activeProduct.image_url} alt={activeProduct.name} className="h-full w-full object-cover" />
                      ) : (
                        <ImageOff className="h-6 w-6 text-muted-foreground" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold text-foreground truncate">{activeProduct.name}</div>
                      <div className="text-xs text-muted-foreground">{activeProduct.sku || "—"}</div>
                      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                        <div><span className="text-muted-foreground">Category: </span><span className="text-foreground">{activeProduct.category || "—"}</span></div>
                        <div><span className="text-muted-foreground">Unit: </span><span className="text-foreground">{activeProduct.unit || "—"}</span></div>
                        <div><span className="text-muted-foreground">Current: </span><span className="text-foreground tabular">{qtyFmt(activeStock?.closing_qty ?? 0)}</span></div>
                        <div><span className="text-muted-foreground">Incoming: </span><span className="text-foreground tabular">{qtyFmt(activeStock?.inward_qty ?? 0)}</span></div>
                        <div><span className="text-muted-foreground">Brand: </span><span className="text-muted-foreground italic">n/a</span></div>
                        <div><span className="text-muted-foreground">Avg cost: </span><span className="text-foreground tabular">₹{inr(avgCost)}</span></div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Order Summary */}
              <SummaryCard
                title="Order Summary"
                rows={[
                  { label: "Subtotal", value: `₹${inr(subtotal)}` },
                  { label: "Discount", value: "₹0.00" },
                  ...(hasCgstSgst ? [
                    { label: "CGST", value: `₹${inr(cgstAmount)}` },
                    { label: "SGST", value: `₹${inr(sgstAmount)}` },
                  ] : []),
                  ...(hasIgst ? [{ label: "IGST", value: `₹${inr(igstAmount)}` }] : []),
                  ...(!hasCgstSgst && !hasIgst ? [{ label: "GST", value: `₹${inr(gstAmount)}` }] : []),
                  { label: "Freight", value: "₹0.00" },
                  { label: "Round Off", value: "₹0.00" },
                ]}
                total={{ label: "Grand Total", value: `₹${inr(total)}` }}
                footer={
                  <div className="text-center">
                    <div className="label-overline">Grand Total</div>
                    <div className="font-display text-2xl font-bold text-primary">₹{inr(total)}</div>
                  </div>
                }
              />
            </div>
          </aside>
        </form>
      </Modal>

      <BulkDeleteBar
        count={sel.count}
        deleting={sel.deleting}
        onClear={sel.clear}
        onDelete={bulkDelete}
        noun="purchase order"
      />
    </div>
  );
}
