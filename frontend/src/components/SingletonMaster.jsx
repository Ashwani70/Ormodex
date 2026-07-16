import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import { PageHeader, PrimaryButton, Input, Field, Select } from "@/components/ui-kit";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";

/**
 * Statutory-details singleton screen: one document per tenant, get + upsert only.
 * No list, no delete — loads the tenant's doc and saves it back via PUT.
 *
 * config = { title, eyebrow, description, endpoint, fields:[{key,label,type,options?}] }
 */
export default function SingletonMaster({ config }) {
  const online = useOnline();
  const [form, setForm] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const blank = useCallback(() => {
    const o = {};
    for (const f of config.fields) o[f.key] = f.type === "checkbox" ? false : "";
    return o;
  }, [config]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(config.endpoint);
      const o = blank();
      for (const f of config.fields) if (r.data?.[f.key] != null) o[f.key] = r.data[f.key];
      setForm(o);
    } catch (e) {
      toast.error("Failed to load " + config.title);
      setForm(blank());
    } finally {
      setLoading(false);
    }
  }, [config.endpoint, config.title, config.fields, blank]);

  useEffect(() => { load(); }, [load]);

  const setField = (key, val) => setForm((f) => ({ ...f, [key]: val }));

  const save = async (e) => {
    e?.preventDefault?.();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    const payload = {};
    for (const f of config.fields) {
      let v = form[f.key];
      if (f.type === "number") v = v === "" ? null : parseFloat(v);
      payload[f.key] = v;
    }
    setSaving(true);
    try {
      await api.put(config.endpoint, payload);
      toast.success("Saved");
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const renderInput = (f) => {
    if (f.type === "checkbox") {
      return (
        <div key={f.key}>
          <label className="flex items-center gap-2 cursor-pointer h-10">
            <input type="checkbox" className="accent-primary w-4 h-4"
              checked={!!form[f.key]} onChange={(e) => setField(f.key, e.target.checked)}
              data-testid={`singleton-field-${f.key}`} />
            <span className="text-sm text-muted-foreground">{f.label}</span>
          </label>
        </div>
      );
    }
    const common = { value: form[f.key] ?? "", onChange: (e) => setField(f.key, e.target.value) };
    let control;
    if (f.type === "select") {
      control = (
        <Select {...common} data-testid={`singleton-field-${f.key}`}>
          <option value="">— Select —</option>
          {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </Select>
      );
    } else if (f.type === "date") {
      control = <Input type="date" {...common} data-testid={`singleton-field-${f.key}`} />;
    } else if (f.type === "number") {
      control = <Input type="text" inputMode="decimal" step="any" {...common} data-testid={`singleton-field-${f.key}`} />;
    } else {
      control = <Input type="text" {...common} data-testid={`singleton-field-${f.key}`} />;
    }
    return <div key={f.key}><Field label={f.label}>{control}</Field></div>;
  };

  return (
    <div data-testid={`singleton-${config.endpoint.split("/").pop()}-page`}>
      <PageHeader eyebrow={config.eyebrow} title={config.title} description={config.description}
        actions={
          <PrimaryButton testid="singleton-save" disabled={!online || saving || loading} onClick={save}>
            {saving ? "Saving…" : "Save"}
          </PrimaryButton>
        }
      />
      <OfflineBanner online={online} />

      {loading ? (
        <div className="text-muted-foreground font-mono text-sm py-8 text-center">Loading…</div>
      ) : (
        <form onSubmit={save} className="bg-card border border-border p-5 grid grid-cols-1 md:grid-cols-2 gap-3"
          style={{ borderRadius: "var(--radius)" }}>
          {config.fields.map(renderInput)}
        </form>
      )}
    </div>
  );
}
