import { Children, cloneElement, isValidElement, useId, useRef, useCallback, forwardRef } from "react";
// Children.toArray, cloneElement, isValidElement, useId all used in Field()
import { ChevronRight, Loader2, Paperclip, X, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

// ── Loading primitives ────────────────────────────────────────
export function Spinner({ className = "" }) {
  return <Loader2 className={cn("animate-spin", className)} />;
}

// Shimmer skeleton block for loading states.
export function Skeleton({ className = "", style }) {
  return (
    <div
      className={cn("animate-pulse bg-muted", className)}
      style={{ borderRadius: "var(--radius-sm)", ...style }}
    />
  );
}

// Skeleton placeholder for a data table while rows load.
export function SkeletonTable({ rows = 5, cols = 4 }) {
  return (
    <div className="bg-card border border-border overflow-hidden" style={{ borderRadius: "var(--radius-lg)" }}>
      <div className="flex gap-4 px-4 py-3 bg-[#F1F5F9]">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-3.5 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4 px-4 py-3.5 border-t border-border">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className="h-3 flex-1" style={{ opacity: 1 - r * 0.12 }} />
          ))}
        </div>
      ))}
    </div>
  );
}

// ============================================================
// Aurora Design System — shared UI kit
// Clean, professional, information-dense. Every screen inherits
// these primitives so masters, invoices, stock, reports and
// dashboards stay visually consistent.
// ============================================================

export function PageHeader({ eyebrow, title, description, actions, children }) {
  return (
    <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between border-b border-border pb-5">
      <div>
        {eyebrow && (
          <div className="label-overline mb-2 flex items-center gap-1.5">
            <ChevronRight className="w-3 h-3 text-primary" />
            {eyebrow}
          </div>
        )}
        <h1
          data-testid="page-title"
          className="font-display font-bold text-[28px] leading-tight tracking-tight text-foreground"
        >
          {title}
        </h1>
        {description && (
          <p className="mt-2 text-sm text-muted-foreground max-w-2xl">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      {children}
    </div>
  );
}

export function StatTile({ label, value, sub, accent = false, testid }) {
  return (
    <div
      data-testid={testid}
      className={cn(
        "bg-card text-card-foreground border border-border p-5 transition-all hover:shadow-md hover:-translate-y-0.5",
        accent && "border-primary/40"
      )}
      style={{ borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-sm)" }}
    >
      <div className="label-overline text-muted-foreground">{label}</div>
      <div
        className={cn(
          "mt-2 font-display font-bold text-2xl sm:text-3xl tabular",
          accent ? "text-primary" : "text-foreground"
        )}
      >
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

// Generic surface card — the canonical container for module content.
export const Card = forwardRef(function Card({ children, className = "", padded = true, style }, ref) {
  return (
    <div
      ref={ref}
      className={cn("bg-card text-card-foreground border border-border", padded && "p-6", className)}
      style={{ borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-sm)", ...style }}
    >
      {children}
    </div>
  );
});

export function SectionTitle({ children, action }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h2 className="font-display font-semibold text-lg tracking-tight text-foreground flex items-center gap-2.5">
        <span className="inline-block w-1.5 h-5 rounded-full bg-primary" />
        {children}
      </h2>
      {action}
    </div>
  );
}

// ── Status badges ─────────────────────────────────────────────
// Pill-shaped, soft-tinted with readable dark text per Aurora spec.
const BADGE_TONES = {
  success: "bg-[#DCFCE7] text-[#166534]",
  warning: "bg-[#FEF3C7] text-[#92400E]",
  danger: "bg-[#FEE2E2] text-[#991B1B]",
  info: "bg-[#DBEAFE] text-[#1E40AF]",
  neutral: "bg-[#CCFBF1] text-[#115E59]",
};

const STATUS_TONE = {
  NEW: "info", CONTACTED: "info", QUOTED: "warning", WON: "success", LOST: "danger",
  DRAFT: "neutral", SENT: "info", RECEIVED: "success", CANCELLED: "danger",
  ACCEPTED: "success", REJECTED: "danger", PENDING: "warning", CONFIRMED: "info",
  DISPATCHED: "neutral", DELIVERED: "success", UNPAID: "danger", PARTIAL: "warning",
  PAID: "success", IN_TRANSIT: "info", COMPLETED: "success", OVERDUE: "danger",
};

export function Badge({ tone = "neutral", children, className = "" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-1 text-xs font-semibold rounded-full",
        BADGE_TONES[tone] || BADGE_TONES.neutral,
        className
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }) {
  const tone = STATUS_TONE[status] || "neutral";
  return <Badge tone={tone}>{status}</Badge>;
}

// Verification status pill (GST / PAN status etc). Maps the free-text status to
// a readable light-theme tone: ACTIVE/VERIFIED → green, blank/UNVERIFIED →
// neutral grey, anything else (INACTIVE/INVALID/…) → red. Replaces the old
// dark-theme bg-*-950 / text-*-400 pills that washed out on the light theme.
const STATE_PILL_OK = ["ACTIVE", "VERIFIED", "VALID", "YES"];
export function StatePill({ value, placeholder = "UNVERIFIED", className = "" }) {
  const v = (value || "").toString().trim().toUpperCase();
  let tone = "danger";
  if (!v) tone = "neutral";
  else if (STATE_PILL_OK.includes(v)) tone = "success";
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-1 text-[10px] font-mono font-bold uppercase tracking-wide rounded-md",
        BADGE_TONES[tone],
        className
      )}
    >
      {value || placeholder}
    </span>
  );
}

// ── Buttons ───────────────────────────────────────────────────
const BTN_BASE =
  "inline-flex items-center justify-center gap-2 font-medium text-sm transition-all duration-200 cursor-pointer focus-visible:outline-none";
// True-disabled (not loading) → muted flat fill with readable muted text,
// which holds contrast better than dropping opacity on a saturated fill.
const BTN_DISABLED = "!bg-muted !text-muted-foreground !border-transparent cursor-not-allowed !translate-y-0";
// Loading → keep the variant color, just dim slightly and block interaction.
const BTN_LOADING = "opacity-80 cursor-wait !translate-y-0";

export function PrimaryButton({ children, onClick, type = "submit", testid, className = "", disabled, loading, icon: Icon, style, form }) {
  return (
    <button
      type={type}
      onClick={onClick}
      data-testid={testid}
      form={form}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        BTN_BASE,
        "h-[46px] px-4 bg-primary text-primary-foreground hover:bg-[var(--primary-hover)] hover:-translate-y-px",
        loading && BTN_LOADING,
        disabled && !loading && BTN_DISABLED,
        className
      )}
      style={{ borderRadius: "var(--radius-md)", ...style }}
    >
      {loading ? <Spinner className="w-4 h-4" /> : Icon && <Icon className="w-4 h-4" />}
      {children}
    </button>
  );
}

export function SecondaryButton({ children, onClick, testid, className = "", icon: Icon, danger, disabled, loading, type = "button", style }) {
  return (
    <button
      type={type}
      onClick={onClick}
      data-testid={testid}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        BTN_BASE,
        "h-[46px] px-4 border bg-surface hover:-translate-y-px",
        danger
          ? "border-[var(--danger)]/40 text-[var(--danger)] hover:border-[var(--danger)] hover:bg-[#FEE2E2]"
          : "border-border text-foreground hover:border-[var(--border-strong)]",
        loading && BTN_LOADING,
        disabled && !loading && BTN_DISABLED,
        className
      )}
      style={{ borderRadius: "var(--radius-md)", background: danger ? undefined : "var(--surface)", ...style }}
    >
      {loading ? <Spinner className="w-4 h-4" /> : Icon && <Icon className="w-4 h-4" />}
      {children}
    </button>
  );
}

export function SuccessButton({ children, onClick, testid, className = "", icon: Icon, disabled, loading, type = "submit", style }) {
  return (
    <button
      type={type}
      onClick={onClick}
      data-testid={testid}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        BTN_BASE,
        "h-[46px] px-4 bg-accent text-accent-foreground hover:bg-[var(--accent-hover)] hover:-translate-y-px",
        loading && BTN_LOADING,
        disabled && !loading && BTN_DISABLED,
        className
      )}
      style={{ borderRadius: "var(--radius-md)", ...style }}
    >
      {loading ? <Spinner className="w-4 h-4" /> : Icon && <Icon className="w-4 h-4" />}
      {children}
    </button>
  );
}

// ── Form controls ─────────────────────────────────────────────
const FIELD_BASE =
  "w-full bg-surface border text-foreground text-sm placeholder:text-muted-foreground transition-[border-color,box-shadow] duration-150 focus:outline-none disabled:opacity-60 disabled:cursor-not-allowed disabled:bg-muted";
const FIELD_OK = "border-input focus:border-primary focus:ring-[3px] focus:ring-primary/15";
const FIELD_ERR = "border-[var(--danger)] focus:border-[var(--danger)] focus:ring-[3px] focus:ring-[rgba(239,68,68,0.15)]";

export const Input = forwardRef(function Input({ error, className, style, ...props }, ref) {
  return (
    <input
      ref={ref}
      {...props}
      aria-invalid={error ? true : undefined}
      className={cn(FIELD_BASE, error ? FIELD_ERR : FIELD_OK, "h-[46px] px-3", className)}
      style={{ borderRadius: "var(--radius-md)", background: "var(--surface)", ...style }}
    />
  );
});

/**
 * NumericInput — the single numeric input for the entire ERP.
 *
 * Behaviour contract:
 *  - value prop is the *raw* state value: a number, "", or null/undefined.
 *  - While the user is actively typing the raw text is kept as-is (allows "-", "0.", etc.)
 *  - On blur: formats with Indian locale thousands separator; notifies onChange with
 *    the numeric value (or "" when the field is empty so parent state stays clean).
 *  - onChange receives a numeric value OR "" — never a formatted string.
 *  - Backspace leaves the field empty (no auto-fill with 0).
 *  - Cursor position never jumps because we use inputMode="decimal" + text type.
 *  - Works inside a <Field> label wrapper.
 */
export const NumericInput = forwardRef(function NumericInput({
  value,
  onChange,
  onBlur,
  onKeyDown,
  error,
  className,
  style,
  decimals = 2,
  min,
  max,
  placeholder = "",
  disabled,
  readOnly,
  tabIndex,
  autoFocus,
  "data-testid": testid,
  id,
  name,
  align = "right",
  // compact = true renders without the tall h-[46px] (for line-item table cells)
  compact = false,
}, ref) {
  // displayValue holds the string the <input> shows. We keep it uncontrolled
  // during active typing to avoid React controlled-input cursor-jump: we only
  // push formatted values on blur, raw text on change. `ref` is forwarded
  // (not kept internally) so callers — e.g. useGridKeyNav's registerCell —
  // can focus/select this input directly, the same as a plain <input>.

  // Convert prop value to a display string (no formatting while editing).
  // Called once on first render and when value changes from outside.
  const toDisplay = useCallback(
    (v) => {
      if (v === "" || v === null || v === undefined) return "";
      const n = Number(v);
      if (Number.isNaN(n)) return String(v);
      return String(v);
    },
    []
  );

  const handleChange = useCallback(
    (e) => {
      const raw = e.target.value;
      // Allow: empty string, digits, one decimal point, leading minus
      // Reject everything else silently.
      if (raw !== "" && !/^-?\d*\.?\d*$/.test(raw)) return;
      // Pass the raw string up — parent stores it as-is while editing.
      // Parent should store as string during edit and convert on save.
      onChange?.(raw === "" ? "" : raw);
    },
    [onChange]
  );

  const handleBlur = useCallback(
    (e) => {
      const raw = String(value ?? "").trim();
      if (raw === "" || raw === "-") {
        onChange?.("");
        onBlur?.(e);
        return;
      }
      const n = parseFloat(raw);
      if (Number.isNaN(n)) {
        onChange?.("");
        onBlur?.(e);
        return;
      }
      // Clamp
      let clamped = n;
      if (min !== undefined && clamped < min) clamped = min;
      if (max !== undefined && clamped > max) clamped = max;
      // Notify with the numeric value (not string) so saves get a real number.
      onChange?.(clamped);
      onBlur?.(e);
    },
    [value, onChange, onBlur, min, max]
  );

  const displayVal = toDisplay(value);

  return (
    <input
      ref={ref}
      id={id}
      name={name}
      data-testid={testid}
      // Use text type — type="number" causes browser-native spinner arrows,
      // prevents custom formatting, and causes cursor jump bugs on Android.
      type="text"
      // Mobile numeric keyboard with decimal point.
      inputMode="decimal"
      value={displayVal}
      onChange={handleChange}
      onBlur={handleBlur}
      onKeyDown={onKeyDown}
      disabled={disabled}
      readOnly={readOnly}
      tabIndex={tabIndex}
      autoFocus={autoFocus}
      placeholder={placeholder}
      aria-invalid={error ? true : undefined}
      className={cn(
        FIELD_BASE,
        error ? FIELD_ERR : FIELD_OK,
        compact ? "h-8 px-2 py-1 text-xs" : "h-[46px] px-3",
        align === "right" && "text-right",
        "tabular-nums font-mono",
        className
      )}
      style={{ borderRadius: "var(--radius-md)", background: "var(--surface)", ...style }}
    />
  );
});

export function Textarea({ error, className, style, ...props }) {
  return (
    <textarea
      {...props}
      aria-invalid={error ? true : undefined}
      className={cn(FIELD_BASE, error ? FIELD_ERR : FIELD_OK, "px-3 py-2.5", className)}
      style={{ borderRadius: "var(--radius-md)", background: "var(--surface)", ...style }}
    />
  );
}

export const Select = forwardRef(function Select({ error, className, style, ...props }, ref) {
  return (
    <select
      ref={ref}
      {...props}
      aria-invalid={error ? true : undefined}
      className={cn(FIELD_BASE, error ? FIELD_ERR : FIELD_OK, "h-[46px] px-3", className)}
      style={{ borderRadius: "var(--radius-md)", background: "var(--surface)", ...style }}
    />
  );
});

// Field wraps a control with a label, optional hint, and an error message.
// Pass `error` to render the validation message in danger color. The message
// is linked to the control via aria-describedby so screen readers announce it,
// and the `error` flag is forwarded to the control for its visual state.
export function Field({ label, children, required, hint, error }) {
  const msgId = useId();
  const arr = Children.toArray(children);
  // Only enhance when the field wraps exactly one element control; otherwise
  // render children as-is (defensive — some callers pass text or multiple nodes).
  const single = arr.length === 1 && isValidElement(arr[0]) ? arr[0] : null;
  const control = single
    ? cloneElement(single, {
        error: single.props.error ?? (error ? true : undefined),
        "aria-describedby":
          cn(single.props["aria-describedby"], (error || hint) && msgId) || undefined,
        "aria-required": required || single.props["aria-required"] || undefined,
      })
    : children;

  return (
    <label className="block">
      {label && (
        <span className="label-overline mb-2 block">
          {label} {required && <span className="text-primary">*</span>}
        </span>
      )}
      {control}
      {error ? (
        <span id={msgId} className="mt-1.5 block text-xs font-medium text-[var(--danger)]">
          {error}
        </span>
      ) : hint ? (
        <span id={msgId} className="mt-1.5 block text-xs text-muted-foreground">
          {hint}
        </span>
      ) : null}
    </label>
  );
}

export function EmptyState({ message = "No data yet", action }) {
  return (
    <div
      className="border border-dashed border-border p-12 flex flex-col items-center justify-center text-center bg-card"
      style={{ borderRadius: "var(--radius-lg)" }}
    >
      <div className="w-12 h-1.5 hazard-stripe mb-4" />
      <div className="font-display font-semibold text-foreground mb-1">{message}</div>
      <div className="text-xs text-muted-foreground mb-4">
        Add records to populate this module
      </div>
      {action}
    </div>
  );
}

// ============================================================
// Enterprise transaction-form building blocks
// Grouped sections, sticky summaries, attachments and audit —
// the shared shape every transaction screen (PO/SO/Invoice/…)
// should compose, so they all read as one product.
// ============================================================

// A titled, bordered group inside a form. `icon` and `description` are optional;
// `actions` renders top-right (e.g. an "Add row" button). Children get a
// responsive grid by default unless `grid={false}`.
export function FormSection({ title, description, icon: Icon, actions, children, grid = true, cols = 2, className = "" }) {
  const colClass = { 1: "md:grid-cols-1", 2: "md:grid-cols-2", 3: "md:grid-cols-3", 4: "md:grid-cols-4" }[cols] || "md:grid-cols-2";
  return (
    <section
      className={cn("bg-card border border-border", className)}
      style={{ borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-sm)" }}
    >
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-border px-6 py-4">
          <div className="flex items-center gap-2.5 min-w-0">
            {Icon && (
              <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Icon className="h-4 w-4" />
              </span>
            )}
            <div className="min-w-0">
              {title && <h3 className="font-display font-semibold text-sm text-foreground truncate">{title}</h3>}
              {description && <p className="text-xs text-muted-foreground truncate">{description}</p>}
            </div>
          </div>
          {actions && <div className="flex flex-shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn("p-6", grid && `grid grid-cols-1 ${colClass} gap-x-5 gap-y-4`)}>
        {children}
      </div>
    </section>
  );
}

// A single label/value line for the SummaryCard.
export function SummaryRow({ label, value, strong, tone }) {
  const toneClass =
    tone === "success" ? "text-[var(--success)]"
    : tone === "danger" ? "text-[var(--danger)]"
    : tone === "warning" ? "text-[var(--warning)]"
    : strong ? "text-foreground" : "text-foreground";
  return (
    <div className="flex items-center justify-between gap-4">
      <span className={cn("text-muted-foreground", strong && "font-semibold text-foreground")}>{label}</span>
      <span className={cn("tabular", strong ? "font-display font-bold" : "font-medium", toneClass)}>{value}</span>
    </div>
  );
}

// Right-rail money summary for transaction screens. Pass `rows` (array of
// {label, value, tone, strong, dividerBefore}) and an optional `total` row.
// `sticky` keeps it pinned on tall forms (desktop).
export function SummaryCard({ title = "Summary", rows = [], total, footer, sticky = false, className = "" }) {
  return (
    <div
      className={cn("bg-card border border-border", sticky && "lg:sticky lg:top-4", className)}
      style={{ borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-sm)" }}
    >
      {title && (
        <div className="border-b border-border px-5 py-3.5">
          <h3 className="font-display font-semibold text-sm text-foreground">{title}</h3>
        </div>
      )}
      <div className="space-y-2.5 p-5 text-sm">
        {rows.map((r, i) => (
          <div key={i}>
            {r.dividerBefore && <div className="my-2.5 border-t border-border" />}
            <SummaryRow {...r} />
          </div>
        ))}
        {total && (
          <div className="mt-1 border-t border-border pt-3">
            <SummaryRow {...total} strong />
          </div>
        )}
      </div>
      {footer && <div className="border-t border-border px-5 py-3 bg-muted/40">{footer}</div>}
    </div>
  );
}

// Attachments picker + list. Controlled: pass `files` (array of {name,size,url?})
// and `onAdd(FileList)` / `onRemove(index)`. Purely presentational — wire it to
// your existing upload flow; it does not change any API behaviour.
export function AttachmentsField({ files = [], onAdd, onRemove, accept, disabled }) {
  const id = useId();
  const fmtSize = (b) => (b == null ? "" : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
  return (
    <div className="space-y-3">
      <label
        htmlFor={id}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-border bg-[var(--bg)] px-4 py-6 text-center transition-colors hover:border-primary hover:bg-primary/5",
          disabled && "pointer-events-none opacity-60"
        )}
      >
        <Paperclip className="h-5 w-5 text-muted-foreground" />
        <span className="text-sm font-medium text-foreground">Click to attach files</span>
        <span className="text-xs text-muted-foreground">PDF, images or documents</span>
        <input
          id={id}
          type="file"
          multiple
          accept={accept}
          disabled={disabled}
          className="hidden"
          onChange={(e) => { onAdd?.(e.target.files); e.target.value = ""; }}
        />
      </label>
      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((f, i) => (
            <li key={i} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-3 py-2 text-sm">
              <span className="flex min-w-0 items-center gap-2">
                <Paperclip className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
                {f.url ? (
                  <a href={f.url} target="_blank" rel="noreferrer" className="truncate text-primary hover:underline">{f.name}</a>
                ) : (
                  <span className="truncate text-foreground">{f.name}</span>
                )}
                {f.size != null && <span className="flex-shrink-0 text-xs text-muted-foreground">{fmtSize(f.size)}</span>}
              </span>
              {onRemove && (
                <button type="button" onClick={() => onRemove(i)} aria-label={`Remove ${f.name}`}
                  className="flex-shrink-0 rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-[var(--danger)]">
                  <X className="h-4 w-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// Vertical audit/approval timeline. `entries`: [{ actor, action, at, note }].
// Read-only presentation of history your backend already returns.
export function AuditTrail({ entries = [], emptyText = "No history yet." }) {
  if (!entries.length) {
    return <p className="text-sm text-muted-foreground">{emptyText}</p>;
  }
  return (
    <ol className="relative space-y-5 border-l border-border pl-5">
      {entries.map((e, i) => (
        <li key={i} className="relative">
          <span className="absolute -left-[27px] flex h-5 w-5 items-center justify-center rounded-full border border-border bg-card text-muted-foreground">
            <Clock className="h-3 w-3" />
          </span>
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
            <span className="text-sm font-medium text-foreground">{e.action}</span>
            {e.at && <span className="text-xs text-muted-foreground">{e.at}</span>}
          </div>
          {e.actor && <div className="text-xs text-muted-foreground">by {e.actor}</div>}
          {e.note && <p className="mt-1 text-sm text-foreground">{e.note}</p>}
        </li>
      ))}
    </ol>
  );
}
