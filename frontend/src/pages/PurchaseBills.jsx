import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import { STANDARD_UOMS, DEFAULT_UOM } from "@/config/uom";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Field, Select, EmptyState,
  FormSection, CollapsibleFormSection, SummaryCard, Badge, NumericInput,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import ItemSearch from "@/components/ItemSearch";
import PartySearch from "@/components/PartySearch";
import useOnline from "@/hooks/useOnline";
import usePdfAction from "@/hooks/usePdfAction";
import useAccordionState from "@/hooks/useAccordionState";
import { useAuth } from "@/context/AuthContext";
import { isAdminRole } from "@/lib/navItems";
import BulkDeleteBar, { SelectCheckbox } from "@/components/BulkDeleteBar";
import useBulkSelect from "@/hooks/useBulkSelect";
import useGridKeyNav from "@/hooks/useGridKeyNav";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import {
  Plus, X, Download, Pencil, Trash2, Receipt, Package, FileText,
  Building2, CreditCard, Printer, Mail, MessageCircle, FileSpreadsheet,
  ChevronsUpDown,
} from "lucide-react";

// Vendor + Bill Details start open (Basic Info equivalent); 3-Way Match
// starts closed (situational — only relevant once GRNs exist for the
// vendor); Line Items is a plain (non-collapsible) FormSection, always visible.
const BILL_SECTION_DEFAULTS = { vendor: true, details: true, grnMatch: false };

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const qtyFmt = (n) => Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });

const blankLine = () => ({
  product_id: "", item_name: "", hsn_code: "", unit: DEFAULT_UOM, qty: "", rate: "",
  discount: "", gst_rate: "", _gst_type: "GST", _cgst: "", _sgst: "", _igst: "",
});
const blank = () => ({
  vendor_invoice_no: "", vendor_invoice_date: "", vendor_id: "",
  purchase_order_id: "", grn_ids: [], tds_rate: "", notes: "",
  payment_terms: "", place_of_supply: "", transport: "", vehicle_no: "", lr_no: "",
  lines: [blankLine()],
});

const lineTaxable = (l) => {
  const base = (parseFloat(l.qty) || 0) * (parseFloat(l.rate) || 0);
  const disc = base * (parseFloat(l.discount) || 0) / 100;
  return base - disc;
};
const lineGst = (l) => lineTaxable(l) * (parseFloat(l.gst_rate) || 0) / 100;
const lineTotal = (l) => lineTaxable(l) + lineGst(l);

function numberToWords(amount) {
  const ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
    "Eighteen", "Nineteen"];
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

// Vendor search is now the shared, keyboard-navigable PartySearch component
// (see components/PartySearch.jsx) — this page's own copy had no Arrow/Enter
// support at all; consolidating fixes that for every page that adopts it.

export default function PurchaseBills() {
  const online = useOnline();
  const { user } = useAuth();
  const isAdmin = isAdminRole(user?.role);
  const { run: downloadBillPdf, busyId } = usePdfAction();
  const [items, setItems] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [orders, setOrders] = useState([]);
  const [grns, setGrns] = useState([]);
  const [bills, setBills] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank());
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  // Which form sections are expanded — persisted so a section left open stays
  // open next time this form is used ("remember last expanded state").
  const acc = useAccordionState("bill-form-sections", BILL_SECTION_DEFAULTS);

  const canDeleteBill = (b) => isAdmin && (b.payment_received || 0) <= 0;
  const deletableBills = bills.filter(canDeleteBill);
  const sel = useBulkSelect(deletableBills);

  const load = async () => {
    const [it, vd, po, gr, bl] = await Promise.all([
      api.get("/products"),
      api.get("/purchase/v2/vendors"),
      api.get("/purchase/v2/orders"),
      api.get("/purchase/v2/grns"),
      api.get("/purchase/v2/bills"),
    ]);
    setItems(Array.isArray(it.data) ? it.data : (it.data?.items ?? []));
    setVendors(Array.isArray(vd.data) ? vd.data : (vd.data?.items ?? []));
    setOrders(Array.isArray(po.data) ? po.data : (po.data?.items ?? []));
    setGrns(Array.isArray(gr.data) ? gr.data : (gr.data?.items ?? []));
    setBills(Array.isArray(bl.data) ? bl.data : (bl.data?.items ?? []));
  };
  useEffect(() => { load(); }, []);

  const bulkDelete = async () => {
    if (!online) return toast.warning("You are offline — deleting is disabled.");
    const { ok, failed } = await sel.runDelete(
      (id) => api.delete(`/purchase/v2/bills/${id}`),
      { reload: load }
    );
    if (failed) toast.error(`Deleted ${ok}, failed ${failed}`);
    else toast.success(`Deleted ${ok} bill${ok === 1 ? "" : "s"}`);
  };

  const setLine = (idx, patch) =>
    setForm((f) => ({ ...f, lines: f.lines.map((l, i) => (i === idx ? { ...l, ...patch } : l)) }));
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

  // Keyboard-first line-item entry (Tally-style): Product → Qty → Unit →
  // Rate → Discount, then Enter on the last column of the last row appends a
  // new row and focuses its Product cell. Arrow keys move between cells;
  // Insert adds a row after the current one; Ctrl+Delete removes the current
  // row. Columns 0-4 are fixed (Product/Qty/Unit/Rate/Discount); column 5+ is
  // the GST-rate sub-widget, whose SHAPE varies per row: 1 input for plain
  // GST% or IGST%, 2 inputs (col 5 = CGST, col 6 = SGST) for CGST+SGST.
  const gstColsForRow = (row) => (form.lines[row]?._gst_type === "CGST_SGST" ? 7 : 6);
  const gridNav = useGridKeyNav({
    rowCount: form.lines.length,
    colCount: gstColsForRow,
    onRowComplete: addLine,
    onInsertRow: insertLineAfter,
    onDeleteRow: removeLineKeepingOne,
  });

  const setGstType = (idx, type) =>
    setForm((f) => ({
      ...f,
      lines: f.lines.map((l, i) => {
        if (i !== idx) return l;
        const cur = parseFloat(l.gst_rate) || 0;
        if (type === "GST")       return { ...l, _gst_type: type };
        if (type === "CGST_SGST") return { ...l, _gst_type: type, _cgst: cur / 2, _sgst: cur / 2 };
        if (type === "IGST")      return { ...l, _gst_type: type, _igst: cur };
        return l;
      }),
    }));

  const pickItem = (idx, id, it) => {
    setLine(idx, {
      product_id: id,
      item_name: it?.name || "",
      hsn_code: it?.hsn_code || "",
      unit: it?.unit || it?.uom || DEFAULT_UOM,
      rate: it?.cost_price != null ? Number(it.cost_price) : "",
      gst_rate: it?.gst_rate ?? 18,
      _cgst: (it?.gst_rate ?? 18) / 2,
      _sgst: (it?.gst_rate ?? 18) / 2,
      _igst: it?.gst_rate ?? 18,
    });
  };

  const toggleGrn = (id) =>
    setForm((f) => ({ ...f, grn_ids: f.grn_ids.includes(id) ? f.grn_ids.filter((g) => g !== id) : [...f.grn_ids, id] }));

  // Auto-fetch line items (product, HSN, qty, rate, GST) from the selected PO
  // so the user doesn't have to retype what was already agreed with the vendor.
  // Only overwrites lines when the form is still blank/untouched — if the user
  // has already started keying in items, ask before clobbering their work.
  const applyPoLines = (po) => {
    if (!po?.lines?.length) return;
    const mapped = po.lines.map((l) => {
      const gst = l.gst_rate ?? 18;
      const gstType = l.gst_type || "GST";
      const productId = l.product_id || l.stock_item_id || "";
      const product = productId ? items.find((i) => i.id === productId) : null;
      return {
        product_id: productId,
        item_name: l.item_name || l.product_name || product?.name || "",
        hsn_code: l.hsn_code || product?.hsn_code || "",
        unit: l.unit || DEFAULT_UOM,
        qty: l.qty || "",
        rate: l.rate || "",
        discount: "",
        gst_rate: gst,
        _gst_type: gstType,
        _cgst: gstType === "CGST_SGST" ? (l.cgst_rate ?? gst / 2) : gst / 2,
        _sgst: gstType === "CGST_SGST" ? (l.sgst_rate ?? gst / 2) : gst / 2,
        _igst: gstType === "IGST" ? (l.igst_rate ?? gst) : gst,
      };
    });
    setForm((f) => ({ ...f, lines: mapped }));
    toast.success(`Fetched ${mapped.length} line${mapped.length === 1 ? "" : "s"} from PO ${po.po_number}`);
  };

  const isLinesBlank = (lines) =>
    lines.every((l) => !l.product_id && !l.item_name && !parseFloat(l.qty) && !parseFloat(l.rate));

  const onPickPurchaseOrder = (poId) => {
    if (!poId) {
      setForm((f) => ({ ...f, purchase_order_id: "" }));
      return;
    }
    const po = orders.find((p) => p.id === poId);
    if (!po) return;
    if (!isLinesBlank(form.lines)) {
      if (!window.confirm("Replace current line items with this PO's items?")) return;
    }
    setForm((f) => ({ ...f, purchase_order_id: poId, vendor_id: f.vendor_id || po.vendor_id || f.vendor_id }));
    applyPoLines(po);
  };

  // Totals
  const subtotal = form.lines.reduce((s, l) => s + lineTaxable(l), 0);
  const gstAmount = form.lines.reduce((s, l) => s + lineGst(l), 0);
  const cgstAmount = form.lines.reduce((s, l) => {
    if (l._gst_type !== "CGST_SGST") return s;
    return s + lineTaxable(l) * (parseFloat(l._cgst) || 0) / 100;
  }, 0);
  const sgstAmount = form.lines.reduce((s, l) => {
    if (l._gst_type !== "CGST_SGST") return s;
    return s + lineTaxable(l) * (parseFloat(l._sgst) || 0) / 100;
  }, 0);
  const igstAmount = form.lines.reduce((s, l) => {
    if (l._gst_type !== "IGST") return s;
    return s + lineTaxable(l) * (parseFloat(l._igst) || 0) / 100;
  }, 0);
  const hasCgstSgst = form.lines.some((l) => l._gst_type === "CGST_SGST");
  const hasIgst = form.lines.some((l) => l._gst_type === "IGST");
  const tds = subtotal * (parseFloat(form.tds_rate) || 0) / 100;
  const gross = subtotal + gstAmount;
  const payable = gross - tds;

  const submit = async (e) => {
    e.preventDefault();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    const lines = form.lines
      .filter((l) => l.product_id && parseFloat(l.qty) > 0)
      .map((l) => ({
        product_id: l.product_id,
        item_name: items.find((i) => i.id === l.product_id)?.name || l.item_name,
        hsn_code: l.hsn_code || null,
        unit: l.unit || DEFAULT_UOM,
        qty: parseFloat(l.qty),
        rate: parseFloat(l.rate) || 0,
        discount: parseFloat(l.discount) || 0,
        gst_rate: parseFloat(l.gst_rate) || 0,
        gst_type: l._gst_type || "GST",
        cgst_rate: l._gst_type === "CGST_SGST" ? parseFloat(l._cgst) || 0 : null,
        sgst_rate: l._gst_type === "CGST_SGST" ? parseFloat(l._sgst) || 0 : null,
        igst_rate: l._gst_type === "IGST" ? parseFloat(l._igst) || 0 : null,
      }));
    if (lines.length === 0) return toast.error("Add at least one product line.");
    if (!form.vendor_id) return toast.error("Select a vendor.");
    const payload = {
      ...form,
      purchase_order_id: form.purchase_order_id || null,
      tds_rate: parseFloat(form.tds_rate) || 0,
      lines,
    };
    if (saving) return;
    setSaving(true);
    try {
      if (editingId) {
        await api.put(`/purchase/v2/bills/${editingId}`, payload);
        toast.success("Bill updated — accounting voucher re-posted");
      } else {
        const { data: created } = await api.post("/purchase/v2/bills", payload);
        toast.success("Bill posted — accounting voucher created");
        // Non-blocking: a bill with no linked GRN posts accounting only —
        // stock quantity/on-hand doesn't move anywhere. Easy to mistake for
        // "goods received" when it wasn't, so flag it (doesn't block save).
        if (created?.stock_impact_warning) {
          toast.warning(created.stock_impact_warning, { duration: 8000 });
        }
      }
      setOpen(false);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  // Enter-as-Tab data entry engine (see useEnterNavigation): Enter moves to
  // the next field anywhere in this form (vendor/bill-details fields,
  // falling through to the grid's own Enter handling inside the line-item
  // table), Ctrl+Enter saves, Ctrl+Shift+Enter saves and immediately opens a
  // fresh blank bill, Escape cancels. Auto-focuses the Vendor field the
  // moment the modal opens — no click required to start typing.
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
  });

  const openNew = () => { setForm(blank()); setEditingId(null); setOpen(true); };

  const openEdit = (b) => {
    setForm({
      vendor_invoice_no: b.vendor_invoice_no || "",
      vendor_invoice_date: b.vendor_invoice_date || "",
      vendor_id: b.vendor_id || "",
      purchase_order_id: b.purchase_order_id || "",
      grn_ids: b.grn_ids || [],
      tds_rate: b.tds_rate != null && b.tds_rate !== 0 ? b.tds_rate : "",
      notes: b.notes || "",
      payment_terms: b.payment_terms || "",
      place_of_supply: b.place_of_supply || "",
      transport: b.transport || "",
      vehicle_no: b.vehicle_no || "",
      lr_no: b.lr_no || "",
      lines: (b.lines || []).map((l) => {
        const gst = l.gst_rate ?? 18;
        const gstType = l.gst_type || "GST";
        return {
          product_id: l.product_id || l.stock_item_id || "",
          item_name: l.item_name || "",
          hsn_code: l.hsn_code || "",
          unit: l.unit || DEFAULT_UOM,
          qty: l.qty != null && l.qty !== 0 ? l.qty : "",
          rate: l.rate != null && l.rate !== 0 ? l.rate : "",
          discount: l.discount != null && l.discount !== 0 ? l.discount : "",
          gst_rate: gst,
          _gst_type: gstType,
          _cgst: gstType === "CGST_SGST" ? (l.cgst_rate ?? gst / 2) : gst / 2,
          _sgst: gstType === "CGST_SGST" ? (l.sgst_rate ?? gst / 2) : gst / 2,
          _igst: gstType === "IGST" ? (l.igst_rate ?? gst) : gst,
        };
      }) || [blankLine()],
    });
    setEditingId(b.id);
    setOpen(true);
  };

  const onDelete = async (b) => {
    if (!online) return toast.warning("You are offline — deleting is disabled.");
    if (!window.confirm(`Delete bill ${b.bill_number}? This also reverses its accounting voucher.`)) return;
    try {
      await api.delete(`/purchase/v2/bills/${b.id}`);
      toast.success("Bill deleted");
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  // Global module shortcuts: Ctrl/Cmd+N → new bill (when the list is showing,
  // not already editing one). Ctrl+Enter/Ctrl+Shift+Enter save this form
  // instead of Ctrl+S — see useEnterNavigation above — since Enter-based save
  // is the primary keyboard-first flow for a line-item voucher like this one.
  useModuleShortcuts({
    onNew: () => { if (!open) openNew(); },
  });

  const vendorGrns = grns.filter((g) => !form.vendor_id || g.vendor_id === form.vendor_id);
  const selectedVendor = vendors.find((v) => v.id === form.vendor_id);

  return (
    <div data-testid="purchase-bills-page">
      <PageHeader
        eyebrow="Purchase"
        title="Purchase Bills"
        description="Vendor invoices. Posting a bill creates the accounting voucher (Dr Inventory + Input GST, Cr Vendor)."
        actions={
          <PrimaryButton testid="new-bill" icon={Plus} disabled={!online} onClick={openNew}>
            New Bill
          </PrimaryButton>
        }
      />
      <OfflineBanner online={online} />

      {bills.length === 0 ? (
        <EmptyState message="No purchase bills yet" />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="border-b border-border label-overline">
                {isAdmin && (
                  <th className="px-3 py-2.5 w-10">
                    <SelectCheckbox
                      label="Select all deletable bills"
                      checked={sel.allSelected}
                      indeterminate={sel.someSelected}
                      onChange={sel.toggleAll}
                    />
                  </th>
                )}
                <th className="px-3 py-2.5">Bill No.</th>
                <th className="px-3 py-2.5">Vendor Inv.</th>
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5">Vendor</th>
                <th className="px-3 py-2.5 text-right">Payable</th>
                <th className="px-3 py-2.5">Voucher</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {bills.map((b) => (
                <tr key={b.id} data-testid={`bill-row-${b.id}`} className={`border-b border-border hover:bg-muted/40 text-foreground ${sel.isSelected(b.id) ? "bg-primary/5" : ""}`}>
                  {isAdmin && (
                    <td className="px-3 py-2.5">
                      {canDeleteBill(b) ? (
                        <SelectCheckbox
                          label={`Select bill ${b.bill_number}`}
                          checked={sel.isSelected(b.id)}
                          onChange={() => sel.toggle(b.id)}
                        />
                      ) : null}
                    </td>
                  )}
                  <td className="px-3 py-2.5 text-foreground font-semibold">{b.bill_number}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{b.vendor_invoice_no}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{b.vendor_invoice_date}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{b.vendor_name}</td>
                  <td className="px-3 py-2.5 text-right tabular text-foreground font-medium">
                    {b.total ? `₹${inr(b.total)}` : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-xs">
                    {b.journal_entry_id
                      ? <Badge tone="success">posted</Badge>
                      : <Badge tone="warning">no voucher</Badge>}
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        onClick={() => downloadBillPdf(`/purchase/v2/bills/${b.id}/pdf`, `${b.bill_number}.pdf`, b.id)}
                        disabled={busyId === b.id}
                        title="Download PDF"
                        data-testid={`bill-pdf-${b.id}`}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center disabled:opacity-50"
                      >
                        <Download className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => openEdit(b)}
                        disabled={!online || (b.payment_received || 0) > 0}
                        title={(b.payment_received || 0) > 0 ? "Bill has payments — cannot edit" : "Edit bill"}
                        data-testid={`bill-edit-${b.id}`}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center disabled:opacity-40"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      {isAdmin && (
                        <button
                          onClick={() => onDelete(b)}
                          disabled={!online || (b.payment_received || 0) > 0}
                          title={(b.payment_received || 0) > 0 ? "Bill has payments — cannot delete" : "Delete bill (admin)"}
                          data-testid={`bill-delete-${b.id}`}
                          className="w-7 h-7 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground inline-flex items-center justify-center disabled:opacity-40"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
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
        title={editingId ? "Edit Purchase Bill" : "New Purchase Bill"}
        icon={Receipt}
        size="full"
        bodyClassName="p-6 bg-[var(--bg)]"
        headerExtra={
          <div className="hidden items-center gap-3 sm:flex">
            <Badge tone={editingId ? "info" : "neutral"}>{editingId ? "EDIT" : "DRAFT"}</Badge>
            <span className="rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground">
              Net payable <span className="font-semibold text-primary">₹{inr(payable)}</span>
            </span>
          </div>
        }
        footer={
          <div className="flex w-full flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">
              Net Payable <span className="font-display font-bold text-base text-primary">₹{inr(payable)}</span>
              {tds > 0 && <span className="ml-2 text-muted-foreground">(after TDS ₹{inr(tds)})</span>}
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
                title="Email"
                onClick={() => toast.info("Email sharing coming soon")}
                className="w-8 h-8 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center transition-colors"
              >
                <Mail className="w-4 h-4" />
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
              <PrimaryButton onClick={submit} testid="save-bill" disabled={!online || saving} icon={Receipt}
                className="bg-gradient-to-r from-[#2563EB] to-[#1D4ED8]">
                {saving ? "Saving…" : (editingId ? "Update Bill" : "Post Bill")}
              </PrimaryButton>
            </div>
          </div>
        }
      >
        <form ref={formRef} id="bill-form" onSubmit={submit} className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="flex min-w-0 flex-col gap-6">

            <div className="flex justify-end gap-2 -mb-2">
              <SecondaryButton icon={ChevronsUpDown} className="h-8 px-2.5 text-xs" onClick={acc.expandAll}>Expand All</SecondaryButton>
              <SecondaryButton icon={ChevronsUpDown} className="h-8 px-2.5 text-xs" onClick={acc.collapseAll}>Collapse All</SecondaryButton>
            </div>

            {/* ── Vendor Info ─────────────────────────────────────────── */}
            <CollapsibleFormSection
              title="Vendor" icon={Building2} cols={4}
              open={acc.isOpen("vendor")} onOpenChange={() => acc.toggle("vendor")}
            >
              <Field label="Vendor" required>
                <PartySearch
                  parties={vendors}
                  value={form.vendor_id}
                  onChange={(id) => setForm({ ...form, vendor_id: id, grn_ids: [] })}
                  placeholder="Search vendor…"
                />
              </Field>
              {selectedVendor && (
                <>
                  <Field label="GSTIN">
                    <Input value={selectedVendor.gstin || "—"} disabled />
                  </Field>
                  <Field label="State / Place of Supply">
                    <Input value={selectedVendor.state || "—"} disabled />
                  </Field>
                  <Field label="Contact">
                    <Input value={selectedVendor.phone || selectedVendor.email || "—"} disabled />
                  </Field>
                </>
              )}
              {!selectedVendor && (
                <>
                  <Field label="GSTIN"><Input placeholder="Auto-filled from vendor" disabled /></Field>
                  <Field label="State"><Input placeholder="Auto-filled from vendor" disabled /></Field>
                  <Field label="Contact"><Input placeholder="Auto-filled from vendor" disabled /></Field>
                </>
              )}
            </CollapsibleFormSection>

            {/* ── Bill Details ─────────────────────────────────────────── */}
            <CollapsibleFormSection
              title="Bill Details" icon={FileText} cols={4}
              open={acc.isOpen("details")} onOpenChange={() => acc.toggle("details")}
            >
              <Field label="Vendor Invoice No." required>
                <Input required value={form.vendor_invoice_no} data-testid="bill-invno"
                  onChange={(e) => setForm({ ...form, vendor_invoice_no: e.target.value })} />
              </Field>
              <Field label="Invoice Date" required>
                <Input type="date" required value={form.vendor_invoice_date}
                  onChange={(e) => setForm({ ...form, vendor_invoice_date: e.target.value })} />
              </Field>
              <Field label="Link Purchase Order">
                <Select value={form.purchase_order_id}
                  onChange={(e) => onPickPurchaseOrder(e.target.value)}>
                  <option value="">— None —</option>
                  {orders.filter((p) => !form.vendor_id || p.vendor_id === form.vendor_id)
                    .map((p) => <option key={p.id} value={p.id}>{p.po_number}</option>)}
                </Select>
              </Field>
              <Field label="Payment Terms">
                <Input value={form.payment_terms} placeholder="e.g. Net 30"
                  onChange={(e) => setForm({ ...form, payment_terms: e.target.value })} />
              </Field>
              <Field label="Place of Supply">
                <Input value={form.place_of_supply} placeholder="State / city"
                  onChange={(e) => setForm({ ...form, place_of_supply: e.target.value })} />
              </Field>
              <Field label="Transport / Carrier">
                <Input value={form.transport} placeholder="Transporter name"
                  onChange={(e) => setForm({ ...form, transport: e.target.value })} />
              </Field>
              <Field label="Vehicle No.">
                <Input value={form.vehicle_no} placeholder="e.g. MH12AB1234"
                  onChange={(e) => setForm({ ...form, vehicle_no: e.target.value })} />
              </Field>
              <Field label="LR No.">
                <Input value={form.lr_no} placeholder="Lorry receipt no."
                  onChange={(e) => setForm({ ...form, lr_no: e.target.value })} />
              </Field>
              <Field label="TDS Rate %">
                <NumericInput value={form.tds_rate} onChange={v => setForm({ ...form, tds_rate: v })} placeholder="0" align="left" />
              </Field>
              <Field label="Remarks">
                <Input value={form.notes} placeholder="Short note"
                  onChange={(e) => setForm({ ...form, notes: e.target.value })} />
              </Field>
            </CollapsibleFormSection>

            {/* ── Link GRNs ─────────────────────────────────────────────── */}
            <CollapsibleFormSection
              title="3-Way Match — Link GRNs" icon={Package} grid={false}
              open={acc.isOpen("grnMatch")} onOpenChange={() => acc.toggle("grnMatch")}
            >
              <div className="border border-border bg-background p-3 max-h-28 overflow-y-auto rounded-lg flex flex-wrap gap-3">
                {vendorGrns.length === 0
                  ? <span className="text-xs text-muted-foreground">No GRNs for this vendor yet</span>
                  : vendorGrns.map((g) => (
                    <label key={g.id} className="flex items-center gap-2 text-xs cursor-pointer">
                      <input type="checkbox" className="accent-primary"
                        checked={form.grn_ids.includes(g.id)} onChange={() => toggleGrn(g.id)} />
                      <span className="text-foreground font-mono">{g.grn_number}</span>
                    </label>
                  ))}
              </div>
            </CollapsibleFormSection>

            {/* ── Line Items ────────────────────────────────────────────── */}
            <FormSection
              title="Line Items"
              icon={Package}
              grid={false}
              actions={
                <SecondaryButton icon={Plus} className="h-9 px-3 text-xs" onClick={addLine}>Add line</SecondaryButton>
              }
            >
              <div className="overflow-x-auto rounded-lg border border-border">
                <table data-grid-managed className="w-full text-left text-xs table-fixed" style={{ minWidth: "1080px" }}>
                  <colgroup>
                    <col style={{ width: "32px" }} />
                    <col style={{ width: "220px" }} />
                    <col style={{ width: "76px" }} />
                    <col style={{ width: "64px" }} />
                    <col style={{ width: "60px" }} />
                    <col style={{ width: "80px" }} />
                    <col style={{ width: "60px" }} />
                    <col style={{ width: "84px" }} />
                    <col style={{ width: "150px" }} />
                    <col style={{ width: "84px" }} />
                    <col style={{ width: "90px" }} />
                    <col style={{ width: "36px" }} />
                  </colgroup>
                  <thead className="sticky top-0 z-10">
                    <tr className="border-b border-border bg-muted text-muted-foreground">
                      <th className="px-1.5 py-2.5 text-center font-semibold">#</th>
                      <th className="px-1.5 py-2.5 font-semibold">Product</th>
                      <th className="px-1.5 py-2.5 font-semibold">HSN/SAC</th>
                      <th className="px-1.5 py-2.5 text-right font-semibold">Qty</th>
                      <th className="px-1.5 py-2.5 font-semibold">Unit</th>
                      <th className="px-1.5 py-2.5 text-right font-semibold">Rate ₹</th>
                      <th className="px-1.5 py-2.5 text-right font-semibold">Disc %</th>
                      <th className="px-1.5 py-2.5 text-right font-semibold">Taxable</th>
                      <th className="px-1.5 py-2.5 font-semibold">GST</th>
                      <th className="px-1.5 py-2.5 text-right font-semibold">GST Amt</th>
                      <th className="px-1.5 py-2.5 text-right font-semibold">Total ₹</th>
                      <th className="px-1.5 py-2.5 text-center font-semibold">Del</th>
                    </tr>
                  </thead>
                  <tbody>
                    {form.lines.map((l, idx) => (
                      <tr key={idx} className="border-b border-border align-top hover:bg-muted/30">
                        <td className="px-1.5 py-1.5 text-center align-middle text-muted-foreground">{idx + 1}</td>
                        <td className="px-1.5 py-1.5">
                          <ItemSearch
                            products={items}
                            value={l.product_id}
                            onChange={(id, it) => pickItem(idx, id, it)}
                            inputRef={gridNav.registerCell(idx, 0)}
                            onKeyDown={gridNav.handleKeyDown(idx, 0)}
                          />
                        </td>
                        <td className="px-1.5 py-1.5">
                          <Input placeholder="7308" value={l.hsn_code || ""}
                            onChange={(e) => setLine(idx, { hsn_code: e.target.value })} className="h-9 px-2" />
                        </td>
                        <td className="px-1.5 py-1.5">
                          <NumericInput compact value={l.qty} onChange={v => setLine(idx, { qty: v })} placeholder="0"
                            ref={gridNav.registerCell(idx, 1)} onKeyDown={gridNav.handleKeyDown(idx, 1)} className="h-9 w-full" />
                        </td>
                        <td className="px-1.5 py-1.5">
                          <Select value={l.unit || DEFAULT_UOM} onChange={(e) => setLine(idx, { unit: e.target.value })}
                            ref={gridNav.registerCell(idx, 2)} onKeyDown={gridNav.handleKeyDown(idx, 2)} className="h-9 px-1.5">
                            {STANDARD_UOMS.map((u) => <option key={u} value={u}>{u}</option>)}
                          </Select>
                        </td>
                        <td className="px-1.5 py-1.5">
                          <NumericInput compact value={l.rate} onChange={v => setLine(idx, { rate: v })} placeholder="0.00"
                            ref={gridNav.registerCell(idx, 3)} onKeyDown={gridNav.handleKeyDown(idx, 3)} className="h-9 w-full" />
                        </td>
                        <td className="px-1.5 py-1.5">
                          <NumericInput compact value={l.discount} onChange={v => setLine(idx, { discount: v })} placeholder="0" max={100}
                            ref={gridNav.registerCell(idx, 4)} onKeyDown={gridNav.handleKeyDown(idx, 4)} className="h-9 w-full" />
                        </td>
                        <td className="px-1.5 py-1.5 text-right align-middle tabular text-muted-foreground">
                          ₹{inr(lineTaxable(l))}
                        </td>
                        <td className="px-1.5 py-1.5">
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
                              <NumericInput compact value={l.gst_rate} onChange={v => setLine(idx, { gst_rate: v })} placeholder="18" max={100} aria-label="GST %"
                                ref={gridNav.registerCell(idx, 5)} onKeyDown={gridNav.handleKeyDown(idx, 5)} className="h-8 w-full" />
                            )}
                            {l._gst_type === "CGST_SGST" && (
                              <div className="flex gap-1">
                                <NumericInput compact value={l._cgst} onChange={v => { const n = parseFloat(v)||0; setLine(idx, { _cgst: v, gst_rate: n + (parseFloat(l._sgst)||0) }); }} placeholder="9" max={100} aria-label="CGST %"
                                  ref={gridNav.registerCell(idx, 5)} onKeyDown={gridNav.handleKeyDown(idx, 5)} className="h-8 w-1/2" />
                                <NumericInput compact value={l._sgst} onChange={v => { const n = parseFloat(v)||0; setLine(idx, { _sgst: v, gst_rate: (parseFloat(l._cgst)||0) + n }); }} placeholder="9" max={100} aria-label="SGST %"
                                  ref={gridNav.registerCell(idx, 6)} onKeyDown={gridNav.handleKeyDown(idx, 6)} className="h-8 w-1/2" />
                              </div>
                            )}
                            {l._gst_type === "IGST" && (
                              <NumericInput compact value={l._igst} onChange={v => { setLine(idx, { _igst: v, gst_rate: v }); }} placeholder="18" max={100} aria-label="IGST %"
                                ref={gridNav.registerCell(idx, 5)} onKeyDown={gridNav.handleKeyDown(idx, 5)} className="h-8 w-full" />
                            )}
                          </div>
                        </td>
                        <td className="px-1.5 py-1.5 text-right align-middle tabular text-muted-foreground">
                          ₹{inr(lineGst(l))}
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
                    ))}
                  </tbody>
                </table>
              </div>
            </FormSection>
          </div>

          {/* ── Right rail: vendor info + bill summary ────────────────── */}
          <aside className="flex min-w-0 flex-col gap-6">
            <div className="lg:sticky lg:top-4 flex flex-col gap-6">

              {/* Vendor card */}
              {selectedVendor && (
                <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <h3 className="mb-3 font-display font-semibold text-sm text-foreground flex items-center gap-2">
                    <Building2 className="w-4 h-4 text-primary" /> Vendor Details
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div>
                      <div className="label-overline">Company</div>
                      <div className="font-semibold text-foreground">{selectedVendor.company || selectedVendor.name}</div>
                    </div>
                    {selectedVendor.gstin && (
                      <div>
                        <div className="label-overline">GSTIN</div>
                        <div className="font-mono text-foreground">{selectedVendor.gstin}</div>
                      </div>
                    )}
                    {selectedVendor.address && (
                      <div>
                        <div className="label-overline">Address</div>
                        <div className="text-muted-foreground text-xs">{selectedVendor.address}</div>
                      </div>
                    )}
                    {(selectedVendor.phone || selectedVendor.email) && (
                      <div>
                        <div className="label-overline">Contact</div>
                        <div className="text-xs text-muted-foreground">{selectedVendor.phone || selectedVendor.email}</div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Bill Summary */}
              <SummaryCard
                title="Bill Summary"
                rows={[
                  { label: "Taxable (subtotal)", value: `₹${inr(subtotal)}` },
                  ...(hasCgstSgst ? [
                    { label: "CGST", value: `₹${inr(cgstAmount)}` },
                    { label: "SGST", value: `₹${inr(sgstAmount)}` },
                  ] : []),
                  ...(hasIgst ? [{ label: "IGST", value: `₹${inr(igstAmount)}` }] : []),
                  ...(!hasCgstSgst && !hasIgst ? [{ label: "GST", value: `₹${inr(gstAmount)}` }] : []),
                  { label: "Gross (incl. GST)", value: `₹${inr(gross)}` },
                  ...(tds > 0 ? [{ label: `TDS @ ${form.tds_rate}%`, value: `−₹${inr(tds)}` }] : []),
                ]}
                total={{ label: "Net Payable", value: `₹${inr(payable)}` }}
                footer={
                  <div className="space-y-2">
                    <div className="text-center">
                      <div className="label-overline">Net Payable</div>
                      <div className="font-display text-2xl font-bold text-primary">₹{inr(payable)}</div>
                    </div>
                    <div className="border-t border-border pt-2 text-[10px] text-muted-foreground text-center leading-snug">
                      {numberToWords(payable)}
                    </div>
                  </div>
                }
              />

              {/* GST breakup */}
              {(hasCgstSgst || hasIgst) && (
                <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <h3 className="mb-3 font-display font-semibold text-sm text-foreground flex items-center gap-2">
                    <CreditCard className="w-4 h-4 text-primary" /> GST Breakup
                  </h3>
                  <div className="space-y-2 text-xs">
                    {form.lines.filter((l) => l._gst_type !== "GST" || l.gst_rate).map((l, i) => {
                      const tax = lineGst(l);
                      if (!tax) return null;
                      return (
                        <div key={i} className="flex justify-between text-muted-foreground border-b border-border pb-1 last:border-0 last:pb-0">
                          <span className="truncate max-w-[140px]">{items.find((it) => it.id === l.product_id)?.name || `Line ${i + 1}`}</span>
                          <span className="tabular text-foreground">₹{inr(tax)}</span>
                        </div>
                      );
                    })}
                    <div className="flex justify-between font-semibold text-foreground pt-1">
                      <span>Total GST</span>
                      <span className="tabular">₹{inr(gstAmount)}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </aside>
        </form>
      </Modal>

      <BulkDeleteBar
        count={sel.count}
        deleting={sel.deleting}
        onClear={sel.clear}
        onDelete={bulkDelete}
        noun="bill"
      />
    </div>
  );
}
