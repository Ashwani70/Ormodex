"use client";
import { useEffect, useState } from "react";
import OSIcon from "./OSIcon";
import { DOWNLOADS, APP_VERSION } from "@/lib/site";

// Detects the visitor's OS so we can surface the matching installer as the primary
// CTA. Returns "windows" | "mac" | "linux" | null.
function detectOS() {
  if (typeof navigator === "undefined") return null;
  const p = (navigator.userAgentData?.platform || navigator.platform || navigator.userAgent || "").toLowerCase();
  if (p.includes("win")) return "windows";
  if (p.includes("mac") || p.includes("iphone") || p.includes("ipad")) return "mac";
  if (p.includes("linux") || p.includes("android")) return "linux";
  return null;
}

export default function OSDownload({ compact = false }) {
  const [os, setOS] = useState(null);
  useEffect(() => setOS(detectOS()), []);

  const order = ["windows", "mac", "linux"];
  const primaryKey = os && DOWNLOADS[os] ? os : "windows";
  const primary = DOWNLOADS[primaryKey];
  const others = order.filter((k) => k !== primaryKey);

  if (compact) {
    return (
      <a
        href={primary.url}
        className="shimmer relative inline-flex items-center gap-2.5 overflow-hidden rounded-xl bg-gradient-to-r from-primary to-violet px-6 py-3 text-sm font-semibold text-white shadow-glow transition hover:scale-[1.03]"
      >
        <OSIcon name={primary.icon} className="h-5 w-5" />
        Download for {primary.label}
      </a>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      {/* primary, OS-detected card */}
      <a
        href={primary.url}
        className="ring-gradient group relative flex items-center justify-between gap-4 overflow-hidden rounded-2xl border border-primary/30 bg-gradient-to-br from-primary/15 to-violet/10 p-6 transition hover:border-primary/60"
      >
        <div className="flex items-center gap-4">
          <span className="flex h-14 w-14 items-center justify-center rounded-xl bg-white/10 text-white">
            <OSIcon name={primary.icon} className="h-8 w-8" />
          </span>
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-accent">
              {os ? "Detected — recommended for you" : "Recommended"}
            </div>
            <div className="text-lg font-bold text-white">Download for {primary.label}</div>
            <div className="text-sm text-slate-400">{primary.sub} · v{APP_VERSION}</div>
          </div>
        </div>
        <span className="shimmer relative hidden overflow-hidden rounded-xl bg-white px-5 py-2.5 text-sm font-bold text-ink transition group-hover:scale-105 sm:inline-block">
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
              className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-4 text-left transition hover:border-white/25 hover:bg-white/10"
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/10 text-white">
                <OSIcon name={d.icon} className="h-6 w-6" />
              </span>
              <div>
                <div className="font-semibold text-white">{d.label}</div>
                <div className="text-xs text-slate-400">{d.sub}</div>
              </div>
            </a>
          );
        })}
      </div>

      <p className="mt-4 text-center text-xs text-slate-500">
        Also available on the web — no install needed. Cross-platform · auto-updating · signed installers.
      </p>
    </div>
  );
}
