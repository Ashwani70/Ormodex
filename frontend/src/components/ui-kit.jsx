import { ChevronRight } from "lucide-react";

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
          className="font-display font-black text-3xl sm:text-4xl tracking-tight text-foreground"
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
      className={`industrial-corner border border-border bg-card text-card-foreground p-4 sm:p-5 transition-colors hover:border-primary ${
        accent ? "border-primary/50" : ""
      }`}
    >
      <div className="label-overline text-muted-foreground">
        {label}
      </div>
      <div
        className={`mt-2 font-display font-black text-2xl sm:text-3xl tabular ${
          accent ? "text-primary" : "text-foreground"
        }`}
      >
        {value}
      </div>
      {sub && (
        <div className={`mt-1 text-xs ${accent ? "text-muted-foreground" : "text-muted-foreground/80"}`}>
          {sub}
        </div>
      )}
    </div>
  );
}

export function SectionTitle({ children, action }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h2 className="font-display font-bold text-lg uppercase tracking-tight text-foreground flex items-center gap-2">
        <span className="inline-block w-2 h-4 bg-primary" />
        {children}
      </h2>
      {action}
    </div>
  );
}

export function StatusBadge({ status }) {
  const map = {
    NEW: "bg-zinc-800 text-zinc-200 border-zinc-700",
    CONTACTED: "bg-blue-950 text-blue-400 border-blue-900",
    QUOTED: "bg-yellow-950 text-yellow-400 border-yellow-700",
    WON: "bg-green-950 text-green-400 border-green-700",
    LOST: "bg-red-950 text-red-400 border-red-700",
    DRAFT: "bg-zinc-800 text-zinc-300 border-zinc-700",
    SENT: "bg-blue-950 text-blue-400 border-blue-900",
    RECEIVED: "bg-green-950 text-green-400 border-green-700",
    CANCELLED: "bg-red-950 text-red-400 border-red-700",
    ACCEPTED: "bg-green-950 text-green-400 border-green-700",
    REJECTED: "bg-red-950 text-red-400 border-red-700",
    PENDING: "bg-yellow-950 text-yellow-400 border-yellow-700",
    CONFIRMED: "bg-blue-950 text-blue-400 border-blue-900",
    DISPATCHED: "bg-purple-950 text-purple-400 border-purple-700",
    DELIVERED: "bg-green-950 text-green-400 border-green-700",
    UNPAID: "bg-red-950 text-red-400 border-red-700",
    PARTIAL: "bg-yellow-950 text-yellow-400 border-yellow-700",
    PAID: "bg-green-950 text-green-400 border-green-700",
    IN_TRANSIT: "bg-blue-950 text-blue-400 border-blue-900",
  };
  const cls = map[status] || "bg-zinc-800 text-zinc-300 border-zinc-700";
  return (
    <span
      className={`inline-block px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider border ${cls}`}
    >
      {status}
    </span>
  );
}

export function PrimaryButton({ children, onClick, type = "button", testid, className = "", disabled, icon: Icon, style }) {
  return (
    <button
      type={type}
      onClick={onClick}
      data-testid={testid}
      disabled={disabled}
      className={`inline-flex items-center gap-2 bg-primary hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground text-primary-foreground font-mono font-semibold uppercase tracking-wider text-xs px-4 py-2.5 transition-colors ${className}`}
      style={{ borderRadius: "var(--radius)", ...style }}
    >
      {Icon && <Icon className="w-4 h-4" />}
      {children}
    </button>
  );
}

export function SecondaryButton({ children, onClick, testid, className = "", icon: Icon, danger, style }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      className={`inline-flex items-center gap-2 border ${
        danger
          ? "border-red-900 text-red-400 hover:border-red-500 hover:text-red-300"
          : "border-border text-muted-foreground hover:border-primary hover:text-primary"
      } bg-transparent font-mono uppercase tracking-wider text-[11px] px-3 py-2 transition-colors ${className}`}
      style={{ borderRadius: "var(--radius)", ...style }}
    >
      {Icon && <Icon className="w-3.5 h-3.5" />}
      {children}
    </button>
  );
}

export function Input(props) {
  return (
    <input
      {...props}
      className={`w-full bg-background border border-input text-foreground text-sm px-4 py-2.5 placeholder:text-muted-foreground focus:border-primary focus:outline-none transition-colors ${
        props.className || ""
      }`}
      style={{ borderRadius: "var(--radius)", ...props.style }}
    />
  );
}

export function Textarea(props) {
  return (
    <textarea
      {...props}
      className={`w-full bg-background border border-input text-foreground text-sm px-4 py-2.5 placeholder:text-muted-foreground focus:border-primary focus:outline-none transition-colors ${
        props.className || ""
      }`}
      style={{ borderRadius: "var(--radius)", ...props.style }}
    />
  );
}

export function Select(props) {
  return (
    <select
      {...props}
      className={`w-full bg-background border border-input text-foreground text-sm px-4 py-2.5 focus:border-primary focus:outline-none transition-colors ${
        props.className || ""
      }`}
      style={{ borderRadius: "var(--radius)", ...props.style }}
    />
  );
}

export function Field({ label, children, required }) {
  return (
    <label className="block">
      <span className="label-overline mb-1.5 block">
        {label} {required && <span className="text-primary">*</span>}
      </span>
      {children}
    </label>
  );
}

export function EmptyState({ message = "No data yet", action }) {
  return (
    <div className="border border-dashed border-border p-12 flex flex-col items-center justify-center text-center">
      <div className="w-12 h-12 hazard-stripe mb-4" />
      <div className="font-display text-foreground mb-1">{message}</div>
      <div className="text-xs text-muted-foreground mb-4 font-mono uppercase tracking-wider">
        Add records to populate this module
      </div>
      {action}
    </div>
  );
}
