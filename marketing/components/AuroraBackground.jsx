// Light, airy hero backdrop: a soft green glow plus a subtle dotted texture.
// Sits behind content with `absolute inset-0`; give the parent `relative`.
export default function AuroraBackground({ className = "" }) {
  return (
    <div className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`} aria-hidden>
      <div className="absolute -right-32 -top-24 h-96 w-96 rounded-full bg-mint blur-3xl opacity-70" />
      <div className="absolute -left-24 top-40 h-80 w-80 rounded-full bg-primary/10 blur-3xl" />
      <div className="dot-texture absolute inset-0" />
    </div>
  );
}
