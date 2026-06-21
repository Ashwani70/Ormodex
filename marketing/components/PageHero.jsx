import AuroraBackground from "./AuroraBackground";

// Light, airy page header for inner SEO pages.
export default function PageHero({ eyebrow, title, subtitle }) {
  return (
    <section className="relative overflow-hidden bg-soft">
      <AuroraBackground />
      <div className="relative mx-auto max-w-7xl px-5 py-20 text-center">
        {eyebrow && (
          <span className="inline-block rounded-full bg-mint px-3 py-1 text-xs font-semibold uppercase tracking-widest text-primary-dark">
            {eyebrow}
          </span>
        )}
        <h1 className="mt-4 text-4xl font-bold tracking-tight text-ink sm:text-5xl">
          {title}
        </h1>
        {subtitle && <p className="mx-auto mt-4 max-w-2xl text-lg text-body">{subtitle}</p>}
      </div>
    </section>
  );
}
