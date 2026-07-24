import { useCallback, useMemo, useState } from "react";

/**
 * Open/closed state for a page's set of CollapsibleFormSections, persisted to
 * localStorage per `storageKey` so a section a user left open stays open next
 * time they open this form ("remember last expanded state").
 *
 * Usage:
 *   const acc = useAccordionState("po-form-sections", { basic: true, items: true });
 *   <CollapsibleFormSection open={acc.isOpen("vendor")} onOpenChange={() => acc.toggle("vendor")} .../>
 *   <SecondaryButton onClick={acc.expandAll}>Expand All</SecondaryButton>
 */
export default function useAccordionState(storageKey, defaults = {}) {
  const [open, setOpen] = useState(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      return raw ? { ...defaults, ...JSON.parse(raw) } : { ...defaults };
    } catch {
      return { ...defaults };
    }
  });

  const persist = useCallback((next) => {
    setOpen(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {
      // Storage full/unavailable (private browsing etc.) — in-memory state still works.
    }
  }, [storageKey]);

  const isOpen = useCallback((id) => !!open[id], [open]);

  const toggle = useCallback((id) => {
    persist({ ...open, [id]: !open[id] });
  }, [open, persist]);

  const ids = useMemo(() => Object.keys(defaults), [defaults]);

  const expandAll = useCallback(() => {
    persist(Object.fromEntries(ids.map((id) => [id, true])));
  }, [ids, persist]);

  const collapseAll = useCallback(() => {
    persist(Object.fromEntries(ids.map((id) => [id, false])));
  }, [ids, persist]);

  return { isOpen, toggle, expandAll, collapseAll };
}
