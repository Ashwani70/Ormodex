import { Fragment, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import { STANDARD_UOMS, DEFAULT_UOM } from "@/config/uom";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Field, Select, EmptyState,
  FormSection, SummaryCard, AttachmentsField, Badge,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import BulkDeleteBar, { SelectCheckbox } from "@/components/BulkDeleteBar";
import useBulkSelect from "@/hooks/useBulkSelect";
import useOnline from "@/hooks/useOnline";
import useTrackingFlags from "@/hooks/useTrackingFlags";
import { missingTrackingFields } from "@/lib/tracking";
import useGridKeyNav from "@/hooks/useGridKeyNav";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import {
  Plus, X, PenLine, Package, PackageCheck, FileText, Truck, ScanLine,
  FileSpreadsheet, ClipboardCheck, Info, ShieldCheck, Save, Eye, Printer, Trash2,
} from "lucide-react";

const blankLine = () => ({
  product_id: "", product_name: "", hsn_code: "", unit: DEFAULT_UOM, _manual: false,
  po_line_index: null, qty_received: "", rate: "", gst_rate: "",
  batch_id: "", serial_id: "", expiry_date: "",
});
const blank = () => ({
  purchase_order_id: "", vendor_id: "", godown_id: "", received_date: "", remarks: "",
  lines: [blankLine()],
});

const inr = (n) => Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Presentation-only line math (the backend computes its own authoritative
// figures on post; this only drives the on-screen preview columns/summary).
const lineTaxable = (l) => (parseFloat(l.qty_received) || 0) * (parseFloat(l.rate) || 0);
const lineGst = (l) => lineTaxable(l) * (parseFloat(l.gst_rate) || 0) / 100;

export default function GRNs() {
  const online = useOnline();
  const [items, setItems] = useState([]);
  const [godowns, setGodowns] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [orders, setOrders] = useState([]);
  const [grns, setGrns] = useState([]);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(blank());
  const { flagsFor, ensureFlags } = useTrackingFlags();
  const sel = useBulkSelect(grns);

  const load = async () => {
    const [it, gd, vd, po, gr] = await Promise.all([
      api.get("/products"),
      api.get("/inventory/v2/godowns"),
      api.get("/purchase/v2/vendors"),
      api.get("/purchase/v2/orders"),
      api.get("/purchase/v2/grns"),
    ]);
    setItems(it.data); setGodowns(gd.data); setVendors(vd.data); setOrders(po.data); setGrns(gr.data);
  };
  useEffect(() => { load(); }, []);

  const itemById = (id) => items.find((i) => i.id === id) || {};

  const setLine = (idx, patch) =>
    setForm((f) => ({ ...f, lines: f.lines.map((l, i) => (i === idx ? { ...l, ...patch } : l)) }));
  const toggleLineManual = (idx) =>
    setForm((f) => ({
      ...f,
      lines: f.lines.map((l, i) =>
        i === idx ? { ...l, _manual: !l._manual, product_id: "", product_name: "" } : l
      ),
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

  // Keyboard-first line-item entry (Tally-style). Fixed 9 editable columns per
  // row (no GST-type sub-widget on this page): Product, Description, HSN,
  // Batch, Serial, Received Qty, Unit, Rate, GST%. The conditional Expiry
  // sub-row field is intentionally NOT part of the grid's column sequence —
  // it renders in its own sub-row only for tracked products, so it stays a
  // normal tab-stop rather than a grid cell.
  const gridNav = useGridKeyNav({
    rowCount: form.lines.length,
    colCount: 9,
    onRowComplete: addLine,
    onInsertRow: insertLineAfter,
    onDeleteRow: removeLineKeepingOne,
  });

  // Selecting a PO prefills vendor + lines from that PO.
  const onSelectPO = (poId) => {
    if (!poId) { setForm((f) => ({ ...f, purchase_order_id: "" })); return; }
    const po = orders.find((p) => p.id === poId);
    if (!po) return;
    setForm((f) => ({
      ...f,
      purchase_order_id: poId,
      vendor_id: po.vendor_id,
      lines: (po.lines || []).map((pl, idx) => ({
        ...blankLine(),
        product_id: pl.product_id || "",
        hsn_code: pl.hsn_code || "",
        unit: pl.unit || DEFAULT_UOM,
        po_line_index: idx,
        qty_received: Math.max(0, (parseFloat(pl.qty) || 0) - (parseFloat(pl.received_qty) || 0)),
        rate: pl.rate || 0,
        gst_rate: pl.gst_rate ?? 18,
      })),
    }));
    ensureFlags((po.lines || []).map((pl) => pl.product_id));
  };

  // Resolve tracking flags whenever a product is chosen on a line.
  const onPickProduct = (idx, productId) => {
    const p = itemById(productId);
    setLine(idx, {
      product_id: productId,
      ...(p.id ? { hsn_code: p.hsn_code || "", unit: p.unit || DEFAULT_UOM, rate: Number(p.cost_price || 0), gst_rate: Number(p.gst_rate ?? 18) } : {}),
    });
    if (productId) ensureFlags([productId]);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    if (!form.godown_id) return toast.error("Select a target warehouse.");
    const lines = form.lines
      .filter((l) => (l._manual ? l.product_name?.trim() : l.product_id) && parseFloat(l.qty_received) > 0)
      .map((l) => {
        const it = l._manual ? {} : itemById(l.product_id);
        return {
          product_id: l._manual ? null : l.product_id,
          product_name: l._manual ? l.product_name : it.name,
          hsn_code: l.hsn_code || null,
          unit: l.unit || DEFAULT_UOM,
          po_line_index: l.po_line_index,
          qty_received: parseFloat(l.qty_received),
          rate: parseFloat(l.rate) || 0,
          gst_rate: parseFloat(l.gst_rate) || 0,
          batch_id: l.batch_id || null,
          serial_id: l.serial_id || null,
          expiry_date: l.expiry_date || null,
        };
      });
    if (lines.length === 0) return toast.error("Add at least one received line.");
    // Client-side mirror of the server's tracking rules (server still enforces).
    for (const l of lines) {
      if (l._manual) continue;
      const miss = missingTrackingFields(l, flagsFor(l.product_id));
      if (miss.length) {
        return toast.error(`${miss.join(" & ")} required for '${l.product_name || l.product_id}'.`);
      }
    }
    if (saving) return;
    setSaving(true);
    try {
      await api.post("/purchase/v2/grns", {
        ...form,
        purchase_order_id: form.purchase_order_id || null,
        received_date: form.received_date || null,
        lines,
      });
      toast.success("GRN posted — stock updated");
      setOpen(false);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const openNew = () => { setForm(blank()); setOpen(true); };

  const deleteOne = async (grn) => {
    if (!window.confirm(`Delete GRN ${grn.grn_number || grn.id}? This reverses its stock receipt.`)) return;
    try {
      await api.delete(`/purchase/v2/grns/${grn.id}`);
      toast.success(`${grn.grn_number || "GRN"} deleted`);
      sel.clear();
      load();
    } catch (err) {
      console.error("GRN delete failure:", err);
      toast.error(formatApiErrorDetail(null, err));
    }
  };

  const bulkDelete = async () => {
    const { ok, failed, firstError } = await sel.runDelete((id) => api.delete(`/purchase/v2/grns/${id}`), { reload: load });
    if (failed) {
      if (firstError) console.error("GRN bulk delete failure:", firstError);
      toast.error(`Deleted ${ok}, failed ${failed} — ${formatApiErrorDetail(null, firstError)}`);
    } else {
      toast.success(`Deleted ${ok} GRN${ok === 1 ? "" : "s"}`);
    }
  };

  // Enter-as-Tab data entry engine (see useEnterNavigation): Enter moves to
  // the next field anywhere in this form (General Information fields, falling
  // through to the grid's own Enter handling inside the line-item table),
  // Ctrl+Enter posts the GRN (via the SAME submit() the Post GRN button calls,
  // so over-receipt / tracking validation still runs), Ctrl+Shift+Enter posts
  // and immediately opens a fresh blank GRN, Escape cancels. Auto-focuses the
  // first eligible field the moment the modal opens.
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

  // Global module shortcut: Ctrl/Cmd+N → new GRN (when the list is showing,
  // not already editing one).
  useModuleShortcuts({
    onNew: () => { if (!open) openNew(); },
  });

  // ── Presentation-only roll-ups for the live summary panel ──────────────
  const selectedPo = orders.find((p) => p.id === form.purchase_order_id);
  const poLineQty = (l) => {
    if (!selectedPo || l.po_line_index == null) return null;
    const pl = (selectedPo.lines || [])[l.po_line_index];
    return pl ? (parseFloat(pl.qty) || 0) : null;
  };
  const subtotal = form.lines.reduce((s, l) => s + lineTaxable(l), 0);
  const gstTotal = form.lines.reduce((s, l) => s + lineGst(l), 0);
  const totalReceived = form.lines.reduce((s, l) => s + (parseFloat(l.qty_received) || 0), 0);
  const totalOrdered = form.lines.reduce((s, l) => s + (poLineQty(l) || 0), 0);
  const productCount = form.lines.filter((l) => (l._manual ? l.product_name?.trim() : l.product_id)).length;
  const grandTotal = subtotal + gstTotal;
  // No state-code on the form → preview as intra-state split (CGST+SGST). The
  // server recomputes the authoritative tax on post; this is display only.
  const cgst = gstTotal / 2, sgst = gstTotal / 2, igst = 0;

  return (
    <div data-testid="grns-page">
      <PageHeader
        eyebrow="Purchase"
        title="Goods Receipt Notes"
        description="Record goods received into a warehouse. Posting a GRN writes inward stock-ledger entries."
        actions={
          <PrimaryButton testid="new-grn" icon={Plus} disabled={!online}
            onClick={openNew}>
            New GRN
          </PrimaryButton>
        }
      />
      <OfflineBanner online={online} />

      {grns.length === 0 ? (
        <EmptyState message="No goods receipt notes yet" />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="border-b border-border label-overline">
                <th className="px-3 py-2.5 w-10">
                  <SelectCheckbox checked={sel.allSelected} indeterminate={sel.someSelected} onChange={sel.toggleAll} label="Select all GRNs" />
                </th>
                <th className="px-3 py-2.5">GRN Number</th>
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5">Vendor</th>
                <th className="px-3 py-2.5 text-right">Lines</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {grns.map((g) => (
                <tr key={g.id} data-testid={`grn-row-${g.id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                  <td className="px-3 py-2.5">
                    <SelectCheckbox checked={sel.isSelected(g.id)} onChange={() => sel.toggle(g.id)} label={`Select ${g.grn_number || g.id}`} />
                  </td>
                  <td className="px-3 py-2.5 text-foreground font-semibold">{g.grn_number || "—"}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{g.received_date || (g.created_at ? new Date(g.created_at).toLocaleDateString("en-IN") : "—")}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{g.vendor_name || "—"}</td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground">{(g.lines || []).length}</td>
                  <td className="px-3 py-2.5 text-right">
                    <button
                      onClick={() => deleteOne(g)}
                      title="Delete GRN"
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="w-4 h-4 inline" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <BulkDeleteBar
        count={sel.count}
        deleting={sel.deleting}
        onClear={sel.clear}
        onDelete={bulkDelete}
        noun="GRN"
        nounPlural="GRNs"
      />

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="New Goods Receipt Note"
        icon={PackageCheck}
        size="full"
        bodyClassName="p-6 bg-[var(--bg)]"
        headerExtra={
          <div className="hidden items-center gap-3 sm:flex">
            <Badge tone="warning">Draft</Badge>
            <span className="rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground">
              GRN # <span className="font-semibold text-foreground">Auto on post</span>
            </span>
          </div>
        }
        footer={
          <div className="flex w-full flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">
              Grand Total <span className="font-display font-bold text-base text-primary">₹{inr(grandTotal)}</span>
            </span>
            <div className="flex flex-wrap items-center gap-2">
              <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
              <SecondaryButton icon={Save} disabled title="Drafts are not stored yet — needs a backend draft endpoint">Save Draft</SecondaryButton>
              <SecondaryButton icon={Eye} disabled title="Preview is not available yet — needs a backend render endpoint">Preview GRN</SecondaryButton>
              <SecondaryButton icon={Printer} disabled title="Print is available after the GRN is posted">Print</SecondaryButton>
              <PrimaryButton onClick={submit} testid="save-grn" disabled={!online || saving} icon={PackageCheck}
                className="bg-gradient-to-r from-[#2563EB] to-[#1D4ED8]">
                {saving ? "Saving…" : "Post GRN"}
              </PrimaryButton>
            </div>
          </div>
        }
      >
        {/* Two-column working surface: form sections (left) + sticky summary (right) */}
        <form ref={formRef} id="grn-form" onSubmit={submit} className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="flex min-w-0 flex-col gap-6">

            {/* ── General Information ─────────────────────────────────── */}
            <FormSection title="General Information" icon={FileText} cols={4}>
              <Field label="Purchase Order">
                <Select value={form.purchase_order_id} data-testid="grn-po"
                  onChange={(e) => onSelectPO(e.target.value)}>
                  <option value="">— Standalone —</option>
                  {orders.filter((p) => !["CLOSED", "CANCELLED"].includes(p.status))
                    .map((p) => <option key={p.id} value={p.id}>{p.po_number}</option>)}
                </Select>
              </Field>
              <Field label="Vendor" required>
                <Select required value={form.vendor_id} data-testid="grn-vendor"
                  onChange={(e) => setForm({ ...form, vendor_id: e.target.value })}>
                  <option value="">— Select vendor —</option>
                  {vendors.map((v) => <option key={v.id} value={v.id}>{v.company || v.name}</option>)}
                </Select>
              </Field>
              <Field label="Target Warehouse" required>
                <Select required value={form.godown_id} data-testid="grn-godown"
                  onChange={(e) => setForm({ ...form, godown_id: e.target.value })}>
                  <option value="">— Select warehouse —</option>
                  {godowns.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                </Select>
              </Field>
              <Field label="Received Date">
                <Input type="date" value={form.received_date}
                  onChange={(e) => setForm({ ...form, received_date: e.target.value })} />
              </Field>

              {/* Fields below have no backend field yet — shown disabled so the
                  layout is complete without pretending the data is persisted. */}
              <Field label="GRN Number" hint="Assigned automatically when you post.">
                <Input value="Auto on post" disabled readOnly />
              </Field>
              <Field label="Invoice Number" hint="Not stored yet — needs an API field.">
                <Input placeholder="Vendor invoice no." disabled />
              </Field>
              <Field label="Supplier GSTIN" hint="Not stored yet — needs an API field.">
                <Input placeholder="e.g. 27ABCDE1234F1Z5" disabled />
              </Field>
              <Field label="Received By" hint="Not stored yet — needs an API field.">
                <Input placeholder="Receiver name" disabled />
              </Field>
              <Field label="Transport" hint="Not stored yet — needs an API field.">
                <Input placeholder="Transporter" disabled />
              </Field>
              <Field label="Vehicle Number" hint="Not stored yet — needs an API field.">
                <Input placeholder="e.g. MH12AB1234" disabled />
              </Field>
              <Field label="Reference Number" hint="Not stored yet — needs an API field.">
                <Input placeholder="Internal reference" disabled />
              </Field>
            </FormSection>

            {/* ── Line items ──────────────────────────────────────────── */}
            <FormSection
              title="Received Products"
              icon={Package}
              grid={false}
              actions={
                <div className="flex flex-wrap items-center gap-2">
                  <SecondaryButton icon={Plus} className="h-9 px-3 text-xs" onClick={addLine}>Add Product</SecondaryButton>
                  <SecondaryButton icon={PenLine} className="h-9 px-3 text-xs" onClick={() => setForm((f) => ({ ...f, lines: [...f.lines, { ...blankLine(), _manual: true }] }))}>Add Custom Product</SecondaryButton>
                  <SecondaryButton icon={FileSpreadsheet} className="h-9 px-3 text-xs" disabled title="Excel import is not wired yet">Import Excel</SecondaryButton>
                  <SecondaryButton icon={ScanLine} className="h-9 px-3 text-xs" disabled title="Barcode scan is not wired yet">Scan Barcode</SecondaryButton>
                </div>
              }
            >
              <div className="overflow-x-auto rounded-lg border border-border">
                <table data-grid-managed className="w-full text-left text-xs" style={{ minWidth: "1640px" }}>
                  <colgroup>
                    <col style={{ width: "44px" }} />
                    <col style={{ width: "230px" }} />
                    <col style={{ width: "170px" }} />
                    <col style={{ width: "110px" }} />
                    <col style={{ width: "120px" }} />
                    <col style={{ width: "120px" }} />
                    <col style={{ width: "90px" }} />
                    <col style={{ width: "100px" }} />
                    <col style={{ width: "100px" }} />
                    <col style={{ width: "90px" }} />
                    <col style={{ width: "100px" }} />
                    <col style={{ width: "80px" }} />
                    <col style={{ width: "100px" }} />
                    <col style={{ width: "100px" }} />
                    <col style={{ width: "100px" }} />
                    <col style={{ width: "120px" }} />
                    <col style={{ width: "120px" }} />
                    <col style={{ width: "56px" }} />
                  </colgroup>
                  <thead className="sticky top-0 z-10">
                    <tr className="border-b border-border bg-muted text-muted-foreground">
                      <th className="px-2 py-2.5 text-center font-semibold">#</th>
                      <th className="px-2 py-2.5 font-semibold">Product</th>
                      <th className="px-2 py-2.5 font-semibold">Description</th>
                      <th className="px-2 py-2.5 font-semibold">HSN/SAC</th>
                      <th className="px-2 py-2.5 font-semibold">Batch No</th>
                      <th className="px-2 py-2.5 font-semibold">Serial No</th>
                      <th className="px-2 py-2.5 text-right font-semibold">Ordered</th>
                      <th className="px-2 py-2.5 text-right font-semibold">Received</th>
                      <th className="px-2 py-2.5 text-right font-semibold">Rejected</th>
                      <th className="px-2 py-2.5 font-semibold">Unit</th>
                      <th className="px-2 py-2.5 text-right font-semibold">Rate</th>
                      <th className="px-2 py-2.5 text-right font-semibold">GST %</th>
                      <th className="px-2 py-2.5 text-right font-semibold">CGST</th>
                      <th className="px-2 py-2.5 text-right font-semibold">SGST</th>
                      <th className="px-2 py-2.5 text-right font-semibold">IGST</th>
                      <th className="px-2 py-2.5 text-right font-semibold">Taxable</th>
                      <th className="px-2 py-2.5 text-right font-semibold">Total</th>
                      <th className="px-2 py-2.5 text-center font-semibold">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {form.lines.map((l, idx) => {
                      const flags = flagsFor(l.product_id);
                      const showTracking = l.product_id && (flags.track_batch || flags.track_serial || flags.track_expiry);
                      const taxable = lineTaxable(l);
                      const g = lineGst(l);
                      const ordered = poLineQty(l);
                      return (
                        <Fragment key={idx}>
                        <tr className={`align-top hover:bg-muted/30 ${showTracking && flags.track_expiry ? "" : "border-b border-border"}`}>
                          <td className="px-2 py-2 text-center align-middle text-muted-foreground">{idx + 1}</td>
                          <td className="px-2 py-2">
                            <div className="flex items-start gap-1.5">
                              <button
                                type="button"
                                title={l._manual ? "Switch to catalog product" : "Enter product manually"}
                                onClick={() => toggleLineManual(idx)}
                                className={`mt-0.5 flex h-10 w-9 flex-shrink-0 items-center justify-center rounded-lg border transition-colors ${l._manual ? "border-[var(--warning)] text-[var(--warning)]" : "border-border text-muted-foreground hover:border-primary hover:text-primary"}`}
                              >
                                {l._manual ? <PenLine className="h-4 w-4" /> : <Package className="h-4 w-4" />}
                              </button>
                              {l._manual ? (
                                <Input
                                  placeholder="Product name (manual)"
                                  value={l.product_name || ""}
                                  onChange={(e) => setLine(idx, { product_name: e.target.value })}
                                  ref={gridNav.registerCell(idx, 0)}
                                  onKeyDown={gridNav.handleKeyDown(idx, 0)}
                                  className="h-10"
                                />
                              ) : (
                                <Select value={l.product_id} onChange={(e) => onPickProduct(idx, e.target.value)}
                                  ref={gridNav.registerCell(idx, 0)} onKeyDown={gridNav.handleKeyDown(idx, 0)} className="h-10">
                                  <option value="">— Product —</option>
                                  {items.map((i) => <option key={i.id} value={i.id}>{i.name}{i.sku ? ` (${i.sku})` : ""}</option>)}
                                </Select>
                              )}
                            </div>
                          </td>
                          <td className="px-2 py-2">
                            <Input placeholder="Description" value={l.description || ""}
                              onChange={(e) => setLine(idx, { description: e.target.value })}
                              ref={gridNav.registerCell(idx, 1)} onKeyDown={gridNav.handleKeyDown(idx, 1)} className="h-10" />
                          </td>
                          <td className="px-2 py-2">
                            <Input placeholder="e.g. 7308" value={l.hsn_code || ""}
                              onChange={(e) => setLine(idx, { hsn_code: e.target.value })}
                              ref={gridNav.registerCell(idx, 2)} onKeyDown={gridNav.handleKeyDown(idx, 2)} className="h-10" />
                          </td>
                          <td className="px-2 py-2">
                            <Input value={l.batch_id || ""} data-testid={`grn-batch-${idx}`}
                              placeholder={flags.track_batch ? "Required" : "—"}
                              required={!!flags.track_batch}
                              onChange={(e) => setLine(idx, { batch_id: e.target.value })}
                              ref={gridNav.registerCell(idx, 3)} onKeyDown={gridNav.handleKeyDown(idx, 3)} className="h-10" />
                          </td>
                          <td className="px-2 py-2">
                            <Input value={l.serial_id || ""} data-testid={`grn-serial-${idx}`}
                              placeholder={flags.track_serial ? "Required" : "—"}
                              required={!!flags.track_serial}
                              onChange={(e) => setLine(idx, { serial_id: e.target.value })}
                              ref={gridNav.registerCell(idx, 4)} onKeyDown={gridNav.handleKeyDown(idx, 4)} className="h-10" />
                          </td>
                          <td className="px-2 py-2 text-right align-middle tabular text-muted-foreground">
                            {ordered == null ? "—" : inr(ordered)}
                          </td>
                          <td className="px-2 py-2">
                            <Input type="text" inputMode="decimal" step="0.0001" min="0" placeholder="0" value={l.qty_received}
                              onChange={(e) => setLine(idx, { qty_received: e.target.value })}
                              ref={gridNav.registerCell(idx, 5)} onKeyDown={gridNav.handleKeyDown(idx, 5)} className="h-10 text-right" />
                          </td>
                          <td className="px-2 py-2">
                            <Input type="text" inputMode="decimal" disabled title="Rejected qty is not stored yet — needs an API field"
                              placeholder="0" className="h-10 text-right" />
                          </td>
                          <td className="px-2 py-2">
                            <Select value={l.unit || DEFAULT_UOM} onChange={(e) => setLine(idx, { unit: e.target.value })}
                              ref={gridNav.registerCell(idx, 6)} onKeyDown={gridNav.handleKeyDown(idx, 6)} className="h-10">
                              {STANDARD_UOMS.map((u) => <option key={u} value={u}>{u}</option>)}
                            </Select>
                          </td>
                          <td className="px-2 py-2">
                            <Input type="text" inputMode="decimal" step="0.01" min="0" placeholder="0.00" value={l.rate}
                              onChange={(e) => setLine(idx, { rate: e.target.value })}
                              ref={gridNav.registerCell(idx, 7)} onKeyDown={gridNav.handleKeyDown(idx, 7)} className="h-10 text-right" />
                          </td>
                          <td className="px-2 py-2">
                            <Input type="text" inputMode="decimal" step="0.01" min="0" placeholder="18" value={l.gst_rate}
                              onChange={(e) => setLine(idx, { gst_rate: e.target.value })}
                              ref={gridNav.registerCell(idx, 8)} onKeyDown={gridNav.handleKeyDown(idx, 8)} className="h-10 text-right" />
                          </td>
                          <td className="px-2 py-2 text-right align-middle tabular text-muted-foreground">₹{inr(g / 2)}</td>
                          <td className="px-2 py-2 text-right align-middle tabular text-muted-foreground">₹{inr(g / 2)}</td>
                          <td className="px-2 py-2 text-right align-middle tabular text-muted-foreground">₹{inr(0)}</td>
                          <td className="px-2 py-2 text-right align-middle tabular font-medium text-foreground">₹{inr(taxable)}</td>
                          <td className="px-2 py-2 text-right align-middle tabular font-semibold text-foreground">₹{inr(taxable + g)}</td>
                          <td className="px-2 py-2 text-center align-middle">
                            <button type="button" onClick={() => removeLine(idx)} aria-label="Remove line"
                              className="flex h-9 w-9 items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:border-[var(--danger)] hover:bg-[#FEE2E2] hover:text-[var(--danger)] mx-auto">
                              <X className="h-4 w-4" />
                            </button>
                          </td>
                        </tr>
                        {/* Expiry is a tracked field but has no dedicated column;
                            show it as a sub-row only when the product requires it
                            so the tracking validation can be satisfied. */}
                        {showTracking && flags.track_expiry && (
                          <tr className="border-b border-border bg-muted/30">
                            <td />
                            <td colSpan={17} className="px-2 pb-3">
                              <div className="max-w-xs">
                                <Field label="Expiry Date" required>
                                  <Input required type="date" value={l.expiry_date} data-testid={`grn-expiry-${idx}`}
                                    onChange={(e) => setLine(idx, { expiry_date: e.target.value })} className="h-10" />
                                </Field>
                              </div>
                            </td>
                          </tr>
                        )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {/* Tracking helper note */}
              <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
                <Info className="h-3.5 w-3.5" />
                Batch / Serial / Expiry are required for tracked products and validated on post.
              </p>
            </FormSection>

            {/* ── Bottom: documents + inspection ──────────────────────── */}
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <FormSection title="Remarks & Documents" icon={ClipboardCheck} grid={false}>
                <div className="space-y-4">
                  <Field label="Remarks">
                    <Input value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} placeholder="Receiving remarks" />
                  </Field>
                  <Field label="Quality Inspection Notes" hint="Not stored yet — needs an API field.">
                    <Input placeholder="Inspection observations" disabled />
                  </Field>
                  <div>
                    <span className="label-overline mb-2 block">Supporting Documents</span>
                    <AttachmentsField files={[]} disabled />
                    <p className="mt-1.5 text-xs text-muted-foreground">Attachments are not stored yet — needs an upload endpoint.</p>
                  </div>
                </div>
              </FormSection>

              <FormSection title="Inspection & Receiving" icon={ShieldCheck} grid={false}>
                <div className="space-y-4">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <Field label="Inspection Status" hint="Not stored yet.">
                      <Select disabled>
                        <option>Pending</option>
                      </Select>
                    </Field>
                    <Field label="Warehouse Location" hint="Bin/location not stored yet.">
                      <Input placeholder="Bin / rack" disabled />
                    </Field>
                  </div>
                  <label className="flex items-center gap-2 text-sm text-muted-foreground">
                    <input type="checkbox" disabled className="h-4 w-4 rounded border-border" />
                    QC Passed <span className="text-xs">(not stored yet)</span>
                  </label>
                  <div>
                    <span className="label-overline mb-2 block">Receiving Checklist</span>
                    <ul className="space-y-1.5 text-sm text-muted-foreground">
                      {["Quantity verified against PO", "Packaging intact", "Batch / serial recorded", "Documents collected"].map((c) => (
                        <li key={c} className="flex items-center gap-2">
                          <input type="checkbox" disabled className="h-4 w-4 rounded border-border" />
                          {c}
                        </li>
                      ))}
                    </ul>
                    <p className="mt-1.5 text-xs text-muted-foreground">Checklist state is not stored yet — needs an API field.</p>
                  </div>
                </div>
              </FormSection>
            </div>

            {/* ── Important information cards ──────────────────────────── */}
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="rounded-2xl border border-[#FDE68A] bg-[#FFFBEB] p-5">
                <div className="mb-2 flex items-center gap-2 font-semibold text-[#92400E]">
                  <Info className="h-5 w-5" /> Important Notes
                </div>
                <ul className="list-disc space-y-1 pl-5 text-[13px] leading-relaxed text-[#92400E]">
                  <li>Verify quantity before posting.</li>
                  <li>Check product quality.</li>
                  <li>Verify batch &amp; serial.</li>
                  <li>Ensure warehouse selection.</li>
                </ul>
              </div>
              <div className="rounded-2xl border border-[#BBF7D0] bg-[#F0FDF4] p-5">
                <div className="mb-2 flex items-center gap-2 font-semibold text-[#166534]">
                  <ShieldCheck className="h-5 w-5" /> GRN Guidelines
                </div>
                <ul className="list-disc space-y-1 pl-5 text-[13px] leading-relaxed text-[#166534]">
                  <li>Stock updates after posting.</li>
                  <li>Linked with Purchase Order.</li>
                  <li>Tax calculated automatically.</li>
                  <li>Inventory ledger updated.</li>
                </ul>
              </div>
            </div>
          </div>

          {/* ── Right: sticky Goods Receipt Summary ───────────────────── */}
          <aside className="min-w-0">
            <SummaryCard
              title="Goods Receipt Summary"
              sticky
              rows={[
                { label: "Total Products", value: productCount },
                { label: "Ordered Qty", value: inr(totalOrdered) },
                { label: "Received Qty", value: inr(totalReceived) },
                { label: "Rejected Qty", value: "0.00" },
                { label: "Subtotal", value: `₹${inr(subtotal)}`, dividerBefore: true },
                { label: "CGST", value: `₹${inr(cgst)}` },
                { label: "SGST", value: `₹${inr(sgst)}` },
                { label: "IGST", value: `₹${inr(igst)}` },
                { label: "Other Charges", value: "₹0.00" },
                { label: "Round Off", value: "₹0.00" },
              ]}
              total={{ label: "Grand Total", value: `₹${inr(grandTotal)}` }}
              footer={
                <div className="text-center">
                  <div className="label-overline">Grand Total</div>
                  <div className="font-display text-2xl font-bold text-primary">₹{inr(grandTotal)}</div>
                </div>
              }
            />
          </aside>
        </form>
      </Modal>
    </div>
  );
}
