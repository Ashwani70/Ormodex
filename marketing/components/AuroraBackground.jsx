// Cinematic animated backdrop: a slowly rotating conic "aurora" blob plus soft
// colour glows, masked into the section. Pure CSS — no canvas, no JS cost.
// Sits behind content with `absolute inset-0`; give the parent `relative`.
export default function AuroraBackground({ className = "" }) {
  return (
    <div className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`} aria-hidden>
      {/* rotating aurora core */}
      <div className="absolute left-1/2 top-0 h-[60rem] w-[60rem] -translate-x-1/2 -translate-y-1/3 opacity-25 blur-3xl">
        <div className="h-full w-full rounded-full bg-aurora animate-aurora-spin" />
      </div>
      {/* coloured side glows */}
      <div className="absolute -left-40 top-40 h-96 w-96 rounded-full bg-primary/30 blur-[120px] animate-pulse-glow" />
      <div className="absolute -right-40 top-24 h-96 w-96 rounded-full bg-accent/25 blur-[120px] animate-pulse-glow" style={{ animationDelay: "1.5s" }} />
      <div className="absolute bottom-0 left-1/3 h-80 w-80 rounded-full bg-violet/25 blur-[120px] animate-pulse-glow" style={{ animationDelay: "3s" }} />
      {/* subtle grid */}
      <div className="grid-texture absolute inset-0" />
    </div>
  );
}
