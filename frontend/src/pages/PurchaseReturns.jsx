import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Field, Select, EmptyState, NumericInput,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";
import usePdfAction from "@/hooks/usePdfAction";
import useTrackingFlags from "@/hooks/useTrackingFlags";
import { missingTrackingFields } from "@/lib/tracking";
import useGridKeyNav from "@/hooks/useGridKeyNav";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { Plus, X, Download, PenLine, Package } from "lucide-react";

const UOM_OPTIONS = ["pcs", "nos", "kg", "g", "mg", "l", "ml", "m", "cm", "mm", "ft", "inch", "box", "pair", "set", "bag", "roll", "sheet", "mtr", "sqft", "sqm", "hr", "day"];
const UOM_LABELS = { pcs: "Pcs", nos: "Nos", mtr: "Mtr" };
const uomLabel = (u) => UOM_LABELS[u] || u;
const blankLine = () => ({ product_id: "", product_name: "", hsn_code: "", unit: "pcs", qty: "", rate: "", gst_rate: "", _manual: false, batch_id: "", serial_id: "", expiry_date: "" });
const blank = () => ({
  vendor_id: "", purchase_bill_id: "", grn_id: "", godown_id: "", return_date: "",
  reason: "", lines: [blankLine()],
});

export default function PurchaseReturns() {
  const online = useOnline();
  const { run: downloadReturnPdf, busyId } = usePdfAction();
  const [items, setItems] = useState([]);
  const [godowns, setGodowns] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [bills, setBills] = useState([]);
  const [returns, setReturns] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank());
  const { flagsFor, ensureFlags } = useTrackingFlags();

  const load = async () => {
    const [it, gd, vd, bl, rt] = await Promise.all([
      api.get("/products"),
      api.get("/inventory/v2/godowns"),
      api.get("/purchase/v2/vendors"),
      api.get("/purchase/v2/bills"),
      api.get("/purchase/v2/returns"),
    ]);
    setItems(it.data); setGodowns(gd.data); setVendors(vd.data); setBills(bl.data); setReturns(rt.data);
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

  // Keyboard-first line-item entry: Product → HSN → Qty → Unit → Rate → GST,
  // then Enter on the last column of the last row appends a new row. No
  // GST-type sub-widget on this form (plain GST% only), so a fixed colCount.
  const gridNav = useGridKeyNav({
    rowCount: form.lines.length,
    colCount: 6,
    onRowComplete: addLine,
    onInsertRow: insertLineAfter,
    onDeleteRow: removeLineKeepingOne,
  });

  const onPickProduct = (idx, productId) => {
    const p = itemById(productId);
    setLine(idx, {
      product_id: productId,
      ...(p.id ? {
        hsn_code: p.hsn_code || "",
        unit: p.unit || "pcs",
        rate: p.cost_price != null ? Number(p.cost_price) : "",
        gst_rate: p.gst_rate != null ? Number(p.gst_rate) : "",
      } : {}),
    });
    if (productId) ensureFlags([productId]);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    if (!form.godown_id) return toast.error("Select the warehouse goods are returned from.");
    const lines = form.lines
      .filter((l) => (l._manual ? l.product_name?.trim() : l.product_id) && parseFloat(l.qty) > 0)
      .map((l) => {
        const it = l._manual ? {} : itemById(l.product_id);
        return {
          product_id: l._manual ? null : l.product_id,
          product_name: l._manual ? l.product_name : it.name,
          hsn_code: l.hsn_code || null,
          unit: l.unit || "pcs",
          qty: parseFloat(l.qty), rate: parseFloat(l.rate) || 0, gst_rate: parseFloat(l.gst_rate) || 0,
          batch_id: l.batch_id || null,
          serial_id: l.serial_id || null,
          expiry_date: l.expiry_date || null,
        };
      });
    if (lines.length === 0) return toast.error("Add at least one line.");
    for (const l of lines) {
      if (l._manual) continue;
      const miss = missingTrackingFields(l, flagsFor(l.product_id));
      if (miss.length) {
        return toast.error(`${miss.join(" & ")} required for '${l.product_name || l.product_id}'.`);
      }
    }
    try {
      await api.post("/purchase/v2/returns", {
        ...form,
        purchase_bill_id: form.purchase_bill_id || null,
        grn_id: form.grn_id || null,
        return_date: form.return_date || null,
        lines,
      });
      toast.success("Return posted — stock and accounting reversed");
      setOpen(false);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  const openNew = () => { setForm(blank()); setOpen(true); };

  // Enter-as-Tab across the whole form; Ctrl+Enter/Ctrl+S saves,
  // Ctrl+Shift+Enter/Ctrl+Shift+S saves and opens a fresh blank return, Esc
  // cancels. The line-item grid above is marked data-grid-managed so its own
  // useGridKeyNav Enter/Arrow handling isn't swallowed by this listener.
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

  useModuleShortcuts({
    onNew: () => { if (!open) openNew(); },
  });

  return (
    <div data-testid="purchase-returns-page">
      <PageHeader
        eyebrow="Purchase"
        title="Purchase Returns / Debit Notes"
        description="Return goods to a vendor. Posts outward stock and reverses the input GST / payable."
        actions={
          <PrimaryButton testid="new-return" icon={Plus} disabled={!online}
            onClick={openNew}>
            New return
          </PrimaryButton>
        }
      />
      <OfflineBanner online={online} />

      {returns.length === 0 ? (
        <EmptyState message="No purchase returns yet" />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm font-mono text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="border-b border-border label-overline">
                <th className="px-3 py-2.5">Debit Note</th>
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5">Vendor</th>
                <th className="px-3 py-2.5">Voucher</th>
                <th className="px-3 py-2.5 text-right">PDF</th>
              </tr>
            </thead>
            <tbody>
              {returns.map((r) => (
                <tr key={r.id} data-testid={`return-row-${r.id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                  <td className="px-3 py-2.5 text-foreground font-semibold">{r.debit_note_number}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{r.return_date}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{r.vendor_name}</td>
                  <td className="px-3 py-2.5 text-xs">
                    {r.journal_entry_id
                      ? <span className="text-emerald-400">reversed</span>
                      : <span className="text-amber-400">no voucher</span>}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <button
                      onClick={() => downloadReturnPdf(`/purchase/v2/returns/${r.id}/pdf`, `${r.debit_note_number}.pdf`, r.id)}
                      disabled={busyId === r.id}
                      title="Download Debit Note PDF"
                      data-testid={`return-pdf-${r.id}`}
                      className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center disabled:opacity-50"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title="New Purchase Return" size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-return" disabled={!online}>Post Return</PrimaryButton>
          </>
        }>
        <form ref={formRef} onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="Vendor" required>
              <Select required value={form.vendor_id} data-testid="return-vendor"
                onChange={(e) => setForm({ ...form, vendor_id: e.target.value, purchase_bill_id: "" })}>
                <option value="">— Select vendor —</option>
                {vendors.map((v) => <option key={v.id} value={v.id}>{v.company || v.name}</option>)}
              </Select>
            </Field>
            <Field label="From Warehouse" required>
              <Select required value={form.godown_id} data-testid="return-godown"
                onChange={(e) => setForm({ ...form, godown_id: e.target.value })}>
                <option value="">— Select warehouse —</option>
                {godowns.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </Select>
            </Field>
            <Field label="Return Date">
              <Input type="date" value={form.return_date}
                onChange={(e) => setForm({ ...form, return_date: e.target.value })} />
            </Field>
            <Field label="Against Bill (optional)">
              <Select value={form.purchase_bill_id}
                onChange={(e) => setForm({ ...form, purchase_bill_id: e.target.value })}>
                <option value="">— None —</option>
                {bills.filter((b) => !form.vendor_id || b.vendor_id === form.vendor_id)
                  .map((b) => <option key={b.id} value={b.id}>{b.bill_number} ({b.vendor_invoice_no})</option>)}
              </Select>
            </Field>
            <Field label="Reason">
              <Input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
            </Field>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="label-overline">Returned lines</div>
              <SecondaryButton icon={Plus} onClick={addLine}>Add line</SecondaryButton>
            </div>
            <div className="space-y-3" data-grid-managed>
              {form.lines.map((l, idx) => {
                const flags = flagsFor(l.product_id);
                const showTracking = l.product_id && (flags.track_batch || flags.track_serial || flags.track_expiry);
                return (
                  <div key={idx} className="border border-border p-3 bg-muted/10">
                    <div className="grid grid-cols-12 gap-2 items-start">
                      <div className="col-span-1 flex justify-center pt-5">
                        <button
                          type="button"
                          title={l._manual ? "Switch to catalog product" : "Enter product manually"}
                          onClick={() => toggleLineManual(idx)}
                          className={`w-9 h-9 border flex items-center justify-center transition-colors ${l._manual ? "border-amber-500 text-amber-400" : "border-border text-muted-foreground hover:border-primary hover:text-primary"}`}
                        >
                          {l._manual ? <PenLine className="w-4 h-4" /> : <Package className="w-4 h-4" />}
                        </button>
                      </div>
                      <div className="col-span-3">
                        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-1">Product</div>
                        {l._manual ? (
                          <Input
                            placeholder="Product name (manual)"
                            value={l.product_name || ""}
                            onChange={(e) => setLine(idx, { product_name: e.target.value })}
                            ref={gridNav.registerCell(idx, 0)} onKeyDown={gridNav.handleKeyDown(idx, 0)}
                            className="border-amber-500/60 focus:border-amber-400"
                          />
                        ) : (
                          <Select value={l.product_id} onChange={(e) => onPickProduct(idx, e.target.value)}
                            ref={gridNav.registerCell(idx, 0)} onKeyDown={gridNav.handleKeyDown(idx, 0)}>
                            <option value="">— Product —</option>
                            {items.map((i) => <option key={i.id} value={i.id}>{i.name}{i.sku ? ` (${i.sku})` : ""}</option>)}
                          </Select>
                        )}
                      </div>
                      <div className="col-span-2">
                        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-1">HSN / SAC</div>
                        <Input placeholder="e.g. 7308" value={l.hsn_code || ""}
                          onChange={(e) => setLine(idx, { hsn_code: e.target.value })}
                          ref={gridNav.registerCell(idx, 1)} onKeyDown={gridNav.handleKeyDown(idx, 1)}
                          className="font-mono" />
                      </div>
                      <div className="col-span-1">
                        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-1">Qty</div>
                        <NumericInput value={l.qty} onChange={(v) => setLine(idx, { qty: v })} placeholder="0"
                          ref={gridNav.registerCell(idx, 2)} onKeyDown={gridNav.handleKeyDown(idx, 2)} />
                      </div>
                      <div className="col-span-1">
                        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-1">Unit</div>
                        <Select value={l.unit || "pcs"} onChange={(e) => setLine(idx, { unit: e.target.value })}
                          ref={gridNav.registerCell(idx, 3)} onKeyDown={gridNav.handleKeyDown(idx, 3)}>
                          {UOM_OPTIONS.map((u) => <option key={u} value={u}>{uomLabel(u)}</option>)}
                        </Select>
                      </div>
                      <div className="col-span-2">
                        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-1">Rate ₹</div>
                        <NumericInput value={l.rate} onChange={(v) => setLine(idx, { rate: v })} placeholder="0.00"
                          ref={gridNav.registerCell(idx, 4)} onKeyDown={gridNav.handleKeyDown(idx, 4)} />
                      </div>
                      <div className="col-span-1">
                        <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-1">GST %</div>
                        <NumericInput value={l.gst_rate} onChange={(v) => setLine(idx, { gst_rate: v })} placeholder="18" max={100}
                          ref={gridNav.registerCell(idx, 5)} onKeyDown={gridNav.handleKeyDown(idx, 5)} />
                      </div>
                      <div className="col-span-1 flex justify-center pt-5">
                        <button type="button" onClick={() => removeLine(idx)}
                          className="w-9 h-9 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground flex items-center justify-center">
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    {/* Batch / serial / expiry — shown and required only for
                        items whose linked stock_item tracks them. */}
                    {showTracking && (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-2 pt-2 border-t border-border">
                        {flags.track_batch && (
                          <Field label="Batch No." required>
                            <Input required value={l.batch_id} data-testid={`return-batch-${idx}`}
                              onChange={(e) => setLine(idx, { batch_id: e.target.value })} />
                          </Field>
                        )}
                        {flags.track_expiry && (
                          <Field label="Expiry Date" required>
                            <Input required type="date" value={l.expiry_date} data-testid={`return-expiry-${idx}`}
                              onChange={(e) => setLine(idx, { expiry_date: e.target.value })} />
                          </Field>
                        )}
                        {flags.track_serial && (
                          <Field label="Serial No." required>
                            <Input required value={l.serial_id} data-testid={`return-serial-${idx}`}
                              onChange={(e) => setLine(idx, { serial_id: e.target.value })} />
                          </Field>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </form>
      </Modal>
    </div>
  );
}
