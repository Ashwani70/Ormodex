import { useEffect } from "react";
import { X, Keyboard } from "lucide-react";
import { SHORTCUTS } from "@/hooks/useKeyboardShortcuts";

function Kbd({ children }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[1.5rem] h-6 px-1.5 bg-muted border border-border text-[11px] font-mono font-semibold text-foreground">
      {children}
    </kbd>
  );
}

const GENERAL = [
  { keys: ["Ctrl", "K"],   label: "Open search" },
  { keys: ["Ctrl", "/"],   label: "Show this shortcuts panel" },
  { keys: ["?"],           label: "Show this shortcuts panel" },
  { keys: ["Esc"],         label: "Close modal/panel — or go back if none is open" },
  { keys: ["Alt", "←"],    label: "Go back (Windows/Linux)" },
  { keys: ["Cmd", "["],    label: "Go back (macOS)" },
  { keys: ["F11"],         label: "Toggle full screen" },
  { keys: ["F12"],         label: "Open Settings" },
];

// Standard ERP action keys — only active on pages that support them
// (see useModuleShortcuts). Shown here so the combo is discoverable even
// where it isn't wired up yet.
const ACTIONS = [
  { keys: ["Ctrl", "S"],   label: "Save" },
  { keys: ["Ctrl", "N"],   label: "New record" },
  { keys: ["Ctrl", "E"],   label: "Edit" },
  { keys: ["Ctrl", "P"],   label: "Print" },
  { keys: ["Ctrl", "F"],   label: "Search this page" },
  { keys: ["Ctrl", "D"],   label: "Duplicate" },
  { keys: ["F2"],          label: "Rename / edit" },
  { keys: ["F8"],          label: "Delete" },
  { keys: ["F9"],          label: "Create voucher / document" },
];

// App-wide voucher/module navigation (Tally's own F-key layout, plus
// Alt-combos) — always on, everywhere, unless the current page defines its
// own meaning for the same key (that page's shortcut always wins).
const VOUCHER_NAV = [
  { keys: ["F3"],          label: "Company Master" },
  { keys: ["F4"],          label: "Contra Voucher" },
  { keys: ["F5"],          label: "Payment Voucher" },
  { keys: ["F6"],          label: "Receipt Voucher" },
  { keys: ["F7"],          label: "Journal Voucher" },
  { keys: ["F8"],          label: "Sales Voucher" },
  { keys: ["F9"],          label: "Purchase Voucher" },
  { keys: ["F10"],         label: "Other Voucher" },
  { keys: ["Alt", "C"],    label: "Create Customer" },
  { keys: ["Alt", "P"],    label: "Create Product" },
  { keys: ["Alt", "I"],    label: "Product Master" },
  { keys: ["Alt", "L"],    label: "Stock Log" },
  { keys: ["Alt", "W"],    label: "Select Warehouse" },
];

// Inside any line-item grid (Sales Order, Invoice, Purchase Bill, ...) or a
// plain field-by-field form built on the Enter-navigation engine.
const DATA_ENTRY = [
  { keys: ["Enter"],           label: "Next field (same as Tab)" },
  { keys: ["Shift", "Enter"],  label: "Previous field (same as Shift+Tab)" },
  { keys: ["Ctrl", "Enter"],   label: "Save (or: open quick-create for a lookup field)" },
  { keys: ["Ctrl", "S"],       label: "Save" },
  { keys: ["Ctrl", "Shift", "Enter"], label: "Save & New" },
  { keys: ["Esc"],             label: "Close popup / cancel form — returns focus" },
  { keys: ["Insert"],          label: "Insert row (grid)" },
  { keys: ["Ctrl", "Delete"],  label: "Delete row (grid)" },
  { keys: ["↑", "↓", "←", "→"], label: "Move between grid cells" },
];

// Split navigation shortcuts into two columns
const mid = Math.ceil(SHORTCUTS.length / 2);
const LEFT_NAV  = SHORTCUTS.slice(0, mid);
const RIGHT_NAV = SHORTCUTS.slice(mid);

export default function KeyboardShortcutsHelp({ open, onClose }) {
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (e.key !== "Escape") return;
      // Closing this panel takes priority over the global back-nav handler
      // also reacting to the same Escape press.
      e.stopPropagation();
      onClose();
    };
    // Capture phase so we intercept before the panel's Escape can bubble to
    // the global back-nav listener on `document`.
    document.addEventListener("keydown", handler, true);
    return () => document.removeEventListener("keydown", handler, true);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-card border border-border shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-border bg-muted/40">
          <div className="flex items-center gap-2">
            <Keyboard className="w-4 h-4 text-primary" />
            <span className="font-mono text-sm uppercase tracking-widest text-foreground font-semibold">
              Keyboard Shortcuts
            </span>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center border border-border text-muted-foreground hover:text-foreground hover:border-foreground transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* General */}
          <section>
            <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground mb-2.5">
              General
            </div>
            <div className="space-y-1.5">
              {GENERAL.map((s, i) => (
                <div key={i} className="flex items-center justify-between gap-4">
                  <span className="text-sm text-muted-foreground">{s.label}</span>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {s.keys.map((k, j) => (
                      <span key={j} className="flex items-center gap-1">
                        {j > 0 && <span className="text-muted-foreground text-[10px]">+</span>}
                        <Kbd>{k}</Kbd>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <div className="border-t border-border" />

          {/* Module actions — only live on pages that support them */}
          <section>
            <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground mb-1">
              Module actions
            </div>
            <p className="text-[11px] text-muted-foreground font-mono mb-2.5">
              Available on pages that support the action (e.g. Save only works while a form is open).
            </p>
            <div className="space-y-1.5">
              {ACTIONS.map((s, i) => (
                <div key={i} className="flex items-center justify-between gap-4">
                  <span className="text-sm text-muted-foreground">{s.label}</span>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {s.keys.map((k, j) => (
                      <span key={j} className="flex items-center gap-1">
                        {j > 0 && <span className="text-muted-foreground text-[10px]">+</span>}
                        <Kbd>{k}</Kbd>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <div className="border-t border-border" />

          {/* Voucher/module F-keys */}
          <section>
            <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground mb-1">
              Voucher &amp; module keys
            </div>
            <p className="text-[11px] text-muted-foreground font-mono mb-2.5">
              Work anywhere in the app, unless the current page defines its own meaning for that key.
            </p>
            <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
              {VOUCHER_NAV.map((s, i) => (
                <div key={i} className="flex items-center justify-between gap-4">
                  <span className="text-sm text-muted-foreground">{s.label}</span>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {s.keys.map((k, j) => (
                      <span key={j} className="flex items-center gap-1">
                        {j > 0 && <span className="text-muted-foreground text-[10px]">+</span>}
                        <Kbd>{k}</Kbd>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <div className="border-t border-border" />

          {/* Data entry — Enter-navigation engine */}
          <section>
            <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground mb-1">
              Data entry
            </div>
            <p className="text-[11px] text-muted-foreground font-mono mb-2.5">
              Inside a voucher form or line-item grid.
            </p>
            <div className="space-y-1.5">
              {DATA_ENTRY.map((s, i) => (
                <div key={i} className="flex items-center justify-between gap-4">
                  <span className="text-sm text-muted-foreground">{s.label}</span>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {s.keys.map((k, j) => (
                      <span key={j} className="flex items-center gap-1">
                        {j > 0 && <span className="text-muted-foreground text-[10px]">+</span>}
                        <Kbd>{k}</Kbd>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <div className="border-t border-border" />

          {/* Navigation — G + key */}
          <section>
            <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-muted-foreground mb-1">
              Navigate — press <Kbd>G</Kbd> then a letter
            </div>
            <p className="text-[11px] text-muted-foreground font-mono mb-3">
              Press G first, then the second key within 1.5 s. Works only when not typing in a field.
            </p>
            <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
              {/* Left column */}
              <div className="space-y-1.5">
                {LEFT_NAV.map((s, i) => (
                  <div key={i} className="flex items-center justify-between gap-2">
                    <span className="text-sm text-muted-foreground truncate">{s.label}</span>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <Kbd>G</Kbd>
                      <span className="text-muted-foreground text-[10px]">→</span>
                      <Kbd>{s.keys[1]}</Kbd>
                    </div>
                  </div>
                ))}
              </div>
              {/* Right column */}
              <div className="space-y-1.5">
                {RIGHT_NAV.map((s, i) => (
                  <div key={i} className="flex items-center justify-between gap-2">
                    <span className="text-sm text-muted-foreground truncate">{s.label}</span>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <Kbd>G</Kbd>
                      <span className="text-muted-foreground text-[10px]">→</span>
                      <Kbd>{s.keys[1]}</Kbd>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-border bg-muted/20 flex items-center justify-between">
          <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
            Shortcuts only activate outside text fields
          </span>
          <button
            onClick={onClose}
            className="px-3 py-1 text-xs font-mono border border-border text-muted-foreground hover:text-foreground hover:border-foreground transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
