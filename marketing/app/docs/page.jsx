import Link from "next/link";
import PageHero from "@/components/PageHero";
import Reveal from "@/components/Reveal";
import { ERP_LOGIN_URL } from "@/lib/site";

export const metadata = {
  title: "Documentation & Help Center",
  description:
    "Guides, setup walkthroughs and module documentation for Gravity One ERP — getting started, billing & GST, inventory, production, HR, integrations and the API.",
};

const QUICKSTART = [
  ["Create your account", "Sign up, name your organization and pick single-user or multi-user.", ERP_LOGIN_URL],
  ["Set up masters", "Add customers, vendors, items, tax rates and opening stock — or import from Excel/Tally.", "/docs#masters"],
  ["Raise your first invoice", "Create a GST invoice, generate the IRN/QR and e-Way Bill in one screen.", "/docs#billing"],
  ["Invite your team", "Add users, assign roles and module permissions (multi-user plans).", "/docs#users"],
];

const SECTIONS = [
  {
    id: "getting-started",
    title: "Getting Started",
    icon: "🚀",
    items: ["Account & organization setup", "Single-user vs multi-user", "Installing the desktop app", "Importing data from Excel / Tally"],
  },
  {
    id: "billing",
    title: "Billing, GST & e-Invoicing",
    icon: "🧾",
    items: ["Creating GST invoices", "IRN & QR (e-Invoicing)", "e-Way Bill generation", "Credit / debit notes & returns"],
  },
  {
    id: "inventory",
    title: "Inventory & Warehouse",
    icon: "📦",
    items: ["Items, batches & serials", "Multi-godown stock", "Stock transfers & adjustments", "Reorder levels & valuation"],
  },
  {
    id: "production",
    title: "Production & Job Work",
    icon: "🏭",
    items: ["Bills of Materials (BOM)", "Work orders", "Job-work outsourcing", "Heat / lot tracking"],
  },
  {
    id: "accounting",
    title: "Accounting & Reports",
    icon: "📊",
    items: ["Ledgers & vouchers", "Trial balance & P&L", "GST returns-ready reports", "Custom report builder"],
  },
  {
    id: "users",
    title: "Users, Roles & Security",
    icon: "🔐",
    items: ["Adding users", "Roles & module permissions", "Approvals & audit trail", "Data backup & recovery"],
  },
  {
    id: "integrations",
    title: "Integrations & API",
    icon: "🔌",
    items: ["REST API reference", "Webhooks", "Payment gateways", "WhatsApp / SMS"],
  },
  {
    id: "masters",
    title: "Masters Setup",
    icon: "🗂️",
    items: ["Customers & vendors", "Item master", "Tax & pricing", "Branches & godowns"],
  },
];

export default function DocsPage() {
  return (
    <>
      <PageHero
        eyebrow="Help Center"
        title="Documentation & guides"
        subtitle="Everything you need to set up, run and master Gravity One ERP — from your first invoice to advanced integrations."
      />

      {/* search bar (visual; links to contact for now) */}
      <section className="mx-auto max-w-3xl px-5 pt-12">
        <Reveal>
          <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-soft">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-slate-400">
              <circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" />
            </svg>
            <input
              className="w-full bg-transparent text-sm text-ink placeholder:text-slate-400 outline-none"
              placeholder="Search the docs — e.g. “e-Way Bill”, “add user”, “import items”"
            />
          </div>
        </Reveal>
      </section>

      {/* quickstart */}
      <section id="getting-started" className="mx-auto max-w-7xl px-5 py-16">
        <Reveal className="mx-auto max-w-2xl text-center">
          <span className="inline-block rounded-full bg-mint px-3 py-1 text-xs font-semibold uppercase tracking-wider text-primary-dark">
            Quickstart
          </span>
          <h2 className="mt-4 text-3xl font-bold tracking-tight text-ink">Go live in four steps</h2>
        </Reveal>
        <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          {QUICKSTART.map(([t, d, href], i) => (
            <Reveal key={t} delay={i * 70}>
              <Link
                href={href}
                className="flex h-full flex-col rounded-2xl border border-slate-100 bg-white p-6 shadow-soft transition hover:-translate-y-1 hover:shadow-card"
              >
                <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-sm font-bold text-white">
                  {i + 1}
                </div>
                <h3 className="font-bold text-ink">{t}</h3>
                <p className="mt-1.5 flex-1 text-sm text-body">{d}</p>
                <span className="mt-3 text-xs font-semibold text-primary">Read guide →</span>
              </Link>
            </Reveal>
          ))}
        </div>
      </section>

      {/* doc sections */}
      <section className="bg-soft py-20">
        <div className="mx-auto max-w-7xl px-5">
          <Reveal className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight text-ink">Browse by topic</h2>
            <p className="mt-3 text-body">Module-by-module guides written for real operators, not engineers.</p>
          </Reveal>
          <div className="mt-12 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
            {SECTIONS.map((s, i) => (
              <Reveal key={s.id} delay={(i % 4) * 60}>
                <div id={s.id} className="h-full scroll-mt-24 rounded-2xl border border-slate-100 bg-white p-6 shadow-soft transition hover:-translate-y-1 hover:shadow-card">
                  <div className="text-2xl">{s.icon}</div>
                  <h3 className="mt-3 font-bold text-ink">{s.title}</h3>
                  <ul className="mt-3 space-y-1.5">
                    {s.items.map((it) => (
                      <li key={it}>
                        <Link href="/contact" className="text-sm text-body transition hover:text-primary">
                          {it}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* help CTA */}
      <section className="mx-auto max-w-4xl px-5 py-20">
        <Reveal>
          <div className="relative overflow-hidden rounded-3xl border border-primary/20 bg-mint p-10 text-center">
            <h2 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">Still stuck? We're here.</h2>
            <p className="mx-auto mt-3 max-w-lg text-body">
              Get personalised help with setup, migration or any module. Our team responds fast — no call-center runaround.
            </p>
            <div className="mt-7 flex flex-wrap justify-center gap-3">
              <Link href="/contact" className="rounded-md bg-primary px-6 py-3 text-sm font-semibold text-white shadow-soft transition hover:bg-primary-dark">
                Contact Support
              </Link>
              <Link href="/download" className="rounded-md border border-slate-200 bg-white px-6 py-3 text-sm font-semibold text-ink transition hover:border-primary/40 hover:text-primary">
                Download the app
              </Link>
            </div>
          </div>
        </Reveal>
      </section>
    </>
  );
}
