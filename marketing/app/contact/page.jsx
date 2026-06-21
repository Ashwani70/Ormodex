import DemoForm from "@/components/DemoForm";

export const metadata = {
  title: "Contact & Book a Demo",
  description: "Book a demo of Gravity One ERP. Tell us about your business and our team will reach out to schedule a personalised walkthrough.",
};

export default function ContactPage() {
  return (
    <section id="demo" className="mx-auto grid max-w-7xl items-start gap-12 px-5 py-20 lg:grid-cols-2">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-ink sm:text-4xl">Let's talk</h1>
        <p className="mt-4 max-w-md text-body">
          Whether you want a demo, pricing, or just have questions — fill the form and we'll
          get back within one business day. Your details go straight into our CRM.
        </p>
        <div className="mt-8 space-y-3 text-sm text-body">
          <p>📧 <a className="text-primary hover:underline" href="mailto:sales@gravityone.com">sales@gravityone.com</a></p>
          <p>📞 +91-00000-00000</p>
          <p>🏢 India</p>
        </div>
      </div>
      <div className="rounded-3xl border border-slate-100 bg-white p-6 shadow-card sm:p-8">
        <DemoForm />
      </div>
    </section>
  );
}
