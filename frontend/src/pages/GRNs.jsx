import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Field, Select, EmptyState,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";
import { Plus, X } from "lucide-react";

const blankLine = () => ({
  stock_item_id: "", po_line_index: null, qty_received: 1, rate: 0, gst_rate: 18,
  batch_id: "", serial_id: "", expiry_date: "",
});
const blank = () => ({
  purchase_order_id: "", vendor_id: "", godown_id: "", received_date: "", remarks: "",
  lines: [blankLine()],
});

export default function GRNs() {
  const online = useOnline();
  const [items, setItems] = useState([]);
  const [godowns, setGodowns] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [orders, setOrders] = useState([]);
  const [grns, setGrns] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank());

  const load = async () => {
    const [it, gd, vd, po, gr] = await Promise.all([
      api.get("/inventory/v2/items"),
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
  const addLine = () => setForm((f) => ({ ...f, lines: [...f.lines, blankLine()] }));
  const removeLine = (idx) => setForm((f) => ({ ...f, lines: f.lines.filter((_, i) => i !== idx) }));

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
        stock_item_id: pl.stock_item_id,
        po_line_index: idx,
        qty_received: Math.max(0, (parseFloat(pl.qty) || 0) - (parseFloat(pl.received_qty) || 0)),
        rate: pl.rate || 0,
        gst_rate: pl.gst_rate ?? 18,
      })),
    }));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    if (!form.godown_id) return toast.error("Select a target godown.");
    const lines = form.lines
      .filter((l) => l.stock_item_id && parseFloat(l.qty_received) > 0)
      .map((l) => {
        const it = itemById(l.stock_item_id);
        return {
          stock_item_id: l.stock_item_id,
          item_name: it.name,
          po_line_index: l.po_line_index,
          qty_received: parseFloat(l.qty_received),
          rate: parseFloat(l.rate) || 0,
          gst_rate: parseFloat(l.gst_rate) || 0,
          batch_id: it.track_batch || it.track_expiry ? (l.batch_id || null) : null,
          serial_id: it.track_serial ? (l.serial_id || null) : null,
          expiry_date: it.track_expiry ? (l.expiry_date || null) : null,
        };
      });
    if (lines.length === 0) return toast.error("Add at least one received line.");
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
    }
  };

  return (
    <div data-testid="grns-page">
      <PageHeader
        eyebrow="Purchase"
        title="Goods Receipt Notes"
        description="Record goods received into a godown. Posting a GRN writes inward stock-ledger entries."
        actions={
          <PrimaryButton testid="new-grn" icon={Plus} disabled={!online}
            onClick={() => { setForm(blank()); setOpen(true); }}>
            New GRN
          </PrimaryButton>
        }
      />
      <OfflineBanner online={online} />

      {grns.length === 0 ? (
        <EmptyState message="No goods receipt notes yet" />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm font-mono text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="border-b border-border label-overline">
                <th className="px-3 py-2.5">GRN Number</th>
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5">Vendor</th>
                <th className="px-3 py-2.5 text-right">Lines</th>
              </tr>
            </thead>
            <tbody>
              {grns.map((g) => (
                <tr key={g.id} data-testid={`grn-row-${g.id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                  <td className="px-3 py-2.5 text-foreground font-semibold">{g.grn_number}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{g.received_date}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{g.vendor_name}</td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground">{(g.lines || []).length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title="New Goods Receipt Note" size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-grn" disabled={!online}>Post GRN</PrimaryButton>
          </>
        }>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <Field label="Purchase Order (optional)">
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
                {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </Select>
            </Field>
            <Field label="Target Godown" required>
              <Select required value={form.godown_id} data-testid="grn-godown"
                onChange={(e) => setForm({ ...form, godown_id: e.target.value })}>
                <option value="">— Select godown —</option>
                {godowns.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </Select>
            </Field>
            <Field label="Received Date">
              <Input type="date" value={form.received_date}
                onChange={(e) => setForm({ ...form, received_date: e.target.value })} />
            </Field>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="label-overline">Received lines</div>
              <SecondaryButton icon={Plus} onClick={addLine}>Add line</SecondaryButton>
            </div>
            <div className="space-y-3">
              {form.lines.map((l, idx) => {
                const it = itemById(l.stock_item_id);
                const needsBatch = it.track_batch || it.track_expiry;
                return (
                  <div key={idx} className="border border-border p-3 bg-muted/10">
                    <div className="grid grid-cols-12 gap-2 items-end">
                      <div className="col-span-5">
                        <Select value={l.stock_item_id} onChange={(e) => setLine(idx, { stock_item_id: e.target.value })}>
                          <option value="">— Item —</option>
                          {items.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
                        </Select>
                      </div>
                      <div className="col-span-2">
                        <Input type="number" step="0.0001" min="0" placeholder="Qty recd" value={l.qty_received}
                          onChange={(e) => setLine(idx, { qty_received: e.target.value })} />
                      </div>
                      <div className="col-span-2">
                        <Input type="number" step="0.01" min="0" placeholder="Rate" value={l.rate}
                          onChange={(e) => setLine(idx, { rate: e.target.value })} />
                      </div>
                      <div className="col-span-2">
                        <Input type="number" step="0.01" min="0" placeholder="GST%" value={l.gst_rate}
                          onChange={(e) => setLine(idx, { gst_rate: e.target.value })} />
                      </div>
                      <div className="col-span-1">
                        <button type="button" onClick={() => removeLine(idx)}
                          className="w-9 h-9 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground flex items-center justify-center">
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    {/* Conditional capture — only for items that track it. */}
                    {(needsBatch || it.track_serial) && (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-2 pt-2 border-t border-border">
                        {needsBatch && (
                          <Field label="Batch No.">
                            <Input value={l.batch_id} data-testid={`grn-batch-${idx}`}
                              onChange={(e) => setLine(idx, { batch_id: e.target.value })} />
                          </Field>
                        )}
                        {it.track_expiry && (
                          <Field label="Expiry Date">
                            <Input type="date" value={l.expiry_date} data-testid={`grn-expiry-${idx}`}
                              onChange={(e) => setLine(idx, { expiry_date: e.target.value })} />
                          </Field>
                        )}
                        {it.track_serial && (
                          <Field label="Serial No.">
                            <Input value={l.serial_id} data-testid={`grn-serial-${idx}`}
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

          <Field label="Remarks">
            <Input value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} />
          </Field>
        </form>
      </Modal>
    </div>
  );
}
