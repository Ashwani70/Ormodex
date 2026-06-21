import Link from "next/link";
import { ERP_LOGIN_URL } from "@/lib/site";

const COLS = [
  {
    title: "Product",
    links: [
      ["Features", "/features"],
      ["Pricing", "/pricing"],
      ["Download App", "/download"],
      ["Book a Demo", "/contact#demo"],
    ],
  },
  {
    title: "Resources",
    links: [
      ["Documentation", "/docs"],
      ["Getting Started", "/docs#getting-started"],
      ["Blog", "/blog"],
      ["Open the App", ERP_LOGIN_URL],
    ],
  },
  {
    title: "Solutions",
    links: [
      ["Manufacturing", "/industries#manufacturing"],
      ["Forging & Casting", "/industries#forging"],
      ["Garments", "/industries#garments"],
      ["Export Businesses", "/industries#export"],
    ],
  },
  {
    title: "Company",
    links: [
      ["About Us", "/about"],
      ["Contact", "/contact"],
    ],
  },
];

export default function Footer() {
  return (
    <footer className="border-t border-slate-100 bg-soft text-body">
      <div className="mx-auto grid max-w-7xl gap-10 px-5 py-16 md:grid-cols-2 lg:grid-cols-6">
        <div className="lg:col-span-2">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary font-black text-white">
              G
            </span>
            <span className="text-xl font-bold tracking-tight text-ink">
              Gravity<span className="text-primary">One</span>
            </span>
          </div>
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-body">
            The intelligent ERP for modern enterprise operations — sales, inventory,
            accounting, GST, production and HR on one platform. Available on Windows,
            macOS, Linux and the web.
          </p>
          <div className="mt-5 flex gap-2">
            {["Windows", "macOS", "Linux"].map((p) => (
              <span key={p} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-body">
                {p}
              </span>
            ))}
          </div>
        </div>
        {COLS.map((c) => (
          <div key={c.title}>
            <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-ink">{c.title}</h4>
            <ul className="space-y-2">
              {c.links.map(([label, href]) => (
                <li key={label}>
                  <Link href={href} className="text-sm text-body transition-colors hover:text-primary">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-slate-200">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-5 py-5 text-xs text-slate-400 sm:flex-row">
          <span>© {new Date().getFullYear()} Gravity One ERP. All rights reserved.</span>
          <span>GST-compliant · ISO-grade security · Made in India</span>
        </div>
      </div>
    </footer>
  );
}
