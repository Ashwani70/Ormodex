import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Field, Select, EmptyState,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { Plus, Pencil, Trash2 } from "lucide-react";

const blank = {
  name: "", sku: "", item_type: "GOODS", hsn_sac_code: "", gst_rate: 18,
  default_unit_id: "", valuation_method: "WEIGHTED_AVG",
  opening_stock_qty: "", opening_stock_value: "",
  reorder_level: "", reorder_qty: "", min_level: "", max_level: "",
  track_batch: false, track_serial: false, track_expiry: false,
};

function Toggle({ label, checked, onChange, testid }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <input type="checkbox" checked={checked} data-testid={testid}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-primary w-4 h-4" />
      <span className="label-overline">{label}</span>
    </label>
  );
}

export default function StockItems() {
  const online = useOnline();
  const [items, setItems] = useState([]);
  const [units, setUnits] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);

  const load = async () => {
    const [it, un] = await Promise.all([
      api.get("/inventory/v2/items"),
      api.get("/inventory/v2/units"),
    ]);
    setItems(it.data);
    setUnits(un.data);
  };
  useEffect(() => { load(); }, []);

  const num = (v) => (v === "" || v == null ? 0 : parseFloat(v) || 0);

  const submit = async (e) => {
    e.preventDefault();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    const payload = {
      ...form,
      gst_rate: num(form.gst_rate),
      opening_stock_qty: num(form.opening_stock_qty),
      opening_stock_value: num(form.opening_stock_value),
      reorder_level: num(form.reorder_level),
      reorder_qty: num(form.reorder_qty),
      min_level: num(form.min_level),
      max_level: num(form.max_level),
      default_unit_id: form.default_unit_id || null,
    };
    try {
      if (editingId) await api.put(`/inventory/v2/items/${editingId}`, payload);
      else await api.post("/inventory/v2/items", payload);
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  const onDelete = async (item) => {
    if (!online) return toast.warning("You are offline — deleting is disabled.");
    if (!window.confirm(`Delete item ${item.name}?`)) return;
    try {
      await api.delete(`/inventory/v2/items/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  const startEdit = (it) => { setForm({ ...blank, ...it }); setEditingId(it.id); setOpen(true); };
  const startNew = () => { setForm(blank); setEditingId(null); setOpen(true); };

  // Enter-as-Tab across the modal form; Ctrl+Enter/Ctrl+S saves, Esc cancels,
  // first field auto-focuses when the modal opens.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: open,
    autoFocus: true,
    onSave: () => submit(new Event("submit", { cancelable: true })),
    onCancel: () => setOpen(false),
  });

  useModuleShortcuts({
    onNew: () => { if (!open && online) startNew(); },
  });

  return (
    <div data-testid="stock-items-page">
      <PageHeader
        eyebrow="Inventory"
        title="Stock Items"
        description="Item master with HSN/SAC, GST, valuation method and batch/serial/expiry tracking."
        actions={
          <PrimaryButton testid="new-stock-item" icon={Plus} disabled={!online} onClick={startNew}>
            New item
          </PrimaryButton>
        }
      />
      <OfflineBanner online={online} />

      {items.length === 0 ? (
        <EmptyState message="No stock items yet" />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm font-mono text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="border-b border-border label-overline">
                <th className="px-3 py-2.5">Name</th>
                <th className="px-3 py-2.5">Type</th>
                <th className="px-3 py-2.5">HSN/SAC</th>
                <th className="px-3 py-2.5 text-right">GST %</th>
                <th className="px-3 py-2.5">Valuation</th>
                <th className="px-3 py-2.5">Tracking</th>
                <th className="px-3 py-2.5 text-right">Reorder</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id} data-testid={`stock-item-row-${it.id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                  <td className="px-3 py-2.5 text-foreground font-semibold">{it.name}</td>
                  <td className="px-3 py-2.5 text-xs text-muted-foreground">{it.item_type}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{it.hsn_sac_code || "—"}</td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground">{it.gst_rate}</td>
                  <td className="px-3 py-2.5 text-xs text-muted-foreground">{it.valuation_method}</td>
                  <td className="px-3 py-2.5 text-[10px]">
                    {["track_batch", "track_serial", "track_expiry"].filter((k) => it[k])
                      .map((k) => k.replace("track_", "")).join(", ") || "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground">{it.reorder_level}</td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="inline-flex gap-1">
                      <button onClick={() => startEdit(it)}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground flex items-center justify-center">
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => onDelete(it)}
                        className="w-7 h-7 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground flex items-center justify-center">
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

      <Modal open={open} onClose={() => setOpen(false)} title={editingId ? "Edit Stock Item" : "New Stock Item"}
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-stock-item" disabled={!online}>Save</PrimaryButton>
          </>
        }>
        <form ref={formRef} onSubmit={submit} className="space-y-6">
          <div>
            <div className="label-overline mb-2 text-primary">Item details</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-muted/20 p-4 border border-border">
              <Field label="Name" required>
                <Input required data-testid="form-item-name" value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </Field>
              <Field label="SKU">
                <Input value={form.sku || ""} onChange={(e) => setForm({ ...form, sku: e.target.value })} />
              </Field>
              <Field label="Item Type" required>
                <Select value={form.item_type} onChange={(e) => setForm({ ...form, item_type: e.target.value })}>
                  <option value="GOODS">Goods</option>
                  <option value="SERVICE">Service</option>
                </Select>
              </Field>
              <Field label="Default Unit">
                <Select value={form.default_unit_id || ""} onChange={(e) => setForm({ ...form, default_unit_id: e.target.value })}>
                  <option value="">— Select unit —</option>
                  {units.map((u) => <option key={u.id} value={u.id}>{u.name} ({u.uqc_code})</option>)}
                </Select>
              </Field>
              <Field label="HSN / SAC Code">
                <Input value={form.hsn_sac_code || ""} onChange={(e) => setForm({ ...form, hsn_sac_code: e.target.value })} />
              </Field>
              <Field label="GST Rate %">
                <Input type="text" inputMode="decimal" step="0.01" value={form.gst_rate}
                  onChange={(e) => setForm({ ...form, gst_rate: e.target.value })} />
              </Field>
            </div>
          </div>

          <div>
            <div className="label-overline mb-2 text-primary">Valuation & opening stock</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-muted/20 p-4 border border-border">
              <Field label="Valuation Method" required>
                <Select value={form.valuation_method} data-testid="form-valuation-method"
                  onChange={(e) => setForm({ ...form, valuation_method: e.target.value })}>
                  <option value="WEIGHTED_AVG">Weighted Average</option>
                  <option value="FIFO">FIFO</option>
                </Select>
              </Field>
              <div />
              <Field label="Opening Stock Qty">
                <Input type="text" inputMode="decimal" step="0.0001" value={form.opening_stock_qty}
                  onChange={(e) => setForm({ ...form, opening_stock_qty: e.target.value })} />
              </Field>
              <Field label="Opening Stock Value">
                <Input type="text" inputMode="decimal" step="0.01" value={form.opening_stock_value}
                  onChange={(e) => setForm({ ...form, opening_stock_value: e.target.value })} />
              </Field>
            </div>
          </div>

          <div>
            <div className="label-overline mb-2 text-primary">Stock levels</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-muted/20 p-4 border border-border">
              <Field label="Reorder Level">
                <Input type="text" inputMode="decimal" step="0.01" value={form.reorder_level}
                  onChange={(e) => setForm({ ...form, reorder_level: e.target.value })} />
              </Field>
              <Field label="Reorder Qty">
                <Input type="text" inputMode="decimal" step="0.01" value={form.reorder_qty}
                  onChange={(e) => setForm({ ...form, reorder_qty: e.target.value })} />
              </Field>
              <Field label="Min Level">
                <Input type="text" inputMode="decimal" step="0.01" value={form.min_level}
                  onChange={(e) => setForm({ ...form, min_level: e.target.value })} />
              </Field>
              <Field label="Max Level">
                <Input type="text" inputMode="decimal" step="0.01" value={form.max_level}
                  onChange={(e) => setForm({ ...form, max_level: e.target.value })} />
              </Field>
            </div>
          </div>

          <div>
            <div className="label-overline mb-2 text-primary">Tracking</div>
            <div className="flex flex-wrap gap-6 bg-muted/20 p-4 border border-border">
              <Toggle label="Track Batch" checked={form.track_batch} testid="form-track-batch"
                onChange={(v) => setForm({ ...form, track_batch: v })} />
              <Toggle label="Track Serial" checked={form.track_serial} testid="form-track-serial"
                onChange={(v) => setForm({ ...form, track_serial: v })} />
              <Toggle label="Track Expiry" checked={form.track_expiry} testid="form-track-expiry"
                onChange={(v) => setForm({ ...form, track_expiry: v })} />
            </div>
            <p className="text-[11px] text-muted-foreground font-mono mt-2">
              When enabled, GRN and movement forms will require batch / serial / expiry capture for this item.
            </p>
          </div>
        </form>
      </Modal>
    </div>
  );
}
