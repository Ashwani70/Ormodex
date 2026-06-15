import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail } from "@/lib/api";
import { Hammer, ArrowRight, ShieldCheck } from "lucide-react";
import { Input, Field, PrimaryButton } from "@/components/ui-kit";

const HERO = "/login_hero.png";

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("admin@gravityone.com");
  const [password, setPassword] = useState("Admin@123");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  if (user && user !== false) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await login(email, password);
      navigate("/", { replace: true });
    } catch (e) {
      setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-zinc-950">
      {/* Left: image */}
      <div
        className="dark-panel hidden lg:block lg:w-1/2 relative bg-cover bg-center"
        style={{ backgroundImage: `url(${HERO})` }}
      >
        <div className="absolute inset-0 bg-black/80" />
        <div className="absolute inset-0 flex flex-col justify-between p-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-yellow-400 flex items-center justify-center" style={{ borderRadius: "var(--radius)" }}>
              <Hammer className="w-5 h-5 text-black" strokeWidth={2.5} />
            </div>
            <div>
              <div className="font-display font-black text-zinc-50 text-lg leading-none">
                GravityOne
              </div>
              <div className="font-mono text-[10px] tracking-[0.3em] uppercase text-yellow-400">
                ERP Platform
              </div>
            </div>
          </div>

          <div className="space-y-6 max-w-md">
            <div className="hazard-stripe h-1.5 w-32" />
            <h2 className="font-display font-black text-4xl leading-tight text-zinc-50">
              The intelligent ERP for{" "}
              <span className="text-yellow-400">modern enterprise</span>{" "}
              operations.
            </h2>
            <p className="text-sm text-zinc-300 leading-relaxed">
              Manage CRM, HRM, Payroll, Inventory, GST invoices, Accounting,
              Manufacturing, Procurement and AI-powered analytics — all in one
              enterprise-grade platform.
            </p>
            <div className="grid grid-cols-3 gap-px bg-zinc-800 border border-zinc-800 max-w-md" style={{ borderRadius: "var(--radius)", overflow: "hidden" }}>
              {[
                ["15", "Modules"],
                ["GST", "Compliant"],
                ["AI", "Powered"],
              ].map(([v, l]) => (
                <div key={l} className="bg-zinc-950 p-4 text-center">
                  <div className="font-display font-black text-yellow-400 text-2xl">
                    {v}
                  </div>
                  <div className="font-mono text-[10px] uppercase tracking-wider text-zinc-500">
                    {l}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3 text-zinc-500 text-xs font-mono uppercase tracking-wider">
            <ShieldCheck className="w-4 h-4 text-green-500" />
            ISO-grade security · End-to-end encrypted
          </div>
        </div>
      </div>

      {/* Right: form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-6 lg:p-12">
        <div 
          className="w-full max-w-md bg-card border border-border shadow-2xl p-8 sm:p-10"
          style={{ borderRadius: "var(--radius)" }}
        >
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <div className="w-10 h-10 bg-yellow-400 flex items-center justify-center" style={{ borderRadius: "var(--radius)" }}>
              <Hammer className="w-5 h-5 text-black" strokeWidth={2.5} />
            </div>
            <div>
              <div className="font-display font-black text-zinc-50 text-lg">
                GravityOne
              </div>
              <div className="font-mono text-[10px] tracking-[0.3em] uppercase text-yellow-400">
                ERP Platform
              </div>
            </div>
          </div>

          <div className="label-overline mb-2 flex items-center gap-2">
            <span className="inline-block w-2 h-2 bg-yellow-400" style={{ borderRadius: "var(--radius)" }} />
            Operator Sign-in
          </div>
          <h1 className="font-display font-black text-3xl sm:text-4xl text-zinc-50 tracking-tight">
            GravityOne ERP
          </h1>
          <p className="mt-2 text-sm text-zinc-400">
            AI-Powered Business Management Platform
          </p>

          <form onSubmit={submit} className="mt-8 space-y-4">
            <Field label="Email" required>
              <Input
                data-testid="login-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@gravityone.com"
                required
              />
            </Field>
            <Field label="Password" required>
              <Input
                data-testid="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
            </Field>

            {err && (
              <div
                data-testid="login-error"
                className="border border-red-900 bg-red-950/40 text-red-400 text-xs font-mono px-3 py-2"
                style={{ borderRadius: "var(--radius)" }}
              >
                {err}
              </div>
            )}

            <PrimaryButton
              type="submit"
              testid="login-submit"
              disabled={busy}
              className="w-full justify-center"
              icon={ArrowRight}
            >
              {busy ? "Authenticating…" : "Enter system"}
            </PrimaryButton>
          </form>

          <div className="mt-6 border border-zinc-800 p-3 bg-zinc-900/40" style={{ borderRadius: "var(--radius)" }}>
            <div className="label-overline mb-1">Default Admin</div>
            <div className="font-mono text-xs text-zinc-300">
              admin@gravityone.com · Admin@123
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
