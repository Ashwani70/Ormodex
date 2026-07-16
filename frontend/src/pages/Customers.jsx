import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
  Field,
  Select,
  EmptyState,
  StatePill,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import BulkDeleteBar, { SelectCheckbox } from "@/components/BulkDeleteBar";
import useBulkSelect from "@/hooks/useBulkSelect";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { Plus, Pencil, Trash2, Mail, Phone, MessageCircle, Globe, Sparkles } from "lucide-react";

const blank = {
  name: "",
  company: "",
  email: "",
  phone: "",
  country: "India",
  address: "",
  gstin: "",
  registration_type: "Regular",
  pan_number: "",
  state_code: "",
  state: "",
  party_type: "CUSTOMER",
  registration_date: "",
  gst_status: "",
  pincode: "",
  customer_code: "",
  credit_limit: 0,
  payment_terms: "",
  pan_holder_name: "",
  pan_type: "",
  pan_status: "",
};

export default function Customers() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);
  const [validating, setValidating] = useState(false);

  const sel = useBulkSelect(items);

  const load = async () => {
    const r = await api.get("/customers");
    setItems(r.data);
  };
  useEffect(() => {
    load();
  }, []);

  const bulkDelete = async () => {
    const { ok, failed } = await sel.runDelete(
      (id) => api.delete(`/customers/${id}`),
      { reload: load }
    );
    if (failed) toast.error(`Deleted ${ok}, failed ${failed}`);
    else toast.success(`Deleted ${ok} ${ok === 1 ? "party" : "parties"}`);
  };

  // Auto-open detail modal when navigated here via ?detail=<id> (e.g. from Ctrl+K search).
  useEffect(() => {
    const detailId = searchParams.get("detail");
    if (!detailId || items.length === 0) return;
    const record = items.find((c) => c.id === detailId);
    if (record) {
      setForm({ ...blank, ...record });
      setEditingId(record.id);
      setOpen(true);
      const next = new URLSearchParams(searchParams);
      next.delete("detail");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, items]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-open the create form via ?new=1 — the global Alt+C shortcut
  // (useKeyboardShortcuts) navigates here with this flag so "Create Customer"
  // is a single keystroke from anywhere in the app.
  useEffect(() => {
    if (searchParams.get("new") !== "1") return;
    setForm(blank);
    setEditingId(null);
    setOpen(true);
    const next = new URLSearchParams(searchParams);
    next.delete("new");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Client-side GSTIN format check mirrors the backend regex so we never make a
  // network call for an obviously-malformed GSTIN.
  const GSTIN_RE = /^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;

  const handleFetchGstin = async () => {
    const gstin = (form.gstin || "").trim().toUpperCase();
    if (!GSTIN_RE.test(gstin)) {
      toast.warning("Please enter a valid 15-character GSTIN before fetching.");
      return;
    }
    setValidating(true);
    const toastId = toast.loading("Fetching GST details…");
    try {
      const res = await api.post("/customers/fetch-gstin", { gstin });
      const d = res.data || {};
      // Auto-fill the listed fields; values remain editable before saving.
      setForm((prev) => ({
        ...prev,
        gstin,
        name: d.company_name || prev.name,
        company: d.trade_name || d.company_name || prev.company,
        address: d.address || prev.address,
        state_code: d.state_code || prev.state_code,
        state: d.state || prev.state,
        pincode: d.pincode || prev.pincode,
        gst_status: d.status || prev.gst_status,
      }));
      if (d.notice) {
        toast.warning(d.notice, { id: toastId });
      } else if (d.cached) {
        toast.success("GST details loaded from cache. You can edit before saving.", { id: toastId });
      } else {
        toast.success("GST details fetched. You can edit before saving.", { id: toastId });
      }
    } catch (e) {
      toast.error(
        formatApiErrorDetail(e.response?.data?.detail) || "Failed to fetch GST details.",
        { id: toastId }
      );
    } finally {
      setValidating(false);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    try {
      if (editingId) await api.put(`/customers/${editingId}`, form);
      else await api.post("/customers", form);
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const openNew = () => { setForm(blank); setEditingId(null); setOpen(true); };

  // Enter-as-Tab across the whole form; Ctrl+Enter/Ctrl+S saves,
  // Ctrl+Shift+Enter/Ctrl+Shift+S saves and opens a fresh blank customer, Esc
  // cancels, first field auto-focuses when the modal opens.
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
    if (!window.confirm(`Delete ${item.company || item.name}?`)) return;
    try {
      await api.delete(`/customers/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const exportCsv = () => {
    const cols = ["name", "company", "email", "phone", "country", "address", "gstin", "party_type", "registration_type"];
    const lines = [cols.join(",")];
    items.forEach((c) => {
      lines.push(cols.map((k) => `"${(c[k] || "").toString().replace(/"/g, '""')}"`).join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `parties_customers_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div data-testid="customers-page">
      <PageHeader
        eyebrow="Sales & CRM"
        title="Customer & Party Database"
        description="Outsource partners, transporters, job workers, and client registry."
        actions={
          <>
            <SecondaryButton testid="export-customers" onClick={exportCsv}>
              Export CSV
            </SecondaryButton>
            <PrimaryButton
              testid="new-customer"
              icon={Plus}
              onClick={openNew}
            >
              New customer
            </PrimaryButton>
          </>
        }
      />

      {items.length === 0 ? (
        <EmptyState message="No customers yet" />
      ) : (
        <div className="border border-zinc-800 bg-zinc-950 overflow-x-auto rounded-md">
          <table className="w-full text-sm font-mono text-left">
            <thead className="bg-zinc-900 text-zinc-400">
              <tr className="border-b border-zinc-800 label-overline">
                <th className="px-3 py-2.5 w-10">
                  <SelectCheckbox
                    label="Select all parties"
                    checked={sel.allSelected}
                    indeterminate={sel.someSelected}
                    onChange={sel.toggleAll}
                  />
                </th>
                <th className="px-3 py-2.5">Company</th>
                <th className="px-3 py-2.5">Contact</th>
                <th className="px-3 py-2.5">Type</th>
                <th className="px-3 py-2.5">Reg Type</th>
                <th className="px-3 py-2.5">Country</th>
                <th className="px-3 py-2.5">Email</th>
                <th className="px-3 py-2.5">Phone</th>
                <th className="px-3 py-2.5">GSTIN</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr
                  key={c.id}
                  data-testid={`customer-row-${c.id}`}
                  className={`border-b border-zinc-900 hover:bg-zinc-900/60 text-zinc-100 ${sel.isSelected(c.id) ? "bg-zinc-900/40" : ""}`}
                >
                  <td className="px-3 py-2.5">
                    <SelectCheckbox
                      label={`Select ${c.company || c.name}`}
                      checked={sel.isSelected(c.id)}
                      onChange={() => sel.toggle(c.id)}
                    />
                  </td>
                  <td className="px-3 py-2.5 text-white font-semibold">
                    {c.company || "—"}
                  </td>
                  <td className="px-3 py-2.5 text-zinc-300">{c.name}</td>
                  <td className="px-3 py-2.5 text-xs text-zinc-400">
                    <span className="bg-zinc-800 text-zinc-300 px-1.5 py-0.5 rounded-sm text-[10px]">
                      {c.party_type || "CUSTOMER"}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-zinc-400">{c.registration_type || "Regular"}</td>
                  <td className="px-3 py-2.5 text-zinc-400">
                    <span className="inline-flex items-center gap-1">
                      <Globe className="w-3 h-3 text-yellow-400" />
                      {c.country}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    {c.email && (
                      <a
                        href={`mailto:${c.email}`}
                        className="inline-flex items-center gap-1 text-zinc-300 hover:text-yellow-400"
                      >
                        <Mail className="w-3 h-3" /> {c.email}
                      </a>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    {c.phone && (
                      <div className="flex items-center gap-2">
                        <a
                          href={`tel:${c.phone}`}
                          className="inline-flex items-center gap-1 text-zinc-300 hover:text-yellow-400"
                        >
                          <Phone className="w-3 h-3" /> {c.phone}
                        </a>
                        <a
                          href={`https://wa.me/${c.phone.replace(/\D/g, "")}`}
                          target="_blank"
                          rel="noreferrer"
                          className="text-zinc-300 hover:text-yellow-400"
                        >
                          <MessageCircle className="w-3.5 h-3.5" />
                        </a>
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-zinc-400">
                    {c.gstin || "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="inline-flex gap-1">
                      <button
                        onClick={() => {
                          setForm({ ...blank, ...c });
                          setEditingId(c.id);
                          setOpen(true);
                        }}
                        className="w-7 h-7 border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => onDelete(c)}
                        className="w-7 h-7 border border-zinc-800 hover:border-red-500 hover:text-red-400 text-zinc-400 flex items-center justify-center"
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
        title={editingId ? "Edit Customer/Party" : "New Customer/Party"}
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-customer">
              Save
            </PrimaryButton>
          </>
        }
      >
        <form ref={formRef} onSubmit={submit} className="space-y-6">
          {/* Section 1: Business Details */}
          <div>
            <div className="label-overline mb-2 text-yellow-400">Business details</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-zinc-900/20 p-4 border border-zinc-900">
              {editingId && (
                <Field label="Customer Code">
                  <Input value={form.customer_code || ""} disabled />
                </Field>
              )}
              <Field label="Company/Trade Name">
                <Input
                  value={form.company || ""}
                  onChange={(e) => setForm({ ...form, company: e.target.value })}
                  placeholder="Legal entity trade name"
                />
              </Field>
              <Field label="Contact Person" required>
                <Input
                  required
                  data-testid="form-cust-name"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </Field>
              <Field label="Party Type" required>
                <Select
                  value={form.party_type}
                  onChange={(e) => setForm({ ...form, party_type: e.target.value })}
                >
                  <option value="CUSTOMER">Customer</option>
                  <option value="TRANSPORTER">Transporter</option>
                  <option value="JOB_WORKER">Job Worker</option>
                </Select>
              </Field>
            </div>
          </div>

          {/* Section 2: Contact & Address */}
          <div>
            <div className="label-overline mb-2 text-yellow-400">Contact & Address</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-zinc-900/20 p-4 border border-zinc-900">
              <Field label="Email">
                <Input
                  type="email"
                  value={form.email || ""}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              </Field>
              <Field label="Phone">
                <Input
                  value={form.phone || ""}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                />
              </Field>
              <Field label="Country">
                <Input
                  value={form.country || ""}
                  onChange={(e) => setForm({ ...form, country: e.target.value })}
                />
              </Field>
              <div className="md:col-span-2">
                <Field label="Address">
                  <Input
                    value={form.address || ""}
                    onChange={(e) => setForm({ ...form, address: e.target.value })}
                  />
                </Field>
              </div>
            </div>
          </div>

          {/* Section 3: GST Verification */}
          <div>
            <div className="label-overline mb-2 text-yellow-400">GST Verification</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-zinc-900/20 p-4 border border-zinc-900">
              <Field label="GSTIN">
                <div className="flex gap-2">
                  <Input
                    value={form.gstin || ""}
                    onChange={(e) => setForm({ ...form, gstin: e.target.value })}
                    placeholder="15-digit GSTIN"
                  />
                  <button
                    type="button"
                    onClick={handleFetchGstin}
                    disabled={validating}
                    className="bg-primary text-black font-mono text-[10px] uppercase font-bold px-3 py-2 hover:bg-yellow-500 disabled:opacity-60 flex items-center gap-1 flex-shrink-0 whitespace-nowrap"
                  >
                    <Sparkles className="w-3 h-3" />
                    {validating ? "Fetching…" : "Fetch Details"}
                  </button>
                </div>
              </Field>
              <Field label="GST Registration Type">
                <Select
                  value={form.registration_type}
                  onChange={(e) => setForm({ ...form, registration_type: e.target.value })}
                >
                  <option value="Regular">Regular</option>
                  <option value="Composition">Composition</option>
                  <option value="Consumer">Consumer / Unregistered</option>
                </Select>
              </Field>
              <Field label="State Code">
                <Input
                  value={form.state_code || ""}
                  onChange={(e) => setForm({ ...form, state_code: e.target.value })}
                  placeholder="e.g. 27"
                />
              </Field>
              <Field label="State Name">
                <Input
                  value={form.state || ""}
                  onChange={(e) => setForm({ ...form, state: e.target.value })}
                  placeholder="e.g. Maharashtra"
                />
              </Field>
              <Field label="Pincode">
                <Input
                  value={form.pincode || ""}
                  onChange={(e) => setForm({ ...form, pincode: e.target.value })}
                  placeholder="e.g. 411018"
                />
              </Field>
              <Field label="GST Status">
                <div className="flex items-center gap-2">
                  <Input
                    value={form.gst_status || ""}
                    onChange={(e) => setForm({ ...form, gstin: form.gstin, gst_status: e.target.value })}
                    placeholder="e.g. ACTIVE"
                    className="flex-1"
                  />
                  {form.gst_status && (
                    <StatePill value={form.gst_status} className="flex-shrink-0" />
                  )}
                </div>
              </Field>
              <Field label="Registration Date">
                <Input
                  value={form.registration_date || ""}
                  onChange={(e) => setForm({ ...form, registration_date: e.target.value })}
                  placeholder="e.g. 2020-04-01"
                />
              </Field>
            </div>
          </div>

          {/* Section 4: Commercial Rules */}
          <div>
            <div className="label-overline mb-2 text-yellow-400">Commercial settings</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-zinc-900/20 p-4 border border-zinc-900">
              <Field label="Credit Limit (INR)">
                <Input
                  type="text" inputMode="decimal"
                  value={form.credit_limit || 0}
                  onChange={(e) => setForm({ ...form, credit_limit: parseFloat(e.target.value) || 0 })}
                />
              </Field>
              <Field label="Payment Terms">
                <Input
                  value={form.payment_terms || ""}
                  onChange={(e) => setForm({ ...form, payment_terms: e.target.value })}
                  placeholder="e.g. Net 30, COD"
                />
              </Field>
            </div>
          </div>
        </form>
      </Modal>

      <BulkDeleteBar
        count={sel.count}
        deleting={sel.deleting}
        onClear={sel.clear}
        onDelete={bulkDelete}
        noun="party"
        nounPlural="parties"
      />
    </div>
  );
}
