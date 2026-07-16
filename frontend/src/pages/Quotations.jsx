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
import { CurrencyFields, downloadPdf, fmtMoney } from "@/lib/currency";
import SendEmailButton from "@/components/SendEmailButton";
import BulkDeleteBar, { SelectCheckbox } from "@/components/BulkDeleteBar";
import useBulkSelect from "@/hooks/useBulkSelect";
import { Plus, Pencil, Trash2, Download } from "lucide-react";

const blank = {
  customer_id: "",
  items: [],
  status: "DRAFT",
  valid_until: "",
  notes: "",
  currency: "INR",
  exchange_rate: 1,
};

export default function Quotations() {
  const [items, setItems] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);

  const sel = useBulkSelect(items);

  const load = async () => {
    const r = await api.get("/quotations");
    setItems(r.data);
  };

  const bulkDelete = async () => {
    const { ok, failed } = await sel.runDelete(
      (id) => api.delete(`/quotations/${id}`),
      { reload: load }
    );
    if (failed) toast.error(`Deleted ${ok}, failed ${failed}`);
    else toast.success(`Deleted ${ok} quotation${ok === 1 ? "" : "s"}`);
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
      items: form.items
        .filter((i) => (i._manual ? i.product_name?.trim() : i.product_id) && Number(i.quantity) > 0)
        .map(({ _manual, ...i }) => ({
          ...i,
          product_id: _manual ? null : (i.product_id || null),
          product_name: i.product_name || "",
          quantity: Number(i.quantity),
          unit_price: Number(i.unit_price),
          gst_rate: Number(i.gst_rate),
        })),
    };
    try {
      if (editingId) await api.put(`/quotations/${editingId}`, payload);
      else await api.post("/quotations", payload);
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const openNew = () => { setForm(blank); setEditingId(null); setOpen(true); };

  // Enter-as-Tab across the whole modal body (header fields + the
  // LineItemsEditor grid, which is marked data-grid-managed so its own Enter/
  // Arrow handling isn't swallowed here). Ctrl+Enter/Ctrl+S saves,
  // Ctrl+Shift+Enter/Ctrl+Shift+S saves and opens a fresh blank quotation.
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
    if (!window.confirm(`Delete ${item.quote_number}?`)) return;
    try {
      await api.delete(`/quotations/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  return (
    <div data-testid="quotations-page">
      <PageHeader
        eyebrow="Sales"
        title="Quotations"
        description="Price quotes sent to buyers"
        actions={
          <PrimaryButton
            icon={Plus}
            testid="new-quotation"
            onClick={openNew}
          >
            New quotation
          </PrimaryButton>
        }
      />

      {items.length === 0 ? (
        <EmptyState message="No quotations yet" />
      ) : (
        <div className="border border-border overflow-x-auto rounded-md">
          <table className="w-full text-sm">
            <thead className="bg-muted text-muted-foreground">
              <tr className="text-left label-overline border-b border-border">
                <th className="px-3 py-2.5 w-10">
                  <SelectCheckbox
                    label="Select all quotations"
                    checked={sel.allSelected}
                    indeterminate={sel.someSelected}
                    onChange={sel.toggleAll}
                  />
                </th>
                <th className="px-3 py-2.5">Quote#</th>
                <th className="px-3 py-2.5">Customer</th>
                <th className="px-3 py-2.5">Items</th>
                <th className="px-3 py-2.5 text-right">Total</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">Valid Till</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((q) => (
                <tr
                  key={q.id}
                  className={`border-b border-border hover:bg-muted/60 text-foreground ${sel.isSelected(q.id) ? "bg-primary/5" : ""}`}
                >
                  <td className="px-3 py-2.5">
                    <SelectCheckbox
                      label={`Select quotation ${q.quote_number}`}
                      checked={sel.isSelected(q.id)}
                      onChange={() => sel.toggle(q.id)}
                    />
                  </td>
                  <td className="px-3 py-2.5 font-mono text-primary font-bold">
                    {q.quote_number}
                  </td>
                  <td className="px-3 py-2.5 text-foreground">{q.customer_name}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{q.items?.length}</td>
                  <td className="px-3 py-2.5 text-right tabular text-foreground font-semibold">
                    {fmtMoney(q.total, q.currency)}
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusBadge status={q.status} />
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                    {q.valid_until || "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="inline-flex gap-1">
                      <button
                        onClick={() =>
                          downloadPdf(
                            `/quotations/${q.id}/pdf`,
                            `${q.quote_number}.pdf`
                          )
                        }
                        title="Download PDF"
                        data-testid={`pdf-${q.id}`}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground flex items-center justify-center bg-background"
                      >
                        <Download className="w-3.5 h-3.5" />
                      </button>
                      <SendEmailButton
                        docType="quotation"
                        docId={q.id}
                        docNumber={q.quote_number}
                        defaultRecipient={
                          customers.find((c) => c.id === q.customer_id)?.email || ""
                        }
                        defaultRecipientName={q.customer_name}
                      />
                      <button
                        onClick={() => {
                          setForm({
                            ...blank, ...q,
                            items: (q.items || []).map((i) => ({ ...i, _manual: !i.product_id })),
                          });
                          setEditingId(q.id);
                          setOpen(true);
                        }}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground flex items-center justify-center bg-background"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => onDelete(q)}
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
        title={editingId ? "Edit Quotation" : "New Quotation"}
        size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-quote">
              Save
            </PrimaryButton>
          </>
        }
      >
        <div ref={formRef} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="Customer" required>
              <select
                required
                value={form.customer_id}
                onChange={(e) =>
                  setForm({ ...form, customer_id: e.target.value })
                }
                data-testid="form-quote-customer"
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
                {["DRAFT", "SENT", "ACCEPTED", "REJECTED"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
            <Field label="Valid Until">
              <Input
                type="date"
                value={form.valid_until || ""}
                onChange={(e) =>
                  setForm({ ...form, valid_until: e.target.value })
                }
              />
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

      <BulkDeleteBar
        count={sel.count}
        deleting={sel.deleting}
        onClear={sel.clear}
        onDelete={bulkDelete}
        noun="quotation"
      />
    </div>
  );
}
