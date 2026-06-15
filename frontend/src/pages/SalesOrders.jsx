import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
  Field,
  EmptyState,
  StatusBadge,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import LineItemsEditor from "@/components/LineItemsEditor";
import { CurrencyFields, downloadPdf, fmtMoney } from "@/lib/currency";
import SendEmailButton from "@/components/SendEmailButton";
import { Plus, Pencil, Trash2, Download, CheckCircle2 } from "lucide-react";

const blank = {
  customer_id: "",
  items: [],
  status: "PENDING",
  notes: "",
  currency: "INR",
  exchange_rate: 1,
};

export default function SalesOrders() {
  const [items, setItems] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);

  const load = async () => {
    const r = await api.get("/sales-orders");
    setItems(r.data);
  };
  useEffect(() => {
    load();
    api.get("/customers").then((r) => setCustomers(r.data));
    api.get("/products").then((r) => setProducts(r.data));
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.customer_id) return toast.error("Select a customer");
    if (form.items.length === 0) return toast.error("Add line items");
    const payload = {
      ...form,
      items: form.items.map((i) => ({
        ...i,
        quantity: Number(i.quantity),
        unit_price: Number(i.unit_price),
        gst_rate: Number(i.gst_rate),
      })),
    };
    try {
      if (editingId) await api.put(`/sales-orders/${editingId}`, payload);
      else await api.post("/sales-orders", payload);
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
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

  return (
    <div data-testid="sales-orders-page">
      <PageHeader
        eyebrow="Sales"
        title="Sales Orders"
        description="Confirmed orders awaiting dispatch"
        actions={
          <PrimaryButton
            icon={Plus}
            testid="new-so"
            onClick={() => {
              setForm(blank);
              setEditingId(null);
              setOpen(true);
            }}
          >
            New order
          </PrimaryButton>
        }
      />

      {items.length === 0 ? (
        <EmptyState message="No sales orders yet" />
      ) : (
        <div className="border border-border overflow-x-auto rounded-md">
          <table className="w-full text-sm">
            <thead className="bg-muted text-muted-foreground">
              <tr className="text-left label-overline border-b border-border">
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
              {items.map((p) => (
                <tr
                  key={p.id}
                  className="border-b border-border hover:bg-muted/60 text-foreground"
                >
                  <td className="px-3 py-2.5 font-mono text-primary font-bold">
                    {p.order_number}
                  </td>
                  <td className="px-3 py-2.5 text-foreground">{p.customer_name}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{p.items?.length}</td>
                  <td className="px-3 py-2.5 text-right tabular text-foreground font-semibold">
                    {fmtMoney(p.total, p.currency)}
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusBadge status={p.status} />
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                    {new Date(p.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="inline-flex gap-1">
                      {p.status === "PENDING" && (
                        <button
                          onClick={() => onConfirm(p)}
                          title="Confirm & deduct stock"
                          className="w-7 h-7 border border-border hover:border-green-500 hover:text-green-400 text-muted-foreground flex items-center justify-center bg-background"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                      <button
                        onClick={() =>
                          downloadPdf(
                            `/sales-orders/${p.id}/pdf`,
                            `${p.order_number}.pdf`
                          )
                        }
                        title="Download PDF"
                        data-testid={`pdf-${p.id}`}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground flex items-center justify-center bg-background"
                      >
                        <Download className="w-3.5 h-3.5" />
                      </button>
                      <SendEmailButton
                        docType="sales_order"
                        docId={p.id}
                        docNumber={p.order_number}
                        defaultRecipient={
                          customers.find((c) => c.id === p.customer_id)?.email || ""
                        }
                        defaultRecipientName={p.customer_name}
                      />
                      <button
                        onClick={() => {
                          setForm({ ...blank, ...p });
                          setEditingId(p.id);
                          setOpen(true);
                        }}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground flex items-center justify-center bg-background"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => onDelete(p)}
                        className="w-7 h-7 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground flex items-center justify-center bg-background"
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
        size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-so">
              Save
            </PrimaryButton>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Customer" required>
              <select
                required
                value={form.customer_id}
                data-testid="form-so-customer"
                onChange={(e) =>
                  setForm({ ...form, customer_id: e.target.value })
                }
                className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
              >
                <option value="">— select —</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.company || c.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Status">
              <select
                value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
                className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
              >
                {["PENDING", "CONFIRMED", "DISPATCHED", "DELIVERED", "CANCELLED"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <CurrencyFields form={form} setForm={setForm} />
          </div>
          <LineItemsEditor
            items={form.items}
            setItems={(items) => setForm({ ...form, items })}
            products={products}
          />
          <Field label="Notes">
            <textarea
              rows={2}
              value={form.notes || ""}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
            />
          </Field>
        </div>
      </Modal>
    </div>
  );
}
