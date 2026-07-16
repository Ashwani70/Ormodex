import { useNavigate, useLocation } from "react-router-dom";

/**
 * Global "go back" for the app's Back Navigation feature.
 *
 * Uses react-router's own history — `navigate(-1)` — rather than a browser
 * hack like `window.history.back()`, and falls back to a given route
 * (defaults to the Dashboard) when there is no previous screen in THIS
 * session, so the user is never accidentally kicked out of the SPA to
 * whatever the browser tab had loaded before the app started.
 *
 * "Is there a previous screen" is answered by react-router itself:
 * `location.key === "default"` is the sentinel react-router assigns to the
 * very first history entry of a session (fresh load, deep link, or a hard
 * refresh) — there is nothing behind it for `navigate(-1)` to pop to. Any
 * subsequent navigation gets a real generated key, meaning at least one
 * entry exists behind it. This is simpler and race-free compared to
 * hand-tracking a navigation counter (which would need to perfectly
 * distinguish push vs. pop on every route change).
 */
export function useGoBack(fallbackPath = "/") {
  const navigate = useNavigate();
  const location = useLocation();

  return () => {
    if (location.key && location.key !== "default") {
      navigate(-1);
    } else {
      navigate(fallbackPath, { replace: true });
    }
  };
}
