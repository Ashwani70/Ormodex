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
              <Link href={`/blog/${post.slug}`} className="ring-gradient block h-full rounded-2xl border border-white/10 bg-surface p-6 transition hover:-translate-y-1 hover:bg-white/[0.04]">
                <div className="text-xs font-medium text-primary-light">{post.keyword}</div>
                <h2 className="mt-2 text-lg font-bold text-white">{post.title}</h2>
                <p className="mt-2 text-sm text-slate-400">{post.description}</p>
                <div className="mt-4 text-xs text-slate-500">{new Date(post.date).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</div>
              </Link>
            </Reveal>
          ))}
        </div>
      </section>
    </>
  );
}
