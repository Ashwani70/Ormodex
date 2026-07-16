import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Search, X } from "lucide-react";

/**
 * Shared customer/vendor autocomplete — consolidates four near-identical
 * "CustomerSearch"/"VendorSearch" implementations that were copy-pasted with
 * drift across SalesOrders/Invoices/CreditNotes/PurchaseBills, none of which
 * had any keyboard navigation (mouse-only onMouseDown selection). Mirrors
 * ItemSearch.jsx's pattern exactly — same portal positioning, same Arrow/
 * Enter/Escape handling, same onKeyDown passthrough so it composes cleanly
 * inside a <KeyboardForm> or a <KeyboardGrid> cell.
 *
 * Props:
 *   parties:   [{ id, name, company?, gstin?, phone?, email? }] — customers or vendors
 *   value:     selected party id
 *   onChange:  (id, party | null) => void
 *   placeholder, inputRef, onKeyDown, testid — same contract as ItemSearch
 *   quickCreateType: when set (e.g. "customer" / "vendor"), marks the root
 *     data-quick-create="<type>" so a parent's useEnterNavigation({onQuickCreate})
 *     fires "create a new <type>" on Ctrl+Enter while this field is focused,
 *     seeded with whatever the user has already typed. Omit to disable.
 */
export default function PartySearch({
  parties = [],
  value,
  onChange,
  placeholder = "Search customer / vendor…",
  inputRef,
  onKeyDown,
  testid,
  quickCreateType,
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef(null);
  const localInputRef = useRef(null);
  const panelRef = useRef(null);
  const [coords, setCoords] = useState(null);
  const setInputRef = (el) => {
    localInputRef.current = el;
    if (typeof inputRef === "function") inputRef(el);
    else if (inputRef) inputRef.current = el;
  };

  const label = (p) => p.company || p.name || "";
  const selected = parties.find((p) => p.id === value);

  useEffect(() => {
    if (selected) setQuery(label(selected));
    else if (!value) setQuery("");
  }, [value, selected]);

  useEffect(() => {
    const handler = (e) => {
      if (rootRef.current && rootRef.current.contains(e.target)) return;
      if (panelRef.current && panelRef.current.contains(e.target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => { setActive(0); }, [query, open]);

  const placePanel = () => {
    const el = localInputRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const width = Math.max(r.width, 280);
    const spaceBelow = window.innerHeight - r.bottom;
    const openUp = spaceBelow < 260 && r.top > spaceBelow;
    setCoords({
      left: Math.min(r.left, window.innerWidth - width - 8),
      top: openUp ? undefined : r.bottom + 4,
      bottom: openUp ? window.innerHeight - r.top + 4 : undefined,
      width,
    });
  };

  useLayoutEffect(() => {
    if (!open) return;
    placePanel();
    const onScrollOrResize = () => placePanel();
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
    return () => {
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
    };
  }, [open]);

  const filtered = (query.length === 0 ? parties : parties.filter((p) => {
    const q = query.toLowerCase();
    return label(p).toLowerCase().includes(q) ||
      p.gstin?.toLowerCase().includes(q) ||
      p.phone?.includes(q) ||
      p.email?.toLowerCase().includes(q);
  })).slice(0, 40);

  const choose = (p) => {
    onChange?.(p.id, p);
    setQuery(label(p));
    setOpen(false);
  };

  const handleLocalKeyDown = (e) => {
    if (open && filtered.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((i) => Math.min(i + 1, filtered.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        if (filtered[active]) choose(filtered[active]);
        return;
      }
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
    }
    onKeyDown?.(e);
  };

  return (
    <div ref={rootRef} className="relative" data-quick-create={quickCreateType || undefined}>
      <div className="relative">
        <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
        <input
          ref={setInputRef}
          type="text"
          data-testid={testid}
          placeholder={placeholder}
          value={query}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            if (!e.target.value) onChange?.("", null);
          }}
          onKeyDown={handleLocalKeyDown}
          className="h-10 w-full rounded-[var(--radius-md)] bg-surface border border-input text-foreground text-sm pl-8 pr-7 focus:border-primary focus:outline-none focus:ring-[3px] focus:ring-primary/15 transition-colors"
        />
        {(value || query) && (
          <button
            type="button"
            tabIndex={-1}
            onClick={() => { onChange?.("", null); setQuery(""); }}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="w-3 h-3" />
          </button>
        )}
      </div>

      {open && coords && filtered.length > 0 && createPortal(
        <div
          ref={panelRef}
          className="fixed z-[100] rounded-lg bg-card border border-border shadow-lg max-h-56 overflow-y-auto"
          style={{ left: coords.left, top: coords.top, bottom: coords.bottom, width: coords.width }}
        >
          {filtered.map((p, i) => (
            <button
              key={p.id}
              type="button"
              onMouseDown={(e) => { e.preventDefault(); choose(p); }}
              onMouseEnter={() => setActive(i)}
              className={`w-full text-left px-3 py-2 flex items-center justify-between gap-2 border-b border-border last:border-0 ${
                i === active ? "bg-primary/15" : "hover:bg-muted"
              }`}
            >
              <div className="min-w-0">
                <div className="text-sm text-foreground font-medium truncate">{label(p)}</div>
                {p.gstin && <div className="text-xs text-muted-foreground font-mono">{p.gstin}</div>}
                {p.phone && <div className="text-xs text-muted-foreground">{p.phone}</div>}
              </div>
            </button>
          ))}
        </div>,
        document.body
      )}
    </div>
  );
}
