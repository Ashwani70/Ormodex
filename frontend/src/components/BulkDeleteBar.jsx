import { Trash2, X } from "lucide-react";
import { Spinner } from "@/components/ui-kit";

/**
 * Floating action bar shown when one or more rows are selected on a list page.
 * Sits fixed at the bottom-center so it never shifts table layout.
 *
 * Props:
 *   count     – number of selected rows
 *   onDelete  – called when the user confirms bulk delete
 *   onClear   – called to clear the selection
 *   deleting  – disables the button and shows a spinner while in flight
 *   noun       – singular label for what's being deleted (default "item")
 *   nounPlural – plural form, when it isn't simply noun + "s" (e.g. "dispatches")
 */
export default function BulkDeleteBar({ count, onDelete, onClear, deleting, noun = "item", nounPlural }) {
  if (!count) return null;
  const label = `${count} ${count === 1 ? noun : nounPlural || `${noun}s`}`;

  const confirmDelete = () => {
    if (deleting) return;
    if (!window.confirm(`Delete ${label}? This cannot be undone.`)) return;
    onDelete();
  };

  return (
    <div
      className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 bg-card border border-border px-4 py-2.5"
      style={{ borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-lg)" }}
      data-testid="bulk-delete-bar"
    >
      <span className="text-sm font-medium text-foreground tabular">{label} selected</span>
      <button
        onClick={confirmDelete}
        disabled={deleting}
        data-testid="bulk-delete-btn"
        className="inline-flex items-center gap-2 h-9 px-3 text-sm font-medium text-[var(--danger)] border border-[var(--danger)]/40 hover:bg-[#FEE2E2] hover:border-[var(--danger)] disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
        style={{ borderRadius: "var(--radius-md)" }}
      >
        {deleting ? <Spinner className="w-4 h-4" /> : <Trash2 className="w-4 h-4" />}
        Delete selected
      </button>
      <button
        onClick={onClear}
        disabled={deleting}
        title="Clear selection"
        className="w-9 h-9 flex items-center justify-center text-muted-foreground hover:text-foreground border border-border hover:border-[var(--border-strong)] disabled:opacity-60 transition-colors"
        style={{ borderRadius: "var(--radius-md)" }}
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

/**
 * Checkbox styled for selection cells. Spread into a `<td>`/`<th>`.
 * `indeterminate` shows the partial state on the header checkbox.
 */
export function SelectCheckbox({ checked, indeterminate, onChange, label = "Select row" }) {
  return (
    <input
      type="checkbox"
      aria-label={label}
      checked={checked}
      ref={(el) => {
        if (el) el.indeterminate = !!indeterminate && !checked;
      }}
      onChange={onChange}
      onClick={(e) => e.stopPropagation()}
      className="w-4 h-4 cursor-pointer accent-[var(--primary)] align-middle"
    />
  );
}
