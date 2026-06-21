import Link from "next/link";
import PageHero from "@/components/PageHero";
import Reveal from "@/components/Reveal";

export const metadata = {
  title: "Industry Solutions — Manufacturing, Forging, Garments, Trading, Export",
  description: "Gravity One ERP tailored for manufacturing, forging & casting, garment manufacturers, traders and export businesses.",
};

const INDUSTRIES = [
  ["manufacturing", "Manufacturing", "BOM-driven production, work orders, costing and shop-floor visibility with GST-ready billing."],
  ["forging", "Forging & Casting", "Heat-wise tracking, scrap accounting, die/tooling management and job-work outsourcing."],
  ["garments", "Garments", "Style / size / colour matrices, lot-based inventory and fast multi-rate billing."],
  ["trading", "Trading", "Rapid invoicing, multi-rate pricing, stock turns and receivables tracking."],
  ["export", "Export Businesses", "Multi-currency invoicing, export documentation and e-Way Bill / e-Invoice support."],
];

export default function IndustriesPage() {
  return (
    <>
      <PageHero eyebrow="Industries" title="Configured for how you actually work"
        subtitle="One platform, tuned to the workflows of your sector." />
      <section className="mx-auto max-w-7xl px-5 py-16">
        <div className="grid gap-6 md:grid-cols-2">
          {INDUSTRIES.map(([id, t, d], i) => (
            <Reveal key={id} delay={(i % 2) * 70}>
              <div id={id} className="ring-gradient h-full overflow-hidden rounded-2xl border border-white/10 bg-surface transition hover:bg-white/[0.04] scroll-mt-24">
                <div className="h-1.5 bg-gradient-to-r from-primary via-accent to-violet" />
                <div className="p-6">
                  <h3 className="text-lg font-bold text-white">{t}</h3>
                  <p className="mt-2 text-sm text-slate-400">{d}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
        <div className="mt-12 text-center">
          <Link href="/contact#demo" className="rounded-xl bg-gradient-to-r from-primary to-violet px-6 py-3 text-sm font-semibold text-white shadow-glow transition hover:scale-[1.03]">Talk to an expert</Link>
        </div>
      </section>
    </>
  );
}
