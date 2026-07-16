import { useCallback, useMemo, useState } from "react";

/**
 * Multi-row selection for list pages with bulk delete.
 *
 * Pass the array of rows currently rendered (each must have a stable `id`).
 * Returns selection state plus helpers to wire into a header checkbox, per-row
 * checkboxes, and a bulk-delete action that fires the existing single-delete
 * endpoint for each selected row in parallel.
 *
 * Usage:
 *   const sel = useBulkSelect(items);
 *   ...
 *   <input type="checkbox" checked={sel.allSelected} onChange={sel.toggleAll} />
 *   <input type="checkbox" checked={sel.isSelected(row.id)} onChange={() => sel.toggle(row.id)} />
 *   <BulkDeleteBar
 *     count={sel.count}
 *     onClear={sel.clear}
 *     onDelete={() => sel.runDelete((id) => api.delete(`/invoices/${id}`), { reload: load })}
 *   />
 */
export default function useBulkSelect(rows) {
  const [selected, setSelected] = useState(() => new Set());
  const [deleting, setDeleting] = useState(false);

  const ids = useMemo(() => (rows || []).map((r) => r.id).filter(Boolean), [rows]);

  const toggle = useCallback((id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const isSelected = useCallback((id) => selected.has(id), [selected]);

  const clear = useCallback(() => setSelected(new Set()), []);

  // Header checkbox: select all rows currently shown, or clear if all are already on.
  const allSelected = ids.length > 0 && ids.every((id) => selected.has(id));
  const someSelected = ids.some((id) => selected.has(id)) && !allSelected;

  const toggleAll = useCallback(() => {
    setSelected((prev) => {
      const everyOn = ids.length > 0 && ids.every((id) => prev.has(id));
      return everyOn ? new Set() : new Set(ids);
    });
  }, [ids]);

  // Only keep ids that still exist in the current rows (e.g. after a reload).
  const selectedIds = useMemo(
    () => ids.filter((id) => selected.has(id)),
    [ids, selected]
  );

  /**
   * Delete every selected row by calling `deleteOne(id)` for each, in parallel.
   * `deleteOne` should return a promise (typically `api.delete(...)`).
   * Returns { ok, failed } counts. On completion, clears selection and calls reload().
   */
  const runDelete = useCallback(
    async (deleteOne, { reload } = {}) => {
      const targets = selectedIds;
      if (targets.length === 0) return { ok: 0, failed: 0 };
      setDeleting(true);
      try {
        const results = await Promise.allSettled(targets.map((id) => deleteOne(id)));
        const failed = results.filter((r) => r.status === "rejected").length;
        const ok = results.length - failed;
        clear();
        if (reload) await reload();
        return { ok, failed };
      } finally {
        setDeleting(false);
      }
    },
    [selectedIds, clear]
  );

  return {
    selected,
    selectedIds,
    count: selectedIds.length,
    isSelected,
    toggle,
    toggleAll,
    allSelected,
    someSelected,
    clear,
    deleting,
    runDelete,
  };
}
