import { useEffect, useRef } from "react";

const ACTIVITY_EVENTS = ["mousemove", "mousedown", "keydown", "touchstart", "scroll"];

/**
 * Calls onIdle after `timeoutMs` of no mouse/keyboard/touch/scroll activity.
 * Client-side inactivity auto-logout — a lighter-weight alternative to a
 * server-enforced per-request last-activity check, which would add a DB write
 * to every authenticated request (see backend/core/cache.py's docstring on
 * why that round-trip cost is avoided elsewhere in this app). The access
 * token's own expiry is the hard backstop; this just logs an inactive tab out
 * sooner for shared/kiosk-style workstations.
 */
export default function useIdleTimer(onIdle, timeoutMs = 20 * 60 * 1000, enabled = true) {
  const timerRef = useRef(null);
  const onIdleRef = useRef(onIdle);
  onIdleRef.current = onIdle;

  useEffect(() => {
    if (!enabled) return undefined;

    const reset = () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => onIdleRef.current?.(), timeoutMs);
    };

    reset();
    ACTIVITY_EVENTS.forEach((evt) => window.addEventListener(evt, reset, { passive: true }));

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      ACTIVITY_EVENTS.forEach((evt) => window.removeEventListener(evt, reset));
    };
  }, [timeoutMs, enabled]);
}
