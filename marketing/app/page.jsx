import Link from "next/link";
import Reveal from "@/components/Reveal";
import DashboardMockup from "@/components/DashboardMockup";
import DemoForm from "@/components/DemoForm";
import AuroraBackground from "@/components/AuroraBackground";
import ParallaxTilt from "@/components/ParallaxTilt";
import OSDownload from "@/components/OSDownload";
import AuthButton from "@/components/AuthButton";

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
  ["Inventory & Warehouse", "Multi-godown stock, batches, serials and transfers.", "M3 7l9-4 9 4-9 4-9-4zM3 7v10l9 4 9-4V7"],
  ["Production Planning", "BOMs, work orders and job-work tracking.", "M12 2v20M2 12h20"],
  ["Accounting & GST", "Tally-style books with GST baked in.", "M4 4h16v16H4zM8 8h8M8 12h8M8 16h5"],
  ["e-Invoicing", "IRN + QR generation, no separate portal.", "M5 3h14v18l-7-3-7 3z"],
  ["e-Way Bill", "Generate and track e-Way Bills inline.", "M3 12h13l3 3 2-2M3 12l4-4M3 12l4 4"],
  ["HR & Payroll", "Attendance, payroll, payslips and statutory.", "M12 12a4 4 0 100-8 4 4 0 000 8zM4 20a8 8 0 0116 0"],
  ["Analytics Dashboard", "Live KPIs across every module.", "M4 20V10M10 20V4M16 20v-7M22 20H2"],
  ["Role-Based Access", "Granular permissions per user and module.", "M12 2l8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6z"],
];

const INDUSTRIES = [
  ["Manufacturing", "BOMs, work orders, costing and shop-floor visibility."],
  ["Forging & Casting", "Heat-wise tracking, scrap, and job-work outsourcing."],
  ["Garments", "Style/size/colour matrices and lot-based inventory."],
  ["Trading", "Fast billing, multi-rate pricing and stock turns."],
  ["Export Businesses", "Multi-currency, export invoices and documentation."],
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
    price: "Starter",
    featured: false,
    points: ["1 user login", "All core modules", "GST billing & e-Invoicing", "Desktop + web access", "Email support"],
  },
  {
    name: "Multi User",
    who: "Growing teams that run on shared data",
    price: "Most popular",
    featured: true,
    points: ["Unlimited users & roles", "Everything in Single User", "Multi-branch / multi-godown", "Approvals & audit trail", "Priority support + onboarding"],
  },
  {
    name: "Enterprise",
    who: "Large organisations & custom workflows",
    price: "Custom",
    featured: false,
    points: ["Dedicated environment", "Custom modules & API", "SSO & advanced security", "On-prem / private cloud", "Dedicated success manager"],
  },
];

const ADDONS = [
  ["e-Invoicing & e-Way Bill", "Direct IRN/QR + e-Way Bill generation from billing."],
  ["AI Assistant", "Natural-language reports, anomaly alerts and insights."],
  ["WhatsApp & SMS", "Send invoices, payment reminders and OTPs automatically."],
  ["Payment Gateway", "Collect online payments with auto-reconciliation."],
  ["Tally / Excel Bridge", "Two-way sync and bulk import with what you use today."],
  ["Mobile App", "Approvals, dashboards and field sales on the go."],
];

const TESTIMONIALS = [
  ["Gravity One cut our monthly closing from 9 days to 2. The GST module alone paid for itself.", "Operations Head", "Forging Industry"],
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
    <span className="inline-block rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-primary-light">
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
      <section className="relative overflow-hidden bg-canvas text-white">
        <AuroraBackground />
        <div className="relative mx-auto grid max-w-7xl items-center gap-12 px-5 pb-16 pt-20 lg:grid-cols-2 lg:pb-24 lg:pt-28">
          <div className="animate-fade-up">
            <Pill>AI-Powered Business Platform</Pill>
            <h1 className="mt-5 text-4xl font-extrabold leading-[1.1] tracking-tight sm:text-5xl lg:text-6xl">
              Run your entire business on{" "}
              <span className="text-gradient">one premium ERP</span>
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-slate-300">
              Sales, inventory, accounting, GST, production, HR and e-Way Bills — for
              a single user or your whole team. On Windows, macOS, Linux and the web.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <OSDownload compact />
              <AuthButton variant="primary" />
              <Link
                href="#tour"
                className="rounded-xl border border-white/15 px-6 py-3 text-sm font-semibold text-white transition hover:border-white/40 hover:bg-white/5"
              >
                ▶ Watch Product Tour
              </Link>
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-400">
              <span>✓ GST Compliant</span>
              <span>✓ e-Invoicing & e-Way Bill</span>
              <span>✓ 15+ Modules</span>
              <span>✓ Single & Multi-user</span>
            </div>
          </div>

          <div className="animate-float lg:pl-6">
            <ParallaxTilt max={9}>
              <DashboardMockup />
            </ParallaxTilt>
          </div>
        </div>

        {/* customer logo marquee */}
        <div className="relative border-t border-white/10 bg-black/20">
          <div className="mx-auto max-w-7xl px-5 py-6">
            <p className="mb-4 text-center text-xs uppercase tracking-widest text-slate-500">
              Trusted by industry leaders
            </p>
            <div className="group relative overflow-hidden">
              <div className="flex w-max animate-marquee items-center gap-12 group-hover:[animation-play-state:paused]">
                {[...LOGOS, ...LOGOS].map((l, i) => (
                  <span key={i} className="text-sm font-bold tracking-wide text-slate-500">{l}</span>
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
          <h2 className="mt-4 text-3xl font-extrabold tracking-tight text-white sm:text-4xl">Stop fighting your tools</h2>
          <p className="mt-3 text-slate-400">If any of these sound familiar, you're running your business on borrowed time.</p>
        </Reveal>
        <div className="mt-14 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {PROBLEMS.map(([t, d], i) => (
            <Reveal key={t} delay={i * 60}>
              <div className="ring-gradient h-full rounded-2xl border border-white/10 bg-surface p-6 transition hover:bg-white/[0.04]">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-red-500/10 text-red-400">✕</div>
                <h3 className="font-bold text-white">{t}</h3>
                <p className="mt-1.5 text-sm text-slate-400">{d}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* 3 ── FEATURES ───────────────────────────────────────────── */}
      <section id="features" className="relative overflow-hidden py-24">
        <div className="pointer-events-none absolute left-1/2 top-0 h-72 w-[50rem] -translate-x-1/2 rounded-full bg-primary/10 blur-[120px]" />
        <div className="relative mx-auto max-w-7xl px-5">
          <Reveal className="mx-auto max-w-2xl text-center">
            <Pill>Everything in one platform</Pill>
            <h2 className="mt-4 text-3xl font-extrabold tracking-tight text-white sm:text-4xl">Powerful modules, one login</h2>
          </Reveal>
          <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {FEATURES.map(([t, d, icon], i) => (
              <Reveal key={t} delay={(i % 5) * 50}>
                <div className="ring-gradient h-full rounded-2xl border border-white/10 bg-surface p-5 transition hover:-translate-y-1 hover:bg-white/[0.04]">
                  <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary/30 to-accent/20 text-primary-light">
                    <Icon d={icon} />
                  </div>
                  <h3 className="text-sm font-bold text-white">{t}</h3>
                  <p className="mt-1.5 text-xs leading-relaxed text-slate-400">{d}</p>
                </div>
              </Reveal>
            ))}
          </div>
          <div className="mt-10 text-center">
            <Link href="/features" className="text-sm font-semibold text-primary-light hover:text-white">
              Explore all features →
            </Link>
          </div>
        </div>
      </section>

      {/* 4 ── BENEFITS ───────────────────────────────────────────── */}
      <section className="border-y border-white/10 bg-surface py-16">
        <div className="mx-auto grid max-w-7xl gap-6 px-5 sm:grid-cols-2 lg:grid-cols-5">
          {BENEFITS.map(([big, small], i) => (
            <Reveal key={small} delay={i * 70}>
              <div className="text-center">
                <div className="text-4xl font-extrabold text-gradient">{big}</div>
                <div className="mt-1 text-sm text-slate-400">{small}</div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* 5 ── INDUSTRIES ─────────────────────────────────────────── */}
      <section id="industries" className="mx-auto max-w-7xl px-5 py-24">
        <Reveal className="mx-auto max-w-2xl text-center">
          <Pill>Built for your industry</Pill>
          <h2 className="mt-4 text-3xl font-extrabold tracking-tight text-white sm:text-4xl">Industry solutions</h2>
        </Reveal>
        <div className="mt-14 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {INDUSTRIES.map(([t, d], i) => (
            <Reveal key={t} delay={i * 60}>
              <div className="ring-gradient group h-full overflow-hidden rounded-2xl border border-white/10 bg-surface transition hover:bg-white/[0.04]">
                <div className="h-1.5 bg-gradient-to-r from-primary via-accent to-violet" />
                <div className="p-6">
                  <h3 className="text-lg font-bold text-white">{t}</h3>
                  <p className="mt-2 text-sm text-slate-400">{d}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* 6 ── PRODUCT TOUR ───────────────────────────────────────── */}
      <section id="tour" className="mx-auto max-w-7xl px-5 py-24">
        <Reveal className="mx-auto max-w-2xl text-center">
          <Pill>Product tour</Pill>
          <h2 className="mt-4 text-3xl font-extrabold tracking-tight text-white sm:text-4xl">See it in action</h2>
          <p className="mt-3 text-slate-400">A cinematic walkthrough of dashboards, billing, inventory and reports.</p>
        </Reveal>
        <Reveal className="mt-12">
          <ParallaxTilt max={5} glare={false}>
            <div className="relative mx-auto flex aspect-video max-w-4xl items-center justify-center overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-surface to-ink shadow-card">
              <div className="pointer-events-none absolute inset-0 bg-radial-fade" />
              <button
                className="relative flex h-20 w-20 items-center justify-center rounded-full bg-white/90 text-ink shadow-glow transition hover:scale-110"
                aria-label="Play product tour"
              >
                <span className="ml-1 text-2xl">▶</span>
              </button>
            </div>
          </ParallaxTilt>
        </Reveal>
      </section>

      {/* 7 ── DOWNLOAD (cross-platform) ──────────────────────────── */}
      <section id="download" className="relative overflow-hidden border-y border-white/10 bg-ink py-24">
        <AuroraBackground className="opacity-60" />
        <div className="relative mx-auto max-w-7xl px-5">
          <Reveal className="mx-auto max-w-2xl text-center">
            <Pill>Download the app</Pill>
            <h2 className="mt-4 text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
              Get Gravity One on every device
            </h2>
            <p className="mt-3 text-slate-400">
              Native desktop apps for Windows, macOS and Linux — or open it instantly in your browser.
            </p>
          </Reveal>
          <Reveal className="mt-12">
            <OSDownload />
          </Reveal>
        </div>
      </section>

      {/* 8 ── PRICING: single vs multi-user ──────────────────────── */}
      <section id="pricing" className="py-24">
        <div className="mx-auto max-w-7xl px-5">
          <Reveal className="mx-auto max-w-2xl text-center">
            <Pill>Simple pricing</Pill>
            <h2 className="mt-4 text-3xl font-extrabold tracking-tight text-white sm:text-4xl">Single user or your whole team</h2>
            <p className="mt-3 text-slate-400">Start solo, scale to unlimited users. Upgrade anytime — your data comes with you.</p>
          </Reveal>
          <div className="mt-14 grid gap-6 lg:grid-cols-3">
            {PLANS.map((p, i) => (
              <Reveal key={p.name} delay={i * 80}>
                <div
                  className={`relative flex h-full flex-col rounded-3xl border p-7 ${
                    p.featured
                      ? "border-primary/50 bg-gradient-to-b from-primary/15 to-surface shadow-glow lg:-translate-y-3"
                      : "border-white/10 bg-surface"
                  }`}
                >
                  {p.featured && (
                    <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-gradient-to-r from-primary to-violet px-3 py-1 text-xs font-semibold text-white shadow-glow">
                      Most popular
                    </span>
                  )}
                  <h3 className="text-xl font-bold text-white">{p.name}</h3>
                  <p className="mt-1 text-sm text-slate-400">{p.who}</p>
                  <div className="mt-5 text-lg font-extrabold text-gradient">{p.price}</div>
                  <ul className="mt-5 flex-1 space-y-2.5 text-sm text-slate-300">
                    {p.points.map((pt) => (
                      <li key={pt} className="flex items-start gap-2">
                        <span className="mt-0.5 text-accent">✓</span>
                        {pt}
                      </li>
                    ))}
                  </ul>
                  <Link
                    href="/contact"
                    className={`mt-7 rounded-xl px-5 py-2.5 text-center text-sm font-semibold transition ${
                      p.featured
                        ? "bg-gradient-to-r from-primary to-violet text-white shadow-glow hover:scale-[1.03]"
                        : "border border-white/15 text-white hover:bg-white/5"
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

      {/* 9 ── ADD-ONS ────────────────────────────────────────────── */}
      <section className="border-y border-white/10 bg-surface py-24">
        <div className="mx-auto max-w-7xl px-5">
          <Reveal className="mx-auto max-w-2xl text-center">
            <Pill>Power-ups</Pill>
            <h2 className="mt-4 text-3xl font-extrabold tracking-tight text-white sm:text-4xl">Add-ons that grow with you</h2>
            <p className="mt-3 text-slate-400">Switch on extra capabilities for single-user or multi-user plans — only pay for what you use.</p>
          </Reveal>
          <div className="mt-14 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {ADDONS.map(([t, d], i) => (
              <Reveal key={t} delay={i * 50}>
                <div className="ring-gradient flex h-full items-start gap-4 rounded-2xl border border-white/10 bg-ink p-6 transition hover:bg-white/[0.04]">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-accent/30 to-primary/20 text-accent">+</span>
                  <div>
                    <h3 className="font-bold text-white">{t}</h3>
                    <p className="mt-1 text-sm text-slate-400">{d}</p>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* 10 ── TESTIMONIALS ──────────────────────────────────────── */}
      <section className="mx-auto max-w-7xl px-5 py-24">
        <Reveal className="mx-auto max-w-2xl text-center">
          <Pill>Success stories</Pill>
          <h2 className="mt-4 text-3xl font-extrabold tracking-tight text-white sm:text-4xl">Loved by operators</h2>
        </Reveal>
        <div className="mt-14 grid gap-6 md:grid-cols-3">
          {TESTIMONIALS.map(([quote, who, ind], i) => (
            <Reveal key={who} delay={i * 70}>
              <figure className="ring-gradient flex h-full flex-col rounded-2xl border border-white/10 bg-surface p-6">
                <div className="mb-3 text-accent">★★★★★</div>
                <blockquote className="flex-1 text-sm leading-relaxed text-slate-200">“{quote}”</blockquote>
                <figcaption className="mt-4 border-t border-white/10 pt-3 text-sm">
                  <span className="font-semibold text-white">{who}</span>
                  <span className="text-slate-500"> · {ind}</span>
                </figcaption>
              </figure>
            </Reveal>
          ))}
        </div>
      </section>

      {/* 11 ── FAQ ───────────────────────────────────────────────── */}
      <section className="py-24">
        <div className="mx-auto max-w-3xl px-5">
          <Reveal className="text-center">
            <Pill>Questions</Pill>
            <h2 className="mt-4 text-3xl font-extrabold tracking-tight text-white sm:text-4xl">Frequently asked</h2>
          </Reveal>
          <div className="mt-12 space-y-3">
            {FAQS.map(([q, a], i) => (
              <Reveal key={q} delay={i * 40}>
                <details className="group rounded-2xl border border-white/10 bg-surface p-5 [&_summary]:cursor-pointer">
                  <summary className="flex items-center justify-between font-semibold text-white marker:content-['']">
                    {q}
                    <span className="ml-4 text-primary-light transition group-open:rotate-45">+</span>
                  </summary>
                  <p className="mt-3 text-sm leading-relaxed text-slate-400">{a}</p>
                </details>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* 12 ── CONTACT / DEMO FORM ───────────────────────────────── */}
      <section id="demo" className="relative overflow-hidden border-t border-white/10 bg-ink py-24">
        <AuroraBackground className="opacity-50" />
        <div className="relative mx-auto grid max-w-7xl items-start gap-12 px-5 lg:grid-cols-2">
          <Reveal>
            <Pill>Book a demo</Pill>
            <h2 className="mt-4 text-3xl font-extrabold tracking-tight text-white sm:text-4xl">See Gravity One on your data</h2>
            <p className="mt-4 max-w-md text-slate-300">
              Tell us about your business and we'll tailor a walkthrough. Submissions go straight
              into our team's pipeline — no bots, no call-center runaround.
            </p>
            <ul className="mt-6 space-y-2 text-sm text-slate-300">
              <li>✓ 1-on-1 personalised demo</li>
              <li>✓ Industry-specific configuration</li>
              <li>✓ Free trial, install help and onboarding</li>
            </ul>
            <div className="mt-8">
              <AuthButton variant="primary" />
            </div>
          </Reveal>
          <Reveal delay={120}>
            <div className="glass-strong rounded-3xl p-6 shadow-card sm:p-8">
              <DemoForm />
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
