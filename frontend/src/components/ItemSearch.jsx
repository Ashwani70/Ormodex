import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Search, X } from "lucide-react";

/**
 * Shared product/item autocomplete for line-item grids — consolidates the
 * near-identical "ProductSearch"/"ItemSearch" implementations that were
 * copy-pasted with drift across SalesOrders/PurchaseOrdersV2/Invoices/
 * CreditNotes/PurchaseBills. Adds Arrow/Enter keyboard navigation within the
 * suggestion list on top of the original mouse-only behaviour (none of the
 * existing copies had it), so it plugs into useGridKeyNav-driven grids
 * without fighting for the Enter/Arrow keys.
 *
 * Props:
 *   products:  [{ id, name, sku, unit, ... }]
 *   value:     selected product id
 *   onChange:  (id, product | null) => void — product is the full record, or
 *              null when the field is cleared / a custom (off-catalog) name
 *              is typed and not matched
 *   stockMap:  optional { [name|sku]: { closing_qty } } for live-stock display
 *   allowCustom: when true, Enter with no matching suggestion selected commits
 *              the typed text as a free-text item name (is_custom line)
 *   inputRef:  forwarded ref for the text input (for useGridKeyNav's registerCell)
 *   onKeyDown: forwarded to the input in addition to this component's own
 *              Arrow/Enter handling, so a parent grid nav hook still sees Tab/
 *              Escape/etc; Arrow/Enter used for suggestion navigation are
 *              stopped from bubbling only while the suggestion list is open.
 *   quickCreateType: when set (e.g. "item"), marks the root
 *              data-quick-create="<type>" so a parent's
 *              useEnterNavigation({onQuickCreate}) fires "create a new
 *              product" on Ctrl+Enter while this field is focused, seeded
 *              with whatever's been typed. Distinct from allowCustom, which
 *              commits a free-text line item with no real Product record —
 *              quick-create is for when the user actually wants a new master.
 */
export default function ItemSearch({
  products = [],
  value,
  onChange,
  stockMap = {},
  allowCustom = false,
  placeholder = "Search product / SKU…",
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
  // The suggestion list renders in a portal at the document root so it
  // escapes any ancestor `overflow-x-auto` table wrapper (which otherwise
  // clips/squashes it to the narrow "Product" column's width — see
  // JobWork.jsx's SearchableProductSelect, which hit and fixed the same
  // issue). Position is computed from the input's live viewport rect.
  const [coords, setCoords] = useState(null);
  const setInputRef = (el) => {
    localInputRef.current = el;
    if (typeof inputRef === "function") inputRef(el);
    else if (inputRef) inputRef.current = el;
  };

  const selected = products.find((p) => p.id === value);

  useEffect(() => {
    if (selected) setQuery(selected.name);
    else if (!value) setQuery((q) => (allowCustom ? q : ""));
  }, [value, selected, allowCustom]);

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
    // Capture on any ancestor (the table body, a modal, etc.) so the panel
    // tracks the input instead of detaching from it when the user scrolls.
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
    return () => {
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
    };
  }, [open]);

  const filtered = query.length === 0
    ? products.slice(0, 50)
    : products.filter((p) =>
        p.name?.toLowerCase().includes(query.toLowerCase()) ||
        p.sku?.toLowerCase().includes(query.toLowerCase())
      ).slice(0, 30);

  const choose = (p) => {
    onChange?.(p.id, p);
    setQuery(p.name);
    setOpen(false);
  };

  const commitCustom = () => {
    if (allowCustom && query.trim()) {
      onChange?.(null, { id: null, name: query.trim(), is_custom: true });
    }
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
        else commitCustom();
        return;
      }
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
    } else if (e.key === "Enter" && allowCustom && query.trim() && !selected) {
      e.preventDefault();
      commitCustom();
      return;
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
          {filtered.map((p, i) => {
            const s = stockMap[p.name] || stockMap[p.sku];
            return (
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
                  <div className="text-sm text-foreground font-medium truncate">{p.name}</div>
                  {p.sku && <div className="text-xs text-muted-foreground">{p.sku}</div>}
                </div>
                {s && (
                  <div className="text-xs text-right shrink-0">
                    <span className={`font-bold tabular ${s.closing_qty > 0 ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>
                      {s.closing_qty} {p.unit || ""}
                    </span>
                    <div className="text-muted-foreground">in stock</div>
                  </div>
                )}
              </button>
            );
          })}
        </div>,
        document.body
      )}
      {open && coords && filtered.length === 0 && allowCustom && query.trim() && createPortal(
        <div
          ref={panelRef}
          className="fixed z-[100] rounded-lg bg-card border border-border shadow-lg"
          style={{ left: coords.left, top: coords.top, bottom: coords.bottom, width: coords.width }}
        >
          <button
            type="button"
            onMouseDown={(e) => { e.preventDefault(); commitCustom(); }}
            className="w-full text-left px-3 py-2 text-sm text-primary hover:bg-muted"
          >
            Use "{query.trim()}" as a custom item
          </button>
        </div>,
        document.body
      )}
    </div>
  );
}
