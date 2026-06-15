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

const blankLine = () => ({ stock_item_id: "", qty: 1, rate: 0, gst_rate: 18, batch_id: "" });
const blank = () => ({
  vendor_id: "", purchase_bill_id: "", grn_id: "", godown_id: "", return_date: "",
  reason: "", lines: [blankLine()],
});

export default function PurchaseReturns() {
  const online = useOnline();
  const [items, setItems] = useState([]);
  const [godowns, setGodowns] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [bills, setBills] = useState([]);
  const [returns, setReturns] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank());

  const load = async () => {
    const [it, gd, vd, bl, rt] = await Promise.all([
      api.get("/inventory/v2/items"),
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
  const addLine = () => setForm((f) => ({ ...f, lines: [...f.lines, blankLine()] }));
  const removeLine = (idx) => setForm((f) => ({ ...f, lines: f.lines.filter((_, i) => i !== idx) }));

  const submit = async (e) => {
    e.preventDefault();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    if (!form.godown_id) return toast.error("Select the godown goods are returned from.");
    const lines = form.lines
      .filter((l) => l.stock_item_id && parseFloat(l.qty) > 0)
      .map((l) => {
        const it = itemById(l.stock_item_id);
        return {
          stock_item_id: l.stock_item_id,
          item_name: it.name,
          qty: parseFloat(l.qty), rate: parseFloat(l.rate) || 0, gst_rate: parseFloat(l.gst_rate) || 0,
          batch_id: (it.track_batch || it.track_expiry) ? (l.batch_id || null) : null,
        };
      });
    if (lines.length === 0) return toast.error("Add at least one line.");
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

  return (
    <div data-testid="purchase-returns-page">
      <PageHeader
        eyebrow="Purchase"
        title="Purchase Returns / Debit Notes"
        description="Return goods to a vendor. Posts outward stock and reverses the input GST / payable."
        actions={
          <PrimaryButton testid="new-return" icon={Plus} disabled={!online}
            onClick={() => { setForm(blank()); setOpen(true); }}>
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
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="Vendor" required>
              <Select required value={form.vendor_id} data-testid="return-vendor"
                onChange={(e) => setForm({ ...form, vendor_id: e.target.value, purchase_bill_id: "" })}>
                <option value="">— Select vendor —</option>
                {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </Select>
            </Field>
            <Field label="From Godown" required>
              <Select required value={form.godown_id} data-testid="return-godown"
                onChange={(e) => setForm({ ...form, godown_id: e.target.value })}>
                <option value="">— Select godown —</option>
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
            <div className="space-y-2">
              {form.lines.map((l, idx) => {
                const it = itemById(l.stock_item_id);
                const needsBatch = it.track_batch || it.track_expiry;
                return (
                  <div key={idx} className="grid grid-cols-12 gap-2 items-end">
                    <div className="col-span-4">
                      <Select value={l.stock_item_id} onChange={(e) => setLine(idx, { stock_item_id: e.target.value })}>
                        <option value="">— Item —</option>
                        {items.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
                      </Select>
                    </div>
                    <div className="col-span-2">
                      <Input type="number" step="0.0001" min="0" placeholder="Qty" value={l.qty}
                        onChange={(e) => setLine(idx, { qty: e.target.value })} />
                    </div>
                    <div className="col-span-2">
                      <Input type="number" step="0.01" min="0" placeholder="Rate" value={l.rate}
                        onChange={(e) => setLine(idx, { rate: e.target.value })} />
                    </div>
                    <div className="col-span-1">
                      <Input type="number" step="0.01" min="0" placeholder="GST%" value={l.gst_rate}
                        onChange={(e) => setLine(idx, { gst_rate: e.target.value })} />
                    </div>
                    <div className="col-span-2">
                      {needsBatch
                        ? <Input placeholder="Batch" value={l.batch_id}
                            onChange={(e) => setLine(idx, { batch_id: e.target.value })} />
                        : <span className="text-[10px] text-muted-foreground font-mono">—</span>}
                    </div>
                    <div className="col-span-1">
                      <button type="button" onClick={() => removeLine(idx)}
                        className="w-9 h-9 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground flex items-center justify-center">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
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
