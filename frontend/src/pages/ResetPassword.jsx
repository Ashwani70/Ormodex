import { useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import api from "@/lib/api";
import { formatApiErrorDetail } from "@/lib/api";
import { Hammer, ArrowRight, ShieldCheck, CheckCircle2, AlertTriangle, KeyRound } from "lucide-react";
import { Input, Field, PrimaryButton } from "@/components/ui-kit";

const HERO = "/login_hero.webp"; // WebP re-encode — see docs/BUILD_GUIDE.md

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");

    if (!token) {
      setErr("Missing reset token. Please use the link from your email.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setErr("Passwords do not match.");
      return;
    }

    if (newPassword.length < 8) {
      setErr("Password must be at least 8 characters.");
      return;
    }

    setBusy(true);
    try {
      await api.post("/auth/reset-password", {
        token,
        new_password: newPassword,
      });
      setSuccess(true);
    } catch (e) {
      setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setBusy(false);
    }
  };

  const renderContent = () => {
    if (!token) {
      return (
        <div className="mt-8 space-y-4">
          <div
            className="flex items-start gap-3 border border-destructive/20 bg-destructive/10 text-destructive text-sm font-mono px-4 py-3"
            style={{ borderRadius: "var(--radius)" }}
          >
            <AlertTriangle className="w-5 h-5 mt-0.5 shrink-0" />
            <div>
              <div className="font-semibold mb-1">Invalid link</div>
              <div className="text-xs opacity-80">
                This password reset link is invalid or missing. Please request a new one from the login page.
              </div>
            </div>
          </div>
          <Link
            to="/login"
            className="w-full flex items-center justify-center gap-2 text-xs text-yellow-400 hover:text-yellow-300 font-mono tracking-wide transition-colors"
          >
            ← Go to login
          </Link>
        </div>
      );
    }

    if (success) {
      return (
        <div className="mt-8 space-y-4">
          <div
            className="flex items-start gap-3 border border-green-500/20 bg-green-500/10 text-green-400 text-sm font-mono px-4 py-3"
            style={{ borderRadius: "var(--radius)" }}
          >
            <CheckCircle2 className="w-5 h-5 mt-0.5 shrink-0" />
            <div>
              <div className="font-semibold mb-1">Password reset successful</div>
              <div className="text-xs text-green-400/80">
                Your password has been updated. You can now log in with your new password.
              </div>
            </div>
          </div>
          <Link to="/login">
            <PrimaryButton
              type="button"
              testid="reset-go-login"
              className="w-full justify-center"
              icon={ArrowRight}
            >
              Go to login
            </PrimaryButton>
          </Link>
        </div>
      );
    }

    return (
      <form onSubmit={submit} className="mt-8 space-y-4 [&_.label-overline]:text-zinc-300">
        <p className="text-sm text-zinc-400">
          Enter your new password below. It must meet the security policy requirements.
        </p>
        <Field label="New password" required>
          <Input
            data-testid="reset-new-password"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="••••••••"
            autoFocus
            required
            minLength={8}
          />
        </Field>
        <Field label="Confirm new password" required>
          <Input
            data-testid="reset-confirm-password"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="••••••••"
            required
            minLength={8}
          />
        </Field>

        {err && (
          <div
            data-testid="reset-error"
            className="border border-destructive/20 bg-destructive/10 text-destructive text-xs font-mono px-3 py-2"
            style={{ borderRadius: "var(--radius)" }}
          >
            {err}
          </div>
        )}

        <PrimaryButton
          type="submit"
          testid="reset-submit"
          disabled={busy}
          className="w-full justify-center"
          icon={KeyRound}
        >
          {busy ? "Resetting…" : "Set new password"}
        </PrimaryButton>
        <Link
          to="/login"
          className="w-full flex items-center justify-center gap-2 text-xs text-zinc-400 hover:text-zinc-200 font-mono transition-colors"
        >
          ← Back to sign-in
        </Link>
      </form>
    );
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
                Ormodex
              </div>
              <div className="font-mono text-[10px] tracking-[0.3em] uppercase text-yellow-400">
                ERP Platform
              </div>
            </div>
          </div>

          <div className="space-y-6 max-w-md">
            <div className="hazard-stripe h-1.5 w-32" />
            <h2 className="font-display font-black text-4xl leading-tight text-zinc-50">
              Secure password{" "}
              <span className="text-yellow-400">recovery</span>{" "}
              system.
            </h2>
            <p className="text-sm text-zinc-300 leading-relaxed">
              Your account security is our priority. Set a strong password that
              meets enterprise-grade policy requirements.
            </p>
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
          className="w-full max-w-md border border-zinc-800 bg-zinc-900/90 shadow-2xl p-8 sm:p-10 backdrop-blur-xl"
          style={{ borderRadius: "var(--radius)" }}
        >
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <div className="w-10 h-10 bg-yellow-400 flex items-center justify-center" style={{ borderRadius: "var(--radius)" }}>
              <Hammer className="w-5 h-5 text-black" strokeWidth={2.5} />
            </div>
            <div>
              <div className="font-display font-black text-foreground text-lg">
                Ormodex
              </div>
              <div className="font-mono text-[10px] tracking-[0.3em] uppercase text-yellow-400">
                ERP Platform
              </div>
            </div>
          </div>

          <div className="label-overline mb-2 flex items-center gap-2 text-zinc-400">
            <span className="inline-block w-2 h-2 bg-yellow-400" style={{ borderRadius: "var(--radius)" }} />
            Password Recovery
          </div>
          <h1 className="font-display font-black text-3xl sm:text-4xl text-zinc-50 tracking-tight">
            Reset Password
          </h1>
          <p className="mt-2 text-sm text-zinc-400">
            Create a new secure password for your account
          </p>

          {renderContent()}
        </div>
      </div>
    </div>
  );
}
