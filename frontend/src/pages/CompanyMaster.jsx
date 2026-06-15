import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Building2, Save, Sparkles, Landmark, FileText, CheckCircle2 } from "lucide-react";
import { PageHeader, PrimaryButton, Field, Input, Textarea } from "@/components/ui-kit";
import ImageUploader from "@/components/ImageUploader";

export default function CompanyMaster() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [profile, setProfile] = useState({
    id: "default",
    name: "",
    address: "",
    gstin: "",
    pan: "",
    state: "",
    state_code: "",
    email: "",
    phone: "",
    bank_name: "",
    bank_account_no: "",
    bank_ifsc: "",
    bank_branch: "",
    terms_conditions: "",
    logo_url: ""
  });

  useEffect(() => {
    api.get("/company/active")
      .then((res) => {
        if (res.data) {
          setProfile(res.data);
        }
      })
      .catch((err) => {
        toast.error("Failed to load company profile.");
      })
      .finally(() => setLoading(false));
  }, []);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setProfile((prev) => ({ ...prev, [name]: value }));
  };

  const handleFetchGstin = async () => {
    if (!profile.gstin || profile.gstin.trim().length !== 15) {
      toast.warning("Please enter a valid 15-digit GSTIN.");
      return;
    }
    setValidating(true);
    try {
      const res = await api.post("/gst/validate-gstin", { gstin: profile.gstin });
      if (res.data && res.data.is_valid) {
        setProfile((prev) => ({
          ...prev,
          name: res.data.trade_name || prev.name,
          pan: res.data.pan || prev.pan,
          state: res.data.state_name || prev.state,
          state_code: res.data.state_code || prev.state_code
        }));
        toast.success("Company details auto-fetched successfully!");
      } else {
        toast.error(res.data.error || "Invalid GSTIN or portal error.");
      }
    } catch (err) {
      toast.error("Failed to validate GSTIN.");
    } finally {
      setValidating(false);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await api.put(`/company/${profile.id}`, profile);
      setProfile(res.data);
      toast.success("Company Profile updated successfully!");
    } catch (err) {
      toast.error("Failed to save company profile.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] font-mono text-sm text-zinc-500 animate-pulse">
        LOADING COMPANY SETTINGS...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="System Settings"
        title="Company Master Profile"
        description="Configure your business master profile, tax parameters, letterhead setup, and bank account credentials."
      />

      <form onSubmit={handleSave} className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Side: General Profile & GST details */}
        <div className="lg:col-span-2 space-y-6">
          <div className="border border-zinc-800 bg-zinc-900/40 p-6 space-y-5 backdrop-blur-md rounded-md">
            <h3 className="text-sm font-mono uppercase tracking-wider text-zinc-300 flex items-center gap-2">
              <Building2 className="w-4 h-4 text-primary" />
              General Business details
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="md:col-span-2">
                <Field label="GSTIN" required>
                  <div className="flex gap-2">
                    <Input
                      name="gstin"
                      value={profile.gstin}
                      onChange={handleChange}
                      placeholder="e.g. 27AABCG1234F1Z5"
                      required
                    />
                    <button
                      type="button"
                      onClick={handleFetchGstin}
                      disabled={validating}
                      className="bg-primary hover:bg-primary-hover disabled:bg-zinc-800 text-black px-4 py-2 font-mono text-xs uppercase font-bold tracking-wider flex items-center gap-1"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      {validating ? "FETCHING..." : "AUTO-FETCH"}
                    </button>
                  </div>
                </Field>
              </div>

              <div className="md:col-span-2">
                <Field label="Company Legal / Trade Name" required>
                  <Input
                    name="name"
                    value={profile.name}
                    onChange={handleChange}
                    placeholder="Enter official trade name"
                    required
                  />
                </Field>
              </div>

              <div>
                <Field label="PAN Number">
                  <Input
                    name="pan"
                    value={profile.pan}
                    onChange={handleChange}
                    placeholder="Auto-extracted from GSTIN"
                  />
                </Field>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <Field label="State">
                  <Input
                    name="state"
                    value={profile.state}
                    onChange={handleChange}
                    placeholder="State"
                  />
                </Field>
                <Field label="State Code">
                  <Input
                    name="state_code"
                    value={profile.state_code}
                    onChange={handleChange}
                    placeholder="Code (e.g. 27)"
                  />
                </Field>
              </div>

              <div>
                <Field label="Contact Email">
                  <Input
                    type="email"
                    name="email"
                    value={profile.email}
                    onChange={handleChange}
                    placeholder="billing@company.com"
                  />
                </Field>
              </div>

              <div>
                <Field label="Contact Phone">
                  <Input
                    name="phone"
                    value={profile.phone}
                    onChange={handleChange}
                    placeholder="+91 99999 88888"
                  />
                </Field>
              </div>

              <div className="md:col-span-2">
                <Field label="Registered Billing Address" required>
                  <Textarea
                    name="address"
                    value={profile.address}
                    onChange={handleChange}
                    placeholder="Complete corporate address matching GST registration"
                    rows={3}
                    required
                  />
                </Field>
              </div>
            </div>
          </div>

          {/* Letterhead and Print Settings */}
          <div className="border border-zinc-800 bg-zinc-900/40 p-6 space-y-5 backdrop-blur-md rounded-md">
            <h3 className="text-sm font-mono uppercase tracking-wider text-zinc-300 flex items-center gap-2">
              <FileText className="w-4 h-4 text-primary" />
              Invoice Terms & Letterhead Setup
            </h3>

            <div>
              <Field label="Standard Invoice Terms & Conditions">
                <Textarea
                  name="terms_conditions"
                  value={profile.terms_conditions}
                  onChange={handleChange}
                  placeholder="Enter invoice disclaimer, payment terms, or jurisdiction clauses"
                  rows={4}
                />
              </Field>
            </div>
            
            <div>
              <Field label="Company Logo">
                <ImageUploader
                  value={profile.logo_url}
                  onChange={(v) => setProfile((p) => ({ ...p, logo_url: v }))}
                />
                <p className="mt-1 text-xs text-zinc-500 font-mono">
                  Attach a logo image (PNG/JPG/WebP, up to 6MB). Shown on PDF invoices.
                </p>
              </Field>
            </div>
          </div>
        </div>

        {/* Right Side: Bank details & Actions */}
        <div className="space-y-6">
          <div className="border border-zinc-800 bg-zinc-900/40 p-6 space-y-5 backdrop-blur-md rounded-md">
            <h3 className="text-sm font-mono uppercase tracking-wider text-zinc-300 flex items-center gap-2">
              <Landmark className="w-4 h-4 text-primary" />
              Bank Account details
            </h3>

            <div className="space-y-4">
              <Field label="Bank Name">
                <Input
                  name="bank_name"
                  value={profile.bank_name}
                  onChange={handleChange}
                  placeholder="e.g. HDFC Bank"
                />
              </Field>

              <Field label="Account Number">
                <Input
                  name="bank_account_no"
                  value={profile.bank_account_no}
                  onChange={handleChange}
                  placeholder="Enter account number"
                />
              </Field>

              <Field label="IFSC Code">
                <Input
                  name="bank_ifsc"
                  value={profile.bank_ifsc}
                  onChange={handleChange}
                  placeholder="e.g. HDFC0000012"
                />
              </Field>

              <Field label="Branch Name">
                <Input
                  name="bank_branch"
                  value={profile.bank_branch}
                  onChange={handleChange}
                  placeholder="e.g. Talawade, Pune"
                />
              </Field>
            </div>
          </div>

          <div className="border border-zinc-800 bg-zinc-900/40 p-5 space-y-4 rounded-md">
            <PrimaryButton
              type="submit"
              icon={Save}
              disabled={saving}
              className="w-full justify-center"
            >
              {saving ? "SAVING CHANGES..." : "SAVE CONFIGURATION"}
            </PrimaryButton>
            
            <div className="flex gap-2 items-start text-zinc-500 font-mono text-[10px] leading-relaxed">
              <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
              <span>Saving updates applies these parameters globally across all invoice letterheads, GST records, and tax calculations instantly.</span>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
