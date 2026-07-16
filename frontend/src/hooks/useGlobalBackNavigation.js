import { useEffect } from "react";
import { useGoBack } from "@/hooks/useNavigationHistory";
import { useIsAnyModalOpen } from "@/context/ModalStackContext";

/**
 * Global "Back Navigation" feature.
 *
 * Mounted ONCE (in Layout.jsx, which wraps every authenticated route) so
 * every module — Inventory, Manufacturing, Purchase, Sales, Accounts, CRM,
 * HR, Reports, Settings, etc. — gets it automatically with no per-page code.
 *
 * Triggers (any one of these navigates back):
 *   - Esc
 *   - Alt + ArrowLeft        (Windows/Linux "back" convention)
 *   - Cmd + [                (macOS "back" convention)
 *   - Mouse "Back" button    (browser/OS side button, fires as a native
 *                             `mouseup` with button === 3, no keyboard involved)
 *
 * Uses react-router's `navigate(-1)` (via useGoBack) rather than
 * `window.history.back()` directly, so navigation stays inside React
 * Router's data model. Falls back to the Dashboard when there's no in-app
 * screen behind the current one (see useNavigationHistory.js).
 *
 * Deliberately backs off when:
 *   - The user is typing (input/textarea/select/contentEditable focused) —
 *     checked so Esc/Alt+Left don't yank focus away mid-edit. Note: Esc
 *     itself is a control key, not printable, but many inputs (native
 *     `<select>`, search boxes, date pickers) treat Esc as "clear/close
 *     THIS widget" — we don't want to race that, so back-nav stays off
 *     while any form field has focus, same as its own escape/blur handles.
 *   - Any modal/overlay is currently open (tracked via ModalStackContext,
 *     `isAnyModalOpen`) — the overlay's own Escape handler closes it first;
 *     back-navigation only resumes once every overlay is closed.
 */

const BACK_MOUSE_BUTTON = 3; // Standard "browser back" side button.

function isTypingTarget(el) {
  if (!el) return false;
  const tag = el.tagName;
  const type = el.type;
  if (tag === "INPUT" && type !== "checkbox" && type !== "radio" && type !== "button" && type !== "submit") return true;
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (el.isContentEditable) return true;
  return false;
}

export function useGlobalBackNavigation({ fallbackPath = "/" } = {}) {
  const goBack = useGoBack(fallbackPath);
  const isAnyModalOpen = useIsAnyModalOpen();

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (isAnyModalOpen) return; // let the modal's own Escape handler close it first
      if (isTypingTarget(document.activeElement)) return;

      const isEsc = e.key === "Escape";
      const isAltLeft = e.altKey && e.key === "ArrowLeft";
      const isCmdBracket = e.metaKey && e.key === "[";

      if (!isEsc && !isAltLeft && !isCmdBracket) return;

      e.preventDefault();
      goBack();
    };

    // Browser/OS mouse "Back" side button. Guard against browsers that also
    // fire a native `popstate`-driven back for this button — we only handle
    // it ourselves when the event actually reaches the page (some browsers
    // intercept it before JS ever sees it, in which case this is a no-op
    // and the browser's own back behavior already applies).
    const handleMouseUp = (e) => {
      if (e.button !== BACK_MOUSE_BUTTON) return;
      if (isAnyModalOpen) return;
      e.preventDefault();
      goBack();
    };

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("mouseup", handleMouseUp);

    // Cleanup: always remove both listeners to avoid leaking handlers
    // across route/component remounts.
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [goBack, isAnyModalOpen]);
}
