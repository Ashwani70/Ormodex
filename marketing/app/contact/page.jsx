import DemoForm from "@/components/DemoForm";

export const metadata = {
  title: "Contact & Book a Demo",
  description: "Book a demo of Gravity One ERP. Tell us about your business and our team will reach out to schedule a personalised walkthrough.",
};

export default function ContactPage() {
  return (
    <section id="demo" className="mx-auto grid max-w-7xl items-start gap-12 px-5 py-16 lg:grid-cols-2">
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight text-white sm:text-4xl">Let's talk</h1>
        <p className="mt-4 max-w-md text-slate-300">
          Whether you want a demo, pricing, or just have questions — fill the form and we'll
          get back within one business day. Your details go straight into our CRM.
        </p>
        <div className="mt-8 space-y-3 text-sm text-slate-300">
          <p>📧 <a className="text-primary-light hover:underline" href="mailto:sales@gravityone.com">sales@gravityone.com</a></p>
          <p>📞 +91-00000-00000</p>
          <p>🏢 India</p>
        </div>
      </div>
      <div className="glass-strong rounded-3xl p-6 shadow-card sm:p-8">
        <DemoForm />
      </div>
    </section>
  );
}
