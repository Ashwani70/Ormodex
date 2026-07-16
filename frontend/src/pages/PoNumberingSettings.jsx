import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, PrimaryButton, Input, Field, Select,
} from "@/components/ui-kit";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { Hash, Wand2 } from "lucide-react";

const blank = () => ({
  mode: "AUTO",
  prefix: "PO",
  fy_format: "",
  branch_code: "",
  separator: "-",
  start_sequence: 1,
  sequence_length: 5,
});

// Mirror of core.po_numbering.build_po_number so the admin sees a live preview
// without a round-trip. Segment order: branch · prefix · FY · sequence.
function buildPreview(s) {
  const sep = s.separator ?? "-";
  const seqStr = String(s.start_sequence || 1).padStart(
    Math.max(1, Math.min(12, Number(s.sequence_length) || 5)), "0"
  );
  const segments = [s.branch_code, s.prefix, s.fy_format, seqStr]
    .map((x) => (x ?? "").toString().trim())
    .filter(Boolean);
  return sep ? segments.join(sep) : segments.join("");
}

export default function PoNumberingSettings() {
  const [form, setForm] = useState(blank());
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = () => {
    setLoading(true);
    setLoadError(null);
    api.get("/settings/po-numbering")
      .then(({ data }) => {
        // Keep only the template fields; drop server-side flags/metadata.
        const b = blank();
        setForm({
          ...b,
          ...Object.fromEntries(Object.keys(b).map((k) => [k, data[k] ?? b[k]])),
        });
      })
      .catch((err) => {
        // Surface the failure inline instead of leaving the page on "LOADING…".
        // (axios timeouts reject with no err.response, so fall back to err.message.)
        const msg = formatApiErrorDetail(err.response?.data?.detail) ||
          err.message || "Could not load settings.";
        setLoadError(msg);
        toast.error(msg);
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  const save = async (e) => {
    e?.preventDefault();
    setSaving(true);
    try {
      const body = {
        ...form,
        start_sequence: Number(form.start_sequence) || 1,
        sequence_length: Number(form.sequence_length) || 5,
      };
      await api.post("/settings/po-numbering", body);
      toast.success("PO numbering settings saved");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  // Enter-as-Tab across the whole form; Ctrl+Enter/Ctrl+S saves, first field
  // auto-focuses on mount. Always-visible settings page — no modal, so
  // `enabled` just tracks whether the form is actually on screen.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: !loading && !loadError,
    autoFocus: true,
    onSave: () => save(new Event("submit", { cancelable: true })),
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px] font-mono text-sm text-muted-foreground">
        LOADING SETTINGS...
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 min-h-[300px] text-center">
        <p className="font-mono text-sm text-destructive max-w-md">{loadError}</p>
        <PrimaryButton type="button" testid="retry-load-po-numbering" onClick={load}>
          Retry
        </PrimaryButton>
      </div>
    );
  }

  const isAuto = form.mode === "AUTO";

  return (
    <div data-testid="po-numbering-settings-page" className="space-y-6">
      <PageHeader
        eyebrow="Document Settings"
        title="Purchase Order Numbering"
        description="Choose how purchase order numbers are generated. Auto-generate builds numbers from a template; Manual lets permitted users enter their own."
      />

      <form ref={formRef} onSubmit={save} className="max-w-3xl space-y-6">
        {/* Mode */}
        <div className="border border-border bg-card p-5" style={{ borderRadius: "var(--radius)" }}>
          <div className="label-overline mb-3">Numbering Mode</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <button
              type="button"
              data-testid="mode-auto"
              onClick={() => set({ mode: "AUTO" })}
              className={`text-left p-4 border ${isAuto ? "border-primary ring-1 ring-primary" : "border-border"} bg-background`}
              style={{ borderRadius: "var(--radius)" }}
            >
              <div className="flex items-center gap-2 mb-1">
                <Wand2 className="w-4 h-4 text-primary" />
                <span className="font-bold text-sm text-foreground">Auto Generate</span>
              </div>
              <p className="text-xs text-muted-foreground">Server builds the next number from the template below.</p>
            </button>
            <button
              type="button"
              data-testid="mode-manual"
              onClick={() => set({ mode: "MANUAL" })}
              className={`text-left p-4 border ${!isAuto ? "border-primary ring-1 ring-primary" : "border-border"} bg-background`}
              style={{ borderRadius: "var(--radius)" }}
            >
              <div className="flex items-center gap-2 mb-1">
                <Hash className="w-4 h-4 text-primary" />
                <span className="font-bold text-sm text-foreground">Manual Entry</span>
              </div>
              <p className="text-xs text-muted-foreground">Permitted users type their own PO number (must be unique).</p>
            </button>
          </div>
        </div>

        {/* Auto configuration */}
        <div
          className={`border border-border bg-card p-5 space-y-4 ${isAuto ? "" : "opacity-50 pointer-events-none"}`}
          style={{ borderRadius: "var(--radius)" }}
        >
          <div className="label-overline">Auto-Generate Template</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <Field label="Prefix">
              <Input data-testid="po-num-prefix" value={form.prefix}
                onChange={(e) => set({ prefix: e.target.value })} placeholder="PO" />
            </Field>
            <Field label="Financial Year (e.g. 26-27)">
              <Input data-testid="po-num-fy" value={form.fy_format}
                onChange={(e) => set({ fy_format: e.target.value })} placeholder="26-27" />
            </Field>
            <Field label="Branch Code">
              <Input data-testid="po-num-branch" value={form.branch_code}
                onChange={(e) => set({ branch_code: e.target.value })} placeholder="DEL" />
            </Field>
            <Field label="Separator">
              <Select data-testid="po-num-sep" value={form.separator}
                onChange={(e) => set({ separator: e.target.value })}>
                <option value="-">Hyphen ( - )</option>
                <option value="/">Slash ( / )</option>
                <option value="">None</option>
              </Select>
            </Field>
            <Field label="Starting Sequence">
              <Input data-testid="po-num-start" type="text" inputMode="decimal" min="1" value={form.start_sequence}
                onChange={(e) => set({ start_sequence: e.target.value })} />
            </Field>
            <Field label="Sequence Length (leading zeros)">
              <Input data-testid="po-num-len" type="text" inputMode="decimal" min="1" max="12" value={form.sequence_length}
                onChange={(e) => set({ sequence_length: e.target.value })} />
            </Field>
          </div>

          <div className="flex items-center gap-2 pt-1 font-mono text-sm">
            <span className="text-muted-foreground">Preview:</span>
            <span data-testid="po-num-preview" className="font-bold text-primary">
              {buildPreview(form)}
            </span>
          </div>
        </div>

        <div className="flex justify-end">
          <PrimaryButton type="submit" testid="save-po-numbering" disabled={saving}>
            {saving ? "Saving..." : "Save Settings"}
          </PrimaryButton>
        </div>
      </form>
    </div>
  );
}
