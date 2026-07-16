import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

// Tracks how many overlay surfaces (modals, the shortcuts-help panel, the
// global search dropdown, the profile dropdown, etc.) are currently open,
// across the whole app. Anything that wants Escape to close IT first —
// instead of the global "Escape = go back" handler also firing on the same
// keypress — registers itself here while open.
//
// A count (not a boolean) because multiple overlays can be open at once
// (e.g. a confirm dialog on top of a form modal); back-navigation should
// stay suppressed until the LAST one closes.
const ModalStackContext = createContext(null);

export function ModalStackProvider({ children }) {
  const [count, setCount] = useState(0);
  const countRef = useRef(0);

  const register = useCallback(() => {
    countRef.current += 1;
    setCount(countRef.current);
    return () => {
      countRef.current = Math.max(0, countRef.current - 1);
      setCount(countRef.current);
    };
  }, []);

  return (
    <ModalStackContext.Provider value={{ isAnyOpen: count > 0, register }}>
      {children}
    </ModalStackContext.Provider>
  );
}

/** Read-only: is any registered overlay currently open? */
export function useIsAnyModalOpen() {
  const ctx = useContext(ModalStackContext);
  return ctx ? ctx.isAnyOpen : false;
}

/** For overlay components: call while open to suppress global back-nav. */
export function useModalStackRegistration(isOpen) {
  const ctx = useContext(ModalStackContext);

  useEffect(() => {
    if (!ctx || !isOpen) return undefined;
    return ctx.register();
  }, [ctx, isOpen]);
}
