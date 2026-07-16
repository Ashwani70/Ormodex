import Link from "next/link";
import Reveal from "@/components/Reveal";
import HeroIllustration from "@/components/HeroIllustration";
import DemoForm from "@/components/DemoForm";
import AuroraBackground from "@/components/AuroraBackground";
import OSDownload from "@/components/OSDownload";
import ProductTourVideo from "@/components/ProductTourVideo";
import { ProblemIconMap } from "@/components/ProblemIcons";

// ── Data ──────────────────────────────────────────────────────────────
const LOGOS = ["NORTHFORGE", "SteelCraft", "VESTRA", "Apex Castings", "Loomwise", "EXIM Global"];

const PROBLEMS = [
  ["Manual spreadsheets", "Scattered Excel files that break, conflict and never reconcile."],
  ["Duplicate data entry", "The same order keyed into 3 systems — slow and error-prone."],
  ["Inventory mismatches", "Physical stock never matches the books; sales over-commit."],
  ["Delayed invoicing", "Dispatch happens days before the invoice — cash flow suffers."],
  ["GST compliance stress", "Manual returns, mismatched ITC and last-minute filing panic."],
  ["No real-time reporting", "Decisions made on last month's numbers, not today's."],
];

const FEATURES = [
  ["Sales & CRM", "Leads, quotes, orders and follow-ups in one pipeline.", "M3 7h18M3 12h18M3 17h12"],
  ["Purchase Management", "POs, GRNs, vendor bills and returns end-to-end.", "M6 2l1 4h13l-2 9H8L6 2H3"],
  ["Inventory & Warehouse", "Multi-warehouse stock, batches, serials and transfers.", "M3 7l9-4 9 4-9 4-9-4zM3 7v10l9 4 9-4V7"],
  ["Production Planning", "BOMs, work orders and job-work tracking.", "M12 2v20M2 12h20"],
  ["Accounting & GST", "Tally-style books with GST baked in.", "M4 4h16v16H4zM8 8h8M8 12h8M8 16h5"],
  ["e-Invoicing", "IRN + QR generation, no separate portal.", "M5 3h14v18l-7-3-7 3z"],
  ["e-Way Bill", "Generate and track e-Way Bills inline.", "M3 12h13l3 3 2-2M3 12l4-4M3 12l4 4"],
  ["HR & Payroll", "Attendance, payroll, payslips and statutory.", "M12 12a4 4 0 100-8 4 4 0 000 8zM4 20a8 8 0 0116 0"],
  ["Analytics Dashboard", "Live KPIs across every module.", "M4 20V10M10 20V4M16 20v-7M22 20H2"],
  ["Role-Based Access", "Granular permissions per user and module.", "M12 2l8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6z"],
];

const INDUSTRIES = [
  {
    title: "Manufacturing",
    description: "BOMs, work orders, costing and shop-floor visibility.",
    image: "/images/manufacturing.png",
    id: "manufacturing",
    features: ["Multi-level BOMs", "Job Card Tracking", "WIP Valuation", "Cost estimation"],
  },
  {
    title: "Forging & Casting",
    description: "Heat-wise tracking, scrap, and job-work outsourcing.",
    image: "/images/forging.png",
    id: "forging",
    features: ["Heat-number traceability", "Scrap & recovery tracking", "Subcontracting / Job-work", "Furnace logbooks"],
  },
  {
    title: "Garments",
    description: "Style/size/colour matrices and lot-based inventory.",
    image: "/images/garments.png",
    id: "garments",
    features: ["Matrix grid inputs", "Lot & bundle tracking", "Bespoke production orders", "Trim & accessory planning"],
  },
  {
    title: "Trading",
    description: "Fast billing, multi-rate pricing and stock turns.",
    image: "/images/trading.png",
    id: "trading",
    features: ["Point of Sale (POS)", "Batch & expiry management", "Multiple price lists", "Real-time stock aging"],
  },
  {
    title: "Export Businesses",
    description: "Multi-currency, export invoices and documentation.",
    image: "/images/export.png",
    id: "export",
    features: ["Multi-currency billing", "Export invoices & packing lists", "Duty drawback tracking", "Shipping bill reference"],
  },
];

const BENEFITS = [
  ["70%", "less manual work"],
  ["99%+", "inventory accuracy"],
  ["3×", "faster invoicing"],
  ["100%", "GST compliant"],
  ["24/7", "real-time visibility"],
];

const PLANS = [
  {
    name: "Single User",
    who: "Solo founders, accountants & small shops",
    price: "₹1,499",
    unit: "/month",
    featured: false,
    points: ["1 user login", "All core modules", "GST billing & e-Invoicing", "Desktop + web access", "Email support"],
  },
  {
    name: "Multi User",
    who: "Growing teams that run on shared data",
    price: "₹999",
    unit: "/user/month",
    featured: true,
    points: ["Unlimited users & roles", "Everything in Single User", "Multi-branch / multi-warehouse", "Approvals & audit trail", "Priority support + onboarding"],
  },
  {
    name: "Enterprise",
    who: "Large organisations & custom workflows",
    price: "Custom",
    unit: "",
    featured: false,
    points: ["Dedicated environment", "Custom modules & API", "SSO & advanced security", "On-prem / private cloud", "Dedicated success manager"],
  },
];


const TESTIMONIALS = [
  ["Ormodex cut our monthly closing from 9 days to 2. The GST module alone paid for itself.", "Operations Head", "Forging Industry"],
  ["Stock accuracy went from chaos to 99%. Our sales team finally trusts the numbers.", "Director", "Garment Manufacturer"],
  ["e-Invoicing and e-Way Bills in the same screen as billing — huge time saver for exports.", "Finance Manager", "Export House"],
];

const FAQS = [
  ["Is my data secure?", "Yes — role-based access, end-to-end encryption and audited changes. Your data stays isolated to your organization."],
  ["Does it work offline / as a desktop app?", "Yes. Download native installers for Windows, macOS and Linux, or run it entirely in the browser — your data syncs either way."],
  ["Single user or multiple users?", "Both. Start as a single user and upgrade to unlimited users with granular, role-based permissions at any time."],
  ["Does it support GST & e-Invoicing?", "Fully. GST-compliant invoicing, returns-ready reports, e-Invoicing (IRN/QR) and e-Way Bill generation are built in."],
  ["Can it integrate with my existing tools?", "Yes — REST APIs plus Tally/Excel import bridges to connect billing, banking and software you already use."],
];

// ── Small helpers ─────────────────────────────────────────────────────
function Pill({ children }) {
  return (
    <span className="inline-block rounded-full bg-mint px-3 py-1 text-xs font-semibold uppercase tracking-wider text-primary-dark">
      {children}
    </span>
  );
}

function Icon({ d }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
      <path d={d} />
    </svg>
  );
}

export default function Home() {
  return (
    <>
      {/* 1 ── HERO ───────────────────────────────────────────────── */}
      <section className="relative overflow-hidden bg-soft">
        <AuroraBackground />
        <div className="relative mx-auto grid max-w-7xl items-center gap-12 px-5 pb-16 pt-16 lg:grid-cols-2 lg:pb-24 lg:pt-24">
          <div className="animate-fade-up">
            <Pill>AI-Powered Business Platform</Pill>
            <h1 className="mt-5 text-4xl font-bold leading-[1.1] tracking-tight text-ink sm:text-5xl lg:text-6xl">
              Run your entire business on{" "}
              <span className="text-primary">one simple ERP</span>
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-body">
              Sales, inventory, accounting, GST, production, HR and e-Way Bills — for
              a single user or your whole team. On Windows, macOS, Linux and the web.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <OSDownload compact />
              <a
                href="#tour"
                className="rounded-md border border-slate-200 bg-white px-6 py-3 text-sm font-semibold text-ink transition hover:border-primary/40 hover:text-primary"
              >
                ▶ Watch Product Tour
              </a>
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-body">
              <span>✓ GST Compliant</span>
              <span>✓ e-Invoicing & e-Way Bill</span>
              <span>✓ 15+ Modules</span>
              <span>✓ Single & Multi-user</span>
            </div>
          </div>

          <div className="animate-float lg:pl-6">
            <HeroIllustration className="mx-auto w-full max-w-xl drop-shadow-[0_20px_40px_rgba(38,50,56,0.12)]" />
          </div>
        </div>

        {/* customer logo marquee */}
        <div className="relative border-t border-slate-200 bg-white">
          <div className="mx-auto max-w-7xl px-5 py-8">
            <p className="mb-5 text-center text-sm font-semibold text-ink">
              Trusted by Fortune 500+ clients
            </p>
            <div className="group relative overflow-hidden">
              <div className="flex w-max animate-marquee items-center gap-14 group-hover:[animation-play-state:paused]">
                {[...LOGOS, ...LOGOS].map((l, i) => (
                  <span key={i} className="text-sm font-bold tracking-wide text-slate-400">{l}</span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 2 ── PROBLEMS ───────────────────────────────────────────── */}
      <section className="mx-auto max-w-7xl px-5 py-24">
        <Reveal className="mx-auto max-w-2xl text-center">
          <Pill>The problems we solve</Pill>
          <h2 className="mt-4 text-3xl font-bold tracking-tight text-ink sm:text-4xl">Stop fighting your tools</h2>
          <p className="mt-3 text-body">If any of these sound familiar, you're running your business on borrowed time.</p>
        </Reveal>
        <div className="mt-14 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {PROBLEMS.map(([t, d], i) => {
            const ProblemIcon = ProblemIconMap[t];
            return (
              <Reveal key={t} delay={i * 60}>
                <div className="group h-full rounded-2xl border border-slate-100/80 border-t-2 border-t-red-400/20 bg-gradient-to-b from-white to-slate-50/40 p-6 shadow-soft transition-all duration-300 hover:-translate-y-1.5 hover:border-t-red-500 hover:shadow-card">
                  <div className="relative mb-4 inline-flex p-3 rounded-2xl bg-white border border-slate-100 shadow-sm transition-transform duration-300 group-hover:scale-110">
                    {ProblemIcon ? (
                      <ProblemIcon className="w-10 h-10" />
                    ) : (
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-50 text-red-500">
                        <Icon d="M18 6 6 18M6 6l12 12" />
                      </div>
                    )}
                  </div>
                  <h3 className="font-bold text-ink text-lg transition-colors duration-300 group-hover:text-red-500">{t}</h3>
                  <p className="mt-2 text-sm text-body leading-relaxed">{d}</p>
                </div>
              </Reveal>
            );
          })}
        </div>
      </section>

      {/* 3 ── FEATURES ───────────────────────────────────────────── */}
      <section id="features" className="bg-soft py-24">
        <div className="mx-auto max-w-7xl px-5">
          <Reveal className="mx-auto max-w-2xl text-center">
            <Pill>Everything in one platform</Pill>
            <h2 className="mt-4 text-3xl font-bold tracking-tight text-ink sm:text-4xl">Manage your entire business in a single system</h2>
            <p className="mt-3 text-body">Powerful modules that share one database — so data flows instead of being re-keyed.</p>
          </Reveal>
          <div className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {FEATURES.map(([t, d, icon], i) => (
              <Reveal key={t} delay={(i % 5) * 50}>
                <div className="group h-full rounded-2xl border border-slate-100/80 border-t-2 border-t-primary/20 bg-gradient-to-b from-white to-slate-50/40 p-5 shadow-soft transition-all duration-300 hover:-translate-y-1.5 hover:border-t-primary hover:shadow-card">
                  <div className="relative mb-4 inline-flex p-2 rounded-xl bg-white border border-slate-100 shadow-sm transition-transform duration-300 group-hover:scale-110 text-primary">
                    <Icon d={icon} />
                  </div>
                  <h3 className="text-sm font-bold text-ink transition-colors duration-300 group-hover:text-primary">{t}</h3>
                  <p className="mt-1.5 text-xs leading-relaxed text-body">{d}</p>
                </div>
              </Reveal>
            ))}
          </div>
          <div className="mt-10 text-center">
            <Link href="/features" className="text-sm font-semibold text-primary hover:text-primary-dark">
              Explore all features →
            </Link>
          </div>
        </div>
      </section>

      {/* 4 ── BENEFITS ───────────────────────────────────────────── */}
      <section className="mx-auto max-w-7xl px-5 py-16">
        <div className="grid gap-6 rounded-2xl border border-slate-100 bg-white p-8 shadow-soft sm:grid-cols-2 lg:grid-cols-5">
          {BENEFITS.map(([big, small], i) => (
            <Reveal key={small} delay={i * 70}>
              <div className="text-center">
                <div className="text-4xl font-bold text-primary">{big}</div>
                <div className="mt-1 text-sm text-body">{small}</div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* 5 ── INDUSTRIES ─────────────────────────────────────────── */}
      <section id="industries" className="mx-auto max-w-7xl px-5 py-24">
        <Reveal className="mx-auto max-w-2xl text-center">
          <Pill>Built for your industry</Pill>
          <h2 className="mt-4 text-3xl font-bold tracking-tight text-ink sm:text-4xl">Industry solutions</h2>
        </Reveal>
        <div className="mt-14 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {INDUSTRIES.map(({ title, description, image, id, features }, i) => (
            <Reveal key={title} delay={i * 60}>
              <Link href={`/industries#${id}`} className="group block h-full">
                <div className="flex h-full flex-col overflow-hidden rounded-3xl border border-slate-100 bg-white shadow-soft transition-all duration-300 hover:-translate-y-2 hover:shadow-card">
                  <div className="relative h-48 w-full overflow-hidden bg-slate-100">
                    <div className="absolute top-4 left-4 z-10 rounded-full bg-white/95 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-primary shadow-sm backdrop-blur-sm">
                      ERP Solution
                    </div>
                    <img
                      src={image}
                      alt={title}
                      className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                    />
                  </div>
                  <div className="flex flex-1 flex-col p-6">
                    <h3 className="text-lg font-bold text-ink transition-colors duration-300 group-hover:text-primary">
                      {title}
                    </h3>
                    <p className="mt-2 text-sm leading-relaxed text-body">{description}</p>
                    <div className="my-4 border-t border-slate-100" />
                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Key Capabilities
                    </p>
                    <ul className="mt-3 flex-1 space-y-2">
                      {features.map((feat) => (
                        <li key={feat} className="flex items-center gap-2 text-xs text-body">
                          <svg className="h-4 w-4 shrink-0 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                          <span>{feat}</span>
                        </li>
                      ))}
                    </ul>
                    <div className="mt-6 flex items-center gap-1.5 text-xs font-semibold text-primary">
                      <span>Learn more</span>
                      <svg className="h-3.5 w-3.5 transition-transform duration-300 group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                      </svg>
                    </div>
                  </div>
                </div>
              </Link>
            </Reveal>
          ))}
        </div>
      </section>

      {/* 6 ── PRODUCT TOUR ───────────────────────────────────────── */}
      <section id="tour" className="bg-soft py-24">
        <div className="mx-auto max-w-7xl px-5">
          <Reveal className="mx-auto max-w-2xl text-center">
            <Pill>Product tour</Pill>
            <h2 className="mt-4 text-3xl font-bold tracking-tight text-ink sm:text-4xl">See it in action</h2>
            <p className="mt-3 text-body">A quick walkthrough of dashboards, billing, inventory and reports.</p>
          </Reveal>
          <Reveal className="mt-12">
            <ProductTourVideo />
          </Reveal>
        </div>
      </section>

      {/* 7 ── DOWNLOAD (cross-platform) ──────────────────────────── */}
      <section id="download" className="mx-auto max-w-7xl px-5 py-24">
        <Reveal className="mx-auto max-w-2xl text-center">
          <Pill>Download the app</Pill>
          <h2 className="mt-4 text-3xl font-bold tracking-tight text-ink sm:text-4xl">
            Get Ormodex on every device
          </h2>
          <p className="mt-3 text-body">
            Native desktop apps for Windows, macOS and Linux — or open it instantly in your browser.
          </p>
        </Reveal>
        <Reveal className="mt-12">
          <OSDownload />
        </Reveal>
      </section>

      {/* 8 ── PRICING: single vs multi-user ──────────────────────── */}
      <section id="pricing" className="bg-soft py-24">
        <div className="mx-auto max-w-7xl px-5">
          <Reveal className="mx-auto max-w-2xl text-center">
            <Pill>Simple pricing</Pill>
            <h2 className="mt-4 text-3xl font-bold tracking-tight text-ink sm:text-4xl">Single user or your whole team</h2>
            <p className="mt-3 text-body">Start solo, scale to unlimited users. Upgrade anytime — your data comes with you. Prices in INR, exclusive of GST.</p>
          </Reveal>
          <div className="mt-14 grid gap-6 lg:grid-cols-3">
            {PLANS.map((p, i) => (
              <Reveal key={p.name} delay={i * 80}>
                <div
                  className={`relative flex h-full flex-col rounded-3xl border p-7 transition ${
                    p.featured
                      ? "border-primary bg-white shadow-card lg:-translate-y-3"
                      : "border-slate-100 bg-white shadow-soft"
                  }`}
                >
                  {p.featured && (
                    <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-1 text-xs font-semibold text-white shadow-glow">
                      Most popular
                    </span>
                  )}
                  <h3 className="text-xl font-bold text-ink">{p.name}</h3>
                  <p className="mt-1 text-sm text-body">{p.who}</p>
                  <div className="mt-5">
                    <span className="text-3xl font-bold text-primary">{p.price}</span>
                    {p.unit && <span className="text-sm font-medium text-body">{p.unit}</span>}
                  </div>
                  <ul className="mt-5 flex-1 space-y-2.5 text-sm text-body">
                    {p.points.map((pt) => (
                      <li key={pt} className="flex items-start gap-2">
                        <span className="mt-0.5 text-primary">✓</span>
                        {pt}
                      </li>
                    ))}
                  </ul>
                  <Link
                    href="/contact"
                    className={`mt-7 rounded-md px-5 py-2.5 text-center text-sm font-semibold transition ${
                      p.featured
                        ? "bg-primary text-white shadow-soft hover:bg-primary-dark"
                        : "border border-slate-200 text-ink hover:border-primary/40 hover:text-primary"
                    }`}
                  >
                    Request Pricing
                  </Link>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* 10 ── TESTIMONIALS ──────────────────────────────────────── */}
      <section className="bg-soft py-24">
        <div className="mx-auto max-w-7xl px-5">
          <Reveal className="mx-auto max-w-2xl text-center">
            <Pill>Success stories</Pill>
            <h2 className="mt-4 text-3xl font-bold tracking-tight text-ink sm:text-4xl">Loved by operators</h2>
          </Reveal>
          <div className="mt-14 grid gap-6 md:grid-cols-3">
            {TESTIMONIALS.map(([quote, who, ind], i) => (
              <Reveal key={who} delay={i * 70}>
                <figure className="flex h-full flex-col rounded-2xl border border-slate-100 bg-white p-6 shadow-soft">
                  <div className="mb-3 text-primary">★★★★★</div>
                  <blockquote className="flex-1 text-sm leading-relaxed text-ink">“{quote}”</blockquote>
                  <figcaption className="mt-4 border-t border-slate-100 pt-3 text-sm">
                    <span className="font-semibold text-ink">{who}</span>
                    <span className="text-body"> · {ind}</span>
                  </figcaption>
                </figure>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* 11 ── FAQ ───────────────────────────────────────────────── */}
      <section className="py-24">
        <div className="mx-auto max-w-3xl px-5">
          <Reveal className="text-center">
            <Pill>Questions</Pill>
            <h2 className="mt-4 text-3xl font-bold tracking-tight text-ink sm:text-4xl">Frequently asked</h2>
          </Reveal>
          <div className="mt-12 space-y-3">
            {FAQS.map(([q, a], i) => (
              <Reveal key={q} delay={i * 40}>
                <details className="group rounded-2xl border border-slate-100 bg-white p-5 shadow-soft [&_summary]:cursor-pointer">
                  <summary className="flex items-center justify-between font-semibold text-ink marker:content-['']">
                    {q}
                    <span className="ml-4 text-primary transition group-open:rotate-45">+</span>
                  </summary>
                  <p className="mt-3 text-sm leading-relaxed text-body">{a}</p>
                </details>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* 12 ── CONTACT / DEMO FORM ───────────────────────────────── */}
      <section id="demo" className="bg-soft py-24">
        <div className="mx-auto grid max-w-7xl items-start gap-12 px-5 lg:grid-cols-2">
          <Reveal>
            <Pill>Book a demo</Pill>
            <h2 className="mt-4 text-3xl font-bold tracking-tight text-ink sm:text-4xl">See Ormodex on your data</h2>
            <p className="mt-4 max-w-md text-body">
              Tell us about your business and we'll tailor a walkthrough. Submissions go straight
              into our team's pipeline — no bots, no call-center runaround.
            </p>
            <ul className="mt-6 space-y-2 text-sm text-body">
              <li>✓ 1-on-1 personalised demo</li>
              <li>✓ Industry-specific configuration</li>
              <li>✓ Free trial, install help and onboarding</li>
            </ul>
            <div className="mt-8">
            </div>
          </Reveal>
          <Reveal delay={120}>
            <div className="rounded-3xl border border-slate-100 bg-white p-6 shadow-card sm:p-8">
              <DemoForm />
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
