import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Field, Select, EmptyState,
  FormSection, SummaryCard, Badge, NumericInput,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import ItemSearch from "@/components/ItemSearch";
import PartySearch from "@/components/PartySearch";
import QuickCreateModal from "@/components/QuickCreateModal";
import EwayBillSection from "@/components/EwayBillSection";
import { downloadPdf, fmtMoney } from "@/lib/currency";
import SendEmailButton from "@/components/SendEmailButton";
import BulkDeleteBar, { SelectCheckbox } from "@/components/BulkDeleteBar";
import useBulkSelect from "@/hooks/useBulkSelect";
import useGridKeyNav from "@/hooks/useGridKeyNav";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import {
  Plus, X, Pencil, Trash2, Download, IndianRupee, Sparkles, FileJson, Truck,
  QrCode, ShieldAlert, Share2, Receipt, Package, UsersRound, FileText,
  PenLine, Printer, MessageCircle, FileSpreadsheet,
} from "lucide-react";

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const UOM_OPTIONS = ["pcs", "nos", "kg", "g", "mg", "l", "ml", "m", "cm", "mm", "ft", "inch", "box", "pair", "set", "bag", "roll", "sheet", "mtr", "sqft", "sqm", "hr", "day"];
const UOM_LABELS = { pcs: "Pcs", nos: "Nos", mtr: "Mtr" };
const uomLabel = (u) => UOM_LABELS[u] || u;
const INV_TYPES = ["TAX_INVOICE", "EXPORT_INVOICE", "DEBIT_NOTE", "CREDIT_NOTE", "PURCHASE_INVOICE"];
const STATUS_TONE = { UNPAID: "danger", PARTIAL: "warning", PAID: "success", CANCELLED: "neutral" };

const blankLine = () => ({ product_id: "", product_name: "", hsn_code: "", unit: "pcs", quantity: "", unit_price: "", discount: "", gst_rate: "", _manual: false, _gst_type: "GST", _cgst: "", _sgst: "", _igst: "" });
const blank = () => ({
  customer_id: "", invoice_type: "TAX_INVOICE", items: [blankLine()], status: "UNPAID",
  payment_received: "", notes: "", currency: "INR", exchange_rate: 1,
  salesperson: "", reference: "", payment_terms: "", place_of_supply: "",
  transport: "", vehicle_no: "", lr_no: "", dispatch_through: "",
});

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
export default function Invoices() {
  const [items, setItems] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank());
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [paymentItem, setPaymentItem] = useState(null);
  const [paymentAmount, setPaymentAmount] = useState(0);
  const [einvoiceItem, setEinvoiceItem] = useState(null);
  const [ewbItem, setEwbItem] = useState(null);

  const sel = useBulkSelect(items);

  const load = async () => {
    const r = await api.get("/invoices");
    setItems(r.data);
  };

  useEffect(() => {
    load();
    api.get("/customers").then((r) => setCustomers(Array.isArray(r.data) ? r.data : (r.data?.items ?? [])));
    api.get("/products").then((r) => setProducts(Array.isArray(r.data) ? r.data : (r.data?.items ?? [])));
  }, []);

  const bulkDelete = async () => {
    const { ok, failed } = await sel.runDelete(
      (id) => api.delete(`/invoices/${id}`),
      { reload: load }
    );
    if (failed) toast.error(`Deleted ${ok}, failed ${failed}`);
    else toast.success(`Deleted ${ok} invoice${ok === 1 ? "" : "s"}`);
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
    const gst = p?.gst_rate != null ? Number(p.gst_rate) : 18;
    setLine(idx, {
      product_id: pid,
      product_name: p?.name || "",
      hsn_code: p?.hsn_code || "",
      unit: p?.unit || "pcs",
      unit_price: p?.selling_price != null ? Number(p.selling_price) : (p?.cost_price != null ? Number(p.cost_price) : ""),
      gst_rate: gst,
      _cgst: gst / 2,
      _sgst: gst / 2,
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
  const outstanding = grandTotal - (parseFloat(form.payment_received) || 0);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.customer_id) return toast.error("Select a customer");
    if (form.items.length === 0) return toast.error("Add line items");
    const payload = {
      ...form,
      payment_received: parseFloat(form.payment_received) || 0,
      items: form.items
        .filter((i) => (i._manual ? i.product_name?.trim() : i.product_id) && parseFloat(i.quantity) > 0)
        .map(({ _manual, _gst_type, _cgst, _sgst, _igst, ...i }) => ({
          ...i,
          product_id: _manual ? null : (i.product_id || null),
          product_name: i.product_name || "",
          quantity: parseFloat(i.quantity) || 0,
          unit_price: parseFloat(i.unit_price) || 0,
          discount: parseFloat(i.discount) || 0,
          gst_rate: parseFloat(i.gst_rate) || 0,
          gst_type: _gst_type || "GST",
          cgst_rate: _gst_type === "CGST_SGST" ? parseFloat(_cgst) || 0 : null,
          sgst_rate: _gst_type === "CGST_SGST" ? parseFloat(_sgst) || 0 : null,
          igst_rate: _gst_type === "IGST" ? parseFloat(_igst) || 0 : null,
        })),
    };
    if (saving) return;
    setSaving(true);
    try {
      if (editingId) await api.put(`/invoices/${editingId}`, payload);
      else await api.post("/invoices", payload);
      toast.success("Invoice Saved Successfully");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async (item) => {
    if (!window.confirm(`Delete ${item.invoice_number}?`)) return;
    try {
      await api.delete(`/invoices/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  // Enter-as-Tab data entry engine (see useEnterNavigation): Enter moves to
  // the next field anywhere in this form (customer/invoice-details fields,
  // falling through to the grid's own Enter handling inside the line-item
  // table), Ctrl+Enter saves, Ctrl+Shift+Enter saves and immediately opens a
  // fresh blank invoice, Escape cancels. Auto-focuses the Customer field the
  // moment the modal opens — no click required to start typing.
  //
  // onQuickCreate: Ctrl+Enter inside the Customer or a line's Product field
  // (both marked quickCreateType below) opens QuickCreateModal instead of
  // saving the invoice — see quickCreate state + handler further down.
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

  const recordPayment = async () => {
    if (!paymentAmount || paymentAmount <= 0) return toast.error("Enter a valid amount");
    try {
      await api.post(`/invoices/${paymentItem.id}/payment?amount=${paymentAmount}`);
      toast.success("Payment recorded");
      setPaymentItem(null);
      setPaymentAmount(0);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const handleGenerateEinvoice = async (invoiceId) => {
    try {
      const res = await api.post(`/invoices/${invoiceId}/generate-einvoice`);
      toast.success("E-Invoice generated successfully!");
      setEinvoiceItem(res.data);
      load();
    } catch (e) {
      toast.error("Failed to generate E-Invoice.");
    }
  };

  const handleCancelEinvoice = async (invoiceId) => {
    if (!window.confirm("Are you sure you want to cancel this E-Invoice on the GST Portal?")) return;
    try {
      const res = await api.post(`/invoices/${invoiceId}/cancel-einvoice`);
      toast.success("E-Invoice cancelled successfully.");
      setEinvoiceItem(res.data);
      load();
    } catch (e) {
      toast.error("Failed to cancel E-Invoice.");
    }
  };

  const handleDownloadEinvoiceJson = async (invoice) => {
    try {
      const res = await api.get(`/invoices/${invoice.id}/einvoice-json`);
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `e-invoice-${invoice.invoice_number}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      toast.success("E-Invoice JSON schema downloaded.");
    } catch (e) {
      toast.error("Failed to download E-Invoice JSON.");
    }
  };

  const openNew = () => { setForm(blank()); setEditingId(null); setOpen(true); };

  // Global module shortcuts: Ctrl/Cmd+N → new invoice, Ctrl/Cmd+S → save
  // the open form (mirrors the "click New Invoice" / "click Save" buttons).
  useModuleShortcuts({
    onNew: () => { if (!open) openNew(); },
    onSave: () => { if (open) submit(new Event("submit")); },
  });
  const openEdit = (p) => {
    setForm({
      ...blank(),
      ...p,
      items: (p.items || []).map((i) => {
        const gst = i.gst_rate ?? 18;
        const gstType = i.gst_type || "GST";
        return {
          ...i,
          _manual: !i.product_id,
          discount: i.discount ?? 0,
          _gst_type: gstType,
          _cgst: gstType === "CGST_SGST" ? (i.cgst_rate ?? gst / 2) : gst / 2,
          _sgst: gstType === "CGST_SGST" ? (i.sgst_rate ?? gst / 2) : gst / 2,
          _igst: gstType === "IGST" ? (i.igst_rate ?? gst) : gst,
        };
      }),
    });
    setEditingId(p.id);
    setOpen(true);
  };

  const selectedCustomer = customers.find((c) => c.id === form.customer_id);

  return (
    <div data-testid="invoices-page">
      <PageHeader
        eyebrow="Sales"
        title="GST Invoice Registry"
        description="Generate Tax Invoices, manage E-Invoices and E-Way Bills."
        actions={
          <PrimaryButton icon={Plus} testid="new-invoice" onClick={openNew}>
            New Invoice
          </PrimaryButton>
        }
      />

      {items.length === 0 ? (
        <EmptyState message="No invoices yet" />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="border-b border-border label-overline">
                <th className="px-3 py-2.5 w-10">
                  <SelectCheckbox
                    label="Select all invoices"
                    checked={sel.allSelected}
                    indeterminate={sel.someSelected}
                    onChange={sel.toggleAll}
                  />
                </th>
                <th className="px-3 py-2.5">Invoice#</th>
                <th className="px-3 py-2.5">Type</th>
                <th className="px-3 py-2.5">Customer</th>
                <th className="px-3 py-2.5 text-right">Taxable</th>
                <th className="px-3 py-2.5 text-right">GST</th>
                <th className="px-3 py-2.5 text-right">Total</th>
                <th className="px-3 py-2.5">E-Portal</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => {
                const out = Number(p.total || 0) - Number(p.payment_received || 0);
                const gst_disp = p.igst > 0 ? `${fmtMoney(p.igst, p.currency)} IGST` : `${fmtMoney((p.cgst || 0) + (p.sgst || 0), p.currency)} C+S`;
                return (
                  <tr
                    key={p.id}
                    className={`border-b border-border hover:bg-muted/40 text-foreground ${sel.isSelected(p.id) ? "bg-primary/5" : ""}`}
                  >
                    <td className="px-3 py-2.5">
                      <SelectCheckbox
                        label={`Select invoice ${p.invoice_number}`}
                        checked={sel.isSelected(p.id)}
                        onChange={() => sel.toggle(p.id)}
                      />
                    </td>
                    <td className="px-3 py-2.5 font-semibold text-primary">{p.invoice_number}</td>
                    <td className="px-3 py-2.5 text-xs text-muted-foreground">{p.invoice_type?.replace("_", " ")}</td>
                    <td className="px-3 py-2.5 text-foreground">{p.customer_name}</td>
                    <td className="px-3 py-2.5 text-right tabular text-muted-foreground">{fmtMoney(p.taxable_value || p.subtotal, p.currency)}</td>
                    <td className="px-3 py-2.5 text-right tabular text-xs text-muted-foreground">{gst_disp}</td>
                    <td className="px-3 py-2.5 text-right tabular font-bold text-foreground">{fmtMoney(p.total, p.currency)}</td>
                    <td className="px-3 py-2.5">
                      <div className="flex flex-col gap-0.5 text-[9px] uppercase">
                        <span className="flex items-center gap-1">
                          E-Inv: <span className={p.einvoice_status === "GENERATED" ? "text-[var(--success)] font-bold" : p.einvoice_status === "CANCELLED" ? "text-[var(--danger)]" : "text-muted-foreground"}>{p.einvoice_status || "PENDING"}</span>
                        </span>
                        <span className="flex items-center gap-1">
                          E-Way: <span className={p.ewb_status === "GENERATED" ? "text-[var(--success)] font-bold" : "text-muted-foreground"}>{p.ewb_status || "PENDING"}</span>
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                      <Badge tone={STATUS_TONE[p.status] || "neutral"}>{p.status}</Badge>
                    </td>
                    <td className="px-3 py-2.5 text-xs text-muted-foreground">{new Date(p.created_at).toLocaleDateString()}</td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center justify-end gap-1.5">
                        <button onClick={() => setEinvoiceItem(p)} title="E-Invoice Details"
                          className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center">
                          <QrCode className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => setEwbItem(p)} title="E-Way Bill"
                          className="w-7 h-7 border border-border hover:border-green-500 hover:text-green-400 text-muted-foreground inline-flex items-center justify-center">
                          <Truck className="w-3.5 h-3.5" />
                        </button>
                        {p.status !== "PAID" && (
                          <button onClick={() => { setPaymentItem(p); setPaymentAmount(out); }} title="Record Payment"
                            className="w-7 h-7 border border-border hover:border-green-500 hover:text-green-400 text-muted-foreground inline-flex items-center justify-center">
                            <IndianRupee className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <button onClick={() => downloadPdf(`/invoices/${p.id}/pdf`, `${p.invoice_number}.pdf`)}
                          title="Download PDF" data-testid={`pdf-${p.id}`}
                          className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center">
                          <Download className="w-3.5 h-3.5" />
                        </button>
                        <SendEmailButton
                          docType="invoice" docId={p.id} docNumber={p.invoice_number}
                          defaultRecipient={customers.find((c) => c.id === p.customer_id)?.email || ""}
                          defaultRecipientName={p.customer_name}
                        />
                        <button
                          onClick={() => {
                            const text = `Hi, here is Invoice ${p.invoice_number}. Total: ${fmtMoney(p.total, p.currency)}.`;
                            window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank");
                          }}
                          title="Share via WhatsApp"
                          className="w-7 h-7 border border-border hover:border-green-500 hover:text-green-400 text-muted-foreground inline-flex items-center justify-center">
                          <Share2 className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => openEdit(p)}
                          className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center">
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => onDelete(p)}
                          className="w-7 h-7 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground inline-flex items-center justify-center">
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

      {/* ── Main Invoice Form Modal ───────────────────────────────────── */}
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editingId ? "Edit Invoice" : "New GST Tax Invoice"}
        icon={Receipt}
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
              {outstanding < grandTotal && <span className="ml-2 text-muted-foreground">Outstanding ₹{inr(outstanding)}</span>}
            </span>
            <div className="flex items-center gap-2">
              <button type="button" title="Print" onClick={() => toast.info("Use PDF download")}
                className="w-8 h-8 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center transition-colors">
                <Printer className="w-4 h-4" />
              </button>
              <button type="button" title="WhatsApp" onClick={() => toast.info("WhatsApp sharing coming soon")}
                className="w-8 h-8 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center transition-colors">
                <MessageCircle className="w-4 h-4" />
              </button>
              <button type="button" title="Export Excel" onClick={() => toast.info("Excel export coming soon")}
                className="w-8 h-8 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center transition-colors">
                <FileSpreadsheet className="w-4 h-4" />
              </button>
              <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
              <PrimaryButton onClick={submit} testid="save-invoice" icon={Receipt} disabled={saving}
                className="bg-gradient-to-r from-[#2563EB] to-[#1D4ED8]">
                {saving ? "Saving…" : (editingId ? "Save Changes" : "Save Invoice")}
              </PrimaryButton>
            </div>
          </div>
        }
      >
        <form ref={formRef} id="inv-form" onSubmit={submit} className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="flex min-w-0 flex-col gap-6">

            {/* ── Customer ──────────────────────────────────────────────── */}
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
                  <Field label="GSTIN"><Input value={selectedCustomer.gstin || "—"} disabled /></Field>
                  <Field label="State"><Input value={selectedCustomer.state || "—"} disabled /></Field>
                  <Field label="Contact"><Input value={selectedCustomer.phone || selectedCustomer.email || "—"} disabled /></Field>
                </>
              ) : (
                <>
                  <Field label="GSTIN"><Input placeholder="Auto-filled" disabled /></Field>
                  <Field label="State"><Input placeholder="Auto-filled" disabled /></Field>
                  <Field label="Contact"><Input placeholder="Auto-filled" disabled /></Field>
                </>
              )}
            </FormSection>

            {/* ── Invoice Details ───────────────────────────────────────── */}
            <FormSection title="Invoice Details" icon={FileText} cols={4}>
              <Field label="Invoice Type" required>
                <Select value={form.invoice_type} onChange={(e) => setForm({ ...form, invoice_type: e.target.value })}>
                  {INV_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
                </Select>
              </Field>
              <Field label="Reference No.">
                <Input value={form.reference || ""} placeholder="Your ref / SO no."
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
              <Field label="Transport / Carrier">
                <Input value={form.transport || ""} placeholder="Transporter name"
                  onChange={(e) => setForm({ ...form, transport: e.target.value })} />
              </Field>
              <Field label="Vehicle No.">
                <Input value={form.vehicle_no || ""} placeholder="e.g. MH12AB1234"
                  onChange={(e) => setForm({ ...form, vehicle_no: e.target.value })} />
              </Field>
              <Field label="LR No.">
                <Input value={form.lr_no || ""} placeholder="Lorry receipt no."
                  onChange={(e) => setForm({ ...form, lr_no: e.target.value })} />
              </Field>
              <Field label="Dispatch Through">
                <Input value={form.dispatch_through || ""} placeholder="Dispatch mode"
                  onChange={(e) => setForm({ ...form, dispatch_through: e.target.value })} />
              </Field>
              <Field label="Payment Received ₹">
                <NumericInput value={form.payment_received} onChange={v => setForm({ ...form, payment_received: v })} placeholder="0.00" align="left" />
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
                              onClick={() => toggleLineManual(idx)}
                              className={`mt-px flex h-10 w-9 flex-shrink-0 items-center justify-center rounded-lg border transition-colors ${l._manual ? "border-[var(--warning)] text-[var(--warning)]" : "border-border text-muted-foreground hover:border-primary hover:text-primary"}`}
                            >
                              {l._manual ? <PenLine className="h-4 w-4" /> : <Package className="h-4 w-4" />}
                            </button>
                            {l._manual ? (
                              <Input placeholder="Product name (manual)" value={l.product_name}
                                onChange={(e) => setLine(idx, { product_name: e.target.value })}
                                ref={gridNav.registerCell(idx, 0)}
                                onKeyDown={gridNav.handleKeyDown(idx, 0)}
                                className="h-10" />
                            ) : (
                              <div className="flex-1 min-w-0">
                                <ItemSearch products={products} value={l.product_id}
                                  onChange={(pid, p) => pickProduct(idx, pid, p)}
                                  inputRef={gridNav.registerCell(idx, 0)}
                                  onKeyDown={gridNav.handleKeyDown(idx, 0)}
                                  quickCreateType="item" />
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="px-2 py-2">
                          <Input placeholder="e.g. 7308" value={l.hsn_code || ""}
                            onChange={(e) => setLine(idx, { hsn_code: e.target.value })} className="h-10" />
                        </td>
                        <td className="px-2 py-2">
                          <NumericInput compact value={l.quantity} onChange={v => setLine(idx, { quantity: v })} placeholder="0"
                            ref={gridNav.registerCell(idx, 1)} onKeyDown={gridNav.handleKeyDown(idx, 1)} className="h-10 w-full" />
                        </td>
                        <td className="px-2 py-2">
                          <Select value={l.unit || "pcs"} onChange={(e) => setLine(idx, { unit: e.target.value })}
                            ref={gridNav.registerCell(idx, 2)} onKeyDown={gridNav.handleKeyDown(idx, 2)} className="h-10">
                            {UOM_OPTIONS.map((u) => <option key={u} value={u}>{uomLabel(u)}</option>)}
                          </Select>
                        </td>
                        <td className="px-2 py-2">
                          <NumericInput compact value={l.unit_price} onChange={v => setLine(idx, { unit_price: v })} placeholder="0.00"
                            ref={gridNav.registerCell(idx, 3)} onKeyDown={gridNav.handleKeyDown(idx, 3)} className="h-10 w-full" />
                        </td>
                        <td className="px-2 py-2">
                          <NumericInput compact value={l.discount} onChange={v => setLine(idx, { discount: v })} placeholder="0" max={100}
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
                                  <button key={key} type="button" onClick={() => setGstType(idx, key)}
                                    className={`rounded-md border px-1.5 py-0.5 text-[10px] font-medium transition-colors ${active ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground hover:border-primary hover:text-primary"}`}>
                                    {label}
                                  </button>
                                );
                              })}
                            </div>
                            {l._gst_type === "GST" && (
                              <NumericInput compact value={l.gst_rate} onChange={v => setLine(idx, { gst_rate: v })} placeholder="18" max={100} aria-label="GST %"
                                ref={gridNav.registerCell(idx, 5)} onKeyDown={gridNav.handleKeyDown(idx, 5)} className="h-9 w-full" />
                            )}
                            {l._gst_type === "CGST_SGST" && (
                              <div className="flex gap-1">
                                <NumericInput compact value={l._cgst} onChange={v => { const n = parseFloat(v) || 0; setLine(idx, { _cgst: v, gst_rate: n + (parseFloat(l._sgst) || 0) }); }} placeholder="9" max={100} aria-label="CGST %"
                                  ref={gridNav.registerCell(idx, 5)} onKeyDown={gridNav.handleKeyDown(idx, 5)} className="h-9 w-1/2" />
                                <NumericInput compact value={l._sgst} onChange={v => { const n = parseFloat(v) || 0; setLine(idx, { _sgst: v, gst_rate: (parseFloat(l._cgst) || 0) + n }); }} placeholder="9" max={100} aria-label="SGST %"
                                  ref={gridNav.registerCell(idx, 6)} onKeyDown={gridNav.handleKeyDown(idx, 6)} className="h-9 w-1/2" />
                              </div>
                            )}
                            {l._gst_type === "IGST" && (
                              <NumericInput compact value={l._igst} onChange={v => { setLine(idx, { _igst: v, gst_rate: v }); }} placeholder="18" max={100} aria-label="IGST %"
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

          {/* ── Right rail ────────────────────────────────────────────── */}
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
                  </div>
                </div>
              )}

              {/* Invoice Summary */}
              <SummaryCard
                title="Invoice Summary"
                rows={[
                  { label: "Taxable (subtotal)", value: `₹${inr(subtotal)}` },
                  ...(hasCgstSgst ? [
                    { label: "CGST", value: `₹${inr(cgstAmount)}` },
                    { label: "SGST", value: `₹${inr(sgstAmount)}` },
                  ] : []),
                  ...(hasIgst ? [{ label: "IGST", value: `₹${inr(igstAmount)}` }] : []),
                  ...(!hasCgstSgst && !hasIgst ? [{ label: "GST", value: `₹${inr(gstAmount)}` }] : []),
                  ...(Number(form.payment_received) > 0 ? [{ label: "Paid", value: `₹${inr(form.payment_received)}` }] : []),
                ]}
                total={{ label: "Grand Total", value: `₹${inr(grandTotal)}` }}
                footer={
                  <div className="space-y-2">
                    <div className="text-center">
                      <div className="label-overline">Grand Total</div>
                      <div className="font-display text-2xl font-bold text-primary">₹{inr(grandTotal)}</div>
                    </div>
                    {outstanding > 0 && outstanding < grandTotal && (
                      <div className="text-center">
                        <div className="label-overline">Outstanding</div>
                        <div className="font-semibold text-[var(--danger)]">₹{inr(outstanding)}</div>
                      </div>
                    )}
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

      {/* ── Record Payment Modal (preserved unchanged) ────────────────── */}
      <Modal
        open={!!paymentItem}
        onClose={() => setPaymentItem(null)}
        title={`Record Payment · ${paymentItem?.invoice_number || ""}`}
        size="sm"
        footer={
          <>
            <SecondaryButton onClick={() => setPaymentItem(null)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={recordPayment}>Record</PrimaryButton>
          </>
        }
      >
        {paymentItem && (
          <div className="space-y-3">
            <div className="text-sm text-muted-foreground">
              Outstanding: <span className="text-[var(--danger)] tabular font-semibold">
                {fmtMoney(Number(paymentItem.total || 0) - Number(paymentItem.payment_received || 0), paymentItem.currency)}
              </span>
            </div>
            <Field label={`Amount received (${paymentItem.currency || "INR"})`}>
              <NumericInput value={paymentAmount} onChange={(v) => setPaymentAmount(v)} placeholder="0.00" align="left" />
            </Field>
          </div>
        )}
      </Modal>

      {/* ── E-Invoice Modal (preserved unchanged) ────────────────────── */}
      <Modal
        open={!!einvoiceItem}
        onClose={() => setEinvoiceItem(null)}
        title={`GST E-Invoice Portal · ${einvoiceItem?.invoice_number || ""}`}
        size="md"
      >
        {einvoiceItem && (
          <div className="space-y-4 text-xs">
            <div className="flex justify-between items-center bg-muted p-3 border border-border rounded-lg">
              <span className="label-overline">E-Invoice Status</span>
              <Badge tone={einvoiceItem.einvoice_status === "GENERATED" ? "success" : einvoiceItem.einvoice_status === "CANCELLED" ? "danger" : "neutral"}>
                {einvoiceItem.einvoice_status || "PENDING"}
              </Badge>
            </div>
            {einvoiceItem.einvoice_status === "GENERATED" ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3 border border-border p-3 rounded-lg bg-muted/30">
                  <div>
                    <span className="label-overline block">Ack No</span>
                    <span className="text-foreground font-bold">{einvoiceItem.ack_no}</span>
                  </div>
                  <div>
                    <span className="label-overline block">Ack Date</span>
                    <span className="text-foreground font-bold">{einvoiceItem.ack_date}</span>
                  </div>
                  <div className="col-span-2">
                    <span className="label-overline block">IRN (Invoice Reference Number)</span>
                    <span className="text-primary break-all">{einvoiceItem.irn}</span>
                  </div>
                </div>
                <div className="flex flex-col items-center justify-center p-4 border border-border rounded-lg bg-muted/20 space-y-2">
                  <div className="w-40 h-40 bg-card p-2 border-4 border-border rounded flex items-center justify-center">
                    <QrCode className="w-36 h-36 text-foreground/60" strokeWidth={1.5} />
                  </div>
                  <span className="text-[10px] text-muted-foreground uppercase tracking-widest">Digitally Signed QR Code</span>
                </div>
                <div className="flex gap-2 justify-end">
                  <SecondaryButton icon={FileJson} onClick={() => handleDownloadEinvoiceJson(einvoiceItem)}>
                    Export JSON
                  </SecondaryButton>
                  <SecondaryButton icon={ShieldAlert} onClick={() => handleCancelEinvoice(einvoiceItem.id)}>
                    Cancel e-Invoice
                  </SecondaryButton>
                </div>
              </div>
            ) : (
              <div className="py-6 flex flex-col items-center justify-center text-center space-y-3 bg-muted/20 border border-border rounded-lg">
                <QrCode className="w-12 h-12 text-muted-foreground" />
                <div>
                  <div className="font-bold text-foreground">No Registry Record Found</div>
                  <p className="text-[10px] text-muted-foreground max-w-sm mt-1 leading-relaxed">
                    This invoice has not been registered on the NIC e-invoice portal yet.
                  </p>
                </div>
                {einvoiceItem.einvoice_status !== "CANCELLED" && (
                  <PrimaryButton icon={Sparkles} onClick={() => handleGenerateEinvoice(einvoiceItem.id)}>
                    Generate e-Invoice
                  </PrimaryButton>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* ── E-Way Bill Modal (preserved unchanged) ───────────────────── */}
      <Modal
        open={!!ewbItem}
        onClose={() => setEwbItem(null)}
        title={`e-Way Bill · ${ewbItem?.invoice_number || ""}`}
        size="lg"
      >
        {ewbItem && <EwayBillSection invoice={ewbItem} onChanged={load} />}
      </Modal>

      <BulkDeleteBar
        count={sel.count}
        deleting={sel.deleting}
        onClear={sel.clear}
        onDelete={bulkDelete}
        noun="invoice"
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
