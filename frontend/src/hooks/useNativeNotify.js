// Native OS notification, falling back to the Web Notification API on the
// plain web/PWA build (where window.ormodex isn't present). Complements
// sonner's in-app toasts for events worth surfacing even when the app window
// isn't focused — e.g. a long report finishing, or a background sync result.
export function notify(title, body, opts = {}) {
  if (typeof window === "undefined") return;

  if (window.ormodex?.notify) {
    window.ormodex.notify(title, body, opts);
    return;
  }

  if (!("Notification" in window)) return;
  if (Notification.permission === "granted") {
    new Notification(title, { body, silent: !!opts.silent });
  } else if (Notification.permission !== "denied") {
    Notification.requestPermission().then((perm) => {
      if (perm === "granted") new Notification(title, { body, silent: !!opts.silent });
    });
  }
}

export default function useNativeNotify() {
  return notify;
}
