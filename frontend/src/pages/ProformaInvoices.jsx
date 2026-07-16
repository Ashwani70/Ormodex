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
  NumericInput,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import { downloadPdf, fmtMoney } from "@/lib/currency";
import SendEmailButton from "@/components/SendEmailButton";
import BulkDeleteBar, { SelectCheckbox } from "@/components/BulkDeleteBar";
import useBulkSelect from "@/hooks/useBulkSelect";
import {
  Plus,
  Pencil,
  Trash2,
  Download,
  Globe,
  Ship,
} from "lucide-react";

const CURRENCIES = ["USD", "EUR", "GBP", "AED", "INR"];
const INCOTERMS = ["FOB", "CIF", "CFR", "EXW", "CIP", "DAP", "DDP"];
const PI_STATUS = ["DRAFT", "SENT", "ACCEPTED", "CONVERTED", "CANCELLED"];

const blankItem = {
  container_spec: "",
  description: "",
  weight_per_unit: "",
  quantity: "",
  unit_price: "",
};

const blank = {
  pi_number: "",
  date: new Date().toISOString().slice(0, 10),
  validity_days: 30,
  buyer_name: "",
  buyer_address: "",
  buyer_country: "",
  buyer_contact_person: "",
  buyer_email: "",
  buyer_phone: "",
  exporter_name: "GRAVITYONE ERP",
  exporter_address: "Pune, Maharashtra, India",
  exporter_gstin: "27AABCG1234F1Z5",
  exporter_iec: "",
  bank_name: "",
  bank_account_no: "",
  bank_swift: "",
  bank_iban: "",
  bank_branch: "",
  items: [{ ...blankItem }],
  currency: "USD",
  incoterms: "CIF",
  country_of_origin: "India",
  port_of_loading: "Mundra Port, India",
  port_of_discharge: "",
  final_destination: "",
  payment_terms:
    "30% advance payment and balance 70% against the scan copy of the bill of lading.",
  delivery_time:
    "Within 45-60 days after receiving confirmation on the same Proforma and advance payment.",
  quantity_tolerance: "Min and Max 5% tolerance in weights & quantities.",
  packing_notes: "Bundle packing with 120 mm min height from floor; 50 pcs per bundle.",
  freight_clause: "",
  special_notes: "",
  status: "DRAFT",
};

export default function ProformaInvoices() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);
  const [company, setCompany] = useState(null);

  const sel = useBulkSelect(items);

  const load = async () => {
    const r = await api.get("/proforma-invoices");
    setItems(r.data);
  };

  const bulkDelete = async () => {
    const { ok, failed } = await sel.runDelete(
      (id) => api.delete(`/proforma-invoices/${id}`),
      { reload: load }
    );
    if (failed) toast.error(`Deleted ${ok}, failed ${failed}`);
    else toast.success(`Deleted ${ok} proforma invoice${ok === 1 ? "" : "s"}`);
  };
  const loadCompany = async () => {
    try {
      const r = await api.get("/company/active");
      setCompany(r.data);
    } catch (err) {
      console.error("Failed to fetch active company", err);
    }
  };
  useEffect(() => {
    load();
    loadCompany();
  }, []);

  const startNew = () => {
    setForm({
      ...blank,
      exporter_name: company?.name || "GRAVITYONE ERP",
      exporter_address: company?.address || "Pune, Maharashtra, India",
      exporter_gstin: company?.gstin || "27AABCG1234F1Z5",
      bank_name: company?.bank_name || "",
      bank_account_no: company?.bank_account_no || "",
      bank_branch: company?.bank_branch || "",
    });
    setEditingId(null);
    setOpen(true);
  };
  const startEdit = (it) => {
    setForm({
      ...blank, ...it,
      items: (it.items?.length ? it.items : [{ ...blankItem }]).map((i) => ({
        ...i,
        weight_per_unit: i.weight_per_unit != null && i.weight_per_unit !== 0 ? i.weight_per_unit : "",
        quantity: i.quantity != null && i.quantity !== 0 ? i.quantity : "",
        unit_price: i.unit_price != null && i.unit_price !== 0 ? i.unit_price : "",
      })),
    });
    setEditingId(it.id);
    setOpen(true);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.buyer_name) return toast.error("Buyer name is required");
    if (!form.items.length) return toast.error("Add at least one line item");
    const payload = {
      ...form,
      items: form.items.map((i) => ({
        ...i,
        weight_per_unit: Number(i.weight_per_unit || 0),
        quantity: Number(i.quantity || 0),
        unit_price: Number(i.unit_price || 0),
      })),
      validity_days: Number(form.validity_days || 30),
    };
    try {
      if (editingId) await api.put(`/proforma-invoices/${editingId}`, payload);
      else await api.post("/proforma-invoices", payload);
      toast.success("Proforma Invoice saved");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const onDelete = async (it) => {
    if (!window.confirm(`Delete ${it.pi_number}?`)) return;
    try {
      await api.delete(`/proforma-invoices/${it.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const updateItem = (idx, patch) => {
    const list = [...form.items];
    list[idx] = { ...list[idx], ...patch };
    setForm({ ...form, items: list });
  };
  const addItem = () => setForm({ ...form, items: [...form.items, { ...blankItem }] });
  const removeItem = (idx) =>
    setForm({ ...form, items: form.items.filter((_, i) => i !== idx) });

  // running totals for the modal
  let formTotalAmount = 0;
  let formTotalWeight = 0;
  form.items.forEach((i) => {
    const q = Number(i.quantity || 0);
    formTotalAmount += q * Number(i.unit_price || 0);
    formTotalWeight += q * Number(i.weight_per_unit || 0);
  });

  return (
    <div data-testid="pi-page">
      <PageHeader
        eyebrow="Export Sales"
        title="Proforma Invoices"
        description="Export-grade Proforma Invoices for international buyers — Incoterms, ports, multi-currency."
        actions={
          <PrimaryButton testid="new-pi" icon={Plus} onClick={startNew}>
            New Proforma
          </PrimaryButton>
        }
      />

      {items.length === 0 ? (
        <EmptyState
          message="No proforma invoices yet"
          action={
            <PrimaryButton onClick={startNew} icon={Plus}>
              Create your first PI
            </PrimaryButton>
          }
        />
      ) : (
        <div className="border border-border overflow-x-auto rounded-md">
          <table className="w-full text-sm">
            <thead className="bg-muted text-muted-foreground">
              <tr className="text-left label-overline border-b border-border">
                <th className="px-3 py-2.5 w-10">
                  <SelectCheckbox
                    label="Select all proforma invoices"
                    checked={sel.allSelected}
                    indeterminate={sel.someSelected}
                    onChange={sel.toggleAll}
                  />
                </th>
                <th className="px-3 py-2.5">PI No.</th>
                <th className="px-3 py-2.5">Buyer</th>
                <th className="px-3 py-2.5">Country</th>
                <th className="px-3 py-2.5">Inco</th>
                <th className="px-3 py-2.5">Port of Discharge</th>
                <th className="px-3 py-2.5 text-right">Net Wt (kg)</th>
                <th className="px-3 py-2.5 text-right">Total</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr
                  key={p.id}
                  data-testid={`pi-row-${p.id}`}
                  className={`border-b border-border hover:bg-muted/60 text-foreground ${sel.isSelected(p.id) ? "bg-primary/5" : ""}`}
                >
                  <td className="px-3 py-2.5">
                    <SelectCheckbox
                      label={`Select proforma invoice ${p.pi_number}`}
                      checked={sel.isSelected(p.id)}
                      onChange={() => sel.toggle(p.id)}
                    />
                  </td>
                  <td className="px-3 py-2.5 font-mono text-primary font-bold">
                    {p.pi_number}
                  </td>
                  <td className="px-3 py-2.5 text-foreground">{p.buyer_name}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">
                    {p.buyer_country ? (
                      <span className="inline-flex items-center gap-1">
                        <Globe className="w-3 h-3 text-primary" />
                        {p.buyer_country}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-foreground">
                    {p.incoterms}
                  </td>
                  <td className="px-3 py-2.5 text-muted-foreground text-xs">
                    {p.port_of_discharge ? (
                      <span className="inline-flex items-center gap-1">
                        <Ship className="w-3 h-3 text-primary" />
                        {p.port_of_discharge}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular text-foreground">
                    {Number(p.total_net_weight || 0).toLocaleString("en-IN")}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular text-primary font-semibold">
                    {fmtMoney(p.total_amount, p.currency)}
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusBadge status={p.status} />
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                    {p.date || new Date(p.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="inline-flex gap-1">
                      <button
                        onClick={() =>
                          downloadPdf(
                            `/proforma-invoices/${p.id}/pdf`,
                            `${p.pi_number}.pdf`
                          )
                        }
                        title="Download PDF"
                        data-testid={`pi-pdf-${p.id}`}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground flex items-center justify-center bg-background"
                      >
                        <Download className="w-3.5 h-3.5" />
                      </button>
                      <SendEmailButton
                        docType="proforma"
                        docId={p.id}
                        docNumber={p.pi_number}
                        defaultRecipient={p.buyer_email || ""}
                        defaultRecipientName={p.buyer_contact_person || p.buyer_name}
                        testid={`pi-email-${p.id}`}
                      />
                      <button
                        onClick={() => startEdit(p)}
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
        title={editingId ? "Edit Proforma Invoice" : "New Proforma Invoice"}
        size="xl"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-pi">
              Save Proforma
            </PrimaryButton>
          </>
        }
      >
        <div className="space-y-5">
          {/* Buyer + dates */}
          <section>
            <h4 className="label-overline mb-2 flex items-center gap-2">
              <span className="inline-block w-2 h-3 bg-primary" />
              Buyer / Consignee
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Field label="Buyer Name" required>
                <Input
                  required
                  data-testid="pi-buyer-name"
                  value={form.buyer_name}
                  onChange={(e) => setForm({ ...form, buyer_name: e.target.value })}
                />
              </Field>
              <Field label="Country">
                <Input
                  value={form.buyer_country}
                  onChange={(e) =>
                    setForm({ ...form, buyer_country: e.target.value })
                  }
                />
              </Field>
              <Field label="Contact Person">
                <Input
                  value={form.buyer_contact_person}
                  onChange={(e) =>
                    setForm({ ...form, buyer_contact_person: e.target.value })
                  }
                />
              </Field>
              <Field label="Email">
                <Input
                  type="email"
                  value={form.buyer_email}
                  onChange={(e) =>
                    setForm({ ...form, buyer_email: e.target.value })
                  }
                />
              </Field>
              <Field label="Phone">
                <Input
                  value={form.buyer_phone}
                  onChange={(e) =>
                    setForm({ ...form, buyer_phone: e.target.value })
                  }
                />
              </Field>
              <Field label="PI Date">
                <Input
                  type="date"
                  value={form.date}
                  onChange={(e) => setForm({ ...form, date: e.target.value })}
                />
              </Field>
              <div className="md:col-span-3">
                <Field label="Buyer Address (full, multi-line)">
                  <textarea
                    rows={2}
                    value={form.buyer_address}
                    onChange={(e) =>
                      setForm({ ...form, buyer_address: e.target.value })
                    }
                    className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
                  />
                </Field>
              </div>
            </div>
          </section>

          {/* Logistics */}
          <section>
            <h4 className="label-overline mb-2 flex items-center gap-2">
              <span className="inline-block w-2 h-3 bg-primary" />
              Logistics &amp; Currency
            </h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Field label="Currency">
                <select
                  value={form.currency}
                  onChange={(e) =>
                    setForm({ ...form, currency: e.target.value })
                  }
                  data-testid="pi-currency"
                  className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
                >
                  {CURRENCIES.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </Field>
              <Field label="Incoterms">
                <select
                  value={form.incoterms}
                  onChange={(e) =>
                    setForm({ ...form, incoterms: e.target.value })
                  }
                  className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
                >
                  {INCOTERMS.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </Field>
              <Field label="Country of Origin">
                <Input
                  value={form.country_of_origin}
                  onChange={(e) =>
                    setForm({ ...form, country_of_origin: e.target.value })
                  }
                />
              </Field>
              <Field label="Status">
                <select
                  value={form.status}
                  onChange={(e) => setForm({ ...form, status: e.target.value })}
                  className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
                >
                  {PI_STATUS.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </Field>
              <Field label="Port of Loading">
                <Input
                  value={form.port_of_loading}
                  onChange={(e) =>
                    setForm({ ...form, port_of_loading: e.target.value })
                  }
                />
              </Field>
              <Field label="Port of Discharge">
                <Input
                  value={form.port_of_discharge}
                  onChange={(e) =>
                    setForm({ ...form, port_of_discharge: e.target.value })
                  }
                />
              </Field>
              <Field label="Final Destination">
                <Input
                  value={form.final_destination}
                  onChange={(e) =>
                    setForm({ ...form, final_destination: e.target.value })
                  }
                />
              </Field>
              <Field label="PI Number (auto if blank)">
                <Input
                  value={form.pi_number}
                  onChange={(e) =>
                    setForm({ ...form, pi_number: e.target.value })
                  }
                />
              </Field>
            </div>
          </section>

          {/* Items */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <h4 className="label-overline flex items-center gap-2">
                <span className="inline-block w-2 h-3 bg-primary" />
                Line Items
              </h4>
              <button
                type="button"
                data-testid="pi-add-item"
                onClick={addItem}
                className="inline-flex items-center gap-1 text-xs font-mono uppercase tracking-wider text-primary hover:opacity-80 transition-opacity"
              >
                <Plus className="w-3.5 h-3.5" /> Add line
              </button>
            </div>
            <div className="space-y-2">
              {form.items.map((it, idx) => {
                const lineTotal =
                  Number(it.quantity || 0) * Number(it.unit_price || 0);
                const lineWeight =
                  Number(it.quantity || 0) * Number(it.weight_per_unit || 0);
                return (
                  <div
                    key={idx}
                    className="border border-border bg-card p-3"
                  >
                    <div className="grid grid-cols-1 md:grid-cols-12 gap-2">
                      <Input
                        placeholder="Container (e.g. 1x40 ft hc)"
                        value={it.container_spec || ""}
                        onChange={(e) =>
                          updateItem(idx, { container_spec: e.target.value })
                        }
                        className="md:col-span-2"
                      />
                      <textarea
                        placeholder="Full product description (specs, packing, etc.)"
                        rows={2}
                        value={it.description}
                        onChange={(e) =>
                          updateItem(idx, { description: e.target.value })
                        }
                        className="md:col-span-6 bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
                      />
                      <NumericInput
                        value={it.weight_per_unit}
                        onChange={(v) => updateItem(idx, { weight_per_unit: v })}
                        placeholder="Wt/unit"
                        className="md:col-span-1"
                      />
                      <NumericInput
                        value={it.quantity}
                        onChange={(v) => updateItem(idx, { quantity: v })}
                        placeholder="Qty"
                        decimals={0}
                        className="md:col-span-1"
                      />
                      <NumericInput
                        value={it.unit_price}
                        onChange={(v) => updateItem(idx, { unit_price: v })}
                        placeholder="Unit price"
                        className="md:col-span-1"
                      />
                      <button
                        type="button"
                        onClick={() => removeItem(idx)}
                        className="md:col-span-1 text-muted-foreground hover:text-red-400 self-start mt-1"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    <div className="flex items-center justify-end gap-4 mt-2 text-xs font-mono">
                      <span className="text-muted-foreground">
                        Net weight:{" "}
                        <span className="text-foreground tabular">
                          {lineWeight.toLocaleString("en-IN")} kg
                        </span>
                      </span>
                      <span className="text-muted-foreground">
                        Line total:{" "}
                        <span className="text-primary tabular font-semibold">
                          {fmtMoney(lineTotal, form.currency)}
                        </span>
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="mt-3 flex items-center justify-end gap-6 border-t border-border pt-3 text-sm">
              <span className="label-overline">
                Net Weight:{" "}
                <span className="text-foreground tabular ml-2">
                  {formTotalWeight.toLocaleString("en-IN")} kg
                </span>
              </span>
              <span className="label-overline">
                {form.incoterms} Total:{" "}
                <span className="text-primary font-display font-bold text-lg ml-2">
                  {fmtMoney(formTotalAmount, form.currency)}
                </span>
              </span>
            </div>
          </section>

          {/* Bank */}
          <section>
            <h4 className="label-overline mb-2 flex items-center gap-2">
              <span className="inline-block w-2 h-3 bg-primary" />
              Bank Details (optional)
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Field label="Bank Name">
                <Input
                  value={form.bank_name}
                  onChange={(e) =>
                    setForm({ ...form, bank_name: e.target.value })
                  }
                />
              </Field>
              <Field label="Branch">
                <Input
                  value={form.bank_branch}
                  onChange={(e) =>
                    setForm({ ...form, bank_branch: e.target.value })
                  }
                />
              </Field>
              <Field label="A/C No.">
                <Input
                  value={form.bank_account_no}
                  onChange={(e) =>
                    setForm({ ...form, bank_account_no: e.target.value })
                  }
                />
              </Field>
              <Field label="SWIFT Code">
                <Input
                  value={form.bank_swift}
                  onChange={(e) =>
                    setForm({ ...form, bank_swift: e.target.value })
                  }
                />
              </Field>
              <Field label="IBAN">
                <Input
                  value={form.bank_iban}
                  onChange={(e) =>
                    setForm({ ...form, bank_iban: e.target.value })
                  }
                />
              </Field>
              <Field label="IEC (Importer Exporter Code)">
                <Input
                  value={form.exporter_iec}
                  onChange={(e) =>
                    setForm({ ...form, exporter_iec: e.target.value })
                  }
                />
              </Field>
            </div>
          </section>

          {/* Terms */}
          <section>
            <h4 className="label-overline mb-2 flex items-center gap-2">
              <span className="inline-block w-2 h-3 bg-primary" />
              Terms &amp; Conditions
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Payment Terms">
                <textarea
                  rows={2}
                  value={form.payment_terms}
                  onChange={(e) =>
                    setForm({ ...form, payment_terms: e.target.value })
                  }
                  className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
                />
              </Field>
              <Field label="Delivery Time">
                <textarea
                  rows={2}
                  value={form.delivery_time}
                  onChange={(e) =>
                    setForm({ ...form, delivery_time: e.target.value })
                  }
                  className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
                />
              </Field>
              <Field label="Quantity Tolerance">
                <Input
                  value={form.quantity_tolerance}
                  onChange={(e) =>
                    setForm({ ...form, quantity_tolerance: e.target.value })
                  }
                />
              </Field>
              <Field label="Packing Notes">
                <Input
                  value={form.packing_notes}
                  onChange={(e) =>
                    setForm({ ...form, packing_notes: e.target.value })
                  }
                />
              </Field>
              <Field label="Freight Clause">
                <textarea
                  rows={2}
                  value={form.freight_clause}
                  onChange={(e) =>
                    setForm({ ...form, freight_clause: e.target.value })
                  }
                  className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
                />
              </Field>
              <Field label="Special Notes">
                <textarea
                  rows={2}
                  value={form.special_notes}
                  onChange={(e) =>
                    setForm({ ...form, special_notes: e.target.value })
                  }
                  className="w-full bg-background border border-input text-foreground text-sm px-3 py-2 focus:border-primary focus:outline-none transition-colors"
                />
              </Field>
            </div>
          </section>
        </div>
      </Modal>

      <BulkDeleteBar
        count={sel.count}
        deleting={sel.deleting}
        onClear={sel.clear}
        onDelete={bulkDelete}
        noun="proforma invoice"
      />
    </div>
  );
}
