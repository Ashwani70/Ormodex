import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail } from "@/lib/api";
import api from "@/lib/api";
import { ArrowRight, ShieldCheck, Mail, ArrowLeft, CheckCircle2, Eye, EyeOff, Lock } from "lucide-react";
import { Input, Field, PrimaryButton } from "@/components/ui-kit";
import Logo, { BRAND } from "@/components/Logo";

const HERO = "/login_hero.webp"; // WebP re-encode of the original ~827KB PNG (~127KB) — see docs/BUILD_GUIDE.md
const CAPTCHA_AFTER_FAILURES = 5;

export default function Login() {
  const { user, login, completeMfaLogin } = useAuth();
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [companyCode, setCompanyCode] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [failCount, setFailCount] = useState(0);
  // Locked-account state (423 from the server), with the retry hint if given.
  const [locked, setLocked] = useState(false);
  // CAPTCHA: fetched once failCount crosses the threshold; re-fetched on wrong answer.
  const [captcha, setCaptcha] = useState(null); // { token, question }
  const [captchaAnswer, setCaptchaAnswer] = useState("");
  // MFA second step: set once the password step reports an MFA-enabled account.
  const [mfaToken, setMfaToken] = useState(null);
  const [mfaCode, setMfaCode] = useState("");
  // Forgot password flow
  const [showForgot, setShowForgot] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotSent, setForgotSent] = useState(false);

  if (user && user !== false) return <Navigate to="/" replace />;

  const needsCaptcha = failCount >= CAPTCHA_AFTER_FAILURES;

  const fetchCaptcha = async () => {
    try {
      const { data } = await api.get("/auth/captcha");
      setCaptcha(data);
      setCaptchaAnswer("");
    } catch {
      setCaptcha(null);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    setLocked(false);
    setBusy(true);
    try {
      const result = await login(identifier, password, {
        rememberMe,
        companyCode,
        captchaToken: captcha?.token,
        captchaAnswer,
      });
      if (result && result.mfaRequired) {
        setMfaToken(result.mfaToken);
        return; // render the code-entry step instead of navigating
      }
      navigate("/", { replace: true });
    } catch (e) {
      if (e.response?.status === 423) {
        setLocked(true);
        setErr(formatApiErrorDetail(e.response?.data?.detail) || "Account locked.");
      } else {
        const next = failCount + 1;
        setFailCount(next);
        setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
        if (next >= CAPTCHA_AFTER_FAILURES) {
          await fetchCaptcha();
        } else if (captcha) {
          // Wrong CAPTCHA answer on a subsequent attempt — refresh the challenge.
          await fetchCaptcha();
        }
      }
    } finally {
      setBusy(false);
    }
  };

  const submitMfa = async (e) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await completeMfaLogin(mfaToken, mfaCode.trim());
      navigate("/", { replace: true });
    } catch (e) {
      setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setBusy(false);
    }
  };

  const submitForgot = async (e) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await api.post("/auth/forgot-password", { email: forgotEmail });
      setForgotSent(true);
    } catch (e) {
      setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setBusy(false);
    }
  };

  const backToLogin = () => {
    setShowForgot(false);
    setForgotSent(false);
    setForgotEmail("");
    setErr("");
  };

  // ── Render form content based on current state ──
  const renderForm = () => {
    // MFA code entry step
    if (mfaToken) {
      return (
        <form onSubmit={submitMfa} className="mt-8 space-y-4">
          <p className="text-sm text-muted-foreground">
            Enter the 6-digit code from your authenticator app, or a recovery
            code.
          </p>
          <Field label="Authentication code" required>
            <Input
              data-testid="login-mfa-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
              placeholder="123456"
              required
            />
          </Field>

          {err && (
            <div
              data-testid="login-error"
              className="border border-destructive/20 bg-destructive/10 text-destructive text-xs font-mono px-3 py-2"
              style={{ borderRadius: "var(--radius)" }}
            >
              {err}
            </div>
          )}

          <PrimaryButton
            type="submit"
            testid="login-mfa-submit"
            disabled={busy}
            className="w-full justify-center"
            icon={ArrowRight}
          >
            {busy ? "Verifying…" : "Verify"}
          </PrimaryButton>
          <button
            type="button"
            className="w-full text-xs text-muted-foreground hover:text-foreground font-mono transition-colors"
            onClick={() => { setMfaToken(null); setMfaCode(""); setErr(""); }}
          >
            ← Back to sign-in
          </button>
        </form>
      );
    }

    // Forgot password: success state
    if (showForgot && forgotSent) {
      return (
        <div className="mt-8 space-y-4">
          <div
            className="flex items-start gap-3 border border-green-600/25 bg-green-500/10 text-green-700 text-sm font-mono px-4 py-3"
            style={{ borderRadius: "var(--radius)" }}
          >
            <CheckCircle2 className="w-5 h-5 mt-0.5 shrink-0" />
            <div>
              <div className="font-semibold mb-1">Reset link sent</div>
              <div className="text-xs text-green-700/80">
                If <span className="font-semibold">{forgotEmail}</span> is registered, a password reset link has been sent to that email. Please check your inbox (and spam folder).
              </div>
            </div>
          </div>
          <button
            type="button"
            className="w-full flex items-center justify-center gap-2 text-xs text-muted-foreground hover:text-foreground font-mono transition-colors"
            onClick={backToLogin}
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to sign-in
          </button>
        </div>
      );
    }

    // Forgot password: form
    if (showForgot) {
      return (
        <form onSubmit={submitForgot} className="mt-8 space-y-4">
          <p className="text-sm text-muted-foreground">
            Enter your registered email address and we'll send you a link to reset your password.
          </p>
          <Field label="Email address" required>
            <Input
              data-testid="forgot-email"
              type="email"
              value={forgotEmail}
              onChange={(e) => setForgotEmail(e.target.value)}
              placeholder="you@company.com"
              autoFocus
              required
            />
          </Field>

          {err && (
            <div
              data-testid="forgot-error"
              className="border border-destructive/20 bg-destructive/10 text-destructive text-xs font-mono px-3 py-2"
              style={{ borderRadius: "var(--radius)" }}
            >
              {err}
            </div>
          )}

          <PrimaryButton
            type="submit"
            testid="forgot-submit"
            disabled={busy}
            className="w-full justify-center"
            icon={Mail}
          >
            {busy ? "Sending…" : "Send reset link"}
          </PrimaryButton>
          <button
            type="button"
            className="w-full flex items-center justify-center gap-2 text-xs text-muted-foreground hover:text-foreground font-mono transition-colors"
            onClick={backToLogin}
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to sign-in
          </button>
        </form>
      );
    }

    // Default: login form
    return (
      <form onSubmit={submit} className="mt-8 space-y-4">
        <Field label="Email or Username" required>
          <Input
            data-testid="login-email"
            type="text"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            placeholder="you@company.com or username"
            autoComplete="username"
            required
          />
        </Field>
        <Field label="Password" required>
          <div className="relative">
            <Input
              data-testid="login-password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              className="pr-10"
              required
            />
            <button
              type="button"
              data-testid="login-toggle-password"
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              onClick={() => setShowPassword((v) => !v)}
              tabIndex={-1}
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </Field>

        <Field label="Company code (optional)">
          <Input
            data-testid="login-company-code"
            type="text"
            value={companyCode}
            onChange={(e) => setCompanyCode(e.target.value)}
            placeholder="Leave blank unless your admin gave you one"
          />
        </Field>

        {needsCaptcha && captcha && (
          <Field label={`Verify: ${captcha.question}`} required>
            <Input
              data-testid="login-captcha-answer"
              type="text"
              inputMode="numeric"
              value={captchaAnswer}
              onChange={(e) => setCaptchaAnswer(e.target.value)}
              placeholder="Answer"
              required
            />
          </Field>
        )}

        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-xs text-muted-foreground font-mono cursor-pointer select-none">
            <input
              data-testid="login-remember-me"
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="h-3.5 w-3.5 accent-primary"
            />
            Remember me
          </label>
          <button
            type="button"
            data-testid="forgot-password-link"
            className="text-xs text-primary hover:text-primary/80 font-mono tracking-wide transition-colors"
            onClick={() => { setShowForgot(true); setErr(""); }}
          >
            Forgot password?
          </button>
        </div>

        {err && (
          <div
            data-testid="login-error"
            className="flex items-start gap-2 border border-destructive/20 bg-destructive/10 text-destructive text-xs font-mono px-3 py-2"
            style={{ borderRadius: "var(--radius)" }}
          >
            {locked && <Lock className="w-3.5 h-3.5 mt-0.5 shrink-0" />}
            <span>{err}</span>
          </div>
        )}

        <PrimaryButton
          type="submit"
          testid="login-submit"
          disabled={busy || locked}
          className="w-full justify-center"
          icon={ArrowRight}
        >
          {busy ? "Authenticating…" : "Enter system"}
        </PrimaryButton>
      </form>
    );
  };

  return (
    <div className="min-h-screen flex bg-background">
      {/* Left: image */}
      <div
        className="hidden lg:block lg:w-1/2 relative bg-cover bg-center"
        style={{ backgroundImage: `url(${HERO})` }}
      >
        {/* Readability scrim: darker behind the text (left/bottom), lighter on the
            right so the supply-chain artwork stays visible instead of a near-black wash. */}
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(105deg, rgba(8,11,24,0.86) 0%, rgba(8,11,24,0.62) 42%, rgba(8,11,24,0.30) 100%), linear-gradient(0deg, rgba(8,11,24,0.55) 0%, rgba(8,11,24,0) 45%)",
          }}
        />
        <div className="absolute inset-0 flex flex-col justify-between p-10">
          {/* Brand — logo image (transparent, sits on the dark hero) with a
              styled text wordmark fallback until the asset is uploaded. */}
          <div className="bg-white/95 rounded-lg px-4 py-2.5 w-fit shadow-lg">
            <Logo variant="full" size="md" alt={BRAND.name} />
          </div>

          <div className="space-y-6 max-w-md">
            <div className="hazard-stripe h-1.5 w-32" />
            <h2 className="font-display font-black text-4xl leading-tight text-zinc-50">
              The intelligent ERP for{" "}
              <span className="text-teal-400">modern enterprise</span>{" "}
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
                  <div className="font-display font-black text-teal-400 text-2xl">
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

      {/* Right: form — light Aurora card (matches the app's design system, and
          the navy-lettered brand logo is actually readable on a white card —
          it was invisible on the old dark zinc-900 panel). Teal hazard-stripe
          on top ties it to the app's modal/dialog motif. */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-6 lg:p-12">
        <div
          className="w-full max-w-md border border-border bg-card shadow-xl overflow-hidden"
          style={{ borderRadius: "var(--radius)" }}
        >
          <div className="hazard-stripe h-1.5 w-full" style={{ borderRadius: 0 }} />
          <div className="p-8 sm:p-10">
            {/* Top-center brand: logo + name + tagline (all breakpoints) */}
            <div className="flex flex-col items-center text-center mb-8">
              <Logo variant="full" size="lg" alt={BRAND.name} clickable={false} />
              <div className="mt-3 font-mono text-[10px] tracking-[0.3em] uppercase text-muted-foreground">
                {BRAND.tagline}
              </div>
            </div>

            <div className="label-overline mb-2 flex items-center gap-2 text-muted-foreground">
              <span className="inline-block w-2 h-2 bg-primary" style={{ borderRadius: "var(--radius)" }} />
              {showForgot ? "Password Recovery" : "Operator Sign-in"}
            </div>
            <h1 className="font-display font-black text-3xl sm:text-4xl text-foreground tracking-tight">
              {showForgot ? "Reset Password" : "Ormodex ERP"}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {showForgot
                ? "We'll send a secure reset link to your email"
                : "AI-Powered Business Management Platform"}
            </p>

            {renderForm()}

            <div className="mt-6 text-center font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              v2.3.1 — Stable Release
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
