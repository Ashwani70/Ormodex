import Link from "next/link";
import PageHero from "@/components/PageHero";
import Reveal from "@/components/Reveal";

export const metadata = {
  title: "About Us",
  description: "Gravity One ERP helps Indian manufacturers, traders and exporters run their entire operation on one GST-compliant, AI-powered platform.",
};

const STATS = [["15+", "Modules"], ["GST", "Compliant"], ["AI", "Powered"], ["24/7", "Support"]];

export default function AboutPage() {
  return (
    <>
      <PageHero eyebrow="About Us" title="Built for Indian enterprise"
        subtitle="We're on a mission to replace spreadsheets and disconnected tools with one intelligent platform." />
      <section className="mx-auto max-w-3xl px-5 py-16">
        <Reveal>
          <p className="text-lg leading-relaxed text-body">
            Gravity One ERP was built for businesses that make and move real things —
            manufacturers, forging and casting units, garment makers, traders and exporters.
            We saw teams losing hours to duplicate data entry, stock mismatches and last-minute
            GST scrambles, and we set out to fix it with a single, connected system.
          </p>
          <p className="mt-4 text-lg leading-relaxed text-body">
            Today, sales, inventory, accounting, GST, e-Invoicing, e-Way Bills, production and HR
            all live in one place — with real-time reporting and role-based access, so everyone
            sees exactly what they should.
          </p>
        </Reveal>
        <div className="mt-12 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {STATS.map(([big, small]) => (
            <div key={small} className="rounded-2xl border border-slate-100 bg-white p-5 text-center shadow-soft">
              <div className="text-2xl font-bold text-primary">{big}</div>
              <div className="mt-1 text-xs uppercase tracking-wide text-slate-500">{small}</div>
            </div>
          ))}
        </div>
        <div className="mt-12 text-center">
          <Link href="/contact#demo" className="rounded-md bg-primary px-6 py-3 text-sm font-semibold text-white shadow-soft transition hover:bg-primary-dark">Book a Demo</Link>
        </div>
      </section>
    </>
  );
}
