import { useEffect, useRef, useState } from "react";
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
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { Plus, Pencil, Trash2, PackageCheck } from "lucide-react";

const blank = {
  supplier_id: "",
  items: [],
  status: "DRAFT",
  notes: "",
  expected_date: "",
};

export default function PurchaseOrders() {
  const [items, setItems] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [products, setProducts] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);
  
  // GRN states
  const [showGrnModal, setShowGrnModal] = useState(false);
  const [grnForm, setGrnForm] = useState({
    purchase_order_id: "",
    purchase_order_number: "",
    supplier_id: "",
    supplier_name: "",
    received_date: new Date().toISOString().split("T")[0],
    received_by: "",
    items: [],
    remarks: "",
  });

  const load = async () => {
    const r = await api.get("/purchase-orders");
    setItems(r.data);
  };
  useEffect(() => {
    load();
    api.get("/suppliers").then((r) => setVendors(r.data));
    api.get("/products").then((r) => setProducts(r.data));
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.supplier_id) return toast.error("Select a vendor");
    if (form.items.length === 0) return toast.error("Add at least one line item");
    const payload = {
      ...form,
      items: form.items.map((i) => ({
        ...i,
        quantity: Number(i.quantity),
        unit_price: Number(i.unit_price),
        gst_rate: Number(i.gst_rate || 0),
      })),
    };
    try {
      if (editingId) await api.put(`/purchase-orders/${editingId}`, payload);
      else await api.post("/purchase-orders", payload);
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const openNew = () => { setForm(blank); setEditingId(null); setOpen(true); };

  // Enter-as-Tab across the whole PO modal body — this is the page's primary
  // create action, so it also owns the Ctrl+N shortcut. The LineItemsEditor
  // grid inside is marked data-grid-managed so its own Enter/Arrow handling
  // isn't swallowed here.
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

  const onDelete = async (item) => {
    if (!window.confirm(`Delete ${item.po_number}?`)) return;
    try {
      await api.delete(`/purchase-orders/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const startGrn = (po) => {
    const grnItems = po.items.map(item => ({
      product_id: item.product_id,
      product_name: item.product_name,
      sku: item.sku || "",
      quantity_ordered: item.quantity,
      quantity_received: item.quantity,
      unit: item.unit || "Nos",
      unit_cost: item.unit_price,
    }));
    setGrnForm({
      purchase_order_id: po.id,
      purchase_order_number: po.po_number,
      supplier_id: po.supplier_id,
      supplier_name: po.supplier_name,
      received_date: new Date().toISOString().split("T")[0],
      received_by: "",
      items: grnItems,
      remarks: "",
    });
    setShowGrnModal(true);
  };

  const submitGrn = async (e) => {
    e.preventDefault();
    if (!grnForm.received_by) return toast.error("Enter receiver's name");
    try {
      await api.post("/grn", grnForm);
      toast.success("Goods received and GRN generated!");
      setShowGrnModal(false);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to submit GRN");
    }
  };

  // Secondary form (opened from a PO row action, not the page's primary
  // create action) — Enter-as-Tab + Ctrl+Enter/Ctrl+S save + Esc cancel, but
  // no Ctrl+N wiring here (that's owned by the PO form above).
  const grnFormRef = useRef(null);
  useEnterNavigation(grnFormRef, {
    enabled: showGrnModal,
    autoFocus: true,
    onSave: () => submitGrn(new Event("submit", { cancelable: true })),
    onCancel: () => setShowGrnModal(false),
  });

  return (
    <div data-testid="po-page">
      <PageHeader
        eyebrow="Purchase"
        title="Purchase Orders"
        description="Material indent and inward tracking"
        actions={
          <PrimaryButton
            icon={Plus}
            testid="new-po"
            onClick={openNew}
          >
            New PO
          </PrimaryButton>
        }
      />

      {items.length === 0 ? (
        <EmptyState message="No purchase orders yet" />
      ) : (
        <div className="border border-border overflow-x-auto rounded-md">
          <table className="w-full text-sm">
            <thead className="bg-muted text-muted-foreground">
              <tr className="text-left label-overline border-b border-border">
                <th className="px-3 py-2.5">PO#</th>
                <th className="px-3 py-2.5">Vendor</th>
                <th className="px-3 py-2.5">Items</th>
                <th className="px-3 py-2.5 text-right">Total</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">Expected</th>
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
                    {p.po_number}
                  </td>
                  <td className="px-3 py-2.5 text-foreground">{p.supplier_name}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{p.items?.length || 0}</td>
                  <td className="px-3 py-2.5 text-right tabular text-foreground font-semibold">
                    ₹{Number(p.total || 0).toLocaleString("en-IN")}
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusBadge status={p.status} />
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                    {p.expected_date || "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="inline-flex gap-1">
                      {p.status !== "RECEIVED" && (
                        <button
                          onClick={() => startGrn(p)}
                          title="Receive Goods (GRN)"
                          className="w-7 h-7 border border-border hover:border-green-500 hover:text-green-400 text-muted-foreground flex items-center justify-center bg-background"
                        >
                          <PackageCheck className="w-3.5 h-3.5" />
                        </button>
                      )}
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
        title={editingId ? "Edit PO" : "New Purchase Order"}
        size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-po">
              Save
            </PrimaryButton>
          </>
        }
      >
        <div ref={formRef} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="Vendor" required>
              <select
                required
                data-testid="form-po-supplier"
                value={form.supplier_id}
                onChange={(e) => setForm({ ...form, supplier_id: e.target.value })}
                className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
              >
                <option value="">— select —</option>
                {vendors.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.company || s.name}
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
                {["DRAFT", "SENT", "RECEIVED", "CANCELLED"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Field label="Expected Date">
              <Input
                type="date"
                value={form.expected_date || ""}
                onChange={(e) =>
                  setForm({ ...form, expected_date: e.target.value })
                }
              />
            </Field>
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
      {/* Goods Receipt Note (GRN) Modal */}
      <Modal
        open={showGrnModal}
        onClose={() => setShowGrnModal(false)}
        title={`Create Goods Receipt Note (GRN) for PO ${grnForm.purchase_order_number}`}
        size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setShowGrnModal(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={submitGrn}>
              Submit GRN & Update Stock
            </PrimaryButton>
          </>
        }
      >
        <form ref={grnFormRef} onSubmit={submitGrn} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Received Date" required>
              <Input type="date" required value={grnForm.received_date} onChange={e => setGrnForm(f => ({ ...f, received_date: e.target.value }))} />
            </Field>
            <Field label="Received By" required>
              <Input required placeholder="Receiver's name" value={grnForm.received_by} onChange={e => setGrnForm(f => ({ ...f, received_by: e.target.value }))} />
            </Field>
          </div>
          <Field label="Remarks / Condition of Goods">
            <Input placeholder="e.g. Received in good condition, no damage" value={grnForm.remarks || ""} onChange={e => setGrnForm(f => ({ ...f, remarks: e.target.value }))} />
          </Field>

          <div>
            <span className="label-overline block mb-2 text-muted-foreground">Review Item Quantities</span>
            <div className="border border-border rounded max-h-60 overflow-y-auto">
              <table className="w-full text-xs text-left bg-card">
                <thead className="bg-muted sticky top-0 label-overline border-b border-border text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Product Name</th>
                    <th className="px-3 py-2">SKU</th>
                    <th className="px-3 py-2 text-right">Qty Ordered</th>
                    <th className="px-3 py-2 text-right">Qty Received</th>
                    <th className="px-3 py-2 text-left">Unit</th>
                  </tr>
                </thead>
                <tbody>
                  {grnForm.items?.map((item, idx) => (
                    <tr key={item.product_id} className="border-b border-border text-foreground">
                      <td className="px-3 py-2 text-foreground font-bold">{item.product_name}</td>
                      <td className="px-3 py-2 font-mono text-muted-foreground">{item.sku}</td>
                      <td className="px-3 py-2 text-right tabular text-muted-foreground">{item.quantity_ordered}</td>
                      <td className="px-3 py-2 text-right pr-2">
                        <input
                          type="text" inputMode="decimal"
                          step="0.001"
                          value={item.quantity_received}
                          onChange={e => {
                            const val = parseFloat(e.target.value) || 0;
                            setGrnForm(f => {
                              const newItems = [...f.items];
                              newItems[idx] = { ...newItems[idx], quantity_received: val };
                              return { ...f, items: newItems };
                            });
                          }}
                          className="w-20 bg-background border border-input text-right text-xs px-2 py-1 text-foreground focus:outline-none focus:border-primary font-bold transition-colors"
                        />
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">{item.unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </form>
      </Modal>
    </div>
  );
}
