import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import { useModalStackRegistration } from "@/context/ModalStackContext";

const FOCUSABLE_SELECTOR = [
  "input:not([type=hidden]):not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "button:not([disabled])",
  "a[href]",
  "[contenteditable=true]",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export default function Modal({ open, onClose, title, children, footer, size = "md", testid, bodyClassName = "", icon: Icon, headerExtra }) {
  // Tell the global back-navigation handler a modal is open, so Escape
  // closes THIS modal instead of also navigating the page back.
  useModalStackRegistration(open);
  const dialogRef = useRef(null);
  const previouslyFocused = useRef(null);

  useEffect(() => {
    const onEsc = (e) => {
      if (e.key !== "Escape") return;
      // Stop this Escape from reaching the global back-nav listener on
      // `document` — closing the modal takes priority over navigating back.
      e.stopPropagation();
      onClose?.();
    };
    // Capture phase so we intercept Escape before it can bubble to any
    // other document-level listener (global back-nav, shortcuts-help, etc.).
    if (open) document.addEventListener("keydown", onEsc, true);
    return () => document.removeEventListener("keydown", onEsc, true);
  }, [open, onClose]);

  // Focus containment: remember what had focus before the modal opened (so
  // closing can restore it — spec: "Closing modal restores previous focus"),
  // and trap native Tab/Shift+Tab at the dialog's own first/last focusable
  // element so focus can never escape to the page behind it. This is
  // deliberately separate from useEnterNavigation's own Tab-as-Enter handling
  // (which only governs the FORM fields inside a modal's body) — the footer's
  // Save/Cancel buttons live outside that form, so without this trap Tab from
  // a footer button would walk straight out to the page behind the modal.
  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement;
    const onTab = (e) => {
      if (e.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusable = Array.from(dialog.querySelectorAll(FOCUSABLE_SELECTOR))
        .filter((el) => el.getClientRects().length > 0); // visible only
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      } else if (!dialog.contains(active)) {
        // Focus somehow ended up outside the dialog (e.g. a portal-rendered
        // dropdown closed without restoring it) — pull it back in rather
        // than let the next Tab continue from wherever it drifted to.
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onTab, true);
    return () => {
      document.removeEventListener("keydown", onTab, true);
      // Restore focus to whatever opened the modal, but only if that element
      // is still attached — it may have been removed by the same action that
      // closed the modal (e.g. a deleted row's own "edit" button).
      const toRestore = previouslyFocused.current;
      if (toRestore && document.contains(toRestore) && typeof toRestore.focus === "function") {
        toRestore.focus();
      }
    };
  }, [open]);

  if (!open) return null;

  const widths = {
    sm: "max-w-md",
    md: "max-w-2xl",
    lg: "max-w-4xl",
    xl: "max-w-6xl",
    // Wide working surface for data-entry dialogs (line-item grids etc.):
    // 96vw capped at 1700px, taller body allowance (92vh) so big forms fit.
    full: "w-[96vw] max-w-[1700px]",
  };
  const isFull = size === "full";

  return (
    <div
      data-testid={testid}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/80 p-4 sm:py-8"
      onClick={onClose}
    >
      {/* Column layout capped to the viewport: header + footer stay fixed and
          only the body scrolls, so the whole form is reachable without the
          dialog itself being clipped. */}
      <div
        ref={dialogRef}
        className={`industrial-corner relative my-auto flex w-full ${widths[size]} flex-col bg-card border border-border text-foreground shadow-2xl ${
          isFull
            ? "max-h-[92vh] sm:h-[92vh]"
            : "max-h-[calc(100vh-2rem)] sm:max-h-[calc(100vh-4rem)]"
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="hazard-stripe h-1.5 w-full flex-shrink-0" />
        <div className="flex flex-shrink-0 items-center justify-between gap-4 border-b border-border px-6 py-4">
          <h3 className="flex min-w-0 items-center gap-2.5 font-display font-bold text-foreground text-lg">
            {Icon && (
              <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon className="h-5 w-5" />
              </span>
            )}
            <span className="truncate">{title}</span>
          </h3>
          <div className="flex flex-shrink-0 items-center gap-3">
            {headerExtra}
            <button
              data-testid="modal-close"
              onClick={onClose}
              className="w-8 h-8 flex items-center justify-center border border-border text-muted-foreground hover:text-primary hover:border-primary transition-colors bg-background"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className={`flex-1 overflow-y-auto overflow-x-hidden ${bodyClassName || "p-5"}`}>{children}</div>
        {footer && (
          <div className="flex flex-shrink-0 items-center justify-end gap-3 border-t border-border px-6 py-4 bg-muted/40">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
