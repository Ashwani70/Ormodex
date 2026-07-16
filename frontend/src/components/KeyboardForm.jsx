import { useRef } from "react";
import useEnterNavigation from "@/hooks/useEnterNavigation";

/**
 * Drop-in wrapper that gives ANY form/modal body full keyboard-first data
 * entry with zero per-page boilerplate: Enter-as-Tab, Shift+Enter back,
 * Ctrl+Enter/Ctrl+S save, Ctrl+Shift+Enter/Ctrl+Shift+S save-and-new, Esc
 * cancel, auto-focus-first-field. This is the single reusable engine every
 * module page should render its form/modal body through instead of each
 * page re-deriving its own formRef + useEnterNavigation call (that
 * duplication was the SalesOrders-only rollout's shape; this component is
 * what makes the SAME logic apply everywhere without copy-paste).
 *
 * Usage — replace a plain wrapper div/form with this:
 *   <KeyboardForm as="form" id="so-form" onSubmit={submit}
 *     onSave={submit} onSaveAndNew={saveAndNew} onCancel={() => setOpen(false)}
 *     enabled={open} autoFocus className="grid ...">
 *     ...fields, including any <KeyboardGrid> line-item table...
 *   </KeyboardForm>
 *
 * `as` controls the rendered element ("form" for an actual <form>, "div" for
 * a plain container e.g. inside a modal that already has its own <form>).
 * All other props not listed below pass straight through to the element, so
 * this is safe to use as a near drop-in replacement for the div/form it
 * wraps (className, onSubmit, id, data-testid, ...).
 */
export default function KeyboardForm({
  as: Tag = "div",
  onSave,
  onSaveAndNew,
  onCancel,
  enabled = true,
  autoFocus = false,
  children,
  ...rest
}) {
  const ref = useRef(null);
  useEnterNavigation(ref, { onSave, onSaveAndNew, onCancel, enabled, autoFocus });
  return (
    <Tag ref={ref} {...rest}>
      {children}
    </Tag>
  );
}
