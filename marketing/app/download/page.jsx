import Link from "next/link";
import PageHero from "@/components/PageHero";
import Reveal from "@/components/Reveal";
import OSDownload from "@/components/OSDownload";
import OSIcon from "@/components/OSIcon";
import AuthButton from "@/components/AuthButton";
import { APP_VERSION } from "@/lib/site";

export const metadata = {
  title: "Download — Windows, macOS & Linux",
  description:
    "Download the Ormodex ERP desktop app for Windows, macOS and Linux, or run it in your browser. Cross-platform, auto-updating, signed installers.",
};

const STEPS = [
  ["Download", "Pick your platform above. The installer is signed and ~80 MB."],
  ["Install", "Run the installer — Windows .exe, macOS .dmg or Linux .AppImage."],
  ["Sign in", "Open the app and log in with your Ormodex account. Your data syncs instantly."],
];

const REQUIREMENTS = [
  ["Windows", "windows", "Windows 10 / 11 (64-bit) · 4 GB RAM · 500 MB disk"],
  ["macOS", "apple", "macOS 12 Monterey or later · Apple Silicon & Intel"],
  ["Linux", "linux", "Ubuntu 20.04+ / Debian / Fedora · glibc 2.31+"],
];

const FAQ = [
  ["Do I need to download to use it?", "No — Ormodex runs fully in the browser too. The desktop apps add offline drafts, faster printing and OS notifications."],
  ["Is it the same on every platform?", "Yes. The same features, data and login work across Windows, macOS, Linux and web. Switch devices anytime."],
  ["How do updates work?", "Desktop apps auto-update in the background, so you're always on the latest, most secure version."],
];

export default function DownloadPage() {
  return (
    <>
      <PageHero
        eyebrow="Download"
        title="Get Ormodex on every device"
        subtitle={`Native apps for Windows, macOS and Linux — or open it in the browser. Current version v${APP_VERSION}.`}
      />

      <section className="mx-auto max-w-7xl px-5 py-16">
        <Reveal>
          <OSDownload />
        </Reveal>

        <div className="mt-8 text-center">
          <span className="text-sm text-body">Prefer no install? </span>
          <AuthButton variant="nav" />
        </div>
      </section>

      {/* 3-step install */}
      <section className="bg-soft py-20">
        <div className="mx-auto max-w-7xl px-5">
          <Reveal className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight text-ink">Up and running in minutes</h2>
          </Reveal>
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {STEPS.map(([t, d], i) => (
              <Reveal key={t} delay={i * 80}>
                <div className="h-full rounded-2xl border border-slate-100 bg-white p-7 shadow-soft">
                  <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-primary font-bold text-white">
                    {i + 1}
                  </div>
                  <h3 className="text-lg font-bold text-ink">{t}</h3>
                  <p className="mt-2 text-sm text-body">{d}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* system requirements */}
      <section className="mx-auto max-w-7xl px-5 py-20">
        <Reveal className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-ink">System requirements</h2>
        </Reveal>
        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {REQUIREMENTS.map(([os, icon, req]) => (
            <Reveal key={os}>
              <div className="flex h-full items-start gap-4 rounded-2xl border border-slate-100 bg-white p-6 shadow-soft">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-mint text-primary">
                  <OSIcon name={icon} className="h-6 w-6" />
                </span>
                <div>
                  <h3 className="font-bold text-ink">{os}</h3>
                  <p className="mt-1 text-sm text-body">{req}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* download FAQ */}
      <section className="bg-soft py-20">
        <div className="mx-auto max-w-3xl px-5">
          <Reveal className="text-center">
            <h2 className="text-3xl font-bold tracking-tight text-ink">Download FAQ</h2>
          </Reveal>
          <div className="mt-10 space-y-3">
            {FAQ.map(([q, a], i) => (
              <Reveal key={q} delay={i * 40}>
                <details className="group rounded-2xl border border-slate-100 bg-white p-5 shadow-soft [&_summary]:cursor-pointer">
                  <summary className="flex items-center justify-between font-semibold text-ink marker:content-['']">
                    {q}
                    <span className="ml-4 text-primary transition group-open:rotate-45">+</span>
                  </summary>
                  <p className="mt-3 text-sm leading-relaxed text-body">{a}</p>
                </details>
              </Reveal>
            ))}
          </div>
          <div className="mt-10 text-center">
            <Link href="/docs" className="text-sm font-semibold text-primary hover:text-primary-dark">
              Read the documentation →
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
