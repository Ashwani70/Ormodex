import { useState, useEffect, useRef, useCallback } from "react";
import api, { API } from "@/lib/api";
import DragDropCanvas from "@/components/LetterheadCanvas";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import {
  FileText, Plus, Copy, Trash2, Star, Eye, Upload,
  Settings, History, LayoutTemplate, Check, Layers,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

// ── Helpers ───────────────────────────────────────────────────────────────────
// Convert a stored path (e.g. "letterhead/tid/id/logo_primary.png") to a
// browser-accessible URL via the serve endpoint.
function fileUrl(storedPath) {
  if (!storedPath) return null;
  // Already a full http URL (future-proofing for cloud storage)
  if (storedPath.startsWith("http")) return storedPath;
  return `${API}/letterhead/files/${storedPath}`;
}

// ── Constants ─────────────────────────────────────────────────────────────────
const THEMES = [
  { key: "corporate_blue",   label: "Corporate Blue",   header: "#1a56db", accent: "#f59e0b" },
  { key: "modern_dark",      label: "Modern Dark",      header: "#18181b", accent: "#facc15" },
  { key: "luxury_gold",      label: "Luxury Gold",      header: "#451a03", accent: "#d97706" },
  { key: "industrial_steel", label: "Industrial Steel", header: "#374151", accent: "#ef4444" },
  { key: "minimal_white",    label: "Minimal White",    header: "#ffffff", accent: "#6366f1" },
  { key: "executive_grey",   label: "Executive Grey",   header: "#4b5563", accent: "#0ea5e9" },
];

const PAGE_SIZES = ["A4", "A4_landscape", "letter"];

const DOC_TYPE_LABELS = {
  quotation: "Quotation", purchase_order: "Purchase Order",
  purchase_bill: "Purchase Bill", sales_order: "Sales Order",
  gst_invoice: "GST Invoice", delivery_challan: "Delivery Challan",
  credit_note: "Credit Note", debit_note: "Debit Note",
  payment_voucher: "Payment Voucher", receipt_voucher: "Receipt Voucher",
  journal_voucher: "Journal Voucher", expense_report: "Expense Report",
  payslip: "Payslip", bank_statement: "Bank Statement",
  proforma_invoice: "Proforma Invoice", work_order: "Work Order",
  packing_list: "Packing List", lr_copy: "LR Copy",
  e_way_bill: "E-Way Bill", custom: "Custom",
};

const EMPTY_TEMPLATE = {
  template_name: "",
  theme: "corporate_blue",
  page_size: "A4",
  margin_top: 15, margin_bottom: 15, margin_left: 20, margin_right: 20,
  header_height: 35, footer_height: 22,
  logo_position: "left", logo_width_mm: 42, logo_height_mm: 18,
  header_elements: [], footer_elements: [],
  watermark_text: "", watermark_opacity: 0.08, watermark_angle: -45,
  watermark_font_size: 60, watermark_color: "#888888",
  primary_color: "#1a56db", secondary_color: "#f3f4f6",
  accent_color: "#f59e0b", text_color: "#111827",
  header_bg_color: "#1a56db", footer_bg_color: "#f0f4ff",
  font_family: "Helvetica", font_size_body: 10,
  applied_to: [], is_default: false,
  logo_url: null, logo2_url: null, background_image: null,
};

// ── Status badge ──────────────────────────────────────────────────────────────
function StatusBadge({ tmpl }) {
  if (!tmpl.is_active)  return <Badge variant="secondary">Inactive</Badge>;
  if (tmpl.is_default)  return <Badge className="bg-amber-500 text-white">Default</Badge>;
  return <Badge variant="outline" className="text-green-700 border-green-400">Active</Badge>;
}

// ── Live header preview (CSS only — updates instantly as form changes) ─────────
function HeaderPreview({ tmpl, company }) {
  const theme = THEMES.find(t => t.key === tmpl.theme) || THEMES[0];
  const hdrBg    = tmpl.header_bg_color || theme.header;
  const accent   = tmpl.accent_color    || theme.accent;
  const isDark   = hdrBg !== "#ffffff" && hdrBg !== "#fff";
  const txtColor = isDark ? "#fff" : "#111";
  const subColor = isDark ? "#ddd" : "#555";

  const coName = company?.name    || "Your Company Name";
  const coAddr = company?.address || "123 Business Street, City";
  const gstin  = company?.gstin   || "22AAAAA0000A1Z5";
  const logoSrc = fileUrl(tmpl.logo_url);

  return (
    <div className="rounded-lg overflow-hidden border border-border shadow-sm text-xs select-none">
      {/* Header band */}
      <div style={{
        background: hdrBg,
        borderBottom: `3px solid ${accent}`,
        padding: "10px 14px",
        display: "flex", alignItems: "center", gap: 10, minHeight: 68,
      }}>
        {/* Logo area */}
        {tmpl.logo_position === "left" && (
          <div style={{ width: 52, height: 24, flexShrink: 0 }}>
            {logoSrc
              ? <img src={logoSrc} alt="logo" style={{ maxWidth: 52, maxHeight: 24, objectFit: "contain" }} />
              : <div style={{ width: 52, height: 24, background: "rgba(255,255,255,0.2)", borderRadius: 4,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  color: "rgba(255,255,255,0.5)", fontSize: 8 }}>LOGO</div>
            }
          </div>
        )}

        {/* Company info */}
        <div style={{ flex: 1 }}>
          {tmpl.logo_position === "center" && logoSrc && (
            <div style={{ textAlign: "center", marginBottom: 2 }}>
              <img src={logoSrc} alt="logo" style={{ maxHeight: 22, objectFit: "contain", margin: "0 auto" }} />
            </div>
          )}
          <div style={{ color: txtColor, fontWeight: 700, fontSize: 14 }}>{coName}</div>
          <div style={{ color: subColor, fontSize: 8, marginTop: 1 }}>{coAddr}</div>
        </div>

        {/* Right: tax IDs */}
        <div style={{ color: subColor, fontSize: 8, textAlign: "right", flexShrink: 0 }}>
          <div>GSTIN: {gstin}</div>
          {company?.email && <div style={{ marginTop: 2 }}>{company.email}</div>}
          {tmpl.logo_position === "right" && logoSrc && (
            <img src={logoSrc} alt="logo"
              style={{ maxWidth: 48, maxHeight: 20, objectFit: "contain", marginTop: 4, marginLeft: "auto" }} />
          )}
        </div>
      </div>

      {/* Body placeholder — intentional print colors, not theme tokens */}
      {/* eslint-disable-next-line no-restricted-syntax */}
      <div style={{ background: "#fff", padding: "10px 14px", minHeight: 48 }}>
        {/* eslint-disable-next-line no-restricted-syntax */}
        <div style={{ color: "#9ca3af", fontSize: 9, fontStyle: "italic" }}>
          ← Document body content appears here →
        </div>
      </div>

      {/* Footer band — intentional print colors */}
      {/* eslint-disable-next-line no-restricted-syntax */}
      <div style={{
        background: tmpl.footer_bg_color || "#f0f4ff",
        borderTop: `1px solid ${accent}`,
        padding: "6px 14px",
        // eslint-disable-next-line no-restricted-syntax
        display: "flex", justifyContent: "space-between", color: "#555", fontSize: 8,
      }}>
        <span>{coAddr}</span>
        <span>Page 1 of 1</span>
      </div>
    </div>
  );
}

// ── Template settings form ────────────────────────────────────────────────────
function TemplateForm({ value, onChange }) {
  const set = (field, val) => onChange({ ...value, [field]: val });

  return (
    <div className="space-y-5">
      {/* Basic */}
      <section>
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Basic</h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Label>Template Name *</Label>
            <Input value={value.template_name} onChange={e => set("template_name", e.target.value)}
              placeholder="e.g. Corporate Letterhead" />
          </div>
          <div>
            <Label>Theme</Label>
            <Select value={value.theme} onValueChange={v => set("theme", v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {THEMES.map(t => (
                  <SelectItem key={t.key} value={t.key}>
                    <div className="flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full inline-block" style={{ background: t.header }} />
                      {t.label}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Page Size</Label>
            <Select value={value.page_size} onValueChange={v => set("page_size", v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {PAGE_SIZES.map(ps => <SelectItem key={ps} value={ps}>{ps.replace(/_/g, " ")}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Font Family</Label>
            <Select value={value.font_family} onValueChange={v => set("font_family", v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {["Helvetica", "Times-Roman", "Courier"].map(f => <SelectItem key={f} value={f}>{f}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Body Font Size (pt)</Label>
            <Input type="number" min={7} max={14} value={value.font_size_body}
              onChange={e => set("font_size_body", +e.target.value)} />
          </div>
        </div>
      </section>

      {/* Layout */}
      <section>
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Layout (mm)</h3>
        <div className="grid grid-cols-2 gap-3">
          {[
            ["margin_top", "Top Margin"], ["margin_bottom", "Bottom Margin"],
            ["margin_left", "Left Margin"], ["margin_right", "Right Margin"],
            ["header_height", "Header Height"], ["footer_height", "Footer Height"],
          ].map(([f, lbl]) => (
            <div key={f}>
              <Label>{lbl}</Label>
              <Input type="number" min={0} max={100} value={value[f]}
                onChange={e => set(f, +e.target.value)} />
            </div>
          ))}
        </div>
      </section>

      {/* Logo */}
      <section>
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Logo</h3>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <Label>Position</Label>
            <Select value={value.logo_position} onValueChange={v => set("logo_position", v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {["left", "center", "right"].map(p => <SelectItem key={p} value={p}>{p}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Width (mm)</Label>
            <Input type="number" value={value.logo_width_mm} onChange={e => set("logo_width_mm", +e.target.value)} />
          </div>
          <div>
            <Label>Height (mm)</Label>
            <Input type="number" value={value.logo_height_mm} onChange={e => set("logo_height_mm", +e.target.value)} />
          </div>
        </div>
      </section>

      {/* Colours */}
      <section>
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Colours</h3>
        <div className="grid grid-cols-2 gap-3">
          {[
            ["primary_color",    "Primary"],
            ["secondary_color",  "Secondary"],
            ["accent_color",     "Accent / Divider"],
            ["text_color",       "Body Text"],
            ["header_bg_color",  "Header Background"],
            ["footer_bg_color",  "Footer Background"],
          ].map(([f, lbl]) => (
            <div key={f} className="flex items-center gap-2">
              <input type="color" value={value[f] || "#000000"}
                onChange={e => set(f, e.target.value)}
                className="w-8 h-8 rounded cursor-pointer border border-border" />
              <div>
                <Label className="leading-tight">{lbl}</Label>
                <p className="text-xs text-muted-foreground font-mono">{value[f]}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Watermark */}
      <section>
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">Watermark</h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Label>Watermark Text (blank = none)</Label>
            <Input value={value.watermark_text || ""} onChange={e => set("watermark_text", e.target.value)}
              placeholder="e.g. CONFIDENTIAL" />
          </div>
          <div>
            <Label>Opacity (0–1)</Label>
            <Input type="number" min={0.01} max={1} step={0.01} value={value.watermark_opacity}
              onChange={e => set("watermark_opacity", +e.target.value)} />
          </div>
          <div>
            <Label>Angle (degrees)</Label>
            <Input type="number" min={-90} max={90} value={value.watermark_angle}
              onChange={e => set("watermark_angle", +e.target.value)} />
          </div>
        </div>
      </section>

      {/* Flags */}
      <section>
        <div className="flex items-center gap-3">
          <Switch checked={!!value.is_default} onCheckedChange={v => set("is_default", v)} id="is_default" />
          <Label htmlFor="is_default">Set as default template</Label>
        </div>
      </section>
    </div>
  );
}

// ── Upload button — shows thumbnail of existing logo and handles upload ────────
function UploadBtn({ label, storedPath, onUploaded, apiPath }) {
  const ref = useRef();
  const [uploading, setUploading] = useState(false);
  const displayUrl = fileUrl(storedPath);

  const upload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await api.post(apiPath, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      onUploaded(res.data.url); // stored path returned by backend
      toast.success(`${label} uploaded`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  return (
    <div className="flex items-center gap-3">
      {displayUrl ? (
        <img src={displayUrl} alt={label}
          className="h-10 w-auto max-w-[80px] rounded border border-border object-contain bg-muted/30 p-0.5" />
      ) : (
        <div className="h-10 w-20 rounded border border-dashed border-border flex items-center justify-center text-[10px] text-muted-foreground">
          No image
        </div>
      )}
      <Button variant="outline" size="sm" disabled={uploading} onClick={() => ref.current?.click()}>
        <Upload className="w-3.5 h-3.5 mr-1" />
        {uploading ? "Uploading…" : storedPath ? `Replace` : `Upload ${label}`}
      </Button>
      <input ref={ref} type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml"
        className="hidden" onChange={upload} />
    </div>
  );
}

// ── Document assignment panel ─────────────────────────────────────────────────
function DocAssignPanel({ templateId, appliedTo, onSaved }) {
  const [selected, setSelected] = useState(appliedTo || []);
  const [saving, setSaving] = useState(false);

  const toggle = (dt) =>
    setSelected(prev => prev.includes(dt) ? prev.filter(x => x !== dt) : [...prev, dt]);

  const save = async () => {
    setSaving(true);
    try {
      await api.patch(`/letterhead/templates/${templateId}/apply-to`, { applied_to: selected });
      toast.success("Document assignments saved");
      onSaved(selected);
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">Select which document types use this template.</p>
      <div className="grid grid-cols-2 gap-2 max-h-72 overflow-y-auto pr-1">
        {Object.entries(DOC_TYPE_LABELS).map(([key, label]) => (
          <button key={key} onClick={() => toggle(key)}
            className={cn(
              "flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-colors text-left",
              selected.includes(key)
                ? "border-primary bg-primary/10 text-primary font-medium"
                : "border-border hover:bg-muted"
            )}>
            {selected.includes(key)
              ? <Check className="w-3 h-3 shrink-0" />
              : <span className="w-3 h-3 shrink-0" />}
            {label}
          </button>
        ))}
      </div>
      <Button onClick={save} disabled={saving} size="sm">
        {saving ? "Saving…" : "Save Assignments"}
      </Button>
    </div>
  );
}

// ── Version history panel ─────────────────────────────────────────────────────
function VersionHistoryPanel({ templateId, onRestored }) {
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState(null);

  useEffect(() => {
    api.get(`/letterhead/templates/${templateId}/versions`)
      .then(r => setVersions(r.data.items || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [templateId]);

  const restore = async (ver) => {
    setRestoring(ver.id);
    try {
      await api.post(`/letterhead/templates/${templateId}/versions/${ver.id}/restore`,
        { change_note: `Restored to version ${ver.version}` });
      toast.success(`Restored to version ${ver.version}`);
      onRestored();
    } catch {
      toast.error("Restore failed");
    } finally {
      setRestoring(null);
    }
  };

  if (loading) return <p className="text-sm text-muted-foreground py-4">Loading history…</p>;
  if (!versions.length) return <p className="text-sm text-muted-foreground py-4">No version history yet.</p>;

  return (
    <div className="space-y-2 max-h-96 overflow-y-auto">
      {versions.map(ver => (
        <div key={ver.id} className="flex items-start gap-3 p-3 rounded-lg border border-border hover:bg-muted/40">
          <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary text-xs font-bold shrink-0">
            v{ver.version}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{ver.change_note || "Updated"}</p>
            <p className="text-xs text-muted-foreground">
              {ver.changed_by || "—"} · {ver.created_at ? new Date(ver.created_at).toLocaleString() : "—"}
            </p>
          </div>
          <Button size="sm" variant="outline" disabled={restoring === ver.id} onClick={() => restore(ver)}>
            {restoring === ver.id ? "…" : "Restore"}
          </Button>
        </div>
      ))}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function LetterheadDesigner() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [company, setCompany]     = useState({});

  // edit modal
  const [formOpen, setFormOpen]   = useState(false);
  const [formMode, setFormMode]   = useState("create");
  const [selected, setSelected]   = useState(null);
  const [form, setForm]           = useState(EMPTY_TEMPLATE);
  const [saving, setSaving]       = useState(false);

  // delete
  const [deleteId, setDeleteId]   = useState(null);
  const [deleting, setDeleting]   = useState(false);

  // panels
  const [assignOpen, setAssignOpen]   = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [panelTmpl, setPanelTmpl]     = useState(null);

  // preview PDF
  const [previewing, setPreviewing]   = useState(false);

  // drag-drop region being edited in the canvas: "header" or "footer"
  const [dndRegion, setDndRegion]     = useState("header");

  // ── Load ──────────────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [tmplRes, coRes] = await Promise.all([
        api.get("/letterhead/templates"),
        api.get("/company/active").catch(() => ({ data: {} })),
      ]);
      setTemplates(tmplRes.data.items || []);
      setCompany(coRes.data || {});
    } catch {
      toast.error("Failed to load letterhead templates");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ── Seed defaults ─────────────────────────────────────────────────────────
  const seedDefaults = async () => {
    try {
      const res = await api.post("/letterhead/seed-defaults");
      toast.success(res.data.message);
      load();
    } catch {
      toast.error("Seed failed");
    }
  };

  // ── Open create ───────────────────────────────────────────────────────────
  const openCreate = () => {
    setForm({ ...EMPTY_TEMPLATE });
    setFormMode("create");
    setSelected(null);
    setFormOpen(true);
  };

  // ── Open edit ─────────────────────────────────────────────────────────────
  const openEdit = (tmpl) => {
    setForm({ ...EMPTY_TEMPLATE, ...tmpl });
    setFormMode("edit");
    setSelected(tmpl.id);
    setFormOpen(true);
  };

  // ── Save ──────────────────────────────────────────────────────────────────
  const saveForm = async () => {
    if (!form.template_name?.trim()) { toast.error("Template name is required"); return; }
    setSaving(true);
    try {
      // Send only the fields that belong to the template (exclude upload-only fields)
      const payload = { ...form, change_note: "Updated via designer" };
      if (formMode === "create") {
        await api.post("/letterhead/templates", payload);
        toast.success("Template created");
      } else {
        await api.put(`/letterhead/templates/${selected}`, payload);
        toast.success("Template saved");
      }
      setFormOpen(false);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  // ── Delete ────────────────────────────────────────────────────────────────
  const confirmDelete = async () => {
    setDeleting(true);
    try {
      await api.delete(`/letterhead/templates/${deleteId}`);
      toast.success("Template deleted");
      setDeleteId(null);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Delete failed");
    } finally {
      setDeleting(false);
    }
  };

  // ── Clone ─────────────────────────────────────────────────────────────────
  const clone = async (id) => {
    try {
      await api.post(`/letterhead/templates/${id}/clone`);
      toast.success("Template cloned");
      load();
    } catch { toast.error("Clone failed"); }
  };

  // ── Set default ───────────────────────────────────────────────────────────
  const setDefault = async (id) => {
    try {
      await api.post(`/letterhead/templates/${id}/set-default`);
      toast.success("Default template updated");
      load();
    } catch { toast.error("Failed"); }
  };

  // ── Preview PDF ───────────────────────────────────────────────────────────
  const previewPdf = async (id) => {
    setPreviewing(true);
    try {
      const res = await api.get(`/letterhead/templates/${id}/preview.pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch { toast.error("Preview failed"); }
    finally { setPreviewing(false); }
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FileText className="w-6 h-6 text-primary" /> Letterhead Designer
          </h1>
          <p className="text-muted-foreground text-sm mt-0.5">
            Design professional letterheads and assign them to any document type
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={seedDefaults}>
            <Layers className="w-4 h-4 mr-1.5" /> Seed 6 Themes
          </Button>
          <Button onClick={openCreate}>
            <Plus className="w-4 h-4 mr-1.5" /> New Template
          </Button>
        </div>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="flex items-center justify-center h-40">
          <div className="w-7 h-7 border-4 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : templates.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">
          <LayoutTemplate className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="text-lg font-medium mb-1">No templates yet</p>
          <p className="text-sm mb-4">
            Click <strong>Seed 6 Themes</strong> to get started with premium presets, or create your own.
          </p>
          <Button onClick={seedDefaults}><Layers className="w-4 h-4 mr-1.5" /> Seed 6 Themes</Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {templates.map(tmpl => {
            const theme = THEMES.find(t => t.key === tmpl.theme) || THEMES[0];
            const logoSrc = fileUrl(tmpl.logo_url);
            return (
              <div key={tmpl.id}
                className="rounded-xl border border-border overflow-hidden shadow-sm hover:shadow-md transition-shadow bg-card">
                {/* Theme bar */}
                <div className="h-1.5" style={{
                  background: `linear-gradient(90deg, ${tmpl.header_bg_color || theme.header}, ${tmpl.accent_color || theme.accent})`
                }} />
                <div className="p-4">
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div className="flex items-center gap-2 min-w-0">
                      {logoSrc && (
                        <img src={logoSrc} alt="logo"
                          className="h-7 w-auto max-w-[44px] object-contain rounded shrink-0" />
                      )}
                      <div className="min-w-0">
                        <p className="font-semibold leading-tight truncate">{tmpl.template_name}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {theme.label} · {(tmpl.page_size || "A4").replace(/_/g, " ")}
                        </p>
                      </div>
                    </div>
                    <StatusBadge tmpl={tmpl} />
                  </div>

                  {/* Colour swatches */}
                  <div className="flex gap-1 mb-3">
                    {[tmpl.primary_color, tmpl.secondary_color, tmpl.accent_color,
                      tmpl.header_bg_color, tmpl.footer_bg_color].map((c, i) => (
                      <span key={i} className="w-5 h-5 rounded-full border border-border"
                        style={{ background: c || "#ccc" }} title={c} />
                    ))}
                  </div>

                  {/* Applied-to tags */}
                  {(tmpl.applied_to || []).length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-3">
                      {tmpl.applied_to.slice(0, 3).map(dt => (
                        <span key={dt} className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                          {DOC_TYPE_LABELS[dt] || dt}
                        </span>
                      ))}
                      {tmpl.applied_to.length > 3 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                          +{tmpl.applied_to.length - 3} more
                        </span>
                      )}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex flex-wrap gap-1.5 pt-2 border-t border-border">
                    <Button size="sm" variant="outline" onClick={() => openEdit(tmpl)}>
                      <Settings className="w-3 h-3 mr-1" /> Edit
                    </Button>
                    <Button size="sm" variant="outline" disabled={previewing} onClick={() => previewPdf(tmpl.id)}>
                      <Eye className="w-3 h-3 mr-1" /> Preview
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => clone(tmpl.id)}>
                      <Copy className="w-3 h-3 mr-1" /> Clone
                    </Button>
                    {!tmpl.is_default && (
                      <Button size="sm" variant="outline" onClick={() => setDefault(tmpl.id)}>
                        <Star className="w-3 h-3 mr-1" /> Default
                      </Button>
                    )}
                    <Button size="sm" variant="outline"
                      onClick={() => { setPanelTmpl(tmpl); setAssignOpen(true); }}>
                      <FileText className="w-3 h-3 mr-1" /> Docs
                    </Button>
                    <Button size="sm" variant="outline"
                      onClick={() => { setPanelTmpl(tmpl); setHistoryOpen(true); }}>
                      <History className="w-3 h-3 mr-1" /> History
                    </Button>
                    {!tmpl.is_default && (
                      <Button size="sm" variant="outline"
                        className="text-destructive border-destructive/40 hover:bg-destructive/10"
                        onClick={() => setDeleteId(tmpl.id)}>
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Edit / Create modal ── */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="max-w-4xl max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {formMode === "create" ? "New Letterhead Template" : `Edit: ${form.template_name}`}
            </DialogTitle>
          </DialogHeader>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left: settings form */}
            <div className="overflow-y-auto max-h-[68vh] pr-2 space-y-0">
              <TemplateForm value={form} onChange={setForm} />

              {/* Logo / background uploads — only available after template is saved */}
              {formMode === "edit" && selected && (
                <div className="mt-5 space-y-4 pt-4 border-t border-border">
                  <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                    Images
                  </h3>
                  <div className="space-y-3">
                    <div>
                      <Label className="text-xs mb-1.5 block">Primary Logo</Label>
                      <UploadBtn
                        label="Primary Logo"
                        storedPath={form.logo_url}
                        apiPath={`/letterhead/templates/${selected}/upload-logo?slot=primary`}
                        onUploaded={path => setForm(f => ({ ...f, logo_url: path }))}
                      />
                    </div>
                    <div>
                      <Label className="text-xs mb-1.5 block">Secondary Logo (top-right)</Label>
                      <UploadBtn
                        label="Secondary Logo"
                        storedPath={form.logo2_url}
                        apiPath={`/letterhead/templates/${selected}/upload-logo?slot=secondary`}
                        onUploaded={path => setForm(f => ({ ...f, logo2_url: path }))}
                      />
                    </div>
                    <div>
                      <Label className="text-xs mb-1.5 block">Background Image (full page)</Label>
                      <UploadBtn
                        label="Background"
                        storedPath={form.background_image}
                        apiPath={`/letterhead/templates/${selected}/upload-background`}
                        onUploaded={path => setForm(f => ({ ...f, background_image: path }))}
                      />
                    </div>
                  </div>
                </div>
              )}

              {formMode === "create" && (
                <p className="text-xs text-muted-foreground mt-3 pt-3 border-t border-border">
                  Logo upload will be available after you create the template.
                </p>
              )}
            </div>

            {/* Right: live preview (updates as you change colours/theme) */}
            <div className="hidden lg:flex flex-col gap-3">
              <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
                Live Preview
              </p>
              <HeaderPreview tmpl={form} company={company} />

              {/* Drag & drop field placement */}
              <div className="mt-2 pt-4 border-t border-border">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
                    Drag &amp; Drop Fields
                  </p>
                  <div className="flex rounded-lg border border-border overflow-hidden text-xs">
                    {["header", "footer"].map(r => (
                      <button
                        key={r}
                        type="button"
                        onClick={() => setDndRegion(r)}
                        className={cn(
                          "px-3 py-1 capitalize transition-colors",
                          dndRegion === r ? "bg-primary text-primary-foreground" : "bg-card hover:bg-muted"
                        )}
                      >
                        {r}
                      </button>
                    ))}
                  </div>
                </div>
                <DragDropCanvas
                  pageSize={form.page_size}
                  company={company}
                  elements={dndRegion === "header" ? (form.header_elements || []) : (form.footer_elements || [])}
                  onChange={(els) =>
                    setForm(f => ({
                      ...f,
                      [dndRegion === "header" ? "header_elements" : "footer_elements"]: els,
                    }))
                  }
                />
              </div>
              <div className="p-3 rounded-lg bg-muted/40 text-xs text-muted-foreground space-y-1">
                <div><span className="font-medium">Page:</span> {(form.page_size || "A4").replace(/_/g, " ")}</div>
                <div>
                  <span className="font-medium">Header:</span> {form.header_height} mm ·{" "}
                  <span className="font-medium">Footer:</span> {form.footer_height} mm
                </div>
                <div>
                  <span className="font-medium">Margins:</span>{" "}
                  T{form.margin_top} B{form.margin_bottom} L{form.margin_left} R{form.margin_right}
                </div>
                {form.logo_url && (
                  <div className="text-green-600 font-medium">✓ Logo uploaded</div>
                )}
              </div>
            </div>
          </div>

          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => setFormOpen(false)}>Cancel</Button>
            <Button onClick={saveForm} disabled={saving}>
              {saving ? "Saving…" : formMode === "create" ? "Create Template" : "Save Changes"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Delete confirm ── */}
      <AlertDialog open={!!deleteId} onOpenChange={v => !v && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Template?</AlertDialogTitle>
            <AlertDialogDescription>
              This template will be soft-deleted and removed from the list.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} disabled={deleting}
              className="bg-destructive hover:bg-destructive/90">
              {deleting ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* ── Document assignment panel ── */}
      <Dialog open={assignOpen} onOpenChange={setAssignOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Assign to Documents — {panelTmpl?.template_name}</DialogTitle>
          </DialogHeader>
          {panelTmpl && (
            <DocAssignPanel
              templateId={panelTmpl.id}
              appliedTo={panelTmpl.applied_to || []}
              onSaved={newList => {
                setTemplates(ts => ts.map(t => t.id === panelTmpl.id ? { ...t, applied_to: newList } : t));
                setAssignOpen(false);
              }}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* ── Version history ── */}
      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Version History — {panelTmpl?.template_name}</DialogTitle>
          </DialogHeader>
          {panelTmpl && (
            <VersionHistoryPanel
              templateId={panelTmpl.id}
              onRestored={() => { setHistoryOpen(false); load(); }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
