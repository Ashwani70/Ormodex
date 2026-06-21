# Gravity One ERP — Marketing Website

A premium B2B SaaS marketing site for Gravity One ERP, built with **Next.js 14
(App Router) + Tailwind CSS**, deployable to **Vercel**. It is a *separate*
project from the ERP product app (which lives in `../frontend`).

## Stack
- **Next.js 14** (App Router, SSG/SSR for SEO), **Tailwind CSS 3**, **Inter** font.
- SEO: per-page metadata, OpenGraph, JSON-LD schema (`SoftwareApplication` +
  `BlogPosting`), `sitemap.xml`, `robots.txt`.
- Lead capture posts to the ERP backend (`POST /api/public/demo-request`), which
  creates a CRM **Lead** (`source = "Website"`).

## Pages
Home, Features, Industries, Pricing, About, Contact, Blog (+ SEO articles).

## Homepage sections
Hero (with dashboard mockup + customer logos), problems, feature cards, industry
solutions, benefits, product tour / screenshots, pricing, testimonials, FAQ,
contact/demo form. Scroll-reveal animations throughout; floating WhatsApp button.

## Run locally
```bash
cd marketing
cp .env.example .env.local      # set NEXT_PUBLIC_ERP_API_BASE etc.
npm install
npm run dev                     # http://localhost:3100
```
The ERP backend must be running (default `http://localhost:8000`) for the demo
form to submit. Its CORS already allows localhost:3000; if you run this on a
different port/host, add that origin to the backend CORS list in `backend/server.py`.

## Deploy (Vercel)
1. Import the `marketing/` directory as a Vercel project.
2. Set env vars: `NEXT_PUBLIC_ERP_API_BASE` (deployed API), `NEXT_PUBLIC_SITE_URL`,
   optional `NEXT_PUBLIC_GA_ID`, `NEXT_PUBLIC_WHATSAPP`.
3. Add the production site origin to the backend CORS allow-list.

## Customising
- **Colors / fonts**: `tailwind.config.js`.
- **Copy / sections**: data arrays at the top of `app/page.jsx`.
- **Blog posts**: `app/blog/posts.js` (swap for a CMS/MDX later).
- **Real screenshots / video**: replace `components/DashboardMockup.jsx` and the
  product-tour placeholder in `app/page.jsx` with real assets.
