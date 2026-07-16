import { useEffect, useState } from "react";
import Logo, { BRAND } from "@/components/Logo";

/**
 * Full-screen branded splash / loading screen.
 *
 * Used as the app's initial boot screen and as a Suspense fallback. Shows the
 * ORMODEX logo with a smooth fade-in, the tagline, and an indeterminate brand
 * progress bar. Pure presentation — no data, no layout shift (fixed overlay).
 *
 * Props:
 *  - message: optional status line under the progress bar
 *  - variant: "splash" (large centered, startup) | "loading" (compact fallback)
 */
export default function SplashScreen({ message = "Loading your workspace…", variant = "splash" }) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const t = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(t);
  }, []);

  const big = variant === "splash";

  return (
    <div
      className="fixed inset-0 z-[9999] flex flex-col items-center justify-center"
      style={{
        background:
          "radial-gradient(1200px 600px at 50% 30%, #ffffff 0%, #f4f7fb 60%, #eef2f8 100%)",
      }}
      role="status"
      aria-live="polite"
      aria-label="Loading"
    >
      <div
        className="flex flex-col items-center text-center transition-all duration-700 ease-out"
        style={{
          opacity: shown ? 1 : 0,
          transform: shown ? "translateY(0) scale(1)" : "translateY(8px) scale(0.98)",
        }}
      >
        <Logo variant="full" size={big ? "xl" : "lg"} alt={BRAND.name} />
        <div
          className="mt-3 font-mono uppercase tracking-[0.35em] text-[10px]"
          style={{ color: BRAND.colors.navy }}
        >
          {BRAND.tagline}
        </div>

        {/* Indeterminate brand progress bar */}
        <div
          className="mt-8 h-1 w-48 overflow-hidden rounded-full"
          style={{ background: "rgba(15,30,61,0.10)" }}
        >
          <div
            className="h-full rounded-full ormodex-splash-bar"
            style={{
              width: "40%",
              background: `linear-gradient(90deg, ${BRAND.colors.green}, ${BRAND.colors.blue})`,
            }}
          />
        </div>
        {message && (
          <div className="mt-3 text-xs text-muted-foreground">{message}</div>
        )}
      </div>

      {/* Scoped keyframes for the sliding progress bar. */}
      <style>{`
        @keyframes ormodex-splash-slide {
          0%   { transform: translateX(-120%); }
          100% { transform: translateX(320%); }
        }
        .ormodex-splash-bar {
          animation: ormodex-splash-slide 1.1s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
        @media (prefers-reduced-motion: reduce) {
          .ormodex-splash-bar { animation-duration: 2.2s; }
        }
      `}</style>
    </div>
  );
}
