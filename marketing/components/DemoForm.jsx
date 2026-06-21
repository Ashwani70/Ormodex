"use client";
import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_ERP_API_BASE || "http://localhost:8000/api";

const INDUSTRIES = ["Manufacturing", "Forging & Casting", "Garments", "Trading", "Export Business", "Other"];

const field =
  "w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-slate-400 outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20";
const labelCls = "mb-1 block text-xs font-semibold text-ink";

export default function DemoForm() {
  const [form, setForm] = useState({
    name: "", company_name: "", industry: "", email: "", phone: "", num_users: "", requirements: "", website: "",
  });
  const [status, setStatus] = useState("idle"); // idle | sending | ok | error
  const [error, setError] = useState("");

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setStatus("sending");
    setError("");
    try {
      const res = await fetch(`${API_BASE}/public/demo-request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name,
          company_name: form.company_name,
          industry: form.industry || null,
          email: form.email,
          phone: form.phone || null,
          num_users: form.num_users ? Number(form.num_users) : null,
          requirements: form.requirements || null,
          website: form.website || null, // honeypot
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Submission failed. Please try again.");
      }
      setStatus("ok");
      setForm({ name: "", company_name: "", industry: "", email: "", phone: "", num_users: "", requirements: "", website: "" });
    } catch (err) {
      setStatus("error");
      setError(err.message);
    }
  };

  if (status === "ok") {
    return (
      <div className="rounded-2xl border border-primary/30 bg-mint p-8 text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary text-white">✓</div>
        <h3 className="text-lg font-bold text-ink">Thank you!</h3>
        <p className="mt-1 text-sm text-body">
          Your request has reached our team. We'll get in touch shortly to schedule your demo.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-3.5">
      <div className="grid gap-3.5 sm:grid-cols-2">
        <div>
          <label className={labelCls}>Name *</label>
          <input className={field} required value={form.name} onChange={set("name")} placeholder="Your name" />
        </div>
        <div>
          <label className={labelCls}>Company Name *</label>
          <input className={field} required value={form.company_name} onChange={set("company_name")} placeholder="Company" />
        </div>
        <div>
          <label className={labelCls}>Industry</label>
          <select className={field} value={form.industry} onChange={set("industry")}>
            <option value="">Select industry</option>
            {INDUSTRIES.map((i) => <option key={i} value={i}>{i}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls}>Email *</label>
          <input type="email" className={field} required value={form.email} onChange={set("email")} placeholder="you@company.com" />
        </div>
        <div>
          <label className={labelCls}>Phone Number</label>
          <input className={field} value={form.phone} onChange={set("phone")} placeholder="+91 ..." />
        </div>
        <div>
          <label className={labelCls}>Number of Users</label>
          <input type="number" min="1" className={field} value={form.num_users} onChange={set("num_users")} placeholder="e.g. 25" />
        </div>
      </div>
      <div>
        <label className={labelCls}>Requirements</label>
        <textarea rows={3} className={field} value={form.requirements} onChange={set("requirements")} placeholder="Tell us what you need…" />
      </div>

      {/* Honeypot — hidden from users, catches bots. */}
      <input
        type="text" tabIndex={-1} autoComplete="off" aria-hidden="true"
        className="hidden" value={form.website} onChange={set("website")}
      />

      {status === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
      )}

      <button
        type="submit"
        disabled={status === "sending"}
        className="w-full rounded-md bg-primary px-5 py-3 text-sm font-semibold text-white shadow-soft transition hover:bg-primary-dark disabled:opacity-60"
      >
        {status === "sending" ? "Sending…" : "Book a Demo"}
      </button>
      <p className="text-center text-xs text-slate-400">We'll never share your details. Submissions go straight to our team.</p>
    </form>
  );
}
