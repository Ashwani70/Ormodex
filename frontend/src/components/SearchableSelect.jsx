import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Plus, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Generic searchable dropdown (combobox) with keyboard navigation and an
 * optional "create new" footer action — used for the product Category picker.
 *
 * Props:
 *   options:   [{ value, label, sublabel? }]
 *   value:     selected value (matched against option.value)
 *   onChange:  (value) => void
 *   onCreate:  optional () => void — renders a "+ Create new…" row at the bottom
 *   createLabel: footer label (default "Create New Category")
 *   placeholder, disabled, error, testid
 *
 * Matches the ui-kit field styling (same tokens as <Input/> and CurrencySelect).
 */
const FIELD_BASE =
  "w-full text-sm text-foreground placeholder:text-muted-foreground/60 outline-none border transition-colors";
const FIELD_OK = "border-input focus:border-primary focus:ring-[3px] focus:ring-primary/15";
const FIELD_ERR = "border-[var(--danger)] focus:border-[var(--danger)] focus:ring-[3px] focus:ring-[rgba(239,68,68,0.15)]";

export default function SearchableSelect({
  options = [],
  value,
  onChange,
  onCreate,
  createLabel = "Create New Category",
  placeholder = "Search…",
  disabled,
  error,
  testid,
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const rootRef = useRef(null);
  const inputRef = useRef(null);
  const listId = useId();

  const selected = useMemo(
    () => options.find((o) => o.value === value) || null,
    [options, value]
  );
  const closedText = selected ? selected.label : "";

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter(
      (o) =>
        o.label.toLowerCase().includes(q) ||
        String(o.sublabel || "").toLowerCase().includes(q)
    );
  }, [query, options]);

  // The create row sits one past the filtered options in the highlight order.
  const createIndex = onCreate ? filtered.length : -1;

  useEffect(() => {
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => { setActive(0); }, [query]);

  const choose = (o) => {
    if (!o) return;
    onChange?.(o.value);
    setOpen(false);
    setQuery("");
    inputRef.current?.blur();
  };

  const fireCreate = () => {
    setOpen(false);
    setQuery("");
    onCreate?.();
  };

  const openMenu = () => { if (!disabled) { setOpen(true); setQuery(""); } };

  const onKeyDown = (e) => {
    if (disabled) return;
    if (!open && (e.key === "ArrowDown" || e.key === "Enter")) {
      e.preventDefault();
      setOpen(true);
      return;
    }
    if (!open) return;
    const max = onCreate ? filtered.length : filtered.length - 1;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, max));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (active === createIndex) fireCreate();
      else choose(filtered[active]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    } else if (e.key === "Tab") {
      // Don't preventDefault/consume Tab — just close the panel first so a
      // parent form's Tab-as-Enter navigation (useEnterNavigation) doesn't
      // leave a stale open dropdown behind when it moves focus onward.
      setOpen(false);
    }
  };

  return (
    <div className="relative" ref={rootRef}>
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-invalid={error ? true : undefined}
          autoComplete="off"
          disabled={disabled}
          data-testid={testid}
          className={cn(FIELD_BASE, error ? FIELD_ERR : FIELD_OK, "h-10 pl-3 pr-8", disabled && "opacity-60 cursor-not-allowed")}
          style={{ borderRadius: "var(--radius-md)", background: "var(--surface)" }}
          placeholder={placeholder}
          value={open ? query : closedText}
          onChange={(e) => { setQuery(e.target.value); if (!open) setOpen(true); }}
          onFocus={openMenu}
          onClick={openMenu}
          onKeyDown={onKeyDown}
        />
        <ChevronDown className="w-4 h-4 absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
      </div>
      {open && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-50 mt-1 max-h-64 w-full overflow-auto border border-border bg-card shadow-lg"
          style={{ borderRadius: "var(--radius-md)" }}
        >
          {filtered.length === 0 && (
            <li className="px-3 py-2 text-sm text-muted-foreground font-mono">No match</li>
          )}
          {filtered.map((o, i) => (
            <li
              key={o.value}
              role="option"
              aria-selected={selected?.value === o.value}
              data-testid={testid ? `${testid}-option-${o.value}` : undefined}
              onMouseDown={(e) => { e.preventDefault(); choose(o); }}
              onMouseEnter={() => setActive(i)}
              className={cn(
                "px-3 py-2 text-sm cursor-pointer flex items-center justify-between gap-2",
                i === active ? "bg-primary/15 text-foreground" : "text-foreground/90 hover:bg-muted"
              )}
            >
              <span>{o.label}</span>
              {o.sublabel && <span className="text-muted-foreground font-mono text-xs">{o.sublabel}</span>}
            </li>
          ))}
          {onCreate && (
            <li
              role="option"
              aria-selected={false}
              data-testid={testid ? `${testid}-create` : undefined}
              onMouseDown={(e) => { e.preventDefault(); fireCreate(); }}
              onMouseEnter={() => setActive(createIndex)}
              className={cn(
                "px-3 py-2 text-sm cursor-pointer flex items-center gap-2 border-t border-border font-medium",
                active === createIndex ? "bg-primary/15 text-primary" : "text-primary hover:bg-muted"
              )}
            >
              <Plus className="w-3.5 h-3.5" /> {createLabel}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
