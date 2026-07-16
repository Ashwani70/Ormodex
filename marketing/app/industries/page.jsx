import Link from "next/link";
import PageHero from "@/components/PageHero";
import Reveal from "@/components/Reveal";

export const metadata = {
  title: "Industry Solutions — Manufacturing, Forging, Garments, Trading, Export",
  description: "Ormodex ERP tailored for manufacturing, forging & casting, garment manufacturers, traders and export businesses.",
};

const INDUSTRIES = [
  {
    id: "manufacturing",
    title: "Manufacturing",
    description: "BOM-driven production, work orders, costing and shop-floor visibility with GST-ready billing.",
    image: "/images/manufacturing.png",
    features: [
      "Multi-level Bill of Materials (BOM) with versioning",
      "Work order scheduling & real-time shop floor tracking",
      "WIP valuation, raw material allocation, and variance analysis",
      "Job cards, labor logs, and machine utilization logs"
    ]
  },
  {
    id: "forging",
    title: "Forging & Casting",
    description: "Heat-wise tracking, scrap accounting, die/tooling management and job-work outsourcing.",
    image: "/images/forging.png",
    features: [
      "Heat-number tracking from raw material to dispatch",
      "Scrap generation, burning loss, and recovery logs",
      "Subcontractor / Job-work dispatch and receipt chalans",
      "Die and mold life-cycle monitoring and maintenance"
    ]
  },
  {
    id: "garments",
    title: "Garments",
    description: "Style / size / colour matrices, lot-based inventory and fast multi-rate billing.",
    image: "/images/garments.png",
    features: [
      "2D style matrices (Size x Color x Pattern) for quick entries",
      "Lot, batch, and bundle-wise production tracking",
      "Trim, button, accessory planning & procurement",
      "Production-stage scanning (cutting, stitching, packing)"
    ]
  },
  {
    id: "trading",
    title: "Trading",
    description: "Rapid invoicing, multi-rate pricing, stock turns and receivables tracking.",
    image: "/images/trading.png",
    features: [
      "Multi-counter Point of Sale (POS) and rapid barcode checkout",
      "Batch-wise inventory with expiry date tracking",
      "Flexible pricing lists, customer schemas, and volume discounts",
      "Aging reports and automated payment reminders"
    ]
  },
  {
    id: "export",
    title: "Export Businesses",
    description: "Multi-currency invoicing, export documentation and e-Way Bill / e-Invoice support.",
    image: "/images/export.png",
    features: [
      "Multi-currency sales orders & foreign exchange rate gain/loss logs",
      "Export invoice, packing lists, and shipping instructions",
      "Duty drawback and refund tracking schemas",
      "Integrated e-Way Bill & e-Invoicing (IRN) inline generation"
    ]
  }
];

export default function IndustriesPage() {
  return (
    <>
      <PageHero eyebrow="Industries" title="Configured for how you actually work"
        subtitle="One platform, tuned to the workflows of your sector." />
      <section className="mx-auto max-w-7xl px-5 py-16">
        <div className="grid gap-8 md:grid-cols-2">
          {INDUSTRIES.map(({ id, title, description, image, features }, i) => (
            <Reveal key={id} delay={(i % 2) * 70} className={i === 4 ? "md:col-span-2 max-w-4xl mx-auto w-full" : ""}>
              <div
                id={id}
                className="group h-full overflow-hidden rounded-3xl border border-slate-100 bg-white shadow-soft transition-all duration-300 hover:-translate-y-1.5 hover:shadow-card scroll-mt-24 flex flex-col"
              >
                <div className="relative h-64 w-full overflow-hidden bg-slate-100">
                  <div className="absolute top-4 left-4 z-10 rounded-full bg-white/95 px-3 py-1 text-xs font-semibold text-primary shadow-sm backdrop-blur-sm">
                    {title}
                  </div>
                  <img
                    src={image}
                    alt={title}
                    className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                  />
                </div>
                <div className="p-8 flex flex-col flex-1">
                  <h3 className="text-2xl font-bold text-ink">{title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-body">{description}</p>
                  <div className="my-6 border-t border-slate-100" />
                  <p className="text-xs font-bold uppercase tracking-wider text-slate-400">
                    Capabilities Included
                  </p>
                  <ul className="mt-4 flex-1 space-y-3">
                    {features.map((feat) => (
                      <li key={feat} className="flex items-start gap-3 text-sm text-body">
                        <svg className="mt-0.5 h-5 w-5 shrink-0 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                        <span>{feat}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
        <div className="mt-12 text-center">
          <Link href="/contact#demo" className="rounded-md bg-primary px-6 py-3 text-sm font-semibold text-white shadow-soft transition hover:bg-primary-dark">Talk to an expert</Link>
        </div>
      </section>
    </>
  );
}
