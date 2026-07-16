import { useEffect, useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
  Field,
  EmptyState,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { Plus, Pencil, Trash2, MapPin, Search, RefreshCw, AlertTriangle } from "lucide-react";

const blank = { name: "", location: "", manager: "" };

export default function Warehouses() {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  // Explicit request lifecycle so we never show the empty state on failure and
  // always surface the real backend error (no generic "Something went wrong").
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async (q = "") => {
    setLoading(true);
    setLoadError(null);
    try {
      const r = await api.get("/warehouses", { params: q ? { q } : undefined });
      setItems(Array.isArray(r.data) ? r.data : (r.data?.items ?? []));
    } catch (e) {
      // Surface the actual backend detail (status + message) and log the full
      // error to the console for debugging — do not hide it.
      const detail = formatApiErrorDetail(e.response?.data?.detail) || e.message;
      const status = e.response?.status;
       
      console.error("[Warehouses] GET /warehouses failed:", status, detail, e);
      setLoadError(status ? `Error ${status}: ${detail}` : detail);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Debounced server-side search.
  useEffect(() => {
    const t = setTimeout(() => load(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search, load]);

  const startNew = () => {
    setForm(blank);
    setEditingId(null);
    setOpen(true);
  };
  const startEdit = (item) => {
    setForm({ ...blank, ...item });
    setEditingId(item.id);
    setOpen(true);
  };
  const submit = async (e) => {
    e.preventDefault();
    if (saving) return;               // guard against double-submit
    setSaving(true);
    try {
      if (editingId) await api.put(`/warehouses/${editingId}`, form);
      else await api.post("/warehouses", form);
      toast.success(editingId ? "Warehouse updated" : "Warehouse created");
      setOpen(false);
      load(search.trim());
    } catch (err) {
      const detail = formatApiErrorDetail(err.response?.data?.detail) || err.message;
       
      console.error("[Warehouses] save failed:", err.response?.status, detail, err);
      toast.error(detail);
    } finally {
      setSaving(false);
    }
  };
  const onDelete = async (item) => {
    if (!window.confirm(`Delete ${item.name}?`)) return;
    try {
      await api.delete(`/warehouses/${item.id}`);
      toast.success("Warehouse deleted");
      load(search.trim());
    } catch (err) {
      const detail = formatApiErrorDetail(err.response?.data?.detail) || err.message;
       
      console.error("[Warehouses] delete failed:", err.response?.status, detail, err);
      toast.error(detail);
    }
  };

  // Enter-as-Tab across the modal form; Ctrl+Enter/Ctrl+S saves, Esc cancels,
  // first field auto-focuses when the modal opens.
  const formRef = useRef(null);
  useEnterNavigation(formRef, {
    enabled: open,
    autoFocus: true,
    onSave: () => submit(new Event("submit", { cancelable: true })),
    onCancel: () => setOpen(false),
  });

  useModuleShortcuts({
    onNew: () => { if (!open) startNew(); },
  });

  return (
    <div data-testid="warehouses-page">
      <PageHeader
        eyebrow="Inventory"
        title="Warehouses"
        description="Storage locations and yard managers"
        actions={
          <div className="flex items-center gap-2">
            <SecondaryButton
              onClick={() => load(search.trim())}
              icon={RefreshCw}
              disabled={loading}
              title="Refresh"
            >
              Refresh
            </SecondaryButton>
            <PrimaryButton testid="new-warehouse" onClick={startNew} icon={Plus}>
              New warehouse
            </PrimaryButton>
          </div>
        }
      />

      {/* Search */}
      <div className="relative max-w-sm mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          data-testid="warehouse-search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search name, location, or manager…"
          className="pl-9"
        />
      </div>

      {loading ? (
        // Loading state — never show the empty state while a request is in flight.
        <div className="flex items-center justify-center py-16" data-testid="warehouses-loading">
          <div className="w-7 h-7 border-4 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : loadError ? (
        // Real backend error — shown instead of a generic message; retry re-fetches.
        <div
          data-testid="warehouses-error"
          className="border border-red-800/60 bg-red-950/30 rounded-lg p-6 flex flex-col items-center text-center gap-3"
        >
          <AlertTriangle className="w-8 h-8 text-red-400" />
          <div className="font-semibold text-red-200">Couldn’t load warehouses</div>
          <div className="text-sm text-red-300/90 font-mono max-w-lg break-words">{loadError}</div>
          <SecondaryButton onClick={() => load(search.trim())} icon={RefreshCw}>
            Retry
          </SecondaryButton>
        </div>
      ) : items.length === 0 ? (
        // Empty state — ONLY reached when the API succeeded and returned no rows.
        <EmptyState
          message={search ? `No warehouses match “${search}”` : "No warehouses yet"}
          action={
            !search && (
              <PrimaryButton onClick={startNew} icon={Plus}>
                Add warehouse
              </PrimaryButton>
            )
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {items.map((w) => (
            <div
              key={w.id}
              data-testid={`warehouse-card-${w.id}`}
              className="industrial-corner border border-zinc-800 bg-zinc-900 p-5 hover:border-yellow-400 transition-colors"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="font-display font-bold text-white text-lg">
                    {w.name}
                  </div>
                  <div className="flex items-center gap-1.5 mt-1 text-xs text-zinc-400">
                    <MapPin className="w-3 h-3 text-yellow-400" />
                    {w.location}
                  </div>
                </div>
              </div>
              <div className="border-t border-zinc-800 pt-3 flex items-center justify-between">
                <div>
                  <div className="label-overline">Yard Manager</div>
                  <div className="text-sm text-white mt-0.5">
                    {w.manager || "—"}
                  </div>
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={() => startEdit(w)}
                    className="w-7 h-7 border border-zinc-800 hover:border-yellow-400 hover:text-yellow-400 text-zinc-400 flex items-center justify-center"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => onDelete(w)}
                    className="w-7 h-7 border border-zinc-800 hover:border-red-500 hover:text-red-400 text-zinc-400 flex items-center justify-center"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editingId ? "Edit Warehouse" : "New Warehouse"}
        size="md"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-warehouse" disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </PrimaryButton>
          </>
        }
      >
        <form ref={formRef} onSubmit={submit} className="space-y-3">
          <Field label="Name" required>
            <Input
              required
              data-testid="form-wh-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Location" required>
            <Input
              required
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
            />
          </Field>
          <Field label="Manager">
            <Input
              value={form.manager || ""}
              onChange={(e) => setForm({ ...form, manager: e.target.value })}
            />
          </Field>
        </form>
      </Modal>
    </div>
  );
}
