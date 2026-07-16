import { X } from "lucide-react";
import { useEffect } from "react";
import { createPortal } from "react-dom";
import { useModalStackRegistration } from "@/context/ModalStackContext";

/**
 * SlideOver — an enterprise-grade, full-screen slide-over panel that enters from
 * the right. Header and footer are sticky; only the body scrolls. Designed for
 * rich, multi-tab data-entry surfaces (SAP B1 / NetSuite style).
 *
 * Props:
 *  - open, onClose
 *  - title, subtitle, icon (lucide component)
 *  - headerExtra   — nodes rendered on the right of the header (e.g. status badge)
 *  - tabs          — [{ id, label, icon }]; renders a sticky tab-rail
 *  - activeTab, onTabChange
 *  - footer        — sticky footer actions
 *  - width         — "full" (default, ~1120px) | "wide" (100vw) | "half"
 *  - onSubmit      — form submit handler (Ctrl/Cmd+S is wired to click the primary)
 *  - testid
 */
export default function SlideOver({
  open,
  onClose,
  title,
  subtitle,
  icon: Icon,
  headerExtra,
  tabs,
  activeTab,
  onTabChange,
  footer,
  children,
  width = "full",
  bodyClassName = "",
  testid,
}) {
  useModalStackRegistration(open);

  useEffect(() => {
    const onEsc = (e) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      onClose?.();
    };
    if (open) document.addEventListener("keydown", onEsc, true);
    return () => document.removeEventListener("keydown", onEsc, true);
  }, [open, onClose]);

  // Lock body scroll while open.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (!open) return null;

  const widths = {
    full: "w-full sm:max-w-[1120px]",
    wide: "w-full",
    half: "w-full sm:max-w-[640px]",
  };

  return createPortal(
    <div
      data-testid={testid}
      className="fixed inset-0 z-[60] flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-[2px] slideover-backdrop"
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={`relative flex h-full flex-col bg-background text-foreground shadow-2xl slideover-panel ${widths[width]}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Sticky header */}
        <header className="flex flex-shrink-0 items-center justify-between gap-4 border-b border-border bg-card px-5 py-3.5 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            {Icon && (
              <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[10px] bg-primary/10 text-primary">
                <Icon className="h-5 w-5" />
              </span>
            )}
            <div className="min-w-0">
              <h2 className="truncate font-display text-lg font-bold leading-tight text-foreground">
                {title}
              </h2>
              {subtitle && (
                <p className="truncate text-xs text-muted-foreground">{subtitle}</p>
              )}
            </div>
          </div>
          <div className="flex flex-shrink-0 items-center gap-3">
            {headerExtra}
            <button
              type="button"
              data-testid="slideover-close"
              onClick={onClose}
              aria-label="Close"
              className="flex h-9 w-9 items-center justify-center rounded-[10px] border border-border bg-background text-muted-foreground transition-colors hover:border-primary hover:text-primary"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>

        {/* Sticky tab rail */}
        {tabs?.length > 0 && (
          <nav className="flex flex-shrink-0 gap-1 overflow-x-auto border-b border-border bg-card px-3 sm:px-4">
            {tabs.map((t) => {
              const TabIcon = t.icon;
              const active = t.id === activeTab;
              return (
                <button
                  key={t.id}
                  type="button"
                  data-testid={`wh-tab-${t.id}`}
                  onClick={() => onTabChange?.(t.id)}
                  className={`relative flex items-center gap-1.5 whitespace-nowrap px-3 py-2.5 text-sm font-medium transition-colors ${
                    active
                      ? "text-primary"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {TabIcon && <TabIcon className="h-4 w-4" />}
                  {t.label}
                  {t.badge != null && (
                    <span className="ml-0.5 rounded-full bg-primary/10 px-1.5 text-[10px] font-bold text-primary">
                      {t.badge}
                    </span>
                  )}
                  {active && (
                    <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-primary" />
                  )}
                </button>
              );
            })}
          </nav>
        )}

        {/* Scrolling body */}
        <div className={`flex-1 overflow-y-auto overflow-x-hidden ${bodyClassName || "p-5 sm:p-6"}`}>
          {children}
        </div>

        {/* Sticky footer */}
        {footer && (
          <footer className="flex flex-shrink-0 flex-wrap items-center justify-end gap-3 border-t border-border bg-card px-5 py-3.5 sm:px-6">
            {footer}
          </footer>
        )}
      </div>
    </div>,
    document.body
  );
}
