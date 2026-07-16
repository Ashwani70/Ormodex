import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Command as CommandPrimitive } from "cmdk";
import { Warehouse as WarehouseIcon, MapPin } from "lucide-react";
import { Dialog, DialogPortal, DialogOverlay } from "@/components/ui/dialog";
import { useModalStackRegistration } from "@/context/ModalStackContext";
import api from "@/lib/api";

/**
 * Global Alt+W "Warehouse Picker" — a keyboard-only, cross-page overlay for
 * jumping straight to a warehouse's detail view, matching the Ctrl+K Global
 * Search's keyboard model (type to filter, Arrow to move, Enter to open, Esc
 * to close — all free from cmdk's CommandPrimitive, same as GlobalSearch.jsx).
 *
 * Scope note: this app has no "active warehouse for the current form" concept
 * anywhere today (each voucher/grid page keeps its own local godown_id
 * state) — so this picker is a fast NAVIGATE-to-warehouse tool (opens
 * /godowns?detail=<id>, the same deep-link convention Customers/Products use),
 * not a value-picker that fills in a field on whatever page you're on. If a
 * true "select warehouse for this line/document" concept gets added later,
 * this component's list+search UI is what a field-scoped variant would reuse.
 */
export default function WarehousePicker({ open, onClose }) {
  const [query, setQuery] = useState("");
  const [warehouses, setWarehouses] = useState([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);
  const navigate = useNavigate();

  useModalStackRegistration(open);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    const t = setTimeout(() => inputRef.current?.focus(), 60);
    setLoading(true);
    api.get("/inventory/v2/godowns")
      .then((res) => {
        const list = Array.isArray(res.data) ? res.data : res.data?.items || [];
        setWarehouses(list);
      })
      .catch(() => setWarehouses([]))
      .finally(() => setLoading(false));
    return () => clearTimeout(t);
  }, [open]);

  const goTo = (id) => {
    navigate(`/godowns?detail=${id}`);
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogPortal>
        <DialogOverlay className="bg-black/50 backdrop-blur-[2px]" />
        <div className="fixed inset-0 z-[150] flex items-start justify-center pt-[12vh] px-4">
          <div className="w-full max-w-lg bg-card border border-border shadow-2xl rounded-lg overflow-hidden">
            <CommandPrimitive shouldFilter loop className="flex flex-col">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
                <WarehouseIcon className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                <CommandPrimitive.Input
                  ref={inputRef}
                  value={query}
                  onValueChange={setQuery}
                  placeholder="Jump to a warehouse… (Alt+W)"
                  className="flex-1 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground"
                />
              </div>
              <CommandPrimitive.List className="max-h-[50vh] overflow-y-auto overscroll-contain p-2">
                <CommandPrimitive.Empty className="py-8 text-center text-sm text-muted-foreground">
                  {loading ? "Loading warehouses…" : "No warehouses found"}
                </CommandPrimitive.Empty>
                {warehouses.map((w) => (
                  <CommandPrimitive.Item
                    key={w.id}
                    value={`${w.name} ${w.code || ""} ${w.city || ""}`}
                    onSelect={() => goTo(w.id)}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-md cursor-pointer text-sm data-[selected=true]:bg-primary/10 data-[selected=true]:text-primary"
                  >
                    <WarehouseIcon className="w-4 h-4 flex-shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div className="font-medium truncate">{w.name}</div>
                      {(w.city || w.code) && (
                        <div className="flex items-center gap-1 text-xs text-muted-foreground truncate">
                          <MapPin className="w-3 h-3 flex-shrink-0" />
                          {[w.code, w.city].filter(Boolean).join(" · ")}
                        </div>
                      )}
                    </div>
                  </CommandPrimitive.Item>
                ))}
              </CommandPrimitive.List>
              <div className="px-4 py-2 border-t border-border text-[10px] font-mono text-muted-foreground flex items-center gap-3">
                <span>↑↓ navigate</span>
                <span>↵ open</span>
                <span>esc close</span>
              </div>
            </CommandPrimitive>
          </div>
        </div>
      </DialogPortal>
    </Dialog>
  );
}
