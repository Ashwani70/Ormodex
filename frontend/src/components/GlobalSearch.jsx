import { useState, useRef, useEffect, useCallback, useMemo, Fragment } from "react";
import { useNavigate } from "react-router-dom";
import { Command as CommandPrimitive } from "cmdk";
import {
  Search, X, Clock, Star, ArrowRight, Loader2,
  Package, User, Truck, Users, Target, BookOpen, FileText,
  ShoppingCart, Receipt, FileMinus, ShoppingBag, PackageCheck,
  CreditCard, Box, Layers, Repeat, Clipboard, Printer, Settings,
} from "lucide-react";
import { Dialog, DialogPortal, DialogOverlay } from "@/components/ui/dialog";
import { useModalStackRegistration } from "@/context/ModalStackContext";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { searchablePages } from "@/lib/navItems";

// Maps the backend's plain-string icon key (routers/search.py `_Entity.icon`)
// to a lucide component. Falls back to a generic file icon for any module
// added server-side before a matching icon is added here.
const ICONS = {
  package: Package, user: User, truck: Truck, users: Users, target: Target,
  book: BookOpen, "file-text": FileText, "shopping-cart": ShoppingCart,
  receipt: Receipt, "file-minus": FileMinus, "shopping-bag": ShoppingBag,
  "package-check": PackageCheck, "book-open": BookOpen, "credit-card": CreditCard,
  box: Box, layers: Layers, settings: Settings, repeat: Repeat,
  clipboard: Clipboard, printer: Printer,
};

const RECENT_KEY = "gew_recent_searches";
const FAVORITES_KEY = "gew_favorite_searches";
const MAX_RECENT = 8;
const DEBOUNCE_MS = 250;

function loadList(key) {
  try {
    const raw = localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveRecent(term) {
  const trimmed = term.trim();
  if (!trimmed) return;
  const existing = loadList(RECENT_KEY).filter((t) => t.toLowerCase() !== trimmed.toLowerCase());
  existing.unshift(trimmed);
  localStorage.setItem(RECENT_KEY, JSON.stringify(existing.slice(0, MAX_RECENT)));
}

function toggleFavorite(term) {
  const trimmed = term.trim();
  if (!trimmed) return loadList(FAVORITES_KEY);
  const existing = loadList(FAVORITES_KEY);
  const idx = existing.findIndex((t) => t.toLowerCase() === trimmed.toLowerCase());
  if (idx >= 0) existing.splice(idx, 1);
  else existing.unshift(trimmed);
  const next = existing.slice(0, MAX_RECENT);
  localStorage.setItem(FAVORITES_KEY, JSON.stringify(next));
  return next;
}

// Wraps every case-insensitive occurrence of `term` in <mark> so the matched
// substring is visually highlighted in result titles/subtitles.
function Highlight({ text, term }) {
  const value = String(text ?? "");
  if (!term) return <>{value}</>;
  const lower = value.toLowerCase();
  const needle = term.toLowerCase();
  const parts = [];
  let i = 0;
  while (i < value.length) {
    const idx = lower.indexOf(needle, i);
    if (idx === -1) {
      parts.push(value.slice(i));
      break;
    }
    if (idx > i) parts.push(value.slice(i, idx));
    parts.push(
      <mark key={idx} className="bg-primary/25 text-foreground rounded-sm px-0.5">
        {value.slice(idx, idx + needle.length)}
      </mark>
    );
    i = idx + needle.length;
  }
  return <Fragment>{parts}</Fragment>;
}

function StatusChip({ status }) {
  if (!status) return null;
  const tone = /paid|active|approved|won|posted|cleared|completed/i.test(status)
    ? "success"
    : /overdue|rejected|bounced|cancelled|void|lost/i.test(status)
    ? "danger"
    : /draft|pending|new|quoted/i.test(status)
    ? "warning"
    : "neutral";
  const toneClasses = {
    success: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
    danger: "bg-red-500/15 text-red-600 dark:text-red-400",
    warning: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
    neutral: "bg-muted text-muted-foreground",
  }[tone];
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wider rounded-sm flex-shrink-0 ${toneClasses}`}>
      {status}
    </span>
  );
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

export default function GlobalSearch({ open, onClose }) {
  const [query, setQuery] = useState("");
  const [groups, setGroups] = useState({});
  const [pageResults, setPageResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [tookMs, setTookMs] = useState(null);
  const [recent, setRecent] = useState(() => loadList(RECENT_KEY));
  const [favorites, setFavorites] = useState(() => loadList(FAVORITES_KEY));
  const inputRef = useRef(null);
  const debounceRef = useRef(null);
  const requestSeq = useRef(0);
  const navigate = useNavigate();
  const { user } = useAuth();
  const pages = useMemo(() => searchablePages(user), [user]);

  useModalStackRegistration(open);

  useEffect(() => {
    if (open) {
      setQuery("");
      setGroups({});
      setPageResults([]);
      setTookMs(null);
      setRecent(loadList(RECENT_KEY));
      setFavorites(loadList(FAVORITES_KEY));
      const t = setTimeout(() => inputRef.current?.focus(), 60);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [open]);

  const runSearch = useCallback(
    async (term) => {
      const seq = ++requestSeq.current;
      setLoading(true);
      try {
        const { data } = await api.get("/search", { params: { q: term } });
        if (seq !== requestSeq.current) return; // a newer keystroke superseded this response
        setGroups(data.groups || {});
        setTookMs(data.took_ms ?? null);
      } catch {
        if (seq !== requestSeq.current) return;
        setGroups({});
        setTookMs(null);
      } finally {
        if (seq === requestSeq.current) setLoading(false);
      }
    },
    []
  );

  const handleType = (value) => {
    setQuery(value);
    const term = value.trim();
    if (!term) {
      setGroups({});
      setPageResults([]);
      setLoading(false);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      return;
    }
    const lower = term.toLowerCase();
    setPageResults(pages.filter((p) => p.label.toLowerCase().includes(lower)).slice(0, 8));

    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (term.length < 2) {
      setGroups({});
      return;
    }
    debounceRef.current = setTimeout(() => runSearch(term), DEBOUNCE_MS);
  };

  const goTo = (path, termForRecent) => {
    if (termForRecent) {
      saveRecent(termForRecent);
      setRecent(loadList(RECENT_KEY));
    }
    onClose();
    navigate(path);
  };

  const handleFavoriteClick = (e, term) => {
    e.stopPropagation();
    setFavorites(toggleFavorite(term));
  };

  const isFavorite = (term) => favorites.some((f) => f.toLowerCase() === term.toLowerCase());

  const groupEntries = Object.entries(groups);
  const totalRecords = groupEntries.reduce((sum, [, hits]) => sum + hits.length, 0);
  const hasQuery = query.trim().length > 0;
  const hasAnyResult = pageResults.length > 0 || totalRecords > 0;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogPortal>
        <DialogOverlay className="bg-black/50 backdrop-blur-[2px]" />
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] px-4 pointer-events-none">
          <div
            className="w-full max-w-2xl pointer-events-auto bg-card border border-border shadow-2xl overflow-hidden animate-in fade-in-0 zoom-in-95 duration-150"
            style={{ borderRadius: "var(--radius-lg)" }}
            role="dialog"
            aria-label="Global search"
          >
            <CommandPrimitive shouldFilter={false} loop className="flex flex-col">
              {/* ── Input row ─────────────────────────────────────────── */}
              <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
                {loading ? (
                  <Loader2 className="w-4 h-4 text-primary flex-shrink-0 animate-spin" />
                ) : (
                  <Search className="w-4 h-4 text-primary flex-shrink-0" />
                )}
                <CommandPrimitive.Input
                  ref={inputRef}
                  value={query}
                  onValueChange={handleType}
                  placeholder="Search products, customers, invoices, vouchers, employees…"
                  className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
                />
                {tookMs != null && hasQuery && (
                  <span className="text-[10px] font-mono text-muted-foreground flex-shrink-0 hidden sm:inline">
                    {totalRecords} in {tookMs}ms
                  </span>
                )}
                <button
                  onClick={onClose}
                  className="p-1 text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
                  aria-label="Close search"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* ── Results ───────────────────────────────────────────── */}
              <CommandPrimitive.List className="max-h-[65vh] overflow-y-auto overscroll-contain p-2">
                {!hasQuery && (
                  <EmptyQueryState
                    recent={recent}
                    favorites={favorites}
                    onPick={(term) => {
                      setQuery(term);
                      handleType(term);
                    }}
                    onFavoriteClick={handleFavoriteClick}
                    isFavorite={isFavorite}
                  />
                )}

                {hasQuery && !hasAnyResult && !loading && (
                  <div className="py-12 text-center">
                    <Search className="w-8 h-8 mx-auto text-muted-foreground/40 mb-2" strokeWidth={1.5} />
                    <p className="text-sm text-muted-foreground">No results for "{query}"</p>
                    <p className="text-xs text-muted-foreground/70 mt-1">Try a different name, code, or number</p>
                  </div>
                )}

                {hasQuery && loading && totalRecords === 0 && (
                  <SkeletonRows />
                )}

                {pageResults.length > 0 && (
                  <CommandPrimitive.Group heading="Pages" className="mb-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-muted-foreground">
                    {pageResults.map((p) => {
                      const Icon = p.icon;
                      return (
                        <CommandPrimitive.Item
                          key={p.path}
                          value={`page-${p.path}`}
                          onSelect={() => goTo(p.path, query)}
                          className="flex items-center gap-3 px-2 py-2 rounded-md text-sm text-foreground/80 cursor-pointer data-[selected=true]:bg-muted data-[selected=true]:text-foreground"
                        >
                          {Icon && <Icon className="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground" strokeWidth={2} />}
                          <span><Highlight text={p.label} term={query} /></span>
                          <ArrowRight className="w-3 h-3 ml-auto text-muted-foreground/50" />
                        </CommandPrimitive.Item>
                      );
                    })}
                  </CommandPrimitive.Group>
                )}

                {groupEntries.map(([key, hits]) => (
                  <CommandPrimitive.Group
                    key={key}
                    heading={hits[0]?.module || key}
                    className="mb-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-muted-foreground"
                  >
                    {hits.map((hit) => {
                      const Icon = ICONS[hit.icon] || FileText;
                      return (
                        <CommandPrimitive.Item
                          key={`${key}-${hit.id}`}
                          value={`${key}-${hit.id}-${hit.title}`}
                          onSelect={() => goTo(hit.path, query)}
                          className="flex items-center gap-3 px-2 py-2.5 rounded-md cursor-pointer data-[selected=true]:bg-muted"
                        >
                          <Icon className="w-4 h-4 flex-shrink-0 text-muted-foreground" strokeWidth={1.75} />
                          <span className="min-w-0 flex-1">
                            <span className="flex items-center gap-2">
                              <span className="truncate text-sm text-foreground font-medium">
                                <Highlight text={hit.title} term={query} />
                              </span>
                              <StatusChip status={hit.status} />
                            </span>
                            {hit.subtitle && (
                              <span className="block truncate text-[11px] text-muted-foreground mt-0.5">
                                <Highlight text={hit.subtitle} term={query} />
                              </span>
                            )}
                          </span>
                          <span className="flex flex-col items-end gap-0.5 flex-shrink-0 text-right">
                            {hit.docNumber && (
                              <span className="text-[10px] font-mono text-muted-foreground">{hit.docNumber}</span>
                            )}
                            {hit.date && (
                              <span className="text-[9px] text-muted-foreground/70">{formatDate(hit.date)}</span>
                            )}
                          </span>
                        </CommandPrimitive.Item>
                      );
                    })}
                  </CommandPrimitive.Group>
                ))}
              </CommandPrimitive.List>

              {/* ── Footer: keyboard hints ────────────────────────────── */}
              <div className="flex items-center gap-4 px-4 py-2 border-t border-border text-[10px] text-muted-foreground font-mono">
                <span className="flex items-center gap-1"><Kbd>↑↓</Kbd> navigate</span>
                <span className="flex items-center gap-1"><Kbd>Enter</Kbd> open</span>
                <span className="flex items-center gap-1"><Kbd>Tab</Kbd> next group</span>
                <span className="flex items-center gap-1 ml-auto"><Kbd>Esc</Kbd> close</span>
              </div>
            </CommandPrimitive>
          </div>
        </div>
      </DialogPortal>
    </Dialog>
  );
}

function Kbd({ children }) {
  return (
    <kbd className="inline-flex items-center px-1 py-0.5 bg-muted border border-border rounded-sm text-[9px]">
      {children}
    </kbd>
  );
}

function SkeletonRows() {
  return (
    <div className="space-y-2 p-2">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-2 py-2 animate-pulse">
          <div className="w-4 h-4 rounded bg-muted flex-shrink-0" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3 bg-muted rounded w-1/3" />
            <div className="h-2 bg-muted/70 rounded w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyQueryState({ recent, favorites, onPick, onFavoriteClick, isFavorite }) {
  if (recent.length === 0 && favorites.length === 0) {
    return (
      <div className="py-10 text-center text-xs text-muted-foreground">
        Start typing to search products, customers, invoices, vouchers and more…
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {favorites.length > 0 && (
        <div>
          <div className="px-2 pb-1 text-[10px] font-mono uppercase text-muted-foreground tracking-widest">
            Favorites
          </div>
          {favorites.map((term) => (
            <button
              key={term}
              onClick={() => onPick(term)}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-xs text-foreground/80 hover:bg-muted hover:text-foreground transition-colors text-left"
            >
              <Star className="w-3 h-3 text-amber-500 flex-shrink-0" fill="currentColor" />
              <span className="flex-1 truncate">{term}</span>
            </button>
          ))}
        </div>
      )}
      {recent.length > 0 && (
        <div>
          <div className="px-2 pb-1 text-[10px] font-mono uppercase text-muted-foreground tracking-widest">
            Recent searches
          </div>
          {recent.map((term) => (
            <div
              key={term}
              onClick={() => onPick(term)}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-xs text-foreground/80 hover:bg-muted hover:text-foreground transition-colors cursor-pointer group"
            >
              <Clock className="w-3 h-3 text-muted-foreground flex-shrink-0" />
              <span className="flex-1 truncate">{term}</span>
              <button
                onClick={(e) => onFavoriteClick(e, term)}
                className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                aria-label="Toggle favorite"
              >
                <Star
                  className={`w-3 h-3 ${isFavorite(term) ? "text-amber-500" : "text-muted-foreground/50"}`}
                  fill={isFavorite(term) ? "currentColor" : "none"}
                />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
