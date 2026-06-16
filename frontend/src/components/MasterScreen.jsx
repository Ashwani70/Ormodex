import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Field, Select, EmptyState,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";
import { Plus, Pencil, Trash2 } from "lucide-react";

/**
 * Generic, config-driven master screen (list + create/edit modal + soft-delete).
 * One component renders all 10 masters from a `config` describing fields/columns,
 * matching the repo's existing screen conventions (ui-kit, sonner, dark theme).
 *
 * config = {
 *   title, eyebrow, description, endpoint (e.g. "/masters/groups"),
 *   columns: [{ key, label, render? }],
 *   fields:  [{ key, label, type, required?, options?, ref?, dependsOnType?, ... }],
 *   refSources: { sourceKey: "/masters/units" },   // loaded for ref + select rendering
 * }
 */
export default function MasterScreen({ config }) {
  const online = useOnline();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refData, setRefData] = useState({});
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({});
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);

  const blank = useCallback(() => {
    const o = {};
    for (const f of config.fields) {
      o[f.key] = f.default ?? (f.type === "checkbox" ? false : f.type === "number" ? 0 : "");
    }
    return o;
  }, [config]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(config.endpoint);
      setItems(Array.isArray(r.data) ? r.data : []);
    } catch (e) {
      toast.error("Failed to load " + config.title);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [config.endpoint, config.title]);

  const loadRefs = useCallback(async () => {
    const sources = config.refSources || {};
    const entries = await Promise.all(
      Object.entries(sources).map(async ([k, url]) => {
        try { return [k, (await api.get(url)).data]; }
        catch { return [k, []]; }
      })
    );
    setRefData(Object.fromEntries(entries));
  }, [config.refSources]);

  useEffect(() => { load(); loadRefs(); }, [load, loadRefs]);

  const refLabel = (sourceKey, id) => {
    const row = (refData[sourceKey] || []).find((r) => r.id === id);
    if (!row) return "—";
    return row.name || row.symbol || row.iso_code || row.id;
  };

  const startNew = () => { setForm(blank()); setEditingId(null); setOpen(true); };
  const startEdit = (row) => {
    const o = blank();
    for (const f of config.fields) if (row[f.key] != null) o[f.key] = row[f.key];
    setForm(o); setEditingId(row.id); setOpen(true);
  };

  const setField = (key, val) => setForm((f) => ({ ...f, [key]: val }));

  const validate = () => {
    for (const f of config.fields) {
      if (f.hidden?.(form)) continue;
      if (f.required && (form[f.key] === "" || form[f.key] == null)) {
        toast.warning(`${f.label} is required.`); return false;
      }
    }
    return true;
  };

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    if (!validate()) return;
    // Build payload, coercing numbers and dropping hidden fields.
    const payload = {};
    for (const f of config.fields) {
      if (f.hidden?.(form)) continue;
      let v = form[f.key];
      if (f.type === "number") v = v === "" ? null : parseFloat(v);
      if (v === "" && !f.required) v = null;
      payload[f.key] = v;
    }
    setSaving(true);
    try {
      if (editingId) await api.put(`${config.endpoint}/${editingId}`, payload);
      else await api.post(config.endpoint, payload);
      toast.success("Saved");
      setOpen(false);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async (row) => {
    if (!online) return toast.warning("You are offline — deleting is disabled.");
    if (!window.confirm(`Delete ${row.name || row.symbol || "this record"}?`)) return;
    try {
      await api.delete(`${config.endpoint}/${row.id}`);
      toast.success("Deleted");
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  const renderCell = (row, col) => {
    if (col.render) return col.render(row, { refLabel });
    const v = row[col.key];
    if (typeof v === "boolean") return v ? "Yes" : "—";
    return v ?? "—";
  };

  const renderInput = (f) => {
    if (f.hidden?.(form)) return null;
    const common = { value: form[f.key] ?? "", onChange: (e) => setField(f.key, e.target.value) };
    let control;
    if (f.type === "checkbox") {
      control = (
        <label className="flex items-center gap-2 cursor-pointer h-10">
          <input type="checkbox" className="accent-primary w-4 h-4"
            checked={!!form[f.key]} onChange={(e) => setField(f.key, e.target.checked)}
            data-testid={`master-field-${f.key}`} />
          <span className="text-sm text-muted-foreground">{f.label}</span>
        </label>
      );
      return <div key={f.key}>{control}</div>;
    } else if (f.type === "select") {
      control = (
        <Select {...common} data-testid={`master-field-${f.key}`}>
          <option value="">— Select —</option>
          {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </Select>
      );
    } else if (f.type === "ref") {
      const rows = refData[f.ref] || [];
      control = (
        <Select {...common} data-testid={`master-field-${f.key}`}>
          <option value="">— {f.placeholder || "Select"} —</option>
          {rows.filter((r) => r.id !== editingId).map((r) => (
            <option key={r.id} value={r.id}>{r.name || r.symbol || r.iso_code || r.id}</option>
          ))}
        </Select>
      );
    } else if (f.type === "number") {
      control = <Input type="number" step={f.step || "any"} {...common} data-testid={`master-field-${f.key}`} />;
    } else if (f.type === "date") {
      control = <Input type="date" {...common} data-testid={`master-field-${f.key}`} />;
    } else {
      control = <Input type="text" {...common} placeholder={f.placeholder} data-testid={`master-field-${f.key}`} />;
    }
    return (
      <div key={f.key} className={f.fullWidth ? "md:col-span-2" : ""}>
        <Field label={f.label} required={f.required}>{control}</Field>
      </div>
    );
  };

  return (
    <div data-testid={`master-${config.endpoint.split("/").pop()}-page`}>
      <PageHeader
        eyebrow={config.eyebrow}
        title={config.title}
        description={config.description}
        actions={
          <PrimaryButton testid="master-new" icon={Plus} disabled={!online} onClick={startNew}>
            New
          </PrimaryButton>
        }
      />
      <OfflineBanner online={online} />

      {loading ? (
        <div className="text-muted-foreground font-mono text-sm py-8 text-center">Loading…</div>
      ) : items.length === 0 ? (
        <EmptyState message={`No ${config.title.toLowerCase()} yet`} />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm font-mono text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="border-b border-border label-overline">
                {config.columns.map((c) => <th key={c.key} className="px-3 py-2.5">{c.label}</th>)}
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id} data-testid={`master-row-${row.id}`} className="border-b border-border hover:bg-muted/40 text-foreground">
                  {config.columns.map((c) => (
                    <td key={c.key} className="px-3 py-2.5 text-foreground">{renderCell(row, c)}</td>
                  ))}
                  <td className="px-3 py-2.5 text-right">
                    <div className="inline-flex gap-1">
                      <button onClick={() => startEdit(row)}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground flex items-center justify-center">
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => onDelete(row)}
                        className="w-7 h-7 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground flex items-center justify-center">
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

      <Modal open={open} onClose={() => setOpen(false)} title={`${editingId ? "Edit" : "New"} ${config.singular || config.title}`} size="lg"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} testid="master-save" disabled={!online || saving}>
              {saving ? "Saving…" : "Save"}
            </PrimaryButton>
          </>
        }>
        <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {config.fields.map(renderInput)}
        </form>
      </Modal>
    </div>
  );
}
