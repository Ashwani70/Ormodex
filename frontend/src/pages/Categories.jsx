import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  PageHeader, PrimaryButton, SecondaryButton, Input, Textarea, Field, Select, EmptyState, StatusBadge,
} from "@/components/ui-kit";
import Modal from "@/components/Modal";
import OfflineBanner from "@/components/OfflineBanner";
import useOnline from "@/hooks/useOnline";
import useEnterNavigation from "@/hooks/useEnterNavigation";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { useAuth } from "@/context/AuthContext";
import { isAdminRole } from "@/lib/navItems";
import {
  Plus, Pencil, Trash2, Search, X, Upload, Download, ArrowUpDown, AlertTriangle, RefreshCw,
} from "lucide-react";

const blank = () => ({
  name: "", code: "", description: "", parent_id: "", status: "Active", display_order: 0,
});

const SORTS = [
  { value: "display_order", label: "Display Order" },
  { value: "name", label: "Name" },
  { value: "code", label: "Code" },
  { value: "created_at", label: "Created" },
];

export default function Categories() {
  const online = useOnline();
  const { user } = useAuth();
  const isAdmin = isAdminRole(user?.role);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("display_order");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank());
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const c = await api.get("/categories", { params: { sort } });
      setItems(c.data);
    } catch (err) {
      const detail = formatApiErrorDetail(err.response?.data?.detail) || err.message;
      setLoadError(detail);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [sort]);

  useEffect(() => { load(); }, [load]);

  const nameById = useCallback(
    (id) => items.find((c) => c.id === id)?.name || "—",
    [items]
  );

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return items;
    return items.filter((r) =>
      [r.name, r.code, r.description].some((v) => String(v ?? "").toLowerCase().includes(term))
    );
  }, [items, search]);

  // ── Multi-select / bulk delete ───────────────────────────────────────────
  // Keep the selection in sync with what's actually on screen: anything filtered
  // out (or removed after a reload) drops out of the selection so the action bar
  // count and "select all" checkbox never reference rows the user can't see.
  const visibleIds = useMemo(() => visible.map((r) => r.id), [visible]);
  useEffect(() => {
    setSelectedIds((prev) => {
      const next = new Set();
      for (const id of visibleIds) if (prev.has(id)) next.add(id);
      return next.size === prev.size ? prev : next;
    });
  }, [visibleIds]);

  const selectedCount = selectedIds.size;
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));

  const toggleOne = (id) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const toggleAllVisible = () =>
    setSelectedIds((prev) => {
      if (visibleIds.every((id) => prev.has(id))) return new Set(); // unselect all
      return new Set(visibleIds);
    });

  const clearSelection = () => setSelectedIds(new Set());

  const onBulkDelete = async () => {
    if (!online) return toast.warning("You are offline — deleting is disabled.");
    if (selectedCount === 0) return;
    const ids = visibleIds.filter((id) => selectedIds.has(id));
    const rows = items.filter((r) => ids.includes(r.id));
    const linkedTotal = rows.reduce((n, r) => n + (r.product_count ?? 0), 0);

    const msg =
      `Delete ${ids.length} categor${ids.length === 1 ? "y" : "ies"}?` +
      (linkedTotal > 0
        ? `\n\n${linkedTotal} linked product(s) across the selection will be ` +
          `unlinked (they stay in the catalog but lose their category).`
        : "");
    if (!window.confirm(msg)) return;

    setBulkDeleting(true);
    try {
      // force: true so linked categories don't block the batch — the confirm
      // above already warned about unlinking. Categories with sub-categories
      // still come back as failures and are reported per-id.
      const { data } = await api.post("/categories/bulk-delete", { ids, force: true });
      if (data.deleted > 0) {
        toast.success(
          `Deleted ${data.deleted} categor${data.deleted === 1 ? "y" : "ies"}` +
          (data.unlinked_products ? ` — ${data.unlinked_products} product(s) unlinked` : "")
        );
      }
      if (data.failed > 0) {
        const firstErr = (data.results || []).find((r) => !r.ok)?.error;
        toast.warning(
          `${data.failed} could not be deleted` + (firstErr ? `: ${formatApiErrorDetail(firstErr)}` : ".")
        );
      }
      clearSelection();
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Bulk delete failed");
    } finally {
      setBulkDeleting(false);
    }
  };

  const startNew = (presetName = "") => {
    setForm({ ...blank(), name: presetName, display_order: items.length });
    setEditingId(null);
    setOpen(true);
  };
  const startEdit = (row) => {
    setForm({
      name: row.name || "", code: row.code || "", description: row.description || "",
      parent_id: row.parent_id || "", status: row.status || "Active",
      display_order: row.display_order ?? 0,
    });
    setEditingId(row.id);
    setOpen(true);
  };

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!online) return toast.warning("You are offline — saving is disabled.");
    if (!form.name.trim()) return toast.warning("Category name is required.");
    const payload = {
      ...form,
      name: form.name.trim(),
      code: form.code.trim() || null,
      description: form.description.trim() || null,
      parent_id: form.parent_id || null,
      display_order: Number(form.display_order) || 0,
    };
    setSaving(true);
    try {
      if (editingId) await api.put(`/categories/${editingId}`, payload);
      else await api.post("/categories", payload);
      toast.success("Category saved");
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
    const linked = row.product_count ?? 0;
    // When products are linked, ask up front whether to unlink + delete (force).
    if (linked > 0) {
      const proceed = window.confirm(
        `"${row.name}" has ${linked} linked product(s).\n\n` +
        `Delete the category and remove it from those products? ` +
        `The products stay in the catalog but will have no category.`
      );
      if (!proceed) return;
      try {
        const { data } = await api.delete(`/categories/${row.id}`, { params: { force: true } });
        toast.success(`Category deleted — ${data.unlinked_products || 0} product(s) unlinked`);
        load();
      } catch (err) {
        toast.error(formatApiErrorDetail(err.response?.data?.detail));
      }
      return;
    }
    if (!window.confirm(`Delete category "${row.name}"?`)) return;
    try {
      await api.delete(`/categories/${row.id}`);
      toast.success("Category deleted");
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
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
    onNew: () => { if (!open && online) startNew(); },
  });

  const onImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/categories/import", fd, {
        params: { commit: true },
        headers: { "Content-Type": "multipart/form-data" },
      });
      if (data.committed > 0) toast.success(`Imported ${data.committed} categor${data.committed === 1 ? "y" : "ies"}.`);
      if (data.error_rows > 0) {
        toast.warning(`${data.error_rows} row(s) skipped (duplicates / missing name).`);
      }
      if (data.committed === 0 && data.error_rows === 0) toast.info("No new rows to import.");
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || "Import failed");
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const onExport = async () => {
    try {
      const resp = await api.get("/categories/export", { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([resp.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = "categories.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Export failed");
    }
  };

  return (
    <div data-testid="categories-page">
      <PageHeader
        eyebrow="Inventory"
        title="Categories"
        description="Manage product categories used across the catalog. Soft-deletes keep history; categories with linked products can't be deleted."
        actions={
          <div className="flex flex-wrap gap-2">
            <SecondaryButton icon={Download} onClick={onExport}>Export</SecondaryButton>
            <SecondaryButton icon={Upload} disabled={!online || importing}
              onClick={() => fileRef.current?.click()}>
              {importing ? "Importing…" : "Import"}
            </SecondaryButton>
            <input ref={fileRef} type="file" accept=".xlsx,.xlsm,.csv" className="hidden"
              data-testid="category-import-input" onChange={onImport} />
            <PrimaryButton testid="new-category" icon={Plus} disabled={!online} onClick={() => startNew()}>
              New category
            </PrimaryButton>
          </div>
        }
      />
      <OfflineBanner online={online} />

      {/* Search + sort */}
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search categories…"
            data-testid="category-search"
            className="w-full bg-background border border-input text-foreground text-sm pl-8 pr-8 py-2 focus:border-primary focus:outline-none transition-colors"
            style={{ borderRadius: "var(--radius)" }}
          />
          {search && (
            <button onClick={() => setSearch("")} title="Clear"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <ArrowUpDown className="w-3.5 h-3.5 text-muted-foreground" />
          <Select value={sort} onChange={(e) => setSort(e.target.value)} className="w-44" data-testid="category-sort">
            {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </Select>
        </div>
      </div>

      {/* Bulk-action bar — appears only when rows are selected (admin only) */}
      {isAdmin && selectedCount > 0 && (
        <div
          data-testid="category-bulk-bar"
          className="flex items-center justify-between gap-3 mb-3 px-3 py-2 border border-primary/30 bg-primary/5"
          style={{ borderRadius: "var(--radius)" }}
        >
          <span className="text-sm text-foreground">
            <strong className="tabular">{selectedCount}</strong> selected
          </span>
          <div className="flex items-center gap-2">
            <SecondaryButton onClick={clearSelection}>Clear</SecondaryButton>
            <button
              type="button"
              onClick={onBulkDelete}
              disabled={!online || bulkDeleting}
              data-testid="category-bulk-delete"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-semibold border border-red-500/40 text-red-500 hover:bg-red-500/10 disabled:opacity-40 transition-colors"
              style={{ borderRadius: "var(--radius)" }}
            >
              <Trash2 className="w-3.5 h-3.5" />
              {bulkDeleting ? "Deleting…" : `Delete ${selectedCount}`}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-muted-foreground font-mono text-sm py-8 text-center" data-testid="categories-loading">Loading…</div>
      ) : loadError ? (
        <div
          data-testid="categories-error"
          className="border border-red-800/60 bg-red-950/30 rounded-lg p-6 flex flex-col items-center text-center gap-3 my-4"
        >
          <AlertTriangle className="w-8 h-8 text-red-400" />
          <div className="font-semibold text-red-200">Couldn't load categories</div>
          <div className="text-sm text-red-300/90 font-mono max-w-lg break-words">{loadError}</div>
          <SecondaryButton onClick={load} icon={RefreshCw}>Retry</SecondaryButton>
        </div>
      ) : items.length === 0 ? (
        <EmptyState message="No categories yet"
          action={<PrimaryButton icon={Plus} onClick={() => startNew()}>Add first category</PrimaryButton>} />
      ) : visible.length === 0 ? (
        <EmptyState message={`No categories match "${search}"`} />
      ) : (
        <div className="border border-border bg-card overflow-x-auto" style={{ borderRadius: "var(--radius)" }}>
          <table className="w-full text-sm text-left">
            <thead className="bg-muted text-muted-foreground">
              <tr className="border-b border-border label-overline">
                {isAdmin && (
                  <th className="px-3 py-2.5 w-10">
                    <input
                      type="checkbox"
                      aria-label="Select all categories"
                      data-testid="category-select-all"
                      checked={allVisibleSelected}
                      ref={(el) => {
                        if (el) el.indeterminate = selectedCount > 0 && !allVisibleSelected;
                      }}
                      onChange={toggleAllVisible}
                      className="align-middle cursor-pointer accent-primary"
                    />
                  </th>
                )}
                <th className="px-3 py-2.5">Name</th>
                <th className="px-3 py-2.5">Code</th>
                <th className="px-3 py-2.5">Parent</th>
                <th className="px-3 py-2.5 text-right">Order</th>
                <th className="px-3 py-2.5 text-right">Products</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.id} data-testid={`category-row-${row.id}`}
                  className={`border-b border-border hover:bg-muted/40 text-foreground ${
                    selectedIds.has(row.id) ? "bg-primary/5" : ""
                  }`}>
                  {isAdmin && (
                    <td className="px-3 py-2.5 w-10">
                      <input
                        type="checkbox"
                        aria-label={`Select ${row.name}`}
                        data-testid={`category-select-${row.id}`}
                        checked={selectedIds.has(row.id)}
                        onChange={() => toggleOne(row.id)}
                        className="align-middle cursor-pointer accent-primary"
                      />
                    </td>
                  )}
                  <td className="px-3 py-2.5 font-semibold text-foreground">{row.name}</td>
                  <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">{row.code || "—"}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{row.parent_id ? nameById(row.parent_id) : "—"}</td>
                  <td className="px-3 py-2.5 text-right tabular text-muted-foreground">{row.display_order ?? 0}</td>
                  <td className="px-3 py-2.5 text-right tabular text-muted-foreground">{row.product_count ?? 0}</td>
                  <td className="px-3 py-2.5"><StatusBadge status={row.status} /></td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="inline-flex gap-1">
                      <button onClick={() => startEdit(row)} title="Edit"
                        data-testid={`category-edit-${row.id}`}
                        className="w-7 h-7 border border-border hover:border-primary hover:text-primary text-muted-foreground flex items-center justify-center">
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => onDelete(row)} title={isAdmin ? "Delete" : "Admin only"}
                        disabled={!isAdmin}
                        data-testid={`category-delete-${row.id}`}
                        className="w-7 h-7 border border-border hover:border-red-500 hover:text-red-400 text-muted-foreground flex items-center justify-center disabled:opacity-40">
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

      <Modal open={open} onClose={() => setOpen(false)}
        title={editingId ? "Edit Category" : "New Category"} size="lg" testid="category-modal"
        footer={
          <>
            <SecondaryButton onClick={() => setOpen(false)}>Cancel</SecondaryButton>
            <PrimaryButton onClick={submit} testid="save-category" disabled={!online || saving}>
              {saving ? "Saving…" : "Save"}
            </PrimaryButton>
          </>
        }>
        <form ref={formRef} onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field label="Category Name" required>
            <Input required data-testid="category-name" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Category Code" hint="Auto-generated if left blank">
            <Input data-testid="category-code" value={form.code} placeholder="Auto"
              onChange={(e) => setForm({ ...form, code: e.target.value })} />
          </Field>
          <Field label="Parent Category">
            <Select value={form.parent_id} data-testid="category-parent"
              onChange={(e) => setForm({ ...form, parent_id: e.target.value })}>
              <option value="">— None (top level) —</option>
              {items.filter((c) => c.id !== editingId).map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </Select>
          </Field>
          <Field label="Status">
            <Select value={form.status} data-testid="category-status"
              onChange={(e) => setForm({ ...form, status: e.target.value })}>
              <option value="Active">Active</option>
              <option value="Inactive">Inactive</option>
            </Select>
          </Field>
          <Field label="Display Order">
            <Input type="text" inputMode="decimal" step="1" data-testid="category-order" value={form.display_order}
              onChange={(e) => setForm({ ...form, display_order: e.target.value })} />
          </Field>
          <div className="md:col-span-2">
            <Field label="Description">
              <Textarea rows={2} value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
          </div>
        </form>
      </Modal>
    </div>
  );
}
