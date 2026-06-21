"use client";
import { useRef } from "react";

/**
 * Wraps children in a 3D tilt that follows the pointer (mouse) for a premium,
 * "floating glass" feel. Falls back to a static card on touch / reduced-motion.
 *
 * `max` = max tilt in degrees. `glare` adds a moving highlight sheen.
 */
export default function ParallaxTilt({ children, max = 10, glare = true, className = "" }) {
  const wrap = useRef(null);
  const inner = useRef(null);
  const glareRef = useRef(null);

  const reduced =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  function onMove(e) {
    if (reduced || !inner.current) return;
    const el = wrap.current;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    const rx = (0.5 - py) * max * 2;
    const ry = (px - 0.5) * max * 2;
    inner.current.style.transform = `perspective(1000px) rotateX(${rx}deg) rotateY(${ry}deg) scale(1.02)`;
    if (glareRef.current) {
      glareRef.current.style.opacity = "1";
      glareRef.current.style.background = `radial-gradient(circle at ${px * 100}% ${py * 100}%, rgba(255,255,255,0.25), transparent 50%)`;
    }
  }

  function onLeave() {
    if (!inner.current) return;
    inner.current.style.transform = "perspective(1000px) rotateX(0) rotateY(0) scale(1)";
    if (glareRef.current) glareRef.current.style.opacity = "0";
  }

  return (
    <div
      ref={wrap}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      className={className}
      style={{ perspective: "1000px" }}
    >
      <div ref={inner} className="tilt-3d relative">
        {children}
        {glare && (
          <div
            ref={glareRef}
            className="pointer-events-none absolute inset-0 rounded-[inherit] opacity-0 transition-opacity duration-200"
            aria-hidden
          />
        )}
      </div>
    </div>
  );
}
