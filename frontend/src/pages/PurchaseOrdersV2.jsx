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

const STATUSES = ["DRAFT", "SENT", "PARTIALLY_RECEIVED", "RECEIVED", "CLOSED", "CANCELLED"];
const blankLine = () => ({ stock_item_id: "", qty: 1, rate: 0, gst_rate: 18 });
const blank = () => ({ vendor_id: "", expected_date: "", status: "DRAFT", notes: "", lines: [blankLine()] });

const lineTotal = (l) => (parseFloat(l.qty) || 0) * (parseFloat(l.rate) || 0) * (1 + (parseFloat(l.gst_rate) || 0) / 100);

export default function PurchaseOrdersV2() {
  const online = useOnline();
  const [items, setItems] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [orders, setOrders] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank());

  const load = async () => {
    const [it, vd, po] = await Promise.all([
      api.get("/inventory/v2/items"),
      api.get("/purchase/v2/vendors"),
      api.get("/purchase/v2/orders"),
    ]);
    setItems(it.data); setVendors(vd.data); setOrders(po.data);
  };
  useEffect(() => { load(); }, []);

  const setLine = (idx, patch) =>
    setForm((f) => ({ ...f, lines: f.lines.map((l, i) => (i === idx ? { ...l, ...patch } : l)) }));
  const addLine = () => setForm((f) => ({ ...f, lines: [...f.lines, blankLine()] }));
  const removeLine = (idx) => setForm((f) => ({ ...f, lines: f.lines.filter((_, i) => i !== idx) }));

  const total = form.lines.reduce((s, l) => s + lineTotal(l), 0);

  const submit = async (e) => {
    e.preventDefault();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    const lines = form.lines
      .filter((l) => l.stock_item_id && parseFloat(l.qty) > 0)
      .map((l) => ({
        stock_item_id: l.stock_item_id,
        item_name: items.find((i) => i.id === l.stock_item_id)?.name,
        qty: parseFloat(l.qty), rate: parseFloat(l.rate) || 0, gst_rate: parseFloat(l.gst_rate) || 0,
      }));
    if (lines.length === 0) return toast.error("Add at least one line.");
    try {
      await api.post("/purchase/v2/orders", { ...form, expected_date: form.expected_date || null, lines });
      toast.success("Purchase order created");
      setOpen(false);
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

  return (
    <div data-testid="purchase-orders-v2-page">
      <PageHeader
        eyebrow="Purchase"
        title="Purchase Orders"
        description="Raise POs against vendors. Receipt status updates as GRNs are posted."
        actions={
          <PrimaryButton testid="new-po" icon={Plus} disabled={!online}
            onClick={() => { setForm(blank()); setOpen(true); }}>
            New PO
          </PrimaryButton>
        }
      />
      <OfflineBanner online={online} />

      {orders.length === 0 ? (
        <EmptyState message="No purchase orders yet" />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm font-mono text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="border-b border-border label-overline">
                <th className="px-3 py-2.5">PO Number</th>
                <th className="px-3 py-2.5">Vendor</th>
                <th className="px-3 py-2.5">Expected</th>
                <th className="px-3 py-2.5 text-right">Total</th>
                <th className="px-3 py-2.5">Status</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((po) => (
                <tr key={po.id} data-testid={`po-row-${po.id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                  <td className="px-3 py-2.5 text-foreground font-semibold">{po.po_number}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{po.vendor_name}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{po.expected_date || "—"}</td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground">{(po.total || 0).toLocaleString("en-IN")}</td>
                  <td className="px-3 py-2.5">
                    <Select value={po.status} onChange={(e) => changeStatus(po, e.target.value)}
                      className="text-xs py-1" disabled={!online}>
                      {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </Select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title="New Purchase Order" size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-po" disabled={!online}>Create PO</PrimaryButton>
          </>
        }>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="Vendor" required>
              <Select required value={form.vendor_id} data-testid="po-vendor"
                onChange={(e) => setForm({ ...form, vendor_id: e.target.value })}>
                <option value="">— Select vendor —</option>
                {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </Select>
            </Field>
            <Field label="Expected Date">
              <Input type="date" value={form.expected_date}
                onChange={(e) => setForm({ ...form, expected_date: e.target.value })} />
            </Field>
            <Field label="Status">
              <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </Select>
            </Field>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="label-overline">Lines</div>
              <SecondaryButton icon={Plus} onClick={addLine}>Add line</SecondaryButton>
            </div>
            <div className="space-y-2">
              {form.lines.map((l, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-2 items-end">
                  <div className="col-span-5">
                    <Select value={l.stock_item_id} onChange={(e) => setLine(idx, { stock_item_id: e.target.value })}>
                      <option value="">— Item —</option>
                      {items.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
                    </Select>
                  </div>
                  <div className="col-span-2">
                    <Input type="number" step="0.01" min="0" placeholder="Qty" value={l.qty}
                      onChange={(e) => setLine(idx, { qty: e.target.value })} />
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
              ))}
            </div>
            <div className="text-right mt-3 font-mono text-sm text-foreground">
              Total (incl. GST): <span className="font-bold text-primary">{total.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span>
            </div>
          </div>

          <Field label="Notes">
            <Input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </Field>
        </form>
      </Modal>
    </div>
  );
}
