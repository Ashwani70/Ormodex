import "./globals.css";
import Script from "next/script";
import { Inter } from "next/font/google";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import WhatsAppButton from "@/components/WhatsAppButton";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://gravityone.com";
const GA_ID = process.env.NEXT_PUBLIC_GA_ID; // e.g. G-XXXXXXX

export const metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Gravity One ERP — Streamline Your Business Operations",
    template: "%s | Gravity One ERP",
  },
  description:
    "Manage sales, inventory, accounting, GST, production, HR, and e-Way Bills from a single platform. ERP software for manufacturing, forging, garments, trading and exporters.",
  keywords: [
    "ERP software for manufacturing", "GST billing software", "ERP for forging companies",
    "inventory management software India", "e-Way Bill integrated ERP", "ERP software India",
  ],
  openGraph: {
    type: "website",
    title: "Gravity One ERP — Streamline Your Business Operations",
    description: "All-in-one GST-compliant ERP for manufacturing, forging, garments, trading and exporters.",
    url: SITE_URL,
    siteName: "Gravity One ERP",
  },
  twitter: { card: "summary_large_image", title: "Gravity One ERP" },
  robots: { index: true, follow: true },
};

export const viewport = {
  themeColor: "#070912",
};

// Organization + SoftwareApplication schema for rich SEO results.
const jsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "Gravity One ERP",
  applicationCategory: "BusinessApplication",
  operatingSystem: "Windows, macOS, Linux, Web",
  offers: { "@type": "Offer", price: "0", priceCurrency: "INR", description: "Free trial available" },
  description:
    "All-in-one GST-compliant ERP for manufacturing, forging, garments, trading and exporters.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${inter.variable} dark`}>
      <body className="bg-canvas font-sans text-slate-200 antialiased">
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
        <Navbar />
        <main>{children}</main>
        <Footer />
        <WhatsAppButton />

        {GA_ID && (
          <>
            <Script src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`} strategy="afterInteractive" />
            <Script id="ga" strategy="afterInteractive">
              {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','${GA_ID}');`}
            </Script>
          </>
        )}
      </body>
    </html>
  );
}
