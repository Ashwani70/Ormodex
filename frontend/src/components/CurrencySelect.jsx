import { useEffect, useId, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { CURRENCIES, CURRENCY_BY_CODE, formatCurrencyOption } from "@/config/currencies";

/**
 * Searchable currency dropdown (combobox) with keyboard navigation.
 *
 * - Filters the predefined ISO list by code or name as the user types.
 * - ArrowUp/Down move the highlight, Enter selects, Escape closes.
 * - Calls `onSelect(currency)` with `{ code, name, symbol, decimals }` so the
 *   caller can auto-fill related fields.
 * - `value` is the selected ISO code; an unknown/legacy code (not in the
 *   catalogue) still displays so existing records stay editable (backward compat).
 *
 * Matches the ui-kit field styling (same border/focus tokens as <Input/>).
 */
const FIELD_BASE =
  "w-full text-sm text-foreground placeholder:text-muted-foreground/60 outline-none border transition-colors";
const FIELD_OK = "border-input focus:border-primary focus:ring-[3px] focus:ring-primary/15";
const FIELD_ERR = "border-[var(--danger)] focus:border-[var(--danger)] focus:ring-[3px] focus:ring-[rgba(239,68,68,0.15)]";

export default function CurrencySelect({ value, onSelect, error, disabled, testid, ...rest }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const rootRef = useRef(null);
  const inputRef = useRef(null);
  const listId = useId();

  const selected = value ? CURRENCY_BY_CODE[String(value).toUpperCase()] : null;
  // What the input shows when closed: the picked option label, or a raw legacy code.
  const closedText = selected ? formatCurrencyOption(selected) : (value || "");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return CURRENCIES;
    return CURRENCIES.filter(
      (c) => c.code.toLowerCase().includes(q) || c.name.toLowerCase().includes(q)
    );
  }, [query]);

  // Close on outside click.
  useEffect(() => {
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  // Keep the highlight in range when the filtered set changes.
  useEffect(() => { setActive(0); }, [query]);

  const choose = (c) => {
    if (!c) return;
    onSelect?.(c);
    setOpen(false);
    setQuery("");
    inputRef.current?.blur();
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
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(filtered[active]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    }
  };

  return (
    <div className="relative" ref={rootRef}>
      <input
        {...rest}
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
        className={cn(FIELD_BASE, error ? FIELD_ERR : FIELD_OK, "h-10 px-3", disabled && "opacity-60 cursor-not-allowed")}
        style={{ borderRadius: "var(--radius-md)", background: "var(--surface)" }}
        placeholder="Search currency (e.g. INR, Dollar)…"
        value={open ? query : closedText}
        onChange={(e) => { setQuery(e.target.value); if (!open) setOpen(true); }}
        onFocus={openMenu}
        onClick={openMenu}
        onKeyDown={onKeyDown}
      />
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
          {filtered.map((c, i) => (
            <li
              key={c.code}
              role="option"
              aria-selected={selected?.code === c.code}
              // onMouseDown (not onClick) so it fires before the input blur closes the list.
              onMouseDown={(e) => { e.preventDefault(); choose(c); }}
              onMouseEnter={() => setActive(i)}
              className={cn(
                "px-3 py-2 text-sm cursor-pointer flex items-center justify-between gap-2",
                i === active ? "bg-primary/15 text-foreground" : "text-foreground/90 hover:bg-muted"
              )}
            >
              <span><span className="font-mono">{c.code}</span> — {c.name}</span>
              <span className="text-muted-foreground">{c.symbol}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
