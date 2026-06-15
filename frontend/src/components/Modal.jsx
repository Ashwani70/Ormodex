import { X } from "lucide-react";
import { useEffect } from "react";

export default function Modal({ open, onClose, title, children, footer, size = "md", testid }) {
  useEffect(() => {
    const onEsc = (e) => e.key === "Escape" && onClose?.();
    if (open) document.addEventListener("keydown", onEsc);
    return () => document.removeEventListener("keydown", onEsc);
  }, [open, onClose]);

  if (!open) return null;

  const widths = {
    sm: "max-w-md",
    md: "max-w-2xl",
    lg: "max-w-4xl",
    xl: "max-w-6xl",
  };

  return (
    <div
      data-testid={testid}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/80 px-4 py-8"
      onClick={onClose}
    >
      <div
        className={`industrial-corner relative w-full ${widths[size]} bg-card border border-border text-foreground shadow-2xl`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="hazard-stripe h-1.5 w-full" />
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h3 className="font-display font-bold text-foreground text-lg">{title}</h3>
          <button
            data-testid="modal-close"
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center border border-border text-muted-foreground hover:text-primary hover:border-primary transition-colors bg-background"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5 max-h-[70vh] overflow-y-auto">{children}</div>
        {footer && (
          <div className="border-t border-border px-5 py-3 flex items-center justify-end gap-2 bg-muted/40">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
