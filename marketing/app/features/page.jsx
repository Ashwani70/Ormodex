import Link from "next/link";
import PageHero from "@/components/PageHero";
import Reveal from "@/components/Reveal";
import { FeatureIconMap } from "@/components/FeatureIcons";

export const metadata = {
  title: "Features — All-in-one ERP modules",
  description: "Sales & CRM, Purchase, Inventory, Production, Accounting & GST, e-Invoicing, e-Way Bill, HR & Payroll and analytics — every Ormodex ERP module explained.",
};

const FEATURES = [
  ["Sales & CRM", "Capture leads, send quotations, confirm orders and track follow-ups in one pipeline that feeds straight into billing."],
  ["Purchase Management", "Raise purchase orders, record GRNs, match vendor bills and handle returns with full audit trails."],
  ["Inventory & Warehouse", "Multi-warehouse stock, batch and serial tracking, stock transfers and real-time valuation."],
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
          {FEATURES.map(([t, d], i) => {
            const IconComponent = FeatureIconMap[t];
            return (
              <Reveal key={t} delay={(i % 3) * 60}>
                <div className="group h-full rounded-2xl border border-slate-100/80 border-t-2 border-t-primary/20 bg-gradient-to-b from-white to-slate-50/40 p-6 shadow-soft transition-all duration-300 hover:-translate-y-1.5 hover:border-t-primary hover:shadow-card">
                  <div className="relative mb-4 inline-flex p-3 rounded-2xl bg-white border border-slate-100 shadow-sm transition-transform duration-300 group-hover:scale-110">
                    {IconComponent ? (
                      <IconComponent className="w-10 h-10" />
                    ) : (
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-mint text-primary">✦</div>
                    )}
                  </div>
                  <h3 className="font-bold text-ink text-lg transition-colors duration-300 group-hover:text-primary">{t}</h3>
                  <p className="mt-2 text-sm text-body leading-relaxed">{d}</p>
                </div>
              </Reveal>
            );
          })}
        </div>
        <div className="mt-12 text-center">
          <Link href="/contact#demo" className="rounded-md bg-primary px-6 py-3 text-sm font-semibold text-white shadow-soft transition hover:bg-primary-dark">Book a Demo</Link>
        </div>
      </section>
    </>
  );
}

