import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import { STANDARD_UOMS, DEFAULT_UOM } from "@/config/uom";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Field, Select, EmptyState,
  FormSection, SummaryCard, Badge, NumericInput,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import ItemSearch from "@/components/ItemSearch";
import PartySearch from "@/components/PartySearch";
import QuickCreateModal from "@/components/QuickCreateModal";
import { downloadPdf, fmtMoney } from "@/lib/currency";
import SendEmailButton from "@/components/SendEmailButton";
import BulkDeleteBar, { SelectCheckbox } from "@/components/BulkDeleteBar";
import useBulkSelect from "@/hooks/useBulkSelect";
import useGridKeyNav from "@/hooks/useGridKeyNav";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import {
  Plus, X, Pencil, Trash2, Download, CheckCircle2, FileText,
  Package, UsersRound, Printer, MessageCircle, FileSpreadsheet, PenLine,
} from "lucide-react";

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const SO_STATUSES = ["PENDING", "CONFIRMED", "DISPATCHED", "DELIVERED", "CANCELLED"];
const STATUS_TONE = { PENDING: "neutral", CONFIRMED: "info", DISPATCHED: "warning", DELIVERED: "success", CANCELLED: "danger" };

const blankLine = () => ({ product_id: "", product_name: "", hsn_code: "", unit: DEFAULT_UOM, quantity: "", unit_price: "", discount: "", gst_rate: "", _manual: false, _gst_type: "GST", _cgst: "", _sgst: "", _igst: "" });
const blank = () => ({ customer_id: "", items: [blankLine()], status: "PENDING", notes: "", currency: "INR", exchange_rate: 1, salesperson: "", reference: "", payment_terms: "", place_of_supply: "", delivery_address: "" });

const lineTaxable = (l) => {
  const base = (parseFloat(l.quantity) || 0) * (parseFloat(l.unit_price) || 0);
  return base - base * (parseFloat(l.discount) || 0) / 100;
};
const lineGst = (l) => lineTaxable(l) * (parseFloat(l.gst_rate) || 0) / 100;
const lineTotal = (l) => lineTaxable(l) + lineGst(l);

function numberToWords(amount) {
  const ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"];
  const tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"];
  const convert = (n) => {
    if (n < 20) return ones[n];
    if (n < 100) return tens[Math.floor(n / 10)] + (n % 10 ? " " + ones[n % 10] : "");
    if (n < 1000) return ones[Math.floor(n / 100)] + " Hundred" + (n % 100 ? " " + convert(n % 100) : "");
    if (n < 100000) return convert(Math.floor(n / 1000)) + " Thousand" + (n % 1000 ? " " + convert(n % 1000) : "");
    if (n < 10000000) return convert(Math.floor(n / 100000)) + " Lakh" + (n % 100000 ? " " + convert(n % 100000) : "");
    return convert(Math.floor(n / 10000000)) + " Crore" + (n % 10000000 ? " " + convert(n % 10000000) : "");
  };
  const n = Math.floor(Math.abs(amount));
  const paise = Math.round((Math.abs(amount) - n) * 100);
  let result = (n === 0 ? "Zero" : convert(n)) + " Rupees";
  if (paise > 0) result += " and " + convert(paise) + " Paise";
  return result + " Only";
}

// Customer search is now the shared, keyboard-navigable PartySearch component
// (see components/PartySearch.jsx) — this page's own copy had no Arrow/Enter
// support at all; consolidating fixes that for every page that adopts it.

/* Product search for line items */
export default function SalesOrders() {
  const [orders, setOrders] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank());
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);

  const sel = useBulkSelect(orders);

  const load = async () => {
    const [r, c, p] = await Promise.all([
      api.get("/sales-orders"),
      api.get("/customers"),
      api.get("/products"),
    ]);
    setOrders(r.data);
    setCustomers(Array.isArray(c.data) ? c.data : (c.data?.items ?? []));
    setProducts(Array.isArray(p.data) ? p.data : (p.data?.items ?? []));
  };

  useEffect(() => { load(); }, []);

  const bulkDelete = async () => {
    const { ok, failed } = await sel.runDelete(
      (id) => api.delete(`/sales-orders/${id}`),
      { reload: load }
    );
    if (failed) toast.error(`Deleted ${ok}, failed ${failed}`);
    else toast.success(`Deleted ${ok} order${ok === 1 ? "" : "s"}`);
  };

  const setLine = (idx, patch) =>
    setForm((f) => ({ ...f, items: f.items.map((l, i) => (i === idx ? { ...l, ...patch } : l)) }));
  const addLine = () => setForm((f) => ({ ...f, items: [...f.items, blankLine()] }));
  const removeLine = (idx) => setForm((f) => ({ ...f, items: f.items.filter((_, i) => i !== idx) }));
  const insertLineAfter = (idx) =>
    setForm((f) => {
      const items = [...f.items];
      items.splice(idx + 1, 0, blankLine());
      return { ...f, items };
    });
  const removeLineKeepingOne = (idx) =>
    setForm((f) => ({
      ...f,
      items: f.items.length > 1 ? f.items.filter((_, i) => i !== idx) : [blankLine()],
    }));

  // Keyboard-first line-item entry (Tally-style): Product → Qty → Unit →
  // Rate → Discount, then Enter on the last column of the last row appends a
  // new row and focuses its Product cell. Arrow keys move between cells;
  // Insert adds a row after the current one; Ctrl+Delete removes the current
  // row. Columns 0-4 are fixed (Product/Qty/Unit/Rate/Discount); column 5+ is
  // the GST-rate sub-widget, whose SHAPE varies per row: 1 input for plain
  // GST% or IGST%, 2 inputs (col 5 = CGST, col 6 = SGST) for CGST+SGST. This
  // is exactly what useGridKeyNav's per-row colCount function exists for —
  // Enter/Arrow keep working seamlessly across the shape change instead of
  // falling back to Tab/click once GST type is toggled mid-entry.
  const gstColsForRow = (row) => (form.items[row]?._gst_type === "CGST_SGST" ? 7 : 6);
  const gridNav = useGridKeyNav({
    rowCount: form.items.length,
    colCount: gstColsForRow,
    onRowComplete: addLine,
    onInsertRow: insertLineAfter,
    onDeleteRow: removeLineKeepingOne,
  });
  const toggleLineManual = (idx) =>
    setForm((f) => ({
      ...f,
      items: f.items.map((l, i) => i === idx ? { ...l, _manual: !l._manual, product_id: "", product_name: "" } : l),
    }));

  const setGstType = (idx, type) =>
    setForm((f) => ({
      ...f,
      items: f.items.map((l, i) => {
        if (i !== idx) return l;
        const cur = parseFloat(l.gst_rate) || 0;
        if (type === "GST")       return { ...l, _gst_type: type };
        if (type === "CGST_SGST") return { ...l, _gst_type: type, _cgst: cur / 2, _sgst: cur / 2 };
        if (type === "IGST")      return { ...l, _gst_type: type, _igst: cur };
        return l;
      }),
    }));

  const pickProduct = (idx, pid, p) => {
    const price = p?.selling_price != null ? Number(p.selling_price) : (p?.cost_price != null ? Number(p.cost_price) : "");
    const gst = p?.gst_rate != null ? Number(p.gst_rate) : "";
    const half = gst !== "" ? gst / 2 : "";
    setLine(idx, {
      product_id: pid,
      product_name: p?.name || "",
      hsn_code: p?.hsn_code || "",
      unit: p?.unit || DEFAULT_UOM,
      unit_price: price,
      gst_rate: gst,
      _cgst: half,
      _sgst: half,
      _igst: gst,
    });
  };

  // Totals
  const subtotal = form.items.reduce((s, l) => s + lineTaxable(l), 0);
  const gstAmount = form.items.reduce((s, l) => s + lineGst(l), 0);
  const cgstAmount = form.items.reduce((s, l) => {
    if (l._gst_type !== "CGST_SGST") return s;
    return s + lineTaxable(l) * (parseFloat(l._cgst) || 0) / 100;
  }, 0);
  const sgstAmount = form.items.reduce((s, l) => {
    if (l._gst_type !== "CGST_SGST") return s;
    return s + lineTaxable(l) * (parseFloat(l._sgst) || 0) / 100;
  }, 0);
  const igstAmount = form.items.reduce((s, l) => {
    if (l._gst_type !== "IGST") return s;
    return s + lineTaxable(l) * (parseFloat(l._igst) || 0) / 100;
  }, 0);
  const hasCgstSgst = form.items.some((l) => l._gst_type === "CGST_SGST");
  const hasIgst = form.items.some((l) => l._gst_type === "IGST");
  const grandTotal = subtotal + gstAmount;

  const submit = async (e) => {
    e.preventDefault();
    if (!form.customer_id) return toast.error("Select a customer");
    if (form.items.length === 0) return toast.error("Add line items");
    const payload = {
      ...form,
      items: form.items
        .filter((i) => (i._manual ? i.product_name?.trim() : i.product_id) && Number(i.quantity) > 0)
        .map(({ _manual, _gst_type, _cgst, _sgst, _igst, ...i }) => ({
          ...i,
          product_id: _manual ? null : (i.product_id || null),
          product_name: i.product_name || "",
          quantity: Number(i.quantity),
          unit_price: Number(i.unit_price),
          discount: Number(i.discount) || 0,
          gst_rate: Number(i.gst_rate),
          gst_type: _gst_type || "GST",
          cgst_rate: _gst_type === "CGST_SGST" ? parseFloat(_cgst) || 0 : null,
          sgst_rate: _gst_type === "CGST_SGST" ? parseFloat(_sgst) || 0 : null,
          igst_rate: _gst_type === "IGST" ? parseFloat(_igst) || 0 : null,
        })),
    };
    if (saving) return;
    setSaving(true);
    try {
      if (editingId) await api.put(`/sales-orders/${editingId}`, payload);
      else await api.post("/sales-orders", payload);
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  // Enter-as-Tab data entry engine (see useEnterNavigation): Enter moves to
  // the next field anywhere in this form (customer/order-details fields,
  // falling through to the grid's own Enter handling inside the line-item
  // table), Ctrl+Enter saves, Ctrl+Shift+Enter saves and immediately opens a
  // fresh blank order, Escape cancels. Auto-focuses the Customer field the
  // moment the modal opens — no click required to start typing.
  //
  // onQuickCreate: Ctrl+Enter inside the Customer or a line's Product field
  // (both marked quickCreateType below) opens QuickCreateModal instead of
  // saving the order — see quickCreate state + handler further down.
  const [quickCreate, setQuickCreate] = useState(null); // { type, seed, lineIdx? } | null
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: open,
    autoFocus: true,
    onSave: () => submit(new Event("submit", { cancelable: true })),
    onSaveAndNew: async () => {
      await submit(new Event("submit", { cancelable: true }));
      openNew();
    },
    onCancel: () => setOpen(false),
    onQuickCreate: (type, fieldEl) => {
      const rowEl = fieldEl.closest("[data-row-index]");
      const lineIdx = rowEl ? Number(rowEl.dataset.rowIndex) : null;
      setQuickCreate({ type, seed: fieldEl.value, lineIdx });
    },
  });

  const handleQuickCreated = (record) => {
    const type = quickCreate?.type;
    const lineIdx = quickCreate?.lineIdx;
    setQuickCreate(null);
    if (type === "customer") {
      setCustomers((prev) => [...prev, record]);
      setForm((f) => ({ ...f, customer_id: record.id }));
    } else if (type === "item" && lineIdx != null) {
      setProducts((prev) => [...prev, record]);
      pickProduct(lineIdx, record.id, record);
    }
  };

  const onDelete = async (item) => {
    if (!window.confirm(`Delete ${item.order_number}?`)) return;
    try {
      await api.delete(`/sales-orders/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const onConfirm = async (item) => {
    if (!window.confirm("Confirm order? Stock will be deducted.")) return;
    try {
      await api.post(`/sales-orders/${item.id}/confirm`);
      toast.success("Confirmed");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const openNew = () => { setForm(blank()); setEditingId(null); setOpen(true); };
  const openEdit = (p) => {
    setForm({
      ...blank(),
      ...p,
      items: (p.items || []).map((i) => {
        const gst = i.gst_rate ?? "";
        const gstNum = parseFloat(gst) || 0;
        const gstType = i.gst_type || "GST";
        return {
          ...i,
          _manual: !i.product_id,
          quantity: i.quantity != null && i.quantity !== 0 ? i.quantity : "",
          unit_price: i.unit_price != null && i.unit_price !== 0 ? i.unit_price : "",
          discount: i.discount != null && i.discount !== 0 ? i.discount : "",
          gst_rate: i.gst_rate != null ? i.gst_rate : "",
          _gst_type: gstType,
          _cgst: gstType === "CGST_SGST" ? (i.cgst_rate ?? gstNum / 2) : gstNum / 2,
          _sgst: gstType === "CGST_SGST" ? (i.sgst_rate ?? gstNum / 2) : gstNum / 2,
          _igst: gstType === "IGST" ? (i.igst_rate ?? gstNum) : gstNum,
        };
      }),
    });
    setEditingId(p.id);
    setOpen(true);
  };

  // Global module shortcuts: Ctrl/Cmd+N → new order (when the list is showing,
  // not already editing one). Ctrl+Enter/Ctrl+Shift+Enter save this form
  // instead of Ctrl+S — see useEnterNavigation above — since Enter-based save
  // is the primary keyboard-first flow for a line-item voucher like this one.
  useModuleShortcuts({
    onNew: () => { if (!open) openNew(); },
  });

  const selectedCustomer = customers.find((c) => c.id === form.customer_id);

  return (
    <div data-testid="sales-orders-page">
      <PageHeader
        eyebrow="Sales"
        title="Sales Orders"
        description="Confirmed orders awaiting dispatch"
        actions={
          <PrimaryButton icon={Plus} testid="new-so" onClick={openNew}>
            New Order
          </PrimaryButton>
        }
      />

      {orders.length === 0 ? (
        <EmptyState message="No sales orders yet" />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="label-overline border-b border-border">
                <th className="px-3 py-2.5 w-10">
                  <SelectCheckbox
                    label="Select all orders"
                    checked={sel.allSelected}
                    indeterminate={sel.someSelected}
                    onChange={sel.toggleAll}
                  />
                </th>
                <th className="px-3 py-2.5">SO#</th>
                <th className="px-3 py-2.5">Customer</th>
                <th className="px-3 py-2.5">Items</th>
                <th className="px-3 py-2.5 text-right">Total</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">Created</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((p) => (
                <tr
                  key={p.id}
                  className={`border-b border-border hover:bg-muted/40 text-foreground ${sel.isSelected(p.id) ? "bg-primary/5" : ""}`}
                >
                  <td className="px-3 py-2.5">
                    <SelectCheckbox
                      label={`Select order ${p.order_number}`}
                      checked={sel.isSelected(p.id)}
                      onChange={() => sel.toggle(p.id)}
                    />
                  </td>
                  <td className="px-3 py-2.5 font-semibold text-primary">{p.order_number}</td>
                  <td className="px-3 py-2.5 text-foreground">{p.customer_name}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{p.items?.length}</td>
                  <td className="px-3 py-2.5 text-right tabular text-foreground font-semibold">
                    {fmtMoney(p.total, p.currency)}
                  </td>
                  <td className="px-3 py-2.5">
                    <Badge tone={STATUS_TONE[p.status] || "neutral"}>{p.status}</Badge>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-muted-foreground">
                    {new Date(p.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center justify-end gap-1.5">
                      {p.status === "PENDING" && (
                        <button
                          onClick={() => onConfirm(p)}
                          title="Confirm & deduct stock"
                          className="w-7 h-7 border border-border hover:border-green-500 hover:text-green-400 text-muted-foreground inline-flex items-center justify-center"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                      <button
                        onClick={() => downloadPdf(`/sales-orders/${p.id}/pdf`, `${p.order_number}.pdf`)}
                        title="Download PDF"
                        data-testid={`pdf-${p.id}`}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center"
                      >
                        <Download className="w-3.5 h-3.5" />
                      </button>
                      <SendEmailButton
                        docType="sales_order"
                        docId={p.id}
                        docNumber={p.order_number}
                        defaultRecipient={customers.find((c) => c.id === p.customer_id)?.email || ""}
                        defaultRecipientName={p.customer_name}
                      />
                      <button
                        onClick={() => openEdit(p)}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => onDelete(p)}
                        className="w-7 h-7 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground inline-flex items-center justify-center"
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
        title={editingId ? "Edit Sales Order" : "New Sales Order"}
        icon={FileText}
        size="full"
        bodyClassName="p-6 bg-[var(--bg)]"
        headerExtra={
          <div className="hidden items-center gap-3 sm:flex">
            <Badge tone={STATUS_TONE[form.status] || "neutral"}>{form.status}</Badge>
            <span className="rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground">
              Total <span className="font-semibold text-primary">₹{inr(grandTotal)}</span>
            </span>
          </div>
        }
        footer={
          <div className="flex w-full flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">
              Grand Total <span className="font-display font-bold text-base text-primary">₹{inr(grandTotal)}</span>
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                title="Print"
                onClick={() => toast.info("Print — use PDF download")}
                className="w-8 h-8 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center transition-colors"
              >
                <Printer className="w-4 h-4" />
              </button>
              <button
                type="button"
                title="WhatsApp"
                onClick={() => toast.info("WhatsApp sharing coming soon")}
                className="w-8 h-8 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center transition-colors"
              >
                <MessageCircle className="w-4 h-4" />
              </button>
              <button
                type="button"
                title="Export Excel"
                onClick={() => toast.info("Excel export coming soon")}
                className="w-8 h-8 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center transition-colors"
              >
                <FileSpreadsheet className="w-4 h-4" />
              </button>
              <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
              <PrimaryButton onClick={submit} testid="save-so" icon={FileText} disabled={saving}
                className="bg-gradient-to-r from-[#2563EB] to-[#1D4ED8]">
                {saving ? "Saving…" : (editingId ? "Save Changes" : "Create Order")}
              </PrimaryButton>
            </div>
          </div>
        }
      >
        <form ref={formRef} id="so-form" onSubmit={submit} className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="flex min-w-0 flex-col gap-6">

            {/* ── Customer Info ──────────────────────────────────────────── */}
            <FormSection title="Customer" icon={UsersRound} cols={4}>
              <Field label="Customer" required>
                <PartySearch
                  parties={customers}
                  value={form.customer_id}
                  onChange={(id) => setForm({ ...form, customer_id: id })}
                  placeholder="Search customer…"
                  quickCreateType="customer"
                />
              </Field>
              {selectedCustomer ? (
                <>
                  <Field label="GSTIN">
                    <Input value={selectedCustomer.gstin || "—"} disabled />
                  </Field>
                  <Field label="State">
                    <Input value={selectedCustomer.state || "—"} disabled />
                  </Field>
                  <Field label="Contact">
                    <Input value={selectedCustomer.phone || selectedCustomer.email || "—"} disabled />
                  </Field>
                </>
              ) : (
                <>
                  <Field label="GSTIN"><Input placeholder="Auto-filled" disabled /></Field>
                  <Field label="State"><Input placeholder="Auto-filled" disabled /></Field>
                  <Field label="Contact"><Input placeholder="Auto-filled" disabled /></Field>
                </>
              )}
            </FormSection>

            {/* ── Order Details ─────────────────────────────────────────── */}
            <FormSection title="Order Details" icon={FileText} cols={4}>
              <Field label="Status">
                <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  {SO_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </Select>
              </Field>
              <Field label="Reference No.">
                <Input value={form.reference || ""} placeholder="Your ref / PO no."
                  onChange={(e) => setForm({ ...form, reference: e.target.value })} />
              </Field>
              <Field label="Salesperson">
                <Input value={form.salesperson || ""} placeholder="Name"
                  onChange={(e) => setForm({ ...form, salesperson: e.target.value })} />
              </Field>
              <Field label="Payment Terms">
                <Input value={form.payment_terms || ""} placeholder="e.g. Net 30"
                  onChange={(e) => setForm({ ...form, payment_terms: e.target.value })} />
              </Field>
              <Field label="Place of Supply">
                <Input value={form.place_of_supply || ""} placeholder="State / city"
                  onChange={(e) => setForm({ ...form, place_of_supply: e.target.value })} />
              </Field>
              <Field label="Delivery Address">
                <Input value={form.delivery_address || ""} placeholder="Ship-to address"
                  onChange={(e) => setForm({ ...form, delivery_address: e.target.value })} />
              </Field>
              <Field label="Currency" hint="Single-currency for now">
                <Select disabled value={form.currency}>
                  <option value="INR">INR ₹</option>
                </Select>
              </Field>
              <Field label="Remarks">
                <Input value={form.notes || ""} placeholder="Short note"
                  onChange={(e) => setForm({ ...form, notes: e.target.value })} />
              </Field>
            </FormSection>

            {/* ── Line Items ────────────────────────────────────────────── */}
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
                <table data-grid-managed className="w-full text-left text-xs" style={{ minWidth: "1400px" }}>
                  <colgroup>
                    <col style={{ width: "40px" }} />
                    <col style={{ width: "260px" }} />
                    <col style={{ width: "100px" }} />
                    <col style={{ width: "80px" }} />
                    <col style={{ width: "70px" }} />
                    <col style={{ width: "110px" }} />
                    <col style={{ width: "80px" }} />
                    <col style={{ width: "100px" }} />
                    <col style={{ width: "210px" }} />
                    <col style={{ width: "100px" }} />
                    <col style={{ width: "110px" }} />
                    <col style={{ width: "44px" }} />
                  </colgroup>
                  <thead className="sticky top-0 z-10">
                    <tr className="border-b border-border bg-muted text-muted-foreground">
                      <th className="px-2 py-2.5 text-center font-semibold">#</th>
                      <th className="px-2 py-2.5 font-semibold">Product</th>
                      <th className="px-2 py-2.5 font-semibold">HSN/SAC</th>
                      <th className="px-2 py-2.5 text-right font-semibold">Qty</th>
                      <th className="px-2 py-2.5 font-semibold">Unit</th>
                      <th className="px-2 py-2.5 text-right font-semibold">Rate ₹</th>
                      <th className="px-2 py-2.5 text-right font-semibold">Disc %</th>
                      <th className="px-2 py-2.5 text-right font-semibold">Taxable</th>
                      <th className="px-2 py-2.5 font-semibold">GST</th>
                      <th className="px-2 py-2.5 text-right font-semibold">GST Amt</th>
                      <th className="px-2 py-2.5 text-right font-semibold">Total ₹</th>
                      <th className="px-2 py-2.5 text-center font-semibold">Del</th>
                    </tr>
                  </thead>
                  <tbody>
                    {form.items.map((l, idx) => (
                      <tr key={idx} data-row-index={idx} className="border-b border-border align-top hover:bg-muted/30">
                        <td className="px-2 py-2 text-center align-middle text-muted-foreground">{idx + 1}</td>
                        <td className="px-2 py-2">
                          <div className="flex items-start gap-1.5">
                            <button
                              type="button"
                              title={l._manual ? "Switch to catalog product" : "Enter product manually"}
                              onClick={() => toggleLineManual(idx)}
                              className={`mt-px flex h-10 w-9 flex-shrink-0 items-center justify-center rounded-lg border transition-colors ${l._manual ? "border-[var(--warning)] text-[var(--warning)]" : "border-border text-muted-foreground hover:border-primary hover:text-primary"}`}
                            >
                              {l._manual ? <PenLine className="h-4 w-4" /> : <Package className="h-4 w-4" />}
                            </button>
                            {l._manual ? (
                              <Input
                                placeholder="Product name (manual)"
                                value={l.product_name}
                                onChange={(e) => setLine(idx, { product_name: e.target.value })}
                                ref={gridNav.registerCell(idx, 0)}
                                onKeyDown={gridNav.handleKeyDown(idx, 0)}
                                className="h-10"
                              />
                            ) : (
                              <div className="flex-1 min-w-0">
                                <ItemSearch
                                  products={products}
                                  value={l.product_id}
                                  onChange={(pid, p) => pickProduct(idx, pid, p)}
                                  inputRef={gridNav.registerCell(idx, 0)}
                                  onKeyDown={gridNav.handleKeyDown(idx, 0)}
                                  quickCreateType="item"
                                />
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="px-2 py-2">
                          <Input placeholder="e.g. 7308" value={l.hsn_code || ""}
                            onChange={(e) => setLine(idx, { hsn_code: e.target.value })} className="h-10" />
                        </td>
                        <td className="px-2 py-2">
                          <NumericInput compact value={l.quantity} onChange={(v) => setLine(idx, { quantity: v })} placeholder="0"
                            ref={gridNav.registerCell(idx, 1)} onKeyDown={gridNav.handleKeyDown(idx, 1)} className="h-10 w-full" />
                        </td>
                        <td className="px-2 py-2">
                          <Select value={l.unit || DEFAULT_UOM} onChange={(e) => setLine(idx, { unit: e.target.value })}
                            ref={gridNav.registerCell(idx, 2)} onKeyDown={gridNav.handleKeyDown(idx, 2)} className="h-10">
                            {l.unit && !STANDARD_UOMS.includes(l.unit) && (
                              <option key={l.unit} value={l.unit}>{l.unit}</option>
                            )}
                            {STANDARD_UOMS.map((u) => <option key={u} value={u}>{u}</option>)}
                          </Select>
                        </td>
                        <td className="px-2 py-2">
                          <NumericInput compact value={l.unit_price} onChange={(v) => setLine(idx, { unit_price: v })} placeholder="0.00"
                            ref={gridNav.registerCell(idx, 3)} onKeyDown={gridNav.handleKeyDown(idx, 3)} className="h-10 w-full" />
                        </td>
                        <td className="px-2 py-2">
                          <NumericInput compact value={l.discount} onChange={(v) => setLine(idx, { discount: v })} placeholder="0" max={100}
                            ref={gridNav.registerCell(idx, 4)} onKeyDown={gridNav.handleKeyDown(idx, 4)} className="h-10 w-full" />
                        </td>
                        <td className="px-2 py-2 text-right align-middle tabular text-muted-foreground">
                          ₹{inr(lineTaxable(l))}
                        </td>
                        <td className="px-2 py-2">
                          <div className="space-y-1.5">
                            <div className="flex flex-wrap gap-1">
                              {["GST", "CGST+SGST", "IGST"].map((label) => {
                                const key = label === "CGST+SGST" ? "CGST_SGST" : label;
                                const active = l._gst_type === key;
                                return (
                                  <button
                                    key={key}
                                    type="button"
                                    onClick={() => setGstType(idx, key)}
                                    className={`rounded-md border px-1.5 py-0.5 text-[10px] font-medium transition-colors ${active ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground hover:border-primary hover:text-primary"}`}
                                  >
                                    {label}
                                  </button>
                                );
                              })}
                            </div>
                            {l._gst_type === "GST" && (
                              <NumericInput compact value={l.gst_rate} onChange={(v) => setLine(idx, { gst_rate: v })} placeholder="18" max={100} aria-label="GST %"
                                ref={gridNav.registerCell(idx, 5)} onKeyDown={gridNav.handleKeyDown(idx, 5)} className="h-9 w-full" />
                            )}
                            {l._gst_type === "CGST_SGST" && (
                              <div className="flex gap-1">
                                <NumericInput compact value={l._cgst} onChange={(v) => { const n = parseFloat(v) || 0; setLine(idx, { _cgst: v, gst_rate: n + (parseFloat(l._sgst) || 0) }); }} placeholder="9" max={100} aria-label="CGST %"
                                  ref={gridNav.registerCell(idx, 5)} onKeyDown={gridNav.handleKeyDown(idx, 5)} className="h-9 w-1/2" />
                                <NumericInput compact value={l._sgst} onChange={(v) => { const n = parseFloat(v) || 0; setLine(idx, { _sgst: v, gst_rate: (parseFloat(l._cgst) || 0) + n }); }} placeholder="9" max={100} aria-label="SGST %"
                                  ref={gridNav.registerCell(idx, 6)} onKeyDown={gridNav.handleKeyDown(idx, 6)} className="h-9 w-1/2" />
                              </div>
                            )}
                            {l._gst_type === "IGST" && (
                              <NumericInput compact value={l._igst} onChange={(v) => { setLine(idx, { _igst: v, gst_rate: v }); }} placeholder="18" max={100} aria-label="IGST %"
                                ref={gridNav.registerCell(idx, 5)} onKeyDown={gridNav.handleKeyDown(idx, 5)} className="h-9 w-full" />
                            )}
                          </div>
                        </td>
                        <td className="px-2 py-2 text-right align-middle tabular text-muted-foreground">
                          ₹{inr(lineGst(l))}
                        </td>
                        <td className="px-2 py-2 text-right align-middle tabular font-semibold text-foreground">
                          ₹{inr(lineTotal(l))}
                        </td>
                        <td className="px-2 py-2 text-center align-middle">
                          <button type="button" onClick={() => removeLine(idx)} aria-label="Remove line"
                            className="flex h-9 w-9 items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:border-[var(--danger)] hover:bg-[#FEE2E2] hover:text-[var(--danger)] mx-auto">
                            <X className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </FormSection>
          </div>

          {/* ── Right rail: customer info + order summary ─────────────── */}
          <aside className="flex min-w-0 flex-col gap-6">
            <div className="lg:sticky lg:top-4 flex flex-col gap-6">

              {/* Customer card */}
              {selectedCustomer && (
                <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <h3 className="mb-3 font-display font-semibold text-sm text-foreground flex items-center gap-2">
                    <UsersRound className="w-4 h-4 text-primary" /> Customer Details
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div>
                      <div className="label-overline">Company</div>
                      <div className="font-semibold text-foreground">{selectedCustomer.company || selectedCustomer.name}</div>
                    </div>
                    {selectedCustomer.gstin && (
                      <div>
                        <div className="label-overline">GSTIN</div>
                        <div className="font-mono text-foreground">{selectedCustomer.gstin}</div>
                      </div>
                    )}
                    {selectedCustomer.address && (
                      <div>
                        <div className="label-overline">Address</div>
                        <div className="text-muted-foreground text-xs">{selectedCustomer.address}</div>
                      </div>
                    )}
                    {(selectedCustomer.phone || selectedCustomer.email) && (
                      <div>
                        <div className="label-overline">Contact</div>
                        <div className="text-xs text-muted-foreground">{selectedCustomer.phone || selectedCustomer.email}</div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Order Summary */}
              <SummaryCard
                title="Order Summary"
                rows={[
                  { label: "Subtotal (taxable)", value: `₹${inr(subtotal)}` },
                  ...(hasCgstSgst ? [
                    { label: "CGST", value: `₹${inr(cgstAmount)}` },
                    { label: "SGST", value: `₹${inr(sgstAmount)}` },
                  ] : []),
                  ...(hasIgst ? [{ label: "IGST", value: `₹${inr(igstAmount)}` }] : []),
                  ...(!hasCgstSgst && !hasIgst ? [{ label: "GST", value: `₹${inr(gstAmount)}` }] : []),
                ]}
                total={{ label: "Grand Total", value: `₹${inr(grandTotal)}` }}
                footer={
                  <div className="space-y-2">
                    <div className="text-center">
                      <div className="label-overline">Grand Total</div>
                      <div className="font-display text-2xl font-bold text-primary">₹{inr(grandTotal)}</div>
                    </div>
                    <div className="border-t border-border pt-2 text-[10px] text-muted-foreground text-center leading-snug">
                      {numberToWords(grandTotal)}
                    </div>
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
        noun="order"
      />

      <QuickCreateModal
        open={!!quickCreate}
        type={quickCreate?.type}
        seedName={quickCreate?.seed}
        onClose={() => setQuickCreate(null)}
        onCreated={handleQuickCreated}
      />
    </div>
  );
}
