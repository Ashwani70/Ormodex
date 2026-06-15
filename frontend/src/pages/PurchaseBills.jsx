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

const blankLine = () => ({ stock_item_id: "", qty: 1, rate: 0, gst_rate: 18 });
const blank = () => ({
  vendor_invoice_no: "", vendor_invoice_date: "", vendor_id: "",
  purchase_order_id: "", grn_ids: [], tds_rate: 0, notes: "", lines: [blankLine()],
});

const lineTax = (l) => (parseFloat(l.qty) || 0) * (parseFloat(l.rate) || 0);
const lineTotal = (l) => lineTax(l) * (1 + (parseFloat(l.gst_rate) || 0) / 100);

export default function PurchaseBills() {
  const online = useOnline();
  const [items, setItems] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [orders, setOrders] = useState([]);
  const [grns, setGrns] = useState([]);
  const [bills, setBills] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank());

  const load = async () => {
    const [it, vd, po, gr, bl] = await Promise.all([
      api.get("/inventory/v2/items"),
      api.get("/purchase/v2/vendors"),
      api.get("/purchase/v2/orders"),
      api.get("/purchase/v2/grns"),
      api.get("/purchase/v2/bills"),
    ]);
    setItems(it.data); setVendors(vd.data); setOrders(po.data); setGrns(gr.data); setBills(bl.data);
  };
  useEffect(() => { load(); }, []);

  const setLine = (idx, patch) =>
    setForm((f) => ({ ...f, lines: f.lines.map((l, i) => (i === idx ? { ...l, ...patch } : l)) }));
  const addLine = () => setForm((f) => ({ ...f, lines: [...f.lines, blankLine()] }));
  const removeLine = (idx) => setForm((f) => ({ ...f, lines: f.lines.filter((_, i) => i !== idx) }));

  const toggleGrn = (id) =>
    setForm((f) => ({ ...f, grn_ids: f.grn_ids.includes(id) ? f.grn_ids.filter((g) => g !== id) : [...f.grn_ids, id] }));

  const taxable = form.lines.reduce((s, l) => s + lineTax(l), 0);
  const gross = form.lines.reduce((s, l) => s + lineTotal(l), 0);
  const tds = taxable * (parseFloat(form.tds_rate) || 0) / 100;
  const payable = gross - tds;

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
      await api.post("/purchase/v2/bills", {
        ...form,
        purchase_order_id: form.purchase_order_id || null,
        tds_rate: parseFloat(form.tds_rate) || 0,
        lines,
      });
      toast.success("Bill posted — accounting voucher created");
      setOpen(false);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  const vendorGrns = grns.filter((g) => !form.vendor_id || g.vendor_id === form.vendor_id);

  return (
    <div data-testid="purchase-bills-page">
      <PageHeader
        eyebrow="Purchase"
        title="Purchase Bills"
        description="Vendor invoices. Posting a bill creates the accounting voucher (Dr Inventory + Input GST, Cr Vendor)."
        actions={
          <PrimaryButton testid="new-bill" icon={Plus} disabled={!online}
            onClick={() => { setForm(blank()); setOpen(true); }}>
            New bill
          </PrimaryButton>
        }
      />
      <OfflineBanner online={online} />

      {bills.length === 0 ? (
        <EmptyState message="No purchase bills yet" />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm font-mono text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="border-b border-border label-overline">
                <th className="px-3 py-2.5">Bill No.</th>
                <th className="px-3 py-2.5">Vendor Inv.</th>
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5">Vendor</th>
                <th className="px-3 py-2.5">Voucher</th>
              </tr>
            </thead>
            <tbody>
              {bills.map((b) => (
                <tr key={b.id} data-testid={`bill-row-${b.id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                  <td className="px-3 py-2.5 text-foreground font-semibold">{b.bill_number}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{b.vendor_invoice_no}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{b.vendor_invoice_date}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{b.vendor_name}</td>
                  <td className="px-3 py-2.5 text-xs">
                    {b.journal_entry_id
                      ? <span className="text-emerald-400">posted</span>
                      : <span className="text-amber-400">no voucher</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title="New Purchase Bill" size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-bill" disabled={!online}>Post Bill</PrimaryButton>
          </>
        }>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <Field label="Vendor" required>
              <Select required value={form.vendor_id} data-testid="bill-vendor"
                onChange={(e) => setForm({ ...form, vendor_id: e.target.value, grn_ids: [] })}>
                <option value="">— Select vendor —</option>
                {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </Select>
            </Field>
            <Field label="Vendor Invoice No." required>
              <Input required value={form.vendor_invoice_no} data-testid="bill-invno"
                onChange={(e) => setForm({ ...form, vendor_invoice_no: e.target.value })} />
            </Field>
            <Field label="Invoice Date" required>
              <Input type="date" required value={form.vendor_invoice_date}
                onChange={(e) => setForm({ ...form, vendor_invoice_date: e.target.value })} />
            </Field>
            <Field label="TDS Rate %">
              <Input type="number" step="0.01" min="0" value={form.tds_rate}
                onChange={(e) => setForm({ ...form, tds_rate: e.target.value })} />
            </Field>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Link Purchase Order (optional)">
              <Select value={form.purchase_order_id}
                onChange={(e) => setForm({ ...form, purchase_order_id: e.target.value })}>
                <option value="">— None —</option>
                {orders.filter((p) => !form.vendor_id || p.vendor_id === form.vendor_id)
                  .map((p) => <option key={p.id} value={p.id}>{p.po_number}</option>)}
              </Select>
            </Field>
            <Field label="Link GRNs (optional, for 3-way match)">
              <div className="border border-border bg-background p-2 max-h-24 overflow-y-auto space-y-1" style={{ borderRadius: "var(--radius)" }}>
                {vendorGrns.length === 0
                  ? <span className="text-xs text-muted-foreground font-mono">No GRNs for this vendor</span>
                  : vendorGrns.map((g) => (
                    <label key={g.id} className="flex items-center gap-2 text-xs font-mono cursor-pointer">
                      <input type="checkbox" className="accent-primary"
                        checked={form.grn_ids.includes(g.id)} onChange={() => toggleGrn(g.id)} />
                      {g.grn_number}
                    </label>
                  ))}
              </div>
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
            <div className="text-right mt-3 font-mono text-xs text-muted-foreground space-y-0.5">
              <div>Taxable: {taxable.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</div>
              <div>Gross (incl. GST): {gross.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</div>
              {tds > 0 && <div>Less TDS: −{tds.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</div>}
              <div className="text-sm text-foreground">Net payable: <span className="font-bold text-primary">{payable.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span></div>
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
