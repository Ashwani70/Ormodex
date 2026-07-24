"use client";
import { useEffect, useState } from "react";
import OSIcon from "./OSIcon";
import { DOWNLOADS, MOBILE_DOWNLOADS, APP_VERSION } from "@/lib/site";

// Detects the visitor's platform so we can surface the matching install option
// as the primary CTA. Returns "windows" | "mac" | "linux" | "android" | "ios" | null.
// Mobile is checked before desktop OS strings because "mac" also matches
// iPhone/iPad user agents, and Android UAs contain "linux".
function detectOS() {
  if (typeof navigator === "undefined") return null;
  const p = (navigator.userAgentData?.platform || navigator.platform || navigator.userAgent || "").toLowerCase();
  if (p.includes("android")) return "android";
  if (p.includes("iphone") || p.includes("ipad") || p.includes("ipod")) return "ios";
  if (p.includes("win")) return "windows";
  if (p.includes("mac")) return "mac";
  if (p.includes("linux")) return "linux";
  return null;
}

const MOBILE_KEYS = new Set(["android", "ios"]);

export default function OSDownload({ compact = false }) {
  const [os, setOS] = useState(null);
  useEffect(() => setOS(detectOS()), []);

  const order = ["windows", "mac", "linux"];
  // A phone visitor gets the PWA recommended as primary — a desktop .exe/.dmg/
  // .AppImage installer can't run on their device at all.
  const onMobile = MOBILE_KEYS.has(os);
  const primaryKey = !onMobile && os && DOWNLOADS[os] ? os : "windows";
  const primary = onMobile ? MOBILE_DOWNLOADS.pwa : DOWNLOADS[primaryKey];
  const others = onMobile ? order : order.filter((k) => k !== primaryKey);

  if (compact) {
    return (
      <a
        href={primary.url}
        className="inline-flex items-center gap-2.5 rounded-md bg-primary px-6 py-3 text-sm font-semibold text-white shadow-soft transition hover:bg-primary-dark"
      >
        <OSIcon name={primary.icon} className="h-5 w-5" />
        {onMobile ? "Install the App" : `Download for ${primary.label}`}
      </a>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      {/* primary, OS-detected card */}
      <a
        href={primary.url}
        target={onMobile ? "_blank" : undefined}
        rel={onMobile ? "noopener noreferrer" : undefined}
        className="group relative flex items-center justify-between gap-4 rounded-2xl border border-primary/30 bg-mint p-6 transition hover:shadow-soft"
      >
        <div className="flex items-center gap-4">
          <span className="flex h-14 w-14 items-center justify-center rounded-xl bg-primary text-white">
            <OSIcon name={primary.icon} className="h-8 w-8" />
          </span>
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-primary-dark">
              {os ? "Detected — recommended for you" : "Recommended"}
            </div>
            <div className="text-lg font-bold text-ink">
              {onMobile ? primary.label : `Download for ${primary.label}`}
            </div>
            <div className="text-sm text-body">
              {primary.sub}
              {!onMobile && <> · v{APP_VERSION}</>}
            </div>
          </div>
        </div>
        <span className="hidden rounded-md bg-primary px-5 py-2.5 text-sm font-bold text-white transition group-hover:bg-primary-dark sm:inline-block">
          Get the app ↓
        </span>
      </a>

      {/* other platforms */}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {others.map((k) => {
          const d = DOWNLOADS[k];
          return (
            <a
              key={k}
              href={d.url}
              className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 text-left transition hover:border-primary/40 hover:shadow-soft"
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-mint text-primary">
                <OSIcon name={d.icon} className="h-6 w-6" />
              </span>
              <div>
                <div className="font-semibold text-ink">{d.label}</div>
                <div className="text-xs text-body">{d.sub}</div>
              </div>
            </a>
          );
        })}
      </div>

      <p className="mt-4 text-center text-xs text-slate-400">
        Also available on the web — no install needed. Cross-platform · auto-updating · signed installers.
      </p>

      {/* mobile / PWA row */}
      <div className="mt-8">
        <div className="mb-3 text-center text-xs font-semibold uppercase tracking-wider text-slate-400">
          On your phone
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {Object.entries(MOBILE_DOWNLOADS).map(([k, d]) =>
            d.available ? (
              <a
                key={k}
                href={d.url}
                target={k === "pwa" ? "_blank" : undefined}
                rel={k === "pwa" ? "noopener noreferrer" : undefined}
                className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 text-left transition hover:border-primary/40 hover:shadow-soft"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-mint text-primary">
                  <OSIcon name={d.icon} className="h-6 w-6" />
                </span>
                <div>
                  <div className="font-semibold text-ink">{d.label}</div>
                  <div className="text-xs text-body">{d.sub}</div>
                </div>
              </a>
            ) : (
              <div
                key={k}
                aria-disabled="true"
                title="Coming soon"
                className="flex items-center gap-3 rounded-xl border border-dashed border-slate-200 bg-slate-50 p-4 text-left opacity-60"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-200 text-slate-500">
                  <OSIcon name={d.icon} className="h-6 w-6" />
                </span>
                <div>
                  <div className="font-semibold text-ink">{d.label}</div>
                  <div className="text-xs text-body">{d.sub}</div>
                </div>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
