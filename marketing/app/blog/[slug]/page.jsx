import Link from "next/link";
import { notFound } from "next/navigation";
import { POSTS, getPost } from "../posts";

// Pre-render every post at build time (SSG) for SEO + speed.
export function generateStaticParams() {
  return POSTS.map((p) => ({ slug: p.slug }));
}

export function generateMetadata({ params }) {
  const post = getPost(params.slug);
  if (!post) return { title: "Article not found" };
  return {
    title: post.title,
    description: post.description,
    openGraph: { title: post.title, description: post.description, type: "article" },
  };
}

export default function BlogPost({ params }) {
  const post = getPost(params.slug);
  if (!post) notFound();

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    headline: post.title,
    description: post.description,
    datePublished: post.date,
    keywords: post.keyword,
    author: { "@type": "Organization", name: "Ormodex ERP" },
  };

  return (
    <article className="mx-auto max-w-3xl px-5 py-16">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <Link href="/blog" className="text-sm font-medium text-primary hover:underline">← Back to blog</Link>
      <h1 className="mt-4 text-3xl font-bold tracking-tight text-ink sm:text-4xl">{post.title}</h1>
      <p className="mt-2 text-sm text-slate-400">
        {new Date(post.date).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}
      </p>
      <div className="mt-8 space-y-8">
        {post.body.map((block, i) => (
          <section key={i}>
            <h2 className="text-xl font-bold text-ink">{block.h}</h2>
            <p className="mt-2 leading-relaxed text-body">{block.p}</p>
          </section>
        ))}
      </div>
      <div className="mt-12 rounded-3xl border border-primary/20 bg-mint p-8 text-center">
        <h3 className="text-xl font-bold text-ink">See Ormodex ERP in action</h3>
        <p className="mt-2 text-sm text-body">Book a personalised demo for your industry.</p>
        <Link href="/contact#demo" className="mt-5 inline-block rounded-md bg-primary px-6 py-3 text-sm font-semibold text-white shadow-soft transition hover:bg-primary-dark">Book a Demo</Link>
      </div>
    </article>
  );
}
