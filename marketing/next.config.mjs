/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The marketing site talks to the ERP backend for lead capture. Set this in
  // Vercel (or .env.local) to the deployed API base, e.g. https://api.gravityone.com
  env: {
    NEXT_PUBLIC_ERP_API_BASE: process.env.NEXT_PUBLIC_ERP_API_BASE || "http://localhost:8000/api",
  },
};

export default nextConfig;
