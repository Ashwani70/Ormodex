import { useEffect, useState, useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Field, Select, EmptyState,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import CurrencySelect from "@/components/CurrencySelect";
import useOnline from "@/hooks/useOnline";
import { useAuth } from "@/context/AuthContext";
import { isAdminRole } from "@/lib/navItems";
import { CURRENCY_BY_CODE } from "@/config/currencies";
import { Plus, Pencil, Trash2, Search, X, PenLine, Package } from "lucide-react";

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
  const { user } = useAuth();
  const isAdmin = isAdminRole(user?.role);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refData, setRefData] = useState({});
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({});
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);

  // Seed the in-page filter from `?q=` so a deep-link from the global Ctrl+K
  // search (e.g. clicking a Ledger record) lands here pre-filtered to it.
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("q") || "");
  useEffect(() => { setSearch(searchParams.get("q") || ""); }, [searchParams]);

  const onSearchChange = (v) => {
    setSearch(v);
    // Keep the URL in sync (without stacking history) so the filter is shareable.
    const next = new URLSearchParams(searchParams);
    if (v) next.set("q", v); else next.delete("q");
    setSearchParams(next, { replace: true });
  };

  // Client-side filter across every configured column's raw value.
  const visibleItems = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return items;
    return items.filter((row) =>
      config.columns.some((c) => String(row[c.key] ?? "").toLowerCase().includes(term))
    );
  }, [items, search, config.columns]);

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
      // Tolerate both shapes: a bare array (default) or the paginated envelope
      // {items,total,...} returned when page/limit are requested.
      const rows = Array.isArray(r.data) ? r.data : (r.data?.items ?? []);
      setItems(rows);
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

  // Auto-open detail modal when navigated here via ?detail=<id> (e.g. from Ctrl+K search).
  useEffect(() => {
    const detailId = searchParams.get("detail");
    if (!detailId || items.length === 0) return;
    const record = items.find((r) => r.id === detailId);
    if (record) {
      startEdit(record);
      const next = new URLSearchParams(searchParams);
      next.delete("detail");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, items]); // eslint-disable-line react-hooks/exhaustive-deps

  const refLabel = (sourceKey, id) => {
    const row = (refData[sourceKey] || []).find((r) => r.id === id);
    if (!row) return "—";
    return row.name || row.symbol || row.iso_code || row.id;
  };

  const startNew = () => { setForm(blank()); setEditingId(null); setOpen(true); };
  const startEdit = (row) => {
    const o = blank();
    for (const f of config.fields) {
      if (row[f.key] != null) o[f.key] = row[f.key];
      // Restore manual mode: if no ref id but a manual text exists, switch to manual
      if (f.manualToggle && f.manualKey) {
        if (row[f.manualKey] && !row[f.key]) {
          o[`_manual_${f.key}`] = true;
          o[f.manualKey] = row[f.manualKey];
        } else if (row[f.manualKey]) {
          o[f.manualKey] = row[f.manualKey];
        }
      }
    }
    setForm(o); setEditingId(row.id); setOpen(true);
  };

  const setField = (key, val) => setForm((f) => ({ ...f, [key]: val }));

  // Currency picker: selecting an ISO currency auto-fills the related fields.
  // `field.fills` maps catalogue keys → form field keys (defaults to the
  // currency master's own field names) so the same picker can be reused.
  const applyCurrency = (field, c) => {
    const map = field.fills || {
      code: "iso_code", symbol: "symbol", name: "formal_name", decimals: "decimal_places",
    };
    setForm((f) => ({
      ...f,
      [map.code]: c.code,
      [map.symbol]: c.symbol,
      [map.name]: c.name,
      [map.decimals]: c.decimals,
    }));
  };

  const validate = () => {
    for (const f of config.fields) {
      if (f.hidden?.(form)) continue;
      if (f.required && (form[f.key] === "" || form[f.key] == null)) {
        toast.warning(`${f.label} is required.`); return false;
      }
      // Non-negative integer guard (e.g. Decimal Places). Backend enforces this
      // too; this is just earlier, friendlier feedback.
      if (f.nonNegativeInt && form[f.key] !== "" && form[f.key] != null) {
        const n = Number(form[f.key]);
        if (!Number.isInteger(n) || n < 0) {
          toast.warning(`${f.label} must be a non-negative whole number.`); return false;
        }
      }
      // Duplicate-code guard against the rows already loaded (e.g. ISO Code).
      if (f.unique && form[f.key]) {
        const val = String(form[f.key]).trim().toLowerCase();
        const clash = items.some(
          (r) => r.id !== editingId && String(r[f.key] ?? "").trim().toLowerCase() === val
        );
        if (clash) { toast.warning(`${f.label} "${form[f.key]}" already exists.`); return false; }
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
      const isManual = f.manualToggle && !!form[`_manual_${f.key}`];
      if (f.manualToggle && isManual) {
        // Manual mode: clear the ref id, store the typed name
        payload[f.key] = null;
        if (f.manualKey) payload[f.manualKey] = form[f.manualKey] || null;
      } else {
        let v = form[f.key];
        if (f.type === "number") v = v === "" ? null : parseFloat(v);
        if (v === "" && !f.required) v = null;
        payload[f.key] = v;
        // Clear the manual text when using picker
        if (f.manualKey) payload[f.manualKey] = null;
      }
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
    // Read-only fields are locked unless the user is an admin (requirement 6).
    const locked = !!f.readOnly && !isAdmin;
    const common = {
      value: form[f.key] ?? "",
      onChange: (e) => setField(f.key, e.target.value),
      disabled: locked,
    };
    let control;
    if (f.type === "checkbox") {
      control = (
        <label className="flex items-center gap-2 cursor-pointer h-10">
          <input type="checkbox" className="accent-primary w-4 h-4" disabled={locked}
            checked={!!form[f.key]} onChange={(e) => setField(f.key, e.target.checked)}
            data-testid={`master-field-${f.key}`} />
          <span className="text-sm text-muted-foreground">{f.label}</span>
        </label>
      );
      return <div key={f.key}>{control}</div>;
    } else if (f.type === "currency-picker") {
      control = (
        <CurrencySelect
          value={form[f.key]}
          onSelect={(c) => applyCurrency(f, c)}
          disabled={locked}
          testid={`master-field-${f.key}`}
        />
      );
    } else if (f.type === "select") {
      control = (
        <Select {...common} data-testid={`master-field-${f.key}`}>
          <option value="">— Select —</option>
          {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </Select>
      );
    } else if (f.type === "ref") {
      const rows = refData[f.ref] || [];
      const isManual = f.manualToggle && !!form[`_manual_${f.key}`];
      const toggleManualMode = () => {
        setForm((prev) => ({
          ...prev,
          [`_manual_${f.key}`]: !prev[`_manual_${f.key}`],
          [f.key]: "",
          ...(f.manualKey ? { [f.manualKey]: "" } : {}),
        }));
      };
      if (f.manualToggle) {
        control = (
          <div className="flex gap-1.5 items-center">
            <button
              type="button"
              onClick={toggleManualMode}
              title={isManual ? "Switch to picker" : "Enter manually"}
              className={`flex-shrink-0 w-8 h-10 border flex items-center justify-center transition-colors ${
                isManual
                  ? "border-amber-500 text-amber-400 bg-amber-500/10"
                  : "border-border text-muted-foreground hover:border-primary hover:text-primary"
              }`}
            >
              {isManual ? <PenLine className="w-3.5 h-3.5" /> : <Package className="w-3.5 h-3.5" />}
            </button>
            {isManual ? (
              <Input
                type="text"
                value={form[f.manualKey] ?? ""}
                onChange={(e) => setField(f.manualKey, e.target.value)}
                placeholder={f.manualPlaceholder || "Enter name…"}
                disabled={locked}
                data-testid={`master-field-${f.key}-manual`}
                className="flex-1"
              />
            ) : (
              <Select {...common} data-testid={`master-field-${f.key}`} className="flex-1">
                <option value="">— {f.placeholder || "Select"} —</option>
                {rows.filter((r) => r.id !== editingId).map((r) => {
                  const label = f.renderOption ? f.renderOption(r) : (r.name || r.symbol || r.iso_code || r.id);
                  return <option key={r.id} value={r.id}>{label}</option>;
                })}
              </Select>
            )}
          </div>
        );
      } else {
        control = (
          <Select {...common} data-testid={`master-field-${f.key}`}>
            <option value="">— {f.placeholder || "Select"} —</option>
            {rows.filter((r) => r.id !== editingId).map((r) => {
              const label = f.renderOption ? f.renderOption(r) : (r.name || r.symbol || r.iso_code || r.id);
              return <option key={r.id} value={r.id}>{label}</option>;
            })}
          </Select>
        );
      }
    } else if (f.type === "number") {
      control = <Input type="text" inputMode="decimal" step={f.step || "any"} {...common} data-testid={`master-field-${f.key}`} />;
    } else if (f.type === "date") {
      control = <Input type="date" {...common} data-testid={`master-field-${f.key}`} />;
    } else {
      control = <Input type="text" {...common} placeholder={f.placeholder} data-testid={`master-field-${f.key}`} />;
    }
    // Hint that read-only fields are auto-filled and admin-only to override.
    const hint = locked && f.readOnly
      ? "Auto-filled from the selected currency · admin only to edit"
      : f.hint;
    return (
      <div key={f.key} className={f.fullWidth ? "md:col-span-2" : ""}>
        <Field label={f.label} required={f.required} hint={hint}>{control}</Field>
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

      <div className="relative mb-3 max-w-sm">
        <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
        <input
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder={`Search ${config.title.toLowerCase()}…`}
          data-testid="master-search"
          className="w-full bg-background border border-input text-foreground text-sm pl-8 pr-8 py-2 focus:border-primary focus:outline-none transition-colors"
          style={{ borderRadius: "var(--radius)" }}
        />
        {search && (
          <button onClick={() => onSearchChange("")} title="Clear"
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {loading ? (
        <div className="text-muted-foreground font-mono text-sm py-8 text-center">Loading…</div>
      ) : items.length === 0 ? (
        <EmptyState message={`No ${config.title.toLowerCase()} yet`} />
      ) : visibleItems.length === 0 ? (
        <EmptyState message={`No ${config.title.toLowerCase()} match "${search}"`} />
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
              {visibleItems.map((row) => (
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
