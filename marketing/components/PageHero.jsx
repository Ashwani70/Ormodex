import AuroraBackground from "./AuroraBackground";

// Compact, cinematic page header for inner SEO pages.
export default function PageHero({ eyebrow, title, subtitle }) {
  return (
    <section className="relative overflow-hidden border-b border-white/5 bg-ink text-white">
      <AuroraBackground className="opacity-70" />
      <div className="relative mx-auto max-w-7xl px-5 py-20 text-center">
        {eyebrow && (
          <span className="inline-block rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-primary-light">
            {eyebrow}
          </span>
        )}
        <h1 className="mt-4 text-4xl font-extrabold tracking-tight sm:text-5xl">
          {title}
        </h1>
        {subtitle && <p className="mx-auto mt-4 max-w-2xl text-lg text-slate-300">{subtitle}</p>}
      </div>
    </section>
  );
}
