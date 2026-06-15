import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Textarea, Field, EmptyState,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";
import { Plus, Pencil } from "lucide-react";

const blank = {
  name: "", gstin: "", pan: "", billing_address: "", shipping_address: "",
  state_code: "", payment_terms_days: 0, opening_balance: 0, email: "", phone: "",
};

export default function Vendors() {
  const online = useOnline();
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);

  const load = async () => {
    const r = await api.get("/purchase/v2/vendors");
    setItems(r.data);
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    const payload = {
      ...form,
      payment_terms_days: parseInt(form.payment_terms_days) || 0,
      opening_balance: parseFloat(form.opening_balance) || 0,
    };
    try {
      if (editingId) await api.put(`/purchase/v2/vendors/${editingId}`, payload);
      else await api.post("/purchase/v2/vendors", payload);
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  return (
    <div data-testid="vendors-page">
      <PageHeader
        eyebrow="Purchase"
        title="Vendors"
        description="Vendor master with GSTIN, PAN and place-of-supply state for IGST vs CGST+SGST."
        actions={
          <PrimaryButton testid="new-vendor" icon={Plus} disabled={!online}
            onClick={() => { setForm(blank); setEditingId(null); setOpen(true); }}>
            New vendor
          </PrimaryButton>
        }
      />
      <OfflineBanner online={online} />

      {items.length === 0 ? (
        <EmptyState message="No vendors yet" />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm font-mono text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="border-b border-border label-overline">
                <th className="px-3 py-2.5">Code</th>
                <th className="px-3 py-2.5">Name</th>
                <th className="px-3 py-2.5">GSTIN</th>
                <th className="px-3 py-2.5">State</th>
                <th className="px-3 py-2.5 text-right">Terms (days)</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((v) => (
                <tr key={v.id} data-testid={`vendor-row-${v.id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                  <td className="px-3 py-2.5 text-muted-foreground text-xs">{v.vendor_code || "—"}</td>
                  <td className="px-3 py-2.5 text-foreground font-semibold">{v.name}</td>
                  <td className="px-3 py-2.5 text-muted-foreground text-xs">{v.gstin || "—"}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{v.state_code || "—"}</td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground">{v.payment_terms_days || 0}</td>
                  <td className="px-3 py-2.5 text-right">
                    <button onClick={() => { setForm({ ...blank, ...v }); setEditingId(v.id); setOpen(true); }}
                      className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center">
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title={editingId ? "Edit Vendor" : "New Vendor"}
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-vendor" disabled={!online}>Save</PrimaryButton>
          </>
        }>
        <form onSubmit={submit} className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Name" required>
              <Input required data-testid="form-vendor-name" value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="State Code">
              <Input value={form.state_code || ""} placeholder="e.g. 27"
                onChange={(e) => setForm({ ...form, state_code: e.target.value })} />
            </Field>
            <Field label="GSTIN">
              <Input value={form.gstin || ""} placeholder="15-digit GSTIN"
                onChange={(e) => setForm({ ...form, gstin: e.target.value })} />
            </Field>
            <Field label="PAN">
              <Input value={form.pan || ""} placeholder="10-char PAN"
                onChange={(e) => setForm({ ...form, pan: e.target.value })} />
            </Field>
            <Field label="Email">
              <Input type="email" value={form.email || ""}
                onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </Field>
            <Field label="Phone">
              <Input value={form.phone || ""} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </Field>
            <Field label="Payment Terms (days)">
              <Input type="number" value={form.payment_terms_days}
                onChange={(e) => setForm({ ...form, payment_terms_days: e.target.value })} />
            </Field>
            <Field label="Opening Balance">
              <Input type="number" step="0.01" value={form.opening_balance}
                onChange={(e) => setForm({ ...form, opening_balance: e.target.value })} />
            </Field>
          </div>
          <Field label="Billing Address">
            <Textarea rows={2} value={form.billing_address || ""}
              onChange={(e) => setForm({ ...form, billing_address: e.target.value })} />
          </Field>
          <Field label="Shipping Address">
            <Textarea rows={2} value={form.shipping_address || ""}
              onChange={(e) => setForm({ ...form, shipping_address: e.target.value })} />
          </Field>
        </form>
      </Modal>
    </div>
  );
}
