import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import SlideOver from "@/components/SlideOver";
import {
  PrimaryButton, SecondaryButton, Input, Textarea, Select, Field, NumericInput, Badge, Spinner,
} from "@/components/ui-kit";
import {
  Warehouse as WarehouseIcon, MapPin, Boxes, Grid3x3, ShieldCheck, FileText, Sparkles,
  Save, Plus, Trash2, Upload, X, Barcode as BarcodeIcon,
  Building2, Phone, Mail, TrendingUp, TrendingDown, AlertTriangle, Activity, PackageX,
} from "lucide-react";
import JsBarcode from "jsbarcode";

// ── Static option lists ──────────────────────────────────────────────
const WAREHOUSE_TYPES = [
  ["MAIN", "Main Warehouse"], ["BRANCH", "Branch Warehouse"], ["RAW_MATERIAL", "Raw Material"],
  ["FINISHED_GOODS", "Finished Goods"], ["WIP", "Work In Progress"], ["SCRAP", "Scrap"],
  ["TRANSIT", "Transit"], ["CONSIGNMENT", "Consignment"],
];
const CYCLE_FREQ = [
  ["NONE", "None"], ["DAILY", "Daily"], ["WEEKLY", "Weekly"], ["MONTHLY", "Monthly"],
  ["QUARTERLY", "Quarterly"], ["YEARLY", "Yearly"],
];
const BIN_KINDS = [
  ["RACK", "Rack"], ["SHELF", "Shelf"], ["BIN", "Bin"], ["ZONE", "Zone"],
  ["COLD_STORAGE", "Cold Storage"], ["DISPATCH", "Dispatch"], ["RETURNS", "Returns"],
];
const INDIAN_STATES = [
  "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
  "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
  "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan",
  "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
  "Delhi", "Jammu and Kashmir", "Ladakh", "Puducherry", "Chandigarh",
];

const TABS = [
  { id: "general", label: "General", icon: WarehouseIcon },
  { id: "location", label: "Location", icon: MapPin },
  { id: "inventory", label: "Inventory", icon: Boxes },
  { id: "bins", label: "Bins", icon: Grid3x3 },
  { id: "security", label: "Security", icon: ShieldCheck },
  { id: "documents", label: "Documents", icon: FileText },
  { id: "insights", label: "AI Insights", icon: Sparkles },
];

const DRAFT_KEY = "wh-draft-v1";

const blank = {
  name: "", address: "", parent_godown_id: "", code: "", short_name: "",
  warehouse_type: "MAIN", status: "ACTIVE", company_id: "", branch_id: "", cost_center_id: "",
  country: "India", state: "", city: "", pincode: "", latitude: "", longitude: "", map_url: "", photo_path: "",
  allow_negative_stock: false, enable_batch: false, enable_serial: false, enable_bin: false,
  valuation_method: "WEIGHTED_AVG", min_stock: "", max_stock: "", safety_stock: "",
  reorder_level: "", reorder_qty: "", cycle_count_frequency: "NONE",
  enable_rack_bin: false, bins: [],
  manager_name: "", manager_phone: "", manager_email: "",
  allowed_user_ids: [], allowed_roles: [], approval_required: false, read_only: false,
  allow_stock_transfer: true, allow_direct_issue: true,
  documents: [], notes: "",
};

// ── Small controls ───────────────────────────────────────────────────
function Toggle({ checked, onChange, label, hint, disabled, testid }) {
  return (
    <label className={`flex items-start justify-between gap-3 rounded-[10px] border border-border bg-card px-3.5 py-3 ${disabled ? "opacity-60" : "cursor-pointer hover:border-[var(--border-strong)]"}`}>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-foreground">{label}</span>
        {hint && <span className="mt-0.5 block text-xs text-muted-foreground">{hint}</span>}
      </span>
      <button
        type="button" role="switch" aria-checked={checked} data-testid={testid} disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={`relative mt-0.5 h-6 w-11 flex-shrink-0 rounded-full transition-colors ${checked ? "bg-primary" : "bg-muted-foreground/30"}`}
      >
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${checked ? "translate-x-[22px]" : "translate-x-0.5"}`} />
      </button>
    </label>
  );
}

function SectionGrid({ title, description, children, cols = 2 }) {
  return (
    <section className="mb-7">
      {title && (
        <div className="mb-3">
          <h3 className="font-display text-sm font-bold uppercase tracking-wide text-foreground">{title}</h3>
          {description && <p className="text-xs text-muted-foreground">{description}</p>}
        </div>
      )}
      <div className={`grid grid-cols-1 gap-4 ${cols === 3 ? "sm:grid-cols-2 lg:grid-cols-3" : cols === 1 ? "" : "sm:grid-cols-2"}`}>
        {children}
      </div>
    </section>
  );
}

// Code128 barcode rendered to an <svg> for a bin code.
function Barcode({ value, height = 40 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current && value) {
      try {
        JsBarcode(ref.current, String(value), {
          format: "CODE128", height, width: 1.4, fontSize: 11, margin: 4, displayValue: true,
        });
      } catch { /* invalid value — ignore */ }
    }
  }, [value, height]);
  return <svg ref={ref} className="max-w-full" />;
}

// Reusable document/photo uploader (backend /uploads/document).
function DocUploader({ accept, onUploaded, label = "Upload", disabled }) {
  const [busy, setBusy] = useState(false);
  const onFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/uploads/document", fd);
      onUploaded({ path: data.path, name: data.name || file.name, size: data.size, content_type: data.content_type });
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <label className={`inline-flex cursor-pointer items-center gap-2 rounded-[10px] border border-dashed border-border px-3.5 py-2.5 text-sm font-medium text-foreground transition-colors hover:border-primary hover:bg-primary/5 ${disabled ? "pointer-events-none opacity-60" : ""}`}>
      {busy ? <Spinner className="h-4 w-4" /> : <Upload className="h-4 w-4 text-muted-foreground" />}
      {busy ? "Uploading…" : label}
      <input type="file" accept={accept} className="hidden" onChange={onFile} disabled={disabled || busy} />
    </label>
  );
}

// ── Main component ────────────────────────────────────────────────────
export default function WarehouseForm({ open, warehouseId, warehouses = [], roles = [], onClose, onSaved }) {
  const [form, setForm] = useState(blank);
  const [tab, setTab] = useState("general");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});
  const [insights, setInsights] = useState(null);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const isEdit = !!warehouseId;

  const set = useCallback((patch) => setForm((f) => ({ ...f, ...patch })), []);

  // Load existing warehouse or reset to a fresh draft.
  useEffect(() => {
    if (!open) return;
    setTab("general");
    setErrors({});
    setInsights(null);
    if (warehouseId) {
      setLoading(true);
      api.get(`/inventory/v2/godowns/${warehouseId}`)
        .then((r) => setForm({ ...blank, ...r.data }))
        .catch((err) => toast.error(formatApiErrorDetail(err.response?.data?.detail)))
        .finally(() => setLoading(false));
    } else {
      // Restore an autosaved draft if present, else fetch the next code.
      let restored = false;
      try {
        const raw = localStorage.getItem(DRAFT_KEY);
        if (raw) {
          const draft = JSON.parse(raw);
          if (draft?.name || draft?.address) {
            setForm({ ...blank, ...draft });
            restored = true;
            toast.info("Restored an unsaved draft", { duration: 2500 });
          }
        }
      } catch { /* ignore corrupt draft */ }
      if (!restored) {
        setForm(blank);
        api.get("/inventory/v2/warehouses/next-code")
          .then((r) => set({ code: r.data.code }))
          .catch(() => {});
      }
    }
  }, [open, warehouseId, set]);

  // Auto-focus first field (query the DOM since ui-kit Input isn't forwardRef).
  const focusFirst = useCallback(() => {
    const el = document.querySelector('[data-testid="wh-name"]');
    if (el) el.focus();
  }, []);
  useEffect(() => {
    if (open && !loading && tab === "general") {
      const t = setTimeout(focusFirst, 120);
      return () => clearTimeout(t);
    }
  }, [open, loading, tab, focusFirst]);

  // Auto-save draft every 30s (new records only).
  useEffect(() => {
    if (!open || isEdit) return;
    const iv = setInterval(() => {
      try {
        if (form.name || form.address) localStorage.setItem(DRAFT_KEY, JSON.stringify(form));
      } catch { /* quota — ignore */ }
    }, 30000);
    return () => clearInterval(iv);
  }, [open, isEdit, form]);

  // Load AI insights lazily when that tab is opened for an existing warehouse.
  useEffect(() => {
    if (open && tab === "insights" && isEdit && !insights && !insightsLoading) {
      setInsightsLoading(true);
      api.get(`/inventory/v2/warehouses/${warehouseId}/insights`)
        .then((r) => setInsights(r.data))
        .catch(() => setInsights({ error: true }))
        .finally(() => setInsightsLoading(false));
    }
  }, [open, tab, isEdit, warehouseId, insights, insightsLoading]);

  const validate = useCallback(() => {
    const e = {};
    if (!form.name?.trim()) e.name = "Warehouse name is required";
    if (form.manager_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.manager_email)) e.manager_email = "Invalid email";
    if (form.pincode && !/^\d{4,6}$/.test(String(form.pincode))) e.pincode = "Invalid pincode";
    const codes = (form.bins || []).map((b) => b.code?.trim()).filter(Boolean);
    if (new Set(codes).size !== codes.length) e.bins = "Bin codes must be unique";
    if ((form.bins || []).some((b) => !b.code?.trim())) e.bins = "Every bin needs a code";
    setErrors(e);
    return e;
  }, [form]);

  const toNum = (v) => (v === "" || v == null ? null : Number(v));

  const doSave = useCallback(async (andNew) => {
    const e = validate();
    if (Object.keys(e).length) {
      // Jump to the tab with the first error.
      if (e.name) setTab("general");
      else if (e.pincode) setTab("location");
      else if (e.bins) setTab("bins");
      else if (e.manager_email) setTab("security");
      toast.error(Object.values(e)[0]);
      return;
    }
    const payload = {
      ...form,
      parent_godown_id: form.parent_godown_id || null,
      latitude: toNum(form.latitude), longitude: toNum(form.longitude),
      min_stock: toNum(form.min_stock), max_stock: toNum(form.max_stock),
      safety_stock: toNum(form.safety_stock), reorder_level: toNum(form.reorder_level),
      reorder_qty: toNum(form.reorder_qty),
    };
    setSaving(true);
    try {
      if (isEdit) await api.put(`/inventory/v2/godowns/${warehouseId}`, payload);
      else await api.post("/inventory/v2/godowns", payload);
      try { localStorage.removeItem(DRAFT_KEY); } catch { /* ignore */ }
      toast.success(isEdit ? "Warehouse updated" : "Warehouse created");
      onSaved?.();
      if (andNew) {
        setForm(blank);
        setTab("general");
        api.get("/inventory/v2/warehouses/next-code").then((r) => set({ code: r.data.code })).catch(() => {});
        setTimeout(focusFirst, 120);
      } else {
        onClose?.();
      }
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  }, [form, isEdit, warehouseId, validate, onSaved, onClose, set, focusFirst]);

  // Keyboard shortcuts: Ctrl+S save, Ctrl+Shift+S save & new. (Esc handled by SlideOver.)
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && (e.key === "s" || e.key === "S")) {
        e.preventDefault();
        e.stopPropagation();
        doSave(e.shiftKey);
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [open, doSave]);

  const parentOptions = useMemo(
    () => warehouses.filter((w) => w.id !== warehouseId),
    [warehouses, warehouseId]
  );

  const statusBadge = (
    <Badge tone={form.status === "ACTIVE" ? "success" : "neutral"}>
      {form.status === "ACTIVE" ? "Active" : "Inactive"}
    </Badge>
  );

  const tabsWithBadges = TABS.map((t) =>
    t.id === "bins" ? { ...t, badge: (form.bins || []).length || null } :
    t.id === "documents" ? { ...t, badge: (form.documents || []).length || null } : t
  );

  return (
    <SlideOver
      open={open}
      onClose={onClose}
      title={isEdit ? form.name || "Edit Warehouse" : "New Warehouse"}
      subtitle={form.code ? `Code ${form.code}` : "Enterprise warehouse master"}
      icon={WarehouseIcon}
      headerExtra={statusBadge}
      tabs={tabsWithBadges}
      activeTab={tab}
      onTabChange={setTab}
      testid="warehouse-form"
      footer={
        <>
          <span className="mr-auto hidden text-xs text-muted-foreground sm:block">
            <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono">Ctrl+S</kbd> Save ·{" "}
            <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono">Ctrl+Shift+S</kbd> Save &amp; New ·{" "}
            <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono">Esc</kbd> Close
          </span>
          <SecondaryButton onClick={onClose} disabled={saving}>Cancel</SecondaryButton>
          {!isEdit && (
            <SecondaryButton onClick={() => doSave(true)} disabled={saving} icon={Plus}>Save &amp; New</SecondaryButton>
          )}
          <PrimaryButton onClick={() => doSave(false)} loading={saving} icon={Save} testid="save-warehouse">
            {saving ? "Saving…" : "Save"}
          </PrimaryButton>
        </>
      }
    >
      {loading ? (
        <div className="flex h-64 items-center justify-center text-muted-foreground">
          <Spinner className="h-6 w-6" />
        </div>
      ) : (
        <div className="mx-auto max-w-4xl page-transition" key={tab}>
          {tab === "general" && (
            <GeneralTab form={form} set={set} errors={errors} parentOptions={parentOptions} />
          )}
          {tab === "location" && <LocationTab form={form} set={set} errors={errors} />}
          {tab === "inventory" && <InventoryTab form={form} set={set} />}
          {tab === "bins" && <BinsTab form={form} set={set} errors={errors} />}
          {tab === "security" && <SecurityTab form={form} set={set} errors={errors} roles={roles} />}
          {tab === "documents" && <DocumentsTab form={form} set={set} />}
          {tab === "insights" && (
            <InsightsTab isEdit={isEdit} loading={insightsLoading} insights={insights} />
          )}
        </div>
      )}
    </SlideOver>
  );
}

// ── Tab 1: General ────────────────────────────────────────────────────
function GeneralTab({ form, set, errors, parentOptions }) {
  return (
    <>
      <SectionGrid title="Identity" description="How this warehouse is identified across the ERP.">
        <Field label="Warehouse Code" hint="Auto-generated">
          <Input value={form.code} readOnly disabled placeholder="Auto" />
        </Field>
        <Field label="Warehouse Name" required error={errors.name}>
          <Input data-testid="wh-name" autoFocus value={form.name}
            onChange={(e) => set({ name: e.target.value })} placeholder="e.g. Central Distribution Center" />
        </Field>
        <Field label="Short Name" hint="For labels & reports">
          <Input value={form.short_name} onChange={(e) => set({ short_name: e.target.value })} placeholder="e.g. CDC" />
        </Field>
        <Field label="Parent Warehouse">
          <Select value={form.parent_godown_id} onChange={(e) => set({ parent_godown_id: e.target.value })}>
            <option value="">— None (top level) —</option>
            {parentOptions.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </Select>
        </Field>
      </SectionGrid>

      <SectionGrid title="Classification">
        <Field label="Warehouse Type">
          <Select value={form.warehouse_type} onChange={(e) => set({ warehouse_type: e.target.value })}>
            {WAREHOUSE_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </Field>
        <Field label="Status">
          <Select value={form.status} onChange={(e) => set({ status: e.target.value })}>
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
          </Select>
        </Field>
      </SectionGrid>

      <SectionGrid title="Accounting" description="Optional links to your org structure." cols={3}>
        <Field label="Company"><Input value={form.company_id} onChange={(e) => set({ company_id: e.target.value })} placeholder="Company name / ID" /></Field>
        <Field label="Branch"><Input value={form.branch_id} onChange={(e) => set({ branch_id: e.target.value })} placeholder="Branch name / ID" /></Field>
        <Field label="Cost Center"><Input value={form.cost_center_id} onChange={(e) => set({ cost_center_id: e.target.value })} placeholder="Cost center" /></Field>
      </SectionGrid>
    </>
  );
}

// ── Tab 2: Location ───────────────────────────────────────────────────
function LocationTab({ form, set, errors }) {
  const photoUrl = usePreview(form.photo_path);
  return (
    <>
      <SectionGrid title="Address" cols={1}>
        <Field label="Address">
          <Textarea rows={2} value={form.address} onChange={(e) => set({ address: e.target.value })}
            placeholder="Street, area, landmark" />
        </Field>
      </SectionGrid>

      <SectionGrid title="Region" cols={2}>
        <Field label="Country"><Input value={form.country} onChange={(e) => set({ country: e.target.value })} /></Field>
        <Field label="State">
          <Select value={form.state} onChange={(e) => set({ state: e.target.value })}>
            <option value="">— Select state —</option>
            {INDIAN_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
          </Select>
        </Field>
        <Field label="City"><Input value={form.city} onChange={(e) => set({ city: e.target.value })} /></Field>
        <Field label="Pincode" error={errors.pincode}>
          <Input value={form.pincode} onChange={(e) => set({ pincode: e.target.value })} placeholder="e.g. 560001" />
        </Field>
      </SectionGrid>

      <SectionGrid title="Geo-location" cols={3}>
        <Field label="Latitude"><NumericInput decimals={6} value={form.latitude} onChange={(v) => set({ latitude: v })} align="left" /></Field>
        <Field label="Longitude"><NumericInput decimals={6} value={form.longitude} onChange={(v) => set({ longitude: v })} align="left" /></Field>
        <Field label="Google Map URL">
          <Input value={form.map_url} onChange={(e) => set({ map_url: e.target.value })} placeholder="https://maps.google.com/…" />
        </Field>
      </SectionGrid>

      <SectionGrid title="Warehouse Photo" cols={1}>
        <div className="flex items-center gap-4">
          {photoUrl ? (
            <div className="relative h-28 w-40 overflow-hidden rounded-[10px] border border-border bg-muted">
              <img src={photoUrl} alt="Warehouse" className="h-full w-full object-cover" />
              <button type="button" onClick={() => set({ photo_path: "" })}
                className="absolute right-1 top-1 flex h-6 w-6 items-center justify-center rounded-md bg-black/60 text-white hover:bg-black/80">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : (
            <div className="flex h-28 w-40 items-center justify-center rounded-[10px] border border-dashed border-border text-muted-foreground">
              <MapPin className="h-6 w-6" />
            </div>
          )}
          <DocUploader accept="image/*" label="Upload photo" onUploaded={(d) => set({ photo_path: d.path })} />
        </div>
      </SectionGrid>
    </>
  );
}

// ── Tab 3: Inventory settings ─────────────────────────────────────────
function InventoryTab({ form, set }) {
  return (
    <>
      <SectionGrid title="Tracking & rules">
        <Toggle label="Allow Negative Stock" hint="Permit issuing beyond on-hand" checked={form.allow_negative_stock} onChange={(v) => set({ allow_negative_stock: v })} testid="wh-neg-stock" />
        <Toggle label="Enable Batch Tracking" hint="Lot / batch numbers" checked={form.enable_batch} onChange={(v) => set({ enable_batch: v })} />
        <Toggle label="Enable Serial Numbers" hint="Per-unit serial tracking" checked={form.enable_serial} onChange={(v) => set({ enable_serial: v })} />
        <Toggle label="Enable Bin Management" hint="Rack / shelf / bin locations" checked={form.enable_bin} onChange={(v) => set({ enable_bin: v, enable_rack_bin: v || form.enable_rack_bin })} />
      </SectionGrid>

      <SectionGrid title="Valuation & levels" cols={3}>
        <Field label="Default Valuation Method">
          <Select value={form.valuation_method} onChange={(e) => set({ valuation_method: e.target.value })}>
            <option value="FIFO">FIFO</option>
            <option value="WEIGHTED_AVG">Weighted Average</option>
          </Select>
        </Field>
        <Field label="Minimum Stock"><NumericInput value={form.min_stock} onChange={(v) => set({ min_stock: v })} /></Field>
        <Field label="Maximum Stock"><NumericInput value={form.max_stock} onChange={(v) => set({ max_stock: v })} /></Field>
        <Field label="Safety Stock"><NumericInput value={form.safety_stock} onChange={(v) => set({ safety_stock: v })} /></Field>
        <Field label="Reorder Level"><NumericInput value={form.reorder_level} onChange={(v) => set({ reorder_level: v })} /></Field>
        <Field label="Reorder Quantity"><NumericInput value={form.reorder_qty} onChange={(v) => set({ reorder_qty: v })} /></Field>
        <Field label="Cycle Count Frequency">
          <Select value={form.cycle_count_frequency} onChange={(e) => set({ cycle_count_frequency: e.target.value })}>
            {CYCLE_FREQ.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </Field>
      </SectionGrid>
    </>
  );
}

// ── Tab 4: Bin management ─────────────────────────────────────────────
function BinsTab({ form, set, errors }) {
  const [showBarcode, setShowBarcode] = useState(null);
  const bins = form.bins || [];

  const addBin = (kind = "BIN") => {
    const n = bins.length + 1;
    const code = `${kind === "RACK" ? "R" : kind === "SHELF" ? "S" : "B"}${String(n).padStart(3, "0")}`;
    set({ bins: [...bins, { id: `tmp-${Date.now()}`, code, name: "", kind, capacity: "", barcode: code, notes: "" }] });
  };
  const updateBin = (i, patch) => {
    const next = bins.slice();
    next[i] = { ...next[i], ...patch };
    set({ bins: next });
  };
  const removeBin = (i) => set({ bins: bins.filter((_, idx) => idx !== i) });

  return (
    <>
      <SectionGrid cols={1}>
        <Toggle label="Enable Rack & Bin Structure" hint="Organise storage into racks, shelves, zones and bins" checked={form.enable_rack_bin} onChange={(v) => set({ enable_rack_bin: v })} testid="wh-rack-bin" />
      </SectionGrid>

      {form.enable_rack_bin && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <SecondaryButton icon={Plus} onClick={() => addBin("RACK")}>Add Rack</SecondaryButton>
            <SecondaryButton icon={Plus} onClick={() => addBin("SHELF")}>Add Shelf</SecondaryButton>
            <SecondaryButton icon={Plus} onClick={() => addBin("BIN")}>Add Bin</SecondaryButton>
            <SecondaryButton icon={Plus} onClick={() => addBin("ZONE")}>Add Zone</SecondaryButton>
          </div>
          {errors.bins && <p className="mb-2 text-sm text-[var(--danger)]">{errors.bins}</p>}

          {bins.length === 0 ? (
            <div className="rounded-[10px] border border-dashed border-border py-12 text-center text-muted-foreground">
              No bins yet. Add a rack, shelf, zone or bin to start.
            </div>
          ) : (
            <div className="overflow-hidden rounded-[10px] border border-border">
              <table className="w-full text-sm">
                <thead className="bg-muted text-muted-foreground">
                  <tr className="label-overline">
                    <th className="px-3 py-2.5 text-left">Kind</th>
                    <th className="px-3 py-2.5 text-left">Code</th>
                    <th className="px-3 py-2.5 text-left">Name</th>
                    <th className="px-3 py-2.5 text-right">Capacity</th>
                    <th className="px-3 py-2.5 text-right">Label</th>
                    <th className="px-3 py-2.5" />
                  </tr>
                </thead>
                <tbody>
                  {bins.map((b, i) => (
                    <Fragment key={b.id || i}>
                      <tr className="border-t border-border">
                        <td className="px-3 py-2">
                          <select value={b.kind} onChange={(e) => updateBin(i, { kind: e.target.value })}
                            className="w-full rounded-md border border-input bg-surface px-2 py-1 text-sm">
                            {BIN_KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                          </select>
                        </td>
                        <td className="px-3 py-2">
                          <input value={b.code} onChange={(e) => updateBin(i, { code: e.target.value, barcode: e.target.value })}
                            className="w-28 rounded-md border border-input bg-surface px-2 py-1 font-mono text-sm" placeholder="Code" />
                        </td>
                        <td className="px-3 py-2">
                          <input value={b.name} onChange={(e) => updateBin(i, { name: e.target.value })}
                            className="w-full rounded-md border border-input bg-surface px-2 py-1 text-sm" placeholder="Description" />
                        </td>
                        <td className="px-3 py-2 text-right">
                          <input value={b.capacity} onChange={(e) => updateBin(i, { capacity: e.target.value })}
                            className="w-20 rounded-md border border-input bg-surface px-2 py-1 text-right font-mono text-sm" placeholder="—" />
                        </td>
                        <td className="px-3 py-2 text-right">
                          <button type="button" onClick={() => setShowBarcode(showBarcode === i ? null : i)}
                            className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:border-primary hover:text-primary">
                            <BarcodeIcon className="h-3.5 w-3.5" /> {showBarcode === i ? "Hide" : "Show"}
                          </button>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <button type="button" onClick={() => removeBin(i)}
                            className="flex h-7 w-7 items-center justify-center rounded-md border border-border text-muted-foreground hover:border-[var(--danger)] hover:text-[var(--danger)]">
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      </tr>
                      {showBarcode === i && b.code && (
                        <tr className="border-t border-border bg-muted/30">
                          <td colSpan={6} className="px-3 py-3">
                            <div className="flex items-center justify-center rounded-md bg-white p-2">
                              <Barcode value={b.code} />
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}

// ── Tab 5: Security ───────────────────────────────────────────────────
function SecurityTab({ form, set, errors, roles }) {
  const toggleRole = (r) => {
    const has = (form.allowed_roles || []).includes(r);
    set({ allowed_roles: has ? form.allowed_roles.filter((x) => x !== r) : [...(form.allowed_roles || []), r] });
  };
  return (
    <>
      <SectionGrid title="Warehouse Manager" cols={3}>
        <Field label="Manager">
          <div className="relative">
            <Building2 className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-9" value={form.manager_name} onChange={(e) => set({ manager_name: e.target.value })} placeholder="Full name" />
          </div>
        </Field>
        <Field label="Phone">
          <div className="relative">
            <Phone className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-9" value={form.manager_phone} onChange={(e) => set({ manager_phone: e.target.value })} placeholder="+91…" />
          </div>
        </Field>
        <Field label="Email" error={errors.manager_email}>
          <div className="relative">
            <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input className="pl-9" value={form.manager_email} onChange={(e) => set({ manager_email: e.target.value })} placeholder="manager@company.com" />
          </div>
        </Field>
      </SectionGrid>

      <SectionGrid title="Allowed Roles" cols={1}>
        <div className="flex flex-wrap gap-2">
          {(roles.length ? roles : ["admin", "accountant", "manager", "operator", "viewer"]).map((r) => {
            const on = (form.allowed_roles || []).includes(r);
            return (
              <button key={r} type="button" onClick={() => toggleRole(r)}
                className={`rounded-full border px-3 py-1.5 text-sm font-medium capitalize transition-colors ${on ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:border-[var(--border-strong)]"}`}>
                {r}
              </button>
            );
          })}
        </div>
      </SectionGrid>

      <SectionGrid title="Access controls">
        <Toggle label="Approval Required" hint="Movements need approval before posting" checked={form.approval_required} onChange={(v) => set({ approval_required: v })} />
        <Toggle label="Read-only Mode" hint="Block all new movements" checked={form.read_only} onChange={(v) => set({ read_only: v })} />
        <Toggle label="Allow Stock Transfer" hint="Permit transfers to/from here" checked={form.allow_stock_transfer} onChange={(v) => set({ allow_stock_transfer: v })} />
        <Toggle label="Allow Direct Issue" hint="Permit direct material issue" checked={form.allow_direct_issue} onChange={(v) => set({ allow_direct_issue: v })} />
      </SectionGrid>
    </>
  );
}

// ── Tab 6: Documents ──────────────────────────────────────────────────
const DOC_CATEGORIES = [
  ["INSURANCE", "Insurance"], ["FIRE_SAFETY", "Fire Safety"], ["LAYOUT", "Warehouse Layout"],
  ["AGREEMENT", "Agreement"], ["IMAGE", "Images"], ["OTHER", "Other"],
];
function DocumentsTab({ form, set }) {
  const docs = form.documents || [];
  const addDoc = (category, d) => set({ documents: [...docs, { id: `tmp-${Date.now()}`, category, ...d }] });
  const removeDoc = (i) => set({ documents: docs.filter((_, idx) => idx !== i) });
  return (
    <>
      <SectionGrid title="Documents" description="Insurance, fire-safety certificates, layout plans, agreements and images." cols={1}>
        <div className="flex flex-wrap gap-2">
          {DOC_CATEGORIES.map(([v, l]) => (
            <DocUploader key={v} accept="image/*,application/pdf" label={`+ ${l}`}
              onUploaded={(d) => addDoc(v, d)} />
          ))}
        </div>
      </SectionGrid>

      {docs.length > 0 && (
        <div className="mb-7 space-y-2">
          {docs.map((d, i) => (
            <div key={d.id || i} className="flex items-center justify-between gap-3 rounded-[10px] border border-border bg-card px-3.5 py-2.5">
              <div className="flex min-w-0 items-center gap-2.5">
                <FileText className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-foreground">{d.name}</span>
                  <span className="text-xs text-muted-foreground">{DOC_CATEGORIES.find(([v]) => v === d.category)?.[1] || d.category}</span>
                </span>
              </div>
              <button type="button" onClick={() => removeDoc(i)}
                className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md border border-border text-muted-foreground hover:border-[var(--danger)] hover:text-[var(--danger)]">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      <SectionGrid title="Notes" cols={1}>
        <Field label="Notes">
          <Textarea rows={4} value={form.notes} onChange={(e) => set({ notes: e.target.value })}
            placeholder="Internal notes about this warehouse…" />
        </Field>
      </SectionGrid>
    </>
  );
}

// ── Tab 7: AI Insights ────────────────────────────────────────────────
function InsightsTab({ isEdit, loading, insights }) {
  if (!isEdit) {
    return (
      <div className="rounded-[10px] border border-dashed border-border py-16 text-center text-muted-foreground">
        <Sparkles className="mx-auto mb-2 h-7 w-7 text-primary/50" />
        Save the warehouse first to unlock AI insights.
      </div>
    );
  }
  if (loading) {
    return <div className="flex h-48 items-center justify-center"><Spinner className="h-6 w-6" /></div>;
  }
  if (!insights || insights.error) {
    return <div className="py-16 text-center text-muted-foreground">No insight data available yet.</div>;
  }
  const money = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  const healthTone = insights.inventory_health_score >= 75 ? "success" : insights.inventory_health_score >= 50 ? "warning" : "danger";
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <InsightCard icon={TrendingUp} label="Current Stock Value" value={money(insights.stock_value)} accent />
        <InsightCard icon={Grid3x3} label="Storage Utilisation"
          value={insights.storage_utilisation != null ? `${insights.storage_utilisation}%` : "—"}
          sub={insights.storage_utilisation == null ? "Set bin capacities" : undefined} />
        <InsightCard icon={Activity} label="Inventory Health"
          value={`${insights.inventory_health_score}/100`} tone={healthTone} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <InsightList icon={PackageX} title="Dead Stock" tone="danger"
          rows={insights.dead_stock} render={(r) => `${r.name} · ${money(r.value)}`} empty="No dead stock 🎉" />
        <InsightList icon={TrendingUp} title="Fast-moving Items" tone="success"
          rows={insights.fast_moving} render={(r) => `${r.name} · ${r.out_30d} out (30d)`} empty="No movement yet" />
        <InsightList icon={TrendingDown} title="Slow-moving Items" tone="warning"
          rows={insights.slow_moving} render={(r) => `${r.name} · qty ${r.qty}`} empty="—" />
        <InsightList icon={AlertTriangle} title="Reorder Suggestions" tone="warning"
          rows={insights.reorder_suggestions} render={(r) => `${r.name} · order ${r.suggested_qty}`} empty="Nothing to reorder" />
        <InsightList icon={AlertTriangle} title="Expected Stockouts" tone="danger"
          rows={insights.expected_stockout} render={(r) => `${r.name} · ~${r.days_cover}d (${r.expected_stockout})`} empty="No imminent stockouts" />
      </div>
    </div>
  );
}

function InsightCard({ icon: Icon, label, value, sub, accent, tone }) {
  const toneColor = tone === "danger" ? "text-[var(--danger)]" : tone === "warning" ? "text-amber-600" : tone === "success" ? "text-primary" : accent ? "text-primary" : "text-foreground";
  return (
    <div className="rounded-[10px] border border-border bg-card p-4" style={{ boxShadow: "var(--shadow-sm)" }}>
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="h-4 w-4" />
        <span className="label-overline">{label}</span>
      </div>
      <div className={`mt-1.5 font-display text-2xl font-bold ${toneColor}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

function InsightList({ icon: Icon, title, rows = [], render, empty, tone }) {
  const toneColor = tone === "danger" ? "text-[var(--danger)]" : tone === "warning" ? "text-amber-600" : tone === "success" ? "text-primary" : "text-foreground";
  return (
    <div className="rounded-[10px] border border-border bg-card p-4" style={{ boxShadow: "var(--shadow-sm)" }}>
      <div className={`mb-2 flex items-center gap-2 text-sm font-bold ${toneColor}`}>
        <Icon className="h-4 w-4" /> {title}
        <span className="ml-auto text-xs font-normal text-muted-foreground">{rows.length}</span>
      </div>
      {rows.length === 0 ? (
        <p className="py-3 text-center text-xs text-muted-foreground">{empty}</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {rows.slice(0, 6).map((r, i) => (
            <li key={i} className="flex items-center gap-2 truncate text-foreground">
              <span className="h-1 w-1 flex-shrink-0 rounded-full bg-muted-foreground/50" />
              <span className="truncate">{render(r)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Helper: preview an object-storage image path as a blob URL ─────────
function usePreview(path) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let revoked = null;
    if (!path) { setSrc(null); return; }
    if (String(path).startsWith("http")) { setSrc(path); return; }
    api.get(`/files/${path}`, { responseType: "blob" })
      .then((r) => { const u = URL.createObjectURL(r.data); revoked = u; setSrc(u); })
      .catch(() => setSrc(null));
    return () => { if (revoked) URL.revokeObjectURL(revoked); };
  }, [path]);
  return src;
}
