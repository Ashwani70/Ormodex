import { useCallback, useEffect, useRef } from "react";

/**
 * Generic "Enter acts like Tab" navigation engine for any form/modal — the
 * keyboard-first primitive every module page builds on (Tally Prime / SAP
 * Business One style data entry). Distinct from useGridKeyNav, which is
 * purpose-built for a row×column line-item grid where the cell layout is
 * known up front; this hook instead walks the LIVE DOM of a container ref, so
 * it works on any form shape without the caller having to model rows/cols —
 * plain field-by-field forms (Product master, Customer master, Settings...).
 *
 * Usage:
 *   const formRef = useRef(null);
 *   useEnterNavigation(formRef, { onSave, onSaveAndNew, onCancel, onQuickCreate });
 *   <div ref={formRef}> ...fields... </div>
 *
 * Behaviour (attached as a keydown listener on the container, capture phase
 * so it sees the event before a field's own onKeyDown, but a field can still
 * call e.stopPropagation() to opt out — ItemSearch's suggestion-list Enter
 * does exactly that by consuming the event itself first):
 *   Enter, Tab             → focus the next eligible field, select its value
 *   Shift+Enter, Shift+Tab → focus the previous eligible field
 *   Ctrl/Cmd+Enter, Ctrl/Cmd+S → onSave()
 *   Ctrl/Cmd+Shift+Enter, Ctrl/Cmd+Shift+S → onSaveAndNew()
 *   Alt+S                  → onSave() (second save convention, spec requirement)
 *   Ctrl/Cmd+Enter (inside a [data-quick-create="TYPE"] field) → onQuickCreate(type, field)
 *                           instead of onSave() — see below.
 *   Escape                → onCancel()
 *
 * Quick-create (Ctrl+Enter on a lookup field): mark a lookup widget's root
 * with data-quick-create="customer" (or "vendor"/"item"/etc) and pass
 * onQuickCreate to open a "create a new <type>" flow for whatever the user
 * has typed so far, without leaving the voucher — e.g. PartySearch/ItemSearch
 * wrap their input in such a root. This only intercepts Ctrl+Enter while
 * focus is INSIDE that field, so the form-level Ctrl+Enter=save meaning is
 * completely undisturbed everywhere else.
 *
 * Tab/Shift+Tab are aliased to Enter/Shift+Enter rather than left to native
 * browser tab order: native Tab order is the DOM's tabindex/document order,
 * which silently diverges from this hook's own "next eligible field" order
 * once a field is skipped for being hidden/disabled/readonly, or once a
 * dynamically-rendered/virtualized control changes the DOM between renders —
 * so intercepting Tab here keeps both keys behaving identically everywhere
 * (the spec's explicit requirement: "Tab: keep working exactly like Enter").
 *
 * "Eligible field" = a real form control that is visible, not disabled, not
 * readonly, and not explicitly opted out via data-enter-skip. Buttons and
 * links are skipped by default (Enter on a button already activates it
 * natively) unless data-enter-stop is set.
 *
 * Validation: before leaving a field via Enter/Tab, its HTML5 constraint
 * validity is checked (required/pattern/min/max/type=email/... — whatever the
 * field already declares; no parallel validation system to keep in sync).
 * A failing field calls the browser's native reportValidity(), which shows
 * the inline error bubble AND keeps focus — navigation simply does not
 * proceed. Opt a field out entirely with data-enter-no-validate.
 *
 * On <textarea>, plain Enter inserts a newline as usual (Tab still navigates
 * out) — only Shift+Enter's "previous field" and the Ctrl+Enter save combos
 * are intercepted there, so multi-line remarks/notes fields keep working
 * exactly like a normal textarea. Rich text editors, code editors, and any
 * genuinely contenteditable region (data-rich-text / data-code-editor, or
 * isContentEditable) are left with fully native key handling — this hook
 * never touches Enter/Tab inside them at all.
 *
 * Coexisting with useGridKeyNav: a line-item grid inside the same form
 * already has its own Enter/Arrow row×column navigation (row-complete,
 * insert/delete row) wired directly on each cell. Because this hook's
 * listener is capture-phase on the FORM, it would otherwise see every
 * keypress before the grid cell's own bubble-phase onKeyDown ever runs,
 * silently breaking the grid. Any element (or ancestor) carrying
 * `data-grid-managed` is skipped entirely here — Enter/Escape on it passes
 * through untouched for the grid's own handler to process. Mark a grid's
 * wrapping <table>/<tbody> with that attribute (see useGridKeyNav usage).
 */

const FIELD_SELECTOR = [
  "input:not([type=hidden])",
  "select",
  "textarea",
  "[contenteditable=true]",
  "[data-enter-field]",           // custom widgets (e.g. ItemSearch's input already matches "input" above, but a composite widget can opt in explicitly)
].join(",");

function isVisible(el) {
  if (!el) return false;
  if (el.hidden) return false;
  const style = window.getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
  // offsetParent is null for display:none and fixed-position-inside-hidden-ancestor;
  // getClientRects catches zero-size elements that are technically "visible".
  if (el.offsetParent === null && style.position !== "fixed") return false;
  return el.getClientRects().length > 0;
}

function isEligible(el) {
  if (!el) return false;
  if (el.disabled) return false;
  if (el.readOnly) return false;
  if (el.getAttribute("aria-hidden") === "true") return false;
  if (el.dataset && "enterSkip" in el.dataset) return false;
  if (el.closest("[data-grid-managed]")) return false;
  if (el.tabIndex === -1 && !el.hasAttribute("data-enter-field")) return false;
  return isVisible(el);
}

// Perf: querySelectorAll over the whole container is the expensive part of
// collectFields, not the per-element isEligible checks — so cache the RAW
// query result per container and only re-run the query when the container's
// subtree actually mutates (new/removed nodes), via one MutationObserver per
// hook instance. isEligible (visible/disabled/readonly) is still re-evaluated
// on every call from the cached list — those checks are cheap property reads,
// and this is what keeps a field that toggled hidden/disabled WITHOUT a DOM
// mutation (e.g. a class/style change, not a node add/remove) correctly
// excluded even between cache refreshes. Net effect: a keypress in a form
// with hundreds of fields costs a handful of property reads instead of a
// full-subtree DOM query, with no staleness window for structural changes.
const queryCache = new WeakMap(); // container -> raw NodeList-derived array

function invalidateQueryCache(container) {
  if (container) queryCache.delete(container);
}

function collectFields(container) {
  if (!container) return [];
  let raw = queryCache.get(container);
  if (!raw) {
    raw = Array.from(container.querySelectorAll(FIELD_SELECTOR));
    queryCache.set(container, raw);
  }
  return raw.filter(isEligible);
}

function focusAndSelect(el) {
  if (!el) return;
  el.focus();
  // Highlight the entire value on focus (spec requirement) — only meaningful
  // for text-like inputs; select() throws on some input types (checkbox etc).
  if (typeof el.select === "function") {
    try { el.select(); } catch { /* not a selectable input type — ignore */ }
  }
  // Bring the field into view even inside a scrollable panel/modal.
  el.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
}

// Standards-based validation: reuse the browser's own constraint-validation
// API (required/pattern/min/max/type=email/etc — whatever the field already
// declares) instead of inventing a parallel validation system. reportValidity()
// both returns pass/fail AND shows the browser's native inline bubble at the
// field, satisfying "show inline validation message" with zero extra UI code.
// A field opts out entirely via data-enter-no-validate (e.g. a field that's
// intentionally optional-looking but has some unrelated pattern attribute).
function isFieldValid(el) {
  if (!el) return true;
  if (el.dataset && "enterNoValidate" in el.dataset) return true;
  if (typeof el.reportValidity !== "function") return true; // custom widgets, contenteditable
  return el.reportValidity();
}

export default function useEnterNavigation(
  containerRef,
  { onSave, onSaveAndNew, onCancel, onQuickCreate, enabled = true, autoFocus = false } = {}
) {
  // Keep latest callbacks in refs so the listener doesn't need to be
  // re-attached (and therefore re-order in the capture chain) every render.
  const cbRef = useRef({});
  cbRef.current = { onSave, onSaveAndNew, onCancel, onQuickCreate };

  const focusFirst = useCallback(() => {
    const fields = collectFields(containerRef.current);
    if (fields[0]) focusAndSelect(fields[0]);
  }, [containerRef]);

  // Auto-focus the first eligible field once the container mounts — "the
  // user should never need to click with the mouse" (spec). Deferred one
  // frame so the container's children (often behind a modal transition) are
  // actually laid out and focusable by the time we query them.
  useEffect(() => {
    if (!enabled || !autoFocus) return;
    const raf = requestAnimationFrame(() => focusFirst());
    return () => cancelAnimationFrame(raf);
    // Intentionally runs once per mount (containerRef/focusFirst are stable
    // across the component's lifetime) — re-running on every render would
    // steal focus back from the user mid-edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Invalidate the field-query cache whenever the container's subtree
  // actually changes structurally (a line added/removed, a field's
  // disabled/hidden attribute flipped, a conditional section mounts). This is
  // the other half of collectFields' cache — see its comment for why this
  // keeps navigation correct without re-querying the DOM on every keypress.
  useEffect(() => {
    const container = containerRef.current;
    if (!container || typeof MutationObserver === "undefined") return;
    const observer = new MutationObserver(() => invalidateQueryCache(container));
    observer.observe(container, {
      childList: true, subtree: true,
      attributes: true, attributeFilter: ["disabled", "readonly", "hidden", "style", "class", "aria-hidden"],
    });
    return () => observer.disconnect();
  }, [containerRef]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !enabled) return;

    const handler = (e) => {
      const mod = e.ctrlKey || e.metaKey;
      const target = e.target;
      const isTextarea = target?.tagName === "TEXTAREA";
      const isRichText = target?.isContentEditable ||
        target?.closest?.("[data-rich-text],[data-code-editor]");

      // Let a grid-managed region (useGridKeyNav) handle its own Enter/Arrow/
      // Escape entirely — see the module docstring. Ctrl+Enter/Ctrl+Shift+Enter
      // save combos still fire from inside a grid cell (those aren't handled
      // by the grid), so only the grid's own keys are excluded here.
      const inGrid = target?.closest?.("[data-grid-managed]");
      if (inGrid && !mod) return;

      // Ctrl+Enter on a lookup field (ItemSearch/PartySearch, marked
      // data-quick-create) opens "create a new <master>" instead of saving
      // the form — this only fires while that field is focused, so it never
      // shadows the form-level Ctrl+Enter=save used everywhere else.
      if (mod && !e.shiftKey && e.key === "Enter") {
        const quickCreateHost = target?.closest?.("[data-quick-create]");
        if (quickCreateHost && cbRef.current.onQuickCreate) {
          e.preventDefault();
          cbRef.current.onQuickCreate(quickCreateHost.dataset.quickCreate, target);
          return;
        }
      }

      // Two equally-valid "save" conventions across the ERP families this
      // mirrors: Tally uses Ctrl+Enter, SAP Business One / NetSuite use
      // Ctrl+S. Both are supported everywhere rather than picking one.
      if (mod && e.shiftKey && (e.key === "Enter" || e.key.toLowerCase() === "s")) {
        e.preventDefault();
        cbRef.current.onSaveAndNew?.();
        return;
      }
      if (mod && (e.key === "Enter" || e.key.toLowerCase() === "s")) {
        e.preventDefault();
        cbRef.current.onSave?.();
        return;
      }
      // Alt+S — a second "save" convention some Tally-family users expect
      // alongside Ctrl+S/Ctrl+Enter (spec requirement); same handler as Ctrl+S.
      if (e.altKey && !mod && e.key.toLowerCase() === "s") {
        e.preventDefault();
        cbRef.current.onSave?.();
        return;
      }
      if (e.key === "Escape") {
        cbRef.current.onCancel?.();
        return;
      }

      // Rich text / code editors (data-rich-text, data-code-editor, or any
      // genuinely contenteditable region) keep 100% native key handling —
      // Enter/Tab must never be hijacked inside them (spec: "Do NOT override
      // Enter inside... rich text editor, code editor"). Ctrl+Enter above
      // still reaches them first to "finish editing" via onSave, matching
      // the spec's textarea-family exception.
      if (isRichText) return;

      if (e.key !== "Enter" && e.key !== "Tab") return;
      if (isTextarea && e.key === "Enter" && !e.shiftKey) {
        // Let a plain Enter insert a newline in multi-line fields — Tab still
        // navigates out of a textarea (see the docstring's Tab/Enter parity note).
        return;
      }

      // Validate before leaving the field — HTML5 constraint validation
      // (required/pattern/min/max/type=email/...) via the browser's own
      // reportValidity(), which also shows the native inline error bubble.
      // A failing field keeps focus and navigation does not proceed, per the
      // spec's "if validation fails, keep focus, do not move" requirement.
      if (!isFieldValid(target)) {
        e.preventDefault();
        return;
      }

      e.preventDefault();
      const fields = collectFields(container);
      const idx = fields.indexOf(target);
      if (idx === -1) {
        // Focus came from outside a tracked field (e.g. a custom widget) —
        // fall back to focusing the first field so Enter/Tab never dead-ends.
        if (fields[0]) focusAndSelect(fields[0]);
        return;
      }
      const step = e.shiftKey ? -1 : 1;
      const next = fields[idx + step];
      if (next) focusAndSelect(next);
      // At the last field with nothing after it, Enter simply does nothing
      // further — the caller's own "last field" handler (e.g. a grid's
      // row-complete) or an explicit Ctrl+Enter save takes over.
    };

    container.addEventListener("keydown", handler, true); // capture phase
    return () => container.removeEventListener("keydown", handler, true);
  }, [containerRef, enabled]);

  return { focusFirst };
}

export { collectFields, focusAndSelect };
