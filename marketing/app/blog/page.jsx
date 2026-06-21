import Link from "next/link";
import PageHero from "@/components/PageHero";
import Reveal from "@/components/Reveal";
import { POSTS } from "./posts";

export const metadata = {
  title: "Blog — ERP, GST & Inventory insights",
  description: "Guides on ERP software for manufacturing, GST billing software, inventory management and e-Way Bill integration for Indian businesses.",
};

export default function BlogPage() {
  return (
    <>
      <PageHero eyebrow="Blog" title="Insights for modern operations"
        subtitle="Practical guides on ERP, GST, inventory and compliance." />
      <section className="mx-auto max-w-5xl px-5 py-16">
        <div className="grid gap-6 md:grid-cols-2">
          {POSTS.map((post, i) => (
            <Reveal key={post.slug} delay={(i % 2) * 60}>
              <Link href={`/blog/${post.slug}`} className="block h-full rounded-2xl border border-slate-100 bg-white p-6 shadow-soft transition hover:-translate-y-1 hover:shadow-card">
                <div className="text-xs font-medium text-primary">{post.keyword}</div>
                <h2 className="mt-2 text-lg font-bold text-ink">{post.title}</h2>
                <p className="mt-2 text-sm text-body">{post.description}</p>
                <div className="mt-4 text-xs text-slate-400">{new Date(post.date).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</div>
              </Link>
            </Reveal>
          ))}
        </div>
      </section>
    </>
  );
}
