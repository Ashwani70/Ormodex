"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import AuthButton from "./AuthButton";

const LINKS = [
  { href: "/features", label: "Features" },
  { href: "/industries", label: "Industries" },
  { href: "/pricing", label: "Pricing" },
  { href: "/docs", label: "Docs" },
  { href: "/contact", label: "Contact" },
];

// Primary nav CTA: download the desktop app. Mirrors AuthButton's primary styling.
function DownloadButton() {
  return (
    <Link
      href="/download"
      className="inline-flex items-center gap-1.5 rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:bg-primary-dark"
    >
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M12 3v12m0 0l4-4m-4 4l-4-4M5 21h14" />
      </svg>
      Download
    </Link>
  );
}

export default function Navbar() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-50 bg-white/90 backdrop-blur transition-shadow ${
        scrolled ? "shadow-soft" : ""
      }`}
    >
      <nav className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
        <Link href="/" className="flex items-center gap-2.5">
          <img src="/logo.png" alt="Ormodex" className="h-9 w-9 object-contain" />
          <span className="text-xl font-bold tracking-tight text-ink">
            Ormodex
          </span>
        </Link>

        <div className="hidden items-center gap-8 lg:flex">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="text-sm font-medium text-body transition-colors hover:text-primary"
            >
              {l.label}
            </Link>
          ))}
        </div>

        <div className="hidden items-center gap-3 lg:flex">
          <AuthButton variant="nav" />
          <DownloadButton />
        </div>

        <button
          className="text-ink lg:hidden"
          aria-label="Toggle menu"
          onClick={() => setOpen((v) => !v)}
        >
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            {open ? <path d="M6 6l12 12M6 18L18 6" /> : <><path d="M3 6h18" /><path d="M3 12h18" /><path d="M3 18h18" /></>}
          </svg>
        </button>
      </nav>

      {open && (
        <div className="border-t border-slate-100 bg-white px-5 py-4 lg:hidden">
          <div className="flex flex-col gap-3">
            {LINKS.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className="text-sm font-medium text-body"
                onClick={() => setOpen(false)}
              >
                {l.label}
              </Link>
            ))}
            <div className="mt-2 flex flex-col gap-2" onClick={() => setOpen(false)}>
              <AuthButton variant="nav" />
              <DownloadButton />
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
