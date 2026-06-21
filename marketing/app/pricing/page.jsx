import Link from "next/link";
import PageHero from "@/components/PageHero";
import Reveal from "@/components/Reveal";

export const metadata = {
  title: "Pricing",
  description: "Gravity One ERP pricing — Starter, Professional and Enterprise plans for small businesses, growing companies and large organizations.",
};

const PLANS = [
  ["Starter", "Small businesses", "Contact Sales", ["Core sales & billing", "GST invoicing", "Up to 5 users", "Email support"], false],
  ["Professional", "Growing companies", "Contact Sales", ["All Starter features", "Inventory & production", "e-Invoicing & e-Way Bill", "Priority support"], true],
  ["Enterprise", "Large organizations", "Custom Pricing", ["All Professional features", "Unlimited users", "Dedicated success manager", "Custom integrations"], false],
];

export default function PricingPage() {
  return (
    <>
      <PageHero eyebrow="Pricing" title="Plans that scale with you"
        subtitle="Transparent tiers, no surprises. Talk to us for a quote tailored to your team size and modules." />
      <section className="mx-auto max-w-7xl px-5 py-16">
        <div className="grid gap-6 lg:grid-cols-3">
          {PLANS.map(([name, who, price, feats, featured], i) => (
            <Reveal key={name} delay={i * 80}>
              <div className={`relative flex h-full flex-col rounded-3xl border p-7 transition ${featured ? "border-primary bg-white shadow-card lg:-translate-y-3" : "border-slate-100 bg-white shadow-soft"}`}>
                {featured && <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-1 text-xs font-semibold text-white shadow-glow">Most popular</span>}
                <h3 className="text-xl font-bold text-ink">{name}</h3>
                <p className="mt-1 text-sm text-body">{who}</p>
                <div className="mt-5 text-2xl font-bold text-primary">{price}</div>
                <ul className="mt-5 flex-1 space-y-2.5 text-sm text-body">
                  {feats.map((f) => <li key={f} className="flex items-start gap-2"><span className="mt-0.5 text-primary">✓</span>{f}</li>)}
                </ul>
                <Link href="/contact" className={`mt-6 rounded-md px-5 py-2.5 text-center text-sm font-semibold transition ${featured ? "bg-primary text-white shadow-soft hover:bg-primary-dark" : "border border-slate-200 text-ink hover:border-primary/40 hover:text-primary"}`}>
                  Request Pricing
                </Link>
              </div>
            </Reveal>
          ))}
        </div>
      </section>
    </>
  );
}
