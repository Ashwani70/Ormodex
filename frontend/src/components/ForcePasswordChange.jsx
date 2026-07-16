/**
 * Full-screen gate shown when the signed-in account must change its password
 * (server set `password_change_required` because the current one fails the
 * policy, or an admin forced a reset). Rendered by ProtectedRoute in place of
 * the app until resolved.
 */
import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail } from "@/lib/api";
import { ShieldAlert, ArrowRight, Eye, EyeOff, Check, X } from "lucide-react";
import { Input, Field, PrimaryButton } from "@/components/ui-kit";

// Mirrors backend/core/password_policy.py's rules so the user gets instant
// feedback instead of only a server error after submitting.
const RULES = [
  { key: "length", label: "At least 12 characters", test: (v) => v.length >= 12 },
  { key: "lower", label: "One lowercase letter", test: (v) => /[a-z]/.test(v) },
  { key: "upper", label: "One uppercase letter", test: (v) => /[A-Z]/.test(v) },
  { key: "digit", label: "One digit", test: (v) => /\d/.test(v) },
  { key: "symbol", label: "One symbol", test: (v) => /[^A-Za-z0-9]/.test(v) },
];

function PasswordField({ label, value, onChange, placeholder, testid, required }) {
  const [visible, setVisible] = useState(false);
  return (
    <Field label={label} required={required}>
      <div className="relative">
        <Input
          data-testid={testid}
          type={visible ? "text" : "password"}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          className="pr-10"
          required={required}
        />
        <button
          type="button"
          aria-label={visible ? "Hide password" : "Show password"}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          onClick={() => setVisible((v) => !v)}
          tabIndex={-1}
        >
          {visible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      </div>
    </Field>
  );
}

export default function ForcePasswordChange() {
  const { changePassword, logout } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    if (next !== confirm) {
      setErr("New passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await changePassword(current, next);
      // On success the user object loses the flag and the app un-gates itself.
    } catch (e) {
      setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-950 p-6">
      <div
        className="w-full max-w-md bg-card border border-border shadow-2xl p-8 sm:p-10"
        style={{ borderRadius: "var(--radius)" }}
      >
        <div className="flex items-center gap-3 mb-2 text-yellow-500">
          <ShieldAlert className="w-5 h-5" />
          <div className="label-overline">Password update required</div>
        </div>
        <h1 className="font-display font-black text-2xl text-foreground tracking-tight">
          Update your password
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Your current password no longer meets our security policy. Please set a
          stronger one to continue.
        </p>

        <form onSubmit={submit} className="mt-6 space-y-4">
          <PasswordField
            label="Current password"
            testid="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            placeholder="••••••••"
            required
          />
          <PasswordField
            label="New password"
            testid="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            placeholder="At least 12 characters"
            required
          />

          {next && (
            <ul className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs font-mono">
              {RULES.map((rule) => {
                const pass = rule.test(next);
                return (
                  <li
                    key={rule.key}
                    className={`flex items-center gap-1.5 ${pass ? "text-green-500" : "text-muted-foreground"}`}
                  >
                    {pass ? <Check className="w-3 h-3 shrink-0" /> : <X className="w-3 h-3 shrink-0" />}
                    {rule.label}
                  </li>
                );
              })}
            </ul>
          )}

          <PasswordField
            label="Confirm new password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Re-enter new password"
            required
          />

          {err && (
            <div
              className="border border-destructive/20 bg-destructive/10 text-destructive text-xs font-mono px-3 py-2"
              style={{ borderRadius: "var(--radius)" }}
            >
              {err}
            </div>
          )}

          <PrimaryButton
            type="submit"
            disabled={busy}
            className="w-full justify-center"
            icon={ArrowRight}
          >
            {busy ? "Updating…" : "Update password"}
          </PrimaryButton>
          <button
            type="button"
            className="w-full text-xs text-muted-foreground hover:text-foreground font-mono"
            onClick={logout}
          >
            Sign out instead
          </button>
        </form>
      </div>
    </div>
  );
}
