import { POSTS } from "./blog/posts";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://ormodex.com";

export default function sitemap() {
  const pages = ["", "/features", "/industries", "/pricing", "/download", "/docs", "/about", "/contact", "/blog"].map((p) => ({
    url: `${SITE_URL}${p}`,
    lastModified: new Date(),
    changeFrequency: "weekly",
    priority: p === "" ? 1 : 0.7,
  }));
  const posts = POSTS.map((post) => ({
    url: `${SITE_URL}/blog/${post.slug}`,
    lastModified: new Date(post.date),
    changeFrequency: "monthly",
    priority: 0.6,
  }));
  return [...pages, ...posts];
}
