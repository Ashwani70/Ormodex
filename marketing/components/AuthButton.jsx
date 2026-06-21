"use client";
import { ERP_LOGIN_URL, ERP_SIGNUP_URL } from "@/lib/site";

// Direct deep-link into the live ERP app's auth. The marketing site itself is
// stateless — login/logout happen in the product app. We send users straight to
// the ERP /login route (configurable via NEXT_PUBLIC_ERP_APP_URL).
export default function AuthButton({ variant = "nav" }) {
  if (variant === "primary") {
    return (
      <a
        href={ERP_SIGNUP_URL}
        className="rounded-xl bg-gradient-to-r from-primary to-violet px-5 py-2.5 text-sm font-semibold text-white shadow-glow transition hover:scale-[1.03]"
      >
        Open the App
      </a>
    );
  }
  return (
    <a
      href={ERP_LOGIN_URL}
      className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:border-white/40 hover:text-white"
    >
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
        <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3" />
      </svg>
      Login
    </a>
  );
}
