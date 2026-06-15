import { useEffect, useState } from "react";
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
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import { Plus, Pencil, Trash2, Mail, Phone, Sparkles } from "lucide-react";

const blank = {
  name: "",
  company: "",
  email: "",
  phone: "",
  address: "",
  gstin: "",
  registration_type: "Regular",
  pan_number: "",
  state_code: "",
  party_type: "SUPPLIER",
  registration_date: "",
  gst_status: "",
  vendor_code: "",
  vendor_rating: 0.0,
  payment_terms: "",
  pan_holder_name: "",
  pan_type: "",
  pan_status: "",
  aadhaar_number: "",
  aadhaar_holder_name: "",
  aadhaar_status: ""
};

export default function Suppliers() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);
  const [validating, setValidating] = useState(false);
  const [verifyingPan, setVerifyingPan] = useState(false);
  const [verifyingAadhaar, setVerifyingAadhaar] = useState(false);

  const load = async () => {
    const r = await api.get("/suppliers");
    setItems(r.data);
  };
  useEffect(() => {
    load();
  }, []);

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
          pan_number: res.data.pan || prev.pan_number,
          state_code: res.data.state_code || prev.state_code,
          registration_type: res.data.taxpayer_type || prev.registration_type,
          registration_date: res.data.registration_date || prev.registration_date,
          gst_status: res.data.portal_status || prev.gst_status
        }));
        toast.success("GSTIN details autofilled and verified!");
      } else {
        toast.error("Invalid GSTIN format.");
      }
    } catch (e) {
      toast.error("Failed to query GSTIN validation.");
    } finally {
      setValidating(false);
    }
  };

  const handleVerifyPan = async () => {
    if (!form.pan_number || form.pan_number.trim().length !== 10) {
      toast.warning("Please enter a valid 10-character PAN.");
      return;
    }
    setVerifyingPan(true);
    try {
      const res = await api.post("/verifications/pan/validate", {
        pan: form.pan_number,
        link_party_id: editingId || null
      });
      if (res.data && res.data.is_valid) {
        setForm((prev) => ({
          ...prev,
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

  const handleVerifyAadhaar = async () => {
    const rawAadhaar = form.aadhaar_number?.replace(/\s/g, "") || "";
    const isMasked = /^XXXX-XXXX-[0-9]{4}$/.test(form.aadhaar_number);
    if (!isMasked && (rawAadhaar.length !== 12 || isNaN(rawAadhaar))) {
      toast.warning("Please enter a valid 12-digit Aadhaar number.");
      return;
    }
    if (isMasked) {
      toast.info("Aadhaar is already verified and masked.");
      return;
    }
    setVerifyingAadhaar(true);
    try {
      const res = await api.post("/verifications/aadhaar/validate", {
        aadhaar: rawAadhaar,
        link_party_id: editingId || null
      });
      if (res.data && res.data.is_valid) {
        setForm((prev) => ({
          ...prev,
          aadhaar_holder_name: res.data.aadhaar_holder_name || "",
          aadhaar_status: res.data.aadhaar_status || "",
          aadhaar_number: `XXXX-XXXX-${rawAadhaar.slice(-4)}`
        }));
        toast.success("Aadhaar verified successfully!");
      } else {
        toast.error(res.data.error || "Invalid Aadhaar.");
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to verify Aadhaar.");
    } finally {
      setVerifyingAadhaar(false);
    }
  };


  const submit = async (e) => {
    e.preventDefault();
    try {
      if (editingId) await api.put(`/suppliers/${editingId}`, form);
      else await api.post("/suppliers", form);
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const onDelete = async (item) => {
    if (!window.confirm(`Delete ${item.company || item.name}?`)) return;
    try {
      await api.delete(`/suppliers/${item.id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  return (
    <div data-testid="suppliers-page">
      <PageHeader
        eyebrow="Purchase"
        title="Supplier Database"
        description="Vendors supplying raw materials, steel, tooling, and consumables."
        actions={
          <PrimaryButton
            testid="new-supplier"
            icon={Plus}
            onClick={() => {
              setForm(blank);
              setEditingId(null);
              setOpen(true);
            }}
          >
            New supplier
          </PrimaryButton>
        }
      />

      {items.length === 0 ? (
        <EmptyState message="No suppliers yet" />
      ) : (
        <div className="border border-zinc-800 bg-zinc-950 overflow-x-auto rounded-md">
          <table className="w-full text-sm font-mono text-left">
            <thead className="bg-zinc-900 text-zinc-400">
              <tr className="border-b border-zinc-800 label-overline">
                <th className="px-3 py-2.5">Company</th>
                <th className="px-3 py-2.5">Contact</th>
                <th className="px-3 py-2.5">Type</th>
                <th className="px-3 py-2.5">Reg Type</th>
                <th className="px-3 py-2.5">Email</th>
                <th className="px-3 py-2.5">Phone</th>
                <th className="px-3 py-2.5">GSTIN</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr
                  key={s.id}
                  data-testid={`supplier-row-${s.id}`}
                  className="border-b border-zinc-900 hover:bg-zinc-900/60 text-zinc-100"
                >
                  <td className="px-3 py-2.5 text-white font-semibold">{s.company || "—"}</td>
                  <td className="px-3 py-2.5 text-zinc-300">{s.name}</td>
                  <td className="px-3 py-2.5 text-xs">
                    <span className="bg-zinc-800 text-zinc-300 px-1.5 py-0.5 rounded-sm text-[10px]">
                      {s.party_type || "SUPPLIER"}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-zinc-400">{s.registration_type || "Regular"}</td>
                  <td className="px-3 py-2.5">
                    {s.email && (
                      <a
                        href={`mailto:${s.email}`}
                        className="inline-flex items-center gap-1 text-zinc-300 hover:text-yellow-400"
                      >
                        <Mail className="w-3 h-3" /> {s.email}
                      </a>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    {s.phone && (
                      <a
                        href={`tel:${s.phone}`}
                        className="inline-flex items-center gap-1 text-zinc-300 hover:text-yellow-400"
                      >
                        <Phone className="w-3 h-3" /> {s.phone}
                      </a>
                    )}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-zinc-400">
                    {s.gstin || "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="inline-flex gap-1">
                      <button
                        onClick={() => {
                          setForm({ ...blank, ...s });
                          setEditingId(s.id);
                          setOpen(true);
                        }}
                        className="w-7 h-7 border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => onDelete(s)}
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
        title={editingId ? "Edit Supplier" : "New Supplier"}
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-supplier">
              Save
            </PrimaryButton>
          </>
        }
      >
        <form onSubmit={submit} className="space-y-6">
          {/* Section 1: Business Details */}
          <div>
            <div className="label-overline mb-2 text-yellow-400">Business details</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-zinc-900/20 p-4 border border-zinc-900">
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
                  data-testid="form-supp-name"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </Field>
              <Field label="Party Type" required>
                <Select
                  value={form.party_type}
                  onChange={(e) => setForm({ ...form, party_type: e.target.value })}
                >
                  <option value="SUPPLIER">Supplier</option>
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
                    className="bg-primary text-black font-mono text-[10px] uppercase font-bold px-3 py-2 hover:bg-yellow-500 flex items-center gap-1 flex-shrink-0"
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
                    onChange={(e) => setForm({ ...form, gstin: form.gstin, gst_status: e.target.value })}
                    placeholder="e.g. ACTIVE"
                    className="flex-1"
                  />
                  {form.gst_status && (
                    <span className={`text-[10px] font-mono font-bold px-2 py-1 border flex-shrink-0 ${
                      form.gst_status === "ACTIVE"
                        ? "bg-green-950 text-green-400 border-green-800"
                        : "bg-red-950 text-red-400 border-red-800"
                    }`}>
                      {form.gst_status}
                    </span>
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
            <div className="label-overline mb-2 text-yellow-400">PAN Verification</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-zinc-900/20 p-4 border border-zinc-900">
              <Field label="PAN Number">
                <div className="flex gap-2">
                  <Input
                    value={form.pan_number || ""}
                    onChange={(e) => setForm({ ...form, pan_number: e.target.value })}
                    placeholder="10-character PAN"
                  />
                  <button
                    type="button"
                    onClick={handleVerifyPan}
                    disabled={verifyingPan}
                    className="bg-primary text-black font-mono text-[10px] uppercase font-bold px-3 py-2 hover:bg-yellow-500 flex items-center gap-1 flex-shrink-0"
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
                  <span className={`text-[10px] font-mono font-bold px-2 py-1 border ${
                    form.pan_status === "ACTIVE"
                      ? "bg-green-950 text-green-400 border-green-800"
                      : form.pan_status
                      ? "bg-red-950 text-red-400 border-red-800"
                      : "bg-zinc-900 text-zinc-500 border-zinc-800"
                  }`}>
                    {form.pan_status || "UNVERIFIED"}
                  </span>
                </div>
              </Field>
            </div>
          </div>

          {/* Section 5: Aadhaar Verification */}
          <div>
            <div className="label-overline mb-2 text-yellow-400">Aadhaar Verification</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-zinc-900/20 p-4 border border-zinc-900">
              <Field label="Aadhaar Number">
                <div className="flex gap-2">
                  <Input
                    value={form.aadhaar_number || ""}
                    onChange={(e) => setForm({ ...form, aadhaar_number: e.target.value })}
                    placeholder="12-digit Aadhaar"
                  />
                  <button
                    type="button"
                    onClick={handleVerifyAadhaar}
                    disabled={verifyingAadhaar}
                    className="bg-primary text-black font-mono text-[10px] uppercase font-bold px-3 py-2 hover:bg-yellow-500 flex items-center gap-1 flex-shrink-0"
                  >
                    <Sparkles className="w-3 h-3" />
                    {verifyingAadhaar ? "..." : "VERIFY"}
                  </button>
                </div>
              </Field>
              <Field label="Aadhaar Holder Name">
                <Input value={form.aadhaar_holder_name || ""} disabled placeholder="Verified name" />
              </Field>
              <Field label="Aadhaar Status">
                <div className="flex items-center h-10">
                  <span className={`text-[10px] font-mono font-bold px-2 py-1 border ${
                    form.aadhaar_status === "VERIFIED"
                      ? "bg-green-950 text-green-400 border-green-800"
                      : form.aadhaar_status
                      ? "bg-red-950 text-red-400 border-red-800"
                      : "bg-zinc-900 text-zinc-500 border-zinc-800"
                  }`}>
                    {form.aadhaar_status || "UNVERIFIED"}
                  </span>
                </div>
              </Field>
            </div>
          </div>

          {/* Section 6: Commercial & Rating */}
          <div>
            <div className="label-overline mb-2 text-yellow-400">Commercial & rating</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-zinc-900/20 p-4 border border-zinc-900">
              <Field label="Vendor Rating (Out of 5.0)">
                <Input
                  type="number"
                  step="0.1"
                  min="0"
                  max="5"
                  value={form.vendor_rating || 0}
                  onChange={(e) => setForm({ ...form, vendor_rating: parseFloat(e.target.value) || 0 })}
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
    </div>
  );
}
