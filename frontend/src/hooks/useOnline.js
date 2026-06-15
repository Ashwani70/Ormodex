import { useEffect, useState } from "react";

// Tracks browser connectivity. The repo has no generic offline-write layer
// (only POS has a page-local sync queue), so non-POS screens are online-only:
// they show status and disable writes when offline rather than fake-queueing.
export default function useOnline() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);
  return online;
}
