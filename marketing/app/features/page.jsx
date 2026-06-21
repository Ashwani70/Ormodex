import Link from "next/link";
import PageHero from "@/components/PageHero";
import Reveal from "@/components/Reveal";

export const metadata = {
  title: "Features — All-in-one ERP modules",
  description: "Sales & CRM, Purchase, Inventory, Production, Accounting & GST, e-Invoicing, e-Way Bill, HR & Payroll and analytics — every Gravity One ERP module explained.",
};

const FEATURES = [
  ["Sales & CRM", "Capture leads, send quotations, confirm orders and track follow-ups in one pipeline that feeds straight into billing."],
  ["Purchase Management", "Raise purchase orders, record GRNs, match vendor bills and handle returns with full audit trails."],
  ["Inventory & Warehouse", "Multi-godown stock, batch and serial tracking, stock transfers and real-time valuation."],
  ["Production Planning", "Bills of material, work orders, job-work outsourcing and shop-floor visibility."],
  ["Accounting & GST", "Tally-style books, ledgers, day book and GST-ready returns built into the ledger."],
  ["e-Invoicing", "Generate IRN and QR codes directly from the invoice screen — no separate portal."],
  ["e-Way Bill Integration", "Create and track e-Way Bills inline with dispatch."],
  ["HR & Payroll", "Attendance, leave, payroll runs, payslips and statutory compliance."],
  ["Analytics Dashboard", "Live KPIs across sales, stock, cash and production."],
  ["Role-Based Access", "Granular per-user, per-module permissions and full action audit logs."],
];

export default function FeaturesPage() {
  return (
    <>
      <PageHero eyebrow="Features" title="Everything you need to run operations"
        subtitle="Fifteen-plus modules that share one database — so data flows instead of being re-keyed." />
      <section className="mx-auto max-w-7xl px-5 py-16">
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(([t, d], i) => (
            <Reveal key={t} delay={(i % 3) * 60}>
              <div className="ring-gradient h-full rounded-2xl border border-white/10 bg-surface p-6 transition hover:-translate-y-1 hover:bg-white/[0.04]">
                <div className="mb-3 h-10 w-10 rounded-xl bg-gradient-to-br from-primary to-accent" />
                <h3 className="font-bold text-white">{t}</h3>
                <p className="mt-2 text-sm text-slate-400">{d}</p>
              </div>
            </Reveal>
          ))}
        </div>
        <div className="mt-12 text-center">
          <Link href="/contact#demo" className="rounded-xl bg-gradient-to-r from-primary to-violet px-6 py-3 text-sm font-semibold text-white shadow-glow transition hover:scale-[1.03]">Book a Demo</Link>
        </div>
      </section>
    </>
  );
}
