import { useEffect } from "react";
import { isInputFocused } from "@/hooks/useKeyboardShortcuts";

/**
 * Opt-in per-page action shortcuts, for module pages (Inventory, Purchase,
 * Sales, Accounts, HR, etc.) that want the standard ERP action keys to do
 * something real on their screen:
 *
 *   Ctrl/Cmd + S   → onSave    (save the currently open form)
 *   Ctrl/Cmd + N   → onNew     (start a new record)
 *   Ctrl/Cmd + E   → onEdit    (edit the selected/current record)
 *   Ctrl/Cmd + P   → onPrint   (print / open the PDF)
 *   Ctrl/Cmd + F   → onSearch  (focus this page's own search box)
 *   F2             → onRename  (rename/edit inline)
 *   F8             → onDelete
 *   F9             → onCreateVoucher
 *
 * A page only needs to pass the callbacks it actually supports — any
 * omitted handler is simply not wired up (no-op), so this is entirely
 * additive and safe to skip. Ctrl+S/N/P/F use preventDefault() so they
 * don't trigger the browser's native Save-page/New-window/Print/Find-in-page
 * dialogs while a handler is registered.
 *
 * Unlike the G-navigation shortcuts, Ctrl+S/N/E/P/F are NOT suppressed
 * while typing in a field — that's the expected behavior for these keys
 * (a user filling a form still expects Ctrl+S to save the form). F2/F8/F9
 * ARE suppressed while typing, since those are bare (unmodified) keys that
 * would otherwise interfere with normal text entry.
 *
 * Registered on the CAPTURE phase and calls stopPropagation() for any key it
 * actually handles, so a page's own Ctrl+N/F "wins" over the app-wide
 * Ctrl+N/F fallback in useKeyboardShortcuts (a bubble-phase, document-level
 * listener mounted once in Layout) — specific beats general. Without this, a
 * page opting into onNew would still also trigger the global "new voucher"
 * navigation on every Ctrl+N, since both listeners are on the same document
 * and neither would otherwise know about the other.
 */
export function useModuleShortcuts({
  onSave,
  onNew,
  onEdit,
  onPrint,
  onSearch,
  onDuplicate,
  onRename,
  onDelete,
  onCreateVoucher,
} = {}) {
  useEffect(() => {
    const handler = (e) => {
      const mod = e.ctrlKey || e.metaKey;

      if (mod && (e.key === "s" || e.key === "S") && onSave) {
        e.preventDefault();
        e.stopPropagation();
        onSave(e);
        return;
      }
      if (mod && (e.key === "n" || e.key === "N") && onNew) {
        e.preventDefault();
        e.stopPropagation();
        onNew(e);
        return;
      }
      if (mod && (e.key === "e" || e.key === "E") && onEdit) {
        e.preventDefault();
        e.stopPropagation();
        onEdit(e);
        return;
      }
      if (mod && (e.key === "p" || e.key === "P") && onPrint) {
        e.preventDefault();
        e.stopPropagation();
        onPrint(e);
        return;
      }
      if (mod && (e.key === "f" || e.key === "F") && onSearch) {
        e.preventDefault();
        e.stopPropagation();
        onSearch(e);
        return;
      }
      if (mod && (e.key === "d" || e.key === "D") && onDuplicate) {
        e.preventDefault();
        e.stopPropagation();
        onDuplicate(e);
        return;
      }

      // Bare function keys — skip while typing so they don't clash with
      // native field editing (e.g. F2 renaming a file in some OS file pickers).
      if (isInputFocused()) return;

      if (e.key === "F2" && onRename) {
        e.preventDefault();
        e.stopPropagation();
        onRename(e);
        return;
      }
      if (e.key === "F8" && onDelete) {
        e.preventDefault();
        e.stopPropagation();
        onDelete(e);
        return;
      }
      if (e.key === "F9" && onCreateVoucher) {
        e.preventDefault();
        e.stopPropagation();
        onCreateVoucher(e);
      }
    };

    // Capture phase: run before the app-wide document-level listener in
    // useKeyboardShortcuts (Layout mounts it first in bubble order) so a
    // page-specific handler here can stopPropagation() and pre-empt the
    // global fallback for the same key.
    document.addEventListener("keydown", handler, true);
    return () => document.removeEventListener("keydown", handler, true);
    // Re-bind whenever a handler identity changes so closures stay fresh
    // (pages typically pass inline arrow functions that capture current state).
  }, [onSave, onNew, onEdit, onPrint, onSearch, onDuplicate, onRename, onDelete, onCreateVoucher]);
}
