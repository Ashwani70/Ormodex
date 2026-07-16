import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
  Textarea,
  Field,
  Select,
  EmptyState,
  StatePill,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";
import BulkDeleteBar, { SelectCheckbox } from "@/components/BulkDeleteBar";
import useBulkSelect from "@/hooks/useBulkSelect";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { Plus, Pencil, Trash2, Mail, Phone, Sparkles } from "lucide-react";

const blank = {
  name: "",
  company: "",
  email: "",
  phone: "",
  contact_person: "",
  mobile: "",
  billing_address: "",
  shipping_address: "",
  address: "",
  gstin: "",
  registration_type: "Regular",
  pan: "",
  pan_number: "",
  state_code: "",
  party_type: "SUPPLIER",
  registration_date: "",
  gst_status: "",
  vendor_code: "",
  vendor_rating: 0.0,
  payment_terms: "",
  payment_terms_days: 0,
  opening_balance: 0.0,
  pan_holder_name: "",
  pan_type: "",
  pan_status: "",
};

export default function Vendors() {
  const online = useOnline();
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);
  const [validating, setValidating] = useState(false);
  const [verifyingPan, setVerifyingPan] = useState(false);
  const load = async () => {
    const r = await api.get("/purchase/v2/vendors");
    // The vendors list endpoint can return either a bare array or a paginated
    // { items: [...] } shape — normalise so selection/render always get an array.
    setItems(Array.isArray(r.data) ? r.data : (r.data?.items || []));
  };
  useEffect(() => {
    load();
  }, []);

  const sel = useBulkSelect(items);

  const bulkDelete = async () => {
    if (!online) return toast.warning("You are offline — deleting is disabled.");
    const { ok, failed } = await sel.runDelete(
      (id) => api.delete(`/purchase/v2/vendors/${id}`),
      { reload: load }
    );
    if (failed) toast.error(`Deleted ${ok}, failed ${failed}`);
    else toast.success(`Deleted ${ok} ${ok === 1 ? "vendor" : "vendors"}`);
  };

  // Auto-open detail modal when navigated here via ?detail=<id> (e.g. from Ctrl+K search).
  useEffect(() => {
    const detailId = searchParams.get("detail");
    if (!detailId || items.length === 0) return;
    const record = items.find((v) => v.id === detailId);
    if (record) {
      setForm({ ...blank, ...record });
      setEditingId(record.id);
      setOpen(true);
      const next = new URLSearchParams(searchParams);
      next.delete("detail");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, items]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFetchGstin = async () => {
    if (!form.gstin || form.gstin.trim().length !== 15) {
      toast.warning("Please enter a valid 15-digit GSTIN.");
      return;
    }
    setValidating(true);
    try {
      const res = await api.post("/verifications/gst/validate", { gstin: form.gstin });
      if (res.data && res.data.is_valid) {
        setForm((prev) => ({
          ...prev,
          company: res.data.trade_name || res.data.legal_name || prev.company,
          name: res.data.legal_name || prev.name,
          address: res.data.address || prev.address,
          billing_address: res.data.address || prev.billing_address,
          pan: res.data.pan || prev.pan,
          pan_number: res.data.pan || prev.pan_number,
          state_code: res.data.state_code || prev.state_code,
          registration_type: res.data.taxpayer_type || prev.registration_type,
          registration_date: res.data.registration_date || prev.registration_date,
          gst_status: res.data.portal_status || prev.gst_status
        }));
        toast.success("GSTIN details autofilled and verified!");
      } else {
        toast.error(res.data?.error || "Invalid GSTIN format.");
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to query GSTIN validation.");
    } finally {
      setValidating(false);
    }
  };

  const handleVerifyPan = async () => {
    const rawPan = form.pan_number || form.pan || "";
    if (!rawPan || rawPan.trim().length !== 10) {
      toast.warning("Please enter a valid 10-character PAN.");
      return;
    }
    setVerifyingPan(true);
    try {
      const res = await api.post("/verifications/pan/validate", {
        pan: rawPan.toUpperCase(),
        link_party_id: editingId || null
      });
      if (res.data && res.data.is_valid) {
        setForm((prev) => ({
          ...prev,
          pan: rawPan.toUpperCase(),
          pan_number: rawPan.toUpperCase(),
          pan_holder_name: res.data.pan_holder_name || "",
          pan_type: res.data.pan_type || "",
          pan_status: res.data.pan_status || "",
        }));
        toast.success("PAN verified successfully!");
      } else {
        toast.error(res.data.error || "Invalid PAN.");
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to verify PAN.");
    } finally {
      setVerifyingPan(false);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    
    const payload = {
      ...form,
      payment_terms_days: parseInt(form.payment_terms_days) || 0,
      opening_balance: parseFloat(form.opening_balance) || 0,
      vendor_rating: parseFloat(form.vendor_rating) || 0.0,
      address: form.address || form.billing_address || "",
      billing_address: form.billing_address || form.address || "",
      pan: form.pan || form.pan_number || "",
      pan_number: form.pan_number || form.pan || ""
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

  const openNew = () => { setForm(blank); setEditingId(null); setOpen(true); };

  // Enter-as-Tab across the whole form; Ctrl+Enter/Ctrl+S saves,
  // Ctrl+Shift+Enter/Ctrl+Shift+S saves and opens a fresh blank vendor, Esc
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
      await api.delete(`/purchase/v2/vendors/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const copyBillingToShipping = () => {
    setForm(prev => ({
      ...prev,
      shipping_address: prev.billing_address
    }));
    toast.info("Billing address copied to shipping address");
  };

  return (
    <div data-testid="vendors-page">
      <PageHeader
        eyebrow="Purchase"
        title="Vendor Database"
        description="Vendors supplying raw materials, steel, tooling, and consumables."
        actions={
          <PrimaryButton
            testid="new-vendor"
            icon={Plus}
            disabled={!online}
            onClick={openNew}
          >
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
                <th className="px-3 py-2.5 w-10">
                  <SelectCheckbox
                    label="Select all vendors"
                    checked={sel.allSelected}
                    indeterminate={sel.someSelected}
                    onChange={sel.toggleAll}
                  />
                </th>
                <th className="px-3 py-2.5">Code</th>
                <th className="px-3 py-2.5">Company</th>
                <th className="px-3 py-2.5">Contact</th>
                <th className="px-3 py-2.5">Type</th>
                <th className="px-3 py-2.5">Reg Type</th>
                <th className="px-3 py-2.5">Email / Phone</th>
                <th className="px-3 py-2.5">GSTIN</th>
                <th className="px-3 py-2.5">State</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((v) => (
                <tr
                  key={v.id}
                  data-testid={`vendor-row-${v.id}`}
                  className={`border-b border-border hover:bg-muted/40 text-foreground ${sel.isSelected(v.id) ? "bg-primary/5" : ""}`}
                >
                  <td className="px-3 py-2.5">
                    <SelectCheckbox
                      label={`Select ${v.company || v.name}`}
                      checked={sel.isSelected(v.id)}
                      onChange={() => sel.toggle(v.id)}
                    />
                  </td>
                  <td className="px-3 py-2.5 text-muted-foreground text-xs">{v.vendor_code || "—"}</td>
                  <td className="px-3 py-2.5 text-foreground font-semibold">{v.company || "—"}</td>
                  <td className="px-3 py-2.5 text-foreground">{v.name}</td>
                  <td className="px-3 py-2.5 text-xs">
                    <span className="bg-muted text-muted-foreground px-1.5 py-0.5 rounded-sm text-[10px]">
                      {v.party_type || "SUPPLIER"}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-muted-foreground">{v.registration_type || "Regular"}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex flex-col gap-0.5 text-xs text-muted-foreground">
                      {v.email && (
                        <a href={`mailto:${v.email}`} className="inline-flex items-center gap-1 hover:text-primary">
                          <Mail className="w-3 h-3" /> {v.email}
                        </a>
                      )}
                      {v.phone && (
                        <a href={`tel:${v.phone}`} className="inline-flex items-center gap-1 hover:text-primary">
                          <Phone className="w-3 h-3" /> {v.phone}
                        </a>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">{v.gstin || "—"}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{v.state_code || "—"}</td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="inline-flex gap-1">
                      <button
                        onClick={() => {
                          setForm({ ...blank, ...v });
                          setEditingId(v.id);
                          setOpen(true);
                        }}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground inline-flex items-center justify-center"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => onDelete(v)}
                        className="w-7 h-7 border border-border hover:border-destructive hover:text-destructive text-muted-foreground inline-flex items-center justify-center"
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
        title={editingId ? "Edit Vendor" : "New Vendor"}
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-vendor" disabled={!online}>
              Save
            </PrimaryButton>
          </>
        }
      >
        <form ref={formRef} onSubmit={submit} className="space-y-6">
          {/* Section 1: Business Details */}
          <div>
            <div className="label-overline mb-2 text-primary font-bold">Business details</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-muted/20 p-4 border border-border rounded-md">
              {editingId && (
                <Field label="Vendor Code">
                  <Input value={form.vendor_code || ""} disabled />
                </Field>
              )}
              <Field label="Company Name">
                <Input
                  value={form.company || ""}
                  onChange={(e) => setForm({ ...form, company: e.target.value })}
                  placeholder="Legal entity company name"
                />
              </Field>
              <Field label="Contact Person" required>
                <Input
                  required
                  data-testid="form-vendor-name"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </Field>
              <Field label="Party Type" required>
                <Select
                  value={form.party_type}
                  onChange={(e) => setForm({ ...form, party_type: e.target.value })}
                >
                  <option value="SUPPLIER">Vendor</option>
                  <option value="TRANSPORTER">Transporter</option>
                  <option value="JOB_WORKER">Job Worker</option>
                </Select>
              </Field>
            </div>
          </div>

          {/* Section 2: Contact & Address */}
          <div>
            <div className="label-overline mb-2 text-primary font-bold">Contact & Address</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-muted/20 p-4 border border-border rounded-md">
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
              <Field label="Contact Person">
                <Input
                  value={form.contact_person || ""}
                  onChange={(e) => setForm({ ...form, contact_person: e.target.value })}
                />
              </Field>
              <Field label="Mobile Number">
                <Input
                  value={form.mobile || ""}
                  onChange={(e) => setForm({ ...form, mobile: e.target.value })}
                />
              </Field>
              <div className="md:col-span-2">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs font-semibold text-foreground">Billing Address</span>
                  <button
                    type="button"
                    onClick={copyBillingToShipping}
                    className="text-[10px] text-primary hover:underline font-mono"
                  >
                    Copy to Shipping
                  </button>
                </div>
                <Textarea
                  rows={2}
                  value={form.billing_address || form.address || ""}
                  onChange={(e) => setForm({ ...form, billing_address: e.target.value, address: e.target.value })}
                />
              </div>
              <div className="md:col-span-2">
                <Field label="Shipping Address">
                  <Textarea
                    rows={2}
                    value={form.shipping_address || ""}
                    onChange={(e) => setForm({ ...form, shipping_address: e.target.value })}
                  />
                </Field>
              </div>
            </div>
          </div>

          {/* Section 3: GST Verification */}
          <div>
            <div className="label-overline mb-2 text-primary font-bold">GST Verification</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-muted/20 p-4 border border-border rounded-md">
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
                    disabled={validating || !online}
                    className="bg-primary text-primary-foreground font-mono text-[10px] uppercase font-bold px-3 py-2 hover:bg-primary/95 flex items-center gap-1 flex-shrink-0 disabled:opacity-50"
                  >
                    <Sparkles className="w-3 h-3" />
                    {validating ? "..." : "AUTOFETCH"}
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
              <Field label="GST Status">
                <div className="flex items-center gap-2">
                  <Input
                    value={form.gst_status || ""}
                    onChange={(e) => setForm({ ...form, gst_status: e.target.value })}
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

          {/* Section 4: PAN Verification */}
          <div>
            <div className="label-overline mb-2 text-primary font-bold">PAN Verification</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-muted/20 p-4 border border-border rounded-md">
              <Field label="PAN Number">
                <div className="flex gap-2">
                  <Input
                    value={form.pan_number || form.pan || ""}
                    onChange={(e) => setForm({ ...form, pan_number: e.target.value, pan: e.target.value })}
                    placeholder="10-character PAN"
                  />
                  <button
                    type="button"
                    onClick={handleVerifyPan}
                    disabled={verifyingPan || !online}
                    className="bg-primary text-primary-foreground font-mono text-[10px] uppercase font-bold px-3 py-2 hover:bg-primary/95 flex items-center gap-1 flex-shrink-0 disabled:opacity-50"
                  >
                    <Sparkles className="w-3 h-3" />
                    {verifyingPan ? "..." : "VERIFY"}
                  </button>
                </div>
              </Field>
              <Field label="PAN Holder Name">
                <Input value={form.pan_holder_name || ""} disabled placeholder="Verified name" />
              </Field>
              <Field label="PAN Type">
                <Input value={form.pan_type || ""} disabled placeholder="Verified type" />
              </Field>
              <Field label="PAN Status">
                <div className="flex items-center h-10">
                  <StatePill value={form.pan_status} placeholder="UNVERIFIED" />
                </div>
              </Field>
            </div>
          </div>

          {/* Section 6: Commercial & Balance */}
          <div>
            <div className="label-overline mb-2 text-primary font-bold">Commercial & Balance</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-muted/20 p-4 border border-border rounded-md">
              <Field label="Opening Balance">
                <Input
                  type="text" inputMode="decimal"
                  step="0.01"
                  value={form.opening_balance}
                  onChange={(e) => setForm({ ...form, opening_balance: e.target.value })}
                />
              </Field>
              <Field label="Payment Terms (days)">
                <Input
                  type="text" inputMode="decimal"
                  value={form.payment_terms_days}
                  onChange={(e) => setForm({ ...form, payment_terms_days: e.target.value })}
                />
              </Field>
              <Field label="Payment Terms (text)">
                <Input
                  value={form.payment_terms || ""}
                  onChange={(e) => setForm({ ...form, payment_terms: e.target.value })}
                  placeholder="e.g. Net 30, COD"
                />
              </Field>
              <Field label="Vendor Rating (Out of 5.0)">
                <Input
                  type="text" inputMode="decimal"
                  step="0.1"
                  min="0"
                  max="5"
                  value={form.vendor_rating || 0}
                  onChange={(e) => setForm({ ...form, vendor_rating: parseFloat(e.target.value) || 0 })}
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
        noun="vendor"
        nounPlural="vendors"
      />
    </div>
  );
}
