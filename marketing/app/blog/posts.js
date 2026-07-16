// Blog content, keyed by slug. SEO-targeted articles for the keywords in the
// brief. Body is an array of {h, p} blocks rendered by the post page. Swap for a
// CMS/MDX source later — the page reads from here.
export const POSTS = [
  {
    slug: "erp-software-for-manufacturing",
    title: "ERP Software for Manufacturing: A Practical Buyer's Guide",
    description: "What manufacturing companies should look for in an ERP — BOMs, work orders, costing, GST and real-time stock.",
    date: "2026-01-15",
    keyword: "ERP software for manufacturing",
    body: [
      { h: "Why manufacturers outgrow spreadsheets", p: "As order volume grows, disconnected spreadsheets create stock mismatches, costing errors and late invoices. A manufacturing ERP unifies production, inventory and accounting on one database." },
      { h: "Must-have modules", p: "Look for bills of material, work orders, multi-warehouse inventory with batch/serial tracking, production costing, and GST-ready accounting with e-Invoicing and e-Way Bill generation built in." },
      { h: "Real-time visibility", p: "The biggest payoff is live reporting: knowing today's WIP, stock and receivables — not last month's. Role-based dashboards keep the shop floor, sales and finance aligned." },
    ],
  },
  {
    slug: "gst-billing-software",
    title: "Choosing GST Billing Software in India",
    description: "GST billing software essentials: compliant invoices, e-Invoicing (IRN/QR), e-Way Bills and returns-ready reports.",
    date: "2026-01-20",
    keyword: "GST billing software",
    body: [
      { h: "What 'GST-compliant' really means", p: "Beyond adding tax to an invoice, true GST billing software produces returns-ready data, reconciles ITC, and generates IRNs and e-Way Bills without a separate portal." },
      { h: "Avoid last-minute filing stress", p: "When billing, inventory and accounting share one ledger, your GST returns assemble themselves — no manual collation across tools." },
    ],
  },
  {
    slug: "erp-for-forging-companies",
    title: "ERP for Forging Companies: Heat-wise Tracking & Job Work",
    description: "How forging and casting units use ERP for heat-wise tracking, scrap accounting, die management and job-work outsourcing.",
    date: "2026-01-25",
    keyword: "ERP for forging companies",
    body: [
      { h: "Forging-specific challenges", p: "Heat numbers, scrap recovery, die/tooling life and job-work outsourcing don't fit generic ERP. You need workflows designed for the forging shop floor." },
      { h: "Job-work made simple", p: "Track material sent out, receive finished goods, and reconcile job-work challans for ITC-04 — all inside the same system as your billing and stock." },
    ],
  },
  {
    slug: "inventory-management-software-india",
    title: "Inventory Management Software in India: A Checklist",
    description: "Multi-warehouse stock, batch/serial tracking, valuation methods and real-time accuracy for Indian businesses.",
    date: "2026-02-01",
    keyword: "inventory management software India",
    body: [
      { h: "Accuracy is the whole game", p: "If the books don't match the rack, sales over-commit and purchasing over-buys. Real-time inventory with barcode-friendly transfers fixes the root cause." },
      { h: "Valuation that auditors accept", p: "Support for FIFO, weighted average and standard costing keeps your stock valuation defensible at year-end." },
    ],
  },
  {
    slug: "e-way-bill-integrated-erp",
    title: "Why an e-Way Bill Integrated ERP Saves Hours",
    description: "Generate and track e-Way Bills inline with dispatch — no separate portal, no re-keying.",
    date: "2026-02-05",
    keyword: "e-Way Bill integrated ERP",
    body: [
      { h: "The portal-hopping tax", p: "Keying invoice data into the e-Way Bill portal by hand is slow and error-prone. An integrated ERP generates the EWB from the dispatch itself." },
      { h: "Compliance without friction", p: "Inline e-Invoicing (IRN/QR) plus e-Way Bills means one screen, one click, and an audit trail that stays consistent." },
    ],
  },
];

export const getPost = (slug) => POSTS.find((p) => p.slug === slug);
